# Expanded Mock Communities Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add ATCC mock communities (MSA-1002, MSA-1003), Zymo log distribution (D6310), and case-insensitive alias support.

**Architecture:** Extend `mocks.py` with new organism definitions, add `MOCK_ALIASES` dict, modify `get_mock_community()` for case-insensitive alias resolution, update `list_mock_communities()` to show aliases.

**Tech Stack:** Python 3.9+, existing nanorunner mock infrastructure.

---

## Task 1: Add MOCK_ALIASES and Update get_mock_community()

**Files:**
- Modify: `nanopore_simulator/core/mocks.py`
- Test: `tests/test_mocks.py`

**Step 1: Write failing test for case-insensitive lookup**

```python
# Add to tests/test_mocks.py

class TestMockAliasesAndCaseInsensitivity:

    def test_case_insensitive_lookup(self):
        """Mock lookup should be case-insensitive."""
        mock1 = get_mock_community("zymo_d6300")
        mock2 = get_mock_community("ZYMO_D6300")
        mock3 = get_mock_community("Zymo_D6300")
        assert mock1 is not None
        assert mock1 == mock2 == mock3

    def test_alias_d6305_resolves(self):
        """D6305 should resolve to zymo_d6300."""
        mock = get_mock_community("d6305")
        assert mock is not None
        assert mock.name == "zymo_d6300"

    def test_alias_d6306_resolves(self):
        """D6306 should resolve to zymo_d6300."""
        mock = get_mock_community("D6306")  # Test case-insensitivity too
        assert mock is not None
        assert mock.name == "zymo_d6300"

    def test_alias_with_zymo_prefix(self):
        """zymo_d6305 should also resolve to zymo_d6300."""
        mock = get_mock_community("zymo_d6305")
        assert mock is not None
        assert mock.name == "zymo_d6300"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_mocks.py::TestMockAliasesAndCaseInsensitivity -v`
Expected: FAIL (case-insensitive lookup not implemented)

**Step 3: Write minimal implementation**

```python
# Add to nanopore_simulator/core/mocks.py after BUILTIN_MOCKS

# Aliases for product codes (lowercase keys for case-insensitive lookup)
MOCK_ALIASES: Dict[str, str] = {
    "d6305": "zymo_d6300",
    "d6306": "zymo_d6300",
    "zymo_d6305": "zymo_d6300",
    "zymo_d6306": "zymo_d6300",
}


def get_mock_community(name: str) -> Optional[MockCommunity]:
    """Get a mock community by name.

    Supports case-insensitive lookup and aliases (e.g., D6305 -> zymo_d6300).

    Args:
        name: The identifier of the mock community to retrieve.

    Returns:
        The MockCommunity if found, None otherwise.
    """
    normalized = name.lower()
    # Check aliases first
    if normalized in MOCK_ALIASES:
        normalized = MOCK_ALIASES[normalized]
    return BUILTIN_MOCKS.get(normalized)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_mocks.py::TestMockAliasesAndCaseInsensitivity -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add nanopore_simulator/core/mocks.py tests/test_mocks.py
git commit -m "feat(mocks): add case-insensitive lookup and D6305/D6306 aliases"
```

---

## Task 2: Add Zymo D6310 Log Distribution Mock

**Files:**
- Modify: `nanopore_simulator/core/mocks.py`
- Test: `tests/test_mocks.py`

**Step 1: Write failing test**

```python
# Add to tests/test_mocks.py

class TestZymoD6310:

    def test_zymo_d6310_exists(self):
        """D6310 mock should exist."""
        mock = get_mock_community("zymo_d6310")
        assert mock is not None
        assert mock.name == "zymo_d6310"

    def test_zymo_d6310_has_10_organisms(self):
        """D6310 should have same 10 organisms as D6300."""
        mock = get_mock_community("zymo_d6310")
        assert len(mock.organisms) == 10

    def test_zymo_d6310_log_distribution(self):
        """D6310 abundances should span multiple orders of magnitude."""
        mock = get_mock_community("zymo_d6310")
        abundances = [org.abundance for org in mock.organisms]
        max_abundance = max(abundances)
        min_abundance = min(abundances)
        # Should span at least 4 orders of magnitude
        assert max_abundance / min_abundance >= 10000

    def test_alias_d6310_resolves(self):
        """d6310 alias should resolve to zymo_d6310."""
        mock = get_mock_community("d6310")
        assert mock is not None
        assert mock.name == "zymo_d6310"

    def test_alias_d6311_resolves(self):
        """D6311 should resolve to zymo_d6310."""
        mock = get_mock_community("D6311")
        assert mock is not None
        assert mock.name == "zymo_d6310"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_mocks.py::TestZymoD6310 -v`
