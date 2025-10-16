"""Tests for timing models"""

import pytest
import statistics
import time
from unittest.mock import patch

from nanopore_simulator.core.timing import (
    TimingModel,
    UniformTimingModel,
    RandomTimingModel,
    PoissonTimingModel,
    AdaptiveTimingModel,
    create_timing_model,
)


class TestTimingModelBase:
    """Test the abstract base class"""

    def test_base_class_cannot_be_instantiated(self):
        """Test that the abstract base class cannot be instantiated"""
        with pytest.raises(TypeError):
            TimingModel(5.0)

    def test_base_interval_validation(self):
        """Test that base interval validation works"""
        with pytest.raises(ValueError, match="base_interval must be non-negative"):
            UniformTimingModel(-1.0)


class TestUniformTimingModel:
    """Test the uniform timing model"""

    def test_uniform_interval(self):
        """Test that uniform model returns constant intervals"""
        model = UniformTimingModel(5.0)

        for _ in range(100):
            assert model.next_interval() == 5.0

    def test_zero_interval(self):
        """Test uniform model with zero interval"""
        model = UniformTimingModel(0.0)
        assert model.next_interval() == 0.0

    def test_reset_has_no_effect(self):
        """Test that reset doesn't change behavior for uniform model"""
        model = UniformTimingModel(3.0)
        assert model.next_interval() == 3.0
        model.reset()
        assert model.next_interval() == 3.0


class TestRandomTimingModel:
    """Test the random timing model"""

    def test_parameter_validation(self):
        """Test parameter validation for random model"""
        # Valid parameters
        RandomTimingModel(5.0, 0.3)

        # Invalid random_factor
        with pytest.raises(
            ValueError, match="random_factor must be between 0.0 and 1.0"
        ):
            RandomTimingModel(5.0, -0.1)

        with pytest.raises(
            ValueError, match="random_factor must be between 0.0 and 1.0"
        ):
            RandomTimingModel(5.0, 1.1)

    def test_random_factor_zero_equals_uniform(self):
        """Test that random_factor=0 behaves like uniform model"""
        model = RandomTimingModel(5.0, 0.0)

        for _ in range(100):
            assert model.next_interval() == 5.0

    def test_random_variation_range(self):
        """Test that random intervals stay within expected range"""
        base_interval = 10.0
        random_factor = 0.3
        model = RandomTimingModel(base_interval, random_factor)

        intervals = [model.next_interval() for _ in range(1000)]

        # All intervals should be non-negative
        assert all(interval >= 0 for interval in intervals)

        # Most intervals should be within expected range (allowing some statistical variance)
        expected_min = base_interval * (1 - random_factor)
        expected_max = base_interval * (1 + random_factor)

        within_range = sum(1 for i in intervals if expected_min <= i <= expected_max)
        assert within_range / len(intervals) > 0.95  # 95% should be within range

    def test_random_distribution_properties(self):
        """Test statistical properties of random distribution"""
        base_interval = 5.0
        random_factor = 0.5
        model = RandomTimingModel(base_interval, random_factor)

        intervals = [model.next_interval() for _ in range(10000)]

        # Mean should be close to base interval
        mean_interval = statistics.mean(intervals)
        assert abs(mean_interval - base_interval) < 0.1

        # Standard deviation should be related to random_factor
        std_dev = statistics.stdev(intervals)
        expected_std = base_interval * random_factor / 3  # Rough approximation
        assert 0.5 * expected_std < std_dev < 2.0 * expected_std


