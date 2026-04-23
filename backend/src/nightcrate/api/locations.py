"""Location management API — CRUD for imaging locations."""

import html
import logging
import re
from zoneinfo import available_timezones

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, field_validator, model_validator
from timezonefinder import TimezoneFinder

from nightcrate.api._common import bool_fields, integrity_guard, row_to_dict
from nightcrate.api.horizon_models import HorizonCreate
from nightcrate.db.session import get_db
from nightcrate.services.coordinate_format import format_latitude, format_longitude
from nightcrate.services.http_client import get as http_get

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/locations", tags=["Locations"])

# Cached TimezoneFinder instance (~200ms to initialize, immutable after)
_TZ_FINDER: TimezoneFinder | None = None


def _get_tz_finder() -> TimezoneFinder:
    global _TZ_FINDER
    if _TZ_FINDER is None:
        _TZ_FINDER = TimezoneFinder()
    return _TZ_FINDER


def _lookup_geo_timezone(latitude: float, longitude: float) -> str | None:
    """Look up the IANA timezone for a lat/lon coordinate pair."""
    try:
        return _get_tz_finder().timezone_at(lat=latitude, lng=longitude)
    except Exception:
        logger.debug("geo_timezone lookup failed for %s, %s", latitude, longitude)
        return None


# Legacy/obscure timezone prefixes — filter these out for a clean dropdown
_LEGACY_PREFIXES = (
    "Etc/",
    "US/",
    "Canada/",
    "Brazil/",
    "Chile/",
    "Mexico/",
    "SystemV/",
    "posix/",
    "right/",
)
_TIMEZONES: list[str] | None = None


def _get_timezones() -> list[str]:
    global _TIMEZONES
    if _TIMEZONES is None:
        _TIMEZONES = sorted(
            tz for tz in available_timezones() if "/" in tz and not tz.startswith(_LEGACY_PREFIXES)
        )
    return _TIMEZONES


# ── Models ────────────────────────────────────────────────────────────────────


class _LocationBase(BaseModel):
    """Shared fields + validators for LocationCreate and LocationUpdate.

    All fields are optional here; the subclasses narrow the required set
    (Create needs name/lat/lon/timezone; Update keeps everything optional).
    Validators live here once instead of being copy-pasted into both models.
    """

    name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    elevation_m: float | None = None
    timezone: str | None = None
    # Geographic/location timezone. Normally auto-derived from coordinates
    # server-side; callers can override — if provided, the server uses the
    # supplied value verbatim.
    geo_timezone: str | None = None
    bortle_class: int | None = None
    sqm_reading: float | None = None
    city: str | None = None
    state_province: str | None = None
    country: str | None = None
    postal_code: str | None = None
    is_default: bool | None = None
    notes: str | None = None
    typical_seeing_low_arcsec: float | None = None
    typical_seeing_high_arcsec: float | None = None

    @field_validator("latitude")
    @classmethod
    def check_lat(cls, v: float | None) -> float | None:
        if v is not None and not -90 <= v <= 90:
            raise ValueError("Latitude must be between -90 and 90")
        return v

    @field_validator("longitude")
    @classmethod
    def check_lon(cls, v: float | None) -> float | None:
        if v is not None and not -180 <= v <= 180:
            raise ValueError("Longitude must be between -180 and 180")
        return v

    @field_validator("bortle_class")
    @classmethod
    def check_bortle(cls, v: int | None) -> int | None:
        if v is not None and not 1 <= v <= 9:
            raise ValueError("Bortle class must be between 1 and 9")
        return v

    @field_validator("sqm_reading")
    @classmethod
    def check_sqm(cls, v: float | None) -> float | None:
        if v is not None and not 10 <= v <= 25:
            raise ValueError("SQM reading must be between 10 and 25")
        return v

    @model_validator(mode="after")
    def check_seeing_range(self) -> _LocationBase:
        low = self.typical_seeing_low_arcsec
        high = self.typical_seeing_high_arcsec
        if low is not None and low <= 0:
            raise ValueError("typical_seeing_low_arcsec must be positive")
        if high is not None and high <= 0:
            raise ValueError("typical_seeing_high_arcsec must be positive")
        if low is not None and high is not None and low > high:
            raise ValueError("typical_seeing_low_arcsec must be \u2264 typical_seeing_high_arcsec")
        return self


