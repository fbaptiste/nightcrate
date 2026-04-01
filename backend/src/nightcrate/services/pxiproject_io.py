"""PixInsight project (.pxiproject) I/O — reads XOSM manifests and embedded image data.

Based on the open XISF specification. A .pxiproject is a directory bundle containing
project.xosm (XML manifest) and project.data/ (binary blobs for pixel data).
"""

import struct
import zlib
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


def _extract_keyword(iw, ns: str, keyword_name: str) -> str | None:
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

    Returns a list of dicts with: index, name, source, file_path, data_src,
    filter, object, exposure, date_obs.
    """
    root, compression = _parse_xosm(project_dir)
    images = []

    for i, iw in enumerate(root.iter(_tag("ImageWindow"))):
        view = iw.get("currentView", f"Image_{i}")
        file_path = iw.get("filePath")
        is_referenced = bool(file_path)

        # Find data blob reference and STF state from MainView
        data_src = None
        is_linear = True
        mv = iw.find(_tag("MainView"))
        if mv is not None:
            img_el = mv.find(_tag("image"))
            if img_el is not None:
                src = img_el.get("src", "")
                data_src = src.replace("@project_data_dir/", "")

            # Detect linearity from STF params.
            # - STF enabled + small midtone (< 0.1) → linear image
            # - STF enabled + no stf elements → linear (PixInsight auto-computes)
            # - STF enabled + midtone = 0.5 (identity) → non-linear (already stretched)
            # - STF disabled → non-linear
            stf_enabled = mv.get("stfEnabled", "0") == "1"
            stf_elements = mv.findall(_tag("stf"))
            if not stf_enabled:
                is_linear = False
            elif not stf_elements:
                # STF enabled but no explicit params → auto-computed → linear
                is_linear = True
            else:
                try:
                    midtone = float(stf_elements[0].get("m", "0.5"))
                    is_linear = midtone < 0.1
                except ValueError:
                    is_linear = True

        # Extract metadata from FITS keywords
        filt = _extract_keyword(iw, XOSM_NS, "FILTER")
        obj = _extract_keyword(iw, XOSM_NS, "OBJECT")
        exptime = _extract_keyword(iw, XOSM_NS, "EXPTIME")
        date_obs = _extract_keyword(iw, XOSM_NS, "DATE-OBS")

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


def _parse_rawimage_header(data: bytes) -> tuple[int, int, int, int]:
    """Parse a rawimage blob header. Returns (width, height, total_channels, bps).

    The rawimage swap format header (128 bytes):
      offset  0: magic "egamiwar" (8 bytes)
      offset 15: bits_per_sample (uint8)
      offset 16: channels_in_blob (uint32 LE) — always 1 per channel section
      offset 28: width (uint32 LE)
      offset 32: height (uint32 LE)
      offset 36: total_channels (uint32 LE) — total channels in the image (e.g. 3 for RGB)

    For multi-channel images, pixel data after the header contains one channel
    section per channel, each with its own block structure.
    """
    if len(data) < RAWIMAGE_HEADER_SIZE:
        raise PxiProjectError("Blob too small for rawimage header")
    if data[:8] != RAWIMAGE_MAGIC:
        raise PxiProjectError(f"Bad rawimage magic: {data[:8]!r}")

    bps = data[15]
    width = struct.unpack_from("<I", data, 28)[0]
    height = struct.unpack_from("<I", data, 32)[0]
    total_channels = struct.unpack_from("<I", data, 36)[0]
    # Fallback: if total_channels is 0 or missing, use channels_in_blob
    if total_channels == 0:
        total_channels = struct.unpack_from("<I", data, 16)[0]

    return width, height, total_channels, bps


def _decompress_channel_section(raw_data: bytes, offset: int, base_codec: str) -> tuple[bytes, int]:
    """Decompress one channel section (num_blocks + blocks). Returns (data, new_offset)."""
    num_blocks = struct.unpack_from("<I", raw_data, offset)[0]
    offset += 4
    result = bytearray()

    for _ in range(num_blocks):
        if offset + 16 > len(raw_data):
            raise PxiProjectError("Truncated block header")
        comp_size, uncomp_size = struct.unpack_from("<QQ", raw_data, offset)
        offset += 16

        # Skip 16-byte block prefix
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
            dctx = zstandard.ZstdDecompressor()
            result.extend(dctx.decompress(chunk, max_output_size=uncomp_size))
        else:
            raise PxiProjectError(f"Unsupported compression: {base_codec}")

    return bytes(result), offset


def _decompress_blob(raw_data: bytes, compression: str, num_channels: int) -> bytes:
    """Decompress pixel data from a rawimage swap blob (after the 128-byte header).

    For multi-channel images, the blob contains one channel section per channel,
    each with its own num_blocks + block data. Channels are concatenated (planar).
    """
    if compression == "none":
        return raw_data

    base_codec = compression.replace("+sh", "").replace("+sc", "")

    result = bytearray()
    offset = 0

    for _ in range(num_channels):
        channel_data, offset = _decompress_channel_section(raw_data, offset, base_codec)
        result.extend(channel_data)

    return bytes(result)


def load_image_data(project_dir: Path, image_index: int) -> np.ndarray:
    """Load an image from a .pxiproject as a float array normalized to [0, 1].

    For referenced images, delegates to xisf_io.
    For embedded images, reads and decompresses the blob from project.data/.
    Returns shape (H, W) for mono or (3, H, W) for color.
    """
    images = list_project_images(project_dir)
    if image_index < 0 or image_index >= len(images):
        raise ValueError(
            f"Image index {image_index} out of range (project has {len(images)} images)"
        )

    entry = images[image_index]

    # Referenced images: delegate to xisf_io
    if entry["source"] == "referenced" and entry["file_path"]:
        from nightcrate.services import xisf_io

        ref_path = Path(entry["file_path"])
        if not ref_path.exists():
            raise FileNotFoundError(f"Referenced file not found: {entry['file_path']}")
        return xisf_io.load_image_data(ref_path)

    # Embedded images: read blob from project.data/
    if not entry["data_src"]:
        raise PxiProjectError(f"No data source for embedded image '{entry['name']}'")

    blob_path = project_dir / "project.data" / entry["data_src"]
    if not blob_path.exists():
        raise FileNotFoundError(f"Blob not found: {blob_path}")

    with open(blob_path, "rb") as f:
        blob = f.read()

    width, height, channels, bps = _parse_rawimage_header(blob)

    # Get compression method from project
    _, compression = _parse_xosm(project_dir)

    # Pixel data starts after the 128-byte header
    pixel_data = blob[RAWIMAGE_HEADER_SIZE:]

    if compression != "none":
        pixel_data = _decompress_blob(pixel_data, compression, channels)

    # Determine dtype
    if bps == 32:
        dtype = np.float32
    elif bps == 64:
        dtype = np.float64
    elif bps == 16:
        dtype = np.uint16
    elif bps == 8:
        dtype = np.uint8
    else:
        raise PxiProjectError(f"Unsupported bits per sample: {bps}")

    arr = np.frombuffer(pixel_data, dtype=dtype)

    if channels == 1:
        arr = arr.reshape(height, width)
    else:
        arr = arr.reshape(channels, height, width)

    normalized = normalize_to_01(arr)
    return reshape_color(normalized)


def read_header(project_dir: Path, image_index: int) -> list[dict]:
    """Read FITS keywords from a project image's XOSM metadata."""
    root, _ = _parse_xosm(project_dir)

    image_windows = list(root.iter(_tag("ImageWindow")))
    if image_index < 0 or image_index >= len(image_windows):
        raise ValueError(
            f"Image index {image_index} out of range (project has {len(image_windows)} images)"
        )

    iw = image_windows[image_index]
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
    images = list_project_images(project_dir)
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
