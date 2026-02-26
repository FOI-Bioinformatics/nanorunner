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
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Union

from nanopore_simulator_v2.config import GenerateConfig, ReplayConfig
from nanopore_simulator_v2.executor import execute_entry
from nanopore_simulator_v2.generators import (
    GeneratorConfig,
    ReadGenerator,
    create_generator,
)
from nanopore_simulator_v2.manifest import (
    FileEntry,
    build_generate_manifest,
    build_replay_manifest,
)
from nanopore_simulator_v2.monitoring import (
    NullMonitor,
    ProgressMonitor,
    create_monitor,
)
from nanopore_simulator_v2.timing import TimingModel, create_timing_model

logger = logging.getLogger(__name__)


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
        logger.info("No files found in source directory")
        return

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
        logger.info("No genomes to generate from")
        return

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
    monitor = create_monitor(
        config.monitor_type, total_files=len(manifest)
    )
    monitor.start()

    try:
        # Ensure target directory exists
        config.target_dir.mkdir(parents=True, exist_ok=True)

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
                _execute_batch_parallel(
                    batch, generator, config.workers, monitor
                )
            else:
                _execute_batch_sequential(batch, generator, monitor)

            # Apply timing delay between batches (not after the last)
            if batch_idx < total_batches - 1:
                interval = timing.next_interval()
                if interval > 0:
                    time.sleep(interval)
    finally:
        monitor.stop()


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

    return [
        batches_dict[k] for k in sorted(batches_dict.keys())
    ]


def _execute_batch_sequential(
    batch: List[FileEntry],
    generator: Optional[ReadGenerator],
    monitor: Union[ProgressMonitor, "NullMonitor"],
) -> None:
    """Process a batch of entries sequentially."""
    for entry in batch:
        result = execute_entry(entry, generator)
        _record_progress(result, monitor)


def _execute_batch_parallel(
    batch: List[FileEntry],
    generator: Optional[ReadGenerator],
    workers: int,
    monitor: Union[ProgressMonitor, "NullMonitor"],
) -> None:
    """Process a batch of entries in parallel using threads."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(execute_entry, entry, generator): entry
            for entry in batch
        }
        for future in as_completed(futures):
            result = future.result()
            _record_progress(result, monitor)


def _record_progress(
    result_path: Path,
    monitor: Union[ProgressMonitor, "NullMonitor"],
) -> None:
    """Record a completed file in the monitor."""
    try:
        size = result_path.stat().st_size if result_path.exists() else 0
    except OSError:
        size = 0
    monitor.update(bytes_delta=size)
