"""Equipment management API endpoints — CRUD for all equipment types."""

from fastapi import APIRouter, HTTPException, Query

from nightcrate.api.equipment_models import (
    CameraCreate,
    CameraResponse,
    CameraUpdate,
    ComputerTypeCreate,
    ComputerTypeResponse,
    ComputerTypeUpdate,
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
    FilterSizeResponse,
    FilterSizeUpdate,
    FilterTypeResponse,
    FilterUpdate,
    ManufacturerCreate,
    ManufacturerResponse,
    ManufacturerUpdate,
    MountTypeCreate,
    MountTypeResponse,
    MountTypeUpdate,
    OpticalDesignCreate,
    OpticalDesignResponse,
    OpticalDesignUpdate,
    SensorCreate,
    SensorResponse,
    SensorUpdate,
    TelescopeConfigurationCreate,
    TelescopeConfigurationResponse,
    TelescopeConfigurationUpdate,
    TelescopeCreate,
    TelescopeResponse,
    TelescopeUpdate,
)
from nightcrate.db.session import get_db

router = APIRouter(prefix="/api/equipment", tags=["equipment"])


# ── Helpers ──────────────────────────────────────────────────────────────────


def _row_to_dict(row) -> dict:
    """Convert an aiosqlite.Row to a plain dict."""
    return dict(row)


def _bool_fields(d: dict, *keys) -> dict:
    """Convert integer 0/1 fields to Python bools for Pydantic."""
    for k in keys:
        if k in d and d[k] is not None:
            d[k] = bool(d[k])
    return d


async def _get_or_404(conn, table: str, row_id: int, label: str = "Item") -> dict:
    """Fetch a single row by ID or raise 404."""
    row = await conn.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,))
    result = await row.fetchone()
    if result is None:
        raise HTTPException(status_code=404, detail=f"{label} not found: {row_id}")
    return _row_to_dict(result)


# ── Manufacturer ─────────────────────────────────────────────────────────────


@router.get("/manufacturer", response_model=list[ManufacturerResponse])
async def list_manufacturers(
    include_retired: bool = Query(False, description="Include retired items"),
):
    async with get_db() as conn:
        where = "" if include_retired else "WHERE active = 1"
        rows = await conn.execute(f"SELECT * FROM manufacturer {where} ORDER BY name")
        return [_bool_fields(_row_to_dict(r), "active") for r in await rows.fetchall()]


@router.get("/manufacturer/{manufacturer_id}", response_model=ManufacturerResponse)
async def get_manufacturer(manufacturer_id: int):
    async with get_db() as conn:
        return _bool_fields(
            await _get_or_404(conn, "manufacturer", manufacturer_id, "Manufacturer"),
            "active",
        )


