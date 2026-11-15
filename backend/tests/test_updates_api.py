import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.api import updates
from nightcrate.core import runtime
from nightcrate.core.updates_state import (
    LatestApp,
    UpdatesState,
    load_updates_state,
    save_updates_state,
)
from nightcrate.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


@pytest.fixture(autouse=True)
def reset_update_globals():
    updates._check_task = None
    saved_kind = runtime.install_kind
    runtime.install_kind = "source"
    yield
    updates._check_task = None
    runtime.install_kind = saved_kind


@pytest.mark.anyio
async def test_404_means_no_update(client, monkeypatch):
    response = httpx.Response(404, request=httpx.Request("GET", updates.update_check.MANIFEST_URL))
    monkeypatch.setattr(updates.update_check.http_client, "get", AsyncMock(return_value=response))
    monkeypatch.setattr(
        updates.remote,
        "fetch_latest_release",
        AsyncMock(return_value=SimpleNamespace(tag_name="2026-11-02")),
    )
    checked = await client.post("/api/updates/check")
    assert checked.status_code == 200
    assert checked.json()["last_error"] is None
    assert checked.json()["notices"] == []


@pytest.mark.anyio
async def test_manifest_and_release_metadata_are_combined(monkeypatch):
    fixtures = Path(__file__).parent / "fixtures" / "updates"
    manifest = json.loads((fixtures / "latest.json").read_text(encoding="utf-8"))
    release = json.loads((fixtures / "release.json").read_text(encoding="utf-8"))
    responses = [
        httpx.Response(200, json=manifest, request=httpx.Request("GET", "https://manifest")),
        httpx.Response(200, json=release, request=httpx.Request("GET", "https://release")),
    ]
    monkeypatch.setattr(
        updates.update_check.http_client,
        "get",
        AsyncMock(side_effect=responses),
    )
    latest = await updates.update_check.fetch_latest_app()
    assert latest is not None
    assert latest.version == "0.55.0"
    assert latest.release_version == "0.55.0"
    assert latest.notes == ["First change", "Second change", "Third change", "Fourth change"]
    assert latest.platforms == ["darwin-aarch64", "windows-x86_64", "linux-x86_64"]


@pytest.mark.anyio
async def test_failure_records_attempt_and_manual_check_runs_when_off(client, monkeypatch):
    save_updates_state(UpdatesState(check_automatically=False))
    monkeypatch.setattr(
        updates.update_check,
        "fetch_latest_app",
        AsyncMock(side_effect=updates.update_check.UpdateCheckError("couldn't reach GitHub")),
    )
    response = await client.post("/api/updates/check")
    assert response.status_code == 200
    body = response.json()
    assert body["last_attempt_at"] is not None
    assert body["last_error"] == "couldn't reach GitHub"
    assert body["check_due"] is False


@pytest.mark.anyio
async def test_concurrent_checks_share_fetch(client, monkeypatch):
    gate = asyncio.Event()

    async def fetch():
        await gate.wait()
        return None

    mock = AsyncMock(side_effect=fetch)
    monkeypatch.setattr(updates.update_check, "fetch_latest_app", mock)
    first = asyncio.create_task(client.post("/api/updates/check"))
    second = asyncio.create_task(client.post("/api/updates/check"))
    await asyncio.sleep(0)
    gate.set()
    assert (await first).status_code == 200
    assert (await second).status_code == 200
    assert mock.await_count == 1


@pytest.mark.anyio
async def test_preference_change_during_check_survives(client, monkeypatch):
    save_updates_state(UpdatesState(check_automatically=True))
    entered = asyncio.Event()
    release = asyncio.Event()

    async def fetch():
        entered.set()
        await release.wait()
        return None

    monkeypatch.setattr(updates.update_check, "fetch_latest_app", fetch)
    check = asyncio.create_task(client.post("/api/updates/check"))
    await entered.wait()
    changed = await client.patch("/api/updates/preferences", json={"check_automatically": False})
    assert changed.status_code == 200
    release.set()
    assert (await check).status_code == 200
    assert load_updates_state().check_automatically is False


@pytest.mark.anyio
async def test_seen_version_and_invalid_notice_action(client, monkeypatch):
    monkeypatch.setattr(runtime, "app_version", lambda: "0.55.0")
    save_updates_state(UpdatesState(last_run_version="0.54.0"))
    assert (await client.get("/api/updates")).json()["updated_from"] == "0.54.0"
    assert (await client.post("/api/updates/seen-version")).status_code == 204
    assert (await client.get("/api/updates")).json()["updated_from"] is None
    invalid = await client.post("/api/updates/notices/openngc", json={"action": "later"})
    assert invalid.status_code == 422


@pytest.mark.anyio
async def test_every_allowed_notice_action_and_clear_skip(client):
    latest = LatestApp(
        version="0.55.0",
        release_version="0.55.0",
        release_url="https://example.test",
        platforms=[],
    )
    save_updates_state(UpdatesState(latest_app=latest, latest_openngc_tag="2026-11-02"))
    assert (
        await client.post("/api/updates/notices/app", json={"action": "later"})
    ).status_code == 200
    assert load_updates_state().app_later_until is not None
    assert (
        await client.post("/api/updates/notices/app", json={"action": "skip"})
    ).status_code == 200
    assert load_updates_state().skipped_app_version == "0.55.0"
    assert (await client.delete("/api/updates/skipped-version")).status_code == 204
    assert load_updates_state().skipped_app_version is None
    assert (
        await client.post("/api/updates/notices/openngc", json={"action": "skip"})
    ).status_code == 200
    assert load_updates_state().skipped_openngc_release == "2026-11-02"
    for notice_id in ("mgc50_age", "wikidata_age", "wikidata_query"):
        response = await client.post(f"/api/updates/notices/{notice_id}", json={"action": "remind"})
        assert response.status_code == 200
        assert notice_id in load_updates_state().remind_after


@pytest.mark.anyio
async def test_first_run_version_is_recorded_once(monkeypatch):
    monkeypatch.setattr(runtime, "app_version", lambda: "0.54.0")
    await updates.record_first_run_version()
    assert load_updates_state().last_run_version == "0.54.0"
    monkeypatch.setattr(runtime, "app_version", lambda: "0.55.0")
    await updates.record_first_run_version()
    assert load_updates_state().last_run_version == "0.54.0"
