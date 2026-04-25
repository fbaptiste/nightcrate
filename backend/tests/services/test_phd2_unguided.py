"""Unit tests for PHD2 unguided RA reconstruction (spec v4 §6.2)."""

from __future__ import annotations

from datetime import datetime

from nightcrate.services.phd2_models import (
    GuidingSample,
    LogSection,
    SectionHeader,
)
from nightcrate.services.phd2_unguided import reconstruct_unguided_ra


def _sample(
    frame: int,
    time_s: float,
    ra: float | None,
    *,
    kind: str = "Mount",
    err: int = 0,
    ra_guide: float | None = None,
) -> GuidingSample:
    return GuidingSample(
        frame=frame,
        time_seconds=time_s,
        mount_kind=kind,  # type: ignore[arg-type]
        ra_raw_px=ra,
        dec_raw_px=0.0 if ra is not None else None,
        ra_guide_px=ra_guide,
        error_code=err,
    )


def _section(samples: list[GuidingSample]) -> LogSection:
    return LogSection(
        kind="guiding",
        index=0,
        start_time=datetime(2026, 1, 1, 0, 0, 0),
        header=SectionHeader(pixel_scale_arcsec_per_px=2.0),
        samples=samples,
    )


class TestZeroDriftZeroCorrections:
    def test_flat_trace_at_zero(self):
        # raraw stays at 0, raguide is 0 → move = 0 every step.
        samples = [_sample(i, float(i), 0.0, ra_guide=0.0) for i in range(5)]
        out = reconstruct_unguided_ra(_section(samples))
        assert out == [0.0, 0.0, 0.0, 0.0, 0.0]


class TestConstantDriftZeroCorrections:
    def test_linear_trace(self):
        # raraw climbs 0, 1, 2, 3, 4 (1px/frame). raguide = 0 → move = 1.
        samples = [_sample(i, float(i), float(i), ra_guide=0.0) for i in range(5)]
        out = reconstruct_unguided_ra(_section(samples))
        # Frame 0: raraw=0, prev_raraw=0, prev_raguide=0 → move=0, rapos=0.
        # Frame 1: raraw=1, prev_raraw=0, prev_raguide=0 → move=1, rapos=1.
        # ... rapos accumulates 0,1,2,3,4.
        assert out == [0.0, 1.0, 2.0, 3.0, 4.0]


class TestPerfectCorrectionConstantDrift:
    def test_recovers_drift_via_raguide_accumulation(self):
        # Mount drifts 1 px/frame; algorithm corrects perfectly so raraw
        # stays at 0. raguide carries the −1 correction each frame.
        # The recurrence should reconstruct the drift trace from raguide.
        samples = [_sample(i, float(i), 0.0, ra_guide=-1.0) for i in range(5)]
        out = reconstruct_unguided_ra(_section(samples))
        # Frame 0: prev=(0,0) → move = 0-0-0 = 0, rapos=0.
        # Frame 1: prev=(0,-1) → move = 0-0-(-1) = 1, rapos=1.
        # Frame 2: prev=(0,-1) → move = 0-0-(-1) = 1, rapos=2.
        # Frame 3: prev=(0,-1) → move = 0-0-(-1) = 1, rapos=3.
        # Frame 4: prev=(0,-1) → move = 0-0-(-1) = 1, rapos=4.
        assert out == [0.0, 1.0, 2.0, 3.0, 4.0]


class TestDropFrame:
    def test_drop_frame_emits_none_without_breaking_recurrence(self):
        # Frame 2 is a DROP (ra_raw_px=None, error_code=7).
        # Recurrence should skip it without losing track of prev_*.
        samples = [
            _sample(0, 0.0, 0.0, ra_guide=0.0),
            _sample(1, 1.0, 1.0, ra_guide=0.0),
            _sample(2, 2.0, None, err=7),
            _sample(3, 3.0, 3.0, ra_guide=0.0),
            _sample(4, 4.0, 4.0, ra_guide=0.0),
        ]
        out = reconstruct_unguided_ra(_section(samples))
        # Frame 0: rapos=0
        # Frame 1: move = 1-0-0 = 1, rapos=1
        # Frame 2: DROP → None, prev_raraw still 1, prev_raguide still 0
        # Frame 3: move = 3-1-0 = 2, rapos=3 (correctly spans the gap!)
        # Frame 4: move = 4-3-0 = 1, rapos=4
        assert out == [0.0, 1.0, None, 3.0, 4.0]


