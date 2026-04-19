"""Edge-case coverage for the Calculators API + service helpers.

This file complements `test_calculators.py` and intentionally targets the
less-trodden branches: parser fallbacks on malformed lat/lon, out-of-range
validation, empty/garbage inputs, SQM/NELM clamps at the boundary, sidereal
HMS rollover, below-horizon airmass, and 404/422 paths in the API layer.
"""

from __future__ import annotations

import math

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.db.session import get_db
from nightcrate.main import app
from nightcrate.services import calculators as svc


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def phoenix_location_id():
    async with get_db() as conn:
        cursor = await conn.execute(
            """INSERT INTO location (
                name, latitude, longitude, elevation_m, timezone, geo_timezone,
                is_default
            ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                "Phoenix Edge",
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


@pytest.fixture
async def svalbard_location_id():
    """A 78°N location where the sun never sets in mid-June."""
    async with get_db() as conn:
        cursor = await conn.execute(
            """INSERT INTO location (
                name, latitude, longitude, elevation_m, timezone, geo_timezone,
                is_default
            ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                "Svalbard Edge",
                78.22,
                15.65,
                8.0,
                "Arctic/Longyearbyen",
                "Arctic/Longyearbyen",
                0,
            ),
        )
        await conn.commit()
        return cursor.lastrowid


# ── services.calculators direct tests ────────────────────────────────────────


class TestConvertAngularUnknown:
    """Lines 79, 81 — unknown angular unit on either side."""

    def test_from_unit_unknown(self):
        with pytest.raises(ValueError, match="Unknown angular unit"):
            svc.convert_angular(1.0, "bogus", "deg")

    def test_to_unit_unknown(self):
        with pytest.raises(ValueError, match="Unknown angular unit"):
            svc.convert_angular(1.0, "deg", "bogus")


class TestConvertLinearUnknown:
    """Lines 94, 96 — unknown linear unit on either side."""

    def test_from_unit_unknown(self):
        with pytest.raises(ValueError, match="Unknown linear unit"):
            svc.convert_linear(1.0, "bogus", "m")

    def test_to_unit_unknown(self):
        with pytest.raises(ValueError, match="Unknown linear unit"):
            svc.convert_linear(1.0, "m", "bogus")


class TestStripDirection:
    """Lines 119, 125 — empty body and leading-direction with non-alpha next char."""

    def test_empty_string(self):
        assert svc._strip_direction("") == ("", None)

    def test_whitespace_only(self):
        # Strips to empty → returns (text, None) at line 119.
        assert svc._strip_direction("   ") == ("", None)

    def test_leading_direction_followed_by_digit(self):
        # Line 125 branch: first char is N/S/E/W and len>1 and next isn't alpha.
        assert svc._strip_direction("N33") == ("33", "N")
        assert svc._strip_direction("S33.5") == ("33.5", "S")
        assert svc._strip_direction("W-5") == ("-5", "W")

    def test_leading_direction_followed_by_alpha_not_stripped(self):
        # 'North' shouldn't be treated as a direction marker.
        assert svc._strip_direction("No data") == ("No data", None)


