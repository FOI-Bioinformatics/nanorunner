"""Thin CLI dispatcher for nanorunner.

Each subcommand is a short function: parse parameters, build a config
dataclass, and call the appropriate runner or utility function.
Validation lives in the config dataclasses, not here.
"""

import logging
import sys
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

import typer

from nanopore_simulator import __version__
from nanopore_simulator.config import GenerateConfig, ReplayConfig
from nanopore_simulator.runner import run_generate, run_replay


# -------------------------------------------------------------------
# Enums
# -------------------------------------------------------------------


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
    enhanced = "enhanced"
    none = "none"


class LogLevel(str, Enum):
    debug = "DEBUG"
    info = "INFO"
    warning = "WARNING"
    error = "ERROR"


class OutputFormat(str, Enum):
    fastq = "fastq"
    fastq_gz = "fastq.gz"


class GeneratorBackend(str, Enum):
    auto = "auto"
    builtin = "builtin"
    badread = "badread"
    nanosim = "nanosim"


class ForceStructure(str, Enum):
    singleplex = "singleplex"
    multiplex = "multiplex"


# -------------------------------------------------------------------
# Typer app
# -------------------------------------------------------------------

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
    log_level: LogLevel = typer.Option(
        LogLevel.warning,
        "--log-level",
        help="Set logging verbosity.",
    ),
) -> None:
    """Nanopore sequencing run simulator for testing bioinformatics pipelines."""
    logging.basicConfig(
        level=getattr(logging, log_level.value),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

_GENOME_EXTENSIONS = {".fa", ".fasta", ".fna", ".fa.gz", ".fasta.gz", ".fna.gz"}


def _build_timing_params(
    burst_probability: Optional[float],
    burst_rate_multiplier: Optional[float],
    random_factor: Optional[float],
    adaptation_rate: Optional[float],
    history_size: Optional[int],
) -> Dict[str, float]:
    """Collect non-None timing sub-parameters into a dict."""
    params: Dict[str, float] = {}
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
    """Validate timing parameter ranges early."""
    if random_factor is not None and not (0.0 <= random_factor <= 1.0):
        typer.echo("Error: Random factor must be between 0.0 and 1.0", err=True)
        raise typer.Exit(code=2)
    if burst_probability is not None and not (0.0 <= burst_probability <= 1.0):
        typer.echo("Error: Burst probability must be between 0.0 and 1.0", err=True)
        raise typer.Exit(code=2)
    if burst_rate_multiplier is not None and burst_rate_multiplier <= 0:
        typer.echo("Error: Burst rate multiplier must be positive", err=True)
        raise typer.Exit(code=2)
    if adaptation_rate is not None and not (0.0 <= adaptation_rate <= 1.0):
        typer.echo("Error: Adaptation rate must be between 0.0 and 1.0", err=True)
        raise typer.Exit(code=2)
    if history_size is not None and history_size < 1:
        typer.echo("Error: History size must be at least 1", err=True)
        raise typer.Exit(code=2)


def _resolve_monitor(monitor: MonitorLevel, quiet: bool) -> str:
    """Map MonitorLevel enum + quiet flag to a config monitor_type string."""
    if quiet or monitor == MonitorLevel.none:
        return "none"
    if monitor == MonitorLevel.enhanced:
        try:
            import psutil  # noqa: F401
        except ImportError:
            from nanopore_simulator.deps import get_install_hint

            typer.echo(
                "Warning: Enhanced monitoring requires psutil. "
                f"Install with: {get_install_hint('psutil')}",
                err=True,
            )
            typer.echo("Falling back to basic monitoring mode.", err=True)
            return "basic"
        return "enhanced"
    # "default" maps to "basic"
    return "basic"


def _find_genome_files(directory: Path) -> List[Path]:
    """Return genome FASTA files found directly inside *directory*."""
    return [
        f
        for f in directory.iterdir()
        if f.is_file()
        and any(f.name.lower().endswith(ext) for ext in _GENOME_EXTENSIONS)
    ]


def _expand_genome_paths(paths: List[Path]) -> List[Path]:
    """Expand genome paths, resolving directories to contained files."""
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
            typer.echo(f"Expanded directory {p.name}/ -> {len(found)} genome file(s)")
            expanded.extend(found)
        else:
            expanded.append(p)
    return expanded


def _resolve_and_download_genomes(
    mock_name: Optional[str],
    species_inputs: Optional[List[str]],
    taxid_inputs: Optional[List[str]],
    offline: bool = False,
) -> tuple:
    """Resolve mock/species/taxid inputs to downloaded genome paths.

    Downloads genomes as needed via NCBI datasets CLI and returns
    a list of local FASTA file paths ready for read generation,
    along with any abundance information from mock communities.

    Args:
        mock_name: Preset mock community name, or None.
        species_inputs: Species names to resolve, or None.
        taxid_inputs: NCBI taxonomy IDs as strings, or None.
        offline: If True, use only cached genomes.

    Returns:
        Tuple of (genome_paths, abundances) where abundances may be None.

    Raises:
        typer.Exit: If resolution or download fails completely.
    """
    from nanopore_simulator.species import (
        GenomeCache,
        GenomeRef,
        download_genome,
        resolve_species,
        resolve_taxid,
    )
    from nanopore_simulator.mocks import get_mock

    cache = GenomeCache()
    # Each entry is (name, ref, abundance_or_none).  The abundance
    # value is only set for mock-community organisms; species and
    # taxid inputs get None so that index alignment is maintained
    # even when different input types are combined.
    genome_downloads: List[tuple] = []

    if mock_name:
        mock_community = get_mock(mock_name)
        if mock_community is None:
            typer.echo(f"Error: Unknown mock community: {mock_name}", err=True)
            raise typer.Exit(code=1)
        for org in mock_community.organisms:
            ref: Optional[GenomeRef] = None
            if org.accession:
                domain = org.domain or (
                    "eukaryota" if org.resolver == "ncbi" else "bacteria"
                )
                ref = GenomeRef(
                    name=org.name,
                    accession=org.accession,
                    source=org.resolver,
                    domain=domain,
                )
            else:
                ref = resolve_species(org.name)
            if ref:
                genome_downloads.append((org.name, ref, org.abundance))
            else:
                typer.echo(f"Warning: Could not resolve: {org.name}", err=True)

    if species_inputs:
        for sp in species_inputs:
            sp_ref: Optional[GenomeRef] = resolve_species(sp)
            if sp_ref:
                genome_downloads.append((sp, sp_ref, None))
            else:
                typer.echo(f"Warning: Could not resolve: {sp}", err=True)

    if taxid_inputs:
        for tid in taxid_inputs:
            tid_ref: Optional[GenomeRef] = resolve_taxid(int(tid))
            if tid_ref:
                genome_downloads.append((f"taxid:{tid}", tid_ref, None))
            else:
                typer.echo(f"Warning: Could not resolve taxid: {tid}", err=True)

    if not genome_downloads:
        typer.echo("Error: No genomes could be resolved", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Downloading {len(genome_downloads)} genome(s)...")
    successful_paths: List[Path] = []
    successful_abundances: List[float] = []
    has_abundance_info = any(ab is not None for _, _, ab in genome_downloads)

    for name, ref, abundance in genome_downloads:
        try:
            path = download_genome(ref, cache=cache)
            typer.echo(f"  Ready: {name} -> {path}")
            successful_paths.append(Path(path))
            if abundance is not None:
                successful_abundances.append(abundance)
        except Exception as exc:
            typer.echo(f"  Failed: {name} - {exc}", err=True)

    if not successful_paths:
        typer.echo("Error: No genomes downloaded successfully", err=True)
        raise typer.Exit(code=1)

    # Renormalize abundances if some genomes failed
    final_abundances = None
    if has_abundance_info and successful_abundances:
        total = sum(successful_abundances)
        if total > 0:
            final_abundances = [a / total for a in successful_abundances]

    return successful_paths, final_abundances


# -------------------------------------------------------------------
# Core commands
# -------------------------------------------------------------------


@app.command()
def replay(
    # Required
    source: Path = typer.Option(
        ...,
        "--source",
        "-s",
        help="Source directory containing FASTQ/POD5 files.",
        exists=True,
        file_okay=False,
        resolve_path=True,
        rich_help_panel="Required",
    ),
    target: Path = typer.Option(
        ...,
        "--target",
        "-t",
        help="Target directory for pipeline to watch.",
        rich_help_panel="Required",
    ),
    # Simulation Configuration
    profile: Optional[str] = typer.Option(
        None,
        help="Use a predefined configuration profile.",
        rich_help_panel="Simulation Configuration",
    ),
    interval: float = typer.Option(
        5.0,
        help="Seconds between file operations.",
        rich_help_panel="Simulation Configuration",
    ),
    operation: OperationChoice = typer.Option(
        OperationChoice.copy,
        help="File operation: copy files or create symlinks.",
        rich_help_panel="Simulation Configuration",
    ),
    force_structure: Optional[ForceStructure] = typer.Option(
        None,
        help="Force specific structure instead of auto-detection.",
        rich_help_panel="Simulation Configuration",
    ),
    batch_size: int = typer.Option(
        1,
        help="Number of files to process per interval.",
        rich_help_panel="Simulation Configuration",
    ),
    no_wait: bool = typer.Option(
        False,
        help="Skip timing delays between batches.",
        rich_help_panel="Simulation Configuration",
    ),
    reads_per_file: Optional[int] = typer.Option(
        None,
        help=(
            "Rechunk FASTQ files into output files of N reads each. "
            "Incompatible with --operation link."
        ),
        rich_help_panel="Simulation Configuration",
    ),
    # Timing Models
    timing_model: Optional[TimingModelChoice] = typer.Option(
        None,
        help="Timing model (overrides profile setting).",
        rich_help_panel="Timing Models",
    ),
    burst_probability: Optional[float] = typer.Option(
        None,
        help="Burst probability for Poisson model (0.0-1.0).",
        rich_help_panel="Timing Models",
    ),
    burst_rate_multiplier: Optional[float] = typer.Option(
        None,
        help="Burst rate multiplier for Poisson model.",
        rich_help_panel="Timing Models",
    ),
    random_factor: Optional[float] = typer.Option(
        None,
        help="Randomness factor for random timing model (0.0-1.0).",
        rich_help_panel="Timing Models",
    ),
    adaptation_rate: Optional[float] = typer.Option(
        None,
        help="Adaptation rate for adaptive timing model (0.0-1.0).",
        rich_help_panel="Timing Models",
    ),
    history_size: Optional[int] = typer.Option(
        None,
        help="History size for adaptive timing model.",
        rich_help_panel="Timing Models",
    ),
    # Parallel Processing
    parallel: bool = typer.Option(
        False,
        help="Enable parallel processing within batches.",
        rich_help_panel="Parallel Processing",
    ),
    worker_count: int = typer.Option(
        4,
        help="Number of worker threads for parallel processing.",
        rich_help_panel="Parallel Processing",
    ),
    # Monitoring
    monitor: MonitorLevel = typer.Option(
        MonitorLevel.default,
        help=(
            "Progress monitoring level: default (basic), "
            "enhanced (resource monitoring + interactive controls), "
            "none (silent)."
        ),
        rich_help_panel="Monitoring",
    ),
    quiet: bool = typer.Option(
        False,
        help="Suppress progress output.",
        rich_help_panel="Monitoring",
    ),
    pipeline: Optional[str] = typer.Option(
        None,
        help="Validate output for specific pipeline compatibility.",
        rich_help_panel="Monitoring",
    ),
) -> None:
    """Replay existing FASTQ/POD5 files with configurable timing."""
    if no_wait:
        interval = 0.0

    _validate_timing_params(
        burst_probability,
        burst_rate_multiplier,
        random_factor,
        adaptation_rate,
        history_size,
    )

    if reads_per_file is not None and operation == OperationChoice.link:
        typer.echo(
            "Error: --reads-per-file is incompatible with --operation link",
            err=True,
        )
        raise typer.Exit(code=2)

    # Build params -- start from profile if provided, then overlay CLI args.
    timing_params = _build_timing_params(
        burst_probability,
        burst_rate_multiplier,
        random_factor,
        adaptation_rate,
        history_size,
    )

    params: Dict = {}
    if profile:
        from nanopore_simulator.profiles import apply_profile

        try:
            params = apply_profile(profile)
        except ValueError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=2)

    # Map profile field names to config field names
    tm = timing_model.value if timing_model else params.get("timing_model", "uniform")
    tp = timing_params or params.get("timing_model_params", {})
    op = operation.value
    bs = batch_size if batch_size != 1 else params.get("batch_size", 1)
    par = parallel or params.get("parallel_processing", False)
    wk = worker_count if worker_count != 4 else params.get("worker_count", 4)
    struct = force_structure.value if force_structure else "auto"
    monitor_type = _resolve_monitor(monitor, quiet)

    try:
        config = ReplayConfig(
            source_dir=source,
            target_dir=target,
            operation=op,
            interval=interval,
            batch_size=bs,
            timing_model=tm,
            timing_params=tp,
            parallel=par,
            workers=wk,
            monitor_type=monitor_type,
            adapter=pipeline,
            reads_per_output=reads_per_file,
            structure=struct,
        )
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2)

    # Pre-flight validation
    from nanopore_simulator.deps import check_preflight

    errors = check_preflight(operation=config.operation)
    if errors:
        for err in errors:
            typer.echo(f"Error: {err}", err=True)
        raise typer.Exit(code=1)

    try:
        run_replay(config)
    except KeyboardInterrupt:
        typer.echo("\nSimulation interrupted by user", err=True)
        raise typer.Exit(code=1)
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)

    # Post-run pipeline validation
    if pipeline:
        _run_pipeline_validation(pipeline, target)


