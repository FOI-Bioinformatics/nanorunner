# NanoRunner Examples

This directory contains practical examples demonstrating NanoRunner's capabilities.

## Prerequisites

- NanoRunner installed: `pip install git+https://github.com/FOI-Bioinformatics/nanorunner.git@v2.0.0`
- Python 3.9 or higher
- Sample data provided in `sample_data/` directory

## Quick Start

Run any example with:
```bash
python examples/01_basic_simulation.py
```

## Available Examples

### 01_basic_simulation.py
**Level**: Beginner
**Time**: ~1 minute
**Description**: Minimal working example showing basic file simulation from singleplex data

### 02_timing_models.py
**Level**: Intermediate
**Time**: ~3 minutes
**Description**: Demonstrates all four timing models (uniform, random, Poisson, adaptive)

### 03_parallel_processing.py
**Level**: Intermediate
**Time**: ~2 minutes
**Description**: High-throughput simulation with parallel processing and monitoring

### 04_configuration_profiles.py
**Level**: Intermediate
**Time**: ~2 minutes
**Description**: Using built-in configuration profiles for common scenarios

### 05_pipeline_integration.py
**Level**: Advanced
**Time**: ~3 minutes
**Description**: Pipeline adapter validation and integration testing

## Sample Data

The `sample_data/` directory contains minimal test files for running examples:

```
sample_data/
├── singleplex/
│   ├── sample1.fastq (100 reads)
│   └── sample2.fastq (100 reads)
└── multiplex/
    ├── barcode01/
    │   └── reads.fastq (100 reads)
    └── barcode02/
        └── reads.fastq (100 reads)
```

## Cleaning Up

After running examples, temporary output directories are created:
```bash
# Remove all example output
rm -rf /tmp/nanorunner_*
```

## Troubleshooting

**Permission errors**: Ensure write access to `/tmp` directory
**Import errors**: Verify nanorunner is installed correctly
**Sample data missing**: Run examples from repository root

## Next Steps

After exploring these examples:
1. Read the [full documentation](../README.md)
2. Review [advanced tutorials](../docs/)
3. Try with your own data
4. Integrate with your pipeline

## Contributing

Found an issue or have an idea for a new example?
[Open an issue](https://github.com/FOI-Bioinformatics/nanorunner/issues)
