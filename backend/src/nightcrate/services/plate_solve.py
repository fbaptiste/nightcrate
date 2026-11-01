"""Plate solving via ASTAP subprocess invocation.

Pure service module — no FastAPI, no DB access. Handles ASTAP binary
resolution, subprocess execution, .ini output parsing, and result
computation. Temp file management for virtual-path images (archive,
pxiproject) is handled internally.
"""

import asyncio
import io
import logging
import math
import os
import shutil
import sys
import tempfile
import threading
import time
from collections.abc import Awaitable
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Literal
from uuid import uuid4

import numpy as np
from astropy.io import fits as astro_fits

from nightcrate.services import (
    fits_io,
    pxiproject_io,
    solve_operations,
    standard_io,
    xisf_io,
)
from nightcrate.services.coordinate_format import format_dec_dms, format_ra_hms
from nightcrate.services.image_annotation_models import WcsParams
from nightcrate.services.image_annotations import detect_wcs_from_cards
from nightcrate.services.path_resolver import (
    FITS_EXTENSIONS,
    STANDARD_EXTENSIONS,
)
from nightcrate.services.path_resolver import (
    resolve_path as _resolve_path_raw,
)
from nightcrate.services.plate_solve_models import AttemptOutcome, PlateSolveResult, SolveAttempt
from nightcrate.services.star_catalog import handles

logger = logging.getLogger("nightcrate")

# Kept only for older direct service tests; API progress is operation-scoped.


async def _finish_awaitable[T](awaitable: Awaitable[T]) -> tuple[T, bool]:
    """Finish an already-started worker despite cancellation of its waiter."""
    task = asyncio.ensure_future(awaitable)
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    return task.result(), cancelled


def _resolve_path(path: str) -> tuple[Path | BinaryIO, str, int, tuple | None]:
    """Wrap path_resolver.resolve_path, converting HTTPException to ValueError."""
    try:
        return _resolve_path_raw(path)
    except Exception as exc:
        if type(exc).__name__ == "HTTPException":
            raise ValueError(getattr(exc, "detail", str(exc))) from None
        raise


def _read_astap_source(image_path: str, hdu: int):
    """Resolve and read the source metadata in one blocking worker."""
    source, file_type, image_index, _cache_key = _resolve_path(image_path)
    raw_bytes: bytes | None = None
    if not isinstance(source, Path):
        raw_bytes = source.read()

    header_source = io.BytesIO(raw_bytes) if raw_bytes is not None else source
    cards = read_header_cards(header_source, file_type, image_index, hdu)
    return source if isinstance(source, Path) else None, file_type, image_index, raw_bytes, cards


_solve_process: asyncio.subprocess.Process | None = None
_astap_stop: threading.Event | None = None
_astap_task: asyncio.Task[PlateSolveResult] | None = None
_native_cancel: threading.Event | None = None
_native_task: asyncio.Task[PlateSolveResult] | None = None


class _NativeProgressReporter:
    """Legacy text adapter retained for direct native-solver consumers."""

    def __init__(self, report) -> None:
        self._report = report
        self._step = None

    def plan(self, steps) -> None:
        del steps

    def start(self, attempt: SolveAttempt) -> None:
        self._step = attempt.step
        if attempt.step == "load":
            self._report("Loading image")
        elif attempt.step in {"near_index", "near_catalog"}:
            self._report("Searching near the supplied position")
        elif attempt.step in {"blind_known_scale", "blind_unknown_scale"}:
            self._report("Blind solve")

    def searched(self, layers: list[str], ranges: list[str]) -> None:
        del layers
        if self._step not in {"near_index", "blind_known_scale", "blind_unknown_scale"}:
            return
        labels = [range_id.replace("-", "°–", 1) + "°" for range_id in ranges]
        prefix = (
            "Searching near the supplied position: fields"
            if self._step == "near_index"
            else "Blind solve: fields"
        )
        self._report(f"{prefix} {', '.join(labels)}")

    def set_sources(
        self,
        position_source: Literal["request", "header", "none"],
        scale_source: Literal["request", "header", "none"],
    ) -> None:
        del position_source, scale_source

    def finish(self, outcome: AttemptOutcome, *, detail: str | None = None) -> None:
        del outcome
        if self._step == "load" and detail and detail.endswith(" stars found"):
            self._report(detail.removesuffix(" found") + " detected")
        self._step = None


class SolveSlotBusy(solve_operations.SolveBusy):
    """The single plate-solving slot is already occupied."""


@asynccontextmanager
async def solve_slot():
    """Claim the solve slot immediately, or fail without yielding."""
    try:
        async with solve_operations.immediate_slot():
            yield
    except solve_operations.SolveBusy as exc:
        raise SolveSlotBusy(str(exc)) from exc


@asynccontextmanager
async def solve_slot_wait():
    """Wait for and hold the solve slot for a short publication step."""
    async with solve_operations.waiting_slot():
        yield


_KEY_VAL_ERRORS = (KeyError, ValueError)
_HEADER_WRITE_ERRORS = (ValueError, TypeError)

_EXIT_CODE_MESSAGES = {
    1: "No solution found.",
    2: "Not enough stars detected. Try a different image or check for clouds/focus issues.",
    16: "Error reading image file.",
    32: "Star database not found. Ensure ASTAP's star database is installed.",
    33: "Error reading star database.",
    34: "Error updating input file.",
}


