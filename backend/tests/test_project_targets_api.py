"""Tests for v0.38.0 manual project ↔ DSO target endpoints."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.db.session import get_db
from nightcrate.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _make_project(client: AsyncClient, name: str = "Targets Project") -> int:
    r = await client.post("/api/projects", json={"name": name})
    assert r.status_code == 201
    return r.json()["id"]


async def _make_dso(name: str = "Test Galaxy") -> int:
    # The seeded DSO catalog isn't loaded in tests; insert minimal rows so the
    # targets endpoints have something to reference.
    async with get_db() as conn:
        await conn.execute(
            "INSERT OR IGNORE INTO dso_catalog_source"
            " (id, source_id, category, display_name, file_path, file_hash)"
            " VALUES (1, 'test-src', 'nightcrate', 'Test', '/tmp/x', 'abc')",
        )
        cursor = await conn.execute(
            "INSERT INTO dso (primary_designation, obj_type, ra_deg, dec_deg,"
            " source_catalog_id, source_row_hash, active)"
            " VALUES (?, 'G', 210.8, 54.3, 1, 'hash', 1)",
            (name,),
        )
        await conn.commit()
        return cursor.lastrowid


class TestProjectTargets:
    async def test_empty_list(self, client: AsyncClient):
        pid = await _make_project(client)
        r = await client.get(f"/api/projects/{pid}/targets")
        assert r.status_code == 200
        assert r.json() == []

    async def test_add_and_list(self, client: AsyncClient):
        pid = await _make_project(client)
        dso_id = await _make_dso("Test Gxy A")
        r = await client.post(f"/api/projects/{pid}/targets", json={"dso_id": dso_id})
        assert r.status_code == 201
        body = r.json()
        assert body["dso_id"] == dso_id
        assert body["primary_designation"] == "Test Gxy A"

        rows = (await client.get(f"/api/projects/{pid}/targets")).json()
        assert len(rows) == 1
        assert rows[0]["dso_id"] == dso_id

    async def test_duplicate_409(self, client: AsyncClient):
        pid = await _make_project(client)
        dso_id = await _make_dso("Test Gxy B")
        await client.post(f"/api/projects/{pid}/targets", json={"dso_id": dso_id})
        r2 = await client.post(f"/api/projects/{pid}/targets", json={"dso_id": dso_id})
        assert r2.status_code == 409

    async def test_invalid_dso_404(self, client: AsyncClient):
        pid = await _make_project(client)
        r = await client.post(f"/api/projects/{pid}/targets", json={"dso_id": 99999})
        assert r.status_code == 404

    async def test_invalid_project_404(self, client: AsyncClient):
        dso_id = await _make_dso("Test Gxy C")
        r = await client.post("/api/projects/99999/targets", json={"dso_id": dso_id})
        assert r.status_code == 404

    async def test_delete(self, client: AsyncClient):
        pid = await _make_project(client)
        dso_id = await _make_dso("Test Gxy D")
        await client.post(f"/api/projects/{pid}/targets", json={"dso_id": dso_id})
        r = await client.delete(f"/api/projects/{pid}/targets/{dso_id}")
        assert r.status_code == 204
        assert (await client.get(f"/api/projects/{pid}/targets")).json() == []

    async def test_delete_missing_404(self, client: AsyncClient):
        pid = await _make_project(client)
        r = await client.delete(f"/api/projects/{pid}/targets/99999")
        assert r.status_code == 404

    async def test_targets_cascade_on_project_delete(self, client: AsyncClient):
        pid = await _make_project(client)
        dso_id = await _make_dso("Test Gxy E")
        await client.post(f"/api/projects/{pid}/targets", json={"dso_id": dso_id})
        await client.delete(f"/api/projects/{pid}/permanent")
        async with get_db() as conn:
            cur = await conn.execute(
                "SELECT COUNT(*) c FROM project_target WHERE project_id = ?", (pid,)
            )
            assert (await cur.fetchone())["c"] == 0
