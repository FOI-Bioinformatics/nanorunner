"""Tests for read-level rechunking in the replay command."""

import gzip
import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nanopore_simulator.cli.main import app
from nanopore_simulator.core.config import SimulationConfig
from nanopore_simulator.core.fastq import (
    count_fastq_reads,
    iter_fastq_reads,
    write_fastq_reads,
)
from nanopore_simulator.core.simulator import NanoporeSimulator


runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fastq_content(n_reads: int, prefix: str = "read") -> str:
    """Return FASTQ text with *n_reads* records."""
    lines = []
    for i in range(n_reads):
        lines.append(f"@{prefix}_{i}")
        lines.append("ACGTACGT")
        lines.append("+")
        lines.append("IIIIIIII")
    return "\n".join(lines) + "\n"


def _write_plain_fastq(path: Path, n_reads: int, prefix: str = "read") -> None:
    path.write_text(_make_fastq_content(n_reads, prefix))


def _write_gzipped_fastq(path: Path, n_reads: int, prefix: str = "read") -> None:
    with gzip.open(path, "wt") as fh:
        fh.write(_make_fastq_content(n_reads, prefix))


def _collect_reads(path: Path):
    """Return list of (header, seq, sep, qual) from a FASTQ file."""
    return list(iter_fastq_reads(path))


# ===================================================================
# FASTQ utility tests
# ===================================================================


class TestCountFastqReads:

    def test_count_plain_fastq(self, tmp_path):
        fq = tmp_path / "test.fastq"
        _write_plain_fastq(fq, 10)
        assert count_fastq_reads(fq) == 10

    def test_count_gzipped_fastq(self, tmp_path):
        fq = tmp_path / "test.fastq.gz"
        _write_gzipped_fastq(fq, 7)
        assert count_fastq_reads(fq) == 7

    def test_count_empty_file(self, tmp_path):
        fq = tmp_path / "empty.fastq"
        fq.write_text("")
        assert count_fastq_reads(fq) == 0

    def test_count_malformed_raises(self, tmp_path):
        fq = tmp_path / "bad.fastq"
        # 5 lines is not a multiple of 4
        fq.write_text("@r1\nACGT\n+\nIIII\n@r2\n")
        with pytest.raises(ValueError, match="not a multiple of 4"):
            count_fastq_reads(fq)


class TestIterFastqReads:

    def test_iter_reads_content(self, tmp_path):
        fq = tmp_path / "test.fastq"
        _write_plain_fastq(fq, 3, prefix="seq")
        reads = list(iter_fastq_reads(fq))
        assert len(reads) == 3
        assert reads[0] == ("@seq_0", "ACGTACGT", "+", "IIIIIIII")
        assert reads[2][0] == "@seq_2"

    def test_iter_gzipped(self, tmp_path):
        fq = tmp_path / "test.fastq.gz"
        _write_gzipped_fastq(fq, 5)
        reads = list(iter_fastq_reads(fq))
        assert len(reads) == 5

    def test_iter_empty_file(self, tmp_path):
        fq = tmp_path / "empty.fastq"
        fq.write_text("")
        assert list(iter_fastq_reads(fq)) == []


class TestWriteFastqReads:

    def test_write_plain(self, tmp_path):
        out = tmp_path / "out.fastq"
        reads = [("@r1", "ACGT", "+", "IIII"), ("@r2", "TTTT", "+", "????")]
        write_fastq_reads(reads, out)
        content = out.read_text()
        assert content.count("@r") == 2
        assert "@r1\nACGT\n+\nIIII\n" in content

    def test_write_gzipped(self, tmp_path):
        out = tmp_path / "out.fastq.gz"
        reads = [("@r1", "ACGT", "+", "IIII")]
        write_fastq_reads(reads, out)
        with gzip.open(out, "rt") as fh:
            content = fh.read()
        assert "@r1\nACGT\n+\nIIII\n" in content

    def test_write_empty_list(self, tmp_path):
        out = tmp_path / "empty.fastq"
        write_fastq_reads([], out)
        assert out.read_text() == ""

    def test_roundtrip(self, tmp_path):
        """Write reads and read them back; verify equality."""
        original = [
            ("@read_0", "ACGTACGT", "+", "IIIIIIII"),
            ("@read_1", "GGCCTTAA", "+", "????????"),
        ]
        out = tmp_path / "rt.fastq"
        write_fastq_reads(original, out)
        recovered = list(iter_fastq_reads(out))
        assert recovered == original

    def test_roundtrip_gzipped(self, tmp_path):
        original = [("@gz_0", "AAAA", "+", "IIII")]
        out = tmp_path / "rt.fastq.gz"
        write_fastq_reads(original, out)
        recovered = list(iter_fastq_reads(out))
        assert recovered == original


