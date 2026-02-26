# Nanorunner Simplification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rewrite nanorunner internals using plan-execute-monitor decomposition, reducing ~10,000 lines to ~4,100 lines while preserving the CLI contract and all features.

**Architecture:** Flat module layout. God object (`simulator.py`) decomposes into `manifest.py` (plan what files to produce), `executor.py` (produce one file), and `runner.py` (orchestrate the loop). Two mode-specific configs replace the 52-field monolith. PipelineAdapter ABC replaced with dict-based validation. Subprocess generators unified.

**Tech Stack:** Python 3.9+, typer (CLI), pytest (testing), optional: psutil, numpy, badread, nanosim

**Design doc:** `docs/plans/2026-02-25-simplification-design.md`

---

## Phase 1: New Package Structure

### Task 1: Scaffold flat package layout

**Files:**
- Create: `nanopore_simulator_v2/` (build alongside existing, swap at end)
- Create: `nanopore_simulator_v2/__init__.py`

**Step 1: Create the new package directory**

```bash
mkdir -p nanopore_simulator_v2
```

**Step 2: Create __init__.py**

```python
"""nanorunner - nanopore sequencing run simulator."""

__version__ = "3.0.0"
```

**Step 3: Commit**

```bash
git add nanopore_simulator_v2/
git commit -m "chore: scaffold v2 package structure for rewrite"
```

**Notes:** We build `nanopore_simulator_v2/` alongside the existing package so all existing tests continue to pass throughout. At the very end (Task 17), we swap directories.

---

## Phase 2: Foundation Modules (no internal dependencies)

### Task 2: config.py — ReplayConfig + GenerateConfig

**Files:**
- Create: `nanopore_simulator_v2/config.py`
- Create: `tests_v2/test_config.py`
- Create: `tests_v2/__init__.py`
- Create: `tests_v2/conftest.py`

**Step 1: Write failing tests**

```python
# tests_v2/test_config.py
"""Tests for configuration dataclasses."""

import pytest
from pathlib import Path
from nanopore_simulator_v2.config import ReplayConfig, GenerateConfig


class TestReplayConfig:
    """ReplayConfig validation and defaults."""

    def test_minimal_valid(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        target = tmp_path / "target"
        cfg = ReplayConfig(source_dir=source, target_dir=target)
        assert cfg.interval == 5.0
        assert cfg.operation == "copy"
        assert cfg.batch_size == 1
        assert cfg.timing_model == "uniform"
        assert cfg.parallel is False
        assert cfg.workers == 4
        assert cfg.monitor_type == "basic"

    def test_link_operation(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        cfg = ReplayConfig(source_dir=source, target_dir=tmp_path / "t", operation="link")
        assert cfg.operation == "link"

    def test_invalid_operation(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        with pytest.raises(ValueError, match="operation"):
            ReplayConfig(source_dir=source, target_dir=tmp_path / "t", operation="delete")

    def test_negative_interval(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        with pytest.raises(ValueError, match="interval"):
            ReplayConfig(source_dir=source, target_dir=tmp_path / "t", interval=-1.0)

    def test_zero_interval_allowed(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        cfg = ReplayConfig(source_dir=source, target_dir=tmp_path / "t", interval=0.0)
        assert cfg.interval == 0.0

    def test_invalid_batch_size(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        with pytest.raises(ValueError, match="batch_size"):
            ReplayConfig(source_dir=source, target_dir=tmp_path / "t", batch_size=0)

    def test_source_dir_must_exist(self, tmp_path):
        with pytest.raises(ValueError, match="source_dir"):
            ReplayConfig(source_dir=tmp_path / "nonexistent", target_dir=tmp_path / "t")

    def test_invalid_timing_model(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        with pytest.raises(ValueError, match="timing_model"):
            ReplayConfig(source_dir=source, target_dir=tmp_path / "t", timing_model="invalid")

    def test_invalid_monitor_type(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        with pytest.raises(ValueError, match="monitor_type"):
            ReplayConfig(source_dir=source, target_dir=tmp_path / "t", monitor_type="invalid")

    def test_invalid_structure(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        with pytest.raises(ValueError, match="structure"):
            ReplayConfig(source_dir=source, target_dir=tmp_path / "t", structure="invalid")

    def test_workers_must_be_positive(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        with pytest.raises(ValueError, match="workers"):
            ReplayConfig(source_dir=source, target_dir=tmp_path / "t", workers=0)

    def test_rechunking_config(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        cfg = ReplayConfig(
            source_dir=source,
            target_dir=tmp_path / "t",
            reads_per_output=500,
        )
        assert cfg.reads_per_output == 500

    def test_rechunking_incompatible_with_link(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        with pytest.raises(ValueError, match="rechunk.*link"):
            ReplayConfig(
                source_dir=source,
                target_dir=tmp_path / "t",
                operation="link",
                reads_per_output=500,
            )

    def test_all_file_extensions(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        cfg = ReplayConfig(source_dir=source, target_dir=tmp_path / "t")
        assert ".fastq" in cfg.file_extensions
        assert ".fq" in cfg.file_extensions
        assert ".fastq.gz" in cfg.file_extensions
        assert ".fq.gz" in cfg.file_extensions
        assert ".pod5" in cfg.file_extensions

    def test_custom_file_extensions(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        cfg = ReplayConfig(
            source_dir=source,
            target_dir=tmp_path / "t",
            file_extensions=(".fastq",),
        )
        assert cfg.file_extensions == (".fastq",)

    def test_frozen(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        cfg = ReplayConfig(source_dir=source, target_dir=tmp_path / "t")
        with pytest.raises(AttributeError):
            cfg.interval = 10.0


class TestGenerateConfig:
    """GenerateConfig validation and defaults."""

    def test_minimal_with_genomes(self, tmp_path):
        genome = tmp_path / "genome.fa"
        genome.write_text(">seq\nACGT\n")
        cfg = GenerateConfig(
            target_dir=tmp_path / "out",
            genome_inputs=[genome],
        )
        assert cfg.read_count == 1000
        assert cfg.interval == 5.0
        assert cfg.batch_size == 100
        assert cfg.generator_backend == "auto"
        assert cfg.mean_length == 5000
        assert cfg.std_length == 2000
        assert cfg.mean_quality == 20.0
        assert cfg.std_quality == 4.0

    def test_minimal_with_mock(self, tmp_path):
        cfg = GenerateConfig(
            target_dir=tmp_path / "out",
            mock_name="zymo_d6300",
        )
        assert cfg.mock_name == "zymo_d6300"

    def test_minimal_with_species(self, tmp_path):
        cfg = GenerateConfig(
            target_dir=tmp_path / "out",
            species_inputs=["Escherichia coli"],
        )
        assert cfg.species_inputs == ["Escherichia coli"]

    def test_minimal_with_taxids(self, tmp_path):
        cfg = GenerateConfig(
            target_dir=tmp_path / "out",
            taxid_inputs=["562"],
        )
        assert cfg.taxid_inputs == ["562"]

    def test_no_input_source(self, tmp_path):
        with pytest.raises(ValueError, match="genome.*species.*mock.*taxid"):
            GenerateConfig(target_dir=tmp_path / "out")

    def test_negative_read_count(self, tmp_path):
        genome = tmp_path / "genome.fa"
        genome.write_text(">seq\nACGT\n")
        with pytest.raises(ValueError, match="read_count"):
            GenerateConfig(
                target_dir=tmp_path / "out",
                genome_inputs=[genome],
                read_count=-1,
            )

    def test_invalid_generator_backend(self, tmp_path):
        genome = tmp_path / "genome.fa"
        genome.write_text(">seq\nACGT\n")
        with pytest.raises(ValueError, match="generator_backend"):
            GenerateConfig(
                target_dir=tmp_path / "out",
                genome_inputs=[genome],
                generator_backend="invalid",
            )

    def test_invalid_output_format(self, tmp_path):
        genome = tmp_path / "genome.fa"
        genome.write_text(">seq\nACGT\n")
        with pytest.raises(ValueError, match="output_format"):
            GenerateConfig(
                target_dir=tmp_path / "out",
                genome_inputs=[genome],
                output_format="bam",
            )

    def test_quality_params(self, tmp_path):
        genome = tmp_path / "genome.fa"
        genome.write_text(">seq\nACGT\n")
        cfg = GenerateConfig(
            target_dir=tmp_path / "out",
            genome_inputs=[genome],
            mean_quality=25.0,
            std_quality=2.0,
        )
        assert cfg.mean_quality == 25.0
        assert cfg.std_quality == 2.0

    def test_frozen(self, tmp_path):
        genome = tmp_path / "genome.fa"
        genome.write_text(">seq\nACGT\n")
        cfg = GenerateConfig(
            target_dir=tmp_path / "out",
            genome_inputs=[genome],
        )
        with pytest.raises(AttributeError):
            cfg.read_count = 5000

    def test_abundances_must_match_genomes(self, tmp_path):
        g1 = tmp_path / "g1.fa"
        g2 = tmp_path / "g2.fa"
        g1.write_text(">s\nACGT\n")
        g2.write_text(">s\nACGT\n")
        with pytest.raises(ValueError, match="abundances"):
            GenerateConfig(
                target_dir=tmp_path / "out",
                genome_inputs=[g1, g2],
                abundances=[0.5],  # should be 2 values
            )

    def test_abundances_must_sum_to_one(self, tmp_path):
        g1 = tmp_path / "g1.fa"
        g2 = tmp_path / "g2.fa"
        g1.write_text(">s\nACGT\n")
        g2.write_text(">s\nACGT\n")
        with pytest.raises(ValueError, match="abundances.*sum"):
            GenerateConfig(
                target_dir=tmp_path / "out",
                genome_inputs=[g1, g2],
                abundances=[0.3, 0.3],
            )
```

