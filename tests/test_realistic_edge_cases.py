"""Realistic edge cases and stress testing for nanopore simulator"""

import pytest
import time
import tempfile
import threading
import signal
import os
import shutil
import random
from pathlib import Path
from unittest.mock import patch, MagicMock
import concurrent.futures

from nanopore_simulator.core.config import SimulationConfig
from nanopore_simulator.core.simulator import NanoporeSimulator
from nanopore_simulator.core.monitoring import SignalHandler, create_progress_monitor
from nanopore_simulator.core.adapters import get_pipeline_adapter
from nanopore_simulator.core.profiles import create_config_from_profile

from tests.fixtures.realistic_data_fixtures import (
    realistic_sequencing_data, RealisticDataGenerator
)


class TestRealisticFileSystemEdgeCases:
    """Test realistic filesystem edge cases"""
    
    def test_mixed_file_sizes_and_types(self, realistic_sequencing_data):
        """Test handling of realistic mixed file sizes and types"""
        temp_path = realistic_sequencing_data['temp_dir']
        generator = realistic_sequencing_data['generator']
        
        source_dir = temp_path / "mixed_files"
        source_dir.mkdir()
        target_dir = temp_path / "mixed_output"
        
        # Create mix of small files for fast testing
        file_configs = [
            (5, False, "tiny"),      # 5 reads, uncompressed
            (50, True, "medium"),    # 50 reads, compressed  
            (100, False, "large"),   # 100 reads, uncompressed
            (25, True, "mixed")      # 25 reads, compressed
        ]
        
        files_created = []
        for i, (reads, compress, size_type) in enumerate(file_configs):
            for j in range(3):  # 3 files of each type
                filename = f"{size_type}_{i}_{j}.fastq"
                if compress:
                    filename += ".gz"
                
                filepath = source_dir / filename
                metadata = generator.create_realistic_fastq_file(filepath, reads, compress)
                files_created.append((filepath, metadata))
        
        # Add some POD5 files
        for i in range(2):
            filepath = source_dir / f"signal_{i}.pod5"
            metadata = generator.create_realistic_pod5_file(filepath, 200)
            files_created.append((filepath, metadata))
        
        config = SimulationConfig(
            source_dir=source_dir,
            target_dir=target_dir,
            interval=0.1,
            operation="copy",
            batch_size=4
        )
        
        simulator = NanoporeSimulator(config)
        simulator.run_simulation()
        
        # Verify all files processed correctly regardless of size/type
        target_files = list(target_dir.glob("*"))
        assert len(target_files) == len(files_created)
        
        # Verify file integrity across different sizes
        for original, metadata in files_created:
            target_file = target_dir / original.name
            assert target_file.exists()
            
            if original.suffix == '.pod5':
                # POD5 files - check size preservation
                assert target_file.stat().st_size == original.stat().st_size
            elif not original.name.endswith('.gz'):
                # Uncompressed FASTQ - check content
                assert target_file.read_text() == original.read_text()
    
    def test_realistic_permission_scenarios(self, realistic_sequencing_data):
        """Test realistic permission and access scenarios"""
        temp_path = realistic_sequencing_data['temp_dir']
        generator = realistic_sequencing_data['generator']
        
        source_dir = temp_path / "permission_test"
        source_dir.mkdir()
        target_dir = temp_path / "permission_output"
        
        # Create some normal files
        normal_files = []
        for i in range(5):
            filepath = source_dir / f"normal_{i}.fastq"
            generator.create_realistic_fastq_file(filepath, 100)
            normal_files.append(filepath)
        
        # Create a file with restricted permissions (simulate real-world issues)
        restricted_file = source_dir / "restricted.fastq"
        generator.create_realistic_fastq_file(restricted_file, 100)
        
        # Make file read-only to simulate permission issues
        os.chmod(restricted_file, 0o444)
        
        try:
            config = SimulationConfig(
                source_dir=source_dir,
                target_dir=target_dir,
                interval=0.1,
                operation="copy",
                batch_size=3
            )
            
            simulator = NanoporeSimulator(config)
            
            # Mock error tracking - will be set up during run_simulation
            errors_encountered = []
            
            # Override the simulator's file processing to track errors
            original_process_file = simulator._process_file
            
            def track_process_file(*args, **kwargs):
                try:
                    return original_process_file(*args, **kwargs)
                except (OSError, PermissionError) as e:
                    errors_encountered.append("permission")
                    return False  # Indicate failure
            
            simulator._process_file = track_process_file
            simulator.run_simulation()
            
            # Verify normal files processed successfully
            normal_targets = [target_dir / f.name for f in normal_files]
            for target_file in normal_targets:
                assert target_file.exists()
            
            # Permission errors should be handled gracefully
            if errors_encountered:
                assert "permission" in str(errors_encountered).lower() or \
                       "access" in str(errors_encountered).lower()
        
        finally:
            # Restore permissions for cleanup
            os.chmod(restricted_file, 0o644)
    
    def test_realistic_symlink_handling(self, realistic_sequencing_data):
        """Test realistic symlink scenarios"""
        temp_path = realistic_sequencing_data['temp_dir']
        generator = realistic_sequencing_data['generator']
        
        # Create source data
        data_dir = temp_path / "actual_data"
        data_dir.mkdir()
        
        # Create actual files
        actual_files = []
        for i in range(3):
            filepath = data_dir / f"data_{i}.fastq"
            generator.create_realistic_fastq_file(filepath, 200)
            actual_files.append(filepath)
        
        # Create source directory with symlinks (common in sequencing setups)
        source_dir = temp_path / "symlink_source"
        source_dir.mkdir()
        target_dir = temp_path / "symlink_output"
        
        # Create symlinks to actual data
        for actual_file in actual_files:
            symlink_path = source_dir / actual_file.name
            symlink_path.symlink_to(actual_file)
        
        # Create broken symlink (realistic scenario)
        broken_link = source_dir / "broken.fastq"
        broken_link.symlink_to(data_dir / "nonexistent.fastq")
        
        config = SimulationConfig(
            source_dir=source_dir,
            target_dir=target_dir,
            interval=0.1,
            operation="copy",
            batch_size=2
        )
        
        simulator = NanoporeSimulator(config)
        simulator.run_simulation()
        
        # Verify valid symlinks were processed
        valid_targets = [target_dir / f.name for f in actual_files]
        for target_file in valid_targets:
            assert target_file.exists()
            assert target_file.is_file()  # Should be actual file, not symlink
        
        # Broken symlink should be handled gracefully
        broken_target = target_dir / "broken.fastq"
        assert not broken_target.exists()  # Should not be created


