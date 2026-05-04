# nanorunner usage guide

Installation, the two run modes (replay and generate), timing models,
configuration, and pipeline integration.

## 1. Installation

nanorunner requires Python 3.9 or later. A conda environment is
recommended.

### Install from GitHub

```bash
# Latest stable release
pip install git+https://github.com/FOI-Bioinformatics/nanorunner.git@v3.0.0

# With resource monitoring extras (psutil)
pip install "nanorunner[enhanced] @ git+https://github.com/FOI-Bioinformatics/nanorunner.git@v3.0.0"
```

### Install for development

```bash
git clone https://github.com/FOI-Bioinformatics/nanorunner.git
cd nanorunner
pip install -e .[enhanced,dev]
```

### Verify the installation

```bash
nanorunner --version           # nanorunner 3.0.0
nanorunner --help              # All subcommands
nanorunner check-deps          # Dependency status with install hints
nanorunner list-profiles
nanorunner list-generators
nanorunner list-mocks
```

---

## 2. Replay mode

Transfer existing FASTQ files from a source directory to a target
directory at controlled intervals.

### Basic invocation

```bash
nanorunner replay --source <source_dir> --target <target_dir> [options]

# Example: 5-second intervals
nanorunner replay -s /data/nanopore_reads -t /watch/simulated_output --interval 5
```

What happens:

1. nanorunner detects singleplex or multiplex layout in the source.
2. Files are copied (or symlinked) to the target with timing control.
3. Progress is reported on the terminal.
4. Output structure mirrors the source (barcode directories preserved).

### Common replay examples

```bash
# Fast testing with symlinks
nanorunner replay -s /data/source -t /test/output \
  --interval 0.5 --operation link --timing-model uniform

# Irregular timing via Poisson model
nanorunner replay -s /data/source -t /watch/output \
  --timing-model poisson --burst-probability 0.15 --interval 5

# High-throughput parallel processing with resource monitoring
nanorunner replay -s /data/source -t /watch/output \
  --profile high_throughput --monitor enhanced
```

---

## 3. Generate mode

Produce simulated nanopore FASTQ reads from genome FASTA files,
delivered incrementally with the same timing models.

### Basic invocation

```bash
nanorunner generate --genomes <fasta_files...> --target <target_dir> [options]

# Example: one genome, 5-second intervals
nanorunner generate --genomes genome.fa -t /watch/output --interval 5
```

What happens:

1. nanorunner reads the input FASTA file(s).
2. A backend (`builtin`, `badread`, or `nanosim`) produces simulated FASTQ reads.
3. Reads are written and delivered with the configured timing model.
4. With multiple genomes, each is assigned to its own barcode directory
   (`barcode01/`, `barcode02/`, ...). Assignment is deterministic:
   individual `--genomes` flags are assigned in argument order; if a
   directory is passed, files within are sorted alphabetically before
   assignment.

### Generate-mode examples

```bash
# Multiple genomes, multiplex (default)
nanorunner generate --genomes g1.fa --genomes g2.fa -t /watch/output --interval 5

# Singleplex (all reads in target root)
nanorunner generate --genomes genome.fa -t /watch/output --force-structure singleplex

# Mix reads from multiple genomes into shared files
nanorunner generate --genomes g1.fa --genomes g2.fa -t /watch/output \
  --force-structure singleplex --mix-reads

# Tune read length, count, and per-file batching
nanorunner generate --genomes genome.fa -t /watch/output \
  --read-count 5000 --mean-read-length 8000 --reads-per-file 200 --output-format fastq.gz

# Select a backend explicitly
nanorunner generate --genomes genome.fa -t /watch/output --generator-backend builtin

# Use a generation profile
nanorunner generate --genomes genome.fa -t /watch/output --profile generate_standard
```

### Output structure

Multiplex (default):

```
target_dir/
|-- barcode01/
|   |-- genome1_reads_0000.fastq.gz
|   `-- genome1_reads_0001.fastq.gz
`-- barcode02/
    |-- genome2_reads_0000.fastq.gz
    `-- genome2_reads_0001.fastq.gz
```

Singleplex (`--force-structure singleplex`):

```
target_dir/
|-- genome1_reads_0000.fastq.gz
|-- genome1_reads_0001.fastq.gz
|-- genome2_reads_0000.fastq.gz
`-- genome2_reads_0001.fastq.gz
```

### Read generation backends

```bash
nanorunner list-generators   # Show available backends on this system
```

