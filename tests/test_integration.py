"""End-to-end integration tests for nanorunner v2.

Exercises the full stack through the CLI (typer.testing.CliRunner),
verifying that replay, generate, and utility commands produce the
expected on-disk results.  All tests use --interval 0 or --no-wait
for speed and rely on tmp_path fixtures.
"""

import gzip
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nanopore_simulator.cli import app

runner = CliRunner()


# -------------------------------------------------------------------
# Replay integration
# -------------------------------------------------------------------


class TestReplaySingleplex:
    """Singleplex replay through the CLI."""

    def test_singleplex_copy_uniform_timing(
        self, source_dir_singleplex: Path, tmp_path: Path
    ):
        """Copy files from a flat source directory with zero interval."""
        target = tmp_path / "target"
        result = runner.invoke(
            app,
            [
                "replay",
                "--source",
                str(source_dir_singleplex),
                "--target",
                str(target),
                "--interval",
                "0",
                "--quiet",
            ],
        )
        assert result.exit_code == 0, result.output
        copied_files = list(target.glob("*.fastq"))
        source_files = list(source_dir_singleplex.glob("*.fastq"))
        assert len(copied_files) == len(source_files)

    def test_singleplex_copy_file_contents_match(
        self, source_dir_singleplex: Path, tmp_path: Path
    ):
        """Copied files preserve the original content."""
        target = tmp_path / "target"
        runner.invoke(
            app,
            [
                "replay",
                "--source",
                str(source_dir_singleplex),
                "--target",
                str(target),
                "--interval",
                "0",
                "--quiet",
            ],
        )
        for src_file in sorted(source_dir_singleplex.glob("*.fastq")):
            tgt_file = target / src_file.name
            assert tgt_file.exists()
            assert tgt_file.read_text() == src_file.read_text()


class TestReplayMultiplex:
    """Multiplex replay through the CLI."""

    def test_multiplex_copy_preserves_barcode_structure(
        self, source_dir_multiplex: Path, tmp_path: Path
    ):
        """Barcode subdirectories are reproduced in the target."""
        target = tmp_path / "target"
        result = runner.invoke(
            app,
            [
                "replay",
                "--source",
                str(source_dir_multiplex),
                "--target",
                str(target),
                "--interval",
                "0",
                "--quiet",
            ],
        )
        assert result.exit_code == 0, result.output
        for bc in ["barcode01", "barcode02"]:
            bc_dir = target / bc
            assert bc_dir.is_dir(), f"Missing barcode dir: {bc}"
            files = list(bc_dir.glob("*.fastq"))
            assert len(files) == 3, f"Expected 3 files in {bc}"


class TestReplayLink:
    """Symlink operation through the CLI."""

    def test_link_creates_symlinks(self, source_dir_singleplex: Path, tmp_path: Path):
        """Link mode creates working symbolic links."""
        target = tmp_path / "target"
        result = runner.invoke(
            app,
            [
                "replay",
                "--source",
                str(source_dir_singleplex),
                "--target",
                str(target),
                "--operation",
                "link",
                "--interval",
                "0",
                "--quiet",
            ],
        )
        assert result.exit_code == 0, result.output
        linked = list(target.glob("*.fastq"))
        assert len(linked) == 5
        for f in linked:
            assert f.is_symlink()

    def test_link_target_readable(self, source_dir_singleplex: Path, tmp_path: Path):
        """Symlinked files resolve to readable content."""
        target = tmp_path / "target"
        runner.invoke(
            app,
            [
                "replay",
                "--source",
                str(source_dir_singleplex),
                "--target",
                str(target),
                "--operation",
                "link",
                "--interval",
                "0",
                "--quiet",
            ],
        )
        for f in target.glob("*.fastq"):
            content = f.read_text()
            assert "@read" in content


