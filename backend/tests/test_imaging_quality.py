"""Tests for composite imaging quality score."""

from nightcrate.services.imaging_quality import (
    compute_imaging_quality,
    compute_sky_clarity,
)


class TestSkyClarity:
    def test_clear_sky(self):
        assert compute_sky_clarity(cloud_cover_pct=0) == 100

    def test_fully_cloudy(self):
        assert compute_sky_clarity(cloud_cover_pct=100) == 0

    def test_weighted_layers(self):
        """Low clouds hurt more than high clouds."""
        # 50% low cloud: effective = 50*1.0 = 50, clarity = 50
        low_only = compute_sky_clarity(
            cloud_cover_pct=50,
            cloud_cover_low_pct=50,
            cloud_cover_mid_pct=0,
            cloud_cover_high_pct=0,
        )
        # 50% high cloud: effective = 50*0.6 = 30, clarity = 70
        high_only = compute_sky_clarity(
            cloud_cover_pct=50,
            cloud_cover_low_pct=0,
            cloud_cover_mid_pct=0,
            cloud_cover_high_pct=50,
        )
        assert high_only > low_only

    def test_fallback_without_layers(self):
        """Falls back to raw cloud_cover_pct when layers unavailable."""
        result = compute_sky_clarity(cloud_cover_pct=30)
        assert result == 70

    def test_effective_cloud_capped_at_100(self):
        """Sum of weighted layers capped at 100."""
        result = compute_sky_clarity(
            cloud_cover_pct=100,
            cloud_cover_low_pct=80,
            cloud_cover_mid_pct=80,
            cloud_cover_high_pct=80,
        )
        assert result == 0


class TestImagingQuality:
    def test_perfect_night(self):
        result = compute_imaging_quality(
            sky_clarity=100,
            seeing_score=95,
            transparency_score=95,
            wind_speed_kmh=3,
            moonless_dark_hours=8,
            darkness_hours=8,
            moon_illumination_pct=0,
            include_moon=True,
        )
        assert result.overall >= 80

    def test_cloudy_night(self):
        result = compute_imaging_quality(
            sky_clarity=10,
            seeing_score=80,
            transparency_score=80,
            wind_speed_kmh=5,
            moonless_dark_hours=6,
            darkness_hours=8,
            moon_illumination_pct=10,
            include_moon=True,
        )
        assert result.overall <= 30

    def test_moon_toggle_difference(self):
        with_moon = compute_imaging_quality(
            sky_clarity=90,
            seeing_score=70,
            transparency_score=70,
            wind_speed_kmh=5,
            moonless_dark_hours=2,
            darkness_hours=8,
            moon_illumination_pct=95,
            include_moon=True,
        )
        without_moon = compute_imaging_quality(
            sky_clarity=90,
            seeing_score=70,
            transparency_score=70,
            wind_speed_kmh=5,
            moonless_dark_hours=2,
            darkness_hours=8,
            moon_illumination_pct=95,
            include_moon=False,
        )
        assert without_moon.overall > with_moon.overall

    def test_new_moon_no_penalty(self):
        with_moon = compute_imaging_quality(
            sky_clarity=90,
            seeing_score=70,
            transparency_score=70,
            wind_speed_kmh=5,
            moonless_dark_hours=8,
            darkness_hours=8,
            moon_illumination_pct=0,
            include_moon=True,
        )
        without_moon = compute_imaging_quality(
            sky_clarity=90,
            seeing_score=70,
            transparency_score=70,
            wind_speed_kmh=5,
            moonless_dark_hours=8,
            darkness_hours=8,
            moon_illumination_pct=0,
            include_moon=False,
        )
        assert abs(with_moon.overall - without_moon.overall) <= 3

    def test_score_range(self):
        for cloud in (0, 50, 100):
            for seeing in (0, 50, 100):
                sky = compute_sky_clarity(cloud_cover_pct=cloud)
                result = compute_imaging_quality(
                    sky_clarity=sky,
                    seeing_score=seeing,
                    transparency_score=50,
                    wind_speed_kmh=10,
                    moonless_dark_hours=4,
                    darkness_hours=8,
                    moon_illumination_pct=50,
                    include_moon=True,
                )
                assert 0 <= result.overall <= 100

    def test_breakdown_present(self):
        result = compute_imaging_quality(
            sky_clarity=80,
            seeing_score=75,
            transparency_score=60,
            wind_speed_kmh=8,
            moonless_dark_hours=6,
            darkness_hours=8,
            moon_illumination_pct=30,
            include_moon=True,
        )
        assert 0 <= result.sky_clarity <= 100
        assert 0 <= result.seeing <= 100
        assert 0 <= result.transparency <= 100
        assert 0 <= result.wind_calm <= 100
        assert 0 <= result.moon_score <= 100

    def test_transparency_affects_score(self):
        """Hazy clear night should score lower than dry clear night."""
        dry_night = compute_imaging_quality(
            sky_clarity=95,
            seeing_score=70,
            transparency_score=90,
            wind_speed_kmh=5,
            moonless_dark_hours=8,
            darkness_hours=8,
            moon_illumination_pct=10,
            include_moon=True,
        )
        hazy_night = compute_imaging_quality(
            sky_clarity=95,
            seeing_score=70,
            transparency_score=30,
            wind_speed_kmh=5,
            moonless_dark_hours=8,
            darkness_hours=8,
            moon_illumination_pct=10,
            include_moon=True,
        )
        assert dry_night.overall > hazy_night.overall

    def test_cloud_gating_effective(self):
        """90% cloud should force Poor regardless of other factors."""
        result = compute_imaging_quality(
            sky_clarity=10,
            seeing_score=100,
            transparency_score=100,
            wind_speed_kmh=0,
            moonless_dark_hours=8,
            darkness_hours=8,
            moon_illumination_pct=0,
            include_moon=True,
        )
        assert result.label == "Poor"


class TestLabel:
    def test_excellent(self):
        result = compute_imaging_quality(
            sky_clarity=100,
            seeing_score=95,
            transparency_score=95,
            wind_speed_kmh=3,
            moonless_dark_hours=8,
            darkness_hours=8,
            moon_illumination_pct=0,
            include_moon=False,
        )
        assert result.label == "Excellent"

    def test_poor(self):
        result = compute_imaging_quality(
            sky_clarity=5,
            seeing_score=10,
            transparency_score=10,
            wind_speed_kmh=40,
            moonless_dark_hours=0,
            darkness_hours=8,
            moon_illumination_pct=100,
            include_moon=True,
        )
        assert result.label == "Poor"
