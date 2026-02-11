"""Integration tests for read generation mode"""

import gzip
import math
import pytest
from pathlib import Path

from nanopore_simulator.cli.main import _expand_genome_paths, _GENOME_EXTENSIONS
from nanopore_simulator.core.config import SimulationConfig
from nanopore_simulator.core.simulator import NanoporeSimulator, _distribute_reads


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
            read_count=100,
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

        # Total 100 reads split equally: 50 each, ceil(50/25) = 2 files per genome
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
            read_count=40,
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
        # 30 total reads split across 2 genomes: 15 each, ceil(15/15) = 1 file per genome = 2 files
        assert len(fq_files) == 2

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
        # 20 total reads, ceil(20/10) = 2 total mixed files
        assert len(fq_files) == 2


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


class TestDistributeReads:
    """Tests for the _distribute_reads helper function."""

    def test_preserves_total(self):
        """Sum of distributed reads must equal total_reads."""
        for total in [10, 100, 1000, 9999]:
            abundances = [0.5, 0.3, 0.2]
            result = _distribute_reads(total, abundances)
            assert sum(result) == total

    def test_minimum_one_for_nonzero(self):
        """Each organism with abundance > 0 gets at least 1 read."""
        result = _distribute_reads(10, [0.999, 0.001])
        assert result[0] >= 1
        assert result[1] >= 1

    def test_handles_zero_abundance(self):
        """Organism with abundance == 0.0 may receive 0 reads."""
        result = _distribute_reads(100, [0.5, 0.0, 0.5])
        assert result[1] == 0
        assert sum(result) == 100

    def test_single_genome(self):
        """Single genome receives all reads."""
        result = _distribute_reads(500, [1.0])
        assert result == [500]

    def test_equal_abundances(self):
        """Equal abundances produce equal (or near-equal) distribution."""
        result = _distribute_reads(100, [0.25, 0.25, 0.25, 0.25])
        assert all(r == 25 for r in result)

    def test_empty_list(self):
        """Empty abundances returns empty list."""
        assert _distribute_reads(100, []) == []

    def test_extreme_range(self):
        """Extreme abundance range still preserves total and minimum."""
        result = _distribute_reads(1000, [0.999, 0.001])
        assert sum(result) == 1000
        assert result[1] >= 1


class TestAbundanceWeightedGeneration:
    """Tests for abundance-weighted read distribution in generate mode."""

    def test_multiplex_abundance_weighted_file_counts(self, genome_files, tmp_path):
        """High-abundance genome should produce more files than low-abundance."""
        target = tmp_path / "output"
        config = SimulationConfig(
            target_dir=target,
            operation="generate",
            genome_inputs=genome_files,
            read_count=200,
            reads_per_file=10,
            mean_read_length=20,
            std_read_length=5,
            min_read_length=10,
            output_format="fastq",
            interval=0.0,
            timing_model="uniform",
        )
        # Set abundances: genome1 gets 90%, genome2 gets 10%
        object.__setattr__(config, "_resolved_abundances", [0.9, 0.1])
        sim = NanoporeSimulator(config, enable_monitoring=False)
        sim.run_simulation()

        b1_files = list((target / "barcode01").glob("*.fastq"))
        b2_files = list((target / "barcode02").glob("*.fastq"))
        # 90% of 200 = 180 reads -> ceil(180/10) = 18 files
        # 10% of 200 = 20 reads -> ceil(20/10) = 2 files
        assert len(b1_files) == 18
        assert len(b2_files) == 2

    def test_even_abundance_produces_equal_files(self, tmp_path):
        """Three genomes at 1/3 each should produce equal file counts."""
        genomes = []
        for i in range(3):
            g = tmp_path / f"genome_{i}.fa"
            g.write_text(f">chr{i}\n" + "ATCGATCG" * 50 + "\n")
            genomes.append(g)

        target = tmp_path / "output"
        config = SimulationConfig(
            target_dir=target,
            operation="generate",
            genome_inputs=genomes,
            read_count=300,
            reads_per_file=10,
            mean_read_length=20,
            std_read_length=5,
            min_read_length=10,
            output_format="fastq",
            interval=0.0,
            timing_model="uniform",
        )
        object.__setattr__(config, "_resolved_abundances", [1 / 3, 1 / 3, 1 / 3])
        sim = NanoporeSimulator(config, enable_monitoring=False)
        sim.run_simulation()

        for i in range(1, 4):
            files = list((target / f"barcode{i:02d}").glob("*.fastq"))
            assert len(files) == 10  # 100 reads / 10 per file

    def test_extreme_abundance_minimum_one_read(self, genome_files, tmp_path):
        """Rare organism with abundance 0.001 still gets at least 1 read."""
        target = tmp_path / "output"
        config = SimulationConfig(
            target_dir=target,
            operation="generate",
            genome_inputs=genome_files,
            read_count=100,
            reads_per_file=10,
            mean_read_length=20,
            std_read_length=5,
            min_read_length=10,
            output_format="fastq",
            interval=0.0,
            timing_model="uniform",
        )
        object.__setattr__(config, "_resolved_abundances", [0.999, 0.001])
        sim = NanoporeSimulator(config, enable_monitoring=False)
        sim.run_simulation()

        # Rare organism should still get at least 1 file
        b2_files = list((target / "barcode02").glob("*.fastq"))
        assert len(b2_files) >= 1

    def test_no_abundance_equal_distribution(self, genome_files, tmp_path):
        """Direct --genomes without abundances should split equally."""
        target = tmp_path / "output"
        config = SimulationConfig(
            target_dir=target,
            operation="generate",
            genome_inputs=genome_files,
            read_count=100,
            reads_per_file=10,
            mean_read_length=20,
            std_read_length=5,
            min_read_length=10,
            output_format="fastq",
            interval=0.0,
            timing_model="uniform",
        )
        sim = NanoporeSimulator(config, enable_monitoring=False)
        sim.run_simulation()

        b1_files = list((target / "barcode01").glob("*.fastq"))
        b2_files = list((target / "barcode02").glob("*.fastq"))
        # 50 reads each, ceil(50/10) = 5 files each
        assert len(b1_files) == 5
        assert len(b2_files) == 5

    def test_singleplex_mixed_weighted_selection(self, genome_files, tmp_path):
        """Singleplex mixed mode should use weighted genome selection."""
        target = tmp_path / "output"
        config = SimulationConfig(
            target_dir=target,
            operation="generate",
            genome_inputs=genome_files,
            force_structure="singleplex",
            read_count=100,
            reads_per_file=10,
            mean_read_length=20,
            std_read_length=5,
            min_read_length=10,
            output_format="fastq",
            mix_reads=True,
            interval=0.0,
            timing_model="uniform",
        )
        object.__setattr__(config, "_resolved_abundances", [0.9, 0.1])
        sim = NanoporeSimulator(config, enable_monitoring=False)
        sim.run_simulation()

        fq_files = list(target.glob("*.fastq"))
        # ceil(100/10) = 10 total mixed files
        assert len(fq_files) == 10


