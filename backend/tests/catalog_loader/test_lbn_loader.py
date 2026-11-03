"""LBN catalog collection, matching, grouping, and lifecycle tests."""

from __future__ import annotations

import csv
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
from nightcrate.catalog_loader.lbn_loader import collect_lbn
from nightcrate.catalog_loader.reconcile import build_object_set
from nightcrate.catalog_loader.registry import CatalogSource

FIXTURES = Path(__file__).parent.parent / "fixtures" / "catalogs"
FULL_SAMPLE = (
    Path(__file__).parents[3]
    / ".superpowers"
    / "codex"
    / "v0.44.0"
    / "samples"
    / "full_VII_9_catalog.tsv"
)
LBN_FILENAME = "lbn_VII_9.tsv"


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
    catalog_path = vizier / LBN_FILENAME
    shutil.copy(FIXTURES / "vizier" / "mini_lbn.tsv", catalog_path)
    if installed:
        version = {
            "files": {
                LBN_FILENAME: {
                    "sha256": file_sha256(catalog_path),
                    "fetch_date": "2026-11-02T00:00:00+00:00",
                }
            }
        }
        (vizier / "version.json").write_text(json.dumps(version), encoding="utf-8")
    return root


def _sources(root: Path) -> dict[str, CatalogSource]:
    return {source.source_id: source for source in registry.get_sources(root)}


def _batch(root: Path):
    source = _sources(root)["vizier_lbn"]
    return collect_lbn({source.source_id: source}, frozenset({"lbn"}))


def _append_openngc_rows(root: Path, names: tuple[str, ...]) -> None:
    path = root / "openngc" / "NGC.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        fieldnames = csv.DictReader(handle, delimiter=";").fieldnames
    assert fieldnames is not None
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=";")
        for position, name in enumerate(names):
            row = dict.fromkeys(fieldnames, "")
            row.update(
                {
                    "Name": name,
                    "Type": "SNR" if name != "NGC6523" else "HII",
                    "RA": f"20:5{position}:00",
                    "Dec": "+31:00:00",
                    "Const": "Cyg",
                    "MajAx": "60",
                    "MinAx": "20",
                    "Identifiers": "LBN 191" if name == "NGC6960" else "",
                }
            )
            writer.writerow(row)


def test_lbn_registry_projects_used_columns_and_uses_readme_credit(tmp_path: Path):
    catalog = registry.optional_catalog("lbn")

    assert catalog is not None
    assert catalog.display_name == "LBN (Lynds bright nebulae)"
    assert catalog.legacy_default is False
    assert catalog.source_ids == ("vizier_lbn",)
    assert catalog.fetch_specs[0].output_filename == LBN_FILENAME
    assert catalog.fetch_specs[0].required_columns == (
        "_RAJ2000",
        "_DEJ2000",
        "Seq",
        "Diam1",
        "Diam2",
        "Bright",
        "Name",
    )
    assert catalog.fetch_specs[0].additional_params == {"-out.add": "_RAJ2000,_DEJ2000"}
    assert catalog.credit == "Lynds 1965. Retrieved via VizieR VII/9."
    source = _sources(_catalogs_root(tmp_path))["vizier_lbn"]
    assert source.attribution == registry.LBN_CITATION
    for wording in (
        "Lynds, B.T. 1965",
        "Catalogue of Bright Nebulae",
        "Astrophysical Journal Supplement Series 12, 163",
        "(VizieR VII/9)",
        registry.CDS_CITATION,
    ):
        assert wording in source.attribution


def test_collect_lbn_uses_equatorial_positions_sizes_names_and_notes(tmp_path: Path):
    rows = {row.source_key: row for row in _batch(_catalogs_root(tmp_path)).objects}

    assert set(rows) == {"1", "25", "128", "191", "245", "437", "913"}
    assert rows["1"].cross_identifications == (("sharpless2", "17"),)
    assert rows["25"].cross_identifications == (("ngc", "6523"),)
    assert rows["128"].cross_identifications == (("cederblad", "168"),)
    assert rows["245"].cross_identifications == (("ic", "1318B"),)
    assert rows["437"].cross_identifications == ()
    assert rows["437"].columns["openngc_notes"] == (
        "Brightness 4 (1 brightest, 6 faintest) · Also DG 187"
    )
    assert rows["191"].columns["maj_axis_arcmin"] == 210.0
    assert rows["191"].columns["min_axis_arcmin"] == 160.0
    assert rows["191"].columns["openngc_notes"] is None
    assert rows["913"].columns["dec_deg"] == pytest.approx(-0.6664)
    assert all(row.columns["obj_type"] == "Neb" for row in rows.values())
    assert all(row.columns["mag_v"] is None for row in rows.values())


