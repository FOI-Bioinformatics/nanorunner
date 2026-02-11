"""Mock community definitions for sample generation."""

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class MockOrganism:
    """A single organism in a mock community.

    Attributes:
        name: Species or strain name for the organism.
        resolver: Database resolver to use ("gtdb" or "ncbi").
        abundance: Proportion in community, must be between 0.0 and 1.0.
        accession: Optional specific genome accession to override default.
        domain: Taxonomic domain ("bacteria", "archaea", or "eukaryota").
            Used for correct genome resolution. Defaults to None, in which
            case domain is inferred from the resolver during resolution.
    """

    name: str
    resolver: str  # "gtdb" or "ncbi"
    abundance: float  # Proportion in community (0.0-1.0)
    accession: Optional[str] = None  # Override specific strain
    domain: Optional[str] = None  # "bacteria", "archaea", or "eukaryota"

    def __post_init__(self) -> None:
        """Validate organism parameters after initialization."""
        valid_resolvers = {"gtdb", "ncbi"}
        if self.resolver not in valid_resolvers:
            raise ValueError(f"resolver must be one of {valid_resolvers}")
        if not 0.0 <= self.abundance <= 1.0:
            raise ValueError("abundance must be between 0.0 and 1.0")
        valid_domains = {"bacteria", "archaea", "eukaryota", None}
        if self.domain not in valid_domains:
            raise ValueError(
                f"domain must be one of {{'bacteria', 'archaea', 'eukaryota'}} or None"
            )


@dataclass
class MockCommunity:
    """A preset mock community with defined composition.

    Attributes:
        name: Identifier for the mock community.
        description: Human-readable description of the community.
        organisms: List of MockOrganism instances comprising the community.
    """

    name: str
    description: str
    organisms: List[MockOrganism]

    def __post_init__(self) -> None:
        """Validate community parameters after initialization."""
        if not self.organisms:
            raise ValueError("MockCommunity must have at least one organism")
        total = sum(org.abundance for org in self.organisms)
        if not 0.99 <= total <= 1.01:
            raise ValueError(f"Organism abundances must sum to 1.0 (got {total:.3f})")


# Zymo D6300 Standard (Even) - 8 bacteria + 2 yeasts
_ZYMO_D6300_ORGANISMS = [
    MockOrganism(
        "Pseudomonas aeruginosa", "ncbi", 0.1, "GCF_000006765.1", domain="bacteria"
    ),
    MockOrganism(
        "Escherichia coli", "ncbi", 0.1, "GCF_000005845.2", domain="bacteria"
    ),
    MockOrganism(
        "Salmonella enterica", "ncbi", 0.1, "GCF_000006945.2", domain="bacteria"
    ),
    MockOrganism(
        "Lactobacillus fermentum", "ncbi", 0.1, "GCF_000159215.1", domain="bacteria"
    ),
    MockOrganism(
        "Enterococcus faecalis", "ncbi", 0.1, "GCF_000007785.1", domain="bacteria"
    ),
    MockOrganism(
        "Staphylococcus aureus", "ncbi", 0.1, "GCF_000013425.1", domain="bacteria"
    ),
    MockOrganism(
        "Listeria monocytogenes", "ncbi", 0.1, "GCF_000196035.1", domain="bacteria"
    ),
    MockOrganism(
        "Bacillus subtilis", "ncbi", 0.1, "GCF_000009045.1", domain="bacteria"
    ),
    # Fungi
    MockOrganism(
        "Saccharomyces cerevisiae", "ncbi", 0.1, "GCF_000146045.2", domain="eukaryota"
    ),
    MockOrganism(
        "Cryptococcus neoformans", "ncbi", 0.1, "GCF_000149245.1", domain="eukaryota"
    ),
]

