"""Species resolution and genome caching for sample generation

This module provides data structures for referencing and caching genome
sequences from taxonomic databases such as GTDB and NCBI. Species names
can be resolved via the GTDB REST API (bacteria/archaea), a local GTDB
TSV index (offline), or the NCBI datasets CLI (all domains).
"""

import gzip as gzip_module
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


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


class ResolutionCache:
    """Cache for species name to GenomeRef resolution results.

    Stores resolved genome references in a JSON file to avoid repeated
    network lookups. Keys are lowercased species names; values are
    serialized GenomeRef dictionaries. Genome accessions are stable
    identifiers, so no time-based expiry is applied.

    Attributes:
        cache_path: Path to the JSON cache file.
    """

    def __init__(self, cache_dir: Optional[Path] = None) -> None:
        """Initialize the resolution cache.

        Args:
            cache_dir: Directory for the cache file. If None, defaults to
                ~/.nanorunner/cache/ using the HOME environment variable.
        """
        if cache_dir is None:
            home = Path(os.environ.get("HOME", Path.home()))
            cache_dir = home / ".nanorunner" / "cache"
        self.cache_path = cache_dir / "resolution_cache.json"
        self._data: Dict[str, Dict[str, str]] = {}
        self._load()

    def _load(self) -> None:
        """Load cached data from disk."""
        if self.cache_path.exists():
            try:
                with open(self.cache_path) as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, OSError):
                logger.debug("Could not load resolution cache; starting fresh.")
                self._data = {}

    def _save(self) -> None:
        """Write cached data to disk."""
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_path, "w") as f:
            json.dump(self._data, f, indent=2)

    def get(self, key: str) -> Optional[GenomeRef]:
        """Look up a cached resolution by species name.

        Args:
            key: Species name (case-insensitive).

        Returns:
            GenomeRef if found in cache, None otherwise.
        """
        entry = self._data.get(key.lower())
        if entry is None:
            return None
        try:
            return GenomeRef(
                name=entry["name"],
                accession=entry["accession"],
                source=entry["source"],
                domain=entry["domain"],
            )
        except (KeyError, ValueError):
            return None

    def put(self, key: str, ref: GenomeRef) -> None:
        """Cache a resolution result.

        Args:
            key: Species name (case-insensitive).
            ref: Resolved genome reference.
        """
        self._data[key.lower()] = {
            "name": ref.name,
            "accession": ref.accession,
            "source": ref.source,
            "domain": ref.domain,
        }
        self._save()

    def clear(self) -> None:
        """Clear all cached resolutions."""
        self._data = {}
        if self.cache_path.exists():
            self.cache_path.unlink()


