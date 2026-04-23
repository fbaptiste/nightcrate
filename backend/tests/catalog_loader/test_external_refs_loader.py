"""Tests for the NightCrate external-refs CSV override loader."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from nightcrate.catalog_loader import load_catalogs
from nightcrate.catalog_loader.external_refs_loader import (
    ExternalRefsCsvError,
    load_external_refs,
)
from nightcrate.catalog_loader.registry import get_sources

MINI_OPENNGC = Path(__file__).parent.parent / "fixtures" / "catalogs" / "openngc"
MINI_WIKIDATA = Path(__file__).parent.parent / "fixtures" / "catalogs" / "wikidata"


@pytest.fixture(autouse=True)
def _isolate_vendored_nightcrate(tmp_path: Path, monkeypatch):
    """Redirect ``registry._nightcrate_dir`` at a fresh temp dir per test
    so CSV writes don't touch the shipped package data.

    Copies the vendored CSVs (augment, crossrefs) into the temp dir so
    the other NightCrate loaders still see their fixtures — they're
    idempotent reload sources and must be present for the full-catalog
    path to succeed.
    """
    import importlib.resources

    from nightcrate.catalog_loader import registry

    real_dir = Path(
        str(importlib.resources.files("nightcrate") / "data" / "catalogs" / "nightcrate")
    )
    isolated = tmp_path / "nightcrate_data"
    isolated.mkdir(parents=True)
    for name in ("dso_augment.csv", "sharpless_crossref.csv", "barnard_crossref.csv"):
        shutil.copy(real_dir / name, isolated / name)
    # External refs CSV starts empty in the isolated dir.
    (isolated / "dso_external_refs.csv").write_text(
        "dso_designation,provider,language,identifier,url,label,note\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(registry, "_nightcrate_dir", lambda: isolated)


def _base_catalogs(tmp_path: Path) -> Path:
    root = tmp_path / "catalogs"
    openngc_dir = root / "openngc"
    openngc_dir.mkdir(parents=True)
    shutil.copy(MINI_OPENNGC / "mini_NGC.csv", openngc_dir / "NGC.csv")
    shutil.copy(MINI_OPENNGC / "mini_addendum.csv", openngc_dir / "addendum.csv")
    shutil.copy(MINI_OPENNGC / "version.json", openngc_dir / "version.json")
    return root


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _refs_for(cur: sqlite3.Cursor, designation: str, provider: str = None) -> list[sqlite3.Row]:
    sql = (
        "SELECT er.provider, er.language, er.identifier, er.url, er.label, er.source_catalog_id "
        "FROM dso_external_ref er "
        "JOIN dso d ON d.id = er.dso_id "
        "WHERE d.primary_designation = ?"
    )
    params: list = [designation]
    if provider is not None:
        sql += " AND er.provider = ?"
        params.append(provider)
    sql += " ORDER BY er.provider, er.language"
    cur.execute(sql, params)
    return cur.fetchall()


def _write_csv(path: Path, rows: list[str]) -> None:
    path.write_text(
        "\n".join(
            [
                "dso_designation,provider,language,identifier,url,label,note",
                *rows,
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_external_refs_upsert_adds_new_row(db, tmp_path):
    root = _base_catalogs(tmp_path)
    # Vendored CSV under the package ships empty; override via a temp copy
    # of the source that points at a local CSV.
    sources = [s for s in get_sources(root) if s.source_id == "nightcrate_external_refs"]
    assert sources, "nightcrate_external_refs must be registered"
    src = sources[0]
    # Build a custom CSV at the spec'd path.
    csv_path = src.file_path
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(
        csv_path,
        [
            "M42,wikipedia,en,Orion_Nebula,"
            "https://en.wikipedia.org/wiki/Orion_Nebula,Orion Nebula,",
        ],
    )
    load_catalogs(db, root)
    cur = db.cursor()
    refs = _refs_for(cur, "M 42", provider="wikipedia")
    assert len(refs) == 1
    assert refs[0]["identifier"] == "Orion_Nebula"
    assert refs[0]["url"] == "https://en.wikipedia.org/wiki/Orion_Nebula"
    assert refs[0]["label"] == "Orion Nebula"


def test_external_refs_suppression_deletes_existing_row(db, tmp_path):
    """Wikidata inserts a row, then the override CSV suppresses it."""
    root = _base_catalogs(tmp_path)
    # Stage Wikidata TSV so there's a row to suppress.
    wd_dir = root / "wikidata"
    wd_dir.mkdir(parents=True)
    shutil.copy(MINI_WIKIDATA / "mini_wikidata.tsv", wd_dir / "dso_external_refs.tsv")

    # CSV suppression for M42's wikipedia ref.
    sources = [s for s in get_sources(root) if s.source_id == "nightcrate_external_refs"]
    csv_path = sources[0].file_path
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(csv_path, ["M42,wikipedia,en,,,,suppress bad auto-match"])

    load_catalogs(db, root)
    cur = db.cursor()
    refs = _refs_for(cur, "M 42", provider="wikipedia")
    assert len(refs) == 0
    # wikidata row for M42 should still be present (unaffected).
    refs = _refs_for(cur, "M 42", provider="wikidata")
    assert len(refs) == 1


def test_external_refs_upsert_overrides_wikidata_sourced_row(db, tmp_path):
    """A CSV upsert on an already-Wikidata-sourced (dso, provider, language)
    tuple overwrites in place with the CSV's values and source_catalog_id."""
    root = _base_catalogs(tmp_path)
    wd_dir = root / "wikidata"
    wd_dir.mkdir(parents=True)
    shutil.copy(MINI_WIKIDATA / "mini_wikidata.tsv", wd_dir / "dso_external_refs.tsv")

    sources = {s.source_id: s for s in get_sources(root)}
    csv_path = sources["nightcrate_external_refs"].file_path
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(
        csv_path,
        [
            # Point at a different Wikipedia article for M42.
            "M42,wikipedia,en,Orion_Nebula_DIFFERENT,"
            "https://en.wikipedia.org/wiki/Orion_Nebula_DIFFERENT,"
            "Different Title,editorial override",
        ],
    )
    load_catalogs(db, root)
    cur = db.cursor()
    refs = _refs_for(cur, "M 42", provider="wikipedia")
    assert len(refs) == 1
    assert refs[0]["identifier"] == "Orion_Nebula_DIFFERENT"
    # source_catalog_id should point at nightcrate_external_refs, not wikidata_external_refs.
    cur.execute(
        "SELECT source_id FROM dso_catalog_source WHERE id = ?",
        (refs[0]["source_catalog_id"],),
    )
    assert cur.fetchone()["source_id"] == "nightcrate_external_refs"


