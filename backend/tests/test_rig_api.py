"""Tests for rig API endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.db.session import get_db
from nightcrate.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _get_or_insert_manufacturer(conn, name: str) -> int:
    """Get existing manufacturer ID or insert a new one."""
    row = await conn.execute("SELECT id FROM manufacturer WHERE name = ?", (name,))
    result = await row.fetchone()
    if result:
        return result[0]
    await conn.execute(
        "INSERT INTO manufacturer (name, active, source) VALUES (?, 1, 'user')", (name,)
    )
    return (await (await conn.execute("SELECT last_insert_rowid()")).fetchone())[0]


async def _get_or_insert_lookup(conn, table: str, name: str) -> int:
    """Get existing lookup table ID or insert a new one."""
    row = await conn.execute(f"SELECT id FROM {table} WHERE name = ?", (name,))
    result = await row.fetchone()
    if result:
        return result[0]
    await conn.execute(f"INSERT INTO {table} (name, active, source) VALUES (?, 1, 'user')", (name,))
    return (await (await conn.execute("SELECT last_insert_rowid()")).fetchone())[0]


async def _seed_equipment():
    """Insert minimal equipment for rig tests. Returns dict of created IDs."""
    async with get_db() as conn:
        # Manufacturers (may already exist from seed loader)
        zwo_mfr = await _get_or_insert_manufacturer(conn, "ZWO")
        cel_mfr = await _get_or_insert_manufacturer(conn, "Celestron")
        askar_mfr = await _get_or_insert_manufacturer(conn, "Askar")
        wa_mfr = await _get_or_insert_manufacturer(conn, "WarpAstron")

        # Sensor
        await conn.execute(
            "INSERT INTO sensor (manufacturer_id, model_name, sensor_type, "
            "pixel_size_um, resolution_x, resolution_y, sensor_width_mm, "
            "sensor_height_mm, active, source) "
            "VALUES (?, 'IMX571 Test', 'mono', 3.76, 6248, 4176, 23.5, 15.7, 1, 'user')",
            (zwo_mfr,),
        )
        sensor = (await (await conn.execute("SELECT last_insert_rowid()")).fetchone())[0]

        # Guide sensor
        await conn.execute(
            "INSERT INTO sensor (manufacturer_id, model_name, sensor_type, "
            "pixel_size_um, resolution_x, resolution_y, active, source) "
            "VALUES (?, 'IMX178 Test', 'mono', 2.4, 3096, 2080, 1, 'user')",
            (zwo_mfr,),
        )
        guide_sensor = (await (await conn.execute("SELECT last_insert_rowid()")).fetchone())[0]

        # Camera
        await conn.execute(
            "INSERT INTO camera (manufacturer_id, sensor_id, model_name, cooled, "
            "tilt_adapter, has_usb_hub, active, source) "
            "VALUES (?, ?, 'ASI 2600MM Pro', 1, 0, 0, 1, 'user')",
            (zwo_mfr, sensor),
        )
        camera = (await (await conn.execute("SELECT last_insert_rowid()")).fetchone())[0]

        # Guide camera
        await conn.execute(
            "INSERT INTO camera (manufacturer_id, sensor_id, model_name, cooled, "
            "tilt_adapter, has_usb_hub, active, source) "
            "VALUES (?, ?, 'ASI 178MM', 0, 0, 0, 1, 'user')",
            (zwo_mfr, guide_sensor),
        )
        guide_camera = (await (await conn.execute("SELECT last_insert_rowid()")).fetchone())[0]

        # Optical design
        od = await _get_or_insert_lookup(conn, "optical_design", "SCT")

        # Telescope
        await conn.execute(
            "INSERT INTO telescope (manufacturer_id, optical_design_id, model_name, "
            "aperture_mm, active, source) "
            "VALUES (?, ?, 'C11 Test', 280.0, 1, 'user')",
            (cel_mfr, od),
        )
        telescope = (await (await conn.execute("SELECT last_insert_rowid()")).fetchone())[0]

        # Telescope configuration
        await conn.execute(
            "INSERT INTO telescope_configuration (telescope_id, config_name, "
            "reduction_factor, effective_focal_length_mm, effective_focal_ratio, "
            "is_native, active, source) "
            "VALUES (?, '0.7x Reducer', 0.7, 1960.0, 7.0, 0, 1, 'user')",
            (telescope,),
        )
        tc = (await (await conn.execute("SELECT last_insert_rowid()")).fetchone())[0]

        # Filter wheel
        await conn.execute(
            "INSERT INTO filter_wheel (manufacturer_id, model_name, num_positions, "
            "active, source) "
            "VALUES (?, '7-pos Wheel', 7, 1, 'user')",
            (zwo_mfr,),
        )
        fw = (await (await conn.execute("SELECT last_insert_rowid()")).fetchone())[0]

        # Filters -- need a filter_type first
        ft_row = await conn.execute("SELECT id FROM filter_type WHERE name = 'luminance' LIMIT 1")
        ft = (await ft_row.fetchone())[0]

        filter_ids = []
        for fname in [
            "Lum Test",
            "Red Test",
            "Green Test",
            "Blue Test",
            "Ha 7nm Test",
            "Oiii 7nm Test",
            "Sii 7nm Test",
        ]:
            await conn.execute(
                "INSERT INTO filter (manufacturer_id, filter_type_id, model_name, "
                "active, source) VALUES (?, ?, ?, 1, 'user')",
                (zwo_mfr, ft, fname),
            )
            fid = (await (await conn.execute("SELECT last_insert_rowid()")).fetchone())[0]
            filter_ids.append(fid)

        # Mount type
        mt = await _get_or_insert_lookup(conn, "mount_type", "EQ")

        # Mount
        await conn.execute(
            "INSERT INTO mount (manufacturer_id, mount_type_id, model_name, "
            "active, source) "
            "VALUES (?, ?, 'WD-20 Test', 1, 'user')",
            (wa_mfr, mt),
        )
        mount = (await (await conn.execute("SELECT last_insert_rowid()")).fetchone())[0]

        # Guide scope
        await conn.execute(
            "INSERT INTO guide_scope (manufacturer_id, model_name, aperture_mm, "
            "focal_length_mm, active, source) "
            "VALUES (?, '52mm f/4 Test', 52.0, 208.0, 1, 'user')",
            (askar_mfr,),
        )
        guide_scope = (await (await conn.execute("SELECT last_insert_rowid()")).fetchone())[0]

        await conn.commit()

        return {
            "camera_id": camera,
            "guide_camera_id": guide_camera,
            "telescope_configuration_id": tc,
            "filter_wheel_id": fw,
            "filter_ids": filter_ids,
            "mount_id": mount,
            "guide_scope_id": guide_scope,
        }


@pytest.fixture
async def equipment():
    return await _seed_equipment()


def _rig_payload(eq, **overrides):
    """Build a minimal rig creation payload."""
    base = {
        "name": "C11 Deep Sky",
        "telescope_configuration_id": eq["telescope_configuration_id"],
        "camera_id": eq["camera_id"],
    }
    base.update(overrides)
    return base


# ── CRUD Tests ───────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_create_rig(client, equipment):
    payload = _rig_payload(equipment)
    resp = await client.post("/api/rigs", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "C11 Deep Sky"
    assert data["camera_name"] == "ASI 2600MM Pro"
    assert data["telescope_config_name"] == "0.7x Reducer"
    assert data["calculators"]["image_scale_arcsec_per_pixel"] == pytest.approx(0.396, abs=0.001)


@pytest.mark.anyio
async def test_list_rigs(client, equipment):
    await client.post("/api/rigs", json=_rig_payload(equipment))
    resp = await client.get("/api/rigs")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "C11 Deep Sky"


@pytest.mark.anyio
async def test_get_rig(client, equipment):
    create_resp = await client.post("/api/rigs", json=_rig_payload(equipment))
    rig_id = create_resp.json()["id"]
    resp = await client.get(f"/api/rigs/{rig_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == rig_id


@pytest.mark.anyio
async def test_get_rig_404(client):
    resp = await client.get("/api/rigs/99999")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_update_rig(client, equipment):
    create_resp = await client.post("/api/rigs", json=_rig_payload(equipment))
    rig_id = create_resp.json()["id"]
    resp = await client.put(f"/api/rigs/{rig_id}", json={"name": "C11 Narrowband"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "C11 Narrowband"


@pytest.mark.anyio
async def test_soft_delete_rig(client, equipment):
    create_resp = await client.post("/api/rigs", json=_rig_payload(equipment))
    rig_id = create_resp.json()["id"]
    resp = await client.delete(f"/api/rigs/{rig_id}")
    assert resp.status_code == 204

    # Should not appear in active list
    list_resp = await client.get("/api/rigs")
    assert len(list_resp.json()) == 0

    # Should appear with active_only=false
    list_resp = await client.get("/api/rigs?active_only=false")
    assert len(list_resp.json()) == 1


@pytest.mark.anyio
async def test_restore_rig(client, equipment):
    create_resp = await client.post("/api/rigs", json=_rig_payload(equipment))
    rig_id = create_resp.json()["id"]
    await client.delete(f"/api/rigs/{rig_id}")
    resp = await client.post(f"/api/rigs/{rig_id}/restore")
    assert resp.status_code == 200
    assert resp.json()["active"] is True


# ── Filter Slots ─────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_create_rig_with_filter_slots(client, equipment):
    payload = _rig_payload(
        equipment,
        filter_wheel_id=equipment["filter_wheel_id"],
        filter_slots=[
            {"slot_number": 1, "filter_id": equipment["filter_ids"][0]},
            {"slot_number": 2, "filter_id": equipment["filter_ids"][1]},
        ],
    )
    resp = await client.post("/api/rigs", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert len(data["filter_slots"]) == 2
    assert data["filter_slots"][0]["slot_number"] == 1
    assert data["filter_slots"][1]["slot_number"] == 2


@pytest.mark.anyio
async def test_update_replaces_filter_slots(client, equipment):
    payload = _rig_payload(
        equipment,
        filter_wheel_id=equipment["filter_wheel_id"],
        filter_slots=[{"slot_number": 1, "filter_id": equipment["filter_ids"][0]}],
    )
    create_resp = await client.post("/api/rigs", json=payload)
    rig_id = create_resp.json()["id"]

    # Replace with different slots
    resp = await client.put(
        f"/api/rigs/{rig_id}",
        json={"filter_slots": [{"slot_number": 3, "filter_id": equipment["filter_ids"][2]}]},
    )
    assert resp.status_code == 200
    slots = resp.json()["filter_slots"]
    assert len(slots) == 1
    assert slots[0]["slot_number"] == 3


@pytest.mark.anyio
async def test_remove_filter_wheel_clears_slots(client, equipment):
    payload = _rig_payload(
        equipment,
        filter_wheel_id=equipment["filter_wheel_id"],
        filter_slots=[{"slot_number": 1, "filter_id": equipment["filter_ids"][0]}],
    )
    create_resp = await client.post("/api/rigs", json=payload)
    rig_id = create_resp.json()["id"]

    resp = await client.put(f"/api/rigs/{rig_id}", json={"filter_wheel_id": None})
    assert resp.status_code == 200
    assert resp.json()["filter_wheel_id"] is None
    assert resp.json()["filter_slots"] == []


# ── Validation ───────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_slot_number_exceeds_wheel_capacity(client, equipment):
    payload = _rig_payload(
        equipment,
        filter_wheel_id=equipment["filter_wheel_id"],
        filter_slots=[{"slot_number": 8, "filter_id": equipment["filter_ids"][0]}],
    )
    resp = await client.post("/api/rigs", json=payload)
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_filter_slots_without_wheel_rejected(client, equipment):
    payload = _rig_payload(
        equipment,
        filter_slots=[{"slot_number": 1, "filter_id": equipment["filter_ids"][0]}],
    )
    resp = await client.post("/api/rigs", json=payload)
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_duplicate_name_rejected(client, equipment):
    await client.post("/api/rigs", json=_rig_payload(equipment))
    resp = await client.post("/api/rigs", json=_rig_payload(equipment))
    assert resp.status_code == 409


# ── Default Flag ─────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_set_default_clears_others(client, equipment):
    r1 = await client.post("/api/rigs", json=_rig_payload(equipment, is_default=True))
    r2 = await client.post(
        "/api/rigs",
        json=_rig_payload(equipment, name="Rig 2", is_default=True),
    )
    assert r2.status_code == 201

    # First rig should no longer be default
    r1_data = await client.get(f"/api/rigs/{r1.json()['id']}")
    assert r1_data.json()["is_default"] is False
    assert r2.json()["is_default"] is True


# ── Clone ────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_clone_rig(client, equipment):
    payload = _rig_payload(
        equipment,
        filter_wheel_id=equipment["filter_wheel_id"],
        filter_slots=[{"slot_number": 1, "filter_id": equipment["filter_ids"][0]}],
    )
    create_resp = await client.post("/api/rigs", json=payload)
    rig_id = create_resp.json()["id"]

    resp = await client.post(f"/api/rigs/{rig_id}/clone")
    assert resp.status_code == 201
    clone = resp.json()
    assert clone["name"] == "C11 Deep Sky (Copy)"
    assert clone["is_default"] is False
    assert len(clone["filter_slots"]) == 1


@pytest.mark.anyio
async def test_clone_name_collision(client, equipment):
    payload = _rig_payload(equipment)
    create_resp = await client.post("/api/rigs", json=payload)
    rig_id = create_resp.json()["id"]

    # First clone
    await client.post(f"/api/rigs/{rig_id}/clone")
    # Second clone -- name collision with "(Copy)", should get "(Copy 2)"
    resp = await client.post(f"/api/rigs/{rig_id}/clone")
    assert resp.status_code == 201
    assert resp.json()["name"] == "C11 Deep Sky (Copy 2)"


# ── Warnings ─────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_guide_camera_same_as_imaging_warning(client, equipment):
    payload = _rig_payload(
        equipment,
        guide_camera_id=equipment["camera_id"],  # same as imaging camera
    )
    resp = await client.post("/api/rigs", json=payload)
    assert resp.status_code == 201
    warnings = resp.json()["warnings"]
    assert any(w["field"] == "guide_camera_id" for w in warnings)


# ── Equipment Options ────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_equipment_options(client, equipment):
    resp = await client.get("/api/rigs/equipment-options")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["telescopes"]) >= 1
    assert len(data["cameras"]) >= 1
    assert len(data["telescopes"][0]["configs"]) >= 1


# ── Calculators ──────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_calculator_endpoint(client, equipment):
    create_resp = await client.post("/api/rigs", json=_rig_payload(equipment))
    rig_id = create_resp.json()["id"]

    resp = await client.get(f"/api/rigs/{rig_id}/calculators")
    assert resp.status_code == 200
    data = resp.json()
    assert data["image_scale_arcsec_per_pixel"] == pytest.approx(0.396, abs=0.001)
    assert data["sampling_assessment"]["seeing_source"] == "default"


@pytest.mark.anyio
async def test_calculator_with_seeing_override(client, equipment):
    create_resp = await client.post("/api/rigs", json=_rig_payload(equipment))
    rig_id = create_resp.json()["id"]

    resp = await client.get(f"/api/rigs/{rig_id}/calculators?seeing_low=1.0&seeing_high=2.0")
    assert resp.status_code == 200
    data = resp.json()
    assert data["sampling_assessment"]["seeing_source"] == "override"
    assert data["sampling_assessment"]["seeing_fwhm_low"] == 1.0


@pytest.mark.anyio
async def test_calculator_guide_suitability_guide_scope_mode(client, equipment):
    """Rig with guide scope + guide camera surfaces guide_suitability."""
    payload = _rig_payload(
        equipment,
        guide_scope_id=equipment["guide_scope_id"],
        guide_camera_id=equipment["guide_camera_id"],
    )
    create_resp = await client.post("/api/rigs", json=payload)
    rig_id = create_resp.json()["id"]

    resp = await client.get(f"/api/rigs/{rig_id}/calculators")
    assert resp.status_code == 200
    gs = resp.json()["guide_suitability"]
    assert gs is not None
    assert gs["mode"] == "guide_scope"
    assert gs["guide_binning"] == 1
    assert gs["centroid_accuracy_pixels"] == pytest.approx(0.2, abs=0.001)


@pytest.mark.anyio
async def test_calculator_guide_suitability_binning_param(client, equipment):
    """guide_binning query param propagates through to guide_suitability."""
    payload = _rig_payload(
        equipment,
        guide_scope_id=equipment["guide_scope_id"],
        guide_camera_id=equipment["guide_camera_id"],
    )
    create_resp = await client.post("/api/rigs", json=payload)
    rig_id = create_resp.json()["id"]

    resp = await client.get(
        f"/api/rigs/{rig_id}/calculators?guide_binning=2&centroid_accuracy_pixels=0.3"
    )
    assert resp.status_code == 200
    gs = resp.json()["guide_suitability"]
    assert gs["guide_binning"] == 2
    assert gs["centroid_accuracy_pixels"] == pytest.approx(0.3, abs=0.001)
    # Binned scale = 2 * unbinned.
    assert gs["guide_scale_arcsec_per_pixel"] == pytest.approx(
        2 * gs["unbinned_guide_scale_arcsec_per_pixel"], abs=0.001
    )


@pytest.mark.anyio
async def test_calculator_guide_binning_validation(client, equipment):
    create_resp = await client.post("/api/rigs", json=_rig_payload(equipment))
    rig_id = create_resp.json()["id"]
    resp = await client.get(f"/api/rigs/{rig_id}/calculators?guide_binning=5")
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_calculator_centroid_accuracy_validation(client, equipment):
    create_resp = await client.post("/api/rigs", json=_rig_payload(equipment))
    rig_id = create_resp.json()["id"]
    resp = await client.get(f"/api/rigs/{rig_id}/calculators?centroid_accuracy_pixels=0.8")
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_calculator_guide_suitability_none_without_guide_camera(client, equipment):
    """No guide camera → guide_suitability is null."""
    create_resp = await client.post("/api/rigs", json=_rig_payload(equipment))
    rig_id = create_resp.json()["id"]

    resp = await client.get(f"/api/rigs/{rig_id}/calculators")
    assert resp.status_code == 200
    assert resp.json()["guide_suitability"] is None


@pytest.mark.anyio
async def test_warning_guide_camera_without_path(client, equipment):
    """Guide camera assigned with no guide scope or OAG emits a warning."""
    payload = _rig_payload(
        equipment,
        guide_camera_id=equipment["guide_camera_id"],
        # No guide_scope_id and no oag_id.
    )
    resp = await client.post("/api/rigs", json=payload)
    assert resp.status_code == 201
    warnings = resp.json()["warnings"]
    assert any(
        w["field"] == "guide_camera_id" and "no guide scope or OAG" in w["message"]
        for w in warnings
    )


@pytest.mark.anyio
async def test_warning_guide_scope_missing_focal_length(client, equipment):
    """Guide scope whose focal_length_mm is NULL emits a warning."""
    # Insert a guide scope with NULL focal length.
    async with get_db() as conn:
        row = await conn.execute("SELECT manufacturer_id FROM guide_scope LIMIT 1")
        mfr_id = (await row.fetchone())[0]
        await conn.execute(
            "INSERT INTO guide_scope (manufacturer_id, model_name, aperture_mm, "
            "focal_length_mm, active, source) "
            "VALUES (?, 'Test No FL', 50.0, NULL, 1, 'user')",
            (mfr_id,),
        )
        await conn.commit()
        no_fl_id = (await (await conn.execute("SELECT last_insert_rowid()")).fetchone())[0]

    payload = _rig_payload(
        equipment,
        guide_scope_id=no_fl_id,
        guide_camera_id=equipment["guide_camera_id"],
    )
    resp = await client.post("/api/rigs", json=payload)
    assert resp.status_code == 201
    warnings = resp.json()["warnings"]
    assert any(
        w["field"] == "guide_scope_id" and "no focal length" in w["message"] for w in warnings
    )
    # And calculator returns None for guide_suitability because FL is missing.
    rig_id = resp.json()["id"]
    calc_resp = await client.get(f"/api/rigs/{rig_id}/calculators")
    assert calc_resp.json()["guide_suitability"] is None


@pytest.mark.anyio
async def test_calculator_image_binning_validation(client, equipment):
    """image_binning=5 / 0 → 422."""
    resp = await client.post("/api/rigs", json=_rig_payload(equipment))
    rig_id = resp.json()["id"]
    bad_high = await client.get(f"/api/rigs/{rig_id}/calculators?image_binning=5")
    bad_low = await client.get(f"/api/rigs/{rig_id}/calculators?image_binning=0")
    assert bad_high.status_code == 422
    assert bad_low.status_code == 422


@pytest.mark.anyio
async def test_calculator_guiding_tolerance_scales_with_image_binning(client, equipment):
    """image_binning=2 doubles tight/acceptable/noticeable vs image_binning=1."""
    resp = await client.post(
        "/api/rigs",
        json=_rig_payload(
            equipment,
            guide_scope_id=equipment["guide_scope_id"],
            guide_camera_id=equipment["guide_camera_id"],
        ),
    )
    rig_id = resp.json()["id"]

    r1 = await client.get(f"/api/rigs/{rig_id}/calculators?image_binning=1")
    r2 = await client.get(f"/api/rigs/{rig_id}/calculators?image_binning=2")
    assert r1.status_code == 200 and r2.status_code == 200
    t1 = r1.json()["guiding_tolerance"]
    t2 = r2.json()["guiding_tolerance"]
    assert t1 is not None and t2 is not None
    assert t2["tight_rms_arcsec"] == pytest.approx(2 * t1["tight_rms_arcsec"], abs=0.001)
    assert t2["acceptable_rms_arcsec"] == pytest.approx(2 * t1["acceptable_rms_arcsec"], abs=0.001)
    assert t2["image_binning"] == 2


@pytest.mark.anyio
async def test_update_rig_duplicate_name_rejected(client, equipment):
    """Renaming a rig to collide with another returns 409."""
    r1 = await client.post("/api/rigs", json=_rig_payload(equipment, name="First"))
    r2 = await client.post("/api/rigs", json=_rig_payload(equipment, name="Second"))
    assert r1.status_code == 201 and r2.status_code == 201
    r2_id = r2.json()["id"]
    resp = await client.put(f"/api/rigs/{r2_id}", json={"name": "First"})
    assert resp.status_code == 409