class LocationCreate(_LocationBase):
    """Required: name, latitude, longitude, timezone. Everything else optional.

    ``horizons`` is optional — when provided (non-empty), the server
    creates the location + all these horizons in a single transaction
    AND skips the usual ``0° flat`` default auto-seed. Exactly one
    entry must carry ``is_default=true`` and at most one may be
    ``type='custom'`` (same product invariants as the per-horizon
    endpoints). When ``horizons`` is absent or ``None`` the legacy
    auto-seed behavior applies. An empty list is rejected (422) so the
    "every location has ≥1 horizon" invariant is never violated.
    """

    name: str
    latitude: float
    longitude: float
    timezone: str
    is_default: bool = False
    horizons: list[HorizonCreate] | None = None

    @model_validator(mode="after")
    def _validate_horizons(self) -> LocationCreate:
        if self.horizons is None:
            return self
        if not self.horizons:
            raise ValueError(
                "horizons: provide at least one horizon or omit the field to auto-seed a 0° default"
            )
        default_count = sum(1 for h in self.horizons if h.is_default)
        if default_count != 1:
            raise ValueError(
                f"horizons: exactly one entry must have is_default=true (got {default_count})"
            )
        custom_count = sum(1 for h in self.horizons if h.type == "custom")
        if custom_count > 1:
            raise ValueError("horizons: at most one 'custom' horizon per location")
        names = [h.name for h in self.horizons]
        if len(names) != len(set(names)):
            raise ValueError("horizons: names must be unique within the list")
        return self


class LocationUpdate(_LocationBase):
    """All fields optional — standard PATCH-style partial update."""


class LocationResponse(BaseModel):
    id: int
    name: str
    latitude: float
    longitude: float
    # Sexagesimal display strings derived from latitude/longitude,
    # formatted like "33deg27'54'' N" / "112deg04'26'' W".
    latitude_display: str
    longitude_display: str
    elevation_m: float | None
    timezone: str
    geo_timezone: str | None
    bortle_class: int | None
    sqm_reading: float | None
    city: str | None
    state_province: str | None
    country: str | None
    postal_code: str | None
    typical_seeing_low_arcsec: float | None
    typical_seeing_high_arcsec: float | None
    is_default: bool
    active: bool = True
    notes: str | None
    created_at: str
    updated_at: str


# ── Helpers ───────────────────────────────────────────────────────────────────


def _add_sexagesimal_display(d: dict) -> None:
    if d.get("latitude") is not None:
        d["latitude_display"] = format_latitude(d["latitude"])
    if d.get("longitude") is not None:
        d["longitude_display"] = format_longitude(d["longitude"])


def _row_to_dict(row) -> dict:
    return row_to_dict(row, extra_fn=_add_sexagesimal_display)


_bool_fields = bool_fields


