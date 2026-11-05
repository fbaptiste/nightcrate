"""Integration tests for the Barnard loader."""

from __future__ import annotations

import csv
import shutil
import sqlite3
from pathlib import Path

import pytest

from nightcrate.catalog_loader import load_catalogs

MINI_FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "catalogs"


@pytest.fixture
def catalogs_root(tmp_path: Path) -> Path:
    openngc_dir = tmp_path / "catalogs" / "openngc"
    openngc_dir.mkdir(parents=True)
    shutil.copy(MINI_FIXTURE_DIR / "openngc" / "mini_NGC.csv", openngc_dir / "NGC.csv")
    shutil.copy(MINI_FIXTURE_DIR / "openngc" / "mini_addendum.csv", openngc_dir / "addendum.csv")
    vizier_dir = tmp_path / "catalogs" / "vizier"
    vizier_dir.mkdir(parents=True)
    shutil.copy(
        MINI_FIXTURE_DIR / "vizier" / "mini_barnard.tsv",
        vizier_dir / "barnard_VII_220.tsv",
    )
    return tmp_path / "catalogs"


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_matching_openngc_own_name_replaces_standalone_barnard_row(db, catalogs_root):
    load_catalogs(db, catalogs_root)
    cur = db.cursor()
    cur.execute(
        """
        SELECT COUNT(*) FROM dso
        WHERE source_catalog_id = (
            SELECT id FROM dso_catalog_source WHERE source_id = 'vizier_barnard'
        )
        """,
    )
    # B 33 merges into the addendum's own B033 object; the other four stay standalone.
    assert cur.fetchone()[0] == 4
    cur.execute(
        """
        SELECT d.source_key
        FROM dso d JOIN dso_designation dd ON dd.dso_id=d.id
        WHERE dd.catalog='barnard' AND dd.identifier='33'
        """
    )
    assert cur.fetchone()[0] == "B033"


def test_all_barnard_dsos_are_drkn(db, catalogs_root):
    load_catalogs(db, catalogs_root)
    cur = db.cursor()
    cur.execute(
        """
        SELECT DISTINCT d.obj_type FROM dso d
        WHERE d.source_catalog_id = (
            SELECT id FROM dso_catalog_source WHERE source_id = 'vizier_barnard'
        )
        """,
    )
    types = {r[0] for r in cur.fetchall()}
    assert types == {"DrkN"}


def test_barnard_common_name_from_names_column(db, catalogs_root):
    load_catalogs(db, catalogs_root)
    cur = db.cursor()
    cur.execute(
        """
        SELECT d.id, d.common_name FROM dso d
        JOIN dso_designation dd ON dd.dso_id = d.id
        WHERE dd.catalog = 'barnard' AND dd.identifier = '33'
        """,
    )
    row = cur.fetchone()
    assert row is not None
    assert row["common_name"] == "Horsehead Nebula"
    assert (
        db.execute(
            "SELECT name FROM dso_other_name WHERE dso_id=? ORDER BY position", (row["id"],)
        ).fetchone()[0]
        == "Barnard Horsehead"
    )


def test_barnard_no_crossref_merge_even_if_emission_region_coincides(db, catalogs_root):
    """B33 and IC 434 share a line of sight but are NOT merged."""
    ngc_path = catalogs_root / "openngc" / "NGC.csv"
    with ngc_path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        fieldnames = reader.fieldnames
    assert fieldnames is not None
    row = dict.fromkeys(fieldnames, "")
    row.update(
        {
            "Name": "IC0434",
            "Type": "HII",
            "RA": "05:41:00",
            "Dec": "-02:27:00",
            "Const": "Ori",
            "Identifiers": "B 33",
        }
    )
    with ngc_path.open("a", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter=";")
        writer.writerow(row)
    load_catalogs(db, catalogs_root)
    cur = db.cursor()
    cur.execute(
        """
        SELECT
            (SELECT dso_id FROM dso_designation WHERE catalog='barnard' AND identifier='33'),
            (SELECT dso_id FROM dso_designation WHERE catalog='ic' AND identifier='434')
        """,
    )
    barnard_id, ic_id = cur.fetchone()
    assert barnard_id != ic_id
