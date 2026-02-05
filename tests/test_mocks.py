"""Tests for mock community definitions."""

import pytest

from nanopore_simulator.core.mocks import MockCommunity, MockOrganism


class TestMockOrganism:
    """Tests for MockOrganism dataclass."""

    def test_create_gtdb_organism(self):
        """Test creating an organism with GTDB resolver."""
        org = MockOrganism(
            name="Escherichia coli",
            resolver="gtdb",
            abundance=0.125,
        )
        assert org.name == "Escherichia coli"
        assert org.resolver == "gtdb"
        assert org.abundance == 0.125
        assert org.accession is None

    def test_create_ncbi_organism_with_accession(self):
        """Test creating an organism with NCBI resolver and accession."""
        org = MockOrganism(
            name="Saccharomyces cerevisiae",
            resolver="ncbi",
            abundance=0.1,
            accession="GCF_000146045.2",
        )
        assert org.resolver == "ncbi"
        assert org.accession == "GCF_000146045.2"

    def test_invalid_resolver(self):
        """Test that invalid resolver raises ValueError."""
        with pytest.raises(ValueError, match="resolver"):
            MockOrganism(name="Test", resolver="invalid", abundance=0.5)

    def test_invalid_abundance_negative(self):
        """Test that negative abundance raises ValueError."""
        with pytest.raises(ValueError, match="abundance"):
            MockOrganism(name="Test", resolver="gtdb", abundance=-0.1)

    def test_invalid_abundance_over_one(self):
        """Test that abundance over 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="abundance"):
            MockOrganism(name="Test", resolver="gtdb", abundance=1.5)


class TestMockCommunity:
    """Tests for MockCommunity dataclass."""

    def test_create_community(self):
        """Test creating a valid mock community."""
        organisms = [
            MockOrganism("E. coli", "gtdb", 0.5),
            MockOrganism("S. aureus", "gtdb", 0.5),
        ]
        community = MockCommunity(
            name="test_mock",
            description="Test mock community",
            organisms=organisms,
        )
        assert community.name == "test_mock"
        assert len(community.organisms) == 2

    def test_abundances_must_sum_to_one(self):
        """Test that abundances not summing to 1.0 raises ValueError."""
        organisms = [
            MockOrganism("E. coli", "gtdb", 0.3),
            MockOrganism("S. aureus", "gtdb", 0.3),
        ]
        with pytest.raises(ValueError, match="sum to 1.0"):
            MockCommunity("test", "Test", organisms)

    def test_abundances_tolerance(self):
        """Test that abundances summing to approximately 1.0 are accepted."""
        organisms = [
            MockOrganism("E. coli", "gtdb", 0.333),
            MockOrganism("S. aureus", "gtdb", 0.333),
            MockOrganism("B. subtilis", "gtdb", 0.334),
        ]
        community = MockCommunity("test", "Test", organisms)
        assert len(community.organisms) == 3

    def test_empty_organisms(self):
        """Test that empty organisms list raises ValueError."""
        with pytest.raises(ValueError, match="at least one organism"):
            MockCommunity("test", "Test", [])
