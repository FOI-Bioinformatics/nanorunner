"""Tests for species resolution and genome caching"""

import json
from unittest.mock import patch, MagicMock

import pytest

from nanopore_simulator.core.species import (
    GenomeRef,
    GenomeCache,
    ResolutionCache,
    GTDBApiResolver,
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


class TestResolutionCache:
    """Tests for ResolutionCache class"""

    def test_get_returns_none_for_missing_key(self, tmp_path):
        """Test that get returns None for keys not in cache."""
        cache = ResolutionCache(cache_dir=tmp_path)
        assert cache.get("Nonexistent species") is None

    def test_put_and_get(self, tmp_path):
        """Test storing and retrieving a resolution result."""
        cache = ResolutionCache(cache_dir=tmp_path)
        ref = GenomeRef("E. coli", "GCF_000005845.2", "gtdb", "bacteria")
        cache.put("Escherichia coli", ref)

        result = cache.get("Escherichia coli")
        assert result is not None
        assert result.name == "E. coli"
        assert result.accession == "GCF_000005845.2"
        assert result.source == "gtdb"
        assert result.domain == "bacteria"

    def test_case_insensitive_lookup(self, tmp_path):
        """Test that cache keys are case-insensitive."""
        cache = ResolutionCache(cache_dir=tmp_path)
        ref = GenomeRef("E. coli", "GCF_000005845.2", "gtdb", "bacteria")
        cache.put("Escherichia Coli", ref)

        assert cache.get("escherichia coli") is not None
        assert cache.get("ESCHERICHIA COLI") is not None

    def test_persistence(self, tmp_path):
        """Test that cached data persists across instances."""
        cache1 = ResolutionCache(cache_dir=tmp_path)
        ref = GenomeRef("E. coli", "GCF_000005845.2", "gtdb", "bacteria")
        cache1.put("Escherichia coli", ref)

        # Create a new instance pointing to the same directory
        cache2 = ResolutionCache(cache_dir=tmp_path)
        result = cache2.get("Escherichia coli")
        assert result is not None
        assert result.accession == "GCF_000005845.2"

    def test_clear(self, tmp_path):
        """Test clearing all cached resolutions."""
        cache = ResolutionCache(cache_dir=tmp_path)
        ref = GenomeRef("E. coli", "GCF_000005845.2", "gtdb", "bacteria")
        cache.put("Escherichia coli", ref)
        assert cache.get("Escherichia coli") is not None

        cache.clear()
        assert cache.get("Escherichia coli") is None
        assert not cache.cache_path.exists()

    def test_corrupted_cache_file(self, tmp_path):
        """Test that a corrupted cache file is handled gracefully."""
        cache_path = tmp_path / "resolution_cache.json"
        cache_path.write_text("not valid json{{{")
        cache = ResolutionCache(cache_dir=tmp_path)
        assert cache.get("anything") is None

    def test_corrupted_entry_returns_none(self, tmp_path):
        """Test that a cache entry with missing fields returns None."""
        cache_path = tmp_path / "resolution_cache.json"
        cache_path.write_text(json.dumps({"bad entry": {"name": "only name"}}))
        cache = ResolutionCache(cache_dir=tmp_path)
        assert cache.get("bad entry") is None


class TestGTDBApiResolver:
    """Tests for GTDBApiResolver class"""

    def _mock_urlopen(self, response_data, status=200):
        """Create a mock for urllib.request.urlopen."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode("utf-8")
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        return mock_response

    def test_resolve_bacteria(self):
        """Test resolving a bacterial species via GTDB API."""
        resolver = GTDBApiResolver()

        genomes_response = [{"accession": "GCF_000005845.2"}]
        card_response = {
            "higherRanks": ["d__Bacteria", "p__Pseudomonadota"],
        }

        call_count = [0]

        def mock_urlopen(req, timeout=None):
            call_count[0] += 1
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "/genomes" in url:
                return self._mock_urlopen(genomes_response)
            elif "/card" in url:
                return self._mock_urlopen(card_response)
            return self._mock_urlopen({})

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            ref = resolver.resolve("Escherichia coli")
            assert ref is not None
            assert ref.accession == "GCF_000005845.2"
            assert ref.source == "gtdb"
            assert ref.domain == "bacteria"
            assert ref.name == "Escherichia coli"

    def test_resolve_archaea(self):
        """Test resolving an archaeal species via GTDB API."""
        resolver = GTDBApiResolver()

        genomes_response = [{"accession": "GCF_000091665.1"}]
        card_response = {
            "higherRanks": ["d__Archaea", "p__Euryarchaeota"],
        }

        def mock_urlopen(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "/genomes" in url:
                return self._mock_urlopen(genomes_response)
            elif "/card" in url:
                return self._mock_urlopen(card_response)
            return self._mock_urlopen({})

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            ref = resolver.resolve("Methanococcus jannaschii")
            assert ref is not None
            assert ref.domain == "archaea"

    def test_resolve_not_found(self):
        """Test resolve returns None for species not in GTDB."""
        resolver = GTDBApiResolver()

        import urllib.error

        def mock_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(
                str(req), 404, "Not Found", {}, None
            )

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            ref = resolver.resolve("Nonexistent species")
            assert ref is None

    def test_resolve_empty_genomes(self):
        """Test resolve returns None when genomes list is empty."""
        resolver = GTDBApiResolver()

        def mock_urlopen(req, timeout=None):
            return self._mock_urlopen([])

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            ref = resolver.resolve("Escherichia coli")
            assert ref is None

    def test_resolve_string_accession(self):
        """Test resolve handles string accession format."""
        resolver = GTDBApiResolver()

        genomes_response = ["GCF_000005845.2"]
        card_response = {"higherRanks": ["d__Bacteria"]}

        def mock_urlopen(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "/genomes" in url:
                return self._mock_urlopen(genomes_response)
            elif "/card" in url:
                return self._mock_urlopen(card_response)
            return self._mock_urlopen({})

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            ref = resolver.resolve("Escherichia coli")
            assert ref is not None
            assert ref.accession == "GCF_000005845.2"

    def test_retry_on_server_error(self):
        """Test that transient server errors are retried."""
        resolver = GTDBApiResolver()
        resolver.RETRY_BACKOFF = 0.0  # speed up test

        import urllib.error

        call_count = [0]

        def mock_urlopen(req, timeout=None):
            call_count[0] += 1
            if call_count[0] <= 2:
                raise urllib.error.HTTPError(
                    str(req), 500, "Server Error", {}, None
                )
            return self._mock_urlopen([{"accession": "GCF_000005845.2"}])

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            result = resolver._request("/test")
            assert result is not None
            assert call_count[0] == 3

    def test_suggest(self):
        """Test species name suggestions from search endpoint."""
        resolver = GTDBApiResolver()

        search_response = {
            "rows": [
                {
                    "gtdbTaxonomy": "d__Bacteria;p__Pseudomonadota;c__Gammaproteobacteria;o__Enterobacterales;f__Enterobacteriaceae;g__Escherichia;s__Escherichia coli",
                    "accession": "GCF_000005845.2",
                    "isGtdbSpeciesRep": True,
                },
                {
                    "gtdbTaxonomy": "d__Bacteria;p__Pseudomonadota;c__Gammaproteobacteria;o__Enterobacterales;f__Enterobacteriaceae;g__Escherichia;s__Escherichia fergusonii",
                    "accession": "GCF_000026225.1",
                    "isGtdbSpeciesRep": True,
                },
            ]
        }

        def mock_urlopen(req, timeout=None):
            return self._mock_urlopen(search_response)

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            suggestions = resolver.suggest("Escherichia")
            assert "Escherichia coli" in suggestions
            assert "Escherichia fergusonii" in suggestions

    def test_suggest_empty_results(self):
        """Test suggest returns empty list when no matches found."""
        resolver = GTDBApiResolver()

        import urllib.error

        def mock_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(
                str(req), 404, "Not Found", {}, None
            )

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            suggestions = resolver.suggest("Nonexistent")
            assert suggestions == []

    def test_network_failure_returns_none(self):
        """Test that network failures return None after retries."""
        resolver = GTDBApiResolver()
        resolver.RETRY_BACKOFF = 0.0

        import urllib.error

        def mock_urlopen(req, timeout=None):
            raise urllib.error.URLError("Connection refused")

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            ref = resolver.resolve("Escherichia coli")
            assert ref is None


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

    def test_resolve_by_taxid_bacteria(self, tmp_path):
        """Test resolving a bacterial genome by taxonomy ID."""
        resolver = NCBIResolver()
        json_line = json.dumps({
            "accession": "GCF_000005845.2",
            "organism": {
                "organism_name": "Escherichia coli",
                "lineage": [{"tax_id": 2}],
            },
            "assembly_info": {"assembly_level": "Complete Genome"},
        })
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json_line,
            )
            ref = resolver.resolve_by_taxid(562)
            assert ref is not None
            assert ref.accession == "GCF_000005845.2"
            assert ref.source == "ncbi"
            assert ref.domain == "bacteria"
            assert ref.name == "Escherichia coli"

            # Verify --reference is NOT used, --assembly-source refseq IS used
            cmd = mock_run.call_args[0][0]
            assert "--reference" not in cmd
            assert "--assembly-source" in cmd
            assert "refseq" in cmd

    def test_resolve_by_taxid_eukaryote(self, tmp_path):
        """Test resolving a eukaryotic genome detects domain correctly."""
        resolver = NCBIResolver()
        json_line = json.dumps({
            "accession": "GCF_000146045.2",
            "organism": {
                "organism_name": "Saccharomyces cerevisiae",
                "lineage": [{"tax_id": 2759}],
            },
            "assembly_info": {"assembly_level": "Complete Genome"},
        })
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json_line,
            )
            ref = resolver.resolve_by_taxid(4932)
            assert ref is not None
            assert ref.domain == "eukaryota"
            assert ref.name == "Saccharomyces cerevisiae"

    def test_resolve_by_name(self, tmp_path):
        """Test resolving genome by organism name"""
        resolver = NCBIResolver()
        json_line = json.dumps({
            "accession": "GCF_000146045.2",
            "organism": {
                "organism_name": "Saccharomyces cerevisiae",
                "lineage": [{"tax_id": 2759}],
            },
            "assembly_info": {"assembly_level": "Complete Genome"},
        })
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json_line,
            )
            ref = resolver.resolve_by_name("Saccharomyces cerevisiae")
            assert ref is not None
            assert ref.name == "Saccharomyces cerevisiae"
            assert ref.domain == "eukaryota"

            # Verify --reference is NOT used
            cmd = mock_run.call_args[0][0]
            assert "--reference" not in cmd

    def test_resolve_by_name_bacteria(self, tmp_path):
        """Test that bacteria domain is detected from lineage."""
        resolver = NCBIResolver()
        json_line = json.dumps({
            "accession": "GCF_000005845.2",
            "organism": {
                "organism_name": "Escherichia coli",
                "lineage": [{"tax_id": 2}],
            },
        })
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json_line,
            )
            ref = resolver.resolve_by_name("Escherichia coli")
            assert ref is not None
            assert ref.domain == "bacteria"

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

    def test_pick_best_assembly(self):
        """Test that the best assembly level is selected."""
        resolver = NCBIResolver()
        lines = [
            json.dumps({
                "accession": "GCF_scaffold",
                "assembly_info": {"assembly_level": "Scaffold"},
            }),
            json.dumps({
                "accession": "GCF_complete",
                "assembly_info": {"assembly_level": "Complete Genome"},
            }),
            json.dumps({
                "accession": "GCF_contig",
                "assembly_info": {"assembly_level": "Contig"},
            }),
        ]
        result = resolver._pick_best_assembly(lines)
        assert result is not None
        assert result["accession"] == "GCF_complete"

    def test_detect_domain_from_lineage(self):
        """Test domain detection from taxonomy lineage."""
        resolver = NCBIResolver()
        assert resolver._detect_domain({
            "organism": {"lineage": [{"tax_id": 2}]}
        }) == "bacteria"
        assert resolver._detect_domain({
            "organism": {"lineage": [{"tax_id": 2157}]}
        }) == "archaea"
        assert resolver._detect_domain({
            "organism": {"lineage": [{"tax_id": 2759}]}
        }) == "eukaryota"

    def test_detect_domain_heuristic(self):
        """Test domain detection falls back to organism name heuristic."""
        resolver = NCBIResolver()
        assert resolver._detect_domain({
            "organism": {"organism_name": "Saccharomyces cerevisiae"}
        }) == "eukaryota"
        assert resolver._detect_domain({
            "organism": {"organism_name": "Candida albicans"}
        }) == "eukaryota"

    def test_detect_domain_default(self):
        """Test domain detection defaults to bacteria."""
        resolver = NCBIResolver()
        assert resolver._detect_domain({}) == "bacteria"
        assert resolver._detect_domain({"organism": {}}) == "bacteria"


class TestSpeciesResolver:
    """Tests for SpeciesResolver unified interface"""

    def test_resolve_from_resolution_cache(self, tmp_path, monkeypatch):
        """Test that resolution cache is checked first."""
        index_file = tmp_path / "indexes" / "gtdb_species.tsv"
        index_file.parent.mkdir(parents=True, exist_ok=True)
        index_file.write_text("species\taccession\tdomain\n")
        monkeypatch.setenv("HOME", str(tmp_path))

        resolver = SpeciesResolver(index_dir=tmp_path / "indexes")

        # Pre-populate resolution cache
        ref = GenomeRef("E. coli", "GCF_cached", "gtdb", "bacteria")
        resolver._resolution_cache.put("Escherichia coli", ref)

        result = resolver.resolve("Escherichia coli")
        assert result is not None
        assert result.accession == "GCF_cached"

    def test_resolve_gtdb_index(self, tmp_path, monkeypatch):
        """Test resolving a species found in GTDB local index."""
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

    def test_resolve_gtdb_api_fallback(self, tmp_path, monkeypatch):
        """Test that GTDB API is tried when local index misses."""
        index_file = tmp_path / "indexes" / "gtdb_species.tsv"
        index_file.parent.mkdir(parents=True, exist_ok=True)
        index_file.write_text("species\taccession\tdomain\n")
        monkeypatch.setenv("HOME", str(tmp_path))

        resolver = SpeciesResolver(index_dir=tmp_path / "indexes")
        api_ref = GenomeRef(
            "Escherichia coli", "GCF_from_api", "gtdb", "bacteria"
        )
        with patch.object(resolver._gtdb_api, "resolve", return_value=api_ref):
            ref = resolver.resolve("Escherichia coli")
            assert ref is not None
            assert ref.accession == "GCF_from_api"
            assert ref.source == "gtdb"

    def test_resolve_ncbi_fallback(self, tmp_path, monkeypatch):
        """Test that NCBI is tried when GTDB sources miss."""
        index_file = tmp_path / "indexes" / "gtdb_species.tsv"
        index_file.parent.mkdir(parents=True, exist_ok=True)
        index_file.write_text("species\taccession\tdomain\n")
        monkeypatch.setenv("HOME", str(tmp_path))

        resolver = SpeciesResolver(index_dir=tmp_path / "indexes")
        with patch.object(resolver._gtdb_api, "resolve", return_value=None):
            with patch.object(resolver._ncbi, "resolve_by_name") as mock_ncbi:
                mock_ncbi.return_value = GenomeRef(
                    "Saccharomyces cerevisiae",
                    "GCF_000146045.2",
                    "ncbi",
                    "eukaryota",
                )
                ref = resolver.resolve("Saccharomyces cerevisiae")
                assert ref is not None
                assert ref.source == "ncbi"

    def test_resolve_caches_result(self, tmp_path, monkeypatch):
        """Test that resolved results are cached."""
        index_file = tmp_path / "indexes" / "gtdb_species.tsv"
        index_file.parent.mkdir(parents=True, exist_ok=True)
        index_file.write_text("species\taccession\tdomain\n")
        monkeypatch.setenv("HOME", str(tmp_path))

        resolver = SpeciesResolver(index_dir=tmp_path / "indexes")
        api_ref = GenomeRef("E. coli", "GCF_from_api", "gtdb", "bacteria")
        with patch.object(resolver._gtdb_api, "resolve", return_value=api_ref):
            resolver.resolve("Escherichia coli")

        # Second call should hit cache, not API
        with patch.object(resolver._gtdb_api, "resolve") as mock_api:
            ref = resolver.resolve("Escherichia coli")
            assert ref is not None
            assert ref.accession == "GCF_from_api"
            mock_api.assert_not_called()

    def test_resolve_not_found(self, tmp_path, monkeypatch):
        """Test resolution returns None when species not found anywhere."""
        index_file = tmp_path / "indexes" / "gtdb_species.tsv"
        index_file.parent.mkdir(parents=True, exist_ok=True)
        index_file.write_text("species\taccession\tdomain\n")
        monkeypatch.setenv("HOME", str(tmp_path))

        resolver = SpeciesResolver(index_dir=tmp_path / "indexes")
        with patch.object(resolver._gtdb_api, "resolve", return_value=None):
            with patch.object(
                resolver._ncbi, "resolve_by_name", return_value=None
            ):
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

    def test_suggest_gtdb_api_first(self, tmp_path, monkeypatch):
        """Test that suggest tries GTDB API first when online."""
        index_file = tmp_path / "indexes" / "gtdb_species.tsv"
        index_file.parent.mkdir(parents=True, exist_ok=True)
        index_file.write_text(
            "species\taccession\tdomain\n"
            "Escherichia coli\tGCF_000005845.2\tbacteria\n"
        )
        monkeypatch.setenv("HOME", str(tmp_path))

        resolver = SpeciesResolver(index_dir=tmp_path / "indexes")
        with patch.object(
            resolver._gtdb_api,
            "suggest",
            return_value=["Escherichia coli", "Escherichia fergusonii"],
        ):
            suggestions = resolver.suggest("Escherichia")
            assert "Escherichia coli" in suggestions
            assert "Escherichia fergusonii" in suggestions

    def test_suggest_falls_back_to_index(self, tmp_path, monkeypatch):
        """Test that suggest falls back to local index when API returns empty."""
        index_file = tmp_path / "indexes" / "gtdb_species.tsv"
        index_file.parent.mkdir(parents=True, exist_ok=True)
        index_file.write_text(
            "species\taccession\tdomain\n"
            "Escherichia coli\tGCF_000005845.2\tbacteria\n"
        )
        monkeypatch.setenv("HOME", str(tmp_path))

        resolver = SpeciesResolver(index_dir=tmp_path / "indexes")
        with patch.object(resolver._gtdb_api, "suggest", return_value=[]):
            suggestions = resolver.suggest("Escherichia")
            assert "Escherichia coli" in suggestions

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

    def test_resolve_offline_skips_network(self, tmp_path, monkeypatch):
        """Test that offline mode skips GTDB API and NCBI resolution."""
        index_file = tmp_path / "indexes" / "gtdb_species.tsv"
        index_file.parent.mkdir(parents=True, exist_ok=True)
        index_file.write_text("species\taccession\tdomain\n")
        monkeypatch.setenv("HOME", str(tmp_path))

        resolver = SpeciesResolver(index_dir=tmp_path / "indexes", offline=True)
        with patch.object(resolver._gtdb_api, "resolve") as mock_api:
            with patch.object(resolver._ncbi, "resolve_by_name") as mock_ncbi:
                ref = resolver.resolve("Saccharomyces cerevisiae")
                assert ref is None
                mock_api.assert_not_called()
                mock_ncbi.assert_not_called()

    def test_offline_suggest_skips_api(self, tmp_path, monkeypatch):
        """Test that offline suggest only uses local index."""
        index_file = tmp_path / "indexes" / "gtdb_species.tsv"
        index_file.parent.mkdir(parents=True, exist_ok=True)
        index_file.write_text(
            "species\taccession\tdomain\n"
            "Escherichia coli\tGCF_000005845.2\tbacteria\n"
        )
        monkeypatch.setenv("HOME", str(tmp_path))

        resolver = SpeciesResolver(index_dir=tmp_path / "indexes", offline=True)
        with patch.object(resolver._gtdb_api, "suggest") as mock_api:
            suggestions = resolver.suggest("Escherichia")
            mock_api.assert_not_called()
            assert "Escherichia coli" in suggestions

    def test_default_index_dir(self, tmp_path, monkeypatch):
        """Test that default index directory is used when not specified"""
        default_index = tmp_path / ".nanorunner" / "indexes" / "gtdb_species.tsv"
        default_index.parent.mkdir(parents=True, exist_ok=True)
        default_index.write_text("species\taccession\tdomain\n")
        monkeypatch.setenv("HOME", str(tmp_path))

        resolver = SpeciesResolver()
        # Should not raise, indicating default path was used
        with patch.object(resolver._gtdb_api, "resolve", return_value=None):
            with patch.object(
                resolver._ncbi, "resolve_by_name", return_value=None
            ):
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
