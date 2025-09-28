"""Configuration management for nanopore simulator"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any


@dataclass
class SimulationConfig:
    """Configuration for the simulation run"""
    source_dir: Path
    target_dir: Path
    interval: float = 5.0  # base seconds between file operations
    operation: str = "copy"  # "copy" or "link"
    file_types: Optional[List[str]] = None
    force_structure: Optional[str] = None  # "singleplex" or "multiplex"
    batch_size: int = 1  # files to process per interval
    
    # Legacy parameters removed - use timing_model="random" with timing_model_params instead
    
    # New timing model parameters
    timing_model: str = "uniform"  # "uniform", "random", "poisson", "adaptive"
    timing_model_params: Optional[Dict[str, Any]] = None  # additional timing model parameters
    
    # Parallel processing parameters
    parallel_processing: bool = False  # enable parallel file processing within batches
    worker_count: int = 4  # number of worker threads for parallel processing
    
    def __post_init__(self) -> None:
        if self.file_types is None:
            self.file_types = ["fastq", "fq", "fastq.gz", "fq.gz", "pod5"]
        else:
            # Create a copy to prevent external modification
            self.file_types = list(self.file_types)
        
        # No more legacy compatibility needed
        
        # Initialize timing model params if None
        if self.timing_model_params is None:
            self.timing_model_params = {}
        
        # Validate parameters
        self._validate_config()
    
    def _validate_config(self) -> None:
        """Validate configuration parameters"""
        # Validate basic parameters
        if self.interval < 0:
            raise ValueError("interval must be non-negative")
        
        # random_factor validation moved to timing model specific validation
        
        if self.batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        
        if self.worker_count < 1:
            raise ValueError("worker_count must be at least 1")
        
        # Validate timing model
        valid_timing_models = {"uniform", "random", "poisson", "adaptive"}
        if self.timing_model not in valid_timing_models:
            raise ValueError(f"timing_model must be one of: {valid_timing_models}")
        
        # Validate timing model specific parameters
        if self.timing_model_params is None:
            return  # No additional parameters to validate
            
        if self.timing_model == "random":
            rf = self.timing_model_params.get("random_factor", 0.3)
            if not 0.0 <= rf <= 1.0:
                raise ValueError("random_factor must be between 0.0 and 1.0")
        
        elif self.timing_model == "poisson":
            bp = self.timing_model_params.get("burst_probability", 0.1)
            if not 0.0 <= bp <= 1.0:
                raise ValueError("burst_probability must be between 0.0 and 1.0")
            
            brm = self.timing_model_params.get("burst_rate_multiplier", 5.0)
            if brm <= 0:
                raise ValueError("burst_rate_multiplier must be positive")
        
        elif self.timing_model == "adaptive":
            ar = self.timing_model_params.get("adaptation_rate", 0.1)
            if not 0.0 <= ar <= 1.0:
                raise ValueError("adaptation_rate must be between 0.0 and 1.0")
            
            hs = self.timing_model_params.get("history_size", 10)
            if hs < 1:
                raise ValueError("history_size must be at least 1")
        
        # Validate operation
        if self.operation not in {"copy", "link"}:
            raise ValueError("operation must be 'copy' or 'link'")
        
        # Validate force_structure
        if self.force_structure is not None and self.force_structure not in {"singleplex", "multiplex"}:
            raise ValueError("force_structure must be 'singleplex' or 'multiplex'")
    
    def get_timing_model_config(self) -> Dict[str, Any]:
        """Get timing model configuration for factory function"""
        config = {"model_type": self.timing_model, "base_interval": self.interval}
        if self.timing_model_params is not None:
            config.update(self.timing_model_params)
        return config