"""Project imaging-session + integration + filter-goal endpoints (v0.38.0).

A session is a manually-entered capture batch (N identical light subs of one
filter). Per-filter ACTUAL integration is derived here from the sessions
(exposure x sub count); goals are entered separately. The v0.39.0 ingest
pipeline will store individual file-backed sub_frames and COALESCE over these
manual values.
"""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, HTTPException

from nightcrate.api._common import get_or_404, row_to_dict
from nightcrate.api.project_session_models import (
    LINE_NAMES,
    FilterGoalsSet,
    IntegrationLine,
    IntegrationSummary,
    SessionCreate,
    SessionResponse,
    SessionUpdate,
)
from nightcrate.db.session import get_db

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


def _session_response(d: dict) -> SessionResponse:
    d["integration_minutes"] = round(d["exposure_seconds"] * d["num_subs"] / 60.0, 2)
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


@router.patch("/{project_id}/sessions/{session_id}")
async def update_session(project_id: int, session_id: int, body: SessionUpdate) -> SessionResponse:
    fields = body.model_dump(exclude_unset=True)

    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")
        cursor = await conn.execute(
            "SELECT * FROM project_session WHERE id = ? AND project_id = ?",
            (session_id, project_id),
        )
        existing = await cursor.fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
        existing = row_to_dict(existing)

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
        cursor = await conn.execute(
            "SELECT id FROM project_session WHERE id = ? AND project_id = ?",
            (session_id, project_id),
        )
        if await cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
        await conn.execute("DELETE FROM project_session WHERE id = ?", (session_id,))
        await conn.commit()


# ── Integration summary + goals ─────────────────────────────────────────────


async def _compute_integration(conn, project_id: int) -> IntegrationSummary:
    cursor = await conn.execute(
        "SELECT filter_id, line_name, exposure_seconds, num_subs, session_date"
        " FROM project_session WHERE project_id = ?",
        (project_id,),
    )
    sessions = [row_to_dict(r) for r in await cursor.fetchall()]

    # Map each specific-filter session to its bandpass line(s). A duo-band
    # filter (Ha+Oiii) maps to BOTH — sub time counts toward each line budget,
    # which is correct for "how much Ha do I have?" (spec §12, documented).
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
    session_count: dict[str, int] = defaultdict(int)
    sub_count: dict[str, int] = defaultdict(int)
    total_sec = 0.0
    dates: list[str] = []

    for s in sessions:
        secs = s["exposure_seconds"] * s["num_subs"]
        total_sec += secs  # wall-clock total counts each session once
        if s["session_date"]:
            dates.append(s["session_date"][:10])
        if s["filter_id"] is not None:
            lines = passband_lines.get(s["filter_id"], [])
        elif s["line_name"] is not None:
            lines = [s["line_name"]]
        else:
            lines = []
        for line in lines:
            actual_sec[line] += secs
            session_count[line] += 1
            sub_count[line] += s["num_subs"]

    cursor = await conn.execute(
        "SELECT line_name, goal_minutes FROM project_filter_goal WHERE project_id = ?",
        (project_id,),
    )
    goals = {r["line_name"]: r["goal_minutes"] for r in await cursor.fetchall()}

    present = set(actual_sec) | set(goals)
    lines = [
        IntegrationLine(
            line_name=line,
            actual_minutes=round(actual_sec[line] / 60.0, 2),
            goal_minutes=goals.get(line),
            session_count=session_count[line],
            sub_count=sub_count[line],
        )
        for line in LINE_NAMES
        if line in present
    ]

    return IntegrationSummary(
        lines=lines,
        total_actual_minutes=round(total_sec / 60.0, 2),
        first_session_date=min(dates) if dates else None,
        last_session_date=max(dates) if dates else None,
    )


@router.get("/{project_id}/integration")
async def get_integration(project_id: int) -> IntegrationSummary:
    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")
        return await _compute_integration(conn, project_id)


@router.put("/{project_id}/integration/goals")
async def set_filter_goals(project_id: int, body: FilterGoalsSet) -> IntegrationSummary:
    """Replace the full set of per-filter goals for a project."""
    # Last value wins for a repeated line_name (UNIQUE (project_id, line_name)).
    goals = {g.line_name: g.goal_minutes for g in body.goals}

    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")
        await conn.execute("DELETE FROM project_filter_goal WHERE project_id = ?", (project_id,))
        for line_name, goal_minutes in goals.items():
            await conn.execute(
                "INSERT INTO project_filter_goal (project_id, line_name, goal_minutes)"
                " VALUES (?, ?, ?)",
                (project_id, line_name, goal_minutes),
            )
        await conn.commit()
        return await _compute_integration(conn, project_id)
