"""Tests for the locations API endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


SAMPLE_LOCATION = {
    "name": "Backyard Observatory",
    "latitude": 34.05,
    "longitude": -118.25,
    "elevation_m": 100.0,
    "timezone": "America/Los_Angeles",
    "bortle_class": 6,
    "sqm_reading": 18.5,
    "city": "Los Angeles",
    "state_province": "CA",
    "country": "US",
    "postal_code": "90001",
    "notes": "Light-polluted urban site",
}


def _make_location(**overrides) -> dict:
    """Return a location payload with optional overrides."""
    loc = {**SAMPLE_LOCATION, **overrides}
    return loc


# ---------------------------------------------------------------------------
# Basic CRUD
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_create_and_read_location(client):
    """Create a location, then read it back by ID."""
    resp = await client.post("/api/locations", json=SAMPLE_LOCATION)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == SAMPLE_LOCATION["name"]
    assert data["latitude"] == SAMPLE_LOCATION["latitude"]
    assert data["longitude"] == SAMPLE_LOCATION["longitude"]
    assert data["timezone"] == SAMPLE_LOCATION["timezone"]
    assert data["bortle_class"] == SAMPLE_LOCATION["bortle_class"]
    assert data["is_default"] is True  # First location auto-promoted
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data

    loc_id = data["id"]
    get_resp = await client.get(f"/api/locations/{loc_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == SAMPLE_LOCATION["name"]


@pytest.mark.anyio
async def test_update_location(client):
    """Create a location, update all fields, verify changes."""
    create = await client.post("/api/locations", json=SAMPLE_LOCATION)
    loc_id = create.json()["id"]

    update_payload = {
        "name": "Updated Name",
        "latitude": 45.0,
        "longitude": -90.0,
        "elevation_m": 500.0,
        "timezone": "America/Chicago",
        "bortle_class": 3,
        "sqm_reading": 21.0,
        "city": "Rural Town",
        "state_province": "WI",
        "country": "US",
        "postal_code": "54000",
        "notes": "Dark sky site",
    }

    resp = await client.put(f"/api/locations/{loc_id}", json=update_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Updated Name"
    assert data["latitude"] == 45.0
    assert data["timezone"] == "America/Chicago"
    assert data["bortle_class"] == 3


@pytest.mark.anyio
async def test_delete_location(client):
    """Create a location, delete it, verify gone."""
    create = await client.post("/api/locations", json=SAMPLE_LOCATION)
    loc_id = create.json()["id"]

    del_resp = await client.delete(f"/api/locations/{loc_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["ok"] is True

    get_resp = await client.get(f"/api/locations/{loc_id}")
    assert get_resp.status_code == 404


@pytest.mark.anyio
async def test_list_locations(client):
    """Create two locations, list them, verify order (default first)."""
    await client.post("/api/locations", json=_make_location(name="Zebra Site"))
    await client.post("/api/locations", json=_make_location(name="Alpha Site"))

    resp = await client.get("/api/locations")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    # Default should be first
    assert data[0]["is_default"] is True


# ---------------------------------------------------------------------------
# Default location promotion
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_delete_default_promotes_next(client):
    """Delete the default location; the next one should become default."""
    loc1 = (await client.post("/api/locations", json=_make_location(name="Site A"))).json()
    loc2 = (await client.post("/api/locations", json=_make_location(name="Site B"))).json()

    # First location is auto-default
    assert loc1["is_default"] is True
    assert loc2["is_default"] is False

    # Delete the default
    await client.delete(f"/api/locations/{loc1['id']}")

    # Second should now be default
    get_resp = await client.get(f"/api/locations/{loc2['id']}")
    assert get_resp.json()["is_default"] is True


# ---------------------------------------------------------------------------
# Unique name constraint
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_duplicate_name_rejected(client):
    """Creating two locations with the same name returns 409."""
    await client.post("/api/locations", json=SAMPLE_LOCATION)
    resp = await client.post("/api/locations", json=SAMPLE_LOCATION)
    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"].lower()


@pytest.mark.anyio
async def test_update_to_duplicate_name_rejected(client):
    """Updating a location name to an existing name returns 409."""
    await client.post("/api/locations", json=_make_location(name="Site A"))
    loc2 = (await client.post("/api/locations", json=_make_location(name="Site B"))).json()

    resp = await client.put(f"/api/locations/{loc2['id']}", json={"name": "Site A"})
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Partial update
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_partial_update_preserves_fields(client):
    """Update only the name; other fields stay unchanged."""
    create = await client.post("/api/locations", json=SAMPLE_LOCATION)
    original = create.json()

    resp = await client.put(f"/api/locations/{original['id']}", json={"name": "New Name"})
    assert resp.status_code == 200
    updated = resp.json()

    assert updated["name"] == "New Name"
    # Everything else should be the same
    assert updated["latitude"] == original["latitude"]
    assert updated["longitude"] == original["longitude"]
    assert updated["timezone"] == original["timezone"]
    assert updated["bortle_class"] == original["bortle_class"]
    assert updated["sqm_reading"] == original["sqm_reading"]
    assert updated["city"] == original["city"]
    assert updated["country"] == original["country"]
    assert updated["notes"] == original["notes"]


# ---------------------------------------------------------------------------
# Set default endpoint
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_set_default(client):
    """POST /api/locations/{id}/set-default clears old default."""
    loc1 = (await client.post("/api/locations", json=_make_location(name="Site A"))).json()
    loc2 = (await client.post("/api/locations", json=_make_location(name="Site B"))).json()

    assert loc1["is_default"] is True

    # Make loc2 the default
    resp = await client.post(f"/api/locations/{loc2['id']}/set-default")
    assert resp.status_code == 200
    assert resp.json()["is_default"] is True

    # loc1 should no longer be default
    loc1_refreshed = (await client.get(f"/api/locations/{loc1['id']}")).json()
    assert loc1_refreshed["is_default"] is False


@pytest.mark.anyio
async def test_get_default_location(client):
    """GET /api/locations/default returns the default location."""
    await client.post("/api/locations", json=_make_location(name="Site A"))

    resp = await client.get("/api/locations/default")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Site A"
    assert data["is_default"] is True


@pytest.mark.anyio
async def test_get_default_location_none(client):
    """GET /api/locations/default returns null when no locations exist."""
    resp = await client.get("/api/locations/default")
    assert resp.status_code == 200
    assert resp.json() is None


# ---------------------------------------------------------------------------
# Delete last location
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_delete_last_location(client):
    """Delete the only location; list should be empty."""
    loc = (await client.post("/api/locations", json=SAMPLE_LOCATION)).json()
    await client.delete(f"/api/locations/{loc['id']}")

    resp = await client.get("/api/locations")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# 404 on missing
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_get_nonexistent_location(client):
    resp = await client.get("/api/locations/99999")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_update_nonexistent_location(client):
    resp = await client.put("/api/locations/99999", json={"name": "Nope"})
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_delete_nonexistent_location(client):
    resp = await client.delete("/api/locations/99999")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_set_default_nonexistent_location(client):
    resp = await client.post("/api/locations/99999/set-default")
    assert resp.status_code == 404
