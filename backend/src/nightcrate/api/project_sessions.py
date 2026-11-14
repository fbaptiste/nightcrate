"""Project imaging-session + integration endpoints (v0.38.0, reshaped v0.41.1).

A session is a capture batch: N identical light subs of one filter. There are two
ways to get one:

* **Manual** (``source='manual'``) — the user enters it. This is the only path for
  a project whose subs aren't cataloged (or aren't available at all).
* **Derived** (``source='auto'``) — ``POST /sessions/derive`` rebuilds one row per
  (observing night, rig, filter, exposure, gain, binning) from the project's
  cataloged light frames. The rig is what splits a simultaneous dual-rig night
  into two sessions rather than colliding them into one. Explicit and
  user-initiated; ingest never does this on its own. Derived rows are read-only,
  because the next derive replaces them.

Per-filter integration is computed here from the sessions (exposure x sub count),
along with a sub count per filter and exposure (v0.41.8). Per-filter goals were
removed in v0.41.1 — this is a read-out, not a tracker.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from fastapi import APIRouter, HTTPException

from nightcrate.api._common import get_or_404, row_to_dict
from nightcrate.api.project_session_models import (
    LINE_NAMES,
    ExposureLine,
    IntegrationLine,
    IntegrationSummary,
    SessionCreate,
    SessionResponse,
    SessionSetupUpdate,
    SessionUpdate,
)
from nightcrate.db.session import get_db
from nightcrate.services.gallery import imaging_runs, valid_session_date
from nightcrate.services.ingest_sessions import project_geo_timezone
from nightcrate.services.rig_setups import set_batch_setup
from nightcrate.services.session_derivation import derive_sessions
from nightcrate.services.session_derivation_models import DerivationSummary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["Projects"])

# Columns the client may update on a session (filter-or-line invariant and the
# NOT NULL capture settings are validated before this list is applied).
_SESSION_COLUMNS = (
    "rig_id",
    "rig_setup_id",
    "filter_id",
    "line_name",
    "exposure_seconds",
    "gain",
    "num_subs",
    "binning",
    "session_date",
    "notes",
)

_SESSION_SELECT = (
    "SELECT ps.*, r.name AS rig_name, f.model_name AS filter_name,"
    " rs.until_at AS setup_until_at"
    " FROM project_session ps"
    " LEFT JOIN rig r ON r.id = ps.rig_id"
    " LEFT JOIN filter f ON f.id = ps.filter_id"
    " LEFT JOIN rig_setup rs ON rs.id = ps.rig_setup_id"
)

_DERIVED_IS_READ_ONLY = (
    "Derived sessions are rebuilt from this project's cataloged sub frames. "
    "Correct the frames on the Catalog tab and re-derive, or add a manual session."
)


def _session_response(d: dict) -> SessionResponse:
    d["integration_minutes"] = d["exposure_seconds"] * d["num_subs"] / 60.0
    return SessionResponse(**d)


async def _fetch_session(conn, project_id: int, session_id: int) -> SessionResponse:
    cursor = await conn.execute(
        f"{_SESSION_SELECT} WHERE ps.id = ? AND ps.project_id = ?",  # nosec B608 - constant SELECT
        (session_id, project_id),
    )
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return _session_response(row_to_dict(row))


async def _validate_fks(conn, *, rig_id: int | None, filter_id: int | None) -> None:
    if rig_id is not None:
        await get_or_404(conn, "rig", rig_id, "Rig")
    if filter_id is not None:
        await get_or_404(conn, "filter", filter_id, "Filter")


async def _validate_setup(conn, rig_id: int | None, rig_setup_id: int | None) -> None:
    if rig_setup_id is None:
        return
    cursor = await conn.execute("SELECT rig_id FROM rig_setup WHERE id = ?", (rig_setup_id,))
    setup = await cursor.fetchone()
    if setup is None or setup["rig_id"] != rig_id:
        raise HTTPException(status_code=422, detail="The setup must belong to the session's rig")


async def _get_editable(conn, project_id: int, session_id: int) -> dict:
    """Fetch a session for mutation, 404 if it isn't the project's and 409 if it
    is derived — editing a row the next derive will replace is a lie."""
    cursor = await conn.execute(
        "SELECT * FROM project_session WHERE id = ? AND project_id = ?",
        (session_id, project_id),
    )
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    existing = row_to_dict(row)
    if existing["source"] == "auto":
        raise HTTPException(status_code=409, detail=_DERIVED_IS_READ_ONLY)
    return existing


# ── Sessions CRUD ────────────────────────────────────────────────────────────


@router.get("/{project_id}/sessions")
async def list_sessions(project_id: int) -> list[SessionResponse]:
    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")
        cursor = await conn.execute(
            f"{_SESSION_SELECT} WHERE ps.project_id = ?"  # nosec B608 - constant SELECT
            " ORDER BY ps.session_date IS NULL, ps.session_date DESC, ps.id DESC",
            (project_id,),
        )
        rows = await cursor.fetchall()
    return [_session_response(row_to_dict(r)) for r in rows]


@router.post("/{project_id}/sessions", status_code=201)
async def create_session(project_id: int, body: SessionCreate) -> SessionResponse:
    async with get_db() as conn:
        await conn.execute("BEGIN IMMEDIATE")
        try:
            await get_or_404(conn, "project", project_id, "Project")
            await _validate_fks(conn, rig_id=body.rig_id, filter_id=body.filter_id)
            await _validate_setup(conn, body.rig_id, body.rig_setup_id)
            cursor = await conn.execute(
                """INSERT INTO project_session
                   (project_id, rig_id, rig_setup_id, filter_id, line_name, exposure_seconds,
                    gain, num_subs, binning, session_date, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    project_id,
                    body.rig_id,
                    body.rig_setup_id,
                    body.filter_id,
                    body.line_name,
                    body.exposure_seconds,
                    body.gain,
                    body.num_subs,
                    body.binning,
                    body.session_date,
                    body.notes,
                ),
            )
            session_id = cursor.lastrowid
            response = await _fetch_session(conn, project_id, session_id)
            await conn.commit()
            return response
        except BaseException:
            await conn.rollback()
            raise


