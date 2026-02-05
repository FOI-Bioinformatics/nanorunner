# NanoRunner Documentation

Comprehensive guides and references for the NanoRunner nanopore sequencing simulator.

## Table of Contents

- [User Guides](#user-guides)
- [Developer Documentation](#developer-documentation)
- [Testing Documentation](#testing-documentation)
- [Quick Links](#quick-links)

## User Guides

### Getting Started
- **[Quick Start Guide](quickstart.md)**: Step-by-step setup and first simulation
- **[Troubleshooting Guide](troubleshooting.md)**: Solutions for common installation and runtime issues
- **[Main README](../README.md)**: Complete feature documentation, examples, and usage

### Working Examples
- **[Examples Directory](../examples/)**: Working code demonstrating timing models, profiles, and pipeline integration
- **[Sample Data](../examples/sample_data/)**: Test FASTQ files for immediate experimentation

## Developer Documentation

### Development Setup
- **[CLAUDE.md](../CLAUDE.md)**: Developer guide for AI assistants and contributors
- **[CONTRIBUTING.md](../CONTRIBUTING.md)**: Contribution guidelines and development workflow
- **[CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md)**: Community standards and expectations

### Architecture & Design
- **Core Components**: See [CLAUDE.md - Architecture](../CLAUDE.md#architecture)
- **Timing Models**: Uniform, Random, Poisson, Adaptive implementations
- **Pipeline Adapters**: Framework for nanometanf, Kraken, miniknife integration

## Testing Documentation

### Test Suite Overview
- **[Testing Guide](testing.md)**: Comprehensive guide covering test categories, running tests, organization, and contributing

### Current Status
- **Test Count**: 524 tests across 31 test files
- **Coverage**: 97% on core components

## Quick Links

### For First-Time Users
1. [Quick Start Guide](quickstart.md) - Get running in 5 minutes
2. [Main README](../README.md) - Full feature documentation
3. [Examples](../examples/) - Working code samples

### For Developers
1. [CLAUDE.md](../CLAUDE.md) - Development guidelines
2. [Testing Guide](testing.md) - How to run and write tests
3. [CONTRIBUTING.md](../CONTRIBUTING.md) - Contribution workflow

### For Troubleshooting
1. [Troubleshooting Guide](troubleshooting.md) - Common issues
2. [GitHub Issues](https://github.com/FOI-Bioinformatics/nanorunner/issues) - Report problems
3. [GitHub Discussions](https://github.com/FOI-Bioinformatics/nanorunner/discussions) - Ask questions

## Documentation Structure

```
nanorunner/
├── README.md                       # Main user documentation
├── CLAUDE.md                       # Developer guide
├── CONTRIBUTING.md                 # Contribution guidelines
├── CODE_OF_CONDUCT.md              # Community standards
├── CHANGELOG.md                    # Version history
├── docs/
│   ├── README.md                   # This file - documentation index
│   ├── quickstart.md               # Quick start guide
│   ├── troubleshooting.md          # Common issues and solutions
│   └── testing.md                  # Comprehensive testing guide
└── examples/
    ├── README.md                   # Examples overview
    ├── 01_basic_simulation.py
    ├── 02_timing_models.py
    ├── 03_parallel_processing.py
    ├── 04_configuration_profiles.py
    ├── 05_pipeline_integration.py
    ├── 06_practical_genome_test.py
    └── sample_data/                # Test FASTQ files
```

## Version Information

- **Current Version**: 2.0.2
- **Python Requirement**: 3.9+
- **Status**: Production/Stable
- **Last Updated**: 2026-02-03