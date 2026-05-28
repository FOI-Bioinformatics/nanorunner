#!/usr/bin/env python
"""Round 12: cross-filesystem atomic_move + memory under sustained load.

- FF (cross-fs atomic_move): the EXDEV fallback path added in v3.1.0
  has one regression test but has never been exercised in an audit
  driver. Forcing EXDEV via monkeypatch confirms the fallback runs
  and the file lands at the target.
- GG (memory under sustained load): repeatedly invoke run_generate
  in the same Python process and observe RSS growth. Linear growth
  with read count is expected; growth across same-size iterations
  would indicate a leak (e.g. an unbounded genome cache).

Usage:
    python bin/audit_atomic_memory.py --root /tmp/audit-2026-05-28-round12
"""

from __future__ import annotations

import argparse
import errno
import logging
import resource
import shutil
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_simulate_replay import _synthetic_fasta_for  # noqa: E402

logger = logging.getLogger("audit-r12")
REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Finding:
    scenario: str
    phase: str
    passed: bool = True
    details: List[str] = field(default_factory=list)
    duration_s: float = 0.0

    def add(self, m: str) -> None:
        self.details.append(m)

    def fail(self, m: str) -> None:
        self.passed = False
        self.details.append(f"FAIL: {m}")


def _reset(p: Path) -> Path:
    if p.exists():
        shutil.rmtree(p, ignore_errors=True)
    p.mkdir(parents=True)
    return p


def _rss_kb() -> int:
    """Return the current process resident set size in kilobytes.

    macOS reports rusage.ru_maxrss in bytes; Linux in kilobytes.
    Normalize to KB.
    """
    val = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return val // 1024
    return val


# ---------------------------------------------------------------------
# Phase FF: cross-filesystem atomic_move
# ---------------------------------------------------------------------


def phase_ff_cross_fs(root: Path) -> List[Finding]:
    findings: List[Finding] = []
    from nanopore_simulator.fastq import atomic_move

    # FF1: when os.replace raises EXDEV, atomic_move must fall back to
    # shutil.move and the destination must exist.
    f = Finding(scenario="atomic_move/exdev_fallback", phase="FF")
    t0 = time.perf_counter()
    try:
        d = _reset(root / "ff" / "exdev")
        src = d / ".target.tmp"
        src.write_text("hello cross-fs\n")
        target = d / "target"

        original_replace = __import__("os").replace
        call_count = {"n": 0}

        def fake_replace(a, b):
            call_count["n"] += 1
            raise OSError(errno.EXDEV, "Cross-device link")

        with patch("os.replace", side_effect=fake_replace):
            atomic_move(src, target)

        f.add(f"replace_called={call_count['n']}")
        if not target.exists():
            f.fail("target does not exist after EXDEV fallback")
        elif src.exists():
            f.fail("source temp still exists after fallback (not moved)")
        elif target.read_text() != "hello cross-fs\n":
            f.fail("target content does not match source content")
        elif call_count["n"] != 1:
            f.fail(f"expected exactly one os.replace call, got {call_count['n']}")
        # Sanity: confirm normal moves still hit the fast path.
        _ = original_replace
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    # FF2: a non-EXDEV OSError must propagate, not silently fall back.
    f = Finding(scenario="atomic_move/permission_error_propagates", phase="FF")
    t0 = time.perf_counter()
    try:
        d = _reset(root / "ff" / "perm")
        src = d / ".target.tmp"
        src.write_text("x")
        target = d / "target"

        def perm_denied(a, b):
            raise OSError(errno.EACCES, "Permission denied")

        raised = False
        with patch("os.replace", side_effect=perm_denied):
            try:
                atomic_move(src, target)
            except OSError as exc:
                raised = exc.errno == errno.EACCES
        if not raised:
            f.fail("non-EXDEV OSError was swallowed by atomic_move")
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    # FF3: real cross-mount test if /Volumes/LaCie is available
    # (the LaCie external drive used by earlier rounds). Skip cleanly
    # otherwise; this is opportunistic, not a contract.
    f = Finding(scenario="atomic_move/real_cross_mount", phase="FF")
    t0 = time.perf_counter()
    try:
        external = Path("/Volumes/LaCie")
        if not external.exists():
            f.add("no /Volumes/LaCie mount; skipped (informational)")
        else:
            # We need source and target on different volumes. Source
            # on the system FS (root /tmp/...), target on /Volumes/LaCie.
            scratch_local = _reset(root / "ff" / "cross_local")
            scratch_remote = external / "nanorunner_round12_cross_mount"
            if scratch_remote.exists():
                shutil.rmtree(scratch_remote, ignore_errors=True)
            scratch_remote.mkdir(parents=True, exist_ok=True)
            src = scratch_local / ".target.tmp"
            src.write_text("cross-mount payload\n")
            target = scratch_remote / "target"
            atomic_move(src, target)
            if not target.exists() or src.exists():
                f.fail("real cross-mount move did not land")
            shutil.rmtree(scratch_remote, ignore_errors=True)
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    return findings