```python
# tests_v2/conftest.py
"""Shared test fixtures."""

import pytest
from pathlib import Path


@pytest.fixture
def sample_fasta(tmp_path):
    """Create a minimal FASTA file."""
    fasta = tmp_path / "genome.fa"
    fasta.write_text(">chr1\nACGTACGTACGTACGT\n>chr2\nTTTTAAAACCCCGGGG\n")
    return fasta


@pytest.fixture
def sample_fastq(tmp_path):
    """Create a minimal FASTQ file."""
    fastq = tmp_path / "reads.fastq"
    fastq.write_text(
        "@read1\nACGTACGT\n+\nIIIIIIII\n"
        "@read2\nTTTTAAAA\n+\nIIIIIIII\n"
    )
    return fastq


@pytest.fixture
def source_dir_singleplex(tmp_path):
    """Create a singleplex source directory with FASTQ files."""
    source = tmp_path / "source"
    source.mkdir()
    for i in range(5):
        (source / f"reads_{i}.fastq").write_text(
            f"@read{i}\nACGTACGT\n+\nIIIIIIII\n"
        )
    return source


@pytest.fixture
def source_dir_multiplex(tmp_path):
    """Create a multiplex source directory with barcode subdirs."""
    source = tmp_path / "source"
    source.mkdir()
    for bc in ["barcode01", "barcode02"]:
        bc_dir = source / bc
        bc_dir.mkdir()
        for i in range(3):
            (bc_dir / f"reads_{i}.fastq").write_text(
                f"@read{i}\nACGTACGT\n+\nIIIIIIII\n"
            )
    return source
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests_v2/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nanopore_simulator_v2.config'`

**Step 3: Write implementation**

Create `nanopore_simulator_v2/config.py` with `ReplayConfig` and `GenerateConfig` frozen dataclasses. Port validation logic from existing `nanopore_simulator/core/config.py:70-173` but split into per-config `__post_init__` methods (~30 lines each instead of 150).

Key field mappings from old `SimulationConfig`:
- `source_dir` → `ReplayConfig.source_dir`
- `target_dir` → both configs
- `interval` → both (default 5.0)
- `operation` → `ReplayConfig.operation` (replay only)
- `file_types` → `ReplayConfig.file_extensions` (as tuple)
- `force_structure` → both as `structure`
- `batch_size` → both (different defaults: 1 for replay, 100 for generate)
- `reads_per_output_file` → `ReplayConfig.reads_per_output`
- `timing_model` + `timing_model_params` → both as `timing_model` + `timing_params`
- `parallel_processing` + `worker_count` → both as `parallel` + `workers`
- `genome_inputs` → `GenerateConfig.genome_inputs`
- `generator_backend` → `GenerateConfig.generator_backend`
- `read_count` → `GenerateConfig.read_count`
- `mean_read_length` → `GenerateConfig.mean_length`
- `std_read_length` → `GenerateConfig.std_length`
- `min_read_length` → `GenerateConfig.min_length` (default 200)
- `mean_quality` / `std_quality` → `GenerateConfig`
- `reads_per_file` → `GenerateConfig.reads_per_file` (default 100)
- `output_format` → `GenerateConfig.output_format` (default "fastq.gz")
- `mix_reads` → `GenerateConfig.mix_reads`
- `species_inputs` / `mock_name` / `taxid_inputs` / `abundances` / `offline_mode` → `GenerateConfig`

Validation rules per config:
- `ReplayConfig.__post_init__`: source_dir exists, operation in {copy, link}, interval >= 0, batch_size >= 1, timing_model in {uniform, random, poisson, adaptive}, monitor_type in {basic, enhanced}, structure in {auto, singleplex, multiplex}, workers >= 1, rechunking incompatible with link
- `GenerateConfig.__post_init__`: at least one input source (genomes/species/mock/taxids), read_count >= 1, generator_backend in {auto, builtin, badread, nanosim}, output_format in {fastq, fastq.gz}, interval >= 0, batch_size >= 1, timing/monitor/structure validation same as replay, abundances length matches genome count, abundances sum to ~1.0

**Step 4: Run tests to verify they pass**

Run: `pytest tests_v2/test_config.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add nanopore_simulator_v2/config.py tests_v2/
git commit -m "feat(v2): add ReplayConfig and GenerateConfig with validation"
```

---

### Task 3: fastq.py — FASTQ utilities

**Files:**
- Create: `nanopore_simulator_v2/fastq.py`
- Create: `tests_v2/test_fastq.py`

**Step 1: Write failing tests**

```python
# tests_v2/test_fastq.py
"""Tests for FASTQ read/write utilities."""

import gzip
import pytest
from pathlib import Path
from nanopore_simulator_v2.fastq import count_reads, iter_reads, write_reads


class TestCountReads:
    def test_plain_fastq(self, sample_fastq):
        assert count_reads(sample_fastq) == 2

    def test_gzipped_fastq(self, tmp_path):
        fq = tmp_path / "reads.fastq.gz"
        with gzip.open(fq, "wt") as f:
            f.write("@r1\nACGT\n+\nIIII\n@r2\nTTTT\n+\nIIII\n")
        assert count_reads(fq) == 2

    def test_empty_file(self, tmp_path):
        fq = tmp_path / "empty.fastq"
        fq.write_text("")
        assert count_reads(fq) == 0


class TestIterReads:
    def test_yields_tuples(self, sample_fastq):
        reads = list(iter_reads(sample_fastq))
        assert len(reads) == 2
        header, seq, sep, qual = reads[0]
        assert header.startswith("@")
        assert sep == "+"
        assert len(seq) == len(qual)

    def test_gzipped(self, tmp_path):
        fq = tmp_path / "reads.fastq.gz"
        with gzip.open(fq, "wt") as f:
            f.write("@r1\nACGT\n+\nIIII\n")
        reads = list(iter_reads(fq))
        assert len(reads) == 1


class TestWriteReads:
    def test_write_plain(self, tmp_path):
        out = tmp_path / "out.fastq"
        reads = [("@r1", "ACGT", "+", "IIII")]
        write_reads(reads, out)
        assert out.exists()
        assert count_reads(out) == 1

    def test_write_gzipped(self, tmp_path):
        out = tmp_path / "out.fastq.gz"
        reads = [("@r1", "ACGT", "+", "IIII")]
        write_reads(reads, out)
        assert out.exists()
        assert count_reads(out) == 1

    def test_roundtrip(self, tmp_path):
        out = tmp_path / "roundtrip.fastq"
        original = [("@r1", "ACGT", "+", "IIII"), ("@r2", "TTTT", "+", "JJJJ")]
        write_reads(original, out)
        recovered = list(iter_reads(out))
        assert recovered == original
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests_v2/test_fastq.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

Port from `nanopore_simulator/core/fastq.py` (99 lines). Rename functions for clarity:
- `count_fastq_reads` → `count_reads`
- `iter_fastq_reads` → `iter_reads`
- `write_fastq_reads` → `write_reads`

Same logic, simpler names. ~80 lines.

**Step 4: Run tests**

Run: `pytest tests_v2/test_fastq.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add nanopore_simulator_v2/fastq.py tests_v2/test_fastq.py
git commit -m "feat(v2): add FASTQ read/write utilities"
```

---

### Task 4: detection.py — File structure detection

**Files:**
- Create: `nanopore_simulator_v2/detection.py`
- Create: `tests_v2/test_detection.py`

**Step 1: Write failing tests**

```python
# tests_v2/test_detection.py
"""Tests for input directory structure detection."""

import pytest
from nanopore_simulator_v2.detection import detect_structure, find_sequencing_files


class TestDetectStructure:
    def test_singleplex(self, source_dir_singleplex):
        assert detect_structure(source_dir_singleplex) == "singleplex"

    def test_multiplex(self, source_dir_multiplex):
        assert detect_structure(source_dir_multiplex) == "multiplex"

    def test_empty_directory(self, tmp_path):
        source = tmp_path / "empty"
        source.mkdir()
        assert detect_structure(source) == "singleplex"


class TestFindSequencingFiles:
    def test_finds_fastq(self, source_dir_singleplex):
        files = find_sequencing_files(source_dir_singleplex)
        assert len(files) == 5
        assert all(f.suffix == ".fastq" for f in files)

    def test_finds_in_barcode_dirs(self, source_dir_multiplex):
        files = find_sequencing_files(source_dir_multiplex / "barcode01")
        assert len(files) == 3
