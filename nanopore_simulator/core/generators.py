"""Read generation backends for simulating nanopore sequencing reads from genome FASTA files"""

import gzip
import logging
import math
import random
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import numpy as np

    _HAS_NUMPY = True
except ImportError:  # pragma: no cover
    _HAS_NUMPY = False

logger = logging.getLogger(__name__)

# Module-level genome cache for ProcessPoolExecutor workers.
# Populated by _init_worker_genomes() which is passed as the
# ``initializer`` argument when the pool is created, so each worker
# process receives pre-parsed genome data without redundant I/O.
_WORKER_GENOME_CACHE: Dict[str, str] = {}


def _init_worker_genomes(genome_data: Dict[str, str]) -> None:
    """Initializer for ProcessPoolExecutor workers.

    Pre-populates the module-level genome cache so that workers can
    skip redundant FASTA parsing.
    """
    global _WORKER_GENOME_CACHE
    _WORKER_GENOME_CACHE = genome_data


def _generate_quality_string_numpy(
    rng: "np.random.Generator", mean: float, std: float, length: int
) -> str:
    """Generate a Phred+33 quality string using numpy vectorized operations.

    This is a shared helper used by generators that need synthetic quality
    scores when numpy is available.
    """
    raw = rng.normal(mean, std, length) if std > 0 else np.full(length, mean)
    clipped = np.clip(raw, 0, 40).astype(np.int8)
    return (clipped + 33).tobytes().decode("ascii")


@dataclass
class ReadGeneratorConfig:
    """Configuration for read generation"""

    num_reads: int = 1000
    mean_read_length: int = 5000
    std_read_length: int = 2000
    min_read_length: int = 200
    mean_quality: float = 20.0  # Q20 typical for R10.4.1 with SUP basecalling
    std_quality: float = 4.0
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
                    sequences.append(
                        (current_header, "".join(current_seq).upper())
                    )
                current_header = line[1:].split()[0]
                current_seq = []
            else:
                current_seq.append(line)

    if current_header is not None:
        sequences.append((current_header, "".join(current_seq).upper()))

    return sequences


class ReadGenerator(ABC):
    """Abstract base class for read generation backends"""

    def __init__(self, config: ReadGeneratorConfig):
        self.config = config

    @abstractmethod
    def generate_reads(
        self,
        genome: GenomeInput,
        output_dir: Path,
        file_index: int,
        num_reads: Optional[int] = None,
    ) -> Path:
        """Generate one FASTQ file of simulated reads from a genome.

        Args:
            genome: Input genome specification.
            output_dir: Directory to write the output file.
            file_index: Index for naming the output file.
            num_reads: Number of reads to generate. If None, uses
                config.reads_per_file.

        Returns:
            Path to the generated FASTQ file.
        """

    @classmethod
    @abstractmethod
    def is_available(cls) -> bool:
        """Check if this backend is available in the current environment."""

    def generate_reads_in_memory(
        self,
        genome: GenomeInput,
        num_reads: int,
    ) -> List[Tuple[str, str, str, str]]:
        """Generate reads and return them as in-memory FASTQ 4-tuples.

        Each tuple is (header, sequence, separator, quality) with the header
        including the leading ``@``.  The default implementation writes to a
        temporary file, then parses it back.  Subclasses may override this
        for a more efficient path.

        Args:
            genome: Input genome specification.
            num_reads: Number of reads to generate.

        Returns:
            List of 4-tuples suitable for :func:`write_fastq_reads`.
        """
        from .fastq import iter_fastq_reads

        with tempfile.TemporaryDirectory() as td:
            output_path = self.generate_reads(
                genome, Path(td), file_index=0, num_reads=num_reads
            )
            return list(iter_fastq_reads(output_path))

    def _output_filename(self, genome: GenomeInput, file_index: int) -> str:
        """Generate output filename based on genome and index."""
        stem = genome.fasta_path.stem
        # Remove .fasta/.fa/.fna suffix if double-extension like genome.fasta.gz
        if stem.endswith((".fasta", ".fa", ".fna")):
            stem = Path(stem).stem
        ext = ".fastq.gz" if self.config.output_format == "fastq.gz" else ".fastq"
        return f"{stem}_reads_{file_index:04d}{ext}"


