# NanoRunner Troubleshooting Guide

Comprehensive guide to diagnosing and resolving common issues.

## Installation Issues

### Git Not Found

**Symptom**: `fatal: not a git repository` or `git: command not found`

**Solution**:
```bash
# Ubuntu/Debian
sudo apt-get install git

# macOS
brew install git

# Or download from: https://git-scm.com/
```

### Permission Denied During Install

**Symptom**: `Permission denied` or `[Errno 13]`

**Solutions**:
```bash
# Option 1: Install to user directory
pip install --user git+https://github.com/FOI-Bioinformatics/nanorunner.git@v2.0.1

# Option 2: Use virtual environment (recommended)
python -m venv nanorunner_env
source nanorunner_env/bin/activate  # On Windows: nanorunner_env\Scripts\activate
pip install git+https://github.com/FOI-Bioinformatics/nanorunner.git@v2.0.1
```

### Python Version Mismatch

**Symptom**: `Requires Python '>=3.9' but the running Python is 3.8`

**Solution**:
```bash
# Check Python version
python --version

# Use specific Python version
python3.11 -m pip install git+https://github.com/FOI-Bioinformatics/nanorunner.git@v2.0.1

# Create alias (add to ~/.bashrc or ~/.zshrc)
alias nanorunner='python3.11 -m nanopore_simulator.cli.main'
```

### Command Not Found After Install

**Symptom**: `nanorunner: command not found`

**Solution**:
```bash
# Check if pip install directory is in PATH
pip show nanorunner | grep Location

# Add to PATH (Linux/macOS)
export PATH="$HOME/.local/bin:$PATH"

# Or use full path
python -m nanopore_simulator.cli.main --help

# Or reinstall with user flag
pip install --user git+https://github.com/FOI-Bioinformatics/nanorunner.git@v2.0.0
```

---

## Runtime Issues

### Permission Denied on Target Directory

**Symptom**: `PermissionError: [Errno 13] Permission denied: '/path/to/target'`

**Solutions**:
```bash
# Check permissions
ls -ld /path/to/target

# Fix permissions
chmod 755 /path/to/target

# Or use writable directory
nanorunner /source ~/nanorunner_output
```

### Source Directory Not Found

**Symptom**: `Error: Source directory does not exist: /path/to/source`

**Solutions**:
```bash
# Check path exists
ls /path/to/source

# Use absolute path
nanorunner $(pwd)/data /output

# Check for typos
nanorunner --help  # Review usage
```

### No Sequencing Files Found

**Symptom**: `ValueError: No sequencing files found in /source`

**Diagnosis**:
```bash
# Check for supported file types
find /source -name "*.fastq" -o -name "*.fq" -o -name "*.pod5" -o -name "*.fastq.gz"

# List directory contents
ls -la /source
```

**Solutions**:
- Ensure files have correct extensions (`.fastq`, `.fq`, `.pod5`, `.fastq.gz`, `.fq.gz`)
- Check barcode subdirectories for multiplex data
- Verify files aren't hidden or in wrong location

### Out of Memory

**Symptom**: `MemoryError` or system slowdown

**Solutions**:
```bash
# Reduce batch size
nanorunner /source /target --batch-size 5

# Disable parallel processing
nanorunner /source /target  # (parallel is off by default)

# Use symlinks instead of copying
nanorunner /source /target --operation link

# Monitor memory usage
nanorunner /source /target --monitor enhanced
```

### Slow Performance

**Symptom**: Very low throughput (< 1 file/sec with small files)

**Solutions**:
```bash
# Enable parallel processing
nanorunner /source /target --parallel --worker-count 8

# Reduce interval
nanorunner /source /target --interval 0.5

# Use uniform timing (fastest)
nanorunner /source /target --timing-model uniform

# Use symlinks for faster operations
nanorunner /source /target --operation link

# Use optimized profile
nanorunner /source /target --profile high_throughput
```

---

## Monitoring Issues

### Enhanced Monitoring Not Working

**Symptom**: Enhanced monitoring falls back to basic mode

