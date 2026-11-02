"""High-stakes identity and rollback tests for the catalog object step."""

from __future__ import annotations

import csv
import shutil
import sqlite3
import time
from dataclasses import replace
from pathlib import Path

import pytest

from nightcrate.catalog_loader.reconcile import (
    NewObject,
    ObjectSet,
    apply_object_set,
    build_object_set,
)
from nightcrate.catalog_loader.registry import CatalogSource

LEGACY = Path(__file__).parent.parent / "fixtures" / "catalogs" / "legacy"


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "test.db")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _source(root: Path, source_id: str, filename: str, parser: str, category: str):
    return CatalogSource(
        source_id,
        category,
        f"Fixture {source_id}",
        root / filename,
        "fixture",
        None,
        None,
        "fixture",
        parser,
    )


def _sources(root: Path = LEGACY) -> dict[str, CatalogSource]:
    items = (
        _source(root, "openngc", "NGC.csv", "openngc", "openngc"),
        _source(root, "openngc_addendum", "addendum.csv", "openngc", "openngc"),
        _source(root, "vizier_sharpless", "sharpless.tsv", "sharpless", "vizier"),
        _source(root, "vizier_barnard", "barnard.tsv", "barnard", "vizier"),
    )
    return {source.source_id: source for source in items}


def _legacy(db: sqlite3.Connection) -> ObjectSet:
    db.executescript((LEGACY / "legacy_dso.sql").read_text(encoding="utf-8"))
    return build_object_set(_sources(), LEGACY / "sharpless_crossref.csv")


def _with_premerge_barnard_pair(current: ObjectSet) -> ObjectSet:
    sources_without_addendum = _sources()
    sources_without_addendum.pop("openngc_addendum")
    standalone_set = build_object_set(sources_without_addendum, LEGACY / "sharpless_crossref.csv")
    standalone = next(
        obj
        for obj in standalone_set.objects
        if obj.source_id == "vizier_barnard" and obj.source_key == "33"
    )
    standalone = replace(
        standalone,
        designations=(),
        file_order=max(obj.file_order for obj in current.objects) + 1,
    )
    return replace(
        current,
        objects=(*current.objects, standalone),
        merges={
            key: target for key, target in current.merges.items() if key != ("vizier_barnard", "33")
        },
    )


def _ownership_sources(root: Path, *, reverse: bool = False) -> dict[str, CatalogSource]:
    root.mkdir()
    with (LEGACY / "NGC.csv").open(encoding="utf-8", newline="") as stream:
        fieldnames = csv.DictReader(stream, delimiter=";").fieldnames
    assert fieldnames is not None
    rows = []
    for name, alternate in (
        ("NGC0755", "0764"),
        ("IC0001", "0764"),
        ("NGC0764", ""),
        ("NGC6838", "6839"),
        ("NGC6839", ""),
    ):
        row = dict.fromkeys(fieldnames, "")
        row.update(
            {
                "Name": name,
                "Type": "G",
                "RA": "01:00:00",
                "Dec": "+01:00:00",
                "Const": "Psc",
                "NGC": alternate,
                "M": "071" if name == "NGC6838" else "",
            }
        )
        rows.append(row)
    if reverse:
        rows.reverse()
    for filename in ("NGC.csv", "addendum.csv"):
        with (root / filename).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter=";")
            writer.writeheader()
            if filename == "NGC.csv":
                writer.writerows(rows)
    (root / "sharpless.tsv").write_text(
        "_RAJ2000\t_DEJ2000\tSh2\tDiam\tClass\n"
        "deg\tdeg\t--\tarcmin\t--\n"
        "--------\t--------\t---\t------\t-----\n",
        encoding="utf-8",
    )
    (root / "barnard.tsv").write_text(
        "_RAJ2000\t_DEJ2000\tBarn\tDiam\tDurch\tNames\n"
        "deg\tdeg\t--\tarcmin\t--\t--\n"
        "--------\t--------\t---\t------\t--\t--\n",
        encoding="utf-8",
    )
    return _sources(root)


def _cross_source_sources(root: Path, source_ids: tuple[str, ...]) -> dict[str, CatalogSource]:
    root.mkdir()
    with (LEGACY / "NGC.csv").open(encoding="utf-8", newline="") as stream:
        fieldnames = csv.DictReader(stream, delimiter=";").fieldnames
    assert fieldnames is not None
    row = dict.fromkeys(fieldnames, "")
    row.update(
        {
            "Name": "NGC0777",
            "Type": "G",
            "RA": "02:00:00",
            "Dec": "+02:00:00",
            "Const": "Psc",
        }
    )
    filenames = {"openngc": "NGC.csv", "openngc_addendum": "addendum.csv"}
    for source_id, filename in filenames.items():
        with (root / filename).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter=";")
            writer.writeheader()
            if source_id in source_ids:
                writer.writerow(row)
    (root / "sharpless.tsv").write_text(
        "_RAJ2000\t_DEJ2000\tSh2\tDiam\tClass\n"
        "deg\tdeg\t--\tarcmin\t--\n"
        "--------\t--------\t---\t------\t-----\n",
        encoding="utf-8",
    )
    (root / "barnard.tsv").write_text(
        "_RAJ2000\t_DEJ2000\tBarn\tDiam\tDurch\tNames\n"
        "deg\tdeg\t--\tarcmin\t--\t--\n"
        "--------\t--------\t---\t------\t--\t--\n",
        encoding="utf-8",
    )
    return _sources(root)


def _snapshot(db: sqlite3.Connection, table: str) -> list[tuple]:
    return [tuple(row) for row in db.execute(f'SELECT * FROM "{table}" ORDER BY id')]  # nosec B608


