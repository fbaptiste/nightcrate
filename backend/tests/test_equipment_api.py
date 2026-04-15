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
        mfr = await _make_manufacturer(client, "TestMfr_ZWO")
        assert mfr["name"] == "TestMfr_ZWO"
        assert mfr["active"] is True
        assert "id" in mfr

        resp = await client.get("/api/equipment/manufacturer")
        assert resp.status_code == 200
        names = [m["name"] for m in resp.json()]
        assert "TestMfr_ZWO" in names

    async def test_get_by_id(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "TestMfr_Celestron")
        resp = await client.get(f"/api/equipment/manufacturer/{mfr['id']}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "TestMfr_Celestron"

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
        mfr = await _make_manufacturer(client, "TestMfr_Sony")
        sensor = await _make_sensor(client, mfr["id"], "IMX294")
        assert sensor["model_name"] == "IMX294"
        assert sensor["manufacturer"]["name"] == "TestMfr_Sony"
        assert sensor["active"] is True

        resp = await client.get("/api/equipment/sensor")
        assert resp.status_code == 200
        models = [s["model_name"] for s in resp.json()]
        assert "IMX294" in models

    async def test_update_sensor(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "TestSensorMfr")
        sensor = await _make_sensor(client, mfr["id"], "TestSensor123")
        resp = await client.put(
            f"/api/equipment/sensor/{sensor['id']}",
            json={"notes": "Updated notes", "pixel_size_um": 4.5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["notes"] == "Updated notes"
        assert data["pixel_size_um"] == 4.5
        assert data["model_name"] == "TestSensor123"

    async def test_soft_delete_sensor(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "TestDeleteMfr")
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
        connector = await _make_connector_size(client, "TestConn_M54")

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
        assert data["connector_size"]["name"] == "TestConn_M54"
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
        c1 = await _make_connector_size(client, "TestConn_M63")
        c2 = await _make_connector_size(client, "TestConn_M68")

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
        assert data["connectors"][0]["name"] == "TestConn_M68"


# ── Filter ────────────────────────────────────────────────────────────────────


class TestFilterCRUD:
    async def test_create_and_add_passband(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "TestMfr_Antlia")
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
        mfr = await _make_manufacturer(client, "TestMfr_Optolong")
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
        mfr = await _make_manufacturer(client, "TestMount Corp")
        iface = await _make_connection_interface(client, "Ethernet Mount Test", "data")

        resp = await client.post(
            "/api/equipment/mount",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "TestMount Pro 9000",
                "payload_capacity_kg": 30.0,
                "goto_capable": True,
                "interface_ids": [iface["id"]],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["model_name"] == "TestMount Pro 9000"
        assert data["manufacturer"]["name"] == "TestMount Corp"
        assert len(data["interfaces"]) == 1

        resp = await client.get("/api/equipment/mount")
        models = [m["model_name"] for m in resp.json()]
        assert "TestMount Pro 9000" in models

    async def test_soft_delete_mount(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "TestMount Soft Delete Corp")
        resp = await client.post(
            "/api/equipment/mount",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "TestMount Soft Delete 9000",
            },
        )
        mount_id = resp.json()["id"]
        resp = await client.delete(f"/api/equipment/mount/{mount_id}")
        assert resp.status_code == 200

        resp = await client.get("/api/equipment/mount")
        models = [m["model_name"] for m in resp.json()]
        assert "TestMount Soft Delete 9000" not in models


# ── Focuser ───────────────────────────────────────────────────────────────────


class TestFocuserCRUD:
    async def test_create_and_list(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "TestMfr_Pegasus")
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
        assert data["form_factor"] is None

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
        """Seed loader populates filter_type; verify expected values present."""
        resp = await client.get("/api/equipment/filter-type")
        assert resp.status_code == 200
        data = resp.json()
        names = {ft["name"] for ft in data}
        assert "narrowband_single" in names
        assert "broadband_color" in names
        assert "luminance" in names

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
            json={"name": "TestDesign_SCT", "description": "Schmidt-Cassegrain Telescope"},
        )
        assert resp.status_code == 201
        od_id = resp.json()["id"]

        resp = await client.get(f"/api/equipment/optical-design/{od_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "TestDesign_SCT"

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
        assert "TestDesign_SCT" not in names

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

    async def test_form_factor_crud(self, client: AsyncClient):
        resp = await client.post(
            "/api/equipment/form-factor",
            json={"name": "TestFormFactor_MiniPC"},
        )
        assert resp.status_code == 201
        ct_id = resp.json()["id"]

        resp = await client.delete(f"/api/equipment/form-factor/{ct_id}")
        assert resp.status_code == 200

    async def test_focuser_type_crud(self, client: AsyncClient):
        resp = await client.post(
            "/api/equipment/focuser-type",
            json={"name": "TestFocuserType_Stepper", "notes": "Stepper motor"},
        )
        assert resp.status_code == 201
        ft_id = resp.json()["id"]
        assert resp.json()["name"] == "TestFocuserType_Stepper"

        resp = await client.put(
            f"/api/equipment/focuser-type/{ft_id}",
            json={"notes": "Updated stepper notes"},
        )
        assert resp.status_code == 200
        assert resp.json()["notes"] == "Updated stepper notes"

        resp = await client.delete(f"/api/equipment/focuser-type/{ft_id}")
        assert resp.status_code == 200

        resp = await client.get("/api/equipment/focuser-type")
        names = [ft["name"] for ft in resp.json()]
        assert "TestFocuserType_Stepper" not in names

    async def test_duplicate_lookup_409(self, client: AsyncClient):
        await client.post("/api/equipment/optical-design", json={"name": "Refractor"})
        resp = await client.post("/api/equipment/optical-design", json={"name": "Refractor"})
        assert resp.status_code == 409


# ── Filter Type CRUD ─────────────────────────────────────────────────────────


class TestFilterTypeCRUD:
    async def test_create_filter_type(self, client: AsyncClient):
        resp = await client.post(
            "/api/equipment/filter-type",
            json={
                "name": "test_custom_type",
                "display_name": "Test Custom Type",
                "description": "A test filter type",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "test_custom_type"
        assert data["display_name"] == "Test Custom Type"
        assert data["active"] is True

    async def test_update_filter_type(self, client: AsyncClient):
        resp = await client.post(
            "/api/equipment/filter-type",
            json={"name": "update_me_ft", "display_name": "Update Me"},
        )
        ft_id = resp.json()["id"]

        resp = await client.put(
            f"/api/equipment/filter-type/{ft_id}",
            json={"display_name": "Updated Display"},
        )
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Updated Display"

    async def test_soft_delete_filter_type(self, client: AsyncClient):
        resp = await client.post(
            "/api/equipment/filter-type",
            json={"name": "delete_me_ft", "display_name": "Delete Me"},
        )
        ft_id = resp.json()["id"]

        resp = await client.delete(f"/api/equipment/filter-type/{ft_id}")
        assert resp.status_code == 200

        resp = await client.get("/api/equipment/filter-type")
        names = [ft["name"] for ft in resp.json()]
        assert "delete_me_ft" not in names

        resp = await client.get("/api/equipment/filter-type?include_retired=true")
        names = [ft["name"] for ft in resp.json()]
        assert "delete_me_ft" in names

    async def test_duplicate_filter_type_409(self, client: AsyncClient):
        await client.post(
            "/api/equipment/filter-type",
            json={"name": "dup_ft", "display_name": "Dup"},
        )
        resp = await client.post(
            "/api/equipment/filter-type",
            json={"name": "dup_ft", "display_name": "Dup Again"},
        )
        assert resp.status_code == 409


# ── Filter Size Options ──────────────────────────────────────────────────────


class TestFilterSizeOptions:
    async def test_create_and_delete_size_option(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "SizeOptMfr")
        ft_id = await _get_filter_type_id(client)

        # Create a filter
        resp = await client.post(
            "/api/equipment/filter",
            json={
                "manufacturer_id": mfr["id"],
                "filter_type_id": ft_id,
                "model_name": "SizeOptFilter",
            },
        )
        filter_id = resp.json()["id"]

        # Create a filter_size
        resp = await client.post(
            "/api/equipment/filter-size",
            json={"name": "TestSizeOpt_36mm"},
        )
        fs_id = resp.json()["id"]

        # Create size option
        resp = await client.post(
            f"/api/equipment/filter/{filter_id}/size-option",
            json={
                "filter_id": filter_id,
                "filter_size_id": fs_id,
                "mounted_thickness_mm": 5.0,
            },
        )
        assert resp.status_code == 201
        so = resp.json()
        assert so["filter_size"]["name"] == "TestSizeOpt_36mm"
        assert so["mounted_thickness_mm"] == 5.0
        option_id = so["id"]

        # Verify it appears in the filter response
        resp = await client.get(f"/api/equipment/filter/{filter_id}")
        assert len(resp.json()["size_options"]) == 1

        # Delete size option
        resp = await client.delete(f"/api/equipment/filter/{filter_id}/size-option/{option_id}")
        assert resp.status_code == 200

        # Verify gone from filter response
        resp = await client.get(f"/api/equipment/filter/{filter_id}")
        assert resp.json()["size_options"] == []

    async def test_update_size_option(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "SizeOptUpdateMfr")
        ft_id = await _get_filter_type_id(client)

        resp = await client.post(
            "/api/equipment/filter",
            json={
                "manufacturer_id": mfr["id"],
                "filter_type_id": ft_id,
                "model_name": "SizeOptUpdateFilter",
            },
        )
        filter_id = resp.json()["id"]

        resp = await client.post(
            "/api/equipment/filter-size",
            json={"name": "TestSizeOpt_50mm"},
        )
        fs_id = resp.json()["id"]

        resp = await client.post(
            f"/api/equipment/filter/{filter_id}/size-option",
            json={"filter_id": filter_id, "filter_size_id": fs_id},
        )
        option_id = resp.json()["id"]

        resp = await client.put(
            f"/api/equipment/filter/{filter_id}/size-option/{option_id}",
            json={"mounted_thickness_mm": 7.5},
        )
        assert resp.status_code == 200
        assert resp.json()["mounted_thickness_mm"] == 7.5

    async def test_size_option_not_found_404(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "SizeOpt404Mfr")
        ft_id = await _get_filter_type_id(client)

        resp = await client.post(
            "/api/equipment/filter",
            json={
                "manufacturer_id": mfr["id"],
                "filter_type_id": ft_id,
                "model_name": "SizeOpt404Filter",
            },
        )
        filter_id = resp.json()["id"]

        resp = await client.put(
            f"/api/equipment/filter/{filter_id}/size-option/99999",
            json={"mounted_thickness_mm": 1.0},
        )
        assert resp.status_code == 404

        resp = await client.delete(f"/api/equipment/filter/{filter_id}/size-option/99999")
        assert resp.status_code == 404


# ── Restore endpoint ─────────────────────────────────────────────────────────


class TestRestore:
    async def test_restore_soft_deleted_manufacturer(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "RestoreMe")
        resp = await client.delete(f"/api/equipment/manufacturer/{mfr['id']}")
        assert resp.status_code == 200

        # Verify it is retired
        resp = await client.get("/api/equipment/manufacturer")
        names = [m["name"] for m in resp.json()]
        assert "RestoreMe" not in names

        # Restore
        resp = await client.post(f"/api/equipment/restore/manufacturer/{mfr['id']}")
        assert resp.status_code == 200

        # Now visible again
        resp = await client.get("/api/equipment/manufacturer")
        names = [m["name"] for m in resp.json()]
        assert "RestoreMe" in names

    async def test_restore_unknown_table_400(self, client: AsyncClient):
        resp = await client.post("/api/equipment/restore/nonexistent_table/1")
        assert resp.status_code == 400


# ── Duplicate-name 409 on updates (lookup tables) ───────────────────────────


class TestLookupUpdateDuplicate409:
    async def test_manufacturer_update_duplicate(self, client: AsyncClient):
        m1 = await _make_manufacturer(client, "MfrDupA")
        await _make_manufacturer(client, "MfrDupB")
        resp = await client.put(f"/api/equipment/manufacturer/{m1['id']}", json={"name": "MfrDupB"})
        assert resp.status_code == 409

    async def test_optical_design_update_duplicate(self, client: AsyncClient):
        r1 = await client.post("/api/equipment/optical-design", json={"name": "OD_DupA"})
        await client.post("/api/equipment/optical-design", json={"name": "OD_DupB"})
        resp = await client.put(
            f"/api/equipment/optical-design/{r1.json()['id']}",
            json={"name": "OD_DupB"},
        )
        assert resp.status_code == 409

    async def test_mount_type_update_duplicate(self, client: AsyncClient):
        r1 = await client.post("/api/equipment/mount-type", json={"name": "MT_DupA"})
        await client.post("/api/equipment/mount-type", json={"name": "MT_DupB"})
        resp = await client.put(
            f"/api/equipment/mount-type/{r1.json()['id']}",
            json={"name": "MT_DupB"},
        )
        assert resp.status_code == 409

    async def test_connection_interface_update_duplicate(self, client: AsyncClient):
        r1 = await client.post(
            "/api/equipment/connection-interface",
            json={"name": "CI_DupA", "category": "data"},
        )
        await client.post(
            "/api/equipment/connection-interface",
            json={"name": "CI_DupB", "category": "data"},
        )
        resp = await client.put(
            f"/api/equipment/connection-interface/{r1.json()['id']}",
            json={"name": "CI_DupB"},
        )
        assert resp.status_code == 409

    async def test_connector_size_update_duplicate(self, client: AsyncClient):
        r1 = await client.post(
            "/api/equipment/connector-size", json={"name": "CS_DupA", "diameter_mm": 1.0}
        )
        await client.post(
            "/api/equipment/connector-size", json={"name": "CS_DupB", "diameter_mm": 2.0}
        )
        resp = await client.put(
            f"/api/equipment/connector-size/{r1.json()['id']}",
            json={"name": "CS_DupB"},
        )
        assert resp.status_code == 409

    async def test_filter_size_update_duplicate(self, client: AsyncClient):
        r1 = await client.post("/api/equipment/filter-size", json={"name": "FS_DupA"})
        await client.post("/api/equipment/filter-size", json={"name": "FS_DupB"})
        resp = await client.put(
            f"/api/equipment/filter-size/{r1.json()['id']}",
            json={"name": "FS_DupB"},
        )
        assert resp.status_code == 409

    async def test_form_factor_update_duplicate(self, client: AsyncClient):
        r1 = await client.post("/api/equipment/form-factor", json={"name": "FF_DupA"})
        await client.post("/api/equipment/form-factor", json={"name": "FF_DupB"})
        resp = await client.put(
            f"/api/equipment/form-factor/{r1.json()['id']}",
            json={"name": "FF_DupB"},
        )
        assert resp.status_code == 409

    async def test_focuser_type_update_duplicate(self, client: AsyncClient):
        r1 = await client.post("/api/equipment/focuser-type", json={"name": "FT_DupA"})
        await client.post("/api/equipment/focuser-type", json={"name": "FT_DupB"})
        resp = await client.put(
            f"/api/equipment/focuser-type/{r1.json()['id']}",
            json={"name": "FT_DupB"},
        )
        assert resp.status_code == 409

    async def test_filter_type_update_duplicate(self, client: AsyncClient):
        r1 = await client.post(
            "/api/equipment/filter-type",
            json={"name": "FTy_DupA", "display_name": "A"},
        )
        await client.post(
            "/api/equipment/filter-type",
            json={"name": "FTy_DupB", "display_name": "B"},
        )
        resp = await client.put(
            f"/api/equipment/filter-type/{r1.json()['id']}",
            json={"name": "FTy_DupB"},
        )
        assert resp.status_code == 409


# ── Lookup table create duplicate 409 ───────────────────────────────────────


class TestLookupCreateDuplicate409:
    async def test_mount_type_create_duplicate(self, client: AsyncClient):
        await client.post("/api/equipment/mount-type", json={"name": "DupMT"})
        resp = await client.post("/api/equipment/mount-type", json={"name": "DupMT"})
        assert resp.status_code == 409

    async def test_connection_interface_create_duplicate(self, client: AsyncClient):
        await client.post(
            "/api/equipment/connection-interface",
            json={"name": "DupCI", "category": "data"},
        )
        resp = await client.post(
            "/api/equipment/connection-interface",
            json={"name": "DupCI", "category": "data"},
        )
        assert resp.status_code == 409

    async def test_connector_size_create_duplicate(self, client: AsyncClient):
        await client.post(
            "/api/equipment/connector-size", json={"name": "DupCS", "diameter_mm": 1.0}
        )
        resp = await client.post(
            "/api/equipment/connector-size", json={"name": "DupCS", "diameter_mm": 1.0}
        )
        assert resp.status_code == 409

    async def test_filter_size_create_duplicate(self, client: AsyncClient):
        await client.post("/api/equipment/filter-size", json={"name": "DupFS"})
        resp = await client.post("/api/equipment/filter-size", json={"name": "DupFS"})
        assert resp.status_code == 409

    async def test_form_factor_create_duplicate(self, client: AsyncClient):
        await client.post("/api/equipment/form-factor", json={"name": "DupFF"})
        resp = await client.post("/api/equipment/form-factor", json={"name": "DupFF"})
        assert resp.status_code == 409

    async def test_focuser_type_create_duplicate(self, client: AsyncClient):
        await client.post("/api/equipment/focuser-type", json={"name": "DupFocT"})
        resp = await client.post("/api/equipment/focuser-type", json={"name": "DupFocT"})
        assert resp.status_code == 409


# ── Equipment create/update duplicate 409 ───────────────────────────────────


class TestEquipmentDuplicate409:
    async def test_sensor_create_duplicate(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "SensorDupMfr")
        await _make_sensor(client, mfr["id"], "DupSensor")
        resp = await client.post(
            "/api/equipment/sensor",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "DupSensor",
                "sensor_type": "mono",
                "pixel_size_um": 3.76,
                "resolution_x": 6248,
                "resolution_y": 4176,
            },
        )
        assert resp.status_code == 409

    async def test_sensor_update_duplicate(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "SensorUpdDupMfr")
        await _make_sensor(client, mfr["id"], "SensorA")
        s2 = await _make_sensor(client, mfr["id"], "SensorB")
        resp = await client.put(
            f"/api/equipment/sensor/{s2['id']}",
            json={"model_name": "SensorA"},
        )
        assert resp.status_code == 409

    async def test_camera_create_duplicate(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "CamDupMfr")
        sensor = await _make_sensor(client, mfr["id"], "CamDupSensor")
        await client.post(
            "/api/equipment/camera",
            json={
                "manufacturer_id": mfr["id"],
                "sensor_id": sensor["id"],
                "model_name": "DupCam",
            },
        )
        resp = await client.post(
            "/api/equipment/camera",
            json={
                "manufacturer_id": mfr["id"],
                "sensor_id": sensor["id"],
                "model_name": "DupCam",
            },
        )
        assert resp.status_code == 409

    async def test_camera_update_duplicate(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "CamUpdDupMfr")
        sensor = await _make_sensor(client, mfr["id"], "CamUpdDupSensor")
        await client.post(
            "/api/equipment/camera",
            json={
                "manufacturer_id": mfr["id"],
                "sensor_id": sensor["id"],
                "model_name": "CamA",
            },
        )
        r2 = await client.post(
            "/api/equipment/camera",
            json={
                "manufacturer_id": mfr["id"],
                "sensor_id": sensor["id"],
                "model_name": "CamB",
            },
        )
        resp = await client.put(
            f"/api/equipment/camera/{r2.json()['id']}",
            json={"model_name": "CamA"},
        )
        assert resp.status_code == 409

    async def test_telescope_create_duplicate(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "ScopeDupMfr")
        await client.post(
            "/api/equipment/telescope",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "DupScope",
                "aperture_mm": 200.0,
            },
        )
        resp = await client.post(
            "/api/equipment/telescope",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "DupScope",
                "aperture_mm": 200.0,
            },
        )
        assert resp.status_code == 409

    async def test_telescope_update_duplicate(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "ScopeUpdDupMfr")
        await client.post(
            "/api/equipment/telescope",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "ScopeA",
                "aperture_mm": 200.0,
            },
        )
        r2 = await client.post(
            "/api/equipment/telescope",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "ScopeB",
                "aperture_mm": 200.0,
            },
        )
        resp = await client.put(
            f"/api/equipment/telescope/{r2.json()['id']}",
            json={"model_name": "ScopeA"},
        )
        assert resp.status_code == 409

    async def test_filter_create_duplicate(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "FilterDupMfr")
        ft_id = await _get_filter_type_id(client)
        await client.post(
            "/api/equipment/filter",
            json={
                "manufacturer_id": mfr["id"],
                "filter_type_id": ft_id,
                "model_name": "DupFilter",
            },
        )
        resp = await client.post(
            "/api/equipment/filter",
            json={
                "manufacturer_id": mfr["id"],
                "filter_type_id": ft_id,
                "model_name": "DupFilter",
            },
        )
        assert resp.status_code == 409

    async def test_filter_update_duplicate(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "FilterUpdDupMfr")
        ft_id = await _get_filter_type_id(client)
        await client.post(
            "/api/equipment/filter",
            json={
                "manufacturer_id": mfr["id"],
                "filter_type_id": ft_id,
                "model_name": "FilterA",
            },
        )
        r2 = await client.post(
            "/api/equipment/filter",
            json={
                "manufacturer_id": mfr["id"],
                "filter_type_id": ft_id,
                "model_name": "FilterB",
            },
        )
        resp = await client.put(
            f"/api/equipment/filter/{r2.json()['id']}",
            json={"model_name": "FilterA"},
        )
        assert resp.status_code == 409

    async def test_mount_create_duplicate(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "MountDupMfr")
        await client.post(
            "/api/equipment/mount",
            json={"manufacturer_id": mfr["id"], "model_name": "DupMount"},
        )
        resp = await client.post(
            "/api/equipment/mount",
            json={"manufacturer_id": mfr["id"], "model_name": "DupMount"},
        )
        assert resp.status_code == 409

    async def test_mount_update_duplicate(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "MountUpdDupMfr")
        await client.post(
            "/api/equipment/mount",
            json={"manufacturer_id": mfr["id"], "model_name": "MountA"},
        )
        r2 = await client.post(
            "/api/equipment/mount",
            json={"manufacturer_id": mfr["id"], "model_name": "MountB"},
        )
        resp = await client.put(
            f"/api/equipment/mount/{r2.json()['id']}",
            json={"model_name": "MountA"},
        )
        assert resp.status_code == 409

    async def test_focuser_create_duplicate(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "FocuserDupMfr")
        await client.post(
            "/api/equipment/focuser",
            json={"manufacturer_id": mfr["id"], "model_name": "DupFocuser"},
        )
        resp = await client.post(
            "/api/equipment/focuser",
            json={"manufacturer_id": mfr["id"], "model_name": "DupFocuser"},
        )
        assert resp.status_code == 409

    async def test_focuser_update_duplicate(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "FocuserUpdDupMfr")
        await client.post(
            "/api/equipment/focuser",
            json={"manufacturer_id": mfr["id"], "model_name": "FocuserA"},
        )
        r2 = await client.post(
            "/api/equipment/focuser",
            json={"manufacturer_id": mfr["id"], "model_name": "FocuserB"},
        )
        resp = await client.put(
            f"/api/equipment/focuser/{r2.json()['id']}",
            json={"model_name": "FocuserA"},
        )
        assert resp.status_code == 409

    async def test_filter_wheel_create_duplicate(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "FWDupMfr")
        await client.post(
            "/api/equipment/filter-wheel",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "DupFW",
                "num_positions": 5,
            },
        )
        resp = await client.post(
            "/api/equipment/filter-wheel",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "DupFW",
                "num_positions": 5,
            },
        )
        assert resp.status_code == 409

    async def test_filter_wheel_update_duplicate(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "FWUpdDupMfr")
        await client.post(
            "/api/equipment/filter-wheel",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "FWA",
                "num_positions": 5,
            },
        )
        r2 = await client.post(
            "/api/equipment/filter-wheel",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "FWB",
                "num_positions": 5,
            },
        )
        resp = await client.put(
            f"/api/equipment/filter-wheel/{r2.json()['id']}",
            json={"model_name": "FWA"},
        )
        assert resp.status_code == 409

    async def test_oag_create_duplicate(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "OAGDupMfr")
        await client.post(
            "/api/equipment/oag",
            json={"manufacturer_id": mfr["id"], "model_name": "DupOAG"},
        )
        resp = await client.post(
            "/api/equipment/oag",
            json={"manufacturer_id": mfr["id"], "model_name": "DupOAG"},
        )
        assert resp.status_code == 409

    async def test_oag_update_duplicate(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "OAGUpdDupMfr")
        await client.post(
            "/api/equipment/oag",
            json={"manufacturer_id": mfr["id"], "model_name": "OAGA"},
        )
        r2 = await client.post(
            "/api/equipment/oag",
            json={"manufacturer_id": mfr["id"], "model_name": "OAGB"},
        )
        resp = await client.put(
            f"/api/equipment/oag/{r2.json()['id']}",
            json={"model_name": "OAGA"},
        )
        assert resp.status_code == 409

    async def test_guide_scope_create_duplicate(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "GSDupMfr")
        await client.post(
            "/api/equipment/guide-scope",
            json={"manufacturer_id": mfr["id"], "model_name": "DupGS"},
        )
        resp = await client.post(
            "/api/equipment/guide-scope",
            json={"manufacturer_id": mfr["id"], "model_name": "DupGS"},
        )
        assert resp.status_code == 409

    async def test_guide_scope_update_duplicate(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "GSUpdDupMfr")
        await client.post(
            "/api/equipment/guide-scope",
            json={"manufacturer_id": mfr["id"], "model_name": "GSA"},
        )
        r2 = await client.post(
            "/api/equipment/guide-scope",
            json={"manufacturer_id": mfr["id"], "model_name": "GSB"},
        )
        resp = await client.put(
            f"/api/equipment/guide-scope/{r2.json()['id']}",
            json={"model_name": "GSA"},
        )
        assert resp.status_code == 409

    async def test_computer_create_duplicate(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "CompDupMfr")
        await client.post(
            "/api/equipment/computer",
            json={"manufacturer_id": mfr["id"], "model_name": "DupComp"},
        )
        resp = await client.post(
            "/api/equipment/computer",
            json={"manufacturer_id": mfr["id"], "model_name": "DupComp"},
        )
        assert resp.status_code == 409

    async def test_computer_update_duplicate(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "CompUpdDupMfr")
        await client.post(
            "/api/equipment/computer",
            json={"manufacturer_id": mfr["id"], "model_name": "CompA"},
        )
        r2 = await client.post(
            "/api/equipment/computer",
            json={"manufacturer_id": mfr["id"], "model_name": "CompB"},
        )
        resp = await client.put(
            f"/api/equipment/computer/{r2.json()['id']}",
            json={"model_name": "CompA"},
        )
        assert resp.status_code == 409

    async def test_software_create_duplicate(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "SWDupMfr")
        await client.post(
            "/api/equipment/software",
            json={
                "manufacturer_id": mfr["id"],
                "name": "DupSW",
                "category": "capture",
            },
        )
        resp = await client.post(
            "/api/equipment/software",
            json={
                "manufacturer_id": mfr["id"],
                "name": "DupSW",
                "category": "capture",
            },
        )
        assert resp.status_code == 409

    async def test_software_update_duplicate(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "SWUpdDupMfr")
        await client.post(
            "/api/equipment/software",
            json={
                "manufacturer_id": mfr["id"],
                "name": "SWA",
                "category": "capture",
            },
        )
        r2 = await client.post(
            "/api/equipment/software",
            json={
                "manufacturer_id": mfr["id"],
                "name": "SWB",
                "category": "capture",
            },
        )
        resp = await client.put(
            f"/api/equipment/software/{r2.json()['id']}",
            json={"name": "SWA"},
        )
        assert resp.status_code == 409


