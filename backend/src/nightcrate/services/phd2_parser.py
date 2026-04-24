"""PHD2 guide-log parser.

Entry point: `parse_log(source) -> ParsedLog`.

Design constraints (from the functional spec):

- **Parse-by-name, never-by-position**: column order is read per-section from
  the actual CSV header line. Future PHD2 versions adding or reordering
  columns must not break parsing.
- **Never silently coerce missing data**: empty fields resolve to `None`,
  never `0.0`. DROP frames have `None` in positional fields.
- **Tolerate format irregularities**: ASIAIR bundles omit the app version;
  header lines pack multiple settings with inconsistent separators; row
  arity can differ between OK (18 cols) and error (19 cols, with a trailing
  quoted ErrorDescription) rows inside the same section.
- **No hardcoded ErrorCode → string table**: spec §11.2 documents that the
  prior table was wrong. The log's own ErrorDescription is authoritative.

References:
- PHD2 Guide Log format: https://github.com/OpenPHDGuiding/phd2/wiki/PHD2GuideLog
- PHD2 Troubleshooting:  https://openphdguiding.org/man/Trouble_shooting.htm
"""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from pathlib import Path
from typing import TextIO

from nightcrate.services.phd2_models import (
    CalibrationDirection,
    CalibrationPhase,
    CalibrationSample,
    GuidingSample,
    LogEvent,
    LogSection,
    MountKind,
    ParsedLog,
    ParseWarning,
    Phd2DebugLogRejected,
    SectionHeader,
    SectionKind,
)

# ── File-level patterns ────────────────────────────────────────────────────────

