"""Manifest building for replay and generate modes.

Answers the planning question: what files will be produced, in what
order, and with what parameters?  The manifest is a list of
``FileEntry`` objects that describe each output file.  Actual
execution is handled separately by ``executor.py``.
"""

import math
import random
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from nanopore_simulator.config import ReplayConfig, GenerateConfig
from nanopore_simulator.detection import (
    detect_structure,
    find_barcode_dirs,
    find_sequencing_files,
)
from nanopore_simulator.fastq import count_reads_with_offsets

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
        source_offset: For rechunk entries, byte offset into the
            concatenated source stream where this chunk's reads begin.
            When set, the executor can seek directly instead of
            scanning and discarding earlier reads.
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
    source_offset: Optional[int] = None


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
    rechunked into smaller output files.  When ``output_structure`` is
    not "preserve", the input shape is decoupled from the output shape:
    source reads are pooled and replayed into a flat or barcoded target
    layout regardless of the source layout.  Batch numbers are assigned
    according to ``batch_size``.

    Args:
        config: Replay mode configuration.

    Returns:
        Ordered list of FileEntry objects to execute.
    """
    # Special case: source is a single file rather than a directory.
    if config.source_dir.is_file():
        raw_entries = _single_file_entries(config)
    else:
        if config.structure != "auto":
            structure = config.structure
        else:
            try:
                structure = detect_structure(config.source_dir)
            except ValueError:
                return []

        if structure == "singleplex":
            raw_entries = _singleplex_entries(config)
        else:
            raw_entries = _multiplex_entries(config)

    if not raw_entries:
        return []

    # Reshape / rechunk path.  Both --reads-per-file and a non-preserve
    # --output-structure flow through the same pooled-rechunk pipeline.
    needs_reshape = config.output_structure != "preserve"
    if config.reads_per_output is not None or needs_reshape:
        raw_entries = _rechunk_entries(raw_entries, config)

    # Assign batch numbers
    for i, entry in enumerate(raw_entries):
        entry.batch = i // config.batch_size

    return raw_entries


def _single_file_entries(config: ReplayConfig) -> List[FileEntry]:
    """Build a synthetic singleplex entry for a single-file source."""
    src = config.source_dir
    return [
        FileEntry(
            source=src,
            target=config.target_dir / src.name,
            operation=config.operation,
            barcode=None,
        )
    ]


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

    Reads are counted in each source FASTQ while simultaneously
    recording byte offsets at chunk boundaries.  Output entries are
    planned with ``reads_per_output`` reads each (or, when only the
    output structure is changing, sized to fit the requested layout)
    and carry a ``source_offset`` so the executor can seek directly to
    the correct position instead of scanning earlier reads.

    Output layout is controlled by ``config.output_structure``:

    - ``preserve``: input barcode groups are kept; chunks within each
      group keep their barcode and are interleaved round-robin so each
      batch interval advances all barcodes together.
    - ``flat``: all source FASTQs (across any input barcodes) are pooled
      into a single sequence of chunks emitted into ``target_dir``.
    - ``barcoded``: source FASTQs are pooled and chunks are dealt
      round-robin across ``output_barcodes`` directories named via
      ``output_barcode_pattern``.
    """
    rpf = config.reads_per_output
    # When only the structure is changing (no explicit --reads-per-file),
    # use a default chunk size large enough that small fixtures still
    # produce at least one file per output barcode.  We override this
    # below once the total read count is known.
    needs_reshape = config.output_structure != "preserve"

    # Group entries by input barcode (or by None for singleplex).
    barcode_order: List[Optional[str]] = []
    groups: dict = {}
    for entry in raw_entries:
        bc = entry.barcode
        if bc not in groups:
            barcode_order.append(bc)
            groups[bc] = {
                "input_target_dir": (
                    config.target_dir / bc if bc else config.target_dir
                ),
                "fastq_files": [],
                "other_entries": [],
            }
        if entry.source is not None and _is_fastq_file(entry.source):
            groups[bc]["fastq_files"].append(entry.source)
        else:
            groups[bc]["other_entries"].append(entry)

    rechunked: List[FileEntry] = []

    # Non-FASTQ files pass through first (preserve mode only).
    if not needs_reshape:
        for bc in barcode_order:
            rechunked.extend(groups[bc]["other_entries"])

    if needs_reshape:
        # Pool all FASTQ sources across input barcodes into a single
        # ordered sequence.  The output layout is computed entirely
        # from output_structure / output_barcodes.
        pooled_sources: List[Path] = []
        for bc in barcode_order:
            pooled_sources.extend(groups[bc]["fastq_files"])
        if not pooled_sources:
            return rechunked
        rechunked.extend(_plan_reshape(pooled_sources, config, rpf))
        return rechunked

    # Preserve mode: build per-input-barcode chunk lists, then
    # interleave round-robin.
    from itertools import zip_longest

    assert rpf is not None  # preserve+rechunk path requires reads_per_output
    per_barcode_chunks: List[List[FileEntry]] = []
    for bc in barcode_order:
        grp = groups[bc]
        target_dir = grp["input_target_dir"]
        sources = grp["fastq_files"]
        per_barcode_chunks.append(
            _plan_preserve_chunks(sources, target_dir, bc, rpf, config)
        )

    for chunk_group in zip_longest(*per_barcode_chunks):
        for entry in chunk_group:
            if entry is not None:
                rechunked.append(entry)

    return rechunked


