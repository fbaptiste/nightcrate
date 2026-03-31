"""Application settings — loaded from and persisted to settings.json."""

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

APP_DIR = Path(os.path.expanduser("~/Library/Application Support/NightCrate"))
SETTINGS_FILE = APP_DIR / "settings.json"


class Settings(BaseModel):
    theme: Literal["light", "dark", "browser"] = "browser"
    gpu_acceleration: bool = True
    max_worker_cores: int | None = None  # None → cpu_count - 1


def _ensure_app_dir() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    _ensure_app_dir()
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text())
            return Settings(**data)
        except Exception:
            pass
    return Settings()


def save_settings(settings: Settings) -> None:
    _ensure_app_dir()
    SETTINGS_FILE.write_text(settings.model_dump_json(indent=2))


# Module-level singleton — loaded once at startup, mutated by the settings API.
_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def update_settings(updated: Settings) -> Settings:
    global _settings
    _settings = updated
    save_settings(updated)
    return _settings
