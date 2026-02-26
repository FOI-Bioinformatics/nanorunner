"""Tests for the v2 CLI thin dispatcher.

Uses typer.testing.CliRunner to exercise all subcommands and verify
that the external interface contract is preserved.
"""

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from nanopore_simulator.cli import app

runner = CliRunner()


# -------------------------------------------------------------------
# Help text tests
# -------------------------------------------------------------------


class TestReplayHelp:
    """Verify replay subcommand help text contains expected flags."""

    def test_replay_help_exits_zero(self):
        result = runner.invoke(app, ["replay", "--help"])
        assert result.exit_code == 0

    def test_replay_help_contains_source(self):
        result = runner.invoke(app, ["replay", "--help"])
        assert "--source" in result.output

    def test_replay_help_contains_target(self):
        result = runner.invoke(app, ["replay", "--help"])
        assert "--target" in result.output

    def test_replay_help_contains_interval(self):
        result = runner.invoke(app, ["replay", "--help"])
        assert "--interval" in result.output

    def test_replay_help_contains_operation(self):
        result = runner.invoke(app, ["replay", "--help"])
        assert "--operation" in result.output

    def test_replay_help_contains_timing_model(self):
        result = runner.invoke(app, ["replay", "--help"])
        assert "--timing-model" in result.output

    def test_replay_help_contains_profile(self):
        result = runner.invoke(app, ["replay", "--help"])
        assert "--profile" in result.output

    def test_replay_help_contains_parallel(self):
        result = runner.invoke(app, ["replay", "--help"])
        assert "--parallel" in result.output

    def test_replay_help_contains_monitor(self):
        result = runner.invoke(app, ["replay", "--help"])
        assert "--monitor" in result.output

    def test_replay_help_contains_reads_per_file(self):
        result = runner.invoke(app, ["replay", "--help"])
        assert "--reads-per-file" in result.output

    def test_replay_help_contains_no_wait(self):
        result = runner.invoke(app, ["replay", "--help"])
        assert "--no-wait" in result.output

    def test_replay_help_contains_burst_probability(self):
        result = runner.invoke(app, ["replay", "--help"])
        assert "--burst-probability" in result.output

    def test_replay_help_contains_random_factor(self):
        result = runner.invoke(app, ["replay", "--help"])
        assert "--random-factor" in result.output

    def test_replay_help_contains_adaptation_rate(self):
        result = runner.invoke(app, ["replay", "--help"])
        assert "--adaptation-rate" in result.output

    def test_replay_help_contains_quiet(self):
        result = runner.invoke(app, ["replay", "--help"])
        assert "--quiet" in result.output


class TestGenerateHelp:
    """Verify generate subcommand help text contains expected flags."""

    def test_generate_help_exits_zero(self):
        result = runner.invoke(app, ["generate", "--help"])
        assert result.exit_code == 0

    def test_generate_help_contains_target(self):
        result = runner.invoke(app, ["generate", "--help"])
        assert "--target" in result.output

    def test_generate_help_contains_genomes(self):
        result = runner.invoke(app, ["generate", "--help"])
        assert "--genomes" in result.output

    def test_generate_help_contains_species(self):
        result = runner.invoke(app, ["generate", "--help"])
        assert "--species" in result.output

    def test_generate_help_contains_mock(self):
        result = runner.invoke(app, ["generate", "--help"])
        assert "--mock" in result.output

    def test_generate_help_contains_taxid(self):
        result = runner.invoke(app, ["generate", "--help"])
        assert "--taxid" in result.output

    def test_generate_help_contains_read_count(self):
        result = runner.invoke(app, ["generate", "--help"])
        assert "--read-count" in result.output

    def test_generate_help_contains_generator_backend(self):
        result = runner.invoke(app, ["generate", "--help"])
        # Rich help may truncate long option names with ellipsis
        assert "generator-backe" in result.output

    def test_generate_help_contains_mean_read_length(self):
        result = runner.invoke(app, ["generate", "--help"])
        assert "--mean-read-length" in result.output

    def test_generate_help_contains_mean_quality(self):
        result = runner.invoke(app, ["generate", "--help"])
        assert "--mean-quality" in result.output

    def test_generate_help_contains_reads_per_file(self):
        result = runner.invoke(app, ["generate", "--help"])
        assert "--reads-per-file" in result.output

    def test_generate_help_contains_output_format(self):
        result = runner.invoke(app, ["generate", "--help"])
        assert "--output-format" in result.output

    def test_generate_help_contains_mix_reads(self):
        result = runner.invoke(app, ["generate", "--help"])
        assert "--mix-reads" in result.output

    def test_generate_help_contains_offline(self):
        result = runner.invoke(app, ["generate", "--help"])
        assert "--offline" in result.output

    def test_generate_help_contains_sample_type(self):
        result = runner.invoke(app, ["generate", "--help"])
        assert "--sample-type" in result.output

    def test_generate_help_contains_abundances(self):
        result = runner.invoke(app, ["generate", "--help"])
        assert "--abundances" in result.output


