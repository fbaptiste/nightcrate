"""HASH planetary-nebula collection, matching, and lifecycle tests."""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.catalog_loader import load_catalogs, registry
from nightcrate.catalog_loader.catalog_choice import (
    CatalogChoice,
    read_choice,
    with_added,
    with_removed,
    write_choice,
)
from nightcrate.catalog_loader.hash import file_sha256
from nightcrate.catalog_loader.hash_loader import _cross_identifications, _notes, collect_hash
from nightcrate.catalog_loader.loader import prepare_object_step
from nightcrate.catalog_loader.reconcile import build_object_set
from nightcrate.catalog_loader.registry import CatalogSource
from nightcrate.catalog_loader.vizier_tsv import parse_vizier_tsv
from nightcrate.db.migrations import apply_migrations
from nightcrate.main import app
from nightcrate.services import catalog_progress

FIXTURES = Path(__file__).parent.parent / "fixtures" / "catalogs"
FULL_SAMPLE = (
    Path(__file__).parents[3]
    / ".superpowers"
    / "codex"
    / "v0.44.0"
    / "samples"
    / "full_V_163_pnmain.tsv"
)
HASH_FILENAME = "hash_V_163_pnmain.tsv"


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "test.db")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


def _catalogs_root(tmp_path: Path, *, installed: bool = False) -> Path:
    root = tmp_path / "catalogs"
    openngc = root / "openngc"
    vizier = root / "vizier"
    openngc.mkdir(parents=True)
    vizier.mkdir()
    shutil.copy(FIXTURES / "openngc" / "mini_NGC.csv", openngc / "NGC.csv")
    shutil.copy(FIXTURES / "openngc" / "mini_addendum.csv", openngc / "addendum.csv")
    shutil.copy(FIXTURES / "openngc" / "version.json", openngc / "version.json")
    shutil.copy(FIXTURES / "vizier" / "mini_hash.tsv", vizier / HASH_FILENAME)
    shutil.copy(
        FIXTURES / "vizier" / "mini_sharpless.tsv",
        vizier / "sharpless_VII_20.tsv",
    )
    if installed:
        catalog_path = vizier / HASH_FILENAME
        version = {
            "files": {
                HASH_FILENAME: {
                    "sha256": file_sha256(catalog_path),
                    "fetch_date": "2026-11-02T00:00:00+00:00",
                }
            }
        }
        (vizier / "version.json").write_text(json.dumps(version), encoding="utf-8")
    return root


def _sources(root: Path) -> dict[str, CatalogSource]:
    return {source.source_id: source for source in registry.get_sources(root)}


def _batch(root: Path, on_catalogs: frozenset[str]):
    source = _sources(root)["vizier_hash"]
    return collect_hash({source.source_id: source}, on_catalogs)


