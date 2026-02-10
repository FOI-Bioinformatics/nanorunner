"""Tests for species resolution and genome caching"""

from unittest.mock import patch, MagicMock

import pytest

from nanopore_simulator.core.species import (
    GenomeRef,
    GenomeCache,
    GTDBIndex,
    NCBIResolver,
    SpeciesResolver,
    download_genome,
)


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

    def test_missing_index_file(self, tmp_path):
        """Test GTDBIndex with nonexistent file returns None without error."""
        index = GTDBIndex(tmp_path / "nonexistent.tsv")
        ref = index.lookup("Escherichia coli")
        assert ref is None

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
                stdout='{"accession": "GCF_000146045.2", "organism": {"organism_name": "Saccharomyces cerevisiae"}}',
            )
            ref = resolver.resolve_by_taxid(4932)
            assert ref is not None
            assert ref.accession == "GCF_000146045.2"
            assert ref.source == "ncbi"
            assert ref.domain == "eukaryota"
            assert ref.name == "Saccharomyces cerevisiae"

    def test_resolve_by_name(self, tmp_path):
        """Test resolving genome by organism name"""
        resolver = NCBIResolver()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout='{"accession": "GCF_000146045.2", "organism": {"organism_name": "Saccharomyces cerevisiae"}, "tax_id": 4932}',
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


