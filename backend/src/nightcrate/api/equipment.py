"""Equipment management API endpoints — CRUD for all equipment types."""

from fastapi import APIRouter, HTTPException, Query

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


_SEED_KEYS = ("source", "seed_key", "seed_hash")


def _strip_seed(d: dict) -> dict:
    """Remove seed-tracking columns from a response dict."""
    for k in _SEED_KEYS:
        d.pop(k, None)
    return d


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


async def _get_or_404(conn, table: str, row_id: int, label: str = "Item") -> dict:
    """Fetch a single row by ID or raise 404."""
    row = await conn.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,))
    result = await row.fetchone()
    if result is None:
        raise HTTPException(status_code=404, detail=f"{label} not found: {row_id}")
    return _row_to_dict(result)


# ── Restore (generic) ────────────────────────────────────────────────────────


@router.post("/restore/{table_name}/{item_id}")
async def restore_item(table_name: str, item_id: int):
    """Restore a soft-deleted item by setting active=1."""
    if table_name not in _RESTORABLE_TABLES:
        raise HTTPException(status_code=400, detail=f"Unknown table: {table_name}")
    async with get_db() as conn:
        await _get_or_404(conn, table_name, item_id, table_name)
        await conn.execute(
            f"UPDATE {table_name} SET active = 1 WHERE id = ?",
            (item_id,),
        )
        await conn.commit()
    return {"ok": True}


# ── Manufacturer ─────────────────────────────────────────────────────────────


@lookup_router.get("/manufacturer", response_model=list[ManufacturerResponse])
async def list_manufacturers(
    include_retired: bool = Query(False, description="Include retired items"),
):
    async with get_db() as conn:
        where = "" if include_retired else "WHERE active = 1"
        rows = await conn.execute(f"SELECT * FROM manufacturer {where} ORDER BY name")
        return [_bool_fields(_row_to_dict(r), "active") for r in await rows.fetchall()]


@lookup_router.get("/manufacturer/{manufacturer_id}", response_model=ManufacturerResponse)
async def get_manufacturer(manufacturer_id: int):
    async with get_db() as conn:
        return _bool_fields(
            await _get_or_404(conn, "manufacturer", manufacturer_id, "Manufacturer"),
            "active",
        )


@lookup_router.post("/manufacturer", response_model=ManufacturerResponse, status_code=201)
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


@lookup_router.put("/manufacturer/{manufacturer_id}", response_model=ManufacturerResponse)
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


@lookup_router.delete("/manufacturer/{manufacturer_id}")
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


@lookup_router.get("/optical-design", response_model=list[OpticalDesignResponse])
async def list_optical_designs(
    include_retired: bool = Query(False, description="Include retired items"),
):
    async with get_db() as conn:
        where = "" if include_retired else "WHERE active = 1"
        rows = await conn.execute(f"SELECT * FROM optical_design {where} ORDER BY name")
        return [_bool_fields(_row_to_dict(r), "active") for r in await rows.fetchall()]


@lookup_router.get("/optical-design/{optical_design_id}", response_model=OpticalDesignResponse)
async def get_optical_design(optical_design_id: int):
    async with get_db() as conn:
        return _bool_fields(
            await _get_or_404(conn, "optical_design", optical_design_id, "Optical design"),
            "active",
        )


@lookup_router.post("/optical-design", response_model=OpticalDesignResponse, status_code=201)
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


@lookup_router.put("/optical-design/{optical_design_id}", response_model=OpticalDesignResponse)
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


@lookup_router.delete("/optical-design/{optical_design_id}")
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


@lookup_router.get("/mount-type", response_model=list[MountTypeResponse])
async def list_mount_types(
    include_retired: bool = Query(False, description="Include retired items"),
):
    async with get_db() as conn:
        where = "" if include_retired else "WHERE active = 1"
        rows = await conn.execute(f"SELECT * FROM mount_type {where} ORDER BY name")
        return [_bool_fields(_row_to_dict(r), "active") for r in await rows.fetchall()]


@lookup_router.get("/mount-type/{mount_type_id}", response_model=MountTypeResponse)
async def get_mount_type(mount_type_id: int):
    async with get_db() as conn:
        return _bool_fields(
            await _get_or_404(conn, "mount_type", mount_type_id, "Mount type"),
            "active",
        )


@lookup_router.post("/mount-type", response_model=MountTypeResponse, status_code=201)
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


@lookup_router.put("/mount-type/{mount_type_id}", response_model=MountTypeResponse)
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


@lookup_router.delete("/mount-type/{mount_type_id}")
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


@lookup_router.get("/connection-interface", response_model=list[ConnectionInterfaceResponse])
async def list_connection_interfaces(
    include_retired: bool = Query(False, description="Include retired items"),
):
    async with get_db() as conn:
        where = "" if include_retired else "WHERE active = 1"
        rows = await conn.execute(f"SELECT * FROM connection_interface {where} ORDER BY name")
        return [_bool_fields(_row_to_dict(r), "active") for r in await rows.fetchall()]


