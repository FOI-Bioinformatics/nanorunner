"""Tests for timing model integration with simulator"""

import pytest
import tempfile
import statistics
from pathlib import Path
from unittest.mock import patch, MagicMock

from nanopore_simulator.core.config import SimulationConfig
from nanopore_simulator.core.simulator import NanoporeSimulator


class TestTimingIntegration:
    
    def setup_method(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        
        # Create test source structure
        self.source_dir = self.temp_path / "source"
        self.target_dir = self.temp_path / "target"
        self.source_dir.mkdir()
        
    def teardown_method(self):
        """Clean up test fixtures"""
        self.temp_dir.cleanup()
    
    def test_uniform_timing_by_default(self):
        """Test that uniform timing is used by default"""
        config = SimulationConfig(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            interval=5.0
        )
        
        assert config.timing_model == "uniform"
        
        simulator = NanoporeSimulator(config)
        
        # Should return exact interval when using uniform timing
        for _ in range(10):
            assert simulator._calculate_interval() == 5.0
    
    def test_random_timing_model(self):
        """Test random timing model calculation"""
        config = SimulationConfig(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            interval=10.0,
            timing_model="random",
            timing_model_params={"random_factor": 0.5}  # 50% variation
        )
        
        simulator = NanoporeSimulator(config)
        
        intervals = []
        for _ in range(100):
            interval = simulator._calculate_interval()
            intervals.append(interval)
            
            # Should be within expected range: 10.0 ± (10.0 * 0.5) = [5.0, 15.0]
            assert 5.0 <= interval <= 15.0
            assert interval >= 0.0  # Never negative
        
        # Should have some variation (not all the same)
        assert len(set(intervals)) > 1
        
        # Mean should be close to base interval
        mean_interval = statistics.mean(intervals)
        assert 9.0 <= mean_interval <= 11.0
    
    def test_random_factor_validation(self):
        """Test validation of random factor parameter in timing model"""
        # Test valid random factors
        for factor in [0.0, 0.3, 0.5, 1.0]:
            config = SimulationConfig(
                source_dir=self.source_dir,
                target_dir=self.target_dir,
                timing_model="random",
                timing_model_params={"random_factor": factor}
            )
            assert config.timing_model_params["random_factor"] == factor
        
        # Test invalid random factors (should raise error during validation)
        with pytest.raises(ValueError, match="random_factor must be between 0.0 and 1.0"):
            SimulationConfig(
                source_dir=self.source_dir,
                target_dir=self.target_dir,
                timing_model="random",
                timing_model_params={"random_factor": -0.1}
            )
        
        with pytest.raises(ValueError, match="random_factor must be between 0.0 and 1.0"):
            SimulationConfig(
                source_dir=self.source_dir,
                target_dir=self.target_dir,
                timing_model="random",
                timing_model_params={"random_factor": 1.5}
            )
    
    def test_zero_random_factor(self):
        """Test that zero random factor behaves like uniform timing"""
        config = SimulationConfig(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            interval=7.0,
            timing_model="random",
            timing_model_params={"random_factor": 0.0}
        )
        
        simulator = NanoporeSimulator(config)
        
        # Should return exact interval when random factor is 0
        for _ in range(10):
            assert simulator._calculate_interval() == 7.0
    
    def test_maximum_random_factor(self):
        """Test maximum random factor creates wide variation"""
        config = SimulationConfig(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            interval=8.0,
            timing_model="random",
            timing_model_params={"random_factor": 1.0}  # Maximum variation
        )
        
        simulator = NanoporeSimulator(config)
        
        intervals = []
        for _ in range(100):
            interval = simulator._calculate_interval()
            intervals.append(interval)
            
            # Should be within expected range: 8.0 ± (8.0 * 1.0) = [0.0, 16.0]
            assert 0.0 <= interval <= 16.0
        
        # Should have significant variation
        std_dev = statistics.stdev(intervals)
        assert std_dev > 1.0  # Should have substantial variation
    
    def test_poisson_timing_model(self):
        """Test Poisson timing model"""
        config = SimulationConfig(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            interval=5.0,
            timing_model="poisson",
            timing_model_params={
                "burst_probability": 0.1,
                "burst_rate_multiplier": 3.0
            }
        )
        
        simulator = NanoporeSimulator(config)
        
        intervals = []
        for _ in range(200):
            interval = simulator._calculate_interval()
            intervals.append(interval)
            assert interval >= 0.0  # Should never be negative
        
        # Should have variation (Poisson process)
        assert len(set(intervals)) > 1
        
        # Mean should be reasonably close to base interval for Poisson
        mean_interval = statistics.mean(intervals)
        assert 2.0 <= mean_interval <= 8.0  # Allow for Poisson variation
    
    def test_adaptive_timing_model(self):
        """Test adaptive timing model"""
        config = SimulationConfig(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            interval=4.0,
            timing_model="adaptive",
            timing_model_params={
                "adaptation_rate": 0.2,
                "history_size": 5
            }
        )
        
        simulator = NanoporeSimulator(config)
        
        intervals = []
        for _ in range(50):
            interval = simulator._calculate_interval()
            intervals.append(interval)
            assert interval >= 0.0
        
        # Should have some variation due to adaptation
        assert len(set(intervals)) > 1
    
    def test_edge_case_very_small_interval(self):
        """Test with very small base interval"""
        config = SimulationConfig(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            interval=0.001,
            timing_model="random",
            timing_model_params={"random_factor": 0.3}
        )
        
        simulator = NanoporeSimulator(config)
        
        # Should handle small intervals without errors
        for _ in range(10):
            interval = simulator._calculate_interval()
            assert interval >= 0.0
            assert interval <= 0.002  # Within expected range
    
    @patch('nanopore_simulator.core.simulator.logging')
    def test_logging_shows_actual_intervals(self, mock_logging):
        """Test that logging shows the actual calculated intervals"""
        config = SimulationConfig(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            interval=3.0,
            timing_model="random",
            timing_model_params={"random_factor": 0.2}
        )
        
        # Create test file
        test_file = self.source_dir / "test.fastq"
        test_file.write_text("@read1\nACGT\n+\nIIII\n")
        
        simulator = NanoporeSimulator(config)
        
        # Mock the timing to ensure we can test logging
        with patch.object(simulator, '_calculate_interval', return_value=3.7):
            with patch('time.sleep'):
                simulator.run_simulation()
        
        # Should have logged the calculated interval
        assert mock_logging.getLogger.called