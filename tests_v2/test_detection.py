"""Tests for input directory structure detection."""

import pytest
from pathlib import Path
from nanopore_simulator_v2.detection import (
    detect_structure,
    find_sequencing_files,
    find_barcode_dirs,
    is_barcode_dir,
)


class TestDetectStructure:
    def test_singleplex(self, source_dir_singleplex):
        assert detect_structure(source_dir_singleplex) == "singleplex"

    def test_multiplex(self, source_dir_multiplex):
        assert detect_structure(source_dir_multiplex) == "multiplex"

    def test_empty_raises(self, tmp_path):
        source = tmp_path / "empty"
        source.mkdir()
        with pytest.raises(ValueError, match="No sequencing files"):
            detect_structure(source)

    def test_mixed_prefers_multiplex(self, tmp_path):
        """When files exist in both root and barcode dirs, prefer multiplex."""
        source = tmp_path / "source"
        source.mkdir()
        # Files in root
        (source / "reads.fastq").write_text("@r1\nACGT\n+\nIIII\n")
        # Files in barcode dir
        bc = source / "barcode01"
        bc.mkdir()
        (bc / "reads.fastq").write_text("@r1\nACGT\n+\nIIII\n")
        assert detect_structure(source) == "multiplex"

    def test_gz_files_detected(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        (source / "reads.fastq.gz").write_bytes(b"")
        assert detect_structure(source) == "singleplex"

    def test_pod5_files_detected(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        (source / "reads.pod5").write_bytes(b"")
        assert detect_structure(source) == "singleplex"


class TestFindSequencingFiles:
    def test_finds_fastq(self, source_dir_singleplex):
        files = find_sequencing_files(source_dir_singleplex)
        assert len(files) == 5
        assert all(f.suffix == ".fastq" for f in files)

    def test_finds_in_barcode_dirs(self, source_dir_multiplex):
        files = find_sequencing_files(source_dir_multiplex / "barcode01")
        assert len(files) == 3

    def test_nonexistent_dir_returns_empty(self, tmp_path):
        files = find_sequencing_files(tmp_path / "nonexistent")
        assert files == []

    def test_ignores_non_sequencing_files(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        (source / "readme.txt").write_text("not a sequencing file")
        (source / "data.csv").write_text("a,b,c")
        (source / "reads.fastq").write_text("@r\nA\n+\nI\n")
        files = find_sequencing_files(source)
        assert len(files) == 1

    def test_finds_fq_extension(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        (source / "reads.fq").write_text("@r\nA\n+\nI\n")
        files = find_sequencing_files(source)
        assert len(files) == 1

    def test_finds_fq_gz_extension(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        (source / "reads.fq.gz").write_bytes(b"")
        files = find_sequencing_files(source)
        assert len(files) == 1


class TestFindBarcodeDirs:
    def test_finds_barcode_dirs(self, source_dir_multiplex):
        dirs = find_barcode_dirs(source_dir_multiplex)
        assert len(dirs) == 2
        names = {d.name for d in dirs}
        assert "barcode01" in names
        assert "barcode02" in names

    def test_no_barcode_dirs(self, source_dir_singleplex):
        dirs = find_barcode_dirs(source_dir_singleplex)
        assert len(dirs) == 0

    def test_ignores_empty_barcode_dirs(self, tmp_path):
        """Barcode dirs without sequencing files should be ignored."""
        source = tmp_path / "source"
        source.mkdir()
        bc = source / "barcode01"
        bc.mkdir()
        # No sequencing files in the barcode dir
        (bc / "readme.txt").write_text("not a sequencing file")
        dirs = find_barcode_dirs(source)
        assert len(dirs) == 0

    def test_unclassified_dir(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        uc = source / "unclassified"
        uc.mkdir()
        (uc / "reads.fastq").write_text("@r\nA\n+\nI\n")
        dirs = find_barcode_dirs(source)
        assert len(dirs) == 1
        assert dirs[0].name == "unclassified"


class TestIsBarcodeDir:
    def test_standard_barcode(self):
        assert is_barcode_dir("barcode01") is True
        assert is_barcode_dir("barcode99") is True

    def test_bc_prefix(self):
        assert is_barcode_dir("BC01") is True
        assert is_barcode_dir("bc01") is True

    def test_unclassified(self):
        assert is_barcode_dir("unclassified") is True

    def test_not_barcode(self):
        assert is_barcode_dir("sample01") is False
        assert is_barcode_dir("data") is False

    def test_case_insensitive(self):
        assert is_barcode_dir("BARCODE01") is True
        assert is_barcode_dir("Barcode01") is True
