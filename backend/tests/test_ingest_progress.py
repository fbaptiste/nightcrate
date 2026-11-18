"""Progress registry and responsive ingest API tests."""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from aiosqlite import Connection
from httpx import ASGITransport, AsyncClient

from nightcrate.api import ingest
from nightcrate.db.session import get_db, workspace_key
from nightcrate.main import app
from nightcrate.services import ingest_progress
from nightcrate.services.ingest_classify import CATEGORY_SUB
from nightcrate.services.ingest_models import IngestStatus
from nightcrate.services.ingest_scanner import ScanEntry, ScanReport
from tests.catalog_helpers import _make_project, _seed_rig, _write_fits


@pytest.fixture(autouse=True)
def _clear_progress():
    ingest_progress.reset()
    yield
    ingest_progress.reset()


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


def _status(project_id: int = 1, run_id: int = 2, status: str = "completed") -> IngestStatus:
    return IngestStatus(run_id=run_id, project_id=project_id, status=status)


def _entry(path: str) -> ScanEntry:
    return ScanEntry(
        path=path,
        name=Path(path).name,
        category=CATEGORY_SUB,
        size_bytes=1,
        mtime="2026-11-15T00:00:00Z",
    )


async def _wait_for(predicate, *, timeout: float = 10.0):
    async with asyncio.timeout(timeout):
        while True:
            value = predicate()
            if value:
                return value
            await asyncio.sleep(0.01)


async def _latest_run(project_id: int) -> dict:
    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT * FROM ingestion_run WHERE project_id = ? ORDER BY id DESC LIMIT 1",
            (project_id,),
        )
        row = await cursor.fetchone()
    assert row is not None
    return dict(row)


async def _frames(project_id: int) -> list[dict]:
    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT sf.id, sf.rig_id, fl.path FROM sub_frame sf "
            "JOIN file_location fl ON fl.sub_frame_id = sf.id "
            "WHERE sf.project_id = ? ORDER BY fl.path",
            (project_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]


async def _auto_sessions(project_id: int) -> list[dict]:
    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT * FROM project_session WHERE project_id = ? AND source = 'auto' ORDER BY id",
            (project_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]


async def _completed_rigged_scan(
    client: AsyncClient, tmp_path: Path, monkeypatch, name: str
) -> tuple[int, int, Path]:
    project_id = await _make_project(client, name)
    rig_id = await _seed_rig(f"{name} rig")
    folder = tmp_path / name
    folder.mkdir()
    _write_fits(folder / "light-1.fits")
    _write_fits(folder / "light-2.fits")
    bound = await client.post(
        f"/api/projects/{project_id}/folders",
        json={"path": str(folder), "rig_id": rig_id},
    )
    assert bound.status_code == 201, bound.text
    monkeypatch.setattr(ingest, "make_pool", lambda _workers: None)
    response = await client.post(f"/api/projects/{project_id}/ingest")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"
    assert {row["rig_id"] for row in await _frames(project_id)} == {rig_id}
    return project_id, rig_id, folder


