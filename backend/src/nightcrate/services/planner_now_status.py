"""Per-DSO "currently up / rising later / already set" status snapshot.

Run at request time, once per planner-targets fetch. For each DSO
with coordinates, tells the UI whether — at the moment the request
was served — the target is:

- ``up``: above the local horizon (the location's custom horizon
  polyline if defined, otherwise 0° geometric horizon).
- ``rising``: below the horizon right now, but scheduled to rise
  above it before astronomical dawn (or the end of the current
  astro-dark window, whichever lands first).
- ``set``: below the horizon now and won't come above during the
  remaining astro-dark window tonight.

Cheap. One vectorised astropy AltAz pass over a coarse time grid
(15-minute sampling from ``now`` to ``astro_dark_end`` + current
instant, clamped to reasonable bounds) for all DSOs at once.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal

import astropy.units as u
import numpy as np
from astropy.coordinates import AltAz, SkyCoord, get_body
from astropy.time import Time, TimeDelta

from nightcrate.services.horizon import resolve_horizon_altitude
from nightcrate.services.planner_visibility import (
    DsoCoord,
    PlannerHorizon,
    PlannerLocation,
    _make_earth_location,
)

NowStatus = Literal["up", "rising", "set"]

# Coarse sampling for the forward look-ahead. 15 min is plenty — the
# question is just "does the object clear the horizon in the next few
# hours?", not a precision rise-time.
_FORWARD_STEP_MINUTES = 15


def compute_now_status(
    location: PlannerLocation,
    horizon: PlannerHorizon,
    dsos: Sequence[DsoCoord],
    *,
    now_utc: datetime | None = None,
    astro_dark_end_utc: datetime | None = None,
) -> dict[int, NowStatus]:
    """Return per-DSO {id: status}.

    ``now_utc`` defaults to the current wall-clock UTC instant.
    ``astro_dark_end_utc`` is the latest UTC time considered "still
    tonight" for the rising-later check; if ``None``, falls back to
    ``now_utc + 12 h`` so objects that rise within the next half-day
    qualify (handles daytime fetches well).

    Horizon test: altitude is compared against the horizon altitude at
    the object's current azimuth (flat for artificial horizons,
    interpolated polyline for custom ones).
    """
    if not dsos:
        return {}

    if now_utc is None:
        now_utc = datetime.now(UTC)
    if astro_dark_end_utc is None or astro_dark_end_utc <= now_utc:
        from datetime import timedelta

        astro_dark_end_utc = now_utc + timedelta(hours=12)

    earth_loc = _make_earth_location(location)

    # Forward-look time grid: sample at ``now`` + 15-min increments up
    # to astro_dark_end. "Up" is decided by the FIRST sample; the
    # remaining samples inform "rising later". 15-min step keeps the
    # astropy call cheap even over an 8-hour horizon.
    horizon_secs = max(0.0, (astro_dark_end_utc - now_utc).total_seconds())
    n_forward = max(1, int(horizon_secs // (_FORWARD_STEP_MINUTES * 60)) + 1)
    step = TimeDelta(_FORWARD_STEP_MINUTES * 60, format="sec")

    t0 = Time(now_utc)
    times = t0 + step * np.arange(n_forward)
    altaz_frame = AltAz(obstime=times, location=earth_loc)

    # Build SkyCoords for every DSO as a single Column-vector →
    # `transform_to` then produces a (N_dsos, N_times) altitude array.
    ra_arr = np.asarray([d.ra_deg for d in dsos]) * u.deg
    dec_arr = np.asarray([d.dec_deg for d in dsos]) * u.deg
    coords = SkyCoord(ra=ra_arr[:, None], dec=dec_arr[:, None], frame="icrs")
    # Broadcast: shape (N_dsos, 1) coords × shape (N_times,) frame →
    # (N_dsos, N_times) result.
    altaz = coords.transform_to(altaz_frame)
    alt = np.asarray(altaz.alt.deg)  # (N_dsos, N_times)
    az = np.asarray(altaz.az.deg)

    # Horizon altitude at each sample's azimuth, per DSO.
    horizon_alt = resolve_horizon_altitude(
        horizon.type, horizon.flat_altitude_deg, horizon.points, az.ravel()
    ).reshape(az.shape)

    above = alt > horizon_alt  # (N_dsos, N_times) bool
    up_now = above[:, 0]
    rising_later = above[:, 1:].any(axis=1) if n_forward > 1 else np.zeros_like(up_now)

    result: dict[int, NowStatus] = {}
    for i, d in enumerate(dsos):
        if up_now[i]:
            result[d.dso_id] = "up"
        elif rising_later[i]:
            result[d.dso_id] = "rising"
        else:
            result[d.dso_id] = "set"
    return result


# ``get_body`` import silences an unused-import lint when the module is
# swapped around; kept for future moon/sun-aware status extensions.
_ = get_body
