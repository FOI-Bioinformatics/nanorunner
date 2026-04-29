# nanorunner audit -- 2026-04-29

Scope: `/Users/andreassjodin/Code/nanorunner` at branch `dev2` (per the
running checkout). Verified with `pytest --collect-only` (730 tests),
`pytest -q --no-cov` (730 passed), and targeted greps. Coverage
measured at 88% (CLAUDE.md line 277 claims 90%; docs/README.md line 42
claims 92%).

## Scoring (out of 10)

| Subpart | Score | Justification |
|---------|-------|---------------|
| CLI surface (`cli.py`, `cli_replay.py`, `cli_generate.py`, `cli_utils.py`, `cli_helpers.py`) | 6/10 | Subcommand split is clean and Typer rich-help-panel use is good. Negatives: `cli.py:138` re-exports `_*` helpers solely so old-style imports keep working (transitional cruft); `cli_utils.py:223-439` re-implements the genome-resolution loop already in `cli_helpers.py:141-251`; `cli_replay.py:192,194` uses `value != default` as a "did the user pass it?" probe (broken when user explicitly passes the default), which `cli_generate.py:207-297` correctly fixed with `Optional` sentinels -- inconsistent. |
| Core simulation (`runner.py`, `manifest.py`, `executor.py`) | 8/10 | The plan-execute-monitor split is genuine and well-commented. `runner.py:266-287` is a clear ~30-line loop. `manifest.py` rechunk path with `_build_chunk_offsets` is non-trivial but documented. The `_signal_handler` install/restore (runner.py 50-81) is exercised by tests. Minor: `_OPERATION_TIMEOUT = 600` (runner.py:317) is a magic constant only consulted in the parallel path. |
| Detection layer (`detection.py`) | 9/10 | 121 lines, four functions, fully covered (100%). No abstractions added that aren't needed. `_BARCODE_PATTERNS` (detection.py:13-18) is simple and case-insensitive. Nothing to remove. |
| Adapters (`adapters.py`) | 8/10 | Dict-based registry with `_resolve_name` alias handling is clean and matches CLAUDE.md's "no ABC" guidance. Both pipeline entries (`nanometa`, `kraken`) currently share the *exact same* pattern list (adapters.py:21-37); the registry would still be justified by future divergence but today it is a single shape. |
| Tests | 6/10 | 730 passing tests, but 88% coverage (under the `--cov-fail-under=90` set in `pytest.ini:14` -- the CI threshold would fail today). `test_coverage_boost.py` and `test_cli_coverage.py` exist purely to push coverage; their existence indicates the primary suites under-cover error paths. Four `pytest.mark.slow` warnings emitted on every run despite the marker being registered in `pytest.ini:16` (likely an interaction with `--strict-markers` plus filter ordering). `tests/__init__.py` is empty. |
| Docs | 5/10 | Two README files (root + `docs/README.md`) plus `CLAUDE.md` overlap heavily. README.md "Key Features" advertises Pause/resume and "Checkpoint system" that the runner does not invoke (see Orphans below). `docs/README.md:42` says 722 tests / 92% coverage; reality is 730 / 88%. Six plan documents under `docs/plans/` are useful history but not linked from the docs index. The `bin/nanopore-simulator` shell entry point imports a non-existent module. |
| **Aggregate** | **42/60 (70%)** | Solid plan-execute-monitor architecture and a thorough test suite let down by accumulated transitional layers (CLI re-exports, duplicated download path, dead worker-pool scaffolding, broken `bin/` script) and documentation drift (advertised features that the runner never wires up). The codebase reads like two refactors stacked: the original simulator was decomposed cleanly, but the second pass to split the CLI left compatibility shims that should now be removed. |

## Orphan code (verified)

Each item below was confirmed by grep and Read against the working tree.

- `nanopore_simulator/generators.py:41-55` -- `_WORKER_GENOME_CACHE` dict
  and `_init_worker_genomes(...)` initializer. Comment says
  "Module-level genome cache for ProcessPoolExecutor workers", but
  `grep -rn ProcessPoolExecutor nanopore_simulator/` returns only the
  comments themselves; the runner uses `ThreadPoolExecutor`
  exclusively (`runner.py:18`). The only references outside the file
  are in `tests/test_generators.py:603-617`, which test the symbol's
  *existence* but never exercise an actual pool.
- `nanopore_simulator/generators.py:600-623` -- `BuiltinGenerator._write_fastq`.
  `grep -rn '_write_fastq\b'` returns exactly one hit: the definition
  itself. The streaming path (`_write_reads_streaming`) replaced it.
- `nanopore_simulator/profiles.py:13-20` -- `_GENERATE_FIELDS` tuple.
  `grep -rn '_GENERATE_FIELDS'` returns the definition only. Profiles
  are filtered by `apply_profile()` via the `description` key, not by
  this allow-list.