_RE_FIRST_LINE = re.compile(
    r"^PHD2 version\s*(?P<app>[^,]*?)\s*,\s*"
    r"Log version\s+(?P<log>\S+)\.\s*"
    r"Log enabled at\s+(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"
)
_RE_CAL_BEGIN = re.compile(r"^Calibration Begins at\s+(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
_RE_GUIDE_BEGIN = re.compile(r"^Guiding Begins at\s+(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
_RE_GUIDE_END = re.compile(r"^Guiding Ends at\s+(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
_RE_CAL_END = re.compile(r"^Calibration complete, mount\s*=\s*(?P<mount>[^.]+)\.")
_RE_PHASE_COMPLETE = re.compile(
    r"^(?P<axis>West|North) calibration complete\.\s*"
    r"Angle\s*=\s*(?P<angle>[-\d.]+)\s*deg,\s*"
    r"Rate\s*=\s*(?P<rate>[-\d.]+)\s*px/sec"
    r"(?:,\s*Parity\s*=\s*(?P<parity>\S+))?"
)
_RE_INFO = re.compile(r"^INFO:\s*(?P<message>.*)$")

# Module-level tuple constant for the narrow except clause below —
# sidesteps the py314 ruff-format bug documented in CLAUDE.md Gotchas
# where ruff strips the parens off `except (A, B):`.
_CAL_ROW_ERRORS: tuple[type[BaseException], ...] = (TypeError, ValueError)

# ── Header key patterns ────────────────────────────────────────────────────────
#
# One regex per typed field. Each is anchored so overlapping prefixes don't
# collide (e.g. `Dec = …` vs `Dec Guide Speed = …`). Unknown `key = value`
# text falls through to `freeform_keys` via the generic sweep at the bottom.

_HEADER_FLOAT = r"([-\d.]+)"
_HEADER_INT = r"(-?\d+)"

_RE_HDR_CAMERA = re.compile(r"Camera\s*=\s*([^,\n]+)")
_RE_HDR_MOUNT = re.compile(r"(?<!\w)Mount\s*=\s*([^,\n]+?)(?=,|$)")
_RE_HDR_AO = re.compile(r"(?<!\w)AO\s*=\s*([^,\n]+?)(?=,|$)")
_RE_HDR_FOCAL_LENGTH = re.compile(rf"Focal length\s*=\s*{_HEADER_INT}\s*mm")
_RE_HDR_BINNING = re.compile(rf"Binning\s*=\s*{_HEADER_INT}")
_RE_HDR_PIXEL_SCALE = re.compile(rf"Pixel scale\s*=\s*{_HEADER_FLOAT}\s*arc-sec/px")
_RE_HDR_EXPOSURE = re.compile(rf"Exposure\s*=\s*{_HEADER_INT}\s*ms")
_RE_HDR_DEC = re.compile(rf"(?<!\w)Dec\s*=\s*{_HEADER_FLOAT}\s*deg")
_RE_HDR_HA = re.compile(rf"Hour angle\s*=\s*{_HEADER_FLOAT}\s*hr")
_RE_HDR_PIER_SIDE = re.compile(r"Pier side\s*=\s*(\w+)")
_RE_HDR_ROTATOR = re.compile(r"Rotator pos\s*=\s*([^,\n]+?)(?=,|$)")
_RE_HDR_LOCK_POS = re.compile(rf"Lock position\s*=\s*{_HEADER_FLOAT}\s*,\s*{_HEADER_FLOAT}")
_RE_HDR_STAR_POS = re.compile(rf"Star position\s*=\s*{_HEADER_FLOAT}\s*,\s*{_HEADER_FLOAT}")
_RE_HDR_HFD = re.compile(rf"HFD\s*=\s*{_HEADER_FLOAT}\s*px")
_RE_HDR_SEARCH_REGION = re.compile(rf"Search region\s*=\s*{_HEADER_FLOAT}\s*px")
_RE_HDR_STAR_MASS_TOL = re.compile(rf"Star mass tolerance\s*=\s*{_HEADER_FLOAT}\s*%")
_RE_HDR_X_GUIDE_ALGO = re.compile(r"X guide algorithm\s*=\s*([^,\n]+?)(?=,\s*\w|$)")
_RE_HDR_Y_GUIDE_ALGO = re.compile(r"Y guide algorithm\s*=\s*([^,\n]+?)(?=,\s*\w|$)")
_RE_HDR_DEC_GUIDE_MODE = re.compile(r"DEC guide mode\s*=\s*(\w+)")
_RE_HDR_BACKLASH_COMP = re.compile(r"Backlash comp\s*=\s*(enabled|disabled)")
_RE_HDR_BACKLASH_PULSE = re.compile(rf"(?<!\w)pulse\s*=\s*{_HEADER_INT}\s*ms")
_RE_HDR_MAX_RA = re.compile(rf"Max RA duration\s*=\s*{_HEADER_INT}")
_RE_HDR_MAX_DEC = re.compile(rf"Max DEC duration\s*=\s*{_HEADER_INT}")
_RE_HDR_RA_GUIDE_SPEED = re.compile(r"RA Guide Speed\s*=\s*([^,\n]+?)(?=,|$)")
_RE_HDR_DEC_GUIDE_SPEED = re.compile(r"Dec Guide Speed\s*=\s*([^,\n]+?)(?=,|$)")
_RE_HDR_X_ANGLE = re.compile(rf"xAngle\s*=\s*{_HEADER_FLOAT}")
_RE_HDR_X_RATE = re.compile(rf"xRate\s*=\s*{_HEADER_FLOAT}")
_RE_HDR_Y_ANGLE = re.compile(rf"yAngle\s*=\s*{_HEADER_FLOAT}")
_RE_HDR_Y_RATE = re.compile(rf"yRate\s*=\s*{_HEADER_FLOAT}")
_RE_HDR_PARITY = re.compile(r"(?<!\w)parity\s*=\s*(\S+?)(?=,|\s|$)")
_RE_HDR_CAL_STEP = re.compile(rf"Calibration [Ss]tep\s*=\s*{_HEADER_INT}\s*ms")
_RE_HDR_ORTHO = re.compile(r"Assume orthogonal axes\s*=\s*(yes|no)")
_RE_HDR_CAL_DEC = re.compile(rf"Cal Dec\s*=\s*{_HEADER_FLOAT}")
_RE_HDR_LAST_CAL = re.compile(r"Last Cal Issue\s*=\s*([^,\n]+?)(?=,|$)")
_RE_HDR_DITHER = re.compile(r"Dither\s*=\s*([^,\n]+?)(?=,|$)")
_RE_HDR_DITHER_SCALE = re.compile(rf"Dither scale\s*=\s*{_HEADER_FLOAT}")
_RE_HDR_NOISE_REDUCTION = re.compile(r"Image noise reduction\s*=\s*([^,\n]+?)(?=,|$)")
# Use [^\S\n] (whitespace minus newline) between `=` and the value so we
# don't accidentally eat the newline and consume the following line.
_RE_HDR_EQUIPMENT_PROFILE = re.compile(
    r"Equipment Profile[^\S\n]*=[^\S\n]*([^\n]*?)$", re.MULTILINE
)

# Generic `word = value` sweep for the freeform bucket — deliberately
# permissive since we subtract recognized keys after the known-field pass.
_RE_GENERIC_KV = re.compile(r"(?P<key>[A-Za-z][A-Za-z0-9_ ]*?)\s*=\s*(?P<val>[^,\n]*)")

_HEADER_KNOWN_PREFIXES = {
    "Camera",
    "Mount",
    "AO",
    "Focal length",
    "Binning",
    "Pixel scale",
    "Exposure",
    "Dec",
    "Hour angle",
    "Pier side",
    "Rotator pos",
    "Lock position",
    "Star position",
    "HFD",
    "Search region",
    "Star mass tolerance",
    "X guide algorithm",
    "Y guide algorithm",
    "DEC guide mode",
    "Backlash comp",
    "pulse",
    "Max RA duration",
    "Max DEC duration",
    "RA Guide Speed",
    "Dec Guide Speed",
    "xAngle",
    "xRate",
    "yAngle",
    "yRate",
    "parity",
    "Calibration Step",
    "Calibration step",
    "Assume orthogonal axes",
    "Cal Dec",
    "Last Cal Issue",
    "Dither",
    "Dither scale",
    "Image noise reduction",
    "Equipment Profile",
}

# ── INFO event classification ─────────────────────────────────────────────────

_IC = re.IGNORECASE
_EVENT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"SETTLING STATE CHANGE,\s*Settling started", _IC), "settle_begin"),
    (re.compile(r"SETTLING STATE CHANGE,\s*Settling complete", _IC), "settle_end"),
    (re.compile(r"DITHER by", _IC), "dither"),
    (re.compile(r"SET LOCK POSITION|MOVE LOCK POSITION", _IC), "lock_position_set"),
    (re.compile(r"SERVER received SET_PAUSED.*UNPAUSED|received RESUMED", _IC), "server_resume"),
    (re.compile(r"SERVER received SET_PAUSED|Server received PAUSED", _IC), "server_pause"),
    (re.compile(r"Star selected at", _IC), "star_selected"),
    (re.compile(r"Alert:", _IC), "alert"),
    (re.compile(r"Guiding Output Enabled", _IC), "guiding_enabled"),
    (re.compile(r"Guiding Output Disabled", _IC), "guiding_disabled"),
]