class BuiltinGenerator(ReadGenerator):
    """Built-in read generator using random subsequences from input genomes.

    Produces reads by sampling random positions from the genome sequence
    with log-normal length distribution and simulated quality scores.
    No external dependencies required.

    Limitations:
        - Reads are error-free subsequences of the reference genome.
        - No substitution, insertion, or deletion errors are introduced.
        - Quality scores are sampled independently and do not correlate
          with actual sequencing errors.
        - Classification accuracy benchmarks using these reads will
          overestimate real-world performance.

    For reads with realistic error profiles, use the badread or nanosim
    backends (install separately).
    """

    def __init__(self, config: ReadGeneratorConfig):
        super().__init__(config)
        self._genome_cache: Dict[Path, str] = {}
        self._np_rng: Optional["np.random.Generator"] = None
        if _HAS_NUMPY:
            self._np_rng = np.random.default_rng()

    @classmethod
    def is_available(cls) -> bool:
        return True

    def _get_genome_sequence(self, genome: GenomeInput) -> str:
        """Return the concatenated genome sequence, caching by resolved path.

        Raises:
            ValueError: If the FASTA file contains no sequences or the
                concatenated sequence is empty.
        """
        key = genome.fasta_path.resolve()
        if key in self._genome_cache:
            return self._genome_cache[key]

        sequences = parse_fasta(genome.fasta_path)
        if not sequences:
            raise ValueError(f"No sequences found in {genome.fasta_path}")

        full_seq = "".join(seq for _, seq in sequences)
        if len(full_seq) == 0:
            raise ValueError(f"Empty genome sequence in {genome.fasta_path}")

        self._genome_cache[key] = full_seq
        return full_seq

    def generate_reads(
        self,
        genome: GenomeInput,
        output_dir: Path,
        file_index: int,
        num_reads: Optional[int] = None,
    ) -> Path:
        full_seq = self._get_genome_sequence(genome)

        output_dir.mkdir(parents=True, exist_ok=True)
        filename = self._output_filename(genome, file_index)
        output_path = output_dir / filename

        actual_reads = num_reads if num_reads is not None else self.config.reads_per_file
        reads = self._sample_reads(full_seq, genome, actual_reads)
        self._write_fastq(reads, output_path)

        return output_path

    def generate_reads_in_memory(
        self,
        genome: GenomeInput,
        num_reads: int,
    ) -> List[Tuple[str, str, str, str]]:
        """Return reads as FASTQ 4-tuples without writing to disk."""
        full_seq = self._get_genome_sequence(genome)

        raw_reads = self._sample_reads(full_seq, genome, num_reads)
        return [
            (f"@{read_id}", seq, "+", quals)
            for read_id, seq, quals in raw_reads
        ]

    def _sample_reads(
        self, genome_seq: str, genome: GenomeInput, num_reads: int
    ) -> List[tuple]:
        """Sample reads from the genome sequence.

        Returns list of (read_id, sequence, quality_string) tuples.
        Uses numpy for batch-generating random values when available.
        """
        genome_len = len(genome_seq)
        stem = genome.fasta_path.stem

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

        if self._np_rng is not None:
            return self._sample_reads_numpy(
                genome_seq, genome_len, stem, num_reads, mu, sigma
            )

        # Stdlib fallback
        reads = []
        for i in range(num_reads):
            if sigma > 0:
                read_len = int(random.lognormvariate(mu, sigma))
            else:
                read_len = mean_len
            read_len = max(self.config.min_read_length, read_len)
            read_len = min(read_len, genome_len)

            max_start = max(0, genome_len - read_len)
            start = random.randint(0, max_start) if max_start > 0 else 0
            seq = genome_seq[start : start + read_len]

            if random.random() < 0.5:
                seq = self._reverse_complement(seq)

            quals = self._generate_quality_string(len(seq))
            read_id = f"{stem}_read_{i}"
            reads.append((read_id, seq, quals))

        return reads

    def _sample_reads_numpy(
        self,
        genome_seq: str,
        genome_len: int,
        stem: str,
        num_reads: int,
        mu: float,
        sigma: float,
    ) -> List[tuple]:
        """Vectorized read sampling using numpy for batch random generation."""
        rng = self._np_rng
        min_len = self.config.min_read_length
        mean_q = self.config.mean_quality
        std_q = self.config.std_quality

        # Batch-generate read lengths
        if sigma > 0:
            raw_lengths = rng.lognormal(mu, sigma, num_reads)
            lengths = np.clip(raw_lengths.astype(int), min_len, genome_len)
        else:
            lengths = np.full(num_reads, min(self.config.mean_read_length, genome_len))

        # Batch-generate RC decisions
        rc_flags = rng.random(num_reads) < 0.5

        reads = []
        for i in range(num_reads):
            read_len = int(lengths[i])
            max_start = max(0, genome_len - read_len)
            start = int(rng.integers(0, max_start + 1)) if max_start > 0 else 0
            seq = genome_seq[start : start + read_len]

            if rc_flags[i]:
                seq = self._reverse_complement(seq)

            quals = _generate_quality_string_numpy(rng, mean_q, std_q, len(seq))
            read_id = f"{stem}_read_{i}"
            reads.append((read_id, seq, quals))

        return reads

    _COMP_TABLE = str.maketrans("ACGTNacgtn", "TGCANtgcan")

    @staticmethod
    def _reverse_complement(seq: str) -> str:
        """Return the reverse complement of a DNA sequence."""
        return seq.translate(BuiltinGenerator._COMP_TABLE)[::-1]

    def _generate_quality_string(self, length: int) -> str:
        """Generate a Phred+33 quality string."""
        if self._np_rng is not None:
            return _generate_quality_string_numpy(
                self._np_rng,
                self.config.mean_quality,
                self.config.std_quality,
                length,
            )
        quals = []
        for _ in range(length):
            q = random.gauss(self.config.mean_quality, self.config.std_quality)
            q = max(0, min(40, q))  # Clamp to valid Phred range
            quals.append(chr(int(q) + 33))
        return "".join(quals)

    def _write_fastq(self, reads: List[tuple], output_path: Path) -> None:
        """Write reads to a FASTQ file (plain or gzipped)."""
        if output_path.suffix == ".gz":
            f = gzip.open(output_path, "wt", compresslevel=1)
        else:
            f = open(output_path, "w")
        with f:
            f.write(
                "".join(
                    f"@{read_id}\n{seq}\n+\n{quals}\n"
                    for read_id, seq, quals in reads
                )
            )