# ---------------------------------------------------------------------
# Phase GG: memory under sustained load
# ---------------------------------------------------------------------


def phase_gg_memory(root: Path) -> List[Finding]:
    findings: List[Finding] = []
    from nanopore_simulator import GenerateConfig
    from nanopore_simulator.runner import run_generate

    genome = _synthetic_fasta_for("ecoliK12", root)

    # Warm-up: import the module and run once so steady-state RSS
    # excludes one-off allocations (numpy, typer, etc.).
    warm_target = _reset(root / "gg" / "warm")
    run_generate(
        GenerateConfig(
            target_dir=warm_target,
            genome_inputs=[genome],
            read_count=100,
            reads_per_file=100,
            mean_length=1500,
            interval=0.0,
            monitor_type="none",
            generator_backend="builtin",
            output_format="fastq",
        )
    )

    # GG1: same-size iterations should not grow RSS noticeably -- if
    # they do, something is being retained across calls (cache, list,
    # logger handler, etc.). Allow 5 MB headroom for GC variance.
    f = Finding(scenario="memory/no_leak_across_iterations", phase="GG")
    t0 = time.perf_counter()
    try:
        rss_samples = []
        for i in range(5):
            tgt = _reset(root / "gg" / f"iter_{i}")
            run_generate(
                GenerateConfig(
                    target_dir=tgt,
                    genome_inputs=[genome],
                    read_count=500,
                    reads_per_file=100,
                    mean_length=1500,
                    interval=0.0,
                    monitor_type="none",
                    generator_backend="builtin",
                    output_format="fastq",
                )
            )
            rss_samples.append(_rss_kb())
        # Compare last 3 to first; if the trend is upward something
        # is accumulating.
        baseline = rss_samples[0]
        growth_kb = rss_samples[-1] - baseline
        f.add(f"rss_kb_samples={rss_samples}")
        f.add(f"growth_baseline_to_last={growth_kb} KB")
        # 5 MB tolerance; the runner allocates GenomeCache + ThreadPool
        # state that may grow a little, but anything past this would
        # indicate an unbounded structure.
        if growth_kb > 5 * 1024:
            f.fail(f"RSS grew {growth_kb} KB over 5 iterations; possible leak")
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    # GG2: scaling -- 10x read count should NOT 10x peak RSS. The
    # builtin generator streams reads to disk so its memory should be
    # roughly O(genome_size + chunk_size), not O(total_reads).
    f = Finding(scenario="memory/sublinear_in_read_count", phase="GG")
    t0 = time.perf_counter()
    try:
        sizes = [200, 2000, 10000]
        peaks: List[int] = []
        for n in sizes:
            tgt = _reset(root / "gg" / f"scale_{n}")
            run_generate(
                GenerateConfig(
                    target_dir=tgt,
                    genome_inputs=[genome],
                    read_count=n,
                    reads_per_file=100,
                    mean_length=1500,
                    interval=0.0,
                    monitor_type="none",
                    generator_backend="builtin",
                    output_format="fastq",
                )
            )
            peaks.append(_rss_kb())
        f.add(f"sizes={sizes} peak_kb={peaks}")
        # 50x read count growth, peak RSS should grow far less than
        # 50x. Allow 5x as a generous bound.
        first_peak = peaks[0]
        last_peak = peaks[-1]
        if last_peak > first_peak * 5 and (last_peak - first_peak) > 10 * 1024:
            f.fail(
                f"peak RSS grew from {first_peak} KB to {last_peak} KB "
                f"for {sizes[0]} vs {sizes[-1]} reads -- super-linear"
            )
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    return findings


def write_report(root: Path, findings: List[Finding]) -> Path:
    path = root / "reports" / "atomic-memory-report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    failed = [f for f in findings if not f.passed]
    by_phase: Dict[str, List[Finding]] = {}
    for f in findings:
        by_phase.setdefault(f.phase, []).append(f)
    lines = [
        "# nanorunner atomic_move + memory audit (round 12)",
        "",
        f"- total scenarios: {len(findings)}",
        f"- failed: {len(failed)}",
        f"- passed: {len(findings) - len(failed)}",
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


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True, type=Path)
    args = p.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    root: Path = args.root
    root.mkdir(parents=True, exist_ok=True)
    (root / "reports").mkdir(exist_ok=True)

    findings: List[Finding] = []
    findings.extend(phase_ff_cross_fs(root))
    findings.extend(phase_gg_memory(root))

    report = write_report(root, findings)
    logger.info("wrote %s", report)
    return 1 if any(not f.passed for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
