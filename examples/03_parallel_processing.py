#!/usr/bin/env python3
"""
Example 3: Parallel Processing with Monitoring

Level: Intermediate
Time: ~2 minutes
Description:
    Demonstrates high-throughput replay using parallel file processing
    with multiple worker threads and the basic progress monitor.
    Compares sequential and parallel execution against the same source
    data so that throughput differences are attributable only to worker
    count and batch size.

    For resource-level metrics (CPU, memory) install the optional
    psutil dependency and set monitor_type="enhanced".

Usage:
    python examples/03_parallel_processing.py

Requirements:
    - nanorunner installed (pip install -e .)
    - nanorunner[enhanced] recommended for resource monitoring
    - Sample data in examples/sample_data/

Expected Output:
    - Sequential and parallel runs against the multiplex sample data
    - Elapsed-time comparison
    - Note on when parallel processing provides meaningful benefit
    - Completes in ~5-10 seconds
"""

import shutil
import tempfile
import time
from pathlib import Path

from nanopore_simulator import ReplayConfig, run_replay


def run_sequential(source_dir: Path) -> float:
    """Replay with a single worker (baseline).

    Returns elapsed wall-clock time in seconds.
    """
    print("\n" + "=" * 60)
    print("Sequential processing (baseline)")
    print("=" * 60)

    target_dir = Path(tempfile.mkdtemp(prefix="nanorunner_seq_"))
    try:
        config = ReplayConfig(
            source_dir=source_dir,
            target_dir=target_dir,
            interval=0.1,
            operation="copy",
            timing_model="uniform",
            batch_size=1,
            parallel=False,
            monitor_type="basic",
        )
        start = time.monotonic()
        run_replay(config)
        elapsed = time.monotonic() - start
    finally:
        shutil.rmtree(target_dir, ignore_errors=True)

    print(f"\nSequential completed in {elapsed:.2f} s")
    return elapsed


def run_parallel(source_dir: Path) -> float:
    """Replay with four worker threads.

    Returns elapsed wall-clock time in seconds.
    """
    print("\n" + "=" * 60)
    print("Parallel processing (4 workers, batch size 4)")
    print("=" * 60)

    target_dir = Path(tempfile.mkdtemp(prefix="nanorunner_par_"))

    # Detect whether psutil is available for enhanced monitoring.
    try:
        import psutil  # noqa: F401
        monitor = "enhanced"
        print("  psutil detected -- using enhanced monitor")
    except ImportError:
        monitor = "basic"
        print("  psutil not installed -- using basic monitor")
        print("  Install enhanced monitoring: pip install nanorunner[enhanced]")

    try:
        config = ReplayConfig(
            source_dir=source_dir,
            target_dir=target_dir,
            interval=0.1,
            operation="copy",
            timing_model="uniform",
            batch_size=4,
            parallel=True,
            workers=4,
            monitor_type=monitor,
        )
        start = time.monotonic()
        run_replay(config)
        elapsed = time.monotonic() - start
    finally:
        shutil.rmtree(target_dir, ignore_errors=True)

    print(f"\nParallel completed in {elapsed:.2f} s")
    return elapsed


def main() -> int:
    print("=" * 60)
    print("Example 3: Parallel Processing with Monitoring")
    print("=" * 60)
    print()
    print("Sequential vs. parallel replay on multiplex sample data.")
    print()

    source_dir = Path(__file__).parent / "sample_data" / "multiplex"
    if not source_dir.exists():
        print(f"Error: sample data not found at {source_dir}")
        print("Run this script from the repository root directory.")
        return 1

    seq_time = run_sequential(source_dir)
    par_time = run_parallel(source_dir)

    print()
    print("=" * 60)
    print("Performance comparison")
    print("=" * 60)
    print()
    print(f"  Sequential:  {seq_time:.2f} s")
    print(f"  Parallel:    {par_time:.2f} s")

    if par_time < seq_time:
        speedup = seq_time / par_time
        print(f"  Speedup:     {speedup:.2f}x")
    else:
        print()
        print(
            "  Note: parallel overhead may exceed gains for small file counts.\n"
            "  Parallel processing yields meaningful throughput improvement\n"
            "  primarily for datasets with more than ~100 files."
        )

    print()
    print("Configuration guidance:")
    print("  parallel=True, workers=N  -- enable N worker threads per batch")
    print("  batch_size=N              -- files processed per timing interval")
    print("  monitor_type='enhanced'   -- CPU/memory metrics (requires psutil)")
    print()

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        raise SystemExit(1)
    except Exception as exc:
        print(f"\nError: {exc}")
        raise SystemExit(1)
