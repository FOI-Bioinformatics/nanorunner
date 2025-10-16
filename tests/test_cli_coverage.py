"""Comprehensive CLI tests to improve coverage"""

import pytest
import tempfile
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from io import StringIO

from nanopore_simulator.cli.main import (
    list_profiles_command,
    list_adapters_command,
    recommend_profiles_command,
    validate_pipeline_command,
    main,
)


class TestCLICommandFunctions:
    """Test individual CLI command functions"""

    def test_list_profiles_command(self, capsys):
        """Test the list profiles command function"""
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
        """Test the list adapters command function"""
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
        """Test recommend profiles command with valid directory"""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)

            # Create some sample files
            (source_dir / "sample1.fastq").write_text("@read1\\nACGT\\n+\\nIIII\\n")
            (source_dir / "sample2.fastq.gz").write_text("compressed_data")

            with patch(
                "nanopore_simulator.cli.main.get_profile_recommendations"
            ) as mock_rec:
                with patch(
                    "nanopore_simulator.cli.main.get_available_profiles"
                ) as mock_profiles:
                    mock_rec.return_value = ["rapid_sequencing", "development_testing"]
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
        """Test recommend profiles command with nonexistent directory"""
        nonexistent_dir = Path("/nonexistent/directory/path")

        result = recommend_profiles_command(nonexistent_dir)

        captured = capsys.readouterr()
        assert result == 1
        assert "Error: Source directory does not exist" in captured.out

    def test_validate_pipeline_command_success(self, capsys):
        """Test validate pipeline command with valid directory"""
        with tempfile.TemporaryDirectory() as temp_dir:
            target_dir = Path(temp_dir)

            # Create sample structure
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
                assert "Valid: ✓" in captured.out

    def test_validate_pipeline_command_invalid(self, capsys):
        """Test validate pipeline command with invalid directory"""
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
                assert "Valid: ✗" in captured.out

    def test_validate_pipeline_command_nonexistent_dir(self, capsys):
        """Test validate pipeline command with nonexistent directory"""
        nonexistent_dir = Path("/nonexistent/directory/path")

        result = validate_pipeline_command(nonexistent_dir, "nanometanf")

        captured = capsys.readouterr()
        assert result == 1
        assert "Error: Target directory does not exist" in captured.out


class TestCLISpecialOptions:
    """Test CLI special options and commands"""

    def test_cli_list_profiles_option(self):
        """Test --list-profiles option"""
        with patch.object(sys, "argv", ["nanorunner", "--list-profiles"]):
            with patch(
                "nanopore_simulator.cli.main.list_profiles_command", return_value=0
            ) as mock_cmd:
                result = main()
                assert result == 0
                mock_cmd.assert_called_once()

    def test_cli_list_adapters_option(self):
        """Test --list-adapters option"""
        with patch.object(sys, "argv", ["nanorunner", "--list-adapters"]):
            with patch(
                "nanopore_simulator.cli.main.list_adapters_command", return_value=0
            ) as mock_cmd:
                result = main()
                assert result == 0
                mock_cmd.assert_called_once()

    def test_cli_recommend_profiles_option(self):
        """Test --recommend option"""
        with patch.object(sys, "argv", ["nanorunner", "--recommend", "/test/path"]):
            with patch(
                "nanopore_simulator.cli.main.recommend_profiles_command", return_value=0
            ) as mock_cmd:
                result = main()
                assert result == 0
                mock_cmd.assert_called_once_with(Path("/test/path"))

    def test_cli_validate_pipeline_option(self):
        """Test --validate-pipeline option"""
        with patch.object(
            sys,
            "argv",
            ["nanorunner", "--validate-pipeline", "nanometanf", "/test/path"],
        ):
            with patch(
                "nanopore_simulator.cli.main.validate_pipeline_command", return_value=0
            ) as mock_cmd:
                result = main()
                assert result == 0
                mock_cmd.assert_called_once_with(Path("/test/path"), "nanometanf")


class TestCLIErrorHandling:
    """Test CLI error handling paths"""

    def test_cli_invalid_profile_name(self):
        """Test CLI with invalid profile name"""
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
                    "invalid_profile",
                ],
            ):
                with patch(
                    "nanopore_simulator.cli.main.validate_profile_name",
                    return_value=False,
                ):
                    # parser.error raises SystemExit with code 2
                    with pytest.raises(SystemExit) as exc_info:
                        main()
                    assert exc_info.value.code == 2

    def test_cli_simulation_error(self):
        """Test CLI when simulation raises an error"""
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
                    mock_sim.run_simulation.side_effect = RuntimeError(
                        "Simulation error"
                    )
                    mock_sim_class.return_value = mock_sim

                    result = main()
                    assert result == 1

    def test_cli_permission_error(self):
        """Test CLI when permission error occurs"""
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
                    mock_sim.run_simulation.side_effect = PermissionError(
                        "Permission denied"
                    )
                    mock_sim_class.return_value = mock_sim

                    result = main()
                    assert result == 1


class TestCLIArgumentValidation:
    """Test CLI argument validation"""

    def test_cli_invalid_timing_model(self):
        """Test CLI with invalid timing model"""
        with patch.object(
            sys,
            "argv",
            ["nanorunner", "/source", "/target", "--timing-model", "invalid_model"],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 2  # argparse error

    def test_cli_invalid_operation(self):
        """Test CLI with invalid operation"""
        with patch.object(
            sys,
            "argv",
            ["nanorunner", "/source", "/target", "--operation", "invalid_operation"],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 2  # argparse error

    def test_cli_invalid_force_structure(self):
        """Test CLI with invalid force structure"""
        with patch.object(
            sys,
            "argv",
            [
                "nanorunner",
                "/source",
                "/target",
                "--force-structure",
                "invalid_structure",
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 2  # argparse error

    def test_cli_invalid_monitor(self):
        """Test CLI with invalid monitor option"""
        with patch.object(
            sys,
            "argv",
            ["nanorunner", "/source", "/target", "--monitor", "invalid_monitor"],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 2  # argparse error


class TestCLIAdvancedFeatures:
    """Test advanced CLI features and edge cases"""

    def test_cli_all_timing_options(self):
        """Test CLI with all timing-related options"""
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
                    "0.2",
                    "--burst-rate-multiplier",
                    "3.0",
                ],
            ):
                with patch(
                    "nanopore_simulator.cli.main.NanoporeSimulator"
                ) as mock_sim_class:
                    mock_sim = MagicMock()
                    mock_sim_class.return_value = mock_sim

                    result = main()
                    assert result == 0
                    mock_sim.run_simulation.assert_called_once()

    def test_cli_parallel_processing_options(self):
        """Test CLI with parallel processing options"""
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
                    "--parallel",
                    "--worker-count",
                    "8",
                ],
            ):
                with patch(
                    "nanopore_simulator.cli.main.NanoporeSimulator"
                ) as mock_sim_class:
                    mock_sim = MagicMock()
                    mock_sim_class.return_value = mock_sim

                    result = main()
                    assert result == 0
                    mock_sim.run_simulation.assert_called_once()

    def test_cli_enhanced_monitoring_options(self):
        """Test CLI with enhanced monitoring options"""
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
                    "--quiet",
                ],
            ):
                with patch(
                    "nanopore_simulator.cli.main.NanoporeSimulator"
                ) as mock_sim_class:
                    mock_sim = MagicMock()
                    mock_sim_class.return_value = mock_sim

                    result = main()
                    assert result == 0
                    mock_sim.run_simulation.assert_called_once()
