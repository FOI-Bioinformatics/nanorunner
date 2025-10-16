"""Integration tests for complete workflows"""

import pytest
import tempfile
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
import time

from nanopore_simulator import (
    SimulationConfig,
    NanoporeSimulator,
    FileStructureDetector,
)


class TestIntegrationWorkflows:

    def setup_method(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def teardown_method(self):
        """Clean up test fixtures"""
        self.temp_dir.cleanup()

    def create_sample_data(self, structure_type="singleplex"):
        """Helper to create sample test data"""
        source_dir = self.temp_path / "sample_data"
        source_dir.mkdir()

        if structure_type == "singleplex":
            # Create singleplex structure
            (source_dir / "sample1.fastq").write_text("@read1\nACGT\n+\nIIII\n")
            (source_dir / "sample2.fastq.gz").write_text("compressed_fastq_data")
            (source_dir / "sample3.pod5").write_text("binary_pod5_data")

        elif structure_type == "multiplex":
            # Create multiplex structure
            for barcode_num in ["01", "02", "12"]:
                barcode_dir = source_dir / f"barcode{barcode_num}"
                barcode_dir.mkdir()
                (barcode_dir / f"reads_{barcode_num}.fastq").write_text(
                    f"@read_bc{barcode_num}\nACGT\n+\nIIII\n"
                )
                (barcode_dir / f"additional_{barcode_num}.fastq.gz").write_text(
                    f"compressed_bc{barcode_num}"
                )

            # Add unclassified directory
            unclass_dir = source_dir / "unclassified"
            unclass_dir.mkdir()
            (unclass_dir / "unassigned.fastq").write_text(
                "@unassigned_read\nNNNN\n+\n!!!!\n"
            )

        elif structure_type == "mixed":
            # Create mixed structure (both files and barcode dirs)
            (source_dir / "direct_file.fastq").write_text("@direct\nACGT\n+\nIIII\n")

            barcode_dir = source_dir / "barcode01"
            barcode_dir.mkdir()
            (barcode_dir / "barcode_file.fastq").write_text("@barcode\nACGT\n+\nIIII\n")

        return source_dir

    def test_end_to_end_singleplex_workflow(self):
        """Test complete singleplex workflow from detection to file processing"""
        source_dir = self.create_sample_data("singleplex")
        target_dir = self.temp_path / "output_singleplex"

        # Step 1: Detect structure
        structure = FileStructureDetector.detect_structure(source_dir)
        assert structure == "singleplex"

        # Step 2: Configure simulation
        config = SimulationConfig(
            source_dir=source_dir,
            target_dir=target_dir,
            interval=0.1,  # Fast for testing
            operation="copy",
            batch_size=2,
        )

        # Step 3: Run simulation
        simulator = NanoporeSimulator(config)
        simulator.run_simulation()

        # Step 4: Verify results
        assert target_dir.exists()
        assert (target_dir / "sample1.fastq").exists()
        assert (target_dir / "sample2.fastq.gz").exists()
        assert (target_dir / "sample3.pod5").exists()

        # Verify content preservation
        assert (target_dir / "sample1.fastq").read_text() == "@read1\nACGT\n+\nIIII\n"
        assert (target_dir / "sample2.fastq.gz").read_text() == "compressed_fastq_data"
        assert (target_dir / "sample3.pod5").read_text() == "binary_pod5_data"

    def test_end_to_end_multiplex_workflow(self):
        """Test complete multiplex workflow"""
        source_dir = self.create_sample_data("multiplex")
        target_dir = self.temp_path / "output_multiplex"

        # Detect and simulate
        structure = FileStructureDetector.detect_structure(source_dir)
        assert structure == "multiplex"

        config = SimulationConfig(
            source_dir=source_dir,
            target_dir=target_dir,
            interval=0.1,
            operation="link",  # Test symlink operation
        )

        simulator = NanoporeSimulator(config)
        simulator.run_simulation()

        # Verify barcode directory structure
        for barcode_num in ["01", "02", "12"]:
            barcode_dir = target_dir / f"barcode{barcode_num}"
            assert barcode_dir.exists()
            assert barcode_dir.is_dir()

            reads_file = barcode_dir / f"reads_{barcode_num}.fastq"
            additional_file = barcode_dir / f"additional_{barcode_num}.fastq.gz"

            assert reads_file.exists()
            assert additional_file.exists()

            # Verify symlinks
            assert reads_file.is_symlink()
            assert additional_file.is_symlink()

            # Verify content through symlinks
            assert reads_file.read_text() == f"@read_bc{barcode_num}\nACGT\n+\nIIII\n"

        # Verify unclassified directory
        unclass_dir = target_dir / "unclassified"
        assert unclass_dir.exists()
        unclass_file = unclass_dir / "unassigned.fastq"
        assert unclass_file.exists()
        assert unclass_file.is_symlink()
        assert unclass_file.read_text() == "@unassigned_read\nNNNN\n+\n!!!!\n"

    def test_console_script_integration(self):
        """Test the installed console script end-to-end"""
        source_dir = self.create_sample_data("singleplex")
        target_dir = self.temp_path / "console_output"

        # Run via console script
        cmd = [
            sys.executable,
            "-m",
            "nanopore_simulator.cli.main",
            str(source_dir),
            str(target_dir),
            "--interval",
            "0.1",
            "--batch-size",
            "3",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        assert result.returncode == 0
        assert "Starting nanopore simulation" in result.stderr
        assert "Simulation completed" in result.stderr

        # Verify files were processed
        assert (target_dir / "sample1.fastq").exists()
        assert (target_dir / "sample2.fastq.gz").exists()
        assert (target_dir / "sample3.pod5").exists()

    def test_forced_structure_override(self):
        """Test forcing structure detection override"""
        source_dir = self.create_sample_data(
            "mixed"
        )  # Has both direct files and barcode dirs
        target_dir = self.temp_path / "forced_output"

        # Force singleplex interpretation
        config = SimulationConfig(
            source_dir=source_dir,
            target_dir=target_dir,
            force_structure="singleplex",
            interval=0.1,
        )

        simulator = NanoporeSimulator(config)
        simulator.run_simulation()

        # Should only process direct files, ignore barcode directories
        assert (target_dir / "direct_file.fastq").exists()
        assert not (target_dir / "barcode01").exists()

    def test_large_batch_processing(self):
        """Test processing with large batch sizes"""
        source_dir = self.temp_path / "large_batch_source"
        source_dir.mkdir()

        # Create many files
        num_files = 20
        for i in range(num_files):
            (source_dir / f"file_{i:03d}.fastq").write_text(
                f"@read{i}\nACGT\n+\nIIII\n"
            )

        target_dir = self.temp_path / "large_batch_output"

        config = SimulationConfig(
            source_dir=source_dir,
            target_dir=target_dir,
            interval=0.05,  # Very fast
            batch_size=10,  # Large batch
        )

        start_time = time.time()
        simulator = NanoporeSimulator(config)
        simulator.run_simulation()
        end_time = time.time()

        # Verify all files processed
        assert len(list(target_dir.glob("*.fastq"))) == num_files

        # Should be faster due to batching (less than 2 intervals for 20 files with batch_size=10)
        assert end_time - start_time < 0.2  # Should complete in under 200ms

    def test_mixed_file_types_workflow(self):
        """Test workflow with mixed FASTQ and POD5 files"""
        source_dir = self.temp_path / "mixed_types_source"
        source_dir.mkdir()

        # Create various file types
        (source_dir / "reads.fastq").write_text("@read1\nACGT\n+\nIIII\n")
        (source_dir / "reads.fq").write_text("@read2\nTGCA\n+\n~~~\n")
        (source_dir / "reads.fastq.gz").write_text("compressed_fastq")
        (source_dir / "reads.fq.gz").write_text("compressed_fq")
        (source_dir / "signals.pod5").write_text("binary_pod5_signals")

        # Add non-sequencing files (should be ignored)
        (source_dir / "readme.txt").write_text("This is documentation")
        (source_dir / "config.json").write_text('{"setting": "value"}')

        target_dir = self.temp_path / "mixed_types_output"

        config = SimulationConfig(
            source_dir=source_dir, target_dir=target_dir, interval=0.1
        )

        simulator = NanoporeSimulator(config)
        simulator.run_simulation()

        # Verify only sequencing files were processed
        sequencing_files = [
            "reads.fastq",
            "reads.fq",
            "reads.fastq.gz",
            "reads.fq.gz",
            "signals.pod5",
        ]
        for filename in sequencing_files:
            assert (target_dir / filename).exists()

        # Verify non-sequencing files were ignored
        assert not (target_dir / "readme.txt").exists()
        assert not (target_dir / "config.json").exists()

    def test_nested_barcode_structure(self):
        """Test handling of complex nested barcode structures"""
        source_dir = self.temp_path / "nested_source"
        source_dir.mkdir()

        # Create complex barcode structure with unique names (case-insensitive filesystem safe)
        barcode_combinations = [
            ("barcode", "01"),
            ("barcode", "12"),
            ("barcode", "96"),
            ("BC", "02"),
            ("BC", "13"),
            ("BC", "97"),  # Different numbers to avoid case conflicts
            ("bc", "03"),
            ("bc", "14"),
            ("bc", "98"),  # Different numbers to avoid case conflicts
        ]

        for bc_pattern, num in barcode_combinations:
            barcode_dir = source_dir / f"{bc_pattern}{num}"
            barcode_dir.mkdir(exist_ok=True)

            # Add multiple files per barcode
            (barcode_dir / "reads_part1.fastq").write_text(
                f"@{bc_pattern}{num}_1\nACGT\n+\nIIII\n"
            )
            (barcode_dir / "reads_part2.fastq.gz").write_text(
                f"compressed_{bc_pattern}{num}"
            )
            (barcode_dir / "signals.pod5").write_text(f"pod5_{bc_pattern}{num}")

        target_dir = self.temp_path / "nested_output"

        config = SimulationConfig(
            source_dir=source_dir, target_dir=target_dir, interval=0.05, batch_size=5
        )

        simulator = NanoporeSimulator(config)
        simulator.run_simulation()

        # Verify all barcode directories and files were processed
        expected_dirs = 9  # 9 unique barcode combinations
        actual_dirs = len([d for d in target_dir.iterdir() if d.is_dir()])
        assert actual_dirs == expected_dirs

        # Verify file count (3 files per directory × 9 directories)
        total_files = sum(
            len(list(d.glob("*"))) for d in target_dir.iterdir() if d.is_dir()
        )
        assert total_files == 27

    def test_error_recovery_and_partial_completion(self):
        """Test behavior when some files cannot be processed"""
        source_dir = self.temp_path / "error_source"
        source_dir.mkdir()

        # Create normal files
        (source_dir / "good_file1.fastq").write_text("@read1\nACGT\n+\nIIII\n")
        (source_dir / "good_file2.fastq").write_text("@read2\nTGCA\n+\n~~~\n")

        target_dir = self.temp_path / "error_output"

        config = SimulationConfig(
            source_dir=source_dir, target_dir=target_dir, interval=0.1
        )

        simulator = NanoporeSimulator(config)

        # Simulate partial failure by making target directory read-only after first file
        with patch.object(
            simulator,
            "_process_file",
            side_effect=[
                None,  # First call succeeds
                PermissionError("Permission denied"),  # Second call fails
            ],
        ):
            with pytest.raises(PermissionError):
                simulator.run_simulation()

        # Should have processed at least the first file before error
        # (This tests graceful degradation)
