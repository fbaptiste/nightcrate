"""Deep-sky object catalog API."""

from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from nightcrate.api.dso_models import (
    CatalogFacet,
    CatalogSource,
    ConstellationFacet,
    DsoDesignation,
    DsoDetail,
    DsoFacetsResponse,
    DsoListItem,
    DsoListResponse,
    ExternalRef,
    RawTypeFacet,
    TypeGroupFacet,
)
from nightcrate.db.session import get_db
from nightcrate.services.dso_type_groups import TYPE_GROUPS, raw_types_for_group

router = APIRouter(prefix="/api/dso", tags=["Deep-Sky Objects"])


SORT_COLUMNS: dict[str, str] = {
    "primary_designation": "primary_designation",
    "mag_v": "mag_v",
    "ra_deg": "ra_deg",
    "dec_deg": "dec_deg",
    "obj_type": "obj_type",
    "constellation": "constellation",
    # The UI's "Size" column is derived (``maj_axis × min_axis``), but sorting
    # by the major axis alone is the intuitive behavior — the largest
    # dimension drives the perceived footprint even when the minor is missing.
    "size": "maj_axis_arcmin",
    "distance_pc": "distance_pc",
}

# Catalogs whose designations ship alongside the list response. Detail
# returns the full set; list payloads stay compact.
LIST_DESIGNATION_CATALOGS: tuple[str, ...] = ("messier", "caldwell")

# Pattern-matches search keys a user might type into the "go to object"
# box: strip whitespace + dashes, lowercase. Equivalent to the loader's
# ``_build_search_key``.
_SEARCH_STRIP_RE = re.compile(r"[\s\-_]+")

# Stored search_keys use the short display-form prefix (``m42``, not
# ``messier42``). When a user types out the long catalog name
# (``messier42``, ``caldwell20``, ``sharpless2281``) we rewrite the
# prefix to the short form before matching.
_LONG_TO_SHORT_PREFIX: dict[str, str] = {
    "messier": "m",
    "caldwell": "c",
    "sharpless2": "sh2",
    "barnard": "b",
    "ruprecht": "ru",
    "dolidze": "do",
    "hickson": "hcg",
}


def normalize_search_key(query: str) -> str:
    normalized = _SEARCH_STRIP_RE.sub("", query).lower()
    for long, short in _LONG_TO_SHORT_PREFIX.items():
        if normalized.startswith(long):
            return short + normalized[len(long) :]
    return normalized


# Display ordering for external refs (v0.21.1): wikipedia first (editorial,
# user-facing), then simbad (CDS full-sky reference), then ned (NASA/IPAC
# extragalactic reference), then wikidata (structured-data link, hidden on
# the client). Frontend filters wikidata out at render time but it stays in
# the tuple for stable server-side sort. Update here when adding a new
# provider — the frontend's PROVIDER_LABEL map and allowlist mirror this.
_EXTERNAL_REF_PROVIDER_ORDER: tuple[str, ...] = (
    "wikipedia",
    "simbad",
    "ned",
    "wikidata",
)


def _external_ref_sort_key(provider: str) -> tuple[int, str]:
    """Stable sort key: known providers in fixed order, unknowns alphabetically last."""
    try:
        return (_EXTERNAL_REF_PROVIDER_ORDER.index(provider), "")
    except ValueError:
        return (len(_EXTERNAL_REF_PROVIDER_ORDER), provider)


async def _load_external_refs(conn, dso_id: int) -> list[ExternalRef]:
    """Return external refs for *dso_id* in canonical order."""
    cursor = await conn.execute(
        """
        SELECT provider, language, identifier, url, label
        FROM dso_external_ref
        WHERE dso_id = ?
        """,
        (dso_id,),
    )
    rows = await cursor.fetchall()
    refs = [
        ExternalRef(
            provider=row["provider"],
            language=row["language"],
            identifier=row["identifier"],
            url=row["url"],
            label=row["label"],
        )
        for row in rows
    ]
    refs.sort(key=lambda r: (_external_ref_sort_key(r.provider), r.language or "", r.identifier))
    return refs


