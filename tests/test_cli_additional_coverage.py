"""Additional CLI tests for remaining coverage gaps."""

import builtins
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from nanopore_simulator.cli.main import app, validate_pipeline_command

runner = CliRunner()


class TestCLIAdditionalCoverage:
    """Test remaining uncovered CLI code paths."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.source_dir = self.temp_path / "source"
        self.target_dir = self.temp_path / "target"
        self.source_dir.mkdir()
        (self.source_dir / "sample.fastq").write_text("@read1\nACGT\n+\nIIII\n")

    def teardown_method(self):
        """Clean up test fixtures."""
        self.temp_dir.cleanup()

    def test_validate_pipeline_with_warnings_and_errors(self, capsys):
        """Test validate_pipeline_command with warnings and errors."""
        with patch(
            "nanopore_simulator.cli.main.validate_for_pipeline"
        ) as mock_validate:
            mock_validate.return_value = {
                "valid": False,
                "files_found": [
                    "file1.fastq",
                    "file2.fastq",
                    "file3.fastq",
                    "file4.fastq",
                    "file5.fastq",
                    "file6.fastq",
                ],
                "warnings": ["Warning 1", "Warning 2"],
                "errors": ["Error 1", "Error 2"],
            }

            result = validate_pipeline_command(self.temp_path, "test_pipeline")

            captured = capsys.readouterr()
            assert result == 1
            assert "Files found: 6" in captured.out
            assert "... and 1 more" in captured.out
            assert "Warnings:" in captured.out
            assert "Warning: Warning 1" in captured.out
            assert "Errors:" in captured.out
            assert "Error: Error 1" in captured.out

    def test_cli_argument_validation_invalid_random_factor(self):
        """Test CLI rejects random factor outside 0.0-1.0 range."""
        result = runner.invoke(app, [
            "replay",
            "--source", str(self.source_dir),
            "--target", str(self.target_dir),
            "--random-factor", "2.0",
        ])

        assert result.exit_code == 2

    def test_cli_argument_validation_invalid_burst_probability(self):
        """Test CLI rejects burst probability outside 0.0-1.0 range."""
        result = runner.invoke(app, [
            "replay",
            "--source", str(self.source_dir),
            "--target", str(self.target_dir),
            "--burst-probability", "1.5",
        ])

        assert result.exit_code == 2

    def test_cli_argument_validation_invalid_burst_rate_multiplier(self):
        """Test CLI rejects negative burst rate multiplier."""
        result = runner.invoke(app, [
            "replay",
            "--source", str(self.source_dir),
            "--target", str(self.target_dir),
            "--burst-rate-multiplier", "-1.0",
        ])

        assert result.exit_code == 2

    def test_cli_nonexistent_source_directory(self):
        """Test CLI with nonexistent source directory."""
        result = runner.invoke(app, [
            "replay",
            "--source", "/nonexistent/source",
            "--target", "/some/target",
        ])

        assert result.exit_code == 2

    def test_cli_profile_configuration_building(self):
        """Test profile configuration with various overrides."""
        with patch(
            "nanopore_simulator.cli.main.validate_profile_name",
            return_value=True,
        ):
            with patch(
                "nanopore_simulator.cli.main.create_config_from_profile"
            ) as mock_create:
                with patch(
                    "nanopore_simulator.cli.main.NanoporeSimulator"
                ) as mock_sim_class:
                    mock_sim = MagicMock()
                    mock_sim_class.return_value = mock_sim

                    result = runner.invoke(app, [
                        "replay",
                        "--source", str(self.source_dir),
                        "--target", str(self.target_dir),
                        "--profile", "bursty",
                        "--timing-model", "random",
                        "--random-factor", "0.3",
                        "--operation", "link",
                        "--batch-size", "5",
                        "--parallel",
                        "--worker-count", "8",
                        "--force-structure", "multiplex",
                    ])

                    assert result.exit_code == 0, result.output

                    mock_create.assert_called_once()
                    call_args = mock_create.call_args
                    overrides = call_args.kwargs
                    assert overrides["timing_model"] == "random"
                    assert overrides["timing_model_params"]["random_factor"] == 0.3
                    assert overrides["operation"] == "link"
                    assert overrides["batch_size"] == 5
                    assert overrides["parallel_processing"] is True
                    assert overrides["worker_count"] == 8
                    assert overrides["force_structure"] == "multiplex"

    def test_cli_standard_configuration_with_timing_params(self):
        """Test standard configuration building with timing parameters."""
        with patch(
            "nanopore_simulator.cli.main.SimulationConfig"
        ) as mock_config:
            with patch(
                "nanopore_simulator.cli.main.NanoporeSimulator"
            ) as mock_sim_class:
                mock_sim = MagicMock()
                mock_sim_class.return_value = mock_sim

                result = runner.invoke(app, [
                    "replay",
                    "--source", str(self.source_dir),
                    "--target", str(self.target_dir),
                    "--timing-model", "random",
                    "--random-factor", "0.4",
                ])

                assert result.exit_code == 0, result.output

                mock_config.assert_called_once()
                call_args = mock_config.call_args
                assert call_args.kwargs["timing_model"] == "random"
                assert call_args.kwargs["timing_model_params"]["random_factor"] == 0.4

    def test_cli_enhanced_monitoring_without_psutil(self):
        """Test enhanced monitoring fallback when psutil unavailable."""
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "psutil":
                raise ImportError("No module named 'psutil'")
            return original_import(name, *args, **kwargs)

        with patch(
            "nanopore_simulator.cli.main.NanoporeSimulator"
        ) as mock_sim_class:
            mock_sim = MagicMock()
            mock_sim_class.return_value = mock_sim

            with patch("builtins.__import__", side_effect=mock_import):
                result = runner.invoke(app, [
                    "replay",
                    "--source", str(self.source_dir),
                    "--target", str(self.target_dir),
                    "--monitor", "enhanced",
                ])

            assert result.exit_code == 0, result.output
            assert "Warning: Enhanced monitoring requires psutil" in result.output
            assert "Falling back to detailed monitoring mode" in result.output

            mock_sim_class.assert_called_once()
            args = mock_sim_class.call_args[0]
            assert args[2] == "detailed"

    def test_cli_enhanced_monitoring_instructions(self):
        """Test enhanced monitoring instructions are printed."""
        with patch(
            "nanopore_simulator.cli.main.NanoporeSimulator"
        ) as mock_sim_class:
            mock_sim = MagicMock()
            mock_sim_class.return_value = mock_sim

            result = runner.invoke(app, [
                "replay",
                "--source", str(self.source_dir),
                "--target", str(self.target_dir),
                "--monitor", "enhanced",
            ])

            assert result.exit_code == 0, result.output
            assert "Enhanced monitoring active. Interactive controls:" in result.output
            assert "Ctrl+C: Graceful shutdown with summary" in result.output
            assert "SIGTERM: Graceful shutdown" in result.output
            assert "Progress is automatically checkpointed" in result.output

    def test_cli_post_simulation_pipeline_validation_success(self):
        """Test post-simulation pipeline validation with valid output."""
        with patch(
            "nanopore_simulator.cli.main.NanoporeSimulator"
        ) as mock_sim_class:
            with patch(
                "nanopore_simulator.cli.main.validate_for_pipeline"
            ) as mock_validate:
                mock_sim = MagicMock()
                mock_sim_class.return_value = mock_sim
                mock_validate.return_value = {"valid": True}

                result = runner.invoke(app, [
                    "replay",
                    "--source", str(self.source_dir),
                    "--target", str(self.target_dir),
                    "--pipeline", "nanometanf",
                ])

                assert result.exit_code == 0, result.output
                assert "Validating output for nanometanf pipeline" in result.output
                assert "Output is compatible with nanometanf pipeline" in result.output

    def test_cli_post_simulation_pipeline_validation_failure(self):
        """Test post-simulation pipeline validation with warnings."""
        with patch(
            "nanopore_simulator.cli.main.NanoporeSimulator"
        ) as mock_sim_class:
            with patch(
                "nanopore_simulator.cli.main.validate_for_pipeline"
            ) as mock_validate:
                mock_sim = MagicMock()
                mock_sim_class.return_value = mock_sim
                mock_validate.return_value = {
                    "valid": False,
                    "warnings": [
                        "Missing required files",
                        "Incorrect structure",
                    ],
                }

                result = runner.invoke(app, [
                    "replay",
                    "--source", str(self.source_dir),
                    "--target", str(self.target_dir),
                    "--pipeline", "kraken",
                ])

                assert result.exit_code == 0, result.output
                assert (
                    "Output may not be compatible with kraken pipeline"
                    in result.output
                )
                assert "Warning: Missing required files" in result.output
                assert "Warning: Incorrect structure" in result.output

    def test_cli_keyboard_interrupt_handling(self):
        """Test KeyboardInterrupt handling during simulation."""
        with patch(
            "nanopore_simulator.cli.main.NanoporeSimulator"
        ) as mock_sim_class:
            mock_sim = MagicMock()
            mock_sim.run_simulation.side_effect = KeyboardInterrupt()
            mock_sim_class.return_value = mock_sim

            result = runner.invoke(app, [
                "replay",
                "--source", str(self.source_dir),
                "--target", str(self.target_dir),
            ])

            assert result.exit_code == 1
            assert "Simulation interrupted by user" in result.output

    def test_cli_no_args_shows_help(self):
        """Test CLI with no arguments shows help and exits cleanly."""
        result = runner.invoke(app, [])

        assert result.exit_code == 0

    def test_cli_missing_target_arg(self):
        """Test CLI error when --target is not provided for replay."""
        result = runner.invoke(app, [
            "replay",
            "--source", str(self.source_dir),
        ])

        assert result.exit_code != 0


class TestCLIArgumentCombinations:
    """Test argument combinations for edge cases."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.source_dir = self.temp_path / "source"
        self.target_dir = self.temp_path / "target"
        self.source_dir.mkdir()
        (self.source_dir / "sample.fastq").write_text("@read1\nACGT\n+\nIIII\n")

    def teardown_method(self):
        """Clean up test fixtures."""
        self.temp_dir.cleanup()

    def test_cli_profile_with_partial_timing_overrides(self):
        """Test profile with only some timing parameters overridden."""
        with patch(
            "nanopore_simulator.cli.main.validate_profile_name",
            return_value=True,
        ):
            with patch(
                "nanopore_simulator.cli.main.create_config_from_profile"
            ) as mock_create:
                with patch(
                    "nanopore_simulator.cli.main.NanoporeSimulator"
                ) as mock_sim_class:
                    mock_sim = MagicMock()
                    mock_sim_class.return_value = mock_sim

                    result = runner.invoke(app, [
                        "replay",
                        "--source", str(self.source_dir),
                        "--target", str(self.target_dir),
                        "--profile", "bursty",
                        "--burst-probability", "0.3",
                    ])

                    assert result.exit_code == 0, result.output

                    call_args = mock_create.call_args
                    overrides = call_args.kwargs
                    assert "timing_model" not in overrides
                    assert overrides["timing_model_params"]["burst_probability"] == 0.3

    def test_cli_poisson_timing_with_standard_config(self):
        """Test Poisson timing model parameters with standard configuration."""
        with patch(
            "nanopore_simulator.cli.main.SimulationConfig"
        ) as mock_config:
            with patch(
                "nanopore_simulator.cli.main.NanoporeSimulator"
            ) as mock_sim_class:
                mock_sim = MagicMock()
                mock_sim_class.return_value = mock_sim

                result = runner.invoke(app, [
                    "replay",
                    "--source", str(self.source_dir),
                    "--target", str(self.target_dir),
                    "--timing-model", "poisson",
                    "--burst-probability", "0.15",
                    "--burst-rate-multiplier", "2.5",
                ])

                assert result.exit_code == 0, result.output

                call_args = mock_config.call_args
                timing_params = call_args.kwargs["timing_model_params"]
                assert timing_params["burst_probability"] == 0.15
                assert timing_params["burst_rate_multiplier"] == 2.5