Expected: FAIL (zymo_d6310 not defined)

**Step 3: Write minimal implementation**

```python
# Add to nanopore_simulator/core/mocks.py

# Zymo D6310 Log Distribution - same species as D6300, log-distributed abundances
_ZYMO_D6310_ORGANISMS = [
    MockOrganism("Listeria monocytogenes", "gtdb", 0.891),
    MockOrganism("Pseudomonas aeruginosa", "gtdb", 0.089),
    MockOrganism("Bacillus subtilis", "gtdb", 0.0089),
    MockOrganism("Escherichia coli", "gtdb", 0.00089),
    MockOrganism("Salmonella enterica", "gtdb", 0.000089),
    MockOrganism("Lactobacillus fermentum", "gtdb", 0.0000089),
    MockOrganism("Enterococcus faecalis", "gtdb", 0.00000089),
    MockOrganism("Staphylococcus aureus", "gtdb", 0.000000089),
    # Fungi - use NCBI resolver
    MockOrganism("Saccharomyces cerevisiae", "ncbi", 0.0002, "GCF_000146045.2"),
    MockOrganism("Cryptococcus neoformans", "ncbi", 0.00002, "GCF_000149245.1"),
]

# Add to BUILTIN_MOCKS dict:
    "zymo_d6310": MockCommunity(
        name="zymo_d6310",
        description="Zymo D6310 Log Distribution - 8 bacteria + 2 yeasts",
        organisms=_ZYMO_D6310_ORGANISMS,
    ),

# Add to MOCK_ALIASES:
    "d6310": "zymo_d6310",
    "d6311": "zymo_d6310",
    "zymo_d6311": "zymo_d6310",
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_mocks.py::TestZymoD6310 -v`
Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add nanopore_simulator/core/mocks.py tests/test_mocks.py
git commit -m "feat(mocks): add Zymo D6310 log distribution mock with aliases"
```

---

## Task 3: Add ATCC MSA-1002 Even Mix Mock

**Files:**
- Modify: `nanopore_simulator/core/mocks.py`
- Test: `tests/test_mocks.py`

**Step 1: Write failing test**

```python
# Add to tests/test_mocks.py

class TestATCCMSA1002:

    def test_atcc_msa1002_exists(self):
        """ATCC MSA-1002 mock should exist."""
        mock = get_mock_community("atcc_msa1002")
        assert mock is not None
        assert mock.name == "atcc_msa1002"

    def test_atcc_msa1002_has_20_organisms(self):
        """MSA-1002 should have 20 bacterial strains."""
        mock = get_mock_community("atcc_msa1002")
        assert len(mock.organisms) == 20

    def test_atcc_msa1002_even_distribution(self):
        """MSA-1002 should have even 5% distribution."""
        mock = get_mock_community("atcc_msa1002")
        for org in mock.organisms:
            assert org.abundance == 0.05

    def test_atcc_msa1002_all_gtdb_resolver(self):
        """MSA-1002 organisms should use GTDB resolver."""
        mock = get_mock_community("atcc_msa1002")
        for org in mock.organisms:
            assert org.resolver == "gtdb"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_mocks.py::TestATCCMSA1002 -v`
Expected: FAIL (atcc_msa1002 not defined)

**Step 3: Write minimal implementation**

```python
# Add to nanopore_simulator/core/mocks.py

# ATCC MSA-1002 - 20 Strain Even Mix (5% each)
_ATCC_MSA1002_ORGANISMS = [
    MockOrganism("Acinetobacter baumannii", "gtdb", 0.05),
    MockOrganism("Bacillus pacificus", "gtdb", 0.05),
    MockOrganism("Phocaeicola vulgatus", "gtdb", 0.05),
    MockOrganism("Bifidobacterium adolescentis", "gtdb", 0.05),
    MockOrganism("Clostridium beijerinckii", "gtdb", 0.05),
    MockOrganism("Cutibacterium acnes", "gtdb", 0.05),
    MockOrganism("Deinococcus radiodurans", "gtdb", 0.05),
    MockOrganism("Enterococcus faecalis", "gtdb", 0.05),
    MockOrganism("Escherichia coli", "gtdb", 0.05),
    MockOrganism("Helicobacter pylori", "gtdb", 0.05),
    MockOrganism("Lactobacillus gasseri", "gtdb", 0.05),
    MockOrganism("Neisseria meningitidis", "gtdb", 0.05),
    MockOrganism("Porphyromonas gingivalis", "gtdb", 0.05),
    MockOrganism("Pseudomonas paraeruginosa", "gtdb", 0.05),
    MockOrganism("Cereibacter sphaeroides", "gtdb", 0.05),
    MockOrganism("Schaalia odontolytica", "gtdb", 0.05),
    MockOrganism("Staphylococcus aureus", "gtdb", 0.05),
    MockOrganism("Staphylococcus epidermidis", "gtdb", 0.05),
    MockOrganism("Streptococcus agalactiae", "gtdb", 0.05),
    MockOrganism("Streptococcus mutans", "gtdb", 0.05),
]

