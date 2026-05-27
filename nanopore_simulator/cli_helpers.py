"""Helper functions shared by CLI command modules.

Contains timing parameter utilities, monitor resolution, genome path
expansion, species/mock resolution, and post-run pipeline validation.
These are internal helpers; they are not part of the public API.
"""

from pathlib import Path
from typing import Dict, List, Optional

import typer

# ---------------------------------------------------------------------------
# Genome file extensions
# ---------------------------------------------------------------------------

_GENOME_EXTENSIONS = {".fa", ".fasta", ".fna", ".fa.gz", ".fasta.gz", ".fna.gz"}


# ---------------------------------------------------------------------------
# Timing helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Monitor resolution
# ---------------------------------------------------------------------------


def _resolve_monitor(monitor: object, quiet: bool) -> str:
    """Map MonitorLevel enum + quiet flag to a config monitor_type string."""
    from nanopore_simulator.cli import MonitorLevel

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


# ---------------------------------------------------------------------------
# Genome path helpers
# ---------------------------------------------------------------------------


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


def _resolve_genome_refs(
    mock_name: Optional[str],
    species_inputs: Optional[List[str]],
    taxid_inputs: Optional[List[str]],
) -> List[tuple]:
    """Resolve mock/species/taxid inputs to genome references.

    Returns a list of (name, GenomeRef, abundance_or_None) tuples.  The
    abundance value is only set for mock-community organisms; species
    and taxid inputs get None so callers can preserve index alignment
    when different input types are combined.  Unresolvable inputs emit
    warnings and are skipped.

    Raises:
        typer.Exit(code=1): If no inputs resolve to a valid GenomeRef
            (e.g. unknown mock name and no other inputs).
    """
    from nanopore_simulator.species import (
        GenomeRef,
        resolve_species,
        resolve_taxid,
    )
    from nanopore_simulator.mocks import get_mock

    refs: List[tuple] = []

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
                refs.append((org.name, ref, org.abundance))
            else:
                typer.echo(f"Warning: Could not resolve: {org.name}", err=True)

    if species_inputs:
        for sp in species_inputs:
            sp_ref: Optional[GenomeRef] = resolve_species(sp)
            if sp_ref:
                refs.append((sp, sp_ref, None))
            else:
                typer.echo(f"Warning: Could not resolve: {sp}", err=True)

    if taxid_inputs:
        for tid in taxid_inputs:
            tid_ref: Optional[GenomeRef] = resolve_taxid(int(tid))
            if tid_ref:
                refs.append((f"taxid:{tid}", tid_ref, None))
            else:
                typer.echo(f"Warning: Could not resolve taxid: {tid}", err=True)

    if not refs:
        typer.echo("Error: No genomes could be resolved", err=True)
        raise typer.Exit(code=1)

    return refs


def _download_genome_refs(refs: List[tuple]) -> List[tuple]:
    """Download genomes from resolved refs.

    Takes the (name, ref, abundance_or_None) tuples returned by
    ``_resolve_genome_refs`` and downloads each genome via the
    shared cache.  Returns the list of (name, ref, path, abundance)
    tuples that downloaded successfully.  Failures emit a warning
    and are dropped from the result.
    """
    from nanopore_simulator.species import GenomeCache, download_genome

    cache = GenomeCache()
    typer.echo(f"Downloading {len(refs)} genome(s)...")
    successful: List[tuple] = []
    for name, ref, abundance in refs:
        try:
            path = download_genome(ref, cache=cache)
            typer.echo(f"  Ready: {name} -> {path}")
            successful.append((name, ref, Path(path), abundance))
        except Exception as exc:
            typer.echo(f"  Failed: {name} - {exc}", err=True)
    return successful


def _resolve_and_download_genomes(
    mock_name: Optional[str],
    species_inputs: Optional[List[str]],
    taxid_inputs: Optional[List[str]],
    offline: bool = False,
) -> tuple:
    """Resolve and download mock/species/taxid inputs in one step.

    Convenience wrapper used by the ``generate`` subcommand.  Returns
    ``(genome_paths, abundances)`` ready for ``GenerateConfig``.  The
    ``abundances`` list is None when no input supplied abundance info,
    otherwise it is renormalized so the surviving genomes sum to 1.0.

    Raises:
        typer.Exit(code=1): If no genomes resolve or none download.
    """
    refs = _resolve_genome_refs(mock_name, species_inputs, taxid_inputs)
    successful = _download_genome_refs(refs)

    if not successful:
        typer.echo("Error: No genomes downloaded successfully", err=True)
        raise typer.Exit(code=1)

    paths = [path for _, _, path, _ in successful]
    abundances_present = [a for _, _, _, a in successful if a is not None]
    has_abundance_info = any(a is not None for _, _, _, a in successful)

    final_abundances = None
    if has_abundance_info and abundances_present:
        total = sum(abundances_present)
        if total > 0:
            final_abundances = [a / total for a in abundances_present]

    return paths, final_abundances


# ---------------------------------------------------------------------------
# Pipeline validation helper
# ---------------------------------------------------------------------------


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
