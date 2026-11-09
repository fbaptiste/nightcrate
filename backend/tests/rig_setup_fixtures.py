"""Small database builders shared by the rig-setup tests."""

from __future__ import annotations

from dataclasses import dataclass

import aiosqlite


@dataclass(frozen=True)
class EquipmentIds:
    manufacturer: int
    configuration: int
    other_configuration: int
    camera_a: int
    camera_b: int
    camera_c: int
    camera_d: int
    wheel: int
    filter_l: int
    filter_ha: int
    filter_r: int
    software: int
    oag: int
    guide_scope: int


async def _insert(conn: aiosqlite.Connection, sql: str, values: tuple = ()) -> int:
    cursor = await conn.execute(sql, values)
    assert cursor.lastrowid is not None
    return cursor.lastrowid


async def make_equipment(conn: aiosqlite.Connection) -> EquipmentIds:
    manufacturer = await _insert(conn, "INSERT INTO manufacturer (name) VALUES ('Test maker')")
    filter_type = await _insert(
        conn,
        "INSERT INTO filter_type (name, display_name) VALUES ('test_filter', 'Test filter')",
    )
    telescope = await _insert(
        conn,
        "INSERT INTO telescope (manufacturer_id, model_name, aperture_mm) VALUES (?, 'Scope', 100)",
        (manufacturer,),
    )
    configuration = await _insert(
        conn,
        """
        INSERT INTO telescope_configuration
            (telescope_id, config_name, effective_focal_length_mm, effective_focal_ratio,
             is_native)
        VALUES (?, '550 mm', 550, 5.5, 1)
        """,
        (telescope,),
    )
    other_configuration = await _insert(
        conn,
        """
        INSERT INTO telescope_configuration
            (telescope_id, config_name, effective_focal_length_mm, effective_focal_ratio)
        VALUES (?, '700 mm', 700, 7.0)
        """,
        (telescope,),
    )
    sensor_a = await _insert(
        conn,
        """
        INSERT INTO sensor
            (manufacturer_id, model_name, sensor_type, pixel_size_um,
             resolution_x, resolution_y, adc_bit_depth)
        VALUES (?, 'Sensor A', 'mono', 2.40, 5544, 3694, 12)
        """,
        (manufacturer,),
    )
    sensor_b = await _insert(
        conn,
        """
        INSERT INTO sensor
            (manufacturer_id, model_name, sensor_type, pixel_size_um,
             resolution_x, resolution_y, adc_bit_depth)
        VALUES (?, 'Sensor B', 'mono', 3.76, 6280, 4210, 16)
        """,
        (manufacturer,),
    )
    sensor_c = await _insert(
        conn,
        """
        INSERT INTO sensor
            (manufacturer_id, model_name, sensor_type, pixel_size_um,
             resolution_x, resolution_y, adc_bit_depth)
        VALUES (?, 'Sensor C', 'mono', 2.90, 5000, 3500, 16)
        """,
        (manufacturer,),
    )
    cameras = []
    for name, sensor_id in (
        ("Camera A", sensor_a),
        ("Camera B", sensor_b),
        ("Camera C", sensor_c),
        ("Camera D", sensor_b),
    ):
        cameras.append(
            await _insert(
                conn,
                "INSERT INTO camera (manufacturer_id, sensor_id, model_name) VALUES (?, ?, ?)",
                (manufacturer, sensor_id, name),
            )
        )
    wheel = await _insert(
        conn,
        """
        INSERT INTO filter_wheel (manufacturer_id, model_name, num_positions)
        VALUES (?, 'Wheel', 5)
        """,
        (manufacturer,),
    )
    filters = []
    for name in ("L", "Ha", "R"):
        filters.append(
            await _insert(
                conn,
                "INSERT INTO filter (manufacturer_id, filter_type_id, model_name) VALUES (?, ?, ?)",
                (manufacturer, filter_type, name),
            )
        )
    software = await _insert(
        conn,
        "INSERT INTO software (manufacturer_id, name, category) "
        "VALUES (?, 'Capture app', 'capture')",
        (manufacturer,),
    )
    oag = await _insert(
        conn,
        "INSERT INTO oag (manufacturer_id, model_name) VALUES (?, 'OAG')",
        (manufacturer,),
    )
    guide_scope = await _insert(
        conn,
        "INSERT INTO guide_scope (manufacturer_id, model_name) VALUES (?, 'Guide scope')",
        (manufacturer,),
    )
    return EquipmentIds(
        manufacturer=manufacturer,
        configuration=configuration,
        other_configuration=other_configuration,
        camera_a=cameras[0],
        camera_b=cameras[1],
        camera_c=cameras[2],
        camera_d=cameras[3],
        wheel=wheel,
        filter_l=filters[0],
        filter_ha=filters[1],
        filter_r=filters[2],
        software=software,
        oag=oag,
        guide_scope=guide_scope,
    )


async def make_rig(
    conn: aiosqlite.Connection,
    equipment: EquipmentIds,
    name: str,
    *,
    camera_id: int | None = None,
) -> int:
    return await _insert(
        conn,
        """
        INSERT INTO rig
            (name, telescope_configuration_id, camera_id, filter_wheel_id, oag_id,
             guide_camera_id, is_mine)
        VALUES (?, ?, ?, ?, ?, ?, 1)
        """,
        (
            name,
            equipment.configuration,
            camera_id or equipment.camera_a,
            equipment.wheel,
            equipment.oag,
            equipment.camera_a,
        ),
    )


async def make_project(conn: aiosqlite.Connection, name: str = "Project A") -> int:
    return await _insert(conn, "INSERT INTO project (name) VALUES (?)", (name,))


async def make_frame(
    conn: aiosqlite.Connection,
    project_id: int,
    content_hash: str,
    *,
    rig_id: int | None,
    date_obs_utc: str = "2026-11-01T03:00:00+00:00",
    frame_type: str = "light",
    filter_name_hint: str | None = "L",
) -> int:
    return await _insert(
        conn,
        """
        INSERT INTO sub_frame
            (project_id, content_hash, rig_id, date_obs_utc, frame_type,
             exposure_seconds, gain, binning_x, binning_y, set_temp_c,
             filter_name_hint)
        VALUES (?, ?, ?, ?, ?, 60, 100, 1, 1, -10, ?)
        """,
        (project_id, content_hash, rig_id, date_obs_utc, frame_type, filter_name_hint),
    )
