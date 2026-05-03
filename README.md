# NanoRunner

![CI](https://github.com/FOI-Bioinformatics/nanorunner/workflows/CI/badge.svg)
![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)

NanoRunner is a Python tool for testing nanopore sequencing analysis pipelines.
It delivers FASTQ files to a target directory with controlled timing, allowing
downstream watch-directory pipelines to be exercised without an active
sequencer.

The tool operates in two modes:

- **Replay**: transfers existing FASTQ files from a source directory to a target
  directory at configurable intervals.
- **Generate**: produces simulated nanopore reads from one or more genome FASTA
  files and writes them to the target directory at configurable intervals.

Both modes preserve singleplex and multiplex (barcoded) directory layouts and
are compatible with downstream pipelines that monitor a directory, such as
Nanometa Live and nanometanf.

## Installation

The recommended environment manager is conda:

```bash
conda create -n nanorunner python=3.10
conda activate nanorunner
pip install git+https://github.com/FOI-Bioinformatics/nanorunner.git@v3.0.0
```

For resource monitoring (CPU, memory, disk I/O) install the `enhanced` extra:

```bash
pip install "nanorunner[enhanced] @ git+https://github.com/FOI-Bioinformatics/nanorunner.git@v3.0.0"
```

For development:

```bash
git clone https://github.com/FOI-Bioinformatics/nanorunner.git
cd nanorunner
pip install -e .[enhanced,dev]
```

Verify the installation and inspect the available subcommands:

```bash
nanorunner --version
nanorunner --help
nanorunner check-deps        # Report dependency status
nanorunner list-profiles     # Configuration presets
nanorunner list-generators   # Read generation backends
nanorunner list-mocks        # Built-in mock communities
```

## Usage

### Replay mode

```bash
nanorunner replay --source <source_dir> --target <target_dir> [options]
```

Examples:

```bash
# Constant intervals
nanorunner replay -s /data/source -t /watch/output --timing-model uniform --interval 5

# Symmetric stochastic variation around the base interval
nanorunner replay -s /data/source -t /watch/output --timing-model random --random-factor 0.3

# Two-component exponential timing with burst clusters
nanorunner replay -s /data/source -t /watch/output --timing-model poisson --burst-probability 0.15

# Exponential intervals with a rate that drifts via EMA
nanorunner replay -s /data/source -t /watch/output --timing-model adaptive

# Use a configuration profile
nanorunner replay -s /data/source -t /watch/output --profile bursty

# Concurrent processing within batches
nanorunner replay -s /data/source -t /watch/output --profile high_throughput --parallel
```

### Generate mode

```bash
nanorunner generate --genomes <fasta_files...> --target <target_dir> [options]
```

Examples:

```bash
# One genome per barcode (default for multiple genomes)
nanorunner generate --genomes g1.fa --genomes g2.fa -t /watch/output --interval 5

# Singleplex layout
nanorunner generate --genomes g.fa -t /watch/output --force-structure singleplex

# Mix reads from all genomes into shared files
nanorunner generate --genomes g1.fa --genomes g2.fa -t /watch/output \
    --force-structure singleplex --mix-reads

# Tune read length, count, and per-file batching
nanorunner generate --genomes g.fa -t /watch/output \
    --read-count 5000 --mean-read-length 8000 --reads-per-file 200 --output-format fastq.gz

# Select a backend explicitly
nanorunner generate --genomes g.fa -t /watch/output --generator-backend builtin
```

#### Output structure

Multiplex (default for multiple genomes):

```
target_dir/
|-- barcode01/
|   |-- genome1_reads_0000.fastq.gz
|   `-- genome1_reads_0001.fastq.gz
`-- barcode02/
    |-- genome2_reads_0000.fastq.gz
    `-- genome2_reads_0001.fastq.gz
```

Barcode assignment is deterministic. When genomes are passed as repeated
`--genomes` flags, assignment follows argument order. When a directory is
passed, files within are sorted alphabetically before assignment.

Singleplex (`--force-structure singleplex`):

```
target_dir/
|-- genome1_reads_0000.fastq.gz
|-- genome1_reads_0001.fastq.gz
`-- genome2_reads_0000.fastq.gz
```

#### Read generation backends

| Backend   | Dependencies   | Description |
|-----------|----------------|-------------|
| `builtin` | None           | Random subsequences from the input FASTA, log-normal length distribution. No error model. Produces an exact read count. Suitable for pipeline structure and connectivity testing. |
| `badread` | [badread][br]  | Nanopore read simulation with empirical error models. Read count per file is approximate (driven by total bases). |
| `nanosim` | [NanoSim][ns]  | Statistical read simulation from training data. |
| `auto`    | varies         | Selects the best available backend (badread > nanosim > builtin). |

[br]: https://github.com/rrwick/Badread
[ns]: https://github.com/bcgsc/NanoSim

### Species and mock community generation

Generate reads from species names or built-in mock communities. Genomes are
resolved through GTDB (bacteria, archaea) or NCBI Datasets (eukaryotes) and
cached locally:

```bash
# Resolve and download genomes by species name
nanorunner generate --species "Escherichia coli" "Staphylococcus aureus" -t /output

# Built-in mock community
nanorunner generate --mock zymo_d6300 -t /output

# Custom abundance ratios
nanorunner generate --species "E. coli" "S. aureus" --abundances 0.7 0.3 -t /output

# Pre-download genomes (offline use later)
nanorunner download --mock zymo_d6300

# Inspect available communities
nanorunner list-mocks
```

Built-in mock communities:

| Mock ID            | Description                                              | Composition |
|--------------------|----------------------------------------------------------|-------------|
| `zymo_d6300`       | Zymo D6300 Microbial Community Standard (even)           | 8 bacteria + 2 yeasts |
| `zymo_d6310`       | Zymo D6310 Log Distribution (7 orders of magnitude)      | 8 bacteria + 2 yeasts |
| `zymo_d6331`       | Zymo D6331 Gut Microbiome Standard                       | 21 strains, 17 species |
| `atcc_msa1002`     | ATCC MSA-1002 20-strain even mix                         | 20 bacteria, 5% each |
| `atcc_msa1003`     | ATCC MSA-1003 20-strain staggered mix                    | 20 bacteria, 0.02% to 18% |
| `cdc_select_agents`| CDC/USDA Tier 1 bacterial select agents                  | 6 species |
| `eskape`           | ESKAPE nosocomial pathogens                              | 6 species |
| `respiratory`      | Community-acquired respiratory pathogens                 | 6 species |
| `who_critical`     | WHO Critical Priority carbapenem-resistant pathogens     | 5 species |
| `bloodstream`      | Bloodstream infection panel                              | 5 bacteria + 1 yeast |
| `wastewater`       | Wastewater surveillance indicators and pathogens         | 6 species |
| `quick_single`     | Single species (E. coli) for minimal testing             | 1 species |
| `quick_3species`   | Three-species test mock                                  | 3 species |
| `quick_gut5`       | Five-species gut microbiome mock                         | 5 species |
| `quick_pathogens`  | Five-species nosocomial pathogen mock                    | 5 species |

### Configuration profiles

Profiles bundle parameter sets for common scenarios:

```bash
nanorunner list-profiles
nanorunner recommend                       # Profile overview
nanorunner recommend --source /path/to/data # Recommendation for input
```

Built-in profiles: `development`, `steady`, `bursty`, `high_throughput`,
`gradual_drift`, `generate_test`, `generate_standard`.

### Pipeline validation

```bash
# Validate output during a replay run
nanorunner replay -s /data/source -t /watch/output --pipeline nanometa

# Validate an existing directory
nanorunner validate --pipeline kraken --target /path/to/output

# List adapters
nanorunner list-adapters
```

Available adapters: `nanometa` (Nanometa Live / nanometanf), `kraken`
(Kraken2 / KrakenUniq), and a generic adapter for arbitrary structures.

### Monitoring

```bash
# Detailed progress display with resource tracking
nanorunner replay -s /data/source -t /watch/output --monitor enhanced

# Headless / automated runs
nanorunner replay -s /data/source -t /watch/output --monitor none --quiet
```

The default monitor reports throughput, ETA, and elapsed time. The `enhanced`
monitor adds CPU, memory, and disk I/O metrics (requires `psutil`). Ctrl+C
performs a graceful shutdown and prints a summary.

## Timing models

| Model      | Behaviour                                                                                  |
|------------|--------------------------------------------------------------------------------------------|
| `uniform`  | Constant intervals at the configured base value.                                            |
| `random`   | Symmetric variation `+/- random_factor` around the base interval.                          |
| `poisson`  | Mixture of two exponential distributions (base and burst rates) with burst clustering.      |
| `adaptive` | Exponentially distributed intervals; the rate parameter drifts via EMA of recent intervals. |

Examples:

```bash
nanorunner replay -s /data -t /output --timing-model uniform --interval 10
nanorunner replay -s /data -t /output --timing-model random --random-factor 0.3
nanorunner replay -s /data -t /output --timing-model poisson \
    --burst-probability 0.15 --burst-rate-multiplier 3.0
nanorunner replay -s /data -t /output --timing-model adaptive \
    --adaptation-rate 0.1 --history-size 10
```

The Poisson and adaptive models are descriptive parameterisations and have
not been calibrated against empirical sequencer output.

## Directory layouts

Singleplex (single sample per run):

```
source_dir/
|-- sample1.fastq
|-- sample2.fastq.gz
`-- sample3.fastq.gz
```

Multiplex (barcoded):

```
source_dir/
|-- barcode01/
|   |-- reads1.fastq
|   `-- reads2.fastq.gz
|-- barcode02/
|   `-- reads.fastq.gz
`-- unclassified/
    `-- unassigned.fastq
```

Recognised directory names: `barcode##`, `BC##`, `bc##`, and `unclassified`.

## Configuration parameters

Core options:

- `--interval SECONDS` -- base interval between operations (default: 5.0)
- `--operation {copy,link}` -- transfer method for replay mode (default: copy)
- `--force-structure {singleplex,multiplex}` -- override automatic detection
- `--batch-size COUNT` -- files processed per interval (default: 1)
- `--profile NAME` -- apply a configuration profile

Timing models:

- `--timing-model {uniform,random,poisson,adaptive}`
- `--random-factor FACTOR` -- variation magnitude for the random model (0.0 to 1.0)
- `--burst-probability PROB` -- burst probability for the Poisson model
- `--burst-rate-multiplier MULT` -- rate multiplier during bursts
- `--adaptation-rate RATE` -- EMA rate for the adaptive model (default: 0.1)
- `--history-size SIZE` -- lookback window for the adaptive model (default: 10)

Read generation:

- `--genomes FASTA [FASTA ...]` -- input FASTA files (selects generate mode)
- `--generator-backend {auto,builtin,badread,nanosim}` -- backend (default: auto)
- `--read-count INT` -- total reads across all genomes (default: 1000)
- `--mean-read-length INT` -- mean read length in bases (default: 5000)
- `--reads-per-file INT` -- reads per output file (default: 100)
- `--output-format {fastq,fastq.gz}` -- output file format (default: fastq.gz)
- `--mix-reads` -- mix reads from all genomes into shared files (singleplex only)

Processing:

- `--parallel` -- enable concurrent file production within batches
- `--worker-count COUNT` -- number of worker threads (default: 4)

Monitoring:

- `--monitor {default,enhanced,none}` (`detailed` is accepted as an alias for `default`)
- `--quiet` -- suppress progress output

## Optional dependencies

The core (replay and built-in generation) depends only on the Python standard
library. Optional dependencies extend functionality:

| Dependency | Purpose                                  | Install |
|------------|------------------------------------------|---------|
| `psutil`   | Resource monitoring                      | `conda install -c conda-forge psutil` |
| `numpy`    | Vectorised read generation               | `conda install -c conda-forge numpy` |
| `badread`  | Read simulation with error models        | `conda install -c bioconda badread` |
| `nanosim`  | Statistical read simulation              | `conda install -c bioconda nanosim` |
| `datasets` | NCBI genome downloads (`--species`, `--mock`) | `conda install -c conda-forge ncbi-datasets-cli` |

Run `nanorunner check-deps` for a current status report and install hints.

## Requirements

- Python 3.9 or later
- POSIX-compliant operating system (Linux, macOS)
- Optional: `psutil` for resource monitoring; `badread` or `NanoSim` for
  higher-fidelity read simulation; `ncbi-datasets-cli` for `--species` /
  `--mock` workflows

## Development

```bash
git clone https://github.com/FOI-Bioinformatics/nanorunner.git
cd nanorunner
pip install -e .[enhanced,dev]
```

Test suite:

```bash
pytest                                 # Full suite
pytest -m "not slow"                   # Exclude slow integration tests
pytest tests/test_cli.py               # CLI tests only
pytest --cov=nanopore_simulator --cov-report=term-missing
```

Code quality:

```bash
black nanopore_simulator/ tests/
mypy nanopore_simulator/
flake8 nanopore_simulator/
```

## Documentation

- [Quick start](docs/quickstart.md)
- [Testing notes](docs/testing.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Examples](examples/)

## License and attribution

MIT License. See [LICENSE](LICENSE) for details.

Developed by [FOI Bioinformatics](https://github.com/FOI-Bioinformatics) at the
Swedish Defence Research Agency. Repository:
<https://github.com/FOI-Bioinformatics/nanorunner>.