class TestSpeciesResolver:
    """Tests for SpeciesResolver unified interface"""

    def test_resolve_gtdb_species(self, tmp_path, monkeypatch):
        """Test resolving a species found in GTDB index"""
        # Create minimal GTDB index
        index_file = tmp_path / "indexes" / "gtdb_species.tsv"
        index_file.parent.mkdir(parents=True, exist_ok=True)
        index_file.write_text(
            "species\taccession\tdomain\n"
            "Escherichia coli\tGCF_000005845.2\tbacteria\n"
        )
        monkeypatch.setenv("HOME", str(tmp_path))

        resolver = SpeciesResolver(index_dir=tmp_path / "indexes")
        ref = resolver.resolve("Escherichia coli")
        assert ref is not None
        assert ref.accession == "GCF_000005845.2"
        assert ref.source == "gtdb"

    def test_resolve_falls_back_to_ncbi(self, tmp_path, monkeypatch):
        """Test that resolution falls back to NCBI when not found in GTDB"""
        # Empty GTDB index
        index_file = tmp_path / "indexes" / "gtdb_species.tsv"
        index_file.parent.mkdir(parents=True, exist_ok=True)
        index_file.write_text("species\taccession\tdomain\n")
        monkeypatch.setenv("HOME", str(tmp_path))

        resolver = SpeciesResolver(index_dir=tmp_path / "indexes")
        with patch.object(resolver._ncbi, "resolve_by_name") as mock_ncbi:
            mock_ncbi.return_value = GenomeRef(
                "Saccharomyces cerevisiae", "GCF_000146045.2", "ncbi", "eukaryota"
            )
            ref = resolver.resolve("Saccharomyces cerevisiae")
            assert ref is not None
            assert ref.source == "ncbi"

    def test_resolve_not_found(self, tmp_path, monkeypatch):
        """Test resolution returns None when species not found in any source"""
        index_file = tmp_path / "indexes" / "gtdb_species.tsv"
        index_file.parent.mkdir(parents=True, exist_ok=True)
        index_file.write_text("species\taccession\tdomain\n")
        monkeypatch.setenv("HOME", str(tmp_path))

        resolver = SpeciesResolver(index_dir=tmp_path / "indexes")
        with patch.object(resolver._ncbi, "resolve_by_name", return_value=None):
            ref = resolver.resolve("Nonexistent organism")
            assert ref is None

    def test_resolve_taxid(self, tmp_path, monkeypatch):
        """Test resolving by NCBI taxonomy ID"""
        index_file = tmp_path / "indexes" / "gtdb_species.tsv"
        index_file.parent.mkdir(parents=True, exist_ok=True)
        index_file.write_text("species\taccession\tdomain\n")
        monkeypatch.setenv("HOME", str(tmp_path))

        resolver = SpeciesResolver(index_dir=tmp_path / "indexes")
        with patch.object(resolver._ncbi, "resolve_by_taxid") as mock_ncbi:
            mock_ncbi.return_value = GenomeRef(
                "Saccharomyces cerevisiae", "GCF_000146045.2", "ncbi", "eukaryota"
            )
            ref = resolver.resolve_taxid(4932)
            assert ref is not None
            assert ref.accession == "GCF_000146045.2"

    def test_suggest(self, tmp_path, monkeypatch):
        """Test species name suggestions from GTDB index"""
        index_file = tmp_path / "indexes" / "gtdb_species.tsv"
        index_file.parent.mkdir(parents=True, exist_ok=True)
        index_file.write_text(
            "species\taccession\tdomain\n"
            "Escherichia coli\tGCF_000005845.2\tbacteria\n"
            "Escherichia fergusonii\tGCF_000026225.1\tbacteria\n"
        )
        monkeypatch.setenv("HOME", str(tmp_path))

        resolver = SpeciesResolver(index_dir=tmp_path / "indexes")
        suggestions = resolver.suggest("Escherichia")
        assert len(suggestions) >= 1
        assert any("Escherichia" in s for s in suggestions)

    def test_cache_property(self, tmp_path, monkeypatch):
        """Test that cache property returns GenomeCache instance"""
        index_file = tmp_path / "indexes" / "gtdb_species.tsv"
        index_file.parent.mkdir(parents=True, exist_ok=True)
        index_file.write_text("species\taccession\tdomain\n")
        monkeypatch.setenv("HOME", str(tmp_path))

        resolver = SpeciesResolver(
            index_dir=tmp_path / "indexes",
            cache_dir=tmp_path / "genomes",
        )
        assert isinstance(resolver.cache, GenomeCache)
        assert resolver.cache.cache_dir == tmp_path / "genomes"

    def test_resolve_offline_skips_ncbi(self, tmp_path, monkeypatch):
        """Test that offline mode skips NCBI resolution."""
        # Empty GTDB index so lookup will miss
        index_file = tmp_path / "indexes" / "gtdb_species.tsv"
        index_file.parent.mkdir(parents=True, exist_ok=True)
        index_file.write_text("species\taccession\tdomain\n")
        monkeypatch.setenv("HOME", str(tmp_path))

        resolver = SpeciesResolver(index_dir=tmp_path / "indexes", offline=True)
        with patch.object(resolver._ncbi, "resolve_by_name") as mock_ncbi:
            ref = resolver.resolve("Saccharomyces cerevisiae")
            assert ref is None
            mock_ncbi.assert_not_called()

    def test_default_index_dir(self, tmp_path, monkeypatch):
        """Test that default index directory is used when not specified"""
        # Create default index location
        default_index = tmp_path / ".nanorunner" / "indexes" / "gtdb_species.tsv"
        default_index.parent.mkdir(parents=True, exist_ok=True)
        default_index.write_text("species\taccession\tdomain\n")
        monkeypatch.setenv("HOME", str(tmp_path))

        resolver = SpeciesResolver()
        # Should not raise, indicating default path was used
        ref = resolver.resolve("Nonexistent")
        assert ref is None


