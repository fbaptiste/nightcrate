"""Tests for the Target Planner ``now_status`` compute.

Exercises the three branches of the clock-vs-dark-window decision:
daytime before tonight, inside astro-dark, and post-dawn.
"""

from __future__ import annotations

from datetime import UTC, datetime

from nightcrate.services.planner_now_status import compute_now_status
from nightcrate.services.planner_visibility import (
    DsoCoord,
    PlannerHorizon,
    PlannerLocation,
)

PHOENIX = PlannerLocation(
    id=1,
    latitude_deg=33.4484,
    longitude_deg=-112.0740,
    elevation_m=331.0,
    timezone="America/Phoenix",
    updated_at="2026-04-01T00:00:00",
)

FLAT_0 = PlannerHorizon(
    id=1,
    location_id=1,
    name="0° flat",
    type="artificial",
    flat_altitude_deg=0.0,
    points=(),
    updated_at="2026-04-01T00:00:00",
)

# Phoenix tonight, 2026-04-22:
# sunset ~ 7:00 pm MST = 02:00 UTC next day
# astro dusk ~ 8:20 pm MST = 03:20 UTC next day
# astro dawn ~ 4:20 am MST = 11:20 UTC
# sunrise ~ 5:45 am MST = 12:45 UTC
DARK_START = datetime(2026, 4, 23, 3, 20, tzinfo=UTC)  # ~8:20 PM local
DARK_END = datetime(2026, 4, 23, 11, 20, tzinfo=UTC)  # ~4:20 AM local

# Orion (RA ~5h35m, Dec -5°) — in April, transits in the afternoon
# from Phoenix, so at 2 PM local (21:00 UTC) it's up; at 2 AM local
# (09:00 UTC) it's already set for the night.
M42 = DsoCoord(dso_id=1, ra_deg=83.82, dec_deg=-5.39)

# Circumpolar-ish — high-dec target that's always reachable from
# Phoenix. Here used as a "definitely rising at some point tonight"
# fixture.
M81 = DsoCoord(dso_id=2, ra_deg=148.89, dec_deg=69.07)

# Southern target that never rises above 0° from Phoenix.
CROSS = DsoCoord(dso_id=3, ra_deg=186.65, dec_deg=-63.1)


def test_post_dawn_returns_empty():
    """Post-dawn ``now`` — tonight's session is over; the function
    returns an empty dict (frontend renders no glyph)."""
    now = DARK_END.replace(hour=12)  # 5 AM local → well past dawn
    result = compute_now_status(
        PHOENIX,
        FLAT_0,
        [M42, M81],
        now_utc=now,
        astro_dark_start_utc=DARK_START,
        astro_dark_end_utc=DARK_END,
    )
    assert result == {}


def test_daytime_rising_not_up():
    """Daytime ``now`` before tonight — even if the object is above
    horizon right now, status must NOT be ``"up"`` (user can't
    observe during daytime)."""
    # 2 PM local = 21:00 UTC — well before dark_start at 03:20 UTC.
    now = datetime(2026, 4, 22, 21, 0, tzinfo=UTC)
    result = compute_now_status(
        PHOENIX,
        FLAT_0,
        [M42],
        now_utc=now,
        astro_dark_start_utc=DARK_START,
        astro_dark_end_utc=DARK_END,
    )
    # M42 is NOT above horizon during tonight's dark window
    # (it sets in the west around 9 PM local), so this is "set".
    # The key assertion: not "up" — which the old code would have
    # returned if M42 was above horizon at the daytime ``now``.
    assert result[M42.dso_id] != "up"


def test_daytime_rising_target_gets_rising():
    """Daytime ``now``, object rises during tonight's dark window →
    ``"rising"`` (the bug Fred reported — a previously-set object
    that comes back up tonight shouldn't read as ``"set"``)."""
    now = datetime(2026, 4, 22, 21, 0, tzinfo=UTC)  # 2 PM local
    result = compute_now_status(
        PHOENIX,
        FLAT_0,
        [M81],
        now_utc=now,
        astro_dark_start_utc=DARK_START,
        astro_dark_end_utc=DARK_END,
    )
    # M81 is a high-dec circumpolar target — guaranteed above horizon
    # at some point during tonight's dark window.
    assert result[M81.dso_id] == "rising"


def test_daytime_truly_set_gets_set():
    """Daytime ``now``, object never clears horizon during tonight
    → ``"set"`` (southern target from Phoenix)."""
    now = datetime(2026, 4, 22, 21, 0, tzinfo=UTC)
    result = compute_now_status(
        PHOENIX,
        FLAT_0,
        [CROSS],
        now_utc=now,
        astro_dark_start_utc=DARK_START,
        astro_dark_end_utc=DARK_END,
    )
    assert result[CROSS.dso_id] == "set"


def test_during_dark_up_now_fires():
    """Inside tonight's astro-dark window, an above-horizon object
    gets ``"up"``."""
    # Midnight local (2026-04-23 07:00 UTC). M81 is up.
    now = datetime(2026, 4, 23, 7, 0, tzinfo=UTC)
    result = compute_now_status(
        PHOENIX,
        FLAT_0,
        [M81],
        now_utc=now,
        astro_dark_start_utc=DARK_START,
        astro_dark_end_utc=DARK_END,
    )
    assert result[M81.dso_id] == "up"


def test_no_dark_window_returns_empty():
    """Polar summer — either bound is ``None`` → empty dict."""
    result = compute_now_status(
        PHOENIX,
        FLAT_0,
        [M42],
        now_utc=datetime(2026, 6, 21, 12, 0, tzinfo=UTC),
        astro_dark_start_utc=None,
        astro_dark_end_utc=None,
    )
    assert result == {}
