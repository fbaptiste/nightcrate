"""NightCrate Melotte list collection, matching, and lifecycle tests."""

from __future__ import annotations

import csv
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
from nightcrate.catalog_loader.melotte_loader import collect_melotte
from nightcrate.catalog_loader.reconcile import build_object_set
from nightcrate.catalog_loader.registry import CatalogSource

FIXTURES = Path(__file__).parent.parent / "fixtures" / "catalogs"


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "test.db")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


def _catalogs_root(tmp_path: Path) -> Path:
    root = tmp_path / "catalogs"
    openngc = root / "openngc"
    openngc.mkdir(parents=True)
    shutil.copy(FIXTURES / "openngc" / "mini_NGC.csv", openngc / "NGC.csv")
    shutil.copy(FIXTURES / "openngc" / "mini_addendum.csv", openngc / "addendum.csv")
    shutil.copy(FIXTURES / "openngc" / "version.json", openngc / "version.json")
    return root


def _sources(root: Path) -> dict[str, CatalogSource]:
    return {source.source_id: source for source in registry.get_sources(root)}


def _batch(root: Path):
    source = _sources(root)["nightcrate_melotte"]
    return collect_melotte({source.source_id: source}, frozenset({"melotte"}))


def _append_openngc_row(
    root: Path,
    filename: str,
    name: str,
    *,
    identifiers: str = "",
    common_name: str = "",
    size: str = "60",
) -> None:
    path = root / "openngc" / filename
    with path.open(encoding="utf-8", newline="") as handle:
        fieldnames = csv.DictReader(handle, delimiter=";").fieldnames
    assert fieldnames is not None
    row = dict.fromkeys(fieldnames, "")
    row.update(
        {
            "Name": name,
            "Type": "OCl",
            "RA": "05:00:00",
            "Dec": "+20:00:00",
            "Const": "Tau",
            "MajAx": size,
            "Identifiers": identifiers,
            "Common names": common_name,
        }
    )
    with path.open("a", encoding="utf-8", newline="") as handle:
        csv.DictWriter(handle, fieldnames=fieldnames, delimiter=";").writerow(row)


def _melotte_rows() -> list[dict[str, str]]:
    path = Path(registry._nightcrate_dir()) / "melotte.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        lines = [line for line in handle if line.strip() and not line.lstrip().startswith("#")]
    return list(csv.DictReader(lines))


def test_melotte_file_has_all_245_unique_numbers_and_five_standalones():
    rows = _melotte_rows()
    numbers = [int(row["melotte"]) for row in rows]
    standalone = [row for row in rows if not row["target_designation"]]

    assert len(rows) == 245
    assert len(set(numbers)) == 245
    assert sorted(numbers) == list(range(1, 246))
    assert [int(row["melotte"]) for row in standalone] == [20, 31, 66, 186, 227]


def test_melotte_registry_is_bundled_optional_and_uses_reviewed_credit(tmp_path: Path):
    catalog = registry.optional_catalog("melotte")

    assert catalog is not None
    assert catalog.display_name == "Melotte star clusters"
    assert catalog.kind == "nightcrate"
    assert catalog.source_ids == ("nightcrate_melotte",)
    assert catalog.fetch_specs == ()
    assert catalog.designation_catalogs == frozenset({"mel"})
    assert catalog.legacy_default is False
    assert catalog.credit == (
        "Melotte 1915, checked by NightCrate. Positions for five clusters from "
        "Hunt & Reffert 2023 or SIMBAD."
    )
    source = _sources(_catalogs_root(tmp_path))["nightcrate_melotte"]
    assert source.attribution == registry.MELOTTE_CITATION
    for wording in (
        "Melotte 1915, MmRAS 60, 175",
        "transcribed and checked by NightCrate",
        "Hunt & Reffert 2023, A&A 673, A114, or SIMBAD",
    ):
        assert wording in source.attribution


