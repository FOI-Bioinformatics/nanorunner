"""Tests for ``atomic_move`` cross-filesystem fallback.

Pre-fix nanorunner used ``Path.rename`` directly, which raises
``OSError: [Errno 18] Cross-device link`` when the source and target
live on different filesystems. The 2026-05-06 audit flagged this as
a real production hazard for macOS Docker bind-mounts and
NFS-backed scratch dirs.

These tests pin the expected behaviour: same-FS moves are atomic
renames, cross-FS moves fall back to copy-then-delete, and other
OSErrors propagate so callers can clean up the tmp file.
"""

from __future__ import annotations

import errno
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from nanopore_simulator.fastq import atomic_move, atomic_tmp_path


def _write_bytes(path: Path, content: bytes = b"data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


class TestAtomicMoveSameFilesystem:
    def test_moves_file_to_target(self, tmp_path):
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        _write_bytes(src, b"payload")

        atomic_move(src, dst)

        assert dst.read_bytes() == b"payload"
        assert not src.exists()

    def test_overwrites_existing_target(self, tmp_path):
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        _write_bytes(src, b"new")
        _write_bytes(dst, b"old")

        atomic_move(src, dst)

        assert dst.read_bytes() == b"new"

    def test_round_trip_with_atomic_tmp_path(self, tmp_path):
        # The canonical usage: write to atomic_tmp_path(target), then
        # atomic_move(tmp, target). Mirrors what executor.py does.
        target = tmp_path / "out.fastq.gz"
        tmp = atomic_tmp_path(target)
        _write_bytes(tmp, b"reads")

        atomic_move(tmp, target)

        assert target.read_bytes() == b"reads"
        assert not tmp.exists()


class TestAtomicMoveCrossFilesystem:
    def test_falls_back_to_shutil_move_on_exdev(self, tmp_path):
        # Simulate the EXDEV case by patching os.replace to raise the
        # exact errno Path.rename emits across filesystems on macOS.
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        _write_bytes(src, b"payload")

        original_replace = os.replace
        call_count = {"n": 0}

        def fake_replace(a, b):
            call_count["n"] += 1
            if call_count["n"] == 1:
                err = OSError("Cross-device link")
                err.errno = errno.EXDEV
                raise err
            return original_replace(a, b)

        with patch("nanopore_simulator.fastq.os.replace", side_effect=fake_replace):
            atomic_move(src, dst)

        # The fallback (shutil.move) succeeded: file landed at dst,
        # tmp source is gone, and our shim was invoked.
        assert dst.read_bytes() == b"payload"
        assert not src.exists()
        assert call_count["n"] == 1


class TestAtomicMovePropagatesOtherErrors:
    def test_permission_error_is_not_swallowed(self, tmp_path):
        # Errors other than EXDEV must propagate so the caller's
        # try/except cleanup runs (deletes the tmp file).
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        _write_bytes(src, b"payload")

        def raise_permission(a, b):
            err = OSError("Permission denied")
            err.errno = errno.EACCES
            raise err

        with patch("nanopore_simulator.fastq.os.replace", side_effect=raise_permission):
            with pytest.raises(OSError) as exc_info:
                atomic_move(src, dst)
            assert exc_info.value.errno == errno.EACCES

        # Source file unchanged, target never created.
        assert src.read_bytes() == b"payload"
        assert not dst.exists()

    def test_missing_source_propagates_filenotfound(self, tmp_path):
        missing = tmp_path / "does_not_exist.txt"
        dst = tmp_path / "dst.txt"
        with pytest.raises((FileNotFoundError, OSError)):
            atomic_move(missing, dst)