def resolve_astap_binary(path_str: str) -> Path:
    """Resolve an ASTAP executable path, handling macOS .app bundles.

    If *path_str* points to a ``.app`` directory, looks inside
    ``Contents/MacOS/`` for the ``astap`` binary. Otherwise validates
    that the path exists and is executable.

    Raises ``ValueError`` on any failure.
    """
    p = Path(path_str)

    if p.suffix.lower() == ".app" and p.is_dir():
        macos_dir = p / "Contents" / "MacOS"
        if not macos_dir.is_dir():
            raise ValueError(f"Invalid .app bundle: {p} (no Contents/MacOS)")
        for name in ("astap", "ASTAP"):
            candidate = macos_dir / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return candidate
        candidates = [
            f for f in macos_dir.iterdir() if f.is_file() and os.access(f, os.X_OK) and not f.suffix
        ]
        if len(candidates) == 1:
            return candidates[0]
        raise ValueError(
            f"Could not locate ASTAP executable in {macos_dir}. "
            f"Found: {[f.name for f in macos_dir.iterdir() if f.is_file()]}"
        )

    if not p.is_file():
        raise ValueError(f"ASTAP executable not found: {p}")
    if not os.access(p, os.X_OK):
        raise ValueError(f"ASTAP path is not executable: {p}")
    return p


def validate_astap_path(path_str: str) -> dict:
    """Validate an ASTAP path and return status dict for the API."""
    try:
        resolved = resolve_astap_binary(path_str)
        return {"valid": True, "resolved_path": str(resolved), "error": None}
    except ValueError as exc:
        return {"valid": False, "resolved_path": None, "error": str(exc)}


def read_header_cards(
    source: Path | BinaryIO,
    file_type: str,
    image_index: int,
    hdu: int,
) -> list[dict]:
    """Read header cards from any supported image source."""
    if file_type == "pxiproject":
        return pxiproject_io.read_header(source, image_index)
    if file_type == "fits":
        return fits_io.read_header(source, hdu)
    if file_type == "xisf":
        return xisf_io.read_header(source, hdu)
    return standard_io.read_header(source)


def read_wcs_params(
    source: Path | BinaryIO,
    file_type: str,
    image_index: int,
    hdu: int,
) -> WcsParams | None:
    """Read WCS parameters with format-specific row-order handling."""
    if file_type == "xisf":
        return xisf_io.read_wcs_params(source, hdu)
    return detect_wcs_from_cards(read_header_cards(source, file_type, image_index, hdu))


def cards_to_dict(cards: list[dict]) -> dict[str, str]:
    """Convert header card list to a {KEY: value} dict (last occurrence wins)."""
    raw: dict[str, str] = {}
    for card in cards:
        if card["key"]:
            raw[card["key"].upper()] = card["value"]
    return raw


def _extract_hints(cards: list[dict]) -> dict:
    """Extract RA, Dec, and FOV hints from header cards.

    Returns a dict with optional keys ``ra_hours``, ``spd``, ``fov_deg``.
    ASTAP uses SPD (south pole distance) = dec + 90.
    """
    raw = cards_to_dict(cards)

    hints: dict[str, float] = {}

    ra_deg = _parse_ra(raw)
    dec_deg = _parse_dec(raw)

    if ra_deg is not None:
        hints["ra_hours"] = ra_deg / 15.0
    if dec_deg is not None:
        hints["spd"] = dec_deg + 90.0

    fov = _estimate_fov(raw)
    if fov is not None:
        hints["fov_deg"] = fov

    return hints


def _parse_ra(raw: dict[str, str]) -> float | None:
    """Extract RA in degrees from header keywords."""
    for key in ("RA", "OBJCTRA", "CRVAL1"):
        val = raw.get(key)
        if val is None:
            continue
        try:
            return float(val)
        except ValueError:
            pass
        parsed = _hms_to_deg(val)
        if parsed is not None:
            return parsed
    return None


def _parse_dec(raw: dict[str, str]) -> float | None:
    """Extract Dec in degrees from header keywords."""
    for key in ("DEC", "OBJCTDEC", "CRVAL2"):
        val = raw.get(key)
        if val is None:
            continue
        try:
            return float(val)
        except ValueError:
            pass
        parsed = _dms_to_deg(val)
        if parsed is not None:
            return parsed
    return None


def _hms_to_deg(s: str) -> float | None:
    """Parse an HMS string like '05 34 31.94' or '05:34:31.94' to degrees."""
    parts = s.replace(":", " ").split()
    if len(parts) != 3:
        return None
    try:
        h, m, sec = float(parts[0]), float(parts[1]), float(parts[2])
        return (h + m / 60.0 + sec / 3600.0) * 15.0
    except ValueError:
        return None


def _dms_to_deg(s: str) -> float | None:
    """Parse a DMS string like '+22 00 52.0' or '-22:00:52.0' to degrees."""
    parts = s.replace(":", " ").split()
    if len(parts) != 3:
        return None
    try:
        d, m, sec = float(parts[0]), float(parts[1]), float(parts[2])
        sign = -1 if d < 0 or s.lstrip().startswith("-") else 1
        return sign * (abs(d) + m / 60.0 + sec / 3600.0)
    except ValueError:
        return None


def _estimate_fov(raw: dict[str, str]) -> float | None:
    """Estimate vertical FOV in degrees from focal length + pixel size + NAXIS2."""
    try:
        focal_mm = float(raw["FOCALLEN"])
        pixel_um = float(raw.get("YPIXSZ") or raw["XPIXSZ"])
        naxis2 = int(raw["NAXIS2"])
    except _KEY_VAL_ERRORS:
        return None
    if focal_mm <= 0:
        return None
    plate_scale_arcsec = (pixel_um / focal_mm) * 206.265
    return plate_scale_arcsec * naxis2 / 3600.0


