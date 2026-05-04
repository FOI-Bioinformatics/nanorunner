# nanorunner documentation

Reference material for the nanorunner nanopore sequencing run simulator.

Start with the [usage guide](quickstart.md) for installation, run modes,
timing models, configuration, and pipeline integration.

## User documentation

- [Usage guide](quickstart.md) -- comprehensive end-to-end reference
- [Troubleshooting](troubleshooting.md) -- installation and runtime issues
- [Testing notes](testing.md) -- test categories, running tests, and
  contribution conventions

## Integration

- [Quick start with Nanometa Live](https://github.com/FOI-Bioinformatics/nanometa_live/blob/main/docs/quickstart-with-nanorunner.md)
  -- end-to-end demo driving Nanometa Live (and the nanometanf Nextflow
  backend) with simulated reads from nanorunner

## Developer documentation

- [CLAUDE.md](../CLAUDE.md) -- architecture, extension points, conventions
- [CONTRIBUTING.md](../CONTRIBUTING.md) -- contribution workflow
- [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) -- community standards
- [Examples](../examples/) -- runnable scripts demonstrating timing
  models, profiles, parallel processing, and pipeline integration

## Archive

Working artifacts from development cycles -- audit reports and design
plans -- live in [`archive/`](archive/README.md). They are preserved
for reference but are not actively maintained.

## Version

- Current version: 3.0.0
- Python requirement: 3.9 or later
- Test suite: 729 tests across 19 files; coverage 88% (the 90%
  threshold in `pytest.ini` is not currently met -- see
  [testing notes](testing.md))
