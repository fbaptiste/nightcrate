"""Unit tests for PHD2 metrics computation.

Hand-computed values — these are pinned regression tests. When a future
version changes the metric definitions (e.g. Pass B adds drift + oscillation)
the expected values here should be updated deliberately, not silently.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from nightcrate.services.phd2_metrics import compute_section_metrics
from nightcrate.services.phd2_models import (
    GuidingSample,
    LogSection,
    SectionHeader,
)


def _make_guiding_section(
    samples: list[GuidingSample],
    *,
    pixel_scale: float | None = 2.0,
) -> LogSection:
    return LogSection(
        kind="guiding",
        index=0,
        start_time=datetime(2026, 1, 1, 0, 0, 0),
        header=SectionHeader(pixel_scale_arcsec_per_px=pixel_scale),
        samples=samples,
    )


def _sample(
    frame: int,
    time_s: float,
    ra: float | None,
    dec: float | None,
    *,
    kind: str = "Mount",
    snr: float | None = 20.0,
    mass: float | None = 1000.0,
    err: int = 0,
) -> GuidingSample:
    return GuidingSample(
        frame=frame,
        time_seconds=time_s,
        mount_kind=kind,  # type: ignore[arg-type]
        ra_raw_px=ra,
        dec_raw_px=dec,
        snr=snr,
        star_mass=mass,
        error_code=err,
    )


class TestRmsComputation:
    def test_pinned_rms_on_hand_computed_values(self):
        """RMS = sqrt(mean(x²)). Values: 1, -2, 3 → sqrt((1+4+9)/3) = sqrt(14/3)."""
        samples = [
            _sample(1, 1.0, 1.0, 0.0),
            _sample(2, 2.0, -2.0, 0.0),
            _sample(3, 3.0, 3.0, 0.0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.rms_ra_px == pytest.approx((14 / 3) ** 0.5)
        assert metrics.rms_dec_px == pytest.approx(0.0)
        assert metrics.rms_total_px == pytest.approx(metrics.rms_ra_px)

    def test_rms_total_combines_ra_and_dec(self):
        """RMS_total = sqrt(RMS_RA² + RMS_Dec²). RA=3, Dec=4 → 5."""
        samples = [
            _sample(1, 1.0, 3.0, 4.0),
            _sample(2, 2.0, -3.0, -4.0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.rms_ra_px == pytest.approx(3.0)
        assert metrics.rms_dec_px == pytest.approx(4.0)
        assert metrics.rms_total_px == pytest.approx(5.0)

    def test_drop_frames_excluded_from_rms(self):
        """DROP frames have None ra_raw/dec_raw — must not count toward RMS."""
        samples = [
            _sample(1, 1.0, 1.0, 1.0),
            _sample(2, 2.0, None, None, kind="DROP", err=6),
            _sample(3, 3.0, 1.0, 1.0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        # Only 2 real samples contribute, both with value 1 — RMS = 1.
        assert metrics.rms_ra_px == pytest.approx(1.0)
        assert metrics.rms_dec_px == pytest.approx(1.0)
        # But total frame count reflects all 3 samples.
        assert metrics.frame_count_total == 3
        assert metrics.frame_count_error == 1


class TestPeakComputation:
    def test_peak_takes_absolute_value(self):
        samples = [
            _sample(1, 1.0, 0.5, 0.0),
            _sample(2, 2.0, -2.5, 0.0),
            _sample(3, 3.0, 1.0, 0.0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.peak_ra_px == pytest.approx(2.5)


class TestDurationAndCounts:
    def test_duration_from_sample_times(self):
        samples = [
            _sample(1, 1.0, 0.0, 0.0),
            _sample(2, 100.5, 0.0, 0.0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.duration_seconds == pytest.approx(99.5)

    def test_error_count_matches_rows_with_nonzero_error_code(self):
        samples = [
            _sample(1, 1.0, 0.0, 0.0, err=0),
            _sample(2, 2.0, 0.0, 0.0, err=0),
            _sample(3, 3.0, None, None, kind="DROP", err=6),
            _sample(4, 4.0, None, None, kind="DROP", err=7),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.frame_count_total == 4
        assert metrics.frame_count_error == 2


class TestSnrAggregation:
    def test_mean_and_median_snr(self):
        samples = [
            _sample(1, 1.0, 0.0, 0.0, snr=10.0),
            _sample(2, 2.0, 0.0, 0.0, snr=20.0),
            _sample(3, 3.0, 0.0, 0.0, snr=30.0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.mean_snr == pytest.approx(20.0)
        assert metrics.median_snr == pytest.approx(20.0)

    def test_missing_snr_samples_are_skipped_not_zeroed(self):
        """Missing SNR values resolve to None — they must not bias the mean toward zero."""
        samples = [
            _sample(1, 1.0, 0.0, 0.0, snr=20.0),
            _sample(2, 2.0, 0.0, 0.0, snr=None),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.mean_snr == pytest.approx(20.0)


class TestArcsecScale:
    def test_arcsec_scale_surfaces_from_header(self):
        samples = [_sample(1, 1.0, 0.0, 0.0)]
        metrics = compute_section_metrics(_make_guiding_section(samples, pixel_scale=3.96))
        assert metrics.arcsec_scale == 3.96

    def test_arcsec_scale_none_when_header_missing_pixel_scale(self):
        samples = [_sample(1, 1.0, 0.0, 0.0)]
        metrics = compute_section_metrics(_make_guiding_section(samples, pixel_scale=None))
        assert metrics.arcsec_scale is None


class TestCalibrationSection:
    def test_calibration_section_returns_mostly_none(self):
        """Calibration sections have no RMS / peak — everything is None."""
        cal = LogSection(
            kind="calibration",
            index=0,
            start_time=datetime(2026, 1, 1),
            header=SectionHeader(pixel_scale_arcsec_per_px=2.0),
        )
        metrics = compute_section_metrics(cal)
        assert metrics.rms_ra_px is None
        assert metrics.rms_dec_px is None
        assert metrics.rms_total_px is None
        assert metrics.peak_ra_px is None
        assert metrics.peak_dec_px is None
        assert metrics.frame_count_total == 0
        assert metrics.duration_seconds == 0.0
        # arcsec_scale still propagates from the header.
        assert metrics.arcsec_scale == 2.0


class TestEmptySection:
    def test_empty_guiding_section_returns_no_metrics(self):
        section = _make_guiding_section([])
        metrics = compute_section_metrics(section)
        assert metrics.rms_ra_px is None
        assert metrics.frame_count_total == 0
        assert metrics.duration_seconds == 0.0
