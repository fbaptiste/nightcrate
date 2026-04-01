"""PixInsight project (.pxiproject) I/O — reads XOSM manifests and embedded image data.

A .pxiproject is a directory bundle containing project.xosm (XML manifest)
and project.data/ (binary blobs for pixel data in PixInsight's swap format).
"""

import struct
import zlib
from functools import lru_cache
from pathlib import Path

import defusedxml.ElementTree as ET
import lz4.block
import numpy as np
import zstandard

from nightcrate.services.imaging import normalize_to_01, reshape_color

XOSM_NS = "http://www.pixinsight.com/xosm"
RAWIMAGE_MAGIC = b"egamiwar"
RAWIMAGE_HEADER_SIZE = 128


class PxiProjectError(Exception):
    """Raised when a .pxiproject cannot be parsed."""


def _tag(local: str) -> str:
    return f"{{{XOSM_NS}}}{local}"


def _parse_xosm(project_dir: Path) -> tuple:
    """Parse project.xosm and return (root, compression_method)."""
    xosm_path = project_dir / "project.xosm"
    if not xosm_path.exists():
        raise PxiProjectError(f"project.xosm not found in {project_dir}")

    root = ET.parse(str(xosm_path)).getroot()

    project_el = root.find(_tag("Project"))
    compression = "none"
    if project_el is not None:
        features = project_el.find(_tag("features"))
        if features is not None:
            compression = features.get("compression", "none")

    return root, compression


def _get_image_window(root, index: int):
    """Get a specific ImageWindow element by index, with bounds checking."""
    windows = list(root.iter(_tag("ImageWindow")))
    if index < 0 or index >= len(windows):
        raise ValueError(f"Image index {index} out of range (project has {len(windows)} images)")
    return windows[index]


def _extract_keyword(iw, keyword_name: str) -> str | None:
    """Extract a FITS keyword value from an ImageWindow's fitsKeywords."""
    fk = iw.find(_tag("fitsKeywords"))
    if fk is None:
        return None
    for kw in fk.findall(_tag("keyword")):
        if kw.get("name") == keyword_name:
            val = kw.get("value", "").strip("'").strip()
            return val if val else None
    return None


def list_project_images(project_dir: Path) -> list[dict]:
    """List all images in a .pxiproject bundle.

    Returns (images_list, compression_method) where each image is a dict with:
    index, name, source, file_path, data_src, filter, object, exposure, date_obs, linear.
    """
    root, compression = _parse_xosm(project_dir)
    images = []

    for i, iw in enumerate(root.iter(_tag("ImageWindow"))):
        view = iw.get("currentView", f"Image_{i}")
        file_path = iw.get("filePath")
        is_referenced = bool(file_path)

        data_src = None
        is_linear = True
        mv = iw.find(_tag("MainView"))
        if mv is not None:
            img_el = mv.find(_tag("image"))
            if img_el is not None:
                src = img_el.get("src", "")
                data_src = src.replace("@project_data_dir/", "")

            # Detect linearity from STF params:
            # - STF enabled + small midtone (< 0.1) → linear
            # - STF enabled + no stf elements → linear (PixInsight auto-computes)
            # - STF enabled + midtone = 0.5 (identity) → non-linear
            # - STF disabled → non-linear
            stf_enabled = mv.get("stfEnabled", "0") == "1"
            stf_elements = mv.findall(_tag("stf"))
            if not stf_enabled:
                is_linear = False
            elif not stf_elements:
                is_linear = True
            else:
                try:
                    midtone = float(stf_elements[0].get("m", "0.5"))
                    is_linear = midtone < 0.1
                except ValueError:
                    is_linear = True

        filt = _extract_keyword(iw, "FILTER")
        obj = _extract_keyword(iw, "OBJECT")
        exptime = _extract_keyword(iw, "EXPTIME")
        date_obs = _extract_keyword(iw, "DATE-OBS")

        exposure = None
        if exptime:
            try:
                exposure = float(exptime)
            except ValueError:
                pass

        images.append(
            {
                "index": i,
                "name": view,
                "source": "referenced" if is_referenced else "embedded",
                "file_path": file_path if is_referenced else None,
                "data_src": data_src,
                "filter": filt,
                "object": obj,
                "exposure": exposure,
                "date_obs": date_obs,
                "linear": is_linear,
            }
        )

    return images


@lru_cache(maxsize=8)
def _cached_project_data(project_dir_str: str) -> tuple[list[dict], str]:
    """Cache parsed project data (images + compression) by project path.

    Avoids re-parsing XOSM when multiple endpoints hit the same project.
    """
    images = list_project_images(Path(project_dir_str))
    _, compression = _parse_xosm(Path(project_dir_str))
    return images, compression


def _get_project_data(project_dir: Path) -> tuple[list[dict], str]:
    """Get cached project images and compression method."""
    return _cached_project_data(str(project_dir))


def _parse_rawimage_header(header: bytes) -> tuple[int, int, int, int]:
    """Parse a rawimage blob header. Returns (width, height, total_channels, bps).

    The rawimage swap format header (128 bytes):
      offset  0: magic "egamiwar" (8 bytes)
      offset 15: bits_per_sample (uint8)
      offset 16: channels_in_blob (uint32 LE)
      offset 28: width (uint32 LE)
      offset 32: height (uint32 LE)
      offset 36: total_channels (uint32 LE) — e.g. 3 for RGB
    """
    if len(header) < RAWIMAGE_HEADER_SIZE:
        raise PxiProjectError("Blob too small for rawimage header")
    if header[:8] != RAWIMAGE_MAGIC:
        raise PxiProjectError(f"Bad rawimage magic: {header[:8]!r}")

    bps = header[15]
    width = struct.unpack_from("<I", header, 28)[0]
    height = struct.unpack_from("<I", header, 32)[0]
    total_channels = struct.unpack_from("<I", header, 36)[0]
    if total_channels == 0:
        total_channels = struct.unpack_from("<I", header, 16)[0]

    return width, height, total_channels, bps


