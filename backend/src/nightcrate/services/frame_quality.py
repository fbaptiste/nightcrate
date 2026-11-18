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
``median_adu``       Median of the recorded samples. All frame types.
``background_adu``   ``sep`` global background in recorded units. All types.
===================  ==========================================================

**Units follow the source.** Integer and camera-raw levels are recorded ADU;
floating-point sources stay floating point. ``quality_units`` identifies which.
Stars are always detected on the normalized measurement grey image.

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
from nightcrate.services.pixel_loader import LoadedImage, grey_of, samples_of

# Compatibility scale for legacy callers that pass a bare normalized array.
# LoadedImage callers keep their recorded units and do not use this constant.
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


def analyze_array(data: np.ndarray | LoadedImage, with_stars: bool) -> dict:
    """Compute the quality metrics for an already-loaded frame.

    *data* is normally a :class:`LoadedImage`, preserving recorded samples for
    levels and using its normalized measurement grey for stars. A bare ``[0,1]``
    array remains supported for older callers.

    Split out from :func:`analyze_frame_file` so the Image Analyzer can measure
    the array it already has in memory instead of re-reading the file. **Both
    callers go through here, which is the point:** the analyzer's numbers and the
    catalog's are the same computation with the same frozen settings, so they
    agree by construction rather than by two implementations happening to match.

    ``with_stars=False`` skips detection (the expensive part — roughly 0.36 s of
    a 0.42 s pass on a 26 MP frame) and returns the ADU stats only.
    """
    image = data if isinstance(data, LoadedImage) else None
    if image is not None:
        recorded = np.concatenate([np.ravel(channel) for channel in samples_of(image).values()])
        normalized = image.normalised()
        normalized_level_plane = (
            normalized.reshape(-1, image.width) if normalized.ndim == 3 else normalized
        )
        detection_data, block_size = grey_of(image)
        median = float(np.median(recorded))
        background = (
            None
            if with_stars and image.kind == "mono"
            else float(image.denormalise(background_level(normalized_level_plane)))
        )
        quality_units = image.units
    else:
        if data.ndim == 3 and data.shape[0] == 3:
            data = LUM_R * data[0] + LUM_G * data[1] + LUM_B * data[2]
        detection_data = data
        block_size = 1
        median = float(np.median(data)) * ADU_FULL_SCALE
        background = None if with_stars else background_level(data) * ADU_FULL_SCALE
        quality_units = "adu"

    result: dict = {
        "error": None,
        "status": "ok",
        "median_adu": round(median, 3),
        "background_adu": round(background, 3) if background is not None else None,
        "hfr": None,
        "star_count": None,
        "snr_estimate": None,
    }

    if with_stars:
        analysis = detect_stars(
            detection_data,
            QUALITY_SETTINGS,
            block_size=block_size,
            original_shape=(image.height, image.width) if image is not None else None,
        )
        result["star_count"] = analysis.star_count
        result["hfr"] = analysis.median_hfr
        result["snr_estimate"] = analysis.median_snr
        if background is None and analysis.background_level is not None:
            level = (
                float(image.denormalise(analysis.background_level))
                if image is not None
                else analysis.background_level * ADU_FULL_SCALE
            )
            result["background_adu"] = round(level, 3)
        if analysis.star_count == 0:
            # A real outcome, not a failure: clouds, a closed shutter, or a frame
            # that simply has nothing detectable in it. Recorded so the UI can
            # distinguish it from "we could not read this file".
            result["status"] = "no_stars"
    result["quality_units"] = quality_units

    return result


def analyze_frame_file(path: str, with_stars: bool) -> dict:
    """Worker: load one frame and compute its quality metrics.

    Module-level and picklable so it runs under ``ProcessPoolExecutor`` (spawn),
    mirroring ``ingest_scanner.parse_image_file``. Returns a plain dict and
    **never raises** — a failure comes back as ``{"path", "error"}`` so one
    unreadable file cannot abort the batch.
    """
    from nightcrate.core.compute import set_gpu_enabled
    from nightcrate.services.pixel_loader import load_image

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
        image = load_image(path)
        result = analyze_array(image, with_stars)
        result["path"] = path
        return result
    except Exception as exc:  # noqa: BLE001 - any failure is recorded, never fatal
        return {"path": path, "error": f"{type(exc).__name__}: {exc}"}
