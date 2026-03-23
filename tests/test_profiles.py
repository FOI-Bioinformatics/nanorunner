"""Tests for configuration profiles."""

import pytest

from nanopore_simulator.profiles import (
    PROFILES,
    get_profile,
    list_profiles,
    apply_profile,
    get_recommendations,
)


class TestProfilesRegistry:
    """Validate the PROFILES data dict contains all expected profiles."""

    EXPECTED = [
        "development",
        "steady",
        "bursty",
        "high_throughput",
        "gradual_drift",
        "generate_test",
        "generate_standard",
    ]

    def test_all_expected_present(self) -> None:
        for name in self.EXPECTED:
            assert name in PROFILES, f"Missing profile: {name}"

    def test_no_unexpected_profiles(self) -> None:
        for name in PROFILES:
            assert name in self.EXPECTED, f"Unexpected profile: {name}"

    def test_profile_count(self) -> None:
        assert len(PROFILES) == 7

    @pytest.mark.parametrize(
        "name",
        EXPECTED,
    )
    def test_each_has_description(self, name: str) -> None:
        assert "description" in PROFILES[name]
        assert len(PROFILES[name]["description"]) > 0

    @pytest.mark.parametrize(
        "name",
        EXPECTED,
    )
    def test_each_has_timing_model(self, name: str) -> None:
        assert "timing_model" in PROFILES[name]
        assert PROFILES[name]["timing_model"] in {
            "uniform",
            "random",
            "poisson",
            "adaptive",
        }

    @pytest.mark.parametrize(
        "name",
        EXPECTED,
    )
    def test_each_has_timing_model_params(self, name: str) -> None:
        assert "timing_model_params" in PROFILES[name]
        assert isinstance(PROFILES[name]["timing_model_params"], dict)

    @pytest.mark.parametrize(
        "name",
        EXPECTED,
    )
    def test_each_has_batch_size(self, name: str) -> None:
        assert "batch_size" in PROFILES[name]
        assert PROFILES[name]["batch_size"] >= 1


class TestGetProfile:
    """Validate get_profile lookup."""

    def test_known_profile(self) -> None:
        result = get_profile("development")
        assert result is not None
        assert (
            result["description"] == "Fast iteration with deterministic uniform timing"
        )

    def test_unknown_returns_none(self) -> None:
        assert get_profile("nonexistent") is None

    def test_development_values(self) -> None:
        p = get_profile("development")
        assert p is not None
        assert p["timing_model"] == "uniform"
        assert p["batch_size"] == 10
        assert p["parallel_processing"] is True
        assert p["operation"] == "link"

    def test_steady_values(self) -> None:
        p = get_profile("steady")
        assert p is not None
        assert p["timing_model"] == "random"
        assert p["timing_model_params"]["random_factor"] == 0.15
        assert p["parallel_processing"] is False

    def test_bursty_values(self) -> None:
        p = get_profile("bursty")
        assert p is not None
        assert p["timing_model"] == "poisson"
        assert p["timing_model_params"]["burst_probability"] == 0.12

    def test_high_throughput_values(self) -> None:
        p = get_profile("high_throughput")
        assert p is not None
        assert p["timing_model"] == "poisson"
        assert p["batch_size"] == 15
        assert p["worker_count"] == 12

    def test_gradual_drift_values(self) -> None:
        p = get_profile("gradual_drift")
        assert p is not None
        assert p["timing_model"] == "adaptive"
        assert p["timing_model_params"]["adaptation_rate"] == 0.15

    def test_generate_test_values(self) -> None:
        p = get_profile("generate_test")
        assert p is not None
        assert p["read_count"] == 100
        assert p["reads_per_file"] == 50
        assert p["generator_backend"] == "builtin"

    def test_generate_standard_values(self) -> None:
        p = get_profile("generate_standard")
        assert p is not None
        assert p["read_count"] == 5000
        assert p["reads_per_file"] == 100
        assert p["generator_backend"] == "auto"


class TestListProfiles:
    """Validate list_profiles returns names and descriptions."""

    def test_returns_dict(self) -> None:
        result = list_profiles()
        assert isinstance(result, dict)

    def test_contains_all_profiles(self) -> None:
        result = list_profiles()
        for name in PROFILES:
            assert name in result

    def test_values_are_descriptions(self) -> None:
        result = list_profiles()
        for name, desc in result.items():
            assert isinstance(desc, str)
            assert len(desc) > 0


class TestApplyProfile:
    """Validate apply_profile returns parameters with optional overrides."""

    def test_basic_apply(self) -> None:
        params = apply_profile("development")
        assert params["timing_model"] == "uniform"
        assert params["batch_size"] == 10

    def test_returns_config_params_only(self) -> None:
        """Result should not contain the description (metadata only)."""
        params = apply_profile("development")
        assert "description" not in params

    def test_with_overrides(self) -> None:
        params = apply_profile("development", overrides={"batch_size": 99})
        assert params["batch_size"] == 99
        # Other values should remain from profile
        assert params["timing_model"] == "uniform"

    def test_override_timing_model(self) -> None:
        params = apply_profile("steady", overrides={"timing_model": "poisson"})
        assert params["timing_model"] == "poisson"

    def test_unknown_profile_raises(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            apply_profile("nonexistent_profile")

    def test_generate_profile_includes_read_params(self) -> None:
        params = apply_profile("generate_test")
        assert "read_count" in params
        assert "reads_per_file" in params
        assert "generator_backend" in params

    def test_replay_profile_omits_generate_params(self) -> None:
        """Replay profiles should not inject generate-mode defaults."""
        params = apply_profile("development")
        # These should not be present in a replay profile
        assert "read_count" not in params
        assert "generator_backend" not in params

    def test_overrides_none_means_no_change(self) -> None:
        params_no_override = apply_profile("bursty")
        params_none = apply_profile("bursty", overrides=None)
        assert params_no_override == params_none


class TestGetRecommendations:
    """Validate profile recommendations based on file count."""

    def test_returns_list(self) -> None:
        result = get_recommendations(10)
        assert isinstance(result, list)

    def test_small_file_count(self) -> None:
        recs = get_recommendations(10)
        assert "steady" in recs or "bursty" in recs

    def test_medium_file_count(self) -> None:
        recs = get_recommendations(200)
        assert "bursty" in recs or "gradual_drift" in recs

    def test_large_file_count(self) -> None:
        recs = get_recommendations(1000)
        assert "high_throughput" in recs

    def test_development_always_included(self) -> None:
        """Development should appear as a fallback recommendation."""
        recs = get_recommendations(50)
        assert "development" in recs

    def test_no_duplicates(self) -> None:
        recs = get_recommendations(100)
        assert len(recs) == len(set(recs))

    def test_max_five_recommendations(self) -> None:
        recs = get_recommendations(10)
        assert len(recs) <= 5

    def test_all_recommendations_are_valid_profiles(self) -> None:
        for count in [5, 50, 200, 1000]:
            recs = get_recommendations(count)
            for name in recs:
                assert (
                    name in PROFILES
                ), f"Recommendation '{name}' is not a valid profile"