class TestAbundanceFallback:
    """Verify that config.abundances is used when _resolved_abundances is absent.

    The download command resolves species externally and passes abundances
    directly via SimulationConfig.abundances rather than through species
    resolution. The manifest must honour those abundances.
    """

    def test_config_abundances_used_without_resolved(self, tmp_path):
        """abundances on config should be used when _resolved_abundances is not set."""
        genomes = []
        for i in range(2):
            g = tmp_path / f"genome_{i}.fa"
            g.write_text(f">chr{i}\n" + "ATCGATCG" * 50 + "\n")
            genomes.append(g)

        target = tmp_path / "output"
        config = SimulationConfig(
            target_dir=target,
            operation="generate",
            genome_inputs=genomes,
            read_count=200,
            reads_per_file=10,
            mean_read_length=20,
            std_read_length=5,
            min_read_length=10,
            output_format="fastq",
            interval=0.0,
            timing_model="uniform",
            abundances=[0.9, 0.1],
        )
        # Do NOT set _resolved_abundances — mirrors the download command path
        sim = NanoporeSimulator(config, enable_monitoring=False)
        sim.run_simulation()

        b1_files = list((target / "barcode01").glob("*.fastq"))
        b2_files = list((target / "barcode02").glob("*.fastq"))
        # 90% of 200 = 180 reads -> ceil(180/10) = 18 files
        # 10% of 200 = 20 reads -> ceil(20/10) = 2 files
        assert len(b1_files) == 18
        assert len(b2_files) == 2


