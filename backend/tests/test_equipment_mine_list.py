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


# ── Parametrized smoke test: all 10 owned types ───────────────────────────────
#
# Focuses on list-level is_mine surfacing for the 7 types not covered by the
# dedicated classes above (mount, focuser, filter_wheel, oag, guide_scope,
# computer, software), plus re-validates camera/telescope/filter in one place.
#
# Each case creates two rows via POST — non-mine first (so insertion order would
# surface it first if the ORDER BY were absent), mine second — then asserts:
#   1. The created row's is_mine round-trips correctly from the POST response.
#   2. The mine row appears before the non-mine row in the GET list.
#
# FK fields that are optional (mount_type_id, focuser_type_id, form_factor_id)
# are omitted to keep setup minimal; the API accepts NULL for all of them.


def _camera_payloads(mfr_id: int, sensor_id: int) -> tuple[dict, dict]:
    return (
        {
            "manufacturer_id": mfr_id,
            "sensor_id": sensor_id,
            "model_name": "Zzz NotMine",
            "is_mine": False,
        },
        {
            "manufacturer_id": mfr_id,
            "sensor_id": sensor_id,
            "model_name": "Aaa Mine",
            "is_mine": True,
        },
    )


def _telescope_payloads(mfr_id: int, _unused: int) -> tuple[dict, dict]:
    return (
        {
            "manufacturer_id": mfr_id,
            "model_name": "Zzz NotMine",
            "aperture_mm": 100.0,
            "is_mine": False,
        },  # noqa: E501
        {
            "manufacturer_id": mfr_id,
            "model_name": "Aaa Mine",
            "aperture_mm": 280.0,
            "is_mine": True,
        },  # noqa: E501
    )


def _filter_payloads(mfr_id: int, ft_id: int) -> tuple[dict, dict]:
    return (
        {
            "manufacturer_id": mfr_id,
            "filter_type_id": ft_id,
            "model_name": "Zzz NotMine",
            "is_mine": False,
        },
        {
            "manufacturer_id": mfr_id,
            "filter_type_id": ft_id,
            "model_name": "Aaa Mine",
            "is_mine": True,
        },
    )


def _mount_payloads(mfr_id: int, _unused: int) -> tuple[dict, dict]:
    return (
        {"manufacturer_id": mfr_id, "model_name": "Zzz NotMine", "is_mine": False},
        {"manufacturer_id": mfr_id, "model_name": "Aaa Mine", "is_mine": True},
    )


def _focuser_payloads(mfr_id: int, _unused: int) -> tuple[dict, dict]:
    return (
        {"manufacturer_id": mfr_id, "model_name": "Zzz NotMine", "is_mine": False},
        {"manufacturer_id": mfr_id, "model_name": "Aaa Mine", "is_mine": True},
    )


def _filter_wheel_payloads(mfr_id: int, _unused: int) -> tuple[dict, dict]:
    return (
        {
            "manufacturer_id": mfr_id,
            "model_name": "Zzz NotMine",
            "num_positions": 5,
            "is_mine": False,
        },  # noqa: E501
        {"manufacturer_id": mfr_id, "model_name": "Aaa Mine", "num_positions": 7, "is_mine": True},
    )


def _oag_payloads(mfr_id: int, _unused: int) -> tuple[dict, dict]:
    return (
        {"manufacturer_id": mfr_id, "model_name": "Zzz NotMine", "is_mine": False},
        {"manufacturer_id": mfr_id, "model_name": "Aaa Mine", "is_mine": True},
    )


def _guide_scope_payloads(mfr_id: int, _unused: int) -> tuple[dict, dict]:
    return (
        {
            "manufacturer_id": mfr_id,
            "model_name": "Zzz NotMine",
            "aperture_mm": 50.0,
            "focal_length_mm": 200.0,
            "is_mine": False,
        },
        {
            "manufacturer_id": mfr_id,
            "model_name": "Aaa Mine",
            "aperture_mm": 60.0,
            "focal_length_mm": 240.0,
            "is_mine": True,
        },
    )


def _computer_payloads(mfr_id: int, _unused: int) -> tuple[dict, dict]:
    return (
        {"manufacturer_id": mfr_id, "model_name": "Zzz NotMine", "is_mine": False},
        {"manufacturer_id": mfr_id, "model_name": "Aaa Mine", "is_mine": True},
    )