def test_collect_lbn_full_sample_count_when_available():
    if not FULL_SAMPLE.exists():
        pytest.skip("local full LBN sample is not present")
    source = CatalogSource(
        "vizier_lbn",
        "vizier",
        "LBN sample",
        FULL_SAMPLE,
        None,
        None,
        "CDS public",
        registry.LBN_CITATION,
        "lbn",
    )

    assert len(collect_lbn({source.source_id: source}, frozenset({"lbn"})).objects) == 1125


def test_lbn_reconcile_keeps_191_separate_with_six_parts_and_merges_ngc_name(tmp_path: Path):
    root = _catalogs_root(tmp_path)
    _append_openngc_rows(
        root,
        ("NGC6523", "NGC6960", "NGC6992", "NGC6995", "NGC6974", "NGC6979", "IC1340"),
    )

    built = build_object_set(_sources(root), None, frozenset({"lbn"}))
    lbn_191_index = next(
        index
        for index, obj in enumerate(built.objects)
        if obj.source_id == "vizier_lbn" and obj.source_key == "191"
    )
    ngc_6960 = next(obj for obj in built.objects if obj.source_key == "NGC6960")
    lbn_437 = next(
        obj for obj in built.objects if obj.source_id == "vizier_lbn" and obj.source_key == "437"
    )

    assert built.merges[("vizier_lbn", "25")] == next(
        index for index, obj in enumerate(built.objects) if obj.source_key == "NGC6523"
    )
    assert ("lbn", "25", False) in built.objects[built.merges[("vizier_lbn", "25")]].designations
    assert ("lbn", "191", True) in built.objects[lbn_191_index].designations
    assert all(designation[:2] != ("lbn", "191") for designation in ngc_6960.designations)
    assert lbn_437.designations == (("lbn", "437", True),)
    group = next(
        group for group in built.groups if group.catalog == "lbn" and group.identifier == "191"
    )
    assert group.whole_index == lbn_191_index
    assert {built.objects[index].source_key for index in group.member_indexes} == {
        "NGC6960",
        "NGC6992",
        "NGC6995",
        "NGC6974",
        "NGC6979",
        "IC1340",
    }


def test_lbn_load_remove_and_add_reactivates_linked_object(db: sqlite3.Connection, tmp_path: Path):
    root = _catalogs_root(tmp_path, installed=True)
    write_choice(root, with_added(None, "lbn"))
    load_catalogs(db, root)
    loop = db.execute(
        "SELECT d.common_name, d.distance_pc FROM dso d "
        "JOIN dso_designation dd ON dd.dso_id=d.id "
        "WHERE dd.catalog='lbn' AND dd.identifier='191'"
    ).fetchone()
    assert tuple(loop) == ("Cygnus Loop", 740.0)
    row = db.execute(
        "SELECT d.id FROM dso d JOIN dso_designation dd ON dd.dso_id=d.id "
        "WHERE dd.catalog='lbn' AND dd.identifier='437'"
    ).fetchone()
    assert row is not None
    dso_id = int(row[0])
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (dso_id,))
    db.commit()

    write_choice(root, with_removed(read_choice(root), "lbn"))
    load_catalogs(db, root)
    assert db.execute("SELECT active FROM dso WHERE id=?", (dso_id,)).fetchone()[0] == 0

    write_choice(root, with_added(read_choice(root), "lbn"))
    load_catalogs(db, root)
    assert tuple(db.execute("SELECT id, active FROM dso WHERE id=?", (dso_id,)).fetchone()) == (
        dso_id,
        1,
    )
    assert db.execute("SELECT 1 FROM favorite_target WHERE dso_id=?", (dso_id,)).fetchone()
