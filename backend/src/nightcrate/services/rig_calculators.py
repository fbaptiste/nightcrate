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

# Sub-exposure (Robin Glover formula) constants.
#
# V-band zero-point photon flux: V=0 delivers ~1e4 photons/s/cm²/nm
# (from the Johnson V zero-point of 3636 Jy at 550 nm).
V_ZERO_MAG_PHOTON_FLUX = 1.0e4

DEFAULT_K_FACTOR = 10.0
MIN_K_FACTOR = 3.0
MAX_K_FACTOR = 20.0

# Bortle class → V-band zenith sky brightness (mag/arcsec²).
# Standard mapping used by the SQM community; values are approximate.
BORTLE_TO_SKY_MAG: dict[int, float] = {
    1: 21.99,
    2: 21.89,
    3: 21.58,
    4: 20.93,
    5: 20.27,
    6: 19.50,
    7: 18.95,
    8: 18.38,
    9: 17.80,
}
_DEFAULT_SKY_MAG = BORTLE_TO_SKY_MAG[5]  # ~20.3 (moderate suburban)

# Fallback bandpass (nm) by filter-type name when filter_passband is missing.
FILTER_TYPE_DEFAULT_BANDPASS: dict[str, float] = {
    "broadband_luminance": 300.0,
    "luminance": 300.0,  # alias used by some seed data
    "broadband_color": 100.0,
    "narrowband_single": 7.0,
    "narrowband_dual": 14.0,
    "narrowband_tri": 21.0,
    "uv_ir_cut": 300.0,
    "light_pollution": 200.0,
    "neutral_density": 300.0,
    "other": 100.0,
}

# Fallback peak transmission (fraction 0-1) by filter-type name.
FILTER_TYPE_DEFAULT_TRANSMISSION: dict[str, float] = {
    "broadband_luminance": 0.95,
    "luminance": 0.95,
    "broadband_color": 0.95,
    "narrowband_single": 0.85,
    "narrowband_dual": 0.85,
    "narrowband_tri": 0.85,
    "uv_ir_cut": 0.95,
    "light_pollution": 0.80,
    "neutral_density": 0.50,
    "other": 0.85,
}

# Unfiltered fallback (wide-open, near full optical bandpass).
UNFILTERED_BANDPASS_NM = 300.0
UNFILTERED_TRANSMISSION = 0.95

# Sub-exposures rounded to the nearest of these standard lengths.
STANDARD_SUB_LENGTHS_SEC: tuple[int, ...] = (
    30,
    60,
    90,
    120,
    180,
    240,
    300,
    480,
    600,
    900,
    1200,
    1800,
)

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
# Sub-Exposure (Robin Glover)
# ---------------------------------------------------------------------------


@dataclass
class FilterInput:
    """One filter's data needed for sub-exposure computation.

    `passbands` is a list of (bandwidth_nm, peak_transmission_pct_or_None).
    When empty, defaults per filter_type are used.
    """

    filter_id: int | None
    filter_name: str
    filter_type_name: str | None
    slot_number: int | None
    filter_peak_transmission_pct: float | None
    passbands: list[tuple[float, float | None]]
    has_passband_data: bool  # False → warning to surface ("passband defaults used")


@dataclass
class SubExposureResult:
    filter_id: int | None
    filter_label: str
    filter_slot_number: int | None
    effective_bandpass_nm: float
    filter_transmission_pct: float
    sky_rate_e_per_s_per_pixel: float
    optimal_sub_seconds: float
    saturation_sub_seconds: float
    recommended_sub_seconds: float
    saturation_capped: bool
    standard_sub_seconds: int  # rounded to nearest standard length
    has_passband_data: bool


@dataclass
class SubExposureCalc:
    location_id: int | None
    location_name: str | None
    sky_mag_per_arcsec2: float
    sky_brightness_source: str  # 'sqm' | 'bortle' | 'default'
    sky_brightness_source_detail: str
    read_noise_e: float
    peak_qe_pct: float
    full_well_capacity_ke: float
    aperture_mm: float
    image_scale_arcsec_per_pixel: float
    k_factor: float
    results: list[SubExposureResult]


