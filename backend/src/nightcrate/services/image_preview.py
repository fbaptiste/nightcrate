"""Bounded, identity-keyed JPEG previews for supported image paths."""

from __future__ import annotations

import hashlib
import math
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Literal

import numpy as np
from astropy.io import fits
from PIL import Image

from nightcrate.services import pxiproject_io, standard_io, xisf_io
from nightcrate.services.catalog_thumbnail import render_array_jpeg
from nightcrate.services.imaging import normalize_to_01, reshape_color
from nightcrate.services.path_resolver import file_type, resolve_path

MIN_MAX_PX = 256
MAX_MAX_PX = 2400
DEFAULT_MAX_PX = 1600
_CACHE_MAX_BYTES = 32 * 1024 * 1024

_cache: OrderedDict[str, bytes] = OrderedDict()
_cache_bytes = 0
_cache_lock = threading.Lock()
_full_decode_sem = threading.Semaphore(1)
_reduced_decode_sem = threading.Semaphore(2)


class PreviewError(Exception):
    """Base class for preview failures translated by the API route."""


class PreviewNotFound(PreviewError):
    """The source path or a referenced backing file is missing."""


class PreviewUnreadable(PreviewError):
    """The source exists but cannot be decoded as a supported image."""


@dataclass(frozen=True)
class PreviewResult:
    etag: str
    content: bytes | None
    not_modified: bool = False


@dataclass(frozen=True)
class _SourceIdentity:
    parts: tuple[object, ...]
    decode_group: Literal["full", "reduced"]


def _stat_parts(path: Path) -> tuple[str, int, int]:
    try:
        real = path.resolve(strict=True)
        stat = real.stat()
    except FileNotFoundError as exc:
        raise PreviewNotFound(f"File not found: {path}") from exc
    except OSError as exc:
        raise PreviewUnreadable(str(exc)) from exc
    return str(real), stat.st_size, stat.st_mtime_ns


def _pxiproject_identity(project_dir: Path, image_index: int) -> _SourceIdentity:
    manifest = project_dir / "project.xosm"
    manifest_parts = _stat_parts(manifest)
    try:
        images, _compression = pxiproject_io._list_project_images_with_compression(project_dir)
        entry = images[image_index]
    except IndexError as exc:
        raise PreviewUnreadable(
            f"Image index {image_index} out of range (project has {len(images)} images)"
        ) from exc
    except (OSError, ValueError, pxiproject_io.PxiProjectError) as exc:
        raise PreviewUnreadable(str(exc)) from exc

    if entry["source"] == "referenced" and entry["file_path"]:
        backing = Path(entry["file_path"])
    else:
        data_src = entry.get("data_src")
        if not data_src:
            raise PreviewUnreadable(f"No data source for embedded image '{entry['name']}'")
        data_dir = (project_dir / "project.data").resolve()
        backing = (data_dir / data_src).resolve()
        if not backing.is_relative_to(data_dir):
            raise PreviewUnreadable(f"Invalid data source path: {data_src}")
    backing_parts = _stat_parts(backing)
    return _SourceIdentity(("pxiproject", *manifest_parts, image_index, *backing_parts), "full")


def _source_identity(path: str) -> _SourceIdentity:
    if "::" in path:
        left, right = path.rsplit("::", 1)
        left_path = Path(left)
        try:
            image_index = int(right)
        except ValueError:
            archive_parts = _stat_parts(left_path)
            suffix = Path(right).suffix.lower()
            group = "full" if suffix in {".xisf", ".tif", ".tiff"} else "reduced"
            return _SourceIdentity(("archive", *archive_parts, right), group)
        if not left_path.is_dir():
            raise PreviewNotFound(f"Project not found: {left_path}")
        return _pxiproject_identity(left_path.resolve(), image_index)

    plain_parts = _stat_parts(Path(path))
    try:
        kind = file_type(Path(plain_parts[0]))
    except Exception as exc:
        raise PreviewUnreadable(str(getattr(exc, "detail", exc))) from exc
    group = "full" if kind in {"xisf", "float_tiff"} else "reduced"
    return _SourceIdentity(("plain", *plain_parts), group)


