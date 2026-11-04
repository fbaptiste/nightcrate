"""Admin API coverage for app-wide optional catalog choices."""

from __future__ import annotations

import json
import shutil
import sqlite3
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.catalog_loader import load_catalogs, registry, vizier
from nightcrate.catalog_loader.catalog_choice import CatalogChoice, read_choice, write_choice
from nightcrate.catalog_loader.hash import file_sha256
from nightcrate.db.session import get_db_path
from nightcrate.main import app
from nightcrate.services import catalog_progress

FIXTURES = Path(__file__).parent / "fixtures" / "catalogs"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


@pytest.fixture
def catalogs_root(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "catalogs"
    (root / "openngc").mkdir(parents=True)
    (root / "vizier").mkdir()
    shutil.copy(FIXTURES / "openngc" / "mini_NGC.csv", root / "openngc" / "NGC.csv")
    shutil.copy(FIXTURES / "openngc" / "mini_addendum.csv", root / "openngc" / "addendum.csv")
    shutil.copy(
        FIXTURES / "vizier" / "mini_sharpless.tsv",
        root / "vizier" / "sharpless_VII_20.tsv",
    )
    shutil.copy(
        FIXTURES / "vizier" / "mini_barnard.tsv",
        root / "vizier" / "barnard_VII_220.tsv",
    )
    monkeypatch.setattr(
        "nightcrate.api.admin.load_config", lambda: SimpleNamespace(db_configured=True)
    )
    with sqlite3.connect(get_db_path()) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        load_catalogs(conn, root)
    return root


@pytest.fixture(autouse=True)
def _reset_progress():
    catalog_progress.reset()
    yield
    catalog_progress.reset()


@pytest.mark.anyio
async def test_list_order_and_states_before_and_after_remove_and_add(
    client, catalogs_root, monkeypatch
):
    response = await client.get("/api/admin/catalogs/optional")
    assert response.status_code == 200
    before = response.json()
    assert [item["catalog_id"] for item in before] == [
        catalog.catalog_id for catalog in registry.OPTIONAL_CATALOGS
    ]
    before_by_id = {item["catalog_id"]: item for item in before}
    for catalog_id in ("sharpless", "barnard"):
        assert before_by_id[catalog_id]["state"] == "on"
        assert before_by_id[catalog_id]["installed"] is True
        assert before_by_id[catalog_id]["object_count"] > 0
    for catalog in registry.OPTIONAL_CATALOGS:
        if catalog.catalog_id in {"sharpless", "barnard"}:
            continue
        assert before_by_id[catalog.catalog_id]["state"] == "off"
        assert before_by_id[catalog.catalog_id]["installed"] is (catalog.kind == "nightcrate")
        assert before_by_id[catalog.catalog_id]["object_count"] == 0

    removed = await client.post("/api/admin/catalogs/optional/barnard/remove")
    assert removed.status_code == 200
    after_remove = (await client.get("/api/admin/catalogs/optional")).json()
    assert after_remove[1]["state"] == "removed"
    assert after_remove[1]["installed"] is False
    assert after_remove[1]["object_count"] == 0

    async def restore(specs, root, _progress=None, *, catalog_id=None):
        assert catalog_id == "barnard"
        destination = root / "vizier" / specs[0].output_filename
        shutil.copy(FIXTURES / "vizier" / "mini_barnard.tsv", destination)
        content = destination.read_bytes()
        return [
            vizier.VizierFetchResult(
                specs[0].source_id,
                destination,
                "fixture-hash",
                len(content),
                "2026-11-02T12:00:00+00:00",
                "https://example.test",
            )
        ]

    monkeypatch.setattr(vizier, "fetch_vizier_tables", restore)
    added = await client.post("/api/admin/catalogs/optional/barnard/add")
    assert added.status_code == 200
    after_add = (await client.get("/api/admin/catalogs/optional")).json()
    assert after_add[1]["state"] == "on"
    assert after_add[1]["object_count"] == before[1]["object_count"]


@pytest.mark.anyio
async def test_list_hides_only_unapplied_missing_legacy_defaults(client, monkeypatch):
    monkeypatch.setattr(
        "nightcrate.api.admin.load_config", lambda: SimpleNamespace(db_configured=True)
    )

    fresh = (await client.get("/api/admin/catalogs/optional")).json()
    fresh_by_id = {item["catalog_id"]: item for item in fresh}
    assert fresh_by_id["sharpless"]["state"] == "off"
    assert fresh_by_id["barnard"]["state"] == "off"

    with sqlite3.connect(get_db_path()) as conn:
        conn.execute(
            "INSERT INTO dso_catalog_applied (catalog_id, state) VALUES ('sharpless', 'on')"
        )
        conn.commit()
    applied = (await client.get("/api/admin/catalogs/optional")).json()
    applied_sharpless = next(item for item in applied if item["catalog_id"] == "sharpless")
    assert applied_sharpless["state"] == "on"
    assert applied_sharpless["installed"] is False

    with sqlite3.connect(get_db_path()) as conn:
        conn.execute("DELETE FROM dso_catalog_applied WHERE catalog_id='sharpless'")
        conn.commit()
    write_choice(
        registry.user_catalogs_root(),
        CatalogChoice(frozenset({"barnard"}), frozenset()),
    )
    chosen = (await client.get("/api/admin/catalogs/optional")).json()
    chosen_barnard = next(item for item in chosen if item["catalog_id"] == "barnard")
    assert chosen_barnard["state"] == "on"
    assert chosen_barnard["installed"] is False


@pytest.mark.anyio
async def test_list_and_removal_preview_require_configured_database(
    client,
    tmp_path: Path,
    monkeypatch,
):
    unconfigured_path = tmp_path / "must-not-be-created.db"
    monkeypatch.setattr(
        "nightcrate.api.admin.load_config", lambda: SimpleNamespace(db_configured=False)
    )
    monkeypatch.setattr("nightcrate.api.admin.get_db_path", lambda: unconfigured_path)

    listing = await client.get("/api/admin/catalogs/optional")
    preview = await client.get("/api/admin/catalogs/optional/barnard/removal-preview")

    assert listing.status_code == 400
    assert preview.status_code == 400
    assert not unconfigured_path.exists()


@pytest.mark.anyio
async def test_list_counts_each_hash_catalog_by_its_own_active_entries(client, catalogs_root):
    hash_path = catalogs_root / "vizier" / "hash_V_163_pnmain.tsv"
    shutil.copy(FIXTURES / "vizier" / "mini_hash.tsv", hash_path)
    (catalogs_root / "vizier" / "version.json").write_text(
        json.dumps(
            {
                "files": {
                    hash_path.name: {
                        "sha256": file_sha256(hash_path),
                        "fetch_date": "2026-11-02T00:00:00+00:00",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    write_choice(
        catalogs_root,
        CatalogChoice(frozenset({"sharpless", "barnard", "png", "abell_pn"}), frozenset()),
    )
    with sqlite3.connect(get_db_path()) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        load_catalogs(conn, catalogs_root)
        entry_ids = {"png": set(), "abell_pn": set()}
        for catalog_id, dso_id in conn.execute(
            """
            SELECT e.catalog_id, e.dso_id
            FROM dso_source_entry e
            JOIN dso d ON d.id = e.dso_id
            WHERE d.active = 1 AND e.catalog_id IN ('png', 'abell_pn')
            """
        ):
            entry_ids[str(catalog_id)].add(int(dso_id))

    response = await client.get("/api/admin/catalogs/optional")

    assert response.status_code == 200
    by_id = {item["catalog_id"]: item for item in response.json()}
    assert len(entry_ids["png"]) != len(entry_ids["abell_pn"])
    assert by_id["png"]["object_count"] == len(entry_ids["png"])
    assert by_id["abell_pn"]["object_count"] == len(entry_ids["abell_pn"])


@pytest.mark.anyio
async def test_list_counts_sharpless_entries_merged_into_other_sources(client, catalogs_root):
    with sqlite3.connect(get_db_path()) as conn:
        entry_ids = {
            int(row[0])
            for row in conn.execute(
                """
                SELECT e.dso_id
                FROM dso_source_entry e
                JOIN dso d ON d.id = e.dso_id
                WHERE d.active = 1 AND e.catalog_id = 'sharpless'
                """
            )
        }
        owned_ids = {
            int(row[0])
            for row in conn.execute(
                """
                SELECT d.id
                FROM dso d
                JOIN dso_catalog_source s ON s.id = d.source_catalog_id
                WHERE d.active = 1 AND s.source_id = 'vizier_sharpless'
                """
            )
        }

    response = await client.get("/api/admin/catalogs/optional")

    assert response.status_code == 200
    sharpless = next(item for item in response.json() if item["catalog_id"] == "sharpless")
    assert entry_ids - owned_ids
    assert sharpless["object_count"] == len(entry_ids)


@pytest.mark.anyio
async def test_preview_counts_match_removal_counts(client, catalogs_root):
    with sqlite3.connect(get_db_path()) as conn:
        barnard_id = int(
            conn.execute(
                """
                SELECT d.id FROM dso d
                JOIN dso_catalog_source s ON s.id=d.source_catalog_id
                WHERE s.source_id='vizier_barnard' ORDER BY d.id LIMIT 1
                """
            ).fetchone()[0]
        )
        unrelated_openngc_id = int(
            conn.execute("SELECT id FROM dso WHERE source_key='NGC1234'").fetchone()[0]
        )
        conn.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (barnard_id,))
        conn.commit()

    openngc_path = catalogs_root / "openngc" / "NGC.csv"
    openngc_lines = openngc_path.read_text(encoding="utf-8").splitlines()
    openngc_path.write_text(
        "\n".join(line for line in openngc_lines if not line.startswith("NGC1234;")) + "\n",
        encoding="utf-8",
    )

    preview = await client.get("/api/admin/catalogs/optional/barnard/removal-preview")
    removed = await client.post("/api/admin/catalogs/optional/barnard/remove")

    assert preview.status_code == removed.status_code == 200
    assert preview.json()["blocked_reason"] is None
    assert removed.json()["objects_removed"] == preview.json()["objects_removed"]
    assert removed.json()["objects_kept"] == preview.json()["objects_kept"] == 1
    with sqlite3.connect(get_db_path()) as conn:
        assert (
            conn.execute("SELECT active FROM dso WHERE id=?", (unrelated_openngc_id,)).fetchone()[0]
            == 0
        )


@pytest.mark.anyio
async def test_unknown_catalog_is_404_and_running_action_is_409(client, catalogs_root):
    unknown_preview = await client.get("/api/admin/catalogs/optional/unknown/removal-preview")
    assert unknown_preview.status_code == 404
    assert (await client.post("/api/admin/catalogs/optional/unknown/add")).status_code == 404
    operation_id = catalog_progress.start("test")
    try:
        response = await client.post("/api/admin/catalogs/optional/sharpless/add")
        assert response.status_code == 409
        assert response.json()["detail"] == "Another catalog update is running."
        preview = await client.get("/api/admin/catalogs/optional/sharpless/removal-preview")
        assert preview.status_code == 409
        assert preview.json()["detail"] == "Another catalog update is running."
    finally:
        catalog_progress.finish(operation_id, outcome="success", message="done")


@pytest.mark.anyio
async def test_download_failure_is_502_and_keeps_choice_and_files(
    client, catalogs_root, monkeypatch, caplog
):
    barnard_path = catalogs_root / "vizier" / "barnard_VII_220.tsv"
    before_file = barnard_path.read_bytes()
    before_choice = read_choice(catalogs_root)
    summary = (
        "Strasbourg timed out, Harvard returned an error (HTTP 502) "
        "and South Africa doesn't have this table"
    )
    technical = (
        "All VizieR mirrors failed for vizier_hash: Error from one mirror; "
        "another response was 761 bytes"
    )

    async def fail(*_args, **_kwargs):
        raise vizier.NoVizierSource(technical, summary=summary)

    monkeypatch.setattr(vizier, "fetch_vizier_tables", fail)
    caplog.set_level("WARNING", logger="nightcrate.api.admin")
    response = await client.post("/api/admin/catalogs/optional/barnard/add")
    status = await client.get("/api/admin/catalogs/fetch-status")

    assert response.status_code == 502
    expected_detail = f"Couldn't download Barnard: {summary}."
    assert response.json()["detail"] == expected_detail
    assert status.status_code == 200
    assert status.json()["detail"] == expected_detail
    assert status.json()["message"] == "Download failed: no mirror had a usable copy."
    for internal_text in ("vizier_hash", "Error", "bytes"):
        assert internal_text not in response.json()["detail"]
        assert internal_text not in status.json()["detail"]
    assert technical in caplog.text
    assert barnard_path.read_bytes() == before_file
    assert read_choice(catalogs_root) == before_choice


@pytest.mark.anyio
async def test_preview_and_remove_report_the_same_blocked_reason(client, catalogs_root):
    choice_before = read_choice(catalogs_root)
    barnard_path = catalogs_root / "vizier" / "barnard_VII_220.tsv"
    file_before = barnard_path.read_bytes()
    (catalogs_root / "openngc" / "addendum.csv").unlink()

    preview = await client.get("/api/admin/catalogs/optional/barnard/removal-preview")
    removal = await client.post("/api/admin/catalogs/optional/barnard/remove")

    assert preview.status_code == 200
    assert preview.json()["blocked_reason"] is not None
    assert removal.status_code == 409
    assert removal.json()["detail"] == preview.json()["blocked_reason"]
    assert read_choice(catalogs_root) == choice_before
    assert barnard_path.read_bytes() == file_before


@pytest.mark.anyio
async def test_remove_does_not_apply_a_dry_run(client, catalogs_root, monkeypatch):
    from nightcrate.catalog_loader import reconcile

    original = reconcile.apply_object_set
    dry_run_values: list[bool] = []

    def record_apply(*args, **kwargs):
        dry_run_values.append(bool(kwargs.get("dry_run", False)))
        return original(*args, **kwargs)

    monkeypatch.setattr(reconcile, "apply_object_set", record_apply)

    response = await client.post("/api/admin/catalogs/optional/barnard/remove")

    assert response.status_code == 200
    assert dry_run_values
    assert not any(dry_run_values)


@pytest.mark.anyio
async def test_removed_vizier_routes_are_404(client, catalogs_root):
    assert (
        await client.get("/api/admin/catalogs/vizier/barnard/remote-version")
    ).status_code == 404
    assert (await client.post("/api/admin/catalogs/vizier/barnard/fetch")).status_code == 404


@pytest.mark.anyio
async def test_melotte_add_needs_no_network(client, catalogs_root, monkeypatch):
    melotte = registry.OptionalCatalog(
        "melotte",
        "Melotte",
        (),
        "nightcrate",
        (),
        frozenset({"mel"}),
        False,
        "Melotte 1915. NightCrate reviewed list.",
    )
    monkeypatch.setattr(registry, "OPTIONAL_CATALOGS", (*registry.OPTIONAL_CATALOGS, melotte))

    async def no_network(*_args, **_kwargs):
        raise AssertionError("nightcrate catalog must not fetch")

    monkeypatch.setattr(vizier, "fetch_vizier_tables", no_network)
    response = await client.post("/api/admin/catalogs/optional/melotte/add")

    assert response.status_code == 200
    assert "melotte" in read_choice(catalogs_root).chosen


@pytest.mark.anyio
async def test_choice_write_failure_after_publication_leaves_new_catalog_off(
    client, catalogs_root, monkeypatch
):
    from nightcrate.catalog_loader import catalog_choice

    spec = vizier.VizierFetchSpec("vizier_test_new", "X/new", "new.tsv", "New catalog", "test")
    catalog = registry.OptionalCatalog(
        "new",
        "New catalog",
        (),
        "vizier",
        (spec,),
        frozenset({"wr"}),
        False,
        "test",
    )
    monkeypatch.setattr(registry, "OPTIONAL_CATALOGS", (*registry.OPTIONAL_CATALOGS, catalog))
    published = catalogs_root / "vizier" / "new.tsv"
    old_choice = read_choice(catalogs_root)

    async def publish(specs, _root, _progress=None, *, catalog_id=None):
        assert catalog_id == "new"
        published.write_bytes(b"newly published")
        return [
            vizier.VizierFetchResult(
                specs[0].source_id,
                published,
                "hash",
                published.stat().st_size,
                "2026-11-02T12:00:00+00:00",
                "https://example.test",
            )
        ]

    monkeypatch.setattr(vizier, "fetch_vizier_tables", publish)
    monkeypatch.setattr(
        catalog_choice, "write_choice", lambda *_args: (_ for _ in ()).throw(OSError("disk full"))
    )
    response = await client.post("/api/admin/catalogs/optional/new/add")

    assert response.status_code == 500
    assert published.read_bytes() == b"newly published"
    assert read_choice(catalogs_root) == old_choice
    statuses = (await client.get("/api/admin/catalogs/optional")).json()
    assert next(item for item in statuses if item["catalog_id"] == "new")["state"] == "off"


def test_choice_write_preserves_existing_mode_and_uses_readable_default(tmp_path):
    choice = CatalogChoice(frozenset({"sharpless"}), frozenset())
    path = tmp_path / "choice.json"

    write_choice(tmp_path, choice)
    assert stat.S_IMODE(path.stat().st_mode) == 0o644

    path.chmod(0o640)
    write_choice(tmp_path, choice)
    assert stat.S_IMODE(path.stat().st_mode) == 0o640


def test_publication_marker_defers_applied_database_and_skips_fresh_database(
    catalogs_root, tmp_path
):
    from nightcrate.catalog_loader.loader import prepare_object_step
    from nightcrate.db.migrations import apply_migrations

    marker = catalogs_root / "vizier" / "publishing" / "sharpless.json"
    marker.parent.mkdir()
    marker.write_text('{"version":1,"catalog_id":"sharpless","files":["sharpless_VII_20.tsv"]}')
    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        before = conn.execute("SELECT COUNT(*) FROM dso").fetchone()[0]
        plan = prepare_object_step(conn, catalogs_root, force=False)
        summary = load_catalogs(conn, catalogs_root)
        after = conn.execute("SELECT COUNT(*) FROM dso").fetchone()[0]
    assert plan.deferred_reason is not None
    assert before == after
    sharpless = next(result for result in summary.results if result.source_id == "vizier_sharpless")
    assert sharpless.status == "skipped"

    fresh_path = tmp_path / "fresh.db"
    apply_migrations(fresh_path)
    with sqlite3.connect(fresh_path) as fresh:
        fresh.execute("PRAGMA foreign_keys = ON")
        load_catalogs(fresh, catalogs_root)
        count = fresh.execute(
            """
            SELECT COUNT(*) FROM dso d
            JOIN dso_catalog_source s ON s.id=d.source_catalog_id
            WHERE s.source_id='vizier_sharpless'
            """
        ).fetchone()[0]
    assert count == 0
