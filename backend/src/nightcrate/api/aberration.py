"""Aberration inspector API endpoints — star detection, zone aggregation, crop, cache."""

import json
from pathlib import Path
from typing import BinaryIO

import numpy as np
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from nightcrate.db.session import get_db
from nightcrate.services.aberration import (
    AnalysisResult,
    DetectionSettings,
    SampleGridResult,
    StarMeasurement,
    compute_sample_grid,
    detect_stars,
)
from nightcrate.services.imaging import StretchParams, compute_image_stats, render_image_png
from nightcrate.services.path_resolver import resolve_path
from nightcrate.services.pixel_loader import grey_of, load_resolved

router = APIRouter(prefix="/api/aberration", tags=["Aberration Inspector"])


# ── Helpers ───────────────────────────────────────────────────────────────────


def _validate_and_resolve(file_path: str) -> tuple[Path | BinaryIO, str, int]:
    """Validate and resolve path, returning (source, file_type).

    Handles regular paths and archive virtual paths (archive.zip::entry).
    """
    source, ft, index, _ck = resolve_path(file_path)
    return source, ft, index


def _settings_key(settings: DetectionSettings) -> str:
    """Produce a stable JSON key from detection settings."""
    return json.dumps({"measurement_version": 2, **settings.model_dump()}, sort_keys=True)


def _legacy_settings_key(settings: DetectionSettings) -> str:
    """Return the exact settings key written through v0.54.1."""
    return json.dumps(settings.model_dump(), sort_keys=True)


def _load_mono_data(
    source: Path | BinaryIO,
    ft: str,
    hdu: int,
    index: int = 0,
) -> tuple[np.ndarray, int, tuple[int, int]]:
    """Load image data and convert color to luminance if needed.

    Returns a 2D float64 array normalized to [0, 1].
    """
    image = load_resolved(source, ft, index, hdu)
    mono, block_size = grey_of(image)
    return mono.astype(np.float64), block_size, (image.height, image.width)


async def _get_cached_analysis(
    file_path: str, hdu: int, settings_json: str
) -> AnalysisResult | None:
    """Load a cached analysis from the database, or return None if not found."""
    async with get_db() as conn:
        cursor = await conn.execute(
            """SELECT id, image_width, image_height, star_count,
                      median_fwhm, median_hfr, median_eccentricity, settings_json
               FROM aberration_analysis
               WHERE file_path = ? AND hdu = ? AND settings_json = ?""",
            (file_path, hdu, settings_json),
        )
        row = await cursor.fetchone()
        if row is None:
            return None

        analysis_id = row[0]

        star_cursor = await conn.execute(
            """SELECT x, y, fwhm, hfr, eccentricity, elongation_angle_deg,
                      peak_adu, flux, snr, semi_major, semi_minor
               FROM aberration_stars
               WHERE analysis_id = ?
               ORDER BY id""",
            (analysis_id,),
        )
        star_rows = await star_cursor.fetchall()

    stars = [
        StarMeasurement(
            x=r[0],
            y=r[1],
            fwhm=r[2],
            hfr=r[3],
            eccentricity=r[4],
            elongation_angle_deg=r[5],
            peak_adu=r[6],
            flux=r[7],
            snr=r[8],
            semi_major=r[9],
            semi_minor=r[10],
        )
        for r in star_rows
    ]

    settings_data = json.loads(row[7])
    settings_data.pop("measurement_version", None)

    return AnalysisResult(
        stars=stars,
        star_count=row[3],
        image_width=row[1],
        image_height=row[2],
        median_fwhm=row[4],
        median_hfr=row[5],
        median_eccentricity=row[6],
        settings=DetectionSettings(**settings_data),
    )


async def _save_analysis(
    file_path: str, hdu: int, settings_json: str, result: AnalysisResult
) -> None:
    """Persist an analysis result to the database."""
    async with get_db() as conn:
        await conn.execute(
            """INSERT OR REPLACE INTO aberration_analysis
               (file_path, hdu, settings_json, image_width, image_height,
                star_count, median_fwhm, median_hfr, median_eccentricity)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                file_path,
                hdu,
                settings_json,
                result.image_width,
                result.image_height,
                result.star_count,
                result.median_fwhm,
                result.median_hfr,
                result.median_eccentricity,
            ),
        )
        # Retrieve the inserted/replaced id
        cursor = await conn.execute(
            """SELECT id FROM aberration_analysis
               WHERE file_path = ? AND hdu = ? AND settings_json = ?""",
            (file_path, hdu, settings_json),
        )
        row = await cursor.fetchone()
        analysis_id = row[0]

        # Delete old stars for this analysis before re-inserting
        await conn.execute(
            "DELETE FROM aberration_stars WHERE analysis_id = ?",
            (analysis_id,),
        )

        if result.stars:
            await conn.executemany(
                """INSERT INTO aberration_stars
                   (analysis_id, x, y, fwhm, hfr, eccentricity, elongation_angle_deg,
                    peak_adu, flux, snr, semi_major, semi_minor)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        analysis_id,
                        s.x,
                        s.y,
                        s.fwhm,
                        s.hfr,
                        s.eccentricity,
                        s.elongation_angle_deg,
                        s.peak_adu,
                        s.flux,
                        s.snr,
                        s.semi_major,
                        s.semi_minor,
                    )
                    for s in result.stars
                ],
            )

        await conn.commit()


