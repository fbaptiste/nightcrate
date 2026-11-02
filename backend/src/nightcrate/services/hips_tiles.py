"""Render DSS2 colour sky images directly from HiPS tiles.

The pure planning and sampling functions follow the HiPS nested-pixel layout.
The asynchronous layer adds source failover, short outage windows, shared
in-flight requests and a bounded in-memory cache of validated JPEG tiles.
"""

from __future__ import annotations

import asyncio
import io
import logging
import math
import time
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import astropy.units as u
import httpx
import numpy as np
from astropy.wcs import WCS
from astropy.wcs.utils import proj_plane_pixel_scales
from astropy_healpix import lonlat_to_healpix
from numpy.typing import NDArray
from PIL import Image

from nightcrate.core.tasks import settle
from nightcrate.services import http_client

logger = logging.getLogger("nightcrate.hips_tiles")

HIPS_DSS2_COLOR = "CDS/P/DSS2/color"


@dataclass(frozen=True, slots=True)
class HipsTileSource:
    name: str
    root_url: str


HIPS_TILE_SOURCES = (
    HipsTileSource("cds", "https://alasky.cds.unistra.fr/DSS/DSSColor"),
    HipsTileSource("esa", "https://cdn.skies.esac.esa.int/DSSColor"),
)

TILE_WIDTH = 512
TILE_ORDER_SHIFT = 9
MAX_TILE_ORDER = 9
MAX_TILES_PER_IMAGE = 32
SOURCE_DOWN_S = 600.0
TILE_TIMEOUT_S = 20.0
TILE_CONNECT_TIMEOUT_S = 5.0
MAX_CONCURRENT_TILE_FETCHES = 8
MAX_CONCURRENT_RENDERS = 4
TILE_CACHE_MAX_BYTES = 64 * 1024 * 1024
JPEG_QUALITY = 90
RENDER_BAND_ROWS = 128

_SUBPIXEL_MASK = (1 << (2 * TILE_ORDER_SHIFT)) - 1
_ORDER_ZERO_PIXEL_DEG = math.degrees(math.sqrt(4 * math.pi / 12))


class TileUnavailable(RuntimeError):
    """No configured source could supply a requested tile."""


@dataclass(frozen=True, slots=True)
class TileBytes:
    jpeg: bytes
    source: str


@dataclass(frozen=True, slots=True)
class RenderedImage:
    jpeg: bytes
    sources: frozenset[str]


@dataclass(frozen=True, slots=True)
class RenderPlan:
    order: int
    tiles: tuple[int, ...]
    tile_index: NDArray[np.int32]
    fx: NDArray[np.float32]
    fy: NDArray[np.float32]
    valid: NDArray[np.bool_]
    width: int
    height: int


def tile_url(root_url: str, order: int, npix: int) -> str:
    directory = (npix // 10_000) * 10_000
    return f"{root_url}/Norder{order}/Dir{directory}/Npix{npix}.jpg"


def tile_order_for(scale_deg_per_px: float) -> int:
    """Return the coarsest tile order whose pixels meet the output scale."""
    if not math.isfinite(scale_deg_per_px) or scale_deg_per_px <= 0:
        raise ValueError("scale_deg_per_px must be positive and finite")
    order = math.ceil(math.log2(_ORDER_ZERO_PIXEL_DEG / (scale_deg_per_px * TILE_WIDTH)))
    return max(0, min(MAX_TILE_ORDER, order))


def _compact_even_bits(values: NDArray[np.int64]) -> NDArray[np.int64]:
    values = values & np.int64(0x55555555)
    values = (values | (values >> 1)) & np.int64(0x33333333)
    values = (values | (values >> 2)) & np.int64(0x0F0F0F0F)
    values = (values | (values >> 4)) & np.int64(0x00FF00FF)
    values = (values | (values >> 8)) & np.int64(0x0000FFFF)
    return values


def morton_split(sub: NDArray[np.int64]) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
    """Split interleaved nested-pixel bits into the HiPS ``ix`` and ``iy``."""
    values = np.asarray(sub, dtype=np.int64)
    return _compact_even_bits(values), _compact_even_bits(values >> 1)


def _geometry_for_order(
    ra_deg: NDArray[np.float64],
    dec_deg: NDArray[np.float64],
    valid: NDArray[np.bool_],
    order: int,
) -> tuple[NDArray[np.int64], NDArray[np.float64], NDArray[np.float64]]:
    pixel = np.zeros(ra_deg.size, dtype=np.int64)
    dx = np.zeros(ra_deg.size, dtype=np.float64)
    dy = np.zeros(ra_deg.size, dtype=np.float64)
    if valid.any():
        selected, selected_dx, selected_dy = lonlat_to_healpix(
            ra_deg[valid] * u.deg,
            dec_deg[valid] * u.deg,
            1 << (order + TILE_ORDER_SHIFT),
            return_offsets=True,
            order="nested",
        )
        pixel[valid] = selected
        dx[valid] = selected_dx
        dy[valid] = selected_dy
    return pixel, dx, dy


def _world_band(
    wcs: WCS, width: int, row_start: int, row_stop: int
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.bool_]]:
    yy, xx = np.indices((row_stop - row_start, width), dtype=np.float64)
    yy += row_start
    ra, dec = wcs.wcs_pix2world(xx.ravel(), yy.ravel(), 0)
    ra = np.asarray(ra, dtype=np.float64)
    dec = np.asarray(dec, dtype=np.float64)
    return ra, dec, np.isfinite(ra) & np.isfinite(dec)


