"""Location management API — CRUD for imaging locations."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from nightcrate.db.session import get_db

router = APIRouter(prefix="/api/locations", tags=["Locations"])


# ── Models ────────────────────────────────────────────────────────────────────


class LocationCreate(BaseModel):
    name: str
    latitude: float
    longitude: float
    elevation_m: float | None = None
    timezone: str
    bortle_class: int | None = None
    sqm_reading: float | None = None
    city: str | None = None
    state_province: str | None = None
    country: str | None = None
    postal_code: str | None = None
    is_default: bool = False
    notes: str | None = None

    @field_validator("latitude")
    @classmethod
    def check_lat(cls, v: float) -> float:
        if not -90 <= v <= 90:
            raise ValueError("Latitude must be between -90 and 90")
        return v

    @field_validator("longitude")
    @classmethod
    def check_lon(cls, v: float) -> float:
        if not -180 <= v <= 180:
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


class LocationUpdate(BaseModel):
    name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    elevation_m: float | None = None
    timezone: str | None = None
    bortle_class: int | None = None
    sqm_reading: float | None = None
    city: str | None = None
    state_province: str | None = None
    country: str | None = None
    postal_code: str | None = None
    is_default: bool | None = None
    notes: str | None = None

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


class LocationResponse(BaseModel):
    id: int
    name: str
    latitude: float
    longitude: float
    elevation_m: float | None
    timezone: str
    bortle_class: int | None
    sqm_reading: float | None
    city: str | None
    state_province: str | None
    country: str | None
    postal_code: str | None
    is_default: bool
    notes: str | None
    created_at: str
    updated_at: str


# ── Helpers ───────────────────────────────────────────────────────────────────


def _row_to_dict(row) -> dict:
    return dict(row)


def _bool_fields(d: dict, *keys: str) -> dict:
    for k in keys:
        if k in d:
            d[k] = bool(d[k])
    return d


async def _ensure_single_default(conn, new_default_id: int) -> None:
    """Clear is_default on all rows except the given ID."""
    await conn.execute(
        "UPDATE location SET is_default = 0 WHERE id != ?",
        (new_default_id,),
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("", response_model=list[LocationResponse])
async def list_locations():
    """List all locations, default first."""
    async with get_db() as conn:
        rows = await conn.execute("SELECT * FROM location ORDER BY is_default DESC, name")
        results = []
        for r in await rows.fetchall():
            d = _row_to_dict(r)
            _bool_fields(d, "is_default")
            results.append(d)
        return results


@router.get("/default", response_model=LocationResponse | None)
async def get_default_location():
    """Get the default location, or null if none set."""
    async with get_db() as conn:
        row = await conn.execute("SELECT * FROM location WHERE is_default = 1 LIMIT 1")
        result = await row.fetchone()
        if result is None:
            return None
        d = _row_to_dict(result)
        _bool_fields(d, "is_default")
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
    async with get_db() as conn:
        # If this is the first location or is_default is set, enforce single default
        count_row = await conn.execute("SELECT COUNT(*) as cnt FROM location")
        count = (await count_row.fetchone())["cnt"]
        make_default = body.is_default or count == 0

        try:
            cursor = await conn.execute(
                """INSERT INTO location (
                    name, latitude, longitude, elevation_m, timezone,
                    bortle_class, sqm_reading, city, state_province,
                    country, postal_code, is_default, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    body.name.strip(),
                    body.latitude,
                    body.longitude,
                    body.elevation_m,
                    body.timezone.strip(),
                    body.bortle_class,
                    body.sqm_reading,
                    body.city,
                    body.state_province,
                    body.country,
                    body.postal_code,
                    1 if make_default else 0,
                    body.notes,
                ),
            )
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(
                    status_code=409,
                    detail=f"Location already exists: {body.name}",
                )
            raise

        new_id = cursor.lastrowid
        if make_default:
            await _ensure_single_default(conn, new_id)
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
        if await existing.fetchone() is None:
            raise HTTPException(status_code=404, detail="Location not found")

        updates = body.model_dump(exclude_unset=True)
        if "is_default" in updates:
            updates["is_default"] = 1 if updates["is_default"] else 0
        if "name" in updates and updates["name"]:
            updates["name"] = updates["name"].strip()

        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [location_id]
            try:
                await conn.execute(
                    f"UPDATE location SET {set_clause} WHERE id = ?",
                    values,
                )
            except Exception as exc:
                if "UNIQUE" in str(exc):
                    raise HTTPException(
                        status_code=409,
                        detail="Location name already exists",
                    )
                raise

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
    """Delete a location. If it was the default, the next location becomes default."""
    async with get_db() as conn:
        existing = await conn.execute("SELECT * FROM location WHERE id = ?", (location_id,))
        row = await existing.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Location not found")

        was_default = bool(row["is_default"])
        await conn.execute("DELETE FROM location WHERE id = ?", (location_id,))

        # If we deleted the default, promote the first remaining location
        if was_default:
            next_row = await conn.execute("SELECT id FROM location ORDER BY name LIMIT 1")
            next_loc = await next_row.fetchone()
            if next_loc:
                await conn.execute(
                    "UPDATE location SET is_default = 1 WHERE id = ?",
                    (next_loc["id"],),
                )

        await conn.commit()
    return {"ok": True}
