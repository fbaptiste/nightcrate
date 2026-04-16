"""Tests for seeing fields on locations."""

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


BASE = {
    "name": "Backyard Observatory",
    "latitude": 33.45,
    "longitude": -112.07,
    "timezone": "America/Phoenix",
}


@pytest.mark.anyio
async def test_create_location_with_seeing(client):
    payload = {**BASE, "typical_seeing_low_arcsec": 2.0, "typical_seeing_high_arcsec": 4.0}
    resp = await client.post("/api/locations", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["typical_seeing_low_arcsec"] == 2.0
    assert data["typical_seeing_high_arcsec"] == 4.0


@pytest.mark.anyio
async def test_create_location_without_seeing(client):
    resp = await client.post("/api/locations", json=BASE)
    assert resp.status_code == 201
    data = resp.json()
    assert data["typical_seeing_low_arcsec"] is None
    assert data["typical_seeing_high_arcsec"] is None


@pytest.mark.anyio
async def test_update_location_seeing(client):
    resp = await client.post("/api/locations", json=BASE)
    loc_id = resp.json()["id"]
    resp = await client.put(
        f"/api/locations/{loc_id}",
        json={"typical_seeing_low_arcsec": 1.5, "typical_seeing_high_arcsec": 3.0},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["typical_seeing_low_arcsec"] == 1.5
    assert data["typical_seeing_high_arcsec"] == 3.0


@pytest.mark.anyio
async def test_seeing_low_must_be_lte_high(client):
    payload = {**BASE, "typical_seeing_low_arcsec": 5.0, "typical_seeing_high_arcsec": 2.0}
    resp = await client.post("/api/locations", json=payload)
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_seeing_single_value_ok(client):
    payload = {**BASE, "typical_seeing_low_arcsec": 2.5}
    resp = await client.post("/api/locations", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["typical_seeing_low_arcsec"] == 2.5
    assert data["typical_seeing_high_arcsec"] is None


@pytest.mark.anyio
async def test_seeing_must_be_positive(client):
    payload = {**BASE, "typical_seeing_low_arcsec": -1.0}
    resp = await client.post("/api/locations", json=payload)
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_seeing_zero_rejected(client):
    payload = {**BASE, "typical_seeing_low_arcsec": 0.0}
    resp = await client.post("/api/locations", json=payload)
    assert resp.status_code == 422
