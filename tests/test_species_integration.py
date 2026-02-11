"""Integration tests for species-based generation (requires network).

These tests verify the full species resolution and generation workflow,
including mock community loading, species name resolution via NCBI,
and simulated read generation. They are marked as both ``slow`` and
``practical`` and are skipped when the NCBI datasets CLI is unavailable.

Note: These tests require network access to query NCBI for genome data.
Some tests may fail if NCBI services are unavailable or rate-limited.

Run with::

    pytest tests/test_species_integration.py -v -s
    pytest tests/test_species_integration.py -m "slow and practical" -v
"""

import gzip

import pytest
from pathlib import Path

from nanopore_simulator.core.config import SimulationConfig
from nanopore_simulator.core.simulator import NanoporeSimulator
from nanopore_simulator.core.species import SpeciesResolver, NCBIResolver


def _datasets_available() -> bool:
    """Check if ncbi-datasets-cli is installed."""
    return NCBIResolver().is_available()


def validate_fastq(path: Path) -> int:
    """Validate FASTQ format and return read count.

    Args:
        path: Path to FASTQ file (plain or gzipped).

    Returns:
        Number of reads in the file.

    Raises:
        AssertionError: If file format is invalid.
    """
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


skip_no_datasets = pytest.mark.skipif(
    not _datasets_available(),
    reason="NCBI datasets CLI not available",
)


@pytest.mark.slow
@pytest.mark.practical
@skip_no_datasets
class TestSpeciesIntegration:
    """Integration tests for species-based read generation."""

    def test_quick_3species_pure(self, tmp_path: Path) -> None:
        """Generate pure samples from quick_3species mock community.

        This test verifies that the quick_3species mock community resolves
        correctly and generates reads into separate barcode directories.
        The quick_3species mock uses E. coli, S. aureus, and B. subtilis,
        which all have reference genomes in NCBI.
        """
        config = SimulationConfig(
            target_dir=tmp_path / "output",
            operation="generate",
            mock_name="quick_3species",
            sample_type="pure",
            read_count=10,
            reads_per_file=10,
            interval=0.0,
        )
        sim = NanoporeSimulator(config, enable_monitoring=False)
        sim.run_simulation()

        # Should have 3 barcode directories (one per species)
        barcodes = list((tmp_path / "output").glob("barcode*"))
        assert len(barcodes) == 3

        # Verify each barcode has valid FASTQ files
        for barcode_dir in barcodes:
            fastq_files = list(barcode_dir.glob("*.fastq*"))
            assert len(fastq_files) >= 1, f"No FASTQ in {barcode_dir.name}"
            for fq in fastq_files:
                validate_fastq(fq)

    def test_species_by_name(self, tmp_path: Path) -> None:
        """Resolve and generate from species name.

        This test verifies that a single species can be resolved by name
        and used to generate simulated reads.
        """
        config = SimulationConfig(
            target_dir=tmp_path / "output",
            operation="generate",
            species_inputs=["Escherichia coli"],
            sample_type="pure",
            read_count=10,
            reads_per_file=10,
            interval=0.0,
        )
        sim = NanoporeSimulator(config, enable_monitoring=False)
        sim.run_simulation()

        fastq_files = list((tmp_path / "output").rglob("*.fastq*"))
        assert len(fastq_files) >= 1
        total_reads = sum(validate_fastq(f) for f in fastq_files)
        assert total_reads == 10


@pytest.mark.slow
@pytest.mark.practical
@skip_no_datasets
class TestSpeciesResolutionWorkflow:
    """Tests for the species resolution workflow."""

    def test_resolver_resolves_species(self) -> None:
        """Verify SpeciesResolver can resolve species.

        This test confirms that the resolver successfully queries GTDB API
        or NCBI for species resolution.
        """
        resolver = SpeciesResolver()
        ref = resolver.resolve("Escherichia coli")

        assert ref is not None
        assert ref.name is not None
        assert ref.accession is not None
        assert ref.source in ("gtdb", "ncbi")

    def test_resolver_suggestions(self) -> None:
        """Verify that the resolver provides suggestions for partial names."""
        resolver = SpeciesResolver()
        suggestions = resolver.suggest("Escherichia")

        # Suggestions may come from GTDB API or local index
        assert isinstance(suggestions, list)


@pytest.mark.slow
@pytest.mark.practical
@skip_no_datasets
class TestSpeciesGenerationParameters:
    """Tests for species-based generation with various parameters."""

    def test_gzipped_output(self, tmp_path: Path) -> None:
        """Generate gzipped FASTQ from species input."""
        config = SimulationConfig(
            target_dir=tmp_path / "output",
            operation="generate",
            species_inputs=["Bacillus subtilis"],
            sample_type="pure",
            read_count=10,
            reads_per_file=10,
            output_format="fastq.gz",
            interval=0.0,
        )
        sim = NanoporeSimulator(config, enable_monitoring=False)
        sim.run_simulation()

        gz_files = list((tmp_path / "output").rglob("*.fastq.gz"))
        assert len(gz_files) >= 1
        for gz in gz_files:
            validate_fastq(gz)

    def test_custom_read_parameters(self, tmp_path: Path) -> None:
        """Generate reads with custom length and quality parameters."""
        config = SimulationConfig(
            target_dir=tmp_path / "output",
            operation="generate",
            species_inputs=["Escherichia coli"],
            sample_type="pure",
            read_count=20,
            reads_per_file=10,
            mean_read_length=1000,
            std_read_length=300,
            min_read_length=200,
            mean_quality=12.0,
            interval=0.0,
        )
        sim = NanoporeSimulator(config, enable_monitoring=False)
        sim.run_simulation()

        fastq_files = list((tmp_path / "output").rglob("*.fastq*"))
        assert len(fastq_files) >= 2  # ceil(20/10) = 2 files per species

        total_reads = sum(validate_fastq(f) for f in fastq_files)
        assert total_reads == 20

    def test_poisson_timing_model(self, tmp_path: Path) -> None:
        """Generate with Poisson timing model from species input."""
        config = SimulationConfig(
            target_dir=tmp_path / "output",
            operation="generate",
            species_inputs=["Escherichia coli"],
            sample_type="pure",
            read_count=10,
            reads_per_file=10,
            interval=0.01,
            timing_model="poisson",
            timing_model_params={
                "burst_probability": 0.2,
                "burst_rate_multiplier": 3.0,
            },
        )
        sim = NanoporeSimulator(config, enable_monitoring=False)
        sim.run_simulation()

        fastq_files = list((tmp_path / "output").rglob("*.fastq*"))
        assert len(fastq_files) >= 1
