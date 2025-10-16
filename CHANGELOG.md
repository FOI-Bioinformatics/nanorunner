# Changelog

All notable changes to NanoRunner will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- **Comprehensive Testing**: 410 tests with 93% coverage and 100% success rate

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

[2.0.0]: https://github.com/FOI-Bioinformatics/nanorunner/releases/tag/v2.0.0
[1.0.0]: https://github.com/FOI-Bioinformatics/nanorunner/releases/tag/v1.0.0
