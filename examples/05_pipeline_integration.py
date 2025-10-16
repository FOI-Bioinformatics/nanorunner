#!/usr/bin/env python3
"""
Example 5: Pipeline Integration and Validation

Description:
    Demonstrates pipeline adapter usage for validating simulation
    output against specific bioinformatics pipeline requirements.
    Shows validation for nanometanf, Kraken, and custom pipelines.

Usage:
    python examples/05_pipeline_integration.py

Requirements:
    - nanorunner installed
    - Sample data in examples/sample_data/

Expected Output:
    - Simulates data with pipeline validation
    - Generates validation reports
    - Shows compatible pipeline detection
    - Completes in ~3-5 seconds
"""

from pathlib import Path
import tempfile
import shutil
from nanopore_simulator import SimulationConfig, NanoporeSimulator
from nanopore_simulator.core.adapters import (
    get_available_adapters,
    validate_for_pipeline,
    get_compatible_pipelines,
)


def list_available_adapters():
    """Display all available pipeline adapters"""
    print("\n" + "=" * 60)
    print("Available Pipeline Adapters")
    print("=" * 60)
    print()

    adapters = get_available_adapters()
    for name, description in adapters.items():
        print(f"  • {name}")
        print(f"    {description}")
        print()


def simulate_with_validation(pipeline_name):
    """Simulate data and validate for specific pipeline"""
    print("=" * 60)
    print(f"Pipeline: {pipeline_name}")
    print("=" * 60)
    print()

    # Choose appropriate source structure for pipeline
    if pipeline_name == "miniknife":
        source_dir = Path("examples/sample_data/multiplex")
        print("Using multiplex data (required for miniknife)")
    else:
        source_dir = Path("examples/sample_data/singleplex")
        print("Using singleplex data")

    target_dir = Path(tempfile.gettempdir()) / f"nanorunner_pipeline_{pipeline_name}"

    if target_dir.exists():
        shutil.rmtree(target_dir)

    print(f"Target: {target_dir}")
    print()

    # Run simulation
    config = SimulationConfig(
        source_dir=source_dir,
        target_dir=target_dir,
        interval=0.5,
        operation="copy",
        timing_model="uniform",
    )

    simulator = NanoporeSimulator(config, enable_monitoring=False)
    simulator.run_simulation()

    # Validate output for pipeline
    print("\nValidating output structure...")
    report = validate_for_pipeline(pipeline_name, target_dir)

    # Display validation results
    print(f"\nValidation Report for '{pipeline_name}':")
    print("-" * 60)
    print(f"Valid:            {'✓ Yes' if report['valid'] else '✗ No'}")
    print(f"Structure Valid:  {'✓' if report['structure_valid'] else '✗'}")
    print(f"Files Found:      {len(report.get('files_found', []))}")

    if report.get("files_found"):
        print(f"\nSample files:")
        for file_path in report["files_found"][:3]:
            print(f"  - {file_path}")
        if len(report["files_found"]) > 3:
            print(f"  ... and {len(report['files_found']) - 3} more")

    if report.get("warnings"):
        print("\n⚠ Warnings:")
        for warning in report["warnings"]:
            print(f"  - {warning}")

    if report.get("errors"):
        print("\n✗ Errors:")
        for error in report["errors"]:
            print(f"  - {error}")

    print()


def detect_compatible_pipelines():
    """Show compatible pipeline detection"""
    print("=" * 60)
    print("Automatic Pipeline Detection")
    print("=" * 60)
    print()

    # Test with singleplex data
    target_dir = Path(tempfile.gettempdir()) / "nanorunner_pipeline_nanometanf"

    if target_dir.exists():
        compatible = get_compatible_pipelines(target_dir)
        print(f"Output directory: {target_dir}")
        print(f"\nCompatible pipelines detected:")
        if compatible:
            for pipeline in compatible:
                print(f"  ✓ {pipeline}")
        else:
            print("  (none - directory empty or incompatible)")
    else:
        print("(Run previous simulations first)")

    print()


def main():
    print("=" * 60)
    print("Example 5: Pipeline Integration & Validation")
    print("=" * 60)
    print()

    # List available adapters
    list_available_adapters()

    # Simulate and validate for different pipelines
    simulate_with_validation("nanometanf")
    simulate_with_validation("kraken")

    # Note: miniknife requires multiplex structure and sample sheet
    # This will show validation warnings
    print("=" * 60)
    print("Pipeline: miniknife (expected to have warnings)")
    print("=" * 60)
    print()
    print("Miniknife requires:")
    print("  - Multiplex barcode structure")
    print("  - sample_sheet.tsv file")
    print()

    simulate_with_validation("miniknife")

    # Detect compatible pipelines
    detect_compatible_pipelines()

    # Summary
    print("=" * 60)
    print("Pipeline Integration Summary")
    print("=" * 60)
    print()
    print("Pipeline adapters enable:")
    print("  ✓ Validation of output structure")
    print("  ✓ Format checking for specific pipelines")
    print("  ✓ Automatic compatibility detection")
    print("  ✓ Requirements verification")
    print()

    print("Typical workflow:")
    print("  1. Simulate data with nanorunner")
    print("  2. Validate output for target pipeline")
    print("  3. Fix any validation issues")
    print("  4. Start pipeline with validated data")
    print()

    print("CLI usage:")
    print("  # Simulate with validation")
    print("  nanorunner /source /target --pipeline nanometanf")
    print()
    print("  # Validate existing directory")
    print("  nanorunner --validate-pipeline kraken /output/dir")
    print()
    print("  # List available adapters")
    print("  nanorunner --list-adapters")
    print()

    # Cleanup
    print("To clean up:")
    print("  rm -rf /tmp/nanorunner_pipeline_*")
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
