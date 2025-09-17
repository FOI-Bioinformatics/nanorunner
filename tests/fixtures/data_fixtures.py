"""Test data fixtures and creation utilities.

This module provides comprehensive test data creation utilities for NanoRunner
testing, including realistic FASTQ/POD5 files, directory structures, and
performance testing datasets.
"""

import gzip
import pytest
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from unittest.mock import MagicMock


def create_test_fastq_content(reads: int = 10, read_length: int = 1000, 
                            quality_score: str = "I") -> str:
    """Create realistic FASTQ file content for testing.
    
    Args:
        reads: Number of reads to generate
        read_length: Length of each read sequence
        quality_score: Quality score character to use
        
    Returns:
        String containing complete FASTQ content
    """
    sequences = []
    bases = "ATCG"
    
    for i in range(reads):
        # Generate realistic read header
        header = f"@read_{i:06d} length={read_length}"
        
        # Generate random-like sequence
        sequence = "".join(bases[j % 4] for j in range(i, i + read_length))
        
        # Quality scores
        qualities = quality_score * read_length
        
        sequences.append(f"{header}\\n{sequence}\\n+\\n{qualities}")
    
    return "\\n".join(sequences) + "\\n"


def create_test_pod5_content(signals: int = 1000) -> bytes:
    """Create mock POD5 file content for testing.
    
    Args:
        signals: Number of signal samples to simulate
        
    Returns:
        Bytes representing mock POD5 data
    """
    # Mock POD5 header and signal data
    header = b"POD5\\x00\\x01\\x00\\x00"  # Mock header
    signal_data = bytes(range(signals % 256))  # Mock signal data
    return header + signal_data


def create_realistic_fastq(file_path: Path, reads: int = 100, 
                         compressed: bool = False) -> Path:
    """Create a realistic FASTQ file for testing.
    
    Args:
        file_path: Path where the file should be created
        reads: Number of reads to include
        compressed: Whether to gzip compress the file
        
    Returns:
        Path to the created file
    """
    content = create_test_fastq_content(reads=reads)
    
    if compressed:
        with gzip.open(file_path, 'wt') as f:
            f.write(content)
    else:
        file_path.write_text(content)
    
    return file_path


def create_compressed_fastq(file_path: Path, reads: int = 100) -> Path:
    """Create a compressed FASTQ file for testing.
    
    Args:
        file_path: Path where the file should be created (should end with .gz)
        reads: Number of reads to include
        
    Returns:
        Path to the created file
    """
    return create_realistic_fastq(file_path, reads=reads, compressed=True)


@pytest.fixture
def singleplex_test_data(tmp_path):
    """Create realistic singleplex test data structure.
    
    Creates:
        - sample1.fastq (100 reads)
        - sample2.fastq.gz (200 reads, compressed)
        - sample3.pod5 (mock POD5 data)
        - sample4.fq (50 reads)
        
    Returns:
        Path to directory containing singleplex data
    """
    source_dir = tmp_path / "singleplex_data"
    source_dir.mkdir()
    
    # Create various file types and sizes
    create_realistic_fastq(source_dir / "sample1.fastq", reads=100)
    create_compressed_fastq(source_dir / "sample2.fastq.gz", reads=200)
    (source_dir / "sample3.pod5").write_bytes(create_test_pod5_content(signals=1000))
    create_realistic_fastq(source_dir / "sample4.fq", reads=50)
    
    return source_dir


@pytest.fixture
def multiplex_test_data(tmp_path):
    """Create realistic multiplex test data structure.
    
    Creates directory structure:
        barcode01/
            ├── reads_1.fastq (100 reads)
            └── reads_2.fastq.gz (150 reads)
        barcode02/
            ├── reads.fastq (80 reads)
            └── signals.pod5 (mock POD5)
        BC03/
            └── data.fq (120 reads)
        unclassified/
            └── unassigned.fastq (30 reads)
            
    Returns:
        Path to directory containing multiplex data
    """
    source_dir = tmp_path / "multiplex_data"
    source_dir.mkdir()
    
    # Barcode 01 - multiple files
    bc01_dir = source_dir / "barcode01"
    bc01_dir.mkdir()
    create_realistic_fastq(bc01_dir / "reads_1.fastq", reads=100)
    create_compressed_fastq(bc01_dir / "reads_2.fastq.gz", reads=150)
    
    # Barcode 02 - mixed file types
    bc02_dir = source_dir / "barcode02"
    bc02_dir.mkdir()
    create_realistic_fastq(bc02_dir / "reads.fastq", reads=80)
    (bc02_dir / "signals.pod5").write_bytes(create_test_pod5_content(signals=800))
    
    # BC03 - different naming convention
    bc03_dir = source_dir / "BC03"
    bc03_dir.mkdir()
    create_realistic_fastq(bc03_dir / "data.fq", reads=120)
    
    # Unclassified reads
    unclass_dir = source_dir / "unclassified"
    unclass_dir.mkdir()
    create_realistic_fastq(unclass_dir / "unassigned.fastq", reads=30)
    
    return source_dir


