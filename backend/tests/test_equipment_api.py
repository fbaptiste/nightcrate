"""Tests for equipment CRUD API endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _make_manufacturer(client, name="TestMfg"):
    resp = await client.post("/api/equipment/manufacturer", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


async def _make_sensor(client, manufacturer_id, model_name="IMX571"):
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


async def _make_connection_interface(client, name="USB 3.0", category="data"):
    resp = await client.post(
        "/api/equipment/connection-interface",
        json={"name": name, "category": category},
    )
    assert resp.status_code == 201
    return resp.json()


async def _make_connector_size(client, name="M48"):
    resp = await client.post(
        "/api/equipment/connector-size",
        json={"name": name, "diameter_mm": 48.0},
    )
    assert resp.status_code == 201
    return resp.json()


async def _get_filter_type_id(client):
    """Get the ID of a seeded filter_type row (narrowband_single)."""
    resp = await client.get("/api/equipment/filter-type")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0
    for ft in data:
        if ft["name"] == "narrowband_single":
            return ft["id"]
    return data[0]["id"]


# ── Manufacturer ──────────────────────────────────────────────────────────────


class TestManufacturerCRUD:
    async def test_create_and_list(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "ZWO")
        assert mfr["name"] == "ZWO"
        assert mfr["active"] is True
        assert "id" in mfr

        resp = await client.get("/api/equipment/manufacturer")
        assert resp.status_code == 200
        names = [m["name"] for m in resp.json()]
        assert "ZWO" in names

    async def test_get_by_id(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "Celestron")
        resp = await client.get(f"/api/equipment/manufacturer/{mfr['id']}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Celestron"

    async def test_update(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "OldName")
        resp = await client.put(
            f"/api/equipment/manufacturer/{mfr['id']}",
            json={"name": "NewName", "website": "https://example.com"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "NewName"
        assert data["website"] == "https://example.com"
        # active unchanged
        assert data["active"] is True

    async def test_soft_delete(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "ToDelete")
        resp = await client.delete(f"/api/equipment/manufacturer/{mfr['id']}")
        assert resp.status_code == 200

        # Gone from default list
        resp = await client.get("/api/equipment/manufacturer")
        names = [m["name"] for m in resp.json()]
        assert "ToDelete" not in names

        # Present with include_retired=true
        resp = await client.get("/api/equipment/manufacturer?include_retired=true")
        names = [m["name"] for m in resp.json()]
        assert "ToDelete" in names

    async def test_duplicate_name_409(self, client: AsyncClient):
        await _make_manufacturer(client, "Duplicate")
        resp = await client.post("/api/equipment/manufacturer", json={"name": "Duplicate"})
        assert resp.status_code == 409

    async def test_not_found_404(self, client: AsyncClient):
        resp = await client.get("/api/equipment/manufacturer/99999")
        assert resp.status_code == 404


# ── Sensor ────────────────────────────────────────────────────────────────────


class TestSensorCRUD:
    async def test_create_and_list(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "Sony")
        sensor = await _make_sensor(client, mfr["id"], "IMX294")
        assert sensor["model_name"] == "IMX294"
        assert sensor["manufacturer"]["name"] == "Sony"
        assert sensor["active"] is True

        resp = await client.get("/api/equipment/sensor")
        assert resp.status_code == 200
        models = [s["model_name"] for s in resp.json()]
        assert "IMX294" in models

    async def test_update_sensor(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "Panasonic")
        sensor = await _make_sensor(client, mfr["id"], "MN34230")
        resp = await client.put(
            f"/api/equipment/sensor/{sensor['id']}",
            json={"notes": "Updated notes", "pixel_size_um": 4.5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["notes"] == "Updated notes"
        assert data["pixel_size_um"] == 4.5
        assert data["model_name"] == "MN34230"

    async def test_soft_delete_sensor(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "Aptina")
        sensor = await _make_sensor(client, mfr["id"], "AR0521")
        resp = await client.delete(f"/api/equipment/sensor/{sensor['id']}")
        assert resp.status_code == 200

        resp = await client.get("/api/equipment/sensor")
        models = [s["model_name"] for s in resp.json()]
        assert "AR0521" not in models

        resp = await client.get("/api/equipment/sensor?include_retired=true")
        models = [s["model_name"] for s in resp.json()]
        assert "AR0521" in models


# ── Camera ────────────────────────────────────────────────────────────────────


class TestCameraCRUD:
    async def test_create_with_interfaces(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "ZWO Cam")
        sensor = await _make_sensor(client, mfr["id"], "IMX571C")
        iface = await _make_connection_interface(client, "USB 3.2", "data")
        connector = await _make_connector_size(client, "M54")

        resp = await client.post(
            "/api/equipment/camera",
            json={
                "manufacturer_id": mfr["id"],
                "sensor_id": sensor["id"],
                "connector_size_id": connector["id"],
                "model_name": "ASI2600MC Pro",
                "cooled": True,
                "cooling_delta_c": 35.0,
                "interface_ids": [iface["id"]],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["model_name"] == "ASI2600MC Pro"
        assert data["cooled"] is True
        assert data["sensor"]["model_name"] == "IMX571C"
        assert data["manufacturer"]["name"] == "ZWO Cam"
        assert data["connector_size"]["name"] == "M54"
        assert len(data["interfaces"]) == 1
        assert data["interfaces"][0]["name"] == "USB 3.2"

    async def test_update_replaces_interfaces(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "ZWO Cam2")
        sensor = await _make_sensor(client, mfr["id"], "IMX455")
        iface1 = await _make_connection_interface(client, "USB2 Old", "data")
        iface2 = await _make_connection_interface(client, "USB3 New", "data")

        resp = await client.post(
            "/api/equipment/camera",
            json={
                "manufacturer_id": mfr["id"],
                "sensor_id": sensor["id"],
                "model_name": "CamWithIface",
                "interface_ids": [iface1["id"]],
            },
        )
        assert resp.status_code == 201
        camera_id = resp.json()["id"]

        # Update interfaces to use new one only
        resp = await client.put(
            f"/api/equipment/camera/{camera_id}",
            json={"interface_ids": [iface2["id"]]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["interfaces"]) == 1
        assert data["interfaces"][0]["name"] == "USB3 New"

    async def test_soft_delete_camera(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "DeleteCamMfr")
        sensor = await _make_sensor(client, mfr["id"], "DeleteSensor")
        resp = await client.post(
            "/api/equipment/camera",
            json={
                "manufacturer_id": mfr["id"],
                "sensor_id": sensor["id"],
                "model_name": "DeleteCam",
            },
        )
        assert resp.status_code == 201
        camera_id = resp.json()["id"]

        resp = await client.delete(f"/api/equipment/camera/{camera_id}")
        assert resp.status_code == 200

        resp = await client.get("/api/equipment/camera")
        models = [c["model_name"] for c in resp.json()]
        assert "DeleteCam" not in models


# ── Telescope ─────────────────────────────────────────────────────────────────


class TestTelescopeCRUD:
    async def test_create_with_connectors(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "Celestron Scope")
        connector = await _make_connector_size(client, "3-inch")

        resp = await client.post(
            "/api/equipment/telescope",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "C11 SCT",
                "aperture_mm": 279.4,
                "connector_size_ids": [connector["id"]],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["model_name"] == "C11 SCT"
        assert data["aperture_mm"] == 279.4
        assert data["manufacturer"]["name"] == "Celestron Scope"
        assert len(data["connectors"]) == 1
        assert data["connectors"][0]["name"] == "3-inch"
        assert data["configurations"] == []

    async def test_add_configuration(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "ScopeMfr2")
        resp = await client.post(
            "/api/equipment/telescope",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "RC8",
                "aperture_mm": 203.0,
            },
        )
        assert resp.status_code == 201
        telescope_id = resp.json()["id"]

        resp = await client.post(
            f"/api/equipment/telescope/{telescope_id}/configuration",
            json={
                "telescope_id": telescope_id,
                "config_name": "Native f/8",
                "effective_focal_length_mm": 1624.0,
                "effective_focal_ratio": 8.0,
                "reduction_factor": 1.0,
                "is_native": True,
            },
        )
        assert resp.status_code == 201
        cfg = resp.json()
        assert cfg["config_name"] == "Native f/8"
        assert cfg["is_native"] is True

        # Config appears in telescope response
        resp = await client.get(f"/api/equipment/telescope/{telescope_id}")
        data = resp.json()
        assert len(data["configurations"]) == 1
        assert data["configurations"][0]["config_name"] == "Native f/8"

    async def test_native_config_uniqueness(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "ScopeMfr3")
        resp = await client.post(
            "/api/equipment/telescope",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "ED80",
                "aperture_mm": 80.0,
            },
        )
        telescope_id = resp.json()["id"]

        # First native config OK
        resp = await client.post(
            f"/api/equipment/telescope/{telescope_id}/configuration",
            json={
                "telescope_id": telescope_id,
                "config_name": "Native",
                "effective_focal_length_mm": 600.0,
                "effective_focal_ratio": 7.5,
                "reduction_factor": 1.0,
                "is_native": True,
            },
        )
        assert resp.status_code == 201

        # Second native config should 409
        resp = await client.post(
            f"/api/equipment/telescope/{telescope_id}/configuration",
            json={
                "telescope_id": telescope_id,
                "config_name": "AlsoNative",
                "effective_focal_length_mm": 600.0,
                "effective_focal_ratio": 7.5,
                "reduction_factor": 1.0,
                "is_native": True,
            },
        )
        assert resp.status_code == 409

    async def test_delete_configuration(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "ScopeMfr4")
        resp = await client.post(
            "/api/equipment/telescope",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "APO60",
                "aperture_mm": 60.0,
            },
        )
        telescope_id = resp.json()["id"]

        resp = await client.post(
            f"/api/equipment/telescope/{telescope_id}/configuration",
            json={
                "telescope_id": telescope_id,
                "config_name": "To Delete",
                "effective_focal_length_mm": 360.0,
                "effective_focal_ratio": 6.0,
                "reduction_factor": 1.0,
                "is_native": False,
            },
        )
        config_id = resp.json()["id"]

        resp = await client.delete(
            f"/api/equipment/telescope/{telescope_id}/configuration/{config_id}"
        )
        assert resp.status_code == 200

        resp = await client.get(f"/api/equipment/telescope/{telescope_id}")
        assert resp.json()["configurations"] == []

    async def test_update_connectors(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "ScopeMfr5")
        c1 = await _make_connector_size(client, "M63")
        c2 = await _make_connector_size(client, "M68")

        resp = await client.post(
            "/api/equipment/telescope",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "WideField",
                "aperture_mm": 100.0,
                "connector_size_ids": [c1["id"]],
            },
        )
        telescope_id = resp.json()["id"]

        resp = await client.put(
            f"/api/equipment/telescope/{telescope_id}",
            json={"connector_size_ids": [c2["id"]]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["connectors"]) == 1
        assert data["connectors"][0]["name"] == "M68"


# ── Filter ────────────────────────────────────────────────────────────────────


class TestFilterCRUD:
    async def test_create_and_add_passband(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "Antlia")
        ft_id = await _get_filter_type_id(client)

        resp = await client.post(
            "/api/equipment/filter",
            json={
                "manufacturer_id": mfr["id"],
                "filter_type_id": ft_id,
                "model_name": "Ha 3nm",
                "peak_transmission_pct": 92.0,
            },
        )
        assert resp.status_code == 201
        filter_id = resp.json()["id"]

        # Add passband
        resp = await client.post(
            f"/api/equipment/filter/{filter_id}/passband",
            json={
                "filter_id": filter_id,
                "line_name": "Ha",
                "central_wavelength_nm": 656.28,
                "bandwidth_nm": 3.0,
                "peak_transmission_pct": 92.0,
            },
        )
        assert resp.status_code == 201
        pb = resp.json()
        assert pb["central_wavelength_nm"] == 656.28
        assert pb["line_name"] == "Ha"

    async def test_passbands_in_response(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "Optolong")
        ft_id = await _get_filter_type_id(client)

        resp = await client.post(
            "/api/equipment/filter",
            json={
                "manufacturer_id": mfr["id"],
                "filter_type_id": ft_id,
                "model_name": "OIII 7nm",
            },
        )
        filter_id = resp.json()["id"]

        await client.post(
            f"/api/equipment/filter/{filter_id}/passband",
            json={
                "filter_id": filter_id,
                "line_name": "Oiii",
                "central_wavelength_nm": 500.7,
                "bandwidth_nm": 7.0,
            },
        )

        resp = await client.get(f"/api/equipment/filter/{filter_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["passbands"]) == 1
        assert data["passbands"][0]["line_name"] == "Oiii"

    async def test_delete_passband(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "Chroma")
        ft_id = await _get_filter_type_id(client)

        resp = await client.post(
            "/api/equipment/filter",
            json={
                "manufacturer_id": mfr["id"],
                "filter_type_id": ft_id,
                "model_name": "SII 5nm",
            },
        )
        filter_id = resp.json()["id"]

        resp = await client.post(
            f"/api/equipment/filter/{filter_id}/passband",
            json={
                "filter_id": filter_id,
                "line_name": "Sii",
                "central_wavelength_nm": 671.6,
                "bandwidth_nm": 5.0,
            },
        )
        passband_id = resp.json()["id"]

        resp = await client.delete(f"/api/equipment/filter/{filter_id}/passband/{passband_id}")
        assert resp.status_code == 200

        resp = await client.get(f"/api/equipment/filter/{filter_id}")
        assert resp.json()["passbands"] == []


# ── Mount ─────────────────────────────────────────────────────────────────────


class TestMountCRUD:
    async def test_create_and_list(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "10Micron")
        iface = await _make_connection_interface(client, "Ethernet Mount", "data")

        resp = await client.post(
            "/api/equipment/mount",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "GM1000 HPS",
                "payload_capacity_kg": 30.0,
                "goto_capable": True,
                "interface_ids": [iface["id"]],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["model_name"] == "GM1000 HPS"
        assert data["manufacturer"]["name"] == "10Micron"
        assert len(data["interfaces"]) == 1

        resp = await client.get("/api/equipment/mount")
        models = [m["model_name"] for m in resp.json()]
        assert "GM1000 HPS" in models

    async def test_soft_delete_mount(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "Skywatcher")
        resp = await client.post(
            "/api/equipment/mount",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "EQ6-R Pro",
            },
        )
        mount_id = resp.json()["id"]
        resp = await client.delete(f"/api/equipment/mount/{mount_id}")
        assert resp.status_code == 200

        resp = await client.get("/api/equipment/mount")
        models = [m["model_name"] for m in resp.json()]
        assert "EQ6-R Pro" not in models


# ── Focuser ───────────────────────────────────────────────────────────────────


class TestFocuserCRUD:
    async def test_create_and_list(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "Pegasus Astro")
        iface = await _make_connection_interface(client, "USB Focuser", "data")

        resp = await client.post(
            "/api/equipment/focuser",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "DMFC",
                "motorized": True,
                "temperature_compensation": True,
                "interface_ids": [iface["id"]],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["model_name"] == "DMFC"
        assert data["motorized"] is True
        assert data["temperature_compensation"] is True
        assert len(data["interfaces"]) == 1

        resp = await client.get("/api/equipment/focuser")
        models = [f["model_name"] for f in resp.json()]
        assert "DMFC" in models

    async def test_soft_delete_focuser(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "MoonLite")
        resp = await client.post(
            "/api/equipment/focuser",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "NightCrawler",
                "motorized": True,
            },
        )
        focuser_id = resp.json()["id"]
        resp = await client.delete(f"/api/equipment/focuser/{focuser_id}")
        assert resp.status_code == 200

        resp = await client.get("/api/equipment/focuser")
        models = [f["model_name"] for f in resp.json()]
        assert "NightCrawler" not in models


# ── Filter Wheel ──────────────────────────────────────────────────────────────


class TestFilterWheelCRUD:
    async def test_create_and_list(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "ZWO FW")
        iface = await _make_connection_interface(client, "USB FW", "data")

        resp = await client.post(
            "/api/equipment/filter-wheel",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "EFW 7x36",
                "num_positions": 7,
                "interface_ids": [iface["id"]],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["model_name"] == "EFW 7x36"
        assert data["num_positions"] == 7
        assert len(data["interfaces"]) == 1

        resp = await client.get("/api/equipment/filter-wheel")
        models = [fw["model_name"] for fw in resp.json()]
        assert "EFW 7x36" in models

    async def test_soft_delete_filter_wheel(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "Starlight Xpress FW")
        resp = await client.post(
            "/api/equipment/filter-wheel",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "SXV-7",
                "num_positions": 7,
            },
        )
        fw_id = resp.json()["id"]
        resp = await client.delete(f"/api/equipment/filter-wheel/{fw_id}")
        assert resp.status_code == 200

        resp = await client.get("/api/equipment/filter-wheel")
        models = [fw["model_name"] for fw in resp.json()]
        assert "SXV-7" not in models


# ── OAG ───────────────────────────────────────────────────────────────────────


class TestOagCRUD:
    async def test_create_and_list(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "ZWO OAG")

        resp = await client.post(
            "/api/equipment/oag",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "ZWO OAG-L",
                "prism_size_mm": 5.0,
                "back_focus_contribution_mm": 16.5,
                "weight_g": 68.0,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["model_name"] == "ZWO OAG-L"
        assert data["prism_size_mm"] == 5.0
        assert data["manufacturer"]["name"] == "ZWO OAG"

        resp = await client.get("/api/equipment/oag")
        models = [o["model_name"] for o in resp.json()]
        assert "ZWO OAG-L" in models

    async def test_soft_delete_oag(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "Agena OAG")
        resp = await client.post(
            "/api/equipment/oag",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "DeleteOAG",
            },
        )
        oag_id = resp.json()["id"]
        resp = await client.delete(f"/api/equipment/oag/{oag_id}")
        assert resp.status_code == 200

        resp = await client.get("/api/equipment/oag")
        models = [o["model_name"] for o in resp.json()]
        assert "DeleteOAG" not in models


# ── Guide Scope ───────────────────────────────────────────────────────────────


class TestGuideScopeCRUD:
    async def test_create_and_list(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "Svbony")

        resp = await client.post(
            "/api/equipment/guide-scope",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "SV165",
                "aperture_mm": 32.0,
                "focal_length_mm": 128.0,
                "weight_g": 95.0,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["model_name"] == "SV165"
        assert data["aperture_mm"] == 32.0
        assert data["manufacturer"]["name"] == "Svbony"

        resp = await client.get("/api/equipment/guide-scope")
        models = [g["model_name"] for g in resp.json()]
        assert "SV165" in models

    async def test_soft_delete_guide_scope(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "Orion GS")
        resp = await client.post(
            "/api/equipment/guide-scope",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "DeleteGS",
            },
        )
        gs_id = resp.json()["id"]
        resp = await client.delete(f"/api/equipment/guide-scope/{gs_id}")
        assert resp.status_code == 200

        resp = await client.get("/api/equipment/guide-scope")
        models = [g["model_name"] for g in resp.json()]
        assert "DeleteGS" not in models


# ── Computer ──────────────────────────────────────────────────────────────────


class TestComputerCRUD:
    async def test_create_and_list(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "Intel")

        resp = await client.post(
            "/api/equipment/computer",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "NUC11",
                "notes": "Mini PC for rig",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["model_name"] == "NUC11"
        assert data["manufacturer"]["name"] == "Intel"
        assert data["computer_type"] is None

        resp = await client.get("/api/equipment/computer")
        models = [c["model_name"] for c in resp.json()]
        assert "NUC11" in models

    async def test_soft_delete_computer(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "ASUS NUC")
        resp = await client.post(
            "/api/equipment/computer",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "PN51",
            },
        )
        comp_id = resp.json()["id"]
        resp = await client.delete(f"/api/equipment/computer/{comp_id}")
        assert resp.status_code == 200

        resp = await client.get("/api/equipment/computer")
        models = [c["model_name"] for c in resp.json()]
        assert "PN51" not in models


# ── Software ──────────────────────────────────────────────────────────────────


class TestSoftwareCRUD:
    async def test_create_and_list(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "NINA Dev")

        resp = await client.post(
            "/api/equipment/software",
            json={
                "manufacturer_id": mfr["id"],
                "name": "N.I.N.A.",
                "category": "capture",
                "website": "https://nighttime-imaging.eu",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "N.I.N.A."
        assert data["category"] == "capture"
        assert data["manufacturer"]["name"] == "NINA Dev"

        resp = await client.get("/api/equipment/software")
        names = [s["name"] for s in resp.json()]
        assert "N.I.N.A." in names

    async def test_update_software(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "OpenPHD Dev")
        resp = await client.post(
            "/api/equipment/software",
            json={
                "manufacturer_id": mfr["id"],
                "name": "PHD2",
                "category": "guiding",
            },
        )
        assert resp.status_code == 201
        sw_id = resp.json()["id"]

        resp = await client.put(
            f"/api/equipment/software/{sw_id}",
            json={"website": "https://openphdguiding.org"},
        )
        assert resp.status_code == 200
        assert resp.json()["website"] == "https://openphdguiding.org"

    async def test_soft_delete_software(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "DeleteSWMfr")
        resp = await client.post(
            "/api/equipment/software",
            json={
                "manufacturer_id": mfr["id"],
                "name": "DeleteSW",
                "category": "utility",
            },
        )
        sw_id = resp.json()["id"]
        resp = await client.delete(f"/api/equipment/software/{sw_id}")
        assert resp.status_code == 200

        resp = await client.get("/api/equipment/software")
        names = [s["name"] for s in resp.json()]
        assert "DeleteSW" not in names


# ── Filter Type (read-only) ───────────────────────────────────────────────────


class TestFilterTypeReadOnly:
    async def test_list_filter_types_seeded(self, client: AsyncClient):
        """Migration seeds filter_type; verify expected values present."""
        resp = await client.get("/api/equipment/filter-type")
        assert resp.status_code == 200
        data = resp.json()
        names = {ft["name"] for ft in data}
        assert "narrowband_single" in names
        assert "broadband_color" in names
        assert "broadband_luminance" in names

    async def test_get_filter_type_by_id(self, client: AsyncClient):
        resp = await client.get("/api/equipment/filter-type")
        ft = resp.json()[0]
        resp = await client.get(f"/api/equipment/filter-type/{ft['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == ft["id"]

    async def test_filter_type_not_found(self, client: AsyncClient):
        resp = await client.get("/api/equipment/filter-type/99999")
        assert resp.status_code == 404


# ── Lookup Tables (spot checks) ───────────────────────────────────────────────


class TestLookupTablesCRUD:
    async def test_optical_design_crud(self, client: AsyncClient):
        resp = await client.post(
            "/api/equipment/optical-design",
            json={"name": "SCT", "description": "Schmidt-Cassegrain Telescope"},
        )
        assert resp.status_code == 201
        od_id = resp.json()["id"]

        resp = await client.get(f"/api/equipment/optical-design/{od_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "SCT"

        resp = await client.put(
            f"/api/equipment/optical-design/{od_id}",
            json={"description": "Updated"},
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated"

        resp = await client.delete(f"/api/equipment/optical-design/{od_id}")
        assert resp.status_code == 200

        resp = await client.get("/api/equipment/optical-design")
        names = [o["name"] for o in resp.json()]
        assert "SCT" not in names

    async def test_mount_type_crud(self, client: AsyncClient):
        resp = await client.post(
            "/api/equipment/mount-type",
            json={"name": "GEM", "description": "German Equatorial Mount"},
        )
        assert resp.status_code == 201
        mt_id = resp.json()["id"]

        resp = await client.get(f"/api/equipment/mount-type/{mt_id}")
        assert resp.status_code == 200

        resp = await client.delete(f"/api/equipment/mount-type/{mt_id}")
        assert resp.status_code == 200

    async def test_connection_interface_crud(self, client: AsyncClient):
        resp = await client.post(
            "/api/equipment/connection-interface",
            json={"name": "USB-C", "category": "data", "notes": "USB 3.2 Gen 2"},
        )
        assert resp.status_code == 201
        ci_id = resp.json()["id"]
        assert resp.json()["category"] == "data"

        resp = await client.put(
            f"/api/equipment/connection-interface/{ci_id}",
            json={"notes": "Updated notes"},
        )
        assert resp.status_code == 200

        resp = await client.delete(f"/api/equipment/connection-interface/{ci_id}")
        assert resp.status_code == 200

    async def test_connector_size_crud(self, client: AsyncClient):
        resp = await client.post(
            "/api/equipment/connector-size",
            json={"name": "T2", "diameter_mm": 42.0},
        )
        assert resp.status_code == 201
        cs_id = resp.json()["id"]

        resp = await client.delete(f"/api/equipment/connector-size/{cs_id}")
        assert resp.status_code == 200

    async def test_filter_size_crud(self, client: AsyncClient):
        resp = await client.post(
            "/api/equipment/filter-size",
            json={"name": '2"', "description": "Two inch filter"},
        )
        assert resp.status_code == 201
        fs_id = resp.json()["id"]

        resp = await client.delete(f"/api/equipment/filter-size/{fs_id}")
        assert resp.status_code == 200

    async def test_computer_type_crud(self, client: AsyncClient):
        resp = await client.post(
            "/api/equipment/computer-type",
            json={"name": "Mini PC"},
        )
        assert resp.status_code == 201
        ct_id = resp.json()["id"]

        resp = await client.delete(f"/api/equipment/computer-type/{ct_id}")
        assert resp.status_code == 200

    async def test_duplicate_lookup_409(self, client: AsyncClient):
        await client.post("/api/equipment/optical-design", json={"name": "Refractor"})
        resp = await client.post("/api/equipment/optical-design", json={"name": "Refractor"})
        assert resp.status_code == 409
