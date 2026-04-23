"""Scoring moon-dimension tests (spec §14.4)."""

from __future__ import annotations

import numpy as np
import pytest

from nightcrate.services.planner_scoring import score_targets

from .scoring_helpers import default_settings, make_input, make_snapshot


def _run_moon(
    *,
    filter_intent: list[str],
    moon_phase_pct: float,
    moon_altitude_deg,
    moon_separation_deg,
    obj_type: str = "G",
    settings=None,
):
    """Run scoring with target-always-visible-at-60° to isolate moon."""
    n = 120
    alt = np.full(n, 60.0)
    snap = make_snapshot(
        altitude_deg=alt,
        moon_altitude_deg=moon_altitude_deg,
        moon_separation_deg=moon_separation_deg,
        moon_phase_pct=moon_phase_pct,
    )
    mid = snap.dark_mid_utc
    assert mid is not None
    scores = score_targets(
        [make_input(obj_type=obj_type, hours_visible=10.0, peak_time=mid)],
        snap,
        None,
        None,
        filter_intent,
        settings or default_settings(),
        "UTC",
    )
    result = scores[1]
    moon = next((d for d in result.breakdown.dimensions if d.key == "moon"), None)
    return result, moon


def test_moon_neutral_without_filter_intent():
    """Empty filter_intent → moon_score = 1.0 for every target."""
    n = 120
    _, moon = _run_moon(
        filter_intent=[],
        moon_phase_pct=100.0,
        moon_altitude_deg=np.full(n, 45.0),
        moon_separation_deg=np.full(n, 10.0),  # nearly at the moon
    )
    assert moon is not None
    assert moon.score == pytest.approx(1.0, abs=1e-6)


def test_moon_neutral_at_new_moon():
    """Phase=0 → moon_score = 1.0 regardless of position."""
    n = 120
    _, moon = _run_moon(
        filter_intent=["L"],
        moon_phase_pct=0.0,
        moon_altitude_deg=np.full(n, 45.0),
        moon_separation_deg=np.full(n, 10.0),
    )
    assert moon is not None
    assert moon.score == pytest.approx(1.0, abs=1e-6)


def test_moon_full_far_from_target_full_score():
    """Full moon, OIII intent, target 90°+ from moon all night → 1.0."""
    n = 120
    _, moon = _run_moon(
        filter_intent=["OIII"],
        moon_phase_pct=100.0,
        moon_altitude_deg=np.full(n, 45.0),
        moon_separation_deg=np.full(n, 95.0),  # >= 90° default min-sep
    )
    assert moon is not None
    assert moon.score == pytest.approx(1.0, abs=1e-3)


def test_moon_full_at_target_low_score():
    """Full moon, OIII intent, target at moon position → very low."""
    n = 120
    _, moon = _run_moon(
        filter_intent=["OIII"],
        moon_phase_pct=100.0,
        moon_altitude_deg=np.full(n, 45.0),
        moon_separation_deg=np.full(n, 5.0),  # essentially on the moon
    )
    assert moon is not None
    assert moon.score < 0.5


def test_moon_ha_tolerates_full_moon():
    """Full moon, Ha intent (sensitivity 0.15) → relatively high."""
    n = 120
    _, moon = _run_moon(
        filter_intent=["Ha"],
        moon_phase_pct=100.0,
        moon_altitude_deg=np.full(n, 45.0),
        moon_separation_deg=np.full(n, 5.0),
    )
    assert moon is not None
    # Ha sensitivity 0.15 × phase 1 × ~0.84 × ~1 ≈ 0.126 impact × 1 overlap
    # = 0.874 score. Should definitely clear 0.8.
    assert moon.score > 0.8


def test_moon_limiting_filter_rule_ha_plus_oiii():
    """Multi-filter (Ha + OIII) → OIII dominates (highest sensitivity)."""
    n = 120
    _, moon = _run_moon(
        filter_intent=["Ha", "OIII"],
        moon_phase_pct=100.0,
        moon_altitude_deg=np.full(n, 45.0),
        moon_separation_deg=np.full(n, 5.0),
    )
    assert moon is not None
    assert any("OIII" in fact for fact in moon.inputs)


def test_moon_limiting_filter_rule_lrgb():
    """L+R+G+B → B is the limit (default sensitivity 1.00 beats L's 0.95)."""
    n = 120
    _, moon = _run_moon(
        filter_intent=["L", "R", "G", "B"],
        moon_phase_pct=100.0,
        moon_altitude_deg=np.full(n, 45.0),
        moon_separation_deg=np.full(n, 95.0),
    )
    assert moon is not None
    assert any("limiting filter B" in fact for fact in moon.inputs)


def test_moon_below_horizon_whole_obs_window():
    """Moon never up during obs window → score = 1.0."""
    n = 120
    _, moon = _run_moon(
        filter_intent=["L"],
        moon_phase_pct=100.0,
        moon_altitude_deg=np.full(n, -20.0),  # always below horizon
        moon_separation_deg=np.full(n, 120.0),
    )
    assert moon is not None
    assert moon.score == pytest.approx(1.0, abs=1e-6)


def test_moon_cluster_modifier_applied():
    """OCl cluster receives softer impact than a galaxy under same conditions."""
    n = 120
    alt = np.full(n, 45.0)
    sep = np.full(n, 30.0)
    _, galaxy = _run_moon(
        filter_intent=["L"],
        moon_phase_pct=100.0,
        moon_altitude_deg=alt,
        moon_separation_deg=sep,
        obj_type="G",
    )
    _, cluster = _run_moon(
        filter_intent=["L"],
        moon_phase_pct=100.0,
        moon_altitude_deg=alt,
        moon_separation_deg=sep,
        obj_type="OCl",
    )
    assert galaxy is not None and cluster is not None
    assert cluster.score > galaxy.score
    assert any("cluster modifier" in fact for fact in cluster.inputs)


def test_moon_cluster_modifier_disabled_by_setting():
    """Setting cluster modifier = 1.0 → cluster scores identically to galaxy."""
    settings = default_settings(scoring_cluster_moon_modifier=1.0)
    n = 120
    alt = np.full(n, 45.0)
    sep = np.full(n, 30.0)
    _, galaxy = _run_moon(
        filter_intent=["L"],
        moon_phase_pct=100.0,
        moon_altitude_deg=alt,
        moon_separation_deg=sep,
        obj_type="G",
        settings=settings,
    )
    _, cluster = _run_moon(
        filter_intent=["L"],
        moon_phase_pct=100.0,
        moon_altitude_deg=alt,
        moon_separation_deg=sep,
        obj_type="OCl",
        settings=settings,
    )
    assert galaxy is not None and cluster is not None
    assert cluster.score == pytest.approx(galaxy.score, abs=1e-6)
