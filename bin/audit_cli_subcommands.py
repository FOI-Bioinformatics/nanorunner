#!/usr/bin/env python
"""End-to-end CLI subcommand sweep for nanorunner.

Drives every subcommand and every "behavior-changing" flag via the
real ``nanorunner`` binary (subprocess) -- not the Python API. This
covers the typer layer, profile overlay, monitor selection, exit-code
wiring, and the cli_utils subcommands that the round 1-2 audit
bypassed.

Usage:
    python bin/audit_cli_subcommands.py \
        --root /Volumes/LaCie/nanorunner/audit-2026-05-27-round3

Exits non-zero on any failed scenario. Findings collected at
``<root>/reports/cli-audit-report.md``.
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

# Reuse helpers from the round 1-2 driver. Both scripts live in bin/.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_simulate_replay import (  # noqa: E402
    _collect_fastq,
    _read_count,
    _synthetic_fasta_for,
)

logger = logging.getLogger("cli-audit")

NANORUNNER = "nanorunner"
DEFAULT_TIMEOUT = 180


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


def _run(
    args: Sequence[str], timeout: int = DEFAULT_TIMEOUT
) -> subprocess.CompletedProcess:
    """Invoke nanorunner via subprocess, returning the completed process.

    Never raises on non-zero exit -- caller asserts on returncode.
    """
    return subprocess.run(
        [NANORUNNER, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _expect_ok(f: Finding, proc: subprocess.CompletedProcess) -> None:
    f.add(f"exit={proc.returncode}")
    if proc.returncode != 0:
        snippet = (proc.stderr or proc.stdout)[-500:]
        f.fail(f"expected exit 0, got {proc.returncode}: {snippet!r}")


def _expect_fail(f: Finding, proc: subprocess.CompletedProcess) -> None:
    f.add(f"exit={proc.returncode}")
    if proc.returncode == 0:
        f.fail(f"expected non-zero exit, got 0; stdout: {proc.stdout[-300:]!r}")


def _reset(target: Path) -> Path:
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    return target


# ---------------------------------------------------------------------
# Phase D1: informational subcommands
# ---------------------------------------------------------------------


def phase_d1_info(root: Path) -> List[Finding]:
    findings: List[Finding] = []
    cases = [
        ("list-profiles", "generate_test"),
        ("list-adapters", "nanometa"),
        ("list-generators", "builtin"),
        ("list-mocks", "zymo_d6300"),
        ("check-deps", "builtin"),
    ]
    for cmd, marker in cases:
        f = Finding(scenario=f"info/{cmd}", phase="D1")
        t0 = time.perf_counter()
        try:
            proc = _run([cmd])
            _expect_ok(f, proc)
            if marker not in proc.stdout:
                f.fail(f"expected {marker!r} in stdout")
        except Exception as exc:
            f.fail(f"exception: {exc}")
        f.duration_s = time.perf_counter() - t0
        findings.append(f)
    return findings


# ---------------------------------------------------------------------
# Phase D2: recommend
# ---------------------------------------------------------------------


def phase_d2_recommend(root: Path, flat_src: Path) -> List[Finding]:
    findings: List[Finding] = []
    for label, extra in [
        ("file_count_50", ["--file-count", "50"]),
        ("source", ["--source", str(flat_src)]),
    ]:
        f = Finding(scenario=f"recommend/{label}", phase="D2")
        t0 = time.perf_counter()
        try:
            proc = _run(["recommend", *extra])
            _expect_ok(f, proc)
            # Must reference at least one known profile.
            if not any(
                name in proc.stdout
                for name in ("development", "steady", "bursty", "generate_test")
            ):
                f.fail("recommend output mentions no known profile name")
        except Exception as exc:
            f.fail(f"exception: {exc}")
        f.duration_s = time.perf_counter() - t0
        findings.append(f)
    return findings


# ---------------------------------------------------------------------
# Phase D3: validate
# ---------------------------------------------------------------------


def phase_d3_validate(root: Path, barcoded_src: Path) -> List[Finding]:
    findings: List[Finding] = []

    f = Finding(scenario="validate/nanometa_ok", phase="D3")
    t0 = time.perf_counter()
    try:
        proc = _run(
            ["validate", "--pipeline", "nanometa", "--target", str(barcoded_src)]
        )
        _expect_ok(f, proc)
    except Exception as exc:
        f.fail(f"exception: {exc}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    # Alias check (nanometanf -> nanometa)
    f = Finding(scenario="validate/nanometanf_alias", phase="D3")
    t0 = time.perf_counter()
    try:
        proc = _run(
            ["validate", "--pipeline", "nanometanf", "--target", str(barcoded_src)]
        )
        _expect_ok(f, proc)
    except Exception as exc:
        f.fail(f"exception: {exc}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    # Empty target dir should fail validation
    empty = _reset(root / "scratch" / "empty_validate")
    f = Finding(scenario="validate/empty_dir_fails", phase="D3")
    t0 = time.perf_counter()
    try:
        proc = _run(["validate", "--pipeline", "nanometa", "--target", str(empty)])
        _expect_fail(f, proc)
    except Exception as exc:
        f.fail(f"exception: {exc}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    return findings


# ---------------------------------------------------------------------
# Phase D4: generate flag sweep
# ---------------------------------------------------------------------


def _gen_baseline(target: Path, genomes: List[Path]) -> List[str]:
    return [
        "generate",
        "--target",
        str(target),
        *sum([["--genomes", str(g)] for g in genomes], []),
        "--read-count",
        "60",
        "--reads-per-file",
        "30",
        "--mean-read-length",
        "1500",
        "--no-wait",
        "--monitor",
        "none",
        "--generator-backend",
        "builtin",
    ]


def phase_d4_generate_sweep(root: Path, genomes: List[Path]) -> List[Finding]:
    findings: List[Finding] = []

    def case(label: str, override: List[str], extra_assert=None, timeout: int = 180):
        scenario = f"gen/{label}"
        target = _reset(root / "scratch" / "gen" / label)
        f = Finding(scenario=scenario, phase="D4")
        t0 = time.perf_counter()
        try:
            cmd = _gen_baseline(target, genomes) + override
            proc = _run(cmd, timeout=timeout)
            _expect_ok(f, proc)
            files = _collect_fastq(target)
            f.add(f"files={len(files)}")
            if not files:
                f.fail("no FASTQ produced")
            elif extra_assert is not None:
                extra_assert(f, target, files)
        except Exception as exc:
            f.fail(f"exception: {exc}\n{traceback.format_exc()}")
        f.duration_s = time.perf_counter() - t0
        findings.append(f)

    # Baseline (with backend=builtin already set)
    case("baseline", [])

    # Output format
    case(
        "fmt_fastq",
        ["--output-format", "fastq"],
        lambda f, t, fs: (
            f.fail("gz unexpected") if any(p.suffix == ".gz" for p in fs) else None
        ),
    )
    case(
        "fmt_fastq_gz",
        ["--output-format", "fastq.gz"],
        lambda f, t, fs: (
            f.fail("expected .gz") if not all(p.suffix == ".gz" for p in fs) else None
        ),
    )

    # Force structure
    case("force_singleplex", ["--force-structure", "singleplex"])
    case(
        "force_multiplex",
        ["--force-structure", "multiplex"],
        lambda f, t, fs: (
            f.fail("no barcode dirs")
            if not any(p.parent.name.startswith("barcode") for p in fs)
            else None
        ),
    )

    # Mix reads
    case("mix_reads", ["--mix-reads"])

    # Reads-per-file
    case("rpf_small", ["--reads-per-file", "10"])
    case("rpf_default", ["--reads-per-file", "100"])

    # Read-count
    case("rc_60", ["--read-count", "60"])
    case("rc_300", ["--read-count", "300"])

    # Abundances
    case(
        "abundances_even",
        ["--abundances", "0.33", "--abundances", "0.34", "--abundances", "0.33"],
    )
    case(
        "abundances_skewed",
        ["--abundances", "0.9", "--abundances", "0.05", "--abundances", "0.05"],
    )

    # Profiles
    case("profile_generate_test", ["--profile", "generate_test"])
    case("profile_generate_standard", ["--profile", "generate_standard"], timeout=300)

    # Timing models
    case("timing_uniform", ["--timing-model", "uniform"])
    case("timing_random", ["--timing-model", "random", "--random-factor", "0.2"])
    case(
        "timing_poisson",
        [
            "--timing-model",
            "poisson",
            "--burst-probability",
            "0.2",
            "--burst-rate-multiplier",
            "5.0",
        ],
    )
    case(
        "timing_adaptive",
        [
            "--timing-model",
            "adaptive",
            "--adaptation-rate",
            "0.2",
            "--history-size",
            "10",
        ],
    )

    # Parallel
    case("parallel_4", ["--parallel", "--worker-count", "4"])
    case("sequential", [])

    # Backend
    case("backend_badread", ["--generator-backend", "badread"], timeout=300)
    case("backend_auto", ["--generator-backend", "auto"], timeout=300)

    # Monitor / quiet
    case("monitor_none", ["--monitor", "none"])
    case("quiet", ["--quiet"])

    # Pipeline validation overlay
    case("pipeline_nanometa", ["--pipeline", "nanometa"])

    return findings


# ---------------------------------------------------------------------
# Phase D5: generate failure modes
# ---------------------------------------------------------------------


def phase_d5_generate_failures(root: Path, genomes: List[Path]) -> List[Finding]:
    findings: List[Finding] = []

    def fail_case(label: str, args: List[str]):
        scenario = f"gen_fail/{label}"
        target = _reset(root / "scratch" / "gen_fail" / label)
        f = Finding(scenario=scenario, phase="D5")
        t0 = time.perf_counter()
        try:
            proc = _run(["generate", "--target", str(target), *args])
            _expect_fail(f, proc)
        except Exception as exc:
            f.fail(f"exception: {exc}")
        f.duration_s = time.perf_counter() - t0
        findings.append(f)

    fail_case("no_genome_source", ["--read-count", "10"])
    fail_case(
        "abundances_wrong_sum",
        [
            "--genomes",
            str(genomes[0]),
            "--genomes",
            str(genomes[1]),
            "--abundances",
            "0.7",
            "--abundances",
            "0.7",
            "--read-count",
            "10",
        ],
    )
    fail_case(
        "unknown_mock", ["--mock", "this_mock_does_not_exist", "--read-count", "10"]
    )
    fail_case(
        "unknown_profile",
        [
            "--genomes",
            str(genomes[0]),
            "--profile",
            "nonexistent_profile_xyz",
            "--read-count",
            "10",
        ],
    )
    fail_case(
        "read_count_zero",
        [
            "--genomes",
            str(genomes[0]),
            "--read-count",
            "0",
        ],
    )
    fail_case(
        "bad_output_format",
        [
            "--genomes",
            str(genomes[0]),
            "--output-format",
            "bam",
            "--read-count",
            "10",
        ],
    )

    return findings


# ---------------------------------------------------------------------
# Phase D6: replay flag sweep
# ---------------------------------------------------------------------


def _make_barcoded_source(root: Path, genomes: List[Path]) -> Path:
    """Create a barcoded source dir to feed replay scenarios."""
    src = _reset(root / "scratch" / "replay_source_barcoded")
    cmd = _gen_baseline(src, genomes) + ["--force-structure", "multiplex"]
    proc = _run(cmd, timeout=240)
    if proc.returncode != 0:
        raise RuntimeError(f"baseline gen failed: {proc.stderr}")
    return src


def phase_d6_replay_sweep(
    root: Path, barcoded_src: Path, flat_src: Path
) -> List[Finding]:
    findings: List[Finding] = []

    def case(
        label: str,
        override: List[str],
        src: Path = barcoded_src,
        extra_assert=None,
        timeout: int = 120,
    ):
        scenario = f"replay/{label}"
        target = _reset(root / "scratch" / "replay" / label)
        f = Finding(scenario=scenario, phase="D6")
        t0 = time.perf_counter()
        try:
            cmd = [
                "replay",
                "--source",
                str(src),
                "--target",
                str(target),
                "--no-wait",
                "--monitor",
                "none",
            ] + override
            proc = _run(cmd, timeout=timeout)
            _expect_ok(f, proc)
            files = _collect_fastq(target)
            f.add(f"files={len(files)}")
            if not files:
                f.fail("no FASTQ produced")
            elif extra_assert is not None:
                extra_assert(f, target, files)
        except Exception as exc:
            f.fail(f"exception: {exc}\n{traceback.format_exc()}")
        f.duration_s = time.perf_counter() - t0
        findings.append(f)

    # Operation
    case("op_copy", ["--operation", "copy"])
    case(
        "op_link",
        ["--operation", "link"],
        extra_assert=lambda f, t, fs: (
            f.fail(f"{len([p for p in fs if not p.is_symlink()])} non-symlinks")
            if any(not p.is_symlink() for p in fs)
            else None
        ),
    )

    # Output structure (and required reads-per-file when reshaping)
    case("out_preserve", ["--output-structure", "preserve"])
    case("out_flat", ["--output-structure", "flat", "--reads-per-file", "25"])
    case(
        "out_barcoded_3",
        [
            "--output-structure",
            "barcoded",
            "--reads-per-file",
            "25",
            "--output-barcodes",
            "3",
        ],
        extra_assert=lambda f, t, fs: (
            f.fail("expected 3 barcode dirs")
            if len(
                [d for d in t.iterdir() if d.is_dir() and d.name.startswith("barcode")]
            )
            != 3
            else None
        ),
    )
    case(
        "out_barcoded_5",
        [
            "--output-structure",
            "barcoded",
            "--reads-per-file",
            "25",
            "--output-barcodes",
            "5",
        ],
    )

    # Custom barcode pattern
    case(
        "custom_pattern",
        [
            "--output-structure",
            "barcoded",
            "--reads-per-file",
            "25",
            "--output-barcodes",
            "3",
            "--output-barcode-pattern",
            "BC{:03d}",
        ],
        extra_assert=lambda f, t, fs: (
            f.fail("custom pattern not applied")
            if not any(d.name.startswith("BC0") for d in t.iterdir() if d.is_dir())
            else None
        ),
    )

    # Custom file prefix
    case(
        "file_prefix",
        [
            "--output-structure",
            "flat",
            "--reads-per-file",
            "25",
            "--output-file-prefix",
            "audit_chunk",
        ],
        extra_assert=lambda f, t, fs: (
            f.fail("prefix not applied")
            if not any(p.name.startswith("audit_chunk") for p in fs)
            else None
        ),
    )

    # Force structure
    case(
        "force_singleplex_flat",
        [
            "--force-structure",
            "singleplex",
            "--output-structure",
            "flat",
            "--reads-per-file",
            "25",
        ],
        src=flat_src,
    )
    case("force_multiplex", ["--force-structure", "multiplex"])

    # Profiles
    for p in ("development", "steady", "bursty", "high_throughput", "gradual_drift"):
        case(f"profile_{p}", ["--profile", p])

    # Parallel / batch
    case(
        "parallel_workers4", ["--parallel", "--worker-count", "4", "--batch-size", "4"]
    )
    case("batch_4", ["--batch-size", "4"])

    return findings


# ---------------------------------------------------------------------
# Phase D7: replay failure modes
# ---------------------------------------------------------------------


def phase_d7_replay_failures(
    root: Path, barcoded_src: Path, flat_src: Path
) -> List[Finding]:
    findings: List[Finding] = []

    def fail_case(label: str, args: List[str]):
        scenario = f"replay_fail/{label}"
        target = _reset(root / "scratch" / "replay_fail" / label)
        f = Finding(scenario=scenario, phase="D7")
        t0 = time.perf_counter()
        try:
            proc = _run(
                [
                    "replay",
                    "--target",
                    str(target),
                    "--no-wait",
                    "--monitor",
                    "none",
                    *args,
                ]
            )
            _expect_fail(f, proc)
        except Exception as exc:
            f.fail(f"exception: {exc}")
        f.duration_s = time.perf_counter() - t0
        findings.append(f)

    fail_case("nonexistent_source", ["--source", str(root / "does_not_exist")])
    fail_case(
        "link_plus_rechunk",
        [
            "--source",
            str(flat_src),
            "--operation",
            "link",
            "--reads-per-file",
            "25",
        ],
    )
    fail_case(
        "link_plus_reshape",
        [
            "--source",
            str(flat_src),
            "--operation",
            "link",
            "--output-structure",
            "flat",
            "--reads-per-file",
            "25",
        ],
    )
    fail_case(
        "barcoded_without_rpf",
        [
            "--source",
            str(flat_src),
            "--output-structure",
            "barcoded",
            "--output-barcodes",
            "3",
        ],
    )
    fail_case(
        "bad_barcode_pattern",
        [
            "--source",
            str(flat_src),
            "--output-structure",
            "barcoded",
            "--reads-per-file",
            "25",
            "--output-barcode-pattern",
            "nopattern",
        ],
    )

    # Source with zero FASTQs
    empty_src = _reset(root / "scratch" / "empty_src")
    fail_case("empty_source_dir", ["--source", str(empty_src)])

    return findings


# ---------------------------------------------------------------------
# Phase D8: download (offline only)
# ---------------------------------------------------------------------


def phase_d8_download(root: Path) -> List[Finding]:
    findings: List[Finding] = []
    f = Finding(scenario="download/help", phase="D8")
    t0 = time.perf_counter()
    try:
        proc = _run(["download", "--help"])
        _expect_ok(f, proc)
        if "Download" not in proc.stdout and "download" not in proc.stdout:
            f.fail("download --help output unexpected")
    except Exception as exc:
        f.fail(f"exception: {exc}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)
    return findings


# ---------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------


def write_report(root: Path, findings: List[Finding]) -> Path:
    path = root / "reports" / "cli-audit-report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    failed = [f for f in findings if not f.passed]
    by_phase: Dict[str, List[Finding]] = {}
    for f in findings:
        by_phase.setdefault(f.phase, []).append(f)
    lines = [
        "# nanorunner CLI subcommand audit",
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


# ---------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------


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
    (root / "scratch").mkdir(exist_ok=True)

    # Synthetic genomes (reuse helper from round 1-2 driver)
    genomes = [
        _synthetic_fasta_for(name, root)
        for name in ("ecoliK12", "bsubtilis168", "saureusNCTC")
    ]

    findings: List[Finding] = []
    findings.extend(phase_d1_info(root))

    # Build a flat single-genome source and a barcoded source for replay tests
    logger.info("building replay sources via generate")
    flat_src = _reset(root / "scratch" / "replay_source_flat")
    proc = _run(
        [
            "generate",
            "--target",
            str(flat_src),
            "--genomes",
            str(genomes[0]),
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
        timeout=120,
    )
    if proc.returncode != 0:
        logger.error("flat source build failed: %s", proc.stderr)
        return 2
    barcoded_src = _make_barcoded_source(root, genomes)

    findings.extend(phase_d2_recommend(root, flat_src))
    findings.extend(phase_d3_validate(root, barcoded_src))
    findings.extend(phase_d4_generate_sweep(root, genomes))
    findings.extend(phase_d5_generate_failures(root, genomes))
    findings.extend(phase_d6_replay_sweep(root, barcoded_src, flat_src))
    findings.extend(phase_d7_replay_failures(root, barcoded_src, flat_src))
    findings.extend(phase_d8_download(root))

    report = write_report(root, findings)
    logger.info("wrote %s", report)
    return 1 if any(not f.passed for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
