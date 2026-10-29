"""Regression tests for moving every user-owned DSO relationship."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from nightcrate.catalog_loader.user_links import (
    CATALOG_DERIVED_TABLES,
    USER_LINK_TABLES,
    count_references,
    move_user_links,
)


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "test.db")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _objects(conn: sqlite3.Connection) -> tuple[int, int]:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO dso_catalog_source
            (source_id, category, display_name, file_path, file_hash, attribution)
        VALUES ('test', 'nightcrate', 'Test', 'test.csv', 'hash', 'test')
        """
    )
    source_id = int(cur.lastrowid)
    ids: list[int] = []
    for name, key in (("NGC 3", "A"), ("NGC 4", "B")):
        cur.execute(
            """
            INSERT INTO dso
                (primary_designation, obj_type, source_catalog_id, source_row_hash, source_key)
            VALUES (?, 'G', ?, ?, ?)
            """,
            (name, source_id, key, key),
        )
        ids.append(int(cur.lastrowid))
    conn.commit()
    return ids[0], ids[1]


def _plan_dependencies(conn: sqlite3.Connection) -> tuple[int, int, int]:
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO location (name, latitude, longitude, timezone) VALUES ('Test', 0, 0, 'UTC')"
    )
    location_id = int(cur.lastrowid)
    cur.execute(
        """
        INSERT INTO location_horizon (location_id, name, type, source)
        VALUES (?, 'Test', 'custom', 'drawn')
        """,
        (location_id,),
    )
    horizon_id = int(cur.lastrowid)
    config_id = int(cur.execute("SELECT id FROM telescope_configuration LIMIT 1").fetchone()[0])
    camera_id = int(cur.execute("SELECT id FROM camera LIMIT 1").fetchone()[0])
    cur.execute(
        """
        INSERT INTO rig (name, telescope_configuration_id, camera_id)
        VALUES ('Test rig', ?, ?)
        """,
        (config_id, camera_id),
    )
    return location_id, horizon_id, int(cur.lastrowid)


def test_fk_tables_are_all_classified(db: sqlite3.Connection):
    def dso_fk_tables() -> set[str]:
        found: set[str] = set()
        cur = db.cursor()
        tables = [
            row[0] for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        ]
        for table in tables:
            for fk in cur.execute(f'PRAGMA foreign_key_list("{table}")'):  # nosec B608
                if fk[2] == "dso" and fk[4] in (None, "id"):
                    found.add(table)
        return found

    assert dso_fk_tables() == CATALOG_DERIVED_TABLES | USER_LINK_TABLES
    db.execute("CREATE TABLE zz_bare (dso_id INTEGER REFERENCES dso)")
    assert dso_fk_tables() == CATALOG_DERIVED_TABLES | USER_LINK_TABLES | {"zz_bare"}


def test_moves_project_target(db: sqlite3.Connection):
    old_id, new_id = _objects(db)
    cur = db.cursor()
    cur.execute("INSERT INTO project (name) VALUES ('P')")
    project_id = int(cur.lastrowid)
    cur.execute(
        "INSERT INTO project_target (project_id, dso_id) VALUES (?, ?)",
        (project_id, old_id),
    )
    target_id = int(cur.lastrowid)

    move_user_links(cur, old_id, new_id, "NGC 3")

    assert tuple(cur.execute("SELECT id, dso_id FROM project_target").fetchone()) == (
        target_id,
        new_id,
    )


def test_moves_favorite_with_plans_and_ranges(db: sqlite3.Connection):
    old_id, new_id = _objects(db)
    location_id, horizon_id, rig_id = _plan_dependencies(db)
    cur = db.cursor()
    cur.execute("INSERT INTO wishlist_section (name) VALUES ('S')")
    section_id = int(cur.lastrowid)
    cur.execute(
        "INSERT INTO favorite_target (dso_id, sort_order, section_id) VALUES (?, 3, ?)",
        (old_id, section_id),
    )
    cur.execute(
        """
        INSERT INTO target_plan (dso_id, location_id, horizon_id, rig_id)
        VALUES (?, ?, ?, ?)
        """,
        (old_id, location_id, horizon_id, rig_id),
    )
    plan_id = int(cur.lastrowid)
    cur.executemany(
        """
        INSERT INTO target_plan_date_range (plan_id, start_date, end_date)
        VALUES (?, ?, ?)
        """,
        ((plan_id, "2026-11-01", "2026-11-10"), (plan_id, "2026-12-01", "2026-12-05")),
    )

    move_user_links(cur, old_id, new_id, "NGC 3")

    favorite = cur.execute(
        "SELECT sort_order, section_id FROM favorite_target WHERE dso_id = ?", (new_id,)
    ).fetchone()
    assert tuple(favorite) == (3, section_id)
    assert (
        cur.execute("SELECT dso_id FROM target_plan WHERE id = ?", (plan_id,)).fetchone()[0]
        == new_id
    )
    assert (
        cur.execute("SELECT COUNT(*) FROM favorite_target WHERE dso_id = ?", (old_id,)).fetchone()[
            0
        ]
        == 0
    )
    assert (
        cur.execute(
            "SELECT COUNT(*) FROM target_plan_date_range WHERE plan_id = ?", (plan_id,)
        ).fetchone()[0]
        == 2
    )


