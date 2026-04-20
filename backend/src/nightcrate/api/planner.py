"""Target Planner API (v0.16.0).

Routes for the "what's up tonight" planner page:

    GET  /api/planner/targets
    GET  /api/planner/targets/{dso_id}/sky-track
    GET  /api/planner/thumbnails/{dso_id}
    POST /api/planner/thumbnails/cache/clear
    GET  /api/planner/thumbnails/cache/stats

Visibility + sky-track computations are delegated to
``services/planner_*``. Thumbnail lifecycle (cache lookup, background
fetch, LRU eviction) is in ``services/thumbnails``.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Response

from nightcrate.api.planner_models import (
    CacheClearResponse,
    DarkWindowOut,
    PlannerLocationSummary,
    PlannerRigSummary,
    PlannerTargetItem,
    PlannerTargetsResponse,
    SkyTrackResponse,
    ThumbnailCacheStats,
    TwilightBandsOut,
)
from nightcrate.core.config import get_settings
from nightcrate.db.session import get_db
from nightcrate.services import thumbnails
from nightcrate.services.dso_type_groups import group_for_raw_type
from nightcrate.services.planner_sky_track import compute_sky_track
from nightcrate.services.planner_visibility import (
    DsoCoord,
    DsoVisibility,
    PlannerLocation,
    default_cache,
)
from nightcrate.services.rig_calculators import (
    COVERAGE_FRAMES_WELL_MAX_PCT,
    COVERAGE_FRAMES_WELL_MIN_PCT,
    compute_coverage_pct,
    compute_fov,
)

router = APIRouter(prefix="/api/planner", tags=["Target Planner"])


# ── DB helpers ───────────────────────────────────────────────────────────────


async def _load_planner_location(conn, location_id: int) -> PlannerLocation:
    """Fetch a location + its horizon and bundle into a ``PlannerLocation``.

    Raises 404 if the location doesn't exist or is soft-deleted, 400 if
    it lacks coordinates (the planner can't geocode).
    """
    cursor = await conn.execute(
        """
        SELECT id, latitude, longitude, elevation_m, timezone, updated_at
        FROM location
        WHERE id = ? AND active = 1
        """,
        (location_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Location {location_id} not found")
    if row["latitude"] is None or row["longitude"] is None:
        raise HTTPException(
            status_code=400,
            detail="Location lacks coordinates; add latitude/longitude to plan targets here.",
        )

    # Optional custom horizon.
    cursor = await conn.execute(
        "SELECT id, updated_at FROM location_horizon WHERE location_id = ?", (location_id,)
    )
    horizon_row = await cursor.fetchone()
    horizon_points: tuple[tuple[float, float], ...] = ()
    horizon_updated_at: str | None = None
    if horizon_row is not None:
        horizon_updated_at = horizon_row["updated_at"]
        cursor = await conn.execute(
            """
            SELECT azimuth_deg, altitude_deg
            FROM location_horizon_point
            WHERE horizon_id = ?
            ORDER BY azimuth_deg ASC
            """,
            (horizon_row["id"],),
        )
        point_rows = await cursor.fetchall()
        horizon_points = tuple(
            (float(r["azimuth_deg"]), float(r["altitude_deg"])) for r in point_rows
        )

    return PlannerLocation(
        id=int(row["id"]),
        latitude_deg=float(row["latitude"]),
        longitude_deg=float(row["longitude"]),
        elevation_m=float(row["elevation_m"]) if row["elevation_m"] is not None else None,
        timezone=row["timezone"],
        updated_at=row["updated_at"],
        horizon_points=horizon_points,
        horizon_updated_at=horizon_updated_at,
    )


async def _load_location_name_and_horizon_flag(conn, location_id: int) -> tuple[str, bool]:
    cursor = await conn.execute("SELECT name FROM location WHERE id = ?", (location_id,))
    row = await cursor.fetchone()
    name = row["name"] if row else ""
    cursor = await conn.execute(
        "SELECT 1 FROM location_horizon WHERE location_id = ? LIMIT 1", (location_id,)
    )
    has_horizon = (await cursor.fetchone()) is not None
    return name, has_horizon


async def _load_rig_fov(conn, rig_id: int) -> tuple[PlannerRigSummary, float, float]:
    """Return ``(summary, fov_major_deg, fov_minor_deg)`` for the rig.

    404 on missing/retired rig, 400 if the rig lacks the fields needed
    to compute FOV (no telescope configuration or no sensor).
    """
    cursor = await conn.execute("SELECT * FROM rig_summary WHERE id = ?", (rig_id,))
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Rig {rig_id} not found")

    focal = row["effective_focal_length_mm"]
    px = row["pixel_size_um"]
    res_x = row["sensor_resolution_x"]
    res_y = row["sensor_resolution_y"]
    if not focal or not px or not res_x or not res_y:
        raise HTTPException(
            status_code=400,
            detail="Rig is missing focal length or sensor info; FOV cannot be computed.",
        )

    width_deg, height_deg = compute_fov(
        focal_length_mm=float(focal),
        sensor_width_mm=row["sensor_width_mm"],
        sensor_height_mm=row["sensor_height_mm"],
        resolution_x=int(res_x),
        resolution_y=int(res_y),
        pixel_size_um=float(px),
    )

    fov_major = max(width_deg, height_deg)
    fov_minor = min(width_deg, height_deg)
    return (
        PlannerRigSummary(
            id=int(row["id"]),
            name=str(row["name"]),
            fov_major_deg=round(fov_major, 4),
            fov_minor_deg=round(fov_minor, 4),
        ),
        fov_major,
        fov_minor,
    )


async def _load_dso_coords(conn) -> list[DsoCoord]:
    cursor = await conn.execute(
        """
        SELECT id, ra_deg, dec_deg, maj_axis_arcmin
        FROM dso
        WHERE active = 1 AND ra_deg IS NOT NULL AND dec_deg IS NOT NULL
        """
    )
    rows = await cursor.fetchall()
    return [
        DsoCoord(
            dso_id=int(r["id"]),
            ra_deg=float(r["ra_deg"]),
            dec_deg=float(r["dec_deg"]),
            maj_axis_arcmin=float(r["maj_axis_arcmin"])
            if r["maj_axis_arcmin"] is not None
            else None,
        )
        for r in rows
    ]


async def _load_dso_metadata(conn, dso_ids: list[int]) -> dict[int, dict]:
    """Fetch UI-visible metadata for a filtered DSO set."""
    if not dso_ids:
        return {}
    placeholders = ",".join("?" for _ in dso_ids)
    cursor = await conn.execute(
        f"""
        SELECT id, primary_designation, common_name, obj_type,
               ra_deg, dec_deg, constellation,
               maj_axis_arcmin, min_axis_arcmin,
               mag_v, distance_pc
        FROM dso
        WHERE id IN ({placeholders})
        """,  # noqa: S608  # nosec B608 — placeholders built from int list
        dso_ids,
    )
    rows = await cursor.fetchall()
    return {int(r["id"]): dict(r) for r in rows}


# ── Tonight-date helper ──────────────────────────────────────────────────────


def _tonight_date(location_tz: str) -> date:
    """Local "tonight" — today's date in the location's timezone.

    If you open the planner at 2 AM on 2026-04-20, "tonight" still
    means the evening that just ended (2026-04-19 → 2026-04-20). To
    keep the UX intuitive, we roll back by 12 hours before taking the
    date, so the UI stays on "tonight" until local noon.
    """
    now_local = datetime.now(ZoneInfo(location_tz))
    anchor = now_local - timedelta(hours=12)
    return anchor.date()


# ── Core /targets endpoint ───────────────────────────────────────────────────


@router.get("/targets", response_model=PlannerTargetsResponse)
async def list_targets(
    location_id: int,
    rig_id: int | None = None,
    date_: date | None = Query(None, alias="date"),
    type_group: str | None = None,
    min_hours: float | None = None,
    max_magnitude: float | None = None,
    min_size_arcmin: float | None = None,
    frames_well: bool = False,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort: Literal[
        "hours_visible",
        "max_altitude",
        "coverage_pct",
        "mag_v",
        "primary_designation",
    ] = "hours_visible",
    sort_dir: Literal["asc", "desc"] = "desc",
) -> PlannerTargetsResponse:
    settings = await get_settings()

    async with get_db() as conn:
        location = await _load_planner_location(conn, location_id)
        location_name, has_horizon = await _load_location_name_and_horizon_flag(conn, location_id)

        rig_summary: PlannerRigSummary | None = None
        rig_fov: tuple[float, float] | None = None
        if rig_id is not None:
            rig_summary, fov_major, fov_minor = await _load_rig_fov(conn, rig_id)
            rig_fov = (fov_major, fov_minor)

        night_date = date_ if date_ is not None else _tonight_date(location.timezone)
        dsos = await _load_dso_coords(conn)

    # The visibility snapshot does ~1 second of vectorized astropy work on
    # cache miss. Off-load to a worker thread so we don't block the event
    # loop — all other requests (including thumbnail polling) stall otherwise.
    snapshot = await asyncio.to_thread(
        default_cache.get_or_compute,
        location,
        night_date,
        dsos,
        flat_min_altitude_deg=float(settings.planner_min_altitude_deg),
    )

    dark_window_out: DarkWindowOut | None = None
    if snapshot.dark_window.start_utc and snapshot.dark_window.end_utc:
        dark_window_out = DarkWindowOut(
            start_utc=snapshot.dark_window.start_utc.isoformat(),
            end_utc=snapshot.dark_window.end_utc.isoformat(),
            hours=round(snapshot.dark_window.hours, 2),
        )

    # Early return when astro-dark doesn't occur tonight.
    if not snapshot.per_dso or dark_window_out is None:
        return PlannerTargetsResponse(
            location=PlannerLocationSummary(
                id=location.id, name=location_name, has_custom_horizon=has_horizon
            ),
            rig=rig_summary,
            date=night_date.isoformat(),
            dark_window=dark_window_out,
            moon_phase_pct=snapshot.moon_phase_pct,
            total=0,
            offset=0,
            limit=limit,
            items=[],
        )

    # Filter thresholds — query params override the user's saved defaults.
    min_hours_eff = min_hours if min_hours is not None else settings.planner_min_visibility_hours
    max_mag_eff = max_magnitude if max_magnitude is not None else settings.planner_max_magnitude
    min_size_eff = (
        min_size_arcmin if min_size_arcmin is not None else settings.planner_min_size_arcmin
    )

    visible_ids = [
        vis.dso_id for vis in snapshot.per_dso.values() if vis.hours_visible >= min_hours_eff
    ]
    async with get_db() as conn:
        metadata = await _load_dso_metadata(conn, visible_ids)

    type_group_filter: set[str] | None = None
    if type_group:
        type_group_filter = {g.strip() for g in type_group.split(",") if g.strip()}

    items: list[tuple[PlannerTargetItem, DsoVisibility]] = []
    for dso_id in visible_ids:
        meta = metadata.get(dso_id)
        if meta is None:
            continue
        group = group_for_raw_type(meta["obj_type"])
        if type_group_filter is not None and group not in type_group_filter:
            continue

        mag_v = meta["mag_v"]
        if mag_v is not None and float(mag_v) > max_mag_eff:
            continue

        maj_axis = meta["maj_axis_arcmin"]
        if min_size_eff > 0 and (maj_axis is None or float(maj_axis) < min_size_eff):
            continue

        coverage = (
            compute_coverage_pct(
                rig_fov[0],
                rig_fov[1],
                maj_axis,
                meta["min_axis_arcmin"],
            )
            if rig_fov is not None
            else None
        )
        if frames_well and rig_fov is not None:
            if coverage is None:
                continue
            if not (COVERAGE_FRAMES_WELL_MIN_PCT <= coverage <= COVERAGE_FRAMES_WELL_MAX_PCT):
                continue

        vis = snapshot.per_dso[dso_id]
        item = PlannerTargetItem(
            dso_id=dso_id,
            primary_designation=meta["primary_designation"],
            common_name=meta["common_name"],
            obj_type=meta["obj_type"],
            type_group=group,
            ra_deg=meta["ra_deg"],
            dec_deg=meta["dec_deg"],
            constellation=meta["constellation"],
            maj_axis_arcmin=maj_axis,
            min_axis_arcmin=meta["min_axis_arcmin"],
            mag_v=mag_v,
            distance_pc=meta["distance_pc"],
            hours_visible=vis.hours_visible,
            max_altitude_deg=vis.max_altitude_deg,
            peak_time_utc=vis.peak_time_utc.isoformat(),
            transit_time_utc=vis.transit_time_utc.isoformat() if vis.transit_time_utc else None,
            altitude_at_transit_deg=vis.altitude_at_transit_deg,
            min_moon_separation_deg=vis.min_moon_separation_deg,
            coverage_pct=coverage,
        )
        items.append((item, vis))

    # Sort + paginate in memory.
    reverse = sort_dir == "desc"

    def _sort_key(pair: tuple[PlannerTargetItem, DsoVisibility]):
        item, _vis = pair
        if sort == "hours_visible":
            return item.hours_visible
        if sort == "max_altitude":
            return item.max_altitude_deg
        if sort == "coverage_pct":
            # Sort NULLs to the end regardless of direction.
            return item.coverage_pct if item.coverage_pct is not None else (-1 if reverse else 1e9)
        if sort == "mag_v":
            return item.mag_v if item.mag_v is not None else (1e9 if reverse else -1)
        return item.primary_designation

    items.sort(key=_sort_key, reverse=reverse)

    total = len(items)
    page = items[offset : offset + limit]

    return PlannerTargetsResponse(
        location=PlannerLocationSummary(
            id=location.id, name=location_name, has_custom_horizon=has_horizon
        ),
        rig=rig_summary,
        date=night_date.isoformat(),
        dark_window=dark_window_out,
        moon_phase_pct=snapshot.moon_phase_pct,
        total=total,
        offset=offset,
        limit=limit,
        items=[item for item, _ in page],
    )


# ── Sky-track ────────────────────────────────────────────────────────────────


@router.get("/targets/{dso_id}/sky-track", response_model=SkyTrackResponse)
async def target_sky_track(
    dso_id: int,
    location_id: int,
    date_: date | None = Query(None, alias="date"),
) -> SkyTrackResponse:
    settings = await get_settings()

    async with get_db() as conn:
        location = await _load_planner_location(conn, location_id)
        cursor = await conn.execute(
            "SELECT ra_deg, dec_deg FROM dso WHERE id = ? AND active = 1", (dso_id,)
        )
        row = await cursor.fetchone()

    if row is None or row["ra_deg"] is None or row["dec_deg"] is None:
        raise HTTPException(status_code=404, detail=f"DSO {dso_id} not found / no coords")

    night_date = date_ if date_ is not None else _tonight_date(location.timezone)
    # Per-DSO astropy work is ~100 ms — still worth keeping off the loop.
    track = await asyncio.to_thread(
        compute_sky_track,
        location,
        night_date,
        (dso_id, float(row["ra_deg"]), float(row["dec_deg"])),
        flat_min_altitude_deg=float(settings.planner_min_altitude_deg),
    )

    bands = track.twilight
    return SkyTrackResponse(
        dso_id=track.dso_id,
        times_utc=[t.isoformat() for t in track.times_utc],
        object_altitude_deg=track.object_altitude_deg,
        object_azimuth_deg=track.object_azimuth_deg,
        moon_altitude_deg=track.moon_altitude_deg,
        horizon_altitude_at_object_az=track.horizon_altitude_at_object_az,
        twilight=TwilightBandsOut(
            sunset_utc=bands.sunset_utc.isoformat() if bands.sunset_utc else None,
            civil_end_utc=bands.civil_end_utc.isoformat() if bands.civil_end_utc else None,
            nautical_end_utc=bands.nautical_end_utc.isoformat() if bands.nautical_end_utc else None,
            astro_start_utc=bands.astro_start_utc.isoformat() if bands.astro_start_utc else None,
            astro_end_utc=bands.astro_end_utc.isoformat() if bands.astro_end_utc else None,
            nautical_start_utc=bands.nautical_start_utc.isoformat()
            if bands.nautical_start_utc
            else None,
            civil_start_utc=bands.civil_start_utc.isoformat() if bands.civil_start_utc else None,
            sunrise_utc=bands.sunrise_utc.isoformat() if bands.sunrise_utc else None,
        ),
        moon_phase_pct=track.moon_phase_pct,
        peak_time_utc=track.peak_time_utc.isoformat(),
        peak_altitude_deg=track.peak_altitude_deg,
        transit_time_utc=track.transit_time_utc.isoformat() if track.transit_time_utc else None,
    )


# ── Thumbnails ───────────────────────────────────────────────────────────────


@router.get("/thumbnails/{dso_id}")
async def get_thumbnail(
    dso_id: int,
    variant: Literal["list", "detail"] = "list",
) -> Response:
    settings = await get_settings()
    max_bytes = settings.thumbnail_cache_max_mb * 1024 * 1024

    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT ra_deg, dec_deg, maj_axis_arcmin FROM dso WHERE id = ? AND active = 1",
            (dso_id,),
        )
        dso_row = await cursor.fetchone()
        if dso_row is None or dso_row["ra_deg"] is None or dso_row["dec_deg"] is None:
            raise HTTPException(status_code=404, detail=f"DSO {dso_id} not found / no coords")

        result = await thumbnails.get_thumbnail(
            conn,
            dso_id=dso_id,
            variant=variant,
            ra_deg=float(dso_row["ra_deg"]),
            dec_deg=float(dso_row["dec_deg"]),
            maj_axis_arcmin=float(dso_row["maj_axis_arcmin"])
            if dso_row["maj_axis_arcmin"] is not None
            else None,
            max_cache_bytes=max_bytes,
            conn_factory=get_db,
        )

    if result.status == "hit":
        return Response(
            content=result.body,
            media_type=result.content_type,
            headers={"Cache-Control": "public, max-age=86400"},
        )
    if result.status == "placeholder":
        return Response(
            content=result.body,
            media_type=result.content_type,
            status_code=202,
        )
    # error → 204 with no body (the error-backoff branch).
    return Response(status_code=204)


@router.post("/thumbnails/cache/clear", response_model=CacheClearResponse)
async def clear_thumbnail_cache() -> CacheClearResponse:
    async with get_db() as conn:
        deleted = await thumbnails.clear_cache(conn)
    return CacheClearResponse(deleted_files=deleted)


@router.get("/thumbnails/cache/stats", response_model=ThumbnailCacheStats)
async def thumbnail_cache_stats() -> ThumbnailCacheStats:
    settings = await get_settings()
    max_bytes = settings.thumbnail_cache_max_mb * 1024 * 1024
    async with get_db() as conn:
        stats = await thumbnails.cache_stats(conn, max_bytes=max_bytes)
    return ThumbnailCacheStats(**stats)
