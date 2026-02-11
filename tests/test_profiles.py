"""Tests for configuration profiles system"""

import pytest
import tempfile
from pathlib import Path

from nanopore_simulator.core.profiles import (
    ProfileDefinition,
    ProfileManager,
    BUILTIN_PROFILES,
    get_available_profiles,
    create_config_from_profile,
    get_profile_recommendations,
    validate_profile_name,
)
from nanopore_simulator.core.config import SimulationConfig


class TestProfileDefinition:
    """Test the ProfileDefinition class"""

    def test_profile_creation(self):
        """Test creating a profile definition"""
        profile = ProfileDefinition(
            name="test_profile",
            description="Test profile for testing",
            timing_model="poisson",
            timing_model_params={"burst_probability": 0.2},
            batch_size=5,
            parallel_processing=True,
        )

        assert profile.name == "test_profile"
        assert profile.timing_model == "poisson"
        assert profile.timing_model_params["burst_probability"] == 0.2
        assert profile.batch_size == 5
        assert profile.parallel_processing is True

    def test_to_config_params(self):
        """Test converting profile to config parameters"""
        profile = ProfileDefinition(
            name="test",
            description="Test",
            timing_model="random",
            timing_model_params={"random_factor": 0.5},
            batch_size=3,
            worker_count=8,
        )

        params = profile.to_config_params()

        assert params["timing_model"] == "random"
        assert params["timing_model_params"]["random_factor"] == 0.5
        assert params["batch_size"] == 3
        assert params["worker_count"] == 8
        assert params["operation"] == "copy"  # Default

    def test_to_config_params_excludes_none_generate_fields(self):
        """Test that to_config_params omits None generate-mode fields"""
        profile = ProfileDefinition(
            name="replay_only",
            description="No generate fields set",
            timing_model="uniform",
            timing_model_params={},
        )

        params = profile.to_config_params()

        assert "read_count" not in params
        assert "mean_read_length" not in params
        assert "mean_quality" not in params
        assert "reads_per_file" not in params
        assert "output_format" not in params
        assert "generator_backend" not in params

    def test_to_config_params_includes_set_generate_fields(self):
        """Test that to_config_params includes non-None generate-mode fields"""
        profile = ProfileDefinition(
            name="gen",
            description="With generate fields",
            timing_model="uniform",
            timing_model_params={},
            read_count=100,
            reads_per_file=50,
            generator_backend="builtin",
        )

        params = profile.to_config_params()

        assert params["read_count"] == 100
        assert params["reads_per_file"] == 50
        assert params["generator_backend"] == "builtin"
        # Fields left as None should still be absent
        assert "mean_read_length" not in params
        assert "mean_quality" not in params
        assert "output_format" not in params


class TestBuiltinProfiles:
    """Test built-in profiles"""

    def test_builtin_profiles_exist(self):
        """Test that expected built-in profiles exist"""
        expected_profiles = [
            "development",
            "steady",
            "bursty",
            "high_throughput",
            "gradual_drift",
            "generate_test",
            "generate_standard",
        ]

        for profile_name in expected_profiles:
            assert profile_name in BUILTIN_PROFILES

    def test_profile_count(self):
        """Test that exactly 7 built-in profiles are defined"""
        assert len(BUILTIN_PROFILES) == 7

    def test_development_profile(self):
        """Test development profile configuration"""
        profile = BUILTIN_PROFILES["development"]

        assert profile.timing_model == "uniform"
        assert profile.batch_size == 10
        assert profile.parallel_processing is True
        assert profile.worker_count == 8
        assert profile.operation == "link"

    def test_steady_profile(self):
        """Test steady profile configuration"""
        profile = BUILTIN_PROFILES["steady"]

        assert profile.timing_model == "random"
        assert profile.timing_model_params["random_factor"] == 0.15
        assert profile.batch_size == 1
        assert profile.parallel_processing is False

    def test_bursty_profile(self):
        """Test bursty profile configuration"""
        profile = BUILTIN_PROFILES["bursty"]

        assert profile.timing_model == "poisson"
        assert profile.timing_model_params["burst_probability"] == 0.12
        assert profile.timing_model_params["burst_rate_multiplier"] == 6.0
        assert profile.batch_size == 3
        assert profile.parallel_processing is True
        assert profile.worker_count == 4

    def test_high_throughput_profile(self):
        """Test high throughput profile"""
        profile = BUILTIN_PROFILES["high_throughput"]

        assert profile.timing_model == "poisson"
        assert profile.timing_model_params["burst_probability"] == 0.20
        assert profile.timing_model_params["burst_rate_multiplier"] == 8.0
        assert profile.batch_size == 15
        assert profile.worker_count == 12
        assert profile.operation == "link"

    def test_gradual_drift_profile(self):
        """Test gradual_drift profile configuration"""
        profile = BUILTIN_PROFILES["gradual_drift"]

        assert profile.timing_model == "adaptive"
        assert profile.timing_model_params["adaptation_rate"] == 0.15
        assert profile.timing_model_params["history_size"] == 15
        assert profile.batch_size == 2
        assert profile.parallel_processing is True

    def test_generate_test_profile(self):
        """Test generate_test profile sets generation parameters"""
        profile = BUILTIN_PROFILES["generate_test"]

        assert profile.timing_model == "uniform"
        assert profile.read_count == 100
        assert profile.reads_per_file == 50
        assert profile.generator_backend == "builtin"

        params = profile.to_config_params()
        assert params["read_count"] == 100
        assert params["reads_per_file"] == 50
        assert params["generator_backend"] == "builtin"

    def test_generate_standard_profile(self):
        """Test generate_standard profile sets generation parameters"""
        profile = BUILTIN_PROFILES["generate_standard"]

        assert profile.timing_model == "poisson"
        assert profile.read_count == 5000
        assert profile.reads_per_file == 100
        assert profile.generator_backend == "auto"

        params = profile.to_config_params()
        assert params["read_count"] == 5000
        assert params["generator_backend"] == "auto"


