from __future__ import annotations

import asyncio
import io
import threading
from functools import cache

import astropy.units as u
import httpx
import numpy as np
import pytest
from astropy_healpix import healpix_to_lonlat
from PIL import Image

from nightcrate.services import hips_tiles, http_client


@pytest.fixture(autouse=True)
def _clean_state():
    hips_tiles.reset_state()
    yield
    hips_tiles.reset_state()


def _jpeg(rgb: tuple[int, int, int] = (30, 60, 90)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (hips_tiles.TILE_WIDTH, hips_tiles.TILE_WIDTH), rgb).save(
        buffer, "JPEG", quality=100
    )
    return buffer.getvalue()


def _mock_http(monkeypatch, handler) -> None:
    original = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        http_client.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=transport, **kwargs),
    )


def test_tile_url_uses_hips_directory_groups():
    assert (
        hips_tiles.tile_url("https://example.test/root", 7, 12_345)
        == "https://example.test/root/Norder7/Dir10000/Npix12345.jpg"
    )


@pytest.mark.parametrize(
    ("scale", "order"),
    [
        (0.5 / 800, 8),
        (2.0 / 800, 6),
        (8.0 / 1024, 4),
        (100.0, 0),
        (1e-12, 9),
    ],
)
def test_tile_order_for_tiers_and_clamps(scale: float, order: int):
    assert hips_tiles.tile_order_for(scale) == order


def _interleave(ix: int, iy: int) -> int:
    result = 0
    for bit in range(9):
        result |= ((ix >> bit) & 1) << (2 * bit)
        result |= ((iy >> bit) & 1) << (2 * bit + 1)
    return result


def test_morton_split_recovers_even_and_odd_coordinates():
    pairs = [(0, 0), (1, 2), (511, 0), (173, 402), (511, 511)]
    packed = np.asarray([_interleave(ix, iy) for ix, iy in pairs], dtype=np.int64)
    ix, iy = hips_tiles.morton_split(packed)
    assert ix.tolist() == [pair[0] for pair in pairs]
    assert iy.tolist() == [pair[1] for pair in pairs]


def test_thumbnail_wcs_is_north_up_east_left_and_centred():
    wcs = hips_tiles.thumbnail_wcs(83.8, -5.4, 2.0, 200, 100)
    assert wcs.wcs.crval.tolist() == pytest.approx([83.8, -5.4])
    assert wcs.wcs.cdelt.tolist() == pytest.approx([-0.01, 0.01])
    assert wcs.wcs.crpix.tolist() == pytest.approx([100.5, 50.5])
    assert list(wcs.wcs.ctype) == ["RA---TAN", "DEC--TAN"]


def test_plan_coarsens_to_tile_cap_and_rejects_impossible_cap(monkeypatch):
    wcs = hips_tiles.thumbnail_wcs(45.0, 20.0, 120.0, 40, 40)
    monkeypatch.setattr(hips_tiles, "tile_order_for", lambda scale: 9)
    plan = hips_tiles.plan_render(wcs, 40, 40, max_tiles=8)
    assert plan.order < 9
    assert len(plan.tiles) <= 8
    with pytest.raises(ValueError, match="above cap"):
        hips_tiles.plan_render(wcs, 40, 40, max_tiles=1)


def test_banded_plan_and_sample_are_bit_identical_to_single_band():
    width, height = 160, 260
    wcs = hips_tiles.thumbnail_wcs(45.0, 20.0, 12.0, width, height)
    banded = hips_tiles.plan_render(wcs, width, height)
    single_band = hips_tiles.plan_render(wcs, width, height, band_rows=height)

    assert len(banded.tiles) > 1
    assert banded.order == single_band.order
    assert banded.tiles == single_band.tiles
    assert np.array_equal(banded.tile_index, single_band.tile_index)
    assert np.array_equal(banded.fx, single_band.fx)
    assert np.array_equal(banded.fy, single_band.fy)
    assert np.array_equal(banded.valid, single_band.valid)

    row, column = np.indices((hips_tiles.TILE_WIDTH, hips_tiles.TILE_WIDTH))
    tiles = {}
    for npix in banded.tiles:
        tile = np.empty((hips_tiles.TILE_WIDTH, hips_tiles.TILE_WIDTH, 3), dtype=np.uint8)
        tile[..., 0] = (row + npix) % 256
        tile[..., 1] = (column + npix * 3) % 256
        tile[..., 2] = (row + column + npix * 7) % 256
        tiles[npix] = tile
    assert np.array_equal(
        hips_tiles.sample(banded, tiles),
        hips_tiles.sample(single_band, tiles, band_rows=height),
    )


