"""Tests for FASTQ read/write utilities."""

import gzip

import pytest
from pathlib import Path
from nanopore_simulator_v2.fastq import count_reads, iter_reads, write_reads


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
