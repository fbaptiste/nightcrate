"""Pure catalog collection and transactional DSO identity reconciliation."""

from __future__ import annotations

import csv
import logging
import math
import sqlite3
from collections import defaultdict, deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

from nightcrate.catalog_loader import registry
from nightcrate.catalog_loader._common import maybe_float, maybe_str, normalize_designation
from nightcrate.catalog_loader.aco_loader import collect_aco
from nightcrate.catalog_loader.arp_loader import collect_arp
from nightcrate.catalog_loader.barnard_loader import _normalise_barn_id, collect_barnard
from nightcrate.catalog_loader.common_names import (
    ListedNames,
    merge_names,
    read_common_names,
    split_common_names,
)
from nightcrate.catalog_loader.crossref_parser import parse_other_id
from nightcrate.catalog_loader.designations import (
    canonical_identifier,
    canonical_legacy_identifier,
)
from nightcrate.catalog_loader.hash import file_sha256, row_sha256
from nightcrate.catalog_loader.hash_loader import collect_hash
from nightcrate.catalog_loader.hh_loader import collect_hh
from nightcrate.catalog_loader.lbn_loader import collect_lbn
from nightcrate.catalog_loader.ldn_loader import collect_ldn
from nightcrate.catalog_loader.loader import (
    _build_canonical_designations,
    _build_display_form,
    _build_search_key,
    _pick_primary,
    collect_openngc,
)
from nightcrate.catalog_loader.mcg_loader import collect_mcg
from nightcrate.catalog_loader.melotte_loader import collect_melotte
from nightcrate.catalog_loader.openngc_parser import _parse_name
from nightcrate.catalog_loader.registry import CatalogSource, catalogs_for_source
from nightcrate.catalog_loader.sharpless_loader import collect_sharpless
from nightcrate.catalog_loader.user_links import (
    count_references,
    dso_reference_tables,
    move_user_links,
    referenced_dso_ids,
)
from nightcrate.catalog_loader.wr_loader import collect_wr
from nightcrate.services.astronomy import (
    constellation_for_coords,
    constellations_for_coords,
)

logger = logging.getLogger("nightcrate.catalog_loader.reconcile")

OBJECT_SOURCE_IDS: tuple[str, ...] = (
    "openngc",
    "openngc_addendum",
    "vizier_sharpless",
    "vizier_barnard",
    "vizier_wr",
    "vizier_wr_phot",
    "vizier_hh",
    "vizier_hash",
    "vizier_lbn",
    "vizier_ldn",
    "vizier_aco_north",
    "vizier_aco_south",
    "vizier_aco_s",
    "vizier_mcg",
    "vizier_mcg_v5",
    "vizier_arp",
)

EDITORIAL_OBJECT_SOURCE_IDS: tuple[str, ...] = (
    "nightcrate_melotte",
    "nightcrate_arp_members",
    "nightcrate_parts",
    "nightcrate_match_overrides",
    "nightcrate_common_names",
)


@dataclass(frozen=True, slots=True)
class NewObject:
    source_id: str
    source_key: str
    columns: dict[str, object]
    designations: tuple[tuple[str, str, bool], ...]
    file_order: int
    catalog_id: str = "openngc"
    other_names: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SourceEntry:
    source_id: str
    source_key: str
    catalog_id: str
    object_index: int


@dataclass(frozen=True, slots=True)
class NewGroup:
    catalog: str
    identifier: str
    whole_index: int | None
    member_indexes: tuple[int, ...]
    common_name: str | None = None


@dataclass(frozen=True, slots=True)
class StatedMatch:
    catalog: str
    identifier: str
    target_index: int
    entry_size_arcmin: float | None
    target_size_arcmin: float | None
    evidence: str


@dataclass(frozen=True, slots=True)
class CollectedObject:
    """One row supplied by an optional-catalog collector to rule R."""

    source_id: str
    source_key: str
    catalog_id: str
    catalog: str | None
    identifier: str | None
    columns: dict[str, object]
    also_catalog_ids: tuple[str, ...] = ()
    extra_designations: tuple[tuple[str, str], ...] = ()
    evidence: str | None = None
    cross_identifications: tuple[tuple[str, str], ...] = ()
    release_designations: tuple[tuple[str, str], ...] = ()
    match_size_arcmin: float | None = None
    match_size_ratio_max: float | None = None
    require_match: bool = False

    def __post_init__(self) -> None:
        if self.require_match and self.release_designations:
            raise ValueError(
                f"collector row {self.source_id}/{self.source_key} cannot require a match "
                "and release designations"
            )


@dataclass(frozen=True, slots=True)
class CollectedGroup:
    """A group whose row keys are ``(source_id, source_key)`` pairs."""

    catalog: str
    identifier: str
    whole_key: tuple[str, str] | None
    member_keys: tuple[tuple[str, str], ...] = ()
    member_designations: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class CollectorBatch:
    """Objects, groups, and effective hash returned by one collector."""

    objects: tuple[CollectedObject, ...]
    groups: tuple[CollectedGroup, ...]
    source_hashes: dict[str, str]


ObjectCollector = Callable[[Mapping[str, CatalogSource], frozenset[str]], CollectorBatch]

COLLECTOR_ORDER: tuple[str, ...] = (
    "melotte",
    "wr",
    "hh",
    "png",
    "abell_pn",
    "lbn",
    "ldn",
    "aco",
    "mcg",
    "arp",
)


def _collector_registry(**collectors: ObjectCollector) -> dict[str, ObjectCollector]:
    """Build the collector registry, rejecting catalogs without an order slot."""
    unknown = collectors.keys() - set(COLLECTOR_ORDER)
    if unknown:
        names = ", ".join(sorted(unknown))
        raise RuntimeError(f"collectors missing from COLLECTOR_ORDER: {names}")
    return collectors


# Phase B registers each source collector here by its first logical catalog.
# _collector_registry validates additions as soon as this module is imported.
OBJECT_COLLECTORS: dict[str, ObjectCollector] = _collector_registry(
    melotte=collect_melotte,
    wr=collect_wr,
    hh=collect_hh,
    png=collect_hash,
    lbn=collect_lbn,
    ldn=collect_ldn,
    aco=collect_aco,
    mcg=collect_mcg,
    arp=collect_arp,
)


@dataclass(frozen=True, slots=True)
class ObjectSet:
    objects: tuple[NewObject, ...]
    merges: dict[tuple[str, str], int]
    hashes: dict[str, str]
    unresolved: int
    _sources: dict[str, CatalogSource] = field(default_factory=dict, repr=False, compare=False)
    entries: tuple[SourceEntry, ...] = ()
    catalog_states: dict[str, str] = field(default_factory=dict)
    groups: tuple[NewGroup, ...] = ()
    stated_matches: tuple[StatedMatch, ...] = ()


