"""Equipment management API endpoints — CRUD for all equipment types."""

from fastapi import APIRouter, HTTPException, Query

from nightcrate.api._common import (
    bool_fields,
    get_or_404,
    integrity_guard,
    row_to_dict,
    strip_seed,
)
from nightcrate.api.equipment_factory import build_equipment_router, build_lookup_router
from nightcrate.api.equipment_models import (
    CameraCreate,
    CameraResponse,
    CameraUpdate,
    ComputerCreate,
    ComputerResponse,
    ComputerUpdate,
    ConnectionInterfaceCreate,
    ConnectionInterfaceResponse,
    ConnectionInterfaceUpdate,
    ConnectorSizeCreate,
    ConnectorSizeResponse,
    ConnectorSizeUpdate,
    FilterCreate,
    FilterPassbandCreate,
    FilterPassbandResponse,
    FilterPassbandUpdate,
    FilterResponse,
    FilterSizeCreate,
    FilterSizeOptionCreate,
    FilterSizeOptionResponse,
    FilterSizeOptionUpdate,
    FilterSizeResponse,
    FilterSizeUpdate,
    FilterTypeCreate,
    FilterTypeResponse,
    FilterTypeUpdate,
    FilterUpdate,
    FilterWheelCreate,
    FilterWheelResponse,
    FilterWheelUpdate,
    FocuserCreate,
    FocuserResponse,
    FocuserTypeCreate,
    FocuserTypeResponse,
    FocuserTypeUpdate,
    FocuserUpdate,
    FormFactorCreate,
    FormFactorResponse,
    FormFactorUpdate,
    GuideScopeCreate,
    GuideScopeResponse,
    GuideScopeUpdate,
    ManufacturerCreate,
    ManufacturerResponse,
    ManufacturerUpdate,
    MineCountsResponse,
    MineToggle,
    MountCreate,
    MountResponse,
    MountTypeCreate,
    MountTypeResponse,
    MountTypeUpdate,
    MountUpdate,
    OagCreate,
    OagResponse,
    OagUpdate,
    OpticalDesignCreate,
    OpticalDesignResponse,
    OpticalDesignUpdate,
    SensorCreate,
    SensorResponse,
    SensorUpdate,
    SoftwareCreate,
    SoftwareResponse,
    SoftwareUpdate,
    TelescopeConfigurationCreate,
    TelescopeConfigurationResponse,
    TelescopeConfigurationUpdate,
    TelescopeCreate,
    TelescopeResponse,
    TelescopeUpdate,
)
from nightcrate.db.session import get_db

router = APIRouter(prefix="/api/equipment", tags=["Equipment"])
lookup_router = APIRouter(prefix="/api/equipment", tags=["Lookup Tables"])


# ── Mine counts ───────────────────────────────────────────────────────────────


@router.get("/mine-counts", response_model=MineCountsResponse)
async def get_mine_counts():
    """Per-type counts of equipment marked as mine. Retired items still count."""
    mapping = {
        "cameras": "camera",
        "telescopes": "telescope",
        "filters": "filter",
        "mounts": "mount",
        "focusers": "focuser",
        "filter_wheels": "filter_wheel",
        "oags": "oag",
        "guide_scopes": "guide_scope",
        "computers": "computer",
        "software": "software",
    }
    counts: dict[str, int] = {}
    async with get_db() as conn:
        for response_key, table in mapping.items():
            row = await (
                await conn.execute(f"SELECT COUNT(*) FROM {table} WHERE is_mine = 1")  # nosec B608 - table name from internal allow-list, not user input
            ).fetchone()
            counts[response_key] = row[0] if row else 0
    return counts


# ── Helpers ──────────────────────────────────────────────────────────────────
_row_to_dict = row_to_dict
_bool_fields = bool_fields
_strip_seed = strip_seed


_RESTORABLE_TABLES = frozenset(
    {
        "manufacturer",
        "optical_design",
        "mount_type",
        "connection_interface",
        "connector_size",
        "filter_size",
        "form_factor",
        "focuser_type",
        "filter_type",
        "sensor",
        "camera",
        "telescope",
        "filter",
        "mount",
        "focuser",
        "filter_wheel",
        "oag",
        "guide_scope",
        "computer",
        "software",
    }
)


# ── Restore (generic) ────────────────────────────────────────────────────────


@router.post("/restore/{table_name}/{item_id}")
async def restore_item(table_name: str, item_id: int):
    """Restore a soft-deleted item by setting active=1."""
    if table_name not in _RESTORABLE_TABLES:
        raise HTTPException(status_code=400, detail=f"Unknown table: {table_name}")
    async with get_db() as conn:
        await get_or_404(conn, table_name, item_id, table_name)
        await conn.execute(
            f"UPDATE {table_name} SET active = 1 WHERE id = ?",  # nosec B608 - table name from internal allow-list, not user input
            (item_id,),
        )
        await conn.commit()
    return {"ok": True}


# ── Lookup tables (factory-built) ────────────────────────────────────────────


