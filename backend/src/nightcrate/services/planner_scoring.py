"""Target Planner scoring algorithm (v0.21.0).

Per-target 0-100 quality score with a transparent breakdown, computed
against tonight's visibility snapshot, the selected rig, the user-declared
filter intent, and the ~25 tunable parameters on ``Settings``.

Pure-function module — no FastAPI / DB deps. The API layer assembles a
``ScoringInput`` per target, hands them to ``score_targets`` alongside
the cached ``VisibilitySnapshot``, and receives a ``dict[dso_id,
TargetScore]``. See ``docs/planner-scoring.md`` for the user-facing
algorithm primer.

Pipeline (per target): hard gates → four quality dimensions (0-1
each) → weighted geometric mean → 0-100 + quality chip. Dimensions
that drop out (no rig → frame_fit absent; no filter intent → moon
neutral) are handled inside the dimension functions.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

import numpy as np

from nightcrate.core.config import Settings
from nightcrate.services.planner_scoring_constants import (
    CLUSTER_OBJ_TYPES,
    FILTER_LINES,
    QUALITY_LABELS,
)
from nightcrate.services.planner_visibility import VisibilitySnapshot

DimensionKey = Literal["observability", "meridian", "moon", "frame_fit"]

_DIMENSION_LABEL: dict[DimensionKey, str] = {
    "observability": "Observability",
    "meridian": "Meridian timing",
    "moon": "Moon impact",
    "frame_fit": "Frame fit",
}


@dataclass(frozen=True, slots=True)
class ScoringInput:
    """Flat per-target input row assembled by the API layer.

    Entries absent from the visibility snapshot pass
    ``hours_visible=None`` / ``peak_time_utc=None`` — the min-hours
    gate trips with the correct "never rose" reason.
    """

    dso_id: int
    obj_type: str | None
    coverage_pct: float | None
    hours_visible: float | None
    peak_time_utc: datetime | None


@dataclass(frozen=True, slots=True)
class DimensionBreakdown:
    """One quality dimension's contribution + human-readable facts."""

    key: DimensionKey
    label: str
    score: float  # 0-1
    weight: float
    contribution: float  # score ** weight, the factor in the geometric mean
    inputs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    """Attached to every ``TargetScore``.

    ``gate_failures`` is non-empty only when ``score_pct is None`` —
    ``dimensions`` is empty in that case. Otherwise ``dimensions`` has
    one entry per active dimension; dropped dimensions are omitted.
    """

    dimensions: tuple[DimensionBreakdown, ...]
    gate_failures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TargetScore:
    """Scoring result for one target."""

    dso_id: int
    score_pct: int | None
    quality_label: str | None
    breakdown: ScoreBreakdown


# ── Hard gates ──────────────────────────────────────────────────────


def _run_gates(
    scoring_input: ScoringInput,
    visible_row: np.ndarray | None,
    settings: Settings,
    has_rig: bool,
) -> list[str]:
    """Run every hard gate in stable order. Returns failure reasons;
    empty means scoring proceeds. Multiple gates can trip on the same
    target — the breakdown surfaces all of them."""
    failures: list[str] = []

    hours = scoring_input.hours_visible or 0.0
    if hours < settings.scoring_gate_min_obs_hours:
        failures.append(
            f"only {hours:.1f} h above the horizon during astro-dark "
            f"(gate: {settings.scoring_gate_min_obs_hours:.1f} h)"
        )

    # Subsumed by the hours gate in most cases but the message matters
    # for users with tight tree lines.
    if visible_row is not None and not visible_row.any():
        failures.append("below your horizon for the entire astro-dark window")

    cov_cap = settings.scoring_gate_max_coverage_pct
    if (
        cov_cap is not None
        and has_rig
        and scoring_input.coverage_pct is not None
        and scoring_input.coverage_pct > cov_cap
    ):
        failures.append(
            f"coverage {scoring_input.coverage_pct:.0f}% exceeds the "
            f"{cov_cap:.0f}% gate (mosaic territory)"
        )

    return failures


# ── Dimension: Observability ────────────────────────────────────────


