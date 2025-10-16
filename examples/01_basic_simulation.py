#!/usr/bin/env python3
"""
Example 1: Basic Simulation

Description:
    Minimal working example of NanoRunner showing basic file simulation
    from singleplex data structure to a target directory.

Usage:
    python examples/01_basic_simulation.py

Requirements:
    - nanorunner installed
    - Sample data in examples/sample_data/

Expected Output:
    - Creates /tmp/nanorunner_basic_output/
    - Copies 2 FASTQ files with 1-second intervals
    - Shows progress: "2/2 files | 100.0%"
    - Completes in ~2-3 seconds
"""

from pathlib import Path
import tempfile
import shutil
from nanopore_simulator import SimulationConfig, NanoporeSimulator


def main():
    print("=" * 60)
    print("Example 1: Basic Simulation")
    print("=" * 60)
    print()

    # Define source and target directories
    source_dir = Path("examples/sample_data/singleplex")
    target_dir = Path(tempfile.gettempdir()) / "nanorunner_basic_output"

    # Clean up any previous runs
    if target_dir.exists():
        shutil.rmtree(target_dir)

    # Check source data exists
    if not source_dir.exists():
        print(f"Error: Sample data not found at {source_dir}")
        print("Please run this script from the repository root directory")
        return 1

    print(f"Source: {source_dir}")
    print(f"Target: {target_dir}")
    print()

    # Create simulation configuration
    # - interval=1.0: 1 second between file operations
    # - operation="copy": copy files (not symlinks)
    # - timing_model="uniform": constant intervals (deterministic)
    config = SimulationConfig(
        source_dir=source_dir,
        target_dir=target_dir,
        interval=1.0,
        operation="copy",
        timing_model="uniform",
    )

    # Create and run simulator
    print("Starting simulation...")
    print("-" * 60)
    simulator = NanoporeSimulator(config, enable_monitoring=True)
    simulator.run_simulation()
    print("-" * 60)
    print()

    # Verify results
    copied_files = list(target_dir.glob("*.fastq"))
    print(f"✓ Success! Copied {len(copied_files)} files to {target_dir}")
    print()
    print("Output files:")
    for file_path in sorted(copied_files):
        print(f"  - {file_path.name}")
    print()

    # Cleanup instructions
    print("To clean up:")
    print(f"  rm -rf {target_dir}")
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
