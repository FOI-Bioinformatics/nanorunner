#!/usr/bin/env python
"""Round 7: packaging + distribution readiness audit.

Verifies that nanorunner is shippable -- versions match across all
sources of truth, the wheel and sdist build cleanly, the wheel
installs into a fresh virtualenv and the CLI works there, CHANGELOG
covers every release tag, and the CI workflow references the right
matrix.

Usage:
    python bin/audit_packaging.py \\
        --root /tmp/audit-2026-05-27-round7
"""

from __future__ import annotations

import argparse
import logging
import re
import shutil
import subprocess
import sys
import time
import traceback
import venv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

logger = logging.getLogger("audit-r7")
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


def _run(
    args: Sequence[str], cwd: Optional[Path] = None, timeout: int = 300
) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, capture_output=True, text=True, timeout=timeout, cwd=cwd
    )


# ---------------------------------------------------------------------
# Phase R: version + metadata consistency
# ---------------------------------------------------------------------


def phase_r_metadata(root: Path) -> List[Finding]:
    findings: List[Finding] = []

    f = Finding(scenario="metadata/version_consistency", phase="R")
    t0 = time.perf_counter()
    try:
        # pyproject.toml
        py = (REPO_ROOT / "pyproject.toml").read_text()
        m = re.search(r'^version\s*=\s*"([^"]+)"', py, re.MULTILINE)
        if not m:
            f.fail("pyproject.toml: version field not found")
        else:
            pyproject_v = m.group(1)
            f.add(f"pyproject={pyproject_v}")

            # __init__.py
            init = (REPO_ROOT / "nanopore_simulator" / "__init__.py").read_text()
            m = re.search(r'__version__\s*=\s*"([^"]+)"', init)
            init_v = m.group(1) if m else None
            f.add(f"__init__={init_v}")
            if init_v != pyproject_v:
                f.fail(f"version mismatch: pyproject={pyproject_v} init={init_v}")

            # README badge
            readme = (REPO_ROOT / "README.md").read_text()
            if pyproject_v not in readme:
                f.fail(f"README does not mention version {pyproject_v}")

            # CHANGELOG
            changelog = (REPO_ROOT / "CHANGELOG.md").read_text()
            if f"## [{pyproject_v}]" not in changelog:
                f.fail(f"CHANGELOG missing section for {pyproject_v}")

            # CLAUDE.md
            claude = (REPO_ROOT / "CLAUDE.md").read_text()
            if pyproject_v not in claude:
                f.fail(f"CLAUDE.md does not mention version {pyproject_v}")
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    # Entry-point declared correctly
    f = Finding(scenario="metadata/entry_point_declared", phase="R")
    t0 = time.perf_counter()
    try:
        py = (REPO_ROOT / "pyproject.toml").read_text()
        if 'nanorunner = "nanopore_simulator.cli:main"' not in py:
            f.fail("entry-point declaration not found in pyproject.toml")
        # Verify the target callable actually exists
        sys.path.insert(0, str(REPO_ROOT))
        try:
            from nanopore_simulator import cli as _cli

            if not callable(getattr(_cli, "main", None)):
                f.fail("nanopore_simulator.cli.main is not callable")
        finally:
            sys.path.pop(0)
    except Exception as exc:
        f.fail(f"exception: {exc}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    # MANIFEST.in includes the things the sdist needs
    f = Finding(scenario="metadata/manifest_includes_essentials", phase="R")
    t0 = time.perf_counter()
    try:
        manifest = (REPO_ROOT / "MANIFEST.in").read_text()
        required = ["README", "LICENSE", "CHANGELOG"]
        missing = [r for r in required if r not in manifest]
        f.add(f"manifest mentions: {[r for r in required if r in manifest]}")
        if missing:
            f.fail(f"MANIFEST.in missing: {missing}")
    except FileNotFoundError:
        f.add("no MANIFEST.in (using pyproject defaults)")
    except Exception as exc:
        f.fail(f"exception: {exc}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    return findings


# ---------------------------------------------------------------------
# Phase S: build + install in clean venv
# ---------------------------------------------------------------------


def phase_s_build_install(root: Path) -> List[Finding]:
    findings: List[Finding] = []
    dist_dir = _reset(root / "dist")
    venv_dir = _reset(root / "fresh_venv")

    # S1: build sdist + wheel
    f = Finding(scenario="package/build_sdist_wheel", phase="S")
    t0 = time.perf_counter()
    try:
        proc = _run(
            [sys.executable, "-m", "build", "--outdir", str(dist_dir)],
            cwd=REPO_ROOT,
            timeout=300,
        )
        f.add(f"exit={proc.returncode}")
        if proc.returncode != 0:
            f.fail(f"build failed: {proc.stderr[-400:]}")
        else:
            artifacts = sorted(dist_dir.iterdir())
            f.add(f"artifacts={[p.name for p in artifacts]}")
            wheels = [p for p in artifacts if p.suffix == ".whl"]
            sdists = [p for p in artifacts if p.name.endswith(".tar.gz")]
            if not wheels:
                f.fail("no wheel produced")
            if not sdists:
                f.fail("no sdist produced")
    except subprocess.TimeoutExpired:
        f.fail("build timed out (300s)")
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    if not f.passed:
        return findings  # No point installing a broken build

    # S2: install the wheel into a clean venv and run sanity commands
    wheel = next((p for p in dist_dir.glob("*.whl")), None)
    if wheel is None:
        return findings

    f = Finding(scenario="package/install_into_clean_venv", phase="S")
    t0 = time.perf_counter()
    try:
        venv.create(venv_dir, with_pip=True, clear=True)
        py = venv_dir / "bin" / "python"
        pip_install = _run(
            [str(py), "-m", "pip", "install", str(wheel)],
            timeout=180,
        )
        f.add(f"pip_install_exit={pip_install.returncode}")
        if pip_install.returncode != 0:
            f.fail(f"pip install failed: {pip_install.stderr[-400:]}")
        else:
            # Now run the CLI from the venv
            cli = venv_dir / "bin" / "nanorunner"
            if not cli.exists():
                f.fail(f"console_script not installed at {cli}")
            else:
                ver = _run([str(cli), "--version"], timeout=30)
                f.add(f"version_exit={ver.returncode} stdout={ver.stdout.strip()!r}")
                if ver.returncode != 0:
                    f.fail(f"--version failed: {ver.stderr[-300:]}")
                if "3.1.0" not in ver.stdout:
                    f.fail("--version did not print 3.1.0")
                # And a subcommand
                lp = _run([str(cli), "list-profiles"], timeout=30)
                if lp.returncode != 0:
                    f.fail(f"list-profiles failed: {lp.stderr[-300:]}")
                if "generate_test" not in lp.stdout:
                    f.fail("list-profiles output missing known content")
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    # S3: sdist contents include README + LICENSE + CHANGELOG
    sdist = next((p for p in dist_dir.glob("*.tar.gz")), None)
    if sdist is not None:
        f = Finding(scenario="package/sdist_contains_docs", phase="S")
        t0 = time.perf_counter()
        try:
            proc = _run(["tar", "-tzf", str(sdist)], timeout=30)
            names = proc.stdout.splitlines()
            f.add(f"entries={len(names)}")
            for required in ("README.md", "LICENSE", "CHANGELOG.md"):
                if not any(required in n for n in names):
                    f.fail(f"sdist missing {required}")
        except Exception as exc:
            f.fail(f"exception: {exc}")
        f.duration_s = time.perf_counter() - t0
        findings.append(f)

    return findings


# ---------------------------------------------------------------------
# Phase T: CHANGELOG vs git tags
# ---------------------------------------------------------------------


def phase_t_changelog(root: Path) -> List[Finding]:
    findings: List[Finding] = []
    f = Finding(scenario="docs/changelog_covers_tags", phase="T")
    t0 = time.perf_counter()
    try:
        changelog = (REPO_ROOT / "CHANGELOG.md").read_text()
        sections = set(re.findall(r"^## \[([0-9.]+)\]", changelog, re.MULTILINE))
        f.add(f"changelog_versions={sorted(sections)}")

        tags = _run(["git", "tag", "--list", "v*"], cwd=REPO_ROOT, timeout=10)
        tag_versions = {
            t.lstrip("v") for t in tags.stdout.split() if re.match(r"v\d", t)
        }
        f.add(f"git_tags={sorted(tag_versions)}")

        missing = tag_versions - sections
        if missing:
            f.fail(f"CHANGELOG missing entries for tags: {sorted(missing)}")
        # Tagless versions in CHANGELOG are fine (current dev), so we
        # don't fail on sections - tags.
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)
    return findings


# ---------------------------------------------------------------------
# Phase U: CI workflow sanity
# ---------------------------------------------------------------------


def phase_u_ci(root: Path) -> List[Finding]:
    findings: List[Finding] = []
    f = Finding(scenario="ci/workflow_matrix_matches_pyproject", phase="U")
    t0 = time.perf_counter()
    try:
        py = (REPO_ROOT / "pyproject.toml").read_text()
        m = re.search(r'requires-python\s*=\s*"([^"]+)"', py)
        required = m.group(1) if m else None
        f.add(f"requires-python={required}")

        ci_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
        if not ci_path.exists():
            f.fail("no CI workflow found")
        else:
            ci = ci_path.read_text()
            # Spot-check: requires-python ">=3.9" should mean CI tests
            # at least the 3.9 floor.
            if required and ">=3.9" in required and '"3.9"' not in ci:
                f.fail("CI does not test the minimum supported Python 3.9")
            # Spot-check: CI installs the package (no missing step)
            if "pip install -e ." not in ci:
                f.fail("CI does not pip-install the package before testing")
    except Exception as exc:
        f.fail(f"exception: {exc}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    return findings


# ---------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------


def write_report(root: Path, findings: List[Finding]) -> Path:
    path = root / "reports" / "packaging-report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    failed = [f for f in findings if not f.passed]
    by_phase: Dict[str, List[Finding]] = {}
    for f in findings:
        by_phase.setdefault(f.phase, []).append(f)
    lines = [
        "# nanorunner packaging audit (round 7)",
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
    findings.extend(phase_r_metadata(root))
    findings.extend(phase_s_build_install(root))
    findings.extend(phase_t_changelog(root))
    findings.extend(phase_u_ci(root))

    report = write_report(root, findings)
    logger.info("wrote %s", report)
    return 1 if any(not f.passed for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