def test_external_refs_invalid_provider_aborts(db, tmp_path):
    root = _base_catalogs(tmp_path)
    sources = {s.source_id: s for s in get_sources(root)}
    csv_path = sources["nightcrate_external_refs"].file_path
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    # ``astrobin`` is an illustrative future provider not in
    # ``_VALID_PROVIDERS``. Previously this test used ``ned`` for the
    # same purpose; v0.21.1 added ned to the valid set, so we picked a
    # still-invalid placeholder.
    _write_csv(csv_path, ["M42,astrobin,,q,https://astrobin.com/?id=q,Q,"])

    # First load base catalogs to seed DSOs.
    load_catalogs(db, root)
    # Direct call to the loader, skipping force-hash because we want error.
    result = load_external_refs(db, sources["nightcrate_external_refs"], force=True)
    assert result.status == "failed"
    assert "provider" in (result.error or "")


def test_external_refs_wikipedia_requires_language(db, tmp_path):
    root = _base_catalogs(tmp_path)
    sources = {s.source_id: s for s in get_sources(root)}
    csv_path = sources["nightcrate_external_refs"].file_path
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(
        csv_path, ["M42,wikipedia,,Orion_Nebula,https://en.wikipedia.org/wiki/Orion_Nebula,,"]
    )

    load_catalogs(db, root)
    result = load_external_refs(db, sources["nightcrate_external_refs"], force=True)
    assert result.status == "failed"
    assert "language" in (result.error or "")


def test_external_refs_wikidata_forbids_language(db, tmp_path):
    root = _base_catalogs(tmp_path)
    sources = {s.source_id: s for s in get_sources(root)}
    csv_path = sources["nightcrate_external_refs"].file_path
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(
        csv_path,
        ["M42,wikidata,en,Q10481,https://www.wikidata.org/wiki/Q10481,Orion,"],
    )

    load_catalogs(db, root)
    result = load_external_refs(db, sources["nightcrate_external_refs"], force=True)
    assert result.status == "failed"
    assert "language" in (result.error or "")


def test_external_refs_upsert_requires_both_identifier_and_url(db, tmp_path):
    root = _base_catalogs(tmp_path)
    sources = {s.source_id: s for s in get_sources(root)}
    csv_path = sources["nightcrate_external_refs"].file_path
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    # identifier set but url empty → invalid.
    _write_csv(csv_path, ["M42,wikipedia,en,Orion_Nebula,,,"])

    load_catalogs(db, root)
    result = load_external_refs(db, sources["nightcrate_external_refs"], force=True)
    assert result.status == "failed"


