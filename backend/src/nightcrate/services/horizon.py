"""Horizon parser, exporters, and filename sanitization.

**Parser.** ``parse_horizon_text`` accepts three file shapes:

1. **N.I.N.A. ``.hrz``** and any generic two-column ``az alt`` text with ``#``
   or ``;`` comments (the catch-all that also handles Astro-Physics APCC
   exports, Telescopius horizon exports, and hand-edited text).
2. **Theodolite (iPhone app) CSV** — full 14-column CSV with a header row;
   the parser detects the ``HDG_DEG`` / ``VERT`` columns and extracts just
   those.

If neither shape matches, ``HorizonParseError`` is raised — the parser does
not silently guess.

**Exporters.** ``export_nina_hrz`` produces a plain ``.hrz`` text that also
loads unmodified in APCC and Telescopius. ``export_stellarium_zip`` produces
a polygonal-landscape zip bundle. ``export_csv`` is a two-column CSV.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from io import StringIO

import numpy as np

THEODOLITE_AZ_COL = "HDG_DEG"
THEODOLITE_ALT_COL = "VERT"

ALT_MIN = -5.0
ALT_MAX = 90.0


class HorizonParseError(ValueError):
    """Raised when a horizon file can't be parsed."""


@dataclass
class HorizonParseResult:
    points: list[tuple[float, float]]
    warnings: list[str] = field(default_factory=list)
    source_filename: str | None = None


# ── Format detection ─────────────────────────────────────────────────────────


def _looks_like_theodolite(first_line: str) -> bool:
    """True when the first non-comment line is a CSV header containing the
    Theodolite-required columns ``HDG_DEG`` and ``VERT``."""
    if "," not in first_line:
        return False
    cols = [c.strip().strip('"') for c in first_line.split(",")]
    return THEODOLITE_AZ_COL in cols and THEODOLITE_ALT_COL in cols


def _strip_comments(line: str) -> str:
    for marker in ("#", ";"):
        idx = line.find(marker)
        if idx != -1:
            line = line[:idx]
    return line.strip()


def _non_comment_lines(text: str) -> list[tuple[int, str]]:
    """Return ``(line_number, content)`` pairs for non-empty, non-comment
    lines. Line numbers are 1-based (matches user expectations in errors)."""
    out: list[tuple[int, str]] = []
    for i, raw in enumerate(text.splitlines(), start=1):
        stripped = _strip_comments(raw)
        if stripped:
            out.append((i, stripped))
    return out


# ── Parser: Theodolite CSV ────────────────────────────────────────────────────


def _parse_theodolite(text: str) -> list[tuple[float, float]]:
    """Extract (azimuth, altitude) from Theodolite's 14-column CSV using the
    ``HDG_DEG`` (heading, degrees) and ``VERT`` (vertical angle, degrees)
    columns."""
    reader = csv.DictReader(StringIO(text))
    if reader.fieldnames is None:
        raise HorizonParseError("Theodolite CSV has no header row.")
    if THEODOLITE_AZ_COL not in reader.fieldnames or THEODOLITE_ALT_COL not in reader.fieldnames:
        raise HorizonParseError(
            f"Theodolite CSV is missing required columns "
            f"{THEODOLITE_AZ_COL!r} or {THEODOLITE_ALT_COL!r}."
        )
    points: list[tuple[float, float]] = []
    for row_num, row in enumerate(reader, start=2):  # +1 for header, +1 for 1-based
        az_raw = (row.get(THEODOLITE_AZ_COL) or "").strip()
        alt_raw = (row.get(THEODOLITE_ALT_COL) or "").strip()
        if not az_raw or not alt_raw:
            continue
        try:
            az = float(az_raw)
            alt = float(alt_raw)
        except ValueError as exc:
            raise HorizonParseError(
                f"Line {row_num}: could not parse "
                f"{THEODOLITE_AZ_COL}={az_raw!r} / {THEODOLITE_ALT_COL}={alt_raw!r}."
            ) from exc
        points.append((az, alt))
    return points


# ── Parser: two-column az/alt text ────────────────────────────────────────────


def _parse_two_column(text: str) -> list[tuple[float, float]]:
    """Parse ``az alt`` pairs (whitespace or comma separated). ``#`` and ``;``
    start comments."""
    points: list[tuple[float, float]] = []
    for line_num, content in _non_comment_lines(text):
        tokens = [t for t in re.split(r"[\s,]+", content) if t]
        if len(tokens) != 2:
            raise HorizonParseError(
                f"Line {line_num}: expected 2 numbers, got {len(tokens)} ({content!r})."
            )
        try:
            az = float(tokens[0])
            alt = float(tokens[1])
        except ValueError as exc:
            raise HorizonParseError(
                f"Line {line_num}: could not parse numbers ({content!r})."
            ) from exc
        points.append((az, alt))
    return points


# ── Shared normalization ──────────────────────────────────────────────────────


