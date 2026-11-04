"""Herbig-Haro object collector for VizieR V/104."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from nightcrate.catalog_loader._common import clean_tex_name, maybe_float, maybe_str
from nightcrate.catalog_loader.hash import file_sha256, row_sha256
from nightcrate.catalog_loader.registry import CatalogSource
from nightcrate.catalog_loader.vizier_tsv import parse_vizier_tsv

if TYPE_CHECKING:
    from nightcrate.catalog_loader.reconcile import CollectorBatch


def _notes(row: dict[str, str | None]) -> str | None:
    parts: list[str] = []
    region = clean_tex_name(row.get("Region"))
    if region is not None:
        parts.append(f"Region {region}")
    name = clean_tex_name(row.get("Name"))
    if name is not None:
        parts.append(f"Also {name}")
    return " · ".join(parts) or None


def _columns(identifier: str, row: dict[str, str | None]) -> dict[str, object]:
    ra_deg = maybe_float(row.get("_RAJ2000"))
    dec_deg = maybe_float(row.get("_DEJ2000"))
    return {
        "primary_designation": f"HH {identifier}",
        "obj_type": "HH",
        "raw_obj_type": None,
        "ra_deg": ra_deg,
        "dec_deg": dec_deg,
        "constellation": None,
        "maj_axis_arcmin": None,
        "min_axis_arcmin": None,
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


def collect_hh(sources: Mapping[str, CatalogSource], on_catalogs: frozenset[str]) -> CollectorBatch:
    """Parse the HH catalog into standalone object rows."""
    from nightcrate.catalog_loader.reconcile import CollectedObject, CollectorBatch

    source_hashes = {
        source_id: file_sha256(source.file_path) for source_id, source in sources.items()
    }
    source = sources.get("vizier_hh")
    objects: list[CollectedObject] = []
    if source is not None:
        for row in parse_vizier_tsv(source.file_path):
            raw_identifier = maybe_str(row.get("HH"))
            if raw_identifier is None:
                continue
            try:
                identifier = str(int(raw_identifier))
            except ValueError:
                continue
            objects.append(
                CollectedObject(
                    source_id=source.source_id,
                    source_key=identifier,
                    catalog_id="hh",
                    catalog="hh",
                    identifier=identifier,
                    columns=_columns(identifier, row),
                )
            )
    return CollectorBatch(tuple(objects), (), source_hashes)
