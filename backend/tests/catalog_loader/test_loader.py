"""Integration tests for the DSO catalog loader.

conftest.py's autouse fixture provisions ``tmp_path / "test.db"`` and
applies all migrations (0005+) via aiosqlite. Here we reopen the same
file with a sync ``sqlite3`` connection — the catalog loader needs a
synchronous connection to run its own transactions.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from nightcrate.catalog_loader import load_catalogs
from nightcrate.catalog_loader.registry import get_sources

MINI_FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "catalogs" / "openngc"


@pytest.fixture
def catalogs_root(tmp_path: Path) -> Path:
    """Stage the mini fixtures under the filenames the registry expects
    (``NGC.csv`` / ``addendum.csv``) inside ``<tmp>/catalogs/openngc/``.
    """
    openngc_dir = tmp_path / "catalogs" / "openngc"
    openngc_dir.mkdir(parents=True)
    shutil.copy(MINI_FIXTURE_DIR / "mini_NGC.csv", openngc_dir / "NGC.csv")
    shutil.copy(MINI_FIXTURE_DIR / "mini_addendum.csv", openngc_dir / "addendum.csv")
    shutil.copy(MINI_FIXTURE_DIR / "version.json", openngc_dir / "version.json")
    return tmp_path / "catalogs"


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _counts(conn: sqlite3.Connection) -> dict[str, int]:
    cur = conn.cursor()
    out: dict[str, int] = {}
    for table in ("dso", "dso_designation", "dso_catalog_source"):
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        out[table] = cur.fetchone()[0]
    return out


def _designations_of(conn: sqlite3.Connection, primary_designation: str) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT dd.catalog, dd.identifier, dd.is_primary
        FROM dso_designation dd
        JOIN dso d ON d.id = dd.dso_id
        WHERE d.primary_designation = ?
        ORDER BY dd.is_primary DESC, dd.catalog, dd.identifier
        """,
        (primary_designation,),
    )
    return [dict(r) for r in cur.fetchall()]


def test_end_to_end_load_mini_fixture(db: sqlite3.Connection, catalogs_root: Path):
    summary = load_catalogs(db, catalogs_root)

    # Assertions target the OpenNGC path; VizieR sources are expected
    # "missing" in tests (no fixtures staged) and nightcrate sources load
    # from the bundled package. Only the two OpenNGC sources should be
    # "loaded" against our mini fixture.
    openngc_results = [r for r in summary.results if r.source_id.startswith("openngc")]
    assert all(r.status == "loaded" for r in openngc_results), [
        (r.source_id, r.status, r.error) for r in openngc_results
    ]

    counts = _counts(db)
    # mini_NGC: 11 rows - 1 NonEx - 1 Dup = 9 canonical. mini_addendum: 3 - 1 Dup = 2.
    assert counts["dso"] == 9 + 2
    # Sources that actually run a loader register a catalog_source row:
    # 2 (OpenNGC) + 1 (nightcrate_augment) + 1 (nightcrate_external_refs,
    # vendored empty CSV) = 4. The crossref stubs register no row (they're
    # side-inputs / placeholders), and VizieR + wikidata sources stay
    # "missing" in tests.
    assert counts["dso_catalog_source"] == 4
    assert counts["dso_designation"] >= counts["dso"]


def test_orion_nebula_has_expected_designations(db: sqlite3.Connection, catalogs_root: Path):
    load_catalogs(db, catalogs_root)
    designations = _designations_of(db, "M 42")
    tuples = [(d["catalog"], d["identifier"]) for d in designations]
    # Primary should be messier/42 (precedence order)
    assert designations[0]["catalog"] == "messier"
    assert designations[0]["is_primary"] == 1
    # All three of NGC 1976, M 42, and LBN 974 (from Identifiers) must be present.
    assert ("ngc", "1976") in tuples
    assert ("messier", "42") in tuples
    assert ("lbn", "974") in tuples
    # PGC leading zeros stripped by the crossref parser.
    assert ("pgc", "26257") in tuples


def test_andromeda_primary_is_messier(db: sqlite3.Connection, catalogs_root: Path):
    load_catalogs(db, catalogs_root)
    designations = _designations_of(db, "M 31")
    assert designations[0]["catalog"] == "messier"
    assert designations[0]["identifier"] == "31"


def test_dup_row_merges_into_canonical(db: sqlite3.Connection, catalogs_root: Path):
    # IC0011 is a Dup that cross-refs to NGC 281. Loading must produce NGC 281
    # as one dso with both NGC 281 AND IC 11 designations.
    load_catalogs(db, catalogs_root)
    designations = _designations_of(db, "NGC 281")
    tuples = [(d["catalog"], d["identifier"]) for d in designations]
    assert ("ngc", "281") in tuples
    assert ("ic", "11") in tuples


