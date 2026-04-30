"""Additional tests to boost code coverage above 90%.

Targets uncovered paths in executor (rechunk, mixed generate), CLI
(edge cases, psutil fallback, download validation), deps (fallback
paths), and monitoring (display callback, format helpers).
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from nanopore_simulator.cli import app
from nanopore_simulator.executor import execute_entry
from nanopore_simulator.generators import (
    BuiltinGenerator,
    GeneratorConfig,
    GenomeInput,
)
from nanopore_simulator.manifest import FileEntry
from nanopore_simulator.monitoring import (
    NullMonitor,
    ProgressMonitor,
    SimulationMetrics,
    create_monitor,
    format_bytes,
    format_time,
)

runner = CliRunner()


# -------------------------------------------------------------------
# Executor: rechunk operation
# -------------------------------------------------------------------


class TestRechunkExecution:
    """Tests for the rechunk operation in the executor."""

    def test_rechunk_writes_correct_reads(self, tmp_path: Path) -> None:
        """Rechunk writes the specified number of reads to target."""
        source = tmp_path / "source.fastq"
        content = ""
        for i in range(10):
            content += f"@read{i}\nACGTACGT\n+\nIIIIIIII\n"
        source.write_text(content)

        target = tmp_path / "target" / "chunk_0000.fastq"
        entry = FileEntry(
            target=target,
            operation="rechunk",
            read_count=3,
            file_index=0,
            source_files=[source],
        )
        result = execute_entry(entry)
        assert result == target
        assert target.exists()
        lines = target.read_text().strip().split("\n")
        assert len(lines) == 12  # 3 reads * 4 lines

    def test_rechunk_second_chunk(self, tmp_path: Path) -> None:
        """File index 1 skips the first chunk of reads."""
        source = tmp_path / "source.fastq"
        content = ""
        for i in range(10):
            content += f"@read{i}\nACGTACGT\n+\nIIIIIIII\n"
        source.write_text(content)

        target = tmp_path / "target" / "chunk_0001.fastq"
        entry = FileEntry(
            target=target,
            operation="rechunk",
            read_count=3,
            file_index=1,
            source_files=[source],
        )
        result = execute_entry(entry)
        assert result.exists()
        text = target.read_text()
        # Second chunk should start with @read3 (skipping 0,1,2)
        assert "@read3" in text

    def test_rechunk_without_source_files_raises(self, tmp_path: Path) -> None:
        """Rechunk without source_files raises ValueError."""
        entry = FileEntry(
            target=tmp_path / "output.fastq",
            operation="rechunk",
            read_count=5,
            file_index=0,
            source_files=None,
        )
        with pytest.raises(ValueError, match="source_files"):
            execute_entry(entry)

    def test_rechunk_multiple_sources(self, tmp_path: Path) -> None:
        """Rechunk reads across multiple source files."""
        src1 = tmp_path / "src1.fastq"
        src2 = tmp_path / "src2.fastq"
        src1.write_text("@r0\nACGT\n+\nIIII\n@r1\nACGT\n+\nIIII\n")
        src2.write_text("@r2\nACGT\n+\nIIII\n@r3\nACGT\n+\nIIII\n")

        target = tmp_path / "target" / "chunk.fastq"
        entry = FileEntry(
            target=target,
            operation="rechunk",
            read_count=3,
            file_index=0,
            source_files=[src1, src2],
        )
        result = execute_entry(entry)
        text = result.read_text()
        assert "@r0" in text
        assert "@r1" in text
        assert "@r2" in text


# -------------------------------------------------------------------
# Executor: mixed generate operation
# -------------------------------------------------------------------


class TestMixedGenerateExecution:
    """Tests for mixed-genome generate execution."""

    def test_mixed_generate_produces_combined_output(self, tmp_path: Path) -> None:
        """Mixed generate combines reads from multiple genomes."""
        genome_a = tmp_path / "a.fa"
        genome_b = tmp_path / "b.fa"
        genome_a.write_text(">chr1\nACGTACGTACGTACGT\n")
        genome_b.write_text(">chr1\nTTTTAAAACCCCGGGG\n")

        config = GeneratorConfig(
            num_reads=10,
            mean_read_length=8,
            std_read_length=0,
            min_read_length=4,
            mean_quality=20.0,
            reads_per_file=10,
            output_format="fastq",
        )
        gen = BuiltinGenerator(config)

        target = tmp_path / "target" / "mixed_reads.fastq"
        entry = FileEntry(
            target=target,
            operation="generate",
            read_count=6,
            file_index=0,
            mixed_genome_reads=[(genome_a, 3), (genome_b, 3)],
        )
        result = execute_entry(entry, generator=gen)
        assert result.exists()
        lines = result.read_text().strip().split("\n")
        # 6 reads * 4 lines each
        assert len(lines) == 24


# -------------------------------------------------------------------
# Monitoring
# -------------------------------------------------------------------


class TestMonitoringFormatters:
    """Tests for formatting helper functions."""

    def test_format_bytes_small(self) -> None:
        assert "B" in format_bytes(500)

    def test_format_bytes_kilobytes(self) -> None:
        assert "KB" in format_bytes(2048)

    def test_format_bytes_megabytes(self) -> None:
        assert "MB" in format_bytes(2 * 1024 * 1024)

    def test_format_bytes_gigabytes(self) -> None:
        assert "GB" in format_bytes(3 * 1024**3)

    def test_format_bytes_terabytes(self) -> None:
        assert "TB" in format_bytes(2 * 1024**4)

    def test_format_bytes_petabytes(self) -> None:
        assert "PB" in format_bytes(2 * 1024**5)

    def test_format_time_seconds(self) -> None:
        assert "s" in format_time(30.0)

    def test_format_time_minutes(self) -> None:
        assert "m" in format_time(120.0)

    def test_format_time_hours(self) -> None:
        assert "h" in format_time(7200.0)


class TestSimulationMetrics:
    """Tests for SimulationMetrics properties."""

    def test_throughput_zero_elapsed(self) -> None:
        m = SimulationMetrics()
        assert m.throughput == 0.0

    def test_throughput_no_files(self) -> None:
        m = SimulationMetrics(files_processed=0)
        assert m.throughput == 0.0

    def test_progress_percentage_zero_total(self) -> None:
        m = SimulationMetrics(files_total=0)
        assert m.progress_percentage == 0.0


class TestNullMonitor:
    """Tests for NullMonitor interface completeness."""

    def test_null_monitor_all_methods(self) -> None:
        m = NullMonitor()
        m.start()
        m.update(bytes_delta=100)
        metrics = m.get_metrics()
        assert isinstance(metrics, SimulationMetrics)
        m.stop()


class TestProgressMonitorEta:
    """Tests for ProgressMonitor ETA estimation."""

    def test_eta_none_when_no_files_processed(self) -> None:
        mon = ProgressMonitor(100, enable_resources=False)
        metrics = mon.get_metrics()
        assert metrics.eta_seconds is None

    def test_eta_zero_when_complete(self) -> None:
        mon = ProgressMonitor(1, enable_resources=False)
        mon.update(bytes_delta=10)
        metrics = mon.get_metrics()
        assert metrics.eta_seconds == 0.0

    @pytest.mark.slow
    def test_display_callback_invoked(self) -> None:
        """Display callback receives metrics during update loop."""
        callback = MagicMock()
        mon = ProgressMonitor(
            10,
            update_interval=0.05,
            display_callback=callback,
            enable_resources=False,
        )
        mon.start()
        import time

        time.sleep(0.15)
        mon.stop()
        assert callback.call_count >= 1

class TestCreateMonitor:
    """Tests for the monitor factory function."""

    def test_create_none_monitor(self) -> None:
        m = create_monitor("none", total_files=10)
        assert isinstance(m, NullMonitor)

    def test_create_basic_monitor(self) -> None:
        m = create_monitor("basic", total_files=10)
        assert isinstance(m, ProgressMonitor)


# -------------------------------------------------------------------
# CLI edge cases
# -------------------------------------------------------------------


class TestCliEdgeCases:
    """CLI edge cases for coverage."""

    def test_replay_random_factor_out_of_range(self, tmp_path: Path) -> None:
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
                "--random-factor",
                "1.5",
                "--interval",
                "0",
            ],
        )
        assert result.exit_code != 0

    def test_replay_burst_probability_out_of_range(self, tmp_path: Path) -> None:
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
                "--burst-probability",
                "2.0",
                "--interval",
                "0",
            ],
        )
        assert result.exit_code != 0

    def test_replay_burst_rate_multiplier_negative(self, tmp_path: Path) -> None:
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
                "--burst-rate-multiplier",
                "-1.0",
                "--interval",
                "0",
            ],
        )
        assert result.exit_code != 0

    def test_replay_adaptation_rate_out_of_range(self, tmp_path: Path) -> None:
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
                "--adaptation-rate",
                "2.0",
                "--interval",
                "0",
            ],
        )
        assert result.exit_code != 0

    def test_replay_history_size_zero(self, tmp_path: Path) -> None:
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
                "--history-size",
                "0",
                "--interval",
                "0",
            ],
        )
        assert result.exit_code != 0

    def test_generate_with_quiet_mode(self, tmp_path: Path) -> None:
        fasta = tmp_path / "genome.fa"
        fasta.write_text(">chr1\nACGTACGTACGTACGT\n")
        target = tmp_path / "target"
        result = runner.invoke(
            app,
            [
                "generate",
                "--target",
                str(target),
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
                "--quiet",
                "--no-wait",
            ],
        )
        assert result.exit_code == 0

    def test_replay_with_monitor_none(self, tmp_path: Path) -> None:
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
                "--monitor",
                "none",
                "--interval",
                "0",
            ],
        )
        assert result.exit_code == 0

    def test_generate_missing_genome_path(self, tmp_path: Path) -> None:
        """Generate with a non-existent genome path fails."""
        result = runner.invoke(
            app,
            [
                "generate",
                "--target",
                str(tmp_path / "target"),
                "--genomes",
                str(tmp_path / "nonexistent.fa"),
                "--no-wait",
            ],
        )
        assert result.exit_code != 0

    def test_recommend_no_args_shows_all(self) -> None:
        """Recommend without arguments shows all profiles."""
        result = runner.invoke(app, ["recommend"])
        assert result.exit_code == 0
        assert "development" in result.output

    def test_recommend_empty_source(self, tmp_path: Path) -> None:
        """Recommend with empty source directory fails."""
        empty = tmp_path / "empty_src"
        empty.mkdir()
        result = runner.invoke(
            app,
            ["recommend", "--source", str(empty)],
        )
        assert result.exit_code != 0

    def test_download_no_source_specified(self) -> None:
        """Download without any source fails."""
        result = runner.invoke(app, ["download"])
        assert result.exit_code != 0


# -------------------------------------------------------------------
# Deps: psutil fallback
# -------------------------------------------------------------------


class TestDepsEdgeCases:
    """Tests for dependency detection edge cases."""

    def test_cli_enhanced_monitor_without_psutil(self, tmp_path: Path) -> None:
        """Enhanced monitor falls back to basic when psutil unavailable."""
        source = tmp_path / "source"
        source.mkdir()
        (source / "r.fastq").write_text("@r1\nACGT\n+\nIIII\n")
        with patch.dict("sys.modules", {"psutil": None}):
            with patch("nanopore_simulator.cli_helpers._resolve_monitor") as mock_resolve:
                mock_resolve.return_value = "basic"
                result = runner.invoke(
                    app,
                    [
                        "replay",
                        "--source",
                        str(source),
                        "--target",
                        str(tmp_path / "target"),
                        "--monitor",
                        "default",
                        "--interval",
                        "0",
                    ],
                )
                assert result.exit_code == 0


# -------------------------------------------------------------------
# Link overwrite
# -------------------------------------------------------------------


class TestLinkOverwrite:
    """Test that linking overwrites existing symlinks."""

    def test_link_overwrites_existing(self, tmp_path: Path) -> None:
        source = tmp_path / "source.fastq"
        source.write_text("@r1\nACGT\n+\nIIII\n")
        target = tmp_path / "target" / "reads.fastq"
        target.parent.mkdir()
        # Create initial symlink to something else
        dummy = tmp_path / "dummy.fastq"
        dummy.write_text("@old\nTTTT\n+\nIIII\n")
        target.symlink_to(dummy)

        entry = FileEntry(
            source=source,
            target=target,
            operation="link",
        )
        execute_entry(entry)
        assert target.read_text() == source.read_text()
