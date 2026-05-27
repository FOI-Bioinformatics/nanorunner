# Getting started

nanorunner delivers FASTQ files into a target directory with controlled
timing so that watch-directory pipelines can be exercised without an
active sequencer. This page walks through installation, the two run
modes, and a first end-to-end run.

## Install

nanorunner requires Python 3.9 or later. Conda is the recommended
environment manager.

```bash
conda create -n nanorunner python=3.10
conda activate nanorunner
pip install git+https://github.com/FOI-Bioinformatics/nanorunner.git@v3.1.0

# With optional resource-monitoring extras
pip install "nanorunner[enhanced] @ git+https://github.com/FOI-Bioinformatics/nanorunner.git@v3.1.0"
```

For development:

```bash
git clone https://github.com/FOI-Bioinformatics/nanorunner.git
cd nanorunner
pip install -e .[enhanced,dev]
```

Verify the installation:

```bash
nanorunner --version
nanorunner --help
nanorunner check-deps
```

## Two run modes

nanorunner has two top-level subcommands:

- **`replay`** -- transfer existing FASTQ files from a source directory
  (or a single FASTQ file) to a target directory with configurable
  timing. Optionally rechunks reads and reshapes the output layout.
  See the [replay guide](guides/replay.md).
- **`generate`** -- produce simulated reads from genome FASTA files,
  species names, or a built-in mock community, and deliver them with
  the same timing models. See the [generate guide](guides/generate.md).

Both modes preserve singleplex and barcoded layouts and are compatible
with downstream watch-directory pipelines such as Nanometa Live and
nanometanf.

## A first replay run

```bash
# Copy FASTQ files into /tmp/watch at 5-second intervals.
nanorunner replay --source /data/nanopore_reads --target /tmp/watch --interval 5
```

What this does:

1. Detects whether `/data/nanopore_reads` is singleplex (FASTQ files
   directly in the directory) or multiplex (FASTQ files inside
   `barcode01/`, `barcode02/`, ... subdirectories).
2. Plans an output sequence and copies one file every 5 seconds.
3. Reports progress on the terminal.
4. Mirrors the source layout in the target directory.

To run a fast smoke test with symlinks instead of copies:

```bash
nanorunner replay -s /data/source -t /tmp/watch \
    --interval 0.5 --operation link --timing-model uniform
```

## A first generate run

```bash
# 1000 simulated reads from one genome, written into /tmp/watch.
nanorunner generate --genomes genome.fa --target /tmp/watch --interval 5
```

What this does:

1. Reads `genome.fa`.
2. Picks the best available backend (`badread` > `nanosim` >
   `builtin`).
3. Writes simulated FASTQ files into `/tmp/watch` with timing delays.

To list backends and their status:

```bash
nanorunner list-generators
```

## Where to next

- [Replay guide](guides/replay.md) -- timing, batching, rechunking,
  and the input/output reshape matrix.
- [Generate guide](guides/generate.md) -- genomes, species, mock
  communities, abundances, mixing.
- [Timing models](guides/timing-models.md) -- the four models and when
  to pick each.
- [Pipeline integration](guides/pipeline-integration.md) -- driving
  Nanometa Live, nanometanf, Kraken from nanorunner output.
- [CLI reference](reference/cli.md) -- flag-by-flag listing.
- [Configuration reference](reference/configuration.md) --
  `ReplayConfig` and `GenerateConfig` field tables.
- [Troubleshooting](reference/troubleshooting.md) -- common errors and
  resolutions.
