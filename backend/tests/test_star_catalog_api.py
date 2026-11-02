import asyncio
import threading
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nightcrate.api import star_catalog
from nightcrate.core import app_config
from nightcrate.db.session import get_db_path
from nightcrate.services.star_catalog import fetch, index, index_build, ranges, store
from nightcrate.services.star_catalog.store import AlreadyInstalled


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(star_catalog.router)
    return TestClient(app)


def _configure_database(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    database = workspace / "nightcrate.db"
    database.touch()
    monkeypatch.setattr(
        star_catalog,
        "load_config",
        lambda: SimpleNamespace(active_db=str(workspace)),
    )
    return database


def test_status_not_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)

    async def no_rigs():
        return []

    monkeypatch.setattr(star_catalog, "_rig_coverage", no_rigs)
    response = _client().get("/api/admin/star-catalog/status")
    assert response.status_code == 200
    body = response.json()
    assert body["installed"] is None
    assert all(item["state"] == "not_built" for item in body["ranges"])
    assert [(item["id"], item["name"], item["recommended"]) for item in body["ranges"]] == [
        ("0.4-10", "Standard", True),
        ("0.2-0.4", "Narrow fields", False),
    ]
    assert body["ranges"][0]["build_memory_bytes"] == 3_200_000_000


def test_unconfigured_status_skips_database_quietly(tmp_path, monkeypatch, caplog):
    legacy_db = tmp_path / "Default" / "nightcrate.db"
    legacy_db.parent.mkdir()
    legacy_db.write_bytes(b"legacy database")
    monkeypatch.setattr(
        star_catalog,
        "load_config",
        lambda: SimpleNamespace(active_db=None),
    )

    def database_must_not_open(*_args, **_kwargs):
        raise AssertionError("unconfigured status opened the database")

    monkeypatch.setattr(star_catalog.aiosqlite, "connect", database_must_not_open)
    caplog.set_level("WARNING")
    for _ in range(2):
        response = _client().get("/api/admin/star-catalog/status")
        assert response.status_code == 200
        assert all(not item["rigs"] for item in response.json()["ranges"])
    assert legacy_db.read_bytes() == b"legacy database"
    assert "failed to load rig coverage" not in caplog.text


def test_configured_missing_database_warns_once_without_traceback(tmp_path, monkeypatch, caplog):
    workspace = tmp_path / "missing-workspace"
    workspace.mkdir()
    missing_db = workspace / "nightcrate.db"
    monkeypatch.setattr(
        star_catalog,
        "load_config",
        lambda: SimpleNamespace(active_db=str(workspace)),
    )

    def database_must_not_open(*_args, **_kwargs):
        raise AssertionError("missing configured database was opened")

    monkeypatch.setattr(star_catalog.aiosqlite, "connect", database_must_not_open)
    caplog.set_level("WARNING")
    response = _client().get("/api/admin/star-catalog/status")

    assert response.status_code == 200
    assert all(not item["rigs"] for item in response.json()["ranges"])
    assert not missing_db.exists()
    warnings = [
        record
        for record in caplog.records
        if "configured database is missing" in record.getMessage()
    ]
    assert len(warnings) == 1
    assert warnings[0].exc_info is None


