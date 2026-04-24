"""PHD2 guide-log data model — the parser's output.

Shared by the parser (`phd2_parser`), metrics (`phd2_metrics`), and API
(`api/phd2`). Designed to serialize cleanly into both HTTP JSON and a future
AI-analyzer prompt context; no schema rework between v0.22.0 and v5 expected.

All distances are in guide-camera pixels. Arcsec conversions happen at the
display layer using `SectionHeader.pixel_scale_arcsec_per_px`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

SectionKind = Literal["calibration", "guiding"]
MountKind = Literal["Mount", "AO", "DROP"]
EventKind = Literal[
    "settle_begin",
    "settle_end",
    "lock_position_set",
    "dither",
    "server_pause",
    "server_resume",
    "star_selected",
    "alert",
    "guiding_enabled",
    "guiding_disabled",
    "info",
]
CalibrationDirection = Literal["West", "East", "Backlash", "North", "South"]


class SectionHeader(BaseModel):
    """Parsed `key = value` block at the start of each section.

    Known fields are surfaced as typed attributes; anything unrecognized is
    preserved verbatim in `freeform_keys` so future PHD2 versions don't lose
    information silently.
    """

    model_config = ConfigDict(extra="forbid")

    # Equipment
    camera: str | None = None
    mount: str | None = None
    ao: str | None = None
    focal_length_mm: float | None = None
    binning: int | None = None
    pixel_scale_arcsec_per_px: float | None = None
    exposure_ms: int | None = None

    # Sky geometry
    declination_deg: float | None = None
    hour_angle_hr: float | None = None
    pier_side: str | None = None
    rotator_position: str | None = None

    # Star + lock
    lock_position_x_px: float | None = None
    lock_position_y_px: float | None = None
    star_position_x_px: float | None = None
    star_position_y_px: float | None = None
    hfd_px: float | None = None
    search_region_px: float | None = None
    star_mass_tolerance_pct: float | None = None

    # Algorithms
    x_guide_algorithm: str | None = None
    y_guide_algorithm: str | None = None
    dec_guide_mode: str | None = None
    backlash_comp_enabled: bool | None = None
    backlash_pulse_ms: int | None = None
    max_ra_duration_ms: int | None = None
    max_dec_duration_ms: int | None = None
    ra_guide_speed: str | None = None
    dec_guide_speed: str | None = None

    # Calibration geometry (on guiding-section Mount line)
    x_angle_deg: float | None = None
    x_rate_px_per_sec: float | None = None
    y_angle_deg: float | None = None
    y_rate_px_per_sec: float | None = None
    parity: str | None = None
    calibration_step_ms: int | None = None
    assume_orthogonal_axes: bool | None = None
    cal_declination_deg: float | None = None
    last_cal_issue: str | None = None

    # Dither
    dither_description: str | None = None
    dither_scale: float | None = None
    image_noise_reduction: str | None = None

    # Profile
    equipment_profile: str | None = None

    # Anything the parser didn't recognize — verbatim `key -> raw value string`.
    freeform_keys: dict[str, str] = {}


class GuidingSample(BaseModel):
    """One row of a guiding section's CSV table.

    Empty CSV fields resolve to `None` — never `0.0`. DROP frames have `None`
    in every positional field; coercing to zero would silently corrupt RMS
    calculations and produce phantom ideal-guiding periods on charts.
    """

    model_config = ConfigDict(extra="forbid")

    frame: int
    time_seconds: float  # elapsed seconds from section start, NOT wall-clock
    mount_kind: MountKind

    # Star offset from lock position (px). Null on DROP frames.
    dx_px: float | None = None
    dy_px: float | None = None

    # Raw distance projected onto mount axes (px). Null on DROP.
    ra_raw_px: float | None = None
    dec_raw_px: float | None = None

    # Output of guide algorithm — post min-move / hysteresis (px). Null on DROP.
    ra_guide_px: float | None = None
    dec_guide_px: float | None = None

    # Pulse durations (ms); 0 means algorithm decided no pulse. Null on DROP.
    ra_duration_ms: int | None = None
    dec_duration_ms: int | None = None

    # W/E for RA, N/S for Dec; None when no pulse issued.
    ra_direction: Literal["W", "E"] | None = None
    dec_direction: Literal["N", "S"] | None = None

    # AO tip/tilt step values; None when no AO.
    x_step: float | None = None
    y_step: float | None = None

    # Usually populated on error rows too (SNR-based errors still measure mass).
    star_mass: float | None = None
    snr: float | None = None

    error_code: int = 0
    # Quoted description from the log — always authoritative over a code table.
    # See spec §11.2 for why there is no hardcoded code-to-string map.
    error_description: str | None = None


class CalibrationSample(BaseModel):
    """One row of a calibration section's CSV table."""

    model_config = ConfigDict(extra="forbid")

    direction: CalibrationDirection
    step: int
    dx_px: float
    dy_px: float
    x_px: float
    y_px: float
    distance_px: float


class CalibrationPhase(BaseModel):
    """One of the five calibration phases — West/East/Backlash/North/South.

    `angle_deg`, `rate_px_per_sec`, and `parity` come from the
    `<Axis> calibration complete. Angle = …, Rate = …, Parity = …` prose
    line emitted by PHD2 after the West and North phases. East/Backlash/
    South phases have these as `None`.
    """

    model_config = ConfigDict(extra="forbid")

    direction: CalibrationDirection
    samples: list[CalibrationSample]
    angle_deg: float | None = None
    rate_px_per_sec: float | None = None
    parity: str | None = None


class LogEvent(BaseModel):
    """An INFO line inside a section — events interleaved with samples."""

    model_config = ConfigDict(extra="forbid")

    time_seconds: float | None = None  # None when the event precedes any sample
    kind: EventKind
    raw_message: str  # The original INFO line after "INFO: "
    parsed_fields: dict[str, str] = {}  # e.g. {"dx": "5.050", "dy": "-3.863"}


class LogSection(BaseModel):
    """A single Calibration or Guiding section of the log.

    Sections are ordered by file position (not by timestamp) — PHD2 can emit
    backward-timestamp sections after a clock change (see spec §3.8).
    """

    model_config = ConfigDict(extra="forbid")

    kind: SectionKind
    index: int  # 0-based section index in file order
    start_time: datetime  # local-clock timestamp from the section-begin line
    end_time: datetime | None = None  # None when the section is EOF-terminated
    header: SectionHeader
    samples: list[GuidingSample] = []
    calibration_phases: list[CalibrationPhase] = []
    events: list[LogEvent] = []
    locale_recovery_applied: bool = False


class ParseWarning(BaseModel):
    """A non-fatal issue discovered during parsing — surfaces in the UI."""

    model_config = ConfigDict(extra="forbid")

    code: str  # stable identifier, e.g. "locale_recovery_applied"
    message: str  # human-readable, already-formatted detail
    section_index: int | None = None  # which section this pertains to, if any


class ParsedLog(BaseModel):
    """The full output of `parse_log(...)` — header + sections + warnings."""

    model_config = ConfigDict(extra="forbid")

    file_path: str
    phd2_version: str | None  # often empty on ASIAIR-bundled logs (spec §11.11)
    log_version: str  # format version, e.g. "2.5"
    log_enabled_at: datetime  # from the first-line `Log enabled at …`
    sections: list[LogSection]
    warnings: list[ParseWarning] = []


class Phd2DebugLogRejected(ValueError):
    """Raised when a file is a PHD2 debug log rather than a guide log.

    Debug logs have a different header format and are not supported until
    v0.30.0+ per the spec roadmap.
    """
