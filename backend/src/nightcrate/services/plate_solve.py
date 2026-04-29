"""Plate solving via ASTAP subprocess invocation.

Pure service module — no FastAPI, no DB access. Handles ASTAP binary
resolution, subprocess execution, .ini output parsing, and result
computation. Temp file management for virtual-path images (archive,
pxiproject) is handled internally.
"""

import asyncio
import logging
import math
import os
import tempfile
import time
from pathlib import Path
from typing import BinaryIO

import numpy as np
from astropy.io import fits as astro_fits

from nightcrate.services import (
    fits_io,
    pxiproject_io,
    standard_io,
    xisf_io,
)
from nightcrate.services.coordinate_format import format_dec_dms, format_ra_hms
from nightcrate.services.path_resolver import (
    FITS_EXTENSIONS,
    STANDARD_EXTENSIONS,
)
from nightcrate.services.path_resolver import (
    resolve_path as _resolve_path_raw,
)
from nightcrate.services.plate_solve_models import PlateSolveResult

logger = logging.getLogger("nightcrate")


def _resolve_path(path: str) -> tuple[Path | BinaryIO, str, int, tuple | None]:
    """Wrap path_resolver.resolve_path, converting HTTPException to ValueError."""
    try:
        return _resolve_path_raw(path)
    except Exception as exc:
        if type(exc).__name__ == "HTTPException":
            raise ValueError(getattr(exc, "detail", str(exc))) from None
        raise


_solve_semaphore = asyncio.Semaphore(1)
_solve_progress: str = ""
_solve_process: asyncio.subprocess.Process | None = None

_KEY_VAL_ERRORS = (KeyError, ValueError)

