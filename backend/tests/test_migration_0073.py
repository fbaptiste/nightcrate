"""Migration 0073 widens project status without damaging its parent graph."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from yoyo import get_backend, read_migrations

from nightcrate.db.migrations import MIGRATIONS_DIR
from tests.test_migration_0069 import _equipment, _rig
from tests.test_migration_0070 import _apply_through

MIGRATION_0072 = "0072.uncataloged_file"
MIGRATION_0073 = "0073.project_ready_to_process"


def _apply_0073(db_path: Path) -> None:
    with get_backend(f"sqlite:///{db_path}") as backend:
        migrations = read_migrations(str(MIGRATIONS_DIR))
        backend.apply_migrations(
            backend.to_apply(migrations).filter(lambda migration: migration.id == MIGRATION_0073)
        )


def _project_foreign_keys(conn: sqlite3.Connection) -> dict[str, list[tuple]]:
    result = {}
    for (table,) in conn.execute(
        "SELECT name FROM sqlite_schema WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ):
        foreign_keys = [tuple(row) for row in conn.execute(f'PRAGMA foreign_key_list("{table}")')]
        if any(row[2] == "project" for row in foreign_keys):
            result[table] = foreign_keys
    return result


def _seed_parent_graph(conn: sqlite3.Connection) -> tuple[int, list[str]]:
    equipment = _equipment(conn)
    rig_id = _rig(conn, equipment, "Migration rig", equipment.camera_a)
    source_id = conn.execute(
        """
        INSERT INTO dso_catalog_source
            (source_id, category, display_name, file_path, file_hash)
        VALUES ('migration', 'nightcrate', 'Migration', '/synthetic', 'hash')
        """
    ).lastrowid
    dso_id = conn.execute(
        """
        INSERT INTO dso
            (primary_designation, obj_type, source_catalog_id, source_row_hash)
        VALUES ('TEST 1', 'Other', ?, 'row-hash')
        """,
        (source_id,),
    ).lastrowid
    project_id = conn.execute(
        "INSERT INTO project (name, location_id) VALUES ('Preserved', NULL)"
    ).lastrowid
    image_id = conn.execute(
        "INSERT INTO project_image (project_id, file_path, is_main) VALUES (?, '/image', 1)",
        (project_id,),
    ).lastrowid
    conn.execute(
        "INSERT INTO project_thumbnail (project_id, size, source_image_id) VALUES (?, 'small', ?)",
        (project_id, image_id),
    )
    conn.execute(
        """
        INSERT INTO project_solve
            (project_id, image_path, image_width, image_height,
             center_ra_deg, center_dec_deg, cd1_1, cd1_2, cd2_1, cd2_2, crpix1, crpix2)
        VALUES (?, '/solve', 100, 80, 1, 2, 0.1, 0, 0, 0.1, 50, 40)
        """,
        (project_id,),
    )
    conn.execute("INSERT INTO project_rig VALUES (?, ?)", (project_id, rig_id))
    conn.execute(
        "INSERT INTO project_session "
        "(project_id, rig_id, line_name, exposure_seconds, num_subs, session_date) "
        "VALUES (?, ?, 'Lum', 60, 1, '2026-11-01')",
        (project_id, rig_id),
    )
    target_id = conn.execute(
        "INSERT INTO project_target (project_id, dso_id) VALUES (?, ?)",
        (project_id, dso_id),
    ).lastrowid
    run_id = conn.execute(
        "INSERT INTO ingestion_run (project_id, source_path) VALUES (?, '/source')",
        (project_id,),
    ).lastrowid
    session_id = conn.execute(
        "INSERT INTO session (project_id, rig_id, start_utc) VALUES (?, ?, '2026-11-01T00:00Z')",
        (project_id, rig_id),
    ).lastrowid
    conn.execute(
        "INSERT INTO project_source_folder (project_id, path, rig_id, project_target_id) "
        "VALUES (?, '/source', ?, ?)",
        (project_id, rig_id, target_id),
    )
    frame_id = conn.execute(
        """
        INSERT INTO sub_frame
            (project_id, content_hash, session_id, rig_id, project_target_id,
             ingestion_run_id, date_obs_utc)
        VALUES (?, 'frame-hash', ?, ?, ?, ?, '2026-11-01T00:00Z')
        """,
        (project_id, session_id, rig_id, target_id, run_id),
    ).lastrowid
    processed_id = conn.execute(
        "INSERT INTO processed_image (project_id, content_hash, ingestion_run_id) "
        "VALUES (?, 'processed-hash', ?)",
        (project_id, run_id),
    ).lastrowid
    conn.execute(
        "INSERT INTO file_location "
        "(project_id, path, category, sub_frame_id) VALUES (?, '/frame', 'sub_frame', ?)",
        (project_id, frame_id),
    )
    conn.execute(
        "INSERT INTO file_location "
        "(project_id, path, category, processed_image_id) VALUES (?, '/processed', 'processed', ?)",
        (project_id, processed_id),
    )
    conn.execute(
        "INSERT INTO project_rig_change (project_id, rig_id) VALUES (?, ?)",
        (project_id, rig_id),
    )
    conn.execute(
        "INSERT INTO project_software (project_id, software_id) VALUES (?, ?)",
        (project_id, equipment.software_a),
    )
    conn.execute(
        "INSERT INTO project_night_note (project_id, night_date, notes) "
        "VALUES (?, '2026-11-01', 'Clear')",
        (project_id,),
    )
    conn.execute(
        "INSERT INTO uncataloged_file (project_id, path, reason, message, run_id) "
        "VALUES (?, '/bad', 'damaged', 'bad', ?)",
        (project_id, run_id),
    )
    conn.execute("UPDATE project SET cover_sub_frame_id = ? WHERE id = ?", (frame_id, project_id))
    tables = sorted(_project_foreign_keys(conn))
    assert len(tables) == 16
    return int(project_id), tables


def test_upgrade_preserves_project_graph_schema_objects_and_sequence(pre_migration_db):
    db_path = pre_migration_db(MIGRATION_0073)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        project_id, child_tables = _seed_parent_graph(conn)
        conn.execute("INSERT INTO project (id, name) VALUES (50, 'Deleted high id')")
        conn.execute("DELETE FROM project WHERE id = 50")
        conn.commit()
        table_info = [tuple(row) for row in conn.execute("PRAGMA table_info(project)")]
        foreign_keys = _project_foreign_keys(conn)
        before = {
            table: [dict(row) for row in conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid')]
            for table in ["project", *child_tables]
        }
        assert (
            conn.execute("SELECT seq FROM sqlite_sequence WHERE name = 'project'").fetchone()[0]
            == 50
        )

    _apply_0073(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        assert [tuple(row) for row in conn.execute("PRAGMA table_info(project)")] == table_info
        assert _project_foreign_keys(conn) == foreign_keys
        for table, rows in before.items():
            assert [
                dict(row) for row in conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid')
            ] == rows
        assert (
            conn.execute("SELECT seq FROM sqlite_sequence WHERE name = 'project'").fetchone()[0]
            == 50
        )
        next_id = conn.execute("INSERT INTO project (name) VALUES ('Next')").lastrowid
        assert next_id == 51
        conn.execute("INSERT INTO project (name, status) VALUES ('Ready', 'ready_to_process')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO project (name, status) VALUES ('Bad', 'bogus')")
        conn.rollback()
        conn.execute(
            "UPDATE project SET updated_at = '2000-01-01 00:00:00' WHERE id = ?", (project_id,)
        )
        conn.execute("UPDATE project SET name = 'Updated' WHERE id = ?", (project_id,))
        assert (
            conn.execute("SELECT updated_at FROM project WHERE id = ?", (project_id,)).fetchone()[0]
            != "2000-01-01 00:00:00"
        )
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM sqlite_schema "
                "WHERE type = 'index' AND name = 'idx_project_active'"
            ).fetchone()[0]
            == 1
        )
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_fresh_database_reaches_0073(tmp_path: Path):
    db_path = tmp_path / "fresh.db"
    _apply_through(db_path, MIGRATION_0073)
    with sqlite3.connect(db_path) as conn:
        sql = conn.execute(
            "SELECT sql FROM sqlite_schema WHERE type = 'table' AND name = 'project'"
        ).fetchone()[0]
        assert "ready_to_process" in sql
        conn.execute("INSERT INTO project (name, status) VALUES ('Ready', 'ready_to_process')")
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
