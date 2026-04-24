"""Unit tests for the PHD2 guide-log parser."""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

import pytest

from nightcrate.services.phd2_models import Phd2DebugLogRejected
from nightcrate.services.phd2_parser import (
    _classify_info_event,
    _is_numeric_fragment,
    _recover_locale_row,
    parse_log,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "phd2"
SAMPLE_ASIAIR = FIXTURES / "sample_asiair.txt"
LOCALE_CORRUPTED = FIXTURES / "locale_corrupted.txt"
BACKWARD_TIMESTAMP = FIXTURES / "backward_timestamp.txt"
MISSING_PIXEL_SCALE = FIXTURES / "missing_pixel_scale.txt"
DEBUG_LOG = FIXTURES / "debug_log_rejected.txt"
MIXED_ARITY = FIXTURES / "mixed_arity.txt"


# ── Real ASIAIR log (trimmed) ────────────────────────────────────────────────


def test_parses_asiair_sample_with_blank_app_version():
    """ASIAIR-bundled logs omit the PHD2 app version — parser must tolerate."""
    log = parse_log(SAMPLE_ASIAIR)
    assert log.phd2_version is None
    assert log.log_version == "2.5"
    assert log.log_enabled_at == datetime(2026, 3, 7, 19, 33, 45)


def test_asiair_sample_splits_into_calibration_plus_guiding():
    log = parse_log(SAMPLE_ASIAIR)
    assert len(log.sections) == 2
    assert log.sections[0].kind == "calibration"
    assert log.sections[1].kind == "guiding"


def test_asiair_calibration_has_five_phases_with_derived_geometry():
    """Spec §3.4: calibration has West/East/Backlash/North/South phases,
    with angle + rate derived values on the `<Axis> calibration complete …`
    prose lines for the West and North axes."""
    log = parse_log(SAMPLE_ASIAIR)
    cal = log.sections[0]
    directions = [p.direction for p in cal.calibration_phases]
    assert directions == ["West", "East", "Backlash", "North", "South"]

    west = cal.calibration_phases[0]
    assert west.angle_deg == 85.1
    assert west.rate_px_per_sec == 1.238
    assert len(west.samples) == 12  # West,0 through West,11

    north = cal.calibration_phases[3]
    assert north.angle_deg == -6.3
    assert north.rate_px_per_sec == 3.254
    assert len(north.samples) == 5

    # East/Backlash/South don't carry derived geometry (only West/North do).
    for phase in (cal.calibration_phases[1], cal.calibration_phases[2], cal.calibration_phases[4]):
        assert phase.angle_deg is None
        assert phase.rate_px_per_sec is None


def test_asiair_guiding_header_fields_extracted():
    """Known header fields surface as typed attributes on `SectionHeader`."""
    log = parse_log(SAMPLE_ASIAIR)
    hdr = log.sections[1].header
    assert hdr.camera == "ZWO ASI178MM"
    assert hdr.mount == "ZWO000"
    assert hdr.pixel_scale_arcsec_per_px == 3.96
    assert hdr.binning == 2
    assert hdr.focal_length_mm == 250
    assert hdr.exposure_ms == 1000
    assert hdr.declination_deg == 69.0
    assert hdr.pier_side == "West"
    assert hdr.lock_position_x_px == 786.046
    assert hdr.lock_position_y_px == 723.641
    assert hdr.hfd_px == 2.52
    # Calibration geometry on the Mount line
    assert hdr.x_angle_deg == 85.1
    assert hdr.x_rate_px_per_sec == 1.238
    assert hdr.y_angle_deg == -6.3
    assert hdr.y_rate_px_per_sec == 3.254
    # ASIAIR leaves Equipment Profile empty.
    assert hdr.equipment_profile in (None, "")


def test_asiair_guiding_samples_parsed_with_correct_types():
    log = parse_log(SAMPLE_ASIAIR)
    guiding = log.sections[1]
    assert len(guiding.samples) == 13

    first = guiding.samples[0]
    assert first.frame == 1
    assert first.time_seconds == pytest.approx(1.202)
    assert first.mount_kind == "Mount"
    assert first.dx_px == pytest.approx(-0.307)
    assert first.ra_raw_px == pytest.approx(-0.698)
    assert first.ra_duration_ms == 500
    assert first.ra_direction == "E"
    assert first.dec_duration_ms == 0
    # No Dec pulse → no direction
    assert first.dec_direction is None


def test_asiair_info_events_classified():
    """Spec §3.5: INFO classifier uses string-contains (not prefix-exact)
    so SETTLING STATE CHANGE, Settling started / complete are both caught."""
    log = parse_log(SAMPLE_ASIAIR)
    events = log.sections[1].events
    kinds = [e.kind for e in events]
    assert "settle_begin" in kinds
    assert "settle_end" in kinds


# ── DROP frames + error descriptions ─────────────────────────────────────────


def test_drop_frames_have_none_not_zero():
    """Spec §11.4: DROP frames must have None in positional fields — coercing
    to zero silently corrupts RMS and creates phantom ideal-guiding periods."""
    log = parse_log(MIXED_ARITY)
    guiding = log.sections[0]
    drops = [s for s in guiding.samples if s.mount_kind == "DROP"]
    assert len(drops) == 2
    for d in drops:
        assert d.dx_px is None
        assert d.dy_px is None
        assert d.ra_raw_px is None
        assert d.dec_raw_px is None
        assert d.ra_duration_ms is None


def test_error_description_captured_verbatim_from_log():
    """Spec §11.2: no hardcoded error-code table. ErrorDescription string
    from the log itself is authoritative."""
    log = parse_log(MIXED_ARITY)
    drops = [s for s in log.sections[0].samples if s.mount_kind == "DROP"]
    assert drops[0].error_code == 6
    assert drops[0].error_description == "Star lost - mass changed"
    assert drops[1].error_code == 7
    assert drops[1].error_description == "No star found"


def test_mixed_arity_rows_parse_ok():
    """Spec §3.3: OK rows may be 18 cols, error rows 19 (declared + trailing
    quoted ErrorDescription). Same log can have both."""
    log = parse_log(MIXED_ARITY)
    samples = log.sections[0].samples
    ok_rows = [s for s in samples if s.error_code == 0]
    err_rows = [s for s in samples if s.error_code != 0]
    assert len(ok_rows) == 3
    assert len(err_rows) == 2
    assert all(s.error_description is None for s in ok_rows)
    assert all(s.error_description is not None for s in err_rows)


# ── Locale-decimal recovery ──────────────────────────────────────────────────


def test_locale_recovery_rebuilds_float_values_correctly():
    """Spec §3.7, §11.10: comma-decimal locale bug splits every float into
    two comma-separated tokens. Recovery rejoins them with `.`."""
    log = parse_log(LOCALE_CORRUPTED)
    section = log.sections[0]
    assert section.locale_recovery_applied is True

    samples = section.samples
    assert len(samples) == 2

    # "1,000" → 1.000; "0,100" → 0.100; etc.
    assert samples[0].time_seconds == 1.000
    assert samples[0].dx_px == pytest.approx(0.100)
    assert samples[0].dy_px == pytest.approx(0.200)
    assert samples[0].ra_raw_px == pytest.approx(0.150)
    assert samples[0].dec_raw_px == pytest.approx(0.180)
    assert samples[0].snr == pytest.approx(20.0)

    # Integer columns stay intact (Frame, RADuration, DECDuration, ErrorCode).
    assert samples[0].frame == 1
    assert samples[0].ra_duration_ms == 50
    assert samples[0].dec_duration_ms == 60
    assert samples[0].error_code == 0


def test_locale_recovery_preserves_sign():
    """Negative floats split as "-0", "100" → recovery must rebuild as -0.100."""
    log = parse_log(LOCALE_CORRUPTED)
    samples = log.sections[0].samples
    assert samples[1].dx_px == pytest.approx(-0.100)
    assert samples[1].ra_raw_px == pytest.approx(-0.150)


def test_locale_recovery_fires_warning():
    log = parse_log(LOCALE_CORRUPTED)
    codes = [w.code for w in log.warnings]
    assert "locale_recovery_applied" in codes


# ── Backward timestamps ──────────────────────────────────────────────────────


def test_sections_kept_in_file_order_not_timestamp_order():
    """Spec §3.8: PHD2 can emit sections whose start timestamps go backward
    (NTP resync mid-session). Parser must keep file order and warn."""
    log = parse_log(BACKWARD_TIMESTAMP)
    # File order: 21:00 first, 20:30 second. Timestamp order would reverse.
    assert log.sections[0].start_time == datetime(2026, 3, 7, 21, 0, 0)
    assert log.sections[1].start_time == datetime(2026, 3, 7, 20, 30, 0)

    codes = [w.code for w in log.warnings]
    assert "backward_timestamp_jump" in codes


# ── Missing pixel scale ──────────────────────────────────────────────────────


def test_missing_pixel_scale_fires_warning():
    log = parse_log(MISSING_PIXEL_SCALE)
    assert log.sections[0].header.pixel_scale_arcsec_per_px is None
    codes = [w.code for w in log.warnings]
    assert "missing_pixel_scale" in codes


# ── Debug log rejection ──────────────────────────────────────────────────────


def test_debug_log_raises_phd2_debug_log_rejected():
    """Spec §3.9: debug logs have a distinct header — reject in v0.22.0."""
    with pytest.raises(Phd2DebugLogRejected):
        parse_log(DEBUG_LOG)


def test_non_phd2_file_raises_value_error(tmp_path: Path):
    """Files that are neither guide nor debug logs must raise ValueError."""
    bogus = tmp_path / "not_phd2.txt"
    bogus.write_text("# random text file\nhello world\n")
    with pytest.raises(ValueError, match="not look like a PHD2 guide log"):
        parse_log(bogus)


def test_empty_file_raises_value_error(tmp_path: Path):
    empty = tmp_path / "empty.txt"
    empty.write_text("")
    with pytest.raises(ValueError, match="Empty file"):
        parse_log(empty)


# ── Stream input ─────────────────────────────────────────────────────────────


def test_parse_log_accepts_text_stream():
    """parse_log(Path) and parse_log(TextIO) must both work."""
    with SAMPLE_ASIAIR.open("r", encoding="utf-8") as f:
        log = parse_log(f)
    assert len(log.sections) == 2


def test_parse_log_from_in_memory_stream():
    """In-memory test path — enables fixture-free unit tests for edge cases."""
    text = (
        "PHD2 version 2.6.13, Log version 2.5. Log enabled at 2026-01-01 00:00:00\n"
        "\n"
        "Guiding Begins at 2026-01-01 00:01:00\n"
        "Pixel scale = 1.0 arc-sec/px, Binning = 1, Focal length = 200 mm\n"
        "Mount = TestMount\n"
        "Frame,Time,mount,dx,dy,RARawDistance,DECRawDistance,RAGuideDistance,"
        "DECGuideDistance,RADuration,RADirection,DECDuration,DECDirection,"
        "XStep,YStep,StarMass,SNR,ErrorCode\n"
        '1,1.0,"Mount",0.5,0.5,0.5,0.5,0.0,0.0,0,,0,,,,1000,20.0,0\n'
    )
    log = parse_log(io.StringIO(text))
    assert len(log.sections) == 1
    assert log.sections[0].samples[0].frame == 1


# ── Helpers ──────────────────────────────────────────────────────────────────


def test_is_numeric_fragment_accepts_signed_integers():
    assert _is_numeric_fragment("123")
    assert _is_numeric_fragment("-42")
    assert _is_numeric_fragment("+7")
    assert not _is_numeric_fragment("")
    assert not _is_numeric_fragment("abc")
    assert not _is_numeric_fragment("1.2")  # period means it's already intact


def test_recover_locale_row_roundtrip():
    """Given a known locale-corrupted token sequence, recovery must produce
    the expected per-column values."""
    header = [
        "Frame",
        "Time",
        "mount",
        "dx",
        "dy",
        "RARawDistance",
        "DECRawDistance",
        "RAGuideDistance",
        "DECGuideDistance",
        "RADuration",
        "RADirection",
        "DECDuration",
        "DECDirection",
        "XStep",
        "YStep",
        "StarMass",
        "SNR",
        "ErrorCode",
    ]
    # Original row: Frame=1, Time=2.5, mount=Mount, dx=0.1, dy=-0.2, ...
    # Locale-corrupted: commas replace decimal points.
    raw = '1,2,5,"Mount",0,1,-0,2,0,3,0,4,0,5,0,5,50,W,60,N,,,1000,20,0,0'
    recovered = _recover_locale_row(raw, header)
    # 18 columns mapped
    assert len(recovered) == 18
    assert recovered[0] == "1"  # Frame
    assert recovered[1] == "2.5"  # Time
    assert recovered[2] == "Mount"
    assert recovered[3] == "0.1"  # dx
    assert recovered[4] == "-0.2"  # dy


# ── Event classification ─────────────────────────────────────────────────────


def test_info_classifier_covers_spec_vocabulary():
    """Each string-contains pattern maps to a closed-vocabulary EventKind."""
    pairs = [
        ("SETTLING STATE CHANGE, Settling started", "settle_begin"),
        ("SETTLING STATE CHANGE, Settling complete", "settle_end"),
        ("DITHER by 5.0, -3.0, new lock pos = 100.0, 200.0", "dither"),
        ("SET LOCK POSITION, new lock pos = 100.0, 200.0", "lock_position_set"),
        ("MOVE LOCK POSITION, new lock pos = 100.0, 200.0", "lock_position_set"),
        ("Guiding Output Disabled", "guiding_disabled"),
        ("Guiding Output Enabled", "guiding_enabled"),
        ("Alert: Star lost", "alert"),
        ("Star selected at 120, 340", "star_selected"),
        ("something entirely new and unseen", "info"),
    ]
    for message, expected_kind in pairs:
        event = _classify_info_event(message)
        assert event.kind == expected_kind, (
            f"{message!r} classified as {event.kind}, expected {expected_kind}"
        )


def test_dither_event_extracts_fields():
    event = _classify_info_event("DITHER by 5.050, -3.863, new lock pos = 723.658, 602.937")
    assert event.kind == "dither"
    assert event.parsed_fields == {
        "dx": "5.050",
        "dy": "-3.863",
        "new_lock_x": "723.658",
        "new_lock_y": "602.937",
    }


def test_lock_position_event_extracts_coords():
    event = _classify_info_event("SET LOCK POSITION, new lock pos = 727.073, 597.574")
    assert event.kind == "lock_position_set"
    assert event.parsed_fields == {"x": "727.073", "y": "597.574"}