@router.post("/{project_id}/sessions/derive")
async def derive_project_sessions(project_id: int) -> DerivationSummary:
    """Rebuild the project's derived sessions from its cataloged light frames.

    Replaces every ``source='auto'`` row; ``source='manual'`` rows are untouched.
    Never runs on its own — ingest catalogs frames and stops there.
    """
    async with get_db() as conn:
        await conn.execute("PRAGMA foreign_keys = ON")
        await get_or_404(conn, "project", project_id, "Project")
        tz_name = await project_geo_timezone(conn, project_id)
        summary = await derive_sessions(conn, project_id, tz_name=tz_name)
        await conn.commit()
        return summary


@router.patch("/{project_id}/sessions/{session_id}")
async def update_session(project_id: int, session_id: int, body: SessionUpdate) -> SessionResponse:
    fields = body.model_dump(exclude_unset=True)

    async with get_db() as conn:
        await conn.execute("BEGIN IMMEDIATE")
        try:
            await get_or_404(conn, "project", project_id, "Project")
            existing = await _get_editable(conn, project_id, session_id)

            for required in ("exposure_seconds", "num_subs"):
                if required in fields and fields[required] is None:
                    raise HTTPException(status_code=422, detail=f"{required} cannot be null")
            if (
                "line_name" in fields
                and fields["line_name"] is not None
                and fields["line_name"] not in LINE_NAMES
            ):
                raise HTTPException(
                    status_code=422, detail=f"Invalid line_name: {fields['line_name']}"
                )
            await _validate_fks(
                conn, rig_id=fields.get("rig_id"), filter_id=fields.get("filter_id")
            )

            merged_filter = fields["filter_id"] if "filter_id" in fields else existing["filter_id"]
            merged_line = fields["line_name"] if "line_name" in fields else existing["line_name"]
            if merged_filter is None and merged_line is None:
                raise HTTPException(
                    status_code=422,
                    detail="A specific filter or a bandpass line_name is required",
                )
            merged_rig = fields["rig_id"] if "rig_id" in fields else existing["rig_id"]
            merged_setup = (
                fields["rig_setup_id"] if "rig_setup_id" in fields else existing["rig_setup_id"]
            )
            if "rig_id" in fields and "rig_setup_id" not in fields and merged_setup is not None:
                cursor = await conn.execute(
                    "SELECT 1 FROM rig_setup WHERE id = ? AND rig_id = ?",
                    (merged_setup, merged_rig),
                )
                if await cursor.fetchone() is None:
                    fields["rig_setup_id"] = None
                    merged_setup = None
            await _validate_setup(conn, merged_rig, merged_setup)

            sets = [f"{col} = ?" for col in _SESSION_COLUMNS if col in fields]
            params = [fields[col] for col in _SESSION_COLUMNS if col in fields]
            if sets:
                params.append(session_id)
                await conn.execute(
                    f"UPDATE project_session SET {', '.join(sets)} WHERE id = ?",  # nosec B608
                    params,
                )
            response = await _fetch_session(conn, project_id, session_id)
            await conn.commit()
            return response
        except BaseException:
            await conn.rollback()
            raise


