"""Tests for POST /<type>/{id}/mine toggle endpoint on all 10 owned equipment types."""

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _make_manufacturer(client, name="ToggleMfg"):
    resp = await client.post("/api/equipment/manufacturer", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


async def _make_sensor(client, manufacturer_id, model_name="IMX571-toggle"):
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


async def _make_camera(client, manufacturer_id, sensor_id, is_mine=False):
    resp = await client.post(
        "/api/equipment/camera",
        json={
            "manufacturer_id": manufacturer_id,
            "sensor_id": sensor_id,
            "model_name": "Toggle Test Cam",
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
    for ft in data:
        if ft["name"] == "narrowband_single":
            return ft["id"]
    return data[0]["id"]


# ── Camera-specific toggle tests ──────────────────────────────────────────────


class TestCameraToggleMine:
    async def test_camera_toggle_mine_on(self, client: AsyncClient):
        """POST /mine with is_mine=true sets the flag; GET confirms it."""
        mfr = await _make_manufacturer(client, "CamToggleOnMfg")
        sensor = await _make_sensor(client, mfr["id"], "Sensor-toggle-on")
        cam = await _make_camera(client, mfr["id"], sensor["id"], is_mine=False)
        assert cam["is_mine"] is False

        resp = await client.post(f"/api/equipment/camera/{cam['id']}/mine", json={"is_mine": True})
        assert resp.status_code == 200
        assert resp.json()["is_mine"] is True

        # Confirm round-trip via GET
        resp = await client.get(f"/api/equipment/camera/{cam['id']}")
        assert resp.status_code == 200
        assert resp.json()["is_mine"] is True

    async def test_camera_toggle_mine_off(self, client: AsyncClient):
        """POST /mine with is_mine=false clears the flag."""
        mfr = await _make_manufacturer(client, "CamToggleOffMfg")
        sensor = await _make_sensor(client, mfr["id"], "Sensor-toggle-off")
        cam = await _make_camera(client, mfr["id"], sensor["id"], is_mine=True)
        assert cam["is_mine"] is True

        resp = await client.post(f"/api/equipment/camera/{cam['id']}/mine", json={"is_mine": False})
        assert resp.status_code == 200
        assert resp.json()["is_mine"] is False

    async def test_camera_toggle_mine_idempotent(self, client: AsyncClient):
        """Toggling to True twice both return 200 with is_mine=true."""
        mfr = await _make_manufacturer(client, "CamToggleIdmMfg")
        sensor = await _make_sensor(client, mfr["id"], "Sensor-toggle-idm")
        cam = await _make_camera(client, mfr["id"], sensor["id"], is_mine=False)

        resp1 = await client.post(f"/api/equipment/camera/{cam['id']}/mine", json={"is_mine": True})
        assert resp1.status_code == 200
        assert resp1.json()["is_mine"] is True

        resp2 = await client.post(f"/api/equipment/camera/{cam['id']}/mine", json={"is_mine": True})
        assert resp2.status_code == 200
        assert resp2.json()["is_mine"] is True

    async def test_camera_toggle_mine_unknown_id(self, client: AsyncClient):
        """POST /mine for a non-existent camera returns 404."""
        resp = await client.post("/api/equipment/camera/99999999/mine", json={"is_mine": True})
        assert resp.status_code == 404


# ── Parametrized smoke test: 9 non-camera types ───────────────────────────────
#
# Route map:
#   filter_wheel → filter-wheel
#   guide_scope  → guide-scope
#   All others: route == table name

_OTHER_TYPES = [
    ("telescope", "telescope"),
    ("filter", "filter"),
    ("mount", "mount"),
    ("focuser", "focuser"),
    ("filter_wheel", "filter-wheel"),
    ("oag", "oag"),
    ("guide_scope", "guide-scope"),
    ("computer", "computer"),
    ("software", "software"),
]


async def _create_item(client: AsyncClient, type_key: str, route: str, mfr_id: int) -> dict:
    """Create a minimal item for the given type and return the response body."""
    if type_key == "telescope":
        payload = {
            "manufacturer_id": mfr_id,
            "model_name": f"Toggle-{type_key}",
            "aperture_mm": 100.0,
            "is_mine": False,
        }
    elif type_key == "filter":
        resp = await client.get("/api/equipment/filter-type")
        assert resp.status_code == 200
        ft_id = resp.json()[0]["id"]
        payload = {
            "manufacturer_id": mfr_id,
            "filter_type_id": ft_id,
            "model_name": f"Toggle-{type_key}",
            "is_mine": False,
        }
    elif type_key == "mount":
        payload = {
            "manufacturer_id": mfr_id,
            "model_name": f"Toggle-{type_key}",
            "is_mine": False,
        }
    elif type_key == "focuser":
        payload = {
            "manufacturer_id": mfr_id,
            "model_name": f"Toggle-{type_key}",
            "is_mine": False,
        }
    elif type_key == "filter_wheel":
        payload = {
            "manufacturer_id": mfr_id,
            "model_name": f"Toggle-{type_key}",
            "num_positions": 5,
            "is_mine": False,
        }
    elif type_key == "oag":
        payload = {
            "manufacturer_id": mfr_id,
            "model_name": f"Toggle-{type_key}",
            "is_mine": False,
        }
    elif type_key == "guide_scope":
        payload = {
            "manufacturer_id": mfr_id,
            "model_name": f"Toggle-{type_key}",
            "aperture_mm": 50.0,
            "focal_length_mm": 200.0,
            "is_mine": False,
        }
    elif type_key == "computer":
        payload = {
            "manufacturer_id": mfr_id,
            "model_name": f"Toggle-{type_key}",
            "is_mine": False,
        }
    elif type_key == "software":
        payload = {
            "manufacturer_id": mfr_id,
            "name": f"Toggle-{type_key}",
            "category": "utility",
            "is_mine": False,
        }
    else:
        raise ValueError(f"Unknown type_key: {type_key}")

    resp = await client.post(f"/api/equipment/{route}", json=payload)
    assert resp.status_code == 201, f"POST /api/equipment/{route} failed: {resp.text}"
    return resp.json()


@pytest.mark.parametrize("type_key,route", _OTHER_TYPES)
async def test_toggle_mine_other_types(client: AsyncClient, type_key: str, route: str):
    """POST /<type>/{id}/mine with is_mine=true returns 200 and is_mine=true for all 9 types."""
    mfr = await _make_manufacturer(client, f"Toggle-{type_key}-Mfg")
    item = await _create_item(client, type_key, route, mfr["id"])
    assert item["is_mine"] is False

    resp = await client.post(f"/api/equipment/{route}/{item['id']}/mine", json={"is_mine": True})
    assert resp.status_code == 200, f"Toggle mine failed for {route}: {resp.text}"
    assert resp.json()["is_mine"] is True, f"is_mine not True in response for {route}"