build_lookup_router(
    lookup_router,
    table="manufacturer",
    url_slug="manufacturer",
    label="Manufacturer",
    create_model=ManufacturerCreate,
    update_model=ManufacturerUpdate,
    response_model=ManufacturerResponse,
)
build_lookup_router(
    lookup_router,
    table="optical_design",
    url_slug="optical-design",
    label="Optical design",
    create_model=OpticalDesignCreate,
    update_model=OpticalDesignUpdate,
    response_model=OpticalDesignResponse,
)
build_lookup_router(
    lookup_router,
    table="mount_type",
    url_slug="mount-type",
    label="Mount type",
    create_model=MountTypeCreate,
    update_model=MountTypeUpdate,
    response_model=MountTypeResponse,
)
build_lookup_router(
    lookup_router,
    table="connection_interface",
    url_slug="connection-interface",
    label="Connection interface",
    create_model=ConnectionInterfaceCreate,
    update_model=ConnectionInterfaceUpdate,
    response_model=ConnectionInterfaceResponse,
)
build_lookup_router(
    lookup_router,
    table="connector_size",
    url_slug="connector-size",
    label="Connector size",
    create_model=ConnectorSizeCreate,
    update_model=ConnectorSizeUpdate,
    response_model=ConnectorSizeResponse,
)
build_lookup_router(
    lookup_router,
    table="filter_size",
    url_slug="filter-size",
    label="Filter size",
    create_model=FilterSizeCreate,
    update_model=FilterSizeUpdate,
    response_model=FilterSizeResponse,
)
build_lookup_router(
    lookup_router,
    table="form_factor",
    url_slug="form-factor",
    label="Form factor",
    create_model=FormFactorCreate,
    update_model=FormFactorUpdate,
    response_model=FormFactorResponse,
)
build_lookup_router(
    lookup_router,
    table="focuser_type",
    url_slug="focuser-type",
    label="Focuser type",
    create_model=FocuserTypeCreate,
    update_model=FocuserTypeUpdate,
    response_model=FocuserTypeResponse,
)
build_lookup_router(
    lookup_router,
    table="filter_type",
    url_slug="filter-type",
    label="Filter type",
    create_model=FilterTypeCreate,
    update_model=FilterTypeUpdate,
    response_model=FilterTypeResponse,
)


# ── Sensor ────────────────────────────────────────────────────────────────────

_SENSOR_JOIN_SQL = """
    SELECT s.*, m.id AS m_id, m.name AS m_name, m.website AS m_website,
           m.notes AS m_notes, m.active AS m_active,
           m.created_at AS m_created_at, m.updated_at AS m_updated_at
    FROM sensor s
    JOIN manufacturer m ON m.id = s.manufacturer_id
"""


def _build_sensor_response(d: dict) -> dict:
    """Extract joined manufacturer fields into nested dict."""
    _bool_fields(d, "active", "dual_gain")
    d["manufacturer"] = {
        "id": d.pop("m_id"),
        "name": d.pop("m_name"),
        "website": d.pop("m_website"),
        "notes": d.pop("m_notes"),
        "active": bool(d.pop("m_active")),
        "created_at": d.pop("m_created_at"),
        "updated_at": d.pop("m_updated_at"),
    }
    return d


@router.get("/sensor", response_model=list[SensorResponse])
async def list_sensors(
    include_retired: bool = Query(False, description="Include retired items"),
):
    async with get_db() as conn:
        where = "" if include_retired else "WHERE s.active = 1"
        rows = await conn.execute(f"{_SENSOR_JOIN_SQL} {where} ORDER BY m.name, s.model_name")
        return [_build_sensor_response(_row_to_dict(r)) for r in await rows.fetchall()]


@router.get("/sensor/{sensor_id}", response_model=SensorResponse)
async def get_sensor(sensor_id: int):
    async with get_db() as conn:
        row = await conn.execute(f"{_SENSOR_JOIN_SQL} WHERE s.id = ?", (sensor_id,))
        result = await row.fetchone()
        if result is None:
            raise HTTPException(status_code=404, detail=f"Sensor not found: {sensor_id}")
        return _build_sensor_response(_row_to_dict(result))


