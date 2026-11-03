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
import re
import sqlite3
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from nightcrate.catalog_loader import registry
from nightcrate.catalog_loader.barnard_loader import _normalise_barn_id
from nightcrate.catalog_loader.crossref_parser import parse_other_id
from nightcrate.catalog_loader.designations import (
    canonical_identifier,
    canonical_legacy_identifier,
    normalize_designation,
)
from nightcrate.catalog_loader.hash import file_sha256
from nightcrate.catalog_loader.openngc_parser import (
    ParsedOpenNgcRow,
    _parse_name,
    parse_openngc,
    split_identifiers,
)
from nightcrate.catalog_loader.registry import CatalogSource, catalogs_for_source, get_sources

logger = logging.getLogger("nightcrate.catalog_loader")

if TYPE_CHECKING:
    from nightcrate.catalog_loader.reconcile import ObjectSet

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
    "hh": "HH",
    "aco": "ACO",
    "png": "PN G",
    "wr": "WR",
}

# These addendum source keys were previously rendered with the synthetic
# ``OTHER`` prefix.  Keeping the exact set makes the existing-database repair
# targeted and prevents unrelated unrecognized names from forcing reloads.
LEGACY_OTHER_NAMES: tuple[str, ...] = (
    "HCG092",
    "HCG079",
    "H05",
    "H13",
    "H20",
    "H21",
    "MWSC3156",
    "MWSC3171",
    "MWSC3561",
)


def _openngc_own_name_rows(cur: sqlite3.Cursor) -> dict[tuple[str, str], list[int]]:
    """Return active OpenNGC objects grouped by their parsed source name."""
    grouped: dict[tuple[str, str], list[int]] = {}
    rows = cur.execute(
        """
        SELECT d.id, d.source_key
        FROM dso d
        JOIN dso_catalog_source s ON s.id = d.source_catalog_id
        WHERE d.active = 1
          AND d.source_key IS NOT NULL
          AND s.source_id IN ('openngc', 'openngc_addendum')
        """
    ).fetchall()
    for dso_id, source_key in rows:
        catalog, identifier = _parse_name(str(source_key))
        if catalog is None or identifier is None:
            continue
        identifier = canonical_identifier(catalog, identifier)
        grouped.setdefault((catalog, identifier), []).append(int(dso_id))
    return grouped


def _designation_ownership_due(cur: sqlite3.Cursor) -> bool:
    """Detect OpenNGC own-name ownership or primary-designation drift."""
    own_names = _openngc_own_name_rows(cur)
    owners = {
        (str(catalog), str(identifier)): int(dso_id)
        for catalog, identifier, dso_id in cur.execute(
            "SELECT catalog, identifier, dso_id FROM dso_designation"
        ).fetchall()
    }
    if any(
        len(dso_ids) == 1 and owners.get(key) != dso_ids[0] for key, dso_ids in own_names.items()
    ):
        return True
    return (
        cur.execute(
            """
            SELECT 1
            FROM dso d
            JOIN dso_catalog_source s ON s.id = d.source_catalog_id
            LEFT JOIN dso_designation dd ON dd.dso_id = d.id
            WHERE d.active = 1
              AND s.source_id IN ('openngc', 'openngc_addendum')
            GROUP BY d.id
            HAVING COUNT(dd.id) > 0
               AND (
                    SUM(CASE WHEN dd.is_primary = 1 THEN 1 ELSE 0 END) != 1
                    OR MAX(CASE WHEN dd.is_primary = 1 THEN dd.display_form END)
                       != d.primary_designation
               )
            LIMIT 1
            """
        ).fetchone()
        is not None
    )


def _barnard_merges_due(cur: sqlite3.Cursor) -> bool:
    """Detect a keyed Barnard row matching one unambiguous OpenNGC own name."""
    openngc_names: dict[str, int] = {}
    ambiguous: set[str] = set()
    for (catalog, identifier), dso_ids in _openngc_own_name_rows(cur).items():
        if catalog != "barnard":
            continue
        key = _normalise_barn_id(identifier).casefold()
        if len(dso_ids) == 1 and key not in openngc_names:
            openngc_names[key] = dso_ids[0]
        else:
            ambiguous.add(key)
    for key in ambiguous:
        openngc_names.pop(key, None)
    if not openngc_names:
        return False
    barnard_keys = cur.execute(
        """
        SELECT d.source_key
        FROM dso d
        JOIN dso_catalog_source s ON s.id = d.source_catalog_id
        WHERE d.active = 1
          AND d.source_key IS NOT NULL
          AND s.source_id = 'vizier_barnard'
        """
    ).fetchall()
    return any(_normalise_barn_id(str(row[0])).casefold() in openngc_names for row in barnard_keys)


