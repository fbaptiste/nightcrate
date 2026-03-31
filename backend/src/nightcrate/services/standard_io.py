"""Standard image format I/O — PNG, JPEG, TIFF.

These are display-ready formats: no stretch is applied. Metadata is extracted
from EXIF (JPEG/TIFF) or PNG text chunks where available.
"""

import io
from pathlib import Path

from PIL import Image
from PIL.ExifTags import TAGS


def load_image_bytes(file_path: Path) -> bytes:
    """Load the image and return it as PNG bytes (for consistent frontend display)."""
    with Image.open(file_path) as img:
        if img.mode not in ("RGB", "RGBA", "L"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()


def read_header(file_path: Path) -> list[dict]:
    """Extract metadata as {key, value, comment} dicts.

    Reads EXIF data from JPEG/TIFF or text chunks from PNG.
    """
    with Image.open(file_path) as img:
        cards: list[dict] = []

        # Basic image info
        cards.append({"key": "Format", "value": img.format or "Unknown", "comment": ""})
        cards.append({"key": "Mode", "value": img.mode, "comment": "Color mode"})
        cards.append({"key": "Width", "value": str(img.width), "comment": "pixels"})
        cards.append({"key": "Height", "value": str(img.height), "comment": "pixels"})

        # EXIF (JPEG, TIFF)
        exif = getattr(img, "_getexif", lambda: None)()
        if exif:
            for tag_id, value in exif.items():
                tag_name = TAGS.get(tag_id, str(tag_id))
                # Skip binary/complex data
                if isinstance(value, (bytes, tuple)) and not isinstance(value, str):
                    if isinstance(value, tuple) and len(value) <= 3:
                        value = str(value)
                    else:
                        continue
                cards.append({"key": tag_name, "value": str(value)[:200], "comment": ""})

        # PNG text chunks
        if hasattr(img, "text"):
            for key, value in img.text.items():
                cards.append({"key": key, "value": str(value)[:200], "comment": "PNG text"})

        return cards


def list_extensions(file_path: Path) -> list[dict]:
    """Standard images have a single 'extension'."""
    with Image.open(file_path) as img:
        return [
            {
                "index": 0,
                "name": img.format or "Image",
                "type": f"{img.mode} ({img.width}x{img.height})",
                "has_image": True,
            }
        ]
