"""FITS file API endpoints."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from nightcrate.services.fits import list_hdus, read_header, render_image_png

router = APIRouter(prefix="/api/fits", tags=["fits"])


def _resolve_path(path: str) -> Path:
    p = Path(path)
    if not p.is_absolute():
        raise HTTPException(status_code=400, detail="Path must be absolute")
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    if p.suffix.lower() not in {".fits", ".fit", ".fts"}:
        raise HTTPException(status_code=400, detail="File must be a FITS file (.fits/.fit/.fts)")
    return p


@router.get("/hdus")
async def get_hdus(path: str = Query(..., description="Absolute path to FITS file")) -> list[dict]:
    """List all HDUs in the file with their type and whether they contain image data."""
    p = _resolve_path(path)
    try:
        return list_hdus(p)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/header")
async def get_header(
    path: str = Query(..., description="Absolute path to FITS file"),
    hdu: int = Query(0, description="HDU index"),
) -> list[dict]:
    """Return all header cards for the specified HDU."""
    p = _resolve_path(path)
    try:
        return read_header(p, hdu)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/image")
async def get_image(
    path: str = Query(..., description="Absolute path to FITS file"),
    hdu: int = Query(0, description="HDU index"),
) -> Response:
    """Return the image data for the specified HDU as a PNG (linear min/max scaled)."""
    p = _resolve_path(path)
    try:
        png_bytes = render_image_png(p, hdu)
        return Response(content=png_bytes, media_type="image/png")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