@router.post("/manufacturer", response_model=ManufacturerResponse, status_code=201)
async def create_manufacturer(body: ManufacturerCreate):
    async with get_db() as conn:
        try:
            cursor = await conn.execute(
                "INSERT INTO manufacturer (name, website, notes) VALUES (?, ?, ?)",
                (body.name, body.website, body.notes),
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(
                    status_code=409, detail=f"Manufacturer already exists: {body.name}"
                )
            raise
        row_id = cursor.lastrowid
        return _bool_fields(
            await _get_or_404(conn, "manufacturer", row_id, "Manufacturer"),
            "active",
        )


@router.put("/manufacturer/{manufacturer_id}", response_model=ManufacturerResponse)
async def update_manufacturer(manufacturer_id: int, body: ManufacturerUpdate):
    async with get_db() as conn:
        existing = await _get_or_404(conn, "manufacturer", manufacturer_id, "Manufacturer")
        updates = body.model_dump(exclude_unset=True)
        if not updates:
            return _bool_fields(existing, "active")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [manufacturer_id]
        try:
            await conn.execute(
                f"UPDATE manufacturer SET {set_clause} WHERE id = ?",
                values,
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(status_code=409, detail="Manufacturer name already exists")
            raise
        return _bool_fields(
            await _get_or_404(conn, "manufacturer", manufacturer_id, "Manufacturer"),
            "active",
        )


@router.delete("/manufacturer/{manufacturer_id}")
async def delete_manufacturer(manufacturer_id: int):
    async with get_db() as conn:
        await _get_or_404(conn, "manufacturer", manufacturer_id, "Manufacturer")
        await conn.execute(
            "UPDATE manufacturer SET active = 0 WHERE id = ?",
            (manufacturer_id,),
        )
        await conn.commit()
    return {"ok": True}


# ── Optical Design ────────────────────────────────────────────────────────────


@router.get("/optical-design", response_model=list[OpticalDesignResponse])
async def list_optical_designs(
    include_retired: bool = Query(False, description="Include retired items"),
):
    async with get_db() as conn:
        where = "" if include_retired else "WHERE active = 1"
        rows = await conn.execute(f"SELECT * FROM optical_design {where} ORDER BY name")
        return [_bool_fields(_row_to_dict(r), "active") for r in await rows.fetchall()]


@router.get("/optical-design/{optical_design_id}", response_model=OpticalDesignResponse)
async def get_optical_design(optical_design_id: int):
    async with get_db() as conn:
        return _bool_fields(
            await _get_or_404(conn, "optical_design", optical_design_id, "Optical design"),
            "active",
        )


@router.post("/optical-design", response_model=OpticalDesignResponse, status_code=201)
async def create_optical_design(body: OpticalDesignCreate):
    async with get_db() as conn:
        try:
            cursor = await conn.execute(
                "INSERT INTO optical_design (name, description) VALUES (?, ?)",
                (body.name, body.description),
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(
                    status_code=409, detail=f"Optical design already exists: {body.name}"
                )
            raise
        row_id = cursor.lastrowid
        return _bool_fields(
            await _get_or_404(conn, "optical_design", row_id, "Optical design"),
            "active",
        )


@router.put("/optical-design/{optical_design_id}", response_model=OpticalDesignResponse)
async def update_optical_design(optical_design_id: int, body: OpticalDesignUpdate):
    async with get_db() as conn:
        existing = await _get_or_404(conn, "optical_design", optical_design_id, "Optical design")
        updates = body.model_dump(exclude_unset=True)
        if not updates:
            return _bool_fields(existing, "active")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [optical_design_id]
        try:
            await conn.execute(
                f"UPDATE optical_design SET {set_clause} WHERE id = ?",
                values,
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(status_code=409, detail="Optical design name already exists")
            raise
        return _bool_fields(
            await _get_or_404(conn, "optical_design", optical_design_id, "Optical design"),
            "active",
        )


@router.delete("/optical-design/{optical_design_id}")
async def delete_optical_design(optical_design_id: int):
    async with get_db() as conn:
        await _get_or_404(conn, "optical_design", optical_design_id, "Optical design")
        await conn.execute(
            "UPDATE optical_design SET active = 0 WHERE id = ?",
            (optical_design_id,),
        )
        await conn.commit()
    return {"ok": True}


# ── Mount Type ────────────────────────────────────────────────────────────────


@router.get("/mount-type", response_model=list[MountTypeResponse])
async def list_mount_types(
    include_retired: bool = Query(False, description="Include retired items"),
):
    async with get_db() as conn:
        where = "" if include_retired else "WHERE active = 1"
        rows = await conn.execute(f"SELECT * FROM mount_type {where} ORDER BY name")
        return [_bool_fields(_row_to_dict(r), "active") for r in await rows.fetchall()]


@router.get("/mount-type/{mount_type_id}", response_model=MountTypeResponse)
async def get_mount_type(mount_type_id: int):
    async with get_db() as conn:
        return _bool_fields(
            await _get_or_404(conn, "mount_type", mount_type_id, "Mount type"),
            "active",
        )


@router.post("/mount-type", response_model=MountTypeResponse, status_code=201)
async def create_mount_type(body: MountTypeCreate):
    async with get_db() as conn:
        try:
            cursor = await conn.execute(
                "INSERT INTO mount_type (name, description) VALUES (?, ?)",
                (body.name, body.description),
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(
                    status_code=409, detail=f"Mount type already exists: {body.name}"
                )
            raise
        row_id = cursor.lastrowid
        return _bool_fields(
            await _get_or_404(conn, "mount_type", row_id, "Mount type"),
            "active",
        )


@router.put("/mount-type/{mount_type_id}", response_model=MountTypeResponse)
async def update_mount_type(mount_type_id: int, body: MountTypeUpdate):
    async with get_db() as conn:
        existing = await _get_or_404(conn, "mount_type", mount_type_id, "Mount type")
        updates = body.model_dump(exclude_unset=True)
        if not updates:
            return _bool_fields(existing, "active")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [mount_type_id]
        try:
            await conn.execute(
                f"UPDATE mount_type SET {set_clause} WHERE id = ?",
                values,
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(status_code=409, detail="Mount type name already exists")
            raise
        return _bool_fields(
            await _get_or_404(conn, "mount_type", mount_type_id, "Mount type"),
            "active",
        )


@router.delete("/mount-type/{mount_type_id}")
async def delete_mount_type(mount_type_id: int):
    async with get_db() as conn:
        await _get_or_404(conn, "mount_type", mount_type_id, "Mount type")
        await conn.execute(
            "UPDATE mount_type SET active = 0 WHERE id = ?",
            (mount_type_id,),
        )
        await conn.commit()
    return {"ok": True}


# ── Connection Interface ──────────────────────────────────────────────────────


@router.get("/connection-interface", response_model=list[ConnectionInterfaceResponse])
async def list_connection_interfaces(
    include_retired: bool = Query(False, description="Include retired items"),
):
    async with get_db() as conn:
        where = "" if include_retired else "WHERE active = 1"
        rows = await conn.execute(f"SELECT * FROM connection_interface {where} ORDER BY name")
        return [_bool_fields(_row_to_dict(r), "active") for r in await rows.fetchall()]


@router.get(
    "/connection-interface/{connection_interface_id}",
    response_model=ConnectionInterfaceResponse,
)
async def get_connection_interface(connection_interface_id: int):
    async with get_db() as conn:
        return _bool_fields(
            await _get_or_404(
                conn, "connection_interface", connection_interface_id, "Connection interface"
            ),
            "active",
        )


@router.post("/connection-interface", response_model=ConnectionInterfaceResponse, status_code=201)
async def create_connection_interface(body: ConnectionInterfaceCreate):
    async with get_db() as conn:
        try:
            cursor = await conn.execute(
                "INSERT INTO connection_interface (name, category, notes) VALUES (?, ?, ?)",
                (body.name, body.category, body.notes),
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(
                    status_code=409,
                    detail=f"Connection interface already exists: {body.name}",
                )
            raise
        row_id = cursor.lastrowid
        return _bool_fields(
            await _get_or_404(conn, "connection_interface", row_id, "Connection interface"),
            "active",
        )


@router.put(
    "/connection-interface/{connection_interface_id}",
    response_model=ConnectionInterfaceResponse,
)
async def update_connection_interface(
    connection_interface_id: int, body: ConnectionInterfaceUpdate
):
    async with get_db() as conn:
        existing = await _get_or_404(
            conn, "connection_interface", connection_interface_id, "Connection interface"
        )
        updates = body.model_dump(exclude_unset=True)
        if not updates:
            return _bool_fields(existing, "active")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [connection_interface_id]
        try:
            await conn.execute(
                f"UPDATE connection_interface SET {set_clause} WHERE id = ?",
                values,
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(
                    status_code=409, detail="Connection interface name already exists"
                )
            raise
        return _bool_fields(
            await _get_or_404(
                conn, "connection_interface", connection_interface_id, "Connection interface"
            ),
            "active",
        )


@router.delete("/connection-interface/{connection_interface_id}")
async def delete_connection_interface(connection_interface_id: int):
    async with get_db() as conn:
        await _get_or_404(
            conn, "connection_interface", connection_interface_id, "Connection interface"
        )
        await conn.execute(
            "UPDATE connection_interface SET active = 0 WHERE id = ?",
            (connection_interface_id,),
        )
        await conn.commit()
    return {"ok": True}


# ── Connector Size ────────────────────────────────────────────────────────────


@router.get("/connector-size", response_model=list[ConnectorSizeResponse])
async def list_connector_sizes(
    include_retired: bool = Query(False, description="Include retired items"),
):
    async with get_db() as conn:
        where = "" if include_retired else "WHERE active = 1"
        rows = await conn.execute(f"SELECT * FROM connector_size {where} ORDER BY name")
        return [_bool_fields(_row_to_dict(r), "active") for r in await rows.fetchall()]


@router.get("/connector-size/{connector_size_id}", response_model=ConnectorSizeResponse)
async def get_connector_size(connector_size_id: int):
    async with get_db() as conn:
        return _bool_fields(
            await _get_or_404(conn, "connector_size", connector_size_id, "Connector size"),
            "active",
        )


@router.post("/connector-size", response_model=ConnectorSizeResponse, status_code=201)
async def create_connector_size(body: ConnectorSizeCreate):
    async with get_db() as conn:
        try:
            cursor = await conn.execute(
                "INSERT INTO connector_size (name, diameter_mm, notes) VALUES (?, ?, ?)",
                (body.name, body.diameter_mm, body.notes),
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(
                    status_code=409, detail=f"Connector size already exists: {body.name}"
                )
            raise
        row_id = cursor.lastrowid
        return _bool_fields(
            await _get_or_404(conn, "connector_size", row_id, "Connector size"),
            "active",
        )


@router.put("/connector-size/{connector_size_id}", response_model=ConnectorSizeResponse)
async def update_connector_size(connector_size_id: int, body: ConnectorSizeUpdate):
    async with get_db() as conn:
        existing = await _get_or_404(conn, "connector_size", connector_size_id, "Connector size")
        updates = body.model_dump(exclude_unset=True)
        if not updates:
            return _bool_fields(existing, "active")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [connector_size_id]
        try:
            await conn.execute(
                f"UPDATE connector_size SET {set_clause} WHERE id = ?",
                values,
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(status_code=409, detail="Connector size name already exists")
            raise
        return _bool_fields(
            await _get_or_404(conn, "connector_size", connector_size_id, "Connector size"),
            "active",
        )


@router.delete("/connector-size/{connector_size_id}")
async def delete_connector_size(connector_size_id: int):
    async with get_db() as conn:
        await _get_or_404(conn, "connector_size", connector_size_id, "Connector size")
        await conn.execute(
            "UPDATE connector_size SET active = 0 WHERE id = ?",
            (connector_size_id,),
        )
        await conn.commit()
    return {"ok": True}


# ── Filter Size ───────────────────────────────────────────────────────────────


@router.get("/filter-size", response_model=list[FilterSizeResponse])
async def list_filter_sizes(
    include_retired: bool = Query(False, description="Include retired items"),
):
    async with get_db() as conn:
        where = "" if include_retired else "WHERE active = 1"
        rows = await conn.execute(f"SELECT * FROM filter_size {where} ORDER BY name")
        return [_bool_fields(_row_to_dict(r), "active") for r in await rows.fetchall()]


@router.get("/filter-size/{filter_size_id}", response_model=FilterSizeResponse)
async def get_filter_size(filter_size_id: int):
    async with get_db() as conn:
        return _bool_fields(
            await _get_or_404(conn, "filter_size", filter_size_id, "Filter size"),
            "active",
        )


@router.post("/filter-size", response_model=FilterSizeResponse, status_code=201)
async def create_filter_size(body: FilterSizeCreate):
    async with get_db() as conn:
        try:
            cursor = await conn.execute(
                "INSERT INTO filter_size (name, description) VALUES (?, ?)",
                (body.name, body.description),
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(
                    status_code=409, detail=f"Filter size already exists: {body.name}"
                )
            raise
        row_id = cursor.lastrowid
        return _bool_fields(
            await _get_or_404(conn, "filter_size", row_id, "Filter size"),
            "active",
        )


@router.put("/filter-size/{filter_size_id}", response_model=FilterSizeResponse)
async def update_filter_size(filter_size_id: int, body: FilterSizeUpdate):
    async with get_db() as conn:
        existing = await _get_or_404(conn, "filter_size", filter_size_id, "Filter size")
        updates = body.model_dump(exclude_unset=True)
        if not updates:
            return _bool_fields(existing, "active")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [filter_size_id]
        try:
            await conn.execute(
                f"UPDATE filter_size SET {set_clause} WHERE id = ?",
                values,
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(status_code=409, detail="Filter size name already exists")
            raise
        return _bool_fields(
            await _get_or_404(conn, "filter_size", filter_size_id, "Filter size"),
            "active",
        )


@router.delete("/filter-size/{filter_size_id}")
async def delete_filter_size(filter_size_id: int):
    async with get_db() as conn:
        await _get_or_404(conn, "filter_size", filter_size_id, "Filter size")
        await conn.execute(
            "UPDATE filter_size SET active = 0 WHERE id = ?",
            (filter_size_id,),
        )
        await conn.commit()
    return {"ok": True}


# ── Computer Type ─────────────────────────────────────────────────────────────


@router.get("/computer-type", response_model=list[ComputerTypeResponse])
async def list_computer_types(
    include_retired: bool = Query(False, description="Include retired items"),
):
    async with get_db() as conn:
        where = "" if include_retired else "WHERE active = 1"
        rows = await conn.execute(f"SELECT * FROM computer_type {where} ORDER BY name")
        return [_bool_fields(_row_to_dict(r), "active") for r in await rows.fetchall()]


@router.get("/computer-type/{computer_type_id}", response_model=ComputerTypeResponse)
async def get_computer_type(computer_type_id: int):
    async with get_db() as conn:
        return _bool_fields(
            await _get_or_404(conn, "computer_type", computer_type_id, "Computer type"),
            "active",
        )


@router.post("/computer-type", response_model=ComputerTypeResponse, status_code=201)
async def create_computer_type(body: ComputerTypeCreate):
    async with get_db() as conn:
        try:
            cursor = await conn.execute(
                "INSERT INTO computer_type (name, description) VALUES (?, ?)",
                (body.name, body.description),
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(
                    status_code=409, detail=f"Computer type already exists: {body.name}"
                )
            raise
        row_id = cursor.lastrowid
        return _bool_fields(
            await _get_or_404(conn, "computer_type", row_id, "Computer type"),
            "active",
        )


@router.put("/computer-type/{computer_type_id}", response_model=ComputerTypeResponse)
async def update_computer_type(computer_type_id: int, body: ComputerTypeUpdate):
    async with get_db() as conn:
        existing = await _get_or_404(conn, "computer_type", computer_type_id, "Computer type")
        updates = body.model_dump(exclude_unset=True)
        if not updates:
            return _bool_fields(existing, "active")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [computer_type_id]
        try:
            await conn.execute(
                f"UPDATE computer_type SET {set_clause} WHERE id = ?",
                values,
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(status_code=409, detail="Computer type name already exists")
            raise
        return _bool_fields(
            await _get_or_404(conn, "computer_type", computer_type_id, "Computer type"),
            "active",
        )


@router.delete("/computer-type/{computer_type_id}")
async def delete_computer_type(computer_type_id: int):
    async with get_db() as conn:
        await _get_or_404(conn, "computer_type", computer_type_id, "Computer type")
        await conn.execute(
            "UPDATE computer_type SET active = 0 WHERE id = ?",
            (computer_type_id,),
        )
        await conn.commit()
    return {"ok": True}


# ── Filter Type (read-only) ───────────────────────────────────────────────────


@router.get("/filter-type", response_model=list[FilterTypeResponse])
async def list_filter_types(
    include_retired: bool = Query(False, description="Include retired items"),
):
    async with get_db() as conn:
        where = "" if include_retired else "WHERE active = 1"
        rows = await conn.execute(f"SELECT * FROM filter_type {where} ORDER BY name")
        return [_bool_fields(_row_to_dict(r), "active") for r in await rows.fetchall()]


@router.get("/filter-type/{filter_type_id}", response_model=FilterTypeResponse)
async def get_filter_type(filter_type_id: int):
    async with get_db() as conn:
        return _bool_fields(
            await _get_or_404(conn, "filter_type", filter_type_id, "Filter type"),
            "active",
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
        try:
            cursor = await conn.execute(
                """INSERT INTO sensor (
                    manufacturer_id, model_name, sensor_type,
                    pixel_size_um, resolution_x, resolution_y,
                    sensor_width_mm, sensor_height_mm, adc_bit_depth,
                    full_well_capacity_ke, read_noise_e, peak_qe_pct,
                    bayer_pattern, dual_gain, hcg_threshold_gain, notes
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
                    body.hcg_threshold_gain,
                    body.notes,
                ),
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(
                    status_code=409,
                    detail=f"Sensor already exists: {body.model_name}",
                )
            raise
        sensor_id = cursor.lastrowid
        row = await conn.execute(f"{_SENSOR_JOIN_SQL} WHERE s.id = ?", (sensor_id,))
        result = await row.fetchone()
        return _build_sensor_response(_row_to_dict(result))


@router.put("/sensor/{sensor_id}", response_model=SensorResponse)
async def update_sensor(sensor_id: int, body: SensorUpdate):
    async with get_db() as conn:
        # Verify exists
        check = await conn.execute("SELECT id FROM sensor WHERE id = ?", (sensor_id,))
        if await check.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"Sensor not found: {sensor_id}")

        updates = body.model_dump(exclude_unset=True)
        if updates:
            # Convert bool dual_gain to int for SQLite
            if "dual_gain" in updates and updates["dual_gain"] is not None:
                updates["dual_gain"] = int(updates["dual_gain"])
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [sensor_id]
            try:
                await conn.execute(
                    f"UPDATE sensor SET {set_clause} WHERE id = ?",
                    values,
                )
                await conn.commit()
            except Exception as exc:
                if "UNIQUE" in str(exc):
                    raise HTTPException(
                        status_code=409, detail="Sensor (manufacturer, model_name) already exists"
                    )
                raise

        row = await conn.execute(f"{_SENSOR_JOIN_SQL} WHERE s.id = ?", (sensor_id,))
        result = await row.fetchone()
        return _build_sensor_response(_row_to_dict(result))


@router.delete("/sensor/{sensor_id}")
async def delete_sensor(sensor_id: int):
    async with get_db() as conn:
        check = await conn.execute("SELECT id FROM sensor WHERE id = ?", (sensor_id,))
        if await check.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"Sensor not found: {sensor_id}")
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
    _bool_fields(d, "active", "cooled", "tilt_adapter", "has_usb_hub")

    d["manufacturer"] = _bool_fields(
        await _get_or_404(conn, "manufacturer", d.pop("manufacturer_id"), "Manufacturer"),
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
            await _get_or_404(conn, "connector_size", cs_id, "Connector size"),
            "active",
        )
    else:
        d["connector_size"] = None

    uh_id = d.pop("usb_hub_interface_id")
    if uh_id:
        d["usb_hub_interface"] = _bool_fields(
            await _get_or_404(conn, "connection_interface", uh_id, "Connection interface"),
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

    for k in ("source", "seed_key", "seed_hash"):
        d.pop(k, None)

    return d


@router.get("/camera", response_model=list[CameraResponse])
async def list_cameras(
    include_retired: bool = Query(False, description="Include retired items"),
):
    async with get_db() as conn:
        where = "" if include_retired else "WHERE active = 1"
        rows = await conn.execute(f"SELECT * FROM camera {where} ORDER BY model_name")
        results = []
        for r in await rows.fetchall():
            results.append(await _build_camera_response(conn, _row_to_dict(r)))
        return results


@router.get("/camera/{camera_id}", response_model=CameraResponse)
async def get_camera(camera_id: int):
    async with get_db() as conn:
        row = await _get_or_404(conn, "camera", camera_id, "Camera")
        return await _build_camera_response(conn, row)


@router.post("/camera", response_model=CameraResponse, status_code=201)
async def create_camera(body: CameraCreate):
    async with get_db() as conn:
        try:
            cursor = await conn.execute(
                """INSERT INTO camera (
                    manufacturer_id, sensor_id, guide_sensor_id, connector_size_id,
                    model_name, cooled, cooling_delta_c, back_focus_mm, weight_g,
                    tilt_adapter, has_usb_hub, usb_hub_interface_id, unity_gain, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    body.manufacturer_id,
                    body.sensor_id,
                    body.guide_sensor_id,
                    body.connector_size_id,
                    body.model_name,
                    int(body.cooled),
                    body.cooling_delta_c,
                    body.back_focus_mm,
                    body.weight_g,
                    int(body.tilt_adapter),
                    int(body.has_usb_hub),
                    body.usb_hub_interface_id,
                    body.unity_gain,
                    body.notes,
                ),
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(
                    status_code=409,
                    detail=f"Camera already exists: {body.model_name}",
                )
            raise
        camera_id = cursor.lastrowid
        for iface_id in body.interface_ids:
            await conn.execute(
                "INSERT INTO camera_interface (camera_id, interface_id) VALUES (?, ?)",
                (camera_id, iface_id),
            )
        await conn.commit()
        row = await _get_or_404(conn, "camera", camera_id, "Camera")
        return await _build_camera_response(conn, row)


@router.put("/camera/{camera_id}", response_model=CameraResponse)
async def update_camera(camera_id: int, body: CameraUpdate):
    async with get_db() as conn:
        await _get_or_404(conn, "camera", camera_id, "Camera")
        updates = body.model_dump(exclude_unset=True)
        interface_ids = updates.pop("interface_ids", None)
        if updates:
            for bool_field in ("cooled", "tilt_adapter", "has_usb_hub"):
                if bool_field in updates and updates[bool_field] is not None:
                    updates[bool_field] = int(updates[bool_field])
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [camera_id]
            try:
                await conn.execute(
                    f"UPDATE camera SET {set_clause} WHERE id = ?",
                    values,
                )
                await conn.commit()
            except Exception as exc:
                if "UNIQUE" in str(exc):
                    raise HTTPException(
                        status_code=409, detail="Camera (manufacturer, model_name) already exists"
                    )
                raise
        if interface_ids is not None:
            await conn.execute("DELETE FROM camera_interface WHERE camera_id = ?", (camera_id,))
            for iface_id in interface_ids:
                await conn.execute(
                    "INSERT INTO camera_interface (camera_id, interface_id) VALUES (?, ?)",
                    (camera_id, iface_id),
                )
            await conn.commit()
        row = await _get_or_404(conn, "camera", camera_id, "Camera")
        return await _build_camera_response(conn, row)


@router.delete("/camera/{camera_id}")
async def delete_camera(camera_id: int):
    async with get_db() as conn:
        await _get_or_404(conn, "camera", camera_id, "Camera")
        await conn.execute("UPDATE camera SET active = 0 WHERE id = ?", (camera_id,))
        await conn.commit()
    return {"ok": True}


# ── Telescope ─────────────────────────────────────────────────────────────────


async def _build_telescope_response(conn, telescope_row: dict) -> dict:
    """Build full telescope response with nested objects."""
    d = dict(telescope_row)
    _bool_fields(d, "active")

    d["manufacturer"] = _bool_fields(
        await _get_or_404(conn, "manufacturer", d.pop("manufacturer_id"), "Manufacturer"),
        "active",
    )

    od_id = d.pop("optical_design_id")
    if od_id:
        d["optical_design"] = _bool_fields(
            await _get_or_404(conn, "optical_design", od_id, "Optical design"),
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
        for k in ("active", "source", "seed_key", "seed_hash"):
            cfg.pop(k, None)

    for k in ("source", "seed_key", "seed_hash"):
        d.pop(k, None)

    return d


@router.get("/telescope", response_model=list[TelescopeResponse])
async def list_telescopes(
    include_retired: bool = Query(False, description="Include retired items"),
):
    async with get_db() as conn:
        where = "" if include_retired else "WHERE active = 1"
        rows = await conn.execute(f"SELECT * FROM telescope {where} ORDER BY model_name")
        results = []
        for r in await rows.fetchall():
            results.append(await _build_telescope_response(conn, _row_to_dict(r)))
        return results


@router.get("/telescope/{telescope_id}", response_model=TelescopeResponse)
async def get_telescope(telescope_id: int):
    async with get_db() as conn:
        row = await _get_or_404(conn, "telescope", telescope_id, "Telescope")
        return await _build_telescope_response(conn, row)


@router.post("/telescope", response_model=TelescopeResponse, status_code=201)
async def create_telescope(body: TelescopeCreate):
    async with get_db() as conn:
        try:
            cursor = await conn.execute(
                """INSERT INTO telescope (
                    manufacturer_id, optical_design_id, model_name,
                    aperture_mm, image_circle_mm, weight_kg, obstruction_pct, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    body.manufacturer_id,
                    body.optical_design_id,
                    body.model_name,
                    body.aperture_mm,
                    body.image_circle_mm,
                    body.weight_kg,
                    body.obstruction_pct,
                    body.notes,
                ),
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(
                    status_code=409,
                    detail=f"Telescope already exists: {body.model_name}",
                )
            raise
        telescope_id = cursor.lastrowid
        for cs_id in body.connector_size_ids:
            await conn.execute(
                "INSERT INTO telescope_connector (telescope_id, connector_size_id) VALUES (?, ?)",
                (telescope_id, cs_id),
            )
        await conn.commit()
        row = await _get_or_404(conn, "telescope", telescope_id, "Telescope")
        return await _build_telescope_response(conn, row)


@router.put("/telescope/{telescope_id}", response_model=TelescopeResponse)
async def update_telescope(telescope_id: int, body: TelescopeUpdate):
    async with get_db() as conn:
        await _get_or_404(conn, "telescope", telescope_id, "Telescope")
        updates = body.model_dump(exclude_unset=True)
        connector_size_ids = updates.pop("connector_size_ids", None)
        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [telescope_id]
            try:
                await conn.execute(
                    f"UPDATE telescope SET {set_clause} WHERE id = ?",
                    values,
                )
                await conn.commit()
            except Exception as exc:
                if "UNIQUE" in str(exc):
                    raise HTTPException(
                        status_code=409,
                        detail="Telescope (manufacturer, model_name) already exists",
                    )
                raise
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
        row = await _get_or_404(conn, "telescope", telescope_id, "Telescope")
        return await _build_telescope_response(conn, row)


@router.delete("/telescope/{telescope_id}")
async def delete_telescope(telescope_id: int):
    async with get_db() as conn:
        await _get_or_404(conn, "telescope", telescope_id, "Telescope")
        await conn.execute("UPDATE telescope SET active = 0 WHERE id = ?", (telescope_id,))
        await conn.commit()
    return {"ok": True}


# ── Telescope configuration child endpoints ───────────────────────────────────


@router.post(
    "/telescope/{telescope_id}/configuration",
    response_model=TelescopeConfigurationResponse,
    status_code=201,
)
async def create_telescope_configuration(telescope_id: int, body: TelescopeConfigurationCreate):
    async with get_db() as conn:
        await _get_or_404(conn, "telescope", telescope_id, "Telescope")
        try:
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
        except Exception as exc:
            exc_str = str(exc)
            if "UNIQUE" in exc_str and "idx_telescope_configuration_one_native" in exc_str:
                raise HTTPException(
                    status_code=409,
                    detail="This telescope already has a native configuration (is_native=true).",  # noqa: E501
                )
            if "UNIQUE" in exc_str:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Configuration name already exists for this telescope: {body.config_name}"
                    ),
                )
            raise
        config_id = cursor.lastrowid
        row = await conn.execute("SELECT * FROM telescope_configuration WHERE id = ?", (config_id,))
        result = await row.fetchone()
        cfg = _bool_fields(_row_to_dict(result), "active", "is_native")
        for k in ("active", "source", "seed_key", "seed_hash"):
            cfg.pop(k, None)
        return cfg


@router.put(
    "/telescope/{telescope_id}/configuration/{config_id}",
    response_model=TelescopeConfigurationResponse,
)
async def update_telescope_configuration(
    telescope_id: int, config_id: int, body: TelescopeConfigurationUpdate
):
    async with get_db() as conn:
        await _get_or_404(conn, "telescope", telescope_id, "Telescope")
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
            try:
                await conn.execute(
                    f"UPDATE telescope_configuration SET {set_clause} WHERE id = ?",
                    values,
                )
                await conn.commit()
            except Exception as exc:
                exc_str = str(exc)
                if "UNIQUE" in exc_str and "idx_telescope_configuration_one_native" in exc_str:
                    raise HTTPException(
                        status_code=409,
                        detail="This telescope already has a native configuration (is_native=true).",  # noqa: E501
                    )
                if "UNIQUE" in exc_str:
                    raise HTTPException(
                        status_code=409,
                        detail="Configuration name already exists for this telescope",
                    )
                raise
        row = await conn.execute("SELECT * FROM telescope_configuration WHERE id = ?", (config_id,))
        result = await row.fetchone()
        cfg = _bool_fields(_row_to_dict(result), "active", "is_native")
        for k in ("active", "source", "seed_key", "seed_hash"):
            cfg.pop(k, None)
        return cfg


@router.delete("/telescope/{telescope_id}/configuration/{config_id}")
async def delete_telescope_configuration(telescope_id: int, config_id: int):
    async with get_db() as conn:
        await _get_or_404(conn, "telescope", telescope_id, "Telescope")
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
    _bool_fields(d, "active")

    d["manufacturer"] = _bool_fields(
        await _get_or_404(conn, "manufacturer", d.pop("manufacturer_id"), "Manufacturer"),
        "active",
    )
    d["filter_type"] = _bool_fields(
        await _get_or_404(conn, "filter_type", d.pop("filter_type_id"), "Filter type"),
        "active",
    )

    fs_id = d.pop("filter_size_id")
    if fs_id:
        d["filter_size"] = _bool_fields(
            await _get_or_404(conn, "filter_size", fs_id, "Filter size"),
            "active",
        )
    else:
        d["filter_size"] = None

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
        for k in ("active", "source", "seed_key", "seed_hash", "created_at", "updated_at"):
            pb.pop(k, None)

    for k in ("source", "seed_key", "seed_hash"):
        d.pop(k, None)

    return d


@router.get("/filter", response_model=list[FilterResponse])
async def list_filters(
    include_retired: bool = Query(False, description="Include retired items"),
):
    async with get_db() as conn:
        where = "" if include_retired else "WHERE active = 1"
        rows = await conn.execute(f"SELECT * FROM filter {where} ORDER BY model_name")
        results = []
        for r in await rows.fetchall():
            results.append(await _build_filter_response(conn, _row_to_dict(r)))
        return results


@router.get("/filter/{filter_id}", response_model=FilterResponse)
async def get_filter(filter_id: int):
    async with get_db() as conn:
        row = await _get_or_404(conn, "filter", filter_id, "Filter")
        return await _build_filter_response(conn, row)


@router.post("/filter", response_model=FilterResponse, status_code=201)
async def create_filter(body: FilterCreate):
    async with get_db() as conn:
        try:
            cursor = await conn.execute(
                """INSERT INTO filter (
                    manufacturer_id, filter_type_id, filter_size_id, model_name,
                    peak_transmission_pct, mounted_thickness_mm, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    body.manufacturer_id,
                    body.filter_type_id,
                    body.filter_size_id,
                    body.model_name,
                    body.peak_transmission_pct,
                    body.mounted_thickness_mm,
                    body.notes,
                ),
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(
                    status_code=409,
                    detail=f"Filter already exists: {body.model_name}",
                )
            raise
        filter_id = cursor.lastrowid
        row = await _get_or_404(conn, "filter", filter_id, "Filter")
        return await _build_filter_response(conn, row)


@router.put("/filter/{filter_id}", response_model=FilterResponse)
async def update_filter(filter_id: int, body: FilterUpdate):
    async with get_db() as conn:
        await _get_or_404(conn, "filter", filter_id, "Filter")
        updates = body.model_dump(exclude_unset=True)
        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [filter_id]
            try:
                await conn.execute(
                    f"UPDATE filter SET {set_clause} WHERE id = ?",
                    values,
                )
                await conn.commit()
            except Exception as exc:
                if "UNIQUE" in str(exc):
                    raise HTTPException(
                        status_code=409,
                        detail="Filter (manufacturer, model_name) already exists",
                    )
                raise
        row = await _get_or_404(conn, "filter", filter_id, "Filter")
        return await _build_filter_response(conn, row)


@router.delete("/filter/{filter_id}")
async def delete_filter(filter_id: int):
    async with get_db() as conn:
        await _get_or_404(conn, "filter", filter_id, "Filter")
        await conn.execute("UPDATE filter SET active = 0 WHERE id = ?", (filter_id,))
        await conn.commit()
    return {"ok": True}


# ── Filter passband child endpoints ───────────────────────────────────────────


@router.post(
    "/filter/{filter_id}/passband",
    response_model=FilterPassbandResponse,
    status_code=201,
)
async def create_filter_passband(filter_id: int, body: FilterPassbandCreate):
    async with get_db() as conn:
        await _get_or_404(conn, "filter", filter_id, "Filter")
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
        for k in ("active", "source", "seed_key", "seed_hash", "created_at", "updated_at"):
            pb.pop(k, None)
        return pb


@router.put(
    "/filter/{filter_id}/passband/{passband_id}",
    response_model=FilterPassbandResponse,
)
async def update_filter_passband(filter_id: int, passband_id: int, body: FilterPassbandUpdate):
    async with get_db() as conn:
        await _get_or_404(conn, "filter", filter_id, "Filter")
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
                    f"UPDATE filter_passband SET {set_clause} WHERE id = ?",
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
        for k in ("active", "source", "seed_key", "seed_hash", "created_at", "updated_at"):
            pb.pop(k, None)
        return pb


@router.delete("/filter/{filter_id}/passband/{passband_id}")
async def delete_filter_passband(filter_id: int, passband_id: int):
    async with get_db() as conn:
        await _get_or_404(conn, "filter", filter_id, "Filter")
        check = await conn.execute(
            "SELECT id FROM filter_passband WHERE id = ? AND filter_id = ?",
            (passband_id, filter_id),
        )
        if await check.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"Passband not found: {passband_id}")
        await conn.execute("UPDATE filter_passband SET active = 0 WHERE id = ?", (passband_id,))
        await conn.commit()
    return {"ok": True}