```

**Step 2: Run tests — expect FAIL**

Run: `pytest tests_v2/test_detection.py -v`

**Step 3: Write implementation**

Port from `nanopore_simulator/core/detector.py` (87 lines). Convert from classmethod-based `FileStructureDetector` to module-level functions:
- `FileStructureDetector.detect_structure()` → `detect_structure(source_dir)`
- `FileStructureDetector._find_sequencing_files()` → `find_sequencing_files(directory)`
- `FileStructureDetector._find_barcode_directories()` → `find_barcode_dirs(source_dir)`
- `FileStructureDetector._is_barcode_directory()` → `is_barcode_dir(dirname)`
- Keep the same regex patterns and extension checks. ~70 lines.

**Step 4: Run tests — expect PASS**

Run: `pytest tests_v2/test_detection.py -v`

**Step 5: Commit**

```bash
git add nanopore_simulator_v2/detection.py tests_v2/test_detection.py
git commit -m "feat(v2): add file structure detection"
```

---

### Task 5: timing.py — Timing models

**Files:**
- Create: `nanopore_simulator_v2/timing.py`
- Create: `tests_v2/test_timing.py`

**Step 1: Write failing tests**

```python
# tests_v2/test_timing.py
"""Tests for timing model implementations."""

import pytest
from nanopore_simulator_v2.timing import (
    create_timing_model,
    UniformTimingModel,
    RandomTimingModel,
    PoissonTimingModel,
    AdaptiveTimingModel,
)


class TestUniform:
    def test_constant_interval(self):
        m = UniformTimingModel(base_interval=2.0)
        assert m.next_interval() == 2.0
        assert m.next_interval() == 2.0

    def test_zero_interval(self):
        m = UniformTimingModel(base_interval=0.0)
        assert m.next_interval() == 0.0


class TestRandom:
    def test_varies_around_base(self):
        m = RandomTimingModel(base_interval=1.0, random_factor=0.3)
        intervals = [m.next_interval() for _ in range(100)]
        assert min(intervals) >= 0.0
        assert any(i != 1.0 for i in intervals)

    def test_zero_factor_is_uniform(self):
        m = RandomTimingModel(base_interval=1.0, random_factor=0.0)
        assert m.next_interval() == 1.0


class TestPoisson:
    def test_positive_intervals(self):
        m = PoissonTimingModel(base_interval=1.0)
        intervals = [m.next_interval() for _ in range(100)]
        assert all(i >= 0 for i in intervals)

    def test_burst_probability(self):
        m = PoissonTimingModel(base_interval=1.0, burst_probability=0.5)
        intervals = [m.next_interval() for _ in range(100)]
        assert len(intervals) == 100


class TestAdaptive:
    def test_adapts_over_time(self):
        m = AdaptiveTimingModel(base_interval=1.0, adaptation_rate=0.5)
        intervals = [m.next_interval() for _ in range(50)]
        assert len(intervals) == 50

    def test_reset(self):
        m = AdaptiveTimingModel(base_interval=1.0)
        for _ in range(10):
            m.next_interval()
        m.reset()
        # After reset, should behave like fresh
        i = m.next_interval()
        assert i >= 0


class TestFactory:
    def test_create_uniform(self):
        m = create_timing_model("uniform", base_interval=1.0)
        assert isinstance(m, UniformTimingModel)

    def test_create_random(self):
        m = create_timing_model("random", base_interval=1.0, random_factor=0.5)
        assert isinstance(m, RandomTimingModel)

    def test_create_poisson(self):
        m = create_timing_model("poisson", base_interval=1.0)
        assert isinstance(m, PoissonTimingModel)

    def test_create_adaptive(self):
        m = create_timing_model("adaptive", base_interval=1.0)
        assert isinstance(m, AdaptiveTimingModel)

    def test_invalid_model(self):
        with pytest.raises(ValueError):
            create_timing_model("invalid", base_interval=1.0)

    def test_negative_interval(self):
        with pytest.raises(ValueError):
            create_timing_model("uniform", base_interval=-1.0)
```

**Step 2: Run tests — expect FAIL**

Run: `pytest tests_v2/test_timing.py -v`

**Step 3: Write implementation**

Copy `nanopore_simulator/core/timing.py` (188 lines) nearly verbatim. This module is already clean. ~190 lines.

**Step 4: Run tests — expect PASS**

Run: `pytest tests_v2/test_timing.py -v`

**Step 5: Commit**

```bash
git add nanopore_simulator_v2/timing.py tests_v2/test_timing.py
git commit -m "feat(v2): add timing model implementations"
```

---

## Phase 3: Data & Utility Modules

### Task 6: mocks.py — Mock community data

**Files:**
- Create: `nanopore_simulator_v2/mocks.py`
- Create: `tests_v2/test_mocks.py`

**Step 1: Write failing tests**

```python
# tests_v2/test_mocks.py
"""Tests for mock community definitions."""

import pytest
from nanopore_simulator_v2.mocks import (
    MockOrganism,
    MockCommunity,
    get_mock,
    list_mocks,
)


class TestMockOrganism:
    def test_valid(self):
        org = MockOrganism(name="E. coli", abundance=0.5)
        assert org.name == "E. coli"

    def test_invalid_abundance(self):
        with pytest.raises(ValueError):
            MockOrganism(name="E. coli", abundance=1.5)

    def test_domain_validation(self):
        org = MockOrganism(name="E. coli", abundance=0.5, domain="bacteria")
        assert org.domain == "bacteria"


class TestMockCommunity:
    def test_abundances_sum_to_one(self):
        orgs = [
            MockOrganism(name="A", abundance=0.6),
            MockOrganism(name="B", abundance=0.4),
        ]
        mc = MockCommunity(name="test", description="test", organisms=orgs)
        assert len(mc.organisms) == 2

    def test_abundances_must_sum_to_one(self):
        orgs = [
            MockOrganism(name="A", abundance=0.3),
            MockOrganism(name="B", abundance=0.3),
        ]
        with pytest.raises(ValueError, match="sum"):
            MockCommunity(name="test", description="test", organisms=orgs)


class TestGetMock:
    def test_known_mock(self):
        mc = get_mock("zymo_d6300")
        assert mc is not None
        assert len(mc.organisms) > 0

    def test_case_insensitive(self):
        mc = get_mock("ZYMO_D6300")
        assert mc is not None

    def test_alias(self):
        mc = get_mock("D6305")
        assert mc is not None

    def test_unknown(self):
        assert get_mock("nonexistent") is None


class TestListMocks:
    def test_returns_dict(self):
        mocks = list_mocks()
        assert isinstance(mocks, dict)
        assert "zymo_d6300" in mocks
        assert len(mocks) >= 10
```

**Step 2: Run tests — expect FAIL**

Run: `pytest tests_v2/test_mocks.py -v`

**Step 3: Write implementation**

Port from `nanopore_simulator/core/mocks.py` (~660 lines). Keep all mock community data intact (this is domain data, not code complexity). Simplify by removing any unused helper functions. Rename `get_mock_community` → `get_mock`.

~500 lines (mostly data definitions).

**Step 4: Run tests — expect PASS**

Run: `pytest tests_v2/test_mocks.py -v`

**Step 5: Commit**

```bash
git add nanopore_simulator_v2/mocks.py tests_v2/test_mocks.py
git commit -m "feat(v2): add mock community definitions"
```

---

### Task 7: adapters.py — Simplified pipeline validation

**Files:**
- Create: `nanopore_simulator_v2/adapters.py`
- Create: `tests_v2/test_adapters.py`

**Step 1: Write failing tests**

```python
# tests_v2/test_adapters.py
"""Tests for pipeline adapter validation."""

import pytest
from pathlib import Path
from nanopore_simulator_v2.adapters import (
    ADAPTERS,
    validate_output,
    list_adapters,
    get_adapter_info,
)


class TestAdapters:
    def test_nanometa_exists(self):
        assert "nanometa" in ADAPTERS

    def test_kraken_exists(self):
        assert "kraken" in ADAPTERS

    def test_alias_nanometanf(self):
        assert "nanometanf" in ADAPTERS

    def test_list_adapters(self):
        adapters = list_adapters()
        assert "nanometa" in adapters
        assert "kraken" in adapters

    def test_get_adapter_info(self):
        info = get_adapter_info("nanometa")
        assert "description" in info


class TestValidateOutput:
    def test_valid_nanometa_structure(self, tmp_path):
        # Create expected barcode structure
        bc = tmp_path / "barcode01"
        bc.mkdir()
        (bc / "reads.fastq").write_text("@r\nA\n+\nI\n")
        issues = validate_output(tmp_path, "nanometa")
        assert len(issues) == 0

    def test_empty_dir_has_issues(self, tmp_path):
        issues = validate_output(tmp_path, "nanometa")
        assert len(issues) > 0

    def test_unknown_adapter(self, tmp_path):
        with pytest.raises(KeyError):
            validate_output(tmp_path, "nonexistent")

    def test_kraken_accepts_flat_fastq(self, tmp_path):
        (tmp_path / "reads.fastq").write_text("@r\nA\n+\nI\n")
        issues = validate_output(tmp_path, "kraken")
        assert len(issues) == 0
```

**Step 2: Run tests — expect FAIL**

Run: `pytest tests_v2/test_adapters.py -v`

**Step 3: Write implementation**

Replace the 326-line `PipelineAdapter` ABC / `GenericAdapter` / `AdapterManager` with a simple dict registry and validation functions.

```python
# nanopore_simulator_v2/adapters.py
"""Pipeline validation — dict-based, no ABC."""

from pathlib import Path
from typing import Any

ADAPTERS: dict[str, dict[str, Any]] = {
    "nanometa": {
        "description": "Nanometa Live real-time taxonomic analysis",
        "required_structure": "multiplex",
        "barcode_pattern": "barcode*",
        "file_patterns": ["*.fastq", "*.fastq.gz"],
    },
    "kraken": {
        "description": "Kraken2/KrakenUniq taxonomic classification",
        "file_patterns": ["*.fastq", "*.fastq.gz", "*.fq", "*.fq.gz"],
    },
}
# Backward-compatible alias
ADAPTERS["nanometanf"] = ADAPTERS["nanometa"]


