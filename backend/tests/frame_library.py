"""Repeatable frame-list timing harness for the v0.47.0 setup-history join."""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.db.session import get_db
from nightcrate.main import app
from nightcrate.services.rig_setups import equipment_usage


async def _insert(conn, sql: str, values: tuple = ()) -> int:
    cursor = await conn.execute(sql, values)
    assert cursor.lastrowid is not None
    return cursor.lastrowid


@dataclass(frozen=True)
class UsageLibrary:
    project_ids: tuple[int, ...]
    camera_id: int
    filter_id: int
    mount_id: int


async def build_usage_library(project_count: int = 500) -> UsageLibrary:
    """Build the large two-rig library used by equipment-usage regressions."""
    async with get_db() as conn:
        maker = await _insert(conn, "INSERT INTO manufacturer (name) VALUES ('Usage timing maker')")
        filter_type = await _insert(
            conn,
            "INSERT INTO filter_type (name, display_name) VALUES ('usage_timing', 'Usage timing')",
        )
        telescope = await _insert(
            conn,
            "INSERT INTO telescope (manufacturer_id, model_name, aperture_mm) "
            "VALUES (?, 'Usage timing scope', 100)",
            (maker,),
        )
        config = await _insert(
            conn,
            "INSERT INTO telescope_configuration "
            "(telescope_id, config_name, effective_focal_length_mm, "
            "effective_focal_ratio, is_native) VALUES (?, '500 mm', 500, 5, 1)",
            (telescope,),
        )
        cameras = []
        for index in range(3):
            sensor = await _insert(
                conn,
                "INSERT INTO sensor "
                "(manufacturer_id, model_name, sensor_type, pixel_size_um, "
                "resolution_x, resolution_y, adc_bit_depth) "
                "VALUES (?, ?, 'mono', 3.76, 4000, 3000, 16)",
                (maker, f"Usage timing sensor {index}"),
            )
            cameras.append(
                await _insert(
                    conn,
                    "INSERT INTO camera (manufacturer_id, sensor_id, model_name) VALUES (?, ?, ?)",
                    (maker, sensor, f"Usage timing camera {index}"),
                )
            )
        wheel = await _insert(
            conn,
            "INSERT INTO filter_wheel (manufacturer_id, model_name, num_positions) "
            "VALUES (?, 'Usage timing wheel', 5)",
            (maker,),
        )
        filter_id = await _insert(
            conn,
            "INSERT INTO filter (manufacturer_id, filter_type_id, model_name) "
            "VALUES (?, ?, 'Usage timing L')",
            (maker, filter_type),
        )
        mount_id = await _insert(
            conn,
            "INSERT INTO mount (manufacturer_id, model_name) VALUES (?, 'Usage timing mount')",
            (maker,),
        )
        rig_ids = []
        for index, camera_id in enumerate((cameras[1], cameras[0]), start=1):
            rig_ids.append(
                await _insert(
                    conn,
                    "INSERT INTO rig "
                    "(name, telescope_configuration_id, camera_id, filter_wheel_id, "
                    "mount_id, is_mine) VALUES (?, ?, ?, ?, ?, 1)",
                    (f"Usage timing rig {index}", config, camera_id, wheel, mount_id),
                )
            )
        await conn.executemany(
            "INSERT INTO rig_filter_slot (rig_id, slot_number, filter_id) VALUES (?, 1, ?)",
            [(rig_id, filter_id) for rig_id in rig_ids],
        )
        earlier_setup = await _insert(
            conn,
            "INSERT INTO rig_setup "
            "(rig_id, until_at, telescope_configuration_id, camera_id, filter_wheel_id, "
            "mount_id) VALUES (?, '2026-10-01T00:00:00+00:00', ?, ?, ?, ?)",
            (rig_ids[0], config, cameras[0], wheel, mount_id),
        )
        await conn.execute(
            "INSERT INTO rig_setup_filter_slot (rig_setup_id, slot_number, filter_id) "
            "VALUES (?, 1, ?)",
            (earlier_setup, filter_id),
        )

        project_ids = []
        for index in range(project_count):
            project_ids.append(
                await _insert(
                    conn,
                    "INSERT INTO project (name) VALUES (?)",
                    (f"Usage timing project {index:04d}",),
                )
            )
        await conn.executemany(
            "INSERT INTO project_rig (project_id, rig_id) VALUES (?, ?)",
            [(project_id, rig_id) for project_id in project_ids for rig_id in rig_ids],
        )

        batches = []
        frames = []
        for index, project_id in enumerate(project_ids):
            available_rigs = rig_ids[:1] if index % 11 == 0 else rig_ids
            for batch_index in range(6):
                rig_id = available_rigs[batch_index % len(available_rigs)]
                setup_id = earlier_setup if rig_id == rig_ids[0] and batch_index == 0 else None
                batches.append(
                    (
                        project_id,
                        rig_id,
                        filter_id,
                        f"2026-10-{batch_index + 1:02d}",
                        setup_id,
                    )
                )
            for frame_index, rig_id in enumerate(available_rigs):
                frames.append(
                    (
                        project_id,
                        f"usage-timing-{index:04d}-{frame_index}",
                        rig_id,
                        f"2026-10-{frame_index + 1:02d}T03:00:00+00:00",
                    )
                )
        await conn.executemany(
            "INSERT INTO project_session "
            "(project_id, rig_id, filter_id, exposure_seconds, num_subs, session_date, "
            "source, rig_setup_id) VALUES (?, ?, ?, 60, 1, ?, 'manual', ?)",
            batches,
        )
        await conn.executemany(
            "INSERT INTO sub_frame "
            "(project_id, content_hash, rig_id, frame_type, exposure_seconds, binning_x, "
            "binning_y, date_obs_utc) VALUES (?, ?, ?, 'light', 60, 1, 1, ?)",
            frames,
        )
        cursor = await conn.execute(
            "SELECT id, project_id, rig_id FROM sub_frame WHERE content_hash LIKE 'usage-timing-%'"
        )
        await conn.executemany(
            "INSERT INTO sub_frame_rig_setup (sub_frame_id, rig_id, rig_setup_id) VALUES (?, ?, ?)",
            [
                (row["id"], row["rig_id"], earlier_setup)
                for row in await cursor.fetchall()
                if row["rig_id"] == rig_ids[0] and row["project_id"] % 3 == 0
            ],
        )
        await conn.executemany(
            "INSERT INTO project_rig_change (project_id, rig_id, camera_id) VALUES (?, ?, ?)",
            [
                (project_id, rig_ids[1], cameras[2])
                for index, project_id in enumerate(project_ids)
                if index % 10 == 0
            ],
        )
        await conn.commit()
    return UsageLibrary(tuple(project_ids), cameras[2], filter_id, mount_id)


