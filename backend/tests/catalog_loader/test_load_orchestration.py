"""Persisted invalidation and missing-file orchestration regressions."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from nightcrate.catalog_loader import load_catalogs
from nightcrate.catalog_loader.loader import SourceResult

FIXTURES = Path(__file__).parent.parent / "fixtures" / "catalogs"


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "test.db")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@pytest.fixture
def catalogs_root(tmp_path: Path) -> Path:
    root = tmp_path / "catalogs"
    openngc = root / "openngc"
    openngc.mkdir(parents=True)
    shutil.copy(FIXTURES / "openngc" / "mini_NGC.csv", openngc / "NGC.csv")
    shutil.copy(FIXTURES / "openngc" / "mini_addendum.csv", openngc / "addendum.csv")
    shutil.copy(FIXTURES / "openngc" / "version.json", openngc / "version.json")
    return root


def _rows(db: sqlite3.Connection, table: str) -> list[tuple]:
    """Snapshot stable values; load-trigger timestamps are not catalog facts."""
    rows = db.execute(f'SELECT * FROM "{table}" ORDER BY id')  # nosec B608
    return [
        tuple(value for key, value in zip(row.keys(), row, strict=True) if key != "updated_at")
        for row in rows
    ]


def test_keys_assigned_stops_repeat(db, catalogs_root, monkeypatch):
    load_catalogs(db, catalogs_root)
    source_id = db.execute(
        "SELECT id FROM dso_catalog_source WHERE source_id='openngc'"
    ).fetchone()[0]
    db.execute(
        """
        INSERT INTO dso
            (primary_designation, obj_type, source_catalog_id, source_row_hash)
        VALUES ('Legacy unmatched', 'Other', ?, 'legacy')
        """,
        (source_id,),
    )
    db.commit()

    def unexpected(*_args, **_kwargs):
        raise AssertionError("object step repeated")

    monkeypatch.setattr("nightcrate.catalog_loader.reconcile.apply_object_set", unexpected)
    load_catalogs(db, catalogs_root)


def test_missing_loaded_source_defers_object_step(db, catalogs_root):
    vizier = catalogs_root / "vizier"
    vizier.mkdir()
    barnard = vizier / "barnard_VII_220.tsv"
    shutil.copy(FIXTURES / "vizier" / "mini_barnard.tsv", barnard)
    load_catalogs(db, catalogs_root)
    before = {table: _rows(db, table) for table in ("dso", "dso_designation")}
    barnard.unlink()
    with (catalogs_root / "openngc" / "NGC.csv").open("a", encoding="utf-8") as stream:
        stream.write("\n")

    summary = load_catalogs(db, catalogs_root)

    assert {table: _rows(db, table) for table in before} == before
    result = next(row for row in summary.results if row.source_id == "vizier_barnard")
    assert result.status == "skipped"
    assert "barnard_VII_220.tsv" in (result.error or "")


def test_deferred_object_step_still_applies_wikidata_change(db, catalogs_root):
    vizier = catalogs_root / "vizier"
    wikidata = catalogs_root / "wikidata"
    vizier.mkdir()
    wikidata.mkdir()
    barnard = vizier / "barnard_VII_220.tsv"
    wikidata_file = wikidata / "dso_external_refs.tsv"
    shutil.copy(FIXTURES / "vizier" / "mini_barnard.tsv", barnard)
    shutil.copy(FIXTURES / "wikidata" / "mini_wikidata.tsv", wikidata_file)
    load_catalogs(db, catalogs_root)
    before = {table: _rows(db, table) for table in ("dso", "dso_designation")}
    barnard.unlink()
    wikidata_file.write_text(
        wikidata_file.read_text(encoding="utf-8").replace(
            '"Andromeda Galaxy"@en', '"Changed Andromeda"@en'
        ),
        encoding="utf-8",
    )

    summary = load_catalogs(db, catalogs_root)

    assert {table: _rows(db, table) for table in before} == before
    assert all(
        result.status == "skipped"
        for result in summary.results
        if result.source_id in {"openngc", "openngc_addendum", "vizier_sharpless", "vizier_barnard"}
    )
    wikidata_result = next(
        result for result in summary.results if result.source_id == "wikidata_external_refs"
    )
    assert wikidata_result.status == "loaded"
    assert (
        db.execute(
            "SELECT label FROM dso_external_ref "
            "WHERE provider='wikidata' AND identifier='Q2469' LIMIT 1"
        ).fetchone()[0]
        == "Changed Andromeda"
    )


def test_changed_augment_waits_for_deferred_object_step(db, catalogs_root):
    vizier = catalogs_root / "vizier"
    wikidata = catalogs_root / "wikidata"
    vizier.mkdir()
    wikidata.mkdir()
    barnard = vizier / "barnard_VII_220.tsv"
    wikidata_file = wikidata / "dso_external_refs.tsv"
    shutil.copy(FIXTURES / "vizier" / "mini_barnard.tsv", barnard)
    shutil.copy(FIXTURES / "wikidata" / "mini_wikidata.tsv", wikidata_file)
    load_catalogs(db, catalogs_root)
    db.execute(
        """
        UPDATE dso
        SET common_name='Sentinel', common_name_augmented=1
        WHERE primary_designation='M 42'
        """
    )
    db.execute(
        "UPDATE dso_catalog_source SET file_hash='old-augment' WHERE source_id='nightcrate_augment'"
    )
    db.commit()
    barnard.unlink()
    wikidata_file.write_text(
        wikidata_file.read_text(encoding="utf-8").replace(
            '"Andromeda Galaxy"@en', '"Changed Andromeda"@en'
        ),
        encoding="utf-8",
    )

    deferred = load_catalogs(db, catalogs_root)

    assert (
        next(result for result in deferred.results if result.source_id == "vizier_barnard").status
        == "skipped"
    )
    assert (
        db.execute(
            "SELECT file_hash FROM dso_catalog_source WHERE source_id='nightcrate_augment'"
        ).fetchone()[0]
        == "old-augment"
    )
    assert tuple(
        db.execute(
            "SELECT common_name, common_name_augmented FROM dso WHERE primary_designation='M 42'"
        ).fetchone()
    ) == ("Sentinel", 1)
    assert (
        db.execute(
            "SELECT label FROM dso_external_ref "
            "WHERE provider='wikidata' AND identifier='Q2469' LIMIT 1"
        ).fetchone()[0]
        == "Changed Andromeda"
    )

    shutil.copy(FIXTURES / "vizier" / "mini_barnard.tsv", barnard)
    resumed = load_catalogs(db, catalogs_root)

    assert next(result for result in resumed.results if result.source_id == "openngc").status == (
        "loaded"
    )
    assert (
        next(
            result for result in resumed.results if result.source_id == "nightcrate_augment"
        ).status
        == "loaded"
    )
    assert (
        db.execute(
            "SELECT file_hash FROM dso_catalog_source WHERE source_id='nightcrate_augment'"
        ).fetchone()[0]
        != "old-augment"
    )
    assert tuple(
        db.execute(
            "SELECT common_name, common_name_augmented FROM dso WHERE primary_designation='M 42'"
        ).fetchone()
    ) == ("Orion Nebula", 1)


def test_object_step_failure_does_not_escape_and_enrichment_continues(db, catalogs_root):
    vizier = catalogs_root / "vizier"
    wikidata = catalogs_root / "wikidata"
    vizier.mkdir()
    wikidata.mkdir()
    barnard = vizier / "barnard_VII_220.tsv"
    wikidata_file = wikidata / "dso_external_refs.tsv"
    shutil.copy(FIXTURES / "vizier" / "mini_barnard.tsv", barnard)
    shutil.copy(FIXTURES / "wikidata" / "mini_wikidata.tsv", wikidata_file)
    load_catalogs(db, catalogs_root)
    before = {table: _rows(db, table) for table in ("dso", "dso_designation")}
    barnard.write_text("broken\n", encoding="utf-8")
    wikidata_file.write_text(
        wikidata_file.read_text(encoding="utf-8").replace(
            '"Andromeda Galaxy"@en', '"Changed Andromeda"@en'
        ),
        encoding="utf-8",
    )

    summary = load_catalogs(db, catalogs_root)

    assert {table: _rows(db, table) for table in before} == before
    object_results = [
        result
        for result in summary.results
        if result.source_id in {"openngc", "openngc_addendum", "vizier_sharpless", "vizier_barnard"}
    ]
    assert all(result.status == "failed" for result in object_results)
    assert all("missing units row" in (result.error or "") for result in object_results)
    assert (
        next(
            result for result in summary.results if result.source_id == "wikidata_external_refs"
        ).status
        == "loaded"
    )
    assert (
        db.execute(
            "SELECT label FROM dso_external_ref "
            "WHERE provider='wikidata' AND identifier='Q2469' LIMIT 1"
        ).fetchone()[0]
        == "Changed Andromeda"
    )


def test_never_loaded_missing_source_never_blocks(db, catalogs_root):
    load_catalogs(db, catalogs_root)
    before = db.execute("SELECT id FROM dso ORDER BY id").fetchall()
    with (catalogs_root / "openngc" / "NGC.csv").open("a", encoding="utf-8") as stream:
        stream.write("\n")
    summary = load_catalogs(db, catalogs_root)
    after = db.execute("SELECT id FROM dso ORDER BY id").fetchall()
    assert [row[0] for row in after] == [row[0] for row in before]
    assert next(row for row in summary.results if row.source_id == "openngc").status == "loaded"


def test_invalidated_augment_does_not_run_object_step(db, catalogs_root, monkeypatch):
    load_catalogs(db, catalogs_root)
    db.execute("UPDATE dso_catalog_source SET file_hash='' WHERE source_id='nightcrate_augment'")
    db.commit()

    def unexpected(*_args, **_kwargs):
        raise AssertionError("invalidated augment triggered object step")

    monkeypatch.setattr("nightcrate.catalog_loader.reconcile.apply_object_set", unexpected)
    summary = load_catalogs(db, catalogs_root)
    assert (
        next(row for row in summary.results if row.source_id == "nightcrate_augment").status
        == "loaded"
    )


def test_augment_change_runs_object_step(db, catalogs_root, monkeypatch):
    from nightcrate.catalog_loader import reconcile

    load_catalogs(db, catalogs_root)
    db.execute(
        "UPDATE dso_catalog_source SET file_hash='stale-nonempty' "
        "WHERE source_id='nightcrate_augment'"
    )
    db.commit()
    real_apply = reconcile.apply_object_set
    calls = 0

    def recording_apply(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real_apply(*args, **kwargs)

    monkeypatch.setattr(reconcile, "apply_object_set", recording_apply)
    summary = load_catalogs(db, catalogs_root)
    assert calls == 1
    assert next(row for row in summary.results if row.source_id == "openngc").status == "loaded"


def test_failed_enrichment_reruns_next_load(db, catalogs_root, monkeypatch):
    from nightcrate.catalog_loader import external_refs_loader

    real_loader = external_refs_loader.load_external_refs
    calls = 0

    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return SourceResult("nightcrate_external_refs", "failed", error="injected")
        return real_loader(*args, **kwargs)

    monkeypatch.setattr(external_refs_loader, "load_external_refs", fail_once)
    first = load_catalogs(db, catalogs_root)
    assert (
        next(row for row in first.results if row.source_id == "nightcrate_external_refs").status
        == "failed"
    )
    second = load_catalogs(db, catalogs_root)
    assert calls == 2
    assert (
        next(row for row in second.results if row.source_id == "nightcrate_external_refs").status
        == "loaded"
    )


def test_raised_enrichment_reruns_next_load(db, catalogs_root, monkeypatch):
    from nightcrate.catalog_loader import external_refs_loader

    real_loader = external_refs_loader.load_external_refs
    calls = 0

    def raise_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("injected")
        return real_loader(*args, **kwargs)

    monkeypatch.setattr(external_refs_loader, "load_external_refs", raise_once)
    with pytest.raises(RuntimeError, match="injected"):
        load_catalogs(db, catalogs_root)
    second = load_catalogs(db, catalogs_root)
    assert calls == 2
    assert (
        next(row for row in second.results if row.source_id == "nightcrate_external_refs").status
        == "loaded"
    )


def test_exception_after_object_commit_defers_augment_until_retry(db, catalogs_root, monkeypatch):
    from nightcrate.catalog_loader import reconcile

    real_apply = reconcile.apply_object_set

    def commit_then_interrupt(*args, **kwargs):
        real_apply(*args, **kwargs)
        raise RuntimeError("interrupted")

    monkeypatch.setattr(reconcile, "apply_object_set", commit_then_interrupt)
    first = load_catalogs(db, catalogs_root)
    assert next(row for row in first.results if row.source_id == "openngc").status == "failed"
    assert (
        next(row for row in first.results if row.source_id == "nightcrate_augment").status
        == "skipped"
    )
    monkeypatch.setattr(reconcile, "apply_object_set", real_apply)

    summary = load_catalogs(db, catalogs_root)

    assert next(row for row in summary.results if row.source_id == "openngc").status == "unchanged"
    assert (
        next(row for row in summary.results if row.source_id == "nightcrate_augment").status
        == "loaded"
    )


def test_barnard_change_runs_object_step_and_all_enrichment(db, catalogs_root, monkeypatch):
    from nightcrate.catalog_loader import loader

    vizier = catalogs_root / "vizier"
    vizier.mkdir()
    barnard = vizier / "barnard_VII_220.tsv"
    shutil.copy(FIXTURES / "vizier" / "mini_barnard.tsv", barnard)
    load_catalogs(db, catalogs_root)
    with barnard.open("a", encoding="utf-8") as stream:
        stream.write("\n")
    real_dispatch = loader._dispatch_source
    called: list[str] = []

    def recording_dispatch(conn, source, crossref_path, *, force):
        called.append(source.source_id)
        return real_dispatch(conn, source, crossref_path, force=force)

    monkeypatch.setattr(loader, "_dispatch_source", recording_dispatch)
    summary = load_catalogs(db, catalogs_root)
    assert (
        next(row for row in summary.results if row.source_id == "vizier_barnard").status == "loaded"
    )
    assert called == [
        "nightcrate_augment",
        "github_50mgc",
        "wikidata_external_refs",
        "nightcrate_external_refs",
    ]


def test_wikidata_change_runs_only_wikidata_and_later(db, catalogs_root, monkeypatch):
    from nightcrate.catalog_loader import loader

    wikidata_dir = catalogs_root / "wikidata"
    wikidata_dir.mkdir()
    wikidata_file = wikidata_dir / "dso_external_refs.tsv"
    shutil.copy(FIXTURES / "wikidata" / "mini_wikidata.tsv", wikidata_file)
    load_catalogs(db, catalogs_root)
    with wikidata_file.open("a", encoding="utf-8") as stream:
        stream.write("\n")
    real_dispatch = loader._dispatch_source
    called: list[str] = []

    def recording_dispatch(conn, source, crossref_path, *, force):
        called.append(source.source_id)
        return real_dispatch(conn, source, crossref_path, force=force)

    monkeypatch.setattr(loader, "_dispatch_source", recording_dispatch)
    summary = load_catalogs(db, catalogs_root)
    assert called == ["wikidata_external_refs", "nightcrate_external_refs"]
    assert (
        next(row for row in summary.results if row.source_id == "nightcrate_augment").status
        == "unchanged"
    )


def test_nothing_changed_runs_only_redshift(db, catalogs_root, monkeypatch):
    from nightcrate.catalog_loader import loader, redshift_distance

    load_catalogs(db, catalogs_root)
    real_redshift = redshift_distance.apply_redshift_distances
    redshift_calls = 0

    def unexpected_dispatch(*_args, **_kwargs):
        raise AssertionError("an enrichment loader ran")

    def recording_redshift(conn):
        nonlocal redshift_calls
        redshift_calls += 1
        return real_redshift(conn)

    monkeypatch.setattr(loader, "_dispatch_source", unexpected_dispatch)
    monkeypatch.setattr(redshift_distance, "apply_redshift_distances", recording_redshift)
    load_catalogs(db, catalogs_root)
    assert redshift_calls == 1


def test_all_merged_sharpless_missing_blocks(db, catalogs_root):
    vizier = catalogs_root / "vizier"
    vizier.mkdir()
    sharpless = vizier / "sharpless_VII_20.tsv"
    sharpless.write_text(
        "_RAJ2000\t_DEJ2000\tSh2\tDiam\tClass\n"
        "deg\tdeg\t--\tarcmin\t--\n"
        "--------\t--------\t---\t------\t-----\n"
        "83.8221\t-5.3911\t281\t85\t3\n",
        encoding="utf-8",
    )
    load_catalogs(db, catalogs_root)
    assert (
        db.execute(
            "SELECT row_count FROM dso_catalog_source WHERE source_id='vizier_sharpless'"
        ).fetchone()[0]
        == 0
    )
    before = {table: _rows(db, table) for table in ("dso", "dso_designation")}
    sharpless.unlink()
    with (catalogs_root / "openngc" / "NGC.csv").open("a", encoding="utf-8") as stream:
        stream.write("\n")

    summary = load_catalogs(db, catalogs_root)

    assert {table: _rows(db, table) for table in before} == before
    result = next(row for row in summary.results if row.source_id == "vizier_sharpless")
    assert result.status == "skipped"
    assert "sharpless_VII_20.tsv" in (result.error or "")


def test_reactivated_object_loses_dropped_curated_distance(db, catalogs_root):
    ngc_path = catalogs_root / "openngc" / "NGC.csv"
    original = ngc_path.read_text(encoding="utf-8")
    load_catalogs(db, catalogs_root)
    db.execute(
        "UPDATE dso SET distance_pc=123, distance_method='curated' WHERE primary_designation='M 31'"
    )
    db.commit()
    ngc_path.write_text(
        "\n".join(line for line in original.splitlines() if not line.startswith("NGC0224;")) + "\n",
        encoding="utf-8",
    )
    load_catalogs(db, catalogs_root)
    assert tuple(
        db.execute(
            "SELECT active, distance_pc, distance_method FROM dso WHERE primary_designation='M 31'"
        ).fetchone()
    ) == (0, 123.0, "curated")

    ngc_path.write_text(original, encoding="utf-8")
    load_catalogs(db, catalogs_root)

    row = db.execute(
        "SELECT active, distance_method FROM dso WHERE primary_designation='M 31'"
    ).fetchone()
    assert row[0] == 1
    assert row[1] != "curated"
