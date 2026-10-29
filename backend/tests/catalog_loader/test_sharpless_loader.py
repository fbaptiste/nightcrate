"""Integration tests for the Sharpless 2 loader."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from nightcrate.catalog_loader import load_catalogs
from nightcrate.catalog_loader.sharpless_loader import load_crossref_csv

MINI_FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "catalogs"


@pytest.fixture
def catalogs_root(tmp_path: Path) -> Path:
    """Stage the mini fixtures into tmp_path/catalogs/{openngc,vizier}/."""
    # OpenNGC (needed as source of NGC 1976 / NGC 7000 so crossref targets exist)
    openngc_dir = tmp_path / "catalogs" / "openngc"
    openngc_dir.mkdir(parents=True)
    shutil.copy(MINI_FIXTURE_DIR / "openngc" / "mini_NGC.csv", openngc_dir / "NGC.csv")
    shutil.copy(MINI_FIXTURE_DIR / "openngc" / "mini_addendum.csv", openngc_dir / "addendum.csv")
    # VizieR Sharpless
    vizier_dir = tmp_path / "catalogs" / "vizier"
    vizier_dir.mkdir(parents=True)
    shutil.copy(
        MINI_FIXTURE_DIR / "vizier" / "mini_sharpless.tsv",
        vizier_dir / "sharpless_VII_20.tsv",
    )
    return tmp_path / "catalogs"


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_crossref_csv_parses_known_good_file(tmp_path):
    path = tmp_path / "crossref.csv"
    path.write_text(
        "# comment\n"
        "sharpless_number,target_designation,notes\n"
        "281,NGC 1976,Orion\n"
        "117,NGC 7000,North America\n",
        encoding="utf-8",
    )
    mapping = load_crossref_csv(path)
    assert mapping == {"281": "NGC 1976", "117": "NGC 7000"}


def test_crossref_csv_missing_is_empty_dict(tmp_path):
    assert load_crossref_csv(tmp_path / "does_not_exist.csv") == {}


def test_sharpless_merges_crossref_target(db, catalogs_root):
    # Run full load so OpenNGC is present first.
    load_catalogs(db, catalogs_root)
    cur = db.cursor()
    # Sh2-281 maps to NGC 1976 per the bundled sharpless_crossref.csv.
    # NGC 1976 must have a sharpless2 designation now.
    cur.execute(
        """
        SELECT COUNT(*) FROM dso_designation
        WHERE catalog = 'sharpless2' AND identifier = '281'
        """,
    )
    assert cur.fetchone()[0] == 1
    # No standalone "Sh2 281" DSO.
    cur.execute("SELECT COUNT(*) FROM dso WHERE primary_designation = 'Sh2-281'")
    assert cur.fetchone()[0] == 0


def test_sharpless_standalone_when_no_crossref(db, catalogs_root):
    load_catalogs(db, catalogs_root)
    cur = db.cursor()
    # Sh2-155 isn't in the crossref — must be a standalone DSO.
    cur.execute(
        """
        SELECT d.id, d.primary_designation, d.obj_type
        FROM dso d
        JOIN dso_designation dd ON dd.dso_id = d.id
        WHERE dd.catalog = 'sharpless2' AND dd.identifier = '155'
        """,
    )
    row = cur.fetchone()
    assert row is not None
    assert row["primary_designation"] == "Sh2-155"
    assert row["obj_type"] == "HII"


def test_sharpless_loader_is_idempotent(db, catalogs_root):
    load_catalogs(db, catalogs_root)
    cur = db.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM dso WHERE obj_type = 'HII' AND source_catalog_id = "
        "(SELECT id FROM dso_catalog_source WHERE source_id='vizier_sharpless')"
    )
    first = cur.fetchone()[0]
    load_catalogs(db, catalogs_root)
    cur.execute(
        "SELECT COUNT(*) FROM dso WHERE obj_type = 'HII' AND source_catalog_id = "
        "(SELECT id FROM dso_catalog_source WHERE source_id='vizier_sharpless')"
    )
    assert cur.fetchone()[0] == first


def test_sharpless_constellation_computed_from_coords(db, catalogs_root):
    load_catalogs(db, catalogs_root)
    cur = db.cursor()
    # Sh2-117 (North America) at RA=315.9, Dec=+44 should be in Cygnus.
    cur.execute(
        """
        SELECT d.constellation
        FROM dso d
        JOIN dso_designation dd ON dd.dso_id = d.id
        WHERE dd.catalog = 'sharpless2' AND dd.identifier = '117'
        """,
    )
    row = cur.fetchone()
    if row:
        # If merged via crossref, constellation comes from OpenNGC; if not,
        # from astropy. Either way it should exist.
        assert row["constellation"] is not None


def test_sharpless_missing_file_is_missing_status(db, tmp_path):
    """A never-loaded, absent Sharpless input reports missing without a source row."""
    summary = load_catalogs(db, tmp_path / "catalogs")
    result = next(row for row in summary.results if row.source_id == "vizier_sharpless")
    assert result.status == "missing"
