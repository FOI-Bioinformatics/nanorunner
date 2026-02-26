"""Configuration dataclasses for replay and generate modes.

Each config is a frozen dataclass with __post_init__ validation. Fields
map directly to CLI parameters. Validation is self-contained -- no
external dependencies.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


_VALID_TIMING_MODELS = {"uniform", "random", "poisson", "adaptive"}
_VALID_MONITOR_TYPES = {"basic", "enhanced", "none"}
_VALID_STRUCTURES_REPLAY = {"auto", "singleplex", "multiplex"}
_VALID_STRUCTURES_GENERATE = {"singleplex", "multiplex"}
_VALID_GENERATOR_BACKENDS = {"auto", "builtin", "badread", "nanosim"}
_VALID_OUTPUT_FORMATS = {"fastq", "fastq.gz"}

_DEFAULT_FILE_EXTENSIONS: Tuple[str, ...] = (
    ".fastq",
    ".fq",
    ".fastq.gz",
    ".fq.gz",
    ".pod5",
)


def _validate_common(
    interval: float,
    batch_size: int,
    timing_model: str,
    monitor_type: str,
    workers: int,
) -> None:
    """Validate fields shared by both configs."""
    if interval < 0:
        raise ValueError("interval must be non-negative")
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    if timing_model not in _VALID_TIMING_MODELS:
        raise ValueError(
            f"timing_model must be one of: {sorted(_VALID_TIMING_MODELS)}"
        )
    if monitor_type not in _VALID_MONITOR_TYPES:
        raise ValueError(
            f"monitor_type must be one of: {sorted(_VALID_MONITOR_TYPES)}"
        )
    if workers < 1:
        raise ValueError("workers must be at least 1")


@dataclass(frozen=True)
class ReplayConfig:
    """Configuration for replay mode (copy/link existing files).

    Attributes:
        source_dir: Directory containing source sequencing files.
        target_dir: Directory where files will be placed.
        operation: File transfer method -- "copy" or "link".
        interval: Base seconds between batch operations.
        batch_size: Number of files to process per interval.
        file_extensions: Tuple of file extensions to include.
        timing_model: Timing pattern -- uniform, random, poisson, or adaptive.
        timing_params: Additional parameters for the timing model.
        parallel: Enable parallel file processing within batches.
        workers: Number of worker threads for parallel processing.
        monitor_type: Progress display type -- "basic" or "enhanced".
        adapter: Pipeline adapter name, or None.
        reads_per_output: Rechunk FASTQ files to this many reads per output file.
        structure: Source directory layout -- "auto", "singleplex", or "multiplex".
    """

    source_dir: Path
    target_dir: Path
    operation: str = "copy"
    interval: float = 5.0
    batch_size: int = 1
    file_extensions: Tuple[str, ...] = _DEFAULT_FILE_EXTENSIONS
    timing_model: str = "uniform"
    timing_params: Dict[str, Any] = field(default_factory=dict)
    parallel: bool = False
    workers: int = 4
    monitor_type: str = "basic"
    adapter: Optional[str] = None
    reads_per_output: Optional[int] = None
    structure: str = "auto"

    def __post_init__(self) -> None:
        _validate_common(
            self.interval,
            self.batch_size,
            self.timing_model,
            self.monitor_type,
            self.workers,
        )
        if not self.source_dir.exists():
            raise ValueError(
                f"source_dir does not exist: {self.source_dir}"
            )
        if self.operation not in {"copy", "link"}:
            raise ValueError("operation must be 'copy' or 'link'")
        if self.structure not in _VALID_STRUCTURES_REPLAY:
            raise ValueError(
                f"structure must be one of: {sorted(_VALID_STRUCTURES_REPLAY)}"
            )
        if self.reads_per_output is not None:
            if self.reads_per_output < 1:
                raise ValueError("reads_per_output must be at least 1")
            if self.operation == "link":
                raise ValueError(
                    "rechunking is incompatible with operation='link' "
                    "because it requires reading and rewriting file contents"
                )


@dataclass(frozen=True)
class GenerateConfig:
    """Configuration for generate mode (produce simulated reads).

    At least one input source must be provided: genome_inputs,
    species_inputs, mock_name, or taxid_inputs.

    Attributes:
        target_dir: Directory where generated files will be placed.
        genome_inputs: Paths to genome FASTA files.
        species_inputs: Species names to resolve via GTDB/NCBI.
        mock_name: Preset mock community name.
        taxid_inputs: NCBI taxonomy IDs.
        abundances: Per-genome abundance fractions (must sum to ~1.0).
        read_count: Total reads to generate across all organisms.
        interval: Base seconds between batch operations.
        batch_size: Number of files to process per interval.
        generator_backend: Read generation backend -- auto, builtin, badread, or nanosim.
        mean_length: Mean read length in bases.
        std_length: Standard deviation of read length.
        min_length: Minimum read length in bases.
        mean_quality: Mean Phred quality score.
        std_quality: Standard deviation of quality score.
        reads_per_file: Number of reads per output file.
        output_format: Output file format -- "fastq" or "fastq.gz".
        mix_reads: Mix reads from different genomes into shared files.
        timing_model: Timing pattern -- uniform, random, poisson, or adaptive.
        timing_params: Additional parameters for the timing model.
        parallel: Enable parallel file processing within batches.
        workers: Number of worker threads for parallel processing.
        monitor_type: Progress display type -- "basic" or "enhanced".
        adapter: Pipeline adapter name, or None.
        structure: Output directory layout -- "singleplex" or "multiplex".
        offline_mode: Use only cached genomes, no network requests.
    """

    target_dir: Path
    genome_inputs: Optional[List[Path]] = None
    species_inputs: Optional[List[str]] = None
    mock_name: Optional[str] = None
    taxid_inputs: Optional[List[str]] = None
    abundances: Optional[List[float]] = None
    read_count: int = 1000
    interval: float = 5.0
    batch_size: int = 100
    generator_backend: str = "auto"
    mean_length: int = 5000
    std_length: int = 2000
    min_length: int = 200
    mean_quality: float = 20.0
    std_quality: float = 4.0
    reads_per_file: int = 100
    output_format: str = "fastq.gz"
    mix_reads: bool = False
    timing_model: str = "uniform"
    timing_params: Dict[str, Any] = field(default_factory=dict)
    parallel: bool = False
    workers: int = 4
    monitor_type: str = "basic"
    adapter: Optional[str] = None
    structure: str = "singleplex"
    offline_mode: bool = False

    def __post_init__(self) -> None:
        _validate_common(
            self.interval,
            self.batch_size,
            self.timing_model,
            self.monitor_type,
            self.workers,
        )
        # At least one input source required
        has_input = bool(
            self.genome_inputs
            or self.species_inputs
            or self.mock_name
            or self.taxid_inputs
        )
        if not has_input:
            raise ValueError(
                "at least one input source required: "
                "genome_inputs, species_inputs, mock_name, or taxid_inputs"
            )
        if self.read_count < 1:
            raise ValueError("read_count must be at least 1")
        if self.generator_backend not in _VALID_GENERATOR_BACKENDS:
            raise ValueError(
                f"generator_backend must be one of: "
                f"{sorted(_VALID_GENERATOR_BACKENDS)}"
            )
        if self.output_format not in _VALID_OUTPUT_FORMATS:
            raise ValueError(
                f"output_format must be one of: {sorted(_VALID_OUTPUT_FORMATS)}"
            )
        if self.structure not in _VALID_STRUCTURES_GENERATE:
            raise ValueError(
                f"structure must be one of: "
                f"{sorted(_VALID_STRUCTURES_GENERATE)}"
            )
        # Validate abundances if provided with genome_inputs
        if self.abundances is not None:
            input_count = len(self.genome_inputs or [])
            if len(self.abundances) != input_count:
                raise ValueError(
                    f"abundances count ({len(self.abundances)}) must match "
                    f"genome count ({input_count})"
                )
            total = sum(self.abundances)
            if not 0.99 <= total <= 1.01:
                raise ValueError(
                    f"abundances must sum to 1.0 (got {total:.3f})"
                )
