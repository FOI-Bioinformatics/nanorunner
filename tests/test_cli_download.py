"""Tests for download subcommand"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, call
import sys

from nanopore_simulator.cli.main import main


class TestDownloadCommand:
    """Test suite for the download subcommand."""

    def test_download_species(self, monkeypatch, tmp_path):
        """Test downloading genomes by species name."""
        monkeypatch.setattr(
            sys, "argv", ["nanorunner", "download", "--species", "Escherichia coli"]
        )
        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve.return_value = MagicMock(accession="GCF_000005845.2")

            with patch("nanopore_simulator.cli.main.download_genome") as mock_dl:
                mock_dl.return_value = tmp_path / "genome.fna.gz"
                result = main()
                assert result == 0
                mock_dl.assert_called_once()

    def test_download_mock(self, monkeypatch, tmp_path):
        """Test downloading genomes for a mock community."""
        monkeypatch.setattr(
            sys, "argv", ["nanorunner", "download", "--mock", "quick_3species"]
        )
        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve.return_value = MagicMock(accession="GCF_000005845.2")

            with patch("nanopore_simulator.cli.main.download_genome") as mock_dl:
                mock_dl.return_value = tmp_path / "genome.fna.gz"
                result = main()
                assert result == 0
                # Should download 3 genomes
                assert mock_dl.call_count == 3

    def test_download_requires_species_or_mock(self, monkeypatch, capsys):
        """Test that download command requires --species, --mock, or --taxid."""
        monkeypatch.setattr(sys, "argv", ["nanorunner", "download"])
        result = main()
        assert result == 1
        captured = capsys.readouterr()
        assert "Must specify" in captured.out

    def test_download_taxid(self, monkeypatch, tmp_path):
        """Test downloading genomes by taxonomy ID."""
        monkeypatch.setattr(sys, "argv", ["nanorunner", "download", "--taxid", "562"])
        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve_taxid.return_value = MagicMock(
                accession="GCF_000005845.2"
            )

            with patch("nanopore_simulator.cli.main.download_genome") as mock_dl:
                mock_dl.return_value = tmp_path / "genome.fna.gz"
                result = main()
                assert result == 0
                mock_dl.assert_called_once()

    def test_download_unknown_mock(self, monkeypatch, capsys):
        """Test that unknown mock community returns error."""
        monkeypatch.setattr(
            sys, "argv", ["nanorunner", "download", "--mock", "nonexistent_mock"]
        )
        result = main()
        assert result == 1
        captured = capsys.readouterr()
        assert "Unknown mock community" in captured.out

    def test_download_unresolvable_species(self, monkeypatch, tmp_path, capsys):
        """Test warning for species that cannot be resolved."""
        monkeypatch.setattr(
            sys, "argv", ["nanorunner", "download", "--species", "Nonexistent species"]
        )
        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve.return_value = None

            result = main()
            assert result == 1
            captured = capsys.readouterr()
            assert "Could not resolve" in captured.out

    def test_download_multiple_species(self, monkeypatch, tmp_path):
        """Test downloading multiple species at once."""
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "nanorunner",
                "download",
                "--species",
                "Escherichia coli",
                "Staphylococcus aureus",
            ],
        )
        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve.return_value = MagicMock(accession="GCF_000005845.2")

            with patch("nanopore_simulator.cli.main.download_genome") as mock_dl:
                mock_dl.return_value = tmp_path / "genome.fna.gz"
                result = main()
                assert result == 0
                assert mock_dl.call_count == 2

    def test_download_multiple_taxids(self, monkeypatch, tmp_path):
        """Test downloading multiple taxonomy IDs at once."""
        monkeypatch.setattr(
            sys, "argv", ["nanorunner", "download", "--taxid", "562", "1280"]
        )
        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve_taxid.return_value = MagicMock(
                accession="GCF_000005845.2"
            )

            with patch("nanopore_simulator.cli.main.download_genome") as mock_dl:
                mock_dl.return_value = tmp_path / "genome.fna.gz"
                result = main()
                assert result == 0
                assert mock_dl.call_count == 2

    def test_download_handles_download_failure(self, monkeypatch, capsys):
        """Test that download failures are handled gracefully."""
        monkeypatch.setattr(
            sys, "argv", ["nanorunner", "download", "--species", "Escherichia coli"]
        )
        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve.return_value = MagicMock(accession="GCF_000005845.2")

            with patch("nanopore_simulator.cli.main.download_genome") as mock_dl:
                mock_dl.side_effect = RuntimeError("Download failed")
                result = main()
                # Should still complete with 0 (partial success)
                assert result == 0
                captured = capsys.readouterr()
                assert "Failed" in captured.out


class TestDownloadAndGenerate:
    """Test suite for the download + generate combined workflow.

    Note: When using --species with nargs="+", target_dir must appear
    before --species or after a -- separator to avoid argparse ambiguity.
    With --mock (single value), target_dir can follow naturally.
    """

    def _make_genome_file(self, path):
        """Create a minimal dummy genome file for config validation."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(">seq1\nACGT\n")
        return path

    def test_download_and_generate_mock(self, monkeypatch, tmp_path):
        """Test download with target_dir triggers read generation for a mock community."""
        target = tmp_path / "output"
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "nanorunner",
                "download",
                "--mock",
                "quick_3species",
                str(target),
            ],
        )
        genome_paths = [
            self._make_genome_file(tmp_path / "genome1.fna"),
            self._make_genome_file(tmp_path / "genome2.fna"),
            self._make_genome_file(tmp_path / "genome3.fna"),
        ]
        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve.return_value = MagicMock(accession="GCF_000005845.2")

            with patch("nanopore_simulator.cli.main.download_genome") as mock_dl:
                mock_dl.side_effect = genome_paths

                with patch(
                    "nanopore_simulator.cli.main.NanoporeSimulator"
                ) as mock_sim_cls:
                    mock_sim = MagicMock()
                    mock_sim_cls.return_value = mock_sim

                    result = main()

                    assert result == 0
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

    def test_download_and_generate_species(self, monkeypatch, tmp_path):
        """Test download+generate with --species instead of --mock."""
        target = tmp_path / "output"
        # Place target_dir before --species to avoid nargs="+" ambiguity
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "nanorunner",
                "download",
                str(target),
                "--species",
                "Escherichia coli",
                "Staphylococcus aureus",
            ],
        )
        genome_paths = [
            self._make_genome_file(tmp_path / "ecoli.fna"),
            self._make_genome_file(tmp_path / "saureus.fna"),
        ]
        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve.return_value = MagicMock(accession="GCF_000005845.2")

            with patch("nanopore_simulator.cli.main.download_genome") as mock_dl:
                mock_dl.side_effect = genome_paths

                with patch(
                    "nanopore_simulator.cli.main.NanoporeSimulator"
                ) as mock_sim_cls:
                    mock_sim = MagicMock()
                    mock_sim_cls.return_value = mock_sim

                    result = main()

                    assert result == 0
                    config = mock_sim_cls.call_args[0][0]
                    assert config.operation == "generate"
                    assert len(config.genome_inputs) == 2
                    # No mock -> no abundances
                    assert config.abundances is None
                    assert config.sample_type == "mixed"
                    mock_sim.run_simulation.assert_called_once()

    def test_download_and_generate_custom_options(self, monkeypatch, tmp_path):
        """Test that custom generation options are passed through to config."""
        target = tmp_path / "output"
        genome_path = self._make_genome_file(tmp_path / "genome.fna")
        # Place target_dir before --species to avoid nargs="+" ambiguity
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "nanorunner",
                "download",
                str(target),
                "--species",
                "Escherichia coli",
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
        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve.return_value = MagicMock(accession="GCF_000005845.2")

            with patch("nanopore_simulator.cli.main.download_genome") as mock_dl:
                mock_dl.return_value = genome_path

                with patch(
                    "nanopore_simulator.cli.main.NanoporeSimulator"
                ) as mock_sim_cls:
                    mock_sim = MagicMock()
                    mock_sim_cls.return_value = mock_sim

                    result = main()

                    assert result == 0
                    config = mock_sim_cls.call_args[0][0]
                    assert config.read_count == 5000
                    assert config.output_format == "fastq"
                    assert config.interval == 2.0
                    assert config.mean_quality == 25.0
                    assert config.generator_backend == "builtin"
                    assert config.batch_size == 3
                    assert config.sample_type == "pure"
                    assert config.mix_reads is True

    def test_download_only_no_target(self, monkeypatch, tmp_path):
        """Test that omitting target_dir preserves download-only behavior."""
        monkeypatch.setattr(
            sys,
            "argv",
            ["nanorunner", "download", "--species", "Escherichia coli"],
        )
        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve.return_value = MagicMock(accession="GCF_000005845.2")

            with patch("nanopore_simulator.cli.main.download_genome") as mock_dl:
                mock_dl.return_value = tmp_path / "genome.fna.gz"

                with patch(
                    "nanopore_simulator.cli.main.NanoporeSimulator"
                ) as mock_sim_cls:
                    result = main()

                    assert result == 0
                    mock_dl.assert_called_once()
                    # No simulator should be created
                    mock_sim_cls.assert_not_called()

    def test_download_and_generate_with_failures(self, monkeypatch, tmp_path, capsys):
        """Test generation runs with successfully downloaded genomes when some fail."""
        target = tmp_path / "output"
        genome_path = self._make_genome_file(tmp_path / "ecoli.fna")
        # Place target_dir before --species to avoid nargs="+" ambiguity
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "nanorunner",
                "download",
                str(target),
                "--species",
                "Escherichia coli",
                "Nonexistent species",
            ],
        )
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

                    result = main()

                    assert result == 0
                    captured = capsys.readouterr()
                    assert "Could not resolve" in captured.out

                    # Simulator should still be created with the one successful genome
                    mock_sim_cls.assert_called_once()
                    config = mock_sim_cls.call_args[0][0]
                    assert len(config.genome_inputs) == 1
                    assert config.genome_inputs[0] == genome_path
                    assert config.sample_type == "pure"  # single genome
                    mock_sim.run_simulation.assert_called_once()

    def test_download_and_generate_all_downloads_fail(
        self, monkeypatch, tmp_path, capsys
    ):
        """Test that generation is skipped with error when all downloads fail."""
        target = tmp_path / "output"
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "nanorunner",
                "download",
                "--mock",
                "quick_3species",
                str(target),
            ],
        )
        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve.return_value = MagicMock(accession="GCF_000005845.2")

            with patch("nanopore_simulator.cli.main.download_genome") as mock_dl:
                mock_dl.side_effect = RuntimeError("Download failed")

                with patch(
                    "nanopore_simulator.cli.main.NanoporeSimulator"
                ) as mock_sim_cls:
                    result = main()

                    assert result == 1
                    captured = capsys.readouterr()
                    assert "No genomes downloaded successfully" in captured.out
                    mock_sim_cls.assert_not_called()

    def test_download_and_generate_simulation_error(
        self, monkeypatch, tmp_path, capsys
    ):
        """Test error handling when simulation fails after successful download."""
        target = tmp_path / "output"
        genome_path = self._make_genome_file(tmp_path / "genome.fna")
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "nanorunner",
                "download",
                "--mock",
                "quick_3species",
                str(target),
            ],
        )
        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve.return_value = MagicMock(accession="GCF_000005845.2")

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

                    result = main()

                    assert result == 1
                    captured = capsys.readouterr()
                    assert "Error during read generation" in captured.out
