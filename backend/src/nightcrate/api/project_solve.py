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
from nightcrate.api.plate_solve import _failure_detail, query_dsos_in_cone
from nightcrate.api.project_solve_models import (
    IdentifiedDso,
    ProjectSolveRequest,
    ProjectSolveResponse,
    SetMainRequest,
)
from nightcrate.core.app_config import get_projects_root
from nightcrate.core.config import get_settings
from nightcrate.core.tasks import settle
from nightcrate.db.session import get_db
from nightcrate.services import fits_io, solve_operations
from nightcrate.services.dso_type_groups import group_for_raw_type
from nightcrate.services.image_annotation_models import WcsParams
from nightcrate.services.image_annotations import compute_fov, project_dsos
from nightcrate.services.path_resolver import resolve_path
from nightcrate.services.plate_solve import run_solve, validate_astap_path
from nightcrate.services.plate_solve_models import AstapLaunchError, ImageReadError
from nightcrate.services.project_images import VARIANT_SIZES, generate_rendered_images

logger = logging.getLogger("nightcrate")

router = APIRouter(prefix="/api/projects", tags=["Projects"])

_VALID_VARIANTS = set(VARIANT_SIZES.keys())
_project_solve_locks: dict[int, asyncio.Lock] = {}

_DSO_COLUMNS = (
    "d.active, d.primary_designation, d.obj_type, d.ra_deg, d.dec_deg,"
    " d.maj_axis_arcmin, d.min_axis_arcmin, d.position_angle_deg,"
    " d.common_name, d.constellation, d.distance_pc, d.distance_method, d.mag_b"
)


def _solve_dir(project_id: int) -> Path:
    root = get_projects_root()
    if root is None:
        raise HTTPException(status_code=503, detail="No database configured")
    return root / str(project_id) / "solve"


def _staging_dir(project_id: int, operation_id) -> Path:
    return _solve_dir(project_id) / f".staging-{operation_id}"


def _ensure_primary_fits_image(image_path: str) -> None:
    """Reject an existing FITS whose primary HDU has no image data."""
    left = Path(image_path.rsplit("::", 1)[0])
    if not left.exists():
        return
    try:
        source, file_type, _image_index, _cache_key = resolve_path(image_path)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise FileNotFoundError(exc.detail) from None
        raise ImageReadError(str(exc.detail)) from exc
    if file_type != "fits":
        return
    try:
        extensions = fits_io.list_extensions(source)
    except FileNotFoundError:
        raise
    except (OSError, ValueError) as exc:
        raise ImageReadError(f"NightCrate couldn't read this file: {exc}") from exc
    if not extensions or not extensions[0]["has_image"]:
        raise HTTPException(
            status_code=422,
            detail=_failure_detail(
                "This file's image isn't in its primary extension. "
                "Open it in the Image Analyzer to solve it.",
                "invalid_image",
                [],
            ),
        )


async def _render_to_staging(image_path: str, staging: Path) -> None:
    """Keep request cancellation from outliving the render worker."""
    await settle(
        asyncio.create_task(asyncio.to_thread(generate_rendered_images, image_path, staging))
    )


def _cleanup_generations(solve_dir: Path, current_id: int) -> None:
    """Leave only the newly published generation in the solve directory."""
    try:
        for path in solve_dir.iterdir():
            if path.name == str(current_id):
                continue
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
            except OSError:
                logger.warning("[project-solve] failed to remove obsolete path %s", path)
    except OSError:
        logger.warning("[project-solve] failed to scan solve generations in %s", solve_dir)


