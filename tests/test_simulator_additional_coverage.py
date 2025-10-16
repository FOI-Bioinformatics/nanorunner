"""Additional tests to improve simulator.py coverage to 95%+"""

import pytest
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from concurrent.futures import Future

from nanopore_simulator.core.simulator import NanoporeSimulator
from nanopore_simulator.core.config import SimulationConfig
from nanopore_simulator.core.monitoring import ProgressMonitor


class TestShutdownScenarios:
    """Test shutdown signal handling during various phases"""

    def test_shutdown_during_batch_loop(self):
        """Test shutdown signal stops simulation between batches"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            target_dir = Path(tmpdir) / "target"
            source_dir.mkdir()

            # Create test files
            for i in range(10):
                (source_dir / f"test_{i}.fastq").write_text(f"@read{i}\nACGT\n+\n!!!!")

            config = SimulationConfig(
                source_dir=source_dir,
                target_dir=target_dir,
                interval=0.1,
                batch_size=2,
                operation="copy",
            )

            simulator = NanoporeSimulator(config, enable_monitoring=True)

            # Create file manifest
            file_manifest = simulator._create_singleplex_manifest()

            # Create a mock monitor that stops after processing some files
            mock_monitor = Mock()
            files_processed = [0]

            def record_file_effect(*args, **kwargs):
                files_processed[0] += 1

            mock_monitor.record_file_processed.side_effect = record_file_effect

            def should_stop_effect():
                # Stop after 2 files processed
                return files_processed[0] >= 2

            mock_monitor.should_stop.side_effect = should_stop_effect
            mock_monitor.is_paused.return_value = False
            mock_monitor.start_batch.return_value = time.time()
            mock_monitor.end_batch.return_value = None
            mock_monitor.record_timing.return_value = None
            mock_monitor.add_wait_time.return_value = None

            simulator.progress_monitor = mock_monitor

            # Execute simulation - should stop after processing 2 files
            simulator._execute_simulation(file_manifest, "singleplex")

            # Verify should_stop was called and stopped early
            assert mock_monitor.should_stop.called
            # Should have stopped before processing all 10 files
            assert files_processed[0] < 10

    def test_shutdown_after_pause(self):
        """Test shutdown signal during pause"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            target_dir = Path(tmpdir) / "target"
            source_dir.mkdir()

            # Create test files
            for i in range(5):
                (source_dir / f"test_{i}.fastq").write_text(f"@read{i}\nACGT\n+\n!!!!")

            config = SimulationConfig(
                source_dir=source_dir,
                target_dir=target_dir,
                interval=0.1,
                batch_size=2,
                operation="copy",
            )

            simulator = NanoporeSimulator(config, enable_monitoring=True)
            file_manifest = simulator._create_singleplex_manifest()

            # Mock monitor that pauses once, then allows shutdown
            mock_monitor = Mock()
            paused_count = [0]

            def is_paused_effect():
                paused_count[0] += 1
                # Paused only on first check
                return paused_count[0] == 1

            def should_stop_effect():
                # Stop after pause has been handled
                return paused_count[0] > 1

            mock_monitor.is_paused.side_effect = is_paused_effect
            mock_monitor.should_stop.side_effect = should_stop_effect
            mock_monitor.wait_if_paused.return_value = None
            mock_monitor.start_batch.return_value = time.time()
            mock_monitor.end_batch.return_value = None
            mock_monitor.record_file_processed.return_value = None
            mock_monitor.record_timing.return_value = None

            simulator.progress_monitor = mock_monitor

            simulator._execute_simulation(file_manifest, "singleplex")

            # Verify pause was handled
            assert mock_monitor.wait_if_paused.called

    def test_shutdown_during_interruptible_sleep(self):
        """Test shutdown signal interrupts sleep"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            target_dir = Path(tmpdir) / "target"
            source_dir.mkdir()

            config = SimulationConfig(
                source_dir=source_dir,
                target_dir=target_dir,
                interval=2.0,  # Long interval
                operation="copy",
            )

            simulator = NanoporeSimulator(
                config, enable_monitoring=True, monitor_type="enhanced"
            )

            # Mock monitor that requests shutdown during sleep
            mock_monitor = Mock()
            call_count = [0]

            def should_stop_side_effect():
                call_count[0] += 1
                # Stop after a few checks (during sleep)
                return call_count[0] > 5

            mock_monitor.should_stop.side_effect = should_stop_side_effect
            mock_monitor.is_paused.return_value = False

            simulator.progress_monitor = mock_monitor

            # Test interruptible sleep directly
            start_time = time.time()
            simulator._interruptible_sleep(2.0)
            elapsed = time.time() - start_time

            # Sleep should be interrupted after ~0.5s (5 checks * 0.1s)
            assert elapsed < 1.0
            assert mock_monitor.should_stop.called

    def test_shutdown_before_file_processing(self):
        """Test shutdown check before processing individual file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            target_dir = Path(tmpdir) / "target"
            source_dir.mkdir()

            (source_dir / "test.fastq").write_text("@read1\nACGT\n+\n!!!!")

            config = SimulationConfig(
                source_dir=source_dir,
                target_dir=target_dir,
                interval=0.1,
                operation="copy",
            )

            simulator = NanoporeSimulator(config, enable_monitoring=True)
            simulator.progress_monitor = Mock()
            simulator.progress_monitor.should_stop.return_value = True

            file_info = {
                "source": source_dir / "test.fastq",
                "target": target_dir / "test.fastq",
                "barcode": None,
            }

            # Should return early without processing
            simulator._process_file(file_info)

            # Target should not exist since processing was skipped
            assert not (target_dir / "test.fastq").exists()


