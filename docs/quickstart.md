# NanoRunner Quick Start Guide

Get up and running with NanoRunner in 5 minutes.

## 1. Installation (2 minutes)

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

## 2. Basic Usage (5 minutes)

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

---

## 3. Common Use Cases

### Development Testing (Fast)

```bash
# Fast intervals with symlinks for quick testing
nanorunner /data/source /test/output \
  --interval 0.5 \
  --operation link \
  --timing-model uniform
```

### Realistic Sequencing Simulation

```bash
# Poisson model with burst behavior (biologically realistic)
nanorunner /data/source /watch/output \
  --timing-model poisson \
  --burst-probability 0.15 \
  --interval 5
```

### High-Throughput with Monitoring

```bash
# Parallel processing with enhanced monitoring
nanorunner /data/source /watch/output \
  --profile high_throughput \
  --monitor enhanced
```

---

## 4. Using Configuration Profiles

Profiles provide optimized parameter sets for common scenarios.

### List Available Profiles

```bash
nanorunner --list-profiles
```

**Built-in profiles:**
- `development_testing` - Fast, for development
- `rapid_sequencing` - High-throughput with bursts
- `accurate_mode` - Steady, minimal variation
- `minion_simulation` - MinION device pattern
- `promethion_simulation` - PromethION device pattern

### Use a Profile

```bash
# Use profile as-is
nanorunner /data/source /watch/output --profile rapid_sequencing

# Override profile parameters
nanorunner /data/source /watch/output \
  --profile rapid_sequencing \
  --interval 3 \
  --worker-count 8
```

---

## 5. Monitoring & Progress (10 minutes)

### Default Monitoring

Basic progress bar with file counts:

```
[████████████████████          ] 65.3% | 653/1000 files | 12.5 files/sec | ETA: 28s
```

### Enhanced Monitoring

With resource tracking (requires psutil):

```
[████████████████████          ] 65.3% | 653/1000 files | 12.5 files/sec | ETA: 28s ↗★★ | CPU: 42% | RAM: 58%
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
| `--operation {copy,link}` | Copy files or create symlinks | copy |
| `--batch-size N` | Files per batch | 1 |
| `--timing-model MODEL` | Timing pattern | uniform |

### Timing Models

| Model | Use Case | Options |
|-------|----------|---------|
| `uniform` | Testing, deterministic | None |
| `random` | Robustness testing | `--random-factor 0.3` |
| `poisson` | Realistic sequencing | `--burst-probability 0.15` |
| `adaptive` | Bottleneck detection | `--adaptation-rate 0.1` |

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

Now that you're familiar with the basics:

1. **Explore timing models**: Try different patterns to match your needs
2. **Optimize performance**: Experiment with batch sizes and workers
3. **Integrate with pipelines**: Validate output for your target pipeline
4. **Read full documentation**: See [README.md](../README.md) for complete reference
5. **Review examples**: Study [examples/](../examples/) for advanced usage
6. **Join community**: Ask questions in [GitHub Discussions](https://github.com/FOI-Bioinformatics/nanorunner/discussions)

---

## Quick Reference Card

```bash
# Basic simulation
nanorunner /source /target

# Fast testing
nanorunner /source /target --interval 0.5 --operation link

# Realistic simulation
nanorunner /source /target --timing-model poisson

# High-throughput
nanorunner /source /target --profile high_throughput

# With validation
nanorunner /source /target --pipeline nanometanf

# List options
nanorunner --list-profiles
nanorunner --list-adapters
nanorunner --help
```

---

**Questions?** Open an issue at: https://github.com/FOI-Bioinformatics/nanorunner/issues
