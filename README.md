# NanoRun - Advanced Nanopore Sequencing Simulator

NanoRun is a comprehensive Python application designed for rigorous testing of nanopore sequencing analysis pipelines. The simulator accurately replicates the temporal and structural characteristics of Oxford Nanopore Technologies sequencing workflows by transferring FASTQ and POD5 files with sophisticated timing models, parallel processing capabilities, and real-time monitoring. This tool facilitates robust validation of bioinformatics pipelines under realistic sequencing conditions.

## Key Features

### Core Simulation Capabilities
- **Automated structure detection**: Intelligent recognition of singleplex and multiplex experimental designs through directory analysis
- **Multi-format file support**: Processing of FASTQ files (`.fastq`, `.fq`, `.fastq.gz`, `.fq.gz`) and Oxford Nanopore POD5 signal files (`.pod5`)
- **Advanced timing models**: Four distinct temporal simulation approaches for realistic sequencing pattern modeling
- **Parallel processing**: Concurrent file operations with configurable worker threads for high-throughput scenarios
- **Configuration profiles**: Pre-defined parameter sets optimized for specific sequencing applications and experimental scales

### Enhanced Monitoring and Control
- **Real-time progress tracking**: Live monitoring with predictive ETA calculation and performance trend analysis
- **Resource utilization monitoring**: CPU, memory, and disk I/O tracking with automatic performance warnings
- **Interactive controls**: Pause/resume functionality with graceful shutdown handling
- **Checkpoint system**: Automatic progress preservation for recovery from interruptions during long simulations
- **Performance analytics**: Throughput analysis with confidence scoring and bottleneck identification

### Pipeline Integration
- **Multi-pipeline support**: Built-in adapters for nanometanf, Kraken, miniknife, and generic bioinformatics workflows
- **Validation framework**: Automated structure and format verification for pipeline compatibility
- **Flexible output formats**: Support for both file copying and symbolic linking to accommodate storage constraints

## Installation

```bash
# Basic installation
pip install nanorun

# Installation with enhanced monitoring capabilities
pip install nanorun[enhanced]
```

## Usage

### Basic Invocation
```bash
nanorun <source_dir> <target_dir> [options]
```

### Essential Examples

#### Timing Model Selection
```bash
# Uniform intervals for deterministic testing
nanorun /data/source /watch/output --timing-model uniform --interval 5

# Random intervals with controlled variation
nanorun /data/source /watch/output --timing-model random --random-factor 0.3

# Poisson process for biologically realistic simulation
nanorun /data/source /watch/output --timing-model poisson --burst-probability 0.15

# Adaptive timing responding to processing bottlenecks
nanorun /data/source /watch/output --timing-model adaptive
```

#### Configuration Profiles
```bash
# Rapid sequencing scenario with optimized parameters
nanorun /data/source /watch/output --profile rapid_sequencing

# High-throughput simulation with parallel processing
nanorun /data/source /watch/output --profile high_throughput

# Development testing with accelerated intervals
nanorun /data/source /watch/output --profile development_testing

# List available profiles and their descriptions
nanorun --list-profiles
```

#### Enhanced Monitoring
```bash
# Enable comprehensive monitoring with resource tracking
nanorun /data/source /watch/output --monitor enhanced

# Detailed monitoring with verbose logging
nanorun /data/source /watch/output --monitor detailed

# Silent operation for automated testing
nanorun /data/source /watch/output --monitor none --quiet
```

#### Parallel Processing
```bash
# Enable parallel processing with custom worker count
nanorun /data/source /watch/output --parallel --worker-count 8

# Combine with configuration profile for optimized performance
nanorun /data/source /watch/output --profile high_throughput --parallel
```

#### Pipeline Validation
```bash
# Validate output compatibility with specific pipeline
nanorun /data/source /watch/output --pipeline nanometanf

# List supported pipeline adapters
nanorun --list-adapters

# Validate existing directory structure
nanorun --validate-pipeline kraken /path/to/output
```

### Configuration Parameters

#### Core Options
- `--interval SECONDS`: Base time interval between file operations (default: 5.0)
- `--operation {copy,link}`: File transfer method (default: copy)
- `--force-structure {singleplex,multiplex}`: Override automatic structure detection
- `--batch-size COUNT`: Files processed per time interval (default: 1)

#### Timing Model Configuration
- `--timing-model {uniform,random,poisson,adaptive}`: Temporal pattern selection
- `--random-factor FACTOR`: Variation magnitude for random model (0.0-1.0)
- `--burst-probability PROB`: Burst event probability for Poisson model
- `--burst-rate-multiplier MULT`: Rate increase during burst events

#### Processing Options
- `--parallel`: Enable concurrent file processing within batches
- `--worker-count COUNT`: Number of parallel worker threads (default: 4)

#### Monitoring Configuration
- `--monitor {default,detailed,enhanced,none}`: Progress monitoring level
- `--quiet`: Suppress progress output for automated workflows

## Timing Models

### Uniform Model
Provides constant intervals for deterministic testing scenarios requiring precise temporal control.

```bash
nanorun /data /output --timing-model uniform --interval 10
```

### Random Model
Introduces symmetric stochastic variation around the base interval, suitable for robustness testing under moderate temporal irregularity.

```bash
# ±30% variation around base interval
nanorun /data /output --timing-model random --interval 5 --random-factor 0.3
```

