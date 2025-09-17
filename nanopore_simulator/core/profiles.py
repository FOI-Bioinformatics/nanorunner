"""Configuration profiles for common sequencing scenarios"""

from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional
from pathlib import Path

from .config import SimulationConfig


@dataclass
class ProfileDefinition:
    """Definition of a configuration profile"""
    name: str
    description: str
    timing_model: str
    timing_model_params: Dict[str, Any]
    batch_size: int = 1
    parallel_processing: bool = False
    worker_count: int = 4
    operation: str = "copy"
    
    def to_config_params(self) -> Dict[str, Any]:
        """Convert profile to config parameters"""
        return {
            'timing_model': self.timing_model,
            'timing_model_params': self.timing_model_params,
            'batch_size': self.batch_size,
            'parallel_processing': self.parallel_processing,
            'worker_count': self.worker_count,
            'operation': self.operation
        }


# Built-in profiles for common sequencing scenarios
BUILTIN_PROFILES = {
    "rapid_sequencing": ProfileDefinition(
        name="rapid_sequencing",
        description="High-throughput rapid sequencing with frequent bursts",
        timing_model="poisson",
        timing_model_params={
            "burst_probability": 0.15,
            "burst_rate_multiplier": 8.0
        },
        batch_size=5,
        parallel_processing=True,
        worker_count=6,
        operation="copy"
    ),
    
    "accurate_mode": ProfileDefinition(
        name="accurate_mode",
        description="Steady, accurate sequencing with minimal variation",
        timing_model="poisson",
        timing_model_params={
            "burst_probability": 0.02,
            "burst_rate_multiplier": 2.0
        },
        batch_size=1,
        parallel_processing=False,
        worker_count=2,
        operation="copy"
    ),
    
    "development_testing": ProfileDefinition(
        name="development_testing",
        description="Fast testing profile for development workflows",
        timing_model="uniform",
        timing_model_params={},
        batch_size=10,
        parallel_processing=True,
        worker_count=8,
        operation="link"  # Faster for testing
    ),
    
    "long_read_nanopore": ProfileDefinition(
        name="long_read_nanopore",
        description="Typical Oxford Nanopore long-read sequencing pattern",
        timing_model="poisson",
        timing_model_params={
            "burst_probability": 0.08,
            "burst_rate_multiplier": 4.0
        },
        batch_size=3,
        parallel_processing=True,
        worker_count=4,
        operation="copy"
    ),
    
    "high_throughput": ProfileDefinition(
        name="high_throughput",
        description="Maximum throughput simulation for stress testing",
        timing_model="poisson",
        timing_model_params={
            "burst_probability": 0.25,
            "burst_rate_multiplier": 10.0
        },
        batch_size=20,
        parallel_processing=True,
        worker_count=12,
        operation="link"
    ),
    
    "adaptive_learning": ProfileDefinition(
        name="adaptive_learning",
        description="Adaptive timing that learns from file processing patterns",
        timing_model="adaptive",
        timing_model_params={
            "adaptation_rate": 0.15,
            "history_size": 15
        },
        batch_size=2,
        parallel_processing=True,
        worker_count=4,
        operation="copy"
    ),
    
    "legacy_random": ProfileDefinition(
        name="legacy_random",
        description="Legacy random interval mode for backward compatibility",
        timing_model="random",
        timing_model_params={
            "random_factor": 0.3
        },
        batch_size=1,
        parallel_processing=False,
        worker_count=4,
        operation="copy"
    ),
    
    "minion_simulation": ProfileDefinition(
        name="minion_simulation",
        description="Oxford Nanopore MinION device simulation",
        timing_model="poisson",
        timing_model_params={
            "burst_probability": 0.12,
            "burst_rate_multiplier": 6.0
        },
        batch_size=2,
        parallel_processing=True,
        worker_count=3,
        operation="copy"
    ),
    
    "promethion_simulation": ProfileDefinition(
        name="promethion_simulation",
        description="Oxford Nanopore PromethION device simulation",
        timing_model="poisson",
        timing_model_params={
            "burst_probability": 0.18,
            "burst_rate_multiplier": 12.0
        },
        batch_size=15,
        parallel_processing=True,
        worker_count=16,
        operation="copy"
    )
}


class ProfileManager:
    """Manages configuration profiles"""
    
    def __init__(self):
        self.builtin_profiles = BUILTIN_PROFILES.copy()
        self.custom_profiles = {}
    
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
    
    def create_config_from_profile(self, profile_name: str, source_dir: Path, 
                                 target_dir: Path, interval: float = 5.0, 
                                 **overrides) -> SimulationConfig:
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
            **config_params
        )
    
    def save_custom_profiles(self, file_path: Path) -> None:
        """Save custom profiles to a file"""
        import json
        
        profiles_data = {}
        for name, profile in self.custom_profiles.items():
            profiles_data[name] = {
                'name': profile.name,
                'description': profile.description,
                'timing_model': profile.timing_model,
                'timing_model_params': profile.timing_model_params,
                'batch_size': profile.batch_size,
                'parallel_processing': profile.parallel_processing,
                'worker_count': profile.worker_count,
                'operation': profile.operation
            }
        
        with open(file_path, 'w') as f:
            json.dump(profiles_data, f, indent=2)
    
    def load_custom_profiles(self, file_path: Path) -> None:
        """Load custom profiles from a file"""
        import json
        
        if not file_path.exists():
            return
        
        with open(file_path, 'r') as f:
            profiles_data = json.load(f)
        
        for name, data in profiles_data.items():
            profile = ProfileDefinition(**data)
            self.custom_profiles[name] = profile
    
    def get_profile_recommendations(self, file_count: int, 
                                  use_case: str = "general") -> list[str]:
        """Get profile recommendations based on context"""
        recommendations = []
        
        if use_case.lower() == "development":
            recommendations.append("development_testing")
        elif use_case.lower() == "stress":
            recommendations.append("high_throughput")
        elif "minion" in use_case.lower():
            recommendations.append("minion_simulation")
        elif "promethion" in use_case.lower():
            recommendations.append("promethion_simulation")
        
        # Recommendations based on file count
        if file_count < 50:
            recommendations.extend(["accurate_mode", "long_read_nanopore"])
        elif file_count < 500:
            recommendations.extend(["rapid_sequencing", "minion_simulation"])
        else:
            recommendations.extend(["high_throughput", "promethion_simulation"])
        
        # Always include adaptive learning as an option
        if "adaptive_learning" not in recommendations:
            recommendations.append("adaptive_learning")
        
        # Remove duplicates while preserving order
        seen = set()
        unique_recommendations = []
        for rec in recommendations:
            if rec not in seen:
                unique_recommendations.append(rec)
                seen.add(rec)
        
        return unique_recommendations[:5]  # Limit to top 5 recommendations


# Global profile manager instance
profile_manager = ProfileManager()


def get_available_profiles() -> Dict[str, str]:
    """Get all available profiles with descriptions"""
    return profile_manager.list_profiles()


def create_config_from_profile(profile_name: str, source_dir: Path, 
                             target_dir: Path, interval: float = 5.0, 
                             **overrides) -> SimulationConfig:
    """Create a configuration from a profile"""
    return profile_manager.create_config_from_profile(
        profile_name, source_dir, target_dir, interval, **overrides
    )


def get_profile_recommendations(file_count: int, use_case: str = "general") -> list[str]:
    """Get profile recommendations"""
    return profile_manager.get_profile_recommendations(file_count, use_case)


def validate_profile_name(name: str) -> bool:
    """Validate if a profile name exists"""
    return profile_manager.get_profile(name) is not None