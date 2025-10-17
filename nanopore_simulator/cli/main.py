"""Command line interface for nanopore simulator"""

import argparse
import sys
from pathlib import Path

from ..core.config import SimulationConfig
from ..core.simulator import NanoporeSimulator
from ..core.profiles import (
    get_available_profiles,
    create_config_from_profile,
    get_profile_recommendations,
    validate_profile_name,
)
from ..core.adapters import (
    get_available_adapters,
    validate_for_pipeline,
    get_compatible_pipelines,
)
from ..core.detector import FileStructureDetector


def list_profiles_command() -> int:
    """List available configuration profiles"""
    profiles = get_available_profiles()
    print("Available Configuration Profiles:")
    print("=" * 50)
    for name, description in profiles.items():
        print(f"  {name:20} - {description}")
    return 0


def list_adapters_command() -> int:
    """List available pipeline adapters"""
    adapters = get_available_adapters()
    print("Available Pipeline Adapters:")
    print("=" * 50)
    for name, description in adapters.items():
        print(f"  {name:15} - {description}")
    return 0


def recommend_profiles_command(source_dir: Path) -> int:
    """Recommend profiles based on source directory"""
    if not source_dir.exists():
        print(f"Error: Source directory does not exist: {source_dir}")
        return 1

    # Count files for recommendations
    files = FileStructureDetector._find_sequencing_files(source_dir)
    file_count = len(files)

    print(f"Analysis of {source_dir}:")
    print(f"  Found {file_count} sequencing files")

    # Detect structure
    structure = FileStructureDetector.detect_structure(source_dir)
    print(f"  Detected structure: {structure}")

    # Get recommendations
    recommendations = get_profile_recommendations(file_count, "general")
    print(f"\nRecommended profiles for {file_count} files:")
    for i, profile_name in enumerate(recommendations, 1):
        profiles = get_available_profiles()
        description = profiles.get(profile_name, "Unknown profile")
        print(f"  {i}. {profile_name} - {description}")

    return 0


def validate_pipeline_command(target_dir: Path, pipeline: str) -> int:
    """Validate directory structure for a pipeline"""
    if not target_dir.exists():
        print(f"Error: Target directory does not exist: {target_dir}")
        return 1

    report = validate_for_pipeline(pipeline, target_dir)

    print(f"Pipeline validation report for '{pipeline}':")
    print("=" * 50)
    print(f"Valid: {'✓' if report.get('valid', False) else '✗'}")

    if "files_found" in report and report["files_found"]:
        print(f"Files found: {len(report['files_found'])}")
        for file_path in report["files_found"][:5]:  # Show first 5 files
            print(f"  - {file_path}")
        if len(report["files_found"]) > 5:
            print(f"  ... and {len(report['files_found']) - 5} more")

    if report.get("warnings"):
        print("Warnings:")
        for warning in report["warnings"]:
            print(f"  ⚠ {warning}")

    if report.get("errors"):
        print("Errors:")
        for error in report["errors"]:
            print(f"  ✗ {error}")

    return 0 if report.get("valid", False) else 1


