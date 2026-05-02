"""Orchestration runner for replay and generate simulations.

Thin orchestrator that replaces the monolithic simulator class.  It
connects three phases:

1. **Plan** -- ``build_replay_manifest`` / ``build_generate_manifest``
2. **Execute** -- ``execute_entry`` for each file
3. **Monitor** -- ``ProgressMonitor`` / ``NullMonitor`` for progress

Timing between batches is handled by a ``TimingModel``.  Parallel
execution within batches uses ``ThreadPoolExecutor``.
"""

import logging
import shutil
import signal
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from types import FrameType
from typing import Any, Callable, Dict, List, Optional, Union

from nanopore_simulator.config import GenerateConfig, ReplayConfig


class EmptySourceError(RuntimeError):
    """Raised when a manifest is empty -- nothing to replay or generate.

    Distinguishes a legitimate "I forgot to point --source somewhere"
    operator mistake from internal failures, so the CLI can present a
    targeted message and exit with a non-zero code rather than the
    pre-2026-05-02 silent-return behaviour that defeated CI pipelines.
    """
from nanopore_simulator.executor import execute_entry
from nanopore_simulator.generators import (
    GeneratorConfig,
    ReadGenerator,
    create_generator,
)
from nanopore_simulator.manifest import (
    FileEntry,
    build_generate_manifest,
    build_replay_manifest,
)
from nanopore_simulator.monitoring import (
    Monitor,
    create_monitor,
    format_bytes,
)
from nanopore_simulator.timing import create_timing_model

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------
# Signal handling
# -------------------------------------------------------------------


def _signal_handler(signum: int, frame: object) -> None:
    """Convert SIGTERM/SIGHUP into KeyboardInterrupt for clean shutdown."""
    sig_name = signal.Signals(signum).name
    logger.info("Received %s, initiating graceful shutdown", sig_name)
    raise KeyboardInterrupt(f"Received {sig_name}")


# Type alias for signal handler values returned by signal.signal()
_SignalHandler = Union[
    Callable[[int, Optional[FrameType]], Any], int, signal.Handlers, None
]


def _install_signal_handlers() -> Dict[signal.Signals, _SignalHandler]:
    """Install SIGTERM/SIGHUP handlers and return the previous handlers."""
    previous: Dict[signal.Signals, _SignalHandler] = {}
    for sig in (signal.SIGTERM, signal.SIGHUP):
        try:
            previous[sig] = signal.signal(sig, _signal_handler)
        except (OSError, ValueError):
            # Not all signals can be caught on all platforms
            pass
    return previous


def _restore_signal_handlers(previous: Dict[signal.Signals, _SignalHandler]) -> None:
    """Restore signal handlers saved by _install_signal_handlers."""
    for sig, handler in previous.items():
        try:
            signal.signal(sig, handler)  # type: ignore[arg-type]
        except (OSError, ValueError):
            pass


def _estimate_output_size(
    manifest: List[FileEntry],
    config: Union[ReplayConfig, GenerateConfig],
) -> int:
    """Estimate total output size in bytes based on manifest and config.

    For generate mode, the estimate is derived from the number of reads,
    mean read length, and an approximate compression ratio for gzipped
    output.  For replay mode, source file sizes are summed directly.

    Args:
        manifest: Planned file entries.
        config: Simulation configuration.

    Returns:
        Estimated output size in bytes.
    """
    if isinstance(config, GenerateConfig):
        # Approximate bytes per read: header (~50) + sequence + quality + newlines
        # A FASTQ record is roughly (mean_length * 2 + 80) bytes uncompressed.
        bytes_per_read = config.mean_length * 2 + 80
        total_reads = sum(e.read_count or 0 for e in manifest)
        raw_size = total_reads * bytes_per_read
        if config.output_format == "fastq.gz":
            # Typical gzip compression ratio for FASTQ is ~0.25-0.35
            return int(raw_size * 0.30)
        return raw_size

    # Replay mode: estimate from source file sizes
    total = 0
    for entry in manifest:
        if entry.source is not None:
            try:
                total += entry.source.stat().st_size
            except OSError:
                pass
    return total


def _check_disk_space(
    manifest: List[FileEntry],
    config: Union[ReplayConfig, GenerateConfig],
) -> None:
    """Log a warning if estimated output may approach available disk space.

    This check is advisory only and does not prevent execution.

    Args:
        manifest: Planned file entries.
        config: Simulation configuration.
    """
    try:
        estimated = _estimate_output_size(manifest, config)
        usage = shutil.disk_usage(config.target_dir)
    except OSError:
        return

    if estimated > usage.free * 0.8:
        logger.warning(
            "Estimated output size (%s) may approach available disk space (%s)",
            format_bytes(estimated),
            format_bytes(usage.free),
        )
    else:
        logger.debug(
            "Disk space check: estimated %s, available %s",
            format_bytes(estimated),
            format_bytes(usage.free),
        )


def _cleanup_tmp_files(target_dir: Path) -> None:
    """Remove orphaned .tmp files left by interrupted atomic writes.

    Atomic writes use the naming pattern ``.original_name.tmp``, so
    this matches any file ending in ``.tmp`` whose name starts with a dot.
    """
    if not target_dir.exists():
        return
    for tmp_file in target_dir.rglob("*.tmp"):
        try:
            tmp_file.unlink()
            logger.debug("Cleaned up partial file: %s", tmp_file)
        except OSError:
            pass