def validate_output(target: Path, adapter_name: str) -> list[str]:
    """Validate target directory against adapter requirements.
    Returns list of issue descriptions. Empty list means valid.
    """
    spec = ADAPTERS[adapter_name]  # raises KeyError if unknown
    issues = []
    # Check file patterns
    # Check required structure
    # ...
    return issues


def list_adapters() -> dict[str, str]:
    """Return {name: description} for all adapters."""
    ...


def get_adapter_info(name: str) -> dict[str, Any]:
    """Return full spec for an adapter."""
    ...
```

~100 lines total. Port validation logic from `GenericAdapter.validate_structure()`.

**Step 4: Run tests — expect PASS**

Run: `pytest tests_v2/test_adapters.py -v`

**Step 5: Commit**

```bash
git add nanopore_simulator_v2/adapters.py tests_v2/test_adapters.py
git commit -m "feat(v2): add simplified pipeline validation"
```

---

### Task 8: deps.py — Dependency checking

**Files:**
- Create: `nanopore_simulator_v2/deps.py`
- Create: `tests_v2/test_deps.py`

**Step 1: Write failing tests**

```python
# tests_v2/test_deps.py
"""Tests for dependency checking."""

import pytest
from nanopore_simulator_v2.deps import (
    DependencyStatus,
    check_all_dependencies,
    check_preflight,
    get_install_hint,
)


class TestGetInstallHint:
    def test_known_dependency(self):
        hint = get_install_hint("badread")
        assert "install" in hint.lower() or "pip" in hint.lower() or "conda" in hint.lower()

    def test_unknown_dependency(self):
        hint = get_install_hint("nonexistent_tool_xyz")
        assert isinstance(hint, str)


class TestCheckAllDependencies:
    def test_returns_list(self):
        deps = check_all_dependencies()
        assert isinstance(deps, list)
        assert all(isinstance(d, DependencyStatus) for d in deps)

    def test_builtin_always_available(self):
        deps = check_all_dependencies()
        builtin = [d for d in deps if d.name == "builtin"]
        assert len(builtin) == 1
        assert builtin[0].available is True


class TestCheckPreflight:
    def test_replay_no_issues(self):
        issues = check_preflight(operation="copy")
        assert isinstance(issues, list)

    def test_generate_builtin_no_issues(self):
        issues = check_preflight(operation="generate", generator_backend="builtin")
        assert isinstance(issues, list)
```

**Step 2: Run tests — expect FAIL**

Run: `pytest tests_v2/test_deps.py -v`

**Step 3: Write implementation**

Port from `nanopore_simulator/core/deps.py` (202 lines). Keep `DependencyStatus`, `INSTALL_HINTS`, `check_all_dependencies()`, `check_preflight()`, `get_install_hint()`. Adapt imports to use `nanopore_simulator_v2.generators.detect_available_backends`.

~180 lines.

**Step 4: Run tests — expect PASS**

Run: `pytest tests_v2/test_deps.py -v`

**Step 5: Commit**

```bash
git add nanopore_simulator_v2/deps.py tests_v2/test_deps.py
git commit -m "feat(v2): add dependency checking"
```

---

### Task 9: profiles.py — Configuration profiles

**Files:**
- Create: `nanopore_simulator_v2/profiles.py`
- Create: `tests_v2/test_profiles.py`

**Step 1: Write failing tests**

```python
# tests_v2/test_profiles.py
"""Tests for configuration profiles."""

import pytest
from nanopore_simulator_v2.profiles import (
    get_profile,
    list_profiles,
    apply_profile,
    get_recommendations,
)


class TestGetProfile:
    def test_known_profile(self):
        p = get_profile("development")
        assert p is not None
        assert p["timing_model"] == "uniform"

    def test_unknown_profile(self):
        assert get_profile("nonexistent") is None

    def test_all_builtin_profiles(self):
        for name in ["development", "steady", "bursty", "high_throughput",
                      "gradual_drift", "generate_test", "generate_standard"]:
            assert get_profile(name) is not None


class TestListProfiles:
    def test_returns_dict(self):
        profiles = list_profiles()
        assert isinstance(profiles, dict)
        assert "development" in profiles

    def test_has_descriptions(self):
        profiles = list_profiles()
        assert all(isinstance(v, str) for v in profiles.values())


class TestApplyProfile:
    def test_returns_params(self):
        params = apply_profile("development")
        assert "timing_model" in params
        assert "batch_size" in params

    def test_overrides(self):
        params = apply_profile("development", overrides={"interval": 10.0})
        assert params["interval"] == 10.0

    def test_unknown_profile(self):
        with pytest.raises(ValueError, match="Unknown profile"):
            apply_profile("nonexistent")


class TestGetRecommendations:
    def test_small_file_count(self):
        recs = get_recommendations(file_count=5)
        assert isinstance(recs, list)
        assert len(recs) > 0

    def test_large_file_count(self):
        recs = get_recommendations(file_count=10000)
        assert isinstance(recs, list)
```

**Step 2: Run tests — expect FAIL**

Run: `pytest tests_v2/test_profiles.py -v`

**Step 3: Write implementation**

Simplify from `nanopore_simulator/core/profiles.py` (347 lines). Remove `ProfileManager` class and `ProfileDefinition` dataclass. Use plain dicts:

```python
PROFILES = {
    "development": {
        "description": "Quick testing with uniform timing",
        "timing_model": "uniform",
        "batch_size": 1,
        "parallel": False,
    },
    # ... etc
}

def get_profile(name: str) -> dict | None: ...
def list_profiles() -> dict[str, str]: ...
def apply_profile(name: str, overrides: dict | None = None) -> dict: ...
def get_recommendations(file_count: int) -> list[str]: ...
```

~200 lines (mostly profile data definitions).

**Step 4: Run tests — expect PASS**

Run: `pytest tests_v2/test_profiles.py -v`

**Step 5: Commit**

```bash
git add nanopore_simulator_v2/profiles.py tests_v2/test_profiles.py
git commit -m "feat(v2): add configuration profiles"
```

---

## Phase 4: Core Processing Modules

### Task 10: generators.py — Read generation backends

**Files:**
- Create: `nanopore_simulator_v2/generators.py`
- Create: `tests_v2/test_generators.py`

**Step 1: Write failing tests**

```python
# tests_v2/test_generators.py
"""Tests for read generation backends."""

import pytest
from pathlib import Path
from nanopore_simulator_v2.generators import (
    ReadGenerator,
    BuiltinGenerator,
    SubprocessGenerator,
    create_generator,
    detect_available_backends,
    parse_fasta,
    GeneratorConfig,
)


class TestGeneratorConfig:
    def test_defaults(self):
        cfg = GeneratorConfig()
        assert cfg.mean_length == 5000
        assert cfg.std_length == 2000
        assert cfg.min_length == 200
        assert cfg.mean_quality == 20.0
        assert cfg.reads_per_file == 100

    def test_invalid_mean_length(self):
        with pytest.raises(ValueError):
            GeneratorConfig(mean_length=-1)


class TestParseFasta:
    def test_plain_fasta(self, sample_fasta):
        records = list(parse_fasta(sample_fasta))
        assert len(records) == 2
        assert records[0][0] == "chr1"
        assert records[0][1] == "ACGTACGTACGTACGT"

    def test_gzipped_fasta(self, tmp_path):
        import gzip
        fa = tmp_path / "genome.fa.gz"
        with gzip.open(fa, "wt") as f:
            f.write(">seq1\nACGT\n")
        records = list(parse_fasta(fa))
        assert len(records) == 1


class TestBuiltinGenerator:
    def test_is_available(self):
        assert BuiltinGenerator.is_available() is True

    def test_generate_reads(self, sample_fasta, tmp_path):
        cfg = GeneratorConfig(mean_length=10, std_length=2, min_length=4)
        gen = BuiltinGenerator(cfg)
        output = gen.generate_reads(
            genome=sample_fasta,
            output_dir=tmp_path / "out",
            num_reads=5,
        )
        assert output.exists()
        assert output.stat().st_size > 0

    def test_generate_reads_in_memory(self, sample_fasta):
        cfg = GeneratorConfig(mean_length=10, std_length=2, min_length=4)
        gen = BuiltinGenerator(cfg)
        reads = gen.generate_reads_in_memory(genome=sample_fasta, num_reads=3)
        assert len(reads) == 3
        assert all(len(r) == 4 for r in reads)  # 4-tuple


class TestFactory:
    def test_create_builtin(self):
        gen = create_generator("builtin")
        assert isinstance(gen, BuiltinGenerator)

    def test_create_auto(self):
        gen = create_generator("auto")
        assert isinstance(gen, ReadGenerator)

    def test_invalid_backend(self):
        with pytest.raises(ValueError):
            create_generator("invalid")


class TestDetectBackends:
    def test_returns_dict(self):
        backends = detect_available_backends()
        assert isinstance(backends, dict)
        assert "builtin" in backends
        assert backends["builtin"] is True
