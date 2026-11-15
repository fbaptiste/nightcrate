"""Ready-to-process status and server-side project stage filtering."""

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.db.session import get_db
from nightcrate.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


async def _project(client: AsyncClient, name: str, status: str = "active") -> int:
    response = await client.post("/api/projects", json={"name": name, "status": status})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_each_stage_filters_and_combines_with_retired(client: AsyncClient):
    expected = {
        "not_started": await _project(client, "Not started"),
        "capturing": await _project(client, "Capturing"),
        "ready_to_process": await _project(client, "Ready", "ready_to_process"),
        "complete": await _project(client, "Complete", "complete"),
        "paused": await _project(client, "Paused", "paused"),
        "abandoned": await _project(client, "Abandoned", "abandoned"),
    }
    response = await client.post(
        f"/api/projects/{expected['capturing']}/sessions",
        json={"line_name": "Lum", "exposure_seconds": 0.1, "num_subs": 1},
    )
    assert response.status_code == 201, response.text
    retired = await _project(client, "Retired ready", "ready_to_process")
    async with get_db() as conn:
        await conn.execute("UPDATE project SET active = 0 WHERE id = ?", (retired,))
        await conn.commit()

    for stage, project_id in expected.items():
        response = await client.get("/api/projects", params={"stage": stage})
        assert response.status_code == 200
        assert [item["id"] for item in response.json()] == [project_id]

    response = await client.get(
        "/api/projects",
        params={"stage": "ready_to_process", "include_retired": "true", "q": "ready"},
    )
    assert {item["id"] for item in response.json()} == {expected["ready_to_process"], retired}
    assert (await client.get("/api/projects", params={"stage": "unknown"})).status_code == 422


async def test_ready_status_patch_and_gallery_filter_round_trip(client: AsyncClient):
    project_id = await _project(client, "Waiting")
    response = await client.patch(
        f"/api/projects/{project_id}", json={"status": "ready_to_process"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ready_to_process"

    gallery = await client.get("/api/gallery", params={"status": "ready_to_process"})
    assert gallery.status_code == 200
    assert [item["project_id"] for item in gallery.json()["items"]] == [project_id]