def test_one_time_step_on_legacy_fixture(db: sqlite3.Connection):
    object_set = _legacy(db)
    before_ids = _snapshot(db, "dso")
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (5)")
    db.execute("INSERT INTO project (name) VALUES ('Legacy')")
    project_id = int(db.execute("SELECT id FROM project WHERE name='Legacy'").fetchone()[0])
    db.execute("INSERT INTO project_target (project_id, dso_id) VALUES (?, 1)", (project_id,))
    target_id = int(db.execute("SELECT id FROM project_target").fetchone()[0])
    db.execute(
        """
        INSERT INTO sub_frame (project_id, content_hash, project_target_id, date_obs_utc)
        VALUES (?, 'legacy-frame', ?, '2026-01-01')
        """,
        (project_id, target_id),
    )
    db.execute(
        """
        INSERT INTO project_solve (
            project_id, image_path, image_width, image_height, center_ra_deg,
            center_dec_deg, cd1_1, cd1_2, cd2_1, cd2_2, crpix1, crpix2
        ) VALUES (?, 'x.fits', 10, 10, 0, 0, 1, 0, 0, 1, 5, 5)
        """,
        (project_id,),
    )
    solve_id = int(db.execute("SELECT id FROM project_solve").fetchone()[0])
    db.execute("INSERT INTO project_dso (solve_id, dso_id) VALUES (?, 3)", (solve_id,))
    db.commit()

    report = apply_object_set(db, object_set, ())

    assert report.inserted == report.merged == 0
    assert report.removed == 1
    assert [row[0] for row in before_ids] == [row[0] for row in _snapshot(db, "dso")]
    assert db.execute("SELECT COUNT(*) FROM dso WHERE source_key IS NULL").fetchone()[0] == 1
    assert tuple(db.execute("SELECT active, source_key FROM dso WHERE id=10").fetchone()) == (
        0,
        None,
    )
    assert (
        db.execute(
            "SELECT dso_id FROM dso_designation WHERE catalog='ic' AND identifier='9'"
        ).fetchone()[0]
        == 5
    )
    assert db.execute("SELECT dso_id FROM favorite_target").fetchone()[0] == 5
    assert db.execute("SELECT dso_id FROM project_target").fetchone()[0] == 1
    assert db.execute("SELECT dso_id FROM project_dso").fetchone()[0] == 3
    assert db.execute("SELECT project_target_id FROM sub_frame").fetchone()[0] == target_id


def test_openngc_barnard_own_name_merges_matching_catalog_row(db: sqlite3.Connection):
    object_set = _legacy(db)
    addendum = next(obj for obj in object_set.objects if obj.source_key == "B033")
    assert ("barnard", "33", True) in addendum.designations
    assert not any(
        obj.source_id == "vizier_barnard" and obj.source_key == "33" for obj in object_set.objects
    )
    target_index = object_set.objects.index(addendum)
    assert object_set.merges[("vizier_barnard", "33")] == target_index


def test_barnard_own_name_merge_fresh_database_keeps_openngc_primary(
    db: sqlite3.Connection,
):
    current = build_object_set(_sources(), LEGACY / "sharpless_crossref.csv")

    apply_object_set(db, current, ())

    survivor = db.execute(
        "SELECT id, primary_designation FROM dso WHERE source_key='B033'"
    ).fetchone()
    assert tuple(survivor) == (survivor["id"], "B 33")
    assert (
        db.execute(
            "SELECT COUNT(*) FROM dso WHERE source_key='33' AND source_catalog_id="
            "(SELECT id FROM dso_catalog_source WHERE source_id='vizier_barnard')"
        ).fetchone()[0]
        == 0
    )
    assert (
        db.execute(
            "SELECT dso_id FROM dso_designation WHERE catalog='barnard' AND identifier='33'"
        ).fetchone()[0]
        == survivor["id"]
    )


def test_existing_barnard_pair_merges_to_survivor_and_moves_user_links(
    db: sqlite3.Connection,
):
    current = build_object_set(_sources(), LEGACY / "sharpless_crossref.csv")
    apply_object_set(db, _with_premerge_barnard_pair(current), ())
    survivor_id = int(db.execute("SELECT id FROM dso WHERE source_key='B033'").fetchone()[0])
    old_id = int(
        db.execute(
            """
            SELECT d.id FROM dso d JOIN dso_catalog_source s ON s.id=d.source_catalog_id
            WHERE s.source_id='vizier_barnard' AND d.source_key='33'
            """
        ).fetchone()[0]
    )
    db.execute("INSERT INTO project (name) VALUES ('Horsehead')")
    project_id = int(db.execute("SELECT last_insert_rowid()").fetchone()[0])
    db.execute(
        "INSERT INTO project_target (project_id, dso_id) VALUES (?, ?)",
        (project_id, old_id),
    )
    db.execute("INSERT INTO wishlist_section (name) VALUES ('Dark nebulae')")
    section_id = int(db.execute("SELECT last_insert_rowid()").fetchone()[0])
    db.execute(
        "INSERT INTO favorite_target (dso_id, section_id) VALUES (?, ?)",
        (old_id, section_id),
    )
    db.execute(
        "INSERT INTO location (name, latitude, longitude, timezone) VALUES ('Test', 0, 0, 'UTC')"
    )
    location_id = int(db.execute("SELECT last_insert_rowid()").fetchone()[0])
    db.execute(
        "INSERT INTO location_horizon (location_id, name, type, source) "
        "VALUES (?, 'Test', 'custom', 'drawn')",
        (location_id,),
    )
    horizon_id = int(db.execute("SELECT last_insert_rowid()").fetchone()[0])
    config_id = int(db.execute("SELECT id FROM telescope_configuration LIMIT 1").fetchone()[0])
    camera_id = int(db.execute("SELECT id FROM camera LIMIT 1").fetchone()[0])
    db.execute(
        "INSERT INTO rig (name, telescope_configuration_id, camera_id) VALUES ('Test', ?, ?)",
        (config_id, camera_id),
    )
    rig_id = int(db.execute("SELECT last_insert_rowid()").fetchone()[0])
    db.execute(
        """
        INSERT INTO target_plan (dso_id, location_id, horizon_id, rig_id)
        VALUES (?, ?, ?, ?)
        """,
        (old_id, location_id, horizon_id, rig_id),
    )
    plan_id = int(db.execute("SELECT last_insert_rowid()").fetchone()[0])
    db.commit()

    report = apply_object_set(db, current, ())

    assert report.merged == 1
    assert db.execute("SELECT COUNT(*) FROM dso WHERE id=?", (old_id,)).fetchone()[0] == 0
    assert db.execute("SELECT dso_id FROM project_target").fetchone()[0] == survivor_id
    assert db.execute("SELECT dso_id FROM favorite_target").fetchone()[0] == survivor_id
    assert db.execute("SELECT dso_id FROM target_plan WHERE id=?", (plan_id,)).fetchone()[0] == (
        survivor_id
    )
    repeat = apply_object_set(db, current, ())
    assert repeat.inserted == repeat.updated == repeat.removed == repeat.merged == 0


