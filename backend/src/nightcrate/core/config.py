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
    # Target Planner filter defaults — initial slider values on the
    # planner page. The altitude floor now lives on each location as a
    # horizon (see ``location_horizon``), so there's no global flat
    # default setting anymore.
    planner_min_visibility_hours: float = 2.0
    planner_max_magnitude: float = 12.0
    planner_min_size_arcmin: float = 5.0
    # Initial bounds for the Frames-Well coverage-range slider (and
    # the default band the slider resets to when the rig changes).
    # 0-200 = no filter; 15-90 matches the old fixed "frames well"
    # bounds from the checkbox era.
    planner_frames_well_min_pct: float = 15.0
    planner_frames_well_max_pct: float = 90.0
    # Default moon-separation value for the "Best time of year" chart
    # in the planner detail panel. ``0`` ignores the moon entirely
    # (every hour above horizon during astro dark counts); larger
    # values filter out nights where the moon lands within that angle
    # of the target.
    planner_moon_sep_deg: int = 0
    # Disk budget for the HiPS/DSS2 caches. Covers both the per-DSO
    # ``APP_DIR/thumbnails/`` (list/detail/rig_framed variants) and
    # the v0.18.0 regional ``APP_DIR/sky_tiles/`` cache. 500 MB is the
    # Pass C default — the regional cache caches whole HEALPix tiles
    # shared across DSOs, so a larger budget makes the cache-reuse
    # payoff actually compound. Users on tight disks can dial down in
    # Settings; users browsing hundreds of targets can go up to 5 GB.
    thumbnail_cache_max_mb: int = 500
    # Monotonic counter appended to thumbnail URLs as ``&_g=N`` so that
    # clearing the cache invalidates any copies the user's browser HTTP
    # cache holds. Incremented by the cache-clear endpoint.
    thumbnail_cache_generation: int = 0


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
