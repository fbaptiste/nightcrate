"""Smoke tests for the Target Planner annual-hours service."""

from __future__ import annotations

import pytest

from nightcrate.services.planner_annual_hours import compute_annual_hours
from nightcrate.services.planner_visibility import PlannerHorizon, PlannerLocation

PHOENIX = PlannerLocation(
    id=1,
    latitude_deg=33.4484,
    longitude_deg=-112.0740,
    elevation_m=331.0,
    timezone="America/Phoenix",
    updated_at="2026-04-01T00:00:00",
)


def _artificial(flat_alt: float, location_id: int = 1, horizon_id: int = 1) -> PlannerHorizon:
    return PlannerHorizon(
        id=horizon_id,
        location_id=location_id,
        name=f"{flat_alt:g}° flat",
        type="artificial",
        flat_altitude_deg=flat_alt,
        points=(),
        updated_at="2026-01-01T00:00:00",
    )


def _custom(
    points: tuple[tuple[float, float], ...], location_id: int = 1, horizon_id: int = 2
) -> PlannerHorizon:
    return PlannerHorizon(
        id=horizon_id,
        location_id=location_id,
        name="Custom horizon",
        type="custom",
        flat_altitude_deg=None,
        points=points,
        updated_at="2026-01-01T00:00:00",
    )


FLAT_30 = _artificial(30.0)

# M42 (Orion Nebula) — northern-winter target from Phoenix.
M42 = (1, 83.8221, -5.3911)

# M31 (Andromeda) — mid-northern-hemisphere target, rises higher from Phoenix.
M31 = (2, 10.6847, 41.2687)


@pytest.fixture(scope="module")
def m42_narrowband_30():
    return compute_annual_hours(PHOENIX, FLAT_30, 2026, M42, moon_sep_deg=0.0)


@pytest.fixture(scope="module")
def m42_lrgb_30():
    return compute_annual_hours(PHOENIX, FLAT_30, 2026, M42, moon_sep_deg=60.0)


@pytest.fixture(scope="module")
def m31_narrowband_30():
    return compute_annual_hours(PHOENIX, FLAT_30, 2026, M31, moon_sep_deg=0.0)


def test_one_point_per_night_in_year(m42_narrowband_30):
    # 2026 is not a leap year → 365 nights.
    assert len(m42_narrowband_30.points) == 365
    assert m42_narrowband_30.points[0].date.isoformat() == "2026-01-01"
    assert m42_narrowband_30.points[-1].date.isoformat() == "2026-12-31"


def test_response_echoes_horizon_and_moon(m42_narrowband_30, m42_lrgb_30):
    assert m42_narrowband_30.horizon_type == "artificial"
    assert m42_narrowband_30.flat_altitude_deg == 30.0
    assert m42_narrowband_30.moon_sep_deg == 0.0
    assert m42_lrgb_30.moon_sep_deg == 60.0


def test_hours_are_non_negative_and_within_night_length(m42_narrowband_30):
    # A single night's astro darkness in Phoenix peaks around ~10 h in
    # winter; allow generous 14 h ceiling for the margin.
    for p in m42_narrowband_30.points:
        assert 0.0 <= p.hours <= 14.0


def test_m42_peaks_in_northern_winter_from_phoenix(m42_narrowband_30):
    """M42 should score high in December/January from Phoenix (Orion
    transits at midnight) and drop to zero in June/July when Orion is
    behind the sun and only up during daylight."""
    by_month: dict[int, float] = {}
    for p in m42_narrowband_30.points:
        by_month[p.date.month] = by_month.get(p.date.month, 0.0) + p.hours

    peak = max(by_month[12], by_month[1])
    trough = max(by_month[6], by_month[7])
    # Peak monthly total should be large (>60 h) and trough ~0.
    assert peak >= 60.0
    assert trough < peak * 0.1


def test_m31_peaks_in_northern_autumn(m31_narrowband_30):
    """M31 transits at midnight around mid-October, peaking September–
    December — verifies the labelled-by-evening-date contract."""
    by_month: dict[int, float] = {}
    for p in m31_narrowband_30.points:
        by_month[p.date.month] = by_month.get(p.date.month, 0.0) + p.hours
    peak_month = max(by_month, key=by_month.get)
    assert peak_month in {9, 10, 11, 12}


def test_lrgb_never_exceeds_narrowband(m42_narrowband_30, m42_lrgb_30):
    """Moon avoidance can only *remove* hours that narrowband counts —
    LRGB must be ≤ narrowband on every night."""
    assert len(m42_narrowband_30.points) == len(m42_lrgb_30.points)
    for n, lr in zip(m42_narrowband_30.points, m42_lrgb_30.points, strict=True):
        assert lr.hours <= n.hours + 1e-6


def test_lrgb_strictly_less_on_some_nights(m42_narrowband_30, m42_lrgb_30):
    """Across a year the moon crosses every stretch of sky, so LRGB
    mode must deduct hours on SOME nights — otherwise the moon check
    is a no-op and the implementation is buggy."""
    deductions = [
        n.hours - lr.hours
        for n, lr in zip(m42_narrowband_30.points, m42_lrgb_30.points, strict=True)
    ]
    # At least 30 nights a year should show a positive deduction.
    assert sum(1 for d in deductions if d > 0.5) >= 30