_RE_DITHER_FIELDS = re.compile(
    r"DITHER by\s*(?P<dx>[-\d.]+)\s*,\s*(?P<dy>[-\d.]+)"
    r"(?:\s*,\s*new lock pos\s*=\s*(?P<lx>[-\d.]+)\s*,\s*(?P<ly>[-\d.]+))?"
)
_RE_LOCK_POS_FIELDS = re.compile(
    r"LOCK POSITION,\s*new lock pos\s*=\s*(?P<x>[-\d.]+)\s*,\s*(?P<y>[-\d.]+)"
)

# ── Entry point ────────────────────────────────────────────────────────────────


def parse_log(source: Path | TextIO) -> ParsedLog:
    """Parse a PHD2 guide log into a structured ParsedLog.

    Accepts a filesystem path or an open text stream. The stream path enables
    in-memory tests without fixture files on disk.

    Raises:
        Phd2DebugLogRejected: when the file is a PHD2 debug log, not a guide
            log. Debug logs have a different header and aren't supported until
            the v0.30.0+ roadmap.
        ValueError: when the first non-blank line is neither of those — the
            file isn't a PHD2 log at all.
    """
    if isinstance(source, Path):
        text = source.read_text(encoding="utf-8", errors="replace")
        file_path = str(source)
    else:
        text = source.read()
        file_path = getattr(source, "name", "<stream>")

    lines = text.splitlines()
    first_line = _first_non_blank(lines)
    if first_line is None:
        raise ValueError("Empty file — not a PHD2 guide log")

    if first_line.startswith("PHD2 debug log") or "DebugLog" in first_line:
        raise Phd2DebugLogRejected(
            "Debug logs are not supported in v0.22.0 — please provide a "
            "PHD2 guide log (filename pattern PHD2_GuideLog_*.txt)."
        )

    if not first_line.startswith("PHD2 version"):
        raise ValueError(f"First line does not look like a PHD2 guide log: {first_line[:80]!r}")

    phd2_version, log_version, log_enabled_at = _parse_first_line(first_line)

    warnings: list[ParseWarning] = []
    sections = _parse_sections(lines, warnings)

    return ParsedLog(
        file_path=file_path,
        phd2_version=phd2_version or None,
        log_version=log_version,
        log_enabled_at=log_enabled_at,
        sections=sections,
        warnings=warnings,
    )


# ── First-line + section splitting ────────────────────────────────────────────


def _first_non_blank(lines: list[str]) -> str | None:
    for line in lines:
        if line.strip():
            return line
    return None


def _parse_first_line(line: str) -> tuple[str, str, datetime]:
    """Extract (app_version, log_version, log_enabled_at) from the first line.

    Tolerates an empty app version (ASIAIR-bundled PHD2 ships without one —
    the line reads ``PHD2 version, Log version 2.5. Log enabled at …``).
    """
    m = _RE_FIRST_LINE.match(line)
    if not m:
        raise ValueError(f"Unparseable first line: {line!r}")
    return (
        m.group("app").strip(),
        m.group("log"),
        _parse_local_timestamp(m.group("ts")),
    )


def _parse_local_timestamp(raw: str) -> datetime:
    """Parse a PHD2 timestamp in the format ``YYYY-MM-DD HH:MM:SS``.

    Treats the timestamp as naive local time (PHD2 does not emit timezone
    information). Downstream code preserves the naive datetime; conversion is
    a UI concern.
    """
    return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")


