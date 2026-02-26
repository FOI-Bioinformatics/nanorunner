"""Tests for simplified pipeline validation."""

import pytest
from pathlib import Path

from nanopore_simulator_v2.adapters import (
    ADAPTERS,
    validate_output,
    list_adapters,
    get_adapter_info,
)


class TestAdaptersRegistry:
    """Validate the ADAPTERS data dict."""

    def test_nanometa_present(self) -> None:
        assert "nanometa" in ADAPTERS

    def test_kraken_present(self) -> None:
        assert "kraken" in ADAPTERS

    def test_nanometa_has_description(self) -> None:
        assert "description" in ADAPTERS["nanometa"]
        assert len(ADAPTERS["nanometa"]["description"]) > 0

    def test_nanometa_has_patterns(self) -> None:
        patterns = ADAPTERS["nanometa"]["patterns"]
        assert "*.fastq" in patterns
        assert "*.fastq.gz" in patterns
        assert "*.pod5" in patterns

    def test_kraken_has_patterns(self) -> None:
        patterns = ADAPTERS["kraken"]["patterns"]
        assert "*.fastq" in patterns
        assert "*.fastq.gz" in patterns

    def test_kraken_no_pod5(self) -> None:
        """Kraken does not accept POD5 files."""
        patterns = ADAPTERS["kraken"]["patterns"]
        assert "*.pod5" not in patterns


class TestValidateOutput:
    """Validate output directory checking for pipeline adapters."""

    def test_valid_nanometa_multiplex(self, tmp_path: Path) -> None:
        """Nanometa accepts multiplex structure with fastq files."""
        bc = tmp_path / "barcode01"
        bc.mkdir()
        (bc / "reads.fastq").write_text("@r1\nACGT\n+\nIIII\n")
        issues = validate_output(tmp_path, "nanometa")
        assert issues == []

    def test_valid_nanometa_singleplex(self, tmp_path: Path) -> None:
        """Nanometa accepts flat directory with matching files."""
        (tmp_path / "reads.fastq.gz").write_text("")
        issues = validate_output(tmp_path, "nanometa")
        assert issues == []

    def test_empty_dir_has_issues(self, tmp_path: Path) -> None:
        """Empty directory should produce at least one issue."""
        issues = validate_output(tmp_path, "nanometa")
        assert len(issues) > 0

    def test_unknown_adapter_raises(self, tmp_path: Path) -> None:
        with pytest.raises(KeyError):
            validate_output(tmp_path, "nonexistent_pipeline")

    def test_kraken_accepts_flat_fastq(self, tmp_path: Path) -> None:
        """Kraken should accept flat FASTQ files."""
        (tmp_path / "data.fastq").write_text("@r1\nACGT\n+\nIIII\n")
        issues = validate_output(tmp_path, "kraken")
        assert issues == []

    def test_kraken_accepts_multiplex(self, tmp_path: Path) -> None:
        bc = tmp_path / "barcode02"
        bc.mkdir()
        (bc / "reads.fq.gz").write_text("")
        issues = validate_output(tmp_path, "kraken")
        assert issues == []

    def test_nanometa_alias_nanometanf(self, tmp_path: Path) -> None:
        """The nanometanf alias should resolve to nanometa."""
        (tmp_path / "reads.fastq").write_text("@r1\nACGT\n+\nIIII\n")
        issues = validate_output(tmp_path, "nanometanf")
        assert issues == []

    def test_nonexistent_dir(self) -> None:
        """Non-existent directory should produce issues."""
        issues = validate_output(Path("/tmp/does_not_exist_xyz"), "nanometa")
        assert len(issues) > 0

    def test_pod5_accepted_by_nanometa(self, tmp_path: Path) -> None:
        (tmp_path / "data.pod5").write_text("")
        issues = validate_output(tmp_path, "nanometa")
        assert issues == []

    def test_wrong_extensions_flagged(self, tmp_path: Path) -> None:
        """Files that do not match any pattern should produce issues."""
        (tmp_path / "data.txt").write_text("not sequencing data")
        issues = validate_output(tmp_path, "nanometa")
        assert len(issues) > 0


class TestListAdapters:
    """Validate list_adapters returns adapter names and descriptions."""

    def test_returns_dict(self) -> None:
        result = list_adapters()
        assert isinstance(result, dict)

    def test_contains_nanometa(self) -> None:
        assert "nanometa" in list_adapters()

    def test_contains_kraken(self) -> None:
        assert "kraken" in list_adapters()

    def test_values_are_descriptions(self) -> None:
        result = list_adapters()
        for name, desc in result.items():
            assert isinstance(desc, str)
            assert len(desc) > 0


class TestGetAdapterInfo:
    """Validate get_adapter_info returns full adapter configuration."""

    def test_known_adapter(self) -> None:
        info = get_adapter_info("nanometa")
        assert "name" in info
        assert "description" in info
        assert "patterns" in info
        assert info["name"] == "nanometa"

    def test_unknown_adapter_raises(self) -> None:
        with pytest.raises(KeyError):
            get_adapter_info("does_not_exist")

    def test_alias_resolves(self) -> None:
        info = get_adapter_info("nanometanf")
        assert info["name"] == "nanometa"

    def test_kraken_info(self) -> None:
        info = get_adapter_info("kraken")
        assert info["name"] == "kraken"
        assert "*.fastq" in info["patterns"]
