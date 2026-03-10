"""Manifest building for replay and generate modes.

Answers the planning question: what files will be produced, in what
order, and with what parameters?  The manifest is a list of
``FileEntry`` objects that describe each output file.  Actual
execution is handled separately by ``executor.py``.
"""

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from nanopore_simulator.config import ReplayConfig, GenerateConfig
from nanopore_simulator.detection import (
    detect_structure,
    find_barcode_dirs,
    find_sequencing_files,
)
from nanopore_simulator.fastq import count_reads


# -------------------------------------------------------------------
# FileEntry dataclass
# -------------------------------------------------------------------


@dataclass
class FileEntry:
    """A single planned file operation.

    For replay mode (copy/link), ``source`` is set and ``genome`` is
    None.  For generate mode, ``genome`` and ``read_count`` are set
    and ``source`` is None.

    Attributes:
        source: Source file path (replay mode).  None for generate.
        target: Target file path (full path including filename).
        operation: One of "copy", "link", "generate", or "rechunk".
        genome: Genome FASTA path (generate mode).  None for replay.
        read_count: Number of reads to write (generate/rechunk mode).
        batch: Zero-based batch index for timing.
        file_index: Sequential file index for naming output files.
        barcode: Barcode directory name, or None for singleplex.
        mixed_genome_reads: For mixed-mode generate entries, a list of
            (genome_path, read_count) tuples.
        source_files: For rechunk entries, ordered list of source FASTQ
            paths whose reads are pooled and re-distributed.
    """

    source: Optional[Path] = None
    target: Path = field(default_factory=Path)
    operation: str = "copy"
    genome: Optional[Path] = None
    read_count: Optional[int] = None
    batch: int = 0
    file_index: int = 0
    barcode: Optional[str] = None
    mixed_genome_reads: Optional[List[tuple]] = None
    source_files: Optional[List[Path]] = None


# -------------------------------------------------------------------
# Read distribution helper
# -------------------------------------------------------------------


def distribute_reads(total: int, weights: List[float]) -> List[int]:
    """Distribute total reads across organisms using largest-remainder.

    Each organism with weight > 0 receives at least 1 read.  The
    remaining reads are distributed by fractional part so the sum
    equals ``total`` exactly.

    Args:
        total: Total reads to distribute.
        weights: Abundance proportions (should sum to approximately 1.0).

    Returns:
        Per-organism read counts summing to ``total``.
    """
    n = len(weights)
    if n == 0:
        return []
    if n == 1:
        return [total]

    # Floor allocation
    raw = [w * total for w in weights]
    floors = [int(r) for r in raw]
    remainders = [r - f for r, f in zip(raw, floors)]

    # Guarantee at least 1 read for any organism with weight > 0
    for i in range(n):
        if weights[i] > 0 and floors[i] < 1:
            floors[i] = 1

    # Distribute remaining reads by largest fractional part
    allocated = sum(floors)
    deficit = total - allocated
    if deficit > 0:
        ranked = sorted(range(n), key=lambda i: (-remainders[i], i))
        for i in range(min(deficit, n)):
            floors[ranked[i]] += 1
    elif deficit < 0:
        # Over-allocated due to minimum-1 guarantees; reduce from
        # the largest allocations that still exceed 1
        surplus = -deficit
        ranked = sorted(range(n), key=lambda i: (-floors[i], i))
        for idx in ranked:
            if surplus <= 0:
                break
            if floors[idx] > 1:
                reduction = min(floors[idx] - 1, surplus)
                floors[idx] -= reduction
                surplus -= reduction

    return floors


# -------------------------------------------------------------------
# Replay manifest
# -------------------------------------------------------------------

_FASTQ_EXTENSIONS = {".fastq", ".fq", ".fastq.gz", ".fq.gz"}


def _is_fastq_file(path: Path) -> bool:
    """Check whether *path* has a FASTQ extension."""
    name = path.name.lower()
    return any(name.endswith(ext) for ext in _FASTQ_EXTENSIONS)


def _get_fastq_extension(path: Path) -> str:
    """Return the canonical FASTQ extension for *path*."""
    if path.name.lower().endswith(".gz"):
        return ".fastq.gz"
    return ".fastq"


def _fastq_stem(path: Path) -> str:
    """Return the filename stem with FASTQ extensions removed."""
    name = path.name
    for ext in (".fastq.gz", ".fq.gz", ".fastq", ".fq"):
        if name.lower().endswith(ext):
            return name[: len(name) - len(ext)]
    return path.stem


