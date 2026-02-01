"""Read generation backends for simulating nanopore sequencing reads from genome FASTA files"""

import gzip
import logging
import math
import random
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ReadGeneratorConfig:
    """Configuration for read generation"""

    num_reads: int = 1000
    mean_read_length: int = 5000
    std_read_length: int = 2000
    min_read_length: int = 200
    mean_quality: float = 10.0
    std_quality: float = 2.0
    reads_per_file: int = 100
    output_format: str = "fastq.gz"

    def __post_init__(self) -> None:
        if self.num_reads < 1:
            raise ValueError("num_reads must be at least 1")
        if self.mean_read_length < 1:
            raise ValueError("mean_read_length must be at least 1")
        if self.std_read_length < 0:
            raise ValueError("std_read_length must be non-negative")
        if self.min_read_length < 1:
            raise ValueError("min_read_length must be at least 1")
        if self.mean_quality <= 0:
            raise ValueError("mean_quality must be positive")
        if self.std_quality < 0:
            raise ValueError("std_quality must be non-negative")
        if self.reads_per_file < 1:
            raise ValueError("reads_per_file must be at least 1")
        if self.output_format not in ("fastq", "fastq.gz"):
            raise ValueError("output_format must be 'fastq' or 'fastq.gz'")


@dataclass
class GenomeInput:
    """Represents a genome FASTA file with optional barcode assignment"""

    fasta_path: Path
    barcode: Optional[str] = None


def parse_fasta(fasta_path: Path) -> List[tuple]:
    """Parse a FASTA file and return list of (header, sequence) tuples.

    Supports both plain and gzipped FASTA files.
    """
    sequences = []
    current_header = None
    current_seq: List[str] = []

    open_fn = gzip.open if str(fasta_path).endswith(".gz") else open
    mode = "rt" if str(fasta_path).endswith(".gz") else "r"

    with open_fn(fasta_path, mode) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if current_header is not None:
                    sequences.append((current_header, "".join(current_seq)))
                current_header = line[1:].split()[0]
                current_seq = []
            else:
                current_seq.append(line.upper())

    if current_header is not None:
        sequences.append((current_header, "".join(current_seq)))

    return sequences


class ReadGenerator(ABC):
    """Abstract base class for read generation backends"""

    def __init__(self, config: ReadGeneratorConfig):
        self.config = config

    @abstractmethod
    def generate_reads(
        self, genome: GenomeInput, output_dir: Path, file_index: int
    ) -> Path:
        """Generate one FASTQ file of simulated reads from a genome.

        Args:
            genome: Input genome specification.
            output_dir: Directory to write the output file.
            file_index: Index for naming the output file.

        Returns:
            Path to the generated FASTQ file.
        """

    @classmethod
    @abstractmethod
    def is_available(cls) -> bool:
        """Check if this backend is available in the current environment."""

    def _output_filename(self, genome: GenomeInput, file_index: int) -> str:
        """Generate output filename based on genome and index."""
        stem = genome.fasta_path.stem
        # Remove .fasta or .fa suffix if double-extension like genome.fasta.gz
        if stem.endswith((".fasta", ".fa")):
            stem = Path(stem).stem
        ext = ".fastq.gz" if self.config.output_format == "fastq.gz" else ".fastq"
        return f"{stem}_reads_{file_index:04d}{ext}"


class BuiltinGenerator(ReadGenerator):
    """Built-in read generator using random subsequences from input genomes.

    Produces reads by sampling random positions from the genome sequence
    with log-normal length distribution and simple quality score simulation.
    No external dependencies required.
    """

    @classmethod
    def is_available(cls) -> bool:
        return True

    def generate_reads(
        self, genome: GenomeInput, output_dir: Path, file_index: int
    ) -> Path:
        sequences = parse_fasta(genome.fasta_path)
        if not sequences:
            raise ValueError(f"No sequences found in {genome.fasta_path}")

        # Concatenate all sequences for sampling
        full_seq = "".join(seq for _, seq in sequences)
        if len(full_seq) == 0:
            raise ValueError(f"Empty genome sequence in {genome.fasta_path}")

        output_dir.mkdir(parents=True, exist_ok=True)
        filename = self._output_filename(genome, file_index)
        output_path = output_dir / filename

        reads = self._sample_reads(full_seq, genome)
        self._write_fastq(reads, output_path)

        return output_path

    def _sample_reads(
        self, genome_seq: str, genome: GenomeInput
    ) -> List[tuple]:
        """Sample reads from the genome sequence.

        Returns list of (read_id, sequence, quality_string) tuples.
        """
        reads = []
        genome_len = len(genome_seq)

        # Log-normal parameters derived from mean and std
        mean_len = self.config.mean_read_length
        std_len = self.config.std_read_length
        if std_len > 0:
            variance = std_len**2
            mu = math.log(mean_len**2 / math.sqrt(variance + mean_len**2))
            sigma = math.sqrt(math.log(1 + variance / mean_len**2))
        else:
            mu = math.log(mean_len)
            sigma = 0.0

        for i in range(self.config.reads_per_file):
            # Sample read length from log-normal distribution
            if sigma > 0:
                read_len = int(random.lognormvariate(mu, sigma))
            else:
                read_len = mean_len
            read_len = max(self.config.min_read_length, read_len)
            read_len = min(read_len, genome_len)

            # Sample start position
            max_start = max(0, genome_len - read_len)
            start = random.randint(0, max_start) if max_start > 0 else 0
            seq = genome_seq[start : start + read_len]

            # Randomly reverse complement ~50% of reads
            if random.random() < 0.5:
                seq = self._reverse_complement(seq)

            # Generate quality scores
            quals = self._generate_quality_string(len(seq))

            stem = genome.fasta_path.stem
            read_id = f"{stem}_read_{i}"
            reads.append((read_id, seq, quals))

        return reads

    @staticmethod
    def _reverse_complement(seq: str) -> str:
        """Return the reverse complement of a DNA sequence."""
        complement = {"A": "T", "T": "A", "G": "C", "C": "G", "N": "N"}
        return "".join(complement.get(base, "N") for base in reversed(seq))

    def _generate_quality_string(self, length: int) -> str:
        """Generate a Phred+33 quality string."""
        quals = []
        for _ in range(length):
            q = random.gauss(self.config.mean_quality, self.config.std_quality)
            q = max(0, min(40, q))  # Clamp to valid Phred range
            quals.append(chr(int(q) + 33))
        return "".join(quals)

    def _write_fastq(self, reads: List[tuple], output_path: Path) -> None:
        """Write reads to a FASTQ file (plain or gzipped)."""
        open_fn = (
            gzip.open if output_path.suffix == ".gz" else open
        )
        with open_fn(output_path, "wt") as f:
            for read_id, seq, quals in reads:
                f.write(f"@{read_id}\n{seq}\n+\n{quals}\n")