@router.put("/{project_id}/sessions/{session_id}/setup")
async def update_session_setup(
    project_id: int, session_id: int, body: SessionSetupUpdate
) -> SessionResponse:
    async with get_db() as conn:
        await conn.execute("BEGIN IMMEDIATE")
        try:
            await set_batch_setup(conn, project_id, session_id, body.rig_setup_id)
            response = await _fetch_session(conn, project_id, session_id)
            await conn.commit()
            return response
        except LookupError as exc:
            await conn.rollback()
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            await conn.rollback()
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except HTTPException:
            await conn.rollback()
            raise
        except Exception as exc:
            await conn.rollback()
            logger.exception(
                "[rig-setups] failed to move project %d session %d", project_id, session_id
            )
            raise HTTPException(status_code=500, detail="Failed to change session setup") from exc
        except BaseException:
            await conn.rollback()
            raise


@router.delete("/{project_id}/sessions/{session_id}", status_code=204)
async def delete_session(project_id: int, session_id: int) -> None:
    async with get_db() as conn:
        await _get_editable(conn, project_id, session_id)
        await conn.execute("DELETE FROM project_session WHERE id = ?", (session_id,))
        await conn.commit()


# ── Integration summary ──────────────────────────────────────────────────────


NOT_RECORDED_LABEL = "Not recorded"


def _integration_label(session: dict) -> str:
    """The bar this session's time counts toward.

    A derived session whose header filter name isn't a recognized bandpass carries
    ``line_name = 'other'`` (purely to satisfy the table CHECK) plus the real name
    in ``filter_label``. Grouping every such filter under one "other" bar would be
    useless, so the label wins in exactly that case.
    """
    if session["line_name"] == "other" and session.get("filter_label"):
        return session["filter_label"]
    return session["line_name"]


def _label_order(label: str, not_recorded: bool = False) -> tuple[int, str]:
    """Canonical bandpasses in vocabulary order, then raw filter names A-Z."""
    if not_recorded:
        return (len(LINE_NAMES) + 1, "")
    try:
        return (LINE_NAMES.index(label), "")
    except ValueError:
        return (len(LINE_NAMES), label.lower())


