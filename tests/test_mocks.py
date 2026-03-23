"""Tests for mock community definitions."""

import pytest

from nanopore_simulator.mocks import (
    MockOrganism,
    MockCommunity,
    BUILTIN_MOCKS,
    MOCK_ALIASES,
    get_mock,
    list_mocks,
)


class TestMockOrganism:
    """Validate MockOrganism dataclass and its constraints."""

    def test_valid_organism(self) -> None:
        org = MockOrganism(
            name="Escherichia coli",
            resolver="ncbi",
            abundance=0.5,
            accession="GCF_000005845.2",
            domain="bacteria",
        )
        assert org.name == "Escherichia coli"
        assert org.resolver == "ncbi"
        assert org.abundance == 0.5
        assert org.accession == "GCF_000005845.2"
        assert org.domain == "bacteria"

    def test_valid_resolver_gtdb(self) -> None:
        org = MockOrganism("Test species", "gtdb", 1.0)
        assert org.resolver == "gtdb"

    def test_invalid_resolver(self) -> None:
        with pytest.raises(ValueError, match="resolver"):
            MockOrganism("Test species", "invalid", 0.5)

    def test_abundance_zero(self) -> None:
        """Boundary: zero abundance is allowed."""
        org = MockOrganism("Test species", "ncbi", 0.0)
        assert org.abundance == 0.0

    def test_abundance_one(self) -> None:
        """Boundary: full abundance is allowed."""
        org = MockOrganism("Test species", "ncbi", 1.0)
        assert org.abundance == 1.0

    def test_abundance_negative(self) -> None:
        with pytest.raises(ValueError, match="abundance"):
            MockOrganism("Test species", "ncbi", -0.1)

    def test_abundance_over_one(self) -> None:
        with pytest.raises(ValueError, match="abundance"):
            MockOrganism("Test species", "ncbi", 1.01)

    def test_domain_none_default(self) -> None:
        org = MockOrganism("Test species", "ncbi", 0.5)
        assert org.domain is None

    def test_domain_archaea(self) -> None:
        org = MockOrganism("Test species", "ncbi", 0.5, domain="archaea")
        assert org.domain == "archaea"

    def test_domain_eukaryota(self) -> None:
        org = MockOrganism("Test species", "ncbi", 0.5, domain="eukaryota")
        assert org.domain == "eukaryota"

    def test_invalid_domain(self) -> None:
        with pytest.raises(ValueError, match="domain"):
            MockOrganism("Test species", "ncbi", 0.5, domain="virus")

    def test_accession_defaults_none(self) -> None:
        org = MockOrganism("Test species", "ncbi", 0.5)
        assert org.accession is None


class TestMockCommunity:
    """Validate MockCommunity dataclass and sum-to-one constraint."""

    def test_valid_community(self) -> None:
        orgs = [
            MockOrganism("Sp A", "ncbi", 0.5),
            MockOrganism("Sp B", "ncbi", 0.5),
        ]
        community = MockCommunity(name="test", description="Test", organisms=orgs)
        assert community.name == "test"
        assert len(community.organisms) == 2

    def test_empty_organisms_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least one organism"):
            MockCommunity(name="empty", description="No organisms", organisms=[])

    def test_abundances_must_sum_to_one(self) -> None:
        orgs = [
            MockOrganism("Sp A", "ncbi", 0.5),
            MockOrganism("Sp B", "ncbi", 0.3),
        ]
        with pytest.raises(ValueError, match="sum to 1.0"):
            MockCommunity(name="bad", description="Bad sum", organisms=orgs)

    def test_abundance_tolerance(self) -> None:
        """Sums close to 1.0 (within 0.01) are accepted."""
        orgs = [
            MockOrganism("Sp A", "ncbi", 0.505),
            MockOrganism("Sp B", "ncbi", 0.505),
        ]
        community = MockCommunity(name="ok", description="Close enough", organisms=orgs)
        assert len(community.organisms) == 2


class TestGetMock:
    """Validate get_mock lookup with case insensitivity and aliases."""

    def test_known_mock(self) -> None:
        mock = get_mock("zymo_d6300")
        assert mock is not None
        assert mock.name == "zymo_d6300"
        assert len(mock.organisms) == 10

    def test_case_insensitive(self) -> None:
        mock = get_mock("ZYMO_D6300")
        assert mock is not None
        assert mock.name == "zymo_d6300"

    def test_mixed_case(self) -> None:
        mock = get_mock("Zymo_D6300")
        assert mock is not None

    def test_alias_d6305(self) -> None:
        mock = get_mock("D6305")
        assert mock is not None
        assert mock.name == "zymo_d6300"

    def test_alias_msa1002(self) -> None:
        mock = get_mock("msa-1002")
        assert mock is not None
        assert mock.name == "atcc_msa1002"

    def test_alias_select_agents(self) -> None:
        mock = get_mock("select_agents")
        assert mock is not None
        assert mock.name == "cdc_select_agents"

    def test_unknown_returns_none(self) -> None:
        assert get_mock("nonexistent_mock") is None


