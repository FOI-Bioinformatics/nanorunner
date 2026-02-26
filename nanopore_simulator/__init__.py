"""nanorunner - nanopore sequencing run simulator."""

__version__ = "3.0.0"

from .config import ReplayConfig, GenerateConfig
from .runner import run_replay, run_generate
