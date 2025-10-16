"""File structure detection for nanopore sequencing data"""

import re
import logging
from pathlib import Path
from typing import List


class FileStructureDetector:
    """Detects the structure of source data (singleplex vs multiplex)"""

    BARCODE_PATTERNS = [r"^barcode\d+$", r"^BC\d+$", r"^bc\d+$", r"^unclassified$"]

    SUPPORTED_EXTENSIONS = {".fastq", ".fq", ".fastq.gz", ".fq.gz", ".pod5"}

    @classmethod
    def detect_structure(cls, source_dir: Path) -> str:
        """
        Detect if source directory contains singleplex or multiplex data

        Returns:
            "singleplex": Files directly in source directory
            "multiplex": Files organized in barcode subdirectories
        """
        source_dir = Path(source_dir)

        # Check for files directly in source directory
        direct_files = cls._find_sequencing_files(source_dir)

        # Check for barcode subdirectories
        barcode_dirs = cls._find_barcode_directories(source_dir)

        if barcode_dirs and not direct_files:
            return "multiplex"
        elif direct_files and not barcode_dirs:
            return "singleplex"
        elif barcode_dirs and direct_files:
            logging.warning(
                "Mixed structure detected - files in both root and barcode directories"
            )
            return "multiplex"  # Prefer multiplex interpretation
        else:
            raise ValueError(f"No sequencing files found in {source_dir}")

    @classmethod
    def _find_sequencing_files(cls, directory: Path) -> List[Path]:
        """Find sequencing files (FASTQ/POD5) in a directory"""
        files: List[Path] = []
        if not directory.exists():
            return files

        for file_path in directory.iterdir():
            if file_path.is_file() and cls._is_sequencing_file(file_path):
                files.append(file_path)
        return files

    @classmethod
    def _find_barcode_directories(cls, source_dir: Path) -> List[Path]:
        """Find barcode subdirectories containing sequencing files"""
        barcode_dirs = []

        for item in source_dir.iterdir():
            if item.is_dir() and cls._is_barcode_directory(item.name):
                # Check if this directory contains sequencing files
                if cls._find_sequencing_files(item):
                    barcode_dirs.append(item)

        return barcode_dirs

    @classmethod
    def _is_barcode_directory(cls, dirname: str) -> bool:
        """Check if directory name matches barcode patterns"""
        for pattern in cls.BARCODE_PATTERNS:
            if re.match(pattern, dirname, re.IGNORECASE):
                return True
        return False

    @classmethod
    def _is_sequencing_file(cls, file_path: Path) -> bool:
        """Check if file is a supported sequencing file"""
        # Check compound extensions like .fastq.gz
        name_lower = file_path.name.lower()
        for ext in cls.SUPPORTED_EXTENSIONS:
            if name_lower.endswith(ext):
                return True
        return False
