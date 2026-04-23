"""Horizons API — multiple horizons per location (v0.19.0).

Each location has ≥1 horizon: at most one ``type='custom'`` polyline
shape, plus zero-to-many ``type='artificial'`` flat-altitude horizons.
Exactly one row per location is ``is_default=1`` (enforced by a partial
unique index); the planner's default-for-location selection uses it.

Mounted at ``/api/locations/{location_id}/horizons``. The location
must exist and be active for every endpoint except the three export
endpoints, which allow soft-deleted locations so users can recover
exports from a deactivated site.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from nightcrate.api._common import integrity_guard
from nightcrate.api.horizon_models import (
    HorizonCreate,
    HorizonImportResponse,
    HorizonParseResponse,
    HorizonPointModel,
    HorizonResponse,
    HorizonUpdate,
    LocationHorizonsReplace,
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/locations/{location_id}/horizons", tags=["Horizons"])
parse_router = APIRouter(prefix="/api/horizons", tags=["Horizons"])


async def _parse_upload_file(file: UploadFile) -> HorizonParseResult:
    """Read an UploadFile as UTF-8 text and parse it. Translates UTF-8 and
    parser failures into HTTP 400s. Shared by ``POST /horizons/import`` and
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


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _fetch_location(conn, location_id: int, *, allow_inactive: bool) -> dict:
    sql = "SELECT * FROM location WHERE id = ?"
    if not allow_inactive:
        sql += " AND active = 1"
    row = await (await conn.execute(sql, (location_id,))).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Location not found: {location_id}")
    return dict(row)


async def _fetch_horizon_row(conn, location_id: int, horizon_id: int) -> dict:
    row = await (
        await conn.execute(
            "SELECT * FROM location_horizon WHERE id = ? AND location_id = ?",
            (horizon_id, location_id),
        )
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Horizon not found: {horizon_id}")
    return dict(row)


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
    points = await _fetch_points(conn, horizon_row["id"]) if horizon_row["type"] == "custom" else []
    return HorizonResponse(
        id=horizon_row["id"],
        location_id=horizon_row["location_id"],
        name=horizon_row["name"],
        type=horizon_row["type"],
        flat_altitude_deg=horizon_row["flat_altitude_deg"],
        source=horizon_row["source"],
        source_filename=horizon_row["source_filename"],
        notes=horizon_row["notes"],
        points=points,
        is_default=bool(horizon_row["is_default"]),
        created_at=horizon_row["created_at"],
        updated_at=horizon_row["updated_at"],
    )


async def _promote_to_default(conn, location_id: int, horizon_id: int) -> None:
    """Clear the old default and set ``horizon_id`` as the new default.

    Two-step so the partial unique index (exactly one default per
    location) never sees two candidates at once.
    """
    await conn.execute(
        "UPDATE location_horizon SET is_default = 0 WHERE location_id = ? AND id != ?",
        (location_id, horizon_id),
    )
    await conn.execute(
        "UPDATE location_horizon SET is_default = 1, updated_at = datetime('now') WHERE id = ?",
        (horizon_id,),
    )


async def _write_points(conn, horizon_id: int, points: list[tuple[float, float]]) -> None:
    await conn.execute("DELETE FROM location_horizon_point WHERE horizon_id = ?", (horizon_id,))
    if points:
        await conn.executemany(
            "INSERT INTO location_horizon_point (horizon_id, azimuth_deg, altitude_deg) "
            "VALUES (?, ?, ?)",
            [(horizon_id, az, alt) for az, alt in points],
        )


async def _count_horizons(conn, location_id: int) -> int:
    row = await (
        await conn.execute(
            "SELECT COUNT(*) AS cnt FROM location_horizon WHERE location_id = ?",
            (location_id,),
        )
    ).fetchone()
    return int(row["cnt"])


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=list[HorizonResponse])
async def list_horizons(location_id: int) -> list[HorizonResponse]:
    """List all horizons for a location.

    Ordering: default first, then custom before artificial (so the
    "drawn" shape — if any — always surfaces above the flat ladder),
    then by ascending flat altitude for artificial horizons and by
    name for customs.
    """
    async with get_db() as conn:
        await _fetch_location(conn, location_id, allow_inactive=False)
        rows = await (
            await conn.execute(
                """
                SELECT * FROM location_horizon
                WHERE location_id = ?
                ORDER BY is_default DESC,
                         CASE type WHEN 'custom' THEN 0 ELSE 1 END,
                         flat_altitude_deg ASC,
                         name ASC
                """,
                (location_id,),
            )
        ).fetchall()
        return [await _build_response(conn, dict(r)) for r in rows]


