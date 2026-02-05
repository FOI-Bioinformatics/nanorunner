"""Main simulator class for nanopore sequencing run simulation"""

import logging
import random
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Dict, Union, Optional, Any

from .config import SimulationConfig
from .detector import FileStructureDetector
from .generators import (
    ReadGeneratorConfig,
    GenomeInput,
    ReadGenerator,
    create_read_generator,
)
from .timing import create_timing_model, TimingModel
from .monitoring import ProgressMonitor, create_progress_monitor
from .species import SpeciesResolver, download_genome, GenomeRef
from .mocks import get_mock_community


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

        # Initialize thread pool for parallel processing (if enabled)
        self.executor: Optional[ThreadPoolExecutor] = None
        if config.parallel_processing:
            self.executor = ThreadPoolExecutor(max_workers=config.worker_count)
            self.logger.info(
                f"Parallel processing enabled with {config.worker_count} workers"
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
                reads_per_file=config.reads_per_file,
                output_format=config.output_format,
            )
            self.read_generator = create_read_generator(
                config.generator_backend, gen_config
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

        resolver = SpeciesResolver()
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
                    ref = GenomeRef(
                        name=org.name,
                        accession=org.accession,
                        source=org.resolver,
                        domain="eukaryota" if org.resolver == "ncbi" else "bacteria",
                    )
                else:
                    ref = resolver.resolve(org.name)

                if ref is None:
                    raise ValueError(f"Could not resolve organism: {org.name}")

                genome_path = download_genome(ref, resolver.cache)
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

                genome_path = download_genome(ref, resolver.cache)
                resolved_genomes.append(genome_path)

            # Resolve taxids
            for taxid in self.config.taxid_inputs or []:
                ref = resolver.resolve_taxid(taxid)
                if ref is None:
                    raise ValueError(f"Could not resolve taxid: {taxid}")

                genome_path = download_genome(ref, resolver.cache)
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
            structure = self.config.force_structure or "multiplex"
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

            # Get file manifest
            if structure == "singleplex":
                file_manifest = self._create_singleplex_manifest()
            else:
                file_manifest = self._create_multiplex_manifest()

        self.logger.info(f"Found {len(file_manifest)} files to simulate")

        # Initialize progress monitoring with enhanced features
        if self.enable_monitoring:
            # Use enhanced monitoring for detailed and parallel configurations
            if self.monitor_type == "detailed" or self.config.parallel_processing:
                monitor_kwargs = {
                    "enable_resources": True,
                    "enable_checkpoint": True,
                    "update_interval": 0.5 if self.config.parallel_processing else 1.0,
                }
            else:
                monitor_kwargs = {}

            self.progress_monitor = create_progress_monitor(
                len(file_manifest), monitor_type=self.monitor_type, **monitor_kwargs
            )
            total_batches = (
                len(file_manifest) + self.config.batch_size - 1
            ) // self.config.batch_size
            self.progress_monitor.set_batch_count(total_batches)
            self.progress_monitor.start()

            self.logger.info(
                f"Enhanced monitoring initialized: {self.monitor_type} mode"
            )

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
            self.logger.info("Shutting down thread pool executor")
            self.executor.shutdown(wait=True)
            self.executor = None

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

        Args:
            structure: "multiplex" assigns each genome to a barcode directory,
                       "singleplex" places files in the target root.
        """
        import math

        manifest = []
        genome_inputs = self.config.genome_inputs
        files_per_genome = math.ceil(
            self.config.read_count / self.config.reads_per_file
        )

        if structure == "multiplex":
            for idx, genome_path in enumerate(genome_inputs):
                barcode = f"barcode{idx + 1:02d}"
                barcode_dir = self.config.target_dir / barcode
                genome = GenomeInput(fasta_path=genome_path, barcode=barcode)
                for fi in range(files_per_genome):
                    manifest.append(
                        {
                            "genome": genome,
                            "target": barcode_dir,
                            "file_index": fi,
                            "barcode": barcode,
                        }
                    )
        elif self.config.mix_reads:
            # Singleplex mixed: pool reads from all genomes into shared files
            total_files = files_per_genome * len(genome_inputs)
            genomes = [
                GenomeInput(fasta_path=gp) for gp in genome_inputs
            ]
            for fi in range(total_files):
                genome = genomes[fi % len(genomes)]
                manifest.append(
                    {
                        "genome": genome,
                        "target": self.config.target_dir,
                        "file_index": fi,
                        "barcode": None,
                    }
                )
        else:
            # Singleplex separate: each genome gets named files
            for genome_path in genome_inputs:
                genome = GenomeInput(fasta_path=genome_path)
                for fi in range(files_per_genome):
                    manifest.append(
                        {
                            "genome": genome,
                            "target": self.config.target_dir,
                            "file_index": fi,
                            "barcode": None,
                        }
                    )

        return manifest

    def _execute_simulation(self, file_manifest: List[Dict], structure: str) -> None:
        """Execute the file simulation with timing and optional parallel processing"""
        total_files = len(file_manifest)
        total_batches = (
            total_files + self.config.batch_size - 1
        ) // self.config.batch_size

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

    def _process_batch_parallel(self, batch: List[Dict]) -> None:
        """Process a batch of files in parallel using ThreadPoolExecutor"""
        if not batch:
            return

        # Submit all files in the batch for parallel processing
        if self.executor is None:
            # Fallback to sequential processing if no executor
            self._process_batch_sequential(batch)
            return

        futures = []
        for file_info in batch:
            future = self.executor.submit(self._process_file, file_info)
            futures.append(future)

        # Wait for all files to complete and handle any exceptions
        exceptions = []
        for future in as_completed(futures):
            try:
                future.result()  # This will raise any exception that occurred
            except Exception as e:
                exceptions.append(e)
                self.logger.error(f"Error processing file: {e}")

        # If any exceptions occurred, raise the first one
        if exceptions:
            raise exceptions[0]

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
        genome = file_info["genome"]
        output_dir = file_info["target"]
        file_index = file_info["file_index"]
        barcode = file_info["barcode"]

        dir_start = time.time()
        output_dir.mkdir(parents=True, exist_ok=True)
        dir_duration = time.time() - dir_start

        if self.progress_monitor:
            self.progress_monitor.record_timing("directory_creation", dir_duration)

        file_op_start = time.time()
        output_path = self.read_generator.generate_reads(
            genome, output_dir, file_index
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
