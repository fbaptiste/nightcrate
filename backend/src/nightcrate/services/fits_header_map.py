"""
NightCrate — FITS Header Keyword Alias Map

Maps variant FITS header keywords from capture software (N.I.N.A., ASIAIR,
SGPro, MaxIm DL, SharpCap) and processing software (PixInsight) to
NightCrate's canonical internal field names.

Each keyword includes a short description for display in NightCrate's
FITS header grid UI.

Sources:
  - FITS Standard 4.0 (IAU FITS Working Group)
  - SBIG FITS Extension (SBFITSEXT 1.0)
  - N.I.N.A. FITS header docs (nighttime-imaging.eu)
  - SGPro FITS header docs
  - MaxIm DL FITS header docs
  - ASIAIR community reports (ZWO forums, Cloudy Nights)
  - PixInsight BPP / SubframeSelector / ImageCalibration keywords
  - Siril keyword handling docs
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# FITS keyword → (canonical_field, short_description)
#
# short_description: for display in the NightCrate header grid UI.
# Keep under ~30 chars so they don't blow out table columns.
#
# When multiple keywords map to the same canonical field, priority is
# determined by KEYWORD_PRIORITY further below.
# ---------------------------------------------------------------------------

FITS_KEYWORD_MAP: dict[str, tuple[str, str]] = {
    # ── Image structure ──────────────────────────────────────────────────
    "BITPIX": ("bit_depth", "Bits per pixel"),
    "NAXIS1": ("image_width", "Image width (px)"),
    "NAXIS2": ("image_height", "Image height (px)"),
    # ── Exposure ─────────────────────────────────────────────────────────
    "EXPTIME": ("exposure_time", "Exposure time (sec)"),
    "EXPOSURE": ("exposure_time", "Exposure time (sec)"),
    "DARKTIME": ("exposure_time", "Dark current time (sec)"),
    # ── Frame type ───────────────────────────────────────────────────────
    "IMAGETYP": ("frame_type", "Frame type"),
    # ── Timestamps ───────────────────────────────────────────────────────
    "DATE-OBS": ("date_obs", "Date/time of obs (UTC)"),
    "DATE-UTC": ("date_obs", "Date/time of obs (UTC)"),
    "DATE-LOC": ("date_obs_local", "Date/time of obs (local)"),
    # ── Target / object ──────────────────────────────────────────────────
    "OBJECT": ("object_name", "Target name"),
    # ── Coordinates ──────────────────────────────────────────────────────
    "RA": ("ra", "Pointing RA (deg)"),
    "DEC": ("dec", "Pointing Dec (deg)"),
    "OBJCTRA": ("object_ra", "Target RA (HMS)"),
    "OBJCTDEC": ("object_dec", "Target Dec (DMS)"),
    "CRVAL1": ("ra", "WCS ref RA (deg)"),
    "CRVAL2": ("dec", "WCS ref Dec (deg)"),
    "AIRMASS": ("airmass", "Atmospheric airmass"),
    "SECZ": ("airmass", "Sec(z) airmass"),
    # ── Camera / instrument ──────────────────────────────────────────────
    "INSTRUME": ("camera_name", "Camera / instrument"),
    "GAIN": ("gain", "Camera gain"),
    "GAINRAW": ("gain", "Camera gain (ZWO raw)"),
    "OFFSET": ("offset", "Camera offset"),
    "EGAIN": ("egain", "e- per ADU"),
    "GAINADU": ("egain", "e- per ADU"),
    # ── Sensor temperature ───────────────────────────────────────────────
    "CCD-TEMP": ("sensor_temp", "Sensor temp (C)"),
    "CCDTEMP": ("sensor_temp", "Sensor temp (C)"),
    "TEMPERAT": ("sensor_temp", "Sensor temp (C)"),
    "SET-TEMP": ("sensor_temp_target", "Cooling setpoint (C)"),
    # ── Pixel geometry ───────────────────────────────────────────────────
    "XPIXSZ": ("pixel_size_x", "Pixel size X (um)"),
    "YPIXSZ": ("pixel_size_y", "Pixel size Y (um)"),
    "PIXSIZE1": ("pixel_size_x", "Pixel size X (um)"),
    "PIXSIZE2": ("pixel_size_y", "Pixel size Y (um)"),
    # ── Binning ──────────────────────────────────────────────────────────
    "XBINNING": ("binning_x", "X binning"),
    "YBINNING": ("binning_y", "Y binning"),
    "CCDXBIN": ("binning_x", "X binning"),
    "CCDYBIN": ("binning_y", "Y binning"),
    "CCDBINX": ("binning_x", "X binning"),
    "BINNING": ("binning_x", "Binning (square)"),
    # ── Readout / Bayer / ISO ────────────────────────────────────────────
    "READOUTM": ("readout_mode", "Readout mode"),
    "BAYERPAT": ("bayer_pattern", "Bayer pattern"),
    "COLORTYP": ("bayer_pattern", "Color sensor type"),
    "ISOSPEED": ("iso", "ISO speed"),
    "ISO": ("iso", "ISO speed"),
    # ── Optics ───────────────────────────────────────────────────────────
    "TELESCOP": ("telescope_name", "Telescope / OTA"),
    "FOCALLEN": ("focal_length", "Focal length (mm)"),
    "FOCRATIO": ("focal_ratio", "Focal ratio (f/N)"),
    "APTDIA": ("aperture_diameter", "Aperture diameter (mm)"),
    # ── Filter ───────────────────────────────────────────────────────────
    "FILTER": ("filter_name", "Filter name"),
    "INSFLNAM": ("filter_name", "Filter name"),
    "FWHEEL": ("filter_wheel_name", "Filter wheel"),
    # ── Focuser ──────────────────────────────────────────────────────────
    "FOCNAME": ("focuser_name", "Focuser model"),
    "FOCUSER": ("focuser_name", "Focuser model"),
    "FOCPOS": ("focuser_position", "Focus position (steps)"),
    "FOCUSPOS": ("focuser_position", "Focus position (steps)"),
    "FOCUSSZ": ("focuser_step_size", "Focus step size (um)"),
    "FOCTEMP": ("focuser_temp", "Focuser temp (C)"),
    "FOCUSTEM": ("focuser_temp", "Focuser temp (C)"),
    # ── Rotator ──────────────────────────────────────────────────────────
    "ROTNAME": ("rotator_name", "Rotator model"),
    "ROTATOR": ("rotator_angle", "Rotator angle (deg)"),
    "ROTATANG": ("rotator_angle", "Rotator angle (deg)"),
    "ROTSTPSZ": ("rotator_step_size", "Rotator step size"),
    # ── Observer site ────────────────────────────────────────────────────
    "SITELAT": ("site_latitude", "Site latitude (deg)"),
    "SITELONG": ("site_longitude", "Site longitude (deg)"),
    "SITEELEV": ("site_elevation", "Site elevation (m)"),
    "LATITUDE": ("site_latitude", "Site latitude (deg)"),
    "LONGITUD": ("site_longitude", "Site longitude (deg)"),
    "ALTITUDE": ("site_elevation", "Site elevation (m)"),
    "OBSGEO-B": ("site_latitude", "WCS site latitude"),
    "OBSGEO-L": ("site_longitude", "WCS site longitude"),
    "OBSGEO-H": ("site_elevation", "WCS site elevation"),
    # ── Software provenance ──────────────────────────────────────────────
    "SWCREATE": ("software_creator", "Created by (software)"),
    "CREATOR": ("software_creator", "Created by (software)"),
    "SWCREATOR": ("software_creator", "Created by (software)"),
    "PROGRAM": ("software_creator", "Created by (software)"),
    "SWMODIFY": ("software_modifier", "Modified by (software)"),
    "ROWORDER": ("row_order", "Pixel row order"),
    # ── Weather (N.I.N.A. weather data source) ───────────────────────────
    "AMBTEMP": ("ambient_temp", "Ambient temp (C)"),
    "HUMIDITY": ("humidity", "Humidity (%)"),
    "PRESSURE": ("pressure", "Air pressure (hPa)"),
    "DEWPOINT": ("dew_point", "Dew point (C)"),
    "MPSAS": ("sky_quality", "Sky quality (mag/as2)"),
    "SKYBRGHT": ("sky_brightness", "Sky brightness (lux)"),
    "SKYTEMP": ("sky_temp", "Sky temp (C)"),
    "CLOUDCVR": ("cloud_cover", "Cloud cover (%)"),
    "WINDSPD": ("wind_speed", "Wind speed (kph)"),
    "WINDGUST": ("wind_gust", "Wind gust (kph)"),
    "WINDDIR": ("wind_direction", "Wind dir (0=N, 90=E)"),
    "STARFWHM": ("star_fwhm_wx", "Star FWHM (weather)"),
    # ── PixInsight: SubframeSelector quality metrics ─────────────────────
    # Written to FITS headers by SubframeSelector (output subframes mode)
    # or WBPP, then read by ImageIntegration for weighting.
    "SSWEIGHT": ("pi_ssweight", "PI: SubframeSel weight"),
    "PSFFLUX": ("pi_psf_flux", "PI: PSF total flux"),
    "PSFFLUXPOW": ("pi_psf_flux_power", "PI: PSF flux power"),
    "PSFSIGNAL": ("pi_psf_signal", "PI: PSF signal est."),
    "PSFSNR": ("pi_psf_snr", "PI: PSF signal/noise"),
    "PSFSIGNALWT": ("pi_psf_signal_wt", "PI: PSF signal weight"),
    "PSFFWHM": ("pi_psf_fwhm", "PI: PSF FWHM (arcsec)"),
    "PSFECCENTR": ("pi_psf_eccen", "PI: PSF eccentricity"),
    "PSFSTARS": ("pi_psf_stars", "PI: PSF stars detected"),
    "PSFRESID": ("pi_psf_residual", "PI: PSF fitting residual"),
    # ── PixInsight: ImageCalibration / WBPP noise estimates ──────────────
    # Written by ImageCalibration after calibrating subs.
    "NOISE00": ("pi_noise_layer0", "PI: Noise layer 0"),
    "NOISE01": ("pi_noise_layer1", "PI: Noise layer 1"),
    "NOISE02": ("pi_noise_layer2", "PI: Noise layer 2"),
    "NOISELBL0": ("pi_noise_alg0", "PI: Noise method 0"),
    "NOISELBL1": ("pi_noise_alg1", "PI: Noise method 1"),
    "NOISELBL2": ("pi_noise_alg2", "PI: Noise method 2"),
    "PCLSCEST": ("pi_pcl_scale_est", "PI: Scale estimate"),
    "PCLLOCEST": ("pi_pcl_loc_est", "PI: Location estimate"),
    # ── PixInsight: ImageIntegration ─────────────────────────────────────
    # Written to stacked master frames.
    "NCOMBINE": ("pi_ncombine", "PI: Frames combined"),
}


# ---------------------------------------------------------------------------
# Flat alias dict (keyword → canonical field name only). For quick lookups.
# ---------------------------------------------------------------------------

FITS_KEYWORD_ALIASES: dict[str, str] = {k: v[0] for k, v in FITS_KEYWORD_MAP.items()}


# ---------------------------------------------------------------------------
# Priority when multiple keywords map to the same canonical field
# ---------------------------------------------------------------------------

KEYWORD_PRIORITY: dict[str, list[str]] = {
    "exposure_time": ["EXPTIME", "EXPOSURE", "DARKTIME"],
    "date_obs": ["DATE-OBS", "DATE-UTC"],
    "ra": ["RA", "CRVAL1"],
    "dec": ["DEC", "CRVAL2"],
    "gain": ["GAIN", "GAINRAW"],
    "egain": ["EGAIN", "GAINADU"],
    "sensor_temp": ["CCD-TEMP", "CCDTEMP", "TEMPERAT"],
    "pixel_size_x": ["XPIXSZ", "PIXSIZE1"],
    "pixel_size_y": ["YPIXSZ", "PIXSIZE2"],
    "binning_x": ["XBINNING", "CCDXBIN", "CCDBINX", "BINNING"],
    "binning_y": ["YBINNING", "CCDYBIN"],
    "filter_name": ["FILTER", "INSFLNAM"],
    "focuser_name": ["FOCNAME", "FOCUSER"],
    "focuser_position": ["FOCPOS", "FOCUSPOS"],
    "focuser_temp": ["FOCTEMP", "FOCUSTEM"],
    "rotator_angle": ["ROTATOR", "ROTATANG"],
    "site_latitude": ["SITELAT", "LATITUDE", "OBSGEO-B"],
    "site_longitude": ["SITELONG", "LONGITUD", "OBSGEO-L"],
    "site_elevation": ["SITEELEV", "ALTITUDE", "OBSGEO-H"],
    "software_creator": ["SWCREATE", "CREATOR", "SWCREATOR", "PROGRAM"],
    "camera_name": ["INSTRUME"],
    "iso": ["ISO", "ISOSPEED"],
    "airmass": ["AIRMASS", "SECZ"],
}


# ---------------------------------------------------------------------------
# IMAGETYP normalization → "light", "dark", "flat", "bias"
# ---------------------------------------------------------------------------

FRAME_TYPE_ALIASES: dict[str, str] = {
    # IRAF short form (N.I.N.A., SGPro, ASIAIR)
    "LIGHT": "light",
    "DARK": "dark",
    "FLAT": "flat",
    "BIAS": "bias",
    # SBFITSEXT 1.0 / MaxIm DL long form
    "LIGHT FRAME": "light",
    "DARK FRAME": "dark",
    "FLAT FIELD": "flat",
    "BIAS FRAME": "bias",
    # Underscore variants
    "LIGHT_FRAME": "light",
    "DARK_FRAME": "dark",
    "FLAT_FRAME": "flat",
    "BIAS_FRAME": "bias",
    # Other conventions
    "OBJECT": "light",
    "SCIENCE": "light",
    "ZERO": "bias",
    "SKYFLAT": "flat",
    "DOMEFLAT": "flat",
    "TWIFLAT": "flat",
}


# ---------------------------------------------------------------------------
# Filter name normalization
# ---------------------------------------------------------------------------

FILTER_NAME_ALIASES: dict[str, str] = {
    "LUMINANCE": "Lum",
    "LUM": "Lum",
    "L": "Lum",
    "CLEAR": "Lum",
    "RED": "Red",
    "R": "Red",
    "GREEN": "Green",
    "G": "Green",
    "BLUE": "Blue",
    "B": "Blue",
    "HA": "Ha",
    "H-ALPHA": "Ha",
    "HALPHA": "Ha",
    "H_ALPHA": "Ha",
    "HYDROGEN ALPHA": "Ha",
    "HYDROGEN-ALPHA": "Ha",
    "OIII": "Oiii",
    "O-III": "Oiii",
    "O3": "Oiii",
    "OXYGEN III": "Oiii",
    "OXYGEN-III": "Oiii",
    "SII": "Sii",
    "S-II": "Sii",
    "S2": "Sii",
    "SULFUR II": "Sii",
    "SULFUR-II": "Sii",
    "SULPHUR II": "Sii",
    "SULPHUR-II": "Sii",
}


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


def resolve_header(keyword: str) -> str | None:
    """Given a raw FITS keyword, return the canonical field name or None."""
    return FITS_KEYWORD_ALIASES.get(keyword.upper())


def get_keyword_description(keyword: str) -> str | None:
    """Return the short UI description for a FITS keyword, or None."""
    entry = FITS_KEYWORD_MAP.get(keyword.upper())
    return entry[1] if entry else None


def get_all_descriptions() -> dict[str, str]:
    """Return dict of every FITS keyword → its short description."""
    return {k: v[1] for k, v in FITS_KEYWORD_MAP.items()}


def normalize_frame_type(raw_value: str) -> str | None:
    """Normalize IMAGETYP to light/dark/flat/bias. None if unrecognized."""
    return FRAME_TYPE_ALIASES.get(raw_value.strip().upper())


def normalize_filter_name(raw_value: str) -> str:
    """Normalize filter name to canonical short form. Passthrough if unknown."""
    cleaned = raw_value.strip().upper()
    return FILTER_NAME_ALIASES.get(cleaned, raw_value.strip())


def extract_metadata(header: dict[str, Any]) -> dict[str, Any]:
    """
    Extract recognized metadata from a FITS header dict.
    Returns canonical_field → value, with priority + normalization applied.
    """
    candidates: dict[str, list[tuple[int, Any]]] = {}

    for keyword, value in header.items():
        ku = keyword.upper()
        canonical = FITS_KEYWORD_ALIASES.get(ku)
        if canonical is None:
            continue
        plist = KEYWORD_PRIORITY.get(canonical, [])
        try:
            pri = plist.index(ku)
        except ValueError:
            pri = 999
        candidates.setdefault(canonical, []).append((pri, value))

    result: dict[str, Any] = {}
    for canonical, entries in candidates.items():
        entries.sort(key=lambda x: x[0])
        val = entries[0][1]
        if val is None:
            continue
        if isinstance(val, str) and val.strip() == "":
            continue
        result[canonical] = val

    if "frame_type" in result:
        n = normalize_frame_type(str(result["frame_type"]))
        if n:
            result["frame_type"] = n

    if "filter_name" in result:
        result["filter_name"] = normalize_filter_name(str(result["filter_name"]))

    return result


def get_calibration_keys() -> list[str]:
    """Canonical fields used for calibration frame matching."""
    return [
        "camera_name",
        "gain",
        "sensor_temp",
        "exposure_time",
        "binning_x",
        "binning_y",
        "filter_name",
        "frame_type",
    ]