def _fused_pgc_repair_due(cur: sqlite3.Cursor) -> bool:
    """Detect legacy PGC designations created from an upstream missing comma."""
    rows = cur.execute(
        """
        SELECT d.id, d.raw_other_id
        FROM dso d
        JOIN dso_catalog_source s ON s.id = d.source_catalog_id
        WHERE d.active = 1
          AND d.raw_other_id IS NOT NULL
          AND s.source_id IN ('openngc', 'openngc_addendum')
        """
    ).fetchall()
    candidates: list[tuple[int, tuple[str, ...]]] = []
    for dso_id, raw_other_id in rows:
        raw_other_id = str(raw_other_id)
        original = tuple(token.strip() for token in str(raw_other_id).split(",") if token.strip())
        repaired = split_identifiers(raw_other_id)
        if repaired != original:
            candidates.append((int(dso_id), repaired))

    for dso_id, repaired in candidates:
        existing = {
            (str(catalog), str(identifier))
            for catalog, identifier in cur.execute(
                "SELECT catalog, identifier FROM dso_designation WHERE dso_id = ?",
                (dso_id,),
            ).fetchall()
        }

        expected = {
            (ref.catalog, ref.storage_identifier)
            for token in repaired
            for ref in parse_other_id(token)
        }
        legacy_malformed = any(
            catalog == "pgc" and len(split_identifiers(f"PGC {identifier}")) > 1
            for catalog, identifier in existing
        )
        if legacy_malformed:
            return True
        if expected <= existing:
            continue

        # A globally owned designation cannot be claimed by this object, so it
        # must not keep retriggering reconciliation on every load.
        missing_claimable = any(
            key not in existing
            and cur.execute(
                "SELECT 1 FROM dso_designation WHERE catalog = ? AND identifier = ? LIMIT 1",
                key,
            ).fetchone()
            is None
            for key in expected
        )
        if missing_claimable:
            return True
    return False


def _designation_canon_due(cur: sqlite3.Cursor) -> bool:
    """Detect stored structured identifiers and search keys needing repair."""
    rows = cur.execute(
        """
        SELECT catalog, identifier, search_key
        FROM dso_designation
        WHERE catalog IN ('mcg', 'png', 'wr', 'ruprecht')
        """
    ).fetchall()
    for catalog, identifier, search_key in rows:
        catalog = str(catalog)
        identifier = str(identifier)
        canonical = canonical_legacy_identifier(catalog, identifier)
        if identifier != canonical or str(search_key) != _build_search_key(catalog, canonical):
            return True

    openngc_rows = cur.execute(
        """
        SELECT d.id, d.raw_other_id
        FROM dso d
        JOIN dso_catalog_source s ON s.id = d.source_catalog_id
        WHERE s.source_id IN ('openngc', 'openngc_addendum')
          AND d.raw_other_id LIKE '%PN G%'
        """
    ).fetchall()
    for dso_id, raw_other_id in openngc_rows:
        expected = {
            ref.storage_identifier
            for ref in parse_other_id(str(raw_other_id))
            if ref.catalog == "png"
        }
        if not expected:
            continue
        actual = {
            str(row[0])
            for row in cur.execute(
                "SELECT identifier FROM dso_designation WHERE dso_id = ? AND catalog = 'png'",
                (dso_id,),
            ).fetchall()
        }
        missing_claimable = any(
            identifier not in actual
            and cur.execute(
                "SELECT 1 FROM dso_designation WHERE catalog = 'png' AND identifier = ? LIMIT 1",
                (identifier,),
            ).fetchone()
            is None
            for identifier in expected
        )
        if missing_claimable:
            return True
    return False


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
    objects_removed: int = 0
    objects_kept: int = 0

    @property
    def total_dsos(self) -> int:
        return sum(r.dso_count for r in self.results)

    @property
    def total_designations(self) -> int:
        return sum(r.designation_count for r in self.results)


@dataclass(frozen=True, slots=True)
class ObjectStepPlan:
    by_id: dict[str, CatalogSource]
    effective: dict[str, Literal["on", "off", "removed"]]
    run: bool
    deferred_reason: str | None
    object_set: ObjectSet | None
    preparation_error: str | None
    all_by_id: dict[str, CatalogSource] = field(repr=False)
    ordered: tuple[CatalogSource, ...] = field(repr=False)
    stored: dict[str, dict[str, object]] = field(repr=False)
    hashes: dict[str, str | None] = field(repr=False)
    sharpless_crossref_path: Path | None = field(repr=False)


