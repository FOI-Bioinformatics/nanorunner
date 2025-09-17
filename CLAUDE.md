# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is `nanorun` - a comprehensive nanopore sequencing run simulator designed for testing bioinformatics pipelines. It implements sophisticated temporal modeling, parallel processing capabilities, and real-time monitoring to accurately simulate nanopore sequencing workflows. The system supports multiple timing models (uniform, random, Poisson, adaptive), configuration profiles for different experimental scenarios, pipeline-specific adapters, and enhanced progress monitoring with resource tracking.

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
nanorun --help
nanorun --list-profiles
nanorun --list-adapters
nanorun /source /target --profile rapid_sequencing --monitor enhanced
```

## Architecture

### Core Components

**nanopore_simulator/core/**
- `config.py`: SimulationConfig dataclass with comprehensive validation for all simulation parameters
- `detector.py`: FileStructureDetector for automatic singleplex/multiplex structure recognition
- `simulator.py`: NanoporeSimulator orchestration class with enhanced error handling and resource management
- `timing.py`: Timing model implementations (UniformTimingModel, RandomTimingModel, PoissonTimingModel, AdaptiveTimingModel)
- `profiles.py`: Configuration profile system with built-in profiles for common sequencing scenarios
- `adapters.py`: Pipeline adapter framework for nanometanf, Kraken, miniknife, and generic pipelines
- `monitoring.py`: Enhanced progress monitoring with resource tracking, predictive ETA, and interactive controls

**nanopore_simulator/cli/**
- `main.py`: Comprehensive command-line interface with profile support, timing model selection, and monitoring options

### Key Design Patterns

**Data Flow:**
1. CLI parses arguments and handles profile/adapter commands
2. Configuration created from profiles or direct parameters with timing model specification
3. FileStructureDetector analyzes source directory structure  
4. NanoporeSimulator initializes with timing model, parallel processing, and monitoring components
5. Enhanced progress monitoring tracks performance with resource usage and predictive analytics
6. Files processed in batches with sophisticated timing models and optional parallelization

**Timing Model Architecture:**
- Abstract `TimingModel` base class with factory pattern implementation
- Uniform: Constant intervals for deterministic testing
- Random: Symmetric variation around base interval with configurable randomness factor
- Poisson: Biologically-realistic intervals with burst behavior modeling
- Adaptive: Dynamic interval adjustment based on historical performance

**Enhanced Monitoring System:**
- Thread-safe `ProgressMonitor` with real-time resource tracking
- Predictive ETA calculation with trend analysis (improving/degrading/stable)
- Interactive controls (pause/resume) with signal handling
- Automatic checkpoint/resume system for long simulations
- Performance warning detection (high CPU/memory usage, low throughput)

**Configuration Profile System:**
- Built-in profiles: `rapid_sequencing`, `accurate_mode`, `development_testing`, `high_throughput`, etc.
- Profile recommendations based on file count and use case
- Override capability for profile-based configurations

**Pipeline Adapter Framework:**
- Standardized validation interface for different bioinformatics pipelines
- Built-in adapters: NanometanfAdapter, KrackenAdapter, MiniknifeAdapter, GenericAdapter
- File pattern validation and structure requirements checking

### Supported File Types
Extensions: `.fastq`, `.fq`, `.fastq.gz`, `.fq.gz`, `.pod5`

### Parallel Processing
- Optional ThreadPoolExecutor-based parallel file processing within batches
- Configurable worker thread count with automatic scaling
- Thread-safe progress monitoring and error handling
- Performance optimization for high-throughput scenarios

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
- `test_integration.py`: End-to-end workflow testing with various configurations
- `test_timing_integration.py`: Timing model integration with simulation workflow
- `test_edge_cases.py`: Error handling, permissions, and boundary conditions
- `test_performance.py`: Large dataset handling and performance benchmarks (marked as `slow`)

**Cross-Platform Considerations:**
- Tests accommodate case-insensitive filesystems (macOS) with unique naming strategies
- Graceful degradation for optional dependencies (psutil for enhanced monitoring)
- Thread-safe operations with proper resource cleanup

**Coverage Standards:**
- Minimum coverage threshold: 90% (currently >99%)
- Comprehensive integration testing with multiple timing models and configurations
- Performance regression testing for parallel processing scenarios

## Integration Context

### Primary Integration: nanometanf Pipeline
The simulator is optimized for testing the nanometanf real-time taxonomic classification pipeline:

```bash
# Configure nanometanf for simulated data consumption
nextflow run nanometanf \
    --realtime_mode \
    --nanopore_output_dir /watch/output \
    --file_pattern "**/*.fastq{,.gz}" \
    --batch_size 10 \
    --batch_interval "5min"
```

### Multi-Pipeline Support
Pipeline adapters enable validation and testing across multiple bioinformatics workflows:
- **Nanometanf**: Real-time taxonomic classification
- **Kraken**: k-mer based taxonomic assignment
- **Miniknife**: Lightweight classification tool
- **Generic**: Customizable adapter for arbitrary pipelines

### Realistic Simulation Scenarios
The timing models provide biologically-motivated temporal patterns:
- **Poisson model**: Simulates natural sequencing irregularities with burst behavior
- **Adaptive model**: Responds to processing bottlenecks with dynamic adjustment
- **Random model**: Introduces controlled stochastic variation for robustness testing

## Configuration Notes

- **Dependencies**: Standard library only for core functionality; optional psutil for enhanced monitoring
- **Python compatibility**: 3.7+ with full type hint support
- **Performance**: Optimized for datasets ranging from development (10s of files) to production scale (10,000+ files)
- **Resource monitoring**: Optional CPU, memory, and disk I/O tracking with performance warnings
- **Extensibility**: Plugin architecture for custom timing models, adapters, and monitoring components
- **Console script entry point**: `nanorun`
- **Enhanced features**: Available via `pip install nanorun[enhanced]` for resource monitoring capabilities

## Development Patterns

When extending functionality:
1. **Timing models**: Inherit from `TimingModel` abstract base class with `next_interval()` implementation
2. **Pipeline adapters**: Implement `PipelineAdapter` interface with validation logic
3. **Monitoring**: Use thread-safe `ProgressMonitor` methods for metrics collection
4. **Testing**: Include both unit tests and integration tests with performance considerations
5. **Configuration**: Add new parameters to `SimulationConfig` with appropriate validation
6. **Documentation**: Update both technical documentation and user-facing examples