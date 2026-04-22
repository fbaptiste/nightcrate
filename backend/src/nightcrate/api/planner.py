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
import os
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Response

from nightcrate.api.dso import normalize_search_key
from nightcrate.api.planner_models import (
    AnnualHoursPoint as AnnualHoursPointOut,
)
from nightcrate.api.planner_models import (
    AnnualHoursResponse,
    CacheClearResponse,
    DarkWindowOut,
    NearbyDsoItem,
    NearbyDsosResponse,
    PlannerHorizonSummary,
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
from nightcrate.services.planner_annual_hours import compute_annual_hours
from nightcrate.services.planner_now_status import compute_now_status
from nightcrate.services.planner_sky_track import compute_sky_track
from nightcrate.services.planner_visibility import (
    DsoCoord,
    DsoVisibility,
    PlannerHorizon,
    PlannerLocation,
    default_cache,
)
from nightcrate.services.rig_calculators import (
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


# ── Sort fields catalog ─────────────────────────────────────────────────────
#
# Canonical list of fields the multi-sort accepts. Frontend's
# ``lib/plannerSortFields.ts`` mirrors this registry; keep the two in
# lockstep when adding a field. ``kind`` drives the sort behaviour:
# "string" sorts case-insensitively, "number" compares numerically,
# "now_status" uses a custom ordinal (up < rising < set).
PLANNER_SORT_FIELDS: dict[str, str] = {
    "primary_designation": "string",
    "common_name": "string",
    "constellation": "string",
    "obj_type": "string",
    "mag_v": "number",
    "maj_axis_arcmin": "number",
    "distance_pc": "number",
    "hours_visible": "number",
    "max_altitude_deg": "number",
    "altitude_at_transit_deg": "number",
    "transit_time_utc": "string",  # ISO strings sort chronologically
    "min_moon_separation_deg": "number",
    "coverage_pct": "number",
    "now_status": "now_status",
}

_NOW_STATUS_ORDER = {"up": 0, "rising": 1, "set": 2}


def _parse_sort(sort: str | None) -> list[tuple[str, str]]:
    """Parse ``field:dir,field:dir,...`` into a list of pairs.

    Returns an empty list when ``sort`` is ``None`` / empty. Raises
    ``HTTPException(422)`` on unknown field or invalid direction so
    callers get an actionable error instead of a silent no-op.
    """
    if not sort or not sort.strip():
        return []
    out: list[tuple[str, str]] = []
    for entry in sort.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if ":" not in entry:
            raise HTTPException(
                status_code=422,
                detail=f"Sort entry '{entry}' missing ':asc' or ':desc' direction.",
            )
        field, _, direction = entry.partition(":")
        field = field.strip()
        direction = direction.strip().lower()
        if field not in PLANNER_SORT_FIELDS:
            raise HTTPException(status_code=422, detail=f"Unknown sort field: '{field}'")
        if direction not in ("asc", "desc"):
            raise HTTPException(
                status_code=422,
                detail=f"Sort direction must be 'asc' or 'desc', got '{direction}' for '{field}'.",
            )
        out.append((field, direction))
    return out


def _sort_value(item: PlannerTargetItem, field: str):
    """Pull a raw sortable value off a ``PlannerTargetItem``. ``None``
    values pass through — null handling lives in the comparator so
    direction never inverts "null sorts last". Empty or whitespace-
    only strings are coerced to ``None`` so OpenNGC rows that have
    ``common_name = ''`` (rather than NULL) still land in the
    null-last bucket instead of sorting alphabetically first / last."""
    value = getattr(item, field, None)
    kind = PLANNER_SORT_FIELDS[field]
    if value is None:
        return None
    if kind == "now_status":
        return _NOW_STATUS_ORDER.get(value, 99)
    if kind == "string":
        stripped = value.strip()
        if not stripped:
            return None
        return stripped.lower()
    return value


def _sort_items(
    items: list[tuple[PlannerTargetItem, DsoVisibility | None]],
    sort_entries: list[tuple[str, str]],
) -> None:
    """Stable multi-key sort in place. Applies the keys right-to-left
    so the first entry is the primary key (Python's Timsort is stable,
    so later passes preserve earlier tie-breaks). Nulls always sort
    last, regardless of the key's direction."""
    from functools import cmp_to_key

    def make_cmp(field: str, direction: str):
        asc = direction == "asc"

        def cmp(
            a: tuple[PlannerTargetItem, DsoVisibility | None],
            b: tuple[PlannerTargetItem, DsoVisibility | None],
        ) -> int:
            va = _sort_value(a[0], field)
            vb = _sort_value(b[0], field)
            if va is None and vb is None:
                return 0
            if va is None:
                return 1  # nulls always last
            if vb is None:
                return -1
            if va < vb:
                return -1 if asc else 1
            if va > vb:
                return 1 if asc else -1
            return 0

        return cmp_to_key(cmp)

    for field, direction in reversed(sort_entries):
        items.sort(key=make_cmp(field, direction))


# ── DB helpers ───────────────────────────────────────────────────────────────


async def _load_planner_location(conn, location_id: int) -> PlannerLocation:
    """Fetch a location and bundle into a ``PlannerLocation``.

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

    return PlannerLocation(
        id=int(row["id"]),
        latitude_deg=float(row["latitude"]),
        longitude_deg=float(row["longitude"]),
        elevation_m=float(row["elevation_m"]) if row["elevation_m"] is not None else None,
        timezone=row["timezone"],
        updated_at=row["updated_at"],
    )


async def _load_planner_horizon(conn, location_id: int, horizon_id: int | None) -> PlannerHorizon:
    """Resolve a horizon for planner compute.

    ``horizon_id=None`` → location's default. When ``horizon_id`` is
    supplied but doesn't belong to ``location_id`` or has been deleted,
    returns 404. Points are loaded eagerly for custom horizons so the
    returned value object is self-contained (safe to pass across
    process-pool boundaries).
    """
    if horizon_id is not None:
        cursor = await conn.execute(
            "SELECT * FROM location_horizon WHERE id = ? AND location_id = ?",
            (horizon_id, location_id),
        )
    else:
        cursor = await conn.execute(
            "SELECT * FROM location_horizon WHERE location_id = ? AND is_default = 1",
            (location_id,),
        )
    row = await cursor.fetchone()
    if row is None:
        # Fallback: no row with is_default=1 shouldn't happen (the
        # migration seeds one; create-location also does) but guard
        # anyway so a corrupted DB surfaces a 500-ish 422 rather than
        # a mysterious crash inside the compute.
        raise HTTPException(
            status_code=404,
            detail=(
                f"Horizon not found for location {location_id}"
                if horizon_id is not None
                else f"Location {location_id} has no default horizon."
            ),
        )

    points: tuple[tuple[float, float], ...] = ()
    if row["type"] == "custom":
        cursor = await conn.execute(
            """
            SELECT azimuth_deg, altitude_deg
            FROM location_horizon_point
            WHERE horizon_id = ?
            ORDER BY azimuth_deg ASC
            """,
            (row["id"],),
        )
        point_rows = await cursor.fetchall()
        points = tuple((float(r["azimuth_deg"]), float(r["altitude_deg"])) for r in point_rows)

    return PlannerHorizon(
        id=int(row["id"]),
        location_id=int(row["location_id"]),
        name=str(row["name"]),
        type=str(row["type"]),
        flat_altitude_deg=float(row["flat_altitude_deg"])
        if row["flat_altitude_deg"] is not None
        else None,
        points=points,
        updated_at=str(row["updated_at"]),
    )


async def _load_location_name(conn, location_id: int) -> str:
    cursor = await conn.execute("SELECT name FROM location WHERE id = ?", (location_id,))
    row = await cursor.fetchone()
    return row["name"] if row else ""


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
    location_id: int | None = None,
    horizon_id: int | None = Query(
        None,
        description=(
            "Horizon to evaluate visibility against. Defaults to the "
            "location's ``is_default=1`` horizon. Ignored in Anytime "
            "mode (``restrict_tonight=false``)."
        ),
    ),
    rig_id: int | None = None,
    date_: date | None = Query(None, alias="date"),
    type: str | None = Query(
        None,
        description=(
            "Comma-separated raw obj_type codes (e.g., 'G,HII,PN'). "
            "OR semantics — a DSO matches if its obj_type is any of the listed codes."
        ),
    ),
    constellation: str | None = Query(
        None,
        description=(
            "Comma-separated 3-letter IAU constellation codes (e.g., 'Ori,And'). "
            "OR semantics — a DSO matches if its constellation is any of the listed codes."
        ),
    ),
    catalog: str | None = Query(
        None,
        description=(
            "Comma-separated designation catalog codes (e.g., 'messier,ngc,barnard'). "
            "OR semantics — a DSO matches if it carries any of the listed catalogs."
        ),
    ),
    has_distance: bool | None = Query(
        None, description="If set, filter to DSOs with (true) or without (false) a distance value"
    ),
    min_hours: float | None = None,
    max_magnitude: float | None = None,
    min_size_arcmin: float | None = None,
    coverage_min_pct: float | None = Query(
        None,
        ge=0.0,
        le=200.0,
        description=(
            "Minimum FOV coverage percentage (inclusive). Requires a "
            "rig to be selected. Paired with ``coverage_max_pct`` to "
            "drive the Frames-Well range filter."
        ),
    ),
    coverage_max_pct: float | None = Query(
        None,
        ge=0.0,
        le=200.0,
        description=("Maximum FOV coverage percentage (inclusive). Requires a rig to be selected."),
    ),
    q: str | None = Query(
        None,
        description=(
            "Free-text search over designations + common names — same semantics "
            "as the DSO catalog's ``q``. Matches a designation ``search_key`` "
            "by prefix or a case-insensitive substring of ``common_name``."
        ),
    ),
    restrict_tonight: bool = Query(
        True,
        description=(
            "When ``True`` (default) the response is limited to DSOs visible "
            "during tonight's astronomical-dark window from the selected "
            "location. When ``False`` the planner acts like a catalog "
            "browser: all active DSOs come back, no visibility computation "
            "runs, and the visibility fields on each item are ``None``."
        ),
    ),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort: str | None = Query(
        None,
        description=(
            "Comma-separated list of ``field:direction`` pairs (direction "
            "is ``asc`` or ``desc``) evaluated in order. Example: "
            "``hours_visible:desc,mag_v:asc``. Unknown fields return 422. "
            "If omitted, Tonight mode defaults to ``hours_visible:desc``; "
            "Anytime defaults to ``primary_designation:asc``. Available "
            "fields: see ``PLANNER_SORT_FIELDS`` in the planner API."
        ),
    ),
) -> PlannerTargetsResponse:
    # Tonight mode is location-dependent; Anytime is pure catalog
    # browse and works without one (first-run users with no locations
    # still get a usable Anytime page).
    if restrict_tonight and location_id is None:
        raise HTTPException(
            status_code=400,
            detail="location_id is required when restrict_tonight=true",
        )

    settings = await get_settings()

    location: PlannerLocation | None = None
    horizon: PlannerHorizon | None = None
    location_summary: PlannerLocationSummary | None = None
    horizon_summary: PlannerHorizonSummary | None = None
    async with get_db() as conn:
        if location_id is not None:
            location = await _load_planner_location(conn, location_id)
            location_name = await _load_location_name(conn, location_id)
            location_summary = PlannerLocationSummary(id=location.id, name=location_name)
            if restrict_tonight:
                horizon = await _load_planner_horizon(conn, location_id, horizon_id)
                horizon_summary = PlannerHorizonSummary(
                    id=horizon.id,
                    name=horizon.name,
                    type=horizon.type,
                    flat_altitude_deg=horizon.flat_altitude_deg,
                )

        rig_summary: PlannerRigSummary | None = None
        rig_fov: tuple[float, float] | None = None
        if rig_id is not None:
            rig_summary, fov_major, fov_minor = await _load_rig_fov(conn, rig_id)
            rig_fov = (fov_major, fov_minor)

        # Anytime mode has no location, so fall back to UTC for the
        # night-date anchor (only used for the response's ``date``
        # field — no visibility computation consumes it).
        tz_for_date = location.timezone if location is not None else "UTC"
        night_date = date_ if date_ is not None else _tonight_date(tz_for_date)
        dsos = await _load_dso_coords(conn)

    # "Anytime" mode skips the visibility snapshot entirely — the
    # handler acts as a paginated catalog browser with the same
    # metadata + search filters the "tonight only" path uses.
    snapshot = (
        await asyncio.to_thread(
            default_cache.get_or_compute,
            location,
            horizon,
            night_date,
            dsos,
        )
        if restrict_tonight and location is not None and horizon is not None
        else None
    )

    dark_window_out: DarkWindowOut | None = None
    moon_phase_pct_out = 0.0
    moon_phase_name_out: str | None = None
    if snapshot is not None:
        moon_phase_pct_out = snapshot.moon_phase_pct
        if snapshot.dark_window.start_utc and snapshot.dark_window.end_utc:
            dark_window_out = DarkWindowOut(
                start_utc=snapshot.dark_window.start_utc.isoformat(),
                end_utc=snapshot.dark_window.end_utc.isoformat(),
                hours=round(snapshot.dark_window.hours, 2),
            )
        # Compute the phase name at the same reference instant the
        # snapshot uses for phase percent — astro-dark midpoint, which
        # is close enough to local midnight for naming purposes.
        if location is not None:
            from astropy.time import Time as _AstroTime

            from nightcrate.services.astronomy import compute_moon_phase_name
            from nightcrate.services.planner_visibility import _make_earth_location

            ref_utc = snapshot.dark_window.start_utc or datetime.now(UTC)
            moon_phase_name_out = compute_moon_phase_name(
                _AstroTime(ref_utc), _make_earth_location(location)
            )

        # Early return when astro-dark doesn't occur tonight (only
        # meaningful in "tonight only" mode — the "anytime" path
        # never reaches here).
        if not snapshot.per_dso or dark_window_out is None:
            return PlannerTargetsResponse(
                location=location_summary,
                horizon=horizon_summary,
                rig=rig_summary,
                date=night_date.isoformat(),
                dark_window=dark_window_out,
                moon_phase_pct=moon_phase_pct_out,
                moon_phase_name=moon_phase_name_out,
                total=0,
                offset=0,
                limit=limit,
                items=[],
                raw_type_counts={},
                catalog_counts={},
                constellation_counts={},
            )

    # Filter thresholds — query params override the user's saved
    # defaults in Tonight mode. In Anytime mode we intentionally do
    # NOT fall back to the imaging-focused saved defaults: the user
    # is browsing the full catalog and expects parity with the DSO
    # catalog page. A missing param in Anytime means "don't filter",
    # not "apply planner_min_size_arcmin=5 quietly".
    if restrict_tonight:
        min_hours_eff = (
            min_hours if min_hours is not None else settings.planner_min_visibility_hours
        )
        max_mag_eff = max_magnitude if max_magnitude is not None else settings.planner_max_magnitude
        min_size_eff = (
            min_size_arcmin if min_size_arcmin is not None else settings.planner_min_size_arcmin
        )
    else:
        min_hours_eff = min_hours if min_hours is not None else 0.0
        max_mag_eff = max_magnitude if max_magnitude is not None else float("inf")
        min_size_eff = min_size_arcmin if min_size_arcmin is not None else 0.0

    if snapshot is not None:
        visible_ids = [
            vis.dso_id for vis in snapshot.per_dso.values() if vis.hours_visible >= min_hours_eff
        ]
    else:
        # Anytime mode — every active DSO with coordinates is a candidate.
        visible_ids = [d.dso_id for d in dsos]
    async with get_db() as conn:
        metadata = await _load_dso_metadata(conn, visible_ids)

        # Optional free-text search — same matching rules as the DSO
        # catalog so a user's mental model carries across pages.
        search_match_ids: set[int] | None = None
        if q and q.strip():
            search_key = normalize_search_key(q)
            cursor = await conn.execute(
                """
                SELECT DISTINCT d.id
                FROM dso d
                WHERE d.active = 1
                  AND (
                      d.id IN (
                          SELECT dso_id FROM dso_designation
                          WHERE search_key LIKE ?
                      )
                      OR LOWER(d.common_name) LIKE ?
                  )
                """,
                (search_key + "%", f"%{q.lower()}%"),
            )
            search_match_ids = {int(r["id"]) for r in await cursor.fetchall()}

    # Per-DSO "currently up / rising / set" status — Tonight mode only,
    # and only when a location is present (location-less Anytime mode
    # has no horizon to test against).
    now_status_by_dso: dict[int, str] = {}
    if restrict_tonight and location is not None and horizon is not None and snapshot is not None:
        visible_coords = [d for d in dsos if d.dso_id in set(visible_ids)]
        now_status_by_dso = await asyncio.to_thread(
            compute_now_status,
            location,
            horizon,
            visible_coords,
            astro_dark_start_utc=snapshot.dark_window.start_utc,
            astro_dark_end_utc=snapshot.dark_window.end_utc,
        )

    raw_type_filter: set[str] | None = None
    if type:
        raw_type_filter = {t.strip() for t in type.split(",") if t.strip()}
    constellation_filter: set[str] | None = None
    if constellation:
        constellation_filter = {c.strip() for c in constellation.split(",") if c.strip()}
    catalog_filter: set[str] | None = None
    if catalog:
        catalog_filter = {c.strip() for c in catalog.split(",") if c.strip()}

    # Catalog filter + per-DSO catalog tallies need a DSO→{catalogs}
    # lookup. Single query, all visible ids at once.
    dso_catalogs: dict[int, set[str]] = {dso_id: set() for dso_id in visible_ids}
    if visible_ids:
        async with get_db() as conn:
            placeholders = ",".join("?" * len(visible_ids))
            cursor = await conn.execute(
                f"SELECT dso_id, catalog FROM dso_designation WHERE dso_id IN ({placeholders})",  # noqa: S608, E501  # nosec B608
                visible_ids,
            )
            for r in await cursor.fetchall():
                dso_catalogs[int(r["dso_id"])].add(r["catalog"])

    items: list[tuple[PlannerTargetItem, DsoVisibility | None]] = []
    # Faceted-search counts: per-chip-value tallies of DSOs that pass
    # every filter EXCEPT the one the chip belongs to. Lets the
    # frontend render "Galaxy (234)" labels that reflect the user's
    # current constellation / mag / visibility constraints.
    raw_type_counts: dict[str, int] = {}
    catalog_counts: dict[str, int] = {}
    constellation_counts: dict[str, int] = {}
    for dso_id in visible_ids:
        meta = metadata.get(dso_id)
        if meta is None:
            continue
        if search_match_ids is not None and dso_id not in search_match_ids:
            continue
        raw = meta["obj_type"]
        row_constellation = meta["constellation"]
        row_catalogs = dso_catalogs.get(dso_id, set())

        # Always-applied filters — not facet dimensions themselves.
        if has_distance is True and meta["distance_pc"] is None:
            continue
        if has_distance is False and meta["distance_pc"] is not None:
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
        # Frames-Well range filter — applied when the user has dialled
        # in a narrower band than the full 0–200 % range. A rig is
        # required to compute coverage; without a rig, the range
        # filter silently no-ops. ``None`` coverage (DSO has no size)
        # always fails the range filter when either bound is active.
        range_active = (coverage_min_pct is not None and coverage_min_pct > 0.0) or (
            coverage_max_pct is not None and coverage_max_pct < 200.0
        )
        if range_active and rig_fov is not None:
            if coverage is None:
                continue
            if coverage_min_pct is not None and coverage < coverage_min_pct:
                continue
            if coverage_max_pct is not None and coverage > coverage_max_pct:
                continue

        # At this point the DSO passes every non-facet-dimension filter.
        # Each facet count is incremented only when the DSO passes the
        # OTHER two facet dimensions — classic faceted-search semantics.
        passes_raw = raw_type_filter is None or raw in raw_type_filter
        passes_const = constellation_filter is None or (
            row_constellation is not None and row_constellation in constellation_filter
        )
        passes_catalog = catalog_filter is None or bool(row_catalogs & catalog_filter)

        if passes_const and passes_catalog:
            raw_type_counts[raw] = raw_type_counts.get(raw, 0) + 1
        if passes_raw and passes_catalog and row_constellation is not None:
            constellation_counts[row_constellation] = (
                constellation_counts.get(row_constellation, 0) + 1
            )
        if passes_raw and passes_const:
            # Each of the DSO's catalogs contributes one to its own tally.
            for c in row_catalogs:
                catalog_counts[c] = catalog_counts.get(c, 0) + 1

        # Now apply the three facet-dimension filters for the items list.
        if not (passes_raw and passes_const and passes_catalog):
            continue

        vis = snapshot.per_dso.get(dso_id) if snapshot is not None else None
        item = PlannerTargetItem(
            dso_id=dso_id,
            primary_designation=meta["primary_designation"],
            common_name=meta["common_name"],
            obj_type=meta["obj_type"],
            ra_deg=meta["ra_deg"],
            dec_deg=meta["dec_deg"],
            constellation=row_constellation,
            maj_axis_arcmin=maj_axis,
            min_axis_arcmin=meta["min_axis_arcmin"],
            mag_v=mag_v,
            distance_pc=meta["distance_pc"],
            hours_visible=vis.hours_visible if vis is not None else None,
            max_altitude_deg=vis.max_altitude_deg if vis is not None else None,
            peak_time_utc=vis.peak_time_utc.isoformat() if vis is not None else None,
            transit_time_utc=vis.transit_time_utc.isoformat() if vis is not None else None,
            altitude_at_transit_deg=(vis.altitude_at_transit_deg if vis is not None else None),
            min_moon_separation_deg=(vis.min_moon_separation_deg if vis is not None else None),
            coverage_pct=coverage,
            now_status=now_status_by_dso.get(dso_id),
        )
        items.append((item, vis))

    # Multi-sort in memory with mode-appropriate fallback. Null values
    # always sort to the end regardless of per-key direction; that's
    # enforced inside ``_sort_items``'s comparator.
    sort_entries = _parse_sort(sort)
    if not sort_entries:
        sort_entries = (
            [("hours_visible", "desc")] if restrict_tonight else [("primary_designation", "asc")]
        )
    _sort_items(items, sort_entries)

    total = len(items)
    page = items[offset : offset + limit]

    return PlannerTargetsResponse(
        location=location_summary,
        horizon=horizon_summary,
        rig=rig_summary,
        date=night_date.isoformat(),
        dark_window=dark_window_out,
        moon_phase_pct=moon_phase_pct_out,
        moon_phase_name=moon_phase_name_out,
        total=total,
        offset=offset,
        limit=limit,
        items=[item for item, _ in page],
        raw_type_counts=raw_type_counts,
        catalog_counts=catalog_counts,
        constellation_counts=constellation_counts,
    )


# ── Sky-track ────────────────────────────────────────────────────────────────


@router.get("/targets/{dso_id}/sky-track", response_model=SkyTrackResponse)
async def target_sky_track(
    dso_id: int,
    location_id: int,
    horizon_id: int | None = Query(
        None,
        description=(
            "Horizon to draw the reference line against. Defaults to the "
            "location's default horizon."
        ),
    ),
    date_: date | None = Query(None, alias="date"),
) -> SkyTrackResponse:
    async with get_db() as conn:
        location = await _load_planner_location(conn, location_id)
        horizon = await _load_planner_horizon(conn, location_id, horizon_id)
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
        horizon,
        night_date,
        (dso_id, float(row["ra_deg"]), float(row["dec_deg"])),
    )

    bands = track.twilight
    return SkyTrackResponse(
        dso_id=track.dso_id,
        times_utc=[t.isoformat() for t in track.times_utc],
        object_altitude_deg=track.object_altitude_deg,
        object_azimuth_deg=track.object_azimuth_deg,
        moon_altitude_deg=track.moon_altitude_deg,
        moon_separation_deg=track.moon_separation_deg,
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


# ── Annual hours above threshold (best-time-of-year chart) ───────────────────


@router.get(
    "/targets/{dso_id}/annual-hours",
    response_model=AnnualHoursResponse,
)
async def target_annual_hours(
    dso_id: int,
    location_id: int,
    horizon_id: int | None = Query(
        None,
        description=(
            "Horizon to count hours against. Defaults to the location's "
            "default horizon. Artificial horizons use their flat altitude "
            "value; custom horizons use the stored polyline."
        ),
    ),
    year: int | None = Query(
        None,
        description=(
            "Calendar year to plot. Defaults to the current year in the "
            "location's geographic timezone."
        ),
    ),
    moon_sep_deg: float = Query(
        60.0,
        ge=0.0,
        le=180.0,
        description=(
            "Minimum moon–target separation (deg). A sample counts only "
            "when the moon is below horizon OR separation > this value. "
            "``0`` disables the moon check entirely (old ``narrowband`` "
            "behaviour) and skips the moon astropy transform."
        ),
    ),
) -> AnnualHoursResponse:
    async with get_db() as conn:
        location = await _load_planner_location(conn, location_id)
        horizon = await _load_planner_horizon(conn, location_id, horizon_id)
        cursor = await conn.execute(
            "SELECT ra_deg, dec_deg FROM dso WHERE id = ? AND active = 1", (dso_id,)
        )
        row = await cursor.fetchone()

    if row is None or row["ra_deg"] is None or row["dec_deg"] is None:
        raise HTTPException(status_code=404, detail=f"DSO {dso_id} not found / no coords")

    if year is None:
        # Use the current year in the location's timezone — otherwise
        # users abroad can see the "wrong" year during the UTC wrap.
        year = datetime.now(ZoneInfo(location.timezone)).year

    # Fan the year out across worker processes. ``max_worker_cores``
    # is user-configurable (``None`` → ``cpu_count - 1``). Cap at the
    # number of calendar months so chunk granularity stays sane even
    # on many-core machines where astropy imports would otherwise
    # dominate the per-chunk cost.
    settings = await get_settings()
    configured_workers = settings.max_worker_cores
    if configured_workers is None:
        configured_workers = max(1, (os.cpu_count() or 2) - 1)
    max_workers = max(1, min(int(configured_workers), 12))

    track = await asyncio.to_thread(
        compute_annual_hours,
        location,
        horizon,
        year,
        (dso_id, float(row["ra_deg"]), float(row["dec_deg"])),
        moon_sep_deg=moon_sep_deg,
        max_workers=max_workers,
    )

    return AnnualHoursResponse(
        dso_id=track.dso_id,
        year=track.year,
        horizon_id=track.horizon_id,
        horizon_type=track.horizon_type,
        horizon_name=track.horizon_name,
        flat_altitude_deg=track.flat_altitude_deg,
        moon_sep_deg=track.moon_sep_deg,
        points=[AnnualHoursPointOut(date=p.date.isoformat(), hours=p.hours) for p in track.points],
    )


# ── Thumbnails ───────────────────────────────────────────────────────────────


@router.get("/thumbnails/{dso_id}")
async def get_thumbnail(
    dso_id: int,
    variant: Literal["list", "detail", "rig_framed"] = "list",
    fov_major_deg: float | None = None,
    fov_minor_deg: float | None = None,
    wait_ms: int = Query(0, ge=0, le=10000),
) -> Response:
    if variant == "rig_framed":
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
