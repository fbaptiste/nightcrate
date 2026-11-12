"""Migration 0072 adds typed scan failures without changing existing rows."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from yoyo import get_backend, read_migrations

from nightcrate.db.migrations import MIGRATIONS_DIR
from tests.test_migration_0070 import _apply_through, _table_counts

MIGRATION_0071 = "0071.thumbnail_checklist"
MIGRATION_0072 = "0072.uncataloged_file"


def _apply_0072(db_path: Path) -> None:
    with get_backend(f"sqlite:///{db_path}") as backend:
        migrations = read_migrations(str(MIGRATIONS_DIR))
        backend.apply_migrations(
            backend.to_apply(migrations).filter(lambda migration: migration.id == MIGRATION_0072)
        )


def test_migration_0072_preserves_existing_rows_and_enforces_contract(tmp_path: Path):
    db_path = tmp_path / "upgrade.db"
    _apply_through(db_path, MIGRATION_0071)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        project_id = conn.execute("INSERT INTO project (name) VALUES ('Retained')").lastrowid
        run_id = conn.execute(
            "INSERT INTO ingestion_run (project_id, source_path) VALUES (?, '/data')",
            (project_id,),
        ).lastrowid
        conn.commit()
        before_counts = _table_counts(conn)
        before_rows = {
            table: [dict(row) for row in conn.execute(f'SELECT * FROM "{table}"')]
            for table in before_counts
        }

    _apply_0072(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        after_counts = _table_counts(conn)
        assert {table: after_counts[table] for table in before_counts} == before_counts
        for table, rows in before_rows.items():
            assert [dict(row) for row in conn.execute(f'SELECT * FROM "{table}"')] == rows

        conn.execute(
            "INSERT INTO uncataloged_file (project_id, path, reason, message, run_id) "
            "VALUES (?, '/data/bad.xisf', 'damaged', 'bad', ?)",
            (project_id, run_id),
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO uncataloged_file (project_id, path, reason, message) "
                "VALUES (?, '/data/bad.xisf', 'unreadable', 'again')",
                (project_id,),
            )
        conn.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO uncataloged_file (project_id, path, reason, message) "
                "VALUES (?, '/data/nope.fits', 'other', 'bad reason')",
                (project_id,),
            )
        conn.rollback()
        conn.execute("DELETE FROM ingestion_run WHERE id = ?", (run_id,))
        assert conn.execute("SELECT run_id FROM uncataloged_file").fetchone()[0] is None
        conn.execute("DELETE FROM project WHERE id = ?", (project_id,))
        assert conn.execute("SELECT COUNT(*) FROM uncataloged_file").fetchone()[0] == 0
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_fresh_database_reaches_0072(tmp_path: Path):
    db_path = tmp_path / "fresh.db"
    _apply_through(db_path, MIGRATION_0072)
    with sqlite3.connect(db_path) as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM sqlite_schema WHERE type = 'table' "
                "AND name = 'uncataloged_file'"
            ).fetchone()[0]
            == 1
        )
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
