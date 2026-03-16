"""FASTQ read/write/count utilities.

Provides functions for counting, iterating, and writing FASTQ records.
Supports both plain text and gzip-compressed files.
"""

import gzip
from pathlib import Path
from typing import Iterator, List, Optional, Tuple


def count_reads(path: Path) -> int:
    """Count reads in a FASTQ file (plain or gzipped).

    Each FASTQ record consists of exactly 4 lines, so the read count
    is line_count // 4.

    Args:
        path: Path to a .fastq or .fastq.gz file.

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


def iter_reads(path: Path) -> Iterator[Tuple[str, str, str, str]]:
    """Yield FASTQ records as (header, sequence, separator, quality) tuples.

    Lines are stripped of trailing whitespace. Each tuple preserves the
    complete record content so it can be written back verbatim.

    Args:
        path: Path to a .fastq or .fastq.gz file.

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


def write_reads(
    reads: List[Tuple[str, str, str, str]], path: Path,
    compress: Optional[bool] = None,
) -> None:
    """Write FASTQ records to a file.

    Each record is a (header, sequence, separator, quality) tuple.
    Output is gzipped when the path ends in .gz, unless *compress*
    is explicitly set.

    Args:
        reads: List of 4-tuples representing FASTQ records.
        path: Output file path.
        compress: Force gzip compression. If None, infer from path suffix.
    """
    use_gz = compress if compress is not None else str(path).endswith(".gz")
    if use_gz:
        fh = gzip.open(path, "wt", compresslevel=1)
    else:
        fh = open(path, "w")

    with fh:
        fh.write(
            "".join(
                f"{header}\n{seq}\n{sep}\n{qual}\n"
                for header, seq, sep, qual in reads
            )
        )
