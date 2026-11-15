"""Running-work reporting and the exclusive update-install reservation."""

from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from nightcrate.core import runtime
from nightcrate.db.session import get_db
from nightcrate.services import catalog_progress, solve_operations
from nightcrate.services.star_catalog import fetch as star_fetch

router = APIRouter(prefix="/api/app", tags=["Updates"])
LEASE_SECONDS = 120

ActivityKind = Literal["scan", "frame_analysis", "plate_solve", "catalog", "star_catalog"]


class RunningActivity(BaseModel):
    kind: ActivityKind
    label: str


class ActivityResponse(BaseModel):
    running: list[RunningActivity]


_CATALOG_NAMES = {
    "openngc": "OpenNGC",
    "github_50mgc": "50 MGC",
    "wikidata_external_refs": "Wikidata",
    "nightcrate": "NightCrate",
}


def _catalog_name(source: object) -> str:
    key = str(source or "")
    if key in _CATALOG_NAMES:
        return _CATALOG_NAMES[key]
    from nightcrate.catalog_loader.registry import optional_catalog

    catalog = optional_catalog(key)
    return catalog.display_name if catalog is not None else key


async def _project_name(project_id: int | None) -> str:
    if project_id is None:
        return ""
    try:
        async with get_db() as conn:
            cursor = await conn.execute("SELECT name FROM project WHERE id = ?", (project_id,))
            row = await cursor.fetchone()
            return str(row["name"]) if row is not None else ""
    except Exception:
        return ""


def running_kinds() -> list[tuple[ActivityKind, object | None]]:
    """Snapshot running work without yielding control to another request."""
    # Imported lazily to avoid a router dependency cycle: these modules import
    # ``admit_work`` for their work-starting endpoints.
    from nightcrate.api import ingest

    running: list[tuple[ActivityKind, object | None]] = []
    if ingest._INGEST_LOCK.locked():
        running.append(("scan", ingest._active_ingest_project_id))
    if ingest._ANALYZE_LOCK.locked():
        running.append(("frame_analysis", None))
    if solve_operations.active_operation() is not None:
        running.append(("plate_solve", None))
    catalog = catalog_progress.snapshot()
    if catalog is not None and catalog["outcome"] is None:
        running.append(("catalog", catalog.get("source")))
    star = star_fetch.current_operation()
    if star is not None and star.state == "running":
        running.append(("star_catalog", None))
    return running


async def _resolve_activity(
    running: list[tuple[ActivityKind, object | None]],
) -> list[RunningActivity]:
    resolved: list[RunningActivity] = []
    for kind, source in running:
        if kind == "scan":
            label = await _project_name(source if isinstance(source, int) else None)
        elif kind == "catalog":
            label = _catalog_name(source)
        else:
            label = ""
        resolved.append(RunningActivity(kind=kind, label=label))
    return resolved


async def running_activity() -> list[RunningActivity]:
    return await _resolve_activity(running_kinds())


async def admit_work() -> AsyncIterator[None]:
    """Admit one work request unless an update owns the process."""
    if runtime.install_is_reserved():
        raise HTTPException(status_code=409, detail="NightCrate is installing an update.")
    runtime.admitted_work += 1
    try:
        yield
    finally:
        runtime.admitted_work -= 1


@router.get("/activity", response_model=ActivityResponse)
async def activity() -> ActivityResponse:
    return ActivityResponse(running=await running_activity())


@router.post("/install-reservation")
async def reserve_install():
    running = running_kinds()
    if running or runtime.admitted_work > 0:
        resolved = await _resolve_activity(running)
        return JSONResponse(
            status_code=409,
            content={"running": [item.model_dump() for item in resolved]},
        )
    if runtime.install_is_reserved():
        return JSONResponse(status_code=409, content={"install_in_progress": True})
    token = secrets.token_urlsafe(32)
    runtime.install_owner = token
    runtime.install_lease_until = runtime.utcnow() + timedelta(seconds=LEASE_SECONDS)
    runtime.install_barrier = False
    return {"token": token}


@router.put("/install-reservation", status_code=status.HTTP_204_NO_CONTENT)
async def renew_install(token: str = Query(...)) -> Response:
    if (
        runtime.install_barrier
        or runtime.install_owner != token
        or not runtime.install_is_reserved()
    ):
        raise HTTPException(status_code=409, detail="The install reservation has expired.")
    runtime.install_lease_until = runtime.utcnow() + timedelta(seconds=LEASE_SECONDS)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/install-barrier", status_code=status.HTTP_204_NO_CONTENT)
async def install_barrier(token: str = Query(...)) -> Response:
    if (
        runtime.install_owner != token
        or not runtime.install_is_reserved()
        or running_kinds()
        or runtime.admitted_work > 0
    ):
        raise HTTPException(status_code=409, detail="NightCrate is still doing work.")
    runtime.install_barrier = True
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/install-reservation", status_code=status.HTTP_204_NO_CONTENT)
async def release_install(token: str = Query(...)) -> Response:
    if runtime.install_owner == token:
        runtime.install_owner = None
        runtime.install_lease_until = None
        runtime.install_barrier = False
    return Response(status_code=status.HTTP_204_NO_CONTENT)