```

**Step 2: Run tests — expect FAIL**

Run: `pytest tests_v2/test_generators.py -v`

**Step 3: Write implementation**

Port from `nanopore_simulator/core/generators.py` (707 lines). Key simplifications:
- Rename `ReadGeneratorConfig` → `GeneratorConfig`
- Merge `BadreadGenerator` and `NanoSimGenerator` into `SubprocessGenerator`
- `SubprocessGenerator.__init__(backend, command_builder)` — parameterized by backend
- Keep `BuiltinGenerator` with its numpy optimizations
- Keep `parse_fasta()`, `detect_available_backends()`, `create_generator()`
- Remove `GenomeInput` dataclass (manifest handles this now)

~400 lines (vs 707).

**Step 4: Run tests — expect PASS**

Run: `pytest tests_v2/test_generators.py -v`

**Step 5: Commit**

```bash
git add nanopore_simulator_v2/generators.py tests_v2/test_generators.py
git commit -m "feat(v2): add read generation backends with unified subprocess wrapper"
```

---

### Task 11: species.py — Species resolution

**Files:**
- Create: `nanopore_simulator_v2/species.py`
- Create: `tests_v2/test_species.py`

**Step 1: Write failing tests**

```python
# tests_v2/test_species.py
"""Tests for species name resolution and genome downloads."""

import pytest
from unittest.mock import patch, MagicMock
from nanopore_simulator_v2.species import (
    GenomeRef,
    GenomeCache,
    ResolutionCache,
    resolve_species,
    resolve_taxid,
    download_genome,
)


class TestGenomeRef:
    def test_valid_ref(self):
        ref = GenomeRef(name="E. coli", accession="GCF_000005845.2", source="ncbi")
        assert ref.name == "E. coli"

    def test_invalid_source(self):
        with pytest.raises(ValueError):
            GenomeRef(name="E. coli", accession="GCF_000005845.2", source="invalid")


class TestGenomeCache:
    def test_cache_dir_created(self, tmp_path):
        cache = GenomeCache(cache_dir=tmp_path / "genomes")
        assert cache.cache_dir.exists()

    def test_not_cached(self, tmp_path):
        cache = GenomeCache(cache_dir=tmp_path / "genomes")
        assert not cache.is_cached("GCF_000005845.2")

    def test_get_cached_path(self, tmp_path):
        cache = GenomeCache(cache_dir=tmp_path / "genomes")
        path = cache.get_cached_path("GCF_000005845.2")
        assert "GCF_000005845.2" in str(path)


class TestResolutionCache:
    def test_put_get(self, tmp_path):
        cache = ResolutionCache(cache_file=tmp_path / "cache.json")
        ref = GenomeRef(name="E. coli", accession="GCF_000005845.2", source="ncbi")
        cache.put("Escherichia coli", ref)
        result = cache.get("Escherichia coli")
        assert result is not None
        assert result.accession == "GCF_000005845.2"

    def test_get_missing(self, tmp_path):
        cache = ResolutionCache(cache_file=tmp_path / "cache.json")
        assert cache.get("nonexistent") is None


class TestResolveSpecies:
    @patch("nanopore_simulator_v2.species._gtdb_lookup")
    def test_resolves_bacteria(self, mock_gtdb):
        mock_gtdb.return_value = GenomeRef(
            name="E. coli",
            accession="GCF_000005845.2",
            source="gtdb",
            domain="bacteria",
        )
        ref = resolve_species("Escherichia coli")
        assert ref.accession == "GCF_000005845.2"
```

**Step 2: Run tests — expect FAIL**

Run: `pytest tests_v2/test_species.py -v`

**Step 3: Write implementation**

Port from `nanopore_simulator/core/species.py` (~855 lines). This module is domain-specific and mostly self-contained. Keep the resolver implementations but simplify the class hierarchy:
- Keep `GenomeRef`, `GenomeCache`, `ResolutionCache`
- Flatten resolver classes into module-level functions: `resolve_species()`, `resolve_taxid()`, `download_genome()`
- Keep GTDB API and NCBI datasets CLI integration
- Keep caching strategy

~700 lines (trimmed from 855).

**Step 4: Run tests — expect PASS**

Run: `pytest tests_v2/test_species.py -v`

**Step 5: Commit**

```bash
git add nanopore_simulator_v2/species.py tests_v2/test_species.py
git commit -m "feat(v2): add species resolution and genome downloads"
```

---

### Task 12: monitoring.py — Progress monitoring

**Files:**
- Create: `nanopore_simulator_v2/monitoring.py`
- Create: `tests_v2/test_monitoring.py`

**Step 1: Write failing tests**

```python
# tests_v2/test_monitoring.py
"""Tests for progress monitoring."""

import pytest
from nanopore_simulator_v2.monitoring import (
    ProgressMonitor,
    create_monitor,
)


class TestProgressMonitor:
    def test_create_basic(self):
        monitor = create_monitor(monitor_type="basic", total_files=10)
        assert monitor is not None

    def test_update(self):
        monitor = create_monitor(monitor_type="basic", total_files=5)
        monitor.start()
        monitor.update(files_done=1, bytes_processed=1024)
        assert monitor.files_processed == 1
        monitor.stop()

    def test_progress_percentage(self):
        monitor = create_monitor(monitor_type="basic", total_files=10)
        monitor.start()
        monitor.update(files_done=5)
        assert monitor.progress_percentage == pytest.approx(50.0)
        monitor.stop()

    def test_eta(self):
        monitor = create_monitor(monitor_type="basic", total_files=10)
        monitor.start()
        for i in range(5):
            monitor.update(files_done=1)
        eta = monitor.estimate_eta()
        assert eta is None or eta >= 0
        monitor.stop()

    def test_pause_resume(self):
        monitor = create_monitor(monitor_type="basic", total_files=10)
        monitor.start()
        monitor.pause()
        assert monitor.is_paused
        monitor.resume()
        assert not monitor.is_paused
        monitor.stop()

    def test_enhanced_monitor(self):
        monitor = create_monitor(monitor_type="enhanced", total_files=10)
        assert monitor is not None

    def test_none_monitor(self):
        monitor = create_monitor(monitor_type="none", total_files=10)
        # Should work but do nothing
        monitor.start()
        monitor.update(files_done=1)
        monitor.stop()
```

**Step 2: Run tests — expect FAIL**

Run: `pytest tests_v2/test_monitoring.py -v`

**Step 3: Write implementation**

Port from `nanopore_simulator/core/monitoring.py` (996 lines). Simplifications:
- Remove unused `SimulationMetrics` fields (keep ~15 of 30+)
- Simplify `estimate_eta()` from 79 lines to ~30 lines
- Keep `ProgressMonitor` class with thread-safe operations
- Keep resource tracking (psutil optional)
- Keep pause/resume with signal handling
- Add `NullMonitor` for `monitor_type="none"`
- `create_monitor()` factory

~600 lines (vs 996).

**Step 4: Run tests — expect PASS**

Run: `pytest tests_v2/test_monitoring.py -v`

**Step 5: Commit**

```bash
git add nanopore_simulator_v2/monitoring.py tests_v2/test_monitoring.py
git commit -m "feat(v2): add progress monitoring with resource tracking"
```

---

## Phase 5: Orchestration (the core rewrite)

### Task 13: manifest.py — Build file manifests

**Files:**
- Create: `nanopore_simulator_v2/manifest.py`
- Create: `tests_v2/test_manifest.py`

This is the first of three modules extracted from the god object. It handles **planning** — given a config, produce a list of file operations to execute.

**Step 1: Write failing tests**

```python
# tests_v2/test_manifest.py
"""Tests for manifest building (plan phase)."""

import pytest
from pathlib import Path
from nanopore_simulator_v2.manifest import (
    FileEntry,
    build_replay_manifest,
    build_generate_manifest,
)
from nanopore_simulator_v2.config import ReplayConfig, GenerateConfig


class TestFileEntry:
    def test_replay_entry(self):
        entry = FileEntry(
            source=Path("/source/reads.fastq"),
            target=Path("/target/reads.fastq"),
            operation="copy",
            batch=0,
        )
        assert entry.genome is None
        assert entry.read_count is None

    def test_generate_entry(self):
        entry = FileEntry(
            source=None,
            target=Path("/target/reads_0.fastq"),
            operation="generate",
            genome=Path("/genomes/ecoli.fa"),
            read_count=100,
            batch=0,
        )
        assert entry.source is None
        assert entry.genome is not None


