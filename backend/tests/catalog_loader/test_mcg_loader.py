"""MCG collection, reconciliation, and lifecycle tests."""

from __future__ import annotations

import csv
import json
import logging
import shutil
import sqlite3
import time
from pathlib import Path

import pytest

from nightcrate.catalog_loader import load_catalogs, registry
from nightcrate.catalog_loader.catalog_choice import (
    read_choice,
    with_added,
    with_removed,
    write_choice,
)
from nightcrate.catalog_loader.designations import canonical_identifier
from nightcrate.catalog_loader.hash import file_sha256
from nightcrate.catalog_loader.loader import _primary_designation_due
from nightcrate.catalog_loader.mcg_loader import collect_mcg
from nightcrate.catalog_loader.reconcile import build_object_set
from nightcrate.catalog_loader.registry import CatalogSource

FIXTURES = Path(__file__).parent.parent / "fixtures" / "catalogs"
SAMPLE_ROOT = Path(__file__).parents[3] / ".superpowers" / "codex" / "v0.44.0" / "samples"
FULL_SAMPLES = {
    "vizier_mcg": SAMPLE_ROOT / "full_VII_62A_mcg.tsv",
    "vizier_mcg_v5": SAMPLE_ROOT / "full_VII_100_catalog.tsv",
}
MCG_FILES = {
    "vizier_mcg": "mcg_VII_62A.tsv",
    "vizier_mcg_v5": "mcg_VII_100.tsv",
}
MINI_FILES = {
    "vizier_mcg": "mini_mcg.tsv",
    "vizier_mcg_v5": "mini_mcg_v5.tsv",
}


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
    for source_id, filename in MCG_FILES.items():
        shutil.copy(FIXTURES / "vizier" / MINI_FILES[source_id], vizier / filename)
    if installed:
        version = {
            "files": {
                filename: {
                    "sha256": file_sha256(vizier / filename),
                    "fetch_date": "2026-11-02T00:00:00+00:00",
                }
                for filename in MCG_FILES.values()
            }
        }
        (vizier / "version.json").write_text(json.dumps(version), encoding="utf-8")
    return root


def _sources(root: Path) -> dict[str, CatalogSource]:
    return {source.source_id: source for source in registry.get_sources(root)}


def _batch(root: Path):
    sources = _sources(root)
    return collect_mcg(
        {source_id: sources[source_id] for source_id in MCG_FILES}, frozenset({"mcg"})
    )


def _append_openngc_rows(root: Path, *rows: tuple[str, str]) -> None:
    path = root / "openngc" / "NGC.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        fieldnames = csv.DictReader(handle, delimiter=";").fieldnames
    assert fieldnames is not None
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=";")
        for name, major_axis in rows:
            row = dict.fromkeys(fieldnames, "")
            row.update(
                {
                    "Name": name,
                    "Type": "G",
                    "RA": "05:33:32.9",
                    "Dec": "-00:39:59",
                    "Const": "Ori",
                    "MajAx": major_axis,
                }
            )
            writer.writerow(row)


def test_mcg_registry_has_two_tables_and_readme_credit(tmp_path: Path):
    catalog = registry.optional_catalog("mcg")

    assert catalog is not None
    assert catalog.display_name == "MCG (Morphological Catalogue of Galaxies)"
    assert catalog.source_ids == tuple(MCG_FILES)
    assert catalog.legacy_default is False
    assert catalog.designation_catalogs == frozenset({"mcg"})
    assert [spec.catalog_id for spec in catalog.fetch_specs] == [
        "VII/62A/mcg",
        "VII/100/catalog",
    ]
    assert [spec.output_filename for spec in catalog.fetch_specs] == list(MCG_FILES.values())
    assert all(
        spec.additional_params == {"-out.add": "_RAJ2000,_DEJ2000"} for spec in catalog.fetch_specs
    )
    assert catalog.credit == (
        "Vorontsov-Velyaminov et al. 1962–1974. Retrieved via VizieR VII/62A and VII/100."
    )
    sources = _sources(_catalogs_root(tmp_path))
    assert {sources[source_id].attribution for source_id in MCG_FILES} == {registry.MCG_CITATION}
    for wording in (
        "Vorontsov-Velyaminov",
        "Morphological Catalogue of Galaxies",
        "(VizieR VII/62A, VII/100)",
        registry.CDS_CITATION,
    ):
        assert wording in sources["vizier_mcg"].attribution


