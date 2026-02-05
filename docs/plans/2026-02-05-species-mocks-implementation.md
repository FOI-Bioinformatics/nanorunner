# Species Lookup and Mock Community Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable sample generation from species names (resolved via GTDB/NCBI) and preset mock communities with pure/mixed sample support.

**Architecture:** New `species.py` module handles taxonomy resolution and genome caching. New `mocks.py` defines preset communities. CLI extends with `--species`, `--mock`, `--sample-type` flags. SimulationConfig gains new fields for species-based generation.

**Tech Stack:** Python 3.9+, ncbi-datasets-cli (external), requests (optional for API fallback), existing nanorunner infrastructure.

---

## Task 1: GenomeRef and GenomeCache Data Structures

**Files:**
- Create: `nanopore_simulator/core/species.py`
- Test: `tests/test_species.py`

**Step 1: Write failing test for GenomeRef**

```python
# tests/test_species.py
"""Tests for species resolution and genome caching"""

import pytest
from pathlib import Path

from nanopore_simulator.core.species import GenomeRef


class TestGenomeRef:

    def test_create_gtdb_ref(self):
        ref = GenomeRef(
            name="Escherichia coli",
            accession="GCF_000005845.2",
            source="gtdb",
            domain="bacteria",
        )
        assert ref.name == "Escherichia coli"
        assert ref.accession == "GCF_000005845.2"
        assert ref.source == "gtdb"
        assert ref.domain == "bacteria"

    def test_create_ncbi_ref(self):
        ref = GenomeRef(
            name="Saccharomyces cerevisiae",
            accession="GCF_000146045.2",
            source="ncbi",
            domain="eukaryota",
        )
        assert ref.source == "ncbi"
        assert ref.domain == "eukaryota"

    def test_invalid_source(self):
        with pytest.raises(ValueError, match="source"):
            GenomeRef(
                name="Test",
                accession="GCF_000000000.1",
                source="invalid",
                domain="bacteria",
            )

    def test_invalid_domain(self):
        with pytest.raises(ValueError, match="domain"):
            GenomeRef(
                name="Test",
                accession="GCF_000000000.1",
                source="gtdb",
                domain="invalid",
            )
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_species.py::TestGenomeRef -v`
Expected: FAIL with "No module named 'nanopore_simulator.core.species'"

**Step 3: Write minimal implementation**

```python
# nanopore_simulator/core/species.py
"""Species resolution and genome caching for sample generation"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class GenomeRef:
    """Reference to a genome for download/caching"""

    name: str
    accession: str
    source: str  # "gtdb" or "ncbi"
    domain: str  # "bacteria", "archaea", or "eukaryota"

    def __post_init__(self) -> None:
        valid_sources = {"gtdb", "ncbi"}
        if self.source not in valid_sources:
            raise ValueError(f"source must be one of {valid_sources}")
        valid_domains = {"bacteria", "archaea", "eukaryota"}
        if self.domain not in valid_domains:
            raise ValueError(f"domain must be one of {valid_domains}")
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_species.py::TestGenomeRef -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add nanopore_simulator/core/species.py tests/test_species.py
git commit -m "feat(species): add GenomeRef dataclass for genome references"
```

---

## Task 2: GenomeCache Class

**Files:**
- Modify: `nanopore_simulator/core/species.py`
- Test: `tests/test_species.py`

**Step 1: Write failing test for GenomeCache**

```python
# Add to tests/test_species.py
from nanopore_simulator.core.species import GenomeRef, GenomeCache


class TestGenomeCache:

    def test_cache_dir_default(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        cache = GenomeCache()
        assert cache.cache_dir == tmp_path / ".nanorunner" / "genomes"

    def test_cache_dir_custom(self, tmp_path):
        cache = GenomeCache(cache_dir=tmp_path / "custom")
        assert cache.cache_dir == tmp_path / "custom"

    def test_get_cached_path_gtdb(self, tmp_path):
        cache = GenomeCache(cache_dir=tmp_path)
        ref = GenomeRef("E. coli", "GCF_000005845.2", "gtdb", "bacteria")
        expected = tmp_path / "gtdb" / "GCF_000005845.2.fna.gz"
        assert cache.get_cached_path(ref) == expected

    def test_get_cached_path_ncbi(self, tmp_path):
        cache = GenomeCache(cache_dir=tmp_path)
        ref = GenomeRef("S. cerevisiae", "GCF_000146045.2", "ncbi", "eukaryota")
        expected = tmp_path / "ncbi" / "GCF_000146045.2.fna.gz"
        assert cache.get_cached_path(ref) == expected

    def test_is_cached_false(self, tmp_path):
        cache = GenomeCache(cache_dir=tmp_path)
        ref = GenomeRef("E. coli", "GCF_000005845.2", "gtdb", "bacteria")
        assert cache.is_cached(ref) is False

    def test_is_cached_true(self, tmp_path):
        cache = GenomeCache(cache_dir=tmp_path)
        ref = GenomeRef("E. coli", "GCF_000005845.2", "gtdb", "bacteria")
        # Create the cached file
        cached_path = cache.get_cached_path(ref)
        cached_path.parent.mkdir(parents=True, exist_ok=True)
        cached_path.write_text("dummy")
        assert cache.is_cached(ref) is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_species.py::TestGenomeCache -v`
Expected: FAIL with "cannot import name 'GenomeCache'"

**Step 3: Write minimal implementation**

```python
# Add to nanopore_simulator/core/species.py
import os


class GenomeCache:
    """Manages cached genome files in ~/.nanorunner/genomes/"""

    def __init__(self, cache_dir: Optional[Path] = None) -> None:
        if cache_dir is None:
            home = Path(os.environ.get("HOME", Path.home()))
            self.cache_dir = home / ".nanorunner" / "genomes"
        else:
            self.cache_dir = cache_dir

    def get_cached_path(self, ref: GenomeRef) -> Path:
        """Get the path where a genome would be cached."""
        return self.cache_dir / ref.source / f"{ref.accession}.fna.gz"

    def is_cached(self, ref: GenomeRef) -> bool:
        """Check if a genome is already cached."""
        return self.get_cached_path(ref).exists()
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_species.py::TestGenomeCache -v`
Expected: PASS (6 tests)

**Step 5: Commit**

```bash
git add nanopore_simulator/core/species.py tests/test_species.py
git commit -m "feat(species): add GenomeCache for managing cached genomes"
```

---

## Task 3: MockOrganism and MockCommunity Data Structures

**Files:**
- Create: `nanopore_simulator/core/mocks.py`
- Test: `tests/test_mocks.py`

**Step 1: Write failing test**

