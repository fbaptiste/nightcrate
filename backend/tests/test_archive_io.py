"""Tests for archive I/O — detection, listing, extraction across zip/tar/7z."""

from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import numpy as np
import py7zr
import pytest
from astropy.io import fits

from nightcrate.services.archive_io import extract_entry, is_archive, list_contents

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_fits_bytes() -> bytes:
    """Create minimal FITS file bytes (20x30 uint16, OBJECT=TestStar, FILTER=L)."""
    data = np.ones((20, 30), dtype=np.uint16) * 1500
    hdu = fits.PrimaryHDU(data)
    hdu.header["OBJECT"] = "TestStar"
    hdu.header["FILTER"] = "L"
    buf = io.BytesIO()
    hdu.writeto(buf)
    return buf.getvalue()


@pytest.fixture
def tmp_zip_archive(tmp_path: Path, tmp_fits_bytes: bytes) -> Path:
    """Create a zip with lights/target/, lights/flats/, darks/, and notes.txt."""
    archive_path = tmp_path / "test.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("lights/target/image_001.fits", tmp_fits_bytes)
        zf.writestr("lights/target/image_002.fits", tmp_fits_bytes)
        zf.writestr("lights/flats/flat_001.fits", tmp_fits_bytes)
        zf.writestr("darks/dark_001.fits", tmp_fits_bytes)
        zf.writestr("notes.txt", "session notes")
    return archive_path


@pytest.fixture
def tmp_tar_gz_archive(tmp_path: Path, tmp_fits_bytes: bytes) -> Path:
    """Create a tar.gz with lights/target/, lights/flats/, and darks/."""
    archive_path = tmp_path / "test.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tf:
        for name in [
            "lights/target/image_001.fits",
            "lights/flats/flat_001.fits",
            "darks/dark_001.fits",
        ]:
            info = tarfile.TarInfo(name=name)
            info.size = len(tmp_fits_bytes)
            tf.addfile(info, io.BytesIO(tmp_fits_bytes))
    return archive_path


@pytest.fixture
def tmp_7z_archive(tmp_path: Path, tmp_fits_bytes: bytes) -> Path:
    """Create a 7z with lights/target/, lights/flats/, and darks/."""
    archive_path = tmp_path / "test.7z"
    with py7zr.SevenZipFile(archive_path, "w") as szf:
        for name in [
            "lights/target/image_001.fits",
            "lights/flats/flat_001.fits",
            "darks/dark_001.fits",
        ]:
            szf.writestr(tmp_fits_bytes, name)
    return archive_path


# ---------------------------------------------------------------------------
# is_archive detection
# ---------------------------------------------------------------------------


class TestIsArchive:
    def test_zip(self, tmp_path: Path):
        assert is_archive(tmp_path / "file.zip") is True

    def test_tar_gz(self, tmp_path: Path):
        assert is_archive(tmp_path / "file.tar.gz") is True

    def test_tgz(self, tmp_path: Path):
        assert is_archive(tmp_path / "file.tgz") is True

    def test_tar_bz2(self, tmp_path: Path):
        assert is_archive(tmp_path / "file.tar.bz2") is True

    def test_tar_zst(self, tmp_path: Path):
        assert is_archive(tmp_path / "file.tar.zst") is True

    def test_7z(self, tmp_path: Path):
        assert is_archive(tmp_path / "file.7z") is True

    def test_plain_tar(self, tmp_path: Path):
        assert is_archive(tmp_path / "file.tar") is True

    def test_non_archive_fits(self, tmp_path: Path):
        assert is_archive(tmp_path / "image.fits") is False

    def test_non_archive_txt(self, tmp_path: Path):
        assert is_archive(tmp_path / "notes.txt") is False

    def test_non_archive_no_extension(self, tmp_path: Path):
        assert is_archive(tmp_path / "README") is False

    def test_case_insensitive_zip(self, tmp_path: Path):
        assert is_archive(tmp_path / "file.ZIP") is True

    def test_case_insensitive_tar_gz(self, tmp_path: Path):
        assert is_archive(tmp_path / "file.TAR.GZ") is True

    def test_case_insensitive_7z(self, tmp_path: Path):
        assert is_archive(tmp_path / "file.7Z") is True


# ---------------------------------------------------------------------------
# list_contents — ZIP
# ---------------------------------------------------------------------------


