"""Tests for species resolution and genome caching"""

import pytest

from nanopore_simulator.core.species import GenomeRef


class TestGenomeRef:
    """Tests for GenomeRef dataclass"""

    def test_create_gtdb_ref(self):
        """Test creating a GTDB genome reference"""
        ref = GenomeRef(
            name="Escherichia coli",
            accession="GCF_000005845.2",
            source="gtdb",
            domain="bacteria",
        )
        assert ref.name == "Escherichia coli"
        assert ref.accession == "GCF_000005845.2"
        assert ref.source == "gtdb"
        assert ref.domain == "bacteria"

    def test_create_ncbi_ref(self):
        """Test creating an NCBI genome reference"""
        ref = GenomeRef(
            name="Saccharomyces cerevisiae",
            accession="GCF_000146045.2",
            source="ncbi",
            domain="eukaryota",
        )
        assert ref.source == "ncbi"
        assert ref.domain == "eukaryota"

    def test_create_archaea_ref(self):
        """Test creating an archaeal genome reference"""
        ref = GenomeRef(
            name="Methanococcus jannaschii",
            accession="GCF_000091665.1",
            source="ncbi",
            domain="archaea",
        )
        assert ref.domain == "archaea"

    def test_invalid_source(self):
        """Test that invalid source values raise ValueError"""
        with pytest.raises(ValueError, match="source"):
            GenomeRef(
                name="Test",
                accession="GCF_000000000.1",
                source="invalid",
                domain="bacteria",
            )

    def test_invalid_domain(self):
        """Test that invalid domain values raise ValueError"""
        with pytest.raises(ValueError, match="domain"):
            GenomeRef(
                name="Test",
                accession="GCF_000000000.1",
                source="gtdb",
                domain="invalid",
            )
