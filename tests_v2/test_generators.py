"""Tests for read generation backends."""

import gzip
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nanopore_simulator_v2.generators import (
    BuiltinGenerator,
    GeneratorConfig,
    GenomeInput,
    SubprocessGenerator,
    create_generator,
    detect_available_backends,
    parse_fasta,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def simple_fasta(tmp_path: Path) -> Path:
    """Create a two-record FASTA file."""
    fasta = tmp_path / "genome.fa"
    fasta.write_text(
        ">chr1\nACGTACGTACGTACGTACGT\n"
        ">chr2\nGCTAGCTAGCTAGCTAGCTA\n"
    )
    return fasta


@pytest.fixture
def gzipped_fasta(tmp_path: Path) -> Path:
    """Create a gzip-compressed FASTA file."""
    fasta = tmp_path / "genome.fa.gz"
    with gzip.open(fasta, "wt") as f:
        f.write(">chr1\nACGTACGTACGT\n>chr2\nTTTTAAAA\n")
    return fasta


@pytest.fixture
def empty_fasta(tmp_path: Path) -> Path:
    """Create a FASTA file with no records."""
    fasta = tmp_path / "empty.fa"
    fasta.write_text("")
    return fasta


@pytest.fixture
def default_config() -> GeneratorConfig:
    return GeneratorConfig(
        num_reads=50,
        mean_read_length=10,
        std_read_length=3,
        min_read_length=5,
        mean_quality=20.0,
        reads_per_file=10,
        output_format="fastq",
    )


# ---------------------------------------------------------------------------
# GeneratorConfig
# ---------------------------------------------------------------------------


class TestGeneratorConfig:
    """Validation of the GeneratorConfig dataclass."""

    def test_default_values(self) -> None:
        cfg = GeneratorConfig()
        assert cfg.num_reads == 1000
        assert cfg.mean_read_length == 5000
        assert cfg.std_read_length == 2000
        assert cfg.min_read_length == 200
        assert cfg.mean_quality == 20.0
        assert cfg.std_quality == 4.0
        assert cfg.reads_per_file == 100
        assert cfg.output_format == "fastq.gz"

    def test_invalid_num_reads_zero(self) -> None:
        with pytest.raises(ValueError, match="num_reads"):
            GeneratorConfig(num_reads=0)

    def test_invalid_num_reads_negative(self) -> None:
        with pytest.raises(ValueError, match="num_reads"):
            GeneratorConfig(num_reads=-5)

    def test_invalid_mean_read_length(self) -> None:
        with pytest.raises(ValueError, match="mean_read_length"):
            GeneratorConfig(mean_read_length=0)

    def test_invalid_std_read_length_negative(self) -> None:
        with pytest.raises(ValueError, match="std_read_length"):
            GeneratorConfig(std_read_length=-1)

    def test_invalid_min_read_length(self) -> None:
        with pytest.raises(ValueError, match="min_read_length"):
            GeneratorConfig(min_read_length=0)

    def test_invalid_mean_quality_zero(self) -> None:
        with pytest.raises(ValueError, match="mean_quality"):
            GeneratorConfig(mean_quality=0)

    def test_invalid_mean_quality_negative(self) -> None:
        with pytest.raises(ValueError, match="mean_quality"):
            GeneratorConfig(mean_quality=-1.0)

    def test_invalid_std_quality_negative(self) -> None:
        with pytest.raises(ValueError, match="std_quality"):
            GeneratorConfig(std_quality=-1)

    def test_invalid_reads_per_file(self) -> None:
        with pytest.raises(ValueError, match="reads_per_file"):
            GeneratorConfig(reads_per_file=0)

    def test_invalid_output_format(self) -> None:
        with pytest.raises(ValueError, match="output_format"):
            GeneratorConfig(output_format="bam")

    def test_valid_output_format_fastq(self) -> None:
        cfg = GeneratorConfig(output_format="fastq")
        assert cfg.output_format == "fastq"

    def test_valid_output_format_fastq_gz(self) -> None:
        cfg = GeneratorConfig(output_format="fastq.gz")
        assert cfg.output_format == "fastq.gz"

    def test_zero_std_length_is_valid(self) -> None:
        cfg = GeneratorConfig(std_read_length=0)
        assert cfg.std_read_length == 0

    def test_zero_std_quality_is_valid(self) -> None:
        cfg = GeneratorConfig(std_quality=0)
        assert cfg.std_quality == 0


# ---------------------------------------------------------------------------
# GenomeInput
# ---------------------------------------------------------------------------


class TestGenomeInput:
    """GenomeInput dataclass."""

    def test_basic_creation(self, simple_fasta: Path) -> None:
        gi = GenomeInput(fasta_path=simple_fasta)
        assert gi.fasta_path == simple_fasta
        assert gi.barcode is None

    def test_with_barcode(self, simple_fasta: Path) -> None:
        gi = GenomeInput(fasta_path=simple_fasta, barcode="barcode01")
        assert gi.barcode == "barcode01"


# ---------------------------------------------------------------------------
# parse_fasta
# ---------------------------------------------------------------------------


class TestParseFasta:
    """FASTA parsing for both plain and gzipped files."""

    def test_parse_plain(self, simple_fasta: Path) -> None:
        records = parse_fasta(simple_fasta)
        assert len(records) == 2
        assert records[0][0] == "chr1"
        assert records[0][1] == "ACGTACGTACGTACGTACGT"
        assert records[1][0] == "chr2"

    def test_parse_gzipped(self, gzipped_fasta: Path) -> None:
        records = parse_fasta(gzipped_fasta)
        assert len(records) == 2
        assert records[0][0] == "chr1"
        assert records[0][1] == "ACGTACGTACGT"

    def test_parse_empty(self, empty_fasta: Path) -> None:
        records = parse_fasta(empty_fasta)
        assert records == []

    def test_sequences_uppercased(self, tmp_path: Path) -> None:
        fasta = tmp_path / "lower.fa"
        fasta.write_text(">seq1\nacgtacgt\n")
        records = parse_fasta(fasta)
        assert records[0][1] == "ACGTACGT"

    def test_multi_line_sequence(self, tmp_path: Path) -> None:
        fasta = tmp_path / "multiline.fa"
        fasta.write_text(">seq1\nACGT\nTTTT\n")
        records = parse_fasta(fasta)
        assert records[0][1] == "ACGTTTTT"

    def test_header_uses_first_word(self, tmp_path: Path) -> None:
        fasta = tmp_path / "header.fa"
        fasta.write_text(">seq1 description text\nACGT\n")
        records = parse_fasta(fasta)
        assert records[0][0] == "seq1"


# ---------------------------------------------------------------------------
# BuiltinGenerator
# ---------------------------------------------------------------------------


class TestBuiltinGenerator:
    """Tests for the built-in (error-free) read generator."""

    def test_is_available_always_true(self) -> None:
        assert BuiltinGenerator.is_available() is True

    def test_generate_reads_creates_file(
        self, default_config: GeneratorConfig, simple_fasta: Path, tmp_path: Path
    ) -> None:
        gen = BuiltinGenerator(default_config)
        genome = GenomeInput(fasta_path=simple_fasta)
        out = gen.generate_reads(genome, tmp_path / "out", file_index=0)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_generate_reads_correct_count(
        self, simple_fasta: Path, tmp_path: Path
    ) -> None:
        cfg = GeneratorConfig(
            num_reads=20,
            mean_read_length=10,
            std_read_length=2,
            min_read_length=5,
            reads_per_file=20,
            output_format="fastq",
        )
        gen = BuiltinGenerator(cfg)
        genome = GenomeInput(fasta_path=simple_fasta)
        out = gen.generate_reads(genome, tmp_path / "out", file_index=0)

        # Count reads in the output file (each FASTQ record = 4 lines)
        lines = out.read_text().strip().split("\n")
        assert len(lines) == 20 * 4

    def test_generate_reads_explicit_num_reads(
        self, default_config: GeneratorConfig, simple_fasta: Path, tmp_path: Path
    ) -> None:
        gen = BuiltinGenerator(default_config)
        genome = GenomeInput(fasta_path=simple_fasta)
        out = gen.generate_reads(
            genome, tmp_path / "out", file_index=0, num_reads=5
        )
        lines = out.read_text().strip().split("\n")
        assert len(lines) == 5 * 4

    def test_generate_reads_gzipped(
        self, simple_fasta: Path, tmp_path: Path
    ) -> None:
        cfg = GeneratorConfig(
            num_reads=5,
            mean_read_length=10,
            std_read_length=0,
            min_read_length=5,
            reads_per_file=5,
            output_format="fastq.gz",
        )
        gen = BuiltinGenerator(cfg)
        genome = GenomeInput(fasta_path=simple_fasta)
        out = gen.generate_reads(genome, tmp_path / "out", file_index=0)
        assert out.name.endswith(".fastq.gz")
        with gzip.open(out, "rt") as f:
            content = f.read().strip()
        assert len(content.split("\n")) == 5 * 4

    def test_generate_reads_in_memory(
        self, default_config: GeneratorConfig, simple_fasta: Path
    ) -> None:
        gen = BuiltinGenerator(default_config)
        genome = GenomeInput(fasta_path=simple_fasta)
        reads = gen.generate_reads_in_memory(genome, num_reads=5)
        assert len(reads) == 5
        for header, seq, sep, qual in reads:
            assert header.startswith("@")
            assert len(seq) > 0
            assert sep == "+"
            assert len(qual) == len(seq)

    def test_generate_reads_in_memory_quality_valid_phred(
        self, default_config: GeneratorConfig, simple_fasta: Path
    ) -> None:
        gen = BuiltinGenerator(default_config)
        genome = GenomeInput(fasta_path=simple_fasta)
        reads = gen.generate_reads_in_memory(genome, num_reads=3)
        for _, _, _, qual in reads:
            for ch in qual:
                assert 33 <= ord(ch) <= 73  # Phred+33 range

    def test_output_filename_plain(
        self, default_config: GeneratorConfig, simple_fasta: Path
    ) -> None:
        gen = BuiltinGenerator(default_config)
        genome = GenomeInput(fasta_path=simple_fasta)
        name = gen._output_filename(genome, file_index=3)
        assert "genome" in name
        assert "0003" in name
        assert name.endswith(".fastq")

    def test_output_filename_gz(
        self, simple_fasta: Path
    ) -> None:
        cfg = GeneratorConfig(output_format="fastq.gz")
        gen = BuiltinGenerator(cfg)
        genome = GenomeInput(fasta_path=simple_fasta)
        name = gen._output_filename(genome, file_index=0)
        assert name.endswith(".fastq.gz")

    def test_genome_caching(
        self, default_config: GeneratorConfig, simple_fasta: Path, tmp_path: Path
    ) -> None:
        gen = BuiltinGenerator(default_config)
        genome = GenomeInput(fasta_path=simple_fasta)
        # First call parses; second should use cache.
        gen.generate_reads(genome, tmp_path / "out1", file_index=0, num_reads=2)
        gen.generate_reads(genome, tmp_path / "out2", file_index=1, num_reads=2)
        # Cache should have exactly one entry
        assert len(gen._genome_cache) == 1

    def test_empty_fasta_raises(
        self, default_config: GeneratorConfig, empty_fasta: Path, tmp_path: Path
    ) -> None:
        gen = BuiltinGenerator(default_config)
        genome = GenomeInput(fasta_path=empty_fasta)
        with pytest.raises(ValueError, match="No sequences"):
            gen.generate_reads(genome, tmp_path / "out", file_index=0)

    def test_reverse_complement(self) -> None:
        assert BuiltinGenerator._reverse_complement("ACGT") == "ACGT"
        assert BuiltinGenerator._reverse_complement("AAAA") == "TTTT"
        assert BuiltinGenerator._reverse_complement("GCTA") == "TAGC"

    def test_zero_std_produces_constant_length(
        self, simple_fasta: Path
    ) -> None:
        cfg = GeneratorConfig(
            num_reads=5,
            mean_read_length=10,
            std_read_length=0,
            min_read_length=5,
            reads_per_file=5,
            output_format="fastq",
        )
        gen = BuiltinGenerator(cfg)
        genome = GenomeInput(fasta_path=simple_fasta)
        reads = gen.generate_reads_in_memory(genome, num_reads=5)
        for _, seq, _, _ in reads:
            assert len(seq) == 10

    def test_min_read_length_enforced(
        self, simple_fasta: Path
    ) -> None:
        cfg = GeneratorConfig(
            num_reads=20,
            mean_read_length=5,
            std_read_length=10,
            min_read_length=5,
            reads_per_file=20,
            output_format="fastq",
        )
        gen = BuiltinGenerator(cfg)
        genome = GenomeInput(fasta_path=simple_fasta)
        reads = gen.generate_reads_in_memory(genome, num_reads=20)
        for _, seq, _, _ in reads:
            assert len(seq) >= 5


# ---------------------------------------------------------------------------
# SubprocessGenerator
# ---------------------------------------------------------------------------


class TestSubprocessGenerator:
    """Tests for the unified subprocess wrapper (badread / nanosim)."""

    def test_class_is_available_always_false(self) -> None:
        # The classmethod returns False; instance _backend_available() checks.
        assert SubprocessGenerator.is_available() is False

    def test_badread_backend_available_when_installed(self) -> None:
        with patch("nanopore_simulator_v2.generators.shutil.which", return_value="/usr/bin/badread"):
            with patch("nanopore_simulator_v2.generators.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                gen = SubprocessGenerator(GeneratorConfig(), backend="badread")
                assert gen._backend_available() is True

    def test_badread_not_available(self) -> None:
        with patch("nanopore_simulator_v2.generators.shutil.which", return_value=None):
            gen = SubprocessGenerator(GeneratorConfig(), backend="badread")
            assert gen._backend_available() is False

    def test_nanosim_available_via_nanosim(self) -> None:
        def which_side_effect(name: str) -> str:
            if name == "nanosim":
                return "/usr/bin/nanosim"
            return None

        with patch("nanopore_simulator_v2.generators.shutil.which", side_effect=which_side_effect):
            with patch("nanopore_simulator_v2.generators.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                gen = SubprocessGenerator(GeneratorConfig(), backend="nanosim")
                assert gen._backend_available() is True

    def test_nanosim_available_via_simulator_py(self) -> None:
        def which_side_effect(name: str) -> str:
            if name == "simulator.py":
                return "/usr/bin/simulator.py"
            return None

        with patch("nanopore_simulator_v2.generators.shutil.which", side_effect=which_side_effect):
            with patch("nanopore_simulator_v2.generators.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                gen = SubprocessGenerator(GeneratorConfig(), backend="nanosim")
                assert gen._backend_available() is True

    def test_nanosim_not_available(self) -> None:
        with patch("nanopore_simulator_v2.generators.shutil.which", return_value=None):
            gen = SubprocessGenerator(GeneratorConfig(), backend="nanosim")
            assert gen._backend_available() is False

    def test_badread_generate_reads(
        self, simple_fasta: Path, tmp_path: Path
    ) -> None:
        fastq_output = "@read1\nACGT\n+\nIIII\n@read2\nTTTT\n+\nIIII\n"
        mock_result = MagicMock(
            returncode=0, stdout=fastq_output, stderr=""
        )
        cfg = GeneratorConfig(
            num_reads=2,
            mean_read_length=10,
            reads_per_file=2,
            output_format="fastq",
        )
        gen = SubprocessGenerator(cfg, backend="badread")
        genome = GenomeInput(fasta_path=simple_fasta)

        with patch("nanopore_simulator_v2.generators.subprocess.run", return_value=mock_result):
            out = gen.generate_reads(genome, tmp_path / "out", file_index=0)

        assert out.exists()
        content = out.read_text()
        assert "@read1" in content

    def test_badread_generate_reads_subprocess_error(
        self, simple_fasta: Path, tmp_path: Path
    ) -> None:
        cfg = GeneratorConfig(
            num_reads=2, mean_read_length=10, reads_per_file=2, output_format="fastq"
        )
        gen = SubprocessGenerator(cfg, backend="badread")
        genome = GenomeInput(fasta_path=simple_fasta)

        exc = subprocess.CalledProcessError(1, "badread", stderr="boom")
        with patch("nanopore_simulator_v2.generators.subprocess.run", side_effect=exc):
            with pytest.raises(RuntimeError, match="badread exited"):
                gen.generate_reads(genome, tmp_path / "out", file_index=0)

    def test_nanosim_generate_reads(
        self, simple_fasta: Path, tmp_path: Path
    ) -> None:
        """NanoSim produces FASTA output that must be converted to FASTQ."""
        cfg = GeneratorConfig(
            num_reads=2,
            mean_read_length=10,
            reads_per_file=2,
            output_format="fastq",
        )
        gen = SubprocessGenerator(cfg, backend="nanosim")
        genome = GenomeInput(fasta_path=simple_fasta)
        output_dir = tmp_path / "out"

        def run_side_effect(*args, **kwargs):
            # NanoSim writes aligned/unaligned FASTA files using a prefix
            cmd = args[0]
            prefix = None
            for i, arg in enumerate(cmd):
                if arg == "-o" and i + 1 < len(cmd):
                    prefix = cmd[i + 1]
                    break
            if prefix:
                Path(f"{prefix}_aligned_reads.fasta").write_text(
                    ">read1\nACGT\n>read2\nTTTT\n"
                )
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch(
            "nanopore_simulator_v2.generators.shutil.which", return_value="/usr/bin/nanosim"
        ):
            with patch(
                "nanopore_simulator_v2.generators.subprocess.run",
                side_effect=run_side_effect,
            ):
                out = gen.generate_reads(genome, output_dir, file_index=0)

        assert out.exists()
        # Output should be FASTQ (4 lines per record)
        lines = out.read_text().strip().split("\n")
        assert len(lines) % 4 == 0
        assert lines[0].startswith("@")

    def test_badread_generate_reads_in_memory(self, simple_fasta: Path) -> None:
        fastq_output = "@read1\nACGT\n+\nIIII\n@read2\nTTTT\n+\nIIII\n"
        mock_result = MagicMock(
            returncode=0, stdout=fastq_output, stderr=""
        )
        cfg = GeneratorConfig(
            num_reads=2,
            mean_read_length=10,
            reads_per_file=2,
            output_format="fastq",
        )
        gen = SubprocessGenerator(cfg, backend="badread")
        genome = GenomeInput(fasta_path=simple_fasta)

        with patch("nanopore_simulator_v2.generators.subprocess.run", return_value=mock_result):
            reads = gen.generate_reads_in_memory(genome, num_reads=2)

        assert len(reads) == 2
        assert reads[0][0] == "@read1"

    def test_unknown_backend_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown subprocess backend"):
            SubprocessGenerator(GeneratorConfig(), backend="unknown")


# ---------------------------------------------------------------------------
# create_generator factory
# ---------------------------------------------------------------------------


class TestCreateGenerator:
    """Factory function for creating generators."""

    def test_create_builtin(self) -> None:
        gen = create_generator("builtin", GeneratorConfig())
        assert isinstance(gen, BuiltinGenerator)

    def test_create_auto_falls_to_builtin(self) -> None:
        """With no external tools, auto should fall back to builtin."""
        with patch("nanopore_simulator_v2.generators.shutil.which", return_value=None):
            gen = create_generator("auto", GeneratorConfig())
            assert isinstance(gen, BuiltinGenerator)

    def test_create_auto_prefers_badread(self) -> None:
        with patch("nanopore_simulator_v2.generators.shutil.which", return_value="/usr/bin/badread"):
            with patch("nanopore_simulator_v2.generators.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                gen = create_generator("auto", GeneratorConfig())
                assert isinstance(gen, SubprocessGenerator)

    def test_create_invalid_backend(self) -> None:
        with pytest.raises(ValueError, match="Unknown backend"):
            create_generator("invalid", GeneratorConfig())

    def test_create_badread_not_installed(self) -> None:
        with patch("nanopore_simulator_v2.generators.shutil.which", return_value=None):
            with pytest.raises(ValueError, match="not available"):
                create_generator("badread", GeneratorConfig())

    def test_create_nanosim_not_installed(self) -> None:
        with patch("nanopore_simulator_v2.generators.shutil.which", return_value=None):
            with pytest.raises(ValueError, match="not available"):
                create_generator("nanosim", GeneratorConfig())


# ---------------------------------------------------------------------------
# detect_available_backends
# ---------------------------------------------------------------------------


class TestDetectAvailableBackends:
    """Backend availability detection."""

    def test_returns_dict(self) -> None:
        result = detect_available_backends()
        assert isinstance(result, dict)
        assert "builtin" in result

    def test_builtin_always_true(self) -> None:
        result = detect_available_backends()
        assert result["builtin"] is True

    def test_has_badread_and_nanosim_keys(self) -> None:
        result = detect_available_backends()
        assert "badread" in result
        assert "nanosim" in result

    def test_with_no_external_tools(self) -> None:
        with patch("nanopore_simulator_v2.generators.shutil.which", return_value=None):
            result = detect_available_backends()
            assert result["builtin"] is True
            assert result["badread"] is False
            assert result["nanosim"] is False


# ---------------------------------------------------------------------------
# Worker genome cache
# ---------------------------------------------------------------------------


class TestWorkerGenomeCache:
    """Module-level worker genome cache for ProcessPoolExecutor."""

    def test_init_worker_genomes(self) -> None:
        from nanopore_simulator_v2.generators import (
            _WORKER_GENOME_CACHE,
            _init_worker_genomes,
        )

        _init_worker_genomes({"test": "ACGT"})
        # Import again to check the module-level variable was set
        from nanopore_simulator_v2 import generators

        assert generators._WORKER_GENOME_CACHE.get("test") == "ACGT"
        # Clean up
        _init_worker_genomes({})