async def _load_designations(
    conn, dso_ids: list[int], *, catalog_filter: tuple[str, ...] | None = None
) -> dict[int, list[DsoDesignation]]:
    """Fetch designations for a set of DSO ids, optionally filtered by catalog.

    Returns a mapping ``dso_id → [designations]`` with the primary first.
    """
    if not dso_ids:
        return {}

    id_placeholders = ",".join("?" * len(dso_ids))
    params: list = list(dso_ids)

    # Placeholders generated from validated id list + whitelist catalog names, not user input.
    base = f"SELECT dso_id, catalog, identifier, display_form, is_primary FROM dso_designation WHERE dso_id IN ({id_placeholders})"  # noqa: S608, E501  # nosec B608
    if catalog_filter:
        cat_placeholders = ",".join("?" * len(catalog_filter))
        base += f" AND (is_primary = 1 OR catalog IN ({cat_placeholders}))"  # nosec B608
        params.extend(catalog_filter)
    sql = base + " ORDER BY is_primary DESC, catalog, identifier"

    cursor = await conn.execute(sql, params)
    rows = await cursor.fetchall()

    grouped: dict[int, list[DsoDesignation]] = {dso_id: [] for dso_id in dso_ids}
    for row in rows:
        grouped[row["dso_id"]].append(
            DsoDesignation(
                catalog=row["catalog"],
                identifier=row["identifier"],
                display_form=row["display_form"],
                is_primary=bool(row["is_primary"]),
            )
        )
    return grouped


@router.get("", response_model=DsoListResponse)
async def list_dsos(
    q: str | None = Query(None, description="Free-text search over designations and common names"),
    type: str | None = Query(None, description="Comma-separated obj_type values"),
    type_group: str | None = Query(
        None,
        description=(
            "Comma-separated type-group names (e.g., 'Emission Nebula,Planetary Nebula'). "
            "Resolves to the union of raw types for those groups."
        ),
    ),
    constellation: str | None = Query(
        None,
        description=(
            "Comma-separated 3-letter IAU constellation codes (e.g., 'Ori,And'). "
            "OR semantics — a DSO matches if its constellation is any of the listed codes."
        ),
    ),
    has_distance: bool | None = Query(
        None, description="If set, filter DSOs with/without a populated distance_pc"
    ),
    catalog: str | None = Query(
        None,
        description=(
            "Comma-separated designation catalog codes (e.g., 'messier,ngc,barnard'). "
            "OR semantics — a DSO matches if it carries any of the listed catalogs."
        ),
    ),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort: str = Query("primary_designation"),
    sort_dir: Literal["asc", "desc"] = Query("asc"),
) -> DsoListResponse:
    if sort not in SORT_COLUMNS:
        raise HTTPException(status_code=400, detail=f"invalid sort column: {sort}")

    where_clauses: list[str] = ["d.active = 1"]
    params: list = []

    if type:
        type_values = [t.strip() for t in type.split(",") if t.strip()]
        if type_values:
            placeholders = ",".join("?" * len(type_values))
            where_clauses.append(f"d.obj_type IN ({placeholders})")
            params.extend(type_values)

    if type_group:
        # Resolve each group name to its raw type codes; union them all.
        group_names = [g.strip() for g in type_group.split(",") if g.strip()]
        raw_codes: list[str] = []
        for gname in group_names:
            raw_codes.extend(raw_types_for_group(gname))
        if raw_codes:
            placeholders = ",".join("?" * len(raw_codes))
            where_clauses.append(f"d.obj_type IN ({placeholders})")
            params.extend(raw_codes)
        else:
            # Unknown group name → zero matches.
            where_clauses.append("1 = 0")

    if constellation:
        const_values = [c.strip() for c in constellation.split(",") if c.strip()]
        if const_values:
            placeholders = ",".join("?" * len(const_values))
            where_clauses.append(f"d.constellation IN ({placeholders})")
            params.extend(const_values)

    if has_distance is True:
        where_clauses.append("d.distance_pc IS NOT NULL")
    elif has_distance is False:
        where_clauses.append("d.distance_pc IS NULL")

    if catalog:
        catalog_codes = [c.strip() for c in catalog.split(",") if c.strip()]
        if catalog_codes:
            placeholders = ",".join("?" * len(catalog_codes))
            where_clauses.append(
                f"d.id IN (SELECT dso_id FROM dso_designation WHERE catalog IN ({placeholders}))"  # noqa: S608, E501  # nosec B608
            )
            params.extend(catalog_codes)

    if q:
        search_key = normalize_search_key(q)
        # Match either a designation search_key exactly/prefix or a
        # case-insensitive substring of common_name.
        where_clauses.append(
            "(d.id IN (SELECT dso_id FROM dso_designation WHERE search_key LIKE ?) "
            "OR LOWER(d.common_name) LIKE ?)"
        )
        params.append(search_key + "%")
        params.append(f"%{q.lower()}%")

    where_sql = " AND ".join(where_clauses)

    async with get_db() as conn:
        # Total count
        count_sql = f"SELECT COUNT(*) AS n FROM dso d WHERE {where_sql}"  # nosec B608 - internal
        cursor = await conn.execute(count_sql, params)
        count_row = await cursor.fetchone()
        total = int(count_row["n"])

        order_col = SORT_COLUMNS[sort]
        order_dir = "DESC" if sort_dir == "desc" else "ASC"
        # Secondary ordering on id for deterministic pagination. `NULLS LAST`
        # on the primary sort so rows with missing values (no magnitude, no
        # coordinates) sink to the bottom regardless of direction — users
        # expect "unknown" at the end, not at the top of an ascending list.
        # order_col/order_dir from SORT_COLUMNS whitelist; params use placeholders.
        list_sql = f"SELECT d.id, d.primary_designation, d.obj_type, d.ra_deg, d.dec_deg, d.constellation, d.maj_axis_arcmin, d.min_axis_arcmin, d.mag_v, d.mag_b, d.distance_pc, d.distance_method, d.common_name FROM dso d WHERE {where_sql} ORDER BY d.{order_col} {order_dir} NULLS LAST, d.id ASC LIMIT ? OFFSET ?"  # noqa: S608, E501  # nosec B608
        cursor = await conn.execute(list_sql, [*params, limit, offset])
        rows = await cursor.fetchall()

        dso_ids = [row["id"] for row in rows]
        designations = await _load_designations(
            conn, dso_ids, catalog_filter=LIST_DESIGNATION_CATALOGS
        )

        items = [
            DsoListItem(
                id=row["id"],
                primary_designation=row["primary_designation"],
                obj_type=row["obj_type"],
                ra_deg=row["ra_deg"],
                dec_deg=row["dec_deg"],
                constellation=row["constellation"],
                maj_axis_arcmin=row["maj_axis_arcmin"],
                min_axis_arcmin=row["min_axis_arcmin"],
                mag_v=row["mag_v"],
                mag_b=row["mag_b"],
                distance_pc=row["distance_pc"],
                distance_method=row["distance_method"],
                common_name=row["common_name"],
                designations=designations.get(row["id"], []),
            )
            for row in rows
        ]

    return DsoListResponse(total=total, offset=offset, limit=limit, items=items)