class TestParseLatLonStringErrors:
    """Lines 154, 158, 163-164, 166, 170, 172, 179, 181, 189, 195, 197, 201, 204, 212, 215."""

    def test_empty_string(self):
        with pytest.raises(ValueError, match="Empty value"):
            svc.parse_latlon_string("", "lat")

    def test_whitespace_only(self):
        with pytest.raises(ValueError, match="Empty value"):
            svc.parse_latlon_string("   ", "lat")

    def test_direction_only_no_numeric(self):
        # 'E' alone is stripped to '', then body is empty → line 158.
        with pytest.raises(ValueError, match="No numeric value"):
            svc.parse_latlon_string("E", "lat")

    def test_direction_only_W(self):
        with pytest.raises(ValueError, match="No numeric value"):
            svc.parse_latlon_string("W", "lon")

    def test_direction_only_N_on_longitude(self):
        with pytest.raises(ValueError, match="No numeric value"):
            svc.parse_latlon_string("N", "lon")

    def test_garbage_text(self):
        # "not a coord" produces a token "not" that fails float() in _tokenize_angle.
        with pytest.raises(ValueError):
            svc.parse_latlon_string("not a coord", "lat")

    def test_only_unit_markers(self):
        # Degree symbol alone becomes space → no tokens → line 170.
        with pytest.raises(ValueError, match="No numeric components"):
            svc.parse_latlon_string("\u00b0", "lat")

    def test_too_many_components(self):
        # 4 numeric tokens → line 172.
        with pytest.raises(ValueError, match="Too many components"):
            svc.parse_latlon_string("33 27 54 10 N", "lat")

    def test_negative_minutes(self):
        # Line 179 is hit when minutes or seconds come through as negative.
        # The leading "-" is absorbed by the sign handler, but a "- 30" gap
        # lets tokens have a negative minute component.
        with pytest.raises(ValueError, match="non-negative"):
            svc.parse_latlon_string("33 -30 0 N", "lat")

    def test_minutes_out_of_range(self):
        with pytest.raises(ValueError, match="< 60"):
            svc.parse_latlon_string("33 60 0 N", "lat")

    def test_seconds_out_of_range(self):
        with pytest.raises(ValueError, match="< 60"):
            svc.parse_latlon_string("33 0 60 N", "lat")

    def test_negative_degrees_preserves_sign(self):
        # Line 189 (degrees < 0 branch) — signed DMS where degrees carry the sign.
        val = svc.parse_latlon_string("-33 27 54", "lat")
        assert abs(val - (-33.465)) < 1e-6

    def test_leading_plus_sign(self):
        # Line 166 strips a leading '+'.
        val = svc.parse_latlon_string("+33.5", "lat")
        assert val == 33.5

    def test_invalid_direction_for_latitude(self):
        # Line 195 — latitude with E/W direction is rejected.
        with pytest.raises(ValueError, match="Invalid latitude direction"):
            svc.parse_latlon_string("33 E", "lat")

    def test_invalid_direction_for_longitude(self):
        # Line 197 — longitude with N/S direction is rejected.
        with pytest.raises(ValueError, match="Invalid longitude direction"):
            svc.parse_latlon_string("33 N", "lon")

    def test_negative_with_N_direction_conflict(self):
        # Line 201 — "-33 N" is a sign/direction contradiction.
        with pytest.raises(ValueError, match="conflicts with direction"):
            svc.parse_latlon_string("-33 N", "lat")

    def test_negative_with_E_direction_conflict(self):
        with pytest.raises(ValueError, match="conflicts with direction"):
            svc.parse_latlon_string("-33 E", "lon")

    def test_negative_with_S_redundant_but_accepted(self):
        # Line 204 — "-33 S" is redundant; implementation keeps the magnitude.
        val = svc.parse_latlon_string("-33 S", "lat")
        assert val == -33.0

    def test_negative_with_W_redundant_but_accepted(self):
        val = svc.parse_latlon_string("-33 W", "lon")
        assert val == -33.0

    def test_latitude_out_of_range(self):
        # Line 212 — "95 N" decimal is caught by the final range check.
        with pytest.raises(ValueError, match="Latitude out of range"):
            svc.parse_latlon_string("95 N", "lat")

    def test_latitude_out_of_range_dms(self):
        with pytest.raises(ValueError, match="Latitude out of range"):
            svc.parse_latlon_string("95 0 0 N", "lat")

    def test_longitude_out_of_range(self):
        # Line 215 — 181 E is outside ±180°.
        with pytest.raises(ValueError, match="Longitude out of range"):
            svc.parse_latlon_string("181 E", "lon")


class TestParseLatLonStringHappy:
    """Inputs that walk happy branches we haven't exercised elsewhere."""

    def test_decimal_with_direction_N(self):
        assert svc.parse_latlon_string("33.5 N", "lat") == 33.5

    def test_decimal_with_direction_S(self):
        assert svc.parse_latlon_string("33.5 S", "lat") == -33.5

    def test_dms_with_symbols(self):
        val = svc.parse_latlon_string("33\u00b027'54\" N", "lat")
        assert abs(val - 33.465) < 1e-6

    def test_dms_with_letters(self):
        val = svc.parse_latlon_string("33d27m54s N", "lat")
        assert abs(val - 33.465) < 1e-6

    def test_whitespace_tolerant(self):
        val = svc.parse_latlon_string("  33  27  54  N  ", "lat")
        assert abs(val - 33.465) < 1e-6

    def test_leading_direction(self):
        # Exercises _strip_direction first-char branch.
        val = svc.parse_latlon_string("N33 27 54", "lat")
        assert abs(val - 33.465) < 1e-6


