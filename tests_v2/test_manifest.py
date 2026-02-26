"""Tests for manifest building (plan phase)."""

import math
from pathlib import Path
from typing import List

import pytest

from nanopore_simulator_v2.config import GenerateConfig, ReplayConfig
from nanopore_simulator_v2.manifest import (
    FileEntry,
    build_generate_manifest,
    build_replay_manifest,
    distribute_reads,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def singleplex_source(tmp_path: Path) -> Path:
    """Create a singleplex source directory with 5 FASTQ files."""
    source = tmp_path / "source_single"
    source.mkdir()
    for i in range(5):
        (source / f"reads_{i}.fastq").write_text(
            f"@read{i}\nACGTACGT\n+\nIIIIIIII\n"
        )
    return source


@pytest.fixture
def multiplex_source(tmp_path: Path) -> Path:
    """Create a multiplex source with 2 barcodes, 3 files each."""
    source = tmp_path / "source_multi"
    source.mkdir()
    for bc in ["barcode01", "barcode02"]:
        bc_dir = source / bc
        bc_dir.mkdir()
        for i in range(3):
            (bc_dir / f"reads_{i}.fastq").write_text(
                f"@read{i}\nACGTACGT\n+\nIIIIIIII\n"
            )
    return source


@pytest.fixture
def empty_source(tmp_path: Path) -> Path:
    """Create an empty source directory."""
    source = tmp_path / "source_empty"
    source.mkdir()
    return source


@pytest.fixture
def genome_a(tmp_path: Path) -> Path:
    """Create a genome FASTA file."""
    fasta = tmp_path / "genome_a.fa"
    fasta.write_text(">chr1\nACGTACGTACGTACGTACGTACGTACGTACGT\n")
    return fasta


@pytest.fixture
def genome_b(tmp_path: Path) -> Path:
    """Create a second genome FASTA file."""
    fasta = tmp_path / "genome_b.fa"
    fasta.write_text(">chr1\nTTTTAAAACCCCGGGGTTTTAAAACCCCGGGG\n")
    return fasta


# ---------------------------------------------------------------------------
# FileEntry dataclass
# ---------------------------------------------------------------------------


class TestFileEntry:
    """Tests for the FileEntry dataclass."""

    def test_replay_entry_defaults(self) -> None:
        entry = FileEntry(
            source=Path("/src/reads.fastq"),
            target=Path("/dst/reads.fastq"),
            operation="copy",
        )
        assert entry.source == Path("/src/reads.fastq")
        assert entry.target == Path("/dst/reads.fastq")
        assert entry.operation == "copy"
        assert entry.genome is None
        assert entry.read_count is None
        assert entry.batch == 0

    def test_generate_entry(self) -> None:
        entry = FileEntry(
            target=Path("/dst/genome_reads_0000.fastq"),
            operation="generate",
            genome=Path("/genomes/ref.fa"),
            read_count=100,
        )
        assert entry.source is None
        assert entry.operation == "generate"
        assert entry.genome == Path("/genomes/ref.fa")
        assert entry.read_count == 100

    def test_link_entry(self) -> None:
        entry = FileEntry(
            source=Path("/src/reads.fastq"),
            target=Path("/dst/reads.fastq"),
            operation="link",
        )
        assert entry.operation == "link"


# ---------------------------------------------------------------------------
# distribute_reads
# ---------------------------------------------------------------------------


class TestDistributeReads:
    """Tests for the largest-remainder read distribution."""

    def test_empty_weights(self) -> None:
        assert distribute_reads(100, []) == []

    def test_single_weight(self) -> None:
        assert distribute_reads(100, [1.0]) == [100]

    def test_equal_split_two(self) -> None:
        result = distribute_reads(100, [0.5, 0.5])
        assert result == [50, 50]

    def test_equal_split_three(self) -> None:
        result = distribute_reads(9, [1 / 3, 1 / 3, 1 / 3])
        assert sum(result) == 9
        assert all(r == 3 for r in result)

    def test_remainder_handling(self) -> None:
        """7 reads across 3 equal genomes: 3+2+2 or similar."""
        result = distribute_reads(7, [1 / 3, 1 / 3, 1 / 3])
        assert sum(result) == 7
        assert all(r >= 2 for r in result)

    def test_abundance_weighted(self) -> None:
        result = distribute_reads(1000, [0.9, 0.1])
        assert result[0] == 900
        assert result[1] == 100
        assert sum(result) == 1000

    def test_abundance_weighted_uneven(self) -> None:
        result = distribute_reads(100, [0.7, 0.2, 0.1])
        assert sum(result) == 100
        assert result[0] == 70
        assert result[1] == 20
        assert result[2] == 10

    def test_minimum_one_read(self) -> None:
        """Very small abundance should still receive at least 1 read."""
        result = distribute_reads(10, [0.99, 0.01])
        assert sum(result) == 10
        assert result[1] >= 1

    def test_sum_always_matches_total(self) -> None:
        """Property: sum of distributed reads equals total when total >= n."""
        weights = [0.5, 0.3, 0.15, 0.05]
        for total in [4, 7, 100, 999, 10000]:
            result = distribute_reads(total, weights)
            assert sum(result) == total, f"Failed for total={total}"

    def test_minimum_guarantee_overallocates(self) -> None:
        """When total < n_organisms, minimum-1 guarantee causes overallocation."""
        result = distribute_reads(1, [0.5, 0.3, 0.15, 0.05])
        # Each organism with weight > 0 gets at least 1
        assert all(r >= 1 for r in result)
        # Sum exceeds total due to minimum guarantee
        assert sum(result) >= 1


# ---------------------------------------------------------------------------
# build_replay_manifest -- singleplex
# ---------------------------------------------------------------------------


class TestBuildReplayManifestSingleplex:
    """Tests for singleplex replay manifest building."""

    def test_correct_count(
        self, singleplex_source: Path, tmp_path: Path
    ) -> None:
        config = ReplayConfig(
            source_dir=singleplex_source,
            target_dir=tmp_path / "target",
            monitor_type="none",
        )
        manifest = build_replay_manifest(config)
        assert len(manifest) == 5

    def test_copy_operations(
        self, singleplex_source: Path, tmp_path: Path
    ) -> None:
        config = ReplayConfig(
            source_dir=singleplex_source,
            target_dir=tmp_path / "target",
            operation="copy",
            monitor_type="none",
        )
        manifest = build_replay_manifest(config)
        assert all(e.operation == "copy" for e in manifest)

    def test_correct_target_paths(
        self, singleplex_source: Path, tmp_path: Path
    ) -> None:
        target = tmp_path / "target"
        config = ReplayConfig(
            source_dir=singleplex_source,
            target_dir=target,
            monitor_type="none",
        )
        manifest = build_replay_manifest(config)
        for entry in manifest:
            assert entry.target.parent == target
            assert entry.target.name == entry.source.name

    def test_link_operation(
        self, singleplex_source: Path, tmp_path: Path
    ) -> None:
        config = ReplayConfig(
            source_dir=singleplex_source,
            target_dir=tmp_path / "target",
            operation="link",
            monitor_type="none",
        )
        manifest = build_replay_manifest(config)
        assert all(e.operation == "link" for e in manifest)

    def test_batching(
        self, singleplex_source: Path, tmp_path: Path
    ) -> None:
        """5 files with batch_size=2 should yield 3 batches (0, 1, 2)."""
        config = ReplayConfig(
            source_dir=singleplex_source,
            target_dir=tmp_path / "target",
            batch_size=2,
            monitor_type="none",
        )
        manifest = build_replay_manifest(config)
        batches = {e.batch for e in manifest}
        assert batches == {0, 1, 2}
        # First two entries in batch 0, next two in batch 1, last in batch 2
        assert sum(1 for e in manifest if e.batch == 0) == 2
        assert sum(1 for e in manifest if e.batch == 1) == 2
        assert sum(1 for e in manifest if e.batch == 2) == 1


# ---------------------------------------------------------------------------
# build_replay_manifest -- multiplex
# ---------------------------------------------------------------------------


class TestBuildReplayManifestMultiplex:
    """Tests for multiplex replay manifest building."""

    def test_preserves_barcode_structure(
        self, multiplex_source: Path, tmp_path: Path
    ) -> None:
        target = tmp_path / "target"
        config = ReplayConfig(
            source_dir=multiplex_source,
            target_dir=target,
            monitor_type="none",
        )
        manifest = build_replay_manifest(config)
        assert len(manifest) == 6  # 2 barcodes * 3 files

        barcodes = {e.barcode for e in manifest}
        assert barcodes == {"barcode01", "barcode02"}

        for entry in manifest:
            # Target should be inside barcode subdir
            assert entry.target.parent == target / entry.barcode

    def test_link_operation_multiplex(
        self, multiplex_source: Path, tmp_path: Path
    ) -> None:
        config = ReplayConfig(
            source_dir=multiplex_source,
            target_dir=tmp_path / "target",
            operation="link",
            monitor_type="none",
        )
        manifest = build_replay_manifest(config)
        assert all(e.operation == "link" for e in manifest)

    def test_forced_singleplex_with_multiplex_source(
        self, multiplex_source: Path, tmp_path: Path
    ) -> None:
        """Forcing singleplex on a multiplex source should find no files
        (files are in barcode subdirs, not root)."""
        config = ReplayConfig(
            source_dir=multiplex_source,
            target_dir=tmp_path / "target",
            structure="singleplex",
            monitor_type="none",
        )
        manifest = build_replay_manifest(config)
        # No files directly in root of multiplex source
        assert len(manifest) == 0


# ---------------------------------------------------------------------------
# build_replay_manifest -- empty source
# ---------------------------------------------------------------------------


class TestBuildReplayManifestEmpty:
    """Tests for edge cases."""

    def test_empty_source_returns_empty(
        self, empty_source: Path, tmp_path: Path
    ) -> None:
        config = ReplayConfig(
            source_dir=empty_source,
            target_dir=tmp_path / "target",
            monitor_type="none",
        )
        manifest = build_replay_manifest(config)
        assert manifest == []


# ---------------------------------------------------------------------------
# build_replay_manifest -- rechunking
# ---------------------------------------------------------------------------


class TestBuildReplayManifestRechunk:
    """Tests for rechunking (reads_per_output set)."""

    def test_rechunk_singleplex(self, tmp_path: Path) -> None:
        """Two source files with 2 reads each, rechunk to 3 reads per output."""
        source = tmp_path / "source_rechunk"
        source.mkdir()
        for i in range(2):
            (source / f"reads_{i}.fastq").write_text(
                f"@readA{i}\nACGT\n+\nIIII\n"
                f"@readB{i}\nTTTT\n+\nIIII\n"
            )
        target = tmp_path / "target"
        config = ReplayConfig(
            source_dir=source,
            target_dir=target,
            operation="copy",
            reads_per_output=3,
            monitor_type="none",
        )
        manifest = build_replay_manifest(config)
        # 4 total reads / 3 per file -> ceil = 2 output files
        rechunk_entries = [e for e in manifest if e.operation == "rechunk"]
        assert len(rechunk_entries) == 2
        # First chunk: 3 reads, second chunk: 1 read
        assert rechunk_entries[0].read_count == 3
        assert rechunk_entries[1].read_count == 1

    def test_rechunk_preserves_pod5(self, tmp_path: Path) -> None:
        """POD5 files should pass through unchanged during rechunking."""
        source = tmp_path / "source_pod5"
        source.mkdir()
        (source / "reads.fastq").write_text(
            "@r1\nACGT\n+\nIIII\n@r2\nTTTT\n+\nIIII\n"
        )
        (source / "signal.pod5").write_bytes(b"\x00" * 10)
        target = tmp_path / "target"
        config = ReplayConfig(
            source_dir=source,
            target_dir=target,
            operation="copy",
            reads_per_output=1,
            monitor_type="none",
        )
        manifest = build_replay_manifest(config)
        pod5_entries = [e for e in manifest if e.operation == "copy"]
        rechunk_entries = [e for e in manifest if e.operation == "rechunk"]
        assert len(pod5_entries) == 1
        assert pod5_entries[0].source.name == "signal.pod5"
        assert len(rechunk_entries) == 2


# ---------------------------------------------------------------------------
# build_generate_manifest -- single genome
# ---------------------------------------------------------------------------


class TestBuildGenerateManifestSingle:
    """Tests for single-genome generate manifest."""

    def test_correct_file_count(
        self, genome_a: Path, tmp_path: Path
    ) -> None:
        config = GenerateConfig(
            target_dir=tmp_path / "target",
            genome_inputs=[genome_a],
            read_count=1000,
            reads_per_file=100,
            monitor_type="none",
        )
        manifest = build_generate_manifest(config)
        assert len(manifest) == 10  # 1000 / 100

    def test_total_reads_distributed(
        self, genome_a: Path, tmp_path: Path
    ) -> None:
        config = GenerateConfig(
            target_dir=tmp_path / "target",
            genome_inputs=[genome_a],
            read_count=250,
            reads_per_file=100,
            monitor_type="none",
        )
        manifest = build_generate_manifest(config)
        total = sum(e.read_count for e in manifest)
        assert total == 250

    def test_all_generate_operations(
        self, genome_a: Path, tmp_path: Path
    ) -> None:
        config = GenerateConfig(
            target_dir=tmp_path / "target",
            genome_inputs=[genome_a],
            read_count=100,
            reads_per_file=50,
            monitor_type="none",
        )
        manifest = build_generate_manifest(config)
        assert all(e.operation == "generate" for e in manifest)


# ---------------------------------------------------------------------------
# build_generate_manifest -- multiple genomes
# ---------------------------------------------------------------------------


class TestBuildGenerateManifestMultiple:
    """Tests for multi-genome generate manifest."""

    def test_equal_split(
        self, genome_a: Path, genome_b: Path, tmp_path: Path
    ) -> None:
        config = GenerateConfig(
            target_dir=tmp_path / "target",
            genome_inputs=[genome_a, genome_b],
            read_count=200,
            reads_per_file=100,
            monitor_type="none",
        )
        manifest = build_generate_manifest(config)
        # 200 reads split equally: 100 each, 1 file per genome
        assert len(manifest) == 2
        genome_a_entries = [e for e in manifest if e.genome == genome_a]
        genome_b_entries = [e for e in manifest if e.genome == genome_b]
        assert sum(e.read_count for e in genome_a_entries) == 100
        assert sum(e.read_count for e in genome_b_entries) == 100

    def test_abundance_weighted(
        self, genome_a: Path, genome_b: Path, tmp_path: Path
    ) -> None:
        config = GenerateConfig(
            target_dir=tmp_path / "target",
            genome_inputs=[genome_a, genome_b],
            abundances=[0.9, 0.1],
            read_count=1000,
            reads_per_file=100,
            monitor_type="none",
        )
        manifest = build_generate_manifest(config)
        genome_a_reads = sum(
            e.read_count for e in manifest if e.genome == genome_a
        )
        genome_b_reads = sum(
            e.read_count for e in manifest if e.genome == genome_b
        )
        assert genome_a_reads == 900
        assert genome_b_reads == 100
        assert genome_a_reads + genome_b_reads == 1000

    def test_total_reads_sum_correct(
        self, genome_a: Path, genome_b: Path, tmp_path: Path
    ) -> None:
        config = GenerateConfig(
            target_dir=tmp_path / "target",
            genome_inputs=[genome_a, genome_b],
            read_count=333,
            reads_per_file=50,
            monitor_type="none",
        )
        manifest = build_generate_manifest(config)
        total = sum(e.read_count for e in manifest)
        assert total == 333

    def test_multiplex_structure(
        self, genome_a: Path, genome_b: Path, tmp_path: Path
    ) -> None:
        target = tmp_path / "target"
        config = GenerateConfig(
            target_dir=target,
            genome_inputs=[genome_a, genome_b],
            read_count=200,
            reads_per_file=100,
            structure="multiplex",
            monitor_type="none",
        )
        manifest = build_generate_manifest(config)
        barcodes = {e.barcode for e in manifest}
        assert barcodes == {"barcode01", "barcode02"}
        for entry in manifest:
            assert entry.target.parent == target / entry.barcode

    def test_batching_generate(
        self, genome_a: Path, tmp_path: Path
    ) -> None:
        config = GenerateConfig(
            target_dir=tmp_path / "target",
            genome_inputs=[genome_a],
            read_count=500,
            reads_per_file=100,
            batch_size=2,
            monitor_type="none",
        )
        manifest = build_generate_manifest(config)
        assert len(manifest) == 5
        batches = {e.batch for e in manifest}
        assert batches == {0, 1, 2}

    def test_mixed_reads_mode(
        self, genome_a: Path, genome_b: Path, tmp_path: Path
    ) -> None:
        config = GenerateConfig(
            target_dir=tmp_path / "target",
            genome_inputs=[genome_a, genome_b],
            read_count=200,
            reads_per_file=100,
            mix_reads=True,
            monitor_type="none",
        )
        manifest = build_generate_manifest(config)
        assert len(manifest) == 2  # 200 / 100
        # Mixed entries have mixed_genome_reads set
        for entry in manifest:
            assert entry.mixed_genome_reads is not None
            assert len(entry.mixed_genome_reads) == 2
        # Total reads across all mixed entries
        total = sum(e.read_count for e in manifest)
        assert total == 200

    def test_no_genomes_returns_empty(self, tmp_path: Path) -> None:
        """GenerateConfig requires at least one input; if genome_inputs is
        empty after resolution we get an empty manifest."""
        config = GenerateConfig(
            target_dir=tmp_path / "target",
            genome_inputs=[],
            species_inputs=["something"],
            read_count=100,
            monitor_type="none",
        )
        # genome_inputs is empty list so no files planned
        manifest = build_generate_manifest(config)
        assert manifest == []