@router.post("/sensor", response_model=SensorResponse, status_code=201)
async def create_sensor(body: SensorCreate):
    async with get_db() as conn:
        with integrity_guard(conflict_detail=f"Sensor already exists: {body.model_name}"):
            cursor = await conn.execute(
                """INSERT INTO sensor (
                    manufacturer_id, model_name, sensor_type,
                    pixel_size_um, resolution_x, resolution_y,
                    sensor_width_mm, sensor_height_mm, adc_bit_depth,
                    full_well_capacity_ke, read_noise_e, peak_qe_pct,
                    bayer_pattern, dual_gain, notes, source_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    body.manufacturer_id,
                    body.model_name,
                    body.sensor_type,
                    body.pixel_size_um,
                    body.resolution_x,
                    body.resolution_y,
                    body.sensor_width_mm,
                    body.sensor_height_mm,
                    body.adc_bit_depth,
                    body.full_well_capacity_ke,
                    body.read_noise_e,
                    body.peak_qe_pct,
                    body.bayer_pattern,
                    int(body.dual_gain),
                    body.notes,
                    body.source_url,
                ),
            )
            await conn.commit()
        sensor_id = cursor.lastrowid
        row = await conn.execute(f"{_SENSOR_JOIN_SQL} WHERE s.id = ?", (sensor_id,))
        result = await row.fetchone()
        return _build_sensor_response(_row_to_dict(result))


@router.put("/sensor/{sensor_id}", response_model=SensorResponse)
async def update_sensor(sensor_id: int, body: SensorUpdate):
    async with get_db() as conn:
        await get_or_404(conn, "sensor", sensor_id, "Sensor")

        updates = body.model_dump(exclude_unset=True)
        if updates:
            # Convert bool dual_gain to int for SQLite
            if "dual_gain" in updates and updates["dual_gain"] is not None:
                updates["dual_gain"] = int(updates["dual_gain"])
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [sensor_id]
            with integrity_guard(
                conflict_detail="Sensor (manufacturer, model_name) already exists"
            ):
                await conn.execute(
                    f"UPDATE sensor SET {set_clause} WHERE id = ?",  # nosec B608 - table name from internal allow-list, not user input
                    values,
                )
                await conn.commit()

        row = await conn.execute(f"{_SENSOR_JOIN_SQL} WHERE s.id = ?", (sensor_id,))
        result = await row.fetchone()
        return _build_sensor_response(_row_to_dict(result))


@router.delete("/sensor/{sensor_id}")
async def delete_sensor(sensor_id: int):
    async with get_db() as conn:
        await get_or_404(conn, "sensor", sensor_id, "Sensor")
        await conn.execute(
            "UPDATE sensor SET active = 0 WHERE id = ?",
            (sensor_id,),
        )
        await conn.commit()
    return {"ok": True}


# ── Camera ────────────────────────────────────────────────────────────────────


async def _build_camera_response(conn, camera_row: dict) -> dict:
    """Build full camera response with nested objects."""
    d = dict(camera_row)
    _bool_fields(d, "active", "cooled", "tilt_adapter", "has_usb_hub", "is_mine")

    d["manufacturer"] = _bool_fields(
        await get_or_404(conn, "manufacturer", d.pop("manufacturer_id"), "Manufacturer"),
        "active",
    )

    sensor_row = await conn.execute(f"{_SENSOR_JOIN_SQL} WHERE s.id = ?", (d.pop("sensor_id"),))
    sensor_result = await sensor_row.fetchone()
    d["sensor"] = _build_sensor_response(_row_to_dict(sensor_result))

    guide_id = d.pop("guide_sensor_id")
    if guide_id:
        gs_row = await conn.execute(f"{_SENSOR_JOIN_SQL} WHERE s.id = ?", (guide_id,))
        gs_result = await gs_row.fetchone()
        d["guide_sensor"] = _build_sensor_response(_row_to_dict(gs_result))
    else:
        d["guide_sensor"] = None

    cs_id = d.pop("connector_size_id")
    if cs_id:
        d["connector_size"] = _bool_fields(
            await get_or_404(conn, "connector_size", cs_id, "Connector size"),
            "active",
        )
    else:
        d["connector_size"] = None

    uh_id = d.pop("usb_hub_interface_id")
    if uh_id:
        d["usb_hub_interface"] = _bool_fields(
            await get_or_404(conn, "connection_interface", uh_id, "Connection interface"),
            "active",
        )
    else:
        d["usb_hub_interface"] = None

    ifaces = await conn.execute(
        """
        SELECT ci.* FROM connection_interface ci
        JOIN camera_interface cai ON cai.interface_id = ci.id
        WHERE cai.camera_id = ?
        ORDER BY ci.name
        """,
        (d["id"],),
    )
    d["interfaces"] = [_bool_fields(_row_to_dict(r), "active") for r in await ifaces.fetchall()]

    _strip_seed(d)

    return d


build_equipment_router(
    router,
    table="camera",
    url_slug="camera",
    label="Camera",
    create_model=CameraCreate,
    update_model=CameraUpdate,
    response_model=CameraResponse,
    response_builder=_build_camera_response,
    bool_columns=("cooled", "tilt_adapter", "has_usb_hub", "is_mine"),
    interface_junction=("camera_interface", "camera_id"),
)


# ── Telescope ─────────────────────────────────────────────────────────────────


async def _build_telescope_response(conn, telescope_row: dict) -> dict:
    """Build full telescope response with nested objects."""
    d = dict(telescope_row)
    _bool_fields(d, "active", "is_mine")

    d["manufacturer"] = _bool_fields(
        await get_or_404(conn, "manufacturer", d.pop("manufacturer_id"), "Manufacturer"),
        "active",
    )

    od_id = d.pop("optical_design_id")
    if od_id:
        d["optical_design"] = _bool_fields(
            await get_or_404(conn, "optical_design", od_id, "Optical design"),
            "active",
        )
    else:
        d["optical_design"] = None

    connectors = await conn.execute(
        """
        SELECT cs.* FROM connector_size cs
        JOIN telescope_connector tc ON tc.connector_size_id = cs.id
        WHERE tc.telescope_id = ?
        ORDER BY cs.name
        """,
        (d["id"],),
    )
    d["connectors"] = [_bool_fields(_row_to_dict(r), "active") for r in await connectors.fetchall()]

    configs = await conn.execute(
        """
        SELECT * FROM telescope_configuration
        WHERE telescope_id = ? AND active = 1
        ORDER BY is_native DESC, config_name
        """,
        (d["id"],),
    )
    d["configurations"] = [
        _bool_fields(_row_to_dict(r), "active", "is_native") for r in await configs.fetchall()
    ]
    for cfg in d["configurations"]:
        _strip_seed(cfg)
        cfg.pop("active", None)

    _strip_seed(d)

    return d


@router.get("/telescope", response_model=list[TelescopeResponse])
async def list_telescopes(
    include_retired: bool = Query(False, description="Include retired items"),
    mine: bool = Query(False, description="Return only items marked as mine"),
):
    async with get_db() as conn:
        conditions = []
        if not include_retired:
            conditions.append("active = 1")
        if mine:
            conditions.append("is_mine = 1")
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = await conn.execute(
            f"SELECT * FROM telescope {where} ORDER BY is_mine DESC, model_name"  # nosec B608 - table name from internal allow-list, not user input
        )
        results = []
        for r in await rows.fetchall():
            results.append(await _build_telescope_response(conn, _row_to_dict(r)))
        return results


@router.get("/telescope/{telescope_id}", response_model=TelescopeResponse)
async def get_telescope(telescope_id: int):
    async with get_db() as conn:
        row = await get_or_404(conn, "telescope", telescope_id, "Telescope")
        return await _build_telescope_response(conn, row)


@router.post("/telescope", response_model=TelescopeResponse, status_code=201)
async def create_telescope(body: TelescopeCreate):
    async with get_db() as conn:
        with integrity_guard(conflict_detail=f"Telescope already exists: {body.model_name}"):
            cursor = await conn.execute(
                """INSERT INTO telescope (
                    manufacturer_id, optical_design_id, model_name,
                    aperture_mm, image_circle_mm, weight_kg, obstruction_pct, notes,
                    source_url, is_mine
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    body.manufacturer_id,
                    body.optical_design_id,
                    body.model_name,
                    body.aperture_mm,
                    body.image_circle_mm,
                    body.weight_kg,
                    body.obstruction_pct,
                    body.notes,
                    body.source_url,
                    int(body.is_mine),
                ),
            )
            await conn.commit()
        telescope_id = cursor.lastrowid
        for cs_id in body.connector_size_ids:
            await conn.execute(
                "INSERT INTO telescope_connector (telescope_id, connector_size_id) VALUES (?, ?)",
                (telescope_id, cs_id),
            )
        await conn.commit()
        row = await get_or_404(conn, "telescope", telescope_id, "Telescope")
        return await _build_telescope_response(conn, row)


