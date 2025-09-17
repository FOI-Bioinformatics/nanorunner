"""Monitoring test fixtures and utilities.

This module provides fixtures for testing monitoring functionality,
including progress monitoring, resource tracking, and signal handling.
"""

import pytest
import threading
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from unittest.mock import MagicMock, patch, Mock
from contextlib import contextmanager

from nanopore_simulator.core.monitoring import (
    ProgressMonitor, ResourceMonitor, SignalHandler
)


@pytest.fixture
def mock_progress_monitor():
    """Create a mock progress monitor for testing.
    
    Returns:
        MagicMock configured to behave like ProgressMonitor
    """
    mock = MagicMock(spec=ProgressMonitor)
    mock.total_files = 100
    mock.processed_files = 0
    mock.current_file = None
    mock.start_time = time.time()
    mock.is_running = False
    
    # Mock methods
    mock.start.return_value = None
    mock.stop.return_value = None
    mock.record_file_processed.return_value = None
    mock.get_stats.return_value = {
        'total_files': 100,
        'processed_files': 0,
        'progress_percentage': 0.0,
        'files_per_second': 0.0,
        'estimated_completion': None
    }
    
    return mock


@pytest.fixture
def mock_resource_monitor():
    """Create a mock resource monitor for testing.
    
    Returns:
        MagicMock configured to behave like ResourceMonitor
    """
    mock = MagicMock(spec=ResourceMonitor)
    mock.is_monitoring = False
    mock.metrics = {
        'cpu_percent': 50.0,
        'memory_percent': 60.0,
        'disk_usage': 70.0,
        'network_io': {'bytes_sent': 1000, 'bytes_recv': 2000}
    }
    
    # Mock methods
    mock.start_monitoring.return_value = None
    mock.stop_monitoring.return_value = None
    mock.get_current_metrics.return_value = mock.metrics
    mock.get_metrics_history.return_value = [mock.metrics]
    
    return mock


@pytest.fixture
def mock_signal_handler():
    """Create a mock signal handler for testing.
    
    Returns:
        MagicMock configured to behave like SignalHandler
    """
    mock = MagicMock(spec=SignalHandler)
    mock.shutdown_requested = False
    mock.pause_requested = False
    
    # Mock methods
    mock.setup_handlers.return_value = None
    mock.cleanup_handlers.return_value = None
    mock.request_shutdown.return_value = None
    mock.request_pause.return_value = None
    mock.is_shutdown_requested.return_value = False
    mock.is_pause_requested.return_value = False
    
    return mock


@pytest.fixture
@contextmanager
def monitoring_test_context():
    """Context manager for monitoring tests with proper setup/teardown.
    
    Provides a controlled environment for testing monitoring functionality
    with automatic cleanup of threads and resources.
    """
    # Track created monitors for cleanup
    monitors = []
    threads = []
    
    class MonitoringContext:
        def __init__(self):
            self.monitors = monitors
            self.threads = threads
            
        def create_progress_monitor(self, total_files=10, **kwargs):
            """Create a real progress monitor for testing."""
            monitor = ProgressMonitor(total_files=total_files, **kwargs)
            self.monitors.append(monitor)
            return monitor
            
        def create_resource_monitor(self, **kwargs):
            """Create a real resource monitor for testing."""
            monitor = ResourceMonitor(**kwargs)
            self.monitors.append(monitor)
            return monitor
            
        def create_signal_handler(self, progress_monitor, **kwargs):
            """Create a real signal handler for testing."""
            handler = SignalHandler(progress_monitor=progress_monitor, **kwargs)
            self.monitors.append(handler)
            return handler
            
        def run_in_thread(self, target, *args, **kwargs):
            """Run a function in a separate thread for testing."""
            thread = threading.Thread(target=target, args=args, kwargs=kwargs)
            self.threads.append(thread)
            thread.start()
            return thread
            
        def wait_for_all_threads(self, timeout=5.0):
            """Wait for all created threads to complete."""
            for thread in self.threads:
                thread.join(timeout=timeout)
    
    context = MonitoringContext()
    
    try:
        yield context
    finally:
        # Cleanup all monitors
        for monitor in monitors:
            if hasattr(monitor, 'stop') and callable(monitor.stop):
                try:
                    monitor.stop()
                except:
                    pass
            if hasattr(monitor, 'stop_monitoring') and callable(monitor.stop_monitoring):
                try:
                    monitor.stop_monitoring()
                except:
                    pass
            if hasattr(monitor, 'cleanup_handlers') and callable(monitor.cleanup_handlers):
                try:
                    monitor.cleanup_handlers()
                except:
                    pass
        
        # Wait for threads to complete
        for thread in threads:
            if thread.is_alive():
                thread.join(timeout=1.0)