@pytest.mark.asyncio
async def test_status_tracks_current_and_waiting_build_ranges(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)
    standard_entered = threading.Event()
    release_standard = threading.Event()
    narrow_entered = threading.Event()
    release_narrow = threading.Event()

    async def no_rigs():
        return []

    async def settings():
        return SimpleNamespace(max_worker_cores=1)

    def build(name, *, on_progress, **_kwargs):
        output = store.staging_dir() / f"build-{name}" / f"{name}.ncidx"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"index")
        if name == "q256":
            on_progress(0.25)
            standard_entered.set()
            release_standard.wait(timeout=5)
        elif name == "q004":
            on_progress(0.5)
            narrow_entered.set()
            release_narrow.wait(timeout=5)
        else:
            on_progress(1.0)
        return output

    monkeypatch.setattr(star_catalog, "_rig_coverage", no_rigs)
    monkeypatch.setattr(star_catalog, "built_ranges", ranges.read_manifest)
    monkeypatch.setattr(index_build, "build_layer", build)
    monkeypatch.setattr(index_build, "get_settings", settings)
    operation = fetch.start_build(["0.2-0.4", "0.4-10"])
    while not standard_entered.is_set():
        await asyncio.sleep(0)

    status = await star_catalog.get_status()
    standard, narrow = status.ranges
    standard_total = sum(
        ranges.LAYERS[name].estimated_bytes for name in ranges.FIELD_RANGES[0].layers
    )
    assert standard.state == "building"
    assert standard.progress == pytest.approx(
        0.25 * ranges.LAYERS["q256"].estimated_bytes / standard_total
    )
    assert narrow.state == "waiting"
    assert narrow.progress is None

    release_standard.set()
    while not narrow_entered.is_set():
        await asyncio.sleep(0)
    status = await star_catalog.get_status()
    standard, narrow = status.ranges
    assert standard.state == "built"
    assert standard.progress is None
    assert narrow.state == "building"
    assert narrow.progress == pytest.approx(0.5)

    release_narrow.set()
    await fetch._task
    assert operation.state == "done"
    fetch._operation = None
    fetch._task = None


def test_download_returns_operation_and_busy_409(monkeypatch):
    operation = fetch.StarOperation(kind="download", phase="downloading")
    monkeypatch.setattr(fetch, "start_download", lambda: operation)
    response = _client().post("/api/admin/star-catalog/download")
    assert response.status_code == 202
    assert response.json()["kind"] == "download"

    def busy():
        raise fetch.StarOperationBusy

    monkeypatch.setattr(fetch, "start_download", busy)
    response = _client().post("/api/admin/star-catalog/download")
    assert response.status_code == 409
    assert response.json()["detail"] == "Another star-data task is running."


def test_download_when_installed_422(monkeypatch):
    def already():
        raise AlreadyInstalled

    monkeypatch.setattr(fetch, "start_download", already)
    response = _client().post("/api/admin/star-catalog/download")
    assert response.status_code == 422
    assert response.json()["detail"] == (
        "The plate-solving stars are already installed. Remove them first to "
        "download or import again."
    )


def test_import_from_star_data_folder_422(tmp_path, monkeypatch):
    source = tmp_path / "catalog.bz2"
    source.write_bytes(b"catalog")
    monkeypatch.setattr(
        fetch,
        "start_import",
        lambda _path: (_ for _ in ()).throw(
            ValueError("Choose a copy outside NightCrate's star-data folder.")
        ),
    )

    response = _client().post("/api/admin/star-catalog/import", json={"path": str(source)})

    assert response.status_code == 422
    assert response.json()["detail"] == "Choose a copy outside NightCrate's star-data folder."


