#!/usr/bin/env python3
"""
Example 6: Generate Mode with Real Genomes

Level: Advanced
Time: ~5 minutes (first run downloads genomes; subsequent runs use cache)
Description:
    Downloads three microbial reference genomes from NCBI and exercises
    nanorunner's generate mode end-to-end. Covers five progressive
    scenarios:

      1. Quick Lambda phage test    -- 50 reads, uniform timing, singleplex
      2. Singleplex multiple genomes -- separate output files per genome
      3. Multiplex barcodes          -- barcode01..03 directory layout
      4. Mixed reads                 -- reads from two genomes in shared files
      5. Poisson timing              -- irregular burst timing on E. coli

    The builtin generator is used in all scenarios (no external tools
    required). Generated reads are error-free random subsequences from
    the reference sequence with log-normal length distribution.

Usage:
    python examples/06_practical_genome_test.py

Requirements:
    - nanorunner installed (pip install -e .)
    - NCBI datasets CLI: https://www.ncbi.nlm.nih.gov/datasets/docs/v2/download-and-install/

Cleanup:
    Genome cache:  rm -rf ~/.cache/nanorunner_genomes/
    Work directory is removed automatically after each run.
"""

import gzip
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Dict


# ---------------------------------------------------------------------------
# Genome catalogue
# ---------------------------------------------------------------------------

GENOMES: Dict[str, Dict] = {
    "lambda": {
        "accession": "GCF_000840245.1",
        "name": "Lambda phage",
        "expected_size_kb": 48,
    },
    "saureus": {
        "accession": "GCF_000013425.1",
        "name": "S. aureus NCTC 8325",
        "expected_size_kb": 2800,
    },
    "ecoli": {
        "accession": "GCF_000005845.2",
        "name": "E. coli K-12 MG1655",
        "expected_size_kb": 4600,
    },
}

CACHE_DIR = Path.home() / ".cache" / "nanorunner_genomes"


# ---------------------------------------------------------------------------
# Genome downloader
# ---------------------------------------------------------------------------


class GenomeDownloader:
    """Download and cache reference genomes from NCBI using the datasets CLI."""

    def __init__(self, cache_dir: Path = CACHE_DIR) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _find_fna(self, extract_dir: Path) -> Path:
        """Locate the first .fna file inside an extracted datasets archive."""
        fna_files = list(extract_dir.rglob("*.fna"))
        if not fna_files:
            raise FileNotFoundError(f"No .fna file found in {extract_dir}")
        return fna_files[0]

    def download(self, key: str) -> Path:
        """Return path to a genome FASTA, downloading from NCBI if necessary.

        Args:
            key: A key in the GENOMES catalogue.

        Returns:
            Path to the cached FASTA file.
        """
        info = GENOMES[key]
        cached = self.cache_dir / f"{key}.fna"
        if cached.exists():
            print(f"  [cached] {info['name']} ({cached.name})")
            return cached

        accession = info["accession"]
        zip_path = self.cache_dir / f"{key}.zip"
        extract_dir = self.cache_dir / f"{key}_extract"

        print(f"  Downloading {info['name']} ({accession})...")
        result = subprocess.run(
            [
                "datasets",
                "download",
                "genome",
                "accession",
                accession,
                "--include",
                "genome",
                "--filename",
                str(zip_path),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"datasets download failed: {result.stderr.strip()}"
            )

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)

        fna = self._find_fna(extract_dir)
        shutil.copy2(fna, cached)

        zip_path.unlink(missing_ok=True)
        shutil.rmtree(extract_dir, ignore_errors=True)

        size_kb = cached.stat().st_size / 1024
        print(f"  Saved {info['name']}: {size_kb:.0f} KB")
        return cached

    def download_all(self) -> Dict[str, Path]:
        """Download all genomes in the catalogue. Returns {key: Path}."""
        paths: Dict[str, Path] = {}
        for key in GENOMES:
            paths[key] = self.download(key)
        return paths


# ---------------------------------------------------------------------------
# FASTQ validation
# ---------------------------------------------------------------------------