def test_favorite_collision_merges_plans(db: sqlite3.Connection):
    old_id, new_id = _objects(db)
    location_id, horizon_id, rig_id = _plan_dependencies(db)
    cur = db.cursor()
    cur.executemany("INSERT INTO favorite_target (dso_id) VALUES (?)", ((old_id,), (new_id,)))
    cur.execute(
        """
        INSERT INTO target_plan
            (dso_id, location_id, horizon_id, rig_id, moon_sep_deg,
             moon_filter_enabled, threshold_hours, notes)
        VALUES (?, ?, ?, ?, 10, 1, 3.5, 'a')
        """,
        (old_id, location_id, horizon_id, rig_id),
    )
    old_plan = int(cur.lastrowid)
    cur.execute(
        """
        INSERT INTO target_plan
            (dso_id, location_id, horizon_id, rig_id, moon_sep_deg, notes)
        VALUES (?, ?, ?, ?, 30, 'b')
        """,
        (new_id, location_id, horizon_id, rig_id),
    )
    new_plan = int(cur.lastrowid)
    cur.executemany(
        """
        INSERT INTO target_plan_date_range (plan_id, start_date, end_date)
        VALUES (?, ?, ?)
        """,
        (
            (old_plan, "2026-11-01", "2026-11-10"),
            (old_plan, "2026-12-01", "2026-12-05"),
            (new_plan, "2026-11-08", "2026-11-20"),
        ),
    )

    move_user_links(cur, old_id, new_id, "NGC 3")

    plan = cur.execute(
        "SELECT moon_sep_deg, notes FROM target_plan WHERE id = ?", (new_plan,)
    ).fetchone()
    assert tuple(plan) == (
        30,
        "b\n\nFrom NGC 3: a\n\nFrom NGC 3, settings not kept: "
        "moon_sep_deg=10, moon_filter_enabled=1, threshold_hours=3.5",
    )
    ranges = cur.execute(
        "SELECT start_date, end_date FROM target_plan_date_range "
        "WHERE plan_id = ? ORDER BY start_date",
        (new_plan,),
    ).fetchall()
    assert [tuple(row) for row in ranges] == [
        ("2026-11-01", "2026-11-20"),
        ("2026-12-01", "2026-12-05"),
    ]


def test_project_target_collision_repoints_all_children(db: sqlite3.Connection):
    old_id, new_id = _objects(db)
    cur = db.cursor()
    cur.execute("INSERT INTO project (name) VALUES ('P')")
    project_id = int(cur.lastrowid)
    cur.execute(
        "INSERT INTO project_target (project_id, dso_id) VALUES (?, ?)", (project_id, old_id)
    )
    old_target = int(cur.lastrowid)
    cur.execute(
        "INSERT INTO project_target (project_id, dso_id) VALUES (?, ?)", (project_id, new_id)
    )
    new_target = int(cur.lastrowid)
    cur.execute(
        "CREATE TABLE zz_future_child (project_target_id INTEGER REFERENCES project_target(id))"
    )
    cur.execute("INSERT INTO zz_future_child VALUES (?)", (old_target,))
    cur.execute(
        """
        INSERT INTO sub_frame
            (project_id, content_hash, project_target_id, date_obs_utc)
        VALUES (?, 'a', ?, '2026-01-01')
        """,
        (project_id, old_target),
    )
    cur.execute(
        "INSERT INTO project_source_folder (project_id, path, project_target_id) "
        "VALUES (?, '/data', ?)",
        (project_id, old_target),
    )

    move_user_links(cur, old_id, new_id, "NGC 3")

    assert (
        cur.execute("SELECT COUNT(*) FROM project_target WHERE id = ?", (old_target,)).fetchone()[0]
        == 0
    )
    assert cur.execute("SELECT project_target_id FROM zz_future_child").fetchone()[0] == new_target
    assert cur.execute("SELECT project_target_id FROM sub_frame").fetchone()[0] == new_target
    assert (
        cur.execute("SELECT project_target_id FROM project_source_folder").fetchone()[0]
        == new_target
    )


def test_project_dso_collision_keeps_main_flag(db: sqlite3.Connection):
    old_id, new_id = _objects(db)
    cur = db.cursor()
    cur.execute("INSERT INTO project (name) VALUES ('P')")
    project_id = int(cur.lastrowid)
    cur.execute(
        """
        INSERT INTO project_solve (
            project_id, image_path, image_width, image_height, center_ra_deg,
            center_dec_deg, cd1_1, cd1_2, cd2_1, cd2_2, crpix1, crpix2
        ) VALUES (?, 'x.fits', 10, 10, 0, 0, 1, 0, 0, 1, 5, 5)
        """,
        (project_id,),
    )
    solve_id = int(cur.lastrowid)
    cur.executemany(
        "INSERT INTO project_dso (solve_id, dso_id, is_main) VALUES (?, ?, ?)",
        ((solve_id, old_id, 1), (solve_id, new_id, 0)),
    )
    move_user_links(cur, old_id, new_id, "NGC 3")
    rows = cur.execute("SELECT dso_id, is_main FROM project_dso").fetchall()
    assert [tuple(row) for row in rows] == [(new_id, 1)]


def test_count_references_discovers_unknown_fk(db: sqlite3.Connection):
    old_id, _ = _objects(db)
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO dso_designation
            (dso_id, catalog, identifier, display_form, search_key, is_primary)
        VALUES (?, 'ngc', '3', 'NGC 3', 'ngc3', 1)
        """,
        (old_id,),
    )
    assert count_references(cur, old_id) == 0
    cur.execute("CREATE TABLE zz_future_link (dso_id INTEGER REFERENCES dso(id))")
    cur.execute("INSERT INTO zz_future_link VALUES (?)", (old_id,))
    assert count_references(cur, old_id) == 1
    cur.execute("CREATE TABLE zz_bare (dso_id INTEGER REFERENCES dso)")
    cur.execute("INSERT INTO zz_bare VALUES (?)", (old_id,))
    assert count_references(cur, old_id) == 2
