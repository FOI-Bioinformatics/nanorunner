#!/usr/bin/env python3
"""
Example 4: Configuration Profiles

Description:
    Demonstrates using built-in configuration profiles for common
    sequencing scenarios. Profiles provide pre-configured parameter
    sets optimized for specific use cases.

Usage:
    python examples/04_configuration_profiles.py

Requirements:
    - nanorunner installed
    - Sample data in examples/sample_data/

Expected Output:
    - Lists all available profiles
    - Demonstrates 3 different profiles
    - Shows how to override profile parameters
    - Completes in ~10-15 seconds
"""

from pathlib import Path
import tempfile
import shutil
from nanopore_simulator.core.profiles import (
    get_available_profiles,
    create_config_from_profile,
)
from nanopore_simulator import NanoporeSimulator


def list_all_profiles():
    """Display all available profiles"""
    print("\n" + "=" * 60)
    print("Available Configuration Profiles")
    print("=" * 60)
    print()

    profiles = get_available_profiles()
    for name, description in profiles.items():
        print(f"  • {name}")
        print(f"    {description}")
        print()


def run_with_profile(profile_name, description):
    """Run simulation with specific profile"""
    print("=" * 60)
    print(f"Profile: {profile_name}")
    print("=" * 60)
    print(f"{description}")
    print()

    source_dir = Path("examples/sample_data/singleplex")
    target_dir = Path(tempfile.gettempdir()) / f"nanorunner_profile_{profile_name}"

    if target_dir.exists():
        shutil.rmtree(target_dir)

    # Create configuration from profile
    config = create_config_from_profile(
        profile_name=profile_name,
        source_dir=source_dir,
        target_dir=target_dir,
        interval=1.0,  # Override base interval
    )

    # Display profile settings
    print(f"Timing Model: {config.timing_model}")
    print(f"Batch Size:   {config.batch_size}")
    print(f"Parallel:     {config.parallel_processing}")
    print(f"Workers:      {config.worker_count}")
    print()

    # Run simulation
    simulator = NanoporeSimulator(config, enable_monitoring=True)
    simulator.run_simulation()

    print(f"\n✓ Output: {target_dir}\n")


def demonstrate_profile_override():
    """Show how to override profile parameters"""
    print("\n" + "=" * 60)
    print("Profile Override Example")
    print("=" * 60)
    print("Customizing 'rapid_sequencing' profile")
    print()

    source_dir = Path("examples/sample_data/multiplex")
    target_dir = Path(tempfile.gettempdir()) / "nanorunner_custom"

    if target_dir.exists():
        shutil.rmtree(target_dir)

    # Start with rapid_sequencing profile but customize it
    config = create_config_from_profile(
        profile_name="rapid_sequencing",
        source_dir=source_dir,
        target_dir=target_dir,
        interval=0.5,  # Override: faster intervals
        worker_count=2,  # Override: fewer workers
        batch_size=2,  # Override: smaller batches
        operation="link",  # Override: use symlinks instead of copy
    )

    print("Customized Settings:")
    print(f"  Interval:   {config.interval}s (overridden)")
    print(f"  Workers:    {config.worker_count} (overridden)")
    print(f"  Batch Size: {config.batch_size} (overridden)")
    print(f"  Operation:  {config.operation} (overridden)")
    print()

    simulator = NanoporeSimulator(config, enable_monitoring=True)
    simulator.run_simulation()

    print(f"\n✓ Custom output: {target_dir}\n")


def main():
    print("=" * 60)
    print("Example 4: Configuration Profiles")
    print("=" * 60)
    print()

    # List all profiles
    list_all_profiles()

    # Demonstrate different profiles
    run_with_profile(
        profile_name="development_testing",
        description="Fast profile for development and testing",
    )

    run_with_profile(
        profile_name="accurate_mode",
        description="Steady, accurate sequencing with minimal variation",
    )

    run_with_profile(
        profile_name="rapid_sequencing",
        description="High-throughput with burst behavior",
    )

    # Show profile customization
    demonstrate_profile_override()

    # Summary
    print("=" * 60)
    print("Profile Summary")
    print("=" * 60)
    print()
    print("Profiles provide optimized parameter sets for:")
    print("  • Development/testing workflows")
    print("  • Realistic sequencing simulation")
    print("  • High-throughput scenarios")
    print("  • Device-specific patterns (MinION, PromethION)")
    print()
    print("Benefits:")
    print("  ✓ Quick start with sensible defaults")
    print("  ✓ Consistent configuration across runs")
    print("  ✓ Easy to customize with overrides")
    print("  ✓ Optimized for specific use cases")
    print()

    print("CLI usage:")
    print("  nanorunner /source /target --profile rapid_sequencing")
    print("  nanorunner /source /target --profile accurate_mode --interval 3")
    print()

    # Cleanup
    print("To clean up:")
    print("  rm -rf /tmp/nanorunner_profile_* /tmp/nanorunner_custom")
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
