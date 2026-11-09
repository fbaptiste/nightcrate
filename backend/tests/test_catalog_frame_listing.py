"""Catalog frame-list contracts used by the Files table."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.db.session import get_db
from nightcrate.main import app

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


async def _project(*, display_tz: str | None = None, geo_tz: str | None = None) -> int:
    async with get_db() as conn:
        location_id = None
        if display_tz is not None:
            cursor = await conn.execute(
                "INSERT INTO location (name, latitude, longitude, timezone, geo_timezone) "
                "VALUES ('Frame listing site', 40, -74, ?, ?)",
                (display_tz, geo_tz),
            )
            location_id = cursor.lastrowid
        cursor = await conn.execute(
            "INSERT INTO project (name, location_id) VALUES ('Frame listing', ?)",
            (location_id,),
        )
        await conn.commit()
        return cursor.lastrowid


async def _frame(
    project_id: int,
    label: str,
    date_obs: str,
    *,
    background: float | None = None,
) -> int:
    async with get_db() as conn:
        cursor = await conn.execute(
            "INSERT INTO sub_frame "
            "(project_id, content_hash, frame_type, exposure_seconds, gain, binning_x, "
            "binning_y, date_obs_utc, filter_name_hint, background_adu) "
            "VALUES (?, ?, 'light', 60, 100, 1, 1, ?, 'Ha', ?)",
            (project_id, f"hash-{label}", date_obs, background),
        )
        frame_id = cursor.lastrowid
        await conn.execute(
            "INSERT INTO file_location (project_id, path, category, sub_frame_id) "
            "VALUES (?, ?, 'sub_frame', ?)",
            (project_id, f"/synthetic/{label}.fits", frame_id),
        )
        await conn.commit()
        return frame_id


async def _listing(client: AsyncClient, project_id: int, **params) -> dict:
    response = await client.get(f"/api/projects/{project_id}/catalog/frames", params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def test_observing_nights_match_derived_batches_across_dst(client: AsyncClient):
    project_id = await _project(display_tz="UTC", geo_tz="America/New_York")
    before_noon = await _frame(project_id, "0130", "2026-11-01T05:30:00Z")
    after_noon = await _frame(project_id, "1300", "2026-11-01T18:00:00Z")

    page = await _listing(client, project_id, sort="date")
    assert page["timezone"] == "UTC", "display timezone remains separate from night grouping"
    assert {row["id"]: row["observing_night"] for row in page["rows"]} == {
        before_noon: "2026-10-31",
        after_noon: "2026-11-01",
    }

    derived = await client.post(f"/api/projects/{project_id}/sessions/derive")
    assert derived.status_code == 200, derived.text
    sessions = await client.get(f"/api/projects/{project_id}/sessions")
    assert sessions.status_code == 200, sessions.text
    assert {row["session_date"] for row in sessions.json()} == {"2026-10-31", "2026-11-01"}

    corrected = await client.patch(
        f"/api/projects/{project_id}/catalog/frames/{before_noon}/classification",
        json={"frame_type": "light"},
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["observing_night"] == "2026-10-31"


async def test_capture_time_sorts_instants_and_pages_without_duplicates(client: AsyncClient):
    project_id = await _project()
    at_13_first = await _frame(project_id, "13-first", "2026-10-15T13:00:00")
    at_11 = await _frame(project_id, "11-z", "2026-10-15T11:00:00Z")
    at_14 = await _frame(project_id, "14-space", "2026-10-15 14:00:00")
    at_13_second = await _frame(project_id, "13-second", "2026-10-15T13:00:00")
    invalid = await _frame(project_id, "invalid", "not-a-timestamp")

    ascending = []
    for offset in (0, 2, 4):
        page = await _listing(client, project_id, sort="date", limit=2, offset=offset)
        ascending.extend(row["id"] for row in page["rows"])
    assert ascending == [at_11, at_13_first, at_13_second, at_14, invalid]
    assert len(ascending) == len(set(ascending)) == 5

    descending = []
    for offset in (0, 2, 4):
        page = await _listing(client, project_id, sort="date_desc", limit=2, offset=offset)
        descending.extend(row["id"] for row in page["rows"])
    assert descending == [at_14, at_13_second, at_13_first, at_11, invalid]
    invalid_row = next(row for row in page["rows"] if row["id"] == invalid)
    assert invalid_row["observing_night"] is None


async def test_background_ascending_keeps_missing_values_last(client: AsyncClient):
    project_id = await _project()
    bright = await _frame(project_id, "bright", "2026-10-15T03:00:00Z", background=1200)
    dark = await _frame(project_id, "dark", "2026-10-15T04:00:00Z", background=400)
    missing = await _frame(project_id, "missing", "2026-10-15T05:00:00Z")

    page = await _listing(client, project_id, sort="background_asc")
    assert [row["id"] for row in page["rows"]] == [dark, bright, missing]
