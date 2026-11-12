"""Plate solving API — ASTAP integration + image annotation endpoints."""

import asyncio
import logging
import math
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from nightcrate.api._common import load_other_names, row_to_dict
from nightcrate.core.config import get_settings
from nightcrate.db.session import get_db
from nightcrate.services import solve_operations
from nightcrate.services.dso_type_groups import group_for_raw_type
from nightcrate.services.image_annotation_models import (
    FileSolution,
    ImageAnnotationResult,
    WcsParams,
)
from nightcrate.services.image_annotations import (
    compute_fov,
    compute_rotation,
    project_dsos,
)
from nightcrate.services.path_resolver import resolve_path
from nightcrate.services.plate_solve import (
    cards_to_dict,
    read_file_solution,
    read_header_cards,
    run_solve,
    validate_astap_path,
)
from nightcrate.services.plate_solve_models import (
    AstapLaunchError,
    ImageReadError,
    PlateSolveRequest,
    PlateSolveResult,
)

logger = logging.getLogger("nightcrate")

router = APIRouter(prefix="/api/plate-solve", tags=["Plate Solve"])


class CancelSolveRequest(BaseModel):
    operation_id: UUID


def _failure_detail(message: str, failure_reason: str | None, attempts) -> dict:
    return {
        "message": message,
        "failure_reason": failure_reason,
        "attempts": [attempt.model_dump(mode="json") for attempt in attempts],
    }


async def _read_image_value(reader, *args, path: str):
    try:
        return await asyncio.to_thread(reader, *args)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[plate-solve] image read failed for %s", path)
        raise HTTPException(status_code=500, detail="Internal processing error") from exc


@router.post("/solve")
async def solve(request: PlateSolveRequest) -> PlateSolveResult:
    """Plate solve an image with the selected solver."""
    logger.info(
        "[plate-solve] solve request: path=%r hdu=%d",
        request.image_path,
        request.hdu,
    )
    settings = await get_settings()
    solver = request.solver or settings.default_solver
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
        operation = solve_operations.claim(request.operation_id, solver)
    except solve_operations.SolveCancelled:
        return PlateSolveResult(
            solved=False,
            solver=solver,
            error_message="Plate solve cancelled.",
            failure_reason="cancelled",
        )
    except solve_operations.SolveBusy as exc:
        raise HTTPException(status_code=409, detail=_failure_detail(str(exc), "busy", [])) from exc
    try:
        operation.checkpoint()
        return await run_solve(
            solver=solver,
            astap_path=settings.astap_executable_path,
            image_path=request.image_path,
            hdu=request.hdu,
            ra_hint=request.ra_hint,
            dec_hint=request.dec_hint,
            fov_hint=request.fov_hint,
            scale_hint_arcsec=request.scale_hint_arcsec,
            ignore_position=request.position == "none",
            ignore_scale=request.scale == "none",
            timeout=request.timeout,
            operation=operation,
        )
    except solve_operations.SolveCancelled:
        return PlateSolveResult(
            solved=False,
            solver=solver,
            error_message="Plate solve cancelled.",
            failure_reason="cancelled",
            attempts=operation.attempts(open_outcome="cancelled", detail="Plate solve cancelled."),
        )
    except FileNotFoundError as exc:
        # A referenced source file wasn't reachable — usually a disconnected
        # drive (e.g. a pxiproject master on another volume), not a bug.
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
        logger.exception("[plate-solve] unexpected error for %s", request.image_path)
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


@router.post("/validate-path")
async def validate_path(
    path: str = Query(..., description="Path to ASTAP executable or .app bundle"),
) -> dict:
    """Validate an ASTAP executable path. Handles macOS .app bundle resolution."""
    return validate_astap_path(path)


@router.get("/progress")
async def progress(operation_id: UUID = Query(...)) -> dict:
    """Return structured progress for one operation."""
    progress_snapshot = solve_operations.snapshot(operation_id)
    if progress_snapshot is None:
        raise HTTPException(status_code=404, detail="Unknown plate solve operation.")
    return progress_snapshot.model_dump(mode="json")


@router.post("/cancel")
async def cancel(request: CancelSolveRequest) -> dict:
    """Cancel one identified operation."""
    result = solve_operations.cancel(request.operation_id)
    return result.model_dump()


@router.get("/detect-wcs")
async def detect_wcs(
    path: str = Query(..., description="Image path"),
    hdu: int = Query(0),
) -> FileSolution:
    """Check if an image has WCS information in its headers."""
    source, file_type, image_index, _ck = resolve_path(path)
    return await _read_image_value(
        read_file_solution, source, file_type, image_index, hdu, path=path
    )


