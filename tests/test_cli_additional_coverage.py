"""Additional CLI tests for remaining coverage gaps"""

import pytest
import tempfile
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from io import StringIO

from nanopore_simulator.cli.main import validate_pipeline_command, main


class TestCLIAdditionalCoverage:
    """Test remaining uncovered CLI code paths"""

    def test_validate_pipeline_with_warnings_and_errors(self, capsys):
        """Test validate_pipeline_command with warnings and errors"""
        with tempfile.TemporaryDirectory() as temp_dir:
            target_dir = Path(temp_dir)

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

                result = validate_pipeline_command(target_dir, "test_pipeline")

                captured = capsys.readouterr()
                assert result == 1
                assert "Files found: 6" in captured.out
                assert "... and 1 more" in captured.out
                assert "Warnings:" in captured.out
                assert "⚠ Warning 1" in captured.out
                assert "Errors:" in captured.out
                assert "✗ Error 1" in captured.out

    def test_cli_argument_validation_errors(self):
        """Test CLI argument validation that triggers parser.error"""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            target_dir = Path(temp_dir) / "output"

            # Create sample file
            (source_dir / "sample.fastq").write_text("@read1\\nACGT\\n+\\nIIII\\n")

            # Test invalid random factor
            with patch.object(
                sys,
                "argv",
                [
                    "nanorunner",
                    str(source_dir),
                    str(target_dir),
                    "--random-factor",
                    "2.0",  # Invalid, must be 0.0-1.0
                ],
            ):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 2

            # Test invalid burst probability
            with patch.object(
                sys,
                "argv",
                [
                    "nanorunner",
                    str(source_dir),
                    str(target_dir),
                    "--burst-probability",
                    "1.5",  # Invalid, must be 0.0-1.0
                ],
            ):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 2

            # Test invalid burst rate multiplier
            with patch.object(
                sys,
                "argv",
                [
                    "nanorunner",
                    str(source_dir),
                    str(target_dir),
                    "--burst-rate-multiplier",
                    "-1.0",  # Invalid, must be positive
                ],
            ):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 2

    def test_cli_nonexistent_source_directory(self):
        """Test CLI with nonexistent source directory"""
        with patch.object(
            sys, "argv", ["nanorunner", "/nonexistent/source", "/some/target"]
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 2

    def test_cli_profile_configuration_building(self):
        """Test profile configuration with various overrides"""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            target_dir = Path(temp_dir) / "output"

            # Create sample file
            (source_dir / "sample.fastq").write_text("@read1\\nACGT\\n+\\nIIII\\n")

            with patch.object(
                sys,
                "argv",
                [
                    "nanorunner",
                    str(source_dir),
                    str(target_dir),
                    "--profile",
                    "rapid_sequencing",
                    "--timing-model",
                    "random",
                    "--random-factor",
                    "0.3",
                    "--operation",
                    "link",
                    "--batch-size",
                    "5",
                    "--parallel",
                    "--worker-count",
                    "8",
                    "--force-structure",
                    "multiplex",
                ],
            ):
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

                            result = main()
                            assert result == 0

                            # Verify the config was created with overrides
                            mock_create.assert_called_once()
                            call_args = mock_create.call_args
                            overrides = call_args.kwargs
                            assert overrides["timing_model"] == "random"
                            assert (
                                overrides["timing_model_params"]["random_factor"] == 0.3
                            )
                            assert overrides["operation"] == "link"
                            assert overrides["batch_size"] == 5
                            assert overrides["parallel_processing"] is True
                            assert overrides["worker_count"] == 8
                            assert overrides["force_structure"] == "multiplex"

    def test_cli_standard_configuration_with_timing_params(self):
        """Test standard configuration building with timing parameters"""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            target_dir = Path(temp_dir) / "output"

            # Create sample file
            (source_dir / "sample.fastq").write_text("@read1\\nACGT\\n+\\nIIII\\n")

            with patch.object(
                sys,
                "argv",
                [
                    "nanorunner",
                    str(source_dir),
                    str(target_dir),
                    "--timing-model",
                    "random",
                    "--random-factor",
                    "0.4",
                ],
            ):
                with patch(
                    "nanopore_simulator.cli.main.SimulationConfig"
                ) as mock_config:
                    with patch(
                        "nanopore_simulator.cli.main.NanoporeSimulator"
                    ) as mock_sim_class:
                        mock_sim = MagicMock()
                        mock_sim_class.return_value = mock_sim

                        result = main()
                        assert result == 0

                        # Verify the config was created with timing params
                        mock_config.assert_called_once()
                        call_args = mock_config.call_args
                        assert call_args.kwargs["timing_model"] == "random"
                        assert (
                            call_args.kwargs["timing_model_params"]["random_factor"]
                            == 0.4
                        )

    def test_cli_enhanced_monitoring_without_psutil(self, capsys):
        """Test enhanced monitoring fallback when psutil unavailable"""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            target_dir = Path(temp_dir) / "output"

            # Create sample file
            (source_dir / "sample.fastq").write_text("@read1\\nACGT\\n+\\nIIII\\n")

            with patch.object(
                sys,
                "argv",
                [
                    "nanorunner",
                    str(source_dir),
                    str(target_dir),
                    "--monitor",
                    "enhanced",
                ],
            ):
                # Mock psutil import failure more carefully to avoid recursion
                original_import = __builtins__["__import__"]

                def mock_import(name, *args, **kwargs):
                    if name == "psutil":
                        raise ImportError("No module named 'psutil'")
                    return original_import(name, *args, **kwargs)

                with patch("builtins.__import__", side_effect=mock_import):
                    with patch(
                        "nanopore_simulator.cli.main.NanoporeSimulator"
                    ) as mock_sim_class:
                        mock_sim = MagicMock()
                        mock_sim_class.return_value = mock_sim

                        result = main()
                        assert result == 0

                        captured = capsys.readouterr()
                        assert (
                            "Warning: Enhanced monitoring requires psutil"
                            in captured.out
                        )
                        assert (
                            "Falling back to detailed monitoring mode" in captured.out
                        )

                        # Verify simulator was created with detailed monitoring
                        mock_sim_class.assert_called_once()
                        args = mock_sim_class.call_args[0]
                        assert args[2] == "detailed"  # monitor_type

    def test_cli_enhanced_monitoring_instructions(self, capsys):
        """Test enhanced monitoring instructions are printed"""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            target_dir = Path(temp_dir) / "output"

            # Create sample file
            (source_dir / "sample.fastq").write_text("@read1\\nACGT\\n+\\nIIII\\n")

            with patch.object(
                sys,
                "argv",
                [
                    "nanorunner",
                    str(source_dir),
                    str(target_dir),
                    "--monitor",
                    "enhanced",
                ],
            ):
                with patch(
                    "nanopore_simulator.cli.main.NanoporeSimulator"
                ) as mock_sim_class:
                    mock_sim = MagicMock()
                    mock_sim_class.return_value = mock_sim

                    result = main()
                    assert result == 0

                    captured = capsys.readouterr()
                    assert (
                        "Enhanced monitoring active. Interactive controls:"
                        in captured.out
                    )
                    assert "Ctrl+C: Graceful shutdown with summary" in captured.out
                    assert "SIGTERM: Graceful shutdown" in captured.out
                    assert "Progress is automatically checkpointed" in captured.out

    def test_cli_post_simulation_pipeline_validation(self, capsys):
        """Test post-simulation pipeline validation"""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            target_dir = Path(temp_dir) / "output"

            # Create sample file
            (source_dir / "sample.fastq").write_text("@read1\\nACGT\\n+\\nIIII\\n")

            # Test successful validation
            with patch.object(
                sys,
                "argv",
                [
                    "nanorunner",
                    str(source_dir),
                    str(target_dir),
                    "--pipeline",
                    "nanometanf",
                ],
            ):
                with patch(
                    "nanopore_simulator.cli.main.NanoporeSimulator"
                ) as mock_sim_class:
                    with patch(
                        "nanopore_simulator.cli.main.validate_for_pipeline"
                    ) as mock_validate:
                        mock_sim = MagicMock()
                        mock_sim_class.return_value = mock_sim
                        mock_validate.return_value = {"valid": True}

                        result = main()
                        assert result == 0

                        captured = capsys.readouterr()
                        assert (
                            "Validating output for nanometanf pipeline" in captured.out
                        )
                        assert (
                            "✓ Output is compatible with nanometanf pipeline"
                            in captured.out
                        )

            # Test failed validation with warnings
            with patch.object(
                sys,
                "argv",
                [
                    "nanorunner",
                    str(source_dir),
                    str(target_dir),
                    "--pipeline",
                    "kraken",
                ],
            ):
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

                        result = main()
                        assert result == 0

                        captured = capsys.readouterr()
                        assert (
                            "✗ Output may not be compatible with kraken pipeline"
                            in captured.out
                        )
                        assert "⚠ Missing required files" in captured.out
                        assert "⚠ Incorrect structure" in captured.out

    def test_cli_keyboard_interrupt_handling(self, capsys):
        """Test KeyboardInterrupt handling in main function"""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            target_dir = Path(temp_dir) / "output"

            # Create sample file
            (source_dir / "sample.fastq").write_text("@read1\\nACGT\\n+\\nIIII\\n")

            with patch.object(
                sys, "argv", ["nanorunner", str(source_dir), str(target_dir)]
            ):
                with patch(
                    "nanopore_simulator.cli.main.NanoporeSimulator"
                ) as mock_sim_class:
                    mock_sim = MagicMock()
                    mock_sim.run_simulation.side_effect = KeyboardInterrupt()
                    mock_sim_class.return_value = mock_sim

                    result = main()
                    assert result == 1

                    captured = capsys.readouterr()
                    assert "Simulation interrupted by user" in captured.out

    def test_cli_no_args_shows_help(self):
        """Test CLI with no arguments shows help and exits cleanly"""
        with patch.object(sys, "argv", ["nanorunner"]):
            result = main()
            assert result == 0

    def test_cli_missing_target_arg(self):
        """Test CLI error when only source dir is provided"""
        with patch.object(sys, "argv", ["nanorunner", "/source"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 2


class TestCLIArgumentCombinations:
    """Test complex argument combinations for edge cases"""

    def test_cli_profile_with_partial_timing_overrides(self):
        """Test profile with only some timing parameters overridden"""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            target_dir = Path(temp_dir) / "output"

            # Create sample file
            (source_dir / "sample.fastq").write_text("@read1\\nACGT\\n+\\nIIII\\n")

            # Test with burst probability but no timing model override
            with patch.object(
                sys,
                "argv",
                [
                    "nanorunner",
                    str(source_dir),
                    str(target_dir),
                    "--profile",
                    "rapid_sequencing",
                    "--burst-probability",
                    "0.3",
                ],
            ):
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

                            result = main()
                            assert result == 0

                            # Verify timing model params are passed without timing model override
                            call_args = mock_create.call_args
                            overrides = call_args.kwargs
                            assert "timing_model" not in overrides
                            assert (
                                overrides["timing_model_params"]["burst_probability"]
                                == 0.3
                            )

    def test_cli_poisson_timing_with_standard_config(self):
        """Test Poisson timing model parameters with standard configuration"""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            target_dir = Path(temp_dir) / "output"

            # Create sample file
            (source_dir / "sample.fastq").write_text("@read1\\nACGT\\n+\\nIIII\\n")

            with patch.object(
                sys,
                "argv",
                [
                    "nanorunner",
                    str(source_dir),
                    str(target_dir),
                    "--timing-model",
                    "poisson",
                    "--burst-probability",
                    "0.15",
                    "--burst-rate-multiplier",
                    "2.5",
                ],
            ):
                with patch(
                    "nanopore_simulator.cli.main.SimulationConfig"
                ) as mock_config:
                    with patch(
                        "nanopore_simulator.cli.main.NanoporeSimulator"
                    ) as mock_sim_class:
                        mock_sim = MagicMock()
                        mock_sim_class.return_value = mock_sim

                        result = main()
                        assert result == 0

                        # Verify Poisson parameters are passed
                        call_args = mock_config.call_args
                        timing_params = call_args.kwargs["timing_model_params"]
                        assert timing_params["burst_probability"] == 0.15
                        assert timing_params["burst_rate_multiplier"] == 2.5
