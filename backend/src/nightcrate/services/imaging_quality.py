"""Composite imaging quality score computation.

Pure computation module — no DB, no HTTP, no FastAPI.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ImagingQualityResult:
    """Result of the composite imaging quality score computation."""

    overall: int
    label: str
    sky_clarity: int
    seeing: int
    transparency: int
    wind_calm: int
    moon_score: int
    moon_included: bool


def compute_sky_clarity(
    *,
    cloud_cover_pct: float,
    cloud_cover_low_pct: float | None = None,
    cloud_cover_mid_pct: float | None = None,
    cloud_cover_high_pct: float | None = None,
) -> int:
    """Weighted sky clarity 0-100. Low clouds weight 1.0, mid 0.9, high 0.6.

    Falls back to raw cloud_cover_pct if layer breakdown unavailable.
    """
    if (
        cloud_cover_low_pct is not None
        and cloud_cover_mid_pct is not None
        and cloud_cover_high_pct is not None
    ):
        effective_cloud = (
            cloud_cover_low_pct * 1.0 + cloud_cover_mid_pct * 0.9 + cloud_cover_high_pct * 0.6
        )
        effective_cloud = min(100.0, effective_cloud)
    else:
        effective_cloud = cloud_cover_pct
    return int(round(max(0.0, 100.0 - effective_cloud)))


def _wind_score(wind_speed_kmh: float) -> float:
    """Map wind speed (km/h) to a 0-100 calm score."""
    if wind_speed_kmh <= 5:
        return 100.0
    if wind_speed_kmh <= 15:
        # Linear 100 → 60 over 5–15 km/h
        return 100.0 - (wind_speed_kmh - 5) * (40.0 / 10.0)
    if wind_speed_kmh <= 30:
        # Linear 60 → ~8 over 15–30 km/h  (60 - (x-15) * 52/15)
        return 60.0 - (wind_speed_kmh - 15) * (52.0 / 15.0)
    return 0.0


def _moon_score(
    moonless_dark_hours: float,
    darkness_hours: float,
    moon_illumination_pct: float,
) -> float:
    """Compute moon quality score 0-100 (100 = no moon penalty)."""
    if darkness_hours <= 0:
        return 100.0
    moon_up_fraction = 1.0 - moonless_dark_hours / darkness_hours
    moon_up_fraction = max(0.0, min(1.0, moon_up_fraction))
    illumination_factor = moon_illumination_pct / 100.0
    return (1.0 - moon_up_fraction * illumination_factor) * 100.0


def _label(overall: int) -> str:
    if overall >= 80:
        return "Excellent"
    if overall >= 55:
        return "Good"
    if overall >= 30:
        return "Marginal"
    return "Poor"


def compute_imaging_quality(
    *,
    sky_clarity: int,
    seeing_score: int,
    transparency_score: int,
    wind_speed_kmh: float,
    moonless_dark_hours: float,
    darkness_hours: float,
    moon_illumination_pct: float,
    include_moon: bool = True,
) -> ImagingQualityResult:
    """Compute the composite imaging quality score.

    Args:
        sky_clarity: Sky clarity score 0-100 (from compute_sky_clarity).
        seeing_score: Seeing quality score 0-100.
        transparency_score: Atmospheric transparency score 0-100.
        wind_speed_kmh: Surface wind speed in km/h.
        moonless_dark_hours: Hours of darkness with moon below horizon.
        darkness_hours: Total hours of darkness.
        moon_illumination_pct: Percent lunar illumination 0-100.
        include_moon: Whether to include the moon penalty factor.
                      Set False for narrowband imaging.

    Returns:
        ImagingQualityResult with overall score, label, and per-factor breakdown.
    """
    seeing = max(0.0, min(100.0, float(seeing_score)))
    transparency = max(0.0, min(100.0, float(transparency_score)))
    wind_calm = max(0.0, min(100.0, _wind_score(wind_speed_kmh)))
    moon = max(
        0.0,
        min(
            100.0,
            _moon_score(
                moonless_dark_hours,
                darkness_hours,
                moon_illumination_pct,
            ),
        ),
    )

    # Cloud gating factor: other factors are multiplied by sqrt(sky_clarity/100).
    # At 50% cloud, other factors contribute 71% of their normal weight.
    # At 100% cloud, other factors contribute 0.
    cloud_gating_factor = math.sqrt(max(0.0, sky_clarity) / 100.0)

    if include_moon:
        # Sky 35 / Seeing 25 / Transparency 15 / Moon 15 / Wind 10
        other_score = seeing * 0.25 + transparency * 0.15 + moon * 0.15 + wind_calm * 0.10
        overall_f = sky_clarity * 0.35 + other_score * cloud_gating_factor
    else:
        # NB mode: Sky 40 / Transparency 25 / Seeing 25 / Wind 10
        other_score = transparency * 0.25 + seeing * 0.25 + wind_calm * 0.10
        overall_f = sky_clarity * 0.40 + other_score * cloud_gating_factor

    overall = int(round(max(0.0, min(100.0, overall_f))))

    return ImagingQualityResult(
        overall=overall,
        label=_label(overall),
        sky_clarity=int(round(max(0.0, min(100.0, float(sky_clarity))))),
        seeing=int(round(seeing)),
        transparency=int(round(transparency)),
        wind_calm=int(round(wind_calm)),
        moon_score=int(round(moon)),
        moon_included=include_moon,
    )
