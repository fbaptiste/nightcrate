"""NightCrate FastAPI application."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from nightcrate.api import aberration, diagnostics, equipment, files, images, settings
from nightcrate.api.diagnostics import RequestTrackingMiddleware
from nightcrate.core.compute import set_gpu_enabled
from nightcrate.core.config import get_settings
from nightcrate.db.migrations import apply_migrations
from nightcrate.db.session import get_db

_LOG_FORMAT = "%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _configure_logging() -> None:
    """Add timestamps to uvicorn's log output."""
    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        for handler in logging.getLogger(name).handlers:
            handler.setFormatter(formatter)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    apply_migrations()
    # Purge stale aberration cache entries
    try:
        app_settings = await get_settings()
        set_gpu_enabled(app_settings.gpu_acceleration)
        ttl_days = app_settings.aberration_cache_ttl_days
        async with get_db() as conn:
            await conn.execute(
                "DELETE FROM aberration_analysis WHERE created_at < datetime('now', ?)",
                (f"-{ttl_days} days",),
            )
            await conn.commit()
    except Exception:
        pass  # Non-fatal — don't block startup
    yield


app = FastAPI(title="NightCrate", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestTrackingMiddleware)

app.include_router(aberration.router)
app.include_router(diagnostics.router)
app.include_router(equipment.router)
app.include_router(files.router)
app.include_router(images.router)
app.include_router(settings.router)

_VERSION_FILE = Path(__file__).resolve().parents[3] / "VERSION"
APP_VERSION = _VERSION_FILE.read_text().strip() if _VERSION_FILE.exists() else "unknown"


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "version": APP_VERSION}


def run() -> None:
    uvicorn.run("nightcrate.main:app", host="127.0.0.1", port=8000, reload=True)