def build_replay_manifest(config: ReplayConfig) -> List[FileEntry]:
    """Build a manifest of file entries for replay mode.

    Detects (or uses forced) source directory structure and enumerates
    files.  When ``reads_per_output`` is set, source FASTQ files are
    rechunked into smaller output files.  Batch numbers are assigned
    according to ``batch_size``.

    Args:
        config: Replay mode configuration.

    Returns:
        Ordered list of FileEntry objects to execute.
    """
    # Determine structure
    if config.structure != "auto":
        structure = config.structure
    else:
        try:
            structure = detect_structure(config.source_dir)
        except ValueError:
            return []

    # Build raw file list
    if structure == "singleplex":
        raw_entries = _singleplex_entries(config)
    else:
        raw_entries = _multiplex_entries(config)

    if not raw_entries:
        return []

    # Rechunking path
    if config.reads_per_output is not None:
        raw_entries = _rechunk_entries(raw_entries, config)

    # Assign batch numbers
    for i, entry in enumerate(raw_entries):
        entry.batch = i // config.batch_size

    return raw_entries


def _singleplex_entries(config: ReplayConfig) -> List[FileEntry]:
    """Build entries for a singleplex source directory."""
    files = find_sequencing_files(config.source_dir)
    entries: List[FileEntry] = []
    for f in sorted(files, key=lambda p: p.name):
        entries.append(
            FileEntry(
                source=f,
                target=config.target_dir / f.name,
                operation=config.operation,
                barcode=None,
            )
        )
    return entries


def _multiplex_entries(config: ReplayConfig) -> List[FileEntry]:
    """Build entries for a multiplex source directory."""
    barcode_dirs = find_barcode_dirs(config.source_dir)
    entries: List[FileEntry] = []
    for bc_dir in sorted(barcode_dirs, key=lambda p: p.name):
        barcode_name = bc_dir.name
        files = find_sequencing_files(bc_dir)
        for f in sorted(files, key=lambda p: p.name):
            target_dir = config.target_dir / barcode_name
            entries.append(
                FileEntry(
                    source=f,
                    target=target_dir / f.name,
                    operation=config.operation,
                    barcode=barcode_name,
                )
            )
    return entries


def _rechunk_entries(
    raw_entries: List[FileEntry], config: ReplayConfig
) -> List[FileEntry]:
    """Replace raw entries with rechunked entries.

    Reads are counted in each source FASTQ, then output entries are
    planned with ``reads_per_output`` reads each.  Non-FASTQ files
    (e.g. POD5) are passed through as-is.
    """
    rpf = config.reads_per_output
    assert rpf is not None

    # Group by barcode
    barcode_order: List[Optional[str]] = []
    groups: dict = {}
    for entry in raw_entries:
        bc = entry.barcode
        if bc not in groups:
            barcode_order.append(bc)
            # Determine target directory from existing entry
            if entry.barcode:
                target_dir = config.target_dir / entry.barcode
            else:
                target_dir = config.target_dir
            groups[bc] = {
                "target_dir": target_dir,
                "fastq_files": [],
                "other_entries": [],
            }
        if _is_fastq_file(entry.source):
            read_count = count_reads(entry.source)
            groups[bc]["fastq_files"].append((entry.source, read_count))
        else:
            groups[bc]["other_entries"].append(entry)

    rechunked: List[FileEntry] = []
    for bc in barcode_order:
        grp = groups[bc]
        target_dir = grp["target_dir"]

        # Non-FASTQ files pass through
        rechunked.extend(grp["other_entries"])

        # Plan rechunked output files
        total_reads = sum(c for _, c in grp["fastq_files"])
        if total_reads == 0:
            continue

        n_output = math.ceil(total_reads / rpf)
        first_source = (
            grp["fastq_files"][0][0] if grp["fastq_files"] else None
        )
        ext = _get_fastq_extension(first_source) if first_source else ".fastq"
        stem = _fastq_stem(first_source) if first_source else "reads"

        # Collect ordered source paths for the rechunk entries.
        source_paths = [src for src, _ in grp["fastq_files"]]

        for chunk_idx in range(n_output):
            filename = f"{stem}_chunk_{chunk_idx:04d}{ext}"
            rechunked.append(
                FileEntry(
                    source=None,
                    target=target_dir / filename,
                    operation="rechunk",
                    barcode=bc,
                    read_count=min(
                        rpf, total_reads - chunk_idx * rpf
                    ),
                    file_index=chunk_idx,
                    source_files=source_paths,
                )
            )

    return rechunked


# -------------------------------------------------------------------
# Generate manifest
# -------------------------------------------------------------------


