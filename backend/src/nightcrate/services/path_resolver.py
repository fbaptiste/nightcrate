"""Resolve and classify image file paths, including pxiproject and archive
virtual paths. Shared between the image-viewer and aberration-inspector
routers."""

from pathlib import Path
from typing import BinaryIO

from fastapi import HTTPException

from nightcrate.services import archive_io, standard_io

FITS_EXTENSIONS = {".fits", ".fit", ".fts"}
XISF_EXTENSIONS = {".xisf"}
STANDARD_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
ALL_EXTENSIONS = FITS_EXTENSIONS | XISF_EXTENSIONS | STANDARD_EXTENSIONS


def file_type(p: Path) -> str:
    """Return 'fits', 'xisf', 'float_tiff', or 'standard' based on extension + content."""
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


def file_type_from_ext(entry_name: str) -> str:
    """Classify by extension alone (no disk read). Used for archive entries."""
    suffix = Path(entry_name).suffix.lower()
    if suffix in FITS_EXTENSIONS:
        return "fits"
    if suffix in XISF_EXTENSIONS:
        return "xisf"
    if suffix in STANDARD_EXTENSIONS:
        if suffix in {".tif", ".tiff"}:
            return "tiff_unknown"
        return "standard"
    raise HTTPException(status_code=422, detail=f"Unsupported format: {entry_name}")


def detect_tiff_type_from_buf(buf: BinaryIO) -> str:
    """Peek at a TIFF byte stream and decide between 'float_tiff' and 'standard'."""
    import tifffile

    try:
        with tifffile.TiffFile(buf) as tif:
            is_float = tif.pages[0].dtype.kind == "f"
        buf.seek(0)
        return "float_tiff" if is_float else "standard"
    except Exception:
        buf.seek(0)
        return "standard"


def resolve_path(path: str) -> tuple[Path | BinaryIO, str, int, tuple | None]:
    """Validate and resolve a file path, handling pxiproject and archive virtual paths.

    Returns (resolved_path, file_type, image_index, cache_key).

    - `image_index` is only meaningful for pxiproject virtual paths; 0 otherwise.
    - `cache_key` is set for archive entries so concurrent callers can share
      the data/stats caches. For regular Path files it's `None` — those use
      `(path, mtime)` directly.
    """
    if "::" in path:
        left, right = path.rsplit("::", 1)
        left_path = Path(left).resolve()

        # pxiproject: right side is an integer index into the project's images.
        try:
            idx = int(right)
            if not left_path.is_dir():
                raise HTTPException(status_code=404, detail=f"Project not found: {left_path}")
            return left_path, "pxiproject", idx, None
        except ValueError:
            pass

        # Archive entry (zip / tar / tar.gz / tar.bz2 / tar.zst / 7z).
        if archive_io.is_archive(left_path):
            if not left_path.is_file():
                raise HTTPException(status_code=404, detail=f"Archive not found: {left}")
            try:
                buf = archive_io.extract_entry(left_path, right)
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail=f"Entry not found: {right}") from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            ft = file_type_from_ext(right)
            if ft == "tiff_unknown":
                ft = detect_tiff_type_from_buf(buf)
            # (archive path, mtime, entry) so concurrent requests dedupe.
            cache_key = (str(left_path), left_path.stat().st_mtime, right)
            return buf, ft, 0, cache_key

        raise HTTPException(status_code=400, detail=f"Invalid virtual path: {path}")

    p = Path(path)
    if not p.is_absolute():
        raise HTTPException(status_code=400, detail="Path must be absolute")
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    return p, file_type(p), 0, None