@app.command()
def generate(
    # Required
    target: Path = typer.Option(
        ...,
        "--target",
        "-t",
        help="Target directory for generated reads.",
        rich_help_panel="Required",
    ),
    # Genome Source
    genomes: Optional[List[Path]] = typer.Option(
        None,
        help="Input genome FASTA files.",
        rich_help_panel="Genome Source",
    ),
    species: Optional[List[str]] = typer.Option(
        None,
        help="Species names to resolve via GTDB/NCBI.",
        rich_help_panel="Genome Source",
    ),
    mock: Optional[str] = typer.Option(
        None,
        help="Preset mock community name (e.g. zymo_d6300).",
        rich_help_panel="Genome Source",
    ),
    taxid: Optional[List[int]] = typer.Option(
        None,
        help="Direct NCBI taxonomy IDs.",
        rich_help_panel="Genome Source",
    ),
    # Read Generation
    generator_backend: GeneratorBackend = typer.Option(
        GeneratorBackend.auto,
        help="Read generation backend.",
        rich_help_panel="Read Generation",
    ),
    read_count: Optional[int] = typer.Option(
        None,
        help="Total number of reads to generate across all genomes. [default: 1000]",
        rich_help_panel="Read Generation",
    ),
    mean_read_length: Optional[int] = typer.Option(
        None,
        help="Mean read length in bases. [default: 5000]",
        rich_help_panel="Read Generation",
    ),
    mean_quality: Optional[float] = typer.Option(
        None,
        help="Mean Phred quality score. [default: 20.0]",
        rich_help_panel="Read Generation",
    ),
    std_quality: Optional[float] = typer.Option(
        None,
        help="Standard deviation of quality scores. [default: 4.0]",
        rich_help_panel="Read Generation",
    ),
    reads_per_file: Optional[int] = typer.Option(
        None,
        help="Number of reads per output file. [default: 100]",
        rich_help_panel="Read Generation",
    ),
    output_format: OutputFormat = typer.Option(
        OutputFormat.fastq_gz,
        help="Output file format.",
        rich_help_panel="Read Generation",
    ),
    mix_reads: bool = typer.Option(
        False,
        help="Mix reads from all genomes into shared files.",
        rich_help_panel="Read Generation",
    ),
    # Species/Mock Options
    abundances: Optional[List[float]] = typer.Option(
        None,
        help="Custom abundances for mixed samples (must sum to 1.0).",
        rich_help_panel="Species/Mock Options",
    ),
    offline: bool = typer.Option(
        False,
        help="Use only cached genomes, no network requests.",
        rich_help_panel="Species/Mock Options",
    ),
    # Simulation Configuration
    profile: Optional[str] = typer.Option(
        None,
        help="Use a predefined configuration profile.",
        rich_help_panel="Simulation Configuration",
    ),
    interval: Optional[float] = typer.Option(
        None,
        help="Seconds between file operations. [default: 5.0]",
        rich_help_panel="Simulation Configuration",
    ),
    force_structure: Optional[ForceStructure] = typer.Option(
        None,
        help="Force specific structure instead of auto-detection.",
        rich_help_panel="Simulation Configuration",
    ),
    batch_size: Optional[int] = typer.Option(
        None,
        help="Number of files to process per interval. [default: 1]",
        rich_help_panel="Simulation Configuration",
    ),
    no_wait: bool = typer.Option(
        False,
        help="Skip timing delays between batches.",
        rich_help_panel="Simulation Configuration",
    ),
    # Timing Models
    timing_model: Optional[TimingModelChoice] = typer.Option(
        None,
        help="Timing model (overrides profile setting).",
        rich_help_panel="Timing Models",
    ),
    burst_probability: Optional[float] = typer.Option(
        None,
        help="Burst probability for Poisson model (0.0-1.0).",
        rich_help_panel="Timing Models",
    ),
    burst_rate_multiplier: Optional[float] = typer.Option(
        None,
        help="Burst rate multiplier for Poisson model.",
        rich_help_panel="Timing Models",
    ),
    random_factor: Optional[float] = typer.Option(
        None,
        help="Randomness factor for random timing model (0.0-1.0).",
        rich_help_panel="Timing Models",
    ),
    adaptation_rate: Optional[float] = typer.Option(
        None,
        help="Adaptation rate for adaptive timing model (0.0-1.0).",
        rich_help_panel="Timing Models",
    ),
    history_size: Optional[int] = typer.Option(
        None,
        help="History size for adaptive timing model.",
        rich_help_panel="Timing Models",
    ),
    # Parallel Processing
    parallel: bool = typer.Option(
        False,
        help="Enable parallel processing within batches.",
        rich_help_panel="Parallel Processing",
    ),
    worker_count: Optional[int] = typer.Option(
        None,
        help="Number of worker threads for parallel processing. [default: 4]",
        rich_help_panel="Parallel Processing",
    ),
    # Monitoring
    monitor: MonitorLevel = typer.Option(
        MonitorLevel.default,
        help=(
            "Progress monitoring level: default (basic), "
            "enhanced (resource monitoring + interactive controls), "
            "none (silent)."
        ),
        rich_help_panel="Monitoring",
    ),
    quiet: bool = typer.Option(
        False,
        help="Suppress progress output.",
        rich_help_panel="Monitoring",
    ),
    pipeline: Optional[str] = typer.Option(
        None,
        help="Validate output for specific pipeline compatibility.",
        rich_help_panel="Monitoring",
    ),
) -> None:
    """Generate simulated nanopore reads from genome FASTA files."""
    # Apply defaults for sentinel-valued CLI options. Explicit CLI values
    # take priority; None means the user did not pass the option, so we
    # fall back to profile values (resolved below) or built-in defaults.
    _read_count = read_count
    _mean_read_length = mean_read_length
    _mean_quality = mean_quality
    _std_quality = std_quality
    _reads_per_file = reads_per_file
    _interval = interval
    _batch_size = batch_size
    _worker_count = worker_count

    if no_wait:
        _interval = 0.0

    # Mutual exclusivity validation
    sources = sum(
        [
            genomes is not None,
            species is not None,
            mock is not None,
            taxid is not None,
        ]
    )
    if sources == 0:
        typer.echo(
            "Error: specify one of --genomes, --species, --mock, or --taxid",
            err=True,
        )
        raise typer.Exit(code=1)
    if sources > 1:
        typer.echo(
            "Error: --genomes, --species, --mock, and --taxid "
            "are mutually exclusive",
            err=True,
        )
        raise typer.Exit(code=1)

    # Expand genome paths (directories -> contained files)
    if genomes:
        genomes = _expand_genome_paths(genomes)

    _validate_timing_params(
        burst_probability,
        burst_rate_multiplier,
        random_factor,
        adaptation_rate,
        history_size,
    )

    timing_params = _build_timing_params(
        burst_probability,
        burst_rate_multiplier,
        random_factor,
        adaptation_rate,
        history_size,
    )

    # Profile overlay
    params: Dict = {}
    if profile:
        from nanopore_simulator.profiles import apply_profile

        try:
            params = apply_profile(profile)
        except ValueError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=2)

    tm = timing_model.value if timing_model else params.get("timing_model", "uniform")
    tp = timing_params or params.get("timing_model_params", {})
    # Resolve sentinel defaults: explicit CLI values (not None) take
    # priority over profile values, which take priority over built-in
    # defaults. This avoids the ambiguity where a user explicitly passing
    # the default value would be indistinguishable from not passing it.
    rc = _read_count if _read_count is not None else params.get("read_count", 1000)
    mrl = (
        _mean_read_length
        if _mean_read_length is not None
        else params.get("mean_read_length", 5000)
    )
    mq = (
        _mean_quality if _mean_quality is not None else params.get("mean_quality", 20.0)
    )
    sq = _std_quality if _std_quality is not None else params.get("std_quality", 4.0)
    rpf = (
        _reads_per_file
        if _reads_per_file is not None
        else params.get("reads_per_file", 100)
    )
    iv = _interval if _interval is not None else params.get("interval", 5.0)
    bs = _batch_size if _batch_size is not None else params.get("batch_size", 1)
    par = parallel or params.get("parallel_processing", False)
    wk = _worker_count if _worker_count is not None else params.get("worker_count", 4)
    if force_structure:
        struct = force_structure.value
    elif genomes and len(genomes) > 1:
        struct = "multiplex"
    else:
        struct = "singleplex"
    monitor_type = _resolve_monitor(monitor, quiet)

    # Species / mock / taxid resolution
    genome_inputs = list(genomes) if genomes else None
    species_inputs = list(species) if species else None
    taxid_inputs = [str(t) for t in taxid] if taxid else None
    mock_name = mock

    try:
        config = GenerateConfig(
            target_dir=target,
            genome_inputs=genome_inputs,
            species_inputs=species_inputs,
            mock_name=mock_name,
            taxid_inputs=taxid_inputs,
            abundances=list(abundances) if abundances else None,
            read_count=rc,
            interval=iv,
            batch_size=bs,
            generator_backend=generator_backend.value,
            mean_length=mrl,
            mean_quality=mq,
            std_quality=sq,
            reads_per_file=rpf,
            output_format=output_format.value,
            mix_reads=mix_reads,
            timing_model=tm,
            timing_params=tp,
            parallel=par,
            workers=wk,
            monitor_type=monitor_type,
            adapter=pipeline,
            structure=struct,
            offline_mode=offline,
        )
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2)

    # Pre-flight validation
    from nanopore_simulator.deps import check_preflight

    needs_download = bool(species_inputs or mock_name or taxid_inputs) and not offline
    errors = check_preflight(
        operation="generate",
        generator_backend=config.generator_backend,
        needs_genome_download=needs_download,
    )
    if errors:
        for err in errors:
            typer.echo(f"Error: {err}", err=True)
        raise typer.Exit(code=1)

    # Resolve mock/species/taxid to genome paths if needed
    if needs_download or (mock_name and offline):
        genome_paths, mock_abundances = _resolve_and_download_genomes(
            mock_name,
            species_inputs,
            taxid_inputs,
            offline=offline,
        )
        # Determine structure for multi-genome inputs
        resolved_struct = struct
        if len(genome_paths) > 1 and force_structure is None:
            resolved_struct = "multiplex"
        # Rebuild config with resolved genome paths (GenerateConfig is frozen)
        config = GenerateConfig(
            target_dir=config.target_dir,
            genome_inputs=genome_paths,
            species_inputs=None,
            mock_name=None,
            taxid_inputs=None,
            abundances=mock_abundances if not abundances else config.abundances,
            read_count=config.read_count,
            interval=config.interval,
            batch_size=config.batch_size,
            generator_backend=config.generator_backend,
            mean_length=config.mean_length,
            std_length=config.std_length,
            min_length=config.min_length,
            mean_quality=config.mean_quality,
            std_quality=config.std_quality,
            reads_per_file=config.reads_per_file,
            output_format=config.output_format,
            mix_reads=config.mix_reads,
            timing_model=config.timing_model,
            timing_params=config.timing_params,
            parallel=config.parallel,
            workers=config.workers,
            monitor_type=config.monitor_type,
            adapter=config.adapter,
            structure=resolved_struct,
            offline_mode=config.offline_mode,
        )

    try:
        run_generate(config)
    except KeyboardInterrupt:
        typer.echo("\nSimulation interrupted by user", err=True)
        raise typer.Exit(code=1)
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)

    # Post-run pipeline validation
    if pipeline:
        _run_pipeline_validation(pipeline, target)