@router.put("/telescope/{telescope_id}", response_model=TelescopeResponse)
async def update_telescope(telescope_id: int, body: TelescopeUpdate):
    async with get_db() as conn:
        await get_or_404(conn, "telescope", telescope_id, "Telescope")
        updates = body.model_dump(exclude_unset=True)
        connector_size_ids = updates.pop("connector_size_ids", None)
        if "is_mine" in updates and updates["is_mine"] is not None:
            updates["is_mine"] = int(updates["is_mine"])
        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [telescope_id]
            with integrity_guard(
                conflict_detail="Telescope (manufacturer, model_name) already exists"
            ):
                await conn.execute(
                    f"UPDATE telescope SET {set_clause} WHERE id = ?",  # nosec B608 - table name from internal allow-list, not user input
                    values,
                )
                await conn.commit()
        if connector_size_ids is not None:
            await conn.execute(
                "DELETE FROM telescope_connector WHERE telescope_id = ?", (telescope_id,)
            )
            for cs_id in connector_size_ids:
                await conn.execute(
                    "INSERT INTO telescope_connector (telescope_id, connector_size_id)"
                    " VALUES (?, ?)",
                    (telescope_id, cs_id),
                )
            await conn.commit()
        row = await get_or_404(conn, "telescope", telescope_id, "Telescope")
        return await _build_telescope_response(conn, row)


@router.delete("/telescope/{telescope_id}")
async def delete_telescope(telescope_id: int):
    async with get_db() as conn:
        await get_or_404(conn, "telescope", telescope_id, "Telescope")
        await conn.execute("UPDATE telescope SET active = 0 WHERE id = ?", (telescope_id,))
        await conn.commit()
    return {"ok": True}


@router.post("/telescope/{telescope_id}/mine", response_model=TelescopeResponse)
async def toggle_telescope_mine(telescope_id: int, body: MineToggle):
    async with get_db() as conn:
        await get_or_404(conn, "telescope", telescope_id, "Telescope")
        await conn.execute(
            "UPDATE telescope SET is_mine = ? WHERE id = ?",
            (int(body.is_mine), telescope_id),
        )
        await conn.commit()
        row = await get_or_404(conn, "telescope", telescope_id, "Telescope")
        return await _build_telescope_response(conn, row)


# ── Telescope configuration child endpoints ───────────────────────────────────