class TestParseLatLonComponents:
    """Lines 229, 234, 236, 240, 245, 247, 253, 255."""

    def test_missing_degrees(self):
        with pytest.raises(ValueError, match="Degrees required"):
            svc.parse_latlon_components(None, 10, 0, "N", "lat")

    def test_negative_minutes(self):
        with pytest.raises(ValueError, match="non-negative"):
            svc.parse_latlon_components(30, -5, 0, "N", "lat")

    def test_negative_seconds(self):
        with pytest.raises(ValueError, match="non-negative"):
            svc.parse_latlon_components(30, 0, -5, "N", "lat")

    def test_minutes_gte_60(self):
        with pytest.raises(ValueError, match="< 60"):
            svc.parse_latlon_components(30, 60, 0, "N", "lat")

    def test_seconds_gte_60(self):
        with pytest.raises(ValueError, match="< 60"):
            svc.parse_latlon_components(30, 0, 60, "N", "lat")

    def test_negative_degrees_branch(self):
        # Line 240 — degrees < 0 preserves sign through the components path.
        val = svc.parse_latlon_components(-33, 27, 54, None, "lat")
        assert abs(val - (-33.465)) < 1e-6

    def test_direction_east_on_latitude(self):
        with pytest.raises(ValueError, match="Invalid latitude direction"):
            svc.parse_latlon_components(33, 0, 0, "E", "lat")

    def test_direction_north_on_longitude(self):
        with pytest.raises(ValueError, match="Invalid longitude direction"):
            svc.parse_latlon_components(100, 0, 0, "N", "lon")

    def test_latitude_out_of_range(self):
        with pytest.raises(ValueError, match="Latitude out of range"):
            svc.parse_latlon_components(95, 0, 0, "N", "lat")

    def test_longitude_out_of_range(self):
        with pytest.raises(ValueError, match="Longitude out of range"):
            svc.parse_latlon_components(181, 0, 0, "E", "lon")


class TestServiceMathGuards:
    """Lines 400, 423, 446, 458, 465, 491, 499, 535 — raw ValueError paths."""

    def test_pixel_scale_zero_focal_length(self):
        with pytest.raises(ValueError, match="must be positive"):
            svc.pixel_scale(0.0, 3.76, 1.0)

    def test_pixel_scale_zero_pixel_size(self):
        with pytest.raises(ValueError, match="must be positive"):
            svc.pixel_scale(540.0, 0.0, 1.0)

    def test_pixel_scale_zero_reducer(self):
        with pytest.raises(ValueError, match="must be positive"):
            svc.pixel_scale(540.0, 3.76, 0.0)

    def test_pixel_scale_negative_focal_length(self):
        with pytest.raises(ValueError, match="must be positive"):
            svc.pixel_scale(-540.0, 3.76, 1.0)

    def test_field_of_view_zero_inputs(self):
        with pytest.raises(ValueError, match="must be positive"):
            svc.field_of_view(0.0, 23.5, 15.7)

    def test_field_of_view_negative_sensor(self):
        with pytest.raises(ValueError, match="must be positive"):
            svc.field_of_view(540.0, -23.5, 15.7)

    def test_sensor_from_pixels_zero_x(self):
        with pytest.raises(ValueError, match="must be positive"):
            svc.sensor_from_pixels(0, 4000, 3.76)

    def test_sensor_from_pixels_zero_y(self):
        with pytest.raises(ValueError, match="must be positive"):
            svc.sensor_from_pixels(6000, 0, 3.76)

    def test_sensor_from_pixels_zero_size(self):
        with pytest.raises(ValueError, match="must be positive"):
            svc.sensor_from_pixels(6000, 4000, 0.0)

    def test_format_bytes_negative(self):
        # Line 458 — recursive negative branch.
        assert svc.format_bytes(-1024) == "-1.00 KB"

    def test_format_bytes_terabyte_and_above(self):
        # Line 465 — loop fall-through for the largest suffix.
        # 2 PB is beyond the suffixes list range.
        assert svc.format_bytes(1024**5 * 2).endswith(" PB")

    def test_bortle_to_sqm_out_of_range(self):
        # Line 499 — bortle outside 1..9.
        with pytest.raises(ValueError, match="Bortle out of range"):
            svc.bortle_to_sqm(99)

    def test_sqm_to_bortle_at_b9_lower_edge(self):
        # Line 491 is the "unreachable" fallback; we can still verify the
        # closest-neighbour behaviour through the normal band lookup.
        assert svc.sqm_to_bortle(17.79) == 9
        # 17.80 is the B8 lower bound (inclusive).
        assert svc.sqm_to_bortle(17.80) == 8

    def test_temperature_unknown_unit(self):
        with pytest.raises(ValueError, match="Unknown temperature unit"):
            svc.temperature_all(10.0, "Z")


