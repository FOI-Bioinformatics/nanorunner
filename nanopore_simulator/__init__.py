"""
Nanopore Simulator Package

A Python package for simulating nanopore sequencing runs by copying/linking
FASTQ or POD5 files to create folder structures that nanometanf can watch.
"""

from .core.config import SimulationConfig
from .core.detector import FileStructureDetector
from .core.simulator import NanoporeSimulator

__version__ = "2.0.1"
__author__ = "Andreas Sjodin"
__email__ = "andreas@example.com"

__all__ = [
    "SimulationConfig",
    "FileStructureDetector",
    "NanoporeSimulator",
]
