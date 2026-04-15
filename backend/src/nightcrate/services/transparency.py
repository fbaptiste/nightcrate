"""Atmospheric transparency estimation for imaging quality scoring.

Three-tier fallback based on data availability:
  primary  (PWV + AOD + humidity + visibility): weights 50/25/15/10
  fallback (PWV + humidity + visibility):       weights 60/25/15
  degraded (humidity + visibility):             weights 70/30

Pure computation module — no DB, no HTTP, no FastAPI.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TransparencyResult:
    score: int  # 0-100
    tier: str  # "primary" | "fallback" | "degraded"
    components: dict  # individual sub-scores for debugging / display


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _pwv_score(pwv_mm: float) -> float:
    """PWV transparency score. <5mm = 100, 35mm = 10, >40mm = 0."""
    return _clamp(100.0 - max(0.0, pwv_mm - 5.0) * 3.0)


def _aod_score(aod: float) -> float:
    """AOD transparency score. <0.05 = 100, 0.6 = 1, >0.6 = 0.

    Steep penalty — wildfire smoke and heavy dust should crush the score.
    """
    return _clamp(100.0 - max(0.0, aod - 0.05) * 180.0)


def _humidity_score(humidity_pct: float) -> float:
    """Surface humidity transparency contribution. 0% = 100, 100% = 20."""
    return _clamp(100.0 - humidity_pct * 0.8)


def _visibility_score(visibility_m: float) -> float:
    """Surface visibility transparency contribution. 25km+ = 100, 0 = 0."""
    return _clamp(visibility_m / 25000.0 * 100.0)


def estimate_transparency(
    *,
    pwv_mm: float | None,
    aod: float | None,
    humidity_pct: float | None,
    visibility_m: float | None,
) -> TransparencyResult:
    """Estimate transparency score 0-100 with three-tier fallback."""
    has_pwv = pwv_mm is not None
    has_aod = aod is not None
    has_humidity = humidity_pct is not None
    has_visibility = visibility_m is not None

    if has_pwv and has_aod and has_humidity and has_visibility:
        pwv_s = _pwv_score(pwv_mm)
        aod_s = _aod_score(aod)
        hum_s = _humidity_score(humidity_pct)
        vis_s = _visibility_score(visibility_m)
        score = pwv_s * 0.50 + aod_s * 0.25 + hum_s * 0.15 + vis_s * 0.10
        return TransparencyResult(
            score=int(round(score)),
            tier="primary",
            components={"pwv": pwv_s, "aod": aod_s, "humidity": hum_s, "visibility": vis_s},
        )

    if has_pwv and has_humidity and has_visibility:
        pwv_s = _pwv_score(pwv_mm)
        hum_s = _humidity_score(humidity_pct)
        vis_s = _visibility_score(visibility_m)
        score = pwv_s * 0.60 + hum_s * 0.25 + vis_s * 0.15
        return TransparencyResult(
            score=int(round(score)),
            tier="fallback",
            components={"pwv": pwv_s, "humidity": hum_s, "visibility": vis_s},
        )

    if has_humidity and has_visibility:
        hum_s = _humidity_score(humidity_pct)
        vis_s = _visibility_score(visibility_m)
        score = hum_s * 0.70 + vis_s * 0.30
        return TransparencyResult(
            score=int(round(score)),
            tier="degraded",
            components={"humidity": hum_s, "visibility": vis_s},
        )

    # If we don't even have humidity + visibility, something is very wrong.
    # Return a neutral score so downstream scoring doesn't crash.
    return TransparencyResult(score=50, tier="degraded", components={})
