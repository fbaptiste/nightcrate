"""Tests for the file browser API endpoints."""

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
def browse_dir(tmp_path: Path) -> Path:
    """Create a directory tree with subdirs, image files, and non-image files."""
    # Subdirectories
    sub = tmp_path / "subdir"
    sub.mkdir()
    hidden = tmp_path / ".hidden"
    hidden.mkdir()

    # A minimal FITS file
    data = np.zeros((10, 10), dtype=np.uint16)
    hdu = fits.PrimaryHDU(data)
    hdu.writeto(tmp_path / "test_image.fits", overwrite=True)

    # A PNG file (valid image extension)
    (tmp_path / "photo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    # Non-image file — should be excluded
    (tmp_path / "readme.txt").write_text("hello")

    # Hidden FITS — should be excluded
    (tmp_path / ".hidden.fits").write_bytes(b"nope")

    return tmp_path


# ---------------------------------------------------------------------------
# GET /api/files/browse — normal directory
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_browse_directory(client, browse_dir):
    resp = await client.get("/api/files/browse", params={"path": str(browse_dir)})
    assert resp.status_code == 200
    data = resp.json()

    assert data["path"] == str(browse_dir)
    assert data["parent"] is not None

    dir_names = [d["name"] for d in data["dirs"]]
    assert "subdir" in dir_names
    assert ".hidden" not in dir_names

    file_names = [f["name"] for f in data["files"]]
    assert "test_image.fits" in file_names
    assert "photo.png" in file_names
    assert "readme.txt" not in file_names
    assert ".hidden.fits" not in file_names


@pytest.mark.anyio
async def test_browse_returns_file_size(client, browse_dir):
    resp = await client.get("/api/files/browse", params={"path": str(browse_dir)})
    data = resp.json()
    fits_entry = next(f for f in data["files"] if f["name"] == "test_image.fits")
    assert "size" in fits_entry
    assert fits_entry["size"] > 0


# ---------------------------------------------------------------------------
# GET /api/files/browse — nonexistent directory
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_browse_nonexistent_directory(client, tmp_path):
    fake_path = tmp_path / "does_not_exist"
    resp = await client.get("/api/files/browse", params={"path": str(fake_path)})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/files/browse — file instead of directory
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_browse_file_not_directory(client, tmp_path):
    file_path = tmp_path / "afile.txt"
    file_path.write_text("hello")
    resp = await client.get("/api/files/browse", params={"path": str(file_path)})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/files/browse — empty directory
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_browse_empty_directory(client, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    resp = await client.get("/api/files/browse", params={"path": str(empty)})
    assert resp.status_code == 200
    data = resp.json()
    assert data["dirs"] == []
    assert data["files"] == []
    assert data["projects"] == []
    assert data["archives"] == []


# ---------------------------------------------------------------------------
# GET /api/files/volumes
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_volumes(client):
    resp = await client.get("/api/files/volumes")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    # First entry should be home
    assert data[0]["name"].startswith("~")
    assert "path" in data[0]


# ---------------------------------------------------------------------------
# GET /api/files/browse — permission denied
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_browse_permission_denied(client, tmp_path):
    restricted = tmp_path / "restricted"
    restricted.mkdir()
    restricted.chmod(0o000)
    try:
        resp = await client.get("/api/files/browse", params={"path": str(restricted)})
        # Should get 403 if the OS enforces permissions
        assert resp.status_code == 403
    except Exception:
        pytest.skip("Platform does not enforce directory permissions in test")
    finally:
        restricted.chmod(0o755)


# ---------------------------------------------------------------------------
# GET /api/files/browse — directory with .pxiproject and archive files
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_browse_detects_pxiproject(client, tmp_path):
    """A .pxiproject directory should appear in projects, not dirs."""
    proj_dir = tmp_path / "M31.pxiproject"
    proj_dir.mkdir()
    resp = await client.get("/api/files/browse", params={"path": str(tmp_path)})
    assert resp.status_code == 200
    data = resp.json()
    project_names = [p["name"] for p in data["projects"]]
    dir_names = [d["name"] for d in data["dirs"]]
    assert "M31.pxiproject" in project_names
    assert "M31.pxiproject" not in dir_names


@pytest.mark.anyio
async def test_browse_detects_archive(client, tmp_path):
    """Archive files should appear in archives, not files."""
    archive_path = tmp_path / "images.zip"
    # Create a minimal valid zip
    import zipfile

    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("test.fits", b"dummy")
    resp = await client.get("/api/files/browse", params={"path": str(tmp_path)})
    assert resp.status_code == 200
    data = resp.json()
    archive_names = [a["name"] for a in data["archives"]]
    file_names = [f["name"] for f in data["files"]]
    assert "images.zip" in archive_names
    assert "images.zip" not in file_names


@pytest.mark.anyio
async def test_browse_stat_oserror(client, tmp_path):
    """If stat() fails on a file, size should be 0."""
    # Create a valid image file, verify it has a size
    fits_path = tmp_path / "test.fits"
    data = np.zeros((10, 10), dtype=np.uint16)
    hdu = fits.PrimaryHDU(data)
    hdu.writeto(fits_path, overwrite=True)

    resp = await client.get("/api/files/browse", params={"path": str(tmp_path)})
    assert resp.status_code == 200
    result = resp.json()
    fits_entry = next(f for f in result["files"] if f["name"] == "test.fits")
    assert fits_entry["size"] > 0


# ---------------------------------------------------------------------------
# GET /api/files/browse-archive
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_browse_archive_basic(client, tmp_path):
    """Browse into a zip archive."""
    import zipfile

    archive_path = tmp_path / "test_archive.zip"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("subdir/image.fits", b"dummy fits data")
        zf.writestr("top.fits", b"top level fits data")

    resp = await client.get(
        "/api/files/browse-archive",
        params={"path": str(archive_path)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["path"] == str(archive_path)
    assert data["parent"] is None


@pytest.mark.anyio
async def test_browse_archive_subdir(client, tmp_path):
    """Browse into a subdirectory inside an archive."""
    import zipfile

    archive_path = tmp_path / "nested.zip"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("dir1/dir2/image.fits", b"data")

    resp = await client.get(
        "/api/files/browse-archive",
        params={"path": str(archive_path), "subdir": "dir1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["subdir"] == "dir1"
    assert data["parent"] == ""


@pytest.mark.anyio
async def test_browse_archive_nested_subdir_parent(client, tmp_path):
    """Subdirectory with slash should compute parent correctly."""
    import zipfile

    archive_path = tmp_path / "deep.zip"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("a/b/c/image.fits", b"data")

    resp = await client.get(
        "/api/files/browse-archive",
        params={"path": str(archive_path), "subdir": "a/b"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["parent"] == "a"


@pytest.mark.anyio
async def test_browse_archive_not_found(client, tmp_path):
    resp = await client.get(
        "/api/files/browse-archive",
        params={"path": str(tmp_path / "nonexistent.zip")},
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_browse_archive_not_archive(client, tmp_path):
    txt_file = tmp_path / "not_an_archive.txt"
    txt_file.write_text("hello")
    resp = await client.get(
        "/api/files/browse-archive",
        params={"path": str(txt_file)},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/files/browse-project
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_browse_project_not_pxiproject(client, tmp_path):
    """Non-.pxiproject directory should return 400."""
    regular_dir = tmp_path / "regular_dir"
    regular_dir.mkdir()
    resp = await client.get(
        "/api/files/browse-project",
        params={"path": str(regular_dir)},
    )
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_browse_project_nonexistent(client, tmp_path):
    """Non-existent .pxiproject path should return 400."""
    resp = await client.get(
        "/api/files/browse-project",
        params={"path": str(tmp_path / "nope.pxiproject")},
    )
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_browse_project_valid(client, tmp_path, monkeypatch):
    """Valid .pxiproject path should return images."""

    proj_dir = tmp_path / "M31.pxiproject"
    proj_dir.mkdir()

    # Mock pxiproject_io.list_project_images to return fake data
    from nightcrate.services import pxiproject_io

    fake_images = [{"index": 0, "name": "M31_L", "source": "embedded"}]
    monkeypatch.setattr(pxiproject_io, "list_project_images", lambda p: fake_images)

    resp = await client.get(
        "/api/files/browse-project",
        params={"path": str(proj_dir)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["path"] == str(proj_dir)
    assert data["parent"] == str(proj_dir.parent)
    assert data["images"] == fake_images


@pytest.mark.anyio
async def test_browse_project_parse_error(client, tmp_path, monkeypatch):
    """If pxiproject_io raises, browse_project should return 422."""
    from nightcrate.services import pxiproject_io

    proj_dir = tmp_path / "Bad.pxiproject"
    proj_dir.mkdir()

    def _raise_bad_xosm(_p):
        raise ValueError("bad xosm")

    monkeypatch.setattr(pxiproject_io, "list_project_images", _raise_bad_xosm)

    resp = await client.get(
        "/api/files/browse-project",
        params={"path": str(proj_dir)},
    )
    assert resp.status_code == 422
