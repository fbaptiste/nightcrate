"""Shared fixtures + builders for ``test_scoring_*`` tests.

The scoring service consumes a ``VisibilitySnapshot`` populated with
per-target time-series arrays. These helpers build synthetic snapshots
with known alt / moon-alt / moon-sep arrays so each dimension can be
tested in isolation without a full astropy compute.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import numpy as np

from nightcrate.core.config import Settings
from nightcrate.services.planner_scoring import ScoringInput
from nightcrate.services.planner_visibility import (
    DarkWindow,
    VisibilitySnapshot,
    VisibilityTimeSeries,
)

_SAMPLE_MINUTES = 5


def make_time_series(
    n_samples: int,
    dark_start: datetime,
) -> list[datetime]:
    """Dense 5-minute sample grid starting at ``dark_start``."""
    return [dark_start + timedelta(minutes=_SAMPLE_MINUTES * i) for i in range(n_samples)]


def default_settings(**overrides) -> Settings:
    """Return a Settings instance with the scoring defaults, optionally
    overriding specific fields. Only overriding keys that exist on the
    model; extras raise ``ValidationError`` so typos fail loudly.
    """
    base = Settings()
    if not overrides:
        return base
    return base.model_copy(update=overrides)


def make_snapshot(
    *,
    dso_id: int = 1,
    altitude_deg: Sequence[float] | np.ndarray,
    visible_mask: Sequence[bool] | np.ndarray | None = None,
    moon_altitude_deg: Sequence[float] | np.ndarray | None = None,
    moon_separation_deg: Sequence[float] | np.ndarray | None = None,
    moon_phase_pct: float = 0.0,
    dark_start: datetime | None = None,
    n_samples: int | None = None,
) -> VisibilitySnapshot:
    """Build a synthetic single-DSO snapshot.

    - ``visible_mask`` defaults to "wherever altitude > 0".
    - ``moon_altitude_deg`` defaults to zeros (moon down — dimension
      stays neutral).
    - ``moon_separation_deg`` defaults to 180° everywhere.
    - ``dark_start`` defaults to 2026-01-15 00:00 UTC; dark_end is
      derived from ``n_samples * _SAMPLE_MINUTES``.
    - ``n_samples`` defaults to ``len(altitude_deg)``; the grid is
      always dense.
    """
    alt_row = np.asarray(altitude_deg, dtype=float)
    n = int(alt_row.shape[0]) if n_samples is None else n_samples
    if dark_start is None:
        dark_start = datetime(2026, 1, 15, 0, 0, tzinfo=UTC)
    dark_end = dark_start + timedelta(minutes=_SAMPLE_MINUTES * (n - 1))

    if visible_mask is None:
        vis_row = alt_row > 0.0
    else:
        vis_row = np.asarray(visible_mask, dtype=bool)

    if moon_altitude_deg is None:
        moon_alt = np.zeros(n, dtype=float)
    else:
        moon_alt = np.asarray(moon_altitude_deg, dtype=float)

    if moon_separation_deg is None:
        moon_sep_row = np.full(n, 180.0, dtype=float)
    else:
        moon_sep_row = np.asarray(moon_separation_deg, dtype=float)

    # Reshape to (1, N) for consistency with real snapshots.
    alt_2d = alt_row.reshape(1, -1)
    vis_2d = vis_row.reshape(1, -1)
    sep_2d = moon_sep_row.reshape(1, -1)

    times_tuple = tuple(make_time_series(n, dark_start))

    time_series = VisibilityTimeSeries(
        dso_id_to_index={dso_id: 0},
        times_utc=times_tuple,
        altitude_deg=alt_2d,
        visible_mask=vis_2d,
        moon_altitude_deg=moon_alt,
        moon_separation_deg=sep_2d,
    )

    return VisibilitySnapshot(
        location_id=1,
        night_date=date(2026, 1, 15),
        dark_window=DarkWindow(start_utc=dark_start, end_utc=dark_end),
        moon_phase_pct=moon_phase_pct,
        per_dso={},
        time_series=time_series,
    )


def peak_time_utc(snapshot: VisibilitySnapshot) -> datetime:
    """Return the timestamp of the maximum-altitude sample inside the
    dark window. Used by tests as a stand-in for the
    ``DsoVisibility.peak_time_utc`` scalar the API layer would
    normally pass in.
    """
    ts = snapshot.time_series
    assert ts is not None
    alt_row = ts.altitude_deg[0]
    idx = int(np.argmax(alt_row))
    return ts.times_utc[idx]


def make_input(
    *,
    dso_id: int = 1,
    obj_type: str | None = "G",
    coverage_pct: float | None = None,
    hours_visible: float | None = None,
    peak_time: datetime | None = None,
) -> ScoringInput:
    return ScoringInput(
        dso_id=dso_id,
        obj_type=obj_type,
        coverage_pct=coverage_pct,
        hours_visible=hours_visible,
        peak_time_utc=peak_time,
    )


def snapshot_with_phase(snapshot: VisibilitySnapshot, moon_phase_pct: float) -> VisibilitySnapshot:
    """Return a copy of ``snapshot`` with a different moon phase."""
    return replace(snapshot, moon_phase_pct=moon_phase_pct)
