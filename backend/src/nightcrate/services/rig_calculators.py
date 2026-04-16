"""Rig optical calculator formulas.

Pure math module with no DB or API dependencies.  Computes image scale,
field of view, resolution limits, sensor coverage, sampling assessment,
and guide system metrics for rig configurations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Unicode constants used in recommendation text.
_ARCSEC = "\u2033"  # double prime (arcsecond)
_ENDASH = "\u2013"  # en dash
_TIMES = "\u00d7"  # multiplication sign
_EMDASH = "\u2014"  # em dash
_RSQUOTE = "\u2019"  # right single quotation mark

# Conversion factor: radians to arcseconds.
_RAD_TO_ARCSEC = 206.265  # (180/pi) * 3600

# Default seeing range when no location or override is provided.
_DEFAULT_SEEING_LOW = 2.0
_DEFAULT_SEEING_HIGH = 4.0


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

    Returns (low, high, source, location_name_or_none).
    """
    if override_low is not None and override_high is not None:
        return override_low, override_high, "override", None

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
# Guide System
# ---------------------------------------------------------------------------


def compute_guide_metrics(
    guide_pixel_size_um: float,
    guide_focal_length_mm: float | None,
    guide_resolution_x: int,
    guide_resolution_y: int,
) -> tuple[float, tuple[float, float]] | None:
    """Compute guide camera image scale and FOV.

    Returns (scale_arcsec_per_pixel, (fov_width_arcmin, fov_height_arcmin))
    or None if guide focal length is not available.
    """
    if guide_focal_length_mm is None:
        return None

    scale = compute_image_scale(guide_pixel_size_um, guide_focal_length_mm)

    # FOV in arcminutes: (pixels * scale_arcsec) / 60
    fov_w = (guide_resolution_x * scale) / 60.0
    fov_h = (guide_resolution_y * scale) / 60.0

    return scale, (fov_w, fov_h)


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
    guide_pixel_size_um: float | None = None,
    guide_focal_length_mm: float | None = None,
    guide_resolution_x: int | None = None,
    guide_resolution_y: int | None = None,
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

    # Guide system (optional).
    guide_scale = None
    guide_fov = None
    if (
        guide_pixel_size_um is not None
        and guide_resolution_x is not None
        and guide_resolution_y is not None
    ):
        guide_result = compute_guide_metrics(
            guide_pixel_size_um,
            guide_focal_length_mm,
            guide_resolution_x,
            guide_resolution_y,
        )
        if guide_result is not None:
            guide_scale, guide_fov = guide_result

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
        "sampling_assessment": {
            "image_scale": sampling.image_scale,
            "ideal_range_low": sampling.ideal_range_low,
            "ideal_range_high": sampling.ideal_range_high,
            "seeing_fwhm_low": sampling.seeing_fwhm_low,
            "seeing_fwhm_high": sampling.seeing_fwhm_high,
            "seeing_source": sampling.seeing_source,
            "seeing_location_name": sampling.seeing_location_name,
            "assessment": sampling.assessment,
            "recommendation": sampling.recommendation,
            "binning_recommendations": sampling.binning_recommendations,
        },
        "guide_image_scale_arcsec_per_pixel": guide_scale,
        "guide_field_of_view_arcmin": guide_fov,
    }