async def _build_library() -> tuple[int, int]:
    async with get_db() as conn:
        maker = await _insert(conn, "INSERT INTO manufacturer (name) VALUES ('Timing maker')")
        telescope = await _insert(
            conn,
            "INSERT INTO telescope (manufacturer_id, model_name, aperture_mm) "
            "VALUES (?, 'Timing scope', 100)",
            (maker,),
        )
        config = await _insert(
            conn,
            "INSERT INTO telescope_configuration "
            "(telescope_id, config_name, effective_focal_length_mm, effective_focal_ratio, "
            "is_native) VALUES (?, '550 mm', 550, 5.5, 1)",
            (telescope,),
        )
        cameras = []
        for index, pixel_size in enumerate((2.4, 3.76, 2.9), start=1):
            sensor = await _insert(
                conn,
                "INSERT INTO sensor "
                "(manufacturer_id, model_name, sensor_type, pixel_size_um, resolution_x, "
                "resolution_y, adc_bit_depth) VALUES (?, ?, 'mono', ?, 4000, 3000, 16)",
                (maker, f"Timing sensor {index}", pixel_size),
            )
            cameras.append(
                await _insert(
                    conn,
                    "INSERT INTO camera (manufacturer_id, sensor_id, model_name) VALUES (?, ?, ?)",
                    (maker, sensor, f"Timing camera {index}"),
                )
            )
        rig = await _insert(
            conn,
            "INSERT INTO rig "
            "(name, telescope_configuration_id, camera_id, is_mine) VALUES ('Timing rig', ?, ?, 1)",
            (config, cameras[1]),
        )
        first_project = await _insert(conn, "INSERT INTO project (name) VALUES ('Timing one')")
        second_project = await _insert(conn, "INSERT INTO project (name) VALUES ('Timing two')")
        await conn.executemany(
            "INSERT INTO project_rig (project_id, rig_id) VALUES (?, ?)",
            ((first_project, rig), (second_project, rig)),
        )
        setup = await _insert(
            conn,
            "INSERT INTO rig_setup "
            "(rig_id, until_at, telescope_configuration_id, camera_id) "
            "VALUES (?, '2026-11-01 00:00:00', ?, ?)",
            (rig, config, cameras[0]),
        )
        await conn.execute(
            "INSERT INTO project_rig_change (project_id, rig_id, camera_id) VALUES (?, ?, ?)",
            (second_project, rig, cameras[2]),
        )
        frames = []
        for index in range(2400):
            project_id = first_project if index < 1600 else second_project
            frames.append(
                (
                    project_id,
                    f"timing-{index:04d}",
                    rig,
                    f"2026-11-{index % 20 + 1:02d}T03:00:00+00:00",
                    float(index % 10 + 1),
                )
            )
        await conn.executemany(
            "INSERT INTO sub_frame "
            "(project_id, content_hash, rig_id, frame_type, exposure_seconds, binning_x, "
            "binning_y, date_obs_utc, hfr) VALUES (?, ?, ?, 'light', 60, 1, 1, ?, ?)",
            frames,
        )
        cursor = await conn.execute(
            "SELECT id, project_id FROM sub_frame WHERE content_hash LIKE 'timing-%' ORDER BY id"
        )
        frame_rows = await cursor.fetchall()
        await conn.executemany(
            "INSERT INTO file_location (project_id, path, category, sub_frame_id) "
            "VALUES (?, ?, 'sub_frame', ?)",
            [
                (row["project_id"], f"/timing/frame-{index:04d}.fits", row["id"])
                for index, row in enumerate(frame_rows)
            ],
        )
        await conn.executemany(
            "INSERT INTO sub_frame_rig_setup (sub_frame_id, rig_id, rig_setup_id) VALUES (?, ?, ?)",
            [(row["id"], rig, setup) for row in frame_rows[:800]],
        )
        await conn.commit()
        return first_project, second_project


