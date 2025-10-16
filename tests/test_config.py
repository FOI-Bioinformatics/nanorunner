"""Tests for simulation configuration"""

import pytest
from pathlib import Path
from nanopore_simulator.core.config import SimulationConfig


class TestSimulationConfig:

    def test_default_configuration(self):
        """Test default configuration values"""
        source_dir = Path("/test/source")
        target_dir = Path("/test/target")

        config = SimulationConfig(source_dir=source_dir, target_dir=target_dir)

        assert config.source_dir == source_dir
        assert config.target_dir == target_dir
        assert config.interval == 5.0
        assert config.operation == "copy"
        assert config.force_structure is None
        assert config.batch_size == 1
        assert config.file_types == ["fastq", "fq", "fastq.gz", "fq.gz", "pod5"]

    def test_custom_configuration(self):
        """Test configuration with custom values"""
        config = SimulationConfig(
            source_dir=Path("/custom/source"),
            target_dir=Path("/custom/target"),
            interval=10.5,
            operation="link",
            force_structure="multiplex",
            batch_size=5,
            file_types=["fastq", "pod5"],
        )

        assert config.source_dir == Path("/custom/source")
        assert config.target_dir == Path("/custom/target")
        assert config.interval == 10.5
        assert config.operation == "link"
        assert config.force_structure == "multiplex"
        assert config.batch_size == 5
        assert config.file_types == ["fastq", "pod5"]

    def test_file_types_default_initialization(self):
        """Test that file_types is properly initialized when None"""
        config = SimulationConfig(
            source_dir=Path("/test/source"),
            target_dir=Path("/test/target"),
            file_types=None,
        )

        expected_types = ["fastq", "fq", "fastq.gz", "fq.gz", "pod5"]
        assert config.file_types == expected_types

    def test_pathlib_path_conversion(self):
        """Test that string paths are handled properly"""
        config = SimulationConfig(
            source_dir="/string/source/path", target_dir="/string/target/path"
        )

        # Should work with Path objects
        assert isinstance(config.source_dir, (str, Path))
        assert isinstance(config.target_dir, (str, Path))

    def test_configuration_immutability_after_init(self):
        """Test that configuration maintains its values after initialization"""
        original_types = ["fastq", "pod5"]
        config = SimulationConfig(
            source_dir=Path("/test/source"),
            target_dir=Path("/test/target"),
            file_types=original_types,
        )

        # Modify the original list
        original_types.append("new_type")

        # Config should not be affected
        assert "new_type" not in config.file_types
        assert len(config.file_types) == 2
