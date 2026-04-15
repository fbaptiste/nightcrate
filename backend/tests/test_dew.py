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

    def test_single_hour_safe(self):
        """Single safe hour should return all_night."""
        result = compute_dew_safe_window([("22:00", 15.0, 5.0)])
        assert result.label == "all_night"

    def test_single_hour_unsafe(self):
        """Single unsafe hour should return none."""
        result = compute_dew_safe_window([("22:00", 10.0, 9.0)])
        assert result.label == "none"

    def test_unsafe_in_the_middle(self):
        """Safe at start and end, unsafe in middle — treated as 'until' first unsafe."""
        hourly = [
            ("20:00", 15.0, 5.0),  # safe (spread=10)
            ("21:00", 15.0, 5.0),  # safe (spread=10)
            ("22:00", 10.0, 9.0),  # unsafe (spread=1)
            ("23:00", 10.0, 9.5),  # unsafe (spread=0.5)
            ("00:00", 15.0, 5.0),  # safe (spread=10)
            ("01:00", 15.0, 5.0),  # safe (spread=10)
        ]
        result = compute_dew_safe_window(hourly)
        # Per the comment: "Unsafe in the middle only — rare, treat as 'until first unsafe'"
        assert result.label == "until"
        assert result.until_time == "22:00"


class TestDewRiskBoundaries:
    """Test exact boundary values for classify_dew_risk."""

    def test_spread_exactly_5(self):
        """Spread of exactly 5.0 should be low (the >= 5 branch)."""
        assert classify_dew_risk(10.0, 5.0) == DEW_RISK_LOW

    def test_spread_exactly_3(self):
        """Spread of exactly 3.0 should be moderate (>= 3, < 5)."""
        assert classify_dew_risk(10.0, 7.0) == DEW_RISK_MODERATE

    def test_spread_exactly_1(self):
        """Spread of exactly 1.0 should be high (>= 1, < 3)."""
        assert classify_dew_risk(10.0, 9.0) == DEW_RISK_HIGH

    def test_spread_just_below_5(self):
        assert classify_dew_risk(10.0, 5.01) == DEW_RISK_MODERATE

    def test_spread_just_below_3(self):
        assert classify_dew_risk(10.0, 7.01) == DEW_RISK_HIGH

    def test_spread_just_below_1(self):
        assert classify_dew_risk(10.0, 9.01) == DEW_RISK_CRITICAL


class TestNegativeSpread:
    """Temperature below dew point — physically impossible but should handle gracefully."""

    def test_negative_spread_is_critical(self):
        """When temp < dew point, spread is negative → should classify as critical."""
        assert classify_dew_risk(5.0, 10.0) == DEW_RISK_CRITICAL

    def test_zero_spread_is_critical(self):
        """When temp == dew point, spread is 0 → critical."""
        assert classify_dew_risk(10.0, 10.0) == DEW_RISK_CRITICAL

    def test_large_negative_spread_is_critical(self):
        assert classify_dew_risk(-5.0, 10.0) == DEW_RISK_CRITICAL
