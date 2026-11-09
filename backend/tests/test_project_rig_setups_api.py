"""Project-resolved setup and project-change API regressions."""

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.db.session import get_db
from nightcrate.main import app
from tests.catalog_helpers import _frames
from tests.rig_setup_fixtures import make_equipment, make_frame, make_project, make_rig


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


async def _project_rig():
    async with get_db() as conn:
        equipment = await make_equipment(conn)
        rig_id = await make_rig(conn, equipment, "Project setup rig")
        project_id = await make_project(conn)
        await conn.execute(
            "INSERT INTO project_rig (project_id, rig_id) VALUES (?, ?)",
            (project_id, rig_id),
        )
        await make_frame(conn, project_id, "old-frame", rig_id=rig_id)
        await conn.commit()
    return equipment, rig_id, project_id


def _change_body(rig: dict, **updates) -> dict:
    body = {
        key: rig[key]
        for key in (
            "telescope_configuration_id",
            "camera_id",
            "filter_wheel_id",
            "single_filter_id",
            "mount_id",
            "focuser_id",
            "oag_id",
            "guide_scope_id",
            "guide_camera_id",
            "computer_id",
        )
    }
    body["filter_slots"] = [
        {"slot_number": item["slot_number"], "filter_id": item["filter_id"]}
        for item in rig["filter_slots"]
    ]
    body["software_ids"] = [item["id"] for item in rig["software"]]
    body.update(updates)
    return body


async def test_setups_for_project_across_a_change(client):
    equipment, rig_id, project_id = await _project_rig()
    split = await client.put(
        f"/api/rigs/{rig_id}",
        json={"camera_id": equipment.camera_b, "apply_mode": "from_now_on"},
    )
    assert split.status_code == 200, split.text
    async with get_db() as conn:
        await make_frame(conn, project_id, "current-frame", rig_id=rig_id)
        await conn.commit()

    response = await client.get(f"/api/projects/{project_id}/rig-setups")
    assert response.status_code == 200, response.text
    rig = response.json()[0]
    assert rig["declared"] is True
    assert [item["rig_setup_id"] is None for item in rig["setups"]] == [True, False]
    assert [item["night_count"] for item in rig["setups"]] == [1, 1]
    assert rig["setups"][0]["parts"]["image_scale_arcsec_per_pixel"] == 1.41
    assert rig["setups"][0]["parts"]["field_of_view_deg"] == [2.46, 1.65]
    assert rig["setups"][1]["parts"]["image_scale_arcsec_per_pixel"] == 0.9
    assert rig["setups"][1]["parts"]["field_of_view_deg"] == [1.39, 0.92]


async def test_setup_options_list_all_rig_setups(client):
    equipment, rig_id, project_id = await _project_rig()
    split = await client.put(
        f"/api/rigs/{rig_id}",
        json={"camera_id": equipment.camera_b, "apply_mode": "from_now_on"},
    )
    assert split.status_code == 200, split.text
    async with get_db() as conn:
        row = await (
            await conn.execute("SELECT id FROM rig_setup WHERE rig_id = ?", (rig_id,))
        ).fetchone()
        assert row is not None
        earlier_setup_id = row["id"]

    response = await client.get(f"/api/projects/{project_id}/rig-setups")
    assert response.status_code == 200, response.text
    rig = response.json()[0]
    assert [item["rig_setup_id"] for item in rig["setups"]] == [earlier_setup_id]
    assert [item["rig_setup_id"] for item in rig["setup_options"]] == [
        None,
        earlier_setup_id,
    ]
    assert [item["camera_name"] for item in rig["setup_options"]] == [
        "Camera B",
        "Camera A",
    ]
    assert [item["image_scale_arcsec_per_pixel"] for item in rig["setup_options"]] == [
        1.41,
        0.9,
    ]


