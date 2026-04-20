"""Sharpless 2 catalog loader (VizieR VII/20).

Every row is classified as ``HII`` (Sharpless is a catalog of HII regions
by definition). The optional ``sharpless_crossref.csv`` side-input maps
selected Sh2 numbers to existing DSOs (e.g., ``Sh2-281 → NGC 1976``) —
when a mapping exists, the Sh2 number is attached as an additional
designation on the target DSO instead of creating a new DSO. Unmapped
rows create standalone DSOs with ``Sh2-<n>`` as their primary designation.

Constellation codes are derived from J2000 RA/Dec via astropy.
"""

from __future__ import annotations

import csv
import logging
import sqlite3
from pathlib import Path

from nightcrate.catalog_loader._common import (
    check_source_state,
    clear_previous_source_rows,
    insert_designation,
    insert_dso,
    maybe_float,
    maybe_str,
    normalize_designation,
    upsert_catalog_source,
)
from nightcrate.catalog_loader.hash import file_sha256, row_sha256
from nightcrate.catalog_loader.loader import SourceResult
from nightcrate.catalog_loader.registry import CatalogSource
from nightcrate.catalog_loader.vizier_tsv import parse_vizier_tsv
from nightcrate.services.astronomy import constellation_for_coords

logger = logging.getLogger("nightcrate.catalog_loader.sharpless")


def load_crossref_csv(path: Path) -> dict[str, str]:
    """Read ``sharpless_crossref.csv`` into a ``{sh2_number: target}`` map.

    Empty or missing files return an empty dict. Comment rows (``#…``)
    are skipped. Malformed rows are logged at WARNING and dropped.
    """
    out: dict[str, str] = {}
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        header_seen = False
        for row in reader:
            if not row or not row[0].strip() or row[0].lstrip().startswith("#"):
                continue
            if not header_seen:
                header_seen = True
                continue
            if len(row) < 2:
                logger.warning("[sharpless] crossref row ignored (too few cols): %r", row)
                continue
            sh2, target = row[0].strip(), row[1].strip()
            if sh2 and target:
                out[sh2] = target
    return out


def _resolve_target(cur: sqlite3.Cursor, target_designation: str) -> int | None:
    search_key = normalize_designation(target_designation)
    cur.execute(
        "SELECT dso_id FROM dso_designation WHERE search_key = ?",
        (search_key,),
    )
    row = cur.fetchone()
    return row[0] if row else None


def load_sharpless(
    conn: sqlite3.Connection,
    source: CatalogSource,
    *,
    crossref_path: Path | None,
    force: bool,
) -> SourceResult:
    """Entry point for the Sharpless loader.

    *crossref_path* points at ``nightcrate_sharpless_crossref`` data. If
    absent or empty, every Sharpless row becomes a standalone DSO. The
    crossref's file hash is folded into the effective source hash so an
    edit to the crossref alone invalidates the Sharpless cache.
    """
    result = SourceResult(source_id=source.source_id, status="skipped")

    # check_source_state emits status='missing' when the main file is absent;
    # skip the hash work in that case rather than raising in file_sha256.
    crossref_hash = (
        file_sha256(crossref_path) if crossref_path is not None and crossref_path.exists() else "-"
    )
    effective_hash = (
        f"{file_sha256(source.file_path)}:{crossref_hash}" if source.file_path.exists() else ""
    )

    preflight = check_source_state(conn, source, effective_hash, force=force)
    if preflight.preset_result is not None:
        if preflight.preset_result.status == "unchanged":
            logger.info("[sharpless] %s: unchanged (file_hash match)", source.source_id)
        return preflight.preset_result

    crossref = load_crossref_csv(crossref_path) if crossref_path is not None else {}
    cur = conn.cursor()

    try:
        conn.execute("BEGIN")
        clear_previous_source_rows(cur, source, logger=logger)
        source_catalog_id = upsert_catalog_source(cur, source, effective_hash, 0)

        dso_count = 0
        designation_count = 0
        merged_count = 0
        unresolved_crossref = 0

        for row in parse_vizier_tsv(source.file_path):
            sh2_raw = row.get("Sh2")
            if sh2_raw is None or not sh2_raw.strip():
                continue
            sh2_number = sh2_raw.strip().lstrip("0") or "0"

            ra_deg = maybe_float(row.get("_RAJ2000"))
            dec_deg = maybe_float(row.get("_DEJ2000"))
            diam = maybe_float(row.get("Diam"))
            class_raw = maybe_str(row.get("Class"))

            display_form = f"Sh2-{sh2_number}"
            search_key = f"sh2{sh2_number}".lower()

            target_id: int | None = None
            if sh2_number in crossref:
                target_id = _resolve_target(cur, crossref[sh2_number])
                if target_id is None:
                    unresolved_crossref += 1
                    logger.warning(
                        "[sharpless] crossref target %r not found for Sh2-%s; "
                        "falling back to standalone DSO",
                        crossref[sh2_number],
                        sh2_number,
                    )

            if target_id is not None:
                if insert_designation(
                    cur,
                    dso_id=target_id,
                    catalog="sharpless2",
                    identifier=sh2_number,
                    display_form=display_form,
                    search_key=search_key,
                    is_primary=False,
                    logger=logger,
                ):
                    designation_count += 1
                    merged_count += 1
                continue

            constellation = None
            if ra_deg is not None and dec_deg is not None:
                try:
                    constellation = constellation_for_coords(ra_deg, dec_deg)
                except Exception:  # noqa: BLE001 — astropy failures shouldn't kill the load
                    logger.debug("[sharpless] constellation lookup failed for Sh2-%s", sh2_number)

            notes = f"Sh2 class: {class_raw}" if class_raw else None
            row_hash = row_sha256({k: v for k, v in row.items() if v is not None})

            dso_id = insert_dso(
                cur,
                primary_designation=display_form,
                obj_type="HII",
                ra_deg=ra_deg,
                dec_deg=dec_deg,
                constellation=constellation,
                maj_axis_arcmin=diam,
                # Sharpless treats objects as circular.
                min_axis_arcmin=diam,
                common_name=None,
                openngc_notes=notes,
                source_catalog_id=source_catalog_id,
                source_row_hash=row_hash,
            )
            dso_count += 1

            if insert_designation(
                cur,
                dso_id=dso_id,
                catalog="sharpless2",
                identifier=sh2_number,
                display_form=display_form,
                search_key=search_key,
                is_primary=True,
                logger=logger,
            ):
                designation_count += 1

        cur.execute(
            "UPDATE dso_catalog_source SET row_count = ? WHERE id = ?",
            (dso_count, source_catalog_id),
        )
        conn.commit()

        result.status = "loaded"
        result.dso_count = dso_count
        result.designation_count = designation_count
        result.unresolved_duplicates = unresolved_crossref
        logger.info(
            "[sharpless] %s: loaded %d standalone DSOs, merged %d into existing, "
            "%d unresolved crossrefs",
            source.source_id,
            dso_count,
            merged_count,
            unresolved_crossref,
        )
    except Exception as exc:  # noqa: BLE001 — transaction rollback guard
        conn.rollback()
        result.status = "failed"
        result.error = str(exc)
        logger.exception("[sharpless] %s: load failed", source.source_id)

    return result