class TestReplayProfile:
    """Profile-based replay through the CLI."""

    def test_development_profile(self, source_dir_singleplex: Path, tmp_path: Path):
        """The development profile completes without error."""
        target = tmp_path / "target"
        result = runner.invoke(
            app,
            [
                "replay",
                "--source",
                str(source_dir_singleplex),
                "--target",
                str(target),
                "--profile",
                "development",
                "--interval",
                "0",
                "--quiet",
            ],
        )
        assert result.exit_code == 0, result.output
        # Development profile uses link operation
        linked = list(target.glob("*.fastq"))
        assert len(linked) == 5


class TestReplayParallel:
    """Parallel replay through the CLI."""

    def test_parallel_replay_produces_files(
        self, source_dir_singleplex: Path, tmp_path: Path
    ):
        """Parallel mode produces the same files as sequential."""
        target = tmp_path / "target"
        result = runner.invoke(
            app,
            [
                "replay",
                "--source",
                str(source_dir_singleplex),
                "--target",
                str(target),
                "--parallel",
                "--worker-count",
                "2",
                "--interval",
                "0",
                "--quiet",
            ],
        )
        assert result.exit_code == 0, result.output
        assert len(list(target.glob("*.fastq"))) == 5


class TestReplayTimingModels:
    """All timing models complete successfully through the CLI."""

    @pytest.mark.parametrize("model", ["uniform", "random", "poisson", "adaptive"])
    def test_timing_model_completes(
        self, model: str, source_dir_singleplex: Path, tmp_path: Path
    ):
        """Each timing model runs to completion with --interval 0."""
        target = tmp_path / f"target_{model}"
        result = runner.invoke(
            app,
            [
                "replay",
                "--source",
                str(source_dir_singleplex),
                "--target",
                str(target),
                "--timing-model",
                model,
                "--interval",
                "0",
                "--quiet",
            ],
        )
        assert result.exit_code == 0, result.output
        assert len(list(target.glob("*.fastq"))) == 5


class TestReplayNoWait:
    """The --no-wait flag zeroes the interval."""

    def test_no_wait_flag(self, source_dir_singleplex: Path, tmp_path: Path):
        """--no-wait produces the same result as --interval 0."""
        target = tmp_path / "target"
        result = runner.invoke(
            app,
            [
                "replay",
                "--source",
                str(source_dir_singleplex),
                "--target",
                str(target),
                "--no-wait",
                "--quiet",
            ],
        )
        assert result.exit_code == 0, result.output
        assert len(list(target.glob("*.fastq"))) == 5


class TestReplayBatchSize:
    """Batch size controls how files are grouped."""

    def test_batch_size_does_not_affect_file_count(
        self, source_dir_singleplex: Path, tmp_path: Path
    ):
        """All files are produced regardless of batch size."""
        target = tmp_path / "target"
        result = runner.invoke(
            app,
            [
                "replay",
                "--source",
                str(source_dir_singleplex),
                "--target",
                str(target),
                "--batch-size",
                "3",
                "--interval",
                "0",
                "--quiet",
            ],
        )
        assert result.exit_code == 0, result.output
        assert len(list(target.glob("*.fastq"))) == 5


# -------------------------------------------------------------------
# Generate integration
# -------------------------------------------------------------------


