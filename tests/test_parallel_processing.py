"""Tests for parallel processing functionality"""

import pytest
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
from concurrent.futures import ThreadPoolExecutor

from nanopore_simulator.core.config import SimulationConfig
from nanopore_simulator.core.simulator import NanoporeSimulator


class TestParallelProcessingConfig:
    """Test parallel processing configuration"""

    def test_parallel_processing_disabled_by_default(self, temp_dirs):
        """Test that parallel processing is disabled by default"""
        source_dir, target_dir = temp_dirs
        config = SimulationConfig(source_dir, target_dir)

        assert config.parallel_processing is False
        assert config.worker_count == 4  # Default worker count

    def test_parallel_processing_configuration(self, temp_dirs):
        """Test parallel processing configuration parameters"""
        source_dir, target_dir = temp_dirs

        config = SimulationConfig(
            source_dir, target_dir, parallel_processing=True, worker_count=8
        )

        assert config.parallel_processing is True
        assert config.worker_count == 8

    def test_worker_count_validation(self, temp_dirs):
        """Test worker count validation"""
        source_dir, target_dir = temp_dirs

        # Valid worker count
        SimulationConfig(source_dir, target_dir, worker_count=1)
        SimulationConfig(source_dir, target_dir, worker_count=16)

        # Invalid worker count
        with pytest.raises(ValueError, match="worker_count must be at least 1"):
            SimulationConfig(source_dir, target_dir, worker_count=0)

        with pytest.raises(ValueError, match="worker_count must be at least 1"):
            SimulationConfig(source_dir, target_dir, worker_count=-1)


class TestSimulatorParallelInitialization:
    """Test simulator initialization with parallel processing"""

    def test_sequential_processing_initialization(self, temp_dirs):
        """Test simulator initialization without parallel processing"""
        source_dir, target_dir = temp_dirs
        config = SimulationConfig(source_dir, target_dir, parallel_processing=False)

        simulator = NanoporeSimulator(config)

        assert simulator.executor is None
        assert simulator.config.parallel_processing is False

    def test_parallel_processing_initialization(self, temp_dirs):
        """Test simulator initialization with parallel processing"""
        source_dir, target_dir = temp_dirs
        config = SimulationConfig(
            source_dir, target_dir, parallel_processing=True, worker_count=2
        )

        simulator = NanoporeSimulator(config)

        assert simulator.executor is not None
        assert isinstance(simulator.executor, ThreadPoolExecutor)
        assert simulator.config.parallel_processing is True

        # Clean up
        simulator._cleanup()

    def test_cleanup_closes_executor(self, temp_dirs):
        """Test that cleanup properly closes the thread pool executor"""
        source_dir, target_dir = temp_dirs
        config = SimulationConfig(
            source_dir, target_dir, parallel_processing=True, worker_count=2
        )

        simulator = NanoporeSimulator(config)
        executor = simulator.executor

        assert executor is not None

        # Call cleanup
        simulator._cleanup()

        assert simulator.executor is None
        # Executor should be shut down (we can't easily test this directly)