def test_higher_threshold_yields_fewer_hours():
    """Raising the altitude threshold from 30° to 50° can only remove
    hours — never add them."""
    low = compute_annual_hours(PHOENIX, _artificial(30.0), 2026, M42, moon_sep_deg=0.0)
    high = compute_annual_hours(PHOENIX, _artificial(50.0), 2026, M42, moon_sep_deg=0.0)
    for a, b in zip(low.points, high.points, strict=True):
        assert b.hours <= a.hours + 1e-6


def test_custom_horizon_empty_points_raises():
    empty_custom = PlannerHorizon(
        id=3,
        location_id=1,
        name="Custom horizon",
        type="custom",
        flat_altitude_deg=None,
        points=(),
        updated_at="2026-01-01T00:00:00",
    )
    with pytest.raises(ValueError):
        compute_annual_hours(PHOENIX, empty_custom, 2026, M42, moon_sep_deg=0.0)


def test_flat_custom_horizon_matches_artificial_of_same_altitude():
    """A synthetic custom horizon at a constant 20° altitude should
    match an artificial 20° horizon within sampling / interpolation
    noise."""
    horizon_points = tuple((float(az), 20.0) for az in range(0, 360, 30))
    using_custom = compute_annual_hours(
        PHOENIX, _custom(horizon_points), 2026, M42, moon_sep_deg=0.0
    )
    using_flat = compute_annual_hours(PHOENIX, _artificial(20.0), 2026, M42, moon_sep_deg=0.0)
    for a, b in zip(using_custom.points, using_flat.points, strict=True):
        assert abs(a.hours - b.hours) <= 0.2


def test_out_of_range_moon_sep_raises():
    with pytest.raises(ValueError):
        compute_annual_hours(PHOENIX, FLAT_30, 2026, M42, moon_sep_deg=-1.0)
    with pytest.raises(ValueError):
        compute_annual_hours(PHOENIX, FLAT_30, 2026, M42, moon_sep_deg=200.0)


# ── Global-deployment edge cases ──────────────────────────────────────────

REYKJAVIK = PlannerLocation(
    id=10,
    latitude_deg=64.1466,
    longitude_deg=-21.9426,
    elevation_m=40.0,
    timezone="Atlantic/Reykjavik",
    updated_at="2026-01-01T00:00:00",
)

LONGYEARBYEN = PlannerLocation(
    id=11,
    latitude_deg=78.2232,
    longitude_deg=15.6267,
    elevation_m=20.0,
    timezone="Arctic/Longyearbyen",
    updated_at="2026-01-01T00:00:00",
)

NEW_YORK = PlannerLocation(
    id=12,
    latitude_deg=40.7128,
    longitude_deg=-74.0060,
    elevation_m=10.0,
    timezone="America/New_York",
    updated_at="2026-01-01T00:00:00",
)

POLARIS = (99, 37.9546, 89.2641)


def test_reykjavik_midsummer_returns_zero_hours():
    """At φ = 64.15° N, between late May and mid July the sun never
    dips below −18° — ``is_dark`` is always false, so every night's
    hours = 0 regardless of target."""
    track = compute_annual_hours(
        REYKJAVIK, _artificial(20.0, location_id=REYKJAVIK.id), 2026, M31, moon_sep_deg=0.0
    )
    midsummer = [p for p in track.points if 6 <= p.date.month <= 7]
    assert all(p.hours == 0.0 for p in midsummer), (
        "Reykjavík midsummer nights should report 0 h — there is no "
        "astronomical darkness at 64° N between late May and mid July."
    )


def test_longyearbyen_polar_winter_exceeds_12h_cap():
    """At φ = 78.2° N in December the sun still climbs to ~−11° at
    local noon, so the daily astro-dark window is ≈15 h. A circumpolar
    target should comfortably exceed the chart's natural 12 h yMax cap."""
    track = compute_annual_hours(
        LONGYEARBYEN,
        _artificial(20.0, location_id=LONGYEARBYEN.id),
        2026,
        POLARIS,
        moon_sep_deg=0.0,
    )
    mid_dec = [p for p in track.points if p.date.month == 12 and 10 <= p.date.day <= 25]
    assert mid_dec, "expected December samples inside the chart window"
    max_hours = max(p.hours for p in mid_dec)
    assert max_hours >= 14.0, (
        f"Longyearbyen polar winter should yield ≥14 h for a circumpolar "
        f"target; got max {max_hours:.2f} h"
    )


def test_new_york_has_no_dst_discontinuities():
    """DST transitions (spring-forward Mar 8 2026, fall-back Nov 1
    2026) change the local offset mid-year. Each transition-day bucket
    must be within 3 h of both neighbours — large jumps would signal a
    1-hour sample-count error in the grid."""
    from datetime import date as _date
    from datetime import timedelta as _td

    track = compute_annual_hours(
        NEW_YORK, _artificial(30.0, location_id=NEW_YORK.id), 2026, M31, moon_sep_deg=0.0
    )
    by_date = {p.date: p.hours for p in track.points}
    for transition in (_date(2026, 3, 8), _date(2026, 11, 1)):
        h_before = by_date[transition - _td(days=1)]
        h_day = by_date[transition]
        h_after = by_date[transition + _td(days=1)]
        assert abs(h_day - h_before) <= 3.0, (
            f"DST jump on {transition}: prev {h_before:.2f} h → day {h_day:.2f} h"
        )
        assert abs(h_after - h_day) <= 3.0, (
            f"DST jump after {transition}: day {h_day:.2f} h → next {h_after:.2f} h"
        )
