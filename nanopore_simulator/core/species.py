"""Species resolution and genome caching for sample generation

This module provides data structures for referencing and caching genome
sequences from taxonomic databases such as GTDB and NCBI.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# Valid values for source and domain fields
VALID_SOURCES = {"gtdb", "ncbi"}
VALID_DOMAINS = {"bacteria", "archaea", "eukaryota"}


@dataclass
class GenomeRef:
    """Reference to a genome for download and caching.

    Represents a genome reference that can be resolved from taxonomic
    databases. Used for species lookup and mock community generation.

    Attributes:
        name: Species or strain name (e.g., "Escherichia coli").
        accession: Database accession number (e.g., "GCF_000005845.2").
        source: Database source, either "gtdb" or "ncbi".
        domain: Taxonomic domain: "bacteria", "archaea", or "eukaryota".
    """

    name: str
    accession: str
    source: str
    domain: str

    def __post_init__(self) -> None:
        """Validate source and domain values after initialization."""
        if self.source not in VALID_SOURCES:
            raise ValueError(
                f"source must be one of {VALID_SOURCES}, got '{self.source}'"
            )
        if self.domain not in VALID_DOMAINS:
            raise ValueError(
                f"domain must be one of {VALID_DOMAINS}, got '{self.domain}'"
            )


class GenomeCache:
    """Manages cached genome files in ~/.nanorunner/genomes/.

    Provides methods for determining cache paths and checking whether
    genome files have been downloaded and cached locally.

    Attributes:
        cache_dir: Path to the genome cache directory.
    """

    def __init__(self, cache_dir: Optional[Path] = None) -> None:
        """Initialize the genome cache.

        Args:
            cache_dir: Custom cache directory path. If None, defaults to
                ~/.nanorunner/genomes/ using the HOME environment variable.
        """
        if cache_dir is None:
            home = Path(os.environ.get("HOME", Path.home()))
            self.cache_dir = home / ".nanorunner" / "genomes"
        else:
            self.cache_dir = cache_dir

    def get_cached_path(self, ref: GenomeRef) -> Path:
        """Get the path where a genome would be cached.

        Args:
            ref: Genome reference to get the cache path for.

        Returns:
            Path to the cached genome file, organized by source database.
        """
        return self.cache_dir / ref.source / f"{ref.accession}.fna.gz"

    def is_cached(self, ref: GenomeRef) -> bool:
        """Check if a genome is already cached.

        Args:
            ref: Genome reference to check.

        Returns:
            True if the genome file exists in the cache, False otherwise.
        """
        return self.get_cached_path(ref).exists()
