"""Main simulator class for nanopore sequencing run simulation"""

import logging
import math
import random
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import List, Dict, Union, Optional, Any

from .config import SimulationConfig
from .detector import FileStructureDetector
from .fastq import count_fastq_reads, iter_fastq_reads, write_fastq_reads
from .generators import (
    ReadGeneratorConfig,
    GenomeInput,
    ReadGenerator,
    BuiltinGenerator,
    create_read_generator,
    parse_fasta,
    _init_worker_genomes,
)
from .timing import create_timing_model, TimingModel
from .monitoring import ProgressMonitor, create_progress_monitor
from .species import SpeciesResolver, download_genome, GenomeRef
from .mocks import get_mock_community


_FASTQ_EXTENSIONS = {".fastq", ".fq", ".fastq.gz", ".fq.gz"}


def _generate_file_worker(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """Module-level worker for ProcessPoolExecutor generate tasks.

    Accepts a serializable dict of parameters, creates a local generator,
    and writes one output file. Returns a dict with output_path and
    duration.

    If the worker process was started with ``_init_worker_genomes``,
    pre-parsed genome sequences are injected into the generator's cache
    so that redundant FASTA parsing is avoided.
    """
    from .generators import (
        ReadGeneratorConfig,
        GenomeInput,
        BuiltinGenerator,
        create_read_generator,
        _WORKER_GENOME_CACHE,
    )
    from .fastq import write_fastq_reads

    gen_config = ReadGeneratorConfig(**kwargs["gen_config"])
    generator = create_read_generator(kwargs["backend"], gen_config)

    # Pre-populate the BuiltinGenerator genome cache from the worker-level
    # cache that was set by the pool initializer, avoiding redundant parsing.
    if isinstance(generator, BuiltinGenerator) and _WORKER_GENOME_CACHE:
        generator._genome_cache = {
            Path(k): v for k, v in _WORKER_GENOME_CACHE.items()
        }

    start = time.time()

    if kwargs.get("mixed", False):
        # Mixed-reads: generate from multiple genomes and shuffle
        all_reads: list = []
        for genome_dict, count in kwargs["genome_reads"]:
            genome = GenomeInput(
                fasta_path=Path(genome_dict["fasta_path"]),
                barcode=genome_dict.get("barcode"),
            )
            reads = generator.generate_reads_in_memory(genome, count)
            all_reads.extend(reads)
        random.shuffle(all_reads)

        output_dir = Path(kwargs["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        ext = kwargs["ext"]
        file_index = kwargs["file_index"]
        output_path = output_dir / f"reads_{file_index:04d}{ext}"
        write_fastq_reads(all_reads, output_path)
    else:
        genome = GenomeInput(
            fasta_path=Path(kwargs["fasta_path"]),
            barcode=kwargs.get("barcode"),
        )
        output_dir = Path(kwargs["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = generator.generate_reads(
            genome, output_dir, kwargs["file_index"],
            num_reads=kwargs.get("num_reads"),
        )

    duration = time.time() - start
    return {"output_path": str(output_path), "duration": duration}


def _is_fastq_file(path: Path) -> bool:
    """Check whether *path* has a FASTQ extension."""
    name = path.name.lower()
    return any(name.endswith(ext) for ext in _FASTQ_EXTENSIONS)


def _get_fastq_extension(path: Path) -> str:
    """Return the canonical FASTQ extension for *path* (.fastq.gz or .fastq)."""
    if path.name.lower().endswith(".gz"):
        return ".fastq.gz"
    return ".fastq"


def _fastq_stem(path: Path) -> str:
    """Return the filename stem with FASTQ extensions removed.

    Handles double extensions such as ``.fastq.gz``.
    """
    name = path.name
    for ext in (".fastq.gz", ".fq.gz", ".fastq", ".fq"):
        if name.lower().endswith(ext):
            return name[: len(name) - len(ext)]
    return path.stem


def _distribute_reads(total_reads: int, abundances: List[float]) -> List[int]:
    """Distribute total reads across organisms proportional to abundances.

    Uses the largest-remainder method to ensure the sum of allocated reads
    equals total_reads exactly. Each organism with abundance > 0 receives
    at least 1 read.

    Args:
        total_reads: Total number of reads to distribute.
        abundances: List of abundance proportions (should sum to ~1.0).

    Returns:
        List of per-organism read counts summing to total_reads.
    """
    n = len(abundances)
    if n == 0:
        return []
    if n == 1:
        return [total_reads]

    # Floor allocation
    raw = [a * total_reads for a in abundances]
    floors = [int(r) for r in raw]
    remainders = [r - f for r, f in zip(raw, floors)]

    # Guarantee at least 1 read for any organism with abundance > 0
    for i in range(n):
        if abundances[i] > 0 and floors[i] < 1:
            floors[i] = 1

    # Distribute remaining reads by largest fractional part
    allocated = sum(floors)
    deficit = total_reads - allocated
    if deficit > 0:
        # Sort indices by remainder descending, break ties by index
        ranked = sorted(range(n), key=lambda i: (-remainders[i], i))
        for i in range(min(deficit, n)):
            floors[ranked[i]] += 1
    elif deficit < 0:
        # Over-allocated due to minimum-1 guarantees; reduce from
        # the largest allocations that still exceed 1
        surplus = -deficit
        ranked = sorted(range(n), key=lambda i: (-floors[i], i))
        for i in ranked:
            if surplus <= 0:
                break
            if floors[i] > 1:
                reduction = min(floors[i] - 1, surplus)
                floors[i] -= reduction
                surplus -= reduction

    return floors


class NanoporeSimulator:
    """Main simulator class that orchestrates the file operations"""

    def __init__(
        self,
        config: SimulationConfig,
        enable_monitoring: bool = True,
        monitor_type: str = "default",
    ):
        self.config = config
        self.logger = self._setup_logging()

        # Initialize timing model
        timing_config = config.get_timing_model_config()
        self.timing_model = create_timing_model(**timing_config)

        # Initialize executor for parallel processing (if enabled).
        # Generate mode uses ProcessPoolExecutor for CPU-bound work;
        # replay mode uses ThreadPoolExecutor for I/O-bound operations.
        # The generate-mode pool is created after species resolution so
        # that pre-parsed genome data can be passed to the worker
        # initializer.
        self.executor: Optional[Union[ThreadPoolExecutor, ProcessPoolExecutor]] = None
        if config.parallel_processing and config.operation != "generate":
            self.executor = ThreadPoolExecutor(
                max_workers=config.worker_count
            )
            self.logger.info(
                f"Parallel processing enabled with {config.worker_count} "
                f"worker threads"
            )

        # Auto-scale batch_size for parallel generate mode.  Only
        # override the default value (1); an explicit user setting is
        # preserved.
        if (
            config.parallel_processing
            and config.operation == "generate"
            and config.batch_size == 1
        ):
            self.config.batch_size = config.worker_count
            self.logger.info(
                f"Auto-scaled batch_size to {config.worker_count} "
                f"to match worker_count"
            )

        # Initialize progress monitoring
        self.enable_monitoring = enable_monitoring
        self.monitor_type = monitor_type
        self.progress_monitor: Optional[ProgressMonitor] = None

        # Resolve species inputs to genome paths (must happen before read generator)
        self._resolve_species_inputs()

        # Initialize read generator for generate mode
        self.read_generator: Optional[ReadGenerator] = None
        if config.operation == "generate":
            gen_config = ReadGeneratorConfig(
                num_reads=config.read_count,
                mean_read_length=config.mean_read_length,
                std_read_length=config.std_read_length,
                min_read_length=config.min_read_length,
                mean_quality=config.mean_quality,
                std_quality=config.std_quality,
                reads_per_file=config.reads_per_file,
                output_format=config.output_format,
            )
            self.read_generator = create_read_generator(
                config.generator_backend, gen_config
            )
            if isinstance(self.read_generator, BuiltinGenerator):
                self.logger.warning(
                    "Using builtin generator: reads are error-free subsequences "
                    "without realistic error profiles. For reads with sequencing "
                    "errors, install badread (pip install badread)."
                )

        # Create ProcessPoolExecutor for generate mode after species
        # resolution, so workers can be pre-loaded with genome data.
        if config.parallel_processing and config.operation == "generate":
            genome_data: Dict[str, str] = {}
            for genome_path in (config.genome_inputs or []):
                resolved = str(genome_path.resolve())
                seqs = parse_fasta(genome_path)
                genome_data[resolved] = "".join(
                    seq for _, seq in seqs
                ).upper()

            self.executor = ProcessPoolExecutor(
                max_workers=config.worker_count,
                initializer=_init_worker_genomes,
                initargs=(genome_data,),
            )
            self.logger.info(
                f"Parallel processing enabled with {config.worker_count} "
                f"worker processes (generate mode, "
                f"{len(genome_data)} genomes pre-loaded)"
            )

        # Interactive control flags
        self._simulation_paused = False
        self._shutdown_requested = False

    def _setup_logging(self) -> logging.Logger:
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        return logging.getLogger(__name__)

    def _resolve_species_inputs(self) -> None:
        """Resolve species/mock inputs to genome paths.

        This method handles species name resolution, mock community expansion,
        and taxid lookups. It updates the config with resolved genome paths
        and abundance information.

        Raises:
            ValueError: If a species, mock community, or taxid cannot be resolved.
        """
        if not (
            self.config.species_inputs
            or self.config.mock_name
            or self.config.taxid_inputs
        ):
            return

        resolver = SpeciesResolver(offline=self.config.offline_mode)
        resolved_genomes: List[Path] = []
        abundances: List[float] = []

        if self.config.mock_name:
            # Load mock community
            mock = get_mock_community(self.config.mock_name)
            if mock is None:
                raise ValueError(f"Unknown mock community: {self.config.mock_name}")

            for org in mock.organisms:
                if org.accession:
                    # Use pre-defined accession
                    domain = (
                        org.domain
                        if org.domain
                        else ("eukaryota" if org.resolver == "ncbi" else "bacteria")
                    )
                    ref = GenomeRef(
                        name=org.name,
                        accession=org.accession,
                        source=org.resolver,
                        domain=domain,
                    )
                else:
                    ref = resolver.resolve(org.name)

                if ref is None:
                    raise ValueError(f"Could not resolve organism: {org.name}")

                genome_path = download_genome(
                    ref, resolver.cache, offline=self.config.offline_mode
                )
                resolved_genomes.append(genome_path)
                abundances.append(org.abundance)

        else:
            # Resolve species names
            species_list = self.config.species_inputs or []
            for species in species_list:
                ref = resolver.resolve(species)
                if ref is None:
                    suggestions = resolver.suggest(species)
                    msg = f"Could not resolve species: {species}"
                    if suggestions:
                        msg += f". Did you mean: {', '.join(suggestions)}?"
                    raise ValueError(msg)

                genome_path = download_genome(
                    ref, resolver.cache, offline=self.config.offline_mode
                )
                resolved_genomes.append(genome_path)

            # Resolve taxids
            for taxid in self.config.taxid_inputs or []:
                ref = resolver.resolve_taxid(taxid)
                if ref is None:
                    raise ValueError(f"Could not resolve taxid: {taxid}")

                genome_path = download_genome(
                    ref, resolver.cache, offline=self.config.offline_mode
                )
                resolved_genomes.append(genome_path)

            # Set abundances
            if self.config.abundances:
                abundances = list(self.config.abundances)
            else:
                # Equal abundances
                n = len(resolved_genomes)
                abundances = [1.0 / n] * n

        # Update config with resolved genomes
        object.__setattr__(self.config, "genome_inputs", resolved_genomes)
        object.__setattr__(self.config, "_resolved_abundances", abundances)

    def run_simulation(self) -> None:
        """Run the complete simulation"""
        self.logger.info(f"Starting nanopore simulation")

        if self.config.operation == "generate":
            self.logger.info(
                f"Mode: generate reads from {len(self.config.genome_inputs)} genome(s)"
            )
        else:
            self.logger.info(f"Source: {self.config.source_dir}")
        self.logger.info(f"Target: {self.config.target_dir}")

        # Prepare target directory
        self._prepare_target_directory()

        if self.config.operation == "generate":
            if self.config.force_structure:
                structure = self.config.force_structure
            elif self.config.mix_reads:
                structure = "singleplex"
            else:
                structure = "multiplex"
            file_manifest = self._create_generate_manifest(structure)
        else:
            # Detect or use forced structure
            if self.config.force_structure:
                structure = self.config.force_structure
                self.logger.info(f"Using forced structure: {structure}")
            else:
                structure = FileStructureDetector.detect_structure(
                    self.config.source_dir
                )
                self.logger.info(f"Detected structure: {structure}")

            # Rechunk path: pre-count reads and stream output chunks
            if self.config.reads_per_output_file is not None:
                rechunk_plan = self._create_rechunk_plan(structure)
                total_output = (
                    rechunk_plan["total_output_files"]
                    + rechunk_plan["total_pod5_files"]
                )
                self.logger.info(
                    f"Rechunking into files of "
                    f"{self.config.reads_per_output_file} reads each "
                    f"({total_output} output files)"
                )
                self._init_monitoring(total_output)
                try:
                    self._execute_rechunk_simulation(rechunk_plan)
                    self.logger.info("Simulation completed")
                finally:
                    if self.progress_monitor:
                        self.progress_monitor.stop()
                    self._cleanup()
                return

            # Get file manifest
            if structure == "singleplex":
                file_manifest = self._create_singleplex_manifest()
            else:
                file_manifest = self._create_multiplex_manifest()

        self.logger.info(f"Found {len(file_manifest)} files to simulate")

        self._init_monitoring(len(file_manifest))

        # Execute simulation
        try:
            self._execute_simulation(file_manifest, structure)
            self.logger.info("Simulation completed")
        finally:
            # Stop monitoring and clean up resources
            if self.progress_monitor:
                self.progress_monitor.stop()
            self._cleanup()

    def _cleanup(self) -> None:
        """Clean up resources used by the simulator"""
        if self.executor is not None:
            self.logger.info("Shutting down executor pool")
            self.executor.shutdown(wait=True)
            self.executor = None

    def _init_monitoring(self, total_files: int) -> None:
        """Initialize progress monitoring for *total_files* output items."""
        if not self.enable_monitoring:
            return
        if self.monitor_type == "detailed" or self.config.parallel_processing:
            monitor_kwargs = {
                "enable_resources": True,
                "enable_checkpoint": True,
                "update_interval": 0.5 if self.config.parallel_processing else 1.0,
            }
        else:
            monitor_kwargs = {}

        self.progress_monitor = create_progress_monitor(
            total_files, monitor_type=self.monitor_type, **monitor_kwargs
        )
        total_batches = (
            total_files + self.config.batch_size - 1
        ) // self.config.batch_size
        self.progress_monitor.set_batch_count(total_batches)
        self.progress_monitor.start()
        self.logger.info(
            f"Enhanced monitoring initialized: {self.monitor_type} mode"
        )

    def _prepare_target_directory(self) -> None:
        """Prepare the target directory for simulation"""
        self.config.target_dir.mkdir(parents=True, exist_ok=True)
        self.logger.info(f"Target directory prepared: {self.config.target_dir}")

    def _create_singleplex_manifest(self) -> List[Dict[str, Any]]:
        """Create file manifest for singleplex simulation"""
        files = FileStructureDetector._find_sequencing_files(self.config.source_dir)

        manifest = []
        for file_path in files:
            manifest.append(
                {
                    "source": file_path,
                    "target": self.config.target_dir / file_path.name,
                    "barcode": None,
                }
            )

        return manifest

    def _create_multiplex_manifest(self) -> List[Dict[str, Any]]:
        """Create file manifest for multiplex simulation"""
        barcode_dirs = FileStructureDetector._find_barcode_directories(
            self.config.source_dir
        )

        manifest = []
        for barcode_dir in barcode_dirs:
            barcode_name = barcode_dir.name
            files = FileStructureDetector._find_sequencing_files(barcode_dir)

            for file_path in files:
                target_barcode_dir = self.config.target_dir / barcode_name
                manifest.append(
                    {
                        "source": file_path,
                        "target": target_barcode_dir / file_path.name,
                        "barcode": barcode_name,
                    }
                )

        return manifest

    def _create_generate_manifest(self, structure: str) -> List[Dict[str, Any]]:
        """Create file manifest for read generation mode.

        The --read-count parameter specifies the total number of reads across
        all genomes. When abundances are available (e.g. from mock communities),
        reads are distributed proportionally. Otherwise, reads are split
        equally among genomes.

        Args:
            structure: "multiplex" assigns each genome to a barcode directory,
                       "singleplex" places files in the target root.
        """
        import math

        manifest = []
        genome_inputs = self.config.genome_inputs
        total_reads = self.config.read_count
        n_genomes = len(genome_inputs)

        # Determine per-genome read counts from abundances
        # _resolved_abundances is set by _resolve_species_inputs(); fall back
        # to config.abundances for callers that resolve genomes externally
        # (e.g. the download command).
        abundances = getattr(self.config, "_resolved_abundances", None)
        if not abundances:
            abundances = self.config.abundances
        if abundances and len(abundances) == n_genomes:
            per_genome_reads = _distribute_reads(total_reads, abundances)
        else:
            # Equal split of total reads
            base = total_reads // n_genomes
            remainder = total_reads % n_genomes
            per_genome_reads = [base] * n_genomes
            for i in range(remainder):
                per_genome_reads[i] += 1

        # Log the distribution
        for idx, (gp, rc) in enumerate(zip(genome_inputs, per_genome_reads)):
            self.logger.info(f"Genome {idx + 1} ({Path(gp).name}): {rc} reads")

        rpf = self.config.reads_per_file

        if structure == "multiplex":
            for idx, genome_path in enumerate(genome_inputs):
                barcode = f"barcode{idx + 1:02d}"
                barcode_dir = self.config.target_dir / barcode
                genome = GenomeInput(fasta_path=genome_path, barcode=barcode)
                n_files = max(1, math.ceil(per_genome_reads[idx] / rpf))
                remaining = per_genome_reads[idx]
                for fi in range(n_files):
                    chunk = min(rpf, remaining)
                    remaining -= chunk
                    manifest.append(
                        {
                            "genome": genome,
                            "target": barcode_dir,
                            "file_index": fi,
                            "barcode": barcode,
                            "num_reads": chunk,
                        }
                    )
        elif self.config.mix_reads:
            # Singleplex mixed: each file contains reads from ALL genomes,
            # distributed proportionally according to abundances.
            total_files = max(1, math.ceil(total_reads / rpf))
            genomes = [GenomeInput(fasta_path=gp) for gp in genome_inputs]
            weights = abundances if abundances else [1.0 / n_genomes] * n_genomes
            remaining = total_reads
            for fi in range(total_files):
                chunk = min(rpf, remaining)
                remaining -= chunk
                # Distribute this file's reads across genomes by abundance
                per_genome = _distribute_reads(chunk, weights)
                genome_reads = [
                    (g, n) for g, n in zip(genomes, per_genome) if n > 0
                ]
                manifest.append(
                    {
                        "mixed": True,
                        "genome_reads": genome_reads,
                        "target": self.config.target_dir,
                        "file_index": fi,
                        "barcode": None,
                        "num_reads": chunk,
                    }
                )
        else:
            # Singleplex separate: each genome gets abundance-weighted file counts
            for idx, genome_path in enumerate(genome_inputs):
                genome = GenomeInput(fasta_path=genome_path)
                n_files = max(1, math.ceil(per_genome_reads[idx] / rpf))
                remaining = per_genome_reads[idx]
                for fi in range(n_files):
                    chunk = min(rpf, remaining)
                    remaining -= chunk
                    manifest.append(
                        {
                            "genome": genome,
                            "target": self.config.target_dir,
                            "file_index": fi,
                            "barcode": None,
                            "num_reads": chunk,
                        }
                    )

        return manifest

    # ------------------------------------------------------------------
    # Rechunk helpers
    # ------------------------------------------------------------------

    def _create_rechunk_plan(self, structure: str) -> Dict[str, Any]:
        """Pre-count reads in source FASTQ files and build a rechunk plan.

        Returns a dict with keys ``groups``, ``total_output_files``, and
        ``total_pod5_files``.  Each group contains the barcode label, the
        target directory, lists of FASTQ files with read counts, and any
        POD5 files to copy as-is.
        """
        rpf = self.config.reads_per_output_file

        # Build normal manifest to identify files and barcodes
        if structure == "singleplex":
            raw_manifest = self._create_singleplex_manifest()
        else:
            raw_manifest = self._create_multiplex_manifest()

        # Group entries by barcode
        barcode_order: List[Optional[str]] = []
        barcode_groups: Dict[Optional[str], Dict[str, Any]] = {}
        for entry in raw_manifest:
            bc = entry["barcode"]
            if bc not in barcode_groups:
                barcode_order.append(bc)
                target_dir = (
                    entry["target"].parent
                    if entry["target"].parent != self.config.target_dir
                    else self.config.target_dir
                )
                barcode_groups[bc] = {
                    "barcode": bc,
                    "target_dir": target_dir,
                    "fastq_files": [],
                    "pod5_files": [],
                }
            source = entry["source"]
            if _is_fastq_file(source):
                count = count_fastq_reads(source)
                barcode_groups[bc]["fastq_files"].append((source, count))
            else:
                barcode_groups[bc]["pod5_files"].append(source)

        # Calculate output counts
        total_output = 0
        total_pod5 = 0
        for bc in barcode_order:
            grp = barcode_groups[bc]
            total_reads = sum(c for _, c in grp["fastq_files"])
            if total_reads > 0:
                total_output += math.ceil(total_reads / rpf)
            total_pod5 += len(grp["pod5_files"])

        groups = [barcode_groups[bc] for bc in barcode_order]
        return {
            "groups": groups,
            "total_output_files": total_output,
            "total_pod5_files": total_pod5,
        }

    def _execute_rechunk_simulation(self, rechunk_plan: Dict[str, Any]) -> None:
        """Stream reads from source files and write rechunked output files.

        For each barcode group, FASTQ files are streamed in order.  Reads
        accumulate across source-file boundaries until the buffer reaches
        ``reads_per_output_file``.  Only the final chunk for a barcode
        group may contain fewer reads.

        POD5 files are copied as-is using the existing copy logic.
        """
        rpf = self.config.reads_per_output_file
        files_processed = 0

        for grp in rechunk_plan["groups"]:
            barcode = grp["barcode"]
            target_dir = grp["target_dir"]
            target_dir = Path(target_dir)
            target_dir.mkdir(parents=True, exist_ok=True)

            # --- Copy POD5 files unchanged ---
            for pod5_path in grp["pod5_files"]:
                if self.progress_monitor and self.progress_monitor.should_stop():
                    return
                if self.progress_monitor and self.progress_monitor.is_paused():
                    self.progress_monitor.wait_if_paused()
                    if self.progress_monitor.should_stop():
                        return

                op_start = time.time()
                dest = target_dir / pod5_path.name
                shutil.copy2(pod5_path, dest)
                duration = time.time() - op_start

                if self.progress_monitor:
                    self.progress_monitor.record_file_processed(dest, duration)
                files_processed += 1

                # Timing between POD5 copies
                if files_processed % self.config.batch_size == 0:
                    interval = self._calculate_interval()
                    if self.monitor_type == "enhanced" and self.progress_monitor:
                        self._interruptible_sleep(interval)
                    else:
                        time.sleep(interval)

            # --- Stream FASTQ reads and write rechunked output ---
            if not grp["fastq_files"]:
                continue

            buffer: List[tuple] = []
            chunk_index = 0
            # Track which source file contributed the first read of the chunk
            first_source: Optional[Path] = None

            for source_path, _ in grp["fastq_files"]:
                for read in iter_fastq_reads(source_path):
                    if self.progress_monitor and self.progress_monitor.should_stop():
                        # Flush remaining buffer before stopping
                        if buffer:
                            self._write_rechunk_chunk(
                                buffer, first_source, chunk_index,
                                target_dir, barcode,
                            )
                        return

                    if not buffer:
                        first_source = source_path
                    buffer.append(read)

                    if len(buffer) >= rpf:
                        if self.progress_monitor and self.progress_monitor.is_paused():
                            self.progress_monitor.wait_if_paused()
                            if self.progress_monitor.should_stop():
                                return

                        self._write_rechunk_chunk(
                            buffer, first_source, chunk_index,
                            target_dir, barcode,
                        )
                        buffer = []
                        first_source = None
                        chunk_index += 1
                        files_processed += 1

                        # Timing between output files
                        if files_processed % self.config.batch_size == 0:
                            interval = self._calculate_interval()
                            if self.progress_monitor:
                                self.progress_monitor.add_wait_time(interval)
                            if (
                                self.monitor_type == "enhanced"
                                and self.progress_monitor
                            ):
                                self._interruptible_sleep(interval)
                            else:
                                time.sleep(interval)

            # Write remaining reads for this barcode group
            if buffer:
                self._write_rechunk_chunk(
                    buffer, first_source, chunk_index,
                    target_dir, barcode,
                )
                files_processed += 1

    def _write_rechunk_chunk(
        self,
        reads: List[tuple],
        first_source: Optional[Path],
        chunk_index: int,
        target_dir: Path,
        barcode: Optional[str],
    ) -> None:
        """Write a single rechunked output file and record progress."""
        ext = _get_fastq_extension(first_source) if first_source else ".fastq"
        stem = _fastq_stem(first_source) if first_source else "reads"
        filename = f"{stem}_chunk_{chunk_index:04d}{ext}"
        output_path = target_dir / filename

        op_start = time.time()
        write_fastq_reads(reads, output_path)
        duration = time.time() - op_start

        if self.progress_monitor:
            self.progress_monitor.record_file_processed(output_path, duration)

        if self.monitor_type == "detailed":
            prefix = f"{barcode}/" if barcode else ""
            self.logger.info(
                f"Rechunked: {prefix}{filename} "
                f"({len(reads)} reads, {duration:.3f}s)"
            )

    def _execute_simulation(self, file_manifest: List[Dict], structure: str) -> None:
        """Execute the file simulation with timing and optional parallel processing.

        When parallel generate mode is active and the timing interval is
        non-zero, a prefetch pipeline is used: the current batch is
        submitted to worker processes, then the main thread sleeps for
        the timing interval while workers generate reads concurrently.
        This overlaps CPU-bound generation with timing delays and
        improves throughput.
        """
        total_files = len(file_manifest)
        total_batches = (
            total_files + self.config.batch_size - 1
        ) // self.config.batch_size

        # Decide whether to use the prefetch pipeline: parallel generate
        # mode with a process pool and non-zero interval.
        use_prefetch = (
            self.config.parallel_processing
            and self.config.operation == "generate"
            and isinstance(self.executor, ProcessPoolExecutor)
        )

        if use_prefetch:
            self._execute_prefetch_loop(file_manifest, total_batches)
        else:
            self._execute_standard_loop(file_manifest, total_batches)

    def _execute_standard_loop(
        self, file_manifest: List[Dict], total_batches: int
    ) -> None:
        """Standard batch loop: process -> wait -> next batch."""
        total_files = len(file_manifest)
        for i, batch_start in enumerate(range(0, total_files, self.config.batch_size)):
            # Check for shutdown signal
            if self.progress_monitor and self.progress_monitor.should_stop():
                self.logger.info(
                    "Shutdown signal received, stopping simulation gracefully"
                )
                break

            # Handle pause/resume
            if self.progress_monitor and self.progress_monitor.is_paused():
                self.logger.info("Simulation paused, waiting for resume...")
                self.progress_monitor.wait_if_paused()

                # Check shutdown again after pause
                if self.progress_monitor.should_stop():
                    break

            batch_end = min(batch_start + self.config.batch_size, total_files)
            batch = file_manifest[batch_start:batch_end]
            batch_num = i + 1

            self.logger.info(
                f"Processing batch {batch_num}/{total_batches} ({len(batch)} files)"
            )

            # Process batch (either sequentially or in parallel)
            batch_start_time = (
                self.progress_monitor.start_batch()
                if self.progress_monitor
                else time.time()
            )

            try:
                if self.config.parallel_processing and self.executor is not None:
                    self._process_batch_parallel(batch)
                else:
                    self._process_batch_sequential(batch)
            except (PermissionError, OSError, MemoryError) as e:
                # Critical errors should stop the simulation
                self.logger.error(f"Critical error processing batch {batch_num}: {e}")
                if self.progress_monitor:
                    self.progress_monitor.record_error(
                        f"critical_error: {type(e).__name__}"
                    )
                raise  # Re-raise critical errors
            except Exception as e:
                # Non-critical errors can be logged and simulation continues
                self.logger.error(f"Error processing batch {batch_num}: {e}")
                if self.progress_monitor:
                    self.progress_monitor.record_error(
                        f"batch_processing: {type(e).__name__}"
                    )
                # Continue with next batch for non-critical errors
                continue

            batch_duration = time.time() - batch_start_time
            throughput = len(batch) / batch_duration if batch_duration > 0 else 0

            # Update monitoring
            if self.progress_monitor:
                self.progress_monitor.end_batch(batch_start_time)

            self.logger.info(
                f"Batch {batch_num} completed in {batch_duration:.2f}s "
                f"({throughput:.1f} files/sec)"
            )

            # Wait for next batch (except for last batch)
            if batch_end < total_files:
                actual_interval = self._calculate_interval()
                self.logger.info(
                    f"Waiting {actual_interval:.2f} seconds before next batch..."
                )

                # Record wait time for monitoring
                if self.progress_monitor:
                    self.progress_monitor.add_wait_time(actual_interval)

                # Use interruptible sleep for enhanced monitoring, regular sleep otherwise
                if self.monitor_type == "enhanced" and self.progress_monitor:
                    self._interruptible_sleep(actual_interval)
                else:
                    time.sleep(actual_interval)

    def _execute_prefetch_loop(
        self, file_manifest: List[Dict], total_batches: int
    ) -> None:
        """Prefetch batch loop for parallel generate mode.

        Submits each batch to the process pool, then sleeps for the
        timing interval while workers generate reads concurrently.
        Results are collected after the sleep completes (or immediately
        if workers finish first).  This overlaps generation with timing
        delays so workers stay busy.
        """
        total_files = len(file_manifest)
        pending_futures: Optional[List[tuple]] = None
        pending_batch_start: Optional[float] = None
        pending_batch_len = 0
        pending_batch_num = 0

        for i, batch_start in enumerate(range(0, total_files, self.config.batch_size)):
            # Check for shutdown signal
            if self.progress_monitor and self.progress_monitor.should_stop():
                self.logger.info(
                    "Shutdown signal received, stopping simulation gracefully"
                )
                break

            # Handle pause/resume
            if self.progress_monitor and self.progress_monitor.is_paused():
                self.logger.info("Simulation paused, waiting for resume...")
                self.progress_monitor.wait_if_paused()
                if self.progress_monitor.should_stop():
                    break

            # Collect results from the previously submitted batch (if any)
            if pending_futures is not None:
                try:
                    self._collect_parallel_results(pending_futures)
                except (PermissionError, OSError, MemoryError) as e:
                    self.logger.error(
                        f"Critical error in batch {pending_batch_num}: {e}"
                    )
                    if self.progress_monitor:
                        self.progress_monitor.record_error(
                            f"critical_error: {type(e).__name__}"
                        )
                    raise
                except Exception as e:
                    self.logger.error(f"Error in batch {pending_batch_num}: {e}")
                    if self.progress_monitor:
                        self.progress_monitor.record_error(
                            f"batch_processing: {type(e).__name__}"
                        )

                batch_duration = time.time() - pending_batch_start
                throughput = (
                    pending_batch_len / batch_duration if batch_duration > 0 else 0
                )
                if self.progress_monitor:
                    self.progress_monitor.end_batch(pending_batch_start)
                self.logger.info(
                    f"Batch {pending_batch_num} completed in "
                    f"{batch_duration:.2f}s ({throughput:.1f} files/sec)"
                )

            batch_end = min(batch_start + self.config.batch_size, total_files)
            batch = file_manifest[batch_start:batch_end]
            batch_num = i + 1

            self.logger.info(
                f"Processing batch {batch_num}/{total_batches} ({len(batch)} files)"
            )

            batch_start_time = (
                self.progress_monitor.start_batch()
                if self.progress_monitor
                else time.time()
            )

            # Submit batch to workers (non-blocking)
            pending_futures = self._submit_batch_parallel(batch)
            pending_batch_start = batch_start_time
            pending_batch_len = len(batch)
            pending_batch_num = batch_num

            # Sleep while workers process (overlapped with generation)
            if batch_end < total_files:
                actual_interval = self._calculate_interval()
                self.logger.info(
                    f"Waiting {actual_interval:.2f} seconds before next batch..."
                )
                if self.progress_monitor:
                    self.progress_monitor.add_wait_time(actual_interval)
                if self.monitor_type == "enhanced" and self.progress_monitor:
                    self._interruptible_sleep(actual_interval)
                else:
                    time.sleep(actual_interval)

        # Collect results from the final batch
        if pending_futures is not None:
            try:
                self._collect_parallel_results(pending_futures)
            except (PermissionError, OSError, MemoryError) as e:
                self.logger.error(
                    f"Critical error in batch {pending_batch_num}: {e}"
                )
                if self.progress_monitor:
                    self.progress_monitor.record_error(
                        f"critical_error: {type(e).__name__}"
                    )
                raise
            except Exception as e:
                self.logger.error(f"Error in batch {pending_batch_num}: {e}")
                if self.progress_monitor:
                    self.progress_monitor.record_error(
                        f"batch_processing: {type(e).__name__}"
                    )

            batch_duration = time.time() - pending_batch_start
            throughput = (
                pending_batch_len / batch_duration if batch_duration > 0 else 0
            )
            if self.progress_monitor:
                self.progress_monitor.end_batch(pending_batch_start)
            self.logger.info(
                f"Batch {pending_batch_num} completed in "
                f"{batch_duration:.2f}s ({throughput:.1f} files/sec)"
            )

    def _calculate_interval(self) -> float:
        """Calculate the next interval using the configured timing model"""
        return self.timing_model.next_interval()

    def _interruptible_sleep(self, duration: float) -> None:
        """Sleep for specified duration while checking for interruptions"""
        start_time = time.time()
        sleep_interval = min(0.1, duration)  # Check every 100ms or less

        while time.time() - start_time < duration:
            # Check for shutdown
            if self.progress_monitor and self.progress_monitor.should_stop():
                self.logger.info("Sleep interrupted by shutdown signal")
                break

            # Handle pause
            if self.progress_monitor and self.progress_monitor.is_paused():
                self.logger.info("Sleep interrupted by pause")
                self.progress_monitor.wait_if_paused()
                # Reset start time after resume to account for pause duration
                start_time = time.time()
                continue

            # Sleep for a short interval
            remaining = duration - (time.time() - start_time)
            time.sleep(min(sleep_interval, remaining))

    def pause_simulation(self) -> None:
        """Pause the simulation if monitoring is enabled"""
        if self.progress_monitor:
            self.progress_monitor.pause()
            self._simulation_paused = True
        else:
            self.logger.warning("Cannot pause simulation without monitoring enabled")

    def resume_simulation(self) -> None:
        """Resume the simulation if monitoring is enabled"""
        if self.progress_monitor:
            self.progress_monitor.resume()
            self._simulation_paused = False
        else:
            self.logger.warning("Cannot resume simulation without monitoring enabled")

    def is_paused(self) -> bool:
        """Check if simulation is currently paused"""
        return self._simulation_paused

    def _process_batch_sequential(self, batch: List[Dict]) -> None:
        """Process a batch of files sequentially"""
        for file_info in batch:
            self._process_file(file_info)

    def _submit_batch_parallel(self, batch: List[Dict]) -> List[tuple]:
        """Submit a batch to the executor without waiting for results.

        Returns a list of ``(future, file_info)`` tuples.  Used by the
        prefetch pipeline in generate mode to overlap I/O with timing
        delays.
        """
        if not batch or self.executor is None:
            return []

        use_process_pool = (
            self.config.operation == "generate"
            and isinstance(self.executor, ProcessPoolExecutor)
        )

        futures: List[tuple] = []
        if use_process_pool:
            gen_config_dict = {
                "num_reads": self.read_generator.config.num_reads,
                "mean_read_length": self.read_generator.config.mean_read_length,
                "std_read_length": self.read_generator.config.std_read_length,
                "min_read_length": self.read_generator.config.min_read_length,
                "mean_quality": self.read_generator.config.mean_quality,
                "std_quality": self.read_generator.config.std_quality,
                "reads_per_file": self.read_generator.config.reads_per_file,
                "output_format": self.read_generator.config.output_format,
            }
            for file_info in batch:
                kwargs = {
                    "gen_config": gen_config_dict,
                    "backend": self.config.generator_backend,
                }
                if file_info.get("mixed", False):
                    kwargs["mixed"] = True
                    kwargs["genome_reads"] = [
                        (
                            {
                                "fasta_path": str(g.fasta_path),
                                "barcode": g.barcode,
                            },
                            n,
                        )
                        for g, n in file_info["genome_reads"]
                    ]
                    kwargs["output_dir"] = str(file_info["target"])
                    kwargs["file_index"] = file_info["file_index"]
                    ext = (
                        ".fastq.gz"
                        if self.config.output_format == "fastq.gz"
                        else ".fastq"
                    )
                    kwargs["ext"] = ext
                else:
                    genome = file_info["genome"]
                    kwargs["fasta_path"] = str(genome.fasta_path)
                    kwargs["barcode"] = genome.barcode
                    kwargs["output_dir"] = str(file_info["target"])
                    kwargs["file_index"] = file_info["file_index"]
                    kwargs["num_reads"] = file_info.get("num_reads")

                future = self.executor.submit(_generate_file_worker, kwargs)
                futures.append((future, file_info))
        else:
            for file_info in batch:
                future = self.executor.submit(self._process_file, file_info)
                futures.append((future, file_info))

        return futures

    def _collect_parallel_results(self, futures: List[tuple]) -> None:
        """Wait for submitted futures and record results.

        Raises the first exception encountered, after collecting all
        completed futures for monitoring.
        """
        if not futures:
            return

        use_process_pool = (
            self.config.operation == "generate"
            and isinstance(self.executor, ProcessPoolExecutor)
        )

        future_to_info = {f: fi for f, fi in futures}
        exceptions = []
        for future in as_completed(future_to_info):
            try:
                result = future.result()
                # For process pool results, update monitoring from main process
                if use_process_pool and self.progress_monitor:
                    output_path = Path(result["output_path"])
                    self.progress_monitor.record_file_processed(
                        output_path, result["duration"]
                    )
            except Exception as e:
                exceptions.append(e)
                self.logger.error(f"Error processing file: {e}")

        if exceptions:
            raise exceptions[0]

    def _process_batch_parallel(self, batch: List[Dict]) -> None:
        """Process a batch of files in parallel.

        Uses ProcessPoolExecutor for generate mode (CPU-bound) and
        ThreadPoolExecutor for replay mode (I/O-bound).
        """
        if not batch:
            return

        if self.executor is None:
            self._process_batch_sequential(batch)
            return

        futures = self._submit_batch_parallel(batch)
        self._collect_parallel_results(futures)

    def _process_file(self, file_info: Dict[str, Any]) -> None:
        """Process a single file (copy, link, or generate)"""
        operation_start = time.time()

        try:
            # Check for shutdown before processing
            if self.progress_monitor and self.progress_monitor.should_stop():
                self.logger.info("Skipping file due to shutdown signal")
                return

            if self.config.operation == "generate":
                self._process_generate(file_info, operation_start)
            else:
                self._process_copy_or_link(file_info, operation_start)

        except Exception as e:
            if self.progress_monitor:
                self.progress_monitor.record_error(
                    f"file_operation: {type(e).__name__}"
                )
            self.logger.error(f"Failed to process file: {e}")
            raise

    def _process_generate(
        self, file_info: Dict[str, Any], operation_start: float
    ) -> None:
        """Process a generate operation for a single manifest entry."""
        if file_info.get("mixed", False):
            return self._process_generate_mixed(file_info, operation_start)

        genome = file_info["genome"]
        output_dir = file_info["target"]
        file_index = file_info["file_index"]
        barcode = file_info["barcode"]
        num_reads = file_info.get("num_reads")

        dir_start = time.time()
        output_dir.mkdir(parents=True, exist_ok=True)
        dir_duration = time.time() - dir_start

        if self.progress_monitor:
            self.progress_monitor.record_timing("directory_creation", dir_duration)

        file_op_start = time.time()
        output_path = self.read_generator.generate_reads(
            genome, output_dir, file_index, num_reads=num_reads
        )
        file_op_duration = time.time() - file_op_start
        total_duration = time.time() - operation_start

        if self.progress_monitor:
            self.progress_monitor.record_file_processed(output_path, total_duration)
            self.progress_monitor.record_timing("file_operations", file_op_duration)

        if self.monitor_type == "detailed":
            if barcode:
                self.logger.info(
                    f"Generated: {output_path.name} in {barcode}/ ({total_duration:.3f}s)"
                )
            else:
                self.logger.info(
                    f"Generated: {output_path.name} ({total_duration:.3f}s)"
                )

    def _process_generate_mixed(
        self, file_info: Dict[str, Any], operation_start: float
    ) -> None:
        """Process a mixed-reads generate operation.

        Generates reads from multiple genomes, shuffles them together, and
        writes a single output file with generic naming (``reads_NNNN``).
        """
        genome_reads_spec = file_info["genome_reads"]
        output_dir = Path(file_info["target"])
        file_index = file_info["file_index"]

        dir_start = time.time()
        output_dir.mkdir(parents=True, exist_ok=True)
        dir_duration = time.time() - dir_start

        if self.progress_monitor:
            self.progress_monitor.record_timing("directory_creation", dir_duration)

        file_op_start = time.time()

        # Collect reads from each genome
        all_reads = []
        for genome, count in genome_reads_spec:
            reads = self.read_generator.generate_reads_in_memory(genome, count)
            all_reads.extend(reads)

        # Shuffle to interleave reads from different genomes
        random.shuffle(all_reads)

        # Write output with generic naming
        ext = ".fastq.gz" if self.config.output_format == "fastq.gz" else ".fastq"
        output_path = output_dir / f"reads_{file_index:04d}{ext}"
        write_fastq_reads(all_reads, output_path)

        file_op_duration = time.time() - file_op_start
        total_duration = time.time() - operation_start

        if self.progress_monitor:
            self.progress_monitor.record_file_processed(output_path, total_duration)
            self.progress_monitor.record_timing("file_operations", file_op_duration)

        if self.monitor_type == "detailed":
            self.logger.info(
                f"Generated mixed: {output_path.name} ({total_duration:.3f}s)"
            )

    def _process_copy_or_link(
        self, file_info: Dict[str, Any], operation_start: float
    ) -> None:
        """Process a copy or link operation."""
        source = file_info["source"]
        target = file_info["target"]
        barcode = file_info["barcode"]

        dir_start = time.time()
        target.parent.mkdir(parents=True, exist_ok=True)
        dir_duration = time.time() - dir_start

        if self.progress_monitor:
            self.progress_monitor.record_timing("directory_creation", dir_duration)

        file_op_start = time.time()
        if self.config.operation == "copy":
            shutil.copy2(source, target)
            operation = "Copied"
        elif self.config.operation == "link":
            if target.exists():
                target.unlink()
            target.symlink_to(source.absolute())
            operation = "Linked"
        else:
            raise ValueError(f"Unknown operation: {self.config.operation}")

        file_op_duration = time.time() - file_op_start
        total_duration = time.time() - operation_start

        if self.progress_monitor:
            self.progress_monitor.record_file_processed(target, total_duration)
            self.progress_monitor.record_timing("file_operations", file_op_duration)

        if self.monitor_type == "detailed":
            if barcode:
                self.logger.info(
                    f"{operation}: {source.name} -> {barcode}/{target.name} ({total_duration:.3f}s)"
                )
            else:
                self.logger.info(
                    f"{operation}: {source.name} -> {target.name} ({total_duration:.3f}s)"
                )