# -------------------------------------------------------------------
# Info commands
# -------------------------------------------------------------------


@app.command("list-profiles")
def list_profiles_cmd() -> None:
    """List all available configuration profiles."""
    from nanopore_simulator.profiles import list_profiles

    profiles = list_profiles()
    print("Available Configuration Profiles:")
    print("=" * 50)
    for name, description in profiles.items():
        print(f"  {name:20} - {description}")


@app.command("list-adapters")
def list_adapters_cmd() -> None:
    """List all available pipeline adapters."""
    from nanopore_simulator.adapters import list_adapters

    adapters = list_adapters()
    print("Available Pipeline Adapters:")
    print("=" * 50)
    for name, description in adapters.items():
        print(f"  {name:15} - {description}")


@app.command("list-generators")
def list_generators_cmd() -> None:
    """List available read generation backends."""
    from nanopore_simulator.generators import detect_available_backends

    backends = detect_available_backends()
    print("Available Read Generation Backends:")
    print("=" * 50)
    for name, available in backends.items():
        status = "available" if available else "not found"
        print(f"  {name:15} - {status}")


@app.command("list-mocks")
def list_mocks_cmd() -> None:
    """List available mock communities."""
    from nanopore_simulator.mocks import BUILTIN_MOCKS, MOCK_ALIASES

    print("Available Mock Communities:")
    print("=" * 60)
    for name, mock_community in sorted(BUILTIN_MOCKS.items()):
        print(f"  {name:20} - {mock_community.description}")

    if MOCK_ALIASES:
        print("\nAliases:")
        print("-" * 60)
        targets: Dict[str, List[str]] = {}
        for alias, alias_target in MOCK_ALIASES.items():
            if alias_target not in targets:
                targets[alias_target] = []
            targets[alias_target].append(alias)
        for alias_target, aliases in sorted(targets.items()):
            alias_str = ", ".join(sorted(aliases))
            print(f"  {alias_str:30} -> {alias_target}")


