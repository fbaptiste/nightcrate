"""Tests for seeing estimation service."""

from nightcrate.services.seeing import (
    estimate_seeing_surface,
    estimate_seeing_wind_shear,
)


class TestSurfaceModel:
    """JAG-Lab-style surface-only seeing estimate."""

    def test_perfect_conditions(self):
        score = estimate_seeing_surface(
            temperature_c=10.0,
            dew_point_c=-5.0,
            humidity_pct=20.0,
            wind_speed_kmh=7.0,
            prev_temperature_c=10.5,
        )
        assert 70 <= score <= 100

    def test_terrible_conditions(self):
        score = estimate_seeing_surface(
            temperature_c=15.0,
            dew_point_c=15.0,
            humidity_pct=95.0,
            wind_speed_kmh=40.0,
            prev_temperature_c=10.0,
        )
        assert 0 <= score <= 30

    def test_score_range(self):
        for temp in (0, 10, 25):
            for hum in (10, 50, 90):
                for wind in (0, 10, 30):
                    score = estimate_seeing_surface(
                        temperature_c=temp,
                        dew_point_c=temp - 5,
                        humidity_pct=hum,
                        wind_speed_kmh=wind,
                    )
                    assert 0 <= score <= 100

    def test_no_prev_temperature(self):
        score = estimate_seeing_surface(
            temperature_c=10.0,
            dew_point_c=2.0,
            humidity_pct=50.0,
            wind_speed_kmh=10.0,
            prev_temperature_c=None,
        )
        assert 0 <= score <= 100


class TestWindShearModel:
    """Trinquet/Cherubini wind-shear seeing estimate for forecast data."""

    def test_calm_jet_stream(self):
        score = estimate_seeing_wind_shear(
            wind_speed_200hpa_kmh=20.0,
            wind_speed_300hpa_kmh=15.0,
            wind_speed_500hpa_kmh=10.0,
            geopotential_200hpa_m=11800.0,
            geopotential_300hpa_m=9200.0,
            geopotential_500hpa_m=5500.0,
            temperature_c=10.0,
            dew_point_c=2.0,
            humidity_pct=40.0,
            wind_speed_surface_kmh=5.0,
            prev_temperature_c=10.0,
        )
        assert 60 <= score <= 100

    def test_strong_jet_stream(self):
        score = estimate_seeing_wind_shear(
            wind_speed_200hpa_kmh=150.0,
            wind_speed_300hpa_kmh=120.0,
            wind_speed_500hpa_kmh=60.0,
            geopotential_200hpa_m=11800.0,
            geopotential_300hpa_m=9200.0,
            geopotential_500hpa_m=5500.0,
            temperature_c=10.0,
            dew_point_c=2.0,
            humidity_pct=40.0,
            wind_speed_surface_kmh=5.0,
            prev_temperature_c=10.0,
        )
        assert 0 <= score <= 40

    def test_score_always_0_to_100(self):
        for upper_wind in (10, 50, 100, 200):
            score = estimate_seeing_wind_shear(
                wind_speed_200hpa_kmh=float(upper_wind),
                wind_speed_300hpa_kmh=float(upper_wind * 0.8),
                wind_speed_500hpa_kmh=float(upper_wind * 0.5),
                geopotential_200hpa_m=11800.0,
                geopotential_300hpa_m=9200.0,
                geopotential_500hpa_m=5500.0,
                temperature_c=10.0,
                dew_point_c=2.0,
                humidity_pct=50.0,
                wind_speed_surface_kmh=10.0,
            )
            assert 0 <= score <= 100
