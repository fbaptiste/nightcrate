"""Rig management API — CRUD for imaging rig templates."""

import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from nightcrate.api.rig_models import (
    EquipmentOptionsOut,
    RigCalculators,
    RigCreate,
    RigOut,
    RigUpdate,
)
from nightcrate.db.session import get_db
from nightcrate.services.rig_calculators import (
    compute_rig_calculators,
    resolve_seeing,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rigs", tags=["Rigs"])


# ── Helpers ──────────────────────────────────────────────────────────────────


def _row_to_dict(row) -> dict:
    """Convert an aiosqlite.Row to a plain dict."""
    return dict(row)


def _bool_fields(d: dict, *keys: str) -> dict:
    """Convert integer 0/1 fields to Python bools for Pydantic."""
    for k in keys:
        if k in d and d[k] is not None:
            d[k] = bool(d[k])
    return d


async def _resolve_location(conn, location_id: int | None) -> dict | None:
    """Get specified location or default. Returns dict or None."""
    if location_id is not None:
        row = await conn.execute("SELECT * FROM location WHERE id = ?", (location_id,))
        result = await row.fetchone()
        if result is None:
            raise HTTPException(status_code=404, detail="Location not found")
        return _row_to_dict(result)
    # Try default
    row = await conn.execute("SELECT * FROM location WHERE is_default = 1 LIMIT 1")
    result = await row.fetchone()
    return _row_to_dict(result) if result else None


async def _build_software(conn, rig_id: int) -> list[dict]:
    """Fetch software entries for a rig."""
    rows = await conn.execute(
        """SELECT s.id, s.name, s.category
        FROM rig_software rs
        JOIN software s ON s.id = rs.software_id
        WHERE rs.rig_id = ?
        ORDER BY s.name""",
        (rig_id,),
    )
    return [_row_to_dict(r) for r in await rows.fetchall()]


async def _save_software(conn, rig_id: int, software_ids: list[int]) -> None:
    """Delete existing software links and insert new ones."""
    await conn.execute("DELETE FROM rig_software WHERE rig_id = ?", (rig_id,))
    for sid in software_ids:
        await conn.execute(
            "INSERT INTO rig_software (rig_id, software_id) VALUES (?, ?)",
            (rig_id, sid),
        )


async def _build_filter_slots(conn, rig_id: int) -> list[dict]:
    """Fetch filter slots with joined filter and type names."""
    rows = await conn.execute(
        """
        SELECT rfs.slot_number, rfs.filter_id,
               f.model_name AS filter_name,
               ft.display_name AS filter_type_name
        FROM rig_filter_slot rfs
        JOIN filter f ON f.id = rfs.filter_id
        JOIN filter_type ft ON ft.id = f.filter_type_id
        WHERE rfs.rig_id = ?
        ORDER BY rfs.slot_number
        """,
        (rig_id,),
    )
    slots = [_row_to_dict(r) for r in await rows.fetchall()]
    if not slots:
        return slots

    # Batch-fetch passbands for all filters on this rig in one query.
    filter_ids = [s["filter_id"] for s in slots]
    placeholders = ",".join("?" * len(filter_ids))
    pb_rows = await conn.execute(
        f"SELECT filter_id, line_name FROM filter_passband "
        f"WHERE filter_id IN ({placeholders}) ORDER BY filter_id, line_name",
        filter_ids,
    )
    passbands_by_filter: dict[int, list[str]] = {fid: [] for fid in filter_ids}
    for row in await pb_rows.fetchall():
        if row["line_name"] is not None:
            passbands_by_filter[row["filter_id"]].append(row["line_name"])
    for s in slots:
        s["passbands"] = passbands_by_filter[s["filter_id"]]
    return slots


def _slot_as_dict(slot) -> dict:
    """Normalize a filter slot (Pydantic model or dict) to a plain dict."""
    if isinstance(slot, dict):
        return slot
    return {"slot_number": slot.slot_number, "filter_id": slot.filter_id}


async def _validate_filter_slots(conn, slots: list, filter_wheel_id: int | None) -> None:
    """Validate filter slot assignments against filter wheel constraints."""
    if not slots:
        return

    if filter_wheel_id is None:
        raise HTTPException(
            status_code=422,
            detail="Filter slots require a filter wheel to be assigned",
        )

    # Look up wheel capacity
    fw_row = await conn.execute(
        "SELECT num_positions FROM filter_wheel WHERE id = ?",
        (filter_wheel_id,),
    )
    fw = await fw_row.fetchone()
    if fw is None:
        raise HTTPException(status_code=422, detail="Filter wheel not found")

    num_positions = fw["num_positions"]
    for slot in slots:
        slot_num = _slot_as_dict(slot)["slot_number"]
        if slot_num > num_positions:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Slot number {slot_num} exceeds filter wheel capacity "
                    f"of {num_positions} positions"
                ),
            )


