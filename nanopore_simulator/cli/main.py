"""Command line interface for nanopore simulator"""

import sys
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

import typer

from .. import __version__
from ..core.config import SimulationConfig
from ..core.simulator import NanoporeSimulator
from ..core.profiles import (
    BUILTIN_PROFILES,
    get_available_profiles,
    create_config_from_profile,
    get_profile_recommendations,
    get_generate_recommendations,
    validate_profile_name,
)
from ..core.adapters import (
    get_available_adapters,
    validate_for_pipeline,
)
from ..core.detector import FileStructureDetector
from ..core.generators import detect_available_backends
from ..core.mocks import BUILTIN_MOCKS, MOCK_ALIASES, get_mock_community
from ..core.species import SpeciesResolver, download_genome, GenomeRef


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TimingModelChoice(str, Enum):
    uniform = "uniform"
    random = "random"
    poisson = "poisson"
    adaptive = "adaptive"


class OperationChoice(str, Enum):
    copy = "copy"
    link = "link"


class MonitorLevel(str, Enum):
    default = "default"
    detailed = "detailed"
    enhanced = "enhanced"
    none = "none"


class OutputFormat(str, Enum):
    fastq = "fastq"
    fastq_gz = "fastq.gz"


class GeneratorBackend(str, Enum):
    auto = "auto"
    builtin = "builtin"
    badread = "badread"
    nanosim = "nanosim"


class SampleType(str, Enum):
    pure = "pure"
    mixed = "mixed"


class ForceStructure(str, Enum):
    singleplex = "singleplex"
    multiplex = "multiplex"


# ---------------------------------------------------------------------------
# Typer app
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="nanorunner",
    help="Nanopore sequencing run simulator for testing bioinformatics pipelines.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    add_completion=False,
    pretty_exceptions_show_locals=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"nanorunner {__version__}")
        raise typer.Exit()