class TestAOFrameAccumulates:
    def test_ao_frames_with_valid_data_accumulate(self):
        # AO frames (mount_kind="AO") with valid star data should NOT
        # be treated like DROP — they accumulate alongside Mount frames.
        # The AO's correction lives in ra_guide_px exactly like a Mount
        # pulse, so the recurrence backs out both sources of correction.
        samples = [
            _sample(0, 0.0, 0.0, kind="Mount", ra_guide=0.0),
            _sample(1, 1.0, 0.5, kind="AO", ra_guide=-0.5),
            _sample(2, 2.0, 0.0, kind="AO", ra_guide=0.0),
            _sample(3, 3.0, 1.0, kind="Mount", ra_guide=0.0),
        ]
        out = reconstruct_unguided_ra(_section(samples))
        # Frame 0: rapos=0
        # Frame 1: move = 0.5-0-0 = 0.5, rapos=0.5
        # Frame 2: move = 0-0.5-(-0.5) = 0, rapos=0.5
        # Frame 3: move = 1-0-0 = 1, rapos=1.5
        assert out == [0.0, 0.5, 0.5, 1.5]


class TestMissingRaGuide:
    def test_missing_ra_guide_falls_back_to_zero(self):
        # ra_guide_px=None should be treated as 0 (no correction).
        samples = [
            _sample(0, 0.0, 0.0, ra_guide=None),
            _sample(1, 1.0, 1.5, ra_guide=None),
            _sample(2, 2.0, 3.0, ra_guide=None),
        ]
        out = reconstruct_unguided_ra(_section(samples))
        # Frame 0: rapos=0
        # Frame 1: move = 1.5-0-0 = 1.5, rapos=1.5
        # Frame 2: move = 3-1.5-0 = 1.5, rapos=3
        assert out == [0.0, 1.5, 3.0]


class TestUndoCorrectionsFalse:
    def test_raw_position_anchored_at_zero(self):
        # undo_corrections=False keeps prev_raguide=0 always so the
        # recurrence emits a raw-position-anchored-at-zero trace.
        samples = [
            _sample(0, 0.0, 5.0, ra_guide=-1.0),
            _sample(1, 1.0, 6.0, ra_guide=-1.0),
            _sample(2, 2.0, 7.0, ra_guide=-1.0),
        ]
        out = reconstruct_unguided_ra(_section(samples), undo_corrections=False)
        # With undo_corrections=False, prev_raguide stays 0 every frame.
        # Frame 0: move = 5-0-0 = 5, rapos=5
        # Frame 1: move = 6-5-0 = 1, rapos=6
        # Frame 2: move = 7-6-0 = 1, rapos=7
        assert out == [5.0, 6.0, 7.0]


class TestMixedMountAODrop:
    def test_mixed_section_handles_all_three(self):
        # One section with Mount + AO + DROP frames interleaved. Mount
        # and AO accumulate; DROP gets None and doesn't update prev_*.
        samples = [
            _sample(0, 0.0, 0.0, kind="Mount", ra_guide=0.0),
            _sample(1, 1.0, 0.3, kind="AO", ra_guide=-0.3),
            _sample(2, 2.0, None, kind="Mount", err=7),
            _sample(3, 3.0, 0.5, kind="Mount", ra_guide=-0.5),
            _sample(4, 4.0, None, kind="AO", err=6),
            _sample(5, 5.0, 0.4, kind="AO", ra_guide=-0.4),
        ]
        out = reconstruct_unguided_ra(_section(samples))
        # Frame 0: rapos=0, prev=(0,0)
        # Frame 1 (AO valid): move = 0.3-0-0 = 0.3, rapos=0.3, prev=(0.3,-0.3)
        # Frame 2 (DROP): None; prev unchanged
        # Frame 3: move = 0.5-0.3-(-0.3) = 0.5, rapos=0.8, prev=(0.5,-0.5)
        # Frame 4 (DROP): None
        # Frame 5: move = 0.4-0.5-(-0.5) = 0.4, rapos=1.2, prev=(0.4,-0.4)
        assert out[0] == 0.0
        assert abs(out[1] - 0.3) < 1e-9
        assert out[2] is None
        assert abs(out[3] - 0.8) < 1e-9
        assert out[4] is None
        assert abs(out[5] - 1.2) < 1e-9


class TestEmptySection:
    def test_empty_samples_returns_empty_list(self):
        out = reconstruct_unguided_ra(_section([]))
        assert out == []


class TestAlignmentInvariant:
    def test_output_length_matches_samples_length(self):
        # Output is always 1:1 aligned with samples — confirms the
        # invariant that downstream consumers (TimeSeriesChart's
        # ``defined`` predicate, the FFT's filter step) rely on.
        samples = [
            _sample(0, 0.0, 0.0, ra_guide=0.0),
            _sample(1, 1.0, None, err=7),
            _sample(2, 2.0, 1.0, ra_guide=0.0),
        ]
        out = reconstruct_unguided_ra(_section(samples))
        assert len(out) == len(samples)