@app.command("check-deps")
def check_deps_cmd() -> None:
    """Check availability of external tools and optional dependencies."""
    from nanopore_simulator.deps import check_all_dependencies

    statuses = check_all_dependencies()

    print("Nanorunner Dependency Status")
    print("=" * 60)

    categories = [
        ("generator", "Read Generation Backends"),
        ("tool", "External Tools"),
        ("python", "Optional Python Packages"),
    ]

    missing_count = 0

    for cat_key, cat_label in categories:
        items = [s for s in statuses if s.category == cat_key]
        if not items:
            continue

        print(f"\n{cat_label}:")
        for dep in items:
            status_str = "available" if dep.available else "not found"
            print(f"  {dep.name:20} {status_str:14}{dep.description}")
            if not dep.available:
                missing_count += 1
                print(f"  {'':20} Install: {dep.install_hint}")
                print(f"  {'':20} Needed for: {dep.required_for}")

    print()
    if missing_count == 0:
        print("All dependencies are available.")
    else:
        print(f"{missing_count} optional dependency(ies) not found.")
        print(
            "Core functionality (builtin generator, replay mode) " "works without them."
        )


# -------------------------------------------------------------------
# Utility commands
# -------------------------------------------------------------------


@app.command("recommend")
def recommend_cmd(
    source: Optional[Path] = typer.Option(
        None,
        "--source",
        "-s",
        help="Source directory to analyse (omit for an overview of all profiles).",
    ),
    file_count: Optional[int] = typer.Option(
        None,
        "--file-count",
        help="Number of files (use instead of --source for quick recommendations).",
    ),
) -> None:
    """Recommend configuration profiles for a source directory."""
    from nanopore_simulator.profiles import get_recommendations, list_profiles

    if file_count is not None:
        recs = get_recommendations(file_count)
        profiles = list_profiles()
        print(f"Recommended profiles for {file_count} files:")
        for i, name in enumerate(recs, 1):
            desc = profiles.get(name, "")
            print(f"  {i}. {name} - {desc}")
        return

    if source is not None:
        if not source.exists() or not source.is_dir():
            typer.echo(f"Error: Not a valid directory: {source}", err=True)
            raise typer.Exit(code=1)
        # Count files in source
        from nanopore_simulator.detection import find_sequencing_files

        files = find_sequencing_files(source)
        # Also check barcode subdirectories
        if not files:
            for subdir in source.iterdir():
                if subdir.is_dir():
                    files.extend(find_sequencing_files(subdir))
        if not files:
            print(f"No sequencing files found in {source}")
            raise typer.Exit(code=1)
        recs = get_recommendations(len(files))
        profiles = list_profiles()
        print(f"Analysis of {source}:")
        print(f"  Found {len(files)} sequencing file(s)")
        print(f"\nRecommended profiles for {len(files)} files:")
        for i, name in enumerate(recs, 1):
            desc = profiles.get(name, "")
            print(f"  {i}. {name} - {desc}")
        return

    # No source or file-count: show all profiles
    profiles = list_profiles()
    print("Available Configuration Profiles")
    print("=" * 55)
    for name, desc in profiles.items():
        print(f"  {name:20} - {desc}")


