"""Equipment management API endpoints — CRUD for all equipment types."""

from fastapi import APIRouter, HTTPException, Query

from nightcrate.api.equipment_models import (
    ComputerTypeCreate,
    ComputerTypeResponse,
    ComputerTypeUpdate,
    ConnectionInterfaceCreate,
    ConnectionInterfaceResponse,
    ConnectionInterfaceUpdate,
    ConnectorSizeCreate,
    ConnectorSizeResponse,
    ConnectorSizeUpdate,
    FilterSizeCreate,
    FilterSizeResponse,
    FilterSizeUpdate,
    FilterTypeResponse,
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
