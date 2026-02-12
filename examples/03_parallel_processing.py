#!/usr/bin/env python3
"""
Example 3: Parallel Processing with Enhanced Monitoring

Description:
    Demonstrates high-throughput simulation using parallel processing
    with multiple worker threads and enhanced monitoring capabilities.
    Shows resource usage tracking and performance metrics.

Usage:
    python examples/03_parallel_processing.py

Requirements:
    - nanorunner installed
    - nanorunner[enhanced] for resource monitoring (optional)
    - Sample data in examples/sample_data/

Expected Output:
    - Processes files in parallel with 4 workers
    - Real-time progress with CPU/memory monitoring
    - Performance comparison: sequential vs parallel
    - Completes in ~5-10 seconds
"""

from pathlib import Path
import tempfile
import shutil
import time
from nanopore_simulator import SimulationConfig, NanoporeSimulator


def run_sequential_simulation():
    """Run simulation without parallel processing"""
    print("\n" + "=" * 60)
    print("Sequential Processing (Baseline)")
    print("=" * 60)
    print()

    source_dir = Path("examples/sample_data/multiplex")
    target_dir = Path(tempfile.gettempdir()) / "nanorunner_sequential"

    if target_dir.exists():
        shutil.rmtree(target_dir)

    config = SimulationConfig(
        source_dir=source_dir,
        target_dir=target_dir,
        interval=0.5,  # Fast intervals for comparison
        operation="copy",
        timing_model="uniform",
        batch_size=1,  # Process one file at a time
        parallel_processing=False,
    )

    start_time = time.time()
    simulator = NanoporeSimulator(config, enable_monitoring=True)
    simulator.run_simulation()
    elapsed = time.time() - start_time

    print(f"\n✓ Sequential completed in {elapsed:.2f} seconds")
    return elapsed


def run_parallel_simulation():
    """Run simulation with parallel processing"""
    print("\n" + "=" * 60)
    print("Parallel Processing (4 Workers)")
    print("=" * 60)
    print()

    source_dir = Path("examples/sample_data/multiplex")
    target_dir = Path(tempfile.gettempdir()) / "nanorunner_parallel"

    if target_dir.exists():
        shutil.rmtree(target_dir)

    config = SimulationConfig(
        source_dir=source_dir,
        target_dir=target_dir,
        interval=0.5,  # Same intervals for fair comparison
        operation="copy",
        timing_model="uniform",
        batch_size=4,  # Process batch of 4 files
        parallel_processing=True,
        worker_count=4,
    )

    start_time = time.time()
    simulator = NanoporeSimulator(config, enable_monitoring=True, monitor_type="enhanced")
    simulator.run_simulation()
    elapsed = time.time() - start_time

    print(f"\n✓ Parallel completed in {elapsed:.2f} seconds")
    return elapsed


def main():
    print("=" * 60)
    print("Example 3: Parallel Processing & Enhanced Monitoring")
    print("=" * 60)
    print()
    print("This example compares sequential vs parallel processing.")
    print("With enhanced monitoring (if psutil is installed).")
    print()

    # Check for psutil
    try:
        import psutil
        print("psutil installed - Enhanced monitoring available")
    except ImportError:
        from nanopore_simulator.core.deps import get_install_hint

        print("psutil not installed - Basic monitoring only")
        print(f"  Install with: {get_install_hint('psutil')}")
    print()

    # Run both simulations
    sequential_time = run_sequential_simulation()
    parallel_time = run_parallel_simulation()

    # Performance comparison
    print("\n" + "=" * 60)
    print("Performance Comparison")
    print("=" * 60)
    print()
    print(f"Sequential:  {sequential_time:.2f} seconds")
    print(f"Parallel:    {parallel_time:.2f} seconds")

    if parallel_time < sequential_time:
        speedup = sequential_time / parallel_time
        print(f"\nSpeedup:     {speedup:.2f}x faster with parallel processing")
    else:
        print("\nNote: Parallel overhead may exceed benefits for small datasets")

    print()
    print("Key Observations:")
    print("  - Parallel processing best for large datasets (>100 files)")
    print("  - Batch size affects throughput (try different values)")
    print("  - Enhanced monitoring shows CPU/memory usage")
    print("  - Worker count should match CPU cores")
    print()

    # Cleanup instructions
    print("To clean up:")
    print("  rm -rf /tmp/nanorunner_sequential /tmp/nanorunner_parallel")
    print()

    return 0


if __name__ == "__main__":
    try:
        exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        exit(1)