class TestPauseResumeInterruption:
    """Test pause/resume during sleep intervals"""

    def test_pause_during_interruptible_sleep(self):
        """Test pause interrupts sleep and resumes"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            target_dir = Path(tmpdir) / "target"
            source_dir.mkdir()

            config = SimulationConfig(
                source_dir=source_dir,
                target_dir=target_dir,
                interval=1.0,
                operation="copy",
            )

            simulator = NanoporeSimulator(
                config, enable_monitoring=True, monitor_type="enhanced"
            )

            # Mock monitor that pauses briefly during sleep
            mock_monitor = Mock()
            pause_count = [0]

            def is_paused_side_effect():
                pause_count[0] += 1
                # Pause briefly during sleep (checks 3-5)
                return 3 <= pause_count[0] <= 5

            mock_monitor.is_paused.side_effect = is_paused_side_effect
            mock_monitor.should_stop.return_value = False
            mock_monitor.wait_if_paused.return_value = None

            simulator.progress_monitor = mock_monitor

            # Test interruptible sleep with pause
            simulator._interruptible_sleep(1.0)

            # Verify pause handling was called
            assert mock_monitor.wait_if_paused.called

    def test_pause_simulation_without_monitoring(self):
        """Test pause when monitoring is disabled"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            target_dir = Path(tmpdir) / "target"
            source_dir.mkdir()

            config = SimulationConfig(
                source_dir=source_dir,
                target_dir=target_dir,
                interval=0.1,
                operation="copy",
            )

            simulator = NanoporeSimulator(config, enable_monitoring=False)
            simulator.progress_monitor = None

            # Should log warning but not crash
            simulator.pause_simulation()
            assert not simulator.is_paused()

    def test_resume_simulation_without_monitoring(self):
        """Test resume when monitoring is disabled"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            target_dir = Path(tmpdir) / "target"
            source_dir.mkdir()

            config = SimulationConfig(
                source_dir=source_dir,
                target_dir=target_dir,
                interval=0.1,
                operation="copy",
            )

            simulator = NanoporeSimulator(config, enable_monitoring=False)
            simulator.progress_monitor = None

            # Should log warning but not crash
            simulator.resume_simulation()
            assert not simulator.is_paused()


class TestParallelProcessingErrorHandling:
    """Test parallel processing with worker failures"""

    def test_parallel_processing_with_file_error(self):
        """Test parallel processing handles file errors"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            target_dir = Path(tmpdir) / "target"
            source_dir.mkdir()

            # Create test file
            (source_dir / "test.fastq").write_text("@read1\nACGT\n+\n!!!!")

            config = SimulationConfig(
                source_dir=source_dir,
                target_dir=target_dir,
                interval=0.1,
                parallel_processing=True,
                worker_count=2,
                operation="copy",
            )

            simulator = NanoporeSimulator(config, enable_monitoring=False)

            # Mock _process_file to raise exception
            with patch.object(
                simulator, "_process_file", side_effect=ValueError("Test error")
            ):
                batch = [
                    {
                        "source": source_dir / "test.fastq",
                        "target": target_dir / "test.fastq",
                        "barcode": None,
                    }
                ]

                # Should raise the exception
                with pytest.raises(ValueError, match="Test error"):
                    simulator._process_batch_parallel(batch)

    def test_parallel_processing_executor_none_fallback(self):
        """Test parallel processing falls back to sequential if executor is None"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            target_dir = Path(tmpdir) / "target"
            source_dir.mkdir()

            (source_dir / "test.fastq").write_text("@read1\nACGT\n+\n!!!!")

            config = SimulationConfig(
                source_dir=source_dir,
                target_dir=target_dir,
                interval=0.1,
                parallel_processing=True,
                operation="copy",
            )

            simulator = NanoporeSimulator(config, enable_monitoring=False)
            simulator.executor = None  # Force executor to None

            batch = [
                {
                    "source": source_dir / "test.fastq",
                    "target": target_dir / "test.fastq",
                    "barcode": None,
                }
            ]

            # Should fall back to sequential processing
            simulator._process_batch_parallel(batch)

            # File should be processed
            assert (target_dir / "test.fastq").exists()

    def test_parallel_processing_empty_batch(self):
        """Test parallel processing with empty batch"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            target_dir = Path(tmpdir) / "target"
            source_dir.mkdir()

            config = SimulationConfig(
                source_dir=source_dir,
                target_dir=target_dir,
                interval=0.1,
                parallel_processing=True,
                operation="copy",
            )

            simulator = NanoporeSimulator(config, enable_monitoring=False)

            # Should handle empty batch gracefully
            simulator._process_batch_parallel([])

    def test_parallel_processing_multiple_errors(self):
        """Test parallel processing with multiple file errors"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            target_dir = Path(tmpdir) / "target"
            source_dir.mkdir()

            # Create test files
            for i in range(3):
                (source_dir / f"test_{i}.fastq").write_text(
                    f"@read{i}\nACGT\n+\n!!!!"
                )

            config = SimulationConfig(
                source_dir=source_dir,
                target_dir=target_dir,
                interval=0.1,
                parallel_processing=True,
                worker_count=3,
                operation="copy",
            )

            simulator = NanoporeSimulator(config, enable_monitoring=False)

            # Mock _process_file to raise different exceptions
            error_count = [0]

            def raising_process_file(file_info):
                error_count[0] += 1
                raise ValueError(f"Error {error_count[0]}")

            with patch.object(simulator, "_process_file", side_effect=raising_process_file):
                batch = [
                    {
                        "source": source_dir / f"test_{i}.fastq",
                        "target": target_dir / f"test_{i}.fastq",
                        "barcode": None,
                    }
                    for i in range(3)
                ]

                # Should raise first exception
                with pytest.raises(ValueError, match="Error"):
                    simulator._process_batch_parallel(batch)


class TestBatchErrorHandling:
    """Test error handling during batch processing"""

    def test_critical_error_stops_simulation(self):
        """Test critical errors stop simulation"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            target_dir = Path(tmpdir) / "target"
            source_dir.mkdir()

            # Create test files
            for i in range(5):
                (source_dir / f"test_{i}.fastq").write_text(f"@read{i}\nACGT\n+\n!!!!")

            config = SimulationConfig(
                source_dir=source_dir,
                target_dir=target_dir,
                interval=0.1,
                batch_size=2,
                operation="copy",
            )

            simulator = NanoporeSimulator(config, enable_monitoring=True)
            file_manifest = simulator._create_singleplex_manifest()

            # Mock monitor
            mock_monitor = Mock()
            mock_monitor.start_batch.return_value = time.time()
            mock_monitor.should_stop.return_value = False
            mock_monitor.is_paused.return_value = False
            mock_monitor.record_error.return_value = None

            simulator.progress_monitor = mock_monitor

            # Mock _process_batch_sequential to raise PermissionError
            with patch.object(
                simulator,
                "_process_batch_sequential",
                side_effect=PermissionError("Access denied"),
            ):
                # Should raise the critical error
                with pytest.raises(PermissionError):
                    simulator._execute_simulation(file_manifest, "singleplex")

                # Verify error was recorded
                assert mock_monitor.record_error.called

    def test_non_critical_error_continues_simulation(self):
        """Test non-critical errors allow simulation to continue"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            target_dir = Path(tmpdir) / "target"
            source_dir.mkdir()

            # Create test files
            for i in range(4):
                (source_dir / f"test_{i}.fastq").write_text(f"@read{i}\nACGT\n+\n!!!!")

            config = SimulationConfig(
                source_dir=source_dir,
                target_dir=target_dir,
                interval=0.1,
                batch_size=2,
                operation="copy",
            )

            simulator = NanoporeSimulator(config, enable_monitoring=True)
            file_manifest = simulator._create_singleplex_manifest()

            # Mock monitor
            mock_monitor = Mock()
            mock_monitor.start_batch.return_value = time.time()
            mock_monitor.should_stop.return_value = False
            mock_monitor.is_paused.return_value = False
            mock_monitor.record_error.return_value = None
            mock_monitor.end_batch.return_value = None
            mock_monitor.add_wait_time.return_value = None

            simulator.progress_monitor = mock_monitor

            call_count = [0]

            def process_batch_with_error(batch):
                call_count[0] += 1
                if call_count[0] == 1:
                    # First batch fails with non-critical error
                    raise RuntimeError("Non-critical error")
                # Second batch succeeds
                for file_info in batch:
                    simulator._process_file(file_info)

            with patch.object(
                simulator,
                "_process_batch_sequential",
                side_effect=process_batch_with_error,
            ):
                # Should NOT raise, simulation continues
                simulator._execute_simulation(file_manifest, "singleplex")

                # Verify error was recorded but simulation continued
                assert mock_monitor.record_error.called
                assert call_count[0] == 2  # Both batches processed


class TestCleanupScenarios:
    """Test resource cleanup in various scenarios"""

    def test_cleanup_with_executor(self):
        """Test cleanup shuts down executor"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            target_dir = Path(tmpdir) / "target"
            source_dir.mkdir()

            config = SimulationConfig(
                source_dir=source_dir,
                target_dir=target_dir,
                interval=0.1,
                parallel_processing=True,
                worker_count=2,
            )

            simulator = NanoporeSimulator(config, enable_monitoring=False)

            assert simulator.executor is not None

            # Call cleanup
            simulator._cleanup()

            # Executor should be None after cleanup
            assert simulator.executor is None

    def test_cleanup_without_executor(self):
        """Test cleanup when no executor exists"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            target_dir = Path(tmpdir) / "target"
            source_dir.mkdir()

            config = SimulationConfig(
                source_dir=source_dir,
                target_dir=target_dir,
                interval=0.1,
                parallel_processing=False,
            )

            simulator = NanoporeSimulator(config, enable_monitoring=False)

            assert simulator.executor is None

            # Should handle gracefully
            simulator._cleanup()

    def test_cleanup_called_on_exception(self):
        """Test cleanup is called even when simulation raises exception"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            target_dir = Path(tmpdir) / "target"
            source_dir.mkdir()

            # Create a test file
            (source_dir / "test.fastq").write_text("@read1\nACGT\n+\n!!!!")

            config = SimulationConfig(
                source_dir=source_dir,
                target_dir=target_dir,
                interval=0.1,
                parallel_processing=True,
                worker_count=2,
                operation="copy",
            )

            simulator = NanoporeSimulator(config, enable_monitoring=False)

            # Verify executor exists
            assert simulator.executor is not None

            # Mock _execute_simulation to raise exception
            with patch.object(
                simulator, "_execute_simulation", side_effect=RuntimeError("Test")
            ):
                with pytest.raises(RuntimeError):
                    simulator.run_simulation()

                # Cleanup should still be called (executor shut down)
                assert simulator.executor is None