def _build_display_form(catalog: str, identifier: str) -> str:
    """Human-friendly designation: ``M 42``, ``NGC 1976``, ``Sh2-281``."""
    if catalog == "other":
        unsupported = re.fullmatch(r"(H|MWSC)(\d+)", identifier)
        if unsupported is not None:
            prefix, digits = unsupported.groups()
            return f"{prefix} {digits.lstrip('0') or '0'}"
    prefix = _DISPLAY_PREFIX.get(catalog, catalog.upper())
    if catalog == "sharpless2":
        return f"{prefix}-{identifier}"
    if catalog == "png":
        return f"{prefix}{identifier}"
    return f"{prefix} {identifier}"


def _build_search_key(catalog: str, identifier: str) -> str:
    """Normalized key for fast lookups.

    Built from the user-facing ``display_form`` (e.g., ``M 42`` → ``m42``,
    ``NGC 1976`` → ``ngc1976``, ``Sh2-281`` → ``sh2281``). Users tend to
    type the short prefix (``M42``) rather than the long catalog name
    (``messier42``), so the display form is the better hit surface.
    """
    return normalize_designation(_build_display_form(catalog, identifier))


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
        identifier = canonical_identifier(catalog, identifier)
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

    if source.parser in {"openngc", "sharpless", "barnard", "parts", "overrides"}:
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


