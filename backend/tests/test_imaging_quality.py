"""Tests for the imaging-quality score (v0.41.4 model).

The expected values come from `docs/imaging-quality-model.md` §4; each pinned case
below carries its hand-derivation in a comment so the arithmetic can be checked
without running the model.

Model under test:
    score        = 100 * availability * quality
    availability = darkness * precip_gate * wind_gate * (1 - cloud) ** 1.5
    quality      = moon_factor * (0.45*seeing + 0.40*transparency + 0.15*wind_calm) / 100
"""

from datetime import UTC, datetime, timedelta

import pytest

from nightcrate.services.astronomy import DarknessWindow
from nightcrate.services.imaging_quality import (
    CLOUD_YIELD_EXPONENT,
    MOON_FLOOR,
    UNUSABLE_AVAILABILITY,
    UNUSABLE_LABEL,
    Flag,
    Mode,
    Role,
    cloud_yield,
    darkness_fraction,
    effective_cloud_fraction,
    expected_useful_hours,
    label_for_score,
    moon_score,
    score_hour,
    wind_calm_score,
)

IDEAL = dict(seeing=100, transparency=100, wind_calm=100, moon=100)
EXAMPLE_NIGHT = dict(seeing=90, transparency=41, wind_calm=70, moon=100)


def _score(cloud=0, low=None, mid=None, high=None, **kw):
    """score_hour with the supporting factors defaulting to ideal."""
    return score_hour(
        cloud_cover=cloud,
        cloud_cover_low=low,
        cloud_cover_mid=mid,
        cloud_cover_high=high,
        **{**IDEAL, **kw},
    )


# ---------------------------------------------------------------------------
# The requirement itself
# ---------------------------------------------------------------------------


class TestTotalCloudIsUnusable:
    """100% cloud means you cannot image. This is the whole point of the model.

    The previous model returned 46 for the reported hour and 55 for 100% high
    cloud with every other factor perfect, because cloud was an additive term
    with a floor. Here it is a gate.
    """

    @pytest.mark.parametrize(
        "low,mid,high",
        [
            (100, 0, 0),  # solid low stratus
            (0, 100, 0),  # solid mid
            (0, 0, 100),  # solid cirrus — the reported case
            (100, 100, 100),  # everything
            (40, 60, 100),  # mixed, high at 100
        ],
    )
    @pytest.mark.parametrize("mode", [Mode.NORMAL, Mode.NARROWBAND])
    def test_full_cover_scores_zero_whatever_the_layer(self, low, mid, high, mode):
        result = _score(cloud=100, low=low, mid=mid, high=high, mode=mode)
        assert result.score == 0
        assert result.label == UNUSABLE_LABEL
        assert result.availability == 0.0
        assert Flag.OVERCAST in result.flags

    def test_perfect_everything_else_cannot_rescue_it(self):
        """The old model scored this 55 'Good'."""
        result = _score(cloud=100, low=0, mid=0, high=100)
        assert result.score == 0
        # The quality half is still reported, and is still perfect — that is the
        # "0, but the data would have been great" story the UI tells.
        assert result.quality == pytest.approx(100.0)

    def test_a_single_layer_at_100_zeroes_it_even_if_total_disagrees(self):
        """Cover is the max over every figure, so an inconsistent feed still gates."""
        result = _score(cloud=40, low=0, mid=0, high=100)
        assert result.score == 0
        assert result.label == UNUSABLE_LABEL


# ---------------------------------------------------------------------------
# Cloud
# ---------------------------------------------------------------------------


