# NanoRunner Examples

This directory contains practical examples demonstrating nanorunner's
capabilities. All examples use the v3.0.0 API.

## Prerequisites

- nanorunner installed: `pip install -e .`
- Python 3.9 or higher
- Sample data in `examples/sample_data/` (included in the repository)

## Quick Start

Run any example from the repository root:

```bash
python examples/01_basic_simulation.py
```

## Available Examples

### 01_basic_simulation.py
**Level**: Beginner
**Time**: ~1 minute
**Description**: Minimal working example showing basic file replay from a
singleplex source directory using `ReplayConfig` and `run_replay`.

Key concepts: `ReplayConfig`, `run_replay`, `operation`, `timing_model`

### 02_timing_models.py
**Level**: Intermediate
**Time**: ~3 minutes
**Description**: Demonstrates all four timing models (uniform, random,
Poisson, adaptive) by running the same source data under each model.
Observing the output timestamps illustrates how temporal patterns differ.

Key concepts: `timing_model`, `timing_params`, `ReplayConfig`

### 03_parallel_processing.py
**Level**: Intermediate
**Time**: ~2 minutes
**Description**: Compares sequential and parallel replay against the same
multiplex source data. Shows the `parallel`, `workers`, and `batch_size`
parameters. Enables enhanced resource monitoring when psutil is installed.

Key concepts: `parallel`, `workers`, `batch_size`, `monitor_type`

### 04_configuration_profiles.py
**Level**: Intermediate
**Time**: ~2 minutes
**Description**: Demonstrates the built-in configuration profiles using
`get_profile`, `apply_profile`, and the `PROFILES` dict. Shows how to
override individual profile parameters before constructing a config.

Key concepts: `apply_profile`, `PROFILES`, profile field name mapping

### 05_pipeline_integration.py
**Level**: Advanced
**Time**: ~3 minutes
**Description**: Validates simulation output against pipeline-specific file
pattern requirements using `validate_output` and the `ADAPTERS` registry.
Covers nanometa and kraken adapters and shows what a validation failure
looks like.

Key concepts: `validate_output`, `ADAPTERS`, `list_adapters`

### 06_practical_genome_test.py
**Level**: Advanced
**Time**: ~5 minutes (first run downloads genomes; subsequent runs use cache)
**Description**: Downloads Lambda phage, S. aureus, and E. coli reference
genomes from NCBI and runs five progressive generate-mode scenarios:
singleplex, multiple genomes, multiplex barcodes, mixed reads, and Poisson
timing. Validates FASTQ output structure after each scenario.

Key concepts: `GenerateConfig`, `run_generate`, `structure`, `mix_reads`,
`timing_params`, NCBI datasets CLI

## API Reference

The examples use the following public imports:

```python
# Core entry points
from nanopore_simulator import ReplayConfig, GenerateConfig
from nanopore_simulator import run_replay, run_generate

# Configuration profiles
from nanopore_simulator.profiles import get_profile, apply_profile, PROFILES, list_profiles

# Pipeline adapters
from nanopore_simulator.adapters import validate_output, ADAPTERS, list_adapters

# Dependency checking
from nanopore_simulator.deps import check_all_dependencies

# Timing models (direct use; normally configured via ReplayConfig/GenerateConfig)
from nanopore_simulator.timing import create_timing_model

# Read generators (direct use; normally configured via GenerateConfig)
from nanopore_simulator.generators import create_generator, detect_available_backends

# Mock communities
from nanopore_simulator.mocks import get_mock_community, MOCK_COMMUNITIES
```

## Sample Data

The `sample_data/` directory contains minimal test files:

```
sample_data/
├── singleplex/
│   ├── sample1.fastq
│   └── sample2.fastq
└── multiplex/
    ├── barcode01/
    │   └── reads.fastq
    └── barcode02/
        └── reads.fastq
```

## Cleaning Up

All examples use `tempfile.mkdtemp` and clean up automatically.
To remove the genome cache created by example 06:

```bash
rm -rf ~/.cache/nanorunner_genomes/
```

## Troubleshooting

**ImportError on nanopore_simulator**: Verify nanorunner is installed:
`pip install -e .`

**Sample data not found**: Run examples from the repository root directory.

**datasets command not found** (example 06): Install the NCBI datasets CLI:
`conda install -c conda-forge ncbi-datasets-cli`

**No enhanced monitoring metrics**: Install psutil:
`pip install nanorunner[enhanced]`

## Next Steps

After exploring these examples:

1. Review the [full documentation](../README.md)
2. Read [docs/quickstart.md](../docs/quickstart.md) for a guided introduction
3. See [docs/troubleshooting.md](../docs/troubleshooting.md) for common issues
4. Try with your own sequencing data
5. Integrate with your bioinformatics pipeline