def test_barnard_merge_retains_unknown_reference_inactive(db: sqlite3.Connection):
    current = build_object_set(_sources(), LEGACY / "sharpless_crossref.csv")
    apply_object_set(db, _with_premerge_barnard_pair(current), ())
    old_id = int(
        db.execute(
            """
            SELECT d.id FROM dso d JOIN dso_catalog_source s ON s.id=d.source_catalog_id
            WHERE s.source_id='vizier_barnard' AND d.source_key='33'
            """
        ).fetchone()[0]
    )
    db.execute("CREATE TABLE zz_future_link (dso_id INTEGER REFERENCES dso(id))")
    db.execute("INSERT INTO zz_future_link VALUES (?)", (old_id,))
    db.commit()

    report = apply_object_set(db, current, ())

    assert tuple(
        db.execute("SELECT active, source_key FROM dso WHERE id=?", (old_id,)).fetchone()
    ) == (
        0,
        None,
    )
    assert report.kept_inactive_merge == 1


def test_barnard_ambiguous_own_names_stay_separate(tmp_path: Path):
    staged = tmp_path / "ambiguous"
    shutil.copytree(LEGACY, staged)
    b033 = next(
        line
        for line in (staged / "addendum.csv").read_text(encoding="utf-8").splitlines()
        if line.startswith("B033;")
    )
    with (staged / "NGC.csv").open("a", encoding="utf-8") as stream:
        stream.write(f"{b033}\n")

    object_set = build_object_set(_sources(staged), staged / "sharpless_crossref.csv")

    assert object_set.unresolved >= 1
    assert ("vizier_barnard", "33") not in object_set.merges
    assert any(
        obj.source_id == "vizier_barnard" and obj.source_key == "33" for obj in object_set.objects
    )


def test_barnard_suffix_does_not_match_unsuffixed_own_name(tmp_path: Path):
    staged = tmp_path / "suffix"
    shutil.copytree(LEGACY, staged)
    with (staged / "barnard.tsv").open("a", encoding="utf-8") as stream:
        stream.write("85.25\t-2.45\t033A\t6\t\tSuffix\n")

    object_set = build_object_set(_sources(staged), staged / "sharpless_crossref.csv")

    assert ("vizier_barnard", "33") in object_set.merges
    assert ("vizier_barnard", "33A") not in object_set.merges
    assert any(
        obj.source_id == "vizier_barnard" and obj.source_key == "33A" for obj in object_set.objects
    )


@pytest.mark.parametrize("reverse", (False, True))
def test_openngc_own_names_beat_real_alternate_claims_in_any_order(tmp_path: Path, reverse: bool):
    root = tmp_path / "ownership"
    object_set = build_object_set(_ownership_sources(root, reverse=reverse), None)
    owners = {
        (catalog, identifier): obj.source_key
        for obj in object_set.objects
        for catalog, identifier, _primary in obj.designations
    }
    assert owners[("ngc", "764")] == "NGC0764"
    assert owners[("ngc", "6839")] == "NGC6839"
    ic_object = next(obj for obj in object_set.objects if obj.source_key == "IC0001")
    assert ic_object.columns["primary_designation"] == "IC 1"
    assert [
        (catalog, identifier)
        for catalog, identifier, is_primary in ic_object.designations
        if is_primary
    ] == [("ic", "1")]


@pytest.mark.parametrize("reverse", (False, True))
def test_legacy_hash_match_precedes_shared_primary_designation(
    db: sqlite3.Connection, tmp_path: Path, reverse: bool
):
    root = tmp_path / "legacy-primary"
    current = build_object_set(_ownership_sources(root, reverse=reverse), None)
    apply_object_set(db, current, ())
    ids = {
        row["source_key"]: row["id"]
        for row in db.execute(
            "SELECT id, source_key FROM dso WHERE source_key IN ('IC0001', 'NGC0764')"
        )
    }
    hashes = {
        row["source_row_hash"]
        for row in db.execute(
            "SELECT source_row_hash FROM dso WHERE id IN (?, ?)",
            (ids["IC0001"], ids["NGC0764"]),
        )
    }
    assert len(hashes) == 2
    db.execute(
        "UPDATE dso SET source_key=NULL, primary_designation='NGC 764' WHERE id IN (?, ?)",
        (ids["IC0001"], ids["NGC0764"]),
    )
    db.execute("UPDATE dso_catalog_source SET keys_assigned=0 WHERE source_id='openngc'")
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (ids["IC0001"],))
    db.execute("INSERT INTO project (name) VALUES ('Legacy primary collision')")
    project_id = int(db.execute("SELECT last_insert_rowid()").fetchone()[0])
    db.execute(
        "INSERT INTO project_target (project_id, dso_id) VALUES (?, ?)",
        (project_id, ids["NGC0764"]),
    )
    db.commit()

    report = apply_object_set(db, current, ())

    assert report.inserted == report.removed == report.merged == 0
    assert {
        row["source_key"]: (row["id"], row["active"])
        for row in db.execute(
            "SELECT id, source_key, active FROM dso WHERE source_key IN ('IC0001', 'NGC0764')"
        )
    } == {
        "IC0001": (ids["IC0001"], 1),
        "NGC0764": (ids["NGC0764"], 1),
    }
    assert db.execute("SELECT dso_id FROM favorite_target").fetchone()[0] == ids["IC0001"]
    assert db.execute("SELECT dso_id FROM project_target").fetchone()[0] == ids["NGC0764"]
    repeat = apply_object_set(db, current, ())
    assert repeat.inserted == repeat.updated == repeat.removed == repeat.merged == 0


@pytest.mark.parametrize(
    ("old_source", "new_source"),
    (("openngc", "openngc_addendum"), ("openngc_addendum", "openngc")),
)
def test_legacy_hash_match_preserves_identity_across_openngc_sources(
    db: sqlite3.Connection, tmp_path: Path, old_source: str, new_source: str
):
    old = build_object_set(
        _cross_source_sources(tmp_path / "old", (old_source,)),
        None,
    )
    current = build_object_set(
        _cross_source_sources(tmp_path / "current", (new_source,)),
        None,
    )
    assert (
        old.objects[0].columns["source_row_hash"] == current.objects[0].columns["source_row_hash"]
    )
    apply_object_set(db, old, ())
    dso_id = int(db.execute("SELECT id FROM dso WHERE source_key='NGC0777'").fetchone()[0])
    db.execute("UPDATE dso SET source_key=NULL WHERE id=?", (dso_id,))
    db.execute(
        "UPDATE dso_catalog_source SET keys_assigned=0 WHERE source_id=?",
        (old_source,),
    )
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (dso_id,))
    db.execute("INSERT INTO project (name) VALUES ('Cross-source legacy row')")
    project_id = int(db.execute("SELECT last_insert_rowid()").fetchone()[0])
    db.execute(
        "INSERT INTO project_target (project_id, dso_id) VALUES (?, ?)",
        (project_id, dso_id),
    )
    db.commit()

    report = apply_object_set(db, current, ())

    assert report.inserted == report.removed == report.merged == 0
    moved = db.execute(
        """
        SELECT d.id, d.active, d.source_key, s.source_id
        FROM dso d JOIN dso_catalog_source s ON s.id=d.source_catalog_id
        WHERE d.id=?
        """,
        (dso_id,),
    ).fetchone()
    assert tuple(moved) == (dso_id, 1, "NGC0777", new_source)
    assert db.execute("SELECT dso_id FROM favorite_target").fetchone()[0] == dso_id
    assert db.execute("SELECT dso_id FROM project_target").fetchone()[0] == dso_id
    repeat = apply_object_set(db, current, ())
    assert repeat.inserted == repeat.updated == repeat.removed == repeat.merged == 0


