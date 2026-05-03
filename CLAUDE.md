# CLAUDE.md

Developer guidance for `nanorunner`, a nanopore sequencing run simulator used
to exercise watch-directory bioinformatics pipelines.

## Overview

`nanorunner` operates in two modes:

- **Replay**: copy or symlink existing FASTQ files from a source directory to a
  target directory at configurable intervals.
- **Generate**: produce simulated reads from genome FASTA files (or species
  names / mock community presets) and write them to the target directory.

Both modes preserve singleplex and multiplex (barcoded) layouts and apply one
of four timing models. Optional resource monitoring is provided by `psutil`.

**Current version:** 3.0.0
**Conda environment for development:** `nanorunner`

## Project conventions

The repository follows the conventions below. Apply them on every change.

- **Single source of truth for the version.** `__init__.py` is canonical.
  `pyproject.toml`, README, and CHANGELOG must match.
- **Flat package layout.** All source modules live in `nanopore_simulator/`
  with no subpackages.
- **Standard-library core.** External dependencies are restricted to optional
  extras (`enhanced`, `dev`); the replay + builtin generation paths must work
  without them.
- **Scientific tone.** Documentation describes capabilities and trade-offs.
  Avoid superlatives and unsupported quantitative claims.
- **Tests track features.** Every new CLI flag, config field, or backend ships
  with unit tests. CLI flags also need an entry in `examples/` or the README.
- **No orphaned files.** Each file in the repo is referenced from another file
  or the package entry points.

## Key commands

```bash
# Install in development mode
pip install -e .[enhanced,dev]

# Full test suite
pytest

# Subset
pytest -m "not slow"
pytest tests/test_cli.py
pytest tests/test_runner.py

# Coverage
pytest --cov=nanopore_simulator --cov-report=html --cov-report=term-missing

# Code quality
black nanopore_simulator/ tests/
mypy nanopore_simulator/
flake8 nanopore_simulator/

# CLI sanity checks
nanorunner --help
nanorunner check-deps
nanorunner list-profiles
nanorunner list-mocks
```

## Architecture

### Plan-Execute-Monitor pattern

The orchestrator decomposes work into three independent phases:

1. **Plan** (`manifest.py`) -- config in, list of `FileEntry` objects out.
2. **Execute** (`executor.py`) -- one `FileEntry` in, one file on disk out
   (copy, link, or generate).
3. **Monitor** (`monitoring.py`) -- progress tracking and display.

`runner.py` is a thin loop (~175 lines) that connects the phases and applies
timing delays between batches.

### Module layout

Flat layout under `nanopore_simulator/`. No subpackages.

**Orchestration**
- `runner.py` -- thin orchestrator
- `manifest.py` -- `FileEntry`, `build_replay_manifest()`, `build_generate_manifest()`, `distribute_reads()`
- `executor.py` -- `execute_entry()` dispatches to copy/link/generate

**Configuration**
- `config.py` -- `ReplayConfig` and `GenerateConfig` (frozen dataclasses with `__post_init__` validation)
- `profiles.py` -- preset bundles: `get_profile()`, `apply_profile()`, `get_recommendations()`

**Read generation**
- `generators.py` -- `ReadGenerator` ABC, `BuiltinGenerator` (random subsequences with log-normal lengths), `SubprocessGenerator` (badread / NanoSim wrapper)
- `species.py` -- name resolution via GTDB REST (bacteria, archaea) and NCBI Datasets CLI (eukaryotes), with local cache
- `mocks.py` -- `MockOrganism`, `MockCommunity`, built-in communities, aliases

**Infrastructure**
- `cli.py` -- Typer CLI
- `timing.py` -- timing model implementations and factory
- `monitoring.py` -- `ProgressMonitor` with optional resource tracking; `NullMonitor` for headless runs
- `detection.py` -- module-level singleplex / multiplex structure detection
- `adapters.py` -- pipeline validation registry (dict-based, no ABC)
- `deps.py` -- dependency probing with install hints
- `fastq.py` -- FASTQ I/O helpers

### Timing models

| Model      | Implementation                                                            |
|------------|---------------------------------------------------------------------------|
| Uniform    | Constant intervals.                                                       |
| Random     | Symmetric variation around the base interval (`random_factor`).           |
| Poisson    | Mixture of two exponential distributions; produces burst clusters.        |
| Adaptive   | Exponential intervals with the rate parameter drifting via EMA of past intervals. |

