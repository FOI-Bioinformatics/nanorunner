"""Tests for progress monitoring system"""

import pytest
import time
import threading
from pathlib import Path
from unittest.mock import Mock, patch

from nanopore_simulator.core.monitoring import (
    SimulationMetrics,
    ProgressDisplay,
    ProgressMonitor,
    DetailedProgressMonitor,
    create_progress_monitor,
)


class TestSimulationMetrics:
    """Test the SimulationMetrics class"""

    def test_metrics_initialization(self):
        """Test metrics initialization"""
        metrics = SimulationMetrics(files_total=100)

        assert metrics.files_total == 100
        assert metrics.files_processed == 0
        assert metrics.start_time > 0
        assert metrics.end_time is None
        assert metrics.progress_percentage == 0.0
        assert metrics.is_complete is False
        assert len(metrics.timing_breakdown) > 0

    def test_progress_percentage_calculation(self):
        """Test progress percentage calculation"""
        metrics = SimulationMetrics(files_total=50)

        assert metrics.progress_percentage == 0.0

        metrics.files_processed = 25
        assert metrics.progress_percentage == 50.0

        metrics.files_processed = 50
        assert metrics.progress_percentage == 100.0
        assert metrics.is_complete is True

    def test_elapsed_time(self):
        """Test elapsed time calculation"""
        start_time = time.time()
        metrics = SimulationMetrics()
        metrics.start_time = start_time

        time.sleep(0.1)  # Small delay
        elapsed = metrics.elapsed_time
        assert elapsed >= 0.1
        assert elapsed < 1.0  # Should be much less than 1 second

    def test_update_throughput(self):
        """Test throughput calculation"""
        metrics = SimulationMetrics()
        metrics.start_time = time.time() - 10  # 10 seconds ago
        metrics.files_processed = 20
        metrics.total_bytes_processed = 2000

        metrics.update_throughput()

        assert (
            abs(metrics.throughput_files_per_sec - 2.0) < 0.01
        )  # ~20 files / 10 seconds
        assert (
            abs(metrics.throughput_bytes_per_sec - 200.0) < 0.01
        )  # ~2000 bytes / 10 seconds
        assert metrics.average_file_size == 100.0  # 2000 bytes / 20 files

    def test_eta_estimation(self):
        """Test ETA estimation"""
        metrics = SimulationMetrics(files_total=100)
        metrics.start_time = time.time() - 10
        metrics.files_processed = 20
        metrics.batches_processed = 4
        metrics.batches_total = 20
        metrics.total_wait_time = 8.0  # 2 seconds average wait per batch

        metrics.update_throughput()
        metrics.estimate_eta()

        assert metrics.eta_seconds is not None
        assert metrics.eta_seconds > 0
        # Should include both processing time and wait time

    def test_to_dict_conversion(self):
        """Test conversion to dictionary"""
        metrics = SimulationMetrics(files_total=50)
        metrics.files_processed = 25
        metrics.total_bytes_processed = 1000

        metrics_dict = metrics.to_dict()

        assert metrics_dict["files_processed"] == 25
        assert metrics_dict["files_total"] == 50
        assert metrics_dict["progress_percentage"] == 50.0
        assert metrics_dict["total_bytes_processed"] == 1000
        assert "timing_breakdown" in metrics_dict


class TestProgressDisplay:
    """Test the ProgressDisplay utility functions"""

    def test_format_bytes(self):
        """Test byte formatting"""
        assert ProgressDisplay.format_bytes(512) == "512.0 B"
        assert ProgressDisplay.format_bytes(1536) == "1.5 KB"
        assert ProgressDisplay.format_bytes(2048 * 1024) == "2.0 MB"
        assert ProgressDisplay.format_bytes(1024**3) == "1.0 GB"

    def test_format_time(self):
        """Test time formatting"""
        assert ProgressDisplay.format_time(30) == "30.0s"
        assert ProgressDisplay.format_time(90) == "1.5m"
        assert ProgressDisplay.format_time(3660) == "1.0h"

    def test_format_rate(self):
        """Test rate formatting"""
        assert ProgressDisplay.format_rate(5.2, "files") == "5.2 files/sec"
        assert ProgressDisplay.format_rate(1024, "bytes") == "1.0 KB/sec"

    def test_create_progress_bar(self):
        """Test progress bar creation"""
        bar = ProgressDisplay.create_progress_bar(50.0, width=10)
        assert "[" in bar and "]" in bar
        assert "50.0%" in bar
        assert "█" in bar  # Filled portion
        assert "░" in bar  # Empty portion

    def test_format_progress_line(self):
        """Test complete progress line formatting"""
        metrics = SimulationMetrics(files_total=100)
        metrics.files_processed = 30
        metrics.throughput_files_per_sec = 2.5
        metrics.eta_seconds = 120

        line = ProgressDisplay.format_progress_line(metrics)

        assert "30/100 files" in line
        assert "2.5 files/sec" in line
        assert "ETA:" in line
        assert "Elapsed:" in line


