"""Pure catalog collection and transactional DSO identity reconciliation."""

from __future__ import annotations

import logging
import sqlite3
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path

from nightcrate.catalog_loader._common import maybe_float, maybe_str, normalize_designation
from nightcrate.catalog_loader.barnard_loader import _normalise_barn_id, collect_barnard
from nightcrate.catalog_loader.crossref_parser import parse_other_id
from nightcrate.catalog_loader.hash import file_sha256, row_sha256
from nightcrate.catalog_loader.loader import (
    _build_canonical_designations,
    _build_display_form,
    _build_search_key,
    _pick_primary,
    collect_openngc,
)
from nightcrate.catalog_loader.registry import CatalogSource
from nightcrate.catalog_loader.sharpless_loader import collect_sharpless
from nightcrate.catalog_loader.user_links import count_references, move_user_links
from nightcrate.services.astronomy import constellation_for_coords

logger = logging.getLogger("nightcrate.catalog_loader.reconcile")

OBJECT_SOURCE_IDS: tuple[str, ...] = (
    "openngc",
    "openngc_addendum",
    "vizier_sharpless",
    "vizier_barnard",
)


@dataclass(frozen=True, slots=True)
class NewObject:
    source_id: str
    source_key: str
    columns: dict[str, object]
    designations: tuple[tuple[str, str, bool], ...]
    file_order: int


@dataclass(frozen=True, slots=True)
class ObjectSet:
    objects: tuple[NewObject, ...]
    merges: dict[tuple[str, str], int]
    hashes: dict[str, str]
    unresolved: int
    _sources: dict[str, CatalogSource] = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class ReconcileReport:
    source_counts: dict[str, int]
    inserted: int = 0
    updated: int = 0
    reactivated: int = 0
    merged: int = 0
    removed: int = 0
    kept_inactive_merge: int = 0


@dataclass(slots=True)
class _Draft:
    source_id: str
    source_key: str
    columns: dict[str, object]
    designations: list[tuple[str, str, bool]]
    file_order: int


def _constellation(ra_deg: float | None, dec_deg: float | None) -> str | None:
    if ra_deg is None or dec_deg is None:
        return None
    try:
        return constellation_for_coords(ra_deg, dec_deg)
    except Exception:  # noqa: BLE001 - catalog coordinates remain usable without it
        return None


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


