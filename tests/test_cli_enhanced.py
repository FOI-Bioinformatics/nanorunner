"""Tests for CLI integration with enhanced monitoring features."""

import builtins
import re
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from nanopore_simulator.cli.main import app

runner = CliRunner()


class TestCLIEnhancedMonitoring:
    """Test CLI integration with enhanced monitoring."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.source_dir = self.temp_path / "source"
        self.target_dir = self.temp_path / "target"
        self.source_dir.mkdir()
        (self.source_dir / "sample.fastq").write_text("test content")

    def teardown_method(self):
        """Clean up test fixtures."""
        self.temp_dir.cleanup()

    def test_cli_enhanced_monitoring_option(self):
        """Test CLI with enhanced monitoring option."""
        with patch(
            "nanopore_simulator.cli.main.NanoporeSimulator"
        ) as mock_simulator:
            result = runner.invoke(
                app,
                [
                    "replay",
                    "--source", str(self.source_dir),
                    "--target", str(self.target_dir),
                    "--monitor", "enhanced",
                ],
            )

            assert result.exit_code == 0, result.output
            mock_simulator.assert_called_once()
            args, kwargs = mock_simulator.call_args
            config = args[0]
            enable_monitoring = args[1]
            monitor_type = args[2]

            assert enable_monitoring is True
            assert monitor_type == "enhanced"

    def test_cli_enhanced_monitoring_without_psutil(self):
        """Test CLI enhanced monitoring fallback when psutil is unavailable."""
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "psutil":
                raise ImportError("No module named 'psutil'")
            return original_import(name, *args, **kwargs)

        with patch(
            "nanopore_simulator.cli.main.NanoporeSimulator"
        ) as mock_simulator:
            with patch("builtins.__import__", side_effect=mock_import):
                result = runner.invoke(
                    app,
                    [
                        "replay",
                        "--source", str(self.source_dir),
                        "--target", str(self.target_dir),
                        "--monitor", "enhanced",
                    ],
                )

            assert result.exit_code == 0, result.output

            # Should contain a warning about psutil in the captured output
            assert "Warning" in result.output

            # Should fall back to detailed monitoring
            args, kwargs = mock_simulator.call_args
            monitor_type = args[2]
            assert monitor_type == "detailed"

    def test_cli_enhanced_monitoring_features(self):
        """Test that enhanced monitoring includes expected features."""
        with patch(
            "nanopore_simulator.cli.main.NanoporeSimulator"
        ) as mock_simulator:
            result = runner.invoke(
                app,
                [
                    "replay",
                    "--source", str(self.source_dir),
                    "--target", str(self.target_dir),
                    "--monitor", "enhanced",
                ],
            )

            assert result.exit_code == 0, result.output

            args, kwargs = mock_simulator.call_args
            monitor_type = args[2]
            assert monitor_type == "enhanced"

    def test_cli_enhanced_with_parallel_processing(self):
        """Test CLI enhanced monitoring with parallel processing."""
        with patch(
            "nanopore_simulator.cli.main.NanoporeSimulator"
        ) as mock_simulator:
            result = runner.invoke(
                app,
                [
                    "replay",
                    "--source", str(self.source_dir),
                    "--target", str(self.target_dir),
                    "--monitor", "enhanced",
                    "--parallel",
                    "--worker-count", "2",
                ],
            )

            assert result.exit_code == 0, result.output
            args, kwargs = mock_simulator.call_args
            config = args[0]
            monitor_type = args[2]

            assert config.parallel_processing is True
            assert config.worker_count == 2
            assert monitor_type == "enhanced"

    def test_cli_enhanced_monitoring_help_text(self):
        """Test that enhanced monitoring is properly documented in help."""
        result = runner.invoke(app, ["replay", "--help"])

        assert result.exit_code == 0, result.output
        help_output = result.output

        # Rich panel rendering wraps text across lines and inserts box
        # drawing characters plus padding.  Strip box-drawing chars and
        # collapse whitespace to enable substring matching.
        stripped = re.sub(r"[╭╮╰╯─│\n]", " ", help_output)
        normalised = re.sub(r"\s+", " ", stripped).lower()

        assert "enhanced" in normalised
        assert "resource monitoring" in normalised
        assert "interactive controls" in normalised
        # Rich markup mode consumes "[enhanced]" as a tag, so check the
        # surrounding text that does render.
        assert "pip install nanorunner" in normalised

    def test_cli_enhanced_monitoring_with_profile(self):
        """Test enhanced monitoring with configuration profiles."""
        with patch(
            "nanopore_simulator.cli.main.NanoporeSimulator"
        ) as mock_simulator:
            result = runner.invoke(
                app,
                [
                    "replay",
                    "--source", str(self.source_dir),
                    "--target", str(self.target_dir),
                    "--profile", "bursty",
                    "--monitor", "enhanced",
                ],
            )

            assert result.exit_code == 0, result.output
            args, kwargs = mock_simulator.call_args
            config = args[0]
            monitor_type = args[2]

            assert monitor_type == "enhanced"
            # bursty profile uses poisson timing
            assert config.timing_model == "poisson"

    def test_cli_interactive_instructions_printed(self):
        """Test that interactive instructions are printed for enhanced monitoring."""
        with patch("nanopore_simulator.cli.main.NanoporeSimulator"):
            result = runner.invoke(
                app,
                [
                    "replay",
                    "--source", str(self.source_dir),
                    "--target", str(self.target_dir),
                    "--monitor", "enhanced",
                ],
            )

            assert result.exit_code == 0, result.output

            # The _run_simulation helper prints interactive instructions
            output = result.output
            assert (
                "Enhanced monitoring active" in output
                or "Ctrl+C" in output
                or "checkpointed" in output
            )


class TestCLIMonitoringLevels:
    """Test different monitoring levels through CLI."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.source_dir = self.temp_path / "source"
        self.target_dir = self.temp_path / "target"
        self.source_dir.mkdir()
        (self.source_dir / "sample.fastq").write_text("test content")

    def teardown_method(self):
        """Clean up test fixtures."""
        self.temp_dir.cleanup()

    def test_cli_default_monitoring(self):
        """Test default monitoring level."""
        with patch(
            "nanopore_simulator.cli.main.NanoporeSimulator"
        ) as mock_simulator:
            result = runner.invoke(
                app,
                [
                    "replay",
                    "--source", str(self.source_dir),
                    "--target", str(self.target_dir),
                ],
            )

            assert result.exit_code == 0, result.output
            args, kwargs = mock_simulator.call_args
            enable_monitoring = args[1]
            monitor_type = args[2]

            assert enable_monitoring is True
            assert monitor_type == "default"

    def test_cli_detailed_monitoring(self):
        """Test detailed monitoring level."""
        with patch(
            "nanopore_simulator.cli.main.NanoporeSimulator"
        ) as mock_simulator:
            result = runner.invoke(
                app,
                [
                    "replay",
                    "--source", str(self.source_dir),
                    "--target", str(self.target_dir),
                    "--monitor", "detailed",
                ],
            )

            assert result.exit_code == 0, result.output
            args, kwargs = mock_simulator.call_args
            monitor_type = args[2]

            assert monitor_type == "detailed"

    def test_cli_no_monitoring(self):
        """Test monitoring disabled."""
        with patch(
            "nanopore_simulator.cli.main.NanoporeSimulator"
        ) as mock_simulator:
            result = runner.invoke(
                app,
                [
                    "replay",
                    "--source", str(self.source_dir),
                    "--target", str(self.target_dir),
                    "--monitor", "none",
                ],
            )

            assert result.exit_code == 0, result.output
            args, kwargs = mock_simulator.call_args
            enable_monitoring = args[1]
            monitor_type = args[2]

            assert enable_monitoring is False
            # Default used when monitoring is disabled
            assert monitor_type == "default"

    def test_cli_quiet_mode(self):
        """Test quiet mode disables monitoring."""
        with patch(
            "nanopore_simulator.cli.main.NanoporeSimulator"
        ) as mock_simulator:
            result = runner.invoke(
                app,
                [
                    "replay",
                    "--source", str(self.source_dir),
                    "--target", str(self.target_dir),
                    "--quiet",
                ],
            )

            assert result.exit_code == 0, result.output
            args, kwargs = mock_simulator.call_args
            enable_monitoring = args[1]

            assert enable_monitoring is False


