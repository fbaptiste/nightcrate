"""Scoring single-dimension tests — observability (§14.2), meridian
(§14.3), frame fit (§14.5)."""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pytest

from nightcrate.services.planner_scoring import score_targets

from .scoring_helpers import (
    default_settings,
    make_input,
    make_snapshot,
)

# ── Observability — §14.2 ─────────────────────────────────────────


def _obs_score(alt_array, *, settings=None, hours=None):
    """Run score_targets over a single DSO with only the observability
    dimension in play (meridian neutralised by placing peak at dark mid,
    moon neutral, no rig).
    """
    snap = make_snapshot(altitude_deg=alt_array)
    mid = snap.dark_mid_utc
    assert mid is not None
    if hours is None:
        hours = float(np.count_nonzero(np.asarray(alt_array) >= 30.0)) * (5 / 60.0)
    scores = score_targets(
        [make_input(hours_visible=hours, peak_time=mid)],
        snap,
        None,
        None,
        [],
        settings or default_settings(),
        "UTC",
    )
    result = scores[1]
    obs_rows = [d for d in result.breakdown.dimensions if d.key == "observability"]
    return result, obs_rows[0] if obs_rows else None


def test_observability_zenith_scores_one():
    """Target at zenith the entire dark window → ~1.0."""
    alt = np.full(120, 90.0)
    result, obs = _obs_score(alt)
    assert obs is not None
    assert obs.score == pytest.approx(1.0, abs=1e-6)


def test_observability_grazing_scores_zero():
    """Target at exactly 30° the whole time → 0.0 (at the airmass cap)."""
    alt = np.full(120, 30.0)
    result, obs = _obs_score(alt)
    assert obs is not None
    assert obs.score == pytest.approx(0.0, abs=1e-6)


def test_observability_linear_rise():
    """Target rising linearly from 30° to 60° over 120 samples.

    q(a) = 1 - (csc(a) - 1) / (csc(30°) - 1). With max_airmass=2
    and a linearly-spaced sample grid, the numeric mean is 0.5330.
    """
    alt = np.linspace(30.0, 60.0, 120)
    result, obs = _obs_score(alt)
    assert obs is not None
    assert obs.score == pytest.approx(0.5330, abs=0.001)


def test_observability_with_lower_threshold():
    """min_altitude_deg=20 → max_airmass ≈ 2.924."""
    settings = default_settings(scoring_observability_min_altitude_deg=20.0)
    # 60°-alt target: sin(60°)=0.866 → airmass 1.155 → quality
    # ≈ 1 - (1.155-1)/(2.924-1) = 1 - 0.0805 = 0.92.
    alt = np.full(120, 60.0)
    result, obs = _obs_score(alt, settings=settings)
    assert obs is not None
    assert obs.score == pytest.approx(0.92, abs=0.01)


def test_observability_circumpolar_high_altitude():
    """Target at constant 75° altitude: sin(75°)=0.96593, airmass=1.03528,
    max_airmass=1/sin(30°)=2.0, quality = 1 - 0.03528/1 = 0.96472 everywhere."""
    alt = np.full(120, 75.0)
    result, obs = _obs_score(alt)
    assert obs is not None
    assert obs.score == pytest.approx(0.9647, abs=0.001)


# ── Meridian — §14.3 ──────────────────────────────────────────────


def _meridian_score(peak_offset_hours, *, dark_hours=6.0):
    """Peak ``peak_offset_hours`` after dark-midpoint (signed), over a
    ``dark_hours``-long window. Altitude pinned high so observability
    doesn't dominate."""
    n = int(dark_hours * 60 / 5) + 1
    alt = np.full(n, 75.0)
    snap = make_snapshot(altitude_deg=alt)
    mid = snap.dark_mid_utc
    assert mid is not None
    peak = mid + timedelta(hours=peak_offset_hours)
    scores = score_targets(
        [make_input(hours_visible=dark_hours, peak_time=peak)],
        snap,
        None,
        None,
        [],
        default_settings(),
        "UTC",
    )
    result = scores[1]
    mer_rows = [d for d in result.breakdown.dimensions if d.key == "meridian"]
    return mer_rows[0] if mer_rows else None


def test_meridian_at_midpoint_scores_one():
    mer = _meridian_score(0.0)
    assert mer is not None
    assert mer.score == pytest.approx(1.0, abs=1e-6)