def test_sample_is_bilinear_uses_row_ix_column_iy_and_flips_output():
    tile = np.zeros((512, 512, 3), dtype=np.uint8)
    row, column = np.indices((512, 512))
    tile[..., 0] = row % 256
    tile[..., 1] = column % 256
    plan = hips_tiles.RenderPlan(
        order=0,
        tiles=(0,),
        tile_index=np.zeros(2, dtype=np.int32),
        fx=np.asarray([10.25, 20.75], dtype=np.float32),
        fy=np.asarray([30.5, 40.25], dtype=np.float32),
        valid=np.ones(2, dtype=np.bool_),
        width=1,
        height=2,
    )
    result = hips_tiles.sample(plan, {0: tile})
    assert result[:, 0, :2].tolist() == [[21, 40], [10, 30]]


def test_nonfinite_wcs_positions_stay_black(monkeypatch):
    class NonfiniteWcs:
        def wcs_pix2world(self, x, y, origin):
            ra = np.zeros_like(x)
            dec = np.zeros_like(y)
            ra[0] = np.nan
            return ra, dec

    monkeypatch.setattr(hips_tiles, "proj_plane_pixel_scales", lambda wcs: [1.0, 1.0])
    plan = hips_tiles.plan_render(NonfiniteWcs(), 9, 9)
    assert (~plan.valid).sum() == 1
    tiles = {npix: np.full((512, 512, 3), 255, dtype=np.uint8) for npix in plan.tiles}
    rendered = hips_tiles.sample(plan, tiles)
    assert (rendered.reshape(-1, 3)[~plan.valid.reshape(9, 9)[::-1].ravel()] == 0).all()


def _sky_rgb(lon_rad, lat_rad) -> np.ndarray:
    red = 120 + 35 * np.cos(lat_rad) * np.cos(lon_rad)
    green = 110 + 30 * np.cos(lat_rad) * np.sin(lon_rad)
    blue = 100 + 25 * np.sin(lat_rad)
    return np.clip(np.rint(np.stack((red, green, blue), axis=-1)), 0, 255).astype(np.uint8)


@cache
def _painted_tile(order: int, npix: int) -> np.ndarray:
    row, column = np.indices((512, 512), dtype=np.float64)
    lon, lat = healpix_to_lonlat(
        npix,
        1 << order,
        dx=(row + 0.5) / 512,
        dy=(column + 0.5) / 512,
        order="nested",
    )
    painted = _sky_rgb(lon.to_value(u.rad), lat.to_value(u.rad))
    encoded = io.BytesIO()
    Image.fromarray(painted).save(encoded, "JPEG", quality=100, subsampling=0)
    return np.asarray(Image.open(io.BytesIO(encoded.getvalue())).convert("RGB"))


@pytest.mark.parametrize(
    ("ra", "dec"),
    [
        (180.0, 0.0),
        (45.0, 0.0),
        (10.0, 41.8),
        (220.0, -41.8),
        (12.0, 88.0),
        (190.0, -88.0),
        (0.2, 15.0),
        (359.8, -15.0),
    ],
)
def test_orientation_matches_independent_healpix_oracle(ra: float, dec: float):
    width = height = 12
    wcs = hips_tiles.thumbnail_wcs(ra, dec, 6.0, width, height)
    plan = hips_tiles.plan_render(wcs, width, height)
    actual = hips_tiles.sample(plan, {npix: _painted_tile(plan.order, npix) for npix in plan.tiles})
    if (ra, dec) == (45.0, 0.0):
        assert len(plan.tiles) == 4  # HiPS base-face corner
    yy, xx = np.indices((height, width), dtype=np.float64)
    lon, lat = wcs.wcs_pix2world(xx.ravel(), yy.ravel(), 0)
    expected = _sky_rgb(np.deg2rad(lon), np.deg2rad(lat)).reshape(height, width, 3)[::-1]
    valid = plan.valid.reshape(height, width)[::-1]
    assert np.max(np.abs(actual[valid].astype(int) - expected[valid].astype(int))) <= 2


def test_orientation_oracle_straddles_a_higher_order_tile_edge():
    lon, lat = healpix_to_lonlat(100, 16, dx=1.0, dy=0.5, order="nested")
    width = height = 24
    wcs = hips_tiles.thumbnail_wcs(lon.to_value(u.deg), lat.to_value(u.deg), 0.2, width, height)
    plan = hips_tiles.plan_render(wcs, width, height)
    assert plan.order == 4
    assert plan.tiles == (100, 101)
    actual = hips_tiles.sample(plan, {npix: _painted_tile(plan.order, npix) for npix in plan.tiles})
    yy, xx = np.indices((height, width), dtype=np.float64)
    expected_lon, expected_lat = wcs.wcs_pix2world(xx.ravel(), yy.ravel(), 0)
    expected = _sky_rgb(np.deg2rad(expected_lon), np.deg2rad(expected_lat)).reshape(
        height, width, 3
    )[::-1]
    assert np.max(np.abs(actual.astype(int) - expected.astype(int))) <= 2


def test_oracle_rejects_seven_wrong_tile_orientations_and_missing_output_flip():
    wcs = hips_tiles.thumbnail_wcs(37.0, 28.0, 6.0, 18, 18)
    plan = hips_tiles.plan_render(wcs, 18, 18)
    correct = {npix: _painted_tile(plan.order, npix) for npix in plan.tiles}
    baseline = hips_tiles.sample(plan, correct)
    yy, xx = np.indices((18, 18), dtype=np.float64)
    lon, lat = wcs.wcs_pix2world(xx.ravel(), yy.ravel(), 0)
    expected = _sky_rgb(np.deg2rad(lon), np.deg2rad(lat)).reshape(18, 18, 3)[::-1]
    valid = plan.valid.reshape(18, 18)[::-1]

    def oracle_error(image):
        return np.max(np.abs(image[valid].astype(int) - expected[valid].astype(int)))

    assert oracle_error(baseline) <= 2
    transforms = (
        lambda image: np.transpose(image, (1, 0, 2)),
        np.flipud,
        np.fliplr,
        lambda image: np.flipud(np.fliplr(image)),
        lambda image: np.rot90(image, 1),
        lambda image: np.rot90(image, 2),
        lambda image: np.rot90(image, 3),
    )
    for transform in transforms:
        wrong = hips_tiles.sample(plan, {key: transform(value) for key, value in correct.items()})
        assert oracle_error(wrong) > 2
    assert oracle_error(baseline[::-1]) > 2


@pytest.mark.asyncio
async def test_fetch_tile_prefers_cds_and_uses_one_attempt(monkeypatch):
    requests: list[str] = []

    def handler(request):
        requests.append(str(request.url))
        return httpx.Response(200, content=_jpeg())

    _mock_http(monkeypatch, handler)
    tile = await hips_tiles.fetch_tile(4, 123)
    assert tile.source == "cds"
    assert len(requests) == 1
    assert "alasky.cds.unistra.fr" in requests[0]


@pytest.mark.asyncio
async def test_connect_failure_marks_cds_down_and_fails_over_once(monkeypatch):
    requests: list[str] = []

    def handler(request):
        requests.append(request.url.host)
        if request.url.host == "alasky.cds.unistra.fr":
            raise httpx.ConnectError("offline", request=request)
        return httpx.Response(200, content=_jpeg())

    _mock_http(monkeypatch, handler)
    first = await hips_tiles.fetch_tile(4, 1)
    second = await hips_tiles.fetch_tile(4, 2)
    assert first.source == second.source == "esa"
    assert requests == [
        "alasky.cds.unistra.fr",
        "cdn.skies.esac.esa.int",
        "cdn.skies.esac.esa.int",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_response",
    [
        httpx.Response(404, content=b"missing"),
        httpx.Response(200, content=b"<html>not a jpeg</html>"),
        httpx.Response(200, content=b"\xff\xd8truncated"),
    ],
)
async def test_http_and_body_failures_try_esa_without_marking_cds_down(monkeypatch, bad_response):
    hosts: list[str] = []

    def handler(request):
        hosts.append(request.url.host)
        if request.url.host == "alasky.cds.unistra.fr":
            return bad_response
        return httpx.Response(200, content=_jpeg())

    _mock_http(monkeypatch, handler)
    assert (await hips_tiles.fetch_tile(3, 8)).source == "esa"
    assert hips_tiles._source_health["cds"].status == "up"
    assert hosts == ["alasky.cds.unistra.fr", "cdn.skies.esac.esa.int"]


@pytest.mark.asyncio
async def test_every_source_failure_names_each_source(monkeypatch):
    _mock_http(monkeypatch, lambda request: httpx.Response(503, content=b"down"))
    with pytest.raises(hips_tiles.TileUnavailable) as error:
        await hips_tiles.fetch_tile(2, 9)
    assert "cds:" in str(error.value)
    assert "esa:" in str(error.value)


@pytest.mark.asyncio
async def test_every_source_down_fails_without_another_request(monkeypatch):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("offline", request=request)

    _mock_http(monkeypatch, handler)
    with pytest.raises(hips_tiles.TileUnavailable):
        await hips_tiles.fetch_tile(2, 10)
    assert calls == 2
    with pytest.raises(hips_tiles.TileUnavailable):
        await hips_tiles.fetch_tile(2, 11)
    assert calls == 2


@pytest.mark.asyncio
async def test_expired_down_window_allows_exactly_one_concurrent_probe(monkeypatch):
    now = 100.0
    monkeypatch.setattr(hips_tiles, "_clock", lambda: now)
    cds_calls = 0
    original = httpx.AsyncClient

    def initial_handler(request):
        if request.url.host == "alasky.cds.unistra.fr":
            raise httpx.ConnectError("offline", request=request)
        return httpx.Response(200, content=_jpeg())

    _mock_http(monkeypatch, initial_handler)
    await hips_tiles.fetch_tile(2, 20)
    now += hips_tiles.SOURCE_DOWN_S + 1

    async_gate = asyncio.Event()

    async def probe_handler(request):
        nonlocal cds_calls
        if request.url.host == "alasky.cds.unistra.fr":
            cds_calls += 1
            await async_gate.wait()
            return httpx.Response(404, content=b"missing")
        return httpx.Response(200, content=_jpeg())

    transport = httpx.MockTransport(probe_handler)
    monkeypatch.setattr(
        http_client.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=transport, **kwargs),
    )
    tasks = [asyncio.create_task(hips_tiles.fetch_tile(2, 30 + n)) for n in range(8)]
    for _ in range(100):
        if cds_calls:
            break
        await asyncio.sleep(0)
    assert cds_calls == 1
    async_gate.set()
    await asyncio.gather(*tasks)
    assert cds_calls == 1
    assert hips_tiles._source_health["cds"].status == "up"


@pytest.mark.asyncio
async def test_cancelled_probe_returns_source_to_unknown(monkeypatch):
    entered = asyncio.Event()

    async def handler(request):
        entered.set()
        await asyncio.Event().wait()

    _mock_http(monkeypatch, handler)
    waiter = asyncio.create_task(hips_tiles.fetch_tile(2, 41))
    await entered.wait()
    hips_tiles._in_flight[(2, 41)].cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert hips_tiles._source_health["cds"].status == "unknown"


@pytest.mark.asyncio
async def test_shared_fetch_survives_one_waiter_cancellation(monkeypatch):
    gate = asyncio.Event()
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        await gate.wait()
        return httpx.Response(200, content=_jpeg())

    _mock_http(monkeypatch, handler)
    first = asyncio.create_task(hips_tiles.fetch_tile(3, 44))
    second = asyncio.create_task(hips_tiles.fetch_tile(3, 44))
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    gate.set()
    assert (await second).source == "cds"
    assert calls == 1


@pytest.mark.asyncio
async def test_tile_lru_respects_byte_cap_and_keeps_source(monkeypatch):
    jpeg = _jpeg()
    monkeypatch.setattr(hips_tiles, "TILE_CACHE_MAX_BYTES", len(jpeg) + 10)
    _mock_http(monkeypatch, lambda request: httpx.Response(200, content=jpeg))
    await hips_tiles.fetch_tile(1, 1)
    second = await hips_tiles.fetch_tile(1, 2)
    assert list(hips_tiles._tile_cache) == [(1, 2)]
    assert hips_tiles._tile_cache[(1, 2)].source == second.source == "cds"


@pytest.mark.asyncio
async def test_global_tile_request_limit_is_eight(monkeypatch):
    active = 0
    peak = 0

    async def handler(request):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return httpx.Response(200, content=_jpeg())

    _mock_http(monkeypatch, handler)
    await asyncio.gather(*(hips_tiles.fetch_tile(3, npix) for npix in range(20)))
    assert peak <= hips_tiles.MAX_CONCURRENT_TILE_FETCHES
    assert peak == hips_tiles.MAX_CONCURRENT_TILE_FETCHES


@pytest.mark.asyncio
async def test_render_limit_caps_whole_image_work_at_four(monkeypatch):
    active = 0
    peak = 0
    gate = asyncio.Event()
    empty_plan = hips_tiles.RenderPlan(
        order=0,
        tiles=(),
        tile_index=np.zeros(1, dtype=np.int32),
        fx=np.zeros(1, dtype=np.float32),
        fy=np.zeros(1, dtype=np.float32),
        valid=np.ones(1, dtype=np.bool_),
        width=1,
        height=1,
    )

    async def fake_in_thread(function, *args):
        nonlocal active, peak
        if function is hips_tiles.plan_render:
            active += 1
            peak = max(peak, active)
            await gate.wait()
            active -= 1
            return empty_plan
        return b"jpeg"

    monkeypatch.setattr(hips_tiles, "_in_thread", fake_in_thread)
    tasks = [
        asyncio.create_task(hips_tiles.render(object(), 1, 1))
        for _ in range(hips_tiles.MAX_CONCURRENT_RENDERS + 2)
    ]
    for _ in range(100):
        if active == hips_tiles.MAX_CONCURRENT_RENDERS:
            break
        await asyncio.sleep(0)
    assert peak == hips_tiles.MAX_CONCURRENT_RENDERS
    gate.set()
    await asyncio.gather(*tasks)


@pytest.mark.asyncio
async def test_repeated_cancellation_holds_render_permit_until_sampling_thread_exits(monkeypatch):
    sampling_started = threading.Event()
    release_sampling = threading.Event()
    empty_plan = hips_tiles.RenderPlan(
        order=0,
        tiles=(),
        tile_index=np.zeros(1, dtype=np.int32),
        fx=np.zeros(1, dtype=np.float32),
        fy=np.zeros(1, dtype=np.float32),
        valid=np.ones(1, dtype=np.bool_),
        width=1,
        height=1,
    )

    monkeypatch.setattr(hips_tiles, "plan_render", lambda *args: empty_plan)

    def blocking_sample(*args):
        sampling_started.set()
        assert release_sampling.wait(timeout=5)
        return np.zeros((1, 1, 3), dtype=np.uint8)

    monkeypatch.setattr(hips_tiles, "sample", blocking_sample)
    task = asyncio.create_task(hips_tiles.render(object(), 1, 1))
    cancelled = False
    try:
        for _ in range(1_000):
            if sampling_started.is_set():
                break
            await asyncio.sleep(0.001)
        assert sampling_started.is_set()
        assert hips_tiles._render_semaphore._value == hips_tiles.MAX_CONCURRENT_RENDERS - 1

        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)

        assert not task.done()
        assert hips_tiles._render_semaphore._value == hips_tiles.MAX_CONCURRENT_RENDERS - 1
    finally:
        release_sampling.set()
        try:
            await task
        except asyncio.CancelledError:
            cancelled = True

    assert cancelled
    assert hips_tiles._render_semaphore._value == hips_tiles.MAX_CONCURRENT_RENDERS