async def _median(client: AsyncClient, project_id: int, sort: str | None) -> float:
    durations = []
    params = {"limit": 100000}
    if sort is not None:
        params["sort"] = sort
    for _ in range(20):
        started = time.perf_counter()
        response = await client.get(f"/api/projects/{project_id}/catalog/frames", params=params)
        durations.append(time.perf_counter() - started)
        assert response.status_code == 200
        assert response.json()["total"] == 1600
    return statistics.median(durations)


@pytest.mark.asyncio
async def test_frame_list_timing():
    first_project, _second_project = await _build_library()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get(f"/api/projects/{first_project}/catalog/frames", params={"limit": 100000})
        default = await _median(client, first_project, None)
        arcsec = await _median(client, first_project, "hfr_arcsec_desc")
    print(f"FRAME_LIBRARY default_median={default:.6f}s arcsec_median={arcsec:.6f}s")


@pytest.mark.asyncio
async def test_equipment_usage_timing():
    library = await build_usage_library()
    durations = []
    async with get_db() as conn:
        await equipment_usage(conn, "camera", library.camera_id)
        for _ in range(7):
            started = time.perf_counter()
            await equipment_usage(conn, "camera", library.camera_id)
            durations.append(time.perf_counter() - started)
    median = statistics.median(durations)
    print(f"EQUIPMENT_USAGE median={median:.6f}s")
    assert median <= 0.100
