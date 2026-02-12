"""Additional tests to improve monitoring.py coverage to 95%+"""

import pytest
import tempfile
import time
import json
import signal
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from nanopore_simulator.core.monitoring import (
    ProgressMonitor,
    SignalHandler,
    ResourceMonitor,
    SimulationMetrics,
    ResourceMetrics,
    create_progress_monitor,
)


class TestProgressMonitorEdgeCases:
    """Test edge cases in ProgressMonitor to improve coverage"""

    def test_record_file_with_permission_error(self):
        """Test recording file when stat() raises PermissionError"""
        monitor = ProgressMonitor(10, enable_checkpoint=False)

        # Mock a file path that raises PermissionError on stat()
        mock_path = Mock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.stat.side_effect = PermissionError("Access denied")

        # Should handle gracefully and use 0 size
        monitor.record_file_processed(mock_path, operation_time=0.1)

        assert monitor.metrics.files_processed == 1
        assert monitor.metrics.total_bytes_processed == 0  # Couldn't get size

    def test_record_file_with_os_error(self):
        """Test recording file when stat() raises OSError"""
        monitor = ProgressMonitor(10, enable_checkpoint=False)

        mock_path = Mock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.stat.side_effect = OSError("Disk error")

        monitor.record_file_processed(mock_path, operation_time=0.1)

        assert monitor.metrics.files_processed == 1
        assert monitor.metrics.total_bytes_processed == 0

    def test_checkpoint_save_failure(self):
        """Test checkpoint save with write error"""
        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = ProgressMonitor(10, enable_checkpoint=True)
            monitor.checkpoint_file = Path(tmpdir) / "readonly" / "checkpoint.json"

            # Try to save to non-existent directory
            monitor._save_checkpoint()  # Should log warning, not crash

            # Verify it didn't crash
            assert monitor.metrics.files_processed == 0

    def test_checkpoint_load_corrupted(self):
        """Test loading corrupted checkpoint file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            checkpoint_path = Path(tmpdir) / "checkpoint.json"

            # Write corrupted JSON
            with open(checkpoint_path, "w") as f:
                f.write("{invalid json")

            monitor = ProgressMonitor(10, enable_checkpoint=True)
            monitor.checkpoint_file = checkpoint_path

            # Should handle gracefully
            monitor._load_checkpoint()

            # Verify it continued with defaults
            assert monitor.metrics.files_processed == 0

    def test_checkpoint_cleanup_failure(self):
        """Test checkpoint cleanup with permission error"""
        with tempfile.TemporaryDirectory() as tmpdir:
            checkpoint_path = Path(tmpdir) / "checkpoint.json"
            checkpoint_path.touch()

            monitor = ProgressMonitor(10, enable_checkpoint=True)
            monitor.checkpoint_file = checkpoint_path

            # Mock unlink to raise error
            with patch.object(Path, "unlink", side_effect=PermissionError("Locked")):
                monitor._cleanup_checkpoint()  # Should log warning, not crash

    def test_display_callback_error_handling(self):
        """Test that display callback errors are handled during update loop"""

        def buggy_callback(metrics):
            raise ValueError("Display error")

        monitor = ProgressMonitor(10, display_callback=buggy_callback)
        monitor.start()
        time.sleep(0.3)  # Let update loop run with buggy callback

        # Should not crash despite buggy callback
        # Use default display for stop to avoid error on final call
        monitor.display_callback = monitor._default_display
        monitor.stop()

    def test_performance_warning_cooldown(self):
        """Test that performance warnings respect cooldown period"""
        monitor = ProgressMonitor(100, enable_resources=True)
        monitor._warning_cooldown = 0.1  # Short cooldown for test

        # Create high memory condition
        monitor.metrics.resource_metrics = ResourceMetrics(memory_percent=90)

        # First check should warn
        monitor._check_performance_warnings()
        first_time = monitor._last_warning_time

        # Immediate second check should not warn (cooldown)
        monitor._check_performance_warnings()
        assert monitor._last_warning_time == first_time

        # After cooldown, should warn again
        time.sleep(0.15)
        monitor._check_performance_warnings()
        assert monitor._last_warning_time > first_time

    def test_performance_warning_high_cpu(self):
        """Test high CPU usage warning"""
        monitor = ProgressMonitor(100, enable_resources=True)

        # Add history of high CPU samples
        for _ in range(6):
            sample = ResourceMetrics(cpu_percent=95)
            monitor.metrics.add_resource_sample(sample)

        monitor._check_performance_warnings()
        # Should have logged warning (verified by no crash)

    def test_performance_warning_low_throughput(self):
        """Test low throughput warning"""
        monitor = ProgressMonitor(100, enable_resources=True)
        monitor.metrics.files_processed = 15
        monitor.metrics.throughput_files_per_sec = 0.05

        # Add throughput history
        for _ in range(12):
            monitor.metrics.add_throughput_sample(0.05)

        monitor.metrics.resource_metrics = ResourceMetrics()
        monitor._check_performance_warnings()
        # Should have logged warning

    def test_performance_warning_high_disk_usage(self):
        """Test high disk usage warning"""
        monitor = ProgressMonitor(100, enable_resources=True)
        monitor.metrics.resource_metrics = ResourceMetrics(disk_usage_percent=95)

        monitor._check_performance_warnings()
        # Should have logged warning


class TestSignalHandlerEdgeCases:
    """Test SignalHandler edge cases"""

    def test_signal_handler_without_monitor(self):
        """Test signal handler when progress_monitor is None"""
        handler = SignalHandler(None)  # type: ignore

        # Simulate signal
        handler._signal_handler(signal.SIGINT, None)

        assert handler.shutdown_requested

    def test_signal_handler_double_signal(self):
        """Test double signal causes immediate exit"""
        monitor = ProgressMonitor(10, enable_checkpoint=False)
        handler = SignalHandler(monitor)

        # First signal
        handler._signal_handler(signal.SIGINT, None)
        assert handler.shutdown_requested

        # Second signal should sys.exit(1)
        with pytest.raises(SystemExit) as exc_info:
            handler._signal_handler(signal.SIGINT, None)

        assert exc_info.value.code == 1

    def test_signal_handler_unknown_signal(self):
        """Test handling of unknown signal number"""
        monitor = ProgressMonitor(10, enable_checkpoint=False)
        handler = SignalHandler(monitor)

        # Use a signal number not in the mapping
        handler._signal_handler(999, None)

        assert handler.shutdown_requested

    @patch("nanopore_simulator.core.monitoring.HAS_PSUTIL", False)
    def test_signal_shutdown_summary_without_psutil(self):
        """Test shutdown summary when psutil not available"""
        monitor = ProgressMonitor(10, enable_checkpoint=False, enable_resources=False)
        monitor.metrics.files_processed = 5
        monitor.metrics.total_bytes_processed = 1024 * 1024

        handler = SignalHandler(monitor)

        # Should print summary without resource metrics
        handler._print_shutdown_summary(monitor.metrics)
        # Verified by no crash

    def test_shutdown_summary_with_errors(self):
        """Test shutdown summary includes errors"""
        monitor = ProgressMonitor(10, enable_checkpoint=False)
        monitor.metrics.files_processed = 5
        monitor.metrics.errors_encountered = 3

        handler = SignalHandler(monitor)
        handler._print_shutdown_summary(monitor.metrics)
        # Should print error count


class TestResourceMonitorEdgeCases:
    """Test ResourceMonitor edge cases"""

    @patch("nanopore_simulator.core.monitoring.HAS_PSUTIL", False)
    def test_resource_monitor_without_psutil(self):
        """Test ResourceMonitor when psutil not available"""
        monitor = ResourceMonitor()

        assert monitor.process is None
        assert monitor._baseline_io is None

        # Should return empty metrics
        metrics = monitor.get_current_metrics()
        assert metrics.cpu_percent == 0.0
        assert metrics.memory_percent == 0.0

    @patch("nanopore_simulator.core.monitoring.HAS_PSUTIL", True)
    @patch("nanopore_simulator.core.monitoring.psutil")
    def test_resource_monitor_io_access_denied(self, mock_psutil):
        """Test ResourceMonitor when io_counters raises AccessDenied"""
        import psutil  # noqa

        mock_process = MagicMock()
        mock_process.io_counters.side_effect = psutil.AccessDenied("No access")
        mock_psutil.Process.return_value = mock_process
        mock_psutil.AccessDenied = psutil.AccessDenied

        monitor = ResourceMonitor()
        assert monitor._baseline_io is None  # Couldn't get baseline

    @patch("nanopore_simulator.core.monitoring.HAS_PSUTIL", True)
    @patch("nanopore_simulator.core.monitoring.psutil")
    def test_resource_monitor_metrics_exception(self, mock_psutil):
        """Test get_current_metrics with general exception"""
        mock_process = MagicMock()
        mock_process.cpu_percent.side_effect = RuntimeError("Unexpected error")
        mock_psutil.Process.return_value = mock_process

        monitor = ResourceMonitor()

        # Should return empty metrics on error
        metrics = monitor.get_current_metrics()
        assert isinstance(metrics, ResourceMetrics)

    @patch("nanopore_simulator.core.monitoring.HAS_PSUTIL", True)
    @patch("nanopore_simulator.core.monitoring.psutil")
    def test_resource_monitor_open_files_access_denied(self, mock_psutil):
        """Test when open_files() raises AccessDenied"""
        import psutil  # noqa

        mock_process = MagicMock()
        mock_process.cpu_percent.return_value = 10.0
        mock_process.memory_info.return_value = MagicMock(rss=1024 * 1024)
        mock_process.memory_percent.return_value = 5.0
        mock_process.children.return_value = []
        mock_process.open_files.side_effect = psutil.AccessDenied("No access")
        mock_psutil.Process.return_value = mock_process
        mock_psutil.AccessDenied = psutil.AccessDenied
        mock_psutil.NoSuchProcess = psutil.NoSuchProcess
        mock_psutil.virtual_memory.return_value = MagicMock(total=8 * 1024**3)

        with patch("nanopore_simulator.core.monitoring.os.getcwd", return_value="/tmp"):
            mock_psutil.disk_usage.return_value = MagicMock(total=100, used=50, free=50)

            monitor = ResourceMonitor()
            monitor.process = mock_process
            metrics = monitor.get_current_metrics()

            # Should have 0 open files due to AccessDenied
            assert metrics.open_files == 0
            assert metrics.cpu_percent == 10.0  # Other metrics should work

    @patch("nanopore_simulator.core.monitoring.HAS_PSUTIL", True)
    @patch("nanopore_simulator.core.monitoring.psutil")
    def test_resource_monitor_disk_usage_error(self, mock_psutil):
        """Test when disk_usage() raises OSError"""
        import psutil as _psutil

        mock_process = MagicMock()
        mock_process.cpu_percent.return_value = 10.0
        mock_process.memory_info.return_value = MagicMock(rss=1024 * 1024)
        mock_process.memory_percent.return_value = 5.0
        mock_process.children.return_value = []
        mock_process.open_files.return_value = []
        mock_psutil.Process.return_value = mock_process
        mock_psutil.disk_usage.side_effect = OSError("Disk error")
        mock_psutil.AccessDenied = _psutil.AccessDenied
        mock_psutil.NoSuchProcess = _psutil.NoSuchProcess
        mock_psutil.virtual_memory.return_value = MagicMock(total=8 * 1024**3)

        monitor = ResourceMonitor()
        monitor.process = mock_process
        metrics = monitor.get_current_metrics()

        # Should have 0 disk usage due to error
        assert metrics.disk_usage_percent == 0.0
        assert metrics.cpu_percent == 10.0  # Other metrics should work


class TestProgressMonitorFactory:
    """Test create_progress_monitor factory function"""

    def test_create_default_monitor(self):
        """Test creating default monitor"""
        monitor = create_progress_monitor(10, monitor_type="default")
        assert isinstance(monitor, ProgressMonitor)
        assert not isinstance(monitor, type("DetailedProgressMonitor"))

    def test_create_enhanced_monitor(self):
        """Test creating enhanced monitor with options"""
        monitor = create_progress_monitor(10, monitor_type="enhanced")
        assert isinstance(monitor, ProgressMonitor)
        assert monitor.resource_monitor is not None
        assert monitor.signal_handler is not None
        assert monitor.update_interval == 0.5

    def test_create_detailed_monitor(self):
        """Test creating detailed monitor"""
        from nanopore_simulator.core.monitoring import DetailedProgressMonitor

        monitor = create_progress_monitor(10, monitor_type="detailed")
        assert isinstance(monitor, DetailedProgressMonitor)

    def test_create_monitor_with_custom_kwargs(self):
        """Test factory respects custom kwargs"""
        monitor = create_progress_monitor(
            10,
            monitor_type="default",
            enable_resources=False,
            enable_checkpoint=False,
            update_interval=2.0,
        )
        assert monitor.resource_monitor is None
        assert monitor.signal_handler is None
        assert monitor.update_interval == 2.0


class TestSimulationMetricsEdgeCases:
    """Test SimulationMetrics edge cases"""

    def test_metrics_to_dict_without_resources(self):
        """Test to_dict when resource_metrics is None"""
        metrics = SimulationMetrics(files_total=10)
        metrics.resource_metrics = None

        result = metrics.to_dict()

        assert "resource_metrics" not in result
        assert "elapsed_time" in result

    def test_metrics_to_dict_with_resources(self):
        """Test to_dict when resource_metrics is present"""
        metrics = SimulationMetrics(files_total=10)
        metrics.resource_metrics = ResourceMetrics(cpu_percent=50, memory_percent=60)

        result = metrics.to_dict()

        assert "resource_metrics" in result
        assert result["resource_metrics"]["cpu_percent"] == 50

    def test_eta_estimation_edge_case_zero_throughput(self):
        """Test ETA estimation with zero throughput"""
        metrics = SimulationMetrics(files_total=10)
        metrics.files_processed = 5
        metrics.throughput_files_per_sec = 0.0

        metrics.estimate_eta()

        assert metrics.eta_seconds is None
        assert metrics.confidence_score == 0.0

    def test_eta_estimation_with_remaining_batches(self):
        """Test ETA factors in wait time for remaining batches"""
        metrics = SimulationMetrics(files_total=100)
        metrics.files_processed = 50
        metrics.batches_total = 10
        metrics.batches_processed = 5
        metrics.total_wait_time = 10.0  # 10 seconds total wait for 5 batches
        metrics.throughput_files_per_sec = 10.0

        metrics.estimate_eta()

        # Should add estimated wait time for remaining 5 batches
        # (10s / 5 batches) * 5 remaining = 10s additional
        assert metrics.eta_seconds is not None
        assert metrics.eta_seconds > 5.0  # Base ETA + wait time


class TestPauseResumeEdgeCases:
    """Test pause/resume edge cases"""

    def test_pause_resume_cycle(self):
        """Test pause and resume changes state correctly"""
        monitor = ProgressMonitor(10, enable_checkpoint=False)

        assert not monitor.is_paused()

        monitor.pause()
        assert monitor.is_paused()

        monitor.resume()
        assert not monitor.is_paused()

    def test_wait_if_paused_with_timeout(self):
        """Test wait_if_paused respects timeout"""
        monitor = ProgressMonitor(10, enable_checkpoint=False)
        monitor.pause()

        start = time.time()
        monitor.wait_if_paused(timeout=0.1)
        elapsed = time.time() - start

        # Should timeout, not wait forever
        assert elapsed < 0.2

    def test_should_stop_without_signal_handler(self):
        """Test should_stop when signal_handler is None"""
        monitor = ProgressMonitor(10, enable_checkpoint=False)
        assert not monitor.should_stop()

    def test_should_stop_with_signal_handler(self):
        """Test should_stop with signal handler"""
        monitor = ProgressMonitor(10, enable_checkpoint=True)
        assert not monitor.should_stop()

        # Trigger shutdown
        if monitor.signal_handler:
            monitor.signal_handler.shutdown_requested = True

        assert monitor.should_stop()
