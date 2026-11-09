"""Rig-history API regressions for v0.47.0."""

from unittest.mock import AsyncMock

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


async def _rig_in_project(*, nights: int = 2):
    async with get_db() as conn:
        equipment = await make_equipment(conn)
        rig_id = await make_rig(conn, equipment, "History Rig")
        project_id = await make_project(conn)
        await conn.execute(
            "INSERT INTO project_rig (project_id, rig_id) VALUES (?, ?)",
            (project_id, rig_id),
        )
        await conn.execute(
            "INSERT INTO rig_filter_slot (rig_id, slot_number, filter_id) VALUES (?, 1, ?)",
            (rig_id, equipment.filter_l),
        )
        await conn.execute(
            "INSERT INTO rig_software (rig_id, software_id) VALUES (?, ?)",
            (rig_id, equipment.software),
        )
        frames = []
        for index in range(nights):
            frames.append(
                await make_frame(
                    conn,
                    project_id,
                    f"history-{index}",
                    rig_id=rig_id,
                    date_obs_utc=f"2026-11-{index + 1:02d}T03:00:00+00:00",
                )
            )
        await conn.commit()
    return equipment, rig_id, project_id, frames


async def _camera_state(rig_id: int):
    async with get_db() as conn:
        cursor = await conn.execute("SELECT camera_id FROM rig WHERE id = ?", (rig_id,))
        camera_id = (await cursor.fetchone())["camera_id"]
        cursor = await conn.execute(
            "SELECT slot_number, filter_id FROM rig_filter_slot WHERE rig_id = ? ORDER BY 1",
            (rig_id,),
        )
        slots = [tuple(row) for row in await cursor.fetchall()]
        cursor = await conn.execute(
            "SELECT software_id FROM rig_software WHERE rig_id = ? ORDER BY 1", (rig_id,)
        )
        software = [row["software_id"] for row in await cursor.fetchall()]
        cursor = await conn.execute(
            "SELECT sub_frame_id, rig_id, rig_setup_id FROM sub_frame_rig_setup ORDER BY 1, 2"
        )
        stamps = [tuple(row) for row in await cursor.fetchall()]
        return camera_id, slots, software, stamps


def _setup_parts_body(parts: dict, **updates) -> dict:
    body = {
        key: parts[key]
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
        for item in parts["filter_slots"]
    ]
    body["software_ids"] = [item["id"] for item in parts["software"]]
    body.update(updates)
    return body


async def test_needs_choice_changes_nothing(client):
    equipment, rig_id, _project_id, _frames_ids = await _rig_in_project()
    before = await _camera_state(rig_id)

    response = await client.put(f"/api/rigs/{rig_id}", json={"camera_id": equipment.camera_b})

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "rig_change_needs_choice",
        "project_count": 1,
        "night_count": 2,
        "changes": [{"group": "camera", "before": "Camera A", "after": "Camera B"}],
    }
    assert await _camera_state(rig_id) == before


async def test_failed_split_rolls_back(client, monkeypatch):
    equipment, rig_id, _project_id, _frames_ids = await _rig_in_project()
    before = await _camera_state(rig_id)
    monkeypatch.setattr(
        "nightcrate.api.rigs._update_rig_row",
        AsyncMock(side_effect=RuntimeError("injected update failure")),
    )

    response = await client.put(
        f"/api/rigs/{rig_id}",
        json={"camera_id": equipment.camera_b, "apply_mode": "from_now_on"},
    )

    assert response.status_code == 500
    assert await _camera_state(rig_id) == before
    async with get_db() as conn:
        cursor = await conn.execute("SELECT COUNT(*) AS n FROM rig_setup")
        assert (await cursor.fetchone())["n"] == 0


async def test_invalid_slots_change_nothing(client):
    equipment, rig_id, _project_id, _frames_ids = await _rig_in_project()
    before = await _camera_state(rig_id)
    response = await client.put(
        f"/api/rigs/{rig_id}",
        json={
            "filter_slots": [{"slot_number": 6, "filter_id": equipment.filter_ha}],
            "apply_mode": "existing",
        },
    )
    assert response.status_code == 422
    assert await _camera_state(rig_id) == before


async def test_correct_setup_rejects_duplicate_slots(client):
    equipment, rig_id, _project_id, _frame_ids = await _rig_in_project(nights=1)
    split = await client.put(
        f"/api/rigs/{rig_id}",
        json={"camera_id": equipment.camera_b, "apply_mode": "from_now_on"},
    )
    assert split.status_code == 200, split.text
    before = (await client.get(f"/api/rigs/{rig_id}/setups")).json()
    setup = before[0]
    body = _setup_parts_body(setup["parts"])
    body["filter_slots"] = [
        {"slot_number": 1, "filter_id": equipment.filter_l},
        {"slot_number": 1, "filter_id": equipment.filter_ha},
    ]

    response = await client.put(f"/api/rig-setups/{setup['id']}", json=body)

    assert response.status_code == 422
    assert (await client.get(f"/api/rigs/{rig_id}/setups")).json() == before


async def test_correct_setup_rejects_missing_camera(client):
    equipment, rig_id, _project_id, _frame_ids = await _rig_in_project(nights=1)
    split = await client.put(
        f"/api/rigs/{rig_id}",
        json={"camera_id": equipment.camera_b, "apply_mode": "from_now_on"},
    )
    assert split.status_code == 200, split.text
    before = (await client.get(f"/api/rigs/{rig_id}/setups")).json()
    setup = before[0]

    response = await client.put(
        f"/api/rig-setups/{setup['id']}",
        json=_setup_parts_body(setup["parts"], camera_id=999_999),
    )

    assert response.status_code == 422
    assert "camera_id" in response.json()["detail"]
    assert (await client.get(f"/api/rigs/{rig_id}/setups")).json() == before


