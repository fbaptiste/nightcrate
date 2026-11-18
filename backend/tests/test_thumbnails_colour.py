"""Colour mosaics in thumbnails, previews and versioned project renditions."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from httpx import ASGITransport, AsyncClient
from PIL import Image

from nightcrate.core.compute import set_gpu_enabled
from nightcrate.main import app
from nightcrate.services.catalog_thumbnail import render_thumbnail_bytes
from nightcrate.services.image_preview import _reset_for_tests, get_preview
from nightcrate.services.project_images import (
    RENDER_VERSION,
    _delete_exact_obsolete,
    drain_background_refreshes,
    generate_rendered_images,
    rendition_path,
)
from tests.catalog_helpers import _make_project


@pytest.fixture(autouse=True)
def _numpy_backend():
    set_gpu_enabled(False)
    _reset_for_tests()
    yield
    _reset_for_tests()


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


def _mosaic(path: Path, *, pedestals=(512, 520, 508)) -> Path:
    height = width = 96
    yy, xx = np.mgrid[:height, :width]
    common = ((xx + yy) % 17).astype(np.uint16)
    data = common.copy()
    colours = np.array([[0, 1], [1, 2]])
    for y in range(height):
        for x in range(width):
            colour = colours[y % 2, x % 2]
            data[y, x] += pedestals[colour]
            if 32 <= y < 64 and 32 <= x < 64:
                data[y, x] += (9000, 4500, 1500)[colour]
    hdu = fits.PrimaryHDU(data)
    hdu.header["BAYERPAT"] = "RGGB"
    hdu.header["ROWORDER"] = "TOP-DOWN"
    hdu.writeto(path)
    return path


def _jpeg(payload: bytes) -> np.ndarray:
    with Image.open(io.BytesIO(payload)) as image:
        return np.asarray(image.convert("RGB"))


def test_obsolete_project_cache_delete_failure_is_logged_and_ignored(
    tmp_path: Path, monkeypatch, caplog
):
    old = tmp_path / "thumb_sm.jpg"
    old.write_bytes(b"old")
    real_unlink = Path.unlink

    def unlink(path, *args, **kwargs):
        if path == old:
            raise PermissionError("cache is read-only")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink)
    _delete_exact_obsolete([old], "rendition")
    assert old.is_file()
    assert "couldn't remove obsolete rendition file" in caplog.text


def test_catalog_thumbnail_mosaic_is_colour(tmp_path: Path):
    path = _mosaic(tmp_path / "mosaic.fits")
    image = _jpeg(render_thumbnail_bytes(str(path), 96))
    assert image.shape[2] == 3
    assert np.max(np.ptp(image, axis=2)) > 20
    patch = image[2:12, 2:12].astype(np.float32) / 255
    assert float(np.var(np.mean(patch, axis=(1, 2)))) < 1e-3


def test_thumbnail_dark_area_not_tinted(tmp_path: Path):
    path = _mosaic(tmp_path / "pedestals.fits", pedestals=(512, 520, 508))
    image = _jpeg(render_thumbnail_bytes(str(path), 96))
    dark = image[2:12, 2:12].mean(axis=(0, 1))
    assert int(dark.max() - dark.min()) <= 3


def test_preview_mosaic_is_colour(tmp_path: Path):
    path = _mosaic(tmp_path / "preview.fits")
    result = get_preview(str(path), max_px=256)
    assert result.content is not None
    image = _jpeg(result.content)
    assert np.max(np.ptp(image, axis=2)) > 20


def test_project_image_mosaic_rendered_in_colour(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def gpu_forbidden():
        raise AssertionError("project rendering must stay on NumPy in worker threads")

    monkeypatch.setattr("nightcrate.core.compute.get_array_module", gpu_forbidden)
    monkeypatch.setattr("nightcrate.services.imaging.get_array_module", gpu_forbidden)
    path = _mosaic(tmp_path / "project.fits")
    output = tmp_path / "renditions"
    generate_rendered_images(str(path), output)
    rendered = np.asarray(Image.open(rendition_path(output, "thumb_sm")).convert("RGB"))
    assert np.max(np.ptp(rendered, axis=2)) > 20
    assert rendition_path(output, "full").name == f"full_v{RENDER_VERSION}.jpg"


async def test_existing_grey_rendition_regenerates(
    client: AsyncClient, tmp_path: Path, monkeypatch
):
    projects_root = tmp_path / "projects"
    monkeypatch.setattr("nightcrate.api.projects.get_projects_root", lambda: projects_root)
    project_id = await _make_project(client, "Versioned rendition")
    path = _mosaic(tmp_path / "old-grey.fits")
    response = await client.post(
        f"/api/projects/{project_id}/images", json={"file_paths": [str(path)]}
    )
    assert response.status_code == 201, response.text
    image_id = response.json()[0]["id"]
    output = projects_root / str(project_id) / f"img_{image_id}"
    current = rendition_path(output, "thumb_sm")
    current.unlink()
    old_unversioned = output / "thumb_sm.jpg"
    old_versioned = output / "thumb_sm_v1.jpg"
    unrelated = output / "thumb_sm_notes.jpg"
    Image.new("L", (32, 32), 128).save(old_unversioned)
    Image.new("L", (32, 32), 128).save(old_versioned)
    unrelated.write_bytes(b"keep")

    response = await client.get(f"/api/projects/{project_id}/images/{image_id}/rendered/thumb_sm")
    assert response.status_code == 200
    assert response.content == old_versioned.read_bytes()
    await drain_background_refreshes()
    assert current.is_file()
    assert not old_unversioned.exists()
    assert not old_versioned.exists()
    assert unrelated.read_bytes() == b"keep"
    response = await client.get(f"/api/projects/{project_id}/images/{image_id}/rendered/thumb_sm")
    image = _jpeg(response.content)
    assert np.max(np.ptp(image, axis=2)) > 20
