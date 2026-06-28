"""Tests for the imaging-core schema (migration 0037).

Covers the load-bearing schema behaviors per the Imaging Core Schema spec §15:
content-hash idempotency, the light-needs-filter CHECK, each calibration-match
view (±1 °C dark temp, flat telescope-configuration join, never-on-filter darks,
accepted-only, library NULL-session frames), single-band vs duoband integration
counting, NULL-safe goal-vs-actual, session_summary, the updated_at trigger, the
project.cover_sub_frame_id back-reference, and one-primary source folders.
"""

from __future__ import annotations

import itertools

import aiosqlite
import pytest

from nightcrate.db.session import get_db_path

_HASH_COUNTER = itertools.count(1)


async def _connect() -> aiosqlite.Connection:
    conn = await aiosqlite.connect(str(get_db_path()))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys = ON")
    return conn


@pytest.fixture
async def graph():
    """Build an equipment + project graph and yield (connection, id-map)."""
    conn = await _connect()
    ids: dict[str, int] = {}

    cur = await conn.execute("INSERT INTO manufacturer (name) VALUES ('TestCo')")
    ids["mfr"] = cur.lastrowid
    cur = await conn.execute(
        "INSERT INTO sensor (manufacturer_id, model_name, sensor_type, pixel_size_um, "
        "resolution_x, resolution_y) VALUES (?, 'IMX571', 'mono', 3.76, 6248, 4176)",
        (ids["mfr"],),
    )
    ids["sensor"] = cur.lastrowid
    cur = await conn.execute(
        "INSERT INTO camera (manufacturer_id, sensor_id, model_name) VALUES (?, ?, 'Cam A')",
        (ids["mfr"], ids["sensor"]),
    )
    ids["camera"] = cur.lastrowid
    cur = await conn.execute(
        "INSERT INTO camera (manufacturer_id, sensor_id, model_name) VALUES (?, ?, 'Cam B')",
        (ids["mfr"], ids["sensor"]),
    )
    ids["camera_b"] = cur.lastrowid
    cur = await conn.execute(
        "INSERT INTO telescope (manufacturer_id, model_name, aperture_mm) "
        "VALUES (?, 'Scope X', 280)",
        (ids["mfr"],),
    )
    ids["tele"] = cur.lastrowid
    for key, name, fl in [("cfg_native", "Native", 2800), ("cfg_reducer", "0.7x", 1960)]:
        cur = await conn.execute(
            "INSERT INTO telescope_configuration (telescope_id, config_name, "
            "effective_focal_length_mm, effective_focal_ratio) VALUES (?, ?, ?, ?)",
            (ids["tele"], name, fl, 7.0),
        )
        ids[key] = cur.lastrowid

    cur = await conn.execute("INSERT INTO filter_type (name) VALUES ('Narrowband')")
    ids["ftype"] = cur.lastrowid
    # Single-band Ha filter.
    cur = await conn.execute(
        "INSERT INTO filter (manufacturer_id, filter_type_id, model_name) VALUES (?, ?, 'Ha 7nm')",
        (ids["mfr"], ids["ftype"]),
    )
    ids["ha"] = cur.lastrowid
    await conn.execute(
        "INSERT INTO filter_passband (filter_id, line_name, central_wavelength_nm, bandwidth_nm) "
        "VALUES (?, 'Ha', 656.3, 7)",
        (ids["ha"],),
    )
    # Duoband Ha+Oiii filter.
    cur = await conn.execute(
        "INSERT INTO filter (manufacturer_id, filter_type_id, model_name) VALUES (?, ?, 'Duo')",
        (ids["mfr"], ids["ftype"]),
    )
    ids["duo"] = cur.lastrowid
    for line, cw in [("Ha", 656.3), ("Oiii", 500.7)]:
        await conn.execute(
            "INSERT INTO filter_passband (filter_id, line_name, central_wavelength_nm, "
            "bandwidth_nm) VALUES (?, ?, ?, 7)",
            (ids["duo"], line, cw),
        )

    cur = await conn.execute("INSERT INTO project (name) VALUES ('Test Project')")
    ids["project"] = cur.lastrowid
    cur = await conn.execute(
        "INSERT INTO dso_catalog_source (source_id, category, display_name, file_path, file_hash) "
        "VALUES ('test-src', 'nightcrate', 'Test Source', '/x', 'h')"
    )
    ids["dso_source"] = cur.lastrowid
    cur = await conn.execute(
        "INSERT INTO dso (primary_designation, obj_type, source_catalog_id, source_row_hash) "
        "VALUES ('NGC 1', 'Neb', ?, 'rowhash')",
        (ids["dso_source"],),
    )
    ids["dso"] = cur.lastrowid
    cur = await conn.execute(
        "INSERT INTO project_target (project_id, dso_id) VALUES (?, ?)",
        (ids["project"], ids["dso"]),
    )
    ids["target"] = cur.lastrowid
    cur = await conn.execute(
        "INSERT INTO session (project_id, rig_id, start_utc, end_utc) "
        "VALUES (?, NULL, '2026-03-15T22:00:00', '2026-03-16T05:00:00')",
        (ids["project"],),
    )
    ids["session"] = cur.lastrowid

    await conn.commit()
    yield conn, ids
    await conn.close()


