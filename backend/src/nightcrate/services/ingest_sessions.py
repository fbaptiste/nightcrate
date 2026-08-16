"""Session-formation helpers for the ingest pipeline (v0.40.0).

A session is a contiguous night of imaging on one rig. Subs are grouped by
``(rig_id, observing_night)`` where the observing night is the noon-to-noon civil
date in the site timezone — so an exposure at 02:00 belongs to the night that
started the previous evening. Simultaneous dual-rig imaging yields two distinct
sessions (never conflated): a NULL rig_id is its own bucket, kept separate from
any resolved rig.

The key/date helpers are pure; ``ensure_session`` takes an open connection
(caller owns the transaction — same contract as ``equipment_resolver``) so both
``api/ingest.py`` and the v0.41.0 rig-attribution pass can form sessions without
a service→api import.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiosqlite

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


def observing_window_utc(night: str, tz_name: str | None) -> tuple[str, str]:
    """UTC bounds of the noon-to-noon observing night *night* (local date in the
    site's geo timezone). A literal noon-UTC stamp would be wrong for any non-UTC
    site (e.g. UTC-7 → real window start is 19:00 UTC); v0.43's PHD2 time-range
    association needs the true UTC window."""
    tz = _zone(tz_name) or UTC
    d = date.fromisoformat(night)
    start = datetime(d.year, d.month, d.day, 12, 0, tzinfo=tz)
    nxt = d + timedelta(days=1)
    end = datetime(nxt.year, nxt.month, nxt.day, 12, 0, tzinfo=tz)
    return start.astimezone(UTC).isoformat(), end.astimezone(UTC).isoformat()


async def ensure_session(
    conn: aiosqlite.Connection, project_id: int, key: tuple, tz_name: str | None
) -> int:
    """Find-or-create the ``session`` row for a ``session_key`` grouping key.

    Identity is (project, observing-night start, rig); start_utc is deterministic
    per (night, geo-tz) so re-ingest dedupes to the same row. Caller owns the
    transaction.
    """
    rig_id, night = key
    start_utc, end_utc = observing_window_utc(night, tz_name)
    cursor = await conn.execute(
        "SELECT id FROM session WHERE project_id = ? AND start_utc = ? AND rig_id IS ?",
        (project_id, start_utc, rig_id),
    )
    row = await cursor.fetchone()
    if row is not None:
        return row["id"]
    cursor = await conn.execute(
        "INSERT INTO session (project_id, rig_id, start_utc, end_utc) VALUES (?, ?, ?, ?)",
        (project_id, rig_id, start_utc, end_utc),
    )
    return cursor.lastrowid


async def sweep_empty_sessions(conn: aiosqlite.Connection, project_id: int) -> None:
    """Delete auto-sessions left with no sub frames.

    Called after anything that re-keys or removes frames (re-scan, folder
    removal, attribution re-key, manual rig override). The manual
    ``project_session`` table is a different thing and is never touched.
    Caller owns the transaction.
    """
    await conn.execute(
        "DELETE FROM session WHERE project_id = ? AND NOT EXISTS "
        "(SELECT 1 FROM sub_frame sf WHERE sf.session_id = session.id)",
        (project_id,),
    )


def _parse_iso(value: str) -> datetime:
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
