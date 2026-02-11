"""Tests for mock community definitions."""

import pytest

from nanopore_simulator.core.mocks import (
    MockOrganism,
    MockCommunity,
    BUILTIN_MOCKS,
    MOCK_ALIASES,
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
        """Test that Zymo D6300 has fungi with eukaryota domain."""
        mock = BUILTIN_MOCKS["zymo_d6300"]
        fungi = [o for o in mock.organisms if o.domain == "eukaryota"]
        assert len(fungi) == 2  # Two yeasts

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


class TestATCCMSA1002:
    """Tests for ATCC MSA-1002 20-strain even mix mock community."""

    def test_atcc_msa1002_exists(self):
        """ATCC MSA-1002 mock should exist."""
        mock = get_mock_community("atcc_msa1002")
        assert mock is not None
        assert mock.name == "atcc_msa1002"

    def test_atcc_msa1002_has_20_organisms(self):
        """MSA-1002 should have 20 bacterial strains."""
        mock = get_mock_community("atcc_msa1002")
        assert len(mock.organisms) == 20

    def test_atcc_msa1002_even_distribution(self):
        """MSA-1002 should have even 5% distribution."""
        mock = get_mock_community("atcc_msa1002")
        for org in mock.organisms:
            assert org.abundance == 0.05

    def test_atcc_msa1002_all_have_accessions(self):
        """MSA-1002 organisms should all have explicit accessions."""
        mock = get_mock_community("atcc_msa1002")
        for org in mock.organisms:
            assert org.accession is not None, f"{org.name} missing accession"


class TestATCCMSA1003:
    """Tests for ATCC MSA-1003 20-strain staggered mix mock community."""

    def test_atcc_msa1003_exists(self):
        """ATCC MSA-1003 mock should exist."""
        mock = get_mock_community("atcc_msa1003")
        assert mock is not None
        assert mock.name == "atcc_msa1003"

    def test_atcc_msa1003_has_20_organisms(self):
        """MSA-1003 should have 20 bacterial strains."""
        mock = get_mock_community("atcc_msa1003")
        assert len(mock.organisms) == 20

    def test_atcc_msa1003_staggered_distribution(self):
        """MSA-1003 should have staggered distribution (0.02% to 18%)."""
        mock = get_mock_community("atcc_msa1003")
        abundances = sorted([org.abundance for org in mock.organisms])
        # Check range spans from ~0.02% to ~18%
        assert abundances[0] < 0.001  # Smallest should be < 0.1%
        assert abundances[-1] > 0.1  # Largest should be > 10%

    def test_atcc_msa1003_log_spread(self):
        """MSA-1003 abundances should span ~3 orders of magnitude."""
        mock = get_mock_community("atcc_msa1003")
        abundances = [org.abundance for org in mock.organisms]
        max_abundance = max(abundances)
        min_abundance = min(abundances)
        assert max_abundance / min_abundance >= 100


class TestListMocksWithAliases:
    """Tests for list_mock_communities including aliases."""

    def test_list_includes_primary_mocks(self):
        """list_mock_communities should include all primary mocks."""
        mocks = list_mock_communities()
        assert "zymo_d6300" in mocks
        assert "zymo_d6310" in mocks
        assert "atcc_msa1002" in mocks
        assert "atcc_msa1003" in mocks

    def test_list_includes_aliases(self):
        """list_mock_communities should include aliases."""
        mocks = list_mock_communities()
        assert "d6305" in mocks
        assert "d6306" in mocks
        assert "d6310" in mocks
        assert "d6311" in mocks

    def test_alias_descriptions_indicate_target(self):
        """Alias descriptions should indicate they are aliases."""
        mocks = list_mock_communities()
        assert "alias" in mocks["d6305"].lower()
        assert "zymo_d6300" in mocks["d6305"]


class TestZymoD6331:
    """Tests for Zymo D6331 Gut Microbiome Standard mock community."""

    def test_zymo_d6331_exists(self):
        """D6331 mock should exist."""
        mock = get_mock_community("zymo_d6331")
        assert mock is not None
        assert mock.name == "zymo_d6331"

    def test_zymo_d6331_has_21_organisms(self):
        """D6331 should have 21 strains (5 E. coli + 12 other species)."""
        mock = get_mock_community("zymo_d6331")
        assert len(mock.organisms) == 21

    def test_zymo_d6331_has_5_ecoli_strains(self):
        """D6331 should have 5 individual E. coli strains at 2.8% each."""
        mock = get_mock_community("zymo_d6331")
        ecoli = [o for o in mock.organisms if "Escherichia coli" in o.name]
        assert len(ecoli) == 5
        expected_strains = {"B-1109", "JM109", "B-3008", "B-766", "B-2207"}
        found_strains = {o.name.replace("Escherichia coli ", "") for o in ecoli}
        assert found_strains == expected_strains
        for org in ecoli:
            assert abs(org.abundance - 0.028) < 0.001
            assert org.accession is not None
            assert org.accession.startswith("GCF_")

    def test_zymo_d6331_ecoli_total_abundance(self):
        """Total E. coli abundance across 5 strains should equal 14%."""
        mock = get_mock_community("zymo_d6331")
        ecoli = [o for o in mock.organisms if "Escherichia coli" in o.name]
        total = sum(o.abundance for o in ecoli)
        assert abs(total - 0.14) < 0.001

    def test_zymo_d6331_cross_kingdom(self):
        """D6331 should include bacteria, archaea, and fungi."""
        mock = get_mock_community("zymo_d6331")
        domains = {o.domain for o in mock.organisms}
        assert "bacteria" in domains
        assert "archaea" in domains
        assert "eukaryota" in domains

    def test_zymo_d6331_has_archaea(self):
        """D6331 should include Methanobrevibacter smithii (archaea)."""
        mock = get_mock_community("zymo_d6331")
        archaea = [o for o in mock.organisms if "Methanobrevibacter" in o.name]
        assert len(archaea) == 1

    def test_zymo_d6331_has_fungi(self):
        """D6331 should include both Candida and Saccharomyces."""
        mock = get_mock_community("zymo_d6331")
        fungi_names = [o.name for o in mock.organisms]
        assert any("Candida" in name for name in fungi_names)
        assert any("Saccharomyces" in name for name in fungi_names)

    def test_zymo_d6331_log_distribution(self):
        """D6331 abundances should span multiple orders of magnitude."""
        mock = get_mock_community("zymo_d6331")
        abundances = [org.abundance for org in mock.organisms]
        max_abundance = max(abundances)
        min_abundance = min(abundances)
        # Should span at least 5 orders of magnitude (14% to 0.0001%)
        assert max_abundance / min_abundance >= 100000

    def test_alias_d6331_resolves(self):
        """d6331 alias should resolve to zymo_d6331."""
        mock = get_mock_community("d6331")
        assert mock is not None
        assert mock.name == "zymo_d6331"

    def test_alias_d6331_case_insensitive(self):
        """D6331 alias should be case-insensitive."""
        mock = get_mock_community("D6331")
        assert mock is not None
        assert mock.name == "zymo_d6331"


class TestMockOrganismDomain:
    """Tests for MockOrganism domain field."""

    def test_domain_defaults_none(self):
        """Domain field should default to None."""
        org = MockOrganism("Test species", "gtdb", 0.5)
        assert org.domain is None

    def test_domain_validation_valid(self):
        """Valid domain values should be accepted."""
        for domain in ["bacteria", "archaea", "eukaryota"]:
            org = MockOrganism("Test", "gtdb", 0.5, domain=domain)
            assert org.domain == domain

    def test_domain_validation_invalid(self):
        """Invalid domain values should raise ValueError."""
        with pytest.raises(ValueError, match="domain"):
            MockOrganism("Test", "gtdb", 0.5, domain="fungi")

    def test_d6331_methanobrevibacter_has_archaea_domain_and_accession(self):
        """M. smithii in D6331 should have archaea domain and accession."""
        mock = get_mock_community("zymo_d6331")
        m_smithii = [o for o in mock.organisms if "Methanobrevibacter" in o.name]
        assert len(m_smithii) == 1
        assert m_smithii[0].domain == "archaea"
        assert m_smithii[0].accession == "GCF_000016525.1"

    def test_d6331_fungi_have_eukaryota_domain(self):
        """Fungi in D6331 should have eukaryota domain."""
        mock = get_mock_community("zymo_d6331")
        candida = [o for o in mock.organisms if "Candida" in o.name]
        saccharomyces = [o for o in mock.organisms if "Saccharomyces" in o.name]
        assert candida[0].domain == "eukaryota"
        assert saccharomyces[0].domain == "eukaryota"


class TestD6310CorrectedAbundances:
    """Tests for corrected Zymo D6310 abundances with interleaved yeasts."""

    def test_d6310_yeasts_interleaved(self):
        """S. cerevisiae and C. neoformans should be interleaved in the log series."""
        mock = get_mock_community("zymo_d6310")
        names = [o.name for o in mock.organisms]
        # S. cerevisiae should appear after Bacillus, before E. coli
        sc_idx = names.index("Saccharomyces cerevisiae")
        bs_idx = names.index("Bacillus subtilis")
        ec_idx = names.index("Escherichia coli")
        assert bs_idx < sc_idx < ec_idx

    def test_d6310_saccharomyces_at_correct_level(self):
        """S. cerevisiae should be at the same abundance level as B. subtilis."""
        mock = get_mock_community("zymo_d6310")
        orgs = {o.name: o.abundance for o in mock.organisms}
        assert orgs["Saccharomyces cerevisiae"] == orgs["Bacillus subtilis"]

    def test_d6310_cryptococcus_at_lowest_level(self):
        """C. neoformans should be the least abundant organism."""
        mock = get_mock_community("zymo_d6310")
        abundances = [(o.name, o.abundance) for o in mock.organisms]
        min_org = min(abundances, key=lambda x: x[1])
        assert min_org[0] == "Cryptococcus neoformans"


class TestATCCAliases:
    """Tests for ATCC mock community aliases."""

    def test_msa1002_alias(self):
        """msa1002 should resolve to atcc_msa1002."""
        mock = get_mock_community("msa1002")
        assert mock is not None
        assert mock.name == "atcc_msa1002"

    def test_msa_dash_1002_alias(self):
        """msa-1002 should resolve to atcc_msa1002."""
        mock = get_mock_community("msa-1002")
        assert mock is not None
        assert mock.name == "atcc_msa1002"

    def test_msa1003_alias(self):
        """msa1003 should resolve to atcc_msa1003."""
        mock = get_mock_community("MSA1003")
        assert mock is not None
        assert mock.name == "atcc_msa1003"


class TestCDCSelectAgents:
    """Tests for CDC/USDA Tier 1 bacterial select agents mock."""

    def test_exists(self):
        """CDC select agents mock should exist."""
        mock = get_mock_community("cdc_select_agents")
        assert mock is not None

    def test_has_6_organisms(self):
        """Should contain 6 Tier 1 bacterial select agents."""
        mock = get_mock_community("cdc_select_agents")
        assert len(mock.organisms) == 6

    def test_even_distribution(self):
        """All organisms should have equal abundance."""
        mock = get_mock_community("cdc_select_agents")
        for org in mock.organisms:
            assert abs(org.abundance - 1 / 6) < 0.001

    def test_contains_key_agents(self):
        """Should contain the canonical Tier 1 agents."""
        mock = get_mock_community("cdc_select_agents")
        names = {o.name for o in mock.organisms}
        assert "Bacillus anthracis" in names
        assert "Yersinia pestis" in names
        assert "Francisella tularensis" in names
        assert "Burkholderia pseudomallei" in names

    def test_all_have_accessions(self):
        """All organisms should have explicit accessions."""
        mock = get_mock_community("cdc_select_agents")
        for org in mock.organisms:
            assert org.accession is not None, f"{org.name} missing accession"

    def test_alias_select_agents(self):
        """select_agents alias should resolve."""
        mock = get_mock_community("select_agents")
        assert mock is not None
        assert mock.name == "cdc_select_agents"


class TestESKAPE:
    """Tests for ESKAPE nosocomial pathogens mock."""

    def test_exists(self):
        """ESKAPE mock should exist."""
        mock = get_mock_community("eskape")
        assert mock is not None

    def test_has_6_organisms(self):
        """Should contain all 6 ESKAPE organisms."""
        mock = get_mock_community("eskape")
        assert len(mock.organisms) == 6

    def test_contains_all_eskape(self):
        """Should contain the canonical ESKAPE organisms."""
        mock = get_mock_community("eskape")
        names = {o.name for o in mock.organisms}
        # E-S-K-A-P-E
        assert "Enterococcus faecium" in names
        assert "Staphylococcus aureus" in names
        assert "Klebsiella pneumoniae" in names
        assert "Acinetobacter baumannii" in names
        assert "Pseudomonas aeruginosa" in names
        assert "Enterobacter cloacae" in names

    def test_even_distribution(self):
        """All organisms should have equal abundance."""
        mock = get_mock_community("eskape")
        for org in mock.organisms:
            assert abs(org.abundance - 1 / 6) < 0.001


class TestRespiratory:
    """Tests for respiratory pathogen panel mock."""

    def test_exists(self):
        """Respiratory mock should exist."""
        mock = get_mock_community("respiratory")
        assert mock is not None

    def test_has_6_organisms(self):
        """Should contain 6 respiratory pathogens."""
        mock = get_mock_community("respiratory")
        assert len(mock.organisms) == 6

    def test_contains_key_pathogens(self):
        """Should contain common respiratory pathogens."""
        mock = get_mock_community("respiratory")
        names = {o.name for o in mock.organisms}
        assert "Streptococcus pneumoniae" in names
        assert "Haemophilus influenzae" in names
        assert "Legionella pneumophila" in names


class TestWHOCritical:
    """Tests for WHO Critical Priority Pathogens mock."""

    def test_exists(self):
        """WHO critical mock should exist."""
        mock = get_mock_community("who_critical")
        assert mock is not None

    def test_has_5_organisms(self):
        """Should contain 5 carbapenem-resistant pathogens."""
        mock = get_mock_community("who_critical")
        assert len(mock.organisms) == 5

    def test_all_gram_negative(self):
        """All WHO critical priority pathogens should be bacteria."""
        mock = get_mock_community("who_critical")
        for org in mock.organisms:
            assert org.domain == "bacteria"


class TestBloodstream:
    """Tests for bloodstream infection panel mock."""

    def test_exists(self):
        """Bloodstream mock should exist."""
        mock = get_mock_community("bloodstream")
        assert mock is not None

    def test_has_6_organisms(self):
        """Should contain 6 organisms."""
        mock = get_mock_community("bloodstream")
        assert len(mock.organisms) == 6

    def test_includes_fungal_component(self):
        """Should include Candida albicans (fungaemia)."""
        mock = get_mock_community("bloodstream")
        fungi = [o for o in mock.organisms if o.domain == "eukaryota"]
        assert len(fungi) == 1
        assert fungi[0].name == "Candida albicans"


class TestWastewater:
    """Tests for wastewater surveillance mock."""

    def test_exists(self):
        """Wastewater mock should exist."""
        mock = get_mock_community("wastewater")
        assert mock is not None

    def test_has_6_organisms(self):
        """Should contain 6 indicator/pathogen organisms."""
        mock = get_mock_community("wastewater")
        assert len(mock.organisms) == 6

    def test_contains_indicator_organisms(self):
        """Should contain standard faecal indicator organisms."""
        mock = get_mock_community("wastewater")
        names = {o.name for o in mock.organisms}
        assert "Escherichia coli" in names
        assert "Enterococcus faecalis" in names


class TestQuickSingle:
    """Tests for single-species minimal mock."""

    def test_exists(self):
        """quick_single mock should exist."""
        mock = get_mock_community("quick_single")
        assert mock is not None

    def test_has_1_organism(self):
        """Should contain exactly 1 organism."""
        mock = get_mock_community("quick_single")
        assert len(mock.organisms) == 1

    def test_is_ecoli(self):
        """Single organism should be E. coli."""
        mock = get_mock_community("quick_single")
        assert mock.organisms[0].name == "Escherichia coli"

    def test_abundance_is_one(self):
        """Single organism should have abundance 1.0."""
        mock = get_mock_community("quick_single")
        assert mock.organisms[0].abundance == 1.0


class TestAllMocksIntegrity:
    """Cross-cutting tests for all built-in mocks."""

    def test_total_mock_count(self):
        """Should have 15 built-in mocks."""
        assert len(BUILTIN_MOCKS) == 15

    def test_all_mocks_have_accessions(self):
        """Every organism in every mock should have an explicit accession."""
        for name, mock in BUILTIN_MOCKS.items():
            for org in mock.organisms:
                assert org.accession is not None, (
                    f"{name}: {org.name} missing accession"
                )

    def test_all_mocks_have_domains(self):
        """Every organism in every mock should have an explicit domain."""
        for name, mock in BUILTIN_MOCKS.items():
            for org in mock.organisms:
                assert org.domain is not None, (
                    f"{name}: {org.name} missing domain"
                )

    def test_all_aliases_resolve(self):
        """Every alias should resolve to an existing mock."""
        for alias, target in MOCK_ALIASES.items():
            assert target in BUILTIN_MOCKS, (
                f"Alias '{alias}' -> '{target}' but '{target}' not in BUILTIN_MOCKS"
            )
