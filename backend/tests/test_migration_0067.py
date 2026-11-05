"""Name normalization and preservation tests for migration 0067."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from yoyo import get_backend, read_migrations

from nightcrate.db.migrations import MIGRATIONS_DIR, apply_migrations

MIGRATION_0066 = "0066.more_catalogs"
MIGRATION_0067 = "0067.dso_other_names"
USER_LINK_TABLES = ("favorite_target", "target_plan", "project_target", "project_dso")


def _apply_through_0066(db_path: Path) -> None:
    with get_backend(f"sqlite:///{db_path}") as backend:
        migrations = read_migrations(str(MIGRATIONS_DIR))
        backend.apply_migrations(
            backend.to_apply(migrations).filter(lambda migration: migration.id <= MIGRATION_0066)
        )


def _applied_migrations(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT migration_id FROM _yoyo_migration").fetchall()}


def _rows(conn: sqlite3.Connection, table: str) -> list[tuple[object, ...]]:
    return conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall()  # nosec B608


def _insert_dso(
    conn: sqlite3.Connection,
    source_id: int,
    number: int,
    common_name: str | None,
    *,
    active: int = 1,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO dso (
            primary_designation, obj_type, common_name, source_catalog_id,
            source_row_hash, active
        ) VALUES (?, 'G', ?, ?, ?, ?)
        """,
        (f"TEST {number}", common_name, source_id, f"hash-{number}", active),
    )
    return int(cursor.lastrowid)


def _prepare_database(db_path: Path) -> tuple[sqlite3.Connection, int]:
    _apply_through_0066(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    migrations = _applied_migrations(conn)
    assert MIGRATION_0066 in migrations
    assert MIGRATION_0067 not in migrations
    cursor = conn.execute(
        """
        INSERT INTO dso_catalog_source
            (source_id, category, display_name, file_path, file_hash, attribution)
        VALUES ('test-0067', 'nightcrate', 'Test 0067', 'test.csv', 'hash', 'test')
        """
    )
    conn.commit()
    return conn, int(cursor.lastrowid)


def _apply_0067_preserving_ids_and_links(db_path: Path, conn: sqlite3.Connection) -> None:
    dso_ids_before = [row[0] for row in conn.execute("SELECT id FROM dso ORDER BY id")]
    links_before = {table: _rows(conn, table) for table in USER_LINK_TABLES}
    conn.commit()
    conn.close()

    apply_migrations(db_path)

    with sqlite3.connect(db_path) as migrated:
        migrated.execute("PRAGMA foreign_keys = ON")
        assert MIGRATION_0067 in _applied_migrations(migrated)
        assert [row[0] for row in migrated.execute("SELECT id FROM dso ORDER BY id")] == (
            dso_ids_before
        )
        assert {table: _rows(migrated, table) for table in USER_LINK_TABLES} == links_before
        assert migrated.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert migrated.execute("PRAGMA foreign_key_check").fetchall() == []


def _other_names(conn: sqlite3.Connection, dso_id: int) -> list[tuple[str, int]]:
    return conn.execute(
        """
        SELECT name, position
        FROM dso_other_name
        WHERE dso_id = ?
        ORDER BY position
        """,
        (dso_id,),
    ).fetchall()


def test_0067_splits_comma_names(tmp_path: Path):
    db_path = tmp_path / "split.db"
    conn, source_id = _prepare_database(db_path)
    dso_id = _insert_dso(
        conn,
        source_id,
        1,
        "Barbell Nebula,Cork Nebula,Little Dumbbell Nebula",
    )

    _apply_0067_preserving_ids_and_links(db_path, conn)

    with sqlite3.connect(db_path) as migrated:
        assert (
            migrated.execute("SELECT common_name FROM dso WHERE id = ?", (dso_id,)).fetchone()[0]
            == "Barbell Nebula"
        )
        assert _other_names(migrated, dso_id) == [
            ("Cork Nebula", 1),
            ("Little Dumbbell Nebula", 2),
        ]


def test_0067_trims_and_dedupes(tmp_path: Path):
    db_path = tmp_path / "dedupe.db"
    conn, source_id = _prepare_database(db_path)
    dso_id = _insert_dso(conn, source_id, 1, " A , a ,B")

    _apply_0067_preserving_ids_and_links(db_path, conn)

    with sqlite3.connect(db_path) as migrated:
        assert (
            migrated.execute("SELECT common_name FROM dso WHERE id = ?", (dso_id,)).fetchone()[0]
            == "A"
        )
        assert _other_names(migrated, dso_id) == [("B", 1)]


def test_0067_keeps_single_and_null_names(tmp_path: Path):
    db_path = tmp_path / "single-null.db"
    conn, source_id = _prepare_database(db_path)
    single_id = _insert_dso(conn, source_id, 1, "Orion Nebula")
    null_id = _insert_dso(conn, source_id, 2, None)

    _apply_0067_preserving_ids_and_links(db_path, conn)

    with sqlite3.connect(db_path) as migrated:
        assert migrated.execute("SELECT id, common_name FROM dso ORDER BY id").fetchall() == [
            (single_id, "Orion Nebula"),
            (null_id, None),
        ]
        assert migrated.execute("SELECT * FROM dso_other_name").fetchall() == []


def test_0067_splits_inactive_retained_names(tmp_path: Path):
    db_path = tmp_path / "inactive.db"
    conn, source_id = _prepare_database(db_path)
    dso_id = _insert_dso(conn, source_id, 1, "First Name,Second Name", active=0)
    project_id = int(
        conn.execute("INSERT INTO project (name) VALUES ('Retained project')").lastrowid
    )
    conn.execute(
        "INSERT INTO project_target (project_id, dso_id) VALUES (?, ?)",
        (project_id, dso_id),
    )

    _apply_0067_preserving_ids_and_links(db_path, conn)

    with sqlite3.connect(db_path) as migrated:
        assert migrated.execute(
            "SELECT active, common_name FROM dso WHERE id = ?", (dso_id,)
        ).fetchone() == (0, "First Name")
        assert _other_names(migrated, dso_id) == [("Second Name", 1)]
        assert migrated.execute("SELECT project_id, dso_id FROM project_target").fetchall() == [
            (project_id, dso_id)
        ]


def test_0067_on_fresh_database(tmp_path: Path):
    db_path = tmp_path / "fresh.db"
    conn, _ = _prepare_database(db_path)

    _apply_0067_preserving_ids_and_links(db_path, conn)

    with sqlite3.connect(db_path) as migrated:
        assert {
            row[0]
            for row in migrated.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        } >= {"dso_other_name", "dso_group"}
        assert "common_name" in {row[1] for row in migrated.execute("PRAGMA table_info(dso_group)")}


def test_0067_rejects_bad_names(tmp_path: Path):
    db_path = tmp_path / "constraints.db"
    conn, source_id = _prepare_database(db_path)
    dso_id = _insert_dso(conn, source_id, 1, None)

    _apply_0067_preserving_ids_and_links(db_path, conn)

    with sqlite3.connect(db_path) as migrated:
        migrated.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError):
            migrated.execute(
                "INSERT INTO dso_other_name (dso_id, name, position) VALUES (?, '  ', 1)",
                (dso_id,),
            )
        with pytest.raises(sqlite3.IntegrityError):
            migrated.execute(
                "INSERT INTO dso_other_name (dso_id, name, position) VALUES (?, 'A,B', 1)",
                (dso_id,),
            )
        assert migrated.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert migrated.execute("PRAGMA foreign_key_check").fetchall() == []