**Solution**:
```bash
# Install psutil
pip install psutil

# Or install with enhanced extras
pip install "nanorunner[enhanced] @ git+https://github.com/FOI-Bioinformatics/nanorunner.git@v2.0.0"

# Verify psutil
python -c "import psutil; print('OK')"
```

### Progress Bar Not Displaying

**Symptom**: No progress output or jumbled display

**Solutions**:
```bash
# Check terminal supports ANSI
echo -e "\033[32mGreen\033[0m"

# Disable monitoring if needed
nanorunner /source /target --monitor none

# Use detailed monitoring for logging
nanorunner /source /target --monitor detailed 2>&1 | tee simulation.log
```

---

## Pipeline Integration Issues

### Validation Fails

**Symptom**: `Pipeline validation failed` or `Structure not valid`

**Diagnosis**:
```bash
# Check what pipelines are compatible
nanorunner --validate-pipeline nanometanf /target

# Check output structure
ls -R /target

# Verify file patterns
find /target -name "*.fastq*"
```

**Solutions**:
- **For miniknife**: Requires multiplex structure with barcode directories
- **For nanometanf**: Works with both singleplex and multiplex
- **For kraken**: Works with any structure

### Pipeline Adapter Not Found

**Symptom**: `Unknown pipeline: xyz`

**Solution**:
```bash
# List available adapters
nanorunner --list-adapters

# Use generic adapter for custom pipelines
# (requires Python API, not CLI)
```

---

## File System Issues

### Symbolic Link Errors

**Symptom**: `OSError: symbolic link privilege not held` (Windows)

**Solutions**:
```bash
# On Windows: Run as Administrator or use copy mode
nanorunner /source /target --operation copy

# Or enable Developer Mode (Windows 10+)
# Settings → Update & Security → For Developers → Developer Mode
```

### Disk Space Exhausted

**Symptom**: `No space left on device`

**Solutions**:
```bash
# Check disk space
df -h /target

# Use symlinks to save space
nanorunner /source /target --operation link

# Use smaller batch size to process incrementally
nanorunner /source /target --batch-size 10

# Cleanup previous runs
rm -rf /tmp/nanorunner_*
```

### Mixed File System Types

**Symptom**: Issues with symlinks across filesystems

**Solution**:
```bash
# Use copy mode for cross-filesystem operations
nanorunner /mnt/source /home/user/target --operation copy

# Ensure source and target are on same filesystem for symlinks
```

---

## Timing Model Issues

### Adaptive Model Not Adapting

**Symptom**: Intervals don't change over time

**Explanation**: Adaptive model requires history to build. Early intervals use base rate.

**Solution**:
```bash
# Increase history size and adaptation rate
nanorunner /source /target \
  --timing-model adaptive \
  --adaptation-rate 0.3 \
  --history-size 20
```

### Poisson Intervals Too Variable

**Symptom**: Intervals are very inconsistent

**Solution**:
```bash
# Reduce burst probability
nanorunner /source /target \
  --timing-model poisson \
  --burst-probability 0.05

# Or use random model for controlled variation
nanorunner /source /target \
  --timing-model random \
  --random-factor 0.2
```

---

## Parallel Processing Issues

### Thread Safety Errors

**Symptom**: Random crashes or corruption with parallel processing

**Solution**:
```bash
# Reduce worker count
nanorunner /source /target --parallel --worker-count 2

# Or disable parallel processing
nanorunner /source /target  # (default is sequential)

# Report bug with details:
# https://github.com/FOI-Bioinformatics/nanorunner/issues
```

### Workers Not Utilized

**Symptom**: Parallel mode shows no speedup

**Diagnosis**:
```bash
# Check batch size (must be > 1 for parallel benefit)
nanorunner /source /target --parallel --batch-size 10 --worker-count 4

# Monitor CPU usage
top  # or htop
```

**Solutions**:
- Batch size should be ≥ worker count
- Small files may not benefit from parallelization
- Use profile designed for parallel processing

---

## Configuration Issues

### Profile Not Found

**Symptom**: `Unknown profile: xyz`

**Solution**:
```bash
# List available profiles
nanorunner --list-profiles

# Check spelling (case-sensitive)
nanorunner /source /target --profile rapid_sequencing  # correct
nanorunner /source /target --profile Rapid_Sequencing  # incorrect
```