async def _ensure_single_default(conn, new_default_id: int) -> None:
    """Clear is_default on all rows except the given ID."""
    await conn.execute(
        "UPDATE location SET is_default = 0 WHERE id != ?",
        (new_default_id,),
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/timezones", response_model=list[str])
async def list_timezones():
    """List all supported IANA timezones (Region/City format)."""
    return _get_timezones()


@router.get("/geo-timezone")
async def get_geo_timezone(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
):
    """Look up the geographic timezone for a coordinate pair."""
    geo_tz = _lookup_geo_timezone(latitude, longitude)
    return {"geo_timezone": geo_tz}


# ── Clear Outside scraper ────────────────────────────────────────────────────
#
# The public forecast page embeds the estimated sky quality in a single
# text fragment of the form:
#   "Est. Sky Quality: 21.69 Magnitude. Class 2 Bortle. ... mcd/m2 Brightness."
# We fetch that page, strip tags, and extract the two numbers by regex.
# If Clear Outside changes the layout the regex will simply miss and the
# endpoint returns nulls — caller decides what to do.
_CLEAR_OUTSIDE_URL = "https://clearoutside.com/forecast/{lat:.2f}/{lon:.2f}"
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_SQM_RE = re.compile(r"Sky Quality:\s*([\d.]+)\s*Magnitude", re.IGNORECASE)
_BORTLE_RE = re.compile(r"Class\s+(\d+)\s+Bortle", re.IGNORECASE)


@router.get("/clear-outside")
async def lookup_clear_outside(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
):
    """Scrape the Clear Outside forecast page for estimated Bortle class and SQM."""
    url = _CLEAR_OUTSIDE_URL.format(lat=latitude, lon=longitude)
    try:
        response = await http_get(
            url,
            headers={"User-Agent": "NightCrate/1.0"},
            label=f"clear_outside[{latitude:.2f},{longitude:.2f}]",
            follow_redirects=True,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Clear Outside lookup failed for %s,%s: %s", latitude, longitude, exc)
        raise HTTPException(status_code=502, detail="Could not reach Clear Outside") from exc

    # Strip tags, decode HTML entities (page uses `&nbsp;` between labels
    # and values), then collapse whitespace. `html.unescape` turns `&nbsp;`
    # into U+00A0, which Python's `\s` matches.
    text = _WHITESPACE_RE.sub(
        " ",
        html.unescape(_HTML_TAG_RE.sub(" ", response.text)),
    )
    sqm_match = _SQM_RE.search(text)
    bortle_match = _BORTLE_RE.search(text)
    sqm = float(sqm_match.group(1)) if sqm_match else None
    bortle = int(bortle_match.group(1)) if bortle_match else None
    logger.info(
        "[clear-outside] %s,%s → sqm=%s bortle=%s",
        latitude,
        longitude,
        sqm,
        bortle,
    )
    return {"sqm": sqm, "bortle": bortle, "source_url": url}


@router.get("", response_model=list[LocationResponse])
async def list_locations(
    include_retired: bool = Query(False, description="Include soft-deleted locations"),
):
    """List locations, default first. Soft-deleted rows are hidden unless
    `include_retired=true`."""
    async with get_db() as conn:
        where = "" if include_retired else "WHERE active = 1"
        rows = await conn.execute(f"SELECT * FROM location {where} ORDER BY is_default DESC, name")  # nosec B608 - table name from internal allow-list, not user input
        results = []
        for r in await rows.fetchall():
            d = _row_to_dict(r)
            _bool_fields(d, "is_default", "active")
            results.append(d)
        return results


@router.get("/default", response_model=LocationResponse | None)
async def get_default_location():
    """Get the default location, or null if none set."""
    async with get_db() as conn:
        row = await conn.execute(
            "SELECT * FROM location WHERE is_default = 1 AND active = 1 LIMIT 1"
        )
        result = await row.fetchone()
        if result is None:
            return None
        d = _row_to_dict(result)
        _bool_fields(d, "is_default", "active")
        return d


@router.get("/{location_id}", response_model=LocationResponse)
async def get_location(location_id: int):
    """Get a single location by ID."""
    async with get_db() as conn:
        row = await conn.execute("SELECT * FROM location WHERE id = ?", (location_id,))
        result = await row.fetchone()
        if result is None:
            raise HTTPException(status_code=404, detail="Location not found")
        d = _row_to_dict(result)
        _bool_fields(d, "is_default")
        return d


@router.post("", response_model=LocationResponse, status_code=201)
async def create_location(body: LocationCreate):
    """Create a new location."""
    geo_tz = (
        body.geo_timezone
        if body.geo_timezone is not None
        else _lookup_geo_timezone(body.latitude, body.longitude)
    )

    async with get_db() as conn:
        # If this is the first location or is_default is set, enforce single default
        count_row = await conn.execute("SELECT COUNT(*) as cnt FROM location")
        count = (await count_row.fetchone())["cnt"]
        make_default = body.is_default or count == 0

        with integrity_guard(conflict_detail=f"Location already exists: {body.name}"):
            cursor = await conn.execute(
                """INSERT INTO location (
                    name, latitude, longitude, elevation_m, timezone, geo_timezone,
                    bortle_class, sqm_reading, city, state_province,
                    country, postal_code, typical_seeing_low_arcsec,
                    typical_seeing_high_arcsec, is_default, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    body.name.strip(),
                    body.latitude,
                    body.longitude,
                    body.elevation_m,
                    body.timezone.strip(),
                    geo_tz,
                    body.bortle_class,
                    body.sqm_reading,
                    body.city,
                    body.state_province,
                    body.country,
                    body.postal_code,
                    body.typical_seeing_low_arcsec,
                    body.typical_seeing_high_arcsec,
                    1 if make_default else 0,
                    body.notes,
                ),
            )

        new_id = cursor.lastrowid
        if make_default:
            await _ensure_single_default(conn, new_id)

        if body.horizons is None:
            # Legacy behaviour — auto-seed a 0° artificial horizon as
            # this location's default. Every location is guaranteed to
            # have ≥1 horizon so the planner never has to branch on
            # "location lacks a horizon".
            await conn.execute(
                """
                INSERT INTO location_horizon (
                    location_id, name, type, flat_altitude_deg, is_default
                ) VALUES (?, '0° flat', 'artificial', 0, 1)
                """,
                (new_id,),
            )
        else:
            # Atomic create — user supplied a pre-validated horizon list
            # (exactly-one-default, ≤1 custom, unique names). Apply each
            # in the same transaction so the invariant holds at commit.
            # Points for custom horizons are inserted via executemany.
            for seed in body.horizons:
                source = seed.source if seed.type == "custom" else None
                source_filename = seed.source_filename if seed.type == "custom" else None
                cursor_h = await conn.execute(
                    """
                    INSERT INTO location_horizon (
                        location_id, name, type, flat_altitude_deg,
                        source, source_filename, notes, is_default
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_id,
                        seed.name.strip(),
                        seed.type,
                        seed.flat_altitude_deg,
                        source,
                        source_filename,
                        seed.notes,
                        1 if seed.is_default else 0,
                    ),
                )
                horizon_id = cursor_h.lastrowid
                if seed.type == "custom" and seed.points:
                    await conn.executemany(
                        "INSERT INTO location_horizon_point "
                        "(horizon_id, azimuth_deg, altitude_deg) VALUES (?, ?, ?)",
                        [(horizon_id, p.azimuth_deg, p.altitude_deg) for p in seed.points],
                    )

        await conn.commit()

        row = await conn.execute("SELECT * FROM location WHERE id = ?", (new_id,))
        d = _row_to_dict(await row.fetchone())
        _bool_fields(d, "is_default")
        return d


@router.put("/{location_id}", response_model=LocationResponse)
async def update_location(location_id: int, body: LocationUpdate):
    """Update a location."""
    async with get_db() as conn:
        existing = await conn.execute("SELECT * FROM location WHERE id = ?", (location_id,))
        existing_row = await existing.fetchone()
        if existing_row is None:
            raise HTTPException(status_code=404, detail="Location not found")

        updates = body.model_dump(exclude_unset=True)
        if "is_default" in updates:
            updates["is_default"] = 1 if updates["is_default"] else 0
        if "name" in updates and updates["name"]:
            updates["name"] = updates["name"].strip()

        # Recompute geo_timezone if coordinates changed AND caller didn't
        # override it explicitly. An explicit value in the request wins.
        if ("latitude" in updates or "longitude" in updates) and "geo_timezone" not in updates:
            lat = updates.get("latitude", existing_row["latitude"])
            lon = updates.get("longitude", existing_row["longitude"])
            updates["geo_timezone"] = _lookup_geo_timezone(lat, lon)

        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [location_id]
            with integrity_guard(conflict_detail="Location name already exists"):
                await conn.execute(
                    f"UPDATE location SET {set_clause} WHERE id = ?",  # nosec B608 - table name from internal allow-list, not user input
                    values,
                )

        if updates.get("is_default") == 1:
            await _ensure_single_default(conn, location_id)

        await conn.commit()

        row = await conn.execute("SELECT * FROM location WHERE id = ?", (location_id,))
        d = _row_to_dict(await row.fetchone())
        _bool_fields(d, "is_default")
        return d


@router.post("/{location_id}/set-default", response_model=LocationResponse)
async def set_default_location(location_id: int):
    """Set a location as the default."""
    async with get_db() as conn:
        existing = await conn.execute("SELECT * FROM location WHERE id = ?", (location_id,))
        if await existing.fetchone() is None:
            raise HTTPException(status_code=404, detail="Location not found")

        await conn.execute(
            "UPDATE location SET is_default = 1 WHERE id = ?",
            (location_id,),
        )
        await _ensure_single_default(conn, location_id)
        await conn.commit()

        row = await conn.execute("SELECT * FROM location WHERE id = ?", (location_id,))
        d = _row_to_dict(await row.fetchone())
        _bool_fields(d, "is_default")
        return d


@router.delete("/{location_id}")
async def delete_location(location_id: int):
    """Soft-delete a location (`active = 0`). If it was the default, promote
    the next active location. The row is preserved so future session records
    that reference this location_id don't orphan — retrieve with
    `?include_retired=true` and restore via the `/restore` endpoint."""
    async with get_db() as conn:
        existing = await conn.execute("SELECT * FROM location WHERE id = ?", (location_id,))
        row = await existing.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Location not found")

        was_default = bool(row["is_default"])
        await conn.execute(
            "UPDATE location SET active = 0, is_default = 0 WHERE id = ?",
            (location_id,),
        )

        # Promote the first remaining ACTIVE location to default if needed.
        if was_default:
            next_row = await conn.execute(
                "SELECT id FROM location WHERE active = 1 ORDER BY name LIMIT 1"
            )
            next_loc = await next_row.fetchone()
            if next_loc:
                await conn.execute(
                    "UPDATE location SET is_default = 1 WHERE id = ?",
                    (next_loc["id"],),
                )

        await conn.commit()
    return {"ok": True}


@router.post("/{location_id}/restore", response_model=LocationResponse)
async def restore_location(location_id: int):
    """Restore a soft-deleted location (`active = 1`)."""
    async with get_db() as conn:
        existing = await conn.execute("SELECT * FROM location WHERE id = ?", (location_id,))
        if await existing.fetchone() is None:
            raise HTTPException(status_code=404, detail="Location not found")
        await conn.execute(
            "UPDATE location SET active = 1 WHERE id = ?",
            (location_id,),
        )
        await conn.commit()
        row = await conn.execute("SELECT * FROM location WHERE id = ?", (location_id,))
        d = _row_to_dict(await row.fetchone())
        _bool_fields(d, "is_default", "active")
        return d
