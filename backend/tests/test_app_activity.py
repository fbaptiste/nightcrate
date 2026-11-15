from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from nightcrate.api import app_activity, ingest
from nightcrate.core import runtime
from nightcrate.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def reset_admission():
    runtime.admitted_work = 0
    runtime.install_owner = None
    runtime.install_lease_until = None
    runtime.install_barrier = False
    yield
    runtime.admitted_work = 0
    runtime.install_owner = None
    runtime.install_lease_until = None
    runtime.install_barrier = False


@pytest.mark.anyio
async def test_empty_activity_and_reservation_owner():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/app/activity")).json() == {"running": []}
        first = await client.post("/api/app/install-reservation")
        assert first.status_code == 200
        token = first.json()["token"]
        second = await client.post("/api/app/install-reservation")
        assert second.status_code == 409
        assert second.json() == {"install_in_progress": True}
        assert (
            await client.delete("/api/app/install-reservation", params={"token": "wrong"})
        ).status_code == 204
        assert runtime.install_owner == token
        assert (
            await client.delete("/api/app/install-reservation", params={"token": token})
        ).status_code == 204


@pytest.mark.anyio
async def test_lease_lapse_and_barrier(monkeypatch):
    now = runtime.utcnow()
    monkeypatch.setattr(runtime, "utcnow", lambda: now)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = (await client.post("/api/app/install-reservation")).json()["token"]
        now += timedelta(seconds=30)
        assert (
            await client.put("/api/app/install-reservation", params={"token": token})
        ).status_code == 204
        assert (
            await client.post("/api/app/install-barrier", params={"token": token})
        ).status_code == 204
        now += timedelta(minutes=10)
        assert runtime.install_is_reserved()


@pytest.mark.anyio
async def test_each_running_signal_has_exact_activity(monkeypatch):
    monkeypatch.setattr(app_activity.solve_operations, "active_operation", lambda: None)
    monkeypatch.setattr(app_activity.catalog_progress, "snapshot", lambda: None)
    monkeypatch.setattr(app_activity.star_fetch, "current_operation", lambda: None)
    monkeypatch.setattr(app_activity, "_project_name", AsyncMock(return_value="NGC 7000"))

    await ingest._INGEST_LOCK.acquire()
    ingest._active_ingest_project_id = 12
    try:
        assert [item.model_dump() for item in await app_activity.running_activity()] == [
            {"kind": "scan", "label": "NGC 7000"}
        ]
    finally:
        ingest._active_ingest_project_id = None
        ingest._INGEST_LOCK.release()

    await ingest._ANALYZE_LOCK.acquire()
    try:
        assert [item.kind for item in await app_activity.running_activity()] == ["frame_analysis"]
    finally:
        ingest._ANALYZE_LOCK.release()

    monkeypatch.setattr(app_activity.solve_operations, "active_operation", lambda: object())
    assert [item.kind for item in await app_activity.running_activity()] == ["plate_solve"]
    monkeypatch.setattr(app_activity.solve_operations, "active_operation", lambda: None)
    monkeypatch.setattr(
        app_activity.catalog_progress,
        "snapshot",
        lambda: {"outcome": None, "source": "openngc"},
    )
    assert [item.model_dump() for item in await app_activity.running_activity()] == [
        {"kind": "catalog", "label": "OpenNGC"}
    ]
    monkeypatch.setattr(app_activity.catalog_progress, "snapshot", lambda: None)
    monkeypatch.setattr(
        app_activity.star_fetch,
        "current_operation",
        lambda: SimpleNamespace(state="running"),
    )
    assert [item.kind for item in await app_activity.running_activity()] == ["star_catalog"]


@pytest.mark.anyio
async def test_reservation_refuses_work_routes_until_released():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = (await client.post("/api/app/install-reservation")).json()["token"]
        ingest_response = await client.post("/api/projects/999999/ingest")
        star_response = await client.post("/api/admin/star-catalog/download")
        assert ingest_response.status_code == 409
        assert ingest_response.json()["detail"] == "NightCrate is installing an update."
        assert star_response.status_code == 409
        await client.delete("/api/app/install-reservation", params={"token": token})
        after_release = await client.post("/api/projects/999999/ingest")
        assert after_release.json().get("detail") != "NightCrate is installing an update."


@pytest.mark.anyio
async def test_scan_blocks_reservation_with_project_label(monkeypatch):
    monkeypatch.setattr(app_activity, "_project_name", AsyncMock(return_value="NGC 7000"))
    await ingest._INGEST_LOCK.acquire()
    ingest._active_ingest_project_id = 12
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/app/install-reservation")
        assert response.status_code == 409
        assert response.json() == {"running": [{"kind": "scan", "label": "NGC 7000"}]}
    finally:
        ingest._active_ingest_project_id = None
        ingest._INGEST_LOCK.release()


@pytest.mark.anyio
async def test_admitted_request_blocks_reservation():
    admitted = app_activity.admit_work()
    await anext(admitted)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.post("/api/app/install-reservation")).status_code == 409
    finally:
        await admitted.aclose()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post("/api/app/install-reservation")).status_code == 200


@pytest.mark.anyio
async def test_lapsed_lease_refuses_barrier_and_barrier_outlives_lease(monkeypatch):
    now = runtime.utcnow()
    monkeypatch.setattr(runtime, "utcnow", lambda: now)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        old = (await client.post("/api/app/install-reservation")).json()["token"]
        now += timedelta(seconds=121)
        admitted = app_activity.admit_work()
        await anext(admitted)
        try:
            assert (
                await client.post("/api/app/install-barrier", params={"token": old})
            ).status_code == 409
        finally:
            await admitted.aclose()
        current = (await client.post("/api/app/install-reservation")).json()["token"]
        assert (
            await client.post("/api/app/install-barrier", params={"token": current})
        ).status_code == 204
        now += timedelta(minutes=10)
        blocked = app_activity.admit_work()
        with pytest.raises(HTTPException, match="NightCrate is installing an update"):
            await anext(blocked)
