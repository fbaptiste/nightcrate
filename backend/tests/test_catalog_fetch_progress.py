"""Registry and admin-API coverage for explicit catalog-action progress."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.catalog_loader.loader import LoadSummary, SourceResult
from nightcrate.main import app
from nightcrate.services import catalog_progress


@pytest.fixture(autouse=True)
def _reset_progress():
    catalog_progress.reset()
    yield
    catalog_progress.reset()


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


def test_registry_ignores_stale_updates_and_expires(monkeypatch):
    now = 10.0
    monkeypatch.setattr(catalog_progress, "_clock", lambda: now)
    operation_id = catalog_progress.start("fetch", source="openngc")
    assert not catalog_progress.update(
        "older",
        catalog_progress.ProgressUpdate("downloading", "wrong", 10, 20),
    )
    assert catalog_progress.update(
        operation_id,
        catalog_progress.ProgressUpdate("downloading", "Downloading…", 10, 20),
    )
    now = 13.5
    active = catalog_progress.snapshot()
    assert active is not None
    assert active["phase_elapsed_s"] == 3.5
    assert active["bytes_received"] == 10

    assert catalog_progress.finish(
        operation_id,
        outcome="success",
        message="OpenNGC loaded.",
    )
    assert not catalog_progress.update(
        operation_id,
        catalog_progress.ProgressUpdate("saving", "late"),
    )
    now += 299.9
    assert catalog_progress.snapshot()["outcome"] == "success"
    now += 0.1
    assert catalog_progress.snapshot() is None


@pytest.mark.asyncio
async def test_status_endpoint_answers_during_transfer_and_all_second_actions_conflict(
    client, monkeypatch
):
    from nightcrate.catalog_loader import remote

    monkeypatch.setattr(
        "nightcrate.api.admin.load_config",
        lambda: SimpleNamespace(db_configured=True),
    )
    entered = asyncio.Event()
    release = asyncio.Event()

    async def gated_fetch(_on_progress=None):
        entered.set()
        await asyncio.wait_for(release.wait(), timeout=2)
        raise RuntimeError("stop after gate")

    monkeypatch.setattr(remote, "fetch_latest_release", gated_fetch)
    running = asyncio.create_task(client.post("/api/admin/catalogs/fetch-from-github"))
    await asyncio.wait_for(entered.wait(), timeout=1)

    status = await asyncio.wait_for(client.get("/api/admin/catalogs/fetch-status"), timeout=1)
    assert status.status_code == 200
    assert status.json()["outcome"] is None

    second_actions = [
        "/api/admin/catalogs/fetch-from-github",
        "/api/admin/catalogs/optional/sharpless/add",
        "/api/admin/catalogs/50mgc/fetch",
        "/api/admin/catalogs/wikidata/fetch",
        "/api/admin/catalogs/reload",
        "/api/admin/catalogs/nightcrate/reload",
    ]
    for path in second_actions:
        response = await client.post(path)
        assert response.status_code == 409, path
        assert response.json()["detail"] == "Another catalog update is running."

    release.set()
    assert (await running).status_code == 502
    assert (await client.get("/api/admin/catalogs/fetch-status")).json()["outcome"] == "failed"


@pytest.mark.asyncio
async def test_refused_requests_do_not_reserve_slot(client, monkeypatch):
    monkeypatch.setattr(
        "nightcrate.api.admin.load_config",
        lambda: SimpleNamespace(db_configured=False),
    )
    response = await client.post("/api/admin/catalogs/fetch-from-github")
    assert response.status_code == 400
    assert catalog_progress.snapshot() is None

    response = await client.post("/api/admin/catalogs/optional/not-a-source/add")
    assert response.status_code == 404
    assert catalog_progress.snapshot() is None


@pytest.mark.asyncio
async def test_status_endpoint_has_no_database_dependency(client, monkeypatch):
    monkeypatch.setattr(
        "nightcrate.api.admin.load_config",
        lambda: (_ for _ in ()).throw(AssertionError("database/config access")),
    )
    operation_id = catalog_progress.start("test")
    response = await client.get("/api/admin/catalogs/fetch-status")
    assert response.status_code == 200
    assert response.json()["operation_id"] == operation_id


@pytest.mark.asyncio
async def test_request_cancellation_finishes_and_releases_guard(client, monkeypatch):
    from nightcrate.catalog_loader import remote

    monkeypatch.setattr(
        "nightcrate.api.admin.load_config",
        lambda: SimpleNamespace(db_configured=True),
    )
    entered = asyncio.Event()

    async def gated_fetch(_on_progress=None):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(remote, "fetch_latest_release", gated_fetch)
    running = asyncio.create_task(client.post("/api/admin/catalogs/fetch-from-github"))
    await asyncio.wait_for(entered.wait(), timeout=1)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running

    retained = catalog_progress.snapshot()
    assert retained is not None
    assert retained["outcome"] == "failed"
    assert retained["detail"] == "Request cancelled."
    replacement = catalog_progress.start("replacement")
    assert replacement != retained["operation_id"]


@pytest.mark.asyncio
async def test_every_action_completes_with_targeted_success(client, monkeypatch, tmp_path):
    from nightcrate.catalog_loader import mgc50_fetch, remote, vizier, wikidata

    monkeypatch.setattr(
        "nightcrate.api.admin.load_config",
        lambda: SimpleNamespace(db_configured=True),
    )
    results = [
        SourceResult("openngc", "loaded"),
        SourceResult("openngc_addendum", "unchanged"),
        SourceResult("vizier_sharpless", "loaded"),
        SourceResult("vizier_barnard", "unchanged"),
        SourceResult("github_50mgc", "loaded"),
        SourceResult("wikidata_external_refs", "loaded"),
        SourceResult("nightcrate_augment", "loaded"),
    ]
    monkeypatch.setattr(
        "nightcrate.api.admin._run_loader",
        lambda force: LoadSummary(results=results),
    )

    async def latest(_progress=None):
        return remote.RemoteReleaseInfo("v-test", None, "https://example.test")

    async def openngc_download(_release, _root, _progress=None):
        return remote.DownloadReport("v-test", [], tmp_path / "version.json")

    async def vizier_download(specs, _root, _progress=None, *, catalog_id=None):
        assert catalog_id in {"sharpless", "barnard"}
        return [
            vizier.VizierFetchResult(
                spec.source_id,
                tmp_path / spec.output_filename,
                "hash",
                10,
                "2026-11-01",
                "https://example.test",
            )
            for spec in specs
        ]

    async def mgc_download(_root, _progress=None):
        return mgc50_fetch.Mgc50FetchResult(tmp_path / "50.fits", "hash", 10, "2026-11-01")

    async def wikidata_download(_root, *, app_version, on_progress=None):
        return wikidata.WikidataFetchResult(tmp_path / "wiki.tsv", "hash", 10, "2026-11-01", "v3")

    monkeypatch.setattr(remote, "fetch_latest_release", latest)
    monkeypatch.setattr(remote, "download_openngc", openngc_download)
    monkeypatch.setattr(vizier, "fetch_vizier_tables", vizier_download)
    monkeypatch.setattr(mgc50_fetch, "fetch_50mgc_from_github", mgc_download)
    monkeypatch.setattr(wikidata, "fetch_wikidata_external_refs", wikidata_download)

    paths = [
        "/api/admin/catalogs/fetch-from-github",
        "/api/admin/catalogs/optional/sharpless/add",
        "/api/admin/catalogs/optional/barnard/add",
        "/api/admin/catalogs/50mgc/fetch",
        "/api/admin/catalogs/wikidata/fetch",
        "/api/admin/catalogs/reload",
        "/api/admin/catalogs/nightcrate/reload",
    ]
    for path in paths:
        response = await client.post(path)
        assert response.status_code == 200, (path, response.text)
        retained = (await client.get("/api/admin/catalogs/fetch-status")).json()
        assert retained["outcome"] == "success", path


@pytest.mark.parametrize(
    ("result", "expected_outcome", "expected_message"),
    [
        (SourceResult("target", "unchanged"), "success", "Target loaded."),
        (
            SourceResult("target", "failed", error="database error"),
            "failed",
            "Download saved; database update failed.",
        ),
        (
            SourceResult("target", "missing", error="file missing"),
            "warning",
            "Update finished with warnings. See details below.",
        ),
        (
            SourceResult("target", "skipped", error="object step deferred"),
            "warning",
            "Update finished with warnings. See details below.",
        ),
    ],
)
def test_loader_results_choose_terminal_outcome(result, expected_outcome, expected_message):
    from nightcrate.api.admin import _CatalogAction

    with _CatalogAction("test", source="target") as action:
        action.loading()
        action.complete(LoadSummary(results=[result]), {"target"}, "Target")

    retained = catalog_progress.snapshot()
    assert retained["outcome"] == expected_outcome
    assert retained["message"] == expected_message


@pytest.mark.parametrize(
    ("result", "expected_outcome", "expected_detail"),
    [
        (SourceResult("github_50mgc", "missing", error="file missing"), "success", None),
        (
            SourceResult("github_50mgc", "skipped", error="object step deferred"),
            "warning",
            "50 MGC: object step deferred",
        ),
        (
            SourceResult("github_50mgc", "failed", error="database error"),
            "failed",
            "50 MGC: database error",
        ),
    ],
)
def test_reload_ignores_only_missing_results(result, expected_outcome, expected_detail):
    from nightcrate.api.admin import _CatalogAction

    with _CatalogAction("reload_all", reload=True) as action:
        action.complete(LoadSummary(results=[result]), {"github_50mgc"}, "Cached catalogs")

    retained = catalog_progress.snapshot()
    assert retained["outcome"] == expected_outcome
    assert retained["detail"] == expected_detail


def test_fetch_missing_result_uses_a_display_name_and_plain_language():
    from nightcrate.api.admin import _CatalogAction

    with _CatalogAction("fetch", source="github_50mgc") as action:
        action.complete(
            LoadSummary(
                results=[
                    SourceResult("github_50mgc", "missing", error="file not found: /private/path")
                ]
            ),
            {"github_50mgc"},
            "50 MGC",
        )

    retained = catalog_progress.snapshot()
    assert retained["outcome"] == "warning"
    assert retained["detail"] == "50 MGC: not downloaded yet"


def test_catalog_result_details_use_display_names():
    from nightcrate.api.admin import _catalog_source_name

    assert {
        source_id: _catalog_source_name(source_id)
        for source_id in (
            "openngc",
            "openngc_addendum",
            "vizier_sharpless",
            "vizier_barnard",
            "github_50mgc",
            "wikidata_external_refs",
            "nightcrate_augment",
            "nightcrate_sharpless_crossref",
            "nightcrate_barnard_crossref",
            "nightcrate_external_refs",
        )
    } == {
        "openngc": "OpenNGC",
        "openngc_addendum": "OpenNGC addendum",
        "vizier_sharpless": "Sharpless 2",
        "vizier_barnard": "Barnard",
        "github_50mgc": "50 MGC",
        "wikidata_external_refs": "Wikidata",
        "nightcrate_augment": "NightCrate object data",
        "nightcrate_sharpless_crossref": "NightCrate Sharpless cross-references",
        "nightcrate_barnard_crossref": "NightCrate Barnard cross-references",
        "nightcrate_external_refs": "NightCrate external references",
    }
