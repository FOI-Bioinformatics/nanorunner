"""Species resolution and genome caching for sample generation

This module provides data structures for referencing and caching genome
sequences from taxonomic databases such as GTDB and NCBI.
"""

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


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


class GTDBIndex:
    """Local index for GTDB species-to-accession mapping.

    Provides lookup of genome accessions by species name using a local
    TSV index file. Supports case-insensitive matching and partial name
    suggestions.

    Attributes:
        index_path: Path to the TSV index file.
    """

    def __init__(self, index_path: Path) -> None:
        """Initialize the GTDB index.

        Args:
            index_path: Path to the TSV index file containing species,
                accession, and domain columns.
        """
        self.index_path = index_path
        self._species_map: Dict[str, Tuple[str, str, str]] = {}
        self._load_index()

    def _load_index(self) -> None:
        """Load the TSV index file into memory."""
        if not self.index_path.exists():
            return
        with open(self.index_path) as f:
            # Skip header line
            next(f, None)
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 3:
                    name, accession, domain = parts[0], parts[1], parts[2]
                    self._species_map[name.lower()] = (name, accession, domain)

    def lookup(self, species_name: str) -> Optional[GenomeRef]:
        """Look up a species by name.

        Performs case-insensitive matching against the index.

        Args:
            species_name: Species name to look up.

        Returns:
            GenomeRef if found, None otherwise.
        """
        key = species_name.lower()
        if key in self._species_map:
            name, accession, domain = self._species_map[key]
            return GenomeRef(
                name=name,
                accession=accession,
                source="gtdb",
                domain=domain,
            )
        return None

    def suggest(self, partial_name: str, max_results: int = 5) -> List[str]:
        """Suggest species names matching a partial input.

        Performs case-insensitive substring matching.

        Args:
            partial_name: Partial species name to match.
            max_results: Maximum number of suggestions to return.

        Returns:
            List of matching species names, up to max_results.
        """
        partial = partial_name.lower()
        matches = []
        for key, (name, _, _) in self._species_map.items():
            if partial in key:
                matches.append(name)
                if len(matches) >= max_results:
                    break
        return matches


class NCBIResolver:
    """Resolve species via NCBI taxonomy and datasets CLI.

    Provides methods for resolving genome references by NCBI taxonomy ID
    or organism name using the ncbi-datasets-cli tool. Requires the
    'datasets' command to be available in the system PATH.
    """

    def is_available(self) -> bool:
        """Check if ncbi-datasets-cli is installed.

        Returns:
            True if the 'datasets' command is available, False otherwise.
        """
        return shutil.which("datasets") is not None

    def resolve_by_taxid(self, taxid: int) -> Optional[GenomeRef]:
        """Resolve a genome reference by NCBI taxonomy ID.

        Queries NCBI for a reference genome associated with the given
        taxonomy ID.

        Args:
            taxid: NCBI taxonomy ID (e.g., 4932 for S. cerevisiae).

        Returns:
            GenomeRef if found, None otherwise.
        """
        if not self.is_available():
            return None

        try:
            result = subprocess.run(
                [
                    "datasets", "summary", "genome", "taxon", str(taxid),
                    "--reference", "--as-json-lines",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return None

            data = json.loads(result.stdout)
            return GenomeRef(
                name=data.get("organism_name", f"taxid:{taxid}"),
                accession=data["accession"],
                source="ncbi",
                domain="eukaryota",
            )
        except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError):
            return None

    def resolve_by_name(self, name: str) -> Optional[GenomeRef]:
        """Resolve a genome reference by organism name.

        Queries NCBI for a reference genome associated with the given
        organism name.

        Args:
            name: Organism name (e.g., "Saccharomyces cerevisiae").

        Returns:
            GenomeRef if found, None otherwise.
        """
        if not self.is_available():
            return None

        try:
            result = subprocess.run(
                [
                    "datasets", "summary", "genome", "taxon", name,
                    "--reference", "--as-json-lines",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return None

            data = json.loads(result.stdout)
            return GenomeRef(
                name=data.get("organism_name", name),
                accession=data["accession"],
                source="ncbi",
                domain="eukaryota",
            )
        except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError):
            return None