def test_registry_retains_recent_paths_per_workspace_and_project(monkeypatch, tmp_path: Path):
    now = [100.0]
    monkeypatch.setattr(ingest_progress, "_clock", lambda: now[0])
    folder = tmp_path / "data"
    ingest_progress.start("w1", 1, 10)
    ingest_progress.folder(str(folder))
    for index in range(12):
        ingest_progress.file_read(str(folder / f"file-{index}.fits"), index != 4)

    running = ingest_progress.snapshot("w1", 1)
    assert running is not None
    assert running["done"] == 12
    assert [item["path"] for item in running["recent"]] == [
        f"file-{index}.fits" for index in range(2, 12)
    ]
    assert ingest_progress.snapshot("w1", 2) is None
    assert ingest_progress.snapshot("w2", 1) is None

    ingest_progress.folder(str(folder / "next"))
    assert ingest_progress.snapshot("w1", 1)["recent"] == []
    assert ingest_progress.snapshot("w1", 1)["done"] == 0
    ingest_progress.finish(_status(run_id=10))
    finished = ingest_progress.snapshot("w1", 1)
    assert finished["running"] is False
    assert finished["result"].status == "completed"

    ingest_progress.start("w1", 2, 20)
    assert ingest_progress.snapshot("w1", 1)["result"].run_id == 10
    assert ingest_progress.snapshot("w1", 2)["running"] is True
    ingest_progress.finish(_status(project_id=2, run_id=20))
    ingest_progress.start("w1", 1, 11)
    assert ingest_progress.snapshot("w1", 1)["run_id"] == 11
    archive = str(folder / "archive.zip")
    ingest_progress.folder(archive)
    ingest_progress.file_read(f"{archive}::Lights/a.fits", True)
    assert ingest_progress.snapshot("w1", 1)["recent"] == [{"path": "Lights/a.fits", "ok": True}]
    ingest_progress.folder(f"{archive}::Lights")
    ingest_progress.file_read(f"{archive}::Lights/Ha/b.fits", True)
    assert ingest_progress.snapshot("w1", 1)["recent"] == [{"path": "Ha/b.fits", "ok": True}]
    ingest_progress.finish(_status(run_id=11))
    now[0] += ingest_progress.RETAIN_FINISHED_S
    assert ingest_progress.snapshot("w1", 1) is None


@pytest.mark.anyio
async def test_pool_callbacks_report_completion_order_and_preserve_result_order(
    monkeypatch, tmp_path: Path
):
    folder = tmp_path / "data"
    paths = [str(folder / f"{index}.fits") for index in range(3)]
    gates = {path: threading.Event() for path in paths}

    def parse(path: str) -> dict:
        assert gates[path].wait(10)
        return {"path": path}

    monkeypatch.setattr(ingest, "parse_image_file", parse)
    ingest_progress.start("w", 1, 1)
    ingest_progress.folder(str(folder))
    with ThreadPoolExecutor(max_workers=3) as pool:
        task = asyncio.create_task(ingest._parse_in_pool([_entry(path) for path in paths], pool))
        for index in (2, 0, 1):
            gates[paths[index]].set()
            await _wait_for(
                lambda index=index: (
                    ingest_progress.snapshot("w", 1)["done"] >= (2, 0, 1).index(index) + 1
                )
            )
        results = await task

    assert [result["path"] for result in results] == paths
    assert [item["path"] for item in ingest_progress.snapshot("w", 1)["recent"]] == [
        "2.fits",
        "0.fits",
        "1.fits",
    ]


@pytest.mark.anyio
async def test_parser_errors_are_reported_and_executor_exceptions_propagate(monkeypatch):
    ingest_progress.start("w", 1, 1)
    ingest_progress.folder("/data")
    monkeypatch.setattr(
        ingest,
        "parse_image_file",
        lambda path: {"path": path, "error": "bad header"},
    )
    result = await ingest._parse_in_pool([_entry("/data/handled.fits")], None)
    assert result[0]["error"] == "bad header"
    assert ingest_progress.snapshot("w", 1)["recent"][-1]["ok"] is False

    def fail(_path: str):
        raise RuntimeError("worker failed")

    monkeypatch.setattr(ingest, "parse_image_file", fail)
    with ThreadPoolExecutor(max_workers=2) as pool:
        with pytest.raises(RuntimeError, match="worker failed"):
            await ingest._parse_in_pool([_entry("/data/a.fits"), _entry("/data/b.fits")], pool)
    assert ingest_progress.snapshot("w", 1)["recent"][-1]["ok"] is False


