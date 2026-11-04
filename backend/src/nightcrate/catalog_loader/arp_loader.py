"""Arp peculiar-galaxy member collector for VizieR VII/192."""

from __future__ import annotations

import csv
import logging
import re
from collections import defaultdict
from collections.abc import Iterator, Mapping
from typing import TYPE_CHECKING

from nightcrate.catalog_loader._common import maybe_float, maybe_str
from nightcrate.catalog_loader.designations import canonical_identifier
from nightcrate.catalog_loader.hash import file_sha256, row_sha256
from nightcrate.catalog_loader.loader import _build_display_form
from nightcrate.catalog_loader.openngc_parser import _parse_name
from nightcrate.catalog_loader.registry import CatalogSource
from nightcrate.catalog_loader.vizier_tsv import parse_vizier_tsv

if TYPE_CHECKING:
    from nightcrate.catalog_loader.reconcile import CollectorBatch

logger = logging.getLogger("nightcrate.catalog_loader.arp")

_MEMBER_FIELDS = ("Arp", "RAJ2000", "DEJ2000", "Name", "MType")
_EDITORIAL_FIELDS = ("arp", "ra_j2000", "dec_j2000", "list_name", "mtype")
_SYSTEM_TYPES = (
    (re.compile(r"\b(?:pair|double\s+system)\b", re.IGNORECASE), "GPair"),
    (re.compile(r"\btriple\b", re.IGNORECASE), "GTrpl"),
    (re.compile(r"\b(?:chain|group)\b", re.IGNORECASE), "GGroup"),
)


def _editorial_rows(source: CatalogSource) -> Iterator[dict[str, str]]:
    with source.file_path.open(encoding="utf-8", newline="") as handle:
        lines = (line for line in handle if line.strip() and not line.lstrip().startswith("#"))
        yield from csv.DictReader(lines)


def _key(row: Mapping[str, str | None], fields: tuple[str, ...]) -> str:
    return ":".join((row.get(field) or "").strip() for field in fields)


def _designation(value: str) -> tuple[str, str] | None:
    if value == "new":
        return None
    catalog, identifier = _parse_name(value)
    if catalog is None or identifier is None:
        raise ValueError(f"unrecognized Arp member designation: {value!r}")
    return catalog, canonical_identifier(catalog, identifier)


def _object_type(mtype: str | None) -> str:
    for pattern, obj_type in _SYSTEM_TYPES:
        if mtype is not None and pattern.search(mtype):
            return obj_type
    return "G"


def _columns(
    arp: str,
    row: dict[str, str | None],
    designation: tuple[str, str] | None,
    *,
    whole_entry: bool,
) -> dict[str, object]:
    ra_deg = maybe_float(row.get("_RAJ2000"))
    dec_deg = maybe_float(row.get("_DEJ2000"))
    list_name = maybe_str(row.get("Name"))
    return {
        "primary_designation": (
            _build_display_form(*designation) if designation is not None else f"Arp {arp}"
        ),
        "obj_type": _object_type(maybe_str(row.get("MType"))) if whole_entry else "G",
        "raw_obj_type": None,
        "ra_deg": ra_deg,
        "dec_deg": dec_deg,
        "constellation": None,
        "maj_axis_arcmin": maybe_float(row.get("dim1")),
        "min_axis_arcmin": maybe_float(row.get("dim2")),
        "position_angle_deg": None,
        "mag_b": None,
        "mag_v": maybe_float(row.get("VT")),
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
        "openngc_notes": (
            f"Listed as {list_name}" if designation is None and list_name is not None else None
        ),
        "raw_other_id": None,
        "source_row_hash": row_sha256(
            {key: value for key, value in row.items() if value is not None}
        ),
    }


