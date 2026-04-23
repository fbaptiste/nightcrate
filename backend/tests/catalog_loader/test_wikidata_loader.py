"""End-to-end tests for the Wikidata loader.

Uses the OpenNGC mini fixture (M42 + M31 + NGC 7293) for the DSO base
and layers Wikidata fixture TSVs on top. Asserts directly on
``dso_external_ref`` rows.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from nightcrate.catalog_loader import load_catalogs
from nightcrate.catalog_loader.registry import get_sources

MINI_OPENNGC = Path(__file__).parent.parent / "fixtures" / "catalogs" / "openngc"
MINI_WIKIDATA = Path(__file__).parent.parent / "fixtures" / "catalogs" / "wikidata"


@pytest.fixture
def catalogs_root(tmp_path: Path) -> Path:
    root = tmp_path / "catalogs"
    # OpenNGC base
    openngc_dir = root / "openngc"
    openngc_dir.mkdir(parents=True)
    shutil.copy(MINI_OPENNGC / "mini_NGC.csv", openngc_dir / "NGC.csv")
    shutil.copy(MINI_OPENNGC / "mini_addendum.csv", openngc_dir / "addendum.csv")
    shutil.copy(MINI_OPENNGC / "version.json", openngc_dir / "version.json")
    # Wikidata dir
    wikidata_dir = root / "wikidata"
    wikidata_dir.mkdir(parents=True)
    shutil.copy(MINI_WIKIDATA / "mini_wikidata.tsv", wikidata_dir / "dso_external_refs.tsv")
    return root


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _refs_for(cur: sqlite3.Cursor, designation: str) -> list[sqlite3.Row]:
    cur.execute(
        """
        SELECT er.provider, er.language, er.identifier, er.url, er.label
        FROM dso_external_ref er
        JOIN dso d ON d.id = er.dso_id
        WHERE d.primary_designation = ?
        ORDER BY er.provider
        """,
        (designation,),
    )
    return cur.fetchall()


def test_wikidata_loader_inserts_wikidata_wikipedia_and_simbad_for_galactic(db, catalogs_root):
    """M42 is an emission nebula (galactic). Wikidata provides P3083
    (SIMBAD) but no P2528 (NED) in the fixture, and the extragalactic
    filter would block NED anyway — so we expect three providers:
    wikidata, wikipedia, simbad. SIMBAD identifier is stored raw
    (``NAME ORI NEB``); the URL is ``+``-encoded."""
    load_catalogs(db, catalogs_root)
    cur = db.cursor()
    refs = _refs_for(cur, "M 42")
    providers = [r["provider"] for r in refs]
    assert providers == ["simbad", "wikidata", "wikipedia"]

    wikidata = next(r for r in refs if r["provider"] == "wikidata")
    assert wikidata["identifier"] == "Q13903"
    assert wikidata["url"] == "https://www.wikidata.org/wiki/Q13903"
    assert wikidata["label"] == "Orion Nebula"

    wikipedia = next(r for r in refs if r["provider"] == "wikipedia")
    assert wikipedia["language"] == "en"
    assert wikipedia["identifier"] == "Orion_Nebula"
    assert wikipedia["url"] == "https://en.wikipedia.org/wiki/Orion_Nebula"
    assert wikipedia["label"] == "Orion Nebula"

    simbad = next(r for r in refs if r["provider"] == "simbad")
    assert simbad["language"] is None
    assert simbad["identifier"] == "NAME ORI NEB"
    assert simbad["url"] == "https://simbad.u-strasbg.fr/simbad/sim-id?Ident=NAME+ORI+NEB"
    assert simbad["label"] == "M 42"


def test_wikidata_loader_inserts_ned_for_extragalactic(db, catalogs_root):
    """M31 is a galaxy. Wikidata has P3083 (SIMBAD) but no reliable NED
    property, so NED is synthesised from M31's primary designation via
    NED's tolerant byname resolver. Four providers total: wikidata,
    wikipedia, simbad, ned."""
    load_catalogs(db, catalogs_root)
    cur = db.cursor()
    refs = _refs_for(cur, "M 31")
    providers = [r["provider"] for r in refs]
    assert providers == ["ned", "simbad", "wikidata", "wikipedia"]

    ned = next(r for r in refs if r["provider"] == "ned")
    # NED identifier = DSO's primary designation.
    assert ned["identifier"] == "M 31"
    assert ned["url"] == "https://ned.ipac.caltech.edu/byname?objname=M+31"
    assert ned["label"] == "M 31"

    simbad = next(r for r in refs if r["provider"] == "simbad")
    assert simbad["identifier"] == "M 31"
    assert simbad["url"] == "https://simbad.u-strasbg.fr/simbad/sim-id?Ident=M+31"


def test_wikidata_loader_matches_via_multiple_designations(db, catalogs_root):
    """Andromeda's Wikidata entity lists NGC, M, PGC, UGC — all pointing at
    the same DSO. The loader must recognise the single-DSO outcome and
    insert exactly one row per provider (wikidata, wikipedia, simbad, ned)."""
    load_catalogs(db, catalogs_root)
    cur = db.cursor()
    refs = _refs_for(cur, "M 31")
    assert len(refs) == 4
    assert {r["provider"] for r in refs} == {"wikidata", "wikipedia", "simbad", "ned"}


def test_wikidata_loader_skips_unmatched_entities(db, catalogs_root):
    """Q999999 references NGC 99999 which doesn't exist — no rows inserted."""
    load_catalogs(db, catalogs_root)
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) AS n FROM dso_external_ref WHERE identifier = 'Q999999'")
    assert cur.fetchone()["n"] == 0


