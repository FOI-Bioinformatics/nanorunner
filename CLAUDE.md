# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is `nanorunner` - a nanopore sequencing run simulator designed for testing bioinformatics pipelines. It operates in two modes: **replay mode** transfers existing FASTQ files with configurable timing, while **generate mode** produces simulated nanopore reads from genome FASTA files. Both modes support multiple timing models (uniform, random, Poisson, adaptive), parallel processing, configuration profiles, pipeline-specific adapters, and progress monitoring with resource tracking.

## Project Standards

This project adheres to strict quality principles in all code, documentation, and development practices:

### 1. Completeness
- **All features must be fully documented**: Every CLI parameter, configuration option, and API method requires comprehensive documentation
- **No partial implementations**: Features should be complete before merging, including error handling, validation, and edge cases
- **Test coverage**: All documented functionality must have corresponding tests
- **Examples provided**: Each major feature should have working code examples in the `examples/` directory

### 2. Consistency
- **Naming conventions**: Use consistent terminology across code, documentation, and user interfaces
  - Package name: `nanorunner` (not `nanorun` or `nanopore-simulator`)
  - Python version: Always specify `3.9+` consistently
  - Version numbers: Keep synchronized across `__init__.py`, CLI, README, and CHANGELOG
- **Code style**: Follow black formatting, mypy type checking, and flake8 linting
- **Documentation format**: Use consistent markdown formatting, heading levels, and code block syntax
- **API design**: Maintain consistent parameter names and patterns across similar functions

### 3. Organization
- **Logical structure**: Documentation and code should follow intuitive hierarchies
  - All source modules in `nanopore_simulator/` (flat layout, no subdirectories)
  - User guides in `docs/`
  - Examples in `examples/`
- **Clear navigation**: All documentation must be linked from README.md or docs/README.md
- **No orphaned files**: Every file should be referenced and serve a clear purpose
- **Proper separation**: Keep concerns separated (e.g., business logic vs. CLI parsing, testing vs. production code)

### 4. Accessibility
- **Progressive disclosure**: Present information from simple to complex
  - README.md: High-level overview and quick start
  - docs/quickstart.md: Beginner-friendly step-by-step guide
  - CLAUDE.md: Technical details for developers
- **Multiple entry points**: Users should find relevant information regardless of their experience level
- **Clear examples**: Provide concrete, runnable examples for all features
- **Troubleshooting guides**: Anticipate common issues and provide solutions

### 5. Cleanliness
- **No legacy code**: Remove deprecated files, functions, and comments
- **No build artifacts**: Keep repository free of generated files (use .gitignore)
- **No redundancy**: Avoid duplicating information across multiple files
- **Clear git history**: Meaningful commit messages and organized branches
- **Minimal dependencies**: Use standard library where possible; justify each external dependency

### 6. Scientific Language
- **Modest tone**: Avoid superlatives, marketing language, and exaggeration
  - Use "provides configurable timing patterns" not "revolutionary ultra-advanced next-generation timing"
- **Precise terminology**: Use established scientific and technical terms
  - Use "temporal patterns" not "timing stuff"
  - Use "throughput optimization" not "making it faster"
- **Evidence-based claims**: Support statements with data
- **Professional objectivity**: Focus on facts and capabilities, not opinions
- **Appropriate detail**: Balance technical accuracy with readability

### Enforcement
When working on this project:
- **Before committing**: Verify changes maintain all six standards
- **Code reviews**: Check for adherence to these principles
- **Documentation updates**: Ensure any code changes are reflected in documentation
- **Version bumps**: Update ALL version references (not just one file)
- **New features**: Must include tests, documentation, and examples

## Key Commands

### Development and Testing
```bash
# Install package in development mode
pip install -e .

# Install with enhanced monitoring features
pip install -e .[enhanced]

# Run all tests with coverage
pytest

# Run specific test categories
pytest tests/test_config.py                  # Configuration validation
pytest tests/test_manifest.py                # Manifest building (plan phase)
pytest tests/test_executor.py                # File execution (do phase)
pytest tests/test_runner.py                  # Orchestration (plan-execute-monitor)
pytest tests/test_cli.py                     # CLI interface tests
pytest tests/test_timing.py                  # Timing model tests
pytest tests/test_generators.py              # Read generation backend tests
pytest tests/test_species.py                 # Species resolution tests
pytest tests/test_mocks.py                   # Mock community tests
pytest tests/test_monitoring.py              # Progress monitoring tests
pytest tests/test_detection.py               # File structure detection tests
pytest tests/test_adapters.py                # Pipeline adapter tests
pytest tests/test_profiles.py                # Configuration profile tests
pytest tests/test_deps.py                    # Dependency checking tests
pytest tests/test_integration.py             # End-to-end integration tests

# Run with coverage reporting
pytest --cov=nanopore_simulator --cov-report=html --cov-report=term-missing

# Quick test subset (exclude performance tests)
pytest -m "not slow"
```

