"""Configuration profiles for common sequencing scenarios.

Each profile is a plain dict of parameters. Replay profiles contain
timing and processing fields only. Generate profiles additionally
include read-generation parameters. No dataclass or manager object --
just data and functions.
"""

from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Built-in profiles
# ---------------------------------------------------------------------------

PROFILES: Dict[str, Dict[str, Any]] = {
    # -- Replay profiles ----------------------------------------------------
    "development": {
        "description": "Fast iteration with deterministic uniform timing",
        "timing_model": "uniform",
        "timing_model_params": {},
        "batch_size": 10,
        "parallel_processing": True,
        "worker_count": 8,
        "operation": "link",
    },
    "steady": {
        "description": "Low-variation random timing for controlled testing",
        "timing_model": "random",
        "timing_model_params": {"random_factor": 0.15},
        "batch_size": 1,
        "parallel_processing": False,
        "worker_count": 4,
        "operation": "copy",
    },
    "bursty": {
        "description": "Intermittent burst pattern for pipeline robustness testing",
        "timing_model": "poisson",
        "timing_model_params": {
            "burst_probability": 0.12,
            "burst_rate_multiplier": 6.0,
        },
        "batch_size": 3,
        "parallel_processing": True,
        "worker_count": 4,
        "operation": "copy",
    },
    "high_throughput": {
        "description": "High file volume with burst timing for stress testing",
        "timing_model": "poisson",
        "timing_model_params": {
            "burst_probability": 0.20,
            "burst_rate_multiplier": 8.0,
        },
        "batch_size": 15,
        "parallel_processing": True,
        "worker_count": 12,
        "operation": "link",
    },
    "gradual_drift": {
        "description": "Slowly varying intervals via exponential moving average",
        "timing_model": "adaptive",
        "timing_model_params": {
            "adaptation_rate": 0.15,
            "history_size": 15,
        },
        "batch_size": 2,
        "parallel_processing": True,
        "worker_count": 4,
        "operation": "copy",
    },
    # -- Generate profiles --------------------------------------------------
    "generate_test": {
        "description": "Quick smoke test for read generation (100 reads, builtin)",
        "timing_model": "uniform",
        "timing_model_params": {},
        "batch_size": 5,
        "parallel_processing": False,
        "worker_count": 2,
        "operation": "copy",
        "read_count": 100,
        "reads_per_file": 50,
        "generator_backend": "builtin",
    },
    "generate_standard": {
        "description": "Standard read generation run (5000 reads, auto backend)",
        "timing_model": "poisson",
        "timing_model_params": {
            "burst_probability": 0.10,
            "burst_rate_multiplier": 4.0,
        },
        "batch_size": 3,
        "parallel_processing": True,
        "worker_count": 4,
        "operation": "copy",
        "read_count": 5000,
        "reads_per_file": 100,
        "generator_backend": "auto",
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_profile(name: str) -> Optional[Dict[str, Any]]:
    """Return a copy of the profile dict for *name*, or None.

    Args:
        name: Profile identifier.

    Returns:
        A dict with all profile parameters, or None if not found.
    """
    profile = PROFILES.get(name)
    if profile is None:
        return None
    return dict(profile)


def list_profiles() -> Dict[str, str]:
    """Return a mapping of profile names to their descriptions."""
    return {name: p["description"] for name, p in PROFILES.items()}


def apply_profile(
    name: str,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build configuration parameters from a profile.

    Returns a dict suitable for passing to a config constructor. The
    ``description`` key is removed since it is metadata, not a config
    parameter. Generate-mode fields are included only when the profile
    defines them.

    Args:
        name: Profile identifier.
        overrides: Optional parameter overrides applied on top.

    Returns:
        Dict of configuration parameters.

    Raises:
        ValueError: If the profile name is not found.
    """
    profile = PROFILES.get(name)
    if profile is None:
        raise ValueError(f"Profile '{name}' not found")

    # Copy without description (metadata, not a config parameter).
    params = {k: v for k, v in profile.items() if k != "description"}

    # Deep-copy timing_model_params to prevent mutation.
    if "timing_model_params" in params:
        params["timing_model_params"] = dict(params["timing_model_params"])

    if overrides:
        params.update(overrides)

    return params


def get_recommendations(file_count: int) -> List[str]:
    """Suggest profiles based on file count.

    Args:
        file_count: Number of files in the source directory.

    Returns:
        Ordered list of recommended profile names (at most 5).
    """
    recommendations: List[str] = []

    if file_count < 50:
        recommendations.extend(["steady", "bursty"])
    elif file_count < 500:
        recommendations.extend(["bursty", "gradual_drift"])
    else:
        recommendations.extend(["high_throughput", "bursty"])

    if "development" not in recommendations:
        recommendations.append("development")

    # Deduplicate while preserving order.
    seen: set = set()
    unique: List[str] = []
    for rec in recommendations:
        if rec not in seen:
            unique.append(rec)
            seen.add(rec)

    return unique[:5]