# ── Software CHECK constraint ───────────────────────────────────────────────


class TestSoftwareCategoryCheck:
    async def test_create_invalid_category_422(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "SWCheckMfr")
        resp = await client.post(
            "/api/equipment/software",
            json={
                "manufacturer_id": mfr["id"],
                "name": "BadCatSW",
                "category": "totally_invalid_category",
            },
        )
        assert resp.status_code == 422

    async def test_update_invalid_category_422(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "SWCheckUpdMfr")
        resp = await client.post(
            "/api/equipment/software",
            json={
                "manufacturer_id": mfr["id"],
                "name": "GoodCatSW",
                "category": "capture",
            },
        )
        sw_id = resp.json()["id"]
        resp = await client.put(
            f"/api/equipment/software/{sw_id}",
            json={"category": "totally_invalid_category"},
        )
        assert resp.status_code == 422


# ── Passband CHECK constraint ───────────────────────────────────────────────


class TestPassbandCheck:
    async def test_create_passband_invalid_line_name(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "PBCheckMfr")
        ft_id = await _get_filter_type_id(client)
        resp = await client.post(
            "/api/equipment/filter",
            json={
                "manufacturer_id": mfr["id"],
                "filter_type_id": ft_id,
                "model_name": "PBCheckFilter",
            },
        )
        filter_id = resp.json()["id"]
        resp = await client.post(
            f"/api/equipment/filter/{filter_id}/passband",
            json={
                "filter_id": filter_id,
                "line_name": "INVALID_LINE",
                "central_wavelength_nm": 500.0,
                "bandwidth_nm": 3.0,
            },
        )
        assert resp.status_code == 422

    async def test_update_passband_invalid_line_name(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "PBCheckUpdMfr")
        ft_id = await _get_filter_type_id(client)
        resp = await client.post(
            "/api/equipment/filter",
            json={
                "manufacturer_id": mfr["id"],
                "filter_type_id": ft_id,
                "model_name": "PBCheckUpdFilter",
            },
        )
        filter_id = resp.json()["id"]
        resp = await client.post(
            f"/api/equipment/filter/{filter_id}/passband",
            json={
                "filter_id": filter_id,
                "line_name": "Ha",
                "central_wavelength_nm": 656.28,
                "bandwidth_nm": 3.0,
            },
        )
        pb_id = resp.json()["id"]
        resp = await client.put(
            f"/api/equipment/filter/{filter_id}/passband/{pb_id}",
            json={"line_name": "INVALID_LINE"},
        )
        assert resp.status_code == 422


