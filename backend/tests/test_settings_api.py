"""Settings API tests for atomic partial updates."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.core.config import Settings, update_settings
from nightcrate.db.session import get_db
from nightcrate.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


async def _rows() -> list[tuple]:
    async with get_db() as conn:
        cursor = await conn.execute("SELECT key, value_json, updated_at FROM settings ORDER BY key")
        return [tuple(row) for row in await cursor.fetchall()]


async def _replace_rows(values: dict[str, object]) -> None:
    async with get_db() as conn:
        await conn.execute("DELETE FROM settings")
        await conn.executemany(
            "INSERT INTO settings (key, value_json, updated_at) VALUES (?, ?, ?)",
            [(key, json.dumps(value), "2000-01-01 00:00:00") for key, value in values.items()],
        )
        await conn.commit()


@pytest.mark.anyio
async def test_patch_writes_only_given_keys(client):
    await update_settings(Settings(theme="dark"))
    async with get_db() as conn:
        await conn.execute("UPDATE settings SET updated_at = '2000-01-01 00:00:00'")
        await conn.commit()
    before = {row[0]: row for row in await _rows()}

    response = await client.patch("/api/settings", json={"gallery_slideshow_seconds": 10})

    assert response.status_code == 200
    assert response.json()["theme"] == "dark"
    assert response.json()["gallery_slideshow_seconds"] == 10
    after = {row[0]: row for row in await _rows()}
    assert after["gallery_slideshow_seconds"] != before["gallery_slideshow_seconds"]
    assert {key: row for key, row in after.items() if key != "gallery_slideshow_seconds"} == {
        key: row for key, row in before.items() if key != "gallery_slideshow_seconds"
    }


@pytest.mark.anyio
async def test_every_successful_patch_survives_reload(client):
    cases = [
        (
            {
                "scoring_threshold_excellent": 50,
                "scoring_threshold_good": 60,
                "scoring_threshold_fair": 40,
                "scoring_weight_moon": 4.0,
            },
            {"scoring_threshold_excellent": 90},
            (90, 60, 40),
        ),
        (
            {
                "scoring_threshold_excellent": 50,
                "scoring_threshold_good": 45,
                "scoring_threshold_fair": 60,
            },
            {"scoring_threshold_fair": 30},
            (80, 60, 30),
        ),
        (
            {"theme": "dark", "gallery_slideshow_seconds": 5},
            {"gallery_slideshow_seconds": 8},
            (80, 60, 40),
        ),
    ]
    for stored, patch, thresholds in cases:
        await _replace_rows(stored)
        response = await client.patch("/api/settings", json=patch)
        assert response.status_code == 200, response.text
        reloaded = await client.get("/api/settings")
        assert reloaded.json() == response.json()
        assert (
            response.json()["scoring_threshold_excellent"],
            response.json()["scoring_threshold_good"],
            response.json()["scoring_threshold_fair"],
        ) == thresholds


@pytest.mark.anyio
async def test_unrelated_patch_keeps_damaged_rows_untouched(client):
    damaged = {
        "scoring_threshold_excellent": 50,
        "scoring_threshold_good": 60,
        "scoring_threshold_fair": 40,
        "scoring_weight_moon": 4.0,
        "browser_favorites": [
            {"name": "valid", "path": "/valid"},
            {"name": "missing path"},
        ],
    }
    await _replace_rows(damaged)
    before = await _rows()
    response = await client.patch("/api/settings", json={"gallery_view": "large"})
    assert response.status_code == 200
    assert response.json()["gallery_view"] == "large"
    after = await _rows()
    assert [row for row in after if row[0] != "gallery_view"] == before


@pytest.mark.anyio
async def test_threshold_patch_over_damaged_trio_saves_what_is_seen(client):
    await _replace_rows(
        {
            "scoring_threshold_excellent": 50,
            "scoring_threshold_good": 60,
            "scoring_threshold_fair": 40,
            "scoring_weight_moon": 4.0,
        }
    )
    response = await client.patch("/api/settings", json={"scoring_threshold_excellent": 90})
    assert response.status_code == 200
    assert (
        response.json()["scoring_threshold_excellent"],
        response.json()["scoring_threshold_good"],
        response.json()["scoring_threshold_fair"],
    ) == (90, 60, 40)
    assert response.json()["scoring_weight_moon"] == 4.0

    await _replace_rows(
        {
            "scoring_threshold_excellent": 90,
            "scoring_threshold_good": 95,
            "scoring_threshold_fair": 85,
        }
    )
    before = await _rows()
    rejected = await client.patch("/api/settings", json={"scoring_threshold_good": 87})
    assert rejected.status_code == 422
    assert await _rows() == before
    visible = (await client.get("/api/settings")).json()
    assert (
        visible["scoring_threshold_excellent"],
        visible["scoring_threshold_good"],
        visible["scoring_threshold_fair"],
    ) == (80, 60, 40)


@pytest.mark.anyio
async def test_concurrent_patches_keep_cross_field_rule(client, monkeypatch):
    await _replace_rows(
        {
            "scoring_threshold_excellent": 80,
            "scoring_threshold_good": 60,
            "scoring_threshold_fair": 40,
        }
    )
    statements: list[str] = []
    began = asyncio.Event()
    original_get_db = get_db

    class RecordingConnection:
        def __init__(self, connection):
            self._connection = connection

        def __getattr__(self, name):
            return getattr(self._connection, name)

        async def execute(self, statement, parameters=None):
            statements.append(statement)
            if statement == "BEGIN IMMEDIATE":
                began.set()
            if parameters is None:
                return await self._connection.execute(statement)
            return await self._connection.execute(statement, parameters)

    @asynccontextmanager
    async def recording_get_db():
        async with original_get_db() as connection:
            yield RecordingConnection(connection)

    monkeypatch.setattr("nightcrate.core.config.get_db", recording_get_db)
    async with original_get_db() as writer:
        await writer.execute("BEGIN IMMEDIATE")
        await writer.execute(
            "UPDATE settings SET value_json = '70' WHERE key = 'scoring_threshold_excellent'"
        )
        request = asyncio.create_task(
            client.patch("/api/settings", json={"scoring_threshold_good": 75})
        )
        await asyncio.wait_for(began.wait(), timeout=2)
        assert statements[0] == "BEGIN IMMEDIATE"
        assert not any("SELECT" in statement for statement in statements)
        await writer.commit()

    response = await request
    assert response.status_code == 422
    async with original_get_db() as conn:
        rows = await (
            await conn.execute(
                "SELECT key, value_json FROM settings "
                "WHERE key LIKE 'scoring_threshold_%' ORDER BY key"
            )
        ).fetchall()
    assert {row["key"]: json.loads(row["value_json"]) for row in rows} == {
        "scoring_threshold_excellent": 70,
        "scoring_threshold_fair": 40,
        "scoring_threshold_good": 60,
    }


@pytest.mark.anyio
async def test_partial_saves_from_two_clients_keep_both(client):
    assert (
        await client.patch("/api/settings", json={"gallery_slideshow_seconds": 8})
    ).status_code == 200
    assert (await client.patch("/api/settings", json={"gallery_view": "large"})).status_code == 200
    loaded = (await client.get("/api/settings")).json()
    assert loaded["gallery_slideshow_seconds"] == 8
    assert loaded["gallery_view"] == "large"


@pytest.mark.anyio
async def test_patch_unknown_key_422(client):
    before = await _rows()
    response = await client.patch("/api/settings", json={"nope": 1})
    assert response.status_code == 422
    assert "nope" in response.json()["detail"]
    assert await _rows() == before


@pytest.mark.anyio
async def test_patch_invalid_value_422(client):
    before = await _rows()
    response = await client.patch("/api/settings", json={"gallery_slideshow_seconds": 7})
    assert response.status_code == 422
    assert "Input should be" in response.json()["detail"]
    assert await _rows() == before


@pytest.mark.anyio
async def test_patch_scoring_order_422(client):
    before = await _rows()
    response = await client.patch("/api/settings", json={"scoring_threshold_good": 90})
    assert response.status_code == 422
    assert "must hold" in response.json()["detail"]
    assert await _rows() == before


@pytest.mark.anyio
async def test_patch_gpu_acceleration_applies(client, monkeypatch):
    calls: list[bool] = []
    monkeypatch.setattr("nightcrate.api.settings.set_gpu_enabled", calls.append)
    response = await client.patch("/api/settings", json={"gpu_acceleration": False})
    assert response.status_code == 200
    assert calls == [False]


@pytest.mark.anyio
async def test_put_whole_object_still_works(client):
    payload = Settings(theme="dark", gallery_slideshow_seconds=15).model_dump(mode="json")
    response = await client.put("/api/settings", json=payload)
    assert response.status_code == 200
    assert response.json() == payload
    assert (await client.get("/api/settings")).json() == payload