class TestProfileManager:
    """Test the ProfileManager class"""

    def test_profile_manager_initialization(self):
        """Test profile manager initialization"""
        manager = ProfileManager()

        assert len(manager.builtin_profiles) > 0
        assert len(manager.custom_profiles) == 0
        assert "development" in manager.builtin_profiles

    def test_list_profiles(self):
        """Test listing all profiles"""
        manager = ProfileManager()
        profiles = manager.list_profiles()

        assert "development" in profiles
        assert "[Built-in]" in profiles["development"]

    def test_get_builtin_profile(self):
        """Test getting a built-in profile"""
        manager = ProfileManager()
        profile = manager.get_profile("bursty")

        assert profile is not None
        assert profile.name == "bursty"
        assert profile.timing_model == "poisson"

    def test_get_nonexistent_profile(self):
        """Test getting a non-existent profile"""
        manager = ProfileManager()
        profile = manager.get_profile("nonexistent")

        assert profile is None

    def test_add_custom_profile(self):
        """Test adding a custom profile"""
        manager = ProfileManager()

        custom_profile = ProfileDefinition(
            name="my_custom",
            description="My custom profile",
            timing_model="uniform",
            timing_model_params={},
        )

        manager.add_custom_profile(custom_profile)

        assert "my_custom" in manager.custom_profiles
        retrieved = manager.get_profile("my_custom")
        assert retrieved is not None
        assert retrieved.name == "my_custom"

    def test_remove_custom_profile(self):
        """Test removing a custom profile"""
        manager = ProfileManager()

        custom_profile = ProfileDefinition(
            name="to_remove",
            description="Profile to remove",
            timing_model="uniform",
            timing_model_params={},
        )

        manager.add_custom_profile(custom_profile)
        assert manager.get_profile("to_remove") is not None

        removed = manager.remove_custom_profile("to_remove")
        assert removed is True
        assert manager.get_profile("to_remove") is None

        # Try to remove non-existent profile
        removed = manager.remove_custom_profile("nonexistent")
        assert removed is False

    def test_create_config_from_profile(self, temp_dirs):
        """Test creating config from profile"""
        source_dir, target_dir = temp_dirs
        manager = ProfileManager()

        config = manager.create_config_from_profile(
            "bursty", source_dir, target_dir, interval=3.0
        )

        assert isinstance(config, SimulationConfig)
        assert config.source_dir == source_dir
        assert config.target_dir == target_dir
        assert config.interval == 3.0
        assert config.timing_model == "poisson"
        assert config.batch_size == 3
        assert config.parallel_processing is True

    def test_create_config_with_overrides(self, temp_dirs):
        """Test creating config with parameter overrides"""
        source_dir, target_dir = temp_dirs
        manager = ProfileManager()

        config = manager.create_config_from_profile(
            "steady",
            source_dir,
            target_dir,
            interval=2.0,
            batch_size=10,  # Override profile default
            operation="link",  # Override profile default
        )

        assert config.batch_size == 10  # Overridden
        assert config.operation == "link"  # Overridden
        assert config.timing_model == "random"  # From profile
        assert config.parallel_processing is False  # From profile

    def test_create_config_unknown_profile(self, temp_dirs):
        """Test creating config from unknown profile"""
        source_dir, target_dir = temp_dirs
        manager = ProfileManager()

        with pytest.raises(ValueError, match="Profile 'unknown' not found"):
            manager.create_config_from_profile("unknown", source_dir, target_dir)


