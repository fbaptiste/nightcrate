from __future__ import annotations

import importlib
import logging

import numpy as np
import pytest

from nightcrate.services import raw_support
from tests.fixtures.raw_fixtures import write_cfa_dng


def test_problem_none_when_libraries_load():
    raw_support.problem.cache_clear()
    assert raw_support.problem() is None


def test_problem_reports_missing_library(monkeypatch):
    real_import = importlib.import_module

    def missing(name: str):
        if name == "rawpy":
            raise ImportError("missing")
        return real_import(name)

    monkeypatch.setattr(raw_support.importlib, "import_module", missing)
    raw_support.problem.cache_clear()
    assert raw_support.problem() == "Raw files can't be read on this computer"
    with pytest.raises(raw_support.RawUnavailable, match="Raw files can't be read"):
        raw_support.require()
    raw_support.problem.cache_clear()


def test_rawpy_demosaic_packs_disabled():
    import rawpy

    assert rawpy.flags["DEMOSAIC_PACK_GPL2"] is False
    assert rawpy.flags["DEMOSAIC_PACK_GPL3"] is False
    print(f"LibRaw version: {rawpy.libraw_version}")


def test_generated_dng_round_trips(tmp_path):
    import exiv2
    import rawpy

    samples = np.arange(32 * 34, dtype=np.uint16).reshape(32, 34) + 512
    path = write_cfa_dng(
        tmp_path / "generated.dng",
        samples,
        pattern="GBRG",
        exif={
            "Exif.Photo.DateTimeOriginal": "2026:03:15 21:30:00",
            "Exif.Photo.ISOSpeedRatings": "800",
        },
    )

    with rawpy.imread(str(path)) as raw:
        np.testing.assert_array_equal(raw.raw_image_visible, samples)
        colours = bytes(raw.color_desc).decode().rstrip("\x00")
        actual = tuple(
            "".join(colours[int(index)] for index in row) for row in raw.raw_colors_visible[:2, :2]
        )
        assert actual == ("GB", "RG")

    image = exiv2.ImageFactory.open(str(path))
    image.readMetadata()
    metadata = image.exifData()
    assert metadata["Exif.Photo.DateTimeOriginal"].toString() == "2026:03:15 21:30:00"
    assert metadata["Exif.Photo.ISOSpeedRatings"].toString() == "800"


def test_self_check_exercises_in_memory_raw_and_exif():
    raw_support.problem.cache_clear()
    assert raw_support.self_check() is None


def test_self_check_returns_plain_reason(monkeypatch):
    real_import = importlib.import_module

    def missing_import(name: str):
        if name == "rawpy":
            raise ImportError("missing rawpy")
        return real_import(name)

    monkeypatch.setattr(raw_support.importlib, "import_module", missing_import)
    assert raw_support.self_check() == raw_support.UNAVAILABLE_MESSAGE


def test_self_check_logs_exception_type_with_traceback(monkeypatch, caplog):
    real_import = importlib.import_module

    def broken_import(name: str):
        if name == "tifffile":
            raise LookupError("broken native probe")
        return real_import(name)

    monkeypatch.setattr(raw_support.importlib, "import_module", broken_import)
    with caplog.at_level(logging.WARNING, logger=raw_support.__name__):
        assert raw_support.self_check() == raw_support.UNAVAILABLE_MESSAGE
    assert "[raw] installed raw self-check failed" in caplog.text
    assert "LookupError: broken native probe" in caplog.text
