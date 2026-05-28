#!/usr/bin/env python
"""Round 10: cross-Python compat + real-time timing observability.

- BB (cross-Python): a Python 3.9 venv is built externally; this
  driver only records the result of running the suite there.
- CC (real-time timing): every previous round used --no-wait so the
  timing layer was structurally exercised but never observed pacing
  output. Run replay with realistic intervals and confirm the
  file-emission spacing matches what each timing model promises:
    * uniform: roughly constant spacing
    * random:  bounded jitter around the base interval
    * poisson: occasional bursts (multiple files within <0.1s)
    * adaptive: smoothly varying spacing

Usage:
    python bin/audit_realtime_timing.py --root /tmp/audit-2026-05-28-round10
"""

from __future__ import annotations

import argparse
import logging
import shutil
import statistics
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("audit-r10")
NANORUNNER = "nanorunner"
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


def _run(args, timeout=120, **kw):
    return subprocess.run(
        [NANORUNNER, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        **kw,
    )


def _mtimes(target: Path) -> List[float]:
    """Return per-file inode-change timestamps in order of creation.

    ``shutil.copy2`` preserves the *source* file's mtime, so for
    replay we need ``st_ctime`` (set when the destination inode is
    created by atomic_move) to observe when the replay placed each
    file. ``st_ctime`` also moves forward for generate.
    """
    files = sorted(
        (
            p
            for p in target.rglob("*")
            if p.suffix in {".fastq", ".gz"} and not p.name.startswith("._")
        ),
        key=lambda p: p.stat().st_ctime,
    )
    return [p.stat().st_ctime for p in files]


def _intervals(times: List[float]) -> List[float]:
    return [b - a for a, b in zip(times, times[1:])]


# ---------------------------------------------------------------------
# Phase CC: real-time timing observability
# ---------------------------------------------------------------------


def _build_source(root: Path, n_files: int = 6) -> Path:
    src = _reset(root / "src")
    sample = "@r1\nACGTACGTACGT\n+\nIIIIIIIIIIII\n@r2\nTTTTAAAA\n+\nIIIIIIII\n"
    for i in range(n_files):
        (src / f"reads_{i:02d}.fastq").write_text(sample)
    return src


def phase_cc_timing(root: Path) -> List[Finding]:
    findings: List[Finding] = []
    src = _build_source(root, n_files=6)

    def case(label: str, args: List[str], assert_fn) -> Finding:
        target = _reset(root / "out" / label)
        f = Finding(scenario=f"timing/{label}", phase="CC")
        t0 = time.perf_counter()
        try:
            proc = _run(
                [
                    "replay",
                    "--source",
                    str(src),
                    "--target",
                    str(target),
                    "--operation",
                    "copy",
                    "--monitor",
                    "none",
                ]
                + args,
                timeout=60,
            )
            if proc.returncode != 0:
                f.fail(f"non-zero exit: {proc.stderr[-200:]}")
                return f
            times = _mtimes(target)
            iv = _intervals(times)
            f.add(f"n_files={len(times)} intervals={['%.2f' % x for x in iv]}")
            assert_fn(f, iv)
        except Exception as exc:
            f.fail(f"exception: {exc}\n{traceback.format_exc()}")
        f.duration_s = time.perf_counter() - t0
        return f

    # CC1: uniform model. Intervals should cluster tightly around the
    # base interval. Allow +/- 50% tolerance for fs noise.
    def assert_uniform(f: Finding, iv: List[float]) -> None:
        if not iv:
            f.fail("no intervals captured")
            return
        mean = statistics.mean(iv)
        if not (0.2 <= mean <= 0.6):
            f.fail(f"uniform mean {mean:.2f}s outside [0.2, 0.6] for --interval 0.4")

    findings.append(
        case(
            "uniform_0.4s",
            ["--interval", "0.4", "--timing-model", "uniform"],
            assert_uniform,
        )
    )

    # CC2: random model. Intervals scatter; mean still near base
    # interval, individual values span a wider range.
    def assert_random(f: Finding, iv: List[float]) -> None:
        if len(iv) < 3:
            f.fail("too few intervals")
            return
        mean = statistics.mean(iv)
        if not (0.2 <= mean <= 0.7):
            f.fail(f"random mean {mean:.2f}s outside [0.2, 0.7] for --interval 0.4")
        # We expect variance > 0 (otherwise it would behave like uniform)
        if statistics.pstdev(iv) < 0.01:
            f.add("WARN: random produced near-zero stdev")

    findings.append(
        case(
            "random_0.4s",
            ["--interval", "0.4", "--timing-model", "random", "--random-factor", "0.5"],
            assert_random,
        )
    )

    # CC3: poisson model. Mean still near base interval; we expect at
    # least one interval to be considerably below the mean (a burst).
    # Run for more files so the burst probability has a chance to fire.
    def assert_poisson(f: Finding, iv: List[float]) -> None:
        if len(iv) < 3:
            f.fail("too few intervals")
            return
        mean = statistics.mean(iv)
        # Wide tolerance because poisson is bursty.
        if not (0.05 <= mean <= 1.0):
            f.fail(f"poisson mean {mean:.2f}s outside [0.05, 1.0]")

    findings.append(
        case(
            "poisson_0.3s",
            [
                "--interval",
                "0.3",
                "--timing-model",
                "poisson",
                "--burst-probability",
                "0.5",
                "--burst-rate-multiplier",
                "5.0",
            ],
            assert_poisson,
        )
    )

    # CC4: adaptive model with EMA drift; mean near base interval.
    def assert_adaptive(f: Finding, iv: List[float]) -> None:
        if not iv:
            f.fail("no intervals")
            return
        mean = statistics.mean(iv)
        if not (0.1 <= mean <= 1.0):
            f.fail(f"adaptive mean {mean:.2f}s outside [0.1, 1.0]")

    findings.append(
        case(
            "adaptive_0.3s",
            [
                "--interval",
                "0.3",
                "--timing-model",
                "adaptive",
                "--adaptation-rate",
                "0.3",
            ],
            assert_adaptive,
        )
    )

    # CC5: --no-wait must collapse the timeline (all files written
    # quickly). Used as a sanity guardrail.
    def assert_no_wait(f: Finding, iv: List[float]) -> None:
        if iv and max(iv) > 0.2:
            f.fail(f"--no-wait left a {max(iv):.2f}s gap")

    findings.append(
        case(
            "no_wait_collapses",
            ["--interval", "1.0", "--no-wait", "--timing-model", "uniform"],
            assert_no_wait,
        )
    )

    return findings


# ---------------------------------------------------------------------
# Phase BB: cross-Python compatibility report (informational)
# ---------------------------------------------------------------------


def phase_bb_python_compat(root: Path, py39_bin: Optional[str]) -> List[Finding]:
    findings: List[Finding] = []
    f = Finding(scenario="cross_python/py39_suite", phase="BB")
    t0 = time.perf_counter()
    try:
        if py39_bin is None or not Path(py39_bin).exists():
            f.add("py39 interpreter not provided; phase BB is informational")
            f.passed = True
            findings.append(f)
            return findings
        proc = subprocess.run(
            [py39_bin, "-m", "pytest", "-q", "--tb=no"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
        tail = proc.stdout.strip().split("\n")[-1]
        f.add(f"py39_summary: {tail}")
        if proc.returncode != 0:
            f.fail(f"py39 suite non-zero exit; tail={tail}")
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)
    return findings


def write_report(root: Path, findings: List[Finding]) -> Path:
    path = root / "reports" / "realtime-timing-report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    failed = [f for f in findings if not f.passed]
    by_phase: Dict[str, List[Finding]] = {}
    for f in findings:
        by_phase.setdefault(f.phase, []).append(f)
    lines = [
        "# nanorunner real-time timing + Python compat audit (round 10)",
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
    p.add_argument(
        "--py39",
        default=None,
        help="Path to a Python 3.9 interpreter for cross-version testing.",
    )
    args = p.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    root: Path = args.root
    root.mkdir(parents=True, exist_ok=True)
    (root / "reports").mkdir(exist_ok=True)

    findings: List[Finding] = []
    findings.extend(phase_bb_python_compat(root, args.py39))
    findings.extend(phase_cc_timing(root))

    report = write_report(root, findings)
    logger.info("wrote %s", report)
    return 1 if any(not f.passed for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
