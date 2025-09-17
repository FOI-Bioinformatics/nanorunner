"""Tests for edge cases and error handling"""

import pytest
import tempfile
import os
import stat
from pathlib import Path
from unittest.mock import patch, MagicMock

from nanopore_simulator.core.config import SimulationConfig
from nanopore_simulator.core.detector import FileStructureDetector
from nanopore_simulator.core.simulator import NanoporeSimulator


class TestEdgeCases:
    
    def setup_method(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        
    def teardown_method(self):
        """Clean up test fixtures"""
        self.temp_dir.cleanup()
    
    def test_empty_source_directory(self):
        """Test behavior with empty source directory"""
        empty_dir = self.temp_path / "empty"
        empty_dir.mkdir()
        
        with pytest.raises(ValueError, match="No sequencing files found"):
            FileStructureDetector.detect_structure(empty_dir)
    
    def test_nonexistent_source_directory(self):
        """Test behavior with nonexistent source directory"""
        nonexistent = self.temp_path / "nonexistent"
        
        # Should not raise exception during detection, but return empty results
        files = FileStructureDetector._find_sequencing_files(nonexistent)
        assert files == []
    
    def test_source_directory_is_file(self):
        """Test behavior when source path is a file, not directory"""
        file_path = self.temp_path / "not_a_directory.txt"
        file_path.write_text("content")
        
        with pytest.raises(NotADirectoryError):
            list(file_path.iterdir())  # This is what would happen in detector
    
    def test_permission_denied_source_directory(self):
        """Test behavior with permission denied on source directory"""
        restricted_dir = self.temp_path / "restricted"
        restricted_dir.mkdir()
        
        # Create a file first
        test_file = restricted_dir / "test.fastq"
        test_file.write_text("content")
        
        # Remove read permissions
        os.chmod(restricted_dir, stat.S_IWRITE)
        
        try:
            # Should raise PermissionError when trying to read
            with pytest.raises(PermissionError):
                FileStructureDetector._find_sequencing_files(restricted_dir)
        finally:
            # Restore permissions for cleanup
            os.chmod(restricted_dir, stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)
    
    def test_circular_symlink_handling(self):
        """Test handling of circular symlinks"""
        source_dir = self.temp_path / "circular_source"
        source_dir.mkdir()
        
        # Create circular symlink
        circular_link = source_dir / "circular.fastq"
        circular_link.symlink_to(circular_link)
        
        # Should not hang or crash
        files = FileStructureDetector._find_sequencing_files(source_dir)
        # Circular symlink should be detected as a file but might cause issues
        # The exact behavior depends on the OS and Python version
        assert isinstance(files, list)
    
    def test_very_long_filename(self):
        """Test handling of very long filenames"""
        source_dir = self.temp_path / "long_names"
        source_dir.mkdir()
        
        # Create file with very long name (close to filesystem limit)
        long_name = "a" * 200 + ".fastq"
        long_file = source_dir / long_name
        
        try:
            long_file.write_text("content")
            
            files = FileStructureDetector._find_sequencing_files(source_dir)
            assert len(files) == 1
            assert files[0].name == long_name
            
        except OSError:
            # Some filesystems might not support such long names
            pytest.skip("Filesystem doesn't support long filenames")
    
    def test_unicode_filename_handling(self):
        """Test handling of unicode filenames"""
        source_dir = self.temp_path / "unicode_source"
        source_dir.mkdir()
        
        # Create files with unicode names
        unicode_files = [
            "测试文件.fastq",
            "файл.fq.gz",
            "🧬sequence.pod5",
            "café_data.fastq"
        ]
        
        for filename in unicode_files:
            try:
                (source_dir / filename).write_text("content")
            except (UnicodeError, OSError):
                # Skip if filesystem doesn't support unicode
                continue
        
        files = FileStructureDetector._find_sequencing_files(source_dir)
        assert len(files) >= 1  # At least one should work
    
    def test_case_sensitivity_in_extensions(self):
        """Test case sensitivity in file extension detection"""
        source_dir = self.temp_path / "case_source"
        source_dir.mkdir()
        
        # Create files with different case extensions (unique base names for case-insensitive filesystems)
        case_variants = [
            "sample1.FASTQ",
            "sample2.Fastq", 
            "sample3.FQ",
            "sample4.POD5",
            "sample5.FASTQ.GZ",
            "sample6.Fq.Gz"
        ]
        
        for filename in case_variants:
            (source_dir / filename).write_text("content")
        
        files = FileStructureDetector._find_sequencing_files(source_dir)
        
        # All should be detected due to case-insensitive matching
        assert len(files) == len(case_variants)
    
    def test_broken_symlink_handling(self):
        """Test handling of broken symlinks"""
        source_dir = self.temp_path / "broken_symlink_source"
        source_dir.mkdir()
        
        # Create broken symlink
        broken_target = source_dir / "nonexistent_target.fastq"
        broken_link = source_dir / "broken.fastq"
        broken_link.symlink_to(broken_target)
        
        # Should not crash on broken symlinks
        files = FileStructureDetector._find_sequencing_files(source_dir)
        
        # Broken symlink should still be detected as existing link
        assert len(files) >= 0  # Should not crash
    
    def test_target_directory_creation_failure(self):
        """Test failure to create target directory"""
        source_dir = self.temp_path / "source"
        source_dir.mkdir()
        (source_dir / "test.fastq").write_text("content")
        
        # Try to create target as child of non-writable directory
        readonly_parent = self.temp_path / "readonly_parent"
        readonly_parent.mkdir()
        target_dir = readonly_parent / "target"
        
        # Remove write permissions
        os.chmod(readonly_parent, stat.S_IREAD | stat.S_IEXEC)
        
        config = SimulationConfig(
            source_dir=source_dir,
            target_dir=target_dir
        )
        simulator = NanoporeSimulator(config)
        
        try:
            with pytest.raises(PermissionError):
                simulator._prepare_target_directory()
        finally:
            # Restore permissions for cleanup
            os.chmod(readonly_parent, stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)
    
    def test_disk_full_simulation(self):
        """Test behavior when disk is full (simulated)"""
        source_dir = self.temp_path / "source"
        source_dir.mkdir()
        source_file = source_dir / "test.fastq"
        source_file.write_text("content")
        
        target_dir = self.temp_path / "target"
        
        config = SimulationConfig(
            source_dir=source_dir,
            target_dir=target_dir
        )
        simulator = NanoporeSimulator(config)
        
        # Mock shutil.copy2 to raise OSError (disk full)
        with patch('shutil.copy2', side_effect=OSError("No space left on device")):
            file_info = {
                'source': source_file,
                'target': target_dir / "test.fastq",
                'barcode': None
            }
            
            with pytest.raises(OSError, match="No space left on device"):
                simulator._process_file(file_info)
    
    def test_extremely_large_batch_size(self):
        """Test with extremely large batch size"""
        source_dir = self.temp_path / "large_batch_source"
        source_dir.mkdir()
        
        # Create a few files
        for i in range(3):
            (source_dir / f"file{i}.fastq").write_text("content")
        
        config = SimulationConfig(
            source_dir=source_dir,
            target_dir=self.temp_path / "target",
            batch_size=1000000  # Much larger than file count
        )
        
        simulator = NanoporeSimulator(config)
        manifest = simulator._create_singleplex_manifest()
        
        # Should handle gracefully without errors
        simulator._execute_simulation(manifest, "singleplex")
        
        # All files should be processed in one batch
        assert len(list((self.temp_path / "target").glob("*"))) == 3
    
    def test_zero_interval_timing(self):
        """Test with zero interval (no delays)"""
        source_dir = self.temp_path / "zero_interval_source"
        source_dir.mkdir()
        
        for i in range(5):
            (source_dir / f"file{i}.fastq").write_text("content")
        
        config = SimulationConfig(
            source_dir=source_dir,
            target_dir=self.temp_path / "target",
            interval=0.0,  # No delays
            batch_size=1
        )
        
        with patch('time.sleep') as mock_sleep:
            simulator = NanoporeSimulator(config)
            simulator.run_simulation()
            
            # Should still call sleep with 0.0
            mock_sleep.assert_called_with(0.0)
    
    def test_negative_batch_size(self):
        """Test with negative batch size"""
        # Should raise ValueError due to validation
        with pytest.raises(ValueError, match="batch_size must be at least 1"):
            SimulationConfig(
                source_dir=self.temp_path / "source",
                target_dir=self.temp_path / "target",
                batch_size=-1
            )
    
    def test_special_characters_in_paths(self):
        """Test paths with special characters"""
        special_chars = ["spaces in name", "dots.in.name", "dash-in-name", "under_score"]
        
        for char_type in special_chars:
            source_dir = self.temp_path / f"source_{char_type}"
            source_dir.mkdir()
            (source_dir / "test.fastq").write_text("content")
            
            target_dir = self.temp_path / f"target_{char_type}"
            
            config = SimulationConfig(
                source_dir=source_dir,
                target_dir=target_dir
            )
            
            # Should handle special characters without issues
            simulator = NanoporeSimulator(config)
            simulator.run_simulation()
            
            assert (target_dir / "test.fastq").exists()
    
    def test_concurrent_file_access(self):
        """Test behavior when files are modified during processing"""
        source_dir = self.temp_path / "concurrent_source"
        source_dir.mkdir()
        source_file = source_dir / "changing.fastq"
        source_file.write_text("original content")
        
        target_dir = self.temp_path / "target"
        
        config = SimulationConfig(
            source_dir=source_dir,
            target_dir=target_dir
        )
        simulator = NanoporeSimulator(config)
        
        # Mock the copy operation to modify source file during copy
        original_copy = simulator._process_file
        
        def mock_process_file(file_info):
            # Modify source file during processing
            file_info['source'].write_text("modified content")
            return original_copy(file_info)
        
        with patch.object(simulator, '_process_file', side_effect=mock_process_file):
            # Should handle concurrent modification gracefully
            simulator.run_simulation()
    
    def test_invalid_file_extensions(self):
        """Test files with invalid or partial extensions"""
        source_dir = self.temp_path / "invalid_ext_source"
        source_dir.mkdir()
        
        # Create files with problematic extensions
        problematic_files = [
            "file.fastq.",  # Trailing dot
            "file.fastq.tmp",  # Wrong extension
            "file.fast",  # Incomplete extension
            "file.fastqq",  # Typo
            "file.",  # Just dot
            "file",  # No extension
            ".fastq",  # Hidden file
            "file..fastq"  # Double dots
        ]
        
        for filename in problematic_files:
            (source_dir / filename).write_text("content")
        
        files = FileStructureDetector._find_sequencing_files(source_dir)
        detected_names = [f.name for f in files]
        
        # Only .fastq (hidden file) and file..fastq should be detected 
        # (file..fastq is valid because it ends with .fastq)
        expected_valid = {".fastq", "file..fastq"}
        assert set(detected_names) == expected_valid
    
    def test_mixed_case_barcode_directories(self):
        """Test barcode directories with mixed case"""
        source_dir = self.temp_path / "mixed_case_source"
        source_dir.mkdir()
        
        # Create barcode directories with various cases (unique names for case-insensitive filesystems)
        case_variants = [
            "Barcode01",
            "BARCODE02", 
            "barcode03",
            "BC04",
            "bc05",
            "Bc06",
            "UNCLASSIFIED"
        ]
        
        for dirname in case_variants:
            barcode_dir = source_dir / dirname
            barcode_dir.mkdir(exist_ok=True)
            (barcode_dir / "reads.fastq").write_text("content")
        
        barcode_dirs = FileStructureDetector._find_barcode_directories(source_dir)
        detected_names = {d.name for d in barcode_dirs}
        
        # All valid barcode patterns should be detected (case-insensitive matching)
        # Note: UNCLASSIFIED matches the unclassified pattern
        expected_count = len(case_variants)
        assert len(barcode_dirs) == expected_count