# Zymo D6310 Log Distribution - same species as D6300, log-distributed abundances.
# Organisms are ordered by decreasing genomic DNA abundance following the
# published Zymo spec.  Pairs share a log level; the series spans ~7 orders
# of magnitude from Listeria (89.1%) to C. neoformans (0.0000089%).
_ZYMO_D6310_ORGANISMS = [
    MockOrganism(
        "Listeria monocytogenes", "ncbi", 0.891, "GCF_000196035.1", domain="bacteria"
    ),
    MockOrganism(
        "Pseudomonas aeruginosa", "ncbi", 0.089, "GCF_000006765.1", domain="bacteria"
    ),
    MockOrganism(
        "Bacillus subtilis", "ncbi", 0.0089, "GCF_000009045.1", domain="bacteria"
    ),
    MockOrganism(
        "Saccharomyces cerevisiae", "ncbi", 0.0089, "GCF_000146045.2", domain="eukaryota"
    ),
    MockOrganism(
        "Escherichia coli", "ncbi", 0.00089, "GCF_000005845.2", domain="bacteria"
    ),
    MockOrganism(
        "Salmonella enterica", "ncbi", 0.00089, "GCF_000006945.2", domain="bacteria"
    ),
    MockOrganism(
        "Lactobacillus fermentum", "ncbi", 0.000089, "GCF_000159215.1", domain="bacteria"
    ),
    MockOrganism(
        "Enterococcus faecalis", "ncbi", 0.0000089, "GCF_000007785.1", domain="bacteria"
    ),
    MockOrganism(
        "Staphylococcus aureus", "ncbi", 0.00000089, "GCF_000013425.1", domain="bacteria"
    ),
    MockOrganism(
        "Cryptococcus neoformans", "ncbi", 0.000000089, "GCF_000149245.1", domain="eukaryota"
    ),
]

_QUICK_3SPECIES_ORGANISMS = [
    MockOrganism(
        "Escherichia coli", "ncbi", 1 / 3, "GCF_000005845.2", domain="bacteria"
    ),
    MockOrganism(
        "Staphylococcus aureus", "ncbi", 1 / 3, "GCF_000013425.1", domain="bacteria"
    ),
    MockOrganism(
        "Bacillus subtilis", "ncbi", 1 / 3, "GCF_000009045.1", domain="bacteria"
    ),
]

_QUICK_GUT5_ORGANISMS = [
    MockOrganism(
        "Bacteroides fragilis", "ncbi", 0.2, "GCF_000025985.1", domain="bacteria"
    ),
    MockOrganism(
        "Faecalibacterium prausnitzii", "ncbi", 0.2, "GCF_000162015.1", domain="bacteria"
    ),
    MockOrganism(
        "Escherichia coli", "ncbi", 0.2, "GCF_000005845.2", domain="bacteria"
    ),
    MockOrganism(
        "Bifidobacterium longum", "ncbi", 0.2, "GCF_000007525.1", domain="bacteria"
    ),
    MockOrganism(
        "Akkermansia muciniphila", "ncbi", 0.2, "GCF_000020225.1", domain="bacteria"
    ),
]

_QUICK_PATHOGENS_ORGANISMS = [
    MockOrganism(
        "Staphylococcus aureus", "ncbi", 0.2, "GCF_000013425.1", domain="bacteria"
    ),
    MockOrganism(
        "Escherichia coli", "ncbi", 0.2, "GCF_000005845.2", domain="bacteria"
    ),
    MockOrganism(
        "Klebsiella pneumoniae", "ncbi", 0.2, "GCF_000240185.1", domain="bacteria"
    ),
    MockOrganism(
        "Pseudomonas aeruginosa", "ncbi", 0.2, "GCF_000006765.1", domain="bacteria"
    ),
    MockOrganism(
        "Enterococcus faecium", "ncbi", 0.2, "GCF_000174395.2", domain="bacteria"
    ),
]

