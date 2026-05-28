#!/usr/bin/env python
"""Round 13: targeted mutation testing.

Twelve rounds shipped seven production bug fixes. This driver
re-introduces each fix as a controlled mutation, runs the full unit
suite, and verifies the test suite KILLS the mutant (i.e. at least
one test fails). A surviving mutant signals weak test coverage in
the area the fix touched.

Strategy:
  - Patch a single line in a single module.
  - Run pytest -x --tb=no -q (stop at first failure -- fast signal).
  - Restore the original line whether the suite kills the mutant or
    not.
  - Aggregate kill rate.

Usage:
    python bin/audit_mutation.py --root /tmp/audit-2026-05-28-round13
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
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("audit-r13")
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


@dataclass
class Mutation:
    """One textual mutation in a single file.

    The driver verifies that ``original`` exists in the file (so the
    mutation is well-targeted), swaps it for ``mutant``, runs pytest,
    and restores.
    """

    file: Path
    original: str
    mutant: str
    description: str


def _run_suite() -> Tuple[int, str]:
    """Run pytest and return (exit_code, tail)."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-x", "--tb=no", "-q"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    tail = (proc.stdout or proc.stderr).strip().split("\n")[-1]
    return proc.returncode, tail


def _apply_mutation(m: Mutation) -> bool:
    """Apply mutation in-place. Returns True if the textual swap took."""
    text = m.file.read_text()
    if m.original not in text:
        return False
    if text.count(m.original) != 1:
        # Ambiguous mutation -- refuse rather than risk swapping the
        # wrong occurrence.
        return False
    m.file.write_text(text.replace(m.original, m.mutant, 1))
    return True


def _restore_file(m: Mutation, snapshot: str) -> None:
    m.file.write_text(snapshot)


def _snapshot(file: Path) -> str:
    return file.read_text()


# ---------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------


def _mutations() -> List[Mutation]:
    """The six mutations to test. Each reverts a prior production fix.

    A mutant that SURVIVES (suite still passes) indicates the original
    bug would have shipped undetected.
    """
    pkg = REPO_ROOT / "nanopore_simulator"
    return [
        # M1: round 1 -- stratified shuffle gone, revert to drain-first
        Mutation(
            file=pkg / "manifest.py",
            original=(
                '    seed = zlib.adler32(str(config.target_dir).encode("utf-8"))\n'
                "    rng = random.Random(seed)\n"
                "    entries: List[FileEntry] = []\n"
                "    max_files = max((len(b) for b in per_barcode), default=0)\n"
                "    for fi in range(max_files):\n"
                "        round_indices = [i for i, b in enumerate(per_barcode) if fi < len(b)]\n"
                "        rng.shuffle(round_indices)\n"
                "        for i in round_indices:\n"
                "            entries.append(per_barcode[i][fi])"
            ),
            mutant=(
                "    entries: List[FileEntry] = []\n"
                "    for bucket in per_barcode:\n"
                "        entries.extend(bucket)"
            ),
            description="revert round-1 fix: drain barcode01 before barcode02",
        ),
        # M2: round 1 -- AppleDouble filter removed
        Mutation(
            file=pkg / "detection.py",
            original=(
                "    name = file_path.name\n"
                '    if name.startswith("."):\n'
                "        return False\n"
                "    name_lower = name.lower()"
            ),
            mutant="    name_lower = file_path.name.lower()",
            description="revert round-1 fix: stop skipping hidden ._files",
        ),
        # M3: round 3 -- output_barcode_pattern distinct-name check removed
        Mutation(
            file=pkg / "config.py",
            original=(
                "        if sample_one == sample_two:\n"
                "            raise ValueError(\n"
                '                "output_barcode_pattern must produce distinct names per "\n'
                '                "barcode index -- include a positional placeholder like "\n'
                "                f'\"barcode{{:02d}}\" (got {self.output_barcode_pattern!r})'\n"
                "            )"
            ),
            mutant="        pass  # MUTANT: skip distinct-name check",
            description="revert round-3 fix: accept non-placeholder patterns",
        ),
        # M4: round 11 -- parallel precedence reverted to `or`
        Mutation(
            file=pkg / "cli_generate.py",
            original=(
                "    par = parallel if parallel is not None "
                'else params.get("parallel_processing", False)'
            ),
            mutant='    par = parallel or params.get("parallel_processing", False)',
            description="revert round-11 fix: --no-parallel ignored under profile",
        ),
        # M5: round 8 -- determinism gone, fresh RNG each call
        Mutation(
            file=pkg / "runner.py",
            original=(
                "    if config.seed is not None:\n"
                "        gen_seed: Optional[int] = config.seed\n"
                "    else:\n"
                "        import zlib\n"
                "\n"
                '        gen_seed = zlib.adler32(str(config.target_dir).encode("utf-8"))'
            ),
            mutant=("    gen_seed: Optional[int] = config.seed"),
            description="revert round-8 fix: no target_dir-derived seed",
        ),
        # M6: round 7 -- offline resolve_taxid skips cache
        Mutation(
            file=pkg / "species.py",
            original=(
                "    res_cache = ResolutionCache(cache_dir=resolution_cache_dir)\n"
                "\n"
                "    # 1. Check the resolution cache so previously-resolved taxids work\n"
                "    #    offline. (Mirrors the resolve_species cache-first pattern.)\n"
                '    cached = res_cache.get(f"taxid:{taxid}")\n'
                "    if cached is not None:\n"
                "        return cached\n"
                "\n"
                "    if offline:\n"
                "        return None"
            ),
            mutant=(
                "    if offline:\n"
                "        return None\n"
                "    res_cache = ResolutionCache(cache_dir=resolution_cache_dir)"
            ),
            description="revert round-7 fix: --taxid --offline ignores cache",
        ),
    ]


