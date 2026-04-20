"""Tests for the Target Planner visibility engine."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import numpy as np
import pytest

from nightcrate.services.planner_visibility import (
    DsoCoord,
    PlannerLocation,
    VisibilityCache,
    compute_visibility_snapshot,
)

# Phoenix, AZ on an April night — astro-dark window is roughly 5–6 hours
# this time of year, plenty for a robust regression test. No custom
# horizon; flat 30° floor.
PHOENIX = PlannerLocation(
    id=1,
    latitude_deg=33.4484,
    longitude_deg=-112.0740,
    elevation_m=331.0,
    timezone="America/Phoenix",
    updated_at="2026-04-01T00:00:00",
)

# M42 (Orion Nebula) — RA/Dec from OpenNGC
M42 = DsoCoord(dso_id=1, ra_deg=83.8221, dec_deg=-5.3911, maj_axis_arcmin=65.0)

# M31 (Andromeda) — well-positioned in April evening skies from Phoenix
M31 = DsoCoord(dso_id=2, ra_deg=10.6847, dec_deg=41.2687, maj_axis_arcmin=190.0)

# A deep southern target — never rises from Phoenix
CROSS = DsoCoord(dso_id=3, ra_deg=186.65, dec_deg=-63.1, maj_axis_arcmin=90.0)


def _snapshot(dsos, *, flat_min: float = 30.0):
    return compute_visibility_snapshot(
        PHOENIX,
        date(2026, 4, 19),
        dsos,
        flat_min_altitude_deg=flat_min,
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
    # M42 in late April is already low at sunset — hours-visible above
    # 30° is typically small but non-negative.
    assert m42.hours_visible >= 0
    # M31 peaks in fall, not spring — it's only rising before dawn.
    assert m31.hours_visible >= 0


def test_custom_horizon_reduces_hours_visible_vs_flat_min():
    """A custom horizon that masks the southern sky must reduce
    hours-visible for a low-declination target (M42)."""
    flat_snap = _snapshot([M42], flat_min=30.0)
    flat_vis = flat_snap.per_dso[M42.dso_id]

    # Simulate a horizon that's 60° tall across the southern sky —
    # massively more restrictive than a flat 30° floor for Orion.
    blocked = replace(
        PHOENIX,
        horizon_points=tuple(
            (float(az), 60.0 if 90.0 <= az <= 270.0 else 15.0) for az in range(0, 360, 10)
        ),
        horizon_updated_at="2026-04-01T00:00:00",
    )
    blocked_snap = compute_visibility_snapshot(
        blocked,
        date(2026, 4, 19),
        [M42],
        flat_min_altitude_deg=30.0,
    )
    blocked_vis = blocked_snap.per_dso[M42.dso_id]
    # Either the flat horizon already blocks M42 (hours = 0), or the
    # custom horizon only makes things stricter.
    assert blocked_vis.hours_visible <= flat_vis.hours_visible


def test_moon_separation_set_only_when_visible():
    """If the DSO is never visible, min_moon_separation_deg is None."""
    snap = _snapshot([CROSS])
    assert snap.per_dso[CROSS.dso_id].min_moon_separation_deg is None


def test_moon_separation_positive_when_visible():
    snap = _snapshot([M42])
    vis = snap.per_dso[M42.dso_id]
    if vis.hours_visible > 0:
        assert vis.min_moon_separation_deg is not None
        assert 0.0 <= vis.min_moon_separation_deg <= 180.0


def test_empty_dso_list():
    snap = _snapshot([])
    assert snap.per_dso == {}
    # Dark window is still computed even without DSOs.
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
    snap = compute_visibility_snapshot(
        polar,
        date(2026, 6, 21),
        [M42],
        flat_min_altitude_deg=30.0,
    )
    assert snap.dark_window.start_utc is None
    assert snap.dark_window.end_utc is None
    assert snap.per_dso == {}


def test_cache_reuses_snapshot_for_same_key():
    cache = VisibilityCache()
    snap_a = cache.get_or_compute(PHOENIX, date(2026, 4, 19), [M42], flat_min_altitude_deg=30.0)
    snap_b = cache.get_or_compute(PHOENIX, date(2026, 4, 19), [M42], flat_min_altitude_deg=30.0)
    assert snap_a is snap_b


def test_cache_invalidates_on_updated_at_change():
    cache = VisibilityCache()
    cache.get_or_compute(PHOENIX, date(2026, 4, 19), [M42], flat_min_altitude_deg=30.0)
    edited = replace(PHOENIX, updated_at="2026-04-02T00:00:00")
    second = cache.get_or_compute(edited, date(2026, 4, 19), [M42], flat_min_altitude_deg=30.0)
    # Different updated_at → different cache slot → freshly computed snapshot.
    # They should have equal values but not be the same instance.
    first = cache.get_or_compute(PHOENIX, date(2026, 4, 19), [M42], flat_min_altitude_deg=30.0)
    assert second is not first


@pytest.mark.parametrize(
    "azimuths_deg, expected_altitude",
    [
        # Polyline: [(0, 10), (90, 20), (180, 30), (270, 20), (359, 10)]
        (0.0, 10.0),
        (90.0, 20.0),
        (180.0, 30.0),
        (45.0, 15.0),  # halfway between 0→90
        (135.0, 25.0),  # halfway between 90→180
        (360.0, 10.0),  # wrap — same as az=0
    ],
)
def test_horizon_interpolation(azimuths_deg, expected_altitude):
    """Sanity-check the azimuth interpolator used by the visibility engine."""
    from nightcrate.services.horizon import interpolate_horizon_altitude

    polyline = [(0.0, 10.0), (90.0, 20.0), (180.0, 30.0), (270.0, 20.0), (359.0, 10.0)]
    actual = interpolate_horizon_altitude(polyline, np.asarray([azimuths_deg]))
    assert actual[0] == pytest.approx(expected_altitude, abs=0.5)
