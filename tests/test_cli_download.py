"""Tests for download subcommand"""

import pytest
from unittest.mock import patch, MagicMock
import sys

from nanopore_simulator.cli.main import main


class TestDownloadCommand:
    """Test suite for the download subcommand."""

    def test_download_species(self, monkeypatch, tmp_path):
        """Test downloading genomes by species name."""
        monkeypatch.setattr(
            sys, "argv",
            ["nanorunner", "download", "--species", "Escherichia coli"]
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
            sys, "argv",
            ["nanorunner", "download", "--mock", "quick_3species"]
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
        monkeypatch.setattr(
            sys, "argv",
            ["nanorunner", "download", "--taxid", "562"]
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
                mock_dl.assert_called_once()

    def test_download_unknown_mock(self, monkeypatch, capsys):
        """Test that unknown mock community returns error."""
        monkeypatch.setattr(
            sys, "argv",
            ["nanorunner", "download", "--mock", "nonexistent_mock"]
        )
        result = main()
        assert result == 1
        captured = capsys.readouterr()
        assert "Unknown mock community" in captured.out

    def test_download_unresolvable_species(self, monkeypatch, tmp_path, capsys):
        """Test warning for species that cannot be resolved."""
        monkeypatch.setattr(
            sys, "argv",
            ["nanorunner", "download", "--species", "Nonexistent species"]
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
            sys, "argv",
            ["nanorunner", "download", "--species", "Escherichia coli",
             "Staphylococcus aureus"]
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
            sys, "argv",
            ["nanorunner", "download", "--taxid", "562", "1280"]
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
            sys, "argv",
            ["nanorunner", "download", "--species", "Escherichia coli"]
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
