"""Rig optical calculator formulas.

Pure math module with no DB or API dependencies.  Computes image scale,
field of view, resolution limits, sensor coverage, sampling assessment,
and guide system metrics for rig configurations.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

# Unicode constants used in recommendation text.
_ARCSEC = "\u2033"  # double prime (arcsecond)
_ENDASH = "\u2013"  # en dash
_TIMES = "\u00d7"  # multiplication sign
_EMDASH = "\u2014"  # em dash
_RSQUOTE = "\u2019"  # right single quotation mark

# Pre-scaled radians-to-arcseconds factor for the common astrophotography
# shortcut formula: arcsec_per_pixel = (pixel_size_um / focal_length_mm) × 206.265
# (bakes the µm→m and mm→m unit scaling into the full 1 rad = 206264.8″ factor).
_RAD_TO_ARCSEC = 206.265

# Default seeing range when no location or override is provided.
_DEFAULT_SEEING_LOW = 2.0
_DEFAULT_SEEING_HIGH = 4.0

# Guide suitability constants.
#
# The 6"/pixel hard cap is a practical PHD2 guiding limit: beyond this,
# guide star centroiding fails regardless of how favorable the G-ratio is.
GUIDE_SCALE_HARD_CAP_ARCSEC = 6.0

DEFAULT_CENTROID_ACCURACY_PIXELS = 0.2
DEFAULT_GUIDE_BINNING = 1
MIN_GUIDE_BINNING = 1
MAX_GUIDE_BINNING = 4

# Rating thresholds keyed on effective_error_main_pixels (guide error
# expressed as main-camera pixels, with the current centroid accuracy).
# The first band whose threshold is >= error_main_px wins.
_GUIDE_RATING_BANDS: tuple[tuple[str, float], ...] = (
    ("excellent", 0.6),
    ("good", 1.0),
    ("marginal", 1.2),
)
# Anything above the final threshold rates as "poor".


# ---------------------------------------------------------------------------
# Image Scale
# ---------------------------------------------------------------------------


def compute_image_scale(pixel_size_um: float, focal_length_mm: float) -> float:
    """Compute image scale in arcseconds per pixel.

    Formula: (pixel_size_um / focal_length_mm) * 206.265
    """
    return (pixel_size_um / focal_length_mm) * _RAD_TO_ARCSEC


def compute_image_scale_binned(base_scale: float) -> dict[int, float]:
    """Compute image scale for binning factors 1 through 4."""
    return {b: base_scale * b for b in range(1, 5)}


# ---------------------------------------------------------------------------
# Field of View
# ---------------------------------------------------------------------------


def compute_fov(
    focal_length_mm: float,
    sensor_width_mm: float | None,
    sensor_height_mm: float | None,
    resolution_x: int,
    resolution_y: int,
    pixel_size_um: float,
) -> tuple[float, float]:
    """Compute field of view in degrees (width, height).

    Prefers the arctan formula with physical sensor dimensions when
    available, falls back to computing sensor size from pixel count
    and pixel size.
    """
    w_mm = sensor_width_mm
    h_mm = sensor_height_mm

    # Fallback: derive physical sensor dimensions from pixels.
    if w_mm is None or h_mm is None:
        w_mm = resolution_x * pixel_size_um / 1000.0
        h_mm = resolution_y * pixel_size_um / 1000.0

    width_deg = 2.0 * math.degrees(math.atan(w_mm / (2.0 * focal_length_mm)))
    height_deg = 2.0 * math.degrees(math.atan(h_mm / (2.0 * focal_length_mm)))
    return width_deg, height_deg


# ---------------------------------------------------------------------------
# Resolution Limits
# ---------------------------------------------------------------------------


def compute_resolution_limits(
    aperture_mm: float,
) -> tuple[float, float, float]:
    """Compute Dawes limit, Rayleigh limit, and maximum useful magnification.

    Returns (dawes_arcsec, rayleigh_arcsec, max_magnification).
    """
    dawes = 116.0 / aperture_mm
    rayleigh = 138.0 / aperture_mm
    max_mag = 2.0 * aperture_mm
    return dawes, rayleigh, max_mag


# ---------------------------------------------------------------------------
# Sensor Coverage
# ---------------------------------------------------------------------------


def compute_sensor_diagonal(
    sensor_width_mm: float | None = None,
    sensor_height_mm: float | None = None,
    resolution_x: int | None = None,
    resolution_y: int | None = None,
    pixel_size_um: float | None = None,
) -> float | None:
    """Compute sensor diagonal in mm.

    Uses physical dimensions when available, otherwise derives from
    pixel count and pixel size.  Returns None if neither is possible.
    """
    w = sensor_width_mm
    h = sensor_height_mm

    if w is None or h is None:
        if resolution_x is not None and resolution_y is not None and pixel_size_um is not None:
            w = resolution_x * pixel_size_um / 1000.0
            h = resolution_y * pixel_size_um / 1000.0
        else:
            return None

    return math.hypot(w, h)


def compute_sensor_coverage(
    sensor_diagonal_mm: float,
    image_circle_mm: float,
) -> float:
    """Compute sensor coverage as a percentage of the image circle.

    Values > 100 indicate the sensor exceeds the image circle and
    vignetting will occur at the corners.
    """
    return (sensor_diagonal_mm / image_circle_mm) * 100.0


# ---------------------------------------------------------------------------
# Seeing Resolution
# ---------------------------------------------------------------------------


def resolve_seeing(
    location_seeing_low: float | None = None,
    location_seeing_high: float | None = None,
    location_name: str | None = None,
    override_low: float | None = None,
    override_high: float | None = None,
) -> tuple[float, float, str, str | None]:
    """Determine the seeing range to use for sampling assessment.

    Priority: override > location > default (2-4").

    Override activates when EITHER `override_low` or `override_high` is
    provided; the missing side is mirrored from the provided one (so a
    single-value slider reads as `(v, v)`).

    Returns (low, high, source, location_name_or_none).
    """
    if override_low is not None or override_high is not None:
        low = override_low if override_low is not None else override_high
        high = override_high if override_high is not None else override_low
        return low, high, "override", None

    if location_seeing_low is not None:
        high = location_seeing_high if location_seeing_high is not None else location_seeing_low
        return location_seeing_low, high, "location", location_name

    return _DEFAULT_SEEING_LOW, _DEFAULT_SEEING_HIGH, "default", None


# ---------------------------------------------------------------------------
# Sampling Assessment
# ---------------------------------------------------------------------------


@dataclass
class SamplingResult:
    """Result of a sampling assessment."""

    image_scale: float
    ideal_range_low: float
    ideal_range_high: float
    seeing_fwhm_low: float
    seeing_fwhm_high: float
    seeing_source: str
    seeing_location_name: str | None
    assessment: str  # "oversampled" | "well_sampled" | "undersampled"
    recommendation: str
    binning_recommendations: dict[int, str]


def _assess_scale(scale: float, ideal_low: float, ideal_high: float) -> str:
    """Classify a single image scale against the ideal range."""
    if scale < ideal_low:
        return "oversampled"
    if scale > ideal_high:
        return "undersampled"
    return "well_sampled"


def _build_recommendation(
    assessment: str,
    scale: float,
    seeing_low: float,
    seeing_high: float,
    seeing_source: str,
    seeing_location_name: str | None,
) -> str:
    """Build a human-readable recommendation string."""
    if assessment == "oversampled":
        scale_2x = scale * 2
        text = (
            f"At {scale:.3f}{_ARCSEC}/pixel unbinned, this setup is oversampled "
            f"for {seeing_low:.1f}{_ENDASH}{seeing_high:.1f}{_ARCSEC} seeing. "
            f"Consider 2{_TIMES} binning ({scale_2x:.3f}{_ARCSEC}/pixel) for better SNR."
        )
    elif assessment == "well_sampled":
        text = (
            f"At {scale:.3f}{_ARCSEC}/pixel, this setup is well-matched "
            f"to {seeing_low:.1f}{_ENDASH}{seeing_high:.1f}{_ARCSEC} seeing conditions."
        )
    else:
        text = (
            f"At {scale:.3f}{_ARCSEC}/pixel, this setup is undersampled "
            f"for {seeing_low:.1f}{_ENDASH}{seeing_high:.1f}{_ARCSEC} seeing. "
            f"Stars will appear blocky. Consider a longer focal length or smaller pixels."
        )

    if seeing_source == "location" and seeing_location_name:
        text += f" (seeing from {seeing_location_name})"
    elif seeing_source == "default":
        text += (
            f" (using default 2{_ENDASH}4{_ARCSEC} seeing "
            f"{_EMDASH} set your location{_RSQUOTE}s typical seeing "
            f"for a more accurate assessment)"
        )

    return text


def assess_sampling(
    image_scale: float,
    seeing_fwhm_low: float,
    seeing_fwhm_high: float,
    seeing_source: str = "location",
    seeing_location_name: str | None = None,
) -> SamplingResult:
    """Assess whether an image scale is well-sampled for given seeing.

    Ideal sampling range: low = seeing_low / 3.0, high = seeing_high / 2.0.
    """
    ideal_low = seeing_fwhm_low / 3.0
    ideal_high = seeing_fwhm_high / 2.0

    assessment = _assess_scale(image_scale, ideal_low, ideal_high)

    # Assess each binning factor.
    binned_scales = compute_image_scale_binned(image_scale)
    binning_recs = {b: _assess_scale(s, ideal_low, ideal_high) for b, s in binned_scales.items()}

    recommendation = _build_recommendation(
        assessment,
        image_scale,
        seeing_fwhm_low,
        seeing_fwhm_high,
        seeing_source,
        seeing_location_name,
    )

    return SamplingResult(
        image_scale=image_scale,
        ideal_range_low=ideal_low,
        ideal_range_high=ideal_high,
        seeing_fwhm_low=seeing_fwhm_low,
        seeing_fwhm_high=seeing_fwhm_high,
        seeing_source=seeing_source,
        seeing_location_name=seeing_location_name,
        assessment=assessment,
        recommendation=recommendation,
        binning_recommendations=binning_recs,
    )


# ---------------------------------------------------------------------------
# Guide Suitability
# ---------------------------------------------------------------------------


@dataclass
class GuideSuitability:
    """Result of a guide-system suitability assessment."""

    mode: str  # "guide_scope" | "oag"
    guide_focal_length_mm: float
    guide_pixel_size_um: float  # native (unbinned)
    guide_binning: int
    effective_guide_pixel_size_um: float  # pixel_size * binning
    unbinned_guide_scale_arcsec_per_pixel: float
    guide_scale_arcsec_per_pixel: float  # binned
    guide_fov_width_arcmin: float  # unchanged by binning
    guide_fov_height_arcmin: float  # unchanged by binning
    centroid_accuracy_pixels: float
    effective_guide_precision_arcsec: float
    g_ratio: float
    effective_error_main_pixels: float
    rating: str  # "excellent" | "good" | "marginal" | "poor"
    rating_reason: str  # "ratio" | "scale_cap"
    recommendation: str
    caveat: str


def _classify_guide_rating(effective_error_main_pixels: float) -> str:
    """Classify effective guide error (in main pixels) against rating bands."""
    for rating, threshold in _GUIDE_RATING_BANDS:
        if effective_error_main_pixels <= threshold:
            return rating
    return "poor"


def _build_guide_recommendation(
    rating: str,
    rating_reason: str,
    guide_scale_arcsec_per_pixel: float,
    effective_guide_precision_arcsec: float,
    effective_error_main_pixels: float,
) -> str:
    """Build a human-readable recommendation for a guide suitability rating."""
    if rating_reason == "scale_cap":
        return (
            f"Guide scale is {guide_scale_arcsec_per_pixel:.2f}{_ARCSEC}/pixel "
            f"{_EMDASH} coarser than the practical limit of "
            f"{GUIDE_SCALE_HARD_CAP_ARCSEC:.0f}{_ARCSEC}/pixel for reliable PHD2 guiding. "
            f"Increase guide focal length or use a smaller-pixel guide camera."
        )

    precision_main_px = f"{effective_error_main_pixels:.2f} main-camera pixels"
    precision_arcsec = f"{effective_guide_precision_arcsec:.2f}{_ARCSEC}"

    if rating == "excellent":
        return (
            f"Guide precision of {precision_arcsec} is {precision_main_px} "
            f"{_EMDASH} guide errors will be well below your imaging resolution."
        )
    if rating == "good":
        return (
            f"Guide precision of {precision_arcsec} is {precision_main_px} "
            f"{_EMDASH} within the standard guideline of \u22641 main pixel."
        )
    if rating == "marginal":
        return (
            f"Guide precision of {precision_arcsec} is {precision_main_px} "
            f"{_EMDASH} borderline; tight guiding may be difficult on high-resolution "
            f"targets. Consider a longer guide focal length or smaller-pixel guide camera."
        )
    # poor (ratio-driven)
    return (
        f"Guide precision of {precision_arcsec} is {precision_main_px} "
        f"{_EMDASH} guide errors will likely show as elongated stars. "
        f"Increase guide focal length, use a guide camera with smaller pixels, "
        f"or switch to OAG."
    )


_CAVEAT_GUIDE_SCOPE = (
    "Note: guide-scope setups are subject to differential flexure between "
    "the guide scope and main scope; even an excellent rating cannot rule "
    "this out."
)
_CAVEAT_OAG = (
    "Note: OAG eliminates differential flexure but guide stars are sampled "
    "off-axis, where star quality may be lower than on-axis."
)


def compute_guide_suitability(
    guide_scope_id: int | None,
    oag_id: int | None,
    guide_scope_focal_length_mm: float | None,
    telescope_effective_focal_length_mm: float,
    guide_pixel_size_um: float | None,
    guide_resolution_x: int | None,
    guide_resolution_y: int | None,
    main_pixel_size_um: float,
    main_focal_length_mm: float,
    guide_binning: int = DEFAULT_GUIDE_BINNING,
    centroid_accuracy_pixels: float = DEFAULT_CENTROID_ACCURACY_PIXELS,
) -> GuideSuitability | None:
    """Compute guide suitability for guide-scope or OAG mode.

    Returns None when no guide system can be evaluated: missing guide
    camera data, missing optical path, or a guide-scope path with no
    focal length on file.
    """
    # Must have guide camera data.
    if guide_pixel_size_um is None or guide_resolution_x is None or guide_resolution_y is None:
        return None

    # Mode resolution and focal-length source.
    if guide_scope_id is not None:
        mode = "guide_scope"
        guide_focal_length_mm = guide_scope_focal_length_mm
    elif oag_id is not None:
        mode = "oag"
        guide_focal_length_mm = telescope_effective_focal_length_mm
    else:
        return None

    if guide_focal_length_mm is None:
        # Guide-scope path with no focal length on file.
        return None

    effective_guide_pixel_size_um = guide_pixel_size_um * guide_binning

    unbinned_guide_scale = compute_image_scale(guide_pixel_size_um, guide_focal_length_mm)
    guide_scale = compute_image_scale(effective_guide_pixel_size_um, guide_focal_length_mm)

    # FOV uses unbinned dimensions: physical sensor is the same at any binning.
    fov_w_arcmin = (guide_resolution_x * unbinned_guide_scale) / 60.0
    fov_h_arcmin = (guide_resolution_y * unbinned_guide_scale) / 60.0

    main_scale = compute_image_scale(main_pixel_size_um, main_focal_length_mm)

    effective_guide_precision_arcsec = guide_scale * centroid_accuracy_pixels
    g_ratio = guide_scale / main_scale
    effective_error_main_pixels = g_ratio * centroid_accuracy_pixels

    # Rating: worst of G-ratio band and absolute scale cap. Cap wins when both fail.
    ratio_rating = _classify_guide_rating(effective_error_main_pixels)
    cap_exceeded = guide_scale > GUIDE_SCALE_HARD_CAP_ARCSEC
    if cap_exceeded:
        rating = "poor"
        rating_reason = "scale_cap"
    else:
        rating = ratio_rating
        rating_reason = "ratio"

    recommendation = _build_guide_recommendation(
        rating,
        rating_reason,
        guide_scale,
        effective_guide_precision_arcsec,
        effective_error_main_pixels,
    )
    caveat = _CAVEAT_GUIDE_SCOPE if mode == "guide_scope" else _CAVEAT_OAG

    return GuideSuitability(
        mode=mode,
        guide_focal_length_mm=guide_focal_length_mm,
        guide_pixel_size_um=guide_pixel_size_um,
        guide_binning=guide_binning,
        effective_guide_pixel_size_um=effective_guide_pixel_size_um,
        unbinned_guide_scale_arcsec_per_pixel=unbinned_guide_scale,
        guide_scale_arcsec_per_pixel=guide_scale,
        guide_fov_width_arcmin=fov_w_arcmin,
        guide_fov_height_arcmin=fov_h_arcmin,
        centroid_accuracy_pixels=centroid_accuracy_pixels,
        effective_guide_precision_arcsec=effective_guide_precision_arcsec,
        g_ratio=g_ratio,
        effective_error_main_pixels=effective_error_main_pixels,
        rating=rating,
        rating_reason=rating_reason,
        recommendation=recommendation,
        caveat=caveat,
    )


# ---------------------------------------------------------------------------
# Guiding Tolerance
# ---------------------------------------------------------------------------


DEFAULT_IMAGE_BINNING = 1
MIN_IMAGE_BINNING = 1
MAX_IMAGE_BINNING = 4


@dataclass
class GuidingTolerance:
    """How much PHD2 RMS the current rig can tolerate before stars elongate."""

    main_scale_arcsec_per_pixel: float  # binned
    image_binning: int
    tight_rms_arcsec: float  # 0.5 × main scale
    acceptable_rms_arcsec: float  # 1.0 × main scale
    noticeable_rms_arcsec: float  # 1.5 × main scale
    current_guide_precision_arcsec: float | None
    guide_system_within_tight: bool | None
    guide_system_within_acceptable: bool | None
    headroom_arcsec: float | None  # tight - current; may be negative
    interpretation: str


def compute_guiding_tolerance(
    unbinned_main_scale_arcsec_per_pixel: float,
    image_binning: int,
    guide_suitability: GuideSuitability | None,
) -> GuidingTolerance:
    """Compute guiding-tolerance thresholds for the current rig + binning.

    The binned main scale drives all three thresholds. When a guide system
    is configured, compare its effective precision to the thresholds and
    generate an interpretation line.
    """
    binned_scale = unbinned_main_scale_arcsec_per_pixel * image_binning
    tight = 0.5 * binned_scale
    acceptable = 1.0 * binned_scale
    noticeable = 1.5 * binned_scale

    current: float | None = None
    within_tight: bool | None = None
    within_acceptable: bool | None = None
    headroom: float | None = None

    if guide_suitability is not None:
        current = guide_suitability.effective_guide_precision_arcsec
        within_tight = current <= tight
        within_acceptable = current <= acceptable
        headroom = tight - current

    if current is None:
        interpretation = (
            "Compare your measured PHD2 RMS (in arcseconds) to these thresholds "
            "to judge whether it\u2019s keeping up with this rig."
        )
    elif within_tight:
        interpretation = (
            f"Your guide system resolves to {current:.2f}{_ARCSEC} \u2014 comfortably "
            f"within the {tight:.2f}{_ARCSEC} tight budget. Stars will stay round."
        )
    elif within_acceptable:
        interpretation = (
            f"Your guide system resolves to {current:.2f}{_ARCSEC} \u2014 within the "
            f"{acceptable:.2f}{_ARCSEC} acceptable budget. Star elongation will be "
            f"barely noticeable."
        )
    else:
        interpretation = (
            f"Your guide system resolves to {current:.2f}{_ARCSEC}, which exceeds the "
            f"{acceptable:.2f}{_ARCSEC} acceptable budget \u2014 expect visibly "
            f"elongated stars even with perfect tracking."
        )

    return GuidingTolerance(
        main_scale_arcsec_per_pixel=binned_scale,
        image_binning=image_binning,
        tight_rms_arcsec=tight,
        acceptable_rms_arcsec=acceptable,
        noticeable_rms_arcsec=noticeable,
        current_guide_precision_arcsec=current,
        guide_system_within_tight=within_tight,
        guide_system_within_acceptable=within_acceptable,
        headroom_arcsec=headroom,
        interpretation=interpretation,
    )


# ---------------------------------------------------------------------------
# Full Calculator
# ---------------------------------------------------------------------------


def compute_rig_calculators(
    pixel_size_um: float,
    focal_length_mm: float,
    focal_ratio: float,
    aperture_mm: float,
    resolution_x: int,
    resolution_y: int,
    sensor_width_mm: float | None,
    sensor_height_mm: float | None,
    image_circle_mm: float | None,
    seeing_fwhm_low: float,
    seeing_fwhm_high: float,
    seeing_source: str,
    seeing_location_name: str | None = None,
    guide_scope_id: int | None = None,
    oag_id: int | None = None,
    guide_pixel_size_um: float | None = None,
    guide_focal_length_mm: float | None = None,
    guide_resolution_x: int | None = None,
    guide_resolution_y: int | None = None,
    guide_binning: int = DEFAULT_GUIDE_BINNING,
    centroid_accuracy_pixels: float = DEFAULT_CENTROID_ACCURACY_PIXELS,
    image_binning: int = DEFAULT_IMAGE_BINNING,
) -> dict:
    """Assemble all optical calculator results into a single dict.

    Returns a dict matching the RigCalculators Pydantic schema shape.
    """
    image_scale = compute_image_scale(pixel_size_um, focal_length_mm)
    binned_scales = compute_image_scale_binned(image_scale)

    fov_w, fov_h = compute_fov(
        focal_length_mm,
        sensor_width_mm,
        sensor_height_mm,
        resolution_x,
        resolution_y,
        pixel_size_um,
    )

    dawes, rayleigh, max_mag = compute_resolution_limits(aperture_mm)

    sensor_diag = compute_sensor_diagonal(
        sensor_width_mm,
        sensor_height_mm,
        resolution_x,
        resolution_y,
        pixel_size_um,
    )

    sensor_cov = None
    if sensor_diag is not None and image_circle_mm is not None:
        sensor_cov = compute_sensor_coverage(sensor_diag, image_circle_mm)

    sampling = assess_sampling(
        image_scale,
        seeing_fwhm_low,
        seeing_fwhm_high,
        seeing_source,
        seeing_location_name,
    )

    guide = compute_guide_suitability(
        guide_scope_id=guide_scope_id,
        oag_id=oag_id,
        guide_scope_focal_length_mm=guide_focal_length_mm,
        telescope_effective_focal_length_mm=focal_length_mm,
        guide_pixel_size_um=guide_pixel_size_um,
        guide_resolution_x=guide_resolution_x,
        guide_resolution_y=guide_resolution_y,
        main_pixel_size_um=pixel_size_um,
        main_focal_length_mm=focal_length_mm,
        guide_binning=guide_binning,
        centroid_accuracy_pixels=centroid_accuracy_pixels,
    )

    # Guiding tolerance is always computable (we always have an imaging camera).
    tolerance = compute_guiding_tolerance(
        unbinned_main_scale_arcsec_per_pixel=image_scale,
        image_binning=image_binning,
        guide_suitability=guide,
    )
    tolerance_dict = asdict(tolerance)
    guide_dict = asdict(guide) if guide is not None else None

    return {
        "image_scale_arcsec_per_pixel": image_scale,
        "image_scale_binned": binned_scales,
        "field_of_view_deg": (fov_w, fov_h),
        "focal_ratio": focal_ratio,
        "dawes_limit_arcsec": dawes,
        "rayleigh_limit_arcsec": rayleigh,
        "max_useful_magnification": max_mag,
        "sensor_diagonal_mm": sensor_diag,
        "sensor_coverage_pct": sensor_cov,
        "sampling_assessment": asdict(sampling),
        "guide_suitability": guide_dict,
        "guiding_tolerance": tolerance_dict,
    }
