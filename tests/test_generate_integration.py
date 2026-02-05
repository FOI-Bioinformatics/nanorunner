"""Integration tests for read generation mode"""

import gzip
import pytest
from pathlib import Path

from nanopore_simulator.core.config import SimulationConfig
from nanopore_simulator.core.simulator import NanoporeSimulator


@pytest.fixture
def genome_files(tmp_path):
    """Create two small genome FASTA files."""
    g1 = tmp_path / "genome1.fa"
    g1.write_text(">chr1\n" + "ATCGATCG" * 50 + "\n>chr2\n" + "GCTAGCTA" * 50 + "\n")
    g2 = tmp_path / "genome2.fa"
    g2.write_text(">chrA\n" + "TTAACCGG" * 50 + "\n")
    return [g1, g2]


class TestGenerateMultiplex:

    def test_multiplex_creates_barcode_dirs(self, genome_files, tmp_path):
        target = tmp_path / "output"
        config = SimulationConfig(
            target_dir=target,
            operation="generate",
            genome_inputs=genome_files,
            read_count=50,
            reads_per_file=25,
            mean_read_length=20,
            std_read_length=5,
            min_read_length=10,
            output_format="fastq",
            interval=0.0,
            timing_model="uniform",
        )
        sim = NanoporeSimulator(config, enable_monitoring=False)
        sim.run_simulation()

        assert (target / "barcode01").is_dir()
        assert (target / "barcode02").is_dir()

        # Each genome: ceil(50/25) = 2 files
        b1_files = list((target / "barcode01").glob("*.fastq"))
        b2_files = list((target / "barcode02").glob("*.fastq"))
        assert len(b1_files) == 2
        assert len(b2_files) == 2

        # Verify FASTQ content
        for fq in b1_files:
            lines = fq.read_text().strip().split("\n")
            assert len(lines) == 25 * 4

    def test_multiplex_gzipped(self, genome_files, tmp_path):
        target = tmp_path / "output"
        config = SimulationConfig(
            target_dir=target,
            operation="generate",
            genome_inputs=genome_files,
            read_count=20,
            reads_per_file=20,
            mean_read_length=15,
            std_read_length=3,
            min_read_length=8,
            output_format="fastq.gz",
            interval=0.0,
            timing_model="uniform",
        )
        sim = NanoporeSimulator(config, enable_monitoring=False)
        sim.run_simulation()

        gz_files = list((target / "barcode01").glob("*.fastq.gz"))
        assert len(gz_files) >= 1

        with gzip.open(gz_files[0], "rt") as f:
            content = f.read()
        lines = content.strip().split("\n")
        assert lines[0].startswith("@")


class TestGenerateSingleplex:

    def test_singleplex_separate(self, genome_files, tmp_path):
        target = tmp_path / "output"
        config = SimulationConfig(
            target_dir=target,
            operation="generate",
            genome_inputs=genome_files,
            force_structure="singleplex",
            read_count=30,
            reads_per_file=15,
            mean_read_length=20,
            std_read_length=5,
            min_read_length=10,
            output_format="fastq",
            mix_reads=False,
            interval=0.0,
            timing_model="uniform",
        )
        sim = NanoporeSimulator(config, enable_monitoring=False)
        sim.run_simulation()

        # Files should be in target root, not in barcode dirs
        fq_files = list(target.glob("*.fastq"))
        # 2 genomes * ceil(30/15) = 4 files
        assert len(fq_files) == 4

    def test_singleplex_mixed(self, genome_files, tmp_path):
        target = tmp_path / "output"
        config = SimulationConfig(
            target_dir=target,
            operation="generate",
            genome_inputs=genome_files,
            force_structure="singleplex",
            read_count=20,
            reads_per_file=10,
            mean_read_length=20,
            std_read_length=5,
            min_read_length=10,
            output_format="fastq",
            mix_reads=True,
            interval=0.0,
            timing_model="uniform",
        )
        sim = NanoporeSimulator(config, enable_monitoring=False)
        sim.run_simulation()

        fq_files = list(target.glob("*.fastq"))
        # 2 genomes * ceil(20/10) = 4 total files
        assert len(fq_files) == 4


class TestGenerateWithTiming:

    def test_generate_with_poisson_timing(self, genome_files, tmp_path):
        """Verify generation works with non-uniform timing models."""
        target = tmp_path / "output"
        config = SimulationConfig(
            target_dir=target,
            operation="generate",
            genome_inputs=genome_files,
            read_count=10,
            reads_per_file=10,
            mean_read_length=15,
            std_read_length=3,
            min_read_length=8,
            output_format="fastq",
            interval=0.01,
            timing_model="poisson",
            timing_model_params={
                "burst_probability": 0.1,
                "burst_rate_multiplier": 2.0,
            },
        )
        sim = NanoporeSimulator(config, enable_monitoring=False)
        sim.run_simulation()

        # Should still produce output
        all_fq = list(target.rglob("*.fastq"))
        assert len(all_fq) >= 2


class TestGenerateConfigValidation:

    def test_missing_genome_inputs(self, tmp_path):
        with pytest.raises(ValueError, match="genome_inputs"):
            SimulationConfig(
                target_dir=tmp_path,
                operation="generate",
            )

    def test_nonexistent_genome(self, tmp_path):
        with pytest.raises(ValueError, match="does not exist"):
            SimulationConfig(
                target_dir=tmp_path,
                operation="generate",
                genome_inputs=[tmp_path / "nonexistent.fa"],
            )

    def test_invalid_output_format(self, genome_files, tmp_path):
        with pytest.raises(ValueError, match="output_format"):
            SimulationConfig(
                target_dir=tmp_path,
                operation="generate",
                genome_inputs=genome_files,
                output_format="bam",
            )
