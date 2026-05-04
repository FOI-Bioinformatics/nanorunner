# Expanded Mock Communities Design

**Date**: 2026-02-05
**Status**: Approved
**Purpose**: Add ATCC mock communities and Zymo log distribution variants with alias support

## Overview

Expand the built-in mock communities to include ATCC standards (MSA-1002, MSA-1003) and Zymo log distribution variants (D6310/D6311). Add case-insensitive alias support so product codes like D6305, D6306 resolve to existing mocks.

## New Mock Communities

### ATCC MSA-1002 (20 Strain Even Mix)

All 20 bacteria at 5% each:

| Species | Resolver | Abundance |
|---------|----------|-----------|
| Acinetobacter baumannii | gtdb | 5% |
| Bacillus pacificus | gtdb | 5% |
| Phocaeicola vulgatus | gtdb | 5% |
| Bifidobacterium adolescentis | gtdb | 5% |
| Clostridium beijerinckii | gtdb | 5% |
| Cutibacterium acnes | gtdb | 5% |
| Deinococcus radiodurans | gtdb | 5% |
| Enterococcus faecalis | gtdb | 5% |
| Escherichia coli | gtdb | 5% |
| Helicobacter pylori | gtdb | 5% |
| Lactobacillus gasseri | gtdb | 5% |
| Neisseria meningitidis | gtdb | 5% |
| Porphyromonas gingivalis | gtdb | 5% |
| Pseudomonas paraeruginosa | gtdb | 5% |
| Cereibacter sphaeroides | gtdb | 5% |
| Schaalia odontolytica | gtdb | 5% |
| Staphylococcus aureus | gtdb | 5% |
| Staphylococcus epidermidis | gtdb | 5% |
| Streptococcus agalactiae | gtdb | 5% |
| Streptococcus mutans | gtdb | 5% |

### ATCC MSA-1003 (20 Strain Staggered Mix)

Same 20 bacteria with log-distributed abundances (0.02% to 18%):

| Species | Resolver | Abundance |
|---------|----------|-----------|
| Escherichia coli | gtdb | 18.0% |
| Porphyromonas gingivalis | gtdb | 18.0% |
| Cereibacter sphaeroides | gtdb | 18.0% |
| Staphylococcus epidermidis | gtdb | 18.0% |
| Streptococcus mutans | gtdb | 18.0% |
| Bacillus pacificus | gtdb | 1.8% |
| Clostridium beijerinckii | gtdb | 1.8% |
| Pseudomonas paraeruginosa | gtdb | 1.8% |
| Staphylococcus aureus | gtdb | 1.8% |
| Streptococcus agalactiae | gtdb | 1.8% |
| Acinetobacter baumannii | gtdb | 0.18% |
| Cutibacterium acnes | gtdb | 0.18% |
| Helicobacter pylori | gtdb | 0.18% |
| Lactobacillus gasseri | gtdb | 0.18% |
| Neisseria meningitidis | gtdb | 0.18% |
| Phocaeicola vulgatus | gtdb | 0.02% |
| Bifidobacterium adolescentis | gtdb | 0.02% |
| Deinococcus radiodurans | gtdb | 0.02% |
| Enterococcus faecalis | gtdb | 0.02% |
| Schaalia odontolytica | gtdb | 0.02% |

### Zymo D6310 (Log Distribution)

Same 10 species as D6300 with log-distributed abundances:

| Species | Resolver | Abundance |
|---------|----------|-----------|
| Listeria monocytogenes | gtdb | 89.1% |
| Pseudomonas aeruginosa | gtdb | 8.9% |
| Bacillus subtilis | gtdb | 0.89% |
| Escherichia coli | gtdb | 0.089% |
| Salmonella enterica | gtdb | 0.0089% |
| Lactobacillus fermentum | gtdb | 0.00089% |
| Enterococcus faecalis | gtdb | 0.000089% |
| Staphylococcus aureus | gtdb | 0.0000089% |
| Saccharomyces cerevisiae | ncbi | 0.02% |
| Cryptococcus neoformans | ncbi | 0.002% |

## Alias System

Case-insensitive aliases mapping product codes to mock names:

| Alias | Target |
|-------|--------|
| d6305 | zymo_d6300 |
| d6306 | zymo_d6300 |
| zymo_d6305 | zymo_d6300 |
| zymo_d6306 | zymo_d6300 |
| d6310 | zymo_d6310 |
| d6311 | zymo_d6310 |
| zymo_d6311 | zymo_d6310 |

## Implementation

### Modified Functions

**get_mock_community(name: str)**
```python
def get_mock_community(name: str) -> Optional[MockCommunity]:
    """Get a mock community by name (case-insensitive, supports aliases)."""
    normalized = name.lower()
    # Check aliases first
    if normalized in MOCK_ALIASES:
        normalized = MOCK_ALIASES[normalized]
    return BUILTIN_MOCKS.get(normalized)
```

**list_mock_communities()**
- Include aliases in output with "(alias for X)" notation

### Files to Modify

| File | Changes |
|------|---------|
| `nanopore_simulator/core/mocks.py` | Add organisms, MOCK_ALIASES, update functions |
| `tests/test_mocks.py` | Add tests for new mocks and aliases |

### Test Cases

1. New mock existence tests (zymo_d6310, atcc_msa1002, atcc_msa1003)
2. Organism count verification (10, 20, 20)
3. Abundance distribution tests (even vs log)
4. Alias resolution tests (d6305 -> zymo_d6300)
5. Case-insensitivity tests (D6300 == d6300)
6. List mocks includes aliases

## Sources

- [ATCC MSA-1002](https://www.atcc.org/products/msa-1002)
- [ATCC MSA-1003](https://www.atcc.org/products/msa-1003)
- [Zymo D6305/D6306 Protocol](https://files.zymoresearch.com/protocols/_d6305_d6306_zymobiomics_microbial_community_dna_standard.pdf)
- [Zymo Microbial Community Standards](https://www.zymoresearch.com/collections/zymobiomics-microbial-community-standards)