def _parse_sections(lines: list[str], warnings: list[ParseWarning]) -> list[LogSection]:
    starts: list[tuple[int, SectionKind, datetime]] = []
    for i, line in enumerate(lines):
        if m := _RE_CAL_BEGIN.match(line):
            starts.append((i, "calibration", _parse_local_timestamp(m.group("ts"))))
        elif m := _RE_GUIDE_BEGIN.match(line):
            starts.append((i, "guiding", _parse_local_timestamp(m.group("ts"))))

    sections: list[LogSection] = []
    prev_start: datetime | None = None
    for section_idx, (start_line, kind, start_ts) in enumerate(starts):
        next_start = starts[section_idx + 1][0] if section_idx + 1 < len(starts) else len(lines)
        section_lines = lines[start_line + 1 : next_start]

        if prev_start is not None and start_ts < prev_start:
            warnings.append(
                ParseWarning(
                    code="backward_timestamp_jump",
                    message=(
                        f"Section {section_idx} starts at {start_ts.isoformat()}, "
                        f"earlier than previous section at {prev_start.isoformat()}. "
                        "Sections are kept in file order."
                    ),
                    section_index=section_idx,
                )
            )
        prev_start = start_ts

        section = _parse_section(
            kind=kind,
            index=section_idx,
            start_time=start_ts,
            body_lines=section_lines,
            warnings=warnings,
        )
        sections.append(section)

    return sections


def _parse_section(
    *,
    kind: SectionKind,
    index: int,
    start_time: datetime,
    body_lines: list[str],
    warnings: list[ParseWarning],
) -> LogSection:
    """Parse a single section's body: header block, CSV, events, end marker."""
    # Find the CSV-header line — for calibration it starts with "Direction,",
    # for guiding with "Frame,". Everything before is the settings block.
    csv_header_idx: int | None = None
    for i, line in enumerate(body_lines):
        if kind == "guiding" and line.startswith("Frame,"):
            csv_header_idx = i
            break
        if kind == "calibration" and line.startswith("Direction,"):
            csv_header_idx = i
            break

    if csv_header_idx is None:
        # No CSV data — degenerate section. Keep what we have and warn.
        warnings.append(
            ParseWarning(
                code="no_csv_header",
                message=f"Section {index} ({kind}) has no CSV header — no samples parsed.",
                section_index=index,
            )
        )
        header = _parse_header_block(body_lines, warnings, index)
        return LogSection(
            kind=kind,
            index=index,
            start_time=start_time,
            end_time=None,
            header=header,
            samples=[],
            calibration_phases=[],
            events=[],
            locale_recovery_applied=False,
        )

    header_lines = body_lines[:csv_header_idx]
    csv_header_line = body_lines[csv_header_idx]
    data_lines = body_lines[csv_header_idx + 1 :]

    header = _parse_header_block(header_lines, warnings, index)
    if kind == "guiding" and header.pixel_scale_arcsec_per_px is None:
        warnings.append(
            ParseWarning(
                code="missing_pixel_scale",
                message=(
                    f"Section {index} (guiding) has no Pixel scale in header — "
                    "arcsec values cannot be computed."
                ),
                section_index=index,
            )
        )

    end_time: datetime | None = None
    events: list[LogEvent] = []
    sample_lines: list[str] = []
    # Running anchor for INFO events. PHD2 emits INFO lines inline with
    # data rows; an event's wall-clock is "sometime between the last
    # data row before it and the next one". We anchor each event to the
    # preceding sample's Time column (or 0.0 when no sample has arrived
    # yet — e.g., "Settling started" right after section begin).
    last_sample_time: float | None = 0.0 if kind == "guiding" else None

    for line in data_lines:
        if not line.strip():
            continue
        if m := _RE_GUIDE_END.match(line):
            end_time = _parse_local_timestamp(m.group("ts"))
            continue
        if _RE_CAL_END.match(line):
            # `Calibration complete, mount = ZWO000.` closes the section.
            continue
        if _RE_PHASE_COMPLETE.match(line):
            # Handled inside _parse_calibration_body; skip here.
            sample_lines.append(line)
            continue
        if m := _RE_INFO.match(line):
            events.append(_classify_info_event(m.group("message"), time_seconds=last_sample_time))
            continue
        # Data row — peek at the Time column to advance the anchor so
        # subsequent INFO lines are dated correctly.
        if kind == "guiding":
            peeked = _peek_sample_time_seconds(line)
            if peeked is not None:
                last_sample_time = peeked
        sample_lines.append(line)

    samples: list[GuidingSample] = []
    calibration_phases: list[CalibrationPhase] = []
    locale_applied = False
    error_count = 0

    if kind == "guiding":
        samples, locale_applied, error_count = _parse_guiding_csv(
            header_line=csv_header_line,
            rows=sample_lines,
            section_index=index,
            warnings=warnings,
        )
    else:
        calibration_phases = _parse_calibration_body(
            header_line=csv_header_line,
            rows=sample_lines,
            section_index=index,
            warnings=warnings,
        )

    if error_count > 0:
        warnings.append(
            ParseWarning(
                code="frames_with_errors",
                message=(
                    f"Section {index} ({kind}) has {error_count} frame(s) with "
                    "ErrorCode != 0. Switch to the Data tab to see which frames errored."
                ),
                section_index=index,
            )
        )

    return LogSection(
        kind=kind,
        index=index,
        start_time=start_time,
        end_time=end_time,
        header=header,
        samples=samples,
        calibration_phases=calibration_phases,
        events=events,
        locale_recovery_applied=locale_applied,
    )


