"""Tests for the horizon API endpoints (v0.19.0 multi-horizon shape)."""

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


async def _get_default_horizon(client, loc_id: int) -> dict:
    resp = await client.get(f"/api/locations/{loc_id}/horizons")
    assert resp.status_code == 200, resp.text
    horizons = resp.json()
    default = next(h for h in horizons if h["is_default"])
    return default


# ── Auto-seeded default ──────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_new_location_has_zero_degree_default(client):
    loc_id = await _make_location(client)
    resp = await client.get(f"/api/locations/{loc_id}/horizons")
    assert resp.status_code == 200
    horizons = resp.json()
    assert len(horizons) == 1
    h = horizons[0]
    assert h["type"] == "artificial"
    assert h["flat_altitude_deg"] == 0.0
    assert h["is_default"] is True


@pytest.mark.anyio
async def test_list_horizons_404_when_location_missing(client):
    resp = await client.get("/api/locations/99999/horizons")
    assert resp.status_code == 404


# ── Create ──────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_create_artificial_horizon(client):
    loc_id = await _make_location(client)
    resp = await client.post(
        f"/api/locations/{loc_id}/horizons",
        json={"name": "30° flat", "type": "artificial", "flat_altitude_deg": 30.0},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["type"] == "artificial"
    assert body["flat_altitude_deg"] == 30.0
    assert body["is_default"] is False  # default stays on the auto-seeded 0°


@pytest.mark.anyio
async def test_create_custom_horizon(client):
    loc_id = await _make_location(client)
    resp = await client.post(
        f"/api/locations/{loc_id}/horizons",
        json={
            "name": "Custom horizon",
            "type": "custom",
            "points": SAMPLE_POINTS,
            "source": "drawn",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["type"] == "custom"
    assert body["flat_altitude_deg"] is None
    assert body["source"] == "drawn"
    assert len(body["points"]) == 4
    azimuths = [p["azimuth_deg"] for p in body["points"]]
    assert azimuths == sorted(azimuths)


@pytest.mark.anyio
async def test_create_artificial_requires_altitude(client):
    loc_id = await _make_location(client)
    resp = await client.post(
        f"/api/locations/{loc_id}/horizons",
        json={"name": "bad", "type": "artificial"},
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_create_custom_requires_two_points(client):
    loc_id = await _make_location(client)
    resp = await client.post(
        f"/api/locations/{loc_id}/horizons",
        json={
            "name": "tiny",
            "type": "custom",
            "points": [{"azimuth_deg": 0.0, "altitude_deg": 10.0}],
        },
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_create_second_custom_conflicts(client):
    loc_id = await _make_location(client)
    first = await client.post(
        f"/api/locations/{loc_id}/horizons",
        json={"name": "Custom", "type": "custom", "points": SAMPLE_POINTS},
    )
    assert first.status_code == 201
    second = await client.post(
        f"/api/locations/{loc_id}/horizons",
        json={"name": "Custom 2", "type": "custom", "points": SAMPLE_POINTS},
    )
    # Partial unique index on (location_id) WHERE type='custom' fires.
    assert second.status_code == 409


@pytest.mark.anyio
async def test_create_with_is_default_promotes(client):
    loc_id = await _make_location(client)
    resp = await client.post(
        f"/api/locations/{loc_id}/horizons",
        json={
            "name": "30° flat",
            "type": "artificial",
            "flat_altitude_deg": 30.0,
            "is_default": True,
        },
    )
    assert resp.status_code == 201
    horizons = (await client.get(f"/api/locations/{loc_id}/horizons")).json()
    defaults = [h for h in horizons if h["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["name"] == "30° flat"


# ── Update ──────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_patch_artificial_altitude(client):
    loc_id = await _make_location(client)
    default = await _get_default_horizon(client, loc_id)
    resp = await client.patch(
        f"/api/locations/{loc_id}/horizons/{default['id']}",
        json={"flat_altitude_deg": 25.0},
    )
    assert resp.status_code == 200
    assert resp.json()["flat_altitude_deg"] == 25.0


@pytest.mark.anyio
async def test_patch_promotes_default(client):
    loc_id = await _make_location(client)
    # Add a second horizon
    second = await client.post(
        f"/api/locations/{loc_id}/horizons",
        json={"name": "30° flat", "type": "artificial", "flat_altitude_deg": 30.0},
    )
    second_id = second.json()["id"]
    # Promote it
    resp = await client.patch(
        f"/api/locations/{loc_id}/horizons/{second_id}",
        json={"is_default": True},
    )
    assert resp.status_code == 200
    horizons = (await client.get(f"/api/locations/{loc_id}/horizons")).json()
    default = next(h for h in horizons if h["is_default"])
    assert default["id"] == second_id


@pytest.mark.anyio
async def test_patch_demoting_current_default_rejected(client):
    """Demoting the default without promoting another is 422 — every
    location must have exactly one default horizon."""
    loc_id = await _make_location(client)
    default = await _get_default_horizon(client, loc_id)
    resp = await client.patch(
        f"/api/locations/{loc_id}/horizons/{default['id']}",
        json={"is_default": False},
    )
    assert resp.status_code == 422


# ── Delete ──────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_delete_last_horizon_rejected(client):
    loc_id = await _make_location(client)
    default = await _get_default_horizon(client, loc_id)
    resp = await client.delete(f"/api/locations/{loc_id}/horizons/{default['id']}")
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_delete_default_auto_promotes(client):
    loc_id = await _make_location(client)
    # Add a second so the first can be deleted.
    second = await client.post(
        f"/api/locations/{loc_id}/horizons",
        json={"name": "30° flat", "type": "artificial", "flat_altitude_deg": 30.0},
    )
    second_id = second.json()["id"]
    default = await _get_default_horizon(client, loc_id)

    # Delete the current default. The only remaining row (second_id)
    # must be auto-promoted.
    resp = await client.delete(f"/api/locations/{loc_id}/horizons/{default['id']}")
    assert resp.status_code == 204
    horizons = (await client.get(f"/api/locations/{loc_id}/horizons")).json()
    assert len(horizons) == 1
    assert horizons[0]["id"] == second_id
    assert horizons[0]["is_default"] is True


@pytest.mark.anyio
async def test_delete_non_default_preserves_default(client):
    loc_id = await _make_location(client)
    second = await client.post(
        f"/api/locations/{loc_id}/horizons",
        json={"name": "30° flat", "type": "artificial", "flat_altitude_deg": 30.0},
    )
    second_id = second.json()["id"]
    default = await _get_default_horizon(client, loc_id)
    resp = await client.delete(f"/api/locations/{loc_id}/horizons/{second_id}")
    assert resp.status_code == 204
    horizons = (await client.get(f"/api/locations/{loc_id}/horizons")).json()
    assert len(horizons) == 1
    assert horizons[0]["id"] == default["id"]


# ── Import ──────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_import_creates_custom_horizon(client):
    loc_id = await _make_location(client)
    file_text = "# NINA\n0 10\n90 20\n180 5\n270 15\n"
    files = {"file": ("backyard.hrz", file_text.encode("utf-8"), "text/plain")}
    resp = await client.post(f"/api/locations/{loc_id}/horizons/import", files=files)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["horizon"]["type"] == "custom"
    assert body["horizon"]["source"] == "imported"
    assert body["horizon"]["source_filename"] == "backyard.hrz"
    assert len(body["horizon"]["points"]) == 4


@pytest.mark.anyio
async def test_import_auto_promotes_to_default(client):
    """Importing a horizon for a location that has no prior custom
    horizon promotes the new row to default — otherwise the imported
    file has no visible effect on the planner (the auto-seeded 0°
    artificial stays active)."""
    loc_id = await _make_location(client)
    file_text = "0 10\n90 20\n180 5\n270 15\n"
    files = {"file": ("backyard.hrz", file_text.encode("utf-8"), "text/plain")}
    resp = await client.post(f"/api/locations/{loc_id}/horizons/import", files=files)
    assert resp.status_code == 200
    horizons = (await client.get(f"/api/locations/{loc_id}/horizons")).json()
    default = next(h for h in horizons if h["is_default"])
    assert default["type"] == "custom"
    assert default["id"] == resp.json()["horizon"]["id"]


@pytest.mark.anyio
async def test_import_replacement_preserves_default_flag(client):
    """When a location already has a custom horizon, re-importing
    replaces its points without changing whatever default state the
    user had chosen for it."""
    loc_id = await _make_location(client)
    # Create a custom horizon but DO NOT promote it (stays as
    # non-default; the auto-seeded 0° artificial remains default).
    await client.post(
        f"/api/locations/{loc_id}/horizons",
        json={"name": "Custom", "type": "custom", "points": SAMPLE_POINTS, "source": "drawn"},
    )
    # Confirm 0° artificial is still default.
    horizons = (await client.get(f"/api/locations/{loc_id}/horizons")).json()
    default_before = next(h for h in horizons if h["is_default"])
    assert default_before["type"] == "artificial"

    # Re-import the custom — must preserve the non-default flag.
    file_text = "0 22\n180 7\n"
    files = {"file": ("replaced.hrz", file_text.encode("utf-8"), "text/plain")}
    resp = await client.post(f"/api/locations/{loc_id}/horizons/import", files=files)
    assert resp.status_code == 200
    horizons = (await client.get(f"/api/locations/{loc_id}/horizons")).json()
    default_after = next(h for h in horizons if h["is_default"])
    assert default_after["id"] == default_before["id"]  # same row still default


@pytest.mark.anyio
async def test_import_replaces_existing_custom(client):
    loc_id = await _make_location(client)
    # Seed a drawn custom horizon.
    await client.post(
        f"/api/locations/{loc_id}/horizons",
        json={"name": "Custom", "type": "custom", "points": SAMPLE_POINTS, "source": "drawn"},
    )
    file_text = "0 22\n180 7\n"
    files = {"file": ("new.hrz", file_text.encode("utf-8"), "text/plain")}
    resp = await client.post(f"/api/locations/{loc_id}/horizons/import", files=files)
    assert resp.status_code == 200
    body = resp.json()
    assert body["horizon"]["source"] == "imported"
    assert len(body["horizon"]["points"]) == 2
    # Still exactly one custom on this location.
    horizons = (await client.get(f"/api/locations/{loc_id}/horizons")).json()
    customs = [h for h in horizons if h["type"] == "custom"]
    assert len(customs) == 1


@pytest.mark.anyio
async def test_import_malformed_400_no_persistence(client):
    loc_id = await _make_location(client)
    files = {"file": ("bad.hrz", b"not numbers here\n", "text/plain")}
    resp = await client.post(f"/api/locations/{loc_id}/horizons/import", files=files)
    assert resp.status_code == 400
    # Only the auto-seeded artificial still exists.
    horizons = (await client.get(f"/api/locations/{loc_id}/horizons")).json()
    assert all(h["type"] == "artificial" for h in horizons)


# ── Exports ─────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_export_nina_downloads_hrz(client):
    loc_id = await _make_location(client)
    created = await client.post(
        f"/api/locations/{loc_id}/horizons",
        json={"name": "Custom", "type": "custom", "points": SAMPLE_POINTS, "source": "drawn"},
    )
    hid = created.json()["id"]
    resp = await client.get(f"/api/locations/{loc_id}/horizons/{hid}/export/nina.hrz")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert "attachment" in resp.headers["content-disposition"]
    body = resp.text
    assert "# NightCrate horizon export" in body
    assert "0 15" in body


@pytest.mark.anyio
async def test_export_csv_downloads(client):
    loc_id = await _make_location(client)
    created = await client.post(
        f"/api/locations/{loc_id}/horizons",
        json={"name": "Custom", "type": "custom", "points": SAMPLE_POINTS, "source": "drawn"},
    )
    hid = created.json()["id"]
    resp = await client.get(f"/api/locations/{loc_id}/horizons/{hid}/export/csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    lines = resp.text.strip().splitlines()
    assert lines[0] == "azimuth_deg,altitude_deg"
    assert len(lines) == 1 + len(SAMPLE_POINTS)


@pytest.mark.anyio
async def test_export_stellarium_zip_contents(client):
    loc_id = await _make_location(client)
    created = await client.post(
        f"/api/locations/{loc_id}/horizons",
        json={"name": "Custom", "type": "custom", "points": SAMPLE_POINTS, "source": "drawn"},
    )
    hid = created.json()["id"]
    resp = await client.get(f"/api/locations/{loc_id}/horizons/{hid}/export/stellarium.zip")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(io.BytesIO(resp.content), "r") as zf:
        names = set(zf.namelist())
        assert names == {"landscape.ini", "horizon.txt", "readme.txt"}
        ini = zf.read("landscape.ini").decode("utf-8")
    assert "name = Mesa Backyard" in ini


@pytest.mark.anyio
async def test_export_artificial_rejected(client):
    """Artificial horizons can't be exported as files — no polyline to emit."""
    loc_id = await _make_location(client)
    default = await _get_default_horizon(client, loc_id)
    resp = await client.get(f"/api/locations/{loc_id}/horizons/{default['id']}/export/nina.hrz")
    assert resp.status_code == 422


# ── Stateless parse ─────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_parse_returns_points_without_persisting(client):
    loc_id = await _make_location(client)
    file_text = "0 10\n90 20\n180 5\n270 15\n"
    files = {"file": ("backyard.hrz", file_text.encode("utf-8"), "text/plain")}
    resp = await client.post("/api/horizons/parse", files=files)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["points"]) == 4
    assert body["warnings"] == []
    assert body["source_filename"] == "backyard.hrz"
    # No custom horizon was persisted.
    horizons = (await client.get(f"/api/locations/{loc_id}/horizons")).json()
    assert all(h["type"] == "artificial" for h in horizons)


@pytest.mark.anyio
async def test_parse_malformed_returns_400(client):
    files = {"file": ("bad.hrz", b"not a number here\n", "text/plain")}
    resp = await client.post("/api/horizons/parse", files=files)
    assert resp.status_code == 400


# ── Cascade ─────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_horizons_404_on_soft_deleted_location(client):
    loc_id = await _make_location(client)
    del_resp = await client.delete(f"/api/locations/{loc_id}")
    assert del_resp.status_code in (200, 204)
    # The locations router soft-deletes; horizons' allow_inactive=False
    # path should 404.
    resp = await client.get(f"/api/locations/{loc_id}/horizons")
    assert resp.status_code == 404
