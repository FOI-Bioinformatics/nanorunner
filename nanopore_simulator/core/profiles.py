"""Configuration profiles for common sequencing scenarios"""

from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional
from pathlib import Path

from .config import SimulationConfig


# Generate-mode field names emitted by ProfileDefinition.to_config_params()
_GENERATE_FIELDS = (
    "read_count",
    "mean_read_length",
    "mean_quality",
    "reads_per_file",
    "output_format",
    "generator_backend",
)


@dataclass
class ProfileDefinition:
    """Definition of a configuration profile.

    Core timing and processing fields are always emitted by
    ``to_config_params()``.  Optional generate-mode fields are only
    included when explicitly set (non-None), so replay profiles do not
    inject unexpected generation defaults into SimulationConfig.
    """

    name: str
    description: str
    timing_model: str
    timing_model_params: Dict[str, Any]
    batch_size: int = 1
    parallel_processing: bool = False
    worker_count: int = 4
    operation: str = "copy"

    # Optional generate-mode defaults (emitted only when set)
    read_count: Optional[int] = None
    mean_read_length: Optional[int] = None
    mean_quality: Optional[float] = None
    reads_per_file: Optional[int] = None
    output_format: Optional[str] = None
    generator_backend: Optional[str] = None

    def to_config_params(self) -> Dict[str, Any]:
        """Convert profile to config parameters.

        Always includes timing and processing fields.  Generate-mode
        fields are included only when they have been explicitly set.
        """
        params: Dict[str, Any] = {
            "timing_model": self.timing_model,
            "timing_model_params": self.timing_model_params,
            "batch_size": self.batch_size,
            "parallel_processing": self.parallel_processing,
            "worker_count": self.worker_count,
            "operation": self.operation,
        }

        # Conditionally include generate-mode fields
        for field_name in _GENERATE_FIELDS:
            value = getattr(self, field_name)
            if value is not None:
                params[field_name] = value

        return params


# Built-in profiles for common sequencing scenarios.
#
# Replay profiles (5) cover the four timing models with distinct use
# cases.  Generate profiles (2) additionally set read-generation
# parameters via the optional generate-mode fields.
BUILTIN_PROFILES = {
    # -- Replay profiles ------------------------------------------------
    "development": ProfileDefinition(
        name="development",
        description="Fast iteration with deterministic uniform timing",
        timing_model="uniform",
        timing_model_params={},
        batch_size=10,
        parallel_processing=True,
        worker_count=8,
        operation="link",
    ),
    "steady": ProfileDefinition(
        name="steady",
        description="Low-variation random timing for controlled testing",
        timing_model="random",
        timing_model_params={"random_factor": 0.15},
        batch_size=1,
        parallel_processing=False,
        worker_count=4,
        operation="copy",
    ),
    "bursty": ProfileDefinition(
        name="bursty",
        description="Intermittent burst pattern for pipeline robustness testing",
        timing_model="poisson",
        timing_model_params={"burst_probability": 0.12, "burst_rate_multiplier": 6.0},
        batch_size=3,
        parallel_processing=True,
        worker_count=4,
        operation="copy",
    ),
    "high_throughput": ProfileDefinition(
        name="high_throughput",
        description="High file volume with burst timing for stress testing",
        timing_model="poisson",
        timing_model_params={"burst_probability": 0.20, "burst_rate_multiplier": 8.0},
        batch_size=15,
        parallel_processing=True,
        worker_count=12,
        operation="link",
    ),
    "gradual_drift": ProfileDefinition(
        name="gradual_drift",
        description="Slowly varying intervals via exponential moving average",
        timing_model="adaptive",
        timing_model_params={"adaptation_rate": 0.15, "history_size": 15},
        batch_size=2,
        parallel_processing=True,
        worker_count=4,
        operation="copy",
    ),
    # -- Generate profiles ----------------------------------------------
    "generate_test": ProfileDefinition(
        name="generate_test",
        description="Quick smoke test for read generation (100 reads, builtin)",
        timing_model="uniform",
        timing_model_params={},
        batch_size=5,
        parallel_processing=False,
        worker_count=2,
        operation="copy",
        read_count=100,
        reads_per_file=50,
        generator_backend="builtin",
    ),
    "generate_standard": ProfileDefinition(
        name="generate_standard",
        description="Standard read generation run (5000 reads, auto backend)",
        timing_model="poisson",
        timing_model_params={"burst_probability": 0.10, "burst_rate_multiplier": 4.0},
        batch_size=3,
        parallel_processing=True,
        worker_count=4,
        operation="copy",
        read_count=5000,
        reads_per_file=100,
        generator_backend="auto",
    ),
}


class ProfileManager:
    """Manages configuration profiles"""

    def __init__(self) -> None:
        self.builtin_profiles: Dict[str, ProfileDefinition] = BUILTIN_PROFILES.copy()
        self.custom_profiles: Dict[str, ProfileDefinition] = {}

    def list_profiles(self) -> Dict[str, str]:
        """List all available profiles with descriptions"""
        profiles = {}

        # Add builtin profiles
        for name, profile in self.builtin_profiles.items():
            profiles[name] = f"[Built-in] {profile.description}"

        # Add custom profiles
        for name, profile in self.custom_profiles.items():
            profiles[name] = f"[Custom] {profile.description}"

        return profiles

    def get_profile(self, name: str) -> Optional[ProfileDefinition]:
        """Get a profile by name"""
        if name in self.builtin_profiles:
            return self.builtin_profiles[name]
        elif name in self.custom_profiles:
            return self.custom_profiles[name]
        else:
            return None

    def add_custom_profile(self, profile: ProfileDefinition) -> None:
        """Add a custom profile"""
        self.custom_profiles[profile.name] = profile

    def remove_custom_profile(self, name: str) -> bool:
        """Remove a custom profile"""
        if name in self.custom_profiles:
            del self.custom_profiles[name]
            return True
        return False

    def create_config_from_profile(
        self,
        profile_name: str,
        source_dir: Path,
        target_dir: Path,
        interval: float = 5.0,
        **overrides: Any,
    ) -> SimulationConfig:
        """Create a SimulationConfig from a profile with optional overrides"""
        profile = self.get_profile(profile_name)
        if profile is None:
            raise ValueError(f"Profile '{profile_name}' not found")

        # Start with profile parameters
        config_params = profile.to_config_params()

        # Apply any overrides
        config_params.update(overrides)

        # Create config with required parameters
        return SimulationConfig(
            source_dir=source_dir,
            target_dir=target_dir,
            interval=interval,
            **config_params,
        )

    def save_custom_profiles(self, file_path: Path) -> None:
        """Save custom profiles to a file"""
        import json

        profiles_data = {}
        for name, profile in self.custom_profiles.items():
            data: Dict[str, Any] = {
                "name": profile.name,
                "description": profile.description,
                "timing_model": profile.timing_model,
                "timing_model_params": profile.timing_model_params,
                "batch_size": profile.batch_size,
                "parallel_processing": profile.parallel_processing,
                "worker_count": profile.worker_count,
                "operation": profile.operation,
            }
            # Include non-None generate fields
            for field_name in _GENERATE_FIELDS:
                value = getattr(profile, field_name)
                if value is not None:
                    data[field_name] = value
            profiles_data[name] = data

        with open(file_path, "w") as f:
            json.dump(profiles_data, f, indent=2)

    def load_custom_profiles(self, file_path: Path) -> None:
        """Load custom profiles from a file"""
        import json

        if not file_path.exists():
            return

        with open(file_path, "r") as f:
            profiles_data = json.load(f)

        for name, data in profiles_data.items():
            profile = ProfileDefinition(**data)
            self.custom_profiles[name] = profile

    def get_profile_recommendations(
        self, file_count: int, use_case: str = "general"
    ) -> list[str]:
        """Get profile recommendations based on file count and use case"""
        recommendations = []

        if use_case.lower() == "development":
            recommendations.append("development")
        elif use_case.lower() == "stress":
            recommendations.append("high_throughput")

        # Recommendations based on file count
        if file_count < 50:
            recommendations.extend(["steady", "bursty"])
        elif file_count < 500:
            recommendations.extend(["bursty", "gradual_drift"])
        else:
            recommendations.extend(["high_throughput", "bursty"])

        # Always include development as a fallback
        if "development" not in recommendations:
            recommendations.append("development")

        # Remove duplicates while preserving order
        seen = set()
        unique_recommendations = []
        for rec in recommendations:
            if rec not in seen:
                unique_recommendations.append(rec)
                seen.add(rec)

        return unique_recommendations[:5]


# Global profile manager instance
profile_manager = ProfileManager()


def get_available_profiles() -> Dict[str, str]:
    """Get all available profiles with descriptions"""
    return profile_manager.list_profiles()


def create_config_from_profile(
    profile_name: str,
    source_dir: Path,
    target_dir: Path,
    interval: float = 5.0,
    **overrides: Any,
) -> SimulationConfig:
    """Create a configuration from a profile"""
    return profile_manager.create_config_from_profile(
        profile_name, source_dir, target_dir, interval, **overrides
    )


def get_profile_recommendations(
    file_count: int, use_case: str = "general"
) -> list[str]:
    """Get profile recommendations"""
    return profile_manager.get_profile_recommendations(file_count, use_case)


def get_generate_recommendations(
    genome_count: int, total_size_mb: float = 0
) -> list[str]:
    """Recommend generate-mode profiles based on genome count and total size.

    For small inputs (few genomes, modest total size), suggests
    ``generate_test`` first for quick feedback.  For larger inputs,
    suggests ``generate_standard`` first.
    """
    if genome_count <= 2 and total_size_mb < 20:
        return ["generate_test", "generate_standard"]
    return ["generate_standard", "generate_test"]


def validate_profile_name(name: str) -> bool:
    """Validate if a profile name exists"""
    return profile_manager.get_profile(name) is not None
