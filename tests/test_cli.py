"""Tests for command line interface using typer.testing.CliRunner"""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from typer.testing import CliRunner

from nanopore_simulator.cli.main import app


runner = CliRunner()


class TestCLI:

    def setup_method(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

        # Create test source structure
        self.source_dir = self.temp_path / "source"
        self.target_dir = self.temp_path / "target"
        self.source_dir.mkdir()

        # Create test files
        (self.source_dir / "sample.fastq").write_text("test content")

    def teardown_method(self):
        """Clean up test fixtures"""
        self.temp_dir.cleanup()

    def test_basic_cli_execution(self):
        """Test basic CLI execution with minimal arguments"""
        result = runner.invoke(app, [
            "replay",
            "--source", str(self.source_dir),
            "--target", str(self.target_dir),
        ])

        assert result.exit_code == 0
        assert (self.target_dir / "sample.fastq").exists()

    def test_cli_with_all_options(self):
        """Test CLI with all optional arguments"""
        result = runner.invoke(app, [
            "replay",
            "--source", str(self.source_dir),
            "--target", str(self.target_dir),
            "--interval", "1.5",
            "--operation", "link",
            "--force-structure", "singleplex",
            "--batch-size", "3",
        ])

        assert result.exit_code == 0
        target_file = self.target_dir / "sample.fastq"
        assert target_file.exists()
        assert target_file.is_symlink()

    def test_cli_nonexistent_source_directory(self):
        """Test CLI error handling for nonexistent source directory"""
        nonexistent_dir = self.temp_path / "nonexistent"

        result = runner.invoke(app, [
            "replay",
            "--source", str(nonexistent_dir),
            "--target", str(self.target_dir),
        ])

        assert result.exit_code != 0

    def test_cli_help_option(self):
        """Test CLI help option"""
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0

        # Check top-level help content
        assert "replay" in result.output
        assert "generate" in result.output

    def test_cli_replay_help_option(self):
        """Test CLI replay subcommand help option"""
        result = runner.invoke(app, ["replay", "--help"])

        assert result.exit_code == 0

        # Check replay help content
        assert "--source" in result.output
        assert "--target" in result.output
        assert "--interval" in result.output
        assert "--operation" in result.output

    def test_cli_version_option(self):
        """Test CLI version option"""
        result = runner.invoke(app, ["--version"])

        assert result.exit_code == 0
        assert "2.0.2" in result.output

    def test_cli_invalid_operation(self):
        """Test CLI with invalid operation argument"""
        result = runner.invoke(app, [
            "replay",
            "--source", str(self.source_dir),
            "--target", str(self.target_dir),
            "--operation", "invalid_operation",
        ])

        assert result.exit_code == 2

    def test_cli_invalid_force_structure(self):
        """Test CLI with invalid force-structure argument"""
        result = runner.invoke(app, [
            "replay",
            "--source", str(self.source_dir),
            "--target", str(self.target_dir),
            "--force-structure", "invalid_structure",
        ])

        assert result.exit_code == 2

    def test_cli_keyboard_interrupt(self):
        """Test CLI handling of keyboard interrupt"""
        with patch(
            "nanopore_simulator.cli.main.NanoporeSimulator"
        ) as mock_simulator:
            mock_instance = MagicMock()
            mock_instance.run_simulation.side_effect = KeyboardInterrupt()
            mock_simulator.return_value = mock_instance

            result = runner.invoke(app, [
                "replay",
                "--source", str(self.source_dir),
                "--target", str(self.target_dir),
            ])

            assert result.exit_code == 1
            assert "Simulation interrupted by user" in result.output

    def test_cli_general_exception(self):
        """Test CLI handling of general exceptions"""
        with patch(
            "nanopore_simulator.cli.main.NanoporeSimulator"
        ) as mock_simulator:
            mock_instance = MagicMock()
            mock_instance.run_simulation.side_effect = Exception("Test error")
            mock_simulator.return_value = mock_instance

            result = runner.invoke(app, [
                "replay",
                "--source", str(self.source_dir),
                "--target", str(self.target_dir),
            ])

            assert result.exit_code == 1
            assert "Error: Test error" in result.output

    def test_cli_float_interval(self):
        """Test CLI with float interval value"""
        result = runner.invoke(app, [
            "replay",
            "--source", str(self.source_dir),
            "--target", str(self.target_dir),
            "--interval", "2.5",
        ])

        assert result.exit_code == 0

    def test_cli_integer_batch_size(self):
        """Test CLI with integer batch size"""
        result = runner.invoke(app, [
            "replay",
            "--source", str(self.source_dir),
            "--target", str(self.target_dir),
            "--batch-size", "5",
        ])

        assert result.exit_code == 0

    def test_cli_multiplex_structure(self):
        """Test CLI with multiplex test data"""
        # Create multiplex structure
        barcode_dir = self.source_dir / "barcode01"
        barcode_dir.mkdir()
        (barcode_dir / "reads.fastq").write_text("multiplex content")

        # Remove singleplex file
        (self.source_dir / "sample.fastq").unlink()

        result = runner.invoke(app, [
            "replay",
            "--source", str(self.source_dir),
            "--target", str(self.target_dir),
            "--operation", "copy",
        ])

        assert result.exit_code == 0
        assert (self.target_dir / "barcode01" / "reads.fastq").exists()
        assert (
            self.target_dir / "barcode01" / "reads.fastq"
        ).read_text() == "multiplex content"

    def test_cli_module_execution(self):
        """Test that CLI can be executed as a module"""
        # Test that the app is callable
        from nanopore_simulator.cli.main import app as cli_app

        assert cli_app is not None

        # Test help via CliRunner
        result = runner.invoke(cli_app, ["--help"])
        assert result.exit_code == 0

    def test_cli_path_conversion(self):
        """Test that CLI properly converts string paths to Path objects"""
        with patch(
            "nanopore_simulator.cli.main.NanoporeSimulator"
        ) as mock_simulator:
            mock_instance = MagicMock()
            mock_simulator.return_value = mock_instance

            result = runner.invoke(app, [
                "replay",
                "--source", str(self.source_dir),
                "--target", str(self.target_dir),
            ])

            assert result.exit_code == 0

            # Check that SimulationConfig was called with Path objects
            call_args = mock_simulator.call_args[0][0]  # First argument (config)
            assert isinstance(call_args.source_dir, Path)
            assert isinstance(call_args.target_dir, Path)
