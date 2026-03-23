# Changelog

All notable changes to NanoRunner will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [3.0.0] - 2026-03-23

This release is a substantial internal rewrite. The CLI contract is preserved — all
subcommands, flags, and observable behaviour remain compatible with 2.x. Internal
Python APIs have changed; see the migration guide below.

### Added
- **Plan-Execute-Monitor Architecture**: Replaced the monolithic `NanoporeSimulator`
  class (~1,400 lines) with three focused modules connected by a thin orchestrator:
  `manifest.py` (plan), `executor.py` (execute), `runner.py` (~175 lines, orchestrate).
- **`manifest.py`**: Pure data-transformation module. `build_replay_manifest()` and
  `build_generate_manifest()` each accept a config dataclass and return a list of
  `FileEntry` objects describing all planned file operations.
- **`executor.py`**: Single `execute_entry()` dispatch function handling copy, link, and
  generate operations with no orchestration logic.
- **`runner.py`**: Thin orchestration loop with `run_replay()` and `run_generate()`
  public functions replacing the previous class-based API.
- **`species.py`**: Species name resolution via GTDB REST API (bacteria/archaea) and
  NCBI datasets CLI (eukaryotes/fungi) with local disk caching.
- **`mocks.py`**: Fifteen built-in mock communities for standardized microbiome testing,
  including `zymo_d6300`, `zymo_d6310`, `zymo_d6331`, `atcc_msa1002`, `atcc_msa1003`,
  `cdc_select_agents`, `eskape`, `respiratory`, `who_critical`, `bloodstream`,
  `wastewater`, and four `quick_*` mocks for development use.
- **`deps.py`**: Centralized dependency-checking module. `nanorunner check-deps` reports
  status of all required and optional dependencies with conda install instructions.
  Pre-flight validation in `generate` and `download` subcommands catches missing tools
  before work begins.
- **Rechunking Support**: `--reads-per-file` controls output file size in generate mode.
  Files are created atomically (written to a temporary path, then renamed) to prevent
  partial reads by downstream tools.
- **Disk Space Pre-check**: Manifest execution estimates required disk space before
  starting and raises a clear error if the target filesystem lacks capacity.
- **Signal Handling**: `SIGINT` and `SIGTERM` trigger a clean shutdown sequence that
  completes the current file before exiting, rather than terminating mid-write.
- **Atomic Writes**: All output files are written via a temporary sibling file and
  renamed on completion, eliminating truncated files from interrupted runs.
- **Robust Backend Detection**: `is_available()` for badread and nanosim verifies the
  tool can actually start (catches broken installs where the binary exists but a
  required Python dependency such as edlib is absent).

### Changed
- **Breaking: Configuration Split**: `SimulationConfig` (52 fields) replaced by two
  mode-specific frozen dataclasses: `ReplayConfig` (~14 fields) and `GenerateConfig`
  (~26 fields). Each validates only its own fields in `__post_init__`.
- **Breaking: Module Layout Flattened**: Removed `core/` and `cli/` subdirectories.
  All source modules now reside directly in `nanopore_simulator/`. The single CLI
  module is `nanopore_simulator/cli.py` (was `nanopore_simulator/cli/main.py`).
- **Breaking: Pipeline Adapters**: Removed `miniknife` adapter (no published tool).
  Renamed `nanometanf` to `nanometa` to align with the published Nanometa Live tool.
  The `PipelineAdapter` ABC and `GenericAdapter` class have been removed; adapters are
  now plain dicts in `ADAPTERS`. A backward-compatible alias maps `nanometanf` to
  `nanometa`.
- **Breaking: Configuration Profiles**: Consolidated 11 built-in profiles to 7 with
  distinct, clearly named behaviours:
  - `development_testing` → `development`
  - `accurate_mode` / `legacy_random` → `steady`
  - `rapid_sequencing` / `long_read_nanopore` / `minion_simulation` → `bursty`
  - `high_throughput` retained (parameters adjusted)
  - `smoothed_timing` → `gradual_drift`
  - `promethion_simulation` removed (no empirical basis)
  - `generate_quick_test` → `generate_test`
  - `generate_realistic` → `generate_standard`
- **Read Generators**: `BadreadGenerator` and `NanoSimGenerator` merged into a single
  `SubprocessGenerator` parameterized by backend name. `BuiltinGenerator` unchanged.
- **Monitoring**: Removed unused `SimulationMetrics` fields and simplified ETA
  estimation. `NullMonitor` used for headless and test execution.
- **Install Instructions**: Standardized all install hints to use conda/bioconda
  channels (e.g., `conda install -c conda-forge -c bioconda badread`).
- **Test Suite**: Reorganized from 40 test files (~17,500 lines) to 18 test files
  (~7,000 lines), one per source module plus integration tests.