class TestGenerateSingleGenome:
    """Single-genome generation through the CLI."""

    def test_single_genome_builtin(self, sample_fasta: Path, tmp_path: Path):
        """Generate reads from one genome and verify output file count."""
        target = tmp_path / "gen_target"
        read_count = 200
        reads_per_file = 100
        result = runner.invoke(
            app,
            [
                "generate",
                "--target",
                str(target),
                "--genomes",
                str(sample_fasta),
                "--generator-backend",
                "builtin",
                "--read-count",
                str(read_count),
                "--reads-per-file",
                str(reads_per_file),
                "--output-format",
                "fastq",
                "--no-wait",
                "--quiet",
            ],
        )
        assert result.exit_code == 0, result.output
        output_files = list(target.glob("*.fastq"))
        expected_files = read_count // reads_per_file
        assert len(output_files) == expected_files

    def test_single_genome_output_has_reads(self, sample_fasta: Path, tmp_path: Path):
        """Each output file contains the expected number of reads."""
        target = tmp_path / "gen_target"
        result = runner.invoke(
            app,
            [
                "generate",
                "--target",
                str(target),
                "--genomes",
                str(sample_fasta),
                "--generator-backend",
                "builtin",
                "--read-count",
                "50",
                "--reads-per-file",
                "50",
                "--output-format",
                "fastq",
                "--no-wait",
                "--quiet",
            ],
        )
        assert result.exit_code == 0, result.output
        output_files = list(target.glob("*.fastq"))
        assert len(output_files) == 1
        content = output_files[0].read_text()
        # Each read has 4 lines
        lines = [l for l in content.strip().split("\n") if l]
        assert len(lines) == 50 * 4

    def test_generate_gzipped_output(self, sample_fasta: Path, tmp_path: Path):
        """Generate mode produces gzipped FASTQ files."""
        target = tmp_path / "gen_target"
        result = runner.invoke(
            app,
            [
                "generate",
                "--target",
                str(target),
                "--genomes",
                str(sample_fasta),
                "--generator-backend",
                "builtin",
                "--read-count",
                "50",
                "--reads-per-file",
                "50",
                "--output-format",
                "fastq.gz",
                "--no-wait",
                "--quiet",
            ],
        )
        assert result.exit_code == 0, result.output
        gz_files = list(target.glob("*.fastq.gz"))
        assert len(gz_files) == 1
        # Verify the file is actually gzipped and readable
        with gzip.open(gz_files[0], "rt") as f:
            content = f.read()
        assert "@" in content


class TestGenerateMultipleGenomes:
    """Multiple-genome generation through the CLI."""

    def test_multiple_genomes_singleplex(self, tmp_path: Path):
        """Two genomes with --force-structure singleplex produce files in root."""
        genome_a = tmp_path / "genome_a.fa"
        genome_b = tmp_path / "genome_b.fa"
        genome_a.write_text(">chr1\nACGTACGTACGTACGT\n")
        genome_b.write_text(">chr1\nTTTTAAAACCCCGGGG\n")

        target = tmp_path / "gen_target"
        result = runner.invoke(
            app,
            [
                "generate",
                "--target",
                str(target),
                "--genomes",
                str(genome_a),
                "--genomes",
                str(genome_b),
                "--generator-backend",
                "builtin",
                "--read-count",
                "200",
                "--reads-per-file",
                "100",
                "--output-format",
                "fastq",
                "--force-structure",
                "singleplex",
                "--no-wait",
                "--quiet",
            ],
        )
        assert result.exit_code == 0, result.output
        output_files = list(target.glob("*.fastq"))
        # 200 reads split between 2 genomes = 100 each = 1 file each = 2 files
        assert len(output_files) == 2

    def test_multiple_genomes_multiplex(self, tmp_path: Path):
        """Two genomes in multiplex mode produce barcode directories."""
        genome_a = tmp_path / "genome_a.fa"
        genome_b = tmp_path / "genome_b.fa"
        genome_a.write_text(">chr1\nACGTACGTACGTACGT\n")
        genome_b.write_text(">chr1\nTTTTAAAACCCCGGGG\n")

        target = tmp_path / "gen_target"
        result = runner.invoke(
            app,
            [
                "generate",
                "--target",
                str(target),
                "--genomes",
                str(genome_a),
                "--genomes",
                str(genome_b),
                "--generator-backend",
                "builtin",
                "--read-count",
                "200",
                "--reads-per-file",
                "100",
                "--output-format",
                "fastq",
                "--force-structure",
                "multiplex",
                "--no-wait",
                "--quiet",
            ],
        )
        assert result.exit_code == 0, result.output
        assert (target / "barcode01").is_dir()
        assert (target / "barcode02").is_dir()
        bc01_files = list((target / "barcode01").glob("*.fastq"))
        bc02_files = list((target / "barcode02").glob("*.fastq"))
        assert len(bc01_files) >= 1
        assert len(bc02_files) >= 1


