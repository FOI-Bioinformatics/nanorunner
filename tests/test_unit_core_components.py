"""Unit tests for core components - testing individual classes in isolation"""

import pytest
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from nanopore_simulator.core.config import SimulationConfig
from nanopore_simulator.core.timing import (
    UniformTimingModel,
    RandomTimingModel,
    PoissonTimingModel,
    AdaptiveTimingModel,
)
from nanopore_simulator.core.detector import FileStructureDetector
from nanopore_simulator.core.monitoring import (
    SimulationMetrics,
    ResourceMetrics,
    ProgressDisplay,
)
from nanopore_simulator.core.adapters import (
    GenericAdapter,
    BUILTIN_ADAPTER_CONFIGS,
)


class TestTimingModels:
    """Unit tests for timing model classes"""

    def test_uniform_timing_model_basic(self):
        """Test UniformTimingModel generates consistent intervals"""
        model = UniformTimingModel(base_interval=2.0)

        # Generate multiple intervals
        intervals = [model.next_interval() for _ in range(10)]

        # All intervals should be exactly the base interval
        assert all(interval == 2.0 for interval in intervals)

    def test_uniform_timing_model_validation(self):
        """Test UniformTimingModel parameter validation"""
        # Valid parameters
        UniformTimingModel(1.0)
        UniformTimingModel(0.1)
        UniformTimingModel(0.0)  # Zero is allowed

        # Invalid parameters
        with pytest.raises(ValueError):
            UniformTimingModel(-1.0)  # Only negative values are invalid

    def test_random_timing_model_basic(self):
        """Test RandomTimingModel generates variable intervals"""
        model = RandomTimingModel(base_interval=2.0, random_factor=0.5)

        # Generate multiple intervals
        intervals = [model.next_interval() for _ in range(20)]

        # Should have some variation
        assert len(set(intervals)) > 1  # Not all the same

        # Should be centered around base interval
        avg_interval = sum(intervals) / len(intervals)
        assert 1.5 <= avg_interval <= 2.5  # Within reasonable range

    def test_random_timing_model_validation(self):
        """Test RandomTimingModel parameter validation"""
        # Valid parameters (parameter is random_factor, not randomness_factor)
        RandomTimingModel(1.0, random_factor=0.2)
        RandomTimingModel(1.0, random_factor=0.0)  # No randomness

        # Invalid parameters
        with pytest.raises(ValueError):
            RandomTimingModel(1.0, random_factor=-0.1)  # Negative randomness
        with pytest.raises(ValueError):
            RandomTimingModel(1.0, random_factor=1.5)  # Randomness > 1.0

    def test_poisson_timing_model_basic(self):
        """Test PoissonTimingModel generates exponential intervals"""
        model = PoissonTimingModel(base_interval=1.0)

        # Generate intervals
        intervals = [model.next_interval() for _ in range(50)]

        # Should have variation (exponential distribution)
        assert len(set(intervals)) > 10

        # Most intervals should be short (exponential property)
        short_intervals = [i for i in intervals if i < 2.0]
        assert len(short_intervals) > len(intervals) * 0.6  # At least 60% short

    def test_poisson_timing_model_bursts(self):
        """Test PoissonTimingModel burst behavior"""
        model = PoissonTimingModel(
            base_interval=1.0, burst_probability=0.5, burst_rate_multiplier=3.0
        )

        # Generate many intervals to test burst behavior
        intervals = [model.next_interval() for _ in range(100)]

        # Should have some very short intervals (bursts)
        very_short = [i for i in intervals if i < 0.3]
        assert len(very_short) > 0  # Should have some burst intervals

    def test_adaptive_timing_model_basic(self):
        """Test AdaptiveTimingModel basic functionality"""
        model = AdaptiveTimingModel(base_interval=1.0, adaptation_rate=0.2)

        # Initial intervals should be positive
        initial_intervals = [model.next_interval() for _ in range(5)]
        assert all(interval > 0 for interval in initial_intervals)

        # Should have interval history
        assert hasattr(model, "interval_history")
        assert len(model.interval_history) > 0

    def test_adaptive_timing_model_adaptation(self):
        """Test AdaptiveTimingModel adapts over time"""
        model = AdaptiveTimingModel(
            base_interval=1.0, adaptation_rate=0.5, history_size=5
        )

        # Generate intervals to build history
        initial_intervals = [model.next_interval() for _ in range(10)]

        # Model should have built some interval history
        assert hasattr(model, "interval_history")
        assert len(model.interval_history) > 0

        # Current mean should be influenced by history
        assert hasattr(model, "current_mean")
        assert model.current_mean > 0

    def test_adaptive_timing_model_validation(self):
        """Test AdaptiveTimingModel parameter validation"""
        # Valid parameters
        AdaptiveTimingModel(1.0, 0.1, 10)

        # Invalid parameters
        with pytest.raises(ValueError):
            AdaptiveTimingModel(1.0, -0.1, 10)  # Negative adaptation rate
        with pytest.raises(ValueError):
            AdaptiveTimingModel(1.0, 1.5, 10)  # Adaptation rate > 1.0
        with pytest.raises(ValueError):
            AdaptiveTimingModel(1.0, 0.1, 0)  # History size < 1