@pytest.fixture
@contextmanager
def capture_monitoring_output():
    """Capture monitoring output for testing display functionality.
    
    Returns:
        Context manager that captures printed output and progress updates
    """
    import io
    import sys
    from contextlib import redirect_stdout, redirect_stderr
    
    # Capture stdout and stderr
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    
    class OutputCapture:
        def __init__(self, stdout_buf, stderr_buf):
            self.stdout = stdout_buf
            self.stderr = stderr_buf
            
        def get_stdout(self):
            """Get captured stdout content."""
            return self.stdout.getvalue()
            
        def get_stderr(self):
            """Get captured stderr content."""
            return self.stderr.getvalue()
            
        def get_all_output(self):
            """Get all captured output."""
            return {
                'stdout': self.get_stdout(),
                'stderr': self.get_stderr()
            }
            
        def assert_contains(self, text, stream='stdout'):
            """Assert that output contains specific text."""
            content = self.get_stdout() if stream == 'stdout' else self.get_stderr()
            assert text in content, f"Text '{text}' not found in {stream}: {content}"
            
        def assert_progress_shown(self):
            """Assert that progress information is displayed."""
            output = self.get_stdout() + self.get_stderr()
            progress_indicators = ['%', 'progress', 'processed', 'files/s', 'ETA']
            assert any(indicator in output.lower() for indicator in progress_indicators), \
                f"No progress indicators found in output: {output}"
    
    capture = OutputCapture(stdout_capture, stderr_capture)
    
    try:
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            yield capture
    finally:
        pass


# Additional monitoring test utilities

def create_test_progress_events(count=10):
    """Create a series of test progress events.
    
    Args:
        count: Number of progress events to create
        
    Returns:
        List of progress event dictionaries
    """
    events = []
    for i in range(count):
        events.append({
            'file_path': Path(f'/test/file_{i:03d}.fastq'),
            'timestamp': time.time() + i * 0.1,
            'file_size': 1000 + i * 100,
            'processing_time': 0.05 + i * 0.01
        })
    return events


def simulate_monitoring_scenario(monitor, events, delay=0.01):
    """Simulate a monitoring scenario with timed events.
    
    Args:
        monitor: Monitor instance to test
        events: List of events to simulate
        delay: Delay between events in seconds
    """
    monitor.start()
    
    try:
        for event in events:
            time.sleep(delay)
            if hasattr(monitor, 'record_file_processed'):
                monitor.record_file_processed(event['file_path'])
            elif hasattr(monitor, 'update'):
                monitor.update(event)
    finally:
        monitor.stop()


class MockMetricsCollector:
    """Mock metrics collector for testing resource monitoring."""
    
    def __init__(self):
        self.cpu_percent = 50.0
        self.memory_percent = 60.0
        self.disk_usage = 70.0
        self.network_io = {'bytes_sent': 1000, 'bytes_recv': 2000}
        self.call_count = 0
        
    def get_cpu_percent(self):
        self.call_count += 1
        return self.cpu_percent
        
    def get_memory_percent(self):
        self.call_count += 1
        return self.memory_percent
        
    def get_disk_usage(self, path='/'):
        self.call_count += 1
        return self.disk_usage
        
    def get_network_io(self):
        self.call_count += 1
        return self.network_io


@pytest.fixture
def mock_metrics_collector():
    """Provide a mock metrics collector for testing."""
    return MockMetricsCollector()


# Performance monitoring utilities

class MonitoringPerformanceProfiler:
    """Profile monitoring system performance for testing."""
    
    def __init__(self):
        self.metrics = {}
        self.start_times = {}
        
    def start_timing(self, name):
        """Start timing a monitoring operation."""
        self.start_times[name] = time.time()
        
    def end_timing(self, name):
        """End timing a monitoring operation."""
        if name in self.start_times:
            duration = time.time() - self.start_times[name]
            self.metrics[name] = duration
            del self.start_times[name]
            return duration
        return None
        
    def get_metrics(self):
        """Get all timing metrics."""
        return self.metrics.copy()
        
    def assert_performance(self, name, max_duration):
        """Assert that an operation completed within time limit."""
        if name not in self.metrics:
            raise ValueError(f"No metrics found for '{name}'")
        actual = self.metrics[name]
        assert actual <= max_duration, \
            f"Operation '{name}' took {actual:.3f}s, expected <= {max_duration}s"


@pytest.fixture
def monitoring_profiler():
    """Provide a monitoring performance profiler."""
    return MonitoringPerformanceProfiler()