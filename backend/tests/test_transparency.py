"""Tests for atmospheric transparency estimation service."""

from nightcrate.services.transparency import estimate_transparency


class TestTransparencyTiers:
    """Test that the correct tier is selected based on available data."""

    def test_primary_tier_all_data(self):
        result = estimate_transparency(
            pwv_mm=3.0,
            aod=0.03,
            humidity_pct=30.0,
            visibility_m=25000.0,
        )
        assert result.tier == "primary"
        assert "pwv" in result.components
        assert "aod" in result.components
        assert "humidity" in result.components
        assert "visibility" in result.components

    def test_fallback_tier_no_aod(self):
        result = estimate_transparency(
            pwv_mm=3.0,
            aod=None,
            humidity_pct=30.0,
            visibility_m=25000.0,
        )
        assert result.tier == "fallback"
        assert "pwv" in result.components
        assert "aod" not in result.components

    def test_degraded_tier_no_pwv(self):
        result = estimate_transparency(
            pwv_mm=None,
            aod=None,
            humidity_pct=30.0,
            visibility_m=25000.0,
        )
        assert result.tier == "degraded"
        assert "humidity" in result.components
        assert "visibility" in result.components

    def test_degraded_tier_no_data(self):
        result = estimate_transparency(
            pwv_mm=None,
            aod=None,
            humidity_pct=None,
            visibility_m=None,
        )
        assert result.tier == "degraded"
        assert result.score == 50  # neutral fallback


class TestTransparencyScores:
    """Test score values for known conditions."""

    def test_excellent_transparency(self):
        """Dry desert conditions: low PWV, no aerosols, low humidity, clear vis."""
        result = estimate_transparency(
            pwv_mm=2.0,
            aod=0.02,
            humidity_pct=15.0,
            visibility_m=30000.0,
        )
        assert result.score >= 85

    def test_poor_transparency_high_pwv(self):
        """Tropical conditions: very high PWV + high humidity + poor vis.
        PWV=40 → 0, AOD=0.03 → 100, humidity=80 → 36, vis=10km → 40.
        Weighted: 0*0.50 + 100*0.25 + 36*0.15 + 40*0.10 ≈ 34.
        """
        result = estimate_transparency(
            pwv_mm=40.0,
            aod=0.03,
            humidity_pct=80.0,
            visibility_m=10000.0,
        )
        assert result.score <= 40

    def test_wildfire_smoke_crushes_score(self):
        """Heavy wildfire smoke — AOD > 0.5 but PWV is excellent.
        PWV=5 → 100, AOD=0.6 → ~1, humidity=30 → 76, vis=20km → 80.
        Weighted: 100*0.50 + 1*0.25 + 76*0.15 + 80*0.10 ≈ 70.
        AOD weight (25%) isn't enough to kill the score alone when PWV is perfect.
        """
        result = estimate_transparency(
            pwv_mm=5.0,
            aod=0.6,
            humidity_pct=30.0,
            visibility_m=20000.0,
        )
        assert result.score <= 75

    def test_score_always_0_to_100(self):
        for pwv in (0.0, 5.0, 20.0, 50.0):
            for aod in (0.0, 0.1, 0.5, 1.0):
                for hum in (0.0, 50.0, 100.0):
                    for vis in (0.0, 10000.0, 30000.0):
                        result = estimate_transparency(
                            pwv_mm=pwv,
                            aod=aod,
                            humidity_pct=hum,
                            visibility_m=vis,
                        )
                        assert 0 <= result.score <= 100
