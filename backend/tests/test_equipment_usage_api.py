"""Resolved equipment usage endpoint regressions."""

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.db.session import get_db
from nightcrate.main import app
from nightcrate.services.rig_setups import equipment_usage, project_setups, save_earlier_setup
from tests.frame_library import build_usage_library
from tests.rig_setup_fixtures import make_equipment, make_project, make_rig


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


async def test_camera_usage_counts_setups_and_changes(client):
    async with get_db() as conn:
        equipment = await make_equipment(conn)
        rig_id = await make_rig(conn, equipment, "Usage rig")
        project_id = await make_project(conn)
        await conn.execute(
            "INSERT INTO project_rig (project_id, rig_id) VALUES (?, ?)",
            (project_id, rig_id),
        )
        setup_id = await save_earlier_setup(conn, rig_id, until_at="2026-11-01")
        await conn.execute(
            "UPDATE rig SET camera_id = ? WHERE id = ?", (equipment.camera_b, rig_id)
        )
        await conn.execute(
            "INSERT INTO project_session "
            "(project_id, source, session_date, rig_id, rig_setup_id, filter_id, "
            "exposure_seconds, num_subs) "
            "VALUES (?, 'manual', '2026-10-31', ?, ?, ?, 60, 1)",
            (project_id, rig_id, setup_id, equipment.filter_l),
        )
        await conn.commit()

    usage = await client.get(f"/api/equipment/camera/{equipment.camera_a}/usage")
    assert usage.status_code == 200
    assert usage.json() == {"rig_count": 1, "project_count": 1}


async def test_filter_usage_counts_manual_batches(client):
    async with get_db() as conn:
        equipment = await make_equipment(conn)
        project_id = await make_project(conn)
        await conn.execute(
            "INSERT INTO project_session "
            "(project_id, source, session_date, filter_id, exposure_seconds, num_subs) "
            "VALUES (?, 'manual', '2026-11-01', ?, 60, 1)",
            (project_id, equipment.filter_ha),
        )
        await conn.commit()
    usage = await client.get(f"/api/equipment/filter/{equipment.filter_ha}/usage")
    assert usage.json() == {"rig_count": 0, "project_count": 1}


async def test_unused_item_is_zero(client):
    async with get_db() as conn:
        equipment = await make_equipment(conn)
        cursor = await conn.execute(
            "INSERT INTO mount (manufacturer_id, model_name) VALUES (?, 'Unused mount')",
            (equipment.manufacturer,),
        )
        mount_id = cursor.lastrowid
        await conn.commit()
    unused = await client.get(f"/api/equipment/mount/{mount_id}/usage")
    assert unused.status_code == 200
    assert unused.json() == {"rig_count": 0, "project_count": 0}


async def test_unknown_kind_404(client):
    unknown = await client.get("/api/equipment/software/1/usage")
    assert unknown.status_code == 404


async def test_sensor_usage_through_camera(client):
    async with get_db() as conn:
        equipment = await make_equipment(conn)
        rig_id = await make_rig(conn, equipment, "Sensor rig")
        project_id = await make_project(conn)
        await conn.execute(
            "INSERT INTO project_rig (project_id, rig_id) VALUES (?, ?)",
            (project_id, rig_id),
        )
        row = await (
            await conn.execute("SELECT sensor_id FROM camera WHERE id = ?", (equipment.camera_a,))
        ).fetchone()
        sensor_id = row["sensor_id"]
        await conn.commit()
    usage = await client.get(f"/api/equipment/sensor/{sensor_id}/usage")
    assert usage.json() == {"rig_count": 1, "project_count": 1}


async def test_usage_matches_project_setups():
    library = await build_usage_library()
    expected = {"camera": 0, "filter": 0, "mount": 0}
    async with get_db() as conn:
        for project_id in library.project_ids:
            setups = await project_setups(conn, project_id)
            parts = [setup.parts for rig in setups for setup in rig.setups]
            expected["camera"] += any(
                library.camera_id in {item.camera_id, item.guide_camera_id} for item in parts
            )
            expected["filter"] += any(
                item.single_filter_id == library.filter_id
                or any(filter_id == library.filter_id for _slot, filter_id in item.filter_slots)
                for item in parts
            )
            expected["mount"] += any(item.mount_id == library.mount_id for item in parts)

        for kind, item_id in (
            ("camera", library.camera_id),
            ("filter", library.filter_id),
            ("mount", library.mount_id),
        ):
            _rig_count, project_count = await equipment_usage(conn, kind, item_id)
            assert project_count == expected[kind]
