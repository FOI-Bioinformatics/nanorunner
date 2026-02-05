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
    """

    name: str
    resolver: str  # "gtdb" or "ncbi"
    abundance: float  # Proportion in community (0.0-1.0)
    accession: Optional[str] = None  # Override specific strain

    def __post_init__(self) -> None:
        """Validate organism parameters after initialization."""
        valid_resolvers = {"gtdb", "ncbi"}
        if self.resolver not in valid_resolvers:
            raise ValueError(f"resolver must be one of {valid_resolvers}")
        if not 0.0 <= self.abundance <= 1.0:
            raise ValueError("abundance must be between 0.0 and 1.0")


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
    MockOrganism("Pseudomonas aeruginosa", "gtdb", 0.1),
    MockOrganism("Escherichia coli", "gtdb", 0.1),
    MockOrganism("Salmonella enterica", "gtdb", 0.1),
    MockOrganism("Lactobacillus fermentum", "gtdb", 0.1),
    MockOrganism("Enterococcus faecalis", "gtdb", 0.1),
    MockOrganism("Staphylococcus aureus", "gtdb", 0.1),
    MockOrganism("Listeria monocytogenes", "gtdb", 0.1),
    MockOrganism("Bacillus subtilis", "gtdb", 0.1),
    # Fungi - use NCBI resolver
    MockOrganism("Saccharomyces cerevisiae", "ncbi", 0.1, "GCF_000146045.2"),
    MockOrganism("Cryptococcus neoformans", "ncbi", 0.1, "GCF_000149245.1"),
]

# Zymo D6310 Log Distribution - same species as D6300, log-distributed abundances
_ZYMO_D6310_ORGANISMS = [
    MockOrganism("Listeria monocytogenes", "gtdb", 0.891),
    MockOrganism("Pseudomonas aeruginosa", "gtdb", 0.089),
    MockOrganism("Bacillus subtilis", "gtdb", 0.0089),
    MockOrganism("Escherichia coli", "gtdb", 0.00089),
    MockOrganism("Salmonella enterica", "gtdb", 0.000089),
    MockOrganism("Lactobacillus fermentum", "gtdb", 0.0000089),
    MockOrganism("Enterococcus faecalis", "gtdb", 0.00000089),
    MockOrganism("Staphylococcus aureus", "gtdb", 0.000000089),
    # Fungi - use NCBI resolver
    MockOrganism("Saccharomyces cerevisiae", "ncbi", 0.0002, "GCF_000146045.2"),
    MockOrganism("Cryptococcus neoformans", "ncbi", 0.00002, "GCF_000149245.1"),
]

_QUICK_3SPECIES_ORGANISMS = [
    MockOrganism("Escherichia coli", "gtdb", 1 / 3),
    MockOrganism("Staphylococcus aureus", "gtdb", 1 / 3),
    MockOrganism("Bacillus subtilis", "gtdb", 1 / 3),
]

_QUICK_GUT5_ORGANISMS = [
    MockOrganism("Bacteroides fragilis", "gtdb", 0.2),
    MockOrganism("Faecalibacterium prausnitzii", "gtdb", 0.2),
    MockOrganism("Escherichia coli", "gtdb", 0.2),
    MockOrganism("Bifidobacterium longum", "gtdb", 0.2),
    MockOrganism("Akkermansia muciniphila", "gtdb", 0.2),
]

_QUICK_PATHOGENS_ORGANISMS = [
    MockOrganism("Staphylococcus aureus", "gtdb", 0.2),
    MockOrganism("Escherichia coli", "gtdb", 0.2),
    MockOrganism("Klebsiella pneumoniae", "gtdb", 0.2),
    MockOrganism("Pseudomonas aeruginosa", "gtdb", 0.2),
    MockOrganism("Enterococcus faecium", "gtdb", 0.2),
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
        description="5 clinically relevant pathogens (ESKAPE subset)",
        organisms=_QUICK_PATHOGENS_ORGANISMS,
    ),
}

# Aliases for product codes (lowercase keys for case-insensitive lookup)
MOCK_ALIASES: Dict[str, str] = {
    "d6305": "zymo_d6300",
    "d6306": "zymo_d6300",
    "zymo_d6305": "zymo_d6300",
    "zymo_d6306": "zymo_d6300",
    "d6310": "zymo_d6310",
    "d6311": "zymo_d6310",
    "zymo_d6311": "zymo_d6310",
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
    """
    return {name: mock.description for name, mock in BUILTIN_MOCKS.items()}
