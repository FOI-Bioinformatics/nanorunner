"""Tests for read generation backends"""

import gzip
import pytest
from pathlib import Path
from unittest.mock import patch

from nanopore_simulator.core.config import SimulationConfig
from nanopore_simulator.core.simulator import NanoporeSimulator
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
        mean_quality=20.0,
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


class TestBuiltinGeneratorWarning:

    def test_builtin_generator_warning_logged(self, simple_fasta, tmp_path, caplog):
        """Verify warning is emitted when builtin generator is used."""
        import logging

        config = SimulationConfig(
            target_dir=tmp_path / "output",
            operation="generate",
            genome_inputs=[simple_fasta],
            read_count=10,
            reads_per_file=10,
            mean_read_length=10,
            std_read_length=3,
            min_read_length=5,
            output_format="fastq",
            interval=0.0,
            timing_model="uniform",
            generator_backend="builtin",
        )
        with caplog.at_level(logging.WARNING):
            NanoporeSimulator(config, enable_monitoring=False)
        assert any("error-free" in msg.lower() for msg in caplog.messages)


class TestGenomeCache:

    def test_genome_cache_avoids_reparse(self, simple_fasta, default_config):
        """Cached genome should return same sequence without re-parsing."""
        gen = BuiltinGenerator(default_config)
        genome = GenomeInput(fasta_path=simple_fasta)

        seq1 = gen._get_genome_sequence(genome)
        seq2 = gen._get_genome_sequence(genome)
        assert seq1 is seq2  # Same object from cache

    def test_genome_cache_resolves_symlinks(self, simple_fasta, tmp_path, default_config):
        """Cache should identify symlinks to the same file."""
        link = tmp_path / "link.fa"
        link.symlink_to(simple_fasta)

        gen = BuiltinGenerator(default_config)
        g1 = GenomeInput(fasta_path=simple_fasta)
        g2 = GenomeInput(fasta_path=link)

        seq1 = gen._get_genome_sequence(g1)
        seq2 = gen._get_genome_sequence(g2)
        assert seq1 is seq2


class TestReverseComplement:

    def test_basic_complement(self):
        """Verify reverse complement with known input."""
        config = ReadGeneratorConfig()
        assert BuiltinGenerator._reverse_complement("ATCG") == "CGAT"

    def test_handles_lowercase(self):
        """Translation table should handle lowercase bases."""
        assert BuiltinGenerator._reverse_complement("atcg") == "cgat"

    def test_handles_n(self):
        """N bases should complement to N."""
        assert BuiltinGenerator._reverse_complement("ANA") == "TNT"


class TestQualityDistribution:

    def test_quality_values_in_phred_range(self, simple_fasta, tmp_path):
        """All quality characters should be in Phred+33 range [33, 73]."""
        config = ReadGeneratorConfig(
            reads_per_file=50,
            mean_read_length=15,
            std_read_length=2,
            min_read_length=5,
            mean_quality=20.0,
            std_quality=5.0,
            output_format="fastq",
        )
        gen = BuiltinGenerator(config)
        genome = GenomeInput(fasta_path=simple_fasta)
        output = gen.generate_reads(genome, tmp_path / "out", 0)

        lines = output.read_text().strip().split("\n")
        for i in range(3, len(lines), 4):
            qual_line = lines[i]
            for ch in qual_line:
                assert 33 <= ord(ch) <= 73, f"Quality char {ch!r} out of range"


class TestQualityDefaults:

    def test_config_default_mean_quality(self):
        """Default mean_quality should be 20.0 (R10.4.1 + SUP)."""
        config = ReadGeneratorConfig()
        assert config.mean_quality == 20.0

    def test_config_default_std_quality(self):
        """Default std_quality should be 4.0."""
        config = ReadGeneratorConfig()
        assert config.std_quality == 4.0

    def test_simulation_config_default_mean_quality(self, simple_fasta, tmp_path):
        """SimulationConfig default mean_quality should be 20.0."""
        config = SimulationConfig(
            target_dir=tmp_path,
            operation="generate",
            genome_inputs=[simple_fasta],
        )
        assert config.mean_quality == 20.0

    def test_simulation_config_default_std_quality(self, simple_fasta, tmp_path):
        """SimulationConfig default std_quality should be 4.0."""
        config = SimulationConfig(
            target_dir=tmp_path,
            operation="generate",
            genome_inputs=[simple_fasta],
        )
        assert config.std_quality == 4.0