```python
# tests/test_mocks.py
"""Tests for mock community definitions"""

import pytest

from nanopore_simulator.core.mocks import MockOrganism, MockCommunity


class TestMockOrganism:

    def test_create_gtdb_organism(self):
        org = MockOrganism(
            name="Escherichia coli",
            resolver="gtdb",
            abundance=0.125,
        )
        assert org.name == "Escherichia coli"
        assert org.resolver == "gtdb"
        assert org.abundance == 0.125
        assert org.accession is None

    def test_create_ncbi_organism_with_accession(self):
        org = MockOrganism(
            name="Saccharomyces cerevisiae",
            resolver="ncbi",
            abundance=0.1,
            accession="GCF_000146045.2",
        )
        assert org.resolver == "ncbi"
        assert org.accession == "GCF_000146045.2"

    def test_invalid_resolver(self):
        with pytest.raises(ValueError, match="resolver"):
            MockOrganism(name="Test", resolver="invalid", abundance=0.5)

    def test_invalid_abundance_negative(self):
        with pytest.raises(ValueError, match="abundance"):
            MockOrganism(name="Test", resolver="gtdb", abundance=-0.1)

    def test_invalid_abundance_over_one(self):
        with pytest.raises(ValueError, match="abundance"):
            MockOrganism(name="Test", resolver="gtdb", abundance=1.5)


class TestMockCommunity:

    def test_create_community(self):
        organisms = [
            MockOrganism("E. coli", "gtdb", 0.5),
            MockOrganism("S. aureus", "gtdb", 0.5),
        ]
        community = MockCommunity(
            name="test_mock",
            description="Test mock community",
            organisms=organisms,
        )
        assert community.name == "test_mock"
        assert len(community.organisms) == 2

    def test_abundances_must_sum_to_one(self):
        organisms = [
            MockOrganism("E. coli", "gtdb", 0.3),
            MockOrganism("S. aureus", "gtdb", 0.3),
        ]
        with pytest.raises(ValueError, match="sum to 1.0"):
            MockCommunity("test", "Test", organisms)

    def test_abundances_tolerance(self):
        # Should accept values that sum to ~1.0 within tolerance
        organisms = [
            MockOrganism("E. coli", "gtdb", 0.333),
            MockOrganism("S. aureus", "gtdb", 0.333),
            MockOrganism("B. subtilis", "gtdb", 0.334),
        ]
        community = MockCommunity("test", "Test", organisms)
        assert len(community.organisms) == 3

    def test_empty_organisms(self):
        with pytest.raises(ValueError, match="at least one organism"):
            MockCommunity("test", "Test", [])
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_mocks.py -v`
Expected: FAIL with "No module named 'nanopore_simulator.core.mocks'"

**Step 3: Write minimal implementation**

```python
# nanopore_simulator/core/mocks.py
"""Mock community definitions for sample generation"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class MockOrganism:
    """A single organism in a mock community"""

    name: str
    resolver: str  # "gtdb" or "ncbi"
    abundance: float  # Proportion in community (0.0-1.0)
    accession: Optional[str] = None  # Override specific strain

    def __post_init__(self) -> None:
        valid_resolvers = {"gtdb", "ncbi"}
        if self.resolver not in valid_resolvers:
            raise ValueError(f"resolver must be one of {valid_resolvers}")
        if not 0.0 <= self.abundance <= 1.0:
            raise ValueError("abundance must be between 0.0 and 1.0")


@dataclass
class MockCommunity:
    """A preset mock community with defined composition"""

    name: str
    description: str
    organisms: List[MockOrganism]

    def __post_init__(self) -> None:
        if not self.organisms:
            raise ValueError("MockCommunity must have at least one organism")
        total = sum(org.abundance for org in self.organisms)
        if not 0.99 <= total <= 1.01:
            raise ValueError(
                f"Organism abundances must sum to 1.0 (got {total:.3f})"
            )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_mocks.py -v`
Expected: PASS (9 tests)

**Step 5: Commit**

```bash
git add nanopore_simulator/core/mocks.py tests/test_mocks.py
git commit -m "feat(mocks): add MockOrganism and MockCommunity dataclasses"
```

---

## Task 4: Built-in Mock Communities

**Files:**
- Modify: `nanopore_simulator/core/mocks.py`
- Test: `tests/test_mocks.py`

**Step 1: Write failing test**

```python
# Add to tests/test_mocks.py
from nanopore_simulator.core.mocks import (
    MockOrganism,
    MockCommunity,
    BUILTIN_MOCKS,
    get_mock_community,
    list_mock_communities,
)


class TestBuiltinMocks:

    def test_zymo_d6300_exists(self):
        assert "zymo_d6300" in BUILTIN_MOCKS

    def test_zymo_d6300_has_10_organisms(self):
        mock = BUILTIN_MOCKS["zymo_d6300"]
        assert len(mock.organisms) == 10

    def test_zymo_d6300_has_fungi(self):
        mock = BUILTIN_MOCKS["zymo_d6300"]
        ncbi_orgs = [o for o in mock.organisms if o.resolver == "ncbi"]
        assert len(ncbi_orgs) == 2  # Two yeasts

    def test_quick_3species_exists(self):
        assert "quick_3species" in BUILTIN_MOCKS

    def test_quick_3species_equal_abundances(self):
        mock = BUILTIN_MOCKS["quick_3species"]
        for org in mock.organisms:
            assert abs(org.abundance - 1/3) < 0.01

    def test_get_mock_community_exists(self):
        mock = get_mock_community("zymo_d6300")
        assert mock is not None
        assert mock.name == "zymo_d6300"

    def test_get_mock_community_not_found(self):
        mock = get_mock_community("nonexistent")
        assert mock is None

    def test_list_mock_communities(self):
        mocks = list_mock_communities()
        assert "zymo_d6300" in mocks
        assert "quick_3species" in mocks
        assert isinstance(mocks["zymo_d6300"], str)  # Description
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_mocks.py::TestBuiltinMocks -v`
Expected: FAIL with "cannot import name 'BUILTIN_MOCKS'"

**Step 3: Write minimal implementation**