class TestPoissonTimingModel:
    """Test the Poisson timing model"""

    def test_parameter_validation(self):
        """Test parameter validation for Poisson model"""
        # Valid parameters
        PoissonTimingModel(5.0, 0.1, 3.0)

        # Invalid burst_probability
        with pytest.raises(
            ValueError, match="burst_probability must be between 0.0 and 1.0"
        ):
            PoissonTimingModel(5.0, -0.1)

        with pytest.raises(
            ValueError, match="burst_probability must be between 0.0 and 1.0"
        ):
            PoissonTimingModel(5.0, 1.1)

        # Invalid burst_rate_multiplier
        with pytest.raises(ValueError, match="burst_rate_multiplier must be positive"):
            PoissonTimingModel(5.0, 0.1, 0.0)

        with pytest.raises(ValueError, match="burst_rate_multiplier must be positive"):
            PoissonTimingModel(5.0, 0.1, -1.0)

    def test_zero_interval_handling(self):
        """Test handling of zero base interval"""
        model = PoissonTimingModel(0.0)
        assert model.next_interval() == 0.0

    def test_no_burst_approximates_exponential(self):
        """Test that with no bursts, intervals approximate exponential distribution"""
        base_interval = 5.0
        model = PoissonTimingModel(base_interval, burst_probability=0.0)

        intervals = [model.next_interval() for _ in range(10000)]

        # Mean should be close to base interval for exponential distribution
        mean_interval = statistics.mean(intervals)
        assert abs(mean_interval - base_interval) < 0.2

    def test_burst_mode_creates_shorter_intervals(self):
        """Test that burst mode creates shorter intervals on average"""
        base_interval = 10.0

        # Model with no bursts
        no_burst_model = PoissonTimingModel(base_interval, burst_probability=0.0)
        no_burst_intervals = [no_burst_model.next_interval() for _ in range(5000)]

        # Model with frequent bursts
        burst_model = PoissonTimingModel(
            base_interval, burst_probability=0.5, burst_rate_multiplier=5.0
        )
        burst_intervals = [burst_model.next_interval() for _ in range(5000)]

        # Burst model should have shorter average intervals
        assert statistics.mean(burst_intervals) < statistics.mean(no_burst_intervals)

    def test_exponential_distribution_properties(self):
        """Test that intervals follow exponential distribution properties"""
        base_interval = 2.0
        model = PoissonTimingModel(base_interval, burst_probability=0.0)

        intervals = [model.next_interval() for _ in range(10000)]

        # All intervals should be positive
        assert all(interval > 0 for interval in intervals)

        # For exponential distribution, P(X > t) = e^(-λt) where λ = 1/mean
        # So about 37% of intervals should be greater than the mean
        greater_than_mean = sum(1 for i in intervals if i > base_interval)
        proportion = greater_than_mean / len(intervals)
        assert (
            0.30 < proportion < 0.44
        )  # Allow some statistical variance around 1/e ≈ 0.368


class TestAdaptiveTimingModel:
    """Test the adaptive timing model"""

    def test_parameter_validation(self):
        """Test parameter validation for adaptive model"""
        # Valid parameters
        AdaptiveTimingModel(5.0, 0.1, 10)

        # Invalid adaptation_rate
        with pytest.raises(
            ValueError, match="adaptation_rate must be between 0.0 and 1.0"
        ):
            AdaptiveTimingModel(5.0, -0.1)

        with pytest.raises(
            ValueError, match="adaptation_rate must be between 0.0 and 1.0"
        ):
            AdaptiveTimingModel(5.0, 1.1)

        # Invalid history_size
        with pytest.raises(ValueError, match="history_size must be at least 1"):
            AdaptiveTimingModel(5.0, 0.1, 0)

    def test_initial_behavior(self):
        """Test initial behavior before adaptation"""
        base_interval = 5.0
        model = AdaptiveTimingModel(base_interval, 0.1, 5)

        # First few intervals should be around base interval (exponential distribution)
        intervals = [model.next_interval() for _ in range(100)]
        mean_initial = statistics.mean(intervals[:10])

        # Should be close to base interval (exponential has higher variance, so wider range)
        assert 0.2 * base_interval < mean_initial < 5.0 * base_interval

    def test_adaptation_occurs(self):
        """Test that the model adapts its mean over time"""
        base_interval = 5.0
        model = AdaptiveTimingModel(base_interval, 0.5, 5)  # High adaptation rate

        # Generate some intervals to build history
        initial_intervals = [model.next_interval() for _ in range(20)]
        initial_mean = model.current_mean

        # Generate more intervals
        later_intervals = [model.next_interval() for _ in range(20)]
        later_mean = model.current_mean

        # The current mean should have changed due to adaptation
        assert initial_mean != later_mean

    def test_reset_functionality(self):
        """Test that reset clears history and resets mean"""
        base_interval = 3.0
        model = AdaptiveTimingModel(base_interval, 0.3, 5)

        # Generate some intervals to change the state
        [model.next_interval() for _ in range(10)]
        adapted_mean = model.current_mean

        # Reset and check state
        model.reset()
        assert model.current_mean == base_interval
        assert len(model.interval_history) == 0
        assert (
            model.current_mean != adapted_mean
        )  # Should be different from adapted state

    def test_history_size_limit(self):
        """Test that history size is properly limited"""
        model = AdaptiveTimingModel(5.0, 0.1, 3)  # Small history size

        # Generate more intervals than history size
        [model.next_interval() for _ in range(10)]

        # History should not exceed the limit
        assert len(model.interval_history) <= 3


