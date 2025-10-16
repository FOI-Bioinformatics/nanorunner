"""Tests for enhanced ETA calculation and DetailedProgressMonitor"""

import pytest
import tempfile
import time
from pathlib import Path

from nanopore_simulator.core.monitoring import (
    ProgressMonitor,
    DetailedProgressMonitor,
    SimulationMetrics,
    ResourceMetrics,
    create_progress_monitor,
)


class TestEnhancedETACalculation:
    """Test enhanced ETA with trend analysis"""

    def test_eta_with_sufficient_history_improving_trend(self):
        """Test ETA calculation with improving throughput trend"""
        metrics = SimulationMetrics(files_total=100)
        metrics.files_processed = 50

        # Add throughput history showing improving trend
        # First half: slower throughput
        for _ in range(5):
            metrics.add_throughput_sample(5.0)

        # Second half: faster throughput
        for _ in range(5):
            metrics.add_throughput_sample(8.0)

        metrics.throughput_files_per_sec = 7.0  # Current avg

        # Estimate ETA with trend analysis
        metrics.estimate_eta()

        # Should detect improving trend
        assert metrics.eta_trend == "improving"
        assert metrics.eta_seconds is not None
        assert 0 < metrics.confidence_score <= 1.0

    def test_eta_with_sufficient_history_degrading_trend(self):
        """Test ETA calculation with degrading throughput trend"""
        metrics = SimulationMetrics(files_total=100)
        metrics.files_processed = 50

        # Add throughput history showing degrading trend
        # First half: faster throughput
        for _ in range(5):
            metrics.add_throughput_sample(10.0)

        # Second half: slower throughput
        for _ in range(5):
            metrics.add_throughput_sample(6.0)

        metrics.throughput_files_per_sec = 8.0  # Current avg

        # Estimate ETA with trend analysis
        metrics.estimate_eta()

        # Should detect degrading trend
        assert metrics.eta_trend == "degrading"
        assert metrics.eta_seconds is not None
        assert 0 < metrics.confidence_score <= 1.0

    def test_eta_with_sufficient_history_stable_trend(self):
        """Test ETA calculation with stable throughput trend"""
        metrics = SimulationMetrics(files_total=100)
        metrics.files_processed = 50

        # Add consistent throughput history
        for _ in range(10):
            metrics.add_throughput_sample(10.0)

        metrics.throughput_files_per_sec = 10.0

        # Estimate ETA with trend analysis
        metrics.estimate_eta()

        # Should detect stable trend
        assert metrics.eta_trend == "stable"
        assert metrics.eta_seconds is not None
        assert 0 < metrics.confidence_score <= 1.0

    def test_eta_with_small_history(self):
        """Test ETA with less than 5 samples - simple calculation"""
        metrics = SimulationMetrics(files_total=100)
        metrics.files_processed = 50

        # Add only 3 throughput samples
        for _ in range(3):
            metrics.add_throughput_sample(10.0)

        metrics.throughput_files_per_sec = 10.0

        # Estimate ETA
        metrics.estimate_eta()

        # Should use simple ETA with lower confidence
        assert metrics.eta_seconds is not None
        assert metrics.confidence_score == 0.5

    def test_eta_with_minimal_history(self):
        """Test ETA with less than 3 samples"""
        metrics = SimulationMetrics(files_total=100)
        metrics.files_processed = 50

        # Add only 2 throughput samples
        for _ in range(2):
            metrics.add_throughput_sample(10.0)

        metrics.throughput_files_per_sec = 10.0

        # Estimate ETA
        metrics.estimate_eta()

        # Should use simple ETA with low confidence
        assert metrics.eta_seconds is not None
        assert metrics.confidence_score == 0.3

    def test_eta_confidence_with_low_variance(self):
        """Test confidence score with consistent measurements"""
        metrics = SimulationMetrics(files_total=100)
        metrics.files_processed = 50

        # Add very consistent throughput history
        for _ in range(10):
            metrics.add_throughput_sample(10.0)

        metrics.throughput_files_per_sec = 10.0

        metrics.estimate_eta()

        # Should have high confidence due to low variance
        assert metrics.confidence_score > 0.9

    def test_eta_confidence_with_high_variance(self):
        """Test confidence score with variable measurements"""
        metrics = SimulationMetrics(files_total=100)
        metrics.files_processed = 50

        # Add variable throughput history
        variable_values = [5.0, 15.0, 7.0, 13.0, 6.0, 14.0, 8.0, 12.0, 9.0, 11.0]
        for val in variable_values:
            metrics.add_throughput_sample(val)

        metrics.throughput_files_per_sec = 10.0

        metrics.estimate_eta()

        # Should have lower confidence due to high variance
        assert metrics.confidence_score < 0.9