class TestFileOperationEdgeCases:
    """Test edge cases in file operations"""

    def test_unknown_operation_type(self):
        """Test error handling for unknown operation type"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            target_dir = Path(tmpdir) / "target"
            source_dir.mkdir()

            (source_dir / "test.fastq").write_text("@read1\nACGT\n+\n!!!!")

            config = SimulationConfig(
                source_dir=source_dir,
                target_dir=target_dir,
                interval=0.1,
                operation="copy",
            )

            simulator = NanoporeSimulator(config, enable_monitoring=True)
            simulator.progress_monitor = Mock()
            simulator.progress_monitor.should_stop.return_value = False
            simulator.progress_monitor.record_error.return_value = None
            simulator.progress_monitor.record_timing.return_value = None

            # Override operation to invalid value
            simulator.config.operation = "invalid_operation"

            file_info = {
                "source": source_dir / "test.fastq",
                "target": target_dir / "test.fastq",
                "barcode": None,
            }

            # Should raise ValueError
            with pytest.raises(ValueError, match="Unknown operation"):
                simulator._process_file(file_info)

            # Error should be recorded
            assert simulator.progress_monitor.record_error.called

    def test_file_operation_with_barcode_logging(self):
        """Test file operation logging includes barcode for multiplex"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            target_dir = Path(tmpdir) / "target"
            source_dir.mkdir()

            (source_dir / "test.fastq").write_text("@read1\nACGT\n+\n!!!!")

            config = SimulationConfig(
                source_dir=source_dir,
                target_dir=target_dir,
                interval=0.1,
                operation="copy",
            )

            simulator = NanoporeSimulator(
                config, enable_monitoring=True, monitor_type="detailed"
            )
            simulator.progress_monitor = Mock()
            simulator.progress_monitor.should_stop.return_value = False
            simulator.progress_monitor.record_file_processed.return_value = None
            simulator.progress_monitor.record_timing.return_value = None

            file_info = {
                "source": source_dir / "test.fastq",
                "target": target_dir / "barcode01" / "test.fastq",
                "barcode": "barcode01",
            }

            # Should process and log with barcode
            simulator._process_file(file_info)

            # File should exist
            assert (target_dir / "barcode01" / "test.fastq").exists()