# Add to BUILTIN_MOCKS dict:
    "atcc_msa1002": MockCommunity(
        name="atcc_msa1002",
        description="ATCC MSA-1002 20-strain even mix (5% each)",
        organisms=_ATCC_MSA1002_ORGANISMS,
    ),
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_mocks.py::TestATCCMSA1002 -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add nanopore_simulator/core/mocks.py tests/test_mocks.py
git commit -m "feat(mocks): add ATCC MSA-1002 20-strain even mix mock"
```

---

## Task 4: Add ATCC MSA-1003 Staggered Mix Mock

**Files:**
- Modify: `nanopore_simulator/core/mocks.py`
- Test: `tests/test_mocks.py`

**Step 1: Write failing test**

```python
# Add to tests/test_mocks.py

class TestATCCMSA1003:

    def test_atcc_msa1003_exists(self):
        """ATCC MSA-1003 mock should exist."""
        mock = get_mock_community("atcc_msa1003")
        assert mock is not None
        assert mock.name == "atcc_msa1003"

    def test_atcc_msa1003_has_20_organisms(self):
        """MSA-1003 should have 20 bacterial strains."""
        mock = get_mock_community("atcc_msa1003")
        assert len(mock.organisms) == 20

    def test_atcc_msa1003_staggered_distribution(self):
        """MSA-1003 should have staggered distribution (0.02% to 18%)."""
        mock = get_mock_community("atcc_msa1003")
        abundances = sorted([org.abundance for org in mock.organisms])
        # Check range spans from ~0.02% to ~18%
        assert abundances[0] < 0.001  # Smallest should be < 0.1%
        assert abundances[-1] > 0.1   # Largest should be > 10%

    def test_atcc_msa1003_log_spread(self):
        """MSA-1003 abundances should span ~3 orders of magnitude."""
        mock = get_mock_community("atcc_msa1003")
        abundances = [org.abundance for org in mock.organisms]
        max_abundance = max(abundances)
        min_abundance = min(abundances)
        assert max_abundance / min_abundance >= 100
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_mocks.py::TestATCCMSA1003 -v`
Expected: FAIL (atcc_msa1003 not defined)

**Step 3: Write minimal implementation**

```python
# Add to nanopore_simulator/core/mocks.py

# ATCC MSA-1003 - 20 Strain Staggered Mix (0.02% to 18%)
_ATCC_MSA1003_ORGANISMS = [
    # High abundance (18%)
    MockOrganism("Escherichia coli", "gtdb", 0.18),
    MockOrganism("Porphyromonas gingivalis", "gtdb", 0.18),
    MockOrganism("Cereibacter sphaeroides", "gtdb", 0.18),
    MockOrganism("Staphylococcus epidermidis", "gtdb", 0.18),
    MockOrganism("Streptococcus mutans", "gtdb", 0.18),
    # Medium abundance (1.8%)
    MockOrganism("Bacillus pacificus", "gtdb", 0.018),
    MockOrganism("Clostridium beijerinckii", "gtdb", 0.018),
    MockOrganism("Pseudomonas paraeruginosa", "gtdb", 0.018),
    MockOrganism("Staphylococcus aureus", "gtdb", 0.018),
    MockOrganism("Streptococcus agalactiae", "gtdb", 0.018),
    # Low abundance (0.18%)
    MockOrganism("Acinetobacter baumannii", "gtdb", 0.0018),
    MockOrganism("Cutibacterium acnes", "gtdb", 0.0018),
    MockOrganism("Helicobacter pylori", "gtdb", 0.0018),
    MockOrganism("Lactobacillus gasseri", "gtdb", 0.0018),
    MockOrganism("Neisseria meningitidis", "gtdb", 0.0018),
    # Very low abundance (0.02%)
    MockOrganism("Phocaeicola vulgatus", "gtdb", 0.0002),
    MockOrganism("Bifidobacterium adolescentis", "gtdb", 0.0002),
    MockOrganism("Deinococcus radiodurans", "gtdb", 0.0002),
    MockOrganism("Enterococcus faecalis", "gtdb", 0.0002),
    MockOrganism("Schaalia odontolytica", "gtdb", 0.0002),
]

