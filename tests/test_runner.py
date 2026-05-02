"""Tests for orchestration runner."""

import signal
from pathlib import Path

import pytest

from nanopore_simulator.config import GenerateConfig, ReplayConfig
from nanopore_simulator.runner import (
    _install_signal_handlers,
    _restore_signal_handlers,
    _signal_handler,
    run_generate,
    run_replay,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def singleplex_source(tmp_path: Path) -> Path:
    """Create a singleplex source directory with 5 FASTQ files."""
    source = tmp_path / "source_single"
    source.mkdir()
    for i in range(5):
        (source / f"reads_{i}.fastq").write_text(f"@read{i}\nACGTACGT\n+\nIIIIIIII\n")
    return source


@pytest.fixture
def multiplex_source(tmp_path: Path) -> Path:
    """Create a multiplex source with 2 barcodes, 3 files each."""
    source = tmp_path / "source_multi"
    source.mkdir()
    for bc in ["barcode01", "barcode02"]:
        bc_dir = source / bc
        bc_dir.mkdir()
        for i in range(3):
            (bc_dir / f"reads_{i}.fastq").write_text(
                f"@read{i}\nACGTACGT\n+\nIIIIIIII\n"
            )
    return source


@pytest.fixture
def empty_source(tmp_path: Path) -> Path:
    """Create an empty source directory."""
    source = tmp_path / "source_empty"
    source.mkdir()
    return source


@pytest.fixture
def genome_a(tmp_path: Path) -> Path:
    """Create a genome FASTA file."""
    fasta = tmp_path / "genome_a.fa"
    fasta.write_text(
        ">chr1\nACGTACGTACGTACGTACGTACGTACGTACGT\n"
        ">chr2\nTTTTAAAACCCCGGGGTTTTAAAACCCCGGGG\n"
    )
    return fasta


@pytest.fixture
def genome_b(tmp_path: Path) -> Path:
    """Create a second genome FASTA file."""
    fasta = tmp_path / "genome_b.fa"
    fasta.write_text(">chr1\nGCGCGCGCGCGCATATATATATATATATATAT\n")
    return fasta


# ---------------------------------------------------------------------------
# run_replay -- singleplex copy
# ---------------------------------------------------------------------------


class TestRunReplaySingleplex:
    """Tests for singleplex replay mode."""

    def test_copies_all_files(self, singleplex_source: Path, tmp_path: Path) -> None:
        target = tmp_path / "target"
        config = ReplayConfig(
            source_dir=singleplex_source,
            target_dir=target,
            operation="copy",
            interval=0.0,
            monitor_type="none",
        )
        run_replay(config)
        output_files = list(target.glob("*.fastq"))
        assert len(output_files) == 5
        # Content preserved
        for f in output_files:
            assert f.read_text() == (singleplex_source / f.name).read_text()

    def test_links_all_files(self, singleplex_source: Path, tmp_path: Path) -> None:
        target = tmp_path / "target"
        config = ReplayConfig(
            source_dir=singleplex_source,
            target_dir=target,
            operation="link",
            interval=0.0,
            monitor_type="none",
        )
        run_replay(config)
        output_files = list(target.glob("*.fastq"))
        assert len(output_files) == 5
        assert all(f.is_symlink() for f in output_files)


# ---------------------------------------------------------------------------
# run_replay -- multiplex
# ---------------------------------------------------------------------------


class TestRunReplayMultiplex:
    """Tests for multiplex replay mode."""

    def test_preserves_structure(self, multiplex_source: Path, tmp_path: Path) -> None:
        target = tmp_path / "target"
        config = ReplayConfig(
            source_dir=multiplex_source,
            target_dir=target,
            operation="copy",
            interval=0.0,
            monitor_type="none",
        )
        run_replay(config)

        bc01_files = list((target / "barcode01").glob("*.fastq"))
        bc02_files = list((target / "barcode02").glob("*.fastq"))
        assert len(bc01_files) == 3
        assert len(bc02_files) == 3


# ---------------------------------------------------------------------------
# run_replay -- parallel
# ---------------------------------------------------------------------------


class TestRunReplayParallel:
    """Tests for parallel replay mode."""

    def test_parallel_copy(self, singleplex_source: Path, tmp_path: Path) -> None:
        target = tmp_path / "target"
        config = ReplayConfig(
            source_dir=singleplex_source,
            target_dir=target,
            operation="copy",
            interval=0.0,
            parallel=True,
            workers=2,
            monitor_type="none",
        )
        run_replay(config)
        output_files = list(target.glob("*.fastq"))
        assert len(output_files) == 5

    def test_parallel_link(self, singleplex_source: Path, tmp_path: Path) -> None:
        target = tmp_path / "target"
        config = ReplayConfig(
            source_dir=singleplex_source,
            target_dir=target,
            operation="link",
            interval=0.0,
            parallel=True,
            workers=2,
            monitor_type="none",
        )
        run_replay(config)
        output_files = list(target.glob("*.fastq"))
        assert len(output_files) == 5
        assert all(f.is_symlink() for f in output_files)


# ---------------------------------------------------------------------------
# run_replay -- empty source
# ---------------------------------------------------------------------------


class TestRunReplayEmpty:
    """Tests for empty source directory.

    Pre-2026-05-02 the runner returned silently with INFO-level
    logging on an empty source -- a forgotten --source pointing at
    the wrong directory looked exactly like a successful no-op,
    which defeated CI pipelines checking $?. The audit followup F6
    flagged this; the runner now raises EmptySourceError so the CLI
    can exit with a non-zero code and a clear message.
    """

    def test_empty_source_raises(
        self, empty_source: Path, tmp_path: Path
    ) -> None:
        from nanopore_simulator.runner import EmptySourceError

        target = tmp_path / "target"
        config = ReplayConfig(
            source_dir=empty_source,
            target_dir=target,
            interval=0.0,
            monitor_type="none",
        )
        with pytest.raises(EmptySourceError) as excinfo:
            run_replay(config)
        # Message names the offending source dir so the operator
        # knows which path was wrong.
        assert str(empty_source) in str(excinfo.value)


# ---------------------------------------------------------------------------
# run_generate -- basic
# ---------------------------------------------------------------------------


class TestRunGenerate:
    """Tests for generate mode."""

    def test_generates_correct_file_count(self, genome_a: Path, tmp_path: Path) -> None:
        target = tmp_path / "target"
        config = GenerateConfig(
            target_dir=target,
            genome_inputs=[genome_a],
            read_count=200,
            reads_per_file=100,
            generator_backend="builtin",
            mean_length=10,
            std_length=3,
            min_length=5,
            interval=0.0,
            monitor_type="none",
            output_format="fastq",
        )
        run_generate(config)
        output_files = list(target.glob("*.fastq"))
        assert len(output_files) == 2  # 200 / 100

    def test_generate_parallel(self, genome_a: Path, tmp_path: Path) -> None:
        target = tmp_path / "target"
        config = GenerateConfig(
            target_dir=target,
            genome_inputs=[genome_a],
            read_count=200,
            reads_per_file=100,
            generator_backend="builtin",
            mean_length=10,
            std_length=3,
            min_length=5,
            interval=0.0,
            parallel=True,
            workers=2,
            monitor_type="none",
            output_format="fastq",
        )
        run_generate(config)
        output_files = list(target.glob("*.fastq"))
        assert len(output_files) == 2

    def test_generate_multiple_genomes(
        self, genome_a: Path, genome_b: Path, tmp_path: Path
    ) -> None:
        target = tmp_path / "target"
        config = GenerateConfig(
            target_dir=target,
            genome_inputs=[genome_a, genome_b],
            read_count=200,
            reads_per_file=100,
            generator_backend="builtin",
            mean_length=10,
            std_length=3,
            min_length=5,
            interval=0.0,
            monitor_type="none",
            output_format="fastq",
        )
        run_generate(config)
        # Each genome gets 100 reads -> 1 file each = 2 files
        output_files = list(target.glob("*.fastq"))
        assert len(output_files) == 2

    def test_generate_multiplex_structure(
        self, genome_a: Path, genome_b: Path, tmp_path: Path
    ) -> None:
        target = tmp_path / "target"
        config = GenerateConfig(
            target_dir=target,
            genome_inputs=[genome_a, genome_b],
            read_count=200,
            reads_per_file=100,
            generator_backend="builtin",
            mean_length=10,
            std_length=3,
            min_length=5,
            interval=0.0,
            structure="multiplex",
            monitor_type="none",
            output_format="fastq",
        )
        run_generate(config)
        bc01_files = list((target / "barcode01").glob("*.fastq"))
        bc02_files = list((target / "barcode02").glob("*.fastq"))
        assert len(bc01_files) == 1
        assert len(bc02_files) == 1


# ---------------------------------------------------------------------------
# run_generate -- with timing
# ---------------------------------------------------------------------------


class TestRunGenerateWithTiming:
    """Tests for generate mode with non-zero interval (kept short)."""

    def test_timing_model_applied(self, genome_a: Path, tmp_path: Path) -> None:
        """Verify that timing model does not break the flow."""
        target = tmp_path / "target"
        config = GenerateConfig(
            target_dir=target,
            genome_inputs=[genome_a],
            read_count=300,
            reads_per_file=100,
            batch_size=1,
            generator_backend="builtin",
            mean_length=10,
            std_length=3,
            min_length=5,
            interval=0.01,
            timing_model="uniform",
            monitor_type="none",
            output_format="fastq",
        )
        run_generate(config)
        output_files = list(target.glob("*.fastq"))
        assert len(output_files) == 3


# ---------------------------------------------------------------------------
# Signal handler install / restore
# ---------------------------------------------------------------------------


class TestSignalHandlers:
    """Tests for _install_signal_handlers and _restore_signal_handlers."""

    def test_install_returns_previous_handlers(self) -> None:
        """_install_signal_handlers returns a dict mapping each handled signal
        to the handler that was previously registered."""
        previous = _install_signal_handlers()
        try:
            assert isinstance(previous, dict)
            # Both SIGTERM and SIGHUP should be present (or fewer if the
            # platform silently dropped one — the function swallows OSError).
            for sig in previous:
                assert isinstance(sig, signal.Signals)
        finally:
            _restore_signal_handlers(previous)

    def test_install_replaces_handlers(self) -> None:
        """After installation, SIGTERM and SIGHUP are mapped to _signal_handler."""
        previous = _install_signal_handlers()
        try:
            for sig in (signal.SIGTERM, signal.SIGHUP):
                try:
                    current = signal.getsignal(sig)
                    assert (
                        current is _signal_handler
                    ), f"Expected _signal_handler for {sig!r}, got {current!r}"
                except (OSError, ValueError):
                    # Signal not available on this platform — skip quietly.
                    pass
        finally:
            _restore_signal_handlers(previous)

    def test_restore_reinstates_previous_handlers(self) -> None:
        """_restore_signal_handlers puts back the handlers saved before install."""
        # Record what was there before the test interferes.
        original_sigterm = signal.getsignal(signal.SIGTERM)

        previous = _install_signal_handlers()
        _restore_signal_handlers(previous)

        restored = signal.getsignal(signal.SIGTERM)
        assert restored is original_sigterm

    def test_signal_handler_raises_keyboard_interrupt(self) -> None:
        """_signal_handler converts SIGTERM to KeyboardInterrupt."""
        with pytest.raises(KeyboardInterrupt, match="SIGTERM"):
            _signal_handler(signal.SIGTERM, None)