@router.post(
    "/telescope/{telescope_id}/configuration",
    response_model=TelescopeConfigurationResponse,
    status_code=201,
)
async def create_telescope_configuration(telescope_id: int, body: TelescopeConfigurationCreate):
    async with get_db() as conn:
        await get_or_404(conn, "telescope", telescope_id, "Telescope")
        with integrity_guard(
            conflict_detail=(
                f"Configuration name already exists for this telescope: {body.config_name}"
            ),
            constraint_map={
                "idx_telescope_configuration_one_native": (
                    "This telescope already has a native configuration (is_native=true)."
                ),
            },
        ):
            cursor = await conn.execute(
                """INSERT INTO telescope_configuration (
                    telescope_id, config_name, accessory_name, reduction_factor,
                    effective_focal_length_mm, effective_focal_ratio,
                    effective_image_circle_mm, effective_back_focus_mm,
                    is_native, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    telescope_id,
                    body.config_name,
                    body.accessory_name,
                    body.reduction_factor,
                    body.effective_focal_length_mm,
                    body.effective_focal_ratio,
                    body.effective_image_circle_mm,
                    body.effective_back_focus_mm,
                    int(body.is_native),
                    body.notes,
                ),
            )
            await conn.commit()
        config_id = cursor.lastrowid
        row = await conn.execute("SELECT * FROM telescope_configuration WHERE id = ?", (config_id,))
        result = await row.fetchone()
        cfg = _bool_fields(_row_to_dict(result), "active", "is_native")
        _strip_seed(cfg)
        cfg.pop("active", None)
        return cfg


@router.put(
    "/telescope/{telescope_id}/configuration/{config_id}",
    response_model=TelescopeConfigurationResponse,
)
async def update_telescope_configuration(
    telescope_id: int, config_id: int, body: TelescopeConfigurationUpdate
):
    async with get_db() as conn:
        await get_or_404(conn, "telescope", telescope_id, "Telescope")
        check = await conn.execute(
            "SELECT id FROM telescope_configuration WHERE id = ? AND telescope_id = ?",
            (config_id, telescope_id),
        )
        if await check.fetchone() is None:
            raise HTTPException(
                status_code=404,
                detail=f"Configuration not found: {config_id}",
            )
        updates = body.model_dump(exclude_unset=True)
        if updates:
            if "is_native" in updates and updates["is_native"] is not None:
                updates["is_native"] = int(updates["is_native"])
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [config_id]
            with integrity_guard(
                conflict_detail="Configuration name already exists for this telescope",
                constraint_map={
                    "idx_telescope_configuration_one_native": (
                        "This telescope already has a native configuration (is_native=true)."
                    ),
                },
            ):
                await conn.execute(
                    f"UPDATE telescope_configuration SET {set_clause} WHERE id = ?",  # nosec B608 - table name from internal allow-list, not user input
                    values,
                )
                await conn.commit()
        row = await conn.execute("SELECT * FROM telescope_configuration WHERE id = ?", (config_id,))
        result = await row.fetchone()
        cfg = _bool_fields(_row_to_dict(result), "active", "is_native")
        _strip_seed(cfg)
        cfg.pop("active", None)
        return cfg


@router.delete("/telescope/{telescope_id}/configuration/{config_id}")
async def delete_telescope_configuration(telescope_id: int, config_id: int):
    async with get_db() as conn:
        await get_or_404(conn, "telescope", telescope_id, "Telescope")
        check = await conn.execute(
            "SELECT id FROM telescope_configuration WHERE id = ? AND telescope_id = ?",
            (config_id, telescope_id),
        )
        if await check.fetchone() is None:
            raise HTTPException(
                status_code=404,
                detail=f"Configuration not found: {config_id}",
            )
        await conn.execute(
            "UPDATE telescope_configuration SET active = 0 WHERE id = ?", (config_id,)
        )
        await conn.commit()
    return {"ok": True}


# ── Filter ────────────────────────────────────────────────────────────────────


async def _build_filter_response(conn, filter_row: dict) -> dict:
    """Build full filter response with nested objects."""
    d = dict(filter_row)
    _bool_fields(d, "active", "is_mine")

    d["manufacturer"] = _bool_fields(
        await get_or_404(conn, "manufacturer", d.pop("manufacturer_id"), "Manufacturer"),
        "active",
    )
    d["filter_type"] = _bool_fields(
        await get_or_404(conn, "filter_type", d.pop("filter_type_id"), "Filter type"),
        "active",
    )

    pbs = await conn.execute(
        """
        SELECT * FROM filter_passband
        WHERE filter_id = ? AND active = 1
        ORDER BY central_wavelength_nm
        """,
        (d["id"],),
    )
    d["passbands"] = [_row_to_dict(r) for r in await pbs.fetchall()]
    for pb in d["passbands"]:
        _strip_seed(pb)
        for k in ("active", "created_at", "updated_at"):
            pb.pop(k, None)

    sos = await conn.execute(
        """
        SELECT * FROM filter_size_option
        WHERE filter_id = ? AND active = 1
        ORDER BY filter_size_id
        """,
        (d["id"],),
    )
    d["size_options"] = []
    for row in await sos.fetchall():
        so = _row_to_dict(row)
        fs_id = so.pop("filter_size_id")
        fs = _bool_fields(
            await get_or_404(conn, "filter_size", fs_id, "Filter size"),
            "active",
        )
        _strip_seed(fs)
        so["filter_size"] = fs
        _strip_seed(so)
        for k in ("active", "created_at", "updated_at"):
            so.pop(k, None)
        d["size_options"].append(so)

    _strip_seed(d)

    return d


@router.get("/filter", response_model=list[FilterResponse])
async def list_filters(
    include_retired: bool = Query(False, description="Include retired items"),
    mine: bool = Query(False, description="Return only items marked as mine"),
):
    async with get_db() as conn:
        conditions = []
        if not include_retired:
            conditions.append("active = 1")
        if mine:
            conditions.append("is_mine = 1")
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = await conn.execute(f"SELECT * FROM filter {where} ORDER BY is_mine DESC, model_name")  # nosec B608 - table name from internal allow-list, not user input
        results = []
        for r in await rows.fetchall():
            results.append(await _build_filter_response(conn, _row_to_dict(r)))
        return results


@router.get("/filter/{filter_id}", response_model=FilterResponse)
async def get_filter(filter_id: int):
    async with get_db() as conn:
        row = await get_or_404(conn, "filter", filter_id, "Filter")
        return await _build_filter_response(conn, row)


@router.post("/filter", response_model=FilterResponse, status_code=201)
async def create_filter(body: FilterCreate):
    async with get_db() as conn:
        with integrity_guard(conflict_detail=f"Filter already exists: {body.model_name}"):
            cursor = await conn.execute(
                """INSERT INTO filter (
                    manufacturer_id, filter_type_id, model_name,
                    peak_transmission_pct, notes, source_url, is_mine
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    body.manufacturer_id,
                    body.filter_type_id,
                    body.model_name,
                    body.peak_transmission_pct,
                    body.notes,
                    body.source_url,
                    int(body.is_mine),
                ),
            )
            await conn.commit()
        filter_id = cursor.lastrowid
        row = await get_or_404(conn, "filter", filter_id, "Filter")
        return await _build_filter_response(conn, row)


