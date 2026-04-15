"""Tests for the image viewer API endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# GET /api/images/header
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_header_returns_fits_keywords(client, tmp_fits_mono):
    """Header endpoint should return FITS keyword cards including those we set."""
    resp = await client.get(
        "/api/images/header",
        params={"path": str(tmp_fits_mono)},
    )
    assert resp.status_code == 200
    cards = resp.json()
    assert isinstance(cards, list)
    assert len(cards) > 0

    # Each card should have key, value, comment fields
    for card in cards:
        assert "key" in card
        assert "value" in card
        assert "comment" in card

    # Verify our custom keywords are present
    keys = {c["key"] for c in cards}
    assert "OBJECT" in keys
    assert "EXPTIME" in keys
    assert "FILTER" in keys

    # Check specific values
    obj_card = next(c for c in cards if c["key"] == "OBJECT")
    assert obj_card["value"] == "TestTarget"

    exp_card = next(c for c in cards if c["key"] == "EXPTIME")
    assert exp_card["value"] == "300.0"

    filter_card = next(c for c in cards if c["key"] == "FILTER")
    assert filter_card["value"] == "Ha"


@pytest.mark.anyio
async def test_header_color_fits(client, tmp_fits_color):
    """Header endpoint should work for color FITS files too."""
    resp = await client.get(
        "/api/images/header",
        params={"path": str(tmp_fits_color)},
    )
    assert resp.status_code == 200
    cards = resp.json()
    keys = {c["key"] for c in cards}
    assert "OBJECT" in keys
    obj_card = next(c for c in cards if c["key"] == "OBJECT")
    assert obj_card["value"] == "ColorTarget"


# ---------------------------------------------------------------------------
# GET /api/images/extensions
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_extensions_returns_info(client, tmp_fits_mono):
    """Extensions endpoint should list HDUs with supports_stretch flag."""
    resp = await client.get(
        "/api/images/extensions",
        params={"path": str(tmp_fits_mono)},
    )
    assert resp.status_code == 200
    exts = resp.json()
    assert isinstance(exts, list)
    assert len(exts) >= 1

    # FITS files should support stretch
    for ext in exts:
        assert "supports_stretch" in ext
        assert ext["supports_stretch"] is True


@pytest.mark.anyio
async def test_extensions_color_fits(client, tmp_fits_color):
    """Extensions endpoint should work for color FITS."""
    resp = await client.get(
        "/api/images/extensions",
        params={"path": str(tmp_fits_color)},
    )
    assert resp.status_code == 200
    exts = resp.json()
    assert len(exts) >= 1
    assert exts[0]["supports_stretch"] is True


# ---------------------------------------------------------------------------
# GET /api/images/image (render)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_render_returns_png(client, tmp_fits_mono):
    """Render endpoint should return a PNG image."""
    resp = await client.get(
        "/api/images/image",
        params={"path": str(tmp_fits_mono)},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"

    # PNG magic bytes
    assert resp.content[:4] == b"\x89PNG"
    assert len(resp.content) > 100  # sanity check: not empty


@pytest.mark.anyio
async def test_render_color_fits(client, tmp_fits_color):
    """Render should work for color FITS files."""
    resp = await client.get(
        "/api/images/image",
        params={"path": str(tmp_fits_color)},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content[:4] == b"\x89PNG"


@pytest.mark.anyio
async def test_render_with_auto_stretch(client, tmp_fits_mono):
    """Render with stretch=auto should return a valid PNG."""
    resp = await client.get(
        "/api/images/image",
        params={"path": str(tmp_fits_mono), "stretch": "auto"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content[:4] == b"\x89PNG"


# ---------------------------------------------------------------------------
# GET /api/images/stats
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_stats_mono(client, tmp_fits_mono):
    """Stats endpoint should return per-channel statistics for mono FITS."""
    resp = await client.get(
        "/api/images/stats",
        params={"path": str(tmp_fits_mono)},
    )
    assert resp.status_code == 200
    data = resp.json()

    # Should have channel stats
    assert "channels" in data
    assert isinstance(data["channels"], list)
    assert len(data["channels"]) >= 1

    # Each channel should have standard statistics
    ch = data["channels"][0]
    assert "median" in ch
    assert "mad" in ch
    assert "avg_dev" in ch

    # STF auto-stretch parameters should be present
    assert "linked_stf" in data


@pytest.mark.anyio
async def test_stats_color(client, tmp_fits_color):
    """Stats endpoint should return per-channel stats for color FITS (3 channels)."""
    resp = await client.get(
        "/api/images/stats",
        params={"path": str(tmp_fits_color)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "channels" in data
    # Color image should have 3 channels (R, G, B)
    assert len(data["channels"]) == 3


# ---------------------------------------------------------------------------
# 404 for missing file
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_header_404_missing_file(client):
    """Header endpoint should return 404 for a nonexistent file."""
    resp = await client.get(
        "/api/images/header",
        params={"path": "/nonexistent/path/missing.fits"},
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_extensions_404_missing_file(client):
    """Extensions endpoint should return 404 for a nonexistent file."""
    resp = await client.get(
        "/api/images/extensions",
        params={"path": "/nonexistent/path/missing.fits"},
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_render_404_missing_file(client):
    """Render endpoint should return 404 for a nonexistent file."""
    resp = await client.get(
        "/api/images/image",
        params={"path": "/nonexistent/path/missing.fits"},
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_stats_404_missing_file(client):
    """Stats endpoint should return 404 for a nonexistent file."""
    resp = await client.get(
        "/api/images/stats",
        params={"path": "/nonexistent/path/missing.fits"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_relative_path_rejected(client):
    """Relative paths should be rejected with 400."""
    resp = await client.get(
        "/api/images/header",
        params={"path": "relative/path/image.fits"},
    )
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_unsupported_extension(client, tmp_path):
    """Unsupported file extensions should be rejected."""
    bad_file = tmp_path / "data.csv"
    bad_file.write_text("not an image")
    resp = await client.get(
        "/api/images/header",
        params={"path": str(bad_file)},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/images/histogram
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_histogram_mono(client, tmp_fits_mono):
    """Histogram endpoint should return channel data for mono FITS."""
    resp = await client.get(
        "/api/images/histogram",
        params={"path": str(tmp_fits_mono)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "color" in data
    assert data["color"] is False
    assert "channels" in data
    assert len(data["channels"]) == 1
    assert data["channels"][0]["name"] == "L"
    assert len(data["channels"][0]["bins"]) == 256
    assert "bin_edges" in data
    assert data["luminosity"] is None


@pytest.mark.anyio
async def test_histogram_color(client, tmp_fits_color):
    """Histogram endpoint should return R/G/B channels plus luminosity for color FITS."""
    resp = await client.get(
        "/api/images/histogram",
        params={"path": str(tmp_fits_color)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["color"] is True
    assert len(data["channels"]) == 3
    channel_names = [c["name"] for c in data["channels"]]
    assert channel_names == ["R", "G", "B"]
    assert data["luminosity"] is not None
    assert len(data["luminosity"]) == 256


@pytest.mark.anyio
async def test_histogram_custom_bins(client, tmp_fits_mono):
    """Histogram endpoint should honor custom bin count."""
    resp = await client.get(
        "/api/images/histogram",
        params={"path": str(tmp_fits_mono), "bins": 64},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["channels"][0]["bins"]) == 64


@pytest.mark.anyio
async def test_histogram_404(client):
    """Histogram endpoint should return 404 for missing file."""
    resp = await client.get(
        "/api/images/histogram",
        params={"path": "/nonexistent/file.fits"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/images/pixel
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_pixel_mono(client, tmp_fits_mono):
    """Pixel endpoint should return mono pixel value."""
    resp = await client.get(
        "/api/images/pixel",
        params={"path": str(tmp_fits_mono), "x": 0, "y": 0},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["x"] == 0
    assert data["y"] == 0
    assert data["color"] is False
    assert "K" in data


@pytest.mark.anyio
async def test_pixel_color(client, tmp_fits_color):
    """Pixel endpoint should return R/G/B/K for color image."""
    resp = await client.get(
        "/api/images/pixel",
        params={"path": str(tmp_fits_color), "x": 10, "y": 10},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["color"] is True
    assert "R" in data
    assert "G" in data
    assert "B" in data
    assert "K" in data


@pytest.mark.anyio
async def test_pixel_out_of_bounds(client, tmp_fits_mono):
    """Pixel endpoint should reject out-of-bounds coordinates."""
    resp = await client.get(
        "/api/images/pixel",
        params={"path": str(tmp_fits_mono), "x": 9999, "y": 9999},
    )
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_pixel_404(client):
    """Pixel endpoint should return 404 for missing file."""
    resp = await client.get(
        "/api/images/pixel",
        params={"path": "/nonexistent/file.fits", "x": 0, "y": 0},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/images/header (header editing)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_header_edit_update(client, tmp_fits_mono):
    """Update an existing keyword value."""
    resp = await client.patch(
        "/api/images/header",
        json={
            "path": str(tmp_fits_mono),
            "hdu": 0,
            "operations": [{"op": "update", "key": "OBJECT", "value": "NewTarget"}],
        },
    )
    assert resp.status_code == 200
    cards = resp.json()
    obj_card = next(c for c in cards if c["key"] == "OBJECT")
    assert obj_card["value"] == "NewTarget"


@pytest.mark.anyio
async def test_header_edit_add(client, tmp_fits_mono):
    """Add a new keyword."""
    resp = await client.patch(
        "/api/images/header",
        json={
            "path": str(tmp_fits_mono),
            "hdu": 0,
            "operations": [
                {"op": "add", "key": "NEWKEY", "value": "hello", "comment": "a new key"}
            ],
        },
    )
    assert resp.status_code == 200
    cards = resp.json()
    keys = {c["key"] for c in cards}
    assert "NEWKEY" in keys


@pytest.mark.anyio
async def test_header_edit_delete(client, tmp_fits_mono):
    """Delete an existing keyword."""
    resp = await client.patch(
        "/api/images/header",
        json={
            "path": str(tmp_fits_mono),
            "hdu": 0,
            "operations": [{"op": "delete", "key": "FILTER"}],
        },
    )
    assert resp.status_code == 200
    cards = resp.json()
    keys = {c["key"] for c in cards}
    assert "FILTER" not in keys


@pytest.mark.anyio
async def test_header_edit_structural_keyword_rejected(client, tmp_fits_mono):
    """Structural keywords like BITPIX cannot be modified."""
    resp = await client.patch(
        "/api/images/header",
        json={
            "path": str(tmp_fits_mono),
            "hdu": 0,
            "operations": [{"op": "update", "key": "BITPIX", "value": "32"}],
        },
    )
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_header_edit_naxis_rejected(client, tmp_fits_mono):
    """NAXIS keywords are structural and cannot be modified."""
    resp = await client.patch(
        "/api/images/header",
        json={
            "path": str(tmp_fits_mono),
            "hdu": 0,
            "operations": [{"op": "delete", "key": "NAXIS1"}],
        },
    )
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_header_edit_virtual_path_rejected(client, tmp_fits_mono):
    """Header editing should be rejected for virtual paths (::)."""
    resp = await client.patch(
        "/api/images/header",
        json={
            "path": f"{tmp_fits_mono}::0",
            "hdu": 0,
            "operations": [{"op": "update", "key": "OBJECT", "value": "X"}],
        },
    )
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_header_edit_non_fits_rejected(client, tmp_path):
    """Header editing should be rejected for non-FITS files."""
    png_file = tmp_path / "test.png"
    png_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    resp = await client.patch(
        "/api/images/header",
        json={
            "path": str(png_file),
            "hdu": 0,
            "operations": [{"op": "add", "key": "FOO", "value": "bar"}],
        },
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_header_edit_missing_file(client):
    """Header editing should return 404 for missing file."""
    resp = await client.patch(
        "/api/images/header",
        json={
            "path": "/nonexistent/file.fits",
            "hdu": 0,
            "operations": [{"op": "add", "key": "FOO", "value": "bar"}],
        },
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_header_edit_relative_path_rejected(client):
    """Header editing should reject relative paths."""
    resp = await client.patch(
        "/api/images/header",
        json={
            "path": "relative/path.fits",
            "hdu": 0,
            "operations": [{"op": "add", "key": "FOO", "value": "bar"}],
        },
    )
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_header_edit_update_nonexistent_key(client, tmp_fits_mono):
    """Updating a key that does not exist should fail."""
    resp = await client.patch(
        "/api/images/header",
        json={
            "path": str(tmp_fits_mono),
            "hdu": 0,
            "operations": [{"op": "update", "key": "NOSUCHKEY", "value": "x"}],
        },
    )
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_header_edit_add_duplicate_key(client, tmp_fits_mono):
    """Adding a key that already exists should fail."""
    resp = await client.patch(
        "/api/images/header",
        json={
            "path": str(tmp_fits_mono),
            "hdu": 0,
            "operations": [{"op": "add", "key": "OBJECT", "value": "dup"}],
        },
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/images/stats-histogram
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_stats_histogram_combined(client, tmp_fits_mono):
    """Stats-histogram endpoint should return both stats and histogram."""
    resp = await client.get(
        "/api/images/stats-histogram",
        params={"path": str(tmp_fits_mono)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "stats" in data
    assert "histogram" in data
    assert "channels" in data["stats"]
    assert "channels" in data["histogram"]


@pytest.mark.anyio
async def test_stats_histogram_standard_image_rejected(client, tmp_path):
    """Stats-histogram should return 404 for standard image formats (PNG)."""
    from PIL import Image

    png_file = tmp_path / "test.png"
    img = Image.new("RGB", (10, 10), color=(128, 128, 128))
    img.save(png_file)
    resp = await client.get(
        "/api/images/stats-histogram",
        params={"path": str(png_file)},
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_stats_standard_image_rejected(client, tmp_path):
    """Stats endpoint should return 404 for standard image formats."""
    from PIL import Image

    png_file = tmp_path / "test.png"
    img = Image.new("RGB", (10, 10), color=(128, 128, 128))
    img.save(png_file)
    resp = await client.get(
        "/api/images/stats",
        params={"path": str(png_file)},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/images/image — stretch parameter variations
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_render_with_stf_params(client, tmp_fits_mono):
    """Render with explicit STF parameters should return valid PNG."""
    resp = await client.get(
        "/api/images/image",
        params={
            "path": str(tmp_fits_mono),
            "stretch": "stf",
            "shadow": 0.01,
            "midtone": 0.3,
            "highlight": 0.99,
        },
    )
    assert resp.status_code == 200
    assert resp.content[:4] == b"\x89PNG"


@pytest.mark.anyio
async def test_render_with_per_channel_overrides(client, tmp_fits_color):
    """Render with per-channel stretch overrides should work for color images."""
    resp = await client.get(
        "/api/images/image",
        params={
            "path": str(tmp_fits_color),
            "stretch": "stf",
            "r_shadow": 0.01,
            "r_midtone": 0.4,
            "g_shadow": 0.02,
            "b_midtone": 0.3,
        },
    )
    assert resp.status_code == 200
    assert resp.content[:4] == b"\x89PNG"


@pytest.mark.anyio
async def test_render_standard_image(client, tmp_path):
    """Rendering a standard PNG should return the PNG directly."""
    from PIL import Image

    png_file = tmp_path / "test.png"
    img = Image.new("RGB", (10, 10), color=(128, 128, 128))
    img.save(png_file)
    resp = await client.get(
        "/api/images/image",
        params={"path": str(png_file)},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"


# ---------------------------------------------------------------------------
# GET /api/images/metadata
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_metadata_endpoint(client, tmp_fits_mono):
    """Metadata endpoint should return canonical metadata and unrecognized keywords."""
    resp = await client.get(
        "/api/images/metadata",
        params={"path": str(tmp_fits_mono)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "canonical" in data
    assert "unrecognized_keywords" in data
    # Our FITS has OBJECT, EXPTIME, FILTER which should be in canonical
    canonical = data["canonical"]
    # Verify some expected canonical fields are present
    assert "exposure_time" in canonical
    assert canonical["exposure_time"] == "300.0"
    assert canonical["filter_name"] == "Ha"


@pytest.mark.anyio
async def test_metadata_404(client):
    """Metadata endpoint should return 404 for missing file."""
    resp = await client.get(
        "/api/images/metadata",
        params={"path": "/nonexistent/file.fits"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Recent files
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_recent_add_and_list(client, tmp_fits_mono):
    """Adding a recent file and listing should return it."""
    await client.post(
        "/api/images/recent",
        params={"path": str(tmp_fits_mono)},
    )
    resp = await client.get("/api/images/recent")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    paths = [r["path"] for r in data]
    assert str(tmp_fits_mono) in paths


@pytest.mark.anyio
async def test_recent_stale_file_pruned(client, tmp_path):
    """Stale files (deleted since recorded) should be pruned from recent list."""
    temp_file = tmp_path / "temp.fits"
    # Create and add
    import numpy as np
    from astropy.io import fits as astropy_fits

    hdu = astropy_fits.PrimaryHDU(np.zeros((10, 10), dtype=np.uint16))
    hdu.writeto(temp_file, overwrite=True)
    await client.post("/api/images/recent", params={"path": str(temp_file)})
    # Delete the file
    temp_file.unlink()
    # List should not include it
    resp = await client.get("/api/images/recent")
    paths = [r["path"] for r in resp.json()]
    assert str(temp_file) not in paths


# ---------------------------------------------------------------------------
# Cache management — _cached_compute TTL expiry
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_cache_eviction_on_ttl(client, tmp_fits_mono):
    """Verify that cached entries expire after TTL (via direct unit test of cache)."""
    from unittest.mock import patch

    from nightcrate.api import images

    # Clear any existing cache state
    images._cache.clear()
    images._stats_cache.clear()

    # Load once to populate cache
    resp = await client.get(
        "/api/images/stats",
        params={"path": str(tmp_fits_mono)},
    )
    assert resp.status_code == 200

    # Verify cache has at least one entry
    assert len(images._stats_cache) > 0

    # Expire the cache by patching the TTL to 0
    with patch.object(images, "_CACHE_TTL_SECONDS", 0):
        # The next call should recompute (expired entry gets deleted)
        resp2 = await client.get(
            "/api/images/stats",
            params={"path": str(tmp_fits_mono)},
        )
        assert resp2.status_code == 200


# ---------------------------------------------------------------------------
# Virtual path resolution edge cases
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_archive_virtual_path_nonexistent_archive(client, tmp_path):
    """Archive virtual path with nonexistent archive should return 404."""
    resp = await client.get(
        "/api/images/header",
        params={"path": f"{tmp_path}/nonexistent.zip::image.fits"},
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_invalid_virtual_path(client, tmp_fits_mono):
    """Virtual path :: with a non-archive, non-project left side should fail."""
    resp = await client.get(
        "/api/images/header",
        params={"path": f"{tmp_fits_mono}::something"},
    )
    assert resp.status_code == 400