class TestGenerateAbundanceWeighting:
    """Abundance-weighted read distribution through the CLI."""

    def test_abundance_weighting(self, tmp_path: Path):
        """Genomes with different abundances produce proportional files."""
        genome_a = tmp_path / "genome_a.fa"
        genome_b = tmp_path / "genome_b.fa"
        genome_a.write_text(">chr1\nACGTACGTACGTACGT\n")
        genome_b.write_text(">chr1\nTTTTAAAACCCCGGGG\n")

        target = tmp_path / "gen_target"
        result = runner.invoke(
            app,
            [
                "generate",
                "--target",
                str(target),
                "--genomes",
                str(genome_a),
                "--genomes",
                str(genome_b),
                "--generator-backend",
                "builtin",
                "--read-count",
                "1000",
                "--reads-per-file",
                "100",
                "--output-format",
                "fastq",
                "--abundances",
                "0.9",
                "--abundances",
                "0.1",
                "--force-structure",
                "singleplex",
                "--no-wait",
                "--quiet",
            ],
        )
        assert result.exit_code == 0, result.output
        output_files = list(target.glob("*.fastq"))
        # 1000 reads total / 100 per file = 10 files
        assert len(output_files) == 10
        # Files are named per genome - genome_a should have more files
        a_files = [f for f in output_files if "genome_a" in f.name]
        b_files = [f for f in output_files if "genome_b" in f.name]
        assert len(a_files) > len(b_files)


class TestGenerateTimingModels:
    """Generate mode works with all timing models."""

    @pytest.mark.parametrize("model", ["uniform", "random", "poisson", "adaptive"])
    def test_generate_with_timing_model(
        self, model: str, sample_fasta: Path, tmp_path: Path
    ):
        """Each timing model completes in generate mode."""
        target = tmp_path / f"gen_{model}"
        result = runner.invoke(
            app,
            [
                "generate",
                "--target",
                str(target),
                "--genomes",
                str(sample_fasta),
                "--generator-backend",
                "builtin",
                "--read-count",
                "50",
                "--reads-per-file",
                "50",
                "--output-format",
                "fastq",
                "--timing-model",
                model,
                "--no-wait",
                "--quiet",
            ],
        )
        assert result.exit_code == 0, result.output
        assert len(list(target.glob("*.fastq"))) == 1


class TestGenerateParallel:
    """Parallel generation through the CLI."""

    def test_parallel_generate(self, sample_fasta: Path, tmp_path: Path):
        """Parallel mode produces expected number of files."""
        target = tmp_path / "gen_target"
        result = runner.invoke(
            app,
            [
                "generate",
                "--target",
                str(target),
                "--genomes",
                str(sample_fasta),
                "--generator-backend",
                "builtin",
                "--read-count",
                "300",
                "--reads-per-file",
                "100",
                "--output-format",
                "fastq",
                "--parallel",
                "--worker-count",
                "2",
                "--no-wait",
                "--quiet",
            ],
        )
        assert result.exit_code == 0, result.output
        assert len(list(target.glob("*.fastq"))) == 3


# -------------------------------------------------------------------
# Cross-cutting / utility commands
# -------------------------------------------------------------------


