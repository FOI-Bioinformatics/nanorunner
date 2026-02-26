"""Tests for progress monitoring and resource tracking."""

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nanopore_simulator.monitoring import (
    NullMonitor,
    ProgressMonitor,
    SimulationMetrics,
    create_monitor,
    format_bytes,
    format_time,
)


# ---------------------------------------------------------------------------
# SimulationMetrics
# ---------------------------------------------------------------------------


class TestSimulationMetrics:
    """Metrics dataclass behaviour."""

    def test_defaults(self) -> None:
        m = SimulationMetrics(files_total=100)
        assert m.files_processed == 0
        assert m.files_total == 100
        assert m.bytes_processed == 0
        assert m.eta_seconds is None
        assert m.start_time > 0

    def test_progress_percentage_zero(self) -> None:
        m = SimulationMetrics(files_total=0)
        assert m.progress_percentage == 0.0

    def test_progress_percentage(self) -> None:
        m = SimulationMetrics(files_total=50, files_processed=25)
        assert m.progress_percentage == 50.0

    def test_progress_percentage_complete(self) -> None:
        m = SimulationMetrics(files_total=10, files_processed=10)
        assert m.progress_percentage == 100.0

    def test_elapsed(self) -> None:
        m = SimulationMetrics(files_total=10)
        m.start_time = time.time() - 5.0
        assert 4.5 <= m.elapsed <= 6.0

    def test_throughput(self) -> None:
        m = SimulationMetrics(files_total=100, files_processed=50)
        m.start_time = time.time() - 10.0
        assert 4.0 <= m.throughput <= 6.0

    def test_throughput_zero_elapsed(self) -> None:
        m = SimulationMetrics(files_total=100, files_processed=0)
        assert m.throughput == 0.0


# ---------------------------------------------------------------------------
# ProgressMonitor
# ---------------------------------------------------------------------------


class TestProgressMonitor:
    """Core progress monitor operations."""

    def test_start_and_stop(self) -> None:
        mon = ProgressMonitor(total_files=10)
        mon.start()
        assert mon._update_thread is not None
        assert mon._update_thread.is_alive()
        mon.stop()
        # Thread should have joined
        assert not mon._update_thread.is_alive()

    def test_update_increments(self) -> None:
        mon = ProgressMonitor(total_files=10)
        mon.update(bytes_delta=1024)
        mon.update(bytes_delta=2048)
        metrics = mon.get_metrics()
        assert metrics.files_processed == 2
        assert metrics.bytes_processed == 3072

    def test_progress_percentage(self) -> None:
        mon = ProgressMonitor(total_files=4)
        mon.update()
        mon.update()
        metrics = mon.get_metrics()
        assert metrics.progress_percentage == 50.0

    def test_estimate_eta_no_progress(self) -> None:
        mon = ProgressMonitor(total_files=100)
        metrics = mon.get_metrics()
        assert metrics.eta_seconds is None

    def test_estimate_eta_with_progress(self) -> None:
        mon = ProgressMonitor(total_files=100)
        # Simulate some progress
        mon._metrics.start_time = time.time() - 10.0
        for _ in range(50):
            mon.update()
        metrics = mon.get_metrics()
        # ETA should be approximately 10 seconds (50 files in 10s, 50 remaining)
        assert metrics.eta_seconds is not None
        assert 5.0 <= metrics.eta_seconds <= 20.0

    def test_estimate_eta_complete(self) -> None:
        mon = ProgressMonitor(total_files=5)
        for _ in range(5):
            mon.update()
        metrics = mon.get_metrics()
        assert metrics.eta_seconds == 0.0

    def test_pause_and_resume(self) -> None:
        mon = ProgressMonitor(total_files=10)
        assert not mon.is_paused()
        mon.pause()
        assert mon.is_paused()
        mon.resume()
        assert not mon.is_paused()

    def test_get_metrics_returns_copy(self) -> None:
        mon = ProgressMonitor(total_files=10)
        mon.update()
        m1 = mon.get_metrics()
        mon.update()
        m2 = mon.get_metrics()
        # Copies should differ
        assert m1.files_processed == 1
        assert m2.files_processed == 2

    def test_stop_without_start(self) -> None:
        """Stopping without starting should not raise."""
        mon = ProgressMonitor(total_files=10)
        mon.stop()  # Should be safe

    def test_start_idempotent(self) -> None:
        """Calling start twice should not create duplicate threads."""
        mon = ProgressMonitor(total_files=10)
        mon.start()
        thread1 = mon._update_thread
        mon.start()
        thread2 = mon._update_thread
        # Should be the same thread since it's still alive
        assert thread1 is thread2
        mon.stop()

    def test_resource_metrics_without_psutil(self) -> None:
        with patch("nanopore_simulator.monitoring.HAS_PSUTIL", False):
            mon = ProgressMonitor(total_files=10, enable_resources=True)
            mon.update()
            metrics = mon.get_metrics()
            # Should still work, just no resource data
            assert metrics.files_processed == 1


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    """Concurrent access to the monitor."""

    def test_concurrent_updates(self) -> None:
        mon = ProgressMonitor(total_files=200)
        barrier = threading.Barrier(4)

        def worker() -> None:
            barrier.wait()
            for _ in range(50):
                mon.update(bytes_delta=100)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        metrics = mon.get_metrics()
        assert metrics.files_processed == 200
        assert metrics.bytes_processed == 200 * 100


