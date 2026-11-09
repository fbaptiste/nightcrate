"""API coverage for durable per-observing-night project notes."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.db.session import get_db
from nightcrate.main import app
from tests.frame_library import build_usage_library

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


async def _project(client: AsyncClient, name: str) -> int:
    response = await client.post("/api/projects", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _save(client: AsyncClient, project_id: int, night: str, notes: str):
    return await client.put(
        f"/api/projects/{project_id}/night-notes/{night}",
        json={"notes": notes},
    )


async def test_create_update_trim_and_list_newest_first(client: AsyncClient):
    project_id = await _project(client, "Night notes")
    first = await _save(client, project_id, "2026-10-14", "  Clear after midnight.  ")
    assert first.status_code == 200, first.text
    assert first.json()["notes"] == "Clear after midnight."

    second = await _save(client, project_id, "2026-10-15", "Thin cloud early.")
    assert second.status_code == 200, second.text

    async with get_db() as conn:
        await conn.execute(
            "UPDATE project_night_note SET updated_at = '2000-01-01 00:00:00' "
            "WHERE project_id = ? AND night_date = '2026-10-14'",
            (project_id,),
        )
        await conn.commit()

    updated = await _save(client, project_id, "2026-10-14", "Excellent seeing.")
    assert updated.status_code == 200, updated.text
    assert updated.json()["notes"] == "Excellent seeing."
    assert updated.json()["updated_at"] != "2000-01-01 00:00:00"

    listing = await client.get(f"/api/projects/{project_id}/night-notes")
    assert listing.status_code == 200, listing.text
    assert [(row["night_date"], row["notes"]) for row in listing.json()] == [
        ("2026-10-15", "Thin cloud early."),
        ("2026-10-14", "Excellent seeing."),
    ]


@pytest.mark.parametrize("night", ["2026-02-30", "2026-W01-1"])
async def test_put_and_delete_reject_non_round_trip_dates(client: AsyncClient, night: str):
    project_id = await _project(client, f"Invalid {night}")
    assert (await _save(client, project_id, night, "Nope")).status_code == 422
    assert (
        await client.delete(f"/api/projects/{project_id}/night-notes/{night}")
    ).status_code == 422


@pytest.mark.parametrize("notes", ["", "   ", "x" * 10_001])
async def test_note_length_is_checked_after_trimming(client: AsyncClient, notes: str):
    project_id = await _project(client, f"Length {len(notes)}")
    assert (await _save(client, project_id, "2026-10-15", notes)).status_code == 422


async def test_unknown_project_is_404(client: AsyncClient):
    assert (await client.get("/api/projects/999999/night-notes")).status_code == 404
    assert (await _save(client, 999999, "2026-10-15", "No project")).status_code == 404


async def test_delete_missing_and_project_isolation(client: AsyncClient):
    first = await _project(client, "First notes")
    second = await _project(client, "Second notes")
    assert (await _save(client, first, "2026-10-15", "Only on first")).status_code == 200

    listing = await client.get(f"/api/projects/{second}/night-notes")
    assert listing.status_code == 200
    assert listing.json() == []
    assert (
        await client.delete(f"/api/projects/{second}/night-notes/2026-10-15")
    ).status_code == 404

    deleted = await client.delete(f"/api/projects/{first}/night-notes/2026-10-15")
    assert deleted.status_code == 204
    assert (await client.get(f"/api/projects/{first}/night-notes")).json() == []
    assert (await client.delete(f"/api/projects/{first}/night-notes/2026-10-15")).status_code == 404


async def test_project_hard_delete_cascades_notes(client: AsyncClient):
    project_id = await _project(client, "Cascade notes")
    assert (await _save(client, project_id, "2026-10-15", "Temporary")).status_code == 200
    async with get_db() as conn:
        await conn.execute("PRAGMA foreign_keys = ON")
        await conn.execute("DELETE FROM project WHERE id = ?", (project_id,))
        await conn.commit()
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM project_night_note WHERE project_id = ?", (project_id,)
        )
        assert (await cursor.fetchone())[0] == 0


async def test_derive_and_removing_every_frame_leave_note_untouched(client: AsyncClient):
    library = await build_usage_library(project_count=1)
    project_id = library.project_ids[0]
    night = "2026-09-30"
    assert (await _save(client, project_id, night, "Keep through rebuilds")).status_code == 200

    first_derive = await client.post(f"/api/projects/{project_id}/sessions/derive")
    assert first_derive.status_code == 200, first_derive.text
    async with get_db() as conn:
        await conn.execute("DELETE FROM sub_frame WHERE project_id = ?", (project_id,))
        await conn.commit()
    second_derive = await client.post(f"/api/projects/{project_id}/sessions/derive")
    assert second_derive.status_code == 200, second_derive.text

    listing = await client.get(f"/api/projects/{project_id}/night-notes")
    assert listing.status_code == 200
    assert listing.json()[0]["night_date"] == night
    assert listing.json()[0]["notes"] == "Keep through rebuilds"
