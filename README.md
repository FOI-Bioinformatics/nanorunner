<p align="center">
  <img src="docs/assets/nanorunner_logo.png" alt="NanoRunner" width="420">
</p>

<p align="center">
  <a href="https://github.com/FOI-Bioinformatics/nanorunner/actions"><img src="https://github.com/FOI-Bioinformatics/nanorunner/workflows/CI/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.9%2B-blue" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT">
  <img src="https://img.shields.io/badge/version-3.1.0-informational" alt="Version 3.1.0">
</p>

# NanoRunner

NanoRunner is a nanopore sequencing run simulator. It delivers FASTQ
files into a target directory with controlled timing so that
watch-directory analysis pipelines can be exercised without an active
sequencer.

Two run modes:

- **Replay** -- transfer existing FASTQ files into the target with
  configurable timing. Accepts a single FASTQ file, a flat directory of
  FASTQs, or barcoded subdirectories. Can rechunk a large FASTQ into
  many small files and reshape the output layout independently of the
  input (any of the three shapes can become any of the three).
- **Generate** -- produce simulated reads from genome FASTAs, species
  names, NCBI taxonomy IDs, explicit NCBI assembly accessions
  (e.g. `GCA_000005845.2`), or built-in mock community presets, and
  deliver them with the same timing models.

Output is compatible with watch-directory pipelines such as
[Nanometa Live](https://github.com/FOI-Bioinformatics/nanometa_live)
and [nanometanf](https://github.com/FOI-Bioinformatics/nanometanf).

## Install

```bash
conda create -n nanorunner python=3.10
conda activate nanorunner
pip install git+https://github.com/FOI-Bioinformatics/nanorunner.git@v3.1.0
nanorunner --help
```

## First run

```bash
# Replay an existing run into a watch directory at 5 s intervals
nanorunner replay --source /data/run01 --target /watch/output --interval 5

# Generate 1000 simulated reads from one genome
nanorunner generate --genomes genome.fa --target /watch/output --interval 5
```

## Documentation

See **[docs/](docs/README.md)** for the full documentation:

- [Getting started](docs/getting-started.md)
- [Replay guide](docs/guides/replay.md) -- includes the 3x3
  input/output reshape matrix.
- [Generate guide](docs/guides/generate.md)
- [Timing models](docs/guides/timing-models.md)
- [Pipeline integration](docs/guides/pipeline-integration.md)
- [CLI reference](docs/reference/cli.md)
- [Configuration reference](docs/reference/configuration.md)
- [Troubleshooting](docs/reference/troubleshooting.md)
- [Examples](examples/) -- runnable scripts
- [CLAUDE.md](CLAUDE.md) -- developer guide

For an end-to-end demo driving Nanometa Live with simulated reads,
see the [Nanometa Live integration walkthrough](https://github.com/FOI-Bioinformatics/nanometa_live/blob/main/docs/quickstart-with-nanorunner.md).

## Requirements

- Python 3.9 or later
- POSIX-compliant operating system (Linux, macOS)
- Optional: `psutil` for resource monitoring; `badread` or `nanosim`
  for higher-fidelity read simulation; `ncbi-datasets-cli` for
  `--species` / `--mock` workflows

Run `nanorunner check-deps` for a current dependency status report.

## Citation

If you use NanoRunner in research, please cite:

> NanoRunner: a nanopore sequencing run simulator for testing
> watch-directory analysis pipelines. FOI Bioinformatics, Swedish
> Defence Research Agency. <https://github.com/FOI-Bioinformatics/nanorunner>

## License

MIT License. See [LICENSE](LICENSE) for details.

Developed by [FOI Bioinformatics](https://github.com/FOI-Bioinformatics)
at the Swedish Defence Research Agency.