def test_collect_mcg_converts_sizes_magnitude_and_keeps_first_duplicate(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    caplog.set_level(logging.INFO, logger="nightcrate.catalog_loader.mcg")

    batch = _batch(_catalogs_root(tmp_path))
    rows = {row.source_key: row for row in batch.objects}

    assert len(batch.objects) == 6
    assert set(batch.source_hashes) == set(MCG_FILES)
    assert "skipped 1 repeated identifiers" in caplog.text
    assert rows["+12-12-005"].columns["ra_deg"] == 184.3339
    assert rows["+07-02-016"].columns["primary_designation"] == "MCG +07-02-016"
    assert rows["+07-02-016"].columns["maj_axis_arcmin"] == 160.0
    assert rows["+07-02-016"].columns["min_axis_arcmin"] == 45.0
    assert rows["+07-25-002"].columns["mag_b"] == 14.0
    assert rows["+12-12-005"].cross_identifications == (("ngc", "4250"),)
    assert rows["+12-12-005"].match_size_arcmin == pytest.approx(1.7)
    assert rows["+12-12-005"].match_size_ratio_max == 3.0
    assert rows["+12-12-005"].columns["openngc_notes"] == "Also NGC 4250:"
    assert rows["-02-01-051"].cross_identifications == (("ic", "1875"),)
    assert rows["-02-01-051"].match_size_ratio_max == 3.0
    assert rows["-02-01-052"].cross_identifications == (("ngc", "4656"),)
    assert rows["-02-01-052"].match_size_ratio_max == 3.0
    assert rows["+07-25-002"].cross_identifications == (("ngc", "2207A"),)
    assert rows["+07-25-002"].match_size_ratio_max is None
    assert rows["+07-25-002"].columns["openngc_notes"] == "Also NGC 2207a"
    assert rows["-06-01-001"].columns["maj_axis_arcmin"] == 0.4
    assert rows["-06-01-001"].columns["min_axis_arcmin"] == 0.3
    assert rows["-06-01-001"].columns["mag_b"] is None
    assert rows["-06-01-001"].columns["openngc_notes"] == (
        "Catalog magnitude 15.50 (mixed sources)"
    )
    assert rows["-06-01-001"].cross_identifications == (("ngc", "520"),)
    assert rows["-06-01-001"].match_size_ratio_max is None


def test_mcg_punctuated_names_gate_by_size_and_suffixes_keep_the_component(
    tmp_path: Path,
):
    root = _catalogs_root(tmp_path)
    _append_openngc_rows(
        root,
        ("NGC4250", "2.0"),
        ("IC1875", "4.0"),
        ("NGC4656", ""),
        ("NGC2207A", "10.0"),
        ("NGC0520", "10.0"),
    )

    built = build_object_set(_sources(root), None, frozenset({"mcg"}))

    assert ("vizier_mcg", "+12-12-005") in built.merges
    assert ("vizier_mcg", "-02-01-051") not in built.merges
    assert ("vizier_mcg", "-02-01-052") not in built.merges
    assert ("vizier_mcg", "+07-25-002") in built.merges
    assert ("vizier_mcg_v5", "-06-01-001") in built.merges
    rejected = {
        obj.source_key: obj
        for obj in built.objects
        if obj.source_id == "vizier_mcg" and obj.source_key in {"-02-01-051", "-02-01-052"}
    }
    assert rejected["-02-01-051"].columns["openngc_notes"] == "Also IC 1875?"
    assert rejected["-02-01-052"].columns["openngc_notes"] == "Also NGC 4656/"
    suffix_owner = built.objects[built.merges[("vizier_mcg", "+07-25-002")]]
    assert any(designation[:2] == ("ngc", "2207A") for designation in suffix_owner.designations)


def test_mcg_openngc_alternate_and_ngc_column_merge_without_duplicate(tmp_path: Path):
    root = _catalogs_root(tmp_path)

    built = build_object_set(_sources(root), None, frozenset({"mcg"}))
    ngc_224 = next(
        index
        for index, obj in enumerate(built.objects)
        if any(
            catalog == "ngc" and identifier == "224"
            for catalog, identifier, _primary in obj.designations
        )
    )

    assert built.merges[("vizier_mcg", "+07-02-016")] == ngc_224
    assert ("mcg", "+07-02-016", False) in built.objects[ngc_224].designations
    assert sum(("mcg", "+07-02-016", False) in obj.designations for obj in built.objects) == 1
    match = next(
        item
        for item in built.stated_matches
        if item.catalog == "mcg" and item.identifier == "+07-02-016"
    )
    assert match.evidence == "OpenNGC alternate"


def test_mcg_two_digit_final_field_canonicalizes_to_loaded_identifier(tmp_path: Path):
    rows = {row.source_key: row for row in _batch(_catalogs_root(tmp_path)).objects}

    assert canonical_identifier("mcg", "-02-01-52") == "-02-01-052"
    assert rows[canonical_identifier("mcg", "-02-01-52")].identifier == "-02-01-052"


def test_collect_mcg_full_sample_counts_and_runtime_when_available(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
):
    missing = [path for path in FULL_SAMPLES.values() if not path.exists()]
    if missing:
        pytest.skip("local full MCG samples are not present")
    root = _catalogs_root(tmp_path)
    for source_id, path in FULL_SAMPLES.items():
        shutil.copy(path, root / "vizier" / MCG_FILES[source_id])
    caplog.set_level(logging.INFO, logger="nightcrate.catalog_loader.mcg")

    started = time.monotonic()
    built = build_object_set(_sources(root), None, frozenset({"mcg"}))
    elapsed = time.monotonic() - started

    batch = _batch(root)
    plain = [
        row
        for row in batch.objects
        if row.cross_identifications
        and row.match_size_ratio_max is None
        and "Also " not in str(row.columns["openngc_notes"])
    ]
    gated = [row for row in batch.objects if row.match_size_ratio_max == 3.0]
    suffix = [
        row
        for row in batch.objects
        if row.cross_identifications
        and row.match_size_ratio_max is None
        and "Also " in str(row.columns["openngc_notes"])
    ]
    notes_only = [
        row
        for row in batch.objects
        if not row.cross_identifications and "Also " in str(row.columns["openngc_notes"])
    ]
    gated_matched = [row for row in gated if (row.source_id, row.source_key) in built.merges]

    assert sum(entry.catalog_id == "mcg" for entry in built.entries) == 30_637
    assert len(plain) == 6_823
    assert len(gated_matched) == 0
    assert len(gated) - len(gated_matched) == 154
    assert len(suffix) == 167
    assert len(notes_only) == 5
    assert "skipped 5 repeated identifiers" in caplog.text
    assert elapsed < 15.0


def test_mcg_load_remove_and_add_reactivates_same_object(db: sqlite3.Connection, tmp_path: Path):
    root = _catalogs_root(tmp_path, installed=True)
    write_choice(root, with_added(None, "mcg"))
    load_catalogs(db, root)
    dso_id = int(
        db.execute(
            "SELECT dso_id FROM dso_designation WHERE catalog='mcg' AND identifier='-06-01-001'"
        ).fetchone()[0]
    )
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (dso_id,))
    db.commit()

    write_choice(root, with_removed(read_choice(root), "mcg"))
    load_catalogs(db, root)
    assert db.execute("SELECT active FROM dso WHERE id=?", (dso_id,)).fetchone()[0] == 0

    write_choice(root, with_added(read_choice(root), "mcg"))
    load_catalogs(db, root)
    assert tuple(db.execute("SELECT id, active FROM dso WHERE id=?", (dso_id,)).fetchone()) == (
        dso_id,
        1,
    )


