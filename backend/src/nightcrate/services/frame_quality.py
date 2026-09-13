"""Per-frame quality metrics for cataloged sub frames (v0.41.3).

Fills the five ``sub_frame`` quality columns that migration 0037 created and left
empty. This is **catalog metadata, not a culling workflow** (arc-wide decision,
2026-07-08): it feeds the session timeline and the context bundle, and helps spot
a frame worth opening in the analyzer. Sub weighting and rejection stay in
PixInsight.

Metric definitions — these are the contract, keep them in step with the columns:

===================  ==========================================================
``hfr``              Median per-star half-flux radius, **pixels**. Lights only.
``star_count``       Stars surviving ``QUALITY_SETTINGS``. Lights only.
``snr_estimate``     Median per-star SNR (flux/fluxerr). Lights only.
``median_adu``       ``median(data) * ADU_FULL_SCALE``. All frame types.
``background_adu``   ``sep`` global background * ``ADU_FULL_SCALE``. All types.
===================  ==========================================================

**Units — 16-bit-equivalent ADU.** ``imaging.normalize_to_01`` is type-based, not
min-max: ``uint16`` is divided by 65535 and float data is assumed already in
``[0, 1]``. Multiplying back by 65535 therefore recovers **true ADU for integer
sources** and yields a **16-bit-equivalent** scale for PixInsight float XISF
(which carries no bit depth at all). One comparable scale across the catalog —
but do not present the float-sourced numbers as real ADU.

**HFR is in pixels and only comparable within a rig.** ``pixel_scale_arcsec`` is
usually NULL on a cataloged frame, so there is no honest arcsec conversion here.

**``QUALITY_SETTINGS`` is frozen and deliberately not user-tunable.** HFR is only
comparable across frames measured with identical detection settings; exposing
sliders would silently make the catalog incomparable to itself. Changing these
constants in a future version means invalidating every stored value.

**Pure numpy — never the GPU backend.** mlx (Apple Metal) is not safe to call
concurrently, and this pass fans out across a ProcessPool. ``detect_stars`` is
numpy+sep only, but ``imaging.compute_image_stats`` routes through
``get_array_module()``, so the median is computed here in numpy instead. A
regression test pins this. See CLAUDE.md's note on the thumbnail path, which hit
the same wall.

Pure service: no DB, no FastAPI. ``api/ingest.py`` owns the transaction.
"""

from __future__ import annotations

import numpy as np

from nightcrate.services.aberration import DetectionSettings, background_level, detect_stars
from nightcrate.services.imaging import LUM_B, LUM_G, LUM_R

# Full-scale value the normalized [0, 1] arrays are scaled back by. See the
# module docstring — this is real ADU for integer sources, 16-bit-equivalent
# for float ones.
ADU_FULL_SCALE = 65535.0

# Frozen detection settings for the batch pass. Deliberately the library
# defaults: measured against real 26 MP subs, loosening min_star_snr /
# min_separation_px / max_semi_major_px moved the count by under 3 %, so the
# stricter isolated-star set is kept — it is the one that makes HFR meaningful.
# detection_threshold is the sensitive knob; leave it alone without re-measuring.
QUALITY_SETTINGS = DetectionSettings()

# Frame types that carry stars worth measuring. Everything else gets the ADU
# stats only — a dark has no HFR, and pretending otherwise would put noise in a
# column the calibration views and the context bundle read.
STAR_BEARING_FRAME_TYPES = frozenset({"light"})


def wants_stars(frame_type: str | None) -> bool:
    """True when star detection is meaningful for this frame type."""
    return (frame_type or "") in STAR_BEARING_FRAME_TYPES


def analyze_array(data: np.ndarray, with_stars: bool) -> dict:
    """Compute the quality metrics for an already-loaded frame.

    *data* is a ``[0, 1]`` array — 2D mono, or (3, H, W) colour, which is
    collapsed to luminance since detection is mono-only.

    Split out from :func:`analyze_frame_file` so the Image Analyzer can measure
    the array it already has in memory instead of re-reading the file. **Both
    callers go through here, which is the point:** the analyzer's numbers and the
    catalog's are the same computation with the same frozen settings, so they
    agree by construction rather than by two implementations happening to match.

    ``with_stars=False`` skips detection (the expensive part — roughly 0.36 s of
    a 0.42 s pass on a 26 MP frame) and returns the ADU stats only.
    """
    if data.ndim == 3 and data.shape[0] == 3:
        data = LUM_R * data[0] + LUM_G * data[1] + LUM_B * data[2]

    result: dict = {
        "error": None,
        "status": "ok",
        "median_adu": round(float(np.median(data)) * ADU_FULL_SCALE, 3),
        "background_adu": None,
        "hfr": None,
        "star_count": None,
        "snr_estimate": None,
    }

    if with_stars:
        analysis = detect_stars(data, QUALITY_SETTINGS)
        result["star_count"] = analysis.star_count
        result["hfr"] = analysis.median_hfr
        result["snr_estimate"] = analysis.median_snr
        if analysis.background_level is not None:
            result["background_adu"] = round(analysis.background_level * ADU_FULL_SCALE, 3)
        if analysis.star_count == 0:
            # A real outcome, not a failure: clouds, a closed shutter, or a frame
            # that simply has nothing detectable in it. Recorded so the UI can
            # distinguish it from "we could not read this file".
            result["status"] = "no_stars"
    else:
        result["background_adu"] = round(background_level(data) * ADU_FULL_SCALE, 3)

    return result


def analyze_frame_file(path: str, with_stars: bool) -> dict:
    """Worker: load one frame and compute its quality metrics.

    Module-level and picklable so it runs under ``ProcessPoolExecutor`` (spawn),
    mirroring ``ingest_scanner.parse_image_file``. Returns a plain dict and
    **never raises** — a failure comes back as ``{"path", "error"}`` so one
    unreadable file cannot abort the batch.
    """
    from nightcrate.core.compute import set_gpu_enabled
    from nightcrate.services.pixel_loader import load_normalized_mono

    # A fresh spawn worker starts with _gpu_enabled = True regardless of the
    # user's setting, so anything that reached get_array_module() here would pick
    # mlx. Nothing on this path should, but the guard is one line.
    #
    # It belongs HERE and not in analyze_array: this function only ever runs in a
    # worker process, whereas analyze_array is also called in-process by the
    # Image Analyzer — where flipping the flag would silently disable mlx for the
    # whole app, including the image renderer.
    set_gpu_enabled(False)

    try:
        result = analyze_array(load_normalized_mono(path), with_stars)
        result["path"] = path
        return result
    except Exception as exc:  # noqa: BLE001 - any failure is recorded, never fatal
        return {"path": path, "error": f"{type(exc).__name__}: {exc}"}