def test_wikidata_loader_simbad_fallback_from_designation_when_no_p3083(db, catalogs_root):
    """Q888888 matches NGC 7293 via its NGC ID but has no P3083 in the
    fixture. SIMBAD fallback kicks in (Q3 decision): identifier +
    URL synthesised from the DSO's primary designation. No enwiki
    sitelink for this entity → no wikipedia row.
    """
    load_catalogs(db, catalogs_root)
    cur = db.cursor()
    refs = _refs_for(cur, "NGC 7293")
    providers = [r["provider"] for r in refs]
    assert providers == ["simbad", "wikidata"]

    simbad = next(r for r in refs if r["provider"] == "simbad")
    # Fallback path: identifier is the DSO's primary designation, URL
    # is built from it (+-encoded).
    assert simbad["identifier"] == "NGC 7293"
    assert simbad["url"] == "https://simbad.u-strasbg.fr/simbad/sim-id?Ident=NGC+7293"
    assert simbad["label"] == "NGC 7293"

    wikidata = next(r for r in refs if r["provider"] == "wikidata")
    assert wikidata["identifier"] == "Q888888"


def test_wikidata_loader_idempotent(db, catalogs_root):
    """Two full loads of the same TSV must produce the same DB state and
    NOT duplicate rows."""
    load_catalogs(db, catalogs_root)
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) AS n FROM dso_external_ref")
    count_after_first = cur.fetchone()["n"]

    load_catalogs(db, catalogs_root, force=True)
    cur.execute("SELECT COUNT(*) AS n FROM dso_external_ref")
    count_after_second = cur.fetchone()["n"]
    assert count_after_first == count_after_second


def test_wikidata_loader_duplicates_multi_match_onto_every_dso(tmp_path, db):
    """When a Wikidata entity cross-references TWO different NightCrate DSOs
    (e.g., Crab Nebula is both NGC 1952 and Sh2-244 in OpenNGC's split
    rows), the loader duplicates the refs onto every matching DSO.

    OpenNGC's per-catalog splits mean the same physical object often
    lives in multiple DSO rows; Wikidata unifies them under one entity,
    and the user wants the Wikipedia chip to appear on any DSO page they
    might navigate to. The editorial CSV override is the escape hatch
    for the rare cases where duplication is undesired (suppression rows).
    """
    # Stage the OpenNGC base so M42 and M31 both exist as distinct DSOs.
    root = tmp_path / "catalogs"
    openngc_dir = root / "openngc"
    openngc_dir.mkdir(parents=True)
    shutil.copy(MINI_OPENNGC / "mini_NGC.csv", openngc_dir / "NGC.csv")
    shutil.copy(MINI_OPENNGC / "mini_addendum.csv", openngc_dir / "addendum.csv")
    shutil.copy(MINI_OPENNGC / "version.json", openngc_dir / "version.json")
    # Stage the multi-match TSV (Q5555555 claims both NGC 1976 and M 31).
    wd_dir = root / "wikidata"
    wd_dir.mkdir(parents=True)
    shutil.copy(MINI_WIKIDATA / "mini_wikidata_ambiguous.tsv", wd_dir / "dso_external_refs.tsv")

    load_catalogs(db, root)

    cur = db.cursor()
    # The QID should land on BOTH DSOs (M42 via NGC 1976, M31 via M).
    cur.execute(
        """
        SELECT d.primary_designation
        FROM dso_external_ref er
        JOIN dso d ON d.id = er.dso_id
        WHERE er.identifier = 'Q5555555' AND er.provider = 'wikidata'
        ORDER BY d.primary_designation
        """
    )
    designations = [r["primary_designation"] for r in cur.fetchall()]
    assert designations == ["M 31", "M 42"]

    # Wikipedia ref should likewise land on both.
    cur.execute(
        "SELECT COUNT(*) AS n FROM dso_external_ref WHERE identifier = 'Impossible' "
        "AND provider = 'wikipedia'"
    )
    assert cur.fetchone()["n"] == 2