def _tiles_for_order(
    wcs: WCS, width: int, height: int, order: int, band_rows: int
) -> tuple[int, ...]:
    tiles: set[int] = set()
    for row_start in range(0, height, band_rows):
        row_stop = min(row_start + band_rows, height)
        ra, dec, valid = _world_band(wcs, width, row_start, row_stop)
        pixel, _, _ = _geometry_for_order(ra, dec, valid, order)
        tiles.update(int(item) for item in np.unique((pixel >> (2 * TILE_ORDER_SHIFT))[valid]))
    return tuple(sorted(tiles))


def plan_render(
    wcs: WCS,
    width: int,
    height: int,
    *,
    max_tiles: int = MAX_TILES_PER_IMAGE,
    band_rows: int = RENDER_BAND_ROWS,
) -> RenderPlan:
    """Map output pixel centres to a capped set of HiPS tiles in row bands."""
    if width <= 0 or height <= 0:
        raise ValueError("render dimensions must be positive")
    if max_tiles < 1:
        raise ValueError("max_tiles must be at least 1")
    if band_rows < 1:
        raise ValueError("band_rows must be at least 1")

    scales = np.asarray(proj_plane_pixel_scales(wcs), dtype=np.float64)
    order = tile_order_for(float(np.max(np.abs(scales))))

    while True:
        tiles = _tiles_for_order(wcs, width, height, order, band_rows)
        if len(tiles) <= max_tiles:
            break
        if order == 0:
            raise ValueError(f"render needs {len(tiles)} tiles at order 0, above cap {max_tiles}")
        order -= 1

    size = width * height
    tile_index = np.zeros(size, dtype=np.int32)
    fx = np.zeros(size, dtype=np.float32)
    fy = np.zeros(size, dtype=np.float32)
    valid = np.zeros(size, dtype=np.bool_)
    tile_keys = np.asarray(tiles, dtype=np.int64)
    for row_start in range(0, height, band_rows):
        row_stop = min(row_start + band_rows, height)
        start = row_start * width
        stop = row_stop * width
        ra, dec, band_valid = _world_band(wcs, width, row_start, row_stop)
        pixel, dx, dy = _geometry_for_order(ra, dec, band_valid, order)
        tile = pixel >> (2 * TILE_ORDER_SHIFT)
        sub = pixel & _SUBPIXEL_MASK
        ix, iy = morton_split(sub)
        band_fx = (ix + dx - 0.5).astype(np.float32)
        band_fy = (iy + dy - 0.5).astype(np.float32)
        band_fx[~band_valid] = 0
        band_fy[~band_valid] = 0
        if band_valid.any():
            tile_index[start:stop][band_valid] = np.searchsorted(
                tile_keys, tile[band_valid]
            ).astype(np.int32)
        fx[start:stop] = band_fx
        fy[start:stop] = band_fy
        valid[start:stop] = band_valid
    return RenderPlan(
        order=order,
        tiles=tiles,
        tile_index=tile_index,
        fx=fx,
        fy=fy,
        valid=valid,
        width=width,
        height=height,
    )


