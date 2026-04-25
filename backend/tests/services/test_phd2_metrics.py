"""Unit tests for PHD2 metrics computation — PHDLogViewer-aligned (spec v4 §5.2).

Hand-computed values — these are pinned regression tests. v0.25.0 (Pass
D-1) switched the formulas from the pre-v3.1 forms to PHDLogViewer's
exact algorithms; expected values reflect the new forms:

- RMS = population standard deviation (NOT RMS-from-zero) — §M1
- RA drift = ``(ra_last − ra_first − Σ ra_guide) / Δt × 60`` — §5.2.3 / §M2
- Dec drift = LS slope of unguided-frames-only y_accum × 60 — §5.2.4 / §M3
- PA error = ``3.8197 · |drift_dec| · pixel_scale / cos(δ)`` — §5.2.6
- Peak = sign-preserving max-by-absolute-value — §5.2.2
- Oscillation = sign-flip rate, **zero values treated as positive** — §5.2.5
- Duration = total + included split — §5.2.8
"""

from __future__ import annotations

import math
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
    declination_deg: float | None = None,
    events: list[LogEvent] | None = None,
) -> LogSection:
    return LogSection(
        kind="guiding",
        index=0,
        start_time=datetime(2026, 1, 1, 0, 0, 0),
        header=SectionHeader(
            pixel_scale_arcsec_per_px=pixel_scale,
            declination_deg=declination_deg,
        ),
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
    ra_guide: float | None = None,
    dec_guide: float | None = None,
    ra_dur: int | None = None,
    dec_dur: int | None = None,
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
        ra_guide_px=ra_guide,
        dec_guide_px=dec_guide,
        ra_duration_ms=ra_dur,
        dec_duration_ms=dec_dur,
    )


