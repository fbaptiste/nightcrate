"""Standard image format I/O — PNG, JPEG, TIFF.

These are display-ready formats: no stretch is applied for 8/16-bit images.
Float32 TIFFs (common from PixInsight) are loaded as scientific images
with stretch support, same as FITS/XISF.
"""

import io
from pathlib import Path

import numpy as np
from PIL import Image
from PIL.ExifTags import TAGS

from nightcrate.services.imaging import normalize_to_01, reshape_color


def is_float_tiff(file_path: Path) -> bool:
    """Check if a TIFF file contains float data (needs scientific treatment)."""
    if file_path.suffix.lower() not in (".tif", ".tiff"):
        return False
    try:
        import tifffile

        with tifffile.TiffFile(str(file_path)) as tif:
            page = tif.pages[0]
            return page.dtype.kind == "f"  # float dtype
    except Exception:
        return False


def load_image_data(file_path: Path) -> np.ndarray:
    """Load a float TIFF as a normalized [0, 1] array for the stretch pipeline.

    Returns shape (H, W) for grayscale or (3, H, W) for RGB.
    """
    import tifffile

    arr = tifffile.imread(str(file_path))

    # Handle various shapes: (H, W), (H, W, C), (C, H, W)
    if arr.ndim == 2:
        pass  # grayscale
    elif arr.ndim == 3:
        if arr.shape[2] in (3, 4):
            # (H, W, C) → (C, H, W), drop alpha if present
            arr = np.moveaxis(arr[:, :, :3], -1, 0)
        # else assume already (C, H, W)
    else:
        raise ValueError(f"Unsupported TIFF array shape: {arr.shape}")

    normalized = normalize_to_01(arr)
    return reshape_color(normalized)


def load_image_bytes(file_path: Path) -> bytes:
    """Load the image and return it as PNG bytes (for consistent frontend display).

    For float TIFFs that Pillow can't handle, falls back to tifffile.
    """
    try:
        with Image.open(file_path) as img:
            if img.mode not in ("RGB", "RGBA", "L"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
    except Exception:
        # Fallback for float TIFFs — this path shouldn't normally be hit
        # since float TIFFs are routed through the stretch pipeline
        if file_path.suffix.lower() in (".tif", ".tiff"):
            import tifffile

            arr = tifffile.imread(str(file_path))
            if arr.dtype.kind == "f":
                arr = np.clip(arr * 255, 0, 255).astype(np.uint8)
            if arr.ndim == 3 and arr.shape[2] in (3, 4):
                mode = "RGB"
                arr = arr[:, :, :3]
            elif arr.ndim == 2:
                mode = "L"
            else:
                raise
            img = Image.fromarray(arr, mode=mode)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        raise


def read_header(file_path: Path) -> list[dict]:
    """Extract metadata as {key, value, comment} dicts.

    Reads EXIF data from JPEG/TIFF or text chunks from PNG.
    For float TIFFs, falls back to tifffile for basic info.
    """
    cards: list[dict] = []

    try:
        with Image.open(file_path) as img:
            cards.append({"key": "Format", "value": img.format or "Unknown", "comment": ""})
            cards.append({"key": "Mode", "value": img.mode, "comment": "Color mode"})
            cards.append({"key": "Width", "value": str(img.width), "comment": "pixels"})
            cards.append({"key": "Height", "value": str(img.height), "comment": "pixels"})

            exif = getattr(img, "_getexif", lambda: None)()
            if exif:
                for tag_id, value in exif.items():
                    tag_name = TAGS.get(tag_id, str(tag_id))
                    if isinstance(value, (bytes, tuple)) and not isinstance(value, str):
                        if isinstance(value, tuple) and len(value) <= 3:
                            value = str(value)
                        else:
                            continue
                    cards.append({"key": tag_name, "value": str(value)[:200], "comment": ""})

            if hasattr(img, "text"):
                for key, value in img.text.items():
                    cards.append({"key": key, "value": str(value)[:200], "comment": "PNG text"})

            return cards
    except Exception:
        if file_path.suffix.lower() not in (".tif", ".tiff"):
            raise

    # Fallback for float TIFFs
    import tifffile

    with tifffile.TiffFile(str(file_path)) as tif:
        page = tif.pages[0]
        cards.append({"key": "Format", "value": "TIFF", "comment": ""})
        cards.append({"key": "Mode", "value": str(page.dtype), "comment": "Data type"})
        cards.append({"key": "Width", "value": str(page.imagewidth), "comment": "pixels"})
        cards.append({"key": "Height", "value": str(page.imagelength), "comment": "pixels"})
        cards.append({"key": "SamplesPerPixel", "value": str(page.samplesperpixel), "comment": ""})
        cards.append({"key": "BitsPerSample", "value": str(page.bitspersample), "comment": ""})

    return cards


def list_extensions(file_path: Path) -> list[dict]:
    """Standard images have a single 'extension'."""
    try:
        with Image.open(file_path) as img:
            return [
                {
                    "index": 0,
                    "name": img.format or "Image",
                    "type": f"{img.mode} ({img.width}x{img.height})",
                    "has_image": True,
                }
            ]
    except Exception:
        if file_path.suffix.lower() not in (".tif", ".tiff"):
            raise

    import tifffile

    with tifffile.TiffFile(str(file_path)) as tif:
        page = tif.pages[0]
        return [
            {
                "index": 0,
                "name": "TIFF",
                "type": f"{page.dtype} ({page.imagewidth}x{page.imagelength})",
                "has_image": True,
            }
        ]