# ── Telescope configuration update duplicate ────────────────────────────────


class TestTelescopeConfigDuplicates:
    async def test_update_config_to_native_409(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "CfgDupMfr")
        resp = await client.post(
            "/api/equipment/telescope",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "CfgDupScope",
                "aperture_mm": 200.0,
            },
        )
        telescope_id = resp.json()["id"]

        # Create native config
        await client.post(
            f"/api/equipment/telescope/{telescope_id}/configuration",
            json={
                "telescope_id": telescope_id,
                "config_name": "Native",
                "effective_focal_length_mm": 1000.0,
                "effective_focal_ratio": 5.0,
                "reduction_factor": 1.0,
                "is_native": True,
            },
        )
        # Create non-native config
        resp = await client.post(
            f"/api/equipment/telescope/{telescope_id}/configuration",
            json={
                "telescope_id": telescope_id,
                "config_name": "Reducer",
                "effective_focal_length_mm": 800.0,
                "effective_focal_ratio": 4.0,
                "reduction_factor": 0.8,
                "is_native": False,
            },
        )
        config_id = resp.json()["id"]

        # Try to update non-native to native -- should 409
        resp = await client.put(
            f"/api/equipment/telescope/{telescope_id}/configuration/{config_id}",
            json={"is_native": True},
        )
        assert resp.status_code == 409

    async def test_update_config_duplicate_name_409(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "CfgNameDupMfr")
        resp = await client.post(
            "/api/equipment/telescope",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "CfgNameDupScope",
                "aperture_mm": 200.0,
            },
        )
        telescope_id = resp.json()["id"]

        await client.post(
            f"/api/equipment/telescope/{telescope_id}/configuration",
            json={
                "telescope_id": telescope_id,
                "config_name": "ConfigA",
                "effective_focal_length_mm": 1000.0,
                "effective_focal_ratio": 5.0,
                "reduction_factor": 1.0,
                "is_native": False,
            },
        )
        resp = await client.post(
            f"/api/equipment/telescope/{telescope_id}/configuration",
            json={
                "telescope_id": telescope_id,
                "config_name": "ConfigB",
                "effective_focal_length_mm": 800.0,
                "effective_focal_ratio": 4.0,
                "reduction_factor": 0.8,
                "is_native": False,
            },
        )
        config_id = resp.json()["id"]

        resp = await client.put(
            f"/api/equipment/telescope/{telescope_id}/configuration/{config_id}",
            json={"config_name": "ConfigA"},
        )
        assert resp.status_code == 409


