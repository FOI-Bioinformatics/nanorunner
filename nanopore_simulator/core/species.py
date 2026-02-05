"""Species resolution and genome caching for sample generation

This module provides data structures for referencing and caching genome
sequences from taxonomic databases such as GTDB and NCBI.
"""

from dataclasses import dataclass


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