| Backend   | Dependencies                                  | Description |
|-----------|-----------------------------------------------|-------------|
| `builtin` | None                                          | Random subsequences from the input FASTA, log-normal length distribution. No error model. Produces an exact read count. Suitable for pipeline structure and connectivity testing. |
| `badread` | [badread](https://github.com/rrwick/Badread)  | Nanopore read simulation with empirical error models. |
| `nanosim` | [NanoSim](https://github.com/bcgsc/NanoSim)   | Statistical read simulation from training data. |
| `auto`    | varies                                        | Selects the best available backend (badread > nanosim > builtin). |

The `builtin` backend always works without external dependencies. Its
reads are error-free subsequences and will inflate accuracy in
classification benchmarks; install `badread` or `nanosim` for realistic
error profiles.

---

## 4. Species and mock community generation

Generate reads without supplying genome files. nanorunner resolves
species names through GTDB (bacteria, archaea) or NCBI Datasets
(eukaryotes) and downloads reference genomes automatically.

### From species names

```bash
nanorunner generate --species "Escherichia coli" "Staphylococcus aureus" -t /watch/output

# Abbreviated names also work
nanorunner generate --species "E. coli" "S. aureus" -t /watch/output
```

### From a built-in mock community

Mock communities are predefined sets of species with established
abundances, commonly used as reference standards in microbiome research.

```bash
nanorunner generate --mock zymo_d6300 -t /watch/output
nanorunner list-mocks
```

### Output structure for multiple species

Each species is assigned its own barcode directory by default
(multiplex). To mix all species into shared files, pass
`--force-structure singleplex --mix-reads`.

### Custom abundances

Specify relative abundances (must sum to 1.0):

```bash
nanorunner generate --species "E. coli" "S. aureus" --abundances 0.7 0.3 -t /watch/output
```

### Pre-download genomes

For offline use or to speed up repeated runs:

```bash
nanorunner download --mock zymo_d6300
nanorunner download --species "E. coli" "S. aureus"
```

### Available mock communities

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

Run `nanorunner list-mocks` for full details and product-code aliases.

---

## 5. Configuration profiles

Profiles bundle parameter sets for common scenarios.

```bash
nanorunner list-profiles                       # List all profiles
nanorunner recommend                           # Profile overview
nanorunner recommend --source /path/to/data    # Recommendation for input
```

Built-in profiles:

| Profile             | Purpose |
|---------------------|---------|
| `development`       | Fast iteration with deterministic uniform timing |
| `steady`            | Low-variation random timing for controlled testing |
| `bursty`            | Intermittent burst pattern for pipeline robustness |
| `high_throughput`   | High file volume with burst timing for stress testing |
| `gradual_drift`     | Slowly varying intervals via exponential moving average |
| `generate_test`     | Quick smoke test for read generation (100 reads, builtin) |
| `generate_standard` | Standard generation run (5000 reads, auto backend) |

### Using profiles

```bash
# As-is
nanorunner replay -s /data/source -t /watch/output --profile bursty

# With per-flag overrides (overrides apply after the profile)
nanorunner replay -s /data/source -t /watch/output \
  --profile bursty --interval 3 --worker-count 8

# In generate mode
nanorunner generate --genomes genome.fa -t /watch/output --profile generate_standard
```

---

## 6. Timing models

| Model      | Behaviour                                                                                  |
|------------|--------------------------------------------------------------------------------------------|
| `uniform`  | Constant intervals at the configured base value.                                            |
| `random`   | Symmetric variation `+/- random_factor` around the base interval.                           |
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

The Poisson and adaptive models are descriptive parameterisations and
have not been calibrated against empirical sequencer output.

---

## 7. Directory layouts

### Singleplex (single sample per run)

```
source_dir/
|-- sample1.fastq
|-- sample2.fastq.gz
`-- sample3.fastq.gz
```

### Multiplex (barcoded)

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

Recognised directory names: `barcode##`, `BC##`, `bc##`, and
`unclassified`. Detection is case-insensitive.

---

## 8. Monitoring

```bash
# Detailed progress display with resource tracking
nanorunner replay -s /data/source -t /watch/output --monitor enhanced

# Headless / automated runs
nanorunner replay -s /data/source -t /watch/output --monitor none --quiet
```

The default monitor reports throughput, ETA, and elapsed time. The
`enhanced` monitor adds CPU, memory, and disk I/O metrics (requires
`psutil`). Ctrl+C performs a graceful shutdown and prints a summary.

---

## 9. Pipeline integration

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

For a full end-to-end walkthrough driving Nanometa Live with simulated
input from nanorunner, see the
[Nanometa Live integration walkthrough](https://github.com/FOI-Bioinformatics/nanometa_live/blob/main/docs/quickstart-with-nanorunner.md).

---

## 10. Configuration parameters

### Core options

- `--interval SECONDS` -- base interval between operations (default: 5.0)
- `--operation {copy,link}` -- transfer method for replay mode (default: copy)
- `--force-structure {singleplex,multiplex}` -- override automatic detection
- `--batch-size COUNT` -- files processed per interval (default: 1)
- `--profile NAME` -- apply a configuration profile

### Timing model options

- `--timing-model {uniform,random,poisson,adaptive}`
- `--random-factor FACTOR` -- variation magnitude for the random model (0.0 to 1.0)
- `--burst-probability PROB` -- burst probability for the Poisson model
- `--burst-rate-multiplier MULT` -- rate multiplier during bursts
- `--adaptation-rate RATE` -- EMA rate for the adaptive model (default: 0.1)
- `--history-size SIZE` -- lookback window for the adaptive model (default: 10)

### Read generation options

- `--genomes FASTA [FASTA ...]` -- input FASTA files (selects generate mode)
- `--generator-backend {auto,builtin,badread,nanosim}` -- backend (default: auto)
- `--read-count INT` -- total reads across all genomes (default: 1000)
- `--mean-read-length INT` -- mean read length in bases (default: 5000)
- `--reads-per-file INT` -- reads per output file (default: 100)
- `--output-format {fastq,fastq.gz}` -- output file format (default: fastq.gz)
- `--mix-reads` -- mix reads from all genomes into shared files (singleplex only)

### Species and mock community options

- `--species NAME [...]` -- species names for genome lookup
- `--mock MOCK_ID` -- preset mock community
- `--abundances FLOAT [...]` -- relative abundances for read distribution

### Processing options

- `--parallel` -- enable concurrent file production within batches
- `--worker-count COUNT` -- number of worker threads (default: 4)

### Monitoring options

- `--monitor {default,enhanced,none}` (`detailed` is accepted as an alias for `default`)
- `--quiet` -- suppress progress output

---

## 11. Optional dependencies

The core (replay and built-in generation) depends only on the Python
standard library. Optional dependencies extend functionality:

| Dependency           | Purpose                                       | Install |
|----------------------|-----------------------------------------------|---------|
| `psutil`             | Resource monitoring                           | `conda install -c conda-forge psutil` |
| `numpy`              | Vectorised read generation                    | `conda install -c conda-forge numpy` |
| `badread`            | Read simulation with error models             | `conda install -c bioconda badread` |
| `nanosim`            | Statistical read simulation                   | `conda install -c bioconda nanosim` |
| `ncbi-datasets-cli`  | NCBI genome downloads (`--species`, `--mock`) | `conda install -c conda-forge ncbi-datasets-cli` |

Run `nanorunner check-deps` for a current status report and install
hints.

---

## 12. Examples

Runnable example scripts are provided in the `examples/` directory:

```bash
git clone https://github.com/FOI-Bioinformatics/nanorunner.git
cd nanorunner

python examples/01_basic_simulation.py
python examples/02_timing_models.py
python examples/03_parallel_processing.py
python examples/04_configuration_profiles.py
python examples/05_pipeline_integration.py
python examples/06_practical_genome_test.py
```

---

## 13. Common options reference

### Essential options

| Option                                     | Description                              | Default |
|--------------------------------------------|------------------------------------------|---------|
| `--interval SECONDS`                       | Base time between operations             | 5.0     |
| `--operation {copy,link}`                  | Copy or symlink (replay mode)            | copy    |
| `--batch-size N`                           | Files per batch                          | 1       |
| `--timing-model MODEL`                     | Timing pattern                           | uniform |
| `--force-structure {singleplex,multiplex}` | Override structure detection             | auto    |

### Timing models at a glance

| Model      | Use case               | Key options |
|------------|------------------------|-------------|
| `uniform`  | Deterministic testing  | --                              |
| `random`   | Robustness testing     | `--random-factor 0.3`           |
| `poisson`  | Irregular intervals    | `--burst-probability 0.15`      |
| `adaptive` | Drifting intervals     | `--adaptation-rate 0.1`         |

### Quick reference card

```bash
# Replay: basic simulation
nanorunner replay -s /source -t /target

# Replay: fast testing with symlinks
nanorunner replay -s /source -t /target --interval 0.5 --operation link

# Replay: irregular intervals via Poisson model
nanorunner replay -s /source -t /target --timing-model poisson

# Replay: high-throughput profile
nanorunner replay -s /source -t /target --profile high_throughput

# Generate: reads from genome
nanorunner generate --genomes genome.fa -t /target --interval 5

# Generate: multiplex from multiple genomes
nanorunner generate --genomes g1.fa g2.fa -t /target

# Generate: singleplex with mixed reads
nanorunner generate --genomes g1.fa g2.fa -t /target --force-structure singleplex --mix-reads

# Generate from species names
nanorunner generate --species "E. coli" "S. aureus" -t /target

# Generate from a mock community
nanorunner generate --mock zymo_d6300 -t /target

# Replay with pipeline validation
nanorunner replay -s /source -t /target --pipeline nanometa

# Inspect status
nanorunner check-deps
nanorunner list-profiles
nanorunner list-adapters
nanorunner list-generators
nanorunner list-mocks
nanorunner --help
```

---

## 14. Where to next

- For installation issues, runtime errors, or backend failures, see
  [Troubleshooting](troubleshooting.md).
- For test conventions and contribution guidance, see
  [Testing notes](testing.md) and
  [CLAUDE.md](../CLAUDE.md).
- For end-to-end use with Nanometa Live, see the
  [integration walkthrough](https://github.com/FOI-Bioinformatics/nanometa_live/blob/main/docs/quickstart-with-nanorunner.md).
- Open issues at
  <https://github.com/FOI-Bioinformatics/nanorunner/issues>.
