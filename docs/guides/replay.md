# Replay guide

The `replay` subcommand transfers existing FASTQ files from a source
into a target directory at controlled intervals. It can also rechunk
files into smaller pieces and reshape the output layout independently
of the input layout.

```bash
nanorunner replay --source <SRC> --target <DST> [options]
```

## Input shapes accepted

`--source` accepts three shapes:

| Shape | Description |
| --- | --- |
| **flat-one** | A path to a single FASTQ file (`.fastq` or `.fastq.gz`) |
| **flat-many** | A directory containing multiple FASTQ files |
| **barcoded** | A directory with `barcode01/`, `barcode02/`, ..., `unclassified/` subdirectories, each holding one or more FASTQ files |

For barcoded input, the recognised directory names are
`barcode##`, `BC##`, `bc##`, and `unclassified` (case-insensitive).

## Output shapes

By default the target mirrors the source. `--output-structure` decouples
the two:

| Value | Effect |
| --- | --- |
| `preserve` (default) | Output mirrors the input layout. |
| `flat` | All chunks land directly under `--target`, no subdirectories. |
| `barcoded` | Pooled reads are dealt round-robin across `--output-barcodes N` directories. |

Reshaping uses the same pooled-rechunk pipeline as `--reads-per-file`,
so it requires `--reads-per-file` to be set and `--operation copy`
(symlinks cannot reshape file contents).

## The 3x3 input/output reshape matrix

Each cell below shows the invocation that goes from the row's input
shape to the column's output shape. Substitute your source path,
target path, and chunk size as needed.

|                | -> flat-one                                                                 | -> flat-many                                                          | -> barcoded                                                                                           |
| -------------- | ------------------------------------------------------------------------------ | -------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| **flat-one**   | `replay -s file.fastq -t dst/` *(default preserve, no reshape needed)*       | `replay -s file.fastq -t dst/ --reads-per-file 1000`                  | `replay -s file.fastq -t dst/ --reads-per-file 1000 --output-structure barcoded --output-barcodes 4` |
| **flat-many**  | `replay -s src/ -t dst/ --reads-per-file 100000000 --output-structure flat`  | `replay -s src/ -t dst/` *(default preserve)*                         | `replay -s src/ -t dst/ --reads-per-file 1000 --output-structure barcoded --output-barcodes 4`        |
| **barcoded**   | `replay -s src/ -t dst/ --reads-per-file 100000000 --output-structure flat`  | `replay -s src/ -t dst/ --reads-per-file 1000 --output-structure flat`  | `replay -s src/ -t dst/` *(default preserve)*                                                          |

Notes:

- "flat-one" output means a single output file. There is no dedicated
  flag; achieve it by setting `--reads-per-file` to a value at least as
  large as the total read count. `replay` then emits one chunk.
- For barcoded output, chunks are dealt round-robin
  (`barcode01/chunk0, barcode02/chunk0, ..., barcode01/chunk1, ...`)
  so timing intervals advance all barcodes together.
- Output barcode names default to `barcode01`, `barcode02`, .... Use
  `--output-barcode-pattern` for custom patterns
  (e.g. `--output-barcode-pattern 'bc{}'` -> `bc1`, `bc2`, ...).

## Common examples

### Mirror the source with controlled timing

```bash
nanorunner replay -s /data/run01 -t /watch/output --interval 5
```

### Stream a single large FASTQ as many small files

```bash
nanorunner replay -s run01.fastq.gz -t /watch/output \
    --reads-per-file 1000 --interval 2
```

### Split one FASTQ across simulated barcodes

```bash
nanorunner replay -s run01.fastq.gz -t /watch/output \
    --reads-per-file 1000 \
    --output-structure barcoded --output-barcodes 12 \
    --interval 2
```

### Flatten a barcoded run

```bash
nanorunner replay -s /data/multiplex_run -t /watch/output \
    --reads-per-file 2000 --output-structure flat --interval 1
```

### Fast iteration with symlinks (no rechunking)

```bash
nanorunner replay -s /data/source -t /tmp/output \
    --interval 0.5 --operation link --timing-model uniform
```

### Pipeline-aware run with output validation

```bash
nanorunner replay -s /data/source -t /watch/output --pipeline nanometa
```

## Timing and batching

- `--interval SECONDS` -- base interval between batches (default 5.0).
- `--batch-size N` -- number of files emitted per batch.
- `--no-wait` -- alias for `--interval 0`.
- `--timing-model {uniform,random,poisson,adaptive}` -- pattern applied
  to the interval. See [Timing models](timing-models.md).

## Parallel processing

```bash
nanorunner replay -s /data/source -t /watch/output \
    --parallel --worker-count 8 --batch-size 4
```

Threads process files within a batch in parallel; batches still respect
the timing model. Useful for large per-file rechunking workloads.

## Monitoring

```bash
nanorunner replay -s /data/source -t /watch/output --monitor enhanced
nanorunner replay -s /data/source -t /watch/output --monitor none --quiet
```

`enhanced` adds CPU, memory, and disk I/O metrics (requires `psutil`).
Ctrl+C performs a graceful shutdown and prints a summary.

## Validation

```bash
nanorunner replay -s /data/source -t /watch/output --pipeline nanometa
nanorunner validate --pipeline kraken --target /path/to/output
nanorunner list-adapters
```

See [Pipeline integration](pipeline-integration.md) for end-to-end
walkthroughs.
