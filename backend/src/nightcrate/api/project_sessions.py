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
    SessionUpdate,
)
from nightcrate.db.session import get_db
from nightcrate.services.ingest_sessions import project_geo_timezone
from nightcrate.services.session_derivation import derive_sessions
from nightcrate.services.session_derivation_models import DerivationSummary

router = APIRouter(prefix="/api/projects", tags=["Projects"])

# Columns the client may update on a session (filter-or-line invariant and the
# NOT NULL capture settings are validated before this list is applied).
_SESSION_COLUMNS = (
    "rig_id",
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
    "SELECT ps.*, r.name AS rig_name, f.model_name AS filter_name"
    " FROM project_session ps"
    " LEFT JOIN rig r ON r.id = ps.rig_id"
    " LEFT JOIN filter f ON f.id = ps.filter_id"
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
        await get_or_404(conn, "project", project_id, "Project")
        await _validate_fks(conn, rig_id=body.rig_id, filter_id=body.filter_id)
        cursor = await conn.execute(
            """INSERT INTO project_session
               (project_id, rig_id, filter_id, line_name, exposure_seconds,
                gain, num_subs, binning, session_date, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                project_id,
                body.rig_id,
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
        await conn.commit()
        return await _fetch_session(conn, project_id, session_id)


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
            raise HTTPException(status_code=422, detail=f"Invalid line_name: {fields['line_name']}")
        await _validate_fks(conn, rig_id=fields.get("rig_id"), filter_id=fields.get("filter_id"))

        merged_filter = fields["filter_id"] if "filter_id" in fields else existing["filter_id"]
        merged_line = fields["line_name"] if "line_name" in fields else existing["line_name"]
        if merged_filter is None and merged_line is None:
            raise HTTPException(
                status_code=422,
                detail="A specific filter or a bandpass line_name is required",
            )

        sets = [f"{col} = ?" for col in _SESSION_COLUMNS if col in fields]
        params = [fields[col] for col in _SESSION_COLUMNS if col in fields]
        if sets:
            params.append(session_id)
            await conn.execute(
                f"UPDATE project_session SET {', '.join(sets)} WHERE id = ?",  # nosec B608 - column names internal
                params,
            )
            await conn.commit()
        return await _fetch_session(conn, project_id, session_id)


@router.delete("/{project_id}/sessions/{session_id}", status_code=204)
async def delete_session(project_id: int, session_id: int) -> None:
    async with get_db() as conn:
        await _get_editable(conn, project_id, session_id)
        await conn.execute("DELETE FROM project_session WHERE id = ?", (session_id,))
        await conn.commit()


# ── Integration summary ──────────────────────────────────────────────────────


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


def _label_order(label: str) -> tuple[int, str]:
    """Canonical bandpasses in vocabulary order, then raw filter names A-Z."""
    try:
        return (LINE_NAMES.index(label), "")
    except ValueError:
        return (len(LINE_NAMES), label.lower())


async def _compute_integration(conn, project_id: int) -> IntegrationSummary:
    cursor = await conn.execute(
        "SELECT ps.id, ps.filter_id, ps.line_name, ps.filter_label, ps.exposure_seconds,"
        " ps.num_subs, ps.session_date, f.model_name AS filter_name"
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

    actual_sec: dict[str, float] = defaultdict(float)
    nights: dict[str, set[str]] = defaultdict(set)
    sub_count: dict[str, int] = defaultdict(int)
    # The exposure breakdown, keyed (filter as shot, exposure). Rounded as the
    # derive groups it, so float noise can't split one sub length into two rows.
    exposure_sec: dict[tuple[str, float], float] = defaultdict(float)
    exposure_subs: dict[tuple[str, float], int] = defaultdict(int)
    total_sec = 0.0
    dates: list[str] = []

    for s in sessions:
        secs = s["exposure_seconds"] * s["num_subs"]
        total_sec += secs  # wall-clock total counts each session once
        if s["session_date"]:
            dates.append(s["session_date"][:10])
        if s["filter_id"] is not None:
            labels = passband_lines.get(s["filter_id"], [])
            shot_with = s["filter_name"]
        elif s["line_name"] is not None:
            labels = [_integration_label(s)]
            shot_with = labels[0]
        else:
            labels = []
            shot_with = None
        if shot_with is not None:
            key = (shot_with, round(s["exposure_seconds"], 3))
            exposure_sec[key] += secs
            exposure_subs[key] += s["num_subs"]
        # Derived rows split one night into several rows (per exposure/gain), so
        # counting rows would overstate nights — count the distinct dates, with
        # each undated row standing alone.
        night = s["session_date"][:10] if s["session_date"] else f"row:{s['id']}"
        for label in labels:
            actual_sec[label] += secs
            nights[label].add(night)
            sub_count[label] += s["num_subs"]

    # Minutes stay unrounded: display rounding is the UI's, and rounding here
    # reported a single 0.1 s sub as no time at all.
    lines = [
        IntegrationLine(
            label=label,
            actual_minutes=actual_sec[label] / 60.0,
            session_count=len(nights[label]),
            sub_count=sub_count[label],
        )
        for label in sorted(actual_sec, key=_label_order)
    ]
    exposures = [
        ExposureLine(
            label=label,
            exposure_seconds=exposure,
            sub_count=exposure_subs[(label, exposure)],
            actual_minutes=exposure_sec[(label, exposure)] / 60.0,
        )
        for label, exposure in sorted(exposure_sec, key=lambda k: (_label_order(k[0]), k[1]))
    ]

    return IntegrationSummary(
        lines=lines,
        exposures=exposures,
        total_actual_minutes=total_sec / 60.0,
        first_session_date=min(dates) if dates else None,
        last_session_date=max(dates) if dates else None,
    )


@router.get("/{project_id}/integration")
async def get_integration(project_id: int) -> IntegrationSummary:
    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")
        return await _compute_integration(conn, project_id)