class TestBuildReplayManifest:
    def test_singleplex(self, source_dir_singleplex, tmp_path):
        config = ReplayConfig(
            source_dir=source_dir_singleplex,
            target_dir=tmp_path / "target",
        )
        manifest = build_replay_manifest(config)
        assert len(manifest) == 5
        assert all(e.operation == "copy" for e in manifest)
        assert all(e.source is not None for e in manifest)

    def test_multiplex(self, source_dir_multiplex, tmp_path):
        config = ReplayConfig(
            source_dir=source_dir_multiplex,
            target_dir=tmp_path / "target",
        )
        manifest = build_replay_manifest(config)
        assert len(manifest) == 6  # 3 files x 2 barcodes
        # Target paths should preserve barcode structure
        targets = [str(e.target) for e in manifest]
        assert any("barcode01" in t for t in targets)
        assert any("barcode02" in t for t in targets)

    def test_link_operation(self, source_dir_singleplex, tmp_path):
        config = ReplayConfig(
            source_dir=source_dir_singleplex,
            target_dir=tmp_path / "target",
            operation="link",
        )
        manifest = build_replay_manifest(config)
        assert all(e.operation == "link" for e in manifest)

    def test_batching(self, source_dir_singleplex, tmp_path):
        config = ReplayConfig(
            source_dir=source_dir_singleplex,
            target_dir=tmp_path / "target",
            batch_size=2,
        )
        manifest = build_replay_manifest(config)
        batches = set(e.batch for e in manifest)
        assert len(batches) == 3  # 5 files / batch_size 2 = 3 batches

    def test_forced_singleplex(self, source_dir_multiplex, tmp_path):
        config = ReplayConfig(
            source_dir=source_dir_multiplex,
            target_dir=tmp_path / "target",
            structure="singleplex",
        )
        manifest = build_replay_manifest(config)
        # Should still find all files but flatten structure
        assert len(manifest) == 6

    def test_empty_source(self, tmp_path):
        source = tmp_path / "empty"
        source.mkdir()
        config = ReplayConfig(
            source_dir=source,
            target_dir=tmp_path / "target",
        )
        manifest = build_replay_manifest(config)
        assert len(manifest) == 0


class TestBuildGenerateManifest:
    def test_single_genome(self, sample_fasta, tmp_path):
        config = GenerateConfig(
            target_dir=tmp_path / "out",
            genome_inputs=[sample_fasta],
            read_count=500,
            reads_per_file=100,
        )
        manifest = build_generate_manifest(config)
        assert len(manifest) == 5  # 500 / 100 = 5 files
        assert all(e.operation == "generate" for e in manifest)
        total_reads = sum(e.read_count for e in manifest)
        assert total_reads == 500

    def test_multiple_genomes_equal(self, tmp_path):
        g1 = tmp_path / "g1.fa"
        g2 = tmp_path / "g2.fa"
        g1.write_text(">s\nACGTACGTACGTACGT\n")
        g2.write_text(">s\nTTTTAAAACCCCGGGG\n")
        config = GenerateConfig(
            target_dir=tmp_path / "out",
            genome_inputs=[g1, g2],
            read_count=1000,
            reads_per_file=100,
        )
        manifest = build_generate_manifest(config)
        # 1000 reads / 100 per file = 10 files, split across 2 genomes
        total_reads = sum(e.read_count for e in manifest)
        assert total_reads == 1000

    def test_abundance_weighting(self, tmp_path):
        g1 = tmp_path / "g1.fa"
        g2 = tmp_path / "g2.fa"
        g1.write_text(">s\nACGTACGTACGTACGT\n")
        g2.write_text(">s\nTTTTAAAACCCCGGGG\n")
        config = GenerateConfig(
            target_dir=tmp_path / "out",
            genome_inputs=[g1, g2],
            read_count=1000,
            reads_per_file=100,
            abundances=[0.9, 0.1],
        )
        manifest = build_generate_manifest(config)
        g1_reads = sum(e.read_count for e in manifest if e.genome == g1)
        g2_reads = sum(e.read_count for e in manifest if e.genome == g2)
        assert g1_reads == 900
        assert g2_reads == 100

    def test_batching(self, sample_fasta, tmp_path):
        config = GenerateConfig(
            target_dir=tmp_path / "out",
            genome_inputs=[sample_fasta],
            read_count=500,
            reads_per_file=100,
            batch_size=2,
        )
        manifest = build_generate_manifest(config)
        batches = set(e.batch for e in manifest)
        assert len(batches) == 3  # 5 files / batch 2 = 3 batches
```

**Step 2: Run tests — expect FAIL**

Run: `pytest tests_v2/test_manifest.py -v`

**Step 3: Write implementation**

Extract from `nanopore_simulator/core/simulator.py`:
- `_create_manifest()` (line ~400) → `build_replay_manifest()`
- `_create_singleplex_manifest()` → integrated
- `_create_multiplex_manifest()` → integrated
- `_create_generate_manifest()` (line ~537) → `build_generate_manifest()`
- `_distribute_reads()` → `_distribute_reads()` (keep as internal helper)
- `_create_rechunk_plan()` → integrated into `build_replay_manifest()` when `reads_per_output` is set

Key data structure:
```python
@dataclass
class FileEntry:
    source: Path | None = None
    target: Path = field(default_factory=Path)
    operation: str = "copy"
    genome: Path | None = None
    read_count: int | None = None
    batch: int = 0
```

Dependencies: `config`, `detection`, `fastq` (for rechunking read counting)

~300 lines.

**Step 4: Run tests — expect PASS**

Run: `pytest tests_v2/test_manifest.py -v`

**Step 5: Commit**

```bash
git add nanopore_simulator_v2/manifest.py tests_v2/test_manifest.py
git commit -m "feat(v2): add manifest building for replay and generate modes"
```

---

### Task 14: executor.py — File execution

**Files:**
- Create: `nanopore_simulator_v2/executor.py`
- Create: `tests_v2/test_executor.py`

**Step 1: Write failing tests**

```python
# tests_v2/test_executor.py
"""Tests for file execution (do phase)."""

import pytest
from pathlib import Path
from nanopore_simulator_v2.executor import execute_entry
from nanopore_simulator_v2.manifest import FileEntry
from nanopore_simulator_v2.generators import BuiltinGenerator, GeneratorConfig


class TestCopyFile:
    def test_copy(self, tmp_path):
        source = tmp_path / "source" / "reads.fastq"
        source.parent.mkdir()
        source.write_text("@r1\nACGT\n+\nIIII\n")
        target = tmp_path / "target" / "reads.fastq"

        entry = FileEntry(
            source=source,
            target=target,
            operation="copy",
            batch=0,
        )
        result = execute_entry(entry)
        assert result.exists()
        assert result.read_text() == source.read_text()

    def test_copy_creates_parent_dirs(self, tmp_path):
        source = tmp_path / "reads.fastq"
        source.write_text("@r1\nACGT\n+\nIIII\n")
        target = tmp_path / "deep" / "nested" / "reads.fastq"

        entry = FileEntry(source=source, target=target, operation="copy", batch=0)
        result = execute_entry(entry)
        assert result.exists()


class TestLinkFile:
    def test_link(self, tmp_path):
        source = tmp_path / "reads.fastq"
        source.write_text("@r1\nACGT\n+\nIIII\n")
        target = tmp_path / "target" / "reads.fastq"

        entry = FileEntry(source=source, target=target, operation="link", batch=0)
        result = execute_entry(entry)
        assert result.exists()
        assert result.is_symlink()
        assert result.read_text() == source.read_text()


class TestGenerateFile:
    def test_generate(self, sample_fasta, tmp_path):
        entry = FileEntry(
            source=None,
            target=tmp_path / "out" / "reads_0.fastq",
            operation="generate",
            genome=sample_fasta,
            read_count=10,
            batch=0,
        )
        cfg = GeneratorConfig(mean_length=10, std_length=2, min_length=4)
        gen = BuiltinGenerator(cfg)
        result = execute_entry(entry, generator=gen)
        assert result.exists()
        assert result.stat().st_size > 0

    def test_generate_requires_generator(self, sample_fasta, tmp_path):
        entry = FileEntry(
            source=None,
            target=tmp_path / "reads.fastq",
            operation="generate",
            genome=sample_fasta,
            read_count=10,
            batch=0,
        )
        with pytest.raises(ValueError, match="generator"):
            execute_entry(entry)
```

**Step 2: Run tests — expect FAIL**

Run: `pytest tests_v2/test_executor.py -v`

**Step 3: Write implementation**

Extract from `nanopore_simulator/core/simulator.py`:
- `_process_file()` / `_copy_file()` / `_create_symlink()` → `_copy_file()`, `_link_file()`
- `_process_generate()` → `_generate_file()`

```python
# nanopore_simulator_v2/executor.py
"""Execute one file operation (do phase)."""

import shutil
from pathlib import Path
from .manifest import FileEntry
from .generators import ReadGenerator


def execute_entry(entry: FileEntry, generator: ReadGenerator | None = None) -> Path:
    """Produce one file. Returns the path written."""
    entry.target.parent.mkdir(parents=True, exist_ok=True)
    if entry.operation == "copy":
        return _copy_file(entry.source, entry.target)
    elif entry.operation == "link":
        return _link_file(entry.source, entry.target)
    elif entry.operation == "generate":
        if generator is None:
            raise ValueError("generator required for generate operation")
        return _generate_file(entry, generator)
    else:
        raise ValueError(f"Unknown operation: {entry.operation}")


def _copy_file(source: Path, target: Path) -> Path:
    shutil.copy2(source, target)
    return target


def _link_file(source: Path, target: Path) -> Path:
    target.symlink_to(source.resolve())
    return target


def _generate_file(entry: FileEntry, generator: ReadGenerator) -> Path:
    output_dir = entry.target.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    return generator.generate_reads(
        genome=entry.genome,
        output_dir=output_dir,
        num_reads=entry.read_count,
    )
```

~80 lines.

**Step 4: Run tests — expect PASS**

Run: `pytest tests_v2/test_executor.py -v`

**Step 5: Commit**

```bash
git add nanopore_simulator_v2/executor.py tests_v2/test_executor.py
git commit -m "feat(v2): add file executor for copy/link/generate operations"
```

---

### Task 15: runner.py — Orchestration loop

**Files:**
- Create: `nanopore_simulator_v2/runner.py`
- Create: `tests_v2/test_runner.py`

**Step 1: Write failing tests**

```python
# tests_v2/test_runner.py
"""Tests for the orchestration runner."""

