"""Comprehensive config validation tests to improve coverage"""

import pytest
from pathlib import Path
import tempfile

from nanopore_simulator.core.config import SimulationConfig


class TestConfigValidationCoverage:
    """Test config validation edge cases and error conditions"""

    def setup_method(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

        # Create sample directories
        self.source_dir = self.temp_path / "source"
        self.source_dir.mkdir()
        self.target_dir = self.temp_path / "target"

    def teardown_method(self):
        """Clean up test fixtures"""
        self.temp_dir.cleanup()

    def test_negative_interval_validation(self):
        """Test validation error for negative interval"""
        with pytest.raises(ValueError, match="interval must be non-negative"):
            SimulationConfig(
                source_dir=self.source_dir,
                target_dir=self.target_dir,
                interval=-1.0,  # Invalid negative interval
            )

    def test_invalid_batch_size_validation(self):
        """Test validation error for invalid batch size"""
        with pytest.raises(ValueError, match="batch_size must be at least 1"):
            SimulationConfig(
                source_dir=self.source_dir,
                target_dir=self.target_dir,
                batch_size=0,  # Invalid batch size
            )

    def test_invalid_worker_count_validation(self):
        """Test validation error for invalid worker count"""
        with pytest.raises(ValueError, match="worker_count must be at least 1"):
            SimulationConfig(
                source_dir=self.source_dir,
                target_dir=self.target_dir,
                worker_count=0,  # Invalid worker count
            )

    def test_invalid_timing_model_validation(self):
        """Test validation error for invalid timing model"""
        with pytest.raises(ValueError, match="timing_model must be one of"):
            SimulationConfig(
                source_dir=self.source_dir,
                target_dir=self.target_dir,
                timing_model="invalid_model",  # Invalid timing model
            )

    def test_random_model_invalid_random_factor_validation(self):
        """Test validation error for invalid random_factor in random model"""
        # Test random_factor too low
        with pytest.raises(
            ValueError, match="random_factor must be between 0.0 and 1.0"
        ):
            SimulationConfig(
                source_dir=self.source_dir,
                target_dir=self.target_dir,
                timing_model="random",
                timing_model_params={"random_factor": -0.1},  # Invalid: too low
            )

        # Test random_factor too high
        with pytest.raises(
            ValueError, match="random_factor must be between 0.0 and 1.0"
        ):
            SimulationConfig(
                source_dir=self.source_dir,
                target_dir=self.target_dir,
                timing_model="random",
                timing_model_params={"random_factor": 1.5},  # Invalid: too high
            )

    def test_poisson_model_invalid_burst_probability_validation(self):
        """Test validation error for invalid burst_probability in poisson model"""
        # Test burst_probability too low
        with pytest.raises(
            ValueError, match="burst_probability must be between 0.0 and 1.0"
        ):
            SimulationConfig(
                source_dir=self.source_dir,
                target_dir=self.target_dir,
                timing_model="poisson",
                timing_model_params={"burst_probability": -0.1},  # Invalid: too low
            )

        # Test burst_probability too high
        with pytest.raises(
            ValueError, match="burst_probability must be between 0.0 and 1.0"
        ):
            SimulationConfig(
                source_dir=self.source_dir,
                target_dir=self.target_dir,
                timing_model="poisson",
                timing_model_params={"burst_probability": 1.5},  # Invalid: too high
            )

    def test_poisson_model_invalid_burst_rate_multiplier_validation(self):
        """Test validation error for invalid burst_rate_multiplier in poisson model"""
        with pytest.raises(ValueError, match="burst_rate_multiplier must be positive"):
            SimulationConfig(
                source_dir=self.source_dir,
                target_dir=self.target_dir,
                timing_model="poisson",
                timing_model_params={
                    "burst_rate_multiplier": -1.0
                },  # Invalid: negative
            )

        with pytest.raises(ValueError, match="burst_rate_multiplier must be positive"):
            SimulationConfig(
                source_dir=self.source_dir,
                target_dir=self.target_dir,
                timing_model="poisson",
                timing_model_params={"burst_rate_multiplier": 0.0},  # Invalid: zero
            )

    def test_adaptive_model_invalid_adaptation_rate_validation(self):
        """Test validation error for invalid adaptation_rate in adaptive model"""
        # Test adaptation_rate too low
        with pytest.raises(
            ValueError, match="adaptation_rate must be between 0.0 and 1.0"
        ):
            SimulationConfig(
                source_dir=self.source_dir,
                target_dir=self.target_dir,
                timing_model="adaptive",
                timing_model_params={"adaptation_rate": -0.1},  # Invalid: too low
            )

        # Test adaptation_rate too high
        with pytest.raises(
            ValueError, match="adaptation_rate must be between 0.0 and 1.0"
        ):
            SimulationConfig(
                source_dir=self.source_dir,
                target_dir=self.target_dir,
                timing_model="adaptive",
                timing_model_params={"adaptation_rate": 1.5},  # Invalid: too high
            )

    def test_adaptive_model_invalid_history_size_validation(self):
        """Test validation error for invalid history_size in adaptive model"""
        with pytest.raises(ValueError, match="history_size must be at least 1"):
            SimulationConfig(
                source_dir=self.source_dir,
                target_dir=self.target_dir,
                timing_model="adaptive",
                timing_model_params={"history_size": 0},  # Invalid: zero
            )

        with pytest.raises(ValueError, match="history_size must be at least 1"):
            SimulationConfig(
                source_dir=self.source_dir,
                target_dir=self.target_dir,
                timing_model="adaptive",
                timing_model_params={"history_size": -5},  # Invalid: negative
            )

    def test_invalid_operation_validation(self):
        """Test validation error for invalid operation"""
        with pytest.raises(ValueError, match="operation must be 'copy', 'link', or 'generate'"):
            SimulationConfig(
                source_dir=self.source_dir,
                target_dir=self.target_dir,
                operation="invalid_operation",  # Invalid operation
            )

    def test_invalid_force_structure_validation(self):
        """Test validation error for invalid force_structure"""
        with pytest.raises(
            ValueError, match="force_structure must be 'singleplex' or 'multiplex'"
        ):
            SimulationConfig(
                source_dir=self.source_dir,
                target_dir=self.target_dir,
                force_structure="invalid_structure",  # Invalid force structure
            )

    def test_get_timing_model_config_functionality(self):
        """Test get_timing_model_config method functionality"""
        # Test with uniform model
        config = SimulationConfig(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            timing_model="uniform",
            interval=5.0,
        )

        timing_config = config.get_timing_model_config()
        assert timing_config["model_type"] == "uniform"
        assert timing_config["base_interval"] == 5.0

        # Test with random model and parameters
        config = SimulationConfig(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            timing_model="random",
            interval=3.0,
            timing_model_params={"random_factor": 0.5},
        )

        timing_config = config.get_timing_model_config()
        assert timing_config["model_type"] == "random"
        assert timing_config["base_interval"] == 3.0
        assert timing_config["random_factor"] == 0.5

        # Test with poisson model and parameters
        config = SimulationConfig(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            timing_model="poisson",
            interval=2.0,
            timing_model_params={
                "burst_probability": 0.2,
                "burst_rate_multiplier": 3.0,
            },
        )

        timing_config = config.get_timing_model_config()
        assert timing_config["model_type"] == "poisson"
        assert timing_config["base_interval"] == 2.0
        assert timing_config["burst_probability"] == 0.2
        assert timing_config["burst_rate_multiplier"] == 3.0

        # Test with adaptive model and parameters
        config = SimulationConfig(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            timing_model="adaptive",
            interval=4.0,
            timing_model_params={"adaptation_rate": 0.3, "history_size": 15},
        )

        timing_config = config.get_timing_model_config()
        assert timing_config["model_type"] == "adaptive"
        assert timing_config["base_interval"] == 4.0
        assert timing_config["adaptation_rate"] == 0.3
        assert timing_config["history_size"] == 15

    def test_valid_edge_case_configurations(self):
        """Test valid edge case configurations"""
        # Test zero interval (valid)
        config = SimulationConfig(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            interval=0.0,  # Valid: zero interval
        )
        assert config.interval == 0.0

        # Test valid boundary values for random model
        config = SimulationConfig(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            timing_model="random",
            timing_model_params={"random_factor": 0.0},  # Valid: minimum
        )
        assert config.timing_model_params["random_factor"] == 0.0

        config = SimulationConfig(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            timing_model="random",
            timing_model_params={"random_factor": 1.0},  # Valid: maximum
        )
        assert config.timing_model_params["random_factor"] == 1.0

        # Test valid boundary values for poisson model
        config = SimulationConfig(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            timing_model="poisson",
            timing_model_params={
                "burst_probability": 0.0,  # Valid: minimum
                "burst_rate_multiplier": 0.01,  # Valid: very small positive
            },
        )
        assert config.timing_model_params["burst_probability"] == 0.0
        assert config.timing_model_params["burst_rate_multiplier"] == 0.01

        config = SimulationConfig(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            timing_model="poisson",
            timing_model_params={
                "burst_probability": 1.0,  # Valid: maximum
                "burst_rate_multiplier": 100.0,  # Valid: large value
            },
        )
        assert config.timing_model_params["burst_probability"] == 1.0
        assert config.timing_model_params["burst_rate_multiplier"] == 100.0

        # Test valid boundary values for adaptive model
        config = SimulationConfig(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            timing_model="adaptive",
            timing_model_params={
                "adaptation_rate": 0.0,  # Valid: minimum
                "history_size": 1,  # Valid: minimum
            },
        )
        assert config.timing_model_params["adaptation_rate"] == 0.0
        assert config.timing_model_params["history_size"] == 1

        config = SimulationConfig(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            timing_model="adaptive",
            timing_model_params={
                "adaptation_rate": 1.0,  # Valid: maximum
                "history_size": 1000,  # Valid: large value
            },
        )
        assert config.timing_model_params["adaptation_rate"] == 1.0
        assert config.timing_model_params["history_size"] == 1000
