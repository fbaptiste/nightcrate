"""Orchestrates DSO catalog loading.

Entry point is :func:`load_catalogs`. For each registered source:

1. Compute the file's sha256 and compare against the last stored
   ``dso_catalog_source.file_hash``.
2. If unchanged and ``force`` is False, skip the source entirely.
3. Otherwise, drop every ``dso`` row produced by this source
   (cascades clean children) and reinsert everything inside one
   transaction. Other sources proceed independently on failure.

Primary-designation precedence (per spec §6): messier > ngc > ic > caldwell
> first-seen. Dup rows merge into an existing canonical DSO as additional
NGC/IC designations; NonEx rows are skipped during parsing.

Cross-references are added in two phases: canonical designations first
(Name + Messier + NGC + IC), then ``other_id`` parses. The
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

from nightcrate.catalog_loader.crossref_parser import parse_other_id
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


def _resolve_existing_designation(cur: sqlite3.Cursor, catalog: str, identifier: str) -> int | None:
    cur.execute(
        "SELECT dso_id FROM dso_designation WHERE catalog = ? AND identifier = ?",
        (catalog, identifier),
    )
    row = cur.fetchone()
    return row[0] if row else None


def _insert_dso(
    cur: sqlite3.Cursor,
    row: ParsedOpenNgcRow,
    primary_designation_display: str,
    source_catalog_id: int,
) -> int:
    cur.execute(
        """
        INSERT INTO dso (
            primary_designation, obj_type, raw_obj_type,
            ra_deg, dec_deg, constellation,
            maj_axis_arcmin, min_axis_arcmin, position_angle_deg,
            mag_b, mag_v, mag_j, mag_h, mag_k, surface_brightness,
            hubble_type, pm_ra, pm_dec, radial_velocity, redshift,
            cstar_mag_u, cstar_mag_b, cstar_mag_v, cstar_id,
            common_name, ned_notes, openngc_notes, raw_other_id,
            source_catalog_id, source_row_hash
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            primary_designation_display,
            row.obj_type,
            row.raw_obj_type,
            row.ra_deg,
            row.dec_deg,
            row.constellation,
            row.maj_axis_arcmin,
            row.min_axis_arcmin,
            row.position_angle_deg,
            row.mag_b,
            row.mag_v,
            row.mag_j,
            row.mag_h,
            row.mag_k,
            row.surface_brightness,
            row.hubble_type,
            row.pm_ra,
            row.pm_dec,
            row.radial_velocity,
            row.redshift,
            row.cstar_mag_u,
            row.cstar_mag_b,
            row.cstar_mag_v,
            row.cstar_id,
            row.common_name,
            row.ned_notes,
            row.openngc_notes,
            row.raw_other_id,
            source_catalog_id,
            row.row_hash,
        ),
    )
    dso_id = cur.lastrowid
    if dso_id is None:
        raise RuntimeError("dso INSERT returned no row id")
    return dso_id


def _insert_designation(
    cur: sqlite3.Cursor,
    *,
    dso_id: int,
    catalog: str,
    identifier: str,
    is_primary: bool,
) -> bool:
    """Insert a single designation; return True if inserted, False on UNIQUE collision.

    A collision means another DSO already claims this (catalog, identifier)
    pair. The existing owner wins — the caller gets back False and the
    incoming row simply lacks that cross-reference.
    """
    display_form = _build_display_form(catalog, identifier)
    search_key = _build_search_key(catalog, identifier)
    try:
        cur.execute(
            """
            INSERT INTO dso_designation
                (dso_id, catalog, identifier, display_form, search_key, is_primary)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (dso_id, catalog, identifier, display_form, search_key, 1 if is_primary else 0),
        )
        return True
    except sqlite3.IntegrityError:
        logger.debug(
            "[catalog_loader] designation collision: %s %s already claimed (dso_id=%d)",
            catalog,
            identifier,
            dso_id,
        )
        return False


def _upsert_catalog_source(
    cur: sqlite3.Cursor,
    source: CatalogSource,
    file_hash: str,
    row_count: int,
) -> int:
    """Insert or update the `dso_catalog_source` row for *source*, returning its id."""
    cur.execute(
        "SELECT id FROM dso_catalog_source WHERE source_id = ?",
        (source.source_id,),
    )
    existing = cur.fetchone()
    if existing is None:
        cur.execute(
            """
            INSERT INTO dso_catalog_source (
                source_id, category, display_name, version, source_url,
                file_path, file_hash, license, attribution, row_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source.source_id,
                source.category,
                source.display_name,
                source.version,
                source.source_url,
                str(source.file_path),
                file_hash,
                source.license,
                source.attribution,
                row_count,
            ),
        )
        new_id = cur.lastrowid
        if new_id is None:
            raise RuntimeError("dso_catalog_source INSERT returned no row id")
        return new_id

    source_catalog_id = existing[0]
    cur.execute(
        """
        UPDATE dso_catalog_source SET
            category = ?, display_name = ?, version = ?, source_url = ?,
            file_path = ?, file_hash = ?, license = ?, attribution = ?,
            loaded_at = datetime('now'), row_count = ?
        WHERE id = ?
        """,
        (
            source.category,
            source.display_name,
            source.version,
            source.source_url,
            str(source.file_path),
            file_hash,
            source.license,
            source.attribution,
            row_count,
            source_catalog_id,
        ),
    )
    return source_catalog_id


