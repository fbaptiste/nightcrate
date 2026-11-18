"""Recorded-value and colour-contract tests for the Image Analyzer."""

from __future__ import annotations

import io
import threading
import zipfile
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from httpx import ASGITransport, AsyncClient
from PIL import Image

from nightcrate.api import images as images_api
from nightcrate.main import app
from nightcrate.services import archive_io, fits_io, raw_io
from nightcrate.services.raw_support import UNAVAILABLE_MESSAGE, RawUnavailable
from tests.fixtures.raw_fixtures import write_cfa_dng


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


@pytest.fixture
def mosaic_fits(tmp_path: Path) -> Path:
    data = np.arange(10, 170, 10, dtype=np.uint16).reshape(4, 4)
    hdu = fits.PrimaryHDU(data)
    hdu.header["BAYERPAT"] = "RGGB"
    hdu.header["ROWORDER"] = "TOP-DOWN"
    path = tmp_path / "mosaic.fits"
    hdu.writeto(path)
    return path


@pytest.mark.anyio
async def test_mosaic_stats_histogram_png_and_pixel_are_colour_aware(
    client: AsyncClient, mosaic_fits: Path
):
    stats = await client.get("/api/images/stats", params={"path": str(mosaic_fits)})
    assert stats.status_code == 200
    body = stats.json()
    assert body["units"] == "adu"
    assert body["full_scale"] == 65535.0
    assert [channel["median"] for channel in body["channels"]] == [60.0, 85.0, 110.0]
    assert [channel["mean"] for channel in body["channels"]] == [60.0, 85.0, 110.0]

    histogram = await client.get(
        "/api/images/histogram", params={"path": str(mosaic_fits), "bins": 4}
    )
    assert histogram.status_code == 200
    assert [channel["bins"] for channel in histogram.json()["channels"]] == [
        [4, 0, 0, 0],
        [8, 0, 0, 0],
        [4, 0, 0, 0],
    ]

    rendered = await client.get(
        "/api/images/image",
        params={"path": str(mosaic_fits), "stretch": "linear"},
    )
    assert rendered.status_code == 200
    with Image.open(io.BytesIO(rendered.content)) as image:
        assert image.mode == "RGB"

    pixel = await client.get("/api/images/pixel", params={"path": str(mosaic_fits), "x": 0, "y": 0})
    assert pixel.json() == {
        "x": 0,
        "y": 0,
        "color": False,
        "K": 10.0,
        "units": "adu",
        "site_colour": "R",
    }


@pytest.mark.anyio
async def test_histogram_clips_negative_float_samples_into_first_bin(
    client: AsyncClient, tmp_path: Path
):
    path = tmp_path / "negative-float.fits"
    fits.PrimaryHDU(np.array([[-0.25, 0.0, 0.5, 1.0]], dtype=np.float32)).writeto(path)

    response = await client.get("/api/images/histogram", params={"path": str(path), "bins": 4})

    assert response.status_code == 200
    bins = response.json()["channels"][0]["bins"]
    assert bins[0] == 2
    assert sum(bins) == 4


@pytest.mark.anyio
async def test_extensions_report_pattern_provenance(client: AsyncClient, mosaic_fits: Path):
    images_api._cache.clear()
    response = await client.get("/api/images/extensions", params={"path": str(mosaic_fits)})
    colour = response.json()[0]["colour"]
    assert colour == {
        "kind": "mosaic",
        "pattern": "RGGB",
        "source": "fits_bayerpat",
        "detail": "BAYERPAT",
        "assumptions": [],
    }
    assert images_api._cache == {}


@pytest.mark.anyio
async def test_extensions_do_not_decode_pixels(client: AsyncClient, mosaic_fits: Path, monkeypatch):
    monkeypatch.setattr(
        images_api,
        "_get_cached_image",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("pixels decoded")),
    )

    response = await client.get("/api/images/extensions", params={"path": str(mosaic_fits)})

    assert response.status_code == 200
    assert response.json()[0]["colour"]["pattern"] == "RGGB"


@pytest.mark.anyio
async def test_extensions_read_metadata_off_event_loop(
    client: AsyncClient, mosaic_fits: Path, monkeypatch
):
    event_loop_thread = threading.get_ident()
    reader_threads = []
    original = fits_io.list_extensions

    def list_extensions(source):
        reader_threads.append(threading.get_ident())
        return original(source)

    monkeypatch.setattr(fits_io, "list_extensions", list_extensions)
    response = await client.get("/api/images/extensions", params={"path": str(mosaic_fits)})

    assert response.status_code == 200
    assert reader_threads and reader_threads[0] != event_loop_thread


@pytest.mark.anyio
async def test_colour_fits_ignores_stale_pattern_keyword(client: AsyncClient, tmp_path: Path):
    path = tmp_path / "colour-with-stale-pattern.fits"
    hdu = fits.PrimaryHDU(np.zeros((3, 4, 5), dtype=np.uint16))
    hdu.header["BAYERPAT"] = "RGGB"
    hdu.writeto(path)

    response = await client.get("/api/images/extensions", params={"path": str(path)})

    assert response.status_code == 200
    assert response.json()[0]["colour"]["kind"] == "colour"
    assert response.json()[0]["colour"]["pattern"] is None


@pytest.mark.anyio
async def test_float_tiff_extension_uses_sample_count_without_decoding(
    client: AsyncClient, tmp_path: Path, monkeypatch
):
    import tifffile

    path = tmp_path / "mono-float.tiff"
    tifffile.imwrite(path, np.zeros((4, 5), dtype=np.float32))
    monkeypatch.setattr(
        images_api,
        "_get_cached_image",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("pixels decoded")),
    )

    response = await client.get("/api/images/extensions", params={"path": str(path)})

    assert response.status_code == 200
    assert response.json()[0]["colour"]["kind"] == "mono"


@pytest.mark.anyio
async def test_archived_extensions_extract_once(
    client: AsyncClient, mosaic_fits: Path, tmp_path: Path, monkeypatch
):
    archive = tmp_path / "images.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.write(mosaic_fits, "mosaic.fits")
    original = archive_io.extract_entry
    calls = []

    def extract(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(archive_io, "extract_entry", extract)
    response = await client.get(
        "/api/images/extensions", params={"path": f"{archive}::mosaic.fits"}
    )

    assert response.status_code == 200
    assert response.json()[0]["colour"]["pattern"] == "RGGB"
    assert len(calls) == 1


@pytest.mark.anyio
async def test_raw_header_route_reads_off_event_loop(
    client: AsyncClient, tmp_path: Path, monkeypatch
):
    path = tmp_path / "capture.dng"
    path.write_bytes(b"unused")
    event_loop_thread = threading.get_ident()
    reader_threads = []

    def read_header(_source):
        reader_threads.append(threading.get_ident())
        return []

    monkeypatch.setattr(raw_io, "read_header", read_header)
    response = await client.get("/api/images/header", params={"path": str(path)})

    assert response.status_code == 200
    assert reader_threads and reader_threads[0] != event_loop_thread


@pytest.mark.anyio
async def test_raw_extensions_use_layout_without_samples(
    client: AsyncClient, tmp_path: Path, monkeypatch
):
    path = tmp_path / "mono.dng"
    path.write_bytes(b"unused")
    monkeypatch.setattr(
        raw_io,
        "read_raw_layout",
        lambda _source: raw_io.RawLayout(None, (64.0,), 4095, (0, 0, 20, 10)),
    )
    monkeypatch.setattr(
        raw_io,
        "read_raw_samples",
        lambda _source: (_ for _ in ()).throw(AssertionError("full samples decoded")),
    )

    response = await client.get("/api/images/extensions", params={"path": str(path)})

    assert response.status_code == 200
    assert response.json()[0]["colour"]["kind"] == "mono"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "status"),
    [
        (raw_io.RawUnsupported("unsupported raw"), 422),
        (OSError("unreadable raw"), 422),
        (RuntimeError("unexpected bug"), 500),
    ],
)
async def test_image_reader_error_mapping(
    client: AsyncClient, tmp_path: Path, monkeypatch, error, status
):
    path = tmp_path / "capture.dng"
    path.write_bytes(b"unused")

    def fail(_source):
        raise error

    monkeypatch.setattr(raw_io, "read_header", fail)
    response = await client.get("/api/images/header", params={"path": str(path)})

    assert response.status_code == status
    assert response.json()["detail"] == (
        str(error) if status == 422 else "Internal processing error"
    )


def test_histogram_stride_bounds_a_61_megapixel_frame_without_allocating_it():
    height, width = 6388, 9576
    pixel_count = height * width
    stride = images_api._histogram_stride(pixel_count)
    sample_count = np.ceil(pixel_count / stride)

    assert sample_count <= images_api._HISTOGRAM_MAX_PIXELS
    assert sample_count > images_api._HISTOGRAM_MAX_PIXELS * 0.5


@pytest.mark.anyio
async def test_view_pattern_is_rejected_when_pattern_is_recorded(
    client: AsyncClient, mosaic_fits: Path
):
    response = await client.get(
        "/api/images/stats", params={"path": str(mosaic_fits), "pattern": "BGGR"}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "A colour pattern is already recorded for this image"


@pytest.mark.anyio
async def test_raw_header_edit_and_unavailable_messages_are_plain(
    client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path = tmp_path / "capture.dng"
    path.write_bytes(b"not needed")

    edited = await client.patch(
        "/api/images/header",
        json={"path": str(path), "operations": [{"op": "add", "key": "OBJECT"}]},
    )
    assert edited.status_code == 422
    assert edited.json()["detail"] == "Header editing is only supported for FITS files"

    def unavailable(_source):
        raise RawUnavailable(UNAVAILABLE_MESSAGE)

    monkeypatch.setattr("nightcrate.api.images.raw_io.read_header", unavailable)
    header = await client.get("/api/images/header", params={"path": str(path)})
    assert header.status_code == 422
    assert header.json()["detail"] == UNAVAILABLE_MESSAGE


@pytest.mark.anyio
async def test_raw_header_and_metadata(client: AsyncClient, tmp_path: Path):
    pytest.importorskip("rawpy")
    pytest.importorskip("exiv2")
    path = write_cfa_dng(
        tmp_path / "metadata.dng",
        np.full((32, 34), 2048, dtype=np.uint16),
        exif={
            "Exif.Photo.DateTimeOriginal": "2026:03:15 21:30:00",
            "Exif.Photo.OffsetTimeOriginal": "-07:00",
            "Exif.Photo.ExposureTime": "1/125",
            "Exif.Photo.ISOSpeedRatings": "400",
            "Exif.Image.Make": "NightCrate",
            "Exif.Image.Model": "Fixture",
        },
    )

    header = await client.get("/api/images/header", params={"path": str(path)})
    assert header.status_code == 200
    assert {card["group"] for card in header.json()} >= {"Capture", "Colour data", "EXIF"}

    metadata = await client.get("/api/images/metadata", params={"path": str(path)})
    assert metadata.status_code == 200
    canonical = metadata.json()["canonical"]
    assert canonical["captured_local"] == "2026-03-15T21:30:00"
    assert canonical["utc_offset_minutes"] == -420
    assert canonical["time_source"] == "exif_offset"
    assert canonical["exposure_time"] == 0.008
    assert canonical["iso"] == 400
    assert canonical["make"] == "NightCrate"
    assert canonical["model"] == "Fixture"
