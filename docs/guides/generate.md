# Generate guide

The `generate` subcommand produces simulated nanopore reads and delivers
them to a target directory with the same timing models as replay mode.

```bash
nanorunner generate --target <DST> [--genomes ... | --species ... | --mock ID | --taxid ... | --accession ...] [options]
```

## Input sources

| Source flag | What it accepts |
| --- | --- |
| `--genomes` | One or more FASTA paths, or a directory containing them. |
| `--species` | One or more species names. Resolved via GTDB (bacteria, archaea) or NCBI Datasets (eukaryotes). |
| `--mock` | A built-in mock community ID. See `nanorunner list-mocks`. |
| `--taxid` | One or more NCBI taxonomy IDs. |
| `--accession` | One or more explicit NCBI assembly accessions (`GCA_/GCF_NNNNNNNNN.V`, e.g. `GCA_000005845.2`). Pins the run to the exact assembly with no taxonomy lookup. |

When `--species`, `--mock`, `--taxid`, or `--accession` is used,
nanorunner downloads the reference genomes on demand into a local
cache. Use `nanorunner download` to pre-populate the cache for
offline work; subsequent `--offline` runs of any of these sources
will resolve from the cache without any network call.

## Backends

| Backend | Dependencies | Behaviour |
| --- | --- | --- |
| `builtin` | none | Random subsequences from the FASTA with a log-normal length distribution. No error model. Produces an exact read count. |
| `badread` | [badread](https://github.com/rrwick/Badread) | Nanopore read simulation with empirical error models. |
| `nanosim` | [NanoSim](https://github.com/bcgsc/NanoSim) | Statistical read simulation from training data. |
| `auto` (default) | varies | Picks the best available: `badread` > `nanosim` > `builtin`. |

The `builtin` backend always works without external dependencies, but
its reads are error-free; install `badread` or `nanosim` for realistic
error profiles.

## Output layout

By default each genome lands in its own barcode directory:

```
target/
|-- barcode01/
|   |-- genome1_reads_0000.fastq.gz
|   `-- genome1_reads_0001.fastq.gz
`-- barcode02/
    `-- genome2_reads_0000.fastq.gz
```

Override with:

- `--force-structure singleplex` -- all files land in `target/`.
- `--mix-reads` (singleplex only) -- combine reads from every genome
  into each output file.

## Common examples

### One genome, default timing

```bash
nanorunner generate --genomes genome.fa -t /watch/output --interval 5
```

### Multiple genomes, multiplex

```bash
nanorunner generate --genomes g1.fa --genomes g2.fa -t /watch/output \
    --interval 5 --read-count 10000
```

### Mixed singleplex from multiple genomes

```bash
nanorunner generate --genomes g1.fa --genomes g2.fa -t /watch/output \
    --force-structure singleplex --mix-reads
```

### From species names

```bash
nanorunner generate --species "Escherichia coli" "Staphylococcus aureus" \
    -t /watch/output
```

### From a mock community

```bash
nanorunner generate --mock zymo_d6300 -t /watch/output
nanorunner list-mocks
```

### From an explicit assembly accession

```bash
nanorunner generate --accession GCA_000005845.2 -t /watch/output
nanorunner generate --accession GCA_000005845.2 --accession GCF_000146045.2 \
    -t /watch/output
```

Use `--accession` when you need to pin the run to a specific assembly
rather than relying on the resolver to pick a representative.

### Custom abundances

```bash
nanorunner generate --species "E. coli" "S. aureus" \
    --abundances 0.7 0.3 -t /watch/output
```

### Tuning read length and batching

```bash
nanorunner generate --genomes genome.fa -t /watch/output \
    --read-count 5000 --mean-read-length 8000 \
    --reads-per-file 200 --output-format fastq.gz
```

## Available mock communities

| Mock ID | Description |
| --- | --- |
| `zymo_d6300` | Zymo D6300 Microbial Community Standard (even, 8 bact + 2 yeast) |
| `zymo_d6310` | Zymo D6310 Log Distribution |
| `zymo_d6331` | Zymo D6331 Gut Microbiome Standard (21 strains) |
| `atcc_msa1002` | ATCC MSA-1002 20-strain even mix |
| `atcc_msa1003` | ATCC MSA-1003 20-strain staggered mix |
| `cdc_select_agents` | CDC/USDA Tier 1 select agents |
| `eskape` | ESKAPE nosocomial pathogens |
| `respiratory` | Community-acquired respiratory pathogens |
| `who_critical` | WHO Critical Priority carbapenem-resistant pathogens |
| `bloodstream` | Bloodstream infection panel |
| `wastewater` | Wastewater surveillance indicators |
| `quick_single` / `quick_3species` / `quick_gut5` / `quick_pathogens` | Small fixtures for fast testing |

Run `nanorunner list-mocks` for full details and product-code aliases.

## Pre-downloading genomes

For offline use or repeated runs:

```bash
nanorunner download --mock zymo_d6300
nanorunner download --species "E. coli" "S. aureus"
nanorunner download --taxid 562
nanorunner download --accession GCA_000005845.2
```

Cached genomes live in the platform-specific data directory and are
reused on subsequent runs automatically.

Once cached, `generate --offline` resolves from the cache for every
genome source (`--mock`, `--species`, `--taxid`, `--accession`) with
no network call. On a cache miss the affected genome is reported and
skipped; if nothing else resolves, the run exits non-zero.
