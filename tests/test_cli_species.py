"""Tests for CLI species/mock arguments"""

import pytest
import sys
from unittest.mock import patch, MagicMock

from nanopore_simulator.cli.main import main


class TestCLISpeciesArgs:

    def test_species_argument(self, tmp_path, monkeypatch):
        """Test --species argument passes species_inputs to config"""
        # Put target_dir before --species to avoid nargs="+" consuming it
        monkeypatch.setattr(
            sys, "argv", ["nanorunner", str(tmp_path), "--species", "Escherichia coli"]
        )
        with patch("nanopore_simulator.cli.main.NanoporeSimulator") as mock_sim:
            mock_sim.return_value.run_simulation.return_value = None
            main()
            config = mock_sim.call_args[0][0]
            assert config.species_inputs == ["Escherichia coli"]

    def test_multiple_species(self, tmp_path, monkeypatch):
        """Test --species with multiple species names"""
        # Put target_dir before --species to avoid nargs="+" consuming it
        monkeypatch.setattr(
            sys,
            "argv",
            ["nanorunner", str(tmp_path), "--species", "E. coli", "S. aureus"],
        )
        with patch("nanopore_simulator.cli.main.NanoporeSimulator") as mock_sim:
            mock_sim.return_value.run_simulation.return_value = None
            main()
            config = mock_sim.call_args[0][0]
            assert len(config.species_inputs) == 2
            assert "E. coli" in config.species_inputs
            assert "S. aureus" in config.species_inputs

    def test_mock_argument(self, tmp_path, monkeypatch):
        """Test --mock argument passes mock_name to config"""
        monkeypatch.setattr(
            sys, "argv", ["nanorunner", "--mock", "zymo_d6300", str(tmp_path)]
        )
        with patch("nanopore_simulator.cli.main.NanoporeSimulator") as mock_sim:
            mock_sim.return_value.run_simulation.return_value = None
            main()
            config = mock_sim.call_args[0][0]
            assert config.mock_name == "zymo_d6300"

    def test_sample_type_argument(self, tmp_path, monkeypatch):
        """Test --sample-type argument passes sample_type to config"""
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "nanorunner",
                "--species",
                "E. coli",
                "--sample-type",
                "mixed",
                str(tmp_path),
            ],
        )
        with patch("nanopore_simulator.cli.main.NanoporeSimulator") as mock_sim:
            mock_sim.return_value.run_simulation.return_value = None
            main()
            config = mock_sim.call_args[0][0]
            assert config.sample_type == "mixed"

    def test_abundances_argument(self, tmp_path, monkeypatch):
        """Test --abundances argument passes abundances to config"""
        # Put target_dir before options with nargs="+" to avoid consumption
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "nanorunner",
                str(tmp_path),
                "--species",
                "E. coli",
                "S. aureus",
                "--sample-type",
                "mixed",
                "--abundances",
                "0.7",
                "0.3",
            ],
        )
        with patch("nanopore_simulator.cli.main.NanoporeSimulator") as mock_sim:
            mock_sim.return_value.run_simulation.return_value = None
            main()
            config = mock_sim.call_args[0][0]
            assert config.abundances == [0.7, 0.3]

    def test_taxid_argument(self, tmp_path, monkeypatch):
        """Test --taxid argument passes taxid_inputs to config"""
        # Put target_dir before --taxid to avoid nargs="+" consuming it
        monkeypatch.setattr(
            sys, "argv", ["nanorunner", str(tmp_path), "--taxid", "562", "1280"]
        )
        with patch("nanopore_simulator.cli.main.NanoporeSimulator") as mock_sim:
            mock_sim.return_value.run_simulation.return_value = None
            main()
            config = mock_sim.call_args[0][0]
            assert config.taxid_inputs == [562, 1280]

    def test_offline_argument(self, tmp_path, monkeypatch):
        """Test --offline argument passes offline_mode to config"""
        monkeypatch.setattr(
            sys,
            "argv",
            ["nanorunner", "--species", "E. coli", "--offline", str(tmp_path)],
        )
        with patch("nanopore_simulator.cli.main.NanoporeSimulator") as mock_sim:
            mock_sim.return_value.run_simulation.return_value = None
            main()
            config = mock_sim.call_args[0][0]
            assert config.offline_mode is True

    def test_list_mocks_command(self, capsys, monkeypatch):
        """Test --list-mocks command lists available mocks"""
        monkeypatch.setattr(sys, "argv", ["nanorunner", "--list-mocks"])
        result = main()
        assert result == 0
        captured = capsys.readouterr()
        assert "zymo_d6300" in captured.out
        assert "Available Mock Communities" in captured.out

    def test_species_and_mock_mutually_exclusive(self, tmp_path, monkeypatch):
        """Test --species and --mock are mutually exclusive"""
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "nanorunner",
                "--species",
                "E. coli",
                "--mock",
                "zymo_d6300",
                str(tmp_path),
            ],
        )
        with pytest.raises(SystemExit):
            main()

    def test_species_and_genomes_mutually_exclusive(self, tmp_path, monkeypatch):
        """Test --species and --genomes are mutually exclusive"""
        # Create a genome file for the test
        genome_file = tmp_path / "genome.fa"
        genome_file.write_text(">seq1\nACGT\n")
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "nanorunner",
                "--species",
                "E. coli",
                "--genomes",
                str(genome_file),
                str(tmp_path),
            ],
        )
        with pytest.raises(SystemExit):
            main()

    def test_mock_and_taxid_mutually_exclusive(self, tmp_path, monkeypatch):
        """Test --mock and --taxid are mutually exclusive"""
        monkeypatch.setattr(
            sys,
            "argv",
            ["nanorunner", "--mock", "zymo_d6300", "--taxid", "562", str(tmp_path)],
        )
        with pytest.raises(SystemExit):
            main()

    def test_species_sets_generate_operation(self, tmp_path, monkeypatch):
        """Test that --species sets operation to generate"""
        # Put target_dir before --species to avoid nargs="+" consuming it
        monkeypatch.setattr(
            sys, "argv", ["nanorunner", str(tmp_path), "--species", "E. coli"]
        )
        with patch("nanopore_simulator.cli.main.NanoporeSimulator") as mock_sim:
            mock_sim.return_value.run_simulation.return_value = None
            main()
            config = mock_sim.call_args[0][0]
            assert config.operation == "generate"

    def test_mock_sets_generate_operation(self, tmp_path, monkeypatch):
        """Test that --mock sets operation to generate"""
        monkeypatch.setattr(
            sys, "argv", ["nanorunner", "--mock", "zymo_d6300", str(tmp_path)]
        )
        with patch("nanopore_simulator.cli.main.NanoporeSimulator") as mock_sim:
            mock_sim.return_value.run_simulation.return_value = None
            main()
            config = mock_sim.call_args[0][0]
            assert config.operation == "generate"

    def test_species_with_profile(self, tmp_path, monkeypatch):
        """Test --species works with --profile"""
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "nanorunner",
                "--species",
                "E. coli",
                "--profile",
                "generate_quick_test",
                str(tmp_path),
            ],
        )
        with patch("nanopore_simulator.cli.main.NanoporeSimulator") as mock_sim:
            mock_sim.return_value.run_simulation.return_value = None
            main()
            config = mock_sim.call_args[0][0]
            assert config.species_inputs == ["E. coli"]
            assert config.operation == "generate"
