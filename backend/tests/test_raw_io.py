from __future__ import annotations

import io
import os
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import tifffile

from nightcrate.services import raw_io
from nightcrate.services.raw_support import RawUnavailable
from tests.fixtures.raw_fixtures import write_cfa_dng


def _generated(path: Path, **kwargs) -> Path:
    samples = np.arange(32 * 34, dtype=np.uint16).reshape(32, 34) + 512
    return write_cfa_dng(path, samples, **kwargs)


def test_pattern_and_levels(tmp_path):
    path = _generated(tmp_path / "levels.dng", pattern="GRBG", black=512, white=16383)
    result = raw_io.read_raw_samples(path)
    assert result.samples.shape == (32, 34)
    assert result.rgb is None
    assert result.pattern.pattern.rows == ("GR", "BG")
    assert result.black_levels == (512.0, 512.0, 512.0, 512.0)
    assert result.white_level == 16383
    assert result.visible == (0, 0, 34, 32)


@pytest.mark.parametrize("pattern", ["RGGB", "GRBG", "GBRG", "BGGR"])
def test_layout_pattern_matches_full_sample_read(tmp_path, pattern):
    path = _generated(tmp_path / f"layout-{pattern}.dng", pattern=pattern)
    layout = raw_io.read_raw_layout(path)
    samples = raw_io.read_raw_samples(path)
    assert layout.pattern == samples.pattern
    assert layout.black_levels == samples.black_levels
    assert layout.white_level == samples.white_level
    assert layout.visible == samples.visible


def test_layout_shifts_pattern_for_odd_visible_origin(monkeypatch):
    import rawpy

    class FakeRaw:
        sizes = SimpleNamespace(left_margin=1, top_margin=1, width=4, height=4)
        raw_pattern = np.array([[0, 1], [1, 2]], dtype=np.uint8)
        color_desc = b"RGBG"
        black_level_per_channel = (64, 65, 66, 65)
        white_level = 4095
        raw_image_visible = np.zeros((4, 4), dtype=np.uint16)
        raw_colors_visible = np.tile(np.array([[2, 1], [1, 0]], dtype=np.uint8), (2, 2))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(rawpy, "imread", lambda _source: FakeRaw())
    layout = raw_io.read_raw_layout(io.BytesIO(b"fixture"))
    samples = raw_io.read_raw_samples(io.BytesIO(b"fixture"))
    assert layout.visible[:2] == (1, 1)
    assert layout.pattern == samples.pattern
    assert layout.pattern.pattern.rows == ("BG", "GR")


def test_time_with_offset(tmp_path):
    path = _generated(
        tmp_path / "offset.dng",
        exif={
            "Exif.Photo.DateTimeOriginal": "2026:03:15 21:30:00",
            "Exif.Photo.SubSecTimeOriginal": "125",
            "Exif.Photo.OffsetTimeOriginal": "-07:00",
            "Exif.Photo.ExposureTime": "1/4",
            "Exif.Photo.ISOSpeedRatings": "800",
            "Exif.Image.Make": "NightCrate",
            "Exif.Image.Model": "Fixture",
        },
    )
    result = raw_io.read_raw_metadata(path)
    assert result.captured_local == datetime(2026, 3, 15, 21, 30, 0, 125000)
    assert result.utc_offset == timedelta(hours=-7)
    assert result.time_source == "exif_offset"
    assert result.exposure_s == pytest.approx(0.25)
    assert result.iso == 800
    assert result.make == "NightCrate"
    assert result.model == "Fixture"


def test_exposure_prefers_exact_exif_rational():
    class Datum:
        def toString(self):
            return "1/125"

        def toFloat(self):
            return 0.00800000037997961

    assert raw_io._exif_exposure({"Exif.Photo.ExposureTime": Datum()}) == 0.008


def test_libraw_exposure_fallback_is_six_significant_digits(monkeypatch):
    import rawpy

    class FakeRaw:
        other = SimpleNamespace(shutter_speed=0.00800000037997961)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(rawpy, "imread", lambda _source: FakeRaw())
    assert raw_io._libraw_exposure(Path("unused.raw")) == 0.008


