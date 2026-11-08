"""Clear obsolete thumbnail crops while preserving their id sequence."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from yoyo import get_backend, read_migrations

from nightcrate.db.migrations import MIGRATIONS_DIR

MIGRATION_0067 = "0067.dso_other_names"
MIGRATION_0068 = "0068.clear_thumbnail_crops"


def _applied_migrations(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT migration_id FROM _yoyo_migration")}


def _apply_through_0067(db_path: Path) -> None:
    with get_backend(f"sqlite:///{db_path}") as backend:
        migrations = read_migrations(str(MIGRATIONS_DIR))
        backend.apply_migrations(
            backend.to_apply(migrations).filter(lambda migration: migration.id <= MIGRATION_0067)
        )


def _apply_0068(db_path: Path) -> None:
    with get_backend(f"sqlite:///{db_path}") as backend:
        migrations = read_migrations(str(MIGRATIONS_DIR))
        backend.apply_migrations(
            backend.to_apply(migrations).filter(lambda migration: migration.id == MIGRATION_0068)
        )


def test_0068_clears_crops_and_preserves_sequence(tmp_path: Path):
    db_path = tmp_path / "crops.db"
    _apply_through_0067(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        assert MIGRATION_0067 in _applied_migrations(conn)
        assert MIGRATION_0068 not in _applied_migrations(conn)
        project_id = int(
            conn.execute("INSERT INTO project (name) VALUES ('Framed project')").lastrowid
        )
        main_id = int(
            conn.execute(
                "INSERT INTO project_image (project_id, file_path, is_main) VALUES (?, ?, 1)",
                (project_id, "/synthetic/main.fits"),
            ).lastrowid
        )
        other_id = int(
            conn.execute(
                "INSERT INTO project_image (project_id, file_path) VALUES (?, ?)",
                (project_id, "/synthetic/other.fits"),
            ).lastrowid
        )
        for size, source_image_id in (
            ("small", None),
            ("medium", None),
            ("large", other_id),
        ):
            conn.execute(
                """
                INSERT INTO project_thumbnail (project_id, size, source_image_id)
                VALUES (?, ?, ?)
                """,
                (project_id, size, source_image_id),
            )
        project_before = conn.execute(
            "SELECT * FROM project WHERE id = ?", (project_id,)
        ).fetchone()
        images_before = conn.execute(
            "SELECT * FROM project_image WHERE project_id = ? ORDER BY id",
            (project_id,),
        ).fetchall()
        assert conn.execute("SELECT id FROM project_thumbnail ORDER BY id").fetchall() == [
            (1,),
            (2,),
            (3,),
        ]
        conn.commit()

    _apply_0068(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        assert MIGRATION_0068 in _applied_migrations(conn)
        assert conn.execute("SELECT * FROM project_thumbnail").fetchall() == []
        assert (
            conn.execute("SELECT * FROM project WHERE id = ?", (project_id,)).fetchone()
            == project_before
        )
        assert (
            conn.execute(
                "SELECT * FROM project_image WHERE project_id = ? ORDER BY id",
                (project_id,),
            ).fetchall()
            == images_before
        )
        next_id = int(
            conn.execute(
                """
                INSERT INTO project_thumbnail (project_id, size, source_image_id)
                VALUES (?, 'small', ?)
                """,
                (project_id, main_id),
            ).lastrowid
        )
        assert next_id == 4
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
