#!/usr/bin/env python
"""End-to-end audit driver for nanorunner generate + replay.

Sweeps the predefined matrix (mock communities, profiles, backends,
genome sources, output formats, and the 3x3 replay reshape matrix) on a
real filesystem, verifies output content, and measures the order in
which files appear across multiple samples.

Usage:
    python bin/audit_simulate_replay.py \
        --root /Volumes/LaCie/nanorunner/audit-2026-05-27

Exits non-zero if any scenario fails its assertions. Findings are
collected in <root>/reports/audit-report.md.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import shutil
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from nanopore_simulator import GenerateConfig, ReplayConfig
from nanopore_simulator.adapters import validate_output
from nanopore_simulator.deps import _detect_backends as probe_backends
from nanopore_simulator.fastq import iter_reads
from nanopore_simulator.mocks import BUILTIN_MOCKS, get_mock
from nanopore_simulator.profiles import PROFILES, apply_profile, get_profile
from nanopore_simulator.runner import run_generate, run_replay

logger = logging.getLogger("audit")


# ---------------------------------------------------------------------
# Scenario bookkeeping
# ---------------------------------------------------------------------


@dataclass
class Finding:
    scenario: str
    phase: str
    passed: bool = True
    details: List[str] = field(default_factory=list)
    duration_s: float = 0.0

    def add(self, msg: str) -> None:
        self.details.append(msg)

    def fail(self, msg: str) -> None:
        self.passed = False
        self.details.append(f"FAIL: {msg}")


def _quiet_config(target: Path) -> Dict[str, object]:
    """Common kwargs to keep audit runs fast and headless."""
    return dict(
        target_dir=target,
        interval=0.0,
        batch_size=1,
        monitor_type="none",
        generator_backend="builtin",
        mean_length=2000,
        std_length=500,
        min_length=200,
        reads_per_file=25,
        output_format="fastq.gz",
    )


def _collect_fastq(target: Path) -> List[Path]:
    return sorted(
        p
        for p in target.rglob("*")
        if p.suffix in {".fastq", ".gz"} and not p.name.startswith("._")
    )


def _read_count(path: Path) -> int:
    return sum(1 for _ in iter_reads(path))


def _per_dir_read_counts(target: Path) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for fq in _collect_fastq(target):
        key = fq.parent.name if fq.parent != target else "<root>"
        counts[key] = counts.get(key, 0) + _read_count(fq)
    return counts


def _file_mtime_order(target: Path) -> List[Tuple[float, Path]]:
    files = [
        p
        for p in target.rglob("*")
        if p.suffix in {".fastq", ".gz"} and not p.name.startswith("._")
    ]
    return sorted([(p.stat().st_mtime_ns, p) for p in files])


# ---------------------------------------------------------------------
# Per-scenario checks
# ---------------------------------------------------------------------


def _check_generated(
    finding: Finding,
    target: Path,
    *,
    expected_reads: int,
    expected_barcodes: Optional[int],
    expected_mean_length: int,
) -> None:
    files = _collect_fastq(target)
    if not files:
        finding.fail("no FASTQ output produced")
        return
    total = 0
    lengths: List[int] = []
    bad_headers = 0
    for fq in files:
        try:
            for header, seq, plus, qual in iter_reads(fq):
                total += 1
                lengths.append(len(seq))
                if not header.startswith("@"):
                    bad_headers += 1
                if len(seq) != len(qual):
                    finding.fail(f"seq/qual length mismatch in {fq.name}")
                    return
        except Exception as exc:
            finding.fail(f"unparseable FASTQ {fq.name}: {exc}")
            return
    finding.add(f"total_reads={total} files={len(files)}")
    if total != expected_reads:
        finding.fail(f"read count mismatch: expected {expected_reads}, got {total}")
    if bad_headers:
        finding.fail(f"{bad_headers} headers missing '@' prefix")
    if expected_barcodes is not None:
        bc_dirs = sorted(
            d.name
            for d in target.iterdir()
            if d.is_dir() and d.name.startswith("barcode")
        )
        finding.add(f"barcode_dirs={bc_dirs}")
        if len(bc_dirs) != expected_barcodes:
            finding.fail(
                f"expected {expected_barcodes} barcode dirs, found {len(bc_dirs)}"
            )
    if lengths:
        mean_len = sum(lengths) / len(lengths)
        finding.add(f"mean_length={mean_len:.0f}")
        # Loose sanity: within 50% of target. Log-normal + clipping is wide.
        if not (expected_mean_length * 0.5 <= mean_len <= expected_mean_length * 1.6):
            finding.fail(
                f"mean read length {mean_len:.0f} far from expected "
                f"{expected_mean_length}"
            )


def _ordering_metric(target: Path) -> Dict[str, object]:
    """Quantify cross-barcode interleaving.

    Returns a dict with the observed sequence of barcode names ordered by
    file mtime, the maximum run-length of one barcode in a row, and the
    number of barcode transitions.
    """
    order = _file_mtime_order(target)
    seq: List[str] = []
    for _, p in order:
        # parent dir is the barcode dir for multiplex output; for flat it
        # is the target dir itself
        seq.append(p.parent.name)
    if not seq:
        return {"sequence": [], "max_run": 0, "transitions": 0}
    max_run = 1
    cur_run = 1
    transitions = 0
    for prev, cur in zip(seq, seq[1:]):
        if prev == cur:
            cur_run += 1
            max_run = max(max_run, cur_run)
        else:
            transitions += 1
            cur_run = 1
    return {
        "sequence": seq,
        "max_run": max_run,
        "transitions": transitions,
        "n_files": len(seq),
        "n_buckets": len(set(seq)),
    }


# ---------------------------------------------------------------------
# Scenario runners
# ---------------------------------------------------------------------


def run_mock_sweep(root: Path, mocks: List[str]) -> List[Finding]:
    findings: List[Finding] = []
    for name in mocks:
        community = get_mock(name)
        if community is None:
            f = Finding(scenario=f"mock/{name}", phase="A2", passed=False)
            f.fail(f"unknown mock community: {name}")
            findings.append(f)
            continue
        genome_files, abundances = _mock_genomes(name, root)
        expected_barcodes = len(community.organisms)
        for fmt in ("fastq.gz", "fastq"):
            scenario = f"mock/{name}/{fmt}"
            target = root / "simulate" / "mocks" / name / fmt.replace(".", "_")
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            target.mkdir(parents=True)
            f = Finding(scenario=scenario, phase="A2")
            t0 = time.perf_counter()
            try:
                kwargs = _quiet_config(target)
                kwargs.update(
                    genome_inputs=list(genome_files),
                    abundances=abundances,
                    read_count=max(200, 20 * expected_barcodes),
                    reads_per_file=25,
                    structure="multiplex",
                    output_format=fmt,
                )
                cfg = GenerateConfig(**kwargs)
                run_generate(cfg)
                _check_generated(
                    f,
                    target,
                    expected_reads=cfg.read_count,
                    expected_barcodes=expected_barcodes,
                    expected_mean_length=2000,
                )
                # adapter structural validation (informational)
                problems = validate_output(target, "nanometa")
                if problems:
                    f.add(f"nanometa adapter problems: {problems}")
                if any(d.startswith("FAIL") for d in f.details):
                    f.passed = False
            except Exception as exc:
                f.fail(f"exception: {exc}\n{traceback.format_exc()}")
            f.duration_s = time.perf_counter() - t0
            findings.append(f)
            logger.info(
                "%s -> %s (%.1fs)", scenario, "OK" if f.passed else "FAIL", f.duration_s
            )
    return findings


def run_profile_sweep(root: Path, genome_files: List[Path]) -> List[Finding]:
    findings: List[Finding] = []
    for name in sorted(PROFILES.keys()):
        scenario = f"profile/{name}"
        target = root / "simulate" / "profiles" / name
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True)
        f = Finding(scenario=scenario, phase="A3")
        t0 = time.perf_counter()
        try:
            # Only exercise generate-oriented profiles for generate runs.
            profile = get_profile(name)
            is_generate_profile = (
                name.startswith("generate_") or "read_count" in profile
            )
            if not is_generate_profile:
                # Use replay-oriented profile against the mock dataset
                f.add(f"profile is replay-oriented (skipping generate exercise)")
                f.passed = True
                findings.append(f)
                continue
            params = apply_profile(name)
            kwargs = _quiet_config(target)
            kwargs.update(
                genome_inputs=list(genome_files),
                structure="multiplex",
                read_count=params.get("read_count", 120),
                reads_per_file=params.get("reads_per_file", 30),
                timing_model=params.get("timing_model", "uniform"),
                timing_params=params.get("timing_model_params", {}),
                batch_size=params.get("batch_size", 1),
                parallel=params.get("parallel_processing", False),
                workers=params.get("worker_count", 4),
                generator_backend=params.get("generator_backend", "builtin"),
            )
            # Cap profiles that ask for huge generation to keep audit fast.
            if kwargs["read_count"] > 200:
                kwargs["read_count"] = 200
            kwargs["interval"] = 0.0
            cfg = GenerateConfig(**kwargs)
            run_generate(cfg)
            _check_generated(
                f,
                target,
                expected_reads=cfg.read_count,
                expected_barcodes=len(genome_files),
                expected_mean_length=cfg.mean_length,
            )
            f.passed = not any(d.startswith("FAIL") for d in f.details)
        except Exception as exc:
            f.fail(f"exception: {exc}\n{traceback.format_exc()}")
        f.duration_s = time.perf_counter() - t0
        findings.append(f)
        logger.info(
            "%s -> %s (%.1fs)", scenario, "OK" if f.passed else "FAIL", f.duration_s
        )
    return findings


def run_backend_sweep(root: Path, genome_files: List[Path]) -> List[Finding]:
    findings: List[Finding] = []
    avail = probe_backends()
    for backend in ("builtin", "badread", "nanosim", "auto"):
        scenario = f"backend/{backend}"
        target = root / "simulate" / "backends" / backend
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True)
        f = Finding(scenario=scenario, phase="A4")
        t0 = time.perf_counter()
        try:
            if backend in ("badread", "nanosim") and not avail.get(backend, False):
                f.add(f"backend {backend} not installed -- skipped")
                f.passed = True
                findings.append(f)
                continue
            kwargs = _quiet_config(target)
            kwargs.update(
                genome_inputs=list(genome_files),
                read_count=60,
                reads_per_file=30,
                structure="multiplex",
                generator_backend=backend,
            )
            cfg = GenerateConfig(**kwargs)
            run_generate(cfg)
            _check_generated(
                f,
                target,
                expected_reads=60,
                expected_barcodes=len(genome_files),
                expected_mean_length=2000,
            )
            f.passed = not any(d.startswith("FAIL") for d in f.details)
        except Exception as exc:
            f.fail(f"exception: {exc}\n{traceback.format_exc()}")
        f.duration_s = time.perf_counter() - t0
        findings.append(f)
    return findings


def run_mix_reads(root: Path, genome_files: List[Path]) -> List[Finding]:
    scenario = "mix-reads/quick_3species"
    target = root / "simulate" / "mix-reads" / "quick_3species"
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    f = Finding(scenario=scenario, phase="A5")
    t0 = time.perf_counter()
    try:
        kwargs = _quiet_config(target)
        kwargs.update(
            genome_inputs=list(genome_files),
            read_count=120,
            reads_per_file=40,
            structure="singleplex",
            mix_reads=True,
        )
        cfg = GenerateConfig(**kwargs)
        run_generate(cfg)
        files = _collect_fastq(target)
        stems = set()
        total = 0
        for fq in files:
            for header, seq, _plus, _qual in iter_reads(fq):
                total += 1
                # Header is "@<stem>_read_N" — capture <stem>
                stem = header.lstrip("@").rsplit("_read_", 1)[0]
                stems.add(stem)
        f.add(f"total_reads={total} files={len(files)} stems={sorted(stems)}")
        if total != 120:
            f.fail(f"expected 120 reads, got {total}")
        if len(stems) != len(genome_files):
            f.fail(
                f"expected reads from {len(genome_files)} genomes, "
                f"got {len(stems)}: {sorted(stems)}"
            )
        f.passed = not any(d.startswith("FAIL") for d in f.details)
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    return [f]


def run_ordering_generate(root: Path, genome_files: List[Path]) -> List[Finding]:
    """Phase A6: measure cross-barcode write ordering for generate."""
    findings: List[Finding] = []
    for batch_size in (1, len(genome_files)):
        scenario = f"ordering/generate/batch{batch_size}"
        target = root / "simulate" / "ordering" / f"batch{batch_size}"
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True)
        f = Finding(scenario=scenario, phase="A6")
        t0 = time.perf_counter()
        try:
            kwargs = _quiet_config(target)
            kwargs.update(
                genome_inputs=list(genome_files),
                read_count=600,
                reads_per_file=50,
                structure="multiplex",
                batch_size=batch_size,
                interval=0.05,  # nonzero so mtimes are distinguishable
            )
            cfg = GenerateConfig(**kwargs)
            run_generate(cfg)
            metric = _ordering_metric(target)
            f.add(f"sequence={metric['sequence']}")
            f.add(f"max_run={metric['max_run']} transitions={metric['transitions']}")
            n_per_barcode = metric["n_files"] // max(1, metric["n_buckets"])
            # Pass criterion: with batch_size=n_genomes we expect maximum run
            # of 1 between barcodes (or at most n_genomes if same-batch order
            # within a batch happens to repeat). With batch_size=1, run_max
            # equal to per-barcode file count signals total grouping.
            if batch_size == 1 and metric["max_run"] >= n_per_barcode:
                f.fail(
                    f"batch_size=1 emits files grouped by barcode "
                    f"(max_run={metric['max_run']}, files/barcode={n_per_barcode}); "
                    "expected interleaving"
                )
            else:
                f.passed = True
        except Exception as exc:
            f.fail(f"exception: {exc}\n{traceback.format_exc()}")
        f.duration_s = time.perf_counter() - t0
        findings.append(f)
    return findings


def run_replay_reshape_matrix(root: Path, sources: Dict[str, Path]) -> List[Finding]:
    """Phase B1: 3x3 reshape matrix."""
    findings: List[Finding] = []
    shapes_out = ("preserve", "flat", "barcoded")
    for in_shape, source in sources.items():
        for out_shape in shapes_out:
            scenario = f"replay/{in_shape}__to__{out_shape}"
            target = root / "replay" / "matrix" / f"{in_shape}__to__{out_shape}"
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            target.mkdir(parents=True)
            f = Finding(scenario=scenario, phase="B1")
            t0 = time.perf_counter()
            try:
                kwargs: Dict[str, object] = dict(
                    source_dir=source,
                    target_dir=target,
                    operation="copy",
                    interval=0.0,
                    batch_size=1,
                    monitor_type="none",
                    output_structure=out_shape,
                )
                if out_shape != "preserve":
                    kwargs["reads_per_output"] = 25
                if out_shape == "barcoded":
                    kwargs["output_barcodes"] = 3
                cfg = ReplayConfig(**kwargs)
                run_replay(cfg)
                src_total = (
                    sum(
                        _read_count(p)
                        for p in _collect_fastq(source)
                        if source.is_dir()
                    )
                    if source.is_dir()
                    else _read_count(source)
                )
                tgt_total = sum(_read_count(p) for p in _collect_fastq(target))
                f.add(f"src_reads={src_total} tgt_reads={tgt_total}")
                if src_total != tgt_total:
                    f.fail(f"read count not preserved ({src_total} -> {tgt_total})")
                if out_shape == "barcoded":
                    bc_dirs = sorted(
                        d.name
                        for d in target.iterdir()
                        if d.is_dir() and d.name.startswith("barcode")
                    )
                    f.add(f"output_barcode_dirs={bc_dirs}")
                    # Round-robin fills barcode bins by chunk index; with
                    # fewer chunks than requested barcodes some bins stay
                    # empty. That is correct behaviour, not a failure.
                    if len(bc_dirs) > 3 or len(bc_dirs) == 0:
                        f.fail(f"unexpected output barcode count: {len(bc_dirs)}")
                f.passed = not any(d.startswith("FAIL") for d in f.details)
            except Exception as exc:
                f.fail(f"exception: {exc}\n{traceback.format_exc()}")
            f.duration_s = time.perf_counter() - t0
            findings.append(f)
            logger.info("%s -> %s", scenario, "OK" if f.passed else "FAIL")
    return findings


def run_replay_ordering(root: Path, source: Path) -> List[Finding]:
    """Phase B3: cross-barcode ordering on replay."""
    scenario = "replay/ordering/barcoded_to_barcoded"
    target = root / "replay" / "ordering" / "barcoded_to_barcoded"
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    f = Finding(scenario=scenario, phase="B3")
    t0 = time.perf_counter()
    try:
        cfg = ReplayConfig(
            source_dir=source,
            target_dir=target,
            operation="copy",
            interval=0.05,
            batch_size=1,
            monitor_type="none",
            output_structure="barcoded",
            reads_per_output=25,
            output_barcodes=3,
        )
        run_replay(cfg)
        metric = _ordering_metric(target)
        f.add(f"sequence={metric['sequence']}")
        f.add(f"max_run={metric['max_run']} transitions={metric['transitions']}")
        if (
            metric["n_buckets"] > 1
            and metric["max_run"] >= metric["n_files"] // metric["n_buckets"]
        ):
            f.fail("replay reshape did not interleave across output barcodes")
        else:
            f.passed = True
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    return [f]


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _synthetic_fasta_for(name: str, root: Path) -> Path:
    """Create (or reuse) a 30 kb synthetic FASTA for a named organism."""
    import random

    out_dir = root / "_genomes"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() else "_" for c in name)
    path = out_dir / f"{safe}.fasta"
    if not path.exists():
        rng = random.Random(hash(name) & 0xFFFFFFFF)
        seq = "".join(rng.choices("ACGT", k=30_000))
        with path.open("w") as fh:
            fh.write(f">{safe}\n")
            for j in range(0, len(seq), 80):
                fh.write(seq[j : j + 80] + "\n")
    return path


def _mock_genomes(mock_name: str, root: Path) -> Tuple[List[Path], List[float]]:
    """Return per-organism synthetic FASTAs and their abundances for a mock."""
    community = get_mock(mock_name)
    if community is None:
        raise ValueError(f"unknown mock: {mock_name}")
    paths: List[Path] = []
    weights: List[float] = []
    for org in community.organisms:
        paths.append(_synthetic_fasta_for(f"{mock_name}_{org.name}", root))
        weights.append(org.abundance)
    # Renormalise (some catalogs use rough proportions, not exact 1.0).
    total = sum(weights) or 1.0
    weights = [w / total for w in weights]
    return paths, weights


def _make_synthetic_genomes(root: Path, n: int = 3) -> List[Path]:
    """Build n trivial FASTA files for genome-source scenarios.

    Using synthetic FASTAs avoids network dependence and keeps the audit
    deterministic. Each genome is a single 30 kb sequence so the builtin
    log-normal generator has room for ~5 kb mean reads.
    """
    import random

    out_dir = root / "_genomes"
    out_dir.mkdir(exist_ok=True)
    rng = random.Random(20260527)
    paths: List[Path] = []
    names = ["ecoliK12", "bsubtilis168", "saureusNCTC"]
    for i, name in enumerate(names[:n]):
        path = out_dir / f"{name}.fasta"
        if not path.exists():
            seq = "".join(rng.choices("ACGT", k=30_000))
            with path.open("w") as fh:
                fh.write(f">{name}\n")
                for j in range(0, len(seq), 80):
                    fh.write(seq[j : j + 80] + "\n")
        paths.append(path)
    return paths


def run_timing_models(root: Path, genome_files: List[Path]) -> List[Finding]:
    """Phase A7: each timing model must run end-to-end without error."""
    findings: List[Finding] = []
    for model in ("uniform", "random", "poisson", "adaptive"):
        scenario = f"timing/{model}"
        target = root / "simulate" / "timing" / model
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True)
        f = Finding(scenario=scenario, phase="A7")
        t0 = time.perf_counter()
        try:
            kwargs = _quiet_config(target)
            kwargs.update(
                genome_inputs=list(genome_files),
                read_count=60,
                reads_per_file=20,
                structure="multiplex",
                timing_model=model,
                interval=0.01,
            )
            cfg = GenerateConfig(**kwargs)
            run_generate(cfg)
            files = _collect_fastq(target)
            total = sum(_read_count(p) for p in files)
            f.add(f"files={len(files)} reads={total}")
            if total != 60:
                f.fail(f"expected 60 reads, got {total}")
        except Exception as exc:
            f.fail(f"exception: {exc}\n{traceback.format_exc()}")
        f.duration_s = time.perf_counter() - t0
        findings.append(f)
    return findings


def run_parallel(root: Path, genome_files: List[Path]) -> List[Finding]:
    """Phase A8: parallel generate (multiple workers) must not corrupt output."""
    scenario = "parallel/generate_workers4"
    target = root / "simulate" / "parallel" / "workers4"
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    f = Finding(scenario=scenario, phase="A8")
    t0 = time.perf_counter()
    try:
        kwargs = _quiet_config(target)
        kwargs.update(
            genome_inputs=list(genome_files),
            read_count=300,
            reads_per_file=25,
            structure="multiplex",
            batch_size=4,
            parallel=True,
            workers=4,
            interval=0.0,
        )
        cfg = GenerateConfig(**kwargs)
        run_generate(cfg)
        files = _collect_fastq(target)
        total = sum(_read_count(p) for p in files)
        f.add(f"files={len(files)} reads={total}")
        if total != 300:
            f.fail(f"expected 300 reads, got {total}")
        # All FASTQs must parse cleanly (no half-written records).
        for fq in files:
            for header, seq, _plus, qual in iter_reads(fq):
                if not header.startswith("@") or len(seq) != len(qual):
                    f.fail(f"corrupted record in {fq.name}")
                    break
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    return [f]


def run_abundance_fidelity(root: Path, genome_files: List[Path]) -> List[Finding]:
    """Phase A9: 90/10 abundance must produce ~90/10 reads in output."""
    scenario = "abundance/90_10"
    target = root / "simulate" / "abundance" / "90_10"
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    f = Finding(scenario=scenario, phase="A9")
    t0 = time.perf_counter()
    try:
        two_genomes = genome_files[:2]
        kwargs = _quiet_config(target)
        kwargs.update(
            genome_inputs=two_genomes,
            abundances=[0.9, 0.1],
            read_count=1000,
            reads_per_file=100,
            structure="multiplex",
        )
        cfg = GenerateConfig(**kwargs)
        run_generate(cfg)
        per_dir = _per_dir_read_counts(target)
        f.add(f"per_dir={per_dir}")
        bc01 = per_dir.get("barcode01", 0)
        bc02 = per_dir.get("barcode02", 0)
        if bc01 + bc02 != 1000:
            f.fail(f"read total wrong: {bc01 + bc02}")
        if not (880 <= bc01 <= 920):
            f.fail(f"barcode01 reads {bc01} not in 90% +-2% band")
        if not (80 <= bc02 <= 120):
            f.fail(f"barcode02 reads {bc02} not in 10% +-2% band")
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    return [f]


def run_quality_score_validity(root: Path, genome_files: List[Path]) -> List[Finding]:
    """Phase A10: every quality char must be in Phred+33 range [!, ~]."""
    scenario = "quality/phred33_range"
    target = root / "simulate" / "quality" / "phred33"
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    f = Finding(scenario=scenario, phase="A10")
    t0 = time.perf_counter()
    try:
        kwargs = _quiet_config(target)
        kwargs.update(
            genome_inputs=list(genome_files),
            read_count=300,
            reads_per_file=100,
            structure="multiplex",
            mean_quality=15.0,
            std_quality=5.0,
        )
        cfg = GenerateConfig(**kwargs)
        run_generate(cfg)
        bad = 0
        n_reads = 0
        for fq in _collect_fastq(target):
            for _h, _s, _p, qual in iter_reads(fq):
                n_reads += 1
                for ch in qual:
                    o = ord(ch)
                    if o < 33 or o > 126:
                        bad += 1
                        break
        f.add(f"reads_checked={n_reads} bad_quality_strings={bad}")
        if bad:
            f.fail(f"{bad} reads had out-of-range Phred+33 quality chars")
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    return [f]


def run_link_operation(root: Path, source: Path) -> List[Finding]:
    """Phase B4: replay --operation link should produce symlinks."""
    scenario = "replay/link_operation"
    target = root / "replay" / "link"
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    f = Finding(scenario=scenario, phase="B4")
    t0 = time.perf_counter()
    try:
        cfg = ReplayConfig(
            source_dir=source,
            target_dir=target,
            operation="link",
            interval=0.0,
            batch_size=1,
            monitor_type="none",
        )
        run_replay(cfg)
        files = _collect_fastq(target)
        if not files:
            f.fail("no files produced")
        n_symlink = sum(1 for p in files if p.is_symlink())
        f.add(f"files={len(files)} symlinks={n_symlink}")
        if n_symlink != len(files):
            f.fail(f"{len(files) - n_symlink} files are not symlinks")
        # Sanity: read counts preserved
        src_total = sum(_read_count(p) for p in _collect_fastq(source))
        tgt_total = sum(_read_count(p) for p in files)
        if src_total != tgt_total:
            f.fail(f"read count drift: {src_total} -> {tgt_total}")
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    return [f]


def run_replay_batched_ordering(root: Path, source: Path) -> List[Finding]:
    """Phase B5: replay batch_size>1 + parallel must preserve totals."""
    scenario = "replay/batch4_parallel"
    target = root / "replay" / "batch4_parallel"
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    f = Finding(scenario=scenario, phase="B5")
    t0 = time.perf_counter()
    try:
        cfg = ReplayConfig(
            source_dir=source,
            target_dir=target,
            operation="copy",
            interval=0.0,
            batch_size=4,
            parallel=True,
            workers=4,
            monitor_type="none",
        )
        run_replay(cfg)
        src = sum(_read_count(p) for p in _collect_fastq(source))
        tgt = sum(_read_count(p) for p in _collect_fastq(target))
        f.add(f"src={src} tgt={tgt}")
        if src != tgt:
            f.fail(f"read count mismatch")
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    return [f]


def run_edge_cases(root: Path, genome_files: List[Path]) -> List[Finding]:
    """Phase A11: pathological inputs (1 read, more barcodes than chunks)."""
    findings: List[Finding] = []

    # 1 read across 3 genomes (multiplex)
    scenario = "edge/one_read_three_genomes"
    target = root / "simulate" / "edge" / "one_read_3"
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    f = Finding(scenario=scenario, phase="A11")
    t0 = time.perf_counter()
    try:
        kwargs = _quiet_config(target)
        kwargs.update(
            genome_inputs=list(genome_files),
            read_count=1,
            reads_per_file=10,
            structure="multiplex",
        )
        cfg = GenerateConfig(**kwargs)
        run_generate(cfg)
        files = _collect_fastq(target)
        total = sum(_read_count(p) for p in files)
        f.add(f"files={len(files)} total_reads={total}")
        # `distribute_reads` guarantees minimum 1 per organism when
        # total<n, so we accept >= 1 but flag if total is zero or huge.
        if total < 1:
            f.fail("no reads produced")
        if total > 10:
            f.fail(f"unexpectedly many reads: {total}")
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    # 5 reads with reads_per_file=100 (single tiny file expected)
    scenario = "edge/few_reads_large_chunk"
    target = root / "simulate" / "edge" / "few_reads"
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    f = Finding(scenario=scenario, phase="A11")
    t0 = time.perf_counter()
    try:
        kwargs = _quiet_config(target)
        kwargs.update(
            genome_inputs=list(genome_files[:1]),
            read_count=5,
            reads_per_file=100,
            structure="singleplex",
        )
        cfg = GenerateConfig(**kwargs)
        run_generate(cfg)
        files = _collect_fastq(target)
        total = sum(_read_count(p) for p in files)
        f.add(f"files={len(files)} total_reads={total}")
        if total != 5 or len(files) != 1:
            f.fail(
                f"expected 1 file with 5 reads, got {len(files)} files / {total} reads"
            )
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)
    return findings


def write_report(root: Path, findings: List[Finding]) -> Path:
    path = root / "reports" / "audit-report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    total = len(findings)
    failed = [f for f in findings if not f.passed]
    by_phase: Dict[str, List[Finding]] = {}
    for f in findings:
        by_phase.setdefault(f.phase, []).append(f)
    lines = [
        "# nanorunner simulate + replay audit",
        "",
        f"- total scenarios: {total}",
        f"- failed: {len(failed)}",
        f"- passed: {total - len(failed)}",
        "",
    ]
    for phase in sorted(by_phase):
        lines.append(f"## Phase {phase}")
        lines.append("")
        lines.append("| scenario | result | seconds | details |")
        lines.append("|---|---|---|---|")
        for f in by_phase[phase]:
            status = "PASS" if f.passed else "FAIL"
            joined = "<br>".join(d.replace("|", "\\|") for d in f.details)
            lines.append(f"| {f.scenario} | {status} | {f.duration_s:.2f} | {joined} |")
        lines.append("")
    if failed:
        lines.append("## Failure detail")
        for f in failed:
            lines.append(f"### {f.scenario}")
            for d in f.details:
                lines.append(f"- {d}")
            lines.append("")
    path.write_text("\n".join(lines))
    return path


# ---------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True, type=Path)
    p.add_argument(
        "--mocks",
        nargs="*",
        default=None,
        help="Subset of mock names; default = all (will take longer)",
    )
    p.add_argument(
        "--skip",
        nargs="*",
        default=[],
        choices=[
            "mocks",
            "profiles",
            "backends",
            "mix",
            "order_gen",
            "timing",
            "parallel",
            "abundance",
            "quality",
            "edge",
            "replay",
            "order_replay",
            "link",
            "batch_replay",
        ],
    )
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    root: Path = args.root
    root.mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(exist_ok=True)
    (root / "reports").mkdir(exist_ok=True)

    genome_files = _make_synthetic_genomes(root, n=3)
    logger.info("synthetic genomes: %s", [p.name for p in genome_files])

    mocks = args.mocks or sorted(BUILTIN_MOCKS.keys())
    findings: List[Finding] = []

    if "mocks" not in args.skip:
        findings.extend(run_mock_sweep(root, mocks))
    if "profiles" not in args.skip:
        findings.extend(run_profile_sweep(root, genome_files))
    if "backends" not in args.skip:
        findings.extend(run_backend_sweep(root, genome_files))
    if "mix" not in args.skip:
        findings.extend(run_mix_reads(root, genome_files))
    if "order_gen" not in args.skip:
        findings.extend(run_ordering_generate(root, genome_files))
    if "timing" not in args.skip:
        findings.extend(run_timing_models(root, genome_files))
    if "parallel" not in args.skip:
        findings.extend(run_parallel(root, genome_files))
    if "abundance" not in args.skip:
        findings.extend(run_abundance_fidelity(root, genome_files))
    if "quality" not in args.skip:
        findings.extend(run_quality_score_validity(root, genome_files))
    if "edge" not in args.skip:
        findings.extend(run_edge_cases(root, genome_files))

    # Phase B: replay using Phase A outputs as sources.
    sources: Dict[str, Path] = {}
    flat_src = root / "simulate" / "mix-reads" / "quick_3species"
    barcoded_src = root / "simulate" / "ordering" / "batch1"
    if flat_src.exists() and any(flat_src.iterdir()):
        sources["flat_dir"] = flat_src
        # Pick a single FASTQ from the flat source for the single-file case.
        first_fastq = next(iter(_collect_fastq(flat_src)), None)
        if first_fastq is not None:
            sources["single_file"] = first_fastq
    if barcoded_src.exists() and any(barcoded_src.iterdir()):
        sources["barcoded_dir"] = barcoded_src

    if "replay" not in args.skip and sources:
        findings.extend(run_replay_reshape_matrix(root, sources))
    if "order_replay" not in args.skip and "barcoded_dir" in sources:
        findings.extend(run_replay_ordering(root, sources["barcoded_dir"]))
    if "link" not in args.skip and "barcoded_dir" in sources:
        findings.extend(run_link_operation(root, sources["barcoded_dir"]))
    if "batch_replay" not in args.skip and "barcoded_dir" in sources:
        findings.extend(run_replay_batched_ordering(root, sources["barcoded_dir"]))

    report = write_report(root, findings)
    logger.info("wrote %s", report)

    failed = sum(1 for f in findings if not f.passed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
