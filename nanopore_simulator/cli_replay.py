"""Replay mode CLI command.

Registers the ``replay`` subcommand on the shared Typer ``app``.
"""

from pathlib import Path
from typing import Dict, Optional

import typer

from nanopore_simulator.cli import (
    ForceStructure,
    MonitorLevel,
    OperationChoice,
    TimingModelChoice,
    app,
)
from nanopore_simulator.cli_helpers import (
    _build_timing_params,
    _resolve_monitor,
    _run_pipeline_validation,
    _validate_timing_params,
)
from nanopore_simulator.config import ReplayConfig
from nanopore_simulator.runner import run_replay


@app.command()
def replay(
    # Required
    source: Path = typer.Option(
        ...,
        "--source",
        "-s",
        help="Source directory containing FASTQ files.",
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
    """Replay existing FASTQ files with configurable timing."""
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