def _prepare_image_file(
    source: Path | BinaryIO,
    file_type: str,
    image_index: int,
    hdu: int,
    temp_dir: Path,
    header_keywords: dict[str, str] | None = None,
) -> Path:
    """Ensure a real filesystem path suitable for ASTAP.

    For regular files in ASTAP-supported formats, returns the path as-is.
    For virtual paths (archive, pxiproject) or unsupported formats
    (compressed XISF), writes a temporary FITS file and returns its path.
    """
    if isinstance(source, Path):
        ext = source.suffix.lower()
        if ext in FITS_EXTENSIONS and hdu > 0:
            data = fits_io.load_image_data(source, hdu)
            return _write_temp_fits(data, temp_dir, header_keywords)
        if ext in FITS_EXTENSIONS | STANDARD_EXTENSIONS:
            return source
        if ext == ".xisf":
            data = xisf_io.load_image_data(source, hdu)
            return _write_temp_fits(data, temp_dir, header_keywords)
        if file_type == "pxiproject":
            data = pxiproject_io.load_image_data(source, image_index)
            return _write_temp_fits(data, temp_dir, header_keywords)
        return source

    if file_type == "fits" and hdu == 0:
        temp_path = temp_dir / "solve_input.fits"
        temp_path.write_bytes(source.read())
        return temp_path

    data = _load_data_from_buf(source, file_type, hdu)
    return _write_temp_fits(data, temp_dir, header_keywords)


def _load_data_from_buf(buf: BinaryIO, file_type: str, hdu: int) -> np.ndarray:
    """Load image data from a BytesIO buffer."""
    if file_type == "xisf":
        return xisf_io.load_image_data(buf, hdu)
    if file_type in ("float_tiff", "standard"):
        if file_type == "float_tiff":
            return standard_io.load_image_data(buf)
        return standard_io.load_image_as_array(buf)
    return fits_io.load_image_data(buf, hdu)


_PASSTHROUGH_KEYS = (
    "FOCALLEN",
    "XPIXSZ",
    "YPIXSZ",
    "INSTRUME",
    "TELESCOP",
    "RA",
    "DEC",
    "OBJCTRA",
    "OBJCTDEC",
    "CRVAL1",
    "CRVAL2",
    "EXPTIME",
    "GAIN",
    "CCD-TEMP",
    "FILTER",
    "DATE-OBS",
    "XBINNING",
    "YBINNING",
    "IMAGETYP",
)


def _write_temp_fits(
    data: np.ndarray,
    temp_dir: Path,
    header_keywords: dict[str, str] | None = None,
) -> Path:
    """Write a numpy array as a temporary FITS file for ASTAP.

    If data is float [0,1] (from XISF/standard normalization), scale to
    uint16 so ASTAP's star detection works with proper dynamic range.
    When *header_keywords* is provided, copies ASTAP-relevant keywords
    (focal length, pixel size, coordinates) into the FITS header so ASTAP
    can determine the correct binning and FOV.
    """
    temp_path = temp_dir / "solve_input.fits"
    if data.dtype in (np.float32, np.float64) and data.max() <= 1.0:
        write_data = (data * 65535).astype(np.uint16)
    else:
        write_data = data
    hdu_obj = astro_fits.PrimaryHDU(write_data)
    if header_keywords:
        for key in _PASSTHROUGH_KEYS:
            val = header_keywords.get(key)
            if val is not None:
                try:
                    hdu_obj.header[key] = _coerce_header_value(val)
                except _HEADER_WRITE_ERRORS:
                    pass
    hdu_obj.writeto(temp_path, overwrite=True)
    return temp_path


def _coerce_header_value(val: str) -> int | float | str:
    """Try to store numeric header values as numbers, not strings."""
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    return val


def _build_astap_args(
    astap_binary: Path,
    image_path: Path,
    output_base: Path,
    mode: str,
    hints: dict,
    ra_hint: float | None,
    dec_hint: float | None,
    fov_hint: float | None,
) -> list[str]:
    """Build the ASTAP command-line argument list."""
    args = [str(astap_binary), "-f", str(image_path), "-z", "0", "-o", str(output_base)]

    if mode == "blind":
        args.extend(["-r", "180"])
        if fov_hint is not None:
            args.extend(["-fov", str(fov_hint)])
    elif mode == "near":
        args.extend(["-r", "30"])
        if ra_hint is not None:
            args.extend(["-ra", str(ra_hint / 15.0)])
        if dec_hint is not None:
            args.extend(["-spd", str(dec_hint + 90.0)])
        if fov_hint is not None:
            args.extend(["-fov", str(fov_hint)])
    else:
        has_ra = ra_hint is not None or "ra_hours" in hints
        has_dec = dec_hint is not None or "spd" in hints
        if has_ra and has_dec:
            args.extend(["-r", "30"])
            if ra_hint is not None:
                args.extend(["-ra", str(ra_hint / 15.0)])
            elif "ra_hours" in hints:
                args.extend(["-ra", str(hints["ra_hours"])])
            if dec_hint is not None:
                args.extend(["-spd", str(dec_hint + 90.0)])
            elif "spd" in hints:
                args.extend(["-spd", str(hints["spd"])])
        else:
            args.extend(["-r", "180"])

        fov_val = fov_hint if fov_hint is not None else hints.get("fov_deg")
        if fov_val is not None:
            args.extend(["-fov", str(fov_val)])

    return args


def _parse_astap_ini(ini_path: Path) -> dict[str, str]:
    """Parse ASTAP's output .ini file (flat key=value, no section headers)."""
    result: dict[str, str] = {}
    for line in ini_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.split("//")[0].strip()
        result[key.strip()] = value
    return result


