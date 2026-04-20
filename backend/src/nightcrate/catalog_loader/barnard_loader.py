"""Barnard dark-nebula catalog loader (VizieR VII/220).

Every row creates a standalone DSO with ``obj_type = 'DrkN'``. Unlike
Sharpless, Barnard does NOT crossref-merge onto existing DSOs — dark
nebulae and emission regions at the same line of sight are physically
distinct objects and should not be conflated.

Constellation codes are derived from J2000 RA/Dec via astropy.
"""

from __future__ import annotations

import logging
import re
import sqlite3

from nightcrate.catalog_loader._common import (
    check_source_state,
    clear_previous_source_rows,
    insert_designation,
    insert_dso,
    maybe_float,
    maybe_str,
    upsert_catalog_source,
)
from nightcrate.catalog_loader.hash import file_sha256, row_sha256
from nightcrate.catalog_loader.loader import SourceResult
from nightcrate.catalog_loader.registry import CatalogSource
from nightcrate.catalog_loader.vizier_tsv import parse_vizier_tsv
from nightcrate.services.astronomy import constellation_for_coords

logger = logging.getLogger("nightcrate.catalog_loader.barnard")

# Barnard identifiers can carry letter suffixes (e.g., ``33a``). We
# normalise leading zeros off the numeric prefix while keeping any suffix.
_BARN_ID_RE = re.compile(r"^0*(\d+)(.*)$")


def _normalise_barn_id(raw: str) -> str:
    match = _BARN_ID_RE.match(raw)
    if match is None:
        return raw
    digits, suffix = match.groups()
    return (digits.lstrip("0") or "0") + (suffix or "")


def load_barnard(
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
            logger.info("[barnard] %s: unchanged (file_hash match)", source.source_id)
        return preflight.preset_result

    cur = conn.cursor()
    try:
        conn.execute("BEGIN")
        clear_previous_source_rows(cur, source, logger=logger)
        source_catalog_id = upsert_catalog_source(cur, source, file_hash, 0)

        dso_count = 0
        designation_count = 0

        for row in parse_vizier_tsv(source.file_path):
            barn_raw = row.get("Barn") or row.get("B")
            if barn_raw is None or not barn_raw.strip():
                continue
            barn_id = _normalise_barn_id(barn_raw.strip())

            ra_deg = maybe_float(row.get("_RAJ2000"))
            dec_deg = maybe_float(row.get("_DEJ2000"))
            diam = maybe_float(row.get("Diam"))
            common_name = maybe_str(row.get("Names"))
            durch = maybe_str(row.get("Durch"))

            display_form = f"B {barn_id}"
            search_key = f"b{barn_id}".lower()

            constellation = None
            if ra_deg is not None and dec_deg is not None:
                try:
                    constellation = constellation_for_coords(ra_deg, dec_deg)
                except Exception:  # noqa: BLE001 — astropy failures shouldn't kill the load
                    logger.debug("[barnard] constellation lookup failed for B %s", barn_id)

            notes = f"Durch: {durch}" if durch else None
            row_hash = row_sha256({k: v for k, v in row.items() if v is not None})

            dso_id = insert_dso(
                cur,
                primary_designation=display_form,
                obj_type="DrkN",
                ra_deg=ra_deg,
                dec_deg=dec_deg,
                constellation=constellation,
                maj_axis_arcmin=diam,
                min_axis_arcmin=diam,
                common_name=common_name,
                openngc_notes=notes,
                source_catalog_id=source_catalog_id,
                source_row_hash=row_hash,
            )
            dso_count += 1

            if insert_designation(
                cur,
                dso_id=dso_id,
                catalog="barnard",
                identifier=barn_id,
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
        logger.info(
            "[barnard] %s: loaded %d DSOs, %d designations",
            source.source_id,
            dso_count,
            designation_count,
        )
    except Exception as exc:  # noqa: BLE001 — transaction rollback guard
        conn.rollback()
        result.status = "failed"
        result.error = str(exc)
        logger.exception("[barnard] %s: load failed", source.source_id)

    return result