### Profile Overrides Not Working

**Symptom**: Profile settings not being overridden

**Example**:
```bash
# This works correctly:
nanorunner /source /target --profile rapid_sequencing --interval 10

# Profile is applied first, then interval override is applied
```

**Note**: Overrides are applied after profile. Check with verbose logging.

---

## Testing and Debugging

### Enable Debug Logging

```bash
# Set Python logging level
export PYTHONLOGLEVEL=DEBUG
nanorunner /source /target

# Or redirect all output
nanorunner /source /target 2>&1 | tee debug.log
```

### Run Test Suite

```bash
# Clone repository
git clone https://github.com/FOI-Bioinformatics/nanorunner.git
cd nanorunner

# Install dev dependencies
pip install -e .[dev]

# Run tests
pytest -v

# Run specific test
pytest tests/test_simulator.py -v

# Check coverage
pytest --cov=nanopore_simulator --cov-report=term-missing
```

### Verify Installation

```bash
# Check version
nanorunner --version

# Test imports
python -c "from nanopore_simulator import SimulationConfig; print('OK')"

# List available options
nanorunner --help
nanorunner --list-profiles
nanorunner --list-adapters
```

---

## Platform-Specific Issues

### macOS: Permission Issues

**Symptom**: `Operation not permitted` on macOS

**Solution**:
```bash
# Grant Terminal full disk access
# System Preferences → Security & Privacy → Privacy → Full Disk Access

# Or use accessible directory
nanorunner /source ~/Documents/nanorunner_output
```

### Windows: Path Issues

**Symptom**: Backslash problems in Windows paths

**Solution**:
```bash
# Use forward slashes
nanorunner C:/data/source C:/output

# Or use raw strings in Python
# (when using API directly)
```

### Linux: SELinux Restrictions

**Symptom**: Permission denied despite correct permissions

**Solution**:
```bash
# Check SELinux status
getenforce

# Temporarily disable (not recommended for production)
sudo setenforce 0

# Or add proper SELinux context
chcon -R -t user_home_t /path/to/target
```

---

## Getting Help

### Before Opening an Issue

1. **Search existing issues**: [GitHub Issues](https://github.com/FOI-Bioinformatics/nanorunner/issues)
2. **Check documentation**: [README](../README.md), [Quick Start](quickstart.md)
3. **Try examples**: Run `examples/*.py` to verify installation
4. **Enable debug logging**: Capture full error output

### Opening an Issue

Include:
- NanoRunner version: `nanorunner --version`
- Python version: `python --version`
- Operating system: `uname -a` (Linux/macOS) or `ver` (Windows)
- Full error message
- Command used
- Minimal reproducing example

### Community Support

- **GitHub Discussions**: [Ask questions](https://github.com/FOI-Bioinformatics/nanorunner/discussions)
- **Bug Reports**: [Report bugs](https://github.com/FOI-Bioinformatics/nanorunner/issues/new?template=bug_report.yml)
- **Feature Requests**: [Suggest features](https://github.com/FOI-Bioinformatics/nanorunner/issues/new?template=feature_request.yml)

---

## FAQ

### Q: Can I pause and resume a simulation?

**A**: Yes, with enhanced monitoring:
```bash
nanorunner /source /target --monitor enhanced
# Press Ctrl+C for graceful shutdown
# Progress is automatically checkpointed every 10 files
```

### Q: How do I simulate very fast sequencing (< 1 second)?

**A**:
```bash
# Use fractional intervals
nanorunner /source /target --interval 0.1  # 100ms
nanorunner /source /target --interval 0.01  # 10ms
```

### Q: Can I use NanoRunner in CI/CD?

**A**: Yes, disable monitoring for automated runs:
```bash
nanorunner /source /target --monitor none --quiet
```

### Q: Does NanoRunner modify source files?

**A**: No, source files are never modified. Only target directory is affected.

### Q: Can I resume an interrupted simulation?

**A**: Not automatically, but checkpoints show progress. Manually skip already-processed files or clean target and restart.

---

**Still stuck?** Open an issue: https://github.com/FOI-Bioinformatics/nanorunner/issues/new/choose