async def _check_warnings(conn, rig_data: dict) -> list[dict]:
    """Check for advisory warnings on a rig configuration."""
    warnings = []

    # Check retired equipment
    equipment_checks = [
        ("telescope_configuration_id", "telescope_configuration", "OTA Configuration"),
        ("camera_id", "camera", "Imaging Camera"),
        ("filter_wheel_id", "filter_wheel", "Filter Wheel"),
        ("single_filter_id", "filter", "Single Filter"),
        ("mount_id", "mount", "Mount"),
        ("focuser_id", "focuser", "Focuser"),
        ("oag_id", "oag", "OAG"),
        ("guide_scope_id", "guide_scope", "Guide Scope"),
        ("guide_camera_id", "camera", "Guide Camera"),
        ("computer_id", "computer", "Computer"),
    ]
    for field, table, label in equipment_checks:
        eq_id = rig_data.get(field)
        if eq_id is not None:
            row = await conn.execute(f"SELECT active FROM {table} WHERE id = ?", (eq_id,))
            result = await row.fetchone()
            if result and not result["active"]:
                warnings.append({"field": field, "message": f"{label} is retired"})

    # Guide camera = imaging camera
    if rig_data.get("guide_camera_id") and rig_data["guide_camera_id"] == rig_data.get("camera_id"):
        warnings.append(
            {
                "field": "guide_camera_id",
                "message": "Guide camera is the same as the imaging camera",
            }
        )

    # Filter wheel + single filter
    if rig_data.get("filter_wheel_id") and rig_data.get("single_filter_id"):
        warnings.append(
            {
                "field": "single_filter_id",
                "message": "Both filter wheel and single filter assigned",
            }
        )

    # Guide scope assigned but missing focal length — suitability can't be computed.
    guide_scope_id = rig_data.get("guide_scope_id")
    if guide_scope_id is not None:
        row = await conn.execute(
            "SELECT focal_length_mm FROM guide_scope WHERE id = ?", (guide_scope_id,)
        )
        result = await row.fetchone()
        if result is not None and result["focal_length_mm"] is None:
            warnings.append(
                {
                    "field": "guide_scope_id",
                    "message": (
                        "Guide scope has no focal length on file \u2014 cannot compute "
                        "guide suitability. Edit the equipment record to set it."
                    ),
                }
            )

    # Guide camera assigned without any optical path.
    if (
        rig_data.get("guide_camera_id")
        and rig_data.get("guide_scope_id") is None
        and rig_data.get("oag_id") is None
    ):
        warnings.append(
            {
                "field": "guide_camera_id",
                "message": (
                    "Guide camera is assigned but no guide scope or OAG is set \u2014 "
                    "guide suitability cannot be computed. Assign a guide scope or OAG, "
                    "or remove the guide camera."
                ),
            }
        )

    return warnings


async def _ensure_single_default(conn, rig_id: int) -> None:
    """Clear is_default on all rigs except the given ID."""
    await conn.execute("UPDATE rig SET is_default = 0 WHERE id != ?", (rig_id,))


