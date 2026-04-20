"""Smoke tests for the Target Planner sky-track service."""

from __future__ import annotations

from datetime import date

import pytest

from nightcrate.services.planner_sky_track import compute_sky_track
from nightcrate.services.planner_visibility import PlannerLocation

PHOENIX = PlannerLocation(
    id=1,
    latitude_deg=33.4484,
    longitude_deg=-112.0740,
    elevation_m=331.0,
    timezone="America/Phoenix",
    updated_at="2026-04-01T00:00:00",
)

M42 = (1, 83.8221, -5.3911)


@pytest.fixture(scope="module")
def track():
    return compute_sky_track(PHOENIX, date(2026, 4, 19), M42, flat_min_altitude_deg=30.0)


def test_has_roughly_180_samples(track):
    # Window is ~ civil dusk − 30 min to civil dawn + 30 min with 5-minute
    # spacing. Phoenix in April is ~12h which is ~144 samples plus the
    # 60-minute padding (another 12), call it 150–210.
    n = len(track.times_utc)
    assert 120 <= n <= 250


def test_all_parallel_arrays_same_length(track):
    n = len(track.times_utc)
    assert len(track.object_altitude_deg) == n
    assert len(track.object_azimuth_deg) == n
    assert len(track.moon_altitude_deg) == n
    assert len(track.horizon_altitude_at_object_az) == n


def test_horizon_flat_when_no_custom_horizon(track):
    # All values should be exactly the passed-in flat min.
    assert set(track.horizon_altitude_at_object_az) == {30.0}


def test_twilight_bands_have_core_boundaries(track):
    bands = track.twilight
    # Phoenix isn't polar; every twilight phase resolves.
    assert bands.sunset_utc is not None
    assert bands.civil_end_utc is not None
    assert bands.astro_start_utc is not None
    assert bands.astro_end_utc is not None
    assert bands.sunrise_utc is not None


def test_moon_phase_populated(track):
    assert 0.0 <= track.moon_phase_pct <= 100.0


def test_custom_horizon_flows_through_to_track():
    from dataclasses import replace

    blocked = replace(
        PHOENIX,
        horizon_points=tuple(
            (float(az), 40.0 if 90.0 <= az <= 270.0 else 10.0) for az in range(0, 360, 10)
        ),
        horizon_updated_at="2026-04-01T00:00:00",
    )
    t = compute_sky_track(blocked, date(2026, 4, 19), M42, flat_min_altitude_deg=30.0)
    # Horizon altitude now varies per-sample (south ~40°, north ~10°).
    values = set(round(v, 0) for v in t.horizon_altitude_at_object_az)
    assert len(values) > 1