def _fresh_connection(path: Path) -> sqlite3.Connection:
    apply_migrations(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _hash_entry(conn: sqlite3.Connection, source_key: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT d.id, d.primary_designation, d.obj_type, d.openngc_notes, d.active
        FROM dso_source_entry e
        JOIN dso_catalog_source s ON s.id=e.source_catalog_id
        JOIN dso d ON d.id=e.dso_id
        WHERE s.source_id='vizier_hash' AND e.source_key=?
        ORDER BY e.catalog_id
        LIMIT 1
        """,
        (source_key,),
    ).fetchone()


def _hash_entry_catalogs(conn: sqlite3.Connection, source_key: str) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute(
            """
            SELECT e.catalog_id
            FROM dso_source_entry e
            JOIN dso_catalog_source s ON s.id=e.source_catalog_id
            WHERE s.source_id='vizier_hash' AND e.source_key=?
            """,
            (source_key,),
        )
    }


def _designations(conn: sqlite3.Connection, dso_id: int) -> set[tuple[str, str, int]]:
    return {
        (str(row[0]), str(row[1]), int(row[2]))
        for row in conn.execute(
            "SELECT catalog, identifier, is_primary FROM dso_designation WHERE dso_id=?",
            (dso_id,),
        )
    }


def test_hash_registry_shares_one_source_and_uses_readme_credit():
    png = registry.optional_catalog("png")
    abell = registry.optional_catalog("abell_pn")

    assert png is not None and abell is not None
    assert png.display_name == "Planetary nebulae (HASH)"
    assert abell.display_name == "Abell planetary nebulae"
    assert png.source_ids == abell.source_ids == ("vizier_hash",)
    assert png.designation_catalogs == frozenset({"png"})
    assert abell.designation_catalogs == frozenset({"abell"})
    assert png.legacy_default is abell.legacy_default is False
    assert png.fetch_specs[0].output_filename == abell.fetch_specs[0].output_filename
    assert png.fetch_specs[0].required_columns == (
        "HASH",
        "PNG",
        "RAJ2000",
        "DEJ2000",
        "Name",
        "PNstat",
        "Domain",
        "MajDiam",
        "MinDiam",
    )
    assert png.fetch_specs[0].citation == abell.fetch_specs[0].citation == registry.HASH_CITATION
    source = next(
        item
        for item in registry.get_sources(Path("unused-catalog-root"))
        if item.source_id == "vizier_hash"
    )
    assert source.attribution == registry.HASH_CITATION
    for wording in (
        "Parker, Q.A., Bojičić, I.S. & Frew, D.J. 2016",
        "HASH: the Hong Kong/AAO/Strasbourg Hα planetary nebula database",
        "This research has made use of the HASH PN database at hashpn.space",
        "(VizieR V/163)",
        registry.CDS_CITATION,
    ):
        assert wording in source.attribution
    assert png.credit == "Parker, Bojičić & Frew 2016 (HASH). Retrieved via VizieR V/163."
    assert abell.credit == (
        "Parker, Bojičić & Frew 2016 (HASH). Retrieved via VizieR V/163."
        + registry.ABELL_PN_COVERAGE
    )


def test_collect_hash_png_filters_domain_and_status_and_converts_sizes(tmp_path: Path):
    rows = {
        row.source_key: row for row in _batch(_catalogs_root(tmp_path), frozenset({"png"})).objects
    }

    assert set(rows) == {
        "9",
        "11",
        "104",
        "384",
        "579",
        "654",
        "662",
        "717",
        "739",
        "32403",
    }
    assert rows["384"].identifier == "036.1-57.1"
    assert rows["384"].columns["maj_axis_arcmin"] == pytest.approx(970.0 / 60.0)
    assert rows["384"].columns["min_axis_arcmin"] == pytest.approx(735.0 / 60.0)
    assert rows["9"].columns["min_axis_arcmin"] is None
    assert rows["11"].columns["openngc_notes"] == "Also M 3-43"
    assert rows["11"].cross_identifications == ()
    assert rows["739"].extra_designations == ()
    assert rows["739"].also_catalog_ids == ()
    assert "5095" not in rows  # P status, but the row belongs to the LMC.


def test_collect_hash_compound_ngc_ic_names_match_leading_object_and_keep_full_note(
    tmp_path: Path,
):
    rows = {
        row.source_key: row for row in _batch(_catalogs_root(tmp_path), frozenset({"png"})).objects
    }

    assert rows["104"].cross_identifications == (("ic", "5148"),)
    assert rows["104"].columns["openngc_notes"] == "Also IC 5148/50"
    assert rows["662"].cross_identifications == (("ngc", "650"),)
    assert rows["662"].columns["openngc_notes"] == "Also NGC 650-1"
    assert rows["717"].cross_identifications == (("ngc", "2371"),)
    assert rows["717"].columns["openngc_notes"] == "Also NGC 2371-72"


def test_collect_hash_tight_sharpless_and_negative_names_are_pinned(tmp_path: Path):
    root = _catalogs_root(tmp_path)
    collected = {row.source_key: row for row in _batch(root, frozenset({"png"})).objects}
    fixture_rows = {
        str(int(row["HASH"])): row
        for row in parse_vizier_tsv(root / "vizier" / HASH_FILENAME)
        if row["HASH"] is not None
    }

    assert collected["32403"].cross_identifications == (("sharpless2", "123"),)
    assert collected["32403"].columns["openngc_notes"] is None
    assert collected["579"].cross_identifications == ()
    assert collected["579"].columns["openngc_notes"] == "Also Sh 1-89"
    assert _cross_identifications(fixture_rows["232"]["Name"]) == ()
    assert fixture_rows["232"]["PNstat"] == "Sy?"
    assert _notes(fixture_rows["232"]["Name"], "Sy?", is_abell=False) == (
        "HASH classifies this as Sy?, not a planetary nebula. · Also M 2-9"
    )


def test_collect_hash_abell_uses_current_class_and_non_pn_notes(tmp_path: Path):
    rows = {
        row.source_key: row
        for row in _batch(_catalogs_root(tmp_path), frozenset({"abell_pn"})).objects
    }

    assert set(rows) == {"739", "936", "4794"}
    assert rows["739"].catalog_id == "abell_pn"
    assert rows["739"].catalog == "abell"
    assert rows["739"].identifier == "21"
    assert rows["739"].columns["primary_designation"] == "Abell 21"
    assert rows["739"].columns["obj_type"] == "PN"
    assert rows["936"].columns["obj_type"] == "Neb"
    assert rows["936"].columns["openngc_notes"] == (
        "HASH classifies this as Ionized ISM, not a planetary nebula."
    )
    assert rows["4794"].columns["obj_type"] == "G"
    assert rows["4794"].columns["openngc_notes"] == (
        "HASH classifies this as Galaxy, not a planetary nebula."
    )
    assert all(row.catalog != "png" for row in rows.values())


def test_collect_hash_both_catalogs_share_true_abell_rows_only(tmp_path: Path):
    rows = {
        row.source_key: row
        for row in _batch(_catalogs_root(tmp_path), frozenset({"png", "abell_pn"})).objects
    }

    assert rows["739"].catalog_id == "png"
    assert rows["739"].also_catalog_ids == ("abell_pn",)
    assert rows["739"].extra_designations == (("abell", "21"),)
    assert rows["739"].columns["primary_designation"] == "PN G205.1+14.2"
    assert rows["936"].catalog_id == "abell_pn"
    assert rows["936"].also_catalog_ids == ()
    assert rows["936"].extra_designations == ()


def test_collect_hash_full_sample_counts_when_available():
    if not FULL_SAMPLE.exists():
        pytest.skip("local full HASH sample is not present")
    source = CatalogSource(
        source_id="vizier_hash",
        category="vizier",
        display_name="HASH sample",
        file_path=FULL_SAMPLE,
        version=None,
        source_url=None,
        license="CDS public",
        attribution=registry.HASH_CITATION,
        parser="png",
    )

    objects = collect_hash({source.source_id: source}, frozenset({"png"})).objects

    assert len(objects) == 3973
    assert len(collect_hash({source.source_id: source}, frozenset({"abell_pn"})).objects) == 80
    ngc_ic = [
        cross_identification
        for row in objects
        for cross_identification in row.cross_identifications
        if cross_identification[0] in {"ngc", "ic"}
    ]
    sharpless2 = [
        (row.source_key, cross_identification)
        for row in objects
        for cross_identification in row.cross_identifications
        if cross_identification[0] == "sharpless2"
    ]
    assert len(ngc_ic) == 128
    assert len(sharpless2) == 9
    assert ("32403", ("sharpless2", "123")) in sharpless2


def test_hash_reconcile_merges_ngc_and_sharpless_names_and_keeps_abell_standalone(
    tmp_path: Path,
):
    root = _catalogs_root(tmp_path)
    built = build_object_set(_sources(root), None, frozenset({"sharpless", "png", "abell_pn"}))
    ngc_index = next(
        index for index, obj in enumerate(built.objects) if obj.source_key == "NGC7293"
    )
    sharpless_index = next(
        index
        for index, obj in enumerate(built.objects)
        if obj.source_id == "vizier_sharpless" and obj.source_key == "188"
    )
    abell = next(
        obj for obj in built.objects if obj.source_id == "vizier_hash" and obj.source_key == "739"
    )

    assert built.merges[("vizier_hash", "384")] == ngc_index
    assert ("png", "036.1-57.1", False) in built.objects[ngc_index].designations
    assert built.merges[("vizier_hash", "654")] == sharpless_index
    assert ("png", "128.0-04.0", False) in built.objects[sharpless_index].designations
    assert abell.designations == (
        ("png", "205.1+14.2", True),
        ("abell", "21", False),
    )
    assert built.groups == ()


@pytest.mark.parametrize(
    ("chosen", "entry_catalogs", "expected_designations", "primary"),
    (
        (frozenset(), set(), set(), None),
        (
            frozenset({"png"}),
            {"png"},
            {("png", "205.1+14.2", 1)},
            "PN G205.1+14.2",
        ),
        (
            frozenset({"abell_pn"}),
            {"abell_pn"},
            {("abell", "21", 1)},
            "Abell 21",
        ),
        (
            frozenset({"png", "abell_pn"}),
            {"png", "abell_pn"},
            {("png", "205.1+14.2", 1), ("abell", "21", 0)},
            "PN G205.1+14.2",
        ),
    ),
)
def test_hash_fresh_install_supports_all_four_selection_states(
    tmp_path: Path,
    chosen: frozenset[str],
    entry_catalogs: set[str],
    expected_designations: set[tuple[str, str, int]],
    primary: str | None,
):
    root = _catalogs_root(tmp_path, installed=True)
    write_choice(root, CatalogChoice(chosen, frozenset()))
    with _fresh_connection(tmp_path / "fresh.db") as conn:
        load_catalogs(conn, root)
        row = _hash_entry(conn, "739")
        assert _hash_entry_catalogs(conn, "739") == entry_catalogs
        if primary is None:
            assert row is None
        else:
            assert row is not None
            assert row["primary_designation"] == primary
            assert _designations(conn, int(row["id"])) == expected_designations

        ngc_id = int(
            conn.execute(
                "SELECT dso_id FROM dso_designation WHERE catalog='ngc' AND identifier='7293'"
            ).fetchone()[0]
        )
        ngc_png = conn.execute(
            "SELECT 1 FROM dso_designation WHERE dso_id=? AND catalog='png'",
            (ngc_id,),
        ).fetchone()
        assert (ngc_png is not None) is ("png" in chosen)

        abell_35 = _hash_entry(conn, "936")
        if "abell_pn" in chosen:
            assert abell_35 is not None
            assert abell_35["primary_designation"] == "Abell 35"
            assert abell_35["obj_type"] == "Neb"
            assert abell_35["openngc_notes"] == (
                "HASH classifies this as Ionized ISM, not a planetary nebula."
            )
        else:
            assert abell_35 is None


def test_hash_transitions_rerun_selection_and_preserve_shared_abell_identity(
    db: sqlite3.Connection, tmp_path: Path
):
    root = _catalogs_root(tmp_path, installed=True)
    hash_path = root / "vizier" / HASH_FILENAME
    original_hash = file_sha256(hash_path)
    choice = CatalogChoice(frozenset({"png", "abell_pn"}), frozenset())
    write_choice(root, choice)
    load_catalogs(db, root)
    abell_before = _hash_entry(db, "739")
    png_only_before = _hash_entry(db, "9")
    assert abell_before is not None and png_only_before is not None

    choice = with_removed(choice, "png")
    write_choice(root, choice)
    assert prepare_object_step(db, root, force=False).run is True
    load_catalogs(db, root)
    abell_after = _hash_entry(db, "739")
    assert abell_after is not None
    assert abell_after["id"] == abell_before["id"]
    assert abell_after["primary_designation"] == "Abell 21"
    assert _hash_entry(db, "9") is None
    assert db.execute("SELECT 1 FROM dso WHERE id=?", (png_only_before["id"],)).fetchone() is None
    assert hash_path.exists() and file_sha256(hash_path) == original_hash

    choice = with_removed(choice, "abell_pn")
    write_choice(root, choice)
    assert prepare_object_step(db, root, force=False).run is True
    load_catalogs(db, root)
    assert _hash_entry(db, "739") is None

    choice = with_added(choice, "png")
    write_choice(root, choice)
    assert prepare_object_step(db, root, force=False).run is True
    load_catalogs(db, root)
    assert _hash_entry_catalogs(db, "739") == {"png"}

    choice = with_added(choice, "abell_pn")
    write_choice(root, choice)
    assert prepare_object_step(db, root, force=False).run is True
    load_catalogs(db, root)
    assert _hash_entry_catalogs(db, "739") == {"png", "abell_pn"}
    assert hash_path.exists() and file_sha256(hash_path) == original_hash


def test_hash_selection_change_applies_once_to_second_database_with_unchanged_file(
    tmp_path: Path,
):
    root = _catalogs_root(tmp_path, installed=True)
    write_choice(
        root,
        CatalogChoice(frozenset({"png", "abell_pn"}), frozenset()),
    )
    first = _fresh_connection(tmp_path / "first.db")
    second = _fresh_connection(tmp_path / "second.db")
    try:
        load_catalogs(first, root)
        load_catalogs(second, root)
        second_abell_id = int(_hash_entry(second, "739")["id"])
        hash_before = file_sha256(root / "vizier" / HASH_FILENAME)

        write_choice(root, with_removed(read_choice(root), "png"))
        load_catalogs(first, root)
        assert prepare_object_step(second, root, force=False).run is True
        load_catalogs(second, root)
        assert int(_hash_entry(second, "739")["id"]) == second_abell_id
        assert _hash_entry(second, "9") is None
        assert prepare_object_step(second, root, force=False).run is False
        assert file_sha256(root / "vizier" / HASH_FILENAME) == hash_before
    finally:
        first.close()
        second.close()


@pytest.mark.anyio
async def test_hash_api_removal_keeps_shared_file_and_abell_identity(
    db: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = _catalogs_root(tmp_path, installed=True)
    hash_path = root / "vizier" / HASH_FILENAME
    digest = file_sha256(hash_path)
    write_choice(root, CatalogChoice(frozenset({"png", "abell_pn"}), frozenset()))
    load_catalogs(db, root)
    abell_before = _hash_entry(db, "739")
    assert abell_before is not None

    monkeypatch.setattr(registry, "user_catalogs_root", lambda: root)
    monkeypatch.setattr(
        "nightcrate.api.admin.load_config", lambda: SimpleNamespace(db_configured=True)
    )
    catalog_progress.reset()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/admin/catalogs/optional/png/remove")
    finally:
        catalog_progress.reset()

    assert response.status_code == 200
    abell_after = _hash_entry(db, "739")
    assert abell_after is not None
    assert abell_after["id"] == abell_before["id"]
    assert abell_after["primary_designation"] == "Abell 21"
    assert _hash_entry(db, "9") is None
    assert hash_path.exists()
    assert file_sha256(hash_path) == digest
    metadata = json.loads((root / "vizier" / "version.json").read_text(encoding="utf-8"))
    assert metadata["files"][HASH_FILENAME]["sha256"] == digest
