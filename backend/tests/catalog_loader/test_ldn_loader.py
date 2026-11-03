"""LDN catalog collection, Barnard matching, grouping, and lifecycle tests."""

from __future__ import annotations

import json
import logging
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
from nightcrate.catalog_loader.ldn_loader import _barnard_ids, collect_ldn
from nightcrate.catalog_loader.loader import prepare_removal_step
from nightcrate.catalog_loader.reconcile import apply_object_set, build_object_set
from nightcrate.catalog_loader.registry import CatalogSource

FIXTURES = Path(__file__).parent.parent / "fixtures" / "catalogs"
FULL_SAMPLE = (
    Path(__file__).parents[3]
    / ".superpowers"
    / "codex"
    / "v0.44.0"
    / "samples"
    / "full_VII_7A_ldn.tsv"
)
LDN_FILENAME = "ldn_VII_7A.tsv"


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
    shutil.copy(FIXTURES / "vizier" / "mini_barnard.tsv", vizier / "barnard_VII_220.tsv")
    catalog_path = vizier / LDN_FILENAME
    shutil.copy(FIXTURES / "vizier" / "mini_ldn.tsv", catalog_path)
    if installed:
        version = {
            "files": {
                LDN_FILENAME: {
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
    source = _sources(root)["vizier_ldn"]
    return collect_ldn({source.source_id: source}, frozenset({"barnard", "ldn"}))


def _append_barnard_group_members(root: Path) -> None:
    path = root / "vizier" / "barnard_VII_220.tsv"
    with path.open("a", encoding="utf-8") as handle:
        handle.write("292.30\t7.00\t331\t20\t\t\n292.40\t7.10\t332\t20\t\t\n")


def test_ldn_registry_projects_used_columns_and_uses_readme_credit(tmp_path: Path):
    catalog = registry.optional_catalog("ldn")

    assert catalog is not None
    assert catalog.display_name == "LDN (Lynds dark nebulae)"
    assert catalog.legacy_default is False
    assert catalog.source_ids == ("vizier_ldn",)
    assert catalog.fetch_specs[0].output_filename == LDN_FILENAME
    assert catalog.fetch_specs[0].required_columns == (
        "_RAJ2000",
        "_DEJ2000",
        "LDN",
        "Area",
        "Opacity",
        "Barn",
    )
    assert catalog.fetch_specs[0].additional_params == {"-out.add": "_RAJ2000,_DEJ2000"}
    assert catalog.credit == "Lynds 1962. Retrieved via VizieR VII/7A."
    source = _sources(_catalogs_root(tmp_path))["vizier_ldn"]
    assert source.attribution == registry.LDN_CITATION
    for wording in (
        "Lynds, B.T. 1962",
        "Catalogue of Dark Nebulae",
        "Astrophysical Journal Supplement Series 7, 1",
        "(VizieR VII/7A)",
        registry.CDS_CITATION,
    ):
        assert wording in source.attribution


def test_collect_ldn_skips_missing_numbers_and_builds_size_only_for_matching(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    caplog.set_level(logging.INFO, logger="nightcrate.catalog_loader.ldn")

    rows = {row.source_key: row for row in _batch(_catalogs_root(tmp_path)).objects}

    assert set(rows) == {"66", "532", "534", "607", "654", "694"}
    assert "skipped 4 rows without an LDN number" in caplog.text
    assert rows["694"].columns["maj_axis_arcmin"] is None
    assert rows["694"].match_size_arcmin == pytest.approx(22.352, rel=1e-3)
    assert rows["694"].match_size_ratio_max == 3.0
    assert rows["694"].cross_identifications == (("barnard", "143"),)
    assert rows["654"].cross_identifications == ()
    assert rows["607"].columns["dec_deg"] == pytest.approx(-0.6936)
    assert rows["607"].columns["openngc_notes"] == "Area 0.147 deg² · opacity 2 (6 darkest)"
    assert all(row.columns["obj_type"] == "DrkN" for row in rows.values())


def test_ldn_packed_barnard_names_parse_to_individual_normalized_ids(tmp_path: Path):
    batch = _batch(_catalogs_root(tmp_path))
    rows = {row.source_key: row for row in batch.objects}
    group = next(group for group in batch.groups if group.identifier == "534")

    assert _barnard_ids("119A117A323") == ("119A", "117A", "323")
    assert group.member_designations == (
        ("barnard", "111"),
        ("barnard", "108"),
        ("barnard", "119A"),
        ("barnard", "117A"),
        ("barnard", "323"),
        ("barnard", "325"),
    )
    assert rows["534"].columns["maj_axis_arcmin"] is None


def test_collect_ldn_full_sample_counts_four_skipped_rows_when_available(
    caplog: pytest.LogCaptureFixture,
):
    if not FULL_SAMPLE.exists():
        pytest.skip("local full LDN sample is not present")
    source = CatalogSource(
        "vizier_ldn",
        "vizier",
        "LDN sample",
        FULL_SAMPLE,
        None,
        None,
        "CDS public",
        registry.LDN_CITATION,
        "ldn",
    )
    caplog.set_level(logging.INFO, logger="nightcrate.catalog_loader.ldn")

    objects = collect_ldn({source.source_id: source}, frozenset({"ldn"})).objects

    assert len(objects) == 1787
    assert "skipped 4 rows without an LDN number" in caplog.text


def test_ldn_reconcile_merges_one_comparable_id_and_groups_multiple_or_large_clouds(
    tmp_path: Path,
):
    root = _catalogs_root(tmp_path)
    _append_barnard_group_members(root)

    built = build_object_set(_sources(root), None, frozenset({"barnard", "ldn"}))

    barnard_143 = next(
        index
        for index, obj in enumerate(built.objects)
        if ("barnard", "143", True) in obj.designations
    )
    assert built.merges[("vizier_ldn", "694")] == barnard_143
    assert ("ldn", "694", False) in built.objects[barnard_143].designations
    match = next(match for match in built.stated_matches if match.identifier == "694")
    assert match.entry_size_arcmin == pytest.approx(22.352, rel=1e-3)
    assert match.target_size_arcmin == 30.0
    assert all(group.identifier != "694" for group in built.groups)

    single_large = next(group for group in built.groups if group.identifier == "66")
    assert [built.objects[index].source_key for index in single_large.member_indexes] == ["72"]
    multiple = next(group for group in built.groups if group.identifier == "654")
    assert {built.objects[index].source_key for index in multiple.member_indexes} == {"331", "332"}
    assert all(built.objects[index].source_key != "654" for index in multiple.member_indexes)


def test_ldn_with_barnard_off_is_standalone_without_groups(tmp_path: Path):
    root = _catalogs_root(tmp_path)
    source = _sources(root)["vizier_ldn"]

    built = build_object_set(_sources(root), None, frozenset({"ldn"}))
    ldn_objects = [obj for obj in built.objects if obj.source_id == "vizier_ldn"]
    batch = collect_ldn({source.source_id: source}, frozenset({"ldn"}))

    assert len(ldn_objects) == 6
    assert not any(source_id == "vizier_ldn" for source_id, _key in built.merges)
    assert built.groups == ()
    assert batch.groups == ()
    assert all(row.cross_identifications == () for row in batch.objects)


def test_ldn_and_barnard_transfer_identity_in_both_removal_orders_with_preview(
    db: sqlite3.Connection, tmp_path: Path
):
    root = _catalogs_root(tmp_path, installed=True)
    load_catalogs(db, root)
    barnard_id = int(
        db.execute(
            "SELECT dso_id FROM dso_designation WHERE catalog='barnard' AND identifier='143'"
        ).fetchone()[0]
    )
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (barnard_id,))
    db.commit()

    write_choice(root, with_added(read_choice(root), "ldn"))
    load_catalogs(db, root)
    assert (
        db.execute(
            "SELECT dso_id FROM dso_designation WHERE catalog='ldn' AND identifier='694'"
        ).fetchone()[0]
        == barnard_id
    )

    preview_plan = prepare_removal_step(db, root, "barnard")
    assert preview_plan.object_set is not None
    preview = apply_object_set(
        db,
        preview_plan.object_set,
        (),
        removed_catalogs=frozenset({"barnard"}),
        dry_run=True,
    )
    write_choice(root, with_removed(read_choice(root), "barnard"))
    removed_barnard = load_catalogs(db, root)

    assert (removed_barnard.objects_removed, removed_barnard.objects_kept) == (
        preview.deleted,
        preview.kept_linked,
    )
    assert (
        db.execute(
            "SELECT dso_id FROM dso_designation WHERE catalog='ldn' AND identifier='694'"
        ).fetchone()[0]
        == barnard_id
    )
    assert db.execute("SELECT 1 FROM favorite_target WHERE dso_id=?", (barnard_id,)).fetchone()

    assert db.execute("SELECT COUNT(*) FROM dso WHERE id=?", (barnard_id,)).fetchone()[0] == 1

    write_choice(root, with_added(read_choice(root), "barnard"))
    load_catalogs(db, root)
    write_choice(root, with_removed(read_choice(root), "ldn"))
    load_catalogs(db, root)

    assert (
        db.execute(
            "SELECT dso_id FROM dso_designation WHERE catalog='barnard' AND identifier='143'"
        ).fetchone()[0]
        == barnard_id
    )
    assert db.execute("SELECT 1 FROM favorite_target WHERE dso_id=?", (barnard_id,)).fetchone()

    write_choice(root, with_added(read_choice(root), "ldn"))
    load_catalogs(db, root)
    assert (
        db.execute(
            "SELECT dso_id FROM dso_designation WHERE catalog='ldn' AND identifier='694'"
        ).fetchone()[0]
        == barnard_id
    )
