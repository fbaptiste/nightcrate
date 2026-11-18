"""Tests for main.py — health endpoint, lifespan startup, and helpers."""

import logging
import tomllib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def configured_db(client, tmp_path):
    """Set up a configured database and return its path."""
    db_path = str(tmp_path / "lifespan_test.db")
    resp = await client.post(
        "/api/admin/database/setup",
        json={"path": db_path, "name": "Lifespan Test"},
    )
    assert resp.status_code == 200
    return db_path


# ---------------------------------------------------------------------------
# GET /api/health
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_health_returns_expected_fields(client):
    """Health endpoint returns status, version, and db_configured."""
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert isinstance(data["version"], str)
    assert "db_configured" in data
    assert isinstance(data["db_configured"], bool)
    assert data["raw_files"] == "available"


@pytest.mark.anyio
async def test_health_reports_package_version_and_kind(client):
    """Health reports package metadata and the source install kind."""
    resp = await client.get("/api/health")
    data = resp.json()
    pyproject = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    assert data["version"] == pyproject["project"]["version"]
    assert data["install_kind"] == "source"
    assert data["workspace_problem"] is None


@pytest.mark.anyio
async def test_health_db_not_configured_by_default(client):
    """In test env (no config.json), db_configured should be False."""
    resp = await client.get("/api/health")
    data = resp.json()
    # Test fixture doesn't set up a configured DB by default
    assert data["db_configured"] is False


@pytest.mark.anyio
async def test_health_db_configured_after_setup(client, tmp_path):
    """After setting up a database, health reports db_configured=True."""
    db_path = str(tmp_path / "health_test.db")
    setup_resp = await client.post(
        "/api/admin/database/setup",
        json={"path": db_path, "name": "Health Test"},
    )
    assert setup_resp.status_code == 200

    resp = await client.get("/api/health")
    data = resp.json()
    assert data["db_configured"] is True


# ---------------------------------------------------------------------------
# _configure_logging
# ---------------------------------------------------------------------------


def test_configure_logging():
    """_configure_logging sets formatters on uvicorn loggers."""
    from nightcrate.main import _configure_logging

    # Add a handler to uvicorn logger so we can verify it gets formatted
    logger = logging.getLogger("uvicorn")
    handler = logging.StreamHandler()
    logger.addHandler(handler)
    try:
        _configure_logging()
        assert handler.formatter is not None
        assert "%(asctime)s" in handler.formatter._fmt
    finally:
        logger.removeHandler(handler)


# ---------------------------------------------------------------------------
# Lifespan — configured DB path
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_lifespan_with_configured_db(configured_db):
    """Lifespan should run migrations, seed, and cache purge when DB is configured."""
    from fastapi import FastAPI

    from nightcrate.main import lifespan

    test_app = FastAPI()
    # The lifespan should complete without errors when a DB is configured
    async with lifespan(test_app):
        pass  # lifespan entered and exited cleanly


@pytest.mark.anyio
async def test_lifespan_unconfigured_db():
    """Lifespan with no configured DB should still start (unconfigured mode)."""
    from fastapi import FastAPI

    from nightcrate.main import lifespan

    test_app = FastAPI()
    # Without a configured DB, lifespan should skip DB operations
    async with lifespan(test_app):
        pass  # lifespan entered and exited cleanly


@pytest.mark.anyio
async def test_lifespan_drains_fetches_before_children_and_lock_release(monkeypatch):
    from fastapi import FastAPI

    from nightcrate import main

    order: list[str] = []

    def record(name):
        async def action():
            order.append(name)

        return action

    monkeypatch.setattr(main.runtime, "production", False)
    monkeypatch.setattr(
        main,
        "acquire_instance_lock",
        lambda *args: SimpleNamespace(release=lambda: order.append("lock")),
    )
    monkeypatch.setattr(
        main.star_catalog_fetch, "shutdown", AsyncMock(side_effect=record("catalog"))
    )
    monkeypatch.setattr(
        main.plate_solve_service, "shutdown", AsyncMock(side_effect=record("solver"))
    )
    monkeypatch.setattr(
        main.sky_tile_cache,
        "drain_background_fetches",
        AsyncMock(side_effect=record("sky")),
    )
    monkeypatch.setattr(
        main.thumbnails,
        "drain_background_fetches",
        AsyncMock(side_effect=record("thumbnails")),
    )
    monkeypatch.setattr(
        main.hips_tiles,
        "drain_background_fetches",
        AsyncMock(side_effect=record("hips")),
    )
    monkeypatch.setattr(
        main.updates,
        "drain_background_fetches",
        AsyncMock(side_effect=record("updates")),
    )
    monkeypatch.setattr(
        main.child_processes,
        "terminate_all",
        lambda: order.append("children"),
    )

    async with main.lifespan(FastAPI()):
        pass

    assert order == [
        "catalog",
        "solver",
        "sky",
        "thumbnails",
        "hips",
        "updates",
        "children",
        "lock",
    ]


@pytest.mark.anyio
async def test_lifespan_seed_failure_non_fatal(configured_db):
    """Data-level failures in the seed loader (bad CSV, FK mismatch, file
    missing) must not take down startup. Coding bugs (TypeError etc.) DO
    propagate — that's caught by the narrow exception tuple in main.py and
    is intentional, so tests for those live elsewhere."""
    from fastapi import FastAPI

    from nightcrate.main import lifespan

    test_app = FastAPI()
    with patch(
        "nightcrate.db.workspace_upgrade.load_all",
        side_effect=ValueError("Malformed seed CSV"),
    ):
        # Should not raise — a data-level seed failure is non-fatal.
        async with lifespan(test_app):
            pass


@pytest.mark.anyio
async def test_lifespan_seed_coding_bug_propagates(configured_db):
    """A coding bug (not a data/OS error) should crash startup loudly so we
    catch it in development instead of swallowing it as a warning."""
    from fastapi import FastAPI

    from nightcrate.main import lifespan

    test_app = FastAPI()
    with patch(
        "nightcrate.db.workspace_upgrade.load_all",
        side_effect=TypeError("Missing positional arg"),
    ):
        with pytest.raises(TypeError, match="Missing positional arg"):
            async with lifespan(test_app):
                pass
