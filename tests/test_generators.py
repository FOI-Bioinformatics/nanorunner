"""Tests for read generation backends"""

import gzip
import pytest
from pathlib import Path
from unittest.mock import patch

from nanopore_simulator.core.generators import (
    ReadGeneratorConfig,
    GenomeInput,
    BuiltinGenerator,
    BadreadGenerator,
    NanoSimGenerator,
    create_read_generator,
    detect_available_backends,
    parse_fasta,
)


@pytest.fixture
def simple_fasta(tmp_path):
    """Create a simple FASTA file for testing."""
    fasta = tmp_path / "genome.fa"
    fasta.write_text(">chr1\nATCGATCGATCGATCGATCG\n>chr2\nGCTAGCTAGCTAGCTAGCTA\n")
    return fasta


@pytest.fixture
def gzipped_fasta(tmp_path):
    """Create a gzipped FASTA file for testing."""
    fasta = tmp_path / "genome.fa.gz"
    with gzip.open(fasta, "wt") as f:
        f.write(">chr1\nATCGATCGATCG\n")
    return fasta


@pytest.fixture
def default_config():
    return ReadGeneratorConfig(
        num_reads=50,
        mean_read_length=10,
        std_read_length=3,
        min_read_length=5,
        mean_quality=10.0,
        reads_per_file=10,
        output_format="fastq",
    )


class TestReadGeneratorConfig:

    def test_default_values(self):
        config = ReadGeneratorConfig()
        assert config.num_reads == 1000
        assert config.mean_read_length == 5000
        assert config.output_format == "fastq.gz"

    def test_invalid_num_reads(self):
        with pytest.raises(ValueError, match="num_reads"):
            ReadGeneratorConfig(num_reads=0)

    def test_invalid_output_format(self):
        with pytest.raises(ValueError, match="output_format"):
            ReadGeneratorConfig(output_format="bam")

    def test_invalid_mean_quality(self):
        with pytest.raises(ValueError, match="mean_quality"):
            ReadGeneratorConfig(mean_quality=-1)

    def test_invalid_reads_per_file(self):
        with pytest.raises(ValueError, match="reads_per_file"):
            ReadGeneratorConfig(reads_per_file=0)


class TestParseFasta:

    def test_parse_simple(self, simple_fasta):
        seqs = parse_fasta(simple_fasta)
        assert len(seqs) == 2
        assert seqs[0][0] == "chr1"
        assert seqs[0][1] == "ATCGATCGATCGATCGATCG"
        assert seqs[1][0] == "chr2"

    def test_parse_gzipped(self, gzipped_fasta):
        seqs = parse_fasta(gzipped_fasta)
        assert len(seqs) == 1
        assert seqs[0][1] == "ATCGATCGATCG"

    def test_empty_file(self, tmp_path):
        empty = tmp_path / "empty.fa"
        empty.write_text("")
        seqs = parse_fasta(empty)
        assert seqs == []


