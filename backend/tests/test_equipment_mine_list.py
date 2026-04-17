"""Tests for ?mine filter and is_mine DESC ordering on equipment list endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _make_manufacturer(client, name="MineTestMfg"):
    resp = await client.post("/api/equipment/manufacturer", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


async def _make_sensor(client, manufacturer_id, model_name="IMX571-mine"):
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


async def _get_filter_type_id(client):
    resp = await client.get("/api/equipment/filter-type")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0
    for ft in data:
        if ft["name"] == "narrowband_single":
            return ft["id"]
    return data[0]["id"]


# ── Camera list tests ─────────────────────────────────────────────────────────


class TestCameraMineList:
    async def test_camera_list_orders_mine_first(self, client: AsyncClient):
        """mine=1 cameras must appear before mine=0 cameras in the default list."""
        mfr = await _make_manufacturer(client, "MineOrderCamMfg")
        sensor_a = await _make_sensor(client, mfr["id"], "SensorA-ord")
        sensor_b = await _make_sensor(client, mfr["id"], "SensorB-ord")

        # Create non-mine camera first (so insertion order would put it first
        # if ordering were broken)
        resp = await client.post(
            "/api/equipment/camera",
            json={
                "manufacturer_id": mfr["id"],
                "sensor_id": sensor_a["id"],
                "model_name": "Zzz NotMine Cam",
                "is_mine": False,
            },
        )
        assert resp.status_code == 201

        resp = await client.post(
            "/api/equipment/camera",
            json={
                "manufacturer_id": mfr["id"],
                "sensor_id": sensor_b["id"],
                "model_name": "Aaa Mine Cam",
                "is_mine": True,
            },
        )
        assert resp.status_code == 201

        resp = await client.get("/api/equipment/camera")
        assert resp.status_code == 200
        items = resp.json()
        # Filter to just our two cameras
        ours = [c for c in items if c["model_name"] in {"Zzz NotMine Cam", "Aaa Mine Cam"}]
        assert len(ours) == 2

        # First must be the mine camera
        assert ours[0]["is_mine"] is True, "Expected mine camera to appear first"

        # No is_mine=0 row should appear before any is_mine=1 row
        seen_not_mine = False
        for item in items:
            if not item["is_mine"]:
                seen_not_mine = True
            elif seen_not_mine:
                pytest.fail("is_mine=1 row appeared after an is_mine=0 row")

    async def test_camera_list_mine_filter(self, client: AsyncClient):
        """?mine=true returns only cameras with is_mine=true."""
        mfr = await _make_manufacturer(client, "MineFilterCamMfg")
        sensor_a = await _make_sensor(client, mfr["id"], "SensorA-flt")
        sensor_b = await _make_sensor(client, mfr["id"], "SensorB-flt")

        resp = await client.post(
            "/api/equipment/camera",
            json={
                "manufacturer_id": mfr["id"],
                "sensor_id": sensor_a["id"],
                "model_name": "MineFilter Mine",
                "is_mine": True,
            },
        )
        assert resp.status_code == 201

        resp = await client.post(
            "/api/equipment/camera",
            json={
                "manufacturer_id": mfr["id"],
                "sensor_id": sensor_b["id"],
                "model_name": "MineFilter NotMine",
                "is_mine": False,
            },
        )
        assert resp.status_code == 201

        resp = await client.get("/api/equipment/camera?mine=true")
        assert resp.status_code == 200
        items = resp.json()
        ours = [c for c in items if c["model_name"] in {"MineFilter Mine", "MineFilter NotMine"}]
        assert len(ours) == 1
        assert ours[0]["is_mine"] is True
        assert ours[0]["model_name"] == "MineFilter Mine"

    async def test_camera_list_mine_false_returns_all(self, client: AsyncClient):
        """?mine=false returns all cameras regardless of is_mine."""
        mfr = await _make_manufacturer(client, "MineFalseCamMfg")
        sensor_a = await _make_sensor(client, mfr["id"], "SensorA-false")
        sensor_b = await _make_sensor(client, mfr["id"], "SensorB-false")

        resp = await client.post(
            "/api/equipment/camera",
            json={
                "manufacturer_id": mfr["id"],
                "sensor_id": sensor_a["id"],
                "model_name": "MineFalse Mine",
                "is_mine": True,
            },
        )
        assert resp.status_code == 201

        resp = await client.post(
            "/api/equipment/camera",
            json={
                "manufacturer_id": mfr["id"],
                "sensor_id": sensor_b["id"],
                "model_name": "MineFalse NotMine",
                "is_mine": False,
            },
        )
        assert resp.status_code == 201

        resp = await client.get("/api/equipment/camera?mine=false")
        assert resp.status_code == 200
        items = resp.json()
        names = {c["model_name"] for c in items}
        assert "MineFalse Mine" in names
        assert "MineFalse NotMine" in names

    async def test_camera_list_mine_filter_composes_with_include_retired(self, client: AsyncClient):
        """?mine=true respects active filter; ?mine=true&include_retired=true shows both."""
        mfr = await _make_manufacturer(client, "MineRetiredCamMfg")
        sensor_a = await _make_sensor(client, mfr["id"], "SensorA-ret")
        sensor_b = await _make_sensor(client, mfr["id"], "SensorB-ret")

        resp = await client.post(
            "/api/equipment/camera",
            json={
                "manufacturer_id": mfr["id"],
                "sensor_id": sensor_a["id"],
                "model_name": "MineRetired Active",
                "is_mine": True,
            },
        )
        assert resp.status_code == 201
        active_id = resp.json()["id"]

        resp = await client.post(
            "/api/equipment/camera",
            json={
                "manufacturer_id": mfr["id"],
                "sensor_id": sensor_b["id"],
                "model_name": "MineRetired Retired",
                "is_mine": True,
            },
        )
        assert resp.status_code == 201
        retired_id = resp.json()["id"]

        # Soft-delete the second camera
        resp = await client.delete(f"/api/equipment/camera/{retired_id}")
        assert resp.status_code == 200

        # ?mine=true — only the active one
        resp = await client.get("/api/equipment/camera?mine=true")
        assert resp.status_code == 200
        ids = {c["id"] for c in resp.json()}
        assert active_id in ids
        assert retired_id not in ids

        # ?mine=true&include_retired=true — both
        resp = await client.get("/api/equipment/camera?mine=true&include_retired=true")
        assert resp.status_code == 200
        ids = {c["id"] for c in resp.json()}
        assert active_id in ids
        assert retired_id in ids


# ── Telescope regression ──────────────────────────────────────────────────────


class TestTelescopeMineList:
    async def test_telescope_list_orders_mine_first(self, client: AsyncClient):
        """mine=1 telescopes must appear before mine=0 telescopes."""
        mfr = await _make_manufacturer(client, "MineScopeMfg")

        resp = await client.post(
            "/api/equipment/telescope",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "Zzz NotMine Scope",
                "aperture_mm": 100.0,
                "is_mine": False,
            },
        )
        assert resp.status_code == 201

        resp = await client.post(
            "/api/equipment/telescope",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "Aaa Mine Scope",
                "aperture_mm": 280.0,
                "is_mine": True,
            },
        )
        assert resp.status_code == 201

        resp = await client.get("/api/equipment/telescope")
        assert resp.status_code == 200
        items = resp.json()
        ours = [t for t in items if t["model_name"] in {"Zzz NotMine Scope", "Aaa Mine Scope"}]
        assert len(ours) == 2
        assert ours[0]["is_mine"] is True, "Expected mine telescope to appear first"

        seen_not_mine = False
        for item in items:
            if not item["is_mine"]:
                seen_not_mine = True
            elif seen_not_mine:
                pytest.fail("is_mine=1 row appeared after an is_mine=0 row")


# ── Filter regression ─────────────────────────────────────────────────────────


class TestFilterMineList:
    async def test_filter_list_mine_filter(self, client: AsyncClient):
        """?mine=true returns only filters with is_mine=true."""
        mfr = await _make_manufacturer(client, "MineFilterMfg")
        ft_id = await _get_filter_type_id(client)

        resp = await client.post(
            "/api/equipment/filter",
            json={
                "manufacturer_id": mfr["id"],
                "filter_type_id": ft_id,
                "model_name": "FilterMine Ha",
                "is_mine": True,
            },
        )
        assert resp.status_code == 201

        resp = await client.post(
            "/api/equipment/filter",
            json={
                "manufacturer_id": mfr["id"],
                "filter_type_id": ft_id,
                "model_name": "FilterNotMine OIII",
                "is_mine": False,
            },
        )
        assert resp.status_code == 201

        resp = await client.get("/api/equipment/filter?mine=true")
        assert resp.status_code == 200
        items = resp.json()
        ours = [f for f in items if f["model_name"] in {"FilterMine Ha", "FilterNotMine OIII"}]
        assert len(ours) == 1
        assert ours[0]["is_mine"] is True
        assert ours[0]["model_name"] == "FilterMine Ha"
