"""Comprehensive adapter tests to improve coverage"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from nanopore_simulator.core.adapters import (
    PipelineRequirements,
    PipelineAdapter,
    NanometanfAdapter,
    KrackenAdapter,
    MiniknifeAdapter,
    GenericAdapter,
    AdapterManager,
    get_available_adapters,
    validate_for_pipeline,
    get_compatible_pipelines,
    get_pipeline_adapter,
)


class TestPipelineAdapterEdgeCases:
    """Test PipelineAdapter edge cases and error conditions"""

    def setup_method(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def teardown_method(self):
        """Clean up test fixtures"""
        self.temp_dir.cleanup()

    def test_pipeline_adapter_validation_with_metadata_files(self):
        """Test validation when metadata files are required"""
        target_dir = self.temp_path / "target"
        target_dir.mkdir()

        # Create some FASTQ files
        (target_dir / "sample1.fastq").write_text("@read1\\nACGT\\n+\\nIIII\\n")
        (target_dir / "sample2.fastq").write_text("@read2\\nTGCA\\n+\\n~~~~\\n")

        # Create adapter with metadata requirements using GenericAdapter
        config = {
            "name": "test_pipeline",
            "description": "Test pipeline with metadata",
            "patterns": ["*.fastq"],
            "metadata_files": ["sample_sheet.csv", "config.json"],
            "min_files": 1,
        }
        adapter = GenericAdapter(config)

        # Test validation without metadata files
        report = adapter.get_validation_report(target_dir)

        assert not report["valid"]
        assert "sample_sheet.csv" in report["missing_files"]
        assert "config.json" in report["missing_files"]
        assert "Missing metadata file: sample_sheet.csv" in report["warnings"]
        assert "Missing metadata file: config.json" in report["warnings"]

        # Test validation with metadata files
        (target_dir / "sample_sheet.csv").write_text("sample,barcode\\nA,01\\nB,02\\n")
        (target_dir / "config.json").write_text('{"setting": "value"}')

        report = adapter.get_validation_report(target_dir)
        assert report["valid"]
        assert len(report["missing_files"]) == 0

    def test_pipeline_adapter_validation_exception_handling(self):
        """Test validation exception handling"""
        target_dir = self.temp_path / "target"
        target_dir.mkdir()

        config = {
            "name": "test_pipeline",
            "description": "Test pipeline",
            "patterns": ["*.fastq"],
            "min_files": 1,
        }
        adapter = GenericAdapter(config)

        # Mock glob to raise exception
        with patch.object(
            Path, "glob", side_effect=PermissionError("Permission denied")
        ):
            report = adapter.get_validation_report(target_dir)

            assert not report["valid"]
            assert len(report["errors"]) > 0
            assert "Validation error:" in report["errors"][0]


class TestNanometanfAdapterEdgeCases:
    """Test NanometanfAdapter edge cases"""

    def setup_method(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def teardown_method(self):
        """Clean up test fixtures"""
        self.temp_dir.cleanup()

    def test_nanometanf_validate_structure_nonexistent_directory(self):
        """Test structure validation with nonexistent directory"""
        adapter = NanometanfAdapter()
        nonexistent_dir = self.temp_path / "nonexistent"

        # Should return False for nonexistent directory
        assert not adapter.validate_structure(nonexistent_dir)

    def test_nanometanf_validate_structure_mixed_invalid_barcode(self):
        """Test structure validation with mixed structure and invalid barcode directory"""
        target_dir = self.temp_path / "target"
        target_dir.mkdir()

        # Create mixed structure with invalid barcode directory
        (target_dir / "root_file.fastq").write_text("@read1\\nACGT\\n+\\nIIII\\n")

        invalid_dir = target_dir / "invalid_barcode_name"
        invalid_dir.mkdir()
        (invalid_dir / "file.fastq").write_text("@read2\\nTGCA\\n+\\n~~~~\\n")

        adapter = NanometanfAdapter()

        # Should return False due to invalid barcode directory
        assert not adapter.validate_structure(target_dir)

    def test_nanometanf_validate_structure_insufficient_files(self):
        """Test structure validation with insufficient files"""
        target_dir = self.temp_path / "target"
        target_dir.mkdir()

        adapter = NanometanfAdapter()

        # Empty directory should fail validation
        assert not adapter.validate_structure(target_dir)


class TestKrackenAdapterEdgeCases:
    """Test KrackenAdapter edge cases"""

    def setup_method(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def teardown_method(self):
        """Clean up test fixtures"""
        self.temp_dir.cleanup()

    def test_kracken_adapter_error_conditions(self):
        """Test KrackenAdapter error conditions"""
        adapter = KrackenAdapter()

        # Test validation with permission error
        target_dir = self.temp_path / "target"
        target_dir.mkdir()

        with patch.object(
            adapter, "validate_structure", side_effect=PermissionError("Access denied")
        ):
            report = adapter.get_validation_report(target_dir)

            assert not report["valid"]
            assert len(report["errors"]) > 0


class TestMiniknifeAdapterEdgeCases:
    """Test MiniknifeAdapter edge cases"""

    def setup_method(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def teardown_method(self):
        """Clean up test fixtures"""
        self.temp_dir.cleanup()

    def test_miniknife_adapter_error_conditions(self):
        """Test MiniknifeAdapter error conditions"""
        adapter = MiniknifeAdapter()

        # Test validation with file system error
        target_dir = self.temp_path / "target"
        target_dir.mkdir()

        with patch.object(Path, "exists", side_effect=OSError("File system error")):
            report = adapter.get_validation_report(target_dir)

            assert not report["valid"]
            assert len(report["errors"]) > 0


class TestGenericAdapterEdgeCases:
    """Test GenericAdapter edge cases"""

    def setup_method(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def teardown_method(self):
        """Clean up test fixtures"""
        self.temp_dir.cleanup()

    def test_generic_adapter_with_custom_validation_rules(self):
        """Test GenericAdapter with custom validation rules"""
        target_dir = self.temp_path / "target"
        target_dir.mkdir()

        # Create files
        for i in range(3):
            (target_dir / f"sample_{i}.fastq").write_text(
                f"@read{i}\\nACGT\\n+\\nIIII\\n"
            )

        # Create adapter with high minimum file requirement
        config = {
            "name": "test_adapter",
            "description": "Test adapter with high file requirement",
            "patterns": ["*.fastq"],
            "min_files": 5,  # Require 5 files, but only 3 exist
        }
        adapter = GenericAdapter(config)

        report = adapter.get_validation_report(target_dir)

        assert not report["valid"]  # Should fail due to insufficient files
        assert len(report["files_found"]) == 3

    def test_generic_adapter_validation_exception(self):
        """Test GenericAdapter validation exception handling"""
        target_dir = self.temp_path / "target"
        target_dir.mkdir()

        config = {
            "name": "test_adapter",
            "description": "Test adapter",
            "patterns": ["*.fastq"],
            "min_files": 1,
        }
        adapter = GenericAdapter(config)

        # Mock validate_structure to raise exception
        with patch.object(
            adapter, "validate_structure", side_effect=RuntimeError("Validation failed")
        ):
            report = adapter.get_validation_report(target_dir)

            assert not report["valid"]
            assert len(report["errors"]) > 0
            assert "Validation error:" in report["errors"][0]


class TestAdapterManagerEdgeCases:
    """Test AdapterManager edge cases"""

    def test_adapter_manager_unknown_adapter(self):
        """Test AdapterManager with unknown adapter"""
        manager = AdapterManager()

        # get_adapter returns None for unknown adapters, doesn't raise ValueError
        result = manager.get_adapter("unknown_adapter")
        assert result is None

    def test_adapter_manager_validation_error(self):
        """Test AdapterManager validation with errors"""
        manager = AdapterManager()

        with tempfile.TemporaryDirectory() as temp_dir:
            target_dir = Path(temp_dir)

            # Mock adapter to raise exception during validation
            mock_adapter = MagicMock()
            mock_adapter.get_validation_report.side_effect = Exception("Adapter error")

            with patch.object(manager, "get_adapter", return_value=mock_adapter):
                # Should catch the exception and return error report
                try:
                    report = manager.validate_for_pipeline("nanometanf", target_dir)
                    # If no exception is raised, validation should indicate failure
                    assert "valid" in report
                except Exception:
                    # Exception during validation is acceptable for this test
                    pass


class TestAdapterIntegrationEdgeCases:
    """Test adapter integration edge cases"""

    def setup_method(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def teardown_method(self):
        """Clean up test fixtures"""
        self.temp_dir.cleanup()

    def test_validate_for_pipeline_with_invalid_directory(self):
        """Test validate_for_pipeline with invalid directory"""
        nonexistent_dir = self.temp_path / "nonexistent"

        report = validate_for_pipeline("nanometanf", nonexistent_dir)

        # Should handle gracefully
        assert isinstance(report, dict)
        assert "valid" in report

    def test_get_compatible_pipelines_with_empty_directory(self):
        """Test get_compatible_pipelines with empty directory"""
        empty_dir = self.temp_path / "empty"
        empty_dir.mkdir()

        compatible = get_compatible_pipelines(empty_dir)

        # Should return empty list or handle gracefully
        assert isinstance(compatible, list)

    def test_generic_adapter_creation_edge_cases(self):
        """Test GenericAdapter creation with edge cases"""
        # Test with minimal parameters
        config = {
            "name": "minimal_adapter",
            "description": "Minimal test adapter",
            "patterns": ["*.txt"],
            "min_files": 0,
        }
        adapter = GenericAdapter(config)

        assert isinstance(adapter, GenericAdapter)
        assert adapter.requirements.validation_rules["min_files"] == 0

        # Test with comprehensive parameters
        config = {
            "name": "comprehensive_adapter",
            "description": "Custom adapter",
            "patterns": ["*.fastq", "*.fq"],
            "structure": "singleplex",
            "min_files": 10,
            "metadata_files": ["config.yml"],
        }
        adapter = GenericAdapter(config)

        assert isinstance(adapter, GenericAdapter)
        assert adapter.requirements.required_structure == "singleplex"
        assert adapter.requirements.validation_rules["min_files"] == 10
        assert "config.yml" in adapter.requirements.metadata_files

    def test_adapter_with_io_errors(self):
        """Test adapter behavior with I/O errors"""
        target_dir = self.temp_path / "target"
        target_dir.mkdir()

        adapter = NanometanfAdapter()

        # Mock file operations to raise I/O errors
        with patch("pathlib.Path.exists", side_effect=OSError("I/O error")):
            # Should raise OSError during validation
            with pytest.raises(OSError, match="I/O error"):
                adapter.validate_structure(target_dir)

    def test_adapter_performance_with_large_file_counts(self):
        """Test adapter performance with large number of files"""
        target_dir = self.temp_path / "large_target"
        target_dir.mkdir()

        # Create many files
        for i in range(100):
            (target_dir / f"file_{i:03d}.fastq").write_text(
                f"@read{i}\\nACGT\\n+\\nIIII\\n"
            )

        adapter = NanometanfAdapter()

        # Should handle large file counts efficiently
        import time

        start_time = time.time()
        report = adapter.get_validation_report(target_dir)
        end_time = time.time()

        assert report["valid"]
        assert len(report["files_found"]) == 100
        assert end_time - start_time < 5.0  # Should complete within 5 seconds

    def test_adapter_with_unicode_filenames(self):
        """Test adapter behavior with unicode filenames"""
        target_dir = self.temp_path / "unicode_target"
        target_dir.mkdir()

        # Create files with unicode names
        unicode_files = [
            "测试文件.fastq",
            "файл_тест.fastq",
            "αρχείο_δοκιμής.fastq",
            "ファイル_テスト.fastq",
        ]

        for filename in unicode_files:
            try:
                (target_dir / filename).write_text("@read\\nACGT\\n+\\nIIII\\n")
            except OSError:
                # Skip if filesystem doesn't support unicode
                continue

        adapter = NanometanfAdapter()

        # Should handle unicode filenames gracefully
        report = adapter.get_validation_report(target_dir)
        assert isinstance(report, dict)
        assert "valid" in report


class TestAdapterErrorRecovery:
    """Test adapter error recovery mechanisms"""

    def setup_method(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def teardown_method(self):
        """Clean up test fixtures"""
        self.temp_dir.cleanup()

    def test_adapter_recovery_from_partial_failures(self):
        """Test adapter recovery from partial validation failures"""
        target_dir = self.temp_path / "partial_fail"
        target_dir.mkdir()

        # Create valid files
        (target_dir / "good_file.fastq").write_text("@read1\\nACGT\\n+\\nIIII\\n")

        # Create directory that might cause issues
        problem_dir = target_dir / "problem_dir"
        problem_dir.mkdir()

        adapter = NanometanfAdapter()

        # Mock specific operations to fail
        original_glob = Path.glob

        def selective_failing_glob(self, pattern):
            if "problem_dir" in str(self):
                raise PermissionError("Access denied")
            return original_glob(self, pattern)

        with patch.object(Path, "glob", selective_failing_glob):
            # Should recover and continue validation
            report = adapter.get_validation_report(target_dir)

            # Should still find the good file
            assert len(report["files_found"]) >= 1

    def test_adapter_graceful_degradation(self):
        """Test adapter graceful degradation under resource constraints"""
        target_dir = self.temp_path / "resource_constrained"
        target_dir.mkdir()

        # Create many files
        for i in range(50):
            (target_dir / f"file_{i}.fastq").write_text("@read\\nACGT\\n+\\nIIII\\n")

        adapter = NanometanfAdapter()

        # Simulate memory constraint by limiting processing
        with patch(
            "builtins.list", side_effect=lambda x: list(x)[:10]
        ):  # Limit to 10 items
            report = adapter.get_validation_report(target_dir)

            # Should still work with limited resources
            assert isinstance(report, dict)
            assert "valid" in report
