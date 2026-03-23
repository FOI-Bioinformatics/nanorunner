#!/usr/bin/env python3
"""
Example 1: Basic Replay Simulation

Level: Beginner
Time: ~1 minute
Description:
    Minimal working example of nanorunner showing basic file replay
    from a singleplex source directory to a target directory.
    Uses ReplayConfig and run_replay -- the two fundamental building
    blocks of replay mode.

Usage:
    python examples/01_basic_simulation.py

Requirements:
    - nanorunner installed (pip install -e .)
    - Sample data in examples/sample_data/

Expected Output:
    - Creates a temporary output directory
    - Copies 2 FASTQ files with 1-second uniform intervals
    - Reports the number of files produced
    - Completes in ~2-3 seconds
"""

import shutil
import tempfile
from pathlib import Path

from nanopore_simulator import ReplayConfig, run_replay


def main() -> int:
    print("=" * 60)
    print("Example 1: Basic Replay Simulation")
    print("=" * 60)
    print()

    # Source directory ships with the repository.
    source_dir = Path(__file__).parent / "sample_data" / "singleplex"
    target_dir = Path(tempfile.mkdtemp(prefix="nanorunner_basic_"))

    if not source_dir.exists():
        print(f"Error: sample data not found at {source_dir}")
        print("Run this script from the repository root directory.")
        return 1

    print(f"Source: {source_dir}")
    print(f"Target: {target_dir}")
    print()

    # Build a replay configuration.
    #
    # Key parameters:
    #   interval=1.0      -- 1 second between batch operations
    #   operation="copy"  -- copy files rather than create symlinks
    #   timing_model="uniform" -- constant interval (deterministic)
    #   monitor_type="basic"   -- print progress to stdout
    config = ReplayConfig(
        source_dir=source_dir,
        target_dir=target_dir,
        interval=1.0,
        operation="copy",
        timing_model="uniform",
        monitor_type="basic",
    )

    print("Starting replay simulation...")
    print("-" * 60)
    run_replay(config)
    print("-" * 60)
    print()

    # Verify output.
    produced = sorted(target_dir.glob("*.fastq"))
    print(f"Produced {len(produced)} file(s) in {target_dir}:")
    for p in produced:
        print(f"  {p.name}")
    print()

    # Clean up.
    shutil.rmtree(target_dir, ignore_errors=True)
    print("Temporary output directory removed.")
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
