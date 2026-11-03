"""Wolf-Rayet star collector for VizieR III/215 tables 13 and 15."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING

from nightcrate.catalog_loader._common import clean_tex_name, maybe_float, maybe_str
from nightcrate.catalog_loader.designations import canonical_identifier
from nightcrate.catalog_loader.hash import file_sha256, row_sha256
from nightcrate.catalog_loader.registry import CatalogSource
from nightcrate.catalog_loader.vizier_tsv import parse_vizier_tsv

if TYPE_CHECKING:
    from nightcrate.catalog_loader.reconcile import CollectorBatch

logger = logging.getLogger("nightcrate.catalog_loader.wr")


def _notes(row: dict[str, str | None], photometry: dict[str, str | None] | None) -> str | None:
    parts: list[str] = []
    if photometry is not None:
        vmag = maybe_str(photometry.get("vmag"))
        spectral_type = clean_tex_name(photometry.get("SpType"))
        if vmag is not None:
            parts.append(f"Narrow-band v {vmag}")
        if spectral_type is not None:
            parts.append(spectral_type)
    name = clean_tex_name(row.get("Name"))
    if name is not None:
        parts.append(f"Also {name}")
    return " · ".join(parts) or None


def _columns(
    identifier: str,
    row: dict[str, str | None],
    photometry: dict[str, str | None] | None,
) -> dict[str, object]:
    ra_deg = maybe_float(row.get("_RAJ2000"))
    dec_deg = maybe_float(row.get("_DEJ2000"))
    hash_cells = {key: value for key, value in row.items() if value is not None}
    if photometry is not None:
        hash_cells.update(
            {f"phot_{key}": value for key, value in photometry.items() if value is not None}
        )
    return {
        "primary_designation": f"WR {identifier}",
        "obj_type": "WR*",
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
        "openngc_notes": _notes(row, photometry),
        "raw_other_id": None,
        "source_row_hash": row_sha256(hash_cells),
    }


def collect_wr(sources: Mapping[str, CatalogSource], on_catalogs: frozenset[str]) -> CollectorBatch:
    """Join WR positions to photometry and return standalone catalog rows."""
    from nightcrate.catalog_loader.reconcile import CollectedObject, CollectorBatch

    source_hashes = {
        source_id: file_sha256(source.file_path) for source_id, source in sources.items()
    }
    main = sources.get("vizier_wr")
    phot_source = sources.get("vizier_wr_phot")
    photometry: dict[str, dict[str, str | None]] = {}
    photometry_identifiers: list[str] = []
    if phot_source is not None:
        for row in parse_vizier_tsv(phot_source.file_path):
            raw_identifier = maybe_str(row.get("WR"))
            if raw_identifier is None:
                continue
            identifier = canonical_identifier("wr", raw_identifier)
            photometry_identifiers.append(identifier)
            if identifier in photometry:
                logger.warning("[wr] duplicate WR id %s in table15; keeping first row", identifier)
                continue
            photometry[identifier] = row

    objects: list[CollectedObject] = []
    main_identifiers: list[str] = []
    main_rows: dict[str, dict[str, str | None]] = {}
    if main is not None:
        for row in parse_vizier_tsv(main.file_path):
            raw_identifier = maybe_str(row.get("WR"))
            if raw_identifier is None:
                continue
            identifier = canonical_identifier("wr", raw_identifier)
            main_identifiers.append(identifier)
            if identifier in main_rows:
                logger.warning("[wr] duplicate WR id %s in table13; keeping first row", identifier)
                continue
            main_rows[identifier] = row

        for identifier, row in main_rows.items():
            objects.append(
                CollectedObject(
                    source_id=main.source_id,
                    source_key=identifier,
                    catalog_id="wr",
                    catalog="wr",
                    identifier=identifier,
                    columns=_columns(identifier, row, photometry.get(identifier)),
                )
            )

    unmatched_photometry = sum(identifier not in main_rows for identifier in photometry_identifiers)
    unmatched_positions = sum(identifier not in photometry for identifier in main_identifiers)
    logger.info("[wr] skipped %d table15 rows without a table13 partner", unmatched_photometry)
    logger.info("[wr] kept %d table13 rows without table15 photometry", unmatched_positions)
    return CollectorBatch(tuple(objects), (), source_hashes)
