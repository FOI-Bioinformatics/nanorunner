"""Tests for CLI integration with enhanced monitoring features"""

import pytest
import tempfile
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from io import StringIO

from nanopore_simulator.cli.main import main


class TestCLIEnhancedMonitoring:
    """Test CLI integration with enhanced monitoring"""

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

    def test_cli_enhanced_monitoring_option(self):
        """Test CLI with enhanced monitoring option"""
        with patch.object(
            sys,
            "argv",
            [
                "nanorunner",
                str(self.source_dir),
                str(self.target_dir),
                "--monitor",
                "enhanced",
            ],
        ):
            with patch(
                "nanopore_simulator.cli.main.NanoporeSimulator"
            ) as mock_simulator:
                main()

                # Check that simulator was called with enhanced monitoring
                mock_simulator.assert_called_once()
                args, kwargs = mock_simulator.call_args
                config = args[0]
                enable_monitoring = args[1]
                monitor_type = args[2]

                assert enable_monitoring is True
                assert monitor_type == "enhanced"

    def test_cli_enhanced_monitoring_without_psutil(self):
        """Test CLI enhanced monitoring fallback when psutil unavailable"""
        # Mock the import inside the try/except block in main()
        original_import = __builtins__["__import__"]

        def mock_import(name, *args, **kwargs):
            if name == "psutil":
                raise ImportError("No module named 'psutil'")
            return original_import(name, *args, **kwargs)

        with patch.object(
            sys,
            "argv",
            [
                "nanorunner",
                str(self.source_dir),
                str(self.target_dir),
                "--monitor",
                "enhanced",
            ],
        ):
            with patch("builtins.__import__", side_effect=mock_import):
                with patch("builtins.print") as mock_print:
                    with patch(
                        "nanopore_simulator.cli.main.NanoporeSimulator"
                    ) as mock_simulator:
                        main()

                        # Should print warning and fall back to detailed
                        warning_calls = [
                            call
                            for call in mock_print.call_args_list
                            if "Warning" in str(call)
                        ]
                        assert len(warning_calls) > 0

                        # Should use detailed monitoring as fallback
                        args, kwargs = mock_simulator.call_args
                        monitor_type = args[2]
                        assert monitor_type == "detailed"

    def test_cli_enhanced_monitoring_features(self):
        """Test that enhanced monitoring includes expected features"""
        with patch.object(
            sys,
            "argv",
            [
                "nanorunner",
                str(self.source_dir),
                str(self.target_dir),
                "--monitor",
                "enhanced",
            ],
        ):
            with patch(
                "nanopore_simulator.cli.main.NanoporeSimulator"
            ) as mock_simulator:
                result = main()
                assert result == 0

                # Should use enhanced monitoring
                args, kwargs = mock_simulator.call_args
                monitor_type = args[2]
                assert monitor_type == "enhanced"

    def test_cli_enhanced_with_parallel_processing(self):
        """Test CLI enhanced monitoring with parallel processing"""
        with patch.object(
            sys,
            "argv",
            [
                "nanorunner",
                str(self.source_dir),
                str(self.target_dir),
                "--monitor",
                "enhanced",
                "--parallel",
                "--worker-count",
                "2",
            ],
        ):
            with patch(
                "nanopore_simulator.cli.main.NanoporeSimulator"
            ) as mock_simulator:
                main()

                # Should enable both enhanced monitoring and parallel processing
                args, kwargs = mock_simulator.call_args
                config = args[0]
                monitor_type = args[2]

                assert config.parallel_processing is True
                assert config.worker_count == 2
                assert monitor_type == "enhanced"

    def test_cli_enhanced_monitoring_help_text(self):
        """Test that enhanced monitoring is properly documented in help"""
        with patch.object(sys, "argv", ["nanorunner", "--help"]):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with pytest.raises(SystemExit) as excinfo:
                    main()

                assert excinfo.value.code == 0
                help_output = mock_stdout.getvalue()

                # Should mention enhanced monitoring
                assert "enhanced" in help_output.lower()
                assert "resource monitoring" in help_output.lower()
                assert "interactive controls" in help_output.lower()
                assert "pip install nanorunner[enhanced]" in help_output

    def test_cli_enhanced_monitoring_with_profile(self):
        """Test enhanced monitoring with configuration profiles"""
        with patch.object(
            sys,
            "argv",
            [
                "nanorunner",
                str(self.source_dir),
                str(self.target_dir),
                "--profile",
                "rapid_sequencing",
                "--monitor",
                "enhanced",
            ],
        ):
            with patch(
                "nanopore_simulator.cli.main.NanoporeSimulator"
            ) as mock_simulator:
                main()

                # Should use profile with enhanced monitoring override
                args, kwargs = mock_simulator.call_args
                config = args[0]
                monitor_type = args[2]

                assert monitor_type == "enhanced"
                # Profile should still be applied to config
                assert config.timing_model == "poisson"  # rapid_sequencing uses poisson

    def test_cli_interactive_instructions_printed(self):
        """Test that interactive instructions are printed for enhanced monitoring"""
        with patch.object(
            sys,
            "argv",
            [
                "nanorunner",
                str(self.source_dir),
                str(self.target_dir),
                "--monitor",
                "enhanced",
            ],
        ):
            with patch("builtins.print") as mock_print:
                with patch("nanopore_simulator.cli.main.NanoporeSimulator"):
                    main()

                    # Should print helpful instructions
                    print_calls = [str(call) for call in mock_print.call_args_list]
                    instruction_calls = [
                        call
                        for call in print_calls
                        if "Enhanced monitoring active" in call
                        or "Ctrl+C" in call
                        or "checkpointed" in call
                    ]

                    assert len(instruction_calls) > 0


