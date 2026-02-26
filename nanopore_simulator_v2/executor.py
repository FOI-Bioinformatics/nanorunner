"""File executor for producing individual output files.

Handles the three operations defined by ``FileEntry``:

- **copy**: Copy a source file to the target path.
- **link**: Create a symbolic link at the target path.
- **generate**: Produce a simulated FASTQ file via a ReadGenerator.

Each function ensures parent directories exist before writing.
"""

import logging
import shutil
from pathlib import Path
from typing import Optional

from nanopore_simulator_v2.generators import GenomeInput, ReadGenerator
from nanopore_simulator_v2.manifest import FileEntry

logger = logging.getLogger(__name__)


def execute_entry(
    entry: FileEntry,
    generator: Optional[ReadGenerator] = None,
) -> Path:
    """Produce one output file according to the entry specification.

    Args:
        entry: A FileEntry describing the operation.
        generator: ReadGenerator instance (required for generate operations).

    Returns:
        Path to the produced file.

    Raises:
        FileNotFoundError: If the source file does not exist for copy/link.
        ValueError: If operation is "generate" and no generator is provided,
            or if the operation is unrecognized.
    """
    entry.target.parent.mkdir(parents=True, exist_ok=True)

    if entry.operation == "copy":
        return _copy_file(entry.source, entry.target)
    elif entry.operation == "link":
        return _link_file(entry.source, entry.target)
    elif entry.operation == "generate":
        if generator is None:
            raise ValueError("generator required for generate operation")
        return _generate_file(entry, generator)
    else:
        raise ValueError(f"Unknown operation: {entry.operation}")


# -------------------------------------------------------------------
# Internal helpers
# -------------------------------------------------------------------


def _copy_file(source: Path, target: Path) -> Path:
    """Copy a source file to target, preserving metadata."""
    if not source.exists():
        raise FileNotFoundError(f"Source file not found: {source}")
    shutil.copy2(source, target)
    return target


def _link_file(source: Path, target: Path) -> Path:
    """Create a symbolic link at target pointing to source."""
    if not source.exists():
        raise FileNotFoundError(f"Source file not found: {source}")
    if target.exists() or target.is_symlink():
        target.unlink()
    target.symlink_to(source.absolute())
    return target


def _generate_file(entry: FileEntry, generator: ReadGenerator) -> Path:
    """Generate a FASTQ file via the given ReadGenerator.

    For mixed-mode entries (``mixed_genome_reads`` is set), reads from
    multiple genomes are generated in memory, shuffled, and written
    to a single output file.

    For standard entries, the generator's ``generate_reads`` method
    writes one output file.

    Args:
        entry: A generate-mode FileEntry.
        generator: The ReadGenerator to use.

    Returns:
        Path to the generated output file.
    """
    if entry.mixed_genome_reads:
        return _generate_mixed_file(entry, generator)

    genome = GenomeInput(
        fasta_path=entry.genome,
        barcode=entry.barcode,
    )
    output_dir = entry.target.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = generator.generate_reads(
        genome, output_dir, entry.file_index,
        num_reads=entry.read_count,
    )
    return output_path


def _generate_mixed_file(
    entry: FileEntry, generator: ReadGenerator
) -> Path:
    """Generate a mixed-reads file from multiple genomes.

    Reads from each genome are generated in memory, combined, shuffled,
    and written to the target path.
    """
    import random
    from nanopore_simulator_v2.fastq import write_reads

    all_reads = []
    for genome_path, count in entry.mixed_genome_reads:
        genome = GenomeInput(fasta_path=genome_path)
        reads = generator.generate_reads_in_memory(genome, count)
        all_reads.extend(reads)

    random.shuffle(all_reads)

    output_dir = entry.target.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    write_reads(all_reads, entry.target)
    return entry.target
