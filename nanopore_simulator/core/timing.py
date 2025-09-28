"""Timing models for realistic sequencing simulation"""

import random
import time
from abc import ABC, abstractmethod
from typing import Optional, List, Any


class TimingModel(ABC):
    """Abstract base class for timing models"""
    
    def __init__(self, base_interval: float):
        if base_interval < 0:
            raise ValueError("base_interval must be non-negative")
        self.base_interval = base_interval
    
    @abstractmethod
    def next_interval(self) -> float:
        """Calculate the next interval between file operations"""
        pass
    
    def reset(self) -> None:
        """Reset the timing model state (override if needed)"""
        pass


class UniformTimingModel(TimingModel):
    """Uniform timing model with fixed intervals"""
    
    def next_interval(self) -> float:
        return self.base_interval


class RandomTimingModel(TimingModel):
    """Random timing model with symmetric variation around base interval"""
    
    def __init__(self, base_interval: float, random_factor: float = 0.3):
        super().__init__(base_interval)
        if not 0.0 <= random_factor <= 1.0:
            raise ValueError("random_factor must be between 0.0 and 1.0")
        self.random_factor = random_factor
    
    def next_interval(self) -> float:
        # Generate random variation: base_interval ± (base_interval * random_factor * random_value)
        # random_value is between -1 and 1 for symmetric variation
        random_value = (random.random() - 0.5) * 2  # Scale to [-1, 1]
        variation = self.base_interval * self.random_factor * random_value
        actual_interval = self.base_interval + variation
        
        # Ensure interval is never negative
        return max(0.0, actual_interval)


class PoissonTimingModel(TimingModel):
    """Poisson-based timing model simulating realistic sequencing patterns"""
    
    def __init__(self, base_interval: float, burst_probability: float = 0.1, 
                 burst_rate_multiplier: float = 5.0):
        super().__init__(base_interval)
        
        if not 0.0 <= burst_probability <= 1.0:
            raise ValueError("burst_probability must be between 0.0 and 1.0")
        if burst_rate_multiplier <= 0:
            raise ValueError("burst_rate_multiplier must be positive")
        
        self.burst_probability = burst_probability
        self.burst_rate_multiplier = burst_rate_multiplier
        
        # Convert interval to rate (events per second)
        # For Poisson process, rate = 1/mean_interval
        self.base_rate = 1.0 / base_interval if base_interval > 0 else float('inf')
    
    def next_interval(self) -> float:
        """Generate next interval using Poisson process with burst mode"""
        if self.base_interval == 0:
            return 0.0
        
        # Determine if this is a burst event
        if random.random() < self.burst_probability:
            # Burst mode: higher rate (shorter intervals)
            rate = self.base_rate * self.burst_rate_multiplier
        else:
            # Normal mode: base rate
            rate = self.base_rate
        
        # Generate exponentially distributed interval (Poisson process)
        try:
            return random.expovariate(rate)
        except (ValueError, OverflowError):
            # Fallback to base interval if rate calculation fails
            return self.base_interval


class AdaptiveTimingModel(TimingModel):
    """Adaptive timing model that learns from recent intervals"""
    
    def __init__(self, base_interval: float, adaptation_rate: float = 0.1, 
                 history_size: int = 10):
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
        """Generate next interval based on adaptive mean"""
        # Use exponential distribution around current mean
        rate = 1.0 / self.current_mean if self.current_mean > 0 else float('inf')
        
        try:
            interval = random.expovariate(rate)
        except (ValueError, OverflowError):
            interval = self.current_mean
        
        # Update history and adaptive mean
        self._update_history(interval)
        
        return interval
    
    def _update_history(self, interval: float) -> None:
        """Update interval history and adaptive mean"""
        self.interval_history.append(interval)
        
        # Keep only recent history
        if len(self.interval_history) > self.history_size:
            self.interval_history.pop(0)
        
        # Update adaptive mean using exponential moving average
        if len(self.interval_history) > 1:
            recent_mean = sum(self.interval_history) / len(self.interval_history)
            self.current_mean = (1 - self.adaptation_rate) * self.current_mean + \
                               self.adaptation_rate * recent_mean
    
    def reset(self) -> None:
        """Reset the adaptive state"""
        self.interval_history.clear()
        self.current_mean = self.base_interval


def create_timing_model(model_type: str, base_interval: float, **kwargs: Any) -> TimingModel:
    """Factory function to create timing models"""
    
    model_type = model_type.lower()
    
    if model_type == "uniform":
        return UniformTimingModel(base_interval)
    elif model_type == "random":
        random_factor = kwargs.get('random_factor', 0.3)
        return RandomTimingModel(base_interval, random_factor)
    elif model_type == "poisson":
        burst_probability = kwargs.get('burst_probability', 0.1)
        burst_rate_multiplier = kwargs.get('burst_rate_multiplier', 5.0)
        return PoissonTimingModel(base_interval, burst_probability, burst_rate_multiplier)
    elif model_type == "adaptive":
        adaptation_rate = kwargs.get('adaptation_rate', 0.1)
        history_size = kwargs.get('history_size', 10)
        return AdaptiveTimingModel(base_interval, adaptation_rate, history_size)
    else:
        raise ValueError(f"Unknown timing model type: {model_type}")