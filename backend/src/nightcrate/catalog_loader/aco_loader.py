"""ACO galaxy-cluster collector for VizieR VII/110A tables 3, 4 and 5."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from nightcrate.catalog_loader._common import maybe_float, maybe_str
from nightcrate.catalog_loader.hash import file_sha256, row_sha256
from nightcrate.catalog_loader.registry import CatalogSource
from nightcrate.catalog_loader.vizier_tsv import parse_vizier_tsv

if TYPE_CHECKING:
    from nightcrate.catalog_loader.reconcile import CollectorBatch

_SOURCE_KEYS = {
    "vizier_aco_north": ("ACO", ""),
    "vizier_aco_south": ("ACO", ""),
    "vizier_aco_s": ("ACOS", "S"),
}


def _notes(row: dict[str, str | None]) -> str | None:
    labels = (
        ("m10", "m10 {value} (tenth-brightest member)"),
        ("Rich", "richness {value}"),
        ("Dclass", "distance class {value}"),
        ("BMtype", "BM {value}"),
        ("z", "z {value}"),
    )
    return (
        " · ".join(
            template.format(value=value)
            for key, template in labels
            if (value := maybe_str(row.get(key))) is not None
        )
        or None
    )


def _columns(identifier: str, row: dict[str, str | None]) -> dict[str, object]:
    ra_deg = maybe_float(row.get("_RAJ2000"))
    dec_deg = maybe_float(row.get("_DEJ2000"))
    return {
        "primary_designation": f"ACO {identifier}",
        "obj_type": "ClG",
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


def collect_aco(
    sources: Mapping[str, CatalogSource], on_catalogs: frozenset[str]
) -> CollectorBatch:
    """Collect all three non-overlap ACO tables as standalone clusters."""
    from nightcrate.catalog_loader.reconcile import CollectedObject, CollectorBatch

    source_hashes = {
        source_id: file_sha256(source.file_path) for source_id, source in sources.items()
    }
    objects: list[CollectedObject] = []
    for source_id, (column, prefix) in _SOURCE_KEYS.items():
        source = sources.get(source_id)
        if source is None:
            continue
        for row in parse_vizier_tsv(source.file_path):
            raw_identifier = maybe_str(row.get(column))
            if raw_identifier is None:
                continue
            try:
                identifier = f"{prefix}{int(raw_identifier)}"
            except ValueError:
                continue
            objects.append(
                CollectedObject(
                    source_id=source.source_id,
                    source_key=identifier,
                    catalog_id="aco",
                    catalog="aco",
                    identifier=identifier,
                    columns=_columns(identifier, row),
                )
            )
    return CollectorBatch(tuple(objects), (), source_hashes)