@pytest.mark.anyio
async def test_listing_is_nonblocking_empty_folder_finishes_and_admission_is_atomic(
    client: AsyncClient, tmp_path: Path, monkeypatch
):
    project_id = await _make_project(client, "Progress listing")
    folder = tmp_path / "empty"
    folder.mkdir()
    assert (
        await client.post(f"/api/projects/{project_id}/folders", json={"path": str(folder)})
    ).status_code == 201
    started = threading.Event()
    release = threading.Event()

    def blocked_scan(_folder: str) -> ScanReport:
        started.set()
        assert release.wait(10)
        return ScanReport([])

    monkeypatch.setattr(ingest, "scan_directory", blocked_scan)
    monkeypatch.setattr(ingest, "make_pool", lambda _workers: None)

    first = asyncio.create_task(client.post(f"/api/projects/{project_id}/ingest"))
    assert await asyncio.to_thread(started.wait, 10)
    progress = await client.get(f"/api/projects/{project_id}/ingest/progress")
    assert progress.status_code == 200
    assert progress.json() | {"scan_id": "ignored"}  # endpoint answered while listing blocked
    assert progress.json()["stage"] == "listing"

    second = await client.post(f"/api/projects/{project_id}/ingest")
    assert second.status_code == 409
    release.set()
    response = await first
    assert response.status_code == 200
    final = (await client.get(f"/api/projects/{project_id}/ingest/progress")).json()
    assert final["running"] is False
    assert final["total"] == 0
    assert final["result"] == response.json()


@pytest.mark.anyio
async def test_inline_reading_saving_and_folder_reset_are_observable(
    client: AsyncClient, tmp_path: Path, monkeypatch
):
    project_id = await _make_project(client, "Progress stages")
    folders = [tmp_path / "one", tmp_path / "two"]
    for folder in folders:
        folder.mkdir()
        assert (
            await client.post(f"/api/projects/{project_id}/folders", json={"path": str(folder)})
        ).status_code == 201

    parse_gates = {str(folder): threading.Event() for folder in folders}
    second_listing = threading.Event()
    release_second_listing = threading.Event()
    saving = asyncio.Event()
    release_saving = asyncio.Event()

    def scan(folder: str) -> ScanReport:
        if folder == str(folders[1]):
            second_listing.set()
            assert release_second_listing.wait(10)
        return ScanReport([_entry(str(Path(folder) / "light.fits"))])

    def parse(path: str) -> dict:
        folder = str(Path(path).parent)
        assert parse_gates[folder].wait(10)
        return {"path": path}

    async def persist(*_args, **_kwargs):
        saving.set()
        await asyncio.wait_for(release_saving.wait(), 10)

    monkeypatch.setattr(ingest, "scan_directory", scan)
    monkeypatch.setattr(ingest, "parse_image_file", parse)
    monkeypatch.setattr(ingest, "_persist_parsed", persist)
    monkeypatch.setattr(ingest, "make_pool", lambda _workers: None)

    task = asyncio.create_task(client.post(f"/api/projects/{project_id}/ingest"))
    await _wait_for(
        lambda: (
            value
            if (value := ingest_progress.snapshot(workspace_key(), project_id))
            and value["stage"] == "reading"
            else None
        )
    )
    assert (await client.get(f"/api/projects/{project_id}/ingest/progress")).json()["total"] == 1
    parse_gates[str(folders[0])].set()
    await asyncio.wait_for(saving.wait(), 10)
    during_save = (await client.get(f"/api/projects/{project_id}/ingest/progress")).json()
    assert during_save["stage"] == "saving"
    assert during_save["recent"] == [{"path": "light.fits", "ok": True}]
    release_saving.set()

    assert await asyncio.to_thread(second_listing.wait, 10)
    second = (await client.get(f"/api/projects/{project_id}/ingest/progress")).json()
    assert second["folder"] == str(folders[1])
    assert second["recent"] == []
    release_second_listing.set()
    parse_gates[str(folders[1])].set()
    response = await task
    assert response.status_code == 200


