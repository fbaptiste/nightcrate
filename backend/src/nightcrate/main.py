"""NightCrate FastAPI application."""

import asyncio
import dataclasses
import logging
import os
import sqlite3
import sys
from contextlib import AsyncExitStack, asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Global astropy IERS configuration lives in
# ``nightcrate.services.planner_visibility`` (top of file). Importing
# the planner API below loads that module, which sets
# ``auto_download=False`` and ``auto_max_age=None`` before the first
# astropy call.
import aiosqlite
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from platformdirs import user_log_dir

from nightcrate.api import (
    aberration,
    admin,
    app_activity,
    calculators,
    diagnostics,
    dso,
    equipment,
    files,
    gallery,
    home,
    horizons,
    images,
    imaging_rules,
    ingest,
    locations,
    messier,
    phd2,
    planner,
    plate_solve,
    project_info,
    project_night_notes,
    project_rig_setups,
    project_sessions,
    project_solve,
    project_targets,
    projects,
    rig_setups,
    rigs,
    settings,
    star_catalog,
    updates,
    weather,
    wishlist,
)
from nightcrate.api.diagnostics import RequestTrackingMiddleware
from nightcrate.core import child_processes, runtime
from nightcrate.core.app_config import load_config, workspace_db_path
from nightcrate.core.compute import set_gpu_enabled
from nightcrate.core.config import get_settings
from nightcrate.core.instance_lock import InstanceLockHeld, acquire_instance_lock
from nightcrate.core.test_hooks import busy_children
from nightcrate.db.session import (
    WorkspaceUnavailable,
    get_db,
    set_db_path,
    set_workspace_problem,
    workspace_problem,
)
from nightcrate.db.workspace_upgrade import WorkspaceRefused, initialize_workspace
from nightcrate.services import plate_solve as plate_solve_service
from nightcrate.services.star_catalog import fetch as star_catalog_fetch

_LOG_FORMAT = "%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Tuple constants for narrow except clauses — sidesteps the py314
# ruff-format bug documented in CLAUDE.md "Gotchas".
_MAINT_EXPECTED_ERRS: tuple[type[BaseException], ...] = (
    sqlite3.Error,
    OSError,
)

WEATHER_CACHE_RETENTION_DAYS = 8


async def purge_weather_cache(conn) -> int:
    """Delete provider responses too old to be useful as stale fallbacks."""
    cursor = await conn.execute(
        "DELETE FROM weather_cache WHERE fetched_at < datetime('now', ?)",
        (f"-{WEATHER_CACHE_RETENTION_DAYS} days",),
    )
    await conn.commit()
    return cursor.rowcount


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

    if runtime.production:
        folder = runtime.log_dir or Path(user_log_dir("NightCrate", appauthor=False))
        folder.mkdir(parents=True, exist_ok=True)
        runtime.log_dir = folder
        log_path = folder / "nightcrate.log"
        for name in ("nightcrate", "uvicorn", "uvicorn.error", "uvicorn.access"):
            target = logging.getLogger(name)
            if not any(getattr(h, "_nightcrate_file_handler", False) for h in target.handlers):
                file_handler = RotatingFileHandler(
                    log_path, maxBytes=5_000_000, backupCount=5, encoding="utf-8"
                )
                file_handler.setFormatter(formatter)
                file_handler._nightcrate_file_handler = True  # type: ignore[attr-defined]
                target.addHandler(file_handler)