class TestParseTimestamp:
    """Lines 291, 296 — tz-absent and tz-aware branches of _parse_timestamp."""

    def test_zulu_suffix(self):
        t = svc._parse_timestamp("2026-04-18T04:00:00Z")
        assert t is not None

    def test_naive_iso_defaults_to_utc(self):
        t = svc._parse_timestamp("2026-04-18T04:00:00")
        assert t is not None

    def test_tz_aware_iso(self):
        t = svc._parse_timestamp("2026-04-18T06:00:00+02:00")
        assert t is not None

    def test_none_uses_now(self):
        t = svc._parse_timestamp(None)
        assert t is not None

    def test_malformed_raises(self):
        with pytest.raises(ValueError):
            svc._parse_timestamp("not-a-timestamp")


class TestLocalSiderealRollover:
    """Lines 379-380, 382-383 — 60-second and 60-minute rounding rollover."""

    def test_double_rollover(self):
        # This timestamp produces LST close enough to an exact hour that the
        # integer-rounded seconds tick 60 → 0 AND the minutes tick 60 → 0.
        # Value computed once and pinned.
        _, hms, _ = svc.local_sidereal_time(0.0, "2026-04-18T00:15:27Z")
        assert hms == "14:00:00"

    def test_seconds_only_rollover(self):
        _, hms, _ = svc.local_sidereal_time(0.0, "2026-04-18T00:01:29Z")
        # Seconds rolled from 60 to 0, minutes += 1.
        hh, mm, ss = hms.split(":")
        assert int(ss) == 0


# ── API-level edge tests ─────────────────────────────────────────────────────


# --- Lat/Lon → decimal POST endpoint ------------------------------------------


