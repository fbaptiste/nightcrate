"""Arp member collection, grouping, identity transfer, and lifecycle tests."""

from __future__ import annotations

import csv
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from nightcrate.catalog_loader import load_catalogs, registry
from nightcrate.catalog_loader.arp_loader import collect_arp
from nightcrate.catalog_loader.catalog_choice import (
    read_choice,
    with_added,
    with_removed,
    write_choice,
)
from nightcrate.catalog_loader.hash import file_sha256
from nightcrate.catalog_loader.reconcile import build_object_set
from nightcrate.catalog_loader.registry import CatalogSource

FIXTURES = Path(__file__).parent.parent / "fixtures" / "catalogs"
SAMPLE_ROOT = Path(__file__).parents[3] / ".superpowers" / "codex" / "v0.44.0" / "samples"
FULL_SAMPLE = SAMPLE_ROOT / "full_VII_192_arplist.tsv"
ARP_FILENAME = "arp_VII_192.tsv"
MCG_FILES = ("mcg_VII_62A.tsv", "mcg_VII_100.tsv")


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "test.db")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


def _catalogs_root(tmp_path: Path, *, installed: bool = False, include_mcg: bool = False) -> Path:
    root = tmp_path / "catalogs"
    openngc = root / "openngc"
    vizier = root / "vizier"
    openngc.mkdir(parents=True)
    vizier.mkdir()
    shutil.copy(FIXTURES / "openngc" / "mini_NGC.csv", openngc / "NGC.csv")
    shutil.copy(FIXTURES / "openngc" / "mini_addendum.csv", openngc / "addendum.csv")
    shutil.copy(FIXTURES / "openngc" / "version.json", openngc / "version.json")
    shutil.copy(FIXTURES / "vizier" / "mini_arp.tsv", vizier / ARP_FILENAME)
    if include_mcg:
        shutil.copy(FIXTURES / "vizier" / "mini_mcg.tsv", vizier / MCG_FILES[0])
        shutil.copy(FIXTURES / "vizier" / "mini_mcg_v5.tsv", vizier / MCG_FILES[1])
    if installed:
        filenames = [ARP_FILENAME, *(MCG_FILES if include_mcg else ())]
        version = {
            "files": {
                filename: {
                    "sha256": file_sha256(vizier / filename),
                    "fetch_date": "2026-11-02T00:00:00+00:00",
                }
                for filename in filenames
            }
        }
        (vizier / "version.json").write_text(json.dumps(version), encoding="utf-8")
    return root


def _sources(root: Path) -> dict[str, CatalogSource]:
    return {source.source_id: source for source in registry.get_sources(root)}


def _batch(root: Path):
    sources = _sources(root)
    return collect_arp(
        {source_id: sources[source_id] for source_id in ("vizier_arp", "nightcrate_arp_members")},
        frozenset({"arp"}),
    )


def _append_openngc(root: Path, *rows: tuple[str, str, str, str], obj_type: str = "G") -> None:
    path = root / "openngc" / "NGC.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        fieldnames = csv.DictReader(handle, delimiter=";").fieldnames
    assert fieldnames is not None
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=";")
        for name, ra, dec, identifiers in rows:
            row = dict.fromkeys(fieldnames, "")
            row.update({"Name": name, "Type": obj_type, "RA": ra, "Dec": dec})
            row["Identifiers"] = identifiers
            writer.writerow(row)


def _designation_members(built, group_identifier: str) -> set[tuple[str, str]]:
    group = next(group for group in built.groups if group.identifier == group_identifier)
    return {
        (catalog, identifier)
        for index in group.member_indexes
        for catalog, identifier, _primary in built.objects[index].designations
    }


