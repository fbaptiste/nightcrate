"""Imaging-quality score for one forecast hour.

Pure functions only: no I/O, no clock, no network. Standard library + math.

Model
-----
    score = 100 * availability * quality

availability  [0, 1]  Expected fraction of the hour that yields keepable sub-frames.
                      Product of hard gates (darkness, precipitation, wind) and the
                      cloud yield curve. Any gate at 0 => 0. 100% cloud => 0, always.

quality       [0, 1]  Expected quality of the sub-frames you do keep.
                      Weighted mean of seeing / transparency / wind-calm, multiplied by
                      a moon factor in NORMAL mode. Moon is ignored in NARROWBAND mode.

The two halves answer two different questions ("can I image?" and "how good will
the data be?") and are both returned so the UI can show them separately. The
product is the single number for the hourly bar; it reads as "expected useful
data, as a fraction of a perfect hour".

**Why cloud is a gate and not a term.** The previous model summed
``sky_clarity * 0.35`` with the other factors gated by ``sqrt(sky_clarity/100)``.
Any weighted sum with cloud as a *term* has a floor: at 100% high cloud the old
model still returned 46, and 55 with every other factor perfect. Tuning the layer
weight could not fix that. Here availability is a product, so 100% cover is
exactly 0 for any k > 0 and nothing downstream can rescue it.

Monotonicity: more cloud never raises the score (yield is (1-f)^k with k > 0 on
the *maximum* of total and per-layer cover); every sub-score enters with a
non-negative weight; every gate is non-increasing in its input.

Cloud layers: coverage from any layer counts fully toward obscuration. Layer
composition only drives an advisory flag (HIGH_CLOUD_ONLY). The forecast reports
high cloud as *coverage* derived from relative humidity, not opacity, so it
cannot distinguish subvisual cirrus from an opaque deck; giving high cloud
partial credit is exactly what produced the original bug. See
``docs/imaging-quality-model.md`` for the sourcing.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from nightcrate.services.astronomy import DarknessWindow

__all__ = [
    "Mode",
    "Role",
    "Flag",
    "FactorScore",
    "ImagingQuality",
    "score_hour",
    "cloud_yield",
    "effective_cloud_fraction",
    "expected_useful_hours",
    "label_for_score",
    "wind_calm_score",
    "moon_score",
    "darkness_fraction",
]


class Mode(Enum):
    NORMAL = "normal"
    NARROWBAND = "narrowband"


class Role(Enum):
    """How a factor enters the score. The UI groups/colours rows by this."""

    GATE = "gate"  # multiplier on availability; 0 closes the hour
    YIELD = "yield"  # multiplier on availability; continuous (cloud)
    QUALITY = "quality"  # weighted term inside quality
    MODIFIER = "modifier"  # multiplier on quality with a floor > 0 (moon)


class Flag(Enum):
    """Machine-readable advisories. Presentation text belongs to the UI."""

    NO_DARKNESS = "no_darkness"
    PRECIPITATION = "precipitation"
    WIND_GATE = "wind_gate"
    OVERCAST = "overcast"
    HIGH_CLOUD_ONLY = "high_cloud_only"  # obscuration is (almost) all >= 8 km
    LAYERS_UNAVAILABLE = "layers_unavailable"
    TOTAL_ESTIMATED = "total_estimated"  # total was missing; estimated from layers
    DEW_RISK = "dew_risk"


# --------------------------------------------------------------------------- #
# Tunables. Each is a judgement call unless noted; see the redesign notes.
#
# These are deliberately module constants rather than user settings: the score is
# only comparable across hours and nights measured identically, and a slider would
# silently make the forecast incomparable to itself. Revisit as a whole if it ever
# becomes tunable.
# --------------------------------------------------------------------------- #

CLOUD_YIELD_EXPONENT: float = 1.5
"""yield = (1 - cloud_fraction) ** k. k = 1 would be 'lost time = covered fraction';
k > 1 adds the losses from exposures spanning cloud passages, guider/focus
recovery and dither settling. 1.5-2.0 is the defensible range."""

QUALITY_WEIGHTS: dict[str, float] = {
    "seeing": 0.45,
    "transparency": 0.40,
    "wind_calm": 0.15,
}
"""Arithmetic weights inside `quality`. Sum to 1. Same in both modes."""

MOON_FLOOR: float = 0.35
"""NORMAL mode only: quality multiplier at moon sub-score 0 (full moon, high in
the sky). 1.0 at moon sub-score 100. Broadband imaging of faint targets under a
full moon keeps roughly a third of its value; bright targets do better, which is
why this is a floor and not a gate. Target-moon separation is the target
planner's job, not this function's."""

PRECIP_PROBABILITY_RAMP: tuple[float, float] = (40.0, 70.0)
"""Gate is 1.0 at or below the first value, 0.0 at or above the second, linear
between. Any non-zero precipitation *amount* closes the gate outright."""

WIND_GATE_RAMP_KMH: tuple[float, float] = (40.0, 60.0)
"""Sustained 10 m wind, km/h. Below 40 the wind_calm quality term handles it;
by 60 km/h a tall OTA is unsafe and guiding is hopeless regardless of sky.
Rig-dependent in truth - a per-rig setting is a plausible later refinement."""

WIND_CALM_RAMP_KMH: tuple[float, float, float] = (5.0, 15.0, 40.0)
"""Breakpoints for the wind_calm quality sub-score: 100 at or below the first,
60 at the second, 0 at the third, linear between. Continuous throughout - the
previous implementation jumped from 8 to 0 at exactly 30 km/h."""

UNUSABLE_AVAILABILITY: float = 0.10
"""Below this availability the hour is labelled Unusable no matter how good the
quality half is. At k = 1.5 this corresponds to ~78% cloud."""

LABEL_THRESHOLDS: tuple[tuple[int, str], ...] = (
    (75, "Excellent"),
    (50, "Good"),
    (25, "Marginal"),
    (0, "Poor"),
)
"""Re-thresholded from the old 80/55/30 because the scale now means something
different: score/100 is expected useful data as a fraction of a perfect hour."""

UNUSABLE_LABEL: str = "Unusable"

HIGH_CLOUD_ONLY_MIN_HIGH_PCT: float = 50.0
HIGH_CLOUD_ONLY_MAX_LOWMID_PCT: float = 10.0
DEW_RISK_SPREAD_C: float = 2.0


# --------------------------------------------------------------------------- #
# Result types
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class FactorScore:
    key: str
    role: Role
    value: float | None
    """The 0-100 figure the UI shows for this row (None if input was absent).
    Every row reads higher-is-better: cloud shows clear-sky %, precipitation
    shows dry %."""
    effect: float
    """GATE / YIELD / MODIFIER: the multiplier actually applied (0-1).
    QUALITY: this term's weight (0-1); contribution = weight * value / 100."""
    applied: bool = True
    """False when the factor exists in the model but is ignored in this mode
    (moon in NARROWBAND) or could not be evaluated (input absent)."""


