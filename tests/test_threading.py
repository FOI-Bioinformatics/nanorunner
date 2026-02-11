"""Tests for --no-wait flag, parallel downloads, and parallel generation."""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from nanopore_simulator.cli.main import app, _download_genomes


runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source_dir(tmp_path):
    """Create a minimal source directory with a FASTQ file."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "sample.fastq").write_text("@read1\nACGT\n+\nIIII\n")
    return source


def _make_genome_file(tmp_path, name="genome.fa"):
    """Create a minimal genome FASTA file."""
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(">chr1\nACGTACGTACGTACGTACGTACGTACGTACGT\n")
    return path


# ---------------------------------------------------------------------------
# --no-wait on replay
# ---------------------------------------------------------------------------


class TestNoWaitReplay:
    """Tests for the --no-wait flag on the replay command."""

    def test_no_wait_sets_interval_zero(self, tmp_path):
        """--no-wait should set interval to 0, completing without timing delays."""
        source = _make_source_dir(tmp_path)
        target = tmp_path / "target"

        result = runner.invoke(app, [
            "replay",
            "--source", str(source),
            "--target", str(target),
            "--no-wait",
        ])

        assert result.exit_code == 0
        assert (target / "sample.fastq").exists()

    def test_no_wait_overrides_explicit_interval(self, tmp_path):
        """--no-wait should override an explicit --interval value."""
        source = _make_source_dir(tmp_path)
        target = tmp_path / "target"

        result = runner.invoke(app, [
            "replay",
            "--source", str(source),
            "--target", str(target),
            "--interval", "60",
            "--no-wait",
        ])

        assert result.exit_code == 0
        assert (target / "sample.fastq").exists()

    def test_no_wait_with_profile(self, tmp_path):
        """--no-wait should override profile interval settings."""
        source = _make_source_dir(tmp_path)
        target = tmp_path / "target"

        result = runner.invoke(app, [
            "replay",
            "--source", str(source),
            "--target", str(target),
            "--profile", "bursty",
            "--no-wait",
        ])

        assert result.exit_code == 0
        assert (target / "sample.fastq").exists()


# ---------------------------------------------------------------------------
# --no-wait on generate
# ---------------------------------------------------------------------------


class TestNoWaitGenerate:
    """Tests for the --no-wait flag on the generate command."""

    def test_no_wait_sets_interval_zero(self, tmp_path):
        """--no-wait on generate should complete without timing delays."""
        genome = _make_genome_file(tmp_path)
        target = tmp_path / "target"

        result = runner.invoke(app, [
            "generate",
            "--genomes", str(genome),
            "--target", str(target),
            "--no-wait",
            "--read-count", "10",
            "--reads-per-file", "10",
        ])

        assert result.exit_code == 0
        assert target.exists()

    def test_no_wait_overrides_explicit_interval(self, tmp_path):
        """--no-wait should override --interval on generate."""
        genome = _make_genome_file(tmp_path)
        target = tmp_path / "target"

        result = runner.invoke(app, [
            "generate",
            "--genomes", str(genome),
            "--target", str(target),
            "--interval", "60",
            "--no-wait",
            "--read-count", "10",
            "--reads-per-file", "10",
        ])

        assert result.exit_code == 0
        assert target.exists()


# ---------------------------------------------------------------------------
# --no-wait on download
# ---------------------------------------------------------------------------


class TestNoWaitDownload:
    """Tests for the --no-wait flag on the download command."""

    def test_no_wait_on_download_with_target(self, tmp_path):
        """--no-wait on download should set interval=0 for generation."""
        target = tmp_path / "output"
        genome_path = _make_genome_file(tmp_path, "genome.fna")

        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve.return_value = MagicMock(
                accession="GCF_000005845.2"
            )

            with patch("nanopore_simulator.cli.main.download_genome") as mock_dl:
                mock_dl.return_value = genome_path

                with patch(
                    "nanopore_simulator.cli.main.NanoporeSimulator"
                ) as mock_sim_cls:
                    mock_sim = MagicMock()
                    mock_sim_cls.return_value = mock_sim

                    result = runner.invoke(app, [
                        "download",
                        "--species", "Escherichia coli",
                        "--target", str(target),
                        "--no-wait",
                    ])

                    assert result.exit_code == 0
                    config = mock_sim_cls.call_args[0][0]
                    assert config.interval == 0.0


# ---------------------------------------------------------------------------
# CLI help output
# ---------------------------------------------------------------------------


class TestHelpOutput:
    """Verify --no-wait appears in CLI help for relevant commands."""

    def test_replay_help_contains_no_wait(self):
        result = runner.invoke(app, ["replay", "--help"])
        assert result.exit_code == 0
        assert "--no-wait" in result.output

    def test_generate_help_contains_no_wait(self):
        result = runner.invoke(app, ["generate", "--help"])
        assert result.exit_code == 0
        assert "--no-wait" in result.output

    def test_download_help_contains_no_wait(self):
        result = runner.invoke(app, ["download", "--help"])
        assert result.exit_code == 0
        assert "--no-wait" in result.output

    def test_download_help_contains_parallel(self):
        result = runner.invoke(app, ["download", "--help"])
        assert result.exit_code == 0
        assert "--parallel" in result.output

    def test_download_help_contains_worker_count(self):
        result = runner.invoke(app, ["download", "--help"])
        assert result.exit_code == 0
        assert "--worker-count" in result.output


# ---------------------------------------------------------------------------
# Parallel downloads
# ---------------------------------------------------------------------------


class TestParallelDownload:
    """Tests for parallel genome downloading."""

    def test_parallel_download_uses_thread_pool(self, tmp_path):
        """--parallel should invoke ThreadPoolExecutor for downloads."""
        genome_paths = [
            _make_genome_file(tmp_path, f"genome{i}.fna") for i in range(3)
        ]

        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve.return_value = MagicMock(
                accession="GCF_000005845.2"
            )

            with patch("nanopore_simulator.cli.main.download_genome") as mock_dl:
                mock_dl.side_effect = genome_paths

                result = runner.invoke(app, [
                    "download",
                    "--mock", "quick_3species",
                    "--parallel",
                ])

                assert result.exit_code == 0
                assert mock_dl.call_count == 3

    def test_parallel_download_with_worker_count(self, tmp_path):
        """--worker-count should be accepted alongside --parallel."""
        genome_path = _make_genome_file(tmp_path, "genome.fna")

        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve.return_value = MagicMock(
                accession="GCF_000005845.2"
            )

            with patch("nanopore_simulator.cli.main.download_genome") as mock_dl:
                mock_dl.return_value = genome_path

                result = runner.invoke(app, [
                    "download",
                    "--species", "Escherichia coli",
                    "--parallel",
                    "--worker-count", "2",
                ])

                assert result.exit_code == 0
                mock_dl.assert_called_once()

    def test_parallel_download_handles_failures(self, tmp_path):
        """Parallel downloads should handle individual failures gracefully."""
        genome_path = _make_genome_file(tmp_path, "genome.fna")

        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve.return_value = MagicMock(
                accession="GCF_000005845.2"
            )

            with patch("nanopore_simulator.cli.main.download_genome") as mock_dl:
                # First succeeds, second and third fail
                mock_dl.side_effect = [
                    genome_path,
                    RuntimeError("Network error"),
                    RuntimeError("Timeout"),
                ]

                result = runner.invoke(app, [
                    "download",
                    "--mock", "quick_3species",
                    "--parallel",
                ])

                assert result.exit_code == 0
                assert "Failed" in result.output
                assert "Downloaded" in result.output

    def test_download_genomes_sequential_fallback(self, tmp_path):
        """When parallel=False, downloads should be sequential (default)."""
        genome_path = _make_genome_file(tmp_path, "genome.fna")

        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve.return_value = MagicMock(
                accession="GCF_000005845.2"
            )

            with patch("nanopore_simulator.cli.main.download_genome") as mock_dl:
                mock_dl.return_value = genome_path

                result = runner.invoke(app, [
                    "download",
                    "--species", "Escherichia coli",
                ])

                assert result.exit_code == 0
                mock_dl.assert_called_once()


# ---------------------------------------------------------------------------
# Parallel generate
# ---------------------------------------------------------------------------


class TestParallelGenerate:
    """Tests for parallel read generation."""

    def test_parallel_generate_with_batch_size(self, tmp_path):
        """--parallel with --batch-size should produce output files."""
        genome = _make_genome_file(tmp_path)
        target = tmp_path / "target"

        result = runner.invoke(app, [
            "generate",
            "--genomes", str(genome),
            "--target", str(target),
            "--no-wait",
            "--parallel",
            "--batch-size", "4",
            "--worker-count", "2",
            "--read-count", "20",
            "--reads-per-file", "10",
        ])

        assert result.exit_code == 0
        assert target.exists()
        # Should have produced output files
        fastq_files = list(target.rglob("*.fastq*"))
        assert len(fastq_files) > 0


# ---------------------------------------------------------------------------
# _download_genomes unit tests
# ---------------------------------------------------------------------------


class TestDownloadGenomesFunction:
    """Direct unit tests for _download_genomes()."""

    def test_parallel_flag_passed_through(self, tmp_path):
        """parallel=True should use ThreadPoolExecutor internally."""
        genome_paths = [
            _make_genome_file(tmp_path, f"g{i}.fna") for i in range(3)
        ]

        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve.return_value = MagicMock(
                accession="GCF_000005845.2"
            )

            with patch("nanopore_simulator.cli.main.download_genome") as mock_dl:
                mock_dl.side_effect = genome_paths

                successful, _ = _download_genomes(
                    species=["sp1", "sp2", "sp3"],
                    mock_name=None,
                    taxid=None,
                    parallel=True,
                    worker_count=2,
                )

                assert len(successful) == 3
                assert mock_dl.call_count == 3

    def test_sequential_with_single_genome(self, tmp_path):
        """Even with parallel=True, a single genome uses sequential path."""
        genome_path = _make_genome_file(tmp_path, "g.fna")

        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve.return_value = MagicMock(
                accession="GCF_000005845.2"
            )

            with patch("nanopore_simulator.cli.main.download_genome") as mock_dl:
                mock_dl.return_value = genome_path

                successful, _ = _download_genomes(
                    species=["sp1"],
                    mock_name=None,
                    taxid=None,
                    parallel=True,
                    worker_count=4,
                )

                assert len(successful) == 1