class TestRmsAsStandardDeviation:
    """RMS = population stddev (PHDLogViewer §M1), NOT RMS-from-zero.

    For series ``[1, -2, 3]``: mean = 2/3, var = ((1−2/3)² + (−2−2/3)²
    + (3−2/3)²) / 3 = (1/9 + 64/9 + 49/9) / 3 = 38/9. stddev = √(38/9).
    """

    def test_pinned_stddev_on_hand_computed_values(self):
        samples = [
            _sample(1, 1.0, 1.0, 0.0),
            _sample(2, 2.0, -2.0, 0.0),
            _sample(3, 3.0, 3.0, 0.0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.rms_ra_px == pytest.approx(math.sqrt(38 / 9))
        # Constant Dec values → variance = 0 → stddev = 0.
        assert metrics.rms_dec_px == pytest.approx(0.0)
        # Total = sqrt(stddev_ra² + stddev_dec²) collapses to stddev_ra.
        assert metrics.rms_total_px == pytest.approx(metrics.rms_ra_px)

    def test_zero_mean_inputs_match_rms_from_zero(self):
        """When the mean is zero, stddev == RMS-from-zero (a deliberate
        sanity-check anchor — RA=[3,-3], Dec=[4,-4] → stddev_ra=3,
        stddev_dec=4, total=5)."""
        samples = [
            _sample(1, 1.0, 3.0, 4.0),
            _sample(2, 2.0, -3.0, -4.0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.rms_ra_px == pytest.approx(3.0)
        assert metrics.rms_dec_px == pytest.approx(4.0)
        assert metrics.rms_total_px == pytest.approx(5.0)

    def test_constant_value_stddev_is_zero(self):
        """A constant series has zero variance — PHDLogViewer reports
        stddev as 0, NightCrate matches. (Pre-v0.25.0 this would have
        been the constant value itself via the RMS-from-zero form.)"""
        samples = [
            _sample(1, 1.0, 5.0, -5.0),
            _sample(2, 2.0, 5.0, -5.0),
            _sample(3, 3.0, 5.0, -5.0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.rms_ra_px == pytest.approx(0.0)
        assert metrics.rms_dec_px == pytest.approx(0.0)
        assert metrics.rms_total_px == pytest.approx(0.0)

    def test_drop_frames_excluded_from_stddev(self):
        """DROP frames have None ra_raw/dec_raw — they must not count
        toward stddev. RA = [1, -1] over the two real samples →
        mean = 0, stddev = 1."""
        samples = [
            _sample(1, 1.0, 1.0, 2.0),
            _sample(2, 2.0, None, None, kind="DROP", err=6),
            _sample(3, 3.0, -1.0, -2.0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.rms_ra_px == pytest.approx(1.0)
        assert metrics.rms_dec_px == pytest.approx(2.0)
        assert metrics.frame_count_total == 3
        assert metrics.frame_count_error == 1


class TestSignedPeak:
    """Peak = sign-preserving max-by-absolute-value (§5.2.2). For
    ``[+0.3, -0.5, +0.4]``, peak_ra is ``-0.5``, NOT ``0.5``."""

    def test_peak_preserves_negative_sign(self):
        samples = [
            _sample(1, 1.0, 0.5, 0.0),
            _sample(2, 2.0, -2.5, 0.0),
            _sample(3, 3.0, 1.0, 0.0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        # |-2.5| > |1.0| > |0.5| → peak_ra = -2.5 (sign retained).
        assert metrics.peak_ra_px == pytest.approx(-2.5)

    def test_peak_preserves_positive_sign(self):
        samples = [
            _sample(1, 1.0, -0.5, 0.0),
            _sample(2, 2.0, 2.5, 0.0),
            _sample(3, 3.0, -1.0, 0.0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.peak_ra_px == pytest.approx(2.5)

    def test_peak_dec_independent_of_peak_ra(self):
        """Each axis picks its own signed max-abs."""
        samples = [
            _sample(1, 1.0, 0.5, -3.0),
            _sample(2, 2.0, -2.0, 1.0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.peak_ra_px == pytest.approx(-2.0)
        assert metrics.peak_dec_px == pytest.approx(-3.0)


class TestDurationAndCounts:
    def test_duration_total_from_sample_times(self):
        samples = [
            _sample(1, 1.0, 0.0, 0.0),
            _sample(2, 100.5, 0.0, 0.0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.duration_total_seconds == pytest.approx(99.5)

    def test_duration_included_excludes_settle_gaps(self):
        """``duration_included`` counts only inter-frame intervals where
        BOTH endpoints are outside settle. A 5 s settle window mid-
        section drops out — the dither-and-resettle gap is recovered
        via the included-time row.
        """
        samples = [
            _sample(1, 0.0, 0.0, 0.0),
            _sample(2, 1.0, 0.0, 0.0),
            # frames 3 and 4 are in settle.
            _sample(3, 2.5, 0.0, 0.0),
            _sample(4, 4.0, 0.0, 0.0),
            _sample(5, 6.0, 0.0, 0.0),
        ]
        events = [_settle_begin(2.0), _settle_end(5.0)]
        metrics = compute_section_metrics(_make_guiding_section(samples, events=events))
        # Total = 6.0 (last - first).
        assert metrics.duration_total_seconds == pytest.approx(6.0)
        # Included intervals: (0→1) plus (5→6) — second pair has
        # frame 5 outside settle and frame 4 in settle, so does NOT
        # count. The (1→2.5) pair has frame 3 in settle, also skipped.
        # So only the (0→1) interval contributes → 1.0 s.
        assert metrics.duration_included_seconds == pytest.approx(1.0)

    def test_duration_included_with_no_settle_equals_total(self):
        """No settle events → every adjacent pair counts → included == total."""
        samples = [
            _sample(1, 0.0, 0.0, 0.0),
            _sample(2, 5.0, 0.0, 0.0),
            _sample(3, 12.0, 0.0, 0.0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.duration_total_seconds == pytest.approx(12.0)
        assert metrics.duration_included_seconds == pytest.approx(12.0)

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
        """Calibration sections have no quality metrics — everything is None."""
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
        assert metrics.drift_ra_px_per_min is None
        assert metrics.drift_dec_px_per_min is None
        assert metrics.polar_alignment_error_arcmin is None
        assert metrics.frame_count_total == 0
        assert metrics.duration_total_seconds == 0.0
        assert metrics.duration_included_seconds == 0.0
        assert metrics.arcsec_scale == 2.0


class TestEmptySection:
    def test_empty_guiding_section_returns_no_metrics(self):
        section = _make_guiding_section([])
        metrics = compute_section_metrics(section)
        assert metrics.rms_ra_px is None
        assert metrics.frame_count_total == 0
        assert metrics.frame_count_in_settle == 0
        assert metrics.frame_count_in_stats == 0
        assert metrics.duration_total_seconds == 0.0
        assert metrics.duration_included_seconds == 0.0
        assert metrics.polar_alignment_error_arcmin is None


class TestSettleExclusion:
    """Per PHD2 / PHDLogViewer convention, samples inside settle windows
    (bracketed by ``settle_begin`` / ``settle_end`` INFO events) must be
    excluded from every guide-quality metric — not just RMS.
    """

    def test_simple_pair_excludes_spike_from_stddev_and_peak(self):
        """Two calm samples around a huge spike bracketed by a settle pair.

        Spike (RA=100 px at t=2.0) must NOT appear in stddev or peak.
        Stats RA=[1, -1] → mean=0, stddev=1, signed peak=1.
        """
        samples = [
            _sample(1, 1.0, 1.0, 0.0),
            _sample(2, 2.0, 100.0, 0.0),
            _sample(3, 3.0, -1.0, 0.0),
        ]
        events = [_settle_begin(1.5), _settle_end(2.5)]
        metrics = compute_section_metrics(_make_guiding_section(samples, events=events))
        assert metrics.rms_ra_px == pytest.approx(1.0)
        assert metrics.peak_ra_px == pytest.approx(1.0)
        assert metrics.frame_count_total == 3
        assert metrics.frame_count_in_settle == 1
        assert metrics.frame_count_in_stats == 2

    def test_boundary_sample_is_treated_as_in_settle(self):
        """A sample with time_seconds exactly equal to an interval edge
        is a transition sample — excluded, to match PHDLogViewer."""
        samples = [
            _sample(1, 1.0, 2.0, 0.0),
            _sample(2, 2.0, 5.0, 0.0),
            _sample(3, 3.0, 3.0, 0.0),
            _sample(4, 4.0, 4.0, 0.0),
            _sample(5, 5.0, 6.0, 0.0),
        ]
        events = [_settle_begin(1.0), _settle_end(3.0)]
        metrics = compute_section_metrics(_make_guiding_section(samples, events=events))
        # Three samples on/inside the [1, 3] window → excluded.
        assert metrics.frame_count_in_settle == 3
        assert metrics.frame_count_in_stats == 2
        # Stats RA = [4, 6] → mean = 5, var = 1, stddev = 1.
        assert metrics.rms_ra_px == pytest.approx(1.0)

    def test_section_opens_mid_settle_from_lone_end(self):
        """A lone ``settle_end`` at t=2.0 with no preceding ``settle_begin``
        means the section opened inside an active settle — exclude everything
        up through t=2.0."""
        samples = [
            _sample(1, 1.0, 10.0, 0.0),
            _sample(2, 2.0, 10.0, 0.0),
            _sample(3, 3.0, 1.0, 0.0),
            _sample(4, 4.0, -1.0, 0.0),
        ]
        events = [_settle_end(2.0)]
        metrics = compute_section_metrics(_make_guiding_section(samples, events=events))
        assert metrics.frame_count_in_settle == 2
        assert metrics.frame_count_in_stats == 2
        # Stats RA = [1, -1] → stddev = 1.
        assert metrics.rms_ra_px == pytest.approx(1.0)

    def test_unclosed_begin_extends_to_last_sample(self):
        """A ``settle_begin`` without a matching ``settle_end`` means the
        section ended during settling — exclude from begin through the
        last sample's time."""
        samples = [
            _sample(1, 1.0, 1.0, 0.0),
            _sample(2, 2.0, 50.0, 0.0),
            _sample(3, 3.0, 75.0, 0.0),
        ]
        events = [_settle_begin(2.0)]
        metrics = compute_section_metrics(_make_guiding_section(samples, events=events))
        assert metrics.frame_count_in_settle == 2
        assert metrics.frame_count_in_stats == 1
        # Single-sample stats → stddev = 0 (variance is undefined for
        # one value; PHDLogViewer/LFit both return 0).
        assert metrics.rms_ra_px == pytest.approx(0.0)

    def test_drop_inside_settle_counts_as_in_settle_not_double(self):
        samples = [
            _sample(1, 1.0, 2.0, 2.0),
            _sample(2, 2.0, None, None, kind="DROP", err=6),
            _sample(3, 3.0, 3.0, 3.0),
        ]
        events = [_settle_begin(1.5), _settle_end(2.5)]
        metrics = compute_section_metrics(_make_guiding_section(samples, events=events))
        assert metrics.frame_count_total == 3
        assert metrics.frame_count_in_settle == 1
        assert metrics.frame_count_in_stats == 2

    def test_frame_count_error_excludes_settle_errors(self):
        """Error rows inside settle windows are transitional noise, not
        real guiding failures — they must not count toward error count."""
        samples = [
            _sample(1, 1.0, 1.0, 0.0, err=0),
            _sample(2, 2.0, None, None, kind="DROP", err=6),
            _sample(3, 3.0, 1.0, 0.0, err=0),
            _sample(4, 4.0, None, None, kind="DROP", err=7),
        ]
        events = [_settle_begin(1.5), _settle_end(2.5)]
        metrics = compute_section_metrics(_make_guiding_section(samples, events=events))
        assert metrics.frame_count_error == 1

    def test_none_anchored_begin_treated_as_zero(self):
        """A ``settle_begin`` event emitted before the first sample has
        ``time_seconds = None`` — anchor it to the section start (0.0)."""
        samples = [
            _sample(1, 1.0, 99.0, 0.0),
            _sample(2, 2.0, 99.0, 0.0),
            _sample(3, 3.0, 99.0, 0.0),
            _sample(4, 4.0, 2.0, 0.0),
        ]
        events = [_settle_begin(None), _settle_end(3.0)]
        metrics = compute_section_metrics(_make_guiding_section(samples, events=events))
        assert metrics.frame_count_in_settle == 3
        # Single-sample stats → stddev = 0.
        assert metrics.rms_ra_px == pytest.approx(0.0)

    def test_no_settle_events_leaves_metrics_unfiltered(self):
        samples = [
            _sample(1, 1.0, 1.0, 0.0),
            _sample(2, 2.0, -1.0, 0.0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.frame_count_in_settle == 0
        assert metrics.frame_count_in_stats == 2
        assert metrics.rms_ra_px == pytest.approx(1.0)


class TestRaDriftCorrectionsSubtraction:
    """RA drift via PHDLogViewer's corrections-subtraction algorithm
    (§5.2.3 / §M2): ``drift = (ra_last − ra_first − Σ ra_guide) / Δt × 60``.

    The Σ runs over all settle-filtered samples with ``ra_duration_ms
    != 0`` and a non-null ``ra_guide_px``.
    """

    def test_pure_drift_no_corrections_matches_simple_slope(self):
        """No guide pulses → sum_raguide = 0 → drift collapses to
        (ra_last − ra_first) / Δt × 60. Linear ramp of +2 px over 60 s
        = +2 px/min."""
        samples = [
            _sample(1, 0.0, 0.0, 0.0),
            _sample(2, 30.0, 1.0, 0.0),
            _sample(3, 60.0, 2.0, 0.0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.drift_ra_px_per_min == pytest.approx(2.0)

    def test_perfect_correction_zeros_observed_drift(self):
        """Star drifted +2 px over 60 s but the algorithm pushed it
        back +2 px (positive ra_guide). Observed raraw is flat — but
        the *true* mount drift is +2 px/min after backing out the
        correction.

        Sequence (each frame): drift +1 px between frames, algorithm
        responds with +1 px ra_guide before the next sample. Observed
        positions stay at 0.

        sum_raguide = +1 + +1 = +2 (frames 2 and 3 both pulse).
        drift = (raraw_last − raraw_first − sum) / dt × 60
              = (0 − 0 − 2) / 60 × 60
              = -2 px/min.

        Hmm — sign flipped from "intuitive" because ra_guide is the
        algorithm's *desired correction*. If the star is being pushed
        positive by the algorithm to counter a -2 drift, ra_guide is
        +2 and the recovered drift is -2. NightCrate matches
        PHDLogViewer's sign convention; the absolute value is what
        the diagnostic engine uses.
        """
        samples = [
            _sample(1, 0.0, 0.0, 0.0, ra_guide=1.0, ra_dur=500),
            _sample(2, 30.0, 0.0, 0.0, ra_guide=1.0, ra_dur=500),
            _sample(3, 60.0, 0.0, 0.0, ra_guide=0.0, ra_dur=0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.drift_ra_px_per_min == pytest.approx(-2.0)

    def test_min_move_pulses_skipped(self):
        """Frames with ra_duration_ms = 0 (algorithm-decided min-move)
        do NOT contribute to sum_raguide even if they have a non-null
        ra_guide_px value."""
        samples = [
            _sample(1, 0.0, 0.0, 0.0),
            # ra_guide_px present but ra_duration_ms = 0 → skipped.
            _sample(2, 60.0, 1.0, 0.0, ra_guide=0.5, ra_dur=0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        # sum = 0 (the only candidate is skipped) → drift = 1/60×60 = 1.
        assert metrics.drift_ra_px_per_min == pytest.approx(1.0)

    def test_single_valid_sample_returns_none(self):
        samples = [_sample(1, 0.0, 1.0, 0.0)]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.drift_ra_px_per_min is None

    def test_zero_duration_returns_none(self):
        """All samples at the same time_seconds → dt = 0 → drift undefined."""
        samples = [
            _sample(1, 5.0, 0.0, 0.0),
            _sample(2, 5.0, 1.0, 0.0),
            _sample(3, 5.0, 2.0, 0.0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.drift_ra_px_per_min is None

    def test_drift_excludes_settle_corrections(self):
        """Settle-window ra_guide values must NOT enter the sum — the
        stats_samples filter strips them out before the corrections
        loop.
        """
        samples = [
            _sample(1, 0.0, 0.0, 0.0),
            # Inside settle: large guide pulse, ignored.
            _sample(2, 30.0, 0.0, 0.0, ra_guide=100.0, ra_dur=2000),
            _sample(3, 60.0, 2.0, 0.0),
        ]
        events = [_settle_begin(20.0), _settle_end(40.0)]
        metrics = compute_section_metrics(_make_guiding_section(samples, events=events))
        # Stats: frames 1 and 3 only, no guide pulses → drift = 2/60×60 = 2.
        assert metrics.drift_ra_px_per_min == pytest.approx(2.0)


class TestDecDriftUnguidedFramesOnly:
    """Dec drift via PHDLogViewer's unguided-frames-only accumulation
    (§5.2.4 / §M3). y_accum advances only when the *previous* frame
    had no Dec pulse (``dec_duration_ms == 0`` or null); the LS slope
    of (t, y_accum) gives the drift rate.
    """

    def test_no_dec_guide_collapses_to_simple_slope(self):
        """Every prev_guided is False → every change accumulates →
        slope of decraw vs t. dec=[0, 1, 2] over 0-120s → 1 per minute."""
        samples = [
            _sample(1, 0.0, 0.0, 0.0),
            _sample(2, 60.0, 0.0, 1.0),
            _sample(3, 120.0, 0.0, 2.0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.drift_dec_px_per_min == pytest.approx(1.0)

    def test_all_guided_returns_zero_match_phdlogviewer(self):
        """When every frame's prev was guided (dec_dur != 0),
        only the seed (first.t, 0) lives in the regression — n=1.
        PHDLogViewer's LFit::B() returns 0 in this degenerate case;
        NightCrate matches for cross-tool consistency.
        """
        samples = [
            _sample(1, 0.0, 0.0, 0.0, dec_dur=500),
            _sample(2, 60.0, 0.0, 5.0, dec_dur=500),
            _sample(3, 120.0, 0.0, 10.0, dec_dur=500),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.drift_dec_px_per_min == pytest.approx(0.0)

    def test_alternating_guided_unguided_uses_only_unguided_changes(self):
        """Frames 1, 3 have dec_dur = 0; frames 2, 4 have dec_dur > 0.
        Pre-frame guided state at each iteration:
            i=2: prev=frame1 (unguided). Δ = dec[2] - dec[1] = 1. y_accum=1.
            i=3: prev=frame2 (guided). Skip — y_accum stays 1.
            i=4: prev=frame3 (unguided). Δ = dec[4] - dec[3] = 3. y_accum=4.
        Regression points: (0, 0), (60, 1), (180, 4).
        n=3, mean_x=80, mean_y=5/3.
        S_xx = (0-80)² + (60-80)² + (180-80)² = 6400+400+10000 = 16800.
        S_xy = (0-80)(0-5/3) + (60-80)(1-5/3) + (180-80)(4-5/3)
             = -80·-5/3 + -20·-2/3 + 100·7/3
             = 400/3 + 40/3 + 700/3 = 1140/3 = 380.
        slope = 380 / 16800 = 0.022619... per second
              × 60 = 1.357... per minute.
        """
        samples = [
            _sample(1, 0.0, 0.0, 0.0, dec_dur=0),
            _sample(2, 60.0, 0.0, 1.0, dec_dur=400),
            _sample(3, 120.0, 0.0, 1.0, dec_dur=0),
            _sample(4, 180.0, 0.0, 4.0, dec_dur=400),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        expected = (380 / 16800) * 60
        assert metrics.drift_dec_px_per_min == pytest.approx(expected)

    def test_single_valid_sample_returns_none(self):
        """Fewer than two samples with valid dec_raw → None (distinct
        from "all-guided" which returns 0)."""
        samples = [_sample(1, 0.0, 0.0, 1.0)]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.drift_dec_px_per_min is None

    def test_all_zero_dec_drift_when_no_drift(self):
        samples = [
            _sample(1, 0.0, 0.0, 0.0),
            _sample(2, 60.0, 0.0, 0.0),
            _sample(3, 120.0, 0.0, 0.0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.drift_dec_px_per_min == pytest.approx(0.0)


class TestPolarAlignmentError:
    """Polar alignment error in arcminutes — Barrett's formula via
    PHDLogViewer (§5.2.6 / §M2): ``α = 3.8197 · |drift| · pixel_scale
    / cos(δ)``.
    """

    def test_pinned_pa_at_celestial_equator(self):
        """δ = 0 → cos(δ) = 1 → α = 3.8197 · drift · scale.

        Drift = 1 px/min, scale = 2 ″/px, δ = 0° →
        α = 3.8197 · 1 · 2 / 1 = 7.6394 arcmin.

        Drift uses the Dec-unguided algorithm: dec=[0, 1, 2] over
        0-120 s with no dec pulses → 1 px/min.
        """
        samples = [
            _sample(1, 0.0, 0.0, 0.0),
            _sample(2, 60.0, 0.0, 1.0),
            _sample(3, 120.0, 0.0, 2.0),
        ]
        metrics = compute_section_metrics(
            _make_guiding_section(samples, pixel_scale=2.0, declination_deg=0.0),
        )
        assert metrics.drift_dec_px_per_min == pytest.approx(1.0)
        assert metrics.polar_alignment_error_arcmin == pytest.approx(7.6394)

    def test_pa_at_mid_declination_amplifies(self):
        """δ = 60° → cos(δ) = 0.5 → PA error doubles vs equator.

        Drift = 0.5 px/min, scale = 1 ″/px, δ = 60° →
        α = 3.8197 · 0.5 · 1 / 0.5 = 3.8197 arcmin.
        """
        samples = [
            _sample(1, 0.0, 0.0, 0.0),
            _sample(2, 60.0, 0.0, 0.5),
        ]
        metrics = compute_section_metrics(
            _make_guiding_section(samples, pixel_scale=1.0, declination_deg=60.0),
        )
        assert metrics.drift_dec_px_per_min == pytest.approx(0.5)
        assert metrics.polar_alignment_error_arcmin == pytest.approx(3.8197)

    def test_pa_uses_absolute_drift(self):
        """Negative Dec drift → PA error is positive (it's an
        absolute-value formula). dec=[0, -1, -2] → drift = -1 px/min,
        |drift| = 1 → same numeric PA as the +1 case."""
        samples = [
            _sample(1, 0.0, 0.0, 0.0),
            _sample(2, 60.0, 0.0, -1.0),
            _sample(3, 120.0, 0.0, -2.0),
        ]
        metrics = compute_section_metrics(
            _make_guiding_section(samples, pixel_scale=2.0, declination_deg=0.0),
        )
        assert metrics.drift_dec_px_per_min == pytest.approx(-1.0)
        assert metrics.polar_alignment_error_arcmin == pytest.approx(7.6394)

    def test_pa_none_when_declination_missing(self):
        samples = [
            _sample(1, 0.0, 0.0, 0.0),
            _sample(2, 60.0, 0.0, 1.0),
        ]
        metrics = compute_section_metrics(
            _make_guiding_section(samples, pixel_scale=2.0, declination_deg=None),
        )
        assert metrics.polar_alignment_error_arcmin is None

    def test_pa_none_when_pixel_scale_missing(self):
        samples = [
            _sample(1, 0.0, 0.0, 0.0),
            _sample(2, 60.0, 0.0, 1.0),
        ]
        metrics = compute_section_metrics(
            _make_guiding_section(samples, pixel_scale=None, declination_deg=0.0),
        )
        assert metrics.polar_alignment_error_arcmin is None

    def test_pa_none_when_drift_undefined(self):
        """Single-sample section → drift undefined → PA error None."""
        samples = [_sample(1, 0.0, 0.0, 0.0)]
        metrics = compute_section_metrics(
            _make_guiding_section(samples, pixel_scale=2.0, declination_deg=0.0),
        )
        assert metrics.drift_dec_px_per_min is None
        assert metrics.polar_alignment_error_arcmin is None

    def test_pa_none_near_celestial_pole(self):
        """δ → 90° → cos(δ) → 0 → formula diverges. NightCrate returns
        None rather than emit nonsense."""
        samples = [
            _sample(1, 0.0, 0.0, 0.0),
            _sample(2, 60.0, 0.0, 0.001),
        ]
        metrics = compute_section_metrics(
            _make_guiding_section(samples, pixel_scale=2.0, declination_deg=89.99999),
        )
        assert metrics.polar_alignment_error_arcmin is None

    def test_pa_pinned_at_high_declination_69(self):
        """Regression anchor for the ASIAir sample log scenario.

        At δ=69°, cos(δ) ≈ 0.358 → 1/cos(δ) ≈ 2.79. A small drift
        amplifies into a large PA error. With drift = 0.4344 px/min,
        scale = 3.96 ″/px, δ = 69°:

            α = 3.8197 · 0.4344 · 3.96 / cos(69°)
              = 3.8197 · 0.4344 · 3.96 / 0.3584
              ≈ 18.34 arcmin

        PHDLogViewer reports a much smaller value (~6.5') for the
        same log, but only because its parser is hardcoded to look
        for ``"RA = ... hr, Dec = ..."`` and silently leaves
        ``session.declination`` at 0.0 when the log uses the
        modern ``"Dec = 69.0 deg"`` standalone line (as ASIAir-
        bundled PHD2 does). Effectively `cos(0) = 1` in PHDLogViewer
        for these logs → 6.5 = 18.34 × cos(69°). NightCrate reads
        the declination correctly and applies the proper correction.

        This test pins the correct high-declination behaviour so a
        future refactor can't quietly regress to the no-cos form.
        Synthesised inputs reproduce the drift exactly: dec_raw_px
        ranges from 0 → 0.4344 over exactly 1 minute with no Dec
        pulses, so the unguided-frames-only algorithm yields
        drift = 0.4344 px/min.
        """
        samples = [
            _sample(1, 0.0, 0.0, 0.0),
            _sample(2, 60.0, 0.0, 0.4344),
        ]
        metrics = compute_section_metrics(
            _make_guiding_section(samples, pixel_scale=3.96, declination_deg=69.0),
        )
        assert metrics.drift_dec_px_per_min == pytest.approx(0.4344)
        # Hand-computed: 3.8197 × 0.4344 × 3.96 / cos(radians(69)) ≈ 18.34
        assert metrics.polar_alignment_error_arcmin == pytest.approx(18.34, abs=0.05)

    def test_pa_at_negative_declination(self):
        """Southern hemisphere targets — δ = -45° → cos(δ) = √2/2 ≈ 0.7071."""
        samples = [
            _sample(1, 0.0, 0.0, 0.0),
            _sample(2, 60.0, 0.0, 1.0),
        ]
        metrics = compute_section_metrics(
            _make_guiding_section(samples, pixel_scale=1.0, declination_deg=-45.0),
        )
        # drift = 1 px/min, scale = 1, |cos(-45)| = √2/2.
        expected = 3.8197 * 1.0 * 1.0 / math.cos(math.radians(45.0))
        assert metrics.polar_alignment_error_arcmin == pytest.approx(expected)


class TestElongation:
    """Scatter-ellipse elongation per PHDLogViewer §5.2.7. ``|lx − ly|
    / (lx + ly)`` over the rotated mount-axis frame, range [0, 1].
    """

    def test_circular_dispersion_is_zero(self):
        """A symmetric square pattern around the mean has equal sigmas
        on both axes after rotation → elongation = 0."""
        samples = [
            _sample(1, 1.0, 1.0, 0.0),
            _sample(2, 2.0, -1.0, 0.0),
            _sample(3, 3.0, 0.0, 1.0),
            _sample(4, 4.0, 0.0, -1.0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.elongation == pytest.approx(0.0, abs=1e-9)

    def test_axis_aligned_line_has_unit_elongation(self):
        """All variance on one axis (RA = ±2, Dec = 0) → after
        rotation by 0 (cov_xy = 0, var_x > 0 → atan2(0, vxx) = 0),
        major sigma is along RA, minor along Dec = 0 →
        |2 − 0| / (2 + 0) = 1.
        """
        samples = [
            _sample(1, 1.0, -1.0, 0.0),
            _sample(2, 2.0, 1.0, 0.0),
            _sample(3, 3.0, -1.0, 0.0),
            _sample(4, 4.0, 1.0, 0.0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.elongation == pytest.approx(1.0, abs=1e-9)

    def test_zero_dispersion_returns_one(self):
        """Constant raraw/decraw → lx + ly < 1e-6 → defensive 1.0 per
        PHDLogViewer (not None — matches the C++ source exactly)."""
        samples = [
            _sample(1, 1.0, 0.5, 0.5),
            _sample(2, 2.0, 0.5, 0.5),
            _sample(3, 3.0, 0.5, 0.5),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.elongation == pytest.approx(1.0)

    def test_elongation_none_on_single_sample(self):
        samples = [_sample(1, 1.0, 0.5, 0.5)]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.elongation is None

    def test_elongation_skips_one_axis_null_samples(self):
        """A row with ra_raw set but dec_raw null doesn't contribute —
        the metric needs both axes to position the point."""
        good_samples = [
            _sample(1, 1.0, 1.0, 0.0),
            _sample(2, 2.0, -1.0, 0.0),
            _sample(3, 3.0, 0.0, 1.0),
            _sample(4, 4.0, 0.0, -1.0),
            # This row would muddy the dispersion if it were counted —
            # ra_raw is given, dec_raw is None → skipped.
            _sample(5, 5.0, 100.0, None),
        ]
        metrics = compute_section_metrics(_make_guiding_section(good_samples))
        # Same square pattern as test_circular_dispersion_is_zero.
        assert metrics.elongation == pytest.approx(0.0, abs=1e-9)

    def test_elongation_respects_settle_filter(self):
        """A spike inside a settle window must NOT inflate the elongation."""
        samples = [
            _sample(1, 1.0, 1.0, 0.0),
            _sample(2, 2.0, -1.0, 0.0),
            # Inside settle — must drop out.
            _sample(3, 3.0, 100.0, 100.0),
            _sample(4, 4.0, 0.0, 1.0),
            _sample(5, 5.0, 0.0, -1.0),
        ]
        events = [_settle_begin(2.5), _settle_end(3.5)]
        metrics = compute_section_metrics(_make_guiding_section(samples, events=events))
        # Surviving samples form the same circular square → 0.
        assert metrics.elongation == pytest.approx(0.0, abs=1e-9)


class TestOscillationZerosTreatedAsPositive:
    """Oscillation = sign-flip rate. Per spec §11.14, **zero values
    are treated as positive** (PHDLogViewer's RaOsc convention).
    """

    def test_full_alternation_is_one(self):
        samples = [
            _sample(1, 1.0, 1.0, 0.5),
            _sample(2, 2.0, -1.0, -0.5),
            _sample(3, 3.0, 1.0, 0.5),
            _sample(4, 4.0, -1.0, -0.5),
            _sample(5, 5.0, 1.0, 0.5),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.oscillation_ra == pytest.approx(1.0)
        assert metrics.oscillation_dec == pytest.approx(1.0)

    def test_no_flips_is_zero(self):
        samples = [
            _sample(1, 1.0, 0.5, -0.5),
            _sample(2, 2.0, 0.6, -0.6),
            _sample(3, 3.0, 0.4, -0.4),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.oscillation_ra == pytest.approx(0.0)
        assert metrics.oscillation_dec == pytest.approx(0.0)

    def test_partial_oscillation(self):
        """RA sequence [1, 2, -1, 1] → signs [+, +, -, +] →
        2 flips out of 3 pairs = 2/3."""
        samples = [
            _sample(1, 1.0, 1.0, 0.0),
            _sample(2, 2.0, 2.0, 0.0),
            _sample(3, 3.0, -1.0, 0.0),
            _sample(4, 4.0, 1.0, 0.0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.oscillation_ra == pytest.approx(2.0 / 3.0)

    def test_zero_values_treated_as_positive(self):
        """RA sequence [1, 0, 2, -1] → signs (+, +, +, -) (zero counts
        as positive per spec §11.14) → 1 flip out of 3 pairs = 1/3.

        The pre-v0.25.0 implementation skipped zeros entirely, which
        was a deliberate divergence from PHDLogViewer.
        """
        samples = [
            _sample(1, 1.0, 1.0, 0.0),
            _sample(2, 2.0, 0.0, 0.0),
            _sample(3, 3.0, 2.0, 0.0),
            _sample(4, 4.0, -1.0, 0.0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.oscillation_ra == pytest.approx(1.0 / 3.0)

    def test_all_zero_values_have_zero_oscillation(self):
        """Every value is 0 → all signs positive → no flips → 0.0
        (NOT None, distinct from the pre-v0.25.0 behaviour)."""
        samples = [
            _sample(1, 1.0, 0.0, 1.0),
            _sample(2, 2.0, 0.0, -1.0),
            _sample(3, 3.0, 0.0, 1.0),
        ]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.oscillation_ra == pytest.approx(0.0)
        # Dec still works normally.
        assert metrics.oscillation_dec == pytest.approx(1.0)

    def test_oscillation_none_on_single_sample(self):
        samples = [_sample(1, 1.0, 0.5, 0.5)]
        metrics = compute_section_metrics(_make_guiding_section(samples))
        assert metrics.oscillation_ra is None
        assert metrics.oscillation_dec is None

    def test_oscillation_excludes_settle_samples(self):
        samples = [
            _sample(1, 1.0, 1.0, 0.0),
            _sample(2, 2.0, 1.0, 0.0),
            _sample(3, 3.0, -10.0, 0.0),
            _sample(4, 4.0, 10.0, 0.0),
            _sample(5, 5.0, 1.0, 0.0),
        ]
        events = [_settle_begin(2.5), _settle_end(4.5)]
        metrics = compute_section_metrics(_make_guiding_section(samples, events=events))
        assert metrics.oscillation_ra == pytest.approx(0.0)