def build_object_set(sources: dict[str, CatalogSource], crossref_path: Path | None) -> ObjectSet:
    """Collect all present object catalogs and resolve ownership in memory."""
    drafts: list[_Draft] = []
    designation_owner: dict[tuple[str, str], int] = {}
    search_owner: dict[str, int] = {}
    merges: dict[tuple[str, str], int] = {}
    hashes: dict[str, str] = {}
    unresolved = 0
    pending_dups: list[tuple[str, object]] = []
    file_order = 0

    def claim(index: int, catalog: str, identifier: str, primary: bool) -> bool:
        key = (catalog, identifier)
        if key in designation_owner:
            return False
        designation_owner[key] = index
        search_owner[_build_search_key(catalog, identifier)] = index
        drafts[index].designations.append((catalog, identifier, primary))
        return True

    def add_openngc(source_id: str) -> list[tuple[str, object]]:
        nonlocal file_order
        source = sources.get(source_id)
        if source is None or not source.file_path.exists():
            return []
        rows, source_hash = collect_openngc(source)
        hashes[source_id] = source_hash
        duplicates: list[tuple[str, object]] = []
        for row in rows:
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
                )
            )
            file_order += 1
            for pos, (catalog, identifier) in enumerate(canonicals):
                if catalog != "other":
                    claim(index, catalog, identifier, pos == primary_idx)
            for ref in parse_other_id(row.raw_other_id):
                claim(index, ref.catalog, ref.identifier, False)
        return duplicates

    def resolve_dup(source_id: str, dup: object) -> bool:
        target: int | None = None
        for catalog, identifier in dup_targets(dup):
            target = designation_owner.get((catalog, identifier))
            if target is not None:
                break
        if target is None:
            return False
        merges[(source_id, dup.raw_name)] = target
        if dup.name_catalog and dup.name_identifier:
            claim(target, dup.name_catalog, dup.name_identifier, False)
        return True

    def dup_targets(dup: object) -> tuple[tuple[str, str], ...]:
        return tuple(
            (catalog, str(identifier))
            for catalog, identifier in (
                ("ngc", dup.ngc_cross_ref),
                ("ic", dup.ic_cross_ref),
                ("messier", dup.messier_number),
            )
            if identifier
        )

    main_dups = add_openngc("openngc")
    pending_dups.extend(item for item in main_dups if not resolve_dup(*item))
    addendum_dups = add_openngc("openngc_addendum")
    pending_dups.extend(item for item in addendum_dups if not resolve_dup(*item))
    waiting: dict[tuple[str, str], list[int]] = defaultdict(list)
    ready: deque[int] = deque()
    queued: set[int] = set()
    resolved: set[int] = set()
    for position, (_, dup) in enumerate(pending_dups):
        targets = dup_targets(dup)
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
        for dependent in waiting.get((dup.name_catalog, dup.name_identifier), ()):
            if dependent not in resolved and dependent not in queued:
                ready.append(dependent)
                queued.add(dependent)
    unresolved += len(pending_dups) - len(resolved)

    sharpless = sources.get("vizier_sharpless")
    if sharpless is not None and sharpless.file_path.exists():
        rows, crossrefs, effective_hash = collect_sharpless(sharpless, crossref_path)
        hashes[sharpless.source_id] = effective_hash
        for row in rows:
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
                        "constellation": _constellation(ra_deg, dec_deg),
                        "maj_axis_arcmin": diameter,
                        "min_axis_arcmin": diameter,
                        "position_angle_deg": None,
                        "common_name": None,
                        "openngc_notes": f"Sh2 class: {class_raw}" if class_raw else None,
                        "surface_brightness": None,
                        "source_row_hash": row_sha256(
                            {key: value for key, value in row.items() if value is not None}
                        ),
                    },
                    [],
                    file_order,
                )
            )
            file_order += 1
            claim(index, "sharpless2", source_key, True)

    barnard = sources.get("vizier_barnard")
    if barnard is not None and barnard.file_path.exists():
        rows, source_hash = collect_barnard(barnard)
        hashes[barnard.source_id] = source_hash
        for row in rows:
            raw = row.get("Barn") or row.get("B")
            if raw is None or not raw.strip():
                continue
            source_key = _normalise_barn_id(raw.strip())
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
                        "constellation": _constellation(ra_deg, dec_deg),
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
                )
            )
            file_order += 1
            claim(index, "barnard", source_key, True)

    augment = sources.get("nightcrate_augment")
    if augment is not None and augment.file_path.exists():
        hashes[augment.source_id] = file_sha256(augment.file_path)

    objects = tuple(
        NewObject(
            draft.source_id,
            draft.source_key,
            draft.columns,
            tuple(draft.designations),
            draft.file_order,
        )
        for draft in drafts
    )
    return ObjectSet(objects, merges, hashes, unresolved, dict(sources))


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
    conn: sqlite3.Connection, new: ObjectSet, enrichment_source_ids: tuple[str, ...]
) -> ReconcileReport:
    """Apply a complete object set atomically while preserving user identity."""
    cur = conn.cursor()
    cur.row_factory = sqlite3.Row
    inserted = updated = reactivated = merged = removed = kept = 0
    source_counts = {source_id: 0 for source_id in OBJECT_SOURCE_IDS if source_id in new.hashes}
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
        cur.execute("SELECT source_id, file_hash, keys_assigned FROM dso_catalog_source")
        stored_state = {
            str(row[0]): {"file_hash": str(row[1]), "keys_assigned": bool(row[2])}
            for row in cur.fetchall()
        }

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
        for source_id in OBJECT_SOURCE_IDS:
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

        for source_id in OBJECT_SOURCE_IDS:
            if not new_by_source.get(source_id):
                continue
            state = stored_state.get(source_id)
            if state is not None and state["keys_assigned"]:
                continue
            unchanged = state is not None and state["file_hash"] == new.hashes.get(source_id)
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
            else:
                for row_hash, old_group in keyless_by_hash[source_id].items():
                    old_candidates = [row for row in old_group if int(row["id"]) not in claimed_old]
                    new_candidates = [
                        index
                        for index in new_by_hash[source_id].get(row_hash, ())
                        if index not in matched_new
                    ]
                    if len(old_candidates) == 1 and len(new_candidates) == 1:
                        pair(new_candidates[0], old_candidates[0])

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
            reset_augment_flags = bool({"common_name", "surface_brightness"} & set(changed_columns))
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
            if reset_augment_flags:
                assignments.extend(
                    ("common_name_augmented = 0", "surface_brightness_augmented = 0")
                )
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

        retained_unclaimed: set[int] = set()
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
                if count_references(cur, old_id) == 0:
                    cur.execute("DELETE FROM dso WHERE id = ?", (old_id,))
                else:
                    cur.execute(
                        "UPDATE dso SET active = 0, source_key = NULL WHERE id = ?",
                        (old_id,),
                    )
                    retained_unclaimed.add(old_id)
                    kept += 1
                    logger.warning(
                        "[reconcile] merged DSO %d retained inactive due to unknown references",
                        old_id,
                    )
                continue
            retained_unclaimed.add(old_id)
            if old["active"]:
                cur.execute("UPDATE dso SET active = 0 WHERE id = ?", (old_id,))
                removed += 1

        for designation in old_designations:
            key = (str(designation["catalog"]), str(designation["identifier"]))
            old_id = int(designation["dso_id"])
            if old_id not in retained_unclaimed or key in owned_designations:
                continue
            cur.execute(
                """
                INSERT INTO dso_designation
                    (dso_id, catalog, identifier, display_form, search_key, is_primary)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    old_id,
                    designation["catalog"],
                    designation["identifier"],
                    designation["display_form"],
                    designation["search_key"],
                    designation["is_primary"],
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
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return ReconcileReport(
        source_counts,
        inserted,
        updated,
        reactivated,
        merged,
        removed,
        kept,
    )
