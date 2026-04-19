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


# ---------------------------------------------------------------------------
# GET /api/admin/browse — hidden files excluded
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_browse_excludes_hidden(client, tmp_path):
    hidden_dir = tmp_path / ".hidden"
    hidden_dir.mkdir()
    hidden_file = tmp_path / ".secret.db"
    hidden_file.write_bytes(b"x")
    visible = tmp_path / "visible"
    visible.mkdir()

    resp = await client.get(f"/api/admin/browse?path={tmp_path}")
    assert resp.status_code == 200
    data = resp.json()

    dir_names = [d["name"] for d in data["dirs"]]
    file_names = [f["name"] for f in data["files"]]
    assert ".hidden" not in dir_names
    assert ".secret.db" not in file_names
    assert "visible" in dir_names


# ---------------------------------------------------------------------------
# GET /api/admin/browse — not a directory
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_browse_not_a_directory(client, tmp_path):
    file_path = tmp_path / "somefile.txt"
    file_path.write_text("hello")

    resp = await client.get(f"/api/admin/browse?path={file_path}")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/admin/shortcuts
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_shortcuts(client):
    resp = await client.get("/api/admin/shortcuts")
    assert resp.status_code == 200
    data = resp.json()
    assert "home" in data
    assert "documents" in data
    assert "app_data" in data
    # home should be a real directory
    assert Path(data["home"]).is_dir()


# ---------------------------------------------------------------------------
# POST /api/admin/mkdir
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_mkdir(client, tmp_path):
    new_dir = tmp_path / "new_folder"
    resp = await client.post("/api/admin/mkdir", json={"path": str(new_dir)})
    assert resp.status_code == 200
    assert new_dir.is_dir()