class TestListCommands:
    """Utility list commands return expected content."""

    def test_list_profiles_exits_zero(self):
        result = runner.invoke(app, ["list-profiles"])
        assert result.exit_code == 0

    def test_list_profiles_contains_development(self):
        result = runner.invoke(app, ["list-profiles"])
        assert "development" in result.output

    def test_list_profiles_contains_bursty(self):
        result = runner.invoke(app, ["list-profiles"])
        assert "bursty" in result.output

    def test_list_profiles_contains_generate_test(self):
        result = runner.invoke(app, ["list-profiles"])
        assert "generate_test" in result.output

    def test_list_adapters_exits_zero(self):
        result = runner.invoke(app, ["list-adapters"])
        assert result.exit_code == 0

    def test_list_adapters_contains_nanometa(self):
        result = runner.invoke(app, ["list-adapters"])
        assert "nanometa" in result.output

    def test_list_adapters_contains_kraken(self):
        result = runner.invoke(app, ["list-adapters"])
        assert "kraken" in result.output

    def test_list_generators_exits_zero(self):
        result = runner.invoke(app, ["list-generators"])
        assert result.exit_code == 0

    def test_list_generators_contains_builtin(self):
        result = runner.invoke(app, ["list-generators"])
        assert "builtin" in result.output

    def test_list_mocks_exits_zero(self):
        result = runner.invoke(app, ["list-mocks"])
        assert result.exit_code == 0

    def test_list_mocks_contains_zymo(self):
        result = runner.invoke(app, ["list-mocks"])
        assert "zymo_d6300" in result.output


class TestCheckDeps:
    """Dependency checking through the CLI."""

    def test_check_deps_exits_zero(self):
        result = runner.invoke(app, ["check-deps"])
        assert result.exit_code == 0

    def test_check_deps_shows_builtin(self):
        result = runner.invoke(app, ["check-deps"])
        assert "builtin" in result.output

    def test_check_deps_shows_categories(self):
        result = runner.invoke(app, ["check-deps"])
        assert "Read Generation Backends" in result.output


