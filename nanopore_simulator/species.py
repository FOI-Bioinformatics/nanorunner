"""Species resolution and genome caching for sample generation.

Provides data structures for referencing and caching genome sequences
from taxonomic databases. Species names can be resolved via the GTDB
REST API (bacteria/archaea) or the NCBI datasets CLI (all domains).

The public resolution interface is exposed as module-level functions:

- ``resolve_species(name, ...)`` -- resolve a species name to a GenomeRef.
- ``resolve_taxid(taxid, ...)`` -- resolve by NCBI taxonomy ID.
- ``download_genome(ref, ...)`` -- download and cache a genome file.

Internal helpers (``_gtdb_lookup``, ``_ncbi_lookup``, ``_ncbi_download``)
handle the network calls and subprocess invocations.
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
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Valid values for source and domain fields.
VALID_SOURCES = {"gtdb", "ncbi"}
VALID_DOMAINS = {"bacteria", "archaea", "eukaryota"}


# -------------------------------------------------------------------
# Data classes
# -------------------------------------------------------------------


@dataclass
class GenomeRef:
    """Reference to a genome for download and caching.

    Attributes:
        name: Species or strain name (e.g. "Escherichia coli").
        accession: Database accession number (e.g. "GCF_000005845.2").
        source: Database source -- "gtdb" or "ncbi".
        domain: Taxonomic domain -- "bacteria", "archaea", or "eukaryota".
    """

    name: str
    accession: str
    source: str
    domain: str

    def __post_init__(self) -> None:
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

    Attributes:
        cache_dir: Path to the genome cache directory.
    """

    def __init__(self, cache_dir: Optional[Path] = None) -> None:
        if cache_dir is None:
            home = Path(os.environ.get("HOME", str(Path.home())))
            self.cache_dir = home / ".nanorunner" / "genomes"
        else:
            self.cache_dir = cache_dir

    def get_cached_path(self, ref: GenomeRef) -> Path:
        """Get the path where a genome would be cached."""
        return self.cache_dir / ref.source / f"{ref.accession}.fna.gz"

    def is_cached(self, ref: GenomeRef) -> bool:
        """Check if a genome is already cached."""
        return self.get_cached_path(ref).exists()


class ResolutionCache:
    """Cache for species name to GenomeRef resolution results.

    Stores resolved genome references in a JSON file to avoid repeated
    network lookups. Keys are lowercased species names; values are
    serialized GenomeRef dictionaries.

    Attributes:
        cache_path: Path to the JSON cache file.
    """

    def __init__(self, cache_dir: Optional[Path] = None) -> None:
        if cache_dir is None:
            home = Path(os.environ.get("HOME", str(Path.home())))
            cache_dir = home / ".nanorunner" / "cache"
        self.cache_path = cache_dir / "resolution_cache.json"
        self._data: Dict[str, Dict[str, str]] = {}
        self._load()

    def _load(self) -> None:
        if self.cache_path.exists():
            try:
                with open(self.cache_path) as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, OSError):
                logger.debug("Could not load resolution cache; starting fresh.")
                self._data = {}

    def _save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_path, "w") as f:
            json.dump(self._data, f, indent=2)

    def get(self, key: str) -> Optional[GenomeRef]:
        """Look up a cached resolution by species name (case-insensitive)."""
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
        """Cache a resolution result."""
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


# -------------------------------------------------------------------
# Internal GTDB helpers
# -------------------------------------------------------------------

_GTDB_BASE_URL = "https://gtdb-api.ecogenomic.org"
_GTDB_TIMEOUT = 30
_GTDB_MAX_RETRIES = 2
_GTDB_RETRY_BACKOFF = 1.0


def _gtdb_request(path: str) -> Optional[Any]:
    """Send a GET request to the GTDB API with retry logic."""
    url = f"{_GTDB_BASE_URL}{path}"
    for attempt in range(_GTDB_MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url)
            req.add_header("Accept", "application/json")
            with urllib.request.urlopen(req, timeout=_GTDB_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 422):
                return None
            if attempt < _GTDB_MAX_RETRIES:
                logger.debug(
                    "GTDB API request failed (HTTP %d), retrying...", exc.code
                )
                time.sleep(_GTDB_RETRY_BACKOFF)
            else:
                logger.debug("GTDB API request failed after retries: %s", exc)
                return None
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            if attempt < _GTDB_MAX_RETRIES:
                logger.debug("GTDB API request error, retrying: %s", exc)
                time.sleep(_GTDB_RETRY_BACKOFF)
            else:
                logger.debug("GTDB API request failed after retries: %s", exc)
                return None
    return None


