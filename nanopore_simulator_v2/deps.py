"""Dependency checking, install hints, and pre-flight validation.

Provides a unified interface for detecting external tools, Python
packages, and read generation backends. The ``check_preflight``
function validates that required dependencies are present before
long-running operations begin.
"""

import shutil
from dataclasses import dataclass
from typing import Dict, List


# Canonical install instructions for external dependencies.
INSTALL_HINTS: Dict[str, str] = {
    "badread": "conda install -c conda-forge -c bioconda badread",
    "nanosim": "conda install -c conda-forge -c bioconda nanosim",
    "datasets": "conda install -c conda-forge ncbi-datasets-cli",
    "psutil": "conda install -c conda-forge psutil",
    "numpy": "conda install -c conda-forge numpy",
}


@dataclass
class DependencyStatus:
    """Status of a single dependency.

    Attributes:
        name: Short identifier (e.g. "badread", "psutil").
        available: Whether the dependency was detected.
        category: Grouping label ("generator", "tool", or "python").
        install_hint: Shell command to install the dependency.
        description: Brief description of what the dependency provides.
        required_for: Note on when the dependency is needed.
    """

    name: str
    available: bool
    category: str
    install_hint: str
    description: str
    required_for: str


def get_install_hint(dep_name: str) -> str:
    """Return the install command for *dep_name*.

    Falls back to a generic message when *dep_name* is not in the
    known hint registry.
    """
    return INSTALL_HINTS.get(dep_name, f"Install '{dep_name}' manually")


def _detect_backends() -> Dict[str, bool]:
    """Detect available read-generation backends.

    Attempts to import the ``generators`` module from this package. If
    it is not yet available (the module is created in a later phase),
    falls back to checking whether external commands are on PATH.
    """
    try:
        from nanopore_simulator_v2.generators import detect_available_backends

        return detect_available_backends()
    except ImportError:
        # Fallback: builtin is always available; check CLI tools.
        return {
            "builtin": True,
            "badread": shutil.which("badread") is not None,
            "nanosim": shutil.which("NanoSim") is not None
            or shutil.which("nanosim") is not None,
        }


def check_all_dependencies() -> List[DependencyStatus]:
    """Check all known dependencies and return their status.

    Inspects read-generation backends, external CLI tools, and
    optional Python packages.
    """
    statuses: List[DependencyStatus] = []

    # -- Read generation backends --
    backends = _detect_backends()

    backend_meta = {
        "builtin": (
            "Error-free subsequence generator (always available)",
            "Core generate mode",
        ),
        "badread": (
            "Realistic nanopore read simulation",
            "--generator badread or --generator auto (preferred)",
        ),
        "nanosim": (
            "Read simulation via NanoSim",
            "--generator nanosim",
        ),
    }

    for name in ("builtin", "badread", "nanosim"):
        desc, needed = backend_meta[name]
        statuses.append(
            DependencyStatus(
                name=name,
                available=backends.get(name, False),
                category="generator",
                install_hint=get_install_hint(name),
                description=desc,
                required_for=needed,
            )
        )

    # -- External CLI tools --
    datasets_available = shutil.which("datasets") is not None
    statuses.append(
        DependencyStatus(
            name="datasets",
            available=datasets_available,
            category="tool",
            install_hint=get_install_hint("datasets"),
            description="NCBI genome download CLI",
            required_for="--species, --mock, --taxid options",
        )
    )

    # -- Optional Python packages --
    try:
        import psutil  # noqa: F401

        psutil_available = True
    except ImportError:
        psutil_available = False

    statuses.append(
        DependencyStatus(
            name="psutil",
            available=psutil_available,
            category="python",
            install_hint=get_install_hint("psutil"),
            description="System resource monitoring",
            required_for="--monitor enhanced",
        )
    )

    try:
        import numpy  # noqa: F401

        numpy_available = True
    except ImportError:
        numpy_available = False

    statuses.append(
        DependencyStatus(
            name="numpy",
            available=numpy_available,
            category="python",
            install_hint=get_install_hint("numpy"),
            description="Vectorized read generation (performance)",
            required_for="Faster builtin generator",
        )
    )

    return statuses


def check_preflight(
    *,
    operation: str = "generate",
    generator_backend: str = "auto",
    needs_genome_download: bool = False,
) -> List[str]:
    """Validate that required dependencies are present before a run.

    Returns a list of error messages. An empty list means all required
    dependencies are satisfied.

    Args:
        operation: "generate", "copy", or "link".
        generator_backend: Requested backend name.
        needs_genome_download: True when genome files must be fetched.
    """
    errors: List[str] = []

    # Replay mode has no external tool requirements (besides downloads).
    if operation in ("copy", "link"):
        if needs_genome_download and shutil.which("datasets") is None:
            errors.append(
                "The 'datasets' CLI is required for genome downloads but "
                f"was not found. Install with: {get_install_hint('datasets')}"
            )
        return errors

    # Generate mode: check requested backend.
    if generator_backend in ("badread", "nanosim"):
        if shutil.which(generator_backend) is None:
            errors.append(
                f"Requested generator backend '{generator_backend}' is not "
                f"installed. Install with: {get_install_hint(generator_backend)}"
            )

    # auto and builtin always have a fallback, so no error needed.

    # Genome downloads.
    if needs_genome_download and shutil.which("datasets") is None:
        errors.append(
            "The 'datasets' CLI is required for genome downloads but "
            f"was not found. Install with: {get_install_hint('datasets')}"
        )

    return errors
