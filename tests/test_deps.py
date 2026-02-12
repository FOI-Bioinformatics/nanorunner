"""Tests for dependency checking and pre-flight validation."""

import builtins
from unittest.mock import patch

import pytest

from nanopore_simulator.core.deps import (
    INSTALL_HINTS,
    DependencyStatus,
    check_all_dependencies,
    check_preflight,
    get_install_hint,
)


class TestGetInstallHint:
    """Tests for get_install_hint()."""

    def test_known_dependency(self):
        hint = get_install_hint("badread")
        assert "badread" in hint
        assert "conda" in hint

    def test_datasets_hint(self):
        hint = get_install_hint("datasets")
        assert "ncbi-datasets-cli" in hint

    def test_psutil_hint(self):
        hint = get_install_hint("psutil")
        assert "psutil" in hint

    def test_numpy_hint(self):
        hint = get_install_hint("numpy")
        assert "numpy" in hint

    def test_unknown_dependency(self):
        hint = get_install_hint("nonexistent_tool")
        assert "nonexistent_tool" in hint
        assert "manually" in hint.lower()


class TestInstallHints:
    """Tests for the INSTALL_HINTS registry."""

    def test_all_expected_keys_present(self):
        expected = {"badread", "nanosim", "datasets", "psutil", "numpy"}
        assert expected == set(INSTALL_HINTS.keys())

    def test_all_hints_are_strings(self):
        for key, value in INSTALL_HINTS.items():
            assert isinstance(value, str), f"{key} hint is not a string"

    def test_hints_contain_conda(self):
        for key, value in INSTALL_HINTS.items():
            assert "conda" in value, f"{key} hint does not contain conda"


class TestDependencyStatus:
    """Tests for DependencyStatus dataclass."""

    def test_creation(self):
        dep = DependencyStatus(
            name="test",
            available=True,
            category="tool",
            install_hint="pip install test",
            description="Test tool",
            required_for="testing",
        )
        assert dep.name == "test"
        assert dep.available is True
        assert dep.category == "tool"


class TestCheckAllDependencies:
    """Tests for check_all_dependencies()."""

    def test_returns_list_of_dependency_status(self):
        statuses = check_all_dependencies()
        assert isinstance(statuses, list)
        assert all(isinstance(s, DependencyStatus) for s in statuses)

    def test_builtin_always_available(self):
        statuses = check_all_dependencies()
        builtin = [s for s in statuses if s.name == "builtin"]
        assert len(builtin) == 1
        assert builtin[0].available is True

    def test_covers_all_categories(self):
        statuses = check_all_dependencies()
        categories = {s.category for s in statuses}
        assert "generator" in categories
        assert "tool" in categories
        assert "python" in categories

    def test_generator_backends_included(self):
        statuses = check_all_dependencies()
        generator_names = {s.name for s in statuses if s.category == "generator"}
        assert "builtin" in generator_names
        assert "badread" in generator_names
        assert "nanosim" in generator_names

    def test_datasets_tool_included(self):
        statuses = check_all_dependencies()
        tools = {s.name for s in statuses if s.category == "tool"}
        assert "datasets" in tools

    def test_python_packages_included(self):
        statuses = check_all_dependencies()
        python_pkgs = {s.name for s in statuses if s.category == "python"}
        assert "psutil" in python_pkgs
        assert "numpy" in python_pkgs

    def test_unavailable_deps_have_install_hints(self):
        statuses = check_all_dependencies()
        for s in statuses:
            if not s.available:
                assert s.install_hint, f"{s.name} missing install_hint"
                assert len(s.install_hint) > 0


class TestCheckPreflight:
    """Tests for check_preflight()."""

    def test_replay_mode_no_errors(self):
        errors = check_preflight(operation="copy")
        assert errors == []

    def test_link_mode_no_errors(self):
        errors = check_preflight(operation="link")
        assert errors == []

    def test_generate_auto_no_errors(self):
        """auto backend always has builtin fallback."""
        errors = check_preflight(
            operation="generate", generator_backend="auto"
        )
        assert errors == []

    def test_generate_builtin_no_errors(self):
        errors = check_preflight(
            operation="generate", generator_backend="builtin"
        )
        assert errors == []

    def test_generate_badread_missing(self):
        with patch(
            "nanopore_simulator.core.generators.BadreadGenerator.is_available",
            return_value=False,
        ):
            errors = check_preflight(
                operation="generate", generator_backend="badread"
            )
            assert len(errors) == 1
            assert "badread" in errors[0].lower()
            assert "conda" in errors[0].lower()

    def test_generate_badread_available(self):
        with patch(
            "nanopore_simulator.core.generators.BadreadGenerator.is_available",
            return_value=True,
        ):
            errors = check_preflight(
                operation="generate", generator_backend="badread"
            )
            assert errors == []

    def test_generate_nanosim_missing(self):
        with patch(
            "nanopore_simulator.core.generators.NanoSimGenerator.is_available",
            return_value=False,
        ):
            errors = check_preflight(
                operation="generate", generator_backend="nanosim"
            )
            assert len(errors) == 1
            assert "nanosim" in errors[0].lower()

    def test_genome_download_datasets_missing(self):
        with patch("shutil.which", return_value=None):
            errors = check_preflight(
                operation="generate",
                generator_backend="auto",
                needs_genome_download=True,
            )
            assert len(errors) == 1
            assert "datasets" in errors[0].lower()
            assert "ncbi-datasets-cli" in errors[0]

    def test_genome_download_datasets_available(self):
        with patch("shutil.which", return_value="/usr/bin/datasets"):
            errors = check_preflight(
                operation="generate",
                generator_backend="auto",
                needs_genome_download=True,
            )
            assert errors == []

    def test_replay_with_genome_download_missing(self):
        """download command uses replay operation but needs datasets."""
        with patch("shutil.which", return_value=None):
            errors = check_preflight(
                operation="copy",
                needs_genome_download=True,
            )
            assert len(errors) == 1
            assert "datasets" in errors[0].lower()

    def test_multiple_errors(self):
        """Missing backend + missing datasets should produce two errors."""
        with patch(
            "nanopore_simulator.core.generators.BadreadGenerator.is_available",
            return_value=False,
        ):
            with patch("shutil.which", return_value=None):
                errors = check_preflight(
                    operation="generate",
                    generator_backend="badread",
                    needs_genome_download=True,
                )
                assert len(errors) == 2

    def test_no_genome_download_flag_skips_datasets_check(self):
        """When needs_genome_download is False, datasets is not checked."""
        with patch("shutil.which", return_value=None):
            errors = check_preflight(
                operation="generate",
                generator_backend="auto",
                needs_genome_download=False,
            )
            assert errors == []