def collect_arp(
    sources: Mapping[str, CatalogSource], on_catalogs: frozenset[str]
) -> CollectorBatch:
    """Collect every VII/192 member and describe its one- or many-member view."""
    from nightcrate.catalog_loader.reconcile import (
        CollectedGroup,
        CollectedObject,
        CollectorBatch,
    )

    source_hashes = {
        source_id: file_sha256(source.file_path) for source_id, source in sources.items()
    }
    member_source = sources.get("vizier_arp")
    editorial_source = sources.get("nightcrate_arp_members")
    if member_source is None:
        return CollectorBatch((), (), source_hashes)

    reviewed: dict[str, str] = {}
    if editorial_source is not None:
        for row in _editorial_rows(editorial_source):
            member_key = _key(row, _EDITORIAL_FIELDS)
            if member_key in reviewed:
                raise ValueError(f"duplicate reviewed Arp member key: {member_key}")
            designation = maybe_str(row.get("designation"))
            if designation is None:
                raise ValueError(f"reviewed Arp member has no designation: {member_key}")
            reviewed[member_key] = designation

    parsed: list[tuple[dict[str, str | None], str, str, tuple[str, str] | None, bool, bool]] = []
    seen_member_keys: set[str] = set()
    keys_by_arp: dict[str, list[str]] = defaultdict(list)
    identities_by_arp: dict[str, set[tuple[str, str] | tuple[str, str, str]]] = defaultdict(set)
    for row in parse_vizier_tsv(member_source.file_path):
        member_key = _key(row, _MEMBER_FIELDS)
        if not member_key:
            raise ValueError(f"duplicate Arp member key: {member_key}")
        if member_key in seen_member_keys:
            logger.warning(
                "[catalog] duplicate Arp %s member %r; skipping row",
                maybe_str(row.get("Arp")) or "?",
                maybe_str(row.get("Name")) or "",
            )
            continue
        raw_arp = maybe_str(row.get("Arp"))
        if raw_arp is None:
            continue
        try:
            arp = str(int(raw_arp))
        except ValueError:
            continue
        reviewed_value = reviewed.get(member_key)
        is_new = reviewed_value == "new"
        if reviewed_value is not None:
            designation = _designation(reviewed_value)
        else:
            list_name = maybe_str(row.get("Name")) or ""
            try:
                designation = _designation(list_name)
            except ValueError:
                logger.warning(
                    "[catalog] unreadable Arp %s member name %r; loading it as a new member",
                    arp,
                    list_name,
                )
                designation = None
                is_new = True
        parsed.append(
            (
                row,
                member_key,
                arp,
                designation,
                reviewed_value is not None,
                is_new,
            )
        )
        seen_member_keys.add(member_key)
        keys_by_arp[arp].append(member_key)
        identity = (
            designation if designation is not None else ("new", member_source.source_id, member_key)
        )
        identities_by_arp[arp].add(identity)

    objects: list[CollectedObject] = []
    for row, member_key, arp, designation, is_reviewed, is_new in parsed:
        multiple = len(identities_by_arp[arp]) > 1
        first_member = keys_by_arp[arp][0] == member_key
        objects.append(
            CollectedObject(
                source_id=member_source.source_id,
                source_key=member_key,
                catalog_id="arp",
                catalog=designation[0] if designation is not None else None,
                identifier=designation[1] if designation is not None else None,
                columns=_columns(
                    arp,
                    row,
                    designation,
                    whole_entry=len(keys_by_arp[arp]) == 1 or is_new,
                ),
                extra_designations=(("arp", arp),) if not multiple and first_member else (),
                evidence="reviewed list" if is_reviewed else None,
                release_designations=(("arp", arp),) if multiple and first_member else (),
            )
        )

    groups = tuple(
        CollectedGroup(
            catalog="arp",
            identifier=arp,
            whole_key=None,
            member_keys=tuple((member_source.source_id, key) for key in keys),
        )
        for arp, keys in keys_by_arp.items()
        if len(identities_by_arp[arp]) > 1
    )
    return CollectorBatch(tuple(objects), groups, source_hashes)