class TestBuiltinGenerator:

    def test_is_available(self):
        assert BuiltinGenerator.is_available() is True

    def test_generate_reads_fastq(self, simple_fasta, tmp_path, default_config):
        gen = BuiltinGenerator(default_config)
        genome = GenomeInput(fasta_path=simple_fasta)
        output = gen.generate_reads(genome, tmp_path / "out", 0)

        assert output.exists()
        assert output.suffix == ".fastq"

        # Verify FASTQ format
        lines = output.read_text().strip().split("\n")
        assert len(lines) == default_config.reads_per_file * 4
        assert lines[0].startswith("@")
        assert lines[2] == "+"

    def test_generate_reads_gzipped(self, simple_fasta, tmp_path):
        config = ReadGeneratorConfig(
            reads_per_file=5,
            mean_read_length=10,
            std_read_length=2,
            min_read_length=5,
            output_format="fastq.gz",
        )
        gen = BuiltinGenerator(config)
        genome = GenomeInput(fasta_path=simple_fasta)
        output = gen.generate_reads(genome, tmp_path / "out", 1)

        assert output.exists()
        assert output.name.endswith(".fastq.gz")

        with gzip.open(output, "rt") as f:
            content = f.read()
        lines = content.strip().split("\n")
        assert len(lines) == 5 * 4

    def test_empty_genome_raises(self, tmp_path, default_config):
        fasta = tmp_path / "empty.fa"
        fasta.write_text(">chr1\n")
        gen = BuiltinGenerator(default_config)
        genome = GenomeInput(fasta_path=fasta)
        with pytest.raises(ValueError, match="Empty genome"):
            gen.generate_reads(genome, tmp_path / "out", 0)

    def test_no_sequences_raises(self, tmp_path, default_config):
        fasta = tmp_path / "noseq.fa"
        fasta.write_text("")
        gen = BuiltinGenerator(default_config)
        genome = GenomeInput(fasta_path=fasta)
        with pytest.raises(ValueError, match="No sequences found"):
            gen.generate_reads(genome, tmp_path / "out", 0)

    def test_read_lengths_respect_minimum(self, simple_fasta, tmp_path):
        config = ReadGeneratorConfig(
            reads_per_file=20,
            mean_read_length=8,
            std_read_length=5,
            min_read_length=5,
            output_format="fastq",
        )
        gen = BuiltinGenerator(config)
        genome = GenomeInput(fasta_path=simple_fasta)
        output = gen.generate_reads(genome, tmp_path / "out", 0)

        lines = output.read_text().strip().split("\n")
        for i in range(0, len(lines), 4):
            seq = lines[i + 1]
            assert len(seq) >= 5

    def test_zero_std_produces_uniform_length(self, simple_fasta, tmp_path):
        config = ReadGeneratorConfig(
            reads_per_file=5,
            mean_read_length=10,
            std_read_length=0,
            min_read_length=5,
            output_format="fastq",
        )
        gen = BuiltinGenerator(config)
        genome = GenomeInput(fasta_path=simple_fasta)
        output = gen.generate_reads(genome, tmp_path / "out", 0)

        lines = output.read_text().strip().split("\n")
        for i in range(0, len(lines), 4):
            seq = lines[i + 1]
            assert len(seq) == 10


class TestBadreadGenerator:

    def test_is_available_when_missing(self):
        with patch("shutil.which", return_value=None):
            assert BadreadGenerator.is_available() is False

    def test_is_available_when_present(self):
        with patch("shutil.which", return_value="/usr/bin/badread"):
            assert BadreadGenerator.is_available() is True


class TestNanoSimGenerator:

    def test_is_available_when_missing(self):
        with patch("shutil.which", return_value=None):
            assert NanoSimGenerator.is_available() is False


class TestFactory:

    def test_create_builtin(self):
        config = ReadGeneratorConfig()
        gen = create_read_generator("builtin", config)
        assert isinstance(gen, BuiltinGenerator)

    def test_create_auto_selects_builtin(self):
        config = ReadGeneratorConfig()
        with patch.object(BadreadGenerator, "is_available", return_value=False):
            with patch.object(NanoSimGenerator, "is_available", return_value=False):
                gen = create_read_generator("auto", config)
                assert isinstance(gen, BuiltinGenerator)

    def test_create_unknown_backend(self):
        config = ReadGeneratorConfig()
        with pytest.raises(ValueError, match="Unknown backend"):
            create_read_generator("nonexistent", config)

    def test_create_unavailable_backend(self):
        config = ReadGeneratorConfig()
        with patch.object(BadreadGenerator, "is_available", return_value=False):
            with pytest.raises(ValueError, match="not available"):
                create_read_generator("badread", config)


class TestDetectBackends:

    def test_detect_returns_dict(self):
        backends = detect_available_backends()
        assert "builtin" in backends
        assert "badread" in backends
        assert "nanosim" in backends
        assert backends["builtin"] is True


class TestGenomeInput:

    def test_defaults(self, simple_fasta):
        gi = GenomeInput(fasta_path=simple_fasta)
        assert gi.barcode is None

    def test_with_barcode(self, simple_fasta):
        gi = GenomeInput(fasta_path=simple_fasta, barcode="barcode01")
        assert gi.barcode == "barcode01"