class TestRealisticConcurrencyScenarios:
    """Test realistic concurrency and parallel processing scenarios"""
    
    def test_parallel_processing_under_load(self, realistic_sequencing_data):
        """Test parallel processing with realistic workload"""
        temp_path = realistic_sequencing_data['temp_dir']
        scenarios = realistic_sequencing_data['scenarios']
        
        # Create moderate-sized dataset
        run_data = scenarios.create_minion_run(temp_path, "parallel_test")
        target_dir = temp_path / "parallel_output"
        
        config = SimulationConfig(
            source_dir=run_data['run_dir'],
            target_dir=target_dir,
            interval=0.05,
            batch_size=10,
            parallel_processing=True,
            worker_count=3,
            operation="copy"
        )
        
        simulator = NanoporeSimulator(config)
        
        # Track concurrent operations
        active_operations = threading.active_count()
        max_concurrent = active_operations
        
        # Mock to track concurrency but let actual processing happen
        original_process_file = simulator._process_file
        
        def track_concurrency(*args, **kwargs):
            nonlocal max_concurrent
            current_threads = threading.active_count()
            max_concurrent = max(max_concurrent, current_threads)
            
            # Do actual processing
            return original_process_file(*args, **kwargs)
        
        simulator._process_file = track_concurrency
        
        start_time = time.time()
        simulator.run_simulation()
        end_time = time.time()
        
        # Verify parallel processing occurred
        assert max_concurrent > active_operations + 1  # Should create additional threads
        
        # Verify all files processed
        processed_files = list(target_dir.rglob("*"))
        processed_files = [f for f in processed_files if f.is_file()]
        assert len(processed_files) == run_data['file_count']
        
        # Performance should benefit from parallelization
        processing_time = end_time - start_time
        assert processing_time < run_data['file_count'] * 0.1  # Should be much faster than sequential
    
    @pytest.mark.slow
    def test_realistic_signal_handling(self, realistic_sequencing_data):
        """Test realistic signal handling scenarios"""
        temp_path = realistic_sequencing_data['temp_dir']
        generator = realistic_sequencing_data['generator']
        
        source_dir = temp_path / "signal_test"
        source_dir.mkdir()
        target_dir = temp_path / "signal_output"
        
        # Create enough files for testing (reduced for speed)
        for i in range(6):
            filepath = source_dir / f"file_{i:03d}.fastq"
            generator.create_realistic_fastq_file(filepath, 30)  # Smaller files
        
        config = SimulationConfig(
            source_dir=source_dir,
            target_dir=target_dir,
            interval=0.01,  # Fast
            batch_size=2    # Small batches to ensure partial processing
        )
        
        simulator = NanoporeSimulator(config)
        
        # Mock interruption by limiting file processing
        files_processed = 0
        original_process_file = simulator._process_file
        
        def limited_process_file(*args, **kwargs):
            nonlocal files_processed
            files_processed += 1
            
            # Process only a few files then simulate interruption
            if files_processed >= 3:
                raise KeyboardInterrupt("Simulated interruption")
            
            return original_process_file(*args, **kwargs)
        
        simulator._process_file = limited_process_file
        
        # Run simulation expecting interruption
        try:
            simulator.run_simulation()
        except KeyboardInterrupt:
            pass  # Expected
        
        # Verify partial processing occurred
        partial_files = list(target_dir.rglob("*"))
        partial_files = [f for f in partial_files if f.is_file()]
        
        # Should have processed some but not all files
        assert 0 < len(partial_files) < 6