# ── Header block parsing ──────────────────────────────────────────────────────


def _parse_header_block(
    lines: list[str],
    warnings: list[ParseWarning],
    section_index: int,
) -> SectionHeader:
    """Parse the settings block above the CSV table into a SectionHeader.

    PHD2 packs multiple `key = value` pairs onto single lines with
    inconsistent separators (commas, bare spaces, missing commas before some
    keys). Known-field regexes pick out typed values; unrecognized pairs
    fall through to `freeform_keys`.
    """
    text = "\n".join(lines)

    hdr_kwargs: dict[str, object] = {}

    def _first_float(pattern: re.Pattern[str]) -> float | None:
        if m := pattern.search(text):
            return float(m.group(1))
        return None

    def _first_int(pattern: re.Pattern[str]) -> int | None:
        if m := pattern.search(text):
            return int(m.group(1))
        return None

    def _first_str(pattern: re.Pattern[str]) -> str | None:
        if m := pattern.search(text):
            return m.group(1).strip()
        return None

    # Equipment
    hdr_kwargs["camera"] = _first_str(_RE_HDR_CAMERA)
    hdr_kwargs["mount"] = _first_str(_RE_HDR_MOUNT)
    hdr_kwargs["ao"] = _first_str(_RE_HDR_AO)
    hdr_kwargs["focal_length_mm"] = _first_float(_RE_HDR_FOCAL_LENGTH)
    hdr_kwargs["binning"] = _first_int(_RE_HDR_BINNING)
    hdr_kwargs["pixel_scale_arcsec_per_px"] = _first_float(_RE_HDR_PIXEL_SCALE)
    hdr_kwargs["exposure_ms"] = _first_int(_RE_HDR_EXPOSURE)

    # Sky geometry
    hdr_kwargs["declination_deg"] = _first_float(_RE_HDR_DEC)
    hdr_kwargs["hour_angle_hr"] = _first_float(_RE_HDR_HA)
    hdr_kwargs["pier_side"] = _first_str(_RE_HDR_PIER_SIDE)
    hdr_kwargs["rotator_position"] = _first_str(_RE_HDR_ROTATOR)

    # Lock / star
    if m := _RE_HDR_LOCK_POS.search(text):
        hdr_kwargs["lock_position_x_px"] = float(m.group(1))
        hdr_kwargs["lock_position_y_px"] = float(m.group(2))
    if m := _RE_HDR_STAR_POS.search(text):
        hdr_kwargs["star_position_x_px"] = float(m.group(1))
        hdr_kwargs["star_position_y_px"] = float(m.group(2))
    hdr_kwargs["hfd_px"] = _first_float(_RE_HDR_HFD)
    hdr_kwargs["search_region_px"] = _first_float(_RE_HDR_SEARCH_REGION)
    hdr_kwargs["star_mass_tolerance_pct"] = _first_float(_RE_HDR_STAR_MASS_TOL)

    # Algorithms
    hdr_kwargs["x_guide_algorithm"] = _first_str(_RE_HDR_X_GUIDE_ALGO)
    hdr_kwargs["y_guide_algorithm"] = _first_str(_RE_HDR_Y_GUIDE_ALGO)
    hdr_kwargs["dec_guide_mode"] = _first_str(_RE_HDR_DEC_GUIDE_MODE)
    if m := _RE_HDR_BACKLASH_COMP.search(text):
        hdr_kwargs["backlash_comp_enabled"] = m.group(1) == "enabled"
    hdr_kwargs["backlash_pulse_ms"] = _first_int(_RE_HDR_BACKLASH_PULSE)
    hdr_kwargs["max_ra_duration_ms"] = _first_int(_RE_HDR_MAX_RA)
    hdr_kwargs["max_dec_duration_ms"] = _first_int(_RE_HDR_MAX_DEC)
    hdr_kwargs["ra_guide_speed"] = _first_str(_RE_HDR_RA_GUIDE_SPEED)
    hdr_kwargs["dec_guide_speed"] = _first_str(_RE_HDR_DEC_GUIDE_SPEED)

    # Calibration geometry
    hdr_kwargs["x_angle_deg"] = _first_float(_RE_HDR_X_ANGLE)
    hdr_kwargs["x_rate_px_per_sec"] = _first_float(_RE_HDR_X_RATE)
    hdr_kwargs["y_angle_deg"] = _first_float(_RE_HDR_Y_ANGLE)
    hdr_kwargs["y_rate_px_per_sec"] = _first_float(_RE_HDR_Y_RATE)
    hdr_kwargs["parity"] = _first_str(_RE_HDR_PARITY)
    hdr_kwargs["calibration_step_ms"] = _first_int(_RE_HDR_CAL_STEP)
    if m := _RE_HDR_ORTHO.search(text):
        hdr_kwargs["assume_orthogonal_axes"] = m.group(1) == "yes"
    hdr_kwargs["cal_declination_deg"] = _first_float(_RE_HDR_CAL_DEC)
    hdr_kwargs["last_cal_issue"] = _first_str(_RE_HDR_LAST_CAL)

    # Dither + image noise reduction
    hdr_kwargs["dither_description"] = _first_str(_RE_HDR_DITHER)
    hdr_kwargs["dither_scale"] = _first_float(_RE_HDR_DITHER_SCALE)
    hdr_kwargs["image_noise_reduction"] = _first_str(_RE_HDR_NOISE_REDUCTION)
    hdr_kwargs["equipment_profile"] = _first_str(_RE_HDR_EQUIPMENT_PROFILE)

    # Freeform sweep — pick up any `key = value` we didn't explicitly handle.
    freeform: dict[str, str] = {}
    for m in _RE_GENERIC_KV.finditer(text):
        key = m.group("key").strip()
        val = m.group("val").strip()
        if key in _HEADER_KNOWN_PREFIXES:
            continue
        if not key:
            continue
        # Skip single-letter keys that came from false-positive fragments.
        if len(key) <= 1:
            continue
        # First occurrence wins — don't overwrite on duplicates.
        freeform.setdefault(key, val)

    hdr_kwargs["freeform_keys"] = freeform

    try:
        return SectionHeader(**hdr_kwargs)
    except ValueError as exc:
        warnings.append(
            ParseWarning(
                code="header_validation_error",
                message=f"Section {section_index} header failed validation: {exc}",
                section_index=section_index,
            )
        )
        return SectionHeader(freeform_keys=freeform)


