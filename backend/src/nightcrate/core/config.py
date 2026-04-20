"""Application settings — one row per preference in the `settings` KV table.

The Pydantic `Settings` model is the single source of truth for field names,
types, and defaults. The DB layer maps field ↔ row, serialising each value
as JSON text so composite types round-trip cleanly.
"""

import json
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from nightcrate.db.session import get_db


class BrowserFavorite(BaseModel):
    name: str
    path: str


class Settings(BaseModel):
    theme: Literal["light", "dark", "browser"] = "browser"
    gpu_acceleration: bool = True
    max_worker_cores: int | None = None  # None → cpu_count - 1
    last_browse_path: str | None = None
    browser_favorites: list[BrowserFavorite] = []
    aberration_cache_ttl_days: int = 30
    weather_cache_ttl_hours: int = 6
    weather_moon_penalty: bool = True
    weather_units: Literal["metric", "imperial"] = "metric"
    # User-chosen display order for the Calculators "Clocks" view. Empty list
    # means "use the component's default order"; unknown ids are filtered on
    # the client so new clocks added later don't break stored arrays.
    calculators_clock_order: list[str] = []
    # Target Planner thresholds. Used both as the flat-horizon floor for
    # locations without a custom horizon and as the initial slider values
    # on the planner page.
    planner_min_altitude_deg: int = 30
    planner_min_visibility_hours: float = 2.0
    planner_max_magnitude: float = 12.0
    planner_min_size_arcmin: float = 5.0
    # Disk budget for the HiPS/DSS2 thumbnail LRU cache under APP_DIR/thumbnails/.
    thumbnail_cache_max_mb: int = 20


async def get_settings() -> Settings:
    """Load settings from the DB. Unknown rows are ignored; missing rows fall
    back to the Pydantic defaults. Rows whose JSON fails to decode are skipped
    (the field keeps its default)."""
    async with get_db() as conn:
        cursor = await conn.execute("SELECT key, value_json FROM settings")
        rows = await cursor.fetchall()

    known = set(Settings.model_fields.keys())
    data: dict[str, Any] = {}
    for row in rows:
        key = row["key"]
        if key not in known:
            continue
        # json.JSONDecodeError is a ValueError subclass — single class catches
        # both bad JSON and any other ValueErrors json raises. Using one
        # exception class keeps the py314 ruff-format bug at bay.
        try:
            data[key] = json.loads(row["value_json"])
        except ValueError:
            # Leave the field at its Pydantic default.
            continue

    # Schema drift (type mismatch across versions) → fall back to defaults
    # rather than crash the app.
    try:
        return Settings(**data)
    except ValidationError:
        return Settings()


async def update_settings(updated: Settings) -> Settings:
    """Persist the full Settings object. Each field becomes one KV row via
    upsert; `updated_at` is refreshed on every affected row."""
    payload = updated.model_dump()
    async with get_db() as conn:
        for key, value in payload.items():
            await conn.execute(
                """
                INSERT INTO settings (key, value_json, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, json.dumps(value)),
            )
        await conn.commit()
    return updated