def test_arp_registry_includes_reviewed_list_and_readme_credit(tmp_path: Path):
    catalog = registry.optional_catalog("arp")

    assert catalog is not None
    assert catalog.display_name == "Arp peculiar galaxies"
    assert catalog.source_ids == ("vizier_arp", "nightcrate_arp_members")
    assert catalog.legacy_default is False
    assert catalog.designation_catalogs == frozenset({"arp"})
    assert len(catalog.fetch_specs) == 1
    assert catalog.fetch_specs[0].catalog_id == "VII/192/arplist"
    assert catalog.fetch_specs[0].output_filename == ARP_FILENAME
    assert catalog.fetch_specs[0].additional_params == {"-out.add": "_RAJ2000,_DEJ2000"}
    assert catalog.credit == "Arp 1966, from Webb's index. Retrieved via VizieR VII/192."
    sources = _sources(_catalogs_root(tmp_path))
    assert sources["vizier_arp"].attribution == registry.ARP_CITATION
    assert sources["nightcrate_arp_members"].category == "nightcrate"
    for wording in ("Arp, H. 1966", "Webb, D. 1996", "(VizieR VII/192)"):
        assert wording in sources["vizier_arp"].attribution


def test_collect_arp_uses_five_field_keys_reviewed_csv_and_standalone_columns(
    tmp_path: Path,
):
    batch = _batch(_catalogs_root(tmp_path))
    rows = {row.source_key: row for row in batch.objects}
    quoted = rows["157:01 24 35.2:+03 47 37:NGC 0520:S pec, Pair"]
    arp_62 = [row for key, row in rows.items() if key.startswith("62:")]

    assert len(rows) == 23
    assert set(batch.source_hashes) == {"vizier_arp", "nightcrate_arp_members"}
    assert len(arp_62) == 2
    assert {row.identifier for row in arp_62} == {"+07-25-002", "+07-25-002b"}
    assert all(row.evidence == "reviewed list" for row in arp_62)
    assert quoted.catalog == "ngc"
    assert quoted.identifier == "520"
    assert quoted.evidence == "reviewed list"
    assert quoted.columns["mag_v"] == 11.5
    assert quoted.columns["maj_axis_arcmin"] == 4.5
    assert quoted.columns["min_axis_arcmin"] == 1.8


def test_arp_system_rows_create_typed_standalones_and_leave_galaxies_as_g(
    tmp_path: Path,
):
    built = build_object_set(_sources(_catalogs_root(tmp_path)), None, frozenset({"arp"}))

    def object_with(catalog: str, identifier: str):
        matches = [
            obj
            for obj in built.objects
            if any(
                item_catalog == catalog and item_identifier == identifier
                for item_catalog, item_identifier, _primary in obj.designations
            )
        ]
        assert len(matches) == 1
        return matches[0]

    triple = object_with("arp", "251")
    chain = object_with("arp", "330")
    pair = object_with("arp", "338")
    galaxy = object_with("mcg", "-02-01-052")
    double_system_component = next(
        obj
        for obj in built.objects
        if obj.source_key == "45:14 19 51.0:+51 54 16:UGC 09178:Double System"
    )

    assert {("arp", "251"), ("mcg", "-02-03-037")} <= {
        (catalog, identifier) for catalog, identifier, _primary in triple.designations
    }
    assert triple.source_id == "vizier_arp"
    assert triple.columns["obj_type"] == "GTrpl"
    assert chain.source_id == "vizier_arp"
    assert chain.columns["primary_designation"] == "Arp 330"
    assert chain.columns["obj_type"] == "GGroup"
    assert pair.source_id == "vizier_arp"
    assert pair.columns["primary_designation"] == "Arp 338"
    assert pair.columns["obj_type"] == "GPair"
    assert galaxy.columns["obj_type"] == "G"
    assert double_system_component.columns["obj_type"] == "G"
    arp_45 = next(group for group in built.groups if group.identifier == "45")
    assert {built.objects[index].columns["obj_type"] for index in arp_45.member_indexes} == {"G"}