@router.get("/lookup", response_model=DsoDetail | None)
async def lookup_dso(
    q: str = Query(..., description="Designation to resolve (e.g., 'M42', 'NGC 1976')"),
) -> DsoDetail | None:
    """Return the DSO whose search_key exactly matches *q*, or null."""
    search_key = normalize_search_key(q)
    async with get_db() as conn:
        cursor = await conn.execute(
            """
            SELECT d.id
            FROM dso d
            JOIN dso_designation dd ON dd.dso_id = d.id
            WHERE dd.search_key = ? AND d.active = 1
            LIMIT 1
            """,
            (search_key,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return await _fetch_detail(conn, int(row["id"]))


@router.get("/facets", response_model=DsoFacetsResponse)
async def list_facets(
    q: str | None = Query(None, description="Free-text search — mirrors /api/dso's param"),
    constellation: str | None = None,
    has_distance: bool | None = None,
    type: str | None = Query(None, description="Comma-separated raw obj_type codes"),
    type_group: str | None = Query(None, description="Comma-separated type-group names"),
    catalog: str | None = Query(None, description="Comma-separated catalog codes"),
) -> DsoFacetsResponse:
    """Distinct obj_type codes, type groups, and constellations with
    counts.

    When any of the filter params are supplied, the returned counts
    reflect **faceted-search** semantics: each chip's tally is "how
    many DSOs would match if only that chip were selected from this
    dimension, with all OTHER filter dimensions held constant". The
    UI uses this so chip labels like "Galaxy (234)" change with the
    user's current filter state instead of always showing full-
    catalog totals.

    Zero params = classic full-catalog counts (the v0.14.0 behaviour).
    """
    # Faceting by a dimension means: when counting for that dimension,
    # apply every OTHER filter but not this one. We implement this by
    # running three queries with slightly different WHERE clauses:
    #   1. Base counts (all filters applied) → used for constellations
    #   2. Without the type dimension → used for both raw types and
    #      type groups (they share the same dimension semantically —
    #      selecting a raw type implies its parent group).
    # ``base_sql_parts`` is the shared filter set that is applied on every
    # facet query (q + has_distance). Type, catalog, and constellation each
    # live in their own clause so each facet can exclude its OWN dimension
    # — that's what keeps the picker populated after the user makes a
    # selection (e.g. once a constellation chip is added, the constellation
    # picker must still show every other constellation's count).
    base_sql_parts: list[str] = ["d.active = 1"]
    base_params: list[object] = []

    if has_distance is True:
        base_sql_parts.append("d.distance_pc IS NOT NULL")
    elif has_distance is False:
        base_sql_parts.append("d.distance_pc IS NULL")
    if q and q.strip():
        search_key = normalize_search_key(q)
        base_sql_parts.append(
            "(d.id IN (SELECT dso_id FROM dso_designation WHERE search_key LIKE ?) "
            "OR LOWER(d.common_name) LIKE ?)"
        )
        base_params.append(search_key + "%")
        base_params.append(f"%{q.lower()}%")

    # Per-dimension clause builders. Each returns ``("", [])`` when its
    # corresponding query param is absent, otherwise a ready-to-splice
    # SQL fragment + bound params.
    def _type_clause() -> tuple[str, list[str]]:
        codes: list[str] = []
        if type:
            codes.extend(c.strip() for c in type.split(",") if c.strip())
        if type_group:
            groups = {g.strip() for g in type_group.split(",") if g.strip()}
            codes.extend(raw for g in TYPE_GROUPS if g.name in groups for raw in g.raw_types)
        if not codes:
            return "", []
        placeholders = ",".join("?" for _ in codes)
        return f"d.obj_type IN ({placeholders})", codes

    def _catalog_clause() -> tuple[str, list[str]]:
        if not catalog:
            return "", []
        codes = [c.strip() for c in catalog.split(",") if c.strip()]
        if not codes:
            return "", []
        placeholders = ",".join("?" for _ in codes)
        # Placeholders are a fixed string of ``?`` marks; codes bind via params.
        return (
            f"d.id IN (SELECT dso_id FROM dso_designation WHERE catalog IN ({placeholders}))",  # noqa: S608, E501  # nosec B608
            codes,
        )

    def _constellation_clause() -> tuple[str, list[str]]:
        if not constellation:
            return "", []
        values = [c.strip() for c in constellation.split(",") if c.strip()]
        if not values:
            return "", []
        placeholders = ",".join("?" for _ in values)
        return f"d.constellation IN ({placeholders})", values

    type_clause, type_params_fragment = _type_clause()
    cat_clause, cat_params_fragment = _catalog_clause()
    const_clause, const_params_fragment = _constellation_clause()

    def _compose(*clauses: tuple[str, list[str]]) -> tuple[str, list[object]]:
        """Join base + the provided per-dim clauses into one WHERE string."""
        parts = list(base_sql_parts)
        p: list[object] = list(base_params)
        for clause, bind in clauses:
            if clause:
                parts.append(clause)
                p.extend(bind)
        return " AND ".join(parts), p

    async with get_db() as conn:
        # Raw / type-group facet: excludes the type dimension. Catalog and
        # constellation ARE applied so selecting them narrows the type chips.
        raw_where, raw_params = _compose(
            (cat_clause, cat_params_fragment),
            (const_clause, const_params_fragment),
        )
        cursor = await conn.execute(
            f"SELECT obj_type, COUNT(*) AS n FROM dso d WHERE {raw_where} "  # noqa: S608  # nosec B608 — whitelisted clauses
            "GROUP BY obj_type ORDER BY obj_type",
            raw_params,
        )
        raw_counts: dict[str, int] = {r["obj_type"]: r["n"] for r in await cursor.fetchall()}

        # Constellations facet: excludes the constellation dimension so the
        # picker keeps showing every other constellation after a selection.
        const_where, const_params = _compose(
            (type_clause, type_params_fragment),
            (cat_clause, cat_params_fragment),
        )
        const_where = f"{const_where} AND d.constellation IS NOT NULL"
        cursor = await conn.execute(
            f"SELECT constellation, COUNT(*) AS n FROM dso d WHERE {const_where} "  # noqa: S608  # nosec B608 — whitelisted clauses
            "GROUP BY constellation ORDER BY constellation",
            const_params,
        )
        constellations = [
            ConstellationFacet(code=r["constellation"], count=r["n"])
            for r in await cursor.fetchall()
        ]

        # Catalogs facet: excludes the catalog dimension. Joins
        # dso_designation to surface the per-catalog count — a DSO with
        # 4 designations contributes to 4 catalogs, so this is an
        # "objects-per-catalog" tally, not distinct DSOs overall.
        cat_where, cat_params = _compose(
            (type_clause, type_params_fragment),
            (const_clause, const_params_fragment),
        )
        cursor = await conn.execute(
            f"SELECT dd.catalog, COUNT(DISTINCT d.id) AS n "  # noqa: S608  # nosec B608 — whitelisted clauses
            f"FROM dso d JOIN dso_designation dd ON dd.dso_id = d.id "
            f"WHERE {cat_where} GROUP BY dd.catalog ORDER BY dd.catalog",
            cat_params,
        )
        catalogs = [CatalogFacet(code=r["catalog"], count=r["n"]) for r in await cursor.fetchall()]

    raw_types = [RawTypeFacet(code=code, count=count) for code, count in sorted(raw_counts.items())]
    type_groups = [
        TypeGroupFacet(
            name=group.name,
            display_order=group.display_order,
            count=sum(raw_counts.get(raw, 0) for raw in group.raw_types),
            raw_types=list(group.raw_types),
        )
        for group in TYPE_GROUPS
    ]

    return DsoFacetsResponse(
        type_groups=type_groups,
        raw_types=raw_types,
        constellations=constellations,
        catalogs=catalogs,
    )


@router.get("/catalog-sources", response_model=list[CatalogSource])
async def list_catalog_sources() -> list[CatalogSource]:
    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT id, source_id, category, display_name, version, source_url, "
            "file_path, file_hash, license, attribution, loaded_at, row_count "
            "FROM dso_catalog_source ORDER BY loaded_at"
        )
        rows = await cursor.fetchall()
        return [
            CatalogSource(
                id=row["id"],
                source_id=row["source_id"],
                category=row["category"],
                display_name=row["display_name"],
                version=row["version"],
                source_url=row["source_url"],
                license=row["license"],
                attribution=row["attribution"],
                loaded_at=row["loaded_at"],
                row_count=row["row_count"],
            )
            for row in rows
        ]


@router.get("/{dso_id}", response_model=DsoDetail)
async def get_dso(dso_id: int) -> DsoDetail:
    async with get_db() as conn:
        return await _fetch_detail(conn, dso_id)


async def _fetch_detail(conn, dso_id: int) -> DsoDetail:
    cursor = await conn.execute("SELECT * FROM dso WHERE id = ? AND active = 1", (dso_id,))
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"DSO not found: {dso_id}")

    designations = (await _load_designations(conn, [dso_id])).get(dso_id, [])
    external_refs = await _load_external_refs(conn, dso_id)

    src_cursor = await conn.execute(
        "SELECT id, source_id, category, display_name, version, source_url, "
        "license, attribution, loaded_at, row_count "
        "FROM dso_catalog_source WHERE id = ?",
        (row["source_catalog_id"],),
    )
    src_row = await src_cursor.fetchone()
    source = CatalogSource(
        id=src_row["id"],
        source_id=src_row["source_id"],
        category=src_row["category"],
        display_name=src_row["display_name"],
        version=src_row["version"],
        source_url=src_row["source_url"],
        license=src_row["license"],
        attribution=src_row["attribution"],
        loaded_at=src_row["loaded_at"],
        row_count=src_row["row_count"],
    )

    return DsoDetail(
        id=row["id"],
        primary_designation=row["primary_designation"],
        obj_type=row["obj_type"],
        raw_obj_type=row["raw_obj_type"],
        ra_deg=row["ra_deg"],
        dec_deg=row["dec_deg"],
        constellation=row["constellation"],
        maj_axis_arcmin=row["maj_axis_arcmin"],
        min_axis_arcmin=row["min_axis_arcmin"],
        position_angle_deg=row["position_angle_deg"],
        mag_b=row["mag_b"],
        mag_v=row["mag_v"],
        mag_j=row["mag_j"],
        mag_h=row["mag_h"],
        mag_k=row["mag_k"],
        surface_brightness=row["surface_brightness"],
        hubble_type=row["hubble_type"],
        pm_ra=row["pm_ra"],
        pm_dec=row["pm_dec"],
        redshift=row["redshift"],
        radial_velocity=row["radial_velocity"],
        cstar_mag_u=row["cstar_mag_u"],
        cstar_mag_b=row["cstar_mag_b"],
        cstar_mag_v=row["cstar_mag_v"],
        cstar_id=row["cstar_id"],
        distance_pc=row["distance_pc"],
        distance_method=row["distance_method"],
        common_name=row["common_name"],
        common_name_augmented=bool(row["common_name_augmented"]),
        surface_brightness_augmented=bool(row["surface_brightness_augmented"]),
        ned_notes=row["ned_notes"],
        openngc_notes=row["openngc_notes"],
        raw_other_id=row["raw_other_id"],
        designations=designations,
        external_refs=external_refs,
        source=source,
    )
