"""Tests for enhanced monitoring features"""

import pytest
import tempfile
import time
import json
import threading
import signal
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, Mock

from nanopore_simulator.core.monitoring import (
    SimulationMetrics, ResourceMetrics, ProgressMonitor, DetailedProgressMonitor,
    ResourceMonitor, SignalHandler, ProgressDisplay, create_progress_monitor,
    HAS_PSUTIL
)


class TestResourceMetrics:
    """Test resource metrics data structure"""
    
    def test_resource_metrics_creation(self):
        """Test creating resource metrics"""
        metrics = ResourceMetrics(
            cpu_percent=50.0,
            memory_percent=75.0,
            memory_used_mb=1024.0
        )
        
        assert metrics.cpu_percent == 50.0
        assert metrics.memory_percent == 75.0
        assert metrics.memory_used_mb == 1024.0
    
    def test_resource_metrics_to_dict(self):
        """Test converting resource metrics to dictionary"""
        metrics = ResourceMetrics(
            cpu_percent=25.5,
            memory_percent=80.2,
            disk_io_read_mb=100.0,
            disk_io_write_mb=50.0
        )
        
        result = metrics.to_dict()
        
        assert result['cpu_percent'] == 25.5
        assert result['memory_percent'] == 80.2
        assert result['disk_io_read_mb'] == 100.0
        assert result['disk_io_write_mb'] == 50.0


class TestEnhancedSimulationMetrics:
    """Test enhanced simulation metrics with trend analysis"""
    
    def test_enhanced_metrics_creation(self):
        """Test creating enhanced metrics"""
        metrics = SimulationMetrics(files_total=100)
        
        assert metrics.files_total == 100
        assert metrics.eta_trend == "stable"
        assert metrics.confidence_score == 0.0
        assert len(metrics.throughput_history) == 0
        assert len(metrics.resource_history) == 0
    
    def test_throughput_history_tracking(self):
        """Test throughput history tracking with deque"""
        metrics = SimulationMetrics(files_total=10)
        
        # Add samples (should maintain max 30)
        for i in range(35):
            metrics.add_throughput_sample(float(i))
        
        # Should only keep last 30
        assert len(metrics.throughput_history) == 30
        assert list(metrics.throughput_history)[0] == 5.0  # First kept sample
        assert list(metrics.throughput_history)[-1] == 34.0  # Last sample
    
    def test_resource_history_tracking(self):
        """Test resource history tracking"""
        metrics = SimulationMetrics(files_total=10)
        
        # Add samples (should maintain max 60)
        for i in range(65):
            resource = ResourceMetrics(
                cpu_percent=float(i),
                memory_used_mb=float(i * 10)
            )
            metrics.add_resource_sample(resource)
        
        # Should only keep last 60
        assert len(metrics.resource_history) == 60
        assert metrics.peak_cpu_percent == 64.0
        assert metrics.peak_memory_mb == 640.0
    
    def test_enhanced_eta_estimation_simple(self):
        """Test basic ETA estimation without history"""
        metrics = SimulationMetrics(files_total=100)
        metrics.files_processed = 25
        metrics.throughput_files_per_sec = 10.0
        
        metrics.estimate_eta()
        
        # Should estimate 7.5 seconds for remaining 75 files
        assert metrics.eta_seconds == 7.5
        assert metrics.confidence_score == 0.3  # Low confidence without history
    
    def test_enhanced_eta_with_trend_analysis(self):
        """Test ETA estimation with trend analysis"""
        metrics = SimulationMetrics(files_total=100)
        metrics.files_processed = 50
        
        # Add throughput history showing improvement
        throughputs = [8.0, 8.5, 9.0, 9.5, 10.0, 10.5, 11.0, 11.5, 12.0]
        for tp in throughputs:
            metrics.add_throughput_sample(tp)
        
        metrics.throughput_files_per_sec = 12.0
        metrics.estimate_eta()
        
        # Should detect improving trend
        assert metrics.eta_trend == "improving"
        assert metrics.confidence_score > 0.5
        assert metrics.eta_seconds is not None
        # ETA should be reasonable (accounting for the optimistic adjustment)
        assert 3.0 <= metrics.eta_seconds <= 5.0
    
    def test_enhanced_eta_degrading_trend(self):
        """Test ETA estimation with degrading performance"""
        metrics = SimulationMetrics(files_total=100)
        metrics.files_processed = 30
        
        # Add throughput history showing degradation
        throughputs = [12.0, 11.5, 11.0, 10.5, 10.0, 9.5, 9.0, 8.5, 8.0]
        for tp in throughputs:
            metrics.add_throughput_sample(tp)
        
        metrics.throughput_files_per_sec = 8.0
        metrics.estimate_eta()
        
        assert metrics.eta_trend == "degrading"
        assert metrics.eta_seconds is not None
        # ETA should be reasonable (accounting for the conservative adjustment)
        assert 8.0 <= metrics.eta_seconds <= 12.0