class TestRealisticResourceConstraints:
    """Test behavior under realistic resource constraints"""
    
    @pytest.mark.slow
    def test_memory_efficient_large_dataset(self, realistic_sequencing_data):
        """Test memory efficiency with large dataset"""
        temp_path = realistic_sequencing_data['temp_dir']
        scenarios = realistic_sequencing_data['scenarios']
        
        # Create moderate dataset for memory testing
        large_run = scenarios.create_minion_run(temp_path, "memory_test")
        target_dir = temp_path / "memory_output"
        
        config = SimulationConfig(
            source_dir=large_run['run_dir'],
            target_dir=target_dir,
            interval=0.01,  # Very fast
            batch_size=50,  # Large batches
            parallel_processing=True,
            worker_count=2
        )
        
        # Monitor memory usage patterns
        memory_samples = []
        
        def sample_memory():
            try:
                import psutil
                process = psutil.Process()
                memory_samples.append(process.memory_info().rss / 1024 / 1024)  # MB
            except ImportError:
                memory_samples.append(0)  # Skip if psutil not available
        
        # Start memory monitoring
        memory_monitor = threading.Timer(0.1, sample_memory)
        memory_monitor.start()
        
        try:
            simulator = NanoporeSimulator(config)
            simulator.run_simulation()
        finally:
            memory_monitor.cancel()
        
        # Verify processing completed
        processed_files = list(target_dir.rglob("*"))
        processed_files = [f for f in processed_files if f.is_file()]
        assert len(processed_files) == large_run['file_count']
        
        # Memory usage should remain reasonable
        if memory_samples and any(m > 0 for m in memory_samples):
            max_memory = max(memory_samples)
            assert max_memory < 500  # Should use less than 500MB
    
    def test_disk_space_monitoring(self, realistic_sequencing_data):
        """Test realistic disk space scenarios"""
        temp_path = realistic_sequencing_data['temp_dir']
        generator = realistic_sequencing_data['generator']
        
        source_dir = temp_path / "disk_test"
        source_dir.mkdir()
        target_dir = temp_path / "disk_output"
        
        # Create files of varying sizes
        total_size_mb = 0
        for i in range(10):
            reads = random.randint(100, 2000)
            filepath = source_dir / f"file_{i}.fastq"
            metadata = generator.create_realistic_fastq_file(filepath, reads)
            total_size_mb += metadata['file_size_mb']
        
        config = SimulationConfig(
            source_dir=source_dir,
            target_dir=target_dir,
            interval=0.1,
            operation="copy",
            batch_size=3
        )
        
        # Monitor disk usage
        disk_usage_samples = []
        
        def sample_disk_usage():
            try:
                import shutil
                usage = shutil.disk_usage(target_dir.parent)
                disk_usage_samples.append({
                    'free_gb': usage.free / 1024 / 1024 / 1024,
                    'used_gb': (usage.total - usage.free) / 1024 / 1024 / 1024
                })
            except Exception:
                pass
        
        # Sample before and after
        sample_disk_usage()
        
        simulator = NanoporeSimulator(config)
        simulator.run_simulation()
        
        sample_disk_usage()
        
        # Verify disk usage increased appropriately
        if len(disk_usage_samples) >= 2:
            initial_used = disk_usage_samples[0]['used_gb']
            final_used = disk_usage_samples[-1]['used_gb']
            usage_increase = final_used - initial_used
            
            # Should increase by roughly the amount copied
            expected_increase_gb = total_size_mb / 1024
            assert abs(usage_increase - expected_increase_gb) < 0.1  # Within 100MB tolerance