def _normalize_azimuth(az: float, context: str) -> float:
    """Fold azimuth into ``[0, 360)``. Reject obviously out-of-range values."""
    if az == 360.0:
        return 0.0
    if -180.0 <= az < 0.0:
        return az + 360.0
    if 0.0 <= az < 360.0:
        return az
    raise HorizonParseError(f"{context}: azimuth {az} out of range [-180, 360).")


def _validate_altitude(alt: float, context: str) -> float:
    if ALT_MIN <= alt <= ALT_MAX:
        return alt
    raise HorizonParseError(f"{context}: altitude {alt} out of range [{ALT_MIN}, {ALT_MAX}].")


def _offset_duplicates(
    points: list[tuple[float, float]],
) -> tuple[list[tuple[float, float]], list[str]]:
    """Points are sorted ascending by azimuth on entry. When two or more
    consecutive points share an azimuth, offset the duplicates by +0.01°
    each so the composite PK on ``(horizon_id, azimuth_deg)`` accepts them.
    Matches N.I.N.A.'s convention for vertical obstructions.

    Two edge cases the naive +0.01° rule fails on:
    - **Near the 360° seam:** raw offset can push the point ≥ 360°,
      violating the ``azimuth_deg ∈ [0, 360)`` CHECK / Pydantic
      ``Field(lt=360.0)``. Wrap modulo 360 so the seam case stays in
      range.
    - **Collision with the next real point:** input ``[(10.00, _),
      (10.00, _), (10.02, _)]`` under the naive rule becomes
      ``[(10.00, _), (10.01, _), (10.02, _)]`` — which then collides
      PK-wise with the genuine 10.02 point on the next iteration
      (dropping it silently when SQLite rejects the duplicate). Cap
      each offset so it never steps past the next real azimuth
      minus a small guard.
    """
    out: list[tuple[float, float]] = []
    warnings: list[str] = []
    last_az: float | None = None
    same_az_offset = 0
    n = len(points)
    for i, (az, alt) in enumerate(points):
        if last_az is not None and abs(az - last_az) < 1e-9:
            same_az_offset += 1
            raw_offset = 0.01 * same_az_offset
            # Cap so we don't leak into the next real azimuth.
            next_real_az: float | None = None
            for j in range(i + 1, n):
                if abs(points[j][0] - az) > 1e-9:
                    next_real_az = points[j][0]
                    break
            if next_real_az is not None:
                # Guard: leave at least 1e-3° between the last offset
                # and the next real point.
                max_offset = next_real_az - az - 1e-3
                if max_offset > 0 and raw_offset > max_offset:
                    raw_offset = max_offset
            new_az = (az + raw_offset) % 360.0
            warnings.append(
                f"Duplicate azimuth {az:.2f} offset to {new_az:.2f} "
                "to preserve vertical-obstruction point."
            )
            out.append((new_az, alt))
        else:
            same_az_offset = 0
            out.append((az, alt))
            last_az = az
    return out, warnings


# ── Public parser ─────────────────────────────────────────────────────────────


def parse_horizon_text(text: str, source_filename: str | None = None) -> HorizonParseResult:
    """Parse a horizon file. Raises ``HorizonParseError`` on failure."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    non_comment = _non_comment_lines(text)
    if not non_comment:
        raise HorizonParseError("Empty file (no non-comment lines).")

    first_line = non_comment[0][1]
    if _looks_like_theodolite(first_line):
        raw = _parse_theodolite(text)
    else:
        raw = _parse_two_column(text)

    if not raw:
        raise HorizonParseError("No data rows found after parsing.")

    # Normalize and validate each point
    normalized: list[tuple[float, float]] = []
    for idx, (az, alt) in enumerate(raw, start=1):
        ctx = f"Point {idx}"
        normalized.append((_normalize_azimuth(az, ctx), _validate_altitude(alt, ctx)))

    # Sort by azimuth ascending
    normalized.sort(key=lambda p: p[0])

    # Offset exact duplicates; collect warnings
    final, warnings = _offset_duplicates(normalized)

    if len(final) < 2:
        raise HorizonParseError(f"Horizon needs at least 2 points; file produced {len(final)}.")

    return HorizonParseResult(points=final, warnings=warnings, source_filename=source_filename)


# ── Exporters ─────────────────────────────────────────────────────────────────


def _fmt_float(value: float) -> str:
    """Format with up to 2 decimal places, trailing zeros trimmed."""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text if text else "0"


def export_nina_hrz(location_name: str, points: list[tuple[float, float]]) -> str:
    """Plain N.I.N.A. .hrz text. Also loads in APCC and Telescopius."""
    lines = [
        "# NightCrate horizon export",
        f"# Location: {location_name}",
        f"# Exported: {datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "# Az Alt",
        "",
    ]
    for az, alt in sorted(points, key=lambda p: p[0]):
        lines.append(f"{_fmt_float(az)} {_fmt_float(alt)}")
    return "\n".join(lines) + "\n"


def export_csv(points: list[tuple[float, float]]) -> str:
    """Two-column CSV with header row."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["azimuth_deg", "altitude_deg"])
    for az, alt in sorted(points, key=lambda p: p[0]):
        writer.writerow([_fmt_float(az), _fmt_float(alt)])
    return buf.getvalue()


