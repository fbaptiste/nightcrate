"""Project ↔ DSO main-target associations (v0.38.0).

`project_target` is the single source of truth for a project's "main
targets". Rows are created either manually here (the Overview's "+ Add
target" affordance) or by `api/project_solve.create_solve` auto-flagging
its best-guess main object. `api/project_solve._assemble_response`
derives the per-object `is_main` flag on the solve response from this
table — so toggling main on the Plate Solve tab and adding via the
Overview "+" edit the same record, and rows survive `DELETE /solve`.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from nightcrate.api._common import get_or_404, integrity_guard, row_to_dict
from nightcrate.db.session import get_db
from nightcrate.services.gallery import ImagingRun, imaging_runs, valid_session_date
from nightcrate.services.messier import Candidate, order_candidates

router = APIRouter(prefix="/api/projects", tags=["Projects"])
links_router = APIRouter(prefix="/api/project-target-links", tags=["Projects"])


class TargetCreate(BaseModel):
    dso_id: int


class TargetResponse(BaseModel):
    # The project_target PK. sub_frame.project_target_id references it, so the
    # catalog's per-frame target correction (v0.41.1) needs it on the wire.
    id: int
    dso_id: int
    active: bool
    primary_designation: str
    common_name: str | None
    obj_type: str
    ra_deg: float | None
    dec_deg: float | None
    created_at: str


class ProjectTargetLink(BaseModel):
    dso_id: int
    project_id: int
    name: str
    status: str
    first_date: str | None
    last_date: str | None
    nights: int
    imaging_runs: list[ImagingRun]


@links_router.get("", response_model=list[ProjectTargetLink])
async def list_project_target_links() -> list[ProjectTargetLink]:
    """Return every active project's main-target links in three batched reads."""
    async with get_db() as conn:
        project_cursor = await conn.execute(
            """
            SELECT id, name, status, created_at
            FROM project
            WHERE active = 1
            ORDER BY id
            """
        )
        projects = {int(row["id"]): row for row in await project_cursor.fetchall()}

        target_cursor = await conn.execute(
            """
            SELECT pt.project_id, pt.dso_id
            FROM project_target pt
            JOIN project p ON p.id = pt.project_id
            WHERE p.active = 1
            ORDER BY pt.dso_id, pt.project_id
            """
        )
        target_rows = await target_cursor.fetchall()

        session_cursor = await conn.execute(
            """
            SELECT ps.project_id, ps.session_date
            FROM project_session ps
            JOIN project p ON p.id = ps.project_id
            WHERE p.active = 1
            ORDER BY ps.project_id, ps.id
            """
        )
        dates_by_project: dict[int, set[date]] = defaultdict(set)
        for row in await session_cursor.fetchall():
            parsed = valid_session_date(row["session_date"])
            if parsed is not None:
                dates_by_project[int(row["project_id"])].add(parsed)

    projects_by_dso: dict[int, list[Candidate]] = defaultdict(list)
    for target in target_rows:
        project_id = int(target["project_id"])
        dso_id = int(target["dso_id"])
        row = projects[project_id]
        projects_by_dso[dso_id].append(
            Candidate(
                project_id=project_id,
                name=row["name"],
                status=row["status"],
                created_at=row["created_at"],
                main_image_id=None,
                dates=sorted(dates_by_project.get(project_id, set())),
            )
        )

    result: list[ProjectTargetLink] = []
    for dso_id in sorted(projects_by_dso):
        for candidate in order_candidates(projects_by_dso[dso_id], image_first=False):
            dates = candidate.dates
            result.append(
                ProjectTargetLink(
                    dso_id=dso_id,
                    project_id=candidate.project_id,
                    name=candidate.name,
                    status=candidate.status,
                    first_date=dates[0].isoformat() if dates else None,
                    last_date=dates[-1].isoformat() if dates else None,
                    nights=len(dates),
                    imaging_runs=imaging_runs(dates),
                )
            )
    return result


_TARGET_SELECT = (
    "SELECT pt.id, pt.dso_id, pt.created_at,"
    " d.active, d.primary_designation, d.common_name, d.obj_type, d.ra_deg, d.dec_deg"
    " FROM project_target pt JOIN dso d ON d.id = pt.dso_id"
)


@router.get("/{project_id}/targets")
async def list_targets(project_id: int) -> list[TargetResponse]:
    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")
        cursor = await conn.execute(
            f"{_TARGET_SELECT} WHERE pt.project_id = ? ORDER BY pt.created_at",  # nosec B608 - constant SELECT
            (project_id,),
        )
        rows = await cursor.fetchall()
    return [TargetResponse(**row_to_dict(r)) for r in rows]


@router.post("/{project_id}/targets", status_code=201)
async def add_target(project_id: int, body: TargetCreate) -> TargetResponse:
    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")
        cursor = await conn.execute("SELECT active FROM dso WHERE id = ?", (body.dso_id,))
        dso_row = await cursor.fetchone()
        if dso_row is None:
            raise HTTPException(status_code=404, detail=f"DSO not found: {body.dso_id}")
        if not dso_row["active"]:
            raise HTTPException(
                status_code=409,
                detail="This object is no longer listed in its catalog.",
            )
        with integrity_guard(conflict_detail="DSO is already a target of this project"):
            await conn.execute(
                "INSERT INTO project_target (project_id, dso_id) VALUES (?, ?)",
                (project_id, body.dso_id),
            )
        await conn.commit()
        cursor = await conn.execute(
            f"{_TARGET_SELECT} WHERE pt.project_id = ? AND pt.dso_id = ?",  # nosec B608 - constant SELECT
            (project_id, body.dso_id),
        )
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=500, detail="Failed to load created target")
        return TargetResponse(**row_to_dict(row))


@router.delete("/{project_id}/targets/{dso_id}", status_code=204)
async def remove_target(project_id: int, dso_id: int) -> None:
    async with get_db() as conn:
        cursor = await conn.execute(
            "DELETE FROM project_target WHERE project_id = ? AND dso_id = ?",
            (project_id, dso_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Target not found: dso {dso_id}")
        await conn.commit()
