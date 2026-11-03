"""Lynds bright-nebula collector for VizieR VII/9."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING

from nightcrate.catalog_loader._common import clean_tex_name, maybe_float, maybe_str
from nightcrate.catalog_loader.hash import file_sha256, row_sha256
from nightcrate.catalog_loader.registry import CatalogSource
from nightcrate.catalog_loader.vizier_tsv import parse_vizier_tsv

if TYPE_CHECKING:
    from nightcrate.catalog_loader.reconcile import CollectorBatch

_NAME_RE = re.compile(r"^(NGC|IC|S|C)\s+(\d+[AB]?)$", re.IGNORECASE)
_DG_RE = re.compile(r"^DG\s+(\d+)$", re.IGNORECASE)
_NAME_CATALOGS = {"NGC": "ngc", "IC": "ic", "S": "sharpless2", "C": "cederblad"}


def _other_name(name: str | None) -> tuple[tuple[str, str], ...]:
    if name is None or (match := _NAME_RE.fullmatch(name)) is None:
        return ()
    prefix, identifier = match.groups()
    return ((_NAME_CATALOGS[prefix.upper()], identifier),)


def _notes(row: dict[str, str | None]) -> str | None:
    parts: list[str] = []
    brightness = maybe_str(row.get("Bright"))
    if brightness not in {None, "0"}:
        parts.append(f"Brightness {brightness} (1 brightest, 6 faintest)")
    name = clean_tex_name(row.get("Name"))
    if name is not None and (match := _DG_RE.fullmatch(name)) is not None:
        parts.append(f"Also DG {match.group(1)}")
    return " · ".join(parts) or None


def _columns(identifier: str, row: dict[str, str | None]) -> dict[str, object]:
    ra_deg = maybe_float(row.get("_RAJ2000"))
    dec_deg = maybe_float(row.get("_DEJ2000"))
    return {
        "primary_designation": f"LBN {identifier}",
        "obj_type": "Neb",
        "raw_obj_type": None,
        "ra_deg": ra_deg,
        "dec_deg": dec_deg,
        "constellation": None,
        "maj_axis_arcmin": maybe_float(row.get("Diam1")),
        "min_axis_arcmin": maybe_float(row.get("Diam2")),
        "position_angle_deg": None,
        "mag_b": None,
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
        "openngc_notes": _notes(row),
        "raw_other_id": None,
        "source_row_hash": row_sha256(
            {key: value for key, value in row.items() if value is not None}
        ),
    }


def collect_lbn(
    sources: Mapping[str, CatalogSource], on_catalogs: frozenset[str]
) -> CollectorBatch:
    """Parse LBN rows and expose the catalog's stated cross-identifications."""
    from nightcrate.catalog_loader.reconcile import CollectedObject, CollectorBatch

    source_hashes = {
        source_id: file_sha256(source.file_path) for source_id, source in sources.items()
    }
    source = sources.get("vizier_lbn")
    objects: list[CollectedObject] = []
    if source is not None:
        for row in parse_vizier_tsv(source.file_path):
            raw_identifier = maybe_str(row.get("Seq"))
            if raw_identifier is None:
                continue
            try:
                identifier = str(int(raw_identifier))
            except ValueError:
                continue
            name = clean_tex_name(row.get("Name"))
            objects.append(
                CollectedObject(
                    source_id=source.source_id,
                    source_key=identifier,
                    catalog_id="lbn",
                    catalog="lbn",
                    identifier=identifier,
                    columns=_columns(identifier, row),
                    cross_identifications=_other_name(name),
                )
            )
    return CollectorBatch(tuple(objects), (), source_hashes)
