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

    def test_reference_value(self):
        """Reference value computed by hand from the formula.

        Inputs: temp=10, dew_point=2, humidity=40, wind=7, prev_temp=10.5

        spread = 10 - 2 = 8
        spread_score = min(100, max(0, 8 * 5)) = 40

        wind = 7, in [5, 10] optimal range → wind_score = 100

        humidity_score = max(0, 100 - 40 * 0.8) = 100 - 32 = 68

        temp_change = |10 - 10.5| = 0.5
        stability_score = max(0, 100 - 0.5 * 10) = 95

        combined = 40*0.30 + 100*0.30 + 68*0.20 + 95*0.20
                 = 12 + 30 + 13.6 + 19 = 74.6
        round(74.6) = 75
        """
        score = estimate_seeing_surface(
            temperature_c=10.0,
            dew_point_c=2.0,
            humidity_pct=40.0,
            wind_speed_kmh=7.0,
            prev_temperature_c=10.5,
        )
        assert score == 75

    def test_extreme_polar_cold(self):
        """Extreme cold: temp=-40, dew_point=-50, humidity=0, wind=0."""
        score = estimate_seeing_surface(
            temperature_c=-40.0,
            dew_point_c=-50.0,
            humidity_pct=0.0,
            wind_speed_kmh=0.0,
            prev_temperature_c=-40.0,
        )
        assert 0 <= score <= 100

    def test_extreme_zero_humidity(self):
        """Humidity = 0% (impossible but shouldn't crash)."""
        score = estimate_seeing_surface(
            temperature_c=15.0,
            dew_point_c=0.0,
            humidity_pct=0.0,
            wind_speed_kmh=7.0,
            prev_temperature_c=15.0,
        )
        assert 0 <= score <= 100

    def test_extreme_zero_wind(self):
        """Wind = 0 km/h."""
        score = estimate_seeing_surface(
            temperature_c=10.0,
            dew_point_c=2.0,
            humidity_pct=40.0,
            wind_speed_kmh=0.0,
            prev_temperature_c=10.0,
        )
        # wind < 5 → max(60, 0*12) = 60
        assert 0 <= score <= 100

    def test_extreme_hurricane_wind(self):
        """Wind = 200 km/h — extreme but shouldn't crash."""
        score = estimate_seeing_surface(
            temperature_c=10.0,
            dew_point_c=2.0,
            humidity_pct=40.0,
            wind_speed_kmh=200.0,
            prev_temperature_c=10.0,
        )
        # wind_score = max(0, 100 - (200-10)*5) = max(0, 100-950) = 0
        assert 0 <= score <= 100

    def test_temperature_stability_sensitivity(self):
        """Stable temperature (delta=0) should score higher than unstable (delta=10).

        Same conditions except prev_temperature_c:
        - stable: prev_temp=10 → temp_change=0 → stability=100
        - unstable: prev_temp=0 → temp_change=10 → stability=0

        All other components identical, so the 20% stability weight determines
        the difference: 100*0.20 - 0*0.20 = 20 points.
        """
        stable = estimate_seeing_surface(
            temperature_c=10.0,
            dew_point_c=2.0,
            humidity_pct=40.0,
            wind_speed_kmh=7.0,
            prev_temperature_c=10.0,
        )
        unstable = estimate_seeing_surface(
            temperature_c=10.0,
            dew_point_c=2.0,
            humidity_pct=40.0,
            wind_speed_kmh=7.0,
            prev_temperature_c=0.0,
        )
        assert stable > unstable
        # Exact difference should be 20 points (stability weight)
        assert stable - unstable == 20

    def test_saturated_air(self):
        """Saturated air: temp == dew_point (spread = 0).

        spread_score = min(100, max(0, 0*5)) = 0
        Should produce a low but not crashing score.
        """
        score = estimate_seeing_surface(
            temperature_c=10.0,
            dew_point_c=10.0,
            humidity_pct=100.0,
            wind_speed_kmh=7.0,
            prev_temperature_c=10.0,
        )
        assert 0 <= score <= 100
        # spread_score=0, wind=100, humidity=max(0,100-80)=20, stability=100
        # combined = 0*0.30 + 100*0.30 + 20*0.20 + 100*0.20 = 0+30+4+20 = 54
        assert score == 54


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

    def test_reference_value_calm_jet_stream(self):
        """Reference value for test_calm_jet_stream inputs, computed by hand.

        Upper atmosphere:
          v200 = 20/3.6 ≈ 5.5556 m/s
          v300 = 15/3.6 ≈ 4.1667 m/s
          v500 = 10/3.6 ≈ 2.7778 m/s

          jet_score = max(0, min(100, (35 - 5.5556)/25 * 100))
                    = min(100, 117.78) = 100

          dz_200_300 = |11800 - 9200| = 2600 m
          dz_300_500 = |9200 - 5500| = 3700 m

          shear_200_300 = |5.5556 - 4.1667| / 2600 = 1.3889/2600 ≈ 0.000534
          shear_300_500 = |4.1667 - 2.7778| / 3700 = 1.3889/3700 ≈ 0.000375
          avg_shear = (0.000534 + 0.000375) / 2 ≈ 0.000455

          shear_score = max(0, min(100, (0.003 - 0.000455)/0.002 * 100))
                      = min(100, 127.27) = 100

          upper_score = 100*0.60 + 100*0.40 = 100

        Surface (temp=10, dp=2, hum=40, wind=5, prev=10):
          spread = 8, spread_score = 40
          wind = 5, in [5,10] → wind_score = 100
          humidity_score = 100 - 40*0.8 = 68
          temp_change = 0 → stability_score = 100
          surface = 40*0.30 + 100*0.30 + 68*0.20 + 100*0.20
                  = 12 + 30 + 13.6 + 20 = 75.6 → round → 76

        Final: 100*0.60 + 76*0.40 = 60 + 30.4 = 90.4 → round → 90
        """
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
        assert score == 90

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
