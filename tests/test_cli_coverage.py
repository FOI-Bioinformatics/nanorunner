"""Targeted CLI tests to boost coverage for error-handling and edge paths.

Covers the ValueError catch blocks, preflight validation failures,
enhanced monitor psutil fallback, and generate error paths.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from typer.testing import CliRunner

from nanopore_simulator.cli import app, _resolve_monitor, MonitorLevel

runner = CliRunner()


class TestResolveMonitor:
    """Direct tests for the _resolve_monitor helper."""

    def test_quiet_returns_none(self) -> None:
        assert _resolve_monitor(MonitorLevel.default, quiet=True) == "none"

    def test_none_level_returns_none(self) -> None:
        assert _resolve_monitor(MonitorLevel.none, quiet=False) == "none"

    def test_default_returns_basic(self) -> None:
        assert _resolve_monitor(MonitorLevel.default, quiet=False) == "basic"

    def test_default_returns_basic_repeated(self) -> None:
        """Default monitor should resolve to basic."""
        assert _resolve_monitor(MonitorLevel.default, quiet=False) == "basic"

    def test_enhanced_with_psutil_returns_enhanced(self) -> None:
        # psutil is available in test env
        result = _resolve_monitor(MonitorLevel.enhanced, quiet=False)
        assert result == "enhanced"

    def test_enhanced_without_psutil_falls_back(self) -> None:
        """When psutil import fails, enhanced falls back to basic."""
        import sys

        # Temporarily remove psutil from modules
        with patch.dict(sys.modules, {"psutil": None}):
            # Patch the import to raise ImportError
            import builtins

            real_import = builtins.__import__

            def mock_import(name, *args, **kwargs):
                if name == "psutil":
                    raise ImportError("mocked")
                return real_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=mock_import):
                result = _resolve_monitor(MonitorLevel.enhanced, quiet=False)
                assert result == "basic"


class TestReplayErrorPaths:
    """CLI replay error-handling paths."""

    def test_replay_config_validation_error(self, tmp_path: Path) -> None:
        """Config validation error is caught and reported."""
        source = tmp_path / "source"
        source.mkdir()
        (source / "r.fastq").write_text("@r1\nACGT\n+\nIIII\n")
        result = runner.invoke(
            app,
            [
                "replay",
                "--source",
                str(source),
                "--target",
                str(tmp_path / "target"),
                "--batch-size",
                "0",  # Invalid
                "--interval",
                "0",
            ],
        )
        assert result.exit_code != 0

    def test_replay_negative_interval(self, tmp_path: Path) -> None:
        """Negative interval is caught as config validation error."""
        source = tmp_path / "source"
        source.mkdir()
        (source / "r.fastq").write_text("@r1\nACGT\n+\nIIII\n")
        result = runner.invoke(
            app,
            [
                "replay",
                "--source",
                str(source),
                "--target",
                str(tmp_path / "target"),
                "--interval",
                "-1",
            ],
        )
        assert result.exit_code != 0

    def test_replay_with_pipeline_validation_post_run(self, tmp_path: Path) -> None:
        """Pipeline validation runs after replay and includes adapter name."""
        source = tmp_path / "source"
        source.mkdir()
        (source / "r.fastq").write_text("@r1\nACGT\n+\nIIII\n")
        result = runner.invoke(
            app,
            [
                "replay",
                "--source",
                str(source),
                "--target",
                str(tmp_path / "target"),
                "--pipeline",
                "kraken",
                "--interval",
                "0",
            ],
        )
        assert result.exit_code == 0
        assert "kraken" in result.output.lower()


class TestGenerateErrorPaths:
    """CLI generate error-handling paths."""

    def test_generate_config_validation_catches_value_error(
        self, tmp_path: Path
    ) -> None:
        """ValueError from GenerateConfig is caught."""
        fasta = tmp_path / "g.fa"
        fasta.write_text(">c\nACGT\n")
        result = runner.invoke(
            app,
            [
                "generate",
                "--target",
                str(tmp_path / "target"),
                "--genomes",
                str(fasta),
                "--batch-size",
                "0",  # Invalid
                "--no-wait",
            ],
        )
        assert result.exit_code != 0

    def test_generate_with_pipeline_validation(self, tmp_path: Path) -> None:
        """Pipeline validation runs after generate mode."""
        fasta = tmp_path / "g.fa"
        fasta.write_text(">chr1\nACGTACGTACGTACGT\n")
        result = runner.invoke(
            app,
            [
                "generate",
                "--target",
                str(tmp_path / "target"),
                "--genomes",
                str(fasta),
                "--generator-backend",
                "builtin",
                "--read-count",
                "10",
                "--reads-per-file",
                "10",
                "--output-format",
                "fastq",
                "--pipeline",
                "nanometa",
                "--no-wait",
            ],
        )
        assert result.exit_code == 0
        assert "nanometa" in result.output.lower()

    def test_generate_runtime_error_caught(self, tmp_path: Path) -> None:
        """Runtime errors from run_generate are caught and reported."""
        fasta = tmp_path / "g.fa"
        fasta.write_text(">chr1\nACGTACGTACGTACGT\n")
        with patch(
            "nanopore_simulator.cli.run_generate",
            side_effect=RuntimeError("test error"),
        ):
            result = runner.invoke(
                app,
                [
                    "generate",
                    "--target",
                    str(tmp_path / "target"),
                    "--genomes",
                    str(fasta),
                    "--no-wait",
                    "--quiet",
                ],
            )
            assert result.exit_code != 0

    def test_replay_runtime_error_caught(self, tmp_path: Path) -> None:
        """Runtime errors from run_replay are caught and reported."""
        source = tmp_path / "source"
        source.mkdir()
        (source / "r.fastq").write_text("@r1\nACGT\n+\nIIII\n")
        with patch(
            "nanopore_simulator.cli.run_replay",
            side_effect=RuntimeError("test error"),
        ):
            result = runner.invoke(
                app,
                [
                    "replay",
                    "--source",
                    str(source),
                    "--target",
                    str(tmp_path / "target"),
                    "--interval",
                    "0",
                    "--quiet",
                ],
            )
            assert result.exit_code != 0


class TestDownloadCommand:
    """Test download command error paths (no network)."""

    def test_download_mock_preflight_fails(self) -> None:
        """Download with missing datasets CLI reports preflight error."""
        with patch(
            "nanopore_simulator.deps.check_preflight",
            return_value=["datasets CLI not found"],
        ):
            result = runner.invoke(
                app,
                ["download", "--mock", "zymo_d6300"],
            )
            assert result.exit_code != 0

    def test_download_species_preflight_fails(self) -> None:
        """Download with missing datasets CLI reports preflight error."""
        with patch(
            "nanopore_simulator.deps.check_preflight",
            return_value=["datasets CLI not found"],
        ):
            result = runner.invoke(
                app,
                ["download", "--species", "Escherichia coli"],
            )
            assert result.exit_code != 0

    def test_download_taxid_preflight_fails(self) -> None:
        """Download with missing datasets CLI reports preflight error."""
        with patch(
            "nanopore_simulator.deps.check_preflight",
            return_value=["datasets CLI not found"],
        ):
            result = runner.invoke(
                app,
                ["download", "--taxid", "562"],
            )
            assert result.exit_code != 0

    def test_download_unknown_mock(self) -> None:
        """Download with an unknown mock name fails."""
        with patch("nanopore_simulator.deps.check_preflight", return_value=[]):
            result = runner.invoke(
                app,
                ["download", "--mock", "nonexistent_mock"],
            )
            assert result.exit_code != 0

    def test_download_mock_successful_download(self) -> None:
        """Download mock with successful genome download."""
        mock_ref = MagicMock()
        mock_ref.name = "E. coli"
        mock_ref.accession = "GCF_000005845.2"
        mock_ref.source = "ncbi"
        mock_ref.domain = "bacteria"

        with patch("nanopore_simulator.deps.check_preflight", return_value=[]):
            with patch(
                "nanopore_simulator.species.download_genome",
                return_value=Path("/tmp/fake_genome.fa"),
            ):
                result = runner.invoke(
                    app,
                    ["download", "--mock", "quick_single"],
                )
                assert result.exit_code == 0
                assert "Download" in result.output

    def test_download_species_resolve_fails(self) -> None:
        """Download species that fails to resolve."""
        with patch("nanopore_simulator.deps.check_preflight", return_value=[]):
            with patch(
                "nanopore_simulator.species.resolve_species",
                return_value=None,
            ):
                result = runner.invoke(
                    app,
                    ["download", "--species", "Nonexistent species"],
                )
                assert result.exit_code != 0

    def test_download_taxid_resolve_fails(self) -> None:
        """Download taxid that fails to resolve."""
        with patch("nanopore_simulator.deps.check_preflight", return_value=[]):
            with patch(
                "nanopore_simulator.species.resolve_taxid",
                return_value=None,
            ):
                result = runner.invoke(
                    app,
                    ["download", "--taxid", "999999999"],
                )
                assert result.exit_code != 0


class TestRecommendWithSource:
    """Test recommend command with source directory analysis."""

    def test_recommend_source_with_barcode_subdirs(self, tmp_path: Path) -> None:
        """Recommend with multiplex source finds files in subdirs."""
        source = tmp_path / "source"
        source.mkdir()
        bc = source / "barcode01"
        bc.mkdir()
        (bc / "r.fastq").write_text("@r1\nACGT\n+\nIIII\n")
        result = runner.invoke(
            app,
            ["recommend", "--source", str(source)],
        )
        assert result.exit_code == 0
        assert "Recommended profiles" in result.output

    def test_recommend_invalid_source_path(self, tmp_path: Path) -> None:
        """Recommend with a file (not directory) fails."""
        fpath = tmp_path / "file.txt"
        fpath.write_text("not a dir")
        result = runner.invoke(
            app,
            ["recommend", "--source", str(fpath)],
        )
        assert result.exit_code != 0


class TestCliMainEntryPoint:
    """Test the main() entry point function."""

    def test_main_returns_zero_on_success(self) -> None:
        from nanopore_simulator.cli import main

        with patch("nanopore_simulator.cli.app") as mock_app:
            mock_app.return_value = None
            code = main()
            assert code == 0

    def test_main_returns_exit_code_on_system_exit(self) -> None:
        from nanopore_simulator.cli import main

        with patch("nanopore_simulator.cli.app", side_effect=SystemExit(1)):
            code = main()
            assert code == 1