def resolve_sky_brightness(
    location_sqm_reading: float | None,
    location_bortle_class: int | None,
    location_name: str | None,
) -> tuple[float, str, str | None, str]:
    """Resolve the sky brightness for sub-exposure math.

    Priority: SQM reading > Bortle class > default (Bortle 5 ~ 20.3).
    Returns (sky_mag_per_arcsec2, source, location_name, human_detail).
    """
    if location_sqm_reading is not None:
        return (
            location_sqm_reading,
            "sqm",
            location_name,
            f"SQM {location_sqm_reading:.2f} mag/arcsec\u00b2",
        )
    if location_bortle_class is not None and location_bortle_class in BORTLE_TO_SKY_MAG:
        mag = BORTLE_TO_SKY_MAG[location_bortle_class]
        return (
            mag,
            "bortle",
            location_name,
            f"Bortle {location_bortle_class} (~{mag:.2f} mag/arcsec\u00b2)",
        )
    return (
        _DEFAULT_SKY_MAG,
        "default",
        None,
        f"Default (Bortle 5 ~ {_DEFAULT_SKY_MAG:.2f} mag/arcsec\u00b2)",
    )


def get_filter_photometrics(filt: FilterInput) -> tuple[float, float, bool]:
    """Return (effective_bandpass_nm, transmission_fraction, used_defaults)."""
    if filt.filter_id is None:  # virtual "Unfiltered" entry
        return UNFILTERED_BANDPASS_NM, UNFILTERED_TRANSMISSION, False

    # Prefer per-passband data — summed bandwidths handle duo/tri-band filters.
    if filt.passbands:
        bandpass = sum(b for (b, _t) in filt.passbands)
        if filt.filter_peak_transmission_pct is not None:
            trans = filt.filter_peak_transmission_pct / 100.0
        else:
            trans_values = [t for (_b, t) in filt.passbands if t is not None]
            if trans_values:
                trans = (sum(trans_values) / len(trans_values)) / 100.0
            else:
                trans = FILTER_TYPE_DEFAULT_TRANSMISSION.get(
                    (filt.filter_type_name or "").lower(), 0.85
                )
        return bandpass, trans, False

    # Fall back to filter-type defaults.
    type_key = (filt.filter_type_name or "").lower()
    bandpass = FILTER_TYPE_DEFAULT_BANDPASS.get(type_key, 100.0)
    trans = (
        filt.filter_peak_transmission_pct / 100.0
        if filt.filter_peak_transmission_pct is not None
        else FILTER_TYPE_DEFAULT_TRANSMISSION.get(type_key, 0.85)
    )
    return bandpass, trans, True


def _round_to_standard_sub(seconds: float) -> int:
    """Pick the nearest standard sub-length; prefer shorter on ties."""
    best = STANDARD_SUB_LENGTHS_SEC[0]
    best_delta = abs(seconds - best)
    for candidate in STANDARD_SUB_LENGTHS_SEC[1:]:
        delta = abs(seconds - candidate)
        if delta < best_delta:
            best = candidate
            best_delta = delta
    # If seconds exceeds the max standard, clamp to the max.
    if seconds > STANDARD_SUB_LENGTHS_SEC[-1]:
        return STANDARD_SUB_LENGTHS_SEC[-1]
    return best