def _build_calculators(
    rig_row: dict,
    seeing_low: float,
    seeing_high: float,
    seeing_source: str,
    seeing_location_name: str | None,
    guide_binning: int = 1,
    centroid_accuracy_pixels: float = 0.2,
    image_binning: int = 1,
) -> dict:
    """Compute all calculator results from rig summary row data."""
    calcs = compute_rig_calculators(
        pixel_size_um=rig_row["pixel_size_um"],
        focal_length_mm=rig_row["effective_focal_length_mm"],
        focal_ratio=rig_row["effective_focal_ratio"],
        aperture_mm=rig_row["aperture_mm"],
        resolution_x=rig_row["sensor_resolution_x"],
        resolution_y=rig_row["sensor_resolution_y"],
        sensor_width_mm=rig_row.get("sensor_width_mm"),
        sensor_height_mm=rig_row.get("sensor_height_mm"),
        image_circle_mm=rig_row.get("effective_image_circle_mm"),
        seeing_fwhm_low=seeing_low,
        seeing_fwhm_high=seeing_high,
        seeing_source=seeing_source,
        seeing_location_name=seeing_location_name,
        guide_scope_id=rig_row.get("guide_scope_id"),
        oag_id=rig_row.get("oag_id"),
        guide_pixel_size_um=rig_row.get("guide_pixel_size_um"),
        guide_focal_length_mm=rig_row.get("guide_scope_focal_length_mm"),
        guide_resolution_x=rig_row.get("guide_resolution_x"),
        guide_resolution_y=rig_row.get("guide_resolution_y"),
        guide_binning=guide_binning,
        centroid_accuracy_pixels=centroid_accuracy_pixels,
        image_binning=image_binning,
    )

    # Map service dict keys to Pydantic model keys
    fov_deg = calcs["field_of_view_deg"]
    fov_arcmin = (fov_deg[0] * 60.0, fov_deg[1] * 60.0)

    return {
        "image_scale_arcsec_per_pixel": calcs["image_scale_arcsec_per_pixel"],
        "image_scale_arcsec_per_pixel_binned": calcs["image_scale_binned"],
        "field_of_view_arcmin": fov_arcmin,
        "field_of_view_deg": fov_deg,
        "focal_ratio": calcs["focal_ratio"],
        "dawes_limit_arcsec": calcs["dawes_limit_arcsec"],
        "rayleigh_limit_arcsec": calcs["rayleigh_limit_arcsec"],
        "max_useful_magnification": calcs["max_useful_magnification"],
        "sensor_diagonal_mm": calcs["sensor_diagonal_mm"],
        "image_circle_mm": rig_row.get("effective_image_circle_mm"),
        "sensor_coverage_pct": calcs["sensor_coverage_pct"],
        "sampling_assessment": calcs["sampling_assessment"],
        "guide_suitability": calcs["guide_suitability"],
        "guiding_tolerance": calcs["guiding_tolerance"],
    }


