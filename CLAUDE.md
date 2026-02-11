# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is `nanorunner` - a nanopore sequencing run simulator designed for testing bioinformatics pipelines. It operates in two modes: **replay mode** transfers existing FASTQ/POD5 files with configurable timing, while **generate mode** produces simulated nanopore reads from genome FASTA files. Both modes support multiple timing models (uniform, random, Poisson, adaptive), parallel processing, configuration profiles, pipeline-specific adapters, and progress monitoring with resource tracking.

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
  - Core components in `nanopore_simulator/core/`
  - CLI interface in `nanopore_simulator/cli/`
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
pytest tests/test_cli.py                    # CLI interface tests
pytest tests/test_cli_enhanced.py           # Enhanced CLI feature tests
pytest tests/test_enhanced_monitoring.py    # Advanced monitoring tests
pytest tests/test_parallel_processing.py    # Parallel processing tests
pytest tests/test_timing_models.py          # Timing model tests
pytest tests/test_profiles.py               # Configuration profile tests
pytest tests/test_adapters.py               # Pipeline adapter tests
pytest tests/test_integration.py            # End-to-end integration tests
pytest tests/test_generators.py             # Read generation backend tests
pytest tests/test_generate_integration.py   # Generate mode end-to-end tests
pytest tests/test_practical.py -m practical # Practical tests with real NCBI genomes
pytest tests/test_performance.py -m slow    # Performance benchmarks

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
nanorunner --list-profiles
nanorunner --list-adapters
nanorunner --list-generators
nanorunner --list-mocks
nanorunner /source /target --profile bursty --monitor enhanced
nanorunner --genomes genome.fa /target --interval 2
nanorunner --mock zymo_d6300 /target --read-count 1000 --interval 1
nanorunner --genomes genome.fa /target --mean-quality 25 --std-quality 3
```

## Architecture

### Core Components

**nanopore_simulator/core/**
- `config.py`: SimulationConfig dataclass with validation for all simulation parameters including generate mode fields
- `detector.py`: FileStructureDetector for automatic singleplex/multiplex structure recognition
- `simulator.py`: NanoporeSimulator orchestration class handling both replay (copy/link) and generate operations
- `timing.py`: Timing model implementations (UniformTimingModel, RandomTimingModel, PoissonTimingModel, AdaptiveTimingModel)
- `generators.py`: Read generation backends (BuiltinGenerator, BadreadGenerator, NanoSimGenerator) with ABC, factory, and FASTA parsing
- `profiles.py`: Configuration profile system with built-in profiles for sequencing and generation scenarios
- `adapters.py`: Pipeline adapter framework with data-driven BUILTIN_ADAPTER_CONFIGS (nanometa, kraken), GenericAdapter, and backward-compatible aliases
- `monitoring.py`: Enhanced progress monitoring with resource tracking, predictive ETA, and interactive controls

**nanopore_simulator/cli/**
- `main.py`: Command-line interface with profile support, timing model selection, monitoring options, and read generation arguments

### Key Design Patterns

**Operation Modes:**
- **Replay mode** (`copy`/`link`): Transfers existing sequencing files from source to target with timing
- **Generate mode** (`generate`): Produces simulated FASTQ reads from FASTA genomes with timing

**Data Flow (Replay):**
1. CLI parses arguments and handles profile/adapter commands
2. Configuration created from profiles or direct parameters with timing model specification
3. FileStructureDetector analyzes source directory structure
4. NanoporeSimulator initializes with timing model, parallel processing, and monitoring components
5. Files processed in batches with timing models and optional parallelization

**Data Flow (Generate):**
1. CLI receives `--genomes` argument, sets `operation="generate"`
2. Configuration created with genome paths and generation parameters
3. NanoporeSimulator initializes ReadGenerator via factory (auto/builtin/badread/nanosim)
4. `_create_generate_manifest()` distributes total `read_count` across genomes using `_distribute_reads()` (abundance-weighted or equal split), then builds file plan per genome
5. Each manifest entry processed through `_process_generate()` which calls `generator.generate_reads()`
6. Output files appear incrementally with timing, compatible with downstream pipelines

**Timing Model Architecture:**
- Abstract `TimingModel` base class with factory pattern implementation
- Uniform: Constant intervals for deterministic testing
- Random: Symmetric variation around base interval with configurable randomness factor
- Poisson: Exponential intervals with burst clusters (not empirically validated)
- Adaptive: Smoothly varying intervals via exponential moving average

**Read Generator Architecture:**
- Abstract `ReadGenerator` base class with factory pattern (`create_read_generator()`)
- BuiltinGenerator: Error-free random subsequences from FASTA with log-normal length distribution. No error model. No external dependencies.
- BadreadGenerator: Wraps `badread simulate` via subprocess
- NanoSimGenerator: Wraps NanoSim via subprocess
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

**Enhanced Monitoring System:**
- Thread-safe `ProgressMonitor` with real-time resource tracking
- Predictive ETA calculation with trend analysis (improving/degrading/stable)
- Interactive controls (pause/resume) with signal handling
- Automatic checkpoint/resume system for long simulations
- Performance warning detection (high CPU/memory usage, low throughput)

**Configuration Profile System:**
- Built-in profiles: `development`, `steady`, `bursty`, `high_throughput`, `gradual_drift`, `generate_test`, `generate_standard`
- Profile recommendations based on file count and use case
- Override capability for profile-based configurations

**Pipeline Adapter Framework:**
- Standardized validation interface for different bioinformatics pipelines
- Built-in adapters defined via `BUILTIN_ADAPTER_CONFIGS`: `nanometa`, `kraken` (both use `GenericAdapter`)
- Backward-compatible alias: `nanometanf` -> `nanometa`
- `PipelineAdapter` ABC available for custom adapter subclasses
- File pattern validation and structure requirements checking

### Supported File Types
- **Replay mode input**: `.fastq`, `.fq`, `.fastq.gz`, `.fq.gz`, `.pod5`
- **Generate mode input**: `.fa`, `.fasta`, `.fa.gz`, `.fasta.gz` (genome FASTA files)
- **Generate mode output**: `.fastq`, `.fastq.gz`

### Parallel Processing
- Optional ThreadPoolExecutor-based parallel file processing within batches
- Configurable worker thread count with automatic scaling
- Thread-safe progress monitoring and error handling
- Applies to both replay and generate modes

## Testing Architecture

**Test Categories:**
- `test_cli.py`: Core command-line interface functionality
- `test_cli_enhanced.py`: Enhanced CLI features and monitoring integration
- `test_config.py`: Configuration validation and parameter handling
- `test_detector.py`: File structure detection algorithms
- `test_simulator.py`: Core simulation functionality and orchestration
- `test_timing_models.py`: Timing model implementations and edge cases
- `test_parallel_processing.py`: Parallel processing capabilities and thread safety
- `test_enhanced_monitoring.py`: Advanced monitoring features and resource tracking
- `test_profiles.py`: Configuration profile system validation
- `test_adapters.py`: Pipeline adapter functionality and validation
- `test_generators.py`: Read generation backends, FASTA parsing, factory, config validation
- `test_generate_integration.py`: End-to-end generate mode with multiplex, singleplex, mixed, and timing
- `test_mocks.py`: Mock community definitions, aliases, and species resolution
- `test_practical.py`: Practical tests using real NCBI genomes (Lambda, S. aureus, E. coli); requires datasets CLI
- `test_integration.py`: End-to-end workflow testing with various configurations
- `test_timing_integration.py`: Timing model integration with simulation workflow
- `test_edge_cases.py`: Error handling, permissions, and boundary conditions
- `test_performance.py`: Large dataset handling and performance benchmarks (marked as `slow`)

**Cross-Platform Considerations:**
- Tests accommodate case-insensitive filesystems (macOS) with unique naming strategies
- Graceful degradation for optional dependencies (psutil for enhanced monitoring)
- Thread-safe operations with proper resource cleanup

**Coverage Standards:**
- Minimum coverage threshold: 90%
- 524 tests across 31 test files
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
4. **Pipeline adapters**: Implement `PipelineAdapter` interface with validation logic
5. **Monitoring**: Use thread-safe `ProgressMonitor` methods for metrics collection
6. **Testing**: Include both unit tests and integration tests with performance considerations
7. **Configuration**: Add new parameters to `SimulationConfig` with appropriate validation
8. **Documentation**: Update both technical documentation and user-facing examples

## User Documentation

For end-user guides and tutorials, see:
- **[README.md](README.md)**: Main user documentation with installation, usage, and examples
- **[docs/quickstart.md](docs/quickstart.md)**: Quick start guide for new users
- **[docs/troubleshooting.md](docs/troubleshooting.md)**: Common issues and solutions
- **[examples/](examples/)**: Working code examples demonstrating all features