def compute_sub_exposure(
    sensor_read_noise_e: float | None,
    sensor_peak_qe_pct: float | None,
    sensor_full_well_ke: float | None,
    aperture_mm: float,
    image_scale_arcsec_per_pixel: float,
    filters: list[FilterInput],
    location_id: int | None = None,
    location_name: str | None = None,
    location_sqm_reading: float | None = None,
    location_bortle_class: int | None = None,
    k_factor: float = DEFAULT_K_FACTOR,
) -> SubExposureCalc | None:
    """Compute optimal sub-exposure lengths per filter (Robin Glover formula).

    Returns None if sensor photometrics are incomplete. Each FilterInput in
    `filters` produces one SubExposureResult; callers should include an
    "Unfiltered" virtual entry when neither a filter wheel nor a single filter
    is assigned.
    """
    if sensor_read_noise_e is None or sensor_peak_qe_pct is None or sensor_full_well_ke is None:
        return None

    sky_mag, sky_source, sky_loc_name, sky_detail = resolve_sky_brightness(
        location_sqm_reading, location_bortle_class, location_name
    )

    # Geometric/photometric primitives.
    qe = sensor_peak_qe_pct / 100.0
    sky_photon_flux_per_nm_per_arcsec2 = V_ZERO_MAG_PHOTON_FLUX * (10.0 ** (-0.4 * sky_mag))
    aperture_cm2 = math.pi * (aperture_mm / 20.0) ** 2  # pi * r_cm^2
    pixel_area_arcsec2 = image_scale_arcsec_per_pixel**2

    k_squared_rn_squared = (k_factor**2) * (sensor_read_noise_e**2)
    full_well_e = sensor_full_well_ke * 1000.0

    results: list[SubExposureResult] = []
    for f in filters:
        bandpass_nm, transmission, used_defaults = get_filter_photometrics(f)
        sky_rate = (
            sky_photon_flux_per_nm_per_arcsec2
            * aperture_cm2
            * pixel_area_arcsec2
            * bandpass_nm
            * transmission
            * qe
        )
        if sky_rate <= 0:
            continue

        optimal_sub = k_squared_rn_squared / sky_rate
        saturation_sub = full_well_e / sky_rate
        recommended = min(optimal_sub, 0.8 * saturation_sub)
        saturation_capped = optimal_sub > 0.8 * saturation_sub

        results.append(
            SubExposureResult(
                filter_id=f.filter_id,
                filter_label=f.filter_name,
                filter_slot_number=f.slot_number,
                effective_bandpass_nm=bandpass_nm,
                filter_transmission_pct=transmission * 100.0,
                sky_rate_e_per_s_per_pixel=sky_rate,
                optimal_sub_seconds=optimal_sub,
                saturation_sub_seconds=saturation_sub,
                recommended_sub_seconds=recommended,
                saturation_capped=saturation_capped,
                standard_sub_seconds=_round_to_standard_sub(recommended),
                has_passband_data=f.has_passband_data and not used_defaults,
            )
        )

    # Sort: slot numbers first (ascending), then non-slot filters by label.
    results.sort(key=lambda r: (r.filter_slot_number is None, r.filter_slot_number or 0))

    return SubExposureCalc(
        location_id=location_id,
        location_name=sky_loc_name,
        sky_mag_per_arcsec2=sky_mag,
        sky_brightness_source=sky_source,
        sky_brightness_source_detail=sky_detail,
        read_noise_e=sensor_read_noise_e,
        peak_qe_pct=sensor_peak_qe_pct,
        full_well_capacity_ke=sensor_full_well_ke,
        aperture_mm=aperture_mm,
        image_scale_arcsec_per_pixel=image_scale_arcsec_per_pixel,
        k_factor=k_factor,
        results=results,
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

    guide_dict = None
    if guide is not None:
        guide_dict = {
            "mode": guide.mode,
            "guide_focal_length_mm": guide.guide_focal_length_mm,
            "guide_pixel_size_um": guide.guide_pixel_size_um,
            "guide_binning": guide.guide_binning,
            "effective_guide_pixel_size_um": guide.effective_guide_pixel_size_um,
            "unbinned_guide_scale_arcsec_per_pixel": guide.unbinned_guide_scale_arcsec_per_pixel,
            "guide_scale_arcsec_per_pixel": guide.guide_scale_arcsec_per_pixel,
            "guide_fov_width_arcmin": guide.guide_fov_width_arcmin,
            "guide_fov_height_arcmin": guide.guide_fov_height_arcmin,
            "centroid_accuracy_pixels": guide.centroid_accuracy_pixels,
            "effective_guide_precision_arcsec": guide.effective_guide_precision_arcsec,
            "g_ratio": guide.g_ratio,
            "effective_error_main_pixels": guide.effective_error_main_pixels,
            "rating": guide.rating,
            "rating_reason": guide.rating_reason,
            "recommendation": guide.recommendation,
            "caveat": guide.caveat,
        }

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
        "guide_suitability": guide_dict,
    }