# ---------------------------------------------------------------------
# Phase HH: mutation kill-rate
# ---------------------------------------------------------------------


def phase_hh_mutation(root: Path) -> List[Finding]:
    findings: List[Finding] = []
    for idx, m in enumerate(_mutations(), start=1):
        scenario = f"mutation/M{idx}_{m.description[:40].replace(' ', '_')}"
        f = Finding(scenario=scenario, phase="HH")
        t0 = time.perf_counter()
        snapshot = _snapshot(m.file)
        try:
            applied = _apply_mutation(m)
            if not applied:
                f.fail(f"original text not found exactly once in {m.file.name}")
                f.duration_s = time.perf_counter() - t0
                findings.append(f)
                continue
            f.add(f"mutated_file={m.file.name}")
            exit_code, tail = _run_suite()
            f.add(f"suite_exit={exit_code} tail={tail}")
            if exit_code == 0:
                f.fail("MUTANT SURVIVED: test suite passed despite known bug")
            else:
                f.add("mutant killed -- regression test fires")
        except Exception as exc:
            f.fail(f"exception: {exc}\n{traceback.format_exc()}")
        finally:
            _restore_file(m, snapshot)
        f.duration_s = time.perf_counter() - t0
        findings.append(f)
        logger.info(
            "M%d %s -- %s (%.1fs)",
            idx,
            "KILLED" if f.passed else "SURVIVED",
            m.description,
            f.duration_s,
        )
    return findings


def write_report(root: Path, findings: List[Finding]) -> Path:
    path = root / "reports" / "mutation-report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    failed = [f for f in findings if not f.passed]
    by_phase: Dict[str, List[Finding]] = {}
    for f in findings:
        by_phase.setdefault(f.phase, []).append(f)
    lines = [
        "# nanorunner mutation testing audit (round 13)",
        "",
        f"- total mutants: {len(findings)}",
        f"- survived (BAD): {len(failed)}",
        f"- killed (good): {len(findings) - len(failed)}",
        f"- kill rate: {(len(findings) - len(failed)) / max(1, len(findings)) * 100:.0f}%",
        "",
    ]
    for phase in sorted(by_phase):
        lines.append(f"## Phase {phase}")
        lines.append("")
        lines.append("| mutant | result | seconds | details |")
        lines.append("|---|---|---|---|")
        for f in by_phase[phase]:
            status = "KILLED" if f.passed else "SURVIVED"
            joined = "<br>".join(d.replace("|", "\\|") for d in f.details)
            lines.append(f"| {f.scenario} | {status} | {f.duration_s:.2f} | {joined} |")
        lines.append("")
    if failed:
        lines.append("## Survivor detail")
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
    findings.extend(phase_hh_mutation(root))

    report = write_report(root, findings)
    logger.info("wrote %s", report)
    return 1 if any(not f.passed for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
