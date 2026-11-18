"""Shared test fixtures."""

import asyncio
import importlib.resources
import logging
import os
import shutil
import socket
import sqlite3
import threading
import time
import zoneinfo
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import numpy as np
import pytest
import yoyo.backends.base
from astropy.io import fits
from yoyo import read_migrations
from yoyo.connections import parse_uri
from yoyo.migrations import default_migration_table

from nightcrate.db.migrations import MIGRATIONS_DIR, MigrationSQLiteBackend
from tests.shard_selection import ShardItem, parse_shard, select_shard


@pytest.fixture(autouse=True)
def _reset_vizier_mirror_health():
    """Keep process-local VizieR mirror health isolated between tests."""
    from nightcrate.catalog_loader import vizier

    vizier.reset_mirror_health()
    vizier.record_fresh_probe_for_tests()
    try:
        yield
    finally:
        vizier.reset_mirror_health()


@pytest.fixture(autouse=True)
def _restore_nightcrate_logger():
    """Keep app logging configuration isolated between tests."""
    logger = logging.getLogger("nightcrate")
    saved_level = logger.level
    saved_propagate = logger.propagate
    saved_handlers = logger.handlers.copy()
    yield
    logger.setLevel(saved_level)
    logger.propagate = saved_propagate
    logger.handlers[:] = saved_handlers


@pytest.fixture
def no_system_tz_database():
    """Hide the operating system's time-zone database to simulate Windows.

    Windows has none, so ``ZoneInfo`` must load zones from the ``tzdata``
    package (GitHub issue #16). The previous search path is restored afterwards.
    """
    saved = zoneinfo.TZPATH
    zoneinfo.reset_tzpath(to=[])
    ZoneInfo.clear_cache()
    yield
    zoneinfo.reset_tzpath(to=saved)
    ZoneInfo.clear_cache()


@pytest.fixture(autouse=True)
def _clear_weather_summary_cache():
    """Keep API-local weather state isolated between tests and event loops."""
    from nightcrate.api.weather import (
        _cache_locks,
        _night_summary_cached,
        _refresh_failures,
        _repair_attempts,
    )

    _night_summary_cached.cache_clear()
    _cache_locks.clear()
    _refresh_failures.clear()
    _repair_attempts.clear()
    yield
    _night_summary_cached.cache_clear()
    _cache_locks.clear()
    _refresh_failures.clear()
    _repair_attempts.clear()


@pytest.fixture(autouse=True)
def _no_cloud_model_network(monkeypatch):
    """Keep the multi-model cloud fetch off the network in every test.

    The weather tests patch `_fetch_or_cached` and `_fetch_or_cached_supplementary`
    individually, but the cloud-model fetch (v0.41.5) is a third call and its
    failure path is deliberately silent — so without this a test suite run would
    quietly make one live Open-Meteo request per weather request and still pass.
    Returning None exercises the documented fallback (primary cloud comes from the
    main forecast, no spread shown). Tests that want a spread patch it themselves;
    an inner patch wins over this one.
    """
    # No `raising=False`: if this function is ever renamed, every test should fail
    # loudly here rather than quietly resume making live Open-Meteo calls.
    monkeypatch.setattr(
        "nightcrate.api.weather._fetch_or_cached_cloud_models",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "nightcrate.api.weather.fetch_model_meta",
        AsyncMock(side_effect=RuntimeError("network disabled in tests")),
    )


class _TemplateMigrationBackend(MigrationSQLiteBackend):
    """Give every yoyo connection the template-only fast-write pragmas."""

    def init_connection(self, connection) -> None:
        super().init_connection(connection)
        connection.execute("PRAGMA journal_mode = MEMORY")
        connection.execute("PRAGMA synchronous = OFF")


def _template_migration_backend(path: Path) -> _TemplateMigrationBackend:
    """Open the test-only backend used to build closed database templates."""
    backend = _TemplateMigrationBackend(parse_uri(f"sqlite:///{path}"), default_migration_table)
    backend.init_database()
    return backend


def _seed_test_database(path: Path) -> None:
    """Seed a closed copy of the migrated template."""

    # Load seed data (filter_type and any other seed CSVs).
    from nightcrate.seed_loader import load_all

    csv_root = importlib.resources.files("nightcrate") / "data" / "seed"
    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = MEMORY")
        conn.execute("PRAGMA synchronous = OFF")
        conn.execute("PRAGMA foreign_keys = ON")
        load_all(conn, csv_root, mode="first_run")
        conn.commit()


@pytest.fixture(scope="session", autouse=True)
def _yoyo_without_hostname_lookup():
    """Give yoyo a deterministic hostname without changing ``socket`` itself."""

    class SocketNamespace(SimpleNamespace):
        def __getattr__(self, name):
            return getattr(socket, name)

    yoyo_socket = SocketNamespace(getfqdn=lambda: "nightcrate-tests")
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(yoyo.backends.base, "socket", yoyo_socket)
        yield


