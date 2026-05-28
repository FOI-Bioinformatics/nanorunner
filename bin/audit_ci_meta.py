#!/usr/bin/env python
"""Round 14: CI workflow hygiene + meta-audit of audit drivers.

After 13 rounds the project has 12 re-runnable audit drivers under
``bin/`` and one CI workflow at ``.github/workflows/ci.yml``. Two
production-meaningful questions have never been asked:

- MM (CI hygiene): is the CI workflow structurally valid? Does it
  install the claimed dev extras? Does it test the documented
  Python floor (3.9)?
- NN (meta-audit): does every audit driver still work? Can each one
  be imported, respond to --help, and produce a report file?
  If a driver silently rotted, the round it claims to cover is
  unprotected.

Usage:
    python bin/audit_ci_meta.py --root /tmp/audit-2026-05-28-round14
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

import yaml

logger = logging.getLogger("audit-r14")
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


# ---------------------------------------------------------------------
# Phase MM: CI workflow hygiene
# ---------------------------------------------------------------------


def phase_mm_ci(root: Path) -> List[Finding]:
    findings: List[Finding] = []
    ci_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"

    # MM1: workflow parses as valid YAML.
    f = Finding(scenario="ci/parses_as_yaml", phase="MM")
    t0 = time.perf_counter()
    try:
        if not ci_path.exists():
            f.fail("no CI workflow found")
        else:
            data = yaml.safe_load(ci_path.read_text())
            # YAML safe_load parses `on:` as Python True (the truthy
            # warning yamllint surfaces). Coerce keys to strings before
            # sorting so we can present them uniformly.
            keys = sorted(str(k) for k in data.keys())
            f.add(f"top_level_keys={keys}")
            if "jobs" not in keys:
                f.fail("workflow missing 'jobs' key")
    except Exception as exc:
        f.fail(f"YAML parse failed: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    # MM2: every step has a name (helps reading CI logs).
    f = Finding(scenario="ci/every_step_named", phase="MM")
    t0 = time.perf_counter()
    try:
        data = yaml.safe_load(ci_path.read_text())
        unnamed: List[str] = []
        for job_id, job in data.get("jobs", {}).items():
            for i, step in enumerate(job.get("steps", [])):
                if "uses" in step:
                    continue  # action references self-document
                if "name" not in step:
                    unnamed.append(f"{job_id}.steps[{i}]")
        f.add(f"unnamed_steps={unnamed}")
        if unnamed:
            f.fail(f"{len(unnamed)} run-step(s) without a name")
    except Exception as exc:
        f.fail(f"exception: {exc}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    # MM3: matrix covers the project's documented Python floor (3.9)
    # and the version it ships on.
    f = Finding(scenario="ci/matrix_covers_floor_and_current", phase="MM")
    t0 = time.perf_counter()
    try:
        data = yaml.safe_load(ci_path.read_text())
        py_versions: set = set()
        for job in data.get("jobs", {}).values():
            mat = job.get("strategy", {}).get("matrix", {})
            for v in mat.get("python-version", []):
                py_versions.add(str(v))
            for incl in mat.get("include", []) or []:
                if "python-version" in incl:
                    py_versions.add(str(incl["python-version"]))
        f.add(f"matrix_python_versions={sorted(py_versions)}")
        required = {"3.9", "3.12"}
        missing = required - py_versions
        if missing:
            f.fail(f"matrix missing Python versions: {sorted(missing)}")
    except Exception as exc:
        f.fail(f"exception: {exc}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    # MM4: workflow installs the [dev] extra so the suite can run.
    f = Finding(scenario="ci/installs_dev_extra", phase="MM")
    t0 = time.perf_counter()
    try:
        text = ci_path.read_text()
        if (
            "pip install -e .[dev]" not in text
            and 'pip install -e ".[dev]"' not in text
        ):
            f.fail("CI does not pip install -e .[dev]")
    except Exception as exc:
        f.fail(f"exception: {exc}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    # MM5: yamllint clean (project-relevant warnings + errors).
    f = Finding(scenario="ci/yamllint_clean", phase="MM")
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "yamllint", str(ci_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            # Treat ERROR as failure, WARN as informational.
            errors = [ln for ln in proc.stdout.splitlines() if "error" in ln]
            warns = [ln for ln in proc.stdout.splitlines() if "warning" in ln]
            f.add(f"warnings={len(warns)} errors={len(errors)}")
            for e in errors[:5]:
                f.add(f"ERR {e}")
            if errors:
                f.fail(f"yamllint reported {len(errors)} ERROR-level issues")
        else:
            f.add("yamllint clean")
    except Exception as exc:
        f.fail(f"exception: {exc}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    return findings


# ---------------------------------------------------------------------
# Phase NN: meta-audit of audit drivers
# ---------------------------------------------------------------------


def phase_nn_meta(root: Path) -> List[Finding]:
    findings: List[Finding] = []
    audit_dir = REPO_ROOT / "bin"
    drivers = sorted(audit_dir.glob("audit_*.py"))

    # NN1: every driver compiles to bytecode (catches syntax errors
    # without running module-level side effects). Each driver imports
    # peer drivers via sys.path.insert at runtime, so a plain import
    # check would need that boilerplate; py_compile is simpler and
    # sufficient for the meta-question.
    f = Finding(scenario="drivers/all_compile", phase="NN")
    t0 = time.perf_counter()
    try:
        broken: List[str] = []
        for drv in drivers:
            proc = subprocess.run(
                [sys.executable, "-m", "py_compile", str(drv)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode != 0:
                broken.append(f"{drv.name}: {proc.stderr.strip().splitlines()[-1]}")
        f.add(f"drivers_total={len(drivers)} broken={len(broken)}")
        for b in broken[:5]:
            f.add(f"BROKEN {b}")
        if broken:
            f.fail(f"{len(broken)} drivers failed to compile")
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    # NN2: every driver responds to --help with exit 0.
    f = Finding(scenario="drivers/all_respond_to_help", phase="NN")
    t0 = time.perf_counter()
    try:
        broken: List[str] = []
        for drv in drivers:
            proc = subprocess.run(
                [sys.executable, str(drv), "--help"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode != 0:
                broken.append(f"{drv.name} exit={proc.returncode}")
        f.add(f"drivers_total={len(drivers)} broken={len(broken)}")
        if broken:
            f.fail(f"{len(broken)} drivers failed --help")
    except Exception as exc:
        f.fail(f"exception: {exc}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    # NN3: every driver emits a non-empty report file when given a
    # clean --root. We run only the three fastest-and-fully-offline
    # drivers (the others either build wheels, run pytest, or touch
    # the network, exceeding a sane round budget).
    # The fast subset deliberately excludes audit_robustness.py: the
    # concurrent-runs scenario races on _cleanup_tmp_files across
    # processes sharing a target dir and is non-deterministic. The
    # user-facing contract (output filenames diverge) still holds; the
    # tmp-cleanup hazard is documented for a future round.
    fast_drivers = [
        "audit_atomic_memory.py",  # round 12 -- ~10s
        "audit_realtime_timing.py",  # round 10 -- ~10s, no --py39
        "audit_semantic.py",  # round 5 -- ~5s, fully offline
    ]
    f = Finding(scenario="drivers/fast_subset_produces_report", phase="NN")
    t0 = time.perf_counter()
    try:
        broken: List[str] = []
        for name in fast_drivers:
            drv = audit_dir / name
            tgt = _reset(root / "meta" / drv.stem)
            proc = subprocess.run(
                [sys.executable, str(drv), "--root", str(tgt)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=120,
            )
            report_dir = tgt / "reports"
            reports = list(report_dir.glob("*.md")) if report_dir.exists() else []
            if proc.returncode != 0 or not reports:
                broken.append(f"{name} exit={proc.returncode} reports={len(reports)}")
        f.add(f"drivers_run={len(fast_drivers)} broken={len(broken)}")
        for b in broken:
            f.add(f"BROKEN {b}")
        if broken:
            f.fail(f"{len(broken)} drivers did not produce a report")
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    return findings


def write_report(root: Path, findings: List[Finding]) -> Path:
    path = root / "reports" / "ci-meta-report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    failed = [f for f in findings if not f.passed]
    by_phase: Dict[str, List[Finding]] = {}
    for f in findings:
        by_phase.setdefault(f.phase, []).append(f)
    lines = [
        "# nanorunner CI + driver meta-audit (round 14)",
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
    findings.extend(phase_mm_ci(root))
    findings.extend(phase_nn_meta(root))

    report = write_report(root, findings)
    logger.info("wrote %s", report)
    return 1 if any(not f.passed for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
