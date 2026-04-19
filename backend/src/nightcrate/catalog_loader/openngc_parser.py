"""Parse OpenNGC's semicolon-delimited CSV (``NGC.csv`` / ``addendum.csv``).

The file is read row-by-row and yielded as ``ParsedOpenNgcRow`` instances.
``NonEx`` rows are skipped entirely; ``Dup`` rows are yielded with
``is_duplicate=True`` so the loader can merge them into the target.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from nightcrate.catalog_loader.hash import row_sha256

# Canonical obj_type vocabulary. Kept in sync with the CHECK constraint on
# `dso.obj_type` in migration 0015. Anything outside this set is folded to
# 'Other' with the original value preserved on `raw_obj_type`.
KNOWN_OBJ_TYPES: frozenset[str] = frozenset(
    [
        "G",
        "GPair",
        "GTrpl",
        "GGroup",
        "HII",
        "EmN",
        "RfN",
        "PN",
        "OCl",
        "GCl",
        "Cl+N",
        "SNR",
        "DrkN",
        "Neb",
        "*Ass",
        "Nova",
        "*",
        "**",
        "Other",
    ]
)

# Required columns on every OpenNGC-format file. Missing columns cause a
# clear failure at parse time, naming the absent column.
REQUIRED_COLUMNS: tuple[str, ...] = ("Name", "Type", "RA", "Dec")

# The Name column's prefix — e.g., "NGC1976" → ("NGC", "1976"). Trailing
# letter suffixes (e.g., "NGC1976A") are part of the identifier.
_NAME_PREFIX_RE = re.compile(r"^([A-Za-z]+)(.*)$")

# Map of OpenNGC Name-column prefixes → (catalog, zero-strip). Used to build
# the primary designation for each row.
_NAME_CATALOG: dict[str, str] = {
    "NGC": "ngc",
    "IC": "ic",
    "M": "messier",
    "C": "caldwell",
    "B": "barnard",
    "ESO": "eso",
    "PGC": "pgc",
    "UGC": "ugc",
    "LBN": "lbn",
    "LDN": "ldn",
    "MCG": "mcg",
    "Sh2": "sharpless2",
    "Mel": "mel",
    "Cl": "cr",  # OpenNGC's addendum uses "Cl399" for Brocchi's Cluster (Collinder 399)
    "Ced": "cederblad",
    "VdB": "vdb",
    "Abell": "abell",
    "Cr": "cr",
}


@dataclass(frozen=True, slots=True)
class ParsedOpenNgcRow:
    # Canonical object fields (match columns on `dso`)
    obj_type: str
    raw_obj_type: str | None
    ra_deg: float | None
    dec_deg: float | None
    constellation: str | None
    maj_axis_arcmin: float | None
    min_axis_arcmin: float | None
    position_angle_deg: float | None
    mag_b: float | None
    mag_v: float | None
    mag_j: float | None
    mag_h: float | None
    mag_k: float | None
    surface_brightness: float | None
    hubble_type: str | None
    pm_ra: float | None
    pm_dec: float | None
    radial_velocity: float | None
    redshift: float | None
    cstar_mag_u: float | None
    cstar_mag_b: float | None
    cstar_mag_v: float | None
    cstar_id: str | None
    common_name: str | None
    ned_notes: str | None
    openngc_notes: str | None
    raw_other_id: str | None

    # Designation builders
    raw_name: str  # original Name value ("NGC1976", "M040", etc.)
    name_catalog: str | None  # resolved catalog for the Name prefix
    name_identifier: str | None  # numeric portion of Name (leading zeros stripped)
    messier_number: str | None  # M column (leading zeros stripped), if set
    ngc_cross_ref: str | None  # NGC column (leading zeros stripped), if set
    ic_cross_ref: str | None  # IC column (leading zeros stripped), if set

    # Duplicate handling
    is_duplicate: bool

    # Provenance
    row_hash: str


def sexagesimal_ra_to_degrees(value: str) -> float | None:
    """Convert ``HH:MM:SS.ss`` right-ascension to decimal degrees."""
    value = value.strip()
    if not value:
        return None
    parts = value.split(":")
    if len(parts) != 3:
        raise ValueError(f"invalid RA format: {value!r}")
    h, m, s = (float(p) for p in parts)
    hours = h + m / 60.0 + s / 3600.0
    return hours * 15.0


def sexagesimal_dec_to_degrees(value: str) -> float | None:
    """Convert ``±DD:MM:SS.s`` declination to decimal degrees."""
    value = value.strip()
    if not value:
        return None
    sign = 1.0
    if value[0] in "+-":
        if value[0] == "-":
            sign = -1.0
        value = value[1:]
    parts = value.split(":")
    if len(parts) != 3:
        raise ValueError(f"invalid Dec format: {value!r}")
    d, m, s = (float(p) for p in parts)
    return sign * (d + m / 60.0 + s / 3600.0)


def _maybe_float(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _maybe_str(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _strip_leading_zeros(value: str | None) -> str | None:
    """Strip leading zeros from a numeric-ish identifier, preserving any
    trailing suffix (e.g., ``040A`` → ``40A``, ``001`` → ``1``, ``0`` → ``0``).
    """
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    # Split numeric prefix from any trailing letter suffix
    m = re.match(r"^(\d+)(.*)$", value)
    if not m:
        return value
    digits, suffix = m.groups()
    stripped = digits.lstrip("0") or "0"
    return stripped + suffix


def _parse_name(raw_name: str) -> tuple[str | None, str | None]:
    """Split an OpenNGC ``Name`` value into ``(catalog, identifier)``.

    Returns ``(None, None)`` when the prefix isn't recognized — the caller
    is expected to still emit a designation using the Name verbatim, but
    flagging this lets the loader know the row has no canonical primary
    catalog to key on.
    """
    raw_name = raw_name.strip()
    if not raw_name:
        return None, None

    match = _NAME_PREFIX_RE.match(raw_name)
    if match is None:
        return None, None

    prefix, rest = match.groups()
    catalog = _NAME_CATALOG.get(prefix)
    if catalog is None:
        return None, None

    identifier = _strip_leading_zeros(rest) if rest else None
    return catalog, identifier


def _validate_header(fieldnames: list[str] | None, *, source: Path) -> None:
    if not fieldnames:
        raise ValueError(f"{source}: file has no header row")
    missing = [col for col in REQUIRED_COLUMNS if col not in fieldnames]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"{source}: missing required column(s): {joined}")


def _row_to_hash_fields(row: dict[str, str]) -> dict[str, str | None]:
    """Build a deterministic subset of the raw row for ``source_row_hash``.

    We hash the verbatim column values so any upstream data edit invalidates
    the hash. Columns outside the known set are ignored — they contribute to
    the file hash but not per-row.
    """
    keys = (
        "Name",
        "Type",
        "RA",
        "Dec",
        "Const",
        "MajAx",
        "MinAx",
        "PosAng",
        "B-Mag",
        "V-Mag",
        "J-Mag",
        "H-Mag",
        "K-Mag",
        "SurfBr",
        "Hubble",
        "Pm-RA",
        "Pm-Dec",
        "RadVel",
        "Redshift",
        "Cstar U-Mag",
        "Cstar B-Mag",
        "Cstar V-Mag",
        "Cstar Names",
        "M",
        "NGC",
        "IC",
        "Identifiers",
        "Common names",
        "NED notes",
        "OpenNGC notes",
    )
    return {k: _maybe_str(row.get(k)) for k in keys}


def parse_openngc(path: Path) -> Iterator[ParsedOpenNgcRow]:
    """Stream ``ParsedOpenNgcRow`` records from an OpenNGC CSV file.

    ``NonEx`` rows are skipped. ``Dup`` rows are yielded with
    ``is_duplicate=True``; their cross-reference NGC/IC columns tell the
    loader which canonical row to attach the duplicate's designations to.
    """
    # ``utf-8-sig`` tolerates a BOM if one appears in future releases.
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        _validate_header(reader.fieldnames, source=path)

        for row in reader:
            obj_type_raw = (row.get("Type") or "").strip()
            if obj_type_raw == "NonEx":
                continue

            is_duplicate = obj_type_raw == "Dup"

            # Non-'Dup' rows get their type folded to 'Other' when unknown.
            # 'Dup' rows don't persist as their own dso — their obj_type is
            # irrelevant — but we still populate a valid value to avoid
            # downstream surprises.
            if is_duplicate:
                obj_type = "Other"
                raw_obj_type = "Dup"
            elif obj_type_raw in KNOWN_OBJ_TYPES:
                obj_type = obj_type_raw
                raw_obj_type = None
            else:
                obj_type = "Other"
                raw_obj_type = obj_type_raw or None

            name_catalog, name_identifier = _parse_name(row.get("Name") or "")

            try:
                ra_deg = sexagesimal_ra_to_degrees(row.get("RA") or "")
                dec_deg = sexagesimal_dec_to_degrees(row.get("Dec") or "")
            except ValueError:
                # Bad coordinate data is non-fatal for a single row — record
                # None and let the loader decide whether to keep the row.
                ra_deg, dec_deg = None, None

            yield ParsedOpenNgcRow(
                obj_type=obj_type,
                raw_obj_type=raw_obj_type,
                ra_deg=ra_deg,
                dec_deg=dec_deg,
                constellation=_maybe_str(row.get("Const")),
                maj_axis_arcmin=_maybe_float(row.get("MajAx")),
                min_axis_arcmin=_maybe_float(row.get("MinAx")),
                position_angle_deg=_maybe_float(row.get("PosAng")),
                mag_b=_maybe_float(row.get("B-Mag")),
                mag_v=_maybe_float(row.get("V-Mag")),
                mag_j=_maybe_float(row.get("J-Mag")),
                mag_h=_maybe_float(row.get("H-Mag")),
                mag_k=_maybe_float(row.get("K-Mag")),
                surface_brightness=_maybe_float(row.get("SurfBr")),
                hubble_type=_maybe_str(row.get("Hubble")),
                pm_ra=_maybe_float(row.get("Pm-RA")),
                pm_dec=_maybe_float(row.get("Pm-Dec")),
                radial_velocity=_maybe_float(row.get("RadVel")),
                redshift=_maybe_float(row.get("Redshift")),
                cstar_mag_u=_maybe_float(row.get("Cstar U-Mag")),
                cstar_mag_b=_maybe_float(row.get("Cstar B-Mag")),
                cstar_mag_v=_maybe_float(row.get("Cstar V-Mag")),
                cstar_id=_maybe_str(row.get("Cstar Names")),
                common_name=_maybe_str(row.get("Common names")),
                ned_notes=_maybe_str(row.get("NED notes")),
                openngc_notes=_maybe_str(row.get("OpenNGC notes")),
                raw_other_id=_maybe_str(row.get("Identifiers")),
                raw_name=(row.get("Name") or "").strip(),
                name_catalog=name_catalog,
                name_identifier=name_identifier,
                messier_number=_strip_leading_zeros(row.get("M")),
                ngc_cross_ref=_strip_leading_zeros(row.get("NGC")),
                ic_cross_ref=_strip_leading_zeros(row.get("IC")),
                is_duplicate=is_duplicate,
                row_hash=row_sha256(_row_to_hash_fields(row)),
            )