@dataclass(frozen=True, slots=True)
class ReconcileReport:
    source_counts: dict[str, int]
    inserted: int = 0
    updated: int = 0
    reactivated: int = 0
    merged: int = 0
    removed: int = 0
    kept_linked: int = 0
    kept_inactive_merge: int = 0
    deleted: int = 0
    transferred: int = 0
    applied: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class _Draft:
    source_id: str
    source_key: str
    columns: dict[str, object]
    designations: list[tuple[str, str, bool]]
    file_order: int
    catalog_id: str
    catalog_names: tuple[str, ...] = ()
    merged_name_contributions: list[tuple[int, int, tuple[str, ...]]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.catalog_names = split_common_names(
            str(value) if (value := self.columns.get("common_name")) is not None else None
        )


@dataclass(frozen=True, slots=True)
class MatchOverride:
    action: str
    target: tuple[str, str] | None


def _read_editorial_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        lines = [line for line in handle if line.strip() and not line.lstrip().startswith("#")]
    if not lines:
        return []
    return [
        {key: (value or "").strip() for key, value in row.items() if key is not None}
        for row in csv.DictReader(lines)
    ]


def _designation_key(value: str) -> tuple[str, str]:
    catalog, identifier = _parse_name(value)
    if catalog is None or identifier is None:
        refs = parse_other_id(value)
        if len(refs) != 1:
            raise ValueError(f"unrecognized designation: {value!r}")
        catalog = refs[0].catalog
        identifier = refs[0].storage_identifier
    return catalog, canonical_identifier(catalog, identifier)


def read_match_overrides(source: CatalogSource | None) -> dict[tuple[str, str], MatchOverride]:
    """Parse and validate the editorial match overrides from their registered source."""
    overrides: dict[tuple[str, str], MatchOverride] = {}
    if source is None or not source.file_path.exists():
        return overrides
    for row in _read_editorial_csv(source.file_path):
        designation = row.get("designation", "")
        action = row.get("action", "")
        if not designation:
            continue
        if action not in {"assign", "separate"}:
            raise ValueError(f"invalid match override action for {designation!r}: {action!r}")
        target_text = row.get("target_designation", "")
        if action == "assign" and not target_text:
            raise ValueError(f"assign override for {designation!r} has no target")
        if action == "separate" and target_text:
            raise ValueError(f"separate override for {designation!r} has a target")
        overrides[_designation_key(designation)] = MatchOverride(
            action,
            _designation_key(target_text) if target_text else None,
        )
    return overrides


def _openngc_columns(row, primary: str) -> dict[str, object]:
    return {
        "primary_designation": primary,
        "obj_type": row.obj_type,
        "raw_obj_type": row.raw_obj_type,
        "ra_deg": row.ra_deg,
        "dec_deg": row.dec_deg,
        "constellation": row.constellation,
        "maj_axis_arcmin": row.maj_axis_arcmin,
        "min_axis_arcmin": row.min_axis_arcmin,
        "position_angle_deg": row.position_angle_deg,
        "mag_b": row.mag_b,
        "mag_v": row.mag_v,
        "mag_j": row.mag_j,
        "mag_h": row.mag_h,
        "mag_k": row.mag_k,
        "surface_brightness": row.surface_brightness,
        "hubble_type": row.hubble_type,
        "pm_ra": row.pm_ra,
        "pm_dec": row.pm_dec,
        "radial_velocity": row.radial_velocity,
        "redshift": row.redshift,
        "cstar_mag_u": row.cstar_mag_u,
        "cstar_mag_b": row.cstar_mag_b,
        "cstar_mag_v": row.cstar_mag_v,
        "cstar_id": row.cstar_id,
        "common_name": row.common_name,
        "ned_notes": row.ned_notes,
        "openngc_notes": row.openngc_notes,
        "raw_other_id": row.raw_other_id,
        "source_row_hash": row.row_hash,
    }


def build_object_set(
    sources: dict[str, CatalogSource],
    crossref_path: Path | None,
    on_catalogs: frozenset[str] | None = None,
) -> ObjectSet:
    """Collect all present object catalogs and resolve ownership in memory."""
    if on_catalogs is None:
        on_catalogs = frozenset({"sharpless", "barnard"})
    drafts: list[_Draft] = []
    designation_owner: dict[tuple[str, str], int] = {}
    search_owner: dict[str, int] = {}
    merges: dict[tuple[str, str], int] = {}
    hashes: dict[str, str] = {}
    unresolved = 0
    groups: list[NewGroup] = []
    stated_matches: list[StatedMatch] = []
    pending_dups: list[tuple[str, object]] = []
    openngc_rows: list[tuple[int, object, list[tuple[str, str]], int]] = []
    openngc_barnard_names: dict[str, list[int]] = defaultdict(list)
    resolved_entries: list[SourceEntry] = []
    resolved_entry_keys: set[tuple[str, str, str, int]] = set()
    dropped_required_matches = 0
    file_order = 0
    name_source_order: dict[str, int] = {}
    openngc_row_ordinals: dict[tuple[str, str], int] = {}

    override_source = sources.get("nightcrate_match_overrides")
    if override_source is not None and override_source.file_path.exists():
        hashes[override_source.source_id] = file_sha256(override_source.file_path)
    overrides = read_match_overrides(override_source)
    reserved_designations = frozenset(overrides)

    parts_source = sources.get("nightcrate_parts")
    if parts_source is not None and parts_source.file_path.exists():
        hashes[parts_source.source_id] = file_sha256(parts_source.file_path)

    common_names_source = sources.get("nightcrate_common_names")
    if common_names_source is not None and common_names_source.file_path.exists():
        hashes[common_names_source.source_id] = file_sha256(common_names_source.file_path)
    listed_names = read_common_names(common_names_source)

    def register_name_source(source_id: str) -> None:
        if source_id not in name_source_order:
            name_source_order[source_id] = len(name_source_order)

    def add_name_contribution(
        index: int,
        source_id: str,
        row_ordinal: int,
        text: object,
    ) -> None:
        names = split_common_names(str(text) if text is not None else None)
        if names:
            register_name_source(source_id)
            drafts[index].merged_name_contributions.append(
                (name_source_order[source_id], row_ordinal, names)
            )

    def record_entry(source_id: str, source_key: str, catalog_id: str, index: int) -> None:
        """Record one logical catalog contribution at the point it resolves."""
        key = (source_id, source_key, catalog_id, index)
        if key not in resolved_entry_keys:
            resolved_entry_keys.add(key)
            resolved_entries.append(SourceEntry(*key))

    def claim(
        index: int,
        catalog: str,
        identifier: str,
        primary: bool,
        *,
        reserved_ok: bool = False,
    ) -> bool:
        identifier = canonical_identifier(catalog, identifier)
        key = (catalog, identifier)
        if key in reserved_designations and not reserved_ok:
            return False
        if key in designation_owner:
            return False
        designation_owner[key] = index
        search_owner[_build_search_key(catalog, identifier)] = index
        drafts[index].designations.append((catalog, identifier, primary))
        return True

    def release(catalog: str, identifier: str) -> None:
        """Release one claim from every structure populated by ``claim``."""
        identifier = canonical_identifier(catalog, identifier)
        key = (catalog, identifier)
        owner = designation_owner.pop(key, None)
        if owner is None:
            return
        search_key = _build_search_key(catalog, identifier)
        if search_owner.get(search_key) == owner:
            search_owner.pop(search_key, None)
        drafts[owner].designations = [
            designation for designation in drafts[owner].designations if designation[:2] != key
        ]

    def optional_designation_is_off(catalog: str) -> bool:
        owners = [
            optional
            for optional in registry.OPTIONAL_CATALOGS
            if catalog in optional.designation_catalogs
        ]
        return bool(owners) and not any(optional.catalog_id in on_catalogs for optional in owners)

    def resolve_stated_match(
        source_id: str,
        source_key: str,
        catalog_id: str,
        catalog: str,
        identifier: str,
        make_standalone: Callable[[], int],
        *,
        cross_identifications: tuple[tuple[str, str], ...] = (),
        entry_size_arcmin: float | None = None,
        match_size_ratio_max: float | None = None,
        row_evidence: str | None = None,
        require_match: bool = False,
    ) -> int | None:
        """Apply rule R and return the owning draft index for one catalog row."""
        identifier = canonical_identifier(catalog, identifier)
        own_key = (catalog, identifier)
        match_override = overrides.get(own_key)
        target: int | None = None
        evidence = row_evidence

        if match_override is not None:
            if match_override.action == "assign" and match_override.target is not None:
                target = designation_owner.get(match_override.target)
                if target is not None and evidence is None:
                    evidence = "reviewed list"
            if target is None:
                if require_match:
                    return None
                index = make_standalone()
                claim(index, catalog, identifier, True, reserved_ok=True)
                return index
        else:
            target = designation_owner.get(own_key)
            if target is not None and evidence is None:
                owner = drafts[target]
                if owner.source_id in {"openngc", "openngc_addendum"}:
                    evidence = "OpenNGC alternate"
                else:
                    evidence = f"earlier catalog: {owner.catalog_id}"
            if target is None:
                for target_catalog, target_identifier in cross_identifications:
                    target_identifier = canonical_identifier(target_catalog, target_identifier)
                    candidate = designation_owner.get((target_catalog, target_identifier))
                    if candidate is not None and match_size_ratio_max is not None:
                        target_size = maybe_float(
                            str(drafts[candidate].columns.get("maj_axis_arcmin") or "")
                        )
                        if (
                            entry_size_arcmin is None
                            or target_size is None
                            or entry_size_arcmin <= 0
                            or target_size <= 0
                            or max(entry_size_arcmin, target_size)
                            / min(entry_size_arcmin, target_size)
                            > match_size_ratio_max
                        ):
                            candidate = None
                    if candidate is not None:
                        target = candidate
                        if evidence is None:
                            evidence = "catalog column"
                        break
            if target is None:
                if require_match:
                    return None
                index = make_standalone()
                claim(index, catalog, identifier, True)
                return index

        merges[(source_id, source_key)] = target
        claim(target, catalog, identifier, False, reserved_ok=True)
        stated_matches.append(
            StatedMatch(
                catalog=catalog,
                identifier=identifier,
                target_index=target,
                entry_size_arcmin=entry_size_arcmin,
                target_size_arcmin=maybe_float(
                    str(drafts[target].columns.get("maj_axis_arcmin") or "")
                ),
                evidence=evidence or "",
            )
        )
        return target

    def add_openngc(source_id: str) -> list[tuple[str, object]]:
        nonlocal file_order
        source = sources.get(source_id)
        if source is None or not source.file_path.exists():
            return []
        rows, source_hash = collect_openngc(source)
        hashes[source_id] = source_hash
        register_name_source(source_id)
        duplicates: list[tuple[str, object]] = []
        for row_ordinal, row in enumerate(rows):
            openngc_row_ordinals[(source_id, row.raw_name)] = row_ordinal
            if row.is_duplicate:
                duplicates.append((source_id, row))
                continue
            canonicals = _build_canonical_designations(row)
            if not canonicals:
                canonicals = [("other", row.raw_name)]
            primary_idx = _pick_primary(canonicals)
            primary_catalog, primary_identifier = canonicals[primary_idx]
            primary = _build_display_form(primary_catalog, primary_identifier)
            index = len(drafts)
            drafts.append(
                _Draft(
                    source_id,
                    row.raw_name,
                    _openngc_columns(row, primary),
                    [],
                    file_order,
                    "openngc",
                )
            )
            record_entry(source_id, row.raw_name, "openngc", index)
            file_order += 1
            openngc_rows.append((index, row, canonicals, primary_idx))
        return duplicates

    def resolve_dup(source_id: str, dup: object) -> bool:
        own_designation = None
        if dup.name_catalog and dup.name_identifier:
            own_designation = (
                dup.name_catalog,
                canonical_identifier(dup.name_catalog, dup.name_identifier),
            )
        match_override = overrides.get(own_designation) if own_designation is not None else None
        if match_override is not None and match_override.action == "separate":
            return False

        target: int | None = None
        for catalog, identifier in dup_resolution_targets(dup):
            target = designation_owner.get((catalog, identifier))
            if target is not None:
                break
        if target is None:
            return False
        merges[(source_id, dup.raw_name)] = target
        record_entry(source_id, dup.raw_name, "openngc", target)
        add_name_contribution(
            target,
            source_id,
            openngc_row_ordinals[(source_id, dup.raw_name)],
            dup.common_name,
        )
        if own_designation is not None:
            claim(target, *own_designation, False, reserved_ok=match_override is not None)
        return True

    def dup_resolution_targets(dup: object) -> tuple[tuple[str, str], ...]:
        if dup.name_catalog and dup.name_identifier:
            own_designation = (
                dup.name_catalog,
                canonical_identifier(dup.name_catalog, dup.name_identifier),
            )
            match_override = overrides.get(own_designation)
            if match_override is not None:
                if match_override.action == "assign" and match_override.target is not None:
                    return (match_override.target,)
                return ()
        return dup_targets(dup)

    def dup_targets(dup: object) -> tuple[tuple[str, str], ...]:
        return tuple(
            (catalog, canonical_identifier(catalog, str(identifier)))
            for catalog, identifier in (
                ("ngc", dup.ngc_cross_ref),
                ("ic", dup.ic_cross_ref),
                ("messier", dup.messier_number),
            )
            if identifier
        )

    pending_dups.extend(add_openngc("openngc"))
    pending_dups.extend(add_openngc("openngc_addendum"))

    # Own parsed names outrank every other object's alternate names. Claim all
    # own names before considering dedicated cross-reference columns or the
    # Identifiers field so ownership is independent of source row order.
    for index, row, canonicals, primary_idx in openngc_rows:
        if row.name_catalog is None or row.name_identifier is None:
            continue
        own_name = (
            row.name_catalog,
            canonical_identifier(row.name_catalog, row.name_identifier),
        )
        own_primary = canonicals[primary_idx] == own_name
        claim(index, row.name_catalog, row.name_identifier, own_primary)
        if row.name_catalog == "barnard":
            match_key = _normalise_barn_id(row.name_identifier).casefold()
            openngc_barnard_names[match_key].append(index)

    for index, row, canonicals, primary_idx in openngc_rows:
        own_name = None
        if row.name_catalog is not None and row.name_identifier is not None:
            own_name = (
                row.name_catalog,
                canonical_identifier(row.name_catalog, row.name_identifier),
            )
        for pos, (catalog, identifier) in enumerate(canonicals):
            if catalog != "other" and (catalog, identifier) != own_name:
                claim(index, catalog, identifier, pos == primary_idx)
        for token in row.other_identifiers:
            for ref in parse_other_id(token):
                claim(index, ref.catalog, ref.storage_identifier, False)

    pending_dups = [item for item in pending_dups if not resolve_dup(*item)]
    waiting: dict[tuple[str, str], list[int]] = defaultdict(list)
    ready: deque[int] = deque()
    queued: set[int] = set()
    resolved: set[int] = set()
    for position, (_, dup) in enumerate(pending_dups):
        targets = dup_resolution_targets(dup)
        for target_key in targets:
            waiting[target_key].append(position)
        if any(target_key in designation_owner for target_key in targets):
            ready.append(position)
            queued.add(position)
    while ready:
        position = ready.popleft()
        queued.discard(position)
        if position in resolved or not resolve_dup(*pending_dups[position]):
            continue
        resolved.add(position)
        dup = pending_dups[position][1]
        if not dup.name_catalog or not dup.name_identifier:
            continue
        dependent_key = (
            dup.name_catalog,
            canonical_identifier(dup.name_catalog, dup.name_identifier),
        )
        for dependent in waiting.get(dependent_key, ()):
            if dependent not in resolved and dependent not in queued:
                ready.append(dependent)
                queued.add(dependent)
    unresolved += len(pending_dups) - len(resolved)

    sharpless = sources.get("vizier_sharpless") if "sharpless" in on_catalogs else None
    if sharpless is not None and sharpless.file_path.exists():
        rows, crossrefs, effective_hash = collect_sharpless(sharpless, crossref_path)
        hashes[sharpless.source_id] = effective_hash
        register_name_source(sharpless.source_id)
        for row_ordinal, row in enumerate(rows):
            raw = row.get("Sh2")
            if raw is None or not raw.strip():
                continue
            source_key = raw.strip().lstrip("0") or "0"
            target = None
            target_name = crossrefs.get(source_key)
            if target_name:
                target = search_owner.get(normalize_designation(target_name))
                if target is None:
                    unresolved += 1
            if target is not None:
                merges[(sharpless.source_id, source_key)] = target
                record_entry(sharpless.source_id, source_key, "sharpless", target)
                add_name_contribution(
                    target,
                    sharpless.source_id,
                    row_ordinal,
                    row.get("Names") or row.get("Name"),
                )
                claim(target, "sharpless2", source_key, False)
                continue
            ra_deg = maybe_float(row.get("_RAJ2000"))
            dec_deg = maybe_float(row.get("_DEJ2000"))
            diameter = maybe_float(row.get("Diam"))
            class_raw = maybe_str(row.get("Class"))
            index = len(drafts)
            drafts.append(
                _Draft(
                    sharpless.source_id,
                    source_key,
                    {
                        "primary_designation": f"Sh2-{source_key}",
                        "obj_type": "HII",
                        "raw_obj_type": None,
                        "ra_deg": ra_deg,
                        "dec_deg": dec_deg,
                        "constellation": None,
                        "maj_axis_arcmin": diameter,
                        "min_axis_arcmin": diameter,
                        "position_angle_deg": None,
                        "common_name": maybe_str(row.get("Names") or row.get("Name")),
                        "openngc_notes": f"Sh2 class: {class_raw}" if class_raw else None,
                        "surface_brightness": None,
                        "source_row_hash": row_sha256(
                            {key: value for key, value in row.items() if value is not None}
                        ),
                    },
                    [],
                    file_order,
                    "sharpless",
                )
            )
            record_entry(sharpless.source_id, source_key, "sharpless", index)
            file_order += 1
            claim(index, "sharpless2", source_key, True)

    barnard = sources.get("vizier_barnard") if "barnard" in on_catalogs else None
    if barnard is not None and barnard.file_path.exists():
        rows, source_hash = collect_barnard(barnard)
        hashes[barnard.source_id] = source_hash
        register_name_source(barnard.source_id)
        for row_ordinal, row in enumerate(rows):
            raw = row.get("Barn") or row.get("B")
            if raw is None or not raw.strip():
                continue
            source_key = _normalise_barn_id(raw.strip())
            own_name_targets = openngc_barnard_names.get(source_key.casefold(), ())
            if len(own_name_targets) == 1:
                target = own_name_targets[0]
                merges[(barnard.source_id, source_key)] = target
                record_entry(barnard.source_id, source_key, "barnard", target)
                add_name_contribution(
                    target,
                    barnard.source_id,
                    row_ordinal,
                    row.get("Names"),
                )
                claim(target, "barnard", source_key, False)
                continue
            if len(own_name_targets) > 1:
                unresolved += 1
                logger.warning(
                    "[reconcile] Barnard %s matches multiple OpenNGC own names; "
                    "keeping the objects separate",
                    source_key,
                )
            ra_deg = maybe_float(row.get("_RAJ2000"))
            dec_deg = maybe_float(row.get("_DEJ2000"))
            diameter = maybe_float(row.get("Diam"))
            durch = maybe_str(row.get("Durch"))
            index = len(drafts)
            drafts.append(
                _Draft(
                    barnard.source_id,
                    source_key,
                    {
                        "primary_designation": f"B {source_key}",
                        "obj_type": "DrkN",
                        "raw_obj_type": None,
                        "ra_deg": ra_deg,
                        "dec_deg": dec_deg,
                        "constellation": None,
                        "maj_axis_arcmin": diameter,
                        "min_axis_arcmin": diameter,
                        "position_angle_deg": None,
                        "common_name": maybe_str(row.get("Names")),
                        "openngc_notes": f"Durch: {durch}" if durch else None,
                        "surface_brightness": None,
                        "source_row_hash": row_sha256(
                            {key: value for key, value in row.items() if value is not None}
                        ),
                    },
                    [],
                    file_order,
                    "barnard",
                )
            )
            record_entry(barnard.source_id, source_key, "barnard", index)
            file_order += 1
            claim(index, "barnard", source_key, True)

    # Phase-B collectors are registered by logical catalog id and run in an
    # explicit ownership order, independent of registry/source insertion order.
    unknown_collectors = OBJECT_COLLECTORS.keys() - set(COLLECTOR_ORDER)
    if unknown_collectors:
        names = ", ".join(sorted(unknown_collectors))
        raise RuntimeError(f"collectors missing from COLLECTOR_ORDER: {names}")
    processed_collector_sources: set[str] = set(hashes)
    for collector_catalog_id in COLLECTOR_ORDER:
        collector = OBJECT_COLLECTORS.get(collector_catalog_id)
        if collector is None:
            continue
        optional = registry.optional_catalog(collector_catalog_id)
        source_ids = (
            optional.source_ids
            if optional is not None
            else tuple(
                source.source_id
                for source in sources.values()
                if source.parser == collector_catalog_id
            )
        )
        collector_sources = {
            source_id: source
            for source_id in source_ids
            if (source := sources.get(source_id)) is not None
            and source_id not in processed_collector_sources
            and source.file_path.exists()
        }
        if not collector_sources:
            continue
        processed_collector_sources.update(collector_sources)
        for source_id in collector_sources:
            register_name_source(source_id)
        batch = collector(collector_sources, on_catalogs)
        unexpected_hashes = batch.source_hashes.keys() - collector_sources.keys()
        if unexpected_hashes:
            names = ", ".join(sorted(unexpected_hashes))
            raise ValueError(
                f"collector {collector_catalog_id} returned hashes for unknown sources: {names}"
            )
        hashes.update(batch.source_hashes)
        batch_indexes: dict[tuple[str, str], int] = {}
        source_row_ordinals: dict[str, int] = defaultdict(int)
        for row in batch.objects:
            row_ordinal = source_row_ordinals[row.source_id]
            source_row_ordinals[row.source_id] += 1
            source = collector_sources.get(row.source_id)
            if source is None:
                raise ValueError(
                    f"collector {collector_catalog_id} returned an object for unknown source "
                    f"{row.source_id!r}"
                )
            if row.source_id not in batch.source_hashes:
                raise ValueError(
                    f"collector {collector_catalog_id} omitted the hash for object source "
                    f"{row.source_id!r}"
                )
            active_catalog_ids = tuple(
                dict.fromkeys(
                    catalog_id
                    for catalog_id in (row.catalog_id, *row.also_catalog_ids)
                    if catalog_id in on_catalogs
                )
            )
            if not active_catalog_ids:
                continue
            for release_catalog, release_identifier in row.release_designations:
                release(release_catalog, release_identifier)

            def make_standalone(row: CollectedObject = row) -> int:
                nonlocal file_order
                index = len(drafts)
                drafts.append(
                    _Draft(
                        row.source_id,
                        row.source_key,
                        row.columns,
                        [],
                        file_order,
                        active_catalog_ids[0],
                    )
                )
                file_order += 1
                return index

            if (row.catalog is None) != (row.identifier is None):
                raise ValueError(
                    f"collector row {row.source_id}/{row.source_key} must provide "
                    "both catalog and identifier, or neither"
                )
            if row.catalog is None or row.identifier is None:
                index = make_standalone()
            else:
                index = resolve_stated_match(
                    row.source_id,
                    row.source_key,
                    active_catalog_ids[0],
                    row.catalog,
                    row.identifier,
                    make_standalone,
                    cross_identifications=row.cross_identifications,
                    entry_size_arcmin=(
                        row.match_size_arcmin
                        if row.match_size_arcmin is not None
                        else (
                            float(row.columns["maj_axis_arcmin"])
                            if row.columns.get("maj_axis_arcmin") is not None
                            else None
                        )
                    ),
                    match_size_ratio_max=row.match_size_ratio_max,
                    row_evidence=row.evidence,
                    require_match=row.require_match,
                )
                if index is None:
                    dropped_required_matches += 1
                    logger.info(
                        "[reconcile] dropped required match %s/%s with no owner",
                        row.source_id,
                        row.source_key,
                    )
                    continue
                if (row.source_id, row.source_key) in merges:
                    add_name_contribution(
                        index,
                        row.source_id,
                        row_ordinal,
                        row.columns.get("common_name"),
                    )
            batch_indexes[(row.source_id, row.source_key)] = index
            for catalog, identifier in row.extra_designations:
                claim(index, catalog, identifier, False)
            for catalog_id in active_catalog_ids:
                record_entry(row.source_id, row.source_key, catalog_id, index)

        for collected_group in batch.groups:
            if (
                collected_group.whole_key is not None
                and collected_group.whole_key not in batch_indexes
            ):
                continue
            whole_index = (
                batch_indexes.get(collected_group.whole_key)
                if collected_group.whole_key is not None
                else None
            )
            member_indexes = [
                batch_indexes[key] for key in collected_group.member_keys if key in batch_indexes
            ]
            for catalog, identifier in collected_group.member_designations:
                owner = designation_owner.get((catalog, canonical_identifier(catalog, identifier)))
                if owner is not None:
                    member_indexes.append(owner)
            deduplicated_members = tuple(dict.fromkeys(member_indexes))
            if whole_index is not None:
                deduplicated_members = tuple(
                    member_index
                    for member_index in deduplicated_members
                    if member_index != whole_index
                )
            if deduplicated_members:
                groups.append(
                    NewGroup(
                        collected_group.catalog,
                        collected_group.identifier,
                        whole_index,
                        deduplicated_members,
                    )
                )

    # Reviewed assign rows without their own loaded entry act as aliases.  An
    # optional designation follows its catalog state; always-loaded catalogs
    # have no optional owner and therefore always participate.
    for designation, match_override in overrides.items():
        if match_override.action != "assign" or match_override.target is None:
            continue
        if designation in designation_owner or optional_designation_is_off(designation[0]):
            continue
        target = designation_owner.get(match_override.target)
        if target is not None:
            claim(target, *designation, False, reserved_ok=True)

    # A preferred canonical designation can lose its claim to another
    # OpenNGC object's own name.  Choose the primary only after every claim is
    # settled so the stored name and is_primary row always describe a
    # designation this object actually owns.  Own names were claimed first,
    # so _pick_primary's first-seen fallback selects the own name when none of
    # the priority catalogs is available.
    for index, _row, _canonicals, _primary_idx in openngc_rows:
        draft = drafts[index]
        if not draft.designations:
            continue
        primary_idx = _pick_primary(
            [(catalog, identifier) for catalog, identifier, _primary in draft.designations]
        )
        primary_catalog, primary_identifier, _primary = draft.designations[primary_idx]
        draft.columns["primary_designation"] = _build_display_form(
            primary_catalog, primary_identifier
        )
        draft.designations = [
            (catalog, identifier, position == primary_idx)
            for position, (catalog, identifier, _primary) in enumerate(draft.designations)
        ]

    if parts_source is not None and parts_source.file_path.exists():
        existing_group_keys = {
            (group.catalog, canonical_identifier(group.catalog, group.identifier))
            for group in groups
        }
        parts_group_owners: dict[tuple[str, str], int] = {}
        members_by_whole: dict[int, list[int]] = defaultdict(list)
        for row in _read_editorial_csv(parts_source.file_path):
            whole_text = row.get("whole_designation", "")
            part_text = row.get("part_designation", "")
            if not whole_text or not part_text:
                continue
            whole_index = designation_owner.get(_designation_key(whole_text))
            part_index = designation_owner.get(_designation_key(part_text))
            if whole_index is None or part_index is None:
                continue
            primary = next(
                (
                    (catalog, identifier)
                    for catalog, identifier, is_primary in drafts[whole_index].designations
                    if is_primary
                ),
                None,
            )
            if primary is None:
                continue
            group_key = (primary[0], canonical_identifier(*primary))
            previous_whole = parts_group_owners.get(group_key)
            if group_key in existing_group_keys or (
                previous_whole is not None and previous_whole != whole_index
            ):
                logger.warning(
                    "[reconcile] skipping parts row %r -> %r; group %s %s already exists",
                    whole_text,
                    part_text,
                    *primary,
                )
                continue
            parts_group_owners[group_key] = whole_index
            if part_index not in members_by_whole[whole_index]:
                members_by_whole[whole_index].append(part_index)
        for whole_index, member_indexes in members_by_whole.items():
            primary = next(
                (
                    (catalog, identifier)
                    for catalog, identifier, is_primary in drafts[whole_index].designations
                    if is_primary
                ),
                None,
            )
            if primary is not None:
                groups.append(NewGroup(*primary, whole_index, tuple(member_indexes)))

    listed_by_object: dict[int, ListedNames] = {}
    for listed in (item for item in listed_names if item.target == "object"):
        key = _designation_key(listed.designation)
        object_index = designation_owner.get(key)
        if object_index is None:
            message = "[reconcile] common-name designation %r did not resolve; skipping"
            if optional_designation_is_off(key[0]):
                logger.debug(message, listed.designation)
            else:
                logger.warning(message, listed.designation)
            continue
        previous = listed_by_object.get(object_index)
        if previous is not None:
            logger.warning(
                "[reconcile] common-name designations %r and %r resolve to one object; "
                "merging their names",
                previous.designation,
                listed.designation,
            )
            listed_by_object[object_index] = ListedNames(
                previous.designation,
                previous.target,
                merge_names(previous.names, listed.names),
                previous.removals | listed.removals,
            )
        else:
            listed_by_object[object_index] = listed

    final_names_by_object: list[tuple[str, ...]] = []
    for index, draft in enumerate(drafts):
        contributions = sorted(draft.merged_name_contributions, key=lambda item: item[:2])
        catalog_names = merge_names(
            draft.catalog_names,
            *(names for _source_order, _row_ordinal, names in contributions),
        )
        listed = listed_by_object.get(index)
        if listed is None:
            names = catalog_names
            draft.columns["common_name_augmented"] = 0
        else:
            names = tuple(
                name
                for name in merge_names(listed.names, catalog_names)
                if name.casefold() not in listed.removals
            )
            draft.columns["common_name_augmented"] = 1
        draft.columns["common_name"] = names[0] if names else None
        final_names_by_object.append(names)

    group_indexes = {
        (group.catalog, canonical_identifier(group.catalog, group.identifier)): index
        for index, group in enumerate(groups)
    }
    for listed in (item for item in listed_names if item.target == "group"):
        key = _designation_key(listed.designation)
        group_index = group_indexes.get(key)
        if group_index is None:
            message = "[reconcile] common-name group %r did not resolve; skipping"
            if optional_designation_is_off(key[0]):
                logger.debug(message, listed.designation)
            else:
                logger.warning(message, listed.designation)
            continue
        groups[group_index] = replace(groups[group_index], common_name=listed.names[0])

    constellation_drafts: list[tuple[_Draft, float, float]] = []
    for draft in drafts:
        if (
            draft.columns.get("constellation") is not None
            or draft.columns.get("ra_deg") is None
            or draft.columns.get("dec_deg") is None
        ):
            continue
        try:
            ra_deg = float(draft.columns["ra_deg"])
            dec_deg = float(draft.columns["dec_deg"])
        except TypeError, ValueError:
            continue
        if not math.isfinite(ra_deg) or not math.isfinite(dec_deg) or not -90 <= dec_deg <= 90:
            continue
        constellation_drafts.append((draft, ra_deg % 360.0, dec_deg))
    if constellation_drafts:
        try:
            constellations = constellations_for_coords(
                [ra_deg for _draft, ra_deg, _dec_deg in constellation_drafts],
                [dec_deg for _draft, _ra_deg, dec_deg in constellation_drafts],
            )
        except Exception:  # noqa: BLE001 - catalog coordinates remain usable without it
            logger.exception(
                "[reconcile] batched constellation lookup failed for %d catalog objects; "
                "retrying individually",
                len(constellation_drafts),
            )
            for draft, ra_deg, dec_deg in constellation_drafts:
                try:
                    draft.columns["constellation"] = constellation_for_coords(ra_deg, dec_deg)
                except Exception:  # noqa: BLE001 - isolate invalid catalog coordinates
                    draft.columns["constellation"] = None
        else:
            for (draft, _ra_deg, _dec_deg), constellation in zip(
                constellation_drafts, constellations, strict=True
            ):
                draft.columns["constellation"] = constellation

    objects = tuple(
        NewObject(
            draft.source_id,
            draft.source_key,
            draft.columns,
            tuple(draft.designations),
            draft.file_order,
            draft.catalog_id,
            final_names_by_object[index][1:],
        )
        for index, draft in enumerate(drafts)
    )
    if dropped_required_matches:
        logger.info(
            "[reconcile] dropped %d rows that require an existing match",
            dropped_required_matches,
        )
    return ObjectSet(
        objects,
        merges,
        hashes,
        unresolved,
        dict(sources),
        tuple(resolved_entries),
        groups=tuple(groups),
        stated_matches=tuple(stated_matches),
    )


def _source_row_id(cur: sqlite3.Cursor, source: CatalogSource, source_hash: str) -> int:
    cur.execute("SELECT id FROM dso_catalog_source WHERE source_id = ?", (source.source_id,))
    row = cur.fetchone()
    values = (
        source.category,
        source.display_name,
        source.version,
        source.source_url,
        str(source.file_path),
        source_hash,
        source.license,
        source.attribution,
    )
    if row is not None:
        cur.execute(
            """
            UPDATE dso_catalog_source SET
                category = ?, display_name = ?, version = ?, source_url = ?,
                file_path = ?, file_hash = ?, license = ?, attribution = ?
            WHERE id = ?
            """,
            (*values, row[0]),
        )
        return int(row[0])
    cur.execute(
        """
        INSERT INTO dso_catalog_source (
            source_id, category, display_name, version, source_url, file_path,
            file_hash, license, attribution, row_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (source.source_id, *values),
    )
    if cur.lastrowid is None:
        raise RuntimeError("dso_catalog_source INSERT returned no row id")
    return int(cur.lastrowid)


def apply_object_set(
    conn: sqlite3.Connection,
    new: ObjectSet,
    enrichment_source_ids: tuple[str, ...],
    *,
    removed_catalogs: frozenset[str] = frozenset(),
    dry_run: bool = False,
) -> ReconcileReport:
    """Apply a complete object set atomically while preserving user identity."""
    cur = conn.cursor()
    cur.row_factory = sqlite3.Row
    inserted = updated = reactivated = merged = removed = kept_linked = kept = deleted = (
        transferred
    ) = 0
    current_entries: list[SourceEntry] = []
    seen_entries: set[tuple[str, str, str, int]] = set()
    entry_catalogs: dict[tuple[str, str], str] = {}

    def add_entry(entry: SourceEntry) -> None:
        key = (entry.source_id, entry.source_key, entry.catalog_id, entry.object_index)
        if key not in seen_entries:
            seen_entries.add(key)
            current_entries.append(entry)

    for entry in new.entries:
        if not 0 <= entry.object_index < len(new.objects):
            continue
        entry_catalogs.setdefault((entry.source_id, entry.source_key), entry.catalog_id)
        obj = new.objects[entry.object_index]
        own_entry = (entry.source_id, entry.source_key) == (obj.source_id, obj.source_key)
        merged_entry = new.merges.get((entry.source_id, entry.source_key)) == entry.object_index
        if own_entry or merged_entry:
            add_entry(entry)
    for index, obj in enumerate(new.objects):
        add_entry(SourceEntry(obj.source_id, obj.source_key, obj.catalog_id, index))
    for (source_id, source_key), object_index in new.merges.items():
        catalog_id = entry_catalogs.get((source_id, source_key), "openngc")
        add_entry(SourceEntry(source_id, source_key, catalog_id, object_index))
    object_source_ids = {obj.source_id for obj in new.objects} | {
        entry.source_id for entry in current_entries
    }
    object_source_ids.update(
        source_id for source_id in OBJECT_SOURCE_IDS if source_id in new.hashes
    )
    object_source_ids.update(
        source_id for source_id in EDITORIAL_OBJECT_SOURCE_IDS if source_id in new.hashes
    )
    source_counts = {source_id: 0 for source_id in object_source_ids if source_id in new.hashes}
    for obj in new.objects:
        if obj.source_id in source_counts:
            source_counts[obj.source_id] += 1
    try:
        conn.execute("BEGIN")
        cur.execute(
            """
            SELECT d.*, s.source_id, s.file_hash AS stored_file_hash
            FROM dso d JOIN dso_catalog_source s ON s.id = d.source_catalog_id
            ORDER BY d.id
            """
        )
        existing = [dict(row) for row in cur.fetchall()]
        cur.execute("SELECT * FROM dso_designation ORDER BY id")
        old_designations = [dict(row) for row in cur.fetchall()]
        cur.execute(
            """
            SELECT e.source_catalog_id, s.source_id, e.source_key,
                   e.catalog_id, e.dso_id
            FROM dso_source_entry e
            JOIN dso_catalog_source s ON s.id = e.source_catalog_id
            ORDER BY e.source_catalog_id, e.source_key, e.catalog_id
            """
        )
        old_entries = [dict(row) for row in cur.fetchall()]
        cur.execute("SELECT source_id, file_hash, keys_assigned FROM dso_catalog_source")
        stored_state = {
            str(row[0]): {"file_hash": str(row[1]), "keys_assigned": bool(row[2])}
            for row in cur.fetchall()
        }
        reference_tables = dso_reference_tables(cur)
        referenced_for_removal = referenced_dso_ids(
            cur,
            exclude=frozenset({"project_dso"}),
            reference_tables=reference_tables,
        )

        existing_by_id: dict[int, dict[str, object]] = {}
        existing_by_source_key: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
        keyless_by_designation: dict[str, dict[str, list[dict[str, object]]]] = defaultdict(
            lambda: defaultdict(list)
        )
        keyless_by_hash: dict[str, dict[str, list[dict[str, object]]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for old in existing:
            old_id = int(old["id"])
            source_id = str(old["source_id"])
            existing_by_id[old_id] = old
            if old["source_key"] is not None:
                existing_by_source_key[(source_id, str(old["source_key"]))].append(old)
                continue
            keyless_by_designation[source_id][str(old["primary_designation"])].append(old)
            keyless_by_hash[source_id][str(old["source_row_hash"])].append(old)

        new_by_source: dict[str, list[int]] = defaultdict(list)
        new_by_designation: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
        new_by_hash: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
        for index, obj in enumerate(new.objects):
            new_by_source[obj.source_id].append(index)
            new_by_designation[obj.source_id][str(obj.columns["primary_designation"])].append(index)
            new_by_hash[obj.source_id][str(obj.columns["source_row_hash"])].append(index)

        source_db_ids: dict[str, int] = {}
        for source_id in object_source_ids:
            if source_id not in new.hashes:
                continue
            source = new._sources[source_id]
            source_db_ids[source_id] = _source_row_id(cur, source, new.hashes[source_id])

        matched_new: dict[int, int] = {}
        claimed_old: set[int] = set()

        def pair(new_index: int, old: dict[str, object]) -> None:
            matched_new[new_index] = int(old["id"])
            claimed_old.add(int(old["id"]))

        for index, obj in enumerate(new.objects):
            candidates = [
                row
                for row in existing_by_source_key.get((obj.source_id, obj.source_key), ())
                if int(row["id"]) not in claimed_old
            ]
            if len(candidates) == 1:
                pair(index, candidates[0])

        for index, obj in enumerate(new.objects):
            if index in matched_new or obj.source_id not in {"openngc", "openngc_addendum"}:
                continue
            other_source = "openngc_addendum" if obj.source_id == "openngc" else "openngc"
            candidates = [
                row
                for row in existing_by_source_key.get((other_source, obj.source_key), ())
                if int(row["id"]) not in claimed_old
            ]
            if len(candidates) == 1:
                pair(index, candidates[0])

        entries_by_object: dict[int, list[SourceEntry]] = defaultdict(list)
        for entry in current_entries:
            entries_by_object[entry.object_index].append(entry)
        old_ids_by_entry: dict[tuple[str, str], set[int]] = defaultdict(set)
        for entry in old_entries:
            old_ids_by_entry[(str(entry["source_id"]), str(entry["source_key"]))].add(
                int(entry["dso_id"])
            )
        for index, obj in enumerate(new.objects):
            if index in matched_new:
                continue
            contributing = {
                (obj.source_id, obj.source_key),
                *((entry.source_id, entry.source_key) for entry in entries_by_object[index]),
            }
            candidate_ids: set[int] = set()
            for key in contributing:
                candidate_ids.update(
                    int(row["id"])
                    for row in existing_by_source_key.get(key, ())
                    if int(row["id"]) not in claimed_old
                )
                candidate_ids.update(
                    old_id for old_id in old_ids_by_entry.get(key, ()) if old_id not in claimed_old
                )
            if len(candidate_ids) == 1:
                pair(index, existing_by_id[candidate_ids.pop()])
                transferred += 1
            elif len(candidate_ids) > 1:
                logger.warning(
                    "[reconcile] contribution identity for %s/%s is ambiguous; inserting",
                    obj.source_id,
                    obj.source_key,
                )

        openngc_source_ids = ("openngc", "openngc_addendum")
        combined_openngc_old_by_hash: dict[str, list[dict[str, object]]] = defaultdict(list)
        combined_openngc_new_by_hash: dict[str, list[int]] = defaultdict(list)
        for source_id in openngc_source_ids:
            state = stored_state.get(source_id)
            if state is None or not state["keys_assigned"]:
                for row_hash, old_group in keyless_by_hash[source_id].items():
                    combined_openngc_old_by_hash[row_hash].extend(
                        row for row in old_group if int(row["id"]) not in claimed_old
                    )
            for row_hash, new_group in new_by_hash[source_id].items():
                combined_openngc_new_by_hash[row_hash].extend(
                    index for index in new_group if index not in matched_new
                )
        for row_hash, old_candidates in combined_openngc_old_by_hash.items():
            new_candidates = combined_openngc_new_by_hash.get(row_hash, ())
            if len(old_candidates) == 1 and len(new_candidates) == 1:
                pair(new_candidates[0], old_candidates[0])

        for source_id in object_source_ids:
            if not new_by_source.get(source_id):
                continue
            state = stored_state.get(source_id)
            if state is not None and state["keys_assigned"]:
                continue
            unchanged = state is not None and state["file_hash"] == new.hashes.get(source_id)
            for row_hash, old_group in keyless_by_hash[source_id].items():
                old_candidates = [row for row in old_group if int(row["id"]) not in claimed_old]
                new_candidates = [
                    index
                    for index in new_by_hash[source_id].get(row_hash, ())
                    if index not in matched_new
                ]
                if len(old_candidates) == 1 and len(new_candidates) == 1:
                    pair(new_candidates[0], old_candidates[0])
            if unchanged:
                for designation, old_group in keyless_by_designation[source_id].items():
                    old_group = [row for row in old_group if int(row["id"]) not in claimed_old]
                    new_group = [
                        index
                        for index in new_by_designation[source_id].get(designation, ())
                        if index not in matched_new
                    ]
                    old_group.sort(key=lambda row: int(row["id"]))
                    new_group.sort(key=lambda index: new.objects[index].file_order)
                    for index, old in zip(new_group, old_group, strict=False):
                        pair(index, old)

        object_ids: dict[int, int] = {}
        for index, obj in enumerate(new.objects):
            source_db_id = source_db_ids[obj.source_id]
            if index not in matched_new:
                columns = [*obj.columns, "source_catalog_id", "source_key", "active"]
                values = [*obj.columns.values(), source_db_id, obj.source_key, 1]
                placeholders = ", ".join("?" for _ in columns)
                names = ", ".join(columns)
                cur.execute(
                    f"INSERT INTO dso ({names}) VALUES ({placeholders})",  # noqa: S608  # nosec B608
                    values,
                )
                if cur.lastrowid is None:
                    raise RuntimeError("dso INSERT returned no row id")
                object_ids[index] = int(cur.lastrowid)
                inserted += 1
                continue

            dso_id = matched_new[index]
            old = existing_by_id[dso_id]
            changed_columns = [
                column for column, value in obj.columns.items() if old[column] != value
            ]
            reset_surface_brightness_flag = "surface_brightness" in changed_columns
            assignments = [f"{column} = ?" for column in changed_columns]
            values = [obj.columns[column] for column in changed_columns]
            if old["source_catalog_id"] != source_db_id:
                assignments.append("source_catalog_id = ?")
                values.append(source_db_id)
            if old["source_key"] != obj.source_key:
                assignments.append("source_key = ?")
                values.append(obj.source_key)
            if not old["active"]:
                assignments.append("active = 1")
            if reset_surface_brightness_flag:
                assignments.append("surface_brightness_augmented = 0")
            if assignments:
                values.append(dso_id)
                cur.execute(
                    f"UPDATE dso SET {', '.join(assignments)} WHERE id = ?",  # noqa: S608  # nosec B608
                    values,
                )
                updated += 1
            object_ids[index] = dso_id
            if not old["active"]:
                reactivated += 1

        cur.execute("DELETE FROM dso_designation")
        owned_designations: set[tuple[str, str]] = set()
        for index, obj in enumerate(new.objects):
            for catalog, identifier, is_primary in obj.designations:
                owned_designations.add((catalog, identifier))
                cur.execute(
                    """
                    INSERT INTO dso_designation
                        (dso_id, catalog, identifier, display_form, search_key, is_primary)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        object_ids[index],
                        catalog,
                        identifier,
                        _build_display_form(catalog, identifier),
                        _build_search_key(catalog, identifier),
                        int(is_primary),
                    ),
                )

        cur.execute("DELETE FROM dso_group")
        for group in new.groups:
            display_form = _build_display_form(group.catalog, group.identifier)
            cur.execute(
                """
                INSERT INTO dso_group (
                    catalog, identifier, display_form, search_key, whole_dso_id, common_name
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    group.catalog,
                    canonical_identifier(group.catalog, group.identifier),
                    display_form,
                    normalize_designation(display_form),
                    object_ids[group.whole_index] if group.whole_index is not None else None,
                    group.common_name,
                ),
            )
            if cur.lastrowid is None:
                raise RuntimeError("dso_group INSERT returned no row id")
            group_id = int(cur.lastrowid)
            cur.executemany(
                "INSERT INTO dso_group_member (group_id, dso_id) VALUES (?, ?)",
                (
                    (group_id, object_ids[member_index])
                    for member_index in dict.fromkeys(group.member_indexes)
                ),
            )

        retained_unclaimed: set[int] = set()
        entries_by_old: dict[int, list[dict[str, object]]] = defaultdict(list)
        for entry in old_entries:
            entries_by_old[int(entry["dso_id"])].append(entry)
        for old in existing:
            old_id = int(old["id"])
            if old_id in claimed_old:
                continue
            merge_target = None
            if old["source_key"] is not None:
                merge_target = new.merges.get((str(old["source_id"]), str(old["source_key"])))
            if merge_target is not None:
                move_user_links(
                    cur,
                    old_id,
                    object_ids[merge_target],
                    str(old["primary_designation"]),
                )
                merged += 1
                if count_references(cur, old_id, reference_tables=reference_tables) == 0:
                    cur.execute("DELETE FROM dso WHERE id = ?", (old_id,))
                else:
                    cur.execute(
                        "UPDATE dso SET active = 0, source_key = NULL WHERE id = ?",
                        (old_id,),
                    )
                    old["source_key"] = None
                    retained_unclaimed.add(old_id)
                    kept += 1
                    logger.warning(
                        "[reconcile] merged DSO %d retained inactive due to unknown references",
                        old_id,
                    )
                continue
            previous_entries = entries_by_old.get(old_id, [])
            entry_catalogs = {str(entry["catalog_id"]) for entry in previous_entries}
            source_catalogs = {
                catalog.catalog_id for catalog in catalogs_for_source(str(old["source_id"]))
            }
            only_removed = bool(entry_catalogs) and entry_catalogs <= removed_catalogs
            if not previous_entries:
                only_removed = bool(source_catalogs) and source_catalogs <= removed_catalogs
            if only_removed:
                if old_id not in referenced_for_removal:
                    cur.execute("DELETE FROM project_dso WHERE dso_id = ?", (old_id,))
                    cur.execute("DELETE FROM dso WHERE id = ?", (old_id,))
                    deleted += 1
                    continue
                retained_unclaimed.add(old_id)
                if old["active"]:
                    cur.execute("UPDATE dso SET active = 0 WHERE id = ?", (old_id,))
                    removed += 1
                    kept_linked += 1
                continue

            retained_unclaimed.add(old_id)
            if old["active"]:
                cur.execute("UPDATE dso SET active = 0 WHERE id = ?", (old_id,))
                removed += 1

        cur.execute(
            """
            DELETE FROM dso_other_name
            WHERE EXISTS (
                SELECT 1 FROM dso
                WHERE dso.id = dso_other_name.dso_id AND dso.active = 1
            )
            """
        )
        for index, obj in enumerate(new.objects):
            cur.executemany(
                "INSERT INTO dso_other_name (dso_id, name, position) VALUES (?, ?, ?)",
                (
                    (object_ids[index], name, position)
                    for position, name in enumerate(obj.other_names, start=1)
                ),
            )

        for designation in old_designations:
            catalog = str(designation["catalog"])
            identifier = canonical_legacy_identifier(catalog, str(designation["identifier"]))
            key = (catalog, identifier)
            old_id = int(designation["dso_id"])
            if old_id not in retained_unclaimed or key in owned_designations:
                continue
            display_form = _build_display_form(catalog, identifier)
            cur.execute(
                """
                INSERT INTO dso_designation
                    (dso_id, catalog, identifier, display_form, search_key, is_primary)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    old_id,
                    catalog,
                    identifier,
                    display_form,
                    _build_search_key(catalog, identifier),
                    designation["is_primary"],
                ),
            )
            old = existing_by_id[old_id]
            if designation["is_primary"] and old["primary_designation"] != display_form:
                cur.execute(
                    "UPDATE dso SET primary_designation = ? WHERE id = ?",
                    (display_form, old_id),
                )
                old["primary_designation"] = display_form
            owned_designations.add(key)

        cur.execute("DELETE FROM dso_source_entry")
        for entry in current_entries:
            source_db_id = source_db_ids.get(entry.source_id)
            if source_db_id is None:
                continue
            cur.execute(
                """
                INSERT INTO dso_source_entry
                    (source_catalog_id, source_key, catalog_id, dso_id)
                VALUES (?, ?, ?, ?)
                """,
                (
                    source_db_id,
                    entry.source_key,
                    entry.catalog_id,
                    object_ids[entry.object_index],
                ),
            )
        for old_id in retained_unclaimed:
            old = existing_by_id[old_id]
            if old["source_key"] is None:
                continue
            retained_entries = entries_by_old.get(old_id, [])
            if retained_entries:
                for entry in retained_entries:
                    cur.execute(
                        """
                        INSERT OR IGNORE INTO dso_source_entry
                            (source_catalog_id, source_key, catalog_id, dso_id)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            entry["source_catalog_id"],
                            entry["source_key"],
                            entry["catalog_id"],
                            old_id,
                        ),
                    )
                continue
            for catalog in catalogs_for_source(str(old["source_id"])):
                cur.execute(
                    """
                    INSERT OR IGNORE INTO dso_source_entry
                        (source_catalog_id, source_key, catalog_id, dso_id)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        old["source_catalog_id"],
                        old["source_key"],
                        catalog.catalog_id,
                        old_id,
                    ),
                )

        for source_id, source_db_id in source_db_ids.items():
            cur.execute(
                """
                UPDATE dso_catalog_source
                SET file_hash = ?, row_count = ?, loaded_at = datetime('now'), keys_assigned = 1
                WHERE id = ?
                """,
                (new.hashes[source_id], source_counts[source_id], source_db_id),
            )
        invalidated = ("nightcrate_augment", *enrichment_source_ids)
        if invalidated:
            placeholders = ", ".join("?" for _ in invalidated)
            cur.execute(
                f"UPDATE dso_catalog_source SET file_hash = '' WHERE source_id IN ({placeholders})",  # noqa: S608  # nosec B608
                invalidated,
            )
        applied: dict[str, str] = {}
        catalog_states = {**new.catalog_states}
        catalog_states.update({catalog_id: "removed" for catalog_id in removed_catalogs})
        for catalog_id, state in catalog_states.items():
            if state == "off":
                cur.execute("DELETE FROM dso_catalog_applied WHERE catalog_id = ?", (catalog_id,))
                applied[catalog_id] = "off"
                continue
            cur.execute(
                """
                INSERT INTO dso_catalog_applied (catalog_id, state)
                VALUES (?, ?)
                ON CONFLICT(catalog_id) DO UPDATE SET
                    state = excluded.state,
                    applied_at = datetime('now')
                """,
                (catalog_id, state),
            )
            applied[catalog_id] = state
        if dry_run:
            conn.rollback()
        else:
            conn.commit()
    except Exception:
        conn.rollback()
        raise

    return ReconcileReport(
        source_counts=source_counts,
        inserted=inserted,
        updated=updated,
        reactivated=reactivated,
        merged=merged,
        removed=removed,
        kept_linked=kept_linked,
        kept_inactive_merge=kept,
        deleted=deleted,
        transferred=transferred,
        applied=applied,
    )