# ATCC MSA-1002 - 20 Strain Even Mix (5% each)
_ATCC_MSA1002_ORGANISMS = [
    MockOrganism(
        "Acinetobacter baumannii", "ncbi", 0.05, "GCF_000015425.1", domain="bacteria"
    ),
    MockOrganism(
        "Bacillus pacificus", "ncbi", 0.05, "GCF_020861345.1", domain="bacteria"
    ),
    MockOrganism(
        "Phocaeicola vulgatus", "ncbi", 0.05, "GCF_000012825.1", domain="bacteria"
    ),
    MockOrganism(
        "Bifidobacterium adolescentis", "ncbi", 0.05, "GCF_000010425.1", domain="bacteria"
    ),
    MockOrganism(
        "Clostridium beijerinckii", "ncbi", 0.05, "GCF_000016965.1", domain="bacteria"
    ),
    MockOrganism(
        "Cutibacterium acnes", "ncbi", 0.05, "GCF_000008345.1", domain="bacteria"
    ),
    MockOrganism(
        "Deinococcus radiodurans", "ncbi", 0.05, "GCF_000008565.1", domain="bacteria"
    ),
    MockOrganism(
        "Enterococcus faecalis", "ncbi", 0.05, "GCF_000007785.1", domain="bacteria"
    ),
    MockOrganism(
        "Escherichia coli", "ncbi", 0.05, "GCF_000005845.2", domain="bacteria"
    ),
    MockOrganism(
        "Helicobacter pylori", "ncbi", 0.05, "GCF_000008525.1", domain="bacteria"
    ),
    MockOrganism(
        "Lactobacillus gasseri", "ncbi", 0.05, "GCF_000014425.1", domain="bacteria"
    ),
    MockOrganism(
        "Neisseria meningitidis", "ncbi", 0.05, "GCF_000008805.1", domain="bacteria"
    ),
    MockOrganism(
        "Porphyromonas gingivalis", "ncbi", 0.05, "GCF_000007585.1", domain="bacteria"
    ),
    MockOrganism(
        "Pseudomonas paraeruginosa", "ncbi", 0.05, "GCF_000017205.1", domain="bacteria"
    ),
    MockOrganism(
        "Cereibacter sphaeroides", "ncbi", 0.05, "GCF_000012905.2", domain="bacteria"
    ),
    MockOrganism(
        "Schaalia odontolytica", "ncbi", 0.05, "GCF_031191545.1", domain="bacteria"
    ),
    MockOrganism(
        "Staphylococcus aureus", "ncbi", 0.05, "GCF_000013425.1", domain="bacteria"
    ),
    MockOrganism(
        "Staphylococcus epidermidis", "ncbi", 0.05, "GCF_000007645.1", domain="bacteria"
    ),
    MockOrganism(
        "Streptococcus agalactiae", "ncbi", 0.05, "GCF_000007265.1", domain="bacteria"
    ),
    MockOrganism(
        "Streptococcus mutans", "ncbi", 0.05, "GCF_000007465.2", domain="bacteria"
    ),
]

# ATCC MSA-1003 - 20 Strain Staggered Mix (0.02% to 18%)
_ATCC_MSA1003_ORGANISMS = [
    # High abundance (18%)
    MockOrganism(
        "Escherichia coli", "ncbi", 0.18, "GCF_000005845.2", domain="bacteria"
    ),
    MockOrganism(
        "Porphyromonas gingivalis", "ncbi", 0.18, "GCF_000007585.1", domain="bacteria"
    ),
    MockOrganism(
        "Cereibacter sphaeroides", "ncbi", 0.18, "GCF_000012905.2", domain="bacteria"
    ),
    MockOrganism(
        "Staphylococcus epidermidis", "ncbi", 0.18, "GCF_000007645.1", domain="bacteria"
    ),
    MockOrganism(
        "Streptococcus mutans", "ncbi", 0.18, "GCF_000007465.2", domain="bacteria"
    ),
    # Medium abundance (1.8%)
    MockOrganism(
        "Bacillus pacificus", "ncbi", 0.018, "GCF_020861345.1", domain="bacteria"
    ),
    MockOrganism(
        "Clostridium beijerinckii", "ncbi", 0.018, "GCF_000016965.1", domain="bacteria"
    ),
    MockOrganism(
        "Pseudomonas paraeruginosa", "ncbi", 0.018, "GCF_000017205.1", domain="bacteria"
    ),
    MockOrganism(
        "Staphylococcus aureus", "ncbi", 0.018, "GCF_000013425.1", domain="bacteria"
    ),
    MockOrganism(
        "Streptococcus agalactiae", "ncbi", 0.018, "GCF_000007265.1", domain="bacteria"
    ),
    # Low abundance (0.18%)
    MockOrganism(
        "Acinetobacter baumannii", "ncbi", 0.0018, "GCF_000015425.1", domain="bacteria"
    ),
    MockOrganism(
        "Cutibacterium acnes", "ncbi", 0.0018, "GCF_000008345.1", domain="bacteria"
    ),
    MockOrganism(
        "Helicobacter pylori", "ncbi", 0.0018, "GCF_000008525.1", domain="bacteria"
    ),
    MockOrganism(
        "Lactobacillus gasseri", "ncbi", 0.0018, "GCF_000014425.1", domain="bacteria"
    ),
    MockOrganism(
        "Neisseria meningitidis", "ncbi", 0.0018, "GCF_000008805.1", domain="bacteria"
    ),
    # Very low abundance (0.02%)
    MockOrganism(
        "Phocaeicola vulgatus", "ncbi", 0.0002, "GCF_000012825.1", domain="bacteria"
    ),
    MockOrganism(
        "Bifidobacterium adolescentis", "ncbi", 0.0002, "GCF_000010425.1", domain="bacteria"
    ),
    MockOrganism(
        "Deinococcus radiodurans", "ncbi", 0.0002, "GCF_000008565.1", domain="bacteria"
    ),
    MockOrganism(
        "Enterococcus faecalis", "ncbi", 0.0002, "GCF_000007785.1", domain="bacteria"
    ),
    MockOrganism(
        "Schaalia odontolytica", "ncbi", 0.0002, "GCF_031191545.1", domain="bacteria"
    ),
]