def _prepare_object_step(
    conn: sqlite3.Connection,
    catalogs_root: Path,
    *,
    force: bool,
    choice,
) -> ObjectStepPlan:
    """Resolve optional-catalog state and prepare one safe object reconciliation."""
    from nightcrate.catalog_loader.catalog_choice import effective_state
    from nightcrate.catalog_loader.reconcile import (
        EDITORIAL_OBJECT_SOURCE_IDS,
        OBJECT_SOURCE_IDS,
        build_object_set,
    )

    sources = get_sources(catalogs_root)
    all_by_id = {source.source_id: source for source in sources}
    load_order = (
        "openngc",
        "openngc_addendum",
        "vizier_sharpless",
        "vizier_barnard",
        "vizier_wr",
        "vizier_wr_phot",
        "vizier_hh",
        "vizier_hash",
        "vizier_lbn",
        "vizier_ldn",
        "nightcrate_melotte",
        "vizier_aco_north",
        "vizier_aco_south",
        "vizier_aco_s",
        "vizier_mcg",
        "vizier_mcg_v5",
        "vizier_arp",
        "nightcrate_arp_members",
        "nightcrate_sharpless_crossref",
        "nightcrate_barnard_crossref",
        "nightcrate_parts",
        "nightcrate_match_overrides",
        "nightcrate_augment",
        "github_50mgc",
        "wikidata_external_refs",
        "nightcrate_external_refs",
    )
    ordered = tuple(all_by_id[source_id] for source_id in load_order if source_id in all_by_id)

    cur = conn.cursor()
    stored = {
        str(row[0]): {
            "file_hash": str(row[1]),
            "row_count": int(row[2]),
            "keys_assigned": bool(row[3]),
        }
        for row in cur.execute(
            "SELECT source_id, file_hash, row_count, keys_assigned FROM dso_catalog_source"
        ).fetchall()
    }
    applied = {
        str(row[0]): str(row[1])
        for row in cur.execute("SELECT catalog_id, state FROM dso_catalog_applied").fetchall()
    }
    effective = {
        catalog.catalog_id: effective_state(choice, catalog, applied.get(catalog.catalog_id))
        for catalog in registry.OPTIONAL_CATALOGS
    }

    def catalog_available(catalog_id: str) -> bool:
        catalog = registry.optional_catalog(catalog_id)
        if catalog is None:
            return False
        installed, _version = registry.optional_catalog_install(catalog, catalogs_root)
        if not installed:
            return False
        if catalog_id == "sharpless":
            crossref = all_by_id.get("nightcrate_sharpless_crossref")
            return crossref is not None and crossref.file_path.exists()
        return True

    availability = {
        catalog.catalog_id: catalog_available(catalog.catalog_id)
        for catalog in registry.OPTIONAL_CATALOGS
    }

    def source_is_on(source_id: str) -> bool:
        if source_id == "nightcrate_arp_members":
            arp = registry.optional_catalog("arp")
            return (
                arp is not None and effective.get("arp") == "on" and availability.get("arp", False)
            )
        catalogs = catalogs_for_source(source_id)
        return not catalogs or any(
            effective[catalog.catalog_id] == "on" and availability[catalog.catalog_id]
            for catalog in catalogs
        )

    by_id = {
        source_id: source for source_id, source in all_by_id.items() if source_is_on(source_id)
    }
    sharpless_on = effective.get("sharpless") == "on"
    sharpless_crossref = all_by_id.get("nightcrate_sharpless_crossref")
    sharpless_crossref_path = (
        sharpless_crossref.file_path if sharpless_on and sharpless_crossref is not None else None
    )

    def current_hash(source: CatalogSource) -> str | None:
        if source.source_id not in by_id or not source.file_path.exists():
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
    object_input_ids = (*OBJECT_SOURCE_IDS, *EDITORIAL_OBJECT_SOURCE_IDS)
    loaded_object_inputs = tuple(
        source_id for source_id in (*object_input_ids, "nightcrate_augment") if source_id in by_id
    )
    missing_loaded = [
        by_id[source_id]
        for source_id in loaded_object_inputs
        if source_id in stored and hashes.get(source_id) is None
    ]
    unavailable_applied = [
        catalog
        for catalog in registry.OPTIONAL_CATALOGS
        if effective[catalog.catalog_id] == "on"
        and not availability[catalog.catalog_id]
        and (
            applied.get(catalog.catalog_id) == "on"
            or any(source_id in stored for source_id in catalog.source_ids)
        )
    ]
    if (
        sharpless_on
        and "vizier_sharpless" in stored
        and sharpless_crossref is not None
        and not sharpless_crossref.file_path.exists()
        and not str(stored["vizier_sharpless"]["file_hash"]).endswith(":-")
    ):
        missing_loaded.append(sharpless_crossref)
    deferred_reason = None
    if missing_loaded:
        missing_names = ", ".join(str(source.file_path) for source in missing_loaded)
        deferred_reason = f"object step deferred; missing file: {missing_names}"
    if unavailable_applied:
        missing_paths = [
            catalogs_root / "vizier" / spec.output_filename
            for catalog in unavailable_applied
            for spec in catalog.fetch_specs
            if not (catalogs_root / "vizier" / spec.output_filename).exists()
        ]
        if missing_paths:
            deferred_reason = "object step deferred; missing file: " + ", ".join(
                str(path) for path in missing_paths
            )
        elif deferred_reason is None:
            unavailable_names = ", ".join(catalog.display_name for catalog in unavailable_applied)
            deferred_reason = (
                f"object step deferred; catalog publication incomplete: {unavailable_names}"
            )

    catalog_states: dict[str, str] = {}
    selection_changed = False
    for catalog_id, state in effective.items():
        available = availability[catalog_id]
        eligible = state in {"off", "removed"} or available
        if eligible:
            catalog_states[catalog_id] = state
            if state != applied.get(catalog_id, "off"):
                selection_changed = True

    object_deferred = deferred_reason is not None
    legacy_placeholders = ", ".join("?" for _ in LEGACY_OTHER_NAMES)
    legacy_names_due = (
        not object_deferred
        and cur.execute(
            f"""
            SELECT 1
            FROM dso d
            JOIN dso_catalog_source s ON s.id = d.source_catalog_id
            WHERE s.source_id = 'openngc_addendum'
              AND d.source_key IN ({legacy_placeholders})
              AND d.primary_designation = 'OTHER ' || d.source_key
            LIMIT 1
            """,  # noqa: S608  # nosec B608 - fixed placeholder count
            LEGACY_OTHER_NAMES,
        ).fetchone()
        is not None
    )
    designation_ownership_due = not object_deferred and _designation_ownership_due(cur)
    barnard_merges_due = not object_deferred and _barnard_merges_due(cur)
    fused_pgc_repair_due = not object_deferred and _fused_pgc_repair_due(cur)
    designation_canon_due = not object_deferred and _designation_canon_due(cur)
    present_owner = any(hashes.get(source_id) is not None for source_id in OBJECT_SOURCE_IDS)
    removed_catalogs = frozenset(
        catalog_id for catalog_id, state in effective.items() if state == "removed"
    )
    object_changed = any(
        hashes.get(source_id) is not None
        and (
            source_id not in stored
            or (
                stored[source_id]["file_hash"] != ""
                and stored[source_id]["file_hash"] != hashes[source_id]
            )
        )
        for source_id in object_input_ids
        if source_id in by_id
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
        for source_id in object_input_ids
        if source_id in by_id
    )
    run = (
        not object_deferred
        and (present_owner or bool(removed_catalogs))
        and (
            force
            or selection_changed
            or object_changed
            or augment_changed
            or keys_due
            or legacy_names_due
            or designation_ownership_due
            or barnard_merges_due
            or fused_pgc_repair_due
            or designation_canon_due
        )
    )
    object_set = None
    preparation_error = None
    if run:
        on_catalogs = frozenset(
            catalog_id for catalog_id, state in effective.items() if state == "on"
        )
        try:
            object_set = replace(
                build_object_set(by_id, sharpless_crossref_path, on_catalogs),
                catalog_states=catalog_states,
            )
        except Exception as exc:  # noqa: BLE001 - load_catalogs reports source failures
            preparation_error = str(exc)

    return ObjectStepPlan(
        by_id=by_id,
        effective=effective,
        run=run,
        deferred_reason=deferred_reason,
        object_set=object_set,
        preparation_error=preparation_error,
        all_by_id=all_by_id,
        ordered=ordered,
        stored=stored,
        hashes=hashes,
        sharpless_crossref_path=sharpless_crossref_path,
    )


