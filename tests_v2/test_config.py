"""Tests for configuration dataclasses."""

import pytest
from pathlib import Path
from nanopore_simulator_v2.config import ReplayConfig, GenerateConfig


class TestReplayConfig:
    """ReplayConfig validation and defaults."""

    def test_minimal_valid(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        target = tmp_path / "target"
        cfg = ReplayConfig(source_dir=source, target_dir=target)
        assert cfg.interval == 5.0
        assert cfg.operation == "copy"
        assert cfg.batch_size == 1
        assert cfg.timing_model == "uniform"
        assert cfg.parallel is False
        assert cfg.workers == 4
        assert cfg.monitor_type == "basic"

    def test_link_operation(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        cfg = ReplayConfig(
            source_dir=source, target_dir=tmp_path / "t", operation="link"
        )
        assert cfg.operation == "link"

    def test_invalid_operation(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        with pytest.raises(ValueError, match="operation"):
            ReplayConfig(
                source_dir=source, target_dir=tmp_path / "t", operation="delete"
            )

    def test_negative_interval(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        with pytest.raises(ValueError, match="interval"):
            ReplayConfig(
                source_dir=source, target_dir=tmp_path / "t", interval=-1.0
            )

    def test_zero_interval_allowed(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        cfg = ReplayConfig(
            source_dir=source, target_dir=tmp_path / "t", interval=0.0
        )
        assert cfg.interval == 0.0

    def test_invalid_batch_size(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        with pytest.raises(ValueError, match="batch_size"):
            ReplayConfig(
                source_dir=source, target_dir=tmp_path / "t", batch_size=0
            )

    def test_source_dir_must_exist(self, tmp_path):
        with pytest.raises(ValueError, match="source_dir"):
            ReplayConfig(
                source_dir=tmp_path / "nonexistent", target_dir=tmp_path / "t"
            )

    def test_invalid_timing_model(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        with pytest.raises(ValueError, match="timing_model"):
            ReplayConfig(
                source_dir=source,
                target_dir=tmp_path / "t",
                timing_model="invalid",
            )

    def test_invalid_monitor_type(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        with pytest.raises(ValueError, match="monitor_type"):
            ReplayConfig(
                source_dir=source,
                target_dir=tmp_path / "t",
                monitor_type="invalid",
            )

    def test_invalid_structure(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        with pytest.raises(ValueError, match="structure"):
            ReplayConfig(
                source_dir=source,
                target_dir=tmp_path / "t",
                structure="invalid",
            )

    def test_workers_must_be_positive(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        with pytest.raises(ValueError, match="workers"):
            ReplayConfig(
                source_dir=source, target_dir=tmp_path / "t", workers=0
            )

    def test_rechunking_config(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        cfg = ReplayConfig(
            source_dir=source,
            target_dir=tmp_path / "t",
            reads_per_output=500,
        )
        assert cfg.reads_per_output == 500

    def test_rechunking_incompatible_with_link(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        with pytest.raises(ValueError, match="rechunk.*link"):
            ReplayConfig(
                source_dir=source,
                target_dir=tmp_path / "t",
                operation="link",
                reads_per_output=500,
            )

    def test_all_file_extensions(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        cfg = ReplayConfig(source_dir=source, target_dir=tmp_path / "t")
        assert ".fastq" in cfg.file_extensions
        assert ".fq" in cfg.file_extensions
        assert ".fastq.gz" in cfg.file_extensions
        assert ".fq.gz" in cfg.file_extensions
        assert ".pod5" in cfg.file_extensions

    def test_custom_file_extensions(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        cfg = ReplayConfig(
            source_dir=source,
            target_dir=tmp_path / "t",
            file_extensions=(".fastq",),
        )
        assert cfg.file_extensions == (".fastq",)

    def test_frozen(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        cfg = ReplayConfig(source_dir=source, target_dir=tmp_path / "t")
        with pytest.raises(AttributeError):
            cfg.interval = 10.0

    def test_valid_timing_models(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        for model in ("uniform", "random", "poisson", "adaptive"):
            cfg = ReplayConfig(
                source_dir=source,
                target_dir=tmp_path / "t",
                timing_model=model,
            )
            assert cfg.timing_model == model

    def test_valid_structures(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        for structure in ("auto", "singleplex", "multiplex"):
            cfg = ReplayConfig(
                source_dir=source,
                target_dir=tmp_path / "t",
                structure=structure,
            )
            assert cfg.structure == structure

    def test_adapter_default_none(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        cfg = ReplayConfig(source_dir=source, target_dir=tmp_path / "t")
        assert cfg.adapter is None

    def test_timing_params_default(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        cfg = ReplayConfig(source_dir=source, target_dir=tmp_path / "t")
        assert cfg.timing_params == {}


class TestGenerateConfig:
    """GenerateConfig validation and defaults."""

    def test_minimal_with_genomes(self, tmp_path):
        genome = tmp_path / "genome.fa"
        genome.write_text(">seq\nACGT\n")
        cfg = GenerateConfig(
            target_dir=tmp_path / "out",
            genome_inputs=[genome],
        )
        assert cfg.read_count == 1000
        assert cfg.interval == 5.0
        assert cfg.batch_size == 100
        assert cfg.generator_backend == "auto"
        assert cfg.mean_length == 5000
        assert cfg.std_length == 2000
        assert cfg.mean_quality == 20.0
        assert cfg.std_quality == 4.0

    def test_minimal_with_mock(self, tmp_path):
        cfg = GenerateConfig(
            target_dir=tmp_path / "out",
            mock_name="zymo_d6300",
        )
        assert cfg.mock_name == "zymo_d6300"

    def test_minimal_with_species(self, tmp_path):
        cfg = GenerateConfig(
            target_dir=tmp_path / "out",
            species_inputs=["Escherichia coli"],
        )
        assert cfg.species_inputs == ["Escherichia coli"]

    def test_minimal_with_taxids(self, tmp_path):
        cfg = GenerateConfig(
            target_dir=tmp_path / "out",
            taxid_inputs=["562"],
        )
        assert cfg.taxid_inputs == ["562"]

    def test_no_input_source(self, tmp_path):
        with pytest.raises(ValueError, match="genome.*species.*mock.*taxid"):
            GenerateConfig(target_dir=tmp_path / "out")

    def test_negative_read_count(self, tmp_path):
        genome = tmp_path / "genome.fa"
        genome.write_text(">seq\nACGT\n")
        with pytest.raises(ValueError, match="read_count"):
            GenerateConfig(
                target_dir=tmp_path / "out",
                genome_inputs=[genome],
                read_count=-1,
            )

    def test_zero_read_count(self, tmp_path):
        genome = tmp_path / "genome.fa"
        genome.write_text(">seq\nACGT\n")
        with pytest.raises(ValueError, match="read_count"):
            GenerateConfig(
                target_dir=tmp_path / "out",
                genome_inputs=[genome],
                read_count=0,
            )

    def test_invalid_generator_backend(self, tmp_path):
        genome = tmp_path / "genome.fa"
        genome.write_text(">seq\nACGT\n")
        with pytest.raises(ValueError, match="generator_backend"):
            GenerateConfig(
                target_dir=tmp_path / "out",
                genome_inputs=[genome],
                generator_backend="invalid",
            )

    def test_invalid_output_format(self, tmp_path):
        genome = tmp_path / "genome.fa"
        genome.write_text(">seq\nACGT\n")
        with pytest.raises(ValueError, match="output_format"):
            GenerateConfig(
                target_dir=tmp_path / "out",
                genome_inputs=[genome],
                output_format="bam",
            )

    def test_quality_params(self, tmp_path):
        genome = tmp_path / "genome.fa"
        genome.write_text(">seq\nACGT\n")
        cfg = GenerateConfig(
            target_dir=tmp_path / "out",
            genome_inputs=[genome],
            mean_quality=25.0,
            std_quality=2.0,
        )
        assert cfg.mean_quality == 25.0
        assert cfg.std_quality == 2.0

    def test_frozen(self, tmp_path):
        genome = tmp_path / "genome.fa"
        genome.write_text(">seq\nACGT\n")
        cfg = GenerateConfig(
            target_dir=tmp_path / "out",
            genome_inputs=[genome],
        )
        with pytest.raises(AttributeError):
            cfg.read_count = 5000

    def test_abundances_must_match_genomes(self, tmp_path):
        g1 = tmp_path / "g1.fa"
        g2 = tmp_path / "g2.fa"
        g1.write_text(">s\nACGT\n")
        g2.write_text(">s\nACGT\n")
        with pytest.raises(ValueError, match="abundances"):
            GenerateConfig(
                target_dir=tmp_path / "out",
                genome_inputs=[g1, g2],
                abundances=[0.5],  # should be 2 values
            )

    def test_abundances_must_sum_to_one(self, tmp_path):
        g1 = tmp_path / "g1.fa"
        g2 = tmp_path / "g2.fa"
        g1.write_text(">s\nACGT\n")
        g2.write_text(">s\nACGT\n")
        with pytest.raises(ValueError, match="abundances.*sum"):
            GenerateConfig(
                target_dir=tmp_path / "out",
                genome_inputs=[g1, g2],
                abundances=[0.3, 0.3],
            )

    def test_valid_abundances(self, tmp_path):
        g1 = tmp_path / "g1.fa"
        g2 = tmp_path / "g2.fa"
        g1.write_text(">s\nACGT\n")
        g2.write_text(">s\nACGT\n")
        cfg = GenerateConfig(
            target_dir=tmp_path / "out",
            genome_inputs=[g1, g2],
            abundances=[0.6, 0.4],
        )
        assert cfg.abundances == [0.6, 0.4]

    def test_default_structure_singleplex(self, tmp_path):
        genome = tmp_path / "genome.fa"
        genome.write_text(">seq\nACGT\n")
        cfg = GenerateConfig(
            target_dir=tmp_path / "out",
            genome_inputs=[genome],
        )
        assert cfg.structure == "singleplex"

    def test_default_reads_per_file(self, tmp_path):
        genome = tmp_path / "genome.fa"
        genome.write_text(">seq\nACGT\n")
        cfg = GenerateConfig(
            target_dir=tmp_path / "out",
            genome_inputs=[genome],
        )
        assert cfg.reads_per_file == 100

    def test_min_length_default(self, tmp_path):
        genome = tmp_path / "genome.fa"
        genome.write_text(">seq\nACGT\n")
        cfg = GenerateConfig(
            target_dir=tmp_path / "out",
            genome_inputs=[genome],
        )
        assert cfg.min_length == 200

    def test_mix_reads_default(self, tmp_path):
        genome = tmp_path / "genome.fa"
        genome.write_text(">seq\nACGT\n")
        cfg = GenerateConfig(
            target_dir=tmp_path / "out",
            genome_inputs=[genome],
        )
        assert cfg.mix_reads is False

    def test_offline_mode_default(self, tmp_path):
        genome = tmp_path / "genome.fa"
        genome.write_text(">seq\nACGT\n")
        cfg = GenerateConfig(
            target_dir=tmp_path / "out",
            genome_inputs=[genome],
        )
        assert cfg.offline_mode is False

    def test_valid_generator_backends(self, tmp_path):
        genome = tmp_path / "genome.fa"
        genome.write_text(">seq\nACGT\n")
        for backend in ("auto", "builtin", "badread", "nanosim"):
            cfg = GenerateConfig(
                target_dir=tmp_path / "out",
                genome_inputs=[genome],
                generator_backend=backend,
            )
            assert cfg.generator_backend == backend

    def test_negative_interval(self, tmp_path):
        genome = tmp_path / "genome.fa"
        genome.write_text(">seq\nACGT\n")
        with pytest.raises(ValueError, match="interval"):
            GenerateConfig(
                target_dir=tmp_path / "out",
                genome_inputs=[genome],
                interval=-1.0,
            )

    def test_invalid_timing_model(self, tmp_path):
        genome = tmp_path / "genome.fa"
        genome.write_text(">seq\nACGT\n")
        with pytest.raises(ValueError, match="timing_model"):
            GenerateConfig(
                target_dir=tmp_path / "out",
                genome_inputs=[genome],
                timing_model="bogus",
            )

    def test_workers_must_be_positive(self, tmp_path):
        genome = tmp_path / "genome.fa"
        genome.write_text(">seq\nACGT\n")
        with pytest.raises(ValueError, match="workers"):
            GenerateConfig(
                target_dir=tmp_path / "out",
                genome_inputs=[genome],
                workers=0,
            )
