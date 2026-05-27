# nanorunner documentation

nanorunner is a Python tool that delivers FASTQ files into a target
directory with controlled timing, so that watch-directory analysis
pipelines can be exercised without an active sequencer.

## Getting started

- **[Getting started](getting-started.md)** -- install, the two run
  modes, and a first end-to-end run.

## Guides

- **[Replay guide](guides/replay.md)** -- transferring existing
  FASTQ files, rechunking, and the 3x3 input/output reshape matrix.
- **[Generate guide](guides/generate.md)** -- simulating reads from
  genomes, species names, and mock communities.
- **[Timing models](guides/timing-models.md)** -- the four timing
  models and the available profiles.
- **[Pipeline integration](guides/pipeline-integration.md)** --
  driving Nanometa Live, nanometanf, and Kraken from nanorunner.

## Reference

- **[CLI reference](reference/cli.md)** -- every option grouped by
  purpose.
- **[Configuration reference](reference/configuration.md)** -- field
  tables for `ReplayConfig` and `GenerateConfig`.
- **[Troubleshooting](reference/troubleshooting.md)** -- installation,
  runtime, and dependency issues.

## Developer

- **[Testing notes](testing.md)** -- test categories and conventions.
- **[CLAUDE.md](../CLAUDE.md)** -- developer guide (architecture,
  extension points).
- **[Examples](../examples/)** -- runnable scripts.
- **[Archive](archive/)** -- historical audits and design plans.

## Integration

- [Nanometa Live walkthrough](https://github.com/FOI-Bioinformatics/nanometa_live/blob/main/docs/quickstart-with-nanorunner.md)
  -- end-to-end demo driving Nanometa Live with simulated reads.

## Version

- Current version: 3.1.0
- Python requirement: 3.9 or later
- Test coverage: 91%
