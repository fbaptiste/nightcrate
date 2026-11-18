"""Migration 0075 adds colour/raw facts and versions stored quality results."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from yoyo import get_backend, read_migrations

from nightcrate.db.migrations import MIGRATIONS_DIR

MIGRATION_0075 = "0075.colour_and_raw_frames"


def _apply_0075(path: Path) -> None:
    with get_backend(f"sqlite:///{path}") as backend:
        migrations = read_migrations(str(MIGRATIONS_DIR))
        backend.apply_migrations(
            backend.to_apply(migrations).filter(lambda migration: migration.id == MIGRATION_0075)
        )


def _project(conn: sqlite3.Connection) -> int:
    return conn.execute("INSERT INTO project (name) VALUES ('0075 project')").lastrowid


def _frame(
    conn: sqlite3.Connection,
    project_id: int,
    name: str,
    header: dict,
    *,
    path_suffix: str = ".fits",
) -> int:
    frame_id = conn.execute(
        "INSERT INTO sub_frame (project_id, content_hash, date_obs_utc, accepted, "
        "rejection_reason, rejection_source, hfr, star_count, "
        "median_adu, background_adu, snr_estimate, quality_analyzed_at, quality_status, "
        "quality_error, fits_header_json) VALUES (?, ?, '2026-11-01', 0, "
        "'user rejected', 'user', 2, 10, 100, 90, "
        "5, '2026-11-02', 'unreadable', 'quality error', ?)",
        (project_id, name, json.dumps(header)),
    ).lastrowid
    conn.execute(
        "INSERT INTO file_location (project_id, path, category, sub_frame_id) "
        "VALUES (?, ?, 'sub_frame', ?)",
        (project_id, f"/{name}{path_suffix}", frame_id),
    )
    return frame_id


def test_columns_and_checks(pre_migration_db):
    path = pre_migration_db(MIGRATION_0075)
    _apply_0075(path)
    with closing(sqlite3.connect(path)) as conn:
        sub_columns = {row[1] for row in conn.execute("PRAGMA table_info(sub_frame)")}
        assert {
            "iso",
            "camera_temp_c",
            "filter_name_source",
            "date_obs_source",
            "frame_type_basis",
            "file_metadata_json",
            "quality_method",
            "quality_units",
        } <= sub_columns
        assert "iso" in {row[1] for row in conn.execute("PRAGMA table_info(project_session)")}

        project_id = _project(conn)
        frame_id = conn.execute(
            "INSERT INTO sub_frame (project_id, content_hash, date_obs_utc) "
            "VALUES (?, 'checks', '2026-11-01')",
            (project_id,),
        ).lastrowid
        session_id = conn.execute(
            "INSERT INTO project_session (project_id, line_name, exposure_seconds, num_subs) "
            "VALUES (?, 'Ha', 60, 1)",
            (project_id,),
        ).lastrowid
        defaults = conn.execute(
            "SELECT iso, camera_temp_c, filter_name_source, date_obs_source, "
            "frame_type_basis, file_metadata_json, quality_method, quality_units "
            "FROM sub_frame WHERE id = ?",
            (frame_id,),
        ).fetchone()
        assert defaults == (None, None, "auto", "header", None, None, None, None)
        assert conn.execute(
            "SELECT iso FROM project_session WHERE id = ?", (session_id,)
        ).fetchone() == (None,)
        for column, value in (
            ("iso", 0),
            ("filter_name_source", "guess"),
            ("date_obs_source", "camera"),
            ("frame_type_basis", "path"),
            ("quality_units", "counts"),
        ):
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(f"UPDATE sub_frame SET {column} = ? WHERE id = ?", (value, frame_id))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE project_session SET iso = 0 WHERE id = ?", (session_id,))


def test_existing_rows_preserved_field_by_field(pre_migration_db):
    path = pre_migration_db(MIGRATION_0075)
    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        project_id = _project(conn)
        frame_id = conn.execute(
            "INSERT INTO sub_frame (project_id, content_hash, frame_type, accepted, "
            "rejection_reason, rejection_source, exposure_seconds, gain, sensor_temp_c, "
            "date_obs_utc, object_hint, filter_name_hint, frame_type_source) "
            "VALUES (?, 'preserved', 'light', 0, 'cloud', 'user', 120, 100, -10, "
            "'2026-11-01', 'M 31', 'Ha', 'user')",
            (project_id,),
        ).lastrowid
        session_id = conn.execute(
            "INSERT INTO project_session (project_id, line_name, exposure_seconds, num_subs) "
            "VALUES (?, 'Ha', 120, 3)",
            (project_id,),
        ).lastrowid
        before_frame = dict(
            conn.execute("SELECT * FROM sub_frame WHERE id = ?", (frame_id,)).fetchone()
        )
        before_session = dict(
            conn.execute("SELECT * FROM project_session WHERE id = ?", (session_id,)).fetchone()
        )
        conn.commit()

    _apply_0075(path)
    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        after_frame = dict(
            conn.execute("SELECT * FROM sub_frame WHERE id = ?", (frame_id,)).fetchone()
        )
        after_session = dict(
            conn.execute("SELECT * FROM project_session WHERE id = ?", (session_id,)).fetchone()
        )
        assert {key: after_frame[key] for key in before_frame} == before_frame
        assert {key: after_session[key] for key in before_session} == before_session
        assert after_frame["filter_name_source"] == "auto"
        assert after_frame["date_obs_source"] == "header"
        assert after_session["iso"] is None
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_quality_invalidation(pre_migration_db):
    path = pre_migration_db(MIGRATION_0075)
    with closing(sqlite3.connect(path)) as conn:
        project_id = _project(conn)
        keep = _frame(
            conn,
            project_id,
            "keep",
            {"BITPIX": 16, "BZERO": 32768, "NAXIS": 2},
        )
        keep_bscale_one = _frame(
            conn,
            project_id,
            "keep-bscale-one",
            {"BITPIX": 16, "BZERO": 32768, "BSCALE": 1, "NAXIS": 2},
        )
        xisf_without_timestamp = _frame(
            conn,
            project_id,
            "xisf-no-timestamp",
            {"XISF:SAMPLEFORMAT": "UInt16"},
            path_suffix=".xisf",
        )
        conn.execute(
            "UPDATE sub_frame SET quality_analyzed_at = NULL WHERE id = ?",
            (xisf_without_timestamp,),
        )
        clear = {
            xisf_without_timestamp,
            _frame(
                conn,
                project_id,
                "mosaic",
                {"BITPIX": 16, "BZERO": 32768, "NAXIS": 2, "BAYERPAT": "RGGB"},
            ),
            _frame(conn, project_id, "rgb", {"BITPIX": 16, "BZERO": 32768, "NAXIS": 3}),
            _frame(conn, project_id, "int16", {"BITPIX": 16, "NAXIS": 2}),
            _frame(
                conn,
                project_id,
                "scaled",
                {"BITPIX": 16, "BZERO": 32768, "BSCALE": 2, "NAXIS": 2},
            ),
            _frame(
                conn,
                project_id,
                "xisf-uint16",
                {"XISF:SAMPLEFORMAT": "UInt16", "NAXIS": 2},
                path_suffix=".xisf",
            ),
            _frame(
                conn,
                project_id,
                "xisf-bounds",
                {"XISF:SAMPLEFORMAT": "UInt16", "XISF:BOUNDS": "1000:5000"},
                path_suffix=".xisf",
            ),
            _frame(conn, project_id, "float", {"BITPIX": -32, "NAXIS": 2}),
        }
        conn.commit()

    _apply_0075(path)
    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        for frame_id in (keep, keep_bscale_one):
            kept = conn.execute("SELECT * FROM sub_frame WHERE id = ?", (frame_id,)).fetchone()
            assert kept["median_adu"] == 100
            assert kept["quality_analyzed_at"] == "2026-11-02"
            assert kept["quality_units"] == "adu"
            assert kept["quality_method"] is None
        for frame_id in clear:
            row = conn.execute("SELECT * FROM sub_frame WHERE id = ?", (frame_id,)).fetchone()
            for column in (
                "hfr",
                "star_count",
                "median_adu",
                "background_adu",
                "snr_estimate",
                "quality_analyzed_at",
                "quality_status",
                "quality_error",
                "quality_units",
            ):
                assert row[column] is None, (frame_id, column)
            assert row["rejection_reason"] == "user rejected"
            assert row["rejection_source"] == "user"


def test_matching_views_iso_and_raw_temperature(pre_migration_db):
    path = pre_migration_db(MIGRATION_0075)
    _apply_0075(path)
    with closing(sqlite3.connect(path)) as conn:
        project_id = _project(conn)

        def add(kind: str, digest: str, iso: int, temp: float, raw: bool = False) -> int:
            return conn.execute(
                "INSERT INTO sub_frame (project_id, content_hash, frame_type, exposure_seconds, "
                "gain, iso, set_temp_c, date_obs_utc, file_metadata_json) "
                "VALUES (?, ?, ?, 60, 100, ?, ?, '2026-11-01', ?)",
                (project_id, digest, kind, iso, temp, "{}" if raw else None),
            ).lastrowid

        raw_light = add("light", "raw-light", 800, -10, True)
        fits_light = add("light", "fits-light", 800, -10)
        matching_dark = add("dark", "dark-800", 800, 30)
        add("dark", "dark-1600", 1600, -10)
        flat = add("flat", "flat-800", 800, 0)
        add("flat", "flat-1600", 1600, 0)
        bias = add("bias", "bias-800", 800, 0)
        add("bias", "bias-1600", 1600, 0)
        conn.commit()

        assert conn.execute(
            "SELECT dark_id FROM matching_darks WHERE light_id = ?", (raw_light,)
        ).fetchall() == [(matching_dark,)]
        assert (
            conn.execute(
                "SELECT dark_id FROM matching_darks WHERE light_id = ?", (fits_light,)
            ).fetchall()
            == []
        )
        assert conn.execute(
            "SELECT flat_id FROM matching_flats WHERE light_id = ?", (raw_light,)
        ).fetchall() == [(flat,)]
        assert conn.execute(
            "SELECT bias_id FROM matching_bias WHERE light_id = ?", (raw_light,)
        ).fetchall() == [(bias,)]