# ── Guiding CSV parsing ────────────────────────────────────────────────────────


# Columns that represent floats in the log. Only these get joined back
# during locale recovery — integer columns stay as a single token even in
# comma-decimal locales because the bug only splits floats at their decimal
# point. StarMass is an integer in PHD2's output (e.g. 1045, 1197), not a
# float, so it's excluded. Frame, RADuration, DECDuration, and ErrorCode
# are always integers.
_FLOAT_GUIDING_COLUMNS = {
    "Time",
    "dx",
    "dy",
    "RARawDistance",
    "DECRawDistance",
    "RAGuideDistance",
    "DECGuideDistance",
    "XStep",
    "YStep",
    "SNR",
}


def _parse_guiding_csv(
    *,
    header_line: str,
    rows: list[str],
    section_index: int,
    warnings: list[ParseWarning],
) -> tuple[list[GuidingSample], bool, int]:
    """Parse a guiding section's CSV table.

    Returns ``(samples, locale_recovery_applied, error_count)``.
    """
    column_names = [c.strip() for c in header_line.split(",")]

    # Locale-decimal recovery detection (spec §3.7, §11.10). If the first
    # data row has markedly more tokens than the header declares, fields
    # were split by a comma-decimal locale bug.
    first_data = next((r for r in rows if r.strip()), None)
    locale_applied = False
    if first_data is not None:
        token_count = len(_tokenize_csv_line(first_data))
        declared = len(column_names)
        if token_count > declared * 1.3:
            locale_applied = True
            warnings.append(
                ParseWarning(
                    code="locale_recovery_applied",
                    message=(
                        f"Section {section_index}: decimal-separator recovery "
                        f"applied ({token_count} tokens vs {declared} header "
                        "columns). Verify values look correct."
                    ),
                    section_index=section_index,
                )
            )

    samples: list[GuidingSample] = []
    error_count = 0

    for raw in rows:
        if not raw.strip():
            continue
        if raw.startswith("INFO:"):
            continue  # handled upstream

        tokens = (
            _recover_locale_row(raw, column_names) if locale_applied else _tokenize_csv_line(raw)
        )
        if len(tokens) < len(column_names):
            warnings.append(
                ParseWarning(
                    code="short_row",
                    message=(
                        f"Section {section_index}: row has {len(tokens)} tokens, "
                        f"expected {len(column_names)}. Skipping."
                    ),
                    section_index=section_index,
                )
            )
            continue

        sample = _row_to_guiding_sample(tokens, column_names)
        if sample is None:
            continue
        if sample.error_code != 0:
            error_count += 1
        samples.append(sample)

    return samples, locale_applied, error_count