class TestDownloadHelp:
    """Verify download subcommand help text."""

    def test_download_help_exits_zero(self):
        result = runner.invoke(app, ["download", "--help"])
        assert result.exit_code == 0

    def test_download_help_contains_species(self):
        result = runner.invoke(app, ["download", "--help"])
        assert "--species" in result.output

    def test_download_help_contains_mock(self):
        result = runner.invoke(app, ["download", "--help"])
        assert "--mock" in result.output

    def test_download_help_contains_taxid(self):
        result = runner.invoke(app, ["download", "--help"])
        assert "--taxid" in result.output

    def test_download_help_contains_target(self):
        result = runner.invoke(app, ["download", "--help"])
        assert "--target" in result.output


# -------------------------------------------------------------------
# Replay functional tests
# -------------------------------------------------------------------


class TestReplayBasic:
    """Verify replay command runs end-to-end."""

    def test_replay_copies_files(self, source_dir_singleplex, tmp_path):
        target = tmp_path / "output"
        result = runner.invoke(app, [
            "replay",
            "--source", str(source_dir_singleplex),
            "--target", str(target),
            "--interval", "0",
        ])
        assert result.exit_code == 0
        assert target.exists()
        # Source has 5 files, verify they were copied
        output_files = list(target.glob("*.fastq"))
        assert len(output_files) == 5

    def test_replay_with_profile(self, source_dir_singleplex, tmp_path):
        target = tmp_path / "output"
        result = runner.invoke(app, [
            "replay",
            "--source", str(source_dir_singleplex),
            "--target", str(target),
            "--interval", "0",
            "--profile", "development",
        ])
        assert result.exit_code == 0
        assert target.exists()

    def test_replay_with_timing_model(self, source_dir_singleplex, tmp_path):
        target = tmp_path / "output"
        result = runner.invoke(app, [
            "replay",
            "--source", str(source_dir_singleplex),
            "--target", str(target),
            "--interval", "0",
            "--timing-model", "random",
        ])
        assert result.exit_code == 0

    def test_replay_link_operation(self, source_dir_singleplex, tmp_path):
        target = tmp_path / "output"
        result = runner.invoke(app, [
            "replay",
            "--source", str(source_dir_singleplex),
            "--target", str(target),
            "--interval", "0",
            "--operation", "link",
        ])
        assert result.exit_code == 0
        output_files = list(target.glob("*.fastq"))
        assert len(output_files) == 5
        # Verify they are symlinks
        for f in output_files:
            assert f.is_symlink()

    def test_replay_multiplex(self, source_dir_multiplex, tmp_path):
        target = tmp_path / "output"
        result = runner.invoke(app, [
            "replay",
            "--source", str(source_dir_multiplex),
            "--target", str(target),
            "--interval", "0",
        ])
        assert result.exit_code == 0
        assert (target / "barcode01").exists()
        assert (target / "barcode02").exists()

    def test_replay_no_wait(self, source_dir_singleplex, tmp_path):
        target = tmp_path / "output"
        result = runner.invoke(app, [
            "replay",
            "--source", str(source_dir_singleplex),
            "--target", str(target),
            "--no-wait",
        ])
        assert result.exit_code == 0

    def test_replay_quiet(self, source_dir_singleplex, tmp_path):
        target = tmp_path / "output"
        result = runner.invoke(app, [
            "replay",
            "--source", str(source_dir_singleplex),
            "--target", str(target),
            "--interval", "0",
            "--quiet",
        ])
        assert result.exit_code == 0

    def test_replay_parallel(self, source_dir_singleplex, tmp_path):
        target = tmp_path / "output"
        result = runner.invoke(app, [
            "replay",
            "--source", str(source_dir_singleplex),
            "--target", str(target),
            "--interval", "0",
            "--parallel",
            "--worker-count", "2",
        ])
        assert result.exit_code == 0
        output_files = list(target.glob("*.fastq"))
        assert len(output_files) == 5