class TestLatLonToDecimalApi:
    """Exercises api.calculators:_resolve_latlon_side branches (lines 151-152)."""

    @pytest.mark.anyio
    async def test_garbage_string(self, client):
        resp = await client.post(
            "/api/calculators/lat-long/to-decimal",
            json={"latitude": "not a coord"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["latitude"] is None
        assert data["latitude_error"] is not None

    @pytest.mark.anyio
    async def test_latitude_out_of_range_string(self, client):
        resp = await client.post(
            "/api/calculators/lat-long/to-decimal",
            json={"latitude": "95 N"},
        )
        data = resp.json()
        assert data["latitude"] is None
        assert "out of range" in data["latitude_error"].lower()

    @pytest.mark.anyio
    async def test_longitude_out_of_range_string(self, client):
        resp = await client.post(
            "/api/calculators/lat-long/to-decimal",
            json={"longitude": "181 E"},
        )
        data = resp.json()
        assert data["longitude"] is None
        assert "out of range" in data["longitude_error"].lower()

    @pytest.mark.anyio
    async def test_components_out_of_range_seconds(self, client):
        # Hits the components branch then ValueError (line 151-152).
        resp = await client.post(
            "/api/calculators/lat-long/to-decimal",
            json={
                "latitude_deg": 33,
                "latitude_min": 0,
                "latitude_sec": 60,
                "latitude_direction": "N",
            },
        )
        data = resp.json()
        assert data["latitude"] is None
        assert data["latitude_error"] is not None

    @pytest.mark.anyio
    async def test_components_out_of_range_minutes(self, client):
        resp = await client.post(
            "/api/calculators/lat-long/to-decimal",
            json={
                "longitude_deg": 100,
                "longitude_min": 60,
                "longitude_sec": 0,
                "longitude_direction": "E",
            },
        )
        data = resp.json()
        assert data["longitude"] is None
        assert data["longitude_error"] is not None

    @pytest.mark.anyio
    async def test_components_missing_degrees(self, client):
        # Direction alone triggers the components branch without deg.
        resp = await client.post(
            "/api/calculators/lat-long/to-decimal",
            json={"latitude_direction": "N"},
        )
        data = resp.json()
        assert data["latitude"] is None
        assert "degrees" in data["latitude_error"].lower()

    @pytest.mark.anyio
    async def test_empty_payload_returns_all_none(self, client):
        resp = await client.post("/api/calculators/lat-long/to-decimal", json={})
        assert resp.status_code == 200
        assert resp.json() == {
            "latitude": None,
            "longitude": None,
            "latitude_error": None,
            "longitude_error": None,
        }


# --- RA/Dec ⇄ Alt/Az POST endpoint --------------------------------------------


class TestRaDecAltAzApi:
    """Lines 223, 230, 235-238 in api/calculators.py."""

    @pytest.mark.anyio
    async def test_forward_missing_ra(self, client, phoenix_location_id):
        resp = await client.post(
            "/api/calculators/radec-altaz",
            json={
                "direction": "forward",
                "dec_deg": 0.0,
                "location_id": phoenix_location_id,
            },
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_forward_missing_dec(self, client, phoenix_location_id):
        resp = await client.post(
            "/api/calculators/radec-altaz",
            json={
                "direction": "forward",
                "ra_deg": 0.0,
                "location_id": phoenix_location_id,
            },
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_reverse_missing_alt(self, client, phoenix_location_id):
        resp = await client.post(
            "/api/calculators/radec-altaz",
            json={
                "direction": "reverse",
                "az_deg": 180.0,
                "location_id": phoenix_location_id,
            },
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_reverse_missing_az(self, client, phoenix_location_id):
        resp = await client.post(
            "/api/calculators/radec-altaz",
            json={
                "direction": "reverse",
                "alt_deg": 45.0,
                "location_id": phoenix_location_id,
            },
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_invalid_direction_value(self, client, phoenix_location_id):
        resp = await client.post(
            "/api/calculators/radec-altaz",
            json={
                "direction": "sideways",
                "ra_deg": 0,
                "dec_deg": 0,
                "location_id": phoenix_location_id,
            },
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_malformed_timestamp(self, client, phoenix_location_id):
        resp = await client.post(
            "/api/calculators/radec-altaz",
            json={
                "direction": "forward",
                "ra_deg": 10.0,
                "dec_deg": 10.0,
                "timestamp_iso": "definitely-not-a-time",
                "location_id": phoenix_location_id,
            },
        )
        # _parse_timestamp raises ValueError → mapped to 422 (lines 237-238).
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_location_not_found(self, client):
        resp = await client.post(
            "/api/calculators/radec-altaz",
            json={
                "direction": "forward",
                "ra_deg": 10.0,
                "dec_deg": 10.0,
                "location_id": 999_999,
            },
        )
        # Line 81 in api/calculators.py.
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_forward_below_horizon(self, client, phoenix_location_id):
        # Pick an RA/Dec that's below Phoenix's horizon at the given UTC time.
        # Southern polar region from a northern observer is always below horizon.
        resp = await client.post(
            "/api/calculators/radec-altaz",
            json={
                "direction": "forward",
                "ra_deg": 0.0,
                "dec_deg": -89.0,
                "timestamp_iso": "2026-04-18T04:00:00Z",
                "location_id": phoenix_location_id,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["below_horizon"] is True
        assert data["airmass"] is None


# --- Sidereal time -----------------------------------------------------------


class TestSiderealTimeApi:
    """Lines 268-269."""

    @pytest.mark.anyio
    async def test_unknown_location(self, client):
        resp = await client.get(
            "/api/calculators/sidereal-time",
            params={"location_id": 999_999},
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_malformed_timestamp(self, client, phoenix_location_id):
        resp = await client.get(
            "/api/calculators/sidereal-time",
            params={
                "location_id": phoenix_location_id,
                "timestamp": "bad-timestamp",
            },
        )
        # ValueError bubbles to HTTP 422 via lines 268-269.
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_absent_timestamp_uses_now(self, client, phoenix_location_id):
        resp = await client.get(
            "/api/calculators/sidereal-time",
            params={"location_id": phoenix_location_id},
        )
        assert resp.status_code == 200
        hh, mm, ss = resp.json()["lst_hms"].split(":")
        assert 0 <= int(hh) < 24
        assert 0 <= int(mm) < 60
        assert 0 <= int(ss) < 60


# --- Tonight -----------------------------------------------------------------


class TestTonightApi:
    """Lines 312-313, 323-324."""

    @pytest.mark.anyio
    async def test_unknown_location(self, client):
        resp = await client.get(
            "/api/calculators/tonight",
            params={"location_id": 999_999},
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_invalid_date_format(self, client, phoenix_location_id):
        resp = await client.get(
            "/api/calculators/tonight",
            params={"location_id": phoenix_location_id, "date": "2026/05/01"},
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_polar_summer_no_sunset(self, client, svalbard_location_id):
        # Svalbard in mid-June: sun never sets. compute_night_summary either
        # returns None-filled timings or raises; either way the response
        # should be well-formed. If it raises, the API maps to 422.
        resp = await client.get(
            "/api/calculators/tonight",
            params={"location_id": svalbard_location_id, "date": "2026-06-21"},
        )
        assert resp.status_code in (200, 422)
        if resp.status_code == 200:
            data = resp.json()
            assert data["timezone"] == "Arctic/Longyearbyen"
            assert data["date"] == "2026-06-21"


# --- Angular / Linear unit converters ----------------------------------------


class TestUnitConvertApi:
    """Lines 365, 387 — Literal enforcement at the query layer already returns
    422 before reaching those in-function checks, so we assert at the HTTP
    boundary. The valid-input happy paths also exercise edge values."""

    @pytest.mark.anyio
    async def test_angular_unknown_from(self, client):
        resp = await client.get(
            "/api/calculators/angular-units/convert",
            params={"value": 1.0, "from": "bogus", "to": "deg"},
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_angular_unknown_to(self, client):
        resp = await client.get(
            "/api/calculators/angular-units/convert",
            params={"value": 1.0, "from": "deg", "to": "bogus"},
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_angular_value_missing(self, client):
        resp = await client.get(
            "/api/calculators/angular-units/convert",
            params={"from": "deg", "to": "rad"},
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_angular_zero(self, client):
        resp = await client.get(
            "/api/calculators/angular-units/convert",
            params={"value": 0.0, "from": "deg", "to": "rad"},
        )
        assert resp.status_code == 200
        assert resp.json()["result"] == 0.0

    @pytest.mark.anyio
    async def test_angular_negative(self, client):
        resp = await client.get(
            "/api/calculators/angular-units/convert",
            params={"value": -5.0, "from": "deg", "to": "rad"},
        )
        data = resp.json()
        assert abs(data["result"] - (-5.0 * math.pi / 180.0)) < 1e-9

    @pytest.mark.anyio
    async def test_linear_unknown_from(self, client):
        resp = await client.get(
            "/api/calculators/linear-units/convert",
            params={"value": 1.0, "from": "bogus", "to": "m"},
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_linear_unknown_to(self, client):
        resp = await client.get(
            "/api/calculators/linear-units/convert",
            params={"value": 1.0, "from": "m", "to": "bogus"},
        )
        assert resp.status_code == 422


# --- Pixel scale / FOV / file size -------------------------------------------


class TestOpticalEndpoints:
    """Lines 415-416, 448-449, 461-462."""

    @pytest.mark.anyio
    async def test_pixel_scale_zero_focal_length(self, client):
        resp = await client.get(
            "/api/calculators/pixel-scale",
            params={"focal_length_mm": 0, "pixel_size_um": 3.76},
        )
        # Query-level gt=0 catches this.
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_pixel_scale_negative(self, client):
        resp = await client.get(
            "/api/calculators/pixel-scale",
            params={"focal_length_mm": -540, "pixel_size_um": 3.76},
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_pixel_scale_zero_pixel_size(self, client):
        resp = await client.get(
            "/api/calculators/pixel-scale",
            params={"focal_length_mm": 540, "pixel_size_um": 0},
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_pixel_scale_zero_reducer(self, client):
        resp = await client.get(
            "/api/calculators/pixel-scale",
            params={"focal_length_mm": 540, "pixel_size_um": 3.76, "reducer": 0},
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_fov_no_inputs(self, client):
        resp = await client.get(
            "/api/calculators/fov",
            params={"focal_length_mm": 540},
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_fov_partial_sensor_dims_width_only(self, client):
        resp = await client.get(
            "/api/calculators/fov",
            params={"focal_length_mm": 540, "sensor_width_mm": 23.5},
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_fov_partial_sensor_dims_height_only(self, client):
        resp = await client.get(
            "/api/calculators/fov",
            params={"focal_length_mm": 540, "sensor_height_mm": 15.7},
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_fov_pixel_path_zero_pixel_size(self, client):
        resp = await client.get(
            "/api/calculators/fov",
            params={
                "focal_length_mm": 540,
                "pixel_count_x": 6000,
                "pixel_count_y": 4000,
                "pixel_size_um": 0,
            },
        )
        # Query-level gt=0 catches this before the service does.
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_fov_pixel_path_missing_pixel_size(self, client):
        # pixel counts present but pixel_size_um missing → fallthrough else.
        resp = await client.get(
            "/api/calculators/fov",
            params={
                "focal_length_mm": 540,
                "pixel_count_x": 6000,
                "pixel_count_y": 4000,
            },
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_file_size_zero_frames(self, client):
        resp = await client.get(
            "/api/calculators/file-size",
            params={"width": 100, "height": 100, "bit_depth": 16, "frames": 0},
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_file_size_negative_frames(self, client):
        resp = await client.get(
            "/api/calculators/file-size",
            params={"width": 100, "height": 100, "bit_depth": 16, "frames": -1},
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_file_size_zero_compression(self, client):
        resp = await client.get(
            "/api/calculators/file-size",
            params={
                "width": 100,
                "height": 100,
                "bit_depth": 16,
                "compression": 0,
            },
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_file_size_huge_value_formats_tb(self, client):
        resp = await client.get(
            "/api/calculators/file-size",
            params={
                "width": 100_000,
                "height": 100_000,
                "bit_depth": 32,
                "frames": 10_000,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_display"].endswith(" TB") or data["total_display"].endswith(" PB")
        # Bytes arithmetic shouldn't overflow int.
        assert data["total_bytes"] == 100_000 * 100_000 * 4 * 10_000


# --- Airmass edge cases ------------------------------------------------------


class TestAirmassApi:
    @pytest.mark.anyio
    async def test_airmass_at_horizon(self, client):
        resp = await client.get("/api/calculators/airmass", params={"altitude_deg": 0})
        assert resp.status_code == 200
        data = resp.json()
        assert data["below_horizon"] is True
        assert data["airmass"] is None

    @pytest.mark.anyio
    async def test_airmass_just_above_horizon(self, client):
        resp = await client.get("/api/calculators/airmass", params={"altitude_deg": 0.01})
        data = resp.json()
        assert data["below_horizon"] is False
        assert data["airmass"] is not None and data["airmass"] > 10.0

    @pytest.mark.anyio
    async def test_airmass_zenith_rounding(self, client):
        resp = await client.get("/api/calculators/airmass", params={"altitude_deg": 90})
        assert abs(resp.json()["airmass"] - 1.0) < 1e-3

    @pytest.mark.anyio
    async def test_airmass_out_of_range(self, client):
        resp = await client.get("/api/calculators/airmass", params={"altitude_deg": 91})
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_airmass_reference_table_shape(self, client):
        resp = await client.get("/api/calculators/airmass", params={"altitude_deg": 45})
        ref = resp.json()["reference_table"]
        assert len(ref) == 6
        assert [row["altitude_deg"] for row in ref] == [10.0, 20.0, 30.0, 45.0, 60.0, 90.0]


# --- SQM / Bortle / NELM -----------------------------------------------------


class TestSqmBortleNelmApi:
    """Lines 574-575 (nelm clamp) — the clamped branch for NELM outside [0, 8]."""

    @pytest.mark.anyio
    async def test_nelm_clamped_high(self, client):
        # nelm=8.5 exceeds the supported range → clamped to 8.0.
        resp = await client.get("/api/calculators/sqm-bortle", params={"nelm": 8.5})
        assert resp.status_code == 200
        data = resp.json()
        assert data["note"] == "clamped"
        # Clamped to 8.0, which maps to ~22.0 SQM.
        assert abs(data["sqm"] - 22.0) < 0.5

    @pytest.mark.anyio
    async def test_nelm_in_range_not_clamped(self, client):
        # nelm=3.0 is inside [0, 8] — no clamp.
        resp = await client.get("/api/calculators/sqm-bortle", params={"nelm": 3.0})
        data = resp.json()
        assert data["note"] is None
        assert data["bortle"] == 9

    @pytest.mark.anyio
    async def test_nelm_roundtrip(self, client):
        # NELM → SQM → NELM should round-trip closely.
        resp = await client.get("/api/calculators/sqm-bortle", params={"nelm": 6.5})
        data = resp.json()
        assert abs(data["nelm"] - 6.5) < 0.1

    @pytest.mark.anyio
    async def test_sqm_clamped_low(self, client):
        resp = await client.get("/api/calculators/sqm-bortle", params={"sqm": 10})
        data = resp.json()
        assert data["note"] == "clamped"
        assert data["sqm"] == 14.0

    @pytest.mark.anyio
    async def test_sqm_clamped_high(self, client):
        resp = await client.get("/api/calculators/sqm-bortle", params={"sqm": 25})
        data = resp.json()
        assert data["note"] == "clamped"
        assert data["sqm"] == 23.0

    @pytest.mark.anyio
    async def test_bortle_midpoint(self, client):
        # Bortle 4 band midpoint from the _BORTLE_BANDS table is 21.09.
        resp = await client.get("/api/calculators/sqm-bortle", params={"bortle": 4})
        data = resp.json()
        assert data["bortle"] == 4
        assert abs(data["sqm"] - 21.09) < 1e-6

    @pytest.mark.anyio
    async def test_sqm_17_79_is_bortle_9(self, client):
        resp = await client.get("/api/calculators/sqm-bortle", params={"sqm": 17.79})
        assert resp.json()["bortle"] == 9

    @pytest.mark.anyio
    async def test_sqm_21_99_is_bortle_1(self, client):
        resp = await client.get("/api/calculators/sqm-bortle", params={"sqm": 21.99})
        assert resp.json()["bortle"] == 1

    @pytest.mark.anyio
    async def test_sqm_21_989_is_bortle_2(self, client):
        # Just under the B1/B2 boundary of 21.99.
        resp = await client.get("/api/calculators/sqm-bortle", params={"sqm": 21.989})
        assert resp.json()["bortle"] == 2

    @pytest.mark.anyio
    async def test_precedence_sqm_over_bortle(self, client):
        # With both sqm and bortle supplied, SQM wins.
        resp = await client.get(
            "/api/calculators/sqm-bortle",
            params={"sqm": 18, "bortle": 1},
        )
        data = resp.json()
        # sqm=18 → Bortle 8, ignoring the user's bortle=1 hint.
        assert data["bortle"] == 8

    @pytest.mark.anyio
    async def test_no_inputs(self, client):
        resp = await client.get("/api/calculators/sqm-bortle")
        assert resp.status_code == 422


# --- Temperature -------------------------------------------------------------


class TestTemperatureApi:
    """Lines 609-610 — ValueError → 422 (unreachable via HTTP due to Literal
    validation, but the valid-unit edge cases still add useful coverage)."""

    @pytest.mark.anyio
    async def test_kelvin_zero(self, client):
        resp = await client.get(
            "/api/calculators/temperature",
            params={"value": 0, "from": "K"},
        )
        data = resp.json()
        assert abs(data["celsius"] - (-273.15)) < 1e-6
        assert abs(data["fahrenheit"] - (-459.67)) < 1e-2

    @pytest.mark.anyio
    async def test_celsius_absolute_zero(self, client):
        resp = await client.get(
            "/api/calculators/temperature",
            params={"value": -273.15, "from": "C"},
        )
        data = resp.json()
        assert abs(data["kelvin"] - 0.0) < 1e-6

    @pytest.mark.anyio
    async def test_invalid_unit(self, client):
        resp = await client.get(
            "/api/calculators/temperature",
            params={"value": 10, "from": "Z"},
        )
        # Pydantic Literal enforces 422 before reaching the service.
        assert resp.status_code == 422