### Removed
- `nanopore_simulator/core/` subdirectory and all modules within it
- `nanopore_simulator/cli/` subdirectory and `cli/main.py`
- `NanoporeSimulator` class (use `run_replay()` / `run_generate()` instead)
- `SimulationConfig` class (use `ReplayConfig` or `GenerateConfig` instead)
- `PipelineAdapter` ABC and `GenericAdapter` class
- `NanometanfAdapter`, `KrackenAdapter`, `MiniknifeAdapter` concrete adapter classes
- `miniknife` pipeline adapter
- `promethion_simulation` configuration profile
- `DetailedProgressMonitor` class (was unused; `--monitor detailed` maps to basic)
- `BadreadGenerator` and `NanoSimGenerator` classes (replaced by `SubprocessGenerator`)
- `--sample-type` CLI option (use `--force-structure` and `--mix-reads` instead)

---

## Migration Guide: 2.x to 3.0

### Python API Changes

**Old (2.x):**
```python
from nanopore_simulator import SimulationConfig, NanoporeSimulator

config = SimulationConfig(
    source_dir="/data/source",
    target_dir="/data/target",
    interval=5.0,
    timing_model="random",
)
simulator = NanoporeSimulator(config)
simulator.run()
```

**New (3.0):**
```python
from nanopore_simulator import ReplayConfig, run_replay

config = ReplayConfig(
    source_dir="/data/source",
    target_dir="/data/target",
    interval=5.0,
    timing_model="random",
)
run_replay(config)
```

For generate mode, use `GenerateConfig` and `run_generate()` in the same pattern.

### Import Path Changes

| 2.x import | 3.0 import |
|---|---|
| `from nanopore_simulator.core.config import SimulationConfig` | `from nanopore_simulator.config import ReplayConfig, GenerateConfig` |
| `from nanopore_simulator.cli.main import app` | `from nanopore_simulator.cli import app` |
| `from nanopore_simulator.core.monitoring import ProgressMonitor` | `from nanopore_simulator.monitoring import ProgressMonitor` |
| `from nanopore_simulator.core.timing import create_timing_model` | `from nanopore_simulator.timing import create_timing_model` |
| `from nanopore_simulator.core.adapters import GenericAdapter` | Removed; use `nanopore_simulator.adapters.ADAPTERS` dict |

### CLI Changes

The CLI contract is fully preserved. All existing `nanorunner` commands, flags, and
behaviours work identically. No changes to shell scripts or CI pipelines are required.

One option has been removed: `--sample-type {pure,mixed}`. The same output structures
are achievable with existing flags:
- Former `--sample-type pure` (default): use `--force-structure multiplex` or let
  structure detection assign each genome its own barcode directory.
- Former `--sample-type mixed`: use `--force-structure singleplex --mix-reads`.

### Profile Name Changes

| 2.x profile | 3.0 profile |
|---|---|
| `development_testing` | `development` |
| `accurate_mode` / `legacy_random` | `steady` |
| `rapid_sequencing` | `bursty` |
| `long_read_nanopore` | `bursty` |
| `minion_simulation` | `bursty` |
| `smoothed_timing` | `gradual_drift` |
| `promethion_simulation` | `high_throughput` (closest equivalent) |
| `generate_quick_test` | `generate_test` |
| `generate_realistic` | `generate_standard` |

## [2.0.2] - 2025-10-27

### Fixed
- **Version Management**: Implemented single source of truth for version numbers
  - CLI now dynamically imports version from `__init__.__version__`
  - Removed hardcoded version string in CLI (main.py:273)
  - Fixed version test failure by synchronizing version expectations
  - All 480 tests now pass (100% pass rate)

### Changed
- **Python Requirements**: Standardized minimum Python version to 3.9+
  - Updated `pyproject.toml` requires-python from `>=3.7` to `>=3.9`
  - Removed Python 3.7 and 3.8 from supported version classifiers
  - Updated CONTRIBUTING.md prerequisites to specify Python 3.9+
  - Updated black target-version to py39
  - Aligned with existing documentation and mypy configuration
- **Documentation Accuracy**: Corrected test suite documentation
  - Updated test count from 48 to actual 480 tests across all documentation
  - Corrected pass rate from claimed 100% to accurate 99.8% → 100%
  - Added coverage percentage (97%) to documentation
  - Updated all version references from v2.0.0 to v2.0.1/v2.0.2 in docs
- **Code Quality**: Applied code quality standards
  - Reformatted 2 files with black (cli/main.py, core/monitoring.py)
  - Removed 2 unused imports (Pattern from adapters.py, get_compatible_pipelines from cli/main.py)
  - Reduced flake8 violations from 125 to 121 issues

### Removed
- **Legacy Files**: Removed duplicate build configuration
  - Deleted setup.py (functionality now in pyproject.toml only)
  - Modern build using PEP 518 pyproject.toml standard

## [2.0.1] - 2025-10-17

