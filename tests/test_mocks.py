"""Tests for mock community definitions."""

import pytest

from nanopore_simulator.core.mocks import (
    MockOrganism,
    MockCommunity,
    BUILTIN_MOCKS,
    get_mock_community,
    list_mock_communities,
)


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


class TestBuiltinMocks:
    """Tests for built-in mock communities."""

    def test_zymo_d6300_exists(self):
        """Test that Zymo D6300 mock exists."""
        assert "zymo_d6300" in BUILTIN_MOCKS

    def test_zymo_d6300_has_10_organisms(self):
        """Test that Zymo D6300 has 10 organisms (8 bacteria + 2 yeasts)."""
        mock = BUILTIN_MOCKS["zymo_d6300"]
        assert len(mock.organisms) == 10

    def test_zymo_d6300_has_fungi(self):
        """Test that Zymo D6300 has fungi using NCBI resolver."""
        mock = BUILTIN_MOCKS["zymo_d6300"]
        ncbi_orgs = [o for o in mock.organisms if o.resolver == "ncbi"]
        assert len(ncbi_orgs) == 2  # Two yeasts

    def test_quick_3species_exists(self):
        """Test that quick_3species mock exists."""
        assert "quick_3species" in BUILTIN_MOCKS

    def test_quick_3species_equal_abundances(self):
        """Test that quick_3species has equal abundances."""
        mock = BUILTIN_MOCKS["quick_3species"]
        for org in mock.organisms:
            assert abs(org.abundance - 1 / 3) < 0.01

    def test_get_mock_community_exists(self):
        """Test getting a mock community that exists."""
        mock = get_mock_community("zymo_d6300")
        assert mock is not None
        assert mock.name == "zymo_d6300"

    def test_get_mock_community_not_found(self):
        """Test getting a mock community that does not exist."""
        mock = get_mock_community("nonexistent")
        assert mock is None

    def test_list_mock_communities(self):
        """Test listing all mock communities."""
        mocks = list_mock_communities()
        assert "zymo_d6300" in mocks
        assert "quick_3species" in mocks
        assert isinstance(mocks["zymo_d6300"], str)  # Description


class TestMockAliasesAndCaseInsensitivity:
    """Tests for case-insensitive lookup and product code aliases."""

    def test_case_insensitive_lookup(self):
        """Mock lookup should be case-insensitive."""
        mock1 = get_mock_community("zymo_d6300")
        mock2 = get_mock_community("ZYMO_D6300")
        mock3 = get_mock_community("Zymo_D6300")
        assert mock1 is not None
        assert mock1 == mock2 == mock3

    def test_alias_d6305_resolves(self):
        """D6305 should resolve to zymo_d6300."""
        mock = get_mock_community("d6305")
        assert mock is not None
        assert mock.name == "zymo_d6300"

    def test_alias_d6306_resolves(self):
        """D6306 should resolve to zymo_d6300."""
        mock = get_mock_community("D6306")  # Test case-insensitivity too
        assert mock is not None
        assert mock.name == "zymo_d6300"

    def test_alias_with_zymo_prefix(self):
        """zymo_d6305 should also resolve to zymo_d6300."""
        mock = get_mock_community("zymo_d6305")
        assert mock is not None
        assert mock.name == "zymo_d6300"


class TestZymoD6310:
    """Tests for Zymo D6310 Log Distribution mock community."""

    def test_zymo_d6310_exists(self):
        """D6310 mock should exist."""
        mock = get_mock_community("zymo_d6310")
        assert mock is not None
        assert mock.name == "zymo_d6310"

    def test_zymo_d6310_has_10_organisms(self):
        """D6310 should have same 10 organisms as D6300."""
        mock = get_mock_community("zymo_d6310")
        assert len(mock.organisms) == 10

    def test_zymo_d6310_log_distribution(self):
        """D6310 abundances should span multiple orders of magnitude."""
        mock = get_mock_community("zymo_d6310")
        abundances = [org.abundance for org in mock.organisms]
        max_abundance = max(abundances)
        min_abundance = min(abundances)
        # Should span at least 4 orders of magnitude
        assert max_abundance / min_abundance >= 10000

    def test_alias_d6310_resolves(self):
        """d6310 alias should resolve to zymo_d6310."""
        mock = get_mock_community("d6310")
        assert mock is not None
        assert mock.name == "zymo_d6310"

    def test_alias_d6311_resolves(self):
        """D6311 should resolve to zymo_d6310."""
        mock = get_mock_community("D6311")
        assert mock is not None
        assert mock.name == "zymo_d6310"