async def _compute_integration(conn, project_id: int) -> IntegrationSummary:
    cursor = await conn.execute(
        "SELECT ps.id, ps.filter_id, ps.line_name, ps.filter_label, ps.exposure_seconds,"
        " ps.num_subs, ps.session_date, ps.source, f.model_name AS filter_name"
        " FROM project_session ps LEFT JOIN filter f ON f.id = ps.filter_id"
        " WHERE ps.project_id = ?",
        (project_id,),
    )
    sessions = [row_to_dict(r) for r in await cursor.fetchall()]

    # Map each specific-filter session to its bandpass line(s). A duo-band
    # filter (Ha+Oiii) maps to BOTH — sub time counts toward each line budget,
    # which is correct for "how much Ha do I have?" (spec §12, documented).
    # Only a manually-entered session can carry a filter_id; a derived one has
    # no equipment identification, so its passbands are genuinely unknown.
    filter_ids = {s["filter_id"] for s in sessions if s["filter_id"] is not None}
    passband_lines: dict[int, list[str]] = defaultdict(list)
    if filter_ids:
        placeholders = ",".join("?" * len(filter_ids))
        cursor = await conn.execute(
            f"SELECT filter_id, line_name FROM filter_passband"  # nosec B608 - placeholders only
            f" WHERE filter_id IN ({placeholders}) AND active = 1",
            tuple(filter_ids),
        )
        for r in await cursor.fetchall():
            passband_lines[r["filter_id"]].append(r["line_name"])

    actual_sec: dict[tuple[str, bool], float] = defaultdict(float)
    nights: dict[tuple[str, bool], set[str]] = defaultdict(set)
    sub_count: dict[tuple[str, bool], int] = defaultdict(int)
    # The exposure breakdown, keyed (filter as shot, exposure). Rounded as the
    # derive groups it, so float noise can't split one sub length into two rows.
    exposure_sec: dict[tuple[str, bool, float], float] = defaultdict(float)
    exposure_subs: dict[tuple[str, bool, float], int] = defaultdict(int)
    exposure_filter_ids: dict[tuple[str, bool, float], set[int | None]] = defaultdict(set)
    total_sec = 0.0
    dates = []

    for s in sessions:
        secs = s["exposure_seconds"] * s["num_subs"]
        total_sec += secs  # wall-clock total counts each session once
        session_date = valid_session_date(s["session_date"])
        if session_date is not None:
            dates.append(session_date)
        not_recorded = (
            s["source"] == "auto"
            and s["line_name"] == "other"
            and not s.get("filter_label")
            and s["filter_id"] is None
        )
        if not_recorded:
            labels = [NOT_RECORDED_LABEL]
            shot_with = NOT_RECORDED_LABEL
        elif s["filter_id"] is not None:
            labels = passband_lines.get(s["filter_id"], [])
            shot_with = s["filter_name"]
        elif s["line_name"] is not None:
            labels = [_integration_label(s)]
            shot_with = labels[0]
        else:
            labels = []
            shot_with = None
        if shot_with is not None:
            key = (shot_with, not_recorded, round(s["exposure_seconds"], 3))
            exposure_sec[key] += secs
            exposure_subs[key] += s["num_subs"]
            exposure_filter_ids[key].add(s["filter_id"])
        # Derived rows split one night into several rows (per exposure/gain), so
        # counting rows would overstate nights — count the distinct dates, with
        # each undated row standing alone.
        night = session_date.isoformat() if session_date is not None else f"row:{s['id']}"
        for label in labels:
            key = (label, not_recorded)
            actual_sec[key] += secs
            nights[key].add(night)
            sub_count[key] += s["num_subs"]

    # Minutes stay unrounded: display rounding is the UI's, and rounding here
    # reported a single 0.1 s sub as no time at all.
    lines = [
        IntegrationLine(
            label=label,
            actual_minutes=actual_sec[(label, not_recorded)] / 60.0,
            session_count=len(nights[(label, not_recorded)]),
            sub_count=sub_count[(label, not_recorded)],
            not_recorded=not_recorded,
        )
        for label, not_recorded in sorted(actual_sec, key=lambda key: _label_order(key[0], key[1]))
    ]
    exposures = [
        ExposureLine(
            label=label,
            exposure_seconds=exposure,
            sub_count=exposure_subs[(label, not_recorded, exposure)],
            actual_minutes=exposure_sec[(label, not_recorded, exposure)] / 60.0,
            not_recorded=not_recorded,
            filter_id=(
                next(iter(exposure_filter_ids[(label, not_recorded, exposure)]))
                if len(exposure_filter_ids[(label, not_recorded, exposure)]) == 1
                and None not in exposure_filter_ids[(label, not_recorded, exposure)]
                else None
            ),
        )
        for label, not_recorded, exposure in sorted(
            exposure_sec,
            key=lambda key: (_label_order(key[0], key[1]), key[2]),
        )
    ]

    return IntegrationSummary(
        lines=lines,
        exposures=exposures,
        total_actual_minutes=total_sec / 60.0,
        first_session_date=min(dates).isoformat() if dates else None,
        last_session_date=max(dates).isoformat() if dates else None,
        imaging_runs=imaging_runs(dates),
        night_count=len(set(dates)),
    )


@router.get("/{project_id}/integration")
async def get_integration(project_id: int) -> IntegrationSummary:
    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")
        return await _compute_integration(conn, project_id)