- `nanopore_simulator/fastq.py:18-46` -- `count_reads(path)`.
  `grep -rn 'count_reads\b'` shows it is referenced only from
  `tests/test_fastq.py`. Production code uses
  `count_reads_with_offsets` (fastq.py:49) which already returns the
  read count.
- `nanopore_simulator/mocks.py:699-710` -- `list_mocks()` is referenced
  only in `tests/test_mocks.py`. The CLI command `list-mocks`
  (`cli_utils.py:59-79`) reaches into `BUILTIN_MOCKS` and
  `MOCK_ALIASES` directly instead of calling this helper.
- `nanopore_simulator/species.py:505-509` -- `resolve_taxid(...)` accepts
  `cache: Optional[GenomeCache] = None` but the function body never
  reads it (species.py:523-530). The docstring explicitly says
  "unused here; for API consistency".
- `nanopore_simulator/species.py:165-169` -- `ResolutionCache.clear()`
  is called only from `tests/test_species.py:208`. No production code
  invokes it.
- `nanopore_simulator/monitoring.py:265-281` -- `pause()`, `resume()`,
  `is_paused()`, `wait_if_paused()` on `ProgressMonitor`. README.md
  advertises "Interactive controls: Pause/resume functionality", but
  `grep -rn 'pause\|resume\|wait_if_paused' nanopore_simulator/runner.py`
  returns no hits -- the runner installs SIGTERM/SIGHUP handlers
  (runner.py:50-72) but they raise `KeyboardInterrupt` rather than
  toggling pause state.
- `nanopore_simulator/monitoring.py:55-62` -- `format_time(seconds)`.
  Production callers: zero (only `format_bytes` is used, in
  `runner.py:144,150`). Tests in `test_monitoring.py:310-319` and
  `test_coverage_boost.py:188-194` are the only consumers.
- `bin/nanopore-simulator:5` -- imports `from nanopore_simulator.cli.main
  import main`. `cli` is a module (`cli.py`), not a package; the
  import raises `ModuleNotFoundError: 'nanopore_simulator.cli' is not
  a package` (verified by running it under the `nanorunner` env). The
  installed console-script entry point is `nanorunner =
  nanopore_simulator.cli:main` (`pyproject.toml:41`). The broken
  `bin/` script is still shipped via `MANIFEST.in:5` (`recursive-include
  bin *`).
- `nanopore_simulator.egg-info/` and `nanorunner.egg-info/` (repository
  root) -- two parallel egg-info trees. The package was renamed
  (top-level dir `nanopore_simulator/`, distribution name `nanorunner`)
  but the obsolete `nanopore_simulator.egg-info/` was never removed.
  Build artefacts; should be `.gitignore`d.

Documentation drift items (factual but not "code"):

- `docs/README.md:42` claims "722 tests / 92% coverage". Actual:
  `pytest --collect-only` reports 730 tests; `pytest --cov` reports
  88%. CLAUDE.md:277 also says 722.
- README.md "Key Features" lists "Checkpoint system: Automatic
  progress preservation for recovery from interruptions". No
  checkpointing code exists; `grep -rn 'checkpoint' nanopore_simulator/`
  returns nothing.

## Simplification opportunities (top 5)

### 1. Delete the dead `_WORKER_GENOME_CACHE` / `_init_worker_genomes`

```diff
--- a/nanopore_simulator/generators.py
@@ -38,21 +38,6 @@
 logger = logging.getLogger(__name__)
 
 
-# Module-level genome cache for ProcessPoolExecutor workers.
-# Populated by _init_worker_genomes() which is passed as the
-# ``initializer`` argument when the pool is created, so each worker
-# process receives pre-parsed genome data without redundant I/O.
-_WORKER_GENOME_CACHE: Dict[str, str] = {}
-
-
-def _init_worker_genomes(genome_data: Dict[str, str]) -> None:
-    """Initializer for ProcessPoolExecutor workers.
-
-    Pre-populates the module-level genome cache so that workers can
-    skip redundant FASTA parsing.
-    """
-    global _WORKER_GENOME_CACHE
-    _WORKER_GENOME_CACHE = genome_data
```

Then drop `tests/test_generators.py::TestWorkerGenomeCache` (lines
601-617). The runner uses `ThreadPoolExecutor`, which shares
in-process state via `BuiltinGenerator._genome_cache` already, so this
scaffold has no realistic future use.

### 2. Replace the `download` command body with a call into `_resolve_and_download_genomes`

`cli_utils.py:343-402` and `cli_helpers.py:141-251` are nearly
line-for-line the same loop (verified by direct comparison). The
helper already supports `mock`/`species`/`taxid` and returns
`(paths, abundances)`. Replace the in-line loop with:

```diff
--- a/nanopore_simulator/cli_utils.py
@@ -331,53 +331,18 @@
     # Resolve and download
-    from nanopore_simulator.species import (
-        GenomeCache,
-        GenomeRef,
-        download_genome,
-        resolve_species,
-        resolve_taxid,
-    )
-    from nanopore_simulator.mocks import get_mock
-
-    cache = GenomeCache()
-    genome_downloads: List[tuple] = []  # (name, ref) pairs
-    mock_community = None
-
-    if mock:
-        mock_community = get_mock(mock)
-        ...  # 50 lines of duplicated resolve+download logic
+    from nanopore_simulator.cli_helpers import _resolve_and_download_genomes
+
+    species_inputs = list(species) if species else None
+    taxid_inputs = [str(t) for t in taxid] if taxid else None
+    successful_paths, _abundances = _resolve_and_download_genomes(
+        mock_name=mock,
+        species_inputs=species_inputs,
+        taxid_inputs=taxid_inputs,
+        offline=False,
+    )
```

Removes ~60 lines of duplication and makes the `download` command
honour the same renormalisation logic the rest of nanorunner uses.

### 3. Remove the `cli.py` `# noqa` re-export block

```diff
--- a/nanopore_simulator/cli.py
@@ -132,16 +132,4 @@
-from nanopore_simulator import cli_replay, cli_generate, cli_utils  # noqa: F401,E402
-
-# Re-export helpers so that existing imports of the form
-#   from nanopore_simulator.cli import _resolve_monitor, _build_timing_params
-# continue to work without modification.
-from nanopore_simulator.cli_helpers import (  # noqa: F401,E402
-    _build_timing_params,
-    _resolve_monitor,
-    _validate_timing_params,
-    _expand_genome_paths,
-    _find_genome_files,
-    _resolve_and_download_genomes,
-    _run_pipeline_validation,
-    _GENOME_EXTENSIONS,
-)
+# Register subcommands. Imports must come after `app` is defined.
+from nanopore_simulator import cli_replay, cli_generate, cli_utils  # noqa: F401,E402
```

Then update three test imports (`tests/test_cli.py:955-1007`,
`tests/test_cli_coverage.py:13`) to import directly from
`cli_helpers`. The re-exports exist solely for "old-style imports
continue to work"; nothing outside the project's own tests imports
them, so the back-compat shim has no audience.

### 4. Delete or rewire `bin/nanopore-simulator`

Either remove the script (`pyproject.toml:41` already provides the
`nanorunner` console entry point) or fix the import:

```diff
--- a/bin/nanopore-simulator
+++ b/bin/nanopore-simulator
-from nanopore_simulator.cli.main import main
+from nanopore_simulator.cli import main
```

Also drop `recursive-include bin *` from `MANIFEST.in:5` if the script
is removed. As written today, the file is shipped in source
distributions and immediately raises `ModuleNotFoundError`.

### 5. Drop the dead `_GENERATE_FIELDS`, `count_reads`, `format_time`, `list_mocks`, `_write_fastq`, `ResolutionCache.clear` block

These are cheap to remove (single-file, no production callers). The
combined diff is small and removes roughly 80 lines, with matching
test removal. They were public-API speculation that no real consumer
exists for; if a need arises later they cost a few minutes to
re-introduce, whereas keeping them now obscures the actual surface
area of each module.

## Risks / things NOT to simplify

- **Do not collapse `Monitor` Protocol + `NullMonitor`.** The Protocol
  is `@runtime_checkable` and `tests/test_monitoring.py:252-274` use
  `isinstance(mon, Monitor)` as part of the contract. Removing
  `NullMonitor` in favour of `Optional[ProgressMonitor]` would force
  conditional checks back into `runner.py:_record_progress` and the
  parallel-execution path.
- **Do not collapse `TimingModel` ABC into a single function.** Four
  models exist (Uniform / Random / Poisson / Adaptive). Two of them
  (Adaptive, Poisson) carry per-instance state (`interval_history`,
  `current_mean`, `base_rate`) that motivates the class form. The
  factory at `timing.py:157-170` is dict-based and already minimal.
- **Do not unify `BuiltinGenerator` and `SubprocessGenerator`.** They
  diverge in real ways (in-process FASTA cache vs subprocess pipe;
  exact vs approximate read counts -- noted in `generators.py:638-643`).
  Their shared shape is genuinely just `generate_reads(...)`.
- **Do not turn the `ADAPTERS` dict into a class.** The CLAUDE.md
  guidance ("no ABC") and the public-API surface (`validate_output`,
  `list_adapters`, `get_adapter_info`) keep adapters as data. A new
  pipeline today is a 7-line dict entry.
- **Do not delete `format_bytes`.** Unlike `format_time`, it is used
  by `runner.py:144,150` for the disk-space warning.
- **Do not "fix" `cli_replay.py`'s `value != default` sentinel
  detection in a single commit.** Behavioural change: anyone who
  invokes `nanorunner replay --batch-size 1 --profile development`
  today silently gets profile's `batch_size=10`; switching to
  `Optional` sentinels would now respect the explicit `1`. That is
  the correct behaviour but requires a test pass and a CHANGELOG
  entry, not a drive-by tidy-up.