```python
# Add to nanopore_simulator/core/mocks.py
from typing import Dict


# Zymo D6300 Standard (Even) - 8 bacteria + 2 yeasts
_ZYMO_D6300_ORGANISMS = [
    MockOrganism("Pseudomonas aeruginosa", "gtdb", 0.1),
    MockOrganism("Escherichia coli", "gtdb", 0.1),
    MockOrganism("Salmonella enterica", "gtdb", 0.1),
    MockOrganism("Lactobacillus fermentum", "gtdb", 0.1),
    MockOrganism("Enterococcus faecalis", "gtdb", 0.1),
    MockOrganism("Staphylococcus aureus", "gtdb", 0.1),
    MockOrganism("Listeria monocytogenes", "gtdb", 0.1),
    MockOrganism("Bacillus subtilis", "gtdb", 0.1),
    # Fungi - use NCBI resolver
    MockOrganism("Saccharomyces cerevisiae", "ncbi", 0.1, "GCF_000146045.2"),
    MockOrganism("Cryptococcus neoformans", "ncbi", 0.1, "GCF_000149245.1"),
]

# Quick 3-species test mock
_QUICK_3SPECIES_ORGANISMS = [
    MockOrganism("Escherichia coli", "gtdb", 1/3),
    MockOrganism("Staphylococcus aureus", "gtdb", 1/3),
    MockOrganism("Bacillus subtilis", "gtdb", 1/3),
]

# Quick gut mock
_QUICK_GUT5_ORGANISMS = [
    MockOrganism("Bacteroides fragilis", "gtdb", 0.2),
    MockOrganism("Faecalibacterium prausnitzii", "gtdb", 0.2),
    MockOrganism("Escherichia coli", "gtdb", 0.2),
    MockOrganism("Bifidobacterium longum", "gtdb", 0.2),
    MockOrganism("Akkermansia muciniphila", "gtdb", 0.2),
]

# Quick pathogen panel
_QUICK_PATHOGENS_ORGANISMS = [
    MockOrganism("Staphylococcus aureus", "gtdb", 0.2),
    MockOrganism("Escherichia coli", "gtdb", 0.2),
    MockOrganism("Klebsiella pneumoniae", "gtdb", 0.2),
    MockOrganism("Pseudomonas aeruginosa", "gtdb", 0.2),
    MockOrganism("Enterococcus faecium", "gtdb", 0.2),
]


BUILTIN_MOCKS: Dict[str, MockCommunity] = {
    "zymo_d6300": MockCommunity(
        name="zymo_d6300",
        description="Zymo D6300 Standard (even) - 8 bacteria + 2 yeasts",
        organisms=_ZYMO_D6300_ORGANISMS,
    ),
    "quick_3species": MockCommunity(
        name="quick_3species",
        description="Minimal 3-species test mock (E. coli, S. aureus, B. subtilis)",
        organisms=_QUICK_3SPECIES_ORGANISMS,
    ),
    "quick_gut5": MockCommunity(
        name="quick_gut5",
        description="Simple 5-species gut microbiome mock",
        organisms=_QUICK_GUT5_ORGANISMS,
    ),
    "quick_pathogens": MockCommunity(
        name="quick_pathogens",
        description="5 clinically relevant pathogens (ESKAPE subset)",
        organisms=_QUICK_PATHOGENS_ORGANISMS,
    ),
}


def get_mock_community(name: str) -> Optional[MockCommunity]:
    """Get a mock community by name."""
    return BUILTIN_MOCKS.get(name)


def list_mock_communities() -> Dict[str, str]:
    """List all available mock communities with descriptions."""
    return {name: mock.description for name, mock in BUILTIN_MOCKS.items()}
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_mocks.py::TestBuiltinMocks -v`
Expected: PASS (8 tests)

**Step 5: Commit**

```bash
git add nanopore_simulator/core/mocks.py tests/test_mocks.py
git commit -m "feat(mocks): add built-in mock communities (Zymo D6300, quick tests)"
```

---

## Task 5: GTDB Species Index

**Files:**
- Modify: `nanopore_simulator/core/species.py`
- Test: `tests/test_species.py`

**Step 1: Write failing test**

```python
# Add to tests/test_species.py
from nanopore_simulator.core.species import (
    GenomeRef,
    GenomeCache,
    GTDBIndex,
)


class TestGTDBIndex:

    def test_lookup_ecoli(self, tmp_path):
        # Create a minimal index file
        index_file = tmp_path / "gtdb_species.tsv"
        index_file.write_text(
            "species\taccession\tdomain\n"
            "Escherichia coli\tGCF_000005845.2\tbacteria\n"
            "Staphylococcus aureus\tGCF_000013425.1\tbacteria\n"
        )
        index = GTDBIndex(index_file)
        ref = index.lookup("Escherichia coli")
        assert ref is not None
        assert ref.accession == "GCF_000005845.2"
        assert ref.source == "gtdb"
        assert ref.domain == "bacteria"

    def test_lookup_not_found(self, tmp_path):
        index_file = tmp_path / "gtdb_species.tsv"
        index_file.write_text("species\taccession\tdomain\n")
        index = GTDBIndex(index_file)
        ref = index.lookup("Nonexistent species")
        assert ref is None

    def test_lookup_case_insensitive(self, tmp_path):
        index_file = tmp_path / "gtdb_species.tsv"
        index_file.write_text(
            "species\taccession\tdomain\n"
            "Escherichia coli\tGCF_000005845.2\tbacteria\n"
        )
        index = GTDBIndex(index_file)
        ref = index.lookup("escherichia coli")
        assert ref is not None
        assert ref.name == "Escherichia coli"

    def test_fuzzy_suggestions(self, tmp_path):
        index_file = tmp_path / "gtdb_species.tsv"
        index_file.write_text(
            "species\taccession\tdomain\n"
            "Escherichia coli\tGCF_000005845.2\tbacteria\n"
            "Escherichia fergusonii\tGCF_000026225.1\tbacteria\n"
        )
        index = GTDBIndex(index_file)
        suggestions = index.suggest("Escherichia col")
        assert "Escherichia coli" in suggestions
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_species.py::TestGTDBIndex -v`
Expected: FAIL with "cannot import name 'GTDBIndex'"

**Step 3: Write minimal implementation**

```python
# Add to nanopore_simulator/core/species.py
from typing import Dict, List


class GTDBIndex:
    """Local index for GTDB species-to-accession mapping"""

    def __init__(self, index_path: Path) -> None:
        self.index_path = index_path
        self._species_map: Dict[str, tuple] = {}  # lowercase name -> (name, accession, domain)
        self._load_index()

    def _load_index(self) -> None:
        """Load the TSV index file."""
        if not self.index_path.exists():
            return
        with open(self.index_path) as f:
            # Skip header
            next(f, None)
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 3:
                    name, accession, domain = parts[0], parts[1], parts[2]
                    self._species_map[name.lower()] = (name, accession, domain)

    def lookup(self, species_name: str) -> Optional[GenomeRef]:
        """Look up a species by name."""
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
        """Suggest species names matching a partial input."""
        partial = partial_name.lower()
        matches = []
        for key, (name, _, _) in self._species_map.items():
            if partial in key:
                matches.append(name)
                if len(matches) >= max_results:
                    break
        return matches
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_species.py::TestGTDBIndex -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add nanopore_simulator/core/species.py tests/test_species.py
git commit -m "feat(species): add GTDBIndex for local species lookup"
```

---

## Task 6: NCBI Taxonomy Resolver

**Files:**
- Modify: `nanopore_simulator/core/species.py`
- Test: `tests/test_species.py`

**Step 1: Write failing test**