class TestReplayValidation:
    """Verify replay validation catches errors."""

    def test_replay_rejects_reads_per_file_with_link(
        self, source_dir_singleplex, tmp_path
    ):
        target = tmp_path / "output"
        result = runner.invoke(app, [
            "replay",
            "--source", str(source_dir_singleplex),
            "--target", str(target),
            "--interval", "0",
            "--operation", "link",
            "--reads-per-file", "10",
        ])
        assert result.exit_code == 2

    def test_replay_invalid_profile(self, source_dir_singleplex, tmp_path):
        target = tmp_path / "output"
        result = runner.invoke(app, [
            "replay",
            "--source", str(source_dir_singleplex),
            "--target", str(target),
            "--interval", "0",
            "--profile", "nonexistent_profile",
        ])
        assert result.exit_code == 2

    def test_replay_invalid_random_factor(
        self, source_dir_singleplex, tmp_path
    ):
        target = tmp_path / "output"
        result = runner.invoke(app, [
            "replay",
            "--source", str(source_dir_singleplex),
            "--target", str(target),
            "--interval", "0",
            "--random-factor", "2.0",
        ])
        assert result.exit_code == 2

    def test_replay_invalid_burst_probability(
        self, source_dir_singleplex, tmp_path
    ):
        target = tmp_path / "output"
        result = runner.invoke(app, [
            "replay",
            "--source", str(source_dir_singleplex),
            "--target", str(target),
            "--interval", "0",
            "--burst-probability", "1.5",
        ])
        assert result.exit_code == 2

    def test_replay_invalid_adaptation_rate(
        self, source_dir_singleplex, tmp_path
    ):
        target = tmp_path / "output"
        result = runner.invoke(app, [
            "replay",
            "--source", str(source_dir_singleplex),
            "--target", str(target),
            "--interval", "0",
            "--adaptation-rate", "-0.1",
        ])
        assert result.exit_code == 2

    def test_replay_invalid_history_size(
        self, source_dir_singleplex, tmp_path
    ):
        target = tmp_path / "output"
        result = runner.invoke(app, [
            "replay",
            "--source", str(source_dir_singleplex),
            "--target", str(target),
            "--interval", "0",
            "--history-size", "0",
        ])
        assert result.exit_code == 2

    def test_replay_invalid_burst_rate_multiplier(
        self, source_dir_singleplex, tmp_path
    ):
        target = tmp_path / "output"
        result = runner.invoke(app, [
            "replay",
            "--source", str(source_dir_singleplex),
            "--target", str(target),
            "--interval", "0",
            "--burst-rate-multiplier", "-1",
        ])
        assert result.exit_code == 2


# -------------------------------------------------------------------
# Generate functional tests
# -------------------------------------------------------------------


