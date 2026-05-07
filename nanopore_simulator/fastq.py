"""FASTQ read/write/count utilities.

Provides functions for counting, iterating, and writing FASTQ records.
Supports both plain text and gzip-compressed files.  Also contains
shared I/O helpers used by ``executor`` and ``generators``.
"""

import gzip
import os
import shutil
from pathlib import Path
from typing import Iterator, List, Optional, Tuple


def atomic_tmp_path(target: Path) -> Path:
    """Return a temporary sibling path for atomic writes."""
    return target.parent / f".{target.name}.tmp"


def atomic_move(tmp: Path, target: Path) -> None:
    """Move a freshly-written tmp file into its final target path.

    On the same filesystem this is an atomic rename (POSIX rename(2)).
    Across filesystems -- the case ``Path.rename`` raises
    ``OSError: [Errno 18] Cross-device link`` -- this falls back to a
    copy-then-delete via ``shutil.move``. Cross-device atomicity is
    impossible by definition, so the best we can do is "the file
    appears at target if the move succeeded; otherwise it does not".

    Surfaces commonly hit by this fallback include macOS Docker
    bind-mounts, NFS-backed scratch directories, and writes from a
    container's overlay layer to a host-mounted volume. Without the
    fallback, nanorunner would crash on those layouts even when the
    user has enough space and permissions to land the file.
    """
    try:
        os.replace(str(tmp), str(target))
    except OSError as exc:
        # errno 18 is EXDEV (cross-device link). Other OSErrors are
        # genuine -- propagate so callers can clean up the tmp file.
        if exc.errno != 18:
            raise
        shutil.move(str(tmp), str(target))


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
            f"Malformed FASTQ: {path} has {line_count} lines " f"(not a multiple of 4)"
        )

    return line_count // 4


def count_reads_with_offsets(path: Path, chunk_size: int) -> Tuple[int, List[int]]:
    """Count reads and record byte offsets at chunk boundaries.

    Iterates through the FASTQ file once, counting reads and recording
    the byte offset at every ``chunk_size`` reads.  The offsets list
    contains one entry per chunk boundary (including offset 0 for the
    first chunk).

    For gzip files the offsets represent decompressed-stream positions.
    Since gzip does not support random access, the executor falls back
    to sequential reading for compressed files regardless of offsets.

    Args:
        path: Path to a .fastq or .fastq.gz file.
        chunk_size: Number of reads per chunk.

    Returns:
        A (read_count, offsets) tuple.  ``offsets[i]`` is the byte
        offset where chunk *i* begins.

    Raises:
        ValueError: If the line count is not a multiple of 4.
    """
    is_gz = str(path).endswith(".gz")
    open_fn = gzip.open if is_gz else open
    mode = "rt" if is_gz else "r"

    offsets: List[int] = [0]
    read_count = 0

    with open_fn(path, mode) as fh:
        while True:
            if read_count > 0 and read_count % chunk_size == 0:
                offsets.append(fh.tell())
            header = fh.readline()
            if not header:
                break
            fh.readline()  # sequence
            fh.readline()  # separator
            qual = fh.readline()
            if not qual:
                break
            read_count += 1

    return read_count, offsets


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
                str(header).rstrip("\n\r"),
                str(seq).rstrip("\n\r"),
                str(sep).rstrip("\n\r"),
                str(qual).rstrip("\n\r"),
            )


def iter_reads_from_offset(
    path: Path, offset: int
) -> Iterator[Tuple[str, str, str, str]]:
    """Yield FASTQ records starting from a byte offset.

    Identical to ``iter_reads`` but seeks to *offset* before reading.
    For plain-text files this avoids scanning reads that precede the
    desired position.  For gzip files the decompressor must still
    process the stream sequentially, but the caller can use the offset
    recorded during manifest building to seek within the decompressed
    stream.

    Args:
        path: Path to a .fastq or .fastq.gz file.
        offset: Byte offset (in the text stream) to seek to.

    Yields:
        4-tuples of stripped lines for each read.
    """
    is_gz = str(path).endswith(".gz")
    open_fn = gzip.open if is_gz else open
    mode = "rt" if is_gz else "r"

    with open_fn(path, mode) as fh:
        if offset > 0:
            fh.seek(offset)
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
                str(header).rstrip("\n\r"),
                str(seq).rstrip("\n\r"),
                str(sep).rstrip("\n\r"),
                str(qual).rstrip("\n\r"),
            )


def write_reads(
    reads: List[Tuple[str, str, str, str]],
    path: Path,
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
                f"{header}\n{seq}\n{sep}\n{qual}\n" for header, seq, sep, qual in reads
            )
        )