@router.put("", response_model=list[HorizonResponse])
async def replace_horizons(
    location_id: int, body: LocationHorizonsReplace
) -> list[HorizonResponse]:
    """Atomically replace this location's full horizon set.

    Takes the complete desired state; the server computes the diff
    against the current rows and applies creates / updates / deletes
    in one SQL transaction. Used by the Location editor's staged-save
    flow so partial-network-failure mid-save can't corrupt the dirty-
    state invariant (every change either fully lands or none of it
    does).

    Body invariants (Pydantic-validated at 422):
      * ``horizons`` non-empty
      * exactly one ``is_default=true``
      * at most one ``type='custom'``
      * unique names within the payload
      * unique ids within the payload (no id repeats)

    Additional server-side checks (422):
      * every ``id`` belongs to this location
      * no id duplicates across payload vs current-server state after
        applying creates/updates (guaranteed by the Pydantic "unique
        ids" rule + the fact that new rows don't have ids)

    The server enforces the "exactly one default" partial unique index
    by demoting every row to ``is_default=0`` first and promoting the
    chosen default last in the same transaction. The at-most-one-
    custom partial unique is protected by validating ≤1 custom in the
    payload and applying deletes before inserts so a replace-custom
    pattern (delete old + create new) doesn't momentarily have two
    custom rows.
    """
    async with get_db() as conn:
        await _fetch_location(conn, location_id, allow_inactive=False)

        # Snapshot the current server state so we can compute the diff.
        current_rows = await (
            await conn.execute(
                "SELECT id FROM location_horizon WHERE location_id = ?",
                (location_id,),
            )
        ).fetchall()
        current_ids: set[int] = {int(r["id"]) for r in current_rows}

        # Validate every supplied id belongs to this location.
        payload_existing_ids = {h.id for h in body.horizons if h.id is not None}
        stray = payload_existing_ids - current_ids
        if stray:
            raise HTTPException(
                status_code=422,
                detail=(f"horizons: id(s) {sorted(stray)} do not belong to location {location_id}"),
            )

        # Diff: server rows missing from the payload → DELETE.
        to_delete = current_ids - payload_existing_ids

        try:
            # 1. Demote every current default. Prevents the partial unique
            #    index from firing when a new row is later inserted with
            #    is_default=1 while an old default is still in place.
            await conn.execute(
                "UPDATE location_horizon SET is_default = 0 "
                "WHERE location_id = ? AND is_default = 1",
                (location_id,),
            )

            # 2. Deletes first. Handling this before inserts means a
            #    "replace custom" pattern (delete old custom + insert new
            #    custom in one PUT) doesn't momentarily violate the
            #    idx_location_horizon_one_custom partial unique index.
            #    Points cascade via FK ON DELETE CASCADE.
            for hid in to_delete:
                await conn.execute("DELETE FROM location_horizon WHERE id = ?", (hid,))

            # 3. Updates on existing rows.
            id_to_new_horizon: dict[int, int] = {}
            for h in body.horizons:
                if h.id is None:
                    continue
                source = h.source if h.type == "custom" else None
                source_filename = h.source_filename if h.type == "custom" else None
                with integrity_guard(conflict_detail="Horizon name conflict on replace."):
                    await conn.execute(
                        """
                        UPDATE location_horizon SET
                            name = ?, type = ?, flat_altitude_deg = ?,
                            source = ?, source_filename = ?, notes = ?,
                            is_default = 0,
                            updated_at = datetime('now')
                        WHERE id = ?
                        """,
                        (
                            h.name.strip(),
                            h.type,
                            h.flat_altitude_deg,
                            source,
                            source_filename,
                            h.notes,
                            h.id,
                        ),
                    )
                if h.type == "custom":
                    await _write_points(
                        conn, h.id, [(p.azimuth_deg, p.altitude_deg) for p in h.points or []]
                    )

            # 4. Inserts for new rows (no id in payload).
            for h in body.horizons:
                if h.id is not None:
                    continue
                source = h.source if h.type == "custom" else None
                source_filename = h.source_filename if h.type == "custom" else None
                with integrity_guard(
                    conflict_detail=(
                        "Horizon name conflict, or duplicate custom horizon in replace set."
                    )
                ):
                    cursor = await conn.execute(
                        """
                        INSERT INTO location_horizon (
                            location_id, name, type, flat_altitude_deg,
                            source, source_filename, notes, is_default
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                        """,
                        (
                            location_id,
                            h.name.strip(),
                            h.type,
                            h.flat_altitude_deg,
                            source,
                            source_filename,
                            h.notes,
                        ),
                    )
                new_id = cursor.lastrowid
                if new_id is None:
                    raise RuntimeError("horizon INSERT returned no row id")
                # Remember the mapping if the caller wants this new row
                # to be the default — we'll promote it below by position.
                idx = body.horizons.index(h)
                id_to_new_horizon[idx] = new_id
                if h.type == "custom" and h.points:
                    await _write_points(
                        conn, new_id, [(p.azimuth_deg, p.altitude_deg) for p in h.points]
                    )

            # 5. Promote the single default. Exactly one of the payload
            #    rows has is_default=true (Pydantic validator ensures);
            #    look it up and PATCH is_default=1 — previous default
            #    already demoted in step 1.
            default_idx = next(i for i, h in enumerate(body.horizons) if h.is_default)
            default_row = body.horizons[default_idx]
            resolved_default_id = (
                default_row.id if default_row.id is not None else id_to_new_horizon[default_idx]
            )
            await conn.execute(
                "UPDATE location_horizon SET is_default = 1, updated_at = datetime('now') "
                "WHERE id = ?",
                (resolved_default_id,),
            )

            await conn.commit()
        except HTTPException:
            await conn.rollback()
            raise
        except Exception:
            await conn.rollback()
            raise

        # Return the fresh server state.
        rows = await (
            await conn.execute(
                """
                SELECT * FROM location_horizon
                WHERE location_id = ?
                ORDER BY is_default DESC,
                         CASE type WHEN 'custom' THEN 0 ELSE 1 END,
                         flat_altitude_deg ASC,
                         name ASC
                """,
                (location_id,),
            )
        ).fetchall()
        return [await _build_response(conn, dict(r)) for r in rows]