class TestSimulationConfig:
    """Unit tests for SimulationConfig validation"""

    def test_basic_config_creation(self):
        """Test basic SimulationConfig creation"""
        config = SimulationConfig(
            source_dir="/tmp/source", target_dir="/tmp/target", interval=1.0
        )

        # Config stores paths as strings, not Path objects
        assert config.source_dir == "/tmp/source"
        assert config.target_dir == "/tmp/target"
        assert config.interval == 1.0

    def test_timing_model_validation(self):
        """Test timing model parameter validation"""
        # Valid timing models
        for model in ["uniform", "random", "poisson", "adaptive"]:
            config = SimulationConfig(
                source_dir="/tmp/source", target_dir="/tmp/target", timing_model=model
            )
            assert config.timing_model == model

        # Invalid timing model
        with pytest.raises(ValueError):
            SimulationConfig(
                source_dir="/tmp/source",
                target_dir="/tmp/target",
                timing_model="invalid_model",
            )

    def test_interval_validation(self):
        """Test interval parameter validation"""
        # Valid intervals
        SimulationConfig("/tmp/source", "/tmp/target", interval=0.1)
        SimulationConfig("/tmp/source", "/tmp/target", interval=10.0)
        SimulationConfig("/tmp/source", "/tmp/target", interval=0.0)  # Zero allowed

        # Invalid intervals (only negative not allowed)
        with pytest.raises(ValueError):
            SimulationConfig("/tmp/source", "/tmp/target", interval=-1.0)

    def test_batch_size_validation(self):
        """Test batch size parameter validation"""
        # Valid batch sizes
        SimulationConfig("/tmp/source", "/tmp/target", batch_size=1)
        SimulationConfig("/tmp/source", "/tmp/target", batch_size=100)

        # Invalid batch sizes
        with pytest.raises(ValueError):
            SimulationConfig("/tmp/source", "/tmp/target", batch_size=0)
        with pytest.raises(ValueError):
            SimulationConfig("/tmp/source", "/tmp/target", batch_size=-5)

    def test_worker_count_validation(self):
        """Test worker count validation"""
        # Valid worker counts
        SimulationConfig("/tmp/source", "/tmp/target", worker_count=1)
        SimulationConfig("/tmp/source", "/tmp/target", worker_count=8)

        # Invalid worker counts
        with pytest.raises(ValueError):
            SimulationConfig("/tmp/source", "/tmp/target", worker_count=0)
        with pytest.raises(ValueError):
            SimulationConfig("/tmp/source", "/tmp/target", worker_count=-1)

    def test_timing_model_params_validation(self):
        """Test timing model parameters validation"""
        # Valid random params
        config = SimulationConfig(
            "/tmp/source",
            "/tmp/target",
            timing_model="random",
            timing_model_params={"randomness_factor": 0.3},
        )
        assert config.timing_model_params["randomness_factor"] == 0.3

        # Valid poisson params
        config = SimulationConfig(
            "/tmp/source",
            "/tmp/target",
            timing_model="poisson",
            timing_model_params={
                "burst_probability": 0.2,
                "burst_rate_multiplier": 2.0,
            },
        )
        assert config.timing_model_params["burst_probability"] == 0.2