import pytest
from pathlib import Path
from nanopore_simulator_v2.runner import run_replay, run_generate
from nanopore_simulator_v2.config import ReplayConfig, GenerateConfig


class TestRunReplay:
    def test_copies_files(self, source_dir_singleplex, tmp_path):
        target = tmp_path / "target"
        config = ReplayConfig(
            source_dir=source_dir_singleplex,
            target_dir=target,
            interval=0.0,
            monitor_type="none",
        )
        run_replay(config)
        assert target.exists()
        output_files = list(target.glob("*.fastq"))
        assert len(output_files) == 5

    def test_links_files(self, source_dir_singleplex, tmp_path):
        target = tmp_path / "target"
        config = ReplayConfig(
            source_dir=source_dir_singleplex,
            target_dir=target,
            operation="link",
            interval=0.0,
            monitor_type="none",
        )
        run_replay(config)
        output_files = list(target.glob("*.fastq"))
        assert len(output_files) == 5
        assert all(f.is_symlink() for f in output_files)

    def test_multiplex_structure(self, source_dir_multiplex, tmp_path):
        target = tmp_path / "target"
        config = ReplayConfig(
            source_dir=source_dir_multiplex,
            target_dir=target,
            interval=0.0,
            monitor_type="none",
        )
        run_replay(config)
        assert (target / "barcode01").exists()
        assert (target / "barcode02").exists()

    def test_parallel(self, source_dir_singleplex, tmp_path):
        target = tmp_path / "target"
        config = ReplayConfig(
            source_dir=source_dir_singleplex,
            target_dir=target,
            interval=0.0,
            parallel=True,
            workers=2,
            monitor_type="none",
        )
        run_replay(config)
        output_files = list(target.glob("*.fastq"))
        assert len(output_files) == 5

    def test_empty_source(self, tmp_path):
        source = tmp_path / "empty"
        source.mkdir()
        target = tmp_path / "target"
        config = ReplayConfig(
            source_dir=source,
            target_dir=target,
            interval=0.0,
            monitor_type="none",
        )
        run_replay(config)
        # Should complete without error


class TestRunGenerate:
    def test_generates_files(self, sample_fasta, tmp_path):
        target = tmp_path / "target"
        config = GenerateConfig(
            target_dir=target,
            genome_inputs=[sample_fasta],
            read_count=50,
            reads_per_file=10,
            interval=0.0,
            generator_backend="builtin",
            monitor_type="none",
            mean_length=10,
            std_length=2,
        )
        run_generate(config)
        assert target.exists()
        output_files = list(target.rglob("*.fastq*"))
        assert len(output_files) == 5  # 50 / 10

    def test_parallel_generate(self, sample_fasta, tmp_path):
        target = tmp_path / "target"
        config = GenerateConfig(
            target_dir=target,
            genome_inputs=[sample_fasta],
            read_count=50,
            reads_per_file=10,
            interval=0.0,
            generator_backend="builtin",
            parallel=True,
            workers=2,
            monitor_type="none",
            mean_length=10,
            std_length=2,
        )
        run_generate(config)
        output_files = list(target.rglob("*.fastq*"))
        assert len(output_files) == 5
```

**Step 2: Run tests — expect FAIL**

Run: `pytest tests_v2/test_runner.py -v`

**Step 3: Write implementation**

This is the core orchestrator — the ~150-line module that replaces the 1,405-line simulator.py.

```python
# nanopore_simulator_v2/runner.py
"""Orchestration: plan -> execute -> monitor loop."""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from pathlib import Path

from .config import ReplayConfig, GenerateConfig
from .manifest import build_replay_manifest, build_generate_manifest, FileEntry
from .executor import execute_entry
from .timing import create_timing_model
from .monitoring import create_monitor
from .generators import create_generator, GeneratorConfig

logger = logging.getLogger(__name__)


def run_replay(config: ReplayConfig) -> None:
    """Execute a replay simulation."""
    manifest = build_replay_manifest(config)
    if not manifest:
        logger.info("No files found in source directory")
        return
    _execute_manifest(manifest, config)


def run_generate(config: GenerateConfig) -> None:
    """Execute a generate simulation."""
    manifest = build_generate_manifest(config)
    gen_config = GeneratorConfig(
        mean_length=config.mean_length,
        std_length=config.std_length,
        min_length=config.min_length,
        mean_quality=config.mean_quality,
        std_quality=config.std_quality,
        reads_per_file=config.reads_per_file,
        output_format=config.output_format,
    )
    generator = create_generator(config.generator_backend, gen_config)
    _execute_manifest(manifest, config, generator)


def _execute_manifest(manifest, config, generator=None):
    """Core execution loop: process entries with timing and monitoring."""
    timing = create_timing_model(
        config.timing_model,
        base_interval=config.interval,
        **(config.timing_params or {}),
    )
    monitor = create_monitor(
        monitor_type=config.monitor_type,
        total_files=len(manifest),
    )
    monitor.start()
    try:
        batches = _group_by_batch(manifest)
        for batch in batches:
            if config.parallel:
                _execute_batch_parallel(batch, generator, config.workers)
            else:
                for entry in batch:
                    result = execute_entry(entry, generator)
                    monitor.update(files_done=1, bytes_processed=result.stat().st_size)
            interval = timing.next_interval()
            if interval > 0:
                time.sleep(interval)
    finally:
        monitor.stop()


def _group_by_batch(manifest: list[FileEntry]) -> list[list[FileEntry]]:
    """Group entries by batch number."""
    batches: dict[int, list[FileEntry]] = {}
    for entry in manifest:
        batches.setdefault(entry.batch, []).append(entry)
    return [batches[k] for k in sorted(batches)]