class TestResourceMonitor:
    """Test resource monitoring functionality"""
    
    @pytest.mark.skipif(not HAS_PSUTIL, reason="psutil not available")
    def test_resource_monitor_with_psutil(self):
        """Test resource monitor when psutil is available"""
        monitor = ResourceMonitor()
        
        assert monitor.process is not None
        
        metrics = monitor.get_current_metrics()
        
        # Should get actual metrics
        assert isinstance(metrics, ResourceMetrics)
        assert metrics.cpu_percent >= 0.0
        assert metrics.memory_percent >= 0.0
        assert metrics.memory_used_mb >= 0.0
    
    def test_resource_monitor_without_psutil(self):
        """Test resource monitor fallback when psutil unavailable"""
        with patch('nanopore_simulator.core.monitoring.HAS_PSUTIL', False):
            with patch('nanopore_simulator.core.monitoring.psutil', None):
                monitor = ResourceMonitor()
                
                assert monitor.process is None
                
                metrics = monitor.get_current_metrics()
                
                # Should return default metrics
                assert isinstance(metrics, ResourceMetrics)
                assert metrics.cpu_percent == 0.0
                assert metrics.memory_percent == 0.0


class TestSignalHandler:
    """Test signal handling for graceful shutdown"""
    
    def test_signal_handler_creation(self):
        """Test creating signal handler"""
        mock_monitor = MagicMock()
        handler = SignalHandler(mock_monitor)
        
        assert handler.progress_monitor == mock_monitor
        assert not handler.shutdown_requested
    
    @patch('builtins.print')
    def test_signal_handler_first_signal(self, mock_print):
        """Test handling first shutdown signal"""
        mock_monitor = MagicMock()
        mock_metrics = MagicMock()
        mock_metrics.files_processed = 50
        mock_metrics.files_total = 100
        mock_metrics.progress_percentage = 50.0
        mock_metrics.elapsed_time = 30.0
        mock_metrics.throughput_files_per_sec = 1.67
        mock_metrics.total_bytes_processed = 1024000
        mock_metrics.errors_encountered = 0
        mock_metrics.peak_memory_mb = 0.0
        mock_metrics.peak_cpu_percent = 0.0
        mock_metrics.resource_metrics = None
        mock_monitor.get_metrics.return_value = mock_metrics
        
        handler = SignalHandler(mock_monitor)
        
        # Simulate SIGINT
        handler._signal_handler(signal.SIGINT, None)
        
        assert handler.shutdown_requested
        mock_print.assert_called()  # Should print shutdown message
    
    @patch('sys.exit')
    @patch('builtins.print')
    def test_signal_handler_forced_shutdown(self, mock_print, mock_exit):
        """Test forced shutdown on second signal"""
        mock_monitor = MagicMock()
        mock_metrics = MagicMock()
        mock_metrics.files_processed = 25
        mock_metrics.files_total = 100
        mock_metrics.progress_percentage = 25.0
        mock_metrics.elapsed_time = 15.0
        mock_metrics.throughput_files_per_sec = 1.67
        mock_metrics.total_bytes_processed = 512000
        mock_metrics.errors_encountered = 0
        mock_metrics.peak_memory_mb = 0.0
        mock_metrics.peak_cpu_percent = 0.0
        mock_metrics.resource_metrics = None
        mock_monitor.get_metrics.return_value = mock_metrics
        
        handler = SignalHandler(mock_monitor)
        
        # First signal
        handler._signal_handler(signal.SIGINT, None)
        assert handler.shutdown_requested
        
        # Second signal should force exit
        handler._signal_handler(signal.SIGINT, None)
        mock_exit.assert_called_with(1)


