# NanoRunner documentation

Reference material for the NanoRunner nanopore sequencing run simulator.

## User documentation

- [Quick start](quickstart.md) -- installation and first simulation
- [Troubleshooting](troubleshooting.md) -- installation and runtime issues
- [Main README](../README.md) -- feature overview, examples, and CLI reference
- [Examples](../examples/) -- working scripts for timing models, profiles,
  parallel processing, and pipeline integration
- [Sample data](../examples/sample_data/) -- small FASTQ files for
  experimentation

## Developer documentation

- [CLAUDE.md](../CLAUDE.md) -- architecture and contributor notes
- [CONTRIBUTING.md](../CONTRIBUTING.md) -- contribution workflow
- [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) -- community standards
- [Testing guide](testing.md) -- test categories, running tests, and
  contribution conventions

## Repository layout

```
nanorunner/
|-- README.md                       Main user documentation
|-- CLAUDE.md                       Developer guide
|-- CONTRIBUTING.md                 Contribution guidelines
|-- CODE_OF_CONDUCT.md              Community standards
|-- CHANGELOG.md                    Version history
|-- docs/
|   |-- README.md                   This file
|   |-- quickstart.md
|   |-- troubleshooting.md
|   `-- testing.md
`-- examples/
    |-- README.md
    |-- 01_basic_simulation.py
    |-- 02_timing_models.py
    |-- 03_parallel_processing.py
    |-- 04_configuration_profiles.py
    |-- 05_pipeline_integration.py
    |-- 06_practical_genome_test.py
    `-- sample_data/
```

## Version

- **Current version**: 3.0.0
- **Python requirement**: 3.9 or later
- **Test suite**: 729 tests across 18 files; 88% coverage (the 90% threshold
  in `pytest.ini` is currently exceeded only by the gap in `cli_helpers.py`)
