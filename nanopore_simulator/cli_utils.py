"""Utility and informational CLI commands.

Registers the following subcommands on the shared Typer ``app``:
  list-profiles, list-adapters, list-generators, list-mocks,
  check-deps, recommend, validate, download.
"""

from pathlib import Path
from typing import Dict, List, Optional

import typer

from nanopore_simulator.cli import GeneratorBackend, OutputFormat, app
from nanopore_simulator.runner import run_generate


# ---------------------------------------------------------------------------
# Informational commands
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Utility commands
# ---------------------------------------------------------------------------


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

        from nanopore_simulator.config import GenerateConfig

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