async def _insert_sub(conn: aiosqlite.Connection, **kw) -> int:
    """Insert a sub_frame with sensible defaults; overrides via kwargs. Returns id."""
    row = {
        "content_hash": f"hash-{next(_HASH_COUNTER)}",
        "frame_type": "light",
        "accepted": 1,
        "camera_id": None,
        "telescope_configuration_id": None,
        "filter_id": None,
        "gain": 100,
        "offset_adu": 50,
        "set_temp_c": -10.0,
        "exposure_seconds": 300.0,
        "binning_x": 1,
        "binning_y": 1,
        "session_id": None,
        "project_target_id": None,
        "date_obs_utc": "2026-03-15T23:00:00",
    }
    row.update(kw)
    cols = ", ".join(row.keys())
    placeholders = ", ".join("?" for _ in row)
    cur = await conn.execute(
        f"INSERT INTO sub_frame ({cols}) VALUES ({placeholders})",  # noqa: S608 - keys are fixed
        tuple(row.values()),
    )
    return cur.lastrowid


async def _scalar(conn: aiosqlite.Connection, sql: str, params: tuple = ()) -> object:
    cur = await conn.execute(sql, params)
    row = await cur.fetchone()
    return row[0] if row else None


# ── Schema sanity + constraints ──────────────────────────────────────────────


class TestSchemaObjects:
    async def test_tables_and_views_exist(self, graph):
        conn, _ = graph
        cur = await conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")
        names = {r["name"] for r in await cur.fetchall()}
        for t in [
            "session",
            "sub_frame",
            "processed_image",
            "file_location",
            "ingestion_run",
            "session_log_file",
            "session_event",
            "autofocus_run",
            "guiding_log_file",
            "guiding_sample",
            "dither_event",
            "project_source_folder",
        ]:
            assert t in names, f"missing table {t}"
        for v in [
            "matching_darks",
            "matching_flats",
            "matching_bias",
            "calibration_coverage",
            "integration_time_per_project_filter",
            "project_filter_goal_progress",
            "session_summary",
        ]:
            assert v in names, f"missing view {v}"

    async def test_content_hash_unique(self, graph):
        conn, ids = graph
        await _insert_sub(conn, content_hash="dup", frame_type="bias", camera_id=ids["camera"])
        with pytest.raises(aiosqlite.IntegrityError):
            await _insert_sub(conn, content_hash="dup", frame_type="bias", camera_id=ids["camera"])

    async def test_light_ingests_without_resolved_filter(self, graph):
        conn, ids = graph
        # A light's filter_id is routinely NULL at v0.40.0 ingest (rig assignment
        # is v0.41.0); the raw FILTER header is kept in filter_name_hint instead.
        # There is no light-needs-filter CHECK — ingest must never fail on this.
        light_id = await _insert_sub(
            conn,
            frame_type="light",
            filter_id=None,
            filter_name_hint="Ha",
            camera_id=ids["camera"],
        )
        assert light_id > 0
        hint = await _scalar(
            conn, "SELECT filter_name_hint FROM sub_frame WHERE id = ?", (light_id,)
        )
        assert hint == "Ha"
        # Calibration without a filter is fine too.
        bias_id = await _insert_sub(
            conn, frame_type="bias", filter_id=None, camera_id=ids["camera"]
        )
        assert bias_id > 0

    async def test_exposure_nonnegative(self, graph):
        conn, ids = graph
        # Bias at 0 s is allowed.
        ok = await _insert_sub(
            conn, frame_type="bias", exposure_seconds=0.0, camera_id=ids["camera"]
        )
        assert ok > 0
        with pytest.raises(aiosqlite.IntegrityError):
            await _insert_sub(
                conn, frame_type="bias", exposure_seconds=-1.0, camera_id=ids["camera"]
            )

    async def test_updated_at_trigger(self, graph):
        conn, ids = graph
        sid = await _insert_sub(conn, frame_type="bias", camera_id=ids["camera"])
        await conn.execute(
            "UPDATE sub_frame SET updated_at = '2000-01-01 00:00:00' WHERE id = ?", (sid,)
        )
        await conn.execute("UPDATE sub_frame SET accepted = 0 WHERE id = ?", (sid,))
        ts = await _scalar(conn, "SELECT updated_at FROM sub_frame WHERE id = ?", (sid,))
        assert ts != "2000-01-01 00:00:00"

    async def test_project_cover_sub_frame_id(self, graph):
        conn, ids = graph
        sid = await _insert_sub(conn, frame_type="bias", camera_id=ids["camera"])
        await conn.execute(
            "UPDATE project SET cover_sub_frame_id = ? WHERE id = ?", (sid, ids["project"])
        )
        got = await _scalar(
            conn, "SELECT cover_sub_frame_id FROM project WHERE id = ?", (ids["project"],)
        )
        assert got == sid

    async def test_source_folder_one_primary(self, graph):
        conn, ids = graph
        await conn.execute(
            "INSERT INTO project_source_folder (project_id, path, is_primary) VALUES (?, '/a', 1)",
            (ids["project"],),
        )
        # A second primary for the same project violates the partial unique index.
        with pytest.raises(aiosqlite.IntegrityError):
            await conn.execute(
                "INSERT INTO project_source_folder (project_id, path, is_primary) "
                "VALUES (?, '/b', 1)",
                (ids["project"],),
            )
        # A non-primary second folder is fine.
        await conn.execute(
            "INSERT INTO project_source_folder (project_id, path, is_primary) VALUES (?, '/b', 0)",
            (ids["project"],),
        )


