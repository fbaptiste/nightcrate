"""Redshift-derived distance backfill (v0.15.0).

Final loader pass — runs after every catalog source has populated its
DSOs + any curated or 50 MGC distances. Any galaxy that still has a
``distance_pc IS NULL`` but a valid ``redshift`` value from OpenNGC gets
a Hubble-law distance tagged ``distance_method = 'redshift'``.

Not a fetched source — no ``dso_catalog_source`` row. Pure local
computation. Re-runs are idempotent via the same ``distance_pc IS NULL``
guard that 50 MGC uses.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass

from nightcrate.services.astronomy import redshift_to_parsecs

logger = logging.getLogger("nightcrate.catalog_loader.redshift")

_GALAXY_TYPES: tuple[str, ...] = ("G", "GPair", "GTrpl", "GGroup")


@dataclass
class RedshiftAugmentSummary:
    galaxies_considered: int = 0
    distances_applied: int = 0
    skipped_non_positive_z: int = 0


def apply_redshift_distances(conn: sqlite3.Connection) -> RedshiftAugmentSummary:
    """Populate ``distance_pc`` on galaxy DSOs with redshift but no distance.

    Precedence stays intact: curated > 50 MGC > redshift. Before running
    we clear any prior ``distance_method = 'redshift'`` entries so the
    computation is authoritative for whatever redshifts now exist in the
    catalog.
    """
    summary = RedshiftAugmentSummary()
    cur = conn.cursor()

    # Wipe prior redshift-derived distances so subsequent 50 MGC / curated
    # updates win cleanly on objects that previously only had a redshift.
    cur.execute(
        """
        UPDATE dso
        SET distance_pc = NULL, distance_method = NULL
        WHERE distance_method = 'redshift'
        """,
    )

    placeholders = ",".join("?" * len(_GALAXY_TYPES))
    cur.execute(
        f"""
        SELECT id, redshift
        FROM dso
        WHERE obj_type IN ({placeholders})
          AND redshift IS NOT NULL
          AND distance_pc IS NULL
          AND active = 1
        """,  # noqa: S608  # nosec B608 - placeholders from module-level constant
        _GALAXY_TYPES,
    )

    for row in cur.fetchall():
        dso_id = int(row[0])
        z = float(row[1])
        summary.galaxies_considered += 1
        if z <= 0:
            summary.skipped_non_positive_z += 1
            continue
        distance_pc = redshift_to_parsecs(z)
        if distance_pc is None:
            # redshift_to_parsecs already guards z<=0, so this is defensive.
            continue
        cur.execute(
            """
            UPDATE dso
            SET distance_pc = ?, distance_method = 'redshift'
            WHERE id = ? AND distance_pc IS NULL
            """,
            (distance_pc, dso_id),
        )
        if cur.rowcount:
            summary.distances_applied += 1

    conn.commit()
    logger.info(
        "[redshift] considered %d galaxies with redshift, applied %d "
        "Hubble-law distances (skipped %d non-positive z)",
        summary.galaxies_considered,
        summary.distances_applied,
        summary.skipped_non_positive_z,
    )
    return summary
