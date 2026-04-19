"""Custom horizon API — one horizon per location, import / edit / export.

Mounted at ``/api/locations/{location_id}/horizon``. The location must
exist and be active for every endpoint except the three export endpoints,
which allow soft-deleted locations so users can recover exports from a
deactivated site.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from nightcrate.api._common import integrity_guard
from nightcrate.api.horizon_models import (
    HorizonImportResponse,
    HorizonPointModel,
    HorizonPut,
    HorizonResponse,
)
from nightcrate.db.session import get_db
from nightcrate.services.horizon import (
    HorizonParseError,
    HorizonParseResult,
    export_csv,
    export_nina_hrz,
    export_stellarium_zip,
    parse_horizon_text,
    sanitize_filename,
)


async def parse_upload_file(file: UploadFile) -> HorizonParseResult:
    """Read an UploadFile as UTF-8 text and parse it. Translates UTF-8 and
    parser failures into HTTP 400s. Shared by ``POST /horizon/import`` and
    ``POST /horizons/parse``."""
    try:
        raw = await file.read()
    finally:
        await file.close()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"File is not valid UTF-8 text: {exc}") from exc
    try:
        return parse_horizon_text(text, source_filename=file.filename)
    except HorizonParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/locations/{location_id}/horizon", tags=["Horizons"])


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _fetch_location(conn, location_id: int, *, allow_inactive: bool) -> dict:
    sql = "SELECT * FROM location WHERE id = ?"
    if not allow_inactive:
        sql += " AND active = 1"
    row = await (await conn.execute(sql, (location_id,))).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Location not found: {location_id}")
    return dict(row)


async def _fetch_horizon_row(conn, location_id: int) -> dict | None:
    row = await (
        await conn.execute("SELECT * FROM location_horizon WHERE location_id = ?", (location_id,))
    ).fetchone()
    return dict(row) if row else None


async def _fetch_points(conn, horizon_id: int) -> list[HorizonPointModel]:
    rows = await (
        await conn.execute(
            "SELECT azimuth_deg, altitude_deg FROM location_horizon_point "
            "WHERE horizon_id = ? ORDER BY azimuth_deg",
            (horizon_id,),
        )
    ).fetchall()
    return [
        HorizonPointModel(azimuth_deg=r["azimuth_deg"], altitude_deg=r["altitude_deg"])
        for r in rows
    ]


async def _build_response(conn, horizon_row: dict) -> HorizonResponse:
    points = await _fetch_points(conn, horizon_row["id"])
    return HorizonResponse(
        location_id=horizon_row["location_id"],
        source=horizon_row["source"],
        source_filename=horizon_row["source_filename"],
        notes=horizon_row["notes"],
        points=points,
        created_at=horizon_row["created_at"],
        updated_at=horizon_row["updated_at"],
    )


async def _replace_horizon(
    conn,
    location_id: int,
    source: Literal["imported", "drawn"],
    points: list[tuple[float, float]],
    source_filename: str | None = None,
    notes: str | None = None,
) -> dict:
    """Upsert the horizon row and replace all points atomically."""
    existing = await _fetch_horizon_row(conn, location_id)
    if existing is None:
        # Concurrent PUTs could both see no existing row and race on the
        # UNIQUE(location_id) constraint; the loser becomes a 409.
        with integrity_guard(conflict_detail="Location already has a horizon (concurrent save)."):
            cursor = await conn.execute(
                "INSERT INTO location_horizon (location_id, source, source_filename, notes) "
                "VALUES (?, ?, ?, ?)",
                (location_id, source, source_filename, notes),
            )
        horizon_id = cursor.lastrowid
    else:
        horizon_id = existing["id"]
        await conn.execute(
            "UPDATE location_horizon "
            "SET source = ?, source_filename = ?, notes = ?, updated_at = datetime('now') "
            "WHERE id = ?",
            (source, source_filename, notes, horizon_id),
        )
        await conn.execute("DELETE FROM location_horizon_point WHERE horizon_id = ?", (horizon_id,))
    if points:
        await conn.executemany(
            "INSERT INTO location_horizon_point (horizon_id, azimuth_deg, altitude_deg) "
            "VALUES (?, ?, ?)",
            [(horizon_id, az, alt) for az, alt in points],
        )
    await conn.commit()
    row = await _fetch_horizon_row(conn, location_id)
    if row is None:
        # Unreachable: we just upserted this row. Guard narrows the type.
        raise RuntimeError("horizon row missing immediately after upsert")
    return row


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=HorizonResponse)
async def get_horizon(location_id: int) -> HorizonResponse:
    async with get_db() as conn:
        await _fetch_location(conn, location_id, allow_inactive=False)
        horizon = await _fetch_horizon_row(conn, location_id)
        if horizon is None:
            raise HTTPException(status_code=404, detail="No horizon defined for this location.")
        return await _build_response(conn, horizon)


@router.put("", response_model=HorizonResponse)
async def put_horizon(location_id: int, body: HorizonPut) -> HorizonResponse:
    async with get_db() as conn:
        await _fetch_location(conn, location_id, allow_inactive=False)
        points = [(p.azimuth_deg, p.altitude_deg) for p in body.points]
        horizon = await _replace_horizon(
            conn,
            location_id,
            source="drawn",
            points=points,
            source_filename=None,
            notes=body.notes,
        )
        return await _build_response(conn, horizon)


@router.delete("", status_code=204)
async def delete_horizon(location_id: int) -> Response:
    async with get_db() as conn:
        await _fetch_location(conn, location_id, allow_inactive=False)
        existing = await _fetch_horizon_row(conn, location_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="No horizon defined for this location.")
        # ON DELETE CASCADE on the FK takes care of the points.
        await conn.execute("DELETE FROM location_horizon WHERE id = ?", (existing["id"],))
        await conn.commit()
    return Response(status_code=204)


@router.post("/import", response_model=HorizonImportResponse)
async def import_horizon(location_id: int, file: UploadFile = File(...)) -> HorizonImportResponse:
    async with get_db() as conn:
        await _fetch_location(conn, location_id, allow_inactive=False)
        result = await parse_upload_file(file)
        horizon = await _replace_horizon(
            conn,
            location_id,
            source="imported",
            points=result.points,
            source_filename=result.source_filename,
        )
        response = await _build_response(conn, horizon)
        return HorizonImportResponse(horizon=response, warnings=result.warnings)


# ── Exports ──────────────────────────────────────────────────────────────────


async def _require_horizon_for_export(
    conn, location_id: int
) -> tuple[dict, list[tuple[float, float]]]:
    loc = await _fetch_location(conn, location_id, allow_inactive=True)
    horizon_row = await _fetch_horizon_row(conn, location_id)
    if horizon_row is None:
        raise HTTPException(status_code=404, detail="No horizon defined for this location.")
    rows = await (
        await conn.execute(
            "SELECT azimuth_deg, altitude_deg FROM location_horizon_point "
            "WHERE horizon_id = ? ORDER BY azimuth_deg",
            (horizon_row["id"],),
        )
    ).fetchall()
    points = [(r["azimuth_deg"], r["altitude_deg"]) for r in rows]
    if len(points) < 2:
        raise HTTPException(status_code=404, detail="Horizon has fewer than 2 points.")
    return loc, points


@router.get("/export/nina.hrz")
async def export_nina(location_id: int) -> Response:
    async with get_db() as conn:
        loc, points = await _require_horizon_for_export(conn, location_id)
        text = export_nina_hrz(loc["name"], points)
        slug = sanitize_filename(loc["name"])
        return Response(
            content=text,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{slug}.hrz"'},
        )


@router.get("/export/stellarium.zip")
async def export_stellarium(location_id: int) -> Response:
    async with get_db() as conn:
        loc, points = await _require_horizon_for_export(conn, location_id)
        payload = export_stellarium_zip(
            loc["name"],
            points,
            latitude=loc["latitude"],
            longitude=loc["longitude"],
            elevation_m=loc.get("elevation_m"),
        )
        slug = sanitize_filename(loc["name"])
        return Response(
            content=payload,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{slug}_landscape.zip"'},
        )


@router.get("/export/csv")
async def export_csv_endpoint(location_id: int) -> Response:
    async with get_db() as conn:
        loc, points = await _require_horizon_for_export(conn, location_id)
        text = export_csv(points)
        slug = sanitize_filename(loc["name"])
        return Response(
            content=text,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{slug}_horizon.csv"'},
        )
