#!/usr/bin/env python
"""Round 4 robustness audit for nanorunner.

Stresses the production paths the previous rounds did not cover:
signal handling mid-run, generate->replay round-trip identity,
unusual filenames, concurrent target writes, source mutation
mid-replay, and permission-denied target paths.

Usage:
    python bin/audit_robustness.py \
        --root /Volumes/LaCie/nanorunner/audit-2026-05-27-round4

Exits non-zero on any failure.
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
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

logger = logging.getLogger("audit-r4")
NANORUNNER = "nanorunner"


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


def _reset(p: Path) -> Path:
    if p.exists():
        shutil.rmtree(p, ignore_errors=True)
    p.mkdir(parents=True)
    return p


def _run(args, timeout=180, **kw):
    return subprocess.run(
        [NANORUNNER, *args], capture_output=True, text=True, timeout=timeout, **kw
    )


# ---------------------------------------------------------------------
# Phase G: round-trip identity
# ---------------------------------------------------------------------


def phase_g_roundtrip(root: Path, genomes: List[Path]) -> List[Finding]:
    """Generate, then replay the generated output and verify the read
    count is preserved across the cycle."""
    findings: List[Finding] = []
    scenario = "roundtrip/generate_then_replay"
    gen_target = _reset(root / "g_roundtrip" / "gen")
    rep_target = _reset(root / "g_roundtrip" / "rep")
    f = Finding(scenario=scenario, phase="G")
    t0 = time.perf_counter()
    try:
        gen_args = [
            "generate",
            "--target",
            str(gen_target),
            *sum([["--genomes", str(g)] for g in genomes], []),
            "--read-count",
            "150",
            "--reads-per-file",
            "25",
            "--mean-read-length",
            "1500",
            "--no-wait",
            "--monitor",
            "none",
            "--generator-backend",
            "builtin",
            "--force-structure",
            "multiplex",
        ]
        proc = _run(gen_args, timeout=120)
        if proc.returncode != 0:
            f.fail(f"generate failed: {proc.stderr[-300:]}")
            f.duration_s = time.perf_counter() - t0
            findings.append(f)
            return findings
        gen_total = sum(_read_count(p) for p in _collect_fastq(gen_target))

        rep_args = [
            "replay",
            "--source",
            str(gen_target),
            "--target",
            str(rep_target),
            "--operation",
            "copy",
            "--no-wait",
            "--monitor",
            "none",
        ]
        proc = _run(rep_args, timeout=120)
        if proc.returncode != 0:
            f.fail(f"replay failed: {proc.stderr[-300:]}")
        rep_total = sum(_read_count(p) for p in _collect_fastq(rep_target))
        f.add(f"gen={gen_total} rep={rep_total}")
        if gen_total != rep_total:
            f.fail("round-trip read count drift")
        if gen_total != 150:
            f.fail(f"generate read count wrong: {gen_total}")
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    # Round-trip via reshape (barcoded source -> flat -> back to barcoded)
    scenario2 = "roundtrip/reshape_chain"
    flat_target = _reset(root / "g_roundtrip" / "rep_flat")
    bar_target = _reset(root / "g_roundtrip" / "rep_bar")
    f = Finding(scenario=scenario2, phase="G")
    t0 = time.perf_counter()
    try:
        proc = _run(
            [
                "replay",
                "--source",
                str(gen_target),
                "--target",
                str(flat_target),
                "--operation",
                "copy",
                "--no-wait",
                "--monitor",
                "none",
                "--output-structure",
                "flat",
                "--reads-per-file",
                "25",
            ],
            timeout=120,
        )
        if proc.returncode != 0:
            f.fail(f"flat replay failed: {proc.stderr[-300:]}")
        proc = _run(
            [
                "replay",
                "--source",
                str(flat_target),
                "--target",
                str(bar_target),
                "--operation",
                "copy",
                "--no-wait",
                "--monitor",
                "none",
                "--output-structure",
                "barcoded",
                "--output-barcodes",
                "3",
                "--reads-per-file",
                "25",
            ],
            timeout=120,
        )
        if proc.returncode != 0:
            f.fail(f"barcoded replay failed: {proc.stderr[-300:]}")
        chain_total = sum(_read_count(p) for p in _collect_fastq(bar_target))
        f.add(f"chained_total={chain_total}")
        if chain_total != gen_total:
            f.fail(f"reshape chain dropped reads: {gen_total} -> {chain_total}")
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)
    return findings


# ---------------------------------------------------------------------
# Phase H: unusual filenames
# ---------------------------------------------------------------------


def phase_h_unusual_filenames(root: Path) -> List[Finding]:
    """Source files with spaces, dots, and unicode characters in their
    names should still be replayable."""
    findings: List[Finding] = []
    src = _reset(root / "h_filenames" / "src")
    tgt = _reset(root / "h_filenames" / "tgt")
    sample = "@r1\nACGTACGT\n+\nIIIIIIII\n@r2\nTTTTTTTT\n+\nIIIIIIII\n"
    weird_names = [
        "reads with spaces.fastq",
        "reads.with.dots.fastq",
        "reads-é-unicode.fastq",
        "reads(parens).fastq.gz",
    ]
    import gzip

    for name in weird_names:
        p = src / name
        if name.endswith(".gz"):
            with gzip.open(p, "wt") as fh:
                fh.write(sample)
        else:
            p.write_text(sample)
    f = Finding(scenario="filenames/replay_weird_names", phase="H")
    t0 = time.perf_counter()
    try:
        proc = _run(
            [
                "replay",
                "--source",
                str(src),
                "--target",
                str(tgt),
                "--operation",
                "copy",
                "--no-wait",
                "--monitor",
                "none",
            ],
            timeout=60,
        )
        if proc.returncode != 0:
            f.fail(f"replay failed: {proc.stderr[-400:]}")
        out = _collect_fastq(tgt)
        f.add(f"input_files={len(weird_names)} output_files={len(out)}")
        if len(out) != len(weird_names):
            f.fail(f"missing outputs: {[p.name for p in out]}")
        total = sum(_read_count(p) for p in out)
        if total != 2 * len(weird_names):
            f.fail(f"read count drift: expected {2*len(weird_names)} got {total}")
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)
    return findings


# ---------------------------------------------------------------------
# Phase I: SIGTERM mid-run cleanup
# ---------------------------------------------------------------------


def phase_i_sigterm(root: Path, genomes: List[Path]) -> List[Finding]:
    """Send SIGTERM to a running generate process and verify it exits
    cleanly without leaving partial files."""
    findings: List[Finding] = []
    f = Finding(scenario="signal/sigterm_clean_shutdown", phase="I")
    t0 = time.perf_counter()
    target = _reset(root / "i_signal" / "tgt")
    try:
        proc = subprocess.Popen(
            [
                NANORUNNER,
                "generate",
                "--target",
                str(target),
                *sum([["--genomes", str(g)] for g in genomes], []),
                "--read-count",
                "300",
                "--reads-per-file",
                "10",
                "--mean-read-length",
                "1500",
                "--interval",
                "0.2",
                "--monitor",
                "none",
                "--generator-backend",
                "builtin",
                "--force-structure",
                "multiplex",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        # Let it produce a few files, then SIGTERM.
        time.sleep(1.5)
        proc.send_signal(signal.SIGTERM)
        try:
            stdout, stderr = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            f.fail("process did not exit within 15s after SIGTERM")
            f.duration_s = time.perf_counter() - t0
            findings.append(f)
            return findings
        f.add(f"exit={proc.returncode}")
        # nanorunner converts SIGTERM to KeyboardInterrupt; typer maps to 130.
        if proc.returncode == 0:
            f.fail("process exited 0 on SIGTERM; should be non-zero")
        # Check for partial / temp files left behind.
        tmp_files = list(target.rglob(".*.tmp"))
        f.add(f"leftover_tmp={len(tmp_files)}")
        if tmp_files:
            f.fail(f"temp files remained: {[str(p) for p in tmp_files]}")
        # Existing fastq outputs should still be parseable.
        for fq in _collect_fastq(target):
            try:
                _read_count(fq)
            except Exception as exc:
                f.fail(f"corrupted output {fq.name}: {exc}")
                break
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)
    return findings


# ---------------------------------------------------------------------
# Phase J: concurrent writers to same target
# ---------------------------------------------------------------------


def phase_j_concurrent(root: Path, genomes: List[Path]) -> List[Finding]:
    """Two simultaneous generate runs writing into the same target dir
    must not corrupt each other's output. Names should diverge so they
    don't clobber.

    Known flakiness: nanopore_simulator.runner._cleanup_tmp_files wipes
    every ``*.tmp`` under ``target_dir`` in its finally block. With two
    concurrent processes sharing a target dir, one process can wipe
    the other's in-flight tmp file mid-atomic_move and the second
    process's run aborts. The user-facing output-files-don't-clobber
    invariant still holds, but the test as written can fail under
    unfavourable timing. A proper fix scopes the cleanup to files
    known to this process; recorded for a future round.
    """
    findings: List[Finding] = []
    f = Finding(scenario="concurrent/two_generates_same_target", phase="J")
    t0 = time.perf_counter()
    target = _reset(root / "j_concurrent" / "tgt")
    try:

        def runner(g_subset):
            return subprocess.run(
                [
                    NANORUNNER,
                    "generate",
                    "--target",
                    str(target),
                    *sum([["--genomes", str(g)] for g in g_subset], []),
                    "--read-count",
                    "60",
                    "--reads-per-file",
                    "20",
                    "--mean-read-length",
                    "1500",
                    "--no-wait",
                    "--monitor",
                    "none",
                    "--generator-backend",
                    "builtin",
                    "--force-structure",
                    "singleplex",
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )

        # Two runs using two different genomes so target filenames diverge
        # (BuiltinGenerator names files <genome_stem>_reads_NNNN.ext).
        results = []
        threads = []
        for g in (genomes[0], genomes[1]):
            t = threading.Thread(target=lambda gg=g: results.append(runner([gg])))
            threads.append(t)
            t.start()
        for t in threads:
            t.join(timeout=120)
        if any(r.returncode != 0 for r in results):
            stderrs = "\n".join(r.stderr[-200:] for r in results)
            f.fail(f"concurrent run failures: {stderrs}")
        files = _collect_fastq(target)
        total = sum(_read_count(p) for p in files)
        f.add(f"files={len(files)} reads={total}")
        # 2 runs x 60 reads = 120
        if total != 120:
            f.fail(f"expected 120 reads, got {total}")
        # No half-written tmp files
        leftovers = list(target.rglob(".*.tmp"))
        if leftovers:
            f.fail(f"tmp leftovers: {leftovers}")
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)
    return findings


# ---------------------------------------------------------------------
# Phase K: source mutation mid-replay
# ---------------------------------------------------------------------


def phase_k_source_mutation(root: Path) -> List[Finding]:
    """Removing a source FASTQ between manifest build and execute must
    not crash the run (replay should either skip with warning, or
    fail with a useful message -- not raise an unhandled exception)."""
    findings: List[Finding] = []
    f = Finding(scenario="source_mutation/file_removed_mid_replay", phase="K")
    t0 = time.perf_counter()
    src = _reset(root / "k_mutation" / "src")
    tgt = _reset(root / "k_mutation" / "tgt")
    sample = "@r\nACGT\n+\nIIII\n"
    for i in range(4):
        (src / f"reads_{i}.fastq").write_text(sample)
    try:
        proc = subprocess.Popen(
            [
                NANORUNNER,
                "replay",
                "--source",
                str(src),
                "--target",
                str(tgt),
                "--operation",
                "copy",
                "--interval",
                "0.5",
                "--monitor",
                "none",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        time.sleep(0.3)
        # Remove one source file mid-stream
        victim = src / "reads_2.fastq"
        if victim.exists():
            victim.unlink()
        try:
            stdout, stderr = proc.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
            f.fail("replay hung after source removal")
            f.duration_s = time.perf_counter() - t0
            findings.append(f)
            return findings
        f.add(f"exit={proc.returncode}")
        if proc.returncode == 0:
            # Acceptable: replay tolerates / skips missing file.
            # Check no crash text in stderr.
            if "Traceback" in stderr:
                f.fail(f"unhandled traceback: {stderr[-400:]}")
        else:
            # Acceptable: replay surfaces a clean error.
            if "Traceback" in stderr:
                f.fail(f"unhandled traceback: {stderr[-400:]}")
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)
    return findings


# ---------------------------------------------------------------------
# Phase L: permission denied on target
# ---------------------------------------------------------------------


def phase_l_permission_denied(root: Path) -> List[Finding]:
    """Target dir made read-only mid-run must produce a clean error,
    not a traceback. We make the target unwritable BEFORE the run."""
    findings: List[Finding] = []
    f = Finding(scenario="permission/target_readonly", phase="L")
    t0 = time.perf_counter()
    import tempfile

    # exFAT volumes (some external drives) silently ignore chmod, so
    # the test must run on a permission-enforcing filesystem. Use the
    # platform temp dir which is HFS+/APFS on macOS and ext on Linux.
    workdir = Path(tempfile.mkdtemp(prefix="nanorunner_perm_"))
    src = _reset(workdir / "src")
    tgt = _reset(workdir / "tgt")
    (src / "reads_0.fastq").write_text("@r\nACGT\n+\nIIII\n")
    try:
        os.chmod(tgt, 0o555)
        # Verify chmod actually stuck (filesystem honors permissions).
        probe = tgt / ".chmod_probe"
        try:
            probe.write_text("x")
            # Chmod did not take effect -> skip the test as inconclusive
            probe.unlink()
            f.add("filesystem ignores chmod; skipped")
            f.duration_s = time.perf_counter() - t0
            findings.append(f)
            shutil.rmtree(workdir, ignore_errors=True)
            return findings
        except PermissionError:
            pass
        proc = _run(
            [
                "replay",
                "--source",
                str(src),
                "--target",
                str(tgt),
                "--operation",
                "copy",
                "--no-wait",
                "--monitor",
                "none",
            ],
            timeout=30,
        )
        f.add(f"exit={proc.returncode}")
        if proc.returncode == 0:
            f.fail("expected non-zero exit on read-only target")
        if "Traceback" in proc.stderr and "Permission" not in proc.stderr:
            f.fail(f"unhandled traceback: {proc.stderr[-400:]}")
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    finally:
        try:
            os.chmod(tgt, 0o755)  # restore so cleanup works
        except OSError:
            pass
        shutil.rmtree(workdir, ignore_errors=True)
    f.duration_s = time.perf_counter() - t0
    findings.append(f)
    return findings


# ---------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------


def write_report(root: Path, findings: List[Finding]) -> Path:
    path = root / "reports" / "robustness-report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    failed = [f for f in findings if not f.passed]
    by_phase: Dict[str, List[Finding]] = {}
    for f in findings:
        by_phase.setdefault(f.phase, []).append(f)
    lines = [
        "# nanorunner robustness audit (round 4)",
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

    genomes = [
        _synthetic_fasta_for(name, root)
        for name in ("ecoliK12", "bsubtilis168", "saureusNCTC")
    ]

    findings: List[Finding] = []
    findings.extend(phase_g_roundtrip(root, genomes))
    findings.extend(phase_h_unusual_filenames(root))
    findings.extend(phase_i_sigterm(root, genomes))
    findings.extend(phase_j_concurrent(root, genomes))
    findings.extend(phase_k_source_mutation(root))
    findings.extend(phase_l_permission_denied(root))

    report = write_report(root, findings)
    logger.info("wrote %s", report)
    return 1 if any(not f.passed for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
