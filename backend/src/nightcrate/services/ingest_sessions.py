"""Pure session-formation helpers for the ingest pipeline (v0.40.0).

A session is a contiguous night of imaging on one rig. Subs are grouped by
``(rig_id, observing_night)`` where the observing night is the noon-to-noon civil
date in the site timezone — so an exposure at 02:00 belongs to the night that
started the previous evening. Simultaneous dual-rig imaging yields two distinct
sessions (never conflated): a NULL rig_id is its own bucket, kept separate from
any resolved rig.

No DB or I/O here — the ingest API turns these keys into ``session`` rows.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Module-level tuple: ruff format strips parens from inline ``except (A, B):`` on
# py3.14, producing invalid Py2 syntax. Referencing a constant sidesteps it.
_BAD_ZONE = (ZoneInfoNotFoundError, ValueError)


def observing_night(date_obs_utc: str, tz_name: str | None) -> str:
    """Return the noon-to-noon observing-night civil date (``YYYY-MM-DD``).

    *date_obs_utc* is an ISO 8601 timestamp. It is interpreted in *tz_name* (the
    site geo timezone) when given and valid, else in UTC. Shifting back 12 hours
    before taking the date groups a whole night (evening through pre-dawn) under
    the date the evening began.
    """
    dt = _parse_iso(date_obs_utc)
    tz = _zone(tz_name)
    if tz is not None:
        dt = dt.astimezone(tz)
    return (dt - timedelta(hours=12)).date().isoformat()


def session_key(rig_id: int | None, date_obs_utc: str, tz_name: str | None) -> tuple:
    """A hashable grouping key: ``(rig_id, observing_night)``.

    rig_id is kept distinct from None so dual-rig nights never merge.
    """
    return (rig_id, observing_night(date_obs_utc, tz_name))


def _parse_iso(value: str) -> datetime:
    from datetime import UTC

    text = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _zone(tz_name: str | None) -> ZoneInfo | None:
    if not tz_name:
        return None
    try:
        return ZoneInfo(tz_name)
    except _BAD_ZONE:
        return None
