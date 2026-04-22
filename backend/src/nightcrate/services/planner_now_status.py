"""Per-DSO "currently up / rising later / already set" status snapshot.

Run at request time, once per planner-targets fetch. For each DSO
with coordinates, tells the UI whether, with respect to tonight's
astronomical-dark session, the target is:

- ``up``: above the local horizon right now, AND the current instant
  is inside tonight's astro-dark window. Only fires when the user
  would actually be able to observe.
- ``rising``: not currently observable (either below horizon during
  the dark window, or we're still in daytime before tonight starts)
  but will clear the horizon at some point inside tonight's dark
  window.
- ``set``: will not clear the horizon at any point during tonight.

"Tonight" follows the snapshot's dark window (``night_date`` anchored
via ``_tonight_date`` — which rolls back 12 hours so "tonight" means
the upcoming session between local noon and midnight, and the
current session between midnight and noon). Between astronomical
dawn and local noon we're sitting on yesterday's snapshot; in that
window we return no status (empty dict) — the session is over, so
the up / rising / set concept doesn't apply.

Cheap. One vectorised astropy AltAz pass over a 15-minute grid
across the *dark-window* portion of tonight (not ``now`` → dark-end,
which would include daytime samples during an afternoon fetch).
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
# question is just "does the object clear the horizon tonight?",
# not a precision rise-time.
_FORWARD_STEP_MINUTES = 15


def compute_now_status(
    location: PlannerLocation,
    horizon: PlannerHorizon,
    dsos: Sequence[DsoCoord],
    *,
    now_utc: datetime | None = None,
    astro_dark_start_utc: datetime | None = None,
    astro_dark_end_utc: datetime | None = None,
) -> dict[int, NowStatus]:
    """Return per-DSO ``{id: status}`` scoped to tonight's astro-dark.

    ``astro_dark_start_utc`` / ``astro_dark_end_utc`` bound tonight's
    session; both are taken from the planner's visibility snapshot.
    Missing either (polar summer with no astro-dark at all) returns
    an empty dict, same shape as "no status to report".

    Status decision tree:

    - ``now > dark_end`` — tonight's session ended; return empty.
    - ``now < dark_start`` — daytime before tonight. Sample the
      dark-window interval. "Up" never fires (user can't see the
      object during daytime); "rising" if ever above horizon in the
      window, "set" otherwise.
    - ``dark_start ≤ now ≤ dark_end`` — inside astro-dark. Sample
      ``now`` → ``dark_end``. "Up" when above horizon on the first
      sample; "rising" if below now but above later; "set" otherwise.

    Sampling the *dark-window* portion (rather than ``now`` → end)
    is the key fix: an afternoon fetch used to report "set" for
    objects that had already dropped below horizon by midday but
    would re-rise during the upcoming night. Clamping the window
    start to ``dark_start_utc`` during daytime drops those spurious
    samples.
    """
    if not dsos:
        return {}
    if now_utc is None:
        now_utc = datetime.now(UTC)
    if astro_dark_start_utc is None or astro_dark_end_utc is None:
        return {}

    # Post-dawn: tonight's session is over. The snapshot we're looking
    # at is yesterday's; showing up/rising/set against it would be
    # stale. Return empty — the frontend renders no glyph.
    if now_utc > astro_dark_end_utc:
        return {}

    # Daytime before tonight: clamp the sample window to tonight's
    # dark interval and suppress the "up" state entirely. Inside
    # astro-dark: sample from now → dark-end and let "up" fire on
    # the first sample.
    if now_utc < astro_dark_start_utc:
        sample_start = astro_dark_start_utc
        evaluate_up_now = False
    else:
        sample_start = now_utc
        evaluate_up_now = True

    earth_loc = _make_earth_location(location)

    total_sec = max(0.0, (astro_dark_end_utc - sample_start).total_seconds())
    n_forward = max(1, int(total_sec // (_FORWARD_STEP_MINUTES * 60)) + 1)
    step = TimeDelta(_FORWARD_STEP_MINUTES * 60, format="sec")

    t0 = Time(sample_start)
    times = t0 + step * np.arange(n_forward)
    altaz_frame = AltAz(obstime=times, location=earth_loc)

    # Build SkyCoords for every DSO as a single Column-vector →
    # ``transform_to`` then produces a (N_dsos, N_times) altitude array.
    ra_arr = np.asarray([d.ra_deg for d in dsos]) * u.deg
    dec_arr = np.asarray([d.dec_deg for d in dsos]) * u.deg
    coords = SkyCoord(ra=ra_arr[:, None], dec=dec_arr[:, None], frame="icrs")
    altaz = coords.transform_to(altaz_frame)
    alt = np.asarray(altaz.alt.deg)  # (N_dsos, N_times)
    az = np.asarray(altaz.az.deg)

    # Horizon altitude at each sample's azimuth, per DSO.
    horizon_alt = resolve_horizon_altitude(
        horizon.type, horizon.flat_altitude_deg, horizon.points, az.ravel()
    ).reshape(az.shape)

    above = alt > horizon_alt  # (N_dsos, N_times) bool

    if evaluate_up_now:
        up_now = above[:, 0]
        rising_later = above[:, 1:].any(axis=1) if n_forward > 1 else np.zeros_like(up_now)
    else:
        # Daytime — "up" cannot fire. Any above-horizon sample during
        # the dark window makes the target "rising".
        up_now = np.zeros(len(dsos), dtype=bool)
        rising_later = above.any(axis=1)

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