def _compute_results(
    ini_data: dict[str, str],
    image_width: int | None,
    image_height: int | None,
    flip_rows: bool = False,
) -> PlateSolveResult:
    """Derive user-facing values from raw ASTAP .ini data."""
    solved = ini_data.get("PLTSOLVD", "F").strip().upper() == "T"

    if not solved:
        return PlateSolveResult(
            solved=False,
            error_message=ini_data.get("ERROR"),
            warning=ini_data.get("WARNING"),
            image_width=image_width,
            image_height=image_height,
        )

    ra_deg = _safe_float(ini_data.get("CRVAL1"))
    dec_deg = _safe_float(ini_data.get("CRVAL2"))

    cd1_1 = _safe_float(ini_data.get("CD1_1"))
    cd1_2 = _safe_float(ini_data.get("CD1_2"))
    cd2_1 = _safe_float(ini_data.get("CD2_1"))
    cd2_2 = _safe_float(ini_data.get("CD2_2"))
    crpix1 = _safe_float(ini_data.get("CRPIX1"))
    crpix2 = _safe_float(ini_data.get("CRPIX2"))
    crota2 = _safe_float(ini_data.get("CROTA2"))

    if flip_rows:
        if crpix2 is not None and image_height is not None:
            crpix2 = image_height + 1 - crpix2
        if cd1_2 is not None:
            cd1_2 = -cd1_2
        if cd2_2 is not None:
            cd2_2 = -cd2_2

    pixel_scale: float | None = None
    if cd2_1 is not None and cd2_2 is not None:
        pixel_scale = pixel_scale_from_cd(cd2_1, cd2_2)

    if not validate_wcs(
        ra_deg,
        dec_deg,
        crpix1,
        crpix2,
        cd1_1,
        cd1_2,
        cd2_1,
        cd2_2,
        pixel_scale,
        image_width,
        image_height,
    ):
        return PlateSolveResult(
            solved=False,
            error_message="ASTAP returned an incomplete solution.",
            image_width=image_width,
            image_height=image_height,
        )

    rotation: float | None = crota2
    if (flip_rows or rotation is None) and cd1_2 is not None and cd2_2 is not None:
        rotation = rotation_from_cd(cd1_2, cd2_2)

    fov_w: float | None = None
    fov_h: float | None = None
    if pixel_scale is not None:
        if image_width is not None:
            fov_w = pixel_scale * image_width / 60.0
        if image_height is not None:
            fov_h = pixel_scale * image_height / 60.0

    return PlateSolveResult(
        solved=True,
        ra_deg=_round(ra_deg, 6),
        dec_deg=_round(dec_deg, 6),
        ra_hms=format_ra_hms(ra_deg) if ra_deg is not None else None,
        dec_dms=format_dec_dms(dec_deg) if dec_deg is not None else None,
        pixel_scale_arcsec=_round(pixel_scale, 3),
        rotation_deg=_round(rotation, 3),
        fov_width_arcmin=_round(fov_w, 2),
        fov_height_arcmin=_round(fov_h, 2),
        image_width=image_width,
        image_height=image_height,
        cd1_1=cd1_1,
        cd1_2=cd1_2,
        cd2_1=cd2_1,
        cd2_2=cd2_2,
        crpix1=crpix1,
        crpix2=crpix2,
        warning=ini_data.get("WARNING"),
    )


def validate_wcs(
    ra_deg: float | None,
    dec_deg: float | None,
    crpix1: float | None,
    crpix2: float | None,
    cd1_1: float | None,
    cd1_2: float | None,
    cd2_1: float | None,
    cd2_2: float | None,
    pixel_scale: float | None,
    image_width: int | None,
    image_height: int | None,
) -> bool:
    """Return whether ASTAP supplied the complete, finite WCS contract."""
    values = (ra_deg, dec_deg, crpix1, crpix2, cd1_1, cd1_2, cd2_1, cd2_2, pixel_scale)
    if any(value is None or not math.isfinite(value) for value in values):
        return False
    if not 0 <= ra_deg < 360 or not -90 <= dec_deg <= 90:
        return False
    if image_width is None or image_height is None or image_width <= 0 or image_height <= 0:
        return False
    determinant = cd1_1 * cd2_2 - cd1_2 * cd2_1
    return math.isfinite(determinant) and determinant != 0 and pixel_scale > 0


def _safe_float(val: str | None) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except ValueError:
        return None


def _round(val: float | None, decimals: int) -> float | None:
    if val is None:
        return None
    return round(val, decimals)


def rotation_from_cd(cd1_2: float, cd2_2: float) -> float:
    """Return NightCrate's unnormalised corrected-solution rotation."""
    return math.degrees(math.atan2(-cd1_2, cd2_2))


def pixel_scale_from_cd(cd2_1: float, cd2_2: float) -> float:
    """Return NightCrate's ASTAP-compatible pixel scale in arcseconds."""
    return math.hypot(cd2_1, cd2_2) * 3600.0


def _safe_int(val: str | None) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except ValueError:
        return None


async def run_plate_solve(
    astap_path: str,
    image_path: str,
    hdu: int = 0,
    ra_hint: float | None = None,
    dec_hint: float | None = None,
    fov_hint: float | None = None,
    timeout: int = 180,
) -> PlateSolveResult:
    """Deprecated ASTAP-only service adapter used by the benchmark."""
    return await run_solve(
        solver="astap",
        astap_path=astap_path,
        image_path=image_path,
        hdu=hdu,
        ra_hint=ra_hint,
        dec_hint=dec_hint,
        fov_hint=fov_hint,
        timeout=timeout,
    )


