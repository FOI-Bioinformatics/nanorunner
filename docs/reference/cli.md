# CLI reference

Every subcommand prints its full option list via `--help`:

```bash
nanorunner --help
nanorunner replay --help
nanorunner generate --help
nanorunner download --help
nanorunner validate --help
nanorunner check-deps --help
```

This page summarises the options grouped by purpose. The authoritative
listing is what `--help` prints in your installed version.

## Replay options

### Required

- `--source, -s PATH` -- source directory or single FASTQ file.
- `--target, -t PATH` -- target directory.

### Simulation configuration

- `--profile NAME` -- apply a configuration profile.
- `--interval SECONDS` -- base seconds between file operations (default 5.0).
- `--operation {copy, link}` -- transfer method (default copy).
- `--force-structure {singleplex, multiplex}` -- override automatic detection.
- `--batch-size N` -- files per interval (default 1).
- `--no-wait` -- alias for `--interval 0`.
- `--reads-per-file N` -- rechunk FASTQs into N-read pieces. Requires `--operation copy`.

### Output layout reshaping

- `--output-structure {preserve, flat, barcoded}` -- target shape.
  Non-preserve values require `--reads-per-file`.
- `--output-barcodes N` -- number of barcode dirs when reshaping to barcoded.
- `--output-barcode-pattern STR` -- format string for barcode dir names.
  Default `barcode{:02d}`. Must contain one positional integer placeholder.
- `--output-file-prefix STR` -- override chunk filename stem.

### Timing model

- `--timing-model {uniform, random, poisson, adaptive}`
- `--random-factor FLOAT` -- variation magnitude for random (0.0 to 1.0).
- `--burst-probability FLOAT` -- burst probability for Poisson.
- `--burst-rate-multiplier FLOAT` -- burst rate multiplier for Poisson.
- `--adaptation-rate FLOAT` -- EMA rate for adaptive (default 0.1).
- `--history-size N` -- lookback window for adaptive (default 10).

### Parallel processing

- `--parallel` -- enable concurrent file ops within a batch.
- `--worker-count N` -- thread count (default 4).

### Monitoring

- `--monitor {default, enhanced, none}`
- `--quiet` -- suppress progress output.
- `--pipeline NAME` -- post-run pipeline validation.

## Generate options

### Required (one of)

- `--genomes FASTA [FASTA ...]` -- input FASTA files or a directory.
- `--species NAME [...]` -- species names (GTDB / NCBI lookup).
- `--mock MOCK_ID` -- built-in mock community.
- `--taxid INT [...]` -- NCBI taxonomy IDs.

### Generation parameters

- `--target, -t PATH` -- target directory.
- `--generator-backend {auto, builtin, badread, nanosim}` (default auto).
- `--read-count INT` -- total reads across all genomes (default 1000).
- `--mean-read-length INT` -- mean read length in bases (default 5000).
- `--reads-per-file INT` -- reads per output file (default 100).
- `--output-format {fastq, fastq.gz}` (default `fastq.gz`).
- `--mix-reads` -- mix reads from all genomes into shared files
  (singleplex only).
- `--abundances FLOAT [...]` -- per-genome abundances (must sum to 1.0).
- `--force-structure {singleplex, multiplex}` -- output layout (default
  multiplex for >1 genome).
- `--offline` -- use only cached genomes; no network requests.

Timing, parallel, and monitoring options match replay mode.

## Utility subcommands

- `nanorunner check-deps` -- dependency status with install hints.
- `nanorunner list-profiles` -- configuration profiles.
- `nanorunner list-adapters` -- pipeline adapters.
- `nanorunner list-generators` -- backend availability.
- `nanorunner list-mocks` -- mock communities and aliases.
- `nanorunner recommend [--source PATH | --file-count N]` -- profile
  recommendations.
- `nanorunner validate --pipeline NAME --target PATH` -- validate an
  existing directory.
- `nanorunner download [--mock | --species | --taxid] [--target PATH]`
  -- pre-cache genomes, optionally generating reads.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success. |
| 1 | Generic error (download failed, IO error, validation issue). |
| 2 | Usage error (bad flag combination, invalid value). |
| 3 | Empty source directory (replay mode). |