class TestProgressMonitor:
    """Test the ProgressMonitor class"""

    def test_monitor_initialization(self):
        """Test monitor initialization"""
        monitor = ProgressMonitor(total_files=50)

        assert monitor.metrics.files_total == 50
        assert monitor.update_interval == 1.0
        assert monitor._stop_event is not None
        assert monitor._lock is not None

    def test_monitor_start_stop(self):
        """Test starting and stopping monitor"""
        monitor = ProgressMonitor(total_files=10, update_interval=0.1)

        # Start monitoring
        monitor.start()
        assert monitor._update_thread is not None
        assert monitor._update_thread.is_alive()

        # Give it a moment to run
        time.sleep(0.2)

        # Stop monitoring
        monitor.stop()
        assert not monitor._update_thread.is_alive()
        assert monitor.metrics.end_time is not None

    def test_batch_tracking(self):
        """Test batch start/end tracking"""
        monitor = ProgressMonitor(total_files=20)
        monitor.set_batch_count(5)

        # Start and end a batch
        start_time = monitor.start_batch()
        time.sleep(0.1)
        monitor.end_batch(start_time)

        assert monitor.metrics.batches_processed == 1
        assert monitor.metrics.total_processing_time >= 0.1

    def test_file_processing_tracking(self):
        """Test file processing tracking"""
        monitor = ProgressMonitor(total_files=10)

        # Create a temporary file for testing
        import tempfile

        with tempfile.NamedTemporaryFile() as tmp_file:
            tmp_path = Path(tmp_file.name)
            tmp_file.write(b"test content")
            tmp_file.flush()

            monitor.record_file_processed(tmp_path, operation_time=0.05)

            assert monitor.metrics.files_processed == 1
            assert monitor.metrics.total_bytes_processed > 0
            assert monitor.metrics.timing_breakdown["file_operations"] == 0.05

    def test_error_recording(self):
        """Test error recording"""
        monitor = ProgressMonitor(total_files=5)

        monitor.record_error("test_error")
        assert monitor.metrics.errors_encountered == 1

        monitor.record_error("another_error")
        assert monitor.metrics.errors_encountered == 2

    def test_wait_time_tracking(self):
        """Test wait time tracking"""
        monitor = ProgressMonitor(total_files=5)

        monitor.add_wait_time(2.5)
        assert monitor.metrics.total_wait_time == 2.5
        assert monitor.metrics.timing_breakdown["waiting"] == 2.5

    def test_custom_timing_recording(self):
        """Test custom timing category recording"""
        monitor = ProgressMonitor(total_files=5)

        monitor.record_timing("validation", 1.2)
        monitor.record_timing("custom_operation", 0.8)

        assert monitor.metrics.timing_breakdown["validation"] == 1.2
        assert monitor.metrics.timing_breakdown["custom_operation"] == 0.8

    def test_thread_safe_metrics_access(self):
        """Test thread-safe access to metrics"""
        monitor = ProgressMonitor(total_files=10, update_interval=0.1)

        monitor.start()

        # Access metrics from main thread while monitor thread is running
        metrics = monitor.get_metrics()
        assert isinstance(metrics, SimulationMetrics)
        assert metrics.files_total == 10

        monitor.stop()

    def test_custom_display_callback(self):
        """Test custom display callback"""
        display_calls = []

        def custom_display(metrics):
            display_calls.append(metrics.files_processed)

        monitor = ProgressMonitor(
            total_files=5, update_interval=0.1, display_callback=custom_display
        )

        monitor.start()
        time.sleep(0.15)  # Let it update once
        monitor.stop()

        # Should have been called at least once
        assert len(display_calls) > 0


class TestDetailedProgressMonitor:
    """Test the DetailedProgressMonitor class"""

    def test_detailed_monitor_initialization(self):
        """Test detailed monitor initialization"""
        monitor = DetailedProgressMonitor(total_files=20, update_interval=0.5)

        assert monitor.metrics.files_total == 20
        assert monitor.update_interval == 0.5
        assert monitor.batch_details == []
        assert monitor.file_details == []

    def test_detailed_batch_tracking(self):
        """Test detailed batch tracking"""
        monitor = DetailedProgressMonitor(total_files=10)

        start_time = monitor.start_batch()
        time.sleep(0.1)
        monitor.end_batch(start_time)

        assert len(monitor.batch_details) == 1
        batch_info = monitor.batch_details[0]
        assert batch_info["batch_number"] == 1
        assert batch_info["duration"] >= 0.1

    def test_detailed_file_tracking(self):
        """Test detailed file tracking"""
        monitor = DetailedProgressMonitor(total_files=5)

        import tempfile

        with tempfile.NamedTemporaryFile() as tmp_file:
            tmp_path = Path(tmp_file.name)
            tmp_file.write(b"test content")
            tmp_file.flush()

            monitor.record_file_processed(tmp_path, operation_time=0.03)

            assert len(monitor.file_details) == 1
            file_info = monitor.file_details[0]
            assert file_info["file_path"] == str(tmp_path)
            assert file_info["operation_time"] == 0.03
            assert file_info["size_bytes"] > 0


