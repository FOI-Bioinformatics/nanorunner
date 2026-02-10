"""Tests for species-based simulation."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from nanopore_simulator.core.config import SimulationConfig
from nanopore_simulator.core.simulator import NanoporeSimulator
from nanopore_simulator.core.species import GenomeRef


class TestSimulatorSpeciesResolution:
    """Tests for species resolution in NanoporeSimulator."""

    def test_resolves_species_before_generation(self, tmp_path):
        """Test that species names are resolved to genome paths."""
        config = SimulationConfig(
            target_dir=tmp_path / "output",
            operation="generate",
            species_inputs=["Escherichia coli"],
            sample_type="pure",
            read_count=10,
            reads_per_file=10,
        )

        with patch(
            "nanopore_simulator.core.simulator.SpeciesResolver"
        ) as mock_resolver_cls:
            mock_resolver = MagicMock()
            mock_resolver_cls.return_value = mock_resolver

            # Mock successful resolution
            mock_ref = GenomeRef(
                "Escherichia coli", "GCF_000005845.2", "gtdb", "bacteria"
            )
            mock_resolver.resolve.return_value = mock_ref

            # Mock download returning a valid genome
            genome_path = tmp_path / "genome.fa"
            genome_path.write_text(">chr1\nATCGATCGATCG\n")

            with patch(
                "nanopore_simulator.core.simulator.download_genome",
                return_value=genome_path,
            ):
                sim = NanoporeSimulator(config, enable_monitoring=False)
                # Verify species were resolved
                mock_resolver.resolve.assert_called_with("Escherichia coli")

    def test_mock_community_resolution(self, tmp_path):
        """Test that mock communities resolve all their organisms."""
        config = SimulationConfig(
            target_dir=tmp_path / "output",
            operation="generate",
            mock_name="quick_3species",
            sample_type="mixed",
            read_count=10,
            reads_per_file=10,
        )

        with patch(
            "nanopore_simulator.core.simulator.SpeciesResolver"
        ) as mock_resolver_cls:
            mock_resolver = MagicMock()
            mock_resolver_cls.return_value = mock_resolver

            mock_ref = GenomeRef("E. coli", "GCF_000005845.2", "gtdb", "bacteria")
            mock_resolver.resolve.return_value = mock_ref

            genome_path = tmp_path / "genome.fa"
            genome_path.write_text(">chr1\nATCGATCGATCG\n")

            with patch(
                "nanopore_simulator.core.simulator.download_genome",
                return_value=genome_path,
            ):
                sim = NanoporeSimulator(config, enable_monitoring=False)
                # Should have resolved 3 species
                assert mock_resolver.resolve.call_count == 3

    def test_species_resolution_failure_raises(self, tmp_path):
        """Test that unresolvable species raises ValueError."""
        config = SimulationConfig(
            target_dir=tmp_path / "output",
            operation="generate",
            species_inputs=["Nonexistent organism"],
            sample_type="pure",
            read_count=10,
            reads_per_file=10,
        )

        with patch(
            "nanopore_simulator.core.simulator.SpeciesResolver"
        ) as mock_resolver_cls:
            mock_resolver = MagicMock()
            mock_resolver_cls.return_value = mock_resolver
            mock_resolver.resolve.return_value = None
            mock_resolver.suggest.return_value = []

            with pytest.raises(ValueError, match="Could not resolve"):
                NanoporeSimulator(config, enable_monitoring=False)

    def test_species_resolution_with_suggestions(self, tmp_path):
        """Test that suggestions are included in error message."""
        config = SimulationConfig(
            target_dir=tmp_path / "output",
            operation="generate",
            species_inputs=["Escherica coli"],  # Typo
            sample_type="pure",
            read_count=10,
            reads_per_file=10,
        )

        with patch(
            "nanopore_simulator.core.simulator.SpeciesResolver"
        ) as mock_resolver_cls:
            mock_resolver = MagicMock()
            mock_resolver_cls.return_value = mock_resolver
            mock_resolver.resolve.return_value = None
            mock_resolver.suggest.return_value = ["Escherichia coli"]

            with pytest.raises(ValueError, match="Did you mean"):
                NanoporeSimulator(config, enable_monitoring=False)

    def test_taxid_resolution(self, tmp_path):
        """Test that taxids are resolved via NCBI."""
        config = SimulationConfig(
            target_dir=tmp_path / "output",
            operation="generate",
            taxid_inputs=[562],  # E. coli taxid
            sample_type="pure",
            read_count=10,
            reads_per_file=10,
        )

        with patch(
            "nanopore_simulator.core.simulator.SpeciesResolver"
        ) as mock_resolver_cls:
            mock_resolver = MagicMock()
            mock_resolver_cls.return_value = mock_resolver

            mock_ref = GenomeRef(
                "Escherichia coli", "GCF_000005845.2", "ncbi", "bacteria"
            )
            mock_resolver.resolve_taxid.return_value = mock_ref

            genome_path = tmp_path / "genome.fa"
            genome_path.write_text(">chr1\nATCGATCGATCG\n")

            with patch(
                "nanopore_simulator.core.simulator.download_genome",
                return_value=genome_path,
            ):
                sim = NanoporeSimulator(config, enable_monitoring=False)
                mock_resolver.resolve_taxid.assert_called_with(562)

    def test_taxid_resolution_failure_raises(self, tmp_path):
        """Test that unresolvable taxid raises ValueError."""
        config = SimulationConfig(
            target_dir=tmp_path / "output",
            operation="generate",
            taxid_inputs=[999999999],  # Invalid taxid
            sample_type="pure",
            read_count=10,
            reads_per_file=10,
        )

        with patch(
            "nanopore_simulator.core.simulator.SpeciesResolver"
        ) as mock_resolver_cls:
            mock_resolver = MagicMock()
            mock_resolver_cls.return_value = mock_resolver
            mock_resolver.resolve_taxid.return_value = None

            with pytest.raises(ValueError, match="Could not resolve taxid"):
                NanoporeSimulator(config, enable_monitoring=False)

    def test_mock_with_predefined_accession(self, tmp_path):
        """Test that mock organisms with accessions skip resolution."""
        config = SimulationConfig(
            target_dir=tmp_path / "output",
            operation="generate",
            mock_name="zymo_d6300",  # Has organisms with accessions
            sample_type="mixed",
            read_count=10,
            reads_per_file=10,
        )

        with patch(
            "nanopore_simulator.core.simulator.SpeciesResolver"
        ) as mock_resolver_cls:
            mock_resolver = MagicMock()
            mock_resolver_cls.return_value = mock_resolver

            # Mock resolver for organisms without accessions
            mock_ref = GenomeRef("Test", "GCF_000000000.1", "gtdb", "bacteria")
            mock_resolver.resolve.return_value = mock_ref

            genome_path = tmp_path / "genome.fa"
            genome_path.write_text(">chr1\nATCGATCGATCG\n")

            with patch(
                "nanopore_simulator.core.simulator.download_genome",
                return_value=genome_path,
            ):
                sim = NanoporeSimulator(config, enable_monitoring=False)
                # Organisms with accessions (2 fungi) should not call resolve
                # 8 bacteria should call resolve
                assert mock_resolver.resolve.call_count == 8

    def test_abundances_from_mock_community(self, tmp_path):
        """Test that abundances are extracted from mock community."""
        config = SimulationConfig(
            target_dir=tmp_path / "output",
            operation="generate",
            mock_name="quick_3species",
            sample_type="mixed",
            read_count=10,
            reads_per_file=10,
        )

        with patch(
            "nanopore_simulator.core.simulator.SpeciesResolver"
        ) as mock_resolver_cls:
            mock_resolver = MagicMock()
            mock_resolver_cls.return_value = mock_resolver

            mock_ref = GenomeRef("Test", "GCF_000000000.1", "gtdb", "bacteria")
            mock_resolver.resolve.return_value = mock_ref

            genome_path = tmp_path / "genome.fa"
            genome_path.write_text(">chr1\nATCGATCGATCG\n")

            with patch(
                "nanopore_simulator.core.simulator.download_genome",
                return_value=genome_path,
            ):
                sim = NanoporeSimulator(config, enable_monitoring=False)
                # quick_3species has equal abundances of 1/3 each
                abundances = sim.config._resolved_abundances
                assert len(abundances) == 3
                assert all(abs(a - 1 / 3) < 0.001 for a in abundances)

    def test_equal_abundances_for_species_without_custom(self, tmp_path):
        """Test that equal abundances are assigned when not specified."""
        config = SimulationConfig(
            target_dir=tmp_path / "output",
            operation="generate",
            species_inputs=["Species A", "Species B"],
            sample_type="mixed",
            read_count=10,
            reads_per_file=10,
        )

        with patch(
            "nanopore_simulator.core.simulator.SpeciesResolver"
        ) as mock_resolver_cls:
            mock_resolver = MagicMock()
            mock_resolver_cls.return_value = mock_resolver

            mock_ref = GenomeRef("Test", "GCF_000000000.1", "gtdb", "bacteria")
            mock_resolver.resolve.return_value = mock_ref

            genome_path = tmp_path / "genome.fa"
            genome_path.write_text(">chr1\nATCGATCGATCG\n")

            with patch(
                "nanopore_simulator.core.simulator.download_genome",
                return_value=genome_path,
            ):
                sim = NanoporeSimulator(config, enable_monitoring=False)
                abundances = sim.config._resolved_abundances
                assert len(abundances) == 2
                assert all(abs(a - 0.5) < 0.001 for a in abundances)

    def test_unknown_mock_community_raises(self, tmp_path):
        """Test that unknown mock community name raises ValueError."""
        config = SimulationConfig(
            target_dir=tmp_path / "output",
            operation="generate",
            mock_name="nonexistent_mock",
            sample_type="mixed",
            read_count=10,
            reads_per_file=10,
        )

        with pytest.raises(ValueError, match="Unknown mock community"):
            NanoporeSimulator(config, enable_monitoring=False)

    def test_no_resolution_for_genome_inputs(self, tmp_path):
        """Test that genome_inputs bypasses species resolution."""
        genome_path = tmp_path / "genome.fa"
        genome_path.write_text(">chr1\nATCGATCGATCG\n")

        config = SimulationConfig(
            target_dir=tmp_path / "output",
            operation="generate",
            genome_inputs=[genome_path],
            read_count=10,
            reads_per_file=10,
        )

        with patch(
            "nanopore_simulator.core.simulator.SpeciesResolver"
        ) as mock_resolver_cls:
            sim = NanoporeSimulator(config, enable_monitoring=False)
            # Should not have instantiated resolver
            mock_resolver_cls.assert_not_called()

    def test_no_resolution_for_copy_operation(self, tmp_path):
        """Test that copy operation bypasses species resolution."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "test.fastq").write_text("@seq1\nACGT\n+\nIIII\n")

        config = SimulationConfig(
            source_dir=source_dir,
            target_dir=tmp_path / "output",
            operation="copy",
        )

        with patch(
            "nanopore_simulator.core.simulator.SpeciesResolver"
        ) as mock_resolver_cls:
            sim = NanoporeSimulator(config, enable_monitoring=False)
            # Should not have instantiated resolver
            mock_resolver_cls.assert_not_called()

    def test_offline_mode_passes_flag(self, tmp_path):
        """Test that offline_mode is forwarded to resolver and download."""
        config = SimulationConfig(
            target_dir=tmp_path / "output",
            operation="generate",
            species_inputs=["Escherichia coli"],
            sample_type="pure",
            read_count=10,
            reads_per_file=10,
            offline_mode=True,
        )

        with patch(
            "nanopore_simulator.core.simulator.SpeciesResolver"
        ) as mock_resolver_cls:
            mock_resolver = MagicMock()
            mock_resolver_cls.return_value = mock_resolver

            mock_ref = GenomeRef(
                "Escherichia coli", "GCF_000005845.2", "gtdb", "bacteria"
            )
            mock_resolver.resolve.return_value = mock_ref

            genome_path = tmp_path / "genome.fa"
            genome_path.write_text(">chr1\nATCGATCGATCG\n")

            with patch(
                "nanopore_simulator.core.simulator.download_genome",
                return_value=genome_path,
            ) as mock_download:
                sim = NanoporeSimulator(config, enable_monitoring=False)
                mock_resolver_cls.assert_called_once_with(offline=True)
                mock_download.assert_called_once_with(
                    mock_ref, mock_resolver.cache, offline=True
                )
