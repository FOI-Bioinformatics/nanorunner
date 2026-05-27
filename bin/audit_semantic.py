#!/usr/bin/env python
"""Round 5 semantic + adversarial input audit for nanorunner.

Verifies the *content* of generated reads matches what a downstream
bioinformatics consumer expects, and probes the generate path with
adversarial FASTA inputs (N-bases, sequences shorter than the
requested read length, multi-chromosome references, empty records).

Usage:
    python bin/audit_semantic.py \
        --root /Volumes/LaCie/nanorunner/audit-2026-05-27-round5

Exits non-zero on any failure. Report at
``<root>/reports/semantic-report.md``.
"""

from __future__ import annotations

import argparse
import gzip
import logging
import shutil
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_simulate_replay import _collect_fastq, _read_count  # noqa: E402

logger = logging.getLogger("audit-r5")
NANORUNNER = "nanorunner"


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
        [NANORUNNER, *args], capture_output=True, text=True, timeout=timeout
    )


def _write_fasta(path: Path, records: List[Tuple[str, str]]) -> None:
    """Write a multi-record FASTA file (no gzip)."""
    with path.open("w") as fh:
        for name, seq in records:
            fh.write(f">{name}\n")
            for i in range(0, len(seq), 80):
                fh.write(seq[i : i + 80] + "\n")


def _all_sequences_in_fasta(path: Path) -> List[str]:
    """Return all sequences (uppercase, concatenated per record)."""
    out: List[str] = []
    cur: List[str] = []
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt") as fh:
        for line in fh:
            line = line.rstrip()
            if not line:
                continue
            if line.startswith(">"):
                if cur:
                    out.append("".join(cur).upper())
                    cur = []
            else:
                cur.append(line)
        if cur:
            out.append("".join(cur).upper())
    return out


def _iter_fastq_records(path: Path):
    from nanopore_simulator.fastq import iter_reads

    yield from iter_reads(path)


# ---------------------------------------------------------------------
# Phase M: semantic correctness
# ---------------------------------------------------------------------


