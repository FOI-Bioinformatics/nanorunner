"""Configuration fixtures for testing.

This module provides reusable configuration fixtures for testing various
NanoRunner simulation scenarios, timing models, and system configurations.
"""

import pytest
from pathlib import Path
from typing import Dict, Any, Optional
from unittest.mock import MagicMock

from nanopore_simulator.core.config import SimulationConfig


@pytest.fixture
def basic_config(tmp_path):
    """Basic simulation configuration for general testing.

    Returns:
        SimulationConfig with minimal required parameters
    """
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()

    return SimulationConfig(
        source_dir=source_dir,
        target_dir=target_dir,
        interval=1.0,
        operation="copy",
        batch_size=1,
        timing_model="uniform",
    )


@pytest.fixture
def parallel_config(tmp_path):
    """Configuration for parallel processing testing.

    Returns:
        SimulationConfig optimized for parallel processing tests
    """
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()

    return SimulationConfig(
        source_dir=source_dir,
        target_dir=target_dir,
        interval=0.5,
        operation="copy",
        batch_size=3,
        timing_model="uniform",
        parallel_processing=True,
        worker_count=4,
    )


@pytest.fixture
def monitoring_config(tmp_path):
    """Configuration for monitoring system testing.

    Returns:
        SimulationConfig with monitoring optimizations
    """
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()

    return SimulationConfig(
        source_dir=source_dir,
        target_dir=target_dir,
        interval=0.1,  # Fast for monitoring tests
        operation="copy",
        batch_size=2,
        timing_model="uniform",
    )


@pytest.fixture
def profile_configs(tmp_path):
    """Dictionary of configurations for different profile testing.

    Returns:
        Dict containing various profile-based configurations
    """
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()

    base_params = {
        "source_dir": source_dir,
        "target_dir": target_dir,
        "operation": "copy",
    }

    return {
        "bursty": SimulationConfig(
            **base_params,
            interval=2.0,
            batch_size=1,
            timing_model="uniform",
            parallel_processing=False,
        ),
        "high_throughput": SimulationConfig(
            **base_params,
            interval=1.0,
            batch_size=5,
            timing_model="poisson",
            parallel_processing=True,
            worker_count=8,
            timing_model_params={
                "burst_probability": 0.15,
                "burst_rate_multiplier": 3.0,
            },
        ),
        "development": SimulationConfig(
            **base_params,
            interval=0.5,
            batch_size=2,
            timing_model="random",
            timing_model_params={"random_factor": 0.3},
        ),
        "gradual_drift": SimulationConfig(
            **base_params,
            interval=10.0,
            batch_size=1,
            timing_model="adaptive",
            timing_model_params={"adaptation_rate": 0.2, "history_size": 10},
        ),
    }


# Timing Model Configuration Fixtures


@pytest.fixture
def uniform_timing_config(tmp_path):
    """Configuration with uniform timing model.

    Returns:
        SimulationConfig configured for uniform timing
    """
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()

    return SimulationConfig(
        source_dir=source_dir,
        target_dir=target_dir,
        interval=5.0,
        timing_model="uniform",
    )


@pytest.fixture
def random_timing_config(tmp_path):
    """Configuration with random timing model.

    Returns:
        SimulationConfig configured for random timing with 30% variation
    """
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()

    return SimulationConfig(
        source_dir=source_dir,
        target_dir=target_dir,
        interval=3.0,
        timing_model="random",
        timing_model_params={"random_factor": 0.3},
    )


@pytest.fixture
def poisson_timing_config(tmp_path):
    """Configuration with Poisson timing model.

    Returns:
        SimulationConfig configured for Poisson timing with burst behavior
    """
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()

    return SimulationConfig(
        source_dir=source_dir,
        target_dir=target_dir,
        interval=4.0,
        timing_model="poisson",
        timing_model_params={"burst_probability": 0.2, "burst_rate_multiplier": 2.5},
    )


@pytest.fixture
def adaptive_timing_config(tmp_path):
    """Configuration with adaptive timing model.

    Returns:
        SimulationConfig configured for adaptive timing
    """
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()

    return SimulationConfig(
        source_dir=source_dir,
        target_dir=target_dir,
        interval=2.0,
        timing_model="adaptive",
        timing_model_params={"adaptation_rate": 0.25, "history_size": 5},
    )


