"""Migration 0071 adds checklist cache identity without losing cache rows."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest
from yoyo import get_backend, read_migrations

from nightcrate.db.migrations import MIGRATIONS_DIR
from tests.test_migration_0070 import _apply_through

MIGRATION_0070 = "0070.project_night_notes"
MIGRATION_0071 = "0071.thumbnail_checklist"


def _apply_0071(db_path: Path) -> None:
    with get_backend(f"sqlite:///{db_path}") as backend:
        migrations = read_migrations(str(MIGRATIONS_DIR))
        backend.apply_migrations(
            backend.to_apply(migrations).filter(lambda migration: migration.id == MIGRATION_0071)
        )


def _dso(conn: sqlite3.Connection) -> int:
    source = conn.execute(
        """
        INSERT INTO dso_catalog_source
            (source_id, category, display_name, file_path, file_hash)
        VALUES ('migration-71', 'nightcrate', 'Migration', '/tmp/catalog', 'hash')
        """
    ).lastrowid
    return int(
        conn.execute(
            """
            INSERT INTO dso (
                primary_designation, obj_type, ra_deg, dec_deg,
                source_catalog_id, source_row_hash, source_key
            ) VALUES ('M 1', 'SNR', 83.6331, 22.0145, ?, 'row', 'm1')
            """,
            (source,),
        ).lastrowid
    )


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_migration_0071_preserves_rows(tmp_path: Path):
    db_path = tmp_path / "upgrade.db"
    _apply_through(db_path, MIGRATION_0070)
    files = [tmp_path / f"cache-{index}.jpg" for index in range(3)]
    for index, path in enumerate(files):
        path.write_bytes(bytes([index + 1]) * 256)
    before_hashes = [_digest(path) for path in files]

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        dso_id = _dso(conn)
        rows = (
            (
                dso_id,
                "list",
                180,
                180,
                None,
                None,
                None,
                None,
                str(files[0]),
                "dss2_color",
                256,
                None,
            ),
            (
                dso_id,
                "detail",
                800,
                800,
                None,
                None,
                None,
                None,
                str(files[1]),
                "placeholder",
                0,
                "offline",
            ),
            (
                dso_id,
                "rig_framed",
                180,
                180,
                370,
                280,
                None,
                None,
                str(files[2]),
                "dss2_color",
                256,
                None,
            ),
        )
        conn.executemany(
            """
            INSERT INTO thumbnail_cache (
                dso_id, variant, width, height,
                fov_major_deg_x1000, fov_minor_deg_x1000,
                center_ra_deg_x1000, center_dec_deg_x1000,
                file_path, source, bytes, fetch_error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
        before = [dict(row) for row in conn.execute("SELECT * FROM thumbnail_cache ORDER BY id")]

    _apply_0071(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        after = [dict(row) for row in conn.execute("SELECT * FROM thumbnail_cache ORDER BY id")]
        assert [
            {key: value for key, value in row.items() if key != "render_key"} for row in after
        ] == before
        assert all(row["render_key"] is None for row in after)

        indexes = {
            row["name"]
            for row in conn.execute("PRAGMA index_list('thumbnail_cache')")
            if row["name"].startswith("idx_thumbnail_cache")
        }
        assert indexes == {
            "idx_thumbnail_cache_unique",
            "idx_thumbnail_cache_last_access",
            "idx_thumbnail_cache_dso",
        }
        unique_columns = [
            row["name"] for row in conn.execute("PRAGMA index_info('idx_thumbnail_cache_unique')")
        ]
        assert unique_columns == [
            "dso_id",
            "variant",
            "width",
            "height",
            None,
            None,
            None,
            None,
            None,
        ]
        sql = conn.execute(
            "SELECT sql FROM sqlite_schema WHERE name = 'idx_thumbnail_cache_unique'"
        ).fetchone()[0]
        compact = " ".join(sql.split()).lower()
        assert "coalesce(fov_major_deg_x1000, -1)" in compact
        assert "coalesce(center_ra_deg_x1000, -999999)" in compact
        assert "coalesce(render_key, '')" in compact

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO thumbnail_cache
                    (dso_id, variant, width, height, file_path, source, bytes)
                VALUES (?, 'list', 180, 180, 'different-list.jpg', 'dss2_color', 1)
                """,
                (dso_id,),
            )
        conn.rollback()

        conn.execute(
            """
            INSERT INTO thumbnail_cache
                (dso_id, variant, width, height, render_key, file_path, source, bytes)
            VALUES (?, 'checklist', 800, 600, 'r1_a', 'check-a.jpg', 'dss2_color', 1)
            """,
            (dso_id,),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO thumbnail_cache
                    (dso_id, variant, width, height, render_key, file_path, source, bytes)
                VALUES (?, 'checklist', 800, 600, 'r1_a', 'check-b.jpg', 'dss2_color', 1)
                """,
                (dso_id,),
            )
        conn.rollback()
        conn.execute(
            """
            INSERT INTO thumbnail_cache
                (dso_id, variant, width, height, render_key, file_path, source, bytes)
            VALUES (?, 'checklist', 800, 600, 'r1_a', 'check-a.jpg', 'dss2_color', 1),
                   (?, 'checklist', 800, 600, 'r1_b', 'check-b.jpg', 'dss2_color', 1)
            """,
            (dso_id, dso_id),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO thumbnail_cache
                    (dso_id, variant, width, height, render_key, file_path, source, bytes)
                VALUES (?, 'checklist', 800, 600, 'r1_c', 'check-a.jpg', 'dss2_color', 1)
                """,
                (dso_id,),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO thumbnail_cache
                    (dso_id, variant, width, height, file_path, source, bytes)
                VALUES (?, 'bogus', 1, 1, 'bogus.jpg', 'dss2_color', 1)
                """,
                (dso_id,),
            )
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

    assert [_digest(path) for path in files] == before_hashes


def test_fresh_database_has_checklist_variant(tmp_path: Path):
    db_path = tmp_path / "fresh.db"
    _apply_through(db_path, MIGRATION_0071)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        dso_id = _dso(conn)
        conn.execute(
            """
            INSERT INTO thumbnail_cache
                (dso_id, variant, width, height, render_key, file_path, source, bytes)
            VALUES (?, 'checklist', 800, 600, 'r1_test', 'test.jpg', 'dss2_color', 1)
            """,
            (dso_id,),
        )
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