def _delete_published_generations(solve_dir: Path) -> None:
    """Delete published images while leaving in-flight staging directories alone."""
    if not solve_dir.is_dir():
        return
    for path in solve_dir.iterdir():
        if path.is_dir() and path.name.isdigit():
            shutil.rmtree(path, ignore_errors=True)
        elif path.is_file() and path.suffix.lower() == ".jpg":
            try:
                path.unlink()
            except OSError:
                logger.warning("[project-solve] failed to remove image %s", path)


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
        f"SELECT pd.dso_id, {_DSO_COLUMNS}"  # nosec B608 - column list is an internal constant
        " FROM project_dso pd JOIN dso d ON d.id = pd.dso_id"
        " WHERE pd.solve_id = ?",
        (solve["id"],),
    )
    link_rows = [row_to_dict(r) for r in await cursor.fetchall()]

    cursor = await conn.execute(
        """
        SELECT don.dso_id, don.name
        FROM dso_other_name don
        JOIN project_dso pd ON pd.dso_id = don.dso_id
        WHERE pd.solve_id = ?
        ORDER BY don.dso_id, don.position
        """,
        (solve["id"],),
    )
    other_names: dict[int, list[str]] = {}
    for row in await cursor.fetchall():
        other_names.setdefault(int(row["dso_id"]), []).append(str(row["name"]))

    # is_main now derives from project_target (the persistent source of truth),
    # so toggling a chip from the Overview and from the Plate Solve tab share
    # one record AND main flags survive solve deletion.
    cursor = await conn.execute(
        "SELECT dso_id FROM project_target WHERE project_id = ?",
        (project_id,),
    )
    main_dso_ids = {r["dso_id"] for r in await cursor.fetchall()}

    wcs = _wcs_from_solve(solve)
    dso_dicts = [
        {**r, "id": r["dso_id"], "type_group": group_for_raw_type(r.get("obj_type", ""))}
        for r in link_rows
    ]
    # project_dsos builds an astropy WCS and reprojects every object — CPU work
    # that would otherwise block the event loop on dense fields, so offload it.
    annotated_list = await asyncio.to_thread(project_dsos, wcs, dso_dicts)
    annotated = {a.id: a for a in annotated_list}
    is_main = {r["dso_id"]: r["dso_id"] in main_dso_ids for r in link_rows}
    active = {r["dso_id"]: bool(r["active"]) for r in link_rows}

    objects = [
        IdentifiedDso(
            dso_id=a.id,
            active=active[a.id],
            primary_designation=a.primary_designation,
            common_name=a.common_name,
            other_names=other_names.get(a.id, []),
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
        solver=solve["solver"],
        star_catalog=solve["star_catalog"],
        stars_detected=solve["stars_detected"],
        stars_matched=solve["stars_matched"],
        rms_px=solve["rms_px"],
        rms_arcsec=(
            solve["rms_px"] * solve["pixel_scale_arcsec"]
            if solve["rms_px"] is not None and solve["pixel_scale_arcsec"] is not None
            else None
        ),
        log_odds=solve["log_odds"],
        solve_path=solve["solve_path"],
        scale_stage=solve["scale_stage"],
        wcs=wcs,
        objects=objects,
    )


async def _require_response(conn, project_id: int, *, attempts=None) -> ProjectSolveResponse:
    response = await _assemble_response(conn, project_id)
    if response is None:
        raise HTTPException(
            status_code=500,
            detail=_failure_detail("Internal plate solve error", "error", attempts or []),
        )
    if attempts is not None:
        response.attempts = list(attempts)
    return response


async def _create_solve_claimed(
    project_id: int,
    body: ProjectSolveRequest,
    *,
    settings,
    solver,
    operation: solve_operations.SolveOperation,
) -> ProjectSolveResponse:
    async with get_db() as conn:
        await get_or_404(conn, "project", project_id, "Project")

        # Fast-fail before the expensive ASTAP solve; the integrity_guard on the
        # INSERT below is the authoritative UNIQUE(project_id) check.
        cursor = await conn.execute(
            "SELECT id FROM project_solve WHERE project_id = ?", (project_id,)
        )
        if await cursor.fetchone() is not None and not body.replace:
            raise HTTPException(
                status_code=409,
                detail=_failure_detail(
                    "A plate solve already exists for this project. Delete it first.",
                    "solve_exists",
                    [],
                ),
            )

        try:
            await settle(
                asyncio.create_task(asyncio.to_thread(_ensure_primary_fits_image, body.image_path)),
                on_cancel=operation.cancel,
            )
            operation.checkpoint()
            result = await run_solve(
                solver=solver,
                astap_path=settings.astap_executable_path,
                image_path=body.image_path,
                hdu=body.hdu,
                ra_hint=body.ra_hint,
                dec_hint=body.dec_hint,
                fov_hint=body.fov_hint,
                scale_hint_arcsec=body.scale_hint_arcsec,
                ignore_position=body.position == "none",
                ignore_scale=body.scale == "none",
                operation=operation,
            )
        except FileNotFoundError as exc:
            # A referenced source file (e.g. a pxiproject's master on another
            # drive) wasn't reachable — usually a disconnected drive, not a bug.
            raise HTTPException(
                status_code=422,
                detail=_failure_detail(
                    f"{exc} — is the source file's drive connected?",
                    "read_error",
                    operation.attempts(open_outcome="error", detail=str(exc)),
                ),
            ) from exc
        except ImageReadError as exc:
            raise HTTPException(
                status_code=422,
                detail=_failure_detail(
                    str(exc),
                    "read_error",
                    operation.attempts(open_outcome="error", detail=str(exc)),
                ),
            ) from exc
        except solve_operations.SolveCancelled:
            raise
        except HTTPException:
            raise
        except AstapLaunchError as exc:
            raise HTTPException(
                status_code=422,
                detail=_failure_detail(
                    str(exc),
                    "invalid_configuration",
                    operation.attempts(open_outcome="error", detail=str(exc)),
                ),
            ) from exc
        except TimeoutError as exc:
            message = str(exc) or "Plate solve timed out."
            raise HTTPException(
                status_code=408,
                detail=_failure_detail(
                    message,
                    "time_limit",
                    operation.attempts(open_outcome="overall_timeout", detail=message),
                ),
            ) from exc
        except Exception as exc:
            logger.exception("[project-solve] unexpected error for %s", body.image_path)
            message = "Internal plate solve error"
            raise HTTPException(
                status_code=500,
                detail=_failure_detail(
                    message,
                    "error",
                    operation.attempts(open_outcome="error", detail=message),
                ),
            ) from exc

        if not result.solved:
            raise HTTPException(
                status_code=422,
                detail=_failure_detail(
                    result.error_message or "Plate solve did not find a solution.",
                    result.failure_reason,
                    result.attempts,
                ),
            )
        if result.cd1_1 is None or result.crpix1 is None or not result.image_width:
            raise HTTPException(
                status_code=422,
                detail=_failure_detail(
                    "Plate solve did not return usable WCS data.",
                    "invalid_wcs",
                    result.attempts,
                ),
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

        solve_dir = _solve_dir(project_id)
        staging = _staging_dir(project_id, operation.operation_id)
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True, exist_ok=True)
        try:
            operation.checkpoint()
            await _render_to_staging(body.image_path, staging)
            operation.checkpoint()
        except solve_operations.SolveCancelled, asyncio.CancelledError:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        except Exception as exc:
            shutil.rmtree(staging, ignore_errors=True)
            logger.warning("[project-solve] render failed for %s", body.image_path, exc_info=True)
            raise HTTPException(
                status_code=422,
                detail=_failure_detail(
                    "The image solved, but NightCrate couldn't render it for display. "
                    "Nothing was saved.",
                    "render_failed",
                    result.attempts,
                ),
            ) from exc

        lock = _project_solve_locks.setdefault(project_id, asyncio.Lock())
        new_generation: Path | None = None
        committed = False
        async with lock:
            try:
                await conn.execute("BEGIN IMMEDIATE")
                operation.checkpoint()
                cursor = await conn.execute(
                    "SELECT id FROM project_solve WHERE project_id = ?", (project_id,)
                )
                old_row = await cursor.fetchone()
                old_id = int(old_row["id"]) if old_row is not None else None
                if old_id is not None and not body.replace:
                    raise HTTPException(
                        status_code=409,
                        detail=_failure_detail(
                            "A plate solve already exists for this project. Delete it first.",
                            "solve_exists",
                            result.attempts,
                        ),
                    )
                if old_id is not None:
                    await conn.execute("DELETE FROM project_solve WHERE id = ?", (old_id,))
            except BaseException:
                try:
                    await conn.rollback()
                finally:
                    shutil.rmtree(staging, ignore_errors=True)
                raise

            try:
                with integrity_guard(
                    conflict_detail=_failure_detail(
                        "A plate solve already exists for this project. Delete it first.",
                        "solve_exists",
                        result.attempts,
                    )
                ):
                    cursor = await conn.execute(
                        """INSERT INTO project_solve
                           (project_id, image_path, image_width, image_height,
                            center_ra_deg, center_dec_deg, ra_hms, dec_dms,
                            pixel_scale_arcsec, rotation_deg,
                            fov_width_arcmin, fov_height_arcmin,
                            cd1_1, cd1_2, cd2_1, cd2_2, crpix1, crpix2,
                            solver, star_catalog, stars_detected, stars_matched,
                            rms_px, log_odds, solve_path, scale_stage)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                                   ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                            result.solver,
                            result.star_catalog,
                            result.stars_detected,
                            result.stars_matched,
                            result.rms_px,
                            result.log_odds,
                            result.solve_path,
                            result.scale_stage,
                        ),
                    )
                solve_id = int(cursor.lastrowid)
                for item in annotated:
                    await conn.execute(
                        "INSERT INTO project_dso (solve_id, dso_id, is_main) VALUES (?, ?, ?)",
                        (solve_id, item.id, 1 if item.id == best_id else 0),
                    )
                if best_id is not None:
                    await conn.execute(
                        "INSERT OR IGNORE INTO project_target (project_id, dso_id) VALUES (?, ?)",
                        (project_id, best_id),
                    )

                new_generation = solve_dir / str(solve_id)
                if new_generation.exists():
                    await settle(
                        asyncio.create_task(asyncio.to_thread(shutil.rmtree, new_generation))
                    )
                try:
                    await settle(
                        asyncio.create_task(asyncio.to_thread(staging.rename, new_generation))
                    )
                except OSError as exc:
                    raise HTTPException(
                        status_code=422,
                        detail=_failure_detail(
                            "The image solved, but NightCrate couldn't render it for display. "
                            "Nothing was saved.",
                            "render_failed",
                            result.attempts,
                        ),
                    ) from exc

                async def commit_and_cleanup() -> None:
                    nonlocal committed
                    operation.begin_commit()
                    await conn.commit()
                    committed = True
                    await asyncio.to_thread(_cleanup_generations, solve_dir, solve_id)

                await settle(asyncio.create_task(commit_and_cleanup()))
            except BaseException:
                if not committed:
                    try:
                        await conn.rollback()
                    finally:
                        shutil.rmtree(staging, ignore_errors=True)
                        if new_generation is not None:
                            shutil.rmtree(new_generation, ignore_errors=True)
                raise
            return await _require_response(conn, project_id, attempts=result.attempts)


@router.post("/{project_id}/solve")
async def create_solve(project_id: int, body: ProjectSolveRequest) -> ProjectSolveResponse:
    settings = await get_settings()
    solver = body.solver or settings.default_solver
    if solver == "astap" and not settings.astap_executable_path:
        raise HTTPException(
            status_code=422,
            detail=_failure_detail(
                "ASTAP executable path is not configured. Set it in Settings.",
                "invalid_configuration",
                [],
            ),
        )
    if solver == "astap":
        validation = validate_astap_path(settings.astap_executable_path)
        if not validation["valid"]:
            raise HTTPException(
                status_code=422,
                detail=_failure_detail(
                    f"ASTAP path is invalid: {validation['error']}",
                    "invalid_configuration",
                    [],
                ),
            )
    try:
        operation = solve_operations.claim(body.operation_id, solver)
    except solve_operations.SolveCancelled:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Plate solve cancelled.",
                "failure_reason": "cancelled",
                "attempts": [],
            },
        ) from None
    except solve_operations.SolveBusy as exc:
        raise HTTPException(status_code=409, detail=_failure_detail(str(exc), "busy", [])) from exc
    try:
        return await _create_solve_claimed(
            project_id,
            body,
            settings=settings,
            solver=solver,
            operation=operation,
        )
    except solve_operations.SolveCancelled:
        shutil.rmtree(_staging_dir(project_id, operation.operation_id), ignore_errors=True)
        raise HTTPException(
            status_code=422,
            detail=_failure_detail(
                "Plate solve cancelled.",
                "cancelled",
                operation.attempts(open_outcome="cancelled", detail="Plate solve cancelled."),
            ),
        ) from None
    except HTTPException, asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("[project-solve] unexpected error for %s", body.image_path)
        message = "Internal plate solve error"
        raise HTTPException(
            status_code=500,
            detail=_failure_detail(
                message,
                "error",
                operation.attempts(open_outcome="error", detail=message),
            ),
        ) from exc
    finally:
        solve_operations.release(operation)


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

        # Verify the DSO belongs to this solve (gives a clear 404).
        cursor = await conn.execute(
            "SELECT id FROM project_dso WHERE solve_id = ? AND dso_id = ?",
            (solve["id"], dso_id),
        )
        if await cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"DSO {dso_id} not in this solve")

        # Source of truth for "is main" is project_target; sync that.
        if body.is_main:
            cursor = await conn.execute(
                "SELECT 1 FROM project_target WHERE project_id = ? AND dso_id = ?",
                (project_id, dso_id),
            )
            if await cursor.fetchone() is None:
                cursor = await conn.execute("SELECT active FROM dso WHERE id = ?", (dso_id,))
                dso_row = await cursor.fetchone()
                if dso_row is None:
                    raise HTTPException(status_code=404, detail=f"DSO {dso_id} not found")
                if not dso_row["active"]:
                    raise HTTPException(
                        status_code=409,
                        detail="This object is no longer listed in its catalog.",
                    )
                await conn.execute(
                    "INSERT INTO project_target (project_id, dso_id) VALUES (?, ?)",
                    (project_id, dso_id),
                )
        else:
            await conn.execute(
                "DELETE FROM project_target WHERE project_id = ? AND dso_id = ?",
                (project_id, dso_id),
            )
        await conn.commit()

        return await _require_response(conn, project_id)


@router.delete("/{project_id}/solve", status_code=204)
async def delete_solve(project_id: int) -> None:
    lock = _project_solve_locks.setdefault(project_id, asyncio.Lock())
    async with lock:
        async with get_db() as conn:
            await get_or_404(conn, "project", project_id, "Project")
            await conn.execute("DELETE FROM project_solve WHERE project_id = ?", (project_id,))
            await conn.commit()

        solve_dir = _solve_dir(project_id)
        _delete_published_generations(solve_dir)


@router.get("/{project_id}/solve/image/{variant}")
async def get_solve_image(project_id: int, variant: str) -> Response:
    if variant not in _VALID_VARIANTS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid variant: {variant}. Must be one of {sorted(_VALID_VARIANTS)}",
        )
    solve_dir = _solve_dir(project_id)
    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT id FROM project_solve WHERE project_id = ?", (project_id,)
        )
        row = await cursor.fetchone()
    path = solve_dir / str(row["id"]) / f"{variant}.jpg" if row is not None else None
    if path is None or not path.is_file():
        path = solve_dir / f"{variant}.jpg"
    if not path.is_file():
        return Response(status_code=204)
    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )
