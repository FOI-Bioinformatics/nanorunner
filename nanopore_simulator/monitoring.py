"""Progress monitoring and performance metrics for simulations.

Provides thread-safe progress tracking, optional resource monitoring
(CPU/memory via psutil), pause/resume, and a NullMonitor that
implements the same interface as a no-op.

Usage::

    monitor = create_monitor("basic", total_files=100)
    monitor.start()
    for path in files:
        process(path)
        monitor.update(bytes_delta=path.stat().st_size)
    monitor.stop()
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# Optional dependency for enhanced resource monitoring.
try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    psutil = None  # type: ignore[assignment]
    HAS_PSUTIL = False

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------
# Formatting helpers
# -------------------------------------------------------------------


def format_bytes(byte_count: int) -> str:
    """Format a byte count in human-readable form (B, KB, MB, GB, TB)."""
    value = float(byte_count)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} PB"


def format_time(seconds: float) -> str:
    """Format a duration in human-readable form (s, m, h)."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f}m"
    else:
        return f"{seconds / 3600:.1f}h"


# -------------------------------------------------------------------
# Metrics dataclass
# -------------------------------------------------------------------


@dataclass
class SimulationMetrics:
    """Snapshot of simulation progress.

    Trimmed to the fields that the runner and display logic actually
    read.  Resource fields are optional and only populated when psutil
    is available and resource tracking is enabled.

    Attributes:
        files_processed: Number of files completed so far.
        files_total: Total files expected in the simulation.
        bytes_processed: Total bytes processed so far.
        start_time: Epoch time when the simulation started.
        eta_seconds: Estimated seconds remaining, or None if unknown.
        resource_cpu_percent: Current aggregate CPU percent, or None.
        resource_memory_mb: Current aggregate RSS in MiB, or None.
    """

    files_processed: int = 0
    files_total: int = 0
    bytes_processed: int = 0
    start_time: float = field(default_factory=time.time)
    eta_seconds: Optional[float] = None
    resource_cpu_percent: Optional[float] = None
    resource_memory_mb: Optional[float] = None

    @property
    def progress_percentage(self) -> float:
        """Progress as a percentage (0--100)."""
        if self.files_total == 0:
            return 0.0
        return (self.files_processed / self.files_total) * 100.0

    @property
    def elapsed(self) -> float:
        """Seconds since the simulation started."""
        return time.time() - self.start_time

    @property
    def throughput(self) -> float:
        """Files processed per second."""
        el = self.elapsed
        if el <= 0 or self.files_processed == 0:
            return 0.0
        return self.files_processed / el


# -------------------------------------------------------------------
# Resource monitor (optional psutil)
# -------------------------------------------------------------------


class _ResourceCollector:
    """Collects CPU and memory metrics from the current process tree."""

    def __init__(self) -> None:
        self._process = psutil.Process() if HAS_PSUTIL else None

    def collect(self) -> tuple:
        """Return (cpu_percent, memory_mb) or (None, None)."""
        if not HAS_PSUTIL or self._process is None:
            return (None, None)
        try:
            try:
                children = self._process.children(recursive=True)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                children = []
            procs = [self._process] + children

            cpu = 0.0
            rss = 0
            for p in procs:
                try:
                    cpu += p.cpu_percent()
                    rss += p.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            memory_mb = rss / (1024 * 1024)
            return (cpu, memory_mb)
        except Exception:
            logger.debug("Resource collection failed", exc_info=True)
            return (None, None)


# -------------------------------------------------------------------
# ProgressMonitor
# -------------------------------------------------------------------


