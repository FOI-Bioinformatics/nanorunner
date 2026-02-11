"""Comprehensive CLI tests to improve coverage.

Uses typer.testing.CliRunner for CLI integration tests and direct function
calls for standalone command helpers.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from nanopore_simulator.cli.main import (
    app,
    list_profiles_command,
    list_adapters_command,
    recommend_profiles_command,
    validate_pipeline_command,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Direct function tests (standalone helpers, not routed through Typer)
# ---------------------------------------------------------------------------


class TestCLICommandFunctions:
    """Test individual CLI command functions called directly."""

    def test_list_profiles_command(self, capsys):
        """Test the list profiles command function."""
        with patch(
            "nanopore_simulator.cli.main.get_available_profiles"
        ) as mock_profiles:
            mock_profiles.return_value = {
                "rapid_sequencing": "Fast sequencing with short intervals",
                "development_testing": "Testing profile with rapid intervals",
            }

            result = list_profiles_command()

            captured = capsys.readouterr()
            assert result == 0
            assert "Available Configuration Profiles:" in captured.out
            assert "rapid_sequencing" in captured.out
            assert "development_testing" in captured.out
            assert "Fast sequencing with short intervals" in captured.out

    def test_list_adapters_command(self, capsys):
        """Test the list adapters command function."""
        with patch(
            "nanopore_simulator.cli.main.get_available_adapters"
        ) as mock_adapters:
            mock_adapters.return_value = {
                "nanometanf": "Real-time taxonomic classification pipeline",
                "kraken": "K-mer based taxonomic assignment",
                "generic": "Generic adapter for any pipeline",
            }

            result = list_adapters_command()

            captured = capsys.readouterr()
            assert result == 0
            assert "Available Pipeline Adapters:" in captured.out
            assert "nanometanf" in captured.out
            assert "kraken" in captured.out
            assert "generic" in captured.out
            assert "Real-time taxonomic classification pipeline" in captured.out

    def test_recommend_profiles_command_success(self, capsys):
        """Test recommend profiles command with valid directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)

            (source_dir / "sample1.fastq").write_text("@read1\\nACGT\\n+\\nIIII\\n")
            (source_dir / "sample2.fastq.gz").write_text("compressed_data")

            with patch(
                "nanopore_simulator.cli.main.get_profile_recommendations"
            ) as mock_rec:
                with patch(
                    "nanopore_simulator.cli.main.get_available_profiles"
                ) as mock_profiles:
                    mock_rec.return_value = [
                        "rapid_sequencing",
                        "development_testing",
                    ]
                    mock_profiles.return_value = {
                        "rapid_sequencing": "Fast sequencing",
                        "development_testing": "Testing profile",
                    }

                    result = recommend_profiles_command(source_dir)

                    captured = capsys.readouterr()
                    assert result == 0
                    assert f"Analysis of {source_dir}:" in captured.out
                    assert "Found 2 sequencing files" in captured.out
                    assert "Detected structure:" in captured.out
                    assert "Recommended profiles for 2 files:" in captured.out
                    assert "rapid_sequencing" in captured.out

    def test_recommend_profiles_command_nonexistent_dir(self, capsys):
        """Test recommend profiles command with nonexistent directory."""
        nonexistent_dir = Path("/nonexistent/directory/path")

        result = recommend_profiles_command(nonexistent_dir)

        captured = capsys.readouterr()
        assert result == 1
        assert "Error: Source directory does not exist" in captured.out

    def test_validate_pipeline_command_success(self, capsys):
        """Test validate pipeline command with valid directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            target_dir = Path(temp_dir)

            (target_dir / "sample.fastq").write_text("@read1\\nACGT\\n+\\nIIII\\n")

            with patch(
                "nanopore_simulator.cli.main.validate_for_pipeline"
            ) as mock_validate:
                mock_validate.return_value = {
                    "valid": True,
                    "structure": "singleplex",
                    "file_count": 1,
                    "issues": [],
                    "recommendations": [],
                }

                result = validate_pipeline_command(target_dir, "nanometanf")

                captured = capsys.readouterr()
                assert result == 0
                assert "Pipeline validation report for 'nanometanf':" in captured.out
                assert "Valid: yes" in captured.out

    def test_validate_pipeline_command_invalid(self, capsys):
        """Test validate pipeline command with invalid pipeline results."""
        with tempfile.TemporaryDirectory() as temp_dir:
            target_dir = Path(temp_dir)

            with patch(
                "nanopore_simulator.cli.main.validate_for_pipeline"
            ) as mock_validate:
                mock_validate.return_value = {
                    "valid": False,
                    "structure": "unknown",
                    "file_count": 0,
                    "issues": ["No sequencing files found"],
                    "recommendations": ["Add FASTQ or POD5 files"],
                }

                result = validate_pipeline_command(target_dir, "kraken")

                captured = capsys.readouterr()
                assert result == 1
                assert "Pipeline validation report for 'kraken':" in captured.out
                assert "Valid: no" in captured.out

    def test_validate_pipeline_command_with_warnings(self, capsys):
        """Test validate pipeline command output includes warnings."""
        with tempfile.TemporaryDirectory() as temp_dir:
            target_dir = Path(temp_dir)

            with patch(
                "nanopore_simulator.cli.main.validate_for_pipeline"
            ) as mock_validate:
                mock_validate.return_value = {
                    "valid": False,
                    "structure": "unknown",
                    "file_count": 0,
                    "warnings": ["Missing barcode directories"],
                    "errors": ["No FASTQ files"],
                }

                result = validate_pipeline_command(target_dir, "nanometanf")

                captured = capsys.readouterr()
                assert result == 1
                assert "Warning: Missing barcode directories" in captured.out
                assert "Error: No FASTQ files" in captured.out

    def test_validate_pipeline_command_nonexistent_dir(self, capsys):
        """Test validate pipeline command with nonexistent directory."""
        nonexistent_dir = Path("/nonexistent/directory/path")

        result = validate_pipeline_command(nonexistent_dir, "nanometanf")

        captured = capsys.readouterr()
        assert result == 1
        assert "Error: Target directory does not exist" in captured.out


# ---------------------------------------------------------------------------
# CLI integration tests via CliRunner
# ---------------------------------------------------------------------------


class TestCLISpecialOptions:
    """Test CLI subcommands routed through the Typer app."""

    def test_cli_list_profiles(self):
        """Test list-profiles subcommand."""
        with patch(
            "nanopore_simulator.cli.main.get_available_profiles"
        ) as mock_profiles:
            mock_profiles.return_value = {
                "rapid_sequencing": "Fast sequencing with short intervals",
            }
            result = runner.invoke(app, ["list-profiles"])
            assert result.exit_code == 0
            assert "Available Configuration Profiles:" in result.output
            assert "rapid_sequencing" in result.output

    def test_cli_list_adapters(self):
        """Test list-adapters subcommand."""
        with patch(
            "nanopore_simulator.cli.main.get_available_adapters"
        ) as mock_adapters:
            mock_adapters.return_value = {
                "nanometanf": "Real-time taxonomic classification pipeline",
                "kraken": "K-mer based taxonomic assignment",
            }
            result = runner.invoke(app, ["list-adapters"])
            assert result.exit_code == 0
            assert "Available Pipeline Adapters:" in result.output
            assert "nanometanf" in result.output

    def test_cli_list_generators(self):
        """Test list-generators subcommand."""
        with patch(
            "nanopore_simulator.cli.main.detect_available_backends"
        ) as mock_backends:
            mock_backends.return_value = {
                "builtin": True,
                "badread": False,
                "nanosim": False,
            }
            result = runner.invoke(app, ["list-generators"])
            assert result.exit_code == 0
            assert "Available Read Generation Backends:" in result.output
            assert "builtin" in result.output

    def test_cli_recommend_profiles(self):
        """Test recommend subcommand via CliRunner with a real directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            (source_dir / "sample1.fastq").write_text("@read1\\nACGT\\n+\\nIIII\\n")

            with patch(
                "nanopore_simulator.cli.main.get_profile_recommendations"
            ) as mock_rec:
                with patch(
                    "nanopore_simulator.cli.main.get_available_profiles"
                ) as mock_profiles:
                    mock_rec.return_value = ["rapid_sequencing"]
                    mock_profiles.return_value = {
                        "rapid_sequencing": "Fast sequencing",
                    }

                    result = runner.invoke(
                        app, ["recommend", "--source", str(source_dir)]
                    )
                    assert result.exit_code == 0
                    assert "Analysis of" in result.output

    def test_cli_validate_pipeline(self):
        """Test validate subcommand via CliRunner with a real directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            target_dir = Path(temp_dir)
            (target_dir / "sample.fastq").write_text("@read1\\nACGT\\n+\\nIIII\\n")

            with patch(
                "nanopore_simulator.cli.main.validate_for_pipeline"
            ) as mock_validate:
                mock_validate.return_value = {
                    "valid": True,
                    "structure": "singleplex",
                    "file_count": 1,
                    "issues": [],
                    "recommendations": [],
                }

                result = runner.invoke(
                    app,
                    [
                        "validate",
                        "--pipeline",
                        "nanometanf",
                        "--target",
                        str(target_dir),
                    ],
                )
                assert result.exit_code == 0
                assert "Pipeline validation report for 'nanometanf':" in result.output
                assert "Valid: yes" in result.output


class TestCLIErrorHandling:
    """Test CLI error handling paths via CliRunner."""

    def test_cli_invalid_profile_name(self):
        """Test CLI replay with invalid profile name."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            target_dir = Path(temp_dir) / "output"

            (source_dir / "sample.fastq").write_text("@read1\\nACGT\\n+\\nIIII\\n")

            with patch(
                "nanopore_simulator.cli.main.validate_profile_name",
                return_value=False,
            ):
                result = runner.invoke(
                    app,
                    [
                        "replay",
                        "--source",
                        str(source_dir),
                        "--target",
                        str(target_dir),
                        "--profile",
                        "invalid_profile",
                    ],
                )
                assert result.exit_code == 2

    def test_cli_simulation_error(self):
        """Test CLI when simulation raises a runtime error."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            target_dir = Path(temp_dir) / "output"

            (source_dir / "sample.fastq").write_text("@read1\\nACGT\\n+\\nIIII\\n")

            with patch(
                "nanopore_simulator.cli.main.NanoporeSimulator"
            ) as mock_sim_class:
                mock_sim = MagicMock()
                mock_sim.run_simulation.side_effect = RuntimeError("Simulation error")
                mock_sim_class.return_value = mock_sim

                result = runner.invoke(
                    app,
                    [
                        "replay",
                        "--source",
                        str(source_dir),
                        "--target",
                        str(target_dir),
                    ],
                )
                assert result.exit_code == 1

    def test_cli_permission_error(self):
        """Test CLI when a permission error occurs during simulation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            target_dir = Path(temp_dir) / "output"

            (source_dir / "sample.fastq").write_text("@read1\\nACGT\\n+\\nIIII\\n")

            with patch(
                "nanopore_simulator.cli.main.NanoporeSimulator"
            ) as mock_sim_class:
                mock_sim = MagicMock()
                mock_sim.run_simulation.side_effect = PermissionError(
                    "Permission denied"
                )
                mock_sim_class.return_value = mock_sim

                result = runner.invoke(
                    app,
                    [
                        "replay",
                        "--source",
                        str(source_dir),
                        "--target",
                        str(target_dir),
                    ],
                )
                assert result.exit_code == 1


