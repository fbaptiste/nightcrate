"""Preservation and vocabulary tests for migration 0066."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest
from yoyo import get_backend, read_migrations

from nightcrate.db.migrations import MIGRATIONS_DIR, apply_migrations


def _apply_through_0065(db_path: Path) -> None:
    with get_backend(f"sqlite:///{db_path}") as backend:
        migrations = read_migrations(str(MIGRATIONS_DIR))
        backend.apply_migrations(
            backend.to_apply(migrations).filter(
                lambda migration: migration.id <= "0065.project_solve_solver"
            )
        )


def _rows(conn: sqlite3.Connection, table: str) -> list[dict[str, object]]:
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in conn.execute(f'SELECT * FROM "{table}" ORDER BY id')]  # nosec B608


def test_migration_0066_preserves_dso_children(tmp_path: Path):
    db_path = tmp_path / "before-0066.db"
    _apply_through_0065(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        source_id = int(
            conn.execute(
                """
                INSERT INTO dso_catalog_source
                    (source_id, category, display_name, file_path, file_hash, attribution)
                VALUES ('test', 'nightcrate', 'Test', 'test.csv', 'hash', 'test')
                """
            ).lastrowid
        )
        conn.execute("INSERT INTO manufacturer (name) VALUES ('Sentinel maker')")
        sentinel_manufacturer_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.execute("INSERT INTO filter_type (name, display_name) VALUES ('sentinel', 'Sentinel')")
        sentinel_filter_type_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.execute(
            """
            INSERT INTO filter (manufacturer_id, filter_type_id, model_name)
            VALUES (?, ?, 'Sentinel filter')
            """,
            (sentinel_manufacturer_id, sentinel_filter_type_id),
        )
        sentinel_filter_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        dso_ids: list[int] = []
        for number in (1, 2):
            dso_ids.append(
                int(
                    conn.execute(
                        """
                        INSERT INTO dso (
                            primary_designation, obj_type, raw_obj_type, ra_deg, dec_deg,
                            constellation, maj_axis_arcmin, min_axis_arcmin,
                            position_angle_deg, mag_b, mag_v, mag_j, mag_h, mag_k,
                            surface_brightness, hubble_type, pm_ra, pm_dec, redshift,
                            radial_velocity, cstar_mag_u, cstar_mag_b, cstar_mag_v,
                            cstar_id, common_name, ned_notes, openngc_notes, raw_other_id,
                            popularity_rank, difficulty, recommended_filter_id,
                            source_catalog_id, source_row_hash, created_at, updated_at,
                            active, distance_pc, distance_method,
                            surface_brightness_augmented, common_name_augmented, source_key
                        ) VALUES (
                            ?, 'G', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'challenging', ?, ?, ?, ?,
                            ?, 0, ?, 'curated', 1, 1, ?
                        )
                        """,
                        (
                            f"TEST {number}",
                            f"raw-{number}",
                            10.0 + number,
                            -20.0 - number,
                            "Psc",
                            30.0 + number,
                            20.0 + number,
                            40.0 + number,
                            11.0 + number,
                            12.0 + number,
                            13.0 + number,
                            14.0 + number,
                            15.0 + number,
                            16.0 + number,
                            f"H{number}",
                            1.1 + number,
                            2.2 + number,
                            0.01 + number,
                            100.0 + number,
                            17.0 + number,
                            18.0 + number,
                            19.0 + number,
                            f"cstar-{number}",
                            f"common-{number}",
                            f"ned-{number}",
                            f"openngc-{number}",
                            f"other-{number}",
                            100 + number,
                            sentinel_filter_id,
                            source_id,
                            f"hash-{number}",
                            f"2026-01-0{number} 01:02:03",
                            f"2026-02-0{number} 04:05:06",
                            1000.0 + number,
                            f"key-{number}",
                        ),
                    ).lastrowid
                )
            )
        conn.executemany(
            """
            INSERT INTO dso_designation
                (dso_id, catalog, identifier, display_form, search_key, is_primary)
            VALUES (?, 'ngc', ?, ?, ?, 1)
            """,
            (
                (dso_ids[0], "1", "NGC 1", "ngc1"),
                (dso_ids[1], "2", "NGC 2", "ngc2"),
            ),
        )
        conn.execute(
            """
            INSERT INTO dso_external_ref
                (dso_id, provider, identifier, created_at, updated_at)
            VALUES (?, 'simbad', 'NGC 1', '2026-03-01', '2026-03-02')
            """,
            (dso_ids[0],),
        )
        conn.execute(
            """
            INSERT INTO thumbnail_cache
                (dso_id, variant, width, height, file_path, source, bytes)
            VALUES (?, 'list', 10, 10, 'thumb.jpg', 'placeholder', 1)
            """,
            (dso_ids[0],),
        )
        conn.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (dso_ids[0],))
        conn.execute(
            "INSERT INTO location (name, latitude, longitude, timezone) VALUES ('L',0,0,'UTC')"
        )
        location_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.execute(
            """
            INSERT INTO location_horizon (location_id,name,type,source)
            VALUES (?, 'H', 'custom', 'drawn')
            """,
            (location_id,),
        )
        horizon_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.execute("INSERT INTO manufacturer (name) VALUES ('Test maker')")
        manufacturer_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.execute(
            """
            INSERT INTO sensor (
                manufacturer_id, model_name, sensor_type, pixel_size_um,
                resolution_x, resolution_y
            ) VALUES (?, 'S', 'mono', 3.76, 10, 10)
            """,
            (manufacturer_id,),
        )
        sensor_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.execute(
            "INSERT INTO camera (manufacturer_id,sensor_id,model_name) VALUES (?,?,'C')",
            (manufacturer_id, sensor_id),
        )
        camera_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.execute(
            "INSERT INTO telescope (manufacturer_id,model_name,aperture_mm) VALUES (?,'T',100)",
            (manufacturer_id,),
        )
        telescope_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.execute(
            """
            INSERT INTO telescope_configuration (
                telescope_id, config_name, effective_focal_length_mm,
                effective_focal_ratio
            ) VALUES (?, 'native', 500, 5)
            """,
            (telescope_id,),
        )
        config_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.execute(
            "INSERT INTO rig (name,telescope_configuration_id,camera_id) VALUES ('R',?,?)",
            (config_id, camera_id),
        )
        rig_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.execute(
            "INSERT INTO target_plan (dso_id,location_id,horizon_id,rig_id) VALUES (?,?,?,?)",
            (dso_ids[0], location_id, horizon_id, rig_id),
        )
        conn.execute("INSERT INTO project (name) VALUES ('P')")
        project_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.execute(
            "INSERT INTO project_target (project_id,dso_id) VALUES (?,?)",
            (project_id, dso_ids[0]),
        )
        conn.execute(
            """
            INSERT INTO project_solve (
                project_id,image_path,image_width,image_height,center_ra_deg,
                center_dec_deg,cd1_1,cd1_2,cd2_1,cd2_2,crpix1,crpix2
            ) VALUES (?, 'x', 10, 10, 0, 0, 1, 0, 0, 1, 5, 5)
            """,
            (project_id,),
        )
        solve_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.execute(
            "INSERT INTO project_dso (solve_id,dso_id,is_main) VALUES (?,?,1)",
            (solve_id, dso_ids[0]),
        )
        tables = (
            "dso",
            "dso_designation",
            "dso_external_ref",
            "thumbnail_cache",
            "favorite_target",
            "target_plan",
            "project_target",
            "project_dso",
        )
        before = {table: _rows(conn, table) for table in tables}
        columns = {
            table: [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')]
            for table in tables
        }
        conn.commit()

    apply_migrations(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        # Later migrations may add columns (0071 adds thumbnail_cache.render_key);
        # every value that existed before 0066 must come through unchanged.
        after = {
            table: [
                {column: row[column] for column in columns[table]} for row in _rows(conn, table)
            ]
            for table in tables
        }
        assert after == before
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        for table in (
            "dso_designation",
            "dso_external_ref",
            "thumbnail_cache",
            "favorite_target",
            "project_target",
            "project_dso",
        ):
            assert "dso" in {row[2] for row in conn.execute(f'PRAGMA foreign_key_list("{table}")')}

        conn.execute(
            """
            INSERT INTO dso_designation
                (dso_id,catalog,identifier,display_form,search_key,is_primary)
            VALUES (?, 'wr', '134', 'WR 134', 'wr134', 0)
            """,
            (dso_ids[0],),
        )
        conn.execute(
            """
            INSERT INTO dso_designation
                (dso_id,catalog,identifier,display_form,search_key,is_primary)
            VALUES (?, 'wr', '135', 'WR 135', 'wr135', 0)
            """,
            (dso_ids[0],),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO dso_designation
                    (dso_id,catalog,identifier,display_form,search_key,is_primary)
                VALUES (?, 'hh', '1', 'HH 1', 'hh1', 1)
                """,
                (dso_ids[0],),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO dso_designation
                    (dso_id,catalog,identifier,display_form,search_key,is_primary)
                VALUES (?, 'unknown', '1', 'X 1', 'x1', 0)
                """,
                (dso_ids[0],),
            )
        old_updated = conn.execute(
            "SELECT updated_at FROM dso WHERE id = ?", (dso_ids[0],)
        ).fetchone()[0]
        time.sleep(1.01)
        conn.execute(
            "UPDATE dso SET primary_designation = primary_designation WHERE id = ?",
            (dso_ids[0],),
        )
        assert (
            conn.execute("SELECT updated_at FROM dso WHERE id = ?", (dso_ids[0],)).fetchone()[0]
            > old_updated
        )

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_migration_0066_fresh_database(tmp_path: Path):
    db_path = tmp_path / "fresh.db"
    apply_migrations(db_path)
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert {
            "dso_group",
            "dso_group_member",
            "dso_source_entry",
            "dso_catalog_applied",
        } <= {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