@router.get("/{horizon_id}", response_model=HorizonResponse)
async def get_horizon(location_id: int, horizon_id: int) -> HorizonResponse:
    async with get_db() as conn:
        await _fetch_location(conn, location_id, allow_inactive=False)
        row = await _fetch_horizon_row(conn, location_id, horizon_id)
        return await _build_response(conn, row)


@router.post("", response_model=HorizonResponse, status_code=201)
async def create_horizon(location_id: int, body: HorizonCreate) -> HorizonResponse:
    async with get_db() as conn:
        await _fetch_location(conn, location_id, allow_inactive=False)
        source = body.source if body.type == "custom" else None
        source_filename = body.source_filename if body.type == "custom" else None

        with integrity_guard(
            conflict_detail=(
                "Location already has a horizon by that name, or already "
                "has a custom horizon (only one allowed per location)."
            )
        ):
            cursor = await conn.execute(
                """
                INSERT INTO location_horizon (
                    location_id, name, type, flat_altitude_deg,
                    source, source_filename, notes, is_default
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    location_id,
                    body.name.strip(),
                    body.type,
                    body.flat_altitude_deg if body.type == "artificial" else None,
                    source,
                    source_filename,
                    body.notes,
                    # is_default always 0 at insert; `_promote_to_default`
                    # then handles the "one default per location" index.
                ),
            )
        new_id = cursor.lastrowid

        if body.type == "custom" and body.points:
            await _write_points(
                conn, new_id, [(p.azimuth_deg, p.altitude_deg) for p in body.points]
            )

        if body.is_default:
            await _promote_to_default(conn, location_id, new_id)

        await conn.commit()
        row = await _fetch_horizon_row(conn, location_id, new_id)
        return await _build_response(conn, row)


@router.patch("/{horizon_id}", response_model=HorizonResponse)
async def update_horizon(location_id: int, horizon_id: int, body: HorizonUpdate) -> HorizonResponse:
    async with get_db() as conn:
        await _fetch_location(conn, location_id, allow_inactive=False)
        existing = await _fetch_horizon_row(conn, location_id, horizon_id)

        updates = body.model_dump(exclude_unset=True)
        # ``points`` and ``is_default`` have dedicated handling below.
        points = updates.pop("points", None)
        make_default = updates.pop("is_default", None)

        # Type-specific validation — CHECK constraint also enforces this,
        # but a 422 with an actionable message is friendlier than the
        # generic integrity-guard 409.
        if existing["type"] == "artificial" and "flat_altitude_deg" in updates:
            if updates["flat_altitude_deg"] is None:
                raise HTTPException(
                    status_code=422,
                    detail="Artificial horizon requires a flat_altitude_deg value.",
                )
        if existing["type"] == "custom" and "flat_altitude_deg" in updates:
            raise HTTPException(
                status_code=422,
                detail="Custom horizons do not use flat_altitude_deg.",
            )
        if existing["type"] == "artificial" and points is not None:
            raise HTTPException(
                status_code=422,
                detail="Artificial horizons do not take points.",
            )

        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            set_clause += ", updated_at = datetime('now')"
            values = [*updates.values(), horizon_id]
            with integrity_guard(conflict_detail="Horizon name already in use for this location."):
                await conn.execute(
                    f"UPDATE location_horizon SET {set_clause} WHERE id = ?",  # noqa: S608  # nosec B608
                    values,
                )

        if existing["type"] == "custom" and points is not None:
            await _write_points(
                conn, horizon_id, [(p["azimuth_deg"], p["altitude_deg"]) for p in points]
            )
            # Writing new points bumps updated_at so cached snapshots
            # keyed on it invalidate.
            await conn.execute(
                "UPDATE location_horizon SET updated_at = datetime('now') WHERE id = ?",
                (horizon_id,),
            )

        if make_default:
            await _promote_to_default(conn, location_id, horizon_id)
        elif make_default is False and existing["is_default"]:
            # Demoting the current default isn't allowed — every location
            # must have exactly one default. Clients should promote the
            # replacement instead; that path atomically demotes the old.
            raise HTTPException(
                status_code=422,
                detail=(
                    "Promote another horizon to default first; "
                    "a location must have exactly one default."
                ),
            )

        await conn.commit()
        row = await _fetch_horizon_row(conn, location_id, horizon_id)
        return await _build_response(conn, row)


@router.delete("/{horizon_id}", status_code=204)
async def delete_horizon(location_id: int, horizon_id: int) -> Response:
    """Delete one horizon.

    Refuses to delete the last remaining horizon on a location (422) —
    every location must have ≥1 horizon for the planner to operate.
    If the deleted row was the default, promotes the first remaining
    row in the list ordering (default/custom-first/alt-ascending).
    """
    async with get_db() as conn:
        await _fetch_location(conn, location_id, allow_inactive=False)
        existing = await _fetch_horizon_row(conn, location_id, horizon_id)
        total = await _count_horizons(conn, location_id)
        if total <= 1:
            raise HTTPException(
                status_code=422,
                detail="Cannot delete the last horizon. Every location must have at least one.",
            )

        await conn.execute("DELETE FROM location_horizon WHERE id = ?", (horizon_id,))

        if existing["is_default"]:
            # Promote a replacement — pick whichever row list_horizons
            # would put first (custom over artificial, lowest altitude
            # first on ties, name alphabetically last).
            next_row = await (
                await conn.execute(
                    """
                    SELECT id FROM location_horizon
                    WHERE location_id = ?
                    ORDER BY CASE type WHEN 'custom' THEN 0 ELSE 1 END,
                             flat_altitude_deg ASC,
                             name ASC
                    LIMIT 1
                    """,
                    (location_id,),
                )
            ).fetchone()
            if next_row is not None:
                await _promote_to_default(conn, location_id, int(next_row["id"]))

        await conn.commit()
    return Response(status_code=204)


@router.post("/import", response_model=HorizonImportResponse)
async def import_horizon(location_id: int, file: UploadFile = File(...)) -> HorizonImportResponse:
    """Import a horizon file as a new custom horizon.

    If the location already has a custom horizon, it gets replaced —
    one custom per location is the enforced invariant. The imported
    row inherits the existing custom's default flag so switching
    providers doesn't silently demote the user's selection.
    """
    async with get_db() as conn:
        await _fetch_location(conn, location_id, allow_inactive=False)
        result = await _parse_upload_file(file)

        existing = await (
            await conn.execute(
                "SELECT id, is_default, name FROM location_horizon "
                "WHERE location_id = ? AND type = 'custom'",
                (location_id,),
            )
        ).fetchone()

        if existing is None:
            cursor = await conn.execute(
                """
                INSERT INTO location_horizon (
                    location_id, name, type, source, source_filename, is_default
                ) VALUES (?, ?, 'custom', 'imported', ?, 0)
                """,
                (
                    location_id,
                    "Custom horizon",
                    result.source_filename,
                ),
            )
            horizon_id = cursor.lastrowid
            # First-time import — promote the new custom horizon to
            # default so the planner actually uses it. Without this
            # the auto-seeded ``0° flat`` artificial default stays
            # active and the user's NINA / Stellarium / Telescopius
            # import has no visible effect on the planner.
            promote_to_default = True
        else:
            horizon_id = int(existing["id"])
            # Replacement import — preserve whatever the user had set
            # as default. If the existing custom was default, the
            # replaced row stays default (the UPDATE below just bumps
            # updated_at); if it wasn't, respect that choice.
            promote_to_default = False
            await conn.execute(
                """
                UPDATE location_horizon
                SET source = 'imported', source_filename = ?,
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (result.source_filename, horizon_id),
            )

        await _write_points(conn, horizon_id, result.points)

        if promote_to_default:
            await _promote_to_default(conn, location_id, horizon_id)

        await conn.commit()
        row = await _fetch_horizon_row(conn, location_id, horizon_id)
        response = await _build_response(conn, row)
        return HorizonImportResponse(horizon=response, warnings=result.warnings)