def test_meridian_at_dark_start():
    """Transit at dark-start boundary: delta = 3h, max_delta = 3 + 2 = 5.
    Score = 1 - 3/5 = 0.4 — penalised but not killed."""
    mer = _meridian_score(-3.0, dark_hours=6.0)  # half_dark = 3 h
    assert mer is not None
    assert mer.score == pytest.approx(0.4, abs=1e-3)


def test_meridian_at_dark_end():
    """Transit at dark-end boundary: symmetric with dark-start."""
    mer = _meridian_score(3.0, dark_hours=6.0)
    assert mer is not None
    assert mer.score == pytest.approx(0.4, abs=1e-3)


def test_meridian_one_fifth_offset():
    """Transit 1h after midpoint of 6h dark, max_delta = 5.
    Score = 1 - 1/5 = 0.8."""
    mer = _meridian_score(1.0, dark_hours=6.0)
    assert mer is not None
    assert mer.score == pytest.approx(0.8, abs=1e-3)


def test_meridian_well_before_dark():
    """Transit 5h before midpoint, max_delta = 5 → score = 0."""
    mer = _meridian_score(-5.0, dark_hours=6.0)
    assert mer is not None
    assert mer.score == 0.0


def test_meridian_well_after_dark():
    """Transit 5h after midpoint, max_delta = 5 → score = 0."""
    mer = _meridian_score(5.0, dark_hours=6.0)
    assert mer is not None
    assert mer.score == 0.0


# ── Frame fit — §14.5 ─────────────────────────────────────────────


def _fit_score(coverage_pct, *, settings=None, rig_major=1.0, rig_minor=0.67):
    """Single-target run with the frame-fit dimension in play."""
    alt = np.full(120, 60.0)
    snap = make_snapshot(altitude_deg=alt)
    mid = snap.dark_mid_utc
    assert mid is not None
    scores = score_targets(
        [make_input(coverage_pct=coverage_pct, hours_visible=10.0, peak_time=mid)],
        snap,
        rig_major,
        rig_minor,
        [],
        settings or default_settings(),
        "UTC",
    )
    result = scores[1]
    fit_rows = [d for d in result.breakdown.dimensions if d.key == "frame_fit"]
    return result, fit_rows[0] if fit_rows else None


def test_frame_fit_at_ideal_scores_one():
    """Default ideal=55 → coverage 55% scores 1.0."""
    _, fit = _fit_score(55.0)
    assert fit is not None
    assert fit.score == pytest.approx(1.0, abs=1e-6)


def test_frame_fit_offset_one_spread_scores_expected():
    """At ideal ± spread, score = exp(-1) ≈ 0.368."""
    _, fit = _fit_score(90.0)  # 90 - 55 = 35 = spread
    assert fit is not None
    assert fit.score == pytest.approx(0.3679, abs=1e-3)


def test_frame_fit_mosaic_enthusiast_preset():
    """With ideal=130, spread=40 a 130% target scores 1.0."""
    settings = default_settings(
        scoring_frame_fit_ideal_coverage_pct=130.0,
        scoring_frame_fit_spread=40.0,
    )
    _, fit = _fit_score(130.0, settings=settings)
    assert fit is not None
    assert fit.score == pytest.approx(1.0, abs=1e-6)


def test_frame_fit_extreme_overflow_scores_zero():
    _, fit = _fit_score(1500.0)
    assert fit is not None
    assert fit.score < 1e-6


def test_frame_fit_dropped_when_no_rig():
    """No rig → frame_fit dimension omitted entirely from breakdown."""
    alt = np.full(120, 60.0)
    snap = make_snapshot(altitude_deg=alt)
    mid = snap.dark_mid_utc
    assert mid is not None
    scores = score_targets(
        [make_input(hours_visible=10.0, peak_time=mid)],
        snap,
        None,
        None,
        [],
        default_settings(),
        "UTC",
    )
    result = scores[1]
    fit_rows = [d for d in result.breakdown.dimensions if d.key == "frame_fit"]
    assert fit_rows == []


def test_frame_fit_dropped_when_coverage_none():
    """DSO with no angular size (coverage=None) → frame_fit omitted."""
    alt = np.full(120, 60.0)
    snap = make_snapshot(altitude_deg=alt)
    mid = snap.dark_mid_utc
    assert mid is not None
    scores = score_targets(
        [make_input(coverage_pct=None, hours_visible=10.0, peak_time=mid)],
        snap,
        1.0,
        0.67,
        [],
        default_settings(),
        "UTC",
    )
    result = scores[1]
    fit_rows = [d for d in result.breakdown.dimensions if d.key == "frame_fit"]
    assert fit_rows == []