class TestBatchProcessing:
    """Test batch processing methods"""

    @pytest.fixture
    def simulator_setup(self, temp_dirs):
        """Setup simulator for testing"""
        source_dir, target_dir = temp_dirs

        # Create test files
        test_files = []
        for i in range(5):
            test_file = source_dir / f"test_{i}.fastq"
            test_file.write_text(f"test content {i}")
            test_files.append(test_file)

        # Create file manifest
        file_manifest = []
        for test_file in test_files:
            file_manifest.append(
                {
                    "source": test_file,
                    "target": target_dir / test_file.name,
                    "barcode": None,
                }
            )

        return source_dir, target_dir, file_manifest

    def test_sequential_batch_processing(self, simulator_setup):
        """Test sequential batch processing"""
        source_dir, target_dir, file_manifest = simulator_setup

        config = SimulationConfig(source_dir, target_dir, parallel_processing=False)
        simulator = NanoporeSimulator(config)

        # Process batch sequentially
        batch = file_manifest[:3]
        simulator._process_batch_sequential(batch)

        # Check that files were processed
        for file_info in batch:
            assert file_info["target"].exists()
            assert file_info["target"].read_text() == file_info["source"].read_text()

    def test_parallel_batch_processing(self, simulator_setup):
        """Test parallel batch processing"""
        source_dir, target_dir, file_manifest = simulator_setup

        config = SimulationConfig(
            source_dir, target_dir, parallel_processing=True, worker_count=3
        )
        simulator = NanoporeSimulator(config)

        try:
            # Process batch in parallel
            batch = file_manifest[:4]
            simulator._process_batch_parallel(batch)

            # Check that files were processed
            for file_info in batch:
                assert file_info["target"].exists()
                assert (
                    file_info["target"].read_text() == file_info["source"].read_text()
                )
        finally:
            simulator._cleanup()

    def test_empty_batch_handling(self, temp_dirs):
        """Test handling of empty batches"""
        source_dir, target_dir = temp_dirs

        config = SimulationConfig(source_dir, target_dir, parallel_processing=True)
        simulator = NanoporeSimulator(config)

        try:
            # Should handle empty batch gracefully
            simulator._process_batch_parallel([])
            simulator._process_batch_sequential([])
        finally:
            simulator._cleanup()

    def test_parallel_processing_exception_handling(self, simulator_setup):
        """Test exception handling in parallel processing"""
        source_dir, target_dir, file_manifest = simulator_setup

        config = SimulationConfig(
            source_dir, target_dir, parallel_processing=True, worker_count=2
        )
        simulator = NanoporeSimulator(config)

        try:
            # Create a file manifest with an invalid source
            bad_manifest = [
                {
                    "source": Path("/nonexistent/file.fastq"),
                    "target": target_dir / "bad.fastq",
                    "barcode": None,
                }
            ]

            # Should raise an exception
            with pytest.raises(FileNotFoundError):
                simulator._process_batch_parallel(bad_manifest)
        finally:
            simulator._cleanup()


class TestParallelPerformance:
    """Test performance characteristics of parallel processing"""

    @pytest.fixture
    def large_file_setup(self, temp_dirs):
        """Setup with larger files for performance testing"""
        source_dir, target_dir = temp_dirs

        # Create larger test files
        test_files = []
        for i in range(10):
            test_file = source_dir / f"large_test_{i}.fastq"
            # Create files with more content to make copying take longer
            content = f"@read{i}\n" + "A" * 1000 + f"\n+\n" + "I" * 1000 + "\n"
            test_file.write_text(content * 100)  # Make it reasonably large
            test_files.append(test_file)

        # Create file manifest
        file_manifest = []
        for test_file in test_files:
            file_manifest.append(
                {
                    "source": test_file,
                    "target": target_dir / test_file.name,
                    "barcode": None,
                }
            )

        return source_dir, target_dir, file_manifest

    def test_parallel_vs_sequential_performance(self, large_file_setup):
        """Test that parallel processing is faster than sequential for large batches"""
        source_dir, target_dir, file_manifest = large_file_setup

        # Sequential processing
        config_seq = SimulationConfig(source_dir, target_dir, parallel_processing=False)
        simulator_seq = NanoporeSimulator(config_seq)

        start_time = time.time()
        simulator_seq._process_batch_sequential(file_manifest)
        sequential_time = time.time() - start_time

        # Clean up sequential files
        for file_info in file_manifest:
            if file_info["target"].exists():
                file_info["target"].unlink()

        # Parallel processing
        config_par = SimulationConfig(
            source_dir, target_dir, parallel_processing=True, worker_count=4
        )
        simulator_par = NanoporeSimulator(config_par)

        try:
            start_time = time.time()
            simulator_par._process_batch_parallel(file_manifest)
            parallel_time = time.time() - start_time

            # Parallel should be faster (or at least not significantly slower)
            # Allow for some overhead and system variation
            speed_ratio = sequential_time / parallel_time
            assert (
                speed_ratio > 0.8
            ), f"Parallel processing should be competitive (ratio: {speed_ratio})"

            # Verify all files were processed correctly
            for file_info in file_manifest:
                assert file_info["target"].exists()
                assert (
                    file_info["target"].stat().st_size
                    == file_info["source"].stat().st_size
                )
        finally:
            simulator_par._cleanup()