class TestGenerateBasic:
    """Verify generate command runs end-to-end."""

    def test_generate_with_genome(self, sample_fasta, tmp_path):
        target = tmp_path / "gen_output"
        result = runner.invoke(app, [
            "generate",
            "--target", str(target),
            "--genomes", str(sample_fasta),
            "--read-count", "10",
            "--interval", "0",
            "--generator-backend", "builtin",
        ])
        assert result.exit_code == 0
        assert target.exists()

    def test_generate_with_two_genomes(self, tmp_path):
        g1 = tmp_path / "genome1.fa"
        g2 = tmp_path / "genome2.fa"
        g1.write_text(">chr1\nACGTACGTACGTACGT\n")
        g2.write_text(">chr1\nTTTTAAAACCCCGGGG\n")
        target = tmp_path / "gen_output"
        result = runner.invoke(app, [
            "generate",
            "--target", str(target),
            "--genomes", str(g1),
            "--genomes", str(g2),
            "--read-count", "10",
            "--interval", "0",
            "--generator-backend", "builtin",
        ])
        assert result.exit_code == 0

    def test_generate_requires_genome_source(self, tmp_path):
        target = tmp_path / "gen_output"
        result = runner.invoke(app, [
            "generate",
            "--target", str(target),
            "--read-count", "10",
        ])
        assert result.exit_code == 1
        assert "specify one of" in result.output.lower() or "error" in result.output.lower()

    def test_generate_mutual_exclusivity(self, sample_fasta, tmp_path):
        target = tmp_path / "gen_output"
        result = runner.invoke(app, [
            "generate",
            "--target", str(target),
            "--genomes", str(sample_fasta),
            "--species", "Escherichia coli",
        ])
        assert result.exit_code == 1

    def test_generate_directory_expansion(self, tmp_path):
        genome_dir = tmp_path / "genomes"
        genome_dir.mkdir()
        (genome_dir / "genome1.fa").write_text(">chr1\nACGTACGTACGTACGT\n")
        (genome_dir / "genome2.fa").write_text(">chr1\nTTTTAAAACCCCGGGG\n")
        target = tmp_path / "gen_output"
        result = runner.invoke(app, [
            "generate",
            "--target", str(target),
            "--genomes", str(genome_dir),
            "--read-count", "10",
            "--interval", "0",
            "--generator-backend", "builtin",
        ])
        assert result.exit_code == 0
        assert "Expanded directory" in result.output

    def test_generate_empty_directory_fails(self, tmp_path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        target = tmp_path / "gen_output"
        result = runner.invoke(app, [
            "generate",
            "--target", str(target),
            "--genomes", str(empty_dir),
            "--read-count", "10",
        ])
        assert result.exit_code == 2

    def test_generate_nonexistent_genome_fails(self, tmp_path):
        target = tmp_path / "gen_output"
        result = runner.invoke(app, [
            "generate",
            "--target", str(target),
            "--genomes", str(tmp_path / "nonexistent.fa"),
            "--read-count", "10",
        ])
        assert result.exit_code == 2

    def test_generate_with_profile(self, sample_fasta, tmp_path):
        target = tmp_path / "gen_output"
        result = runner.invoke(app, [
            "generate",
            "--target", str(target),
            "--genomes", str(sample_fasta),
            "--read-count", "10",
            "--interval", "0",
            "--generator-backend", "builtin",
            "--profile", "generate_test",
        ])
        assert result.exit_code == 0

    def test_generate_no_wait(self, sample_fasta, tmp_path):
        target = tmp_path / "gen_output"
        result = runner.invoke(app, [
            "generate",
            "--target", str(target),
            "--genomes", str(sample_fasta),
            "--read-count", "10",
            "--no-wait",
            "--generator-backend", "builtin",
        ])
        assert result.exit_code == 0

    def test_generate_quiet(self, sample_fasta, tmp_path):
        target = tmp_path / "gen_output"
        result = runner.invoke(app, [
            "generate",
            "--target", str(target),
            "--genomes", str(sample_fasta),
            "--read-count", "10",
            "--interval", "0",
            "--generator-backend", "builtin",
            "--quiet",
        ])
        assert result.exit_code == 0


# -------------------------------------------------------------------
# List commands
# -------------------------------------------------------------------


class TestListProfiles:
    """Verify list-profiles subcommand."""

    def test_exits_zero(self):
        result = runner.invoke(app, ["list-profiles"])
        assert result.exit_code == 0

    def test_contains_development(self):
        result = runner.invoke(app, ["list-profiles"])
        assert "development" in result.output

    def test_contains_bursty(self):
        result = runner.invoke(app, ["list-profiles"])
        assert "bursty" in result.output

    def test_contains_generate_test(self):
        result = runner.invoke(app, ["list-profiles"])
        assert "generate_test" in result.output


class TestListAdapters:
    """Verify list-adapters subcommand."""

    def test_exits_zero(self):
        result = runner.invoke(app, ["list-adapters"])
        assert result.exit_code == 0

    def test_contains_nanometa(self):
        result = runner.invoke(app, ["list-adapters"])
        assert "nanometa" in result.output

    def test_contains_kraken(self):
        result = runner.invoke(app, ["list-adapters"])
        assert "kraken" in result.output


class TestListGenerators:
    """Verify list-generators subcommand."""

    def test_exits_zero(self):
        result = runner.invoke(app, ["list-generators"])
        assert result.exit_code == 0

    def test_contains_builtin(self):
        result = runner.invoke(app, ["list-generators"])
        assert "builtin" in result.output

    def test_contains_badread(self):
        result = runner.invoke(app, ["list-generators"])
        assert "badread" in result.output


class TestListMocks:
    """Verify list-mocks subcommand."""

    def test_exits_zero(self):
        result = runner.invoke(app, ["list-mocks"])
        assert result.exit_code == 0

    def test_contains_zymo(self):
        result = runner.invoke(app, ["list-mocks"])
        assert "zymo" in result.output

    def test_contains_eskape(self):
        result = runner.invoke(app, ["list-mocks"])
        assert "eskape" in result.output

    def test_contains_aliases(self):
        result = runner.invoke(app, ["list-mocks"])
        assert "Aliases:" in result.output


# -------------------------------------------------------------------
# Check-deps
# -------------------------------------------------------------------


class TestCheckDeps:
    """Verify check-deps subcommand."""

    def test_exits_zero(self):
        result = runner.invoke(app, ["check-deps"])
        assert result.exit_code == 0

    def test_contains_builtin_available(self):
        result = runner.invoke(app, ["check-deps"])
        assert "builtin" in result.output
        assert "available" in result.output

    def test_contains_section_headers(self):
        result = runner.invoke(app, ["check-deps"])
        assert "Read Generation Backends:" in result.output


# -------------------------------------------------------------------
# Recommend
# -------------------------------------------------------------------


class TestRecommend:
    """Verify recommend subcommand."""

    def test_recommend_with_file_count(self):
        result = runner.invoke(app, ["recommend", "--file-count", "100"])
        assert result.exit_code == 0
        assert "Recommended" in result.output

    def test_recommend_with_source(self, source_dir_singleplex):
        result = runner.invoke(app, [
            "recommend", "--source", str(source_dir_singleplex),
        ])
        assert result.exit_code == 0
        assert "Recommended" in result.output

    def test_recommend_no_args_shows_profiles(self):
        result = runner.invoke(app, ["recommend"])
        assert result.exit_code == 0
        assert "Available" in result.output

    def test_recommend_nonexistent_source(self, tmp_path):
        result = runner.invoke(app, [
            "recommend", "--source", str(tmp_path / "nonexistent"),
        ])
        assert result.exit_code == 1

    def test_recommend_small_file_count(self):
        result = runner.invoke(app, ["recommend", "--file-count", "10"])
        assert result.exit_code == 0
        # Should recommend steady/bursty for small counts
        assert any(p in result.output for p in ["steady", "bursty"])

    def test_recommend_large_file_count(self):
        result = runner.invoke(app, ["recommend", "--file-count", "5000"])
        assert result.exit_code == 0
        assert "high_throughput" in result.output


# -------------------------------------------------------------------
# Validate
# -------------------------------------------------------------------


class TestValidate:
    """Verify validate subcommand."""

    def test_validate_with_matching_files(self, tmp_path):
        target = tmp_path / "valid"
        target.mkdir()
        (target / "reads.fastq").write_text("@read1\nACGT\n+\nIIII\n")
        result = runner.invoke(app, [
            "validate",
            "--pipeline", "nanometa",
            "--target", str(target),
        ])
        assert result.exit_code == 0
        assert "Valid: yes" in result.output

    def test_validate_empty_directory_fails(self, tmp_path):
        target = tmp_path / "empty"
        target.mkdir()
        result = runner.invoke(app, [
            "validate",
            "--pipeline", "nanometa",
            "--target", str(target),
        ])
        assert result.exit_code == 1
        assert "Valid: no" in result.output

    def test_validate_unknown_adapter(self, tmp_path):
        target = tmp_path / "valid"
        target.mkdir()
        result = runner.invoke(app, [
            "validate",
            "--pipeline", "nonexistent",
            "--target", str(target),
        ])
        # Should fail with KeyError from the adapter module
        assert result.exit_code != 0


# -------------------------------------------------------------------
# Download command (requires mocking external tools)
# -------------------------------------------------------------------


class TestDownload:
    """Verify download subcommand error handling."""

    def test_download_requires_source(self):
        result = runner.invoke(app, ["download"])
        assert result.exit_code == 1

    def test_download_help_exits_zero(self):
        result = runner.invoke(app, ["download", "--help"])
        assert result.exit_code == 0


# -------------------------------------------------------------------
# Version flag
# -------------------------------------------------------------------


class TestVersionFlag:
    """Verify --version output."""

    def test_version_flag(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "nanorunner" in result.output
        assert "3.0.0" in result.output


# -------------------------------------------------------------------
# No args behavior
# -------------------------------------------------------------------


class TestNoArgs:
    """Verify app shows help when invoked without arguments."""

    def test_no_args_shows_help(self):
        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "Usage" in result.output or "replay" in result.output


# -------------------------------------------------------------------
# Monitor level resolution
# -------------------------------------------------------------------


class TestMonitorLevelResolution:
    """Verify the _resolve_monitor helper function."""

    def test_quiet_returns_none(self):
        from nanopore_simulator.cli import _resolve_monitor, MonitorLevel
        assert _resolve_monitor(MonitorLevel.default, True) == "none"

    def test_none_returns_none(self):
        from nanopore_simulator.cli import _resolve_monitor, MonitorLevel
        assert _resolve_monitor(MonitorLevel.none, False) == "none"

    def test_default_returns_basic(self):
        from nanopore_simulator.cli import _resolve_monitor, MonitorLevel
        assert _resolve_monitor(MonitorLevel.default, False) == "basic"

    def test_detailed_returns_basic(self):
        from nanopore_simulator.cli import _resolve_monitor, MonitorLevel
        assert _resolve_monitor(MonitorLevel.detailed, False) == "basic"


# -------------------------------------------------------------------
# Timing params builder
# -------------------------------------------------------------------


class TestBuildTimingParams:
    """Verify _build_timing_params helper."""

    def test_all_none_returns_empty(self):
        from nanopore_simulator.cli import _build_timing_params
        result = _build_timing_params(None, None, None, None, None)
        assert result == {}

    def test_collects_provided_values(self):
        from nanopore_simulator.cli import _build_timing_params
        result = _build_timing_params(0.1, 3.0, 0.5, 0.2, 10)
        assert result == {
            "burst_probability": 0.1,
            "burst_rate_multiplier": 3.0,
            "random_factor": 0.5,
            "adaptation_rate": 0.2,
            "history_size": 10,
        }

    def test_partial_values(self):
        from nanopore_simulator.cli import _build_timing_params
        result = _build_timing_params(None, None, 0.3, None, None)
        assert result == {"random_factor": 0.3}


# -------------------------------------------------------------------
# Integration: replay with timing sub-params
# -------------------------------------------------------------------


class TestReplayTimingParams:
    """Verify timing sub-params are passed through to config."""

    def test_replay_with_random_factor(self, source_dir_singleplex, tmp_path):
        target = tmp_path / "output"
        result = runner.invoke(app, [
            "replay",
            "--source", str(source_dir_singleplex),
            "--target", str(target),
            "--interval", "0",
            "--timing-model", "random",
            "--random-factor", "0.3",
        ])
        assert result.exit_code == 0

    def test_replay_with_poisson_params(self, source_dir_singleplex, tmp_path):
        target = tmp_path / "output"
        result = runner.invoke(app, [
            "replay",
            "--source", str(source_dir_singleplex),
            "--target", str(target),
            "--interval", "0",
            "--timing-model", "poisson",
            "--burst-probability", "0.1",
            "--burst-rate-multiplier", "5.0",
        ])
        assert result.exit_code == 0

    def test_replay_with_adaptive_params(
        self, source_dir_singleplex, tmp_path
    ):
        target = tmp_path / "output"
        result = runner.invoke(app, [
            "replay",
            "--source", str(source_dir_singleplex),
            "--target", str(target),
            "--interval", "0",
            "--timing-model", "adaptive",
            "--adaptation-rate", "0.2",
            "--history-size", "10",
        ])
        assert result.exit_code == 0


# -------------------------------------------------------------------
# Edge cases
# -------------------------------------------------------------------


class TestEdgeCases:
    """Verify edge cases and error handling."""

    def test_replay_batch_size_override(
        self, source_dir_singleplex, tmp_path
    ):
        target = tmp_path / "output"
        result = runner.invoke(app, [
            "replay",
            "--source", str(source_dir_singleplex),
            "--target", str(target),
            "--interval", "0",
            "--batch-size", "3",
        ])
        assert result.exit_code == 0
        output_files = list(target.glob("*.fastq"))
        assert len(output_files) == 5

    def test_generate_with_force_structure_multiplex(
        self, sample_fasta, tmp_path
    ):
        target = tmp_path / "gen_output"
        result = runner.invoke(app, [
            "generate",
            "--target", str(target),
            "--genomes", str(sample_fasta),
            "--read-count", "10",
            "--interval", "0",
            "--generator-backend", "builtin",
            "--force-structure", "multiplex",
        ])
        assert result.exit_code == 0
        # Should have barcode directories
        barcode_dirs = [d for d in target.iterdir() if d.is_dir()]
        assert len(barcode_dirs) >= 1

    def test_generate_output_format_fastq(self, sample_fasta, tmp_path):
        target = tmp_path / "gen_output"
        result = runner.invoke(app, [
            "generate",
            "--target", str(target),
            "--genomes", str(sample_fasta),
            "--read-count", "10",
            "--interval", "0",
            "--generator-backend", "builtin",
            "--output-format", "fastq",
        ])
        assert result.exit_code == 0
        # Check for uncompressed fastq files
        output_files = list(target.rglob("*.fastq"))
        gz_files = list(target.rglob("*.fastq.gz"))
        assert len(output_files) > 0
        assert len(gz_files) == 0
