#!/usr/bin/env python3
"""
Example 6: Practical Genome Test

Description:
    Downloads real genomes from NCBI and exercises nanorunner's generate mode
    end-to-end. Demonstrates singleplex, multiplex, mixed-read, and
    timing-model scenarios using actual microbial reference sequences.

Usage:
    python examples/06_practical_genome_test.py

Requirements:
    - nanorunner installed
    - NCBI datasets CLI (https://www.ncbi.nlm.nih.gov/datasets/docs/v2/download-and-install/)

Expected Output:
    - Downloads Lambda phage, S. aureus, and E. coli genomes (cached)
    - Runs 5 progressive scenarios validating generate mode
    - Prints summary statistics for each scenario

Cleanup:
    - Genome cache: rm -rf ~/.cache/nanorunner_genomes/
    - Output files are cleaned up automatically between scenarios
"""

import gzip
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


# ---------------------------------------------------------------------------
# Genome download helper
# ---------------------------------------------------------------------------

GENOMES = {
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


class GenomeDownloader:
    """Downloads and caches reference genomes from NCBI using the datasets CLI."""

    def __init__(self, cache_dir: Path = CACHE_DIR):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _find_fna(self, extract_dir: Path) -> Path:
        """Locate the .fna file inside an extracted datasets zip."""
        fna_files = list(extract_dir.rglob("*.fna"))
        if not fna_files:
            raise FileNotFoundError(
                f"No .fna file found in {extract_dir}"
            )
        return fna_files[0]

    def download(self, key: str) -> Path:
        """Return path to a genome FASTA, downloading if necessary."""
        info = GENOMES[key]
        cached = self.cache_dir / f"{key}.fna"
        if cached.exists():
            print(f"  [cached] {info['name']} ({cached})")
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

        # Clean up intermediate files
        zip_path.unlink(missing_ok=True)
        shutil.rmtree(extract_dir, ignore_errors=True)

        size_kb = cached.stat().st_size / 1024
        print(f"  Saved {info['name']}: {size_kb:.0f} KB")
        return cached

    def download_all(self) -> dict:
        """Download all configured genomes. Returns {key: Path}."""
        paths = {}
        for key in GENOMES:
            paths[key] = self.download(key)
        return paths


# ---------------------------------------------------------------------------
# FASTQ validation
# ---------------------------------------------------------------------------


def validate_fastq_format(path: Path) -> dict:
    """Validate FASTQ file and return basic statistics.

    Returns dict with keys: valid, read_count, error (if invalid).
    """
    if path.suffix == ".gz":
        opener = gzip.open
    else:
        opener = open

    read_count = 0
    try:
        with opener(path, "rt") as fh:
            lines = fh.read().strip().split("\n")

        if len(lines) % 4 != 0:
            return {"valid": False, "read_count": 0,
                    "error": f"Line count {len(lines)} not divisible by 4"}

        for i in range(0, len(lines), 4):
            header = lines[i]
            seq = lines[i + 1]
            sep = lines[i + 2]
            qual = lines[i + 3]

            if not header.startswith("@"):
                return {"valid": False, "read_count": read_count,
                        "error": f"Line {i+1}: header does not start with @"}
            if not sep.startswith("+"):
                return {"valid": False, "read_count": read_count,
                        "error": f"Line {i+3}: separator does not start with +"}
            if len(seq) != len(qual):
                return {"valid": False, "read_count": read_count,
                        "error": f"Read {read_count+1}: seq/qual length mismatch"}
            read_count += 1

    except Exception as e:
        return {"valid": False, "read_count": read_count, "error": str(e)}

    return {"valid": True, "read_count": read_count}


# ---------------------------------------------------------------------------
# Prerequisite checks
# ---------------------------------------------------------------------------


def check_prerequisites() -> bool:
    """Verify that nanorunner and datasets CLI are available."""
    ok = True

    try:
        from nanopore_simulator import SimulationConfig, NanoporeSimulator  # noqa: F401
    except ImportError:
        print("ERROR: nanorunner is not installed. Run: pip install -e .")
        ok = False

    result = subprocess.run(
        ["datasets", "--version"], capture_output=True, text=True
    )
    if result.returncode != 0:
        print("ERROR: NCBI datasets CLI not found.")
        print("Install from: https://www.ncbi.nlm.nih.gov/datasets/docs/v2/download-and-install/")
        ok = False

    return ok


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def scenario_1_lambda_quick(genome_paths: dict, work_dir: Path):
    """Quick Lambda phage test: 50 reads, uniform timing, singleplex."""
    from nanopore_simulator import SimulationConfig, NanoporeSimulator

    print("\n--- Scenario 1: Quick Lambda phage test ---")

    target = work_dir / "scenario1"
    config = SimulationConfig(
        target_dir=target,
        operation="generate",
        genome_inputs=[genome_paths["lambda"]],
        force_structure="singleplex",
        read_count=50,
        reads_per_file=25,
        mean_read_length=500,
        std_read_length=200,
        min_read_length=100,
        output_format="fastq",
        interval=0.0,
        timing_model="uniform",
    )
    sim = NanoporeSimulator(config, enable_monitoring=False)
    sim.run_simulation()

    fq_files = list(target.glob("*.fastq"))
    total_reads = 0
    for fq in fq_files:
        result = validate_fastq_format(fq)
        assert result["valid"], f"Invalid FASTQ: {result['error']}"
        total_reads += result["read_count"]

    print(f"  Files: {len(fq_files)}, Total reads: {total_reads}")
    print("  PASSED")


def scenario_2_singleplex_multiple(genome_paths: dict, work_dir: Path):
    """Singleplex with two genomes, separate files."""
    from nanopore_simulator import SimulationConfig, NanoporeSimulator

    print("\n--- Scenario 2: Singleplex multiple genomes ---")

    target = work_dir / "scenario2"
    config = SimulationConfig(
        target_dir=target,
        operation="generate",
        genome_inputs=[genome_paths["lambda"], genome_paths["saureus"]],
        force_structure="singleplex",
        read_count=30,
        reads_per_file=15,
        mean_read_length=500,
        std_read_length=200,
        min_read_length=100,
        output_format="fastq",
        mix_reads=False,
        interval=0.0,
        timing_model="uniform",
    )
    sim = NanoporeSimulator(config, enable_monitoring=False)
    sim.run_simulation()

    fq_files = list(target.glob("*.fastq"))
    # No barcode directories in singleplex
    barcode_dirs = [d for d in target.iterdir() if d.is_dir() and d.name.startswith("barcode")]
    assert len(barcode_dirs) == 0, "Unexpected barcode directories in singleplex mode"

    total_reads = 0
    for fq in fq_files:
        result = validate_fastq_format(fq)
        assert result["valid"], f"Invalid FASTQ: {result['error']}"
        total_reads += result["read_count"]

    print(f"  Files: {len(fq_files)}, Total reads: {total_reads}")
    print("  PASSED")


def scenario_3_multiplex(genome_paths: dict, work_dir: Path):
    """Multiplex with all three genomes in barcode directories."""
    from nanopore_simulator import SimulationConfig, NanoporeSimulator

    print("\n--- Scenario 3: Multiplex barcodes ---")

    target = work_dir / "scenario3"
    config = SimulationConfig(
        target_dir=target,
        operation="generate",
        genome_inputs=[
            genome_paths["lambda"],
            genome_paths["saureus"],
            genome_paths["ecoli"],
        ],
        read_count=20,
        reads_per_file=10,
        mean_read_length=500,
        std_read_length=200,
        min_read_length=100,
        output_format="fastq",
        interval=0.0,
        timing_model="uniform",
    )
    sim = NanoporeSimulator(config, enable_monitoring=False)
    sim.run_simulation()

    for i in range(1, 4):
        bdir = target / f"barcode{i:02d}"
        assert bdir.is_dir(), f"Missing {bdir.name}"
        fq_files = list(bdir.glob("*.fastq"))
        assert len(fq_files) >= 1, f"No FASTQ files in {bdir.name}"
        for fq in fq_files:
            result = validate_fastq_format(fq)
            assert result["valid"], f"Invalid FASTQ in {bdir.name}: {result['error']}"
        print(f"  {bdir.name}: {len(fq_files)} files")

    print("  PASSED")


def scenario_4_mixed(genome_paths: dict, work_dir: Path):
    """Mixed reads from Lambda + S. aureus in singleplex mode."""
    from nanopore_simulator import SimulationConfig, NanoporeSimulator

    print("\n--- Scenario 4: Mixed reads ---")

    target = work_dir / "scenario4"
    config = SimulationConfig(
        target_dir=target,
        operation="generate",
        genome_inputs=[genome_paths["lambda"], genome_paths["saureus"]],
        force_structure="singleplex",
        read_count=20,
        reads_per_file=10,
        mean_read_length=500,
        std_read_length=200,
        min_read_length=100,
        output_format="fastq",
        mix_reads=True,
        interval=0.0,
        timing_model="uniform",
    )
    sim = NanoporeSimulator(config, enable_monitoring=False)
    sim.run_simulation()

    fq_files = list(target.glob("*.fastq"))
    total_reads = 0
    for fq in fq_files:
        result = validate_fastq_format(fq)
        assert result["valid"], f"Invalid FASTQ: {result['error']}"
        total_reads += result["read_count"]

    print(f"  Files: {len(fq_files)}, Total reads: {total_reads}")
    print("  PASSED")


def scenario_5_poisson(genome_paths: dict, work_dir: Path):
    """E. coli with Poisson timing model."""
    from nanopore_simulator import SimulationConfig, NanoporeSimulator

    print("\n--- Scenario 5: Poisson timing ---")

    target = work_dir / "scenario5"
    config = SimulationConfig(
        target_dir=target,
        operation="generate",
        genome_inputs=[genome_paths["ecoli"]],
        force_structure="singleplex",
        read_count=30,
        reads_per_file=15,
        mean_read_length=1000,
        std_read_length=400,
        min_read_length=200,
        output_format="fastq",
        interval=0.01,
        timing_model="poisson",
        timing_model_params={
            "burst_probability": 0.2,
            "burst_rate_multiplier": 3.0,
        },
    )
    sim = NanoporeSimulator(config, enable_monitoring=False)
    sim.run_simulation()

    fq_files = list(target.rglob("*.fastq"))
    total_reads = 0
    for fq in fq_files:
        result = validate_fastq_format(fq)
        assert result["valid"], f"Invalid FASTQ: {result['error']}"
        total_reads += result["read_count"]

    print(f"  Files: {len(fq_files)}, Total reads: {total_reads}")
    print("  PASSED")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    print("=" * 60)
    print("Example 6: Practical Genome Test")
    print("=" * 60)

    if not check_prerequisites():
        return 1

    print("\nDownloading genomes...")
    downloader = GenomeDownloader()
    genome_paths = downloader.download_all()

    work_dir = Path(tempfile.mkdtemp(prefix="nanorunner_practical_"))
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