def _tokenize_csv_line(line: str) -> list[str]:
    """Split a CSV row honoring quoted fields (so commas inside quotes stay)."""
    reader = csv.reader(io.StringIO(line), quotechar='"', skipinitialspace=False)
    try:
        return next(reader)
    except StopIteration:
        return []


def _recover_locale_row(raw: str, column_names: list[str]) -> list[str]:
    """Rebuild a locale-corrupted row's field values.

    In comma-decimal locales (IT/DE/FR) PHD2 historically wrote floats with
    comma decimals AND used comma as the CSV separator (see spec §3.7 and
    §11.10). Every numeric field becomes two adjacent comma-separated
    tokens; joining them with ``.`` recovers the original float. The quoted
    ``mount`` column is the positional anchor — its presence is reliable.
    """
    tokens = _tokenize_csv_line(raw)
    recovered: list[str] = []
    token_idx = 0
    for col in column_names:
        if token_idx >= len(tokens):
            break
        current = tokens[token_idx]
        next_token = tokens[token_idx + 1] if token_idx + 1 < len(tokens) else ""

        is_float_col = col in _FLOAT_GUIDING_COLUMNS
        both_numeric = _is_numeric_fragment(current) and _is_numeric_fragment(next_token)
        if is_float_col and both_numeric:
            recovered.append(f"{current}.{next_token}")
            token_idx += 2
        else:
            recovered.append(current)
            token_idx += 1

    # Trailing ErrorDescription (quoted string) may remain.
    if token_idx < len(tokens):
        recovered.append(tokens[token_idx])
    return recovered


def _is_numeric_fragment(s: str) -> bool:
    """True if ``s`` parses as a signed integer (the fragment side of a corrupted float)."""
    if not s:
        return False
    if s[0] in "+-":
        s = s[1:]
    return s.isdigit()


def _row_to_guiding_sample(tokens: list[str], column_names: list[str]) -> GuidingSample | None:
    """Map a row to a GuidingSample by column name, tolerating optional ErrorDescription."""
    # Row arity may equal declared count OR declared + 1 (trailing quoted
    # ErrorDescription) — spec §11.1. Accept both; longer rows have the
    # extra token treated as ErrorDescription regardless of whether the
    # header declared it.
    name_to_value: dict[str, str] = {}
    for i, col in enumerate(column_names):
        if i < len(tokens):
            name_to_value[col] = tokens[i]

    # If there's a trailing token past the declared columns, treat it as
    # ErrorDescription (unless the header already declared that column).
    if len(tokens) > len(column_names):
        extra = tokens[len(column_names)]
        if "ErrorDescription" not in name_to_value:
            name_to_value["ErrorDescription"] = extra

    def _raw(col: str) -> str:
        return name_to_value.get(col, "").strip()

    def _f(col: str) -> float | None:
        v = _raw(col)
        if not v:
            return None
        try:
            return float(v)
        except ValueError:
            return None

    def _i(col: str) -> int | None:
        v = _raw(col)
        if not v:
            return None
        try:
            return int(v)
        except ValueError:
            return None

    def _s(col: str) -> str | None:
        return _raw(col).strip('"') or None

    frame_num = _i("Frame")
    time_s = _f("Time")
    if frame_num is None or time_s is None:
        return None  # not a data row

    mount_raw = _s("mount")
    mount_kind: MountKind = mount_raw if mount_raw in ("Mount", "AO", "DROP") else "Mount"  # type: ignore[assignment]

    ra_dir_raw = _s("RADirection")
    dec_dir_raw = _s("DECDirection")

    return GuidingSample(
        frame=frame_num,
        time_seconds=time_s,
        mount_kind=mount_kind,
        dx_px=_f("dx"),
        dy_px=_f("dy"),
        ra_raw_px=_f("RARawDistance"),
        dec_raw_px=_f("DECRawDistance"),
        ra_guide_px=_f("RAGuideDistance"),
        dec_guide_px=_f("DECGuideDistance"),
        ra_duration_ms=_i("RADuration"),
        dec_duration_ms=_i("DECDuration"),
        ra_direction=ra_dir_raw if ra_dir_raw in ("W", "E") else None,  # type: ignore[arg-type]
        dec_direction=dec_dir_raw if dec_dir_raw in ("N", "S") else None,  # type: ignore[arg-type]
        x_step=_f("XStep"),
        y_step=_f("YStep"),
        star_mass=_f("StarMass"),
        snr=_f("SNR"),
        error_code=_i("ErrorCode") or 0,
        error_description=_s("ErrorDescription"),
    )


# ── Calibration CSV parsing ────────────────────────────────────────────────────


