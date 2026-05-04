# NanoRunner

![CI](https://github.com/FOI-Bioinformatics/nanorunner/workflows/CI/badge.svg)
![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)

NanoRunner is a Python tool for testing nanopore sequencing analysis
pipelines. It delivers FASTQ files to a target directory with controlled
timing, allowing downstream watch-directory pipelines to be exercised
without an active sequencer.

The tool operates in two modes:

- **Replay**: transfer existing FASTQ files from a source directory to a
  target directory at configurable intervals.
- **Generate**: produce simulated nanopore reads from genome FASTA files
  (or species names / mock community presets) and write them to the target
  directory at configurable intervals.

Both modes preserve singleplex and multiplex (barcoded) directory layouts
and are compatible with downstream pipelines that monitor a directory,
such as Nanometa Live and nanometanf.

## Get started

The recommended environment manager is conda:

```bash
conda create -n nanorunner python=3.10
conda activate nanorunner
pip install git+https://github.com/FOI-Bioinformatics/nanorunner.git@v3.0.0
nanorunner --help
```

For full installation options, the two run modes, timing models,
configuration parameters, and pipeline integration, see the
[usage guide](docs/quickstart.md). For an end-to-end demo driving
Nanometa Live with simulated reads, see the
[Nanometa Live integration walkthrough](https://github.com/FOI-Bioinformatics/nanometa_live/blob/main/docs/quickstart-with-nanorunner.md).

## Documentation

- [Usage guide](docs/quickstart.md) -- installation, run modes, timing
  models, configuration, pipeline integration
- [Troubleshooting](docs/troubleshooting.md) -- installation and runtime
  issues
- [Testing notes](docs/testing.md) -- test categories, running tests, and
  contribution conventions
- [Examples](examples/) -- runnable scripts demonstrating timing models,
  profiles, parallel processing, and pipeline integration
- [CLAUDE.md](CLAUDE.md) -- developer guide (architecture, extension
  points)

## Requirements

- Python 3.9 or later
- POSIX-compliant operating system (Linux, macOS)
- Optional: `psutil` for resource monitoring; `badread` or `nanosim`
  for higher-fidelity read simulation; `ncbi-datasets-cli` for
  `--species` / `--mock` workflows

Run `nanorunner check-deps` for a current dependency status report and
install hints.

## Citation

If you use NanoRunner in research, please cite:

> NanoRunner: a nanopore sequencing run simulator for testing
> watch-directory analysis pipelines. FOI Bioinformatics, Swedish
> Defence Research Agency. <https://github.com/FOI-Bioinformatics/nanorunner>

## License

MIT License. See [LICENSE](LICENSE) for details.

Developed by [FOI Bioinformatics](https://github.com/FOI-Bioinformatics)
at the Swedish Defence Research Agency.