class TestExpandGenomePaths:
    """Tests for _expand_genome_paths: directory expansion and extension support."""

    def test_plain_files_pass_through(self, tmp_path):
        """Individual FASTA files are returned unchanged."""
        g1 = tmp_path / "a.fa"
        g1.write_text(">seq\nATCG\n")
        g2 = tmp_path / "b.fasta"
        g2.write_text(">seq\nATCG\n")
        result = _expand_genome_paths([g1, g2])
        assert result == [g1, g2]

    def test_directory_expanded(self, tmp_path):
        """A directory is expanded to its genome files."""
        genome_dir = tmp_path / "genomes"
        genome_dir.mkdir()
        (genome_dir / "g1.fa").write_text(">s\nATCG\n")
        (genome_dir / "g2.fasta.gz").write_bytes(b"")
        (genome_dir / "notes.txt").write_text("ignore me")
        result = _expand_genome_paths([genome_dir])
        assert len(result) == 2
        names = {p.name for p in result}
        assert names == {"g1.fa", "g2.fasta.gz"}

    def test_fna_extensions_recognised(self, tmp_path):
        """Files with .fna and .fna.gz extensions are discovered."""
        genome_dir = tmp_path / "ncbi"
        genome_dir.mkdir()
        (genome_dir / "GCF_000005845.2.fna.gz").write_bytes(b"")
        (genome_dir / "GCF_000006745.1.fna.gz").write_bytes(b"")
        (genome_dir / "GCF_000009045.1.fna").write_text(">s\nATCG\n")
        result = _expand_genome_paths([genome_dir])
        assert len(result) == 3

    def test_mixed_files_and_dirs(self, tmp_path):
        """A mix of individual files and directories is handled."""
        single = tmp_path / "single.fa"
        single.write_text(">s\nATCG\n")
        genome_dir = tmp_path / "batch"
        genome_dir.mkdir()
        (genome_dir / "a.fasta").write_text(">s\nATCG\n")
        (genome_dir / "b.fna.gz").write_bytes(b"")
        result = _expand_genome_paths([single, genome_dir])
        assert len(result) == 3
        assert result[0] == single

    def test_nonexistent_path_raises(self, tmp_path):
        """A non-existent path produces an exit error."""
        from click.exceptions import Exit
        with pytest.raises(Exit):
            _expand_genome_paths([tmp_path / "missing.fa"])

    def test_empty_directory_raises(self, tmp_path):
        """A directory with no genome files produces an exit error."""
        empty = tmp_path / "empty"
        empty.mkdir()
        from click.exceptions import Exit
        with pytest.raises(Exit):
            _expand_genome_paths([empty])

    def test_directory_with_only_non_genome_files_raises(self, tmp_path):
        """A directory containing only non-genome files produces an error."""
        d = tmp_path / "txt_only"
        d.mkdir()
        (d / "readme.txt").write_text("hello")
        (d / "data.csv").write_text("a,b")
        from click.exceptions import Exit
        with pytest.raises(Exit):
            _expand_genome_paths([d])

    def test_all_supported_extensions(self, tmp_path):
        """All extensions in _GENOME_EXTENSIONS are discovered."""
        genome_dir = tmp_path / "all_exts"
        genome_dir.mkdir()
        for ext in _GENOME_EXTENSIONS:
            (genome_dir / f"test{ext}").write_text(">s\nA\n")
        result = _expand_genome_paths([genome_dir])
        assert len(result) == len(_GENOME_EXTENSIONS)


class TestFnaGenomeGeneration:
    """Test that .fna/.fna.gz genome files work end-to-end with generation."""

    def test_fna_file_generates_reads(self, tmp_path):
        """A .fna genome file produces reads with correct output naming."""
        genome = tmp_path / "GCF_000005845.2.fna"
        genome.write_text(">chr1\n" + "ATCGATCG" * 50 + "\n")
        target = tmp_path / "output"
        config = SimulationConfig(
            target_dir=target,
            operation="generate",
            genome_inputs=[genome],
            read_count=10,
            reads_per_file=5,
            mean_read_length=20,
            std_read_length=5,
            min_read_length=10,
            output_format="fastq",
            interval=0.0,
            timing_model="uniform",
        )
        sim = NanoporeSimulator(config, enable_monitoring=False)
        sim.run_simulation()
        fq_files = list(target.rglob("*.fastq"))
        assert len(fq_files) >= 1
        # Output filename should strip .fna, giving GCF_000005845.2_reads_*
        assert all("GCF_000005845.2_reads_" in f.name for f in fq_files)

    def test_fna_gz_file_generates_reads(self, tmp_path):
        """A .fna.gz genome file works with the builtin generator."""
        genome = tmp_path / "test_genome.fna.gz"
        import gzip as gz
        with gz.open(genome, "wt") as f:
            f.write(">chr1\n" + "ATCGATCG" * 50 + "\n")
        target = tmp_path / "output"
        config = SimulationConfig(
            target_dir=target,
            operation="generate",
            genome_inputs=[genome],
            read_count=10,
            reads_per_file=10,
            mean_read_length=20,
            std_read_length=5,
            min_read_length=10,
            output_format="fastq",
            interval=0.0,
            timing_model="uniform",
        )
        sim = NanoporeSimulator(config, enable_monitoring=False)
        sim.run_simulation()
        fq_files = list(target.rglob("*.fastq"))
        assert len(fq_files) >= 1
        assert all("test_genome_reads_" in f.name for f in fq_files)