def _execute_batch_parallel(batch, generator, workers):
    """Execute a batch of entries in parallel."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(execute_entry, entry, generator) for entry in batch]
        for f in futures:
            f.result()  # raises on error
```

~150 lines. Handles both modes, parallel and sequential, with timing and monitoring.

**Step 4: Run tests — expect PASS**

Run: `pytest tests_v2/test_runner.py -v`

**Step 5: Commit**

```bash
git add nanopore_simulator_v2/runner.py tests_v2/test_runner.py
git commit -m "feat(v2): add orchestration runner with plan-execute-monitor loop"
```

---

## Phase 6: CLI

### Task 16: cli.py — Command-line interface

**Files:**
- Create: `nanopore_simulator_v2/cli.py`
- Create: `tests_v2/test_cli.py`

**Step 1: Write failing tests**

```python
# tests_v2/test_cli.py
"""Tests for CLI interface."""

import pytest
from typer.testing import CliRunner
from nanopore_simulator_v2.cli import app

runner = CliRunner()


class TestReplayCommand:
    def test_help(self):
        result = runner.invoke(app, ["replay", "--help"])
        assert result.exit_code == 0
        assert "source" in result.output.lower()
        assert "target" in result.output.lower()

    def test_basic_replay(self, source_dir_singleplex, tmp_path):
        target = tmp_path / "target"
        result = runner.invoke(app, [
            "replay",
            "--source", str(source_dir_singleplex),
            "--target", str(target),
            "--interval", "0",
        ])
        assert result.exit_code == 0

    def test_replay_with_profile(self, source_dir_singleplex, tmp_path):
        target = tmp_path / "target"
        result = runner.invoke(app, [
            "replay",
            "--source", str(source_dir_singleplex),
            "--target", str(target),
            "--profile", "development",
            "--interval", "0",
        ])
        assert result.exit_code == 0


class TestGenerateCommand:
    def test_help(self):
        result = runner.invoke(app, ["generate", "--help"])
        assert result.exit_code == 0
        assert "target" in result.output.lower()

    def test_basic_generate(self, sample_fasta, tmp_path):
        target = tmp_path / "target"
        result = runner.invoke(app, [
            "generate",
            "--genomes", str(sample_fasta),
            "--target", str(target),
            "--read-count", "10",
            "--interval", "0",
            "--backend", "builtin",
        ])
        assert result.exit_code == 0


class TestListCommands:
    def test_list_profiles(self):
        result = runner.invoke(app, ["list-profiles"])
        assert result.exit_code == 0
        assert "development" in result.output

    def test_list_adapters(self):
        result = runner.invoke(app, ["list-adapters"])
        assert result.exit_code == 0
        assert "nanometa" in result.output

    def test_list_generators(self):
        result = runner.invoke(app, ["list-generators"])
        assert result.exit_code == 0
        assert "builtin" in result.output

    def test_list_mocks(self):
        result = runner.invoke(app, ["list-mocks"])
        assert result.exit_code == 0
        assert "zymo" in result.output.lower()


class TestCheckDeps:
    def test_check_deps(self):
        result = runner.invoke(app, ["check-deps"])
        assert result.exit_code == 0


class TestRecommend:
    def test_recommend(self):
        result = runner.invoke(app, ["recommend", "--file-count", "100"])
        assert result.exit_code == 0


class TestValidate:
    def test_validate(self, source_dir_multiplex, tmp_path):
        result = runner.invoke(app, [
            "validate",
            "--target", str(source_dir_multiplex),
            "--adapter", "nanometa",
        ])
        assert result.exit_code == 0
```

**Step 2: Run tests — expect FAIL**

Run: `pytest tests_v2/test_cli.py -v`

**Step 3: Write implementation**

Rewrite `nanopore_simulator/cli/main.py` (1,409 lines) as a thin ~400-line dispatcher.

Key design:
- Each subcommand maps typer params directly to config fields
- `_filter_params(locals(), ConfigClass)` helper (~10 lines) removes `None` values and maps names
- Profile handling: `apply_profile()` returns dict, CLI overrides take precedence
- All validation in config `__post_init__`, no duplication in CLI
- Enums for typer choices (TimingModelChoice, OperationChoice, etc.) — keep these from existing code
- List/info commands call module-level functions directly

Port the following CLI param names from existing code (these define the CLI contract):
- `replay`: `--source`, `--target`, `--interval`, `--operation`, `--batch-size`, `--timing-model`, `--profile`, `--adapter`, `--parallel`, `--workers`, `--monitor`, `--reads-per-output`, `--structure`, timing sub-params
- `generate`: `--target`, `--genomes`, `--species`, `--mock`, `--taxids`, `--read-count`, `--interval`, `--batch-size`, `--backend`, `--mean-length`, `--std-length`, `--mean-quality`, `--std-quality`, `--reads-per-file`, `--output-format`, `--mix-reads`, `--abundances`, `--profile`, `--parallel`, `--workers`, `--monitor`
- `list-profiles`, `list-adapters`, `list-generators`, `list-mocks`, `check-deps`, `recommend`, `validate`, `download`

~400 lines.

**Step 4: Run tests — expect PASS**

Run: `pytest tests_v2/test_cli.py -v`

**Step 5: Commit**

```bash
git add nanopore_simulator_v2/cli.py tests_v2/test_cli.py
git commit -m "feat(v2): add thin CLI with direct config mapping"
```

---

## Phase 7: Integration & Swap

### Task 17: Integration tests

**Files:**
- Create: `tests_v2/test_integration.py`

**Step 1: Write integration tests**

```python
# tests_v2/test_integration.py
"""End-to-end integration tests."""

import pytest
from pathlib import Path
from typer.testing import CliRunner
from nanopore_simulator_v2.cli import app

runner = CliRunner()


class TestReplayIntegration:
    def test_singleplex_copy(self, source_dir_singleplex, tmp_path):
        target = tmp_path / "target"
        result = runner.invoke(app, [
            "replay",
            "--source", str(source_dir_singleplex),
            "--target", str(target),
            "--interval", "0",
            "--timing-model", "uniform",
        ])
        assert result.exit_code == 0
        assert len(list(target.glob("*.fastq"))) == 5

    def test_multiplex_copy(self, source_dir_multiplex, tmp_path):
        target = tmp_path / "target"
        result = runner.invoke(app, [
            "replay",
            "--source", str(source_dir_multiplex),
            "--target", str(target),
            "--interval", "0",
        ])
        assert result.exit_code == 0
        assert (target / "barcode01").exists()
        assert (target / "barcode02").exists()

    def test_with_profile(self, source_dir_singleplex, tmp_path):
        target = tmp_path / "target"
        result = runner.invoke(app, [
            "replay",
            "--source", str(source_dir_singleplex),
            "--target", str(target),
            "--profile", "development",
            "--interval", "0",
        ])
        assert result.exit_code == 0

    def test_parallel_replay(self, source_dir_singleplex, tmp_path):
        target = tmp_path / "target"
        result = runner.invoke(app, [
            "replay",
            "--source", str(source_dir_singleplex),
            "--target", str(target),
            "--interval", "0",
            "--parallel",
            "--workers", "2",
        ])
        assert result.exit_code == 0
        assert len(list(target.glob("*.fastq"))) == 5

    def test_link_operation(self, source_dir_singleplex, tmp_path):
        target = tmp_path / "target"
        result = runner.invoke(app, [
            "replay",
            "--source", str(source_dir_singleplex),
            "--target", str(target),
            "--operation", "link",
            "--interval", "0",
        ])
        assert result.exit_code == 0
        assert all(f.is_symlink() for f in target.glob("*.fastq"))


class TestGenerateIntegration:
    def test_single_genome(self, sample_fasta, tmp_path):
        target = tmp_path / "target"
        result = runner.invoke(app, [
            "generate",
            "--genomes", str(sample_fasta),
            "--target", str(target),
            "--read-count", "20",
            "--reads-per-file", "10",
            "--interval", "0",
            "--backend", "builtin",
        ])
        assert result.exit_code == 0
        output_files = list(target.rglob("*.fastq*"))
        assert len(output_files) == 2

    def test_multiple_genomes(self, tmp_path):
        g1 = tmp_path / "g1.fa"
        g2 = tmp_path / "g2.fa"
        g1.write_text(">chr1\nACGTACGTACGTACGT\n")
        g2.write_text(">chr1\nTTTTAAAACCCCGGGG\n")
        target = tmp_path / "target"
        result = runner.invoke(app, [
            "generate",
            "--genomes", str(g1),
            "--genomes", str(g2),
            "--target", str(target),
            "--read-count", "20",
            "--interval", "0",
            "--backend", "builtin",
        ])
        assert result.exit_code == 0


class TestTimingModels:
    def test_random_timing(self, source_dir_singleplex, tmp_path):
        target = tmp_path / "target"
        result = runner.invoke(app, [
            "replay",
            "--source", str(source_dir_singleplex),
            "--target", str(target),
            "--timing-model", "random",
            "--interval", "0",
        ])
        assert result.exit_code == 0

    def test_poisson_timing(self, source_dir_singleplex, tmp_path):
        target = tmp_path / "target"
        result = runner.invoke(app, [
            "replay",
            "--source", str(source_dir_singleplex),
            "--target", str(target),
            "--timing-model", "poisson",
            "--interval", "0",
        ])
        assert result.exit_code == 0
```

**Step 2: Run integration tests**

Run: `pytest tests_v2/test_integration.py -v`
Expected: All PASS (assuming all previous tasks completed)

**Step 3: Commit**

```bash
git add tests_v2/test_integration.py
git commit -m "test(v2): add end-to-end integration tests"
```

---

### Task 18: Swap packages and update entry points

**Files:**
- Rename: `nanopore_simulator/` → `nanopore_simulator_old/`
- Rename: `nanopore_simulator_v2/` → `nanopore_simulator/`
- Rename: `tests/` → `tests_old/`
- Rename: `tests_v2/` → `tests/`
- Modify: `pyproject.toml` or `setup.cfg` (if entry points reference specific modules)
- Modify: `nanopore_simulator/__init__.py`

**Step 1: Verify all v2 tests pass**

Run: `pytest tests_v2/ -v`
Expected: All PASS

**Step 2: Swap directories**

```bash
mv nanopore_simulator nanopore_simulator_old
mv nanopore_simulator_v2 nanopore_simulator
mv tests tests_old
mv tests_v2 tests
```

**Step 3: Update __init__.py exports**

Update `nanopore_simulator/__init__.py` to export the new public API:
```python
"""nanorunner - nanopore sequencing run simulator."""

__version__ = "3.0.0"

from .config import ReplayConfig, GenerateConfig
from .runner import run_replay, run_generate
```

**Step 4: Update setup.py/pyproject.toml entry points**

Verify `nanorunner` console script points to `nanopore_simulator.cli:app`. Check the existing entry point definition and update if the module path changed (it shouldn't — `nanopore_simulator.cli` is now `nanopore_simulator/cli.py` instead of `nanopore_simulator/cli/main.py`).

**Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All PASS

**Step 6: Test CLI**

```bash
pip install -e .
nanorunner --help
nanorunner list-profiles
nanorunner list-adapters
nanorunner list-generators
nanorunner list-mocks
nanorunner check-deps
```

**Step 7: Commit**

```bash
git add -A
git commit -m "refactor: swap to v2 package structure (plan-execute-monitor)"
```

---

### Task 19: Clean up and update documentation

**Files:**
- Delete: `nanopore_simulator_old/` (after confirming tests pass)
- Delete: `tests_old/` (after confirming tests pass)
- Modify: `CLAUDE.md` (update architecture section)
- Modify: `README.md` (update if internal module references exist)

**Step 1: Delete old code**

```bash
rm -rf nanopore_simulator_old tests_old
```

**Step 2: Update CLAUDE.md architecture section**

Update the Architecture section to reflect the new flat module layout, plan-execute-monitor pattern, and simplified abstractions.

**Step 3: Run final verification**

```bash
pytest tests/ -v --tb=short
nanorunner --help
nanorunner list-profiles
nanorunner list-mocks
```

**Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove old package, update documentation for v3 architecture"
```

---

## Summary

| Phase | Tasks | What it builds |
|-------|-------|----------------|
| 1 | 1 | Package scaffold |
| 2 | 2-5 | Foundation: config, fastq, detection, timing |
| 3 | 6-9 | Data/utility: mocks, adapters, deps, profiles |
| 4 | 10-12 | Core: generators, species, monitoring |
| 5 | 13-15 | Orchestration: manifest, executor, runner |
| 6 | 16 | CLI |
| 7 | 17-19 | Integration tests, swap, cleanup |

**19 tasks total.** Each task is TDD: write tests → verify fail → implement → verify pass → commit.

**Target outcome:**
- Source: ~10,000 → ~4,100 lines (16 files)
- Tests: ~17,500 → ~8,000 lines (16 files)
- No module exceeds 800 lines
- CLI contract unchanged
- All features preserved