class BadreadGenerator(ReadGenerator):
    """Read generator wrapping the badread simulate tool.

    Requires badread to be installed and available in PATH.
    """

    @classmethod
    def is_available(cls) -> bool:
        return shutil.which("badread") is not None

    def generate_reads(
        self,
        genome: GenomeInput,
        output_dir: Path,
        file_index: int,
        num_reads: Optional[int] = None,
    ) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = self._output_filename(genome, file_index)
        output_path = output_dir / filename

        actual_reads = num_reads if num_reads is not None else self.config.reads_per_file
        # Calculate total bases needed: badread --quantity accepts total bases
        # or coverage (Nx). Using total bases gives precise read count control.
        total_bases = actual_reads * self.config.mean_read_length

        # badread outputs to stdout
        cmd = [
            "badread",
            "simulate",
            "--reference",
            str(genome.fasta_path),
            "--quantity",
            str(total_bases),
            "--length",
            f"{self.config.mean_read_length},{self.config.std_read_length}",
        ]

        logger.info(f"Running badread: {' '.join(cmd)}")

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        if output_path.suffix == ".gz":
            with gzip.open(output_path, "wt", compresslevel=1) as f:
                f.write(result.stdout)
        else:
            output_path.write_text(result.stdout)

        return output_path

    def generate_reads_in_memory(
        self,
        genome: GenomeInput,
        num_reads: int,
    ) -> List[Tuple[str, str, str, str]]:
        """Parse badread stdout directly into 4-tuples without temp files."""
        actual_reads = num_reads
        total_bases = actual_reads * self.config.mean_read_length

        cmd = [
            "badread",
            "simulate",
            "--reference",
            str(genome.fasta_path),
            "--quantity",
            str(total_bases),
            "--length",
            f"{self.config.mean_read_length},{self.config.std_read_length}",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        reads: List[Tuple[str, str, str, str]] = []
        lines = result.stdout.split("\n")
        i = 0
        while i + 3 < len(lines):
            header = lines[i]
            if not header.startswith("@"):
                i += 1
                continue
            seq = lines[i + 1]
            sep = lines[i + 2]
            qual = lines[i + 3]
            reads.append((header, seq, sep, qual))
            i += 4

        return reads


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
        self,
        genome: GenomeInput,
        output_dir: Path,
        file_index: int,
        num_reads: Optional[int] = None,
    ) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = self._output_filename(genome, file_index)
        output_path = output_dir / filename

        actual_reads = num_reads if num_reads is not None else self.config.reads_per_file
        prefix = output_dir / f"nanosim_temp_{file_index}"

        cmd = [
            self._get_command(),
            "simulate",
            "linear",
            "-r",
            str(genome.fasta_path),
            "-n",
            str(actual_reads),
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
        if _HAS_NUMPY:
            _ns_rng = np.random.default_rng()
        if output_path.suffix == ".gz":
            fh = gzip.open(output_path, "wt", compresslevel=1)
        else:
            fh = open(output_path, "w")
        with fh as f:
            for header, seq in all_seqs:
                if _HAS_NUMPY:
                    qual = _generate_quality_string_numpy(
                        _ns_rng,
                        self.config.mean_quality,
                        self.config.std_quality,
                        len(seq),
                    )
                else:
                    qual = "".join(
                        chr(
                            int(
                                max(
                                    0,
                                    min(
                                        40,
                                        random.gauss(
                                            self.config.mean_quality,
                                            self.config.std_quality,
                                        ),
                                    ),
                                )
                            )
                            + 33
                        )
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


def create_read_generator(backend: str, config: ReadGeneratorConfig) -> ReadGenerator:
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