# ===================================================================
# Config validation tests
# ===================================================================


class TestConfigRechunkValidation:

    def test_reads_per_output_file_default_is_none(self):
        """Default value should be None (no rechunking)."""
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "src"
            source.mkdir()
            (source / "test.fastq").write_text("@r\nA\n+\nI\n")
            cfg = SimulationConfig(
                source_dir=source,
                target_dir=Path(td) / "tgt",
            )
            assert cfg.reads_per_output_file is None

    def test_valid_with_copy(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "src"
            source.mkdir()
            (source / "test.fastq").write_text("@r\nA\n+\nI\n")
            cfg = SimulationConfig(
                source_dir=source,
                target_dir=Path(td) / "tgt",
                operation="copy",
                reads_per_output_file=100,
            )
            assert cfg.reads_per_output_file == 100

    def test_zero_raises(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "src"
            source.mkdir()
            (source / "test.fastq").write_text("@r\nA\n+\nI\n")
            with pytest.raises(ValueError, match="at least 1"):
                SimulationConfig(
                    source_dir=source,
                    target_dir=Path(td) / "tgt",
                    reads_per_output_file=0,
                )

    def test_negative_raises(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "src"
            source.mkdir()
            (source / "test.fastq").write_text("@r\nA\n+\nI\n")
            with pytest.raises(ValueError, match="at least 1"):
                SimulationConfig(
                    source_dir=source,
                    target_dir=Path(td) / "tgt",
                    reads_per_output_file=-1,
                )

    def test_link_operation_raises(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "src"
            source.mkdir()
            (source / "test.fastq").write_text("@r\nA\n+\nI\n")
            with pytest.raises(ValueError, match="incompatible with.*link"):
                SimulationConfig(
                    source_dir=source,
                    target_dir=Path(td) / "tgt",
                    operation="link",
                    reads_per_output_file=50,
                )

    def test_generate_operation_raises(self, tmp_path):
        fasta = tmp_path / "genome.fa"
        fasta.write_text(">chr1\nACGTACGT\n")
        with pytest.raises(ValueError, match="only applicable to replay"):
            SimulationConfig(
                target_dir=tmp_path / "tgt",
                operation="generate",
                genome_inputs=[fasta],
                reads_per_output_file=50,
            )


# ===================================================================
# Rechunk logic tests (end-to-end via NanoporeSimulator)
# ===================================================================


class TestRechunkSimulation:

    def _run_rechunk(self, source_dir, target_dir, reads_per_file, **kwargs):
        """Helper to run a rechunk simulation."""
        config = SimulationConfig(
            source_dir=source_dir,
            target_dir=target_dir,
            operation="copy",
            reads_per_output_file=reads_per_file,
            interval=0.0,
            **kwargs,
        )
        sim = NanoporeSimulator(config, enable_monitoring=False)
        sim.run_simulation()

    def test_split_large_file(self, tmp_path):
        """100-read file with reads_per_file=30 -> 4 chunks (30+30+30+10)."""
        source = tmp_path / "src"
        target = tmp_path / "tgt"
        source.mkdir()
        _write_plain_fastq(source / "big.fastq", 100)

        self._run_rechunk(source, target, 30)

        chunks = sorted(target.glob("*.fastq"))
        assert len(chunks) == 4
        counts = [count_fastq_reads(c) for c in chunks]
        assert counts == [30, 30, 30, 10]

    def test_merge_small_files(self, tmp_path):
        """Three 5-read files with reads_per_file=10 -> 2 chunks (10+5)."""
        source = tmp_path / "src"
        target = tmp_path / "tgt"
        source.mkdir()
        _write_plain_fastq(source / "a.fastq", 5, prefix="a")
        _write_plain_fastq(source / "b.fastq", 5, prefix="b")
        _write_plain_fastq(source / "c.fastq", 5, prefix="c")

        self._run_rechunk(source, target, 10)

        chunks = sorted(target.glob("*.fastq"))
        assert len(chunks) == 2
        counts = [count_fastq_reads(c) for c in chunks]
        assert sorted(counts, reverse=True) == [10, 5]

    def test_exact_multiple(self, tmp_path):
        """20-read file with reads_per_file=10 -> exactly 2 chunks."""
        source = tmp_path / "src"
        target = tmp_path / "tgt"
        source.mkdir()
        _write_plain_fastq(source / "exact.fastq", 20)

        self._run_rechunk(source, target, 10)

        chunks = sorted(target.glob("*.fastq"))
        assert len(chunks) == 2
        counts = [count_fastq_reads(c) for c in chunks]
        assert counts == [10, 10]

    def test_reads_per_file_larger_than_total(self, tmp_path):
        """reads_per_file > total reads -> single chunk with all reads."""
        source = tmp_path / "src"
        target = tmp_path / "tgt"
        source.mkdir()
        _write_plain_fastq(source / "small.fastq", 5)

        self._run_rechunk(source, target, 100)

        chunks = sorted(target.glob("*.fastq"))
        assert len(chunks) == 1
        assert count_fastq_reads(chunks[0]) == 5

    def test_empty_fastq_skipped(self, tmp_path):
        """0-read file produces no output chunks."""
        source = tmp_path / "src"
        target = tmp_path / "tgt"
        source.mkdir()
        (source / "empty.fastq").write_text("")

        self._run_rechunk(source, target, 10)

        chunks = list(target.glob("*.fastq"))
        assert len(chunks) == 0

    def test_content_preservation(self, tmp_path):
        """All output reads concatenated must equal all source reads."""
        source = tmp_path / "src"
        target = tmp_path / "tgt"
        source.mkdir()
        _write_plain_fastq(source / "f1.fastq", 7, prefix="f1")
        _write_plain_fastq(source / "f2.fastq", 13, prefix="f2")

        self._run_rechunk(source, target, 5)

        # Collect source reads in order
        src_reads = []
        for fq in sorted(source.glob("*.fastq")):
            src_reads.extend(_collect_reads(fq))

        # Collect output reads in chunk order
        out_reads = []
        for fq in sorted(target.glob("*.fastq")):
            out_reads.extend(_collect_reads(fq))

        assert len(out_reads) == len(src_reads)
        assert out_reads == src_reads

    def test_barcode_isolation_multiplex(self, tmp_path):
        """Multiplex: reads stay within their barcode group."""
        source = tmp_path / "src"
        target = tmp_path / "tgt"
        source.mkdir()

        bc1 = source / "barcode01"
        bc2 = source / "barcode02"
        bc1.mkdir()
        bc2.mkdir()

        _write_plain_fastq(bc1 / "reads.fastq", 12, prefix="bc1")
        _write_plain_fastq(bc2 / "reads.fastq", 8, prefix="bc2")

        self._run_rechunk(source, target, 5)

        # barcode01: 12 reads -> 3 chunks (5+5+2)
        bc1_chunks = sorted((target / "barcode01").glob("*.fastq"))
        assert len(bc1_chunks) == 3
        bc1_reads = []
        for c in bc1_chunks:
            bc1_reads.extend(_collect_reads(c))
        assert all("bc1" in r[0] for r in bc1_reads)
        assert len(bc1_reads) == 12

        # barcode02: 8 reads -> 2 chunks (5+3)
        bc2_chunks = sorted((target / "barcode02").glob("*.fastq"))
        assert len(bc2_chunks) == 2
        bc2_reads = []
        for c in bc2_chunks:
            bc2_reads.extend(_collect_reads(c))
        assert all("bc2" in r[0] for r in bc2_reads)
        assert len(bc2_reads) == 8

    def test_pod5_passthrough(self, tmp_path):
        """POD5 files are copied as-is without rechunking."""
        source = tmp_path / "src"
        target = tmp_path / "tgt"
        source.mkdir()
        _write_plain_fastq(source / "reads.fastq", 10)
        pod5 = source / "signal.pod5"
        pod5.write_bytes(b"pod5 binary data")

        self._run_rechunk(source, target, 5)

        # FASTQ rechunked
        chunks = sorted(target.glob("*.fastq"))
        assert len(chunks) == 2

        # POD5 copied
        assert (target / "signal.pod5").exists()
        assert (target / "signal.pod5").read_bytes() == b"pod5 binary data"

    def test_gzipped_source_gzipped_output(self, tmp_path):
        """Gzipped source -> gzipped output."""
        source = tmp_path / "src"
        target = tmp_path / "tgt"
        source.mkdir()
        _write_gzipped_fastq(source / "reads.fastq.gz", 10)

        self._run_rechunk(source, target, 4)

        chunks = sorted(target.glob("*.fastq.gz"))
        assert len(chunks) == 3  # 4+4+2
        total = sum(count_fastq_reads(c) for c in chunks)
        assert total == 10

    def test_chunk_naming_convention(self, tmp_path):
        """Output files follow {stem}_chunk_{index:04d}{ext} naming."""
        source = tmp_path / "src"
        target = tmp_path / "tgt"
        source.mkdir()
        _write_plain_fastq(source / "sample.fastq", 10)

        self._run_rechunk(source, target, 4)

        names = sorted(f.name for f in target.glob("*.fastq"))
        assert names == [
            "sample_chunk_0000.fastq",
            "sample_chunk_0001.fastq",
            "sample_chunk_0002.fastq",
        ]

    def test_cross_file_filling(self, tmp_path):
        """Reads from multiple source files fill a single output chunk."""
        source = tmp_path / "src"
        target = tmp_path / "tgt"
        source.mkdir()
        # 3-read file + 2-read file, reads_per_file=4 -> 1 chunk of 4, 1 of 1
        _write_plain_fastq(source / "a.fastq", 3, prefix="a")
        _write_plain_fastq(source / "b.fastq", 2, prefix="b")

        self._run_rechunk(source, target, 4)

        chunks = sorted(target.glob("*.fastq"))
        assert len(chunks) == 2

        first_chunk_reads = _collect_reads(chunks[0])
        assert len(first_chunk_reads) == 4
        # First 3 reads from file a, 4th from file b
        assert first_chunk_reads[0][0] == "@a_0"
        assert first_chunk_reads[3][0] == "@b_0"

    def test_mixed_compression_in_barcode(self, tmp_path):
        """Both .fastq and .fastq.gz files in the same barcode group."""
        source = tmp_path / "src"
        target = tmp_path / "tgt"
        source.mkdir()
        bc = source / "barcode01"
        bc.mkdir()
        _write_plain_fastq(bc / "plain.fastq", 3, prefix="plain")
        _write_gzipped_fastq(bc / "compressed.fastq.gz", 3, prefix="gz")

        self._run_rechunk(source, target, 4)

        bc_target = target / "barcode01"
        # 6 reads total -> 2 chunks (4+2)
        # There may be mixed extensions based on which source starts each chunk
        chunks = sorted(
            list(bc_target.glob("*.fastq")) + list(bc_target.glob("*.fastq.gz"))
        )
        total = sum(count_fastq_reads(c) for c in chunks)
        assert total == 6

    def test_singleplex_rechunk_with_timing(self, tmp_path):
        """Singleplex rechunk applies timing between output files."""
        source = tmp_path / "src"
        target = tmp_path / "tgt"
        source.mkdir()
        _write_plain_fastq(source / "data.fastq", 20)

        config = SimulationConfig(
            source_dir=source,
            target_dir=target,
            operation="copy",
            reads_per_output_file=5,
            interval=0.0,
            timing_model="uniform",
        )
        sim = NanoporeSimulator(config, enable_monitoring=False)
        sim.run_simulation()

        chunks = sorted(target.glob("*.fastq"))
        assert len(chunks) == 4
        total = sum(count_fastq_reads(c) for c in chunks)
        assert total == 20


# ===================================================================
# CLI tests
# ===================================================================


class TestCLIRechunk:

    def setup_method(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.source_dir = self.temp_path / "source"
        self.target_dir = self.temp_path / "target"
        self.source_dir.mkdir()
        _write_plain_fastq(self.source_dir / "sample.fastq", 20)

    def teardown_method(self):
        self.temp_dir.cleanup()

    def test_reads_per_file_accepted(self):
        result = runner.invoke(app, [
            "replay",
            "--source", str(self.source_dir),
            "--target", str(self.target_dir),
            "--reads-per-file", "5",
            "--interval", "0",
        ])
        assert result.exit_code == 0
        chunks = sorted(self.target_dir.glob("*.fastq"))
        assert len(chunks) == 4

    def test_reads_per_file_with_link_errors(self):
        result = runner.invoke(app, [
            "replay",
            "--source", str(self.source_dir),
            "--target", str(self.target_dir),
            "--reads-per-file", "10",
            "--operation", "link",
        ])
        assert result.exit_code == 2
        assert "incompatible" in result.output.lower() or "incompatible" in (result.stderr or "").lower()

    def test_help_contains_reads_per_file(self):
        result = runner.invoke(app, ["replay", "--help"])
        assert "--reads-per-file" in result.output