@app.command("validate")
def validate_cmd(
    pipeline: str = typer.Option(
        ...,
        "--pipeline",
        "-p",
        help="Pipeline name to validate against.",
    ),
    target: Path = typer.Option(
        ...,
        "--target",
        "-t",
        help="Target directory to validate.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
) -> None:
    """Validate directory structure for a pipeline."""
    from nanopore_simulator.adapters import validate_output

    issues = validate_output(target, pipeline)
    print(f"Pipeline validation report for '{pipeline}':")
    print("=" * 50)
    if not issues:
        print("Valid: yes")
    else:
        print("Valid: no")
        print("Issues:")
        for issue in issues:
            print(f"  - {issue}")
        raise typer.Exit(code=1)


@app.command()
def download(
    # Genome Source
    species: Optional[List[str]] = typer.Option(
        None,
        help="Species names to download.",
        rich_help_panel="Genome Source",
    ),
    mock: Optional[str] = typer.Option(
        None,
        help="Mock community to download genomes for.",
        rich_help_panel="Genome Source",
    ),
    taxid: Optional[List[int]] = typer.Option(
        None,
        help="NCBI taxonomy IDs to download.",
        rich_help_panel="Genome Source",
    ),
    # Optional target for generation
    target: Optional[Path] = typer.Option(
        None,
        "--target",
        "-t",
        help="Target directory for read generation (omit for download only).",
    ),
    # Generation options
    read_count: int = typer.Option(
        1000,
        help="Total number of reads to generate.",
        rich_help_panel="Generation Options",
    ),
    reads_per_file: int = typer.Option(
        100,
        help="Number of reads per output file.",
        rich_help_panel="Generation Options",
    ),
    mean_read_length: int = typer.Option(
        5000,
        help="Mean read length in bases.",
        rich_help_panel="Generation Options",
    ),
    mean_quality: float = typer.Option(
        20.0,
        help="Mean Phred quality score.",
        rich_help_panel="Generation Options",
    ),
    std_quality: float = typer.Option(
        4.0,
        help="Standard deviation of quality scores.",
        rich_help_panel="Generation Options",
    ),
    output_format: OutputFormat = typer.Option(
        OutputFormat.fastq_gz,
        help="Output file format.",
        rich_help_panel="Generation Options",
    ),
    generator_backend: GeneratorBackend = typer.Option(
        GeneratorBackend.auto,
        help="Read generation backend.",
        rich_help_panel="Generation Options",
    ),
    interval: float = typer.Option(
        5.0,
        help="Seconds between file operations.",
        rich_help_panel="Generation Options",
    ),
    batch_size: int = typer.Option(
        1,
        help="Number of files to process per interval.",
        rich_help_panel="Generation Options",
    ),
    mix_reads: bool = typer.Option(
        False,
        help="Mix reads from all genomes into shared files.",
        rich_help_panel="Generation Options",
    ),
    no_wait: bool = typer.Option(
        False,
        help="Skip timing delays during read generation.",
        rich_help_panel="Generation Options",
    ),
    # Parallel Processing
    parallel: bool = typer.Option(
        False,
        help="Download genomes in parallel.",
        rich_help_panel="Parallel Processing",
    ),
    worker_count: int = typer.Option(
        4,
        help="Number of concurrent downloads.",
        rich_help_panel="Parallel Processing",
    ),
) -> None:
    """Download genomes for offline use, optionally generating reads."""
    if no_wait:
        interval = 0.0

    if not (species or mock or taxid):
        typer.echo("Error: Must specify --species, --mock, or --taxid", err=True)
        raise typer.Exit(code=1)

    # Pre-flight: verify datasets CLI
    from nanopore_simulator.deps import check_preflight

    errors = check_preflight(operation="copy", needs_genome_download=True)
    if errors:
        for err in errors:
            typer.echo(f"Error: {err}", err=True)
        raise typer.Exit(code=1)

    # Resolve and download
    from nanopore_simulator.species import (
        GenomeCache,
        GenomeRef,
        download_genome,
        resolve_species,
        resolve_taxid,
    )
    from nanopore_simulator.mocks import get_mock

    cache = GenomeCache()
    genome_downloads: List[tuple] = []  # (name, ref) pairs
    mock_community = None

    if mock:
        mock_community = get_mock(mock)
        if mock_community is None:
            typer.echo(f"Error: Unknown mock community: {mock}", err=True)
            raise typer.Exit(code=1)
        for org in mock_community.organisms:
            ref: Optional[GenomeRef] = None
            if org.accession:
                domain = org.domain or (
                    "eukaryota" if org.resolver == "ncbi" else "bacteria"
                )
                ref = GenomeRef(
                    name=org.name,
                    accession=org.accession,
                    source=org.resolver,
                    domain=domain,
                )
            else:
                ref = resolve_species(org.name)
            if ref:
                genome_downloads.append((org.name, ref))
            else:
                typer.echo(f"Warning: Could not resolve: {org.name}", err=True)

    if species:
        for sp in species:
            sp_ref: Optional[GenomeRef] = resolve_species(sp)
            if sp_ref:
                genome_downloads.append((sp, sp_ref))
            else:
                typer.echo(f"Warning: Could not resolve: {sp}", err=True)

    if taxid:
        for tid in taxid:
            tid_ref: Optional[GenomeRef] = resolve_taxid(tid)
            if tid_ref:
                genome_downloads.append((f"taxid:{tid}", tid_ref))
            else:
                typer.echo(f"Warning: Could not resolve taxid: {tid}", err=True)

    if not genome_downloads:
        typer.echo("No genomes to download", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Downloading {len(genome_downloads)} genome(s)...")
    successful: List[tuple] = []  # (name, ref, path)

    for name, ref in genome_downloads:
        try:
            path = download_genome(ref, cache=cache)
            typer.echo(f"  Downloaded: {name} -> {path}")
            successful.append((name, ref, path))
        except Exception as exc:
            typer.echo(f"  Failed: {name} - {exc}", err=True)

    typer.echo("Download complete")

    # Optionally generate reads if target provided
    if target is not None:
        if not successful:
            typer.echo(
                "Error: No genomes downloaded successfully, cannot generate reads",
                err=True,
            )
            raise typer.Exit(code=1)

        genome_paths = [path for _, _, path in successful]

        try:
            config = GenerateConfig(
                target_dir=target,
                genome_inputs=genome_paths,
                read_count=read_count,
                interval=interval,
                batch_size=batch_size,
                generator_backend=generator_backend.value,
                mean_length=mean_read_length,
                mean_quality=mean_quality,
                std_quality=std_quality,
                reads_per_file=reads_per_file,
                output_format=output_format.value,
                mix_reads=mix_reads,
                parallel=parallel,
                workers=worker_count,
            )
            typer.echo(f"\nGenerating reads into {target}...")
            run_generate(config)
            typer.echo("Read generation complete")
        except Exception as exc:
            typer.echo(f"Error during read generation: {exc}", err=True)
            raise typer.Exit(code=1)


# -------------------------------------------------------------------
# Pipeline validation helper
# -------------------------------------------------------------------


def _run_pipeline_validation(pipeline_name: str, target: Path) -> None:
    """Print post-run pipeline validation results."""
    from nanopore_simulator.adapters import validate_output

    print(f"\nValidating output for {pipeline_name} pipeline...")
    issues = validate_output(target, pipeline_name)
    if not issues:
        print(f"Output is compatible with {pipeline_name} pipeline")
    else:
        print(f"Output may not be compatible with {pipeline_name} pipeline")
        for issue in issues:
            print(f"  Warning: {issue}")


# -------------------------------------------------------------------
# Entry point
# -------------------------------------------------------------------


def main() -> int:
    """Entry point for console_scripts."""
    try:
        app()
        return 0
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 0


if __name__ == "__main__":
    sys.exit(main())