class TestCloudYield:
    @pytest.mark.parametrize(
        "cover,expected",
        [(0, 1.0), (10, 0.8538), (20, 0.7155), (50, 0.3536), (80, 0.0894), (100, 0.0)],
    )
    def test_curve_at_k_1_5(self, cover, expected):
        assert cloud_yield(cover / 100) == pytest.approx(expected, abs=0.0001)

    def test_exactly_zero_at_full_cover_for_any_exponent(self):
        for k in (0.5, 1.0, 1.5, 3.0):
            assert cloud_yield(1.0, exponent=k) == 0.0

    def test_rejects_non_positive_exponent(self):
        with pytest.raises(ValueError):
            cloud_yield(0.5, exponent=0)

    def test_unusable_threshold_is_about_78_percent_cover(self):
        cover = 1 - UNUSABLE_AVAILABILITY ** (1 / CLOUD_YIELD_EXPONENT)
        assert cover == pytest.approx(0.7846, abs=0.001)


class TestEffectiveCloudFraction:
    def test_takes_the_maximum_not_the_total(self):
        fraction, _ = effective_cloud_fraction(
            cloud_cover=30, cloud_cover_low=0, cloud_cover_mid=0, cloud_cover_high=80
        )
        assert fraction == pytest.approx(0.80)

    def test_estimates_a_missing_total_from_the_layers(self):
        # random overlap: 1 - (1-0.3)(1-0.0)(1-0.3) = 0.51
        fraction, flags = effective_cloud_fraction(
            cloud_cover=None, cloud_cover_low=30, cloud_cover_mid=0, cloud_cover_high=30
        )
        assert fraction == pytest.approx(0.51)
        assert Flag.TOTAL_ESTIMATED in flags

    def test_flags_missing_layers(self):
        fraction, flags = effective_cloud_fraction(cloud_cover=40)
        assert fraction == pytest.approx(0.40)
        assert Flag.LAYERS_UNAVAILABLE in flags

    def test_refuses_to_guess_with_no_cloud_data_at_all(self):
        with pytest.raises(ValueError, match="no cloud cover data"):
            effective_cloud_fraction(cloud_cover=None)

    def test_high_cloud_only_advisory(self):
        _, flags = effective_cloud_fraction(
            cloud_cover=100, cloud_cover_low=0, cloud_cover_mid=0, cloud_cover_high=100
        )
        assert Flag.HIGH_CLOUD_ONLY in flags

    def test_high_cloud_only_does_not_fire_with_mid_cloud_present(self):
        """The 04:00 row: 17% mid means it is not a pure cirrus deck."""
        _, flags = effective_cloud_fraction(
            cloud_cover=100, cloud_cover_low=0, cloud_cover_mid=17, cloud_cover_high=100
        )
        assert Flag.HIGH_CLOUD_ONLY not in flags


# ---------------------------------------------------------------------------
# Pinned regressions — the real reported night
# ---------------------------------------------------------------------------


class TestReportedNight:
    """The five hours from the bug report, with the factors that reproduce the
    old scores to within 1. Old scores are in the comments."""

    def test_1900_sixty_percent_cirrus(self):
        # old: 60 "Good". yield 0.4^1.5 = 0.25298;
        # quality (0.45*85 + 0.40*40 + 0.15*48)/100 = 0.6145 -> 15.55
        result = score_hour(
            cloud_cover=60,
            cloud_cover_low=0,
            cloud_cover_mid=0,
            cloud_cover_high=60,
            seeing=85,
            transparency=40,
            wind_calm=48,
            moon=100,
        )
        assert result.score == 16
        assert result.label == "Poor"
        assert Flag.HIGH_CLOUD_ONLY in result.flags

    @pytest.mark.parametrize(
        "seeing,transparency,wind_calm,quality",
        [(90, 41, 70, 67.4), (91, 42, 82, 70.0), (83, 40, 48, 60.5)],
    )
    def test_2000_to_2200_full_cirrus(self, seeing, transparency, wind_calm, quality):
        # old: 46 / 47 / 42 "Marginal"
        result = score_hour(
            cloud_cover=100,
            cloud_cover_low=0,
            cloud_cover_mid=0,
            cloud_cover_high=100,
            seeing=seeing,
            transparency=transparency,
            wind_calm=wind_calm,
            moon=100,
        )
        assert result.score == 0
        assert result.label == UNUSABLE_LABEL
        # quality is still reported so the UI can say what it would have been
        assert result.quality == pytest.approx(quality, abs=0.05)


