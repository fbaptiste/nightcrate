"""Parity coverage for the planner's vectorized score-only pass."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import numpy as np
import pytest

from nightcrate.core.config import Settings
from nightcrate.services.planner_scoring import ScoringInput, score_targets, score_values
from nightcrate.services.planner_visibility import (
    DarkWindow,
    VisibilitySnapshot,
    VisibilityTimeSeries,
)


def _snapshot(
    altitudes: np.ndarray,
    visible: np.ndarray,
    *,
    moon_altitude: np.ndarray | None = None,
    moon_separation: np.ndarray | None = None,
    moon_phase: float = 70.0,
) -> VisibilitySnapshot:
    rows, samples = altitudes.shape
    start = datetime(2026, 1, 15, 1, 0, tzinfo=UTC)
    times = tuple(start + timedelta(minutes=5 * index) for index in range(samples))
    return VisibilitySnapshot(
        location_id=1,
        night_date=date(2026, 1, 15),
        dark_window=DarkWindow(start, times[-1]),
        moon_phase_pct=moon_phase,
        time_series=VisibilityTimeSeries(
            dso_id_to_index={index + 1: index for index in range(rows)},
            times_utc=times,
            altitude_deg=altitudes,
            visible_mask=visible,
            moon_altitude_deg=(
                moon_altitude if moon_altitude is not None else np.full(samples, 45.0)
            ),
            moon_separation_deg=(
                moon_separation if moon_separation is not None else np.full((rows, samples), 50.0)
            ),
        ),
    )


def _assert_parity(
    inputs: list[ScoringInput],
    snapshot: VisibilitySnapshot,
    *,
    settings: Settings | None = None,
    rig: bool = True,
    filters: tuple[str, ...] = ("L",),
) -> None:
    settings = settings or Settings()
    fov_major = 2.0 if rig else None
    fov_minor = 1.5 if rig else None
    detailed = score_targets(
        inputs,
        snapshot,
        fov_major,
        fov_minor,
        filters,
        settings,
        "America/Phoenix",
    )
    values = score_values(
        inputs,
        snapshot,
        fov_major,
        fov_minor,
        filters,
        settings,
    )
    assert values == {
        dso_id: (score.score_pct, score.quality_label) for dso_id, score in detailed.items()
    }


def test_gate_and_dimension_edge_cases_match_detailed_scores():
    samples = 24
    altitudes = np.full((8, samples), 55.0)
    visible = np.ones((8, samples), dtype=bool)
    visible[2] = False  # horizon gate alone
    visible[3] = False  # hours + horizon gates together
    altitudes[5] = 20.0  # no samples above scoring minimum
    snapshot = _snapshot(altitudes, visible)
    inputs = [
        ScoringInput(
            dso_id=index + 1,
            obj_type="GCl" if index == 6 else "G",
            coverage_pct=500.0 if index == 4 else 55.0,
            hours_visible=0.0 if index in {1, 3} else 2.0,
            peak_time_utc=snapshot.dark_mid_utc,
            transit_time_utc=snapshot.dark_mid_utc,
        )
        for index in range(8)
    ]
    settings = Settings().model_copy(update={"scoring_gate_max_coverage_pct": 100.0})
    _assert_parity(inputs, snapshot, settings=settings)


def test_extreme_coverage_scores_zero_without_warnings():
    altitudes = np.full((1, 24), 55.0)
    snapshot = _snapshot(altitudes, np.ones_like(altitudes, dtype=bool))
    inputs = [
        ScoringInput(
            dso_id=1,
            obj_type="G",
            coverage_pct=1500.0,
            hours_visible=2.0,
            peak_time_utc=snapshot.dark_mid_utc,
            transit_time_utc=snapshot.dark_mid_utc,
        )
    ]
    settings = Settings()

    with np.errstate(all="raise"):
        values = score_values(inputs, snapshot, 2.0, 1.5, ("L",), settings)
        detailed = score_targets(
            inputs,
            snapshot,
            2.0,
            1.5,
            ("L",),
            settings,
            "America/Phoenix",
        )

    assert values[1][0] == 0
    assert detailed[1].score_pct == 0


@pytest.mark.parametrize(
    ("moon_phase", "moon_altitude", "rig", "filters", "min_altitude"),
    [
        (0.0, 45.0, True, ("L",), 30.0),  # new moon
        (70.0, -5.0, True, ("L",), 30.0),  # Moon down all window
        (70.0, 45.0, False, ("L",), 30.0),  # no rig
        (70.0, 45.0, True, (), 30.0),  # no filter intent
        (70.0, 45.0, True, ("L",), 90.0),  # degenerate observability anchor
    ],
)
def test_context_edge_cases_match_detailed_scores(
    moon_phase: float,
    moon_altitude: float,
    rig: bool,
    filters: tuple[str, ...],
    min_altitude: float,
):
    altitudes = np.full((2, 24), 90.0 if min_altitude == 90.0 else 55.0)
    snapshot = _snapshot(
        altitudes,
        np.ones_like(altitudes, dtype=bool),
        moon_altitude=np.full(24, moon_altitude),
        moon_phase=moon_phase,
    )
    inputs = [
        ScoringInput(
            dso_id=1,
            obj_type="GCl",
            coverage_pct=55.0,
            hours_visible=2.0,
            peak_time_utc=snapshot.dark_mid_utc,
            transit_time_utc=snapshot.dark_mid_utc,
        ),
        ScoringInput(
            dso_id=2,
            obj_type="G",
            coverage_pct=None if not rig else 90.0,
            hours_visible=2.0,
            peak_time_utc=snapshot.dark_mid_utc,
            transit_time_utc=snapshot.dark_mid_utc,
        ),
    ]
    settings = Settings().model_copy(
        update={"scoring_observability_min_altitude_deg": min_altitude}
    )
    _assert_parity(inputs, snapshot, settings=settings, rig=rig, filters=filters)


def test_seeded_random_500_target_snapshot_matches_detailed_scores():
    rng = np.random.default_rng(440)
    rows = 500
    samples = 36
    altitudes = rng.uniform(5.0, 88.0, size=(rows, samples))
    visible = rng.random((rows, samples)) > 0.15
    snapshot = _snapshot(
        altitudes,
        visible,
        moon_altitude=rng.uniform(-20.0, 70.0, size=samples),
        moon_separation=rng.uniform(5.0, 180.0, size=(rows, samples)),
        moon_phase=83.0,
    )
    inputs = [
        ScoringInput(
            dso_id=index + 1,
            obj_type=rng.choice(["G", "HII", "OCl", "GCl", "*Ass", "Cl+N"]),
            coverage_pct=(None if index % 17 == 0 else float(rng.uniform(1.0, 250.0))),
            hours_visible=float(visible[index].sum() * 5.0 / 60.0),
            peak_time_utc=snapshot.dark_mid_utc,
            transit_time_utc=snapshot.dark_mid_utc
            + timedelta(minutes=float(rng.uniform(-120.0, 120.0))),
        )
        for index in range(rows)
    ]
    _assert_parity(inputs, snapshot, filters=("Ha", "OIII", "L"))