### Fixed
- **Critical**: Fixed `DetailedProgressMonitor` parameter handling bug in factory function (`monitoring.py:956-962`)
  - Factory was passing unsupported parameters to `DetailedProgressMonitor.__init__()`
  - Now correctly filters parameters to only pass `update_interval` and `log_level`
  - Detailed monitoring mode now works as documented

### Added
- **CLI Parameters**: Added adaptive timing model configuration options
  - `--adaptation-rate`: Controls learning speed (0.0-1.0, default: 0.1)
  - `--history-size`: Sets lookback window size (integer ≥1, default: 10)
  - Both parameters now fully documented in README.md

### Changed
- **Documentation**: Comprehensive cleanup and reorganization
  - Fixed coverage badge (93% → 95%)
  - Updated test counts to reflect actual comprehensive test suite (480 tests)
  - Added links to docs/quickstart.md and docs/troubleshooting.md
  - Removed redundant troubleshooting content from README.md
  - Applied modest scientific language throughout documentation
  - Fixed package name inconsistencies in CLAUDE.md
- **Root Directory**: Removed legacy files (nanopore_simulator.py, test artifacts)
- **Testing**: Achieved 99.8% pass rate on comprehensive test suite (480 tests)

## [2.0.0] - 2025-10-16

### Added
- **Timing Models**: Four sophisticated timing models (uniform, random, Poisson, adaptive) for realistic sequencing simulation
- **Parallel Processing**: ThreadPoolExecutor-based concurrent file processing with configurable worker threads
- **Configuration Profiles**: Pre-defined parameter sets for common sequencing scenarios (rapid_sequencing, high_throughput, etc.)
- **Pipeline Adapters**: Built-in support for nanometanf, Kraken, miniknife, and generic bioinformatics pipelines
- **Enhanced Monitoring**: Real-time progress tracking with resource usage (CPU, memory, disk I/O)
- **Interactive Controls**: Pause/resume functionality and graceful shutdown handling
- **Checkpoint System**: Automatic progress preservation for recovery from interruptions
- **Predictive ETA**: Trend analysis and confidence scoring for time estimates
- **Comprehensive Testing**: Extensive test suite with high coverage and 100% success rate

### Changed
- **Breaking**: Removed legacy `random_interval` parameter in favor of timing model system
- **Breaking**: Renamed package entry point to `nanorunner` (was `nanopore-simulator`)
- **Architecture**: Complete rewrite with modular core components
- **Performance**: Test suite optimized from 5-10 minutes to 69 seconds
- **Documentation**: Comprehensive README with usage examples and tutorials

### Fixed
- Thread safety issues in parallel processing
- Race conditions in progress monitoring
- Permission error handling for restricted directories
- Memory leaks in long-running simulations
- Cross-platform compatibility (Linux, macOS, Unix)

### Removed
- **Breaking**: Legacy `random_interval` boolean parameter (use `timing_model="random"` instead)

## [1.0.0] - 2024-09-16

### Added
- Initial release of nanopore sequencing simulator
- Basic file copying/linking for singleplex and multiplex structures
- Simple interval-based timing
- Command-line interface
- FASTQ and POD5 file support
- Automatic structure detection

---

## Migration Guide: 1.x to 2.0

### Configuration Changes

**Old (1.x):**
```python
config = SimulationConfig(
    source_dir=source,
    target_dir=target,
    interval=5.0,
    random_interval=True  # REMOVED
)
```

**New (2.0):**
```python
config = SimulationConfig(
    source_dir=source,
    target_dir=target,
    interval=5.0,
    timing_model="random",  # Use timing model instead
    timing_model_params={"random_factor": 0.3}
)
```

### CLI Changes

**Old (1.x):**
```bash
nanopore-simulator /source /target --interval 5 --random
```

**New (2.0):**
```bash
nanorunner /source /target --interval 5 --timing-model random --random-factor 0.3
```

### New Features You Should Try

1. **Configuration Profiles** - Pre-optimized settings:
   ```bash
   nanorunner /source /target --profile rapid_sequencing
   ```

2. **Enhanced Monitoring** - Real-time resource tracking:
   ```bash
   nanorunner /source /target --monitor enhanced
   ```

3. **Parallel Processing** - For large datasets:
   ```bash
   nanorunner /source /target --parallel --worker-count 8
   ```

4. **Poisson Timing** - Biologically realistic simulation:
   ```bash
   nanorunner /source /target --timing-model poisson
   ```

[3.0.0]: https://github.com/FOI-Bioinformatics/nanorunner/releases/tag/v3.0.0
[2.0.2]: https://github.com/FOI-Bioinformatics/nanorunner/releases/tag/v2.0.2
[2.0.1]: https://github.com/FOI-Bioinformatics/nanorunner/releases/tag/v2.0.1
[2.0.0]: https://github.com/FOI-Bioinformatics/nanorunner/releases/tag/v2.0.0
[1.0.0]: https://github.com/FOI-Bioinformatics/nanorunner/releases/tag/v1.0.0
