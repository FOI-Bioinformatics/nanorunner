# nanorunner troubleshooting

Common issues and resolutions. nanorunner targets POSIX-compliant
operating systems (Linux, macOS); Windows is not supported.

## Installation issues

### Command not found after install

**Symptom:** `nanorunner: command not found`

```bash
# Check if pip's install location is on PATH
pip show nanorunner | grep Location

# If installed with --user, ensure the user-bin directory is on PATH
export PATH="$HOME/.local/bin:$PATH"

# As a fallback, invoke the module directly
python -m nanopore_simulator.cli --help
```

### Permission denied during install

```bash
# Option 1: install into a virtual environment (recommended)
python -m venv nanorunner_env
source nanorunner_env/bin/activate
pip install git+https://github.com/FOI-Bioinformatics/nanorunner.git

# Option 2: install into the user site-packages directory
pip install --user git+https://github.com/FOI-Bioinformatics/nanorunner.git
```

### Python version mismatch

`Requires Python '>=3.9' but the running Python is 3.8`. Use a Python
3.9 or newer interpreter:

```bash
python3.11 -m pip install git+https://github.com/FOI-Bioinformatics/nanorunner.git
```

---

## Missing dependencies

Always start with the dependency checker:

```bash
nanorunner check-deps
```

It reports the status of all optional dependencies and prints install
hints for missing ones.

### badread fails to start

**Symptom:** `badread exited with status 1`, or
`ModuleNotFoundError: No module named 'edlib'`.

nanorunner verifies that backends actually start, not just that their
binary exists on `PATH`. badread can be partially installed (binary
present, Python deps missing).

```bash
conda install -c conda-forge -c bioconda badread
nanorunner check-deps
```

### NCBI datasets CLI missing

**Symptom:** `datasets CLI is required` when using `--species`,
`--mock`, or `--taxid`.

```bash
conda install -c conda-forge ncbi-datasets-cli
datasets --version
```

### NanoSim fails to start

```bash
conda install -c conda-forge -c bioconda nanosim
nanorunner check-deps
```

### NumPy not installed

Read generation falls back to a pure-Python implementation if numpy is
missing. For better generation performance:

```bash
conda install -c conda-forge numpy
```

### Enhanced monitoring not available

The `--monitor enhanced` mode requires `psutil`:

```bash
conda install -c conda-forge psutil
# Or install nanorunner with the enhanced extra:
pip install "nanorunner[enhanced] @ git+https://github.com/FOI-Bioinformatics/nanorunner.git"
```

---

## Runtime issues

### Permission denied on the target directory

```bash
ls -ld /path/to/target           # Inspect ownership and mode
chmod 755 /path/to/target        # Fix permissions
# Or write to a directory you own:
nanorunner replay -s /source -t ~/nanorunner_output
```

### Source directory not found

```bash
ls /path/to/source               # Verify the path exists
nanorunner --help                # Check option spellings
```

### No sequencing files found

`ValueError: No sequencing files found in /source`. nanorunner accepts
`.fastq`, `.fq`, `.fastq.gz`, `.fq.gz`. For multiplex layouts, the
files live inside `barcode##/` subdirectories.

```bash
find /source -name "*.fastq*" -o -name "*.fq*"   # Confirm what is there
ls -la /source                                    # Surface hidden files
```

### Out of memory or slow performance

```bash
# Lower batch size
nanorunner replay -s /source -t /target --batch-size 5

# Use symlinks instead of copies
nanorunner replay -s /source -t /target --operation link

# Add resource tracking to confirm CPU / memory pressure
nanorunner replay -s /source -t /target --monitor enhanced
```

For sustained throughput problems, the high-throughput profile bundles
parallel processing and burst timing:

```bash
nanorunner replay -s /source -t /target --profile high_throughput
```

---

## Monitoring issues

### Progress bar not displaying

