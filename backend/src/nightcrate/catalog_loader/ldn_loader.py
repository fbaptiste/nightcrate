"""Lynds dark-nebula collector for VizieR VII/7A."""

from __future__ import annotations

import logging
import math
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING

from nightcrate.catalog_loader._common import maybe_float, maybe_str
from nightcrate.catalog_loader.barnard_loader import _normalise_barn_id
from nightcrate.catalog_loader.hash import file_sha256, row_sha256
from nightcrate.catalog_loader.registry import CatalogSource
from nightcrate.catalog_loader.vizier_tsv import parse_vizier_tsv

if TYPE_CHECKING:
    from nightcrate.catalog_loader.reconcile import CollectorBatch

logger = logging.getLogger("nightcrate.catalog_loader.ldn")

_BARNARD_RE = re.compile(r"\d+[A-Z]?")


def _barnard_ids(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    return tuple(_normalise_barn_id(match.group()) for match in _BARNARD_RE.finditer(value))


def _match_size(area: float | None) -> float | None:
    if area is None or area < 0:
        return None
    return 2.0 * math.sqrt(area / math.pi) * 60.0


def _notes(row: dict[str, str | None]) -> str | None:
    parts: list[str] = []
    area = maybe_str(row.get("Area"))
    opacity = maybe_str(row.get("Opacity"))
    if area is not None:
        parts.append(f"Area {area} deg²")
    if opacity is not None:
        parts.append(f"opacity {opacity} (6 darkest)")
    return " · ".join(parts) or None


def _columns(identifier: str, row: dict[str, str | None]) -> dict[str, object]:
    ra_deg = maybe_float(row.get("_RAJ2000"))
    dec_deg = maybe_float(row.get("_DEJ2000"))
    return {
        "primary_designation": f"LDN {identifier}",
        "obj_type": "DrkN",
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


def collect_ldn(
    sources: Mapping[str, CatalogSource], on_catalogs: frozenset[str]
) -> CollectorBatch:
    """Parse LDN rows, including size-gated Barnard matches and groups."""
    from nightcrate.catalog_loader.reconcile import (
        CollectedGroup,
        CollectedObject,
        CollectorBatch,
    )

    source_hashes = {
        source_id: file_sha256(source.file_path) for source_id, source in sources.items()
    }
    source = sources.get("vizier_ldn")
    objects: list[CollectedObject] = []
    groups: list[CollectedGroup] = []
    skipped = 0
    if source is not None:
        for row in parse_vizier_tsv(source.file_path):
            raw_identifier = maybe_str(row.get("LDN"))
            if raw_identifier is None:
                skipped += 1
                continue
            try:
                identifier = str(int(raw_identifier))
            except ValueError:
                skipped += 1
                continue
            barnard_ids = _barnard_ids(row.get("Barn")) if "barnard" in on_catalogs else ()
            area = maybe_float(row.get("Area"))
            key = (source.source_id, identifier)
            objects.append(
                CollectedObject(
                    source_id=source.source_id,
                    source_key=identifier,
                    catalog_id="ldn",
                    catalog="ldn",
                    identifier=identifier,
                    columns=_columns(identifier, row),
                    cross_identifications=(
                        (("barnard", barnard_ids[0]),) if len(barnard_ids) == 1 else ()
                    ),
                    match_size_arcmin=_match_size(area),
                    match_size_ratio_max=3.0,
                )
            )
            if barnard_ids:
                groups.append(
                    CollectedGroup(
                        catalog="ldn",
                        identifier=identifier,
                        whole_key=key,
                        member_designations=tuple(
                            ("barnard", barnard_id) for barnard_id in barnard_ids
                        ),
                    )
                )
    logger.info("[ldn] skipped %d rows without an LDN number", skipped)
    return CollectorBatch(tuple(objects), tuple(groups), source_hashes)
