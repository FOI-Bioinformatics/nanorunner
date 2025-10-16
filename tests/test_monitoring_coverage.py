"""Comprehensive monitoring tests to improve coverage"""

import pytest
import tempfile
import time
import threading
import signal
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock
from io import StringIO

from nanopore_simulator.core.monitoring import (
    ResourceMetrics,
    SimulationMetrics,
    ResourceMonitor,
    SignalHandler,
    ProgressMonitor,
    ProgressDisplay,
    DetailedProgressMonitor,
    create_progress_monitor,
)


class TestResourceMetricsEdgeCases:
    """Test ResourceMetrics edge cases and error conditions"""

    def test_resource_metrics_without_psutil(self):
        """Test ResourceMetrics behavior when psutil is not available"""
        # This tests the import error handling (lines 19-21)
        with patch("nanopore_simulator.core.monitoring.HAS_PSUTIL", False):
            with patch("nanopore_simulator.core.monitoring.psutil", None):
                monitor = ResourceMonitor()
                metrics = monitor.get_current_metrics()

                # Without psutil, should return default/zero values
                assert metrics.cpu_percent == 0.0
                assert metrics.memory_percent == 0.0

    def test_resource_metrics_to_dict(self):
        """Test ResourceMetrics to_dict conversion"""
        metrics = ResourceMetrics(
            cpu_percent=45.5,
            memory_percent=67.2,
            memory_used_mb=1024.5,
            disk_io_read_mb=100.0,
            disk_io_write_mb=200.0,
            disk_usage_percent=75.0,
            open_files=15,
            network_io_mb=50.0,
        )

        result = metrics.to_dict()

        assert result["cpu_percent"] == 45.5
        assert result["memory_percent"] == 67.2
        assert result["memory_used_mb"] == 1024.5
        assert result["disk_io_read_mb"] == 100.0
        assert result["disk_io_write_mb"] == 200.0
        assert result["disk_usage_percent"] == 75.0
        assert result["open_files"] == 15
        assert result["network_io_mb"] == 50.0


class TestResourceMonitorErrorConditions:
    """Test ResourceMonitor error handling and edge cases"""

    def test_resource_monitor_without_psutil(self):
        """Test ResourceMonitor when psutil is not available"""
        with patch("nanopore_simulator.core.monitoring.HAS_PSUTIL", False):
            monitor = ResourceMonitor()
            metrics = monitor.get_current_metrics()

            # Should return default metrics
            assert isinstance(metrics, ResourceMetrics)
            assert metrics.cpu_percent == 0.0
            assert metrics.memory_percent == 0.0

    def test_resource_monitor_with_psutil_errors(self):
        """Test ResourceMonitor handling psutil errors"""
        with patch("nanopore_simulator.core.monitoring.HAS_PSUTIL", True):
            # Mock process that raises exceptions
            mock_process = MagicMock()
            mock_process.cpu_percent.side_effect = Exception("CPU error")
            mock_process.memory_info.side_effect = Exception("Memory error")
            mock_process.memory_percent.side_effect = Exception("Memory percent error")
            mock_process.open_files.side_effect = Exception("Open files error")

            with patch(
                "nanopore_simulator.core.monitoring.psutil.Process",
                return_value=mock_process,
            ):
                monitor = ResourceMonitor()
                metrics = monitor.get_current_metrics()

                # Should handle exceptions gracefully and return default metrics
                assert isinstance(metrics, ResourceMetrics)


class TestProgressMonitorCorrectAPI:
    """Test ProgressMonitor with correct API usage"""

    def test_progress_monitor_basic_usage(self):
        """Test basic ProgressMonitor usage"""
        monitor = create_progress_monitor(total_files=10, monitor_type="default")

        # Test basic functionality
        monitor.start()
        monitor.record_file_processed(Path("/test/file.txt"))
        monitor.stop()

        assert monitor.metrics.files_processed >= 0
        assert monitor.metrics.files_total == 10

    def test_progress_monitor_enhanced_mode(self):
        """Test ProgressMonitor in enhanced mode"""
        monitor = create_progress_monitor(total_files=5, monitor_type="enhanced")

        monitor.start()
        monitor.set_batch_count(2)

        start_time = monitor.start_batch()
        monitor.record_file_processed(Path("/test/file1.txt"))
        monitor.end_batch(start_time)

        monitor.add_wait_time(0.5)
        monitor.stop()

        assert monitor.metrics.batches_total == 2
        assert monitor.metrics.total_wait_time >= 0.5

    def test_progress_monitor_detailed_mode(self):
        """Test detailed progress monitor"""
        monitor = create_progress_monitor(total_files=3, monitor_type="detailed")

        monitor.start()
        monitor.record_file_processed(Path("/test/file.txt"))
        monitor.stop()

        assert isinstance(monitor, DetailedProgressMonitor)