def validate_fastq(path: Path) -> Dict:
    """Validate a FASTQ file and return basic statistics.

    Returns a dict with keys: valid (bool), read_count (int),
    and error (str, only present when valid is False).
    """
    opener = gzip.open if path.suffix == ".gz" else open
    read_count = 0
    try:
        with opener(path, "rt") as fh:
            lines = fh.read().strip().split("\n")

        if len(lines) % 4 != 0:
            return {
                "valid": False,
                "read_count": 0,
                "error": f"Line count {len(lines)} not divisible by 4",
            }

        for i in range(0, len(lines), 4):
            header, seq, sep, qual = (
                lines[i], lines[i + 1], lines[i + 2], lines[i + 3]
            )
            if not header.startswith("@"):
                return {
                    "valid": False,
                    "read_count": read_count,
                    "error": f"Line {i + 1}: header does not start with @",
                }
            if not sep.startswith("+"):
                return {
                    "valid": False,
                    "read_count": read_count,
                    "error": f"Line {i + 3}: separator does not start with +",
                }
            if len(seq) != len(qual):
                return {
                    "valid": False,
                    "read_count": read_count,
                    "error": f"Read {read_count + 1}: seq/qual length mismatch",
                }
            read_count += 1

    except Exception as exc:
        return {"valid": False, "read_count": read_count, "error": str(exc)}

    return {"valid": True, "read_count": read_count}


# ---------------------------------------------------------------------------
# Prerequisite check
# ---------------------------------------------------------------------------


def check_prerequisites() -> bool:
    """Verify that nanorunner and the NCBI datasets CLI are available."""
    ok = True

    try:
        from nanopore_simulator import GenerateConfig, run_generate  # noqa: F401
    except ImportError:
        print("ERROR: nanorunner is not installed. Run: pip install -e .")
        ok = False

    result = subprocess.run(
        ["datasets", "--version"], capture_output=True, text=True
    )
    if result.returncode != 0:
        print("ERROR: NCBI datasets CLI not found.")
        print(
            "Install from: "
            "https://www.ncbi.nlm.nih.gov/datasets/docs/v2/download-and-install/"
        )
        ok = False

    return ok


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def scenario_1_lambda_quick(genome_paths: Dict[str, Path], work_dir: Path) -> None:
    """Quick Lambda phage test: 50 reads, uniform timing, singleplex output."""
    from nanopore_simulator import GenerateConfig, run_generate

    print("\n--- Scenario 1: Lambda phage quick test ---")

    target = work_dir / "scenario1"
    config = GenerateConfig(
        target_dir=target,
        genome_inputs=[genome_paths["lambda"]],
        structure="singleplex",
        read_count=50,
        reads_per_file=25,
        mean_length=500,
        std_length=200,
        min_length=100,
        output_format="fastq",
        interval=0.0,
        timing_model="uniform",
        monitor_type="none",
        generator_backend="builtin",
    )
    run_generate(config)

    fq_files = list(target.glob("*.fastq"))
    total_reads = 0
    for fq in fq_files:
        result = validate_fastq(fq)
        assert result["valid"], f"Invalid FASTQ {fq.name}: {result.get('error')}"
        total_reads += result["read_count"]

    print(f"  Files: {len(fq_files)}, Total reads: {total_reads}")
    assert total_reads == 50, f"Expected 50 reads, got {total_reads}"
    print("  PASSED")


def scenario_2_singleplex_multiple(
    genome_paths: Dict[str, Path], work_dir: Path
) -> None:
    """Singleplex with two genomes: separate output files, no barcode dirs."""
    from nanopore_simulator import GenerateConfig, run_generate

    print("\n--- Scenario 2: Singleplex, two genomes ---")

    target = work_dir / "scenario2"
    config = GenerateConfig(
        target_dir=target,
        genome_inputs=[genome_paths["lambda"], genome_paths["saureus"]],
        structure="singleplex",
        read_count=30,
        reads_per_file=15,
        mean_length=500,
        std_length=200,
        min_length=100,
        output_format="fastq",
        mix_reads=False,
        interval=0.0,
        timing_model="uniform",
        monitor_type="none",
        generator_backend="builtin",
    )
    run_generate(config)

    fq_files = list(target.glob("*.fastq"))
    barcode_dirs = [d for d in target.iterdir() if d.is_dir() and d.name.startswith("barcode")]
    assert not barcode_dirs, "Unexpected barcode directories in singleplex mode"

    total_reads = 0
    for fq in fq_files:
        result = validate_fastq(fq)
        assert result["valid"], f"Invalid FASTQ {fq.name}: {result.get('error')}"
        total_reads += result["read_count"]

    print(f"  Files: {len(fq_files)}, Total reads: {total_reads}")
    print("  PASSED")


