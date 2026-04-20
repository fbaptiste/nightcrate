"""NightCrate DSO augmentation CSV loader.

Applies editorial overrides on top of the base OpenNGC + VizieR data:

- ``common_name_override`` replaces ``dso.common_name`` unconditionally.
- ``surface_brightness`` fills non-galaxy DSOs only (galaxy surface
  brightness uses OpenNGC's different methodology and is authoritative).
- ``distance_pc`` fills ``dso.distance_pc`` with
  ``distance_method = 'curated'``. Because this loader runs BEFORE
  the 50 MGC augmenter and the redshift backfill, a curated value
  stops them from overwriting it via their ``WHERE distance_pc IS NULL``
  guards.

Rows whose ``designation`` doesn't resolve to an existing DSO are
logged at WARNING and skipped (the augment file enriches known objects,
not creates new ones).
"""

from __future__ import annotations

import csv
import logging
import sqlite3
from pathlib import Path

from nightcrate.catalog_loader._common import (
    check_source_state,
    maybe_float,
    normalize_designation,
    upsert_catalog_source,
)
from nightcrate.catalog_loader.hash import file_sha256
from nightcrate.catalog_loader.loader import SourceResult
from nightcrate.catalog_loader.registry import CatalogSource

logger = logging.getLogger("nightcrate.catalog_loader.augment")

GALAXY_TYPES: frozenset[str] = frozenset({"G", "GPair", "GTrpl", "GGroup"})


def _resolve_dso(cur: sqlite3.Cursor, designation: str) -> tuple[int, str] | None:
    """Return ``(dso_id, obj_type)`` for the DSO matching *designation*, or None."""
    search_key = normalize_designation(designation)
    cur.execute(
        """
        SELECT d.id, d.obj_type
        FROM dso d
        JOIN dso_designation dd ON dd.dso_id = d.id
        WHERE dd.search_key = ? AND d.active = 1
        LIMIT 1
        """,
        (search_key,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return int(row[0]), str(row[1])


def _read_augment_csv(path: Path) -> list[dict[str, str]]:
    """Return a list of augment rows as dicts keyed by header column.

    Comment lines (``#…``) and empty rows are skipped; the first
    non-comment line is the header.
    """
    with path.open("r", encoding="utf-8", newline="") as fh:
        raw_lines = [line for line in fh if line.strip() and not line.lstrip().startswith("#")]
    if not raw_lines:
        return []
    reader = csv.DictReader(raw_lines)
    return [{k: (v or "").strip() for k, v in row.items() if k is not None} for row in reader]


def load_augment(
    conn: sqlite3.Connection,
    source: CatalogSource,
    *,
    force: bool,
) -> SourceResult:
    result = SourceResult(source_id=source.source_id, status="skipped")

    if not source.file_path.exists():
        preflight = check_source_state(conn, source, "", force=force)
        if preflight.preset_result is not None:
            return preflight.preset_result
        return result

    file_hash = file_sha256(source.file_path)
    preflight = check_source_state(conn, source, file_hash, force=force)
    if preflight.preset_result is not None:
        if preflight.preset_result.status == "unchanged":
            logger.info("[augment] %s: unchanged (file_hash match)", source.source_id)
        return preflight.preset_result

    cur = conn.cursor()
    try:
        conn.execute("BEGIN")

        # Reset augmentation flags on reload so removing a row from the CSV
        # also removes its flags. Curated distances are cleared too; the
        # loader re-sets them from the fresh CSV below.
        cur.execute(
            """
            UPDATE dso
            SET common_name_augmented = 0,
                surface_brightness_augmented = 0
            WHERE common_name_augmented = 1 OR surface_brightness_augmented = 1
            """,
        )
        cur.execute(
            """
            UPDATE dso
            SET distance_pc = NULL, distance_method = NULL
            WHERE distance_method = 'curated'
            """,
        )

        source_catalog_id = upsert_catalog_source(cur, source, file_hash, 0)

        rows_applied = 0
        unresolved = 0
        sb_ignored_galaxy = 0

        for row in _read_augment_csv(source.file_path):
            designation = row.get("designation", "")
            if not designation:
                continue

            resolved = _resolve_dso(cur, designation)
            if resolved is None:
                unresolved += 1
                logger.warning("[augment] designation %r not found; skipping row", designation)
                continue
            dso_id, obj_type = resolved

            name_override = row.get("common_name_override") or None
            sb = maybe_float(row.get("surface_brightness"))
            distance_pc = maybe_float(row.get("distance_pc"))

            updates: list[str] = []
            params: list = []

            if name_override:
                updates.append("common_name = ?")
                params.append(name_override)
                updates.append("common_name_augmented = 1")

            if sb is not None:
                if obj_type in GALAXY_TYPES:
                    sb_ignored_galaxy += 1
                    logger.debug(
                        "[augment] ignoring surface_brightness override on galaxy DSO "
                        "(%s); OpenNGC's value is authoritative",
                        designation,
                    )
                else:
                    updates.append("surface_brightness = ?")
                    params.append(sb)
                    updates.append("surface_brightness_augmented = 1")

            if distance_pc is not None:
                updates.append("distance_pc = ?")
                params.append(distance_pc)
                updates.append("distance_method = 'curated'")

            if not updates:
                continue

            params.append(dso_id)
            # updates is built exclusively from hard-coded column names above.
            cur.execute(f"UPDATE dso SET {', '.join(updates)} WHERE id = ?", params)  # noqa: S608  # nosec B608
            rows_applied += 1

        cur.execute(
            "UPDATE dso_catalog_source SET row_count = ? WHERE id = ?",
            (rows_applied, source_catalog_id),
        )
        conn.commit()

        result.status = "loaded"
        result.dso_count = rows_applied
        result.unresolved_duplicates = unresolved
        logger.info(
            "[augment] %s: applied to %d DSOs (%d unresolved, %d galaxy-SB ignored)",
            source.source_id,
            rows_applied,
            unresolved,
            sb_ignored_galaxy,
        )
    except Exception as exc:  # noqa: BLE001 — transaction rollback guard
        conn.rollback()
        result.status = "failed"
        result.error = str(exc)
        logger.exception("[augment] %s: load failed", source.source_id)

    return result