### Code Quality
```bash
# Format code
black nanopore_simulator/ tests/

# Type checking
mypy nanopore_simulator/

# Lint code
flake8 nanopore_simulator/
```

### Package Operations
```bash
# Build package
python -m build

# Test console script functionality
nanorunner --help
nanorunner list-profiles
nanorunner list-adapters
nanorunner list-generators
nanorunner list-mocks
nanorunner check-deps
nanorunner replay --source /source --target /target --profile bursty --monitor enhanced
nanorunner replay --source /source --target /target --reads-per-file 50 --interval 1
nanorunner generate --genomes genome.fa --target /target --interval 2
nanorunner generate --mock zymo_d6300 --target /target --read-count 1000 --interval 1
nanorunner generate --genomes genome.fa --target /target --mean-quality 25 --std-quality 3
nanorunner validate --pipeline nanometa --target /path/to/output
nanorunner recommend --source /path/to/data
```

## Architecture

### Plan-Execute-Monitor Pattern

The codebase follows a plan-execute-monitor decomposition. Instead of a single orchestration class, three small modules handle distinct phases:

1. **Plan** (`manifest.py`): Config -> list of `FileEntry` describing what files to produce
2. **Execute** (`executor.py`): One `FileEntry` -> one file on disk (copy, link, or generate)
3. **Monitor** (`monitoring.py`): Progress tracking and display

The orchestrator (`runner.py`) is a thin loop connecting these phases (~175 lines).

### Module Layout

Flat layout -- all source modules in `nanopore_simulator/` with no subdirectories.

**Orchestration:**
- `runner.py`: Thin orchestrator connecting plan, execute, and monitor phases
- `manifest.py`: Builds file manifests for replay and generate modes (`FileEntry` dataclass, `build_replay_manifest()`, `build_generate_manifest()`, `distribute_reads()`)
- `executor.py`: Produces one file per entry (`execute_entry()` dispatches to copy/link/generate)

**Configuration:**
- `config.py`: Mode-specific frozen dataclasses (`ReplayConfig`, `GenerateConfig`) with `__post_init__` validation
- `profiles.py`: Dict-based configuration presets (`get_profile()`, `apply_profile()`, `get_recommendations()`)

**Read Generation:**
- `generators.py`: `ReadGenerator` ABC with `BuiltinGenerator` (random subsequences, log-normal lengths, optional numpy) and `SubprocessGenerator` (unified wrapper for badread/nanosim)
- `species.py`: Species name resolution via GTDB REST API (bacteria/archaea) and NCBI datasets CLI (eukaryotes), with local caching
- `mocks.py`: Mock community definitions (`MockOrganism`, `MockCommunity`), built-in communities, aliases

**Infrastructure:**
- `cli.py`: Typer-based CLI with subcommands (`replay`, `generate`, `download`, `list-profiles`, `list-adapters`, `list-generators`, `list-mocks`, `recommend`, `validate`, `check-deps`)
- `timing.py`: Timing model implementations (Uniform, Random, Poisson, Adaptive) with factory
- `monitoring.py`: Thread-safe `ProgressMonitor` with resource tracking, ETA, pause/resume; `NullMonitor` for headless mode
- `detection.py`: Module-level functions for singleplex/multiplex structure detection
- `adapters.py`: Dict-based pipeline validation (`ADAPTERS` registry, `validate_output()`) -- no ABC
- `deps.py`: Dependency checking with install hints and pre-flight validation
- `fastq.py`: FASTQ read/write utilities

### Key Design Patterns

**Operation Modes:**
- **Replay mode** (`copy`/`link`): Transfers existing sequencing files from source to target with timing
- **Generate mode** (`generate`): Produces simulated FASTQ reads from FASTA genomes with timing