async def _build_rig_response(
    conn,
    rig_row: dict,
    location_id: int | None = None,
    override_seeing_low: float | None = None,
    override_seeing_high: float | None = None,
) -> dict:
    """Assemble a full RigOut response from a rig_summary row."""
    rig_id = rig_row["id"]

    # Filter slots
    filter_slots = await _build_filter_slots(conn, rig_id)

    # Location and seeing resolution
    location = await _resolve_location(conn, location_id)
    loc_seeing_low = location.get("typical_seeing_low_arcsec") if location else None
    loc_seeing_high = location.get("typical_seeing_high_arcsec") if location else None
    loc_name = location.get("name") if location else None

    seeing_low, seeing_high, seeing_source, seeing_loc_name = resolve_seeing(
        location_seeing_low=loc_seeing_low,
        location_seeing_high=loc_seeing_high,
        location_name=loc_name,
        override_low=override_seeing_low,
        override_high=override_seeing_high,
    )

    calculators = _build_calculators(
        rig_row, seeing_low, seeing_high, seeing_source, seeing_loc_name
    )

    # Warnings
    warnings = await _check_warnings(conn, rig_row)

    _bool_fields(rig_row, "is_default", "active")

    return {
        "id": rig_row["id"],
        "name": rig_row["name"],
        "description": rig_row.get("description"),
        "telescope_configuration_id": rig_row["telescope_configuration_id"],
        "telescope_id": rig_row["telescope_id"],
        "telescope_name": rig_row["telescope_name"],
        "telescope_config_name": rig_row["telescope_config_name"],
        "effective_focal_length_mm": rig_row["effective_focal_length_mm"],
        "effective_focal_ratio": rig_row["effective_focal_ratio"],
        "aperture_mm": rig_row["aperture_mm"],
        "camera_id": rig_row["camera_id"],
        "camera_name": rig_row["camera_name"],
        "pixel_size_um": rig_row["pixel_size_um"],
        "sensor_resolution_x": rig_row["sensor_resolution_x"],
        "sensor_resolution_y": rig_row["sensor_resolution_y"],
        "sensor_width_mm": rig_row.get("sensor_width_mm"),
        "sensor_height_mm": rig_row.get("sensor_height_mm"),
        "sensor_type": rig_row["sensor_type"],
        "filter_wheel_id": rig_row.get("filter_wheel_id"),
        "filter_wheel_name": rig_row.get("filter_wheel_name"),
        "filter_wheel_positions": rig_row.get("filter_wheel_positions"),
        "single_filter_id": rig_row.get("single_filter_id"),
        "single_filter_name": rig_row.get("single_filter_name"),
        "mount_id": rig_row.get("mount_id"),
        "mount_name": rig_row.get("mount_name"),
        "focuser_id": rig_row.get("focuser_id"),
        "focuser_name": rig_row.get("focuser_name"),
        "oag_id": rig_row.get("oag_id"),
        "oag_name": rig_row.get("oag_name"),
        "guide_scope_id": rig_row.get("guide_scope_id"),
        "guide_scope_name": rig_row.get("guide_scope_name"),
        "guide_scope_focal_length_mm": rig_row.get("guide_scope_focal_length_mm"),
        "guide_camera_id": rig_row.get("guide_camera_id"),
        "guide_camera_name": rig_row.get("guide_camera_name"),
        "computer_id": rig_row.get("computer_id"),
        "computer_name": rig_row.get("computer_name"),
        "software": await _build_software(conn, rig_id),
        "filter_slots": filter_slots,
        "is_default": rig_row["is_default"],
        "active": rig_row["active"],
        "notes": rig_row.get("notes"),
        "created_at": rig_row["created_at"],
        "updated_at": rig_row["updated_at"],
        "calculators": calculators,
        "warnings": warnings,
    }


async def _get_rig_summary(conn, rig_id: int) -> dict:
    """Fetch a rig from the rig_summary view or raise 404."""
    row = await conn.execute("SELECT * FROM rig_summary WHERE id = ?", (rig_id,))
    result = await row.fetchone()
    if result is None:
        raise HTTPException(status_code=404, detail="Rig not found")
    return _row_to_dict(result)