class TestGenomeDownload:
    """Tests for download_genome function"""

    def test_download_genome(self, tmp_path):
        """Test downloading a genome via datasets CLI"""
        cache = GenomeCache(cache_dir=tmp_path)
        ref = GenomeRef("E. coli", "GCF_000005845.2", "gtdb", "bacteria")

        with patch("nanopore_simulator.core.species.subprocess.run") as mock_run:
            # Simulate datasets download creating a zip
            def create_mock_download(*args, **kwargs):
                # Create the expected output structure in the temp dir
                # The function uses a tempfile.TemporaryDirectory, so we need
                # to extract the path from the command arguments
                cmd = args[0]
                # Find the --filename argument
                for i, arg in enumerate(cmd):
                    if arg == "--filename":
                        zip_path = cmd[i + 1]
                        break
                else:
                    zip_path = None

                if zip_path:
                    import zipfile
                    from pathlib import Path

                    zip_path = Path(zip_path)
                    zip_path.parent.mkdir(parents=True, exist_ok=True)

                    # Create temp dir for fna file
                    fna_content = ">chr\nATCG\n"

                    # Create zip with the expected structure
                    with zipfile.ZipFile(zip_path, "w") as zf:
                        zf.writestr(
                            "ncbi_dataset/data/GCF_000005845.2/"
                            "GCF_000005845.2_genomic.fna",
                            fna_content,
                        )

                return MagicMock(returncode=0, stdout="", stderr="")

            mock_run.side_effect = create_mock_download

            path = download_genome(ref, cache)
            assert path.exists()
            assert path.suffix == ".gz"

    def test_download_uses_cache(self, tmp_path):
        """Test that download_genome returns cached file if it exists"""
        cache = GenomeCache(cache_dir=tmp_path)
        ref = GenomeRef("E. coli", "GCF_000005845.2", "gtdb", "bacteria")

        # Pre-create cached file
        cached_path = cache.get_cached_path(ref)
        cached_path.parent.mkdir(parents=True, exist_ok=True)
        cached_path.write_text("cached")

        # Should not call subprocess
        with patch("nanopore_simulator.core.species.subprocess.run") as mock_run:
            path = download_genome(ref, cache)
            mock_run.assert_not_called()
            assert path == cached_path

    def test_download_genome_failure(self, tmp_path):
        """Test that download_genome raises error on datasets failure"""
        cache = GenomeCache(cache_dir=tmp_path)
        ref = GenomeRef("E. coli", "GCF_000005845.2", "gtdb", "bacteria")

        with patch("nanopore_simulator.core.species.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="Error: genome not found",
            )

            with pytest.raises(RuntimeError, match="Failed to download"):
                download_genome(ref, cache)

    def test_download_genome_no_fna_file(self, tmp_path):
        """Test that download_genome raises error when no .fna file found"""
        cache = GenomeCache(cache_dir=tmp_path)
        ref = GenomeRef("E. coli", "GCF_000005845.2", "gtdb", "bacteria")

        with patch("nanopore_simulator.core.species.subprocess.run") as mock_run:

            def create_empty_zip(*args, **kwargs):
                cmd = args[0]
                for i, arg in enumerate(cmd):
                    if arg == "--filename":
                        zip_path = cmd[i + 1]
                        break
                else:
                    zip_path = None

                if zip_path:
                    import zipfile
                    from pathlib import Path

                    zip_path = Path(zip_path)
                    zip_path.parent.mkdir(parents=True, exist_ok=True)

                    # Create empty zip
                    with zipfile.ZipFile(zip_path, "w") as zf:
                        zf.writestr("ncbi_dataset/README.md", "Empty dataset")

                return MagicMock(returncode=0, stdout="", stderr="")

            mock_run.side_effect = create_empty_zip

            with pytest.raises(RuntimeError, match="No .fna file found"):
                download_genome(ref, cache)

    def test_download_genome_no_datasets_cli(self, tmp_path):
        """Test error when datasets CLI is not installed."""
        cache = GenomeCache(cache_dir=tmp_path)
        ref = GenomeRef("E. coli", "GCF_000005845.2", "gtdb", "bacteria")

        with patch("nanopore_simulator.core.species.shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="ncbi-datasets-cli"):
                download_genome(ref, cache)

    def test_download_genome_offline_not_cached(self, tmp_path):
        """Test error when offline mode is enabled and genome is not cached."""
        cache = GenomeCache(cache_dir=tmp_path)
        ref = GenomeRef("E. coli", "GCF_000005845.2", "gtdb", "bacteria")

        with pytest.raises(RuntimeError, match="offline mode"):
            download_genome(ref, cache, offline=True)

    def test_download_genome_offline_cached(self, tmp_path):
        """Test that offline mode returns cached genome without error."""
        cache = GenomeCache(cache_dir=tmp_path)
        ref = GenomeRef("E. coli", "GCF_000005845.2", "gtdb", "bacteria")

        # Pre-create cached file
        cached_path = cache.get_cached_path(ref)
        cached_path.parent.mkdir(parents=True, exist_ok=True)
        cached_path.write_text("cached")

        path = download_genome(ref, cache, offline=True)
        assert path == cached_path