class TestProgressMonitorFactory:
    """Test the progress monitor factory function"""

    def test_create_default_monitor(self):
        """Test creating default monitor"""
        monitor = create_progress_monitor(10, monitor_type="default")
        assert isinstance(monitor, ProgressMonitor)
        assert not isinstance(monitor, DetailedProgressMonitor)

    def test_create_detailed_monitor(self):
        """Test creating detailed monitor"""
        monitor = create_progress_monitor(10, monitor_type="detailed")
        assert isinstance(monitor, DetailedProgressMonitor)

    def test_create_monitor_with_custom_params(self):
        """Test creating monitor with custom parameters"""
        monitor = create_progress_monitor(
            15, monitor_type="default", update_interval=0.5
        )
        assert monitor.metrics.files_total == 15
        assert monitor.update_interval == 0.5


class TestProgressMonitorIntegration:
    """Test progress monitor integration scenarios"""

    def test_complete_simulation_workflow(self):
        """Test a complete simulation workflow with monitoring"""
        monitor = ProgressMonitor(total_files=5, update_interval=0.1)
        monitor.set_batch_count(2)

        # Simulate workflow
        monitor.start()

        # Batch 1
        batch_start = monitor.start_batch()

        # Process 3 files
        import tempfile

        for i in range(3):
            with tempfile.NamedTemporaryFile() as tmp_file:
                tmp_path = Path(tmp_file.name)
                tmp_file.write(f"content {i}".encode())
                tmp_file.flush()
                monitor.record_file_processed(tmp_path, 0.01)

        monitor.end_batch(batch_start)
        monitor.add_wait_time(0.5)

        # Batch 2
        batch_start = monitor.start_batch()

        # Process remaining 2 files
        for i in range(2):
            with tempfile.NamedTemporaryFile() as tmp_file:
                tmp_path = Path(tmp_file.name)
                tmp_file.write(f"content {i+3}".encode())
                tmp_file.flush()
                monitor.record_file_processed(tmp_path, 0.01)

        monitor.end_batch(batch_start)

        monitor.stop()

        # Verify final state
        final_metrics = monitor.get_metrics()
        assert final_metrics.files_processed == 5
        assert final_metrics.batches_processed == 2
        assert final_metrics.is_complete is True
        assert final_metrics.total_wait_time == 0.5
        assert final_metrics.throughput_files_per_sec > 0

    def test_error_handling_during_monitoring(self):
        """Test error handling during monitoring"""
        error_count = 0

        def faulty_display(metrics):
            nonlocal error_count
            error_count += 1
            if error_count <= 2:
                raise ValueError("Display error")

        monitor = ProgressMonitor(
            total_files=5, update_interval=0.05, display_callback=faulty_display
        )

        # Should not crash even with faulty display callback
        monitor.start()
        time.sleep(0.15)  # Let it try a few updates
        monitor.stop()

        # Should have attempted multiple calls
        assert error_count > 1

    def test_monitor_performance(self):
        """Test monitor performance with many updates"""
        monitor = ProgressMonitor(total_files=1000, update_interval=0.01)

        start_time = time.time()

        # Simulate processing many files quickly
        for i in range(100):
            monitor.record_file_processed(Path(f"file_{i}.txt"), 0.001)

        elapsed = time.time() - start_time

        # Should be very fast
        assert elapsed < 0.1  # Less than 100ms for 100 file records

        metrics = monitor.get_metrics()
        assert metrics.files_processed == 100
        assert metrics.throughput_files_per_sec > 100  # Should be very high


class TestMonitoringEdgeCases:
    """Test edge cases and error conditions"""

    def test_zero_files_monitoring(self):
        """Test monitoring with zero files"""
        monitor = ProgressMonitor(total_files=0)

        assert monitor.metrics.progress_percentage == 0.0
        assert monitor.metrics.is_complete is True  # 0/0 is complete

    def test_negative_timing_values(self):
        """Test handling of negative timing values"""
        monitor = ProgressMonitor(total_files=5)

        # These should be handled gracefully
        monitor.record_timing("test", -1.0)  # Negative timing
        monitor.add_wait_time(-0.5)  # Negative wait time

        # Monitor should still function
        metrics = monitor.get_metrics()
        assert isinstance(metrics, SimulationMetrics)

    def test_monitor_without_start(self):
        """Test monitor operations without starting"""
        monitor = ProgressMonitor(total_files=5)

        # Should work without starting the update thread
        monitor.record_file_processed(Path("test.txt"), 0.1)
        monitor.add_wait_time(1.0)

        metrics = monitor.get_metrics()
        assert metrics.files_processed == 1
        assert metrics.total_wait_time == 1.0

    def test_multiple_start_stop_cycles(self):
        """Test multiple start/stop cycles"""
        monitor = ProgressMonitor(total_files=5, update_interval=0.05)

        # Multiple start/stop cycles
        for _ in range(3):
            monitor.start()
            time.sleep(0.1)
            monitor.stop()

        # Should handle multiple cycles gracefully
        metrics = monitor.get_metrics()
        assert isinstance(metrics, SimulationMetrics)