def test_arp_157_designates_openngc_pair_instead_of_component(tmp_path: Path):
    root = _catalogs_root(tmp_path)
    _append_openngc(
        root,
        ("NGC0520", "01:24:35.2", "+03:47:37", ""),
        obj_type="GPair",
    )
    _append_openngc(root, ("NGC0520A", "01:24:34.8", "+03:47:34", ""))

    built = build_object_set(_sources(root), None, frozenset({"arp"}))
    arp_owners = [obj for obj in built.objects if ("arp", "157", False) in obj.designations]

    assert len(arp_owners) == 1
    pair = arp_owners[0]
    assert pair.source_id == "openngc"
    assert pair.columns["obj_type"] == "GPair"
    assert any(
        catalog == "ngc" and identifier == "520"
        for catalog, identifier, _primary in pair.designations
    )
    component = next(
        obj
        for obj in built.objects
        if any(
            catalog == "ngc" and identifier == "520A"
            for catalog, identifier, _primary in obj.designations
        )
    )
    assert all(
        catalog != "arp" or identifier != "157"
        for catalog, identifier, _primary in component.designations
    )


def test_arp_244_group_releases_openngc_alternate_and_arp_85_uses_reviewed_members(
    tmp_path: Path,
):
    root = _catalogs_root(tmp_path)
    _append_openngc(
        root,
        ("NGC4038", "12:01:52.8", "-18:51:54", "Arp 244"),
        ("NGC4039", "12:01:53.8", "-18:53:06", ""),
        ("NGC5194", "13:29:52.3", "+47:11:54", ""),
        ("NGC5195", "13:29:58.6", "+47:16:04", ""),
    )

    off = build_object_set(_sources(root), None, frozenset())
    on = build_object_set(_sources(root), None, frozenset({"arp"}))

    assert any(("arp", "244", False) in obj.designations for obj in off.objects)
    assert {("ngc", "4038"), ("ngc", "4039")} <= _designation_members(on, "244")
    assert not any(
        catalog == "arp" and identifier == "244"
        for obj in on.objects
        for catalog, identifier, _primary in obj.designations
    )
    assert {("ngc", "5194"), ("ngc", "5195")} <= _designation_members(on, "85")


def test_arp_repeated_names_follow_reviewed_rows_and_mtype_separates_arp_62(
    tmp_path: Path,
):
    built = build_object_set(_sources(_catalogs_root(tmp_path)), None, frozenset({"arp"}))

    assert {("mcg", "+04-01-007"), ("pgc", "1679585")} <= _designation_members(built, "249")
    assert {("mcg", "+07-25-002"), ("mcg", "+07-25-002b")} <= _designation_members(built, "62")
    source_keys = {
        built.objects[index].source_key
        for index in next(
            group for group in built.groups if group.identifier == "62"
        ).member_indexes
    }
    assert any(key.endswith(":E(c)") for key in source_keys)
    assert any(key.endswith(":SB") for key in source_keys)


def test_arp_single_member_is_designation_and_duplicate_rows_become_one_member(
    tmp_path: Path,
):
    root = _catalogs_root(tmp_path)
    _append_openngc(root, ("NGC2623", "08:38:24.1", "+25:45:01", ""))

    built = build_object_set(_sources(root), None, frozenset({"arp"}))
    ngc_5457_index = next(
        index
        for index, obj in enumerate(built.objects)
        if any(
            catalog == "ngc" and identifier == "5457"
            for catalog, identifier, _primary in obj.designations
        )
    )
    ngc_2623_index = next(
        index
        for index, obj in enumerate(built.objects)
        if any(
            catalog == "ngc" and identifier == "2623"
            for catalog, identifier, _primary in obj.designations
        )
    )
    ngc_5457 = built.objects[ngc_5457_index]
    ngc_2623 = built.objects[ngc_2623_index]

    assert ("arp", "26", False) in ngc_5457.designations
    assert all(group.identifier != "26" for group in built.groups)
    assert ("arp", "243", False) in ngc_2623.designations
    assert all(group.identifier != "243" for group in built.groups)
    assert (
        sum(
            index == ngc_2623_index
            for (source_id, source_key), index in built.merges.items()
            if source_id == "vizier_arp" and source_key.startswith("243:")
        )
        == 3
    )