# Zymo D6331 Gut Microbiome Standard - 21 strains across 17 species
# (bacteria, archaea, fungi).  Five E. coli strains (NRRL collection) are
# listed individually at 2.8% each (14% total).  Zymo-submitted RefSeq
# assemblies from BioProject PRJNA933634 (2023).
_ZYMO_D6331_ORGANISMS = [
    # High abundance (14%)
    MockOrganism(
        "Faecalibacterium prausnitzii", "ncbi", 0.14, "GCF_000162015.1", domain="bacteria"
    ),
    MockOrganism(
        "Veillonella rogosae", "ncbi", 0.14, "GCF_001312485.1", domain="bacteria"
    ),
    MockOrganism(
        "Roseburia hominis", "ncbi", 0.14, "GCF_000225345.1", domain="bacteria"
    ),
    MockOrganism(
        "Bacteroides fragilis", "ncbi", 0.14, "GCF_000025985.1", domain="bacteria"
    ),
    # E. coli strains — 5 NRRL strains at 2.8% each (14% total)
    MockOrganism(
        "Escherichia coli B-1109", "ncbi", 0.028, "GCF_028743555.1", domain="bacteria"
    ),
    MockOrganism(
        "Escherichia coli JM109", "ncbi", 0.028, "GCF_028743375.1", domain="bacteria"
    ),
    MockOrganism(
        "Escherichia coli B-3008", "ncbi", 0.028, "GCF_028743355.1", domain="bacteria"
    ),
    MockOrganism(
        "Escherichia coli B-766", "ncbi", 0.028, "GCF_028743755.1", domain="bacteria"
    ),
    MockOrganism(
        "Escherichia coli B-2207", "ncbi", 0.028, "GCF_028743335.1", domain="bacteria"
    ),
    # Medium abundance (6%)
    MockOrganism(
        "Prevotella corporis", "ncbi", 0.06, "GCF_000430525.1", domain="bacteria"
    ),
    MockOrganism(
        "Bifidobacterium adolescentis", "ncbi", 0.06, "GCF_000010425.1", domain="bacteria"
    ),
    MockOrganism(
        "Fusobacterium nucleatum", "ncbi", 0.06, "GCF_000007325.1", domain="bacteria"
    ),
    MockOrganism(
        "Lactobacillus fermentum", "ncbi", 0.06, "GCF_000159215.1", domain="bacteria"
    ),
    # Low abundance (1.4-1.5%)
    MockOrganism(
        "Clostridioides difficile", "ncbi", 0.015, "GCF_000009205.2", domain="bacteria"
    ),
    MockOrganism(
        "Akkermansia muciniphila", "ncbi", 0.015, "GCF_000020225.1", domain="bacteria"
    ),
    MockOrganism(
        "Candida albicans", "ncbi", 0.015, "GCF_000182965.3", domain="eukaryota"
    ),
    MockOrganism(
        "Saccharomyces cerevisiae", "ncbi", 0.014, "GCF_000146045.2", domain="eukaryota"
    ),
    # Very low abundance (0.1% and below)
    MockOrganism(
        "Methanobrevibacter smithii", "ncbi", 0.001, "GCF_000016525.1", domain="archaea"
    ),
    MockOrganism(
        "Salmonella enterica", "ncbi", 0.0001, "GCF_000006945.2", domain="bacteria"
    ),
    MockOrganism(
        "Enterococcus faecalis", "ncbi", 0.00001, "GCF_000007785.1", domain="bacteria"
    ),
    MockOrganism(
        "Clostridium perfringens", "ncbi", 0.000001, "GCF_000009685.1", domain="bacteria"
    ),
]

