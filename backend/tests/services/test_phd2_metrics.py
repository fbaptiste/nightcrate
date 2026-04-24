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
    LogEvent,
    LogSection,
    SectionHeader,
)


def _make_guiding_section(
    samples: list[GuidingSample],
    *,
    pixel_scale: float | None = 2.0,
    events: list[LogEvent] | None = None,
) -> LogSection:
    return LogSection(
        kind="guiding",
        index=0,
        start_time=datetime(2026, 1, 1, 0, 0, 0),
        header=SectionHeader(pixel_scale_arcsec_per_px=pixel_scale),
        samples=samples,
        events=events or [],
    )


def _settle_begin(time_s: float | None) -> LogEvent:
    return LogEvent(time_seconds=time_s, kind="settle_begin", raw_message="Settling started")


def _settle_end(time_s: float | None) -> LogEvent:
    return LogEvent(time_seconds=time_s, kind="settle_end", raw_message="Settling complete")


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
        assert metrics.frame_count_in_settle == 0
        assert metrics.frame_count_in_stats == 0
        assert metrics.duration_seconds == 0.0


class TestSettleExclusion:
    """Per PHD2 / PHDLogViewer convention, samples inside settle windows
    (bracketed by ``settle_begin`` / ``settle_end`` INFO events) must be
    excluded from every guide-quality metric — not just RMS.
    """

    def test_simple_pair_excludes_spike_from_rms_and_peak(self):
        """Two calm samples around a huge spike bracketed by a settle pair.

        Spike (RA=100 px at t=2.0) must NOT appear in RMS or peak.
        """
        samples = [
            _sample(1, 1.0, 1.0, 0.0),
            _sample(2, 2.0, 100.0, 0.0),  # inside settle window
            _sample(3, 3.0, -1.0, 0.0),
        ]
        events = [_settle_begin(1.5), _settle_end(2.5)]
        metrics = compute_section_metrics(_make_guiding_section(samples, events=events))
        # Only frames 1 and 3 contribute — RMS = sqrt((1² + 1²)/2) = 1.
        assert metrics.rms_ra_px == pytest.approx(1.0)
        assert metrics.peak_ra_px == pytest.approx(1.0)
        assert metrics.frame_count_total == 3
        assert metrics.frame_count_in_settle == 1
        assert metrics.frame_count_in_stats == 2

    def test_boundary_sample_is_treated_as_in_settle(self):
        """A sample with time_seconds exactly equal to an interval edge
        is a transition sample — excluded, to match PHDLogViewer."""
        samples = [
            _sample(1, 1.0, 2.0, 0.0),  # on settle_begin boundary → excluded
            _sample(2, 2.0, 5.0, 0.0),  # inside → excluded
            _sample(3, 3.0, 3.0, 0.0),  # on settle_end boundary → excluded
            _sample(4, 4.0, 4.0, 0.0),  # after settle → kept
        ]
        events = [_settle_begin(1.0), _settle_end(3.0)]
        metrics = compute_section_metrics(_make_guiding_section(samples, events=events))
        assert metrics.frame_count_in_settle == 3
        assert metrics.frame_count_in_stats == 1
        assert metrics.rms_ra_px == pytest.approx(4.0)

    def test_section_opens_mid_settle_from_lone_end(self):
        """A lone ``settle_end`` at t=2.0 with no preceding ``settle_begin``
        means the section opened inside an active settle — exclude everything
        up through t=2.0."""
        samples = [
            _sample(1, 1.0, 10.0, 0.0),  # before the end → excluded
            _sample(2, 2.0, 10.0, 0.0),  # on the end boundary → excluded
            _sample(3, 3.0, 1.0, 0.0),  # after → kept
            _sample(4, 4.0, -1.0, 0.0),  # after → kept
        ]
        events = [_settle_end(2.0)]
        metrics = compute_section_metrics(_make_guiding_section(samples, events=events))
        assert metrics.frame_count_in_settle == 2
        assert metrics.frame_count_in_stats == 2
        assert metrics.rms_ra_px == pytest.approx(1.0)

    def test_unclosed_begin_extends_to_last_sample(self):
        """A ``settle_begin`` without a matching ``settle_end`` means the
        section ended during settling — exclude from begin through the
        last sample's time."""
        samples = [
            _sample(1, 1.0, 1.0, 0.0),  # before begin → kept
            _sample(2, 2.0, 50.0, 0.0),  # on begin boundary → excluded
            _sample(3, 3.0, 75.0, 0.0),  # inside settle → excluded
        ]
        events = [_settle_begin(2.0)]
        metrics = compute_section_metrics(_make_guiding_section(samples, events=events))
        assert metrics.frame_count_in_settle == 2
        assert metrics.frame_count_in_stats == 1
        assert metrics.rms_ra_px == pytest.approx(1.0)

    def test_drop_inside_settle_counts_as_in_settle_not_double(self):
        """A DROP row inside a settle window must count in in_settle but
        NOT double-count against in_stats (in_stats already excludes via
        the null-positional filter)."""
        samples = [
            _sample(1, 1.0, 2.0, 2.0),  # kept
            _sample(2, 2.0, None, None, kind="DROP", err=6),  # in settle AND null → in_settle only
            _sample(3, 3.0, 3.0, 3.0),  # kept
        ]
        events = [_settle_begin(1.5), _settle_end(2.5)]
        metrics = compute_section_metrics(_make_guiding_section(samples, events=events))
        assert metrics.frame_count_total == 3
        assert metrics.frame_count_in_settle == 1
        # in_stats = samples that had positional data AND were outside
        # settle — the two non-DROP samples.
        assert metrics.frame_count_in_stats == 2

    def test_frame_count_error_excludes_settle_errors(self):
        """Error rows inside settle windows are transitional noise, not
        real guiding failures — they must not count toward error count."""
        samples = [
            _sample(1, 1.0, 1.0, 0.0, err=0),
            _sample(2, 2.0, None, None, kind="DROP", err=6),  # in settle
            _sample(3, 3.0, 1.0, 0.0, err=0),
            _sample(4, 4.0, None, None, kind="DROP", err=7),  # outside settle
        ]
        events = [_settle_begin(1.5), _settle_end(2.5)]
        metrics = compute_section_metrics(_make_guiding_section(samples, events=events))
        # Only frame 4's error row counts — frame 2's is inside settle.
        assert metrics.frame_count_error == 1

    def test_none_anchored_begin_treated_as_zero(self):
        """A ``settle_begin`` event emitted before the first sample has
        ``time_seconds = None`` — anchor it to the section start (0.0)."""
        samples = [
            _sample(1, 1.0, 99.0, 0.0),  # inside the [0, 3] settle → excluded
            _sample(2, 2.0, 99.0, 0.0),  # excluded
            _sample(3, 3.0, 99.0, 0.0),  # on end boundary → excluded
            _sample(4, 4.0, 2.0, 0.0),  # after → kept
        ]
        events = [_settle_begin(None), _settle_end(3.0)]
        metrics = compute_section_metrics(_make_guiding_section(samples, events=events))
        assert metrics.frame_count_in_settle == 3
        assert metrics.rms_ra_px == pytest.approx(2.0)

    def test_no_settle_events_leaves_metrics_unfiltered(self):
        """When a section has no settle events, behaviour matches the
        pre-settle-support baseline — every sample goes into stats."""
        samples = [
            _sample(1, 1.0, 1.0, 0.0),
            _sample(2, 2.0, -1.0, 0.0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.frame_count_in_settle == 0
        assert metrics.frame_count_in_stats == 2
        assert metrics.rms_ra_px == pytest.approx(1.0)


class TestDrift:
    def test_pinned_slope_in_units_per_minute(self):
        """Linear ramp: +2 px over 1 minute = +2 px/min slope.

        Times at 0, 60, 120 seconds (= 0, 1, 2 minutes), values at
        0, 2, 4 → regression slope exactly 2 per minute.
        """
        samples = [
            _sample(1, 0.0, 0.0, 0.0),
            _sample(2, 60.0, 2.0, -1.0),
            _sample(3, 120.0, 4.0, -2.0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.drift_ra_px_per_min == pytest.approx(2.0)
        # Dec: 0, -1, -2 → slope = -1 per minute.
        assert metrics.drift_dec_px_per_min == pytest.approx(-1.0)

    def test_flat_data_has_zero_drift(self):
        """All values identical → slope is zero."""
        samples = [
            _sample(1, 0.0, 0.5, 0.5),
            _sample(2, 30.0, 0.5, 0.5),
            _sample(3, 60.0, 0.5, 0.5),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.drift_ra_px_per_min == pytest.approx(0.0)
        assert metrics.drift_dec_px_per_min == pytest.approx(0.0)

    def test_drift_excludes_settle_samples(self):
        """Samples inside a settle window must not skew the regression."""
        samples = [
            _sample(1, 0.0, 0.0, 0.0),
            _sample(2, 60.0, 2.0, 0.0),
            # Big spike inside settle — ignored.
            _sample(3, 90.0, 50.0, 0.0),
            _sample(4, 120.0, 4.0, 0.0),
        ]
        events = [_settle_begin(70.0), _settle_end(100.0)]
        metrics = compute_section_metrics(_make_guiding_section(samples, events=events))
        # Fitted to [(0, 0), (60, 2), (120, 4)] — slope +2 px/min.
        assert metrics.drift_ra_px_per_min == pytest.approx(2.0)

    def test_drift_none_on_single_sample(self):
        """<2 pairs → drift is undefined."""
        samples = [_sample(1, 0.0, 1.0, 1.0)]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.drift_ra_px_per_min is None
        assert metrics.drift_dec_px_per_min is None

    def test_drift_none_on_identical_timestamps(self):
        """Degenerate case: all samples at the same time_seconds — no slope."""
        samples = [
            _sample(1, 5.0, 0.0, 0.0),
            _sample(2, 5.0, 1.0, 1.0),
            _sample(3, 5.0, 2.0, 2.0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.drift_ra_px_per_min is None
        assert metrics.drift_dec_px_per_min is None


class TestOscillation:
    def test_full_alternation_is_one(self):
        """Sign flips every step → oscillation = 1.0."""
        samples = [
            _sample(1, 1.0, 1.0, 0.5),
            _sample(2, 2.0, -1.0, -0.5),
            _sample(3, 3.0, 1.0, 0.5),
            _sample(4, 4.0, -1.0, -0.5),
            _sample(5, 5.0, 1.0, 0.5),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        # 4 pairs, all flip → 4/4 = 1.0 for both axes.
        assert metrics.oscillation_ra == pytest.approx(1.0)
        assert metrics.oscillation_dec == pytest.approx(1.0)

    def test_no_flips_is_zero(self):
        """All same sign → oscillation = 0.0."""
        samples = [
            _sample(1, 1.0, 0.5, -0.5),
            _sample(2, 2.0, 0.6, -0.6),
            _sample(3, 3.0, 0.4, -0.4),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.oscillation_ra == pytest.approx(0.0)
        assert metrics.oscillation_dec == pytest.approx(0.0)

    def test_partial_oscillation(self):
        """RA sequence [1, 2, -1, 1] → one flip pair at 2→-1 and
        another at -1→1 = 2 flips out of 3 pairs = 2/3."""
        samples = [
            _sample(1, 1.0, 1.0, 0.0),
            _sample(2, 2.0, 2.0, 0.0),
            _sample(3, 3.0, -1.0, 0.0),
            _sample(4, 4.0, 1.0, 0.0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.oscillation_ra == pytest.approx(2.0 / 3.0)

    def test_zero_values_are_skipped(self):
        """Zero RA values aren't flips — they have no sign. Sequence
        [1, 0, 2, -1]: zero is skipped, leaving [1, 2, -1] → 1 flip /
        2 pairs = 0.5."""
        samples = [
            _sample(1, 1.0, 1.0, 0.0),
            _sample(2, 2.0, 0.0, 0.0),
            _sample(3, 3.0, 2.0, 0.0),
            _sample(4, 4.0, -1.0, 0.0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.oscillation_ra == pytest.approx(0.5)

    def test_oscillation_none_when_all_zero_or_single(self):
        """All zero RA → no valid pairs → None."""
        samples = [
            _sample(1, 1.0, 0.0, 1.0),
            _sample(2, 2.0, 0.0, -1.0),
            _sample(3, 3.0, 0.0, 1.0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.oscillation_ra is None
        # Dec flips every step still works.
        assert metrics.oscillation_dec == pytest.approx(1.0)

    def test_oscillation_excludes_settle_samples(self):
        """Settle window is filtered before computing oscillation."""
        samples = [
            _sample(1, 1.0, 1.0, 0.0),
            _sample(2, 2.0, 1.0, 0.0),
            # Inside settle — a wild alternating pair ignored.
            _sample(3, 3.0, -10.0, 0.0),
            _sample(4, 4.0, 10.0, 0.0),
            _sample(5, 5.0, 1.0, 0.0),
        ]
        events = [_settle_begin(2.5), _settle_end(4.5)]
        metrics = compute_section_metrics(_make_guiding_section(samples, events=events))
        # Kept pairs: (1,1), (1,1), (1,1)... only (1,1,1) remains with
        # settle filter → 0 flips.
        assert metrics.oscillation_ra == pytest.approx(0.0)