@pytest.fixture(scope="session")
def _migration_template_chain(tmp_path_factory) -> tuple[Path, dict[str, Path]]:
    """Build one migration chain and closed snapshots per pytest worker."""
    template_dir = tmp_path_factory.mktemp("migration-template-chain")
    template_db = template_dir / "test.db"
    snapshots: dict[str, Path] = {}
    migrations = read_migrations(str(MIGRATIONS_DIR))

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("nightcrate.db.session._db_path", template_db)
        monkeypatch.setattr("nightcrate.core.app_config.APP_DIR", template_dir)
        monkeypatch.setattr("nightcrate.core.app_config.CONFIG_PATH", template_dir / "config.json")

        with _template_migration_backend(template_db) as backend:
            migration_ids = [migration.id for migration in backend.to_apply(migrations)]

        for migration_id in migration_ids:
            if migration_id >= "0064.project_solve_row_order":
                snapshot = template_dir / f"before-{migration_id.split('.', 1)[0]}.db"
                shutil.copyfile(template_db, snapshot)
                snapshots[migration_id] = snapshot

            with _template_migration_backend(template_db) as backend:
                current = backend.to_apply(migrations).filter(
                    lambda migration, expected=migration_id: migration.id == expected
                )
                if len(current) != 1:
                    raise RuntimeError(f"expected one pending migration for {migration_id}")
                backend.apply_migrations(current)

        for path in [template_db, *snapshots.values()]:
            for suffix in ("-journal", "-wal", "-shm"):
                assert not Path(f"{path}{suffix}").exists()

    return template_db, snapshots


@pytest.fixture(scope="session")
def unseeded_template_db(_migration_template_chain) -> Path:
    """Return the closed, fully migrated end of the worker's template chain."""
    template_db, _ = _migration_template_chain
    return template_db


@pytest.fixture(scope="session")
def pre_migration_template(_migration_template_chain):
    """Look up closed databases immediately before migrations under test."""
    _, snapshots = _migration_template_chain

    def lookup(migration_id: str) -> Path:
        try:
            return snapshots[migration_id]
        except KeyError as exc:
            raise ValueError(f"no pre-migration snapshot for {migration_id}") from exc

    return lookup


@pytest.fixture
def pre_migration_db(tmp_path, pre_migration_template):
    """Copy a cached pre-migration database for one preservation test."""

    def copy(migration_id: str, name: str = "upgrade.db") -> Path:
        path = tmp_path / name
        shutil.copyfile(pre_migration_template(migration_id), path)
        return path

    return copy


@pytest.fixture(scope="session")
def _template_db(tmp_path_factory, unseeded_template_db) -> Path:
    """Seed one closed copy of the migrated template per pytest worker."""
    template_dir = tmp_path_factory.mktemp("seeded-template")
    template_db = template_dir / "test.db"
    shutil.copyfile(unseeded_template_db, template_db)
    _seed_test_database(template_db)
    for suffix in ("-journal", "-wal", "-shm"):
        assert not Path(f"{template_db}{suffix}").exists()
    return template_db


@pytest.fixture(autouse=True)
def _test_db(tmp_path: Path, monkeypatch, _template_db):
    """Give each test an independent copy of the database template."""
    test_db = tmp_path / "test.db"
    shutil.copyfile(_template_db, test_db)
    monkeypatch.setattr("nightcrate.db.session._db_path", test_db)
    monkeypatch.setattr("nightcrate.db.session._workspace_problem", None)
    monkeypatch.setattr("nightcrate.core.app_config.APP_DIR", tmp_path)
    monkeypatch.setattr("nightcrate.core.app_config.CONFIG_PATH", tmp_path / "config.json")


def _new_aiosqlite_workers(
    baseline: set[threading.Thread],
) -> set[threading.Thread]:
    """Return live aiosqlite workers created after ``baseline``."""
    from aiosqlite.core import _connection_worker_thread

    return {
        thread
        for thread in threading.enumerate()
        if thread not in baseline and getattr(thread, "_target", None) is _connection_worker_thread
    }


def _assert_no_aiosqlite_workers(baseline: set[threading.Thread]) -> None:
    workers = _new_aiosqlite_workers(baseline)
    assert not workers, "aiosqlite worker threads outlived the test: " + ", ".join(
        thread.name for thread in workers
    )


@pytest.fixture
def aiosqlite_worker_guard():
    """Expose the teardown guard for its deterministic negative test."""
    baseline = set(threading.enumerate())
    return lambda: _assert_no_aiosqlite_workers(baseline)