@pytest.fixture
def mixed_test_data(tmp_path):
    """Create mixed structure test data (both singleplex and multiplex).
    
    Creates:
        - direct_file.fastq (in root)
        - barcode01/reads.fastq (in subdirectory)
        - invalid_dir/file.txt (non-barcode directory)
        
    Returns:
        Path to directory containing mixed data
    """
    source_dir = tmp_path / "mixed_data"
    source_dir.mkdir()
    
    # Direct file in root
    create_realistic_fastq(source_dir / "direct_file.fastq", reads=50)
    
    # Barcode directory
    bc_dir = source_dir / "barcode01"
    bc_dir.mkdir()
    create_realistic_fastq(bc_dir / "reads.fastq", reads=75)
    
    # Invalid directory (not a barcode)
    invalid_dir = source_dir / "invalid_dir"
    invalid_dir.mkdir()
    (invalid_dir / "file.txt").write_text("Not a FASTQ file")
    
    return source_dir


@pytest.fixture
def empty_test_data(tmp_path):
    """Create empty directory structure for testing edge cases.
    
    Returns:
        Path to empty directory
    """
    empty_dir = tmp_path / "empty_data"
    empty_dir.mkdir()
    return empty_dir


@pytest.fixture
def large_test_dataset(tmp_path):
    """Create large dataset for performance testing.
    
    Creates 100 files with varying sizes for performance testing.
    Use only for tests marked with @pytest.mark.slow.
    
    Returns:
        Path to directory containing large dataset
    """
    source_dir = tmp_path / "large_dataset"
    source_dir.mkdir()
    
    # Create files with varying sizes
    for i in range(100):
        filename = f"large_file_{i:03d}.fastq"
        reads = 50 + (i % 200)  # 50-250 reads per file
        create_realistic_fastq(source_dir / filename, reads=reads)
    
    return source_dir


@pytest.fixture
def small_test_dataset(tmp_path):
    """Create small dataset for quick testing.
    
    Creates 5 small files for fast test execution.
    
    Returns:
        Path to directory containing small dataset
    """
    source_dir = tmp_path / "small_dataset"
    source_dir.mkdir()
    
    for i in range(5):
        filename = f"small_file_{i}.fastq"
        create_realistic_fastq(source_dir / filename, reads=10)
    
    return source_dir


@pytest.fixture
def unicode_test_data(tmp_path):
    """Create test data with unicode filenames for internationalization testing.
    
    Creates files with various unicode characters in names.
    
    Returns:
        Path to directory containing unicode filename test data
    """
    source_dir = tmp_path / "unicode_data"
    source_dir.mkdir()
    
    unicode_names = [
        "测试文件.fastq",           # Chinese
        "файл_тест.fastq",         # Russian
        "αρχείο_δοκιμής.fastq",   # Greek
        "ファイル_テスト.fastq",    # Japanese
        "archivø_test.fastq",      # Danish
    ]
    
    for name in unicode_names:
        try:
            create_realistic_fastq(source_dir / name, reads=20)
        except (OSError, UnicodeError):
            # Skip if filesystem doesn't support unicode
            continue
    
    return source_dir


@pytest.fixture
def edge_case_filenames(tmp_path):
    """Create test data with edge case filenames.
    
    Creates files with challenging names for robust testing.
    
    Returns:
        Path to directory containing edge case filenames
    """
    source_dir = tmp_path / "edge_case_names"
    source_dir.mkdir()
    
    edge_names = [
        "file with spaces.fastq",
        "file-with-hyphens.fastq",
        "file_with_underscores.fastq",
        "file.with.dots.fastq",
        "UPPERCASE.FASTQ",
        "123numeric_start.fastq",
    ]
    
    for name in edge_names:
        try:
            create_realistic_fastq(source_dir / name, reads=15)
        except OSError:
            # Skip problematic names on some filesystems
            continue
    
    return source_dir


