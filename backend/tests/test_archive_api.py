"""Tests for archive browsing and image viewing via archive virtual paths."""

import asyncio
import zipfile
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from httpx import ASGITransport, AsyncClient

from nightcrate.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def tmp_zip_with_fits(tmp_path: Path) -> Path:
    """Create a zip archive containing a FITS file and a nested directory structure."""
    # Create a mono FITS in memory
    rng = np.random.default_rng(42)
    data = rng.integers(1400, 1600, size=(100, 120), dtype=np.uint16)
    data[48:53, 58:63] = 40000

    hdu = fits.PrimaryHDU(data)
    hdu.header["OBJECT"] = "ArchiveTarget"
    hdu.header["EXPTIME"] = 300.0
    hdu.header["FILTER"] = "Ha"

    fits_path = tmp_path / "temp_for_zip.fits"
    hdu.writeto(fits_path, overwrite=True)
    fits_bytes = fits_path.read_bytes()

    # Build zip with structure:
    # lights/Ha/frame001.fits
    # lights/OIII/frame002.fits
    # darks/dark001.fits
    zip_path = tmp_path / "session.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("lights/Ha/frame001.fits", fits_bytes)
        zf.writestr("lights/OIII/frame002.fits", fits_bytes)
        zf.writestr("darks/dark001.fits", fits_bytes)

    return zip_path


@pytest.fixture
def tmp_dir_with_archive(tmp_path: Path, tmp_zip_with_fits: Path) -> Path:
    """Return the directory containing the zip archive and some other files."""
    # Add a regular image file
    rng = np.random.default_rng(42)
    data = rng.integers(1400, 1600, size=(50, 60), dtype=np.uint16)
    hdu = fits.PrimaryHDU(data)
    fits_path = tmp_path / "standalone.fits"
    hdu.writeto(fits_path, overwrite=True)

    # Add a non-archive, non-image file
    (tmp_path / "readme.txt").write_text("hello")

    return tmp_path


# ── Task 8: browse-archive endpoint ─────────────────────────────────────────


class TestBrowseIncludesArchives:
    async def test_browse_lists_archives(self, client: AsyncClient, tmp_dir_with_archive: Path):
        """browse response includes archives array when dir contains archive files."""
        resp = await client.get("/api/files/browse", params={"path": str(tmp_dir_with_archive)})
        assert resp.status_code == 200
        data = resp.json()
        assert "archives" in data
        archive_names = [a["name"] for a in data["archives"]]
        assert "session.zip" in archive_names

    async def test_browse_archives_excludes_hidden(
        self, client: AsyncClient, tmp_dir_with_archive: Path
    ):
        """Hidden archive files should not appear."""
        # Create a hidden archive
        hidden_zip = tmp_dir_with_archive / ".hidden.zip"
        with zipfile.ZipFile(hidden_zip, "w") as zf:
            zf.writestr("dummy.txt", "hi")

        resp = await client.get("/api/files/browse", params={"path": str(tmp_dir_with_archive)})
        data = resp.json()
        archive_names = [a["name"] for a in data["archives"]]
        assert ".hidden.zip" not in archive_names