@pytest.fixture(autouse=True)
async def _drain_background_fetches(_test_db, monkeypatch):
    """Keep background work and its SQLite threads inside each test loop."""
    del _test_db, monkeypatch
    from nightcrate.api import ingest, updates
    from nightcrate.services import hips_tiles, project_images, sky_tile_cache, thumbnails

    baseline = set(threading.enumerate())
    sky_tile_cache.reset_failure_backoff()
    thumbnails.reset_failure_backoff()
    yield

    await project_images.drain_background_refreshes()
    await ingest.drain_background_thumbnail_refreshes()
    await sky_tile_cache.drain_background_fetches()
    await thumbnails.drain_background_fetches()
    await hips_tiles.drain_background_fetches()
    await updates.drain_background_fetches()
    sky_tile_cache.reset_failure_backoff()
    thumbnails.reset_failure_backoff()

    deadline = time.monotonic() + 0.5
    while _new_aiosqlite_workers(baseline) and time.monotonic() < deadline:
        await asyncio.sleep(0.01)
    _assert_no_aiosqlite_workers(baseline)


def pytest_collection_modifyitems(config, items):
    """Select one stable CI shard when NIGHTCRATE_TEST_SHARD is set."""
    raw = os.environ.get("NIGHTCRATE_TEST_SHARD")
    if not raw:
        return
    try:
        shard = parse_shard(raw)
        shard_items = []
        for item in items:
            marker = item.get_closest_marker("xdist_group")
            if marker is None:
                key = item.nodeid
            elif marker.args:
                key = marker.args[0]
            elif "name" in marker.kwargs:
                key = marker.kwargs["name"]
            else:
                raise ValueError(f"{item.nodeid} has an xdist_group marker without a name")
            shard_items.append(
                ShardItem(
                    key=key,
                    pin_to_first=item.get_closest_marker("requires_frontend") is not None,
                )
            )
        keep = select_shard(shard_items, shard)
    except ValueError as exc:
        raise pytest.UsageError(f"invalid NIGHTCRATE_TEST_SHARD: {exc}") from exc
    items[:] = [item for item, selected in zip(items, keep, strict=True) if selected]


@pytest.fixture
def tmp_fits_mono(tmp_path: Path) -> Path:
    """Create a minimal mono (uint16) FITS file and return its path."""
    # Simulate a typical astro sub: background ~1500, a few bright stars
    rng = np.random.default_rng(42)
    data = rng.integers(1400, 1600, size=(100, 120), dtype=np.uint16)
    # Add a "star" at (50, 60)
    data[48:53, 58:63] = 40000

    hdu = fits.PrimaryHDU(data)
    hdu.header["OBJECT"] = "TestTarget"
    hdu.header["EXPTIME"] = 300.0
    hdu.header["FILTER"] = "Ha"
    hdu.header["DATE-OBS"] = "2026-03-15T02:30:45"
    hdu.header["GAIN"] = 100
    hdu.header["CCD-TEMP"] = -10.0
    hdu.header["INSTRUME"] = "ZWO ASI2600MM Pro"

    path = tmp_path / "mono_test.fits"
    hdu.writeto(path, overwrite=True)
    return path


@pytest.fixture
def tmp_fits_color(tmp_path: Path) -> Path:
    """Create a minimal 3-channel (RGB, uint16) FITS file and return its path."""
    rng = np.random.default_rng(99)
    # Shape (3, H, W) — planar RGB
    data = rng.integers(1000, 2000, size=(3, 80, 100), dtype=np.uint16)
    # Make red channel brighter (higher median)
    data[0] += 500

    hdu = fits.PrimaryHDU(data)
    hdu.header["OBJECT"] = "ColorTarget"
    hdu.header["EXPTIME"] = 120.0
    hdu.header["FILTER"] = "RGB"

    path = tmp_path / "color_test.fits"
    hdu.writeto(path, overwrite=True)
    return path


@pytest.fixture
def tmp_fits_float32(tmp_path: Path) -> Path:
    """Create a float32 FITS file (already normalized 0–1)."""
    rng = np.random.default_rng(7)
    data = rng.uniform(0.01, 0.05, size=(60, 80)).astype(np.float32)
    data[25:35, 35:45] = 0.8  # bright region

    hdu = fits.PrimaryHDU(data)
    hdu.header["OBJECT"] = "FloatTarget"

    path = tmp_path / "float_test.fits"
    hdu.writeto(path, overwrite=True)
    return path


@pytest.fixture
def tmp_fits_no_image(tmp_path: Path) -> Path:
    """Create a FITS file with an empty primary HDU (no image data)."""
    hdu = fits.PrimaryHDU()
    path = tmp_path / "empty_test.fits"
    hdu.writeto(path, overwrite=True)
    return path


@pytest.fixture
def tmp_dir_with_fits(tmp_path: Path, tmp_fits_mono: Path) -> Path:
    """Create a directory tree with FITS files and subdirectories for browse tests."""
    import shutil

    sub = tmp_path / "subdir"
    sub.mkdir()
    hidden = tmp_path / ".hidden"
    hidden.mkdir()

    # Copy the mono fits into the dir
    shutil.copy(tmp_fits_mono, tmp_path / "image1.fits")
    shutil.copy(tmp_fits_mono, tmp_path / "image2.fit")
    # Non-FITS file should be excluded
    (tmp_path / "readme.txt").write_text("hello")
    # Hidden file should be excluded
    (tmp_path / ".secret.fits").write_text("nope")

    return tmp_path