def _compute_observability(
    alt_row: np.ndarray,
    visible_row: np.ndarray,
    min_altitude_deg: float,
    sample_minutes: float,
) -> tuple[float, tuple[str, ...]]:
    """Mean altitude-quality across samples where the target is above
    both the custom horizon AND the scoring min-altitude threshold.

    ``quality(t) = max(0, 1 - (airmass(t) - 1) / (max_airmass - 1))``.
    Airmass via the sec(z) approximation; the min-altitude anchor
    pins quality to 0 at the threshold and 1 at zenith.
    """
    usable = visible_row & (alt_row >= min_altitude_deg)
    if not usable.any():
        return 0.0, (f"never above {min_altitude_deg:.0f}° during astro-dark",)

    alts = alt_row[usable]
    sin_alts = np.sin(np.radians(alts))
    airmass = 1.0 / np.maximum(sin_alts, 1e-6)

    min_sin = math.sin(math.radians(min_altitude_deg))
    max_airmass = 1.0 / max(min_sin, 1e-6)

    denom = max_airmass - 1.0
    if denom <= 0.0:
        # Degenerate (min_altitude=90°) — every usable sample is at zenith.
        quality = np.ones_like(airmass)
    else:
        quality = np.clip(1.0 - (airmass - 1.0) / denom, 0.0, 1.0)

    score = float(quality.mean())

    hours = float(usable.sum() * (sample_minutes / 60.0))
    peak_alt = float(alts.max())
    facts = (
        f"{hours:.1f} h above {min_altitude_deg:.0f}° during astro-dark",
        f"peak altitude {peak_alt:.0f}°",
    )
    return score, facts


# ── Dimension: Meridian timing ──────────────────────────────────────


def _compute_meridian(
    peak_time_utc: datetime,
    dark_start_utc: datetime,
    dark_end_utc: datetime,
    dark_mid_utc: datetime,
    tz_name: str,
) -> tuple[float, tuple[str, ...]]:
    """``1 - |t_peak - t_mid| / half_dark``, clamped to [0, 1].

    ``peak_time_utc`` is produced by the visibility reduction: transit
    when it falls inside astro-dark, else the higher-altitude dark-window
    endpoint.
    """
    dark_hours = (dark_end_utc - dark_start_utc).total_seconds() / 3600.0
    half_dark = dark_hours / 2.0
    if half_dark <= 0:
        return 0.0, ("astro-dark window is zero length",)

    delta_hours = abs((peak_time_utc - dark_mid_utc).total_seconds() / 3600.0)
    score = max(0.0, 1.0 - delta_hours / half_dark)

    try:
        tz = ZoneInfo(tz_name)
        peak_local = peak_time_utc.astimezone(tz).strftime("%H:%M")
        mid_local = dark_mid_utc.astimezone(tz).strftime("%H:%M")
    except Exception:  # pragma: no cover — zoneinfo lookup failure
        peak_local = peak_time_utc.strftime("%H:%MZ")
        mid_local = dark_mid_utc.strftime("%H:%MZ")
    facts = (
        f"peak at {peak_local} local (dark midpoint {mid_local})",
        f"{delta_hours:.1f} h from the midpoint of {dark_hours:.1f} h of dark",
    )
    return score, facts


# ── Dimension: Moon impact ──────────────────────────────────────────


def _moon_sensitivity_and_min_sep(filter_line: str, settings: Settings) -> tuple[float, float]:
    key = filter_line.lower()
    sens = getattr(settings, f"scoring_moon_sensitivity_{key}")
    min_sep = getattr(settings, f"scoring_moon_min_sep_{key}")
    return float(sens), float(min_sep)