```python
# Add to tests/test_species.py
from unittest.mock import patch, MagicMock

from nanopore_simulator.core.species import NCBIResolver


class TestNCBIResolver:

    def test_resolve_by_taxid(self, tmp_path):
        # Mock subprocess call to datasets
        resolver = NCBIResolver()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout='{"accession": "GCF_000146045.2", "organism_name": "Saccharomyces cerevisiae"}'
            )
            ref = resolver.resolve_by_taxid(4932)
            assert ref is not None
            assert ref.accession == "GCF_000146045.2"
            assert ref.source == "ncbi"
            assert ref.domain == "eukaryota"

    def test_resolve_by_name(self, tmp_path):
        resolver = NCBIResolver()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout='{"accession": "GCF_000146045.2", "organism_name": "Saccharomyces cerevisiae", "tax_id": 4932}'
            )
            ref = resolver.resolve_by_name("Saccharomyces cerevisiae")
            assert ref is not None
            assert ref.name == "Saccharomyces cerevisiae"

    def test_datasets_not_available(self):
        resolver = NCBIResolver()
        with patch("shutil.which", return_value=None):
            assert resolver.is_available() is False

    def test_datasets_available(self):
        resolver = NCBIResolver()
        with patch("shutil.which", return_value="/usr/bin/datasets"):
            assert resolver.is_available() is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_species.py::TestNCBIResolver -v`
Expected: FAIL with "cannot import name 'NCBIResolver'"

**Step 3: Write minimal implementation**

```python
# Add to nanopore_simulator/core/species.py
import json
import shutil
import subprocess


class NCBIResolver:
    """Resolve species via NCBI taxonomy and datasets CLI"""

    def is_available(self) -> bool:
        """Check if ncbi-datasets-cli is installed."""
        return shutil.which("datasets") is not None

    def resolve_by_taxid(self, taxid: int) -> Optional[GenomeRef]:
        """Resolve a genome reference by NCBI taxonomy ID."""
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
                domain="eukaryota",  # Default for NCBI fallback
            )
        except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError):
            return None

    def resolve_by_name(self, name: str) -> Optional[GenomeRef]:
        """Resolve a genome reference by organism name."""
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
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_species.py::TestNCBIResolver -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add nanopore_simulator/core/species.py tests/test_species.py
git commit -m "feat(species): add NCBIResolver for taxonomy ID and name lookup"
```

---

## Task 7: SpeciesResolver (Unified Interface)

**Files:**
- Modify: `nanopore_simulator/core/species.py`
- Test: `tests/test_species.py`

**Step 1: Write failing test**

```python
# Add to tests/test_species.py
from nanopore_simulator.core.species import SpeciesResolver


class TestSpeciesResolver:

    def test_resolve_gtdb_species(self, tmp_path, monkeypatch):
        # Create minimal GTDB index
        index_file = tmp_path / "indexes" / "gtdb_species.tsv"
        index_file.parent.mkdir(parents=True, exist_ok=True)
        index_file.write_text(
            "species\taccession\tdomain\n"
            "Escherichia coli\tGCF_000005845.2\tbacteria\n"
        )
        monkeypatch.setenv("HOME", str(tmp_path))

        resolver = SpeciesResolver(index_dir=tmp_path / "indexes")
        ref = resolver.resolve("Escherichia coli")
        assert ref is not None
        assert ref.accession == "GCF_000005845.2"
        assert ref.source == "gtdb"

    def test_resolve_falls_back_to_ncbi(self, tmp_path, monkeypatch):
        # Empty GTDB index
        index_file = tmp_path / "indexes" / "gtdb_species.tsv"
        index_file.parent.mkdir(parents=True, exist_ok=True)
        index_file.write_text("species\taccession\tdomain\n")
        monkeypatch.setenv("HOME", str(tmp_path))

        resolver = SpeciesResolver(index_dir=tmp_path / "indexes")
        with patch.object(resolver._ncbi, "resolve_by_name") as mock_ncbi:
            mock_ncbi.return_value = GenomeRef(
                "Saccharomyces cerevisiae", "GCF_000146045.2", "ncbi", "eukaryota"
            )
            ref = resolver.resolve("Saccharomyces cerevisiae")
            assert ref is not None
            assert ref.source == "ncbi"

    def test_resolve_not_found(self, tmp_path, monkeypatch):
        index_file = tmp_path / "indexes" / "gtdb_species.tsv"
        index_file.parent.mkdir(parents=True, exist_ok=True)
        index_file.write_text("species\taccession\tdomain\n")
        monkeypatch.setenv("HOME", str(tmp_path))

        resolver = SpeciesResolver(index_dir=tmp_path / "indexes")
        with patch.object(resolver._ncbi, "resolve_by_name", return_value=None):
            ref = resolver.resolve("Nonexistent organism")
            assert ref is None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_species.py::TestSpeciesResolver -v`
Expected: FAIL with "cannot import name 'SpeciesResolver'"

**Step 3: Write minimal implementation**

```python
# Add to nanopore_simulator/core/species.py

class SpeciesResolver:
    """Unified species resolution with GTDB-first, NCBI fallback strategy"""

    def __init__(
        self,
        index_dir: Optional[Path] = None,
        cache_dir: Optional[Path] = None,
    ) -> None:
        if index_dir is None:
            home = Path(os.environ.get("HOME", Path.home()))
            index_dir = home / ".nanorunner" / "indexes"

        self._gtdb = GTDBIndex(index_dir / "gtdb_species.tsv")
        self._ncbi = NCBIResolver()
        self._cache = GenomeCache(cache_dir)

    def resolve(self, species_name: str) -> Optional[GenomeRef]:
        """Resolve a species name to a genome reference.

        Strategy:
        1. Try GTDB index (bacteria/archaea)
        2. Fall back to NCBI (eukaryotes, other)
        """
        # Try GTDB first
        ref = self._gtdb.lookup(species_name)
        if ref is not None:
            return ref

        # Fall back to NCBI
        return self._ncbi.resolve_by_name(species_name)

    def resolve_taxid(self, taxid: int) -> Optional[GenomeRef]:
        """Resolve by NCBI taxonomy ID."""
        return self._ncbi.resolve_by_taxid(taxid)

    def suggest(self, partial_name: str) -> List[str]:
        """Get species name suggestions."""
        return self._gtdb.suggest(partial_name)

    @property
    def cache(self) -> GenomeCache:
        """Access the genome cache."""
        return self._cache
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_species.py::TestSpeciesResolver -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add nanopore_simulator/core/species.py tests/test_species.py
git commit -m "feat(species): add SpeciesResolver with GTDB-first, NCBI fallback"
```

---

## Task 8: Genome Download Function

**Files:**
- Modify: `nanopore_simulator/core/species.py`
- Test: `tests/test_species.py`

**Step 1: Write failing test**

