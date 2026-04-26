"""Plate solving API — ASTAP integration + image annotation endpoints."""

import logging
import math

from fastapi import APIRouter, HTTPException, Query

from nightcrate.api._common import row_to_dict
from nightcrate.core.config import get_settings
from nightcrate.db.session import get_db
from nightcrate.services.dso_type_groups import group_for_raw_type
from nightcrate.services.image_annotation_models import (
    ImageAnnotationResult,
    WcsParams,
)
from nightcrate.services.image_annotations import (
    compute_fov,
    compute_rotation,
    detect_wcs_from_cards,
    project_dsos,
)
from nightcrate.services.path_resolver import resolve_path
from nightcrate.services.plate_solve import (
    _read_header_cards,
    get_solve_progress,
    run_plate_solve,
    validate_astap_path,
)
from nightcrate.services.plate_solve_models import PlateSolveRequest, PlateSolveResult

logger = logging.getLogger("nightcrate")

router = APIRouter(prefix="/api/plate-solve", tags=["Plate Solve"])


@router.post("/solve")
async def solve(request: PlateSolveRequest) -> PlateSolveResult:
    """Plate solve an image via ASTAP."""
    settings = await get_settings()
    if not settings.astap_executable_path:
        raise HTTPException(
            status_code=422,
            detail="ASTAP executable path is not configured. Set it in Settings.",
        )

    validation = validate_astap_path(settings.astap_executable_path)
    if not validation["valid"]:
        raise HTTPException(
            status_code=422,
            detail=f"ASTAP path is invalid: {validation['error']}",
        )

    try:
        return await run_plate_solve(
            astap_path=settings.astap_executable_path,
            image_path=request.image_path,
            hdu=request.hdu,
            mode=request.mode,
            ra_hint=request.ra_hint,
            dec_hint=request.dec_hint,
            fov_hint=request.fov_hint,
            timeout=request.timeout,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=408, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[plate-solve] unexpected error for %s", request.image_path)
        raise HTTPException(status_code=500, detail="Internal plate solve error") from exc


@router.post("/validate-path")
async def validate_path(
    path: str = Query(..., description="Path to ASTAP executable or .app bundle"),
) -> dict:
    """Validate an ASTAP executable path. Handles macOS .app bundle resolution."""
    return validate_astap_path(path)


@router.get("/progress")
async def progress() -> dict:
    """Return the current plate solve progress message."""
    return {"message": get_solve_progress()}


@router.post("/cancel")
async def cancel() -> dict:
    """Cancel a running plate solve."""
    from nightcrate.services.plate_solve import cancel_solve

    cancelled = cancel_solve()
    return {"cancelled": cancelled}


@router.get("/detect-wcs")
async def detect_wcs(
    path: str = Query(..., description="Image path"),
    hdu: int = Query(0),
) -> WcsParams | None:
    """Check if an image has WCS information in its headers."""
    source, file_type, image_index, _ck = resolve_path(path)
    cards = _read_header_cards(source, file_type, image_index, hdu)
    return detect_wcs_from_cards(cards)


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
            cards = _read_header_cards(source, file_type, image_index, hdu)
            raw: dict[str, str] = {}
            for card in cards:
                if card["key"]:
                    raw[card["key"].upper()] = card["value"]
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
        cards = _read_header_cards(source, file_type, image_index, hdu)
        wcs_params = detect_wcs_from_cards(cards)
        if wcs_params is None:
            raise HTTPException(
                status_code=422,
                detail="No WCS information available. Plate solve the image first.",
            )

    center_ra, center_dec, diag_radius, fov_w, fov_h, pixel_scale = compute_fov(
        wcs_params,
    )
    rotation = compute_rotation(wcs_params)

    dsos = await _query_dsos_in_cone(center_ra, center_dec, diag_radius)

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


async def _query_dsos_in_cone(
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
        ra_clause = "(ra_deg >= ? OR ra_deg <= ?)" if ra_min < 0 else "(ra_deg >= ? OR ra_deg <= ?)"
        ra_params = (ra_min % 360, ra_max % 360)
    else:
        ra_clause = "ra_deg BETWEEN ? AND ?"
        ra_params = (ra_min, ra_max)

    query = (  # nosec B608 — ra_clause is hardcoded SQL, not user input
        f"SELECT id, primary_designation, obj_type, ra_deg, dec_deg,"
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

    results: list[dict] = []
    for row in rows:
        d = row_to_dict(row)
        d["type_group"] = group_for_raw_type(d.get("obj_type", ""))
        results.append(d)
    return results