# ── Calibration-matching views ───────────────────────────────────────────────


class TestCalibrationViews:
    async def test_matching_darks_temp_tolerance(self, graph):
        conn, ids = graph
        light = await _insert_sub(
            conn, frame_type="light", filter_id=ids["ha"], camera_id=ids["camera"], set_temp_c=-10.0
        )
        # Within ±1 °C → matches.
        in_tol = await _insert_sub(
            conn, frame_type="dark", camera_id=ids["camera"], set_temp_c=-10.8
        )
        # Outside ±1 °C → no match.
        await _insert_sub(conn, frame_type="dark", camera_id=ids["camera"], set_temp_c=-12.0)
        rows = await (
            await conn.execute("SELECT dark_id FROM matching_darks WHERE light_id = ?", (light,))
        ).fetchall()
        assert {r["dark_id"] for r in rows} == {in_tol}

    async def test_matching_darks_never_on_filter_and_exposure(self, graph):
        conn, ids = graph
        light = await _insert_sub(
            conn,
            frame_type="light",
            filter_id=ids["ha"],
            camera_id=ids["camera"],
            exposure_seconds=300.0,
        )
        # Same camera/gain/binning/temp but different exposure → no match.
        await _insert_sub(conn, frame_type="dark", camera_id=ids["camera"], exposure_seconds=120.0)
        # Matching exposure → match (darks carry no filter; matching ignores filter).
        good = await _insert_sub(
            conn, frame_type="dark", camera_id=ids["camera"], exposure_seconds=300.0
        )
        rows = await (
            await conn.execute("SELECT dark_id FROM matching_darks WHERE light_id = ?", (light,))
        ).fetchall()
        assert {r["dark_id"] for r in rows} == {good}

    async def test_matching_darks_excludes_rejected(self, graph):
        conn, ids = graph
        light = await _insert_sub(
            conn, frame_type="light", filter_id=ids["ha"], camera_id=ids["camera"]
        )
        await _insert_sub(conn, frame_type="dark", camera_id=ids["camera"], accepted=0)
        count = await _scalar(
            conn, "SELECT COUNT(*) FROM matching_darks WHERE light_id = ?", (light,)
        )
        assert count == 0

    async def test_library_dark_null_session_matches(self, graph):
        conn, ids = graph
        light = await _insert_sub(
            conn,
            frame_type="light",
            filter_id=ids["ha"],
            camera_id=ids["camera"],
            session_id=ids["session"],
        )
        # Library dark has no session — must still match.
        lib = await _insert_sub(conn, frame_type="dark", camera_id=ids["camera"], session_id=None)
        rows = await (
            await conn.execute("SELECT dark_id FROM matching_darks WHERE light_id = ?", (light,))
        ).fetchall()
        assert {r["dark_id"] for r in rows} == {lib}

    async def test_matching_flats_telescope_configuration(self, graph):
        conn, ids = graph
        light = await _insert_sub(
            conn,
            frame_type="light",
            filter_id=ids["ha"],
            camera_id=ids["camera"],
            telescope_configuration_id=ids["cfg_native"],
        )
        # Same everything but reducer config → no match (optical train differs).
        await _insert_sub(
            conn,
            frame_type="flat",
            filter_id=ids["ha"],
            camera_id=ids["camera"],
            telescope_configuration_id=ids["cfg_reducer"],
        )
        # Native config → match.
        good = await _insert_sub(
            conn,
            frame_type="flat",
            filter_id=ids["ha"],
            camera_id=ids["camera"],
            telescope_configuration_id=ids["cfg_native"],
        )
        rows = await (
            await conn.execute("SELECT flat_id FROM matching_flats WHERE light_id = ?", (light,))
        ).fetchall()
        assert {r["flat_id"] for r in rows} == {good}

    async def test_matching_flats_filter(self, graph):
        conn, ids = graph
        light = await _insert_sub(
            conn,
            frame_type="light",
            filter_id=ids["ha"],
            camera_id=ids["camera"],
            telescope_configuration_id=ids["cfg_native"],
        )
        # Different filter → no match.
        await _insert_sub(
            conn,
            frame_type="flat",
            filter_id=ids["duo"],
            camera_id=ids["camera"],
            telescope_configuration_id=ids["cfg_native"],
        )
        count = await _scalar(
            conn, "SELECT COUNT(*) FROM matching_flats WHERE light_id = ?", (light,)
        )
        assert count == 0

    async def test_matching_bias(self, graph):
        conn, ids = graph
        light = await _insert_sub(
            conn, frame_type="light", filter_id=ids["ha"], camera_id=ids["camera"], binning_x=1
        )
        good = await _insert_sub(conn, frame_type="bias", camera_id=ids["camera"], binning_x=1)
        # Different binning → no match.
        await _insert_sub(conn, frame_type="bias", camera_id=ids["camera"], binning_x=2)
        # Different camera → no match.
        await _insert_sub(conn, frame_type="bias", camera_id=ids["camera_b"], binning_x=1)
        rows = await (
            await conn.execute("SELECT bias_id FROM matching_bias WHERE light_id = ?", (light,))
        ).fetchall()
        assert {r["bias_id"] for r in rows} == {good}

    async def test_calibration_coverage(self, graph):
        conn, ids = graph
        light = await _insert_sub(
            conn,
            frame_type="light",
            filter_id=ids["ha"],
            camera_id=ids["camera"],
            telescope_configuration_id=ids["cfg_native"],
        )
        await _insert_sub(conn, frame_type="dark", camera_id=ids["camera"])
        await _insert_sub(
            conn,
            frame_type="flat",
            filter_id=ids["ha"],
            camera_id=ids["camera"],
            telescope_configuration_id=ids["cfg_native"],
        )
        # No bias inserted → has_bias should be 0.
        cur = await conn.execute(
            "SELECT has_dark, has_flat, has_bias FROM calibration_coverage WHERE light_id = ?",
            (light,),
        )
        row = await cur.fetchone()
        assert (row["has_dark"], row["has_flat"], row["has_bias"]) == (1, 1, 0)


