"""Migration 0069 preserves existing catalogs and enforces setup history."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pytest
from yoyo import get_backend, read_migrations

from nightcrate.db.migrations import MIGRATIONS_DIR

MIGRATION_0068 = "0068.clear_thumbnail_crops"
MIGRATION_0069 = "0069.rig_setups_and_project_software"


def _apply_through(db_path: Path, migration_id: str) -> None:
    with get_backend(f"sqlite:///{db_path}") as backend:
        migrations = read_migrations(str(MIGRATIONS_DIR))
        backend.apply_migrations(
            backend.to_apply(migrations).filter(lambda migration: migration.id <= migration_id)
        )


def _apply_0069(db_path: Path) -> None:
    with get_backend(f"sqlite:///{db_path}") as backend:
        migrations = read_migrations(str(MIGRATIONS_DIR))
        backend.apply_migrations(
            backend.to_apply(migrations).filter(lambda migration: migration.id == MIGRATION_0069)
        )


def _insert(conn: sqlite3.Connection, sql: str, values: tuple = ()) -> int:
    row_id = conn.execute(sql, values).lastrowid
    assert row_id is not None
    return row_id


@dataclass(frozen=True)
class Equipment:
    config: int
    other_config: int
    camera_a: int
    camera_b: int
    camera_c: int
    camera_d: int
    software_a: int
    software_b: int


def _equipment(conn: sqlite3.Connection) -> Equipment:
    maker = _insert(conn, "INSERT INTO manufacturer (name) VALUES ('Test maker')")
    telescope = _insert(
        conn,
        "INSERT INTO telescope (manufacturer_id, model_name, aperture_mm) VALUES (?, 'Scope', 100)",
        (maker,),
    )
    config = _insert(
        conn,
        """
        INSERT INTO telescope_configuration
            (telescope_id, config_name, effective_focal_length_mm,
             effective_focal_ratio, is_native)
        VALUES (?, '550 mm', 550, 5.5, 1)
        """,
        (telescope,),
    )
    other_config = _insert(
        conn,
        """
        INSERT INTO telescope_configuration
            (telescope_id, config_name, effective_focal_length_mm, effective_focal_ratio)
        VALUES (?, '700 mm', 700, 7)
        """,
        (telescope,),
    )
    sensor_a = _insert(
        conn,
        """
        INSERT INTO sensor
            (manufacturer_id, model_name, sensor_type, pixel_size_um,
             resolution_x, resolution_y, adc_bit_depth)
        VALUES (?, 'Sensor A', 'mono', 2.40, 5544, 3694, 12)
        """,
        (maker,),
    )
    sensor_b = _insert(
        conn,
        """
        INSERT INTO sensor
            (manufacturer_id, model_name, sensor_type, pixel_size_um,
             resolution_x, resolution_y, adc_bit_depth)
        VALUES (?, 'Sensor B', 'mono', 3.76, 6280, 4210, 16)
        """,
        (maker,),
    )
    cameras = [
        _insert(
            conn,
            "INSERT INTO camera (manufacturer_id, sensor_id, model_name) VALUES (?, ?, ?)",
            (maker, sensor, name),
        )
        for name, sensor in (
            ("Camera A", sensor_a),
            ("Camera B", sensor_b),
            ("Camera C", sensor_b),
            ("Camera D", sensor_b),
        )
    ]
    software_a = _insert(
        conn,
        "INSERT INTO software (manufacturer_id, name) VALUES (?, 'Program A')",
        (maker,),
    )
    software_b = _insert(
        conn,
        "INSERT INTO software (manufacturer_id, name) VALUES (?, 'Program B')",
        (maker,),
    )
    return Equipment(
        config,
        other_config,
        cameras[0],
        cameras[1],
        cameras[2],
        cameras[3],
        software_a,
        software_b,
    )


def _rig(conn: sqlite3.Connection, equipment: Equipment, name: str, camera_id: int) -> int:
    return _insert(
        conn,
        "INSERT INTO rig (name, telescope_configuration_id, camera_id) VALUES (?, ?, ?)",
        (name, equipment.config, camera_id),
    )


def _project(conn: sqlite3.Connection, name: str = "Project A") -> int:
    return _insert(conn, "INSERT INTO project (name) VALUES (?)", (name,))


def _frame(
    conn: sqlite3.Connection,
    project_id: int,
    rig_id: int,
    content_hash: str,
    frame_type: str = "light",
) -> int:
    return _insert(
        conn,
        """
        INSERT INTO sub_frame
            (project_id, content_hash, rig_id, frame_type, date_obs_utc,
             exposure_seconds, gain, binning_x, binning_y, set_temp_c,
             filter_name_hint)
        VALUES (?, ?, ?, ?, '2026-11-01T03:00:00+00:00', 60, 100, 1, 1, -10, 'L')
        """,
        (project_id, content_hash, rig_id, frame_type),
    )


def _setup(
    conn: sqlite3.Connection,
    rig_id: int,
    config_id: int,
    camera_id: int,
    until_at: str = "2026-11-07T12:00:00+00:00",
) -> int:
    return _insert(
        conn,
        """
        INSERT INTO rig_setup
            (rig_id, until_at, telescope_configuration_id, camera_id)
        VALUES (?, ?, ?, ?)
        """,
        (rig_id, until_at, config_id, camera_id),
    )


def test_upgrade_preserves_records(tmp_path: Path):
    db_path = tmp_path / "upgrade.db"
    _apply_through(db_path, MIGRATION_0068)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        equipment = _equipment(conn)
        rig_id = _rig(conn, equipment, "Main rig", equipment.camera_a)
        project_id = _project(conn)
        conn.execute("INSERT INTO project_rig VALUES (?, ?)", (project_id, rig_id))
        _frame(conn, project_id, rig_id, "frame-1")
        _frame(conn, project_id, rig_id, "frame-2")
        conn.execute(
            """
            INSERT INTO project_session
                (project_id, rig_id, line_name, exposure_seconds, num_subs, session_date)
            VALUES (?, ?, 'Lum', 60, 2, '2026-11-01')
            """,
            (project_id, rig_id),
        )
        conn.execute(
            "INSERT INTO project_source_folder (project_id, path, rig_id) VALUES (?, ?, ?)",
            (project_id, "/synthetic/project-a", rig_id),
        )
        tables = (
            "rig",
            "project",
            "project_rig",
            "sub_frame",
            "project_session",
            "project_source_folder",
        )
        before = {
            table: [dict(row) for row in conn.execute(f"SELECT * FROM {table}")] for table in tables
        }
        conn.commit()

    _apply_0069(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        for table in tables:
            after = [dict(row) for row in conn.execute(f"SELECT * FROM {table}")]
            if table == "project_session":
                assert all(row.pop("rig_setup_id") is None for row in after)
            assert after == before[table]
        assert conn.execute("SELECT COUNT(*) FROM sub_frame_rig_setup").fetchone()[0] == 0
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_fresh_database_has_new_objects(tmp_path: Path):
    db_path = tmp_path / "fresh.db"
    _apply_through(db_path, MIGRATION_0069)
    expected_tables = {
        "rig_setup",
        "rig_setup_filter_slot",
        "rig_setup_software",
        "sub_frame_rig_setup",
        "project_rig_change",
        "project_rig_change_filter_slot",
        "project_rig_change_software",
        "software_version",
        "project_software",
    }
    expected_views = {
        "sub_frame_equipment",
        "matching_darks",
        "matching_flats",
        "matching_bias",
        "calibration_coverage",
    }
    with sqlite3.connect(db_path) as conn:
        objects = set(
            conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        )
        views = set(conn.execute("SELECT name FROM sqlite_master WHERE type = 'view'").fetchall())
        assert {(name,) for name in expected_tables} <= objects
        assert {(name,) for name in expected_views} <= views
        columns = {row[1] for row in conn.execute("PRAGMA table_info(project_session)")}
        assert "rig_setup_id" in columns


def test_view_resolves_change_then_stamp_then_rig(tmp_path: Path):
    db_path = tmp_path / "view.db"
    _apply_through(db_path, MIGRATION_0069)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        equipment = _equipment(conn)
        rig_1 = _rig(conn, equipment, "Main rig", equipment.camera_a)
        rig_2 = _rig(conn, equipment, "Travel rig", equipment.camera_d)
        project_id = _project(conn)
        f1 = _frame(conn, project_id, rig_1, "f1")
        f2 = _frame(conn, project_id, rig_1, "f2")
        f3 = _frame(conn, project_id, rig_1, "f3")
        setup_id = _setup(conn, rig_1, equipment.config, equipment.camera_b)
        conn.executemany(
            "INSERT INTO sub_frame_rig_setup VALUES (?, ?, ?)",
            ((f1, rig_1, setup_id), (f3, rig_1, setup_id)),
        )
        conn.execute("UPDATE sub_frame SET rig_id = ? WHERE id = ?", (rig_2, f3))
        rows = dict(conn.execute("SELECT sub_frame_id, camera_id FROM sub_frame_equipment"))
        assert rows == {f1: equipment.camera_b, f2: equipment.camera_a, f3: equipment.camera_d}
        conn.execute(
            "INSERT INTO project_rig_change (project_id, rig_id, camera_id) VALUES (?, ?, ?)",
            (project_id, rig_1, equipment.camera_c),
        )
        rows = dict(conn.execute("SELECT sub_frame_id, camera_id FROM sub_frame_equipment"))
        assert rows == {f1: equipment.camera_c, f2: equipment.camera_c, f3: equipment.camera_d}


def test_stamp_must_match_its_rig(tmp_path: Path):
    db_path = tmp_path / "stamp.db"
    _apply_through(db_path, MIGRATION_0069)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        equipment = _equipment(conn)
        rig_1 = _rig(conn, equipment, "Main rig", equipment.camera_a)
        rig_2 = _rig(conn, equipment, "Travel rig", equipment.camera_b)
        frame_id = _frame(conn, _project(conn), rig_2, "f1")
        setup_id = _setup(conn, rig_1, equipment.config, equipment.camera_a)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO sub_frame_rig_setup VALUES (?, ?, ?)",
                (frame_id, rig_2, setup_id),
            )


def test_deletes_cascade_through_setups_and_stamps(tmp_path: Path):
    db_path = tmp_path / "cascade.db"
    _apply_through(db_path, MIGRATION_0069)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        equipment = _equipment(conn)
        rig_1 = _rig(conn, equipment, "Main rig", equipment.camera_a)
        rig_2 = _rig(conn, equipment, "Travel rig", equipment.camera_b)
        project_1 = _project(conn)
        frame_1 = _frame(conn, project_1, rig_1, "f1")
        setup_1 = _setup(conn, rig_1, equipment.config, equipment.camera_a)
        conn.execute("INSERT INTO sub_frame_rig_setup VALUES (?, ?, ?)", (frame_1, rig_1, setup_1))
        conn.execute("UPDATE sub_frame SET rig_id = ? WHERE id = ?", (rig_2, frame_1))
        conn.execute("DELETE FROM rig WHERE id = ?", (rig_1,))
        assert (
            conn.execute("SELECT COUNT(*) FROM rig_setup WHERE id = ?", (setup_1,)).fetchone()[0]
            == 0
        )
        assert conn.execute("SELECT COUNT(*) FROM sub_frame_rig_setup").fetchone()[0] == 0
        assert (
            conn.execute("SELECT rig_id FROM sub_frame WHERE id = ?", (frame_1,)).fetchone()[0]
            == rig_2
        )

        project_2 = _project(conn, "Project B")
        frame_2 = _frame(conn, project_2, rig_2, "f2")
        setup_2 = _setup(conn, rig_2, equipment.config, equipment.camera_b)
        conn.execute("INSERT INTO sub_frame_rig_setup VALUES (?, ?, ?)", (frame_2, rig_2, setup_2))
        conn.execute("DELETE FROM project WHERE id = ?", (project_2,))
        assert conn.execute("SELECT COUNT(*) FROM sub_frame_rig_setup").fetchone()[0] == 0
        assert (
            conn.execute("SELECT COUNT(*) FROM rig_setup WHERE id = ?", (setup_2,)).fetchone()[0]
            == 1
        )


def test_project_software_rules(tmp_path: Path):
    db_path = tmp_path / "software.db"
    _apply_through(db_path, MIGRATION_0069)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        equipment = _equipment(conn)
        project_id = _project(conn)
        version_a = _insert(
            conn,
            "INSERT INTO software_version (software_id, version) VALUES (?, '1.0')",
            (equipment.software_a,),
        )
        conn.execute(
            "INSERT INTO project_software (project_id, software_id) VALUES (?, ?)",
            (project_id, equipment.software_a),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO project_software (project_id, software_id) VALUES (?, ?)",
                (project_id, equipment.software_a),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO project_software
                    (project_id, software_id, software_version_id)
                VALUES (?, ?, ?)
                """,
                (project_id, equipment.software_b, version_a),
            )
        conn.execute("DELETE FROM project WHERE id = ?", (project_id,))
        assert conn.execute("SELECT COUNT(*) FROM project_software").fetchone()[0] == 0