```python
# Add to tests/test_species.py

class TestGenomeDownload:

    def test_download_genome(self, tmp_path):
        cache = GenomeCache(cache_dir=tmp_path)
        ref = GenomeRef("E. coli", "GCF_000005845.2", "gtdb", "bacteria")

        with patch("subprocess.run") as mock_run:
            # Simulate datasets download creating a zip
            def create_mock_download(*args, **kwargs):
                # Create the expected output structure
                zip_path = tmp_path / "ncbi_dataset.zip"
                extract_dir = tmp_path / "ncbi_dataset"
                extract_dir.mkdir(parents=True, exist_ok=True)
                fna_dir = extract_dir / "data" / "GCF_000005845.2"
                fna_dir.mkdir(parents=True, exist_ok=True)
                (fna_dir / "GCF_000005845.2_genomic.fna").write_text(">chr\nATCG\n")
                # Create zip
                import zipfile
                with zipfile.ZipFile(zip_path, "w") as zf:
                    zf.write(
                        fna_dir / "GCF_000005845.2_genomic.fna",
                        "data/GCF_000005845.2/GCF_000005845.2_genomic.fna"
                    )
                return MagicMock(returncode=0)

            mock_run.side_effect = create_mock_download

            path = download_genome(ref, cache)
            assert path.exists()
            assert path.suffix == ".gz"

    def test_download_uses_cache(self, tmp_path):
        cache = GenomeCache(cache_dir=tmp_path)
        ref = GenomeRef("E. coli", "GCF_000005845.2", "gtdb", "bacteria")

        # Pre-create cached file
        cached_path = cache.get_cached_path(ref)
        cached_path.parent.mkdir(parents=True, exist_ok=True)
        cached_path.write_text("cached")

        # Should not call subprocess
        with patch("subprocess.run") as mock_run:
            path = download_genome(ref, cache)
            mock_run.assert_not_called()
            assert path == cached_path
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_species.py::TestGenomeDownload -v`
Expected: FAIL with "cannot import name 'download_genome'"

**Step 3: Write minimal implementation**

```python
# Add to nanopore_simulator/core/species.py
import gzip as gzip_module
import zipfile
import tempfile
import logging

logger = logging.getLogger(__name__)


def download_genome(ref: GenomeRef, cache: GenomeCache) -> Path:
    """Download a genome and cache it.

    Returns the path to the cached genome file.
    """
    # Check cache first
    cached_path = cache.get_cached_path(ref)
    if cached_path.exists():
        logger.info(f"Using cached genome: {cached_path}")
        return cached_path

    # Download via datasets CLI
    logger.info(f"Downloading genome: {ref.accession}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        zip_path = tmpdir / "ncbi_dataset.zip"

        result = subprocess.run(
            [
                "datasets", "download", "genome", "accession", ref.accession,
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

        # Extract and find the .fna file
        extract_dir = tmpdir / "extract"
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
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_species.py::TestGenomeDownload -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add nanopore_simulator/core/species.py tests/test_species.py
git commit -m "feat(species): add download_genome function with caching"
```

---

## Task 9: SimulationConfig Updates

**Files:**
- Modify: `nanopore_simulator/core/config.py`
- Test: `tests/test_config.py` (create if needed)

**Step 1: Write failing test**

```python
# Add to tests/test_unit_core_components.py or create tests/test_config_species.py
import pytest
from pathlib import Path

from nanopore_simulator.core.config import SimulationConfig


class TestSimulationConfigSpecies:

    def test_species_inputs_field(self, tmp_path):
        config = SimulationConfig(
            target_dir=tmp_path,
            operation="generate",
            species_inputs=["Escherichia coli", "Staphylococcus aureus"],
            sample_type="pure",
        )
        assert config.species_inputs == ["Escherichia coli", "Staphylococcus aureus"]
        assert config.sample_type == "pure"

    def test_mock_name_field(self, tmp_path):
        config = SimulationConfig(
            target_dir=tmp_path,
            operation="generate",
            mock_name="zymo_d6300",
            sample_type="mixed",
        )
        assert config.mock_name == "zymo_d6300"
        assert config.sample_type == "mixed"

    def test_abundances_field(self, tmp_path):
        config = SimulationConfig(
            target_dir=tmp_path,
            operation="generate",
            species_inputs=["E. coli", "S. aureus"],
            abundances=[0.7, 0.3],
            sample_type="mixed",
        )
        assert config.abundances == [0.7, 0.3]

    def test_abundances_must_match_species_count(self, tmp_path):
        with pytest.raises(ValueError, match="abundances"):
            SimulationConfig(
                target_dir=tmp_path,
                operation="generate",
                species_inputs=["E. coli", "S. aureus"],
                abundances=[0.5],  # Wrong count
                sample_type="mixed",
            )

    def test_abundances_must_sum_to_one(self, tmp_path):
        with pytest.raises(ValueError, match="sum to 1.0"):
            SimulationConfig(
                target_dir=tmp_path,
                operation="generate",
                species_inputs=["E. coli", "S. aureus"],
                abundances=[0.5, 0.3],  # Sums to 0.8
                sample_type="mixed",
            )

    def test_sample_type_default_for_mock(self, tmp_path):
        config = SimulationConfig(
            target_dir=tmp_path,
            operation="generate",
            mock_name="zymo_d6300",
        )
        assert config.sample_type == "mixed"  # Default for mock

    def test_sample_type_default_for_species(self, tmp_path):
        config = SimulationConfig(
            target_dir=tmp_path,
            operation="generate",
            species_inputs=["E. coli", "S. aureus"],
        )
        assert config.sample_type == "pure"  # Default for species

    def test_invalid_sample_type(self, tmp_path):
        with pytest.raises(ValueError, match="sample_type"):
            SimulationConfig(
                target_dir=tmp_path,
                operation="generate",
                species_inputs=["E. coli"],
                sample_type="invalid",
            )
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_unit_core_components.py::TestSimulationConfigSpecies -v`
Expected: FAIL with "species_inputs" not a valid field

**Step 3: Write minimal implementation**

