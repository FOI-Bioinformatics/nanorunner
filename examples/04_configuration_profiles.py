#!/usr/bin/env python3
"""
Example 4: Configuration Profiles

Level: Intermediate
Time: ~2 minutes
Description:
    Demonstrates the built-in configuration profiles that provide
    pre-parameterised settings for common sequencing scenarios.

    Profiles are plain dicts returned by get_profile() or apply_profile().
    apply_profile() supports an optional overrides argument so that
    individual parameters can be customised without rebuilding the full
    configuration from scratch.

    Profile field names differ from ReplayConfig field names in two
    places:
      - "timing_model_params"  ->  timing_params  (ReplayConfig)
      - "parallel_processing"  ->  parallel        (ReplayConfig)
      - "worker_count"         ->  workers         (ReplayConfig)

    This example shows how to map them correctly.

Usage:
    python examples/04_configuration_profiles.py

Requirements:
    - nanorunner installed (pip install -e .)
    - Sample data in examples/sample_data/

Expected Output:
    - Lists all available profiles with their descriptions
    - Runs three profiles against the singleplex sample data
    - Demonstrates per-parameter override on the bursty profile
    - Completes in ~10-15 seconds
"""

import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict

from nanopore_simulator import ReplayConfig, run_replay
from nanopore_simulator.profiles import PROFILES, apply_profile, list_profiles


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def profile_params_to_config_kwargs(params: Dict[str, Any]) -> Dict[str, Any]:
    """Translate profile field names to ReplayConfig field names.

    Profiles use timing_model_params, parallel_processing, and worker_count.
    ReplayConfig uses timing_params, parallel, and workers.
    """
    kwargs = dict(params)
    if "timing_model_params" in kwargs:
        kwargs["timing_params"] = kwargs.pop("timing_model_params")
    if "parallel_processing" in kwargs:
        kwargs["parallel"] = kwargs.pop("parallel_processing")
    if "worker_count" in kwargs:
        kwargs["workers"] = kwargs.pop("worker_count")
    # "operation" is in both -- no translation needed.
    return kwargs


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def show_available_profiles() -> None:
    """Print all profiles with their descriptions."""
    print("\n" + "=" * 60)
    print("Available configuration profiles")
    print("=" * 60)
    print()
    for name, description in list_profiles().items():
        print(f"  {name}")
        print(f"    {description}")
    print()


def show_profile_details(name: str) -> None:
    """Print the parameter values stored in a profile."""
    profile = PROFILES.get(name, {})
    print(f"  Profile '{name}' parameters:")
    for key, value in profile.items():
        if key == "description":
            continue
        print(f"    {key}: {value}")
    print()


# ---------------------------------------------------------------------------
# Simulation helpers
# ---------------------------------------------------------------------------


def run_with_profile(
    profile_name: str,
    source_dir: Path,
    interval_override: float = 0.5,
) -> None:
    """Run a replay simulation using the named profile.

    Args:
        profile_name: A key from PROFILES.
        source_dir: Path to the source FASTQ directory.
        interval_override: Base interval to use (overrides profile default).
    """
    print(f"\n{'=' * 60}")
    print(f"Profile: {profile_name}")
    print(f"{'=' * 60}")

    params = apply_profile(profile_name, overrides={"interval": interval_override})
    kwargs = profile_params_to_config_kwargs(params)

    # Ensure interval and monitor_type are present.
    kwargs.setdefault("interval", interval_override)
    kwargs.setdefault("monitor_type", "basic")

    target_dir = Path(tempfile.mkdtemp(prefix=f"nanorunner_profile_{profile_name}_"))
    try:
        config = ReplayConfig(
            source_dir=source_dir,
            target_dir=target_dir,
            **kwargs,
        )
        print(f"  timing_model: {config.timing_model}")
        print(f"  batch_size:   {config.batch_size}")
        print(f"  parallel:     {config.parallel}")
        print(f"  workers:      {config.workers}")
        print()

        run_replay(config)
        produced = list(target_dir.rglob("*.fastq"))
        print(f"  Produced {len(produced)} file(s).")
    finally:
        shutil.rmtree(target_dir, ignore_errors=True)


def demonstrate_override(source_dir: Path) -> None:
    """Show parameter override on the bursty profile."""
    print("\n" + "=" * 60)
    print("Profile override: bursty with custom parameters")
    print("=" * 60)
    print()

    # Start from bursty but override several fields.
    params = apply_profile(
        "bursty",
        overrides={
            "interval": 0.3,
            "worker_count": 2,
            "batch_size": 2,
        },
    )
    kwargs = profile_params_to_config_kwargs(params)
    kwargs.setdefault("monitor_type", "basic")

    print("  Overridden parameters:")
    print(f"    interval:   {kwargs.get('interval')} s")
    print(f"    workers:    {kwargs.get('workers')}")
    print(f"    batch_size: {kwargs.get('batch_size')}")
    print()

    target_dir = Path(tempfile.mkdtemp(prefix="nanorunner_profile_custom_"))
    try:
        config = ReplayConfig(
            source_dir=source_dir,
            target_dir=target_dir,
            **kwargs,
        )
        run_replay(config)
        produced = list(target_dir.rglob("*.fastq"))
        print(f"  Produced {len(produced)} file(s).")
    finally:
        shutil.rmtree(target_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    print("=" * 60)
    print("Example 4: Configuration Profiles")
    print("=" * 60)
    print()

    source_dir = Path(__file__).parent / "sample_data" / "singleplex"
    if not source_dir.exists():
        print(f"Error: sample data not found at {source_dir}")
        print("Run this script from the repository root directory.")
        return 1

    show_available_profiles()

    run_with_profile("development", source_dir)
    run_with_profile("steady", source_dir)
    run_with_profile("bursty", source_dir)

    demonstrate_override(source_dir)

    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print()
    print("  get_profile(name)        -- retrieve profile dict (or None)")
    print("  apply_profile(name)      -- dict ready for config construction")
    print("  apply_profile(name, {})  -- same with parameter overrides")
    print()
    print("  CLI equivalents:")
    print("    nanorunner replay /src /dst --profile bursty")
    print("    nanorunner replay /src /dst --profile steady --interval 3")
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