@dataclass(frozen=True, slots=True)
class ImagingQuality:
    score: int
    label: str
    availability: float
    quality: float
    mode: Mode
    factors: tuple[FactorScore, ...]
    flags: tuple[Flag, ...]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _pct(x: float | None) -> float | None:
    """Clamp a percentage to [0, 100]; pass None through."""
    return None if x is None else _clamp(float(x), 0.0, 100.0)


def _required_pct(name: str, x: float | None) -> float:
    if x is None:
        raise ValueError(f"{name} sub-score is required")
    return _clamp(float(x), 0.0, 100.0)


def _ramp_down(x: float, lo: float, hi: float) -> float:
    """1.0 for x <= lo, 0.0 for x >= hi, linear in between."""
    if x <= lo:
        return 1.0
    if x >= hi:
        return 0.0
    return 1.0 - (x - lo) / (hi - lo)


def _round_half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


# --------------------------------------------------------------------------- #
# Sub-score derivations (inputs to the model, kept here so there is one source)
# --------------------------------------------------------------------------- #


def wind_calm_score(wind_speed_kmh: float) -> float:
    """Map surface wind speed (km/h) to a 0-100 calm sub-score.

    Continuous over the whole range. Piecewise linear through
    WIND_CALM_RAMP_KMH: 100 at or below 5 km/h, 60 at 15, 0 at 40.
    """
    calm, moderate, useless = WIND_CALM_RAMP_KMH
    v = max(0.0, float(wind_speed_kmh))
    if v <= calm:
        return 100.0
    if v <= moderate:
        return 100.0 - (v - calm) * (40.0 / (moderate - calm))
    if v <= useless:
        return 60.0 - (v - moderate) * (60.0 / (useless - moderate))
    return 0.0


