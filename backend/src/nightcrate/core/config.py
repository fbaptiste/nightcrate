"""Application settings — stored in the SQLite database."""

import json
from typing import Literal

from pydantic import BaseModel

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


async def get_settings() -> Settings:
    """Load settings from the database. Returns defaults for missing/invalid data."""
    async with get_db() as conn:
        cursor = await conn.execute("SELECT data FROM settings WHERE id = 1")
        row = await cursor.fetchone()
        if row:
            try:
                data = json.loads(row[0])
                return Settings(**data)
            except json.JSONDecodeError, TypeError, ValueError:
                pass
    return Settings()


async def update_settings(updated: Settings) -> Settings:
    """Persist settings to the database and return the saved value."""
    async with get_db() as conn:
        await conn.execute(
            "UPDATE settings SET data = ? WHERE id = 1",
            (updated.model_dump_json(),),
        )
        await conn.commit()
    return updated