def test_legacy_cross_source_hash_collision_is_left_to_source_local_matching(
    db: sqlite3.Connection, tmp_path: Path
):
    old = build_object_set(
        _cross_source_sources(tmp_path / "old", ("openngc_addendum",)),
        None,
    )
    current = build_object_set(
        _cross_source_sources(tmp_path / "current", ("openngc", "openngc_addendum")),
        None,
    )
    apply_object_set(db, old, ())
    old_id = int(db.execute("SELECT id FROM dso WHERE source_key='NGC0777'").fetchone()[0])
    db.execute("UPDATE dso SET source_key=NULL WHERE id=?", (old_id,))
    db.execute("UPDATE dso_catalog_source SET keys_assigned=0 WHERE source_id='openngc_addendum'")
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (old_id,))
    db.commit()

    report = apply_object_set(db, current, ())

    rows = db.execute(
        """
        SELECT d.id, s.source_id
        FROM dso d JOIN dso_catalog_source s ON s.id=d.source_catalog_id
        WHERE d.source_key='NGC0777' AND d.active=1
        ORDER BY s.source_id
        """
    ).fetchall()
    ids_by_source = {row["source_id"]: row["id"] for row in rows}
    assert set(ids_by_source) == {"openngc", "openngc_addendum"}
    assert ids_by_source["openngc_addendum"] == old_id
    assert ids_by_source["openngc"] != old_id
    assert report.inserted == 1
    assert report.removed == report.merged == 0
    assert db.execute("SELECT dso_id FROM favorite_target").fetchone()[0] == old_id
    repeat = apply_object_set(db, current, ())
    assert repeat.inserted == repeat.updated == repeat.removed == repeat.merged == 0


@pytest.mark.parametrize(
    ("keyed_source", "current_source"),
    (("openngc", "openngc_addendum"), ("openngc_addendum", "openngc")),
)
def test_cross_source_keyed_identity_precedes_legacy_hash_match(
    db: sqlite3.Connection, tmp_path: Path, keyed_source: str, current_source: str
):
    initial = build_object_set(
        _cross_source_sources(tmp_path / "initial", ("openngc", "openngc_addendum")),
        None,
    )
    current = build_object_set(
        _cross_source_sources(tmp_path / "current", (current_source,)),
        None,
    )
    apply_object_set(db, initial, ())
    ids = {
        row["source_id"]: row["id"]
        for row in db.execute(
            """
            SELECT d.id, s.source_id
            FROM dso d JOIN dso_catalog_source s ON s.id=d.source_catalog_id
            WHERE d.source_key='NGC0777'
            """
        )
    }
    keyed_id = ids[keyed_source]
    keyless_id = ids[current_source]
    db.execute("UPDATE dso SET source_key=NULL WHERE id=?", (keyless_id,))
    db.execute(
        "UPDATE dso_catalog_source SET keys_assigned=? WHERE source_id=?",
        (0, current_source),
    )
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (keyed_id,))
    db.execute("INSERT INTO project (name) VALUES ('Keyed identity precedence')")
    project_id = int(db.execute("SELECT last_insert_rowid()").fetchone()[0])
    db.execute(
        "INSERT INTO project_target (project_id, dso_id) VALUES (?, ?)",
        (project_id, keyed_id),
    )
    db.commit()

    report = apply_object_set(db, current, ())

    survivor = db.execute(
        """
        SELECT d.id, d.active, d.source_key, s.source_id
        FROM dso d JOIN dso_catalog_source s ON s.id=d.source_catalog_id
        WHERE d.id=?
        """,
        (keyed_id,),
    ).fetchone()
    assert tuple(survivor) == (keyed_id, 1, "NGC0777", current_source)
    assert tuple(
        db.execute("SELECT active, source_key FROM dso WHERE id=?", (keyless_id,)).fetchone()
    ) == (
        0,
        None,
    )
    assert report.inserted == report.merged == 0
    assert report.removed == 1
    assert db.execute("SELECT dso_id FROM favorite_target").fetchone()[0] == keyed_id
    assert db.execute("SELECT dso_id FROM project_target").fetchone()[0] == keyed_id
    repeat = apply_object_set(db, current, ())
    assert repeat.inserted == repeat.updated == repeat.removed == repeat.merged == 0


def test_own_name_repair_preserves_object_ids_and_user_links(
    db: sqlite3.Connection, tmp_path: Path
):
    root = tmp_path / "ownership"
    current = build_object_set(_ownership_sources(root), None)
    by_key = {obj.source_key: obj for obj in current.objects}

    def move_claim(alternate_key: str, own_key: str, identifier: str) -> None:
        alternate = by_key[alternate_key]
        owner = by_key[own_key]
        by_key[alternate_key] = replace(
            alternate,
            designations=(*alternate.designations, ("ngc", identifier, False)),
        )
        by_key[own_key] = replace(
            owner,
            designations=tuple(
                designation
                for designation in owner.designations
                if designation[:2] != ("ngc", identifier)
            ),
        )

    move_claim("NGC0755", "NGC0764", "764")
    move_claim("NGC6838", "NGC6839", "6839")
    old = replace(current, objects=tuple(by_key[obj.source_key] for obj in current.objects))
    apply_object_set(db, old, ())
    ids = {
        row["source_key"]: row["id"]
        for row in db.execute("SELECT id, source_key FROM dso WHERE source_key IS NOT NULL")
    }
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (ids["NGC0755"],))
    db.execute("INSERT INTO project (name) VALUES ('Ownership')")
    project_id = int(db.execute("SELECT last_insert_rowid()").fetchone()[0])
    db.execute(
        "INSERT INTO project_target (project_id, dso_id) VALUES (?, ?)",
        (project_id, ids["NGC0764"]),
    )
    db.commit()

    report = apply_object_set(db, current, ())

    assert report.merged == report.inserted == report.removed == 0
    assert {
        row["source_key"]: row["id"]
        for row in db.execute("SELECT id, source_key FROM dso WHERE source_key IS NOT NULL")
    } == ids
    assert db.execute("SELECT dso_id FROM favorite_target").fetchone()[0] == ids["NGC0755"]
    assert db.execute("SELECT dso_id FROM project_target").fetchone()[0] == ids["NGC0764"]
    owners = {
        row["identifier"]: row["dso_id"]
        for row in db.execute("SELECT identifier, dso_id FROM dso_designation WHERE catalog='ngc'")
    }
    assert owners["764"] == ids["NGC0764"]
    assert owners["6839"] == ids["NGC6839"]
    repeat = apply_object_set(db, current, ())
    assert repeat.inserted == repeat.updated == repeat.removed == repeat.merged == 0


