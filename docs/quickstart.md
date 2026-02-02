# NanoRunner Quick Start Guide

Get up and running with NanoRunner.

## 1. Installation

### Install from GitHub

```bash
# Latest stable release
pip install git+https://github.com/FOI-Bioinformatics/nanorunner.git@v2.0.2

# With enhanced monitoring (optional but recommended)
pip install "nanorunner[enhanced] @ git+https://github.com/FOI-Bioinformatics/nanorunner.git@v2.0.2"
```

### Verify Installation

```bash
nanorunner --version
# Output: nanorunner 2.0.2

nanorunner --help
# Shows all available options
```

---

## 2. Replay Mode - Replaying Existing Files

Transfer existing FASTQ/POD5 files from a source directory to a target directory with controlled timing.

### Your First Simulation

```bash
# Basic syntax
nanorunner <source_directory> <target_directory> [options]

# Example: Simulate with 5-second intervals
nanorunner /data/nanopore_reads /watch/simulated_output --interval 5
```

### What Happens

1. NanoRunner detects singleplex vs multiplex structure
2. Files are copied/linked to target directory with timing control
3. Progress is displayed in real-time
4. Output structure matches source (preserves barcode directories)

### Common Replay Examples

```bash
# Fast testing with symlinks
nanorunner /data/source /test/output \
  --interval 0.5 \
  --operation link \
  --timing-model uniform

# Realistic sequencing with Poisson timing
nanorunner /data/source /watch/output \
  --timing-model poisson \
  --burst-probability 0.15 \
  --interval 5

# High-throughput parallel processing with monitoring
nanorunner /data/source /watch/output \
  --profile high_throughput \
  --monitor enhanced
```

---

## 3. Generate Mode - Simulating Reads from Genomes

Produce simulated nanopore FASTQ reads from genome FASTA files, delivered incrementally with the same timing models.

### Your First Read Generation

```bash
# Basic syntax (no source directory needed)
nanorunner --genomes <fasta_files...> <target_directory> [options]

# Example: Generate reads from a genome with 5-second intervals
nanorunner --genomes genome.fa /watch/output --interval 5
```

### What Happens

1. NanoRunner reads the genome FASTA file(s)
2. A read generation backend (builtin, badread, or nanosim) produces simulated FASTQ reads
3. Reads are written to output files and delivered with the configured timing model
4. In multiplex mode, each genome is assigned to a barcode directory (`barcode01/`, `barcode02/`, ...)

### Generate Mode Examples

```bash
# Multiple genomes in multiplex mode (each genome gets a barcode directory)
nanorunner --genomes genome1.fa genome2.fa /watch/output --interval 5

# Singleplex output (all files in target root)
nanorunner --genomes genome.fa /watch/output --force-structure singleplex

# Mix reads from multiple genomes into shared files
nanorunner --genomes g1.fa g2.fa /watch/output \
  --force-structure singleplex \
  --mix-reads

# Custom generation parameters
nanorunner --genomes genome.fa /watch/output \
  --read-count 5000 \
  --mean-read-length 8000 \
  --reads-per-file 200 \
  --output-format fastq.gz

# Use a specific backend
nanorunner --genomes genome.fa /watch/output --generator-backend builtin

# Use a generation profile
nanorunner --genomes genome.fa /watch/output --profile generate_realistic
```

### Output Structure

**Multiplex** (default):
```
target_dir/
├── barcode01/
│   ├── genome1_reads_0000.fastq.gz
│   └── genome1_reads_0001.fastq.gz
└── barcode02/
    ├── genome2_reads_0000.fastq.gz
    └── genome2_reads_0001.fastq.gz
```

**Singleplex** (`--force-structure singleplex`):
```
target_dir/
├── genome1_reads_0000.fastq.gz
├── genome1_reads_0001.fastq.gz
├── genome2_reads_0000.fastq.gz
└── genome2_reads_0001.fastq.gz
```

### Read Generation Backends

Check which backends are available on your system:

```bash
nanorunner --list-generators
```

