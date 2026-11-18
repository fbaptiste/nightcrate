"""Frame-type guesses from file and in-scope folder names."""

import io
import zipfile
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from httpx import ASGITransport, AsyncClient

from nightcrate.api.ingest import _classification_folder_names
from nightcrate.main import app
from nightcrate.services.ingest_classify import CATEGORY_SUB, classify_frame
from tests.catalog_helpers import _frames, _ingest_folder, _make_project


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


@pytest.mark.parametrize(
    ("folder", "expected"),
    [
        ("Darks 300s -10C", "dark"),
        ("darks_2026-03-14", "dark"),
        ("Bias", "bias"),
        ("FlatDarks", "dark_flat"),
    ],
)
def test_folder_keyword_only(folder: str, expected: str):
    route, frame_type, basis = classify_frame({}, {}, folder_names=[folder])
    assert (route, frame_type, basis) == (CATEGORY_SUB, expected, "folder_name")


def test_folder_with_other_words_ignored():
    assert classify_frame({}, {}, folder_names=["Dark Sky Site 2025"]) == (
        CATEGORY_SUB,
        "unknown",
        None,
    )


def test_ancestors_above_bound_folder_ignored(tmp_path: Path):
    bound = tmp_path / "Dark Sky Site 2025" / "Project"
    path = bound / "IMG_1.fit"
    assert _classification_folder_names(str(path), str(bound)) == ["Project"]


def test_nearest_folder_wins():
    assert classify_frame({}, {}, folder_names=["Flats", "Darks"])[1:] == (
        "flat",
        "folder_name",
    )


def test_filename_beats_folders():
    assert classify_frame({}, {}, filename="Light_M31.fit", folder_names=["Darks"])[1:] == (
        "light",
        "file_name",
    )


def test_header_beats_names():
    assert classify_frame(
        {}, {"IMAGETYP": "BIAS"}, filename="Light_M31.fit", folder_names=["Darks"]
    )[1:] == ("bias", "header")


def test_archive_inner_folders_count(tmp_path: Path):
    archive = tmp_path / "capture.zip"
    path = f"{archive}::Darks/Flats/IMG_1.fit"
    names = _classification_folder_names(path, str(archive))
    assert names == ["Flats", "Darks", "capture"]
    assert classify_frame({}, {}, folder_names=names)[1:] == ("flat", "folder_name")


def test_archive_inner_bound_excludes_archive_and_out_of_scope_parents(tmp_path: Path):
    archive = tmp_path / "capture_Darks.zip"
    bound = f"{archive}::Session"
    assert _classification_folder_names(f"{archive}::Session/IMG_1.fit", bound) == ["Session"]
    assert _classification_folder_names(f"{archive}::Other/Darks/IMG_2.fit", bound) == []


async def test_archive_name_does_not_classify_file_when_inner_folder_is_bound(
    client: AsyncClient, tmp_path: Path
):
    archive = tmp_path / "capture_Darks.zip"
    payload = io.BytesIO()
    fits.PrimaryHDU(np.full((8, 8), 1000, dtype=np.uint16)).writeto(payload)
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("Session/IMG_1.fit", payload.getvalue())

    project_id = await _make_project(client, "Bound archive folder")
    await _ingest_folder(client, project_id, f"{archive}::Session")
    rows = await _frames(client, project_id)
    assert len(rows) == 1
    assert rows[0]["frame_type"] == "unknown"
    assert rows[0]["frame_type_basis"] is None


async def test_basis_stored(client: AsyncClient, tmp_path: Path):
    project_id = await _make_project(client, "Folder basis")
    folder = tmp_path / "Darks 300s -10C"
    folder.mkdir()
    hdu = fits.PrimaryHDU(np.full((8, 8), 1000, dtype=np.uint16))
    hdu.header["EXPTIME"] = 300
    hdu.writeto(folder / "IMG_1.fit")

    await _ingest_folder(client, project_id, folder)
    rows = await _frames(client, project_id, frame_type="dark")
    assert len(rows) == 1
    assert rows[0]["frame_type_basis"] == "folder_name"
