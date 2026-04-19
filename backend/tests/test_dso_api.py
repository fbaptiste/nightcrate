"""Tests for the DSO catalog API."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.catalog_loader import load_catalogs
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
async def test_list_designations_contain_messier_only(client, dso_loaded):
    """List endpoint trims designations to primary + messier + caldwell."""
    resp = await client.get("/api/dso?q=M42")
    items = resp.json()["items"]
    m42 = next(i for i in items if i["primary_designation"] == "M 42")
    catalogs = {d["catalog"] for d in m42["designations"]}
    # Must include primary (messier) but NOT the LBN/PGC extras.
    assert "messier" in catalogs
    assert "lbn" not in catalogs
    assert "pgc" not in catalogs


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
    type_counts = {t["value"]: t["count"] for t in body["obj_types"]}
    assert type_counts["HII"] == 2  # NGC1976 + NGC0281
    assert type_counts["G"] == 2  # NGC0224 + NGC5457
    const_counts = {c["value"]: c["count"] for c in body["constellations"]}
    assert const_counts["Per"] == 2


@pytest.mark.anyio
async def test_catalog_sources_endpoint(client, dso_loaded):
    resp = await client.get("/api/dso/catalog-sources")
    assert resp.status_code == 200
    sources = resp.json()
    ids = {s["source_id"] for s in sources}
    assert ids == {"openngc", "openngc_addendum"}
    # Attribution is always populated (from version.json).
    assert all(s["attribution"] for s in sources)
