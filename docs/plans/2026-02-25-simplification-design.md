# Nanorunner Simplification: Plan-Execute-Monitor Rewrite

**Date:** 2026-02-25
**Status:** Approved
**Approach:** Nuclear rewrite — rebuild internals, preserve CLI contract

## Problem

The codebase has grown to ~10,000 lines across 14 source files with ~17,500 lines across 40 test files. Two modules (`simulator.py` at 1,405 lines and `cli/main.py` at 1,409 lines) account for 37% of source code and exhibit god object patterns. The simulator imports from 8 other core modules and has 30+ methods across 5 distinct execution paths. Test files are fragmented with `*_coverage.py` files added incrementally rather than organized coherently.

## Constraints

- **CLI contract preserved** — all `nanorunner` subcommands, flags, and behavior remain identical
- **All features retained** — replay, generate, mocks, species resolution, adapters, monitoring, timing models, rechunking, profiles
- **Internal APIs may change freely** — no backward compatibility requirement for Python imports

## Architecture: Plan-Execute-Monitor

The god object decomposes into three phases connected by a simple orchestration loop:

1. **Plan** (`manifest.py`): config → list of `FileEntry` describing what files to produce
2. **Execute** (`executor.py`): one `FileEntry` → one file on disk
3. **Monitor** (`monitoring.py`): progress tracking and display

The orchestrator (`runner.py`) is ~20 lines of glue:

```python
def _execute_manifest(manifest, config, generator=None):
    timing = create_timing_model(config.timing_model, config.timing_params)
    monitor = create_monitor(config, len(manifest))
    batches = _group_by_batch(manifest)
    for batch in batches:
        if config.parallel:
            _execute_batch_parallel(batch, generator, config.workers)
        else:
            for entry in batch:
                execute_entry(entry, generator)
                monitor.update(entry)
        timing.wait()
```

## Module Structure

Flat layout — no `core/` or `cli/` subdirectories.

```
nanopore_simulator/
  __init__.py          # Version, public API
  cli.py               # Thin typer CLI (~400 lines)
  config.py            # ReplayConfig + GenerateConfig (~150 lines)
  manifest.py          # Build file manifests for both modes (~300 lines)
  executor.py          # Produce one file (copy/link/generate) (~200 lines)
  runner.py            # Orchestration loop + parallel (~150 lines)
  timing.py            # Timing model implementations (~190 lines)
  generators.py        # Read generation backends (~350 lines)
  species.py           # Species/genome resolution (~800 lines)
  mocks.py             # Mock community data (~500 lines)
  monitoring.py        # Progress display + tracking (~600 lines)
  detection.py         # Input structure detection (~90 lines)
  adapters.py          # Pipeline validation, dict-based (~100 lines)
  profiles.py          # Configuration presets (~250 lines)
  deps.py              # Dependency checking (~200 lines)
  fastq.py             # FASTQ read/write utilities (~100 lines)
```

**Target: ~4,100 lines** (vs ~10,000 current, ~60% reduction).

### Dependency Direction

```
cli.py → config, profiles, adapters, deps, mocks
         ↓
       runner.py → manifest, executor, monitoring, timing
                   ↓                ↓
              config, detection,   generators, species
              generators, species  fastq
```

No circular dependencies.

## Configuration Design

Split `SimulationConfig` (52 fields, 150-line validation) into two mode-specific dataclasses:

**`ReplayConfig`** (~15 fields): source_dir, target_dir, operation, interval, batch_size, file_extensions, timing_model, timing_params, parallel, workers, monitor_type, adapter, reads_per_output, structure.

**`GenerateConfig`** (~20 fields): target_dir, genome_inputs, species_inputs, mock_name, taxid_inputs, abundances, read_count, interval, batch_size, generator_backend, mean_length, std_length, mean_quality, std_quality, timing_model, timing_params, parallel, workers, monitor_type, adapter, structure.

Each config validates only its own fields in `__post_init__` (~30 lines each). No conditional validation, no `object.__setattr__()` hacks.

## Manifest Design

`FileEntry` dataclass represents one planned file operation:

```python
@dataclass
class FileEntry:
    source: Path | None       # None for generate mode
    target: Path
    operation: str            # "copy", "link", or "generate"
    genome: Path | None       # For generate mode
    read_count: int | None    # For generate mode
    batch: int                # Batch assignment
```

Two builder functions:
- `build_replay_manifest(config: ReplayConfig) -> list[FileEntry]` — detects structure, enumerates source files, handles rechunking
- `build_generate_manifest(config: GenerateConfig) -> list[FileEntry]` — resolves species/mocks, distributes reads across genomes

Both are pure data transformations: config in, list out.

## Executor Design

Single dispatch function:

```python
def execute_entry(entry: FileEntry, generator: ReadGenerator | None = None) -> Path:
    if entry.operation == "copy":
        return _copy_file(entry.source, entry.target)
    elif entry.operation == "link":
        return _link_file(entry.source, entry.target)
    elif entry.operation == "generate":
        return _generate_file(entry, generator)
```

No orchestration, no timing, no monitoring. File I/O only.

## Abstraction Simplifications

### PipelineAdapter → Dict-based validation

Delete `PipelineAdapter` ABC and `GenericAdapter` class. Replace with:
- `ADAPTERS` dict mapping names to validation specs
- `validate_output(target, adapter_name) -> list[str]` function
- 325 lines → ~100 lines

### ReadGenerator → Unified subprocess wrapper

Merge `BadreadGenerator` and `NanoSimGenerator` into `SubprocessGenerator` parameterized by backend name and command builder. Keep `BuiltinGenerator` as-is. Keep `ReadGenerator` ABC (justified with 2 distinct implementations).
- 706 lines → ~350 lines

### Monitoring → Trimmed

Keep resource tracking, pause/resume, progress display. Remove unused `SimulationMetrics` fields. Simplify ETA estimation.
- 996 lines → ~600 lines

## CLI Design

Single `cli.py` file (~400 lines). Typer parameters map directly to config dataclass fields. No `_build_config()` monster. Validation lives in config `__post_init__`, not duplicated in CLI.

```python
@app.command()
def replay(source: Path, target: Path, interval: float = 1.0, ...):
    config = ReplayConfig(**_filter_params(locals(), ReplayConfig))
    run_replay(config)
```

## Test Reorganization

**40 → 16 files, ~17,500 → ~8,000 lines.**

```
tests/
  conftest.py              # Shared fixtures
  test_config.py           # Config validation
  test_manifest.py         # Manifest building
  test_executor.py         # File operations
  test_runner.py           # Orchestration
  test_timing.py           # Timing models
  test_generators.py       # Read generators
  test_species.py          # Species resolution
  test_mocks.py            # Mock communities
  test_monitoring.py       # Monitoring
  test_detection.py        # Structure detection
  test_adapters.py         # Pipeline validation
  test_profiles.py         # Profiles
  test_deps.py             # Dependencies
  test_cli.py              # CLI commands
  test_integration.py      # End-to-end workflows
  test_practical.py        # Real genome tests (marked slow)
```

Tests written from scratch, organized by module, testing behavior rather than implementation.

## Size Targets

| Area | Current | Target | Reduction |
|------|---------|--------|-----------|
| Source code | ~10,000 lines / 14 files | ~4,100 lines / 16 files | 60% fewer lines |
| Test code | ~17,500 lines / 40 files | ~8,000 lines / 16 files | 54% fewer lines |
| Largest module | 1,405 lines (simulator.py) | ~800 lines (species.py) | No module exceeds 800 |
| Config fields | 52 in one class | ~15 + ~20 in two classes | Clear separation |
