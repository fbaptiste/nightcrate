"""PHD2 guide-log metrics — v0.22.0 scope.

Pure functions over the parsed data model. v0.22.0 computes only the
top-line summary metrics (RMS, peak, frame count, duration, SNR, star mass).
Drift, oscillation, and settle-aware filtering arrive in v0.23.0 (Pass B).

All distances are in guide-camera pixels. `arcsec_scale` is surfaced so the
display layer can render dual-unit labels without re-reading the section
header.
"""

from __future__ import annotations

import math
from statistics import median

from pydantic import BaseModel, ConfigDict

from nightcrate.services.phd2_models import LogSection


class SectionMetrics(BaseModel):
    """Top-line per-section metrics — attached to each guiding section in the API response."""

    model_config = ConfigDict(extra="forbid")

    rms_ra_px: float | None
    rms_dec_px: float | None
    rms_total_px: float | None
    peak_ra_px: float | None
    peak_dec_px: float | None
    frame_count_total: int
    frame_count_error: int
    duration_seconds: float
    mean_snr: float | None
    median_snr: float | None
    mean_star_mass: float | None
    # arcsec conversion factor from the section header, surfaced so the UI
    # can render "0.42 px / 1.66″" without re-reading the header. `None` when
    # `Pixel scale` was absent.
    arcsec_scale: float | None


def compute_section_metrics(section: LogSection) -> SectionMetrics:
    """Compute summary metrics for one guiding section.

    Calibration sections also route through this (returning mostly `None` +
    zero counts) so the API response shape stays uniform across kinds.
    """
    if section.kind == "calibration" or not section.samples:
        return SectionMetrics(
            rms_ra_px=None,
            rms_dec_px=None,
            rms_total_px=None,
            peak_ra_px=None,
            peak_dec_px=None,
            frame_count_total=len(section.samples),
            frame_count_error=sum(1 for s in section.samples if s.error_code != 0),
            duration_seconds=_duration_seconds(section),
            mean_snr=None,
            median_snr=None,
            mean_star_mass=None,
            arcsec_scale=section.header.pixel_scale_arcsec_per_px,
        )

    ra_raw = [s.ra_raw_px for s in section.samples if s.ra_raw_px is not None]
    dec_raw = [s.dec_raw_px for s in section.samples if s.dec_raw_px is not None]
    snrs = [s.snr for s in section.samples if s.snr is not None]
    masses = [s.star_mass for s in section.samples if s.star_mass is not None]

    rms_ra = _rms(ra_raw)
    rms_dec = _rms(dec_raw)
    rms_total = (
        math.sqrt(rms_ra**2 + rms_dec**2) if rms_ra is not None and rms_dec is not None else None
    )
    peak_ra = max((abs(v) for v in ra_raw), default=None)
    peak_dec = max((abs(v) for v in dec_raw), default=None)

    return SectionMetrics(
        rms_ra_px=rms_ra,
        rms_dec_px=rms_dec,
        rms_total_px=rms_total,
        peak_ra_px=peak_ra,
        peak_dec_px=peak_dec,
        frame_count_total=len(section.samples),
        frame_count_error=sum(1 for s in section.samples if s.error_code != 0),
        duration_seconds=_duration_seconds(section),
        mean_snr=sum(snrs) / len(snrs) if snrs else None,
        median_snr=median(snrs) if snrs else None,
        mean_star_mass=sum(masses) / len(masses) if masses else None,
        arcsec_scale=section.header.pixel_scale_arcsec_per_px,
    )


def _rms(values: list[float]) -> float | None:
    if not values:
        return None
    return math.sqrt(sum(v * v for v in values) / len(values))


def _duration_seconds(section: LogSection) -> float:
    """Wall-clock duration from first to last sample's ``Time`` column.

    Uses per-frame elapsed seconds rather than section end - section start —
    section end may be ``None`` (EOF-terminated sections), and the sample
    series gives exact duration anyway.
    """
    if not section.samples:
        return 0.0
    return section.samples[-1].time_seconds - section.samples[0].time_seconds