**Data Flow (both modes):**
1. CLI parses arguments, applies profile overrides, builds `ReplayConfig` or `GenerateConfig`
2. `runner.py` calls `build_replay_manifest()` or `build_generate_manifest()` to plan file operations
3. Manifest entries processed via `execute_entry()` with timing delays between batches
4. `ProgressMonitor` (or `NullMonitor`) tracks progress throughout

**Timing Model Architecture:**
- Abstract `TimingModel` base class with factory pattern
- Uniform: Constant intervals for deterministic testing
- Random: Symmetric variation around base interval with configurable randomness factor
- Poisson: Exponential intervals with burst clusters (not empirically validated)
- Adaptive: Smoothly varying intervals via exponential moving average

**Read Generator Architecture:**
- Abstract `ReadGenerator` base class with factory pattern (`create_generator()`)
- `BuiltinGenerator`: Error-free random subsequences from FASTA with log-normal length distribution. No error model. No external dependencies.
- `SubprocessGenerator`: Unified wrapper for badread and nanosim backends
- Auto mode tries badread, nanosim, then builtin in order of preference
- `detect_available_backends()` reports which backends are installed

**Mock Community System:**
- Built-in mock communities for standardized microbiome testing
- `MockOrganism` includes optional `domain` field ("bacteria", "archaea", "eukaryota") for correct genome resolution
- Species resolved via GTDB (bacteria/archaea) or NCBI (fungi/eukaryotes) with automatic genome downloads
- Abundance-weighted read distribution: `--read-count` specifies total reads, distributed proportionally across organisms
- Case-insensitive lookup with product code aliases (e.g., D6305 -> zymo_d6300)
- Available mocks (`--list-mocks` to see all):
  - `zymo_d6300`: Zymo D6300 Standard - 10 species, even distribution
  - `zymo_d6310`: Zymo D6310 Log Distribution - 10 species, 7 orders of magnitude
  - `zymo_d6331`: Zymo D6331 Gut Microbiome - 21 strains, 17 species (bacteria, archaea, fungi)
  - `atcc_msa1002`: ATCC MSA-1002 - 20 strains, 5% each
  - `atcc_msa1003`: ATCC MSA-1003 - 20 strains, staggered (0.02%-18%)
  - `cdc_select_agents`: CDC/USDA Tier 1 bacterial select agents - 6 species
  - `eskape`: ESKAPE nosocomial pathogens - 6 species
  - `respiratory`: Community-acquired respiratory pathogens - 6 species
  - `who_critical`: WHO Critical Priority carbapenem-resistant pathogens - 5 species
  - `bloodstream`: Bloodstream infection panel - 5 bacteria + 1 yeast
  - `wastewater`: Wastewater surveillance indicators and pathogens - 6 species
  - `quick_single`, `quick_3species`, `quick_gut5`, `quick_pathogens`: Fast testing mocks

**Monitoring System:**
- Thread-safe `ProgressMonitor` with optional resource tracking (psutil)
- ETA calculation via throughput extrapolation
- Pause/resume with signal handling
- `NullMonitor` for headless or test execution

**Configuration Profile System:**
- Built-in profiles: `development`, `steady`, `bursty`, `high_throughput`, `gradual_drift`, `generate_test`, `generate_standard`
- Profile recommendations based on file count and use case
- Override capability for profile-based configurations

**Pipeline Validation:**
- Dict-based `ADAPTERS` registry with validation specs for nanometa and kraken
- `validate_output()` checks file patterns and required structure
- Backward-compatible alias: `nanometanf` -> `nanometa`

### Supported File Types
- **Replay mode input**: `.fastq`, `.fq`, `.fastq.gz`, `.fq.gz`
- **Generate mode input**: `.fa`, `.fasta`, `.fa.gz`, `.fasta.gz` (genome FASTA files)
- **Generate mode output**: `.fastq`, `.fastq.gz`

### Parallel Processing
- Optional ThreadPoolExecutor-based parallel file processing within batches
- Configurable worker thread count with automatic scaling
- Thread-safe progress monitoring and error handling
- Applies to both replay and generate modes

## Testing Architecture

**Test organization:** One test file per source module, plus integration tests.

