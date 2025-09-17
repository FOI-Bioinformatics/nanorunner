#!/usr/bin/env python3
"""
Nanopore Sequencing Run Simulator

Simulates nanopore sequencing runs by copying/linking FASTQ or POD5 files 
from a source data folder to a target folder structure that nanometanf can watch.

Supports both singleplex (files in one folder) and multiplex (files in barcode folders).
"""

import argparse
import os
import shutil
import time
import re
from pathlib import Path
from typing import List, Dict, Optional, Union
from dataclasses import dataclass
import logging


@dataclass
class SimulationConfig:
    """Configuration for the simulation run"""
    source_dir: Path
    target_dir: Path
    interval: float = 5.0  # seconds between file operations
    operation: str = "copy"  # "copy" or "link"
    file_types: List[str] = None
    force_structure: Optional[str] = None  # "singleplex" or "multiplex"
    batch_size: int = 1  # files to process per interval
    
    def __post_init__(self):
        if self.file_types is None:
            self.file_types = ["fastq", "fq", "fastq.gz", "fq.gz", "pod5"]


class FileStructureDetector:
    """Detects the structure of source data (singleplex vs multiplex)"""
    
    BARCODE_PATTERNS = [
        r"^barcode\d+$",
        r"^BC\d+$", 
        r"^bc\d+$",
        r"^unclassified$"
    ]
    
    SUPPORTED_EXTENSIONS = {
        '.fastq', '.fq', '.fastq.gz', '.fq.gz', '.pod5'
    }
    
    @classmethod
    def detect_structure(cls, source_dir: Path) -> str:
        """
        Detect if source directory contains singleplex or multiplex data
        
        Returns:
            "singleplex": Files directly in source directory
            "multiplex": Files organized in barcode subdirectories
        """
        source_dir = Path(source_dir)
        
        # Check for files directly in source directory
        direct_files = cls._find_sequencing_files(source_dir)
        
        # Check for barcode subdirectories
        barcode_dirs = cls._find_barcode_directories(source_dir)
        
        if barcode_dirs and not direct_files:
            return "multiplex"
        elif direct_files and not barcode_dirs:
            return "singleplex"
        elif barcode_dirs and direct_files:
            logging.warning("Mixed structure detected - files in both root and barcode directories")
            return "multiplex"  # Prefer multiplex interpretation
        else:
            raise ValueError(f"No sequencing files found in {source_dir}")
    
    @classmethod
    def _find_sequencing_files(cls, directory: Path) -> List[Path]:
        """Find sequencing files (FASTQ/POD5) in a directory"""
        files = []
        if not directory.exists():
            return files
            
        for file_path in directory.iterdir():
            if file_path.is_file() and cls._is_sequencing_file(file_path):
                files.append(file_path)
        return files
    
    @classmethod
    def _find_barcode_directories(cls, source_dir: Path) -> List[Path]:
        """Find barcode subdirectories containing sequencing files"""
        barcode_dirs = []
        
        for item in source_dir.iterdir():
            if item.is_dir() and cls._is_barcode_directory(item.name):
                # Check if this directory contains sequencing files
                if cls._find_sequencing_files(item):
                    barcode_dirs.append(item)
        
        return barcode_dirs
    
    @classmethod
    def _is_barcode_directory(cls, dirname: str) -> bool:
        """Check if directory name matches barcode patterns"""
        for pattern in cls.BARCODE_PATTERNS:
            if re.match(pattern, dirname, re.IGNORECASE):
                return True
        return False
    
    @classmethod
    def _is_sequencing_file(cls, file_path: Path) -> bool:
        """Check if file is a supported sequencing file"""
        # Check compound extensions like .fastq.gz
        name_lower = file_path.name.lower()
        for ext in cls.SUPPORTED_EXTENSIONS:
            if name_lower.endswith(ext):
                return True
        return False