class GTDBApiResolver:
    """Resolve species names via the GTDB REST API.

    Uses the public API at gtdb-api.ecogenomic.org to look up
    representative genome accessions for bacteria and archaea.
    Requests are retried up to 2 times on transient errors with
    a 1-second backoff between attempts.
    """

    BASE_URL = "https://gtdb-api.ecogenomic.org"
    TIMEOUT = 30
    MAX_RETRIES = 2
    RETRY_BACKOFF = 1.0

    def _request(self, path: str) -> Optional[Any]:
        """Send a GET request to the GTDB API with retry logic.

        Args:
            path: URL path appended to BASE_URL (e.g., "/taxon/...").

        Returns:
            Parsed JSON response, or None on failure.
        """
        url = f"{self.BASE_URL}{path}"
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                req = urllib.request.Request(url)
                req.add_header("Accept", "application/json")
                with urllib.request.urlopen(req, timeout=self.TIMEOUT) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code in (404, 422):
                    return None
                if attempt < self.MAX_RETRIES:
                    logger.debug(
                        "GTDB API request failed (HTTP %d), retrying...",
                        exc.code,
                    )
                    time.sleep(self.RETRY_BACKOFF)
                else:
                    logger.debug("GTDB API request failed after retries: %s", exc)
                    return None
            except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
                if attempt < self.MAX_RETRIES:
                    logger.debug("GTDB API request error, retrying: %s", exc)
                    time.sleep(self.RETRY_BACKOFF)
                else:
                    logger.debug("GTDB API request failed after retries: %s", exc)
                    return None
        return None

    def resolve(self, species_name: str) -> Optional[GenomeRef]:
        """Resolve a species name to its GTDB representative genome.

        Queries two endpoints: one for the representative genome accession
        and one for taxonomic classification (domain).

        Args:
            species_name: Species name (e.g., "Escherichia coli").

        Returns:
            GenomeRef if the species is found in GTDB, None otherwise.
        """
        formatted = species_name.replace(" ", "%20")

        # Get representative genome accession
        genomes = self._request(
            f"/taxon/s__{formatted}/genomes?sp_reps_only=true"
        )
        if not genomes or not isinstance(genomes, list) or len(genomes) == 0:
            return None

        # Extract accession from first representative genome
        first = genomes[0]
        accession = None
        if isinstance(first, dict):
            accession = first.get("accession") or first.get("gid")
        elif isinstance(first, str):
            accession = first
        if not accession:
            return None

        # Get domain from taxonomy card
        domain = "bacteria"  # default for GTDB organisms
        card = self._request(f"/taxon/s__{formatted}/card")
        if card and isinstance(card, dict):
            higher_ranks = card.get("higherRanks", [])
            if isinstance(higher_ranks, list):
                for rank in higher_ranks:
                    rank_str = str(rank)
                    if rank_str.startswith("d__"):
                        domain_name = rank_str[3:].lower()
                        if domain_name in VALID_DOMAINS:
                            domain = domain_name
                        break

        return GenomeRef(
            name=species_name,
            accession=accession,
            source="gtdb",
            domain=domain,
        )

    def suggest(self, partial_name: str, max_results: int = 5) -> List[str]:
        """Suggest species names matching a partial input.

        Uses the GTDB search endpoint and filters for species-level taxa.

        Args:
            partial_name: Partial species name to match.
            max_results: Maximum number of suggestions to return.

        Returns:
            List of matching species names, up to max_results.
        """
        formatted = partial_name.replace(" ", "%20")
        data = self._request(f"/search/gtdb?search={formatted}")
        if not data:
            return []

        rows = data.get("rows", []) if isinstance(data, dict) else []
        seen: set = set()
        results: List[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            taxonomy = row.get("gtdbTaxonomy", "")
            # Extract species name from taxonomy string (s__Species name)
            for part in taxonomy.split(";"):
                part = part.strip()
                if part.startswith("s__") and len(part) > 3:
                    species = part[3:]
                    if species.lower() not in seen:
                        seen.add(species.lower())
                        results.append(species)
                    break
            if len(results) >= max_results:
                break
        return results


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
            logger.debug(
                "GTDB index not found at %s; species resolution will use NCBI.",
                self.index_path,
            )
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

    Assembly selection prefers RefSeq assemblies and ranks candidates by
    assembly level (complete genome > chromosome > scaffold > contig).
    """

    # Assembly level ranking (lower is better)
    _ASSEMBLY_RANK = {
        "Complete Genome": 0,
        "Chromosome": 1,
        "Scaffold": 2,
        "Contig": 3,
    }

    def is_available(self) -> bool:
        """Check if ncbi-datasets-cli is installed.

        Returns:
            True if the 'datasets' command is available, False otherwise.
        """
        return shutil.which("datasets") is not None

    def _pick_best_assembly(self, lines: List[str]) -> Optional[Dict[str, Any]]:
        """Select the best assembly from multiple JSON lines.

        Ranks assemblies by assembly level (complete > chromosome >
        scaffold > contig) and returns the highest-ranked candidate.

        Args:
            lines: JSON lines from datasets CLI output.

        Returns:
            Parsed JSON dict for the best assembly, or None.
        """
        candidates: List[Dict[str, Any]] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if "accession" in data:
                    candidates.append(data)
            except json.JSONDecodeError:
                continue

        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        def rank_key(d: Dict[str, Any]) -> int:
            level = (
                d.get("assembly_info", {}).get("assembly_level", "Contig")
            )
            return self._ASSEMBLY_RANK.get(level, 99)

        candidates.sort(key=rank_key)
        return candidates[0]

    def _detect_domain(self, data: Dict[str, Any]) -> str:
        """Detect taxonomic domain from NCBI datasets JSON response.

        Checks organism taxonomy information for domain-level classification.
        Uses known NCBI taxonomy IDs: Bacteria (2), Archaea (2157),
        Eukaryota (2759).

        Args:
            data: Parsed JSON from NCBI datasets CLI.

        Returns:
            Domain string: "bacteria", "archaea", or "eukaryota".
            Defaults to "bacteria" when domain cannot be determined.
        """
        organism = data.get("organism", {})

        # Check taxonomy lineage if available
        lineage = organism.get("lineage", [])
        if not lineage:
            classification = organism.get("classification", {})
            lineage = classification.get("lineage", [])

        for item in lineage:
            if isinstance(item, dict):
                tax_id = item.get("tax_id", 0)
            elif isinstance(item, (int, float)):
                tax_id = int(item)
            else:
                continue
            if tax_id == 2:
                return "bacteria"
            elif tax_id == 2157:
                return "archaea"
            elif tax_id == 2759:
                return "eukaryota"

        # Heuristic: check organism name against known eukaryotic patterns
        org_name = organism.get("organism_name", "").lower()
        eukaryote_markers = [
            "saccharomyces", "candida", "aspergillus", "cryptococcus",
            "fusarium", "penicillium", "neurospora", "schizosaccharomyces",
        ]
        for marker in eukaryote_markers:
            if marker in org_name:
                return "eukaryota"

        # Default to bacteria (most common use case in metagenomics)
        return "bacteria"

    def resolve_by_taxid(self, taxid: int) -> Optional[GenomeRef]:
        """Resolve a genome reference by NCBI taxonomy ID.

        Queries NCBI for a genome associated with the given taxonomy ID.
        Prefers RefSeq assemblies and selects the best assembly level.

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
                    "datasets",
                    "summary",
                    "genome",
                    "taxon",
                    str(taxid),
                    "--assembly-source",
                    "refseq",
                    "--as-json-lines",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return None

            lines = result.stdout.strip().split("\n")
            data = self._pick_best_assembly(lines)
            if data is None:
                return None

            organism_name = data.get("organism", {}).get(
                "organism_name", f"taxid:{taxid}"
            )
            domain = self._detect_domain(data)
            return GenomeRef(
                name=organism_name,
                accession=data["accession"],
                source="ncbi",
                domain=domain,
            )
        except (subprocess.TimeoutExpired, KeyError, IndexError):
            return None

    def resolve_by_name(self, name: str) -> Optional[GenomeRef]:
        """Resolve a genome reference by organism name.

        Queries NCBI for a genome associated with the given organism name.
        Prefers RefSeq assemblies and selects the best assembly level.

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
                    "datasets",
                    "summary",
                    "genome",
                    "taxon",
                    name,
                    "--assembly-source",
                    "refseq",
                    "--as-json-lines",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return None

            lines = result.stdout.strip().split("\n")
            data = self._pick_best_assembly(lines)
            if data is None:
                return None

            organism_name = data.get("organism", {}).get("organism_name", name)
            domain = self._detect_domain(data)
            return GenomeRef(
                name=organism_name,
                accession=data["accession"],
                source="ncbi",
                domain=domain,
            )
        except (subprocess.TimeoutExpired, KeyError, IndexError):
            return None


class SpeciesResolver:
    """Unified species resolution with multi-source fallback strategy.

    Provides a single interface for resolving species names to genome
    references. Resolution proceeds through several sources in order:
    resolution cache, local GTDB index, GTDB REST API, and NCBI
    datasets CLI.

    Attributes:
        cache: GenomeCache instance for accessing cached genome files.
    """

    def __init__(
        self,
        index_dir: Optional[Path] = None,
        cache_dir: Optional[Path] = None,
        offline: bool = False,
    ) -> None:
        """Initialize the species resolver.

        Args:
            index_dir: Directory containing index files. If None, defaults to
                ~/.nanorunner/indexes/ using the HOME environment variable.
            cache_dir: Directory for genome cache. If None, defaults to
                ~/.nanorunner/genomes/ using the HOME environment variable.
            offline: If True, skip network lookups (GTDB API and NCBI) and
                rely only on the resolution cache, local GTDB index, and
                cached genomes.
        """
        if index_dir is None:
            home = Path(os.environ.get("HOME", Path.home()))
            index_dir = home / ".nanorunner" / "indexes"

        self._gtdb_api = GTDBApiResolver()
        self._gtdb_index = GTDBIndex(index_dir / "gtdb_species.tsv")
        self._ncbi = NCBIResolver()
        self._cache = GenomeCache(cache_dir)
        self._resolution_cache = ResolutionCache()
        self._offline = offline

    def resolve(self, species_name: str) -> Optional[GenomeRef]:
        """Resolve a species name to a genome reference.

        Resolution order:
        1. Resolution cache (instant, any previous source)
        2. GTDB local index (if TSV file exists; offline-capable)
        3. GTDB REST API (bacteria/archaea; skipped if offline)
        4. NCBI datasets CLI (all domains; skipped if offline)

        Args:
            species_name: Species name to resolve (e.g., "Escherichia coli").

        Returns:
            GenomeRef if found, None otherwise.
        """
        # 1. Check resolution cache
        cached = self._resolution_cache.get(species_name)
        if cached is not None:
            return cached

        # 2. Try GTDB local index (fast, offline-capable)
        ref = self._gtdb_index.lookup(species_name)
        if ref is not None:
            self._resolution_cache.put(species_name, ref)
            return ref

        if self._offline:
            return None

        # 3. Try GTDB API (bacteria/archaea)
        ref = self._gtdb_api.resolve(species_name)
        if ref is not None:
            self._resolution_cache.put(species_name, ref)
            return ref

        # 4. Fall back to NCBI (all domains)
        ref = self._ncbi.resolve_by_name(species_name)
        if ref is not None:
            self._resolution_cache.put(species_name, ref)
            return ref

        return None

    def resolve_taxid(self, taxid: int) -> Optional[GenomeRef]:
        """Resolve a genome reference by NCBI taxonomy ID.

        Args:
            taxid: NCBI taxonomy ID (e.g., 4932 for S. cerevisiae).

        Returns:
            GenomeRef if found, None otherwise.
        """
        if self._offline:
            return None
        ref = self._ncbi.resolve_by_taxid(taxid)
        if ref is not None:
            self._resolution_cache.put(f"taxid:{taxid}", ref)
        return ref

    def suggest(self, partial_name: str) -> List[str]:
        """Get species name suggestions.

        Tries the GTDB REST API first (if online), then falls back to
        the local GTDB index.

        Args:
            partial_name: Partial species name to match.

        Returns:
            List of matching species names.
        """
        if not self._offline:
            suggestions = self._gtdb_api.suggest(partial_name)
            if suggestions:
                return suggestions
        return self._gtdb_index.suggest(partial_name)

    @property
    def cache(self) -> GenomeCache:
        """Access the genome cache.

        Returns:
            GenomeCache instance for checking and accessing cached genomes.
        """
        return self._cache


def download_genome(
    ref: GenomeRef, cache: GenomeCache, offline: bool = False
) -> Path:
    """Download a genome and cache it.

    Uses the NCBI datasets CLI to download the genome sequence for the
    given reference. Downloaded genomes are compressed with gzip and
    stored in the cache directory.

    Args:
        ref: Genome reference specifying the accession to download.
        cache: Genome cache instance for storing the downloaded genome.
        offline: If True, raise an error instead of downloading when the
            genome is not already cached.

    Returns:
        Path to the cached genome file (gzip compressed).

    Raises:
        RuntimeError: If the download fails, no .fna file is found,
            offline mode is enabled and the genome is not cached, or
            the datasets CLI is not installed.
    """
    # Check cache first
    cached_path = cache.get_cached_path(ref)
    if cached_path.exists():
        logger.info(f"Using cached genome: {cached_path}")
        return cached_path

    # Offline mode: genome must already be cached
    if offline:
        raise RuntimeError(
            f"Genome {ref.accession} ({ref.name}) is not cached and "
            "offline mode is enabled. Run 'nanorunner download' first "
            "to cache the required genomes."
        )

    # Check that datasets CLI is available before attempting download
    if shutil.which("datasets") is None:
        from .deps import get_install_hint

        raise RuntimeError(
            f"Cannot download genome {ref.accession}: "
            "the 'datasets' CLI (ncbi-datasets-cli) is not installed. "
            f"Install with: {get_install_hint('datasets')}"
        )

    # Download via datasets CLI
    logger.info(f"Downloading genome: {ref.accession}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        zip_path = tmpdir_path / "ncbi_dataset.zip"

        result = subprocess.run(
            [
                "datasets",
                "download",
                "genome",
                "accession",
                ref.accession,
                "--include",
                "genome",
                "--filename",
                str(zip_path),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to download genome {ref.accession}: {result.stderr}"
            )

        # Extract and find the .fna file
        extract_dir = tmpdir_path / "extract"
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)

        fna_files = list(extract_dir.rglob("*.fna"))
        if not fna_files:
            raise RuntimeError(f"No .fna file found for {ref.accession}")

        # Compress and move to cache
        cached_path.parent.mkdir(parents=True, exist_ok=True)
        with open(fna_files[0], "rb") as f_in:
            with gzip_module.open(cached_path, "wb") as f_out:
                f_out.write(f_in.read())

        logger.info(f"Cached genome: {cached_path}")
        return cached_path
