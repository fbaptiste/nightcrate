"""NightCrate FastAPI application."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from nightcrate.api import (
    aberration,
    admin,
    diagnostics,
    equipment,
    files,
    images,
    locations,
    settings,
    weather,
)
from nightcrate.api.diagnostics import RequestTrackingMiddleware
from nightcrate.core.app_config import load_config
from nightcrate.core.compute import set_gpu_enabled
from nightcrate.core.config import get_settings
from nightcrate.db.migrations import apply_migrations
from nightcrate.db.session import get_db, set_db_path

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

    # Check if a database is configured and available before running DB operations.
    # If not configured, the app starts in "unconfigured" mode where only
    # /api/health and /api/admin/* endpoints are functional.
    config = load_config()
    if config.db_configured:
        set_db_path(Path(config.active_db))
        apply_migrations()
        # Load seed data (first run populates, subsequent runs check for updates).
        # Uses a separate sync sqlite3 connection — the seed loader is synchronous
        # and aiosqlite's internal connection has thread restrictions.
        try:
            import importlib.resources
            import sqlite3

            from nightcrate.db.session import get_db_path
            from nightcrate.seed_loader import load_all

            csv_root = importlib.resources.files("nightcrate") / "data" / "seed"
            sync_conn = sqlite3.connect(str(get_db_path()))
            try:
                sync_conn.row_factory = sqlite3.Row
                sync_conn.execute("PRAGMA foreign_keys = ON")
                load_all(sync_conn, csv_root, "auto")
                sync_conn.commit()
            finally:
                sync_conn.close()
        except Exception:
            logging.getLogger("nightcrate").warning("Seed loader failed", exc_info=True)
            # Non-fatal — don't block startup
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
        # Purge stale weather cache entries
        try:
            weather_ttl = app_settings.weather_cache_ttl_hours
            async with get_db() as conn:
                await conn.execute(
                    "DELETE FROM weather_cache WHERE fetched_at < datetime('now', ?)",
                    (f"-{weather_ttl * 2} hours",),
                )
                await conn.commit()
        except Exception:
            pass  # Non-fatal — don't block startup

    yield


openapi_tags = [
    {
        "name": "File Browser",
        "description": (
            "Browse the local filesystem for image files, archives, and PixInsight "
            "projects. Lists volumes, directories, and supported file types. Handles "
            "navigation into archive files and multi-image project containers."
        ),
    },
    {
        "name": "Image Viewer",
        "description": (
            "Load, render, and inspect astronomical image files (FITS, XISF, "
            "PixInsight projects, PNG, JPEG, TIFF). Provides stretched PNG rendering, "
            "per-channel statistics, histograms, pixel inspection, header reading and "
            "editing, and recent file tracking."
        ),
    },
    {
        "name": "Aberration Inspector",
        "description": (
            "Analyse star shapes across the imaging field to diagnose optical "
            "aberrations such as tilt, coma, and field curvature. Performs star "
            "detection, sample grid computation, and crop rendering with results "
            "cached in the database."
        ),
    },
    {
        "name": "Equipment",
        "description": (
            "CRUD operations for all equipment types in the NightCrate catalog: "
            "cameras, sensors, telescopes (OTAs) with configurations, filters with "
            "passbands and size options, mounts, focusers, filter wheels, OAGs, "
            "guide scopes, computers, and software. Supports soft-delete with "
            "optional restore."
        ),
    },
    {
        "name": "Lookup Tables",
        "description": (
            "Reference data tables that provide the vocabularies and classification "
            "values used by equipment records: manufacturers, optical designs, mount "
            "types, connection interfaces, connector sizes, filter sizes, filter "
            "types, form factors, and focuser types."
        ),
    },
    {
        "name": "Locations",
        "description": (
            "Manage imaging locations with coordinates, timezone, Bortle class, "
            "and SQM readings. Supports multiple locations with a default for "
            "weather, moon phase, and session planning features."
        ),
    },
    {
        "name": "Weather",
        "description": (
            "Weather forecast and imaging quality predictions. Provides 7-day "
            "daily summaries with composite imaging quality scores, hourly "
            "detail breakdowns with seeing estimates, and methodology "
            "documentation. Integrates Open-Meteo weather data with astronomy, "
            "seeing estimation, and imaging quality scoring."
        ),
    },
    {
        "name": "Settings",
        "description": (
            "Read and update application settings stored in the database. Controls "
            "preferences such as GPU acceleration, worker core limits, theme mode, "
            "and aberration cache TTL."
        ),
    },
    {
        "name": "Administration",
        "description": (
            "Database lifecycle management: create, register, activate, and remove "
            "databases. First-run setup wizard support, filesystem browsing for "
            "database file selection, directory creation, and equipment re-seeding."
        ),
    },
    {
        "name": "Diagnostics",
        "description": (
            "Request timing and performance diagnostics. Tracks API request "
            "durations grouped by activity label for in-app performance analysis."
        ),
    },
]

app = FastAPI(title="NightCrate", lifespan=lifespan, openapi_tags=openapi_tags)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestTrackingMiddleware)

# Router order doesn't affect Swagger section order (openapi_tags controls that)
app.include_router(files.router)
app.include_router(images.router)
app.include_router(aberration.router)
app.include_router(equipment.router)
app.include_router(equipment.lookup_router)
app.include_router(locations.router)
app.include_router(weather.router)
app.include_router(settings.router)
app.include_router(admin.router)
app.include_router(diagnostics.router)

_VERSION_FILE = Path(__file__).resolve().parents[3] / "VERSION"
APP_VERSION = _VERSION_FILE.read_text().strip() if _VERSION_FILE.exists() else "unknown"


@app.get("/api/health", tags=["Administration"])
async def health() -> dict:
    """Check application health, version, and database configuration status."""
    config = load_config()
    return {"status": "ok", "version": APP_VERSION, "db_configured": config.db_configured}


def run() -> None:
    uvicorn.run("nightcrate.main:app", host="127.0.0.1", port=8000, reload=True)