async def run_solve(
    *,
    solver: Literal["native", "astap"],
    astap_path: str | None,
    image_path: str,
    hdu: int,
    ra_hint: float | None,
    dec_hint: float | None,
    fov_hint: float | None,
    scale_hint_arcsec: float | None = None,
    ignore_position: bool = False,
    ignore_scale: bool = False,
    timeout: int = 180,
    operation: solve_operations.SolveOperation | None = None,
) -> PlateSolveResult:
    """Dispatch one solve while retaining ownership until its worker stops.

    Endpoints pass their claimed operation. Direct callers get a temporary
    operation for backwards compatibility.
    """
    global _astap_stop, _astap_task, _native_cancel, _native_task
    owns_operation = operation is None
    if operation is None:
        try:
            operation = solve_operations.claim(uuid4(), solver)
        except solve_operations.SolveBusy as exc:
            raise RuntimeError(str(exc)) from exc
    try:
        operation.checkpoint()
        if solver == "astap":
            if astap_path is None:
                raise ValueError("ASTAP executable path is not configured. Set it in Settings.")
            task = asyncio.create_task(
                _do_solve(
                    resolve_astap_binary(astap_path),
                    image_path,
                    hdu,
                    ra_hint,
                    dec_hint,
                    fov_hint,
                    timeout,
                    scale_hint_arcsec=scale_hint_arcsec,
                    ignore_position=ignore_position,
                    ignore_scale=ignore_scale,
                    operation=operation,
                )
            )
            operation.task = task
            _astap_stop = operation.stop
            _astap_task = task
            try:
                result = await asyncio.shield(task)
                result.attempts = operation.attempts()
                return result
            except asyncio.CancelledError:
                operation.cancel()
                while True:
                    try:
                        await asyncio.shield(task)
                    except asyncio.CancelledError:
                        if not task.done():
                            continue
                    except Exception:
                        logger.exception("[plate_solve] ASTAP task failed while cancelling")
                    break
                raise
            finally:
                if task.done() and _astap_task is task:
                    _astap_task = None
                    _astap_stop = None
                operation.task = None

        from nightcrate.services.native_solver.solve_image import solve_image

        _native_cancel = operation.stop
        _native_task = asyncio.create_task(
            asyncio.to_thread(
                solve_image,
                image_path,
                hdu,
                ra_hint=ra_hint,
                dec_hint=dec_hint,
                fov_hint=fov_hint,
                scale_hint_arcsec=scale_hint_arcsec,
                ignore_position=ignore_position,
                ignore_scale=ignore_scale,
                cancel=operation.stop,
                reporter=operation,
            )
        )
        operation.task = _native_task
        try:
            result = await asyncio.shield(_native_task)
            return result
        except asyncio.CancelledError:
            operation.cancel()
            while True:
                try:
                    await asyncio.shield(_native_task)
                except asyncio.CancelledError:
                    if _native_task.done():
                        try:
                            _native_task.result()
                        except Exception:
                            logger.exception("[plate_solve] native worker failed while cancelling")
                        break
                    continue
                except Exception:
                    logger.exception("[plate_solve] native worker failed while cancelling")
                    break
                else:
                    break
            raise
        finally:
            if _native_task.done():
                _native_task = None
                _native_cancel = None
            operation.task = None
    finally:
        if owns_operation:
            solve_operations.release(operation)


async def shutdown() -> None:
    """Stop an active solver and close mappings only after it has stopped."""
    global _astap_stop, _astap_task, _native_cancel, _native_task, _solve_process
    active = solve_operations.active_operation()
    if active is not None:
        active.cancel()
    astap_task = _astap_task
    if astap_task is not None and not astap_task.done():
        if _astap_stop is not None:
            _astap_stop.set()
        proc = _solve_process
        if proc is not None and proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        try:
            await asyncio.wait_for(asyncio.shield(astap_task), timeout=10.0)
        except TimeoutError:
            logger.warning("[plate_solve] ASTAP task outlived shutdown timeout")
            return
        except Exception:
            logger.exception("[plate_solve] ASTAP task failed during shutdown")
    elif (proc := _solve_process) is not None and proc.returncode is None:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        cancelled = await _wait_for_process_exit(proc)
        if cancelled:
            raise asyncio.CancelledError
    if astap_task is not None and _astap_task is astap_task:
        _astap_task = None
        _astap_stop = None
    if _solve_process is not None and _solve_process.returncode is not None:
        _solve_process = None
    task = _native_task
    if task is not None and not task.done():
        if _native_cancel is not None:
            _native_cancel.set()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=10.0)
        except TimeoutError:
            logger.warning("[plate_solve] native worker outlived shutdown timeout")
            return
        except Exception:
            logger.exception("[plate_solve] native worker failed during shutdown")
    _native_task = None
    _native_cancel = None
    handles.close_all()


async def _wait_for_process_exit(proc: asyncio.subprocess.Process) -> bool:
    """Wait through repeated cancellation until a subprocess has exited."""
    wait_task = asyncio.create_task(proc.wait())
    cancelled = False
    while True:
        try:
            await asyncio.shield(wait_task)
        except asyncio.CancelledError:
            cancelled = True
            if not wait_task.done():
                continue
        if wait_task.done():
            wait_task.result()
            return cancelled


_ASTAP_NEAR_SECONDS = 60.0
_ASTAP_ERROR_CODES = {16, 32, 33, 34}


@dataclass
class _AstapRun:
    result: PlateSolveResult
    outcome: AttemptOutcome
    detail: str | None = None


def _astap_config_paths(
    environ: dict[str, str] | os._Environ[str] | None = None,
    *,
    platform: str | None = None,
) -> list[Path]:
    """Return user ASTAP config candidates for the current platform.

    The Linux and Windows locations mirror their conventional config roots;
    only the macOS behaviour has been verified against ASTAP itself.
    """
    values = os.environ if environ is None else environ
    current_platform = sys.platform if platform is None else platform
    if current_platform == "win32":
        local = values.get("LOCALAPPDATA")
        if not local:
            return []
        return [Path(local) / "astap" / "astap.cfg"]
    xdg_config = values.get("XDG_CONFIG_HOME")
    if xdg_config:
        return [Path(xdg_config) / "astap" / "astap.cfg"]
    home = Path(values.get("HOME", str(Path.home())))
    return [home / ".config" / "astap" / "astap.cfg"]


