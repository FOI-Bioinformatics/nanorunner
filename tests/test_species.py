"""Tests for species resolution and genome caching."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nanopore_simulator.species import (
    VALID_DOMAINS,
    VALID_SOURCES,
    GenomeCache,
    GenomeRef,
    ResolutionCache,
    download_genome,
    resolve_species,
    resolve_taxid,
)


# ---------------------------------------------------------------------------
# GenomeRef
# ---------------------------------------------------------------------------


class TestGenomeRef:
    """GenomeRef dataclass validation."""

    def test_valid_creation(self) -> None:
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

    def test_valid_ncbi_source(self) -> None:
        ref = GenomeRef(
            name="S. cerevisiae",
            accession="GCF_000146045.2",
            source="ncbi",
            domain="eukaryota",
        )
        assert ref.source == "ncbi"

    def test_valid_archaea_domain(self) -> None:
        ref = GenomeRef(
            name="Halobacterium salinarum",
            accession="GCF_000006805.1",
            source="gtdb",
            domain="archaea",
        )
        assert ref.domain == "archaea"

    def test_invalid_source_raises(self) -> None:
        with pytest.raises(ValueError, match="source must be one of"):
            GenomeRef(
                name="Test", accession="GCF_123", source="unknown", domain="bacteria"
            )

    def test_invalid_domain_raises(self) -> None:
        with pytest.raises(ValueError, match="domain must be one of"):
            GenomeRef(name="Test", accession="GCF_123", source="gtdb", domain="virus")

    def test_all_valid_sources(self) -> None:
        for src in VALID_SOURCES:
            ref = GenomeRef(name="X", accession="A", source=src, domain="bacteria")
            assert ref.source == src

    def test_all_valid_domains(self) -> None:
        for dom in VALID_DOMAINS:
            ref = GenomeRef(name="X", accession="A", source="gtdb", domain=dom)
            assert ref.domain == dom


# ---------------------------------------------------------------------------
# GenomeCache
# ---------------------------------------------------------------------------


class TestGenomeCache:
    """Genome file cache on disk."""

    def test_default_cache_dir(self, tmp_path: Path) -> None:
        with patch.dict("os.environ", {"HOME": str(tmp_path)}):
            cache = GenomeCache()
            assert ".nanorunner" in str(cache.cache_dir)
            assert "genomes" in str(cache.cache_dir)

    def test_custom_cache_dir(self, tmp_path: Path) -> None:
        cache = GenomeCache(cache_dir=tmp_path / "my_cache")
        assert cache.cache_dir == tmp_path / "my_cache"

    def test_get_cached_path(self, tmp_path: Path) -> None:
        cache = GenomeCache(cache_dir=tmp_path)
        ref = GenomeRef(
            name="E. coli",
            accession="GCF_000005845.2",
            source="gtdb",
            domain="bacteria",
        )
        path = cache.get_cached_path(ref)
        assert path == tmp_path / "gtdb" / "GCF_000005845.2.fna.gz"

    def test_is_cached_false_when_missing(self, tmp_path: Path) -> None:
        cache = GenomeCache(cache_dir=tmp_path)
        ref = GenomeRef(
            name="E. coli",
            accession="GCF_000005845.2",
            source="gtdb",
            domain="bacteria",
        )
        assert cache.is_cached(ref) is False

    def test_is_cached_true_when_present(self, tmp_path: Path) -> None:
        cache = GenomeCache(cache_dir=tmp_path)
        ref = GenomeRef(
            name="E. coli",
            accession="GCF_000005845.2",
            source="gtdb",
            domain="bacteria",
        )
        cached_path = cache.get_cached_path(ref)
        cached_path.parent.mkdir(parents=True, exist_ok=True)
        cached_path.write_text("fake genome")
        assert cache.is_cached(ref) is True

    def test_ncbi_source_path(self, tmp_path: Path) -> None:
        cache = GenomeCache(cache_dir=tmp_path)
        ref = GenomeRef(
            name="S. cerevisiae",
            accession="GCF_000146045.2",
            source="ncbi",
            domain="eukaryota",
        )
        path = cache.get_cached_path(ref)
        assert "ncbi" in str(path)


# ---------------------------------------------------------------------------
# ResolutionCache
# ---------------------------------------------------------------------------


class TestResolutionCache:
    """Resolution cache for species name lookups."""

    def test_put_and_get(self, tmp_path: Path) -> None:
        cache = ResolutionCache(cache_dir=tmp_path)
        ref = GenomeRef(
            name="E. coli",
            accession="GCF_000005845.2",
            source="gtdb",
            domain="bacteria",
        )
        cache.put("Escherichia coli", ref)
        result = cache.get("Escherichia coli")
        assert result is not None
        assert result.accession == "GCF_000005845.2"

    def test_get_missing_returns_none(self, tmp_path: Path) -> None:
        cache = ResolutionCache(cache_dir=tmp_path)
        assert cache.get("Nonexistent species") is None

    def test_case_insensitive_lookup(self, tmp_path: Path) -> None:
        cache = ResolutionCache(cache_dir=tmp_path)
        ref = GenomeRef(
            name="E. coli",
            accession="GCF_000005845.2",
            source="gtdb",
            domain="bacteria",
        )
        cache.put("Escherichia Coli", ref)
        result = cache.get("escherichia coli")
        assert result is not None
        assert result.accession == "GCF_000005845.2"

    def test_persistence(self, tmp_path: Path) -> None:
        ref = GenomeRef(
            name="E. coli",
            accession="GCF_000005845.2",
            source="gtdb",
            domain="bacteria",
        )
        cache1 = ResolutionCache(cache_dir=tmp_path)
        cache1.put("E. coli", ref)

        # Create a new instance reading from the same directory
        cache2 = ResolutionCache(cache_dir=tmp_path)
        result = cache2.get("E. coli")
        assert result is not None
        assert result.accession == "GCF_000005845.2"

    def test_clear(self, tmp_path: Path) -> None:
        cache = ResolutionCache(cache_dir=tmp_path)
        ref = GenomeRef(
            name="E. coli",
            accession="GCF_000005845.2",
            source="gtdb",
            domain="bacteria",
        )
        cache.put("E. coli", ref)
        cache.clear()
        assert cache.get("E. coli") is None

    def test_corrupted_cache_file(self, tmp_path: Path) -> None:
        # Write invalid JSON to the cache file
        cache_file = tmp_path / "resolution_cache.json"
        cache_file.write_text("not json {{{")
        cache = ResolutionCache(cache_dir=tmp_path)
        # Should start fresh instead of crashing
        assert cache.get("anything") is None


# ---------------------------------------------------------------------------
# resolve_species (mocked GTDB)
# ---------------------------------------------------------------------------


class TestResolveSpecies:
    """Species name resolution with mocked backends."""

    def test_resolve_species_via_gtdb_api(self, tmp_path: Path) -> None:
        genome_list = [{"accession": "GCF_000005845.2", "gid": "GCF_000005845.2"}]
        card_data = {"higherRanks": ["d__Bacteria", "p__Proteobacteria"]}

        def mock_urlopen(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            mm = MagicMock()
            if "genomes" in url:
                mm.read.return_value = json.dumps(genome_list).encode()
            else:
                mm.read.return_value = json.dumps(card_data).encode()
            mm.__enter__ = lambda s: mm
            mm.__exit__ = MagicMock(return_value=False)
            return mm

        with patch(
            "nanopore_simulator.species.urllib.request.urlopen",
            side_effect=mock_urlopen,
        ):
            ref = resolve_species(
                "Escherichia coli",
                cache=GenomeCache(cache_dir=tmp_path / "genomes"),
                resolution_cache_dir=tmp_path / "resolutions",
            )

        assert ref is not None
        assert ref.accession == "GCF_000005845.2"
        assert ref.domain == "bacteria"

    def test_resolve_species_from_cache(self, tmp_path: Path) -> None:
        # Pre-populate the resolution cache
        rc = ResolutionCache(cache_dir=tmp_path / "resolutions")
        ref = GenomeRef(
            name="E. coli",
            accession="GCF_000005845.2",
            source="gtdb",
            domain="bacteria",
        )
        rc.put("Escherichia coli", ref)

        result = resolve_species(
            "Escherichia coli",
            cache=GenomeCache(cache_dir=tmp_path / "genomes"),
            resolution_cache_dir=tmp_path / "resolutions",
        )
        assert result is not None
        assert result.accession == "GCF_000005845.2"

    def test_resolve_species_offline_cache_miss(self, tmp_path: Path) -> None:
        result = resolve_species(
            "Nonexistent species",
            offline=True,
            cache=GenomeCache(cache_dir=tmp_path / "genomes"),
            resolution_cache_dir=tmp_path / "resolutions",
        )
        assert result is None

    def test_resolve_species_offline_cache_hit(self, tmp_path: Path) -> None:
        rc = ResolutionCache(cache_dir=tmp_path / "resolutions")
        ref = GenomeRef(
            name="E. coli",
            accession="GCF_000005845.2",
            source="gtdb",
            domain="bacteria",
        )
        rc.put("Escherichia coli", ref)

        result = resolve_species(
            "Escherichia coli",
            offline=True,
            cache=GenomeCache(cache_dir=tmp_path / "genomes"),
            resolution_cache_dir=tmp_path / "resolutions",
        )
        assert result is not None

    def test_resolve_species_gtdb_not_found_falls_to_ncbi(self, tmp_path: Path) -> None:
        """When GTDB returns nothing, NCBI is tried via datasets CLI."""
        import urllib.error

        def mock_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(
                url="http://gtdb",
                code=404,
                msg="Not found",
                hdrs=None,
                fp=None,
            )

        ncbi_output = json.dumps(
            {
                "accession": "GCF_000146045.2",
                "organism": {
                    "organism_name": "Saccharomyces cerevisiae",
                    "lineage": [{"tax_id": 2759}],
                },
                "assembly_info": {"assembly_level": "Complete Genome"},
            }
        )

        mock_run_result = MagicMock(returncode=0, stdout=ncbi_output, stderr="")

        with patch(
            "nanopore_simulator.species.urllib.request.urlopen",
            side_effect=mock_urlopen,
        ):
            with patch(
                "nanopore_simulator.species.shutil.which",
                return_value="/usr/bin/datasets",
            ):
                with patch(
                    "nanopore_simulator.species.subprocess.run",
                    return_value=mock_run_result,
                ):
                    ref = resolve_species(
                        "Saccharomyces cerevisiae",
                        cache=GenomeCache(cache_dir=tmp_path / "genomes"),
                        resolution_cache_dir=tmp_path / "resolutions",
                    )

        assert ref is not None
        assert ref.source == "ncbi"
        assert ref.domain == "eukaryota"

    def test_resolve_species_domain_hint_skips_gtdb(self, tmp_path: Path) -> None:
        """When domain=eukaryota, GTDB is skipped and NCBI is used directly."""
        ncbi_output = json.dumps(
            {
                "accession": "GCF_000146045.2",
                "organism": {
                    "organism_name": "Saccharomyces cerevisiae",
                    "lineage": [{"tax_id": 2759}],
                },
                "assembly_info": {"assembly_level": "Complete Genome"},
            }
        )
        mock_run_result = MagicMock(returncode=0, stdout=ncbi_output, stderr="")

        with patch(
            "nanopore_simulator.species.shutil.which", return_value="/usr/bin/datasets"
        ):
            with patch(
                "nanopore_simulator.species.subprocess.run",
                return_value=mock_run_result,
            ):
                ref = resolve_species(
                    "Saccharomyces cerevisiae",
                    domain="eukaryota",
                    cache=GenomeCache(cache_dir=tmp_path / "genomes"),
                    resolution_cache_dir=tmp_path / "resolutions",
                )

        assert ref is not None
        assert ref.domain == "eukaryota"


# ---------------------------------------------------------------------------
# resolve_taxid (mocked NCBI)
# ---------------------------------------------------------------------------


class TestResolveTaxid:
    """Taxonomy ID resolution with mocked NCBI."""

    def test_resolve_taxid_success(self, tmp_path: Path) -> None:
        ncbi_output = json.dumps(
            {
                "accession": "GCF_000005845.2",
                "organism": {
                    "organism_name": "Escherichia coli",
                    "lineage": [{"tax_id": 2}],
                },
                "assembly_info": {"assembly_level": "Complete Genome"},
            }
        )
        mock_result = MagicMock(returncode=0, stdout=ncbi_output, stderr="")

        with patch(
            "nanopore_simulator.species.shutil.which", return_value="/usr/bin/datasets"
        ):
            with patch(
                "nanopore_simulator.species.subprocess.run", return_value=mock_result
            ):
                ref = resolve_taxid(
                    562,
                    cache=GenomeCache(cache_dir=tmp_path / "genomes"),
                    resolution_cache_dir=tmp_path / "resolutions",
                )

        assert ref is not None
        assert ref.name == "Escherichia coli"
        assert ref.domain == "bacteria"

    def test_resolve_taxid_offline(self, tmp_path: Path) -> None:
        result = resolve_taxid(
            562,
            offline=True,
            cache=GenomeCache(cache_dir=tmp_path / "genomes"),
            resolution_cache_dir=tmp_path / "resolutions",
        )
        assert result is None

    def test_resolve_taxid_datasets_not_installed(self, tmp_path: Path) -> None:
        with patch("nanopore_simulator.species.shutil.which", return_value=None):
            result = resolve_taxid(
                562,
                cache=GenomeCache(cache_dir=tmp_path / "genomes"),
                resolution_cache_dir=tmp_path / "resolutions",
            )
        assert result is None

    def test_resolve_taxid_subprocess_fails(self, tmp_path: Path) -> None:
        mock_result = MagicMock(returncode=1, stdout="", stderr="error")

        with patch(
            "nanopore_simulator.species.shutil.which", return_value="/usr/bin/datasets"
        ):
            with patch(
                "nanopore_simulator.species.subprocess.run", return_value=mock_result
            ):
                result = resolve_taxid(
                    99999999,
                    cache=GenomeCache(cache_dir=tmp_path / "genomes"),
                    resolution_cache_dir=tmp_path / "resolutions",
                )
        assert result is None


# ---------------------------------------------------------------------------
# download_genome
# ---------------------------------------------------------------------------


class TestDownloadGenome:
    """Genome download and caching."""

    def test_cache_hit_returns_existing(self, tmp_path: Path) -> None:
        cache = GenomeCache(cache_dir=tmp_path)
        ref = GenomeRef(
            name="E. coli",
            accession="GCF_000005845.2",
            source="gtdb",
            domain="bacteria",
        )
        # Pre-populate the cache
        cached_path = cache.get_cached_path(ref)
        cached_path.parent.mkdir(parents=True, exist_ok=True)
        cached_path.write_text("fake genome data")

        result = download_genome(ref, cache=cache)
        assert result == cached_path

    def test_offline_not_cached_raises(self, tmp_path: Path) -> None:
        cache = GenomeCache(cache_dir=tmp_path)
        ref = GenomeRef(
            name="E. coli",
            accession="GCF_000005845.2",
            source="gtdb",
            domain="bacteria",
        )
        with pytest.raises(RuntimeError, match="not cached"):
            download_genome(ref, cache=cache, offline=True)

    def test_datasets_not_installed_raises(self, tmp_path: Path) -> None:
        cache = GenomeCache(cache_dir=tmp_path)
        ref = GenomeRef(
            name="E. coli",
            accession="GCF_000005845.2",
            source="gtdb",
            domain="bacteria",
        )
        with patch("nanopore_simulator.species.shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="datasets"):
                download_genome(ref, cache=cache)

    def test_download_success(self, tmp_path: Path) -> None:
        cache = GenomeCache(cache_dir=tmp_path / "genomes")
        ref = GenomeRef(
            name="E. coli",
            accession="GCF_000005845.2",
            source="gtdb",
            domain="bacteria",
        )

        import zipfile

        def run_side_effect(*args, **kwargs):
            # Simulate datasets download: create a zip with an .fna file
            cmd = args[0]
            zip_path = None
            for i, arg in enumerate(cmd):
                if arg == "--filename" and i + 1 < len(cmd):
                    zip_path = Path(cmd[i + 1])
                    break
            if zip_path:
                zip_path.parent.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(zip_path, "w") as zf:
                    zf.writestr(
                        "ncbi_dataset/data/GCF_000005845.2/genome.fna",
                        ">chr1\nACGTACGT\n",
                    )
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch(
            "nanopore_simulator.species.shutil.which", return_value="/usr/bin/datasets"
        ):
            with patch(
                "nanopore_simulator.species.subprocess.run", side_effect=run_side_effect
            ):
                result = download_genome(ref, cache=cache)

        assert result.exists()
        assert result.name.endswith(".fna.gz")

    def test_download_subprocess_failure(self, tmp_path: Path) -> None:
        cache = GenomeCache(cache_dir=tmp_path / "genomes")
        ref = GenomeRef(
            name="E. coli",
            accession="GCF_000005845.2",
            source="gtdb",
            domain="bacteria",
        )
        mock_result = MagicMock(returncode=1, stdout="", stderr="download failed")

        with patch(
            "nanopore_simulator.species.shutil.which", return_value="/usr/bin/datasets"
        ):
            with patch(
                "nanopore_simulator.species.subprocess.run", return_value=mock_result
            ):
                with pytest.raises(RuntimeError, match="Failed to download"):
                    download_genome(ref, cache=cache)


# ---------------------------------------------------------------------------
# Domain detection helper
# ---------------------------------------------------------------------------


class TestDetectDomain:
    """Domain detection from NCBI datasets JSON."""

    def test_detect_bacteria_from_lineage(self) -> None:
        from nanopore_simulator.species import _detect_domain

        data = {"organism": {"lineage": [{"tax_id": 2}]}}
        assert _detect_domain(data) == "bacteria"

    def test_detect_archaea_from_lineage(self) -> None:
        from nanopore_simulator.species import _detect_domain

        data = {"organism": {"lineage": [{"tax_id": 2157}]}}
        assert _detect_domain(data) == "archaea"

    def test_detect_eukaryota_from_lineage(self) -> None:
        from nanopore_simulator.species import _detect_domain

        data = {"organism": {"lineage": [{"tax_id": 2759}]}}
        assert _detect_domain(data) == "eukaryota"

    def test_detect_eukaryota_from_name_heuristic(self) -> None:
        from nanopore_simulator.species import _detect_domain

        data = {
            "organism": {"organism_name": "Saccharomyces cerevisiae", "lineage": []}
        }
        assert _detect_domain(data) == "eukaryota"

    def test_defaults_to_bacteria(self) -> None:
        from nanopore_simulator.species import _detect_domain

        data = {"organism": {"organism_name": "Unknown org", "lineage": []}}
        assert _detect_domain(data) == "bacteria"


# ---------------------------------------------------------------------------
# Assembly selection
# ---------------------------------------------------------------------------


class TestPickBestAssembly:
    """Assembly ranking from multiple JSON lines."""

    def test_single_candidate(self) -> None:
        from nanopore_simulator.species import _pick_best_assembly

        lines = [
            json.dumps(
                {
                    "accession": "GCF_001",
                    "assembly_info": {"assembly_level": "Scaffold"},
                }
            )
        ]
        result = _pick_best_assembly(lines)
        assert result is not None
        assert result["accession"] == "GCF_001"

    def test_prefers_complete_genome(self) -> None:
        from nanopore_simulator.species import _pick_best_assembly

        lines = [
            json.dumps(
                {
                    "accession": "GCF_001",
                    "assembly_info": {"assembly_level": "Scaffold"},
                }
            ),
            json.dumps(
                {
                    "accession": "GCF_002",
                    "assembly_info": {"assembly_level": "Complete Genome"},
                }
            ),
        ]
        result = _pick_best_assembly(lines)
        assert result is not None
        assert result["accession"] == "GCF_002"

    def test_empty_input(self) -> None:
        from nanopore_simulator.species import _pick_best_assembly

        assert _pick_best_assembly([]) is None

    def test_invalid_json_skipped(self) -> None:
        from nanopore_simulator.species import _pick_best_assembly

        lines = ["not json", json.dumps({"accession": "GCF_001"})]
        result = _pick_best_assembly(lines)
        assert result is not None
        assert result["accession"] == "GCF_001"
