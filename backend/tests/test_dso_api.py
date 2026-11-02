"""Tests for the DSO catalog API."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.catalog_loader import load_catalogs
from nightcrate.db.session import get_db
from nightcrate.main import app

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "catalogs" / "openngc"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def dso_loaded(tmp_path):
    """Stage the mini fixtures into the test DB and run the loader."""
    openngc_dir = tmp_path / "catalogs" / "openngc"
    openngc_dir.mkdir(parents=True)
    shutil.copy(FIXTURE_DIR / "mini_NGC.csv", openngc_dir / "NGC.csv")
    shutil.copy(FIXTURE_DIR / "mini_addendum.csv", openngc_dir / "addendum.csv")
    shutil.copy(FIXTURE_DIR / "version.json", openngc_dir / "version.json")

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    load_catalogs(conn, tmp_path / "catalogs")
    conn.close()


async def _insert_sort_dso(
    primary: str,
    *,
    marker: str,
    obj_type: str = "G",
    constellation: str | None = "Ori",
    common_name: str | None = None,
    designations: tuple[tuple[str, str, str, bool], ...] = (),
) -> int:
    async with get_db() as conn:
        source = await conn.execute("SELECT id FROM dso_catalog_source WHERE source_id = 'openngc'")
        source_id = int((await source.fetchone())["id"])
        cursor = await conn.execute(
            """
            INSERT INTO dso (
                primary_designation, obj_type, constellation, common_name,
                source_catalog_id, source_row_hash, source_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                primary,
                obj_type,
                constellation,
                common_name,
                source_id,
                f"phase-f-{marker}",
                f"phase-f-{marker}",
            ),
        )
        assert cursor.lastrowid is not None
        dso_id = int(cursor.lastrowid)
        await conn.executemany(
            """
            INSERT INTO dso_designation (
                dso_id, catalog, identifier, display_form, search_key, is_primary
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                (dso_id, catalog, identifier, display, f"phasef{marker}", int(is_primary))
                for catalog, identifier, display, is_primary in designations
            ),
        )
        await conn.commit()
    return dso_id


# ── List ──────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_list_returns_all_loaded_dsos(client, dso_loaded):
    resp = await client.get("/api/dso")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 11  # 9 canonical from NGC + 2 from addendum
    assert body["limit"] == 100
    assert body["offset"] == 0
    assert len(body["items"]) == 11


@pytest.mark.anyio
async def test_list_pagination(client, dso_loaded):
    page1 = (await client.get("/api/dso?limit=3&offset=0")).json()
    page2 = (await client.get("/api/dso?limit=3&offset=3")).json()
    assert len(page1["items"]) == 3
    assert len(page2["items"]) == 3
    assert {i["id"] for i in page1["items"]}.isdisjoint({i["id"] for i in page2["items"]})


@pytest.mark.anyio
async def test_list_filter_by_single_type(client, dso_loaded):
    resp = await client.get("/api/dso?type=HII")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 2  # NGC1976 (Orion) + NGC0281 (Pacman)
    assert all(i["obj_type"] == "HII" for i in items)


@pytest.mark.anyio
async def test_list_filter_by_multiple_types(client, dso_loaded):
    resp = await client.get("/api/dso?type=HII,PN")
    items = resp.json()["items"]
    types = {i["obj_type"] for i in items}
    assert types == {"HII", "PN"}


@pytest.mark.anyio
async def test_list_filter_by_constellation(client, dso_loaded):
    resp = await client.get("/api/dso?constellation=Per")
    items = resp.json()["items"]
    assert len(items) == 2  # NGC0869 + NGC0884 (Double Cluster)
    assert all(i["constellation"] == "Per" for i in items)


@pytest.mark.anyio
async def test_list_filter_by_multiple_constellations_is_or_semantic(client, dso_loaded):
    """``constellation=Per,Ori`` returns rows from either constellation."""
    resp = await client.get("/api/dso?constellation=Per,Ori")
    items = resp.json()["items"]
    constellations = {i["constellation"] for i in items}
    assert constellations == {"Per", "Ori"}


@pytest.mark.anyio
async def test_constellations_facet_does_not_collapse_after_selection(client, dso_loaded):
    """Selecting one constellation must NOT empty the facet for the rest —
    otherwise the multi-select picker would hide every remaining option
    after the first click."""
    unfiltered = (await client.get("/api/dso/facets")).json()
    filtered = (await client.get("/api/dso/facets?constellation=Per")).json()
    unfiltered_codes = {c["code"] for c in unfiltered["constellations"]}
    filtered_codes = {c["code"] for c in filtered["constellations"]}
    assert filtered_codes == unfiltered_codes


@pytest.mark.anyio
async def test_list_search_matches_messier_designation(client, dso_loaded):
    resp = await client.get("/api/dso?q=M42")
    items = resp.json()["items"]
    assert any(i["primary_designation"] == "M 42" for i in items)


@pytest.mark.anyio
async def test_list_search_matches_ngc_with_space(client, dso_loaded):
    # "ngc 1976" normalizes to "ngc1976" — must still match.
    resp = await client.get("/api/dso?q=ngc 1976")
    items = resp.json()["items"]
    assert any(i["primary_designation"] == "M 42" for i in items)


@pytest.mark.anyio
async def test_list_search_matches_common_name(client, dso_loaded):
    resp = await client.get("/api/dso?q=Orion Nebula")
    items = resp.json()["items"]
    assert any(i["primary_designation"] == "M 42" for i in items)


@pytest.mark.anyio
async def test_list_sort_by_mag_v_ascending(client, dso_loaded):
    resp = await client.get("/api/dso?sort=mag_v&sort_dir=asc&limit=500")
    items = [i for i in resp.json()["items"] if i["mag_v"] is not None]
    mags = [i["mag_v"] for i in items]
    assert mags == sorted(mags)


@pytest.mark.anyio
async def test_list_invalid_sort_returns_400(client, dso_loaded):
    resp = await client.get("/api/dso?sort=invalid_column")
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_list_invalid_sort_direction_returns_422(client, dso_loaded):
    resp = await client.get("/api/dso?sort_dir=sideways")
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_designation_sort_is_natural_stable_and_keeps_missing_primary_rows(
    client, dso_loaded
):
    values = [
        "NGC 800010",
        "NGC 800002",
        "ESO 800107-010",
        "ESO 800107-2",
        "M 9001",
        "Mel 9001",
    ]
    catalogs = ["ngc", "ngc", "eso", "eso", "messier", "mel"]
    inserted: list[int] = []
    for index, (display, catalog) in enumerate(zip(values, catalogs, strict=True)):
        identifier = display.split(" ", 1)[1]
        inserted.append(
            await _insert_sort_dso(
                display,
                marker=f"natural-{index}",
                common_name="Phase F natural",
                designations=((catalog, identifier, display, True),),
            )
        )
    missing_id = await _insert_sort_dso(
        "ZZ 3", marker="natural-missing", common_name="Phase F natural"
    )
    inserted.append(missing_id)

    ascending = (
        await client.get(
            "/api/dso",
            params={"q": "Phase F natural", "sort": "primary_designation", "limit": 500},
        )
    ).json()
    assert [item["display_designation"] for item in ascending["items"]] == [
        "ESO 800107-2",
        "ESO 800107-010",
        "M 9001",
        "Mel 9001",
        "NGC 800002",
        "NGC 800010",
        "ZZ 3",
    ]
    assert (
        next(item for item in ascending["items"] if item["id"] == missing_id)["designations"] == []
    )

    descending = (
        await client.get(
            "/api/dso",
            params={
                "q": "Phase F natural",
                "sort": "primary_designation",
                "sort_dir": "desc",
                "limit": 500,
            },
        )
    ).json()
    assert [item["display_designation"] for item in descending["items"]] == list(
        reversed([item["display_designation"] for item in ascending["items"]])
    )

    paged_ids: list[int] = []
    for offset in (0, 3, 6):
        page = (
            await client.get(
                "/api/dso",
                params={"q": "Phase F natural", "limit": 3, "offset": offset},
            )
        ).json()
        paged_ids.extend(item["id"] for item in page["items"])
    assert len(paged_ids) == len(set(paged_ids)) == 7
    assert set(paged_ids) == set(inserted)


@pytest.mark.anyio
async def test_single_catalog_uses_lowest_alias_before_pagination_in_both_directions(
    client, dso_loaded
):
    await _insert_sort_dso(
        "NGC 800001",
        marker="catalog-a",
        common_name="Phase F catalog",
        designations=(
            ("ngc", "800001", "NGC 800001", True),
            ("caldwell", "20", "C 20", False),
            ("caldwell", "3", "C 3", False),
        ),
    )
    await _insert_sort_dso(
        "NGC 800002",
        marker="catalog-b",
        common_name="Phase F catalog",
        designations=(
            ("ngc", "800002", "NGC 800002", True),
            ("caldwell", "10", "C 10", False),
        ),
    )

    params = {
        "q": "Phase F catalog",
        "catalog": "caldwell,caldwell",
        "sort": "primary_designation",
        "sort_dir": "desc",
    }
    body = (await client.get("/api/dso", params=params)).json()
    assert body["total"] == 2
    assert [item["display_designation"] for item in body["items"]] == ["C 10", "C 3"]
    first_aliases = {d["display_form"] for d in body["items"][1]["designations"]}
    assert {"NGC 800001", "C 3", "C 20"} <= first_aliases


@pytest.mark.anyio
async def test_multi_catalog_display_rank_and_exact_order_are_filter_order_independent(
    client, dso_loaded
):
    groups = {
        "G2 MI": (
            (
                "M 9010",
                (("messier", "9010", "M 9010", True), ("ic", "9099", "IC 9099", False)),
            ),
            ("IC 9002", (("ic", "9002", "IC 9002", True),)),
            ("M 9002", (("messier", "9002", "M 9002", True),)),
            ("IC 9010", (("ic", "9010", "IC 9010", True),)),
        ),
        "G2 MC": (
            (
                "M 9110",
                (
                    ("messier", "9110", "M 9110", True),
                    ("caldwell", "9199", "C 9199", False),
                ),
            ),
            ("C 9102", (("caldwell", "9102", "C 9102", True),)),
            ("M 9102", (("messier", "9102", "M 9102", True),)),
            ("C 9110", (("caldwell", "9110", "C 9110", True),)),
        ),
        "G2 NI": (
            (
                "NGC 9210",
                (("ngc", "9210", "NGC 9210", True), ("ic", "9201", "IC 9201", False)),
            ),
            ("IC 9203", (("ic", "9203", "IC 9203", True),)),
            ("NGC 9202", (("ngc", "9202", "NGC 9202", True),)),
        ),
        "G2 SB": (
            (
                "B 9320",
                (
                    ("barnard", "9320", "B 9320", True),
                    ("sharpless2", "9301", "Sh2-9301", False),
                ),
            ),
            ("Sh2-9302", (("sharpless2", "9302", "Sh2-9302", True),)),
            ("B 9303", (("barnard", "9303", "B 9303", True),)),
        ),
    }
    for group, objects in groups.items():
        for index, (primary, designations) in enumerate(objects):
            await _insert_sort_dso(
                primary,
                marker=f"{group}-{index}",
                common_name=group,
                designations=designations,
            )

    cases = (
        ("G2 MI", "messier,ic", ["IC 9002", "IC 9010", "M 9002", "M 9010"]),
        ("G2 MC", "messier,caldwell", ["C 9102", "C 9110", "M 9102", "M 9110"]),
        ("G2 NI", "ngc,ic", ["IC 9203", "NGC 9202", "NGC 9210"]),
        ("G2 SB", "sharpless2,barnard", ["B 9303", "B 9320", "Sh2-9302"]),
    )
    for query, catalogs, expected in cases:
        ascending = (
            await client.get(
                "/api/dso",
                params={"q": query, "catalog": catalogs, "sort": "primary_designation"},
            )
        ).json()
        descending = (
            await client.get(
                "/api/dso",
                params={
                    "q": query,
                    "catalog": catalogs,
                    "sort": "primary_designation",
                    "sort_dir": "desc",
                },
            )
        ).json()
        assert ascending["total"] == len(expected)
        assert [item["display_designation"] for item in ascending["items"]] == expected
        assert [item["display_designation"] for item in descending["items"]] == list(
            reversed(expected)
        )

    canonical = (
        await client.get(
            "/api/dso",
            params={"q": "G2 MI", "catalog": "messier,ic", "sort": "primary_designation"},
        )
    ).json()
    reversed_duplicated = (
        await client.get(
            "/api/dso",
            params={
                "q": "G2 MI",
                "catalog": "ic,messier,ic,messier",
                "sort": "primary_designation",
            },
        )
    ).json()
    assert [item["id"] for item in reversed_duplicated["items"]] == [
        item["id"] for item in canonical["items"]
    ]
    assert [item["display_designation"] for item in reversed_duplicated["items"]] == [
        item["display_designation"] for item in canonical["items"]
    ]

    single_catalog = (
        await client.get(
            "/api/dso",
            params={"q": "G2 MI", "catalog": "ic", "sort": "primary_designation"},
        )
    ).json()
    assert [item["display_designation"] for item in single_catalog["items"]] == [
        "IC 9002",
        "IC 9010",
        "IC 9099",
    ]
    unfiltered = (
        await client.get("/api/dso", params={"q": "G2 MI", "sort": "primary_designation"})
    ).json()
    assert [item["display_designation"] for item in unfiltered["items"]] == [
        "IC 9002",
        "IC 9010",
        "M 9002",
        "M 9010",
    ]


@pytest.mark.anyio
async def test_multi_catalog_equal_keys_paging_and_combined_alias_search(client, dso_loaded):
    tie_first = await _insert_sort_dso(
        "IC 0002",
        marker="g2-tie-first",
        common_name="G2 paging",
        designations=(("ic", "9402a", "IC 0002", True),),
    )
    tie_second = await _insert_sort_dso(
        "IC 2",
        marker="g2-tie-second",
        common_name="G2 paging",
        designations=(("ic", "9402b", "IC 2", True),),
    )
    for marker, display, catalog, identifier in (
        ("one", "IC 1", "ic", "9401"),
        ("ten", "IC 10", "ic", "9410"),
        ("messier", "M 3", "messier", "9403"),
    ):
        await _insert_sort_dso(
            display,
            marker=f"g2-page-{marker}",
            common_name="G2 paging",
            designations=((catalog, identifier, display, True),),
        )

    for direction, expected_names in (
        ("asc", ["IC 1", "IC 0002", "IC 2", "IC 10", "M 3"]),
        ("desc", ["M 3", "IC 10", "IC 0002", "IC 2", "IC 1"]),
    ):
        params = {
            "q": "G2 paging",
            "catalog": "messier,ic",
            "sort": "primary_designation",
            "sort_dir": direction,
        }
        full = (await client.get("/api/dso", params=params)).json()["items"]
        paged = []
        for offset in (0, 2, 4):
            page = (
                await client.get("/api/dso", params={**params, "limit": 2, "offset": offset})
            ).json()["items"]
            paged.extend(page)
        assert [item["display_designation"] for item in full] == expected_names
        assert [item["id"] for item in paged] == [item["id"] for item in full]
        tie_ids = [
            item["id"] for item in full if item["display_designation"] in {"IC 0002", "IC 2"}
        ]
        assert tie_ids == [tie_first, tie_second]

    combined_id = await _insert_sort_dso(
        "M 9509",
        marker="g2-combined",
        common_name="Independent filters",
        obj_type="HII",
        constellation="Ori",
        designations=(
            ("messier", "9509", "M 9509", True),
            ("ic", "9599", "IC 9599", False),
            ("pgc", "987654", "PGC 987654", False),
        ),
    )
    async with get_db() as conn:
        await conn.execute(
            "UPDATE dso_designation SET search_key = 'pgc987654' "
            "WHERE dso_id = ? AND catalog = 'pgc'",
            (combined_id,),
        )
        await conn.commit()
    combined = (
        await client.get(
            "/api/dso",
            params={
                "q": "PGC 987654",
                "catalog": "messier,ic",
                "type": "HII",
                "constellation": "Ori",
                "sort": "primary_designation",
            },
        )
    ).json()
    assert combined["total"] == 1
    assert combined["items"][0]["id"] == combined_id
    assert combined["items"][0]["display_designation"] == "M 9509"


@pytest.mark.anyio
async def test_label_and_common_name_sorts_match_display_with_missing_last(client, dso_loaded):
    await _insert_sort_dso(
        "TYPE STAR",
        marker="type-star",
        obj_type="*",
        designations=(("abell", "9002", "Abell 9002", False),),
    )
    await _insert_sort_dso(
        "TYPE GALAXY",
        marker="type-galaxy",
        obj_type="G",
        designations=(("abell", "9001", "Abell 9001", False),),
    )
    type_items = (
        await client.get("/api/dso", params={"catalog": "abell", "sort": "obj_type"})
    ).json()["items"]
    assert [item["primary_designation"] for item in type_items] == ["TYPE GALAXY", "TYPE STAR"]

    for index, constellation in enumerate(("CMa", "Cam")):
        await _insert_sort_dso(
            f"CONST {constellation}",
            marker=f"const-{index}",
            constellation=constellation,
            designations=(("arp", str(9001 + index), f"Arp {9001 + index}", False),),
        )
    constellation_items = (
        await client.get("/api/dso", params={"catalog": "arp", "sort": "constellation"})
    ).json()["items"]
    assert [
        item["constellation"]
        for item in constellation_items
        if item["primary_designation"].startswith("CONST ")
    ] == ["Cam", "CMa"]

    common_values = ("alpha", "Beta", "", None)
    for index, common_name in enumerate(common_values):
        await _insert_sort_dso(
            f"COMMON {index}",
            marker=f"common-{index}",
            common_name=common_name,
            designations=(("hickson", str(9001 + index), f"HCG {9001 + index}", False),),
        )
    ascending = (
        await client.get("/api/dso", params={"catalog": "hickson", "sort": "common_name"})
    ).json()["items"]
    descending = (
        await client.get(
            "/api/dso",
            params={"catalog": "hickson", "sort": "common_name", "sort_dir": "desc"},
        )
    ).json()["items"]
    assert [
        item["common_name"]
        for item in ascending
        if item["primary_designation"].startswith("COMMON ")
    ] == ["alpha", "Beta", "", None]
    assert [
        item["common_name"]
        for item in descending
        if item["primary_designation"].startswith("COMMON ")
    ] == ["Beta", "alpha", "", None]


@pytest.mark.anyio
async def test_list_designations_are_complete_ranked_and_keep_primary_flags(client, dso_loaded):
    resp = await client.get("/api/dso?q=M42")
    items = resp.json()["items"]
    m42 = next(i for i in items if i["primary_designation"] == "M 42")
    assert [
        (designation["catalog"], designation["display_form"], designation["is_primary"])
        for designation in m42["designations"]
    ] == [
        ("messier", "M 42", True),
        ("ngc", "NGC 1976", False),
        ("lbn", "LBN 974", False),
        ("pgc", "PGC 26257", False),
    ]


# ── Detail ───────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_detail_returns_full_designation_list(client, dso_loaded):
    # Find M42 first
    search = (await client.get("/api/dso?q=M42")).json()
    m42 = next(i for i in search["items"] if i["primary_designation"] == "M 42")
    resp = await client.get(f"/api/dso/{m42['id']}")
    assert resp.status_code == 200
    detail = resp.json()
    catalogs = {d["catalog"] for d in detail["designations"]}
    # Now all designations including LBN and PGC should be present.
    assert "messier" in catalogs
    assert "ngc" in catalogs
    assert "lbn" in catalogs
    assert "pgc" in catalogs
    assert detail["source"]["source_id"] == "openngc"


@pytest.mark.anyio
async def test_detail_returns_inactive_object_while_list_and_search_hide_it(client, dso_loaded):
    search = (await client.get("/api/dso?q=M42")).json()
    m42 = next(i for i in search["items"] if i["primary_designation"] == "M 42")
    async with get_db() as conn:
        await conn.execute("UPDATE dso SET active = 0 WHERE id = ?", (m42["id"],))
        await conn.commit()

    detail = await client.get(f"/api/dso/{m42['id']}")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["active"] is False
    assert detail_body["source"]["source_id"] == "openngc"
    assert (await client.get("/api/dso?q=M42")).json()["items"] == []


@pytest.mark.anyio
async def test_detail_404_on_unknown_id(client, dso_loaded):
    resp = await client.get("/api/dso/999999")
    assert resp.status_code == 404


# ── Lookup ───────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_lookup_exact_match(client, dso_loaded):
    resp = await client.get("/api/dso/lookup?q=M42")
    assert resp.status_code == 200
    body = resp.json()
    assert body is not None
    assert body["primary_designation"] == "M 42"


@pytest.mark.anyio
async def test_lookup_tolerates_whitespace_and_case(client, dso_loaded):
    for query in ("M 42", "m 42", "messier42", "messier 42"):
        resp = await client.get(f"/api/dso/lookup?q={query}")
        body = resp.json()
        assert body is not None, f"lookup failed for {query!r}"
        assert body["primary_designation"] == "M 42"


@pytest.mark.anyio
async def test_lookup_returns_null_on_miss(client, dso_loaded):
    resp = await client.get("/api/dso/lookup?q=NotARealObject")
    assert resp.status_code == 200
    assert resp.json() is None


# ── Facets and catalog sources ───────────────────────────────────────────────


@pytest.mark.anyio
async def test_facets_returns_types_and_constellations_with_counts(client, dso_loaded):
    resp = await client.get("/api/dso/facets")
    assert resp.status_code == 200
    body = resp.json()
    raw_counts = {t["code"]: t["count"] for t in body["raw_types"]}
    assert raw_counts["HII"] == 2  # NGC1976 + NGC0281
    assert raw_counts["G"] == 2  # NGC0224 + NGC5457
    const_counts = {c["code"]: c["count"] for c in body["constellations"]}
    assert const_counts["Per"] == 2
    # Type groups aggregate raw codes. "Emission Nebula" covers HII+EmN+Cl+N.
    group_counts = {g["name"]: g["count"] for g in body["type_groups"]}
    assert group_counts["Emission Nebula"] == 2
    assert group_counts["Galaxy"] == 2


@pytest.mark.anyio
async def test_catalog_sources_endpoint(client, dso_loaded):
    resp = await client.get("/api/dso/catalog-sources")
    assert resp.status_code == 200
    sources = resp.json()
    ids = {s["source_id"] for s in sources}
    # OpenNGC + nightcrate bundled sources always register in tests; VizieR
    # sources stay "missing" and don't show up until fetched.
    assert {"openngc", "openngc_addendum"} <= ids
    assert "nightcrate_augment" in ids
    # Attribution is always populated.
    assert all(s["attribution"] for s in sources)


# ── v0.15.0 extensions: type_group, has_distance, distance sort, facets ─────


@pytest.mark.anyio
async def test_list_filter_by_type_group(client, dso_loaded):
    """type_group=Emission Nebula expands to HII+EmN+Cl+N."""
    resp = await client.get("/api/dso?type_group=Emission Nebula")
    assert resp.status_code == 200
    items = resp.json()["items"]
    types = {i["obj_type"] for i in items}
    # Mini fixture contains HII only in this group.
    assert types <= {"HII", "EmN", "Cl+N"}
    assert len(items) >= 1


@pytest.mark.anyio
async def test_list_filter_by_has_distance_true(client, dso_loaded):
    resp = await client.get("/api/dso?has_distance=true")
    items = resp.json()["items"]
    assert all(i["distance_pc"] is not None for i in items)


@pytest.mark.anyio
async def test_list_filter_by_has_distance_false(client, dso_loaded):
    resp = await client.get("/api/dso?has_distance=false")
    items = resp.json()["items"]
    assert all(i["distance_pc"] is None for i in items)


@pytest.mark.anyio
async def test_list_sort_by_distance_pc_nulls_last(client, dso_loaded):
    resp = await client.get("/api/dso?sort=distance_pc&sort_dir=asc&limit=500")
    items = resp.json()["items"]
    with_dist = [i for i in items if i["distance_pc"] is not None]
    without = [i for i in items if i["distance_pc"] is None]
    # All items with a distance come before items without.
    assert items[: len(with_dist)] == with_dist
    assert items[len(with_dist) :] == without


@pytest.mark.anyio
async def test_facets_includes_type_groups_and_raw_types(client, dso_loaded):
    resp = await client.get("/api/dso/facets")
    body = resp.json()
    assert "type_groups" in body
    assert "raw_types" in body
    # Every type_groups entry carries a raw_types list.
    assert all("raw_types" in g for g in body["type_groups"])


# ── v0.18.1 extensions: catalog filter + catalogs facet ─────────────────────


@pytest.mark.anyio
async def test_list_filter_by_single_catalog_messier(client, dso_loaded):
    """catalog=messier returns only DSOs with a Messier designation."""
    resp = await client.get("/api/dso?catalog=messier")
    assert resp.status_code == 200
    items = resp.json()["items"]
    designation_sets = [{d["catalog"] for d in i["designations"]} for i in items]
    assert all("messier" in s for s in designation_sets)
    # Mini NGC fixture has M42 (NGC1976), M31 (NGC224), M101 (NGC5457).
    primary_names = {i["primary_designation"] for i in items}
    assert {"M 42", "M 31", "M 101"} <= primary_names


@pytest.mark.anyio
async def test_list_filter_by_multiple_catalogs_is_or_semantic(client, dso_loaded):
    """catalog=messier,barnard returns the union, not the intersection."""
    messier_only = (await client.get("/api/dso?catalog=messier")).json()["items"]
    # Use NGC (huge overlap) to prove union semantics: messier ⊂ union, and
    # the union has rows messier alone doesn't (e.g. NGC 281 / Pacman, which
    # carries an NGC designation but not a Messier one).
    union = (await client.get("/api/dso?catalog=messier,ngc")).json()["items"]
    assert len(union) > len(messier_only)
    primary_names = {i["primary_designation"] for i in union}
    assert "NGC 281" in primary_names


@pytest.mark.anyio
async def test_list_filter_by_unknown_catalog_returns_empty(client, dso_loaded):
    """An unknown catalog code matches zero DSOs (no designations for it)."""
    resp = await client.get("/api/dso?catalog=doesnotexist")
    assert resp.json()["total"] == 0


@pytest.mark.anyio
async def test_facets_includes_catalog_counts(client, dso_loaded):
    resp = await client.get("/api/dso/facets")
    body = resp.json()
    assert "catalogs" in body
    catalog_counts = {c["code"]: c["count"] for c in body["catalogs"]}
    # Every canonical NGC row in the fixture contributes an 'ngc' designation.
    assert catalog_counts.get("ngc", 0) >= 8
    # Messier subset is smaller than NGC.
    assert 0 < catalog_counts.get("messier", 0) < catalog_counts["ngc"]


@pytest.mark.anyio
async def test_catalog_facet_excludes_own_dimension_filter(client, dso_loaded):
    """When catalog filter is active, the catalogs facet still surfaces
    the full distribution across catalogs — its own dimension is
    excluded from its own facet query (classic faceted search)."""
    unfiltered = (await client.get("/api/dso/facets")).json()
    filtered = (await client.get("/api/dso/facets?catalog=messier")).json()
    unfiltered_codes = {c["code"] for c in unfiltered["catalogs"]}
    filtered_codes = {c["code"] for c in filtered["catalogs"]}
    # Catalogs facet should not collapse to only messier.
    assert filtered_codes == unfiltered_codes
    # Other-dimension facets DO apply the catalog filter — raw type counts
    # under catalog=messier should be lower than unfiltered.
    unfiltered_raw = {t["code"]: t["count"] for t in unfiltered["raw_types"]}
    filtered_raw = {t["code"]: t["count"] for t in filtered["raw_types"]}
    # Galaxies: M31 + M101 both have messier designations, so count stays ≥ 2
    # but cannot exceed the unfiltered total.
    assert filtered_raw.get("G", 0) <= unfiltered_raw.get("G", 0)


@pytest.mark.anyio
async def test_detail_includes_distance_and_augmentation_flags(client, dso_loaded):
    # M42 has a curated distance per the bundled augment CSV.
    search = (await client.get("/api/dso?q=M42")).json()
    m42 = next(i for i in search["items"] if i["primary_designation"] == "M 42")
    detail = (await client.get(f"/api/dso/{m42['id']}")).json()
    assert detail["distance_pc"] == pytest.approx(412.0, abs=1e-3)
    assert detail["distance_method"] == "curated"
    assert detail["common_name_augmented"] is True


# ── External references ──────────────────────────────────────────────────────


MINI_WIKIDATA = Path(__file__).parent / "fixtures" / "catalogs" / "wikidata"


@pytest.fixture
async def dso_loaded_with_wikidata(tmp_path):
    """Stage OpenNGC + Wikidata TSV + reload so detail responses carry
    external_refs."""
    openngc_dir = tmp_path / "catalogs" / "openngc"
    openngc_dir.mkdir(parents=True)
    shutil.copy(FIXTURE_DIR / "mini_NGC.csv", openngc_dir / "NGC.csv")
    shutil.copy(FIXTURE_DIR / "mini_addendum.csv", openngc_dir / "addendum.csv")
    shutil.copy(FIXTURE_DIR / "version.json", openngc_dir / "version.json")
    wd_dir = tmp_path / "catalogs" / "wikidata"
    wd_dir.mkdir(parents=True)
    shutil.copy(MINI_WIKIDATA / "mini_wikidata.tsv", wd_dir / "dso_external_refs.tsv")

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    load_catalogs(conn, tmp_path / "catalogs")
    conn.close()


@pytest.mark.anyio
async def test_detail_includes_external_refs_with_wikipedia_first(client, dso_loaded_with_wikidata):
    """M42 (emission nebula, not extragalactic) gets three refs in the
    order wikipedia → simbad → wikidata. NED is skipped by the
    extragalactic filter (v0.21.1)."""
    search = (await client.get("/api/dso?q=M42")).json()
    m42 = next(i for i in search["items"] if i["primary_designation"] == "M 42")
    detail = (await client.get(f"/api/dso/{m42['id']}")).json()
    refs = detail["external_refs"]
    assert [r["provider"] for r in refs] == ["wikipedia", "simbad", "wikidata"]

    assert refs[0]["language"] == "en"
    assert refs[0]["identifier"] == "Orion_Nebula"
    assert refs[0]["url"] == "https://en.wikipedia.org/wiki/Orion_Nebula"
    assert refs[0]["label"] == "Orion Nebula"

    assert refs[1]["language"] is None
    assert refs[1]["identifier"] == "NAME ORI NEB"
    assert refs[1]["url"].startswith("https://simbad.u-strasbg.fr/simbad/sim-id?Ident=")

    assert refs[2]["language"] is None
    assert refs[2]["identifier"] == "Q13903"


@pytest.mark.anyio
async def test_detail_returns_empty_external_refs_for_unmatched_dso(client, dso_loaded):
    """When no Wikidata data is loaded, every DSO detail carries an empty array."""
    search = (await client.get("/api/dso?q=M42")).json()
    m42 = next(i for i in search["items"] if i["primary_designation"] == "M 42")
    detail = (await client.get(f"/api/dso/{m42['id']}")).json()
    assert detail["external_refs"] == []


@pytest.mark.anyio
async def test_lookup_endpoint_includes_external_refs(client, dso_loaded_with_wikidata):
    """The /lookup endpoint shares _fetch_detail — verify the shape is identical."""
    detail = (await client.get("/api/dso/lookup?q=M42")).json()
    assert detail is not None
    assert "external_refs" in detail
    providers = [r["provider"] for r in detail["external_refs"]]
    assert providers == ["wikipedia", "simbad", "wikidata"]


@pytest.mark.anyio
async def test_list_response_does_not_include_external_refs(client, dso_loaded_with_wikidata):
    """External refs are detail-only; list payloads stay compact."""
    response = (await client.get("/api/dso?q=M42")).json()
    item = response["items"][0]
    assert "external_refs" not in item