async def test_change_equal_to_rig_is_dropped(client):
    equipment, rig_id, project_id = await _project_rig()
    rig = (await client.get(f"/api/rigs/{rig_id}")).json()
    changed = await client.put(
        f"/api/projects/{project_id}/rigs/{rig_id}/change",
        json=_change_body(
            rig,
            oag_id=None,
            guide_scope_id=equipment.guide_scope,
        ),
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["changed_groups"] == ["guider"]
    assert changed.json()["setups"][0]["parts"]["guide_scope_id"] == equipment.guide_scope

    dropped = await client.put(
        f"/api/projects/{project_id}/rigs/{rig_id}/change",
        json=_change_body(rig),
    )
    assert dropped.status_code == 200, dropped.text
    assert dropped.json()["changed_groups"] == []
    async with get_db() as conn:
        row = await (
            await conn.execute(
                "SELECT 1 FROM project_rig_change WHERE project_id = ? AND rig_id = ?",
                (project_id, rig_id),
            )
        ).fetchone()
        assert row is None


async def test_project_change_rejects_missing_part(client):
    _equipment, rig_id, project_id = await _project_rig()
    rig = (await client.get(f"/api/rigs/{rig_id}")).json()

    response = await client.put(
        f"/api/projects/{project_id}/rigs/{rig_id}/change",
        json=_change_body(rig, camera_id=999_999),
    )

    assert response.status_code == 422
    assert "camera_id" in response.json()["detail"]
    async with get_db() as conn:
        row = await (
            await conn.execute(
                "SELECT 1 FROM project_rig_change WHERE project_id = ? AND rig_id = ?",
                (project_id, rig_id),
            )
        ).fetchone()
        assert row is None


async def test_project_change_only_this_project(client):
    equipment, rig_id, project_id = await _project_rig()
    async with get_db() as conn:
        project_2 = await make_project(conn, "Unchanged project")
        await conn.execute(
            "INSERT INTO project_rig (project_id, rig_id) VALUES (?, ?)",
            (project_2, rig_id),
        )
        await conn.commit()
    rig = (await client.get(f"/api/rigs/{rig_id}")).json()
    await client.put(
        f"/api/projects/{project_id}/rigs/{rig_id}/change",
        json=_change_body(rig, oag_id=None, guide_scope_id=equipment.guide_scope),
    )
    first = (await client.get(f"/api/projects/{project_id}/rig-setups")).json()[0]
    second = (await client.get(f"/api/projects/{project_2}/rig-setups")).json()[0]
    assert first["changed_groups"] == ["guider"]
    assert second["changed_groups"] == []
    assert second["setups"][0]["parts"]["oag_id"] == equipment.oag


async def test_guide_camera_follows_rig_after_guider_swap(client):
    equipment, rig_id, project_id = await _project_rig()
    rig = (await client.get(f"/api/rigs/{rig_id}")).json()
    changed = await client.put(
        f"/api/projects/{project_id}/rigs/{rig_id}/change",
        json=_change_body(rig, oag_id=None, guide_scope_id=equipment.guide_scope),
    )
    assert changed.status_code == 200
    corrected = await client.put(
        f"/api/rigs/{rig_id}",
        json={"guide_camera_id": equipment.camera_b, "apply_mode": "existing"},
    )
    assert corrected.status_code == 200
    setup = (await client.get(f"/api/projects/{project_id}/rig-setups")).json()[0]
    assert setup["changed_groups"] == ["guider"]
    assert setup["setups"][0]["parts"]["guide_scope_id"] == equipment.guide_scope
    assert setup["setups"][0]["parts"]["guide_camera_id"] == equipment.camera_b


async def test_change_survives_rig_edits(client):
    equipment, rig_id, project_id = await _project_rig()
    rig = (await client.get(f"/api/rigs/{rig_id}")).json()
    await client.put(
        f"/api/projects/{project_id}/rigs/{rig_id}/change",
        json=_change_body(rig, oag_id=None, guide_scope_id=equipment.guide_scope),
    )
    changed_rig = await client.put(
        f"/api/rigs/{rig_id}",
        json={"camera_id": equipment.camera_b, "apply_mode": "existing"},
    )
    assert changed_rig.status_code == 200
    setup = (await client.get(f"/api/projects/{project_id}/rig-setups")).json()[0]
    assert setup["setups"][0]["parts"]["camera_id"] == equipment.camera_b
    assert setup["setups"][0]["parts"]["guide_scope_id"] == equipment.guide_scope


async def test_change_camera_drives_pixel_scale(client):
    equipment, rig_id, project_id = await _project_rig()
    async with get_db() as conn:
        project_2 = await make_project(conn, "Project B")
        await conn.execute(
            "INSERT INTO project_rig (project_id, rig_id) VALUES (?, ?)",
            (project_2, rig_id),
        )
        await make_frame(conn, project_2, "p2-frame", rig_id=rig_id)
        await conn.commit()
    rig = (await client.get(f"/api/rigs/{rig_id}")).json()
    changed = await client.put(
        f"/api/projects/{project_id}/rigs/{rig_id}/change",
        json=_change_body(rig, camera_id=equipment.camera_b),
    )
    assert changed.status_code == 200
    assert round((await _frames(client, project_id))[0]["pixel_scale_arcsec"], 2) == 1.41
    assert round((await _frames(client, project_2))[0]["pixel_scale_arcsec"], 2) == 0.9


async def test_undo_project_change_restores_rig(client):
    equipment, rig_id, project_id = await _project_rig()
    rig = (await client.get(f"/api/rigs/{rig_id}")).json()
    changed = await client.put(
        f"/api/projects/{project_id}/rigs/{rig_id}/change",
        json=_change_body(rig, camera_id=equipment.camera_b),
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["setups"][0]["parts"]["camera_id"] == equipment.camera_b
    assert round((await _frames(client, project_id))[0]["pixel_scale_arcsec"], 2) == 1.41

    deleted = await client.delete(f"/api/projects/{project_id}/rigs/{rig_id}/change")

    assert deleted.status_code == 204, deleted.text
    restored = (await client.get(f"/api/projects/{project_id}/rig-setups")).json()[0]
    assert restored["changed_groups"] == []
    assert restored["setups"][0]["parts"]["camera_id"] == equipment.camera_a
    assert round((await _frames(client, project_id))[0]["pixel_scale_arcsec"], 2) == 0.9


async def test_undo_project_change_unknown_project(client):
    response = await client.delete("/api/projects/999999/rigs/999999/change")
    assert response.status_code == 404


async def test_project_change_rejects_rig_not_used_by_project(client):
    equipment, _rig_id, project_id = await _project_rig()
    async with get_db() as conn:
        other_rig_id = await make_rig(conn, equipment, "Other rig")
        await conn.commit()
    other_rig = (await client.get(f"/api/rigs/{other_rig_id}")).json()

    response = await client.put(
        f"/api/projects/{project_id}/rigs/{other_rig_id}/change",
        json=_change_body(other_rig),
    )

    assert response.status_code == 404


async def test_project_delete_cascades_change(client):
    equipment, rig_id, project_id = await _project_rig()
    rig = (await client.get(f"/api/rigs/{rig_id}")).json()
    await client.put(
        f"/api/projects/{project_id}/rigs/{rig_id}/change",
        json=_change_body(rig, camera_id=equipment.camera_b),
    )
    deleted = await client.delete(f"/api/projects/{project_id}/permanent")
    assert deleted.status_code == 204
    async with get_db() as conn:
        count = await (
            await conn.execute(
                "SELECT COUNT(*) AS n FROM project_rig_change WHERE project_id = ?",
                (project_id,),
            )
        ).fetchone()
        assert count["n"] == 0


async def test_setups_include_undeclared_rigs_and_retired_declared_rig(client):
    async with get_db() as conn:
        equipment = await make_equipment(conn)
        declared = await make_rig(conn, equipment, "Retired")
        frame_rig = await make_rig(conn, equipment, "Frame only")
        batch_rig = await make_rig(conn, equipment, "Batch only")
        project_id = await make_project(conn)
        await conn.execute(
            "INSERT INTO project_rig (project_id, rig_id) VALUES (?, ?)",
            (project_id, declared),
        )
        await conn.execute("UPDATE rig SET active = 0 WHERE id = ?", (declared,))
        await make_frame(conn, project_id, "undeclared-frame", rig_id=frame_rig)
        await conn.execute(
            "INSERT INTO project_session "
            "(project_id, source, session_date, rig_id, filter_id, exposure_seconds, num_subs) "
            "VALUES (?, 'manual', '2026-11-02', ?, ?, 60, 1)",
            (project_id, batch_rig, equipment.filter_l),
        )
        await conn.commit()

    setups = (await client.get(f"/api/projects/{project_id}/rig-setups")).json()
    assert {item["rig_id"]: item["declared"] for item in setups} == {
        declared: True,
        frame_rig: False,
        batch_rig: False,
    }
    project = (await client.get(f"/api/projects/{project_id}")).json()
    assert project["rigs"] == [{"id": declared, "name": "Retired", "active": False}]


async def test_project_rigs_include_retired(client):
    _equipment, rig_id, project_id = await _project_rig()
    async with get_db() as conn:
        await conn.execute("UPDATE rig SET active = 0 WHERE id = ?", (rig_id,))
        await conn.commit()
    project = (await client.get(f"/api/projects/{project_id}")).json()
    assert project["rigs"][0]["active"] is False