# ── Filter size option duplicate 409 ────────────────────────────────────────


class TestFilterSizeOptionDuplicate:
    async def test_create_duplicate_size_option_409(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "SODupMfr")
        ft_id = await _get_filter_type_id(client)
        resp = await client.post(
            "/api/equipment/filter",
            json={
                "manufacturer_id": mfr["id"],
                "filter_type_id": ft_id,
                "model_name": "SODupFilter",
            },
        )
        filter_id = resp.json()["id"]
        resp = await client.post("/api/equipment/filter-size", json={"name": "SODup_36mm"})
        fs_id = resp.json()["id"]

        await client.post(
            f"/api/equipment/filter/{filter_id}/size-option",
            json={"filter_id": filter_id, "filter_size_id": fs_id},
        )
        resp = await client.post(
            f"/api/equipment/filter/{filter_id}/size-option",
            json={"filter_id": filter_id, "filter_size_id": fs_id},
        )
        assert resp.status_code == 409

    async def test_update_size_option_duplicate_409(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "SOUpdDupMfr")
        ft_id = await _get_filter_type_id(client)
        resp = await client.post(
            "/api/equipment/filter",
            json={
                "manufacturer_id": mfr["id"],
                "filter_type_id": ft_id,
                "model_name": "SOUpdDupFilter",
            },
        )
        filter_id = resp.json()["id"]
        r1 = await client.post("/api/equipment/filter-size", json={"name": "SOUpdDup_A"})
        r2 = await client.post("/api/equipment/filter-size", json={"name": "SOUpdDup_B"})

        await client.post(
            f"/api/equipment/filter/{filter_id}/size-option",
            json={"filter_id": filter_id, "filter_size_id": r1.json()["id"]},
        )
        resp = await client.post(
            f"/api/equipment/filter/{filter_id}/size-option",
            json={"filter_id": filter_id, "filter_size_id": r2.json()["id"]},
        )
        option_id = resp.json()["id"]

        resp = await client.put(
            f"/api/equipment/filter/{filter_id}/size-option/{option_id}",
            json={"filter_size_id": r1.json()["id"]},
        )
        assert resp.status_code == 409

    async def test_restore_unknown_table_400(self, client: AsyncClient):
        resp = await client.post("/api/equipment/restore/nonexistent_table/1")
        assert resp.status_code == 400

    async def test_restore_nonexistent_item_404(self, client: AsyncClient):
        resp = await client.post("/api/equipment/restore/manufacturer/99999")
        assert resp.status_code == 404


# ── 404 tests for equipment types ────────────────────────────────────────────