def test_removed_object_keeps_enrichment_and_records(db: sqlite3.Connection):
    object_set = _legacy(db)
    db.execute(
        """
        UPDATE dso SET common_name='Curated', common_name_augmented=1,
            distance_pc=1234, distance_method='50mgc'
        WHERE id=5
        """
    )
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (5)")
    db.commit()
    without_ic9 = replace(
        object_set,
        objects=tuple(obj for obj in object_set.objects if obj.source_key != "IC0009"),
    )

    report = apply_object_set(db, without_ic9, ())

    row = db.execute(
        "SELECT active, common_name, common_name_augmented, distance_pc, distance_method "
        "FROM dso WHERE id=5"
    ).fetchone()
    assert tuple(row) == (0, "Curated", 1, 1234.0, "50mgc")
    assert db.execute("SELECT dso_id FROM favorite_target").fetchone()[0] == 5
    assert report.removed == 2


def test_reappearing_object_reactivates_same_row(db: sqlite3.Connection):
    object_set = _legacy(db)
    apply_object_set(db, object_set, ())
    without_ic9 = replace(
        object_set,
        objects=tuple(obj for obj in object_set.objects if obj.source_key != "IC0009"),
    )
    apply_object_set(db, without_ic9, ())
    report = apply_object_set(db, object_set, ())
    assert tuple(db.execute("SELECT active, source_key FROM dso WHERE id=5").fetchone()) == (
        1,
        "IC0009",
    )
    assert report.reactivated == 1


def test_shared_name_is_not_a_merge(db: sqlite3.Connection):
    object_set = _legacy(db)
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (5)")
    db.commit()
    without_ic9 = replace(
        object_set,
        objects=tuple(obj for obj in object_set.objects if obj.source_key != "IC0009"),
    )
    apply_object_set(db, without_ic9, ())
    host_id = db.execute("SELECT id FROM dso WHERE source_key='NGC0005'").fetchone()[0]
    assert db.execute("SELECT dso_id FROM favorite_target").fetchone()[0] == 5
    assert host_id != 5


def test_former_duplicate_listed_again_gets_new_row(db: sqlite3.Connection, tmp_path: Path):
    _legacy(db)
    staged = tmp_path / "legacy"
    shutil.copytree(LEGACY, staged)
    path = staged / "NGC.csv"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "NGC0007;Dup;00:08:00.0;+27:34:00;Peg;;;;;;;;;;;;;;;;;;;;0008;;;;;;;Type:1|RA:1|Dec:1",
        "NGC0007;G;00:08:30.0;+27:32:00;Peg;;;;;;;;;;;;;;;;;;;;;;;;;;;Type:1|RA:1|Dec:1",
    )
    path.write_text(text, encoding="utf-8")
    object_set = build_object_set(_sources(staged), staged / "sharpless_crossref.csv")
    old_survivor = db.execute("SELECT id FROM dso WHERE primary_designation='NGC 8'").fetchone()[0]

    apply_object_set(db, object_set, ())

    new_row = db.execute("SELECT id FROM dso WHERE source_key='NGC0007'").fetchone()
    assert new_row is not None and new_row[0] != old_survivor
    assert db.execute("SELECT id FROM dso WHERE source_key='NGC0008'").fetchone()[0] == old_survivor


def test_former_duplicate_listed_again_gets_new_row_with_null_key(
    db: sqlite3.Connection, tmp_path: Path
):
    object_set = _legacy(db)
    apply_object_set(db, object_set, ())
    source_id = db.execute(
        "SELECT id FROM dso_catalog_source WHERE source_id='openngc'"
    ).fetchone()[0]
    db.execute(
        """
        INSERT INTO dso
            (primary_designation, obj_type, source_catalog_id, source_row_hash, active)
        VALUES ('NGC 7', 'G', ?, 'former-duplicate', 0)
        """,
        (source_id,),
    )
    old_id = int(db.execute("SELECT max(id) FROM dso").fetchone()[0])
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (old_id,))
    db.commit()
    staged = tmp_path / "legacy"
    shutil.copytree(LEGACY, staged)
    path = staged / "NGC.csv"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "NGC0007;Dup;00:08:00.0;+27:34:00;Peg;;;;;;;;;;;;;;;;;;;;0008;;;;;;;Type:1|RA:1|Dec:1",
            "NGC0007;G;00:08:30.0;+27:32:00;Peg;;;;;;;;;;;;;;;;;;;;;;;;;;;Type:1|RA:1|Dec:1",
        ),
        encoding="utf-8",
    )

    apply_object_set(
        db,
        build_object_set(_sources(staged), staged / "sharpless_crossref.csv"),
        (),
    )

    new_id = db.execute("SELECT id FROM dso WHERE source_key='NGC0007'").fetchone()[0]
    assert new_id != old_id
    assert db.execute("SELECT active FROM dso WHERE id=?", (old_id,)).fetchone()[0] == 0
    assert db.execute("SELECT dso_id FROM favorite_target").fetchone()[0] == old_id


def test_duplicate_merge_moves_records(db: sqlite3.Connection):
    object_set = _legacy(db)
    apply_object_set(db, object_set, ())
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (1)")
    db.commit()
    survivor_index = next(
        index for index, obj in enumerate(object_set.objects) if obj.source_key == "NGC0002"
    )
    without_one = replace(
        object_set,
        objects=tuple(obj for obj in object_set.objects if obj.source_key != "NGC0001"),
        merges={("openngc", "NGC0001"): survivor_index - 1},
    )
    report = apply_object_set(db, without_one, ())
    survivor_id = db.execute("SELECT id FROM dso WHERE source_key='NGC0002'").fetchone()[0]
    assert db.execute("SELECT dso_id FROM favorite_target").fetchone()[0] == survivor_id
    assert db.execute("SELECT COUNT(*) FROM dso WHERE id=1").fetchone()[0] == 0
    assert report.merged == 1