def _etag(identity: _SourceIdentity, hdu: int, max_px: int) -> tuple[str, str]:
    digest = hashlib.blake2b(
        repr((*identity.parts, hdu, max_px)).encode("utf-8"), digest_size=16
    ).hexdigest()
    return digest, f'"{digest}"'


def _etag_matches(value: str | None, etag: str) -> bool:
    if value is None:
        return False
    candidate = value.strip()
    return candidate == etag or candidate == f"W/{etag}"


def _cache_get(key: str) -> bytes | None:
    with _cache_lock:
        value = _cache.get(key)
        if value is not None:
            _cache.move_to_end(key)
        return value


def _cache_put(key: str, value: bytes) -> None:
    global _cache_bytes
    if len(value) > _CACHE_MAX_BYTES:
        with _cache_lock:
            previous = _cache.pop(key, None)
            if previous is not None:
                _cache_bytes -= len(previous)
        return
    with _cache_lock:
        previous = _cache.pop(key, None)
        if previous is not None:
            _cache_bytes -= len(previous)
        _cache[key] = value
        _cache_bytes += len(value)
        while _cache_bytes > _CACHE_MAX_BYTES:
            _, evicted = _cache.popitem(last=False)
            _cache_bytes -= len(evicted)


def _normalize_fits_sample(
    data: np.ndarray,
    *,
    bitpix: int,
    bscale: float,
    bzero: float,
    blank_mask: np.ndarray | None = None,
) -> np.ndarray:
    """Apply FITS scaling and normalize according to the logical pixel type."""
    scaled = np.asarray(data, dtype=np.float64) * bscale + bzero
    valid = np.isfinite(scaled)
    if blank_mask is not None:
        valid &= ~blank_mask
    if not np.any(valid):
        raise PreviewUnreadable("Image contains no finite pixel values")

    scaled[~valid] = 0.0
    if bitpix == 16 and bscale == 1.0 and bzero == 32768.0:
        logical = scaled.astype(np.uint16)
    elif bitpix == 32 and bscale == 1.0 and bzero == 2**31:
        logical = scaled.astype(np.uint32)
    elif bitpix == 8 and bscale == 1.0 and bzero == 0.0:
        logical = scaled.astype(np.uint8)
    elif bitpix == 16 and bscale == 1.0 and bzero == 0.0:
        logical = scaled.astype(np.int16)
    elif bitpix == 32 and bscale == 1.0 and bzero == 0.0:
        logical = scaled.astype(np.int32)
    else:
        logical = scaled

    result = normalize_to_01(logical).astype(np.float32)
    result[~valid] = 0.0
    return reshape_color(np.clip(result, 0.0, 1.0))


def _load_fits(source: Path | BinaryIO, hdu: int, max_px: int) -> np.ndarray:
    with fits.open(
        source,
        memmap=isinstance(source, Path),
        do_not_scale_image_data=True,
    ) as hdul:
        if hdu < 0 or hdu >= len(hdul):
            raise PreviewUnreadable(f"HDU index {hdu} out of range (file has {len(hdul)} HDUs)")
        target = hdul[hdu]
        if target.data is None:
            raise PreviewUnreadable(f"HDU {hdu} contains no image data")
        raw = target.data
        while raw.ndim > 3 and raw.shape[0] == 1:
            raw = raw[0]
        if raw.ndim not in {2, 3}:
            raise PreviewUnreadable(f"Unsupported FITS array shape: {raw.shape}")
        channel_last = raw.ndim == 3 and raw.shape[-1] == 3 and raw.shape[0] != 3
        if channel_last:
            height, width = raw.shape[:2]
        else:
            height, width = raw.shape[-2:]
        step = max(1, math.ceil(max(height, width) / max_px))
        if raw.ndim == 2:
            sampled = raw[::step, ::step]
        elif channel_last:
            sampled = raw[::step, ::step, :]
        else:
            sampled = raw[:, ::step, ::step]
        blank = target.header.get("BLANK")
        blank_mask = sampled == blank if blank is not None else None
        bitpix = int(target.header["BITPIX"])
        bscale = float(target.header.get("BSCALE", 1.0))
        bzero = float(target.header.get("BZERO", 0.0))
        return _normalize_fits_sample(
            sampled,
            bitpix=bitpix,
            bscale=bscale,
            bzero=bzero,
            blank_mask=blank_mask,
        )


