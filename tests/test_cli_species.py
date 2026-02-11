"""Tests for CLI species/mock arguments using typer.testing.CliRunner."""

import pytest
from unittest.mock import patch

from typer.testing import CliRunner

from nanopore_simulator.cli.main import app

runner = CliRunner()


class TestCLISpeciesArgs:

    def test_species_argument(self, tmp_path):
        """Test --species argument passes species_inputs to config."""
        with patch("nanopore_simulator.cli.main.NanoporeSimulator") as mock_sim:
            mock_sim.return_value.run_simulation.return_value = None
            result = runner.invoke(app, [
                "generate", "--target", str(tmp_path),
                "--species", "Escherichia coli",
            ])
            assert result.exit_code == 0, result.output
            config = mock_sim.call_args[0][0]
            assert config.species_inputs == ["Escherichia coli"]

    def test_multiple_species(self, tmp_path):
        """Test --species with multiple species names using repeated flags."""
        with patch("nanopore_simulator.cli.main.NanoporeSimulator") as mock_sim:
            mock_sim.return_value.run_simulation.return_value = None
            result = runner.invoke(app, [
                "generate", "--target", str(tmp_path),
                "--species", "E. coli",
                "--species", "S. aureus",
            ])
            assert result.exit_code == 0, result.output
            config = mock_sim.call_args[0][0]
            assert len(config.species_inputs) == 2
            assert "E. coli" in config.species_inputs
            assert "S. aureus" in config.species_inputs

    def test_mock_argument(self, tmp_path):
        """Test --mock argument passes mock_name to config."""
        with patch("nanopore_simulator.cli.main.NanoporeSimulator") as mock_sim:
            mock_sim.return_value.run_simulation.return_value = None
            result = runner.invoke(app, [
                "generate", "--target", str(tmp_path),
                "--mock", "zymo_d6300",
            ])
            assert result.exit_code == 0, result.output
            config = mock_sim.call_args[0][0]
            assert config.mock_name == "zymo_d6300"

    def test_sample_type_argument(self, tmp_path):
        """Test --sample-type argument passes sample_type to config."""
        with patch("nanopore_simulator.cli.main.NanoporeSimulator") as mock_sim:
            mock_sim.return_value.run_simulation.return_value = None
            result = runner.invoke(app, [
                "generate", "--target", str(tmp_path),
                "--species", "E. coli",
                "--sample-type", "mixed",
            ])
            assert result.exit_code == 0, result.output
            config = mock_sim.call_args[0][0]
            assert config.sample_type == "mixed"

    def test_abundances_argument(self, tmp_path):
        """Test --abundances argument passes abundances to config."""
        with patch("nanopore_simulator.cli.main.NanoporeSimulator") as mock_sim:
            mock_sim.return_value.run_simulation.return_value = None
            result = runner.invoke(app, [
                "generate", "--target", str(tmp_path),
                "--species", "E. coli",
                "--species", "S. aureus",
                "--sample-type", "mixed",
                "--abundances", "0.7",
                "--abundances", "0.3",
            ])
            assert result.exit_code == 0, result.output
            config = mock_sim.call_args[0][0]
            assert config.abundances == [0.7, 0.3]

    def test_taxid_argument(self, tmp_path):
        """Test --taxid argument passes taxid_inputs to config."""
        with patch("nanopore_simulator.cli.main.NanoporeSimulator") as mock_sim:
            mock_sim.return_value.run_simulation.return_value = None
            result = runner.invoke(app, [
                "generate", "--target", str(tmp_path),
                "--taxid", "562",
                "--taxid", "1280",
            ])
            assert result.exit_code == 0, result.output
            config = mock_sim.call_args[0][0]
            assert config.taxid_inputs == [562, 1280]

    def test_offline_argument(self, tmp_path):
        """Test --offline argument passes offline_mode to config."""
        with patch("nanopore_simulator.cli.main.NanoporeSimulator") as mock_sim:
            mock_sim.return_value.run_simulation.return_value = None
            result = runner.invoke(app, [
                "generate", "--target", str(tmp_path),
                "--species", "E. coli",
                "--offline",
            ])
            assert result.exit_code == 0, result.output
            config = mock_sim.call_args[0][0]
            assert config.offline_mode is True

    def test_list_mocks_command(self):
        """Test list-mocks command lists available mocks."""
        result = runner.invoke(app, ["list-mocks"])
        assert result.exit_code == 0
        assert "zymo_d6300" in result.output
        assert "Available Mock Communities" in result.output

    def test_species_and_mock_mutually_exclusive(self, tmp_path):
        """Test --species and --mock are mutually exclusive."""
        result = runner.invoke(app, [
            "generate", "--target", str(tmp_path),
            "--species", "E. coli",
            "--mock", "zymo_d6300",
        ])
        assert result.exit_code != 0

    def test_species_and_genomes_mutually_exclusive(self, tmp_path):
        """Test --species and --genomes are mutually exclusive."""
        genome_file = tmp_path / "genome.fa"
        genome_file.write_text(">seq1\nACGT\n")
        result = runner.invoke(app, [
            "generate", "--target", str(tmp_path),
            "--species", "E. coli",
            "--genomes", str(genome_file),
        ])
        assert result.exit_code != 0

    def test_mock_and_taxid_mutually_exclusive(self, tmp_path):
        """Test --mock and --taxid are mutually exclusive."""
        result = runner.invoke(app, [
            "generate", "--target", str(tmp_path),
            "--mock", "zymo_d6300",
            "--taxid", "562",
        ])
        assert result.exit_code != 0

    def test_species_sets_generate_operation(self, tmp_path):
        """Test that --species sets operation to generate."""
        with patch("nanopore_simulator.cli.main.NanoporeSimulator") as mock_sim:
            mock_sim.return_value.run_simulation.return_value = None
            result = runner.invoke(app, [
                "generate", "--target", str(tmp_path),
                "--species", "E. coli",
            ])
            assert result.exit_code == 0, result.output
            config = mock_sim.call_args[0][0]
            assert config.operation == "generate"

    def test_mock_sets_generate_operation(self, tmp_path):
        """Test that --mock sets operation to generate."""
        with patch("nanopore_simulator.cli.main.NanoporeSimulator") as mock_sim:
            mock_sim.return_value.run_simulation.return_value = None
            result = runner.invoke(app, [
                "generate", "--target", str(tmp_path),
                "--mock", "zymo_d6300",
            ])
            assert result.exit_code == 0, result.output
            config = mock_sim.call_args[0][0]
            assert config.operation == "generate"

    def test_species_with_profile(self, tmp_path):
        """Test --species works with --profile."""
        with patch("nanopore_simulator.cli.main.NanoporeSimulator") as mock_sim:
            mock_sim.return_value.run_simulation.return_value = None
            result = runner.invoke(app, [
                "generate", "--target", str(tmp_path),
                "--species", "E. coli",
                "--profile", "generate_test",
            ])
            assert result.exit_code == 0, result.output
            config = mock_sim.call_args[0][0]
            assert config.species_inputs == ["E. coli"]
            assert config.operation == "generate"


class TestListMocksOutput:

    def test_list_mocks_shows_aliases_section(self):
        """list-mocks should show aliases in a separate section."""
        result = runner.invoke(app, ["list-mocks"])
        assert result.exit_code == 0
        assert "\nAliases:" in result.output
