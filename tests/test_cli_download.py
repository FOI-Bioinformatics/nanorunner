"""Tests for download subcommand using Typer CliRunner."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from typer.testing import CliRunner

from nanopore_simulator.cli.main import app


runner = CliRunner()


class TestDownloadCommand:
    """Test suite for the download subcommand."""

    def test_download_species(self, tmp_path):
        """Test downloading genomes by species name."""
        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve.return_value = MagicMock(
                accession="GCF_000005845.2"
            )

            with patch("nanopore_simulator.cli.main.download_genome") as mock_dl:
                mock_dl.return_value = tmp_path / "genome.fna.gz"
                result = runner.invoke(
                    app, ["download", "--species", "Escherichia coli"]
                )
                assert result.exit_code == 0
                mock_dl.assert_called_once()

    def test_download_mock(self, tmp_path):
        """Test downloading genomes for a mock community."""
        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve.return_value = MagicMock(
                accession="GCF_000005845.2"
            )

            with patch("nanopore_simulator.cli.main.download_genome") as mock_dl:
                mock_dl.return_value = tmp_path / "genome.fna.gz"
                result = runner.invoke(
                    app, ["download", "--mock", "quick_3species"]
                )
                assert result.exit_code == 0
                # Should download 3 genomes
                assert mock_dl.call_count == 3

    def test_download_requires_species_or_mock(self):
        """Test that download command requires --species, --mock, or --taxid."""
        result = runner.invoke(app, ["download"])
        assert result.exit_code == 1
        assert "Must specify" in result.output

    def test_download_taxid(self, tmp_path):
        """Test downloading genomes by taxonomy ID."""
        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve_taxid.return_value = MagicMock(
                accession="GCF_000005845.2"
            )

            with patch("nanopore_simulator.cli.main.download_genome") as mock_dl:
                mock_dl.return_value = tmp_path / "genome.fna.gz"
                result = runner.invoke(app, ["download", "--taxid", "562"])
                assert result.exit_code == 0
                mock_dl.assert_called_once()

    def test_download_unknown_mock(self):
        """Test that unknown mock community returns error."""
        result = runner.invoke(
            app, ["download", "--mock", "nonexistent_mock"]
        )
        assert result.exit_code == 1
        assert "Unknown mock community" in result.output

    def test_download_unresolvable_species(self):
        """Test warning for species that cannot be resolved."""
        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve.return_value = None

            result = runner.invoke(
                app, ["download", "--species", "Nonexistent species"]
            )
            assert result.exit_code == 1
            assert "Could not resolve" in result.output

    def test_download_multiple_species(self, tmp_path):
        """Test downloading multiple species at once."""
        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve.return_value = MagicMock(
                accession="GCF_000005845.2"
            )

            with patch("nanopore_simulator.cli.main.download_genome") as mock_dl:
                mock_dl.return_value = tmp_path / "genome.fna.gz"
                result = runner.invoke(
                    app,
                    [
                        "download",
                        "--species",
                        "Escherichia coli",
                        "--species",
                        "Staphylococcus aureus",
                    ],
                )
                assert result.exit_code == 0
                assert mock_dl.call_count == 2

    def test_download_multiple_taxids(self, tmp_path):
        """Test downloading multiple taxonomy IDs at once."""
        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve_taxid.return_value = MagicMock(
                accession="GCF_000005845.2"
            )

            with patch("nanopore_simulator.cli.main.download_genome") as mock_dl:
                mock_dl.return_value = tmp_path / "genome.fna.gz"
                result = runner.invoke(
                    app,
                    [
                        "download",
                        "--taxid",
                        "562",
                        "--taxid",
                        "1280",
                    ],
                )
                assert result.exit_code == 0
                assert mock_dl.call_count == 2

    def test_download_handles_download_failure(self):
        """Test that download failures are handled gracefully."""
        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve.return_value = MagicMock(
                accession="GCF_000005845.2"
            )

            with patch("nanopore_simulator.cli.main.download_genome") as mock_dl:
                mock_dl.side_effect = RuntimeError("Download failed")
                result = runner.invoke(
                    app, ["download", "--species", "Escherichia coli"]
                )
                # No target provided; download-only path returns normally
                # even when individual downloads fail
                assert result.exit_code == 0
                assert "Failed" in result.output


class TestDownloadAndGenerate:
    """Test suite for the download + generate combined workflow.

    When a --target is provided, successfully downloaded genomes are
    used for read generation via NanoporeSimulator.
    """

    def _make_genome_file(self, path):
        """Create a minimal dummy genome file for config validation."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(">seq1\nACGT\n")
        return path

    def test_download_and_generate_mock(self, tmp_path):
        """Test download with --target triggers read generation for a mock community."""
        target = tmp_path / "output"
        genome_paths = [
            self._make_genome_file(tmp_path / "genome1.fna"),
            self._make_genome_file(tmp_path / "genome2.fna"),
            self._make_genome_file(tmp_path / "genome3.fna"),
        ]
        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve.return_value = MagicMock(
                accession="GCF_000005845.2"
            )

            with patch("nanopore_simulator.cli.main.download_genome") as mock_dl:
                mock_dl.side_effect = genome_paths

                with patch(
                    "nanopore_simulator.cli.main.NanoporeSimulator"
                ) as mock_sim_cls:
                    mock_sim = MagicMock()
                    mock_sim_cls.return_value = mock_sim

                    result = runner.invoke(
                        app,
                        [
                            "download",
                            "--mock",
                            "quick_3species",
                            "--target",
                            str(target),
                        ],
                    )

                    assert result.exit_code == 0
                    assert mock_dl.call_count == 3

                    # Verify simulator was created with correct config
                    mock_sim_cls.assert_called_once()
                    config = mock_sim_cls.call_args[0][0]
                    assert config.operation == "generate"
                    assert config.target_dir == target
                    assert len(config.genome_inputs) == 3
                    assert config.genome_inputs == genome_paths
                    assert config.read_count == 1000  # default
                    assert config.sample_type == "mixed"  # >1 organism
                    assert config.abundances is not None
                    mock_sim.run_simulation.assert_called_once()

    def test_download_and_generate_species(self, tmp_path):
        """Test download+generate with --species instead of --mock."""
        target = tmp_path / "output"
        genome_paths = [
            self._make_genome_file(tmp_path / "ecoli.fna"),
            self._make_genome_file(tmp_path / "saureus.fna"),
        ]
        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve.return_value = MagicMock(
                accession="GCF_000005845.2"
            )

            with patch("nanopore_simulator.cli.main.download_genome") as mock_dl:
                mock_dl.side_effect = genome_paths

                with patch(
                    "nanopore_simulator.cli.main.NanoporeSimulator"
                ) as mock_sim_cls:
                    mock_sim = MagicMock()
                    mock_sim_cls.return_value = mock_sim

                    result = runner.invoke(
                        app,
                        [
                            "download",
                            "--species",
                            "Escherichia coli",
                            "--species",
                            "Staphylococcus aureus",
                            "--target",
                            str(target),
                        ],
                    )

                    assert result.exit_code == 0
                    config = mock_sim_cls.call_args[0][0]
                    assert config.operation == "generate"
                    assert len(config.genome_inputs) == 2
                    # No mock -> no abundances
                    assert config.abundances is None
                    assert config.sample_type == "mixed"
                    mock_sim.run_simulation.assert_called_once()

    def test_download_and_generate_custom_options(self, tmp_path):
        """Test that custom generation options are passed through to config."""
        target = tmp_path / "output"
        genome_path = self._make_genome_file(tmp_path / "genome.fna")
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

                    result = runner.invoke(
                        app,
                        [
                            "download",
                            "--species",
                            "Escherichia coli",
                            "--target",
                            str(target),
                            "--read-count",
                            "5000",
                            "--output-format",
                            "fastq",
                            "--interval",
                            "2",
                            "--mean-quality",
                            "25.0",
                            "--generator-backend",
                            "builtin",
                            "--batch-size",
                            "3",
                            "--sample-type",
                            "pure",
                            "--mix-reads",
                        ],
                    )

                    assert result.exit_code == 0
                    config = mock_sim_cls.call_args[0][0]
                    assert config.read_count == 5000
                    assert config.output_format == "fastq"
                    assert config.interval == 2.0
                    assert config.mean_quality == 25.0
                    assert config.generator_backend == "builtin"
                    assert config.batch_size == 3
                    assert config.sample_type == "pure"
                    assert config.mix_reads is True

    def test_download_only_no_target(self, tmp_path):
        """Test that omitting --target preserves download-only behavior."""
        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve.return_value = MagicMock(
                accession="GCF_000005845.2"
            )

            with patch("nanopore_simulator.cli.main.download_genome") as mock_dl:
                mock_dl.return_value = tmp_path / "genome.fna.gz"

                with patch(
                    "nanopore_simulator.cli.main.NanoporeSimulator"
                ) as mock_sim_cls:
                    result = runner.invoke(
                        app,
                        ["download", "--species", "Escherichia coli"],
                    )

                    assert result.exit_code == 0
                    mock_dl.assert_called_once()
                    # No simulator should be created
                    mock_sim_cls.assert_not_called()

    def test_download_and_generate_with_failures(self, tmp_path):
        """Test generation runs with successfully downloaded genomes when some fail."""
        target = tmp_path / "output"
        genome_path = self._make_genome_file(tmp_path / "ecoli.fna")
        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            # First species resolves, second does not
            mock_resolver.resolve.side_effect = [
                MagicMock(accession="GCF_000005845.2"),
                None,
            ]

            with patch("nanopore_simulator.cli.main.download_genome") as mock_dl:
                mock_dl.return_value = genome_path

                with patch(
                    "nanopore_simulator.cli.main.NanoporeSimulator"
                ) as mock_sim_cls:
                    mock_sim = MagicMock()
                    mock_sim_cls.return_value = mock_sim

                    result = runner.invoke(
                        app,
                        [
                            "download",
                            "--species",
                            "Escherichia coli",
                            "--species",
                            "Nonexistent species",
                            "--target",
                            str(target),
                        ],
                    )

                    assert result.exit_code == 0
                    assert "Could not resolve" in result.output

                    # Simulator should still be created with one successful genome
                    mock_sim_cls.assert_called_once()
                    config = mock_sim_cls.call_args[0][0]
                    assert len(config.genome_inputs) == 1
                    assert config.genome_inputs[0] == genome_path
                    assert config.sample_type == "pure"  # single genome
                    mock_sim.run_simulation.assert_called_once()

    def test_download_and_generate_all_downloads_fail(self, tmp_path):
        """Test that generation is skipped with error when all downloads fail."""
        target = tmp_path / "output"
        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve.return_value = MagicMock(
                accession="GCF_000005845.2"
            )

            with patch("nanopore_simulator.cli.main.download_genome") as mock_dl:
                mock_dl.side_effect = RuntimeError("Download failed")

                with patch(
                    "nanopore_simulator.cli.main.NanoporeSimulator"
                ) as mock_sim_cls:
                    result = runner.invoke(
                        app,
                        [
                            "download",
                            "--mock",
                            "quick_3species",
                            "--target",
                            str(target),
                        ],
                    )

                    assert result.exit_code == 1
                    assert "No genomes downloaded successfully" in result.output
                    mock_sim_cls.assert_not_called()

    def test_download_and_generate_simulation_error(self, tmp_path):
        """Test error handling when simulation fails after successful download."""
        target = tmp_path / "output"
        genome_path = self._make_genome_file(tmp_path / "genome.fna")
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
                    mock_sim.run_simulation.side_effect = RuntimeError(
                        "Simulation failed"
                    )

                    result = runner.invoke(
                        app,
                        [
                            "download",
                            "--mock",
                            "quick_3species",
                            "--target",
                            str(target),
                        ],
                    )

                    assert result.exit_code == 1
                    assert "Error during read generation" in result.output