def moon_score(moon_altitude_deg: float | None, moon_illumination_pct: float) -> float:
    """Per-hour moon sub-score, 0-100, higher is better (less moon interference).

    Below the horizon is 100 regardless of phase. Above it, the penalty scales
    with illumination *and* with ``sin(altitude)`` — the geometric factor for how
    much moonlight is scattered into the sky above the observer. A full moon at
    5° is far less damaging than one overhead, which the previous implementation
    could not express: it was a binary switch that treated any moon above the
    horizon as if it were at the zenith.

    No tunable constant: sin(altitude) is 0 at the horizon and 1 at the zenith.
    """
    if moon_altitude_deg is None or moon_altitude_deg <= 0.0:
        return 100.0
    illumination = _clamp(float(moon_illumination_pct), 0.0, 100.0) / 100.0
    geometry = math.sin(math.radians(_clamp(float(moon_altitude_deg), 0.0, 90.0)))
    return 100.0 * (1.0 - illumination * geometry)


def darkness_fraction(
    hour_start_utc: datetime,
    darkness: DarknessWindow,
    *,
    mode: Mode = Mode.NORMAL,
    hour_length: timedelta = timedelta(hours=1),
) -> float:
    """Fraction of this hour (0-1) inside the usable darkness window.

    NORMAL uses astronomical darkness (sun <= -18°). NARROWBAND uses sun <= -12°,
    keeping the astronomical-twilight hours that 3nm-class narrowband filters can
    genuinely shoot through.

    Exact minute overlap against the twilight boundary datetimes rather than the
    ``darkness_category`` label, which is a single instantaneous classification
    taken at the top of the hour and so cannot describe an hour that straddles a
    boundary.

    Returns 0.0 when the relevant window does not exist, which is the correct
    answer for a polar summer: no astronomical darkness means no broadband hour,
    while narrowband may still have a nautical window.
    """
    if mode is Mode.NARROWBAND:
        start, end = darkness.nautical_end, darkness.nautical_start
    else:
        start, end = darkness.astro_start, darkness.astro_end
    if start is None or end is None or end <= start:
        return 0.0

    hour_end = hour_start_utc + hour_length
    overlap = min(hour_end, end) - max(hour_start_utc, start)
    if overlap <= timedelta(0):
        return 0.0
    return _clamp(overlap / hour_length, 0.0, 1.0)


# --------------------------------------------------------------------------- #
# Cloud
# --------------------------------------------------------------------------- #