class TestBoundaryCases:
    @pytest.mark.parametrize(
        "cover,expected,label",
        [
            (0, 100, "Excellent"),  # 1.0 * 1.0
            (20, 72, "Good"),  # 0.7155
            (50, 35, "Marginal"),  # 0.3536
            (80, 9, UNUSABLE_LABEL),  # 0.0894 -> below the 0.10 availability floor
            (100, 0, UNUSABLE_LABEL),
        ],
    )
    def test_ideal_factors_isolate_cloud(self, cover, expected, label):
        result = _score(cloud=cover)
        assert result.score == expected
        assert result.label == label

    def test_example_night_clear_sky(self):
        # quality = (0.45*90 + 0.40*41 + 0.15*70)/100 = 0.674
        result = score_hour(cloud_cover=0, **EXAMPLE_NIGHT)
        assert result.score == 67
        assert result.quality == pytest.approx(67.4)


class TestMoonAndMode:
    """Clear sky, seeing 90, transparency 80, wind_calm 80 -> base quality 0.845."""

    BASE = dict(seeing=90, transparency=80, wind_calm=80)

    @pytest.mark.parametrize(
        "moon,normal,narrowband",
        [
            (100, 85, 85),  # factor 1.00 -> 84.5
            (50, 57, 85),  # factor 0.35 + 0.65*0.5 = 0.675 -> 57.04
            (0, 30, 85),  # factor 0.35 -> 29.575
        ],
    )
    def test_moon_multiplies_quality_in_normal_mode_only(self, moon, normal, narrowband):
        assert score_hour(cloud_cover=0, moon=moon, **self.BASE).score == normal
        assert (
            score_hour(cloud_cover=0, moon=moon, mode=Mode.NARROWBAND, **self.BASE).score
            == narrowband
        )

    def test_moon_factor_floors_rather_than_gates(self):
        """A full moon costs most of the night's value but never all of it."""
        result = score_hour(cloud_cover=0, moon=0, **self.BASE)
        assert result.availability == pytest.approx(1.0)
        assert result.score > 0
        moon_factor = next(f for f in result.factors if f.key == "moon")
        assert moon_factor.effect == pytest.approx(MOON_FLOOR)

    def test_narrowband_marks_moon_not_applied(self):
        result = score_hour(cloud_cover=0, moon=0, mode=Mode.NARROWBAND, **self.BASE)
        moon_factor = next(f for f in result.factors if f.key == "moon")
        assert moon_factor.applied is False
        assert moon_factor.role is Role.MODIFIER


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------