class TestTimingModelFactory:
    """Test the factory function for creating timing models"""

    def test_create_uniform_model(self):
        """Test creating uniform timing model"""
        model = create_timing_model("uniform", 5.0)
        assert isinstance(model, UniformTimingModel)
        assert model.base_interval == 5.0

    def test_create_random_model(self):
        """Test creating random timing model"""
        model = create_timing_model("random", 5.0, random_factor=0.4)
        assert isinstance(model, RandomTimingModel)
        assert model.base_interval == 5.0
        assert model.random_factor == 0.4

    def test_create_poisson_model(self):
        """Test creating Poisson timing model"""
        model = create_timing_model(
            "poisson", 5.0, burst_probability=0.2, burst_rate_multiplier=3.0
        )
        assert isinstance(model, PoissonTimingModel)
        assert model.base_interval == 5.0
        assert model.burst_probability == 0.2
        assert model.burst_rate_multiplier == 3.0

    def test_create_adaptive_model(self):
        """Test creating adaptive timing model"""
        model = create_timing_model(
            "adaptive", 5.0, adaptation_rate=0.2, history_size=8
        )
        assert isinstance(model, AdaptiveTimingModel)
        assert model.base_interval == 5.0
        assert model.adaptation_rate == 0.2
        assert model.history_size == 8

    def test_case_insensitive_model_type(self):
        """Test that model type is case insensitive"""
        model1 = create_timing_model("UNIFORM", 5.0)
        model2 = create_timing_model("Uniform", 5.0)
        model3 = create_timing_model("uniform", 5.0)

        assert all(isinstance(m, UniformTimingModel) for m in [model1, model2, model3])

    def test_unknown_model_type_raises_error(self):
        """Test that unknown model type raises ValueError"""
        with pytest.raises(ValueError, match="Unknown timing model type"):
            create_timing_model("unknown", 5.0)

    def test_default_parameters(self):
        """Test that default parameters are used when not specified"""
        # Random model with default random_factor
        model = create_timing_model("random", 5.0)
        assert isinstance(model, RandomTimingModel)
        assert model.random_factor == 0.3  # Default value

        # Poisson model with default parameters
        model = create_timing_model("poisson", 5.0)
        assert isinstance(model, PoissonTimingModel)
        assert model.burst_probability == 0.1  # Default value
        assert model.burst_rate_multiplier == 5.0  # Default value


class TestTimingModelIntegration:
    """Integration tests for timing models"""

    def test_models_produce_reasonable_intervals(self):
        """Test that all models produce reasonable intervals for typical use"""
        base_interval = 2.0
        models = [
            create_timing_model("uniform", base_interval),
            create_timing_model("random", base_interval, random_factor=0.3),
            create_timing_model("poisson", base_interval, burst_probability=0.1),
            create_timing_model("adaptive", base_interval, adaptation_rate=0.1),
        ]

        for model in models:
            intervals = [model.next_interval() for _ in range(100)]

            # All intervals should be non-negative
            assert all(interval >= 0 for interval in intervals)

            # Mean should be in a reasonable range (for most models should be close to base_interval)
            mean_interval = statistics.mean(intervals)
            assert 0.1 * base_interval < mean_interval < 10 * base_interval

    def test_performance_timing_models(self):
        """Test that timing models perform efficiently"""
        model = create_timing_model("poisson", 1.0, burst_probability=0.2)

        # Time how long it takes to generate many intervals
        start_time = time.time()
        intervals = [model.next_interval() for _ in range(10000)]
        elapsed = time.time() - start_time

        # Should complete quickly (less than 1 second for 10k intervals)
        assert elapsed < 1.0
        assert len(intervals) == 10000
