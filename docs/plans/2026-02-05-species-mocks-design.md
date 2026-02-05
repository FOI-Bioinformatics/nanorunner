# Species Lookup and Mock Community Support

**Date**: 2026-02-05
**Status**: Draft
**Purpose**: Enable sample generation from species names and preset mock communities

## Overview

This design adds the ability to generate simulated nanopore reads by specifying species names (resolved via GTDB/NCBI) or preset mock communities (Zymo, ATCC, synthetic). Users can create pure samples (each species in separate barcodes) or mixed samples (interleaved reads simulating metagenomic samples).

Primary use case: Pipeline testing with known ground truth communities.

## Core Concepts

### Sample Types

Controlled by `--sample-type`:

- **Pure samples** (`--sample-type pure`): Each species produces reads in its own barcode directory. A 3-species run creates `barcode01/`, `barcode02/`, `barcode03/`.

- **Mixed samples** (`--sample-type mixed`): All species' reads interleave into shared files in target root (singleplex) or single barcode (multiplex).

**Default inference**:
- `--mock` defaults to `mixed` (mock communities are typically mixed)
- Multiple `--species` defaults to `pure` (separate barcodes for ground truth)
- Single `--species` defaults to `pure` singleplex

### Species Resolution (Domain-Aware)

Resolution follows a domain-aware strategy:

1. **Bacteria/Archaea**: GTDB lookup via local index, then representative genome, then NCBI accession
2. **Eukaryotes (fungi, etc.)**: NCBI taxonomy to RefSeq reference genome
3. **Fallback**: Direct NCBI taxid via `--taxid` for edge cases

Preset mocks encode the correct resolution path per organism. For custom species, the system queries GTDB first; if not found, falls back to NCBI taxonomy.

### Abundance Control

For mixed samples:
- Preset mocks use documented compositions (e.g., Zymo D6300 specific percentages)
- Custom species default to equal abundances
- Override with `--abundances 0.5 0.3 0.2` (must sum to 1.0, order matches species order)

## Architecture

### New Module: `nanopore_simulator/core/species.py`

Handles species resolution and genome acquisition:

```
SpeciesResolver
├── GTDBResolver      # Local index + API fallback for bacteria/archaea
├── NCBIResolver      # RefSeq lookup for eukaryotes, taxid fallback
└── GenomeCache       # ~/.nanorunner/genomes/ management
```

Key methods:
- `resolve(name: str) -> GenomeRef`: Returns accession + download URL + domain
- `download(ref: GenomeRef) -> Path`: Fetches genome, returns cached path
- `resolve_and_download(name: str) -> Path`: Convenience method

### New Module: `nanopore_simulator/core/mocks.py`

Defines preset mock communities:

```python
@dataclass
class MockOrganism:
    name: str                    # "Escherichia coli"
    resolver: str                # "gtdb" or "ncbi"
    accession: Optional[str]     # Override for specific strain
    abundance: float             # Proportion in community

@dataclass
class MockCommunity:
    name: str                    # "zymo_d6300"
    description: str
    organisms: List[MockOrganism]
```

Built-in mocks stored as `BUILTIN_MOCKS` dict, similar to `BUILTIN_PROFILES`.

### Cache Structure

```
~/.nanorunner/
├── genomes/
│   ├── gtdb/
│   │   └── GCF_000005845.2.fna.gz    # E. coli
│   └── ncbi/
│       └── GCF_000146045.2.fna.gz    # S. cerevisiae
└── indexes/
    └── gtdb_species_r220.tsv         # Species-to-accession mapping
```

## CLI Interface

### New Arguments

```bash
# Species by name (GTDB/NCBI resolved)
nanorunner --species "Escherichia coli" "Staphylococcus aureus" /output

# Preset mock community
nanorunner --mock zymo_d6300 /output

# Mixed sample with custom abundances
nanorunner --species "E. coli" "S. aureus" --sample-type mixed --abundances 0.7 0.3 /output

# Pure samples (each species in own barcode)
nanorunner --species "E. coli" "S. aureus" --sample-type pure /output

# Direct NCBI taxid fallback
nanorunner --taxid 562 4932 /output

# Pre-download genomes for offline use
nanorunner download --mock zymo_d6300
nanorunner download --species "Bacillus subtilis"
```

### Argument Reference

| Argument | Description |
|----------|-------------|
| `--species` | One or more species names (quotes for multi-word) |
| `--mock` | Preset mock community name |
| `--taxid` | Direct NCBI taxonomy IDs (fallback) |
| `--sample-type` | `pure` or `mixed` (default inferred) |
| `--abundances` | Space-separated floats summing to 1.0 |
| `--list-mocks` | Show available mock communities |
| `--offline` | Use only cached genomes, no network requests |

### Mutual Exclusivity

- `--species`, `--mock`, `--taxid`, and `--genomes` are mutually exclusive
- `--abundances` only valid with `--species` or `--taxid` (mocks have built-in abundances)