def phase_m_semantic_substring(root: Path) -> List[Finding]:
    """Every generated read (or its reverse complement) must be a
    substring of one of the source genome's sequences. BuiltinGenerator
    samples subsequences directly, so any drift here means real data
    corruption."""
    findings: List[Finding] = []
    src_fa = root / "m_semantic" / "ref.fa"
    src_fa.parent.mkdir(parents=True, exist_ok=True)
    # Two distinct chromosomes with known content
    chr1 = "ACGT" * 1500  # 6000 bp
    chr2 = "GGCCAATT" * 800  # 6400 bp
    _write_fasta(src_fa, [("chr1", chr1), ("chr2", chr2)])

    target = _reset(root / "m_semantic" / "out")
    f = Finding(scenario="semantic/reads_are_substrings", phase="M")
    t0 = time.perf_counter()
    try:
        proc = _run(
            [
                "generate",
                "--target",
                str(target),
                "--genomes",
                str(src_fa),
                "--read-count",
                "40",
                "--reads-per-file",
                "10",
                "--mean-read-length",
                "200",
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
        if proc.returncode != 0:
            f.fail(f"generate failed: {proc.stderr[-300:]}")
        else:
            sources = _all_sequences_in_fasta(src_fa)
            rc_table = str.maketrans("ACGT", "TGCA")

            def revcomp(s: str) -> str:
                return s.translate(rc_table)[::-1]

            bad = 0
            checked = 0
            for fq in _collect_fastq(target):
                for header, seq, _plus, _qual in _iter_fastq_records(fq):
                    checked += 1
                    seq = seq.upper()
                    if not any(seq in s or revcomp(seq) in s for s in sources):
                        bad += 1
                        if bad <= 3:
                            f.add(f"non-substring read: {header} len={len(seq)}")
            f.add(f"reads_checked={checked} non_substrings={bad}")
            if bad:
                f.fail(
                    f"{bad} of {checked} reads are not substrings of any source chromosome"
                )
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)
    return findings


# ---------------------------------------------------------------------
# Phase N: adversarial FASTA inputs
# ---------------------------------------------------------------------


def phase_n_adversarial(root: Path) -> List[Finding]:
    findings: List[Finding] = []
    base = root / "n_adversarial"
    base.mkdir(parents=True, exist_ok=True)

    def case(
        label: str,
        records: List[Tuple[str, str]],
        read_count: int = 30,
        mean_length: int = 200,
        expect_zero_exit: bool = True,
        extra_assert=None,
    ):
        fa = base / f"{label}.fa"
        _write_fasta(fa, records)
        target = _reset(base / label / "out")
        f = Finding(scenario=f"adversarial/{label}", phase="N")
        t0 = time.perf_counter()
        try:
            proc = _run(
                [
                    "generate",
                    "--target",
                    str(target),
                    "--genomes",
                    str(fa),
                    "--read-count",
                    str(read_count),
                    "--reads-per-file",
                    str(max(1, read_count)),
                    "--mean-read-length",
                    str(mean_length),
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
            f.add(f"exit={proc.returncode}")
            if expect_zero_exit and proc.returncode != 0:
                f.fail(f"unexpected non-zero exit: {proc.stderr[-300:]}")
            if not expect_zero_exit and proc.returncode == 0:
                f.fail("expected non-zero exit, got 0")
            files = _collect_fastq(target)
            f.add(f"files={len(files)}")
            if extra_assert is not None and proc.returncode == 0:
                extra_assert(f, target, files)
        except Exception as exc:
            f.fail(f"exception: {exc}\n{traceback.format_exc()}")
        f.duration_s = time.perf_counter() - t0
        findings.append(f)

    # N1: N-bases mixed in
    case(
        "n_bases",
        [("chr1", "ACGTNNNNACGT" * 500)],
        read_count=20,
        mean_length=300,
    )

    # N2: sequence shorter than requested mean_read_length
    def short_assert(f, t, files):
        total = sum(_read_count(p) for p in files)
        if total < 1:
            f.fail("no reads produced from short sequence")
        # Reads must not exceed the source sequence length
        for fq in files:
            for _h, seq, _p, _q in _iter_fastq_records(fq):
                if len(seq) > 200:
                    f.fail(f"read length {len(seq)} exceeds source length 200")
                    return

    case(
        "sequence_shorter_than_mean_length",
        [("short_chr", "ACGT" * 50)],  # 200 bp
        read_count=10,
        mean_length=1000,
        extra_assert=short_assert,
    )

    # N3: multi-chromosome FASTA, reads must come from at least one
    def multi_assert(f, t, files):
        sources = ["A" * 2000, "T" * 2000, "G" * 2000, "C" * 2000]
        from_each = {c: 0 for c in "ATGC"}
        for fq in files:
            for _h, seq, _p, _q in _iter_fastq_records(fq):
                s = seq.upper()
                # A read should be predominantly one of the homopolymer bases
                # because each chromosome is a single base repeated.
                for base in "ATGC":
                    if s.count(base) > len(s) * 0.9:
                        from_each[base] += 1
                        break
        f.add(f"reads_per_chrom={from_each}")
        # We don't require every chromosome appears -- reservoir bias
        # is allowed -- but at least 2 of 4 should contribute.
        if sum(1 for v in from_each.values() if v > 0) < 2:
            f.fail(f"reads sampled from too few chromosomes: {from_each}")

    case(
        "multi_chromosome_homopolymers",
        [
            ("chrA", "A" * 2000),
            ("chrT", "T" * 2000),
            ("chrG", "G" * 2000),
            ("chrC", "C" * 2000),
        ],
        read_count=40,
        mean_length=200,
        extra_assert=multi_assert,
    )

    # N4: lowercase bases must be uppercased in output (or accepted)
    def lower_assert(f, t, files):
        for fq in files:
            for _h, seq, _p, _q in _iter_fastq_records(fq):
                if any(c.islower() for c in seq):
                    f.fail("output contains lowercase bases (not normalised)")
                    return

    case(
        "lowercase_bases",
        [("lower", "acgt" * 500)],
        read_count=15,
        mean_length=200,
        extra_assert=lower_assert,
    )

    # N5: single record exactly mean_read_length long
    case(
        "sequence_exactly_mean_length",
        [("exact", "ACGT" * 50)],  # 200 bp == mean_length
        read_count=10,
        mean_length=200,
    )

    # N6: empty FASTA must produce a clean non-zero exit, not a crash
    empty_fa = base / "empty.fa"
    empty_fa.write_text("")
    target = _reset(base / "empty_fa" / "out")
    f = Finding(scenario="adversarial/empty_fasta", phase="N")
    t0 = time.perf_counter()
    try:
        proc = _run(
            [
                "generate",
                "--target",
                str(target),
                "--genomes",
                str(empty_fa),
                "--read-count",
                "10",
                "--reads-per-file",
                "10",
                "--no-wait",
                "--monitor",
                "none",
                "--generator-backend",
                "builtin",
                "--output-format",
                "fastq",
            ],
            timeout=30,
        )
        f.add(f"exit={proc.returncode}")
        if proc.returncode == 0:
            f.fail("expected non-zero exit on empty FASTA")
        if "Traceback" in proc.stderr:
            f.fail(f"unhandled traceback: {proc.stderr[-300:]}")
    except Exception as exc:
        f.fail(f"exception: {exc}\n{traceback.format_exc()}")
    f.duration_s = time.perf_counter() - t0
    findings.append(f)

    return findings


# ---------------------------------------------------------------------
# Phase O: boundary read-count / chunk values
# ---------------------------------------------------------------------


def phase_o_boundaries(root: Path) -> List[Finding]:
    findings: List[Finding] = []
    base = root / "o_boundary"
    base.mkdir(parents=True, exist_ok=True)
    ref = base / "ref.fa"
    _write_fasta(ref, [("chr1", "ACGT" * 1000)])

    def case(label: str, override: List[str], expect_zero: bool = True):
        target = _reset(base / label / "out")
        f = Finding(scenario=f"boundary/{label}", phase="O")
        t0 = time.perf_counter()
        try:
            proc = _run(
                [
                    "generate",
                    "--target",
                    str(target),
                    "--genomes",
                    str(ref),
                    "--no-wait",
                    "--monitor",
                    "none",
                    "--generator-backend",
                    "builtin",
                    "--force-structure",
                    "singleplex",
                    "--output-format",
                    "fastq",
                ]
                + override,
                timeout=30,
            )
            f.add(f"exit={proc.returncode}")
            if expect_zero and proc.returncode != 0:
                f.fail(f"unexpected non-zero: {proc.stderr[-300:]}")
            if not expect_zero and proc.returncode == 0:
                f.fail("expected non-zero, got 0")
        except Exception as exc:
            f.fail(f"exception: {exc}\n{traceback.format_exc()}")
        f.duration_s = time.perf_counter() - t0
        findings.append(f)

    case("read_count_1", ["--read-count", "1", "--reads-per-file", "1"])
    case(
        "reads_per_file_1",
        ["--read-count", "10", "--reads-per-file", "1"],
    )
    case(
        "read_count_negative",
        ["--read-count", "-5", "--reads-per-file", "1"],
        expect_zero=False,
    )
    case(
        "reads_per_file_zero",
        ["--read-count", "10", "--reads-per-file", "0"],
        expect_zero=False,
    )
    case(
        "mean_quality_negative",
        ["--read-count", "5", "--mean-quality", "-1"],
        expect_zero=False,
    )
    return findings


# ---------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------


def write_report(root: Path, findings: List[Finding]) -> Path:
    path = root / "reports" / "semantic-report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    failed = [f for f in findings if not f.passed]
    by_phase: Dict[str, List[Finding]] = {}
    for f in findings:
        by_phase.setdefault(f.phase, []).append(f)
    lines = [
        "# nanorunner semantic + adversarial audit (round 5)",
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
    findings.extend(phase_m_semantic_substring(root))
    findings.extend(phase_n_adversarial(root))
    findings.extend(phase_o_boundaries(root))

    report = write_report(root, findings)
    logger.info("wrote %s", report)
    return 1 if any(not f.passed for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