class TestDetailedProgressMonitor:
    """Test DetailedProgressMonitor class"""

    def test_detailed_monitor_creation(self):
        """Test creating detailed monitor"""
        monitor = DetailedProgressMonitor(total_files=100, update_interval=1.0)

        assert isinstance(monitor, DetailedProgressMonitor)
        assert isinstance(monitor, ProgressMonitor)
        assert monitor.metrics.files_total == 100
        assert monitor.batch_details == []
        assert monitor.file_details == []

    def test_detailed_monitor_batch_tracking(self):
        """Test batch tracking in detailed monitor"""
        monitor = DetailedProgressMonitor(total_files=10)

        # Start and end a batch
        start_time = monitor.start_batch()
        time.sleep(0.01)
        monitor.end_batch(start_time)

        # Should have recorded batch details
        assert len(monitor.batch_details) == 1
        assert monitor.batch_details[0]["batch_number"] == 1
        assert monitor.batch_details[0]["duration"] > 0

    def test_detailed_monitor_file_tracking(self):
        """Test file tracking in detailed monitor"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.fastq"
            test_file.write_text("@read1\nACGT\n+\n!!!!")

            monitor = DetailedProgressMonitor(total_files=10)

            # Record file
            monitor.record_file_processed(test_file, operation_time=0.1)

            # Should have recorded file details
            assert len(monitor.file_details) == 1
            assert monitor.file_details[0]["file_path"] == str(test_file)
            assert monitor.file_details[0]["operation_time"] == 0.1
            assert monitor.file_details[0]["size_bytes"] > 0

    def test_detailed_monitor_display(self):
        """Test detailed monitor display formatting"""
        monitor = DetailedProgressMonitor(total_files=100)

        # Add some data
        monitor.metrics.files_processed = 50
        monitor.metrics.total_bytes_processed = 1024 * 1024
        monitor.metrics.update_throughput()

        # Test display - should not raise
        monitor._detailed_display(monitor.metrics)

    def test_detailed_monitor_with_completion(self):
        """Test detailed monitor at completion"""
        monitor = DetailedProgressMonitor(total_files=10)

        # Simulate completion
        monitor.metrics.files_processed = 10
        monitor.metrics.total_bytes_processed = 1024 * 100
        monitor.metrics.update_throughput()

        # Display at completion - should trigger final summary
        monitor._detailed_display(monitor.metrics)

    def test_detailed_monitor_stats_logging(self):
        """Test detailed stats logging"""
        monitor = DetailedProgressMonitor(total_files=100)

        monitor.metrics.files_processed = 50
        monitor.metrics.total_bytes_processed = 1024 * 1024
        monitor.metrics.errors_encountered = 2
        monitor.metrics.update_throughput()

        # Log stats - should not raise
        monitor._log_detailed_stats(monitor.metrics)

    def test_detailed_monitor_final_summary_logging(self):
        """Test final summary logging"""
        monitor = DetailedProgressMonitor(total_files=100)

        monitor.metrics.files_processed = 100
        monitor.metrics.total_bytes_processed = 1024 * 1024 * 10
        monitor.metrics.errors_encountered = 3
        monitor.metrics.timing_breakdown = {
            "file_operations": 10.0,
            "directory_creation": 2.0,
            "waiting": 5.0,
        }
        monitor.metrics.update_throughput()

        # Log final summary - should not raise
        monitor._log_final_summary(monitor.metrics)

    def test_create_progress_monitor_detailed_type(self):
        """Test factory creates detailed monitor"""
        monitor = create_progress_monitor(100, monitor_type="detailed", update_interval=0.5)

        assert isinstance(monitor, DetailedProgressMonitor)
        assert monitor.update_interval == 0.5

    def test_detailed_monitor_with_batch_details(self):
        """Test detailed monitor tracks batch file counts"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file1 = Path(tmpdir) / "test1.fastq"
            test_file2 = Path(tmpdir) / "test2.fastq"
            test_file1.write_text("@read1\nACGT\n+\n!!!!")
            test_file2.write_text("@read2\nACGT\n+\n!!!!")

            monitor = DetailedProgressMonitor(total_files=10)

            # Start batch
            start_time = monitor.start_batch()

            # Record files in batch
            monitor.record_file_processed(test_file1)
            monitor.record_file_processed(test_file2)

            # End batch
            monitor.end_batch(start_time)

            # Batch should have file count
            assert len(monitor.batch_details) == 1
            assert monitor.batch_details[0]["batch_number"] == 1
            assert len(monitor.file_details) == 2


class TestEnhancedMonitoringFeatures:
    """Test various enhanced monitoring features"""

    def test_monitor_with_resource_metrics_display(self):
        """Test monitor displays with resource metrics"""
        monitor = ProgressMonitor(100, enable_resources=True)

        # Add resource metrics
        monitor.metrics.resource_metrics = ResourceMetrics(
            cpu_percent=50.0, memory_percent=60.0
        )
        monitor.metrics.files_processed = 50
        monitor.metrics.update_throughput()

        # Display should include resources
        monitor._default_display(monitor.metrics)

    def test_monitor_final_summary_with_resources(self):
        """Test final summary includes resource info"""
        monitor = ProgressMonitor(100, enable_resources=True)

        monitor.metrics.files_processed = 100
        monitor.metrics.total_bytes_processed = 1024 * 1024
        monitor.metrics.peak_memory_mb = 100.0
        monitor.metrics.peak_cpu_percent = 80.0
        monitor.metrics.update_throughput()

        # Add throughput history for performance insights
        for _ in range(10):
            monitor.metrics.add_throughput_sample(5.0)
        monitor.metrics.add_throughput_sample(15.0)  # Create variation

        # Print final summary
        monitor._print_final_summary(monitor.metrics)

    def test_monitor_final_summary_with_errors(self):
        """Test final summary includes error count"""
        monitor = ProgressMonitor(100)

        monitor.metrics.files_processed = 100
        monitor.metrics.total_bytes_processed = 1024 * 1024
        monitor.metrics.errors_encountered = 5
        monitor.metrics.update_throughput()

        # Print final summary
        monitor._print_final_summary(monitor.metrics)

    def test_monitor_zero_files_display(self):
        """Test display with zero files"""
        monitor = ProgressMonitor(0)

        # Should not crash with zero files
        monitor._default_display(monitor.metrics)
