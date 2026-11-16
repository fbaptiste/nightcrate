"""API behavior while an active workspace is blocked."""

import shutil
import sqlite3
from pathlib import Path

import aiosqlite
import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.core.app_config import AppConfig, DatabaseEntry, load_config, save_config
from nightcrate.db import workspace_upgrade as upgrade
from nightcrate.db.session import get_db_path, set_workspace_problem, workspace_problem
from nightcrate.db.workspace_upgrade import WorkspaceProblem
from nightcrate.main import app, lifespan


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_blocked_workspace_keeps_health_and_admin_available(tmp_path, monkeypatch):
    workspace = tmp_path / "broken"
    monkeypatch.setattr(upgrade, "load_all", lambda *_args: None)
    monkeypatch.setattr(upgrade, "load_catalogs", lambda *_args: None)
    upgrade.initialize_workspace(workspace, "Broken", "1.0")
    db = workspace / "nightcrate.db"
    save_config(
        AppConfig(
            databases={str(workspace): DatabaseEntry(name="Broken")},
            active_db=str(workspace),
        )
    )
    problem = WorkspaceProblem(
        kind="upgrade_failed",
        workspace_path=str(workspace),
        workspace_name="Broken",
        last_opened_by="0.52.0",
        error="RuntimeError: migration failed",
        backup_path=str(workspace / "backups" / "before.db"),
    )
    set_workspace_problem(problem)
    sync_calls = []
    async_calls = []
    real_sync_connect = sqlite3.connect
    real_async_connect = aiosqlite.connect

    def sync_connect(database, *args, **kwargs):
        sync_calls.append(Path(str(database)).resolve())
        return real_sync_connect(database, *args, **kwargs)

    def async_connect(database, *args, **kwargs):
        async_calls.append(Path(database).resolve())
        return real_async_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", sync_connect)
    monkeypatch.setattr(aiosqlite, "connect", async_connect)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        health = (await client.get("/api/health")).json()
        assert health["db_configured"] is False
        assert health["workspace_problem"]["kind"] == "upgrade_failed"
        assert (await client.get("/api/projects")).status_code == 409
        assert (await client.get("/api/admin/status")).status_code == 200
        catalog = await client.get("/api/admin/star-catalog/status")
        assert catalog.status_code == 200
        assert all(item["rigs"] == [] for item in catalog.json()["ranges"])
    assert db.resolve() not in sync_calls
    assert db.resolve() not in async_calls


def test_problem_path_is_temporary(tmp_path):
    assert Path(tmp_path).is_dir()


def _problem(tmp_path):
    return WorkspaceProblem(
        kind="unreadable",
        workspace_path=str(tmp_path / "old"),
        workspace_name="Old",
        last_opened_by=None,
        error="bad database",
        backup_path=None,
    )


@pytest.mark.anyio
async def test_setup_allowed_while_blocked(tmp_path):
    set_workspace_problem(_problem(tmp_path))
    workspace = tmp_path / "replacement"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/admin/database/setup",
            json={"path": str(workspace), "name": "Replacement"},
        )
    assert response.status_code == 200
    assert workspace_problem() is None
    assert get_db_path() == workspace / "nightcrate.db"


@pytest.mark.anyio
async def test_activating_another_workspace_clears_problem(tmp_path):
    set_workspace_problem(_problem(tmp_path))
    workspace = tmp_path / "another"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/admin/database/create",
            json={"path": str(workspace), "name": "Another"},
        )
        assert created.status_code == 200
        activated = await client.post("/api/admin/database/activate", json={"path": str(workspace)})
    assert activated.status_code == 200
    assert workspace_problem() is None


@pytest.mark.anyio
async def test_admin_activation_failure_keeps_previous(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        setup = await client.post(
            "/api/admin/database/setup", json={"path": str(first), "name": "First"}
        )
        assert setup.status_code == 200
        created = await client.post(
            "/api/admin/database/create", json={"path": str(second), "name": "Second"}
        )
        assert created.status_code == 200
        with sqlite3.connect(second / "nightcrate.db") as conn:
            conn.execute(
                "INSERT INTO _yoyo_migration VALUES (?, ?, datetime('now'))",
                ("future-hash", "9999.future"),
            )
        response = await client.post("/api/admin/database/activate", json={"path": str(second)})
    assert response.status_code == 409
    assert response.json()["detail"]["problem"]["kind"] == "newer"
    assert load_config().active_db == str(first)
    assert get_db_path() == first / "nightcrate.db"


@pytest.mark.anyio
async def test_startup_failure_blocks_database(tmp_path, monkeypatch):
    workspace = tmp_path / "startup failure"
    monkeypatch.setattr(upgrade, "load_all", lambda *_args: None)
    monkeypatch.setattr(upgrade, "load_catalogs", lambda *_args: None)
    upgrade.initialize_workspace(workspace, "Broken", "1.0")
    save_config(
        AppConfig(
            databases={str(workspace): DatabaseEntry(name="Broken")},
            active_db=str(workspace),
        )
    )
    migrations = tmp_path / "bad-migrations"
    shutil.copytree(upgrade.MIGRATIONS_DIR, migrations)
    (migrations / "9999.fail.sql").write_text("THIS IS NOT SQL;", encoding="utf-8")
    monkeypatch.setattr(upgrade, "MIGRATIONS_DIR", migrations)

    async with lifespan(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            health = (await client.get("/api/health")).json()
            assert health["db_configured"] is False
            assert health["workspace_problem"]["kind"] == "upgrade_failed"
            assert (await client.get("/api/projects")).status_code == 409
            assert (await client.get("/api/admin/status")).status_code == 200
            catalog = await client.get("/api/admin/star-catalog/status")
            assert catalog.status_code == 200
            assert all(item["rigs"] == [] for item in catalog.json()["ranges"])


@pytest.mark.anyio
async def test_recovery_failure_health_and_admin_remain_available(tmp_path):
    workspace = tmp_path / "corrupt startup"
    workspace.mkdir()
    db = workspace / "nightcrate.db"
    db.write_bytes(b"not a sqlite database")
    Path(f"{db}-journal").write_bytes(b"hot journal")
    save_config(
        AppConfig(
            databases={str(workspace): DatabaseEntry(name="Corrupt")},
            active_db=str(workspace),
        )
    )

    async with lifespan(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            health = await client.get("/api/health")
            assert health.status_code == 200
            assert health.json()["workspace_problem"]["kind"] == "unreadable"
            assert health.json()["db_configured"] is False
            assert (await client.get("/api/admin/status")).status_code == 200