class BadreadGenerator(ReadGenerator):
    """Read generator wrapping the badread simulate tool.

    Requires badread to be installed and available in PATH.
    """

    @classmethod
    def is_available(cls) -> bool:
        return shutil.which("badread") is not None

    def generate_reads(
        self, genome: GenomeInput, output_dir: Path, file_index: int
    ) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = self._output_filename(genome, file_index)
        output_path = output_dir / filename

        # badread outputs to stdout
        cmd = [
            "badread",
            "simulate",
            "--reference",
            str(genome.fasta_path),
            "--quantity",
            f"{self.config.reads_per_file}x",
            "--length",
            f"{self.config.mean_read_length},{self.config.std_read_length}",
        ]

        logger.info(f"Running badread: {' '.join(cmd)}")

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        if output_path.suffix == ".gz":
            with gzip.open(output_path, "wt") as f:
                f.write(result.stdout)
        else:
            output_path.write_text(result.stdout)

        return output_path


class NanoSimGenerator(ReadGenerator):
    """Read generator wrapping NanoSim.

    Requires nanosim or simulator.py to be available in PATH.
    """

    @classmethod
    def is_available(cls) -> bool:
        return (
            shutil.which("nanosim") is not None
            or shutil.which("simulator.py") is not None
        )

    @classmethod
    def _get_command(cls) -> str:
        """Get the NanoSim command name."""
        if shutil.which("nanosim") is not None:
            return "nanosim"
        return "simulator.py"

    def generate_reads(
        self, genome: GenomeInput, output_dir: Path, file_index: int
    ) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = self._output_filename(genome, file_index)
        output_path = output_dir / filename

        prefix = output_dir / f"nanosim_temp_{file_index}"

        cmd = [
            self._get_command(),
            "simulate",
            "linear",
            "-r",
            str(genome.fasta_path),
            "-n",
            str(self.config.reads_per_file),
            "-o",
            str(prefix),
        ]

        logger.info(f"Running NanoSim: {' '.join(cmd)}")

        subprocess.run(cmd, capture_output=True, text=True, check=True)

        # NanoSim writes to prefix_aligned_reads.fasta and prefix_unaligned_reads.fasta
        # Collect outputs into a single FASTQ
        aligned = Path(f"{prefix}_aligned_reads.fasta")
        unaligned = Path(f"{prefix}_unaligned_reads.fasta")

        all_seqs = []
        for fasta_file in [aligned, unaligned]:
            if fasta_file.exists():
                all_seqs.extend(parse_fasta(fasta_file))
                fasta_file.unlink()

        # Convert to FASTQ with synthetic quality scores
        open_fn = gzip.open if output_path.suffix == ".gz" else open
        with open_fn(output_path, "wt") as f:
            for header, seq in all_seqs:
                qual = "".join(
                    chr(int(max(0, min(40, random.gauss(self.config.mean_quality, self.config.std_quality)))) + 33)
                    for _ in range(len(seq))
                )
                f.write(f"@{header}\n{seq}\n+\n{qual}\n")

        return output_path


# Backend registry
_BACKENDS = {
    "builtin": BuiltinGenerator,
    "badread": BadreadGenerator,
    "nanosim": NanoSimGenerator,
}


def detect_available_backends() -> Dict[str, bool]:
    """Detect which read generation backends are available."""
    return {name: cls.is_available() for name, cls in _BACKENDS.items()}


def create_read_generator(
    backend: str, config: ReadGeneratorConfig
) -> ReadGenerator:
    """Factory function to create a read generator.

    Args:
        backend: Backend name or "auto" to select the best available.
        config: Read generation configuration.

    Returns:
        An initialized ReadGenerator instance.

    Raises:
        ValueError: If the requested backend is not available.
    """
    if backend == "auto":
        # Try backends in order of preference
        for name in ["badread", "nanosim", "builtin"]:
            cls = _BACKENDS[name]
            if cls.is_available():
                logger.info(f"Auto-selected read generation backend: {name}")
                return cls(config)
        raise RuntimeError("No read generation backend available")

    if backend not in _BACKENDS:
        raise ValueError(
            f"Unknown backend '{backend}'. Available: {list(_BACKENDS.keys())}"
        )

    cls = _BACKENDS[backend]
    if not cls.is_available():
        raise ValueError(
            f"Backend '{backend}' is not available in the current environment"
        )

    return cls(config)