def test_wikidata_loader_missing_file_marks_source(db, tmp_path):
    """When the TSV is absent, the loader reports ``missing`` status; the
    other sources keep running."""
    root = tmp_path / "catalogs"
    openngc_dir = root / "openngc"
    openngc_dir.mkdir(parents=True)
    shutil.copy(MINI_OPENNGC / "mini_NGC.csv", openngc_dir / "NGC.csv")
    shutil.copy(MINI_OPENNGC / "mini_addendum.csv", openngc_dir / "addendum.csv")
    shutil.copy(MINI_OPENNGC / "version.json", openngc_dir / "version.json")
    # No wikidata dir at all.
    summary = load_catalogs(db, root)
    wd_result = next(r for r in summary.results if r.source_id == "wikidata_external_refs")
    assert wd_result.status == "missing"


def test_wikidata_registry_entry_present_even_when_file_absent(tmp_path):
    """The registry always surfaces the wikidata source — the admin UI
    needs the row to show a Fetch button when no data is installed."""
    sources = get_sources(tmp_path / "nonexistent")
    ids = [s.source_id for s in sources]
    assert "wikidata_external_refs" in ids
    assert "nightcrate_external_refs" in ids


def test_wikidata_loader_skips_ned_for_non_galaxy(db, catalogs_root):
    """NED rows are inserted only for extragalactic DSOs (obj_type in
    GALAXY_TYPES). M42 is an emission nebula, not a galaxy — no NED
    row, regardless of Wikidata coverage."""
    load_catalogs(db, catalogs_root)
    cur = db.cursor()
    cur.execute(
        """
        SELECT COUNT(*) AS n
        FROM dso_external_ref er
        JOIN dso d ON d.id = er.dso_id
        WHERE d.primary_designation = 'M 42' AND er.provider = 'ned'
        """
    )
    assert cur.fetchone()["n"] == 0


def test_wikidata_loader_dedupes_on_nullable_language(tmp_path, db):
    """Regression: two Wikidata entities (different QIDs) both cross-
    referenced to the same DSO must collapse to ONE wikidata row per DSO.

    Background: the ``UNIQUE(dso_id, provider, language)`` constraint in
    migration 0022 does NOT enforce uniqueness when language IS NULL —
    SQLite treats all NULLs as distinct inside a unique index. The
    partial unique index ``(dso_id, provider) WHERE language IS NULL``
    covers the language-agnostic case. Without it, two QIDs claiming
    the same DSO would both land — observed in the wild on M101
    (Q14371 Pinwheel Galaxy + Q14374 Messier 102 both reference NGC 5457).
    """
    root = tmp_path / "catalogs"
    openngc_dir = root / "openngc"
    openngc_dir.mkdir(parents=True)
    shutil.copy(MINI_OPENNGC / "mini_NGC.csv", openngc_dir / "NGC.csv")
    shutil.copy(MINI_OPENNGC / "mini_addendum.csv", openngc_dir / "addendum.csv")
    shutil.copy(MINI_OPENNGC / "version.json", openngc_dir / "version.json")

    wd_dir = root / "wikidata"
    wd_dir.mkdir(parents=True)
    # Two separate Wikidata entities both pointing at NGC 1976 (M42).
    header = (
        "?item\t?itemLabel\t?ngc_id\t?pgc_id\t?ugc_id\t?msg\t?ic\t?cal\t?sh2\t?bar"
        "\t?simbad_id\t?enwiki_title\n"
    )
    rows = (
        '<http://www.wikidata.org/entity/Q111>\t"Primary Orion"@en\t"1976"'
        "\t\t\t\t\t\t\t\t\t\n"
        '<http://www.wikidata.org/entity/Q222>\t"Duplicate Orion"@en\t"1976"'
        "\t\t\t\t\t\t\t\t\t\n"
    )
    (wd_dir / "dso_external_refs.tsv").write_text(header + rows, encoding="utf-8")

    load_catalogs(db, root)
    cur = db.cursor()
    cur.execute(
        """
        SELECT COUNT(*) AS n
        FROM dso_external_ref er
        JOIN dso d ON d.id = er.dso_id
        WHERE d.primary_designation = 'M 42' AND er.provider = 'wikidata'
        """
    )
    assert cur.fetchone()["n"] == 1