def test_merge_kept_inactive_when_unknown_table_references_it(db: sqlite3.Connection):
    object_set = _legacy(db)
    apply_object_set(db, object_set, ())
    db.execute("CREATE TABLE zz_future_link (dso_id INTEGER REFERENCES dso(id))")
    db.execute("INSERT INTO zz_future_link VALUES (1)")
    db.commit()
    survivor_index = next(
        index for index, obj in enumerate(object_set.objects) if obj.source_key == "NGC0002"
    )
    without_one = replace(
        object_set,
        objects=tuple(obj for obj in object_set.objects if obj.source_key != "NGC0001"),
        merges={("openngc", "NGC0001"): survivor_index - 1},
    )
    report = apply_object_set(db, without_one, ())
    assert tuple(db.execute("SELECT active, source_key FROM dso WHERE id=1").fetchone()) == (
        0,
        None,
    )
    assert report.kept_inactive_merge == 1


@pytest.mark.parametrize("stage", ("designation", "object_update", "move_user_links"))
def test_rollback_at_each_stage(
    db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch, stage: str
):
    from nightcrate.catalog_loader import reconcile

    object_set = _legacy(db)
    candidate = object_set
    expected_error: type[Exception] = sqlite3.IntegrityError

    if stage == "designation":
        first = object_set.objects[0]
        candidate = replace(
            object_set,
            objects=(
                NewObject(
                    first.source_id,
                    first.source_key,
                    first.columns,
                    (("invalid-catalog", "1", True),),
                    first.file_order,
                ),
                *object_set.objects[1:],
            ),
        )
    elif stage == "object_update":
        first = object_set.objects[0]
        candidate = replace(
            object_set,
            objects=(
                replace(first, columns={**first.columns, "ra_deg": 42.0}),
                *object_set.objects[1:],
            ),
        )
        db.execute(
            """
            CREATE TRIGGER fail_first_object_update
            BEFORE UPDATE OF ra_deg ON dso WHEN OLD.id = 1
            BEGIN
                SELECT RAISE(ABORT, 'injected object update failure');
            END
            """
        )
        db.commit()
    else:
        apply_object_set(db, object_set, ())
        db.execute("INSERT INTO favorite_target (dso_id) VALUES (1)")
        db.commit()
        survivor_index = next(
            index for index, obj in enumerate(object_set.objects) if obj.source_key == "NGC0002"
        )
        candidate = replace(
            object_set,
            objects=tuple(obj for obj in object_set.objects if obj.source_key != "NGC0001"),
            merges={("openngc", "NGC0001"): survivor_index - 1},
        )
        real_move = reconcile.move_user_links

        def move_then_fail(*args, **kwargs):
            real_move(*args, **kwargs)
            raise RuntimeError("injected user-link move failure")

        monkeypatch.setattr(reconcile, "move_user_links", move_then_fail)
        expected_error = RuntimeError

    tables = ("dso", "dso_designation", "dso_catalog_source", "favorite_target")
    before = {table: _snapshot(db, table) for table in tables}
    with pytest.raises(expected_error):
        apply_object_set(db, candidate, ())
    assert {table: _snapshot(db, table) for table in tables} == before


def test_surface_brightness_reset_when_object_becomes_galaxy(db: sqlite3.Connection):
    object_set = _legacy(db)
    db.execute("UPDATE dso SET surface_brightness=99, surface_brightness_augmented=1 WHERE id=1")
    db.commit()
    apply_object_set(db, object_set, ())
    assert tuple(
        db.execute(
            "SELECT surface_brightness, surface_brightness_augmented FROM dso WHERE id=1"
        ).fetchone()
    ) == (13.8, 0)


def test_second_run_changes_no_catalog_values(db: sqlite3.Connection):
    object_set = _legacy(db)
    apply_object_set(db, object_set, ())
    before = [
        tuple(row)
        for row in db.execute(
            """
            SELECT id, primary_designation, obj_type, ra_deg, dec_deg,
                   source_catalog_id, source_row_hash, source_key, active,
                   distance_pc, distance_method
            FROM dso ORDER BY id
            """
        )
    ]
    report = apply_object_set(db, object_set, ())
    after = [
        tuple(row)
        for row in db.execute(
            """
            SELECT id, primary_designation, obj_type, ra_deg, dec_deg,
                   source_catalog_id, source_row_hash, source_key, active,
                   distance_pc, distance_method
            FROM dso ORDER BY id
            """
        )
    ]
    assert after == before
    assert report.inserted == report.updated == report.removed == report.merged == 0


def test_changed_values_update_in_place(db: sqlite3.Connection):
    object_set = _legacy(db)
    apply_object_set(db, object_set, ())
    first = object_set.objects[0]
    changed_columns = {**first.columns, "ra_deg": 42.25, "source_row_hash": "changed"}
    changed = replace(
        object_set,
        objects=(replace(first, columns=changed_columns), *object_set.objects[1:]),
    )
    apply_object_set(db, changed, ())
    assert tuple(
        db.execute("SELECT id, ra_deg FROM dso WHERE source_key='NGC0001'").fetchone()
    ) == (
        1,
        42.25,
    )


def test_null_key_unclaimed_row_is_removed_not_merged(db: sqlite3.Connection):
    object_set = _legacy(db)
    source_id = db.execute(
        "SELECT id FROM dso_catalog_source WHERE source_id='openngc'"
    ).fetchone()[0]
    db.execute(
        """
        INSERT INTO dso
            (primary_designation, obj_type, source_catalog_id, source_row_hash)
        VALUES ('Legacy keyless', 'Other', ?, 'keyless')
        """,
        (source_id,),
    )
    keyless_id = int(db.execute("SELECT max(id) FROM dso").fetchone()[0])
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (keyless_id,))
    db.commit()
    report = apply_object_set(db, object_set, ())
    assert db.execute("SELECT active FROM dso WHERE id=?", (keyless_id,)).fetchone()[0] == 0
    assert db.execute("SELECT dso_id FROM favorite_target").fetchone()[0] == keyless_id
    assert report.merged == 0


def test_addendum_to_main_move_keeps_id(db: sqlite3.Connection):
    object_set = _legacy(db)
    apply_object_set(db, object_set, ())
    old_id = db.execute("SELECT id FROM dso WHERE source_key='B033'").fetchone()[0]
    moved_objects = tuple(
        replace(obj, source_id="openngc") if obj.source_key == "B033" else obj
        for obj in object_set.objects
    )
    moved = replace(object_set, objects=moved_objects)
    apply_object_set(db, moved, ())
    row = db.execute(
        """
        SELECT d.id, s.source_id
        FROM dso d JOIN dso_catalog_source s ON s.id=d.source_catalog_id
        WHERE d.source_key='B033'
        """
    ).fetchone()
    assert tuple(row) == (old_id, "openngc")