class TestParallelIntegration:
    """Integration tests for parallel processing with full simulation"""

    def test_full_simulation_with_parallel_processing(self, temp_dirs):
        """Test complete simulation workflow with parallel processing"""
        source_dir, target_dir = temp_dirs

        # Create test files
        for i in range(8):
            test_file = source_dir / f"test_{i}.fastq"
            test_file.write_text(f"@read{i}\nACGT\n+\nIIII\n")

        config = SimulationConfig(
            source_dir,
            target_dir,
            interval=0.1,  # Fast interval for testing
            batch_size=3,
            parallel_processing=True,
            worker_count=2,
            timing_model="uniform",
        )

        simulator = NanoporeSimulator(config)

        # Run simulation
        start_time = time.time()
        simulator.run_simulation()
        elapsed_time = time.time() - start_time

        # Check that files were transferred
        source_files = list(source_dir.glob("*.fastq"))
        target_files = list(target_dir.glob("*.fastq"))

        assert len(target_files) == len(source_files)

        # Verify content
        for source_file in source_files:
            target_file = target_dir / source_file.name
            assert target_file.exists()
            assert target_file.read_text() == source_file.read_text()

        # Simulation should complete reasonably quickly
        # With 8 files, batch_size 3, and interval 0.1, should take ~0.3s + processing time
        assert elapsed_time < 2.0  # Allow generous margin for system variation

    def test_timing_model_with_parallel_processing(self, temp_dirs):
        """Test that timing models work correctly with parallel processing"""
        source_dir, target_dir = temp_dirs

        # Create test file
        test_file = source_dir / "test.fastq"
        test_file.write_text("@read1\nACGT\n+\nIIII\n")

        # Use random timing model with parallel processing
        config = SimulationConfig(
            source_dir,
            target_dir,
            interval=0.1,
            timing_model="random",
            timing_model_params={"random_factor": 0.2},
            parallel_processing=True,
            worker_count=2,
        )

        # Should use random timing model
        assert config.timing_model == "random"
        assert config.timing_model_params["random_factor"] == 0.2

        simulator = NanoporeSimulator(config)
        simulator.run_simulation()

        # Verify file was transferred
        target_file = target_dir / "test.fastq"
        assert target_file.exists()
        assert target_file.read_text() == test_file.read_text()

    def test_multiplex_with_parallel_processing(self, temp_dirs):
        """Test multiplex simulation with parallel processing"""
        source_dir, target_dir = temp_dirs

        # Create multiplex structure
        for barcode in ["barcode01", "barcode02", "unclassified"]:
            barcode_dir = source_dir / barcode
            barcode_dir.mkdir()

            for i in range(3):
                test_file = barcode_dir / f"reads_{i}.fastq"
                test_file.write_text(f"@read{i}\nACGT\n+\nIIII\n")

        config = SimulationConfig(
            source_dir,
            target_dir,
            interval=0.05,
            batch_size=2,
            parallel_processing=True,
            worker_count=3,
            timing_model="poisson",
            timing_model_params={"burst_probability": 0.1},
        )

        simulator = NanoporeSimulator(config)
        simulator.run_simulation()

        # Verify directory structure was preserved
        for barcode in ["barcode01", "barcode02", "unclassified"]:
            target_barcode_dir = target_dir / barcode
            assert target_barcode_dir.exists()
            assert target_barcode_dir.is_dir()

            # Check files in each barcode directory
            source_files = list((source_dir / barcode).glob("*.fastq"))
            target_files = list(target_barcode_dir.glob("*.fastq"))

            assert len(target_files) == len(source_files)

            for source_file in source_files:
                target_file = target_barcode_dir / source_file.name
                assert target_file.exists()
                assert target_file.read_text() == source_file.read_text()


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        source_dir = tmp_path / "source"
        target_dir = tmp_path / "target"
        source_dir.mkdir()
        target_dir.mkdir()
        yield source_dir, target_dir