def test_arp_anonymous_member_is_created_and_found_through_group(tmp_path: Path):
    built = build_object_set(_sources(_catalogs_root(tmp_path)), None, frozenset({"arp"}))
    group = next(group for group in built.groups if group.identifier == "196")
    members = [built.objects[index] for index in group.member_indexes]
    anonymous = next(obj for obj in members if obj.columns["primary_designation"] == "Arp 196")

    assert anonymous.designations == ()
    assert anonymous.columns["openngc_notes"] == "Listed as ARP 196"
    assert anonymous.columns["mag_v"] == 18.8
    assert len(group.member_indexes) == 2


def test_collect_arp_full_sample_counts_when_available():
    if not FULL_SAMPLE.exists():
        pytest.skip("local full Arp sample is not present")
    source = CatalogSource(
        "vizier_arp",
        "vizier",
        "Arp sample",
        FULL_SAMPLE,
        None,
        None,
        "CDS public",
        registry.ARP_CITATION,
        "arp",
    )
    editorial = next(
        item
        for item in registry.get_sources(Path("/tmp/no-catalogs"))
        if item.source_id == "nightcrate_arp_members"
    )

    batch = collect_arp(
        {"vizier_arp": source, "nightcrate_arp_members": editorial}, frozenset({"arp"})
    )

    assert len(batch.objects) == 592
    assert len(batch.groups) == 179
    assert len({row.source_key for row in batch.objects}) == 592
    assert sum(row.evidence == "reviewed list" for row in batch.objects) == 337


def test_arp_added_after_mcg_then_mcg_removed_keeps_member_id(
    db: sqlite3.Connection, tmp_path: Path
):
    root = _catalogs_root(tmp_path, installed=True, include_mcg=True)
    write_choice(root, with_added(None, "mcg"))
    load_catalogs(db, root)
    mcg_id = int(
        db.execute(
            "SELECT dso_id FROM dso_designation WHERE catalog='mcg' AND identifier='+07-25-002'"
        ).fetchone()[0]
    )
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (mcg_id,))
    db.commit()

    write_choice(root, with_added(read_choice(root), "arp"))
    load_catalogs(db, root)
    assert (
        db.execute(
            "SELECT dso_id FROM dso_source_entry e "
            "JOIN dso_catalog_source s ON s.id=e.source_catalog_id "
            "WHERE s.source_id='vizier_arp' AND e.source_key LIKE '62:%:SB'"
        ).fetchone()[0]
        == mcg_id
    )

    write_choice(root, with_removed(read_choice(root), "mcg"))
    load_catalogs(db, root)
    assert (
        db.execute(
            "SELECT dso_id FROM dso_designation WHERE catalog='mcg' AND identifier='+07-25-002'"
        ).fetchone()[0]
        == mcg_id
    )
    assert db.execute("SELECT 1 FROM favorite_target WHERE dso_id=?", (mcg_id,)).fetchone()


def test_arp_load_remove_and_add_reactivates_same_object(db: sqlite3.Connection, tmp_path: Path):
    root = _catalogs_root(tmp_path, installed=True)
    write_choice(root, with_added(None, "arp"))
    load_catalogs(db, root)
    dso_id = int(
        db.execute(
            "SELECT dso_id FROM dso_designation WHERE catalog='mcg' AND identifier='+07-25-002b'"
        ).fetchone()[0]
    )
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (dso_id,))
    db.commit()

    write_choice(root, with_removed(read_choice(root), "arp"))
    load_catalogs(db, root)
    assert db.execute("SELECT active FROM dso WHERE id=?", (dso_id,)).fetchone()[0] == 0

    write_choice(root, with_added(read_choice(root), "arp"))
    load_catalogs(db, root)
    assert tuple(db.execute("SELECT id, active FROM dso WHERE id=?", (dso_id,)).fetchone()) == (
        dso_id,
        1,
    )