def _load_source(
    conn: sqlite3.Connection,
    source: CatalogSource,
    *,
    force: bool,
) -> SourceResult:
    result = SourceResult(source_id=source.source_id, status="skipped")

    if not source.file_path.exists():
        # Not an error — the user hasn't fetched the catalog from GitHub yet.
        # The Admin UI distinguishes ``missing`` from ``failed`` and surfaces
        # a "Load from GitHub" CTA on the first; only genuine download / parse
        # failures get the error treatment.
        result.status = "missing"
        result.error = f"file not found: {source.file_path}"
        logger.debug("[catalog_loader] %s: %s", source.source_id, result.error)
        return result

    file_hash = file_sha256(source.file_path)

    cur = conn.cursor()
    cur.execute(
        "SELECT id, file_hash FROM dso_catalog_source WHERE source_id = ?",
        (source.source_id,),
    )
    existing = cur.fetchone()
    if existing and existing[1] == file_hash and not force:
        result.status = "unchanged"
        # Populate counts from the current state for reporting.
        cur.execute("SELECT row_count FROM dso_catalog_source WHERE id = ?", (existing[0],))
        row = cur.fetchone()
        if row:
            result.dso_count = int(row[0])
        logger.info("[catalog_loader] %s: unchanged (file_hash match)", source.source_id)
        return result

    # The heavy path: drop and reinsert inside a single transaction.
    try:
        conn.execute("BEGIN")
        # If the source exists, wipe its rows first (cascades to designations).
        if existing is not None:
            cur.execute("DELETE FROM dso WHERE source_catalog_id = ?", (existing[0],))
            logger.info(
                "[catalog_loader] %s: cleared %d previous rows",
                source.source_id,
                cur.rowcount,
            )

        # Pre-register the source with a placeholder row_count; we'll
        # update it at the end once we know the actual count.
        source_catalog_id = _upsert_catalog_source(cur, source, file_hash, 0)

        rows = list(parse_openngc(source.file_path))
        canonical_rows = [r for r in rows if not r.is_duplicate]
        duplicate_rows = [r for r in rows if r.is_duplicate]

        dso_count = 0
        designation_count = 0

        # Pass 1 — canonical rows
        for row in canonical_rows:
            canonicals = _build_canonical_designations(row)
            if not canonicals:
                # The Name didn't match a known catalog prefix and no M/NGC/IC
                # cross-refs exist. Rare but possible on addendum rows. Fall
                # back to an 'Other' synthetic designation so the row still
                # has a primary_designation for display.
                synthetic = ("other", row.raw_name or f"row_{id(row)}")
                canonicals = [synthetic]

            primary_idx = _pick_primary(canonicals)
            primary_catalog, primary_identifier = canonicals[primary_idx]
            primary_display = _build_display_form(primary_catalog, primary_identifier)

            dso_id = _insert_dso(cur, row, primary_display, source_catalog_id)
            dso_count += 1

            for idx, (catalog, identifier) in enumerate(canonicals):
                # The fallback 'other' pseudo-catalog isn't in the CHECK
                # vocabulary — skip it as a real designation but keep the
                # primary_designation text on the dso itself.
                if catalog == "other":
                    continue
                if _insert_designation(
                    cur,
                    dso_id=dso_id,
                    catalog=catalog,
                    identifier=identifier,
                    is_primary=(idx == primary_idx),
                ):
                    designation_count += 1

            # Phase 2 — cross-references from the Identifiers column.
            for ref in parse_other_id(row.raw_other_id):
                if _insert_designation(
                    cur,
                    dso_id=dso_id,
                    catalog=ref.catalog,
                    identifier=ref.identifier,
                    is_primary=False,
                ):
                    designation_count += 1

        # Pass 2 — Dup rows fold into the canonical they reference
        unresolved = 0
        for dup in duplicate_rows:
            target_dso_id: int | None = None
            # Most Dups carry an NGC cross-ref; a few carry an IC. A handful
            # (historical Messier duplicates — e.g., M102 folding into M101)
            # only carry a Messier cross-ref in the addendum file.
            if dup.ngc_cross_ref:
                target_dso_id = _resolve_existing_designation(cur, "ngc", dup.ngc_cross_ref)
            if target_dso_id is None and dup.ic_cross_ref:
                target_dso_id = _resolve_existing_designation(cur, "ic", dup.ic_cross_ref)
            if target_dso_id is None and dup.messier_number:
                target_dso_id = _resolve_existing_designation(cur, "messier", dup.messier_number)
            if target_dso_id is None:
                unresolved += 1
                logger.warning(
                    "[catalog_loader] %s: unresolved Dup %s (NGC=%s, IC=%s)",
                    source.source_id,
                    dup.raw_name,
                    dup.ngc_cross_ref,
                    dup.ic_cross_ref,
                )
                continue

            # Attach the Dup's own Name as an additional designation.
            if dup.name_catalog and dup.name_identifier:
                if _insert_designation(
                    cur,
                    dso_id=target_dso_id,
                    catalog=dup.name_catalog,
                    identifier=dup.name_identifier,
                    is_primary=False,
                ):
                    designation_count += 1

        # Update the stored row_count
        cur.execute(
            "UPDATE dso_catalog_source SET row_count = ? WHERE id = ?",
            (dso_count, source_catalog_id),
        )
        conn.commit()

        result.status = "loaded"
        result.dso_count = dso_count
        result.designation_count = designation_count
        result.unresolved_duplicates = unresolved
        logger.info(
            "[catalog_loader] %s: loaded %d DSOs, %d designations (%d unresolved Dups)",
            source.source_id,
            dso_count,
            designation_count,
            unresolved,
        )
    except Exception as exc:  # noqa: BLE001 — transaction-rollback guard
        conn.rollback()
        result.status = "failed"
        result.error = str(exc)
        logger.exception("[catalog_loader] %s: load failed", source.source_id)

    return result


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
        barnard_loader,
        mgc50_augmenter,
        sharpless_loader,
    )

    if source.parser == "openngc":
        return _load_source(conn, source, force=force)
    if source.parser == "sharpless":
        return sharpless_loader.load_sharpless(
            conn, source, crossref_path=sharpless_crossref_path, force=force
        )
    if source.parser == "barnard":
        return barnard_loader.load_barnard(conn, source, force=force)
    if source.parser == "mgc50":
        return mgc50_augmenter.augment_from_mgc50(conn, source, force=force)
    if source.parser == "augment":
        return augment_loader.load_augment(conn, source, force=force)
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
      5. HyperLEDA (only fills where distance_pc IS NULL — curated wins)

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
    )
    by_id = {s.source_id: s for s in sources}
    ordered = [by_id[sid] for sid in load_order if sid in by_id]

    summary = LoadSummary()
    for source in ordered:
        summary.results.append(_dispatch_source(conn, source, sharpless_crossref_path, force=force))

    # Hubble-law backfill for galaxies with redshift but no distance yet.
    # Not a fetched source — a local computation that runs last so the
    # precedence stays: curated > 50 MGC > redshift.
    try:
        from nightcrate.catalog_loader.redshift_distance import apply_redshift_distances

        apply_redshift_distances(conn)
    except sqlite3.Error:
        logger.exception("[catalog_loader] redshift backfill failed")

    return summary
