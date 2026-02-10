"""Tests for command line interface"""

import pytest
import tempfile
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from io import StringIO

from nanopore_simulator.cli.main import main


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
        with patch.object(
            sys, "argv", ["nanorunner", str(self.source_dir), str(self.target_dir)]
        ):
            result = main()

            assert result == 0
            assert (self.target_dir / "sample.fastq").exists()

    def test_cli_with_all_options(self):
        """Test CLI with all optional arguments"""
        with patch.object(
            sys,
            "argv",
            [
                "nanorunner",
                str(self.source_dir),
                str(self.target_dir),
                "--interval",
                "1.5",
                "--operation",
                "link",
                "--force-structure",
                "singleplex",
                "--batch-size",
                "3",
            ],
        ):
            result = main()

            assert result == 0
            target_file = self.target_dir / "sample.fastq"
            assert target_file.exists()
            assert target_file.is_symlink()

    def test_cli_nonexistent_source_directory(self):
        """Test CLI error handling for nonexistent source directory"""
        nonexistent_dir = self.temp_path / "nonexistent"

        with patch.object(
            sys, "argv", ["nanorunner", str(nonexistent_dir), str(self.target_dir)]
        ):
            with patch("sys.stderr", new_callable=StringIO):
                with pytest.raises(SystemExit) as excinfo:
                    main()

                # argparse exits with code 2 for argument errors
                assert excinfo.value.code == 2

    def test_cli_help_option(self):
        """Test CLI help option"""
        with patch.object(sys, "argv", ["nanorunner", "--help"]):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with pytest.raises(SystemExit) as excinfo:
                    main()

                # Help should exit with code 0
                assert excinfo.value.code == 0

                # Check help content
                help_output = mock_stdout.getvalue()
                assert "Nanopore sequencing run simulator" in help_output
                assert "--interval" in help_output
                assert "--operation" in help_output

    def test_cli_version_option(self):
        """Test CLI version option"""
        with patch.object(sys, "argv", ["nanorunner", "--version"]):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with pytest.raises(SystemExit) as excinfo:
                    main()

                assert excinfo.value.code == 0
                version_output = mock_stdout.getvalue()
                assert "2.0.2" in version_output

    def test_cli_invalid_operation(self):
        """Test CLI with invalid operation argument"""
        with patch.object(
            sys,
            "argv",
            [
                "nanorunner",
                str(self.source_dir),
                str(self.target_dir),
                "--operation",
                "invalid_operation",
            ],
        ):
            with patch("sys.stderr", new_callable=StringIO):
                with pytest.raises(SystemExit) as excinfo:
                    main()

                assert excinfo.value.code == 2

    def test_cli_invalid_force_structure(self):
        """Test CLI with invalid force-structure argument"""
        with patch.object(
            sys,
            "argv",
            [
                "nanorunner",
                str(self.source_dir),
                str(self.target_dir),
                "--force-structure",
                "invalid_structure",
            ],
        ):
            with patch("sys.stderr", new_callable=StringIO):
                with pytest.raises(SystemExit) as excinfo:
                    main()

                assert excinfo.value.code == 2

    def test_cli_keyboard_interrupt(self):
        """Test CLI handling of keyboard interrupt"""
        with patch.object(
            sys, "argv", ["nanorunner", str(self.source_dir), str(self.target_dir)]
        ):
            with patch(
                "nanopore_simulator.cli.main.NanoporeSimulator"
            ) as mock_simulator:
                mock_instance = MagicMock()
                mock_instance.run_simulation.side_effect = KeyboardInterrupt()
                mock_simulator.return_value = mock_instance

                with patch("builtins.print") as mock_print:
                    result = main()

                    assert result == 1  # Should return 1 for user interruption
                    mock_print.assert_called_with("\nSimulation interrupted by user")

    def test_cli_general_exception(self):
        """Test CLI handling of general exceptions"""
        with patch.object(
            sys, "argv", ["nanorunner", str(self.source_dir), str(self.target_dir)]
        ):
            with patch(
                "nanopore_simulator.cli.main.NanoporeSimulator"
            ) as mock_simulator:
                mock_instance = MagicMock()
                mock_instance.run_simulation.side_effect = Exception("Test error")
                mock_simulator.return_value = mock_instance

                with patch("builtins.print") as mock_print:
                    result = main()

                    assert result == 1  # Should return 1 for errors
                    mock_print.assert_called_with("Error: Test error")

    def test_cli_float_interval(self):
        """Test CLI with float interval value"""
        with patch.object(
            sys,
            "argv",
            [
                "nanorunner",
                str(self.source_dir),
                str(self.target_dir),
                "--interval",
                "2.5",
            ],
        ):
            result = main()
            assert result == 0

    def test_cli_integer_batch_size(self):
        """Test CLI with integer batch size"""
        with patch.object(
            sys,
            "argv",
            [
                "nanorunner",
                str(self.source_dir),
                str(self.target_dir),
                "--batch-size",
                "5",
            ],
        ):
            result = main()
            assert result == 0

    def test_cli_multiplex_structure(self):
        """Test CLI with multiplex test data"""
        # Create multiplex structure
        barcode_dir = self.source_dir / "barcode01"
        barcode_dir.mkdir()
        (barcode_dir / "reads.fastq").write_text("multiplex content")

        # Remove singleplex file
        (self.source_dir / "sample.fastq").unlink()

        with patch.object(
            sys,
            "argv",
            [
                "nanorunner",
                str(self.source_dir),
                str(self.target_dir),
                "--operation",
                "copy",
            ],
        ):
            result = main()

            assert result == 0
            assert (self.target_dir / "barcode01" / "reads.fastq").exists()
            assert (
                self.target_dir / "barcode01" / "reads.fastq"
            ).read_text() == "multiplex content"

    def test_cli_module_execution(self):
        """Test that CLI can be executed as a module"""
        # Test that the module has the main function
        from nanopore_simulator.cli.main import main as cli_main

        assert callable(cli_main)

        # Test direct function call with mock args
        with patch.object(sys, "argv", ["nanorunner", "--help"]):
            with patch("sys.stdout", new_callable=StringIO):
                with pytest.raises(SystemExit):
                    cli_main()

    def test_cli_path_conversion(self):
        """Test that CLI properly converts string paths to Path objects"""
        with patch.object(
            sys, "argv", ["nanorunner", str(self.source_dir), str(self.target_dir)]
        ):
            with patch(
                "nanopore_simulator.cli.main.NanoporeSimulator"
            ) as mock_simulator:
                main()

                # Check that SimulationConfig was called with Path objects
                call_args = mock_simulator.call_args[0][0]  # First argument (config)
                assert isinstance(call_args.source_dir, Path)
                assert isinstance(call_args.target_dir, Path)