# CDC/USDA Tier 1 bacterial select agents (as of 2025 Federal Register)
_CDC_SELECT_AGENTS_ORGANISMS = [
    MockOrganism(
        "Bacillus anthracis", "ncbi", 1 / 6, "GCF_000008445.1", domain="bacteria"
    ),
    MockOrganism(
        "Yersinia pestis", "ncbi", 1 / 6, "GCF_000009065.1", domain="bacteria"
    ),
    MockOrganism(
        "Francisella tularensis", "ncbi", 1 / 6, "GCF_000008985.1", domain="bacteria"
    ),
    MockOrganism(
        "Burkholderia pseudomallei", "ncbi", 1 / 6, "GCF_000011545.1", domain="bacteria"
    ),
    MockOrganism(
        "Burkholderia mallei", "ncbi", 1 / 6, "GCF_000011705.1", domain="bacteria"
    ),
    MockOrganism(
        "Coxiella burnetii", "ncbi", 1 / 6, "GCF_000007765.2", domain="bacteria"
    ),
]

# ESKAPE pathogens - the six canonical hospital-acquired multidrug-resistant organisms
_ESKAPE_ORGANISMS = [
    MockOrganism(
        "Enterococcus faecium", "ncbi", 1 / 6, "GCF_000174395.2", domain="bacteria"
    ),
    MockOrganism(
        "Staphylococcus aureus", "ncbi", 1 / 6, "GCF_000013425.1", domain="bacteria"
    ),
    MockOrganism(
        "Klebsiella pneumoniae", "ncbi", 1 / 6, "GCF_000240185.1", domain="bacteria"
    ),
    MockOrganism(
        "Acinetobacter baumannii", "ncbi", 1 / 6, "GCF_000015425.1", domain="bacteria"
    ),
    MockOrganism(
        "Pseudomonas aeruginosa", "ncbi", 1 / 6, "GCF_000006765.1", domain="bacteria"
    ),
    MockOrganism(
        "Enterobacter cloacae", "ncbi", 1 / 6, "GCF_000025565.1", domain="bacteria"
    ),
]

# Respiratory pathogen panel - common causes of community-acquired pneumonia
_RESPIRATORY_ORGANISMS = [
    MockOrganism(
        "Streptococcus pneumoniae", "ncbi", 1 / 6, "GCF_000006885.1", domain="bacteria"
    ),
    MockOrganism(
        "Haemophilus influenzae", "ncbi", 1 / 6, "GCF_000027305.1", domain="bacteria"
    ),
    MockOrganism(
        "Moraxella catarrhalis", "ncbi", 1 / 6, "GCF_000193045.1", domain="bacteria"
    ),
    MockOrganism(
        "Klebsiella pneumoniae", "ncbi", 1 / 6, "GCF_000240185.1", domain="bacteria"
    ),
    MockOrganism(
        "Legionella pneumophila", "ncbi", 1 / 6, "GCF_000008485.1", domain="bacteria"
    ),
    MockOrganism(
        "Mycoplasma pneumoniae", "ncbi", 1 / 6, "GCF_000027345.1", domain="bacteria"
    ),
]