@pytest.mark.anyio
async def test_failed_and_cancelled_runs_finish_the_progress_record(
    client: AsyncClient, tmp_path: Path, monkeypatch
):
    project_id = await _make_project(client, "Progress failures")
    folder = tmp_path / "files"
    folder.mkdir()
    assert (
        await client.post(f"/api/projects/{project_id}/folders", json={"path": str(folder)})
    ).status_code == 201
    monkeypatch.setattr(
        ingest,
        "scan_directory",
        lambda _folder: ScanReport([_entry("/bad-1.fits"), _entry("/bad-2.fits")]),
    )
    monkeypatch.setattr(ingest, "make_pool", lambda _workers: ThreadPoolExecutor(max_workers=2))
    monkeypatch.setattr(
        ingest,
        "parse_image_file",
        lambda _path: (_ for _ in ()).throw(RuntimeError("executor boom")),
    )
    response = await client.post(f"/api/projects/{project_id}/ingest")
    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert (await client.get(f"/api/projects/{project_id}/ingest/progress")).json()["result"][
        "status"
    ] == "failed"

    listed = threading.Event()
    release = threading.Event()

    def blocked(_folder: str) -> ScanReport:
        listed.set()
        assert release.wait(10)
        return ScanReport([])

    monkeypatch.setattr(ingest, "scan_directory", blocked)
    monkeypatch.setattr(ingest, "make_pool", lambda _workers: None)
    task = asyncio.create_task(client.post(f"/api/projects/{project_id}/ingest"))
    assert await asyncio.to_thread(listed.wait, 10)
    task.cancel()
    await asyncio.sleep(0)
    assert (await client.post(f"/api/projects/{project_id}/ingest")).status_code == 409
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert ingest_progress.snapshot(workspace_key(), project_id)["result"].status == "cancelled"
    assert (await client.post(f"/api/projects/{project_id}/ingest")).status_code == 200


@pytest.mark.anyio
async def test_cancel_during_folder_save_rolls_back_the_folder(
    client: AsyncClient, tmp_path: Path, monkeypatch
):
    project_id = await _make_project(client, "Cancelled folder")
    folder = tmp_path / "cancelled-folder"
    folder.mkdir()
    _write_fits(folder / "light-1.fits")
    _write_fits(folder / "light-2.fits")
    bound = await client.post(f"/api/projects/{project_id}/folders", json={"path": str(folder)})
    assert bound.status_code == 201, bound.text
    monkeypatch.setattr(ingest, "make_pool", lambda _workers: None)
    original_persist = ingest._persist_parsed
    calls = 0

    async def cancel_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise asyncio.CancelledError
        await original_persist(*args, **kwargs)

    monkeypatch.setattr(ingest, "_persist_parsed", cancel_second)

    with pytest.raises(asyncio.CancelledError):
        await client.post(f"/api/projects/{project_id}/ingest")

    assert await _frames(project_id) == []
    assert (await _latest_run(project_id))["status"] == "cancelled"


@pytest.mark.anyio
async def test_cancel_during_grouping_restores_frame_rigs(
    client: AsyncClient, tmp_path: Path, monkeypatch
):
    project_id, rig_id, _folder = await _completed_rigged_scan(
        client, tmp_path, monkeypatch, "cancel-grouping"
    )

    async def cancel_after_clearing(conn, target_project_id: int, _tz_name):
        await conn.execute(
            "UPDATE sub_frame SET rig_id = NULL WHERE project_id = ?", (target_project_id,)
        )
        raise asyncio.CancelledError

    monkeypatch.setattr(ingest, "assign_rigs_and_sessions", cancel_after_clearing)

    with pytest.raises(asyncio.CancelledError):
        await client.post(f"/api/projects/{project_id}/ingest")

    assert {row["rig_id"] for row in await _frames(project_id)} == {rig_id}
    assert (await _latest_run(project_id))["status"] == "cancelled"


