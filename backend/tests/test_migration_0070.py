"""Migration 0070 adds night notes without changing existing records."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from yoyo import get_backend, read_migrations

from nightcrate.db.migrations import MIGRATIONS_DIR
from tests.test_migration_0069 import _equipment, _frame, _project, _rig, _setup

MIGRATION_0069 = "0069.rig_setups_and_project_software"
MIGRATION_0070 = "0070.project_night_notes"


def _apply_through(db_path: Path, migration_id: str) -> None:
    with get_backend(f"sqlite:///{db_path}") as backend:
        migrations = read_migrations(str(MIGRATIONS_DIR))
        backend.apply_migrations(
            backend.to_apply(migrations).filter(lambda migration: migration.id <= migration_id)
        )


def _apply_0070(db_path: Path) -> None:
    with get_backend(f"sqlite:///{db_path}") as backend:
        migrations = read_migrations(str(MIGRATIONS_DIR))
        backend.apply_migrations(
            backend.to_apply(migrations).filter(lambda migration: migration.id == MIGRATION_0070)
        )


def _table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE '_yoyo_%'"
        )
    ]
    return {
        table: conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in tables
    }


def test_upgrade_preserves_all_counts_and_selected_rows(tmp_path: Path):
    db_path = tmp_path / "upgrade.db"
    _apply_through(db_path, MIGRATION_0069)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        equipment = _equipment(conn)
        rig_id = _rig(conn, equipment, "Migration rig", equipment.camera_a)
        project_id = _project(conn, "Migration project")
        frame_id = _frame(conn, project_id, rig_id, "migration-frame")
        setup_id = _setup(conn, rig_id, equipment.config, equipment.camera_a)
        conn.execute(
            "INSERT INTO sub_frame_rig_setup VALUES (?, ?, ?)",
            (frame_id, rig_id, setup_id),
        )
        conn.execute(
            "INSERT INTO project_session "
            "(project_id, rig_id, rig_setup_id, line_name, exposure_seconds, num_subs, "
            "session_date, source) VALUES (?, ?, ?, 'Ha', 300, 4, '2026-10-15', 'auto')",
            (project_id, rig_id, setup_id),
        )
        conn.commit()
        before_counts = _table_counts(conn)
        preserved = {
            table: [dict(row) for row in conn.execute(f"SELECT * FROM {table}")]
            for table in ("project", "project_session", "sub_frame_rig_setup")
        }

    _apply_0070(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        after_counts = _table_counts(conn)
        assert {table: after_counts[table] for table in before_counts} == before_counts
        assert after_counts["project_night_note"] == 0
        for table, expected in preserved.items():
            assert [dict(row) for row in conn.execute(f"SELECT * FROM {table}")] == expected
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_fresh_database_reaches_0070(tmp_path: Path):
    db_path = tmp_path / "fresh.db"
    _apply_through(db_path, MIGRATION_0070)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'project_night_note'"
        ).fetchone()[0]
        assert "PRIMARY KEY (project_id, night_date)" in sql
        project_id = conn.execute("INSERT INTO project (name) VALUES ('Fresh')").lastrowid
        conn.execute(
            "INSERT INTO project_night_note (project_id, night_date, notes) VALUES (?, ?, ?)",
            (project_id, "2026-10-15", "First light"),
        )
        conn.execute("DELETE FROM project WHERE id = ?", (project_id,))
        assert conn.execute("SELECT COUNT(*) FROM project_night_note").fetchone()[0] == 0
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