@app.callback()
def _app_callback(
    version: bool = typer.Option(
        False,
        "--version",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """Nanopore sequencing run simulator for testing bioinformatics pipelines."""


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _build_timing_params(
    burst_probability: Optional[float],
    burst_rate_multiplier: Optional[float],
    random_factor: Optional[float],
    adaptation_rate: Optional[float],
    history_size: Optional[int],
) -> dict:
    """Collect timing model sub-parameters into a dict."""
    params: dict = {}
    if burst_probability is not None:
        params["burst_probability"] = burst_probability
    if burst_rate_multiplier is not None:
        params["burst_rate_multiplier"] = burst_rate_multiplier
    if random_factor is not None:
        params["random_factor"] = random_factor
    if adaptation_rate is not None:
        params["adaptation_rate"] = adaptation_rate
    if history_size is not None:
        params["history_size"] = history_size
    return params


def _validate_timing_params(
    burst_probability: Optional[float],
    burst_rate_multiplier: Optional[float],
    random_factor: Optional[float],
    adaptation_rate: Optional[float],
    history_size: Optional[int],
) -> None:
    """Validate timing parameter ranges. Raises typer.BadParameter on error."""
    if random_factor is not None and (random_factor < 0.0 or random_factor > 1.0):
        typer.echo("Error: Random factor must be between 0.0 and 1.0", err=True)
        raise typer.Exit(code=2)
    if burst_probability is not None and (
        burst_probability < 0.0 or burst_probability > 1.0
    ):
        typer.echo("Error: Burst probability must be between 0.0 and 1.0", err=True)
        raise typer.Exit(code=2)
    if burst_rate_multiplier is not None and burst_rate_multiplier <= 0:
        typer.echo("Error: Burst rate multiplier must be positive", err=True)
        raise typer.Exit(code=2)
    if adaptation_rate is not None and (
        adaptation_rate < 0.0 or adaptation_rate > 1.0
    ):
        typer.echo("Error: Adaptation rate must be between 0.0 and 1.0", err=True)
        raise typer.Exit(code=2)
    if history_size is not None and history_size < 1:
        typer.echo("Error: History size must be at least 1", err=True)
        raise typer.Exit(code=2)


def _build_config(
    *,
    target_dir: Path,
    source_dir: Optional[Path] = None,
    is_generate: bool = False,
    profile: Optional[str] = None,
    interval: float = 5.0,
    operation: OperationChoice = OperationChoice.copy,
    force_structure: Optional[ForceStructure] = None,
    batch_size: int = 1,
    reads_per_output_file: Optional[int] = None,
    timing_model: Optional[TimingModelChoice] = None,
    burst_probability: Optional[float] = None,
    burst_rate_multiplier: Optional[float] = None,
    random_factor: Optional[float] = None,
    adaptation_rate: Optional[float] = None,
    history_size: Optional[int] = None,
    parallel: bool = False,
    worker_count: int = 4,
    # Generate-mode parameters
    genomes: Optional[List[Path]] = None,
    generator_backend: GeneratorBackend = GeneratorBackend.auto,
    read_count: int = 1000,
    mean_read_length: int = 5000,
    mean_quality: float = 20.0,
    std_quality: float = 4.0,
    reads_per_file: int = 100,
    output_format: OutputFormat = OutputFormat.fastq_gz,
    mix_reads: bool = False,
    # Species/mock parameters
    species: Optional[List[str]] = None,
    mock: Optional[str] = None,
    taxid: Optional[List[int]] = None,
    sample_type: Optional[SampleType] = None,
    abundances: Optional[List[float]] = None,
    offline: bool = False,
) -> SimulationConfig:
    """Build a SimulationConfig from CLI parameters."""
    timing_params = _build_timing_params(
        burst_probability, burst_rate_multiplier, random_factor,
        adaptation_rate, history_size,
    )
    fs_str = force_structure.value if force_structure else None

    if profile:
        if not validate_profile_name(profile):
            typer.echo(f"Error: Unknown profile: {profile}", err=True)
            raise typer.Exit(code=2)

        overrides: dict = {}
        if timing_model:
            overrides["timing_model"] = timing_model.value
            overrides["timing_model_params"] = timing_params
        elif timing_params:
            overrides["timing_model_params"] = timing_params

        if operation != OperationChoice.copy:
            overrides["operation"] = operation.value
        if batch_size != 1:
            overrides["batch_size"] = batch_size
        if parallel:
            overrides["parallel_processing"] = True
        if worker_count != 4:
            overrides["worker_count"] = worker_count
        if fs_str:
            overrides["force_structure"] = fs_str
        if reads_per_output_file is not None:
            overrides["reads_per_output_file"] = reads_per_output_file

        if is_generate:
            overrides["operation"] = "generate"
            if genomes:
                overrides["genome_inputs"] = genomes
            overrides["generator_backend"] = generator_backend.value
            overrides["read_count"] = read_count
            overrides["mean_read_length"] = mean_read_length
            overrides["mean_quality"] = mean_quality
            overrides["std_quality"] = std_quality
            overrides["reads_per_file"] = reads_per_file
            overrides["output_format"] = output_format.value
            overrides["mix_reads"] = mix_reads

        if species:
            overrides["species_inputs"] = species
        if mock:
            overrides["mock_name"] = mock
        if taxid:
            overrides["taxid_inputs"] = taxid
        if sample_type:
            overrides["sample_type"] = sample_type.value
        if abundances:
            overrides["abundances"] = abundances
        if offline:
            overrides["offline_mode"] = offline

        return create_config_from_profile(
            profile, source_dir, target_dir, interval, **overrides,
        )

    # No profile -- build directly
    tm = timing_model.value if timing_model else "uniform"
    config_kwargs: dict = {
        "target_dir": target_dir,
        "interval": interval,
        "force_structure": fs_str,
        "batch_size": batch_size,
        "timing_model": tm,
        "timing_model_params": timing_params,
        "parallel_processing": parallel,
        "worker_count": worker_count,
    }
    if reads_per_output_file is not None:
        config_kwargs["reads_per_output_file"] = reads_per_output_file

    if is_generate:
        config_kwargs["operation"] = "generate"
        if genomes:
            config_kwargs["genome_inputs"] = genomes
        config_kwargs["generator_backend"] = generator_backend.value
        config_kwargs["read_count"] = read_count
        config_kwargs["mean_read_length"] = mean_read_length
        config_kwargs["mean_quality"] = mean_quality
        config_kwargs["std_quality"] = std_quality
        config_kwargs["reads_per_file"] = reads_per_file
        config_kwargs["output_format"] = output_format.value
        config_kwargs["mix_reads"] = mix_reads
    else:
        config_kwargs["source_dir"] = source_dir
        config_kwargs["operation"] = operation.value

    if species:
        config_kwargs["species_inputs"] = species
    if mock:
        config_kwargs["mock_name"] = mock
    if taxid:
        config_kwargs["taxid_inputs"] = taxid
    if sample_type:
        config_kwargs["sample_type"] = sample_type.value
    if abundances:
        config_kwargs["abundances"] = abundances
    if offline:
        config_kwargs["offline_mode"] = offline

    return SimulationConfig(**config_kwargs)


def _setup_monitoring(
    monitor: MonitorLevel, quiet: bool
) -> tuple:
    """Determine monitoring settings. Returns (enable_monitoring, monitor_type)."""
    enable_monitoring = not quiet and monitor != MonitorLevel.none
    monitor_type = monitor.value if enable_monitoring else "default"

    if monitor_type == "enhanced":
        try:
            import psutil  # noqa: F401
        except ImportError:
            print(
                "Warning: Enhanced monitoring requires psutil. "
                "Install with: pip install nanorunner[enhanced]"
            )
            print("Falling back to detailed monitoring mode.")
            monitor_type = "detailed"

    return enable_monitoring, monitor_type


def _run_simulation(
    config: SimulationConfig,
    enable_monitoring: bool,
    monitor_type: str,
    is_generate: bool = False,
    pipeline: Optional[str] = None,
) -> None:
    """Create simulator, run, and handle post-run validation."""
    try:
        simulator = NanoporeSimulator(config, enable_monitoring, monitor_type)

        if is_generate and hasattr(simulator, "read_generator"):
            from ..core.generators import BuiltinGenerator

            if isinstance(simulator.read_generator, BuiltinGenerator):
                print(
                    "Note: Using builtin generator (error-free reads). "
                    "For realistic error profiles, install badread: "
                    "pip install badread"
                )

        if monitor_type == "enhanced":
            print("Enhanced monitoring active. Interactive controls:")
            print("  - Ctrl+C: Graceful shutdown with summary")
            print("  - SIGTERM: Graceful shutdown (on Unix systems)")
            print("  - Progress is automatically checkpointed every 10 files")
            print("  - Resource usage (CPU, memory) is monitored\n")

        simulator.run_simulation()

        if pipeline:
            print(f"\nValidating output for {pipeline} pipeline...")
            report = validate_for_pipeline(pipeline, config.target_dir)
            if report.get("valid", False):
                print(
                    f"Output is compatible with {pipeline} pipeline"
                )
            else:
                print(
                    f"Output may not be compatible with {pipeline} pipeline"
                )
                if report.get("warnings"):
                    for warning in report["warnings"]:
                        print(f"  Warning: {warning}")

    except KeyboardInterrupt:
        print("\nSimulation interrupted by user")
        raise typer.Exit(code=1)
    except Exception as e:
        print(f"Error: {e}")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Info commands
# ---------------------------------------------------------------------------


def list_profiles_command() -> int:
    """List available configuration profiles."""
    profiles = get_available_profiles()
    print("Available Configuration Profiles:")
    print("=" * 50)
    for name, description in profiles.items():
        print(f"  {name:20} - {description}")
    return 0


def list_adapters_command() -> int:
    """List available pipeline adapters."""
    adapters = get_available_adapters()
    print("Available Pipeline Adapters:")
    print("=" * 50)
    for name, description in adapters.items():
        print(f"  {name:15} - {description}")
    return 0


def list_generators_command() -> int:
    """List available read generation backends."""
    backends = detect_available_backends()
    print("Available Read Generation Backends:")
    print("=" * 50)
    for name, available in backends.items():
        status = "available" if available else "not found"
        print(f"  {name:15} - {status}")
    return 0


def list_mocks_command() -> int:
    """List available mock communities."""
    print("Available Mock Communities:")
    print("=" * 60)
    for name, mock in sorted(BUILTIN_MOCKS.items()):
        print(f"  {name:20} - {mock.description}")

    if MOCK_ALIASES:
        print("\nAliases:")
        print("-" * 60)
        targets: Dict[str, List[str]] = {}
        for alias, target in MOCK_ALIASES.items():
            if target not in targets:
                targets[target] = []
            targets[target].append(alias)
        for target, aliases in sorted(targets.items()):
            alias_str = ", ".join(sorted(aliases))
            print(f"  {alias_str:30} -> {target}")

    return 0


@app.command("list-profiles")
def list_profiles_cmd() -> None:
    """List all available configuration profiles."""
    list_profiles_command()


@app.command("list-adapters")
def list_adapters_cmd() -> None:
    """List all available pipeline adapters."""
    list_adapters_command()


@app.command("list-generators")
def list_generators_cmd() -> None:
    """List available read generation backends."""
    list_generators_command()


@app.command("list-mocks")
def list_mocks_cmd() -> None:
    """List available mock communities."""
    list_mocks_command()


# ---------------------------------------------------------------------------
# Utility commands
# ---------------------------------------------------------------------------


_GENOME_EXTENSIONS = {".fa", ".fasta", ".fna", ".fa.gz", ".fasta.gz", ".fna.gz"}


def _find_genome_files(directory: Path) -> list:
    """Return genome FASTA files found directly inside *directory*."""
    return [
        f
        for f in directory.iterdir()
        if f.is_file()
        and any(f.name.lower().endswith(ext) for ext in _GENOME_EXTENSIONS)
    ]


def _expand_genome_paths(paths: List[Path]) -> List[Path]:
    """Expand a list of genome paths, resolving directories to contained files.

    Each element may be a file (kept as-is) or a directory (scanned for
    genome files matching ``_GENOME_EXTENSIONS``).  Raises ``typer.Exit``
    on missing paths, non-genome files, or empty directories.
    """
    expanded: List[Path] = []
    for p in paths:
        if not p.exists():
            typer.echo(f"Error: Path does not exist: {p}", err=True)
            raise typer.Exit(code=2)
        if p.is_dir():
            found = sorted(_find_genome_files(p))
            if not found:
                exts = ", ".join(sorted(_GENOME_EXTENSIONS))
                typer.echo(
                    f"Error: No genome files found in directory: {p}\n"
                    f"  Supported extensions: {exts}",
                    err=True,
                )
                raise typer.Exit(code=2)
            typer.echo(
                f"Expanded directory {p.name}/ -> {len(found)} genome file(s)"
            )
            expanded.extend(found)
        else:
            expanded.append(p)
    return expanded


def _show_profile_overview() -> int:
    """Show all profiles grouped by mode when no source directory is given."""
    profiles = get_available_profiles()

    replay_names = [
        n for n in BUILTIN_PROFILES if not n.startswith("generate_")
    ]
    generate_names = [
        n for n in BUILTIN_PROFILES if n.startswith("generate_")
    ]

    print("Available Configuration Profiles")
    print("=" * 55)

    print("\nReplay profiles (for existing FASTQ/POD5 files):")
    for name in replay_names:
        desc = profiles.get(name, "")
        print(f"  {name:20} - {desc}")

    print("\nGenerate profiles (for genome FASTA files):")
    for name in generate_names:
        desc = profiles.get(name, "")
        print(f"  {name:20} - {desc}")

    print("\nUse --source <dir> to get recommendations for a specific directory.")
    return 0


def _show_replay_recommendations(
    source_dir: Path, file_count: int
) -> None:
    """Print replay-mode profile recommendations."""
    try:
        structure = FileStructureDetector.detect_structure(source_dir)
    except ValueError as e:
        print(f"\n  Error detecting structure: {e}")
        return
    print(f"  Detected structure: {structure}")

    recommendations = get_profile_recommendations(file_count, "general")
    profiles = get_available_profiles()
    print(f"\nRecommended replay profiles for {file_count} files:")
    for i, name in enumerate(recommendations, 1):
        desc = profiles.get(name, "Unknown profile")
        print(f"  {i}. {name} - {desc}")


def _show_generate_recommendations(
    genome_files: list,
) -> None:
    """Print generate-mode profile recommendations."""
    total_size = sum(f.stat().st_size for f in genome_files)
    total_size_mb = total_size / (1024 * 1024)

    print(f"  Found {len(genome_files)} genome FASTA file(s):")
    for gf in genome_files[:5]:
        print(f"    {gf.name}")
    if len(genome_files) > 5:
        print(f"    ... and {len(genome_files) - 5} more")

    recommendations = get_generate_recommendations(
        len(genome_files), total_size_mb
    )
    profiles = get_available_profiles()
    print(f"\nRecommended generate profiles for {len(genome_files)} genome(s):")
    for i, name in enumerate(recommendations, 1):
        desc = profiles.get(name, "Unknown profile")
        print(f"  {i}. {name} - {desc}")


def recommend_profiles_command(source_dir: Optional[Path] = None) -> int:
    """Recommend profiles based on source directory contents.

    When *source_dir* is ``None``, displays a categorised overview of all
    available profiles.  Otherwise analyses the directory for sequencing
    and/or genome files and recommends appropriate profiles.
    """
    if source_dir is None:
        return _show_profile_overview()

    if not source_dir.exists():
        print(f"Error: Source directory does not exist: {source_dir}")
        return 1

    if not source_dir.is_dir():
        print(f"Error: Not a directory: {source_dir}")
        return 1

    seq_files = FileStructureDetector._find_sequencing_files(source_dir)
    genome_files = _find_genome_files(source_dir)

    # Also check barcode subdirectories for sequencing files
    if not seq_files:
        for subdir in source_dir.iterdir():
            if subdir.is_dir():
                seq_files.extend(
                    FileStructureDetector._find_sequencing_files(subdir)
                )

    has_seq = len(seq_files) > 0
    has_genomes = len(genome_files) > 0

    if not has_seq and not has_genomes:
        print(f"Analysis of {source_dir}:")
        print("  No sequencing or genome files found.")
        seq_exts = sorted(FileStructureDetector.SUPPORTED_EXTENSIONS)
        gen_exts = sorted(_GENOME_EXTENSIONS)
        print(f"  Supported sequencing extensions: {', '.join(seq_exts)}")
        print(f"  Supported genome extensions: {', '.join(gen_exts)}")
        return 1

    print(f"Analysis of {source_dir}:")

    if has_seq:
        print(f"  Found {len(seq_files)} sequencing file(s)")
        _show_replay_recommendations(source_dir, len(seq_files))

    if has_seq and has_genomes:
        print()

    if has_genomes:
        _show_generate_recommendations(genome_files)

    return 0


def validate_pipeline_command(target_dir: Path, pipeline: str) -> int:
    """Validate directory structure for a pipeline."""
    if not target_dir.exists():
        print(f"Error: Target directory does not exist: {target_dir}")
        return 1

    report = validate_for_pipeline(pipeline, target_dir)

    print(f"Pipeline validation report for '{pipeline}':")
    print("=" * 50)
    print(f"Valid: {'yes' if report.get('valid', False) else 'no'}")

    if "files_found" in report and report["files_found"]:
        print(f"Files found: {len(report['files_found'])}")
        for file_path in report["files_found"][:5]:
            print(f"  - {file_path}")
        if len(report["files_found"]) > 5:
            print(f"  ... and {len(report['files_found']) - 5} more")

    if report.get("warnings"):
        print("Warnings:")
        for warning in report["warnings"]:
            print(f"  Warning: {warning}")

    if report.get("errors"):
        print("Errors:")
        for error in report["errors"]:
            print(f"  Error: {error}")

    return 0 if report.get("valid", False) else 1


@app.command("recommend")
def recommend_cmd(
    source: Optional[Path] = typer.Option(
        None, "--source", "-s",
        help="Source directory to analyse (omit for an overview of all profiles).",
        exists=True, file_okay=False, resolve_path=True,
    ),
) -> None:
    """Recommend configuration profiles for a source directory."""
    code = recommend_profiles_command(source)
    if code != 0:
        raise typer.Exit(code=code)


@app.command("validate")
def validate_cmd(
    pipeline: str = typer.Option(
        ..., "--pipeline", "-p",
        help="Pipeline name to validate against.",
    ),
    target: Path = typer.Option(
        ..., "--target", "-t",
        help="Target directory to validate.",
        exists=True, file_okay=False, resolve_path=True,
    ),
) -> None:
    """Validate directory structure for a pipeline."""
    code = validate_pipeline_command(target, pipeline)
    if code != 0:
        raise typer.Exit(code=code)


# ---------------------------------------------------------------------------
# Core commands
# ---------------------------------------------------------------------------


@app.command()
def replay(
    # Required
    source: Path = typer.Option(
        ..., "--source", "-s",
        help="Source directory containing FASTQ/POD5 files.",
        exists=True, file_okay=False, resolve_path=True,
        rich_help_panel="Required",
    ),
    target: Path = typer.Option(
        ..., "--target", "-t",
        help="Target directory for pipeline to watch.",
        rich_help_panel="Required",
    ),
    # Simulation Configuration
    profile: Optional[str] = typer.Option(
        None, help="Use a predefined configuration profile.",
        rich_help_panel="Simulation Configuration",
    ),
    interval: float = typer.Option(
        5.0, help="Seconds between file operations.",
        rich_help_panel="Simulation Configuration",
    ),
    operation: OperationChoice = typer.Option(
        OperationChoice.copy,
        help="File operation: copy files or create symlinks.",
        rich_help_panel="Simulation Configuration",
    ),
    force_structure: Optional[ForceStructure] = typer.Option(
        None, help="Force specific structure instead of auto-detection.",
        rich_help_panel="Simulation Configuration",
    ),
    batch_size: int = typer.Option(
        1, help="Number of files to process per interval.",
        rich_help_panel="Simulation Configuration",
    ),
    reads_per_file: Optional[int] = typer.Option(
        None,
        help=(
            "Rechunk FASTQ files into output files of N reads each. "
            "Large files are split; small files within the same barcode "
            "group are merged. POD5 files pass through unchanged. "
            "Incompatible with --operation link."
        ),
        rich_help_panel="Simulation Configuration",
    ),
    # Timing Models
    timing_model: Optional[TimingModelChoice] = typer.Option(
        None, help="Timing model (overrides profile setting).",
        rich_help_panel="Timing Models",
    ),
    burst_probability: Optional[float] = typer.Option(
        None, help="Burst probability for Poisson model (0.0-1.0).",
        rich_help_panel="Timing Models",
    ),
    burst_rate_multiplier: Optional[float] = typer.Option(
        None, help="Burst rate multiplier for Poisson model.",
        rich_help_panel="Timing Models",
    ),
    random_factor: Optional[float] = typer.Option(
        None, help="Randomness factor for random timing model (0.0-1.0).",
        rich_help_panel="Timing Models",
    ),
    adaptation_rate: Optional[float] = typer.Option(
        None, help="Adaptation rate for adaptive timing model (0.0-1.0).",
        rich_help_panel="Timing Models",
    ),
    history_size: Optional[int] = typer.Option(
        None, help="History size for adaptive timing model.",
        rich_help_panel="Timing Models",
    ),
    # Parallel Processing
    parallel: bool = typer.Option(
        False, help="Enable parallel processing within batches.",
        rich_help_panel="Parallel Processing",
    ),
    worker_count: int = typer.Option(
        4, help="Number of worker threads for parallel processing.",
        rich_help_panel="Parallel Processing",
    ),
    # Monitoring
    monitor: MonitorLevel = typer.Option(
        MonitorLevel.default,
        help=(
            "Progress monitoring level: default (basic), detailed (verbose "
            "logging), enhanced (resource monitoring + interactive controls), "
            "none (silent). Enhanced features require: pip install nanorunner[enhanced]"
        ),
        rich_help_panel="Monitoring",
    ),
    quiet: bool = typer.Option(
        False, help="Suppress progress output.",
        rich_help_panel="Monitoring",
    ),
    pipeline: Optional[str] = typer.Option(
        None, help="Validate output for specific pipeline compatibility.",
        rich_help_panel="Monitoring",
    ),
) -> None:
    """Replay existing FASTQ/POD5 files with configurable timing."""
    _validate_timing_params(
        burst_probability, burst_rate_multiplier, random_factor,
        adaptation_rate, history_size,
    )

    if reads_per_file is not None and operation == OperationChoice.link:
        typer.echo(
            "Error: --reads-per-file is incompatible with --operation link",
            err=True,
        )
        raise typer.Exit(code=2)

    config = _build_config(
        target_dir=target,
        source_dir=source,
        is_generate=False,
        profile=profile,
        interval=interval,
        operation=operation,
        force_structure=force_structure,
        batch_size=batch_size,
        reads_per_output_file=reads_per_file,
        timing_model=timing_model,
        burst_probability=burst_probability,
        burst_rate_multiplier=burst_rate_multiplier,
        random_factor=random_factor,
        adaptation_rate=adaptation_rate,
        history_size=history_size,
        parallel=parallel,
        worker_count=worker_count,
    )

    enable_monitoring, monitor_type = _setup_monitoring(monitor, quiet)
    _run_simulation(config, enable_monitoring, monitor_type,
                    is_generate=False, pipeline=pipeline)


@app.command()
def generate(
    # Required
    target: Path = typer.Option(
        ..., "--target", "-t",
        help="Target directory for generated reads.",
        rich_help_panel="Required",
    ),
    # Genome Source (one required -- validated in body)
    genomes: Optional[List[Path]] = typer.Option(
        None, help="Input genome FASTA files.",
        rich_help_panel="Genome Source",
    ),
    species: Optional[List[str]] = typer.Option(
        None, help="Species names to resolve via GTDB/NCBI.",
        rich_help_panel="Genome Source",
    ),
    mock: Optional[str] = typer.Option(
        None, help="Preset mock community name (e.g. zymo_d6300).",
        rich_help_panel="Genome Source",
    ),
    taxid: Optional[List[int]] = typer.Option(
        None, help="Direct NCBI taxonomy IDs.",
        rich_help_panel="Genome Source",
    ),
    # Read Generation
    generator_backend: GeneratorBackend = typer.Option(
        GeneratorBackend.auto, help="Read generation backend.",
        rich_help_panel="Read Generation",
    ),
    read_count: int = typer.Option(
        1000, help="Total number of reads to generate across all genomes.",
        rich_help_panel="Read Generation",
    ),
    mean_read_length: int = typer.Option(
        5000, help="Mean read length in bases.",
        rich_help_panel="Read Generation",
    ),
    mean_quality: float = typer.Option(
        20.0, help="Mean Phred quality score (typical for R10.4.1 + SUP: 20.0).",
        rich_help_panel="Read Generation",
    ),
    std_quality: float = typer.Option(
        4.0, help="Standard deviation of quality scores.",
        rich_help_panel="Read Generation",
    ),
    reads_per_file: int = typer.Option(
        100, help="Number of reads per output file.",
        rich_help_panel="Read Generation",
    ),
    output_format: OutputFormat = typer.Option(
        OutputFormat.fastq_gz, help="Output file format.",
        rich_help_panel="Read Generation",
    ),
    mix_reads: bool = typer.Option(
        False, help="Mix reads from all genomes into shared files.",
        rich_help_panel="Read Generation",
    ),
    # Species/Mock Options
    sample_type: Optional[SampleType] = typer.Option(
        None, help="Sample type: pure (per-species barcodes) or mixed.",
        rich_help_panel="Species/Mock Options",
    ),
    abundances: Optional[List[float]] = typer.Option(
        None, help="Custom abundances for mixed samples (must sum to 1.0).",
        rich_help_panel="Species/Mock Options",
    ),
    offline: bool = typer.Option(
        False, help="Use only cached genomes, no network requests.",
        rich_help_panel="Species/Mock Options",
    ),
    # Simulation Configuration
    profile: Optional[str] = typer.Option(
        None, help="Use a predefined configuration profile.",
        rich_help_panel="Simulation Configuration",
    ),
    interval: float = typer.Option(
        5.0, help="Seconds between file operations.",
        rich_help_panel="Simulation Configuration",
    ),
    force_structure: Optional[ForceStructure] = typer.Option(
        None, help="Force specific structure instead of auto-detection.",
        rich_help_panel="Simulation Configuration",
    ),
    batch_size: int = typer.Option(
        1, help="Number of files to process per interval.",
        rich_help_panel="Simulation Configuration",
    ),
    # Timing Models
    timing_model: Optional[TimingModelChoice] = typer.Option(
        None, help="Timing model (overrides profile setting).",
        rich_help_panel="Timing Models",
    ),
    burst_probability: Optional[float] = typer.Option(
        None, help="Burst probability for Poisson model (0.0-1.0).",
        rich_help_panel="Timing Models",
    ),
    burst_rate_multiplier: Optional[float] = typer.Option(
        None, help="Burst rate multiplier for Poisson model.",
        rich_help_panel="Timing Models",
    ),
    random_factor: Optional[float] = typer.Option(
        None, help="Randomness factor for random timing model (0.0-1.0).",
        rich_help_panel="Timing Models",
    ),
    adaptation_rate: Optional[float] = typer.Option(
        None, help="Adaptation rate for adaptive timing model (0.0-1.0).",
        rich_help_panel="Timing Models",
    ),
    history_size: Optional[int] = typer.Option(
        None, help="History size for adaptive timing model.",
        rich_help_panel="Timing Models",
    ),
    # Parallel Processing
    parallel: bool = typer.Option(
        False, help="Enable parallel processing within batches.",
        rich_help_panel="Parallel Processing",
    ),
    worker_count: int = typer.Option(
        4, help="Number of worker threads for parallel processing.",
        rich_help_panel="Parallel Processing",
    ),
    # Monitoring
    monitor: MonitorLevel = typer.Option(
        MonitorLevel.default,
        help=(
            "Progress monitoring level: default (basic), detailed (verbose "
            "logging), enhanced (resource monitoring + interactive controls), "
            "none (silent). Enhanced features require: pip install nanorunner[enhanced]"
        ),
        rich_help_panel="Monitoring",
    ),
    quiet: bool = typer.Option(
        False, help="Suppress progress output.",
        rich_help_panel="Monitoring",
    ),
    pipeline: Optional[str] = typer.Option(
        None, help="Validate output for specific pipeline compatibility.",
        rich_help_panel="Monitoring",
    ),
) -> None:
    """Generate simulated nanopore reads from genome FASTA files."""
    # Mutual exclusivity validation
    sources = sum([
        genomes is not None,
        species is not None,
        mock is not None,
        taxid is not None,
    ])
    if sources == 0:
        typer.echo(
            "Error: specify one of --genomes, --species, --mock, or --taxid",
            err=True,
        )
        raise typer.Exit(code=1)
    if sources > 1:
        typer.echo(
            "Error: --genomes, --species, --mock, and --taxid are mutually exclusive",
            err=True,
        )
        raise typer.Exit(code=1)

    # Validate and expand genome paths (directories -> contained files)
    if genomes:
        genomes = _expand_genome_paths(genomes)

    _validate_timing_params(
        burst_probability, burst_rate_multiplier, random_factor,
        adaptation_rate, history_size,
    )

    config = _build_config(
        target_dir=target,
        is_generate=True,
        profile=profile,
        interval=interval,
        force_structure=force_structure,
        batch_size=batch_size,
        timing_model=timing_model,
        burst_probability=burst_probability,
        burst_rate_multiplier=burst_rate_multiplier,
        random_factor=random_factor,
        adaptation_rate=adaptation_rate,
        history_size=history_size,
        parallel=parallel,
        worker_count=worker_count,
        genomes=genomes,
        generator_backend=generator_backend,
        read_count=read_count,
        mean_read_length=mean_read_length,
        mean_quality=mean_quality,
        std_quality=std_quality,
        reads_per_file=reads_per_file,
        output_format=output_format,
        mix_reads=mix_reads,
        species=species,
        mock=mock,
        taxid=taxid,
        sample_type=sample_type,
        abundances=abundances,
        offline=offline,
    )

    enable_monitoring, monitor_type = _setup_monitoring(monitor, quiet)
    _run_simulation(config, enable_monitoring, monitor_type,
                    is_generate=True, pipeline=pipeline)


# ---------------------------------------------------------------------------
# Download command
# ---------------------------------------------------------------------------


def _download_genomes(
    species: Optional[List[str]],
    mock_name: Optional[str],
    taxid: Optional[List[int]],
) -> tuple:
    """Resolve and download genomes. Returns (successful_downloads, mock_community)."""
    resolver = SpeciesResolver()
    genomes_to_download: List[tuple] = []
    mock_community = None

    if mock_name:
        mock_community = get_mock_community(mock_name)
        if mock_community is None:
            print(f"Error: Unknown mock community: {mock_name}")
            raise typer.Exit(code=1)
        for org in mock_community.organisms:
            ref: Optional[GenomeRef] = None
            if org.accession:
                domain = (
                    org.domain
                    if org.domain
                    else ("eukaryota" if org.resolver == "ncbi" else "bacteria")
                )
                ref = GenomeRef(
                    name=org.name,
                    accession=org.accession,
                    source=org.resolver,
                    domain=domain,
                )
            else:
                ref = resolver.resolve(org.name)
            if ref:
                genomes_to_download.append((org.name, ref))
            else:
                print(f"Warning: Could not resolve: {org.name}")

    if species:
        for sp in species:
            ref = resolver.resolve(sp)
            if ref:
                genomes_to_download.append((sp, ref))
            else:
                print(f"Warning: Could not resolve: {sp}")

    if taxid:
        for tid in taxid:
            ref = resolver.resolve_taxid(tid)
            if ref:
                genomes_to_download.append((f"taxid:{tid}", ref))
            else:
                print(f"Warning: Could not resolve taxid: {tid}")

    if not genomes_to_download:
        print("No genomes to download")
        raise typer.Exit(code=1)

    print(f"Downloading {len(genomes_to_download)} genome(s)...")
    successful: List[tuple] = []
    for name, ref in genomes_to_download:
        try:
            path = download_genome(ref, resolver.cache)
            print(f"  Downloaded: {name} -> {path}")
            successful.append((name, ref, path))
        except Exception as e:
            print(f"  Failed: {name} - {e}")

    print("Download complete")
    return successful, mock_community


@app.command()
def download(
    # Genome Source (one required)
    species: Optional[List[str]] = typer.Option(
        None, help="Species names to download.",
        rich_help_panel="Genome Source",
    ),
    mock: Optional[str] = typer.Option(
        None, help="Mock community to download genomes for.",
        rich_help_panel="Genome Source",
    ),
    taxid: Optional[List[int]] = typer.Option(
        None, help="NCBI taxonomy IDs to download.",
        rich_help_panel="Genome Source",
    ),
    # Optional target for generation
    target: Optional[Path] = typer.Option(
        None, "--target", "-t",
        help="Target directory for read generation (omit for download only).",
    ),
    # Generation options (when target provided)
    read_count: int = typer.Option(
        1000, help="Total number of reads to generate.",
        rich_help_panel="Generation Options",
    ),
    reads_per_file: int = typer.Option(
        100, help="Number of reads per output file.",
        rich_help_panel="Generation Options",
    ),
    mean_read_length: int = typer.Option(
        5000, help="Mean read length in bases.",
        rich_help_panel="Generation Options",
    ),
    mean_quality: float = typer.Option(
        20.0, help="Mean Phred quality score.",
        rich_help_panel="Generation Options",
    ),
    std_quality: float = typer.Option(
        4.0, help="Standard deviation of quality scores.",
        rich_help_panel="Generation Options",
    ),
    output_format: OutputFormat = typer.Option(
        OutputFormat.fastq_gz, help="Output file format.",
        rich_help_panel="Generation Options",
    ),
    generator_backend: GeneratorBackend = typer.Option(
        GeneratorBackend.auto, help="Read generation backend.",
        rich_help_panel="Generation Options",
    ),
    interval: float = typer.Option(
        5.0, help="Seconds between file operations.",
        rich_help_panel="Generation Options",
    ),
    batch_size: int = typer.Option(
        1, help="Number of files to process per interval.",
        rich_help_panel="Generation Options",
    ),
    sample_type: Optional[SampleType] = typer.Option(
        None, help="Sample type: pure (per-species barcodes) or mixed.",
        rich_help_panel="Generation Options",
    ),
    mix_reads: bool = typer.Option(
        False, help="Mix reads from all genomes into shared files.",
        rich_help_panel="Generation Options",
    ),
) -> None:
    """Download genomes for offline use, optionally generating reads."""
    if not (species or mock or taxid):
        print("Error: Must specify --species, --mock, or --taxid")
        raise typer.Exit(code=1)

    successful_downloads, mock_community = _download_genomes(species, mock, taxid)

    if target is not None:
        if not successful_downloads:
            print("Error: No genomes downloaded successfully, cannot generate reads")
            raise typer.Exit(code=1)

        genome_paths = [path for _, _, path in successful_downloads]

        st = sample_type.value if sample_type else None
        if st is None:
            st = "mixed" if len(genome_paths) > 1 else "pure"

        abundances_list = None
        if mock_community is not None:
            downloaded_names = {name for name, _, _ in successful_downloads}
            abundances_list = []
            for org in mock_community.organisms:
                if org.name in downloaded_names:
                    abundances_list.append(org.abundance)
            total = sum(abundances_list)
            if total > 0 and abs(total - 1.0) > 0.001:
                abundances_list = [a / total for a in abundances_list]

        try:
            config = SimulationConfig(
                target_dir=target,
                operation="generate",
                genome_inputs=genome_paths,
                generator_backend=generator_backend.value,
                read_count=read_count,
                mean_read_length=mean_read_length,
                mean_quality=mean_quality,
                std_quality=std_quality,
                reads_per_file=reads_per_file,
                output_format=output_format.value,
                mix_reads=mix_reads,
                interval=interval,
                batch_size=batch_size,
                sample_type=st,
                abundances=abundances_list,
            )

            print(f"\nGenerating reads into {target}...")
            simulator = NanoporeSimulator(config, enable_monitoring=True)
            simulator.run_simulation()
            print("Read generation complete")
        except Exception as e:
            print(f"Error during read generation: {e}")
            raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Backward-compatible entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """Entry point for console_scripts and bin/nanopore-simulator."""
    try:
        app()
        return 0
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 0


if __name__ == "__main__":
    sys.exit(main())