# ── Integration + goal-progress + session_summary ────────────────────────────


class TestIntegrationViews:
    async def test_single_band_integration(self, graph):
        conn, ids = graph
        for _ in range(3):
            await _insert_sub(
                conn,
                frame_type="light",
                filter_id=ids["ha"],
                camera_id=ids["camera"],
                exposure_seconds=300.0,
                project_target_id=ids["target"],
            )
        cur = await conn.execute(
            "SELECT line_name, total_seconds, total_minutes, sub_count "
            "FROM integration_time_per_project_filter WHERE project_id = ?",
            (ids["project"],),
        )
        rows = {r["line_name"]: r for r in await cur.fetchall()}
        assert set(rows) == {"Ha"}
        assert rows["Ha"]["total_seconds"] == 900.0
        assert rows["Ha"]["total_minutes"] == 15.0
        assert rows["Ha"]["sub_count"] == 3

    async def test_duoband_double_counts(self, graph):
        conn, ids = graph
        for _ in range(2):
            await _insert_sub(
                conn,
                frame_type="light",
                filter_id=ids["duo"],
                camera_id=ids["camera"],
                exposure_seconds=600.0,
                project_target_id=ids["target"],
            )
        cur = await conn.execute(
            "SELECT line_name, total_minutes, sub_count "
            "FROM integration_time_per_project_filter WHERE project_id = ?",
            (ids["project"],),
        )
        rows = {r["line_name"]: r for r in await cur.fetchall()}
        # The duoband sub contributes to BOTH line budgets.
        assert set(rows) == {"Ha", "Oiii"}
        assert rows["Ha"]["total_minutes"] == 20.0
        assert rows["Oiii"]["total_minutes"] == 20.0
        assert rows["Ha"]["sub_count"] == 2
        assert rows["Oiii"]["sub_count"] == 2

    async def test_rejected_lights_excluded_from_integration(self, graph):
        conn, ids = graph
        await _insert_sub(
            conn,
            frame_type="light",
            filter_id=ids["ha"],
            camera_id=ids["camera"],
            exposure_seconds=300.0,
            project_target_id=ids["target"],
            accepted=0,
        )
        count = await _scalar(
            conn,
            "SELECT COUNT(*) FROM integration_time_per_project_filter WHERE project_id = ?",
            (ids["project"],),
        )
        assert count == 0

    async def test_goal_progress_null_safe_and_actual(self, graph):
        conn, ids = graph
        # Goal with no matching subs.
        await conn.execute(
            "INSERT INTO project_filter_goal (project_id, line_name, goal_minutes) "
            "VALUES (?, 'Sii', 30)",
            (ids["project"],),
        )
        # Goal with 15 min of actuals.
        await conn.execute(
            "INSERT INTO project_filter_goal (project_id, line_name, goal_minutes) "
            "VALUES (?, 'Ha', 60)",
            (ids["project"],),
        )
        for _ in range(3):
            await _insert_sub(
                conn,
                frame_type="light",
                filter_id=ids["ha"],
                camera_id=ids["camera"],
                exposure_seconds=300.0,
                project_target_id=ids["target"],
            )
        cur = await conn.execute(
            "SELECT line_name, goal_minutes, actual_minutes, completion_ratio "
            "FROM project_filter_goal_progress WHERE project_id = ?",
            (ids["project"],),
        )
        rows = {r["line_name"]: r for r in await cur.fetchall()}
        assert rows["Sii"]["actual_minutes"] == 0
        assert rows["Sii"]["completion_ratio"] == 0
        assert rows["Ha"]["actual_minutes"] == 15.0
        assert rows["Ha"]["completion_ratio"] == 0.25

    async def test_session_summary(self, graph):
        conn, ids = graph
        for _ in range(3):
            await _insert_sub(
                conn,
                frame_type="light",
                filter_id=ids["ha"],
                camera_id=ids["camera"],
                exposure_seconds=300.0,
                session_id=ids["session"],
                project_target_id=ids["target"],
            )
        await _insert_sub(
            conn,
            frame_type="light",
            filter_id=ids["ha"],
            camera_id=ids["camera"],
            exposure_seconds=300.0,
            session_id=ids["session"],
            accepted=0,
        )
        await _insert_sub(
            conn, frame_type="dark", camera_id=ids["camera"], session_id=ids["session"]
        )
        cur = await conn.execute(
            "SELECT duration_hours, total_subs, accepted_lights, rejected_lights, "
            "accepted_light_minutes, distinct_filters FROM session_summary WHERE session_id = ?",
            (ids["session"],),
        )
        row = await cur.fetchone()
        assert row["duration_hours"] == pytest.approx(7.0)  # julianday float arithmetic
        assert row["total_subs"] == 5
        assert row["accepted_lights"] == 3
        assert row["rejected_lights"] == 1
        assert row["accepted_light_minutes"] == 15.0
        assert row["distinct_filters"] == 1
