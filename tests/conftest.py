"""Pytest configuration and shared fixtures for NanoRunner testing.

This module provides comprehensive test configuration, shared fixtures,
and utilities for testing the NanoRunner nanopore sequencing simulator.

The fixtures are organized into categories:
- Basic test setup and configuration
- Data creation and management utilities
- Monitoring and performance test utilities
- File system and I/O test utilities
- Mock and isolation utilities
"""

import pytest
import logging
import tempfile
import threading
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from unittest.mock import MagicMock, patch

# Import our organized fixture modules
from .fixtures.data_fixtures import DataTestManager
from .fixtures.config_fixtures import ConfigBuilder


def pytest_configure(config):
    """Configure pytest markers and options."""
    # Test category markers
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "unit: marks tests as unit tests")
    config.addinivalue_line(
        "markers", "performance: marks tests as performance benchmarks"
    )
    config.addinivalue_line(
        "markers", "coverage: marks tests specifically for coverage improvement"
    )
    config.addinivalue_line(
        "markers",
        "practical: marks tests that download real genomes from NCBI (requires datasets CLI)",
    )

    # Pipeline-specific markers
    config.addinivalue_line(
        "markers", "nanometanf: marks tests specific to nanometanf pipeline integration"
    )
    config.addinivalue_line(
        "markers", "kraken: marks tests specific to Kraken pipeline integration"
    )
    config.addinivalue_line(
        "markers", "miniknife: marks tests specific to miniknife pipeline integration"
    )

    # System requirement markers
    config.addinivalue_line(
        "markers",
        "requires_psutil: marks tests that require psutil for resource monitoring",
    )
    config.addinivalue_line(
        "markers",
        "requires_threading: marks tests that use threading/concurrent features",
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add automatic markers based on test characteristics."""
    for item in items:
        # Auto-mark slow tests
        if "large_dataset" in item.nodeid or "performance" in item.nodeid:
            item.add_marker(pytest.mark.slow)

        # Auto-mark integration tests
        if "integration" in item.nodeid or "test_cli" in item.nodeid:
            item.add_marker(pytest.mark.integration)

        # Auto-mark unit tests (everything not marked as integration)
        if not any(mark.name == "integration" for mark in item.iter_markers()):
            item.add_marker(pytest.mark.unit)

        # Auto-mark coverage tests
        if "_coverage" in item.nodeid:
            item.add_marker(pytest.mark.coverage)


# ============================================================================
# Basic Test Configuration and Setup
# ============================================================================


@pytest.fixture(scope="session")
def test_session_info():
    """Provide information about the current test session."""
    return {
        "session_id": int(time.time()),
        "temp_base": Path(tempfile.gettempdir()) / "nanorunner_tests",
        "start_time": time.time(),
    }


@pytest.fixture
def mock_logging_config():
    """Fixture to mock logging configuration for consistent test output."""
    return {
        "level": logging.INFO,
        "format": "%(asctime)s - %(levelname)s - %(message)s",
        "datefmt": "%Y-%m-%d %H:%M:%S",
    }


@pytest.fixture
def test_directories(tmp_path):
    """Create standard test directory structure.

    Returns:
        Dict containing paths to standard test directories
    """
    directories = {
        "source": tmp_path / "source",
        "target": tmp_path / "target",
        "temp": tmp_path / "temp",
        "output": tmp_path / "output",
    }

    # Create all directories
    for directory in directories.values():
        directory.mkdir(parents=True, exist_ok=True)

    return directories


@pytest.fixture
def isolated_filesystem(tmp_path, monkeypatch):
    """Provide isolated filesystem for tests that modify the working directory.

    Changes working directory to a temporary location and restores it after test.
    """
    original_cwd = Path.cwd()
    monkeypatch.chdir(tmp_path)

    yield tmp_path

    # Cleanup is automatic via monkeypatch


# ============================================================================
# Data Management Fixtures
# ============================================================================


@pytest.fixture
def test_data_manager():
    """Provide a test data manager with automatic cleanup."""
    manager = DataTestManager()
    yield manager
    manager.cleanup()


@pytest.fixture
def config_builder(tmp_path):
    """Provide a configuration builder for flexible test setup."""
    return ConfigBuilder(tmp_path)


# ============================================================================
# Mock and Isolation Utilities
# ============================================================================


@pytest.fixture
def mock_file_operations():
    """Mock file operations for testing error conditions and edge cases."""
    mocks = {}

    with (
        patch("shutil.copy2") as mock_copy,
        patch("shutil.move") as mock_move,
        patch("pathlib.Path.symlink_to") as mock_symlink,
        patch("pathlib.Path.mkdir") as mock_mkdir,
    ):

        mocks["copy"] = mock_copy
        mocks["move"] = mock_move
        mocks["symlink"] = mock_symlink
        mocks["mkdir"] = mock_mkdir

        yield mocks


@pytest.fixture
def mock_time_operations():
    """Mock time-related operations for deterministic timing tests."""
    with patch("time.time") as mock_time, patch("time.sleep") as mock_sleep:

        # Set up a controllable time progression
        mock_time.side_effect = [i * 0.1 for i in range(1000)]  # 0.1s increments

        yield {"time": mock_time, "sleep": mock_sleep}


@pytest.fixture
def mock_system_resources():
    """Mock system resource monitoring for consistent test results."""
    mock_process = MagicMock()
    mock_process.cpu_percent.return_value = 45.0
    mock_process.memory_percent.return_value = 60.0
    mock_process.memory_info.return_value = MagicMock(rss=1024 * 1024 * 100)  # 100MB
    mock_process.open_files.return_value = []

    with (
        patch("psutil.Process", return_value=mock_process),
        patch("psutil.disk_usage") as mock_disk,
        patch("psutil.net_io_counters") as mock_net,
    ):

        mock_disk.return_value = MagicMock(
            total=1000 * 1024 * 1024 * 1024,  # 1TB
            used=500 * 1024 * 1024 * 1024,  # 500GB
            free=500 * 1024 * 1024 * 1024,  # 500GB
        )

        mock_net.return_value = MagicMock(
            bytes_sent=1024 * 1024, bytes_recv=2 * 1024 * 1024  # 1MB  # 2MB
        )

        yield {"process": mock_process, "disk": mock_disk, "network": mock_net}


# ============================================================================
# Performance and Timing Test Utilities
# ============================================================================


@pytest.fixture
def performance_context():
    """Provide context for performance testing with timing and resource tracking."""

    class PerformanceContext:
        def __init__(self):
            self.start_time = None
            self.end_time = None
            self.measurements = {}

        def start_measurement(self, name: str = "default"):
            """Start timing measurement."""
            self.start_time = time.time()
            return self

        def end_measurement(self, name: str = "default"):
            """End timing measurement and record result."""
            if self.start_time is None:
                raise ValueError("Must call start_measurement first")

            self.end_time = time.time()
            duration = self.end_time - self.start_time
            self.measurements[name] = duration
            return duration

        def assert_duration_under(self, seconds: float, name: str = "default"):
            """Assert that measurement completed under specified time."""
            if name not in self.measurements:
                raise ValueError(f"No measurement found for '{name}'")

            actual = self.measurements[name]
            assert (
                actual < seconds
            ), f"Operation took {actual:.3f}s, expected under {seconds}s"

        def assert_throughput_over(
            self, items_per_second: float, item_count: int, name: str = "default"
        ):
            """Assert that throughput meets minimum requirement."""
            if name not in self.measurements:
                raise ValueError(f"No measurement found for '{name}'")

            duration = self.measurements[name]
            actual_throughput = item_count / duration if duration > 0 else float("inf")

            assert actual_throughput >= items_per_second, (
                f"Throughput was {actual_throughput:.1f} items/s, "
                f"expected at least {items_per_second} items/s"
            )

    return PerformanceContext()


@pytest.fixture
def timing_control():
    """Provide utilities for controlling timing in tests."""

    class TimingControl:
        def __init__(self):
            self._paused = False
            self._step_mode = False
            self._step_event = threading.Event()

        def pause(self):
            """Pause timing progression."""
            self._paused = True

        def resume(self):
            """Resume timing progression."""
            self._paused = False
            if self._step_mode:
                self._step_event.set()

        def step(self):
            """Advance one step in step mode."""
            if self._step_mode:
                self._step_event.set()

        def enable_step_mode(self):
            """Enable step-by-step timing control."""
            self._step_mode = True
            self._step_event.clear()

        def wait_for_step(self, timeout: float = 1.0):
            """Wait for next step signal."""
            if self._step_mode:
                return self._step_event.wait(timeout)
            return True

    return TimingControl()


# ============================================================================
# Error Injection and Chaos Testing
# ============================================================================


@pytest.fixture
def error_injector():
    """Provide utilities for injecting errors during testing."""

    class ErrorInjector:
        def __init__(self):
            self.injection_count = 0
            self.max_injections = float("inf")
            self.error_probability = 0.0

        def set_error_rate(self, probability: float, max_count: int = None):
            """Set error injection rate."""
            self.error_probability = probability
            if max_count is not None:
                self.max_injections = max_count

        def should_inject_error(self) -> bool:
            """Determine if error should be injected."""
            if self.injection_count >= self.max_injections:
                return False

            if random.random() < self.error_probability:
                self.injection_count += 1
                return True
            return False

        def inject_file_error(self):
            """Inject file operation error."""
            if self.should_inject_error():
                raise PermissionError("Injected file operation error")

        def inject_network_error(self):
            """Inject network-related error."""
            if self.should_inject_error():
                raise ConnectionError("Injected network error")

        def inject_memory_error(self):
            """Inject memory-related error."""
            if self.should_inject_error():
                raise MemoryError("Injected memory error")

    return ErrorInjector()


# ============================================================================
# Test Data Validation Utilities
# ============================================================================


@pytest.fixture
def test_validator():
    """Provide utilities for validating test results and data."""

    class TestValidator:
        def validate_file_structure(
            self, path: Path, expected_files: List[str]
        ) -> bool:
            """Validate that directory contains expected files."""
            actual_files = {f.name for f in path.glob("*") if f.is_file()}
            expected_set = set(expected_files)

            missing = expected_set - actual_files
            extra = actual_files - expected_set

            if missing:
                raise AssertionError(f"Missing files: {missing}")
            if extra:
                raise AssertionError(f"Unexpected files: {extra}")

            return True

        def validate_timing_accuracy(
            self, expected: float, actual: float, tolerance: float = 0.1
        ) -> bool:
            """Validate timing is within acceptable tolerance."""
            diff = abs(expected - actual)
            max_diff = expected * tolerance

            if diff > max_diff:
                raise AssertionError(
                    f"Timing difference {diff:.3f}s exceeds tolerance "
                    f"{max_diff:.3f}s (expected: {expected:.3f}s, "
                    f"actual: {actual:.3f}s)"
                )

            return True

        def validate_performance_metrics(
            self, metrics: Dict[str, Any], requirements: Dict[str, Any]
        ) -> bool:
            """Validate performance metrics meet requirements."""
            for metric, requirement in requirements.items():
                if metric not in metrics:
                    raise AssertionError(f"Missing metric: {metric}")

                actual = metrics[metric]
                if isinstance(requirement, dict):
                    if "min" in requirement and actual < requirement["min"]:
                        raise AssertionError(
                            f"{metric} = {actual} below minimum {requirement['min']}"
                        )
                    if "max" in requirement and actual > requirement["max"]:
                        raise AssertionError(
                            f"{metric} = {actual} above maximum {requirement['max']}"
                        )
                else:
                    if actual != requirement:
                        raise AssertionError(
                            f"{metric} = {actual}, expected {requirement}"
                        )

            return True

    return TestValidator()


# ============================================================================
# Concurrency and Threading Test Utilities
# ============================================================================


@pytest.fixture
def thread_test_utilities():
    """Provide utilities for testing concurrent and threaded operations."""

    class ThreadTestUtilities:
        def __init__(self):
            self.threads = []
            self.events = {}
            self.results = {}

        def create_event(self, name: str) -> threading.Event:
            """Create a named threading event."""
            event = threading.Event()
            self.events[name] = event
            return event

        def run_concurrent(
            self, functions: List[callable], timeout: float = 5.0
        ) -> List[Any]:
            """Run functions concurrently and return results."""
            results = [None] * len(functions)
            threads = []

            def wrapper(index, func):
                try:
                    results[index] = func()
                except Exception as e:
                    results[index] = e

            # Start threads
            for i, func in enumerate(functions):
                thread = threading.Thread(target=wrapper, args=(i, func))
                thread.start()
                threads.append(thread)

            # Wait for completion
            for thread in threads:
                thread.join(timeout=timeout)
                if thread.is_alive():
                    raise TimeoutError(f"Thread did not complete within {timeout}s")

            self.threads.extend(threads)
            return results

        def assert_thread_safety(
            self,
            shared_resource,
            operations: List[callable],
            thread_count: int = 5,
            iterations: int = 10,
        ):
            """Test thread safety of shared resource operations."""
            results = []

            def worker():
                local_results = []
                for _ in range(iterations):
                    for operation in operations:
                        try:
                            result = operation(shared_resource)
                            local_results.append(("success", result))
                        except Exception as e:
                            local_results.append(("error", e))
                return local_results

            # Run workers concurrently
            workers = [worker] * thread_count
            all_results = self.run_concurrent(workers)

            # Analyze results for thread safety issues
            for worker_results in all_results:
                if isinstance(worker_results, Exception):
                    raise AssertionError(f"Worker failed: {worker_results}")
                results.extend(worker_results)

            return results

        def cleanup(self):
            """Clean up threading resources."""
            for thread in self.threads:
                if thread.is_alive():
                    thread.join(timeout=1.0)

    utilities = ThreadTestUtilities()
    yield utilities
    utilities.cleanup()


# ============================================================================
# Test Session Cleanup and Reporting
# ============================================================================


@pytest.fixture(scope="session", autouse=True)
def test_session_cleanup():
    """Automatic cleanup at end of test session."""
    yield

    # Cleanup any remaining temporary files
    import tempfile
    import shutil

    temp_dir = Path(tempfile.gettempdir())

    for item in temp_dir.glob("nanorunner_test_*"):
        if item.is_dir():
            try:
                shutil.rmtree(item)
            except (PermissionError, OSError):
                pass  # Best effort cleanup


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Custom terminal summary with test statistics."""
    if hasattr(terminalreporter, "stats"):
        stats = terminalreporter.stats

        # Count tests by category
        unit_tests = sum(1 for item in stats.get("passed", []) if "unit" in str(item))
        integration_tests = sum(
            1 for item in stats.get("passed", []) if "integration" in str(item)
        )
        coverage_tests = sum(
            1 for item in stats.get("passed", []) if "coverage" in str(item)
        )

        terminalreporter.write_line("")
        terminalreporter.write_line("=== NanoRunner Test Summary ===")
        terminalreporter.write_line(f"Unit Tests: {unit_tests}")
        terminalreporter.write_line(f"Integration Tests: {integration_tests}")
        terminalreporter.write_line(f"Coverage Tests: {coverage_tests}")
        terminalreporter.write_line("============================")


# ============================================================================
# Compatibility and Import Handling
# ============================================================================


def pytest_runtest_setup(item):
    """Setup for individual test runs with dependency checking."""
    # Check for psutil requirement
    if item.get_closest_marker("requires_psutil"):
        try:
            import psutil
        except ImportError:
            pytest.skip("psutil not available")

    # Check for threading requirements
    if item.get_closest_marker("requires_threading"):
        import threading

        if threading.active_count() > 1:
            pytest.skip("Other threads active, skipping threading test")


# Import random for error injection
import random
