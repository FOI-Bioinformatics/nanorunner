"""Generate mode CLI command.

Registers the ``generate`` subcommand on the shared Typer ``app``.
"""

from pathlib import Path
from typing import Dict, List, Optional

import typer

from nanopore_simulator.cli import (
    ForceStructure,
    GeneratorBackend,
    MonitorLevel,
    OutputFormat,
    TimingModelChoice,
    app,
)
from nanopore_simulator.cli_helpers import (
    _build_timing_params,
    _expand_genome_paths,
    _resolve_and_download_genomes,
    _resolve_monitor,
    _run_pipeline_validation,
    _validate_timing_params,
)
from nanopore_simulator.config import GenerateConfig
from nanopore_simulator.runner import EmptySourceError, run_generate


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
    except EmptySourceError as exc:
        # Distinct exit code (3) for "operator mistake" vs (1) generic
        # error so CI pipelines can branch on the cause if needed.
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=3)
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)

    # Post-run pipeline validation
    if pipeline:
        _run_pipeline_validation(pipeline, target)