class DataTestManager:
    """Utility class for managing test data lifecycle and cleanup."""
    
    def __init__(self):
        self._temp_dirs: List[Path] = []
        self._created_files: List[Path] = []
    
    def create_temp_structure(self, structure_type: str = "singleplex", 
                            file_count: int = 5) -> Path:
        """Create temporary test structure with automatic cleanup.
        
        Args:
            structure_type: Type of structure ('singleplex', 'multiplex', 'mixed')
            file_count: Number of files to create
            
        Returns:
            Path to created structure
        """
        temp_dir = Path(tempfile.mkdtemp(prefix=f"nanorun_test_{structure_type}_"))
        self._temp_dirs.append(temp_dir)
        
        if structure_type == "singleplex":
            return self._create_singleplex_structure(temp_dir, file_count)
        elif structure_type == "multiplex":
            return self._create_multiplex_structure(temp_dir, file_count)
        elif structure_type == "mixed":
            return self._create_mixed_structure(temp_dir, file_count)
        else:
            raise ValueError(f"Unknown structure type: {structure_type}")
    
    def _create_singleplex_structure(self, base_dir: Path, file_count: int) -> Path:
        """Create singleplex structure."""
        for i in range(file_count):
            filename = f"sample_{i:03d}.fastq"
            create_realistic_fastq(base_dir / filename, reads=50)
        return base_dir
    
    def _create_multiplex_structure(self, base_dir: Path, file_count: int) -> Path:
        """Create multiplex structure."""
        barcodes = ["barcode01", "barcode02", "BC03", "unclassified"]
        files_per_barcode = max(1, file_count // len(barcodes))
        
        for barcode in barcodes:
            bc_dir = base_dir / barcode
            bc_dir.mkdir()
            for i in range(files_per_barcode):
                filename = f"reads_{i}.fastq"
                create_realistic_fastq(bc_dir / filename, reads=30)
        
        return base_dir
    
    def _create_mixed_structure(self, base_dir: Path, file_count: int) -> Path:
        """Create mixed structure."""
        # Some files in root
        for i in range(file_count // 2):
            filename = f"root_file_{i}.fastq"
            create_realistic_fastq(base_dir / filename, reads=40)
        
        # Some files in barcode directories
        bc_dir = base_dir / "barcode01"
        bc_dir.mkdir()
        for i in range(file_count // 2):
            filename = f"bc_file_{i}.fastq"
            create_realistic_fastq(bc_dir / filename, reads=35)
        
        return base_dir
    
    def cleanup(self):
        """Clean up all created temporary structures."""
        import shutil
        
        for temp_dir in self._temp_dirs:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
        
        for file_path in self._created_files:
            if file_path.exists():
                file_path.unlink()
        
        self._temp_dirs.clear()
        self._created_files.clear()


@pytest.fixture
def test_data_manager():
    """Provide a test data manager with automatic cleanup."""
    manager = TestDataManager()
    yield manager
    manager.cleanup()


# Performance testing utilities
def create_performance_dataset(size: str = "medium") -> Path:
    """Create performance testing dataset.
    
    Args:
        size: Dataset size ('small', 'medium', 'large', 'xlarge')
        
    Returns:
        Path to created dataset
    """
    size_configs = {
        "small": {"files": 10, "reads_per_file": 50},
        "medium": {"files": 100, "reads_per_file": 100},
        "large": {"files": 500, "reads_per_file": 200},
        "xlarge": {"files": 1000, "reads_per_file": 500},
    }
    
    if size not in size_configs:
        raise ValueError(f"Unknown size: {size}. Choose from {list(size_configs.keys())}")
    
    config = size_configs[size]
    temp_dir = Path(tempfile.mkdtemp(prefix=f"nanorun_perf_{size}_"))
    
    for i in range(config["files"]):
        filename = f"perf_file_{i:04d}.fastq"
        create_realistic_fastq(temp_dir / filename, reads=config["reads_per_file"])
    
    return temp_dir


# Data validation utilities
def validate_test_structure(path: Path, expected_structure: str) -> bool:
    """Validate that a test data structure matches expectations.
    
    Args:
        path: Path to validate
        expected_structure: Expected structure type
        
    Returns:
        True if structure is valid
    """
    if expected_structure == "singleplex":
        return _validate_singleplex_structure(path)
    elif expected_structure == "multiplex":
        return _validate_multiplex_structure(path)
    elif expected_structure == "mixed":
        return _validate_mixed_structure(path)
    else:
        return False


def _validate_singleplex_structure(path: Path) -> bool:
    """Validate singleplex structure has files in root."""
    fastq_files = list(path.glob("*.fastq")) + list(path.glob("*.fq"))
    return len(fastq_files) > 0 and not any(d.is_dir() for d in path.iterdir() if d.name.startswith("barcode"))


def _validate_multiplex_structure(path: Path) -> bool:
    """Validate multiplex structure has barcode directories."""
    barcode_dirs = [d for d in path.iterdir() if d.is_dir() and 
                   (d.name.startswith("barcode") or d.name.startswith("BC") or d.name == "unclassified")]
    return len(barcode_dirs) > 0


def _validate_mixed_structure(path: Path) -> bool:
    """Validate mixed structure has both root files and barcode directories."""
    root_files = list(path.glob("*.fastq")) + list(path.glob("*.fq"))
    barcode_dirs = [d for d in path.iterdir() if d.is_dir() and d.name.startswith("barcode")]
    return len(root_files) > 0 and len(barcode_dirs) > 0