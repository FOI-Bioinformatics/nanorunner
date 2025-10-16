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


class TestBuiltinProfiles:
    """Test built-in profiles"""

    def test_builtin_profiles_exist(self):
        """Test that expected built-in profiles exist"""
        expected_profiles = [
            "rapid_sequencing",
            "accurate_mode",
            "development_testing",
            "long_read_nanopore",
            "high_throughput",
            "adaptive_learning",
            "legacy_random",
            "minion_simulation",
            "promethion_simulation",
        ]

        for profile_name in expected_profiles:
            assert profile_name in BUILTIN_PROFILES

    def test_rapid_sequencing_profile(self):
        """Test rapid sequencing profile configuration"""
        profile = BUILTIN_PROFILES["rapid_sequencing"]

        assert profile.timing_model == "poisson"
        assert profile.timing_model_params["burst_probability"] == 0.15
        assert profile.timing_model_params["burst_rate_multiplier"] == 8.0
        assert profile.batch_size == 5
        assert profile.parallel_processing is True
        assert profile.worker_count == 6

    def test_accurate_mode_profile(self):
        """Test accurate mode profile configuration"""
        profile = BUILTIN_PROFILES["accurate_mode"]

        assert profile.timing_model == "poisson"
        assert profile.timing_model_params["burst_probability"] == 0.02
        assert profile.timing_model_params["burst_rate_multiplier"] == 2.0
        assert profile.batch_size == 1
        assert profile.parallel_processing is False

    def test_development_testing_profile(self):
        """Test development testing profile"""
        profile = BUILTIN_PROFILES["development_testing"]

        assert profile.timing_model == "uniform"
        assert profile.batch_size == 10
        assert profile.parallel_processing is True
        assert profile.operation == "link"  # Faster for testing

    def test_high_throughput_profile(self):
        """Test high throughput profile"""
        profile = BUILTIN_PROFILES["high_throughput"]

        assert profile.timing_model == "poisson"
        assert profile.timing_model_params["burst_probability"] == 0.25
        assert profile.batch_size == 20
        assert profile.worker_count == 12
        assert profile.operation == "link"


class TestProfileManager:
    """Test the ProfileManager class"""

    def test_profile_manager_initialization(self):
        """Test profile manager initialization"""
        manager = ProfileManager()

        assert len(manager.builtin_profiles) > 0
        assert len(manager.custom_profiles) == 0
        assert "rapid_sequencing" in manager.builtin_profiles

    def test_list_profiles(self):
        """Test listing all profiles"""
        manager = ProfileManager()
        profiles = manager.list_profiles()

        assert "rapid_sequencing" in profiles
        assert "[Built-in]" in profiles["rapid_sequencing"]

    def test_get_builtin_profile(self):
        """Test getting a built-in profile"""
        manager = ProfileManager()
        profile = manager.get_profile("rapid_sequencing")

        assert profile is not None
        assert profile.name == "rapid_sequencing"
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
            "rapid_sequencing", source_dir, target_dir, interval=3.0
        )

        assert isinstance(config, SimulationConfig)
        assert config.source_dir == source_dir
        assert config.target_dir == target_dir
        assert config.interval == 3.0
        assert config.timing_model == "poisson"
        assert config.batch_size == 5
        assert config.parallel_processing is True

    def test_create_config_with_overrides(self, temp_dirs):
        """Test creating config with parameter overrides"""
        source_dir, target_dir = temp_dirs
        manager = ProfileManager()

        config = manager.create_config_from_profile(
            "accurate_mode",
            source_dir,
            target_dir,
            interval=2.0,
            batch_size=10,  # Override profile default
            operation="link",  # Override profile default
        )

        assert config.batch_size == 10  # Overridden
        assert config.operation == "link"  # Overridden
        assert config.timing_model == "poisson"  # From profile
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

        assert "accurate_mode" in recommendations
        assert "long_read_nanopore" in recommendations
        assert len(recommendations) <= 5

    def test_recommendations_for_large_dataset(self):
        """Test recommendations for large datasets"""
        recommendations = get_profile_recommendations(1000, "general")

        assert (
            "high_throughput" in recommendations
            or "promethion_simulation" in recommendations
        )
        assert len(recommendations) <= 5

    def test_recommendations_for_development(self):
        """Test recommendations for development use case"""
        recommendations = get_profile_recommendations(50, "development")

        assert "development_testing" in recommendations

    def test_recommendations_for_stress_testing(self):
        """Test recommendations for stress testing"""
        recommendations = get_profile_recommendations(500, "stress")

        assert "high_throughput" in recommendations

    def test_recommendations_for_minion(self):
        """Test recommendations for MinION device"""
        recommendations = get_profile_recommendations(100, "minion")

        assert "minion_simulation" in recommendations

    def test_recommendations_for_promethion(self):
        """Test recommendations for PromethION device"""
        recommendations = get_profile_recommendations(2000, "promethion")

        assert "promethion_simulation" in recommendations


class TestProfileIntegration:
    """Test profile integration with the rest of the system"""

    def test_global_functions(self):
        """Test global convenience functions"""
        profiles = get_available_profiles()
        assert "rapid_sequencing" in profiles

        assert validate_profile_name("rapid_sequencing") is True
        assert validate_profile_name("nonexistent") is False

    def test_create_config_from_profile_global(self, temp_dirs):
        """Test global create_config_from_profile function"""
        source_dir, target_dir = temp_dirs

        config = create_config_from_profile(
            "development_testing", source_dir, target_dir, interval=1.0
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

    def test_legacy_compatibility(self, temp_dirs):
        """Test that legacy_random profile maintains compatibility"""
        source_dir, target_dir = temp_dirs

        config = create_config_from_profile("legacy_random", source_dir, target_dir)

        assert config.timing_model == "random"
        assert config.timing_model_params["random_factor"] == 0.3
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
