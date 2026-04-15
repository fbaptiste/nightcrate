"""Tests for dew risk classification and safe window computation."""

from nightcrate.services.dew import (
    DEW_RISK_CRITICAL,
    DEW_RISK_HIGH,
    DEW_RISK_LOW,
    DEW_RISK_MODERATE,
    classify_dew_risk,
    compute_dew_safe_window,
)


class TestClassifyDewRisk:
    def test_low_risk_wide_spread(self):
        assert classify_dew_risk(15.0, 5.0) == DEW_RISK_LOW

    def test_moderate_risk(self):
        assert classify_dew_risk(15.0, 11.0) == DEW_RISK_MODERATE

    def test_high_risk(self):
        assert classify_dew_risk(15.0, 13.5) == DEW_RISK_HIGH

    def test_critical_risk(self):
        assert classify_dew_risk(15.0, 14.5) == DEW_RISK_CRITICAL

    def test_exact_boundaries(self):
        # spread = 5.0 → low (>= 5)
        assert classify_dew_risk(10.0, 5.0) == DEW_RISK_LOW
        # spread = 3.0 → moderate (>= 3, < 5)
        assert classify_dew_risk(10.0, 7.0) == DEW_RISK_MODERATE
        # spread = 1.0 → high (>= 1, < 3)
        assert classify_dew_risk(10.0, 9.0) == DEW_RISK_HIGH


class TestDewSafeWindow:
    def test_all_night_safe(self):
        # All spreads >= 3.0
        hourly = [
            ("20:00", 15.0, 5.0),
            ("21:00", 14.0, 5.0),
            ("22:00", 13.0, 5.0),
        ]
        result = compute_dew_safe_window(hourly)
        assert result.label == "all_night"

    def test_no_safe_hours(self):
        # All spreads < 3.0
        hourly = [
            ("20:00", 10.0, 9.0),
            ("21:00", 10.0, 9.5),
            ("22:00", 10.0, 9.0),
        ]
        result = compute_dew_safe_window(hourly)
        assert result.label == "none"

    def test_safe_until(self):
        # Safe first, then unsafe
        hourly = [
            ("20:00", 15.0, 5.0),
            ("21:00", 14.0, 5.0),
            ("22:00", 10.0, 9.0),
            ("23:00", 10.0, 9.5),
        ]
        result = compute_dew_safe_window(hourly)
        assert result.label == "until"
        assert result.until_time == "22:00"

    def test_safe_after(self):
        # Unsafe first, then safe
        hourly = [
            ("20:00", 10.0, 9.0),
            ("21:00", 10.0, 9.5),
            ("22:00", 15.0, 5.0),
            ("23:00", 14.0, 5.0),
        ]
        result = compute_dew_safe_window(hourly)
        assert result.label == "after"
        assert result.after_time == "22:00"

    def test_empty_returns_none(self):
        result = compute_dew_safe_window([])
        assert result.label == "none"
