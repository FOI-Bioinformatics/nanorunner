#!/usr/bin/env python
"""Round 6 audit: documented examples + scalability sanity.

Phase P: run every script under ``examples/`` and verify it exits 0,
producing the documented behavior. These scripts are explicit user
documentation -- if any have rotted with API changes, that is a
production-readiness regression.

Phase Q: throw production-scale workloads at generate and replay
(thousands of reads across many barcodes) and verify completion time,
exit code, and output integrity stay sane.

Usage:
    python bin/audit_examples_scale.py \
        --root /Volumes/LaCie/nanorunner/audit-2026-05-27-round6
    # Optional: skip the network-dependent example
    python bin/audit_examples_scale.py --root ... --no-network
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_simulate_replay import (  # noqa: E402
    _collect_fastq,
    _read_count,
    _synthetic_fasta_for,
)

logger = logging.getLogger("audit-r6")
NANORUNNER = "nanorunner"
REPO_ROOT = Path(__file__).resolve().parent.parent

# Scripts that touch the network or external CLIs.
NETWORK_EXAMPLES = {"06_practical_genome_test.py"}


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


# ---------------------------------------------------------------------
# Phase P: documented examples
# ---------------------------------------------------------------------


def phase_p_examples(root: Path, skip_network: bool) -> List[Finding]:
    findings: List[Finding] = []
    examples_dir = REPO_ROOT / "examples"
    scripts = sorted(p for p in examples_dir.glob("*.py") if p.is_file())
    for script in scripts:
        scenario = f"examples/{script.name}"
        f = Finding(scenario=scenario, phase="P")
        if skip_network and script.name in NETWORK_EXAMPLES:
            f.add("network-dependent example; skipped (--no-network)")
            findings.append(f)
            continue
        t0 = time.perf_counter()
        try:
            # Most examples create their own tempdirs; we still cap
            # runtime aggressively so a hung script does not stall.
            proc = subprocess.run(
                [sys.executable, str(script)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=300,
            )
            f.add(f"exit={proc.returncode}")
            if proc.returncode != 0:
                tail = (proc.stderr or proc.stdout)[-400:]
                f.fail(f"non-zero exit: {tail!r}")
            else:
                # Sanity: stdout should not be empty (every example prints
                # at least a heading or summary).
                if not (proc.stdout.strip() or proc.stderr.strip()):
                    f.fail("example produced no output at all")
        except subprocess.TimeoutExpired:
            f.fail("example timed out (300s)")
        except Exception as exc:
            f.fail(f"exception: {exc}\n{traceback.format_exc()}")
        f.duration_s = time.perf_counter() - t0
        findings.append(f)
        logger.info(
            "%s -> %s (%.1fs)", scenario, "OK" if f.passed else "FAIL", f.duration_s
        )
    return findings


# ---------------------------------------------------------------------
# Phase Q: scalability sanity
# ---------------------------------------------------------------------


def _run(args, timeout=600):
    return subprocess.run(
        [NANORUNNER, *args], capture_output=True, text=True, timeout=timeout
    )


def phase_q_scale(root: Path) -> List[Finding]:
    findings: List[Finding] = []
    genomes = [
        _synthetic_fasta_for(name, root)
        for name in ("ecoliK12", "bsubtilis168", "saureusNCTC")
    ]

    def case(
        label: str,
        override: List[str],
        deadline_s: float,
        expect_files: Optional[int] = None,
        expect_reads: Optional[int] = None,
        use_parallel: bool = False,
        timeout: int = 600,
    ):
        scenario = f"scale/{label}"
        target = _reset(root / "q_scale" / label)
        f = Finding(scenario=scenario, phase="Q")
        t0 = time.perf_counter()
        try:
            args = [
                "generate",
                "--target",
                str(target),
                *sum([["--genomes", str(g)] for g in genomes], []),
                "--no-wait",
                "--monitor",
                "none",
                "--generator-backend",
                "builtin",
                "--output-format",
                "fastq.gz",
            ] + override
            if use_parallel:
                args += ["--parallel", "--worker-count", "4"]
            proc = _run(args, timeout=timeout)
            elapsed = time.perf_counter() - t0
            f.add(f"exit={proc.returncode} elapsed={elapsed:.1f}s")
            if proc.returncode != 0:
                f.fail(f"non-zero exit: {proc.stderr[-300:]}")
            elif elapsed > deadline_s:
                f.fail(f"exceeded deadline {deadline_s}s (took {elapsed:.1f}s)")
            files = _collect_fastq(target)
            f.add(f"files={len(files)}")
            if expect_files is not None and len(files) != expect_files:
                f.fail(f"expected {expect_files} files, got {len(files)}")
            if expect_reads is not None:
                total = sum(_read_count(p) for p in files)
                f.add(f"reads={total}")
                if total != expect_reads:
                    f.fail(f"expected {expect_reads} reads, got {total}")
        except subprocess.TimeoutExpired:
            f.fail(f"timed out after {timeout}s")
        except Exception as exc:
            f.fail(f"exception: {exc}\n{traceback.format_exc()}")
        f.duration_s = time.perf_counter() - t0
        findings.append(f)
        logger.info(
            "%s -> %s (%.1fs)", scenario, "OK" if f.passed else "FAIL", f.duration_s
        )

    # Q1: 5,000 reads across 3 barcodes, default chunking. Per-barcode
    # is ~1667 reads = 17 files of <=100, total 51 files.
    case(
        "5k_reads_multiplex",
        [
            "--read-count",
            "5000",
            "--reads-per-file",
            "100",
            "--mean-read-length",
            "2000",
            "--force-structure",
            "multiplex",
        ],
        deadline_s=60.0,
        expect_files=51,
        expect_reads=5000,
    )

    # Q2: same but parallel -- should not be slower, and totals must
    # still be exact.
    case(
        "5k_reads_multiplex_parallel",
        [
            "--read-count",
            "5000",
            "--reads-per-file",
            "100",
            "--mean-read-length",
            "2000",
            "--force-structure",
            "multiplex",
            "--batch-size",
            "4",
        ],
        deadline_s=60.0,
        expect_reads=5000,
        use_parallel=True,
    )

    # Q3: fine-grained chunking stresses the per-file overhead
    case(
        "fine_chunking_5_per_file",
        [
            "--read-count",
            "1000",
            "--reads-per-file",
            "5",
            "--mean-read-length",
            "1000",
            "--force-structure",
            "multiplex",
        ],
        deadline_s=60.0,
        expect_reads=1000,
    )

    # Q4: replay round-trip at scale
    src = root / "q_scale" / "5k_reads_multiplex"
    if src.exists() and any(src.iterdir()):
        scenario = "scale/replay_5k_roundtrip"
        target = _reset(root / "q_scale" / "replay_5k")
        f = Finding(scenario=scenario, phase="Q")
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
                    "--no-wait",
                    "--monitor",
                    "none",
                ],
                timeout=600,
            )
            elapsed = time.perf_counter() - t0
            f.add(f"exit={proc.returncode} elapsed={elapsed:.1f}s")
            if proc.returncode != 0:
                f.fail(f"non-zero exit: {proc.stderr[-300:]}")
            elif elapsed > 60.0:
                f.fail(f"exceeded deadline 60s (took {elapsed:.1f}s)")
            files = _collect_fastq(target)
            total = sum(_read_count(p) for p in files)
            f.add(f"files={len(files)} reads={total}")
            if total != 5000:
                f.fail(f"replay dropped reads: 5000 -> {total}")
        except Exception as exc:
            f.fail(f"exception: {exc}\n{traceback.format_exc()}")
        f.duration_s = time.perf_counter() - t0
        findings.append(f)

    return findings


def write_report(root: Path, findings: List[Finding]) -> Path:
    path = root / "reports" / "examples-scale-report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    failed = [f for f in findings if not f.passed]
    by_phase: Dict[str, List[Finding]] = {}
    for f in findings:
        by_phase.setdefault(f.phase, []).append(f)
    lines = [
        "# nanorunner examples + scalability audit (round 6)",
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
        "--no-network",
        action="store_true",
        help="Skip network-dependent examples (06_practical_genome_test.py)",
    )
    args = p.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    root: Path = args.root
    root.mkdir(parents=True, exist_ok=True)
    (root / "reports").mkdir(exist_ok=True)

    findings: List[Finding] = []
    findings.extend(phase_p_examples(root, skip_network=args.no_network))
    findings.extend(phase_q_scale(root))

    report = write_report(root, findings)
    logger.info("wrote %s", report)
    return 1 if any(not f.passed for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