def test_build_unknown_range_422():
    response = _client().post(
        "/api/admin/star-catalog/ranges/build", json={"range_ids": ["unknown"]}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_build_filters_built_range_while_solve_holds_publication(tmp_path, monkeypatch):
    await fetch.shutdown()
    fetch._operation = None
    fetch._task = None
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)
    standard, narrow = ranges.FIELD_RANGES
    for name in standard.layers:
        ranges.layer_path(name).parent.mkdir(parents=True, exist_ok=True)
        ranges.layer_path(name).write_bytes(b"ready")
    ranges.write_manifest({standard.id})

    def layer_state(name):
        return "ready" if ranges.layer_path(name).is_file() else "missing"

    narrow_built = threading.Event()

    def build(name, *, on_progress, **_kwargs):
        output = store.staging_dir() / f"build-{name}" / f"{name}.ncidx"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"ready")
        on_progress(1.0)
        narrow_built.set()
        return output

    async def settings():
        return SimpleNamespace(max_worker_cores=1)

    async def no_rigs():
        return []

    monkeypatch.setattr(index, "layer_state", layer_state)
    monkeypatch.setattr(index_build, "layer_state", layer_state)
    monkeypatch.setattr(index_build, "build_layer", build)
    monkeypatch.setattr(index_build, "get_settings", settings)
    monkeypatch.setattr(index_build.shutil, "disk_usage", lambda _: SimpleNamespace(free=10**12))
    monkeypatch.setattr(star_catalog, "_rig_coverage", no_rigs)

    app = FastAPI()
    app.include_router(star_catalog.router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        async with star_catalog.plate_solve.solve_slot():
            response = await client.post(
                "/api/admin/star-catalog/ranges/build",
                json={"range_ids": [standard.id, narrow.id]},
            )
            assert response.status_code == 202
            assert response.json()["ranges"] == [narrow.id]
            while not narrow_built.is_set():
                await asyncio.sleep(0)
            status = (await client.get("/api/admin/star-catalog/status")).json()
            assert [item["state"] for item in status["ranges"]] == ["built", "building"]

        await fetch._task
        response = await client.post(
            "/api/admin/star-catalog/ranges/build", json={"range_ids": [standard.id]}
        )
        assert response.status_code == 422
        assert response.json()["detail"] == "Those ranges are already built."

    fetch._operation = None
    fetch._task = None


@pytest.mark.asyncio
async def test_status_reports_ready_current_range_as_built(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)
    standard = ranges.FIELD_RANGES[0]

    async def no_rigs():
        return []

    operation = fetch.StarOperation(
        kind="build",
        phase="building",
        ranges=[standard.id],
        current_range=standard.id,
    )
    monkeypatch.setattr(star_catalog, "_rig_coverage", no_rigs)
    monkeypatch.setattr(star_catalog, "built_ranges", lambda: {standard.id})
    monkeypatch.setattr(fetch, "current_operation", lambda: operation)

    status = await star_catalog.get_status()

    assert status.ranges[0].state == "built"
    assert status.ranges[0].progress is None


def test_delete_range_409_while_solving(monkeypatch):
    @asynccontextmanager
    async def occupied():
        raise star_catalog.plate_solve.SolveSlotBusy(
            "A plate solve is running. Try again when it finishes."
        )
        yield

    monkeypatch.setattr(star_catalog.plate_solve, "solve_slot", occupied)
    response = _client().delete("/api/admin/star-catalog/ranges/0.4-10")
    assert response.status_code == 409
    assert response.json()["detail"] == ("A plate solve is running. Try again when it finishes.")


def test_delete_all_reports_operation(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)
    fetch._operation = None
    response = _client().delete("/api/admin/star-catalog/")
    assert response.status_code == 200
    assert response.json()["kind"] == "remove"


def test_rig_coverage(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)
    configured_db = _configure_database(tmp_path, monkeypatch)

    class Connection:
        async def execute_fetchall(self, query):
            assert "active = 1 AND is_mine = 1" in query
            return [
                {
                    "id": 1,
                    "name": "400 mm rig",
                    "effective_focal_length_mm": 400.0,
                    "pixel_size_um": 3.76,
                    "sensor_resolution_x": 6248,
                    "sensor_resolution_y": 4176,
                    "sensor_width_mm": None,
                    "sensor_height_mm": None,
                }
            ]

    @asynccontextmanager
    async def database(path):
        assert path == configured_db
        yield Connection()

    monkeypatch.setattr(star_catalog.aiosqlite, "connect", database)
    ranges = _client().get("/api/admin/star-catalog/status").json()["ranges"]
    covered = [item["id"] for item in ranges if item["rigs"]]
    assert covered == ["0.4-10"]
    assert ranges[0]["rigs"][0]["field_deg"] == pytest.approx(3.36, abs=0.01)


def test_rig_coverage_uses_solve_dialog_linear_field(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)
    configured_db = _configure_database(tmp_path, monkeypatch)

    class Connection:
        async def execute_fetchall(self, _query):
            return [
                {
                    "id": 1,
                    "name": "6.4 degree rig",
                    "effective_focal_length_mm": 206.265,
                    "pixel_size_um": 4.0,
                    "sensor_resolution_x": 5760,
                    "sensor_resolution_y": 4000,
                }
            ]

    @asynccontextmanager
    async def database(path):
        assert path == configured_db
        yield Connection()

    monkeypatch.setattr(star_catalog.aiosqlite, "connect", database)
    ranges = _client().get("/api/admin/star-catalog/status").json()["ranges"]
    covered = [item for item in ranges if item["rigs"]]

    assert [item["id"] for item in covered] == ["0.4-10"]
    assert covered[0]["rigs"][0]["field_deg"] == pytest.approx(6.4, abs=1e-9)


def test_rig_coverage_uses_two_choice_boundaries(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)
    configured_db = _configure_database(tmp_path, monkeypatch)

    class Connection:
        async def execute_fetchall(self, _query):
            return [
                {
                    "id": index,
                    "name": f"{field_deg} degree rig",
                    "effective_focal_length_mm": 206.265,
                    "pixel_size_um": 1.0,
                    "sensor_resolution_x": int(field_deg * 3600),
                    "sensor_resolution_y": 100,
                }
                for index, field_deg in enumerate((0.3, 0.4, 2.0, 10.0), start=1)
            ]

    @asynccontextmanager
    async def database(path):
        assert path == configured_db
        yield Connection()

    monkeypatch.setattr(star_catalog.aiosqlite, "connect", database)
    choices = _client().get("/api/admin/star-catalog/status").json()["ranges"]

    assert [rig["field_deg"] for rig in choices[0]["rigs"]] == [0.4, 2.0, 10.0]
    assert [rig["field_deg"] for rig in choices[1]["rigs"]] == [0.3]


@pytest.mark.asyncio
async def test_build_allowed_while_solving_publication_waits(monkeypatch):
    await fetch.shutdown()
    fetch._operation = None
    fetch._task = None
    published = asyncio.Event()

    async def worker():
        async with fetch.publish_lock():
            published.set()

    def start_build(range_ids):
        return fetch._claim(
            fetch.StarOperation(kind="build", phase="building", ranges=range_ids),
            worker,
        )

    monkeypatch.setattr(fetch, "start_build", start_build)
    async with star_catalog.plate_solve.solve_slot():
        operation = await star_catalog.build_ranges(star_catalog.BuildRequest(range_ids=["0.4-10"]))
        await asyncio.sleep(0)
        assert operation.state == "running"
        assert not published.is_set()
    await fetch._task
    assert published.is_set()
    assert operation.state == "done"


def test_rig_coverage_lists_only_my_rigs(tmp_path, monkeypatch):
    """Seeded all-in-one smart telescopes appear only once marked as mine."""
    import sqlite3

    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)
    monkeypatch.setattr(
        star_catalog,
        "load_config",
        lambda: SimpleNamespace(active_db=str(tmp_path)),
    )
    monkeypatch.setattr(star_catalog, "workspace_db_path", lambda _workspace: get_db_path())
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    seeded = conn.execute(
        "SELECT id, name FROM rig_summary "
        "WHERE source = 'seed' AND active = 1 AND is_mine = 0 "
        "AND effective_focal_length_mm IS NOT NULL ORDER BY id"
    ).fetchall()
    assert seeded, "the seed data should include all-in-one smart telescopes"
    seeded_names = {row["name"] for row in seeded}

    def listed_names() -> set[str]:
        ranges = _client().get("/api/admin/star-catalog/status").json()["ranges"]
        return {rig["name"] for item in ranges for rig in item["rigs"]}

    try:
        assert not listed_names() & seeded_names
        conn.execute("UPDATE rig SET is_mine = 1 WHERE id = ?", (seeded[0]["id"],))
        conn.commit()
        assert seeded[0]["name"] in listed_names()
    finally:
        conn.execute("UPDATE rig SET is_mine = 0 WHERE id = ?", (seeded[0]["id"],))
        conn.commit()
        conn.close()