```bash
echo -e "\033[32mGreen\033[0m"   # Confirm terminal supports ANSI

# Disable monitoring entirely
nanorunner replay -s /source -t /target --monitor none

# Capture both monitor and program output to a log
nanorunner replay -s /source -t /target 2>&1 | tee simulation.log
```

---

## Pipeline integration

### Validation fails

`Pipeline validation failed` or `Structure not valid`:

```bash
# Inspect the validator's view
nanorunner validate --pipeline nanometa --target /target

# Inspect the actual structure
ls -R /target
find /target -name "*.fastq*"
```

The `nanometa` adapter accepts both singleplex and multiplex layouts;
the `kraken` adapter accepts any directory containing FASTQ files.

### Pipeline adapter not found

```bash
nanorunner list-adapters
```

If your pipeline is not listed, the generic adapter is available via
the Python API.

---

## File-system issues

### Symlinks across filesystems

Symbolic links cannot cross some filesystem boundaries. Use copy mode:

```bash
nanorunner replay -s /mnt/source -t /home/user/target --operation copy
```

### Disk space exhausted

```bash
df -h /target

# Use symlinks instead of copies
nanorunner replay -s /source -t /target --operation link

# Or smaller batches and clean up between runs
rm -rf /tmp/nanorunner_*
```

---

## Configuration issues

### Profile not found

```bash
nanorunner list-profiles
```

Profile names are case-sensitive. `--profile bursty` works;
`--profile Bursty` does not.

### Verifying overrides

Per-flag overrides apply after the profile, so the explicit value wins:

```bash
nanorunner replay -s /source -t /target --profile bursty --interval 10
# Result: bursty profile with interval = 10
```

---

## Testing and debugging

### Enable debug logging

```bash
PYTHONLOGLEVEL=DEBUG nanorunner replay -s /source -t /target

# Or capture all output for review
nanorunner replay -s /source -t /target 2>&1 | tee debug.log
```

### Run the test suite

```bash
git clone https://github.com/FOI-Bioinformatics/nanorunner.git
cd nanorunner
pip install -e .[dev]

pytest -v
pytest tests/test_runner.py -v       # A single module
pytest --cov=nanopore_simulator --cov-report=term-missing
```

### Verify installation

```bash
nanorunner --version
python -c "from nanopore_simulator import ReplayConfig; print('OK')"
nanorunner --help
nanorunner list-profiles
nanorunner list-adapters
```

---

## FAQ

### Can I pause and resume a simulation?

No. Pause / resume and checkpointing are not implemented. Use Ctrl+C
for graceful shutdown; restart from the beginning, or run on a subset
of source files.

### How do I simulate sub-second intervals?

```bash
nanorunner replay -s /source -t /target --interval 0.1   # 100 ms
nanorunner replay -s /source -t /target --interval 0.01  # 10 ms
```

### Can I use nanorunner in CI?

Yes -- disable interactive monitoring:

```bash
nanorunner replay -s /source -t /target --monitor none --quiet
```

### Does nanorunner modify source files?

No. Source files are never written to; only the target directory is
modified.

### Can I resume an interrupted simulation?

Not automatically. Either restrict the source directory to the
remaining files (e.g. by symlinking only the unsent files into a fresh
source) or clear the target and start again.

---

## Getting help

Before opening an issue:

1. Search [existing issues](https://github.com/FOI-Bioinformatics/nanorunner/issues).
2. Re-read the [usage guide](quickstart.md) and main [README](../README.md).
3. Run an example from `examples/` to confirm the install works.
4. Capture full error output with `2>&1 | tee debug.log`.

Include in the report:

- nanorunner version (`nanorunner --version`)
- Python version (`python --version`)
- Operating system (`uname -a`)
- Full error message and the exact command used
- A minimal reproducer

Channels:

- [GitHub Discussions](https://github.com/FOI-Bioinformatics/nanorunner/discussions)
- [Bug reports](https://github.com/FOI-Bioinformatics/nanorunner/issues/new?template=bug_report.yml)
- [Feature requests](https://github.com/FOI-Bioinformatics/nanorunner/issues/new?template=feature_request.yml)
