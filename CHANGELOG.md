# Changelog

All notable changes to NanoRunner will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **Breaking: Pipeline Adapters**: Removed `miniknife` adapter (fictional pipeline
  with no published tool). Renamed `nanometanf` adapter to `nanometa` to align with
  the published Nanometa Live tool. Both built-in adapters (`nanometa`, `kraken`) are
  now data-driven via `BUILTIN_ADAPTER_CONFIGS` using `GenericAdapter`, replacing the
  previous concrete `NanometanfAdapter`, `KrackenAdapter`, and `MiniknifeAdapter`
  classes. The `PipelineAdapter` ABC and `GenericAdapter` remain available for custom
  adapters. A backward-compatible alias maps `nanometanf` to `nanometa`.
- **Breaking: Configuration Profiles**: Consolidated 11 built-in profiles into 7
  with clearer names and distinct timing behaviors.
  - `development_testing` -> `development`
  - `accurate_mode` / `legacy_random` -> `steady` (random timing, low variation)
  - `rapid_sequencing` / `long_read_nanopore` / `minion_simulation` -> `bursty` (Poisson burst pattern)
  - `high_throughput` -> `high_throughput` (parameters adjusted: bp=0.20, brm=8.0, batch=15)
  - `smoothed_timing` -> `gradual_drift` (adaptive EMA timing)
  - `promethion_simulation` removed (no empirical basis; `high_throughput` serves the same role)
  - `generate_quick_test` -> `generate_test`
  - `generate_realistic` -> `generate_standard`
- **ProfileDefinition**: Extended with optional generate-mode fields (`read_count`,
  `mean_read_length`, `mean_quality`, `reads_per_file`, `output_format`,
  `generator_backend`). Generate profiles now set these parameters directly
  instead of only describing them in the description string.
- **Profile Recommendations**: Simplified recommendation engine to use new names
  and removed device-specific use cases (minion/promethion) that had no empirical basis.

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

[2.0.1]: https://github.com/FOI-Bioinformatics/nanorunner/releases/tag/v2.0.1
[2.0.0]: https://github.com/FOI-Bioinformatics/nanorunner/releases/tag/v2.0.0
[1.0.0]: https://github.com/FOI-Bioinformatics/nanorunner/releases/tag/v1.0.0
