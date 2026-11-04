"""Collector for NightCrate's reviewed Melotte star-cluster list."""

from __future__ import annotations

import csv
from collections.abc import Iterator, Mapping
from typing import TYPE_CHECKING

from nightcrate.catalog_loader._common import maybe_float, maybe_str
from nightcrate.catalog_loader.hash import file_sha256, row_sha256
from nightcrate.catalog_loader.openngc_parser import _parse_name
from nightcrate.catalog_loader.registry import CatalogSource

if TYPE_CHECKING:
    from nightcrate.catalog_loader.reconcile import CollectorBatch


def _rows(source: CatalogSource) -> Iterator[dict[str, str]]:
    with source.file_path.open(encoding="utf-8", newline="") as handle:
        lines = (line for line in handle if line.strip() and not line.lstrip().startswith("#"))
        yield from csv.DictReader(lines)


def _target(value: str) -> tuple[str, str]:
    catalog, identifier = _parse_name(value)
    if catalog is None or identifier is None:
        raise ValueError(f"unrecognized Melotte target designation: {value!r}")
    return catalog, identifier


def _notes(row: dict[str, str]) -> str | None:
    parts = [value for value in (maybe_str(row.get("notes")),) if value is not None]
    position_source = maybe_str(row.get("position_source"))
    if position_source is not None:
        parts.append(f"Position: {position_source}")
    return " · ".join(parts) or None


def _columns(identifier: str, row: dict[str, str]) -> dict[str, object]:
    ra_deg = maybe_float(row.get("ra_deg"))
    dec_deg = maybe_float(row.get("dec_deg"))
    return {
        "primary_designation": f"Mel {identifier}",
        "obj_type": "OCl",
        "raw_obj_type": None,
        "ra_deg": ra_deg,
        "dec_deg": dec_deg,
        "constellation": None,
        "maj_axis_arcmin": maybe_float(row.get("size_arcmin")),
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
        "common_name": maybe_str(row.get("common_name")),
        "ned_notes": None,
        "openngc_notes": _notes(row),
        "raw_other_id": None,
        "source_row_hash": row_sha256(
            {key: value for key, value in row.items() if value is not None}
        ),
    }


def collect_melotte(
    sources: Mapping[str, CatalogSource], on_catalogs: frozenset[str]
) -> CollectorBatch:
    """Return reviewed matches and five standalone Melotte clusters."""
    from nightcrate.catalog_loader.reconcile import CollectedObject, CollectorBatch

    source_hashes = {
        source_id: file_sha256(source.file_path) for source_id, source in sources.items()
    }
    source = sources.get("nightcrate_melotte")
    objects: list[CollectedObject] = []
    if source is not None:
        for row in _rows(source):
            raw_identifier = maybe_str(row.get("melotte"))
            if raw_identifier is None:
                continue
            try:
                identifier = str(int(raw_identifier))
            except ValueError:
                continue
            target = maybe_str(row.get("target_designation"))
            objects.append(
                CollectedObject(
                    source_id=source.source_id,
                    source_key=identifier,
                    catalog_id="melotte",
                    catalog="mel",
                    identifier=identifier,
                    columns=_columns(identifier, row),
                    evidence="reviewed list" if target is not None else None,
                    cross_identifications=(_target(target),) if target is not None else (),
                    require_match=target is not None,
                )
            )
    return CollectorBatch(tuple(objects), (), source_hashes)