# -------------------------------------------------------------------
# Public entry points
# -------------------------------------------------------------------


def run_replay(config: ReplayConfig) -> None:
    """Execute a replay simulation.

    Builds a manifest from the source directory, then processes files
    with timing delays and optional parallelism.

    Args:
        config: Replay mode configuration.
    """
    manifest = build_replay_manifest(config)
    if not manifest:
        # Pre-2026-05-02 this returned silently with INFO-level logging,
        # which defeated CI pipelines that check $? -- a forgotten
        # --source pointing at the wrong directory looked exactly like
        # a successful run with nothing to do. Raising lets cli_replay
        # surface a targeted message and exit with code 1.
        raise EmptySourceError(
            f"No FASTQ files found in source directory: {config.source_dir}. "
            f"Check the path and that files match the expected pattern "
            f"(*.fastq, *.fq, *.fastq.gz, *.fq.gz)."
        )

    logger.info("Replay manifest: %d files", len(manifest))
    _execute_manifest(manifest, config)


def run_generate(config: GenerateConfig) -> None:
    """Execute a generate simulation.

    Builds a manifest from genome inputs, creates a read generator,
    and processes entries with timing delays and optional parallelism.

    Args:
        config: Generate mode configuration.
    """
    manifest = build_generate_manifest(config)
    if not manifest:
        # Same rationale as run_replay: silent zero-exit on an empty
        # manifest is hostile to CI. Raise so the CLI exits with a
        # non-zero code and a clear message.
        raise EmptySourceError(
            "No genomes available to generate from. Provide at least "
            "one of --genomes, --species, --mock, or --taxid."
        )

    gen_config = GeneratorConfig(
        num_reads=config.read_count,
        mean_read_length=config.mean_length,
        std_read_length=config.std_length,
        min_read_length=config.min_length,
        mean_quality=config.mean_quality,
        std_quality=config.std_quality,
        reads_per_file=config.reads_per_file,
        output_format=config.output_format,
    )
    generator = create_generator(config.generator_backend, gen_config)

    logger.info(
        "Generate manifest: %d files (%d total reads)",
        len(manifest),
        config.read_count,
    )
    _execute_manifest(manifest, config, generator)


# -------------------------------------------------------------------
# Internal orchestration
# -------------------------------------------------------------------


def _execute_manifest(
    manifest: List[FileEntry],
    config: Union[ReplayConfig, GenerateConfig],
    generator: Optional[ReadGenerator] = None,
) -> None:
    """Process a manifest of file entries with timing and monitoring.

    Args:
        manifest: Ordered list of FileEntry objects.
        config: Configuration (ReplayConfig or GenerateConfig).
        generator: ReadGenerator for generate operations, or None.
    """
    # Create timing model
    timing = create_timing_model(
        config.timing_model,
        config.interval,
        **(config.timing_params or {}),
    )

    # Create monitor
    monitor = create_monitor(config.monitor_type, total_files=len(manifest))
    monitor.start()

    previous_handlers = _install_signal_handlers()
    try:
        # Ensure target directory exists
        config.target_dir.mkdir(parents=True, exist_ok=True)

        _check_disk_space(manifest, config)

        batches = _group_by_batch(manifest)
        total_batches = len(batches)

        for batch_idx, batch in enumerate(batches):
            logger.debug(
                "Processing batch %d/%d (%d files)",
                batch_idx + 1,
                total_batches,
                len(batch),
            )

            if config.parallel and config.workers > 1:
                _execute_batch_parallel(batch, generator, config.workers, monitor)
            else:
                _execute_batch_sequential(batch, generator, monitor)

            # Apply timing delay between batches (not after the last)
            if batch_idx < total_batches - 1:
                interval = timing.next_interval()
                if interval > 0:
                    time.sleep(interval)
    finally:
        monitor.stop()
        _cleanup_tmp_files(config.target_dir)
        _restore_signal_handlers(previous_handlers)


def _group_by_batch(manifest: List[FileEntry]) -> List[List[FileEntry]]:
    """Group entries by their batch number.

    Returns a list of lists, one per batch, preserving order within
    each batch.
    """
    if not manifest:
        return []

    batches_dict: Dict[int, List[FileEntry]] = {}
    for entry in manifest:
        batches_dict.setdefault(entry.batch, []).append(entry)

    return [batches_dict[k] for k in sorted(batches_dict.keys())]


def _execute_batch_sequential(
    batch: List[FileEntry],
    generator: Optional[ReadGenerator],
    monitor: Monitor,
) -> None:
    """Process a batch of entries sequentially."""
    for entry in batch:
        result = execute_entry(entry, generator)
        _record_progress(result, monitor)


_OPERATION_TIMEOUT = 600  # seconds per file operation


def _execute_batch_parallel(
    batch: List[FileEntry],
    generator: Optional[ReadGenerator],
    workers: int,
    monitor: Monitor,
) -> None:
    """Process a batch of entries in parallel using threads."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(execute_entry, entry, generator): entry for entry in batch
        }
        for future in as_completed(futures, timeout=_OPERATION_TIMEOUT):
            result = future.result()
            _record_progress(result, monitor)


def _record_progress(
    result_path: Path,
    monitor: Monitor,
) -> None:
    """Record a completed file in the monitor."""
    try:
        size = result_path.stat().st_size if result_path.exists() else 0
    except OSError:
        size = 0
    monitor.update(bytes_delta=size)
