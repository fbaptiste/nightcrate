"""Target Planner API (v0.16.0–v0.18.0).

Routes for the "what's up tonight" planner page:

    GET  /api/planner/targets
    GET  /api/planner/targets/{dso_id}/sky-track
    GET  /api/planner/thumbnails/{dso_id}      — DSO-keyed cache (Pass A/B)
    POST /api/planner/thumbnails/cache/clear
    GET  /api/planner/thumbnails/cache/stats
    GET  /api/planner/sky-tile-grid            — view layout (Pass C, v0.18.0)
    GET  /api/planner/sky-tile                 — cell bytes (Pass C, v0.18.0)
    POST /api/planner/sky-tile/cache/clear
    GET  /api/planner/sky-tile/cache/stats

Visibility + sky-track computations are delegated to
``services/planner_*``. Thumbnail lifecycle is in
``services/thumbnails``. The v0.18.0 DSO-agnostic sky-tile cache
lives in ``services/sky_tile_cache`` and its math in
``services/sky_tiles``.
"""

from __future__ import annotations

import asyncio
import math
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Response

from nightcrate.api.planner_models import (
    CacheClearResponse,
    DarkWindowOut,
    NearbyDsoItem,
    NearbyDsosResponse,
    PlannerLocationSummary,
    PlannerRigSummary,
    PlannerTargetItem,
    PlannerTargetsResponse,
    SkyTileCellLayout,
    SkyTileGridLayout,
    SkyTrackResponse,
    ThumbnailCacheStats,
    TwilightBandsOut,
)
from nightcrate.core.config import get_settings, update_settings
from nightcrate.db.session import get_db
from nightcrate.services import sky_tile_cache, thumbnails
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
from nightcrate.services.sky_tile_cache import make_cell_key
from nightcrate.services.sky_tiles import (
    TIERS,
    Tier,
    compute_grid_layout,
    tangent_for_ipix,
    tier_for_fov,
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
            transit_time_utc=vis.transit_time_utc.isoformat(),
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


_RIG_DEPENDENT_VARIANTS = {"rig_framed", "fov_simulator"}


@router.get("/thumbnails/{dso_id}")
async def get_thumbnail(
    dso_id: int,
    variant: Literal["list", "detail", "rig_framed", "fov_simulator"] = "list",
    fov_major_deg: float | None = None,
    fov_minor_deg: float | None = None,
    center_ra_deg: float | None = None,
    center_dec_deg: float | None = None,
    wait_ms: int = Query(0, ge=0, le=10000),
) -> Response:
    if variant in _RIG_DEPENDENT_VARIANTS:
        if fov_major_deg is None or fov_minor_deg is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"variant={variant!r} requires fov_major_deg and fov_minor_deg query parameters"
                ),
            )
        if fov_major_deg <= 0 or fov_minor_deg <= 0:
            raise HTTPException(
                status_code=400,
                detail="fov_major_deg and fov_minor_deg must be positive",
            )

    # Sky-centre override is only valid for the simulator variant — for
    # any other caller it's almost certainly a bug, so 400 rather than
    # silently ignoring.
    if (center_ra_deg is not None or center_dec_deg is not None) and variant != "fov_simulator":
        raise HTTPException(
            status_code=400,
            detail="center_ra_deg / center_dec_deg are only valid for variant=fov_simulator",
        )
    if center_ra_deg is not None and not (0.0 <= center_ra_deg < 360.0):
        raise HTTPException(status_code=400, detail="center_ra_deg must be in [0, 360)")
    if center_dec_deg is not None and not (-90.0 <= center_dec_deg <= 90.0):
        raise HTTPException(status_code=400, detail="center_dec_deg must be in [-90, 90]")

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
            fov_major_deg=fov_major_deg,
            fov_minor_deg=fov_minor_deg,
            center_ra_deg=center_ra_deg,
            center_dec_deg=center_dec_deg,
            wait_timeout_s=wait_ms / 1000.0,
        )

    if result.status == "hit":
        return Response(
            content=result.body,
            media_type=result.content_type,
            headers={"Cache-Control": "public, max-age=86400"},
        )
    if result.status == "placeholder":
        # Hard no-cache on the placeholder: the client polls by changing
        # the URL's ``__v`` cache-buster, but if a browser caches the
        # 1×1 PNG under the *base* URL, the next render serves stale
        # placeholder bytes even after the real image is in the backend
        # cache. Both the standard ``Cache-Control`` directive and the
        # legacy ``Pragma`` header are needed for older intermediaries.
        return Response(
            content=result.body,
            media_type=result.content_type,
            status_code=202,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    # error → 204 with no body (the error-backoff branch).
    return Response(
        status_code=204,
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


@router.get("/dsos/in-region", response_model=NearbyDsosResponse)
async def dsos_in_region(
    ra_center_deg: float = Query(..., ge=0.0, lt=360.0),
    dec_center_deg: float = Query(..., ge=-90.0, le=90.0),
    extent_deg: float = Query(..., gt=0.0),
    exclude_id: int | None = Query(None),
    limit: int = Query(500, ge=1, le=500),
) -> NearbyDsosResponse:
    """DSOs inside a sky region, for the FOV simulator annotation overlay.

    The region is a bounding box centred on (ra_center, dec_center) with
    side ``extent_deg``, inflated by 10% so objects whose centre sits
    just outside the frame but whose angular extent reaches inward are
    still returned.

    TODO: RA wrap-around near 0h/24h is not handled — a target whose
    region crosses RA=0 silently drops objects on the far side of the
    meridian. Acceptable for Pass B; revisit when planning targets near
    the celestial prime meridian.
    """
    half = (extent_deg / 2.0) * 1.1
    dec_min = max(-90.0, dec_center_deg - half)
    dec_max = min(90.0, dec_center_deg + half)
    # RA half-width widens at high declination so the sky-angular
    # bounding box stays roughly isotropic.
    cos_dec = max(math.cos(math.radians(dec_center_deg)), 1e-6)
    ra_half = half / cos_dec
    ra_min = ra_center_deg - ra_half
    ra_max = ra_center_deg + ra_half

    async with get_db() as conn:
        cursor = await conn.execute(
            """
            SELECT id, primary_designation, ra_deg, dec_deg,
                   maj_axis_arcmin, min_axis_arcmin, obj_type
            FROM dso
            WHERE active = 1
              AND ra_deg IS NOT NULL AND dec_deg IS NOT NULL
              AND dec_deg BETWEEN ? AND ?
              AND ra_deg  BETWEEN ? AND ?
              AND (? IS NULL OR id != ?)
            ORDER BY COALESCE(maj_axis_arcmin, 0) DESC
            LIMIT ?
            """,
            (dec_min, dec_max, ra_min, ra_max, exclude_id, exclude_id, limit),
        )
        rows = await cursor.fetchall()

    items = [
        NearbyDsoItem(
            id=int(r["id"]),
            primary_designation=str(r["primary_designation"]),
            ra_deg=float(r["ra_deg"]),
            dec_deg=float(r["dec_deg"]),
            maj_axis_arcmin=float(r["maj_axis_arcmin"])
            if r["maj_axis_arcmin"] is not None
            else None,
            min_axis_arcmin=float(r["min_axis_arcmin"])
            if r["min_axis_arcmin"] is not None
            else None,
            obj_type=str(r["obj_type"]),
            type_group=group_for_raw_type(str(r["obj_type"])),
        )
        for r in rows
    ]
    return NearbyDsosResponse(items=items)


@router.post("/thumbnails/cache/clear", response_model=CacheClearResponse)
async def clear_thumbnail_cache() -> CacheClearResponse:
    async with get_db() as conn:
        deleted = await thumbnails.clear_cache(conn)
    # Bump the cache-generation counter so clients can discriminate
    # newly-fetched images from whatever the browser HTTP-cache holds
    # under the old URLs. Every thumbnail URL carries ``&_g=N`` sourced
    # from this counter.
    settings = await get_settings()
    settings.thumbnail_cache_generation += 1
    await update_settings(settings)
    return CacheClearResponse(deleted_files=deleted)


@router.get("/thumbnails/cache/stats", response_model=ThumbnailCacheStats)
async def thumbnail_cache_stats() -> ThumbnailCacheStats:
    settings = await get_settings()
    max_bytes = settings.thumbnail_cache_max_mb * 1024 * 1024
    async with get_db() as conn:
        stats = await thumbnails.cache_stats(conn, max_bytes=max_bytes)
    return ThumbnailCacheStats(
        **stats,
        generation=settings.thumbnail_cache_generation,
    )


# ── Sky-tile cache (v0.18.0 / Pass C) ────────────────────────────────────────


# HiPS surveys the sky-tile endpoint will fetch from. Limiting to a
# known allow-list keeps the cache URL space bounded and prevents
# clients from pointing CDS at arbitrary survey paths.
_ALLOWED_HIPS_SURVEYS = frozenset({"CDS/P/DSS2/color"})


@router.get("/sky-tile-grid", response_model=SkyTileGridLayout)
def get_sky_tile_grid(
    ra_deg: float = Query(..., ge=0.0, lt=360.0),
    dec_deg: float = Query(..., ge=-90.0, le=90.0),
    tier: Literal["narrow", "med", "wide"] | None = Query(
        None, description="Explicit tier. If omitted, derived from ``fov_major_deg``."
    ),
    fov_major_deg: float | None = Query(
        None, gt=0.0, le=60.0, description="Rig major FOV; selects a tier if ``tier`` is absent."
    ),
    extent_deg: float = Query(..., gt=0.0, le=60.0),
) -> SkyTileGridLayout:
    """Compute the cell layout for a simulator or preview view.

    Pure math — no CDS calls, no disk I/O. Runs in a few milliseconds.
    The frontend uses the returned ``cells`` list (each with identity
    + top-left composite pixel position) to request cell JPEGs via
    ``/api/planner/sky-tile`` and stitch them into the viewport.

    Caller must supply either ``tier`` directly, or ``fov_major_deg``
    for the backend to derive the tier from.
    """
    if tier is None:
        if fov_major_deg is None:
            raise HTTPException(
                status_code=400,
                detail="Supply either ``tier`` or ``fov_major_deg``.",
            )
        tier_spec = tier_for_fov(fov_major_deg)
    else:
        tier_spec = TIERS[tier]

    layout = compute_grid_layout(
        center_ra_deg=ra_deg,
        center_dec_deg=dec_deg,
        tier_name=tier_spec.name,
        extent_deg=extent_deg,
    )
    return SkyTileGridLayout(
        nside=layout.nside,
        ipix=layout.ipix,
        tangent_ra_deg=layout.tangent_ra_deg,
        tangent_dec_deg=layout.tangent_dec_deg,
        tier=layout.tier,
        cell_size_deg=layout.cell_size_deg,
        cell_width_px=layout.cell_width_px,
        cell_height_px=layout.cell_height_px,
        composite_width_px=layout.composite_width_px,
        composite_height_px=layout.composite_height_px,
        view_center_pixel_x=layout.view_center_pixel_x,
        view_center_pixel_y=layout.view_center_pixel_y,
        cells=[
            SkyTileCellLayout(
                nside=c.nside,
                ipix=c.ipix,
                tier=c.tier,
                cell_i=c.cell_i,
                cell_j=c.cell_j,
                pixel_x=c.pixel_x,
                pixel_y=c.pixel_y,
            )
            for c in layout.cells
        ],
    )


@router.get("/sky-tile")
async def get_sky_tile(
    hips: str = Query("CDS/P/DSS2/color", description="HiPS survey path."),
    nside: int = Query(..., ge=1, le=4096),
    ipix: int = Query(..., ge=0),
    tier: Literal["narrow", "med", "wide"] = Query(...),
    cell_i: int = Query(..., ge=-256, le=256),
    cell_j: int = Query(..., ge=-256, le=256),
    wait_ms: int = Query(0, ge=0, le=10000),
) -> Response:
    """Serve one HEALPix-regional TAN cell from the sky-tile cache.

    Cells are keyed by sky region + tier + cell offset — no DSO. Two
    DSOs whose 5×5 simulator views overlap in the same HEALPix region
    share every cell in the overlap. On a cache miss the endpoint
    schedules a background ``hips2fits`` fetch with a custom WCS
    header (shared tangent point for every cell in the region) and,
    with ``wait_ms > 0``, holds the request open under
    ``asyncio.shield`` so the real image ships in the same round trip.

    Returns 200 with the JPEG on a hit, 202 + 1×1 PNG placeholder on
    miss (client polls), or 204 during the 1-hour failure backoff.
    """
    if hips not in _ALLOWED_HIPS_SURVEYS:
        raise HTTPException(status_code=400, detail=f"Unsupported HiPS survey: {hips!r}")
    # ipix upper bound is 12 * nside² (HEALPix definition).
    if ipix >= 12 * nside * nside:
        raise HTTPException(
            status_code=400,
            detail=f"ipix={ipix} exceeds {12 * nside * nside - 1} for nside={nside}",
        )
    tier_name: Tier = tier  # Literal narrows to Tier.
    tier_spec = TIERS[tier_name]

    # Region tangent is a deterministic function of (nside, ipix).
    # Compute once and hand to the cache service so cells within the
    # region all share it.
    region_ra, region_dec = tangent_for_ipix(ipix)

    settings = await get_settings()
    max_bytes = settings.thumbnail_cache_max_mb * 1024 * 1024

    key = make_cell_key(
        hips_survey=hips,
        healpix_nside=nside,
        healpix_ipix=ipix,
        tier=tier_spec,
        cell_i=cell_i,
        cell_j=cell_j,
    )

    async with get_db() as conn:
        result = await sky_tile_cache.get_cell(
            conn,
            key=key,
            region_ra_deg=region_ra,
            region_dec_deg=region_dec,
            max_cache_bytes=max_bytes,
            conn_factory=get_db,
            wait_timeout_s=wait_ms / 1000.0,
        )

    if result.status == "hit":
        return Response(
            content=result.body,
            media_type=result.content_type,
            headers={"Cache-Control": "public, max-age=86400"},
        )
    if result.status == "placeholder":
        # Same no-store contract as the thumbnails endpoint: the client
        # polls via a ``__v`` cache-buster, so a cached placeholder
        # would defeat the retry loop.
        return Response(
            content=result.body,
            media_type=result.content_type,
            status_code=202,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    return Response(
        status_code=204,
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


@router.post("/sky-tile/cache/clear", response_model=CacheClearResponse)
async def clear_sky_tile_cache() -> CacheClearResponse:
    async with get_db() as conn:
        deleted = await sky_tile_cache.clear_cache(conn)
    settings = await get_settings()
    settings.thumbnail_cache_generation += 1
    await update_settings(settings)
    return CacheClearResponse(deleted_files=deleted)


@router.get("/sky-tile/cache/stats", response_model=ThumbnailCacheStats)
async def sky_tile_cache_stats() -> ThumbnailCacheStats:
    settings = await get_settings()
    max_bytes = settings.thumbnail_cache_max_mb * 1024 * 1024
    async with get_db() as conn:
        stats = await sky_tile_cache.cache_stats(conn, max_bytes=max_bytes)
    return ThumbnailCacheStats(
        **stats,
        generation=settings.thumbnail_cache_generation,
    )
