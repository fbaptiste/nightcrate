"""Migration 0076 corrects legacy capture-time provenance."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from yoyo import get_backend, read_migrations

from nightcrate.db.migrations import MIGRATIONS_DIR

MIGRATION_0076 = "0076.legacy_date_obs_source"


def _apply_0076(path: Path) -> None:
    with get_backend(f"sqlite:///{path}") as backend:
        migrations = read_migrations(str(MIGRATIONS_DIR))
        backend.apply_migrations(
            backend.to_apply(migrations).filter(lambda migration: migration.id == MIGRATION_0076)
        )


def test_legacy_file_times_are_relabelled_without_changing_other_fields(pre_migration_db):
    path = pre_migration_db(MIGRATION_0076)
    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        project_id = conn.execute("INSERT INTO project (name) VALUES ('0076 project')").lastrowid

        def add(
            name: str,
            header: str | None,
            *,
            file_metadata: str | None = None,
            source: str = "header",
            online: bool = True,
        ) -> int:
            frame_id = conn.execute(
                "INSERT INTO sub_frame "
                "(project_id, content_hash, frame_type, date_obs_utc, date_obs_source, "
                "fits_header_json, file_metadata_json) "
                "VALUES (?, ?, 'light', '2026-11-01T02:03:04Z', ?, ?, ?)",
                (project_id, name, source, header, file_metadata),
            ).lastrowid
            if online:
                conn.execute(
                    "INSERT INTO file_location (project_id, path, category, sub_frame_id) "
                    "VALUES (?, ?, 'sub_frame', ?)",
                    (project_id, f"/{name}.fits", frame_id),
                )
            return frame_id

        expected = {
            add("date-obs", json.dumps({"DATE-OBS": "2026-11-01T02:03:04"})): "header",
            add("date-utc", json.dumps({"DATE-UTC": "2026-11-01T02:03:04"})): "header",
            add("blank-date-obs", json.dumps({"DATE-OBS": "  "})): "file_time",
            add("no-header", None): "file_time",
            add("invalid-header", "{not json"): "file_time",
            add("offline", json.dumps({}), online=False): "file_time",
            add("new-raw", None, file_metadata="{}"): "header",
            add("already-file-time", None, source="file_time"): "file_time",
        }
        before = {
            row["id"]: dict(row)
            for row in conn.execute(
                "SELECT * FROM sub_frame WHERE project_id = ? ORDER BY id", (project_id,)
            )
        }
        conn.commit()

    _apply_0076(path)

    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        after = {
            row["id"]: dict(row)
            for row in conn.execute(
                "SELECT * FROM sub_frame WHERE project_id = ? ORDER BY id", (project_id,)
            )
        }
        for frame_id, expected_source in expected.items():
            unchanged = dict(after[frame_id])
            assert unchanged.pop("date_obs_source") == expected_source
            original = dict(before[frame_id])
            original.pop("date_obs_source")
            assert unchanged == original
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