```python
# Modify nanopore_simulator/core/config.py
# Add new fields to SimulationConfig dataclass (after existing fields):

    # Species-based generation parameters
    species_inputs: Optional[List[str]] = None  # Species names to resolve
    mock_name: Optional[str] = None  # Preset mock community name
    taxid_inputs: Optional[List[int]] = None  # Direct NCBI taxonomy IDs
    sample_type: Optional[str] = None  # "pure" or "mixed"
    abundances: Optional[List[float]] = None  # Custom abundances for mixed samples
    offline_mode: bool = False  # Use only cached genomes

# Add validation in _validate_config() method:

        # Validate species-based generation
        if self.species_inputs or self.mock_name or self.taxid_inputs:
            if self.operation != "generate":
                # Auto-set operation to generate
                object.__setattr__(self, "operation", "generate")

            # Validate sample_type
            if self.sample_type is None:
                # Default: mixed for mock, pure for species
                if self.mock_name:
                    object.__setattr__(self, "sample_type", "mixed")
                else:
                    object.__setattr__(self, "sample_type", "pure")

            if self.sample_type not in {"pure", "mixed"}:
                raise ValueError("sample_type must be 'pure' or 'mixed'")

            # Validate abundances
            if self.abundances is not None:
                if self.mock_name:
                    raise ValueError("abundances cannot be used with mock communities")
                input_count = len(self.species_inputs or []) + len(self.taxid_inputs or [])
                if len(self.abundances) != input_count:
                    raise ValueError(
                        f"abundances count ({len(self.abundances)}) must match "
                        f"species/taxid count ({input_count})"
                    )
                total = sum(self.abundances)
                if not 0.99 <= total <= 1.01:
                    raise ValueError(f"abundances must sum to 1.0 (got {total:.3f})")

            # genome_inputs not required for species-based generation
            if not self.genome_inputs:
                object.__setattr__(self, "genome_inputs", [])
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_unit_core_components.py::TestSimulationConfigSpecies -v`
Expected: PASS (8 tests)

**Step 5: Commit**

```bash
git add nanopore_simulator/core/config.py tests/test_unit_core_components.py
git commit -m "feat(config): add species_inputs, mock_name, sample_type fields"
```

---

## Task 10: CLI Arguments for Species/Mock

**Files:**
- Modify: `nanopore_simulator/cli/main.py`
- Test: `tests/test_cli.py`

**Step 1: Write failing test**

```python
# Add to tests/test_cli.py or create tests/test_cli_species.py
import pytest
from unittest.mock import patch, MagicMock
import sys

from nanopore_simulator.cli.main import main


class TestCLISpeciesArgs:

    def test_species_argument(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            sys, "argv",
            ["nanorunner", "--species", "Escherichia coli", str(tmp_path)]
        )
        with patch("nanopore_simulator.cli.main.NanoporeSimulator") as mock_sim:
            mock_sim.return_value.run_simulation.return_value = None
            main()
            config = mock_sim.call_args[0][0]
            assert config.species_inputs == ["Escherichia coli"]

    def test_multiple_species(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            sys, "argv",
            ["nanorunner", "--species", "E. coli", "S. aureus", str(tmp_path)]
        )
        with patch("nanopore_simulator.cli.main.NanoporeSimulator") as mock_sim:
            mock_sim.return_value.run_simulation.return_value = None
            main()
            config = mock_sim.call_args[0][0]
            assert len(config.species_inputs) == 2

    def test_mock_argument(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            sys, "argv",
            ["nanorunner", "--mock", "zymo_d6300", str(tmp_path)]
        )
        with patch("nanopore_simulator.cli.main.NanoporeSimulator") as mock_sim:
            mock_sim.return_value.run_simulation.return_value = None
            main()
            config = mock_sim.call_args[0][0]
            assert config.mock_name == "zymo_d6300"

    def test_sample_type_argument(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            sys, "argv",
            ["nanorunner", "--species", "E. coli", "--sample-type", "mixed", str(tmp_path)]
        )
        with patch("nanopore_simulator.cli.main.NanoporeSimulator") as mock_sim:
            mock_sim.return_value.run_simulation.return_value = None
            main()
            config = mock_sim.call_args[0][0]
            assert config.sample_type == "mixed"

    def test_abundances_argument(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            sys, "argv",
            [
                "nanorunner", "--species", "E. coli", "S. aureus",
                "--sample-type", "mixed",
                "--abundances", "0.7", "0.3",
                str(tmp_path)
            ]
        )
        with patch("nanopore_simulator.cli.main.NanoporeSimulator") as mock_sim:
            mock_sim.return_value.run_simulation.return_value = None
            main()
            config = mock_sim.call_args[0][0]
            assert config.abundances == [0.7, 0.3]

    def test_list_mocks_command(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["nanorunner", "--list-mocks"])
        result = main()
        assert result == 0
        captured = capsys.readouterr()
        assert "zymo_d6300" in captured.out

    def test_species_and_mock_mutually_exclusive(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(
            sys, "argv",
            ["nanorunner", "--species", "E. coli", "--mock", "zymo_d6300", str(tmp_path)]
        )
        with pytest.raises(SystemExit):
            main()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::TestCLISpeciesArgs -v`
Expected: FAIL with unrecognized argument "--species"

**Step 3: Write minimal implementation**

```python
# Modify nanopore_simulator/cli/main.py

# Add import at top:
from ..core.mocks import list_mock_communities, get_mock_community

# Add new command function:
def list_mocks_command() -> int:
    """List available mock communities"""
    mocks = list_mock_communities()
    print("Available Mock Communities:")
    print("=" * 50)
    for name, description in mocks.items():
        print(f"  {name:20} - {description}")
    return 0

# Add new argument group after gen_group:
    species_group = parser.add_argument_group("Species/Mock Generation")
    species_group.add_argument(
        "--species",
        type=str,
        nargs="+",
        metavar="NAME",
        help="Species names to resolve via GTDB/NCBI",
    )
    species_group.add_argument(
        "--mock",
        type=str,
        metavar="MOCK_NAME",
        help="Preset mock community name (e.g., zymo_d6300)",
    )
    species_group.add_argument(
        "--taxid",
        type=int,
        nargs="+",
        metavar="TAXID",
        help="Direct NCBI taxonomy IDs",
    )
    species_group.add_argument(
        "--sample-type",
        choices=["pure", "mixed"],
        help="Sample type: pure (per-species barcodes) or mixed (interleaved)",
    )
    species_group.add_argument(
        "--abundances",
        type=float,
        nargs="+",
        metavar="ABUNDANCE",
        help="Custom abundances for mixed samples (must sum to 1.0)",
    )
    species_group.add_argument(
        "--offline",
        action="store_true",
        help="Use only cached genomes, no network requests",
    )

# Add --list-mocks argument:
    parser.add_argument(
        "--list-mocks",
        action="store_true",
        help="List available mock communities",
    )

# Add handler after other list commands:
    if args.list_mocks:
        return list_mocks_command()

# Add mutual exclusivity check:
    species_mock_count = sum([
        args.species is not None,
        args.mock is not None,
        args.taxid is not None,
        args.genomes is not None,
    ])
    if species_mock_count > 1:
        parser.error("--species, --mock, --taxid, and --genomes are mutually exclusive")

# Add to config building (both profile and non-profile paths):
    if args.species:
        config_kwargs["species_inputs"] = args.species
    if args.mock:
        config_kwargs["mock_name"] = args.mock
    if args.taxid:
        config_kwargs["taxid_inputs"] = args.taxid
    if args.sample_type:
        config_kwargs["sample_type"] = args.sample_type
    if args.abundances:
        config_kwargs["abundances"] = args.abundances
    if args.offline:
        config_kwargs["offline_mode"] = args.offline
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py::TestCLISpeciesArgs -v`
Expected: PASS (7 tests)