# Add to BUILTIN_MOCKS dict:
    "atcc_msa1003": MockCommunity(
        name="atcc_msa1003",
        description="ATCC MSA-1003 20-strain staggered mix (0.02%-18%)",
        organisms=_ATCC_MSA1003_ORGANISMS,
    ),
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_mocks.py::TestATCCMSA1003 -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add nanopore_simulator/core/mocks.py tests/test_mocks.py
git commit -m "feat(mocks): add ATCC MSA-1003 20-strain staggered mix mock"
```

---

## Task 5: Update list_mock_communities() to Show Aliases

**Files:**
- Modify: `nanopore_simulator/core/mocks.py`
- Test: `tests/test_mocks.py`

**Step 1: Write failing test**

```python
# Add to tests/test_mocks.py

class TestListMocksWithAliases:

    def test_list_includes_primary_mocks(self):
        """list_mock_communities should include all primary mocks."""
        mocks = list_mock_communities()
        assert "zymo_d6300" in mocks
        assert "zymo_d6310" in mocks
        assert "atcc_msa1002" in mocks
        assert "atcc_msa1003" in mocks

    def test_list_includes_aliases(self):
        """list_mock_communities should include aliases."""
        mocks = list_mock_communities()
        assert "d6305" in mocks
        assert "d6306" in mocks
        assert "d6310" in mocks
        assert "d6311" in mocks

    def test_alias_descriptions_indicate_target(self):
        """Alias descriptions should indicate they are aliases."""
        mocks = list_mock_communities()
        assert "alias" in mocks["d6305"].lower()
        assert "zymo_d6300" in mocks["d6305"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_mocks.py::TestListMocksWithAliases -v`
Expected: FAIL (aliases not in list output)

**Step 3: Write minimal implementation**

```python
# Replace list_mock_communities in nanopore_simulator/core/mocks.py

def list_mock_communities() -> Dict[str, str]:
    """List all available mock communities with descriptions.

    Returns:
        Dictionary mapping mock community names to their descriptions.
        Includes aliases with "(alias for X)" notation.
    """
    result = {name: mock.description for name, mock in BUILTIN_MOCKS.items()}
    # Add aliases
    for alias, target in MOCK_ALIASES.items():
        if target in BUILTIN_MOCKS:
            result[alias] = f"(alias for {target})"
    return result
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_mocks.py::TestListMocksWithAliases -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add nanopore_simulator/core/mocks.py tests/test_mocks.py
git commit -m "feat(mocks): update list_mock_communities to show aliases"
```

---

## Task 6: Update CLI --list-mocks Output Format

**Files:**
- Modify: `nanopore_simulator/cli/main.py`
- Test: `tests/test_cli_species.py`

**Step 1: Write failing test**

```python
# Add to tests/test_cli_species.py

class TestListMocksOutput:

    def test_list_mocks_shows_aliases_section(self, monkeypatch, capsys):
        """--list-mocks should show aliases in separate section."""
        monkeypatch.setattr(sys, "argv", ["nanorunner", "--list-mocks"])
        result = main()
        assert result == 0
        captured = capsys.readouterr()
        assert "Aliases:" in captured.out or "alias" in captured.out.lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_species.py::TestListMocksOutput -v`
Expected: FAIL (no Aliases section)

**Step 3: Write minimal implementation**

```python
# Modify list_mocks_command in nanopore_simulator/cli/main.py

def list_mocks_command() -> int:
    """List available mock communities."""
    from ..core.mocks import BUILTIN_MOCKS, MOCK_ALIASES

    print("Available Mock Communities:")
    print("=" * 60)
    for name, mock in sorted(BUILTIN_MOCKS.items()):
        print(f"  {name:20} - {mock.description}")

    if MOCK_ALIASES:
        print("\nAliases:")
        print("-" * 60)
        # Group aliases by target
        targets: Dict[str, List[str]] = {}
        for alias, target in MOCK_ALIASES.items():
            if target not in targets:
                targets[target] = []
            targets[target].append(alias)
        for target, aliases in sorted(targets.items()):
            alias_str = ", ".join(sorted(aliases))
            print(f"  {alias_str:30} -> {target}")

    return 0
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli_species.py::TestListMocksOutput -v`
Expected: PASS

**Step 5: Commit**

```bash
git add nanopore_simulator/cli/main.py tests/test_cli_species.py
git commit -m "feat(cli): improve --list-mocks output with grouped aliases"
```

---

## Task 7: Final Integration Test and Cleanup

**Step 1: Run full test suite**

```bash
pytest -m "not slow" -v
```

Verify all tests pass.

**Step 2: Run lint and format**

```bash
black nanopore_simulator/ tests/
```

**Step 3: Verify mock count**

```bash
nanorunner --list-mocks
```

Expected output shows 7 primary mocks + aliases.

**Step 4: Final commit if needed**

```bash
git add -A
git commit -m "style: apply black formatting"
```