class TestEquipment404:
    async def test_camera_not_found(self, client: AsyncClient):
        resp = await client.get("/api/equipment/camera/99999")
        assert resp.status_code == 404

        resp = await client.put("/api/equipment/camera/99999", json={"model_name": "X"})
        assert resp.status_code == 404

        resp = await client.delete("/api/equipment/camera/99999")
        assert resp.status_code == 404

    async def test_telescope_not_found(self, client: AsyncClient):
        resp = await client.get("/api/equipment/telescope/99999")
        assert resp.status_code == 404

        resp = await client.delete("/api/equipment/telescope/99999")
        assert resp.status_code == 404

    async def test_filter_not_found(self, client: AsyncClient):
        resp = await client.get("/api/equipment/filter/99999")
        assert resp.status_code == 404

        resp = await client.delete("/api/equipment/filter/99999")
        assert resp.status_code == 404

    async def test_sensor_not_found(self, client: AsyncClient):
        resp = await client.get("/api/equipment/sensor/99999")
        assert resp.status_code == 404

    async def test_mount_not_found(self, client: AsyncClient):
        resp = await client.get("/api/equipment/mount/99999")
        assert resp.status_code == 404

    async def test_focuser_not_found(self, client: AsyncClient):
        resp = await client.get("/api/equipment/focuser/99999")
        assert resp.status_code == 404

    async def test_filter_wheel_not_found(self, client: AsyncClient):
        resp = await client.get("/api/equipment/filter-wheel/99999")
        assert resp.status_code == 404

    async def test_oag_not_found(self, client: AsyncClient):
        resp = await client.get("/api/equipment/oag/99999")
        assert resp.status_code == 404

    async def test_guide_scope_not_found(self, client: AsyncClient):
        resp = await client.get("/api/equipment/guide-scope/99999")
        assert resp.status_code == 404

    async def test_computer_not_found(self, client: AsyncClient):
        resp = await client.get("/api/equipment/computer/99999")
        assert resp.status_code == 404

    async def test_software_not_found(self, client: AsyncClient):
        resp = await client.get("/api/equipment/software/99999")
        assert resp.status_code == 404

    async def test_telescope_config_not_found(self, client: AsyncClient):
        """Config endpoints return 404 when telescope or config doesn't exist."""
        # Telescope doesn't exist
        resp = await client.post(
            "/api/equipment/telescope/99999/configuration",
            json={
                "telescope_id": 99999,
                "config_name": "X",
                "effective_focal_length_mm": 100,
                "effective_focal_ratio": 5,
                "reduction_factor": 1.0,
                "is_native": False,
            },
        )
        assert resp.status_code == 404

    async def test_passband_not_found(self, client: AsyncClient):
        """Passband endpoints return 404 when filter or passband doesn't exist."""
        mfr = await _make_manufacturer(client, "PB404Mfr")
        ft_id = await _get_filter_type_id(client)

        resp = await client.post(
            "/api/equipment/filter",
            json={
                "manufacturer_id": mfr["id"],
                "filter_type_id": ft_id,
                "model_name": "PB404Filter",
            },
        )
        filter_id = resp.json()["id"]

        # Passband doesn't exist
        resp = await client.put(
            f"/api/equipment/filter/{filter_id}/passband/99999",
            json={"bandwidth_nm": 5.0},
        )
        assert resp.status_code == 404

        resp = await client.delete(f"/api/equipment/filter/{filter_id}/passband/99999")
        assert resp.status_code == 404


# ── Update passband ──────────────────────────────────────────────────────────


class TestUpdatePassband:
    async def test_update_passband_fields(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "UpdatePBMfr")
        ft_id = await _get_filter_type_id(client)

        resp = await client.post(
            "/api/equipment/filter",
            json={
                "manufacturer_id": mfr["id"],
                "filter_type_id": ft_id,
                "model_name": "UpdatePBFilter",
            },
        )
        filter_id = resp.json()["id"]

        resp = await client.post(
            f"/api/equipment/filter/{filter_id}/passband",
            json={
                "filter_id": filter_id,
                "line_name": "Ha",
                "central_wavelength_nm": 656.28,
                "bandwidth_nm": 3.0,
            },
        )
        pb_id = resp.json()["id"]

        resp = await client.put(
            f"/api/equipment/filter/{filter_id}/passband/{pb_id}",
            json={"bandwidth_nm": 5.0, "peak_transmission_pct": 95.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["bandwidth_nm"] == 5.0
        assert data["peak_transmission_pct"] == 95.0
        # Unchanged fields preserved
        assert data["line_name"] == "Ha"
        assert data["central_wavelength_nm"] == 656.28


# ── Update telescope configuration ───────────────────────────────────────────


class TestUpdateConfiguration:
    async def test_update_config_fields(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "UpdateCfgMfr")
        resp = await client.post(
            "/api/equipment/telescope",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "UpdateCfgScope",
                "aperture_mm": 150.0,
            },
        )
        telescope_id = resp.json()["id"]

        resp = await client.post(
            f"/api/equipment/telescope/{telescope_id}/configuration",
            json={
                "telescope_id": telescope_id,
                "config_name": "With Reducer",
                "effective_focal_length_mm": 750.0,
                "effective_focal_ratio": 5.0,
                "reduction_factor": 0.75,
                "is_native": False,
            },
        )
        config_id = resp.json()["id"]

        resp = await client.put(
            f"/api/equipment/telescope/{telescope_id}/configuration/{config_id}",
            json={"effective_focal_length_mm": 780.0},
        )
        assert resp.status_code == 200
        assert resp.json()["effective_focal_length_mm"] == 780.0
        assert resp.json()["config_name"] == "With Reducer"

    async def test_update_config_not_found_404(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "UpdateCfg404Mfr")
        resp = await client.post(
            "/api/equipment/telescope",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "UpdateCfg404Scope",
                "aperture_mm": 100.0,
            },
        )
        telescope_id = resp.json()["id"]

        resp = await client.put(
            f"/api/equipment/telescope/{telescope_id}/configuration/99999",
            json={"config_name": "X"},
        )
        assert resp.status_code == 404


# ── Equipment update tests ───────────────────────────────────────────────────


class TestEquipmentUpdates:
    async def test_update_mount(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "UpdateMountMfr")
        resp = await client.post(
            "/api/equipment/mount",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "UpdateMount",
                "payload_capacity_kg": 20.0,
            },
        )
        mount_id = resp.json()["id"]

        resp = await client.put(
            f"/api/equipment/mount/{mount_id}",
            json={"payload_capacity_kg": 25.0, "goto_capable": True},
        )
        assert resp.status_code == 200
        assert resp.json()["payload_capacity_kg"] == 25.0
        assert resp.json()["goto_capable"] is True

    async def test_update_focuser(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "UpdateFocuserMfr")
        resp = await client.post(
            "/api/equipment/focuser",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "UpdateFocuser",
                "motorized": False,
            },
        )
        focuser_id = resp.json()["id"]

        resp = await client.put(
            f"/api/equipment/focuser/{focuser_id}",
            json={"motorized": True, "total_steps": 10000},
        )
        assert resp.status_code == 200
        assert resp.json()["motorized"] is True
        assert resp.json()["total_steps"] == 10000

    async def test_update_filter_wheel(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "UpdateFWMfr")
        resp = await client.post(
            "/api/equipment/filter-wheel",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "UpdateFW",
                "num_positions": 5,
            },
        )
        fw_id = resp.json()["id"]

        resp = await client.put(
            f"/api/equipment/filter-wheel/{fw_id}",
            json={"num_positions": 7},
        )
        assert resp.status_code == 200
        assert resp.json()["num_positions"] == 7

    async def test_update_oag(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "UpdateOagMfr")
        resp = await client.post(
            "/api/equipment/oag",
            json={"manufacturer_id": mfr["id"], "model_name": "UpdateOAG"},
        )
        oag_id = resp.json()["id"]

        resp = await client.put(
            f"/api/equipment/oag/{oag_id}",
            json={"prism_size_mm": 8.0, "weight_g": 120.0},
        )
        assert resp.status_code == 200
        assert resp.json()["prism_size_mm"] == 8.0
        assert resp.json()["weight_g"] == 120.0

    async def test_update_guide_scope(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "UpdateGSMfr")
        resp = await client.post(
            "/api/equipment/guide-scope",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "UpdateGS",
                "aperture_mm": 50.0,
            },
        )
        gs_id = resp.json()["id"]

        resp = await client.put(
            f"/api/equipment/guide-scope/{gs_id}",
            json={"focal_length_mm": 200.0},
        )
        assert resp.status_code == 200
        assert resp.json()["focal_length_mm"] == 200.0

    async def test_update_computer(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "UpdateCompMfr")
        resp = await client.post(
            "/api/equipment/computer",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "UpdateComp",
            },
        )
        comp_id = resp.json()["id"]

        resp = await client.put(
            f"/api/equipment/computer/{comp_id}",
            json={"notes": "Added RAM"},
        )
        assert resp.status_code == 200
        assert resp.json()["notes"] == "Added RAM"

    async def test_update_filter(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "UpdateFilterMfr")
        ft_id = await _get_filter_type_id(client)

        resp = await client.post(
            "/api/equipment/filter",
            json={
                "manufacturer_id": mfr["id"],
                "filter_type_id": ft_id,
                "model_name": "UpdateFilter",
            },
        )
        filter_id = resp.json()["id"]

        resp = await client.put(
            f"/api/equipment/filter/{filter_id}",
            json={"peak_transmission_pct": 98.5},
        )
        assert resp.status_code == 200
        assert resp.json()["peak_transmission_pct"] == 98.5

    async def test_update_telescope(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "UpdateScopeMfr")
        resp = await client.post(
            "/api/equipment/telescope",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "UpdateScope",
                "aperture_mm": 200.0,
            },
        )
        scope_id = resp.json()["id"]

        resp = await client.put(
            f"/api/equipment/telescope/{scope_id}",
            json={"aperture_mm": 203.2, "notes": "Corrected aperture"},
        )
        assert resp.status_code == 200
        assert resp.json()["aperture_mm"] == 203.2
        assert resp.json()["notes"] == "Corrected aperture"


# ── Junction table (interface) operations ───────────────────────────────────


