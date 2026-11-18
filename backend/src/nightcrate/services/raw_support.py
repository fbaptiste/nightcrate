"""Runtime capability probe for camera-raw support."""

from __future__ import annotations

import importlib
import io
import logging
from functools import lru_cache

UNAVAILABLE_MESSAGE = "Raw files can't be read on this computer"
logger = logging.getLogger(__name__)


class RawUnavailable(RuntimeError):
    """Raised when this installation cannot load the raw-file libraries."""


@lru_cache(maxsize=1)
def problem() -> str | None:
    """Return a stable user-facing reason when raw support is unavailable."""
    try:
        rawpy = importlib.import_module("rawpy")
        exiv2 = importlib.import_module("exiv2")
        # Access one native-backed symbol from each module.  This catches broken
        # wheels whose Python package imports but whose bundled library does not.
        if not rawpy.libraw_version or exiv2.ImageFactory is None:
            raise RuntimeError("raw library probe failed")
    except Exception:  # noqa: BLE001 - a capability probe must fail closed
        return UNAVAILABLE_MESSAGE
    return None


def require() -> None:
    """Raise :class:`RawUnavailable` unless both raw libraries work."""
    reason = problem()
    if reason is not None:
        raise RawUnavailable(reason)


def self_check() -> str | None:
    """Exercise both native raw libraries against an in-memory Bayer DNG."""
    try:
        np = importlib.import_module("numpy")
        tifffile = importlib.import_module("tifffile")
        rawpy = importlib.import_module("rawpy")
        exiv2 = importlib.import_module("exiv2")
        samples = np.arange(32 * 34, dtype=np.uint16).reshape(32, 34) + 512
        output = io.BytesIO()
        tifffile.imwrite(
            output,
            samples,
            photometric=32803,
            metadata=None,
            extratags=[
                (50706, "B", 4, (1, 4, 0, 0), False),
                (50707, "B", 4, (1, 3, 0, 0), False),
                (50708, "s", 0, "NightCrate Generated Camera", False),
                (33421, "H", 2, (2, 2), False),
                (33422, "B", 4, (0, 1, 1, 2), False),
                (50714, "H", 1, 512, False),
                (50717, "I", 1, 16383, False),
                (271, "s", 0, "NightCrate", False),
                (272, "s", 0, "Generated DNG", False),
            ],
        )
        payload = output.getvalue()
        with rawpy.imread(io.BytesIO(payload)) as raw:
            if raw.raw_image_visible.shape != samples.shape:
                raise RuntimeError("raw sample shape mismatch")
        image = exiv2.ImageFactory.open(payload)
        image.readMetadata()
        if image.exifData()["Exif.Image.Make"].toString() != "NightCrate":
            raise RuntimeError("raw EXIF probe failed")
    except Exception:  # noqa: BLE001 - the installed-app probe must fail closed
        logger.warning("[raw] installed raw self-check failed", exc_info=True)
        return UNAVAILABLE_MESSAGE
    return None