def _compute_moon(
    visible_row: np.ndarray,
    moon_alt: np.ndarray,
    moon_sep_row: np.ndarray,
    moon_phase_pct: float,
    filter_intent: Sequence[str],
    obj_type: str | None,
    settings: Settings,
) -> tuple[float, tuple[str, ...]]:
    """Moon impact over the target's observation window.

    No filter intent → ``moon_score = 1.0``. With filter intent, the
    most-sensitive filter sets session-wide parameters (spec §7.2). The
    cluster modifier softens impact for OCl / GCl / *Ass targets.
    """
    if not filter_intent:
        return 1.0, ("no filter intent declared — moon dimension is neutral",)

    sens_pairs = [
        (f, *_moon_sensitivity_and_min_sep(f, settings)) for f in filter_intent if f in FILTER_LINES
    ]
    if not sens_pairs:
        return 1.0, ("filter intent did not match any known line",)
    limiting_filter, sensitivity, min_sep = max(sens_pairs, key=lambda t: t[1])

    phase = moon_phase_pct / 100.0
    if phase <= 0.0:
        return 1.0, ("moon phase 0% (new moon) — no impact regardless of position",)

    obs_samples = int(visible_row.sum())
    if obs_samples == 0:
        # Subsumed by a hard gate; neutral keeps the geometric mean
        # from biting on nothing.
        return 1.0, ("no observation samples — moon dimension is neutral",)

    moon_up_in_obs = visible_row & (moon_alt > 0.0)
    if not moon_up_in_obs.any():
        return 1.0, (
            f"moon below horizon for the entire observation window "
            f"(limiting filter {limiting_filter})",
        )

    alt_m = moon_alt[moon_up_in_obs]
    sep_m = moon_sep_row[moon_up_in_obs]

    moon_alt_factor = np.sqrt(np.clip(np.sin(np.radians(alt_m)), 0.0, 1.0))
    base = sensitivity * phase * moon_alt_factor
    sky_glow = base * settings.scoring_moon_sky_glow_weight
    proximity = np.minimum(1.0, sep_m / max(min_sep, 1e-6))
    proximity_penalty = base * (1.0 - proximity) * settings.scoring_moon_proximity_weight
    per_sample_impact = sky_glow + proximity_penalty

    mean_impact = float(per_sample_impact.mean())
    overlap = moon_up_in_obs.sum() / obs_samples

    is_cluster = obj_type in CLUSTER_OBJ_TYPES
    cluster_factor = settings.scoring_cluster_moon_modifier if is_cluster else 1.0
    adjusted_impact = mean_impact * cluster_factor

    moon_score = float(np.clip(1.0 - adjusted_impact * overlap, 0.0, 1.0))

    mean_sep = float(sep_m.mean())
    overlap_pct = overlap * 100.0
    facts: list[str] = [
        f"limiting filter {limiting_filter} (sensitivity {sensitivity:.2f}, "
        f"min separation {min_sep:.0f}°)",
        f"moon phase {moon_phase_pct:.0f}%, mean separation {mean_sep:.0f}° while up",
        f"moon up {overlap_pct:.0f}% of the observation window",
    ]
    if is_cluster:
        facts.append(f"cluster modifier ×{settings.scoring_cluster_moon_modifier:.2f} applied")
    return moon_score, tuple(facts)


# ── Dimension: Frame fit ────────────────────────────────────────────


def _compute_frame_fit(
    coverage_pct: float,
    ideal_pct: float,
    spread: float,
) -> tuple[float, tuple[str, ...]]:
    """Gaussian on coverage: ``exp(-((cov - ideal) / spread) ** 2)``.

    Graceful at extremes — coverage 1500% yields score ~0, coverage =
    ideal yields 1.0. Spread is the standard-deviation knob: low →
    demanding, high → forgiving.
    """
    spread_safe = max(spread, 1e-6)
    z = (coverage_pct - ideal_pct) / spread_safe
    score = float(math.exp(-(z * z)))
    verdict = _frame_fit_verdict(coverage_pct, ideal_pct)
    facts = (
        f"coverage {coverage_pct:.0f}% (ideal {ideal_pct:.0f}%, spread {spread:.0f})",
        verdict,
    )
    return score, facts


def _frame_fit_verdict(coverage_pct: float, ideal_pct: float) -> str:
    ratio = coverage_pct / max(ideal_pct, 1e-6)
    if 0.8 <= ratio <= 1.2:
        return "framing is on-target"
    if ratio < 0.5:
        return "target is smaller than your framing preference"
    if ratio < 0.8:
        return "target is a bit small for your framing preference"
    if ratio <= 2.0:
        return "target overfills your framing preference"
    return "target is mosaic-scale for this rig"


# ── Combination ─────────────────────────────────────────────────────


def _weighted_geometric_mean(entries: Sequence[tuple[float, float]]) -> float:
    """Weighted geometric mean ``(prod(s_i ** w_i)) ** (1 / sum(w_i))``.

    A zero score anywhere drags the product to zero. Weight-0 entries
    are dropped from both numerator and denominator.
    """
    active = [(s, w) for s, w in entries if w > 0]
    if not active:
        return 0.0
    total_weight = sum(w for _, w in active)
    log_sum = 0.0
    for s, w in active:
        if s <= 0.0:
            return 0.0
        log_sum += w * math.log(s)
    return math.exp(log_sum / total_weight)


def _label_for_score(score_pct: int, settings: Settings) -> str:
    if score_pct >= settings.scoring_threshold_excellent:
        return QUALITY_LABELS[0]
    if score_pct >= settings.scoring_threshold_good:
        return QUALITY_LABELS[1]
    if score_pct >= settings.scoring_threshold_fair:
        return QUALITY_LABELS[2]
    return QUALITY_LABELS[3]


def _make_dimension_row(
    key: DimensionKey,
    score: float,
    weight: float,
    facts: tuple[str, ...],
) -> DimensionBreakdown:
    contribution = score**weight if score > 0 else 0.0
    return DimensionBreakdown(
        key=key,
        label=_DIMENSION_LABEL[key],
        score=score,
        weight=weight,
        contribution=contribution,
        inputs=facts,
    )