def test_time_without_offset(tmp_path):
    path = _generated(
        tmp_path / "no-offset.dng",
        exif={"Exif.Photo.DateTimeOriginal": "2026:03:15 21:30:00"},
    )
    result = raw_io.read_raw_metadata(path)
    assert result.captured_local == datetime(2026, 3, 15, 21, 30)
    assert result.utc_offset is None
    assert result.time_source == "none"


def test_raw_in_zip_reads(tmp_path):
    path = _generated(
        tmp_path / "inside.dng",
        exif={"Exif.Photo.DateTimeOriginal": "2026:03:15 21:30:00"},
    )
    archive = tmp_path / "raw.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.write(path, "capture/inside.dng")
    with zipfile.ZipFile(archive) as source:
        payload = source.read("capture/inside.dng")
    samples = raw_io.read_raw_samples(io.BytesIO(payload))
    metadata = raw_io.read_raw_metadata(io.BytesIO(payload))
    assert samples.samples.shape == (32, 34)
    assert metadata.captured_local == datetime(2026, 3, 15, 21, 30)

    from nightcrate.services.pixel_loader import load_image

    loaded = load_image(f"{archive}::capture/inside.dng")
    assert loaded.kind == "mosaic"
    assert loaded.recorded.shape == (32, 34)


def test_linear_dng_is_rgb(tmp_path):
    path = tmp_path / "linear.dng"
    pixels = np.empty((32, 34, 3), dtype=np.uint16)
    pixels[..., 0] = 1000
    pixels[..., 1] = 2000
    pixels[..., 2] = 3000
    extratags = [
        (50706, "B", 4, (1, 4, 0, 0), False),
        (50707, "B", 4, (1, 3, 0, 0), False),
        (50708, "s", 0, "NightCrate Linear DNG", False),
        (50717, "I", 1, 16383, False),
    ]
    tifffile.imwrite(
        path,
        pixels,
        photometric=34892,
        planarconfig="contig",
        metadata=None,
        extratags=extratags,
    )
    result = raw_io.read_raw_samples(path)
    assert result.samples is None
    assert result.pattern is None
    assert result.rgb.shape == (3, 32, 34)
    np.testing.assert_array_equal(result.rgb[:, 0, 0], (1000, 2000, 3000))


def test_unsupported_plain_message():
    with pytest.raises(raw_io.RawUnsupported) as caught:
        raw_io.read_raw_samples(io.BytesIO(b"not a raw file"))
    assert str(caught.value)
    assert "Traceback" not in str(caught.value)


def test_unavailable_raises(monkeypatch):
    monkeypatch.setattr(
        raw_io,
        "require",
        lambda: (_ for _ in ()).throw(RawUnavailable("Raw files can't be read on this computer")),
    )
    with pytest.raises(RawUnavailable, match="Raw files can't be read"):
        raw_io.read_raw_samples(io.BytesIO(b"unused"))


def test_header_groups_order(tmp_path):
    path = _generated(
        tmp_path / "header.dng",
        exif={
            "Exif.Photo.DateTimeOriginal": "2026:03:15 21:30:00",
            "Exif.Photo.OffsetTimeOriginal": "-05:30",
            "Exif.Photo.ExposureTime": "1/2",
            "Exif.Photo.ISOSpeedRatings": "400",
        },
    )
    cards = raw_io.read_header(path)
    order = list(dict.fromkeys(card["group"] for card in cards))
    assert order[:4] == ["Capture", "Camera and lens", "Colour data", "EXIF"]
    assert all(set(card) == {"group", "key", "value", "comment"} for card in cards)
    by_key = {card["key"]: card for card in cards}
    assert by_key["UTC offset"]["value"] == "-05:30"
    assert by_key["Pattern source"]["value"] == "the raw file"


