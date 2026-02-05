"""Mock community definitions for sample generation."""

from dataclasses import dataclass
from typing import List, Optional


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