# Edge Case Configuration Fixtures


@pytest.fixture
def minimal_config(tmp_path):
    """Minimal valid configuration for boundary testing.

    Returns:
        SimulationConfig with minimal valid parameters
    """
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()

    return SimulationConfig(
        source_dir=source_dir,
        target_dir=target_dir,
        interval=0.1,  # Minimum practical interval
        batch_size=1,
        timing_model="uniform",
    )


@pytest.fixture
def maximal_config(tmp_path):
    """Configuration with maximum reasonable parameters.

    Returns:
        SimulationConfig with high-scale parameters
    """
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()

    return SimulationConfig(
        source_dir=source_dir,
        target_dir=target_dir,
        interval=60.0,  # Long interval
        batch_size=50,  # Large batch
        timing_model="adaptive",
        parallel_processing=True,
        worker_count=16,  # High worker count
        timing_model_params={"adaptation_rate": 0.5, "history_size": 20},
    )


@pytest.fixture
def invalid_config_params(tmp_path):
    """Parameters that should cause configuration validation errors.

    Returns:
        Dict containing various invalid parameter sets
    """
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()

    base_params = {"source_dir": source_dir, "target_dir": target_dir}

    return {
        "negative_interval": {**base_params, "interval": -1.0},
        "zero_batch_size": {**base_params, "batch_size": 0},
        "negative_worker_count": {**base_params, "worker_count": -1},
        "invalid_timing_model": {**base_params, "timing_model": "invalid_model"},
        "invalid_operation": {**base_params, "operation": "invalid_operation"},
        "invalid_structure": {**base_params, "force_structure": "invalid_structure"},
    }


# Pipeline-Specific Configuration Fixtures


@pytest.fixture
def nanometanf_config(tmp_path):
    """Configuration optimized for nanometanf pipeline testing.

    Returns:
        SimulationConfig optimized for nanometanf integration
    """
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()

    return SimulationConfig(
        source_dir=source_dir,
        target_dir=target_dir,
        interval=5.0,  # 5-second intervals like nanometanf expects
        batch_size=10,  # Batch processing for efficiency
        timing_model="poisson",  # Realistic sequencing timing
        operation="copy",  # nanometanf needs actual files
        timing_model_params={"burst_probability": 0.1, "burst_rate_multiplier": 2.0},
    )


@pytest.fixture
def kraken_config(tmp_path):
    """Configuration optimized for Kraken pipeline testing.

    Returns:
        SimulationConfig suitable for Kraken workflow testing
    """
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()

    return SimulationConfig(
        source_dir=source_dir,
        target_dir=target_dir,
        interval=3.0,
        batch_size=5,
        timing_model="uniform",  # Consistent for reproducible testing
        operation="copy",
    )


@pytest.fixture
def miniknife_config(tmp_path):
    """Configuration optimized for miniknife pipeline testing.

    Returns:
        SimulationConfig suitable for miniknife workflow
    """
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()

    return SimulationConfig(
        source_dir=source_dir,
        target_dir=target_dir,
        interval=2.0,
        batch_size=3,
        timing_model="random",
        operation="link",  # miniknife can work with links
        timing_model_params={"random_factor": 0.25},
    )


# Configuration Builder Utilities


class ConfigBuilder:
    """Builder pattern for creating test configurations."""

    def __init__(self, tmp_path: Path):
        self.tmp_path = tmp_path
        self._params = {
            "source_dir": tmp_path / "source",
            "target_dir": tmp_path / "target",
            "interval": 1.0,
            "operation": "copy",
            "batch_size": 1,
            "timing_model": "uniform",
        }
        # Ensure source directory exists
        self._params["source_dir"].mkdir(exist_ok=True)

    def with_timing_model(self, model: str, **model_params) -> "ConfigBuilder":
        """Set timing model and parameters."""
        self._params["timing_model"] = model
        if model_params:
            self._params["timing_model_params"] = model_params
        return self

    def with_parallel_processing(
        self, enabled: bool = True, worker_count: int = 4
    ) -> "ConfigBuilder":
        """Configure parallel processing."""
        self._params["parallel_processing"] = enabled
        if enabled:
            self._params["worker_count"] = worker_count
        return self

    def with_batch_size(self, size: int) -> "ConfigBuilder":
        """Set batch size."""
        self._params["batch_size"] = size
        return self

    def with_interval(self, interval: float) -> "ConfigBuilder":
        """Set timing interval."""
        self._params["interval"] = interval
        return self

    def with_operation(self, operation: str) -> "ConfigBuilder":
        """Set file operation type."""
        self._params["operation"] = operation
        return self

    def with_structure(self, structure: str) -> "ConfigBuilder":
        """Force specific structure type."""
        self._params["force_structure"] = structure
        return self

    def build(self) -> SimulationConfig:
        """Build the configuration."""
        return SimulationConfig(**self._params)