class TestValidateCommand:
    """Pipeline validation through the CLI."""

    def test_validate_nanometa_with_multiplex_fastq(
        self, source_dir_multiplex: Path, tmp_path: Path
    ):
        """Validate a multiplex directory against the nanometa adapter."""
        # First replay to create a valid output directory
        target = tmp_path / "target"
        runner.invoke(
            app,
            [
                "replay",
                "--source",
                str(source_dir_multiplex),
                "--target",
                str(target),
                "--interval",
                "0",
                "--quiet",
            ],
        )
        # Now validate
        result = runner.invoke(
            app,
            [
                "validate",
                "--pipeline",
                "nanometa",
                "--target",
                str(target),
            ],
        )
        assert result.exit_code == 0
        assert "Valid: yes" in result.output

    def test_validate_empty_directory_reports_issues(self, tmp_path: Path):
        """Validating an empty directory reports missing files."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        result = runner.invoke(
            app,
            [
                "validate",
                "--pipeline",
                "nanometa",
                "--target",
                str(empty_dir),
            ],
        )
        assert result.exit_code == 1
        assert "Valid: no" in result.output

    def test_validate_kraken_adapter(self, source_dir_singleplex: Path, tmp_path: Path):
        """Validate a singleplex directory against the kraken adapter."""
        target = tmp_path / "target"
        runner.invoke(
            app,
            [
                "replay",
                "--source",
                str(source_dir_singleplex),
                "--target",
                str(target),
                "--interval",
                "0",
                "--quiet",
            ],
        )
        result = runner.invoke(
            app,
            [
                "validate",
                "--pipeline",
                "kraken",
                "--target",
                str(target),
            ],
        )
        assert result.exit_code == 0
        assert "Valid: yes" in result.output


class TestRecommendCommand:
    """Profile recommendation through the CLI."""

    def test_recommend_by_file_count(self):
        result = runner.invoke(
            app,
            ["recommend", "--file-count", "10"],
        )
        assert result.exit_code == 0
        assert "Recommended profiles" in result.output

    def test_recommend_source_directory(self, source_dir_singleplex: Path):
        result = runner.invoke(
            app,
            ["recommend", "--source", str(source_dir_singleplex)],
        )
        assert result.exit_code == 0
        assert "Recommended profiles" in result.output


class TestVersionFlag:
    """Version flag returns the expected version string."""

    def test_version_output(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "nanorunner" in result.output
        assert "3.0.0" in result.output


class TestReplayRechunking:
    """Replay with --reads-per-file rechunking."""

    def test_rechunk_singleplex(self, tmp_path: Path):
        """Rechunking distributes reads across multiple output files."""
        # Create source with multi-read FASTQ files
        source = tmp_path / "source"
        source.mkdir()
        reads_content = ""
        for i in range(10):
            reads_content += f"@read{i}\nACGTACGT\n+\nIIIIIIII\n"
        (source / "reads.fastq").write_text(reads_content)

        target = tmp_path / "target"
        result = runner.invoke(
            app,
            [
                "replay",
                "--source",
                str(source),
                "--target",
                str(target),
                "--reads-per-file",
                "3",
                "--interval",
                "0",
                "--quiet",
            ],
        )
        assert result.exit_code == 0, result.output
        # 10 reads / 3 per file = 4 chunks (3+3+3+1)
        output_files = list(target.glob("*.fastq"))
        assert len(output_files) == 4


class TestReplayForceStructure:
    """The --force-structure flag overrides auto-detection."""

    def test_force_singleplex(self, source_dir_singleplex: Path, tmp_path: Path):
        target = tmp_path / "target"
        result = runner.invoke(
            app,
            [
                "replay",
                "--source",
                str(source_dir_singleplex),
                "--target",
                str(target),
                "--force-structure",
                "singleplex",
                "--interval",
                "0",
                "--quiet",
            ],
        )
        assert result.exit_code == 0, result.output
        assert len(list(target.glob("*.fastq"))) == 5


class TestReplayPipelinePostValidation:
    """Post-run pipeline validation through the CLI."""

    def test_replay_with_pipeline_flag(
        self, source_dir_singleplex: Path, tmp_path: Path
    ):
        """The --pipeline flag triggers post-run validation output."""
        target = tmp_path / "target"
        result = runner.invoke(
            app,
            [
                "replay",
                "--source",
                str(source_dir_singleplex),
                "--target",
                str(target),
                "--pipeline",
                "nanometa",
                "--interval",
                "0",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "nanometa" in result.output.lower()


class TestGenerateWithGenomeDirectory:
    """Generate mode with a directory of genome files."""

    def test_genome_directory_expansion(self, tmp_path: Path):
        """A directory containing genome files is expanded automatically."""
        genome_dir = tmp_path / "genomes"
        genome_dir.mkdir()
        (genome_dir / "species_a.fa").write_text(">chr1\nACGTACGTACGTACGT\n")
        (genome_dir / "species_b.fa").write_text(">chr1\nTTTTAAAACCCCGGGG\n")

        target = tmp_path / "gen_target"
        result = runner.invoke(
            app,
            [
                "generate",
                "--target",
                str(target),
                "--genomes",
                str(genome_dir),
                "--generator-backend",
                "builtin",
                "--read-count",
                "100",
                "--reads-per-file",
                "50",
                "--output-format",
                "fastq",
                "--force-structure",
                "singleplex",
                "--no-wait",
                "--quiet",
            ],
        )
        assert result.exit_code == 0, result.output
        output_files = list(target.glob("*.fastq"))
        # 100 reads / 2 genomes = 50 each / 50 per file = 1 file each
        assert len(output_files) == 2


@pytest.mark.slow
class TestStress96Barcodes:
    """Stress test: 96 barcodes x 5 files x 100 reads."""

    def test_96_barcode_stress(self, tmp_path: Path):
        """Generate 96 barcodes with 5 files each, verifying scale."""
        # Create 96 genome files
        genome_dir = tmp_path / "genomes"
        genome_dir.mkdir()
        for i in range(96):
            seq = "ACGTACGT" * 10  # 80bp genome
            (genome_dir / f"species_{i:03d}.fa").write_text(f">chr1\n{seq}\n")
        genomes = sorted(genome_dir.glob("*.fa"))

        target = tmp_path / "target"
        # Build CLI args: 96 genomes, each gets a barcode dir
        args = [
            "generate",
            "--target",
            str(target),
            "--generator-backend",
            "builtin",
            "--read-count",
            str(96 * 500),  # 500 reads per genome
            "--reads-per-file",
            "100",  # 5 files per barcode
            "--output-format",
            "fastq",
            "--force-structure",
            "multiplex",
            "--no-wait",
            "--quiet",
        ]
        for g in genomes:
            args.extend(["--genomes", str(g)])

        result = runner.invoke(app, args)
        assert result.exit_code == 0, result.output

        # Verify all 96 barcode directories created
        barcode_dirs = sorted(
            d for d in target.iterdir() if d.is_dir() and d.name.startswith("barcode")
        )
        assert (
            len(barcode_dirs) == 96
        ), f"Expected 96 barcode dirs, got {len(barcode_dirs)}"

        # Verify total file count: 96 barcodes x 5 files = 480
        all_files = list(target.rglob("*.fastq"))
        assert len(all_files) == 480, f"Expected 480 files, got {len(all_files)}"

        # Verify no filename collisions (all paths unique)
        paths = [str(f) for f in all_files]
        assert len(paths) == len(set(paths)), "File path collision detected"

        # Verify no leftover .tmp files
        tmp_files = list(target.rglob("*.tmp"))
        assert len(tmp_files) == 0, f"Found {len(tmp_files)} orphaned .tmp files"


class TestErrorHandling:
    """CLI reports errors cleanly for invalid inputs."""

    def test_missing_source_directory(self, tmp_path: Path):
        """Replay with non-existent source directory fails."""
        result = runner.invoke(
            app,
            [
                "replay",
                "--source",
                str(tmp_path / "nonexistent"),
                "--target",
                str(tmp_path / "target"),
            ],
        )
        assert result.exit_code != 0

    def test_generate_no_genome_source(self, tmp_path: Path):
        """Generate without any genome source fails."""
        result = runner.invoke(
            app,
            [
                "generate",
                "--target",
                str(tmp_path / "target"),
            ],
        )
        assert result.exit_code != 0

    def test_generate_mutual_exclusion(self, sample_fasta: Path, tmp_path: Path):
        """Providing both --genomes and --mock fails."""
        result = runner.invoke(
            app,
            [
                "generate",
                "--target",
                str(tmp_path / "target"),
                "--genomes",
                str(sample_fasta),
                "--mock",
                "zymo_d6300",
                "--no-wait",
                "--quiet",
            ],
        )
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output.lower()

    def test_invalid_profile_name(self, source_dir_singleplex: Path, tmp_path: Path):
        """An unrecognized profile name fails with a clear message."""
        result = runner.invoke(
            app,
            [
                "replay",
                "--source",
                str(source_dir_singleplex),
                "--target",
                str(tmp_path / "target"),
                "--profile",
                "nonexistent_profile",
                "--interval",
                "0",
            ],
        )
        assert result.exit_code != 0

    def test_reads_per_file_incompatible_with_link(
        self, source_dir_singleplex: Path, tmp_path: Path
    ):
        """--reads-per-file with --operation link fails."""
        result = runner.invoke(
            app,
            [
                "replay",
                "--source",
                str(source_dir_singleplex),
                "--target",
                str(tmp_path / "target"),
                "--operation",
                "link",
                "--reads-per-file",
                "5",
                "--interval",
                "0",
            ],
        )
        assert result.exit_code != 0
        assert "incompatible" in result.output.lower()

    def test_validate_unknown_adapter(self, tmp_path: Path):
        """Validating with an unknown adapter name fails."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        result = runner.invoke(
            app,
            [
                "validate",
                "--pipeline",
                "nonexistent",
                "--target",
                str(empty_dir),
            ],
        )
        assert result.exit_code != 0
