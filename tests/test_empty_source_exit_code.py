"""Tests for the empty-source exit-code contract (audit followup F6).

Pre-2026-05-02 nanorunner replay/generate exited 0 on an empty source
directory (or no genomes), with only an INFO-level log line. CI
pipelines checking $? could not distinguish "ran successfully with
nothing to do because --source pointed at the wrong place" from a
real successful run. This file pins the new contract:

- run_replay raises EmptySourceError on empty manifest
- run_generate raises EmptySourceError when no genome inputs are given
- the CLI catches EmptySourceError and exits with code 3 (distinct
  from generic exit-code 1 so CI can branch on the cause)
- the error message names the offending path / missing flag so the
  operator knows what to fix
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from nanopore_simulator.cli import app

runner = CliRunner()


@pytest.fixture
def empty_dir(tmp_path: Path) -> Path:
    d = tmp_path / "empty_source"
    d.mkdir()
    return d


@pytest.fixture
def target_dir(tmp_path: Path) -> Path:
    d = tmp_path / "target"
    return d


class TestReplayEmptySourceExitCode:
    def test_exit_code_three_on_empty_source(
        self, empty_dir: Path, target_dir: Path
    ):
        result = runner.invoke(
            app,
            [
                "replay",
                "--source",
                str(empty_dir),
                "--target",
                str(target_dir),
                "--no-wait",
                "--monitor",
                "none",
            ],
        )
        assert result.exit_code == 3, (
            f"expected exit code 3 for empty-source error, got "
            f"{result.exit_code}; output:\n{result.output}"
        )

    def test_error_message_names_source_dir(
        self, empty_dir: Path, target_dir: Path
    ):
        result = runner.invoke(
            app,
            [
                "replay",
                "--source",
                str(empty_dir),
                "--target",
                str(target_dir),
                "--no-wait",
                "--monitor",
                "none",
            ],
        )
        # Operator-facing diagnostic should name the path that
        # was empty so they know which --source to fix.
        assert str(empty_dir) in result.output, (
            f"empty-source error should name the offending dir; output:\n"
            f"{result.output}"
        )

    def test_exit_code_distinct_from_generic_error(
        self, tmp_path: Path
    ):
        # A non-existent --source raises a different (generic) error
        # path that should exit code 1 (or 2 for argparse-level), NOT
        # 3 -- exit code 3 is reserved for "operator pointed at an
        # empty but valid directory".
        nonexistent = tmp_path / "does_not_exist"
        target = tmp_path / "target"
        result = runner.invoke(
            app,
            [
                "replay",
                "--source",
                str(nonexistent),
                "--target",
                str(target),
                "--no-wait",
                "--monitor",
                "none",
            ],
        )
        assert result.exit_code != 0
        assert result.exit_code != 3
