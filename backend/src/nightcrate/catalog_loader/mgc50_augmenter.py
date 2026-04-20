"""50 Mpc Galaxy Catalog distance augmenter (Ohlson+ 2024).

Ohlson et al. 2024 homogenises distances for 15,424 nearby galaxies from
HyperLEDA, the Local Volume Galaxy Catalog, and the NASA-Sloan Atlas.
Each row carries a PGC cross-reference and a linear distance in Mpc
(``bestdist``), so conversion to parsecs is just ``bestdist × 1e6``.

Scope: this loader doesn't create DSOs — it updates ``dso.distance_pc``
where NULL on DSOs that have a matching PGC designation. The standard
``WHERE distance_pc IS NULL`` guard means curated distances never get
overwritten; redshift-derived distances haven't been applied yet at this
point in the load order either, so 50 MGC wins over them too.

Source file: ``data/catalog.fits`` (FITS binary table), fetched from the
author's GitHub mirror (see :mod:`nightcrate.catalog_loader.mgc50_fetch`)
and parsed by :mod:`nightcrate.catalog_loader.mgc50_parser` via astropy.
We moved off VizieR's ``J/AJ/167/31`` endpoint because CDS has been
intermittently flaky; the underlying data is identical, just in FITS
rather than fixed-width ASCII.

Note: about 83% of 50 MGC's ``bestdist`` values are flow-corrected
redshift distances. Only a few hundred are truly independent (Cepheids,
TRGB, SBF). Our ``redshift`` method (``redshift_distance.py``) is the
naive Hubble-law fallback; 50 MGC values are still preferred because the
authors apply flow correction.
"""

from __future__ import annotations

import logging
import sqlite3

from nightcrate.catalog_loader._common import (
    check_source_state,
    upsert_catalog_source,
)
from nightcrate.catalog_loader.hash import file_sha256
from nightcrate.catalog_loader.loader import SourceResult
from nightcrate.catalog_loader.mgc50_parser import parse_50mgc_fits
from nightcrate.catalog_loader.registry import CatalogSource

logger = logging.getLogger("nightcrate.catalog_loader.mgc50")


def _load_pgc_map(cur: sqlite3.Cursor) -> dict[str, tuple[int, str | None]]:
    """Preload every ``pgc*`` search_key to ``(dso_id, distance_method)``.

    One query up front replaces a per-row SELECT that would otherwise run
    15k times during a full 50 MGC load. Active DSOs only.
    """
    cur.execute(
        """
        SELECT dd.search_key, dd.dso_id, d.distance_method
        FROM dso_designation dd
        JOIN dso d ON d.id = dd.dso_id
        WHERE dd.catalog = 'pgc' AND d.active = 1
        """,
    )
    return {row[0]: (int(row[1]), row[2]) for row in cur.fetchall()}


def augment_from_mgc50(
    conn: sqlite3.Connection,
    source: CatalogSource,
    *,
    force: bool,
) -> SourceResult:
    """Apply distance updates from the 50 MGC FITS file (linear Mpc).

    ``row_count`` on ``dso_catalog_source`` stores the number of DSO rows
    actually updated (not the number of FITS rows read) so the Attribution
    panel can show "X galaxies augmented with distances".
    """
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
            logger.info("[50mgc] %s: unchanged (file_hash match)", source.source_id)
        return preflight.preset_result

    cur = conn.cursor()
    try:
        conn.execute("BEGIN")

        # Reset distances previously set by 50 MGC so a newer release can
        # correct / remove them. Curated + redshift distances stay intact —
        # redshift is reapplied after this pass anyway.
        cur.execute(
            """
            UPDATE dso
            SET distance_pc = NULL, distance_method = NULL
            WHERE distance_method = '50mgc'
            """,
        )
        cleared = cur.rowcount
        if cleared:
            logger.info(
                "[50mgc] %s: cleared %d previous 50mgc-sourced distances",
                source.source_id,
                cleared,
            )

        source_catalog_id = upsert_catalog_source(cur, source, file_hash, 0)

        pgc_map = _load_pgc_map(cur)
        logger.info(
            "[50mgc] %s: preloaded %d PGC → dso mappings",
            source.source_id,
            len(pgc_map),
        )

        matched = 0
        updated = 0
        skipped_curated = 0
        rows_read = 0

        for parsed in parse_50mgc_fits(source.file_path):
            rows_read += 1
            if parsed.best_dist_mpc <= 0:
                continue

            pgc_str = str(parsed.pgc).lstrip("0") or "0"
            hit = pgc_map.get(f"pgc{pgc_str}".lower())
            if hit is None:
                continue
            matched += 1
            dso_id, current_method = hit
            if current_method == "curated":
                skipped_curated += 1
                continue

            distance_pc = parsed.best_dist_mpc * 1_000_000.0
            cur.execute(
                """
                UPDATE dso
                SET distance_pc = ?, distance_method = '50mgc'
                WHERE id = ? AND distance_pc IS NULL
                """,
                (distance_pc, dso_id),
            )
            if cur.rowcount:
                updated += 1

        cur.execute(
            "UPDATE dso_catalog_source SET row_count = ? WHERE id = ?",
            (updated, source_catalog_id),
        )
        conn.commit()

        result.status = "loaded"
        # dso_count reports galaxies updated — the Admin UI surfaces it.
        result.dso_count = updated
        result.designation_count = 0
        logger.info(
            "[50mgc] %s: read %d rows, matched %d existing DSOs, updated %d, skipped %d curated",
            source.source_id,
            rows_read,
            matched,
            updated,
            skipped_curated,
        )
    except Exception as exc:  # noqa: BLE001 — transaction rollback guard
        conn.rollback()
        result.status = "failed"
        result.error = str(exc)
        logger.exception("[50mgc] %s: load failed", source.source_id)

    return result