class TestListMocks:
    """Validate list_mocks returns complete information."""

    def test_returns_dict(self) -> None:
        result = list_mocks()
        assert isinstance(result, dict)

    def test_contains_all_builtins(self) -> None:
        result = list_mocks()
        for name in BUILTIN_MOCKS:
            assert name in result

    def test_contains_aliases(self) -> None:
        result = list_mocks()
        for alias in MOCK_ALIASES:
            assert alias in result, f"Missing alias: {alias}"

    def test_alias_values_indicate_target(self) -> None:
        result = list_mocks()
        assert "alias for" in result["d6305"].lower()


class TestBuiltinMockIntegrity:
    """Ensure every built-in mock has consistent data."""

    EXPECTED_MOCKS = [
        "zymo_d6300",
        "zymo_d6310",
        "zymo_d6331",
        "atcc_msa1002",
        "atcc_msa1003",
        "cdc_select_agents",
        "eskape",
        "respiratory",
        "who_critical",
        "bloodstream",
        "wastewater",
        "quick_single",
        "quick_3species",
        "quick_gut5",
        "quick_pathogens",
    ]

    def test_all_expected_mocks_present(self) -> None:
        for name in self.EXPECTED_MOCKS:
            assert name in BUILTIN_MOCKS, f"Missing mock: {name}"

    def test_no_unexpected_mocks(self) -> None:
        for name in BUILTIN_MOCKS:
            assert name in self.EXPECTED_MOCKS, f"Unexpected mock: {name}"

    def test_builtin_count(self) -> None:
        assert len(BUILTIN_MOCKS) == 15

    @pytest.mark.parametrize("name", EXPECTED_MOCKS)
    def test_abundances_sum_to_one(self, name: str) -> None:
        """Each community's abundances should sum to approximately 1.0."""
        mock = BUILTIN_MOCKS[name]
        total = sum(org.abundance for org in mock.organisms)
        assert 0.99 <= total <= 1.01, f"{name}: abundances sum to {total:.6f}"

    @pytest.mark.parametrize("name", EXPECTED_MOCKS)
    def test_name_matches_key(self, name: str) -> None:
        """The mock's .name attribute should match its dict key."""
        assert BUILTIN_MOCKS[name].name == name

    @pytest.mark.parametrize("name", EXPECTED_MOCKS)
    def test_has_description(self, name: str) -> None:
        assert len(BUILTIN_MOCKS[name].description) > 0

    def test_zymo_d6300_organism_count(self) -> None:
        assert len(BUILTIN_MOCKS["zymo_d6300"].organisms) == 10

    def test_zymo_d6310_organism_count(self) -> None:
        assert len(BUILTIN_MOCKS["zymo_d6310"].organisms) == 10

    def test_zymo_d6331_organism_count(self) -> None:
        assert len(BUILTIN_MOCKS["zymo_d6331"].organisms) == 21

    def test_atcc_msa1002_organism_count(self) -> None:
        assert len(BUILTIN_MOCKS["atcc_msa1002"].organisms) == 20

    def test_atcc_msa1003_organism_count(self) -> None:
        assert len(BUILTIN_MOCKS["atcc_msa1003"].organisms) == 20

    def test_quick_single_organism_count(self) -> None:
        assert len(BUILTIN_MOCKS["quick_single"].organisms) == 1


class TestAliasIntegrity:
    """Verify all aliases resolve to valid mocks."""

    EXPECTED_ALIASES = [
        "d6305",
        "d6306",
        "zymo_d6305",
        "zymo_d6306",
        "d6310",
        "d6311",
        "zymo_d6311",
        "d6331",
        "msa1002",
        "msa-1002",
        "msa_1002",
        "msa1003",
        "msa-1003",
        "msa_1003",
        "select_agents",
    ]

    def test_all_expected_aliases_present(self) -> None:
        for alias in self.EXPECTED_ALIASES:
            assert alias in MOCK_ALIASES, f"Missing alias: {alias}"

    def test_alias_count(self) -> None:
        assert len(MOCK_ALIASES) == 15

    @pytest.mark.parametrize("alias", EXPECTED_ALIASES)
    def test_alias_target_exists(self, alias: str) -> None:
        target = MOCK_ALIASES[alias]
        assert (
            target in BUILTIN_MOCKS
        ), f"Alias '{alias}' points to non-existent mock '{target}'"
