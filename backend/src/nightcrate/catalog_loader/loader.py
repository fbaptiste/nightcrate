"""Orchestrates DSO catalog loading.

Entry point is :func:`load_catalogs`. Object-producing sources are collected
into one complete in-memory set, matched by stable source identity, and applied
in a transaction. Enrichment sources run afterward in dependency order. Empty
stored hashes persist invalidation across failures and process restarts.

Primary-designation precedence (per spec §6): messier > ngc > ic > caldwell
> first-seen. Dup rows merge into an existing canonical DSO as additional
NGC/IC designations; NonEx rows are skipped during parsing.

Cross-references are claimed immediately after each canonical row. The
``UNIQUE(catalog, identifier)`` constraint on ``dso_designation`` means
the same designation cannot point to two different DSOs — on collision
we keep the first and silently drop later claimants, logging at DEBUG.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from nightcrate.catalog_loader.hash import file_sha256
from nightcrate.catalog_loader.openngc_parser import (
    ParsedOpenNgcRow,
    parse_openngc,
)
from nightcrate.catalog_loader.registry import CatalogSource, get_sources

logger = logging.getLogger("nightcrate.catalog_loader")

CatalogLoadStatus = Literal["loaded", "unchanged", "skipped", "missing", "failed"]

# Priority order for choosing which designation becomes `is_primary=1`
# and drives `dso.primary_designation`.
_PRIMARY_PRIORITY: tuple[str, ...] = ("messier", "ngc", "ic", "caldwell")

# Display prefix per catalog, used to build `display_form` strings.
# Any catalog not listed here falls back to its uppercase code.
_DISPLAY_PREFIX: dict[str, str] = {
    "ngc": "NGC",
    "ic": "IC",
    "messier": "M",
    "caldwell": "C",
    "ugc": "UGC",
    "pgc": "PGC",
    "mcg": "MCG",
    "eso": "ESO",
    "arp": "Arp",
    "hickson": "HCG",
    "sharpless2": "Sh2",
    "barnard": "B",
    "ldn": "LDN",
    "lbn": "LBN",
    "vdb": "vdB",
    "cederblad": "Ced",
    "pk": "PK",
    "rcw": "RCW",
    "gum": "Gum",
    "mrk": "Mrk",
    "terzan": "Terzan",
    "pal": "Pal",
    "mel": "Mel",
    "cr": "Cr",
    "stock": "Stock",
    "ruprecht": "Ru",
    "abell": "Abell",
    "dolidze": "Do",
    "dwb": "DWB",
}


@dataclass
class SourceResult:
    source_id: str
    status: CatalogLoadStatus
    dso_count: int = 0
    designation_count: int = 0
    skipped_nonex: int = 0
    unresolved_duplicates: int = 0
    error: str | None = None


@dataclass
class LoadSummary:
    results: list[SourceResult] = field(default_factory=list)

    @property
    def total_dsos(self) -> int:
        return sum(r.dso_count for r in self.results)

    @property
    def total_designations(self) -> int:
        return sum(r.designation_count for r in self.results)


def _build_display_form(catalog: str, identifier: str) -> str:
    """Human-friendly designation: ``M 42``, ``NGC 1976``, ``Sh2-281``."""
    prefix = _DISPLAY_PREFIX.get(catalog, catalog.upper())
    if catalog == "sharpless2":
        return f"{prefix}-{identifier}"
    return f"{prefix} {identifier}"


def _build_search_key(catalog: str, identifier: str) -> str:
    """Normalized key for fast lookups.

    Built from the user-facing ``display_form`` (e.g., ``M 42`` → ``m42``,
    ``NGC 1976`` → ``ngc1976``, ``Sh2-281`` → ``sh2281``). Users tend to
    type the short prefix (``M42``) rather than the long catalog name
    (``messier42``), so the display form is the better hit surface.
    """
    display = _build_display_form(catalog, identifier)
    return display.lower().replace(" ", "").replace("-", "").replace("_", "")


def _pick_primary(designations: list[tuple[str, str]]) -> int:
    """Return the index of the designation that should be marked primary.

    Priority: messier > ngc > ic > caldwell > first-seen.
    Ties within a priority bucket resolve to the first one encountered.
    """
    best_idx = 0
    best_rank = len(_PRIMARY_PRIORITY) + 1
    for idx, (catalog, _identifier) in enumerate(designations):
        try:
            rank = _PRIMARY_PRIORITY.index(catalog)
        except ValueError:
            continue
        if rank < best_rank:
            best_rank = rank
            best_idx = idx
    return best_idx


def _build_canonical_designations(row: ParsedOpenNgcRow) -> list[tuple[str, str]]:
    """Designations always derivable from the named columns on *row*.

    Returns a list of ``(catalog, identifier)`` tuples in insertion order.
    Duplicates within the list (same catalog+identifier) are dropped
    preserving first occurrence.
    """
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []

    def add(catalog: str | None, identifier: str | None) -> None:
        if catalog is None or not identifier:
            return
        key = (catalog, identifier)
        if key in seen:
            return
        seen.add(key)
        out.append(key)

    # Primary prefix from Name (NGC/IC on main file, varied on addendum)
    add(row.name_catalog, row.name_identifier)
    # Cross-refs from the dedicated M/NGC/IC columns
    add("messier", row.messier_number)
    add("ngc", row.ngc_cross_ref)
    add("ic", row.ic_cross_ref)
    return out


def collect_openngc(source: CatalogSource) -> tuple[list[ParsedOpenNgcRow], str]:
    """Parse an OpenNGC object source without reading or writing the database."""
    return list(parse_openngc(source.file_path)), file_sha256(source.file_path)


def _dispatch_source(
    conn: sqlite3.Connection,
    source: CatalogSource,
    sharpless_crossref_path: Path | None,
    *,
    force: bool,
) -> SourceResult:
    """Route a ``CatalogSource`` to the parser-specific loader."""
    # Local imports: the per-parser modules import back into this module for
    # ``SourceResult``/``CatalogLoadStatus`` so we defer at call-time.
    from nightcrate.catalog_loader import (
        augment_loader,
        external_refs_loader,
        mgc50_augmenter,
        wikidata_loader,
    )

    if source.parser in {"openngc", "sharpless", "barnard"}:
        return SourceResult(source_id=source.source_id, status="skipped")
    if source.parser == "mgc50":
        return mgc50_augmenter.augment_from_mgc50(conn, source, force=force)
    if source.parser == "augment":
        return augment_loader.load_augment(conn, source, force=force)
    if source.parser == "wikidata_external_refs":
        return wikidata_loader.load_wikidata(conn, source, force=force)
    if source.parser == "external_refs":
        return external_refs_loader.load_external_refs(conn, source, force=force)
    if source.parser in {"sharpless_crossref", "barnard_crossref"}:
        # These files are side-inputs consumed by other loaders (Sharpless
        # reads sharpless_crossref.csv directly during its own load). The
        # registry entry exists for attribution + hash tracking only.
        result = SourceResult(source_id=source.source_id, status="skipped")
        if source.file_path.exists():
            # Surface as "loaded" (with zero rows) so the Admin table shows
            # a successful entry rather than "missing" for the bundled files.
            result.status = "loaded"
        else:
            result.status = "missing"
            result.error = f"file not found: {source.file_path}"
        return result
    logger.warning("[catalog_loader] unknown parser %r for %s", source.parser, source.source_id)
    return SourceResult(source_id=source.source_id, status="failed", error="unknown parser")


def load_catalogs(
    conn: sqlite3.Connection,
    catalogs_root: Path,
    *,
    force: bool = False,
) -> LoadSummary:
    """Load all registered DSO catalog sources in dependency order.

    Callers pass a standard :class:`sqlite3.Connection` (NOT aiosqlite) — the
    loader is synchronous for the same reason the equipment seed loader is:
    it runs at startup, needs its own isolated transactions per source, and
    sharing aiosqlite's thread-restricted connection is awkward.

    The connection must have ``PRAGMA foreign_keys = ON`` enabled so the
    ``ON DELETE CASCADE`` on ``dso_designation`` fires when the loader
    wipes rows before reload.

    Load order (matters for augmenters that depend on existing DSOs):
      1. OpenNGC + addendum
      2. Sharpless (reads nightcrate_sharpless_crossref as a side-input)
      3. Barnard
      4. NightCrate augmentation CSV (sets curated distances)
      5. 50 MGC (galaxy distance augmenter; only fills where
         distance_pc IS NULL — curated wins)
      6. Redshift backfill (post-load Hubble-law pass for galaxies
         still without a distance)

    Parameters
    ----------
    conn
        Open sqlite3 connection.
    catalogs_root
        Directory containing per-source subdirectories (e.g., ``openngc/``).
    force
        If True, reload every source regardless of file-hash equality.
    """
    conn.execute("PRAGMA foreign_keys = ON")

    from nightcrate.catalog_loader.reconcile import (
        OBJECT_SOURCE_IDS,
        apply_object_set,
        build_object_set,
    )

    sources = get_sources(catalogs_root)
    # Sharpless reads its crossref CSV directly during load; find the path
    # up front so we can pass it along.
    sharpless_crossref_path: Path | None = next(
        (s.file_path for s in sources if s.source_id == "nightcrate_sharpless_crossref"),
        None,
    )

    # Explicit load order overrides the registry's natural order so that
    # augmenters run after the base catalogs they augment. Redshift-derived
    # distances are applied at the very end as a post-load computation —
    # they're not a fetched source, so they don't appear in the registry.
    load_order = (
        "openngc",
        "openngc_addendum",
        "vizier_sharpless",
        "vizier_barnard",
        "nightcrate_sharpless_crossref",
        "nightcrate_barnard_crossref",
        "nightcrate_augment",
        "github_50mgc",
        # Wikidata runs last among bulk sources so every DSO (including
        # Sharpless/Barnard standalones) exists before designation-based
        # matching. The editorial override CSV runs strictly after Wikidata
        # so CSV rows always win.
        "wikidata_external_refs",
        "nightcrate_external_refs",
    )
    by_id = {s.source_id: s for s in sources}
    ordered = [by_id[sid] for sid in load_order if sid in by_id]

    cur = conn.cursor()
    cur.execute("SELECT source_id, file_hash, row_count, keys_assigned FROM dso_catalog_source")
    stored = {
        str(row[0]): {
            "file_hash": str(row[1]),
            "row_count": int(row[2]),
            "keys_assigned": bool(row[3]),
        }
        for row in cur.fetchall()
    }

    def current_hash(source: CatalogSource) -> str | None:
        if not source.file_path.exists():
            return None
        if source.source_id == "vizier_sharpless":
            crossref_hash = (
                file_sha256(sharpless_crossref_path)
                if sharpless_crossref_path is not None and sharpless_crossref_path.exists()
                else "-"
            )
            return f"{file_sha256(source.file_path)}:{crossref_hash}"
        return file_sha256(source.file_path)

    hashes = {source.source_id: current_hash(source) for source in ordered}
    loaded_object_inputs = (*OBJECT_SOURCE_IDS, "nightcrate_augment")
    missing_loaded = [
        by_id[source_id]
        for source_id in loaded_object_inputs
        if source_id in stored and hashes.get(source_id) is None
    ]
    sharpless_crossref = by_id["nightcrate_sharpless_crossref"]
    if (
        "vizier_sharpless" in stored
        and not sharpless_crossref.file_path.exists()
        and not stored["vizier_sharpless"]["file_hash"].endswith(":-")
    ):
        missing_loaded.append(sharpless_crossref)
    object_deferred = bool(missing_loaded)
    missing_names = ", ".join(str(source.file_path) for source in missing_loaded)

    present_owner = any(hashes.get(source_id) is not None for source_id in OBJECT_SOURCE_IDS)
    object_changed = any(
        hashes.get(source_id) is not None
        and (
            source_id not in stored
            or (
                stored[source_id]["file_hash"] != ""
                and stored[source_id]["file_hash"] != hashes[source_id]
            )
        )
        for source_id in OBJECT_SOURCE_IDS
    )
    augment_changed = (
        hashes.get("nightcrate_augment") is not None
        and "nightcrate_augment" in stored
        and stored["nightcrate_augment"]["file_hash"] != ""
        and stored["nightcrate_augment"]["file_hash"] != hashes["nightcrate_augment"]
    )
    keys_due = any(
        source_id in stored
        and hashes.get(source_id) is not None
        and not stored[source_id]["keys_assigned"]
        for source_id in OBJECT_SOURCE_IDS
    )
    run_objects = (
        not object_deferred
        and present_owner
        and (force or object_changed or augment_changed or keys_due)
    )

    object_results: dict[str, SourceResult] = {}
    object_ran = False
    object_error: str | None = None
    if run_objects:
        try:
            object_set = build_object_set(by_id, sharpless_crossref_path)
            enrichment_ids = (
                "github_50mgc",
                "wikidata_external_refs",
                "nightcrate_external_refs",
            )
            report = apply_object_set(conn, object_set, enrichment_ids)
            object_ran = True
            for source_id in OBJECT_SOURCE_IDS:
                if hashes.get(source_id) is not None:
                    object_results[source_id] = SourceResult(
                        source_id,
                        "loaded",
                        dso_count=report.source_counts.get(source_id, 0),
                        unresolved_duplicates=object_set.unresolved,
                    )
        except Exception as exc:  # noqa: BLE001 - one failed object step is a load result
            object_error = str(exc)
            logger.exception("[catalog_loader] object reconciliation failed")

    for source_id in OBJECT_SOURCE_IDS:
        if source_id in object_results:
            continue
        source = by_id[source_id]
        if object_error is not None:
            object_results[source_id] = SourceResult(
                source_id,
                "failed",
                dso_count=int(stored.get(source_id, {}).get("row_count", 0)),
                error=object_error,
            )
        elif object_deferred:
            object_results[source_id] = SourceResult(
                source_id,
                "skipped",
                dso_count=int(stored.get(source_id, {}).get("row_count", 0)),
                error=f"object step deferred; missing file: {missing_names}",
            )
        elif hashes.get(source_id) is None:
            object_results[source_id] = SourceResult(
                source_id, "missing", error=f"file not found: {source.file_path}"
            )
        elif source_id in stored:
            object_results[source_id] = SourceResult(
                source_id,
                "unchanged",
                dso_count=int(stored[source_id]["row_count"]),
            )
        else:
            object_results[source_id] = SourceResult(source_id, "skipped")

    enrichment_order = (
        "nightcrate_augment",
        "github_50mgc",
        "wikidata_external_refs",
        "nightcrate_external_refs",
    )
    object_step_blocked = object_deferred or object_error is not None
    earliest: int | None = 0 if object_ran or (force and not object_step_blocked) else None
    if earliest is None:
        for index, source_id in enumerate(enrichment_order):
            source_hash = hashes.get(source_id)
            if source_hash is None:
                continue
            previous = stored.get(source_id)
            if source_id == "nightcrate_augment" and object_step_blocked:
                # A genuinely changed augment file is an object input: consuming it
                # before reconciliation can leave removed overrides behind. A blank
                # stored hash is only persisted invalidation, so that remains safe to
                # run while the object step is blocked.
                if previous is None or (
                    previous["file_hash"] != "" and previous["file_hash"] != source_hash
                ):
                    continue
            if (
                previous is None
                or previous["file_hash"] == ""
                or previous["file_hash"] != source_hash
            ):
                earliest = index
                break

    enrichment_results: dict[str, SourceResult] = {}
    if earliest is not None:
        due_ids = enrichment_order[earliest:]
        placeholders = ", ".join("?" for _ in due_ids)
        conn.execute(
            f"UPDATE dso_catalog_source SET file_hash = '' WHERE source_id IN ({placeholders})",  # noqa: S608  # nosec B608
            due_ids,
        )
        conn.commit()
        for source_id in due_ids:
            source = by_id[source_id]
            enrichment_results[source_id] = _dispatch_source(
                conn, source, sharpless_crossref_path, force=True
            )

    for source_id in enrichment_order:
        if source_id in enrichment_results:
            continue
        source = by_id[source_id]
        if hashes.get(source_id) is None:
            enrichment_results[source_id] = SourceResult(
                source_id, "missing", error=f"file not found: {source.file_path}"
            )
        elif source_id in stored:
            enrichment_results[source_id] = SourceResult(
                source_id,
                "unchanged",
                dso_count=int(stored[source_id]["row_count"]),
            )
        else:
            enrichment_results[source_id] = SourceResult(source_id, "skipped")

    side_results: dict[str, SourceResult] = {}
    for source_id in ("nightcrate_sharpless_crossref", "nightcrate_barnard_crossref"):
        source = by_id[source_id]
        side_results[source_id] = SourceResult(
            source_id,
            "loaded" if source.file_path.exists() else "missing",
            error=None if source.file_path.exists() else f"file not found: {source.file_path}",
        )

    try:
        from nightcrate.catalog_loader.redshift_distance import apply_redshift_distances

        apply_redshift_distances(conn)
    except sqlite3.Error:
        logger.exception("[catalog_loader] redshift backfill failed")

    summary = LoadSummary()
    for source in ordered:
        result = (
            object_results.get(source.source_id)
            or enrichment_results.get(source.source_id)
            or side_results[source.source_id]
        )
        summary.results.append(result)
    return summary