class TestMountInterfaceOperations:
    async def test_update_mount_replaces_interfaces(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "MountIfaceMfr")
        iface1 = await _make_connection_interface(client, "ST4 Mount", "data")
        iface2 = await _make_connection_interface(client, "WiFi Mount", "data")

        resp = await client.post(
            "/api/equipment/mount",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "MountIfaceTest",
                "interface_ids": [iface1["id"]],
            },
        )
        assert resp.status_code == 201
        mount_id = resp.json()["id"]
        assert len(resp.json()["interfaces"]) == 1
        assert resp.json()["interfaces"][0]["name"] == "ST4 Mount"

        # Replace interfaces
        resp = await client.put(
            f"/api/equipment/mount/{mount_id}",
            json={"interface_ids": [iface2["id"]]},
        )
        assert resp.status_code == 200
        assert len(resp.json()["interfaces"]) == 1
        assert resp.json()["interfaces"][0]["name"] == "WiFi Mount"

    async def test_update_mount_clear_interfaces(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "MountIfaceClearMfr")
        iface = await _make_connection_interface(client, "ClearMe Mount", "data")

        resp = await client.post(
            "/api/equipment/mount",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "MountIfaceClearTest",
                "interface_ids": [iface["id"]],
            },
        )
        mount_id = resp.json()["id"]

        # Set interfaces to empty list
        resp = await client.put(
            f"/api/equipment/mount/{mount_id}",
            json={"interface_ids": []},
        )
        assert resp.status_code == 200
        assert resp.json()["interfaces"] == []


class TestFocuserInterfaceOperations:
    async def test_update_focuser_replaces_interfaces(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "FocuserIfaceMfr")
        iface1 = await _make_connection_interface(client, "USB FocuserIface1", "data")
        iface2 = await _make_connection_interface(client, "BT FocuserIface2", "data")

        resp = await client.post(
            "/api/equipment/focuser",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "FocuserIfaceTest",
                "motorized": True,
                "interface_ids": [iface1["id"]],
            },
        )
        assert resp.status_code == 201
        focuser_id = resp.json()["id"]
        assert len(resp.json()["interfaces"]) == 1

        resp = await client.put(
            f"/api/equipment/focuser/{focuser_id}",
            json={"interface_ids": [iface2["id"]]},
        )
        assert resp.status_code == 200
        assert len(resp.json()["interfaces"]) == 1
        assert resp.json()["interfaces"][0]["name"] == "BT FocuserIface2"


class TestFilterWheelInterfaceOperations:
    async def test_update_filter_wheel_replaces_interfaces(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "FWIfaceMfr")
        iface1 = await _make_connection_interface(client, "USB FWIface1", "data")
        iface2 = await _make_connection_interface(client, "Serial FWIface2", "data")

        resp = await client.post(
            "/api/equipment/filter-wheel",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "FWIfaceTest",
                "num_positions": 5,
                "interface_ids": [iface1["id"]],
            },
        )
        assert resp.status_code == 201
        fw_id = resp.json()["id"]
        assert len(resp.json()["interfaces"]) == 1

        resp = await client.put(
            f"/api/equipment/filter-wheel/{fw_id}",
            json={"interface_ids": [iface2["id"]]},
        )
        assert resp.status_code == 200
        assert len(resp.json()["interfaces"]) == 1
        assert resp.json()["interfaces"][0]["name"] == "Serial FWIface2"


# ── Seed tracking columns stripped from responses ───────────────────────────