def test_removed_mcg_project_target_repairs_legacy_primary_once(
    db: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch,
):
    root = _catalogs_root(tmp_path, installed=True)
    write_choice(root, with_added(None, "mcg"))
    load_catalogs(db, root)
    dso_id = int(
        db.execute(
            """
            SELECT dso_id FROM dso_designation
            WHERE catalog='mcg' AND identifier='+07-25-002' AND is_primary=1
            """
        ).fetchone()[0]
    )
    db.execute("INSERT INTO project (name) VALUES ('Legacy MCG primary')")
    project_id = int(db.execute("SELECT last_insert_rowid()").fetchone()[0])
    db.execute(
        "INSERT INTO project_target (project_id, dso_id) VALUES (?, ?)",
        (project_id, dso_id),
    )
    db.execute(
        "UPDATE dso SET primary_designation='MCG+07-25-002' WHERE id=?",
        (dso_id,),
    )
    db.execute(
        """
        UPDATE dso_designation
        SET display_form='MCG+07-25-002', search_key='mcg+07-25-002'
        WHERE dso_id=? AND catalog='mcg' AND identifier='+07-25-002'
        """,
        (dso_id,),
    )
    db.commit()
    write_choice(root, with_removed(read_choice(root), "mcg"))

    load_catalogs(db, root)

    object_step_called = False

    def unexpected_object_step(*_args, **_kwargs):
        nonlocal object_step_called
        object_step_called = True
        raise AssertionError("retained primary repair repeated")

    monkeypatch.setattr(
        "nightcrate.catalog_loader.reconcile.apply_object_set",
        unexpected_object_step,
    )
    repeat = load_catalogs(db, root)

    primary = db.execute(
        """
        SELECT d.primary_designation, dd.display_form
        FROM dso d
        JOIN dso_designation dd ON dd.dso_id=d.id AND dd.is_primary=1
        WHERE d.id=?
        """,
        (dso_id,),
    ).fetchone()
    assert tuple(primary) == ("MCG +07-25-002", "MCG +07-25-002")
    assert not object_step_called
    assert next(result for result in repeat.results if result.source_id == "openngc").status == (
        "unchanged"
    )


def test_mcg_primary_display_mismatch_triggers_one_repair(
    db: sqlite3.Connection,
    tmp_path: Path,
):
    root = _catalogs_root(tmp_path, installed=True)
    write_choice(root, with_added(None, "mcg"))
    load_catalogs(db, root)
    primary = db.execute(
        """
        SELECT d.id, dd.display_form
        FROM dso d
        JOIN dso_designation dd ON dd.dso_id = d.id
        WHERE dd.catalog = 'mcg' AND dd.is_primary = 1
        ORDER BY d.id
        LIMIT 1
        """
    ).fetchone()
    dso_id = int(primary[0])
    expected_display = str(primary[1])
    db.execute(
        "UPDATE dso SET primary_designation=? WHERE id=?",
        (expected_display.replace("MCG ", "MCG"), dso_id),
    )
    db.commit()

    assert _primary_designation_due(db.cursor())
    load_catalogs(db, root)

    assert (
        db.execute("SELECT primary_designation FROM dso WHERE id=?", (dso_id,)).fetchone()[0]
        == expected_display
    )
    assert not _primary_designation_due(db.cursor())
