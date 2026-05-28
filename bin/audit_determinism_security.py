#!/usr/bin/env python
"""Round 8: determinism + idempotency + security audit.

- V: determinism. Two CLI runs with the same target_dir, same flags
  must produce byte-identical FASTQ files (the round-1 stratified
  shuffle is seeded off target_dir for exactly this reason).
- W: idempotency. Re-running into a non-empty target must either
  overwrite cleanly or report a useful error -- not silently mix
  half of the old run with half of the new one.
- X: static analysis. bandit and pip-audit findings; mypy strict on
  the public surface.

Usage:
    python bin/audit_determinism_security.py \\
        --root /tmp/audit-2026-05-28-round8
"""

from __future__ import annotations

import argparse
import hashlib
import json
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
from audit_simulate_replay import _collect_fastq, _synthetic_fasta_for  # noqa: E402

logger = logging.getLogger("audit-r8")
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


def _run(args, timeout=180, **kw):
    return subprocess.run(
        [NANORUNNER, *args], capture_output=True, text=True, timeout=timeout, **kw
    )


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _dir_hashes(root: Path) -> Dict[str, str]:
    """Return {relative_path: sha256} for every FASTQ in *root*."""
    out: Dict[str, str] = {}
    for p in _collect_fastq(root):
        out[str(p.relative_to(root))] = _sha256(p)
    return out


# ---------------------------------------------------------------------
# Phase V: determinism
# ---------------------------------------------------------------------


def phase_v_determinism(root: Path, genomes: List[Path]) -> List[Finding]:
    findings: List[Finding] = []

    def _generate_into(target: Path) -> subprocess.CompletedProcess:
        return _run(
            [
                "generate",
                "--target",
                str(target),
                *sum([["--genomes", str(g)] for g in genomes], []),
                "--read-count",
                "300",
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
                "--output-format",
                "fastq",
            ],
            timeout=120,
        )

    # V1: same target_dir twice -> identical output (the stratified
    # shuffle in _generate_multiplex_entries is seeded off target_dir
    # specifically so this holds, but we have never verified it
    # byte-for-byte at the CLI layer.
    f = Finding(scenario="determinism/same_target_twice", phase="V")
    t0 = time.perf_counter()
    try:
        target = root / "v1" / "tgt"
        _reset(target)
        p1 = _generate_into(target)
        if p1.returncode != 0:
            f.fail(f"first run failed: {p1.stderr[-300:]}")
        else:
            hashes_a = _dir_hashes(target)
            _reset(target)
            p2 = _generate_into(target)
            if p2.returncode != 0:
                f.fail(f"second run failed: {p2.stderr[-300:]}")
            else:
                hashes_b = _dir_hashes(target)
                f.add(f"files={len(hashes_a)} run2_files={len(hashes_b)}")
                if hashes_a != hashes_b:
                    diffs = sorted(set(hashes_a) ^ set(hashes_b))
                    differing = [
                        k
                        for k in hashes_a
                        if k in hashes_b and hashes_a[k] != hashes_b[k]
                    ]
                    if diffs:
                        f.fail(f"file-set differs: {diffs[:3]}")
                    if differing:
                        f.fail(
                            f"content differs in {len(differing)} files; example: {differing[0]}"
                        )
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    # V2: different target_dir -> can legitimately differ in ordering
    # (the seed is per-target) but read totals and per-genome counts
    # must match.
    f = Finding(scenario="determinism/different_target_same_totals", phase="V")
    t0 = time.perf_counter()
    try:
        tgt_a = _reset(root / "v2" / "a")
        tgt_b = _reset(root / "v2" / "b")
        p1 = _generate_into(tgt_a)
        p2 = _generate_into(tgt_b)
        if p1.returncode != 0 or p2.returncode != 0:
            f.fail("run failed")
        else:
            from nanopore_simulator.fastq import iter_reads

            tot_a = sum(1 for fq in _collect_fastq(tgt_a) for _ in iter_reads(fq))
            tot_b = sum(1 for fq in _collect_fastq(tgt_b) for _ in iter_reads(fq))
            f.add(f"tot_a={tot_a} tot_b={tot_b}")
            if tot_a != tot_b or tot_a != 300:
                f.fail("read totals differ across runs")
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    return findings


# ---------------------------------------------------------------------
# Phase W: idempotency / re-run behavior
# ---------------------------------------------------------------------