async def _save_filter_slots(conn, rig_id: int, slots: list) -> None:
    """Delete existing filter slots and insert new ones."""
    await conn.execute("DELETE FROM rig_filter_slot WHERE rig_id = ?", (rig_id,))
    for slot in slots:
        s = _slot_as_dict(slot)
        await conn.execute(
            "INSERT INTO rig_filter_slot (rig_id, slot_number, filter_id) VALUES (?, ?, ?)",
            (rig_id, s["slot_number"], s["filter_id"]),
        )


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/equipment-options", response_model=EquipmentOptionsOut)
async def get_equipment_options():
    """Return active equipment grouped for dropdown population."""
    async with get_db() as conn:
        # Telescopes with configurations
        tc_rows = await conn.execute(
            """
            SELECT tc.id, tc.config_name, tc.effective_focal_length_mm,
                   tc.effective_focal_ratio, tc.effective_image_circle_mm,
                   t.id AS telescope_id, t.model_name AS telescope_name,
                   t.aperture_mm, t.is_mine, m.name AS manufacturer_name
            FROM telescope_configuration tc
            JOIN telescope t ON t.id = tc.telescope_id
            JOIN manufacturer m ON m.id = t.manufacturer_id
            WHERE tc.active = 1 AND t.active = 1
            ORDER BY t.is_mine DESC, m.name, t.model_name, tc.config_name
            """
        )
        telescopes_map: dict[int, dict] = {}
        for r in await tc_rows.fetchall():
            d = _row_to_dict(r)
            tid = d["telescope_id"]
            if tid not in telescopes_map:
                telescopes_map[tid] = {
                    "telescope_id": tid,
                    "telescope_name": d["telescope_name"],
                    "manufacturer_name": d["manufacturer_name"],
                    "aperture_mm": d["aperture_mm"],
                    "is_mine": bool(d["is_mine"]),
                    "configs": [],
                }
            telescopes_map[tid]["configs"].append(
                {
                    "id": d["id"],
                    "config_name": d["config_name"],
                    "effective_focal_length_mm": d["effective_focal_length_mm"],
                    "effective_focal_ratio": d["effective_focal_ratio"],
                    "effective_image_circle_mm": d.get("effective_image_circle_mm"),
                }
            )
        telescopes = list(telescopes_map.values())

        # Cameras
        cam_rows = await conn.execute(
            """
            SELECT c.id, c.model_name, m.name AS manufacturer_name,
                   s.pixel_size_um, s.resolution_x, s.resolution_y,
                   s.sensor_width_mm, s.sensor_height_mm, s.sensor_type,
                   c.is_mine
            FROM camera c
            JOIN manufacturer m ON m.id = c.manufacturer_id
            JOIN sensor s ON s.id = c.sensor_id
            WHERE c.active = 1
            ORDER BY c.is_mine DESC, m.name, c.model_name
            """
        )
        cameras = [_row_to_dict(r) for r in await cam_rows.fetchall()]

        # Filter wheels
        fw_rows = await conn.execute(
            """
            SELECT fw.id, fw.model_name, m.name AS manufacturer_name,
                   fw.num_positions, fw.is_mine
            FROM filter_wheel fw
            JOIN manufacturer m ON m.id = fw.manufacturer_id
            WHERE fw.active = 1
            ORDER BY fw.is_mine DESC, m.name, fw.model_name
            """
        )
        filter_wheels = [_row_to_dict(r) for r in await fw_rows.fetchall()]

        # Filters
        f_rows = await conn.execute(
            """
            SELECT f.id, f.model_name, m.name AS manufacturer_name,
                   ft.display_name AS filter_type_name, f.is_mine
            FROM filter f
            JOIN manufacturer m ON m.id = f.manufacturer_id
            JOIN filter_type ft ON ft.id = f.filter_type_id
            WHERE f.active = 1
            ORDER BY f.is_mine DESC, m.name, f.model_name
            """
        )
        filters = [_row_to_dict(r) for r in await f_rows.fetchall()]

        # Mounts
        mt_rows = await conn.execute(
            """
            SELECT mt.id, mt.model_name, m.name AS manufacturer_name,
                   mt.is_mine
            FROM mount mt
            JOIN manufacturer m ON m.id = mt.manufacturer_id
            WHERE mt.active = 1
            ORDER BY mt.is_mine DESC, m.name, mt.model_name
            """
        )
        mounts = [_row_to_dict(r) for r in await mt_rows.fetchall()]

        # Focusers
        foc_rows = await conn.execute(
            """
            SELECT foc.id, foc.model_name, m.name AS manufacturer_name,
                   foc.is_mine
            FROM focuser foc
            JOIN manufacturer m ON m.id = foc.manufacturer_id
            WHERE foc.active = 1
            ORDER BY foc.is_mine DESC, m.name, foc.model_name
            """
        )
        focusers = [_row_to_dict(r) for r in await foc_rows.fetchall()]

        # OAGs
        oag_rows = await conn.execute(
            """
            SELECT o.id, o.model_name, m.name AS manufacturer_name,
                   o.is_mine
            FROM oag o
            JOIN manufacturer m ON m.id = o.manufacturer_id
            WHERE o.active = 1
            ORDER BY o.is_mine DESC, m.name, o.model_name
            """
        )
        oags = [_row_to_dict(r) for r in await oag_rows.fetchall()]

        # Guide scopes
        gs_rows = await conn.execute(
            """
            SELECT gs.id, gs.model_name, m.name AS manufacturer_name,
                   gs.focal_length_mm, gs.is_mine
            FROM guide_scope gs
            JOIN manufacturer m ON m.id = gs.manufacturer_id
            WHERE gs.active = 1
            ORDER BY gs.is_mine DESC, m.name, gs.model_name
            """
        )
        guide_scopes = [_row_to_dict(r) for r in await gs_rows.fetchall()]

        # Computers
        comp_rows = await conn.execute(
            """
            SELECT c.id, c.model_name, m.name AS manufacturer_name,
                   c.is_mine
            FROM computer c
            JOIN manufacturer m ON m.id = c.manufacturer_id
            WHERE c.active = 1
            ORDER BY c.is_mine DESC, m.name, c.model_name
            """
        )
        computers = [_row_to_dict(r) for r in await comp_rows.fetchall()]

        # Software
        sw_rows = await conn.execute(
            """
            SELECT id, name, category, is_mine FROM software
            WHERE active = 1
            ORDER BY is_mine DESC, name
            """
        )
        software = [_row_to_dict(r) for r in await sw_rows.fetchall()]

        return {
            "telescopes": telescopes,
            "cameras": cameras,
            "filter_wheels": filter_wheels,
            "filters": filters,
            "mounts": mounts,
            "focusers": focusers,
            "oags": oags,
            "guide_scopes": guide_scopes,
            "computers": computers,
            "software": software,
        }


