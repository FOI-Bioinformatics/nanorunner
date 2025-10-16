#!/usr/bin/env python3
"""
Example 2: Timing Models Demonstration

Description:
    Demonstrates all four timing models available in NanoRunner:
    1. Uniform - constant intervals (deterministic)
    2. Random - symmetric variation around base interval
    3. Poisson - biologically realistic with burst behavior
    4. Adaptive - dynamic adjustment based on history

Usage:
    python examples/02_timing_models.py

Requirements:
    - nanorunner installed
    - Sample data in examples/sample_data/

Expected Output:
    - Four separate simulations, one for each timing model
    - Observable differences in timing behavior
    - Completes in ~15-20 seconds total
"""

from pathlib import Path
import tempfile
import shutil
from nanopore_simulator import SimulationConfig, NanoporeSimulator


def run_simulation_with_model(model_name, model_params, description):
    """Helper function to run simulation with specific timing model"""
    print(f"\n{'=' * 60}")
    print(f"Timing Model: {model_name.upper()}")
    print(f"{'=' * 60}")
    print(f"Description: {description}")
    print()

    source_dir = Path("examples/sample_data/singleplex")
    target_dir = Path(tempfile.gettempdir()) / f"nanorunner_timing_{model_name}"

    # Clean up previous run
    if target_dir.exists():
        shutil.rmtree(target_dir)

    # Create configuration with specific timing model
    config = SimulationConfig(
        source_dir=source_dir,
        target_dir=target_dir,
        interval=2.0,  # Base interval of 2 seconds
        operation="copy",
        timing_model=model_name,
        timing_model_params=model_params,
    )

    # Run simulation
    simulator = NanoporeSimulator(config, enable_monitoring=True)
    simulator.run_simulation()

    print(f"\n✓ Output: {target_dir}\n")


def main():
    print("=" * 60)
    print("Example 2: Timing Models Demonstration")
    print("=" * 60)
    print()
    print("This example demonstrates the four timing models.")
    print("Observe how intervals vary between each model.")
    print()

    # 1. Uniform Model - Constant intervals
    run_simulation_with_model(
        model_name="uniform",
        model_params={},
        description="Exactly 2.0 seconds between each file (deterministic)",
    )

    # 2. Random Model - Symmetric variation
    run_simulation_with_model(
        model_name="random",
        model_params={"random_factor": 0.3},  # ±30% variation
        description="Random intervals between 1.4-2.6 seconds (±30%)",
    )

    # 3. Poisson Model - Realistic sequencing pattern
    run_simulation_with_model(
        model_name="poisson",
        model_params={
            "burst_probability": 0.2,  # 20% chance of burst
            "burst_rate_multiplier": 4.0,  # 4x faster during burst
        },
        description="Exponential intervals with 20% burst probability",
    )

    # 4. Adaptive Model - Dynamic adjustment
    run_simulation_with_model(
        model_name="adaptive",
        model_params={
            "adaptation_rate": 0.2,  # 20% adaptation
            "history_size": 5,  # Remember last 5 intervals
        },
        description="Adapts intervals based on recent history",
    )

    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print()
    print("All four timing models demonstrated:")
    print("  1. Uniform:  Predictable, constant intervals")
    print("  2. Random:   Controlled variation for robustness testing")
    print("  3. Poisson:  Biologically realistic sequencing pattern")
    print("  4. Adaptive: Dynamic response to processing speed")
    print()
    print("Use case recommendations:")
    print("  - Testing:      uniform")
    print("  - Robustness:   random")
    print("  - Realism:      poisson")
    print("  - Bottlenecks:  adaptive")
    print()

    # Cleanup instructions
    print("To clean up all outputs:")
    print("  rm -rf /tmp/nanorunner_timing_*")
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
