"""Derive imaging sessions from a project's cataloged light frames (v0.41.1).

A derived session is one row per ``(observing night, rig, filter, exposure, gain,
binning)`` — the grain a user would hand-enter for a night's batch, and the
finest grain ``project_session`` can represent (it carries a single exposure,
gain and sub count per row). The rig comes from the frame, which inherited it
from its source folder's user-declared tag, so it only splits a group when two
rigs really did shoot the same filter on the same night.

**Never runs automatically.** Ingest catalogs frames and stops there; a project
may legitimately hold no subs at all and still keep a full hand-entered session
record. The user asks for a derive from the Sessions tab, and the pass replaces
every ``source='auto'`` row while leaving ``source='manual'`` rows untouched.

Pure service: takes an open connection and **never commits** — the caller owns
the transaction, same contract as ``ingest_sessions``.
"""

from __future__ import annotations

import logging

import aiosqlite

from nightcrate.services.ingest_sessions import observing_night
from nightcrate.services.line_names import canonicalize_line_name, normalize_label
from nightcrate.services.session_derivation_models import DerivationSummary, DerivedSession

logger = logging.getLogger(__name__)

_LOG_PREFIX = "[derive-sessions]"

# Module-level tuple: ruff format strips parens from inline ``except (A, B):`` on
# py3.14, producing invalid Py2 syntax. Referencing a constant sidesteps it.
_COERCE_ERRORS = (TypeError, ValueError)

# Fallback bandpass when a header filter name isn't a recognized line name. The
# real name survives in project_session.filter_label; line_name only has to
# satisfy the table CHECK and give the integration bars a closed vocabulary.
_UNKNOWN_LINE = "other"


def group_key(
    night: str,
    filter_hint: str | None,
    exposure_seconds: float | None,
    gain: float | None,
    binning_x: int | None,
    binning_y: int | None,
    rig_id: int | None = None,
) -> tuple:
    """The hashable grain of one derived session.

    Pure, so the grain is testable without a database. The filter component is the
    **canonical** key — a recognized line name, else the normalized label — so that
    ``"Ha"`` and ``"H-alpha"`` on the same night collapse into one session instead
    of two. Gain is compared coerced (``101`` and ``101.0`` are one group), and
    binning on the ``(x, y)`` pair.

    *rig_id* comes from the frame, which inherited it from its source folder's
    user-declared tag. It only ever splits a group when two rigs really did shoot
    the same filter on the same night — which is two sessions, not one.
    """
    return (
        night,
        rig_id,
        filter_key(filter_hint),
        round(float(exposure_seconds or 0.0), 3),
        coerce_gain(gain),
        (binning_x, binning_y),
    )


def filter_key(filter_hint: str | None) -> str | None:
    """Canonical grouping key for a header filter name (``None`` when absent)."""
    if not filter_hint:
        return None
    return canonicalize_line_name(filter_hint) or normalize_label(filter_hint) or None


def coerce_gain(gain: float | None) -> int | None:
    """``sub_frame.gain`` is REAL, ``project_session.gain`` is INTEGER >= 0."""
    if gain is None:
        return None
    try:
        value = int(round(float(gain)))
    except _COERCE_ERRORS:
        return None
    return value if value >= 0 else None


def coerce_binning(binning_x: int | None, binning_y: int | None) -> int | None:
    """``project_session.binning`` is a single INTEGER; asymmetric binning has no
    representation there, so it stores NULL rather than a misleading half-truth."""
    if binning_x is None or binning_x != binning_y or binning_x < 1:
        return None
    return binning_x