# ---------------------------------------------------------------------------
# NullMonitor
# ---------------------------------------------------------------------------


class TestNullMonitor:
    """Null monitor implements the same interface but does nothing."""

    def test_is_instance_compatible(self) -> None:
        mon = NullMonitor()
        # Should have the same public methods as ProgressMonitor
        assert hasattr(mon, "start")
        assert hasattr(mon, "stop")
        assert hasattr(mon, "update")
        assert hasattr(mon, "get_metrics")
        assert hasattr(mon, "pause")
        assert hasattr(mon, "resume")
        assert hasattr(mon, "is_paused")

    def test_start_stop_no_ops(self) -> None:
        mon = NullMonitor()
        mon.start()
        mon.stop()
        # No exception raised

    def test_update_no_op(self) -> None:
        mon = NullMonitor()
        mon.update()
        mon.update(bytes_delta=1024)
        metrics = mon.get_metrics()
        assert metrics.files_processed == 0

    def test_get_metrics_returns_empty(self) -> None:
        mon = NullMonitor()
        metrics = mon.get_metrics()
        assert isinstance(metrics, SimulationMetrics)
        assert metrics.files_total == 0

    def test_pause_resume_no_ops(self) -> None:
        mon = NullMonitor()
        mon.pause()
        assert not mon.is_paused()
        mon.resume()
        assert not mon.is_paused()

    def test_estimate_eta_always_none(self) -> None:
        mon = NullMonitor()
        metrics = mon.get_metrics()
        assert metrics.eta_seconds is None


# ---------------------------------------------------------------------------
# create_monitor factory
# ---------------------------------------------------------------------------


class TestCreateMonitor:
    """Factory function for creating monitors."""

    def test_create_basic(self) -> None:
        mon = create_monitor("basic", total_files=100)
        assert isinstance(mon, ProgressMonitor)
        assert not isinstance(mon, NullMonitor)

    def test_create_enhanced(self) -> None:
        mon = create_monitor("enhanced", total_files=100)
        assert isinstance(mon, ProgressMonitor)

    def test_create_none(self) -> None:
        mon = create_monitor("none", total_files=100)
        assert isinstance(mon, NullMonitor)

    def test_total_files_propagated(self) -> None:
        mon = create_monitor("basic", total_files=42)
        metrics = mon.get_metrics()
        assert metrics.files_total == 42


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


class TestFormatBytes:
    """Human-readable byte formatting."""

    def test_bytes(self) -> None:
        assert format_bytes(500) == "500.0 B"

    def test_kilobytes(self) -> None:
        assert format_bytes(1024) == "1.0 KB"

    def test_megabytes(self) -> None:
        assert format_bytes(1024 * 1024) == "1.0 MB"

    def test_gigabytes(self) -> None:
        assert format_bytes(1024 ** 3) == "1.0 GB"

    def test_zero(self) -> None:
        assert format_bytes(0) == "0.0 B"


class TestFormatTime:
    """Human-readable time formatting."""

    def test_seconds(self) -> None:
        assert format_time(30.0) == "30.0s"

    def test_minutes(self) -> None:
        assert format_time(90.0) == "1.5m"

    def test_hours(self) -> None:
        assert format_time(7200.0) == "2.0h"

    def test_zero(self) -> None:
        assert format_time(0.0) == "0.0s"


# ---------------------------------------------------------------------------
# Resource monitoring (psutil optional)
# ---------------------------------------------------------------------------


class TestResourceMonitoring:
    """Resource tracking with optional psutil."""

    def test_monitor_with_psutil_available(self) -> None:
        """When psutil is available, resource metrics are populated."""
        try:
            import psutil  # noqa: F401
            has_psutil = True
        except ImportError:
            has_psutil = False

        mon = ProgressMonitor(
            total_files=10, enable_resources=True, update_interval=0.05
        )
        mon.start()
        # Wait long enough for at least one background update cycle.
        time.sleep(0.3)
        mon.update()
        mon.stop()

        metrics = mon.get_metrics()
        if has_psutil:
            assert metrics.resource_cpu_percent is not None
            assert metrics.resource_memory_mb is not None

    def test_monitor_without_resource_tracking(self) -> None:
        mon = ProgressMonitor(total_files=10, enable_resources=False)
        mon.update()
        metrics = mon.get_metrics()
        assert metrics.resource_cpu_percent is None
        assert metrics.resource_memory_mb is None
