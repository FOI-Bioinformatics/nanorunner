#!/usr/bin/env python
"""Round 11: profile/CLI flag precedence + adapter validation correctness.

- DD (precedence): when a profile sets a value (e.g. batch_size=10,
  parallel=True) and the CLI explicitly passes a different value,
  the CLI must win. Every previous round assumed this worked; only
  exit codes were checked.
- EE (adapter validation): validate_output should return an issue
  list -- empty when the directory matches the adapter spec,
  non-empty when it does not. Confirm both branches actually fire.

Usage:
    python bin/audit_profile_adapter.py --root /tmp/audit-2026-05-28-round11
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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("audit-r11")
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


def _run(args, timeout=120):
    return subprocess.run(
        [NANORUNNER, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _build_source(root: Path, n_files: int = 4) -> Path:
    src = _reset(root / "src")
    sample = "@r1\nACGTACGT\n+\nIIIIIIII\n"
    for i in range(n_files):
        (src / f"reads_{i:02d}.fastq").write_text(sample)
    return src


# ---------------------------------------------------------------------
# Phase DD: profile / CLI flag precedence
# ---------------------------------------------------------------------


def phase_dd_precedence(root: Path) -> List[Finding]:
    findings: List[Finding] = []
    src = _build_source(root)

    def _replay(
        label: str, profile: str, extra: List[str]
    ) -> subprocess.CompletedProcess:
        tgt = _reset(root / "dd" / label)
        # --log-level is a *global* option and must come before the
        # subcommand name; placing it after `replay` fails parsing.
        return _run(
            [
                "--log-level",
                "DEBUG",
                "replay",
                "--source",
                str(src),
                "--target",
                str(tgt),
                "--profile",
                profile,
                "--interval",
                "0.0",
                "--monitor",
                "none",
            ]
            + extra,
            timeout=30,
        )

    # DD1: explicit --batch-size must override profile's batch_size.
    # development profile sets batch_size=10; we pass --batch-size 2
    # and expect 2 file-per-interval batches in the debug log.
    f = Finding(scenario="precedence/batch_size_overrides_profile", phase="DD")
    t0 = time.perf_counter()
    try:
        proc = _replay("bs_override", "development", ["--batch-size", "2"])
        if proc.returncode != 0:
            f.fail(f"non-zero exit: {proc.stderr[-200:]}")
        else:
            # 4 source files / batch_size=2 -> 2 batches.
            text = proc.stderr + proc.stdout
            m = re.search(r"Processing batch (\d+)/(\d+)", text)
            if m is None:
                f.add("no batch-progress message; relying on file count only")
            else:
                total_batches = int(m.group(2))
                f.add(f"total_batches={total_batches}")
                if total_batches != 2:
                    f.fail(
                        f"--batch-size 2 not honored: expected 2 batches "
                        f"(development profile sets 10), got {total_batches}"
                    )
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    # DD2: explicit --no-parallel must override a profile that has
    # parallel_processing=True. The "development" profile does.
    # If precedence is correct the resolved parallel is False; if the
    # current code uses `parallel OR profile`, --no-parallel silently
    # loses.
    f = Finding(scenario="precedence/no_parallel_overrides_profile", phase="DD")
    t0 = time.perf_counter()
    try:
        proc = _replay("np_override", "development", ["--no-parallel"])
        if proc.returncode != 0:
            f.fail(f"non-zero exit: {proc.stderr[-200:]}")
        else:
            text = proc.stderr + proc.stdout
            # The runner's _execute_manifest logs "Processing batch X/Y
            # (Z files)" for sequential; parallel runs use the parallel
            # path. We can detect parallel mode by the runner debug
            # output. Simpler: confirm the FINAL resolved config by
            # rerunning a tiny Python introspection in a subprocess.
            check = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from typer.testing import CliRunner\n"
                    "from nanopore_simulator.cli import app\n"
                    "import sys, json\n"
                    "from unittest.mock import patch\n"
                    "captured = {}\n"
                    "def fake_run(cfg):\n"
                    "    captured['parallel'] = cfg.parallel\n"
                    "with patch('nanopore_simulator.cli_replay.run_replay', side_effect=fake_run):\n"
                    "    r = CliRunner().invoke(app, ['replay', '--source', sys.argv[1], '--target', sys.argv[2], '--profile', 'development', '--interval', '0', '--monitor', 'none', '--no-parallel'])\n"
                    "print(json.dumps({'exit': r.exit_code, 'parallel': captured.get('parallel')}))\n",
                    str(src),
                    str(_reset(root / "dd" / "np_inspect")),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=30,
            )
            import json as _json

            data = _json.loads(check.stdout.strip().split("\n")[-1])
            f.add(f"resolved_parallel={data.get('parallel')}")
            if data.get("parallel") is True:
                f.fail(
                    "--no-parallel did not override profile's parallel_processing=True"
                )
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    # DD3: same parallel-precedence check for generate.
    f = Finding(
        scenario="precedence/no_parallel_overrides_profile_generate", phase="DD"
    )
    t0 = time.perf_counter()
    try:
        from audit_simulate_replay import _synthetic_fasta_for  # noqa: WPS433

        genome = _synthetic_fasta_for("ecoliK12", root)
        check = subprocess.run(
            [
                sys.executable,
                "-c",
                "from typer.testing import CliRunner\n"
                "from nanopore_simulator.cli import app\n"
                "import sys, json\n"
                "from unittest.mock import patch\n"
                "captured = {}\n"
                "def fake_run(cfg):\n"
                "    captured['parallel'] = cfg.parallel\n"
                "with patch('nanopore_simulator.cli_generate.run_generate', side_effect=fake_run):\n"
                "    r = CliRunner().invoke(app, ['generate', '--target', sys.argv[1], '--genomes', sys.argv[2], '--profile', 'generate_standard', '--read-count', '10', '--reads-per-file', '5', '--interval', '0', '--monitor', 'none', '--no-parallel', '--generator-backend', 'builtin'])\n"
                "print(json.dumps({'exit': r.exit_code, 'parallel': captured.get('parallel')}))\n",
                str(_reset(root / "dd" / "np_gen")),
                str(genome),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        import json as _json

        data = _json.loads(check.stdout.strip().split("\n")[-1])
        f.add(f"resolved_parallel={data.get('parallel')}")
        if data.get("parallel") is True:
            f.fail(
                "--no-parallel did not override profile's parallel_processing=True (generate)"
            )
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    # DD4: explicit --timing-model must override profile's timing_model.
    f = Finding(scenario="precedence/timing_model_overrides_profile", phase="DD")
    t0 = time.perf_counter()
    try:
        check = subprocess.run(
            [
                sys.executable,
                "-c",
                "from typer.testing import CliRunner\n"
                "from nanopore_simulator.cli import app\n"
                "import sys, json\n"
                "from unittest.mock import patch\n"
                "captured = {}\n"
                "def fake_run(cfg):\n"
                "    captured['timing_model'] = cfg.timing_model\n"
                "with patch('nanopore_simulator.cli_replay.run_replay', side_effect=fake_run):\n"
                "    r = CliRunner().invoke(app, ['replay', '--source', sys.argv[1], '--target', sys.argv[2], '--profile', 'bursty', '--timing-model', 'uniform', '--interval', '0', '--monitor', 'none'])\n"
                "print(json.dumps({'exit': r.exit_code, 'timing_model': captured.get('timing_model')}))\n",
                str(src),
                str(_reset(root / "dd" / "tm_inspect")),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        import json as _json

        data = _json.loads(check.stdout.strip().split("\n")[-1])
        f.add(f"resolved_timing_model={data.get('timing_model')}")
        if data.get("timing_model") != "uniform":
            f.fail(
                f"--timing-model uniform was ignored; got {data.get('timing_model')}"
            )
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    return findings


# ---------------------------------------------------------------------
# Phase EE: adapter validation
# ---------------------------------------------------------------------


def phase_ee_adapter(root: Path) -> List[Finding]:
    findings: List[Finding] = []
    from nanopore_simulator.adapters import validate_output, list_adapters

    # EE1: validate_output on a missing target returns one issue.
    f = Finding(scenario="adapter/missing_target_yields_issue", phase="EE")
    t0 = time.perf_counter()
    try:
        issues = validate_output(root / "does_not_exist", "nanometa")
        f.add(f"issues={issues}")
        if not issues or "does not exist" not in issues[0].lower():
            f.fail("expected one 'does not exist' issue")
    except Exception as exc:
        f.fail(f"exception: {exc}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    # EE2: validate_output on a directory with no matching files returns
    # one "No files matching ..." issue.
    f = Finding(scenario="adapter/empty_dir_yields_issue", phase="EE")
    t0 = time.perf_counter()
    try:
        empty = _reset(root / "empty")
        issues = validate_output(empty, "nanometa")
        f.add(f"issues={issues}")
        if not issues or "no files matching" not in issues[0].lower():
            f.fail("expected one 'No files matching' issue")
    except Exception as exc:
        f.fail(f"exception: {exc}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    # EE3: validate_output on a directory with matching FASTQ returns
    # an empty issue list (passes validation).
    f = Finding(scenario="adapter/matching_dir_no_issues", phase="EE")
    t0 = time.perf_counter()
    try:
        good = _reset(root / "good")
        # nanometa expects FASTQ files anywhere under the target dir,
        # potentially in barcode subdirectories.
        bc = good / "barcode01"
        bc.mkdir()
        (bc / "reads.fastq.gz").write_bytes(b"\x1f\x8b\x08\x00")
        issues = validate_output(good, "nanometa")
        f.add(f"issues={issues}")
        if issues:
            f.fail(f"expected no issues, got {issues}")
    except Exception as exc:
        f.fail(f"exception: {exc}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    # EE4: unknown adapter name raises KeyError per docstring.
    f = Finding(scenario="adapter/unknown_name_raises", phase="EE")
    t0 = time.perf_counter()
    try:
        good = _reset(root / "ee4")
        (good / "reads.fastq").write_text("@r\nACGT\n+\nIIII\n")
        try:
            validate_output(good, "no_such_adapter_xyz")
            f.fail("expected KeyError for unknown adapter")
        except KeyError:
            f.add("raised KeyError as documented")
    except Exception as exc:
        f.fail(f"exception: {exc}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    # EE5: every registered adapter has a description and accepts the
    # public list_adapters lookup.
    f = Finding(scenario="adapter/list_adapters_consistent", phase="EE")
    t0 = time.perf_counter()
    try:
        adapters = list_adapters()
        f.add(f"adapters={sorted(adapters)}")
        if not adapters:
            f.fail("list_adapters returned empty")
        for name, desc in adapters.items():
            if not desc.strip():
                f.fail(f"adapter {name} has empty description")
    except Exception as exc:
        f.fail(f"exception: {exc}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    return findings


def write_report(root: Path, findings: List[Finding]) -> Path:
    path = root / "reports" / "precedence-adapter-report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    failed = [f for f in findings if not f.passed]
    by_phase: Dict[str, List[Finding]] = {}
    for f in findings:
        by_phase.setdefault(f.phase, []).append(f)
    lines = [
        "# nanorunner profile/CLI precedence + adapter audit (round 11)",
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

    sys.path.insert(0, str(Path(__file__).resolve().parent))

    findings: List[Finding] = []
    findings.extend(phase_dd_precedence(root))
    findings.extend(phase_ee_adapter(root))

    report = write_report(root, findings)
    logger.info("wrote %s", report)
    return 1 if any(not f.passed for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