class TestStripSeedColumns:
    async def test_camera_response_excludes_seed_keys(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "SeedStripMfr")
        sensor = await _make_sensor(client, mfr["id"], "SeedStripSensor")

        resp = await client.post(
            "/api/equipment/camera",
            json={
                "manufacturer_id": mfr["id"],
                "sensor_id": sensor["id"],
                "model_name": "SeedStripCam",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        for key in ("source", "seed_key", "seed_hash"):
            assert key not in data

    async def test_telescope_response_excludes_seed_keys(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "SeedStripScopeMfr")

        resp = await client.post(
            "/api/equipment/telescope",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "SeedStripScope",
                "aperture_mm": 100.0,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        for key in ("source", "seed_key", "seed_hash"):
            assert key not in data

    async def test_telescope_config_excludes_seed_keys(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "SeedCfgStripMfr")
        resp = await client.post(
            "/api/equipment/telescope",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "SeedCfgStripScope",
                "aperture_mm": 100.0,
            },
        )
        telescope_id = resp.json()["id"]

        resp = await client.post(
            f"/api/equipment/telescope/{telescope_id}/configuration",
            json={
                "telescope_id": telescope_id,
                "config_name": "Native",
                "effective_focal_length_mm": 500.0,
                "effective_focal_ratio": 5.0,
                "reduction_factor": 1.0,
                "is_native": True,
            },
        )
        assert resp.status_code == 201
        cfg = resp.json()
        for key in ("source", "seed_key", "seed_hash"):
            assert key not in cfg

    async def test_filter_response_excludes_seed_keys(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "SeedStripFilterMfr")
        ft_id = await _get_filter_type_id(client)

        resp = await client.post(
            "/api/equipment/filter",
            json={
                "manufacturer_id": mfr["id"],
                "filter_type_id": ft_id,
                "model_name": "SeedStripFilter",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        for key in ("source", "seed_key", "seed_hash"):
            assert key not in data

    async def test_mount_response_excludes_seed_keys(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "SeedStripMountMfr")
        resp = await client.post(
            "/api/equipment/mount",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "SeedStripMount",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        for key in ("source", "seed_key", "seed_hash"):
            assert key not in data

    async def test_focuser_response_excludes_seed_keys(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "SeedStripFocuserMfr")
        resp = await client.post(
            "/api/equipment/focuser",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "SeedStripFocuser",
                "motorized": False,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        for key in ("source", "seed_key", "seed_hash"):
            assert key not in data

    async def test_filter_wheel_response_excludes_seed_keys(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "SeedStripFWMfr")
        resp = await client.post(
            "/api/equipment/filter-wheel",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "SeedStripFW",
                "num_positions": 5,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        for key in ("source", "seed_key", "seed_hash"):
            assert key not in data

    async def test_oag_response_excludes_seed_keys(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "SeedStripOagMfr")
        resp = await client.post(
            "/api/equipment/oag",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "SeedStripOAG",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        for key in ("source", "seed_key", "seed_hash"):
            assert key not in data

    async def test_guide_scope_response_excludes_seed_keys(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "SeedStripGSMfr")
        resp = await client.post(
            "/api/equipment/guide-scope",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "SeedStripGS",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        for key in ("source", "seed_key", "seed_hash"):
            assert key not in data

    async def test_computer_response_excludes_seed_keys(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "SeedStripCompMfr")
        resp = await client.post(
            "/api/equipment/computer",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "SeedStripComp",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        for key in ("source", "seed_key", "seed_hash"):
            assert key not in data

    async def test_software_response_excludes_seed_keys(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "SeedStripSWMfr")
        resp = await client.post(
            "/api/equipment/software",
            json={
                "manufacturer_id": mfr["id"],
                "name": "SeedStripSW",
                "category": "capture",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        for key in ("source", "seed_key", "seed_hash"):
            assert key not in data


# ── include_retired on list endpoints ───────────────────────────────────────


class TestIncludeRetired:
    async def test_camera_include_retired(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "RetiredCamMfr")
        sensor = await _make_sensor(client, mfr["id"], "RetiredCamSensor")
        resp = await client.post(
            "/api/equipment/camera",
            json={
                "manufacturer_id": mfr["id"],
                "sensor_id": sensor["id"],
                "model_name": "RetiredCam",
            },
        )
        camera_id = resp.json()["id"]
        await client.delete(f"/api/equipment/camera/{camera_id}")

        resp = await client.get("/api/equipment/camera")
        assert "RetiredCam" not in [c["model_name"] for c in resp.json()]

        resp = await client.get("/api/equipment/camera?include_retired=true")
        assert "RetiredCam" in [c["model_name"] for c in resp.json()]

    async def test_telescope_include_retired(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "RetiredScopeMfr")
        resp = await client.post(
            "/api/equipment/telescope",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "RetiredScope",
                "aperture_mm": 80.0,
            },
        )
        scope_id = resp.json()["id"]
        await client.delete(f"/api/equipment/telescope/{scope_id}")

        resp = await client.get("/api/equipment/telescope")
        assert "RetiredScope" not in [t["model_name"] for t in resp.json()]

        resp = await client.get("/api/equipment/telescope?include_retired=true")
        assert "RetiredScope" in [t["model_name"] for t in resp.json()]

    async def test_filter_include_retired(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "RetiredFilterMfr")
        ft_id = await _get_filter_type_id(client)
        resp = await client.post(
            "/api/equipment/filter",
            json={
                "manufacturer_id": mfr["id"],
                "filter_type_id": ft_id,
                "model_name": "RetiredFilter",
            },
        )
        filter_id = resp.json()["id"]
        await client.delete(f"/api/equipment/filter/{filter_id}")

        resp = await client.get("/api/equipment/filter")
        assert "RetiredFilter" not in [f["model_name"] for f in resp.json()]

        resp = await client.get("/api/equipment/filter?include_retired=true")
        assert "RetiredFilter" in [f["model_name"] for f in resp.json()]

    async def test_mount_include_retired(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "RetiredMountMfr")
        resp = await client.post(
            "/api/equipment/mount",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "RetiredMount",
            },
        )
        mount_id = resp.json()["id"]
        await client.delete(f"/api/equipment/mount/{mount_id}")

        resp = await client.get("/api/equipment/mount")
        assert "RetiredMount" not in [m["model_name"] for m in resp.json()]

        resp = await client.get("/api/equipment/mount?include_retired=true")
        assert "RetiredMount" in [m["model_name"] for m in resp.json()]

    async def test_focuser_include_retired(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "RetiredFocuserMfr")
        resp = await client.post(
            "/api/equipment/focuser",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "RetiredFocuser",
                "motorized": True,
            },
        )
        focuser_id = resp.json()["id"]
        await client.delete(f"/api/equipment/focuser/{focuser_id}")

        resp = await client.get("/api/equipment/focuser")
        assert "RetiredFocuser" not in [f["model_name"] for f in resp.json()]

        resp = await client.get("/api/equipment/focuser?include_retired=true")
        assert "RetiredFocuser" in [f["model_name"] for f in resp.json()]

    async def test_filter_wheel_include_retired(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "RetiredFWMfr")
        resp = await client.post(
            "/api/equipment/filter-wheel",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "RetiredFW",
                "num_positions": 5,
            },
        )
        fw_id = resp.json()["id"]
        await client.delete(f"/api/equipment/filter-wheel/{fw_id}")

        resp = await client.get("/api/equipment/filter-wheel")
        assert "RetiredFW" not in [fw["model_name"] for fw in resp.json()]

        resp = await client.get("/api/equipment/filter-wheel?include_retired=true")
        assert "RetiredFW" in [fw["model_name"] for fw in resp.json()]

    async def test_oag_include_retired(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "RetiredOagMfr")
        resp = await client.post(
            "/api/equipment/oag",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "RetiredOAG",
            },
        )
        oag_id = resp.json()["id"]
        await client.delete(f"/api/equipment/oag/{oag_id}")

        resp = await client.get("/api/equipment/oag")
        assert "RetiredOAG" not in [o["model_name"] for o in resp.json()]

        resp = await client.get("/api/equipment/oag?include_retired=true")
        assert "RetiredOAG" in [o["model_name"] for o in resp.json()]

    async def test_guide_scope_include_retired(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "RetiredGSMfr")
        resp = await client.post(
            "/api/equipment/guide-scope",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "RetiredGS",
            },
        )
        gs_id = resp.json()["id"]
        await client.delete(f"/api/equipment/guide-scope/{gs_id}")

        resp = await client.get("/api/equipment/guide-scope")
        assert "RetiredGS" not in [g["model_name"] for g in resp.json()]

        resp = await client.get("/api/equipment/guide-scope?include_retired=true")
        assert "RetiredGS" in [g["model_name"] for g in resp.json()]

    async def test_computer_include_retired(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "RetiredCompMfr")
        resp = await client.post(
            "/api/equipment/computer",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "RetiredComp",
            },
        )
        comp_id = resp.json()["id"]
        await client.delete(f"/api/equipment/computer/{comp_id}")

        resp = await client.get("/api/equipment/computer")
        assert "RetiredComp" not in [c["model_name"] for c in resp.json()]

        resp = await client.get("/api/equipment/computer?include_retired=true")
        assert "RetiredComp" in [c["model_name"] for c in resp.json()]

    async def test_software_include_retired(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "RetiredSWMfr")
        resp = await client.post(
            "/api/equipment/software",
            json={
                "manufacturer_id": mfr["id"],
                "name": "RetiredSW",
                "category": "utility",
            },
        )
        sw_id = resp.json()["id"]
        await client.delete(f"/api/equipment/software/{sw_id}")

        resp = await client.get("/api/equipment/software")
        assert "RetiredSW" not in [s["name"] for s in resp.json()]

        resp = await client.get("/api/equipment/software?include_retired=true")
        assert "RetiredSW" in [s["name"] for s in resp.json()]


# ── Lookup table update/delete coverage ─────────────────────────────────────


class TestLookupUpdateCoverage:
    """Cover update endpoints for lookup tables that had update lines missing."""

    async def test_update_mount_type(self, client: AsyncClient):
        resp = await client.post(
            "/api/equipment/mount-type",
            json={"name": "UpdateMT", "description": "Original"},
        )
        mt_id = resp.json()["id"]

        resp = await client.put(
            f"/api/equipment/mount-type/{mt_id}",
            json={"description": "Updated desc"},
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated desc"

    async def test_update_connector_size(self, client: AsyncClient):
        resp = await client.post(
            "/api/equipment/connector-size",
            json={"name": "UpdateCS", "diameter_mm": 42.0},
        )
        cs_id = resp.json()["id"]

        resp = await client.put(
            f"/api/equipment/connector-size/{cs_id}",
            json={"diameter_mm": 48.0},
        )
        assert resp.status_code == 200
        assert resp.json()["diameter_mm"] == 48.0

    async def test_update_filter_size(self, client: AsyncClient):
        resp = await client.post(
            "/api/equipment/filter-size",
            json={"name": "UpdateFS", "description": "Original"},
        )
        fs_id = resp.json()["id"]

        resp = await client.put(
            f"/api/equipment/filter-size/{fs_id}",
            json={"description": "Updated FS desc"},
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated FS desc"

    async def test_update_form_factor(self, client: AsyncClient):
        resp = await client.post(
            "/api/equipment/form-factor",
            json={"name": "UpdateFF", "description": "Original"},
        )
        ff_id = resp.json()["id"]

        resp = await client.put(
            f"/api/equipment/form-factor/{ff_id}",
            json={"description": "Updated FF desc"},
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated FF desc"


# ── Get-by-id for equipment types with missing get coverage ────────────────


class TestGetById:
    async def test_get_mount_by_id(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "GetMountMfr")
        resp = await client.post(
            "/api/equipment/mount",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "GetMountById",
            },
        )
        mount_id = resp.json()["id"]

        resp = await client.get(f"/api/equipment/mount/{mount_id}")
        assert resp.status_code == 200
        assert resp.json()["model_name"] == "GetMountById"

    async def test_get_focuser_by_id(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "GetFocuserMfr")
        resp = await client.post(
            "/api/equipment/focuser",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "GetFocuserById",
                "motorized": False,
            },
        )
        focuser_id = resp.json()["id"]

        resp = await client.get(f"/api/equipment/focuser/{focuser_id}")
        assert resp.status_code == 200
        assert resp.json()["model_name"] == "GetFocuserById"

    async def test_get_filter_wheel_by_id(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "GetFWMfr")
        resp = await client.post(
            "/api/equipment/filter-wheel",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "GetFWById",
                "num_positions": 5,
            },
        )
        fw_id = resp.json()["id"]

        resp = await client.get(f"/api/equipment/filter-wheel/{fw_id}")
        assert resp.status_code == 200
        assert resp.json()["model_name"] == "GetFWById"

    async def test_get_oag_by_id(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "GetOagMfr")
        resp = await client.post(
            "/api/equipment/oag",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "GetOagById",
            },
        )
        oag_id = resp.json()["id"]

        resp = await client.get(f"/api/equipment/oag/{oag_id}")
        assert resp.status_code == 200
        assert resp.json()["model_name"] == "GetOagById"

    async def test_get_guide_scope_by_id(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "GetGSMfr")
        resp = await client.post(
            "/api/equipment/guide-scope",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "GetGSById",
            },
        )
        gs_id = resp.json()["id"]

        resp = await client.get(f"/api/equipment/guide-scope/{gs_id}")
        assert resp.status_code == 200
        assert resp.json()["model_name"] == "GetGSById"

    async def test_get_computer_by_id(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "GetCompMfr")
        resp = await client.post(
            "/api/equipment/computer",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "GetCompById",
            },
        )
        comp_id = resp.json()["id"]

        resp = await client.get(f"/api/equipment/computer/{comp_id}")
        assert resp.status_code == 200
        assert resp.json()["model_name"] == "GetCompById"

    async def test_get_software_by_id(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "GetSWMfr")
        resp = await client.post(
            "/api/equipment/software",
            json={
                "manufacturer_id": mfr["id"],
                "name": "GetSWById",
                "category": "capture",
            },
        )
        sw_id = resp.json()["id"]

        resp = await client.get(f"/api/equipment/software/{sw_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "GetSWById"

    async def test_get_camera_by_id(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "GetCamMfr")
        sensor = await _make_sensor(client, mfr["id"], "GetCamSensor")
        resp = await client.post(
            "/api/equipment/camera",
            json={
                "manufacturer_id": mfr["id"],
                "sensor_id": sensor["id"],
                "model_name": "GetCamById",
            },
        )
        cam_id = resp.json()["id"]

        resp = await client.get(f"/api/equipment/camera/{cam_id}")
        assert resp.status_code == 200
        assert resp.json()["model_name"] == "GetCamById"


# ── 404 for update/delete on remaining equipment types ────────────────────


class TestEquipment404Extra:
    async def test_update_mount_404(self, client: AsyncClient):
        resp = await client.put("/api/equipment/mount/99999", json={"model_name": "X"})
        assert resp.status_code == 404

    async def test_delete_mount_404(self, client: AsyncClient):
        resp = await client.delete("/api/equipment/mount/99999")
        assert resp.status_code == 404

    async def test_update_focuser_404(self, client: AsyncClient):
        resp = await client.put("/api/equipment/focuser/99999", json={"model_name": "X"})
        assert resp.status_code == 404

    async def test_delete_focuser_404(self, client: AsyncClient):
        resp = await client.delete("/api/equipment/focuser/99999")
        assert resp.status_code == 404

    async def test_update_filter_wheel_404(self, client: AsyncClient):
        resp = await client.put("/api/equipment/filter-wheel/99999", json={"num_positions": 7})
        assert resp.status_code == 404

    async def test_delete_filter_wheel_404(self, client: AsyncClient):
        resp = await client.delete("/api/equipment/filter-wheel/99999")
        assert resp.status_code == 404

    async def test_update_oag_404(self, client: AsyncClient):
        resp = await client.put("/api/equipment/oag/99999", json={"prism_size_mm": 5.0})
        assert resp.status_code == 404

    async def test_delete_oag_404(self, client: AsyncClient):
        resp = await client.delete("/api/equipment/oag/99999")
        assert resp.status_code == 404

    async def test_update_guide_scope_404(self, client: AsyncClient):
        resp = await client.put("/api/equipment/guide-scope/99999", json={"aperture_mm": 50.0})
        assert resp.status_code == 404

    async def test_delete_guide_scope_404(self, client: AsyncClient):
        resp = await client.delete("/api/equipment/guide-scope/99999")
        assert resp.status_code == 404

    async def test_update_computer_404(self, client: AsyncClient):
        resp = await client.put("/api/equipment/computer/99999", json={"notes": "X"})
        assert resp.status_code == 404

    async def test_delete_computer_404(self, client: AsyncClient):
        resp = await client.delete("/api/equipment/computer/99999")
        assert resp.status_code == 404

    async def test_update_software_404(self, client: AsyncClient):
        resp = await client.put("/api/equipment/software/99999", json={"website": "X"})
        assert resp.status_code == 404

    async def test_delete_software_404(self, client: AsyncClient):
        resp = await client.delete("/api/equipment/software/99999")
        assert resp.status_code == 404

    async def test_update_sensor_404(self, client: AsyncClient):
        resp = await client.put("/api/equipment/sensor/99999", json={"notes": "X"})
        assert resp.status_code == 404

    async def test_delete_sensor_404(self, client: AsyncClient):
        resp = await client.delete("/api/equipment/sensor/99999")
        assert resp.status_code == 404

    async def test_update_filter_404(self, client: AsyncClient):
        resp = await client.put("/api/equipment/filter/99999", json={"notes": "X"})
        assert resp.status_code == 404

    async def test_update_telescope_404(self, client: AsyncClient):
        resp = await client.put("/api/equipment/telescope/99999", json={"notes": "X"})
        assert resp.status_code == 404

    async def test_delete_config_not_found(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "CfgDel404Mfr")
        resp = await client.post(
            "/api/equipment/telescope",
            json={
                "manufacturer_id": mfr["id"],
                "model_name": "CfgDel404Scope",
                "aperture_mm": 100.0,
            },
        )
        telescope_id = resp.json()["id"]

        resp = await client.delete(f"/api/equipment/telescope/{telescope_id}/configuration/99999")
        assert resp.status_code == 404


# ── Lookup table get-by-id coverage ─────────────────────────────────────────


class TestLookupGetById:
    async def test_get_connection_interface_by_id(self, client: AsyncClient):
        ci = await _make_connection_interface(client, "GetCIById", "data")
        resp = await client.get(f"/api/equipment/connection-interface/{ci['id']}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "GetCIById"

    async def test_get_connector_size_by_id(self, client: AsyncClient):
        cs = await _make_connector_size(client, "GetCSById")
        resp = await client.get(f"/api/equipment/connector-size/{cs['id']}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "GetCSById"

    async def test_get_filter_size_by_id(self, client: AsyncClient):
        resp = await client.post(
            "/api/equipment/filter-size",
            json={"name": "GetFSById"},
        )
        assert resp.status_code == 201
        fs_id = resp.json()["id"]

        resp = await client.get(f"/api/equipment/filter-size/{fs_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "GetFSById"

    async def test_get_form_factor_by_id(self, client: AsyncClient):
        resp = await client.post(
            "/api/equipment/form-factor",
            json={"name": "GetFFById"},
        )
        assert resp.status_code == 201
        ff_id = resp.json()["id"]

        resp = await client.get(f"/api/equipment/form-factor/{ff_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "GetFFById"

    async def test_get_focuser_type_by_id(self, client: AsyncClient):
        resp = await client.post(
            "/api/equipment/focuser-type",
            json={"name": "GetFTById"},
        )
        assert resp.status_code == 201
        ft_id = resp.json()["id"]

        resp = await client.get(f"/api/equipment/focuser-type/{ft_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "GetFTById"


# ── Duplicate name on update (409) ──────────────────────────────────────────


class TestDuplicateOnUpdate:
    async def test_update_manufacturer_duplicate_409(self, client: AsyncClient):
        await _make_manufacturer(client, "DupUpdateMfr1")
        mfr2 = await _make_manufacturer(client, "DupUpdateMfr2")

        resp = await client.put(
            f"/api/equipment/manufacturer/{mfr2['id']}",
            json={"name": "DupUpdateMfr1"},
        )
        assert resp.status_code == 409

    async def test_update_optical_design_duplicate_409(self, client: AsyncClient):
        await client.post(
            "/api/equipment/optical-design",
            json={"name": "DupOD1"},
        )
        resp2 = await client.post(
            "/api/equipment/optical-design",
            json={"name": "DupOD2"},
        )
        resp = await client.put(
            f"/api/equipment/optical-design/{resp2.json()['id']}",
            json={"name": "DupOD1"},
        )
        assert resp.status_code == 409

    async def test_update_mount_type_duplicate_409(self, client: AsyncClient):
        await client.post(
            "/api/equipment/mount-type",
            json={"name": "DupMT1"},
        )
        resp2 = await client.post(
            "/api/equipment/mount-type",
            json={"name": "DupMT2"},
        )
        resp = await client.put(
            f"/api/equipment/mount-type/{resp2.json()['id']}",
            json={"name": "DupMT1"},
        )
        assert resp.status_code == 409

    async def test_update_connection_interface_duplicate_409(self, client: AsyncClient):
        await _make_connection_interface(client, "DupCI1", "data")
        ci2 = await _make_connection_interface(client, "DupCI2", "data")

        resp = await client.put(
            f"/api/equipment/connection-interface/{ci2['id']}",
            json={"name": "DupCI1"},
        )
        assert resp.status_code == 409

    async def test_update_connector_size_duplicate_409(self, client: AsyncClient):
        await _make_connector_size(client, "DupCS1")
        cs2 = await _make_connector_size(client, "DupCS2")

        resp = await client.put(
            f"/api/equipment/connector-size/{cs2['id']}",
            json={"name": "DupCS1"},
        )
        assert resp.status_code == 409

    async def test_update_filter_size_duplicate_409(self, client: AsyncClient):
        await client.post("/api/equipment/filter-size", json={"name": "DupFS1"})
        resp2 = await client.post("/api/equipment/filter-size", json={"name": "DupFS2"})
        resp = await client.put(
            f"/api/equipment/filter-size/{resp2.json()['id']}",
            json={"name": "DupFS1"},
        )
        assert resp.status_code == 409

    async def test_update_form_factor_duplicate_409(self, client: AsyncClient):
        await client.post("/api/equipment/form-factor", json={"name": "DupFF1"})
        resp2 = await client.post("/api/equipment/form-factor", json={"name": "DupFF2"})
        resp = await client.put(
            f"/api/equipment/form-factor/{resp2.json()['id']}",
            json={"name": "DupFF1"},
        )
        assert resp.status_code == 409

    async def test_update_focuser_type_duplicate_409(self, client: AsyncClient):
        await client.post("/api/equipment/focuser-type", json={"name": "DupFT1"})
        resp2 = await client.post("/api/equipment/focuser-type", json={"name": "DupFT2"})
        resp = await client.put(
            f"/api/equipment/focuser-type/{resp2.json()['id']}",
            json={"name": "DupFT1"},
        )
        assert resp.status_code == 409

    async def test_update_filter_type_duplicate_409(self, client: AsyncClient):
        await client.post(
            "/api/equipment/filter-type",
            json={"name": "dup_ftype1", "display_name": "Dup1"},
        )
        resp2 = await client.post(
            "/api/equipment/filter-type",
            json={"name": "dup_ftype2", "display_name": "Dup2"},
        )
        resp = await client.put(
            f"/api/equipment/filter-type/{resp2.json()['id']}",
            json={"name": "dup_ftype1"},
        )
        assert resp.status_code == 409


# ── No-op updates (empty body) ─────────────────────────────────────────────


class TestNoopUpdate:
    async def test_empty_update_manufacturer(self, client: AsyncClient):
        mfr = await _make_manufacturer(client, "NoopMfr")
        resp = await client.put(f"/api/equipment/manufacturer/{mfr['id']}", json={})
        assert resp.status_code == 200
        assert resp.json()["name"] == "NoopMfr"

    async def test_empty_update_optical_design(self, client: AsyncClient):
        resp = await client.post("/api/equipment/optical-design", json={"name": "NoopOD"})
        od_id = resp.json()["id"]
        resp = await client.put(f"/api/equipment/optical-design/{od_id}", json={})
        assert resp.status_code == 200
        assert resp.json()["name"] == "NoopOD"

    async def test_empty_update_filter_type(self, client: AsyncClient):
        resp = await client.post(
            "/api/equipment/filter-type",
            json={"name": "noop_ft", "display_name": "Noop"},
        )
        ft_id = resp.json()["id"]
        resp = await client.put(f"/api/equipment/filter-type/{ft_id}", json={})
        assert resp.status_code == 200
        assert resp.json()["name"] == "noop_ft"