**Test files:**
- `test_config.py`: ReplayConfig and GenerateConfig validation
- `test_manifest.py`: Manifest building for replay and generate modes
- `test_executor.py`: File copy/link/generate operations
- `test_runner.py`: Orchestration, parallel execution, batching
- `test_timing.py`: All timing models and factory
- `test_generators.py`: Read generator backends, FASTA parsing, factory
- `test_species.py`: Species resolution with mocked HTTP/subprocess
- `test_mocks.py`: Mock community data, aliases, validation
- `test_monitoring.py`: Progress monitoring, ETA, resource tracking
- `test_detection.py`: File structure detection
- `test_adapters.py`: Pipeline validation
- `test_profiles.py`: Configuration profiles
- `test_deps.py`: Dependency checking
- `test_cli.py`: CLI commands via typer.testing.CliRunner
- `test_integration.py`: End-to-end workflows
- `conftest.py`: Shared fixtures (sample_fasta, source directories)

**Coverage Standards:**
- Minimum coverage threshold: 90% (set in `pytest.ini`)
- Currently 729 tests across 18 test files; coverage is 88%, below
  the threshold. The largest gap is `cli_helpers.py` at 55%.
- Comprehensive integration testing with multiple timing models and configurations

## Integration Context

### Primary Integration: Nanometa Live
The simulator is designed for testing the Nanometa Live real-time taxonomic analysis pipeline (`github.com/FOI-Bioinformatics/nanometa_live`). Both replay and generate modes produce output compatible with its watch-directory behavior:
- Same barcode directory patterns (`barcode01/`, `barcode02/`, `unclassified/`)
- Same file extensions (`.fastq`, `.fastq.gz`)
- Files appear incrementally with timing

```bash
# Configure nanometa for simulated data consumption
nextflow run nanometa_live \
    --realtime_mode \
    --nanopore_output_dir /watch/output \
    --file_pattern "**/*.fastq{,.gz}" \
    --batch_size 10 \
    --batch_interval "5min"
```

### Multi-Pipeline Support
Pipeline adapters enable validation and testing across multiple bioinformatics workflows:
- **nanometa**: Nanometa Live real-time taxonomic analysis
- **kraken**: Kraken2/KrakenUniq taxonomic classification
- **Generic**: Customizable adapter for arbitrary pipelines

### Timing Models
The timing models provide configurable temporal patterns:
- **Poisson model**: Exponential inter-event intervals with burst clusters (not validated against empirical data)
- **Adaptive model**: Smoothly varying intervals via exponential moving average of own output
- **Random model**: Introduces controlled stochastic variation for robustness testing

## Configuration Notes

- **Dependencies**: Standard library only for core functionality; optional psutil for enhanced monitoring; optional badread/NanoSim for external read generation backends
- **Python compatibility**: 3.9+ with full type hint support
- **Performance**: Optimized for datasets ranging from development (10s of files) to production scale (10,000+ files)
- **Resource monitoring**: Optional CPU, memory, and disk I/O tracking with performance warnings
- **Extensibility**: Plugin architecture for custom timing models, adapters, read generators, and monitoring components
- **Console script entry point**: `nanorunner`
- **Enhanced features**: Available via `pip install nanorunner[enhanced]` for resource monitoring capabilities

## Development Patterns

When extending functionality:
1. **Timing models**: Inherit from `TimingModel` abstract base class with `next_interval()` implementation
2. **Read generators**: Inherit from `ReadGenerator` ABC with `generate_reads()` and `is_available()` implementations; register in `_BACKENDS` dict in `generators.py`
3. **Mock communities**: Add `MockOrganism` list and `MockCommunity` entry in `mocks.py`; use GTDB resolver for bacteria/archaea, NCBI with explicit accession for fungi
4. **Pipeline adapters**: Add entry to `ADAPTERS` dict in `adapters.py` with validation spec
5. **Monitoring**: Use thread-safe `ProgressMonitor` methods for metrics collection
6. **Testing**: Include both unit tests and integration tests with performance considerations
7. **Configuration**: Add new parameters to `ReplayConfig` or `GenerateConfig` with `__post_init__` validation
8. **Documentation**: Update both technical documentation and user-facing examples

## User Documentation

For end-user guides and tutorials, see:
- **[README.md](README.md)**: Main user documentation with installation, usage, and examples
- **[docs/quickstart.md](docs/quickstart.md)**: Quick start guide for new users
- **[docs/troubleshooting.md](docs/troubleshooting.md)**: Common issues and solutions
- **[examples/](examples/)**: Working code examples demonstrating all features
