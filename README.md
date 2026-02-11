# NanoRunner - Nanopore Sequencing Simulator

![CI](https://github.com/FOI-Bioinformatics/nanorunner/workflows/CI/badge.svg)
![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)
![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)

NanoRunner is a Python tool for testing nanopore sequencing analysis pipelines. It operates in two modes:

- **Replay mode**: Transfers existing FASTQ and POD5 files from a source directory to a target directory with configurable timing, replicating the temporal characteristics of a real sequencing run.
- **Generate mode**: Produces simulated nanopore FASTQ reads from genome FASTA files, delivering them incrementally with the same timing models.

Both modes support singleplex and multiplex (barcoded) output structures, multiple timing models, parallel processing, and real-time monitoring. The output is compatible with downstream pipelines such as Nanometa Live and Kraken.

## Key Features

### Core Capabilities
- **Two operation modes**: Replay existing sequencing files or generate simulated reads from genomes
- **Automated structure detection**: Recognition of singleplex and multiplex experimental designs through directory analysis
- **Multi-format file support**: FASTQ files (`.fastq`, `.fq`, `.fastq.gz`, `.fq.gz`), POD5 signal files (`.pod5`), and genome FASTA files (`.fa`, `.fasta`, gzipped variants)
- **Timing models**: Four temporal simulation approaches (uniform, random, Poisson, adaptive)
- **Parallel processing**: Concurrent file operations with configurable worker threads
- **Configuration profiles**: Pre-defined parameter sets for common sequencing and generation scenarios

### Read Generation
- **Built-in generator**: Error-free random subsequences with log-normal length distribution. No external dependencies. For reads with error profiles, use badread or NanoSim.
- **Badread integration**: Optional wrapper for the badread simulator (requires separate installation)
- **NanoSim integration**: Optional wrapper for NanoSim (requires separate installation)
- **Auto-detection**: Automatically selects the best available backend
- **Multiplex output**: Each genome assigned to a barcode directory (`barcode01/`, `barcode02/`, ...)
- **Singleplex output**: Files in target root, optionally mixing reads from multiple genomes

### Monitoring and Control
- **Real-time progress tracking**: Live monitoring with predictive ETA calculation and performance trend analysis
- **Resource utilization monitoring**: CPU, memory, and disk I/O tracking with automatic performance warnings
- **Interactive controls**: Pause/resume functionality with graceful shutdown handling
- **Checkpoint system**: Automatic progress preservation for recovery from interruptions

### Pipeline Integration
- **Multi-pipeline support**: Built-in adapters for Nanometa Live, Kraken, and generic workflows
- **Validation framework**: Automated structure and format verification for pipeline compatibility
- **Flexible output**: Support for file copying, symbolic linking, and read generation

## Installation

### From GitHub

```bash
# Latest stable release (v2.0.2)
pip install git+https://github.com/FOI-Bioinformatics/nanorunner.git@v2.0.2

# Development version (main branch)
pip install git+https://github.com/FOI-Bioinformatics/nanorunner.git@main

# With enhanced monitoring features
pip install "nanorunner[enhanced] @ git+https://github.com/FOI-Bioinformatics/nanorunner.git@v2.0.2"
```

### For Development

```bash
git clone https://github.com/FOI-Bioinformatics/nanorunner.git
cd nanorunner
pip install -e .[enhanced,dev]
```

### Verify Installation

```bash
nanorunner --version  # Should output: nanorunner 2.0.2
nanorunner --help     # Display all available subcommands
nanorunner list-profiles    # Show built-in configuration profiles
nanorunner list-generators  # Show available read generation backends
nanorunner list-mocks       # Show available mock communities
```

## Usage

### Replay Mode

Transfer existing sequencing files with configurable timing:

```bash
nanorunner replay --source <source_dir> --target <target_dir> [options]
```

#### Examples

```bash
# Uniform intervals for deterministic testing
nanorunner replay -s /data/source -t /watch/output --timing-model uniform --interval 5

# Random intervals with controlled variation
nanorunner replay -s /data/source -t /watch/output --timing-model random --random-factor 0.3

# Poisson process for irregular timing with burst clusters
nanorunner replay -s /data/source -t /watch/output --timing-model poisson --burst-probability 0.15

# Adaptive timing with smoothly varying intervals
nanorunner replay -s /data/source -t /watch/output --timing-model adaptive

# Use a configuration profile
nanorunner replay -s /data/source -t /watch/output --profile bursty

# High-throughput with parallel processing
nanorunner replay -s /data/source -t /watch/output --profile high_throughput --parallel
```

### Generate Mode

Produce simulated reads from genome FASTA files:

```bash
nanorunner generate --genomes <fasta_files...> --target <target_dir> [options]
```

#### Examples

```bash
# Generate reads from two genomes (multiplex: each genome gets a barcode directory)
nanorunner generate --genomes genome1.fa genome2.fa -t /watch/output --interval 5

# Singleplex output (flat directory)
nanorunner generate --genomes genome.fa -t /watch/output --force-structure singleplex

# Mix reads from multiple genomes into shared files
nanorunner generate --genomes g1.fa g2.fa -t /watch/output --force-structure singleplex --mix-reads

# Specify generation parameters
nanorunner generate --genomes genome.fa -t /watch/output \
    --read-count 5000 \
    --mean-read-length 8000 \
    --reads-per-file 200 \
    --output-format fastq.gz

# Use a specific backend
nanorunner generate --genomes genome.fa -t /watch/output --generator-backend builtin

# Use a generation profile with Poisson timing
nanorunner generate --genomes genome.fa -t /watch/output --profile generate_standard

# List available backends
nanorunner list-generators
```

#### Generate Mode Output Structure

**Multiplex** (default when multiple genomes provided):
```
target_dir/
├── barcode01/
│   ├── genome1_reads_0000.fastq.gz
│   └── genome1_reads_0001.fastq.gz
└── barcode02/
    ├── genome2_reads_0000.fastq.gz
    └── genome2_reads_0001.fastq.gz
```

**Singleplex** (`--force-structure singleplex`):
```
target_dir/
├── genome1_reads_0000.fastq.gz
├── genome1_reads_0001.fastq.gz
├── genome2_reads_0000.fastq.gz
└── genome2_reads_0001.fastq.gz
```

#### Read Generation Backends

| Backend | Dependencies | Description |
|---------|-------------|-------------|
| `builtin` | None | Error-free random subsequences with log-normal length distribution. No error model; suitable for testing pipeline structure and connectivity. |
| `badread` | [badread](https://github.com/rrwick/Badread) | Nanopore read simulation with error models |
| `nanosim` | [NanoSim](https://github.com/bcgsc/NanoSim) | Statistical read simulation from training data |
| `auto` | Varies | Selects the best available backend (badread > nanosim > builtin) |

### Species and Mock Community Generation

Generate reads from species names or preset mock communities without providing genome files directly:

```bash
# Generate from species names (resolves via GTDB/NCBI)
nanorunner generate --species "Escherichia coli" "Staphylococcus aureus" -t /output

# Use a preset mock community
nanorunner generate --mock zymo_d6300 -t /output

# Pure samples (each species in separate barcode)
nanorunner generate --species "E. coli" "S. aureus" --sample-type pure -t /output

# Mixed samples with custom abundances
nanorunner generate --species "E. coli" "S. aureus" --sample-type mixed --abundances 0.7 0.3 -t /output

# List available mock communities
nanorunner list-mocks

# Pre-download genomes for offline use
nanorunner download --mock zymo_d6300
```

#### Available Mock Communities

| Mock ID | Description | Organisms |
|---------|-------------|-----------|
| `zymo_d6300` | Zymo D6300 Standard (even) | 8 bacteria + 2 yeasts |
| `zymo_d6310` | Zymo D6310 Log Distribution (7 orders of magnitude) | 8 bacteria + 2 yeasts |
| `zymo_d6331` | Zymo D6331 Gut Microbiome Standard | 21 strains, 17 species |
| `atcc_msa1002` | ATCC MSA-1002 20-strain even mix (5% each) | 20 bacteria |
| `atcc_msa1003` | ATCC MSA-1003 20-strain staggered mix (0.02%-18%) | 20 bacteria |
| `cdc_select_agents` | CDC/USDA Tier 1 bacterial select agents | 6 species |
| `eskape` | ESKAPE nosocomial pathogens | 6 species |
| `respiratory` | Community-acquired respiratory pathogens | 6 species |
| `who_critical` | WHO Critical Priority carbapenem-resistant pathogens | 5 species |
| `bloodstream` | Bloodstream infection panel | 5 bacteria + 1 yeast |
| `wastewater` | Wastewater surveillance indicators and pathogens | 6 species |
| `quick_single` | Single species (E. coli) for minimal testing | 1 species |
| `quick_3species` | Minimal 3-species test mock | 3 species |
| `quick_gut5` | Simple 5-species gut microbiome mock | 5 species |
| `quick_pathogens` | Clinically relevant nosocomial pathogens | 5 species |

Use `nanorunner list-mocks` to see all communities, aliases, and descriptions.

### Enhanced Monitoring

```bash
# Enable comprehensive monitoring with resource tracking
nanorunner replay -s /data/source -t /watch/output --monitor enhanced

# Detailed monitoring with verbose logging
nanorunner replay -s /data/source -t /watch/output --monitor detailed

# Silent operation for automated testing
nanorunner replay -s /data/source -t /watch/output --monitor none --quiet
```

### Pipeline Validation

```bash
# Validate output compatibility with specific pipeline during replay
nanorunner replay -s /data/source -t /watch/output --pipeline nanometa

# List supported pipeline adapters
nanorunner list-adapters

# Validate existing directory structure
nanorunner validate --pipeline kraken --target /path/to/output
```

### Configuration Profiles

```bash
# List all available profiles
nanorunner list-profiles

# Get recommendations based on source data
nanorunner recommend --source /path/to/data

# Get an overview of all profiles (no source needed)
nanorunner recommend
```

Built-in profiles include: `development`, `steady`, `bursty`, `high_throughput`, `gradual_drift`, `generate_test`, `generate_standard`.

## Configuration Parameters

### Core Options
- `--interval SECONDS`: Base time interval between file operations (default: 5.0)
- `--operation {copy,link}`: File transfer method for replay mode (default: copy)
- `--force-structure {singleplex,multiplex}`: Override automatic structure detection
- `--batch-size COUNT`: Files processed per time interval (default: 1)
- `--profile NAME`: Use a predefined configuration profile

### Timing Model Configuration
- `--timing-model {uniform,random,poisson,adaptive}`: Temporal pattern selection
- `--random-factor FACTOR`: Variation magnitude for random model (0.0-1.0)
- `--burst-probability PROB`: Burst event probability for Poisson model
- `--burst-rate-multiplier MULT`: Rate increase during burst events
- `--adaptation-rate RATE`: Learning speed for adaptive model (0.0-1.0, default: 0.1)
- `--history-size SIZE`: Lookback window for adaptive model (default: 10)

### Read Generation Options
- `--genomes FASTA [FASTA ...]`: Input genome FASTA files (activates generate mode)
- `--generator-backend {auto,builtin,badread,nanosim}`: Read generation backend (default: auto)
- `--read-count INT`: Total reads to generate across all genomes (default: 1000)
- `--mean-read-length INT`: Mean read length in bases (default: 5000)
- `--reads-per-file INT`: Reads per output file (default: 100)
- `--output-format {fastq,fastq.gz}`: Output file format (default: fastq.gz)
- `--mix-reads`: Mix reads from all genomes into shared files (singleplex mode)

### Processing Options
- `--parallel`: Enable concurrent file processing within batches
- `--worker-count COUNT`: Number of parallel worker threads (default: 4)

### Monitoring Configuration
- `--monitor {default,detailed,enhanced,none}`: Progress monitoring level
- `--quiet`: Suppress progress output for automated workflows

## Timing Models

### Uniform Model
Provides constant intervals for deterministic testing scenarios requiring precise temporal control.

```bash
nanorunner replay -s /data -t /output --timing-model uniform --interval 10
```

### Random Model
Introduces symmetric stochastic variation around the base interval, suitable for robustness testing under moderate temporal irregularity.

```bash
# +/-30% variation around base interval
nanorunner replay -s /data -t /output --timing-model random --interval 5 --random-factor 0.3
```

### Poisson Model
Generates intervals from a mixture of two exponential distributions (base rate and burst rate), producing irregular timing with occasional short-interval clusters.

```bash
# 15% probability of burst events with 3x rate increase
nanorunner replay -s /data -t /output --timing-model poisson --burst-probability 0.15 --burst-rate-multiplier 3.0
```

### Adaptive Model
Generates exponentially distributed intervals with a rate parameter that drifts over time via exponential moving average of recent intervals.

```bash
# Default adaptive behavior
nanorunner replay -s /data -t /output --timing-model adaptive

# Fast adaptation for dynamic environments
nanorunner replay -s /data -t /output --timing-model adaptive --adaptation-rate 0.5

# Conservative adaptation with extended history
nanorunner replay -s /data -t /output --timing-model adaptive --adaptation-rate 0.05 --history-size 30
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

### Barcode Recognition
Supported naming conventions for automatic multiplex detection:
- `barcode##` (e.g., barcode01, barcode02)
- `BC##` (e.g., BC01, BC02)
- `bc##` (e.g., bc01, bc02)
- `unclassified` for unassigned reads

## Enhanced Monitoring Features

### Real-time Progress Display
```
[==============================] 75.2% | 1,847/2,455 files | 12.3 files/sec | ETA: 2.1m | CPU: 45% | RAM: 62% | Elapsed: 2.5m
```

### Interactive Controls
- **Ctrl+C**: Graceful shutdown with summary statistics
- **Pause/Resume**: Process control during long simulations
- **Automatic checkpointing**: Progress preservation every 10 files

## Pipeline Integration

### Primary Integration: Nanometa Live
Both replay and generate modes produce output compatible with Nanometa Live's real-time monitoring.

### Multi-Pipeline Support
Built-in adapters provide validation for multiple bioinformatics workflows:

- **nanometa**: Nanometa Live real-time taxonomic analysis pipeline
- **kraken**: Kraken2/KrakenUniq taxonomic classification pipeline
- **Generic**: Customizable adapter for arbitrary pipeline requirements

## Technical Requirements

- **Python**: Version 3.9 or higher
- **Core dependencies**: Standard library only for basic functionality (including built-in read generation)
- **Enhanced features**: Optional psutil dependency for resource monitoring
- **Optional read generators**: badread and/or NanoSim for higher-fidelity read simulation
- **Platform compatibility**: POSIX-compliant operating systems (Linux, macOS, Unix)
- **Testing**: 730 tests across 37 test files

## Development and Contribution

### Installation for Development
```bash
git clone https://github.com/FOI-Bioinformatics/nanorunner.git
cd nanorunner
pip install -e .[enhanced,dev]
```

### Testing Framework

```bash
# Run complete test suite
pytest

# Run fast tests only (exclude slow integration tests)
pytest -m "not slow"

# Run specific test modules
pytest tests/test_cli.py                    # CLI interface tests
pytest tests/test_timing_models.py          # Timing model validation
pytest tests/test_generators.py             # Read generation backends
pytest tests/test_generate_integration.py   # Generate mode end-to-end
pytest tests/test_mocks.py                  # Mock community definitions
pytest tests/test_species.py                # Species name resolution
pytest tests/test_practical.py              # Practical tests with real NCBI genomes

# Generate coverage report
pytest --cov=nanopore_simulator --cov-report=html --cov-report=term-missing
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

## Documentation

Guides and references are available in the [docs/](docs/) directory:

- **[Quick Start Guide](docs/quickstart.md)**: Step-by-step setup and first simulation
- **[Troubleshooting Guide](docs/troubleshooting.md)**: Solutions for common installation and runtime issues
- **[Examples](examples/)**: Working code demonstrating timing models, profiles, generation, and pipeline integration

## Troubleshooting

Common issues and solutions:
- **Python version errors**: Ensure Python 3.9+ is installed
- **Permission denied**: Use `--user` flag or check target directory permissions
- **Import errors**: Verify installation with `pip show nanorunner`
- **Enhanced monitoring unavailable**: Install with `pip install "nanorunner[enhanced] @ git+..."`

For detailed troubleshooting steps, see [docs/troubleshooting.md](docs/troubleshooting.md).

## Support and Contribution

- **Issues**: [Search existing issues](https://github.com/FOI-Bioinformatics/nanorunner/issues) or [report a new issue](https://github.com/FOI-Bioinformatics/nanorunner/issues/new/choose)
- **Discussions**: [Ask questions](https://github.com/FOI-Bioinformatics/nanorunner/discussions)
- **Contributing**: See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines

## License and Attribution

This software is distributed under the MIT License and developed for research applications in bioinformatics pipeline validation. The simulator is designed to complement the Nanometa Live taxonomic analysis pipeline and supports the broader Oxford Nanopore Technologies ecosystem.

**Developed by**: [FOI Bioinformatics](https://github.com/FOI-Bioinformatics) - Swedish Defence Research Agency
**Repository**: https://github.com/FOI-Bioinformatics/nanorunner