class TestCLIArgumentValidation:
    """Test CLI argument validation for invalid enum/choice values."""

    def test_cli_invalid_timing_model(self):
        """Test CLI replay with an invalid timing model value."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            target_dir = Path(temp_dir) / "output"
            (source_dir / "sample.fastq").write_text("@read1\\nACGT\\n+\\nIIII\\n")

            result = runner.invoke(
                app,
                [
                    "replay",
                    "--source",
                    str(source_dir),
                    "--target",
                    str(target_dir),
                    "--timing-model",
                    "invalid_model",
                ],
            )
            assert result.exit_code == 2

    def test_cli_invalid_operation(self):
        """Test CLI replay with an invalid operation value."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            target_dir = Path(temp_dir) / "output"
            (source_dir / "sample.fastq").write_text("@read1\\nACGT\\n+\\nIIII\\n")

            result = runner.invoke(
                app,
                [
                    "replay",
                    "--source",
                    str(source_dir),
                    "--target",
                    str(target_dir),
                    "--operation",
                    "invalid_operation",
                ],
            )
            assert result.exit_code == 2

    def test_cli_invalid_force_structure(self):
        """Test CLI replay with an invalid force-structure value."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            target_dir = Path(temp_dir) / "output"
            (source_dir / "sample.fastq").write_text("@read1\\nACGT\\n+\\nIIII\\n")

            result = runner.invoke(
                app,
                [
                    "replay",
                    "--source",
                    str(source_dir),
                    "--target",
                    str(target_dir),
                    "--force-structure",
                    "invalid_structure",
                ],
            )
            assert result.exit_code == 2

    def test_cli_invalid_monitor(self):
        """Test CLI replay with an invalid monitor level."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            target_dir = Path(temp_dir) / "output"
            (source_dir / "sample.fastq").write_text("@read1\\nACGT\\n+\\nIIII\\n")

            result = runner.invoke(
                app,
                [
                    "replay",
                    "--source",
                    str(source_dir),
                    "--target",
                    str(target_dir),
                    "--monitor",
                    "invalid_monitor",
                ],
            )
            assert result.exit_code == 2