def main() -> int:
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Advanced nanopore sequencing run simulator with profiles and pipeline support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic simulation
  nanorunner /data/source /watch/output --interval 5

  # Use a configuration profile
  nanorunner /data/source /watch/output --profile rapid_sequencing

  # High-throughput simulation with parallel processing
  nanorunner /data/source /watch/output --profile high_throughput --parallel

  # Enhanced monitoring with resource tracking and interactive controls
  nanorunner /data/source /watch/output --monitor enhanced

  # Poisson timing model with custom parameters
  nanorunner /data/source /watch/output --timing-model poisson --burst-probability 0.2

  # Random timing with custom factor
  nanorunner /data/source /watch/output --timing-model random --random-factor 0.4

  # Detailed monitoring with verbose logging
  nanorunner /data/source /watch/output --monitor detailed

  # List available profiles
  nanorunner --list-profiles

  # Get profile recommendations
  nanorunner --recommend /path/to/data

  # Validate for specific pipeline
  nanorunner --validate-pipeline kraken /target/dir

  # Enhanced features require: pip install nanorunner[enhanced]
        """,
    )

    # Command-specific arguments
    parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="List all available configuration profiles",
    )
    parser.add_argument(
        "--list-adapters",
        action="store_true",
        help="List all available pipeline adapters",
    )
    parser.add_argument(
        "--recommend",
        type=Path,
        metavar="SOURCE_DIR",
        help="Get profile recommendations for a source directory",
    )
    parser.add_argument(
        "--validate-pipeline",
        nargs=2,
        metavar=("PIPELINE", "TARGET_DIR"),
        help="Validate target directory for a specific pipeline",
    )

    # Main simulation arguments (optional for some commands)
    parser.add_argument(
        "source_dir",
        type=Path,
        nargs="?",
        help="Source directory containing FASTQ/POD5 files",
    )
    parser.add_argument(
        "target_dir",
        type=Path,
        nargs="?",
        help="Target directory for pipeline to watch",
    )

    # Configuration options
    parser.add_argument(
        "--profile", type=str, help="Use a predefined configuration profile"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Seconds between file operations (default: 5.0)",
    )
    parser.add_argument(
        "--operation",
        choices=["copy", "link"],
        default="copy",
        help="File operation: copy files or create symlinks (default: copy)",
    )
    parser.add_argument(
        "--force-structure",
        choices=["singleplex", "multiplex"],
        help="Force specific structure instead of auto-detection",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1,
        help="Number of files to process per interval (default: 1)",
    )

    # Timing model options
    parser.add_argument(
        "--timing-model",
        choices=["uniform", "random", "poisson", "adaptive"],
        help="Timing model to use (overrides profile setting)",
    )
    parser.add_argument(
        "--burst-probability",
        type=float,
        help="Burst probability for Poisson model (0.0-1.0)",
    )
    parser.add_argument(
        "--burst-rate-multiplier",
        type=float,
        help="Burst rate multiplier for Poisson model",
    )

    # Advanced timing options
    parser.add_argument(
        "--random-factor",
        type=float,
        help="Randomness factor for random timing model (0.0-1.0)",
    )
    parser.add_argument(
        "--adaptation-rate",
        type=float,
        help="Adaptation rate for adaptive timing model (0.0-1.0, default: 0.1)",
    )
    parser.add_argument(
        "--history-size",
        type=int,
        help="History size for adaptive timing model (default: 10)",
    )

    # Parallel processing options
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Enable parallel processing within batches",
    )
    parser.add_argument(
        "--worker-count",
        type=int,
        default=4,
        help="Number of worker threads for parallel processing (default: 4)",
    )

    # Monitoring options
    parser.add_argument(
        "--monitor",
        choices=["default", "detailed", "enhanced", "none"],
        default="default",
        help="Progress monitoring level: default (basic), detailed (verbose logging), enhanced (resource monitoring + interactive controls), none (silent)",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output")

    # Pipeline validation
    parser.add_argument(
        "--pipeline",
        type=str,
        help="Validate output for specific pipeline compatibility",
    )

    parser.add_argument("--version", action="version", version="%(prog)s 2.0.1")

    args = parser.parse_args()

    # Handle command-specific operations
    if args.list_profiles:
        return list_profiles_command()

    if args.list_adapters:
        return list_adapters_command()

    if args.recommend:
        return recommend_profiles_command(args.recommend)

    if args.validate_pipeline:
        pipeline_name, target_dir = args.validate_pipeline
        return validate_pipeline_command(Path(target_dir), pipeline_name)

    # Main simulation requires source and target directories
    if not args.source_dir or not args.target_dir:
        parser.error("source_dir and target_dir are required for simulation")

    if not args.source_dir.exists():
        parser.error(f"Source directory does not exist: {args.source_dir}")

    # Validate arguments
    if args.random_factor is not None and (
        args.random_factor < 0.0 or args.random_factor > 1.0
    ):
        parser.error("Random factor must be between 0.0 and 1.0")

    if args.burst_probability is not None and (
        args.burst_probability < 0.0 or args.burst_probability > 1.0
    ):
        parser.error("Burst probability must be between 0.0 and 1.0")

    if args.burst_rate_multiplier is not None and args.burst_rate_multiplier <= 0:
        parser.error("Burst rate multiplier must be positive")

    if args.adaptation_rate is not None and (
        args.adaptation_rate < 0.0 or args.adaptation_rate > 1.0
    ):
        parser.error("Adaptation rate must be between 0.0 and 1.0")

    if args.history_size is not None and args.history_size < 1:
        parser.error("History size must be at least 1")

    # Create configuration
    try:
        if args.profile:
            # Validate profile exists
            if not validate_profile_name(args.profile):
                parser.error(f"Unknown profile: {args.profile}")

            # Build timing model params from CLI arguments
            timing_model_params = {}

            # Handle Poisson model parameters
            if args.burst_probability is not None:
                timing_model_params["burst_probability"] = args.burst_probability
            if args.burst_rate_multiplier is not None:
                timing_model_params["burst_rate_multiplier"] = (
                    args.burst_rate_multiplier
                )

            # Handle random model parameters
            if args.random_factor is not None:
                timing_model_params["random_factor"] = args.random_factor

            # Handle adaptive model parameters
            if args.adaptation_rate is not None:
                timing_model_params["adaptation_rate"] = args.adaptation_rate
            if args.history_size is not None:
                timing_model_params["history_size"] = args.history_size

            # Create config from profile with overrides
            overrides = {}
            if args.timing_model:
                overrides["timing_model"] = args.timing_model
                overrides["timing_model_params"] = timing_model_params
            elif timing_model_params:
                overrides["timing_model_params"] = timing_model_params

            if args.operation != "copy":
                overrides["operation"] = args.operation
            if args.batch_size != 1:
                overrides["batch_size"] = args.batch_size
            if args.parallel:
                overrides["parallel_processing"] = True
            if args.worker_count != 4:
                overrides["worker_count"] = args.worker_count
            if args.force_structure:
                overrides["force_structure"] = args.force_structure

            config = create_config_from_profile(
                args.profile,
                args.source_dir,
                args.target_dir,
                args.interval,
                **overrides,
            )
        else:
            # Build timing model configuration
            timing_model = args.timing_model or "uniform"
            timing_model_params = {}

            if timing_model == "random":
                if args.random_factor is not None:
                    timing_model_params["random_factor"] = args.random_factor
            elif timing_model == "poisson":
                if args.burst_probability is not None:
                    timing_model_params["burst_probability"] = args.burst_probability
                if args.burst_rate_multiplier is not None:
                    timing_model_params["burst_rate_multiplier"] = (
                        args.burst_rate_multiplier
                    )
            elif timing_model == "adaptive":
                if args.adaptation_rate is not None:
                    timing_model_params["adaptation_rate"] = args.adaptation_rate
                if args.history_size is not None:
                    timing_model_params["history_size"] = args.history_size

            # Create standard configuration
            config = SimulationConfig(
                source_dir=args.source_dir,
                target_dir=args.target_dir,
                interval=args.interval,
                operation=args.operation,
                force_structure=args.force_structure,
                batch_size=args.batch_size,
                timing_model=timing_model,
                timing_model_params=timing_model_params,
                parallel_processing=args.parallel,
                worker_count=args.worker_count,
            )

        # Determine monitoring settings
        enable_monitoring = not args.quiet and args.monitor != "none"
        monitor_type = args.monitor if enable_monitoring else "default"

        # Handle enhanced monitoring options
        if monitor_type == "enhanced":
            # Warn if psutil not available
            try:
                import psutil
            except ImportError:
                print(
                    "Warning: Enhanced monitoring requires psutil. Install with: pip install nanorunner[enhanced]"
                )
                print("Falling back to detailed monitoring mode.")
                monitor_type = "detailed"

        # Run simulation
        simulator = NanoporeSimulator(config, enable_monitoring, monitor_type)

        # Print helpful instructions for enhanced monitoring
        if monitor_type == "enhanced":
            print("Enhanced monitoring active. Interactive controls:")
            print("  - Ctrl+C: Graceful shutdown with summary")
            print("  - SIGTERM: Graceful shutdown (on Unix systems)")
            print("  - Progress is automatically checkpointed every 10 files")
            print("  - Resource usage (CPU, memory) is monitored\n")

        simulator.run_simulation()

        # Post-simulation pipeline validation if requested
        if args.pipeline:
            print(f"\nValidating output for {args.pipeline} pipeline...")
            report = validate_for_pipeline(args.pipeline, args.target_dir)
            if report.get("valid", False):
                print(f"✓ Output is compatible with {args.pipeline} pipeline")
            else:
                print(f"✗ Output may not be compatible with {args.pipeline} pipeline")
                if report.get("warnings"):
                    for warning in report["warnings"]:
                        print(f"  ⚠ {warning}")

    except KeyboardInterrupt:
        print("\nSimulation interrupted by user")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
