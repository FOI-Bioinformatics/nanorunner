"""Timing models for sequencing simulation.

Provides four timing patterns for controlling the interval between
batch operations:

- Uniform: constant intervals for deterministic testing
- Random: symmetric variation around a base interval
- Poisson: exponential intervals with burst clusters (not empirically
  validated against nanopore sequencing data)
- Adaptive: smoothly varying intervals via exponential moving average
"""

import random
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List


class TimingModel(ABC):
    """Abstract base class for timing models."""

    def __init__(self, base_interval: float) -> None:
        if base_interval < 0:
            raise ValueError("base_interval must be non-negative")
        self.base_interval = base_interval

    @abstractmethod
    def next_interval(self) -> float:
        """Calculate the next interval between file operations."""

    def reset(self) -> None:
        """Reset the timing model state (override if needed)."""


class UniformTimingModel(TimingModel):
    """Uniform timing model with fixed intervals."""

    def next_interval(self) -> float:
        return self.base_interval


class RandomTimingModel(TimingModel):
    """Random timing model with symmetric variation around base interval."""

    def __init__(self, base_interval: float, random_factor: float = 0.3) -> None:
        super().__init__(base_interval)
        if not 0.0 <= random_factor <= 1.0:
            raise ValueError("random_factor must be between 0.0 and 1.0")
        self.random_factor = random_factor

    def next_interval(self) -> float:
        random_value = (random.random() - 0.5) * 2  # Scale to [-1, 1]
        variation = self.base_interval * self.random_factor * random_value
        actual_interval = self.base_interval + variation
        return max(0.0, actual_interval)


class PoissonTimingModel(TimingModel):
    """Poisson-based timing model with exponential inter-event intervals.

    Generates intervals from a mixture of two exponential distributions:
    a base rate and an elevated burst rate. This produces irregular timing
    with occasional short-interval clusters. The model has not been
    validated against empirical nanopore sequencing data.
    """

    def __init__(
        self,
        base_interval: float,
        burst_probability: float = 0.1,
        burst_rate_multiplier: float = 5.0,
    ) -> None:
        super().__init__(base_interval)

        if not 0.0 <= burst_probability <= 1.0:
            raise ValueError("burst_probability must be between 0.0 and 1.0")
        if burst_rate_multiplier <= 0:
            raise ValueError("burst_rate_multiplier must be positive")

        self.burst_probability = burst_probability
        self.burst_rate_multiplier = burst_rate_multiplier
        self.base_rate = 1.0 / base_interval if base_interval > 0 else float("inf")

    def next_interval(self) -> float:
        """Generate next interval using Poisson process with burst mode."""
        if self.base_interval == 0:
            return 0.0

        if random.random() < self.burst_probability:
            rate = self.base_rate * self.burst_rate_multiplier
        else:
            rate = self.base_rate

        try:
            return random.expovariate(rate)
        except (ValueError, OverflowError):
            return self.base_interval


class AdaptiveTimingModel(TimingModel):
    """Timing model with smoothly varying intervals via exponential moving average.

    Generates exponentially distributed intervals and adjusts the rate
    parameter based on a moving average of its own recent output. This
    produces gradually drifting timing patterns. The model does not
    respond to external system metrics or processing load.
    """

    def __init__(
        self,
        base_interval: float,
        adaptation_rate: float = 0.1,
        history_size: int = 10,
    ) -> None:
        super().__init__(base_interval)

        if not 0.0 <= adaptation_rate <= 1.0:
            raise ValueError("adaptation_rate must be between 0.0 and 1.0")
        if history_size < 1:
            raise ValueError("history_size must be at least 1")

        self.adaptation_rate = adaptation_rate
        self.history_size = history_size
        self.interval_history: List[float] = []
        self.current_mean = base_interval

    def next_interval(self) -> float:
        """Generate next interval based on adaptive mean."""
        rate = 1.0 / self.current_mean if self.current_mean > 0 else float("inf")

        try:
            interval = random.expovariate(rate)
        except (ValueError, OverflowError):
            interval = self.current_mean

        self._update_history(interval)
        return interval

    def _update_history(self, interval: float) -> None:
        """Update interval history and adaptive mean."""
        self.interval_history.append(interval)

        if len(self.interval_history) > self.history_size:
            self.interval_history.pop(0)

        if len(self.interval_history) > 1:
            recent_mean = sum(self.interval_history) / len(self.interval_history)
            self.current_mean = (
                1 - self.adaptation_rate
            ) * self.current_mean + self.adaptation_rate * recent_mean

    def reset(self) -> None:
        """Reset the adaptive state."""
        self.interval_history.clear()
        self.current_mean = self.base_interval


_TIMING_REGISTRY: Dict[str, Callable[..., TimingModel]] = {
    "uniform": lambda base, **kw: UniformTimingModel(base),
    "random": lambda base, **kw: RandomTimingModel(base, kw.get("random_factor", 0.3)),
    "poisson": lambda base, **kw: PoissonTimingModel(
        base,
        kw.get("burst_probability", 0.1),
        kw.get("burst_rate_multiplier", 5.0),
    ),
    "adaptive": lambda base, **kw: AdaptiveTimingModel(
        base,
        kw.get("adaptation_rate", 0.1),
        kw.get("history_size", 10),
    ),
}


def create_timing_model(
    model_type: str, base_interval: float, **kwargs: Any
) -> TimingModel:
    """Factory function to create timing models.

    Args:
        model_type: One of "uniform", "random", "poisson", "adaptive".
        base_interval: Base interval in seconds.
        **kwargs: Additional parameters passed to the specific model.

    Returns:
        A configured TimingModel instance.

    Raises:
        ValueError: If model_type is not recognized or base_interval < 0.
    """
    factory = _TIMING_REGISTRY.get(model_type.lower())
    if factory is None:
        raise ValueError(f"Unknown timing model type: {model_type}")
    return factory(base_interval, **kwargs)