# ── Public API ──────────────────────────────────────────────────────


def score_targets(
    inputs: Sequence[ScoringInput],
    snapshot: VisibilitySnapshot,
    rig_fov_major_deg: float | None,
    rig_fov_minor_deg: float | None,
    filter_intent: Sequence[str],
    settings: Settings,
    tz_name: str,
) -> dict[int, TargetScore]:
    """Score every input row against the snapshot.

    Returns a dict keyed by ``dso_id``. Dropped dimensions (no rig →
    frame_fit; no filter intent → moon neutral) are handled per-
    dimension; the combiner sees at most four entries per target.
    """
    has_rig = rig_fov_major_deg is not None and rig_fov_minor_deg is not None
    ts = snapshot.time_series
    dark_start = snapshot.dark_window.start_utc
    dark_end = snapshot.dark_window.end_utc
    dark_mid = snapshot.dark_mid_utc
    sample_minutes = _time_series_sample_minutes(snapshot)

    out: dict[int, TargetScore] = {}

    for item in inputs:
        row_idx = ts.dso_id_to_index.get(item.dso_id) if ts is not None else None
        have_row = ts is not None and row_idx is not None
        alt_row = ts.altitude_deg[row_idx] if have_row else None
        visible_row = ts.visible_mask[row_idx] if have_row else None
        moon_sep_row = ts.moon_separation_deg[row_idx] if have_row else None

        failures = _run_gates(item, visible_row, settings, has_rig)
        if failures:
            out[item.dso_id] = TargetScore(
                dso_id=item.dso_id,
                score_pct=None,
                quality_label=None,
                breakdown=ScoreBreakdown(
                    dimensions=(),
                    gate_failures=tuple(failures),
                ),
            )
            continue

        # Gates passed → snapshot arrays + dark-window endpoints exist
        # by construction (gate_min_obs_hours would have tripped
        # otherwise). Asserts are type narrowing, not runtime checks.
        assert alt_row is not None  # nosec B101
        assert visible_row is not None  # nosec B101
        assert moon_sep_row is not None  # nosec B101
        assert ts is not None  # nosec B101
        assert dark_start is not None and dark_end is not None  # nosec B101
        assert dark_mid is not None  # nosec B101
        assert item.peak_time_utc is not None  # nosec B101

        obs_score, obs_facts = _compute_observability(
            alt_row,
            visible_row,
            settings.scoring_observability_min_altitude_deg,
            sample_minutes,
        )
        mer_score, mer_facts = _compute_meridian(
            item.peak_time_utc, dark_start, dark_end, dark_mid, tz_name
        )
        moon_score, moon_facts = _compute_moon(
            visible_row,
            ts.moon_altitude_deg,
            moon_sep_row,
            snapshot.moon_phase_pct,
            filter_intent,
            item.obj_type,
            settings,
        )

        dimension_rows: list[DimensionBreakdown] = [
            _make_dimension_row(
                "observability", obs_score, settings.scoring_weight_observability, obs_facts
            ),
            _make_dimension_row("meridian", mer_score, settings.scoring_weight_meridian, mer_facts),
            _make_dimension_row("moon", moon_score, settings.scoring_weight_moon, moon_facts),
        ]

        if has_rig and item.coverage_pct is not None:
            fit_score, fit_facts = _compute_frame_fit(
                item.coverage_pct,
                settings.scoring_frame_fit_ideal_coverage_pct,
                settings.scoring_frame_fit_spread,
            )
            dimension_rows.append(
                _make_dimension_row(
                    "frame_fit", fit_score, settings.scoring_weight_frame_fit, fit_facts
                )
            )

        raw = _weighted_geometric_mean([(row.score, row.weight) for row in dimension_rows])
        score_pct = int(round(raw * 100))
        label = _label_for_score(score_pct, settings)

        out[item.dso_id] = TargetScore(
            dso_id=item.dso_id,
            score_pct=score_pct,
            quality_label=label,
            breakdown=ScoreBreakdown(
                dimensions=tuple(dimension_rows),
                gate_failures=(),
            ),
        )

    return out


def _time_series_sample_minutes(snapshot: VisibilitySnapshot) -> float:
    """Derive the sample cadence from the time-series timestamps.

    Falls back to 5 minutes (matching the visibility module's
    ``_SAMPLE_MINUTES``) when fewer than two samples — in that case
    gates trip first, but avoid division-by-zero downstream.
    """
    ts = snapshot.time_series
    if ts is None or len(ts.times_utc) < 2:
        return 5.0
    return (ts.times_utc[1] - ts.times_utc[0]).total_seconds() / 60.0