def effective_cloud_fraction(
    *,
    cloud_cover: float | None,
    cloud_cover_low: float | None = None,
    cloud_cover_mid: float | None = None,
    cloud_cover_high: float | None = None,
) -> tuple[float, tuple[Flag, ...]]:
    """Fraction of sky (0-1) treated as obscured, plus advisory flags.

    Uses the maximum of every available cover figure. A model's total should
    already be >= each layer; taking the max makes the result robust to an
    inconsistent feed and monotonic in every input — adding cloud to any layer
    can never raise the score even if the total field does not move.

    If the total is missing it is estimated from the layers with random overlap,
    ``1 - prod(1 - f_l)``, the conservative (higher) estimate.

    Raises ValueError if no cloud figure at all is available: an hour cannot be
    scored without cloud data, and silently treating 'unknown' as 'clear' would
    be worse than failing. Callers scoring a whole forecast must catch this per
    hour rather than failing the request.
    """
    total = _pct(cloud_cover)
    layers = tuple(
        v
        for v in (_pct(cloud_cover_low), _pct(cloud_cover_mid), _pct(cloud_cover_high))
        if v is not None
    )
    flags: list[Flag] = []

    if total is None and not layers:
        raise ValueError("no cloud cover data for this hour")

    if not layers:
        flags.append(Flag.LAYERS_UNAVAILABLE)

    if total is None:
        total = 100.0 * (1.0 - math.prod(1.0 - f / 100.0 for f in layers))
        flags.append(Flag.TOTAL_ESTIMATED)

    fraction = max((total, *layers)) / 100.0

    if fraction >= 1.0:
        flags.append(Flag.OVERCAST)

    high = _pct(cloud_cover_high)
    if high is not None and high >= HIGH_CLOUD_ONLY_MIN_HIGH_PCT:
        lowmid = [v for v in (_pct(cloud_cover_low), _pct(cloud_cover_mid)) if v is not None]
        lowmid_combined = 100.0 * (1.0 - math.prod(1.0 - f / 100.0 for f in lowmid))
        if lowmid_combined <= HIGH_CLOUD_ONLY_MAX_LOWMID_PCT:
            flags.append(Flag.HIGH_CLOUD_ONLY)

    return fraction, tuple(flags)


def cloud_yield(fraction: float, *, exponent: float = CLOUD_YIELD_EXPONENT) -> float:
    """Expected fraction of an hour's sub-frames that survive cloud cover.

    (1 - f) ** k. Exactly 0 at f = 1 for any k > 0, exactly 1 at f = 0,
    strictly decreasing in f.
    """
    if exponent <= 0:
        raise ValueError("exponent must be positive")
    f = _clamp(fraction, 0.0, 1.0)
    return (1.0 - f) ** exponent


# --------------------------------------------------------------------------- #
# Score
# --------------------------------------------------------------------------- #