**Step 5: Commit**

```bash
git add nanopore_simulator/cli/main.py tests/test_cli.py
git commit -m "feat(cli): add --species, --mock, --sample-type, --abundances arguments"
```

---

## Task 11: Simulator Integration

**Files:**
- Modify: `nanopore_simulator/core/simulator.py`
- Test: `tests/test_simulator_species.py`

**Step 1: Write failing test**

```python
# tests/test_simulator_species.py
"""Tests for species-based simulation"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from nanopore_simulator.core.config import SimulationConfig
from nanopore_simulator.core.simulator import NanoporeSimulator
from nanopore_simulator.core.species import GenomeRef


class TestSimulatorSpeciesResolution:

    def test_resolves_species_before_generation(self, tmp_path):
        config = SimulationConfig(
            target_dir=tmp_path / "output",
            operation="generate",
            species_inputs=["Escherichia coli"],
            sample_type="pure",
            read_count=10,
            reads_per_file=10,
        )

        with patch("nanopore_simulator.core.simulator.SpeciesResolver") as mock_resolver_cls:
            mock_resolver = MagicMock()
            mock_resolver_cls.return_value = mock_resolver

            # Mock successful resolution
            mock_ref = GenomeRef("Escherichia coli", "GCF_000005845.2", "gtdb", "bacteria")
            mock_resolver.resolve.return_value = mock_ref

            # Mock download returning a valid genome
            genome_path = tmp_path / "genome.fa"
            genome_path.write_text(">chr1\nATCGATCGATCG\n")

            with patch("nanopore_simulator.core.simulator.download_genome", return_value=genome_path):
                sim = NanoporeSimulator(config, enable_monitoring=False)
                # Verify species were resolved
                mock_resolver.resolve.assert_called_with("Escherichia coli")

    def test_mock_community_resolution(self, tmp_path):
        config = SimulationConfig(
            target_dir=tmp_path / "output",
            operation="generate",
            mock_name="quick_3species",
            sample_type="mixed",
            read_count=10,
            reads_per_file=10,
        )

        with patch("nanopore_simulator.core.simulator.SpeciesResolver") as mock_resolver_cls:
            mock_resolver = MagicMock()
            mock_resolver_cls.return_value = mock_resolver

            mock_ref = GenomeRef("E. coli", "GCF_000005845.2", "gtdb", "bacteria")
            mock_resolver.resolve.return_value = mock_ref

            genome_path = tmp_path / "genome.fa"
            genome_path.write_text(">chr1\nATCGATCGATCG\n")

            with patch("nanopore_simulator.core.simulator.download_genome", return_value=genome_path):
                sim = NanoporeSimulator(config, enable_monitoring=False)
                # Should have resolved 3 species
                assert mock_resolver.resolve.call_count == 3

    def test_species_resolution_failure_raises(self, tmp_path):
        config = SimulationConfig(
            target_dir=tmp_path / "output",
            operation="generate",
            species_inputs=["Nonexistent organism"],
            sample_type="pure",
            read_count=10,
            reads_per_file=10,
        )

        with patch("nanopore_simulator.core.simulator.SpeciesResolver") as mock_resolver_cls:
            mock_resolver = MagicMock()
            mock_resolver_cls.return_value = mock_resolver
            mock_resolver.resolve.return_value = None
            mock_resolver.suggest.return_value = []

            with pytest.raises(ValueError, match="Could not resolve"):
                NanoporeSimulator(config, enable_monitoring=False)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_simulator_species.py -v`
Expected: FAIL with "cannot import name 'SpeciesResolver' from 'nanopore_simulator.core.simulator'"

**Step 3: Write minimal implementation**

```python
# Modify nanopore_simulator/core/simulator.py

# Add imports at top:
from .species import SpeciesResolver, download_genome, GenomeRef
from .mocks import get_mock_community

# Add method to NanoporeSimulator class:
    def _resolve_species_inputs(self) -> None:
        """Resolve species/mock inputs to genome paths."""
        if not (self.config.species_inputs or self.config.mock_name or self.config.taxid_inputs):
            return

        resolver = SpeciesResolver()
        resolved_genomes = []
        abundances = []

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
            for taxid in (self.config.taxid_inputs or []):
                ref = resolver.resolve_taxid(taxid)
                if ref is None:
                    raise ValueError(f"Could not resolve taxid: {taxid}")

                genome_path = download_genome(ref, resolver.cache)
                resolved_genomes.append(genome_path)

            # Set abundances
            if self.config.abundances:
                abundances = self.config.abundances
            else:
                # Equal abundances
                n = len(resolved_genomes)
                abundances = [1.0 / n] * n

        # Update config with resolved genomes
        object.__setattr__(self.config, "genome_inputs", resolved_genomes)
        object.__setattr__(self.config, "_resolved_abundances", abundances)

# Call from __init__ before other setup:
        self._resolve_species_inputs()
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_simulator_species.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add nanopore_simulator/core/simulator.py tests/test_simulator_species.py
git commit -m "feat(simulator): integrate species resolution into simulation workflow"
```

---

## Task 12: Download Subcommand

**Files:**
- Modify: `nanopore_simulator/cli/main.py`
- Test: `tests/test_cli_download.py`

**Step 1: Write failing test**

```python
# tests/test_cli_download.py
"""Tests for download subcommand"""

import pytest
from unittest.mock import patch, MagicMock
import sys

from nanopore_simulator.cli.main import main


class TestDownloadCommand:

    def test_download_species(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            sys, "argv",
            ["nanorunner", "download", "--species", "Escherichia coli"]
        )
        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve.return_value = MagicMock(accession="GCF_000005845.2")

            with patch("nanopore_simulator.cli.main.download_genome") as mock_dl:
                mock_dl.return_value = tmp_path / "genome.fna.gz"
                result = main()
                assert result == 0
                mock_dl.assert_called_once()

    def test_download_mock(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            sys, "argv",
            ["nanorunner", "download", "--mock", "quick_3species"]
        )
        with patch("nanopore_simulator.cli.main.SpeciesResolver") as mock_cls:
            mock_resolver = MagicMock()
            mock_cls.return_value = mock_resolver
            mock_resolver.resolve.return_value = MagicMock(accession="GCF_000005845.2")

            with patch("nanopore_simulator.cli.main.download_genome") as mock_dl:
                mock_dl.return_value = tmp_path / "genome.fna.gz"
                result = main()
                assert result == 0
                # Should download 3 genomes
                assert mock_dl.call_count == 3

    def test_download_requires_species_or_mock(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["nanorunner", "download"])
        with pytest.raises(SystemExit):
            main()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_download.py -v`
Expected: FAIL with "unrecognized arguments: download"