class NanoporeSimulator:
    """Main simulator class that orchestrates the file operations"""
    
    def __init__(self, config: SimulationConfig):
        self.config = config
        self.logger = self._setup_logging()
        
    def _setup_logging(self) -> logging.Logger:
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        return logging.getLogger(__name__)
    
    def run_simulation(self):
        """Run the complete simulation"""
        self.logger.info(f"Starting nanopore simulation")
        self.logger.info(f"Source: {self.config.source_dir}")
        self.logger.info(f"Target: {self.config.target_dir}")
        
        # Detect or use forced structure
        if self.config.force_structure:
            structure = self.config.force_structure
            self.logger.info(f"Using forced structure: {structure}")
        else:
            structure = FileStructureDetector.detect_structure(self.config.source_dir)
            self.logger.info(f"Detected structure: {structure}")
        
        # Prepare target directory
        self._prepare_target_directory()
        
        # Get file manifest
        if structure == "singleplex":
            file_manifest = self._create_singleplex_manifest()
        else:
            file_manifest = self._create_multiplex_manifest()
        
        self.logger.info(f"Found {len(file_manifest)} files to simulate")
        
        # Execute simulation
        self._execute_simulation(file_manifest, structure)
        
        self.logger.info("Simulation completed")
    
    def _prepare_target_directory(self):
        """Prepare the target directory for simulation"""
        self.config.target_dir.mkdir(parents=True, exist_ok=True)
        self.logger.info(f"Target directory prepared: {self.config.target_dir}")
    
    def _create_singleplex_manifest(self) -> List[Dict[str, Union[Path, str]]]:
        """Create file manifest for singleplex simulation"""
        files = FileStructureDetector._find_sequencing_files(self.config.source_dir)
        
        manifest = []
        for file_path in files:
            manifest.append({
                'source': file_path,
                'target': self.config.target_dir / file_path.name,
                'barcode': None
            })
        
        return manifest
    
    def _create_multiplex_manifest(self) -> List[Dict[str, Union[Path, str]]]:
        """Create file manifest for multiplex simulation"""
        barcode_dirs = FileStructureDetector._find_barcode_directories(self.config.source_dir)
        
        manifest = []
        for barcode_dir in barcode_dirs:
            barcode_name = barcode_dir.name
            files = FileStructureDetector._find_sequencing_files(barcode_dir)
            
            for file_path in files:
                target_barcode_dir = self.config.target_dir / barcode_name
                manifest.append({
                    'source': file_path,
                    'target': target_barcode_dir / file_path.name,
                    'barcode': barcode_name
                })
        
        return manifest
    
    def _execute_simulation(self, file_manifest: List[Dict], structure: str):
        """Execute the file simulation with timing"""
        total_files = len(file_manifest)
        
        for i, batch_start in enumerate(range(0, total_files, self.config.batch_size)):
            batch_end = min(batch_start + self.config.batch_size, total_files)
            batch = file_manifest[batch_start:batch_end]
            
            self.logger.info(f"Processing batch {i+1} ({len(batch)} files)")
            
            for file_info in batch:
                self._process_file(file_info)
            
            # Wait for next batch (except for last batch)
            if batch_end < total_files:
                self.logger.info(f"Waiting {self.config.interval} seconds before next batch...")
                time.sleep(self.config.interval)
    
    def _process_file(self, file_info: Dict[str, Union[Path, str]]):
        """Process a single file (copy or link)"""
        source = file_info['source']
        target = file_info['target']
        barcode = file_info['barcode']
        
        # Create target directory if needed
        target.parent.mkdir(parents=True, exist_ok=True)
        
        # Perform operation
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
        
        # Log operation
        if barcode:
            self.logger.info(f"{operation}: {source.name} -> {barcode}/{target.name}")
        else:
            self.logger.info(f"{operation}: {source.name} -> {target.name}")


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Simulate nanopore sequencing runs for nanometanf",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Simulate singleplex run with 5-second intervals
  python nanopore_simulator.py /data/singleplex /watch/output --interval 5

  # Simulate multiplex run using symlinks
  python nanopore_simulator.py /data/multiplex /watch/output --operation link

  # Force singleplex structure with larger batches
  python nanopore_simulator.py /data /watch/output --force-structure singleplex --batch-size 5
        """
    )
    
    parser.add_argument("source_dir", type=Path, help="Source directory containing FASTQ/POD5 files")
    parser.add_argument("target_dir", type=Path, help="Target directory for nanometanf to watch")
    parser.add_argument("--interval", type=float, default=5.0, 
                       help="Seconds between file operations (default: 5.0)")
    parser.add_argument("--operation", choices=["copy", "link"], default="copy",
                       help="File operation: copy files or create symlinks (default: copy)")
    parser.add_argument("--force-structure", choices=["singleplex", "multiplex"],
                       help="Force specific structure instead of auto-detection")
    parser.add_argument("--batch-size", type=int, default=1,
                       help="Number of files to process per interval (default: 1)")
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.source_dir.exists():
        parser.error(f"Source directory does not exist: {args.source_dir}")
    
    # Create configuration
    config = SimulationConfig(
        source_dir=args.source_dir,
        target_dir=args.target_dir,
        interval=args.interval,
        operation=args.operation,
        force_structure=args.force_structure,
        batch_size=args.batch_size
    )
    
    # Run simulation
    try:
        simulator = NanoporeSimulator(config)
        simulator.run_simulation()
    except KeyboardInterrupt:
        print("\nSimulation interrupted by user")
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())