@lookup_router.get(
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


@lookup_router.post(
    "/connection-interface", response_model=ConnectionInterfaceResponse, status_code=201
)
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


@lookup_router.put(
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


@lookup_router.delete("/connection-interface/{connection_interface_id}")
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


@lookup_router.get("/connector-size", response_model=list[ConnectorSizeResponse])
async def list_connector_sizes(
    include_retired: bool = Query(False, description="Include retired items"),
):
    async with get_db() as conn:
        where = "" if include_retired else "WHERE active = 1"
        rows = await conn.execute(f"SELECT * FROM connector_size {where} ORDER BY name")
        return [_bool_fields(_row_to_dict(r), "active") for r in await rows.fetchall()]


@lookup_router.get("/connector-size/{connector_size_id}", response_model=ConnectorSizeResponse)
async def get_connector_size(connector_size_id: int):
    async with get_db() as conn:
        return _bool_fields(
            await _get_or_404(conn, "connector_size", connector_size_id, "Connector size"),
            "active",
        )


@lookup_router.post("/connector-size", response_model=ConnectorSizeResponse, status_code=201)
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


@lookup_router.put("/connector-size/{connector_size_id}", response_model=ConnectorSizeResponse)
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


@lookup_router.delete("/connector-size/{connector_size_id}")
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


@lookup_router.get("/filter-size", response_model=list[FilterSizeResponse])
async def list_filter_sizes(
    include_retired: bool = Query(False, description="Include retired items"),
):
    async with get_db() as conn:
        where = "" if include_retired else "WHERE active = 1"
        rows = await conn.execute(f"SELECT * FROM filter_size {where} ORDER BY name")
        return [_bool_fields(_row_to_dict(r), "active") for r in await rows.fetchall()]


@lookup_router.get("/filter-size/{filter_size_id}", response_model=FilterSizeResponse)
async def get_filter_size(filter_size_id: int):
    async with get_db() as conn:
        return _bool_fields(
            await _get_or_404(conn, "filter_size", filter_size_id, "Filter size"),
            "active",
        )


@lookup_router.post("/filter-size", response_model=FilterSizeResponse, status_code=201)
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


@lookup_router.put("/filter-size/{filter_size_id}", response_model=FilterSizeResponse)
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


@lookup_router.delete("/filter-size/{filter_size_id}")
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


@lookup_router.get("/form-factor", response_model=list[FormFactorResponse])
async def list_form_factors(
    include_retired: bool = Query(False, description="Include retired items"),
):
    async with get_db() as conn:
        where = "" if include_retired else "WHERE active = 1"
        rows = await conn.execute(f"SELECT * FROM form_factor {where} ORDER BY name")
        return [_bool_fields(_row_to_dict(r), "active") for r in await rows.fetchall()]


@lookup_router.get("/form-factor/{form_factor_id}", response_model=FormFactorResponse)
async def get_form_factor(form_factor_id: int):
    async with get_db() as conn:
        return _bool_fields(
            await _get_or_404(conn, "form_factor", form_factor_id, "Form factor"),
            "active",
        )


@lookup_router.post("/form-factor", response_model=FormFactorResponse, status_code=201)
async def create_form_factor(body: FormFactorCreate):
    async with get_db() as conn:
        try:
            cursor = await conn.execute(
                "INSERT INTO form_factor (name, description) VALUES (?, ?)",
                (body.name, body.description),
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(
                    status_code=409, detail=f"Form factor already exists: {body.name}"
                )
            raise
        row_id = cursor.lastrowid
        return _bool_fields(
            await _get_or_404(conn, "form_factor", row_id, "Form factor"),
            "active",
        )


@lookup_router.put("/form-factor/{form_factor_id}", response_model=FormFactorResponse)
async def update_form_factor(form_factor_id: int, body: FormFactorUpdate):
    async with get_db() as conn:
        existing = await _get_or_404(conn, "form_factor", form_factor_id, "Form factor")
        updates = body.model_dump(exclude_unset=True)
        if not updates:
            return _bool_fields(existing, "active")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [form_factor_id]
        try:
            await conn.execute(
                f"UPDATE form_factor SET {set_clause} WHERE id = ?",
                values,
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(status_code=409, detail="Form factor name already exists")
            raise
        return _bool_fields(
            await _get_or_404(conn, "form_factor", form_factor_id, "Form factor"),
            "active",
        )


@lookup_router.delete("/form-factor/{form_factor_id}")
async def delete_form_factor(form_factor_id: int):
    async with get_db() as conn:
        await _get_or_404(conn, "form_factor", form_factor_id, "Form factor")
        await conn.execute(
            "UPDATE form_factor SET active = 0 WHERE id = ?",
            (form_factor_id,),
        )
        await conn.commit()
    return {"ok": True}


# ── Focuser Type ──────────────────────────────────────────────────────────────


@lookup_router.get("/focuser-type", response_model=list[FocuserTypeResponse])
async def list_focuser_types(
    include_retired: bool = Query(False, description="Include retired items"),
):
    async with get_db() as conn:
        where = "" if include_retired else "WHERE active = 1"
        rows = await conn.execute(f"SELECT * FROM focuser_type {where} ORDER BY name")
        return [_bool_fields(_row_to_dict(r), "active") for r in await rows.fetchall()]


@lookup_router.get("/focuser-type/{focuser_type_id}", response_model=FocuserTypeResponse)
async def get_focuser_type(focuser_type_id: int):
    async with get_db() as conn:
        return _bool_fields(
            await _get_or_404(conn, "focuser_type", focuser_type_id, "Focuser type"),
            "active",
        )


@lookup_router.post("/focuser-type", response_model=FocuserTypeResponse, status_code=201)
async def create_focuser_type(body: FocuserTypeCreate):
    async with get_db() as conn:
        try:
            cursor = await conn.execute(
                "INSERT INTO focuser_type (name, notes) VALUES (?, ?)",
                (body.name, body.notes),
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(
                    status_code=409, detail=f"Focuser type already exists: {body.name}"
                )
            raise
        row_id = cursor.lastrowid
        return _bool_fields(
            await _get_or_404(conn, "focuser_type", row_id, "Focuser type"),
            "active",
        )


@lookup_router.put("/focuser-type/{focuser_type_id}", response_model=FocuserTypeResponse)
async def update_focuser_type(focuser_type_id: int, body: FocuserTypeUpdate):
    async with get_db() as conn:
        existing = await _get_or_404(conn, "focuser_type", focuser_type_id, "Focuser type")
        updates = body.model_dump(exclude_unset=True)
        if not updates:
            return _bool_fields(existing, "active")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [focuser_type_id]
        try:
            await conn.execute(
                f"UPDATE focuser_type SET {set_clause} WHERE id = ?",
                values,
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(status_code=409, detail="Focuser type name already exists")
            raise
        return _bool_fields(
            await _get_or_404(conn, "focuser_type", focuser_type_id, "Focuser type"),
            "active",
        )


@lookup_router.delete("/focuser-type/{focuser_type_id}")
async def delete_focuser_type(focuser_type_id: int):
    async with get_db() as conn:
        await _get_or_404(conn, "focuser_type", focuser_type_id, "Focuser type")
        await conn.execute(
            "UPDATE focuser_type SET active = 0 WHERE id = ?",
            (focuser_type_id,),
        )
        await conn.commit()
    return {"ok": True}


# ── Filter Type (read-only) ───────────────────────────────────────────────────


@lookup_router.get("/filter-type", response_model=list[FilterTypeResponse])
async def list_filter_types(
    include_retired: bool = Query(False, description="Include retired items"),
):
    async with get_db() as conn:
        where = "" if include_retired else "WHERE active = 1"
        rows = await conn.execute(f"SELECT * FROM filter_type {where} ORDER BY name")
        return [_bool_fields(_row_to_dict(r), "active") for r in await rows.fetchall()]


@lookup_router.get("/filter-type/{filter_type_id}", response_model=FilterTypeResponse)
async def get_filter_type(filter_type_id: int):
    async with get_db() as conn:
        return _bool_fields(
            await _get_or_404(conn, "filter_type", filter_type_id, "Filter type"),
            "active",
        )


@lookup_router.post("/filter-type", response_model=FilterTypeResponse, status_code=201)
async def create_filter_type(body: FilterTypeCreate):
    async with get_db() as conn:
        try:
            cursor = await conn.execute(
                "INSERT INTO filter_type (name, display_name, description) VALUES (?, ?, ?)",
                (body.name, body.display_name, body.description),
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(
                    status_code=409, detail=f"Filter type already exists: {body.name}"
                )
            raise
        return _bool_fields(
            await _get_or_404(conn, "filter_type", cursor.lastrowid, "Filter type"),
            "active",
        )


@lookup_router.put("/filter-type/{filter_type_id}", response_model=FilterTypeResponse)
async def update_filter_type(filter_type_id: int, body: FilterTypeUpdate):
    async with get_db() as conn:
        existing = await _get_or_404(conn, "filter_type", filter_type_id, "Filter type")
        updates = body.model_dump(exclude_unset=True)
        if not updates:
            return _bool_fields(existing, "active")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [filter_type_id]
        try:
            await conn.execute(
                f"UPDATE filter_type SET {set_clause} WHERE id = ?",
                values,
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(status_code=409, detail="Filter type name already exists")
            raise
        return _bool_fields(
            await _get_or_404(conn, "filter_type", filter_type_id, "Filter type"),
            "active",
        )


@lookup_router.delete("/filter-type/{filter_type_id}")
async def delete_filter_type(filter_type_id: int):
    async with get_db() as conn:
        await _get_or_404(conn, "filter_type", filter_type_id, "Filter type")
        await conn.execute(
            "UPDATE filter_type SET active = 0 WHERE id = ?",
            (filter_type_id,),
        )
        await conn.commit()
    return {"ok": True}


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
        await _get_or_404(conn, "sensor", sensor_id, "Sensor")

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
        await _get_or_404(conn, "sensor", sensor_id, "Sensor")
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

    _strip_seed(d)

    return d


@router.get("/camera", response_model=list[CameraResponse])
async def list_cameras(
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
        rows = await conn.execute(f"SELECT * FROM camera {where} ORDER BY is_mine DESC, model_name")
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
                    tilt_adapter, has_usb_hub, usb_hub_interface_id, unity_gain,
                    effective_full_well_ke, effective_read_noise_lcg_e,
                    effective_read_noise_hcg_e, effective_peak_qe_pct,
                    hcg_threshold_gain, notes, source_url, is_mine
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                    body.effective_full_well_ke,
                    body.effective_read_noise_lcg_e,
                    body.effective_read_noise_hcg_e,
                    body.effective_peak_qe_pct,
                    body.hcg_threshold_gain,
                    body.notes,
                    body.source_url,
                    int(body.is_mine),
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


@router.post("/camera/{camera_id}/mine", response_model=CameraResponse)
async def toggle_camera_mine(camera_id: int, body: MineToggle):
    async with get_db() as conn:
        await _get_or_404(conn, "camera", camera_id, "Camera")
        await conn.execute(
            "UPDATE camera SET is_mine = ? WHERE id = ?",
            (int(body.is_mine), camera_id),
        )
        await conn.commit()
        row = await _get_or_404(conn, "camera", camera_id, "Camera")
        return await _build_camera_response(conn, row)


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
            f"SELECT * FROM telescope {where} ORDER BY is_mine DESC, model_name"
        )
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


@router.post("/telescope/{telescope_id}/mine", response_model=TelescopeResponse)
async def toggle_telescope_mine(telescope_id: int, body: MineToggle):
    async with get_db() as conn:
        await _get_or_404(conn, "telescope", telescope_id, "Telescope")
        await conn.execute(
            "UPDATE telescope SET is_mine = ? WHERE id = ?",
            (int(body.is_mine), telescope_id),
        )
        await conn.commit()
        row = await _get_or_404(conn, "telescope", telescope_id, "Telescope")
        return await _build_telescope_response(conn, row)


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
        _strip_seed(cfg)
        cfg.pop("active", None)
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
            await _get_or_404(conn, "filter_size", fs_id, "Filter size"),
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
        rows = await conn.execute(f"SELECT * FROM filter {where} ORDER BY is_mine DESC, model_name")
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


@router.post("/filter/{filter_id}/mine", response_model=FilterResponse)
async def toggle_filter_mine(filter_id: int, body: MineToggle):
    async with get_db() as conn:
        await _get_or_404(conn, "filter", filter_id, "Filter")
        await conn.execute(
            "UPDATE filter SET is_mine = ? WHERE id = ?",
            (int(body.is_mine), filter_id),
        )
        await conn.commit()
        row = await _get_or_404(conn, "filter", filter_id, "Filter")
        return await _build_filter_response(conn, row)


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
        _strip_seed(pb)
        for k in ("active", "created_at", "updated_at"):
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


# ── Filter size option child endpoints ──────────────────────────────────────


async def _build_size_option_response(conn, so_row) -> dict:
    so = _row_to_dict(so_row)
    fs = _bool_fields(
        await _get_or_404(conn, "filter_size", so.pop("filter_size_id"), "Filter size"),
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
        await _get_or_404(conn, "filter", filter_id, "Filter")
        try:
            cursor = await conn.execute(
                """INSERT INTO filter_size_option (
                    filter_id, filter_size_id, mounted_thickness_mm, notes
                ) VALUES (?, ?, ?, ?)""",
                (filter_id, body.filter_size_id, body.mounted_thickness_mm, body.notes),
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(status_code=409, detail="This filter already offers that size")
            raise
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
        await _get_or_404(conn, "filter", filter_id, "Filter")
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
            try:
                await conn.execute(
                    f"UPDATE filter_size_option SET {set_clause} WHERE id = ?", values
                )
                await conn.commit()
            except Exception as exc:
                if "UNIQUE" in str(exc):
                    raise HTTPException(
                        status_code=409, detail="This filter already offers that size"
                    )
                raise
        row = await conn.execute("SELECT * FROM filter_size_option WHERE id = ?", (option_id,))
        return await _build_size_option_response(conn, await row.fetchone())


@router.delete("/filter/{filter_id}/size-option/{option_id}")
async def delete_filter_size_option(filter_id: int, option_id: int):
    async with get_db() as conn:
        await _get_or_404(conn, "filter", filter_id, "Filter")
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
    _bool_fields(d, "active", "counterweight_required", "goto_capable")

    d["manufacturer"] = _bool_fields(
        await _get_or_404(conn, "manufacturer", d.pop("manufacturer_id"), "Manufacturer"),
        "active",
    )

    mt_id = d.pop("mount_type_id")
    if mt_id:
        d["mount_type"] = _bool_fields(
            await _get_or_404(conn, "mount_type", mt_id, "Mount type"),
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


@router.get("/mount", response_model=list[MountResponse])
async def list_mounts(
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
        rows = await conn.execute(f"SELECT * FROM mount {where} ORDER BY is_mine DESC, model_name")
        results = []
        for r in await rows.fetchall():
            results.append(await _build_mount_response(conn, _row_to_dict(r)))
        return results


@router.get("/mount/{mount_id}", response_model=MountResponse)
async def get_mount(mount_id: int):
    async with get_db() as conn:
        row = await _get_or_404(conn, "mount", mount_id, "Mount")
        return await _build_mount_response(conn, row)


@router.post("/mount", response_model=MountResponse, status_code=201)
async def create_mount(body: MountCreate):
    async with get_db() as conn:
        try:
            cursor = await conn.execute(
                """INSERT INTO mount (
                    manufacturer_id, mount_type_id, model_name,
                    payload_capacity_kg, mount_weight_kg, counterweight_required,
                    goto_capable, periodic_error_arcsec, drive_type, notes, source_url,
                    is_mine
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    body.manufacturer_id,
                    body.mount_type_id,
                    body.model_name,
                    body.payload_capacity_kg,
                    body.mount_weight_kg,
                    int(body.counterweight_required),
                    int(body.goto_capable),
                    body.periodic_error_arcsec,
                    body.drive_type,
                    body.notes,
                    body.source_url,
                    int(body.is_mine),
                ),
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(
                    status_code=409,
                    detail=f"Mount already exists: {body.model_name}",
                )
            raise
        mount_id = cursor.lastrowid
        for iface_id in body.interface_ids:
            await conn.execute(
                "INSERT INTO mount_interface (mount_id, interface_id) VALUES (?, ?)",
                (mount_id, iface_id),
            )
        await conn.commit()
        row = await _get_or_404(conn, "mount", mount_id, "Mount")
        return await _build_mount_response(conn, row)


@router.put("/mount/{mount_id}", response_model=MountResponse)
async def update_mount(mount_id: int, body: MountUpdate):
    async with get_db() as conn:
        await _get_or_404(conn, "mount", mount_id, "Mount")
        updates = body.model_dump(exclude_unset=True)
        interface_ids = updates.pop("interface_ids", None)
        if updates:
            for bool_field in ("counterweight_required", "goto_capable"):
                if bool_field in updates and updates[bool_field] is not None:
                    updates[bool_field] = int(updates[bool_field])
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [mount_id]
            try:
                await conn.execute(
                    f"UPDATE mount SET {set_clause} WHERE id = ?",
                    values,
                )
                await conn.commit()
            except Exception as exc:
                if "UNIQUE" in str(exc):
                    raise HTTPException(
                        status_code=409,
                        detail="Mount (manufacturer, model_name) already exists",
                    )
                raise
        if interface_ids is not None:
            await conn.execute("DELETE FROM mount_interface WHERE mount_id = ?", (mount_id,))
            for iface_id in interface_ids:
                await conn.execute(
                    "INSERT INTO mount_interface (mount_id, interface_id) VALUES (?, ?)",
                    (mount_id, iface_id),
                )
            await conn.commit()
        row = await _get_or_404(conn, "mount", mount_id, "Mount")
        return await _build_mount_response(conn, row)


@router.delete("/mount/{mount_id}")
async def delete_mount(mount_id: int):
    async with get_db() as conn:
        await _get_or_404(conn, "mount", mount_id, "Mount")
        await conn.execute("UPDATE mount SET active = 0 WHERE id = ?", (mount_id,))
        await conn.commit()
    return {"ok": True}


@router.post("/mount/{mount_id}/mine", response_model=MountResponse)
async def toggle_mount_mine(mount_id: int, body: MineToggle):
    async with get_db() as conn:
        await _get_or_404(conn, "mount", mount_id, "Mount")
        await conn.execute(
            "UPDATE mount SET is_mine = ? WHERE id = ?",
            (int(body.is_mine), mount_id),
        )
        await conn.commit()
        row = await _get_or_404(conn, "mount", mount_id, "Mount")
        return await _build_mount_response(conn, row)


# ── Focuser ───────────────────────────────────────────────────────────────────


async def _build_focuser_response(conn, focuser_row: dict) -> dict:
    """Build full focuser response with nested objects."""
    d = dict(focuser_row)
    _bool_fields(d, "active", "motorized", "temperature_compensation")

    d["manufacturer"] = _bool_fields(
        await _get_or_404(conn, "manufacturer", d.pop("manufacturer_id"), "Manufacturer"),
        "active",
    )

    ft_id = d.pop("focuser_type_id")
    if ft_id:
        d["focuser_type"] = _bool_fields(
            await _get_or_404(conn, "focuser_type", ft_id, "Focuser type"),
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


@router.get("/focuser", response_model=list[FocuserResponse])
async def list_focusers(
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
            f"SELECT * FROM focuser {where} ORDER BY is_mine DESC, model_name"
        )
        results = []
        for r in await rows.fetchall():
            results.append(await _build_focuser_response(conn, _row_to_dict(r)))
        return results


@router.get("/focuser/{focuser_id}", response_model=FocuserResponse)
async def get_focuser(focuser_id: int):
    async with get_db() as conn:
        row = await _get_or_404(conn, "focuser", focuser_id, "Focuser")
        return await _build_focuser_response(conn, row)


@router.post("/focuser", response_model=FocuserResponse, status_code=201)
async def create_focuser(body: FocuserCreate):
    async with get_db() as conn:
        try:
            cursor = await conn.execute(
                """INSERT INTO focuser (
                    manufacturer_id, focuser_type_id, model_name, motorized, travel_range_mm,
                    step_size_um, total_steps, temperature_compensation,
                    backlash_steps, notes, source_url, is_mine
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    body.manufacturer_id,
                    body.focuser_type_id,
                    body.model_name,
                    int(body.motorized),
                    body.travel_range_mm,
                    body.step_size_um,
                    body.total_steps,
                    int(body.temperature_compensation),
                    body.backlash_steps,
                    body.notes,
                    body.source_url,
                    int(body.is_mine),
                ),
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(
                    status_code=409,
                    detail=f"Focuser already exists: {body.model_name}",
                )
            raise
        focuser_id = cursor.lastrowid
        for iface_id in body.interface_ids:
            await conn.execute(
                "INSERT INTO focuser_interface (focuser_id, interface_id) VALUES (?, ?)",
                (focuser_id, iface_id),
            )
        await conn.commit()
        row = await _get_or_404(conn, "focuser", focuser_id, "Focuser")
        return await _build_focuser_response(conn, row)


@router.put("/focuser/{focuser_id}", response_model=FocuserResponse)
async def update_focuser(focuser_id: int, body: FocuserUpdate):
    async with get_db() as conn:
        await _get_or_404(conn, "focuser", focuser_id, "Focuser")
        updates = body.model_dump(exclude_unset=True)
        interface_ids = updates.pop("interface_ids", None)
        if updates:
            for bool_field in ("motorized", "temperature_compensation"):
                if bool_field in updates and updates[bool_field] is not None:
                    updates[bool_field] = int(updates[bool_field])
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [focuser_id]
            try:
                await conn.execute(
                    f"UPDATE focuser SET {set_clause} WHERE id = ?",
                    values,
                )
                await conn.commit()
            except Exception as exc:
                if "UNIQUE" in str(exc):
                    raise HTTPException(
                        status_code=409,
                        detail="Focuser (manufacturer, model_name) already exists",
                    )
                raise
        if interface_ids is not None:
            await conn.execute("DELETE FROM focuser_interface WHERE focuser_id = ?", (focuser_id,))
            for iface_id in interface_ids:
                await conn.execute(
                    "INSERT INTO focuser_interface (focuser_id, interface_id) VALUES (?, ?)",
                    (focuser_id, iface_id),
                )
            await conn.commit()
        row = await _get_or_404(conn, "focuser", focuser_id, "Focuser")
        return await _build_focuser_response(conn, row)


@router.delete("/focuser/{focuser_id}")
async def delete_focuser(focuser_id: int):
    async with get_db() as conn:
        await _get_or_404(conn, "focuser", focuser_id, "Focuser")
        await conn.execute("UPDATE focuser SET active = 0 WHERE id = ?", (focuser_id,))
        await conn.commit()
    return {"ok": True}


@router.post("/focuser/{focuser_id}/mine", response_model=FocuserResponse)
async def toggle_focuser_mine(focuser_id: int, body: MineToggle):
    async with get_db() as conn:
        await _get_or_404(conn, "focuser", focuser_id, "Focuser")
        await conn.execute(
            "UPDATE focuser SET is_mine = ? WHERE id = ?",
            (int(body.is_mine), focuser_id),
        )
        await conn.commit()
        row = await _get_or_404(conn, "focuser", focuser_id, "Focuser")
        return await _build_focuser_response(conn, row)


# ── Filter Wheel ──────────────────────────────────────────────────────────────


async def _build_filter_wheel_response(conn, fw_row: dict) -> dict:
    """Build full filter wheel response with nested objects."""
    d = dict(fw_row)
    _bool_fields(d, "active")

    d["manufacturer"] = _bool_fields(
        await _get_or_404(conn, "manufacturer", d.pop("manufacturer_id"), "Manufacturer"),
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

    cs_cam_id = d.pop("camera_side_connector_id")
    if cs_cam_id:
        d["camera_side_connector"] = _bool_fields(
            await _get_or_404(conn, "connector_size", cs_cam_id, "Connector size"),
            "active",
        )
    else:
        d["camera_side_connector"] = None

    cs_tel_id = d.pop("telescope_side_connector_id")
    if cs_tel_id:
        d["telescope_side_connector"] = _bool_fields(
            await _get_or_404(conn, "connector_size", cs_tel_id, "Connector size"),
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


@router.get("/filter-wheel", response_model=list[FilterWheelResponse])
async def list_filter_wheels(
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
            f"SELECT * FROM filter_wheel {where} ORDER BY is_mine DESC, model_name"
        )
        results = []
        for r in await rows.fetchall():
            results.append(await _build_filter_wheel_response(conn, _row_to_dict(r)))
        return results


@router.get("/filter-wheel/{filter_wheel_id}", response_model=FilterWheelResponse)
async def get_filter_wheel(filter_wheel_id: int):
    async with get_db() as conn:
        row = await _get_or_404(conn, "filter_wheel", filter_wheel_id, "Filter wheel")
        return await _build_filter_wheel_response(conn, row)


@router.post("/filter-wheel", response_model=FilterWheelResponse, status_code=201)
async def create_filter_wheel(body: FilterWheelCreate):
    async with get_db() as conn:
        try:
            cursor = await conn.execute(
                """INSERT INTO filter_wheel (
                    manufacturer_id, filter_size_id, camera_side_connector_id,
                    telescope_side_connector_id, model_name, num_positions,
                    back_focus_contribution_mm, notes, source_url, is_mine
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    body.manufacturer_id,
                    body.filter_size_id,
                    body.camera_side_connector_id,
                    body.telescope_side_connector_id,
                    body.model_name,
                    body.num_positions,
                    body.back_focus_contribution_mm,
                    body.notes,
                    body.source_url,
                    int(body.is_mine),
                ),
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(
                    status_code=409,
                    detail=f"Filter wheel already exists: {body.model_name}",
                )
            raise
        filter_wheel_id = cursor.lastrowid
        for iface_id in body.interface_ids:
            await conn.execute(
                "INSERT INTO filter_wheel_interface (filter_wheel_id, interface_id) VALUES (?, ?)",
                (filter_wheel_id, iface_id),
            )
        await conn.commit()
        row = await _get_or_404(conn, "filter_wheel", filter_wheel_id, "Filter wheel")
        return await _build_filter_wheel_response(conn, row)


@router.put("/filter-wheel/{filter_wheel_id}", response_model=FilterWheelResponse)
async def update_filter_wheel(filter_wheel_id: int, body: FilterWheelUpdate):
    async with get_db() as conn:
        await _get_or_404(conn, "filter_wheel", filter_wheel_id, "Filter wheel")
        updates = body.model_dump(exclude_unset=True)
        interface_ids = updates.pop("interface_ids", None)
        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [filter_wheel_id]
            try:
                await conn.execute(
                    f"UPDATE filter_wheel SET {set_clause} WHERE id = ?",
                    values,
                )
                await conn.commit()
            except Exception as exc:
                if "UNIQUE" in str(exc):
                    raise HTTPException(
                        status_code=409,
                        detail="Filter wheel (manufacturer, model_name) already exists",
                    )
                raise
        if interface_ids is not None:
            await conn.execute(
                "DELETE FROM filter_wheel_interface WHERE filter_wheel_id = ?", (filter_wheel_id,)
            )
            for iface_id in interface_ids:
                await conn.execute(
                    "INSERT INTO filter_wheel_interface"
                    " (filter_wheel_id, interface_id) VALUES (?, ?)",
                    (filter_wheel_id, iface_id),
                )
            await conn.commit()
        row = await _get_or_404(conn, "filter_wheel", filter_wheel_id, "Filter wheel")
        return await _build_filter_wheel_response(conn, row)


@router.delete("/filter-wheel/{filter_wheel_id}")
async def delete_filter_wheel(filter_wheel_id: int):
    async with get_db() as conn:
        await _get_or_404(conn, "filter_wheel", filter_wheel_id, "Filter wheel")
        await conn.execute("UPDATE filter_wheel SET active = 0 WHERE id = ?", (filter_wheel_id,))
        await conn.commit()
    return {"ok": True}


@router.post("/filter-wheel/{filter_wheel_id}/mine", response_model=FilterWheelResponse)
async def toggle_filter_wheel_mine(filter_wheel_id: int, body: MineToggle):
    async with get_db() as conn:
        await _get_or_404(conn, "filter_wheel", filter_wheel_id, "Filter wheel")
        await conn.execute(
            "UPDATE filter_wheel SET is_mine = ? WHERE id = ?",
            (int(body.is_mine), filter_wheel_id),
        )
        await conn.commit()
        row = await _get_or_404(conn, "filter_wheel", filter_wheel_id, "Filter wheel")
        return await _build_filter_wheel_response(conn, row)


# ── OAG ───────────────────────────────────────────────────────────────────────


async def _build_oag_response(conn, oag_row: dict) -> dict:
    """Build full OAG response with nested objects."""
    d = dict(oag_row)
    _bool_fields(d, "active")

    d["manufacturer"] = _bool_fields(
        await _get_or_404(conn, "manufacturer", d.pop("manufacturer_id"), "Manufacturer"),
        "active",
    )

    isc_id = d.pop("imaging_side_connector_id")
    if isc_id:
        d["imaging_side_connector"] = _bool_fields(
            await _get_or_404(conn, "connector_size", isc_id, "Connector size"),
            "active",
        )
    else:
        d["imaging_side_connector"] = None

    gcc_id = d.pop("guide_camera_connector_id")
    if gcc_id:
        d["guide_camera_connector"] = _bool_fields(
            await _get_or_404(conn, "connector_size", gcc_id, "Connector size"),
            "active",
        )
    else:
        d["guide_camera_connector"] = None

    _strip_seed(d)

    return d


@router.get("/oag", response_model=list[OagResponse])
async def list_oags(
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
        rows = await conn.execute(f"SELECT * FROM oag {where} ORDER BY is_mine DESC, model_name")
        results = []
        for r in await rows.fetchall():
            results.append(await _build_oag_response(conn, _row_to_dict(r)))
        return results


@router.get("/oag/{oag_id}", response_model=OagResponse)
async def get_oag(oag_id: int):
    async with get_db() as conn:
        row = await _get_or_404(conn, "oag", oag_id, "OAG")
        return await _build_oag_response(conn, row)


@router.post("/oag", response_model=OagResponse, status_code=201)
async def create_oag(body: OagCreate):
    async with get_db() as conn:
        try:
            cursor = await conn.execute(
                """INSERT INTO oag (
                    manufacturer_id, imaging_side_connector_id, guide_camera_connector_id,
                    model_name, prism_size_mm, back_focus_contribution_mm, weight_g, notes,
                    source_url, is_mine
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    body.manufacturer_id,
                    body.imaging_side_connector_id,
                    body.guide_camera_connector_id,
                    body.model_name,
                    body.prism_size_mm,
                    body.back_focus_contribution_mm,
                    body.weight_g,
                    body.notes,
                    body.source_url,
                    int(body.is_mine),
                ),
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(
                    status_code=409,
                    detail=f"OAG already exists: {body.model_name}",
                )
            raise
        oag_id = cursor.lastrowid
        row = await _get_or_404(conn, "oag", oag_id, "OAG")
        return await _build_oag_response(conn, row)


@router.put("/oag/{oag_id}", response_model=OagResponse)
async def update_oag(oag_id: int, body: OagUpdate):
    async with get_db() as conn:
        await _get_or_404(conn, "oag", oag_id, "OAG")
        updates = body.model_dump(exclude_unset=True)
        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [oag_id]
            try:
                await conn.execute(
                    f"UPDATE oag SET {set_clause} WHERE id = ?",
                    values,
                )
                await conn.commit()
            except Exception as exc:
                if "UNIQUE" in str(exc):
                    raise HTTPException(
                        status_code=409,
                        detail="OAG (manufacturer, model_name) already exists",
                    )
                raise
        row = await _get_or_404(conn, "oag", oag_id, "OAG")
        return await _build_oag_response(conn, row)


@router.delete("/oag/{oag_id}")
async def delete_oag(oag_id: int):
    async with get_db() as conn:
        await _get_or_404(conn, "oag", oag_id, "OAG")
        await conn.execute("UPDATE oag SET active = 0 WHERE id = ?", (oag_id,))
        await conn.commit()
    return {"ok": True}


@router.post("/oag/{oag_id}/mine", response_model=OagResponse)
async def toggle_oag_mine(oag_id: int, body: MineToggle):
    async with get_db() as conn:
        await _get_or_404(conn, "oag", oag_id, "OAG")
        await conn.execute(
            "UPDATE oag SET is_mine = ? WHERE id = ?",
            (int(body.is_mine), oag_id),
        )
        await conn.commit()
        row = await _get_or_404(conn, "oag", oag_id, "OAG")
        return await _build_oag_response(conn, row)


# ── Guide Scope ───────────────────────────────────────────────────────────────


async def _build_guide_scope_response(conn, gs_row: dict) -> dict:
    """Build full guide scope response with nested objects."""
    d = dict(gs_row)
    _bool_fields(d, "active")

    d["manufacturer"] = _bool_fields(
        await _get_or_404(conn, "manufacturer", d.pop("manufacturer_id"), "Manufacturer"),
        "active",
    )

    gcc_id = d.pop("guide_camera_connector_id")
    if gcc_id:
        d["guide_camera_connector"] = _bool_fields(
            await _get_or_404(conn, "connector_size", gcc_id, "Connector size"),
            "active",
        )
    else:
        d["guide_camera_connector"] = None

    _strip_seed(d)

    return d


@router.get("/guide-scope", response_model=list[GuideScopeResponse])
async def list_guide_scopes(
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
            f"SELECT * FROM guide_scope {where} ORDER BY is_mine DESC, model_name"
        )
        results = []
        for r in await rows.fetchall():
            results.append(await _build_guide_scope_response(conn, _row_to_dict(r)))
        return results


@router.get("/guide-scope/{guide_scope_id}", response_model=GuideScopeResponse)
async def get_guide_scope(guide_scope_id: int):
    async with get_db() as conn:
        row = await _get_or_404(conn, "guide_scope", guide_scope_id, "Guide scope")
        return await _build_guide_scope_response(conn, row)


@router.post("/guide-scope", response_model=GuideScopeResponse, status_code=201)
async def create_guide_scope(body: GuideScopeCreate):
    async with get_db() as conn:
        try:
            cursor = await conn.execute(
                """INSERT INTO guide_scope (
                    manufacturer_id, guide_camera_connector_id, model_name,
                    aperture_mm, focal_length_mm, weight_g, notes, source_url, is_mine
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    body.manufacturer_id,
                    body.guide_camera_connector_id,
                    body.model_name,
                    body.aperture_mm,
                    body.focal_length_mm,
                    body.weight_g,
                    body.notes,
                    body.source_url,
                    int(body.is_mine),
                ),
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(
                    status_code=409,
                    detail=f"Guide scope already exists: {body.model_name}",
                )
            raise
        guide_scope_id = cursor.lastrowid
        row = await _get_or_404(conn, "guide_scope", guide_scope_id, "Guide scope")
        return await _build_guide_scope_response(conn, row)


@router.put("/guide-scope/{guide_scope_id}", response_model=GuideScopeResponse)
async def update_guide_scope(guide_scope_id: int, body: GuideScopeUpdate):
    async with get_db() as conn:
        await _get_or_404(conn, "guide_scope", guide_scope_id, "Guide scope")
        updates = body.model_dump(exclude_unset=True)
        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [guide_scope_id]
            try:
                await conn.execute(
                    f"UPDATE guide_scope SET {set_clause} WHERE id = ?",
                    values,
                )
                await conn.commit()
            except Exception as exc:
                if "UNIQUE" in str(exc):
                    raise HTTPException(
                        status_code=409,
                        detail="Guide scope (manufacturer, model_name) already exists",
                    )
                raise
        row = await _get_or_404(conn, "guide_scope", guide_scope_id, "Guide scope")
        return await _build_guide_scope_response(conn, row)


@router.delete("/guide-scope/{guide_scope_id}")
async def delete_guide_scope(guide_scope_id: int):
    async with get_db() as conn:
        await _get_or_404(conn, "guide_scope", guide_scope_id, "Guide scope")
        await conn.execute("UPDATE guide_scope SET active = 0 WHERE id = ?", (guide_scope_id,))
        await conn.commit()
    return {"ok": True}


@router.post("/guide-scope/{guide_scope_id}/mine", response_model=GuideScopeResponse)
async def toggle_guide_scope_mine(guide_scope_id: int, body: MineToggle):
    async with get_db() as conn:
        await _get_or_404(conn, "guide_scope", guide_scope_id, "Guide scope")
        await conn.execute(
            "UPDATE guide_scope SET is_mine = ? WHERE id = ?",
            (int(body.is_mine), guide_scope_id),
        )
        await conn.commit()
        row = await _get_or_404(conn, "guide_scope", guide_scope_id, "Guide scope")
        return await _build_guide_scope_response(conn, row)


# ── Computer ──────────────────────────────────────────────────────────────────


async def _build_computer_response(conn, computer_row: dict) -> dict:
    """Build full computer response with nested objects."""
    d = dict(computer_row)
    _bool_fields(d, "active")

    d["manufacturer"] = _bool_fields(
        await _get_or_404(conn, "manufacturer", d.pop("manufacturer_id"), "Manufacturer"),
        "active",
    )

    ct_id = d.pop("form_factor_id")
    if ct_id:
        d["form_factor"] = _bool_fields(
            await _get_or_404(conn, "form_factor", ct_id, "Form factor"),
            "active",
        )
    else:
        d["form_factor"] = None

    _strip_seed(d)

    return d


@router.get("/computer", response_model=list[ComputerResponse])
async def list_computers(
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
            f"SELECT * FROM computer {where} ORDER BY is_mine DESC, model_name"
        )
        results = []
        for r in await rows.fetchall():
            results.append(await _build_computer_response(conn, _row_to_dict(r)))
        return results


@router.get("/computer/{computer_id}", response_model=ComputerResponse)
async def get_computer(computer_id: int):
    async with get_db() as conn:
        row = await _get_or_404(conn, "computer", computer_id, "Computer")
        return await _build_computer_response(conn, row)


@router.post("/computer", response_model=ComputerResponse, status_code=201)
async def create_computer(body: ComputerCreate):
    async with get_db() as conn:
        try:
            cursor = await conn.execute(
                """INSERT INTO computer (
                    manufacturer_id, form_factor_id, model_name, notes, source_url, is_mine
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    body.manufacturer_id,
                    body.form_factor_id,
                    body.model_name,
                    body.notes,
                    body.source_url,
                    int(body.is_mine),
                ),
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(
                    status_code=409,
                    detail=f"Computer already exists: {body.model_name}",
                )
            raise
        computer_id = cursor.lastrowid
        row = await _get_or_404(conn, "computer", computer_id, "Computer")
        return await _build_computer_response(conn, row)


@router.put("/computer/{computer_id}", response_model=ComputerResponse)
async def update_computer(computer_id: int, body: ComputerUpdate):
    async with get_db() as conn:
        await _get_or_404(conn, "computer", computer_id, "Computer")
        updates = body.model_dump(exclude_unset=True)
        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [computer_id]
            try:
                await conn.execute(
                    f"UPDATE computer SET {set_clause} WHERE id = ?",
                    values,
                )
                await conn.commit()
            except Exception as exc:
                if "UNIQUE" in str(exc):
                    raise HTTPException(
                        status_code=409,
                        detail="Computer (manufacturer, model_name) already exists",
                    )
                raise
        row = await _get_or_404(conn, "computer", computer_id, "Computer")
        return await _build_computer_response(conn, row)


@router.delete("/computer/{computer_id}")
async def delete_computer(computer_id: int):
    async with get_db() as conn:
        await _get_or_404(conn, "computer", computer_id, "Computer")
        await conn.execute("UPDATE computer SET active = 0 WHERE id = ?", (computer_id,))
        await conn.commit()
    return {"ok": True}


@router.post("/computer/{computer_id}/mine", response_model=ComputerResponse)
async def toggle_computer_mine(computer_id: int, body: MineToggle):
    async with get_db() as conn:
        await _get_or_404(conn, "computer", computer_id, "Computer")
        await conn.execute(
            "UPDATE computer SET is_mine = ? WHERE id = ?",
            (int(body.is_mine), computer_id),
        )
        await conn.commit()
        row = await _get_or_404(conn, "computer", computer_id, "Computer")
        return await _build_computer_response(conn, row)


# ── Software ──────────────────────────────────────────────────────────────────


async def _build_software_response(conn, sw_row: dict) -> dict:
    """Build full software response with nested objects."""
    d = dict(sw_row)
    _bool_fields(d, "active")

    mfr_id = d.pop("manufacturer_id")
    if mfr_id:
        d["manufacturer"] = _bool_fields(
            await _get_or_404(conn, "manufacturer", mfr_id, "Manufacturer"),
            "active",
        )
    else:
        d["manufacturer"] = None

    _strip_seed(d)

    return d


@router.get("/software", response_model=list[SoftwareResponse])
async def list_software(
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
        rows = await conn.execute(f"SELECT * FROM software {where} ORDER BY is_mine DESC, name")
        results = []
        for r in await rows.fetchall():
            results.append(await _build_software_response(conn, _row_to_dict(r)))
        return results


@router.get("/software/{software_id}", response_model=SoftwareResponse)
async def get_software(software_id: int):
    async with get_db() as conn:
        row = await _get_or_404(conn, "software", software_id, "Software")
        return await _build_software_response(conn, row)


@router.post("/software", response_model=SoftwareResponse, status_code=201)
async def create_software(body: SoftwareCreate):
    async with get_db() as conn:
        try:
            cursor = await conn.execute(
                """INSERT INTO software (
                    manufacturer_id, name, category, website, notes, is_mine
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    body.manufacturer_id,
                    body.name,
                    body.category,
                    body.website,
                    body.notes,
                    int(body.is_mine),
                ),
            )
            await conn.commit()
        except Exception as exc:
            exc_str = str(exc)
            if "UNIQUE" in exc_str:
                raise HTTPException(
                    status_code=409,
                    detail=f"Software already exists: {body.name}",
                )
            if "CHECK" in exc_str:
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid category: {body.category}",
                )
            raise
        software_id = cursor.lastrowid
        row = await _get_or_404(conn, "software", software_id, "Software")
        return await _build_software_response(conn, row)


@router.put("/software/{software_id}", response_model=SoftwareResponse)
async def update_software(software_id: int, body: SoftwareUpdate):
    async with get_db() as conn:
        await _get_or_404(conn, "software", software_id, "Software")
        updates = body.model_dump(exclude_unset=True)
        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [software_id]
            try:
                await conn.execute(
                    f"UPDATE software SET {set_clause} WHERE id = ?",
                    values,
                )
                await conn.commit()
            except Exception as exc:
                exc_str = str(exc)
                if "UNIQUE" in exc_str:
                    raise HTTPException(
                        status_code=409,
                        detail="Software (manufacturer, name) already exists",
                    )
                if "CHECK" in exc_str:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Invalid category: {updates.get('category')}",
                    )
                raise
        row = await _get_or_404(conn, "software", software_id, "Software")
        return await _build_software_response(conn, row)


@router.delete("/software/{software_id}")
async def delete_software(software_id: int):
    async with get_db() as conn:
        await _get_or_404(conn, "software", software_id, "Software")
        await conn.execute("UPDATE software SET active = 0 WHERE id = ?", (software_id,))
        await conn.commit()
    return {"ok": True}


@router.post("/software/{software_id}/mine", response_model=SoftwareResponse)
async def toggle_software_mine(software_id: int, body: MineToggle):
    async with get_db() as conn:
        await _get_or_404(conn, "software", software_id, "Software")
        await conn.execute(
            "UPDATE software SET is_mine = ? WHERE id = ?",
            (int(body.is_mine), software_id),
        )
        await conn.commit()
        row = await _get_or_404(conn, "software", software_id, "Software")
        return await _build_software_response(conn, row)
