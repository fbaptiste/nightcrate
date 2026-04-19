"""Tests for the Calculators API.

Covers every endpoint with at least one happy-path assertion plus spot checks
for numerical correctness against hand-computed values.
"""

import math

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


@pytest.fixture
async def phoenix_location_id():
    """Insert a Phoenix location and yield its ID."""
    async with get_db() as conn:
        cursor = await conn.execute(
            """INSERT INTO location (
                name, latitude, longitude, elevation_m, timezone, geo_timezone,
                is_default
            ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                "Phoenix Test",
                33.45,
                -112.07,
                340.0,
                "America/Phoenix",
                "America/Phoenix",
                1,
            ),
        )
        await conn.commit()
        return cursor.lastrowid


# ── 1. Lat/Lon → sexagesimal ─────────────────────────────────────────────────


@pytest.mark.anyio
async def test_lat_long_to_sexagesimal(client):
    resp = await client.get(
        "/api/calculators/lat-long/to-sexagesimal",
        params={"latitude": 33.465, "longitude": -112.07388888888888},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["latitude_display"] == "33\u00b027\u203254\u2033 N"
    assert data["longitude_display"] == "112\u00b004\u203226\u2033 W"


@pytest.mark.anyio
async def test_lat_long_to_sexagesimal_out_of_range(client):
    resp = await client.get(
        "/api/calculators/lat-long/to-sexagesimal",
        params={"latitude": 99.0, "longitude": 0.0},
    )
    assert resp.status_code == 422


# ── 2. Lat/Lon → decimal ─────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_lat_long_to_decimal_roundtrip_string(client):
    # First format a known decimal to sexagesimal
    decimal_in = {"latitude": 33.465, "longitude": -112.07388888888888}
    formatted = (
        await client.get("/api/calculators/lat-long/to-sexagesimal", params=decimal_in)
    ).json()

    # Parse it back
    payload = {
        "latitude": formatted["latitude_display"],
        "longitude": formatted["longitude_display"],
    }
    resp = await client.post("/api/calculators/lat-long/to-decimal", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["latitude_error"] is None
    assert data["longitude_error"] is None
    # Seconds rounding means <1/3600° tolerance.
    assert abs(data["latitude"] - 33.465) < 1e-3
    assert abs(data["longitude"] - (-112.07388888888888)) < 1e-3


@pytest.mark.anyio
async def test_lat_long_to_decimal_ascii_string(client):
    resp = await client.post(
        "/api/calculators/lat-long/to-decimal",
        json={"latitude": "33 27 54 N", "longitude": "112 04 26 W"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["latitude_error"] is None
    assert data["longitude_error"] is None
    assert abs(data["latitude"] - 33.465) < 1e-3
    assert abs(data["longitude"] - (-112.07388888888888)) < 1e-3


@pytest.mark.anyio
async def test_lat_long_to_decimal_components(client):
    resp = await client.post(
        "/api/calculators/lat-long/to-decimal",
        json={
            "latitude_deg": 33,
            "latitude_min": 27,
            "latitude_sec": 54,
            "latitude_direction": "N",
            "longitude_deg": 112,
            "longitude_min": 4,
            "longitude_sec": 26,
            "longitude_direction": "W",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert abs(data["latitude"] - 33.465) < 1e-3
    assert abs(data["longitude"] - (-112.07388888888888)) < 1e-3


@pytest.mark.anyio
async def test_lat_long_to_decimal_pure_decimal_with_direction(client):
    resp = await client.post(
        "/api/calculators/lat-long/to-decimal",
        json={"latitude": "33.465 S", "longitude": "112.074 E"},
    )
    data = resp.json()
    assert abs(data["latitude"] - (-33.465)) < 1e-6
    assert abs(data["longitude"] - 112.074) < 1e-6


@pytest.mark.anyio
async def test_lat_long_to_decimal_empty(client):
    resp = await client.post("/api/calculators/lat-long/to-decimal", json={})
    data = resp.json()
    assert data == {
        "latitude": None,
        "longitude": None,
        "latitude_error": None,
        "longitude_error": None,
    }


@pytest.mark.anyio
async def test_lat_long_to_decimal_garbage(client):
    resp = await client.post(
        "/api/calculators/lat-long/to-decimal",
        json={"latitude": "not a coord"},
    )
    data = resp.json()
    assert data["latitude"] is None
    assert data["latitude_error"] is not None
    assert data["longitude"] is None


# ── 3. RA/Dec ⇄ Alt/Az ───────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_radec_altaz_polaris_forward(client, phoenix_location_id):
    # Polaris is very close to the celestial north pole; its altitude must be
    # approximately equal to the observer's latitude regardless of time.
    resp = await client.post(
        "/api/calculators/radec-altaz",
        json={
            "direction": "forward",
            "ra_deg": 37.95,
            "dec_deg": 89.26,
            "timestamp_iso": "2026-06-21T05:00:00Z",
            "location_id": phoenix_location_id,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert abs(data["alt_deg"] - 33.45) < 2.0
    assert data["airmass"] is not None
    assert data["below_horizon"] is False


@pytest.mark.anyio
async def test_radec_altaz_reverse(client, phoenix_location_id):
    # Reverse transform: send a specific Alt/Az, expect sensible RA/Dec back.
    resp = await client.post(
        "/api/calculators/radec-altaz",
        json={
            "direction": "reverse",
            "alt_deg": 60.0,
            "az_deg": 180.0,
            "timestamp_iso": "2026-04-18T04:00:00Z",
            "location_id": phoenix_location_id,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert 0.0 <= data["ra_deg"] < 360.0
    assert -90.0 <= data["dec_deg"] <= 90.0
    assert data["alt_deg"] == 60.0
    assert data["az_deg"] == 180.0
    assert data["airmass"] is not None


@pytest.mark.anyio
async def test_radec_altaz_below_horizon(client, phoenix_location_id):
    resp = await client.post(
        "/api/calculators/radec-altaz",
        json={
            "direction": "reverse",
            "alt_deg": -10.0,
            "az_deg": 90.0,
            "timestamp_iso": "2026-04-18T04:00:00Z",
            "location_id": phoenix_location_id,
        },
    )
    data = resp.json()
    assert data["below_horizon"] is True
    assert data["airmass"] is None


@pytest.mark.anyio
async def test_radec_altaz_location_not_found(client):
    resp = await client.post(
        "/api/calculators/radec-altaz",
        json={
            "direction": "forward",
            "ra_deg": 10.0,
            "dec_deg": 0.0,
            "location_id": 99999,
        },
    )
    assert resp.status_code == 404


# ── 4. Sidereal time ─────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_sidereal_time(client, phoenix_location_id):
    resp = await client.get(
        "/api/calculators/sidereal-time",
        params={
            "location_id": phoenix_location_id,
            "timestamp": "2026-04-18T04:00:00Z",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert 0.0 <= data["lst_hours"] < 24.0
    hh, mm, ss = data["lst_hms"].split(":")
    assert 0 <= int(hh) < 24
    assert 0 <= int(mm) < 60
    assert 0 <= int(ss) < 60
    assert data["utc_iso"].startswith("2026-04-18")


# ── 5. Tonight ───────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_tonight_phoenix(client, phoenix_location_id):
    resp = await client.get(
        "/api/calculators/tonight",
        params={"location_id": phoenix_location_id, "date": "2026-04-18"},
    )
    assert resp.status_code == 200
    data = resp.json()

    # Every field present on the response envelope.
    for key in (
        "date",
        "timezone",
        "sunset",
        "civil_twilight_end",
        "nautical_twilight_end",
        "astronomical_twilight_end",
        "astronomical_twilight_start",
        "nautical_twilight_start",
        "civil_twilight_start",
        "sunrise",
        "moonrise",
        "moonset",
        "moon_illumination_pct",
        "moon_phase_name",
        "astronomical_dark_hours",
        "moonless_dark_hours",
    ):
        assert key in data

    assert data["date"] == "2026-04-18"
    assert data["timezone"] == "America/Phoenix"
    # Phoenix in April has a real sunset & sunrise.
    assert data["sunset"] is not None
    assert data["sunrise"] is not None
    # ~5 hours of astronomical darkness in mid-April.
    assert 2.0 < data["astronomical_dark_hours"] < 10.0
    assert 0.0 <= data["moon_illumination_pct"] <= 100.0


@pytest.mark.anyio
async def test_tonight_default_date(client, phoenix_location_id):
    """Omitting `date` should default to 'today' and still succeed."""
    resp = await client.get(
        "/api/calculators/tonight",
        params={"location_id": phoenix_location_id},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["timezone"] == "America/Phoenix"
    assert len(data["date"]) == 10  # YYYY-MM-DD


# ── 6. Angular units ────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_angular_rad_to_deg(client):
    resp = await client.get(
        "/api/calculators/angular-units/convert",
        params={"value": 1.0, "from": "rad", "to": "deg"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert abs(data["result"] - (180.0 / math.pi)) < 1e-9


@pytest.mark.anyio
async def test_angular_deg_to_arcsec(client):
    resp = await client.get(
        "/api/calculators/angular-units/convert",
        params={"value": 1.0, "from": "deg", "to": "arcsec"},
    )
    data = resp.json()
    assert abs(data["result"] - 3600.0) < 1e-6


@pytest.mark.anyio
async def test_angular_arcmin_to_mas(client):
    resp = await client.get(
        "/api/calculators/angular-units/convert",
        params={"value": 1.0, "from": "arcmin", "to": "mas"},
    )
    data = resp.json()
    assert abs(data["result"] - 60_000.0) < 1e-3
    assert set(data["all_units"].keys()) == {"rad", "deg", "arcmin", "arcsec", "mas"}


# ── 7. Linear units ─────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_linear_m_to_ft(client):
    resp = await client.get(
        "/api/calculators/linear-units/convert",
        params={"value": 1.0, "from": "m", "to": "ft"},
    )
    data = resp.json()
    assert abs(data["result"] - 3.2808398950131233) < 1e-9


@pytest.mark.anyio
async def test_linear_au_to_m(client):
    resp = await client.get(
        "/api/calculators/linear-units/convert",
        params={"value": 1.0, "from": "au", "to": "m"},
    )
    data = resp.json()
    assert abs(data["result"] - 1.495978707e11) < 1e3  # AU exact to 9 digits


# ── 8. Pixel scale ───────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_pixel_scale_asi2600mm_at_540mm(client):
    # ZWO ASI2600MM Pro at 540 mm focal length → 1.436 arcsec/pixel.
    resp = await client.get(
        "/api/calculators/pixel-scale",
        params={"focal_length_mm": 540, "pixel_size_um": 3.76},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert abs(data["arcsec_per_pixel"] - 1.436) < 0.01
    assert data["effective_focal_length_mm"] == 540


@pytest.mark.anyio
async def test_pixel_scale_with_reducer(client):
    resp = await client.get(
        "/api/calculators/pixel-scale",
        params={"focal_length_mm": 540, "pixel_size_um": 3.76, "reducer": 0.8},
    )
    data = resp.json()
    assert abs(data["effective_focal_length_mm"] - 432.0) < 1e-6
    # Reducer → shorter eff focal → larger arcsec/pixel.
    assert abs(data["arcsec_per_pixel"] - (3.76 / 432.0 * 206.265)) < 1e-3


# ── 9. FOV ───────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_fov_sensor_dimensions(client):
    # ASI2600MM sensor 23.5 × 15.7 mm at 540 mm → ~2.49° × 1.66°.
    resp = await client.get(
        "/api/calculators/fov",
        params={
            "focal_length_mm": 540,
            "sensor_width_mm": 23.5,
            "sensor_height_mm": 15.7,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert abs(data["width_deg"] - 2.49) < 0.05
    assert abs(data["height_deg"] - 1.66) < 0.05
    assert data["diagonal_deg"] > data["width_deg"]


@pytest.mark.anyio
async def test_fov_pixel_grid(client):
    resp = await client.get(
        "/api/calculators/fov",
        params={
            "focal_length_mm": 540,
            "pixel_count_x": 6248,
            "pixel_count_y": 4176,
            "pixel_size_um": 3.76,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    # Same sensor: 6248 * 3.76 / 1000 ≈ 23.49 mm
    assert abs(data["width_deg"] - 2.49) < 0.05


@pytest.mark.anyio
async def test_fov_missing_inputs(client):
    resp = await client.get("/api/calculators/fov", params={"focal_length_mm": 540})
    assert resp.status_code == 422


# ── 10. File size ────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_file_size_basic(client):
    resp = await client.get(
        "/api/calculators/file-size",
        params={"width": 6248, "height": 4176, "bit_depth": 16, "frames": 100},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["bytes_per_frame"] == 6248 * 4176 * 2
    assert data["total_bytes"] == data["bytes_per_frame"] * 100
    assert abs(data["megapixels"] - (6248 * 4176 / 1_000_000)) < 1e-6
    assert "MB" in data["per_frame_display"] or "GB" in data["per_frame_display"]
    assert data["total_display"].endswith(("MB", "GB", "TB"))


# ── 11. Airmass ──────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_airmass_zenith(client):
    resp = await client.get("/api/calculators/airmass", params={"altitude_deg": 90})
    assert resp.status_code == 200
    data = resp.json()
    assert abs(data["airmass"] - 1.0) < 1e-3
    # Reference table contains six altitudes.
    alts = [row["altitude_deg"] for row in data["reference_table"]]
    assert alts == [10.0, 20.0, 30.0, 45.0, 60.0, 90.0]


@pytest.mark.anyio
async def test_airmass_30_degrees(client):
    resp = await client.get("/api/calculators/airmass", params={"altitude_deg": 30})
    data = resp.json()
    assert abs(data["airmass"] - 2.0) < 0.02


@pytest.mark.anyio
async def test_airmass_10_degrees(client):
    resp = await client.get("/api/calculators/airmass", params={"altitude_deg": 10})
    data = resp.json()
    assert abs(data["airmass"] - 5.6) < 0.1


@pytest.mark.anyio
async def test_airmass_below_horizon(client):
    resp = await client.get("/api/calculators/airmass", params={"altitude_deg": -5})
    data = resp.json()
    assert data["below_horizon"] is True
    assert data["airmass"] is None


# ── 12. SQM / Bortle / NELM ──────────────────────────────────────────────────


@pytest.mark.anyio
async def test_sqm_bortle_b1(client):
    resp = await client.get("/api/calculators/sqm-bortle", params={"sqm": 21.99})
    assert resp.status_code == 200
    data = resp.json()
    assert data["bortle"] == 1
    assert data["note"] is None
    # NELM check: per spec, SQM=21.9 → NELM ≈ 6.6; 21.99 should be similar.
    assert 6.3 < data["nelm"] < 6.8


@pytest.mark.anyio
async def test_sqm_bortle_b8(client):
    resp = await client.get("/api/calculators/sqm-bortle", params={"sqm": 18.0})
    data = resp.json()
    assert data["bortle"] == 8


@pytest.mark.anyio
async def test_sqm_bortle_nelm_from_sqm(client):
    # Spec pin: SQM 21.9 → NELM ≈ 6.6 (±0.1).
    resp = await client.get("/api/calculators/sqm-bortle", params={"sqm": 21.9})
    data = resp.json()
    assert abs(data["nelm"] - 6.6) < 0.15


@pytest.mark.anyio
async def test_sqm_bortle_from_bortle(client):
    resp = await client.get("/api/calculators/sqm-bortle", params={"bortle": 3})
    data = resp.json()
    assert data["bortle"] == 3
    assert 21.69 <= data["sqm"] <= 21.89


@pytest.mark.anyio
async def test_sqm_bortle_from_nelm(client):
    resp = await client.get("/api/calculators/sqm-bortle", params={"nelm": 6.6})
    data = resp.json()
    # Round-trip: SQM derived from NELM ≈ 21.9.
    assert abs(data["sqm"] - 21.9) < 0.3


@pytest.mark.anyio
async def test_sqm_bortle_clamped(client):
    resp = await client.get("/api/calculators/sqm-bortle", params={"sqm": 30.0})
    data = resp.json()
    assert data["note"] == "clamped"
    assert data["sqm"] == 23.0


@pytest.mark.anyio
async def test_sqm_bortle_precedence(client):
    # sqm > nelm > bortle — supplying all should use SQM.
    resp = await client.get(
        "/api/calculators/sqm-bortle",
        params={"sqm": 21.99, "nelm": 1.0, "bortle": 9},
    )
    data = resp.json()
    assert data["bortle"] == 1  # derived from sqm=21.99


@pytest.mark.anyio
async def test_sqm_bortle_none(client):
    resp = await client.get("/api/calculators/sqm-bortle")
    assert resp.status_code == 422


# ── 13. Temperature ──────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_temperature_c_zero(client):
    resp = await client.get("/api/calculators/temperature", params={"value": 0, "from": "C"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["celsius"] == 0
    assert abs(data["fahrenheit"] - 32.0) < 1e-6
    assert abs(data["kelvin"] - 273.15) < 1e-6


@pytest.mark.anyio
async def test_temperature_f_input(client):
    resp = await client.get("/api/calculators/temperature", params={"value": 212, "from": "F"})
    data = resp.json()
    assert abs(data["celsius"] - 100.0) < 1e-6
    assert abs(data["kelvin"] - 373.15) < 1e-6


@pytest.mark.anyio
async def test_temperature_k_input(client):
    resp = await client.get("/api/calculators/temperature", params={"value": 0, "from": "K"})
    data = resp.json()
    assert abs(data["celsius"] - (-273.15)) < 1e-6
    assert abs(data["fahrenheit"] - (-459.67)) < 1e-6