def _decompress_channel_section(
    raw_data: bytes, offset: int, base_codec: str, dctx: zstandard.ZstdDecompressor | None
) -> tuple[bytes, int]:
    """Decompress one channel section (num_blocks + blocks). Returns (data, new_offset)."""
    num_blocks = struct.unpack_from("<I", raw_data, offset)[0]
    offset += 4
    result = bytearray()

    for _ in range(num_blocks):
        if offset + 16 > len(raw_data):
            raise PxiProjectError("Truncated block header")
        comp_size, uncomp_size = struct.unpack_from("<QQ", raw_data, offset)
        offset += 16

        # Skip 16-byte block prefix (checksum/metadata — not needed for decompression)
        offset += 16

        if offset + comp_size > len(raw_data):
            raise PxiProjectError("Truncated block data")
        chunk = raw_data[offset : offset + comp_size]
        offset += comp_size

        if comp_size == uncomp_size:
            result.extend(chunk)
        elif base_codec == "zlib":
            result.extend(zlib.decompress(chunk))
        elif base_codec in ("lz4", "lz4hc"):
            result.extend(lz4.block.decompress(chunk, uncompressed_size=uncomp_size))
        elif base_codec == "zstd":
            result.extend(dctx.decompress(chunk, max_output_size=uncomp_size))
        else:
            raise PxiProjectError(f"Unsupported compression: {base_codec}")

    return bytes(result), offset


def _decompress_blob(raw_data: bytes, compression: str, num_channels: int) -> bytes:
    """Decompress pixel data from a rawimage swap blob (after the 128-byte header).

    For multi-channel images, the blob contains one channel section per channel,
    each with its own num_blocks + block data. Channels are concatenated (planar).

    Note: byte shuffling (+sh) in the project compression setting applies to
    property/metadata blobs, NOT to rawimage pixel data.
    """
    if compression == "none":
        return raw_data

    base_codec = compression.replace("+sh", "").replace("+sc", "")
    dctx = zstandard.ZstdDecompressor() if base_codec == "zstd" else None

    result = bytearray()
    offset = 0

    for _ in range(num_channels):
        channel_data, offset = _decompress_channel_section(raw_data, offset, base_codec, dctx)
        result.extend(channel_data)

    return bytes(result)


BPS_TO_DTYPE = {32: np.float32, 64: np.float64, 16: np.uint16, 8: np.uint8}


def load_image_data(project_dir: Path, image_index: int) -> np.ndarray:
    """Load an image from a .pxiproject as a float array normalized to [0, 1].

    For referenced images, delegates to xisf_io.
    For embedded images, reads and decompresses the blob from project.data/.
    Returns shape (H, W) for mono or (3, H, W) for color.
    """
    images, compression = _get_project_data(project_dir)
    if image_index < 0 or image_index >= len(images):
        raise ValueError(
            f"Image index {image_index} out of range (project has {len(images)} images)"
        )

    entry = images[image_index]

    if entry["source"] == "referenced" and entry["file_path"]:
        from nightcrate.services import xisf_io

        ref_path = Path(entry["file_path"])
        if not ref_path.exists():
            raise FileNotFoundError(f"Referenced file not found: {entry['file_path']}")
        return xisf_io.load_image_data(ref_path)

    if not entry["data_src"]:
        raise PxiProjectError(f"No data source for embedded image '{entry['name']}'")

    blob_path = project_dir / "project.data" / entry["data_src"]
    if not blob_path.exists():
        raise FileNotFoundError(f"Blob not found: {blob_path}")

    with open(blob_path, "rb") as f:
        header = f.read(RAWIMAGE_HEADER_SIZE)
        pixel_data = f.read()

    width, height, channels, bps = _parse_rawimage_header(header)

    if compression != "none":
        pixel_data = _decompress_blob(pixel_data, compression, channels)

    dtype = BPS_TO_DTYPE.get(bps)
    if dtype is None:
        raise PxiProjectError(f"Unsupported bits per sample: {bps}")

    arr = np.frombuffer(pixel_data, dtype=dtype)

    if channels == 1:
        arr = arr.reshape(height, width)
    else:
        arr = arr.reshape(channels, height, width)

    return reshape_color(normalize_to_01(arr))


def read_header(project_dir: Path, image_index: int) -> list[dict]:
    """Read FITS keywords from a project image's XOSM metadata."""
    root, _ = _parse_xosm(project_dir)
    iw = _get_image_window(root, image_index)

    cards: list[dict] = []
    fk = iw.find(_tag("fitsKeywords"))
    if fk is not None:
        for kw in fk.findall(_tag("keyword")):
            cards.append(
                {
                    "key": kw.get("name", ""),
                    "value": kw.get("value", ""),
                    "comment": kw.get("comment", ""),
                }
            )

    return cards


def list_extensions(project_dir: Path, image_index: int) -> list[dict]:
    """Return a single-entry extension list for a project image."""
    images, _ = _get_project_data(project_dir)
    if image_index < 0 or image_index >= len(images):
        raise ValueError(f"Image index {image_index} out of range")

    entry = images[image_index]
    return [
        {
            "index": 0,
            "name": entry["name"],
            "type": f"PxiProject {'referenced' if entry['source'] == 'referenced' else 'embedded'}",
            "has_image": True,
            "linear": entry.get("linear", True),
        }
    ]