def _private_astap_environment(
    temp_home: Path,
    *,
    environ: dict[str, str] | os._Environ[str] | None = None,
    platform: str | None = None,
) -> dict[str, str]:
    """Copy ASTAP settings into an isolated per-subprocess home."""
    values = os.environ if environ is None else environ
    env = dict(values)
    current_platform = sys.platform if platform is None else platform
    candidates = _astap_config_paths(values, platform=current_platform)
    env["HOME"] = str(temp_home)
    if current_platform == "win32":
        env["LOCALAPPDATA"] = str(temp_home)
        env["APPDATA"] = str(temp_home)
        target = temp_home / "astap" / "astap.cfg"
    else:
        env["XDG_CONFIG_HOME"] = str(temp_home / ".config")
        target = temp_home / ".config" / "astap" / "astap.cfg"
    for candidate in candidates:
        if candidate.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate, target)
            break
    return env


@contextmanager
def _guard_astap_settings(
    *,
    environ: dict[str, str] | os._Environ[str] | None = None,
    platform: str | None = None,
):
    """Restore a pre-existing Windows ASTAP config if a solve changes it."""
    current_platform = sys.platform if platform is None else platform
    if current_platform != "win32":
        yield
        return
    paths = _astap_config_paths(environ, platform=current_platform)
    if not paths or not paths[0].is_file():
        yield
        return
    path = paths[0]
    try:
        original = path.read_bytes()
    except OSError:
        logger.warning(
            "[plate_solve] Could not protect ASTAP settings before a solve: %s",
            path,
            exc_info=True,
        )
        yield
        return
    try:
        yield
    finally:
        try:
            unchanged = path.read_bytes() == original
        except OSError:
            unchanged = False
        if not unchanged:
            temp_path: Path | None = None
            try:
                fd, temp_name = tempfile.mkstemp(prefix=".astap.cfg.", dir=path.parent)
                temp_path = Path(temp_name)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(original)
                os.replace(temp_path, path)
                temp_path = None
                logger.warning("[plate_solve] Restored ASTAP settings changed by a solve: %s", path)
            except OSError:
                logger.warning(
                    "[plate_solve] Failed to restore ASTAP settings after a solve: %s",
                    path,
                    exc_info=True,
                )
            finally:
                if temp_path is not None:
                    try:
                        temp_path.unlink()
                    except OSError:
                        pass


async def _run_astap_step(
    args: list[str],
    output_base: Path,
    timeout: float,
    width: int | None,
    height: int,
    *,
    flip_rows: bool,
    stop: threading.Event,
    operation: solve_operations.SolveOperation | None,
) -> _AstapRun:
    """Run one ASTAP step and translate process/INI state to a typed outcome."""
    global _solve_process
    ini_path = Path(f"{output_base}.ini")
    if ini_path.is_file():
        ini_path.unlink()
    started = time.monotonic()
    logger.info("[plate-solve] running: %s", " ".join(args))
    with (
        _guard_astap_settings(),
        tempfile.TemporaryDirectory(prefix="nightcrate_astap_home_") as home,
    ):
        env = _private_astap_environment(Path(home))
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        _solve_process = proc
        if operation is not None:
            operation.process = proc
        if stop.is_set():
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            cancelled = await _wait_for_process_exit(proc)
            _solve_process = None
            if operation is not None:
                operation.process = None
            if cancelled:
                raise asyncio.CancelledError
            return _AstapRun(
                PlateSolveResult(solved=False, error_message="Solve cancelled."), "cancelled"
            )
        if proc.stdout is None or proc.stderr is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()
            _solve_process = None
            if operation is not None:
                operation.process = None
            raise OSError("ASTAP process streams are unavailable.")
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.CancelledError:
            if proc.returncode is None:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
            await _wait_for_process_exit(proc)
            raise
        except TimeoutError:
            if proc.returncode is None:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
            cancelled = await _wait_for_process_exit(proc)
            if cancelled:
                raise asyncio.CancelledError
            return _AstapRun(
                PlateSolveResult(
                    solved=False,
                    error_message=f"ASTAP step timed out after {timeout:.0f} seconds.",
                    image_width=width,
                    image_height=height,
                    solve_time_seconds=round(time.monotonic() - started, 1),
                ),
                "step_timeout",
            )
        finally:
            _solve_process = None
            if operation is not None and operation.process is proc:
                operation.process = None

    elapsed = time.monotonic() - started
    if stdout:
        logger.info("[plate-solve] ASTAP: %s", stdout.decode(errors="replace").strip())
    if stderr:
        logger.info("[plate-solve] stderr: %s", stderr.decode(errors="replace").strip())
    if stop.is_set():
        return _AstapRun(
            PlateSolveResult(
                solved=False,
                error_message="Solve cancelled.",
                image_width=width,
                image_height=height,
                solve_time_seconds=round(elapsed, 1),
            ),
            "cancelled",
        )
    exit_code = proc.returncode
    if exit_code == 1:
        return _AstapRun(
            PlateSolveResult(
                solved=False,
                error_message=_EXIT_CODE_MESSAGES[1],
                image_width=width,
                image_height=height,
                solve_time_seconds=round(elapsed, 1),
            ),
            "no_match",
        )
    if exit_code == 2:
        return _AstapRun(
            PlateSolveResult(
                solved=False,
                error_message=_EXIT_CODE_MESSAGES[2],
                image_width=width,
                image_height=height,
                solve_time_seconds=round(elapsed, 1),
            ),
            "too_few_stars",
        )
    if exit_code in _ASTAP_ERROR_CODES:
        detail = _EXIT_CODE_MESSAGES[exit_code]
        if ini_path.is_file():
            detail = _parse_astap_ini(ini_path).get("ERROR") or detail
        return _AstapRun(
            PlateSolveResult(
                solved=False,
                error_message=detail,
                image_width=width,
                image_height=height,
                solve_time_seconds=round(elapsed, 1),
            ),
            "error",
            detail,
        )
    if not ini_path.is_file():
        detail = _EXIT_CODE_MESSAGES.get(
            exit_code, f"ASTAP exited with code {exit_code} and no output."
        )
        return _AstapRun(
            PlateSolveResult(
                solved=False,
                error_message=detail,
                image_width=width,
                image_height=height,
                solve_time_seconds=round(elapsed, 1),
            ),
            "error",
            detail,
        )
    result = _compute_results(_parse_astap_ini(ini_path), width, height, flip_rows=flip_rows)
    result.solve_time_seconds = round(elapsed, 1)
    if result.solved:
        return _AstapRun(result, "solved")
    if result.error_message == "ASTAP returned an incomplete solution.":
        return _AstapRun(result, "error", result.error_message)
    result.error_message = result.error_message or _EXIT_CODE_MESSAGES[1]
    return _AstapRun(result, "no_match")