class TestCLIMonitoringLevels:
    """Test different monitoring levels through CLI"""

    def setup_method(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

        self.source_dir = self.temp_path / "source"
        self.target_dir = self.temp_path / "target"
        self.source_dir.mkdir()

        (self.source_dir / "sample.fastq").write_text("test content")

    def teardown_method(self):
        """Clean up test fixtures"""
        self.temp_dir.cleanup()

    def test_cli_default_monitoring(self):
        """Test default monitoring level"""
        with patch.object(
            sys, "argv", ["nanorunner", str(self.source_dir), str(self.target_dir)]
        ):
            with patch(
                "nanopore_simulator.cli.main.NanoporeSimulator"
            ) as mock_simulator:
                main()

                args, kwargs = mock_simulator.call_args
                enable_monitoring = args[1]
                monitor_type = args[2]

                assert enable_monitoring is True
                assert monitor_type == "default"

    def test_cli_detailed_monitoring(self):
        """Test detailed monitoring level"""
        with patch.object(
            sys,
            "argv",
            [
                "nanorunner",
                str(self.source_dir),
                str(self.target_dir),
                "--monitor",
                "detailed",
            ],
        ):
            with patch(
                "nanopore_simulator.cli.main.NanoporeSimulator"
            ) as mock_simulator:
                main()

                args, kwargs = mock_simulator.call_args
                monitor_type = args[2]

                assert monitor_type == "detailed"

    def test_cli_no_monitoring(self):
        """Test monitoring disabled"""
        with patch.object(
            sys,
            "argv",
            [
                "nanorunner",
                str(self.source_dir),
                str(self.target_dir),
                "--monitor",
                "none",
            ],
        ):
            with patch(
                "nanopore_simulator.cli.main.NanoporeSimulator"
            ) as mock_simulator:
                main()

                args, kwargs = mock_simulator.call_args
                enable_monitoring = args[1]
                monitor_type = args[2]

                assert enable_monitoring is False
                assert (
                    monitor_type == "default"
                )  # Default used when monitoring disabled

    def test_cli_quiet_mode(self):
        """Test quiet mode disables monitoring"""
        with patch.object(
            sys,
            "argv",
            ["nanorunner", str(self.source_dir), str(self.target_dir), "--quiet"],
        ):
            with patch(
                "nanopore_simulator.cli.main.NanoporeSimulator"
            ) as mock_simulator:
                main()

                args, kwargs = mock_simulator.call_args
                enable_monitoring = args[1]

                assert enable_monitoring is False


class TestCLIEnhancedFeatureIntegration:
    """Test integration of enhanced features through CLI"""

    def setup_method(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

        self.source_dir = self.temp_path / "source"
        self.target_dir = self.temp_path / "target"
        self.source_dir.mkdir()

        # Create multiple test files for better testing
        for i in range(3):
            (self.source_dir / f"sample_{i}.fastq").write_text(f"test content {i}")

    def teardown_method(self):
        """Clean up test fixtures"""
        self.temp_dir.cleanup()

    def test_cli_enhanced_with_timing_models(self):
        """Test enhanced monitoring with different timing models"""
        timing_models = ["uniform", "random", "poisson", "adaptive"]

        for model in timing_models:
            with patch.object(
                sys,
                "argv",
                [
                    "nanorunner",
                    str(self.source_dir),
                    str(self.target_dir),
                    "--monitor",
                    "enhanced",
                    "--timing-model",
                    model,
                    "--interval",
                    "0.1",  # Fast for testing
                ],
            ):
                with patch(
                    "nanopore_simulator.cli.main.NanoporeSimulator"
                ) as mock_simulator:
                    result = main()

                    assert result == 0

                    # Check configuration
                    args, kwargs = mock_simulator.call_args
                    config = args[0]
                    monitor_type = args[2]

                    assert config.timing_model == model
                    assert monitor_type == "enhanced"

    def test_cli_enhanced_with_batch_processing(self):
        """Test enhanced monitoring with batch processing"""
        with patch.object(
            sys,
            "argv",
            [
                "nanorunner",
                str(self.source_dir),
                str(self.target_dir),
                "--monitor",
                "enhanced",
                "--batch-size",
                "2",
                "--interval",
                "0.1",
            ],
        ):
            with patch(
                "nanopore_simulator.cli.main.NanoporeSimulator"
            ) as mock_simulator:
                result = main()

                assert result == 0

                args, kwargs = mock_simulator.call_args
                config = args[0]

                assert config.batch_size == 2

    def test_cli_enhanced_error_handling(self):
        """Test enhanced monitoring error handling through CLI"""
        with patch.object(
            sys,
            "argv",
            [
                "nanorunner",
                str(self.source_dir),
                str(self.target_dir),
                "--monitor",
                "enhanced",
            ],
        ):
            with patch(
                "nanopore_simulator.cli.main.NanoporeSimulator"
            ) as mock_simulator:
                # Simulate simulator exception
                mock_instance = MagicMock()
                mock_instance.run_simulation.side_effect = Exception("Test error")
                mock_simulator.return_value = mock_instance

                with patch("builtins.print") as mock_print:
                    result = main()

                    assert result == 1  # Should return error code

                    # Should print error message
                    error_calls = [
                        call
                        for call in mock_print.call_args_list
                        if "Error:" in str(call)
                    ]
                    assert len(error_calls) > 0

    def test_cli_enhanced_with_multiplex_structure(self):
        """Test enhanced monitoring with multiplex data structure"""
        # Create multiplex structure
        barcode_dir = self.source_dir / "barcode01"
        barcode_dir.mkdir()
        (barcode_dir / "reads.fastq").write_text("multiplex content")

        # Remove singleplex files
        for file in self.source_dir.glob("sample_*.fastq"):
            file.unlink()

        with patch.object(
            sys,
            "argv",
            [
                "nanorunner",
                str(self.source_dir),
                str(self.target_dir),
                "--monitor",
                "enhanced",
                "--interval",
                "0.1",
            ],
        ):
            result = main()

            assert result == 0
            assert (self.target_dir / "barcode01" / "reads.fastq").exists()


if __name__ == "__main__":
    pytest.main([__file__])
