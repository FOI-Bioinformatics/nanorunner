"""Tests for FASTQ read/write utilities."""

import gzip

import pytest
from pathlib import Path
from nanopore_simulator.fastq import (
    count_reads,
    count_reads_with_offsets,
    iter_reads,
    iter_reads_from_offset,
    write_reads,
)


class TestCountReads:
    def test_plain_fastq(self, sample_fastq):
        assert count_reads(sample_fastq) == 2

    def test_gzipped_fastq(self, tmp_path):
        fq = tmp_path / "reads.fastq.gz"
        with gzip.open(fq, "wt") as f:
            f.write("@r1\nACGT\n+\nIIII\n@r2\nTTTT\n+\nIIII\n")
        assert count_reads(fq) == 2

    def test_empty_file(self, tmp_path):
        fq = tmp_path / "empty.fastq"
        fq.write_text("")
        assert count_reads(fq) == 0

    def test_malformed_raises(self, tmp_path):
        fq = tmp_path / "bad.fastq"
        fq.write_text("@r1\nACGT\n+\n")  # 3 lines, not multiple of 4
        with pytest.raises(ValueError, match="not a multiple of 4"):
            count_reads(fq)


class TestIterReads:
    def test_yields_tuples(self, sample_fastq):
        reads = list(iter_reads(sample_fastq))
        assert len(reads) == 2
        header, seq, sep, qual = reads[0]
        assert header.startswith("@")
        assert sep == "+"
        assert len(seq) == len(qual)

    def test_gzipped(self, tmp_path):
        fq = tmp_path / "reads.fastq.gz"
        with gzip.open(fq, "wt") as f:
            f.write("@r1\nACGT\n+\nIIII\n")
        reads = list(iter_reads(fq))
        assert len(reads) == 1

    def test_empty_file(self, tmp_path):
        fq = tmp_path / "empty.fastq"
        fq.write_text("")
        reads = list(iter_reads(fq))
        assert len(reads) == 0

    def test_strips_newlines(self, sample_fastq):
        reads = list(iter_reads(sample_fastq))
        for header, seq, sep, qual in reads:
            assert "\n" not in header
            assert "\n" not in seq
            assert "\n" not in qual


class TestWriteReads:
    def test_write_plain(self, tmp_path):
        out = tmp_path / "out.fastq"
        reads = [("@r1", "ACGT", "+", "IIII")]
        write_reads(reads, out)
        assert out.exists()
        assert count_reads(out) == 1

    def test_write_gzipped(self, tmp_path):
        out = tmp_path / "out.fastq.gz"
        reads = [("@r1", "ACGT", "+", "IIII")]
        write_reads(reads, out)
        assert out.exists()
        assert count_reads(out) == 1

    def test_roundtrip(self, tmp_path):
        out = tmp_path / "roundtrip.fastq"
        original = [("@r1", "ACGT", "+", "IIII"), ("@r2", "TTTT", "+", "JJJJ")]
        write_reads(original, out)
        recovered = list(iter_reads(out))
        assert recovered == original

    def test_roundtrip_gzipped(self, tmp_path):
        out = tmp_path / "roundtrip.fastq.gz"
        original = [("@r1", "ACGT", "+", "IIII"), ("@r2", "TTTT", "+", "JJJJ")]
        write_reads(original, out)
        recovered = list(iter_reads(out))
        assert recovered == original

    def test_write_empty(self, tmp_path):
        out = tmp_path / "empty.fastq"
        write_reads([], out)
        assert out.exists()
        assert count_reads(out) == 0


class TestTruncatedInput:
    """Truncated FASTQ files (last record missing qual line) must not
    raise -- the parser stops cleanly at the EOF.

    Covers the ``if not qual: break`` branches in
    ``count_reads_with_offsets``, ``iter_reads``, and
    ``iter_reads_from_offset``.
    """

    @pytest.fixture
    def truncated_fastq(self, tmp_path: Path) -> Path:
        """One full record, then a header/seq/+ but no qual line."""
        fq = tmp_path / "truncated.fastq"
        fq.write_text("@r1\nACGT\n+\nIIII\n@r2\nACGT\n+\n")
        return fq

    def test_count_with_offsets_handles_truncation(self, truncated_fastq):
        count, offsets = count_reads_with_offsets(truncated_fastq, chunk_size=1)
        # Only the complete record counts; the truncated tail is
        # ignored. An offset may be recorded at the start of the bad
        # record (which the executor will then read past EOF) -- that
        # is harmless because the count is the authoritative bound.
        assert count == 1
        assert offsets[0] == 0
        assert len(offsets) >= 1

    def test_iter_reads_handles_truncation(self, truncated_fastq):
        reads = list(iter_reads(truncated_fastq))
        assert len(reads) == 1
        assert reads[0][0] == "@r1"

    def test_iter_reads_from_offset_handles_truncation(self, truncated_fastq):
        reads = list(iter_reads_from_offset(truncated_fastq, offset=0))
        assert len(reads) == 1