def scenario_3_multiplex(genome_paths: Dict[str, Path], work_dir: Path) -> None:
    """Multiplex with three genomes: one barcode directory per genome."""
    from nanopore_simulator import GenerateConfig, run_generate

    print("\n--- Scenario 3: Multiplex barcodes ---")

    target = work_dir / "scenario3"
    config = GenerateConfig(
        target_dir=target,
        genome_inputs=[
            genome_paths["lambda"],
            genome_paths["saureus"],
            genome_paths["ecoli"],
        ],
        structure="multiplex",
        read_count=20,
        reads_per_file=10,
        mean_length=500,
        std_length=200,
        min_length=100,
        output_format="fastq",
        interval=0.0,
        timing_model="uniform",
        monitor_type="none",
        generator_backend="builtin",
    )
    run_generate(config)

    for i in range(1, 4):
        bdir = target / f"barcode{i:02d}"
        assert bdir.is_dir(), f"Missing expected directory {bdir.name}"
        fq_files = list(bdir.glob("*.fastq"))
        assert fq_files, f"No FASTQ files found in {bdir.name}"
        for fq in fq_files:
            result = validate_fastq(fq)
            assert result["valid"], (
                f"Invalid FASTQ in {bdir.name}: {result.get('error')}"
            )
        print(f"  {bdir.name}: {len(fq_files)} file(s)")

    print("  PASSED")


def scenario_4_mixed(genome_paths: Dict[str, Path], work_dir: Path) -> None:
    """Mixed reads: Lambda + S. aureus reads interleaved in shared files."""
    from nanopore_simulator import GenerateConfig, run_generate

    print("\n--- Scenario 4: Mixed reads ---")

    target = work_dir / "scenario4"
    config = GenerateConfig(
        target_dir=target,
        genome_inputs=[genome_paths["lambda"], genome_paths["saureus"]],
        structure="singleplex",
        read_count=20,
        reads_per_file=10,
        mean_length=500,
        std_length=200,
        min_length=100,
        output_format="fastq",
        mix_reads=True,
        interval=0.0,
        timing_model="uniform",
        monitor_type="none",
        generator_backend="builtin",
    )
    run_generate(config)

    fq_files = list(target.glob("*.fastq"))
    total_reads = 0
    for fq in fq_files:
        result = validate_fastq(fq)
        assert result["valid"], f"Invalid FASTQ {fq.name}: {result.get('error')}"
        total_reads += result["read_count"]

    print(f"  Files: {len(fq_files)}, Total reads: {total_reads}")
    print("  PASSED")


def scenario_5_poisson(genome_paths: Dict[str, Path], work_dir: Path) -> None:
    """E. coli with Poisson timing model: irregular burst intervals."""
    from nanopore_simulator import GenerateConfig, run_generate

    print("\n--- Scenario 5: Poisson timing ---")

    target = work_dir / "scenario5"
    config = GenerateConfig(
        target_dir=target,
        genome_inputs=[genome_paths["ecoli"]],
        structure="singleplex",
        read_count=30,
        reads_per_file=15,
        mean_length=1000,
        std_length=400,
        min_length=200,
        output_format="fastq",
        interval=0.01,
        timing_model="poisson",
        timing_params={
            "burst_probability": 0.2,
            "burst_rate_multiplier": 3.0,
        },
        monitor_type="none",
        generator_backend="builtin",
    )
    run_generate(config)

    fq_files = list(target.rglob("*.fastq"))
    total_reads = 0
    for fq in fq_files:
        result = validate_fastq(fq)
        assert result["valid"], f"Invalid FASTQ {fq.name}: {result.get('error')}"
        total_reads += result["read_count"]

    print(f"  Files: {len(fq_files)}, Total reads: {total_reads}")
    print("  PASSED")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    print("=" * 60)
    print("Example 6: Generate Mode with Real Genomes")
    print("=" * 60)

    if not check_prerequisites():
        return 1

    print("\nPreparing genomes...")
    downloader = GenomeDownloader()
    genome_paths = downloader.download_all()

    work_dir = Path(tempfile.mkdtemp(prefix="nanorunner_genome_test_"))
    print(f"\nWork directory: {work_dir}")

    try:
        scenario_1_lambda_quick(genome_paths, work_dir)
        scenario_2_singleplex_multiple(genome_paths, work_dir)
        scenario_3_multiplex(genome_paths, work_dir)
        scenario_4_mixed(genome_paths, work_dir)
        scenario_5_poisson(genome_paths, work_dir)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    print("\n" + "=" * 60)
    print("All 5 scenarios passed.")
    print("=" * 60)
    print(f"\nGenome cache: {CACHE_DIR}")
    print("To remove cached genomes: rm -rf ~/.cache/nanorunner_genomes/")

    return 0


if __name__ == "__main__":
    sys.exit(main())