async def _run_database_maintenance() -> None:
    """Run non-fatal startup maintenance after guarded activation."""
    app_settings = await get_settings()
    set_gpu_enabled(app_settings.gpu_acceleration)
    startup_logger = logging.getLogger("nightcrate.startup")

    try:
        async with get_db() as conn:
            await conn.execute(
                "DELETE FROM aberration_analysis WHERE created_at < datetime('now', ?)",
                (f"-{app_settings.aberration_cache_ttl_days} days",),
            )
            await conn.commit()
    except _MAINT_EXPECTED_ERRS:
        startup_logger.warning("aberration cache purge failed", exc_info=True)
    try:
        async with get_db() as conn:
            await purge_weather_cache(conn)
    except _MAINT_EXPECTED_ERRS:
        startup_logger.warning("weather cache purge failed", exc_info=True)
    try:
        from nightcrate.services.thumbnails import rehydrate_from_disk as rehydrate_thumbnails
        from nightcrate.services.thumbnails import sync_orphan_files

        async with get_db() as conn:
            conn.row_factory = aiosqlite.Row
            await rehydrate_thumbnails(conn)
            await sync_orphan_files(conn)
    except _MAINT_EXPECTED_ERRS:
        startup_logger.warning("thumbnail cache maintenance failed", exc_info=True)
    try:
        from nightcrate.services.sky_tile_cache import (
            rehydrate_from_disk as rehydrate_sky_tiles,
        )
        from nightcrate.services.sky_tile_cache import (
            sync_orphan_files as sync_sky_tile_orphans,
        )

        async with get_db() as conn:
            conn.row_factory = aiosqlite.Row
            await rehydrate_sky_tiles(conn)
            await sync_sky_tile_orphans(conn)
    except _MAINT_EXPECTED_ERRS:
        startup_logger.warning("sky-tile cache maintenance failed", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    async with AsyncExitStack() as stack:
        if not runtime.production:
            try:
                instance_lock = acquire_instance_lock(
                    runtime.install_kind, runtime.app_version(), None
                )
            except InstanceLockHeld as exc:
                info = exc.info
                if info is None:
                    logging.getLogger("nightcrate.startup").error(
                        "[startup] NightCrate is already running; quit it first"
                    )
                else:
                    logging.getLogger("nightcrate.startup").error(
                        "[startup] NightCrate is already running (%s, pid %d, version %s); "
                        "quit it first",
                        info.kind,
                        info.pid,
                        info.version,
                    )
                raise SystemExit(3) from exc
            stack.callback(instance_lock.release)

        await stack.enter_async_context(busy_children())
        try:
            delay = float(os.getenv("NIGHTCRATE_TEST_STARTUP_DELAY", "0"))
            if delay:
                await asyncio.sleep(delay)

            set_workspace_problem(None)
            config = load_config()
            if config.db_configured and config.active_db is not None:
                workspace = Path(config.active_db)
                entry = config.databases.get(config.active_db)
                name = entry.name if entry is not None and entry.name else workspace.name
                try:
                    result = initialize_workspace(
                        workspace,
                        name,
                        runtime.app_version(),
                        on_step=lambda step: runtime.report_step(step, name),
                    )
                except WorkspaceRefused as exc:
                    set_workspace_problem(exc.problem)
                else:
                    set_db_path(workspace_db_path(workspace))
                    runtime.last_activation_backup = result.backup_path
                    await _run_database_maintenance()
            await updates.record_first_run_version()
            yield
        finally:
            await star_catalog_fetch.shutdown()
            await plate_solve_service.shutdown()
            child_processes.terminate_all()


openapi_tags = [
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
        "name": "Administration",
        "description": (
            "Database lifecycle management: create, register, activate, and remove "
            "databases. First-run setup wizard support, filesystem browsing for "
            "database file selection, directory creation, and equipment re-seeding."
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
        "name": "Deep-Sky Objects",
        "description": (
            "Deep-sky object catalog browsing and designation resolution. "
            "Backed by OpenNGC (NGC/IC/Messier/Caldwell + ~20 cross-reference "
            "catalogs). Provides list, detail, exact-designation lookup, and "
            "catalog-source attribution endpoints."
        ),
    },
    {
        "name": "Diagnostics",
        "description": (
            "Request timing and performance diagnostics. Tracks API request "
            "durations grouped by activity label for in-app performance analysis."
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
        "name": "File Browser",
        "description": (
            "Browse the local filesystem for image files, archives, and PixInsight "
            "projects. Lists volumes, directories, and supported file types. Handles "
            "navigation into archive files and multi-image project containers."
        ),
    },
    {
        "name": "Horizons",
        "description": (
            "Per-location custom horizon profiles (azimuth/altitude polylines) for "
            "session planning and visibility analysis. Import from N.I.N.A. .hrz, "
            "Theodolite CSV, Telescopius, APCC, or generic two-column text. Export "
            "to N.I.N.A., Stellarium, or CSV. Includes a stateless parse endpoint "
            "used by the staged-save editor flow."
        ),
    },
    {
        "name": "Image Analyzer",
        "description": (
            "Load, render, and inspect astronomical image files (FITS, XISF, "
            "PixInsight projects, PNG, JPEG, TIFF). Provides stretched PNG rendering, "
            "per-channel statistics, histograms, pixel inspection, header reading and "
            "editing, and recent file tracking."
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
        "name": "Lookup Tables",
        "description": (
            "Reference data tables that provide the vocabularies and classification "
            "values used by equipment records: manufacturers, optical designs, mount "
            "types, connection interfaces, connector sizes, filter sizes, filter "
            "types, form factors, and focuser types."
        ),
    },
    {
        "name": "PHD2 Guide-Log Analyzer",
        "description": (
            "Parse and analyse PHD2 autoguiding logs. Handles format "
            "irregularities (locale-decimal recovery, missing app version, "
            "18-vs-19-column arity) and classifies INFO events into a closed "
            "vocabulary (settle, dither, alert, pause, etc.). Delivers "
            "the parser, per-section summary metrics, guiding graph "
            "(RA/Dec time-series + pulses + SNR + Mass), dispersion "
            "scatter plot, and per-frame data table."
        ),
    },
    {
        "name": "Plate Solve",
        "description": (
            "Plate solve astronomical images via ASTAP integration. Supports "
            "near solve (with coordinate hints from FITS headers) and blind "
            "solve. Works with all NightCrate image sources: filesystem, "
            "archives, and PixInsight projects."
        ),
    },
    {
        "name": "Projects",
        "description": (
            "Imaging project management: create and organise projects with "
            "multi-image galleries, drag-to-reorder, main image designation, "
            "and auto-stretched thumbnails. Supports images from the filesystem, "
            "archives (zip/tar/7z), and PixInsight .pxiproject containers via "
            "the :: virtual-path convention."
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
        "name": "Settings",
        "description": (
            "Read and update application settings stored in the database. Controls "
            "preferences such as GPU acceleration, worker core limits, theme mode, "
            "and aberration cache TTL."
        ),
    },
    {
        "name": "Star catalog",
        "description": (
            "Manage the shared Siril Gaia DR3 star catalog and locally built "
            "field-range indexes used by the built-in plate solver."
        ),
    },
    {
        "name": "Target Planner",
        "description": (
            "Tonight's visibility planning for DSO targets. Computes altitude tracks, "
            "scoring (observability, meridian timing, moon impact, frame fit), annual "
            "hours charts, sky-tile cache, and FOV simulator. Includes target wishlist "
            "with sections, date ranges, and calendar view."
        ),
    },
    {
        "name": "Updates",
        "description": "Application update checks, notices, and install coordination.",
    },
    {
        "name": "Weather",
        "description": (
            "Personal imaging verdicts (Go / Uncertain / No / Not enough data) "
            "for the next 14 nights, from Open-Meteo hourly forecasts and each "
            "location's imaging rules, with hourly detail and methodology."
        ),
    },
]

app = FastAPI(title="NightCrate", lifespan=lifespan, openapi_tags=openapi_tags)

_LAN_MODE = os.environ.get("NIGHTCRATE_LAN", "").strip() == "1"

if not runtime.production:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if _LAN_MODE else ["http://localhost:5173", "http://127.0.0.1:5173"],
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
app.include_router(imaging_rules.router)
app.include_router(horizons.router)
app.include_router(horizons.parse_router)
app.include_router(rigs.router)
app.include_router(rig_setups.router)
app.include_router(calculators.router)
app.include_router(weather.router)
app.include_router(dso.router)
app.include_router(planner.router)
app.include_router(phd2.router)
app.include_router(plate_solve.router)
app.include_router(projects.router)
app.include_router(project_night_notes.router)
app.include_router(project_rig_setups.router)
app.include_router(gallery.router)
app.include_router(home.router)
app.include_router(project_info.router)
app.include_router(messier.router)
app.include_router(ingest.router)
app.include_router(project_sessions.router)
app.include_router(project_solve.router)
app.include_router(project_targets.router)
app.include_router(project_targets.links_router)
app.include_router(settings.router)
app.include_router(star_catalog.router)
app.include_router(admin.router)
app.include_router(updates.router)
app.include_router(app_activity.router)
app.include_router(wishlist.router)
app.include_router(diagnostics.router)


@app.get("/api/health", tags=["Administration"])
async def health() -> dict:
    """Check application health, version, and database configuration status."""
    config = load_config()
    problem = workspace_problem()
    return {
        "status": "ok",
        "version": runtime.app_version(),
        "db_configured": config.db_configured and problem is None,
        "install_kind": runtime.install_kind,
        "workspace_problem": dataclasses.asdict(problem) if problem is not None else None,
    }


@app.exception_handler(WorkspaceUnavailable)
async def workspace_unavailable_handler(
    _request: Request, _exc: WorkspaceUnavailable
) -> JSONResponse:
    problem = workspace_problem()
    return JSONResponse(
        status_code=409,
        content={"detail": {"problem": dataclasses.asdict(problem) if problem else None}},
    )