def _plan_preserve_chunks(
    sources: List[Path],
    target_dir: Path,
    barcode: Optional[str],
    rpf: int,
    config: ReplayConfig,
) -> List[FileEntry]:
    """Plan rechunked entries for one input barcode group (preserve mode)."""
    fastq_files = [(src, *count_reads_with_offsets(src, rpf)) for src in sources]
    total_reads = sum(c for _, c, _ in fastq_files)
    if total_reads == 0:
        return []

    n_output = math.ceil(total_reads / rpf)
    first_source = fastq_files[0][0]
    ext = _get_fastq_extension(first_source)
    source_paths = [src for src, _, _ in fastq_files]
    chunk_offsets = _build_chunk_offsets(fastq_files, rpf)

    entries: List[FileEntry] = []
    for chunk_idx in range(n_output):
        src_file_idx, byte_offset = chunk_offsets.get(chunk_idx, (0, None))
        chunk_source = (
            source_paths[src_file_idx] if byte_offset is not None else first_source
        )
        stem = (
            config.output_file_prefix
            if config.output_file_prefix
            else _fastq_stem(chunk_source)
        )
        filename = f"{stem}_chunk_{chunk_idx:04d}{ext}"
        entries.append(
            FileEntry(
                source=(
                    source_paths[src_file_idx] if byte_offset is not None else None
                ),
                target=target_dir / filename,
                operation="rechunk",
                barcode=barcode,
                read_count=min(rpf, total_reads - chunk_idx * rpf),
                file_index=chunk_idx,
                source_files=source_paths,
                source_offset=byte_offset,
            )
        )
    return entries


def _plan_reshape(
    pooled_sources: List[Path], config: ReplayConfig, rpf: Optional[int]
) -> List[FileEntry]:
    """Plan chunks for a non-preserve output layout from pooled sources."""
    assert rpf is not None  # enforced by ReplayConfig validation
    fastq_files = [(src, *count_reads_with_offsets(src, rpf)) for src in pooled_sources]
    total_reads = sum(c for _, c, _ in fastq_files)
    if total_reads == 0:
        return []

    n_output = math.ceil(total_reads / rpf)
    first_source = pooled_sources[0]
    ext = _get_fastq_extension(first_source)
    chunk_offsets = _build_chunk_offsets(fastq_files, rpf)

    if config.output_structure == "flat":
        per_chunk_barcodes: List[Optional[str]] = [None] * n_output
        per_chunk_target_dirs: List[Path] = [config.target_dir] * n_output
        per_chunk_file_idx: List[int] = list(range(n_output))
    else:  # "barcoded"
        n_bc = config.output_barcodes
        per_chunk_barcodes = []
        per_chunk_target_dirs = []
        per_chunk_file_idx = []
        per_bc_counter = [0] * n_bc
        for chunk_idx in range(n_output):
            bc_idx = chunk_idx % n_bc
            bc_name = config.output_barcode_pattern.format(bc_idx + 1)
            per_chunk_barcodes.append(bc_name)
            per_chunk_target_dirs.append(config.target_dir / bc_name)
            per_chunk_file_idx.append(per_bc_counter[bc_idx])
            per_bc_counter[bc_idx] += 1

    entries: List[FileEntry] = []
    for chunk_idx in range(n_output):
        src_file_idx, byte_offset = chunk_offsets.get(chunk_idx, (0, None))
        chunk_source = (
            pooled_sources[src_file_idx] if byte_offset is not None else first_source
        )
        stem = (
            config.output_file_prefix
            if config.output_file_prefix
            else _fastq_stem(chunk_source)
        )
        filename = f"{stem}_chunk_{per_chunk_file_idx[chunk_idx]:04d}{ext}"
        entries.append(
            FileEntry(
                source=(
                    pooled_sources[src_file_idx] if byte_offset is not None else None
                ),
                target=per_chunk_target_dirs[chunk_idx] / filename,
                operation="rechunk",
                barcode=per_chunk_barcodes[chunk_idx],
                read_count=min(rpf, total_reads - chunk_idx * rpf),
                file_index=per_chunk_file_idx[chunk_idx],
                source_files=pooled_sources,
                source_offset=byte_offset,
            )
        )
    return entries