def _parse_calibration_body(
    *,
    header_line: str,
    rows: list[str],
    section_index: int,
    warnings: list[ParseWarning],
) -> list[CalibrationPhase]:
    """Parse a calibration section into five named phases.

    The body is a sequence of data rows interleaved with two prose completion
    lines: ``West calibration complete. Angle = …, Rate = …, Parity = …`` and
    ``North calibration complete. Angle = …, Rate = …, Parity = …``. These
    lines carry the derived calibration geometry and mark phase boundaries.
    """
    column_names = [c.strip() for c in header_line.split(",")]
    phase_samples: dict[CalibrationDirection, list[CalibrationSample]] = {
        "West": [],
        "East": [],
        "Backlash": [],
        "North": [],
        "South": [],
    }
    phase_meta: dict[str, tuple[float, float, str | None]] = {}

    for raw in rows:
        if not raw.strip():
            continue
        if m := _RE_PHASE_COMPLETE.match(raw):
            phase_meta[m.group("axis")] = (
                float(m.group("angle")),
                float(m.group("rate")),
                m.group("parity"),
            )
            continue
        tokens = _tokenize_csv_line(raw)
        if len(tokens) < len(column_names):
            continue
        mapped = dict(zip(column_names, tokens, strict=False))
        direction = mapped.get("Direction", "").strip()
        if direction not in phase_samples:
            continue

        try:
            sample = CalibrationSample(
                direction=direction,  # type: ignore[arg-type]
                step=int(mapped.get("Step", "0") or 0),
                dx_px=float(mapped.get("dx", "0") or 0),
                dy_px=float(mapped.get("dy", "0") or 0),
                x_px=float(mapped.get("x", "0") or 0),
                y_px=float(mapped.get("y", "0") or 0),
                distance_px=float(mapped.get("Dist", "0") or 0),
            )
        except _CAL_ROW_ERRORS:
            warnings.append(
                ParseWarning(
                    code="bad_calibration_row",
                    message=f"Section {section_index}: couldn't parse calibration row {raw!r}",
                    section_index=section_index,
                )
            )
            continue
        phase_samples[direction].append(sample)

    west_meta = phase_meta.get("West")
    north_meta = phase_meta.get("North")
    return [
        CalibrationPhase(
            direction="West",
            samples=phase_samples["West"],
            angle_deg=west_meta[0] if west_meta else None,
            rate_px_per_sec=west_meta[1] if west_meta else None,
            parity=west_meta[2] if west_meta else None,
        ),
        CalibrationPhase(direction="East", samples=phase_samples["East"]),
        CalibrationPhase(direction="Backlash", samples=phase_samples["Backlash"]),
        CalibrationPhase(
            direction="North",
            samples=phase_samples["North"],
            angle_deg=north_meta[0] if north_meta else None,
            rate_px_per_sec=north_meta[1] if north_meta else None,
            parity=north_meta[2] if north_meta else None,
        ),
        CalibrationPhase(direction="South", samples=phase_samples["South"]),
    ]


# ── INFO event classification ─────────────────────────────────────────────────


def _classify_info_event(
    raw_message: str,
    time_seconds: float | None = None,
) -> LogEvent:
    """Map an INFO line to a closed-vocabulary `EventKind`.

    ``time_seconds`` is the wall-clock anchor — the Time column of the
    most-recent sample line before this INFO line. Passed in by the
    section walker so event ordering + timing reflects the log's real
    interleaving.

    Unmatched patterns fall through as the generic `info` kind — the raw
    message is retained regardless of classification so a future PHD2 version
    that introduces a new INFO pattern doesn't lose any information.
    """
    message = raw_message.strip()
    kind: str = "info"
    for pattern, tag in _EVENT_PATTERNS:
        if pattern.search(message):
            kind = tag
            break

    parsed_fields: dict[str, str] = {}
    if kind == "dither":
        if m := _RE_DITHER_FIELDS.search(message):
            parsed_fields["dx"] = m.group("dx")
            parsed_fields["dy"] = m.group("dy")
            if m.group("lx"):
                parsed_fields["new_lock_x"] = m.group("lx")
                parsed_fields["new_lock_y"] = m.group("ly")
    elif kind == "lock_position_set":
        if m := _RE_LOCK_POS_FIELDS.search(message):
            parsed_fields["x"] = m.group("x")
            parsed_fields["y"] = m.group("y")

    return LogEvent(  # type: ignore[arg-type]
        kind=kind,
        raw_message=message,
        parsed_fields=parsed_fields,
        time_seconds=time_seconds,
    )


def _peek_sample_time_seconds(line: str) -> float | None:
    """Quickly extract the Time column from a guiding-CSV data row.

    Used by the section walker to keep the running event-anchor time up
    to date without parsing the full row. Tolerant of locale-corrupted
    rows (where Time is split into two tokens; this peek grabs only the
    integer part, which is close enough to anchor events to the right
    second).
    """
    tokens = _tokenize_csv_line(line)
    if len(tokens) < 2:
        return None
    try:
        return float(tokens[1])
    except ValueError:
        return None
