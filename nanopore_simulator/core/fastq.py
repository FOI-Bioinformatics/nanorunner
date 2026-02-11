"""FASTQ read/write/count utilities for rechunking replay files."""

import gzip
from pathlib import Path
from typing import Iterator, List, Tuple


def count_fastq_reads(path: Path) -> int:
    """Count reads in a FASTQ file (plain or gzipped).

    Each FASTQ record consists of exactly 4 lines, so the read count
    is ``line_count // 4``.

    Args:
        path: Path to a ``.fastq`` or ``.fastq.gz`` file.

    Returns:
        Number of reads in the file.

    Raises:
        ValueError: If the line count is not a multiple of 4.
    """
    open_fn = gzip.open if str(path).endswith(".gz") else open
    mode = "rt" if str(path).endswith(".gz") else "r"

    line_count = 0
    with open_fn(path, mode) as fh:
        for _ in fh:
            line_count += 1

    if line_count % 4 != 0:
        raise ValueError(
            f"Malformed FASTQ: {path} has {line_count} lines "
            f"(not a multiple of 4)"
        )

    return line_count // 4


def iter_fastq_reads(
    path: Path,
) -> Iterator[Tuple[str, str, str, str]]:
    """Yield FASTQ records as (header, sequence, separator, quality) tuples.

    Lines are stripped of trailing whitespace. Each tuple preserves the
    complete record content so it can be written back verbatim.

    Args:
        path: Path to a ``.fastq`` or ``.fastq.gz`` file.

    Yields:
        4-tuples of stripped lines for each read.
    """
    open_fn = gzip.open if str(path).endswith(".gz") else open
    mode = "rt" if str(path).endswith(".gz") else "r"

    with open_fn(path, mode) as fh:
        while True:
            header = fh.readline()
            if not header:
                break
            seq = fh.readline()
            sep = fh.readline()
            qual = fh.readline()
            if not qual:
                break
            yield (
                header.rstrip("\n\r"),
                seq.rstrip("\n\r"),
                sep.rstrip("\n\r"),
                qual.rstrip("\n\r"),
            )


def write_fastq_reads(
    reads: List[Tuple[str, str, str, str]], path: Path
) -> None:
    """Write FASTQ records to a file.

    Each record is a (header, sequence, separator, quality) tuple.
    Output is gzipped when the path ends in ``.gz``.

    Args:
        reads: List of 4-tuples representing FASTQ records.
        path: Output file path.
    """
    open_fn = gzip.open if str(path).endswith(".gz") else open
    mode = "wt" if str(path).endswith(".gz") else "w"

    with open_fn(path, mode) as fh:
        for header, seq, sep, qual in reads:
            fh.write(f"{header}\n{seq}\n{sep}\n{qual}\n")
