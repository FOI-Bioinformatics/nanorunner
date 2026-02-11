"""Core modules for nanopore simulator"""

from .config import SimulationConfig
from .detector import FileStructureDetector
from .fastq import count_fastq_reads, iter_fastq_reads, write_fastq_reads
from .generators import (
    ReadGeneratorConfig,
    GenomeInput,
    ReadGenerator,
    BuiltinGenerator,
    BadreadGenerator,
    NanoSimGenerator,
    create_read_generator,
    detect_available_backends,
)
from .simulator import NanoporeSimulator

__all__ = [
    "SimulationConfig",
    "FileStructureDetector",
    "NanoporeSimulator",
    "ReadGeneratorConfig",
    "GenomeInput",
    "ReadGenerator",
    "BuiltinGenerator",
    "BadreadGenerator",
    "NanoSimGenerator",
    "create_read_generator",
    "detect_available_backends",
    "count_fastq_reads",
    "iter_fastq_reads",
    "write_fastq_reads",
]