### Poisson Model
Implements biologically-motivated timing with burst behavior, accurately modeling the irregular nature of actual sequencing data generation.

```bash
# 15% probability of burst events with 3x rate increase
nanorun /data /output --timing-model poisson --burst-probability 0.15 --burst-rate-multiplier 3.0
```

### Adaptive Model
Dynamically adjusts intervals based on historical performance, simulating feedback mechanisms in real sequencing systems.

```bash
nanorun /data /output --timing-model adaptive --adaptation-rate 0.2
```

## Experimental Design Support

### Singleplex Configuration
Files located directly within the source directory represent single-sample experiments:

```
source_dir/
├── sample1.fastq
├── sample2.fastq.gz
└── sample3.pod5
```

Output preserves the flat structure:
```
target_dir/
├── sample1.fastq
├── sample2.fastq.gz
└── sample3.pod5
```

### Multiplex Configuration
Barcode-based sample organization for multiplexed experiments:

```
source_dir/
├── barcode01/
│   ├── reads1.fastq
│   └── reads2.fastq.gz
├── barcode02/
│   └── reads.fastq.gz
└── unclassified/
    └── unassigned.fastq
```

Hierarchical structure is preserved:
```
target_dir/
├── barcode01/
│   ├── reads1.fastq
│   └── reads2.fastq.gz
├── barcode02/
│   └── reads.fastq.gz
└── unclassified/
    └── unassigned.fastq
```

### Barcode Recognition
Supported naming conventions for automatic multiplex detection:
- `barcode##` (e.g., barcode01, barcode02)
- `BC##` (e.g., BC01, BC02)
- `bc##` (e.g., bc01, bc02)
- `unclassified` for unassigned reads

## Enhanced Monitoring Features

### Real-time Progress Display
```
[██████████████████████████████] 75.2% | 1,847/2,455 files | 12.3 files/sec | ETA: 2.1m ↗★★ | CPU: 45% | RAM: 62% | Elapsed: 2.5m
```

### Performance Indicators
- **Progress bar**: Visual completion status with file count
- **Throughput**: Current processing rate in files per second
- **ETA prediction**: Estimated time to completion with trend analysis
  - ↗ Improving performance
  - ↘ Degrading performance  
  - → Stable performance
- **Confidence**: Star rating (★) indicating prediction reliability
- **Resource usage**: Real-time CPU and memory utilization
- **Elapsed time**: Total simulation duration

### Interactive Controls
- **Ctrl+C**: Graceful shutdown with summary statistics
- **Pause/Resume**: Process control during long simulations
- **Automatic checkpointing**: Progress preservation every 10 files

## Pipeline Integration

### Primary Integration: nanometanf
Optimized for testing the nanometanf real-time taxonomic classification pipeline:

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
Built-in adapters provide validation for multiple bioinformatics workflows:

- **nanometanf**: Real-time taxonomic classification with MinKNOW integration
- **Kraken**: k-mer based taxonomic assignment
- **miniknife**: Lightweight classification for resource-constrained environments
- **Generic**: Customizable adapter for arbitrary pipeline requirements

### Validation Workflow
```bash
# Simulate data with pipeline-specific validation
nanorun /data/source /watch/output --pipeline nanometanf --monitor enhanced

# Post-simulation validation report
nanorun --validate-pipeline kraken /watch/output
```

## Performance Characteristics

### Throughput Optimization
- **Sequential processing**: Suitable for development and small datasets (< 100 files)
- **Parallel processing**: Optimized for production workflows (> 1,000 files)
- **Batch processing**: Configurable batch sizes for memory management
- **Resource monitoring**: Automatic detection of CPU, memory, and I/O bottlenecks

### Scalability Testing
The simulator accommodates diverse experimental scales:
- **Development**: 10-100 files with rapid intervals
- **Validation**: 100-1,000 files with realistic timing
- **Production**: 1,000-10,000+ files with parallel processing

## Technical Requirements

- **Python**: Version 3.7 or higher with full type annotation support
- **Core dependencies**: Standard library only for basic functionality
- **Enhanced features**: Optional psutil dependency for resource monitoring
- **Platform compatibility**: POSIX-compliant operating systems (Linux, macOS, Unix)
- **Storage**: Minimal footprint with optional symbolic linking for large datasets

## Development and Contribution

### Installation for Development
```bash
git clone https://github.com/FOI-Bioinformatics/nanorun.git
cd nanorun
pip install -e .[enhanced,dev]
```

### Testing Framework
```bash
# Run comprehensive test suite
pytest

# Generate coverage report
pytest --cov=nanopore_simulator --cov-report=html

# Performance benchmarks
pytest tests/test_performance.py -m slow
```

### Code Quality Standards
```bash
# Format code
black nanopore_simulator/ tests/

# Type checking
mypy nanopore_simulator/

# Linting
flake8 nanopore_simulator/
```

## License and Attribution

This software is distributed under the MIT License and developed for research applications in bioinformatics pipeline validation. The simulator is designed to complement the nanometanf taxonomic classification pipeline and supports the broader Oxford Nanopore Technologies ecosystem.

**Developed by**: [FOI Bioinformatics](https://github.com/FOI-Bioinformatics) - Swedish Defence Research Agency  
**Repository**: https://github.com/FOI-Bioinformatics/nanorun  
**Documentation**: Comprehensive user guides and API documentation available in the repository