def sample(
    plan: RenderPlan,
    tiles: Mapping[int, NDArray[np.uint8]] | NDArray[np.uint8],
    *,
    band_rows: int = RENDER_BAND_ROWS,
) -> NDArray[np.uint8]:
    """Bilinearly sample decoded tiles in row bands and return a top-down array."""
    if band_rows < 1:
        raise ValueError("band_rows must be at least 1")
    if not plan.tiles:
        return np.zeros((plan.height, plan.width, 3), dtype=np.uint8)
    if isinstance(tiles, np.ndarray):
        stack = tiles
    else:
        try:
            stack = np.stack([tiles[npix] for npix in plan.tiles])
        except KeyError as exc:
            raise ValueError(f"missing decoded tile {exc.args[0]}") from exc
    expected = (len(plan.tiles), TILE_WIDTH, TILE_WIDTH, 3)
    if stack.shape != expected or stack.dtype != np.uint8:
        raise ValueError(f"decoded tiles must have shape {expected} and dtype uint8")

    image = np.zeros((plan.height, plan.width, 3), dtype=np.uint8)
    for row_start in range(0, plan.height, band_rows):
        row_stop = min(row_start + band_rows, plan.height)
        start = row_start * plan.width
        stop = row_stop * plan.width
        row = np.clip(plan.fx[start:stop], 0, TILE_WIDTH - 1)
        column = np.clip(plan.fy[start:stop], 0, TILE_WIDTH - 1)
        row0 = np.floor(row).astype(np.int32)
        column0 = np.floor(column).astype(np.int32)
        row1 = np.minimum(row0 + 1, TILE_WIDTH - 1)
        column1 = np.minimum(column0 + 1, TILE_WIDTH - 1)
        row_weight = (row - row0).astype(np.float32)[:, None]
        column_weight = (column - column0).astype(np.float32)[:, None]
        index = plan.tile_index[start:stop]

        output = stack[index, row0, column0].astype(np.float32)
        output *= (1 - row_weight) * (1 - column_weight)
        output += stack[index, row1, column0] * row_weight * (1 - column_weight)
        output += stack[index, row0, column1] * (1 - row_weight) * column_weight
        output += stack[index, row1, column1] * row_weight * column_weight
        output[~plan.valid[start:stop]] = 0
        image[row_start:row_stop] = (
            np.clip(np.rint(output), 0, 255)
            .astype(np.uint8)
            .reshape(row_stop - row_start, plan.width, 3)
        )
    return image[::-1]


def encode_jpeg(rgb: NDArray[np.uint8]) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(rgb).save(buffer, format="JPEG", quality=JPEG_QUALITY)
    return buffer.getvalue()


def thumbnail_wcs(ra_deg: float, dec_deg: float, fov_deg: float, width: int, height: int) -> WCS:
    if width <= 0 or height <= 0 or fov_deg <= 0:
        raise ValueError("thumbnail dimensions and field of view must be positive")
    scale = fov_deg / max(width, height)
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crval = [ra_deg, dec_deg]
    wcs.wcs.cdelt = [-scale, scale]
    wcs.wcs.crpix = [(width + 1) / 2, (height + 1) / 2]
    wcs.wcs.cunit = ["deg", "deg"]
    wcs.array_shape = (height, width)
    return wcs


HealthStatus = Literal["unknown", "up", "probing", "down"]


@dataclass(slots=True)
class _SourceHealth:
    status: HealthStatus = "unknown"
    down_until: float = 0.0
    probe_done: asyncio.Future[None] | None = None
    last_error: str | None = None


_source_health: dict[str, _SourceHealth] = {
    source.name: _SourceHealth() for source in HIPS_TILE_SOURCES
}
_in_flight: dict[tuple[int, int], asyncio.Task[TileBytes]] = {}
_tile_cache: OrderedDict[tuple[int, int], TileBytes] = OrderedDict()
_tile_cache_bytes = 0
_tile_fetch_semaphore = asyncio.Semaphore(MAX_CONCURRENT_TILE_FETCHES)
_render_semaphore = asyncio.Semaphore(MAX_CONCURRENT_RENDERS)


