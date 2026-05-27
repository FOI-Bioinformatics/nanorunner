"""Targeted unit tests for cli_helpers genome-resolution helpers."""

from pathlib import Path
from unittest.mock import patch

import pytest
import typer

from nanopore_simulator.cli_helpers import (
    _download_genome_refs,
    _resolve_and_download_genomes,
    _resolve_genome_refs,
    _run_pipeline_validation,
)

# ---------------------------------------------------------------------------
# _resolve_genome_refs
# ---------------------------------------------------------------------------


def test_resolve_unknown_mock_exits():
    with pytest.raises(typer.Exit):
        _resolve_genome_refs("not_a_real_mock_xyz", None, None)


def test_resolve_no_inputs_exits():
    with pytest.raises(typer.Exit):
        _resolve_genome_refs(None, None, None)


def test_resolve_species_warns_when_unresolvable(capsys):
    with patch("nanopore_simulator.species.resolve_species", return_value=None):
        with pytest.raises(typer.Exit):
            _resolve_genome_refs(None, ["NoSuchSpecies"], None)
    err = capsys.readouterr().err
    assert "Could not resolve: NoSuchSpecies" in err


def test_resolve_taxid_warns_when_unresolvable(capsys):
    with patch("nanopore_simulator.species.resolve_taxid", return_value=None):
        with pytest.raises(typer.Exit):
            _resolve_genome_refs(None, None, ["9999999"])
    err = capsys.readouterr().err
    assert "Could not resolve taxid: 9999999" in err


def test_resolve_species_returns_ref():
    from nanopore_simulator.species import GenomeRef

    fake = GenomeRef(name="X", accession="ACC1", source="ncbi", domain="bacteria")
    with patch("nanopore_simulator.species.resolve_species", return_value=fake):
        refs = _resolve_genome_refs(None, ["X"], None)
    assert len(refs) == 1
    assert refs[0][2] is None  # abundance


def test_resolve_taxid_returns_ref():
    from nanopore_simulator.species import GenomeRef

    fake = GenomeRef(name="t", accession="ACC2", source="ncbi", domain="bacteria")
    with patch("nanopore_simulator.species.resolve_taxid", return_value=fake):
        refs = _resolve_genome_refs(None, None, ["123"])
    assert refs[0][0] == "taxid:123"


def test_resolve_mock_organism_without_accession_uses_resolver(capsys):
    """Mock organisms missing an accession fall through to resolve_species,
    and unresolvable ones emit a warning rather than aborting."""
    from nanopore_simulator.mocks import MockCommunity, MockOrganism

    fake_mock = MockCommunity(
        name="t_mock",
        description="test",
        organisms=[
            MockOrganism(
                name="GenusA speciesA",
                resolver="gtdb",
                abundance=1.0,
                accession=None,
            ),
        ],
    )
    with patch("nanopore_simulator.mocks.get_mock", return_value=fake_mock):
        with patch("nanopore_simulator.species.resolve_species", return_value=None):
            with pytest.raises(typer.Exit):
                _resolve_genome_refs("t_mock", None, None)
    err = capsys.readouterr().err
    assert "Could not resolve: GenusA speciesA" in err


# ---------------------------------------------------------------------------
# _download_genome_refs
# ---------------------------------------------------------------------------


def test_download_genome_refs_handles_failure(capsys, tmp_path):
    from nanopore_simulator.species import GenomeRef

    ref = GenomeRef(name="X", accession="A", source="ncbi", domain="bacteria")
    with patch(
        "nanopore_simulator.species.download_genome",
        side_effect=RuntimeError("boom"),
    ):
        result = _download_genome_refs([("X", ref, None)])
    assert result == []
    err = capsys.readouterr().err
    assert "Failed: X" in err


def test_download_genome_refs_success(tmp_path):
    from nanopore_simulator.species import GenomeRef

    ref = GenomeRef(name="X", accession="A", source="ncbi", domain="bacteria")
    fake_path = tmp_path / "g.fa"
    fake_path.write_text(">x\nACGT\n")
    with patch("nanopore_simulator.species.download_genome", return_value=fake_path):
        result = _download_genome_refs([("X", ref, 0.5)])
    assert len(result) == 1
    assert result[0][2] == Path(fake_path)
    assert result[0][3] == 0.5


# ---------------------------------------------------------------------------
# _resolve_and_download_genomes
# ---------------------------------------------------------------------------


def test_resolve_and_download_all_fail(tmp_path):
    from nanopore_simulator.species import GenomeRef

    ref = GenomeRef(name="X", accession="A", source="ncbi", domain="bacteria")
    with patch("nanopore_simulator.species.resolve_species", return_value=ref):
        with patch(
            "nanopore_simulator.species.download_genome",
            side_effect=RuntimeError("network down"),
        ):
            with pytest.raises(typer.Exit):
                _resolve_and_download_genomes(None, ["X"], None)


def test_resolve_and_download_renormalizes_abundances(tmp_path):
    """When mock organisms supply abundances, the returned list is renormalized
    so surviving genomes sum to 1.0."""
    from nanopore_simulator.mocks import MockCommunity, MockOrganism
    from nanopore_simulator.species import GenomeRef

    fake_mock = MockCommunity(
        name="m",
        description="",
        organisms=[
            MockOrganism(name="A", resolver="gtdb", accession="A1", abundance=0.25),
            MockOrganism(name="B", resolver="gtdb", accession="B1", abundance=0.75),
        ],
    )
    p1 = tmp_path / "a.fa"
    p2 = tmp_path / "b.fa"
    p1.write_text(">a\nACGT\n")
    p2.write_text(">b\nACGT\n")

    def fake_dl(ref, cache=None):
        return p1 if ref.accession == "A1" else p2

    with patch("nanopore_simulator.mocks.get_mock", return_value=fake_mock):
        with patch("nanopore_simulator.species.download_genome", side_effect=fake_dl):
            paths, abundances = _resolve_and_download_genomes("m", None, None)

    assert paths == [p1, p2]
    assert abundances is not None
    assert abs(sum(abundances) - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# _run_pipeline_validation
# ---------------------------------------------------------------------------


def test_run_pipeline_validation_reports_issues(capsys, tmp_path):
    with patch(
        "nanopore_simulator.adapters.validate_output",
        return_value=["missing barcode01/", "no fastq files"],
    ):
        _run_pipeline_validation("nanometa", tmp_path)
    out = capsys.readouterr().out
    assert "may not be compatible" in out
    assert "missing barcode01/" in out


def test_run_pipeline_validation_compatible(capsys, tmp_path):
    with patch("nanopore_simulator.adapters.validate_output", return_value=[]):
        _run_pipeline_validation("nanometa", tmp_path)
    out = capsys.readouterr().out
    assert "is compatible" in out