async def run_astap_chain(
    binary: Path | str,
    image_file: Path,
    *,
    position: tuple[float, float] | None,
    scale_arcsec: float | None,
    image_height: int,
    deadline: float,
    stop: threading.Event,
    reporter,
    image_width: int | None = None,
    operation: solve_operations.SolveOperation | None = None,
    position_source: Literal["request", "header", "none"] | None = None,
    scale_source: Literal["request", "header", "none"] | None = None,
) -> PlateSolveResult:
    """Run ASTAP's near-then-whole-sky chain under one deadline."""
    if image_width is None:
        image_width, _ = _get_dimensions_from_file(image_file)
    steps = ["astap_near", "astap_blind"] if position is not None else ["astap_blind"]
    reporter.plan(steps)
    position_source = position_source or ("none" if position is None else "request")
    scale_source = scale_source or ("none" if scale_arcsec is None else "request")
    output_base = image_file.parent / "result"
    field_deg = scale_arcsec * image_height / 3600.0 if scale_arcsec is not None else 0.0
    last_result: PlateSolveResult | None = None
    last_outcome: AttemptOutcome | None = None
    for step in steps:
        attempt = SolveAttempt(
            solver="astap",
            step=step,
            position_source=position_source,
            scale_source=scale_source,
        )
        reporter.start(attempt)
        if operation is not None:
            operation.set_sources(position_source, scale_source)
        remaining = deadline - time.monotonic()
        if stop.is_set():
            reporter.finish("cancelled")
            return PlateSolveResult(
                solved=False,
                error_message="Solve cancelled.",
                failure_reason="cancelled",
            )
        if remaining <= 0:
            reporter.finish("overall_timeout")
            return PlateSolveResult(
                solved=False,
                error_message="ASTAP solve timed out.",
                failure_reason="time_limit",
            )
        args = [str(binary), "-f", str(image_file), "-z", "0", "-o", str(output_base)]
        if step == "astap_near":
            ra_deg, dec_deg = position
            args.extend(
                [
                    "-r",
                    "30",
                    "-ra",
                    str(ra_deg / 15.0),
                    "-spd",
                    str(dec_deg + 90.0),
                    "-fov",
                    str(field_deg),
                ]
            )
            step_timeout = min(_ASTAP_NEAR_SECONDS, remaining)
        else:
            args.extend(["-r", "180", "-fov", str(field_deg)])
            step_timeout = remaining
        run = await _run_astap_step(
            args,
            output_base,
            step_timeout,
            image_width,
            image_height,
            flip_rows=image_file.suffix.lower() in STANDARD_EXTENSIONS,
            stop=stop,
            operation=operation,
        )
        outcome = run.outcome
        if outcome == "step_timeout" and time.monotonic() >= deadline:
            outcome = "overall_timeout"
            run.result.error_message = "ASTAP solve timed out."
        reporter.finish(outcome, detail=run.detail)
        last_result = run.result
        last_outcome = outcome
        if outcome == "solved":
            return run.result
        if outcome not in {"no_match", "step_timeout"}:
            run.result.failure_reason = {
                "overall_timeout": "time_limit",
                "cancelled": "cancelled",
                "too_few_stars": "too_few_stars",
                "error": "error",
            }.get(outcome, "error")
            return run.result
    if position is not None:
        message = "ASTAP found no solution near the position or across the whole sky."
    else:
        message = "ASTAP found no solution across the whole sky."
    if last_result is None:
        last_result = PlateSolveResult(solved=False)
    last_result.error_message = message
    last_result.failure_reason = "time_limit" if last_outcome == "step_timeout" else "no_match"
    return last_result


