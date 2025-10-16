"""Performance and stress tests for nanopore simulator"""

import pytest
import tempfile
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import threading

from nanopore_simulator.core.config import SimulationConfig
from nanopore_simulator.core.simulator import NanoporeSimulator
from nanopore_simulator.core.detector import FileStructureDetector


class TestPerformance:

    def setup_method(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def teardown_method(self):
        """Clean up test fixtures"""
        self.temp_dir.cleanup()

    @pytest.mark.slow
    def test_large_file_count_performance(self):
        """Test performance with large number of files"""
        source_dir = self.temp_path / "large_source"
        source_dir.mkdir()
        target_dir = self.temp_path / "large_target"

        # Create 1000 small files
        num_files = 1000
        for i in range(num_files):
            (source_dir / f"file_{i:04d}.fastq").write_text("@read\nACGT\n+\nIIII\n")

        config = SimulationConfig(
            source_dir=source_dir,
            target_dir=target_dir,
            interval=0.001,  # Very fast
            batch_size=100,  # Large batches for efficiency
        )

        start_time = time.time()
        simulator = NanoporeSimulator(config)
        simulator.run_simulation()
        end_time = time.time()

        # Verify all files processed
        processed_files = list(target_dir.glob("*.fastq"))
        assert len(processed_files) == num_files

        # Performance check - should complete in reasonable time
        processing_time = end_time - start_time
        assert processing_time < 30.0  # Should complete within 30 seconds

        # Calculate throughput
        throughput = num_files / processing_time
        print(
            f"Processed {num_files} files in {processing_time:.2f}s ({throughput:.1f} files/sec)"
        )

    @pytest.mark.slow
    def test_large_file_size_performance(self):
        """Test performance with large individual files"""
        source_dir = self.temp_path / "large_files_source"
        source_dir.mkdir()
        target_dir = self.temp_path / "large_files_target"

        # Create a few large files (simulate large FASTQ files)
        large_content = (
            "@read\n" + "A" * 1000000 + "\n+\n" + "I" * 1000000 + "\n"
        )  # ~2MB

        for i in range(5):
            (source_dir / f"large_file_{i}.fastq").write_text(large_content)

        config = SimulationConfig(
            source_dir=source_dir,
            target_dir=target_dir,
            interval=0.1,
            operation="copy",  # Test copy performance with large files
        )

        start_time = time.time()
        simulator = NanoporeSimulator(config)
        simulator.run_simulation()
        end_time = time.time()

        # Verify files processed and content preserved
        for i in range(5):
            target_file = target_dir / f"large_file_{i}.fastq"
            assert target_file.exists()
            assert len(target_file.read_text()) == len(large_content)

        processing_time = end_time - start_time
        print(f"Processed 5 large files (~2MB each) in {processing_time:.2f}s")

    def test_deep_barcode_hierarchy_performance(self):
        """Test performance with deeply nested barcode structure"""
        source_dir = self.temp_path / "deep_source"
        source_dir.mkdir()
        target_dir = self.temp_path / "deep_target"

        # Create many barcode directories
        num_barcodes = 100
        for i in range(1, num_barcodes + 1):
            barcode_dir = source_dir / f"barcode{i:02d}"
            barcode_dir.mkdir()

            # Multiple files per barcode
            for j in range(5):
                (barcode_dir / f"reads_{j}.fastq").write_text(
                    f"@read_{i}_{j}\nACGT\n+\nIIII\n"
                )

        config = SimulationConfig(
            source_dir=source_dir, target_dir=target_dir, interval=0.01, batch_size=20
        )

        start_time = time.time()
        simulator = NanoporeSimulator(config)
        simulator.run_simulation()
        end_time = time.time()

        # Verify structure and file count
        target_barcodes = [d for d in target_dir.iterdir() if d.is_dir()]
        assert len(target_barcodes) == num_barcodes

        total_files = sum(
            len(list(bc_dir.glob("*.fastq"))) for bc_dir in target_barcodes
        )
        assert total_files == num_barcodes * 5

        processing_time = end_time - start_time
        print(
            f"Processed {num_barcodes} barcode directories ({total_files} files) in {processing_time:.2f}s"
        )

    def test_concurrent_detection_performance(self):
        """Test file structure detection performance under concurrent access"""
        source_dir = self.temp_path / "concurrent_source"
        source_dir.mkdir()

        # Create mixed structure
        for i in range(50):
            (source_dir / f"direct_{i}.fastq").write_text("content")

        for i in range(20):
            barcode_dir = source_dir / f"barcode{i:02d}"
            barcode_dir.mkdir()
            (barcode_dir / "reads.fastq").write_text("content")

        def detect_structure():
            return FileStructureDetector.detect_structure(source_dir)

        # Run detection concurrently
        start_time = time.time()
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(detect_structure) for _ in range(50)]
            results = [future.result() for future in futures]
        end_time = time.time()

        # All should return same result
        assert all(result == "multiplex" for result in results)

        detection_time = end_time - start_time
        print(f"50 concurrent structure detections completed in {detection_time:.2f}s")

    def test_memory_usage_large_manifest(self):
        """Test memory efficiency with large file manifests"""
        source_dir = self.temp_path / "memory_test_source"
        source_dir.mkdir()

        # Create many small files to test manifest size
        num_files = 5000
        for i in range(num_files):
            (source_dir / f"small_{i:05d}.fastq").write_text("@read\nA\n+\nI\n")

        config = SimulationConfig(
            source_dir=source_dir,
            target_dir=self.temp_path / "memory_test_target",
            interval=0.0,  # No delays
            batch_size=1000,
        )

        simulator = NanoporeSimulator(config)

        # Test manifest creation time
        start_time = time.time()
        manifest = simulator._create_singleplex_manifest()
        manifest_time = time.time() - start_time

        assert len(manifest) == num_files
        print(f"Created manifest for {num_files} files in {manifest_time:.3f}s")

        # Test that manifest is memory-efficient (basic check)
        import sys

        manifest_size = sys.getsizeof(manifest)
        size_per_item = manifest_size / len(manifest) if manifest else 0
        print(
            f"Manifest memory usage: {manifest_size} bytes ({size_per_item:.1f} bytes/item)"
        )

    def test_symlink_vs_copy_performance(self):
        """Compare performance of symlink vs copy operations"""
        source_dir = self.temp_path / "perf_comparison_source"
        source_dir.mkdir()

        # Create test files
        num_files = 100
        for i in range(num_files):
            (source_dir / f"test_{i:03d}.fastq").write_text(
                "@read\n" + "A" * 1000 + "\n+\n" + "I" * 1000 + "\n"
            )

        # Test copy operation
        copy_target = self.temp_path / "copy_target"
        copy_config = SimulationConfig(
            source_dir=source_dir,
            target_dir=copy_target,
            interval=0.0,
            operation="copy",
            batch_size=num_files,  # Single batch
        )

        start_time = time.time()
        copy_simulator = NanoporeSimulator(copy_config)
        copy_simulator.run_simulation()
        copy_time = time.time() - start_time

        # Test symlink operation
        link_target = self.temp_path / "link_target"
        link_config = SimulationConfig(
            source_dir=source_dir,
            target_dir=link_target,
            interval=0.0,
            operation="link",
            batch_size=num_files,  # Single batch
        )

        start_time = time.time()
        link_simulator = NanoporeSimulator(link_config)
        link_simulator.run_simulation()
        link_time = time.time() - start_time

        print(f"Copy operation: {copy_time:.3f}s")
        print(f"Link operation: {link_time:.3f}s")
        print(f"Link is {copy_time/link_time:.1f}x faster than copy")

        # Symlinks should generally be faster
        assert link_time < copy_time

    def test_batch_size_impact_on_performance(self):
        """Test how batch size affects performance"""
        source_dir = self.temp_path / "batch_test_source"
        source_dir.mkdir()

        # Create test files
        num_files = 200
        for i in range(num_files):
            (source_dir / f"batch_test_{i:03d}.fastq").write_text(
                "@read\nACGT\n+\nIIII\n"
            )

        batch_sizes = [1, 10, 50, 100, 200]
        results = {}

        for batch_size in batch_sizes:
            target_dir = self.temp_path / f"batch_target_{batch_size}"
            config = SimulationConfig(
                source_dir=source_dir,
                target_dir=target_dir,
                interval=0.001,  # Small delay to see batching effect
                batch_size=batch_size,
            )

            start_time = time.time()
            simulator = NanoporeSimulator(config)
            simulator.run_simulation()
            end_time = time.time()

            results[batch_size] = end_time - start_time
            print(f"Batch size {batch_size}: {results[batch_size]:.3f}s")

        # Larger batch sizes should generally be more efficient
        # (fewer delay intervals)
        assert results[200] <= results[1]

    def test_stress_test_rapid_operations(self):
        """Stress test with very rapid operations"""
        source_dir = self.temp_path / "stress_source"
        source_dir.mkdir()

        # Create moderate number of files
        num_files = 500
        for i in range(num_files):
            (source_dir / f"stress_{i:03d}.fastq").write_text("@read\nACGT\n+\nIIII\n")

        config = SimulationConfig(
            source_dir=source_dir,
            target_dir=self.temp_path / "stress_target",
            interval=0.0,  # No delays - maximum speed
            batch_size=50,
            operation="link",  # Faster operation
        )

        # Run multiple times to check consistency
        times = []
        for run in range(3):
            target_dir = self.temp_path / f"stress_target_run_{run}"
            config.target_dir = target_dir

            start_time = time.time()
            simulator = NanoporeSimulator(config)
            simulator.run_simulation()
            end_time = time.time()

            times.append(end_time - start_time)

            # Verify completion
            assert len(list(target_dir.glob("*.fastq"))) == num_files

        avg_time = sum(times) / len(times)
        std_dev = (sum((t - avg_time) ** 2 for t in times) / len(times)) ** 0.5

        print(f"Stress test - Average time: {avg_time:.3f}s, Std dev: {std_dev:.3f}s")

        # Check for reasonable consistency (coefficient of variation < 50%)
        cv = std_dev / avg_time if avg_time > 0 else float("inf")
        assert cv < 0.5, f"Performance too inconsistent: CV = {cv:.2f}"