def score_hour(
    *,
    # cloud (percent). Total may be None if any layer is present.
    cloud_cover: float | None,
    cloud_cover_low: float | None = None,
    cloud_cover_mid: float | None = None,
    cloud_cover_high: float | None = None,
    # already-derived 0-100 sub-scores, higher is better
    seeing: float,
    transparency: float,
    wind_calm: float,
    moon: float,
    # gates
    darkness: float = 1.0,
    precipitation_mm: float | None = None,
    precipitation_probability: float | None = None,
    wind_speed_kmh: float | None = None,
    # advisory only
    temperature_c: float | None = None,
    dew_point_c: float | None = None,
    mode: Mode = Mode.NORMAL,
) -> ImagingQuality:
    """Score one forecast hour.

    ``seeing`` / ``transparency`` / ``wind_calm`` / ``moon`` are 0-100 sub-scores
    derived upstream (``wind_calm_score`` and ``moon_score`` in this module supply
    the last two). ``moon`` must be the value for *this hour* — a nightly figure
    makes a post-moonset clearing score wrong. ``darkness`` is the fraction of the
    hour inside the usable window, from ``darkness_fraction``.

    ``temperature_c`` / ``dew_point_c`` only raise DEW_RISK and never affect the
    score: dew heaters make that a preparation issue, not a go/no-go one.
    """
    flags: list[Flag] = []
    factors: list[FactorScore] = []

    # ---- availability: gates ------------------------------------------------
    dark = _clamp(float(darkness), 0.0, 1.0)
    if dark <= 0.0:
        flags.append(Flag.NO_DARKNESS)
    factors.append(FactorScore("darkness", Role.GATE, 100.0 * dark, dark))

    precip_gate = 1.0
    precip_value: float | None = None
    if precipitation_mm is not None and precipitation_mm > 0.0:
        precip_gate = 0.0
        precip_value = 0.0
    elif precipitation_probability is not None:
        p = _clamp(float(precipitation_probability), 0.0, 100.0)
        precip_gate = _ramp_down(p, *PRECIP_PROBABILITY_RAMP)
        precip_value = 100.0 - p  # "dry %", so every row reads higher-is-better
    if precip_gate <= 0.0:
        flags.append(Flag.PRECIPITATION)
    factors.append(
        FactorScore(
            "precipitation", Role.GATE, precip_value, precip_gate, applied=precip_value is not None
        )
    )

    wind_gate = 1.0
    if wind_speed_kmh is not None:
        wind_gate = _ramp_down(max(0.0, float(wind_speed_kmh)), *WIND_GATE_RAMP_KMH)
        if wind_gate <= 0.0:
            flags.append(Flag.WIND_GATE)
    factors.append(
        FactorScore(
            "wind_gate",
            Role.GATE,
            None if wind_speed_kmh is None else 100.0 * wind_gate,
            wind_gate,
            applied=wind_speed_kmh is not None,
        )
    )

    # ---- availability: cloud yield -----------------------------------------
    cloud_fraction, cloud_flags = effective_cloud_fraction(
        cloud_cover=cloud_cover,
        cloud_cover_low=cloud_cover_low,
        cloud_cover_mid=cloud_cover_mid,
        cloud_cover_high=cloud_cover_high,
    )
    flags.extend(cloud_flags)
    yield_ = cloud_yield(cloud_fraction)
    # value shown is clear-sky %, so every row reads higher-is-better
    factors.append(FactorScore("cloud", Role.YIELD, 100.0 * (1.0 - cloud_fraction), yield_))

    availability = dark * precip_gate * wind_gate * yield_

    # ---- quality ------------------------------------------------------------
    sub = {
        "seeing": _required_pct("seeing", seeing),
        "transparency": _required_pct("transparency", transparency),
        "wind_calm": _required_pct("wind_calm", wind_calm),
    }
    base = sum(QUALITY_WEIGHTS[k] * sub[k] for k in QUALITY_WEIGHTS) / 100.0
    for k in QUALITY_WEIGHTS:
        factors.append(FactorScore(k, Role.QUALITY, sub[k], QUALITY_WEIGHTS[k]))

    moon_value = _required_pct("moon", moon)
    if mode is Mode.NARROWBAND:
        moon_factor = 1.0
        factors.append(FactorScore("moon", Role.MODIFIER, moon_value, 1.0, applied=False))
    else:
        moon_factor = MOON_FLOOR + (1.0 - MOON_FLOOR) * moon_value / 100.0
        factors.append(FactorScore("moon", Role.MODIFIER, moon_value, moon_factor))

    quality = base * moon_factor

    # ---- advisory -----------------------------------------------------------
    if temperature_c is not None and dew_point_c is not None:
        if float(temperature_c) - float(dew_point_c) <= DEW_RISK_SPREAD_C:
            flags.append(Flag.DEW_RISK)

    # ---- compose ------------------------------------------------------------
    score = _round_half_up(100.0 * availability * quality)
    label = _label(score, availability)

    return ImagingQuality(
        score=score,
        label=label,
        availability=availability,
        quality=100.0 * quality,
        mode=mode,
        factors=tuple(factors),
        flags=tuple(flags),
    )


def label_for_score(score: int, availability: float) -> str:
    """Label for a score / availability pair.

    Public because the nightly aggregate is labelled by the same rule as an
    individual hour — ``Unusable`` is a statement about availability, not a
    bottom bucket of the 0-100 scale, so it cannot be re-derived from the score
    alone.
    """
    if availability < UNUSABLE_AVAILABILITY:
        return UNUSABLE_LABEL
    for threshold, name in LABEL_THRESHOLDS:
        if score >= threshold:
            return name
    return "Poor"


_label = label_for_score


def expected_useful_hours(results: Iterable[ImagingQuality]) -> float:
    """Night-level summary: equivalent hours of perfect data.

    Sums ``availability * quality`` rather than the rounded integer score, so a
    long night does not accumulate half a point of rounding error per hour.
    Hours outside darkness contribute 0 automatically.
    """
    return sum(r.availability * r.quality / 100.0 for r in results)