class TestGates:
    """Baseline: 10% cloud, seeing 90 / transparency 80 / wind_calm 80, new moon.
    yield 0.9^1.5 = 0.85381, quality 0.845 -> 72."""

    BASE = dict(
        cloud_cover=10,
        cloud_cover_low=0,
        cloud_cover_mid=0,
        cloud_cover_high=10,
        seeing=90,
        transparency=80,
        wind_calm=80,
        moon=100,
    )

    def test_baseline(self):
        assert score_hour(**self.BASE).score == 72

    def test_no_darkness_closes_the_hour(self):
        result = score_hour(**self.BASE, darkness=0.0)
        assert result.score == 0
        assert result.label == UNUSABLE_LABEL
        assert Flag.NO_DARKNESS in result.flags

    def test_half_darkness_halves_availability(self):
        assert score_hour(**self.BASE, darkness=0.5).score == 36

    @pytest.mark.parametrize("prob,expected", [(40, 72), (55, 36), (70, 0), (80, 0)])
    def test_precipitation_probability_ramp(self, prob, expected):
        assert score_hour(**self.BASE, precipitation_probability=prob).score == expected

    def test_any_precipitation_amount_closes_the_hour(self):
        result = score_hour(**self.BASE, precipitation_mm=0.2)
        assert result.score == 0
        assert Flag.PRECIPITATION in result.flags

    @pytest.mark.parametrize("kmh,expected", [(40, 72), (50, 36), (60, 0), (65, 0)])
    def test_wind_gate_ramp(self, kmh, expected):
        assert score_hour(**self.BASE, wind_speed_kmh=kmh).score == expected

    def test_wind_gate_absent_when_no_wind_reading(self):
        result = score_hour(**self.BASE)
        gate = next(f for f in result.factors if f.key == "wind_gate")
        assert gate.applied is False
        assert gate.effect == 1.0

    def test_dew_is_advisory_only(self):
        with_dew = score_hour(**self.BASE, temperature_c=12.0, dew_point_c=10.5)
        assert Flag.DEW_RISK in with_dew.flags
        assert with_dew.score == score_hour(**self.BASE).score


# ---------------------------------------------------------------------------
# Monotonicity — the structural guarantee
# ---------------------------------------------------------------------------


class TestMonotonicity:
    def test_more_cloud_never_raises_the_score(self):
        previous = 101
        for cover in range(0, 101):
            score = score_hour(
                cloud_cover=cover, seeing=80, transparency=70, wind_calm=60, moon=90
            ).score
            assert score <= previous
            previous = score

    @pytest.mark.parametrize("factor", ["seeing", "transparency", "wind_calm", "moon"])
    def test_better_sub_scores_never_lower_the_score(self, factor):
        previous = -1
        for value in range(0, 101):
            kwargs = dict(seeing=80, transparency=70, wind_calm=60, moon=90)
            kwargs[factor] = value
            score = score_hour(cloud_cover=20, **kwargs).score
            assert score >= previous
            previous = score

    def test_raising_a_layer_never_raises_the_score(self):
        """Even when the (possibly inconsistent) total does not move."""
        baseline = score_hour(
            cloud_cover=30,
            cloud_cover_low=30,
            cloud_cover_mid=0,
            cloud_cover_high=0,
            seeing=80,
            transparency=70,
            wind_calm=60,
            moon=90,
        ).score
        for high in range(0, 101, 10):
            score = score_hour(
                cloud_cover=30,
                cloud_cover_low=30,
                cloud_cover_mid=0,
                cloud_cover_high=high,
                seeing=80,
                transparency=70,
                wind_calm=60,
                moon=90,
            ).score
            assert score <= baseline


# ---------------------------------------------------------------------------
# Sub-score derivations
# ---------------------------------------------------------------------------


class TestWindCalmScore:
    @pytest.mark.parametrize(
        "kmh,expected", [(0, 100), (5, 100), (10, 80), (15, 60), (27.5, 30), (40, 0), (100, 0)]
    )
    def test_breakpoints(self, kmh, expected):
        assert wind_calm_score(kmh) == pytest.approx(expected)

    def test_continuous_across_the_old_discontinuity(self):
        """The previous implementation jumped from 8 to 0 at exactly 30 km/h."""
        assert wind_calm_score(29.99) == pytest.approx(wind_calm_score(30.01), abs=0.1)

    def test_never_negative(self):
        assert wind_calm_score(500) == 0.0