def test_collect_melotte_marks_reviewed_targets_and_builds_standalones(tmp_path: Path):
    rows = {row.source_key: row for row in _batch(_catalogs_root(tmp_path)).objects}

    assert len(rows) == 245
    assert rows["15"].cross_identifications == (("ic", "1805"),)
    assert rows["15"].evidence == "reviewed list"
    assert rows["15"].require_match is True
    assert rows["15"].columns["ra_deg"] is None
    assert rows["22"].cross_identifications == (("messier", "45"),)
    assert rows["25"].cross_identifications == (("caldwell", "41"),)
    assert rows["111"].cross_identifications == (("mel", "111"),)

    alpha_persei = rows["20"]
    assert alpha_persei.require_match is False
    assert alpha_persei.columns["obj_type"] == "OCl"
    assert alpha_persei.columns["common_name"] == "Alpha Persei Cluster"
    assert alpha_persei.columns["maj_axis_arcmin"] == 166.8
    assert alpha_persei.columns["openngc_notes"] == (
        "size is 2 x r50 (r50 1.390 deg) from Hunt & Reffert 2023 · Position: Hunt & Reffert 2023"
    )
    assert rows["31"].columns["maj_axis_arcmin"] is None
    assert rows["227"].columns["maj_axis_arcmin"] is None


def test_melotte_reconcile_merges_reviewed_targets_and_keeps_five_standalones(
    tmp_path: Path,
):
    root = _catalogs_root(tmp_path)
    _append_openngc_row(root, "NGC.csv", "IC1805", size="25")
    _append_openngc_row(
        root,
        "addendum.csv",
        "M045",
        identifiers="Mel 022",
        common_name="Pleiades",
        size="110",
    )
    _append_openngc_row(
        root,
        "addendum.csv",
        "C041",
        identifiers="Mel 025",
        common_name="Hyades",
        size="330",
    )
    _append_openngc_row(
        root,
        "addendum.csv",
        "Mel111",
        common_name="Coma Star Cluster",
        size="275",
    )

    built = build_object_set(_sources(root), None, frozenset({"melotte"}))

    for identifier, source_key in (
        ("15", "IC1805"),
        ("22", "M045"),
        ("25", "C041"),
        ("111", "Mel111"),
    ):
        owner_index = built.merges[("nightcrate_melotte", identifier)]
        assert built.objects[owner_index].source_key == source_key
        assert any(
            designation[:2] == ("mel", identifier)
            for designation in built.objects[owner_index].designations
        )
    assert (
        built.objects[built.merges[("nightcrate_melotte", "22")]].columns["maj_axis_arcmin"]
        == 110.0
    )
    assert (
        built.objects[built.merges[("nightcrate_melotte", "25")]].columns["common_name"] == "Hyades"
    )
    assert (
        built.objects[built.merges[("nightcrate_melotte", "111")]].columns["common_name"]
        == "Coma Star Cluster"
    )

    standalone = [obj for obj in built.objects if obj.source_id == "nightcrate_melotte"]
    assert {obj.source_key for obj in standalone} == {"20", "31", "66", "186", "227"}
    alpha_persei = next(obj for obj in standalone if obj.source_key == "20")
    assert alpha_persei.designations == (("mel", "20", True),)
    assert alpha_persei.columns["common_name"] == "Alpha Persei Cluster"


def test_melotte_off_claims_no_rows_from_reviewed_list(tmp_path: Path):
    root = _catalogs_root(tmp_path)

    built = build_object_set(_sources(root), None, frozenset())

    assert all(obj.source_id != "nightcrate_melotte" for obj in built.objects)
    assert all(entry.source_id != "nightcrate_melotte" for entry in built.entries)
    assert not any(source_id == "nightcrate_melotte" for source_id, _key in built.merges)


def test_melotte_load_remove_and_add_reactivates_same_object(
    db: sqlite3.Connection, tmp_path: Path
):
    root = _catalogs_root(tmp_path)
    write_choice(root, with_added(None, "melotte"))
    load_catalogs(db, root)
    row = db.execute(
        "SELECT d.id, d.common_name, d.maj_axis_arcmin FROM dso d "
        "JOIN dso_designation dd ON dd.dso_id=d.id "
        "WHERE dd.catalog='mel' AND dd.identifier='20'"
    ).fetchone()
    assert row is not None
    dso_id = int(row[0])
    assert tuple(row[1:]) == ("Alpha Persei Cluster", 166.8)
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (dso_id,))
    db.commit()

    write_choice(root, with_removed(read_choice(root), "melotte"))
    load_catalogs(db, root)
    assert db.execute("SELECT active FROM dso WHERE id=?", (dso_id,)).fetchone()[0] == 0

    write_choice(root, with_added(read_choice(root), "melotte"))
    load_catalogs(db, root)
    assert tuple(db.execute("SELECT id, active FROM dso WHERE id=?", (dso_id,)).fetchone()) == (
        dso_id,
        1,
    )
    assert db.execute("SELECT 1 FROM favorite_target WHERE dso_id=?", (dso_id,)).fetchone()
