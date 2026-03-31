"""FITS file API endpoints."""

from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from nightcrate.services.fits import (
    StretchParams,
    get_image_stats,
    list_hdus,
    read_header,
    render_image_png,
)

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
async def get_hdus(
    path: str = Query(..., description="Absolute path to FITS file"),
) -> list[dict]:
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


@router.get("/stats")
async def get_stats(
    path: str = Query(..., description="Absolute path to FITS file"),
    hdu: int = Query(0, description="HDU index"),
) -> dict:
    """Return per-channel statistics and auto-computed STF defaults."""
    p = _resolve_path(path)
    try:
        stats = get_image_stats(p, hdu)
        return asdict(stats)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/image")
async def get_image(
    path: str = Query(..., description="Absolute path to FITS file"),
    hdu: int = Query(0, description="HDU index"),
    stretch: str = Query("stf", description="Stretch type: stf | linear | asinh"),
    # STF params
    shadow: float = Query(0.0, description="Shadow clip, normalized 0–1"),
    midtone: float = Query(0.5, description="Midtones balance 0–1"),
    highlight: float = Query(1.0, description="Highlight clip, normalized 0–1"),
    # Linear / Asinh params
    black_pct: float = Query(0.0, description="Black point percentile (0–100)"),
    white_pct: float = Query(100.0, description="White point percentile (0–100)"),
    gamma: float = Query(1.0, description="Gamma / midtones (0.1–10)"),
    asinh_beta: float = Query(0.1, description="Asinh softening factor (0.001–5)"),
    # Per-channel overrides (color, unlinked mode)
    r_shadow: float | None = Query(None),
    r_midtone: float | None = Query(None),
    r_highlight: float | None = Query(None),
    g_shadow: float | None = Query(None),
    g_midtone: float | None = Query(None),
    g_highlight: float | None = Query(None),
    b_shadow: float | None = Query(None),
    b_midtone: float | None = Query(None),
    b_highlight: float | None = Query(None),
) -> Response:
    """Return the image as a PNG with the requested stretch applied."""
    p = _resolve_path(path)

    linked = StretchParams(
        stretch=stretch,
        shadow=shadow,
        midtone=midtone,
        highlight=highlight,
        black_pct=black_pct,
        white_pct=white_pct,
        gamma=gamma,
        asinh_beta=asinh_beta,
    )

    # Build per-channel params only if any channel override was provided
    channel_overrides = [
        r_shadow,
        r_midtone,
        r_highlight,
        g_shadow,
        g_midtone,
        g_highlight,
        b_shadow,
        b_midtone,
        b_highlight,
    ]
    per_channel = None
    if any(v is not None for v in channel_overrides):

        def _ch(sh, mt, hl) -> StretchParams:
            return StretchParams(
                stretch=stretch,
                shadow=sh if sh is not None else shadow,
                midtone=mt if mt is not None else midtone,
                highlight=hl if hl is not None else highlight,
                black_pct=black_pct,
                white_pct=white_pct,
                gamma=gamma,
                asinh_beta=asinh_beta,
            )

        per_channel = [
            _ch(r_shadow, r_midtone, r_highlight),
            _ch(g_shadow, g_midtone, g_highlight),
            _ch(b_shadow, b_midtone, b_highlight),
        ]

    try:
        png_bytes = render_image_png(p, hdu, linked=linked, per_channel=per_channel)
        return Response(content=png_bytes, media_type="image/png")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