class ProgressMonitor:
    """Thread-safe progress monitor with optional resource tracking.

    The monitor runs a background thread that periodically updates
    resource metrics and calls an optional display callback. The
    ``update()`` method is meant to be called from worker threads
    after each file is processed.
    """

    def __init__(
        self,
        total_files: int,
        *,
        update_interval: float = 1.0,
        display_callback: Optional[Callable[["SimulationMetrics"], None]] = None,
        enable_resources: bool = True,
    ) -> None:
        self._metrics = SimulationMetrics(files_total=total_files)
        self._update_interval = update_interval
        self._display_callback = display_callback

        # Resource collector
        self._resource_collector = (
            _ResourceCollector() if enable_resources else None
        )

        # Pause / resume
        self._paused = threading.Event()
        self._paused.set()  # Start unpaused

        # Background update thread
        self._stop_event = threading.Event()
        self._update_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    # -- Lifecycle --------------------------------------------------

    def start(self) -> None:
        """Start the background monitoring thread."""
        if self._update_thread is not None and self._update_thread.is_alive():
            return
        self._stop_event.clear()
        self._update_thread = threading.Thread(
            target=self._update_loop, daemon=True
        )
        self._update_thread.start()
        logger.info("Progress monitoring started")

    def stop(self) -> None:
        """Stop the background monitoring thread."""
        if self._update_thread is not None and self._update_thread.is_alive():
            self._stop_event.set()
            self._update_thread.join(timeout=2.0)
            logger.info("Progress monitoring stopped")

    # -- Updates (called from workers) ------------------------------

    def update(self, *, bytes_delta: int = 0) -> None:
        """Record that one file has been processed.

        Args:
            bytes_delta: Number of bytes in the processed file.
        """
        with self._lock:
            self._metrics.files_processed += 1
            self._metrics.bytes_processed += bytes_delta

    # -- Queries ----------------------------------------------------

    def get_metrics(self) -> SimulationMetrics:
        """Return a snapshot of the current metrics (thread-safe copy)."""
        with self._lock:
            m = SimulationMetrics(
                files_processed=self._metrics.files_processed,
                files_total=self._metrics.files_total,
                bytes_processed=self._metrics.bytes_processed,
                start_time=self._metrics.start_time,
                eta_seconds=self._estimate_eta(),
                resource_cpu_percent=self._metrics.resource_cpu_percent,
                resource_memory_mb=self._metrics.resource_memory_mb,
            )
        return m

    # -- Pause / resume ---------------------------------------------

    def pause(self) -> None:
        """Pause the simulation (workers should call wait_if_paused)."""
        self._paused.clear()
        logger.info("Simulation paused")

    def resume(self) -> None:
        """Resume the simulation."""
        self._paused.set()
        logger.info("Simulation resumed")

    def is_paused(self) -> bool:
        """Return True if the simulation is currently paused."""
        return not self._paused.is_set()

    def wait_if_paused(self, timeout: Optional[float] = None) -> None:
        """Block until the simulation is resumed."""
        self._paused.wait(timeout)

    # -- ETA --------------------------------------------------------

    def _estimate_eta(self) -> Optional[float]:
        """Simple throughput-extrapolation ETA.

        Returns None when no files have been processed, 0.0 when
        the simulation is complete.
        """
        processed = self._metrics.files_processed
        total = self._metrics.files_total

        if processed == 0:
            return None

        remaining = total - processed
        if remaining <= 0:
            return 0.0

        elapsed = time.time() - self._metrics.start_time
        if elapsed <= 0:
            return None

        rate = processed / elapsed
        return remaining / rate

    # -- Background loop --------------------------------------------

    def _update_loop(self) -> None:
        """Periodic background update: resources and display callback."""
        while not self._stop_event.wait(self._update_interval):
            self._paused.wait()
            if self._stop_event.is_set():
                break

            # Collect resources
            if self._resource_collector is not None:
                cpu, mem = self._resource_collector.collect()
                with self._lock:
                    self._metrics.resource_cpu_percent = cpu
                    self._metrics.resource_memory_mb = mem

            # Display callback
            if self._display_callback is not None:
                try:
                    self._display_callback(self.get_metrics())
                except Exception as exc:
                    logger.error("Error in display callback: %s", exc)


# -------------------------------------------------------------------
# NullMonitor
# -------------------------------------------------------------------


class NullMonitor:
    """No-op monitor that implements the same interface as ProgressMonitor.

    Used when ``monitor_type="none"`` to avoid conditional checks
    throughout the runner code.
    """

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def update(self, *, bytes_delta: int = 0) -> None:
        pass

    def get_metrics(self) -> SimulationMetrics:
        return SimulationMetrics()

    def pause(self) -> None:
        pass

    def resume(self) -> None:
        pass

    def is_paused(self) -> bool:
        return False

    def wait_if_paused(self, timeout: Optional[float] = None) -> None:
        pass


# -------------------------------------------------------------------
# Factory
# -------------------------------------------------------------------


def create_monitor(
    monitor_type: str, *, total_files: int, **kwargs: Any
) -> "ProgressMonitor":
    """Create a progress monitor by type name.

    Args:
        monitor_type: "basic", "enhanced", or "none".
        total_files: Total expected file count.
        **kwargs: Additional keyword arguments forwarded to ProgressMonitor.

    Returns:
        A ProgressMonitor or NullMonitor instance.
    """
    mt = monitor_type.lower()
    if mt == "none":
        return NullMonitor()  # type: ignore[return-value]
    if mt == "enhanced":
        kwargs.setdefault("enable_resources", True)
        kwargs.setdefault("update_interval", 0.5)
    else:
        kwargs.setdefault("enable_resources", False)
    return ProgressMonitor(total_files, **kwargs)