def test_addendum_m102_dup_folds_via_messier(db: sqlite3.Connection, catalogs_root: Path):
    # Addendum row M102 is marked Dup with M=101 — it should fold into M101
    # (which comes from NGC5457 in mini_NGC.csv).
    load_catalogs(db, catalogs_root)
    # Ensure no separate dso was created for the Dup row.
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM dso WHERE primary_designation = 'M 102'")
    assert cur.fetchone()[0] == 0
    # The M102 designation should be attached to M101's dso.
    designations = _designations_of(db, "M 101")
    tuples = [(d["catalog"], d["identifier"]) for d in designations]
    assert ("messier", "101") in tuples
    assert ("messier", "102") in tuples


def test_nonex_rows_skipped_entirely(db: sqlite3.Connection, catalogs_root: Path):
    load_catalogs(db, catalogs_root)
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM dso_designation WHERE catalog='ic' AND identifier='67'")
    # IC 67 is NonEx — no designation, no dso.
    assert cur.fetchone()[0] == 0


def test_unchanged_reload_is_noop(db: sqlite3.Connection, catalogs_root: Path):
    first = load_catalogs(db, catalogs_root)
    before = _counts(db)
    second = load_catalogs(db, catalogs_root)
    after = _counts(db)

    assert before == after
    # Only check OpenNGC sources — VizieR sources stay "missing" and
    # nightcrate sources skip the hash-check path.
    openngc_second = [r for r in second.results if r.source_id.startswith("openngc")]
    assert all(r.status == "unchanged" for r in openngc_second), [
        (r.source_id, r.status) for r in openngc_second
    ]
    openngc_first = [r for r in first.results if r.source_id.startswith("openngc")]
    assert all(r.status == "loaded" for r in openngc_first)


def test_force_reload_replaces_rows(db: sqlite3.Connection, catalogs_root: Path):
    load_catalogs(db, catalogs_root)
    before = _counts(db)
    summary = load_catalogs(db, catalogs_root, force=True)
    after = _counts(db)
    assert before == after
    openngc_results = [r for r in summary.results if r.source_id.startswith("openngc")]
    assert all(r.status == "loaded" for r in openngc_results)


def test_each_source_gets_distinct_catalog_source_row(db: sqlite3.Connection, catalogs_root: Path):
    load_catalogs(db, catalogs_root)
    cur = db.cursor()
    # Only the OpenNGC + bundled nightcrate sources register in tests; VizieR
    # sources stay "missing" and do not insert catalog_source rows.
    cur.execute("SELECT source_id FROM dso_catalog_source ORDER BY source_id")
    ids = [r[0] for r in cur.fetchall()]
    assert "openngc" in ids
    assert "openngc_addendum" in ids
    assert "nightcrate_augment" in ids


def test_unique_catalog_identifier_constraint(db: sqlite3.Connection, catalogs_root: Path):
    load_catalogs(db, catalogs_root)
    # Seeding the same (catalog, identifier) twice must raise.
    cur = db.cursor()
    cur.execute("SELECT id FROM dso LIMIT 1")
    dso_id = cur.fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        cur.execute(
            """
            INSERT INTO dso_designation
                (dso_id, catalog, identifier, display_form, search_key, is_primary)
            VALUES (?, 'messier', '42', 'M 42', 'messier42', 0)
            """,
            (dso_id,),
        )


def test_search_key_normalization(db: sqlite3.Connection, catalogs_root: Path):
    load_catalogs(db, catalogs_root)
    cur = db.cursor()
    # Every search_key must be lowercase with no whitespace.
    cur.execute(
        "SELECT search_key FROM dso_designation "
        "WHERE search_key != lower(search_key) OR search_key LIKE '% %'"
    )
    assert cur.fetchall() == []


def test_registry_exposes_expected_sources(catalogs_root: Path):
    sources = get_sources(catalogs_root)
    ids = {s.source_id for s in sources}
    assert {"openngc", "openngc_addendum"} <= ids
    assert {"vizier_sharpless", "vizier_barnard", "github_50mgc"} <= ids
    assert {
        "nightcrate_augment",
        "nightcrate_sharpless_crossref",
        "nightcrate_barnard_crossref",
    } <= ids
    # OpenNGC sources use the openngc parser.
    for src in sources:
        if src.source_id.startswith("openngc"):
            assert src.parser == "openngc"
            assert src.category == "openngc"