| Backend | Dependencies | Description |
|---------|-------------|-------------|
| `builtin` | None | Random subsequences with log-normal length distribution and simulated quality scores |
| `badread` | [badread](https://github.com/rrwick/Badread) | Realistic nanopore read simulation with error models |
| `nanosim` | [NanoSim](https://github.com/bcgsc/NanoSim) | Statistical read simulation from training data |
| `auto` | Varies | Selects the best available backend (badread > nanosim > builtin) |

The `builtin` backend requires no external dependencies and is always available. For higher-fidelity reads, install badread or NanoSim separately.

---

## 4. Using Configuration Profiles

Profiles provide optimized parameter sets for common scenarios.

### List Available Profiles

```bash
nanorunner --list-profiles
```

**Built-in profiles:**
- `development_testing` - Fast intervals, symlinks, for development
- `rapid_sequencing` - High-throughput with bursts
- `accurate_mode` - Steady, minimal variation
- `minion_simulation` - MinION device pattern
- `promethion_simulation` - PromethION device pattern
- `generate_quick_test` - Quick read generation (100 reads, builtin)
- `generate_realistic` - Realistic read generation with Poisson timing

### Use a Profile

```bash
# Use profile as-is
nanorunner /data/source /watch/output --profile rapid_sequencing

# Override profile parameters
nanorunner /data/source /watch/output \
  --profile rapid_sequencing \
  --interval 3 \
  --worker-count 8

# Combine a profile with generate mode
nanorunner --genomes genome.fa /watch/output --profile generate_realistic
```

---

## 5. Monitoring & Progress

### Default Monitoring

Basic progress bar with file counts:

```
[====================          ] 65.3% | 653/1000 files | 12.5 files/sec | ETA: 28s
```

### Enhanced Monitoring

With resource tracking (requires psutil):

```
[====================          ] 65.3% | 653/1000 files | 12.5 files/sec | ETA: 28s | CPU: 42% | RAM: 58%
```

Enable with:

```bash
nanorunner /data/source /watch/output --monitor enhanced
```

### Interactive Controls

- **Ctrl+C**: Graceful shutdown with summary
- **Pause/Resume**: Available in enhanced mode
- **Automatic checkpoints**: Progress saved every 10 files

---

## 6. Pipeline Integration

### Validate for Specific Pipeline

```bash
# Simulate with validation
nanorunner /data/source /watch/output --pipeline nanometanf

# Validate existing directory
nanorunner --validate-pipeline kraken /path/to/output
```

### List Supported Pipelines

```bash
nanorunner --list-adapters
```

**Built-in adapters:**
- `nanometanf` - Real-time taxonomic classification
- `kraken` - k-mer based classification
- `miniknife` - Lightweight classification

Both replay and generate modes produce output that is compatible with these pipelines.

---

## 7. Examples

Runnable example scripts are provided in the `examples/` directory:

```bash
# Clone repository for examples
git clone https://github.com/FOI-Bioinformatics/nanorunner.git
cd nanorunner

# Run examples
python examples/01_basic_simulation.py
python examples/02_timing_models.py
python examples/03_parallel_processing.py
python examples/04_configuration_profiles.py
python examples/05_pipeline_integration.py
```

---

## 8. Common Options Reference

### Essential Options

| Option | Description | Default |
|--------|-------------|---------|
| `--interval SECONDS` | Base time between operations | 5.0 |
| `--operation {copy,link}` | Copy files or create symlinks (replay mode) | copy |
| `--batch-size N` | Files per batch | 1 |
| `--timing-model MODEL` | Timing pattern | uniform |
| `--force-structure {singleplex,multiplex}` | Override structure detection | auto |

### Timing Models

| Model | Use Case | Key Options |
|-------|----------|-------------|
| `uniform` | Testing, deterministic | None |
| `random` | Robustness testing | `--random-factor 0.3` |
| `poisson` | Realistic sequencing | `--burst-probability 0.15` |
| `adaptive` | Bottleneck detection | `--adaptation-rate 0.1` |

### Read Generation Options

| Option | Description | Default |
|--------|-------------|---------|
| `--genomes FASTA [...]` | Input genome files (activates generate mode) | - |
| `--generator-backend` | Backend: auto, builtin, badread, nanosim | auto |
| `--read-count N` | Reads per genome | 1000 |
| `--mean-read-length N` | Mean read length in bases | 5000 |
| `--reads-per-file N` | Reads per output file | 100 |
| `--output-format` | fastq or fastq.gz | fastq.gz |
| `--mix-reads` | Mix genomes into shared files (singleplex) | false |

### Processing Options

| Option | Description | Default |
|--------|-------------|---------|
| `--parallel` | Enable parallel processing | false |
| `--worker-count N` | Number of workers | 4 |
| `--monitor LEVEL` | Progress monitoring | default |

---

## 9. Troubleshooting

### Installation Issues

**Problem**: `Command not found: nanorunner`
```bash
# Solution: Ensure pip install location is in PATH
pip install --user git+https://github.com/FOI-Bioinformatics/nanorunner.git@v2.0.2
# Add to PATH: export PATH="$HOME/.local/bin:$PATH"
```

**Problem**: `Python version mismatch`
```bash
# Solution: Use Python 3.9+
python3.11 -m pip install git+https://github.com/FOI-Bioinformatics/nanorunner.git@v2.0.2
```

### Runtime Issues

**Problem**: Permission denied on target directory
```bash
# Solution: Check write permissions
chmod 755 /path/to/target
```

**Problem**: Out of memory with large datasets
```bash
# Solution: Reduce batch size
nanorunner /data /output --batch-size 5
```

**Problem**: Slow performance
```bash
# Solution: Enable parallel processing
nanorunner /data /output --parallel --worker-count 8
```

---

## 10. Next Steps

Now that you are familiar with the basics:

1. **Explore timing models**: Try different patterns to match your needs
2. **Try generate mode**: Simulate reads from reference genomes without needing existing FASTQ files
3. **Optimize performance**: Experiment with batch sizes and workers
4. **Integrate with pipelines**: Validate output for your target pipeline
5. **Read full documentation**: See [README.md](../README.md) for complete reference
6. **Review examples**: Study [examples/](../examples/) for advanced usage

---

## Quick Reference Card

```bash
# Replay: basic simulation
nanorunner /source /target

# Replay: fast testing with symlinks
nanorunner /source /target --interval 0.5 --operation link

# Replay: realistic Poisson timing
nanorunner /source /target --timing-model poisson

# Replay: high-throughput profile
nanorunner /source /target --profile high_throughput

# Generate: reads from genome
nanorunner --genomes genome.fa /target --interval 5

# Generate: multiplex from multiple genomes
nanorunner --genomes g1.fa g2.fa /target

# Generate: singleplex with mixed reads
nanorunner --genomes g1.fa g2.fa /target --force-structure singleplex --mix-reads

# Replay with pipeline validation
nanorunner /source /target --pipeline nanometanf

# List options
nanorunner --list-profiles
nanorunner --list-adapters
nanorunner --list-generators
nanorunner --help
```

---

**Questions?** Open an issue at: https://github.com/FOI-Bioinformatics/nanorunner/issues