def test_external_refs_simbad_upsert_overrides_wikidata_row(db, tmp_path):
    """CSV row with provider=simbad overrides the automated Wikidata-
    sourced SIMBAD link (same upsert contract as wikipedia / wikidata)."""
    root = _base_catalogs(tmp_path)
    # Load Wikidata first so the automated SIMBAD row for M42 lands.
    wd_dir = root / "wikidata"
    wd_dir.mkdir(parents=True)
    shutil.copy(MINI_WIKIDATA / "mini_wikidata.tsv", wd_dir / "dso_external_refs.tsv")
    sources = {s.source_id: s for s in get_sources(root)}
    csv_path = sources["nightcrate_external_refs"].file_path
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(
        csv_path,
        [
            "M42,simbad,,NAME M 42 CORRECTED,"
            "https://simbad.u-strasbg.fr/simbad/sim-id?Ident=NAME+M+42+CORRECTED,"
            "M 42 editorial,",
        ],
    )

    load_catalogs(db, root)
    cur = db.cursor()
    refs = _refs_for(cur, "M 42", provider="simbad")
    assert len(refs) == 1
    assert refs[0]["identifier"] == "NAME M 42 CORRECTED"
    assert refs[0]["label"] == "M 42 editorial"


def test_external_refs_ned_upsert_and_suppression(db, tmp_path):
    """CSV can upsert a NED row (M31 in the fixture already has one via
    Wikidata — override works) and suppress a NED row entirely."""
    root = _base_catalogs(tmp_path)
    wd_dir = root / "wikidata"
    wd_dir.mkdir(parents=True)
    shutil.copy(MINI_WIKIDATA / "mini_wikidata.tsv", wd_dir / "dso_external_refs.tsv")
    sources = {s.source_id: s for s in get_sources(root)}
    csv_path = sources["nightcrate_external_refs"].file_path
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(
        csv_path,
        [
            # Upsert — override the NED identifier.
            "M31,ned,,M 31 edited,https://ned.ipac.caltech.edu/byname?objname=M+31+edited,M 31,",
        ],
    )
    load_catalogs(db, root)
    cur = db.cursor()
    refs = _refs_for(cur, "M 31", provider="ned")
    assert len(refs) == 1
    assert refs[0]["identifier"] == "M 31 edited"

    # Now suppress the NED row via an empty-identifier + empty-url CSV row.
    _write_csv(csv_path, ["M31,ned,,,,,"])
    load_catalogs(db, root, force=True)
    refs = _refs_for(cur, "M 31", provider="ned")
    assert len(refs) == 0


def test_external_refs_simbad_forbids_language(db, tmp_path):
    """SIMBAD + NED are language-agnostic providers (like wikidata) —
    setting language on them is an error."""
    root = _base_catalogs(tmp_path)
    sources = {s.source_id: s for s in get_sources(root)}
    csv_path = sources["nightcrate_external_refs"].file_path
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(
        csv_path,
        [
            "M42,simbad,en,NAME M 42,"
            "https://simbad.u-strasbg.fr/simbad/sim-id?Ident=NAME+M+42,M 42,",
        ],
    )
    load_catalogs(db, root)
    result = load_external_refs(db, sources["nightcrate_external_refs"], force=True)
    assert result.status == "failed"
    assert "language" in (result.error or "")


def test_external_refs_unknown_designation_is_warning_not_error(db, tmp_path):
    root = _base_catalogs(tmp_path)
    sources = {s.source_id: s for s in get_sources(root)}
    csv_path = sources["nightcrate_external_refs"].file_path
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    # Valid row that resolves + one that doesn't.
    _write_csv(
        csv_path,
        [
            "NGC99999,wikipedia,en,Imaginary,https://en.wikipedia.org/wiki/Imaginary,Imaginary,",
            "M42,wikipedia,en,Orion_Nebula,"
            "https://en.wikipedia.org/wiki/Orion_Nebula,Orion Nebula,",
        ],
    )
    load_catalogs(db, root)
    cur = db.cursor()
    refs = _refs_for(cur, "M 42", provider="wikipedia")
    # The valid row lands; the unresolvable one is skipped.
    assert len(refs) == 1


def test_external_refs_suppression_on_nonexistent_ref_is_noop(db, tmp_path):
    """Suppressing an already-absent (dso, provider, language) tuple is fine."""
    root = _base_catalogs(tmp_path)
    sources = {s.source_id: s for s in get_sources(root)}
    csv_path = sources["nightcrate_external_refs"].file_path
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(csv_path, ["M42,wikipedia,en,,,,no existing row"])
    load_catalogs(db, root)
    # No exception; loader reports loaded with zero deletions.
    result = load_external_refs(db, sources["nightcrate_external_refs"], force=True)
    assert result.status == "loaded"


def test_external_refs_csv_error_exception_shape():
    """Direct sanity check on the validation error path."""
    assert issubclass(ExternalRefsCsvError, ValueError)