def prepare_object_step(
    conn: sqlite3.Connection,
    catalogs_root: Path,
    *,
    force: bool,
) -> ObjectStepPlan:
    """Resolve the persisted optional-catalog choice for reconciliation."""
    from nightcrate.catalog_loader.catalog_choice import read_choice

    return _prepare_object_step(
        conn,
        catalogs_root,
        force=force,
        choice=read_choice(catalogs_root),
    )


def prepare_removal_step(
    conn: sqlite3.Connection,
    catalogs_root: Path,
    catalog_id: str,
) -> ObjectStepPlan:
    """Prepare the exact reconciliation a catalog removal would perform."""
    from nightcrate.catalog_loader.catalog_choice import read_choice, with_removed

    return _prepare_object_step(
        conn,
        catalogs_root,
        force=False,
        choice=with_removed(read_choice(catalogs_root), catalog_id),
    )


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
        EDITORIAL_OBJECT_SOURCE_IDS,
        OBJECT_SOURCE_IDS,
        apply_object_set,
    )

    object_input_ids = (*OBJECT_SOURCE_IDS, *EDITORIAL_OBJECT_SOURCE_IDS)

    plan = prepare_object_step(conn, catalogs_root, force=force)
    by_id = plan.all_by_id
    ordered = plan.ordered
    stored = plan.stored
    hashes = plan.hashes
    sharpless_crossref_path = plan.sharpless_crossref_path
    object_deferred = plan.deferred_reason is not None

    object_results: dict[str, SourceResult] = {}
    object_ran = False
    object_error: str | None = None
    objects_removed = 0
    objects_kept = 0
    if plan.run:
        try:
            object_set = plan.object_set
            if object_set is None:
                raise RuntimeError(
                    plan.preparation_error or "object step was due without a prepared object set"
                )
            enrichment_ids = (
                "github_50mgc",
                "wikidata_external_refs",
                "nightcrate_external_refs",
            )
            removed_catalogs = frozenset(
                catalog_id for catalog_id, state in plan.effective.items() if state == "removed"
            )
            report = apply_object_set(
                conn,
                object_set,
                enrichment_ids,
                removed_catalogs=removed_catalogs,
            )
            objects_removed = report.deleted
            objects_kept = report.kept_linked
            object_ran = True
            for source_id in object_input_ids:
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

    for source_id in object_input_ids:
        if source_id in object_results:
            continue
        source = by_id[source_id]
        source_catalogs = catalogs_for_source(source_id)
        source_effectively_on = not source_catalogs or any(
            plan.effective[catalog.catalog_id] == "on" for catalog in source_catalogs
        )
        if object_error is not None:
            object_results[source_id] = SourceResult(
                source_id,
                "failed",
                dso_count=int(stored.get(source_id, {}).get("row_count", 0)),
                error=object_error,
            )
        elif object_deferred and source_effectively_on:
            object_results[source_id] = SourceResult(
                source_id,
                "skipped",
                dso_count=int(stored.get(source_id, {}).get("row_count", 0)),
                error=plan.deferred_reason,
            )
        elif source_id not in plan.by_id:
            object_results[source_id] = SourceResult(
                source_id,
                "missing" if source_effectively_on and not source.file_path.exists() else "skipped",
                error=(
                    f"file not found: {source.file_path}"
                    if source_effectively_on and not source.file_path.exists()
                    else None
                ),
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

    summary = LoadSummary(objects_removed=objects_removed, objects_kept=objects_kept)
    for source in ordered:
        result = (
            object_results.get(source.source_id)
            or enrichment_results.get(source.source_id)
            or side_results[source.source_id]
        )
        summary.results.append(result)
    return summary