_EXIT_CODE_MESSAGES = {
    1: "No solution found. Try blind solve or verify the image contains stars.",
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


def get_solve_progress() -> str:
    return _solve_progress


def cancel_solve() -> bool:
    global _solve_process
    if _solve_process is not None and _solve_process.returncode is None:
        _solve_process.kill()
        return True
    return False


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


_MAX_EXTRACT_STARS = 500
_EXTRACT_DOT_RADIUS = 5


def create_star_map_preview(
    image_path: str,
    hdu: int = 0,
    *,
    thresh: float = 5.0,
    min_area: int = 5,
    max_elongation: float = 0.0,
    bg_mesh: int = 64,
    deblend_cont: float = 0.005,
) -> bytes:
    """Create a star map and return it as PNG bytes for preview."""
    import io
    import tempfile

    from PIL import Image

    resolved, file_type, image_index, _ = _resolve_path(image_path)
    with tempfile.TemporaryDirectory() as tmp:
        star_map_path = _create_star_map(
            resolved, file_type, image_index, hdu, Path(tmp),
            thresh=thresh, min_area=min_area,
            max_elongation=max_elongation,
            bg_mesh=bg_mesh, deblend_cont=deblend_cont,
        )
        with astro_fits.open(star_map_path) as hdu_list:
            data = hdu_list[0].data
        if data.max() > 0:
            normed = data / data.max()
            stretched = np.power(normed, 0.3)
            scaled = (stretched * 255).astype(np.uint8)
        else:
            scaled = np.zeros_like(data, dtype=np.uint8)
        img = Image.fromarray(scaled, mode="L")
        buf = io.BytesIO()
        img.save(buf, format="PNG", compress_level=1)
        return buf.getvalue()


def _create_star_map(
    source: Path | BinaryIO,
    file_type: str,
    image_index: int,
    hdu: int,
    temp_dir: Path,
    *,
    thresh: float = 5.0,
    min_area: int = 5,
    max_elongation: float = 0.0,
    bg_mesh: int = 64,
    deblend_cont: float = 0.005,
) -> Path:
    """Detect stars with sep and create a synthetic star map for ASTAP.

    Extracts the brightest stars, renders Gaussian-profile dots on a
    black background. ASTAP solves this reliably even when the original
    stretched image fails.

    ``thresh`` — detection threshold in sigma (higher = fewer, brighter).
    ``min_area`` — minimum pixel area for a detection.
    ``max_elongation`` — max a/b ratio; 0 disables the filter.
    """
    import sep

    if file_type == "pxiproject":
        data = pxiproject_io.load_image_data(source, image_index)
    elif file_type == "fits":
        data = fits_io.load_image_data(source, hdu)
    elif file_type == "xisf":
        data = xisf_io.load_image_data(source, hdu)
    else:
        data = standard_io.load_image_data(source)

    if data.ndim == 3:
        mono = np.mean(data, axis=0)
    else:
        mono = data

    mono = np.ascontiguousarray(mono, dtype=np.float64)
    bkg = sep.Background(mono, bw=bg_mesh, bh=bg_mesh)
    img_sub = mono - bkg

    sep.set_extract_pixstack(1_000_000)
    detect_thresh = thresh
    objects = None
    for attempt in range(4):
        try:
            objects = sep.extract(
                img_sub, thresh=detect_thresh, err=bkg.globalrms,
                minarea=min_area, deblend_cont=deblend_cont,
            )
            break
        except Exception as exc:
            if "pixel buffer full" in str(exc) and attempt < 3:
                detect_thresh *= 2
            else:
                raise

    h, w = mono.shape
    star_map = np.zeros((h, w), dtype=np.float32)

    if objects is not None and len(objects) > 0:
        if max_elongation > 0:
            b = objects["b"]
            a = objects["a"]
            safe_b = np.where(b > 0, b, 1e-6)
            elongation = a / safe_b
            objects = objects[elongation <= max_elongation]

        if len(objects) > _MAX_EXTRACT_STARS:
            flux_cutoff = np.sort(objects["flux"])[-_MAX_EXTRACT_STARS]
            objects = objects[objects["flux"] >= flux_cutoff]

        fluxes = objects["flux"]
        max_flux = fluxes.max() if fluxes.max() > 0 else 1.0
        r = _EXTRACT_DOT_RADIUS
        sigma = r * 1.6

        for i in range(len(objects)):
            x = int(round(float(objects["x"][i])))
            y = int(round(float(objects["y"][i])))
            if 0 <= x < w and 0 <= y < h:
                brightness = min(1.0, (fluxes[i] / max_flux) * 3.0 + 0.3)
                for dy in range(-r, r + 1):
                    for dx in range(-r, r + 1):
                        d2 = dx * dx + dy * dy
                        if d2 <= r * r:
                            ny, nx = y + dy, x + dx
                            if 0 <= ny < h and 0 <= nx < w:
                                val = brightness * math.exp(-d2 / sigma)
                                if val > star_map[ny, nx]:
                                    star_map[ny, nx] = val

        logger.info(
            "[plate-solve] star extraction: %d stars, %dx%d star map",
            len(objects),
            w,
            h,
        )
    else:
        logger.warning("[plate-solve] star extraction: no stars detected")

    temp_path = temp_dir / "star_map.fits"
    hdu_obj = astro_fits.PrimaryHDU(star_map)
    hdu_obj.writeto(temp_path, overwrite=True)
    return temp_path


def _prepare_image_file(
    source: Path | BinaryIO,
    file_type: str,
    image_index: int,
    hdu: int,
    temp_dir: Path,
) -> Path:
    """Ensure a real filesystem path suitable for ASTAP.

    For regular files in ASTAP-supported formats, returns the path as-is.
    For virtual paths (archive, pxiproject) or unsupported formats
    (compressed XISF), writes a temporary FITS file and returns its path.
    """
    if isinstance(source, Path):
        ext = source.suffix.lower()
        if ext in FITS_EXTENSIONS | STANDARD_EXTENSIONS:
            return source
        if ext == ".xisf":
            data = xisf_io.load_image_data(source, hdu)
            return _write_temp_fits(data, temp_dir)
        if file_type == "pxiproject":
            data = pxiproject_io.load_image_data(source, image_index)
            return _write_temp_fits(data, temp_dir)
        return source

    if file_type == "fits":
        temp_path = temp_dir / "solve_input.fits"
        temp_path.write_bytes(source.read())
        return temp_path

    data = _load_data_from_buf(source, file_type, hdu)
    return _write_temp_fits(data, temp_dir)


def _load_data_from_buf(buf: BinaryIO, file_type: str, hdu: int) -> np.ndarray:
    """Load image data from a BytesIO buffer."""
    if file_type == "xisf":
        return xisf_io.load_image_data(buf, hdu)
    if file_type in ("float_tiff", "standard"):
        if file_type == "float_tiff":
            return standard_io.load_image_data(buf)
        return standard_io.load_image_as_array(buf)
    return fits_io.load_image_data(buf, hdu)


def _write_temp_fits(data: np.ndarray, temp_dir: Path) -> Path:
    """Write a numpy array as a temporary FITS file."""
    temp_path = temp_dir / "solve_input.fits"
    hdu_obj = astro_fits.PrimaryHDU(data)
    hdu_obj.writeto(temp_path, overwrite=True)
    return temp_path


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

    pixel_scale: float | None = None
    if cd2_1 is not None and cd2_2 is not None:
        pixel_scale = math.sqrt(cd2_1**2 + cd2_2**2) * 3600.0

    rotation: float | None = crota2
    if rotation is None and cd1_1 is not None and cd2_1 is not None:
        rotation = math.degrees(math.atan2(cd2_1, cd1_1))

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
    mode: str = "auto",
    ra_hint: float | None = None,
    dec_hint: float | None = None,
    fov_hint: float | None = None,
    timeout: int = 180,
    extract_thresh: float = 5.0,
    extract_min_area: int = 5,
    extract_max_elongation: float = 0.0,
    extract_bg_mesh: int = 64,
    extract_deblend_cont: float = 0.005,
) -> PlateSolveResult:
    """Execute ASTAP plate solve and return results.

    Raises ``RuntimeError`` if another solve is already in progress.
    """
    astap_binary = resolve_astap_binary(astap_path)

    if _solve_semaphore.locked():
        if cancel_solve():
            logger.warning("[plate-solve] killed stale ASTAP process before new solve")
            await asyncio.sleep(0.5)
        if _solve_semaphore.locked():
            raise RuntimeError("A plate solve is already in progress.")
    await _solve_semaphore.acquire()

    try:
        return await _do_solve(
            astap_binary,
            image_path,
            hdu,
            mode,
            ra_hint,
            dec_hint,
            fov_hint,
            timeout,
            extract_thresh=extract_thresh,
            extract_min_area=extract_min_area,
            extract_max_elongation=extract_max_elongation,
            extract_bg_mesh=extract_bg_mesh,
            extract_deblend_cont=extract_deblend_cont,
        )
    finally:
        _solve_semaphore.release()


