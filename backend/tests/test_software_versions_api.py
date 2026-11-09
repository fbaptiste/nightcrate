"""Software version CRUD and transaction regressions."""

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


async def _software(client, versions=None):
    manufacturers = await client.get("/api/equipment/manufacturer")
    body = {
        "manufacturer_id": manufacturers.json()[0]["id"],
        "name": "Versioned app",
        "category": "processing",
    }
    if versions is not None:
        body["versions"] = versions
    response = await client.post("/api/equipment/software", json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def test_versions_crud_and_order(client):
    software = await _software(client, [{"version": "1.9.2"}, {"version": "1.9.3"}])
    assert [item["version"] for item in software["versions"]] == ["1.9.3", "1.9.2"]
    newest, oldest = software["versions"]
    updated = await client.put(
        f"/api/equipment/software/{software['id']}",
        json={"versions": [{"id": newest["id"], "version": "1.9.4"}]},
    )
    assert updated.status_code == 200, updated.text
    assert [(item["id"], item["version"]) for item in updated.json()["versions"]] == [
        (newest["id"], "1.9.4")
    ]
    assert oldest["id"] != newest["id"]


async def test_omitted_or_null_versions_unchanged(client):
    software = await _software(client, [{"version": "1"}])
    item_id = software["id"]
    omitted = await client.put(f"/api/equipment/software/{item_id}", json={"notes": "kept"})
    assert len(omitted.json()["versions"]) == 1
    null = await client.put(f"/api/equipment/software/{item_id}", json={"versions": None})
    assert len(null.json()["versions"]) == 1


async def test_empty_versions_removes_all(client):
    software = await _software(client, [{"version": "1"}])
    item_id = software["id"]
    empty = await client.put(f"/api/equipment/software/{item_id}", json={"versions": []})
    assert empty.status_code == 200
    assert empty.json()["versions"] == []


async def test_post_version_and_duplicate(client):
    software = await _software(client)
    created = await client.post(
        f"/api/equipment/software/{software['id']}/versions", json={"version": " 2.0 "}
    )
    assert created.status_code == 201
    assert created.json()["version"] == "2.0"
    duplicate = await client.post(
        f"/api/equipment/software/{software['id']}/versions", json={"version": "2.0"}
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == {"code": "version_exists", "version": "2.0"}


async def test_create_with_versions(client):
    software = await _software(client, [{"version": "1"}, {"version": "2"}])
    assert [item["version"] for item in software["versions"]] == ["2", "1"]


async def test_versions_only_rename(client):
    software = await _software(client, [{"version": "1"}])
    version = software["versions"][0]
    response = await client.put(
        f"/api/equipment/software/{software['id']}",
        json={"versions": [{"id": version["id"], "version": "1.1"}]},
    )
    assert response.status_code == 200
    assert response.json()["versions"][0]["version"] == "1.1"


async def test_duplicate_version_in_request(client):
    software = await _software(client)
    response = await client.put(
        f"/api/equipment/software/{software['id']}",
        json={"versions": [{"version": "2.0"}, {"version": " 2.0 "}]},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Version 2.0 is listed twice"


async def test_duplicate_version_against_existing(client):
    software = await _software(client, [{"version": "2.0"}])
    response = await client.put(
        f"/api/equipment/software/{software['id']}",
        json={"versions": [{"version": "2.0"}]},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "version_exists", "version": "2.0"}


async def test_swap_version_names(client):
    software = await _software(client, [{"version": "1.9.2"}, {"version": "1.9.3"}])
    newer, older = software["versions"]
    response = await client.put(
        f"/api/equipment/software/{software['id']}",
        json={
            "versions": [
                {"id": newer["id"], "version": older["version"]},
                {"id": older["id"], "version": newer["version"]},
            ]
        },
    )
    assert response.status_code == 200, response.text
    assert {item["id"]: item["version"] for item in response.json()["versions"]} == {
        newer["id"]: older["version"],
        older["id"]: newer["version"],
    }


async def test_versions_only_delete(client):
    software = await _software(client, [{"version": "1"}])
    response = await client.put(f"/api/equipment/software/{software['id']}", json={"versions": []})
    assert response.status_code == 200
    assert response.json()["versions"] == []


async def test_version_in_use_cannot_be_removed(client):
    software = await _software(client, [{"version": "1"}])
    project = (await client.post("/api/projects", json={"name": "Version user"})).json()
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
    refused = await client.put(f"/api/equipment/software/{software['id']}", json={"versions": []})
    assert refused.status_code == 409
    assert refused.json()["detail"]["projects"] == ["Version user"]


async def test_syqon_rows_seeded(client):
    response = await client.get("/api/equipment/software", params={"include_retired": True})
    syqon = [
        item
        for item in response.json()
        if item["manufacturer"] and item["manufacturer"]["name"] == "SyQon"
    ]
    assert {(item["name"], item["category"]) for item in syqon} == {
        ("SyQon Studio", "processing"),
        ("DeepPrism", "processing"),
        ("Parallax", "processing"),
        ("Axiom", "processing"),
    }