def _gtdb_lookup(species_name: str) -> Optional[GenomeRef]:
    """Resolve a species name via the GTDB REST API.

    Queries the public API for representative genome accessions
    (bacteria/archaea). Returns None when the species is not found.
    """
    formatted = species_name.replace(" ", "%20")

    genomes = _gtdb_request(
        f"/taxon/s__{formatted}/genomes?sp_reps_only=true"
    )
    if not genomes or not isinstance(genomes, list) or len(genomes) == 0:
        return None

    first = genomes[0]
    accession = None
    if isinstance(first, dict):
        accession = first.get("accession") or first.get("gid")
    elif isinstance(first, str):
        accession = first
    if not accession:
        return None

    # Get domain from taxonomy card
    domain = "bacteria"
    card = _gtdb_request(f"/taxon/s__{formatted}/card")
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


# -------------------------------------------------------------------
# Internal NCBI helpers
# -------------------------------------------------------------------

# Assembly level ranking (lower is better).
_ASSEMBLY_RANK = {
    "Complete Genome": 0,
    "Chromosome": 1,
    "Scaffold": 2,
    "Contig": 3,
}


def _pick_best_assembly(lines: List[str]) -> Optional[Dict[str, Any]]:
    """Select the highest-ranked assembly from JSON lines output."""
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
        level = d.get("assembly_info", {}).get("assembly_level", "Contig")
        return _ASSEMBLY_RANK.get(level, 99)

    candidates.sort(key=rank_key)
    return candidates[0]


def _detect_domain(data: Dict[str, Any]) -> str:
    """Detect taxonomic domain from NCBI datasets JSON response.

    Known NCBI taxonomy IDs: Bacteria (2), Archaea (2157),
    Eukaryota (2759). Falls back to name heuristics, then defaults
    to "bacteria".
    """
    organism = data.get("organism", {})

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

    # Heuristic: check organism name against known eukaryotic genera
    org_name = organism.get("organism_name", "").lower()
    eukaryote_markers = [
        "saccharomyces", "candida", "aspergillus", "cryptococcus",
        "fusarium", "penicillium", "neurospora", "schizosaccharomyces",
    ]
    for marker in eukaryote_markers:
        if marker in org_name:
            return "eukaryota"

    return "bacteria"