class TestFileStructureDetector:
    """Unit tests for FileStructureDetector"""

    def test_empty_directory_detection(self):
        """Test detection on empty directory"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # FileStructureDetector raises ValueError for empty directories
            with pytest.raises(ValueError, match="No sequencing files found"):
                FileStructureDetector.detect_structure(Path(temp_dir))

    def test_singleplex_detection(self):
        """Test detection of singleplex structure"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create files directly in root
            (temp_path / "file1.fastq").touch()
            (temp_path / "file2.fastq").touch()
            (temp_path / "file3.fq.gz").touch()

            # FileStructureDetector uses class methods
            structure_type = FileStructureDetector.detect_structure(temp_path)

            assert structure_type == "singleplex"

    def test_multiplex_detection(self):
        """Test detection of multiplex structure"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create barcode directories
            for i in range(1, 4):
                barcode_dir = temp_path / f"barcode{i:02d}"
                barcode_dir.mkdir()
                (barcode_dir / f"file{i}.fastq").touch()
                (barcode_dir / f"file{i}_2.fastq").touch()

            # FileStructureDetector uses class methods
            structure_type = FileStructureDetector.detect_structure(temp_path)

            assert structure_type == "multiplex"

    def test_file_pattern_detection(self):
        """Test file pattern detection"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create files with different extensions
            (temp_path / "file1.fastq").touch()
            (temp_path / "file2.fq").touch()
            (temp_path / "file3.fastq.gz").touch()
            (temp_path / "file4.pod5").touch()
            (temp_path / "readme.txt").touch()  # Should be ignored

            # FileStructureDetector uses class methods
            structure_type = FileStructureDetector.detect_structure(temp_path)

            # Should detect singleplex structure with supported files
            assert structure_type == "singleplex"


class TestMonitoringMetrics:
    """Unit tests for monitoring and metrics classes"""

    def test_simulation_metrics_basic(self):
        """Test basic SimulationMetrics functionality"""
        metrics = SimulationMetrics(files_total=10)

        # Initial state
        assert metrics.files_processed == 0
        assert metrics.files_total == 10
        assert metrics.progress_percentage == 0.0
        assert not metrics.is_complete

        # Update progress
        metrics.files_processed = 5
        assert metrics.progress_percentage == 50.0
        assert not metrics.is_complete

        # Complete
        metrics.files_processed = 10
        assert metrics.progress_percentage == 100.0
        assert metrics.is_complete

    def test_simulation_metrics_elapsed_time(self):
        """Test elapsed time calculation"""
        start_time = time.time()
        metrics = SimulationMetrics(start_time=start_time)

        # Mock some time passing
        time.sleep(0.1)
        elapsed = metrics.elapsed_time
        assert 0.05 <= elapsed <= 0.5  # Should be around 0.1 seconds

        # Test with end time set
        metrics.end_time = start_time + 2.0
        assert metrics.elapsed_time == 2.0

    def test_simulation_metrics_throughput(self):
        """Test throughput calculations"""
        metrics = SimulationMetrics(files_total=100, start_time=time.time() - 10.0)
        metrics.files_processed = 50
        metrics.total_bytes_processed = 1024 * 1024  # 1 MB

        # Need to call update_throughput to calculate
        metrics.update_throughput()

        # Test file throughput
        throughput = metrics.throughput_files_per_sec
        assert 4.0 <= throughput <= 6.0  # ~5 files/sec

        # Test bytes throughput
        bytes_throughput = metrics.throughput_bytes_per_sec
        assert 100000 <= bytes_throughput <= 120000  # ~100KB/sec

    def test_simulation_metrics_zero_division_safety(self):
        """Test metrics handle zero division safely"""
        metrics = SimulationMetrics(files_total=0)

        # Should not raise errors
        assert metrics.progress_percentage == 0.0
        assert metrics.is_complete == True  # 0/0 is considered complete
        assert metrics.average_file_size >= 0

    def test_resource_metrics_basic(self):
        """Test ResourceMetrics basic functionality"""
        metrics = ResourceMetrics(
            cpu_percent=75.5, memory_percent=45.2, memory_used_mb=1024.0
        )

        assert metrics.cpu_percent == 75.5
        assert metrics.memory_percent == 45.2
        assert metrics.memory_used_mb == 1024.0

        # Test to_dict conversion
        data = metrics.to_dict()
        assert data["cpu_percent"] == 75.5
        assert data["memory_percent"] == 45.2

    def test_progress_display_formatting(self):
        """Test ProgressDisplay formatting utilities"""
        # Test time formatting (uses decimal format like "1.5m")
        assert ProgressDisplay.format_time(0) == "0.0s"
        assert ProgressDisplay.format_time(90) == "1.5m"  # Not "1m 30s"
        assert ProgressDisplay.format_time(3665) == "1.0h"  # Approximately 1 hour

        # Test bytes formatting
        assert ProgressDisplay.format_bytes(0) == "0.0 B"
        assert ProgressDisplay.format_bytes(1024) == "1.0 KB"
        assert ProgressDisplay.format_bytes(1024 * 1024) == "1.0 MB"
        assert ProgressDisplay.format_bytes(1024 * 1024 * 1024) == "1.0 GB"

        # Test progress bar creation
        bar = ProgressDisplay.create_progress_bar(50.0, width=10)
        assert "50.0%" in bar  # Should contain percentage

        bar_complete = ProgressDisplay.create_progress_bar(100.0, width=10)
        assert "100.0%" in bar_complete  # Should show completion


