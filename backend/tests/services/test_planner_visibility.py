"""Tests for the Target Planner visibility engine."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import astropy.units as u_astro
import numpy as np
import pytest
from astropy.coordinates import AltAz, EarthLocation, SkyCoord
from astropy.time import Time

from nightcrate.services.planner_visibility import (
    DsoCoord,
    PlannerHorizon,
    PlannerLocation,
    VisibilityCache,
    compute_visibility_snapshot,
)

# Phoenix, AZ on an April night — astro-dark window is roughly 5–6 hours
# this time of year, plenty for a robust regression test.
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


def _custom(points: tuple[tuple[float, float], ...], horizon_id: int = 2) -> PlannerHorizon:
    return PlannerHorizon(
        id=horizon_id,
        location_id=PHOENIX.id,
        name="Custom horizon",
        type="custom",
        flat_altitude_deg=None,
        points=points,
        updated_at="2026-04-01T00:00:00",
    )


FLAT_30 = _artificial(30.0, horizon_id=1)


# M42 (Orion Nebula) — RA/Dec from OpenNGC
M42 = DsoCoord(dso_id=1, ra_deg=83.8221, dec_deg=-5.3911, maj_axis_arcmin=65.0)

# M31 (Andromeda) — well-positioned in April evening skies from Phoenix
M31 = DsoCoord(dso_id=2, ra_deg=10.6847, dec_deg=41.2687, maj_axis_arcmin=190.0)

# A deep southern target — never rises from Phoenix
CROSS = DsoCoord(dso_id=3, ra_deg=186.65, dec_deg=-63.1, maj_axis_arcmin=90.0)

# M51 (Whirlpool) — RA 13h30m, Dec +47°. At Phoenix on 2026-04-19 its
# meridian crossing (LST ≈ 13.5h) falls inside the astro-dark window
# (which runs roughly 08:30 PM → 04:21 AM local / LST 07:50 → 15:41).
M51 = DsoCoord(dso_id=4, ra_deg=202.4696, dec_deg=47.1953, maj_axis_arcmin=11.2)

# M8 (Lagoon) — RA 18h03m, Dec −24°. At Phoenix on 2026-04-19 it
# transits at LST ≈ 18h, which lands after astro-dark ends.
M8 = DsoCoord(dso_id=5, ra_deg=270.917, dec_deg=-24.387, maj_axis_arcmin=90.0)


def _snapshot(dsos, *, horizon: PlannerHorizon = FLAT_30):
    return compute_visibility_snapshot(
        PHOENIX,
        horizon,
        date(2026, 4, 19),
        dsos,
    )


def test_snapshot_has_dark_window_and_moon_phase():
    snap = _snapshot([M42])
    assert snap.dark_window.start_utc is not None
    assert snap.dark_window.end_utc is not None
    assert snap.dark_window.hours > 0
    assert snap.dark_window.hours < 12  # sanity — this isn't a polar site
    assert 0.0 <= snap.moon_phase_pct <= 100.0


def test_southern_target_never_visible():
    """Crux is at Dec ≈ −60°; from Phoenix (lat 33°) it never rises above
    the horizon, let alone the 30° minimum."""
    snap = _snapshot([CROSS])
    vis = snap.per_dso[CROSS.dso_id]
    assert vis.hours_visible == 0.0
    assert vis.max_altitude_deg < 30.0
    assert vis.min_moon_separation_deg is None
    assert vis.rise_time_utc is None
    assert vis.set_time_utc is None


def test_hours_visible_and_peak_sanity():
    snap = _snapshot([M42, M31])
    m42 = snap.per_dso[M42.dso_id]
    m31 = snap.per_dso[M31.dso_id]

    # On 2026-04-19 from Phoenix, Orion is setting in the early evening
    # so peak is near astro-dark start; Andromeda is rising in the early
    # morning so peak is near astro-dark end. Both should have non-zero
    # altitude values and positive visibility periods if the filter
    # allows (rise to 30°).
    assert m42.max_altitude_deg > 0
    assert m31.max_altitude_deg > 0
    assert m42.hours_visible >= 0
    assert m31.hours_visible >= 0


def test_custom_horizon_reduces_hours_visible_vs_flat_min():
    """A custom horizon that masks the southern sky must reduce
    hours-visible for a low-declination target (M42) vs a flat 30° floor."""
    flat_snap = _snapshot([M42], horizon=FLAT_30)
    flat_vis = flat_snap.per_dso[M42.dso_id]

    # Simulate a horizon that's 60° tall across the southern sky.
    points = tuple((float(az), 60.0 if 90.0 <= az <= 270.0 else 15.0) for az in range(0, 360, 10))
    blocked_snap = compute_visibility_snapshot(
        PHOENIX,
        _custom(points),
        date(2026, 4, 19),
        [M42],
    )
    blocked_vis = blocked_snap.per_dso[M42.dso_id]
    # Either the flat horizon already blocks M42 (hours = 0), or the
    # custom horizon only makes things stricter.
    assert blocked_vis.hours_visible <= flat_vis.hours_visible


def test_moon_separation_set_only_when_visible():
    """If the DSO is never visible, min_moon_separation_deg is None."""
    snap = _snapshot([CROSS])
    assert snap.per_dso[CROSS.dso_id].min_moon_separation_deg is None


def test_transit_always_reported_even_outside_dark_hours():
    """Meridian transit is a sidereal fact about the object, not a
    function of the astro-dark window. M42 peaks late December (lower
    transit in April is around midday), so its transit may fall
    outside the ~5-hour astro-dark window — but the planner must still
    report it."""
    snap = _snapshot([M42])
    vis = snap.per_dso[M42.dso_id]
    assert vis.transit_time_utc is not None
    assert vis.altitude_at_transit_deg == pytest.approx(51.16, abs=0.1)


def test_transit_reported_for_never_visible_southern_target():
    """Deep southern CROSS never rises from Phoenix, but its transit
    (below the southern horizon) is still reported — altitude will be
    negative, which callers can use to tell "never visible"."""
    snap = _snapshot([CROSS])
    vis = snap.per_dso[CROSS.dso_id]
    assert vis.transit_time_utc is not None
    assert vis.altitude_at_transit_deg == pytest.approx(-6.55, abs=0.5)


def test_peak_equals_transit_when_transit_inside_dark():
    """M51 culminates in the middle of the Phoenix April astro-dark
    window, so peak and transit should refer to the same instant at
    the same altitude."""
    snap = _snapshot([M51])
    vis = snap.per_dso[M51.dso_id]
    assert snap.dark_window.start_utc <= vis.transit_time_utc <= snap.dark_window.end_utc
    assert vis.peak_time_utc == vis.transit_time_utc
    assert vis.max_altitude_deg == vis.altitude_at_transit_deg
    assert vis.max_altitude_deg == pytest.approx(76.25, abs=0.5)


def test_peak_at_dark_start_when_transit_before_window():
    """M42 in April is already setting in the west at astro-dark
    start — its true transit is in the afternoon (before the window).
    Peak should therefore be evaluated at dark_start."""
    snap = _snapshot([M42])
    vis = snap.per_dso[M42.dso_id]
    assert vis.transit_time_utc < snap.dark_window.start_utc
    assert vis.peak_time_utc == snap.dark_window.start_utc


def test_peak_at_dark_end_when_transit_after_window():
    """M8 (Lagoon) rises late in Phoenix April; its transit falls
    after astro-dark ends. Peak evaluates at the higher endpoint."""
    snap = _snapshot([M8])
    vis = snap.per_dso[M8.dso_id]
    assert vis.transit_time_utc > snap.dark_window.end_utc
    assert vis.peak_time_utc == snap.dark_window.end_utc


def test_transit_altitude_matches_astropy_apparent_frame():
    """Regression for max-alt / transit-alt splits."""
    snap = _snapshot([M51])
    vis = snap.per_dso[M51.dso_id]
    loc = EarthLocation(
        lat=PHOENIX.latitude_deg * u_astro.deg,
        lon=PHOENIX.longitude_deg * u_astro.deg,
        height=(PHOENIX.elevation_m or 0.0) * u_astro.m,
    )
    coord = SkyCoord(ra=M51.ra_deg * u_astro.deg, dec=M51.dec_deg * u_astro.deg, frame="icrs")
    altaz = coord.transform_to(AltAz(obstime=Time(vis.transit_time_utc), location=loc))
    expected = float(altaz.alt.deg)
    assert vis.altitude_at_transit_deg == pytest.approx(expected, abs=0.01)
    assert vis.max_altitude_deg == vis.altitude_at_transit_deg


def test_moon_separation_positive_when_visible():
    snap = _snapshot([M42])
    vis = snap.per_dso[M42.dso_id]
    if vis.hours_visible > 0:
        assert vis.min_moon_separation_deg is not None
        assert 0.0 <= vis.min_moon_separation_deg <= 180.0


def test_min_moon_separation_pinned_corrected():
    # Regression guard for the GCRS-distance separation bug (see
    # astronomy.direction_only): the buggy code transformed the
    # distance-bearing Moon into the target's ICRS frame, shifting the
    # origin ~1 AU and producing a materially wrong separation. M51 from
    # Phoenix on 2026-04-19 is ~95° from the Moon at closest approach.
    snap = _snapshot([M51])
    vis = snap.per_dso[M51.dso_id]
    assert vis.min_moon_separation_deg is not None
    assert vis.min_moon_separation_deg == pytest.approx(95.2, abs=0.7)


def test_empty_dso_list():
    snap = _snapshot([])
    assert snap.per_dso == {}
    assert snap.dark_window.start_utc is not None


def test_polar_summer_returns_empty_snapshot():
    """At the North Pole in June, astro-dark never occurs."""
    polar = PlannerLocation(
        id=2,
        latitude_deg=89.9,
        longitude_deg=0.0,
        elevation_m=0.0,
        timezone="UTC",
        updated_at="2026-01-01T00:00:00",
    )
    polar_horizon = PlannerHorizon(
        id=99,
        location_id=polar.id,
        name="0° flat",
        type="artificial",
        flat_altitude_deg=0.0,
        points=(),
        updated_at="2026-01-01T00:00:00",
    )
    snap = compute_visibility_snapshot(polar, polar_horizon, date(2026, 6, 21), [M42])
    assert snap.dark_window.start_utc is None
    assert snap.dark_window.end_utc is None
    assert snap.per_dso == {}


def test_cache_reuses_snapshot_for_same_key():
    cache = VisibilityCache()
    snap_a = cache.get_or_compute(PHOENIX, FLAT_30, date(2026, 4, 19), [M42])
    snap_b = cache.get_or_compute(PHOENIX, FLAT_30, date(2026, 4, 19), [M42])
    assert snap_a is snap_b


def test_cache_invalidates_on_horizon_change():
    """Swapping horizons (different id) must invalidate — otherwise
    hours/peak come out against the wrong altitude floor."""
    cache = VisibilityCache()
    flat_40 = _artificial(40.0, horizon_id=2)
    first = cache.get_or_compute(PHOENIX, FLAT_30, date(2026, 4, 19), [M42])
    second = cache.get_or_compute(PHOENIX, flat_40, date(2026, 4, 19), [M42])
    assert first is not second


def test_cache_invalidates_on_location_updated_at_change():
    cache = VisibilityCache()
    cache.get_or_compute(PHOENIX, FLAT_30, date(2026, 4, 19), [M42])
    edited = replace(PHOENIX, updated_at="2026-04-02T00:00:00")
    second = cache.get_or_compute(edited, FLAT_30, date(2026, 4, 19), [M42])
    first = cache.get_or_compute(PHOENIX, FLAT_30, date(2026, 4, 19), [M42])
    assert second is not first


@pytest.mark.parametrize(
    "azimuths_deg, expected_altitude",
    [
        (0.0, 10.0),
        (90.0, 20.0),
        (180.0, 30.0),
        (45.0, 15.0),
        (135.0, 25.0),
        (360.0, 10.0),
    ],
)
def test_horizon_interpolation(azimuths_deg, expected_altitude):
    """Sanity-check the azimuth interpolator used by the visibility engine."""
    from nightcrate.services.horizon import interpolate_horizon_altitude

    polyline = [(0.0, 10.0), (90.0, 20.0), (180.0, 30.0), (270.0, 20.0), (359.0, 10.0)]
    actual = interpolate_horizon_altitude(polyline, np.asarray([azimuths_deg]))
    assert actual[0] == pytest.approx(expected_altitude, abs=0.5)
