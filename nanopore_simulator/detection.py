"""File structure detection for nanopore sequencing data.

Provides module-level functions to determine whether a source directory
contains singleplex data (files directly in the root) or multiplex
data (files organized in barcode subdirectories).
"""

import logging
import re
from pathlib import Path
from typing import List

_BARCODE_PATTERNS = [
    r"^barcode\d+$",
    r"^BC\d+$",
    r"^bc\d+$",
    r"^unclassified$",
]

_SUPPORTED_EXTENSIONS = {".fastq", ".fq", ".fastq.gz", ".fq.gz", ".pod5"}


def detect_structure(source_dir: Path) -> str:
    """Detect whether source directory contains singleplex or multiplex data.

    Args:
        source_dir: Path to the source directory.

    Returns:
        "singleplex" if files are directly in the source directory,
        "multiplex" if files are organized in barcode subdirectories.

    Raises:
        ValueError: If no sequencing files are found anywhere.
    """
    source_dir = Path(source_dir)
    direct_files = find_sequencing_files(source_dir)
    barcode_dirs = find_barcode_dirs(source_dir)

    if barcode_dirs and not direct_files:
        return "multiplex"
    elif direct_files and not barcode_dirs:
        return "singleplex"
    elif barcode_dirs and direct_files:
        logging.warning(
            "Mixed structure detected - files in both root and barcode " "directories"
        )
        return "multiplex"
    else:
        raise ValueError(f"No sequencing files found in {source_dir}")


def find_sequencing_files(directory: Path) -> List[Path]:
    """Find sequencing files (FASTQ/POD5) in a directory.

    Only searches the immediate directory, not subdirectories.

    Args:
        directory: Path to search for sequencing files.

    Returns:
        List of paths to sequencing files found.
    """
    files: List[Path] = []
    if not directory.exists():
        return files

    for file_path in directory.iterdir():
        if file_path.is_file() and _is_sequencing_file(file_path):
            files.append(file_path)
    return files


def find_barcode_dirs(source_dir: Path) -> List[Path]:
    """Find barcode subdirectories that contain sequencing files.

    Args:
        source_dir: Parent directory to search for barcode subdirectories.

    Returns:
        List of paths to barcode directories containing sequencing files.
    """
    barcode_dirs: List[Path] = []

    for item in source_dir.iterdir():
        if item.is_dir() and is_barcode_dir(item.name):
            if find_sequencing_files(item):
                barcode_dirs.append(item)

    return barcode_dirs


def is_barcode_dir(dirname: str) -> bool:
    """Check if a directory name matches known barcode patterns.

    Recognized patterns: barcode01, BC01, bc01, unclassified.
    Matching is case-insensitive.

    Args:
        dirname: Directory name to check.

    Returns:
        True if the name matches a barcode pattern.
    """
    for pattern in _BARCODE_PATTERNS:
        if re.match(pattern, dirname, re.IGNORECASE):
            return True
    return False


def _is_sequencing_file(file_path: Path) -> bool:
    """Check if a file has a supported sequencing file extension.

    Handles compound extensions like .fastq.gz by checking the
    lowercased filename suffix.
    """
    name_lower = file_path.name.lower()
    for ext in _SUPPORTED_EXTENSIONS:
        if name_lower.endswith(ext):
            return True
    return False