@router.get("", response_model=list[RigOut])
async def list_rigs(
    active_only: bool = Query(True, description="Only show active rigs"),
    location_id: int | None = Query(None, description="Location for seeing data"),
):
    """List all rigs with calculator data."""
    async with get_db() as conn:
        if active_only:
            rows = await conn.execute(
                "SELECT * FROM rig_summary WHERE active = 1 ORDER BY is_default DESC, name"
            )
        else:
            rows = await conn.execute("SELECT * FROM rig_summary ORDER BY is_default DESC, name")
        results = []
        for r in await rows.fetchall():
            d = _row_to_dict(r)
            response = await _build_rig_response(conn, d, location_id=location_id)
            results.append(response)
        return results


@router.get("/{rig_id}", response_model=RigOut)
async def get_rig(
    rig_id: int,
    location_id: int | None = Query(None, description="Location for seeing data"),
):
    """Get a single rig by ID."""
    async with get_db() as conn:
        rig_row = await _get_rig_summary(conn, rig_id)
        return await _build_rig_response(conn, rig_row, location_id=location_id)


@router.post("", response_model=RigOut, status_code=201)
async def create_rig(body: RigCreate):
    """Create a new rig."""
    async with get_db() as conn:
        # Validate filter slots
        await _validate_filter_slots(conn, body.filter_slots, body.filter_wheel_id)

        # Handle default flag
        if body.is_default:
            await _ensure_single_default(conn, -1)  # Clear all defaults temporarily

        try:
            cursor = await conn.execute(
                """INSERT INTO rig (
                    name, description, telescope_configuration_id, camera_id,
                    filter_wheel_id, single_filter_id, mount_id, focuser_id,
                    oag_id, guide_scope_id, guide_camera_id, computer_id,
                    is_default, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    body.name.strip(),
                    body.description,
                    body.telescope_configuration_id,
                    body.camera_id,
                    body.filter_wheel_id,
                    body.single_filter_id,
                    body.mount_id,
                    body.focuser_id,
                    body.oag_id,
                    body.guide_scope_id,
                    body.guide_camera_id,
                    body.computer_id,
                    1 if body.is_default else 0,
                    body.notes,
                ),
            )
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(
                    status_code=409,
                    detail=f"A rig with the name '{body.name}' already exists",
                )
            raise

        new_id = cursor.lastrowid

        # Save filter slots
        if body.filter_slots:
            await _save_filter_slots(conn, new_id, body.filter_slots)

        # Save software links
        if body.software_ids:
            await _save_software(conn, new_id, body.software_ids)

        await conn.commit()

        rig_row = await _get_rig_summary(conn, new_id)
        return await _build_rig_response(conn, rig_row)


@router.put("/{rig_id}", response_model=RigOut)
async def update_rig(rig_id: int, body: RigUpdate):
    """Update an existing rig."""
    async with get_db() as conn:
        # Verify rig exists
        existing_row = await conn.execute("SELECT * FROM rig WHERE id = ?", (rig_id,))
        existing = await existing_row.fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Rig not found")

        updates = body.model_dump(exclude_unset=True)
        filter_slots = updates.pop("filter_slots", None)
        software_ids = updates.pop("software_ids", None)

        # Determine effective filter_wheel_id for validation
        effective_fw_id = updates.get("filter_wheel_id", existing["filter_wheel_id"])

        # If filter_wheel_id is being set to None, clear filter slots
        if "filter_wheel_id" in updates and updates["filter_wheel_id"] is None:
            await conn.execute("DELETE FROM rig_filter_slot WHERE rig_id = ?", (rig_id,))
            filter_slots = None  # Don't try to save slots

        # Validate filter slots if provided
        if filter_slots is not None:
            await _validate_filter_slots(conn, filter_slots, effective_fw_id)

        # Handle default flag
        if updates.get("is_default"):
            updates["is_default"] = 1
            await _ensure_single_default(conn, rig_id)
        elif "is_default" in updates:
            updates["is_default"] = 1 if updates["is_default"] else 0

        # Strip name if provided
        if "name" in updates and updates["name"]:
            updates["name"] = updates["name"].strip()

        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [rig_id]
            try:
                await conn.execute(
                    f"UPDATE rig SET {set_clause} WHERE id = ?",
                    values,
                )
            except Exception as exc:
                if "UNIQUE" in str(exc):
                    raise HTTPException(
                        status_code=409,
                        detail="A rig with that name already exists",
                    )
                raise

        # Replace filter slots if provided
        if filter_slots is not None:
            await _save_filter_slots(conn, rig_id, filter_slots)

        # Replace software links if provided
        if software_ids is not None:
            await _save_software(conn, rig_id, software_ids)

        await conn.commit()

        rig_row = await _get_rig_summary(conn, rig_id)
        return await _build_rig_response(conn, rig_row)


@router.delete("/{rig_id}")
async def delete_rig(rig_id: int):
    """Soft-delete a rig (sets active=0)."""
    async with get_db() as conn:
        row = await conn.execute("SELECT id FROM rig WHERE id = ?", (rig_id,))
        if await row.fetchone() is None:
            raise HTTPException(status_code=404, detail="Rig not found")

        await conn.execute("UPDATE rig SET active = 0 WHERE id = ?", (rig_id,))
        await conn.commit()

    return Response(status_code=204)


@router.post("/{rig_id}/clone", response_model=RigOut, status_code=201)
async def clone_rig(rig_id: int):
    """Clone a rig with a '(Copy)' name suffix."""
    async with get_db() as conn:
        # Fetch original rig
        orig_row = await conn.execute("SELECT * FROM rig WHERE id = ?", (rig_id,))
        original = await orig_row.fetchone()
        if original is None:
            raise HTTPException(status_code=404, detail="Rig not found")

        original = _row_to_dict(original)
        original_name = original["name"]

        # Generate unique clone name
        base_name = f"{original_name} (Copy)"
        existing = await conn.execute("SELECT id FROM rig WHERE name = ?", (base_name,))
        if await existing.fetchone() is None:
            clone_name = base_name
        else:
            n = 2
            while True:
                candidate = f"{original_name} (Copy {n})"
                check = await conn.execute("SELECT id FROM rig WHERE name = ?", (candidate,))
                if await check.fetchone() is None:
                    clone_name = candidate
                    break
                n += 1

        # Insert clone (never default)
        cursor = await conn.execute(
            """INSERT INTO rig (
                name, description, telescope_configuration_id, camera_id,
                filter_wheel_id, single_filter_id, mount_id, focuser_id,
                oag_id, guide_scope_id, guide_camera_id, computer_id,
                is_default, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)""",
            (
                clone_name,
                original["description"],
                original["telescope_configuration_id"],
                original["camera_id"],
                original["filter_wheel_id"],
                original["single_filter_id"],
                original["mount_id"],
                original["focuser_id"],
                original["oag_id"],
                original["guide_scope_id"],
                original["guide_camera_id"],
                original["computer_id"],
                original["notes"],
            ),
        )
        clone_id = cursor.lastrowid

        # Clone filter slots
        slot_rows = await conn.execute(
            "SELECT slot_number, filter_id FROM rig_filter_slot WHERE rig_id = ?",
            (rig_id,),
        )
        for s in await slot_rows.fetchall():
            await conn.execute(
                "INSERT INTO rig_filter_slot (rig_id, slot_number, filter_id) VALUES (?, ?, ?)",
                (clone_id, s["slot_number"], s["filter_id"]),
            )

        # Clone software
        sw_rows = await conn.execute(
            "SELECT software_id FROM rig_software WHERE rig_id = ?",
            (rig_id,),
        )
        for s in await sw_rows.fetchall():
            await conn.execute(
                "INSERT INTO rig_software (rig_id, software_id) VALUES (?, ?)",
                (clone_id, s["software_id"]),
            )

        await conn.commit()

        rig_row = await _get_rig_summary(conn, clone_id)
        return await _build_rig_response(conn, rig_row)


@router.post("/{rig_id}/restore", response_model=RigOut)
async def restore_rig(rig_id: int):
    """Restore a soft-deleted rig (sets active=1)."""
    async with get_db() as conn:
        row = await conn.execute("SELECT id FROM rig WHERE id = ?", (rig_id,))
        if await row.fetchone() is None:
            raise HTTPException(status_code=404, detail="Rig not found")

        await conn.execute("UPDATE rig SET active = 1 WHERE id = ?", (rig_id,))
        await conn.commit()

        rig_row = await _get_rig_summary(conn, rig_id)
        return await _build_rig_response(conn, rig_row)


@router.get("/{rig_id}/calculators", response_model=RigCalculators)
async def get_calculators(
    rig_id: int,
    location_id: int | None = Query(None, description="Location for seeing data"),
    seeing_low: float | None = Query(None, description="Override seeing low (arcsec)"),
    seeing_high: float | None = Query(None, description="Override seeing high (arcsec)"),
    guide_binning: int = Query(1, ge=1, le=4, description="Guide camera binning (1-4)"),
    centroid_accuracy_pixels: float = Query(
        0.2,
        ge=0.05,
        le=0.5,
        description="Assumed PHD2 centroid accuracy in guide pixels",
    ),
    image_binning: int = Query(
        1,
        ge=1,
        le=4,
        description="Imaging camera binning (1-4); drives headline scale and guiding tolerance",
    ),
):
    """Get calculator results for a rig."""
    async with get_db() as conn:
        rig_row = await _get_rig_summary(conn, rig_id)

        # Location and seeing resolution
        location = await _resolve_location(conn, location_id)
        loc_seeing_low = location.get("typical_seeing_low_arcsec") if location else None
        loc_seeing_high = location.get("typical_seeing_high_arcsec") if location else None
        loc_name = location.get("name") if location else None

        seeing_fwhm_low, seeing_fwhm_high, seeing_source, seeing_loc_name = resolve_seeing(
            location_seeing_low=loc_seeing_low,
            location_seeing_high=loc_seeing_high,
            location_name=loc_name,
            override_low=seeing_low,
            override_high=seeing_high,
        )

        return _build_calculators(
            rig_row,
            seeing_fwhm_low,
            seeing_fwhm_high,
            seeing_source,
            seeing_loc_name,
            guide_binning=guide_binning,
            centroid_accuracy_pixels=centroid_accuracy_pixels,
            image_binning=image_binning,
        )