**Step 3: Write minimal implementation**

```python
# Modify nanopore_simulator/cli/main.py

# Add imports:
from ..core.species import SpeciesResolver, download_genome, GenomeRef

# Add subparsers after main parser creation:
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Download subcommand
    download_parser = subparsers.add_parser(
        "download",
        help="Pre-download genomes for offline use",
    )
    download_parser.add_argument(
        "--species",
        type=str,
        nargs="+",
        help="Species names to download",
    )
    download_parser.add_argument(
        "--mock",
        type=str,
        help="Mock community to download genomes for",
    )
    download_parser.add_argument(
        "--taxid",
        type=int,
        nargs="+",
        help="NCBI taxonomy IDs to download",
    )

# Add handler for download command:
    if args.command == "download":
        return download_command(args)

# Add download_command function:
def download_command(args) -> int:
    """Download genomes for offline use"""
    if not (args.species or args.mock or args.taxid):
        print("Error: Must specify --species, --mock, or --taxid")
        return 1

    resolver = SpeciesResolver()
    genomes_to_download = []

    if args.mock:
        mock = get_mock_community(args.mock)
        if mock is None:
            print(f"Error: Unknown mock community: {args.mock}")
            return 1
        for org in mock.organisms:
            if org.accession:
                ref = GenomeRef(
                    name=org.name,
                    accession=org.accession,
                    source=org.resolver,
                    domain="eukaryota" if org.resolver == "ncbi" else "bacteria",
                )
            else:
                ref = resolver.resolve(org.name)
            if ref:
                genomes_to_download.append((org.name, ref))

    if args.species:
        for species in args.species:
            ref = resolver.resolve(species)
            if ref:
                genomes_to_download.append((species, ref))
            else:
                print(f"Warning: Could not resolve: {species}")

    if args.taxid:
        for taxid in args.taxid:
            ref = resolver.resolve_taxid(taxid)
            if ref:
                genomes_to_download.append((f"taxid:{taxid}", ref))
            else:
                print(f"Warning: Could not resolve taxid: {taxid}")

    if not genomes_to_download:
        print("No genomes to download")
        return 1

    print(f"Downloading {len(genomes_to_download)} genome(s)...")
    for name, ref in genomes_to_download:
        try:
            path = download_genome(ref, resolver.cache)
            print(f"  Downloaded: {name} -> {path}")
        except Exception as e:
            print(f"  Failed: {name} - {e}")

    print("Download complete")
    return 0
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli_download.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add nanopore_simulator/cli/main.py tests/test_cli_download.py
git commit -m "feat(cli): add download subcommand for pre-fetching genomes"
```

---

## Task 13: Integration Test

**Files:**
- Create: `tests/test_species_integration.py`

**Step 1: Write integration test**

```python
# tests/test_species_integration.py
"""Integration tests for species-based generation (requires network)"""

import pytest
from pathlib import Path

from nanopore_simulator.core.config import SimulationConfig
from nanopore_simulator.core.simulator import NanoporeSimulator
from nanopore_simulator.core.species import SpeciesResolver, NCBIResolver


# Skip if datasets CLI not available
def _datasets_available() -> bool:
    return NCBIResolver().is_available()


skip_no_datasets = pytest.mark.skipif(
    not _datasets_available(),
    reason="NCBI datasets CLI not available",
)


@pytest.mark.slow
@pytest.mark.practical
@skip_no_datasets
class TestSpeciesIntegration:

    def test_quick_3species_pure(self, tmp_path):
        """Generate pure samples from quick_3species mock"""
        config = SimulationConfig(
            target_dir=tmp_path / "output",
            operation="generate",
            mock_name="quick_3species",
            sample_type="pure",
            read_count=10,
            reads_per_file=10,
            interval=0.0,
        )
        sim = NanoporeSimulator(config, enable_monitoring=False)
        sim.run_simulation()

        # Should have 3 barcode directories
        barcodes = list((tmp_path / "output").glob("barcode*"))
        assert len(barcodes) == 3

    def test_species_by_name(self, tmp_path):
        """Resolve and generate from species name"""
        config = SimulationConfig(
            target_dir=tmp_path / "output",
            operation="generate",
            species_inputs=["Escherichia coli"],
            sample_type="pure",
            read_count=10,
            reads_per_file=10,
            interval=0.0,
        )
        sim = NanoporeSimulator(config, enable_monitoring=False)
        sim.run_simulation()

        fastq_files = list((tmp_path / "output").rglob("*.fastq*"))
        assert len(fastq_files) >= 1
```

**Step 2: Run test (if datasets available)**

Run: `pytest tests/test_species_integration.py -v -m "slow and practical"`
Expected: PASS if datasets CLI installed, SKIP otherwise

**Step 3: Commit**

```bash
git add tests/test_species_integration.py
git commit -m "test: add integration tests for species-based generation"
```

---

## Task 14: Update Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/quickstart.md`

**Step 1: Update README.md**

Add section after existing generation documentation:

```markdown
### Species and Mock Community Generation

Generate samples from species names or preset mock communities:

```bash
# Generate from species names (resolves via GTDB/NCBI)
nanorunner --species "Escherichia coli" "Staphylococcus aureus" /output

# Use a preset mock community
nanorunner --mock zymo_d6300 /output

# Pure samples (each species in separate barcode)
nanorunner --species "E. coli" "S. aureus" --sample-type pure /output

# Mixed samples with custom abundances
nanorunner --species "E. coli" "S. aureus" --sample-type mixed --abundances 0.7 0.3 /output

# List available mock communities
nanorunner --list-mocks

# Pre-download genomes for offline use
nanorunner download --mock zymo_d6300
```
```

**Step 2: Commit documentation**

```bash
git add README.md docs/quickstart.md
git commit -m "docs: add species and mock community generation documentation"
```

---

## Task 15: Final Integration Test and Cleanup

**Step 1: Run full test suite**

```bash
pytest -m "not slow" -v
```

**Step 2: Run lint and type checks**

```bash
black nanopore_simulator/ tests/
mypy nanopore_simulator/
flake8 nanopore_simulator/
```

**Step 3: Final commit**

```bash
git add -A
git commit -m "chore: lint and format species/mock implementation"
```

---

## Summary

This plan implements species lookup and mock community support in 15 tasks:

1. **Tasks 1-2**: GenomeRef and GenomeCache data structures
2. **Tasks 3-4**: MockOrganism, MockCommunity, and built-in mocks
3. **Tasks 5-7**: GTDBIndex, NCBIResolver, SpeciesResolver
4. **Task 8**: Genome download with caching
5. **Task 9**: SimulationConfig updates
6. **Tasks 10-12**: CLI integration (arguments + download subcommand)
7. **Tasks 13-15**: Integration tests, documentation, cleanup

Each task follows TDD with failing test first, minimal implementation, then commit.
