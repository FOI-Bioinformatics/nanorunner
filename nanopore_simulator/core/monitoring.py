"""Real-time progress monitoring and performance metrics"""

import time
import threading
import signal
import os
import sys
import json
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Callable
from pathlib import Path
import logging
from collections import deque

# Optional dependency for enhanced monitoring
try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    psutil = None  # type: ignore
    HAS_PSUTIL = False


@dataclass
class ResourceMetrics:
    """System resource usage metrics"""

    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_used_mb: float = 0.0
    disk_io_read_mb: float = 0.0
    disk_io_write_mb: float = 0.0
    disk_usage_percent: float = 0.0
    open_files: int = 0
    network_io_mb: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "memory_used_mb": self.memory_used_mb,
            "disk_io_read_mb": self.disk_io_read_mb,
            "disk_io_write_mb": self.disk_io_write_mb,
            "disk_usage_percent": self.disk_usage_percent,
            "open_files": self.open_files,
            "network_io_mb": self.network_io_mb,
        }


@dataclass
class SimulationMetrics:
    """Metrics collected during simulation"""

    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    files_processed: int = 0
    files_total: int = 0
    batches_processed: int = 0
    batches_total: int = 0
    total_bytes_processed: int = 0
    total_wait_time: float = 0.0
    total_processing_time: float = 0.0
    errors_encountered: int = 0
    last_update_time: float = field(default_factory=time.time)

    # Performance metrics
    throughput_files_per_sec: float = 0.0
    throughput_bytes_per_sec: float = 0.0
    average_file_size: float = 0.0
    average_batch_time: float = 0.0
    eta_seconds: Optional[float] = None

    # Enhanced ETA with trend analysis
    eta_trend: str = "stable"  # "improving", "degrading", "stable"
    confidence_score: float = 0.0  # 0.0 to 1.0

    # Resource metrics
    resource_metrics: Optional[ResourceMetrics] = None
    peak_memory_mb: float = 0.0
    peak_cpu_percent: float = 0.0
    total_disk_io_mb: float = 0.0

    # Timing breakdown
    timing_breakdown: Dict[str, float] = field(default_factory=dict)

    # Performance history for trend analysis
    throughput_history: deque = field(default_factory=lambda: deque(maxlen=30))
    resource_history: deque = field(default_factory=lambda: deque(maxlen=60))

    def __post_init__(self) -> None:
        if not self.timing_breakdown:
            self.timing_breakdown = {
                "file_operations": 0.0,
                "directory_creation": 0.0,
                "validation": 0.0,
                "waiting": 0.0,
            }

    @property
    def elapsed_time(self) -> float:
        """Get elapsed time since start"""
        end_time = self.end_time if self.end_time else time.time()
        return end_time - self.start_time

    @property
    def progress_percentage(self) -> float:
        """Get progress as percentage"""
        if self.files_total == 0:
            return 0.0
        return (self.files_processed / self.files_total) * 100.0

    @property
    def is_complete(self) -> bool:
        """Check if simulation is complete"""
        if self.files_total == 0:
            return True  # 0/0 is considered complete
        return self.files_processed >= self.files_total

    def update_throughput(self) -> None:
        """Update throughput metrics"""
        elapsed = self.elapsed_time
        if elapsed > 0:
            self.throughput_files_per_sec = self.files_processed / elapsed
            self.throughput_bytes_per_sec = self.total_bytes_processed / elapsed

        if self.files_processed > 0:
            self.average_file_size = self.total_bytes_processed / self.files_processed

        if self.batches_processed > 0:
            self.average_batch_time = (
                self.total_processing_time / self.batches_processed
            )

    def estimate_eta(self) -> None:
        """Enhanced ETA estimation with trend analysis"""
        if self.files_processed == 0 or self.throughput_files_per_sec == 0:
            self.eta_seconds = None
            self.confidence_score = 0.0
            return

        remaining_files = self.files_total - self.files_processed
        if remaining_files <= 0:
            self.eta_seconds = 0.0
            self.confidence_score = 1.0
            return

        # Simple estimate as baseline
        simple_eta = remaining_files / self.throughput_files_per_sec

        # Enhanced prediction using throughput history
        if len(self.throughput_history) >= 3:
            recent_throughputs = list(self.throughput_history)[
                -10:
            ]  # Last 10 measurements
            avg_recent = sum(recent_throughputs) / len(recent_throughputs)

            # Trend analysis
            if len(recent_throughputs) >= 5:
                first_half = recent_throughputs[: len(recent_throughputs) // 2]
                second_half = recent_throughputs[len(recent_throughputs) // 2 :]

                first_avg = sum(first_half) / len(first_half)
                second_avg = sum(second_half) / len(second_half)

                trend_ratio = second_avg / first_avg if first_avg > 0 else 1.0

                if trend_ratio > 1.05:  # 5% improvement
                    self.eta_trend = "improving"
                    # Use optimistic prediction
                    predicted_throughput = avg_recent * min(
                        trend_ratio, 1.2
                    )  # Cap at 20% improvement
                elif trend_ratio < 0.95:  # 5% degradation
                    self.eta_trend = "degrading"
                    # Use conservative prediction
                    predicted_throughput = avg_recent * max(
                        trend_ratio, 0.8
                    )  # Cap at 20% degradation
                else:
                    self.eta_trend = "stable"
                    predicted_throughput = avg_recent

                self.eta_seconds = (
                    remaining_files / predicted_throughput
                    if predicted_throughput > 0
                    else simple_eta
                )

                # Confidence based on consistency of recent measurements
                variance = sum((x - avg_recent) ** 2 for x in recent_throughputs) / len(
                    recent_throughputs
                )
                coefficient_of_variation = (
                    (variance**0.5) / avg_recent if avg_recent > 0 else 1.0
                )
                self.confidence_score = max(
                    0.0, min(1.0, 1.0 - coefficient_of_variation)
                )
            else:
                self.eta_seconds = simple_eta
                self.confidence_score = 0.5
        else:
            self.eta_seconds = simple_eta
            self.confidence_score = 0.3

        # Factor in wait time for remaining batches
        remaining_batches = max(0, self.batches_total - self.batches_processed)
        if self.batches_processed > 0:
            estimated_wait_time = remaining_batches * (
                self.total_wait_time / self.batches_processed
            )
            self.eta_seconds += estimated_wait_time

    def add_throughput_sample(self, throughput: float) -> None:
        """Add throughput sample to history"""
        self.throughput_history.append(throughput)

    def add_resource_sample(self, resource_metrics: ResourceMetrics) -> None:
        """Add resource metrics sample to history"""
        self.resource_history.append(resource_metrics)

        # Update peak values
        if resource_metrics.memory_used_mb > self.peak_memory_mb:
            self.peak_memory_mb = resource_metrics.memory_used_mb
        if resource_metrics.cpu_percent > self.peak_cpu_percent:
            self.peak_cpu_percent = resource_metrics.cpu_percent

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary"""
        result = {
            "elapsed_time": self.elapsed_time,
            "files_processed": self.files_processed,
            "files_total": self.files_total,
            "progress_percentage": self.progress_percentage,
            "throughput_files_per_sec": self.throughput_files_per_sec,
            "throughput_bytes_per_sec": self.throughput_bytes_per_sec,
            "average_file_size": self.average_file_size,
            "eta_seconds": self.eta_seconds,
            "eta_trend": self.eta_trend,
            "confidence_score": self.confidence_score,
            "total_bytes_processed": self.total_bytes_processed,
            "errors_encountered": self.errors_encountered,
            "timing_breakdown": self.timing_breakdown.copy(),
            "peak_memory_mb": self.peak_memory_mb,
            "peak_cpu_percent": self.peak_cpu_percent,
            "total_disk_io_mb": self.total_disk_io_mb,
        }

        if self.resource_metrics:
            result["resource_metrics"] = self.resource_metrics.to_dict()

        return result


class ProgressDisplay:
    """Handles progress display formatting"""

    @staticmethod
    def format_bytes(bytes_count: int) -> str:
        """Format bytes in human readable format"""
        count_float = float(bytes_count)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if count_float < 1024.0:
                return f"{count_float:.1f} {unit}"
            count_float /= 1024.0
        return f"{count_float:.1f} PB"

    @staticmethod
    def format_time(seconds: float) -> str:
        """Format time in human readable format"""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f}m"
        else:
            hours = seconds / 3600
            return f"{hours:.1f}h"

    @staticmethod
    def format_rate(rate: float, unit: str) -> str:
        """Format rate with appropriate units"""
        if unit == "files":
            return f"{rate:.1f} files/sec"
        elif unit == "bytes":
            return f"{ProgressDisplay.format_bytes(int(rate))}/sec"
        return f"{rate:.1f} {unit}/sec"

    @staticmethod
    def create_progress_bar(percentage: float, width: int = 50) -> str:
        """Create ASCII progress bar"""
        filled = int(width * percentage / 100)
        bar = "█" * filled + "░" * (width - filled)
        return f"[{bar}] {percentage:.1f}%"

    @staticmethod
    def format_progress_line(
        metrics: SimulationMetrics,
        include_bar: bool = True,
        show_resources: bool = False,
    ) -> str:
        """Format a complete progress line"""
        parts = []

        if include_bar:
            bar = ProgressDisplay.create_progress_bar(metrics.progress_percentage, 30)
            parts.append(bar)

        # Files progress
        parts.append(f"{metrics.files_processed}/{metrics.files_total} files")

        # Throughput
        if metrics.throughput_files_per_sec > 0:
            parts.append(f"{metrics.throughput_files_per_sec:.1f} files/sec")

        # Enhanced ETA with trend
        if metrics.eta_seconds is not None:
            eta_str = ProgressDisplay.format_time(metrics.eta_seconds)
            trend_indicator = {"improving": "↗", "degrading": "↘", "stable": "→"}.get(
                metrics.eta_trend, ""
            )
            confidence_stars = "★" * int(metrics.confidence_score * 3)  # 0-3 stars
            parts.append(f"ETA: {eta_str} {trend_indicator}{confidence_stars}")

        # Resource usage (if available and requested)
        if show_resources and metrics.resource_metrics and HAS_PSUTIL:
            cpu = metrics.resource_metrics.cpu_percent
            mem = metrics.resource_metrics.memory_percent
            parts.append(f"CPU: {cpu:.0f}% | RAM: {mem:.0f}%")

        # Elapsed time
        elapsed_str = ProgressDisplay.format_time(metrics.elapsed_time)
        parts.append(f"Elapsed: {elapsed_str}")

        return " | ".join(parts)


class ResourceMonitor:
    """System resource monitoring"""

    def __init__(self) -> None:
        self.process = psutil.Process() if HAS_PSUTIL else None
        self._baseline_io = None

        if HAS_PSUTIL and self.process:
            try:
                self._baseline_io = self.process.io_counters()  # type: ignore
            except (psutil.AccessDenied, AttributeError):
                self._baseline_io = None

    def get_current_metrics(self) -> ResourceMetrics:
        """Get current system resource metrics"""
        if not HAS_PSUTIL or not self.process:
            return ResourceMetrics()

        try:
            # CPU and memory
            cpu_percent = self.process.cpu_percent()
            memory_info = self.process.memory_info()
            memory_percent = self.process.memory_percent()

            # Disk I/O
            io_read_mb = 0.0
            io_write_mb = 0.0
            if self._baseline_io:
                try:
                    current_io = self.process.io_counters()  # type: ignore
                    io_read_mb = (
                        current_io.read_bytes - self._baseline_io.read_bytes
                    ) / (1024 * 1024)
                    io_write_mb = (
                        current_io.write_bytes - self._baseline_io.write_bytes
                    ) / (1024 * 1024)
                except (psutil.AccessDenied, AttributeError):
                    pass

            # Open files
            try:
                open_files = len(self.process.open_files())
            except (psutil.AccessDenied, AttributeError):
                open_files = 0

            # Disk usage of current working directory
            try:
                disk_usage = psutil.disk_usage(os.getcwd())
                disk_usage_percent = (disk_usage.used / disk_usage.total) * 100
            except (OSError, psutil.AccessDenied):
                disk_usage_percent = 0.0

            return ResourceMetrics(
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                memory_used_mb=memory_info.rss / (1024 * 1024),
                disk_io_read_mb=io_read_mb,
                disk_io_write_mb=io_write_mb,
                disk_usage_percent=disk_usage_percent,
                open_files=open_files,
            )
        except Exception as e:
            logging.getLogger(__name__).warning(
                f"Error collecting resource metrics: {e}"
            )
            return ResourceMetrics()


class SignalHandler:
    """Handles graceful shutdown on signals"""

    def __init__(self, progress_monitor: "ProgressMonitor") -> None:
        self.progress_monitor = progress_monitor
        self.shutdown_requested = False
        self.logger = logging.getLogger(__name__)

        # Register signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        if hasattr(signal, "SIGBREAK"):  # Windows
            signal.signal(signal.SIGBREAK, self._signal_handler)

    def _signal_handler(self, signum: int, frame: Any) -> None:
        """Handle shutdown signals"""
        signal_names = {signal.SIGINT: "SIGINT", signal.SIGTERM: "SIGTERM"}
        if hasattr(signal, "SIGBREAK"):
            signal_names[signal.SIGBREAK] = "SIGBREAK"

        signal_name = signal_names.get(signum, f"Signal {signum}")  # type: ignore

        if not self.shutdown_requested:
            self.shutdown_requested = True
            print(f"\n\n{signal_name} received. Initiating graceful shutdown...")
            self.logger.info(f"Graceful shutdown initiated by {signal_name}")

            # Print current progress summary
            if self.progress_monitor:
                metrics = self.progress_monitor.get_metrics()
                self._print_shutdown_summary(metrics)
        else:
            print("\nForced shutdown requested. Exiting immediately.")
            sys.exit(1)

    def _print_shutdown_summary(self, metrics: SimulationMetrics) -> None:
        """Print summary during shutdown"""
        print("\n=== Shutdown Summary ===")
        print(
            f"Files processed: {metrics.files_processed}/{metrics.files_total} ({metrics.progress_percentage:.1f}%)"
        )
        print(f"Runtime: {ProgressDisplay.format_time(metrics.elapsed_time)}")
        print(f"Average throughput: {metrics.throughput_files_per_sec:.1f} files/sec")

        if metrics.total_bytes_processed > 0:
            print(
                f"Data processed: {ProgressDisplay.format_bytes(metrics.total_bytes_processed)}"
            )

        if metrics.errors_encountered > 0:
            print(f"Errors encountered: {metrics.errors_encountered}")

        if HAS_PSUTIL and metrics.resource_metrics:
            print(f"Peak memory usage: {metrics.peak_memory_mb:.1f} MB")
            print(f"Peak CPU usage: {metrics.peak_cpu_percent:.1f}%")

        print("\nProgress has been saved. Simulation can be resumed.")


class ProgressMonitor:
    """Enhanced real-time progress monitoring system"""

    def __init__(
        self,
        total_files: int,
        update_interval: float = 1.0,
        display_callback: Optional[Callable[[SimulationMetrics], None]] = None,
        enable_resources: bool = True,
        enable_checkpoint: bool = True,
    ):
        self.metrics = SimulationMetrics(files_total=total_files)
        self.update_interval = update_interval
        self.display_callback = display_callback or self._default_display
        self.logger = logging.getLogger(__name__)

        # Enhanced monitoring components
        self.resource_monitor = ResourceMonitor() if enable_resources else None
        self.signal_handler = SignalHandler(self) if enable_checkpoint else None
        self.checkpoint_file = (
            Path("simulation_checkpoint.json") if enable_checkpoint else None
        )

        # Interactive controls
        self._paused = threading.Event()
        self._paused.set()  # Start unpaused

        # Threading for updates
        self._stop_event = threading.Event()
        self._update_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # File tracking
        self._file_sizes: Dict[Path, int] = {}
        self._batch_start_times: List[float] = []

        # Performance warnings
        self._last_warning_time = 0.0
        self._warning_cooldown = 30.0  # 30 seconds between warnings

    def start(self) -> None:
        """Start the progress monitoring"""
        if self._update_thread is None or not self._update_thread.is_alive():
            self._stop_event.clear()
            self._update_thread = threading.Thread(
                target=self._update_loop, daemon=True
            )
            self._update_thread.start()
            self.logger.info("Enhanced progress monitoring started")

            # Load checkpoint if it exists
            self._load_checkpoint()

    def stop(self) -> None:
        """Stop the progress monitoring"""
        if self._update_thread and self._update_thread.is_alive():
            self._stop_event.set()
            self._update_thread.join(timeout=2.0)
            self.logger.info("Enhanced progress monitoring stopped")

        # Final update
        with self._lock:
            self.metrics.end_time = time.time()
            self.metrics.update_throughput()
            self.metrics.estimate_eta()

        # Save final checkpoint and cleanup
        self._save_checkpoint()
        self._cleanup_checkpoint()

        self.display_callback(self.metrics)

    def set_batch_count(self, total_batches: int) -> None:
        """Set the total number of batches"""
        with self._lock:
            self.metrics.batches_total = total_batches

    def start_batch(self) -> float:
        """Mark the start of a new batch"""
        start_time = time.time()
        self._batch_start_times.append(start_time)
        return start_time

    def end_batch(self, start_time: float) -> None:
        """Mark the end of a batch"""
        end_time = time.time()
        batch_duration = end_time - start_time

        with self._lock:
            self.metrics.batches_processed += 1
            self.metrics.total_processing_time += batch_duration

    def add_wait_time(self, wait_duration: float) -> None:
        """Add wait time to metrics"""
        with self._lock:
            self.metrics.total_wait_time += wait_duration
            self.metrics.timing_breakdown["waiting"] += wait_duration

    def record_file_processed(
        self, file_path: Path, operation_time: float = 0.0
    ) -> None:
        """Record that a file was processed"""
        try:
            file_size = file_path.stat().st_size if file_path.exists() else 0
        except (OSError, PermissionError):
            file_size = 0

        with self._lock:
            self.metrics.files_processed += 1
            self.metrics.total_bytes_processed += file_size
            self.metrics.timing_breakdown["file_operations"] += operation_time
            self._file_sizes[file_path] = file_size

            # Periodic checkpoint saves
            if self.metrics.files_processed % 10 == 0:
                self._save_checkpoint()

    def record_error(self, error_type: str = "general") -> None:
        """Record an error"""
        with self._lock:
            self.metrics.errors_encountered += 1

        self.logger.warning(f"Error recorded: {error_type}")

    def record_timing(self, category: str, duration: float) -> None:
        """Record timing for a specific category"""
        with self._lock:
            if category not in self.metrics.timing_breakdown:
                self.metrics.timing_breakdown[category] = 0.0
            self.metrics.timing_breakdown[category] += duration

    def pause(self) -> None:
        """Pause the simulation"""
        self._paused.clear()
        self.logger.info("Simulation paused")
        print("\n⏸️  Simulation paused. Press 'r' to resume or 'q' to quit.")

    def resume(self) -> None:
        """Resume the simulation"""
        self._paused.set()
        self.logger.info("Simulation resumed")
        print("▶️  Simulation resumed.")

    def is_paused(self) -> bool:
        """Check if simulation is paused"""
        return not self._paused.is_set()

    def wait_if_paused(self, timeout: Optional[float] = None) -> None:
        """Wait if simulation is paused"""
        self._paused.wait(timeout)

    def should_stop(self) -> bool:
        """Check if shutdown was requested"""
        return bool(self.signal_handler and self.signal_handler.shutdown_requested)

    def get_metrics(self) -> SimulationMetrics:
        """Get current metrics (thread-safe copy)"""
        with self._lock:
            # Create a copy of current metrics
            current_metrics = SimulationMetrics(
                start_time=self.metrics.start_time,
                end_time=self.metrics.end_time,
                files_processed=self.metrics.files_processed,
                files_total=self.metrics.files_total,
                batches_processed=self.metrics.batches_processed,
                batches_total=self.metrics.batches_total,
                total_bytes_processed=self.metrics.total_bytes_processed,
                total_wait_time=self.metrics.total_wait_time,
                total_processing_time=self.metrics.total_processing_time,
                errors_encountered=self.metrics.errors_encountered,
                timing_breakdown=self.metrics.timing_breakdown.copy(),
                eta_trend=self.metrics.eta_trend,
                confidence_score=self.metrics.confidence_score,
                resource_metrics=self.metrics.resource_metrics,
                peak_memory_mb=self.metrics.peak_memory_mb,
                peak_cpu_percent=self.metrics.peak_cpu_percent,
                total_disk_io_mb=self.metrics.total_disk_io_mb,
            )

            # Copy history
            current_metrics.throughput_history = self.metrics.throughput_history.copy()
            current_metrics.resource_history = self.metrics.resource_history.copy()

            # Update derived metrics
            current_metrics.update_throughput()
            current_metrics.estimate_eta()

            return current_metrics

    def _update_loop(self) -> None:
        """Enhanced update loop with resource monitoring and performance analysis"""
        while not self._stop_event.wait(self.update_interval):
            # Wait if paused
            self._paused.wait()

            if self._stop_event.is_set():
                break

            with self._lock:
                # Update resource metrics
                if self.resource_monitor:
                    resource_metrics = self.resource_monitor.get_current_metrics()
                    self.metrics.resource_metrics = resource_metrics
                    self.metrics.add_resource_sample(resource_metrics)

                    # Update cumulative totals
                    self.metrics.total_disk_io_mb = (
                        resource_metrics.disk_io_read_mb
                        + resource_metrics.disk_io_write_mb
                    )

                # Update performance metrics
                self.metrics.update_throughput()
                self.metrics.add_throughput_sample(
                    self.metrics.throughput_files_per_sec
                )
                self.metrics.estimate_eta()
                self.metrics.last_update_time = time.time()

                # Check for performance issues
                self._check_performance_warnings()

            # Call display callback
            try:
                self.display_callback(self.get_metrics())
            except Exception as e:
                self.logger.error(f"Error in display callback: {e}")

    def _check_performance_warnings(self) -> None:
        """Check for performance issues and emit warnings"""
        current_time = time.time()
        if current_time - self._last_warning_time < self._warning_cooldown:
            return

        if not self.metrics.resource_metrics:
            return

        warnings = []

        # High memory usage
        if self.metrics.resource_metrics.memory_percent > 85:
            warnings.append(
                f"High memory usage: {self.metrics.resource_metrics.memory_percent:.1f}%"
            )

        # High CPU usage sustained
        if len(self.metrics.resource_history) >= 5:
            recent_cpu = [
                r.cpu_percent for r in list(self.metrics.resource_history)[-5:]
            ]
            avg_cpu = sum(recent_cpu) / len(recent_cpu)
            if avg_cpu > 90:
                warnings.append(f"Sustained high CPU usage: {avg_cpu:.1f}%")

        # Low throughput
        if (
            len(self.metrics.throughput_history) >= 10
            and self.metrics.throughput_files_per_sec < 0.1
            and self.metrics.files_processed > 10
        ):
            warnings.append(
                f"Low throughput: {self.metrics.throughput_files_per_sec:.2f} files/sec"
            )

        # High disk usage
        if self.metrics.resource_metrics.disk_usage_percent > 90:
            warnings.append(
                f"Low disk space: {self.metrics.resource_metrics.disk_usage_percent:.1f}% used"
            )

        # Emit warnings
        if warnings:
            self._last_warning_time = current_time
            for warning in warnings:
                self.logger.warning(f"Performance warning: {warning}")

    def _save_checkpoint(self) -> None:
        """Save current progress to checkpoint file"""
        if not self.checkpoint_file:
            return

        try:
            checkpoint_data = {
                "metrics": self.metrics.to_dict(),
                "timestamp": time.time(),
                "version": "2.0.0",
            }

            with open(self.checkpoint_file, "w") as f:
                json.dump(checkpoint_data, f, indent=2)

        except Exception as e:
            self.logger.warning(f"Failed to save checkpoint: {e}")

    def _load_checkpoint(self) -> None:
        """Load progress from checkpoint file"""
        if not self.checkpoint_file or not self.checkpoint_file.exists():
            return

        try:
            with open(self.checkpoint_file, "r") as f:
                checkpoint_data = json.load(f)

            # Restore basic metrics (be careful with threading)
            if "metrics" in checkpoint_data:
                saved_metrics = checkpoint_data["metrics"]
                self.metrics.files_processed = saved_metrics.get("files_processed", 0)
                self.metrics.total_bytes_processed = saved_metrics.get(
                    "total_bytes_processed", 0
                )

            self.logger.info(
                f"Resumed from checkpoint: {self.metrics.files_processed} files processed"
            )

        except Exception as e:
            self.logger.warning(f"Failed to load checkpoint: {e}")

    def _cleanup_checkpoint(self) -> None:
        """Remove checkpoint file when simulation completes"""
        if self.checkpoint_file and self.checkpoint_file.exists():
            try:
                self.checkpoint_file.unlink()
            except Exception as e:
                self.logger.warning(f"Failed to cleanup checkpoint: {e}")

    def _default_display(self, metrics: SimulationMetrics) -> None:
        """Enhanced default display callback"""
        if metrics.files_total > 0:
            # Show resources if available
            show_resources = HAS_PSUTIL and metrics.resource_metrics is not None
            progress_line = ProgressDisplay.format_progress_line(
                metrics, show_resources=show_resources
            )
            print(f"\r{progress_line}", end="", flush=True)

            # Print newline when complete
            if metrics.is_complete:
                print()  # New line at completion
                self._print_final_summary(metrics)

    def _print_final_summary(self, metrics: SimulationMetrics) -> None:
        """Print comprehensive final summary"""
        print("\n=== Simulation Complete ===")
        print(f"📁 Files processed: {metrics.files_processed}/{metrics.files_total}")
        print(f"⏱️  Total time: {ProgressDisplay.format_time(metrics.elapsed_time)}")
        print(
            f"💾 Data processed: {ProgressDisplay.format_bytes(metrics.total_bytes_processed)}"
        )
        print(
            f"🚀 Average throughput: {metrics.throughput_files_per_sec:.1f} files/sec"
        )

        if metrics.errors_encountered > 0:
            print(f"⚠️  Errors encountered: {metrics.errors_encountered}")

        if HAS_PSUTIL and metrics.peak_memory_mb > 0:
            print(f"🧠 Peak memory usage: {metrics.peak_memory_mb:.1f} MB")
            print(f"⚡ Peak CPU usage: {metrics.peak_cpu_percent:.1f}%")

        # Performance insights
        if len(metrics.throughput_history) >= 5:
            throughputs = list(metrics.throughput_history)
            min_tp = min(throughputs)
            max_tp = max(throughputs)
            if max_tp > min_tp * 1.5:
                print(
                    f"📊 Throughput varied from {min_tp:.1f} to {max_tp:.1f} files/sec"
                )


class DetailedProgressMonitor(ProgressMonitor):
    """Extended progress monitor with detailed logging and statistics"""

    def __init__(
        self,
        total_files: int,
        update_interval: float = 1.0,
        log_level: int = logging.INFO,
    ):
        super().__init__(total_files, update_interval, self._detailed_display)
        self.detailed_logger = logging.getLogger(f"{__name__}.detailed")
        self.detailed_logger.setLevel(log_level)

        # Additional tracking
        self.batch_details: List[Dict[str, Any]] = []
        self.file_details: List[Dict[str, Any]] = []

    def end_batch(self, start_time: float) -> None:
        """Enhanced batch tracking"""
        super().end_batch(start_time)

        end_time = time.time()
        batch_info = {
            "batch_number": self.metrics.batches_processed,
            "start_time": start_time,
            "end_time": end_time,
            "duration": end_time - start_time,
            "files_in_batch": len(
                [
                    f
                    for f in self.file_details
                    if f.get("batch_number") == self.metrics.batches_processed
                ]
            ),
        }
        self.batch_details.append(batch_info)

    def record_file_processed(
        self, file_path: Path, operation_time: float = 0.0
    ) -> None:
        """Enhanced file tracking"""
        super().record_file_processed(file_path, operation_time)

        file_info = {
            "file_path": str(file_path),
            "size_bytes": self._file_sizes.get(file_path, 0),
            "operation_time": operation_time,
            "batch_number": self.metrics.batches_processed,
            "timestamp": time.time(),
        }
        self.file_details.append(file_info)

    def _detailed_display(self, metrics: SimulationMetrics) -> None:
        """Detailed display with comprehensive information"""
        if metrics.files_total == 0:
            return

        # Basic progress
        progress_line = ProgressDisplay.format_progress_line(metrics)
        print(f"\r{progress_line}", end="", flush=True)

        # Detailed logging every 10 updates or at completion
        update_count = len(self.batch_details)
        if update_count % 10 == 0 or metrics.is_complete:
            self._log_detailed_stats(metrics)

        if metrics.is_complete:
            print()  # New line at completion
            self._log_final_summary(metrics)

    def _log_detailed_stats(self, metrics: SimulationMetrics) -> None:
        """Log detailed statistics"""
        self.detailed_logger.info(
            f"Progress: {metrics.progress_percentage:.1f}% | "
            f"Files: {metrics.files_processed}/{metrics.files_total} | "
            f"Throughput: {metrics.throughput_files_per_sec:.1f} files/sec | "
            f"Data: {ProgressDisplay.format_bytes(metrics.total_bytes_processed)} | "
            f"Errors: {metrics.errors_encountered}"
        )

    def _log_final_summary(self, metrics: SimulationMetrics) -> None:
        """Log comprehensive final summary"""
        self.detailed_logger.info("=== Simulation Complete ===")
        self.detailed_logger.info(
            f"Total time: {ProgressDisplay.format_time(metrics.elapsed_time)}"
        )
        self.detailed_logger.info(f"Files processed: {metrics.files_processed}")
        self.detailed_logger.info(
            f"Data processed: {ProgressDisplay.format_bytes(metrics.total_bytes_processed)}"
        )
        self.detailed_logger.info(
            f"Average throughput: {metrics.throughput_files_per_sec:.1f} files/sec"
        )
        self.detailed_logger.info(
            f"Average file size: {ProgressDisplay.format_bytes(int(metrics.average_file_size))}"
        )

        if metrics.errors_encountered > 0:
            self.detailed_logger.warning(
                f"Errors encountered: {metrics.errors_encountered}"
            )

        # Timing breakdown
        self.detailed_logger.info("Timing breakdown:")
        for category, duration in metrics.timing_breakdown.items():
            percentage = (
                (duration / metrics.elapsed_time) * 100
                if metrics.elapsed_time > 0
                else 0
            )
            self.detailed_logger.info(
                f"  {category}: {ProgressDisplay.format_time(duration)} ({percentage:.1f}%)"
            )


def create_progress_monitor(
    total_files: int, monitor_type: str = "default", **kwargs: Any
) -> ProgressMonitor:
    """Factory function to create progress monitors"""
    if monitor_type.lower() == "detailed":
        # Extract only parameters supported by DetailedProgressMonitor
        detailed_kwargs = {
            "update_interval": kwargs.get("update_interval", 1.0),
            "log_level": kwargs.get("log_level", logging.INFO),
        }
        return DetailedProgressMonitor(total_files, **detailed_kwargs)
    elif monitor_type.lower() == "enhanced":
        # Enhanced monitor with all features enabled
        kwargs.setdefault("enable_resources", True)
        kwargs.setdefault("enable_checkpoint", True)
        kwargs.setdefault("update_interval", 0.5)  # More frequent updates
        return ProgressMonitor(total_files, **kwargs)
    else:
        return ProgressMonitor(total_files, **kwargs)