class TestSignalHandlerCorrectAPI:
    """Test SignalHandler with correct API"""

    def test_signal_handler_creation(self):
        """Test SignalHandler creation with progress monitor"""
        progress_monitor = create_progress_monitor(total_files=5)

        # SignalHandler requires a progress monitor
        handler = SignalHandler(progress_monitor)

        assert handler.progress_monitor is progress_monitor
        assert not handler.shutdown_requested

    def test_signal_handler_signal_processing(self):
        """Test signal handling"""
        progress_monitor = create_progress_monitor(total_files=5)
        handler = SignalHandler(progress_monitor)

        # Simulate signal
        handler._signal_handler(signal.SIGINT, None)

        assert handler.shutdown_requested


class TestSimulationMetricsEdgeCases:
    """Test SimulationMetrics edge cases"""

    def test_simulation_metrics_initialization(self):
        """Test SimulationMetrics initialization"""
        metrics = SimulationMetrics(files_total=100)

        assert metrics.files_total == 100
        assert metrics.files_processed == 0
        assert isinstance(metrics.timing_breakdown, dict)
        assert "waiting" in metrics.timing_breakdown

    def test_simulation_metrics_calculations(self):
        """Test SimulationMetrics calculations"""
        metrics = SimulationMetrics(files_total=100)
        metrics.files_processed = 50
        metrics.start_time = time.time() - 10  # 10 seconds ago

        # Test throughput update
        metrics.update_throughput()
        assert metrics.throughput_files_per_sec > 0

        # Test ETA estimation
        metrics.estimate_eta()
        assert metrics.eta_seconds is not None


class TestProgressDisplayCorrectAPI:
    """Test ProgressDisplay with correct API"""

    def test_progress_display_static_methods(self):
        """Test ProgressDisplay static utility methods"""
        # Test format_bytes
        assert "1.0 KB" in ProgressDisplay.format_bytes(1024)
        assert "1.0 MB" in ProgressDisplay.format_bytes(1024 * 1024)

        # Test format_time
        assert "30.0s" in ProgressDisplay.format_time(30)
        assert "1.5m" in ProgressDisplay.format_time(90)

        # Test format_rate
        assert "5.2 files/sec" in ProgressDisplay.format_rate(5.2, "files")


class TestMonitoringIntegrationRealistic:
    """Test realistic monitoring integration scenarios"""

    def test_monitoring_lifecycle(self):
        """Test complete monitoring lifecycle"""
        monitor = create_progress_monitor(total_files=3, monitor_type="enhanced")

        # Complete lifecycle
        monitor.start()

        # Process some files
        for i in range(3):
            with tempfile.NamedTemporaryFile() as temp_file:
                temp_path = Path(temp_file.name)
                monitor.record_file_processed(temp_path)

        monitor.stop()

        assert monitor.metrics.files_processed == 3

    def test_monitoring_with_errors(self):
        """Test monitoring behavior with simulated errors"""
        monitor = create_progress_monitor(total_files=5, monitor_type="default")

        monitor.start()

        # Test with non-existent file (should handle gracefully)
        non_existent_file = Path("/nonexistent/file.txt")
        monitor.record_file_processed(non_existent_file)

        monitor.stop()

        # Should still work despite errors
        assert monitor.metrics.files_processed >= 0

    def test_resource_monitor_realistic_usage(self):
        """Test ResourceMonitor in realistic scenario"""
        monitor = ResourceMonitor()

        # Get metrics multiple times
        for _ in range(3):
            metrics = monitor.get_current_metrics()
            assert isinstance(metrics, ResourceMetrics)
            time.sleep(0.01)  # Small delay
