"""Session-formation helpers for the ingest pipeline (v0.40.0, v0.41.1).

A session is one night of imaging on a project, per rig. Subs are grouped by
observing night — the noon-to-noon civil date in the site timezone — so an
exposure at 02:00 belongs to the night that started the previous evening.

The rig comes from ``project_source_folder.rig_id``, which the **user declares**
per bound folder; nothing infers it from a header. A NULL rig is its own bucket,
so simultaneous dual-rig imaging yields two sessions and is never conflated.

The date helpers are pure; ``ensure_session`` and ``project_geo_timezone`` take an
open connection and never commit (caller owns the transaction), so the ingest
boundary and the session-derivation service can share them without a
service→api import.
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiosqlite

# Module-level tuple: ruff format strips parens from inline ``except (A, B):`` on
# py3.14, producing invalid Py2 syntax. Referencing a constant sidesteps it.
_BAD_ZONE = (ZoneInfoNotFoundError, ValueError)


def folder_prefix(path: str) -> str:
    """A source folder's path with a trailing OS separator, for prefix matching.

    Built here rather than in SQL because paths are stored with the OS-native
    separator — a hardcoded ``'/'`` silently matches nothing on Windows.
    """
    return os.path.join(str(Path(path)), "")


def row_dict(row) -> dict:
    return {k: row[k] for k in row.keys()}


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
    conn: aiosqlite.Connection,
    project_id: int,
    night: str,
    tz_name: str | None,
    *,
    rig_id: int | None = None,
) -> int:
    """Find-or-create the ``session`` row for an observing *night* on *rig_id*.

    Identity is (project, observing-night start, rig); start_utc is deterministic
    per (night, geo-tz) so re-ingest dedupes to the same row. ``rig_id IS ?``
    rather than ``=`` so a NULL rig matches its own bucket instead of nothing.
    ``ORDER BY id LIMIT 1`` because DBs written before v0.41.1 can hold more than
    one row per (project, night, rig) — the extras empty out and are removed by
    :func:`sweep_empty_sessions`. Caller owns the transaction.
    """
    start_utc, end_utc = observing_window_utc(night, tz_name)
    cursor = await conn.execute(
        "SELECT id FROM session WHERE project_id = ? AND start_utc = ? AND rig_id IS ? "
        "ORDER BY id LIMIT 1",
        (project_id, start_utc, rig_id),
    )
    row = await cursor.fetchone()
    if row is not None:
        return row["id"]
    cursor = await conn.execute(
        "INSERT INTO session (project_id, start_utc, end_utc, rig_id) VALUES (?, ?, ?, ?)",
        (project_id, start_utc, end_utc, rig_id),
    )
    return cursor.lastrowid


async def assign_rigs_and_sessions(
    conn: aiosqlite.Connection, project_id: int, tz_name: str | None
) -> None:
    """Give every cataloged frame its rig and its session. **Single owner of both
    facts** — ingest, folder tagging and folder removal all call this rather than
    each writing their own answer.

    The rig is the one tagged on the *innermost* bound source folder containing the
    frame's file. Longest-prefix wins, which is the only rule that behaves when
    folders nest: binding ``/data`` to rig A and ``/data/rig-b`` to rig B must give
    the nested files rig B regardless of which folder was added, scanned or tagged
    last. Frames under no bound folder get NULL, which is a valid answer.

    Caller owns the transaction.
    """
    # Clear, then apply each folder shortest-path-first so the innermost binding
    # lands last and wins. One statement per bound folder (a handful), not per
    # frame.
    #
    # The prefix is built in PYTHON, not SQL: paths are stored with the OS-native
    # separator, so an `rtrim(path, '/') || '/'` comparison would never match on
    # Windows and rig tagging would silently do nothing there. os.path.join(p, "")
    # appends the right separator on every platform. Comparing a fixed-length
    # substring also keeps `_` and `%` in real paths from acting as LIKE wildcards
    # — the same reason api/ingest.py:remove_folder avoids LIKE.
    await conn.execute("UPDATE sub_frame SET rig_id = NULL WHERE project_id = ?", (project_id,))
    cursor = await conn.execute(
        "SELECT path, rig_id FROM project_source_folder WHERE project_id = ?", (project_id,)
    )
    folders = [row_dict(r) for r in await cursor.fetchall()]
    for folder in sorted(folders, key=lambda f: len(f["path"])):
        if folder["rig_id"] is None:
            continue
        prefix = folder_prefix(folder["path"])
        await conn.execute(
            "UPDATE sub_frame SET rig_id = ? WHERE project_id = ? AND id IN ("
            "  SELECT fl.sub_frame_id FROM file_location fl"
            "  WHERE fl.project_id = ? AND fl.sub_frame_id IS NOT NULL"
            "    AND substr(fl.path, 1, ?) = ?)",
            (folder["rig_id"], project_id, project_id, len(prefix), prefix),
        )

    # Re-key sessions. The distinct (rig, night) set is tens of entries even for a
    # multi-year project, so group first and issue one ensure_session per group —
    # a per-frame loop here cost ~100x more on a 2400-frame project.
    cursor = await conn.execute(
        "SELECT id, date_obs_utc, rig_id FROM sub_frame WHERE project_id = ?", (project_id,)
    )
    groups: dict[tuple, list[int]] = {}
    for row in await cursor.fetchall():
        key = (row["rig_id"], observing_night(row["date_obs_utc"], tz_name))
        groups.setdefault(key, []).append(row["id"])

    for (rig_id, night), frame_ids in groups.items():
        session_id = await ensure_session(conn, project_id, night, tz_name, rig_id=rig_id)
        await conn.executemany(
            "UPDATE sub_frame SET session_id = ? WHERE id = ?",
            [(session_id, fid) for fid in frame_ids],
        )

    await sweep_empty_sessions(conn, project_id)


async def sweep_empty_sessions(conn: aiosqlite.Connection, project_id: int) -> None:
    """Delete sessions left with no sub frames.

    Called after anything that removes frames (re-scan, folder removal). This is
    the internal (project, night) grouping that ``sub_frame.session_id`` points
    at — the user-facing ``project_session`` table is a different thing and is
    never touched here. Caller owns the transaction.
    """
    await conn.execute(
        "DELETE FROM session WHERE project_id = ? AND NOT EXISTS "
        "(SELECT 1 FROM sub_frame sf WHERE sf.session_id = session.id)",
        (project_id,),
    )


async def project_geo_timezone(conn: aiosqlite.Connection, project_id: int) -> str | None:
    """The IANA zone that defines this project's observing nights.

    Prefers the site's ``geo_timezone`` (derived from its coordinates) over the
    user's display ``timezone`` — a remote-observatory operator legitimately views
    times in their home zone while nights are bounded by the site's local noon.
    Returns ``None`` when the project has no location, which the night helpers
    read as UTC.
    """
    cursor = await conn.execute(
        "SELECT l.geo_timezone, l.timezone FROM project p "
        "LEFT JOIN location l ON l.id = p.location_id WHERE p.id = ?",
        (project_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return row["geo_timezone"] or row["timezone"]


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