async def test_correct_setup_unknown_id(client):
    _equipment, rig_id, _project_id, _frame_ids = await _rig_in_project(nights=0)
    rig = (await client.get(f"/api/rigs/{rig_id}")).json()

    response = await client.put(
        "/api/rig-setups/999999",
        json=_setup_parts_body(rig),
    )

    assert response.status_code == 404


async def test_name_only_edit_never_asks(client):
    _equipment, rig_id, _project_id, _frames_ids = await _rig_in_project()
    response = await client.put(f"/api/rigs/{rig_id}", json={"name": "Renamed Rig"})
    assert response.status_code == 200
    assert response.json()["name"] == "Renamed Rig"


async def test_unused_rig_never_asks(client):
    async with get_db() as conn:
        equipment = await make_equipment(conn)
        rig_id = await make_rig(conn, equipment, "Unused Rig")
        await conn.commit()
    response = await client.put(f"/api/rigs/{rig_id}", json={"camera_id": equipment.camera_b})
    assert response.status_code == 200
    async with get_db() as conn:
        cursor = await conn.execute("SELECT COUNT(*) AS n FROM rig_setup")
        assert (await cursor.fetchone())["n"] == 0


async def test_from_now_on_existing_and_setup_correction_pixel_scales(client):
    equipment, rig_id, project_id, frame_ids = await _rig_in_project(nights=1)
    split = await client.put(
        f"/api/rigs/{rig_id}",
        json={"camera_id": equipment.camera_b, "apply_mode": "from_now_on"},
    )
    assert split.status_code == 200, split.text
    rows = await _frames(client, project_id)
    assert round(rows[0]["pixel_scale_arcsec"], 2) == 0.90

    async with get_db() as conn:
        new_frame = await make_frame(conn, project_id, "new-current", rig_id=rig_id)
        await conn.commit()
        cursor = await conn.execute("SELECT id FROM rig_setup WHERE rig_id = ?", (rig_id,))
        setup_id = (await cursor.fetchone())["id"]
    rows = {row["id"]: row for row in await _frames(client, project_id)}
    assert round(rows[new_frame]["pixel_scale_arcsec"], 2) == 1.41

    setup = (await client.get(f"/api/rigs/{rig_id}/setups")).json()[0]
    body = {
        key: setup["parts"][key]
        for key in (
            "telescope_configuration_id",
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
    body.update(
        camera_id=equipment.camera_c,
        filter_slots=[
            {"slot_number": item["slot_number"], "filter_id": item["filter_id"]}
            for item in setup["parts"]["filter_slots"]
        ],
        software_ids=[item["id"] for item in setup["parts"]["software"]],
    )
    corrected = await client.put(f"/api/rig-setups/{setup_id}", json=body)
    assert corrected.status_code == 200, corrected.text
    rows = {row["id"]: row for row in await _frames(client, project_id)}
    assert round(rows[frame_ids[0]]["pixel_scale_arcsec"], 2) == 1.09


async def test_existing_changes_every_record(client):
    equipment, rig_id, project_id, _frame_ids = await _rig_in_project(nights=1)
    response = await client.put(
        f"/api/rigs/{rig_id}",
        json={"camera_id": equipment.camera_b, "apply_mode": "existing"},
    )
    assert response.status_code == 200
    assert round((await _frames(client, project_id))[0]["pixel_scale_arcsec"], 2) == 1.41
    assert (await client.get(f"/api/rigs/{rig_id}/setups")).json() == []


async def test_list_setups_newest_first(client):
    equipment, rig_id, project_id, _frame_ids = await _rig_in_project(nights=1)
    first = await client.put(
        f"/api/rigs/{rig_id}",
        json={"camera_id": equipment.camera_b, "apply_mode": "from_now_on"},
    )
    assert first.status_code == 200
    async with get_db() as conn:
        await make_frame(
            conn,
            project_id,
            "second-night",
            rig_id=rig_id,
            date_obs_utc="2026-11-03T03:00:00+00:00",
        )
        await conn.commit()
    second = await client.put(
        f"/api/rigs/{rig_id}",
        json={"camera_id": equipment.camera_c, "apply_mode": "from_now_on"},
    )
    assert second.status_code == 200
    setups = (await client.get(f"/api/rigs/{rig_id}/setups")).json()
    assert [item["parts"]["camera_name"] for item in setups] == ["Camera B", "Camera A"]
    assert [item["night_count"] for item in setups] == [1, 1]


async def test_clone_is_mine(client):
    _equipment, rig_id, _project_id, _frame_ids = await _rig_in_project(nights=0)
    clone = await client.post(f"/api/rigs/{rig_id}/clone")
    assert clone.status_code == 201
    assert clone.json()["is_mine"] is True
    mine = await client.get("/api/rigs", params={"mine": True})
    mine_ids = {item["id"] for item in mine.json()}
    assert clone.json()["id"] in mine_ids


async def test_software_options_grouped_by_category(client):
    options = (await client.get("/api/rigs/equipment-options")).json()["software"]
    categories = [item["category"] for item in options]
    rank = {
        category: index
        for index, category in enumerate(
            ("capture", "guiding", "plate_solving", "planetarium", "utility", "other", "processing")
        )
    }
    category_ranks = [rank[category] for category in categories]
    assert category_ranks == sorted(category_ranks)