@router.get("/annotate")
async def annotate(
    path: str = Query(..., description="Image path"),
    hdu: int = Query(0),
    crval1: float | None = Query(None),
    crval2: float | None = Query(None),
    cd1_1: float | None = Query(None),
    cd1_2: float | None = Query(None),
    cd2_1: float | None = Query(None),
    cd2_2: float | None = Query(None),
    crpix1: float | None = Query(None),
    crpix2: float | None = Query(None),
    naxis1: int | None = Query(None),
    naxis2: int | None = Query(None),
) -> ImageAnnotationResult:
    """Return DSO annotations for an image, projected to pixel coordinates.

    WCS can come from image headers or be provided explicitly (e.g. from
    a prior ASTAP solve). If explicit WCS params are all provided, they
    take priority over headers.
    """
    wcs_override = _build_wcs_override(
        crval1,
        crval2,
        cd1_1,
        cd1_2,
        cd2_1,
        cd2_2,
        crpix1,
        crpix2,
    )

    if wcs_override is not None:
        nx = naxis1
        ny = naxis2
        if not nx or not ny:
            source, file_type, image_index, _ck = resolve_path(path)
            cards = await _read_image_value(
                read_header_cards, source, file_type, image_index, hdu, path=path
            )
            raw = cards_to_dict(cards)
            nx = nx or int(float(raw.get("NAXIS1", "0")))
            ny = ny or int(float(raw.get("NAXIS2", "0")))
        if not nx or not ny:
            raise HTTPException(status_code=422, detail="Cannot determine image dimensions.")
        wcs_params = WcsParams(
            **wcs_override,
            naxis1=nx,
            naxis2=ny,
        )
    else:
        source, file_type, image_index, _ck = resolve_path(path)
        solution = await _read_image_value(
            read_file_solution, source, file_type, image_index, hdu, path=path
        )
        wcs_params = solution.wcs
        if wcs_params is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    solution.unavailable_reason
                    or "No WCS information available. Plate solve the image first."
                ),
            )

    center_ra, center_dec, diag_radius, fov_w, fov_h, pixel_scale = compute_fov(
        wcs_params,
    )
    rotation = compute_rotation(wcs_params)

    dsos = await query_dsos_in_cone(center_ra, center_dec, diag_radius)

    annotations = project_dsos(wcs_params, dsos)

    return ImageAnnotationResult(
        wcs=wcs_params,
        center_ra_deg=round(center_ra, 6),
        center_dec_deg=round(center_dec, 6),
        fov_width_arcmin=round(fov_w, 2),
        fov_height_arcmin=round(fov_h, 2),
        pixel_scale_arcsec=round(pixel_scale, 3),
        rotation_deg=round(rotation, 3),
        dsos=annotations,
    )


def _build_wcs_override(
    crval1: float | None,
    crval2: float | None,
    cd1_1: float | None,
    cd1_2: float | None,
    cd2_1: float | None,
    cd2_2: float | None,
    crpix1: float | None,
    crpix2: float | None,
) -> dict | None:
    """Return a dict of WCS fields if all override params are provided."""
    vals = {
        "crval1": crval1,
        "crval2": crval2,
        "cd1_1": cd1_1,
        "cd1_2": cd1_2,
        "cd2_1": cd2_1,
        "cd2_2": cd2_2,
        "crpix1": crpix1,
        "crpix2": crpix2,
    }
    if all(v is not None for v in vals.values()):
        return vals
    if any(v is not None for v in vals.values()):
        raise HTTPException(
            status_code=422,
            detail="Partial WCS override — all 8 fields must be provided together.",
        )
    return None


async def query_dsos_in_cone(
    center_ra: float,
    center_dec: float,
    radius_deg: float,
) -> list[dict]:
    """Cone-search the DSO table. Handles RA wrap-around near 0h/24h."""
    cos_dec = max(math.cos(math.radians(center_dec)), 1e-6)
    ra_half = radius_deg / cos_dec
    dec_min = max(-90.0, center_dec - radius_deg)
    dec_max = min(90.0, center_dec + radius_deg)
    ra_min = center_ra - ra_half
    ra_max = center_ra + ra_half

    if ra_min < 0 or ra_max > 360:
        ra_clause = "(ra_deg >= ? OR ra_deg <= ?)"
        ra_params = (ra_min % 360, ra_max % 360)
    else:
        ra_clause = "ra_deg BETWEEN ? AND ?"
        ra_params = (ra_min, ra_max)

    query = (
        # nosec B608 — hardcoded SQL: only ra_clause (a fixed string) is interpolated; all values are bound with ? params
        f"SELECT id, primary_designation, obj_type, ra_deg, dec_deg,"  # nosec B608
        f" maj_axis_arcmin, min_axis_arcmin, position_angle_deg,"
        f" common_name, constellation, distance_pc, distance_method, mag_b"
        f" FROM dso WHERE active = 1"
        f" AND ra_deg IS NOT NULL AND dec_deg IS NOT NULL"
        f" AND dec_deg BETWEEN ? AND ?"
        f" AND {ra_clause}"
        f" ORDER BY COALESCE(maj_axis_arcmin, 0) DESC LIMIT 500"
    )

    async with get_db() as conn:
        cursor = await conn.execute(
            query,
            (dec_min, dec_max, *ra_params),
        )
        rows = await cursor.fetchall()
        other_names = await load_other_names(conn, [int(row["id"]) for row in rows])

    results: list[dict] = []
    for row in rows:
        d = row_to_dict(row)
        d["other_names"] = other_names.get(int(row["id"]), [])
        d["type_group"] = group_for_raw_type(d.get("obj_type", ""))
        results.append(d)
    return results
