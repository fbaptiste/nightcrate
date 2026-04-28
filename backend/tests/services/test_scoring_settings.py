"""Pydantic validation tests on the scoring fields in ``Settings``."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from nightcrate.core.config import Settings


def test_default_settings_is_valid():
    Settings()


def test_out_of_order_thresholds_rejected():
    """excellent=50, good=70 violates strict ordering → ValidationError."""
    with pytest.raises(ValidationError):
        Settings(
            scoring_threshold_excellent=50,
            scoring_threshold_good=70,
        )


def test_equal_thresholds_rejected():
    """Strict descending — equal values are rejected too."""
    with pytest.raises(ValidationError):
        Settings(
            scoring_threshold_excellent=60,
            scoring_threshold_good=60,
        )


def test_negative_weight_rejected():
    with pytest.raises(ValidationError):
        Settings(scoring_weight_meridian=-0.5)


def test_zero_weight_allowed():
    """Weight 0 is allowed (it means "dimension doesn't contribute")."""
    settings = Settings(scoring_weight_meridian=0.0)
    assert settings.scoring_weight_meridian == 0.0


def test_scoring_gate_max_coverage_none_allowed():
    """None disables the coverage gate."""
    settings = Settings(scoring_gate_max_coverage_pct=None)
    assert settings.scoring_gate_max_coverage_pct is None


def test_defaults_match_spec():
    """Pinned-defaults regression — spec §12 numbers land in Settings."""
    s = Settings()
    assert s.scoring_weight_observability == 2.0
    assert s.scoring_weight_meridian == 1.0
    assert s.scoring_weight_moon == 1.5
    assert s.scoring_weight_frame_fit == 1.0
    assert s.scoring_moon_sensitivity_ha == 0.15
    assert s.scoring_moon_sensitivity_oiii == 0.70
    assert s.scoring_moon_sensitivity_l == 0.95
    assert s.scoring_moon_sensitivity_b == 1.00
    assert s.scoring_moon_min_sep_ha == 60.0
    assert s.scoring_moon_min_sep_oiii == 90.0
    assert s.scoring_cluster_moon_modifier == 0.5
    assert s.scoring_observability_min_altitude_deg == 30.0
    assert s.scoring_frame_fit_ideal_coverage_pct == 55.0
    assert s.scoring_frame_fit_spread == 35.0
    assert s.scoring_threshold_excellent == 80
    assert s.scoring_threshold_good == 60
    assert s.scoring_threshold_fair == 40
    assert s.scoring_meridian_buffer_hours == 2.0
    assert s.scoring_gate_min_obs_hours == 1.0
    assert s.scoring_gate_max_coverage_pct is None


def test_min_altitude_below_10_rejected():
    """Below 10° the airmass formula degrades — validation rejects it."""
    with pytest.raises(ValidationError):
        Settings(scoring_observability_min_altitude_deg=5.0)


def test_min_altitude_at_10_allowed():
    settings = Settings(scoring_observability_min_altitude_deg=10.0)
    assert settings.scoring_observability_min_altitude_deg == 10.0