class TestPipelineAdapters:
    """Unit tests for pipeline adapter classes"""

    def test_nanometa_adapter_basic(self):
        """Test nanometa adapter basic functionality"""
        adapter = GenericAdapter(BUILTIN_ADAPTER_CONFIGS["nanometa"])

        assert adapter.requirements.name == "nanometa"
        assert "fastq" in adapter.requirements.expected_patterns[0]
        assert "pod5" in adapter.requirements.expected_patterns[-1]

    def test_nanometa_adapter_file_support(self):
        """Test nanometa adapter file support detection"""
        adapter = GenericAdapter(BUILTIN_ADAPTER_CONFIGS["nanometa"])

        # Should support these files
        assert adapter.supports_file(Path("test.fastq"))
        assert adapter.supports_file(Path("test.fq"))
        assert adapter.supports_file(Path("test.fastq.gz"))
        assert adapter.supports_file(Path("test.pod5"))

        # Should not support these files
        assert not adapter.supports_file(Path("test.txt"))
        assert not adapter.supports_file(Path("test.bam"))
        assert not adapter.supports_file(Path("test.sam"))

    def test_nanometa_adapter_barcode_detection(self):
        """Test nanometa adapter barcode directory detection"""
        adapter = GenericAdapter(BUILTIN_ADAPTER_CONFIGS["nanometa"])

        # Should recognize these as barcode directories
        assert adapter.is_barcode_directory(Path("barcode01"))
        assert adapter.is_barcode_directory(Path("barcode12"))
        assert adapter.is_barcode_directory(Path("BC01"))
        assert adapter.is_barcode_directory(Path("bc05"))
        assert adapter.is_barcode_directory(Path("unclassified"))

        # Should not recognize these
        assert not adapter.is_barcode_directory(Path("data"))
        assert not adapter.is_barcode_directory(Path("results"))
        assert not adapter.is_barcode_directory(Path("temp"))

    def test_kraken_adapter_basic(self):
        """Test Kraken adapter basic functionality"""
        adapter = GenericAdapter(BUILTIN_ADAPTER_CONFIGS["kraken"])

        assert adapter.requirements.name == "kraken"
        assert any(
            "fastq" in pattern for pattern in adapter.requirements.expected_patterns
        )

        # Should support FASTQ files but not POD5
        assert adapter.supports_file(Path("test.fastq"))
        assert not adapter.supports_file(Path("test.pod5"))

    def test_generic_adapter_creation(self):
        """Test GenericAdapter creation with custom config"""
        config = {
            "name": "custom_pipeline",
            "description": "My custom pipeline",
            "patterns": ["*.bam", "*.sam"],
            "min_files": 2,
        }

        adapter = GenericAdapter(config)

        assert adapter.requirements.name == "custom_pipeline"
        assert adapter.requirements.description == "My custom pipeline"
        assert "*.bam" in adapter.requirements.expected_patterns
        assert "*.sam" in adapter.requirements.expected_patterns
        assert adapter.requirements.validation_rules["min_files"] == 2

    def test_adapter_validation_structure(self):
        """Test adapter structure validation"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create a simple structure
            (temp_path / "test.fastq").touch()
            (temp_path / "test2.fastq").touch()

            adapter = GenericAdapter(BUILTIN_ADAPTER_CONFIGS["nanometa"])

            # Should validate successfully
            assert adapter.validate_structure(temp_path) == True

            # Test validation report
            report = adapter.get_validation_report(temp_path)
            assert report["valid"] == True
            assert report["structure_valid"] == True
            assert len(report["files_found"]) >= 2

    def test_adapter_validation_empty_directory(self):
        """Test adapter validation on empty directory"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            adapter = GenericAdapter(BUILTIN_ADAPTER_CONFIGS["nanometa"])

            # Should fail validation
            assert adapter.validate_structure(temp_path) == False

            report = adapter.get_validation_report(temp_path)
            assert report["valid"] == False


