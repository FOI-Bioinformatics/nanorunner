"""Pipeline validation for output directory structure.

Provides lightweight validation that an output directory conforms to the
file patterns expected by a given bioinformatics pipeline. No abstract
classes or manager objects -- just data and functions.
"""

from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# Adapter configurations
# ---------------------------------------------------------------------------

ADAPTERS: Dict[str, Dict[str, Any]] = {
    "nanometa": {
        "name": "nanometa",
        "description": "Nanometa Live real-time taxonomic analysis pipeline",
        "patterns": [
            "*.fastq",
            "*.fq",
            "*.fastq.gz",
            "*.fq.gz",
            "*.pod5",
        ],
    },
    "kraken": {
        "name": "kraken",
        "description": "Kraken2/KrakenUniq taxonomic classification pipeline",
        "patterns": [
            "*.fastq",
            "*.fq",
            "*.fastq.gz",
            "*.fq.gz",
        ],
    },
}

# Backward-compatible aliases.
_ALIASES: Dict[str, str] = {
    "nanometanf": "nanometa",
}


def _resolve_name(name: str) -> str:
    """Resolve an adapter name, applying aliases and lowering case.

    Raises:
        KeyError: If the name (after alias resolution) is not found.
    """
    key = name.lower()
    key = _ALIASES.get(key, key)
    if key not in ADAPTERS:
        raise KeyError(f"Unknown adapter: '{name}'")
    return key


def _find_matching_files(target: Path, patterns: List[str]) -> List[Path]:
    """Collect all files under *target* matching any of the glob patterns.

    Searches both the root directory and one level of subdirectories to
    handle both singleplex and multiplex layouts.
    """
    matched: List[Path] = []
    if not target.is_dir():
        return matched

    for item in target.iterdir():
        if item.is_file():
            for pat in patterns:
                if fnmatch(item.name, pat):
                    matched.append(item)
                    break
        elif item.is_dir():
            for child in item.iterdir():
                if child.is_file():
                    for pat in patterns:
                        if fnmatch(child.name, pat):
                            matched.append(child)
                            break
    return matched


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_output(target: Path, adapter_name: str) -> List[str]:
    """Check whether *target* has files matching the adapter's patterns.

    Args:
        target: Output directory to validate.
        adapter_name: Registered adapter name or alias.

    Returns:
        A list of issue descriptions. An empty list means the directory
        structure is valid for the given pipeline.

    Raises:
        KeyError: If *adapter_name* is not a known adapter or alias.
    """
    key = _resolve_name(adapter_name)
    config = ADAPTERS[key]
    issues: List[str] = []

    if not target.exists():
        issues.append(f"Directory does not exist: {target}")
        return issues

    if not target.is_dir():
        issues.append(f"Path is not a directory: {target}")
        return issues

    patterns = config["patterns"]
    matched = _find_matching_files(target, patterns)

    if not matched:
        issues.append(f"No files matching {patterns} found in {target}")

    return issues


def list_adapters() -> Dict[str, str]:
    """Return a mapping of adapter names to their descriptions."""
    return {name: cfg["description"] for name, cfg in ADAPTERS.items()}


def get_adapter_info(name: str) -> Dict[str, Any]:
    """Return the full configuration dict for an adapter.

    Args:
        name: Adapter name or alias.

    Returns:
        A dict with keys ``name``, ``description``, and ``patterns``.

    Raises:
        KeyError: If the adapter is not found.
    """
    key = _resolve_name(name)
    return dict(ADAPTERS[key])