class TestBrowseArchiveEndpoint:
    async def test_root_listing(self, client: AsyncClient, tmp_zip_with_fits: Path):
        """browse-archive returns root listing with dirs/files."""
        resp = await client.get(
            "/api/files/browse-archive", params={"path": str(tmp_zip_with_fits)}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["subdir"] == ""
        assert data["parent"] is None
        dir_names = [d["name"] for d in data["dirs"]]
        assert "lights" in dir_names
        assert "darks" in dir_names
        assert len(data["files"]) == 0  # No files at root level

    async def test_subdir_listing(self, client: AsyncClient, tmp_zip_with_fits: Path):
        """browse-archive with subdir returns correct listing with correct parent."""
        resp = await client.get(
            "/api/files/browse-archive",
            params={"path": str(tmp_zip_with_fits), "subdir": "lights"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["subdir"] == "lights"
        assert data["parent"] == ""
        dir_names = [d["name"] for d in data["dirs"]]
        assert "Ha" in dir_names
        assert "OIII" in dir_names

    async def test_nested_parent(self, client: AsyncClient, tmp_zip_with_fits: Path):
        """browse-archive computes nested parent correctly (subdir='a/b' -> parent='a')."""
        resp = await client.get(
            "/api/files/browse-archive",
            params={"path": str(tmp_zip_with_fits), "subdir": "lights/Ha"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["parent"] == "lights"
        file_names = [f["name"] for f in data["files"]]
        assert "frame001.fits" in file_names

    async def test_darks_subdir(self, client: AsyncClient, tmp_zip_with_fits: Path):
        """browse-archive lists files in darks subdir."""
        resp = await client.get(
            "/api/files/browse-archive",
            params={"path": str(tmp_zip_with_fits), "subdir": "darks"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["parent"] == ""
        file_names = [f["name"] for f in data["files"]]
        assert "dark001.fits" in file_names

    async def test_nonexistent_archive_404(self, client: AsyncClient, tmp_path: Path):
        """browse-archive with nonexistent archive returns 404."""
        fake = tmp_path / "nonexistent.zip"
        resp = await client.get("/api/files/browse-archive", params={"path": str(fake)})
        assert resp.status_code == 404

    async def test_not_an_archive_400(self, client: AsyncClient, tmp_path: Path):
        """browse-archive with a non-archive file returns 400."""
        txt_file = tmp_path / "readme.txt"
        txt_file.write_text("hello")
        resp = await client.get("/api/files/browse-archive", params={"path": str(txt_file)})
        assert resp.status_code == 400


# ── Task 9: Archive virtual paths in images.py ──────────────────────────────


class TestArchiveImageEndpoints:
    async def test_extensions(self, client: AsyncClient, tmp_zip_with_fits: Path):
        """Archive virtual path returns valid extension info."""
        virtual = f"{tmp_zip_with_fits}::lights/Ha/frame001.fits"
        resp = await client.get("/api/images/extensions", params={"path": virtual})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["has_image"] is True

    async def test_stats(self, client: AsyncClient, tmp_zip_with_fits: Path):
        """Archive virtual path returns channel stats."""
        virtual = f"{tmp_zip_with_fits}::lights/Ha/frame001.fits"
        resp = await client.get("/api/images/stats", params={"path": virtual, "hdu": 0})
        assert resp.status_code == 200
        data = resp.json()
        assert data["color"] is False
        assert len(data["channels"]) == 1

    async def test_image_png(self, client: AsyncClient, tmp_zip_with_fits: Path):
        """Archive virtual path returns PNG bytes."""
        virtual = f"{tmp_zip_with_fits}::lights/Ha/frame001.fits"
        resp = await client.get("/api/images/image", params={"path": virtual, "hdu": 0})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert len(resp.content) > 0

    async def test_header(self, client: AsyncClient, tmp_zip_with_fits: Path):
        """Archive virtual path returns header cards."""
        virtual = f"{tmp_zip_with_fits}::lights/Ha/frame001.fits"
        resp = await client.get("/api/images/header", params={"path": virtual, "hdu": 0})
        assert resp.status_code == 200
        cards = resp.json()
        keys = {c["key"] for c in cards}
        assert "OBJECT" in keys

    async def test_invalid_entry_404(self, client: AsyncClient, tmp_zip_with_fits: Path):
        """Invalid entry path in archive returns 404."""
        virtual = f"{tmp_zip_with_fits}::nonexistent/file.fits"
        resp = await client.get("/api/images/extensions", params={"path": virtual})
        assert resp.status_code == 404

    async def test_concurrent_image_and_stats(self, client: AsyncClient, tmp_zip_with_fits: Path):
        """Concurrent image + stats-histogram requests for same archive entry don't crash.

        Regression test: before caching was added for archive (BytesIO) paths,
        concurrent requests bypassed the per-key lock and ran GPU operations
        from multiple threads simultaneously, crashing the backend.
        """
        virtual = f"{tmp_zip_with_fits}::lights/Ha/frame001.fits"
        image_req = client.get(
            "/api/images/image",
            params={"path": virtual, "hdu": 0, "stretch": "auto"},
        )
        stats_req = client.get(
            "/api/images/stats-histogram",
            params={"path": virtual, "hdu": 0},
        )
        image_resp, stats_resp = await asyncio.gather(image_req, stats_req)
        assert image_resp.status_code == 200
        assert stats_resp.status_code == 200
        assert image_resp.headers["content-type"] == "image/png"
        stats_data = stats_resp.json()
        assert "stats" in stats_data
        assert "histogram" in stats_data
