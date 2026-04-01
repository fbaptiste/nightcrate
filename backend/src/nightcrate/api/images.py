"""Unified image API endpoints — dispatches by file type (FITS, XISF, PNG/JPEG/TIFF)."""

from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from nightcrate.db.session import get_db
from nightcrate.services import fits_io, pxiproject_io, standard_io, xisf_io
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
    """Return 'fits', 'xisf', 'float_tiff', or 'standard' based on extension and content."""
    ext = p.suffix.lower()
    if ext in FITS_EXTENSIONS:
        return "fits"
    if ext in XISF_EXTENSIONS:
        return "xisf"
    if ext in STANDARD_EXTENSIONS:
        if ext in (".tif", ".tiff") and standard_io.is_float_tiff(p):
            return "float_tiff"
        return "standard"
    raise HTTPException(
        status_code=400,
        detail=f"Unsupported file type: {ext}. Supported: {', '.join(sorted(ALL_EXTENSIONS))}",
    )


def _resolve_path(path: str) -> tuple[Path, str, int]:
    """Validate and resolve a file path.

    Returns (resolved_path, file_type, image_index).
    image_index is only meaningful for pxiproject virtual paths; 0 otherwise.
    """
    if "::" in path:
        parts = path.rsplit("::", 1)
        try:
            project_dir, idx = Path(parts[0]), int(parts[1])
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid virtual path: {path}")
        if not project_dir.is_dir():
            raise HTTPException(status_code=404, detail=f"Project not found: {project_dir}")
        return project_dir, "pxiproject", idx

    p = Path(path)
    if not p.is_absolute():
        raise HTTPException(status_code=400, detail="Path must be absolute")
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    return p, _file_type(p), 0


def _load_image_data(p: Path, ft: str, idx: int, hdu: int):
    """Load normalized image data for any supported file type."""
    if ft == "pxiproject":
        return pxiproject_io.load_image_data(p, idx)
    if ft == "fits":
        return fits_io.load_image_data(p, hdu)
    if ft == "float_tiff":
        return standard_io.load_image_data(p)
    return xisf_io.load_image_data(p, hdu)


@router.get("/extensions")
async def get_extensions(
    path: str = Query(..., description="Absolute path to image file"),
) -> list[dict]:
    """List extensions/layers in the file."""
    p, ft, idx = _resolve_path(path)
    try:
        if ft == "pxiproject":
            return pxiproject_io.list_extensions(p, idx)
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
    p, ft, idx = _resolve_path(path)
    try:
        if ft == "pxiproject":
            return pxiproject_io.read_header(p, idx)
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
    """Return per-channel statistics and auto-computed stretch defaults.

    Only applicable to FITS, XISF, float TIFF, and pxiproject. Returns 404 for standard images.
    """
    p, ft, idx = _resolve_path(path)
    if ft == "standard":
        raise HTTPException(
            status_code=404, detail="Stats not available for standard image formats"
        )
    try:
        data = _load_image_data(p, ft, idx, hdu)
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
    p, ft, idx = _resolve_path(path)

    try:
        if ft == "standard":
            png_bytes = standard_io.load_image_bytes(p)
            return Response(content=png_bytes, media_type="image/png")

        data = _load_image_data(p, ft, idx, hdu)

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
        await conn.execute(
            """DELETE FROM recent_files WHERE id NOT IN (
                   SELECT id FROM recent_files ORDER BY opened_at DESC LIMIT ?
               )""",
            (MAX_RECENT,),
        )
        await conn.commit()
    return {"ok": True}


def _resolve_recent_name(raw_path: str, project_cache: dict[str, list[dict]]) -> str | None:
    """Resolve display name for a recent file path. Returns None if stale."""
    if "::" not in raw_path:
        p = Path(raw_path)
        return p.name if p.exists() else None

    project_dir_str, idx_str = raw_path.rsplit("::", 1)
    project_dir = Path(project_dir_str)
    if not project_dir.is_dir():
        return None

    if project_dir_str not in project_cache:
        try:
            project_cache[project_dir_str] = pxiproject_io.list_project_images(project_dir)
        except Exception:
            project_cache[project_dir_str] = []

    images = project_cache[project_dir_str]
    idx = int(idx_str) if idx_str.isdigit() else -1
    img_name = images[idx]["name"] if 0 <= idx < len(images) else idx_str
    return f"{project_dir.name} / {img_name}"


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
    project_cache: dict[str, list[dict]] = {}

    for row in rows:
        raw_path = row[0]
        name = _resolve_recent_name(raw_path, project_cache)
        if name is not None:
            result.append({"path": raw_path, "name": name, "opened_at": row[1]})
        else:
            stale_paths.append(raw_path)

    if stale_paths:
        async with get_db() as conn:
            await conn.executemany(
                "DELETE FROM recent_files WHERE path = ?",
                [(p,) for p in stale_paths],
            )
            await conn.commit()

    return result