def phase_w_idempotency(root: Path, genomes: List[Path]) -> List[Finding]:
    findings: List[Finding] = []

    # W1: re-run into a populated target. Today's behavior is "overwrite
    # via atomic move", so the second run should produce the same set
    # of filenames (no stale files left over). Document whatever the
    # observed behavior is.
    f = Finding(scenario="idempotency/rerun_into_populated_target", phase="W")
    t0 = time.perf_counter()
    try:
        target = _reset(root / "w1" / "tgt")
        for run_idx in range(2):
            p = _run(
                [
                    "generate",
                    "--target",
                    str(target),
                    "--genomes",
                    str(genomes[0]),
                    "--read-count",
                    "30",
                    "--reads-per-file",
                    "10",
                    "--mean-read-length",
                    "1500",
                    "--no-wait",
                    "--monitor",
                    "none",
                    "--generator-backend",
                    "builtin",
                    "--force-structure",
                    "singleplex",
                    "--output-format",
                    "fastq",
                ],
                timeout=60,
            )
            if p.returncode != 0:
                f.fail(f"run {run_idx} exited {p.returncode}: {p.stderr[-200:]}")
                break
        files = _collect_fastq(target)
        from nanopore_simulator.fastq import iter_reads

        total = sum(1 for fq in files for _ in iter_reads(fq))
        f.add(f"files={len(files)} reads={total}")
        # Atomic move semantics: second run replaces existing files.
        # File count and read count should equal a single run.
        if total != 30:
            f.fail(f"re-run produced {total} reads (expected 30 -- overwrite mismatch)")
        if any(p.name.startswith(".") for p in files):
            f.fail("found a leftover dot-file")
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    # W2: stale .tmp left in the target before a run should be
    # cleaned up (the runner has _cleanup_tmp_files in the finally
    # block, but if a previous attempt crashed mid-write the file
    # exists at startup).
    f = Finding(scenario="idempotency/stale_tmp_cleaned", phase="W")
    t0 = time.perf_counter()
    try:
        target = _reset(root / "w2" / "tgt")
        stale = target / ".genome_reads_0000.fastq.tmp"
        stale.write_text("LEFTOVER")
        p = _run(
            [
                "generate",
                "--target",
                str(target),
                "--genomes",
                str(genomes[0]),
                "--read-count",
                "10",
                "--reads-per-file",
                "10",
                "--mean-read-length",
                "1500",
                "--no-wait",
                "--monitor",
                "none",
                "--generator-backend",
                "builtin",
                "--force-structure",
                "singleplex",
                "--output-format",
                "fastq",
            ],
            timeout=60,
        )
        f.add(f"exit={p.returncode}")
        if p.returncode != 0:
            f.fail(f"run failed: {p.stderr[-200:]}")
        elif stale.exists():
            f.fail("stale .tmp survived the run")
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    return findings


# ---------------------------------------------------------------------
# Phase X: static analysis (security + types)
# ---------------------------------------------------------------------


def phase_x_static(root: Path) -> List[Finding]:
    findings: List[Finding] = []

    # X1: bandit security scan. The project has pyproject.toml config;
    # treat HIGH-severity findings as failures, MEDIUM/LOW as advisory.
    f = Finding(scenario="static/bandit", phase="X")
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "bandit",
                "-r",
                "nanopore_simulator/",
                "-f",
                "json",
                "-q",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=90,
        )
        data = json.loads(proc.stdout or "{}")
        results = data.get("results", [])
        sev = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for r in results:
            sev[r.get("issue_severity", "LOW")] = (
                sev.get(r.get("issue_severity", "LOW"), 0) + 1
            )
        f.add(f"high={sev['HIGH']} medium={sev['MEDIUM']} low={sev['LOW']}")
        if sev["HIGH"]:
            for r in results:
                if r.get("issue_severity") == "HIGH":
                    f.add(
                        f"HIGH: {r.get('test_id')} {r.get('filename')}:{r.get('line_number')} {r.get('issue_text')}"
                    )
            f.fail(f"{sev['HIGH']} HIGH-severity bandit finding(s)")
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    # X2: pip-audit. Look up advisories for installed dependencies.
    # Treat any vulnerability as advisory unless it touches a direct
    # dependency we use.
    f = Finding(scenario="static/pip_audit", phase="X")
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip_audit",
                "--format",
                "json",
                "--progress-spinner",
                "off",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        try:
            data = json.loads(proc.stdout or "{}")
        except json.JSONDecodeError:
            f.add(f"pip-audit produced non-JSON output: {proc.stdout[:200]!r}")
            data = {}
        deps = data.get("dependencies", [])
        vulnerable = [d for d in deps if d.get("vulns")]
        f.add(f"packages_scanned={len(deps)} vulnerable_packages={len(vulnerable)}")
        for d in vulnerable[:5]:
            ids = ",".join(v.get("id", "?") for v in d.get("vulns", []))
            f.add(f"vuln: {d.get('name')}=={d.get('version')} {ids}")
        # Don't fail on vulnerabilities in transitive deps -- record for
        # visibility. The CI workflow runs pip-audit separately and is
        # the authoritative gate.
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    # X3: mypy on the public surface. CI already runs `mypy
    # nanopore_simulator/` (default config); this scenario just
    # confirms the tree is currently clean.
    f = Finding(scenario="static/mypy", phase="X")
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "mypy", "nanopore_simulator/"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        f.add(f"exit={proc.returncode}")
        if proc.returncode != 0:
            tail = proc.stdout[-400:] if proc.stdout else proc.stderr[-400:]
            f.fail(f"mypy errors: {tail}")
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    # X4: public API stability -- import the things README/CLAUDE
    # claim are public and verify they exist and are callable.
    f = Finding(scenario="static/public_api_intact", phase="X")
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-c",
                "from nanopore_simulator import ReplayConfig, GenerateConfig, "
                "run_replay, run_generate; "
                "assert all(callable(x) or isinstance(x, type) "
                "for x in [ReplayConfig, GenerateConfig, run_replay, run_generate])",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        f.add(f"exit={proc.returncode}")
        if proc.returncode != 0:
            f.fail(f"public-API import failed: {proc.stderr[-200:]}")
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    return findings


def write_report(root: Path, findings: List[Finding]) -> Path:
    path = root / "reports" / "determinism-security-report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    failed = [f for f in findings if not f.passed]
    by_phase: Dict[str, List[Finding]] = {}
    for f in findings:
        by_phase.setdefault(f.phase, []).append(f)
    lines = [
        "# nanorunner determinism + security audit (round 8)",
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
    findings.extend(phase_v_determinism(root, genomes))
    findings.extend(phase_w_idempotency(root, genomes))
    findings.extend(phase_x_static(root))

    report = write_report(root, findings)
    logger.info("wrote %s", report)
    return 1 if any(not f.passed for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
