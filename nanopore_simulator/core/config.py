"""Configuration management for nanopore simulator"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any


@dataclass
class SimulationConfig:
    """Configuration for the simulation run"""

    source_dir: Optional[Path] = None
    target_dir: Optional[Path] = None
    interval: float = 5.0  # base seconds between file operations
    operation: str = "copy"  # "copy", "link", or "generate"
    file_types: Optional[List[str]] = None
    force_structure: Optional[str] = None  # "singleplex" or "multiplex"
    batch_size: int = 1  # files to process per interval

    # Legacy parameters removed - use timing_model="random" with timing_model_params instead

    # New timing model parameters
    timing_model: str = "uniform"  # "uniform", "random", "poisson", "adaptive"
    timing_model_params: Optional[Dict[str, Any]] = (
        None  # additional timing model parameters
    )

    # Parallel processing parameters
    parallel_processing: bool = False  # enable parallel file processing within batches
    worker_count: int = 4  # number of worker threads for parallel processing

    # Read generation parameters (for operation="generate")
    genome_inputs: Optional[List[Path]] = None
    generator_backend: str = "auto"
    read_count: int = 1000
    mean_read_length: int = 5000
    std_read_length: int = 2000
    min_read_length: int = 200
    mean_quality: float = 10.0
    reads_per_file: int = 100
    output_format: str = "fastq.gz"
    mix_reads: bool = False  # singleplex: mix genomes into shared files

    # Species-based generation parameters
    species_inputs: Optional[List[str]] = None  # Species names to resolve
    mock_name: Optional[str] = None  # Preset mock community name
    taxid_inputs: Optional[List[int]] = None  # Direct NCBI taxonomy IDs
    sample_type: Optional[str] = None  # "pure" or "mixed"
    abundances: Optional[List[float]] = None  # Custom abundances for mixed samples
    offline_mode: bool = False  # Use only cached genomes

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
        if self.operation not in {"copy", "link", "generate"}:
            raise ValueError("operation must be 'copy', 'link', or 'generate'")

        # Validate generate-specific parameters
        if self.operation == "generate":
            # Must have either genome_inputs OR species-based inputs
            has_genome_inputs = bool(self.genome_inputs)
            has_species_inputs = bool(
                self.species_inputs or self.mock_name or self.taxid_inputs
            )
            if not has_genome_inputs and not has_species_inputs:
                raise ValueError(
                    "generate operation requires genome_inputs, species_inputs, "
                    "mock_name, or taxid_inputs"
                )
            # Validate genome_inputs if provided
            if self.genome_inputs:
                for gpath in self.genome_inputs:
                    if not gpath.exists():
                        raise ValueError(f"Genome file does not exist: {gpath}")
            if self.target_dir is None:
                raise ValueError("target_dir must be provided for generate operation")
            if self.read_count < 1:
                raise ValueError("read_count must be at least 1")
            if self.mean_read_length < 1:
                raise ValueError("mean_read_length must be at least 1")
            if self.min_read_length < 1:
                raise ValueError("min_read_length must be at least 1")
            if self.reads_per_file < 1:
                raise ValueError("reads_per_file must be at least 1")
            if self.output_format not in ("fastq", "fastq.gz"):
                raise ValueError("output_format must be 'fastq' or 'fastq.gz'")
        else:
            # Non-generate operations require source_dir
            if self.source_dir is None:
                raise ValueError("source_dir is required for copy/link operations")

        # Validate force_structure
        if self.force_structure is not None and self.force_structure not in {
            "singleplex",
            "multiplex",
        }:
            raise ValueError("force_structure must be 'singleplex' or 'multiplex'")

        # Validate species-based generation
        if self.species_inputs or self.mock_name or self.taxid_inputs:
            # Validate sample_type
            if self.sample_type is None:
                # Default: mixed for mock, pure for species
                if self.mock_name:
                    object.__setattr__(self, "sample_type", "mixed")
                else:
                    object.__setattr__(self, "sample_type", "pure")

            if self.sample_type not in {"pure", "mixed"}:
                raise ValueError("sample_type must be 'pure' or 'mixed'")

            # Validate abundances
            if self.abundances is not None:
                if self.mock_name:
                    raise ValueError("abundances cannot be used with mock communities")
                input_count = len(self.species_inputs or []) + len(
                    self.taxid_inputs or []
                )
                if len(self.abundances) != input_count:
                    raise ValueError(
                        f"abundances count ({len(self.abundances)}) must match "
                        f"species/taxid count ({input_count})"
                    )
                total = sum(self.abundances)
                if not 0.99 <= total <= 1.01:
                    raise ValueError(f"abundances must sum to 1.0 (got {total:.3f})")

    def get_timing_model_config(self) -> Dict[str, Any]:
        """Get timing model configuration for factory function"""
        config = {"model_type": self.timing_model, "base_interval": self.interval}
        if self.timing_model_params is not None:
            config.update(self.timing_model_params)
        return config
