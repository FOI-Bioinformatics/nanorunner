#!/usr/bin/env python3
"""
Example 5: Pipeline Validation with Adapters

Level: Advanced
Time: ~3 minutes
Description:
    Demonstrates pipeline adapter usage for validating that a simulation
    output directory conforms to the file patterns expected by a specific
    bioinformatics pipeline.

    The ADAPTERS registry defines validation specifications for each
    supported pipeline. validate_output() checks a directory against
    those specifications and returns a list of issue descriptions.
    An empty list indicates a valid structure.

    Supported adapters:
      - nanometa  -- Nanometa Live real-time taxonomic analysis
      - kraken    -- Kraken2/KrakenUniq taxonomic classification

Usage:
    python examples/05_pipeline_integration.py

Requirements:
    - nanorunner installed (pip install -e .)
    - Sample data in examples/sample_data/

Expected Output:
    - Lists all registered pipeline adapters with their descriptions
    - Simulates data and validates the output for nanometa and kraken
    - Reports any validation issues found
    - Completes in ~3-5 seconds
"""

import shutil
import tempfile
from pathlib import Path

from nanopore_simulator import ReplayConfig, run_replay
from nanopore_simulator.adapters import ADAPTERS, list_adapters, validate_output


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def show_available_adapters() -> None:
    """Print all registered adapters and their descriptions."""
    print("\n" + "=" * 60)
    print("Registered pipeline adapters")
    print("=" * 60)
    print()
    for name, description in list_adapters().items():
        spec = ADAPTERS[name]
        print(f"  {name}")
        print(f"    {description}")
        print(f"    Accepted patterns: {', '.join(spec['patterns'])}")
    print()


# ---------------------------------------------------------------------------
# Simulation + validation
# ---------------------------------------------------------------------------


def simulate_and_validate(
    pipeline_name: str,
    source_dir: Path,
) -> None:
    """Run a replay simulation then validate the output for a pipeline.

    Args:
        pipeline_name: An adapter key from ADAPTERS (e.g. 'nanometa').
        source_dir: Path to source FASTQ files.
    """
    print(f"\n{'=' * 60}")
    print(f"Pipeline: {pipeline_name}")
    print(f"{'=' * 60}")

    target_dir = Path(tempfile.mkdtemp(prefix=f"nanorunner_pipeline_{pipeline_name}_"))

    try:
        config = ReplayConfig(
            source_dir=source_dir,
            target_dir=target_dir,
            interval=0.1,
            operation="copy",
            timing_model="uniform",
            monitor_type="none",  # suppress progress output for brevity
        )
        run_replay(config)

        # Validate the output structure for the target pipeline.
        issues = validate_output(target_dir, pipeline_name)

        print(f"  Output directory: {target_dir}")
        produced = list(target_dir.rglob("*.fastq")) + list(target_dir.rglob("*.fastq.gz"))
        print(f"  Files produced:   {len(produced)}")
        print()

        if issues:
            print("  Validation FAILED:")
            for issue in issues:
                print(f"    - {issue}")
        else:
            print("  Validation PASSED: output is compatible with this pipeline.")

    finally:
        shutil.rmtree(target_dir, ignore_errors=True)


def demonstrate_validation_failure() -> None:
    """Show what a validation failure looks like against an empty directory."""
    print("\n" + "=" * 60)
    print("Validation against an empty directory (expected failure)")
    print("=" * 60)
    print()

    empty_dir = Path(tempfile.mkdtemp(prefix="nanorunner_empty_"))
    try:
        issues = validate_output(empty_dir, "nanometa")
        if issues:
            print("  Issues reported (as expected):")
            for issue in issues:
                print(f"    - {issue}")
        else:
            print("  (no issues -- unexpected)")
    finally:
        shutil.rmtree(empty_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    print("=" * 60)
    print("Example 5: Pipeline Validation with Adapters")
    print("=" * 60)
    print()

    source_dir = Path(__file__).parent / "sample_data" / "singleplex"
    if not source_dir.exists():
        print(f"Error: sample data not found at {source_dir}")
        print("Run this script from the repository root directory.")
        return 1

    show_available_adapters()

    simulate_and_validate("nanometa", source_dir)
    simulate_and_validate("kraken", source_dir)

    demonstrate_validation_failure()

    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print()
    print("  list_adapters()                  -- all adapter names + descriptions")
    print("  validate_output(path, name)      -- returns list of issues (empty = ok)")
    print("  ADAPTERS[name]['patterns']       -- accepted file pattern globs")
    print()
    print("  Typical workflow:")
    print("    1. Simulate data with run_replay() or run_generate()")
    print("    2. Call validate_output(target_dir, pipeline_name)")
    print("    3. Investigate any reported issues before starting the pipeline")
    print()
    print("  CLI equivalents:")
    print("    nanorunner replay /src /dst --adapter nanometa")
    print("    nanorunner validate /output --adapter kraken")
    print("    nanorunner list-adapters")
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