def test_sharpless_crossref_added_and_removed(db: sqlite3.Connection, tmp_path: Path):
    object_set = _legacy(db)
    apply_object_set(db, object_set, ())
    empty_crossref = tmp_path / "crossref.csv"
    empty_crossref.write_text("sh2,target_designation\n", encoding="utf-8")
    standalone_set = build_object_set(_sources(), empty_crossref)
    apply_object_set(db, standalone_set, ())
    standalone = db.execute("SELECT id FROM dso WHERE source_key='12'").fetchone()
    assert standalone is not None
    standalone_id = int(standalone[0])
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (standalone_id,))
    db.commit()

    report = apply_object_set(db, object_set, ())

    ngc3_id = db.execute("SELECT id FROM dso WHERE source_key='NGC0003'").fetchone()[0]
    assert db.execute("SELECT dso_id FROM favorite_target").fetchone()[0] == ngc3_id
    assert db.execute("SELECT COUNT(*) FROM dso WHERE id=?", (standalone_id,)).fetchone()[0] == 0
    assert report.merged == 1


def test_dup_via_addendum_resolves_before_sharpless(tmp_path: Path):
    root = tmp_path / "catalogs"
    root.mkdir()
    header = (LEGACY / "NGC.csv").read_text(encoding="utf-8").splitlines()[0]
    (root / "NGC.csv").write_text(
        header
        + "\n"
        + "NGC0002;Dup;00:00:00;+00:00:00;Psc;;;;;;;;;;;;;;;;;;;;0003;;;;;;;x\n"
        + "NGC0004;Dup;00:00:00;+00:00:00;Psc;;;;;;;;;;;;;;;;;;;;0002;;;;;;;x\n",
        encoding="utf-8",
    )
    (root / "addendum.csv").write_text(
        header + "\nNGC0003;G;00:00:00;+00:00:00;Psc;;;;;;;;;;;;;;;;;;;;;;;;;;;x\n",
        encoding="utf-8",
    )
    (root / "sharpless.tsv").write_text(
        "_RAJ2000\t_DEJ2000\tSh2\tDiam\tClass\n"
        "deg\tdeg\t--\tarcmin\t--\n"
        "--------\t--------\t---\t------\t-----\n"
        "0\t0\t5\t10\t1\n",
        encoding="utf-8",
    )
    (root / "barnard.tsv").write_text(
        "_RAJ2000\t_DEJ2000\tBarn\tDiam\tDurch\tNames\n"
        "deg\tdeg\t--\tarcmin\t--\t--\n"
        "--------\t--------\t---\t------\t--\t--\n",
        encoding="utf-8",
    )
    crossref = root / "crossref.csv"
    crossref.write_text("sh2,target_designation\n5,NGC 2\n", encoding="utf-8")

    object_set = build_object_set(_sources(root), crossref)

    target = next(obj for obj in object_set.objects if obj.source_key == "NGC0003")
    assert ("ngc", "2", False) in target.designations
    assert ("ngc", "4", False) in target.designations
    assert ("sharpless2", "5", False) in target.designations
    assert not any(obj.source_id == "vizier_sharpless" for obj in object_set.objects)


def test_forward_and_chained_duplicates_resolve(tmp_path: Path):
    root = tmp_path / "catalogs"
    root.mkdir()
    header = (LEGACY / "NGC.csv").read_text(encoding="utf-8").splitlines()[0]
    (root / "NGC.csv").write_text(
        header
        + "\n"
        + "NGC0002;Dup;00:00:00;+00:00:00;Psc;;;;;;;;;;;;;;;;;;;;0003;;;;;;;x\n"
        + "NGC0003;Dup;00:00:00;+00:00:00;Psc;;;;;;;;;;;;;;;;;;;;0004;;;;;;;x\n",
        encoding="utf-8",
    )
    (root / "addendum.csv").write_text(
        header + "\nNGC0004;G;00:00:00;+00:00:00;Psc;;;;;;;;;;;;;;;;;;;;;;;;;;;x\n",
        encoding="utf-8",
    )
    (root / "sharpless.tsv").write_text(
        "_RAJ2000\t_DEJ2000\tSh2\tDiam\tClass\n"
        "deg\tdeg\t--\tarcmin\t--\n"
        "--------\t--------\t---\t------\t-----\n",
        encoding="utf-8",
    )
    (root / "barnard.tsv").write_text(
        "_RAJ2000\t_DEJ2000\tBarn\tDiam\tDurch\tNames\n"
        "deg\tdeg\t--\tarcmin\t--\t--\n"
        "--------\t--------\t---\t------\t--\t--\n",
        encoding="utf-8",
    )
    crossref = root / "crossref.csv"
    crossref.write_text("sh2,target_designation\n", encoding="utf-8")

    object_set = build_object_set(_sources(root), crossref)

    assert object_set.unresolved == 0
    assert len(object_set.objects) == 1
    assert set(object_set.objects[0].designations) == {
        ("ngc", "2", False),
        ("ngc", "3", False),
        ("ngc", "4", True),
    }


