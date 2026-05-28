"""Project plate-solve + identified-DSO endpoints (v0.37.0).

A project has at most one plate solve. The solved image is standalone (kept
out of the gallery). Solving stores the solution + every catalog object in the
frame (one auto-flagged main); deleting the solve cascades its objects.
"""

from __future__ import annotations

import asyncio
import logging
import math
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from nightcrate.api._common import get_or_404, integrity_guard, row_to_dict
from nightcrate.api.plate_solve import query_dsos_in_cone
from nightcrate.api.project_solve_models import (
    IdentifiedDso,
    ProjectSolveRequest,
    ProjectSolveResponse,
    SetMainRequest,
)
from nightcrate.core.app_config import get_projects_root
from nightcrate.core.config import get_settings
from nightcrate.db.session import get_db
from nightcrate.services.dso_type_groups import group_for_raw_type
from nightcrate.services.image_annotation_models import WcsParams
from nightcrate.services.image_annotations import compute_fov, project_dsos
from nightcrate.services.plate_solve import run_plate_solve, validate_astap_path
from nightcrate.services.project_images import VARIANT_SIZES, generate_rendered_images

logger = logging.getLogger("nightcrate")

router = APIRouter(prefix="/api/projects", tags=["Projects"])

_VALID_VARIANTS = set(VARIANT_SIZES.keys())

_DSO_COLUMNS = (
    "d.primary_designation, d.obj_type, d.ra_deg, d.dec_deg,"
    " d.maj_axis_arcmin, d.min_axis_arcmin, d.position_angle_deg,"
    " d.common_name, d.constellation, d.distance_pc, d.distance_method, d.mag_b"
)


def _solve_dir(project_id: int) -> Path:
    root = get_projects_root()
    if root is None:
        raise HTTPException(status_code=503, detail="No database configured")
    return root / str(project_id) / "solve"


def _wcs_from_solve(row: dict) -> WcsParams:
    return WcsParams(
        crval1=row["center_ra_deg"],
        crval2=row["center_dec_deg"],
        cd1_1=row["cd1_1"],
        cd1_2=row["cd1_2"],
        cd2_1=row["cd2_1"],
        cd2_2=row["cd2_2"],
        crpix1=row["crpix1"],
        crpix2=row["crpix2"],
        naxis1=row["image_width"],
        naxis2=row["image_height"],
    )


async def _assemble_response(conn, project_id: int) -> ProjectSolveResponse | None:
    cursor = await conn.execute("SELECT * FROM project_solve WHERE project_id = ?", (project_id,))
    solve = await cursor.fetchone()
    if solve is None:
        return None
    solve = row_to_dict(solve)

    cursor = await conn.execute(
        f"SELECT pd.dso_id, pd.is_main, {_DSO_COLUMNS}"  # nosec B608 - column list is an internal constant
        " FROM project_dso pd JOIN dso d ON d.id = pd.dso_id"
        " WHERE pd.solve_id = ?",
        (solve["id"],),
    )
    link_rows = [row_to_dict(r) for r in await cursor.fetchall()]

    wcs = _wcs_from_solve(solve)
    dso_dicts = [
        {**r, "id": r["dso_id"], "type_group": group_for_raw_type(r.get("obj_type", ""))}
        for r in link_rows
    ]
    # project_dsos builds an astropy WCS and reprojects every object — CPU work
    # that would otherwise block the event loop on dense fields, so offload it.
    annotated_list = await asyncio.to_thread(project_dsos, wcs, dso_dicts)
    annotated = {a.id: a for a in annotated_list}
    is_main = {r["dso_id"]: bool(r["is_main"]) for r in link_rows}

    objects = [
        IdentifiedDso(
            dso_id=a.id,
            primary_designation=a.primary_designation,
            common_name=a.common_name,
            obj_type=a.obj_type,
            type_group=a.type_group,
            constellation=a.constellation,
            ra_deg=a.ra_deg,
            dec_deg=a.dec_deg,
            maj_axis_arcmin=a.maj_axis_arcmin,
            min_axis_arcmin=a.min_axis_arcmin,
            distance_pc=a.distance_pc,
            mag_b=a.mag_b,
            is_main=is_main.get(a.id, False),
            pixel_x=a.pixel_x,
            pixel_y=a.pixel_y,
            ellipse_semi_major_px=a.ellipse_semi_major_px,
            ellipse_semi_minor_px=a.ellipse_semi_minor_px,
            ellipse_angle_deg=a.ellipse_angle_deg,
        )
        for a in annotated.values()
    ]
    # Mains first, then largest objects.
    objects.sort(key=lambda o: (not o.is_main, -(o.maj_axis_arcmin or 0.0)))

    return ProjectSolveResponse(
        id=solve["id"],
        project_id=solve["project_id"],
        image_path=solve["image_path"],
        image_width=solve["image_width"],
        image_height=solve["image_height"],
        center_ra_deg=solve["center_ra_deg"],
        center_dec_deg=solve["center_dec_deg"],
        ra_hms=solve["ra_hms"],
        dec_dms=solve["dec_dms"],
        pixel_scale_arcsec=solve["pixel_scale_arcsec"],
        rotation_deg=solve["rotation_deg"],
        fov_width_arcmin=solve["fov_width_arcmin"],
        fov_height_arcmin=solve["fov_height_arcmin"],
        solved_at=solve["solved_at"],
        wcs=wcs,
        objects=objects,
    )


