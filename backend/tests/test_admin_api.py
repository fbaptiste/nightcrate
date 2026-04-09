"""Tests for the admin API endpoints."""

from pathlib import Path

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


# ---------------------------------------------------------------------------
# GET /api/admin/info
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_admin_info(client):
    resp = await client.get("/api/admin/info")
    assert resp.status_code == 200
    data = resp.json()
    assert "config_file" in data
    assert "app_data_dir" in data
    assert "backend_root" in data
    assert "seed_data_dir" in data
    assert "python_version" in data
    assert data["python_version"].startswith("3.")


# ---------------------------------------------------------------------------
# GET /api/admin/status (unconfigured)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_admin_status_unconfigured(client):
    resp = await client.get("/api/admin/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["db_configured"] is False
    assert data["active_db"] is None
    assert data["known_databases"] == []


# ---------------------------------------------------------------------------
# GET /api/health
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_health_includes_db_configured(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "db_configured" in data
    assert data["status"] == "ok"
    assert "version" in data


# ---------------------------------------------------------------------------
# POST /api/admin/database/setup (first run)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_setup_first_run(client, tmp_path):
    db_path = str(tmp_path / "test_setup.db")
    resp = await client.post(
        "/api/admin/database/setup",
        json={"path": db_path, "name": "Test Setup DB"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["path"] == db_path
    assert data["name"] == "Test Setup DB"
    assert data["available"] is True
    assert data["size_bytes"] is not None
    assert Path(db_path).is_file()


# ---------------------------------------------------------------------------
# POST /api/admin/database/setup — rejects if already configured
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_setup_rejects_if_configured(client, tmp_path):
    db_path = str(tmp_path / "test_setup_dup.db")
    # First call should succeed
    resp1 = await client.post(
        "/api/admin/database/setup",
        json={"path": db_path, "name": "First"},
    )
    assert resp1.status_code == 200

    # Second call should be rejected with 409
    db_path2 = str(tmp_path / "test_setup_dup2.db")
    resp2 = await client.post(
        "/api/admin/database/setup",
        json={"path": db_path2, "name": "Second"},
    )
    assert resp2.status_code == 409


# ---------------------------------------------------------------------------
# POST /api/admin/database/create
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_create_database(client, tmp_path):
    db_path = str(tmp_path / "test_create.db")
    resp = await client.post(
        "/api/admin/database/create",
        json={"path": db_path, "name": "New DB"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["path"] == db_path
    assert data["name"] == "New DB"
    assert data["available"] is True
    assert Path(db_path).is_file()

    # Should NOT be set as active
    status = await client.get("/api/admin/status")
    status_data = status.json()
    assert status_data["active_db"] is None or status_data["active_db"]["path"] != db_path
    # But should be in known databases
    known_paths = [d["path"] for d in status_data["known_databases"]]
    assert db_path in known_paths


# ---------------------------------------------------------------------------
# POST /api/admin/database/activate
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_activate_database(client, tmp_path):
    # First create a database
    db_path = str(tmp_path / "test_activate.db")
    create_resp = await client.post(
        "/api/admin/database/create",
        json={"path": db_path, "name": "To Activate"},
    )
    assert create_resp.status_code == 200

    # Now activate it
    activate_resp = await client.post(
        "/api/admin/database/activate",
        json={"path": db_path},
    )
    assert activate_resp.status_code == 200
    data = activate_resp.json()
    assert data["path"] == db_path
    assert data["available"] is True

    # Status should reflect the active database
    status = await client.get("/api/admin/status")
    status_data = status.json()
    assert status_data["db_configured"] is True
    assert status_data["active_db"]["path"] == db_path


# ---------------------------------------------------------------------------
# POST /api/admin/database/activate — unknown path
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_activate_unknown_path(client, tmp_path):
    db_path = str(tmp_path / "nonexistent.db")
    resp = await client.post(
        "/api/admin/database/activate",
        json={"path": db_path},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/admin/database/activate — file missing
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_activate_missing_file(client, tmp_path, monkeypatch):
    # Manually add a path to config without creating the file
    from nightcrate.core.app_config import DatabaseEntry, load_config, save_config

    db_path = str(tmp_path / "missing.db")
    config = load_config()
    config.databases[db_path] = DatabaseEntry(name="Missing")
    save_config(config)

    resp = await client.post(
        "/api/admin/database/activate",
        json={"path": db_path},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# DELETE /api/admin/database
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_remove_database(client, tmp_path):
    # Create a database
    db_path = str(tmp_path / "test_remove.db")
    await client.post(
        "/api/admin/database/create",
        json={"path": db_path, "name": "To Remove"},
    )

    # Remove it
    resp = await client.request(
        "DELETE",
        "/api/admin/database",
        json={"path": db_path},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Should be gone from known databases
    status = await client.get("/api/admin/status")
    known_paths = [d["path"] for d in status.json()["known_databases"]]
    assert db_path not in known_paths

    # File should still exist on disk
    assert Path(db_path).is_file()


# ---------------------------------------------------------------------------
# DELETE /api/admin/database — cannot remove active
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_remove_active_rejected(client, tmp_path):
    db_path = str(tmp_path / "test_remove_active.db")
    setup_resp = await client.post(
        "/api/admin/database/setup",
        json={"path": db_path, "name": "Active DB"},
    )
    assert setup_resp.status_code == 200

    resp = await client.request(
        "DELETE",
        "/api/admin/database",
        json={"path": db_path},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/admin/status — shows unavailable when file deleted
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_status_shows_unavailable(client, tmp_path):
    db_path = str(tmp_path / "test_unavailable.db")
    # Create database in known list without activating
    await client.post(
        "/api/admin/database/create",
        json={"path": db_path, "name": "Soon Gone"},
    )

    # Delete the file
    Path(db_path).unlink()

    status = await client.get("/api/admin/status")
    status_data = status.json()
    known = {d["path"]: d for d in status_data["known_databases"]}
    assert db_path in known
    assert known[db_path]["available"] is False
    assert known[db_path]["size_bytes"] is None


# ---------------------------------------------------------------------------
# GET /api/admin/browse
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_browse(client, tmp_path):
    # Create a subdirectory and a .db file inside tmp_path
    sub = tmp_path / "subdir"
    sub.mkdir()
    db_file = tmp_path / "test.db"
    db_file.write_bytes(b"SQLite format 3\x00")
    txt_file = tmp_path / "readme.txt"
    txt_file.write_text("hello")

    resp = await client.get(f"/api/admin/browse?path={tmp_path}")
    assert resp.status_code == 200
    data = resp.json()
    assert "path" in data
    assert "dirs" in data
    assert "files" in data

    dir_names = [d["name"] for d in data["dirs"]]
    assert "subdir" in dir_names

    file_names = [f["name"] for f in data["files"]]
    assert "test.db" in file_names
    # .txt should be excluded
    assert "readme.txt" not in file_names

    # Each file has size
    db_entry = next(f for f in data["files"] if f["name"] == "test.db")
    assert "size" in db_entry
    assert db_entry["size"] > 0