class TestSimulationConfigSpecies:
    """Unit tests for species-based generation configuration"""

    def test_species_inputs_field(self, tmp_path):
        """Test species_inputs field accepts list of species names"""
        config = SimulationConfig(
            target_dir=tmp_path,
            operation="generate",
            species_inputs=["Escherichia coli", "Staphylococcus aureus"],
            sample_type="pure",
        )
        assert config.species_inputs == ["Escherichia coli", "Staphylococcus aureus"]
        assert config.sample_type == "pure"

    def test_mock_name_field(self, tmp_path):
        """Test mock_name field for preset mock communities"""
        config = SimulationConfig(
            target_dir=tmp_path,
            operation="generate",
            mock_name="zymo_d6300",
            sample_type="mixed",
        )
        assert config.mock_name == "zymo_d6300"
        assert config.sample_type == "mixed"

    def test_abundances_field(self, tmp_path):
        """Test abundances field for custom abundance ratios"""
        config = SimulationConfig(
            target_dir=tmp_path,
            operation="generate",
            species_inputs=["E. coli", "S. aureus"],
            abundances=[0.7, 0.3],
            sample_type="mixed",
        )
        assert config.abundances == [0.7, 0.3]

    def test_abundances_must_match_species_count(self, tmp_path):
        """Test that abundances count must match species/taxid count"""
        with pytest.raises(ValueError, match="abundances"):
            SimulationConfig(
                target_dir=tmp_path,
                operation="generate",
                species_inputs=["E. coli", "S. aureus"],
                abundances=[0.5],  # Wrong count
                sample_type="mixed",
            )

    def test_abundances_must_sum_to_one(self, tmp_path):
        """Test that abundances must sum to 1.0"""
        with pytest.raises(ValueError, match="sum to 1.0"):
            SimulationConfig(
                target_dir=tmp_path,
                operation="generate",
                species_inputs=["E. coli", "S. aureus"],
                abundances=[0.5, 0.3],  # Sums to 0.8
                sample_type="mixed",
            )

    def test_sample_type_default_for_mock(self, tmp_path):
        """Test sample_type defaults to mixed for mock communities"""
        config = SimulationConfig(
            target_dir=tmp_path,
            operation="generate",
            mock_name="zymo_d6300",
        )
        assert config.sample_type == "mixed"  # Default for mock

    def test_sample_type_default_for_species(self, tmp_path):
        """Test sample_type defaults to pure for species inputs"""
        config = SimulationConfig(
            target_dir=tmp_path,
            operation="generate",
            species_inputs=["E. coli", "S. aureus"],
        )
        assert config.sample_type == "pure"  # Default for species

    def test_invalid_sample_type(self, tmp_path):
        """Test that invalid sample_type raises ValueError"""
        with pytest.raises(ValueError, match="sample_type"):
            SimulationConfig(
                target_dir=tmp_path,
                operation="generate",
                species_inputs=["E. coli"],
                sample_type="invalid",
            )