_STELLARIUM_LANDSCAPE_INI = """\
[landscape]
name = {name}
type = polygonal
author = NightCrate
description = Custom horizon exported from NightCrate
polygonal_horizon_list = horizon.txt
polygonal_horizon_list_mode = azDeg_altDeg
polygonal_angle_rotatez = 0
ground_color = 0.15, 0.15, 0.20
horizon_line_color = 0.90, 0.55, 0.10
minimal_brightness = 0.01

[location]
planet = Earth
latitude = {lat}
longitude = {lon}
altitude = {elev}
"""

_STELLARIUM_README = """\
This landscape was exported from NightCrate, an astrophotography
session-cataloging app. It describes the horizon profile measured
or drawn for the observing location named in landscape.ini.

To install: unzip into Stellarium's `landscapes/` directory, then
select the landscape by name in Stellarium's View options.
"""


def export_stellarium_zip(
    location_name: str,
    points: list[tuple[float, float]],
    latitude: float,
    longitude: float,
    elevation_m: float | None,
) -> bytes:
    """Stellarium polygonal-landscape zip bundle."""
    horizon_lines = [
        f"{_fmt_float(az)} {_fmt_float(alt)}" for az, alt in sorted(points, key=lambda p: p[0])
    ]
    horizon_txt = "\n".join(horizon_lines) + "\n"
    landscape_ini = _STELLARIUM_LANDSCAPE_INI.format(
        name=location_name,
        lat=latitude,
        lon=longitude,
        elev=elevation_m if elevation_m is not None else 0,
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("landscape.ini", landscape_ini)
        zf.writestr("horizon.txt", horizon_txt)
        zf.writestr("readme.txt", _STELLARIUM_README)
    return buf.getvalue()


# ── Azimuth interpolation (Target Planner visibility) ────────────────────────


def interpolate_horizon_altitude(
    points: Sequence[tuple[float, float]],
    azimuths_deg: np.ndarray,
) -> np.ndarray:
    """Linearly interpolate a custom horizon's altitude at the given azimuths.

    ``points`` is the location's horizon polyline, sorted ascending by
    azimuth with values in ``[0, 360)``. This function wraps the polyline
    at the 360° seam so azimuths near 0°/360° interpolate across the
    shortest arc.

    Returns an array the same shape as ``azimuths_deg`` giving horizon
    altitude in degrees at each azimuth.
    """
    if len(points) < 2:
        raise ValueError("Need at least 2 horizon points to interpolate.")

    az = np.asarray([p[0] for p in points], dtype=np.float64)
    alt = np.asarray([p[1] for p in points], dtype=np.float64)

    # Extend the polyline with a wrapped copy of the last point at
    # azimuth - 360 (so queries near 0° see the last point "behind" them)
    # and a wrapped copy of the first point at azimuth + 360 (so queries
    # near 360° see the first point "ahead"). This is what makes the
    # interpolation continuous across the 0°/360° seam.
    az_wrapped = np.concatenate(([az[-1] - 360.0], az, [az[0] + 360.0]))
    alt_wrapped = np.concatenate(([alt[-1]], alt, [alt[0]]))

    query = np.mod(np.asarray(azimuths_deg, dtype=np.float64), 360.0)
    return np.interp(query, az_wrapped, alt_wrapped)


def resolve_horizon_altitude(
    horizon_type: str,
    flat_altitude_deg: float | None,
    points: Sequence[tuple[float, float]],
    azimuths_deg: np.ndarray,
) -> np.ndarray:
    """Return horizon altitude at each azimuth for either horizon type.

    Artificial horizons return a constant ``flat_altitude_deg`` at every
    azimuth; custom horizons interpolate the polyline. Callers that
    already hold a ``PlannerHorizon`` value object should pass its
    fields directly — keeps this function free of the planner import
    cycle.
    """
    if horizon_type == "artificial":
        if flat_altitude_deg is None:
            raise ValueError("Artificial horizon requires flat_altitude_deg.")
        return np.full_like(np.asarray(azimuths_deg, dtype=np.float64), float(flat_altitude_deg))
    if horizon_type == "custom":
        return interpolate_horizon_altitude(points, azimuths_deg)
    raise ValueError(f"Unknown horizon type: {horizon_type!r}")


# ── Filename sanitization ─────────────────────────────────────────────────────


def sanitize_filename(name: str) -> str:
    """Produce a safe filesystem-friendly stem from a location name.

    Spaces become underscores; any char not in ``[a-zA-Z0-9_-]`` is dropped;
    result is lowercased. Falls back to ``horizon`` if the result is empty.
    """
    step1 = name.replace(" ", "_")
    step2 = re.sub(r"[^a-zA-Z0-9_\-]", "", step1)
    step3 = re.sub(r"_+", "_", step2).strip("_").lower()
    return step3 or "horizon"
