#!/usr/bin/env python3
"""
Example 2: Timing Models Demonstration

Level: Intermediate
Time: ~3 minutes
Description:
    Demonstrates all four timing models available in nanorunner:
      1. uniform  -- constant intervals (deterministic)
      2. random   -- symmetric variation around a base interval
      3. poisson  -- exponential intervals with burst clusters
      4. adaptive -- smoothly varying intervals via exponential moving average

    Each model is run against the same source data so that the only
    observable difference is the temporal pattern between batches.

Usage:
    python examples/02_timing_models.py

Requirements:
    - nanorunner installed (pip install -e .)
    - Sample data in examples/sample_data/

Expected Output:
    - Four sequential replay simulations
    - A brief summary of recommended use cases for each model
    - Completes in ~15-20 seconds total
"""

import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict

from nanopore_simulator import ReplayConfig, run_replay


def run_with_model(
    model_name: str,
    timing_params: Dict[str, Any],
    description: str,
    source_dir: Path,
) -> None:
    """Run a replay simulation with the specified timing model.

    Args:
        model_name: One of uniform, random, poisson, adaptive.
        timing_params: Additional keyword arguments for the timing model.
        description: Human-readable description printed before the run.
        source_dir: Path to the source FASTQ directory.
    """
    print(f"\n{'=' * 60}")
    print(f"Timing model: {model_name.upper()}")
    print(f"{'=' * 60}")
    print(f"  {description}")
    print()

    target_dir = Path(tempfile.mkdtemp(prefix=f"nanorunner_timing_{model_name}_"))

    try:
        config = ReplayConfig(
            source_dir=source_dir,
            target_dir=target_dir,
            interval=2.0,
            operation="copy",
            timing_model=model_name,
            timing_params=timing_params,
            monitor_type="basic",
        )
        run_replay(config)
        produced = list(target_dir.glob("*.fastq"))
        print(f"  Produced {len(produced)} file(s).")
    finally:
        shutil.rmtree(target_dir, ignore_errors=True)


def main() -> int:
    print("=" * 60)
    print("Example 2: Timing Models Demonstration")
    print("=" * 60)
    print()
    print("Each run uses a 2-second base interval.")
    print("Observe how intervals vary across models.")
    print()

    source_dir = Path(__file__).parent / "sample_data" / "singleplex"
    if not source_dir.exists():
        print(f"Error: sample data not found at {source_dir}")
        print("Run this script from the repository root directory.")
        return 1

    # 1. Uniform -- constant 2.0 s between every batch.
    run_with_model(
        model_name="uniform",
        timing_params={},
        description="Exactly 2.0 s between each batch (deterministic).",
        source_dir=source_dir,
    )

    # 2. Random -- symmetric variation; random_factor=0.3 gives ±30 %.
    run_with_model(
        model_name="random",
        timing_params={"random_factor": 0.3},
        description="Random intervals roughly 1.4-2.6 s (±30 % variation).",
        source_dir=source_dir,
    )

    # 3. Poisson -- exponential intervals with occasional burst clusters.
    #    burst_probability and burst_rate_multiplier are not validated
    #    against empirical nanopore data; they serve as robustness test
    #    parameters only.
    run_with_model(
        model_name="poisson",
        timing_params={
            "burst_probability": 0.2,
            "burst_rate_multiplier": 4.0,
        },
        description=(
            "Exponential inter-batch intervals with 20 % burst probability "
            "and 4x burst rate."
        ),
        source_dir=source_dir,
    )

    # 4. Adaptive -- interval drifts smoothly via exponential moving average.
    run_with_model(
        model_name="adaptive",
        timing_params={
            "adaptation_rate": 0.2,
            "history_size": 5,
        },
        description=(
            "Smoothly varying interval via exponential moving average "
            "(adaptation rate 0.2, history 5)."
        ),
        source_dir=source_dir,
    )

    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print()
    print("  uniform  -- deterministic; suitable for automated tests")
    print("  random   -- controlled stochastic variation; robustness testing")
    print("  poisson  -- irregular bursts; stress-tests pipeline batch handling")
    print("  adaptive -- smooth drift; simulates gradual sequencer load change")
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
