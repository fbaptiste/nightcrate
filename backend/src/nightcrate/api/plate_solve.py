"""Plate solving API — ASTAP integration endpoints."""

import logging

from fastapi import APIRouter, HTTPException, Query

from nightcrate.core.config import get_settings
from nightcrate.services.plate_solve import (
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