async def _require_response(conn, project_id: int) -> ProjectSolveResponse:
    response = await _assemble_response(conn, project_id)
    if response is None:
        raise HTTPException(status_code=500, detail="Plate solve state could not be assembled")
    return response


@router.post("/{project_id}/solve")
async def create_solve(project_id: int, body: ProjectSolveRequest) -> ProjectSolveResponse:
    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")

        # Fast-fail before the expensive ASTAP solve; the integrity_guard on the
        # INSERT below is the authoritative UNIQUE(project_id) check.
        cursor = await conn.execute(
            "SELECT id FROM project_solve WHERE project_id = ?", (project_id,)
        )
        if await cursor.fetchone() is not None:
            raise HTTPException(
                status_code=409,
                detail="A plate solve already exists for this project. Delete it first.",
            )

        settings = await get_settings()
        if not settings.astap_executable_path:
            raise HTTPException(
                status_code=422,
                detail="ASTAP executable path is not configured. Set it in Settings.",
            )
        validation = validate_astap_path(settings.astap_executable_path)
        if not validation["valid"]:
            raise HTTPException(
                status_code=422, detail=f"ASTAP path is invalid: {validation['error']}"
            )

        try:
            result = await run_plate_solve(
                astap_path=settings.astap_executable_path,
                image_path=body.image_path,
                hdu=body.hdu,
                mode="auto",
                ra_hint=body.ra_hint,
                dec_hint=body.dec_hint,
                fov_hint=body.fov_hint,
            )
        except FileNotFoundError as exc:
            # A referenced source file (e.g. a pxiproject's master on another
            # drive) wasn't reachable — usually a disconnected drive, not a bug.
            raise HTTPException(
                status_code=422,
                detail=f"{exc} — is the source file's drive connected?",
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except TimeoutError as exc:
            raise HTTPException(status_code=408, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("[project-solve] unexpected error for %s", body.image_path)
            raise HTTPException(status_code=500, detail="Internal plate solve error") from exc

        if not result.solved:
            raise HTTPException(
                status_code=422,
                detail=result.error_message or "Plate solve did not find a solution.",
            )
        if result.cd1_1 is None or result.crpix1 is None or not result.image_width:
            raise HTTPException(
                status_code=422, detail="Plate solve did not return usable WCS data."
            )

        wcs = WcsParams(
            crval1=result.ra_deg,
            crval2=result.dec_deg,
            cd1_1=result.cd1_1,
            cd1_2=result.cd1_2,
            cd2_1=result.cd2_1,
            cd2_2=result.cd2_2,
            crpix1=result.crpix1,
            crpix2=result.crpix2,
            naxis1=result.image_width,
            naxis2=result.image_height,
        )
        center_ra, center_dec, diag_radius, _fw, _fh, _ps = compute_fov(wcs)
        dso_rows = await query_dsos_in_cone(center_ra, center_dec, diag_radius)
        annotated = project_dsos(wcs, dso_rows)

        # Best-guess main: nearest the frame centre, tie-break largest object.
        best_id: int | None = None
        if annotated:
            cx, cy = result.image_width / 2, result.image_height / 2
            best = min(
                annotated,
                key=lambda a: (
                    math.hypot(a.pixel_x - cx, a.pixel_y - cy),
                    -(a.maj_axis_arcmin or 0.0),
                ),
            )
            best_id = best.id

        with integrity_guard(
            conflict_detail="A plate solve already exists for this project. Delete it first."
        ):
            cursor = await conn.execute(
                """INSERT INTO project_solve
                   (project_id, image_path, image_width, image_height,
                    center_ra_deg, center_dec_deg, ra_hms, dec_dms,
                    pixel_scale_arcsec, rotation_deg, fov_width_arcmin, fov_height_arcmin,
                    cd1_1, cd1_2, cd2_1, cd2_2, crpix1, crpix2)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    project_id,
                    body.image_path,
                    result.image_width,
                    result.image_height,
                    result.ra_deg,
                    result.dec_deg,
                    result.ra_hms,
                    result.dec_dms,
                    result.pixel_scale_arcsec,
                    result.rotation_deg,
                    result.fov_width_arcmin,
                    result.fov_height_arcmin,
                    result.cd1_1,
                    result.cd1_2,
                    result.cd2_1,
                    result.cd2_2,
                    result.crpix1,
                    result.crpix2,
                ),
            )
        solve_id = cursor.lastrowid
        for a in annotated:
            await conn.execute(
                "INSERT INTO project_dso (solve_id, dso_id, is_main) VALUES (?, ?, ?)",
                (solve_id, a.id, 1 if a.id == best_id else 0),
            )
        await conn.commit()

        # Pre-render the standalone solve image for the overlay viewer.
        try:
            await asyncio.to_thread(
                generate_rendered_images, body.image_path, _solve_dir(project_id)
            )
        except Exception:
            logger.warning("[project-solve] render failed for %s", body.image_path, exc_info=True)

        return await _require_response(conn, project_id)


@router.get("/{project_id}/solve")
async def get_solve(project_id: int) -> Response:
    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")
        response = await _assemble_response(conn, project_id)
    if response is None:
        return Response(status_code=204)
    return Response(
        content=response.model_dump_json(),
        media_type="application/json",
    )


@router.put("/{project_id}/solve/objects/{dso_id}")
async def set_object_main(
    project_id: int, dso_id: int, body: SetMainRequest
) -> ProjectSolveResponse:
    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")
        cursor = await conn.execute(
            "SELECT id FROM project_solve WHERE project_id = ?", (project_id,)
        )
        solve = await cursor.fetchone()
        if solve is None:
            raise HTTPException(status_code=404, detail="No plate solve for this project")

        cursor = await conn.execute(
            "UPDATE project_dso SET is_main = ? WHERE solve_id = ? AND dso_id = ?",
            (1 if body.is_main else 0, solve["id"], dso_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"DSO {dso_id} not in this solve")
        await conn.commit()

        return await _require_response(conn, project_id)


@router.delete("/{project_id}/solve", status_code=204)
async def delete_solve(project_id: int) -> None:
    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")
        await conn.execute("DELETE FROM project_solve WHERE project_id = ?", (project_id,))
        await conn.commit()

    solve_dir = _solve_dir(project_id)
    if solve_dir.is_dir():
        shutil.rmtree(solve_dir, ignore_errors=True)


@router.get("/{project_id}/solve/image/{variant}")
async def get_solve_image(project_id: int, variant: str) -> Response:
    if variant not in _VALID_VARIANTS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid variant: {variant}. Must be one of {sorted(_VALID_VARIANTS)}",
        )
    path = _solve_dir(project_id) / f"{variant}.jpg"
    if not path.is_file():
        return Response(status_code=204)
    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )
