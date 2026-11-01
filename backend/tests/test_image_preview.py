"""Service and route tests for bounded image previews."""

from __future__ import annotations

import hashlib
import io
import struct
import zipfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from astropy.io import fits
from httpx import ASGITransport, AsyncClient
from PIL import Image

from nightcrate.main import app
from nightcrate.services import image_preview
from nightcrate.services.catalog_thumbnail import render_array_jpeg


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


@pytest.fixture(autouse=True)
def reset_preview_cache():
    image_preview._reset_for_tests()
    yield
    image_preview._reset_for_tests()


def _jpeg(content: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(content))
    image.load()
    return image


def _fits_bytes() -> bytes:
    buffer = io.BytesIO()
    fits.HDUList(
        [
            fits.PrimaryHDU(np.tile(np.arange(40, dtype=np.uint16), (20, 1))),
            fits.ImageHDU(np.tile(np.arange(20, dtype=np.uint16)[:, None], (1, 40))),
        ]
    ).writeto(buffer)
    return buffer.getvalue()


def _make_xisf(data: np.ndarray) -> bytes:
    height, width = data.shape
    pixels = np.asarray(data, dtype=np.float32).tobytes()
    offset = 4096
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<xisf version="1.0" xmlns="http://www.pixinsight.com/xisf">
<Image geometry="{width}:{height}:1" sampleFormat="Float32" colorSpace="Gray"
       location="attachment:{offset}:{len(pixels)}" />
</xisf>""".encode()
    header = b"XISF0100" + struct.pack("<I", len(xml)) + b"\0" * 4 + xml
    return header + b"\0" * (offset - len(header)) + pixels


def _png_bytes(value: int, size: tuple[int, int] = (30, 20)) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(np.full((size[1], size[0]), value, dtype=np.uint8)).save(buffer, format="PNG")
    return buffer.getvalue()


def _project_xml(paths: list[Path]) -> str:
    namespace = "http://www.pixinsight.com/xosm"
    windows = "".join(
        f'<ImageWindow currentView="Image_{index}" filePath="{path}">'
        f'<MainView id="Image_{index}" stfEnabled="1" />'
        "</ImageWindow>"
        for index, path in enumerate(paths)
    )
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<xosm version="1.2" xmlns="{namespace}">'
        '<Project><features compression="none" /></Project>'
        f"{windows}</xosm>"
    )


@pytest.mark.anyio
async def test_fits_hdus_and_archive_hdus_have_distinct_etags(client, tmp_path):
    path = tmp_path / "multi.fits"
    payload = _fits_bytes()
    path.write_bytes(payload)

    first = await client.get("/api/images/preview", params={"path": str(path), "hdu": 0})
    second = await client.get("/api/images/preview", params={"path": str(path), "hdu": 1})
    assert first.status_code == second.status_code == 200
    assert first.headers["etag"] != second.headers["etag"]
    assert first.content != second.content

    archive = tmp_path / "images.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("multi.fits", payload)
    virtual = f"{archive}::multi.fits"
    archived_first = await client.get("/api/images/preview", params={"path": virtual, "hdu": 0})
    archived_second = await client.get("/api/images/preview", params={"path": virtual, "hdu": 1})
    assert archived_first.status_code == archived_second.status_code == 200
    assert archived_first.headers["etag"] != archived_second.headers["etag"]


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["unsigned", "scaled_blank", "color"])
async def test_fits_scaling_color_and_orientation(client, tmp_path, kind):
    path = tmp_path / f"{kind}.fits"
    if kind == "unsigned":
        data = np.tile(np.arange(40, dtype=np.uint16), (20, 1))
        fits.PrimaryHDU(data).writeto(path)
    elif kind == "scaled_blank":
        data = np.tile(np.arange(40, dtype=np.int16), (20, 1))
        data[0, 0] = -32768
        hdu = fits.PrimaryHDU(data)
        hdu.header["BSCALE"] = 2.0
        hdu.header["BZERO"] = 100.0
        hdu.header["BLANK"] = -32768
        hdu.writeto(path)
    else:
        data = np.stack(
            [
                np.tile(np.arange(40, dtype=np.uint16), (20, 1)),
                np.full((20, 40), 100, dtype=np.uint16),
                np.flipud(np.tile(np.arange(20, dtype=np.uint16)[:, None], (1, 40))),
            ]
        )
        fits.PrimaryHDU(data).writeto(path)

    response = await client.get("/api/images/preview", params={"path": str(path)})

    assert response.status_code == 200, response.text
    image = _jpeg(response.content)
    assert image.size == (40, 20)
    assert image.mode == ("RGB" if kind == "color" else "L")


@pytest.mark.anyio
async def test_channel_last_fits_preview_is_color_bounded_and_upright(client, tmp_path):
    path = tmp_path / "channel-last.fits"
    data = np.zeros((300, 600, 3), dtype=np.uint16)
    data[:150, :, 0] = 65535
    data[150:, :, 2] = 65535
    fits.PrimaryHDU(data).writeto(path)

    response = await client.get(
        "/api/images/preview",
        params={"path": str(path), "max_px": 256},
    )

    assert response.status_code == 200, response.text
    image = _jpeg(response.content)
    pixels = np.asarray(image)
    assert image.mode == "RGB"
    assert max(image.size) <= 256
    assert image.width > image.height
    assert pixels[10, 10, 0] > pixels[10, 10, 2]
    assert pixels[-10, 10, 2] > pixels[-10, 10, 0]


@pytest.mark.anyio
async def test_preview_tone_handling_matches_rendered_images(client, tmp_path):
    stretched = tmp_path / "stretched.fits"
    fits.PrimaryHDU(np.linspace(0.2, 0.8, 4096, dtype=np.float32).reshape(64, 64)).writeto(
        stretched
    )
    stretched_response = await client.get("/api/images/preview", params={"path": str(stretched)})
    stretched_pixels = np.asarray(_jpeg(stretched_response.content).convert("L"))
    assert float(np.mean(stretched_pixels)) == pytest.approx(0.5 * 255, abs=8)

    rng = np.random.default_rng(42)
    linear_data = np.clip(rng.normal(1000, 80, (128, 128)), 0, 65535).astype(np.uint16)
    linear_data[64, 64] = 60000
    linear = tmp_path / "linear.fits"
    fits.PrimaryHDU(linear_data).writeto(linear)
    linear_response = await client.get("/api/images/preview", params={"path": str(linear)})
    linear_pixels = np.asarray(_jpeg(linear_response.content).convert("L"))
    assert float(np.median(linear_pixels)) == pytest.approx(0.25 * 255, abs=15)


@pytest.mark.anyio
async def test_standard_images_are_encoded_without_a_second_stretch(client, tmp_path):
    eight_bit = tmp_path / "known-mean.png"
    eight_bit_data = np.tile(np.arange(64, 128, dtype=np.uint8), (64, 1))
    Image.fromarray(eight_bit_data).save(eight_bit)
    eight_response = await client.get("/api/images/preview", params={"path": str(eight_bit)})
    eight_pixels = np.asarray(_jpeg(eight_response.content).convert("L"))
    assert float(np.mean(eight_pixels)) == pytest.approx(float(np.mean(eight_bit_data)), abs=3)

    sixteen_bit = tmp_path / "sixteen-bit.png"
    Image.fromarray(np.full((32, 32), 32768, dtype=np.uint16)).save(sixteen_bit)
    sixteen_response = await client.get("/api/images/preview", params={"path": str(sixteen_bit)})
    sixteen_pixels = np.asarray(_jpeg(sixteen_response.content).convert("L"))
    assert float(np.mean(sixteen_pixels)) == pytest.approx(0.5 * 255, abs=3)


def test_unsigned_fits_normalization_uses_logical_bit_depth():
    raw = np.array([[32767, -31768, -32768]], dtype=np.int16)
    normalized = image_preview._normalize_fits_sample(
        raw,
        bitpix=16,
        bscale=1.0,
        bzero=32768.0,
        blank_mask=np.array([[False, False, True]]),
    )
    assert normalized[0, 0] == pytest.approx(1.0)
    assert normalized[0, 1] == pytest.approx(1000 / 65535)
    assert normalized[0, 2] == 0.0


def test_catalog_thumbnail_default_stf_bytes_are_unchanged():
    fixture = np.linspace(0.0, 0.08, 600, dtype=np.float32).reshape(20, 30)
    default = render_array_jpeg(fixture, 96)
    assert default == render_array_jpeg(fixture, 96, stretch="stf")
    assert hashlib.sha256(default).hexdigest() == (
        "088f248e4f99c2fee775ceaa6af8ceabf1b9b9dbec1c30b8b5d6b973b37e3b5b"
    )


@pytest.mark.anyio
async def test_xisf_and_png_render(client, tmp_path):
    xisf = tmp_path / "small.xisf"
    xisf.write_bytes(_make_xisf(np.linspace(0, 1, 600).reshape(20, 30)))
    png = tmp_path / "small.png"
    Image.fromarray(np.tile(np.arange(30, dtype=np.uint8), (20, 1))).save(png)

    for path in (xisf, png):
        response = await client.get("/api/images/preview", params={"path": str(path)})
        assert response.status_code == 200, response.text
        assert response.headers["content-type"] == "image/jpeg"
        assert _jpeg(response.content).size == (30, 20)


@pytest.mark.anyio
async def test_archive_members_and_project_images_have_distinct_keys(client, tmp_path):
    archive = tmp_path / "two.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("one.png", _png_bytes(20))
        zipped.writestr("two.png", _png_bytes(80))
    one = await client.get("/api/images/preview", params={"path": f"{archive}::one.png"})
    two = await client.get("/api/images/preview", params={"path": f"{archive}::two.png"})
    assert one.headers["etag"] != two.headers["etag"]

    first_xisf = tmp_path / "first.xisf"
    second_xisf = tmp_path / "second.xisf"
    first_xisf.write_bytes(_make_xisf(np.linspace(0, 1, 600).reshape(20, 30)))
    second_xisf.write_bytes(_make_xisf(np.linspace(1, 0, 600).reshape(20, 30)))
    project = tmp_path / "test.pxiproject"
    project.mkdir()
    project.joinpath("project.xosm").write_text(
        _project_xml([first_xisf, second_xisf]), encoding="utf-8"
    )
    first = await client.get("/api/images/preview", params={"path": f"{project}::0"})
    second = await client.get("/api/images/preview", params={"path": f"{project}::1"})
    assert first.status_code == second.status_code == 200
    assert first.headers["etag"] != second.headers["etag"]


@pytest.mark.anyio
async def test_etag_changes_revalidates_and_cache_hit_skips_reload(client, tmp_path):
    path = tmp_path / "source.png"
    path.write_bytes(_png_bytes(20))
    with patch("nightcrate.services.image_preview._render", wraps=image_preview._render) as render:
        first = await client.get("/api/images/preview", params={"path": str(path)})
        cached = await client.get("/api/images/preview", params={"path": str(path)})
        assert render.call_count == 1
    assert cached.content == first.content
    assert first.headers["etag"].startswith('"') and first.headers["etag"].endswith('"')
    not_modified = await client.get(
        "/api/images/preview",
        params={"path": str(path)},
        headers={"If-None-Match": f"W/{first.headers['etag']}"},
    )
    assert not_modified.status_code == 304
    assert not_modified.headers["cache-control"] == "no-cache"

    path.write_bytes(_png_bytes(90, size=(31, 20)))
    changed = await client.get("/api/images/preview", params={"path": str(path)})
    assert changed.headers["etag"] != first.headers["etag"]


@pytest.mark.anyio
async def test_missing_unreadable_and_clamped_size(client, tmp_path):
    missing = await client.get(
        "/api/images/preview", params={"path": str(tmp_path / "missing.fits")}
    )
    assert missing.status_code == 404

    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    unreadable = await client.get("/api/images/preview", params={"path": str(bad)})
    assert unreadable.status_code == 422

    large = tmp_path / "large.png"
    large.write_bytes(_png_bytes(50, size=(600, 300)))
    preview = await client.get("/api/images/preview", params={"path": str(large), "max_px": 100})
    assert max(_jpeg(preview.content).size) <= 256


def test_cache_byte_budget_is_enforced(monkeypatch):
    monkeypatch.setattr(image_preview, "_CACHE_MAX_BYTES", 10)
    image_preview._cache_put("one", b"123456")
    image_preview._cache_put("two", b"abcdef")
    assert sum(len(value) for value in image_preview._cache.values()) <= 10
    assert "one" not in image_preview._cache