@pytest.mark.anyio
async def test_failure_during_grouping_restores_frame_rigs_and_records_error(
    client: AsyncClient, tmp_path: Path, monkeypatch
):
    project_id, rig_id, _folder = await _completed_rigged_scan(
        client, tmp_path, monkeypatch, "failed-grouping"
    )

    async def fail_after_clearing(conn, target_project_id: int, _tz_name):
        await conn.execute(
            "UPDATE sub_frame SET rig_id = NULL WHERE project_id = ?", (target_project_id,)
        )
        raise RuntimeError("grouping failed")

    monkeypatch.setattr(ingest, "assign_rigs_and_sessions", fail_after_clearing)

    response = await client.post(f"/api/projects/{project_id}/ingest")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "failed"
    assert response.json()["first_error"] == "RuntimeError: grouping failed"
    assert {row["rig_id"] for row in await _frames(project_id)} == {rig_id}
    run = await _latest_run(project_id)
    assert run["status"] == "failed"
    assert run["errors_count"] == 1
    assert "RuntimeError: grouping failed" in run["errors_json"]


@pytest.mark.anyio
async def test_cancellation_during_derivation_rolls_back_sessions_with_run(
    client: AsyncClient, tmp_path: Path, monkeypatch
):
    project_id, _rig_id, _folder = await _completed_rigged_scan(
        client, tmp_path, monkeypatch, "cancel-derivation"
    )
    before = await _auto_sessions(project_id)

    async def cancel_after_deleting(conn, target_project_id: int, *, tz_name):
        del tz_name
        await conn.execute(
            "DELETE FROM project_session WHERE project_id = ? AND source = 'auto'",
            (target_project_id,),
        )
        raise asyncio.CancelledError

    monkeypatch.setattr(ingest, "refresh_auto_sessions", cancel_after_deleting)
    with pytest.raises(asyncio.CancelledError):
        await client.post(f"/api/projects/{project_id}/ingest")

    assert await _auto_sessions(project_id) == before
    assert (await _latest_run(project_id))["status"] == "cancelled"


@pytest.mark.anyio
async def test_failure_during_derivation_rolls_back_sessions_with_run(
    client: AsyncClient, tmp_path: Path, monkeypatch
):
    project_id, _rig_id, _folder = await _completed_rigged_scan(
        client, tmp_path, monkeypatch, "failed-derivation"
    )
    before = await _auto_sessions(project_id)

    async def fail_after_deleting(conn, target_project_id: int, *, tz_name):
        del tz_name
        await conn.execute(
            "DELETE FROM project_session WHERE project_id = ? AND source = 'auto'",
            (target_project_id,),
        )
        raise RuntimeError("derivation failed")

    monkeypatch.setattr(ingest, "refresh_auto_sessions", fail_after_deleting)
    response = await client.post(f"/api/projects/{project_id}/ingest")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "failed"
    assert await _auto_sessions(project_id) == before
    assert (await _latest_run(project_id))["status"] == "failed"


@pytest.mark.anyio
async def test_cancel_in_second_folder_preserves_first_folder_commit(
    client: AsyncClient, tmp_path: Path, monkeypatch
):
    project_id = await _make_project(client, "Cancelled second folder")
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    _write_fits(first / "committed.fits")
    _write_fits(second / "rolled-back-1.fits")
    _write_fits(second / "rolled-back-2.fits")
    for folder in (first, second):
        bound = await client.post(f"/api/projects/{project_id}/folders", json={"path": str(folder)})
        assert bound.status_code == 201, bound.text
    monkeypatch.setattr(ingest, "make_pool", lambda _workers: None)
    original_persist = ingest._persist_parsed
    second_calls = 0

    async def cancel_second_file(conn, project_id, run_id, result, counters, geo_tz, bound_folder):
        nonlocal second_calls
        if Path(result["path"]).parent == second:
            second_calls += 1
            if second_calls == 2:
                raise asyncio.CancelledError
        await original_persist(conn, project_id, run_id, result, counters, geo_tz, bound_folder)

    monkeypatch.setattr(ingest, "_persist_parsed", cancel_second_file)

    with pytest.raises(asyncio.CancelledError):
        await client.post(f"/api/projects/{project_id}/ingest")

    assert [Path(row["path"]).name for row in await _frames(project_id)] == ["committed.fits"]
    run = await _latest_run(project_id)
    assert run["status"] == "cancelled"
    assert run["files_scanned"] == 1
    assert run["subs_inserted"] == 1
    assert run["errors_count"] == 0


