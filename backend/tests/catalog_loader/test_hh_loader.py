"""Herbig-Haro catalog collection and lifecycle tests."""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from nightcrate.catalog_loader import load_catalogs, registry
from nightcrate.catalog_loader.catalog_choice import (
    read_choice,
    with_added,
    with_removed,
    write_choice,
)
from nightcrate.catalog_loader.hash import file_sha256
from nightcrate.catalog_loader.hh_loader import collect_hh
from nightcrate.catalog_loader.reconcile import build_object_set

FIXTURES = Path(__file__).parent.parent / "fixtures" / "catalogs"


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "test.db")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


def _catalogs_root(tmp_path: Path, *, installed: bool = False) -> Path:
    root = tmp_path / "catalogs"
    openngc = root / "openngc"
    vizier = root / "vizier"
    openngc.mkdir(parents=True)
    vizier.mkdir()
    shutil.copy(FIXTURES / "openngc" / "mini_NGC.csv", openngc / "NGC.csv")
    shutil.copy(FIXTURES / "openngc" / "mini_addendum.csv", openngc / "addendum.csv")
    shutil.copy(FIXTURES / "openngc" / "version.json", openngc / "version.json")
    catalog_path = vizier / "hh_V_104.tsv"
    shutil.copy(FIXTURES / "vizier" / "mini_hh.tsv", catalog_path)
    if installed:
        version = {
            "files": {
                catalog_path.name: {
                    "sha256": file_sha256(catalog_path),
                    "fetch_date": "2026-11-02T00:00:00+00:00",
                }
            }
        }
        (vizier / "version.json").write_text(json.dumps(version), encoding="utf-8")
    return root


def _sources(root: Path):
    return {source.source_id: source for source in registry.get_sources(root)}


def _hh_batch(root: Path):
    sources = _sources(root)
    return collect_hh({"vizier_hh": sources["vizier_hh"]}, frozenset({"hh"}))


def test_hh_registry_projects_only_used_columns():
    catalog = registry.optional_catalog("hh")

    assert catalog is not None
    assert catalog.display_name == "Herbig-Haro objects"
    assert catalog.legacy_default is False
    assert catalog.fetch_specs[0].required_columns == (
        "_RAJ2000",
        "_DEJ2000",
        "HH",
        "Name",
        "Region",
    )


def test_collect_hh_keeps_46_and_47_as_separate_objects(tmp_path: Path):
    rows = {row.source_key: row for row in _hh_batch(_catalogs_root(tmp_path)).objects}

    assert set(rows) == {"46", "47", "161"}
    assert rows["46"].columns["primary_designation"] == "HH 46"
    assert rows["47"].columns["primary_designation"] == "HH 47"
    assert rows["46"].columns["obj_type"] == rows["47"].columns["obj_type"] == "HH"
    assert rows["46"].columns["openngc_notes"] == "Region Gum Nebula"
    assert rows["47"].columns["openngc_notes"] == "Region Gum Nebula"


def test_collect_hh_omits_missing_number_177(tmp_path: Path):
    identifiers = {row.source_key for row in _hh_batch(_catalogs_root(tmp_path)).objects}

    assert "177" not in identifiers


def test_collect_hh_removes_tex_punctuation_from_notes(tmp_path: Path):
    row = next(
        row for row in _hh_batch(_catalogs_root(tmp_path)).objects if row.source_key == "161"
    )

    assert row.columns["openngc_notes"] == "Region Cassiopeia · Also LkHα 198B/HH"
    assert not set("^{}").intersection(str(row.columns["openngc_notes"]))


def test_hh_reconcile_keeps_fixture_rows_standalone_without_groups(tmp_path: Path):
    root = _catalogs_root(tmp_path)
    built = build_object_set(_sources(root), None, frozenset({"hh"}))
    hh_objects = [obj for obj in built.objects if obj.source_id == "vizier_hh"]

    assert len(hh_objects) == 3
    assert not any(source_id == "vizier_hh" for source_id, _source_key in built.merges)
    assert {obj.designations for obj in hh_objects} == {
        (("hh", "46", True),),
        (("hh", "47", True),),
        (("hh", "161", True),),
    }
    assert built.groups == ()
    assert built.stated_matches == ()


def test_hh_load_remove_and_add_reactivates_linked_object(db: sqlite3.Connection, tmp_path: Path):
    root = _catalogs_root(tmp_path, installed=True)
    write_choice(root, with_added(None, "hh"))
    load_catalogs(db, root)
    row = db.execute(
        "SELECT d.id FROM dso d JOIN dso_designation dd ON dd.dso_id=d.id "
        "WHERE dd.catalog='hh' AND dd.identifier='46'"
    ).fetchone()
    assert row is not None
    dso_id = int(row[0])
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (dso_id,))
    db.commit()

    write_choice(root, with_removed(read_choice(root), "hh"))
    load_catalogs(db, root)
    assert db.execute("SELECT active FROM dso WHERE id=?", (dso_id,)).fetchone()[0] == 0
    assert (
        db.execute(
            "SELECT display_form FROM dso_designation WHERE dso_id=? AND catalog='hh'", (dso_id,)
        ).fetchone()[0]
        == "HH 46"
    )

    write_choice(root, with_added(read_choice(root), "hh"))
    load_catalogs(db, root)
    assert tuple(db.execute("SELECT id, active FROM dso WHERE id=?", (dso_id,)).fetchone()) == (
        dso_id,
        1,
    )