@pytest.fixture
def config_builder(tmp_path):
    """Provide a configuration builder for flexible test setup.

    Returns:
        ConfigBuilder instance for creating custom configurations
    """
    return ConfigBuilder(tmp_path)


# Mock Configuration Utilities


@pytest.fixture
def mock_config():
    """Mock configuration for unit testing.

    Returns:
        MagicMock configured to behave like SimulationConfig
    """
    mock = MagicMock(spec=SimulationConfig)
    mock.source_dir = Path("/mock/source")
    mock.target_dir = Path("/mock/target")
    mock.interval = 1.0
    mock.operation = "copy"
    mock.batch_size = 1
    mock.timing_model = "uniform"
    mock.timing_model_params = {}
    mock.parallel_processing = False
    mock.worker_count = 4
    mock.force_structure = None

    # Mock methods
    mock.get_timing_model_config.return_value = {
        "model_type": "uniform",
        "interval": 1.0,
    }

    return mock


# Validation Utilities


def validate_config_parameters(config: SimulationConfig) -> Dict[str, Any]:
    """Validate configuration parameters and return analysis.

    Args:
        config: Configuration to validate

    Returns:
        Dict containing validation results and recommendations
    """
    results = {
        "valid": True,
        "warnings": [],
        "recommendations": [],
        "performance_estimate": "unknown",
    }

    # Check for performance implications
    if config.parallel_processing and config.batch_size == 1:
        results["recommendations"].append(
            "Consider increasing batch_size for better parallel performance"
        )

    if config.interval < 0.1:
        results["warnings"].append("Very short interval may cause high system load")

    if config.worker_count > 8:
        results["warnings"].append("High worker count may not improve performance")

    # Performance estimation
    if config.parallel_processing and config.batch_size > 1:
        results["performance_estimate"] = "high"
    elif config.parallel_processing or config.batch_size > 1:
        results["performance_estimate"] = "medium"
    else:
        results["performance_estimate"] = "basic"

    return results


def create_config_variants(
    base_config: SimulationConfig,
) -> Dict[str, SimulationConfig]:
    """Create configuration variants for comprehensive testing.

    Args:
        base_config: Base configuration to create variants from

    Returns:
        Dict of configuration variants for different test scenarios
    """
    variants = {}

    # Fast variant for quick tests
    variants["fast"] = SimulationConfig(
        source_dir=base_config.source_dir,
        target_dir=base_config.target_dir,
        interval=0.01,  # Very fast
        batch_size=base_config.batch_size,
        timing_model="uniform",
    )

    # Slow variant for stress tests
    variants["slow"] = SimulationConfig(
        source_dir=base_config.source_dir,
        target_dir=base_config.target_dir,
        interval=10.0,  # Very slow
        batch_size=base_config.batch_size,
        timing_model=base_config.timing_model,
    )

    # Parallel variant
    variants["parallel"] = SimulationConfig(
        source_dir=base_config.source_dir,
        target_dir=base_config.target_dir,
        interval=base_config.interval,
        batch_size=max(3, base_config.batch_size),
        timing_model=base_config.timing_model,
        parallel_processing=True,
        worker_count=4,
    )

    # Link operation variant
    variants["link"] = SimulationConfig(
        source_dir=base_config.source_dir,
        target_dir=base_config.target_dir,
        interval=base_config.interval,
        batch_size=base_config.batch_size,
        timing_model=base_config.timing_model,
        operation="link",
    )

    return variants