async def _run_analysis(file_path: str, hdu: int, settings: DetectionSettings) -> AnalysisResult:
    """Run analysis with caching. Returns cached result if available."""
    settings_json = _settings_key(settings)

    cached = await _get_cached_analysis(file_path, hdu, settings_json)
    if cached is not None:
        return cached

    legacy_settings_json = _legacy_settings_key(settings)
    try:
        source, ft, index = _validate_and_resolve(file_path)
    except Exception:
        cached = await _get_cached_analysis(file_path, hdu, legacy_settings_json)
        if cached is not None:
            return cached
        raise

    try:
        mono, block_size, original_shape = _load_mono_data(source, ft, hdu, index)
    except HTTPException:
        cached = await _get_cached_analysis(file_path, hdu, legacy_settings_json)
        if cached is not None:
            return cached
        raise
    except Exception as exc:
        cached = await _get_cached_analysis(file_path, hdu, legacy_settings_json)
        if cached is not None:
            return cached
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        result = detect_stars(
            mono,
            settings,
            block_size=block_size,
            original_shape=original_shape,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Star detection failed: {exc}") from exc

    await _save_analysis(file_path, hdu, settings_json, result)
    return result


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/analyze")
async def analyze(
    path: str = Query(..., description="Absolute path to image file"),
    hdu: int = Query(0, description="Extension index"),
    min_snr: float = Query(10.0, description="Minimum star SNR"),
    min_fwhm: float = Query(3.0, description="Minimum FWHM (px)"),
    max_fwhm: float = Query(30.0, description="Maximum FWHM (px)"),
) -> AnalysisResult:
    """Detect stars and return per-star measurements. Results are cached in the DB."""
    settings = DetectionSettings(
        min_star_snr=min_snr,
        min_star_fwhm_px=min_fwhm,
        max_star_fwhm_px=max_fwhm,
    )
    return await _run_analysis(path, hdu, settings)


@router.post("/samples")
async def samples(
    path: str = Query(..., description="Absolute path to image file"),
    hdu: int = Query(0, description="Extension index"),
    samples_across: int = Query(5, ge=3, le=9, description="Sample squares across width"),
    min_snr: float = Query(10.0, description="Minimum star SNR"),
    min_fwhm: float = Query(3.0, description="Minimum FWHM (px)"),
    max_fwhm: float = Query(30.0, description="Maximum FWHM (px)"),
) -> SampleGridResult:
    """Return evenly-spaced sample squares with aggregated star metrics."""
    settings = DetectionSettings(
        min_star_snr=min_snr,
        min_star_fwhm_px=min_fwhm,
        max_star_fwhm_px=max_fwhm,
    )
    analysis = await _run_analysis(path, hdu, settings)
    return compute_sample_grid(analysis, samples_across=samples_across)


@router.get("/crop")
async def get_crop(
    path: str = Query(..., description="Absolute path to image file"),
    hdu: int = Query(0, description="Extension index"),
    x0: int = Query(..., description="Left edge (pixels)"),
    y0: int = Query(..., description="Top edge (pixels)"),
    x1: int = Query(..., description="Right edge (pixels)"),
    y1: int = Query(..., description="Bottom edge (pixels)"),
) -> Response:
    """Return an auto-stretched PNG crop of the specified region."""
    source, ft, index = _validate_and_resolve(path)

    try:
        mono, block_size, _original_shape = _load_mono_data(source, ft, hdu, index)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    h, w = mono.shape
    cx0 = max(0, min(x0 // block_size, w))
    cy0 = max(0, min(y0 // block_size, h))
    cx1 = max(0, min(int(np.ceil(x1 / block_size)), w))
    cy1 = max(0, min(int(np.ceil(y1 / block_size)), h))

    crop = mono[cy0:cy1, cx0:cx1]

    if crop.size == 0:
        raise HTTPException(status_code=400, detail="Crop region is empty")

    try:
        stats = compute_image_stats(crop)
        stf = stats.channels[0].stf
        stretch = StretchParams(
            stretch="stf",
            shadow=stf.shadow,
            midtone=stf.midtone,
            highlight=stf.highlight,
        )
        png_bytes = render_image_png(crop, linked=stretch)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Render failed") from exc

    return Response(content=png_bytes, media_type="image/png")


@router.get("/cache/size")
async def cache_size() -> dict:
    """Return the aberration cache size in bytes (approximate)."""
    async with get_db() as conn:
        # Try dbstat virtual table first (available in most SQLite builds)
        try:
            cursor = await conn.execute(
                """SELECT COALESCE(SUM(pgsize), 0)
                   FROM dbstat
                   WHERE name IN ('aberration_analysis', 'aberration_stars')"""
            )
            row = await cursor.fetchone()
            size_bytes = int(row[0]) if row else 0
            return {"bytes": size_bytes}
        except Exception:  # nosec B110 - dbstat is optional; fall through to row-count estimate
            pass

        # Fallback: row count estimate (~100 bytes per star)
        cursor = await conn.execute("SELECT COUNT(*) FROM aberration_analysis")
        analysis_count = (await cursor.fetchone())[0]
        cursor = await conn.execute("SELECT COUNT(*) FROM aberration_stars")
        star_count = (await cursor.fetchone())[0]
        estimated = (analysis_count * 200) + (star_count * 100)
        return {"bytes": estimated}


@router.delete("/cache")
async def clear_cache() -> dict:
    """Delete all cached aberration data."""
    async with get_db() as conn:
        # Stars are deleted via CASCADE when analysis rows are removed
        cursor = await conn.execute("DELETE FROM aberration_analysis")
        deleted = cursor.rowcount
        await conn.commit()
    return {"ok": True, "deleted_analyses": deleted}
