"""NightCrate FastAPI application."""

import logging
import os
import sqlite3
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from nightcrate.api import (
    aberration,
    admin,
    calculators,
    diagnostics,
    equipment,
    files,
    horizons,
    horizons_parse,
    images,
    locations,
    rigs,
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

# Tuple constants for narrow except clauses — sidesteps the py314
# ruff-format bug documented in CLAUDE.md "Gotchas".
_SEED_EXPECTED_ERRS: tuple[type[BaseException], ...] = (
    sqlite3.Error,
    OSError,
    ValueError,
)
_MAINT_EXPECTED_ERRS: tuple[type[BaseException], ...] = (
    sqlite3.Error,
    OSError,
)


def _configure_logging() -> None:
    """Add timestamps to uvicorn's log output and emit nightcrate logs at DEBUG."""
    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        for handler in logging.getLogger(name).handlers:
            handler.setFormatter(formatter)

    # The `nightcrate.*` namespace loggers have no handlers by default, so
    # INFO/DEBUG records disappear (root's default threshold is WARNING).
    # Attach our own stdout handler with matching format. Level reads from
    # the NIGHTCRATE_LOG_LEVEL env var (default INFO); set it to DEBUG when
    # you need verbose traces. Disable propagation to avoid double-printing.
    level_name = os.getenv("NIGHTCRATE_LOG_LEVEL", "INFO").upper()
    level = logging.getLevelNamesMapping().get(level_name, logging.INFO)
    nc_logger = logging.getLogger("nightcrate")
    nc_logger.setLevel(level)
    nc_logger.propagate = False
    if not any(getattr(h, "_nightcrate_handler", False) for h in nc_logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.NOTSET)
        handler.setFormatter(formatter)
        handler._nightcrate_handler = True  # type: ignore[attr-defined]
        nc_logger.addHandler(handler)


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
        except _SEED_EXPECTED_ERRS:
            # Expected failure modes — bad CSV data, FK mismatch, file missing.
            # Coding bugs (TypeError, NameError, AttributeError) now crash loudly.
            logging.getLogger("nightcrate").warning("Seed loader failed", exc_info=True)
        # Load app settings + set GPU flag up front so the purges below
        # don't depend on each other's side effects.
        app_settings = await get_settings()
        set_gpu_enabled(app_settings.gpu_acceleration)
        startup_logger = logging.getLogger("nightcrate.startup")

        # Purge stale aberration cache entries (non-fatal).
        try:
            async with get_db() as conn:
                await conn.execute(
                    "DELETE FROM aberration_analysis WHERE created_at < datetime('now', ?)",
                    (f"-{app_settings.aberration_cache_ttl_days} days",),
                )
                await conn.commit()
        except _MAINT_EXPECTED_ERRS:
            startup_logger.warning("aberration cache purge failed", exc_info=True)

        # Purge stale weather cache entries (non-fatal).
        try:
            async with get_db() as conn:
                await conn.execute(
                    "DELETE FROM weather_cache WHERE fetched_at < datetime('now', ?)",
                    (f"-{app_settings.weather_cache_ttl_hours * 2} hours",),
                )
                await conn.commit()
        except _MAINT_EXPECTED_ERRS:
            startup_logger.warning("weather cache purge failed", exc_info=True)

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
        "name": "Rigs",
        "description": (
            "Imaging rig templates: user-composed equipment configurations with "
            "optical calculators (image scale, FOV, sampling assessment). Each rig "
            "combines an OTA configuration, camera, and optional filter wheel, mount, "
            "guiding, and peripheral equipment."
        ),
    },
    {
        "name": "Calculators",
        "description": (
            "Stand-alone astronomy and optical calculators: coordinate formatting "
            "and parsing, RA/Dec ⇄ Alt/Az transforms, local sidereal time, tonight's "
            "astronomy summary, angular/linear/temperature unit conversions, pixel "
            "scale, field of view, raw file-size estimates, Kasten-Young airmass, "
            "and SQM / Bortle / NELM sky-quality conversions."
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
app.include_router(horizons.router)
app.include_router(horizons_parse.router)
app.include_router(rigs.router)
app.include_router(calculators.router)
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
