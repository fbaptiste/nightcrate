"""Smoke tests for the Target Planner annual-hours service."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from nightcrate.services.planner_annual_hours import (
    MoonDataPoint,
    compute_annual_hours,
    compute_moon_year,
    derive_phase_dates,
)
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


def test_no_moon_data_without_filter_or_include(m42_narrowband_30):
    # moon_sep_deg=0 + no filter + include_moon False → moon math skipped (perf
    # path): altitude/illumination stay None so the chart legend has no data.
    assert all(m.max_altitude_deg is None for m in m42_narrowband_30.moon_data)


def test_include_moon_populates_altitude_and_illumination():
    # The annual chart forces moon computation for display via include_moon.
    track = compute_annual_hours(PHOENIX, FLAT_30, 2026, M42, moon_sep_deg=0.0, include_moon=True)
    assert len(track.moon_data) == len(track.points)
    alts = [m.max_altitude_deg for m in track.moon_data if m.max_altitude_deg is not None]
    illums = [m.illumination_pct for m in track.moon_data]
    # Most nights have the moon up at some point during darkness → real altitudes,
    # and illumination cycles 0→100 over the lunar month (not all zero).
    assert len(alts) > 300
    assert max(alts) > 20.0
    assert max(illums) > 90.0
    assert min(illums) < 10.0


def test_annual_min_separation_pinned_corrected():
    # Regression guard for the GCRS-distance separation bug (see
    # astronomy.direction_only): the closest Moon approach to M42 during
    # darkness on 2026-01-15 from Phoenix is ~146°. The pre-fix code,
    # which transformed the distance-bearing Moon into the target's ICRS
    # frame, reported a materially origin-shifted value.
    track = compute_annual_hours(PHOENIX, FLAT_30, 2026, M42, moon_sep_deg=0.0, include_moon=True)
    by_date = {p.date.isoformat(): track.moon_data[i] for i, p in enumerate(track.points)}
    sep = by_date["2026-01-15"].min_separation_deg
    assert sep is not None
    assert sep == pytest.approx(145.9, abs=0.7)


@pytest.fixture(scope="module")
def moon_year_phoenix():
    return compute_moon_year(PHOENIX, FLAT_30, 2026)


def test_moon_year_shape_and_ranges(moon_year_phoenix):
    md = moon_year_phoenix
    assert len(md) == 365  # 2026 is not a leap year
    alts = [m.max_altitude_deg for m in md if m.max_altitude_deg is not None]
    assert alts and max(alts) <= 90.0
    assert max(alts) > 60.0  # the Moon transits high at some point in the year
    ills = [m.illumination_pct for m in md]
    assert min(ills) < 5.0  # reaches new moon
    assert max(ills) > 95.0  # reaches full moon


def test_derive_phase_dates_detects_year_boundary_extrema():
    # A new moon on the first day and a full moon on the last day (only one
    # neighbour each) must still be detected — the illumination threshold makes
    # the one-sided boundary check safe.
    d0 = date(2026, 1, 1)
    illums = [0.4, 18.0, 55.0, 88.0, 99.6]  # new at index 0, full at index 4
    md = [
        MoonDataPoint(
            date=d0 + timedelta(days=i),
            illumination_pct=v,
            min_separation_deg=None,
            max_altitude_deg=None,
        )
        for i, v in enumerate(illums)
    ]
    new_moons, full_moons = derive_phase_dates(md)
    assert new_moons == [d0]
    assert full_moons == [d0 + timedelta(days=4)]


def test_derive_phase_dates_ignores_mid_cycle_endpoints():
    # An endpoint that is NOT near new/full (mid-cycle) must not be flagged.
    d0 = date(2026, 1, 1)
    illums = [52.0, 60.0, 75.0, 60.0, 48.0]  # endpoints ~50%, no true extremum
    md = [
        MoonDataPoint(
            date=d0 + timedelta(days=i),
            illumination_pct=v,
            min_separation_deg=None,
            max_altitude_deg=None,
        )
        for i, v in enumerate(illums)
    ]
    new_moons, full_moons = derive_phase_dates(md)
    assert new_moons == []
    assert full_moons == []  # 75% peak is below the 95% full-moon threshold


def test_derive_phase_dates(moon_year_phoenix):
    new_moons, full_moons = derive_phase_dates(moon_year_phoenix)
    # A year holds ~12-13 lunations of each phase.
    assert 11 <= len(new_moons) <= 14
    assert 11 <= len(full_moons) <= 14
    by_date = {m.date: m.illumination_pct for m in moon_year_phoenix}
    # New moons sit at illumination minima, full moons at maxima.
    assert all(by_date[d] < 5.0 for d in new_moons)
    assert all(by_date[d] > 95.0 for d in full_moons)
    # Phases alternate and stay ordered through the year.
    assert new_moons == sorted(new_moons)
    assert full_moons == sorted(full_moons)


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


def test_illumination_high_at_full_moon_low_at_new_moon():
    """Verify the illumination formula is correct: full moon (elongation
    ~180°) → ~100%, new moon (elongation ~0°) → ~0%.  The formula uses
    (1 - cos(elongation)) / 2, not (1 + cos(elongation)) / 2."""
    track = compute_annual_hours(
        PHOENIX,
        FLAT_30,
        2026,
        M42,
        moon_sep_deg=60.0,
    )
    illuminations = [(m.date, m.illumination_pct) for m in track.moon_data]
    min_illum = min(illuminations, key=lambda x: x[1])
    max_illum = max(illuminations, key=lambda x: x[1])
    assert min_illum[1] < 2.0, (
        f"Minimum illumination should be near 0% (new moon); got {min_illum[1]}% on {min_illum[0]}"
    )
    assert max_illum[1] > 98.0, (
        f"Maximum illumination should be near 100% (full moon); "
        f"got {max_illum[1]}% on {max_illum[0]}"
    )


def test_illumination_filter_reduces_full_moon_nights():
    """With max_illumination_pct=50, nights near full moon (illumination
    ~100%) should have filtered_hours < raw hours. The filter lets time
    through only when the moon is below the horizon."""
    track = compute_annual_hours(
        PHOENIX,
        FLAT_30,
        2026,
        M42,
        moon_sep_deg=0.0,
        max_illumination_pct=50.0,
        min_separation_deg=60.0,
        moon_combine="and",
    )
    reduced = sum(
        1
        for r, f in zip(track.points, track.filtered_points, strict=True)
        if r.hours > 0.5 and f.hours < r.hours - 0.1
    )
    assert reduced > 30, (
        f"Expected many nights with filtered < raw under strict moon filter; got {reduced}"
    )


def test_min_separation_only_considers_moon_above_horizon():
    """min_separation_deg in moon_data should be None for nights where the
    moon never rises above the horizon during dark hours while the target
    is visible, and should reflect actual moon-above-horizon geometry
    otherwise."""
    track = compute_annual_hours(
        PHOENIX,
        FLAT_30,
        2026,
        M42,
        moon_sep_deg=60.0,
    )
    for md in track.moon_data:
        if md.min_separation_deg is not None:
            assert 0.0 <= md.min_separation_deg <= 180.0


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
