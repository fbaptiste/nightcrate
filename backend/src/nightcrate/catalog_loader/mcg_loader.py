"""MCG galaxy collector for VizieR VII/62A and VII/100."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from nightcrate.catalog_loader._common import maybe_float, maybe_str
from nightcrate.catalog_loader.designations import canonical_identifier
from nightcrate.catalog_loader.hash import file_sha256, row_sha256
from nightcrate.catalog_loader.loader import _build_display_form
from nightcrate.catalog_loader.registry import CatalogSource
from nightcrate.catalog_loader.vizier_tsv import parse_vizier_tsv

if TYPE_CHECKING:
    from nightcrate.catalog_loader.reconcile import CollectorBatch

logger = logging.getLogger("nightcrate.catalog_loader.mcg")

_NAME_RE = re.compile(
    r"^(NGC|IC)\s*0*(\d+)\s*([A-Za-z]?)\s*([:?/*]?)$",
    re.IGNORECASE,
)
_SOURCES = (
    ("vizier_mcg", True, "OtherName", "Mag"),
    ("vizier_mcg_v5", False, "Name", "mag"),
)


@dataclass(frozen=True, slots=True)
class _OtherName:
    cross_identifications: tuple[tuple[str, str], ...] = ()
    gated: bool = False
    keep_in_notes: bool = False


def _identifier(value: str | None) -> str | None:
    raw = maybe_str(value)
    if raw is None:
        return None
    if raw.upper().startswith("MCG"):
        raw = raw[3:].strip()
    canonical = canonical_identifier("mcg", raw)
    return canonical if canonical != raw or re.fullmatch(r"[+-]\d+-\d+-\d+[A-Za-z]*", raw) else None


def _other_name(value: str | None) -> _OtherName:
    raw = maybe_str(value)
    if raw is None:
        return _OtherName()
    match = _NAME_RE.fullmatch(raw)
    if match is None:
        return _OtherName(keep_in_notes=True)

    prefix, number, suffix, marker = match.groups()
    identifier = str(int(number)) + suffix.upper()
    cross_identifications = ((prefix.lower(), identifier),)
    if marker in {":", "?", "/"} and not suffix:
        return _OtherName(cross_identifications, gated=True, keep_in_notes=True)
    if suffix and not marker:
        return _OtherName(cross_identifications, keep_in_notes=True)
    if not suffix and marker in {"", "*"}:
        return _OtherName(cross_identifications)
    return _OtherName(keep_in_notes=True)


def _scaled(value: str | None, scale: float) -> float | None:
    parsed = maybe_float(value)
    return parsed * scale if parsed is not None else None


def _columns(
    identifier: str,
    row: dict[str, str | None],
    *,
    size_scale: float,
    mixed_magnitude_column: str | None,
    other_name_note: str | None,
) -> dict[str, object]:
    ra_deg = maybe_float(row.get("_RAJ2000"))
    dec_deg = maybe_float(row.get("_DEJ2000"))
    mixed_magnitude = (
        maybe_str(row.get(mixed_magnitude_column)) if mixed_magnitude_column is not None else None
    )
    notes = []
    if mixed_magnitude is not None:
        notes.append(f"Catalog magnitude {mixed_magnitude} (mixed sources)")
    if other_name_note is not None:
        notes.append(f"Also {other_name_note}")
    return {
        "primary_designation": _build_display_form("mcg", identifier),
        "obj_type": "G",
        "raw_obj_type": None,
        "ra_deg": ra_deg,
        "dec_deg": dec_deg,
        "constellation": None,
        "maj_axis_arcmin": _scaled(row.get("MajAxis"), size_scale),
        "min_axis_arcmin": _scaled(row.get("MinAxis"), size_scale),
        "position_angle_deg": None,
        "mag_b": maybe_float(row.get("Mag")),
        "mag_v": None,
        "mag_j": None,
        "mag_h": None,
        "mag_k": None,
        "surface_brightness": None,
        "hubble_type": None,
        "pm_ra": None,
        "pm_dec": None,
        "radial_velocity": None,
        "redshift": None,
        "cstar_mag_u": None,
        "cstar_mag_b": None,
        "cstar_mag_v": None,
        "cstar_id": None,
        "common_name": None,
        "ned_notes": None,
        "openngc_notes": " · ".join(notes) or None,
        "raw_other_id": None,
        "source_row_hash": row_sha256(
            {key: value for key, value in row.items() if value is not None}
        ),
    }


def collect_mcg(
    sources: Mapping[str, CatalogSource], on_catalogs: frozenset[str]
) -> CollectorBatch:
    """Collect both non-overlapping MCG tables, keeping first duplicate keys."""
    from nightcrate.catalog_loader.reconcile import CollectedObject, CollectorBatch

    source_hashes = {
        source_id: file_sha256(source.file_path) for source_id, source in sources.items()
    }
    objects: list[CollectedObject] = []
    seen: set[str] = set()
    duplicate_count = 0
    for source_id, tenths_arcmin, name_column, magnitude_column in _SOURCES:
        source = sources.get(source_id)
        if source is None:
            continue
        for row in parse_vizier_tsv(source.file_path):
            identifier = _identifier(row.get("MCG"))
            if identifier is None:
                continue
            if identifier in seen:
                duplicate_count += 1
                continue
            seen.add(identifier)
            raw_other_name = maybe_str(row.get(name_column))
            other_name = _other_name(raw_other_name)
            size_scale = 0.1 if tenths_arcmin else 1.0
            columns = _columns(
                identifier,
                row,
                size_scale=size_scale,
                mixed_magnitude_column=None if tenths_arcmin else magnitude_column,
                other_name_note=(raw_other_name if other_name.keep_in_notes else None),
            )
            objects.append(
                CollectedObject(
                    source_id=source.source_id,
                    source_key=identifier,
                    catalog_id="mcg",
                    catalog="mcg",
                    identifier=identifier,
                    columns=columns,
                    cross_identifications=other_name.cross_identifications,
                    match_size_arcmin=(
                        maybe_float(str(columns["maj_axis_arcmin"])) if other_name.gated else None
                    ),
                    match_size_ratio_max=3.0 if other_name.gated else None,
                )
            )
    if duplicate_count:
        logger.info("[mcg] skipped %d repeated identifiers", duplicate_count)
    return CollectorBatch(tuple(objects), (), source_hashes)
