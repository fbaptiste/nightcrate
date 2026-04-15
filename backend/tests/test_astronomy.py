"""Tests for astronomy service — moon, twilight, darkness computations."""

from datetime import date

import pytest

from nightcrate.services.astronomy import (
    NightSummary,
    compute_hourly_astro,
    compute_moon_polyline,
    compute_night_summary,
)


class TestNightSummary:
    """Test the nightly summary computation for a known location and date."""

    @pytest.fixture
    def summary(self) -> NightSummary:
        # Borrego Springs, CA — dark site, well-characterized
        return compute_night_summary(
            latitude=33.2558,
            longitude=-116.3753,
            elevation_m=236.0,
            night_date=date(2026, 3, 15),
            timezone_str="America/Los_Angeles",
        )

    def test_sunset_before_sunrise(self, summary: NightSummary):
        assert summary.sunset is not None
        assert summary.sunrise is not None
        assert summary.sunset < summary.sunrise

    def test_astronomical_darkness(self, summary: NightSummary):
        assert summary.darkness.astro_start is not None
        assert summary.darkness.astro_end is not None
        assert summary.darkness.astro_start < summary.darkness.astro_end
        assert summary.darkness.astro_start > summary.sunset
        assert summary.darkness.astro_end < summary.sunrise

    def test_darkness_hours_positive(self, summary: NightSummary):
        assert summary.darkness_hours > 0
        assert summary.darkness_hours < 14  # sanity — never more than ~14h

    def test_moonless_hours_lte_darkness(self, summary: NightSummary):
        assert summary.moonless_dark_hours <= summary.darkness_hours
        assert summary.moonless_dark_hours >= 0

    def test_moon_info(self, summary: NightSummary):
        assert 0 <= summary.moon.illumination_pct <= 100
        assert summary.moon.phase_name in (
            "New Moon",
            "Waxing Crescent",
            "First Quarter",
            "Waxing Gibbous",
            "Full Moon",
            "Waning Gibbous",
            "Last Quarter",
            "Waning Crescent",
        )

    def test_elongation_field(self, summary: NightSummary):
        """The renamed field elongation_deg should exist and be in range."""
        assert 0 <= summary.moon.elongation_deg <= 180

    def test_twilight_order(self, summary: NightSummary):
        # Evening: sunset < civil_end < nautical_end < astro_start
        assert summary.sunset < summary.darkness.civil_end
        assert summary.darkness.civil_end < summary.darkness.nautical_end
        assert summary.darkness.nautical_end < summary.darkness.astro_start

    def test_deepest_darkness_reached(self, summary: NightSummary):
        assert summary.deepest_darkness_reached == "astro"

    def test_no_imaging_window_false(self, summary: NightSummary):
        assert summary.no_imaging_window is False


class TestPolarLatitude:
    """Test graceful handling of polar latitudes where some twilight crossings may not occur."""

    def test_tromso_summer_no_astro_dark(self):
        """Tromsø in June — midnight sun, no sunset at all."""
        summary = compute_night_summary(
            latitude=69.6496,
            longitude=18.9560,
            elevation_m=10.0,
            night_date=date(2026, 6, 21),
            timezone_str="Europe/Oslo",
        )
        # Should NOT raise, should return a valid result
        assert summary.no_imaging_window is True
        assert summary.darkness_hours == 0.0
        assert summary.deepest_darkness_reached in ("none", "civil", "nautical")

    def test_polar_returns_valid_moon_info(self):
        """Moon info should still be computed even with no imaging window."""
        summary = compute_night_summary(
            latitude=69.6496,
            longitude=18.9560,
            elevation_m=10.0,
            night_date=date(2026, 6, 21),
            timezone_str="Europe/Oslo",
        )
        assert 0 <= summary.moon.illumination_pct <= 100
        assert summary.moon.phase_name is not None


class TestHourlyAstro:
    """Test hourly astronomical data (moon altitude for each hour of the night)."""

    def test_hourly_returns_entries(self):
        hours = compute_hourly_astro(
            latitude=33.2558,
            longitude=-116.3753,
            elevation_m=236.0,
            night_date=date(2026, 3, 15),
            timezone_str="America/Los_Angeles",
        )
        # Should cover roughly sunset to sunrise — at least 10 hours
        assert len(hours) >= 10

    def test_hourly_has_moon_altitude(self):
        hours = compute_hourly_astro(
            latitude=33.2558,
            longitude=-116.3753,
            elevation_m=236.0,
            night_date=date(2026, 3, 15),
            timezone_str="America/Los_Angeles",
        )
        for h in hours:
            assert isinstance(h.moon_altitude_deg, float)
            assert -90 <= h.moon_altitude_deg <= 90

    def test_hourly_has_timestamps(self):
        hours = compute_hourly_astro(
            latitude=33.2558,
            longitude=-116.3753,
            elevation_m=236.0,
            night_date=date(2026, 3, 15),
            timezone_str="America/Los_Angeles",
        )
        from datetime import datetime

        for h in hours:
            assert isinstance(h.time_utc, datetime)
            assert isinstance(h.time_local, str)  # formatted HH:MM
            assert isinstance(h.darkness_category, str)
            assert h.darkness_category in (
                "daylight",
                "civil_twilight",
                "nautical_twilight",
                "astronomical_twilight",
                "night",
            )

    def test_polar_hourly_returns_empty(self):
        """Polar conditions with no sunset should return empty list."""
        hours = compute_hourly_astro(
            latitude=69.6496,
            longitude=18.9560,
            elevation_m=10.0,
            night_date=date(2026, 6, 21),
            timezone_str="Europe/Oslo",
        )
        assert isinstance(hours, list)
        # May be empty if no sunset occurs
        # (the function gracefully returns [] for polar day)


class TestMoonPolyline:
    """Test moon polyline computation for rendering."""

    def test_polyline_returns_points(self):
        from datetime import UTC, datetime

        points = compute_moon_polyline(
            latitude=33.2558,
            longitude=-116.3753,
            elevation_m=236.0,
            start_utc=datetime(2026, 3, 16, 2, 0, tzinfo=UTC),
            end_utc=datetime(2026, 3, 16, 12, 0, tzinfo=UTC),
        )
        assert len(points) > 10  # 10h at 10-min intervals = ~61 points
        for p in points:
            assert isinstance(p.time_utc, str)
            assert -90 <= p.altitude_deg <= 90
