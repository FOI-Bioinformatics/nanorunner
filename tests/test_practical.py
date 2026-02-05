"""Practical end-to-end tests using real genomes from NCBI.

These tests download reference genomes via the NCBI datasets CLI and exercise
nanorunner's generate mode with realistic inputs. They are marked as both
``slow`` and ``practical`` and are skipped when the datasets CLI is unavailable.

Run with::

    pytest tests/test_practical.py -v -s
    pytest tests/test_practical.py -m practical -v
"""

import gzip
import shutil
import subprocess
import zipfile

import pytest
from pathlib import Path

from nanopore_simulator.core.config import SimulationConfig
from nanopore_simulator.core.simulator import NanoporeSimulator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

GENOMES = {
    "lambda": {
        "accession": "GCF_000840245.1",
        "name": "Lambda phage",
    },
    "saureus": {
        "accession": "GCF_000013425.1",
        "name": "S. aureus NCTC 8325",
    },
    "ecoli": {
        "accession": "GCF_000005845.2",
        "name": "E. coli K-12 MG1655",
    },
}


def _datasets_available() -> bool:
    """Check whether the NCBI datasets CLI is installed."""
    try:
        r = subprocess.run(
            ["datasets", "--version"], capture_output=True, text=True, timeout=10
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _download_genome(accession: str, dest: Path) -> Path:
    """Download a genome and return the path to the .fna file."""
    zip_path = dest / f"{accession}.zip"
    extract_dir = dest / f"{accession}_extract"

    subprocess.run(
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
        check=True,
    )

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)

    fna_files = list(extract_dir.rglob("*.fna"))
    assert fna_files, f"No .fna file found for {accession}"

    final = dest / f"{accession}.fna"
    shutil.copy2(fna_files[0], final)

    # Clean intermediates
    zip_path.unlink(missing_ok=True)
    shutil.rmtree(extract_dir, ignore_errors=True)

    return final


def validate_fastq(path: Path) -> int:
    """Validate FASTQ format and return read count. Raises on invalid data."""
    if path.suffix == ".gz":
        with gzip.open(path, "rt") as fh:
            content = fh.read()
    else:
        content = path.read_text()

    lines = content.strip().split("\n")
    assert len(lines) % 4 == 0, f"Line count {len(lines)} not divisible by 4"

    read_count = 0
    for i in range(0, len(lines), 4):
        assert lines[i].startswith("@"), f"Line {i+1}: missing @ header"
        assert lines[i + 2].startswith("+"), f"Line {i+3}: missing + separator"
        assert len(lines[i + 1]) == len(
            lines[i + 3]
        ), f"Read {read_count+1}: seq/qual length mismatch"
        read_count += 1

    return read_count


# ---------------------------------------------------------------------------
# Session-scoped genome fixture
# ---------------------------------------------------------------------------

datasets_available = _datasets_available()

skip_no_datasets = pytest.mark.skipif(
    not datasets_available,
    reason="NCBI datasets CLI not available",
)


@pytest.fixture(scope="session")
def genome_cache(tmp_path_factory):
    """Download genomes once per session and cache them."""
    if not datasets_available:
        pytest.skip("NCBI datasets CLI not available")

    cache = tmp_path_factory.mktemp("genomes")
    paths = {}
    for key, info in GENOMES.items():
        paths[key] = _download_genome(info["accession"], cache)
        assert paths[key].exists()
    return paths


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------

pytestmark = [pytest.mark.slow, pytest.mark.practical, skip_no_datasets]