# ── Exports ──────────────────────────────────────────────────────────────────


async def _require_custom_horizon_for_export(
    conn, location_id: int, horizon_id: int
) -> tuple[dict, list[tuple[float, float]]]:
    loc = await _fetch_location(conn, location_id, allow_inactive=True)
    horizon_row = await _fetch_horizon_row(conn, location_id, horizon_id)
    if horizon_row["type"] != "custom":
        raise HTTPException(
            status_code=422, detail="Artificial horizons cannot be exported as files."
        )
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


@router.get("/{horizon_id}/export/nina.hrz")
async def export_nina(location_id: int, horizon_id: int) -> Response:
    async with get_db() as conn:
        loc, points = await _require_custom_horizon_for_export(conn, location_id, horizon_id)
        text = export_nina_hrz(loc["name"], points)
        slug = sanitize_filename(loc["name"])
        return Response(
            content=text,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{slug}.hrz"'},
        )


@router.get("/{horizon_id}/export/stellarium.zip")
async def export_stellarium(location_id: int, horizon_id: int) -> Response:
    async with get_db() as conn:
        loc, points = await _require_custom_horizon_for_export(conn, location_id, horizon_id)
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


@router.get("/{horizon_id}/export/csv")
async def export_csv_endpoint(location_id: int, horizon_id: int) -> Response:
    async with get_db() as conn:
        loc, points = await _require_custom_horizon_for_export(conn, location_id, horizon_id)
        text = export_csv(points)
        slug = sanitize_filename(loc["name"])
        return Response(
            content=text,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{slug}_horizon.csv"'},
        )


# ── Stateless parse (staged-save flow kept for backwards-compat) ─────────────


@parse_router.post("/parse", response_model=HorizonParseResponse)
async def parse_horizon(file: UploadFile = File(...)) -> HorizonParseResponse:
    """Parse a horizon file and return points + warnings without touching
    the database. Used by the custom-horizon editor when the user is
    iterating on an imported polyline before committing it."""
    result = await _parse_upload_file(file)
    return HorizonParseResponse(
        points=[HorizonPointModel(azimuth_deg=az, altitude_deg=alt) for az, alt in result.points],
        warnings=result.warnings,
        source_filename=result.source_filename,
    )


# ``Literal`` used only inside model validators; keep the import alive
# so `from nightcrate.api.horizons import *` re-exports don't break.
_ = Literal