def _build_chunk_offsets(fastq_files: list, rpf: int) -> dict:
    """Map global chunk indices to (source_file_index, byte_offset).

    Given the per-file read counts and per-file offset lists produced
    by ``count_reads_with_offsets``, this computes a mapping from each
    output chunk index to the source file index and the byte offset
    within that file where reading should begin.

    When a chunk boundary falls inside a source file at a position
    that was recorded by ``count_reads_with_offsets``, the offset is
    stored directly.  When the boundary falls at a non-aligned
    position within a file (because the file boundary did not align
    with the chunk boundary), no offset is stored for that chunk and
    the executor falls back to sequential skipping.

    Args:
        fastq_files: List of (path, read_count, offsets) tuples.
        rpf: Reads per output file (chunk size).

    Returns:
        Dict mapping chunk_idx -> (source_file_index, byte_offset).
    """
    mapping: dict = {}
    cumulative_reads = 0

    for file_idx, (_, file_reads, file_offsets) in enumerate(fastq_files):
        # file_offsets[k] is the byte offset where read (k * rpf)
        # starts within this file.
        for local_chunk_idx, byte_offset in enumerate(file_offsets):
            local_read_start = local_chunk_idx * rpf
            if local_read_start >= file_reads:
                break
            global_read_start = cumulative_reads + local_read_start
            global_chunk_idx = global_read_start // rpf

            # Only store if the global chunk starts exactly at this
            # local boundary (i.e. cumulative reads are chunk-aligned).
            if global_read_start == global_chunk_idx * rpf:
                if global_chunk_idx not in mapping:
                    mapping[global_chunk_idx] = (file_idx, byte_offset)

        cumulative_reads += file_reads

    return mapping


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
        per_genome_reads = distribute_reads(total_reads, [1.0 / n_genomes] * n_genomes)

    rpf = config.reads_per_file
    ext = ".fastq.gz" if config.output_format == "fastq.gz" else ".fastq"

    entries: List[FileEntry] = []

    if config.structure == "multiplex":
        entries = _generate_multiplex_entries(
            config, genomes, per_genome_reads, rpf, ext
        )
    elif config.mix_reads:
        entries = _generate_mixed_entries(config, genomes, per_genome_reads, rpf, ext)
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
    """Generate entries with each genome in a separate barcode directory.

    Entries are emitted in *stratified rounds*: within round *r* every
    barcode that still has chunks contributes exactly one entry, in a
    shuffled order; only once round *r* is exhausted does any barcode
    begin its (r+1)th chunk. This guarantees no draining -- consumers
    see early reads for every sample -- while avoiding the strict
    tick-tock (bc01, bc02, bc03, bc01, bc02, bc03, ...) that is
    unrepresentative of real sequencer output. The shuffle is seeded
    deterministically off the target path so unit tests are
    reproducible.

    Without this stratification, default ``batch_size=1`` would write
    every file for barcode01 before any file appears for barcode02,
    which breaks downstream watch-directory consumers.
    """
    per_barcode: List[List[FileEntry]] = []
    for idx, genome_path in enumerate(genomes):
        barcode = f"barcode{idx + 1:02d}"
        barcode_dir = config.target_dir / barcode
        stem = _genome_stem(genome_path)
        n_files = max(1, math.ceil(per_genome_reads[idx] / rpf))
        remaining = per_genome_reads[idx]
        bucket: List[FileEntry] = []
        for fi in range(n_files):
            chunk = min(rpf, remaining)
            remaining -= chunk
            filename = f"{stem}_reads_{fi:04d}{ext}"
            bucket.append(
                FileEntry(
                    target=barcode_dir / filename,
                    operation="generate",
                    genome=genome_path,
                    read_count=chunk,
                    file_index=fi,
                    barcode=barcode,
                )
            )
        per_barcode.append(bucket)

    seed = zlib.adler32(str(config.target_dir).encode("utf-8"))
    rng = random.Random(seed)
    entries: List[FileEntry] = []
    max_files = max((len(b) for b in per_barcode), default=0)
    for fi in range(max_files):
        round_indices = [i for i, b in enumerate(per_barcode) if fi < len(b)]
        rng.shuffle(round_indices)
        for i in round_indices:
            entries.append(per_barcode[i][fi])
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
        list(config.abundances) if config.abundances else [1.0 / n_genomes] * n_genomes
    )

    entries: List[FileEntry] = []
    remaining = total_reads
    for fi in range(total_files):
        chunk = min(rpf, remaining)
        remaining -= chunk
        # Distribute this file's reads across genomes
        per_genome = distribute_reads(chunk, weights)
        genome_reads = [(g, n) for g, n in zip(genomes, per_genome) if n > 0]
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