# WHO Critical Priority Pathogens - carbapenem-resistant Gram-negatives
_WHO_CRITICAL_ORGANISMS = [
    MockOrganism(
        "Acinetobacter baumannii", "ncbi", 0.2, "GCF_000015425.1", domain="bacteria"
    ),
    MockOrganism(
        "Pseudomonas aeruginosa", "ncbi", 0.2, "GCF_000006765.1", domain="bacteria"
    ),
    MockOrganism(
        "Klebsiella pneumoniae", "ncbi", 0.2, "GCF_000240185.1", domain="bacteria"
    ),
    MockOrganism(
        "Escherichia coli", "ncbi", 0.2, "GCF_000005845.2", domain="bacteria"
    ),
    MockOrganism(
        "Enterobacter cloacae", "ncbi", 0.2, "GCF_000025565.1", domain="bacteria"
    ),
]

# Bloodstream infection panel - common causes of bacteraemia and fungaemia
_BLOODSTREAM_ORGANISMS = [
    MockOrganism(
        "Staphylococcus aureus", "ncbi", 1 / 6, "GCF_000013425.1", domain="bacteria"
    ),
    MockOrganism(
        "Escherichia coli", "ncbi", 1 / 6, "GCF_000005845.2", domain="bacteria"
    ),
    MockOrganism(
        "Klebsiella pneumoniae", "ncbi", 1 / 6, "GCF_000240185.1", domain="bacteria"
    ),
    MockOrganism(
        "Enterococcus faecalis", "ncbi", 1 / 6, "GCF_000007785.1", domain="bacteria"
    ),
    MockOrganism(
        "Staphylococcus epidermidis", "ncbi", 1 / 6, "GCF_000007645.1", domain="bacteria"
    ),
    MockOrganism(
        "Candida albicans", "ncbi", 1 / 6, "GCF_000182965.3", domain="eukaryota"
    ),
]

# Wastewater surveillance panel - indicator organisms and waterborne pathogens
_WASTEWATER_ORGANISMS = [
    MockOrganism(
        "Escherichia coli", "ncbi", 1 / 6, "GCF_000005845.2", domain="bacteria"
    ),
    MockOrganism(
        "Enterococcus faecalis", "ncbi", 1 / 6, "GCF_000007785.1", domain="bacteria"
    ),
    MockOrganism(
        "Salmonella enterica", "ncbi", 1 / 6, "GCF_000006945.2", domain="bacteria"
    ),
    MockOrganism(
        "Campylobacter jejuni", "ncbi", 1 / 6, "GCF_000009085.1", domain="bacteria"
    ),
    MockOrganism(
        "Legionella pneumophila", "ncbi", 1 / 6, "GCF_000008485.1", domain="bacteria"
    ),
    MockOrganism(
        "Vibrio cholerae", "ncbi", 1 / 6, "GCF_000006745.1", domain="bacteria"
    ),
]

# Single-species mock for minimal regression testing
_QUICK_SINGLE_ORGANISMS = [
    MockOrganism(
        "Escherichia coli", "ncbi", 1.0, "GCF_000005845.2", domain="bacteria"
    ),
]


