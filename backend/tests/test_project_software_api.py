"""Project software/version association regressions."""

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


async def test_project_software_two_versions(client):
    manufacturer_id = (await client.get("/api/equipment/manufacturer")).json()[0]["id"]
    software = (
        await client.post(
            "/api/equipment/software",
            json={
                "name": "Project app",
                "manufacturer_id": manufacturer_id,
                "category": "processing",
                "versions": [{"version": "1"}, {"version": "2"}],
            },
        )
    ).json()
    project = (await client.post("/api/projects", json={"name": "Software project"})).json()
    version_ids = [item["id"] for item in software["versions"]]
    response = await client.put(
        f"/api/projects/{project['id']}/software",
        json={
            "entries": [
                {"software_id": software["id"], "software_version_id": version_ids[1]},
                {"software_id": software["id"], "software_version_id": version_ids[0]},
            ]
        },
    )
    assert response.status_code == 200, response.text
    assert [item["software_version_id"] for item in response.json()["software"]] == version_ids[
        ::-1
    ]


async def test_retired_program_stays_on_project(client):
    manufacturer_id = (await client.get("/api/equipment/manufacturer")).json()[0]["id"]
    software = (
        await client.post(
            "/api/equipment/software",
            json={
                "manufacturer_id": manufacturer_id,
                "name": "Retired app",
                "category": "processing",
            },
        )
    ).json()
    project = (await client.post("/api/projects", json={"name": "Retired software"})).json()
    await client.put(
        f"/api/projects/{project['id']}/software",
        json={"entries": [{"software_id": software["id"], "software_version_id": None}]},
    )
    await client.delete(f"/api/equipment/software/{software['id']}")
    refreshed = await client.get(f"/api/projects/{project['id']}")
    assert refreshed.json()["software"][0]["active"] is False


async def test_project_software_rejects_duplicates_and_foreign_versions(client):
    manufacturer_id = (await client.get("/api/equipment/manufacturer")).json()[0]["id"]
    first = (
        await client.post(
            "/api/equipment/software",
            json={
                "manufacturer_id": manufacturer_id,
                "name": "First",
                "category": "processing",
                "versions": [{"version": "1"}],
            },
        )
    ).json()
    second = (
        await client.post(
            "/api/equipment/software",
            json={
                "manufacturer_id": manufacturer_id,
                "name": "Second",
                "category": "processing",
                "versions": [{"version": "1"}],
            },
        )
    ).json()
    project = (await client.post("/api/projects", json={"name": "Validation"})).json()
    entry = {
        "software_id": first["id"],
        "software_version_id": first["versions"][0]["id"],
    }
    duplicate = await client.put(
        f"/api/projects/{project['id']}/software", json={"entries": [entry, entry]}
    )
    assert duplicate.status_code == 422
    foreign = await client.put(
        f"/api/projects/{project['id']}/software",
        json={
            "entries": [
                {
                    "software_id": first["id"],
                    "software_version_id": second["versions"][0]["id"],
                }
            ]
        },
    )
    assert foreign.status_code == 422


async def test_version_delete_failure_rolls_back_software_edit(client):
    manufacturer_id = (await client.get("/api/equipment/manufacturer")).json()[0]["id"]
    software = (
        await client.post(
            "/api/equipment/software",
            json={
                "manufacturer_id": manufacturer_id,
                "name": "Rollback app",
                "category": "processing",
                "versions": [{"version": "1"}],
            },
        )
    ).json()
    project = (await client.post("/api/projects", json={"name": "Uses version"})).json()
    await client.put(
        f"/api/projects/{project['id']}/software",
        json={
            "entries": [
                {
                    "software_id": software["id"],
                    "software_version_id": software["versions"][0]["id"],
                }
            ]
        },
    )
    refused = await client.put(
        f"/api/equipment/software/{software['id']}",
        json={"name": "Should roll back", "versions": []},
    )
    assert refused.status_code == 409
    assert refused.json()["detail"] == {
        "code": "version_in_use",
        "version": "1",
        "projects": ["Uses version"],
    }
    current = await client.get(f"/api/equipment/software/{software['id']}")
    assert current.json()["name"] == "Rollback app"
