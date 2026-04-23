"""NightCrate editorial external-refs CSV loader.

Runs AFTER :mod:`wikidata_loader` so CSV rows always win. Two semantics:

- **Upsert**: ``identifier`` AND ``url`` both non-empty → insert or
  update the external ref for this ``(dso_id, provider, language)``.
- **Suppression**: both empty → delete the existing row if present.

Validation is strict: invalid rows abort the whole CSV load (Wikidata-
sourced rows stay in place) because silently ignoring a typo in a
hand-edited override file is worse than a clear error.
"""

from __future__ import annotations

import csv
import logging
import sqlite3
from pathlib import Path

from nightcrate.catalog_loader._common import (
    check_source_state,
    normalize_designation,
    upsert_catalog_source,
)
from nightcrate.catalog_loader.hash import file_sha256
from nightcrate.catalog_loader.loader import SourceResult
from nightcrate.catalog_loader.registry import CatalogSource

logger = logging.getLogger("nightcrate.catalog_loader.external_refs")

_VALID_PROVIDERS: frozenset[str] = frozenset({"wikidata", "wikipedia", "simbad", "ned"})
_LANGUAGE_AWARE_PROVIDERS: frozenset[str] = frozenset({"wikipedia"})


class ExternalRefsCsvError(ValueError):
    """Raised on structural or semantic errors in the external-refs CSV."""


def _resolve_dso_id(cur: sqlite3.Cursor, designation: str) -> int | None:
    search_key = normalize_designation(designation)
    cur.execute(
        """
        SELECT d.id
        FROM dso d
        JOIN dso_designation dd ON dd.dso_id = d.id
        WHERE dd.search_key = ? AND d.active = 1
        LIMIT 1
        """,
        (search_key,),
    )
    row = cur.fetchone()
    return int(row[0]) if row is not None else None


def _read_rows(path: Path) -> list[dict[str, str]]:
    """Return CSV rows as dicts with empty cells coerced to empty strings.

    Comment-only lines (``#…``) are stripped; the first non-comment line
    is the header.
    """
    with path.open("r", encoding="utf-8", newline="") as fh:
        raw_lines = [line for line in fh if line.strip() and not line.lstrip().startswith("#")]
    if not raw_lines:
        return []
    reader = csv.DictReader(raw_lines)
    return [{k: (v or "").strip() for k, v in row.items() if k is not None} for row in reader]


def _validate_row(row: dict[str, str], row_number: int) -> None:
    provider = row.get("provider", "")
    language = row.get("language", "")
    identifier = row.get("identifier", "")
    url = row.get("url", "")

    if provider not in _VALID_PROVIDERS:
        raise ExternalRefsCsvError(
            f"row {row_number}: provider {provider!r} not in {sorted(_VALID_PROVIDERS)}"
        )
    if provider in _LANGUAGE_AWARE_PROVIDERS and not language:
        raise ExternalRefsCsvError(
            f"row {row_number}: provider {provider!r} requires 'language' (e.g. 'en')"
        )
    if provider not in _LANGUAGE_AWARE_PROVIDERS and language:
        raise ExternalRefsCsvError(
            f"row {row_number}: provider {provider!r} must not set 'language'"
        )

    # Suppression: both empty is allowed.
    if not identifier and not url:
        return
    # Upsert: both non-empty is required.
    if not identifier or not url:
        raise ExternalRefsCsvError(
            f"row {row_number}: upsert rows require both 'identifier' and 'url' "
            "(leave both empty for a suppression row)"
        )


def _apply_row(
    cur: sqlite3.Cursor,
    row: dict[str, str],
    source_catalog_id: int,
    stats: _Stats,
) -> None:
    designation = row.get("dso_designation", "")
    provider = row["provider"]
    language = row.get("language") or None
    identifier = row.get("identifier", "")
    url = row.get("url", "")
    label = row.get("label") or None

    dso_id = _resolve_dso_id(cur, designation)
    if dso_id is None:
        stats.unresolved += 1
        logger.warning(
            "[external_refs] designation %r not found; skipping row",
            designation,
        )
        return

    if not identifier and not url:
        # Suppression.
        cur.execute(
            """
            DELETE FROM dso_external_ref
            WHERE dso_id = ?
              AND provider = ?
              AND (language IS ? OR language = ?)
            """,
            (dso_id, provider, language, language),
        )
        if cur.rowcount:
            stats.suppressed += 1
        return

    # Bare ``ON CONFLICT DO UPDATE`` lets SQLite pick whichever unique
    # constraint was hit — the main ``UNIQUE(dso_id, provider, language)``
    # for wikipedia rows, or the partial ``(dso_id, provider) WHERE
    # language IS NULL`` index for wikidata rows (NULLs are distinct in
    # SQLite's unique-index semantics, so the main UNIQUE doesn't cover
    # the language-agnostic case on its own).
    cur.execute(
        """
        INSERT INTO dso_external_ref (
            dso_id, provider, language, identifier, url, label, source_catalog_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT DO UPDATE SET
            identifier        = excluded.identifier,
            url               = excluded.url,
            label             = excluded.label,
            source_catalog_id = excluded.source_catalog_id,
            updated_at        = datetime('now')
        """,
        (dso_id, provider, language, identifier, url, label, source_catalog_id),
    )
    stats.upserted += 1


class _Stats:
    __slots__ = ("upserted", "suppressed", "unresolved")

    def __init__(self) -> None:
        self.upserted = 0
        self.suppressed = 0
        self.unresolved = 0


def load_external_refs(
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
            logger.info("[external_refs] %s: unchanged (file_hash match)", source.source_id)
        return preflight.preset_result

    cur = conn.cursor()
    stats = _Stats()
    try:
        conn.execute("BEGIN")

        # Validate ALL rows first so a late error leaves nothing half-applied.
        rows = _read_rows(source.file_path)
        for i, row in enumerate(rows, start=1):
            _validate_row(row, i)

        source_catalog_id = upsert_catalog_source(cur, source, file_hash, 0)

        # Wipe prior upserts owned by this source so removing a row from the
        # CSV also removes its effect. Suppression rows don't reach this
        # table (they DELETE elsewhere), so rebuilding from scratch is safe.
        cur.execute(
            "DELETE FROM dso_external_ref WHERE source_catalog_id = ?",
            (source_catalog_id,),
        )

        for row in rows:
            _apply_row(cur, row, source_catalog_id, stats)

        cur.execute(
            "UPDATE dso_catalog_source SET row_count = ? WHERE id = ?",
            (stats.upserted + stats.suppressed, source_catalog_id),
        )
        conn.commit()

        result.status = "loaded"
        result.dso_count = stats.upserted
        result.unresolved_duplicates = stats.unresolved
        logger.info(
            "[external_refs] %s: upserted=%d suppressed=%d unresolved=%d",
            source.source_id,
            stats.upserted,
            stats.suppressed,
            stats.unresolved,
        )
    except ExternalRefsCsvError as exc:
        conn.rollback()
        result.status = "failed"
        result.error = str(exc)
        logger.error("[external_refs] %s: %s", source.source_id, exc)
    except Exception as exc:  # noqa: BLE001 — transaction rollback guard
        conn.rollback()
        result.status = "failed"
        result.error = str(exc)
        logger.exception("[external_refs] %s: load failed", source.source_id)

    return result