def build_generate_manifest(config: GenerateConfig) -> List[FileEntry]:
    """Build a manifest of file entries for generate mode.

    Distributes ``read_count`` across genomes (abundance-weighted or
    equal split), then plans output files with ``reads_per_file``
    reads each.  Batch numbers are assigned according to
    ``batch_size``.

    For multiplex structure, each genome maps to a separate barcode
    directory.  For singleplex with ``mix_reads=True``, each file
    contains reads from all genomes.

    Args:
        config: Generate mode configuration.

    Returns:
        Ordered list of FileEntry objects to execute.
    """
    genomes = config.genome_inputs or []
    if not genomes:
        return []

    total_reads = config.read_count
    n_genomes = len(genomes)

    # Determine per-genome read counts
    if config.abundances and len(config.abundances) == n_genomes:
        per_genome_reads = distribute_reads(total_reads, config.abundances)
    else:
        per_genome_reads = distribute_reads(
            total_reads, [1.0 / n_genomes] * n_genomes
        )

    rpf = config.reads_per_file
    ext = ".fastq.gz" if config.output_format == "fastq.gz" else ".fastq"

    entries: List[FileEntry] = []

    if config.structure == "multiplex":
        entries = _generate_multiplex_entries(
            config, genomes, per_genome_reads, rpf, ext
        )
    elif config.mix_reads:
        entries = _generate_mixed_entries(
            config, genomes, per_genome_reads, rpf, ext
        )
    else:
        entries = _generate_singleplex_entries(
            config, genomes, per_genome_reads, rpf, ext
        )

    # Assign batch numbers
    for i, entry in enumerate(entries):
        entry.batch = i // config.batch_size

    return entries


def _genome_stem(genome_path: Path) -> str:
    """Return the genome filename stem, handling double extensions."""
    stem = genome_path.stem
    if stem.endswith((".fasta", ".fa", ".fna")):
        stem = Path(stem).stem
    return stem


def _generate_multiplex_entries(
    config: GenerateConfig,
    genomes: List[Path],
    per_genome_reads: List[int],
    rpf: int,
    ext: str,
) -> List[FileEntry]:
    """Generate entries with each genome in a separate barcode directory."""
    entries: List[FileEntry] = []
    for idx, genome_path in enumerate(genomes):
        barcode = f"barcode{idx + 1:02d}"
        barcode_dir = config.target_dir / barcode
        stem = _genome_stem(genome_path)
        n_files = max(1, math.ceil(per_genome_reads[idx] / rpf))
        remaining = per_genome_reads[idx]
        for fi in range(n_files):
            chunk = min(rpf, remaining)
            remaining -= chunk
            filename = f"{stem}_reads_{fi:04d}{ext}"
            entries.append(
                FileEntry(
                    target=barcode_dir / filename,
                    operation="generate",
                    genome=genome_path,
                    read_count=chunk,
                    file_index=fi,
                    barcode=barcode,
                )
            )
    return entries


def _generate_singleplex_entries(
    config: GenerateConfig,
    genomes: List[Path],
    per_genome_reads: List[int],
    rpf: int,
    ext: str,
) -> List[FileEntry]:
    """Generate entries for singleplex mode (separate files per genome)."""
    entries: List[FileEntry] = []
    for idx, genome_path in enumerate(genomes):
        stem = _genome_stem(genome_path)
        n_files = max(1, math.ceil(per_genome_reads[idx] / rpf))
        remaining = per_genome_reads[idx]
        for fi in range(n_files):
            chunk = min(rpf, remaining)
            remaining -= chunk
            filename = f"{stem}_reads_{fi:04d}{ext}"
            entries.append(
                FileEntry(
                    target=config.target_dir / filename,
                    operation="generate",
                    genome=genome_path,
                    read_count=chunk,
                    file_index=fi,
                    barcode=None,
                )
            )
    return entries


def _generate_mixed_entries(
    config: GenerateConfig,
    genomes: List[Path],
    per_genome_reads: List[int],
    rpf: int,
    ext: str,
) -> List[FileEntry]:
    """Generate mixed-read entries with reads from all genomes in each file."""
    total_reads = config.read_count
    n_genomes = len(genomes)
    total_files = max(1, math.ceil(total_reads / rpf))

    # Weights for per-file distribution
    weights = (
        list(config.abundances)
        if config.abundances
        else [1.0 / n_genomes] * n_genomes
    )

    entries: List[FileEntry] = []
    remaining = total_reads
    for fi in range(total_files):
        chunk = min(rpf, remaining)
        remaining -= chunk
        # Distribute this file's reads across genomes
        per_genome = distribute_reads(chunk, weights)
        genome_reads = [
            (g, n) for g, n in zip(genomes, per_genome) if n > 0
        ]
        filename = f"reads_{fi:04d}{ext}"
        entries.append(
            FileEntry(
                target=config.target_dir / filename,
                operation="generate",
                read_count=chunk,
                file_index=fi,
                barcode=None,
                mixed_genome_reads=genome_reads,
            )
        )
    return entries
