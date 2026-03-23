"""Tests for dependency checking and pre-flight validation."""

import pytest
from unittest.mock import patch

from nanopore_simulator.deps import (
    DependencyStatus,
    INSTALL_HINTS,
    get_install_hint,
    check_all_dependencies,
    check_preflight,
)


class TestDependencyStatus:
    """Validate DependencyStatus dataclass."""

    def test_creates_status(self) -> None:
        status = DependencyStatus(
            name="test",
            available=True,
            category="tool",
            install_hint="pip install test",
            description="A test dependency",
            required_for="testing",
        )
        assert status.name == "test"
        assert status.available is True
        assert status.category == "tool"
        assert status.install_hint == "pip install test"
        assert status.description == "A test dependency"
        assert status.required_for == "testing"

    def test_unavailable_status(self) -> None:
        status = DependencyStatus(
            name="missing",
            available=False,
            category="generator",
            install_hint="conda install missing",
            description="Not installed",
            required_for="something",
        )
        assert status.available is False


class TestGetInstallHint:
    """Validate install hint lookup."""

    def test_known_dependency(self) -> None:
        hint = get_install_hint("badread")
        assert "badread" in hint

    def test_another_known(self) -> None:
        hint = get_install_hint("psutil")
        assert "psutil" in hint

    def test_unknown_dependency(self) -> None:
        hint = get_install_hint("totally_unknown_thing")
        assert "totally_unknown_thing" in hint
        # Should contain a generic fallback message
        assert "install" in hint.lower()

    def test_all_hints_are_strings(self) -> None:
        for name, hint in INSTALL_HINTS.items():
            assert isinstance(hint, str)
            assert len(hint) > 0


class TestCheckAllDependencies:
    """Validate comprehensive dependency checking."""

    def test_returns_list(self) -> None:
        result = check_all_dependencies()
        assert isinstance(result, list)

    def test_all_items_are_dependency_status(self) -> None:
        result = check_all_dependencies()
        for item in result:
            assert isinstance(item, DependencyStatus)

    def test_builtin_always_available(self) -> None:
        """The builtin generator has no external deps and is always present."""
        result = check_all_dependencies()
        builtin_statuses = [s for s in result if s.name == "builtin"]
        assert len(builtin_statuses) == 1
        assert builtin_statuses[0].available is True

    def test_contains_generator_category(self) -> None:
        result = check_all_dependencies()
        categories = {s.category for s in result}
        assert "generator" in categories

    def test_contains_python_category(self) -> None:
        result = check_all_dependencies()
        categories = {s.category for s in result}
        assert "python" in categories

    def test_contains_tool_category(self) -> None:
        result = check_all_dependencies()
        categories = {s.category for s in result}
        assert "tool" in categories

    def test_each_status_has_install_hint(self) -> None:
        result = check_all_dependencies()
        for status in result:
            assert len(status.install_hint) > 0

    def test_each_status_has_description(self) -> None:
        result = check_all_dependencies()
        for status in result:
            assert len(status.description) > 0


class TestCheckPreflight:
    """Validate pre-flight checks for different operation modes."""

    def test_replay_no_issues(self) -> None:
        """Replay mode (copy) requires no external tools."""
        issues = check_preflight(operation="copy")
        assert issues == []

    def test_replay_link_no_issues(self) -> None:
        issues = check_preflight(operation="link")
        assert issues == []

    def test_generate_builtin_no_issues(self) -> None:
        """Generate mode with builtin backend requires nothing external."""
        issues = check_preflight(operation="generate", generator_backend="builtin")
        assert issues == []

    def test_generate_auto_no_issues(self) -> None:
        """Auto mode always has builtin as fallback."""
        issues = check_preflight(operation="generate", generator_backend="auto")
        assert issues == []

    @patch("shutil.which", return_value=None)
    def test_generate_badread_missing(self, mock_which: object) -> None:
        """Request for missing badread backend should produce an issue."""
        issues = check_preflight(operation="generate", generator_backend="badread")
        assert len(issues) >= 1
        assert any("badread" in msg for msg in issues)

    @patch("shutil.which", return_value=None)
    def test_genome_download_needs_datasets(self, mock_which: object) -> None:
        """Genome downloads require the datasets CLI."""
        issues = check_preflight(
            operation="generate",
            generator_backend="builtin",
            needs_genome_download=True,
        )
        assert len(issues) >= 1
        assert any("datasets" in msg for msg in issues)

    @patch("shutil.which", return_value="/usr/local/bin/datasets")
    def test_genome_download_with_datasets_ok(self, mock_which: object) -> None:
        """When datasets CLI is found, no genome download issue."""
        issues = check_preflight(
            operation="generate",
            generator_backend="builtin",
            needs_genome_download=True,
        )
        datasets_issues = [i for i in issues if "datasets" in i]
        assert datasets_issues == []

    @patch("shutil.which", return_value=None)
    def test_replay_with_genome_download(self, mock_which: object) -> None:
        """Replay mode can still require datasets for the download command."""
        issues = check_preflight(
            operation="copy",
            needs_genome_download=True,
        )
        assert len(issues) >= 1
        assert any("datasets" in msg for msg in issues)
