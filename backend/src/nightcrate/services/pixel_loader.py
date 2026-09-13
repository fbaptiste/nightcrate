"""Load a frame's pixel array from a path string, at native resolution.

Turns *any* path this app accepts — a plain file, an archive entry
(``archive.zip::entry``), a PixInsight project image (``project.pxiproject::N``) —
into a normalized ``[0, 1]`` numpy array.

**This is not yet the only copy of that dispatch.** ``services/catalog_thumbnail.py``
was migrated onto it; ``api/images.py:_load_image_data`` and
``api/aberration.py:_load_mono_data`` still hand-roll the same ``file_type`` ladder,
because both hold an already-resolved ``(source, file_type, index)`` for their caches
rather than a path string. They have already drifted — this module wraps pxiproject /
float-TIFF / standard results in ``imaging.reshape_color`` and ``api/images.py`` does
not. Folding them in means splitting the dispatch below into a
``load_from_resolved(source, file_type, index, hdu)`` seam that those two can call;
until that happens, a new format needs editing here *and* in both api modules.

**Pure numpy, safe in a worker process.** Every loader reached from here imports
only numpy/astropy/PIL — nothing touches ``core.compute.get_array_module()``, so
this is callable from a ``ProcessPoolExecutor`` worker or a thread. See
``services/frame_quality.py`` for why that matters.

**Raises ``ValueError``, never ``HTTPException``.** ``path_resolver.resolve_path``
raises FastAPI's ``HTTPException`` on a bad path, which must not escape into a
spawn worker (it would pickle a web-framework exception across a process
boundary). Converted here, following the ``services/plate_solve.py`` precedent.
"""

from __future__ import annotations

import numpy as np

from nightcrate.services import fits_io, pxiproject_io, standard_io, xisf_io
from nightcrate.services.imaging import LUM_B, LUM_G, LUM_R, reshape_color
from nightcrate.services.path_resolver import resolve_path as _resolve_path_raw


def resolve(path: str) -> tuple[object, str, int]:
    """Resolve *path* to ``(source, file_type, image_index)``.

    Wraps ``path_resolver.resolve_path``, converting ``HTTPException`` to
    ``ValueError`` so callers outside the HTTP layer get a plain exception.
    """
    try:
        resolved, ft, idx, _cache_key = _resolve_path_raw(path)
    except Exception as exc:
        if type(exc).__name__ == "HTTPException":
            raise ValueError(getattr(exc, "detail", str(exc))) from None
        raise
    return resolved, ft, idx


def load_normalized(path: str, hdu: int = 0) -> np.ndarray:
    """Load *path* as a ``[0, 1]`` array, shape (H, W) mono or (3, H, W) color.

    Native resolution — no decimation. The per-format loaders already normalize
    (``imaging.normalize_to_01``) and reshape.
    """
    resolved, ft, idx = resolve(path)
    if ft == "pxiproject":
        return reshape_color(pxiproject_io.load_image_data(resolved, idx))
    if ft == "fits":
        return fits_io.load_image_data(resolved, hdu)
    if ft == "xisf":
        return xisf_io.load_image_data(resolved, hdu)
    if ft == "float_tiff":
        return reshape_color(standard_io.load_image_data(resolved))
    if ft == "standard":
        return reshape_color(standard_io.load_image_as_array(resolved))
    raise ValueError(f"Unsupported file type: {ft}")


def load_normalized_mono(path: str, hdu: int = 0) -> np.ndarray:
    """Load *path* as a 2D float64 ``[0, 1]`` array, collapsing color to luminance.

    Star detection and the frame-quality pass are mono-only; a colour frame is
    collapsed with the same Rec. 709 weights the rest of the app uses.
    """
    data = load_normalized(path, hdu)
    if data.ndim == 3 and data.shape[0] == 3:
        mono = LUM_R * data[0] + LUM_G * data[1] + LUM_B * data[2]
        return mono.astype(np.float64)
    return data.astype(np.float64)