class TestPracticalLambdaPhage:

    def test_lambda_singleplex_uniform(self, genome_cache, tmp_path):
        """Generate reads from Lambda phage in singleplex mode."""
        target = tmp_path / "out"
        config = SimulationConfig(
            target_dir=target,
            operation="generate",
            genome_inputs=[genome_cache["lambda"]],
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
        assert len(fq_files) == 2  # ceil(50/25) = 2
        total = sum(validate_fastq(f) for f in fq_files)
        assert total == 50

    def test_lambda_gzipped_output(self, genome_cache, tmp_path):
        """Generate gzipped FASTQ from Lambda phage."""
        target = tmp_path / "out"
        config = SimulationConfig(
            target_dir=target,
            operation="generate",
            genome_inputs=[genome_cache["lambda"]],
            force_structure="singleplex",
            read_count=20,
            reads_per_file=20,
            mean_read_length=300,
            std_read_length=100,
            min_read_length=50,
            output_format="fastq.gz",
            interval=0.0,
            timing_model="uniform",
        )
        sim = NanoporeSimulator(config, enable_monitoring=False)
        sim.run_simulation()

        gz_files = list(target.glob("*.fastq.gz"))
        assert len(gz_files) >= 1
        for gz in gz_files:
            validate_fastq(gz)


class TestPracticalMultiplex:

    def test_multiplex_two_genomes(self, genome_cache, tmp_path):
        """Two genomes assigned to barcode directories."""
        target = tmp_path / "out"
        config = SimulationConfig(
            target_dir=target,
            operation="generate",
            genome_inputs=[genome_cache["lambda"], genome_cache["saureus"]],
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

        for i in (1, 2):
            bdir = target / f"barcode{i:02d}"
            assert bdir.is_dir()
            fq = list(bdir.glob("*.fastq"))
            assert len(fq) >= 1
            for f in fq:
                validate_fastq(f)

    def test_multiplex_all_three(self, genome_cache, tmp_path):
        """All three genomes in multiplex barcode layout."""
        target = tmp_path / "out"
        config = SimulationConfig(
            target_dir=target,
            operation="generate",
            genome_inputs=[
                genome_cache["lambda"],
                genome_cache["saureus"],
                genome_cache["ecoli"],
            ],
            read_count=10,
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

        for i in (1, 2, 3):
            bdir = target / f"barcode{i:02d}"
            assert bdir.is_dir()
            fq = list(bdir.glob("*.fastq"))
            assert len(fq) >= 1
            for f in fq:
                validate_fastq(f)


class TestPracticalSingleplex:

    def test_singleplex_separate(self, genome_cache, tmp_path):
        """Two genomes in singleplex, separate files per genome."""
        target = tmp_path / "out"
        config = SimulationConfig(
            target_dir=target,
            operation="generate",
            genome_inputs=[genome_cache["lambda"], genome_cache["saureus"]],
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
        # 2 genomes * ceil(30/15) = 4
        assert len(fq_files) == 4
        barcode_dirs = [
            d for d in target.iterdir() if d.is_dir() and d.name.startswith("barcode")
        ]
        assert len(barcode_dirs) == 0

    def test_singleplex_mixed(self, genome_cache, tmp_path):
        """Two genomes in singleplex with mix_reads=True."""
        target = tmp_path / "out"
        config = SimulationConfig(
            target_dir=target,
            operation="generate",
            genome_inputs=[genome_cache["lambda"], genome_cache["saureus"]],
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
        assert len(fq_files) >= 1
        for f in fq_files:
            validate_fastq(f)


class TestPracticalTimingModels:

    def test_poisson_ecoli(self, genome_cache, tmp_path):
        """E. coli generation with Poisson timing model."""
        target = tmp_path / "out"
        config = SimulationConfig(
            target_dir=target,
            operation="generate",
            genome_inputs=[genome_cache["ecoli"]],
            force_structure="singleplex",
            read_count=20,
            reads_per_file=10,
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
        assert len(fq_files) >= 1
        for f in fq_files:
            validate_fastq(f)

    def test_random_saureus(self, genome_cache, tmp_path):
        """S. aureus generation with random timing model."""
        target = tmp_path / "out"
        config = SimulationConfig(
            target_dir=target,
            operation="generate",
            genome_inputs=[genome_cache["saureus"]],
            force_structure="singleplex",
            read_count=20,
            reads_per_file=10,
            mean_read_length=800,
            std_read_length=300,
            min_read_length=150,
            output_format="fastq",
            interval=0.01,
            timing_model="random",
            timing_model_params={"random_factor": 0.5},
        )
        sim = NanoporeSimulator(config, enable_monitoring=False)
        sim.run_simulation()

        fq_files = list(target.rglob("*.fastq"))
        assert len(fq_files) >= 1
        for f in fq_files:
            validate_fastq(f)


class TestPracticalParallel:

    def test_parallel_generation(self, genome_cache, tmp_path):
        """Parallel generation with all three genomes."""
        target = tmp_path / "out"
        config = SimulationConfig(
            target_dir=target,
            operation="generate",
            genome_inputs=[
                genome_cache["lambda"],
                genome_cache["saureus"],
                genome_cache["ecoli"],
            ],
            read_count=10,
            reads_per_file=10,
            mean_read_length=500,
            std_read_length=200,
            min_read_length=100,
            output_format="fastq",
            interval=0.0,
            timing_model="uniform",
            parallel_processing=True,
            worker_count=3,
        )
        sim = NanoporeSimulator(config, enable_monitoring=False)
        sim.run_simulation()

        fq_files = list(target.rglob("*.fastq"))
        assert len(fq_files) >= 3
        for f in fq_files:
            validate_fastq(f)


class TestPracticalEdgeCases:

    def test_zero_interval(self, genome_cache, tmp_path):
        """Generation with interval=0.0 completes without delay."""
        target = tmp_path / "out"
        config = SimulationConfig(
            target_dir=target,
            operation="generate",
            genome_inputs=[genome_cache["lambda"]],
            force_structure="singleplex",
            read_count=10,
            reads_per_file=10,
            mean_read_length=200,
            std_read_length=50,
            min_read_length=50,
            output_format="fastq",
            interval=0.0,
            timing_model="uniform",
        )
        sim = NanoporeSimulator(config, enable_monitoring=False)
        sim.run_simulation()

        fq_files = list(target.glob("*.fastq"))
        assert len(fq_files) >= 1
        total = sum(validate_fastq(f) for f in fq_files)
        assert total == 10

    def test_very_short_reads(self, genome_cache, tmp_path):
        """Generation with short read parameters."""
        target = tmp_path / "out"
        config = SimulationConfig(
            target_dir=target,
            operation="generate",
            genome_inputs=[genome_cache["lambda"]],
            force_structure="singleplex",
            read_count=20,
            reads_per_file=20,
            mean_read_length=50,
            std_read_length=10,
            min_read_length=20,
            output_format="fastq",
            interval=0.0,
            timing_model="uniform",
        )
        sim = NanoporeSimulator(config, enable_monitoring=False)
        sim.run_simulation()

        fq_files = list(target.glob("*.fastq"))
        assert len(fq_files) >= 1
        for f in fq_files:
            validate_fastq(f)