async def derive_sessions(
    conn: aiosqlite.Connection, project_id: int, *, tz_name: str | None
) -> DerivationSummary:
    """Rebuild the project's ``source='auto'`` sessions from its cataloged lights.

    Caller owns the transaction.
    """
    summary = DerivationSummary(project_id=project_id)

    # Fallback rig for frames from an untagged folder: the project's rig, when it
    # has exactly one. With several, "which rig" is a question only the user can
    # answer — tag the source folders.
    default_rig_id = await _project_single_rig(conn, project_id)
    cursor = await conn.execute(
        "SELECT date_obs_utc, filter_name_hint, exposure_seconds, gain, binning_x, binning_y, "
        "rig_id FROM sub_frame WHERE project_id = ? AND frame_type = 'light'",
        (project_id,),
    )
    rows = await cursor.fetchall()
    summary.lights_considered = len(rows)

    groups: dict[tuple, DerivedSession] = {}
    for row in rows:
        exposure = round(float(row["exposure_seconds"] or 0.0), 3)
        # project_session.exposure_seconds is CHECK (> 0) while sub_frame allows
        # >= 0 (bias frames). A light with a missing EXPTIME would abort the whole
        # INSERT, so drop it here and report the count rather than fail loudly.
        if exposure <= 0:
            summary.lights_skipped += 1
            continue
        night = observing_night(row["date_obs_utc"], tz_name)
        rig_id = row["rig_id"] if row["rig_id"] is not None else default_rig_id
        key = group_key(
            night,
            row["filter_name_hint"],
            exposure,
            row["gain"],
            row["binning_x"],
            row["binning_y"],
            rig_id,
        )
        existing = groups.get(key)
        if existing is not None:
            existing.num_subs += 1
            continue
        hint = row["filter_name_hint"]
        groups[key] = DerivedSession(
            night=night,
            rig_id=rig_id,
            line_name=(canonicalize_line_name(hint) if hint else None) or _UNKNOWN_LINE,
            filter_label=hint,
            exposure_seconds=exposure,
            gain=coerce_gain(row["gain"]),
            binning=coerce_binning(row["binning_x"], row["binning_y"]),
            num_subs=1,
        )

    cursor = await conn.execute(
        "DELETE FROM project_session WHERE project_id = ? AND source = 'auto'",
        (project_id,),
    )
    summary.sessions_replaced = cursor.rowcount if cursor.rowcount > 0 else 0

    # Sorted so re-deriving an unchanged catalog produces the same row order,
    # which keeps the Sessions tab stable and makes the tests comparable.
    for key in sorted(groups, key=_sort_key):
        session = groups[key]
        await conn.execute(
            "INSERT INTO project_session (project_id, rig_id, line_name, filter_label, "
            "exposure_seconds, gain, num_subs, binning, session_date, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'auto')",
            (
                project_id,
                session.rig_id,
                session.line_name,
                session.filter_label,
                session.exposure_seconds,
                session.gain,
                session.num_subs,
                session.binning,
                session.night,
            ),
        )
    summary.sessions_created = len(groups)

    cursor = await conn.execute(
        "SELECT COUNT(*) AS n FROM project_session WHERE project_id = ? AND source = 'manual'",
        (project_id,),
    )
    summary.manual_sessions_kept = (await cursor.fetchone())["n"]

    logger.info(
        "%s project %d: %d lights -> %d sessions (replaced %d, skipped %d, %d manual kept)",
        _LOG_PREFIX,
        project_id,
        summary.lights_considered,
        summary.sessions_created,
        summary.sessions_replaced,
        summary.lights_skipped,
        summary.manual_sessions_kept,
    )
    return summary


async def _project_single_rig(conn: aiosqlite.Connection, project_id: int) -> int | None:
    """The project's rig when it has exactly one — the only case where attributing
    a rig to a derived session is a fact rather than a guess."""
    cursor = await conn.execute(
        "SELECT rig_id FROM project_rig WHERE project_id = ? LIMIT 2", (project_id,)
    )
    rows = await cursor.fetchall()
    return rows[0]["rig_id"] if len(rows) == 1 else None


def _sort_key(key: tuple) -> tuple:
    """Total order over group keys, tolerating the NULLs any component may hold."""
    night, rig_id, filt, exposure, gain, binning = key
    return (
        night,
        -1 if rig_id is None else rig_id,
        filt or "",
        exposure,
        -1 if gain is None else gain,
        (-1 if binning[0] is None else binning[0], -1 if binning[1] is None else binning[1]),
    )
