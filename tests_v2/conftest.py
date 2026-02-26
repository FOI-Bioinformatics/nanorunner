"""Shared test fixtures for v2 tests."""

import pytest
from pathlib import Path


@pytest.fixture
def sample_fasta(tmp_path: Path) -> Path:
    """Create a minimal FASTA file."""
    fasta = tmp_path / "genome.fa"
    fasta.write_text(">chr1\nACGTACGTACGTACGT\n>chr2\nTTTTAAAACCCCGGGG\n")
    return fasta


@pytest.fixture
def sample_fastq(tmp_path: Path) -> Path:
    """Create a minimal FASTQ file."""
    fastq = tmp_path / "reads.fastq"
    fastq.write_text(
        "@read1\nACGTACGT\n+\nIIIIIIII\n"
        "@read2\nTTTTAAAA\n+\nIIIIIIII\n"
    )
    return fastq


@pytest.fixture
def source_dir_singleplex(tmp_path: Path) -> Path:
    """Create a singleplex source directory with FASTQ files."""
    source = tmp_path / "source"
    source.mkdir()
    for i in range(5):
        (source / f"reads_{i}.fastq").write_text(
            f"@read{i}\nACGTACGT\n+\nIIIIIIII\n"
        )
    return source


@pytest.fixture
def source_dir_multiplex(tmp_path: Path) -> Path:
    """Create a multiplex source directory with barcode subdirs."""
    source = tmp_path / "source"
    source.mkdir()
    for bc in ["barcode01", "barcode02"]:
        bc_dir = source / bc
        bc_dir.mkdir()
        for i in range(3):
            (bc_dir / f"reads_{i}.fastq").write_text(
                f"@read{i}\nACGTACGT\n+\nIIIIIIII\n"
            )
    return source
