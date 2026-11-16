"""Create the FITS and XISF files used by the frozen-backend smoke test."""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import numpy as np
import zstandard
from astropy.io import fits


def _make_xisf(
    width: int,
    height: int,
    channels: int,
    sample_format: str,
    pixel_data: bytes,
    compression: str = "",
    fits_keywords: list[tuple[str, str, str]] | None = None,
) -> bytes:
    """Build a minimal attached-data XISF file.

    This is a standalone copy of the clean-room test writer. Packaging must not
    import the test suite, which is absent from frozen builds and installers.
    """
    offset = 4096
    keyword_xml = "".join(
        f'<FITSKeyword name="{name}" value="{value}" comment="{comment}" />\n'
        for name, value, comment in (fits_keywords or [])
    )
    compression_attr = f' compression="{compression}"' if compression else ""
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<xisf version="1.0" xmlns="http://www.pixinsight.com/xisf">
<Image geometry="{width}:{height}:{channels}" sampleFormat="{sample_format}"
 colorSpace="{"RGB" if channels == 3 else "Gray"}"
 location="attachment:{offset}:{len(pixel_data)}"{compression_attr}>
{keyword_xml}</Image>
</xisf>"""
    xml_bytes = xml.encode()
    total_header = 16 + len(xml_bytes)
    if total_header > offset:
        offset = total_header
        old_location = f"attachment:4096:{len(pixel_data)}"
        xml_bytes = xml.replace(
            old_location, f"attachment:{offset}:{len(pixel_data)}"
        ).encode()
    padding = b"\0" * (offset - 16 - len(xml_bytes))
    return (
        b"XISF0100"
        + struct.pack("<I", len(xml_bytes))
        + struct.pack("<I", 0)
        + xml_bytes
        + padding
        + pixel_data
    )


def make_data(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(1)
    height, width = 600, 800
    yy, xx = np.mgrid[0:height, 0:width]
    stars = [
        (
            rng.uniform(20, width - 20),
            rng.uniform(20, height - 20),
            rng.uniform(500, 20_000),
        )
        for _ in range(80)
    ]

    def frame() -> np.ndarray:
        image = rng.normal(1000, 20, (height, width))
        for x, y, amplitude in stars:
            image += amplitude * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * 1.8**2))
        return np.clip(image, 0, 65535).astype(np.uint16)

    for index in range(16):
        header = fits.Header()
        header["IMAGETYP"] = "Light Frame"
        header["EXPTIME"] = 300.0
        header["FILTER"] = "Ha"
        header["DATE-OBS"] = f"2026-10-01T03:{index:02d}:00"
        header["OBJECT"] = "NGC 7000"
        header["GAIN"] = 100
        header["XBINNING"] = 1
        header["CCD-TEMP"] = -10.0
        fits.PrimaryHDU(frame(), header=header).writeto(
            output / f"Light_NGC7000_Ha_{index:03d}.fits", overwrite=True
        )

    keywords = [
        ("IMAGETYP", "'Light Frame'", ""),
        ("EXPTIME", "300.0", ""),
        ("FILTER", "'OIII'", ""),
        ("DATE-OBS", "'2026-10-02T03:00:00'", ""),
        ("OBJECT", "'NGC 7000'", ""),
    ]
    for index in range(4):
        raw = frame().tobytes()
        compressed = zstandard.ZstdCompressor().compress(raw)
        xisf = _make_xisf(
            width,
            height,
            1,
            "UInt16",
            compressed,
            compression=f"zstd:{len(raw)}",
            fits_keywords=keywords,
        )
        (output / f"Light_NGC7000_OIII_{index:03d}.xisf").write_bytes(xisf)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: make_test_data.py <output-dir>", file=sys.stderr)
        return 2
    make_data(Path(sys.argv[1]).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