@pytest.mark.anyio
async def test_timezone_failure_finishes_progress_and_releases_admission(
    client: AsyncClient, tmp_path: Path, monkeypatch
):
    project_id = await _make_project(client, "Progress timezone failure")
    folder = tmp_path / "timezone"
    folder.mkdir()
    assert (
        await client.post(f"/api/projects/{project_id}/folders", json={"path": str(folder)})
    ).status_code == 201
    calls = 0

    async def fail_once(_conn, _project_id: int) -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("timezone failed")
        return "UTC"

    monkeypatch.setattr(ingest, "project_geo_timezone", fail_once)
    monkeypatch.setattr(ingest, "make_pool", lambda _workers: None)

    with pytest.raises(RuntimeError, match="timezone failed"):
        await client.post(f"/api/projects/{project_id}/ingest")
    finished = ingest_progress.snapshot(workspace_key(), project_id)
    assert finished["running"] is False
    assert finished["result"].status == "failed"
    assert finished["result"].first_error == "RuntimeError: timezone failed"

    response = await client.post(f"/api/projects/{project_id}/ingest")
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


@pytest.mark.anyio
async def test_final_update_failure_finishes_progress_and_releases_admission(
    client: AsyncClient, tmp_path: Path, monkeypatch
):
    project_id = await _make_project(client, "Progress final update failure")
    folder = tmp_path / "final-update"
    folder.mkdir()
    assert (
        await client.post(f"/api/projects/{project_id}/folders", json={"path": str(folder)})
    ).status_code == 201
    original_execute = Connection.execute
    fail_final_update = True

    async def execute(conn, sql: str, parameters=None):
        nonlocal fail_final_update
        if fail_final_update and sql.startswith("UPDATE ingestion_run SET status"):
            fail_final_update = False
            raise RuntimeError("final update failed")
        return await original_execute(conn, sql, parameters)

    monkeypatch.setattr(Connection, "execute", execute)
    monkeypatch.setattr(ingest, "make_pool", lambda _workers: None)

    with pytest.raises(RuntimeError, match="final update failed"):
        await client.post(f"/api/projects/{project_id}/ingest")
    finished = ingest_progress.snapshot(workspace_key(), project_id)
    assert finished["running"] is False
    assert finished["result"].status == "failed"
    assert finished["result"].first_error == "RuntimeError: final update failed"

    response = await client.post(f"/api/projects/{project_id}/ingest")
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


@pytest.mark.anyio
async def test_workspace_activation_hides_another_workspaces_finished_scan(
    client: AsyncClient, tmp_path: Path
):
    first_workspace = workspace_key()
    ingest_progress.start(first_workspace, 1, 1)
    ingest_progress.finish(_status())
    second = tmp_path / "second-workspace"
    created = await client.post(
        "/api/admin/database/create", json={"path": str(second), "name": "Second"}
    )
    assert created.status_code == 200, created.text
    activated = await client.post("/api/admin/database/activate", json={"path": str(second)})
    assert activated.status_code == 200, activated.text
    assert workspace_key() != first_workspace
    assert (await client.get("/api/projects/1/ingest/progress")).json() is None


@pytest.mark.anyio
async def test_real_spawn_pool_reports_small_fits_files(client: AsyncClient, tmp_path: Path):
    project_id = await _make_project(client, "Real process progress")
    folder = tmp_path / "real"
    folder.mkdir()
    _write_fits(folder / "light-1.fits")
    _write_fits(folder / "light-2.fits")
    assert (
        await client.post(f"/api/projects/{project_id}/folders", json={"path": str(folder)})
    ).status_code == 201
    response = await client.post(f"/api/projects/{project_id}/ingest")
    assert response.status_code == 200, response.text
    progress = (await client.get(f"/api/projects/{project_id}/ingest/progress")).json()
    assert {item["path"] for item in progress["recent"]} == {"light-1.fits", "light-2.fits"}
    assert all(item["ok"] for item in progress["recent"])
    assert progress["result"] == response.json()
