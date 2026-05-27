# Pipeline integration

nanorunner is built to drive downstream pipelines that watch a
directory for incoming FASTQ files. This page covers the validation
adapters bundled with the tool and an end-to-end walkthrough.

## Adapters

```bash
nanorunner list-adapters
```

| Adapter | Purpose |
| --- | --- |
| `nanometa` | Nanometa Live and nanometanf (barcoded directory layout). `nanometanf` is accepted as an alias. |
| `kraken` | Kraken2 / KrakenUniq watch-directory pipelines. |
| `generic` | Permissive check for FASTQ files with no structural constraints. |

Validate during a run:

```bash
nanorunner replay -s /data/source -t /watch/output --pipeline nanometa
```

Validate an existing output directory:

```bash
nanorunner validate --pipeline kraken --target /path/to/output
```

A validation report lists missing structures or unexpected files.
Exit code is 1 when issues are found.

## Driving Nanometa Live

Start `nanometa_live` (or `nanometanf`) pointed at a watch directory:

```bash
nextflow run nanometa_live \
    --realtime_mode \
    --nanopore_output_dir /watch/output \
    --file_pattern "**/*.fastq{,.gz}" \
    --batch_size 10 \
    --batch_interval "5min"
```

Then run nanorunner against the same target:

```bash
nanorunner replay \
    --source /data/run01 \
    --target /watch/output \
    --interval 30 \
    --pipeline nanometa
```

The pipeline picks up files as nanorunner writes them. Use the timing
models to vary the arrival pattern.

For a full step-by-step walkthrough including environment setup, see
[Nanometa Live integration walkthrough](https://github.com/FOI-Bioinformatics/nanometa_live/blob/main/docs/quickstart-with-nanorunner.md).

## Pre-flight checks

```bash
nanorunner check-deps          # Backend and CLI tool availability
nanorunner list-profiles       # Configuration presets
nanorunner list-generators     # Read generation backends
nanorunner list-mocks          # Mock communities
```

## Tips

- Use `--operation link` for fast iteration on a local filesystem.
  Symlinks are not portable across mount points.
- Use the [reshape matrix](replay.md#the-3x3-inputoutput-reshape-matrix)
  to exercise pipelines against layouts you do not have data for
  (e.g. simulate 24 barcodes from one large FASTQ).
- For headless CI runs, pass `--monitor none --quiet` and check
  `--pipeline ...` exit codes for validation pass/fail.
