"""Tests for nanopore simulator core functionality"""

import pytest
import tempfile
import time
import logging
from pathlib import Path
from unittest.mock import patch, MagicMock

from nanopore_simulator.core.config import SimulationConfig
from nanopore_simulator.core.simulator import NanoporeSimulator


class TestNanoporeSimulator:

    def setup_method(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

        # Create test source structure
        self.source_dir = self.temp_path / "source"
        self.target_dir = self.temp_path / "target"
        self.source_dir.mkdir()

    def teardown_method(self):
        """Clean up test fixtures"""
        self.temp_dir.cleanup()

    def test_simulator_initialization(self):
        """Test simulator initialization"""
        config = SimulationConfig(
            source_dir=self.source_dir, target_dir=self.target_dir
        )

        simulator = NanoporeSimulator(config)

        assert simulator.config == config
        assert simulator.logger is not None
        assert isinstance(simulator.logger, logging.Logger)

    def test_prepare_target_directory(self):
        """Test target directory preparation"""
        config = SimulationConfig(
            source_dir=self.source_dir, target_dir=self.target_dir
        )
        simulator = NanoporeSimulator(config)

        # Target should not exist initially
        assert not self.target_dir.exists()

        simulator._prepare_target_directory()

        # Target should exist after preparation
        assert self.target_dir.exists()
        assert self.target_dir.is_dir()

    def test_create_singleplex_manifest(self):
        """Test singleplex manifest creation"""
        # Create test files
        (self.source_dir / "sample1.fastq").write_text("test")
        (self.source_dir / "sample2.pod5").write_text("test")

        config = SimulationConfig(
            source_dir=self.source_dir, target_dir=self.target_dir
        )
        simulator = NanoporeSimulator(config)

        manifest = simulator._create_singleplex_manifest()

        assert len(manifest) == 2

        # Check first file
        file1 = manifest[0]
        assert file1["source"].name in ["sample1.fastq", "sample2.pod5"]
        assert file1["target"].parent == self.target_dir
        assert file1["barcode"] is None

        # Check second file
        file2 = manifest[1]
        assert file2["source"].name in ["sample1.fastq", "sample2.pod5"]
        assert file2["target"].parent == self.target_dir
        assert file2["barcode"] is None

    def test_create_multiplex_manifest(self):
        """Test multiplex manifest creation"""
        # Create barcode directories with files
        barcode01 = self.source_dir / "barcode01"
        barcode02 = self.source_dir / "barcode02"
        barcode01.mkdir()
        barcode02.mkdir()

        (barcode01 / "reads1.fastq").write_text("test")
        (barcode01 / "reads2.fastq.gz").write_text("test")
        (barcode02 / "reads.pod5").write_text("test")

        config = SimulationConfig(
            source_dir=self.source_dir, target_dir=self.target_dir
        )
        simulator = NanoporeSimulator(config)

        manifest = simulator._create_multiplex_manifest()

        assert len(manifest) == 3

        # Check barcode assignment
        barcodes = [item["barcode"] for item in manifest]
        assert "barcode01" in barcodes
        assert "barcode02" in barcodes

        # Check target paths include barcode directories
        for item in manifest:
            assert item["barcode"] in str(item["target"])

    def test_process_file_copy_operation(self):
        """Test file copy operation"""
        # Create source file
        source_file = self.source_dir / "test.fastq"
        source_file.write_text("test content")

        config = SimulationConfig(
            source_dir=self.source_dir, target_dir=self.target_dir, operation="copy"
        )
        simulator = NanoporeSimulator(config)

        file_info = {
            "source": source_file,
            "target": self.target_dir / "test.fastq",
            "barcode": None,
        }

        simulator._process_file(file_info)

        # Check file was copied
        target_file = self.target_dir / "test.fastq"
        assert target_file.exists()
        assert target_file.read_text() == "test content"

        # Original should still exist
        assert source_file.exists()

    def test_process_file_link_operation(self):
        """Test file link operation"""
        # Create source file
        source_file = self.source_dir / "test.fastq"
        source_file.write_text("test content")

        config = SimulationConfig(
            source_dir=self.source_dir, target_dir=self.target_dir, operation="link"
        )
        simulator = NanoporeSimulator(config)

        file_info = {
            "source": source_file,
            "target": self.target_dir / "test.fastq",
            "barcode": None,
        }

        simulator._process_file(file_info)

        # Check symlink was created
        target_file = self.target_dir / "test.fastq"
        assert target_file.exists()
        assert target_file.is_symlink()
        assert target_file.read_text() == "test content"

    def test_process_file_with_barcode(self):
        """Test file processing with barcode subdirectory"""
        # Create source file
        source_file = self.source_dir / "test.fastq"
        source_file.write_text("test content")

        config = SimulationConfig(
            source_dir=self.source_dir, target_dir=self.target_dir
        )
        simulator = NanoporeSimulator(config)

        file_info = {
            "source": source_file,
            "target": self.target_dir / "barcode01" / "test.fastq",
            "barcode": "barcode01",
        }

        simulator._process_file(file_info)

        # Check barcode directory was created
        barcode_dir = self.target_dir / "barcode01"
        assert barcode_dir.exists()
        assert barcode_dir.is_dir()

        # Check file was processed
        target_file = barcode_dir / "test.fastq"
        assert target_file.exists()
        assert target_file.read_text() == "test content"

    def test_process_file_invalid_operation(self):
        """Test error handling for invalid operation"""
        # Should raise ValueError during config validation
        with pytest.raises(ValueError, match="operation must be 'copy' or 'link'"):
            SimulationConfig(
                source_dir=self.source_dir,
                target_dir=self.target_dir,
                operation="invalid_op",
            )

    @patch("time.sleep")
    def test_execute_simulation_timing(self, mock_sleep):
        """Test simulation execution with timing"""
        # Create test files
        (self.source_dir / "file1.fastq").write_text("test")
        (self.source_dir / "file2.fastq").write_text("test")
        (self.source_dir / "file3.fastq").write_text("test")

        config = SimulationConfig(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            interval=2.0,
            batch_size=2,
        )
        simulator = NanoporeSimulator(config)

        # Create manifest
        manifest = [
            {
                "source": self.source_dir / "file1.fastq",
                "target": self.target_dir / "file1.fastq",
                "barcode": None,
            },
            {
                "source": self.source_dir / "file2.fastq",
                "target": self.target_dir / "file2.fastq",
                "barcode": None,
            },
            {
                "source": self.source_dir / "file3.fastq",
                "target": self.target_dir / "file3.fastq",
                "barcode": None,
            },
        ]

        simulator._execute_simulation(manifest, "singleplex")

        # Should sleep between batches (2 batches total, so 1 sleep)
        assert mock_sleep.call_count == 1
        mock_sleep.assert_called_with(2.0)

    def test_run_simulation_singleplex(self):
        """Test complete singleplex simulation"""
        # Create test files
        (self.source_dir / "sample1.fastq").write_text("content1")
        (self.source_dir / "sample2.pod5").write_text("content2")

        config = SimulationConfig(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            interval=0.1,  # Short interval for testing
        )
        simulator = NanoporeSimulator(config)

        simulator.run_simulation()

        # Check files were processed
        assert (self.target_dir / "sample1.fastq").exists()
        assert (self.target_dir / "sample2.pod5").exists()
        assert (self.target_dir / "sample1.fastq").read_text() == "content1"
        assert (self.target_dir / "sample2.pod5").read_text() == "content2"

    def test_run_simulation_multiplex(self):
        """Test complete multiplex simulation"""
        # Create barcode structure
        barcode01 = self.source_dir / "barcode01"
        barcode01.mkdir()
        (barcode01 / "reads.fastq").write_text("bc01_content")

        unclassified = self.source_dir / "unclassified"
        unclassified.mkdir()
        (unclassified / "unassigned.fastq").write_text("unclass_content")

        config = SimulationConfig(
            source_dir=self.source_dir, target_dir=self.target_dir, interval=0.1
        )
        simulator = NanoporeSimulator(config)

        simulator.run_simulation()

        # Check structure was recreated
        assert (self.target_dir / "barcode01" / "reads.fastq").exists()
        assert (self.target_dir / "unclassified" / "unassigned.fastq").exists()

        # Check content
        assert (
            self.target_dir / "barcode01" / "reads.fastq"
        ).read_text() == "bc01_content"
        assert (
            self.target_dir / "unclassified" / "unassigned.fastq"
        ).read_text() == "unclass_content"

    def test_run_simulation_forced_structure(self):
        """Test simulation with forced structure"""
        # Create files that could be either structure
        (self.source_dir / "sample.fastq").write_text("content")

        config = SimulationConfig(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            force_structure="singleplex",
            interval=0.1,
        )
        simulator = NanoporeSimulator(config)

        simulator.run_simulation()

        # Should treat as singleplex despite potential ambiguity
        assert (self.target_dir / "sample.fastq").exists()

    @patch("nanopore_simulator.core.simulator.logging.basicConfig")
    def test_logging_configuration(self, mock_basic_config):
        """Test that logging is properly configured"""
        import logging  # Import real logging for comparison

        config = SimulationConfig(
            source_dir=self.source_dir, target_dir=self.target_dir
        )

        simulator = NanoporeSimulator(config)

        # Verify logging.basicConfig was called
        mock_basic_config.assert_called_once()
        call_args = mock_basic_config.call_args[1]

        assert call_args["level"] == logging.INFO
        assert "format" in call_args
        assert "datefmt" in call_args