def _clock() -> float:
    return time.monotonic()


def reset_state() -> None:
    """Reset module state between tests without touching any disk cache."""
    global _tile_cache_bytes, _tile_fetch_semaphore, _render_semaphore
    for task in _in_flight.values():
        task.cancel()
    _in_flight.clear()
    _tile_cache.clear()
    _tile_cache_bytes = 0
    _source_health.clear()
    _source_health.update({source.name: _SourceHealth() for source in HIPS_TILE_SOURCES})
    _tile_fetch_semaphore = asyncio.Semaphore(MAX_CONCURRENT_TILE_FETCHES)
    _render_semaphore = asyncio.Semaphore(MAX_CONCURRENT_RENDERS)


def _finish_probe(health: _SourceHealth) -> None:
    future = health.probe_done
    health.probe_done = None
    if future is not None and not future.done():
        future.set_result(None)


def _mark_up(health: _SourceHealth, *, error: str | None = None) -> None:
    health.status = "up"
    health.down_until = 0.0
    health.last_error = error
    _finish_probe(health)


def _mark_unknown(health: _SourceHealth, error: str) -> None:
    health.status = "unknown"
    health.down_until = 0.0
    health.last_error = error
    _finish_probe(health)


def _mark_down(source: HipsTileSource, health: _SourceHealth, error: str) -> None:
    health.status = "down"
    health.down_until = _clock() + SOURCE_DOWN_S
    health.last_error = error
    _finish_probe(health)
    logger.warning("[hips_tiles] source=%s down for %.0f s: %s", source.name, SOURCE_DOWN_S, error)


def _decode_tile(jpeg: bytes) -> NDArray[np.uint8]:
    with Image.open(io.BytesIO(jpeg)) as image:
        if image.format != "JPEG" or image.size != (TILE_WIDTH, TILE_WIDTH):
            raise ValueError(
                f"expected a {TILE_WIDTH}x{TILE_WIDTH} JPEG, got {image.format} {image.size}"
            )
        image.load()
        array = np.asarray(image.convert("RGB"), dtype=np.uint8)
    if array.shape != (TILE_WIDTH, TILE_WIDTH, 3):
        raise ValueError(f"decoded tile has unexpected shape {array.shape}")
    return array


def _is_source_timeout(exc: BaseException) -> bool:
    return isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout))


async def _request_source(
    source: HipsTileSource, order: int, npix: int, *, probing: bool
) -> TileBytes:
    health = _source_health[source.name]
    try:
        async with _tile_fetch_semaphore:
            response = await http_client.get(
                tile_url(source.root_url, order, npix),
                attempts=1,
                timeout=TILE_TIMEOUT_S,
                connect_timeout=TILE_CONNECT_TIMEOUT_S,
                follow_redirects=True,
                label=f"HiPS {source.name} order={order} npix={npix}",
            )
        if response.status_code != 200:
            error = f"HTTP {response.status_code}"
            if probing:
                _mark_up(health, error=error)
            else:
                health.last_error = error
            raise TileUnavailable(error)
        try:
            await _in_thread(_decode_tile, response.content)
        except (OSError, ValueError) as exc:
            error = f"invalid JPEG: {exc}"
            if probing:
                _mark_up(health, error=error)
            else:
                health.last_error = error
            raise TileUnavailable(error) from exc
    except asyncio.CancelledError:
        if probing:
            _mark_unknown(health, "probe cancelled")
        raise
    except Exception as exc:
        if _is_source_timeout(exc):
            _mark_down(source, health, f"{type(exc).__name__}: {exc}")
        elif isinstance(exc, TileUnavailable):
            pass
        elif probing:
            _mark_unknown(health, f"{type(exc).__name__}: {exc}")
        else:
            health.last_error = f"{type(exc).__name__}: {exc}"
        raise

    _mark_up(health)
    logger.debug("[hips_tiles] order=%d npix=%d source=%s", order, npix, source.name)
    return TileBytes(response.content, source.name)