async def _do_solve(
    astap_binary: Path,
    image_path: str,
    hdu: int,
    mode: str,
    ra_hint: float | None,
    dec_hint: float | None,
    fov_hint: float | None,
    timeout: int,
    *,
    extract_thresh: float = 5.0,
    extract_min_area: int = 5,
    extract_max_elongation: float = 0.0,
    extract_bg_mesh: int = 64,
    extract_deblend_cont: float = 0.005,
) -> PlateSolveResult:
    source, file_type, image_index, _cache_key = _resolve_path(image_path)
    cards = read_header_cards(source, file_type, image_index, hdu)
    hints = _extract_hints(cards)

    raw_header = cards_to_dict(cards)
    width = _safe_int(raw_header.get("NAXIS1"))
    height = _safe_int(raw_header.get("NAXIS2"))

    if hasattr(source, "seek"):
        source.seek(0)

    with tempfile.TemporaryDirectory(prefix="nightcrate_solve_") as tmp:
        tmp_dir = Path(tmp)
        output_base = tmp_dir / "result"

        if mode == "extract":
            image_file = await asyncio.to_thread(
                _create_star_map,
                source,
                file_type,
                image_index,
                hdu,
                tmp_dir,
                thresh=extract_thresh,
                min_area=extract_min_area,
                max_elongation=extract_max_elongation,
                bg_mesh=extract_bg_mesh,
                deblend_cont=extract_deblend_cont,
            )
        else:
            image_file = await asyncio.to_thread(
                _prepare_image_file,
                source,
                file_type,
                image_index,
                hdu,
                tmp_dir,
            )

        if width is None or height is None:
            w, h = await asyncio.to_thread(
                _get_dimensions_from_file,
                image_file,
            )
            if width is None:
                width = w
            if height is None:
                height = h

        astap_mode = "auto" if mode == "extract" else mode
        effective_fov = fov_hint
        if mode == "extract" and effective_fov is None:
            effective_fov = 0.0
        args = _build_astap_args(
            astap_binary,
            image_file,
            output_base,
            astap_mode,
            hints,
            ra_hint,
            dec_hint,
            effective_fov,
        )

        result, first_elapsed = await _run_astap(
            args,
            output_base,
            timeout,
            width,
            height,
        )

        if not result.solved and result.error_message:
            msg = result.error_message
            retryable = "No solution" in msg or "Not enough stars" in msg
            if retryable:
                logger.info("[plate-solve] retrying with -speed slow")
                ini_path = Path(str(output_base) + ".ini")
                if ini_path.is_file():
                    ini_path.unlink()
                remaining = max(30, timeout - int(first_elapsed))
                result, retry_elapsed = await _run_astap(
                    [*args, "-speed", "slow"],
                    output_base,
                    remaining,
                    width,
                    height,
                )
                result.solve_time_seconds = round(first_elapsed + retry_elapsed, 1)

        return result


