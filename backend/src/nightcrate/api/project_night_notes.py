"""Notes attached to a project's civil observing nights."""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from nightcrate.api._common import get_or_404, row_to_dict
from nightcrate.db.session import get_db

logger = logging.getLogger("nightcrate.project_night_notes")
_LOG_PREFIX = "[night-notes]"

router = APIRouter(prefix="/api/projects", tags=["Projects"])


class NightNote(BaseModel):
    night_date: str
    notes: str
    updated_at: str


class NightNotePut(BaseModel):
    notes: str = Field(min_length=1, max_length=10_000)

    @field_validator("notes", mode="before")
    @classmethod
    def trim_notes(cls, value):
        return value.strip() if isinstance(value, str) else value


def _valid_night_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="night_date must be a real YYYY-MM-DD date"
        ) from exc
    if parsed.isoformat() != value:
        raise HTTPException(status_code=422, detail="night_date must be a real YYYY-MM-DD date")
    return value


async def _fetch_note(conn, project_id: int, night_date: str) -> NightNote | None:
    cursor = await conn.execute(
        "SELECT night_date, notes, updated_at FROM project_night_note "
        "WHERE project_id = ? AND night_date = ?",
        (project_id, night_date),
    )
    row = await cursor.fetchone()
    return NightNote(**row_to_dict(row)) if row is not None else None


@router.get("/{project_id}/night-notes", response_model=list[NightNote])
async def list_night_notes(project_id: int) -> list[NightNote]:
    async with get_db() as conn:
        try:
            await get_or_404(conn, "project", project_id, "Project")
            cursor = await conn.execute(
                "SELECT night_date, notes, updated_at FROM project_night_note "
                "WHERE project_id = ? ORDER BY night_date DESC",
                (project_id,),
            )
            return [NightNote(**row_to_dict(row)) for row in await cursor.fetchall()]
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("%s failed to list notes for project %d", _LOG_PREFIX, project_id)
            raise HTTPException(status_code=500, detail="Failed to list night notes") from exc


@router.put("/{project_id}/night-notes/{night_date}", response_model=NightNote)
async def put_night_note(project_id: int, night_date: str, body: NightNotePut) -> NightNote:
    night_date = _valid_night_date(night_date)
    async with get_db() as conn:
        await conn.execute("BEGIN IMMEDIATE")
        try:
            await get_or_404(conn, "project", project_id, "Project")
            await conn.execute(
                """
                INSERT INTO project_night_note (project_id, night_date, notes)
                VALUES (?, ?, ?)
                ON CONFLICT(project_id, night_date) DO UPDATE SET
                    notes = excluded.notes,
                    updated_at = datetime('now')
                """,
                (project_id, night_date, body.notes),
            )
            note = await _fetch_note(conn, project_id, night_date)
            if note is None:
                raise RuntimeError("upserted night note could not be loaded")
            await conn.commit()
            return note
        except HTTPException:
            await conn.rollback()
            raise
        except Exception as exc:
            await conn.rollback()
            logger.exception(
                "%s failed to save project %d note for %s",
                _LOG_PREFIX,
                project_id,
                night_date,
            )
            raise HTTPException(status_code=500, detail="Failed to save night note") from exc
        except BaseException:
            await conn.rollback()
            raise


@router.delete("/{project_id}/night-notes/{night_date}", status_code=204)
async def delete_night_note(project_id: int, night_date: str) -> Response:
    night_date = _valid_night_date(night_date)
    async with get_db() as conn:
        await conn.execute("BEGIN IMMEDIATE")
        try:
            await get_or_404(conn, "project", project_id, "Project")
            cursor = await conn.execute(
                "DELETE FROM project_night_note WHERE project_id = ? AND night_date = ?",
                (project_id, night_date),
            )
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Night note not found")
            await conn.commit()
            return Response(status_code=204)
        except HTTPException:
            await conn.rollback()
            raise
        except Exception as exc:
            await conn.rollback()
            logger.exception(
                "%s failed to delete project %d note for %s",
                _LOG_PREFIX,
                project_id,
                night_date,
            )
            raise HTTPException(status_code=500, detail="Failed to delete night note") from exc
        except BaseException:
            await conn.rollback()
            raise