@router.put("/filter/{filter_id}", response_model=FilterResponse)
async def update_filter(filter_id: int, body: FilterUpdate):
    async with get_db() as conn:
        await get_or_404(conn, "filter", filter_id, "Filter")
        updates = body.model_dump(exclude_unset=True)
        if "is_mine" in updates and updates["is_mine"] is not None:
            updates["is_mine"] = int(updates["is_mine"])
        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [filter_id]
            with integrity_guard(
                conflict_detail="Filter (manufacturer, model_name) already exists"
            ):
                await conn.execute(
                    f"UPDATE filter SET {set_clause} WHERE id = ?",  # nosec B608 - table name from internal allow-list, not user input
                    values,
                )
                await conn.commit()
        row = await get_or_404(conn, "filter", filter_id, "Filter")
        return await _build_filter_response(conn, row)


@router.delete("/filter/{filter_id}")
async def delete_filter(filter_id: int):
    async with get_db() as conn:
        await get_or_404(conn, "filter", filter_id, "Filter")
        await conn.execute("UPDATE filter SET active = 0 WHERE id = ?", (filter_id,))
        await conn.commit()
    return {"ok": True}


@router.post("/filter/{filter_id}/mine", response_model=FilterResponse)
async def toggle_filter_mine(filter_id: int, body: MineToggle):
    async with get_db() as conn:
        await get_or_404(conn, "filter", filter_id, "Filter")
        await conn.execute(
            "UPDATE filter SET is_mine = ? WHERE id = ?",
            (int(body.is_mine), filter_id),
        )
        await conn.commit()
        row = await get_or_404(conn, "filter", filter_id, "Filter")
        return await _build_filter_response(conn, row)


# ── Filter passband child endpoints ───────────────────────────────────────────


@router.post(
    "/filter/{filter_id}/passband",
    response_model=FilterPassbandResponse,
    status_code=201,
)
async def create_filter_passband(filter_id: int, body: FilterPassbandCreate):
    async with get_db() as conn:
        await get_or_404(conn, "filter", filter_id, "Filter")
        try:
            cursor = await conn.execute(
                """INSERT INTO filter_passband (
                    filter_id, line_name, central_wavelength_nm,
                    bandwidth_nm, peak_transmission_pct
                ) VALUES (?, ?, ?, ?, ?)""",
                (
                    filter_id,
                    body.line_name,
                    body.central_wavelength_nm,
                    body.bandwidth_nm,
                    body.peak_transmission_pct,
                ),
            )
            await conn.commit()
        except Exception as exc:
            exc_str = str(exc)
            if "CHECK" in exc_str:
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid line_name: {body.line_name}",
                )
            raise
        passband_id = cursor.lastrowid
        row = await conn.execute("SELECT * FROM filter_passband WHERE id = ?", (passband_id,))
        result = await row.fetchone()
        pb = _row_to_dict(result)
        _strip_seed(pb)
        for k in ("active", "created_at", "updated_at"):
            pb.pop(k, None)
        return pb


@router.put(
    "/filter/{filter_id}/passband/{passband_id}",
    response_model=FilterPassbandResponse,
)
async def update_filter_passband(filter_id: int, passband_id: int, body: FilterPassbandUpdate):
    async with get_db() as conn:
        await get_or_404(conn, "filter", filter_id, "Filter")
        check = await conn.execute(
            "SELECT id FROM filter_passband WHERE id = ? AND filter_id = ?",
            (passband_id, filter_id),
        )
        if await check.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"Passband not found: {passband_id}")
        updates = body.model_dump(exclude_unset=True)
        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [passband_id]
            try:
                await conn.execute(
                    f"UPDATE filter_passband SET {set_clause} WHERE id = ?",  # nosec B608 - table name from internal allow-list, not user input
                    values,
                )
                await conn.commit()
            except Exception as exc:
                exc_str = str(exc)
                if "CHECK" in exc_str:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Invalid line_name: {updates.get('line_name')}",
                    )
                raise
        row = await conn.execute("SELECT * FROM filter_passband WHERE id = ?", (passband_id,))
        result = await row.fetchone()
        pb = _row_to_dict(result)
        _strip_seed(pb)
        for k in ("active", "created_at", "updated_at"):
            pb.pop(k, None)
        return pb


@router.delete("/filter/{filter_id}/passband/{passband_id}")
async def delete_filter_passband(filter_id: int, passband_id: int):
    async with get_db() as conn:
        await get_or_404(conn, "filter", filter_id, "Filter")
        check = await conn.execute(
            "SELECT id FROM filter_passband WHERE id = ? AND filter_id = ?",
            (passband_id, filter_id),
        )
        if await check.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"Passband not found: {passband_id}")
        await conn.execute("UPDATE filter_passband SET active = 0 WHERE id = ?", (passband_id,))
        await conn.commit()
    return {"ok": True}


# ── Filter size option child endpoints ──────────────────────────────────────


async def _build_size_option_response(conn, so_row) -> dict:
    so = _row_to_dict(so_row)
    fs = _bool_fields(
        await get_or_404(conn, "filter_size", so.pop("filter_size_id"), "Filter size"),
        "active",
    )
    _strip_seed(fs)
    so["filter_size"] = fs
    _strip_seed(so)
    for k in ("active", "created_at", "updated_at"):
        so.pop(k, None)
    return so


@router.post(
    "/filter/{filter_id}/size-option",
    response_model=FilterSizeOptionResponse,
    status_code=201,
)
async def create_filter_size_option(filter_id: int, body: FilterSizeOptionCreate):
    async with get_db() as conn:
        await get_or_404(conn, "filter", filter_id, "Filter")
        with integrity_guard(conflict_detail="This filter already offers that size"):
            cursor = await conn.execute(
                """INSERT INTO filter_size_option (
                    filter_id, filter_size_id, mounted_thickness_mm, notes
                ) VALUES (?, ?, ?, ?)""",
                (filter_id, body.filter_size_id, body.mounted_thickness_mm, body.notes),
            )
            await conn.commit()
        row = await conn.execute(
            "SELECT * FROM filter_size_option WHERE id = ?", (cursor.lastrowid,)
        )
        return await _build_size_option_response(conn, await row.fetchone())