def _load_standard(source: Path | BinaryIO, max_px: int) -> np.ndarray:
    with Image.open(source) as opened:
        opened.draft("RGB", (max_px, max_px))
        factor = max(1, math.ceil(max(opened.size) / max_px))
        image = opened.reduce(factor) if factor > 1 else opened.copy()
        if image.mode in {"RGBA", "LA", "P"}:
            image = image.convert("RGB")
        elif image.mode not in {"RGB", "L", "I", "I;16"}:
            image = image.convert("RGB")
        mode = image.mode
        array = np.asarray(image)
    if array.ndim == 3:
        array = np.moveaxis(array[..., :3], -1, 0)
    if mode in {"I", "I;16"} or array.dtype == np.uint16:
        result = array.astype(np.float32) / 65535.0
    elif np.issubdtype(array.dtype, np.integer):
        result = array.astype(np.float32) / 255.0
    else:
        result = normalize_to_01(array).astype(np.float32)
    return reshape_color(np.clip(result, 0.0, 1.0))


def _decimate(data: np.ndarray, max_px: int) -> np.ndarray:
    height, width = data.shape[-2:]
    step = max(1, math.ceil(max(height, width) / max_px))
    small = data[::step, ::step] if data.ndim == 2 else data[:, ::step, ::step]
    return np.asarray(small, dtype=np.float32)


def _resolve(path: str) -> tuple[Path | BinaryIO, str, int]:
    try:
        source, kind, image_index, _cache_key = resolve_path(path)
        return source, kind, image_index
    except Exception as exc:
        detail = str(getattr(exc, "detail", exc))
        if getattr(exc, "status_code", None) == 404 or isinstance(exc, FileNotFoundError):
            raise PreviewNotFound(detail) from exc
        raise PreviewUnreadable(detail) from exc


def _render(path: str, hdu: int, max_px: int) -> bytes:
    source, kind, image_index = _resolve(path)
    try:
        if kind == "fits":
            data = _load_fits(source, hdu, max_px)
            stretch = "auto"
        elif kind == "standard":
            data = _load_standard(source, max_px)
            stretch = "none"
        elif kind == "xisf":
            data = _decimate(xisf_io.load_image_data(source, hdu), max_px)
            stretch = "auto"
        elif kind == "float_tiff":
            data = _decimate(standard_io.load_image_data(source), max_px)
            stretch = "auto"
        elif kind == "pxiproject":
            data = _decimate(pxiproject_io.load_image_data(source, image_index), max_px)
            stretch = "auto"
        else:
            raise PreviewUnreadable(f"Unsupported image type: {kind}")
        return render_array_jpeg(data, max_px, quality=85, stretch=stretch)
    except PreviewError:
        raise
    except FileNotFoundError as exc:
        raise PreviewNotFound(str(exc)) from exc
    except Exception as exc:
        raise PreviewUnreadable(str(exc)) from exc


def get_preview(
    path: str,
    *,
    hdu: int = 0,
    max_px: int = DEFAULT_MAX_PX,
    if_none_match: str | None = None,
) -> PreviewResult:
    """Return a cached or freshly rendered preview, or an ETag-only 304 result."""
    clamped = min(MAX_MAX_PX, max(MIN_MAX_PX, max_px))
    identity = _source_identity(path)
    key, etag = _etag(identity, hdu, clamped)
    if _etag_matches(if_none_match, etag):
        return PreviewResult(etag=etag, content=None, not_modified=True)
    cached = _cache_get(key)
    if cached is not None:
        return PreviewResult(etag=etag, content=cached)

    semaphore = _full_decode_sem if identity.decode_group == "full" else _reduced_decode_sem
    with semaphore:
        cached = _cache_get(key)
        if cached is None:
            cached = _render(path, hdu, clamped)
            _cache_put(key, cached)
    return PreviewResult(etag=etag, content=cached)


def _reset_for_tests() -> None:
    global _cache_bytes
    with _cache_lock:
        _cache.clear()
        _cache_bytes = 0
