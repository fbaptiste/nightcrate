"""HTTP and repository access for per-location imaging rules."""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from nightcrate.api._common import bool_fields, row_to_dict
from nightcrate.db.session import get_db
from nightcrate.services.imaging_rules import (
    DEFAULT_PRESET,
    PRESETS,
    ImagingRules,
    PresetKey,
)

router = APIRouter(tags=["Weather"])

_RULE_FIELDS = tuple(ImagingRules.model_fields)
_BOOLEAN_FIELDS = (
    "cloud_use_ecmwf",
    "cloud_use_gfs",
    "cloud_use_icon",
    "wind_counted",
    "dew_counted",
    "moon_must_be_down",
)


class ImagingRulesResponse(BaseModel):
    location_id: int
    saved: bool
    rules: ImagingRules


class PresetResponse(BaseModel):
    key: PresetKey
    label: str
    rules: ImagingRules


async def _require_active_location(conn: Any, location_id: int) -> None:
    cursor = await conn.execute(
        "SELECT 1 FROM location WHERE id = ? AND active = 1",
        (location_id,),
    )
    if await cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="Location not found")


async def load_rules(conn: Any, location_id: int) -> tuple[ImagingRules, bool]:
    """Load saved rules, or return a copy of the default preset."""
    cursor = await conn.execute(
        f"SELECT {', '.join(_RULE_FIELDS)} FROM location_imaging_rules "  # nosec B608 - fixed model field names
        "WHERE location_id = ?",
        (location_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return PRESETS[DEFAULT_PRESET][1].model_copy(deep=True), False
    values = row_to_dict(row)
    bool_fields(values, *_BOOLEAN_FIELDS)
    return ImagingRules.model_validate(values), True


@router.get(
    "/api/locations/{location_id}/imaging-rules",
    response_model=ImagingRulesResponse,
)
async def get_imaging_rules(location_id: int) -> ImagingRulesResponse:
    async with get_db() as conn:
        await _require_active_location(conn, location_id)
        rules, saved = await load_rules(conn, location_id)
    return ImagingRulesResponse(location_id=location_id, saved=saved, rules=rules)


@router.put(
    "/api/locations/{location_id}/imaging-rules",
    response_model=ImagingRulesResponse,
)
async def put_imaging_rules(location_id: int, body: ImagingRules) -> ImagingRulesResponse:
    values = body.model_dump()
    for field in _BOOLEAN_FIELDS:
        values[field] = int(values[field])
    columns = ", ".join(("location_id", *_RULE_FIELDS))
    placeholders = ", ".join("?" for _ in range(len(_RULE_FIELDS) + 1))
    updates = ", ".join(f"{field} = excluded.{field}" for field in _RULE_FIELDS)
    async with get_db() as conn:
        await _require_active_location(conn, location_id)
        await conn.execute(
            f"""INSERT INTO location_imaging_rules ({columns})
                VALUES ({placeholders})
                ON CONFLICT(location_id) DO UPDATE SET {updates}""",  # nosec B608 - fixed model field names
            (location_id, *(values[field] for field in _RULE_FIELDS)),
        )
        await conn.commit()
    return ImagingRulesResponse(location_id=location_id, saved=True, rules=body)


@router.get("/api/imaging-rules/presets", response_model=list[PresetResponse])
async def list_presets() -> list[PresetResponse]:
    return [
        PresetResponse(key=key, label=label, rules=rules) for key, (label, rules) in PRESETS.items()
    ]
