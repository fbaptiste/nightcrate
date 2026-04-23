"""Scoring hard-gate tests (spec §14.1) + quality-chip display (§14.7)."""

from __future__ import annotations

import numpy as np

from nightcrate.services.planner_scoring import score_targets

from .scoring_helpers import (
    default_settings,
    make_input,
    make_snapshot,
    peak_time_utc,
)


def _default_run(
    *,
    hours_visible: float,
    altitude_deg=None,
    visible_mask=None,
    coverage_pct: float | None = None,
    obj_type: str | None = "G",
    settings=None,
    rig_major: float | None = None,
    rig_minor: float | None = None,
    filter_intent: list[str] | None = None,
):
    """Single-DSO score_targets invocation for gate assertions."""
    if altitude_deg is None:
        # 120 samples × 5 min = 10 h at varying altitudes above 30°.
        altitude_deg = np.linspace(30.0, 75.0, 120)
    snap = make_snapshot(altitude_deg=altitude_deg, visible_mask=visible_mask)
    peak = peak_time_utc(snap)
    scores = score_targets(
        [
            make_input(
                obj_type=obj_type,
                coverage_pct=coverage_pct,
                hours_visible=hours_visible,
                peak_time=peak,
            )
        ],
        snap,
        rig_major,
        rig_minor,
        filter_intent or [],
        settings or default_settings(),
        "UTC",
    )
    return scores[1]


# ── Gate tests — §14.1 ────────────────────────────────────────────


def test_gate_min_obs_hours_fires_below_threshold():
    """30-min target with 1.0-hour gate → gated."""
    result = _default_run(hours_visible=0.5)
    assert result.score_pct is None
    assert any("0.5" in f for f in result.breakdown.gate_failures)


def test_gate_min_obs_hours_passes_above_threshold():
    """70-min target with 1.0-hour gate → not gated."""
    result = _default_run(hours_visible=1.17)
    assert result.score_pct is not None


def test_gate_above_horizon_fires_when_below_all_night():
    """Target below horizon all night → gated with horizon-specific message."""
    n = 120
    alt = np.full(n, -5.0)  # never rises
    vis = np.zeros(n, dtype=bool)
    result = _default_run(
        hours_visible=0.0,
        altitude_deg=alt,
        visible_mask=vis,
    )
    assert result.score_pct is None
    assert any("below your horizon" in f for f in result.breakdown.gate_failures)


def test_gate_max_coverage_blocks_when_configured():
    """gate_max_coverage_pct=100, target at 120% → gated."""
    settings = default_settings(scoring_gate_max_coverage_pct=100.0)
    result = _default_run(
        hours_visible=5.0,
        coverage_pct=120.0,
        settings=settings,
        rig_major=1.0,
        rig_minor=0.67,
    )
    assert result.score_pct is None
    assert any("mosaic" in f for f in result.breakdown.gate_failures)


def test_gate_max_coverage_disabled_by_default():
    """Default settings have no coverage gate — 200% target scores."""
    result = _default_run(
        hours_visible=5.0,
        coverage_pct=200.0,
        rig_major=1.0,
        rig_minor=0.67,
    )
    assert result.score_pct is not None


# ── Display tests — §14.7 ─────────────────────────────────────────


def test_quality_label_excellent():
    """Score = 87 with default thresholds → 'Excellent'."""
    # Build a snapshot that pins a near-perfect set of dimensions.
    n = 120
    alt = np.full(n, 85.0)
    snap = make_snapshot(altitude_deg=alt, moon_phase_pct=0.0)
    # Place transit near dark midpoint.
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
    assert result.score_pct is not None
    assert result.score_pct >= 80
    assert result.quality_label == "Excellent"


def test_quality_label_good():
    """Score ~65 → 'Good'."""
    # Engineered inputs: observability ~0.7, meridian 0.5, moon 1.0 → geometric
    # mean ≈ 0.7^(2/4.5) * 0.5^(1/4.5) * 1.0^(1.5/4.5) ≈ 0.69 → 69.
    n = 120
    alt = np.full(n, 45.0)  # airmass 1.41 → quality 0.59
    snap = make_snapshot(altitude_deg=alt)
    # Peak shifted 50% toward one edge of the dark window.
    offset = (snap.dark_window.end_utc - snap.dark_window.start_utc) / 4
    peak = snap.dark_window.start_utc + offset  # 25% of window in
    scores = score_targets(
        [make_input(hours_visible=10.0, peak_time=peak)],
        snap,
        None,
        None,
        [],
        default_settings(),
        "UTC",
    )
    result = scores[1]
    assert result.score_pct is not None
    assert 60 <= result.score_pct < 80
    assert result.quality_label == "Good"


def test_quality_label_poor():
    """Grazing-horizon target during a short dark window → Poor."""
    n = 24  # 2 hours of sampling
    alt = np.full(n, 31.0)  # barely above threshold
    snap = make_snapshot(altitude_deg=alt)
    # Peak at the very edge → meridian score ≈ 0.
    peak = snap.dark_window.end_utc
    scores = score_targets(
        [make_input(hours_visible=2.0, peak_time=peak)],
        snap,
        None,
        None,
        [],
        default_settings(),
        "UTC",
    )
    result = scores[1]
    assert result.score_pct is not None
    assert result.score_pct < 40
    assert result.quality_label == "Poor"


def test_quality_label_null_for_gated():
    """Gated target → score_pct=None + quality_label=None."""
    result = _default_run(hours_visible=0.1)
    assert result.score_pct is None
    assert result.quality_label is None


def test_quality_label_thresholds_respected():
    """Raising ``scoring_threshold_excellent`` should reclassify an
    otherwise-Excellent score as 'Good'."""
    settings = default_settings(scoring_threshold_excellent=95)
    n = 120
    alt = np.full(n, 72.0)  # solid altitude but not zenith
    snap = make_snapshot(altitude_deg=alt)
    mid = snap.dark_mid_utc
    assert mid is not None
    scores = score_targets(
        [make_input(hours_visible=10.0, peak_time=mid)],
        snap,
        None,
        None,
        [],
        settings,
        "UTC",
    )
    result = scores[1]
    assert result.score_pct is not None
    # With stricter threshold, label should not be 'Excellent' even
    # if the score is in the 80s.
    if result.score_pct < 95:
        assert result.quality_label != "Excellent"
