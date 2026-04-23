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


def test_wikidata_loader_inserts_wikidata_and_wikipedia_rows(db, catalogs_root):
    load_catalogs(db, catalogs_root)
    cur = db.cursor()
    refs = _refs_for(cur, "M 42")
    providers = [r["provider"] for r in refs]
    assert providers == ["wikidata", "wikipedia"]
    wikidata = next(r for r in refs if r["provider"] == "wikidata")
    assert wikidata["identifier"] == "Q13903"
    assert wikidata["url"] == "https://www.wikidata.org/wiki/Q13903"
    assert wikidata["label"] == "Orion Nebula"
    wikipedia = next(r for r in refs if r["provider"] == "wikipedia")
    assert wikipedia["language"] == "en"
    assert wikipedia["identifier"] == "Orion_Nebula"
    assert wikipedia["url"] == "https://en.wikipedia.org/wiki/Orion_Nebula"
    assert wikipedia["label"] == "Orion Nebula"


def test_wikidata_loader_matches_via_multiple_designations(db, catalogs_root):
    """Andromeda's Wikidata entity lists NGC, M, PGC, UGC — all pointing at
    the same DSO. The loader must recognise the single-DSO outcome and
    insert exactly one Wikidata row + one Wikipedia row."""
    load_catalogs(db, catalogs_root)
    cur = db.cursor()
    refs = _refs_for(cur, "M 31")
    assert len(refs) == 2
    assert {r["provider"] for r in refs} == {"wikidata", "wikipedia"}


def test_wikidata_loader_skips_unmatched_entities(db, catalogs_root):
    """Q999999 references NGC 99999 which doesn't exist — no rows inserted."""
    load_catalogs(db, catalogs_root)
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) AS n FROM dso_external_ref WHERE identifier = 'Q999999'")
    assert cur.fetchone()["n"] == 0


def test_wikidata_loader_inserts_wikidata_without_wikipedia_when_no_enwiki(db, catalogs_root):
    """Q888888 matches NGC 7293 but has no enwiki sitelink — only the
    wikidata row is inserted."""
    load_catalogs(db, catalogs_root)
    cur = db.cursor()
    refs = _refs_for(cur, "NGC 7293")
    assert len(refs) == 1
    assert refs[0]["provider"] == "wikidata"
    assert refs[0]["identifier"] == "Q888888"


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
        "?item\t?itemLabel\t?ngc_id\t?pgc_id\t?ugc_id\t?msg\t?ic\t?cal\t?sh2\t?bar\t?enwiki_title\n"
    )
    rows = (
        '<http://www.wikidata.org/entity/Q111>\t"Primary Orion"@en\t"1976"'
        "\t\t\t\t\t\t\t\t\n"
        '<http://www.wikidata.org/entity/Q222>\t"Duplicate Orion"@en\t"1976"'
        "\t\t\t\t\t\t\t\t\n"
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
