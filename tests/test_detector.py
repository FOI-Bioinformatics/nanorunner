"""Tests for file structure detector"""

import pytest
import tempfile
from pathlib import Path

from nanopore_simulator.core.detector import FileStructureDetector


class TestFileStructureDetector:
    
    def test_detect_singleplex_structure(self):
        """Test detection of singleplex structure"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Create singleplex files
            (tmpdir / "sample1.fastq").touch()
            (tmpdir / "sample2.fastq.gz").touch()
            (tmpdir / "sample3.pod5").touch()
            
            structure = FileStructureDetector.detect_structure(tmpdir)
            assert structure == "singleplex"
    
    def test_detect_multiplex_structure(self):
        """Test detection of multiplex structure"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Create multiplex structure
            barcode01 = tmpdir / "barcode01"
            barcode01.mkdir()
            (barcode01 / "reads.fastq").touch()
            
            barcode02 = tmpdir / "barcode02"
            barcode02.mkdir()
            (barcode02 / "reads.fastq.gz").touch()
            
            structure = FileStructureDetector.detect_structure(tmpdir)
            assert structure == "multiplex"
    
    def test_is_sequencing_file(self):
        """Test sequencing file detection"""
        test_files = [
            ("sample.fastq", True),
            ("sample.fq", True),
            ("sample.fastq.gz", True),
            ("sample.fq.gz", True),
            ("sample.pod5", True),
            ("sample.txt", False),
            ("sample.bam", False),
        ]
        
        for filename, expected in test_files:
            file_path = Path(filename)
            result = FileStructureDetector._is_sequencing_file(file_path)
            assert result == expected, f"Failed for {filename}"
    
    def test_is_barcode_directory(self):
        """Test barcode directory name detection"""
        test_names = [
            ("barcode01", True),
            ("barcode123", True),
            ("BC01", True),
            ("bc05", True),
            ("unclassified", True),
            ("sample", False),
            ("fastq_pass", False),
        ]
        
        for dirname, expected in test_names:
            result = FileStructureDetector._is_barcode_directory(dirname)
            assert result == expected, f"Failed for {dirname}"
    
    def test_no_sequencing_files_error(self):
        """Test error when no sequencing files found"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Create non-sequencing files
            (tmpdir / "readme.txt").touch()
            (tmpdir / "config.json").touch()
            
            with pytest.raises(ValueError, match="No sequencing files found"):
                FileStructureDetector.detect_structure(tmpdir)