## Built-in Mock Communities

### Zymo Standards

| Mock | Description | Composition |
|------|-------------|-------------|
| `zymo_d6300` | Standard (even) | 8 bacteria + 2 yeasts, equal DNA mass |
| `zymo_d6305` | Log distribution | Same 10 organisms, 10-fold abundance range |
| `zymo_d6306` | HMW DNA | High molecular weight version of D6300 |
| `zymo_d6310` | Gut microbiome | 21 gut-relevant strains |
| `zymo_d6311` | Skin microbiome | Skin-associated organisms |

### ATCC Standards

| Mock | Description | Composition |
|------|-------------|-------------|
| `atcc_msa1003` | 20 Strain Mix | Diverse bacterial mix for WGS |
| `atcc_msa2002` | Oral microbiome | Oral cavity organisms |

### Synthetic Quick-Test Mocks

| Mock | Description | Composition |
|------|-------------|-------------|
| `quick_3species` | Minimal test | E. coli, S. aureus, B. subtilis (equal) |
| `quick_gut5` | Simple gut | 5 common gut bacteria (equal) |
| `quick_pathogens` | Pathogen panel | 5 clinically relevant pathogens |
| `quick_soil5` | Soil sample | 5 common soil bacteria |

## Data Flow

### Resolution and Download

```
User Input                Resolution                    Download
---------------------------------------------------------------------------
--species "E. coli"  ->  GTDBResolver.resolve()    ->  GenomeCache.get()
                         |                              |
                         v                              v
                         GenomeRef(                     Check ~/.nanorunner/genomes/
                           accession=GCF_000005845.2,   +- Cached? Return path
                           domain="bacteria",           +- Missing? datasets download
                           source="gtdb"
                         )

--mock zymo_d6300    ->  Load MockCommunity         ->  Resolve each organism
                         |                              |
                         v                              v
                         [MockOrganism(...), ...]       Parallel downloads (optional)
```

### Generation Flow

1. Resolve all species/mock organisms to GenomeRefs
2. Download missing genomes to cache
3. Build manifest based on `--sample-type`:
   - **Pure mode**: genome1 -> barcode01/*.fastq, genome2 -> barcode02/*.fastq
   - **Mixed mode**: all genomes -> interleaved reads in shared files
4. Generate reads using existing backends (BuiltinGenerator/BadreadGenerator)
5. Apply timing model using existing infrastructure

### Abundance Handling in Mixed Mode

Total reads distributed proportionally. For 1000 reads with abundances `[0.7, 0.2, 0.1]`:
- 700 reads from genome1
- 200 reads from genome2
- 100 reads from genome3
- Interleaved into output files

## Error Handling

### Species Resolution Errors

| Scenario | Behavior |
|----------|----------|
| Species not in GTDB | Try NCBI taxonomy lookup |
| Species not in NCBI | Clear error with suggestions (fuzzy match) |
| Ambiguous name | List matching species, ask user to be specific |
| Network unavailable | Use cached genomes only, fail if missing |

### Download Errors

| Scenario | Behavior |
|----------|----------|
| NCBI datasets CLI missing | Error with installation instructions |
| Download fails (network) | Retry 3x with backoff, then fail with message |
| Corrupted download | Validate checksum, re-download if mismatch |
| Disk full | Fail early with space requirement estimate |

### Validation

| Check | When |
|-------|------|
| Abundances sum to 1.0 | Argument parsing |
| Abundance count matches species count | Argument parsing |
| All genomes downloadable | Before generation starts |
| Cache directory writable | On first download attempt |

## Implementation Scope

### New Files

| File | Purpose |
|------|---------|
| `nanopore_simulator/core/species.py` | SpeciesResolver, GTDBResolver, NCBIResolver, GenomeCache |
| `nanopore_simulator/core/mocks.py` | MockCommunity, MockOrganism, BUILTIN_MOCKS |
| `tests/test_species.py` | Species resolution unit tests |
| `tests/test_mocks.py` | Mock community tests |
| `tests/test_species_integration.py` | End-to-end with real downloads (marked slow) |

### Modified Files

| File | Changes |
|------|---------|
| `nanopore_simulator/cli/main.py` | Add `--species`, `--mock`, `--taxid`, `--sample-type`, `--abundances`, `--list-mocks`, `--offline`, `download` subcommand |
| `nanopore_simulator/core/config.py` | Add `species_inputs`, `mock_name`, `sample_type`, `abundances` fields |
| `nanopore_simulator/core/simulator.py` | Integrate species resolution before manifest creation |
| `nanopore_simulator/core/profiles.py` | Add mock-oriented generation profiles |

### External Dependencies

| Dependency | Purpose | Required? |
|------------|---------|-----------|
| `ncbi-datasets-cli` | Genome downloads | Yes (runtime) |
| `requests` | GTDB API fallback | Optional (for unlisted species) |

### Estimated Scope

- ~1500 lines new code
- ~200 lines modifications to existing files
