"""Migration 0074 removes only the obsolete folder/frame target labels."""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from yoyo import get_backend, read_migrations
from yoyo.backends import SQLiteBackend

from nightcrate.db.migrations import MIGRATIONS_DIR, apply_migrations
from tests.test_migration_0069 import _equipment, _rig
from tests.test_migration_0070 import _apply_through

MIGRATION_0073 = "0073.project_ready_to_process"
MIGRATION_0074 = "0074.drop_folder_and_frame_target"
REMOVED = {
    "project_source_folder": {"project_target_id"},
    "sub_frame": {"project_target_id", "project_target_source"},
}


def _apply_0074(path: Path) -> None:
    with get_backend(f"sqlite:///{path}") as backend:
        migrations = read_migrations(str(MIGRATIONS_DIR))
        backend.apply_migrations(
            backend.to_apply(migrations).filter(lambda migration: migration.id == MIGRATION_0074)
        )


def _normalise(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


def _table_xinfo(conn: sqlite3.Connection, table: str) -> list[tuple]:
    return [tuple(row)[1:] for row in conn.execute(f'PRAGMA table_xinfo("{table}")')]


def _foreign_keys(conn: sqlite3.Connection) -> set[tuple]:
    result = set()
    for (table,) in conn.execute(
        "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ):
        for row in conn.execute(f'PRAGMA foreign_key_list("{table}")'):
            result.add((table, row[3], row[2], row[4], row[5], row[6], row[7]))
    return result


def _objects(conn: sqlite3.Connection) -> dict[tuple[str, str], str]:
    return {
        (row[0], row[1]): _normalise(row[2])
        for row in conn.execute(
            "SELECT type, name, sql FROM sqlite_schema "
            "WHERE tbl_name IN ('sub_frame', 'project_source_folder') "
            "AND type IN ('index', 'trigger') AND sql IS NOT NULL"
        )
    }


def _rows(conn: sqlite3.Connection, table: str) -> list[dict]:
    return [dict(row) for row in conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid')]


def _child_tables(conn: sqlite3.Connection) -> set[str]:
    result = set()
    for (table,) in conn.execute(
        "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ):
        if any(
            row[2] in {"sub_frame", "project_source_folder"}
            for row in conn.execute(f'PRAGMA foreign_key_list("{table}")')
        ):
            result.add(table)
    return result


def _seed_graph(conn: sqlite3.Connection) -> tuple[int, int, int]:
    equipment = _equipment(conn)
    rig_id = _rig(conn, equipment, "0074 rig", equipment.camera_a)
    setup_id = conn.execute(
        "INSERT INTO rig_setup "
        "(rig_id, until_at, telescope_configuration_id, camera_id) VALUES (?, ?, ?, ?)",
        (rig_id, "2026-11-01", equipment.config, equipment.camera_a),
    ).lastrowid
    source_id = conn.execute(
        "INSERT INTO dso_catalog_source "
        "(source_id, category, display_name, file_path, file_hash) "
        "VALUES ('0074', 'nightcrate', 'Migration 0074', '/synthetic', 'hash')"
    ).lastrowid
    dso_ids = []
    for index in range(2):
        dso_ids.append(
            conn.execute(
                "INSERT INTO dso "
                "(primary_designation, obj_type, source_catalog_id, source_row_hash) "
                "VALUES (?, 'Other', ?, ?)",
                (f"TEST {index + 1}", source_id, f"row-{index}"),
            ).lastrowid
        )
    project_id = conn.execute("INSERT INTO project (name) VALUES ('0074 project')").lastrowid
    targets = [
        conn.execute(
            "INSERT INTO project_target (project_id, dso_id) VALUES (?, ?)",
            (project_id, dso_id),
        ).lastrowid
        for dso_id in dso_ids
    ]
    run_id = conn.execute(
        "INSERT INTO ingestion_run (project_id, source_path) VALUES (?, '/source')",
        (project_id,),
    ).lastrowid
    session_id = conn.execute(
        "INSERT INTO session (project_id, rig_id, start_utc, end_utc) VALUES (?, ?, ?, ?)",
        (project_id, rig_id, "2026-11-01T00:00:00Z", "2026-11-01T02:00:00Z"),
    ).lastrowid
    folder_id = conn.execute(
        "INSERT INTO project_source_folder "
        "(project_id, path, is_primary, rig_id, project_target_id) VALUES (?, ?, 1, ?, ?)",
        (project_id, "/source", rig_id, targets[0]),
    ).lastrowid
    frame_id = conn.execute(
        """
        INSERT INTO sub_frame (
            project_id, content_hash, session_id, rig_id, project_target_id,
            ingestion_run_id, frame_type, accepted, rejection_source,
            exposure_seconds, gain, date_obs_utc, object_hint, filter_name_hint,
            frame_type_source, project_target_source, quality_status
        ) VALUES (?, 'frame-hash', ?, ?, ?, ?, 'light', 1, 'user',
                  120, 100, '2026-11-01T00:30:00Z', 'TEST', 'Ha',
                  'user', 'user', 'ok')
        """,
        (project_id, session_id, rig_id, targets[0], run_id),
    ).lastrowid
    conn.execute(
        "INSERT INTO session_event "
        "(session_id, event_utc, event_type, related_sub_frame_id) VALUES (?, ?, ?, ?)",
        (session_id, "2026-11-01T00:30:00Z", "exposure_end", frame_id),
    )
    conn.execute(
        "INSERT INTO file_location (project_id, path, category, sub_frame_id) "
        "VALUES (?, '/source/frame.fits', 'sub_frame', ?)",
        (project_id, frame_id),
    )
    conn.execute(
        "INSERT INTO sub_frame_rig_setup (sub_frame_id, rig_id, rig_setup_id) VALUES (?, ?, ?)",
        (frame_id, rig_id, setup_id),
    )
    conn.execute("UPDATE project SET cover_sub_frame_id = ? WHERE id = ?", (frame_id, project_id))

    conn.execute(
        "INSERT INTO project_source_folder "
        "(id, project_id, path, project_target_id) VALUES (80, ?, '/deleted', ?)",
        (project_id, targets[1]),
    )
    conn.execute("DELETE FROM project_source_folder WHERE id = 80")
    conn.execute(
        "INSERT INTO sub_frame "
        "(id, project_id, content_hash, project_target_id, date_obs_utc) "
        "VALUES (90, ?, 'deleted-frame', ?, '2026-11-01')",
        (project_id, targets[1]),
    )
    conn.execute("DELETE FROM sub_frame WHERE id = 90")
    conn.commit()
    return int(project_id), int(folder_id), int(frame_id)


def _expected_create_sql(table: str, sql: str) -> str:
    if table == "project_source_folder":
        return sql.replace(
            ", project_target_id INTEGER REFERENCES project_target(id) ON DELETE SET NULL", ""
        )
    return sql.replace(
        "    project_target_id        INTEGER REFERENCES project_target(id) ON DELETE SET NULL,\n",
        "",
    ).replace(
        ", project_target_source TEXT NOT NULL DEFAULT 'auto'\n"
        "    CHECK (project_target_source IN ('auto', 'user'))",
        "",
    )


def test_upgrade_preserves_everything_except_target_labels(pre_migration_db):
    path = pre_migration_db(MIGRATION_0074)
    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        project_id, _folder_id, _frame_id = _seed_graph(conn)
        children = _child_tables(conn)
        assert children == {"file_location", "project", "session_event", "sub_frame_rig_setup"}
        tracked_tables = {"project_source_folder", "sub_frame", *children}
        before_rows = {table: _rows(conn, table) for table in tracked_tables}
        before_info = {table: _table_xinfo(conn, table) for table in REMOVED}
        before_sql = {
            table: conn.execute(
                "SELECT sql FROM sqlite_schema WHERE type='table' AND name=?", (table,)
            ).fetchone()[0]
            for table in REMOVED
        }
        before_fks = _foreign_keys(conn)
        before_objects = _objects(conn)
        before_sequences = dict(
            conn.execute(
                "SELECT name, seq FROM sqlite_sequence "
                "WHERE name IN ('sub_frame', 'project_source_folder')"
            )
        )
        summary = dict(
            conn.execute(
                "SELECT * FROM session_summary WHERE project_id = ?", (project_id,)
            ).fetchone()
        )
        summary.pop("distinct_targets")
        other_views = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_schema WHERE type='view' AND name != 'session_summary'"
            )
        ]

    _apply_0074(path)

    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        for table, removed in REMOVED.items():
            assert _table_xinfo(conn, table) == [
                column for column in before_info[table] if column[0] not in removed
            ]
            actual_sql = conn.execute(
                "SELECT sql FROM sqlite_schema WHERE type='table' AND name=?", (table,)
            ).fetchone()[0]
            assert _normalise(actual_sql) == _normalise(
                _expected_create_sql(table, before_sql[table])
            )

        for table, rows in before_rows.items():
            expected = [
                {key: value for key, value in row.items() if key not in REMOVED.get(table, set())}
                for row in rows
            ]
            assert _rows(conn, table) == expected

        removed_edges = {
            (
                "project_source_folder",
                "project_target_id",
                "project_target",
                "id",
                "NO ACTION",
                "SET NULL",
                "NONE",
            ),
            (
                "sub_frame",
                "project_target_id",
                "project_target",
                "id",
                "NO ACTION",
                "SET NULL",
                "NONE",
            ),
        }
        assert _foreign_keys(conn) == before_fks - removed_edges
        assert _objects(conn) == {
            key: sql
            for key, sql in before_objects.items()
            if key[1] not in {"idx_source_folder_target", "idx_sub_frame_target"}
        }
        assert (
            dict(
                conn.execute(
                    "SELECT name, seq FROM sqlite_sequence "
                    "WHERE name IN ('sub_frame', 'project_source_folder')"
                )
            )
            == before_sequences
        )
        assert (
            conn.execute(
                "INSERT INTO project_source_folder (project_id, path) VALUES (?, '/next')",
                (project_id,),
            ).lastrowid
            > 80
        )
        assert (
            conn.execute(
                "INSERT INTO sub_frame (project_id, content_hash, date_obs_utc) "
                "VALUES (?, 'next-frame', '2026-11-02')",
                (project_id,),
            ).lastrowid
            > 90
        )

        after_summary = dict(
            conn.execute(
                "SELECT * FROM session_summary WHERE project_id = ?", (project_id,)
            ).fetchone()
        )
        assert "distinct_targets" not in after_summary
        assert after_summary == summary
        for view in other_views:
            conn.execute(f'SELECT * FROM "{view}" LIMIT 1').fetchall()

        probes = (
            (
                "INSERT INTO project_source_folder (project_id, path, is_primary) VALUES (?, ?, 2)",
                (project_id, "/bad-primary"),
            ),
            (
                "INSERT INTO sub_frame "
                "(project_id, content_hash, date_obs_utc, frame_type) "
                "VALUES (?, ?, '2026-11-03', 'bad')",
                (project_id, "bad-type"),
            ),
            (
                "INSERT INTO sub_frame "
                "(project_id, content_hash, date_obs_utc, frame_type_source) "
                "VALUES (?, ?, '2026-11-03', 'bad')",
                (project_id, "bad-source"),
            ),
            (
                "INSERT INTO sub_frame "
                "(project_id, content_hash, date_obs_utc, accepted) "
                "VALUES (?, ?, '2026-11-03', 2)",
                (project_id, "bad-accepted"),
            ),
            (
                "INSERT INTO sub_frame "
                "(project_id, content_hash, date_obs_utc, rejection_source) "
                "VALUES (?, ?, '2026-11-03', 'bad')",
                (project_id, "bad-rejection"),
            ),
            (
                "INSERT INTO sub_frame "
                "(project_id, content_hash, date_obs_utc, exposure_seconds) "
                "VALUES (?, ?, '2026-11-03', -1)",
                (project_id, "bad-exposure"),
            ),
            (
                "INSERT INTO sub_frame "
                "(project_id, content_hash, date_obs_utc, quality_status) "
                "VALUES (?, ?, '2026-11-03', 'bad')",
                (project_id, "bad-quality"),
            ),
        )
        for sql, params in probes:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(sql, params)
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_fresh_database_reaches_0074(tmp_path: Path):
    path = tmp_path / "fresh.db"
    _apply_through(path, MIGRATION_0074)
    with closing(sqlite3.connect(path)) as conn:
        assert "project_target_id" not in {
            row[1] for row in conn.execute("PRAGMA table_xinfo(project_source_folder)")
        }
        assert {"project_target_id", "project_target_source"}.isdisjoint(
            {row[1] for row in conn.execute("PRAGMA table_xinfo(sub_frame)")}
        )
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_real_entry_point_disables_foreign_keys_on_every_yoyo_connection(
    pre_migration_db, monkeypatch
):
    path = pre_migration_db(MIGRATION_0074, "foreign-keys-default-on.db")
    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        project_id, _folder_id, _frame_id = _seed_graph(conn)
        before = {
            table: _rows(conn, table)
            for table in ("file_location", "session_event", "sub_frame_rig_setup", "project")
        }

    original_connect = SQLiteBackend.connect
    connections = 0

    def foreign_keys_on_connect(backend, dburi):
        nonlocal connections
        connection = original_connect(backend, dburi)
        connection.execute("PRAGMA foreign_keys = ON")
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        connections += 1
        return connection

    monkeypatch.setattr(SQLiteBackend, "connect", foreign_keys_on_connect)
    apply_migrations(path)

    assert connections >= 2  # Root backend plus yoyo's per-migration copy.
    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        assert {
            table: _rows(conn, table)
            for table in ("file_location", "session_event", "sub_frame_rig_setup", "project")
        } == before
        assert (
            conn.execute(
                "SELECT cover_sub_frame_id FROM project WHERE id = ?", (project_id,)
            ).fetchone()[0]
            is not None
        )
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