def _software_payloads(mfr_id: int, _unused: int) -> tuple[dict, dict]:
    # manufacturer_id is optional for software; include it for consistency.
    return (
        {"manufacturer_id": mfr_id, "name": "Zzz NotMine", "category": "utility", "is_mine": False},
        {"manufacturer_id": mfr_id, "name": "Aaa Mine", "category": "capture", "is_mine": True},
    )


# name-field key varies by type (model_name vs name for software)
_NAME_KEY: dict[str, str] = {
    "camera": "model_name",
    "telescope": "model_name",
    "filter": "model_name",
    "mount": "model_name",
    "focuser": "model_name",
    "filter-wheel": "model_name",
    "oag": "model_name",
    "guide-scope": "model_name",
    "computer": "model_name",
    "software": "name",
}

_PAYLOAD_BUILDERS = {
    "camera": _camera_payloads,
    "telescope": _telescope_payloads,
    "filter": _filter_payloads,
    "mount": _mount_payloads,
    "focuser": _focuser_payloads,
    "filter-wheel": _filter_wheel_payloads,
    "oag": _oag_payloads,
    "guide-scope": _guide_scope_payloads,
    "computer": _computer_payloads,
    "software": _software_payloads,
}


@pytest.mark.parametrize("route", list(_PAYLOAD_BUILDERS.keys()))
class TestIsMineRoundTripAllTypes:
    """Smoke test: POST is_mine=True round-trips and the row appears first in GET list.

    Complements camera/telescope/filter dedicated classes by covering the
    remaining 7 owned types (mount, focuser, filter_wheel, oag, guide_scope,
    computer, software).  The test also re-validates the first three so a
    single parametrize covers all 10 owned types end-to-end.
    """

    async def test_is_mine_create_round_trip(self, client: AsyncClient, route: str):
        """POST with is_mine=True must return is_mine=True in the response body."""
        mfr = await _make_manufacturer(client, f"RoundTrip-{route}-Mfg")
        aux_id = await self._aux_id(client, route, mfr["id"])
        _, mine_payload = _PAYLOAD_BUILDERS[route](mfr["id"], aux_id)

        resp = await client.post(f"/api/equipment/{route}", json=mine_payload)
        assert resp.status_code == 201, f"POST /api/equipment/{route} failed: {resp.text}"
        assert resp.json()["is_mine"] is True, (
            f"POST /api/equipment/{route} did not round-trip is_mine=True"
        )

    async def test_is_mine_appears_first_in_list(self, client: AsyncClient, route: str):
        """mine row created after non-mine row must still appear first in GET list."""
        mfr = await _make_manufacturer(client, f"ListOrder-{route}-Mfg")
        aux_id = await self._aux_id(client, route, mfr["id"])
        not_mine_payload, mine_payload = _PAYLOAD_BUILDERS[route](mfr["id"], aux_id)
        name_key = _NAME_KEY[route]
        not_mine_name = not_mine_payload[name_key]
        mine_name = mine_payload[name_key]

        resp = await client.post(f"/api/equipment/{route}", json=not_mine_payload)
        assert resp.status_code == 201
        resp = await client.post(f"/api/equipment/{route}", json=mine_payload)
        assert resp.status_code == 201

        resp = await client.get(f"/api/equipment/{route}")
        assert resp.status_code == 200
        items = resp.json()
        ours = [i for i in items if i.get(name_key) in {not_mine_name, mine_name}]
        assert len(ours) == 2, f"Expected 2 rows for {route}, got {len(ours)}"
        assert ours[0]["is_mine"] is True, f"Expected mine row to appear first for {route}"

    # ── helpers ───────────────────────────────────────────────────────────────

    async def _aux_id(self, client: AsyncClient, route: str, mfr_id: int) -> int:
        """Return a secondary FK id for types that need one.

        camera → sensor id; filter → filter_type id; all others → 0 (ignored).
        """
        if route == "camera":
            sensor = await _make_sensor(client, mfr_id, f"SensorSmoke-{mfr_id}")
            return sensor["id"]
        if route == "filter":
            return await _get_filter_type_id(client)
        # All other types either use no secondary FK or accept None.
        return 0
