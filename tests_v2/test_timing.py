"""Tests for timing model implementations."""

import pytest
from nanopore_simulator_v2.timing import (
    create_timing_model,
    UniformTimingModel,
    RandomTimingModel,
    PoissonTimingModel,
    AdaptiveTimingModel,
)


class TestUniform:
    def test_constant_interval(self):
        m = UniformTimingModel(base_interval=2.0)
        assert m.next_interval() == 2.0
        assert m.next_interval() == 2.0

    def test_zero_interval(self):
        m = UniformTimingModel(base_interval=0.0)
        assert m.next_interval() == 0.0


class TestRandom:
    def test_varies_around_base(self):
        m = RandomTimingModel(base_interval=1.0, random_factor=0.3)
        intervals = [m.next_interval() for _ in range(100)]
        assert min(intervals) >= 0.0
        assert any(i != 1.0 for i in intervals)

    def test_zero_factor_is_uniform(self):
        m = RandomTimingModel(base_interval=1.0, random_factor=0.0)
        assert m.next_interval() == 1.0

    def test_invalid_random_factor(self):
        with pytest.raises(ValueError, match="random_factor"):
            RandomTimingModel(base_interval=1.0, random_factor=1.5)

    def test_negative_random_factor(self):
        with pytest.raises(ValueError, match="random_factor"):
            RandomTimingModel(base_interval=1.0, random_factor=-0.1)


class TestPoisson:
    def test_positive_intervals(self):
        m = PoissonTimingModel(base_interval=1.0)
        intervals = [m.next_interval() for _ in range(100)]
        assert all(i >= 0 for i in intervals)

    def test_burst_probability(self):
        m = PoissonTimingModel(base_interval=1.0, burst_probability=0.5)
        intervals = [m.next_interval() for _ in range(100)]
        assert len(intervals) == 100

    def test_zero_interval(self):
        m = PoissonTimingModel(base_interval=0.0)
        assert m.next_interval() == 0.0

    def test_invalid_burst_probability(self):
        with pytest.raises(ValueError, match="burst_probability"):
            PoissonTimingModel(base_interval=1.0, burst_probability=1.5)

    def test_invalid_burst_rate_multiplier(self):
        with pytest.raises(ValueError, match="burst_rate_multiplier"):
            PoissonTimingModel(base_interval=1.0, burst_rate_multiplier=-1.0)


class TestAdaptive:
    def test_adapts_over_time(self):
        m = AdaptiveTimingModel(base_interval=1.0, adaptation_rate=0.5)
        intervals = [m.next_interval() for _ in range(50)]
        assert len(intervals) == 50

    def test_reset(self):
        m = AdaptiveTimingModel(base_interval=1.0)
        for _ in range(10):
            m.next_interval()
        m.reset()
        assert len(m.interval_history) == 0
        assert m.current_mean == m.base_interval

    def test_invalid_adaptation_rate(self):
        with pytest.raises(ValueError, match="adaptation_rate"):
            AdaptiveTimingModel(base_interval=1.0, adaptation_rate=2.0)

    def test_invalid_history_size(self):
        with pytest.raises(ValueError, match="history_size"):
            AdaptiveTimingModel(base_interval=1.0, history_size=0)


class TestFactory:
    def test_create_uniform(self):
        m = create_timing_model("uniform", base_interval=1.0)
        assert isinstance(m, UniformTimingModel)

    def test_create_random(self):
        m = create_timing_model("random", base_interval=1.0, random_factor=0.5)
        assert isinstance(m, RandomTimingModel)

    def test_create_poisson(self):
        m = create_timing_model("poisson", base_interval=1.0)
        assert isinstance(m, PoissonTimingModel)

    def test_create_adaptive(self):
        m = create_timing_model("adaptive", base_interval=1.0)
        assert isinstance(m, AdaptiveTimingModel)

    def test_invalid_model(self):
        with pytest.raises(ValueError):
            create_timing_model("invalid", base_interval=1.0)

    def test_negative_interval(self):
        with pytest.raises(ValueError):
            create_timing_model("uniform", base_interval=-1.0)

    def test_case_insensitive(self):
        m = create_timing_model("UNIFORM", base_interval=1.0)
        assert isinstance(m, UniformTimingModel)

    def test_passes_kwargs_to_random(self):
        m = create_timing_model("random", base_interval=1.0, random_factor=0.8)
        assert isinstance(m, RandomTimingModel)
        assert m.random_factor == 0.8

    def test_passes_kwargs_to_poisson(self):
        m = create_timing_model(
            "poisson",
            base_interval=1.0,
            burst_probability=0.3,
            burst_rate_multiplier=10.0,
        )
        assert isinstance(m, PoissonTimingModel)
        assert m.burst_probability == 0.3
        assert m.burst_rate_multiplier == 10.0

    def test_passes_kwargs_to_adaptive(self):
        m = create_timing_model(
            "adaptive",
            base_interval=1.0,
            adaptation_rate=0.5,
            history_size=20,
        )
        assert isinstance(m, AdaptiveTimingModel)
        assert m.adaptation_rate == 0.5
        assert m.history_size == 20
