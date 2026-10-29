"""High-stakes identity and rollback tests for the catalog object step."""

from __future__ import annotations

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


def _snapshot(db: sqlite3.Connection, table: str) -> list[tuple]:
    return [tuple(row) for row in db.execute(f'SELECT * FROM "{table}" ORDER BY id')]  # nosec B608


def test_one_time_step_on_legacy_fixture(db: sqlite3.Connection):
    object_set = _legacy(db)
    before_ids = _snapshot(db, "dso")
    before_designations = [
        tuple(row)
        for row in db.execute(
            "SELECT dso_id, catalog, identifier, display_form, search_key, is_primary "
            "FROM dso_designation ORDER BY dso_id, catalog, identifier"
        )
    ]
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

    assert report.inserted == report.removed == report.merged == 0
    assert [row[0] for row in before_ids] == [row[0] for row in _snapshot(db, "dso")]
    assert db.execute("SELECT COUNT(*) FROM dso WHERE source_key IS NULL").fetchone()[0] == 0
    after_designations = [
        tuple(row)
        for row in db.execute(
            "SELECT dso_id, catalog, identifier, display_form, search_key, is_primary "
            "FROM dso_designation ORDER BY dso_id, catalog, identifier"
        )
    ]
    assert after_designations == before_designations
    assert db.execute("SELECT dso_id FROM favorite_target").fetchone()[0] == 5
    assert db.execute("SELECT dso_id FROM project_target").fetchone()[0] == 1
    assert db.execute("SELECT dso_id FROM project_dso").fetchone()[0] == 3
    assert db.execute("SELECT project_target_id FROM sub_frame").fetchone()[0] == target_id


def test_alternate_name_beats_later_canonical(db: sqlite3.Connection):
    object_set = _legacy(db)
    addendum = next(obj for obj in object_set.objects if obj.source_key == "B033")
    barnard = next(
        obj
        for obj in object_set.objects
        if obj.source_id == "vizier_barnard" and obj.source_key == "33"
    )
    assert ("barnard", "33", True) in addendum.designations
    assert not barnard.designations


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
    assert report.removed == 1


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