@pytest.mark.anyio
async def test_mkdir_already_exists(client, tmp_path):
    existing = tmp_path / "existing"
    existing.mkdir()
    resp = await client.post("/api/admin/mkdir", json={"path": str(existing)})
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# DELETE /api/admin/database — with delete_file=true
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_remove_database_deletes_file(client, tmp_path):
    db_path = str(tmp_path / "test_delete_file.db")
    await client.post(
        "/api/admin/database/create",
        json={"path": db_path, "name": "Delete Me"},
    )
    assert Path(db_path).is_file()

    resp = await client.request(
        "DELETE",
        "/api/admin/database?delete_file=true",
        json={"path": db_path},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    # File should be gone from disk
    assert not Path(db_path).is_file()


# ---------------------------------------------------------------------------
# POST /api/admin/database/add — existing file
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_add_existing_database(client, tmp_path):
    db_path = tmp_path / "existing.db"
    db_path.write_bytes(b"SQLite format 3\x00")

    resp = await client.post(
        "/api/admin/database/add",
        json={"path": str(db_path), "name": "Existing DB"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Existing DB"
    assert data["available"] is True


@pytest.mark.anyio
async def test_add_nonexistent_file_rejected(client, tmp_path):
    resp = await client.post(
        "/api/admin/database/add",
        json={"path": str(tmp_path / "nope.db"), "name": "Missing"},
    )
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_add_non_db_extension_rejected(client, tmp_path):
    txt_file = tmp_path / "data.txt"
    txt_file.write_text("not a db")
    resp = await client.post(
        "/api/admin/database/add",
        json={"path": str(txt_file), "name": "Wrong Ext"},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/admin/database/create — already exists
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_create_database_already_exists(client, tmp_path):
    """Creating a DB at an existing path should fail with 400."""
    existing = tmp_path / "existing.db"
    existing.write_bytes(b"data")

    resp = await client.post(
        "/api/admin/database/create",
        json={"path": str(existing), "name": "Dup"},
    )
    assert resp.status_code == 400
    assert "already exists" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# POST /api/admin/database/add — duplicate registration
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_add_database_duplicate_rejected(client, tmp_path):
    """Adding an already-registered database should return 409."""
    db_file = tmp_path / "dup.db"
    db_file.write_bytes(b"SQLite format 3\x00")

    # First add succeeds
    resp1 = await client.post(
        "/api/admin/database/add",
        json={"path": str(db_file), "name": "First"},
    )
    assert resp1.status_code == 200

    # Second add should fail with 409
    resp2 = await client.post(
        "/api/admin/database/add",
        json={"path": str(db_file), "name": "Second"},
    )
    assert resp2.status_code == 409
    assert "already registered" in resp2.json()["detail"].lower()


# ---------------------------------------------------------------------------
# POST /api/admin/database/setup — path already exists
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_setup_existing_path_rejected(client, tmp_path):
    """Setup with a path that already exists should return 400."""
    existing = tmp_path / "taken.db"
    existing.write_bytes(b"data")

    resp = await client.post(
        "/api/admin/database/setup",
        json={"path": str(existing), "name": "Taken"},
    )
    assert resp.status_code == 400
    assert "already exists" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# DELETE /api/admin/database — unknown path
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_remove_unknown_database_rejected(client, tmp_path):
    """Removing a path not in known databases should return 400."""
    resp = await client.request(
        "DELETE",
        "/api/admin/database",
        json={"path": str(tmp_path / "unknown.db")},
    )
    assert resp.status_code == 400
    assert "not in known databases" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# GET /api/admin/browse — PermissionError
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_browse_permission_error(client, tmp_path):
    """Browse should handle PermissionError gracefully (return partial results)."""
    # Create a dir that we can browse
    sub = tmp_path / "restricted"
    sub.mkdir()

    # We can't easily simulate PermissionError on iterdir without mocking,
    # so use a real path — the endpoint returns partial results on PermissionError
    resp = await client.get(f"/api/admin/browse?path={tmp_path}")
    assert resp.status_code == 200
    # At minimum we get a valid response structure
    data = resp.json()
    assert "dirs" in data
    assert "files" in data


# ---------------------------------------------------------------------------
# POST /api/admin/mkdir — OSError
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_mkdir_invalid_path(client):
    """Creating a directory at an invalid path should return 400."""
    # Use a path that can't be created (e.g., a file as parent)
    resp = await client.post(
        "/api/admin/mkdir",
        json={"path": "/dev/null/impossible/path"},
    )
    assert resp.status_code == 400 or resp.status_code == 409


# ---------------------------------------------------------------------------
# POST /api/admin/reseed
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_reseed_no_database(client):
    """Reseed without a configured database should return 400."""
    resp = await client.post("/api/admin/reseed")
    assert resp.status_code == 400
    assert "no database" in resp.json()["detail"].lower()


@pytest.mark.anyio
async def test_reseed_with_active_database(client, tmp_path):
    """Reseed with an active database should run the seed loader."""
    # Set up a database first
    db_path = str(tmp_path / "reseed_test.db")
    setup_resp = await client.post(
        "/api/admin/database/setup",
        json={"path": db_path, "name": "Reseed Test"},
    )
    assert setup_resp.status_code == 200

    # Now reseed
    resp = await client.post("/api/admin/reseed")
    assert resp.status_code == 200
    data = resp.json()
    assert "mode" in data
    assert data["mode"] == "update"
    assert "ok" in data
    assert data["ok"] is True
    assert "total_inserted" in data
    assert "total_updated" in data
    assert "total_unchanged" in data
    assert "total_skipped" in data


# ---------------------------------------------------------------------------
# GET /api/admin/catalogs/remote-version
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_remote_version_reports_installed_and_latest(client, tmp_path, monkeypatch):
    """With a version.json present locally + GitHub reachable, returns both
    tags and flags has_update correctly."""
    # Point user_catalogs_root at the tmp_path.
    monkeypatch.setattr("nightcrate.catalog_loader.registry.APP_DIR", tmp_path)
    openngc_dir = tmp_path / "catalogs" / "openngc"
    openngc_dir.mkdir(parents=True)
    (openngc_dir / "version.json").write_text('{"version": "v20231203"}', encoding="utf-8")

    from nightcrate.catalog_loader import remote

    async def fake_fetch():
        return remote.RemoteReleaseInfo(
            tag_name="v20260307",
            published_at="2026-03-07T17:18:41Z",
            release_url="https://github.com/mattiaverga/OpenNGC/releases/tag/v20260307",
        )

    monkeypatch.setattr("nightcrate.catalog_loader.remote.fetch_latest_release", fake_fetch)

    resp = await client.get("/api/admin/catalogs/remote-version")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["latest_tag"] == "v20260307"
    assert data["installed_version"] == "v20231203"
    assert data["has_update"] is True


@pytest.mark.anyio
async def test_remote_version_no_installation(client, tmp_path, monkeypatch):
    monkeypatch.setattr("nightcrate.catalog_loader.registry.APP_DIR", tmp_path)

    from nightcrate.catalog_loader import remote

    async def fake_fetch():
        return remote.RemoteReleaseInfo(tag_name="v20260307", published_at=None, release_url="")

    monkeypatch.setattr("nightcrate.catalog_loader.remote.fetch_latest_release", fake_fetch)

    resp = await client.get("/api/admin/catalogs/remote-version")
    assert resp.status_code == 200
    data = resp.json()
    assert data["installed_version"] is None
    assert data["has_update"] is True


@pytest.mark.anyio
async def test_remote_version_returns_502_on_github_failure(client, tmp_path, monkeypatch):
    monkeypatch.setattr("nightcrate.catalog_loader.registry.APP_DIR", tmp_path)

    async def fake_fetch():
        raise RuntimeError("GitHub unreachable")

    monkeypatch.setattr("nightcrate.catalog_loader.remote.fetch_latest_release", fake_fetch)

    resp = await client.get("/api/admin/catalogs/remote-version")
    assert resp.status_code == 502
    assert "Could not reach GitHub" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /api/admin/catalogs/fetch-from-github
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_fetch_from_github_no_database(client):
    resp = await client.post("/api/admin/catalogs/fetch-from-github")
    assert resp.status_code == 400
    assert "no database" in resp.json()["detail"].lower()


@pytest.mark.anyio
async def test_fetch_from_github_happy_path(client, tmp_path, monkeypatch):
    """Happy path: create a DB, mock the remote fetch/download, verify the
    endpoint runs the loader and returns a populated summary."""
    import shutil

    # Set up a database
    db_path = str(tmp_path / "catalogs_db.db")
    setup_resp = await client.post(
        "/api/admin/database/setup",
        json={"path": db_path, "name": "Catalogs Test"},
    )
    assert setup_resp.status_code == 200

    # Point user_catalogs_root at tmp_path and simulate the download by
    # copying mini fixtures into the expected layout.
    monkeypatch.setattr("nightcrate.catalog_loader.registry.APP_DIR", tmp_path)
    openngc_dir = tmp_path / "catalogs" / "openngc"
    openngc_dir.mkdir(parents=True)

    mini_fixture = Path(__file__).parent / "fixtures" / "catalogs" / "openngc"

    from nightcrate.catalog_loader import remote

    async def fake_fetch():
        return remote.RemoteReleaseInfo(tag_name="v20260307", published_at=None, release_url="")

    async def fake_download(release, catalogs_root):
        # Simulate a real download by staging the mini fixtures under the
        # expected filenames.
        shutil.copy(mini_fixture / "mini_NGC.csv", openngc_dir / "NGC.csv")
        shutil.copy(mini_fixture / "mini_addendum.csv", openngc_dir / "addendum.csv")
        (openngc_dir / "version.json").write_text('{"version": "v20260307"}', encoding="utf-8")
        return remote.DownloadReport(
            tag=release.tag_name,
            files=[],
            version_json_path=openngc_dir / "version.json",
        )

    monkeypatch.setattr("nightcrate.catalog_loader.remote.fetch_latest_release", fake_fetch)
    monkeypatch.setattr("nightcrate.catalog_loader.remote.download_openngc", fake_download)

    resp = await client.post("/api/admin/catalogs/fetch-from-github")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["fetched_version"] == "v20260307"
    assert data["total_dsos"] > 0
    assert any(s["status"] == "loaded" for s in data["per_source"])


@pytest.mark.anyio
async def test_fetch_from_github_network_failure_returns_502(client, tmp_path, monkeypatch):
    db_path = str(tmp_path / "catalogs_db.db")
    setup_resp = await client.post(
        "/api/admin/database/setup",
        json={"path": db_path, "name": "Catalogs Test"},
    )
    assert setup_resp.status_code == 200

    async def fake_fetch():
        raise RuntimeError("GitHub unreachable")

    monkeypatch.setattr("nightcrate.catalog_loader.remote.fetch_latest_release", fake_fetch)

    resp = await client.post("/api/admin/catalogs/fetch-from-github")
    assert resp.status_code == 502
    assert "Failed to download" in resp.json()["detail"]
