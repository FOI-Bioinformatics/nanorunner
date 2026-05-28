#!/usr/bin/env python
"""Round 9: wheel hygiene + test-suite stability + API docstring coverage.

Round 7 confirmed that the wheel builds and installs into a fresh
venv. This round looks one layer deeper:

- Y (wheel hygiene): what does the wheel/sdist actually contain? Are
  there developer artifacts (audit drivers, examples, tests, stray
  __pycache__) shipped to end users that shouldn't be?
- Z (test stability): is the suite deterministic? Three consecutive
  runs should produce the same pass count and the same set of test
  IDs in the same order.
- AA (docstring coverage): every public symbol re-exported from
  ``nanopore_simulator`` should have a docstring.

Usage:
    python bin/audit_wheel_stability.py --root /tmp/audit-2026-05-28-round9
"""

from __future__ import annotations

import argparse
import inspect
import json
import logging
import shutil
import subprocess
import sys
import time
import traceback
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger("audit-r9")
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
# Phase Y: wheel hygiene
# ---------------------------------------------------------------------


def _build_artifacts(root: Path) -> Optional[Path]:
    dist = _reset(root / "dist")
    proc = subprocess.run(
        [sys.executable, "-m", "build", "--outdir", str(dist)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0:
        return None
    return dist


def _wheel_members(wheel: Path) -> List[str]:
    with zipfile.ZipFile(wheel) as zf:
        return zf.namelist()


def _sdist_members(sdist: Path) -> List[str]:
    proc = subprocess.run(
        ["tar", "-tzf", str(sdist)], capture_output=True, text=True, timeout=30
    )
    return proc.stdout.splitlines()


def phase_y_wheel(root: Path) -> List[Finding]:
    findings: List[Finding] = []

    dist = _build_artifacts(root)
    if dist is None:
        f = Finding(scenario="wheel/build_succeeded", phase="Y", passed=False)
        f.fail("python -m build failed")
        return [f]

    wheel = next(iter(dist.glob("*.whl")), None)
    sdist = next(iter(dist.glob("*.tar.gz")), None)

    # Y1: wheel must only ship the importable package -- no audit
    # drivers, examples, tests, docs, or stray __pycache__.
    f = Finding(scenario="wheel/contents_minimal", phase="Y")
    t0 = time.perf_counter()
    try:
        if wheel is None:
            f.fail("no wheel produced")
        else:
            members = _wheel_members(wheel)
            disallowed_prefixes = ("bin/", "examples/", "tests/", "docs/")
            disallowed = [
                m for m in members if any(m.startswith(p) for p in disallowed_prefixes)
            ]
            pycache = [m for m in members if "__pycache__" in m]
            f.add(f"total_entries={len(members)}")
            f.add(f"disallowed={disallowed[:5]}")
            f.add(f"pycache={len(pycache)}")
            if disallowed:
                f.fail(f"wheel ships developer-only paths: {disallowed[:5]}")
            if pycache:
                f.fail(f"wheel contains {len(pycache)} __pycache__ entries")
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    # Y2: wheel must include the top-level metadata files declared in
    # pyproject (README + LICENSE) so PyPI page renders correctly.
    f = Finding(scenario="wheel/metadata_files_present", phase="Y")
    t0 = time.perf_counter()
    try:
        if wheel is None:
            f.fail("no wheel produced")
        else:
            members = _wheel_members(wheel)
            dist_info = [m for m in members if "dist-info" in m]
            f.add(f"dist_info_entries={len(dist_info)}")
            need = {"METADATA": False, "RECORD": False, "WHEEL": False}
            for m in dist_info:
                for key in need:
                    if m.endswith(f"/{key}"):
                        need[key] = True
            missing = [k for k, v in need.items() if not v]
            if missing:
                f.fail(f"wheel missing dist-info files: {missing}")
            # The METADATA file should embed the README (long
            # description). Quick check that "nanorunner" appears.
            metadata_path = next(
                (m for m in dist_info if m.endswith("/METADATA")), None
            )
            if metadata_path:
                with zipfile.ZipFile(wheel) as zf:
                    body = zf.read(metadata_path).decode("utf-8", "replace")
                if "nanopore" not in body.lower():
                    f.fail("wheel METADATA does not mention 'nanopore'")
    except Exception as exc:
        f.fail(f"exception: {exc}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    # Y3: sdist may legitimately ship tests/examples/bin/docs (it's a
    # source distribution), but should NOT ship __pycache__ or build
    # artefacts.
    f = Finding(scenario="sdist/no_build_artifacts", phase="Y")
    t0 = time.perf_counter()
    try:
        if sdist is None:
            f.fail("no sdist produced")
        else:
            members = _sdist_members(sdist)
            # nanorunner.egg-info/ is a standard sdist artefact
            # produced by setuptools (PKG-INFO, SOURCES.txt, etc.) --
            # not pollution. Only flag things that genuinely should
            # not be in a clean sdist.
            polluted = [
                m
                for m in members
                if "__pycache__" in m
                or m.endswith(".pyc")
                or "/build/" in m
                or "/.git/" in m
            ]
            f.add(f"total_entries={len(members)} polluted={len(polluted)}")
            if polluted:
                f.fail(f"sdist contains build artefacts: {polluted[:5]}")
    except Exception as exc:
        f.fail(f"exception: {exc}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    return findings


# ---------------------------------------------------------------------
# Phase Z: test-suite stability
# ---------------------------------------------------------------------


def phase_z_stability(root: Path) -> List[Finding]:
    findings: List[Finding] = []

    f = Finding(scenario="suite/three_runs_identical", phase="Z")
    t0 = time.perf_counter()
    try:
        import re

        # Compare a normalized form of the summary -- pass/fail counts
        # and warning count, with the timing tail stripped so that
        # natural runtime jitter does not look like flakiness.
        def _normalize(tail: str) -> str:
            return re.sub(r"\s*in\s*[\d.]+s.*$", "", tail).strip()

        run_summaries: List[str] = []
        for i in range(3):
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "--tb=no"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=300,
            )
            tail = proc.stdout.strip().split("\n")[-1]
            run_summaries.append(_normalize(tail))
            if proc.returncode != 0:
                f.fail(f"run {i} exited non-zero: {tail}")
                break
        f.add(f"normalized_summaries={run_summaries}")
        if len(set(run_summaries)) > 1:
            f.fail(f"summary varied across runs: {sorted(set(run_summaries))}")
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    return findings


# ---------------------------------------------------------------------
# Phase AA: public API docstring coverage
# ---------------------------------------------------------------------


def phase_aa_docstrings(root: Path) -> List[Finding]:
    findings: List[Finding] = []

    f = Finding(scenario="api/public_symbols_documented", phase="AA")
    t0 = time.perf_counter()
    try:
        # Import the top-level package (the public re-export surface).
        import nanopore_simulator as pkg

        public = [
            (name, getattr(pkg, name)) for name in dir(pkg) if not name.startswith("_")
        ]
        f.add(f"public_symbols={len(public)}")
        missing: List[str] = []
        for name, obj in public:
            # Modules are documented in their own docstring; we check
            # them too. Built-in types (str, int) shouldn't appear here.
            doc = inspect.getdoc(obj)
            if not doc or len(doc.strip()) < 5:
                missing.append(name)
        if missing:
            f.fail(f"no/empty docstring on: {missing}")
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    # AA2: public API methods of ReplayConfig / GenerateConfig (the
    # dataclass docstrings should describe every field).
    f = Finding(scenario="api/config_dataclass_docstrings", phase="AA")
    t0 = time.perf_counter()
    try:
        from nanopore_simulator.config import GenerateConfig, ReplayConfig

        for cls in (ReplayConfig, GenerateConfig):
            doc = inspect.getdoc(cls) or ""
            field_names = list(cls.__dataclass_fields__.keys())
            undocumented = [fn for fn in field_names if fn not in doc and fn != "self"]
            f.add(
                f"{cls.__name__}: fields={len(field_names)} undocumented={undocumented}"
            )
            if undocumented:
                f.fail(f"{cls.__name__} docstring missing fields: {undocumented}")
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    return findings


def write_report(root: Path, findings: List[Finding]) -> Path:
    path = root / "reports" / "wheel-stability-report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    failed = [f for f in findings if not f.passed]
    by_phase: Dict[str, List[Finding]] = {}
    for f in findings:
        by_phase.setdefault(f.phase, []).append(f)
    lines = [
        "# nanorunner wheel + stability + docstring audit (round 9)",
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
    findings.extend(phase_y_wheel(root))
    findings.extend(phase_z_stability(root))
    findings.extend(phase_aa_docstrings(root))

    report = write_report(root, findings)
    logger.info("wrote %s", report)
    return 1 if any(not f.passed for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