def _source_error(source: HipsTileSource, health: _SourceHealth) -> str:
    if health.status == "down" and health.down_until > _clock():
        return health.last_error or "temporarily down"
    return health.last_error or f"source {health.status}"


async def _fetch_tile_uncached(order: int, npix: int) -> TileBytes:
    tried: set[str] = set()
    errors: dict[str, str] = {}
    while len(tried) < len(HIPS_TILE_SOURCES):
        probe_waiters: list[asyncio.Future[None]] = []
        chosen: tuple[HipsTileSource, bool] | None = None
        now = _clock()
        for source in HIPS_TILE_SOURCES:
            if source.name in tried:
                continue
            health = _source_health[source.name]
            if health.status == "down" and health.down_until <= now:
                health.status = "unknown"
                health.down_until = 0.0
            if health.status == "probing":
                if health.probe_done is not None:
                    probe_waiters.append(health.probe_done)
                continue
            if health.status == "down":
                errors[source.name] = _source_error(source, health)
                continue
            probing = health.status == "unknown"
            if probing:
                health.status = "probing"
                health.probe_done = asyncio.get_running_loop().create_future()
            chosen = source, probing
            break

        if chosen is None:
            if probe_waiters:
                await asyncio.wait(probe_waiters, return_when=asyncio.FIRST_COMPLETED)
                continue
            break

        source, probing = chosen
        tried.add(source.name)
        try:
            return await _request_source(source, order, npix, probing=probing)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - fail over on every source failure
            errors[source.name] = f"{type(exc).__name__}: {exc}"

    for source in HIPS_TILE_SOURCES:
        errors.setdefault(source.name, _source_error(source, _source_health[source.name]))
    detail = "; ".join(f"{source.name}: {errors[source.name]}" for source in HIPS_TILE_SOURCES)
    raise TileUnavailable(f"HiPS tile order={order} npix={npix} unavailable ({detail})")


def _cache_tile(key: tuple[int, int], tile: TileBytes) -> None:
    global _tile_cache_bytes
    previous = _tile_cache.pop(key, None)
    if previous is not None:
        _tile_cache_bytes -= len(previous.jpeg)
    _tile_cache[key] = tile
    _tile_cache_bytes += len(tile.jpeg)
    while _tile_cache_bytes > TILE_CACHE_MAX_BYTES and _tile_cache:
        _, evicted = _tile_cache.popitem(last=False)
        _tile_cache_bytes -= len(evicted.jpeg)


async def fetch_tile(order: int, npix: int) -> TileBytes:
    key = (order, npix)
    cached = _tile_cache.get(key)
    if cached is not None:
        _tile_cache.move_to_end(key)
        return cached

    task = _in_flight.get(key)
    if task is None:
        task = asyncio.create_task(_fetch_tile_uncached(order, npix))
        _in_flight[key] = task

        def finished(done: asyncio.Task[TileBytes]) -> None:
            if _in_flight.get(key) is done:
                _in_flight.pop(key, None)
            if not done.cancelled() and done.exception() is None:
                _cache_tile(key, done.result())

        task.add_done_callback(finished)
    return await asyncio.shield(task)


async def _in_thread(function, *args):
    """Do not release the owning concurrency permit before a thread exits."""
    worker = asyncio.create_task(asyncio.to_thread(function, *args))
    return await settle(worker)


def _finish_render(plan: RenderPlan, blobs: Mapping[int, bytes]) -> bytes:
    decoded = np.empty((len(plan.tiles), TILE_WIDTH, TILE_WIDTH, 3), dtype=np.uint8)
    for index, npix in enumerate(plan.tiles):
        decoded[index] = _decode_tile(blobs[npix])
    return encode_jpeg(sample(plan, decoded))


async def render(wcs: WCS, width: int, height: int) -> RenderedImage:
    async with _render_semaphore:
        plan = await _in_thread(plan_render, wcs, width, height)
        fetched = await asyncio.gather(*(fetch_tile(plan.order, npix) for npix in plan.tiles))
        blobs = {npix: tile.jpeg for npix, tile in zip(plan.tiles, fetched, strict=True)}
        jpeg = await _in_thread(_finish_render, plan, blobs)
        return RenderedImage(jpeg, frozenset(tile.source for tile in fetched))