async def _do_solve(
    astap_binary: Path,
    image_path: str,
    hdu: int,
    ra_hint: float | None,
    dec_hint: float | None,
    fov_hint: float | None,
    timeout: int,
    *,
    scale_hint_arcsec: float | None = None,
    ignore_position: bool = False,
    ignore_scale: bool = False,
    operation: solve_operations.SolveOperation | None = None,
    stop: threading.Event | None = None,
) -> PlateSolveResult:
    """Prepare ASTAP's exact input file and run the structured step chain."""
    started = time.monotonic()
    deadline = started + timeout
    stop_event = operation.stop if operation is not None else stop or threading.Event()
    reporter = operation
    if reporter is None:
        from nightcrate.services.native_solver.models import NullSolveReporter

        reporter = NullSolveReporter()
    preparation, prepare_cancelled = await _finish_awaitable(
        asyncio.to_thread(_read_astap_source, image_path, hdu)
    )
    if prepare_cancelled:
        raise asyncio.CancelledError
    source, file_type, image_index, raw_bytes, cards = preparation

    def fresh_source() -> Path | BinaryIO:
        if raw_bytes is not None:
            return io.BytesIO(raw_bytes)
        if source is None:
            raise RuntimeError("ASTAP source preparation returned no source.")
        return source

    raw_header = cards_to_dict(cards)
    if stop_event.is_set():
        return PlateSolveResult(
            solved=False,
            error_message="Solve cancelled.",
            failure_reason="cancelled",
        )
    if time.monotonic() >= deadline:
        return PlateSolveResult(
            solved=False,
            error_message="ASTAP solve timed out.",
            failure_reason="time_limit",
        )
    with tempfile.TemporaryDirectory(prefix="nightcrate_solve_") as tmp:
        image_file = await asyncio.to_thread(
            _prepare_image_file,
            fresh_source(),
            file_type,
            image_index,
            hdu,
            Path(tmp),
            header_keywords=raw_header,
        )
        try:
            width, height = await asyncio.to_thread(_get_dimensions_from_file, image_file)
        except OSError, ValueError:
            width, height = None, None
        if width is None:
            width = _safe_int(raw_header.get("NAXIS1"))
        if height is None:
            height = _safe_int(raw_header.get("NAXIS2"))
        if width is None or height is None or width <= 0 or height <= 0:
            raise ValueError("Cannot determine the prepared image dimensions.")
        from nightcrate.services.native_solver.hints import hints_for

        hints = hints_for(
            cards,
            image_height=height,
            ra_hint=ra_hint,
            dec_hint=dec_hint,
            scale_hint_arcsec=scale_hint_arcsec,
            fov_hint=fov_hint,
            ignore_position=ignore_position,
            ignore_scale=ignore_scale,
        )
        position = (
            (hints.ra_deg, hints.dec_deg)
            if hints.ra_deg is not None and hints.dec_deg is not None
            else None
        )
        result = await run_astap_chain(
            astap_binary,
            image_file,
            position=position,
            scale_arcsec=hints.scale_arcsec,
            image_width=width,
            image_height=height,
            deadline=deadline,
            stop=stop_event,
            reporter=reporter,
            operation=operation,
            position_source=hints.position_source,
            scale_source=hints.scale_source,
        )
        result.solver = "astap"
        result.solve_time_seconds = round(time.monotonic() - started, 1)
        return result


async def _run_astap(
    args: list[str],
    output_base: Path,
    timeout: float,
    width: int,
    height: int,
    flip_rows: bool = False,
    *,
    stop: threading.Event | None = None,
) -> tuple[PlateSolveResult, float]:
    """Compatibility wrapper around one typed ASTAP subprocess step."""
    started = time.monotonic()
    run = await _run_astap_step(
        args,
        output_base,
        timeout,
        width,
        height,
        flip_rows=flip_rows,
        stop=stop or threading.Event(),
        operation=None,
    )
    return run.result, time.monotonic() - started


def get_image_dimensions(image_path: str, hdu: int = 0) -> tuple[int | None, int | None]:
    """Read image dimensions from any supported path."""
    source, file_type, image_index, _ = _resolve_path(image_path)

    # A BinaryIO source (archive entry) is closed by header reading (astropy
    # closes file objects passed to fits.open); read its bytes once and hand a
    # fresh buffer to each consumer so the fallbacks don't hit a closed stream.
    raw_bytes: bytes | None = None
    if not isinstance(source, Path):
        raw_bytes = source.read()

    def fresh_source() -> Path | BinaryIO:
        return io.BytesIO(raw_bytes) if raw_bytes is not None else source

    cards = read_header_cards(fresh_source(), file_type, image_index, hdu)
    raw = cards_to_dict(cards)
    w = _safe_int(raw.get("NAXIS1"))
    h = _safe_int(raw.get("NAXIS2"))
    if w and h:
        return w, h
    if isinstance(source, Path):
        fw, fh = _get_dimensions_from_file(source)
        if fw and fh:
            return fw, fh
    try:
        if file_type == "pxiproject":
            data = pxiproject_io.load_image_data(fresh_source(), image_index)
        elif file_type == "fits":
            data = fits_io.load_image_data(fresh_source(), hdu)
        elif file_type == "xisf":
            data = xisf_io.load_image_data(fresh_source(), hdu)
        else:
            data = standard_io.load_image_data(fresh_source())
        if data is not None and data.ndim >= 2:
            return data.shape[-1], data.shape[-2]
    except Exception:
        logger.debug(
            "[plate-solve] failed to load pixel data for dimensions: %s",
            image_path,
            exc_info=True,
        )
    return None, None


def _get_dimensions_from_file(image_path: Path) -> tuple[int | None, int | None]:
    """Read image dimensions directly from a file on disk."""
    ext = image_path.suffix.lower()
    if ext in FITS_EXTENSIONS:
        with astro_fits.open(image_path, memmap=False) as hdul:
            for h in hdul:
                if h.data is not None and h.data.ndim >= 2:
                    shape = h.data.shape
                    return shape[-1], shape[-2]
    try:
        from PIL import Image

        with Image.open(image_path) as img:
            return img.size
    except Exception:  # nosec B110 — best-effort fallback
        pass
    return None, None
