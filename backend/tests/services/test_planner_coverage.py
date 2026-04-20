"""Tests for the Target Planner FOV coverage helper."""

from __future__ import annotations

import pytest

from nightcrate.services.rig_calculators import (
    COVERAGE_FRAMES_WELL_MAX_PCT,
    COVERAGE_FRAMES_WELL_MIN_PCT,
    compute_coverage_pct,
    frames_well,
)


def test_object_fits_comfortably():
    """30' object in 60'×40' frame — major axis binds at 50%."""
    pct = compute_coverage_pct(60.0 / 60.0, 40.0 / 60.0, 30.0, 30.0)
    assert pct == pytest.approx(75.0, abs=0.1)


def test_object_clipped_on_minor_axis():
    """30' object in 20'×60' frame — clipped to 150% on the bound axis."""
    pct = compute_coverage_pct(60.0 / 60.0, 20.0 / 60.0, 30.0, 10.0)
    # min_axis = 10' → 10/20 = 50%; maj_axis = 30' → 30/60 = 50%. Both 50%.
    assert pct == pytest.approx(50.0, abs=0.1)


def test_rectangular_object_binds_on_minor_axis():
    """30'×10' object in 60'×5' frame — minor axis exceeds frame."""
    pct = compute_coverage_pct(60.0 / 60.0, 5.0 / 60.0, 30.0, 10.0)
    # 30' / 60' = 50%; 10' / 5' = 200% → max is 200%
    assert pct == pytest.approx(200.0, abs=0.1)


def test_null_major_axis_returns_none():
    assert compute_coverage_pct(1.0, 0.5, None, 10.0) is None


def test_null_minor_axis_uses_major_axis_as_fallback():
    """A circular object entered with only maj_axis gets a coverage number
    — we don't zero-divide or return None."""
    pct = compute_coverage_pct(1.0, 1.0, 30.0, None)
    # Both axes treated as 30'/60 = 0.5 deg vs 1.0 deg frame.
    assert pct == pytest.approx(50.0, abs=0.1)


def test_zero_fov_returns_none():
    assert compute_coverage_pct(0.0, 1.0, 30.0, 30.0) is None
    assert compute_coverage_pct(1.0, 0.0, 30.0, 30.0) is None


def test_frames_well_band():
    assert frames_well(15.0)
    assert frames_well(90.0)
    assert frames_well(50.0)
    assert not frames_well(14.9)
    assert not frames_well(90.1)
    assert not frames_well(None)


def test_frames_well_matches_constants():
    assert COVERAGE_FRAMES_WELL_MIN_PCT == 15.0
    assert COVERAGE_FRAMES_WELL_MAX_PCT == 90.0