@router.put(
    "/filter/{filter_id}/size-option/{option_id}",
    response_model=FilterSizeOptionResponse,
)
async def update_filter_size_option(filter_id: int, option_id: int, body: FilterSizeOptionUpdate):
    async with get_db() as conn:
        await get_or_404(conn, "filter", filter_id, "Filter")
        check = await conn.execute(
            "SELECT id FROM filter_size_option WHERE id = ? AND filter_id = ?",
            (option_id, filter_id),
        )
        if await check.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"Size option not found: {option_id}")
        updates = body.model_dump(exclude_unset=True)
        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [option_id]
            with integrity_guard(conflict_detail="This filter already offers that size"):
                await conn.execute(
                    f"UPDATE filter_size_option SET {set_clause} WHERE id = ?",  # nosec B608 - table name from internal allow-list, not user input
                    values,
                )
                await conn.commit()
        row = await conn.execute("SELECT * FROM filter_size_option WHERE id = ?", (option_id,))
        return await _build_size_option_response(conn, await row.fetchone())


@router.delete("/filter/{filter_id}/size-option/{option_id}")
async def delete_filter_size_option(filter_id: int, option_id: int):
    async with get_db() as conn:
        await get_or_404(conn, "filter", filter_id, "Filter")
        check = await conn.execute(
            "SELECT id FROM filter_size_option WHERE id = ? AND filter_id = ?",
            (option_id, filter_id),
        )
        if await check.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"Size option not found: {option_id}")
        await conn.execute("UPDATE filter_size_option SET active = 0 WHERE id = ?", (option_id,))
        await conn.commit()
    return {"ok": True}


# ── Mount ─────────────────────────────────────────────────────────────────────


async def _build_mount_response(conn, mount_row: dict) -> dict:
    """Build full mount response with nested objects."""
    d = dict(mount_row)
    _bool_fields(d, "active", "counterweight_required", "goto_capable", "is_mine")

    d["manufacturer"] = _bool_fields(
        await get_or_404(conn, "manufacturer", d.pop("manufacturer_id"), "Manufacturer"),
        "active",
    )

    mt_id = d.pop("mount_type_id")
    if mt_id:
        d["mount_type"] = _bool_fields(
            await get_or_404(conn, "mount_type", mt_id, "Mount type"),
            "active",
        )
    else:
        d["mount_type"] = None

    ifaces = await conn.execute(
        """
        SELECT ci.* FROM connection_interface ci
        JOIN mount_interface mi ON mi.interface_id = ci.id
        WHERE mi.mount_id = ?
        ORDER BY ci.name
        """,
        (d["id"],),
    )
    d["interfaces"] = [_bool_fields(_row_to_dict(r), "active") for r in await ifaces.fetchall()]

    _strip_seed(d)

    return d


build_equipment_router(
    router,
    table="mount",
    url_slug="mount",
    label="Mount",
    create_model=MountCreate,
    update_model=MountUpdate,
    response_model=MountResponse,
    response_builder=_build_mount_response,
    bool_columns=("counterweight_required", "goto_capable", "is_mine"),
    interface_junction=("mount_interface", "mount_id"),
)


# ── Focuser ───────────────────────────────────────────────────────────────────


async def _build_focuser_response(conn, focuser_row: dict) -> dict:
    """Build full focuser response with nested objects."""
    d = dict(focuser_row)
    _bool_fields(d, "active", "motorized", "temperature_compensation", "is_mine")

    d["manufacturer"] = _bool_fields(
        await get_or_404(conn, "manufacturer", d.pop("manufacturer_id"), "Manufacturer"),
        "active",
    )

    ft_id = d.pop("focuser_type_id")
    if ft_id:
        d["focuser_type"] = _bool_fields(
            await get_or_404(conn, "focuser_type", ft_id, "Focuser type"),
            "active",
        )
    else:
        d["focuser_type"] = None

    ifaces = await conn.execute(
        """
        SELECT ci.* FROM connection_interface ci
        JOIN focuser_interface fi ON fi.interface_id = ci.id
        WHERE fi.focuser_id = ?
        ORDER BY ci.name
        """,
        (d["id"],),
    )
    d["interfaces"] = [_bool_fields(_row_to_dict(r), "active") for r in await ifaces.fetchall()]

    _strip_seed(d)

    return d


build_equipment_router(
    router,
    table="focuser",
    url_slug="focuser",
    label="Focuser",
    create_model=FocuserCreate,
    update_model=FocuserUpdate,
    response_model=FocuserResponse,
    response_builder=_build_focuser_response,
    bool_columns=("motorized", "temperature_compensation", "is_mine"),
    interface_junction=("focuser_interface", "focuser_id"),
)


# ── Filter Wheel ──────────────────────────────────────────────────────────────