@pytest.mark.parametrize("legacy_variant", ("duplicate_text", "moved_name"))
def test_bootstrap_with_changed_file_pairs_only_unambiguous(
    db: sqlite3.Connection, tmp_path: Path, legacy_variant: str
):
    _legacy(db)
    staged = tmp_path / "legacy"
    shutil.copytree(LEGACY, staged)
    ngc_path = staged / "NGC.csv"

    if legacy_variant == "moved_name":
        old_root = tmp_path / "old"
        shutil.copytree(LEGACY, old_root)
        old_ngc = old_root / "NGC.csv"
        old_text = old_ngc.read_text(encoding="utf-8").replace(
            "NGC0002;G;00:07:17.0;+27:41:40;Peg;1.80;1.20;35;13.50;12.60;;;;"
            "14.10;Sc;;;;1100;0.0037;;;;007;",
            "NGC0002;G;00:07:17.0;+27:41:40;Peg;1.80;1.20;35;13.50;12.60;;;;"
            "14.10;Sc;;;;1100;0.0037;;;;008;",
        )
        old_ngc.write_text(old_text, encoding="utf-8")
        old_set = build_object_set(_sources(old_root), old_root / "sharpless_crossref.csv")
        old_two = next(obj for obj in old_set.objects if obj.source_key == "NGC0002")
        db.execute(
            "UPDATE dso SET primary_designation='M 8', source_row_hash=? WHERE id=2",
            (old_two.columns["source_row_hash"],),
        )
        db.execute(
            "UPDATE dso_catalog_source SET file_hash=? WHERE source_id='openngc'",
            (old_set.hashes["openngc"],),
        )
        db.execute("DELETE FROM dso_designation WHERE catalog='messier' AND dso_id IN (1, 2)")
        db.execute(
            """
            INSERT INTO dso_designation
                (dso_id, catalog, identifier, display_form, search_key, is_primary)
            VALUES (1, 'messier', '7', 'M 7', 'm7', 1),
                   (2, 'messier', '8', 'M 8', 'm8', 1)
            """
        )

    db.execute("INSERT INTO favorite_target (dso_id) VALUES (1), (2)")
    db.commit()
    lines = ngc_path.read_text(encoding="utf-8").splitlines()
    ngc_path.write_text(
        "\n".join(line for line in lines if not line.startswith("NGC0001;")) + "\n",
        encoding="utf-8",
    )
    changed = build_object_set(_sources(staged), staged / "sharpless_crossref.csv")

    report = apply_object_set(db, changed, ())

    assert db.execute("SELECT active FROM dso WHERE id=1").fetchone()[0] == 0
    assert [row[0] for row in db.execute("SELECT dso_id FROM favorite_target ORDER BY dso_id")] == [
        1,
        2,
    ]
    assert db.execute("SELECT id FROM dso WHERE source_key='NGC0003'").fetchone()[0] == 3
    current_two = db.execute("SELECT id FROM dso WHERE source_key='NGC0002'").fetchone()[0]
    if legacy_variant == "duplicate_text":
        assert current_two == 2
        assert report.inserted == 0
    else:
        assert current_two not in {1, 2}
        assert db.execute("SELECT active FROM dso WHERE id=2").fetchone()[0] == 0
        assert report.inserted == 1


def test_legacy_pairing_does_not_run_after_keys_assigned(db: sqlite3.Connection):
    source = _sources()["openngc"]
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO dso_catalog_source
            (source_id, category, display_name, file_path, file_hash, attribution,
             keys_assigned)
        VALUES ('openngc', 'openngc', 'Synthetic', 'synthetic.csv', 'same', 'test', 1)
        """
    )
    source_id = int(cur.lastrowid)
    cur.execute(
        """
        INSERT INTO dso
            (primary_designation, obj_type, source_catalog_id, source_row_hash, active)
        VALUES ('Same display', 'G', ?, 'old', 0)
        """,
        (source_id,),
    )
    old_id = int(cur.lastrowid)
    cur.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (old_id,))
    db.commit()
    new = ObjectSet(
        (
            NewObject(
                "openngc",
                "NEW0001",
                {
                    "primary_designation": "Same display",
                    "obj_type": "G",
                    "source_row_hash": "new",
                },
                (),
                0,
            ),
        ),
        {},
        {"openngc": "same"},
        0,
        {"openngc": source},
    )

    report = apply_object_set(db, new, ())

    new_id = db.execute("SELECT id FROM dso WHERE source_key='NEW0001'").fetchone()[0]
    assert new_id != old_id
    assert tuple(
        db.execute("SELECT active, source_key FROM dso WHERE id=?", (old_id,)).fetchone()
    ) == (
        0,
        None,
    )
    assert db.execute("SELECT dso_id FROM favorite_target").fetchone()[0] == old_id
    assert report.inserted == 1


def test_changed_legacy_hash_must_be_unique_on_both_sides(db: sqlite3.Connection):
    source = _sources()["openngc"]
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO dso_catalog_source
            (source_id, category, display_name, file_path, file_hash, attribution)
        VALUES ('openngc', 'openngc', 'Synthetic', 'synthetic.csv', 'old', 'test')
        """
    )
    source_id = int(cur.lastrowid)
    cur.executemany(
        """
        INSERT INTO dso
            (primary_designation, obj_type, source_catalog_id, source_row_hash)
        VALUES (?, 'G', ?, 'collision')
        """,
        (("Old one", source_id), ("Old two", source_id)),
    )
    db.commit()
    new = ObjectSet(
        (
            NewObject(
                "openngc",
                "NEW0001",
                {
                    "primary_designation": "New object",
                    "obj_type": "G",
                    "source_row_hash": "collision",
                },
                (),
                0,
            ),
        ),
        {},
        {"openngc": "new"},
        0,
        {"openngc": source},
    )

    report = apply_object_set(db, new, ())

    assert report.inserted == 1
    assert db.execute("SELECT COUNT(*) FROM dso WHERE active=0").fetchone()[0] == 2
    assert db.execute("SELECT COUNT(*) FROM dso WHERE source_key='NEW0001'").fetchone()[0] == 1


def test_apply_object_set_preserves_connection_row_factory(db: sqlite3.Connection):
    object_set = _legacy(db)
    db.row_factory = None

    apply_object_set(db, object_set, ())

    assert db.row_factory is None
    assert isinstance(db.execute("SELECT id FROM dso LIMIT 1").fetchone(), tuple)


def test_matching_twenty_thousand_objects_is_linear(db: sqlite3.Connection):
    count = 20_000
    source = _sources()["openngc"]
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO dso_catalog_source
            (source_id, category, display_name, file_path, file_hash, attribution,
             keys_assigned)
        VALUES ('openngc', 'openngc', 'Synthetic', 'synthetic.csv', 'same', 'test', 1)
        """
    )
    source_id = int(cur.lastrowid)
    cur.executemany(
        """
        INSERT INTO dso
            (primary_designation, obj_type, source_catalog_id, source_row_hash, source_key)
        VALUES (?, 'G', ?, ?, ?)
        """,
        ((f"Object {index}", source_id, f"hash-{index}", f"key-{index}") for index in range(count)),
    )
    db.commit()
    objects = tuple(
        NewObject(
            "openngc",
            f"key-{index}",
            {
                "primary_designation": f"Object {index}",
                "obj_type": "G",
                "source_row_hash": f"hash-{index}",
            },
            (),
            index,
        )
        for index in range(count)
    )
    object_set = ObjectSet(
        objects,
        {},
        {"openngc": "same"},
        0,
        {"openngc": source},
    )

    started = time.perf_counter()
    report = apply_object_set(db, object_set, ())
    elapsed = time.perf_counter() - started

    assert elapsed < 5
    assert report.inserted == report.updated == report.removed == 0
    assert db.execute("SELECT COUNT(*) FROM dso").fetchone()[0] == count
