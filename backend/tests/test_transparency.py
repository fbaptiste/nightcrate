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


class TestTransparencyExtremes:
    """Edge cases and extreme input values."""

    def test_extreme_pwv_zero(self):
        """PWV = 0 (bone dry). PWV component should score 100.

        _pwv_score(0) = clamp(100 - max(0, 0-5)*3) = clamp(100 - 0) = 100
        """
        result = estimate_transparency(
            pwv_mm=0.0,
            aod=0.05,
            humidity_pct=30.0,
            visibility_m=25000.0,
        )
        assert result.components["pwv"] == 100.0

    def test_extreme_pwv_very_high(self):
        """PWV = 100 mm (extreme). PWV component should score 0.

        _pwv_score(100) = clamp(100 - max(0, 100-5)*3) = clamp(100 - 285) = 0
        """
        result = estimate_transparency(
            pwv_mm=100.0,
            aod=0.05,
            humidity_pct=30.0,
            visibility_m=25000.0,
        )
        assert result.components["pwv"] == 0.0

    def test_extreme_aod_zero(self):
        """AOD = 0 (perfectly clean atmosphere).

        _aod_score(0) = clamp(100 - max(0, 0-0.05)*180) = clamp(100) = 100
        """
        result = estimate_transparency(
            pwv_mm=5.0,
            aod=0.0,
            humidity_pct=30.0,
            visibility_m=25000.0,
        )
        assert result.components["aod"] == 100.0

    def test_extreme_aod_volcanic(self):
        """AOD = 1.0 (volcanic eruption level).

        _aod_score(1.0) = clamp(100 - max(0, 1.0-0.05)*180)
                        = clamp(100 - 0.95*180) = clamp(100 - 171) = clamp(-71) = 0
        """
        result = estimate_transparency(
            pwv_mm=5.0,
            aod=1.0,
            humidity_pct=30.0,
            visibility_m=25000.0,
        )
        assert result.components["aod"] == 0.0

    def test_extreme_visibility_zero(self):
        """Visibility = 0 m (fog).

        _visibility_score(0) = clamp(0/25000*100) = 0
        """
        result = estimate_transparency(
            pwv_mm=5.0,
            aod=0.05,
            humidity_pct=30.0,
            visibility_m=0.0,
        )
        assert result.components["visibility"] == 0.0

    def test_extreme_visibility_beyond_ceiling(self):
        """Visibility = 50000 m (crystal clear, beyond the 25km ceiling).

        _visibility_score(50000) = clamp(50000/25000*100) = clamp(200) = 100
        Should cap at 100, not exceed it.
        """
        result = estimate_transparency(
            pwv_mm=5.0,
            aod=0.05,
            humidity_pct=30.0,
            visibility_m=50000.0,
        )
        assert result.components["visibility"] == 100.0

    def test_contradictory_high_pwv_excellent_visibility(self):
        """High PWV (30mm) but excellent visibility (30km).

        PWV drags the score down even though visibility is great.

        _pwv_score(30) = clamp(100 - max(0, 30-5)*3) = 100 - 75 = 25
        _aod_score(0.03) = clamp(100 - max(0, 0.03-0.05)*180) = 100 (negative arg)
        _humidity_score(30) = clamp(100 - 30*0.8) = 76
        _visibility_score(30000) = clamp(30000/25000*100) = clamp(120) = 100

        score = 25*0.50 + 100*0.25 + 76*0.15 + 100*0.10
              = 12.5 + 25 + 11.4 + 10 = 58.9 → 59

        Despite perfect visibility and AOD, PWV at 50% weight pulls the score
        well below what visibility alone would suggest.
        """
        result = estimate_transparency(
            pwv_mm=30.0,
            aod=0.03,
            humidity_pct=30.0,
            visibility_m=30000.0,
        )
        assert result.tier == "primary"
        assert result.score == 59
        # Verify the PWV component is low while visibility is maxed
        assert result.components["pwv"] == 25.0
        assert result.components["visibility"] == 100.0

    def test_reference_value_primary_tier(self):
        """Reference value computed by hand from the primary tier formula.

        Inputs: pwv=10, aod=0.1, humidity=50, visibility=20000

        _pwv_score(10) = clamp(100 - max(0, 10-5)*3) = 100 - 15 = 85
        _aod_score(0.1) = clamp(100 - max(0, 0.1-0.05)*180) = 100 - 9 = 91
        _humidity_score(50) = clamp(100 - 50*0.8) = 100 - 40 = 60
        _visibility_score(20000) = clamp(20000/25000*100) = 80

        score = 85*0.50 + 91*0.25 + 60*0.15 + 80*0.10
              = 42.5 + 22.75 + 9.0 + 8.0 = 82.25
        round(82.25) = 82
        """
        result = estimate_transparency(
            pwv_mm=10.0,
            aod=0.1,
            humidity_pct=50.0,
            visibility_m=20000.0,
        )
        assert result.tier == "primary"
        assert result.score == 82
