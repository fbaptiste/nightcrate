"""Smoke tests for the Target Planner sky-track service."""

from __future__ import annotations

from datetime import date

import pytest

from nightcrate.services.planner_sky_track import compute_sky_track
from nightcrate.services.planner_visibility import PlannerHorizon, PlannerLocation

PHOENIX = PlannerLocation(
    id=1,
    latitude_deg=33.4484,
    longitude_deg=-112.0740,
    elevation_m=331.0,
    timezone="America/Phoenix",
    updated_at="2026-04-01T00:00:00",
)


def _artificial(flat_alt: float, horizon_id: int = 1) -> PlannerHorizon:
    return PlannerHorizon(
        id=horizon_id,
        location_id=PHOENIX.id,
        name=f"{flat_alt:g}° flat",
        type="artificial",
        flat_altitude_deg=flat_alt,
        points=(),
        updated_at="2026-04-01T00:00:00",
    )


FLAT_30 = _artificial(30.0)

M42 = (1, 83.8221, -5.3911)


@pytest.fixture(scope="module")
def track():
    return compute_sky_track(PHOENIX, FLAT_30, date(2026, 4, 19), M42)


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
    assert len(track.moon_azimuth_deg) == n
    assert len(track.moon_separation_deg) == n
    assert len(track.horizon_altitude_at_object_az) == n


def test_moon_azimuth_in_range(track):
    # Azimuth is a compass bearing measured 0 = N, increasing through E.
    assert all(0.0 <= az < 360.0 for az in track.moon_azimuth_deg)


def test_moon_azimuth_pinned(track):
    # Pinned against the computed track for Phoenix on 2026-04-19: the
    # Moon starts the night low in the west (~280°) and has swung round
    # to the NE (~37°) by the post-dawn edge of the display window.
    assert track.moon_azimuth_deg[0] == pytest.approx(280.11, abs=0.5)
    assert track.moon_azimuth_deg[-1] == pytest.approx(36.9, abs=0.5)


def test_horizon_flat_when_artificial(track):
    # All values should be exactly the artificial horizon's altitude.
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


def test_moon_separation_varies_across_night(track):
    # Regression guard for the GCRS-distance separation bug: the buggy
    # code transformed the distance-bearing Moon into the target's ICRS
    # frame, shifting the origin ~1 AU and freezing the separation
    # (range < 0.3° across a whole night, value ~3-4x too large). The
    # correct on-sky separation moves by several degrees as the Moon
    # tracks along its orbit + parallax. See astronomy.direction_only.
    sep = track.moon_separation_deg
    assert max(sep) - min(sep) > 1.0


def test_moon_separation_pinned(track):
    # Hand-verified corrected values for M42 from Phoenix on 2026-04-19
    # (distance stripped). The pre-fix bug reported ~122° here, frozen.
    assert track.moon_separation_deg[0] == pytest.approx(37.85, abs=0.5)
    assert track.moon_separation_deg[-1] == pytest.approx(34.32, abs=0.5)


def test_custom_horizon_flows_through_to_track():
    horizon_points = tuple(
        (float(az), 40.0 if 90.0 <= az <= 270.0 else 10.0) for az in range(0, 360, 10)
    )
    custom = PlannerHorizon(
        id=2,
        location_id=PHOENIX.id,
        name="Custom horizon",
        type="custom",
        flat_altitude_deg=None,
        points=horizon_points,
        updated_at="2026-04-01T00:00:00",
    )
    t = compute_sky_track(PHOENIX, custom, date(2026, 4, 19), M42)
    # Horizon altitude now varies per-sample (south ~40°, north ~10°).
    values = {round(v, 0) for v in t.horizon_altitude_at_object_az}
    assert len(values) > 1