def _ncbi_lookup(
    *, name: Optional[str] = None, taxid: Optional[int] = None
) -> Optional[GenomeRef]:
    """Resolve a genome reference via NCBI datasets CLI.

    Exactly one of *name* or *taxid* must be provided.
    """
    if shutil.which("datasets") is None:
        return None

    identifier = name if name is not None else str(taxid)
    try:
        result = subprocess.run(
            [
                "datasets", "summary", "genome", "taxon",
                identifier,
                "--assembly-source", "refseq",
                "--as-json-lines",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None

        lines = result.stdout.strip().split("\n")
        data = _pick_best_assembly(lines)
        if data is None:
            return None

        fallback_name = name if name is not None else f"taxid:{taxid}"
        organism_name = data.get("organism", {}).get(
            "organism_name", fallback_name
        )
        domain = _detect_domain(data)

        return GenomeRef(
            name=organism_name,
            accession=data["accession"],
            source="ncbi",
            domain=domain,
        )
    except (subprocess.TimeoutExpired, KeyError, IndexError):
        return None


def _ncbi_download(ref: GenomeRef, cache: GenomeCache) -> Path:
    """Download a genome via NCBI datasets CLI and cache it.

    Raises:
        RuntimeError: If the download fails or no .fna file is found.
    """
    cached_path = cache.get_cached_path(ref)
    logger.info("Downloading genome: %s", ref.accession)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        zip_path = tmpdir_path / "ncbi_dataset.zip"

        result = subprocess.run(
            [
                "datasets", "download", "genome", "accession",
                ref.accession,
                "--include", "genome",
                "--filename", str(zip_path),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to download genome {ref.accession}: {result.stderr}"
            )

        extract_dir = tmpdir_path / "extract"
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)

        fna_files = list(extract_dir.rglob("*.fna"))
        if not fna_files:
            raise RuntimeError(f"No .fna file found for {ref.accession}")

        cached_path.parent.mkdir(parents=True, exist_ok=True)
        with open(fna_files[0], "rb") as f_in:
            with gzip_module.open(cached_path, "wb") as f_out:
                f_out.write(f_in.read())

    logger.info("Cached genome: %s", cached_path)
    return cached_path


# -------------------------------------------------------------------
# Public resolution functions
# -------------------------------------------------------------------


def resolve_species(
    name: str,
    *,
    domain: Optional[str] = None,
    offline: bool = False,
    cache: Optional[GenomeCache] = None,
    resolution_cache_dir: Optional[Path] = None,
) -> Optional[GenomeRef]:
    """Resolve a species name to a GenomeRef.

    Resolution order:
    1. Resolution cache (instant, any previous source).
    2. GTDB REST API (bacteria/archaea; skipped if offline or
       domain is "eukaryota").
    3. NCBI datasets CLI (all domains; skipped if offline).

    Args:
        name: Species name (e.g. "Escherichia coli").
        domain: Optional domain hint ("bacteria", "archaea", "eukaryota").
            When "eukaryota", GTDB lookup is skipped.
        offline: If True, skip network lookups and rely only on the
            resolution cache.
        cache: Genome cache instance. If None, uses default location.
        resolution_cache_dir: Directory for the resolution cache file.
            If None, uses default (~/.nanorunner/cache/).

    Returns:
        GenomeRef if found, None otherwise.
    """
    res_cache = ResolutionCache(cache_dir=resolution_cache_dir)

    # 1. Check resolution cache
    cached = res_cache.get(name)
    if cached is not None:
        return cached

    if offline:
        return None

    # 2. Try GTDB API (skip for eukaryotes)
    if domain != "eukaryota":
        ref = _gtdb_lookup(name)
        if ref is not None:
            res_cache.put(name, ref)
            return ref

    # 3. Fall back to NCBI
    ref = _ncbi_lookup(name=name)
    if ref is not None:
        res_cache.put(name, ref)
        return ref

    return None


def resolve_taxid(
    taxid: int,
    *,
    offline: bool = False,
    cache: Optional[GenomeCache] = None,
    resolution_cache_dir: Optional[Path] = None,
) -> Optional[GenomeRef]:
    """Resolve a genome reference by NCBI taxonomy ID.

    Args:
        taxid: NCBI taxonomy ID (e.g. 562 for E. coli).
        offline: If True, return None (no network calls).
        cache: Genome cache instance (unused here; for API consistency).
        resolution_cache_dir: Directory for the resolution cache file.

    Returns:
        GenomeRef if found, None otherwise.
    """
    if offline:
        return None

    res_cache = ResolutionCache(cache_dir=resolution_cache_dir)
    ref = _ncbi_lookup(taxid=taxid)
    if ref is not None:
        res_cache.put(f"taxid:{taxid}", ref)
    return ref


def download_genome(
    ref: GenomeRef,
    *,
    cache: Optional[GenomeCache] = None,
    offline: bool = False,
) -> Path:
    """Download a genome and cache it.

    Uses the NCBI datasets CLI to download the genome sequence.
    Returns the path to the cached gzip-compressed genome file.

    Args:
        ref: Genome reference specifying the accession.
        cache: Genome cache instance. If None, uses default location.
        offline: If True, raise an error when the genome is not cached.

    Raises:
        RuntimeError: If the download fails, no .fna file is found,
            offline mode is enabled and the genome is not cached, or
            the datasets CLI is not installed.
    """
    if cache is None:
        cache = GenomeCache()

    cached_path = cache.get_cached_path(ref)
    if cached_path.exists():
        logger.info("Using cached genome: %s", cached_path)
        return cached_path

    if offline:
        raise RuntimeError(
            f"Genome {ref.accession} ({ref.name}) is not cached and "
            "offline mode is enabled. Run 'nanorunner download' first "
            "to cache the required genomes."
        )

    if shutil.which("datasets") is None:
        from nanopore_simulator.deps import get_install_hint

        raise RuntimeError(
            f"Cannot download genome {ref.accession}: "
            "the 'datasets' CLI (ncbi-datasets-cli) is not installed. "
            f"Install with: {get_install_hint('datasets')}"
        )

    return _ncbi_download(ref, cache)
