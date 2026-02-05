"""Tests for species resolution and genome caching"""

from unittest.mock import patch, MagicMock

import pytest

from nanopore_simulator.core.species import GenomeRef, GenomeCache, GTDBIndex, NCBIResolver


class TestGenomeRef:
    """Tests for GenomeRef dataclass"""

    def test_create_gtdb_ref(self):
        """Test creating a GTDB genome reference"""
        ref = GenomeRef(
            name="Escherichia coli",
            accession="GCF_000005845.2",
            source="gtdb",
            domain="bacteria",
        )
        assert ref.name == "Escherichia coli"
        assert ref.accession == "GCF_000005845.2"
        assert ref.source == "gtdb"
        assert ref.domain == "bacteria"

    def test_create_ncbi_ref(self):
        """Test creating an NCBI genome reference"""
        ref = GenomeRef(
            name="Saccharomyces cerevisiae",
            accession="GCF_000146045.2",
            source="ncbi",
            domain="eukaryota",
        )
        assert ref.source == "ncbi"
        assert ref.domain == "eukaryota"

    def test_create_archaea_ref(self):
        """Test creating an archaeal genome reference"""
        ref = GenomeRef(
            name="Methanococcus jannaschii",
            accession="GCF_000091665.1",
            source="ncbi",
            domain="archaea",
        )
        assert ref.domain == "archaea"

    def test_invalid_source(self):
        """Test that invalid source values raise ValueError"""
        with pytest.raises(ValueError, match="source"):
            GenomeRef(
                name="Test",
                accession="GCF_000000000.1",
                source="invalid",
                domain="bacteria",
            )

    def test_invalid_domain(self):
        """Test that invalid domain values raise ValueError"""
        with pytest.raises(ValueError, match="domain"):
            GenomeRef(
                name="Test",
                accession="GCF_000000000.1",
                source="gtdb",
                domain="invalid",
            )


class TestGenomeCache:
    """Tests for GenomeCache class"""

    def test_cache_dir_default(self, tmp_path, monkeypatch):
        """Test default cache directory uses HOME environment variable"""
        monkeypatch.setenv("HOME", str(tmp_path))
        cache = GenomeCache()
        assert cache.cache_dir == tmp_path / ".nanorunner" / "genomes"

    def test_cache_dir_custom(self, tmp_path):
        """Test custom cache directory is used when provided"""
        cache = GenomeCache(cache_dir=tmp_path / "custom")
        assert cache.cache_dir == tmp_path / "custom"

    def test_get_cached_path_gtdb(self, tmp_path):
        """Test cached path for GTDB genome reference"""
        cache = GenomeCache(cache_dir=tmp_path)
        ref = GenomeRef("E. coli", "GCF_000005845.2", "gtdb", "bacteria")
        expected = tmp_path / "gtdb" / "GCF_000005845.2.fna.gz"
        assert cache.get_cached_path(ref) == expected

    def test_get_cached_path_ncbi(self, tmp_path):
        """Test cached path for NCBI genome reference"""
        cache = GenomeCache(cache_dir=tmp_path)
        ref = GenomeRef("S. cerevisiae", "GCF_000146045.2", "ncbi", "eukaryota")
        expected = tmp_path / "ncbi" / "GCF_000146045.2.fna.gz"
        assert cache.get_cached_path(ref) == expected

    def test_is_cached_false(self, tmp_path):
        """Test is_cached returns False when genome is not cached"""
        cache = GenomeCache(cache_dir=tmp_path)
        ref = GenomeRef("E. coli", "GCF_000005845.2", "gtdb", "bacteria")
        assert cache.is_cached(ref) is False

    def test_is_cached_true(self, tmp_path):
        """Test is_cached returns True when genome file exists"""
        cache = GenomeCache(cache_dir=tmp_path)
        ref = GenomeRef("E. coli", "GCF_000005845.2", "gtdb", "bacteria")
        # Create the cached file
        cached_path = cache.get_cached_path(ref)
        cached_path.parent.mkdir(parents=True, exist_ok=True)
        cached_path.write_text("dummy")
        assert cache.is_cached(ref) is True


class TestGTDBIndex:
    """Tests for GTDBIndex class"""

    def test_lookup_ecoli(self, tmp_path):
        """Test looking up E. coli by exact species name"""
        index_file = tmp_path / "gtdb_species.tsv"
        index_file.write_text(
            "species\taccession\tdomain\n"
            "Escherichia coli\tGCF_000005845.2\tbacteria\n"
            "Staphylococcus aureus\tGCF_000013425.1\tbacteria\n"
        )
        index = GTDBIndex(index_file)
        ref = index.lookup("Escherichia coli")
        assert ref is not None
        assert ref.accession == "GCF_000005845.2"
        assert ref.source == "gtdb"
        assert ref.domain == "bacteria"

    def test_lookup_not_found(self, tmp_path):
        """Test lookup returns None for nonexistent species"""
        index_file = tmp_path / "gtdb_species.tsv"
        index_file.write_text("species\taccession\tdomain\n")
        index = GTDBIndex(index_file)
        ref = index.lookup("Nonexistent species")
        assert ref is None

    def test_lookup_case_insensitive(self, tmp_path):
        """Test lookup is case-insensitive but preserves original name"""
        index_file = tmp_path / "gtdb_species.tsv"
        index_file.write_text(
            "species\taccession\tdomain\n"
            "Escherichia coli\tGCF_000005845.2\tbacteria\n"
        )
        index = GTDBIndex(index_file)
        ref = index.lookup("escherichia coli")
        assert ref is not None
        assert ref.name == "Escherichia coli"

    def test_fuzzy_suggestions(self, tmp_path):
        """Test suggest returns matching species names for partial input"""
        index_file = tmp_path / "gtdb_species.tsv"
        index_file.write_text(
            "species\taccession\tdomain\n"
            "Escherichia coli\tGCF_000005845.2\tbacteria\n"
            "Escherichia fergusonii\tGCF_000026225.1\tbacteria\n"
        )
        index = GTDBIndex(index_file)
        suggestions = index.suggest("Escherichia col")
        assert "Escherichia coli" in suggestions


class TestNCBIResolver:
    """Tests for NCBIResolver class"""

    def test_resolve_by_taxid(self, tmp_path):
        """Test resolving genome by NCBI taxonomy ID"""
        resolver = NCBIResolver()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout='{"accession": "GCF_000146045.2", "organism_name": "Saccharomyces cerevisiae"}'
            )
            ref = resolver.resolve_by_taxid(4932)
            assert ref is not None
            assert ref.accession == "GCF_000146045.2"
            assert ref.source == "ncbi"
            assert ref.domain == "eukaryota"

    def test_resolve_by_name(self, tmp_path):
        """Test resolving genome by organism name"""
        resolver = NCBIResolver()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout='{"accession": "GCF_000146045.2", "organism_name": "Saccharomyces cerevisiae", "tax_id": 4932}'
            )
            ref = resolver.resolve_by_name("Saccharomyces cerevisiae")
            assert ref is not None
            assert ref.name == "Saccharomyces cerevisiae"

    def test_datasets_not_available(self):
        """Test is_available returns False when datasets CLI is not installed"""
        resolver = NCBIResolver()
        with patch("shutil.which", return_value=None):
            assert resolver.is_available() is False

    def test_datasets_available(self):
        """Test is_available returns True when datasets CLI is installed"""
        resolver = NCBIResolver()
        with patch("shutil.which", return_value="/usr/bin/datasets"):
            assert resolver.is_available() is True