class TestProfileRecommendations:
    """Test profile recommendation system"""

    def test_recommendations_for_small_dataset(self):
        """Test recommendations for small datasets"""
        recommendations = get_profile_recommendations(10, "general")

        assert "steady" in recommendations
        assert "bursty" in recommendations
        assert len(recommendations) <= 5

    def test_recommendations_for_medium_dataset(self):
        """Test recommendations for medium datasets"""
        recommendations = get_profile_recommendations(200, "general")

        assert "bursty" in recommendations
        assert "gradual_drift" in recommendations
        assert len(recommendations) <= 5

    def test_recommendations_for_large_dataset(self):
        """Test recommendations for large datasets"""
        recommendations = get_profile_recommendations(1000, "general")

        assert "high_throughput" in recommendations
        assert "bursty" in recommendations
        assert len(recommendations) <= 5

    def test_recommendations_for_development(self):
        """Test recommendations for development use case"""
        recommendations = get_profile_recommendations(50, "development")

        assert "development" in recommendations

    def test_recommendations_for_stress_testing(self):
        """Test recommendations for stress testing"""
        recommendations = get_profile_recommendations(500, "stress")

        assert "high_throughput" in recommendations

    def test_recommendations_always_include_development_fallback(self):
        """Test that development is included as a fallback"""
        recommendations = get_profile_recommendations(200, "general")

        assert "development" in recommendations


class TestProfileIntegration:
    """Test profile integration with the rest of the system"""

    def test_global_functions(self):
        """Test global convenience functions"""
        profiles = get_available_profiles()
        assert "development" in profiles

        assert validate_profile_name("development") is True
        assert validate_profile_name("nonexistent") is False

    def test_create_config_from_profile_global(self, temp_dirs):
        """Test global create_config_from_profile function"""
        source_dir, target_dir = temp_dirs

        config = create_config_from_profile(
            "development", source_dir, target_dir, interval=1.0
        )

        assert isinstance(config, SimulationConfig)
        assert config.timing_model == "uniform"
        assert config.batch_size == 10
        assert config.operation == "link"

    def test_profile_config_validation(self, temp_dirs):
        """Test that profiles create valid configurations"""
        source_dir, target_dir = temp_dirs

        # Test all built-in profiles
        for profile_name in BUILTIN_PROFILES.keys():
            config = create_config_from_profile(profile_name, source_dir, target_dir)

            # Config should be valid (no exceptions during creation)
            assert isinstance(config, SimulationConfig)
            assert config.source_dir == source_dir
            assert config.target_dir == target_dir

    def test_steady_profile_uses_random_model(self, temp_dirs):
        """Test that the steady profile uses the random timing model"""
        source_dir, target_dir = temp_dirs

        config = create_config_from_profile("steady", source_dir, target_dir)

        assert config.timing_model == "random"
        assert config.timing_model_params["random_factor"] == 0.15
        assert config.parallel_processing is False


class TestProfileSerialization:
    """Test profile serialization and deserialization"""

    def test_save_and_load_custom_profiles(self):
        """Test saving and loading custom profiles"""
        manager = ProfileManager()

        # Add custom profiles
        custom1 = ProfileDefinition(
            name="custom1",
            description="Custom profile 1",
            timing_model="poisson",
            timing_model_params={"burst_probability": 0.3},
            batch_size=7,
        )

        custom2 = ProfileDefinition(
            name="custom2",
            description="Custom profile 2",
            timing_model="adaptive",
            timing_model_params={"adaptation_rate": 0.2},
            parallel_processing=True,
        )

        manager.add_custom_profile(custom1)
        manager.add_custom_profile(custom2)

        # Save to temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_file = Path(f.name)

        try:
            manager.save_custom_profiles(temp_file)

            # Create new manager and load profiles
            new_manager = ProfileManager()
            new_manager.load_custom_profiles(temp_file)

            # Verify profiles were loaded
            loaded1 = new_manager.get_profile("custom1")
            loaded2 = new_manager.get_profile("custom2")

            assert loaded1 is not None
            assert loaded1.name == "custom1"
            assert loaded1.timing_model == "poisson"
            assert loaded1.timing_model_params["burst_probability"] == 0.3

            assert loaded2 is not None
            assert loaded2.name == "custom2"
            assert loaded2.timing_model == "adaptive"
            assert loaded2.parallel_processing is True

        finally:
            # Clean up
            if temp_file.exists():
                temp_file.unlink()

    def test_save_and_load_custom_profile_with_generate_fields(self):
        """Test round-tripping a custom profile that has generate-mode fields"""
        manager = ProfileManager()

        gen_profile = ProfileDefinition(
            name="custom_gen",
            description="Custom generate profile",
            timing_model="uniform",
            timing_model_params={},
            read_count=500,
            generator_backend="builtin",
        )
        manager.add_custom_profile(gen_profile)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_file = Path(f.name)

        try:
            manager.save_custom_profiles(temp_file)

            new_manager = ProfileManager()
            new_manager.load_custom_profiles(temp_file)

            loaded = new_manager.get_profile("custom_gen")
            assert loaded is not None
            assert loaded.read_count == 500
            assert loaded.generator_backend == "builtin"
        finally:
            if temp_file.exists():
                temp_file.unlink()

    def test_load_nonexistent_file(self):
        """Test loading from non-existent file"""
        manager = ProfileManager()
        nonexistent = Path("/tmp/nonexistent_profiles.json")

        # Should not raise an exception
        manager.load_custom_profiles(nonexistent)
        assert len(manager.custom_profiles) == 0


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
