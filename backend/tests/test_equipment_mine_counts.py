"""Tests for GET /api/equipment/mine-counts endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _make_manufacturer(client, name="CountsMfg"):
    resp = await client.post("/api/equipment/manufacturer", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


async def _make_sensor(client, manufacturer_id, model_name="IMX571-counts"):
    resp = await client.post(
        "/api/equipment/sensor",
        json={
            "manufacturer_id": manufacturer_id,
            "model_name": model_name,
            "sensor_type": "mono",
            "pixel_size_um": 3.76,
            "resolution_x": 6248,
            "resolution_y": 4176,
        },
    )
    assert resp.status_code == 201
    return resp.json()


async def _make_camera(client, manufacturer_id, sensor_id, model_name="CountsCam", is_mine=False):
    resp = await client.post(
        "/api/equipment/camera",
        json={
            "manufacturer_id": manufacturer_id,
            "sensor_id": sensor_id,
            "model_name": model_name,
            "is_mine": is_mine,
        },
    )
    assert resp.status_code == 201
    return resp.json()


async def _make_telescope(client, manufacturer_id, model_name="CountsTelescope", is_mine=False):
    resp = await client.post(
        "/api/equipment/telescope",
        json={
            "manufacturer_id": manufacturer_id,
            "model_name": model_name,
            "aperture_mm": 100.0,
            "is_mine": is_mine,
        },
    )
    assert resp.status_code == 201
    return resp.json()


async def _make_filter(
    client, manufacturer_id, filter_type_id, model_name="CountsFilter", is_mine=False
):
    resp = await client.post(
        "/api/equipment/filter",
        json={
            "manufacturer_id": manufacturer_id,
            "filter_type_id": filter_type_id,
            "model_name": model_name,
            "is_mine": is_mine,
        },
    )
    assert resp.status_code == 201
    return resp.json()


async def _get_filter_type_id(client):
    resp = await client.get("/api/equipment/filter-type")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0
    return data[0]["id"]


# ── Tests ─────────────────────────────────────────────────────────────────────

_EXPECTED_KEYS = {
    "cameras",
    "telescopes",
    "filters",
    "mounts",
    "focusers",
    "filter_wheels",
    "oags",
    "guide_scopes",
    "computers",
    "software",
}


async def test_mine_counts_zero_when_nothing_owned(client: AsyncClient):
    """GET /mine-counts returns 200 with all 10 keys at 0 when nothing is marked mine."""
    # Create items with is_mine=False to confirm they don't count
    mfr = await _make_manufacturer(client, "CountsZeroMfg")
    sensor = await _make_sensor(client, mfr["id"], "Sensor-counts-zero")
    await _make_camera(client, mfr["id"], sensor["id"], "ZeroCam", is_mine=False)
    await _make_telescope(client, mfr["id"], "ZeroScope", is_mine=False)

    resp = await client.get("/api/equipment/mine-counts")
    assert resp.status_code == 200

    data = resp.json()
    assert set(data.keys()) == _EXPECTED_KEYS

    for key in _EXPECTED_KEYS:
        assert data[key] == 0, f"Expected {key}=0, got {data[key]}"


async def test_mine_counts_reflect_marked_items(client: AsyncClient):
    """GET /mine-counts returns correct per-type counts after marking items."""
    mfr = await _make_manufacturer(client, "CountsMarkMfg")
    sensor1 = await _make_sensor(client, mfr["id"], "Sensor-counts-m1")
    sensor2 = await _make_sensor(client, mfr["id"], "Sensor-counts-m2")
    sensor3 = await _make_sensor(client, mfr["id"], "Sensor-counts-m3")
    ft_id = await _get_filter_type_id(client)

    # Create 2 mine cameras, 1 non-mine camera
    await _make_camera(client, mfr["id"], sensor1["id"], "MineCam1", is_mine=True)
    await _make_camera(client, mfr["id"], sensor2["id"], "MineCam2", is_mine=True)
    await _make_camera(client, mfr["id"], sensor3["id"], "NotMineCam", is_mine=False)

    # Create 1 mine telescope
    await _make_telescope(client, mfr["id"], "MineScope", is_mine=True)
    await _make_telescope(client, mfr["id"], "NotMineScope", is_mine=False)

    # Create 3 mine filters
    await _make_filter(client, mfr["id"], ft_id, "MineFilter1", is_mine=True)
    await _make_filter(client, mfr["id"], ft_id, "MineFilter2", is_mine=True)
    await _make_filter(client, mfr["id"], ft_id, "MineFilter3", is_mine=True)
    await _make_filter(client, mfr["id"], ft_id, "NotMineFilter", is_mine=False)

    resp = await client.get("/api/equipment/mine-counts")
    assert resp.status_code == 200

    data = resp.json()
    assert set(data.keys()) == _EXPECTED_KEYS

    assert data["cameras"] == 2
    assert data["telescopes"] == 1
    assert data["filters"] == 3
    assert data["mounts"] == 0
    assert data["focusers"] == 0
    assert data["filter_wheels"] == 0
    assert data["oags"] == 0
    assert data["guide_scopes"] == 0
    assert data["computers"] == 0
    assert data["software"] == 0


async def test_mine_counts_ignores_retired(client: AsyncClient):
    """Retired cameras (active=0, is_mine=1) still count as mine."""
    mfr = await _make_manufacturer(client, "CountsRetiredMfg")
    sensor = await _make_sensor(client, mfr["id"], "Sensor-counts-retired")

    # Create a mine camera then retire it
    cam = await _make_camera(client, mfr["id"], sensor["id"], "RetiredMineCam", is_mine=True)

    # Retire via DELETE (soft-delete sets active=0)
    del_resp = await client.delete(f"/api/equipment/camera/{cam['id']}")
    assert del_resp.status_code == 200

    resp = await client.get("/api/equipment/mine-counts")
    assert resp.status_code == 200

    data = resp.json()
    # Retired-but-mine camera must still be counted
    assert data["cameras"] >= 1, "Retired mine camera should still be counted in mine-counts"