def test_calibration_matches_only_same_camera(tmp_path: Path):
    db_path = tmp_path / "calibration.db"
    _apply_through(db_path, MIGRATION_0069)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        equipment = _equipment(conn)
        rig_id = _rig(conn, equipment, "Main rig", equipment.camera_a)
        project_id = _project(conn)
        setup_b = _setup(conn, rig_id, equipment.config, equipment.camera_b)
        setup_other_scope = _setup(
            conn, rig_id, equipment.other_config, equipment.camera_b, "2026-11-08T12:00:00+00:00"
        )
        frame_ids: dict[str, int] = {}
        for label, frame_type in (
            ("light-b", "light"),
            ("dark-a", "dark"),
            ("dark-b", "dark"),
            ("flat-a", "flat"),
            ("flat-b", "flat"),
            ("flat-other-scope", "flat"),
            ("bias-a", "bias"),
            ("bias-b", "bias"),
        ):
            frame_ids[label] = _frame(conn, project_id, rig_id, label, frame_type)
        for label in ("light-b", "dark-b", "flat-b", "bias-b"):
            conn.execute(
                "INSERT INTO sub_frame_rig_setup VALUES (?, ?, ?)",
                (frame_ids[label], rig_id, setup_b),
            )
        conn.execute(
            "INSERT INTO sub_frame_rig_setup VALUES (?, ?, ?)",
            (frame_ids["flat-other-scope"], rig_id, setup_other_scope),
        )
        assert conn.execute("SELECT dark_id FROM matching_darks").fetchall() == [
            (frame_ids["dark-b"],)
        ]
        assert conn.execute("SELECT flat_id FROM matching_flats").fetchall() == [
            (frame_ids["flat-b"],)
        ]
        assert conn.execute("SELECT bias_id FROM matching_bias").fetchall() == [
            (frame_ids["bias-b"],)
        ]
