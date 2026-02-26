"""Tests for file executor (do phase)."""

from pathlib import Path

import pytest

from nanopore_simulator.executor import execute_entry
from nanopore_simulator.generators import (
    BuiltinGenerator,
    GeneratorConfig,
    GenomeInput,
)
from nanopore_simulator.manifest import FileEntry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def source_file(tmp_path: Path) -> Path:
    """Create a source FASTQ file."""
    f = tmp_path / "source" / "reads.fastq"
    f.parent.mkdir(parents=True)
    f.write_text("@read1\nACGTACGT\n+\nIIIIIIII\n")
    return f


@pytest.fixture
def simple_fasta(tmp_path: Path) -> Path:
    """Create a genome FASTA for generation tests."""
    fasta = tmp_path / "genome.fa"
    fasta.write_text(
        ">chr1\nACGTACGTACGTACGTACGTACGTACGTACGT\n"
        ">chr2\nTTTTAAAACCCCGGGGTTTTAAAACCCCGGGG\n"
    )
    return fasta


@pytest.fixture
def builtin_generator() -> BuiltinGenerator:
    """Create a BuiltinGenerator with small reads for testing."""
    config = GeneratorConfig(
        num_reads=50,
        mean_read_length=10,
        std_read_length=3,
        min_read_length=5,
        mean_quality=20.0,
        reads_per_file=10,
        output_format="fastq",
    )
    return BuiltinGenerator(config)


# ---------------------------------------------------------------------------
# Copy operation
# ---------------------------------------------------------------------------


class TestCopyOperation:
    """Tests for copy file execution."""

    def test_copy_preserves_content(
        self, source_file: Path, tmp_path: Path
    ) -> None:
        target = tmp_path / "target" / "reads.fastq"
        entry = FileEntry(
            source=source_file,
            target=target,
            operation="copy",
        )
        result = execute_entry(entry)
        assert result == target
        assert target.exists()
        assert target.read_text() == source_file.read_text()

    def test_copy_creates_parent_dirs(
        self, source_file: Path, tmp_path: Path
    ) -> None:
        target = tmp_path / "deep" / "nested" / "dir" / "reads.fastq"
        entry = FileEntry(
            source=source_file,
            target=target,
            operation="copy",
        )
        result = execute_entry(entry)
        assert target.exists()
        assert result.parent.exists()

    def test_copy_source_missing_raises(self, tmp_path: Path) -> None:
        entry = FileEntry(
            source=tmp_path / "nonexistent.fastq",
            target=tmp_path / "target" / "reads.fastq",
            operation="copy",
        )
        with pytest.raises(FileNotFoundError, match="Source file not found"):
            execute_entry(entry)


# ---------------------------------------------------------------------------
# Link operation
# ---------------------------------------------------------------------------


class TestLinkOperation:
    """Tests for symlink file execution."""

    def test_link_creates_symlink(
        self, source_file: Path, tmp_path: Path
    ) -> None:
        target = tmp_path / "target" / "reads.fastq"
        entry = FileEntry(
            source=source_file,
            target=target,
            operation="link",
        )
        result = execute_entry(entry)
        assert result == target
        assert target.is_symlink()

    def test_link_resolves_to_source(
        self, source_file: Path, tmp_path: Path
    ) -> None:
        target = tmp_path / "target" / "reads.fastq"
        entry = FileEntry(
            source=source_file,
            target=target,
            operation="link",
        )
        execute_entry(entry)
        assert target.read_text() == source_file.read_text()

    def test_link_source_missing_raises(self, tmp_path: Path) -> None:
        entry = FileEntry(
            source=tmp_path / "nonexistent.fastq",
            target=tmp_path / "target" / "reads.fastq",
            operation="link",
        )
        with pytest.raises(FileNotFoundError, match="Source file not found"):
            execute_entry(entry)


# ---------------------------------------------------------------------------
# Generate operation
# ---------------------------------------------------------------------------


class TestGenerateOperation:
    """Tests for generate file execution."""

    def test_generate_produces_file(
        self,
        simple_fasta: Path,
        builtin_generator: BuiltinGenerator,
        tmp_path: Path,
    ) -> None:
        target_dir = tmp_path / "target"
        # Target filename matches generator naming convention
        entry = FileEntry(
            target=target_dir / "genome_reads_0000.fastq",
            operation="generate",
            genome=simple_fasta,
            read_count=5,
            file_index=0,
        )
        result = execute_entry(entry, generator=builtin_generator)
        assert result.exists()
        assert result.stat().st_size > 0

    def test_generate_without_generator_raises(
        self, simple_fasta: Path, tmp_path: Path
    ) -> None:
        entry = FileEntry(
            target=tmp_path / "target" / "reads.fastq",
            operation="generate",
            genome=simple_fasta,
            read_count=5,
        )
        with pytest.raises(ValueError, match="generator required"):
            execute_entry(entry)

    def test_generate_creates_parent_dirs(
        self,
        simple_fasta: Path,
        builtin_generator: BuiltinGenerator,
        tmp_path: Path,
    ) -> None:
        target_dir = tmp_path / "deep" / "nested"
        entry = FileEntry(
            target=target_dir / "genome_reads_0000.fastq",
            operation="generate",
            genome=simple_fasta,
            read_count=3,
            file_index=0,
        )
        result = execute_entry(entry, generator=builtin_generator)
        assert result.exists()
        assert result.parent.exists()


# ---------------------------------------------------------------------------
# Unknown operation
# ---------------------------------------------------------------------------


class TestUnknownOperation:
    """Tests for unrecognized operation types."""

    def test_unknown_operation_raises(self, tmp_path: Path) -> None:
        entry = FileEntry(
            target=tmp_path / "output.txt",
            operation="foobar",
        )
        with pytest.raises(ValueError, match="Unknown operation"):
            execute_entry(entry)