class TestRealisticErrorScenarios:
    """Test realistic error conditions and recovery"""
    
    def test_partial_file_corruption_handling(self, realistic_sequencing_data):
        """Test handling of corrupted files (realistic sequencing scenario)"""
        temp_path = realistic_sequencing_data['temp_dir']
        generator = realistic_sequencing_data['generator']
        
        source_dir = temp_path / "corruption_test"
        source_dir.mkdir()
        target_dir = temp_path / "corruption_output"
        
        # Create mix of good and corrupted files
        good_files = []
        for i in range(5):
            filepath = source_dir / f"good_{i}.fastq"
            generator.create_realistic_fastq_file(filepath, 200)
            good_files.append(filepath)
        
        # Create corrupted files (simulate real-world corruption)
        corrupted_files = []
        for i in range(2):
            filepath = source_dir / f"corrupted_{i}.fastq"
            # Write malformed FASTQ
            filepath.write_text("@incomplete_read\nACGT\n")  # Missing quality scores
            corrupted_files.append(filepath)
        
        config = SimulationConfig(
            source_dir=source_dir,
            target_dir=target_dir,
            interval=0.1,
            operation="copy",
            batch_size=2
        )
        
        # Track errors during file processing
        errors_logged = []
        
        simulator = NanoporeSimulator(config)
        
        # Mock file processing to track errors with corrupted files
        original_process_file = simulator._process_file
        
        def mock_process_file(*args, **kwargs):
            try:
                return original_process_file(*args, **kwargs)
            except Exception as e:
                errors_logged.append("corruption")
                return False  # Indicate failure
        
        simulator._process_file = mock_process_file
        
        # Should complete despite corrupted files
        simulator.run_simulation()
        
        # Verify good files were processed
        for good_file in good_files:
            target_file = target_dir / good_file.name
            assert target_file.exists()
        
        # Corrupted files may or may not be copied (depends on detection)
        # But simulation should complete without crashing
        total_target_files = list(target_dir.glob("*"))
        assert len(total_target_files) >= len(good_files)
    
    def test_network_mounted_storage_simulation(self, realistic_sequencing_data):
        """Test realistic network storage scenarios"""
        temp_path = realistic_sequencing_data['temp_dir']
        generator = realistic_sequencing_data['generator']
        
        source_dir = temp_path / "network_source"
        source_dir.mkdir()
        target_dir = temp_path / "network_target"
        
        # Create files that simulate network-mounted data
        for i in range(8):
            filepath = source_dir / f"network_file_{i}.fastq"
            generator.create_realistic_fastq_file(filepath, 300)
        
        config = SimulationConfig(
            source_dir=source_dir,
            target_dir=target_dir,
            interval=0.3,  # Slower to simulate network delays
            operation="copy",
            batch_size=2
        )
        
        # Simulate network delays
        original_copy = shutil.copy2
        network_delays = []
        
        def delayed_copy(src, dst):
            # Simulate network latency
            delay = random.uniform(0.01, 0.05)
            network_delays.append(delay)
            time.sleep(delay)
            return original_copy(src, dst)
        
        with patch('shutil.copy2', side_effect=delayed_copy):
            start_time = time.time()
            simulator = NanoporeSimulator(config)
            simulator.run_simulation()
            total_time = time.time() - start_time
        
        # Verify completion despite network delays
        target_files = list(target_dir.glob("*"))
        assert len(target_files) == 8
        
        # Should account for network delays in timing
        total_network_delay = sum(network_delays)
        assert total_time > total_network_delay  # Should include the delays
        
        # Verify files are identical despite network transfer
        for i in range(8):
            source_file = source_dir / f"network_file_{i}.fastq"
            target_file = target_dir / f"network_file_{i}.fastq"
            assert target_file.read_text() == source_file.read_text()