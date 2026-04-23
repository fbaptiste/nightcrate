"""Loader for Wikidata SPARQL TSV → ``dso_external_ref`` rows.

For each :class:`WikidataRecord` produced by :mod:`wikidata_tsv`:

1. Look up every catalog identifier against ``dso_designation.search_key``.
   Collect unique ``dso_id`` candidates.
2. If zero candidates → skip silently (no matching DSO).
3. If one or more candidates → upsert a ``wikidata`` row (+ optional
   ``wikipedia`` row when an enwiki sitelink is present) onto EACH
   matching DSO. OpenNGC's per-catalog splits (e.g., NGC 1316 +
   PGC 12769 → same physical galaxy in two DSO rows; NGC 1952 +
   Sh2-244 → same Crab Nebula in two rows) make multi-match the
   common case, not an error. The editorial CSV layer remains the
   escape hatch for cases where duplication is undesired.

Upsert semantics use bare ``ON CONFLICT DO UPDATE`` so SQLite picks
whichever unique constraint fires — either ``UNIQUE(dso_id, provider,
language)`` for wikipedia rows, or the partial unique ``(dso_id,
provider) WHERE language IS NULL`` for wikidata rows (NULLs are
distinct in SQLite's main unique-index semantics, so the language-
agnostic case needs its own index). The updated_at trigger bumps
timestamps automatically when column values actually change.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterable
from urllib.parse import quote_plus

from nightcrate.catalog_loader._common import (
    check_source_state,
    upsert_catalog_source,
)
from nightcrate.catalog_loader.augment_loader import GALAXY_TYPES
from nightcrate.catalog_loader.hash import file_sha256
from nightcrate.catalog_loader.loader import SourceResult
from nightcrate.catalog_loader.registry import CatalogSource
from nightcrate.catalog_loader.wikidata_tsv import (
    WikidataRecord,
    build_search_keys,
    parse_wikidata_tsv,
)

logger = logging.getLogger("nightcrate.catalog_loader.wikidata")


# SIMBAD accepts spaces as ``+`` in the Ident= query param and is
# tolerant of many alias forms (M 42, NGC 1976, Sh 2-281, etc.) —
# constructing from the primary designation works in practice when
# Wikidata has no P3083 for the DSO (v0.21.1 Q3 decision).
_SIMBAD_URL_TEMPLATE = "https://simbad.u-strasbg.fr/simbad/sim-id?Ident={ident}"
_NED_URL_TEMPLATE = "https://ned.ipac.caltech.edu/byname?objname={ident}"


def _build_simbad_url(identifier: str) -> str:
    return _SIMBAD_URL_TEMPLATE.format(ident=quote_plus(identifier))


def _build_ned_url(identifier: str) -> str:
    return _NED_URL_TEMPLATE.format(ident=quote_plus(identifier))


def _is_extragalactic(obj_type: str | None) -> bool:
    """NED is extragalactic-only; galactic objects are skipped even when
    Wikidata has a P2528 for them (data is thin; wrong-object risk).
    Reuses the ``GALAXY_TYPES`` constant from ``augment_loader``."""
    return obj_type is not None and obj_type in GALAXY_TYPES


def _load_dso_metadata(cur: sqlite3.Cursor) -> dict[int, tuple[str, str]]:
    """Return ``{dso_id: (primary_designation, obj_type)}`` for all active
    DSOs. Pre-fetched once so the per-match upsert loop doesn't re-hit
    the DB for every ref insert."""
    cur.execute("SELECT id, primary_designation, obj_type FROM dso WHERE active = 1")
    return {int(row[0]): (str(row[1]), str(row[2])) for row in cur.fetchall()}


def _resolve_dso_ids(cur: sqlite3.Cursor, search_keys: list[str]) -> set[int]:
    """Return the set of distinct ``dso.id`` values for any of *search_keys*.

    Only active DSOs (``dso.active = 1``) are considered.
    """
    if not search_keys:
        return set()
    placeholders = ",".join("?" * len(search_keys))
    cur.execute(
        f"""
        SELECT DISTINCT d.id
        FROM dso d
        JOIN dso_designation dd ON dd.dso_id = d.id
        WHERE dd.search_key IN ({placeholders}) AND d.active = 1
        """,  # noqa: S608  # nosec B608 — placeholders built only from ``?`` chars
        search_keys,
    )
    return {int(row[0]) for row in cur.fetchall()}


def _upsert_external_ref(
    cur: sqlite3.Cursor,
    *,
    dso_id: int,
    provider: str,
    language: str | None,
    identifier: str,
    url: str | None,
    label: str | None,
    source_catalog_id: int,
) -> None:
    """Insert or update a ``dso_external_ref`` row in place."""
    # Bare ``ON CONFLICT DO UPDATE`` (no target) — SQLite dispatches to
    # whichever unique constraint was hit. This is load-bearing for
    # language-agnostic providers (wikidata): the main ``UNIQUE(dso_id,
    # provider, language)`` doesn't enforce uniqueness when language is
    # NULL (all NULLs are distinct in SQLite's unique-index semantics),
    # so a partial unique index on ``(dso_id, provider) WHERE language
    # IS NULL`` covers that case instead. With a bare ON CONFLICT the
    # correct index is picked automatically.
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


def _wikipedia_slug(title: str) -> str:
    """Return the Wikipedia article slug (underscored title, no URL-encoding)."""
    return title.replace(" ", "_")


def _process_record(
    cur: sqlite3.Cursor,
    record: WikidataRecord,
    source_catalog_id: int,
    dso_meta: dict[int, tuple[str, str]],
    stats: _Stats,
) -> None:
    search_keys = build_search_keys(record)
    if not search_keys:
        stats.unmatched += 1
        return

    dso_ids = _resolve_dso_ids(cur, search_keys)
    if not dso_ids:
        stats.unmatched += 1
        logger.debug(
            "[wikidata] no DSO match for %s (%s); keys=%s",
            record.qid,
            record.label or "no label",
            search_keys,
        )
        return

    # Multi-match is normal and expected (not an error). OpenNGC has
    # per-catalog DSO splits — NGC 1316 + PGC 12769 are the same physical
    # galaxy in two rows; NGC 1952 (Crab) + Sh2-244 refer to the same
    # object; NGC/Barnard pairs describe physically-separate but visually-
    # coincident features. Wikidata unifies them under one entity; we
    # duplicate the ref onto every matching DSO so a user on any of them
    # sees the Wikipedia/Wikidata chip. (Spec §1.3's Stephan's-Quintet
    # philosophy generalised to all providers — no global uniqueness
    # constraint on (provider, language, identifier).)
    if len(dso_ids) > 1:
        stats.multi_match += 1
        logger.debug(
            "[wikidata] multi-match for %s (%s): keys=%s map to dso_ids=%s; linking all",
            record.qid,
            record.label or "no label",
            search_keys,
            sorted(dso_ids),
        )

    stats.matched += 1

    for dso_id in sorted(dso_ids):
        # Both ``_resolve_dso_ids`` and ``dso_meta`` filter to active=1,
        # so every id in ``dso_ids`` is guaranteed present in ``dso_meta``.
        primary_designation, obj_type = dso_meta[dso_id]

        _upsert_external_ref(
            cur,
            dso_id=dso_id,
            provider="wikidata",
            language=None,
            identifier=record.qid,
            url=record.qid_url,
            label=record.label,
            source_catalog_id=source_catalog_id,
        )
        stats.wikidata_refs += 1

        if record.enwiki_title and record.enwiki_url:
            _upsert_external_ref(
                cur,
                dso_id=dso_id,
                provider="wikipedia",
                language="en",
                identifier=_wikipedia_slug(record.enwiki_title),
                url=record.enwiki_url,
                label=record.enwiki_title,
                source_catalog_id=source_catalog_id,
            )
            stats.wikipedia_refs += 1

        # SIMBAD: always, via P3083 when present or primary-designation
        # fallback. SIMBAD's name resolver is tolerant enough that
        # broad coverage beats the occasional imperfect match (Q3 for
        # v0.21.1).
        simbad_identifier = record.simbad_id or primary_designation
        _upsert_external_ref(
            cur,
            dso_id=dso_id,
            provider="simbad",
            language=None,
            identifier=simbad_identifier,
            url=_build_simbad_url(simbad_identifier),
            label=primary_designation,
            source_catalog_id=source_catalog_id,
        )
        stats.simbad_refs += 1

        # NED: extragalactic-only, synthesised from primary_designation.
        # Wikidata doesn't index NED IDs (P2528 is earthquake magnitude,
        # not NED — the spec's property claim was wrong and Wikidata
        # has no reliable equivalent), so the v0.21.1 approach became
        # "use NED's tolerant byname resolver with the DSO's primary
        # designation, gated by the galaxy-type filter." Safer than
        # the Wikidata-only path originally proposed: galaxy DSOs have
        # unambiguous primary designations (NGC X / PGC X / UGC X /
        # IC X), all of which NED's resolver handles correctly.
        if _is_extragalactic(obj_type):
            _upsert_external_ref(
                cur,
                dso_id=dso_id,
                provider="ned",
                language=None,
                identifier=primary_designation,
                url=_build_ned_url(primary_designation),
                label=primary_designation,
                source_catalog_id=source_catalog_id,
            )
            stats.ned_refs += 1


class _Stats:
    __slots__ = (
        "parsed",
        "matched",
        "unmatched",
        "multi_match",
        "wikidata_refs",
        "wikipedia_refs",
        "simbad_refs",
        "ned_refs",
    )

    def __init__(self) -> None:
        self.parsed = 0
        self.matched = 0
        self.unmatched = 0
        self.multi_match = 0
        self.wikidata_refs = 0
        self.wikipedia_refs = 0
        self.simbad_refs = 0
        self.ned_refs = 0


def load_wikidata(
    conn: sqlite3.Connection,
    source: CatalogSource,
    *,
    force: bool,
) -> SourceResult:
    """Load Wikidata SPARQL TSV → ``dso_external_ref``.

    Returns a :class:`SourceResult`; ``dso_count`` carries the total
    external-ref rows inserted (Wikidata + Wikipedia combined).
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
            logger.info("[wikidata] %s: unchanged (file_hash match)", source.source_id)
        return preflight.preset_result

    cur = conn.cursor()
    stats = _Stats()
    try:
        conn.execute("BEGIN")

        # Wipe previously-loaded Wikidata rows so a reload doesn't leave
        # stale refs from an earlier query version. Wikipedia rows sourced
        # from the SAME Wikidata fetch are also cleared — they'll be
        # re-inserted downstream. CSV-sourced rows are preserved
        # (source_catalog_id points at nightcrate_external_refs, not this
        # source).
        cur.execute(
            "SELECT id FROM dso_catalog_source WHERE source_id = ?",
            (source.source_id,),
        )
        existing = cur.fetchone()
        if existing is not None:
            cur.execute(
                "DELETE FROM dso_external_ref WHERE source_catalog_id = ?",
                (existing[0],),
            )

        source_catalog_id = upsert_catalog_source(cur, source, file_hash, 0)

        # Pre-fetch (primary_designation, obj_type) for every active DSO
        # so the per-match insert loop has both fields handy — SIMBAD
        # needs ``primary_designation`` as a fallback identifier + row
        # label; NED needs ``obj_type`` for the extragalactic gate.
        dso_meta = _load_dso_metadata(cur)

        records: Iterable[WikidataRecord] = parse_wikidata_tsv(source.file_path)
        for record in records:
            stats.parsed += 1
            _process_record(cur, record, source_catalog_id, dso_meta, stats)

        total_refs = stats.wikidata_refs + stats.wikipedia_refs + stats.simbad_refs + stats.ned_refs
        cur.execute(
            "UPDATE dso_catalog_source SET row_count = ? WHERE id = ?",
            (total_refs, source_catalog_id),
        )
        conn.commit()

        result.status = "loaded"
        result.dso_count = total_refs
        # designation_count is unused for this loader but reporting the
        # parsed-entity count here gives operators a useful headline number
        # in the LoadSummary aggregate.
        result.designation_count = stats.parsed
        logger.info(
            "[wikidata] %s: parsed=%d matched=%d unmatched=%d multi_match=%d "
            "wikidata=%d wikipedia=%d simbad=%d ned=%d",
            source.source_id,
            stats.parsed,
            stats.matched,
            stats.unmatched,
            stats.multi_match,
            stats.wikidata_refs,
            stats.wikipedia_refs,
            stats.simbad_refs,
            stats.ned_refs,
        )
    except Exception as exc:  # noqa: BLE001 — transaction rollback guard
        conn.rollback()
        result.status = "failed"
        result.error = str(exc)
        logger.exception("[wikidata] %s: load failed", source.source_id)

    return result