async def _build_filter_wheel_response(conn, fw_row: dict) -> dict:
    """Build full filter wheel response with nested objects."""
    d = dict(fw_row)
    _bool_fields(d, "active", "is_mine")

    d["manufacturer"] = _bool_fields(
        await get_or_404(conn, "manufacturer", d.pop("manufacturer_id"), "Manufacturer"),
        "active",
    )

    fs_id = d.pop("filter_size_id")
    if fs_id:
        d["filter_size"] = _bool_fields(
            await get_or_404(conn, "filter_size", fs_id, "Filter size"),
            "active",
        )
    else:
        d["filter_size"] = None

    cs_cam_id = d.pop("camera_side_connector_id")
    if cs_cam_id:
        d["camera_side_connector"] = _bool_fields(
            await get_or_404(conn, "connector_size", cs_cam_id, "Connector size"),
            "active",
        )
    else:
        d["camera_side_connector"] = None

    cs_tel_id = d.pop("telescope_side_connector_id")
    if cs_tel_id:
        d["telescope_side_connector"] = _bool_fields(
            await get_or_404(conn, "connector_size", cs_tel_id, "Connector size"),
            "active",
        )
    else:
        d["telescope_side_connector"] = None

    ifaces = await conn.execute(
        """
        SELECT ci.* FROM connection_interface ci
        JOIN filter_wheel_interface fwi ON fwi.interface_id = ci.id
        WHERE fwi.filter_wheel_id = ?
        ORDER BY ci.name
        """,
        (d["id"],),
    )
    d["interfaces"] = [_bool_fields(_row_to_dict(r), "active") for r in await ifaces.fetchall()]

    _strip_seed(d)

    return d


build_equipment_router(
    router,
    table="filter_wheel",
    url_slug="filter-wheel",
    label="Filter wheel",
    create_model=FilterWheelCreate,
    update_model=FilterWheelUpdate,
    response_model=FilterWheelResponse,
    response_builder=_build_filter_wheel_response,
    interface_junction=("filter_wheel_interface", "filter_wheel_id"),
)


# ── OAG ───────────────────────────────────────────────────────────────────────


async def _build_oag_response(conn, oag_row: dict) -> dict:
    """Build full OAG response with nested objects."""
    d = dict(oag_row)
    _bool_fields(d, "active", "is_mine")

    d["manufacturer"] = _bool_fields(
        await get_or_404(conn, "manufacturer", d.pop("manufacturer_id"), "Manufacturer"),
        "active",
    )

    isc_id = d.pop("imaging_side_connector_id")
    if isc_id:
        d["imaging_side_connector"] = _bool_fields(
            await get_or_404(conn, "connector_size", isc_id, "Connector size"),
            "active",
        )
    else:
        d["imaging_side_connector"] = None

    gcc_id = d.pop("guide_camera_connector_id")
    if gcc_id:
        d["guide_camera_connector"] = _bool_fields(
            await get_or_404(conn, "connector_size", gcc_id, "Connector size"),
            "active",
        )
    else:
        d["guide_camera_connector"] = None

    _strip_seed(d)

    return d


build_equipment_router(
    router,
    table="oag",
    url_slug="oag",
    label="OAG",
    create_model=OagCreate,
    update_model=OagUpdate,
    response_model=OagResponse,
    response_builder=_build_oag_response,
)


# ── Guide Scope ───────────────────────────────────────────────────────────────


async def _build_guide_scope_response(conn, gs_row: dict) -> dict:
    """Build full guide scope response with nested objects."""
    d = dict(gs_row)
    _bool_fields(d, "active", "is_mine")

    d["manufacturer"] = _bool_fields(
        await get_or_404(conn, "manufacturer", d.pop("manufacturer_id"), "Manufacturer"),
        "active",
    )

    gcc_id = d.pop("guide_camera_connector_id")
    if gcc_id:
        d["guide_camera_connector"] = _bool_fields(
            await get_or_404(conn, "connector_size", gcc_id, "Connector size"),
            "active",
        )
    else:
        d["guide_camera_connector"] = None

    _strip_seed(d)

    return d


build_equipment_router(
    router,
    table="guide_scope",
    url_slug="guide-scope",
    label="Guide scope",
    create_model=GuideScopeCreate,
    update_model=GuideScopeUpdate,
    response_model=GuideScopeResponse,
    response_builder=_build_guide_scope_response,
)


# ── Computer ──────────────────────────────────────────────────────────────────


async def _build_computer_response(conn, computer_row: dict) -> dict:
    """Build full computer response with nested objects."""
    d = dict(computer_row)
    _bool_fields(d, "active", "is_mine")

    d["manufacturer"] = _bool_fields(
        await get_or_404(conn, "manufacturer", d.pop("manufacturer_id"), "Manufacturer"),
        "active",
    )

    ct_id = d.pop("form_factor_id")
    if ct_id:
        d["form_factor"] = _bool_fields(
            await get_or_404(conn, "form_factor", ct_id, "Form factor"),
            "active",
        )
    else:
        d["form_factor"] = None

    _strip_seed(d)

    return d


build_equipment_router(
    router,
    table="computer",
    url_slug="computer",
    label="Computer",
    create_model=ComputerCreate,
    update_model=ComputerUpdate,
    response_model=ComputerResponse,
    response_builder=_build_computer_response,
)


# ── Software ──────────────────────────────────────────────────────────────────


async def _build_software_response(conn, sw_row: dict) -> dict:
    """Build full software response with nested objects."""
    d = dict(sw_row)
    _bool_fields(d, "active", "is_mine")

    mfr_id = d.pop("manufacturer_id")
    if mfr_id:
        d["manufacturer"] = _bool_fields(
            await get_or_404(conn, "manufacturer", mfr_id, "Manufacturer"),
            "active",
        )
    else:
        d["manufacturer"] = None

    _strip_seed(d)

    return d


build_equipment_router(
    router,
    table="software",
    url_slug="software",
    label="Software",
    create_model=SoftwareCreate,
    update_model=SoftwareUpdate,
    response_model=SoftwareResponse,
    response_builder=_build_software_response,
    name_column="name",
    order_by="is_mine DESC, name",
    check_detail_fn=lambda d: f"Invalid category: {d.get('category')}",
)
