"""Unified image API endpoints — dispatches by file type (FITS, XISF, PNG/JPEG/TIFF)."""

from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from nightcrate.db.session import get_db
from nightcrate.services import fits_io, standard_io, xisf_io
from nightcrate.services.imaging import (
    StretchParams,
    compute_image_stats,
    render_image_png,
)

router = APIRouter(prefix="/api/images", tags=["images"])

FITS_EXTENSIONS = {".fits", ".fit", ".fts"}
XISF_EXTENSIONS = {".xisf"}
STANDARD_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
ALL_EXTENSIONS = FITS_EXTENSIONS | XISF_EXTENSIONS | STANDARD_EXTENSIONS


def _file_type(p: Path) -> str:
    """Return 'fits', 'xisf', or 'standard' based on extension."""
    ext = p.suffix.lower()
    if ext in FITS_EXTENSIONS:
        return "fits"
    if ext in XISF_EXTENSIONS:
        return "xisf"
    if ext in STANDARD_EXTENSIONS:
        return "standard"
    raise HTTPException(
        status_code=400,
        detail=f"Unsupported file type: {ext}. Supported: {', '.join(sorted(ALL_EXTENSIONS))}",
    )


def _resolve_path(path: str) -> tuple[Path, str]:
    """Validate and resolve a file path. Returns (path, file_type)."""
    p = Path(path)
    if not p.is_absolute():
        raise HTTPException(status_code=400, detail="Path must be absolute")
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    return p, _file_type(p)


@router.get("/extensions")
async def get_extensions(
    path: str = Query(..., description="Absolute path to image file"),
) -> list[dict]:
    """List extensions/layers in the file."""
    p, ft = _resolve_path(path)
    try:
        if ft == "fits":
            return fits_io.list_extensions(p)
        if ft == "xisf":
            return xisf_io.list_extensions(p)
        return standard_io.list_extensions(p)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/header")
async def get_header(
    path: str = Query(..., description="Absolute path to image file"),
    hdu: int = Query(0, description="Extension index"),
) -> list[dict]:
    """Return metadata cards for the specified extension."""
    p, ft = _resolve_path(path)
    try:
        if ft == "fits":
            return fits_io.read_header(p, hdu)
        if ft == "xisf":
            return xisf_io.read_header(p, hdu)
        return standard_io.read_header(p)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal processing error") from exc


@router.get("/stats")
async def get_stats(
    path: str = Query(..., description="Absolute path to image file"),
    hdu: int = Query(0, description="Extension index"),
) -> dict:
    """Return per-channel statistics and auto-computed STF defaults.

    Only applicable to FITS and XISF files. Returns 404 for standard images.
    """
    p, ft = _resolve_path(path)
    if ft == "standard":
        raise HTTPException(
            status_code=404, detail="Stats not available for standard image formats"
        )
    try:
        if ft == "fits":
            data = fits_io.load_image_data(p, hdu)
        else:
            data = xisf_io.load_image_data(p, hdu)
        stats = compute_image_stats(data)
        return asdict(stats)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal processing error") from exc


@router.get("/image")
async def get_image(
    path: str = Query(..., description="Absolute path to image file"),
    hdu: int = Query(0, description="Extension index"),
    stretch: str = Query("stf", description="Stretch type: stf | linear"),
    shadow: float = Query(0.0, description="Shadow clip, normalized 0–1"),
    midtone: float = Query(0.5, description="Midtones balance 0–1"),
    highlight: float = Query(1.0, description="Highlight clip, normalized 0–1"),
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
    """Return the image as a PNG. Stretch is applied for FITS/XISF only."""
    p, ft = _resolve_path(path)

    try:
        if ft == "standard":
            png_bytes = standard_io.load_image_bytes(p)
            return Response(content=png_bytes, media_type="image/png")

        # FITS or XISF — load normalized data and apply stretch
        if ft == "fits":
            data = fits_io.load_image_data(p, hdu)
        else:
            data = xisf_io.load_image_data(p, hdu)

        linked = StretchParams(stretch=stretch, shadow=shadow, midtone=midtone, highlight=highlight)

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
                )

            per_channel = [
                _ch(r_shadow, r_midtone, r_highlight),
                _ch(g_shadow, g_midtone, g_highlight),
                _ch(b_shadow, b_midtone, b_highlight),
            ]

        png_bytes = render_image_png(data, linked=linked, per_channel=per_channel)
        return Response(content=png_bytes, media_type="image/png")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal processing error") from exc


# ── Recent files ─────────────────────────────────────────────────────────────

MAX_RECENT = 100


@router.post("/recent")
async def add_recent(path: str = Query(..., description="Path to record")) -> dict:
    """Record a file open. Upserts the path and prunes beyond MAX_RECENT."""
    async with get_db() as conn:
        await conn.execute(
            """INSERT INTO recent_files (path, opened_at) VALUES (?, datetime('now'))
               ON CONFLICT(path) DO UPDATE SET opened_at = datetime('now')""",
            (path,),
        )
        # Prune old entries
        await conn.execute(
            """DELETE FROM recent_files WHERE id NOT IN (
                   SELECT id FROM recent_files ORDER BY opened_at DESC LIMIT ?
               )""",
            (MAX_RECENT,),
        )
        await conn.commit()
    return {"ok": True}


@router.get("/recent")
async def get_recent() -> list[dict]:
    """Return recent files ordered most recent first. Excludes files that no longer exist."""
    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT path, opened_at FROM recent_files ORDER BY opened_at DESC LIMIT ?",
            (MAX_RECENT,),
        )
        rows = await cursor.fetchall()

    result = []
    stale_paths = []
    for row in rows:
        p = Path(row[0])
        if p.exists():
            result.append({"path": row[0], "name": p.name, "opened_at": row[1]})
        else:
            stale_paths.append(row[0])

    # Clean up stale entries in the background
    if stale_paths:
        async with get_db() as conn:
            await conn.executemany(
                "DELETE FROM recent_files WHERE path = ?",
                [(p,) for p in stale_paths],
            )
            await conn.commit()

    return result