BUILTIN_MOCKS: Dict[str, MockCommunity] = {
    "zymo_d6300": MockCommunity(
        name="zymo_d6300",
        description="Zymo D6300 Standard (even) - 8 bacteria + 2 yeasts",
        organisms=_ZYMO_D6300_ORGANISMS,
    ),
    "zymo_d6310": MockCommunity(
        name="zymo_d6310",
        description="Zymo D6310 Log Distribution - 8 bacteria + 2 yeasts",
        organisms=_ZYMO_D6310_ORGANISMS,
    ),
    "quick_3species": MockCommunity(
        name="quick_3species",
        description="Minimal 3-species test mock (E. coli, S. aureus, B. subtilis)",
        organisms=_QUICK_3SPECIES_ORGANISMS,
    ),
    "quick_gut5": MockCommunity(
        name="quick_gut5",
        description="Simple 5-species gut microbiome mock",
        organisms=_QUICK_GUT5_ORGANISMS,
    ),
    "quick_pathogens": MockCommunity(
        name="quick_pathogens",
        description="5 clinically relevant nosocomial pathogens",
        organisms=_QUICK_PATHOGENS_ORGANISMS,
    ),
    "atcc_msa1002": MockCommunity(
        name="atcc_msa1002",
        description="ATCC MSA-1002 20-strain even mix (5% each)",
        organisms=_ATCC_MSA1002_ORGANISMS,
    ),
    "atcc_msa1003": MockCommunity(
        name="atcc_msa1003",
        description="ATCC MSA-1003 20-strain staggered mix (0.02%-18%)",
        organisms=_ATCC_MSA1003_ORGANISMS,
    ),
    "zymo_d6331": MockCommunity(
        name="zymo_d6331",
        description="Zymo D6331 Gut Microbiome Standard - 21 strains, 17 species (bacteria, archaea, fungi)",
        organisms=_ZYMO_D6331_ORGANISMS,
    ),
    # -- Clinical / surveillance mocks ------------------------------------
    "cdc_select_agents": MockCommunity(
        name="cdc_select_agents",
        description="CDC/USDA Tier 1 bacterial select agents - 6 species, even mix",
        organisms=_CDC_SELECT_AGENTS_ORGANISMS,
    ),
    "eskape": MockCommunity(
        name="eskape",
        description="ESKAPE nosocomial pathogens - 6 species, even mix",
        organisms=_ESKAPE_ORGANISMS,
    ),
    "respiratory": MockCommunity(
        name="respiratory",
        description="Community-acquired respiratory pathogens - 6 species, even mix",
        organisms=_RESPIRATORY_ORGANISMS,
    ),
    "who_critical": MockCommunity(
        name="who_critical",
        description="WHO Critical Priority carbapenem-resistant pathogens - 5 species",
        organisms=_WHO_CRITICAL_ORGANISMS,
    ),
    "bloodstream": MockCommunity(
        name="bloodstream",
        description="Bloodstream infection panel - 5 bacteria + 1 yeast, even mix",
        organisms=_BLOODSTREAM_ORGANISMS,
    ),
    "wastewater": MockCommunity(
        name="wastewater",
        description="Wastewater surveillance indicators and waterborne pathogens - 6 species",
        organisms=_WASTEWATER_ORGANISMS,
    ),
    "quick_single": MockCommunity(
        name="quick_single",
        description="Single species (E. coli) for minimal regression testing",
        organisms=_QUICK_SINGLE_ORGANISMS,
    ),
}

# Aliases for product codes (lowercase keys for case-insensitive lookup)
MOCK_ALIASES: Dict[str, str] = {
    # Zymo aliases
    "d6305": "zymo_d6300",
    "d6306": "zymo_d6300",
    "zymo_d6305": "zymo_d6300",
    "zymo_d6306": "zymo_d6300",
    "d6310": "zymo_d6310",
    "d6311": "zymo_d6310",
    "zymo_d6311": "zymo_d6310",
    "d6331": "zymo_d6331",
    # ATCC aliases
    "msa1002": "atcc_msa1002",
    "msa-1002": "atcc_msa1002",
    "msa_1002": "atcc_msa1002",
    "msa1003": "atcc_msa1003",
    "msa-1003": "atcc_msa1003",
    "msa_1003": "atcc_msa1003",
    # CDC alias
    "select_agents": "cdc_select_agents",
}


def get_mock_community(name: str) -> Optional[MockCommunity]:
    """Get a mock community by name.

    Supports case-insensitive lookup and aliases (e.g., D6305 -> zymo_d6300).

    Args:
        name: The identifier of the mock community to retrieve.

    Returns:
        The MockCommunity if found, None otherwise.
    """
    normalized = name.lower()
    # Check aliases first
    if normalized in MOCK_ALIASES:
        normalized = MOCK_ALIASES[normalized]
    return BUILTIN_MOCKS.get(normalized)


def list_mock_communities() -> Dict[str, str]:
    """List all available mock communities with descriptions.

    Returns:
        Dictionary mapping mock community names to their descriptions.
        Includes aliases with "(alias for X)" notation.
    """
    result = {name: mock.description for name, mock in BUILTIN_MOCKS.items()}
    # Add aliases
    for alias, target in MOCK_ALIASES.items():
        if target in BUILTIN_MOCKS:
            result[alias] = f"(alias for {target})"
    return result
