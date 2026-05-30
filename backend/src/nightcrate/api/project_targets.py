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

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from nightcrate.api._common import get_or_404, integrity_guard, row_to_dict
from nightcrate.db.session import get_db

router = APIRouter(prefix="/api/projects", tags=["Projects"])


class TargetCreate(BaseModel):
    dso_id: int


class TargetResponse(BaseModel):
    dso_id: int
    primary_designation: str
    common_name: str | None
    obj_type: str
    ra_deg: float | None
    dec_deg: float | None
    created_at: str


_TARGET_SELECT = (
    "SELECT pt.dso_id, pt.created_at,"
    " d.primary_designation, d.common_name, d.obj_type, d.ra_deg, d.dec_deg"
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
        await get_or_404(conn, "dso", body.dso_id, "DSO")
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