class TestMoonScore:
    def test_below_the_horizon_is_always_100(self):
        assert moon_score(-5.0, 100) == 100.0
        assert moon_score(0.0, 100) == 100.0
        assert moon_score(None, 100) == 100.0

    def test_full_moon_overhead_is_zero(self):
        assert moon_score(90.0, 100) == pytest.approx(0.0)

    def test_new_moon_never_penalises(self):
        for altitude in (5.0, 45.0, 90.0):
            assert moon_score(altitude, 0) == pytest.approx(100.0)

    @pytest.mark.parametrize("altitude,expected", [(30.0, 50.0), (90.0, 0.0)])
    def test_penalty_scales_with_sine_of_altitude(self, altitude, expected):
        assert moon_score(altitude, 100) == pytest.approx(expected, abs=0.01)

    def test_low_moon_costs_far_less_than_a_high_one(self):
        """The old model could not express this — any moon above the horizon was
        treated as if it were at the zenith."""
        assert moon_score(5.0, 100) > moon_score(60.0, 100)


class TestDarknessFraction:
    """Hour grid is UTC; the window is a pair of boundary datetimes."""

    @staticmethod
    def _window(astro_start=None, astro_end=None, nautical_end=None, nautical_start=None):
        return DarknessWindow(
            civil_end=None,
            nautical_end=nautical_end,
            astro_start=astro_start,
            astro_end=astro_end,
            nautical_start=nautical_start,
            civil_start=None,
        )

    def test_hour_fully_inside_the_window(self):
        window = self._window(
            astro_start=datetime(2026, 3, 15, 20, 0, tzinfo=UTC),
            astro_end=datetime(2026, 3, 16, 4, 0, tzinfo=UTC),
        )
        assert darkness_fraction(datetime(2026, 3, 15, 22, 0, tzinfo=UTC), window) == 1.0

    def test_hour_fully_outside_the_window(self):
        window = self._window(
            astro_start=datetime(2026, 3, 15, 20, 0, tzinfo=UTC),
            astro_end=datetime(2026, 3, 16, 4, 0, tzinfo=UTC),
        )
        assert darkness_fraction(datetime(2026, 3, 15, 18, 0, tzinfo=UTC), window) == 0.0

    def test_straddling_hour_is_a_real_fraction(self):
        """Exactly what the categorical darkness label cannot express."""
        window = self._window(
            astro_start=datetime(2026, 3, 15, 20, 15, tzinfo=UTC),
            astro_end=datetime(2026, 3, 16, 4, 0, tzinfo=UTC),
        )
        got = darkness_fraction(datetime(2026, 3, 15, 20, 0, tzinfo=UTC), window)
        assert got == pytest.approx(0.75)

    def test_narrowband_widens_to_the_nautical_window(self):
        window = self._window(
            astro_start=datetime(2026, 3, 15, 22, 0, tzinfo=UTC),
            astro_end=datetime(2026, 3, 16, 2, 0, tzinfo=UTC),
            nautical_end=datetime(2026, 3, 15, 21, 0, tzinfo=UTC),
            nautical_start=datetime(2026, 3, 16, 3, 0, tzinfo=UTC),
        )
        hour = datetime(2026, 3, 15, 21, 0, tzinfo=UTC)
        assert darkness_fraction(hour, window, mode=Mode.NORMAL) == 0.0
        assert darkness_fraction(hour, window, mode=Mode.NARROWBAND) == 1.0

    def test_polar_summer_has_no_window(self):
        """No astronomical darkness at all — 0 for every hour, which is correct."""
        window = self._window()
        for hour in range(0, 24, 4):
            when = datetime(2026, 6, 21, hour, 0, tzinfo=UTC)
            assert darkness_fraction(when, window) == 0.0

    def test_polar_summer_can_still_have_a_nautical_window(self):
        window = self._window(
            nautical_end=datetime(2026, 6, 21, 23, 0, tzinfo=UTC),
            nautical_start=datetime(2026, 6, 22, 1, 0, tzinfo=UTC),
        )
        assert darkness_fraction(datetime(2026, 6, 21, 23, 0, tzinfo=UTC), window) == 0.0
        assert (
            darkness_fraction(
                datetime(2026, 6, 21, 23, 0, tzinfo=UTC), window, mode=Mode.NARROWBAND
            )
            == 1.0
        )

    def test_half_hour_grid(self):
        window = self._window(
            astro_start=datetime(2026, 3, 15, 20, 0, tzinfo=UTC),
            astro_end=datetime(2026, 3, 15, 20, 30, tzinfo=UTC),
        )
        got = darkness_fraction(
            datetime(2026, 3, 15, 20, 0, tzinfo=UTC), window, hour_length=timedelta(hours=1)
        )
        assert got == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Labels and night aggregation