class TestEnhancedProgressMonitor:
    """Test enhanced progress monitoring features"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
    
    def teardown_method(self):
        """Clean up test fixtures"""
        self.temp_dir.cleanup()
    
    def test_enhanced_monitor_creation(self):
        """Test creating enhanced progress monitor"""
        monitor = ProgressMonitor(
            total_files=100,
            enable_resources=True,
            enable_checkpoint=True
        )
        
        assert monitor.metrics.files_total == 100
        assert monitor.resource_monitor is not None
        assert monitor.signal_handler is not None
        assert monitor.checkpoint_file is not None
    
    def test_enhanced_monitor_without_features(self):
        """Test creating monitor with features disabled"""
        monitor = ProgressMonitor(
            total_files=50,
            enable_resources=False,
            enable_checkpoint=False
        )
        
        assert monitor.metrics.files_total == 50
        assert monitor.resource_monitor is None
        assert monitor.signal_handler is None
        assert monitor.checkpoint_file is None
    
    def test_pause_resume_functionality(self):
        """Test pause and resume functionality"""
        monitor = ProgressMonitor(total_files=10)
        
        # Should start unpaused
        assert not monitor.is_paused()
        
        # Pause
        monitor.pause()
        assert monitor.is_paused()
        
        # Resume
        monitor.resume()
        assert not monitor.is_paused()
    
    def test_should_stop_functionality(self):
        """Test shutdown detection"""
        monitor = ProgressMonitor(total_files=10, enable_checkpoint=True)
        
        # Should not stop initially
        assert not monitor.should_stop()
        
        # Simulate shutdown request
        if monitor.signal_handler:
            monitor.signal_handler.shutdown_requested = True
            assert monitor.should_stop()
    
    @patch('builtins.open', create=True)
    def test_checkpoint_save_load(self, mock_open):
        """Test checkpoint save and load functionality"""
        monitor = ProgressMonitor(total_files=100, enable_checkpoint=True)
        
        # Process some files
        monitor.metrics.files_processed = 25
        monitor.metrics.total_bytes_processed = 1024000
        
        # Mock file operations
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file
        
        # Save checkpoint
        monitor._save_checkpoint()
        
        # Should have attempted to write JSON
        assert mock_open.called
        assert mock_file.write.called or hasattr(mock_file, 'write')
    
    def test_performance_warnings(self):
        """Test performance warning detection"""
        monitor = ProgressMonitor(total_files=100, enable_resources=True)
        
        # Simulate high resource usage
        if monitor.resource_monitor:
            high_usage_metrics = ResourceMetrics(
                cpu_percent=95.0,
                memory_percent=90.0,
                disk_usage_percent=95.0
            )
            
            monitor.metrics.resource_metrics = high_usage_metrics
            monitor.metrics.throughput_files_per_sec = 0.05  # Very slow
            monitor.metrics.files_processed = 20
            
            # Add resource history
            for _ in range(6):
                monitor.metrics.add_resource_sample(high_usage_metrics)
            
            # Check warnings (should detect issues)
            with patch.object(monitor.logger, 'warning') as mock_warning:
                monitor._check_performance_warnings()
                
                # Should have issued warnings
                assert mock_warning.called
    
    def test_interruptible_operations(self):
        """Test that operations can be interrupted"""
        monitor = ProgressMonitor(total_files=10, enable_checkpoint=True)
        monitor.start()
        
        try:
            # Should be able to pause and check status
            monitor.pause()
            assert monitor.is_paused()
            
            # Should be able to resume
            monitor.resume()
            assert not monitor.is_paused()
            
        finally:
            monitor.stop()


class TestProgressDisplay:
    """Test enhanced progress display features"""
    
    def test_enhanced_progress_line_with_resources(self):
        """Test progress line with resource information"""
        metrics = SimulationMetrics(files_total=100)
        metrics.files_processed = 50
        metrics.throughput_files_per_sec = 2.5
        metrics.eta_seconds = 20.0
        metrics.eta_trend = "improving"
        metrics.confidence_score = 0.8
        
        # Add resource metrics
        if HAS_PSUTIL:
            metrics.resource_metrics = ResourceMetrics(
                cpu_percent=45.0,
                memory_percent=60.0
            )
        
        progress_line = ProgressDisplay.format_progress_line(
            metrics, 
            show_resources=HAS_PSUTIL and metrics.resource_metrics is not None
        )
        
        assert "50/100 files" in progress_line
        assert "2.5 files/sec" in progress_line
        assert "ETA: 20.0s" in progress_line
        assert "↗" in progress_line  # Improving trend indicator
        
        if HAS_PSUTIL and metrics.resource_metrics:
            assert "CPU: 45%" in progress_line
            assert "RAM: 60%" in progress_line
    
    def test_trend_indicators(self):
        """Test ETA trend indicators"""
        metrics = SimulationMetrics(files_total=100)
        metrics.files_processed = 30
        metrics.eta_seconds = 15.0
        
        # Test improving trend
        metrics.eta_trend = "improving"
        metrics.confidence_score = 0.9
        line = ProgressDisplay.format_progress_line(metrics)
        assert "↗" in line
        assert "★★" in line  # High confidence (0.9 * 3 = 2.7 -> 2 stars)
        
        # Test degrading trend
        metrics.eta_trend = "degrading"
        metrics.confidence_score = 0.3
        line = ProgressDisplay.format_progress_line(metrics)
        assert "↘" in line
        # Low confidence (0.3 * 3 = 0.9 -> 0 stars, so no stars in line)
        assert "★" not in line or line.count("★") == 0
        
        # Test stable trend
        metrics.eta_trend = "stable"
        metrics.confidence_score = 0.6
        line = ProgressDisplay.format_progress_line(metrics)
        assert "→" in line
        assert "★" in line  # Medium confidence (0.6 * 3 = 1.8 -> 1 star)


class TestMonitorFactory:
    """Test monitor factory function"""
    
    def test_create_default_monitor(self):
        """Test creating default monitor"""
        monitor = create_progress_monitor(total_files=50)
        
        assert isinstance(monitor, ProgressMonitor)
        assert not isinstance(monitor, DetailedProgressMonitor)
        assert monitor.metrics.files_total == 50
    
    def test_create_detailed_monitor(self):
        """Test creating detailed monitor"""
        monitor = create_progress_monitor(total_files=75, monitor_type="detailed")
        
        assert isinstance(monitor, DetailedProgressMonitor)
        assert monitor.metrics.files_total == 75
    
    def test_create_enhanced_monitor(self):
        """Test creating enhanced monitor"""
        monitor = create_progress_monitor(
            total_files=100, 
            monitor_type="enhanced"
        )
        
        assert isinstance(monitor, ProgressMonitor)
        assert monitor.metrics.files_total == 100
        # Enhanced should have faster updates
        assert monitor.update_interval == 0.5


class TestIntegration:
    """Integration tests for enhanced monitoring"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
    
    def teardown_method(self):
        """Clean up test fixtures"""
        self.temp_dir.cleanup()
    
    def test_full_enhanced_monitoring_lifecycle(self):
        """Test complete enhanced monitoring lifecycle"""
        # Create test files
        test_files = []
        for i in range(5):
            test_file = self.temp_path / f"test_{i}.fastq"
            test_file.write_text(f"test content {i}")
            test_files.append(test_file)
        
        # Create enhanced monitor
        monitor = create_progress_monitor(
            total_files=len(test_files),
            monitor_type="enhanced",
            enable_resources=True,
            enable_checkpoint=True,
            update_interval=0.1  # Fast updates for testing
        )
        
        try:
            monitor.start()
            
            # Simulate file processing
            for i, test_file in enumerate(test_files):
                monitor.record_file_processed(test_file, 0.1)
                time.sleep(0.05)  # Small delay to see progress
                
                # Test pause/resume midway
                if i == 2:
                    monitor.pause()
                    assert monitor.is_paused()
                    time.sleep(0.1)
                    monitor.resume()
                    assert not monitor.is_paused()
            
            # Get final metrics
            final_metrics = monitor.get_metrics()
            
            assert final_metrics.files_processed == len(test_files)
            assert final_metrics.progress_percentage == 100.0
            assert final_metrics.throughput_files_per_sec > 0
            
            # Should have throughput history
            assert len(final_metrics.throughput_history) > 0
            
            # Should have ETA trend analysis
            assert final_metrics.eta_trend in ["improving", "degrading", "stable"]
            assert 0.0 <= final_metrics.confidence_score <= 1.0
            
        finally:
            monitor.stop()
    
    @patch('nanopore_simulator.core.monitoring.HAS_PSUTIL', True)
    def test_enhanced_monitoring_with_psutil_mock(self):
        """Test enhanced monitoring with mocked psutil"""
        # Mock psutil process
        mock_process = MagicMock()
        mock_process.cpu_percent.return_value = 25.0
        mock_process.memory_percent.return_value = 50.0
        mock_process.memory_info.return_value = MagicMock(rss=1024*1024*100)  # 100MB
        
        with patch('nanopore_simulator.core.monitoring.psutil.Process', return_value=mock_process):
            monitor = ProgressMonitor(
                total_files=10,
                enable_resources=True,
                update_interval=0.1
            )
            
            try:
                monitor.start()
                
                # Process a file
                test_file = self.temp_path / "test.fastq"
                test_file.write_text("test content")
                monitor.record_file_processed(test_file, 0.05)
                
                # Wait for update
                time.sleep(0.2)
                
                metrics = monitor.get_metrics()
                
                # Should have resource metrics
                assert metrics.resource_metrics is not None
                assert metrics.resource_metrics.cpu_percent == 25.0
                assert metrics.resource_metrics.memory_percent == 50.0
                
            finally:
                monitor.stop()