class TestCLIEnhancedFeatureIntegration:
    """Test integration of enhanced features through CLI."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.source_dir = self.temp_path / "source"
        self.target_dir = self.temp_path / "target"
        self.source_dir.mkdir()
        for i in range(3):
            (self.source_dir / f"sample_{i}.fastq").write_text(
                f"test content {i}"
            )

    def teardown_method(self):
        """Clean up test fixtures."""
        self.temp_dir.cleanup()

    def test_cli_enhanced_with_timing_models(self):
        """Test enhanced monitoring with different timing models."""
        timing_models = ["uniform", "random", "poisson", "adaptive"]

        for model in timing_models:
            with patch(
                "nanopore_simulator.cli.main.NanoporeSimulator"
            ) as mock_simulator:
                result = runner.invoke(
                    app,
                    [
                        "replay",
                        "--source", str(self.source_dir),
                        "--target", str(self.target_dir),
                        "--monitor", "enhanced",
                        "--timing-model", model,
                        "--interval", "0.1",
                    ],
                )

                assert result.exit_code == 0, (
                    f"Failed for timing model {model}: {result.output}"
                )
                args, kwargs = mock_simulator.call_args
                config = args[0]
                monitor_type = args[2]

                assert config.timing_model == model
                assert monitor_type == "enhanced"

    def test_cli_enhanced_with_batch_processing(self):
        """Test enhanced monitoring with batch processing."""
        with patch(
            "nanopore_simulator.cli.main.NanoporeSimulator"
        ) as mock_simulator:
            result = runner.invoke(
                app,
                [
                    "replay",
                    "--source", str(self.source_dir),
                    "--target", str(self.target_dir),
                    "--monitor", "enhanced",
                    "--batch-size", "2",
                    "--interval", "0.1",
                ],
            )

            assert result.exit_code == 0, result.output
            args, kwargs = mock_simulator.call_args
            config = args[0]

            assert config.batch_size == 2

    def test_cli_enhanced_error_handling(self):
        """Test enhanced monitoring error handling through CLI."""
        with patch(
            "nanopore_simulator.cli.main.NanoporeSimulator"
        ) as mock_simulator:
            mock_instance = MagicMock()
            mock_instance.run_simulation.side_effect = Exception("Test error")
            mock_simulator.return_value = mock_instance

            result = runner.invoke(
                app,
                [
                    "replay",
                    "--source", str(self.source_dir),
                    "--target", str(self.target_dir),
                    "--monitor", "enhanced",
                ],
            )

            assert result.exit_code == 1
            assert "Error:" in result.output

    def test_cli_enhanced_with_multiplex_structure(self):
        """Test enhanced monitoring with multiplex data structure."""
        # Create multiplex structure
        barcode_dir = self.source_dir / "barcode01"
        barcode_dir.mkdir()
        (barcode_dir / "reads.fastq").write_text("multiplex content")

        # Remove singleplex files
        for file in self.source_dir.glob("sample_*.fastq"):
            file.unlink()

        result = runner.invoke(
            app,
            [
                "replay",
                "--source", str(self.source_dir),
                "--target", str(self.target_dir),
                "--monitor", "enhanced",
                "--interval", "0.1",
            ],
        )

        assert result.exit_code == 0, result.output
        assert (self.target_dir / "barcode01" / "reads.fastq").exists()


if __name__ == "__main__":
    pytest.main([__file__])