class _StandInDatum:
    def __init__(
        self,
        key: str,
        type_name: str,
        count: int,
        plain: str,
        *,
        printed: str | None = None,
        print_raises: bool = False,
    ):
        self._key = key
        self._type_name = type_name
        self._count = count
        self._plain = plain
        self._printed = plain if printed is None else printed
        self._print_raises = print_raises

    def key(self):
        return self._key

    def typeName(self):
        return self._type_name

    def count(self):
        return self._count

    def print(self, _exif_data):
        if self._print_raises:
            raise RuntimeError("uninterpretable")
        return self._printed

    def toString(self):
        return self._plain

    def tagLabel(self):
        return ""

    def tagDesc(self):
        return ""


@pytest.mark.parametrize("type_name", ["Undefined", "Byte", "SByte"])
def test_cards_hide_large_uninterpreted_byte_types(type_name):
    datum = _StandInDatum("Exif.Photo.Binary", type_name, 17, "0 1 2")
    assert raw_io._cards([datum]) == []


@pytest.mark.parametrize(
    "type_name",
    ["Short", "SShort", "Long", "SLong", "Rational", "SRational", "Float", "Double"],
)
def test_cards_hide_large_uninterpreted_numeric_types(type_name):
    datum = _StandInDatum("Exif.Photo.Array", type_name, 65, "1 2 3")
    assert raw_io._cards([datum]) == []


@pytest.mark.parametrize(
    ("datum", "expected_value"),
    [
        (_StandInDatum("Exif.Photo.Bytes16", "Undefined", 16, "0 1"), "0 1"),
        (_StandInDatum("Exif.Photo.Shorts64", "Short", 64, "1 2"), "1 2"),
        (
            _StandInDatum(
                "Exif.Canon.AFPointsInFocus",
                "Short",
                66,
                "0 0 0",
                printed="(none)",
            ),
            "(none)",
        ),
        (_StandInDatum("Exif.Photo.LongText", "Ascii", 10_000, "long text"), "long text"),
        (
            _StandInDatum(
                "Exif.Photo.InterpretedBytes",
                "Byte",
                17,
                "0 1 2",
                printed="2.30",
            ),
            "2.30",
        ),
    ],
)
def test_cards_keep_small_or_interpreted_values(datum, expected_value):
    assert raw_io._cards([datum])[0]["value"] == expected_value


def test_cards_hide_large_value_when_print_raises():
    datum = _StandInDatum(
        "Exif.Photo.MakerNote",
        "Undefined",
        17,
        "0 1 2",
        print_raises=True,
    )
    assert raw_io._cards([datum]) == []


@pytest.mark.skipif(
    not os.getenv("NIGHTCRATE_RAW_SAMPLES"), reason="real raw samples not configured"
)
def test_real_samples_metadata():
    root = Path(os.environ["NIGHTCRATE_RAW_SAMPLES"])
    paths = sorted(path for path in root.iterdir() if path.suffix.lower() in raw_io.RAW_EXTENSIONS)
    assert len(paths) == 18
    for path in paths:
        metadata = raw_io.read_raw_metadata(path)
        layout = raw_io.read_raw_layout(path)
        samples = raw_io.read_raw_samples(path)
        assert layout.pattern == samples.pattern, path.name
        assert layout.visible == samples.visible, path.name
        assert layout.black_levels == samples.black_levels, path.name
        assert layout.white_level == samples.white_level, path.name
        assert metadata.captured_local is not None, path.name
        assert metadata.exposure_s is not None, path.name
        assert metadata.iso is not None, path.name
        assert metadata.make, path.name
        assert metadata.model, path.name
        keys = {card["key"] for card in metadata.cards}
        if path.suffix.lower() == ".cr2":
            assert "Exif.Photo.MakerNote" not in keys, path.name
            assert "Exif.Canon.ImageType" in keys, path.name
        if "Exif.Photo.OffsetTimeOriginal" in keys:
            assert metadata.time_source == "exif_offset", path.name
        elif keys & {
            "Exif.CanonTi.TimeZone",
            "Exif.NikonWt.Timezone",
            "Exif.NikonWt.TimeZone",
        }:
            assert metadata.time_source == "maker_note", path.name
        print(
            path.name,
            metadata.time_source,
            metadata.utc_offset,
            metadata.camera_temp_c,
            metadata.sensor_temp_c,
        )