async def _run_astap(
    args: list[str],
    output_base: Path,
    timeout: int,
    width: int | None,
    height: int | None,
) -> tuple[PlateSolveResult, float]:
    """Run ASTAP subprocess and parse result. Returns (result, elapsed_seconds)."""
    global _solve_progress
    _solve_progress = "Starting ASTAP..."
    logger.info("[plate-solve] running: %s", " ".join(args))
    start = time.monotonic()

    try:
        global _solve_process
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _solve_process = proc
        stdout_lines: list[str] = []
        stderr_data = b""

        async def _read_stdout():
            assert proc.stdout
            async for raw_line in proc.stdout:
                line = raw_line.decode(errors="replace").rstrip()
                stdout_lines.append(line)
                if line:
                    global _solve_progress
                    _solve_progress = line
                    logger.debug("[plate-solve] %s", line)

        async def _read_stderr():
            nonlocal stderr_data
            assert proc.stderr
            stderr_data = await proc.stderr.read()

        try:
            await asyncio.wait_for(
                asyncio.gather(_read_stdout(), _read_stderr(), proc.wait()),
                timeout=timeout,
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            elapsed = time.monotonic() - start
            _solve_progress = ""
            _solve_process = None
            logger.warning("[plate-solve] timed out after %.1fs", elapsed)
            return PlateSolveResult(
                solved=False,
                error_message=f"Solve timed out after {timeout} seconds.",
                solve_time_seconds=round(elapsed, 1),
                image_width=width,
                image_height=height,
            ), elapsed

    except Exception:
        _solve_progress = ""
        raise

    elapsed = time.monotonic() - start
    exit_code = proc.returncode
    _solve_progress = ""
    _solve_process = None

    logger.info("[plate-solve] finished in %.1fs, exit code %d", elapsed, exit_code)

    if stderr_data:
        logger.debug("[plate-solve] stderr: %s", stderr_data.decode(errors="replace").strip())

    ini_path = Path(str(output_base) + ".ini")
    if not ini_path.is_file():
        error_msg = _EXIT_CODE_MESSAGES.get(
            exit_code,
            f"ASTAP exited with code {exit_code} and no output.",
        )
        return PlateSolveResult(
            solved=False,
            error_message=error_msg,
            solve_time_seconds=round(elapsed, 1),
            image_width=width,
            image_height=height,
        ), elapsed

    ini_data = _parse_astap_ini(ini_path)
    result = _compute_results(ini_data, width, height)
    result.solve_time_seconds = round(elapsed, 1)

    if not result.solved and not result.error_message:
        result.error_message = _EXIT_CODE_MESSAGES.get(
            exit_code,
            f"ASTAP exited with code {exit_code}.",
        )

    return result, elapsed


def get_image_dimensions(image_path: str, hdu: int = 0) -> tuple[int | None, int | None]:
    """Read image dimensions from any supported path."""
    source, file_type, image_index, _ = _resolve_path(image_path)
    cards = read_header_cards(source, file_type, image_index, hdu)
    raw = cards_to_dict(cards)
    w = _safe_int(raw.get("NAXIS1"))
    h = _safe_int(raw.get("NAXIS2"))
    if w and h:
        return w, h
    if hasattr(source, "seek"):
        source.seek(0)
    if isinstance(source, Path):
        fw, fh = _get_dimensions_from_file(source)
        if fw and fh:
            return fw, fh
    try:
        if hasattr(source, "seek"):
            source.seek(0)
        if file_type == "pxiproject":
            data = pxiproject_io.load_image_data(source, image_index)
        elif file_type == "fits":
            data = fits_io.load_image_data(source, hdu)
        elif file_type == "xisf":
            data = xisf_io.load_image_data(source, hdu)
        else:
            data = standard_io.load_image_data(source)
        if data is not None and data.ndim >= 2:
            return data.shape[-1], data.shape[-2]
    except Exception:
        pass
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