The Poisson and adaptive models are descriptive parameterisations; they have
not been calibrated against empirical sequencer output.

### Read generators

- `BuiltinGenerator`: random subsequences from FASTA with log-normal length
  distribution. No error model. No external dependencies. Produces an exact
  read count.
- `SubprocessGenerator`: unified wrapper for `badread` and `nanosim`.
- `auto`: tries `badread`, then `nanosim`, then `builtin`.
- `detect_available_backends()` reports installed backends.

### Mock communities

- `MockOrganism` exposes an optional `domain` field (`bacteria`, `archaea`,
  `eukaryota`) so genome resolution selects the correct source.
- Bacteria and archaea resolve through GTDB; fungi and other eukaryotes use
  NCBI Datasets with explicit accessions.
- Read counts are abundance-weighted: `--read-count` is the total, distributed
  across organisms by their listed proportions.
- Lookups are case-insensitive and accept product code aliases (e.g. `D6305`
  resolves to `zymo_d6300`).

Available mocks (see `nanorunner list-mocks` for the full catalogue):
`zymo_d6300`, `zymo_d6310`, `zymo_d6331`, `atcc_msa1002`, `atcc_msa1003`,
`cdc_select_agents`, `eskape`, `respiratory`, `who_critical`, `bloodstream`,
`wastewater`, plus four `quick_*` mocks for fast tests.

### Pipeline adapters

- `adapters.ADAPTERS` is a dict keyed by adapter name with validation specs
  (file patterns, expected structure).
- `validate_output()` checks a target directory against the spec.
- Backwards-compatible alias: `nanometanf` -> `nanometa`.

### Supported file types

- Replay input: `.fastq`, `.fq`, `.fastq.gz`, `.fq.gz`
- Generate input: `.fa`, `.fasta`, `.fa.gz`, `.fasta.gz`
- Generate output: `.fastq`, `.fastq.gz`

### Parallel processing

- Optional `ThreadPoolExecutor` runs file operations within a batch.
- Worker count is configurable; progress monitoring is thread-safe.
- Available for both replay and generate modes.

## Testing

One test file per source module, plus end-to-end integration tests. Test
files: `test_config.py`, `test_manifest.py`, `test_executor.py`,
`test_runner.py`, `test_timing.py`, `test_generators.py`, `test_species.py`,
`test_mocks.py`, `test_monitoring.py`, `test_detection.py`,
`test_adapters.py`, `test_profiles.py`, `test_deps.py`, `test_cli.py`,
`test_integration.py`. Shared fixtures live in `conftest.py`.

Coverage target: 90% (set in `pytest.ini`). Current coverage is 88%; the
largest gap is `cli_helpers.py` at 55%.

## Integration with Nanometa Live

Both modes produce output compatible with the watch-directory behaviour of
Nanometa Live and nanometanf:

- Same barcode directory patterns: `barcode01/`, `barcode02/`, `unclassified/`
- Same file extensions: `.fastq`, `.fastq.gz`
- Files appear incrementally with timing delays

```bash
# Drive nanometa_live (or nanometanf directly) from simulated input
nextflow run nanometa_live \
    --realtime_mode \
    --nanopore_output_dir /watch/output \
    --file_pattern "**/*.fastq{,.gz}" \
    --batch_size 10 \
    --batch_interval "5min"
```

## Extending the codebase

- **Timing models**: subclass `TimingModel` and implement `next_interval()`.
- **Read generators**: subclass `ReadGenerator`, implement `generate_reads()`
  and `is_available()`, then register in the `_BACKENDS` dict in
  `generators.py`.
- **Mock communities**: add `MockOrganism` and `MockCommunity` entries in
  `mocks.py`. Use the GTDB resolver for bacteria and archaea; eukaryotes
  require an explicit NCBI accession.
- **Pipeline adapters**: add an entry to `adapters.ADAPTERS` with a validation
  spec.
- **Configuration**: extend `ReplayConfig` or `GenerateConfig` with a
  `__post_init__` validation rule.

Every new feature must include unit tests and either a README example or an
entry under `examples/`.

## Reference

- [README](README.md) -- user-facing documentation
- [Quick start](docs/quickstart.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Examples](examples/)
