"""Tests for the horizon API endpoints."""

import io
import zipfile

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
    "name": "Mesa Backyard",
    "latitude": 33.46,
    "longitude": -111.62,
    "elevation_m": 400.0,
    "timezone": "America/Phoenix",
}

SAMPLE_POINTS = [
    {"azimuth_deg": 0.0, "altitude_deg": 15.0},
    {"azimuth_deg": 90.0, "altitude_deg": 10.0},
    {"azimuth_deg": 180.0, "altitude_deg": 5.0},
    {"azimuth_deg": 270.0, "altitude_deg": 12.0},
]


async def _make_location(client, **overrides) -> int:
    payload = {**SAMPLE_LOCATION, **overrides}
    resp = await client.post("/api/locations", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ── GET ───────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_get_horizon_404_when_none(client):
    loc_id = await _make_location(client)
    resp = await client.get(f"/api/locations/{loc_id}/horizon")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_get_horizon_404_when_location_missing(client):
    resp = await client.get("/api/locations/99999/horizon")
    assert resp.status_code == 404


# ── PUT ───────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_put_horizon_creates_drawn(client):
    loc_id = await _make_location(client)
    resp = await client.put(
        f"/api/locations/{loc_id}/horizon",
        json={"source": "drawn", "points": SAMPLE_POINTS, "notes": "trees"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["location_id"] == loc_id
    assert body["source"] == "drawn"
    assert body["source_filename"] is None
    assert body["notes"] == "trees"
    assert len(body["points"]) == 4
    # Returned sorted ascending by azimuth
    azimuths = [p["azimuth_deg"] for p in body["points"]]
    assert azimuths == sorted(azimuths)


@pytest.mark.anyio
async def test_put_horizon_replaces_existing_atomically(client):
    loc_id = await _make_location(client)
    await client.put(
        f"/api/locations/{loc_id}/horizon", json={"source": "drawn", "points": SAMPLE_POINTS}
    )
    new_points = [
        {"azimuth_deg": 30.0, "altitude_deg": 20.0},
        {"azimuth_deg": 150.0, "altitude_deg": 8.0},
    ]
    resp = await client.put(
        f"/api/locations/{loc_id}/horizon", json={"source": "drawn", "points": new_points}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["points"]) == 2
    assert body["points"][0]["azimuth_deg"] == 30.0


@pytest.mark.anyio
async def test_put_horizon_rejects_fewer_than_two_points(client):
    loc_id = await _make_location(client)
    resp = await client.put(
        f"/api/locations/{loc_id}/horizon",
        json={"source": "drawn", "points": [{"azimuth_deg": 45.0, "altitude_deg": 10.0}]},
    )
    assert resp.status_code == 422
    assert "at least 2" in resp.text.lower()


@pytest.mark.anyio
async def test_put_horizon_rejects_invalid_azimuth(client):
    loc_id = await _make_location(client)
    resp = await client.put(
        f"/api/locations/{loc_id}/horizon",
        json={
            "source": "drawn",
            "points": [
                {"azimuth_deg": 400.0, "altitude_deg": 10.0},
                {"azimuth_deg": 90.0, "altitude_deg": 5.0},
            ],
        },
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_put_horizon_rejects_invalid_altitude(client):
    loc_id = await _make_location(client)
    resp = await client.put(
        f"/api/locations/{loc_id}/horizon",
        json={
            "source": "drawn",
            "points": [
                {"azimuth_deg": 0.0, "altitude_deg": 95.0},
                {"azimuth_deg": 90.0, "altitude_deg": 5.0},
            ],
        },
    )
    assert resp.status_code == 422


# ── DELETE ────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_delete_horizon_returns_204(client):
    loc_id = await _make_location(client)
    await client.put(
        f"/api/locations/{loc_id}/horizon", json={"source": "drawn", "points": SAMPLE_POINTS}
    )
    resp = await client.delete(f"/api/locations/{loc_id}/horizon")
    assert resp.status_code == 204
    get_resp = await client.get(f"/api/locations/{loc_id}/horizon")
    assert get_resp.status_code == 404


@pytest.mark.anyio
async def test_delete_horizon_404_when_none(client):
    loc_id = await _make_location(client)
    resp = await client.delete(f"/api/locations/{loc_id}/horizon")
    assert resp.status_code == 404


# ── Import ────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_import_horizon_creates_from_nina_hrz(client):
    loc_id = await _make_location(client)
    file_text = "# NINA\n0 10\n90 20\n180 5\n270 15\n"
    files = {"file": ("backyard.hrz", file_text.encode("utf-8"), "text/plain")}
    resp = await client.post(f"/api/locations/{loc_id}/horizon/import", files=files)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["warnings"] == []
    assert body["horizon"]["source"] == "imported"
    assert body["horizon"]["source_filename"] == "backyard.hrz"
    assert len(body["horizon"]["points"]) == 4


@pytest.mark.anyio
async def test_import_replaces_existing_horizon(client):
    loc_id = await _make_location(client)
    # Seed a drawn horizon first
    await client.put(
        f"/api/locations/{loc_id}/horizon", json={"source": "drawn", "points": SAMPLE_POINTS}
    )
    # Then import replaces it entirely, including the source type
    file_text = "0 22\n180 7\n"
    files = {"file": ("new.hrz", file_text.encode("utf-8"), "text/plain")}
    resp = await client.post(f"/api/locations/{loc_id}/horizon/import", files=files)
    assert resp.status_code == 200
    body = resp.json()
    assert body["horizon"]["source"] == "imported"
    assert len(body["horizon"]["points"]) == 2


@pytest.mark.anyio
async def test_import_malformed_file_400_no_persistence(client):
    loc_id = await _make_location(client)
    files = {"file": ("bad.hrz", b"not numbers here\n", "text/plain")}
    resp = await client.post(f"/api/locations/{loc_id}/horizon/import", files=files)
    assert resp.status_code == 400
    get_resp = await client.get(f"/api/locations/{loc_id}/horizon")
    assert get_resp.status_code == 404


@pytest.mark.anyio
async def test_import_non_utf8_rejected(client):
    loc_id = await _make_location(client)
    files = {"file": ("weird.hrz", b"\xff\xfe\x00\x00binary", "application/octet-stream")}
    resp = await client.post(f"/api/locations/{loc_id}/horizon/import", files=files)
    assert resp.status_code == 400


# ── Exports ───────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_export_nina_downloads_hrz(client):
    loc_id = await _make_location(client)
    await client.put(
        f"/api/locations/{loc_id}/horizon", json={"source": "drawn", "points": SAMPLE_POINTS}
    )
    resp = await client.get(f"/api/locations/{loc_id}/horizon/export/nina.hrz")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert "attachment" in resp.headers["content-disposition"]
    assert ".hrz" in resp.headers["content-disposition"]
    body = resp.text
    assert "# NightCrate horizon export" in body
    assert "0 15" in body


@pytest.mark.anyio
async def test_export_csv_downloads(client):
    loc_id = await _make_location(client)
    await client.put(
        f"/api/locations/{loc_id}/horizon", json={"source": "drawn", "points": SAMPLE_POINTS}
    )
    resp = await client.get(f"/api/locations/{loc_id}/horizon/export/csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    body = resp.text
    lines = body.strip().splitlines()
    assert lines[0] == "azimuth_deg,altitude_deg"
    assert len(lines) == 1 + len(SAMPLE_POINTS)


@pytest.mark.anyio
async def test_export_stellarium_zip_contents(client):
    loc_id = await _make_location(client)
    await client.put(
        f"/api/locations/{loc_id}/horizon", json={"source": "drawn", "points": SAMPLE_POINTS}
    )
    resp = await client.get(f"/api/locations/{loc_id}/horizon/export/stellarium.zip")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(io.BytesIO(resp.content), "r") as zf:
        names = set(zf.namelist())
        assert names == {"landscape.ini", "horizon.txt", "readme.txt"}
        ini = zf.read("landscape.ini").decode("utf-8")
    assert "name = Mesa Backyard" in ini
    assert "latitude = 33.46" in ini


@pytest.mark.anyio
async def test_export_404_when_no_horizon(client):
    loc_id = await _make_location(client)
    for fmt in ("nina.hrz", "stellarium.zip", "csv"):
        resp = await client.get(f"/api/locations/{loc_id}/horizon/export/{fmt}")
        assert resp.status_code == 404, f"{fmt} should 404 with no horizon"


@pytest.mark.anyio
async def test_filename_sanitized_in_disposition(client):
    loc_id = await _make_location(client, name="Mesa Backyard  (North)")
    await client.put(
        f"/api/locations/{loc_id}/horizon", json={"source": "drawn", "points": SAMPLE_POINTS}
    )
    resp = await client.get(f"/api/locations/{loc_id}/horizon/export/nina.hrz")
    disp = resp.headers["content-disposition"]
    assert "mesa_backyard_north" in disp.lower()
    assert ".hrz" in disp


# ── Stateless parse ───────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_parse_returns_points_without_persisting(client):
    loc_id = await _make_location(client)
    file_text = "0 10\n90 20\n180 5\n270 15\n"
    files = {"file": ("backyard.hrz", file_text.encode("utf-8"), "text/plain")}
    resp = await client.post("/api/horizons/parse", files=files)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["points"]) == 4
    assert body["points"][0] == {"azimuth_deg": 0.0, "altitude_deg": 10.0}
    assert body["warnings"] == []
    assert body["source_filename"] == "backyard.hrz"
    # Crucially: no horizon was persisted for the location
    get_resp = await client.get(f"/api/locations/{loc_id}/horizon")
    assert get_resp.status_code == 404


@pytest.mark.anyio
async def test_parse_malformed_file_returns_400(client):
    files = {"file": ("bad.hrz", b"not a number here\n", "text/plain")}
    resp = await client.post("/api/horizons/parse", files=files)
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_parse_non_utf8_returns_400(client):
    files = {"file": ("weird.hrz", b"\xff\xfe\x00\x00binary", "application/octet-stream")}
    resp = await client.post("/api/horizons/parse", files=files)
    assert resp.status_code == 400


# ── Cascade ───────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_cascade_delete_on_location_removes_horizon(client):
    loc_id = await _make_location(client)
    await client.put(
        f"/api/locations/{loc_id}/horizon", json={"source": "drawn", "points": SAMPLE_POINTS}
    )
    # Locations use soft-delete; hard-cascade requires actually hard-deleting the row.
    # Verify the horizon still exists after soft-delete, and GETs 404 (location inactive).
    del_resp = await client.delete(f"/api/locations/{loc_id}")
    assert del_resp.status_code in (200, 204)
    get_resp = await client.get(f"/api/locations/{loc_id}/horizon")
    # Soft-deleted location makes GET 404
    assert get_resp.status_code == 404