# ---------------------------------------------------------------------------


class TestLabels:
    @pytest.mark.parametrize(
        "score,expected",
        [
            (100, "Excellent"),
            (75, "Excellent"),
            (74, "Good"),
            (50, "Good"),
            (49, "Marginal"),
            (25, "Marginal"),
            (24, "Poor"),
            (0, "Poor"),
        ],
    )
    def test_thresholds(self, score, expected):
        assert label_for_score(score, availability=1.0) == expected

    def test_unusable_overrides_any_score(self):
        """Unusable is a statement about availability, not a bucket of the scale."""
        assert label_for_score(90, availability=0.05) == UNUSABLE_LABEL

    def test_boundary_of_the_unusable_rule(self):
        assert label_for_score(50, availability=UNUSABLE_AVAILABILITY) == "Good"
        assert label_for_score(50, availability=UNUSABLE_AVAILABILITY - 0.001) == UNUSABLE_LABEL


class TestExpectedUsefulHours:
    def test_sums_unrounded_contributions(self):
        hours = [score_hour(cloud_cover=0, **IDEAL) for _ in range(4)]
        assert expected_useful_hours(hours) == pytest.approx(4.0)

    def test_clouded_hours_contribute_nothing(self):
        hours = [score_hour(cloud_cover=100, **IDEAL) for _ in range(4)]
        assert expected_useful_hours(hours) == pytest.approx(0.0)

    def test_mixed_night(self):
        hours = [score_hour(cloud_cover=0, **IDEAL), score_hour(cloud_cover=100, **IDEAL)]
        assert expected_useful_hours(hours) == pytest.approx(1.0)

    def test_does_not_accumulate_rounding_error(self):
        """Summing the rounded int score would drift by up to 0.5 per hour."""
        hours = [score_hour(cloud_cover=33, **IDEAL) for _ in range(10)]
        exact = 10 * hours[0].availability * hours[0].quality / 100.0
        assert expected_useful_hours(hours) == pytest.approx(exact)
        assert expected_useful_hours(hours) != pytest.approx(sum(h.score for h in hours) / 100.0)


class TestFactorRows:
    def test_every_factor_reads_higher_is_better(self):
        result = score_hour(
            cloud_cover=30,
            seeing=80,
            transparency=70,
            wind_calm=60,
            moon=90,
            precipitation_probability=20,
            wind_speed_kmh=10,
        )
        by_key = {f.key: f for f in result.factors}
        # cloud shows clear-sky %, precipitation shows dry %
        assert by_key["cloud"].value == pytest.approx(70.0)
        assert by_key["precipitation"].value == pytest.approx(80.0)
        for factor in result.factors:
            if factor.value is not None:
                assert 0.0 <= factor.value <= 100.0

    def test_roles_are_assigned(self):
        result = score_hour(cloud_cover=0, **IDEAL)
        roles = {f.key: f.role for f in result.factors}
        assert roles["darkness"] is Role.GATE
        assert roles["cloud"] is Role.YIELD
        assert roles["seeing"] is Role.QUALITY
        assert roles["moon"] is Role.MODIFIER

    def test_quality_terms_carry_their_weight_as_effect(self):
        result = score_hour(cloud_cover=0, **IDEAL)
        weights = {f.key: f.effect for f in result.factors if f.role is Role.QUALITY}
        assert weights == {"seeing": 0.45, "transparency": 0.40, "wind_calm": 0.15}
        assert sum(weights.values()) == pytest.approx(1.0)