class TestCLIAdvancedFeatures:
    """Test advanced CLI features and option combinations."""

    def test_cli_all_timing_options(self):
        """Test CLI replay with Poisson timing model and burst parameters."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            target_dir = Path(temp_dir) / "output"

            (source_dir / "sample.fastq").write_text("@read1\\nACGT\\n+\\nIIII\\n")

            with patch(
                "nanopore_simulator.cli.main.NanoporeSimulator"
            ) as mock_sim_class:
                mock_sim = MagicMock()
                mock_sim_class.return_value = mock_sim

                result = runner.invoke(
                    app,
                    [
                        "replay",
                        "--source",
                        str(source_dir),
                        "--target",
                        str(target_dir),
                        "--timing-model",
                        "poisson",
                        "--burst-probability",
                        "0.2",
                        "--burst-rate-multiplier",
                        "3.0",
                    ],
                )
                assert result.exit_code == 0
                mock_sim.run_simulation.assert_called_once()

    def test_cli_parallel_processing_options(self):
        """Test CLI replay with parallel processing enabled."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            target_dir = Path(temp_dir) / "output"

            (source_dir / "sample.fastq").write_text("@read1\\nACGT\\n+\\nIIII\\n")

            with patch(
                "nanopore_simulator.cli.main.NanoporeSimulator"
            ) as mock_sim_class:
                mock_sim = MagicMock()
                mock_sim_class.return_value = mock_sim

                result = runner.invoke(
                    app,
                    [
                        "replay",
                        "--source",
                        str(source_dir),
                        "--target",
                        str(target_dir),
                        "--parallel",
                        "--worker-count",
                        "8",
                    ],
                )
                assert result.exit_code == 0
                mock_sim.run_simulation.assert_called_once()

    def test_cli_enhanced_monitoring_options(self):
        """Test CLI replay with enhanced monitoring and quiet mode."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            target_dir = Path(temp_dir) / "output"

            (source_dir / "sample.fastq").write_text("@read1\\nACGT\\n+\\nIIII\\n")

            with patch(
                "nanopore_simulator.cli.main.NanoporeSimulator"
            ) as mock_sim_class:
                mock_sim = MagicMock()
                mock_sim_class.return_value = mock_sim

                result = runner.invoke(
                    app,
                    [
                        "replay",
                        "--source",
                        str(source_dir),
                        "--target",
                        str(target_dir),
                        "--monitor",
                        "enhanced",
                        "--quiet",
                    ],
                )
                assert result.exit_code == 0
                mock_sim.run_simulation.assert_called_once()

    def test_cli_version_flag(self):
        """Test --version flag prints version and exits."""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "nanorunner" in result.output

    def test_cli_no_args_shows_help(self):
        """Test that invoking the app with no arguments shows help."""
        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "Usage" in result.output or "Commands" in result.output