class TestListContentsZip:
    def test_root_level(self, tmp_zip_archive: Path):
        entries = list_contents(tmp_zip_archive)
        names = {e["name"] for e in entries}
        assert names == {"lights", "darks", "notes.txt"}

    def test_root_dirs_marked(self, tmp_zip_archive: Path):
        entries = list_contents(tmp_zip_archive)
        lights = next(e for e in entries if e["name"] == "lights")
        assert lights["is_dir"] is True

    def test_root_file_not_dir(self, tmp_zip_archive: Path):
        entries = list_contents(tmp_zip_archive)
        notes = next(e for e in entries if e["name"] == "notes.txt")
        assert notes["is_dir"] is False

    def test_file_has_size(self, tmp_zip_archive: Path):
        entries = list_contents(tmp_zip_archive)
        notes = next(e for e in entries if e["name"] == "notes.txt")
        assert notes["size"] > 0

    def test_dir_has_no_size(self, tmp_zip_archive: Path):
        entries = list_contents(tmp_zip_archive)
        lights = next(e for e in entries if e["name"] == "lights")
        assert lights["size"] is None

    def test_subdir_lights(self, tmp_zip_archive: Path):
        entries = list_contents(tmp_zip_archive, subdir="lights")
        names = {e["name"] for e in entries}
        assert names == {"target", "flats"}

    def test_nested_subdir(self, tmp_zip_archive: Path):
        entries = list_contents(tmp_zip_archive, subdir="lights/target")
        names = {e["name"] for e in entries}
        assert names == {"image_001.fits", "image_002.fits"}
        for e in entries:
            assert e["is_dir"] is False
            assert e["size"] > 0

    def test_darks_subdir(self, tmp_zip_archive: Path):
        entries = list_contents(tmp_zip_archive, subdir="darks")
        names = {e["name"] for e in entries}
        assert names == {"dark_001.fits"}

    def test_empty_subdir_returns_empty(self, tmp_zip_archive: Path):
        entries = list_contents(tmp_zip_archive, subdir="nonexistent")
        assert entries == []


# ---------------------------------------------------------------------------
# list_contents — tar.gz
# ---------------------------------------------------------------------------


class TestListContentsTarGz:
    def test_root_level(self, tmp_tar_gz_archive: Path):
        entries = list_contents(tmp_tar_gz_archive)
        names = {e["name"] for e in entries}
        assert names == {"lights", "darks"}

    def test_subdir(self, tmp_tar_gz_archive: Path):
        entries = list_contents(tmp_tar_gz_archive, subdir="lights")
        names = {e["name"] for e in entries}
        assert names == {"target", "flats"}


# ---------------------------------------------------------------------------
# list_contents — 7z
# ---------------------------------------------------------------------------


class TestListContents7z:
    def test_root_level(self, tmp_7z_archive: Path):
        entries = list_contents(tmp_7z_archive)
        names = {e["name"] for e in entries}
        assert names == {"lights", "darks"}

    def test_subdir(self, tmp_7z_archive: Path):
        entries = list_contents(tmp_7z_archive, subdir="lights")
        names = {e["name"] for e in entries}
        assert names == {"target", "flats"}


# ---------------------------------------------------------------------------
# extract_entry
# ---------------------------------------------------------------------------


class TestExtractEntry:
    def test_zip_extraction(self, tmp_zip_archive: Path):
        result = extract_entry(tmp_zip_archive, "notes.txt")
        assert isinstance(result, io.BytesIO)
        assert result.read() == b"session notes"

    def test_zip_fits_extraction(self, tmp_zip_archive: Path):
        result = extract_entry(tmp_zip_archive, "lights/target/image_001.fits")
        data = result.read()
        assert len(data) > 0

    def test_tar_gz_extraction(self, tmp_tar_gz_archive: Path):
        result = extract_entry(tmp_tar_gz_archive, "darks/dark_001.fits")
        assert isinstance(result, io.BytesIO)
        assert len(result.read()) > 0

    def test_7z_extraction(self, tmp_7z_archive: Path):
        result = extract_entry(tmp_7z_archive, "darks/dark_001.fits")
        assert isinstance(result, io.BytesIO)
        assert len(result.read()) > 0

    def test_not_found_raises(self, tmp_zip_archive: Path):
        with pytest.raises(FileNotFoundError):
            extract_entry(tmp_zip_archive, "nonexistent.fits")

    def test_extracted_fits_is_valid(self, tmp_zip_archive: Path):
        """Extracted FITS bytes should be loadable by astropy."""
        result = extract_entry(tmp_zip_archive, "lights/target/image_001.fits")
        with fits.open(result) as hdul:
            assert hdul[0].data is not None
            assert hdul[0].data.shape == (20, 30)
            assert hdul[0].header["OBJECT"] == "TestStar"
            assert hdul[0].header["FILTER"] == "L"


# ---------------------------------------------------------------------------
# Path traversal security
# ---------------------------------------------------------------------------


class TestPathTraversal:
    def test_dotdot_in_entry_rejected(self, tmp_zip_archive: Path):
        with pytest.raises(ValueError, match="[Pp]ath traversal"):
            extract_entry(tmp_zip_archive, "../etc/passwd")

    def test_absolute_path_rejected(self, tmp_zip_archive: Path):
        with pytest.raises(ValueError, match="[Pp]ath traversal"):
            extract_entry(tmp_zip_archive, "/etc/passwd")

    def test_dotdot_in_subdir_rejected(self, tmp_zip_archive: Path):
        with pytest.raises(ValueError, match="[Pp]ath traversal"):
            list_contents(tmp_zip_archive, subdir="../etc")

    def test_absolute_subdir_rejected(self, tmp_zip_archive: Path):
        with pytest.raises(ValueError, match="[Pp]ath traversal"):
            list_contents(tmp_zip_archive, subdir="/etc")
