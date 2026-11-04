"""Reviewed match overrides and catalog-derived DSO groups."""

from __future__ import annotations

import csv
import json
import logging
import shutil
import sqlite3
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

import pytest

from nightcrate.catalog_loader import load_catalogs, registry
from nightcrate.catalog_loader import reconcile as reconcile_module
from nightcrate.catalog_loader.catalog_choice import CatalogChoice, write_choice
from nightcrate.catalog_loader.hash import file_sha256
from nightcrate.catalog_loader.loader import _build_search_key
from nightcrate.catalog_loader.reconcile import (
    COLLECTOR_ORDER,
    OBJECT_COLLECTORS,
    CollectedGroup,
    CollectedObject,
    CollectorBatch,
    NewGroup,
    NewObject,
    ObjectSet,
    SourceEntry,
    apply_object_set,
    build_object_set,
)
from nightcrate.catalog_loader.registry import CatalogSource, OptionalCatalog, get_sources
from nightcrate.catalog_loader.user_links import dso_reference_tables

FIXTURES = Path(__file__).parent.parent / "fixtures" / "catalogs" / "openngc"


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(tmp_path / "test.db")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    yield connection
    connection.close()


def _source(path: Path, source_id: str, parser: str) -> CatalogSource:
    return CatalogSource(
        source_id=source_id,
        category="nightcrate" if source_id.startswith("nightcrate") else "vizier",
        display_name=source_id,
        file_path=path,
        version="test",
        source_url=None,
        license="MIT",
        attribution="test",
        parser=parser,
    )


def _openngc_files(
    root: Path,
    rows: list[dict[str, str]],
    addendum_rows: list[dict[str, str]] | None = None,
) -> dict[str, CatalogSource]:
    root.mkdir(parents=True)
    with (FIXTURES / "mini_NGC.csv").open(encoding="utf-8", newline="") as handle:
        fieldnames = csv.DictReader(handle, delimiter=";").fieldnames
    assert fieldnames is not None
    for filename, file_rows in (("NGC.csv", rows), ("addendum.csv", addendum_rows or [])):
        with (root / filename).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=";")
            writer.writeheader()
            writer.writerows(file_rows)
    return {
        "openngc": _source(root / "NGC.csv", "openngc", "openngc"),
        "openngc_addendum": _source(root / "addendum.csv", "openngc_addendum", "openngc"),
    }


def _openngc_row(name: str, identifiers: str = "") -> dict[str, str]:
    with (FIXTURES / "mini_NGC.csv").open(encoding="utf-8", newline="") as handle:
        fieldnames = csv.DictReader(handle, delimiter=";").fieldnames
    assert fieldnames is not None
    row = dict.fromkeys(fieldnames, "")
    row.update(
        {
            "Name": name,
            "Type": "SNR" if name == "NGC6960" else "G",
            "RA": "20:45:58",
            "Dec": "+30:35:43",
            "Const": "Cyg",
            "MajAx": "210",
            "MinAx": "160",
            "Identifiers": identifiers,
        }
    )
    return row


def _optional(catalog_id: str, source_id: str, designation: str) -> OptionalCatalog:
    return OptionalCatalog(
        catalog_id=catalog_id,
        display_name=catalog_id,
        source_ids=(source_id,),
        kind="nightcrate",
        fetch_specs=(),
        designation_catalogs=frozenset({designation}),
        legacy_default=False,
        credit="test",
    )


def _columns(primary: str, size: float = 10.0) -> dict[str, object]:
    return {
        "primary_designation": primary,
        "obj_type": "Neb",
        "ra_deg": 1.0,
        "dec_deg": 2.0,
        "maj_axis_arcmin": size,
        "min_axis_arcmin": size,
        "source_row_hash": primary,
    }


def test_override_reserves_designation_against_openngc_alternate(tmp_path: Path):
    sources = _openngc_files(tmp_path / "openngc", [_openngc_row("NGC6960", "LBN 191")])
    override = tmp_path / "overrides.csv"
    override.write_text(
        "designation,action,target_designation,notes\nLBN 191,separate,,test\n",
        encoding="utf-8",
    )
    sources["nightcrate_match_overrides"] = _source(
        override, "nightcrate_match_overrides", "overrides"
    )

    built = build_object_set(sources, None, frozenset())

    ngc = next(obj for obj in built.objects if obj.source_key == "NGC6960")
    assert ("lbn", "191", False) not in ngc.designations


def test_duplicate_assign_override_moves_only_its_designation(tmp_path: Path):
    m101 = _openngc_row("NGC5457")
    m101["M"] = "101"
    duplicate = _openngc_row("M102")
    duplicate.update({"Type": "Dup", "M": "101"})
    sources = _openngc_files(
        tmp_path / "openngc",
        [m101, _openngc_row("NGC5866")],
        [duplicate],
    )
    override = tmp_path / "overrides.csv"
    override.write_text(
        "designation,action,target_designation,notes\nM 102,assign,NGC 5866,test\n",
        encoding="utf-8",
    )
    sources["nightcrate_match_overrides"] = _source(
        override, "nightcrate_match_overrides", "overrides"
    )

    built = build_object_set(sources, None, frozenset())

    m101_index = next(i for i, obj in enumerate(built.objects) if obj.source_key == "NGC5457")
    ngc5866_index = next(i for i, obj in enumerate(built.objects) if obj.source_key == "NGC5866")
    assert {designation[:2] for designation in built.objects[m101_index].designations} == {
        ("ngc", "5457"),
        ("messier", "101"),
    }
    assert ("messier", "102") in {
        designation[:2] for designation in built.objects[ngc5866_index].designations
    }
    assert built.merges[("openngc_addendum", "M102")] == ngc5866_index
    assert SourceEntry("openngc_addendum", "M102", "openngc", ngc5866_index) in built.entries


def test_duplicate_without_override_keeps_stated_target(tmp_path: Path):
    m101 = _openngc_row("NGC5457")
    m101["M"] = "101"
    duplicate = _openngc_row("M102")
    duplicate.update({"Type": "Dup", "M": "101"})
    sources = _openngc_files(
        tmp_path / "openngc",
        [m101, _openngc_row("NGC5866")],
        [duplicate],
    )

    built = build_object_set(sources, None, frozenset())

    m101_object = next(obj for obj in built.objects if obj.source_key == "NGC5457")
    ngc5866_object = next(obj for obj in built.objects if obj.source_key == "NGC5866")
    assert ("messier", "102", False) in m101_object.designations
    assert all(designation[:2] != ("messier", "102") for designation in ngc5866_object.designations)


def test_separate_override_keeps_duplicate_off_stated_target(tmp_path: Path):
    m101 = _openngc_row("NGC5457")
    m101["M"] = "101"
    duplicate = _openngc_row("M102")
    duplicate.update({"Type": "Dup", "M": "101"})
    sources = _openngc_files(tmp_path / "openngc", [m101], [duplicate])
    override = tmp_path / "overrides.csv"
    override.write_text(
        "designation,action,target_designation,notes\nM 102,separate,,test\n",
        encoding="utf-8",
    )
    sources["nightcrate_match_overrides"] = _source(
        override, "nightcrate_match_overrides", "overrides"
    )

    built = build_object_set(sources, None, frozenset())

    assert all(
        designation[:2] != ("messier", "102")
        for obj in built.objects
        for designation in obj.designations
    )
    assert ("openngc_addendum", "M102") not in built.merges
    assert built.unresolved == 1


def test_always_loaded_assign_override_adds_alias_without_source_row(tmp_path: Path):
    sources = _openngc_files(tmp_path / "openngc", [_openngc_row("NGC5866")])
    override = tmp_path / "overrides.csv"
    override.write_text(
        "designation,action,target_designation,notes\nM 102,assign,NGC 5866,test\n",
        encoding="utf-8",
    )
    sources["nightcrate_match_overrides"] = _source(
        override, "nightcrate_match_overrides", "overrides"
    )

    built = build_object_set(sources, None, frozenset())

    assert ("messier", "102") in {designation[:2] for designation in built.objects[0].designations}


def test_duplicate_assign_override_second_load_runs_no_object_step(
    db: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    catalogs_root = tmp_path / "catalogs"
    m101 = _openngc_row("NGC5457")
    m101["M"] = "101"
    duplicate = _openngc_row("M102")
    duplicate.update({"Type": "Dup", "M": "101"})
    _openngc_files(
        catalogs_root / "openngc",
        [m101, _openngc_row("NGC5866")],
        [duplicate],
    )
    override = tmp_path / "overrides.csv"
    override.write_text(
        "designation,action,target_designation,notes\nM 102,assign,NGC 5866,test\n",
        encoding="utf-8",
    )
    sources = [
        replace(source, file_path=override)
        if source.source_id == "nightcrate_match_overrides"
        else source
        for source in get_sources(catalogs_root)
    ]
    monkeypatch.setattr("nightcrate.catalog_loader.loader.get_sources", lambda _root: sources)

    first = load_catalogs(db, catalogs_root)
    owner = db.execute(
        """
        SELECT d.source_key
        FROM dso_designation dd JOIN dso d ON d.id=dd.dso_id
        WHERE dd.catalog='messier' AND dd.identifier='102'
        """
    ).fetchone()
    assert owner is not None and owner[0] == "NGC5866"

    def unexpected(*_args, **_kwargs):
        raise AssertionError("unchanged object step repeated")

    monkeypatch.setattr("nightcrate.catalog_loader.reconcile.apply_object_set", unexpected)
    second = load_catalogs(db, catalogs_root)

    assert next(row for row in first.results if row.source_id == "openngc").status == "loaded"
    assert next(row for row in second.results if row.source_id == "openngc").status == "unchanged"


def test_assign_with_target_catalog_off_creates_standalone_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    sources = _openngc_files(tmp_path / "openngc", [_openngc_row("NGC6960", "LBN 1")])
    override = tmp_path / "overrides.csv"
    override.write_text(
        "designation,action,target_designation,notes\nLBN 1,assign,Sh2-1,test\n",
        encoding="utf-8",
    )
    lbn_file = tmp_path / "lbn.tsv"
    lbn_file.write_text("fixture\n", encoding="utf-8")
    sources["nightcrate_match_overrides"] = _source(
        override, "nightcrate_match_overrides", "overrides"
    )
    sources["test_lbn"] = _source(lbn_file, "test_lbn", "test_lbn")
    monkeypatch.setattr(
        registry,
        "OPTIONAL_CATALOGS",
        (_optional("lbn", "test_lbn", "lbn"), _optional("sharpless", "test_sh2", "sharpless2")),
    )
    monkeypatch.setitem(
        OBJECT_COLLECTORS,
        "lbn",
        lambda sources, on_catalogs: CollectorBatch(
            (CollectedObject("test_lbn", "1", "lbn", "lbn", "1", _columns("LBN 1")),),
            (),
            {"test_lbn": "lbn-hash"},
        ),
    )

    built = build_object_set(sources, None, frozenset({"lbn"}))

    owner = next(i for i, obj in enumerate(built.objects) if obj.source_key == "1")
    assert built.merges.get(("test_lbn", "1")) is None
    assert ("lbn", "1", True) in built.objects[owner].designations
    assert all(match.catalog != "lbn" for match in built.stated_matches)


def test_require_match_drops_absent_target_while_default_stays_standalone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    sources = _openngc_files(tmp_path / "openngc", [])
    source_path = tmp_path / "objects.tsv"
    source_path.write_text("fixture\n", encoding="utf-8")
    sources["test_lbn"] = _source(source_path, "test_lbn", "lbn")
    monkeypatch.setattr(registry, "OPTIONAL_CATALOGS", (_optional("lbn", "test_lbn", "lbn"),))
    require_match = True

    def collector(_sources, _on_catalogs):
        return CollectorBatch(
            (
                CollectedObject(
                    "test_lbn",
                    "missing-target",
                    "lbn",
                    "lbn",
                    "99",
                    _columns("LBN 99"),
                    cross_identifications=(("ngc", "9999"),),
                    require_match=require_match,
                ),
            ),
            (),
            {"test_lbn": "lbn-hash"},
        )

    monkeypatch.setitem(OBJECT_COLLECTORS, "lbn", collector)
    caplog.set_level(logging.INFO, logger="nightcrate.catalog_loader.reconcile")

    required = build_object_set(sources, None, frozenset({"lbn"}))
    require_match = False
    optional = build_object_set(sources, None, frozenset({"lbn"}))

    assert all(obj.source_id != "test_lbn" for obj in required.objects)
    standalone = next(obj for obj in optional.objects if obj.source_id == "test_lbn")
    assert standalone.designations == (("lbn", "99", True),)
    assert "dropped required match test_lbn/missing-target with no owner" in caplog.text
    assert "dropped 1 rows that require an existing match" in caplog.text


def test_separate_lbn_191_is_standalone_and_not_owned_by_ngc_6960(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    sources = _openngc_files(tmp_path / "openngc", [_openngc_row("NGC6960", "LBN 191")])
    editorial = Path(registry._nightcrate_dir())
    sources["nightcrate_match_overrides"] = _source(
        editorial / "dso_match_overrides.csv", "nightcrate_match_overrides", "overrides"
    )
    lbn_file = tmp_path / "lbn.tsv"
    lbn_file.write_text("fixture\n", encoding="utf-8")
    sources["test_lbn"] = _source(lbn_file, "test_lbn", "test_lbn")
    monkeypatch.setattr(registry, "OPTIONAL_CATALOGS", (_optional("lbn", "test_lbn", "lbn"),))
    monkeypatch.setitem(
        OBJECT_COLLECTORS,
        "lbn",
        lambda sources, on_catalogs: CollectorBatch(
            (CollectedObject("test_lbn", "191", "lbn", "lbn", "191", _columns("LBN 191", 210)),),
            (),
            {"test_lbn": "lbn-hash"},
        ),
    )

    built = build_object_set(sources, None, frozenset({"lbn"}))

    lbn = next(obj for obj in built.objects if obj.source_id == "test_lbn")
    ngc = next(obj for obj in built.objects if obj.source_key == "NGC6960")
    assert ("lbn", "191", True) in lbn.designations
    assert all(designation[:2] != ("lbn", "191") for designation in ngc.designations)


def test_alias_override_follows_optional_catalog_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    sources = _openngc_files(tmp_path / "openngc", [_openngc_row("NGC6742")])
    editorial = Path(registry._nightcrate_dir())
    sources["nightcrate_match_overrides"] = _source(
        editorial / "dso_match_overrides.csv", "nightcrate_match_overrides", "overrides"
    )
    monkeypatch.setattr(
        registry,
        "OPTIONAL_CATALOGS",
        (_optional("abell_pn", "test_hash", "abell"),),
    )

    off = build_object_set(sources, None, frozenset())
    on = build_object_set(sources, None, frozenset({"abell_pn"}))

    assert all(obj.designations == (("ngc", "6742", True),) for obj in off.objects)
    assert ("abell", "50", False) in on.objects[0].designations


def test_release_clears_claim_and_allows_reclaim(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    with pytest.raises(ValueError, match="collector row test_arp/244"):
        CollectedObject(
            "test_arp",
            "244",
            "arp",
            "arp",
            "244",
            _columns("Arp 244"),
            release_designations=(("arp", "244"),),
            require_match=True,
        )

    sources = _openngc_files(tmp_path / "openngc", [_openngc_row("NGC4038", "Arp 244")])
    arp_file = tmp_path / "arp.tsv"
    arp_file.write_text("fixture\n", encoding="utf-8")
    sources["test_arp"] = _source(arp_file, "test_arp", "test_arp")
    monkeypatch.setattr(registry, "OPTIONAL_CATALOGS", (_optional("arp", "test_arp", "arp"),))
    monkeypatch.setitem(
        OBJECT_COLLECTORS,
        "arp",
        lambda sources, on_catalogs: CollectorBatch(
            (
                CollectedObject(
                    "test_arp",
                    "244",
                    "arp",
                    "arp",
                    "244",
                    _columns("Arp 244"),
                    release_designations=(("arp", "244"),),
                ),
            ),
            (),
            {"test_arp": "arp-hash"},
        ),
    )

    built = build_object_set(sources, None, frozenset({"arp"}))

    ngc = next(obj for obj in built.objects if obj.source_key == "NGC4038")
    arp = next(obj for obj in built.objects if obj.source_id == "test_arp")
    assert all(designation[:2] != ("arp", "244") for designation in ngc.designations)
    assert ("arp", "244", True) in arp.designations


def test_collectors_follow_explicit_order_not_source_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    openngc = _openngc_files(tmp_path / "openngc", [])
    melotte_path = tmp_path / "melotte.csv"
    lbn_path = tmp_path / "lbn.tsv"
    melotte_path.write_text("fixture\n", encoding="utf-8")
    lbn_path.write_text("fixture\n", encoding="utf-8")
    melotte_source = _source(melotte_path, "test_melotte", "melotte")
    lbn_source = _source(lbn_path, "test_lbn", "lbn")
    # Both registry and source order are the reverse of ownership order.
    sources = {"test_lbn": lbn_source, "test_melotte": melotte_source, **openngc}
    monkeypatch.setattr(
        registry,
        "OPTIONAL_CATALOGS",
        (
            _optional("lbn", "test_lbn", "lbn"),
            _optional("melotte", "test_melotte", "melotte"),
        ),
    )
    monkeypatch.setitem(
        OBJECT_COLLECTORS,
        "melotte",
        lambda sources, on_catalogs: CollectorBatch(
            (CollectedObject("test_melotte", "mel", "melotte", "lbn", "99", _columns("Mel 1")),),
            (),
            {"test_melotte": "melotte-hash"},
        ),
    )
    monkeypatch.setitem(
        OBJECT_COLLECTORS,
        "lbn",
        lambda sources, on_catalogs: CollectorBatch(
            (CollectedObject("test_lbn", "lbn", "lbn", "lbn", "99", _columns("LBN 99")),),
            (),
            {"test_lbn": "lbn-hash"},
        ),
    )

    built = build_object_set(sources, None, frozenset({"melotte", "lbn"}))

    owner = next(obj for obj in built.objects if ("lbn", "99", True) in obj.designations)
    assert COLLECTOR_ORDER.index("melotte") < COLLECTOR_ORDER.index("lbn")
    assert owner.source_id == "test_melotte"
    assert built.merges[("test_lbn", "lbn")] == built.objects.index(owner)


@pytest.mark.parametrize("merge", [False, True])
def test_collector_two_catalog_row_records_both_entries(
    db: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    merge: bool,
):
    rows = [_openngc_row("NGC7293")] if merge else []
    sources = _openngc_files(tmp_path / "openngc", rows)
    shared_path = tmp_path / "hash.tsv"
    shared_path.write_text("fixture\n", encoding="utf-8")
    sources["test_hash"] = _source(shared_path, "test_hash", "png")
    png = _optional("png", "test_hash", "png")
    abell = _optional("abell_pn", "test_hash", "abell")
    monkeypatch.setattr(registry, "OPTIONAL_CATALOGS", (abell, png))

    def collect_hash(
        collector_sources: Mapping[str, CatalogSource], on_catalogs: frozenset[str]
    ) -> CollectorBatch:
        assert tuple(collector_sources) == ("test_hash",)
        assert on_catalogs == frozenset({"png", "abell_pn"})
        catalog, identifier, primary = (
            ("ngc", "7293", "PN G036.1-57.1") if merge else ("png", "036.1-57.1", "PN G036.1-57.1")
        )
        return CollectorBatch(
            (
                CollectedObject(
                    "test_hash",
                    "hash-1",
                    "png",
                    catalog,
                    identifier,
                    _columns(primary),
                    also_catalog_ids=("abell_pn",),
                ),
            ),
            (),
            {"test_hash": "hash-source"},
        )

    monkeypatch.setitem(OBJECT_COLLECTORS, "png", collect_hash)

    built = build_object_set(sources, None, frozenset({"png", "abell_pn"}))
    entries = [
        entry
        for entry in built.entries
        if (entry.source_id, entry.source_key) == ("test_hash", "hash-1")
    ]

    assert {entry.catalog_id for entry in entries} == {"png", "abell_pn"}
    assert len({entry.object_index for entry in entries}) == 1
    assert (("test_hash", "hash-1") in built.merges) is merge

    apply_object_set(db, built, ())
    stored = db.execute(
        """
        SELECT e.catalog_id
        FROM dso_source_entry e
        JOIN dso_catalog_source s ON s.id = e.source_catalog_id
        WHERE s.source_id = 'test_hash' AND e.source_key = 'hash-1'
        ORDER BY e.catalog_id
        """
    ).fetchall()
    assert [row[0] for row in stored] == ["abell_pn", "png"]


def test_two_source_collector_joins_and_tracks_each_input(
    db: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    catalogs_root = tmp_path / "catalogs"
    openngc = catalogs_root / "openngc"
    openngc.mkdir(parents=True)
    shutil.copy(FIXTURES / "mini_NGC.csv", openngc / "NGC.csv")
    shutil.copy(FIXTURES / "mini_addendum.csv", openngc / "addendum.csv")
    main_path = tmp_path / "wr_main.csv"
    phot_path = tmp_path / "wr_phot.csv"
    main_path.write_text("number,name\n1,Alpha\n", encoding="utf-8")
    phot_path.write_text("number,vmag\n1,12.3\n", encoding="utf-8")
    main_source_id = "nightcrate_sharpless_crossref"
    phot_source_id = "nightcrate_barnard_crossref"

    redirected: list[CatalogSource] = []
    for source in get_sources(catalogs_root):
        if source.source_id == main_source_id:
            source = replace(source, file_path=main_path, parser="wr")
        elif source.source_id == phot_source_id:
            source = replace(source, file_path=phot_path, parser="wr")
        redirected.append(source)
    monkeypatch.setattr("nightcrate.catalog_loader.loader.get_sources", lambda _root: redirected)
    monkeypatch.setattr(
        reconcile_module,
        "OBJECT_SOURCE_IDS",
        (*reconcile_module.OBJECT_SOURCE_IDS, main_source_id, phot_source_id),
    )
    wr = OptionalCatalog(
        "wr",
        "Wolf-Rayet",
        (main_source_id, phot_source_id),
        "nightcrate",
        (),
        frozenset({"wr"}),
        False,
        "test",
    )
    monkeypatch.setattr(registry, "OPTIONAL_CATALOGS", (wr,))
    calls: list[tuple[str, ...]] = []

    def collect_wr(
        collector_sources: Mapping[str, CatalogSource], on_catalogs: frozenset[str]
    ) -> CollectorBatch:
        calls.append(tuple(collector_sources))
        assert on_catalogs == frozenset({"wr"})
        with collector_sources[main_source_id].file_path.open(
            encoding="utf-8", newline=""
        ) as handle:
            main_rows = list(csv.DictReader(handle))
        with collector_sources[phot_source_id].file_path.open(
            encoding="utf-8", newline=""
        ) as handle:
            photometry = {row["number"]: row for row in csv.DictReader(handle)}
        objects = []
        for row in main_rows:
            number = row["number"]
            columns = _columns(f"WR {number}")
            columns["common_name"] = row["name"]
            columns["mag_v"] = float(photometry[number]["vmag"])
            objects.append(CollectedObject(main_source_id, number, "wr", "wr", number, columns))
        return CollectorBatch(
            tuple(objects),
            (),
            {
                source_id: file_sha256(source.file_path)
                for source_id, source in collector_sources.items()
            },
        )

    monkeypatch.setitem(OBJECT_COLLECTORS, "wr", collect_wr)
    write_choice(catalogs_root, CatalogChoice(frozenset({"wr"}), frozenset()))

    first = load_catalogs(db, catalogs_root)

    assert calls == [(main_source_id, phot_source_id)]
    assert tuple(
        db.execute(
            "SELECT common_name, mag_v FROM dso WHERE primary_designation = 'WR 1'"
        ).fetchone()
    ) == ("Alpha", 12.3)
    stored_hashes = dict(
        db.execute(
            "SELECT source_id, file_hash FROM dso_catalog_source WHERE source_id IN (?, ?)",
            (main_source_id, phot_source_id),
        ).fetchall()
    )
    assert stored_hashes == {
        main_source_id: file_sha256(main_path),
        phot_source_id: file_sha256(phot_path),
    }
    assert all(
        next(result for result in first.results if result.source_id == source_id).status == "loaded"
        for source_id in (main_source_id, phot_source_id)
    )

    phot_path.write_text("number,vmag\n1,11.2\n", encoding="utf-8")
    changed = load_catalogs(db, catalogs_root)
    unchanged = load_catalogs(db, catalogs_root)

    assert len(calls) == 2
    assert (
        db.execute("SELECT mag_v FROM dso WHERE primary_designation = 'WR 1'").fetchone()[0] == 11.2
    )
    assert (
        next(result for result in changed.results if result.source_id == phot_source_id).status
        == "loaded"
    )
    assert (
        next(result for result in unchanged.results if result.source_id == phot_source_id).status
        == "unchanged"
    )

    write_choice(catalogs_root, CatalogChoice(frozenset(), frozenset({"wr"})))
    removed = load_catalogs(db, catalogs_root)

    assert removed.objects_removed == 1
    assert db.execute("SELECT 1 FROM dso WHERE primary_designation = 'WR 1'").fetchone() is None


def test_collector_group_resolves_new_whole_and_existing_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    sources = _openngc_files(tmp_path / "openngc", [_openngc_row("NGC6960")])
    ldn_path = tmp_path / "ldn.tsv"
    ldn_path.write_text("fixture\n", encoding="utf-8")
    sources["test_ldn"] = _source(ldn_path, "test_ldn", "ldn")
    monkeypatch.setattr(registry, "OPTIONAL_CATALOGS", (_optional("ldn", "test_ldn", "ldn"),))
    monkeypatch.setitem(
        OBJECT_COLLECTORS,
        "ldn",
        lambda sources, on_catalogs: CollectorBatch(
            (CollectedObject("test_ldn", "whole", "ldn", "ldn", "1", _columns("LDN 1")),),
            (CollectedGroup("ldn", "1", ("test_ldn", "whole"), (), (("ngc", "6960"),)),),
            {"test_ldn": "ldn-hash"},
        ),
    )

    built = build_object_set(sources, None, frozenset({"ldn"}))

    group = built.groups[0]
    assert built.objects[group.whole_index].source_key == "whole"
    assert [built.objects[index].source_key for index in group.member_indexes] == ["NGC6960"]


def test_cross_identification_size_limit_is_only_applied_to_rule_r_step_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    known = _openngc_row("NGC1")
    known["MajAx"] = "10"
    unknown = _openngc_row("NGC2")
    unknown["MajAx"] = ""
    sources = _openngc_files(tmp_path / "openngc", [known, unknown])
    ldn_path = tmp_path / "ldn.tsv"
    ldn_path.write_text("fixture\n", encoding="utf-8")
    sources["test_ldn"] = _source(ldn_path, "test_ldn", "ldn")
    override_path = tmp_path / "overrides.csv"
    override_path.write_text(
        "designation,action,target_designation,notes\nLDN 6,assign,NGC 1,test\n",
        encoding="utf-8",
    )
    sources["nightcrate_match_overrides"] = _source(
        override_path, "nightcrate_match_overrides", "overrides"
    )
    monkeypatch.setattr(registry, "OPTIONAL_CATALOGS", (_optional("ldn", "test_ldn", "ldn"),))
    monkeypatch.setitem(
        OBJECT_COLLECTORS,
        "ldn",
        lambda sources, on_catalogs: CollectorBatch(
            (
                CollectedObject(
                    "test_ldn",
                    "comparable",
                    "ldn",
                    "ldn",
                    "1",
                    _columns("LDN 1"),
                    cross_identifications=(("ngc", "1"),),
                    match_size_arcmin=30,
                    match_size_ratio_max=3,
                ),
                CollectedObject(
                    "test_ldn",
                    "too-large",
                    "ldn",
                    "ldn",
                    "2",
                    _columns("LDN 2"),
                    cross_identifications=(("ngc", "1"),),
                    match_size_arcmin=31,
                    match_size_ratio_max=3,
                ),
                CollectedObject(
                    "test_ldn",
                    "unknown-target",
                    "ldn",
                    "ldn",
                    "3",
                    _columns("LDN 3"),
                    cross_identifications=(("ngc", "2"),),
                    match_size_arcmin=10,
                    match_size_ratio_max=3,
                ),
                CollectedObject(
                    "test_ldn",
                    "own-name",
                    "ldn",
                    "ngc",
                    "1",
                    _columns("NGC 1"),
                    match_size_arcmin=100,
                    match_size_ratio_max=3,
                ),
                CollectedObject(
                    "test_ldn",
                    "ungated",
                    "ldn",
                    "ldn",
                    "4",
                    _columns("LDN 4"),
                    cross_identifications=(("ngc", "1"),),
                    match_size_arcmin=100,
                ),
                CollectedObject(
                    "test_ldn",
                    "unknown-entry",
                    "ldn",
                    "ldn",
                    "5",
                    _columns("LDN 5", None),
                    cross_identifications=(("ngc", "1"),),
                    match_size_ratio_max=3,
                ),
                CollectedObject(
                    "test_ldn",
                    "assigned",
                    "ldn",
                    "ldn",
                    "6",
                    _columns("LDN 6"),
                    cross_identifications=(("ngc", "2"),),
                    match_size_arcmin=100,
                    match_size_ratio_max=3,
                ),
            ),
            (),
            {"test_ldn": "ldn-hash"},
        ),
    )

    built = build_object_set(sources, None, frozenset({"ldn"}))
    ngc_1 = next(index for index, obj in enumerate(built.objects) if obj.source_key == "NGC1")

    assert built.merges[("test_ldn", "comparable")] == ngc_1
    assert built.merges[("test_ldn", "own-name")] == ngc_1
    assert built.merges[("test_ldn", "ungated")] == ngc_1
    assert built.merges[("test_ldn", "assigned")] == ngc_1
    assert ("test_ldn", "too-large") not in built.merges
    assert ("test_ldn", "unknown-target") not in built.merges
    assert ("test_ldn", "unknown-entry") not in built.merges
    comparable = next(match for match in built.stated_matches if match.identifier == "1")
    assert comparable.entry_size_arcmin == 30
    assert comparable.target_size_arcmin == 10


def test_group_resolution_drops_members_that_resolve_to_the_whole(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    sources = _openngc_files(tmp_path / "openngc", [_openngc_row("NGC1"), _openngc_row("NGC2")])
    ldn_path = tmp_path / "ldn.tsv"
    ldn_path.write_text("fixture\n", encoding="utf-8")
    sources["test_ldn"] = _source(ldn_path, "test_ldn", "ldn")
    monkeypatch.setattr(registry, "OPTIONAL_CATALOGS", (_optional("ldn", "test_ldn", "ldn"),))
    monkeypatch.setitem(
        OBJECT_COLLECTORS,
        "ldn",
        lambda sources, on_catalogs: CollectorBatch(
            (
                CollectedObject(
                    "test_ldn",
                    "kept-group",
                    "ldn",
                    "ldn",
                    "1",
                    _columns("LDN 1"),
                    cross_identifications=(("ngc", "1"),),
                ),
                CollectedObject(
                    "test_ldn",
                    "empty-group",
                    "ldn",
                    "ldn",
                    "2",
                    _columns("LDN 2"),
                    cross_identifications=(("ngc", "1"),),
                ),
            ),
            (
                CollectedGroup(
                    "ldn",
                    "1",
                    ("test_ldn", "kept-group"),
                    member_designations=(("ngc", "2"), ("ngc", "999")),
                ),
                CollectedGroup(
                    "ldn",
                    "2",
                    ("test_ldn", "empty-group"),
                    member_designations=(("ngc", "1"),),
                ),
            ),
            {"test_ldn": "ldn-hash"},
        ),
    )

    built = build_object_set(sources, None, frozenset({"ldn"}))

    assert len(built.groups) == 1
    group = built.groups[0]
    assert group.identifier == "1"
    assert [built.objects[index].source_key for index in group.member_indexes] == ["NGC2"]


def test_arp_group_resolves_merged_members_after_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    sources = _openngc_files(
        tmp_path / "openngc",
        [_openngc_row("NGC4038", "Arp 244"), _openngc_row("NGC4039")],
    )
    arp_path = tmp_path / "arp.csv"
    arp_path.write_text("fixture\n", encoding="utf-8")
    sources["test_arp"] = _source(arp_path, "test_arp", "arp")
    monkeypatch.setattr(registry, "OPTIONAL_CATALOGS", (_optional("arp", "test_arp", "arp"),))
    monkeypatch.setitem(
        OBJECT_COLLECTORS,
        "arp",
        lambda sources, on_catalogs: CollectorBatch(
            (
                CollectedObject(
                    "test_arp",
                    "a",
                    "arp",
                    "ngc",
                    "4038",
                    _columns("NGC 4038"),
                    evidence="reviewed list",
                    release_designations=(("arp", "244"),),
                ),
                CollectedObject(
                    "test_arp",
                    "b",
                    "arp",
                    "ngc",
                    "4039",
                    _columns("NGC 4039"),
                    evidence="reviewed list",
                ),
            ),
            (CollectedGroup("arp", "244", None, (("test_arp", "a"), ("test_arp", "b")), ()),),
            {"test_arp": "arp-hash"},
        ),
    )

    built = build_object_set(sources, None, frozenset({"arp"}))

    group = built.groups[0]
    assert group.whole_index is None
    assert {built.objects[index].source_key for index in group.member_indexes} == {
        "NGC4038",
        "NGC4039",
    }
    assert all(
        designation[:2] != ("arp", "244")
        for obj in built.objects
        for designation in obj.designations
    )


def test_collector_extra_designation_claims_one_member_number(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    sources = _openngc_files(tmp_path / "openngc", [_openngc_row("NGC1")])
    arp_path = tmp_path / "arp.csv"
    arp_path.write_text("fixture\n", encoding="utf-8")
    sources["test_arp"] = _source(arp_path, "test_arp", "arp")
    monkeypatch.setattr(registry, "OPTIONAL_CATALOGS", (_optional("arp", "test_arp", "arp"),))
    monkeypatch.setitem(
        OBJECT_COLLECTORS,
        "arp",
        lambda sources, on_catalogs: CollectorBatch(
            (
                CollectedObject(
                    "test_arp",
                    "one",
                    "arp",
                    "ngc",
                    "1",
                    _columns("NGC 1"),
                    extra_designations=(("arp", "1"),),
                ),
            ),
            (),
            {"test_arp": "arp-hash"},
        ),
    )

    built = build_object_set(sources, None, frozenset({"arp"}))

    target = next(obj for obj in built.objects if obj.source_key == "NGC1")
    assert ("arp", "1", False) in target.designations


def test_collector_anonymous_member_is_reachable_through_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    sources = _openngc_files(tmp_path / "openngc", [])
    arp_path = tmp_path / "arp.csv"
    arp_path.write_text("fixture\n", encoding="utf-8")
    sources["test_arp"] = _source(arp_path, "test_arp", "arp")
    monkeypatch.setattr(registry, "OPTIONAL_CATALOGS", (_optional("arp", "test_arp", "arp"),))
    monkeypatch.setitem(
        OBJECT_COLLECTORS,
        "arp",
        lambda sources, on_catalogs: CollectorBatch(
            (CollectedObject("test_arp", "anonymous", "arp", None, None, _columns("Arp 146")),),
            (CollectedGroup("arp", "146", None, (("test_arp", "anonymous"),), ()),),
            {"test_arp": "arp-hash"},
        ),
    )

    built = build_object_set(sources, None, frozenset({"arp"}))

    anonymous_index = built.groups[0].member_indexes[0]
    anonymous = built.objects[anonymous_index]
    assert anonymous.source_key == "anonymous"
    assert anonymous.columns["primary_designation"] == "Arp 146"
    assert anonymous.designations == ()


def test_stated_match_evidence_uses_owner_and_row_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    sources = _openngc_files(tmp_path / "openngc", [_openngc_row("NGC1")])
    for catalog_id in ("melotte", "lbn", "arp"):
        path = tmp_path / f"{catalog_id}.csv"
        path.write_text("fixture\n", encoding="utf-8")
        sources[f"test_{catalog_id}"] = _source(path, f"test_{catalog_id}", catalog_id)
    monkeypatch.setattr(
        registry,
        "OPTIONAL_CATALOGS",
        tuple(
            _optional(catalog_id, f"test_{catalog_id}", catalog_id)
            for catalog_id in ("melotte", "lbn", "arp")
        ),
    )
    monkeypatch.setitem(
        OBJECT_COLLECTORS,
        "melotte",
        lambda sources, on_catalogs: CollectorBatch(
            (CollectedObject("test_melotte", "mel", "melotte", "melotte", "1", _columns("Mel 1")),),
            (),
            {"test_melotte": "melotte-hash"},
        ),
    )
    monkeypatch.setitem(
        OBJECT_COLLECTORS,
        "lbn",
        lambda sources, on_catalogs: CollectorBatch(
            (
                CollectedObject("test_lbn", "openngc", "lbn", "ngc", "1", _columns("NGC 1")),
                CollectedObject("test_lbn", "earlier", "lbn", "melotte", "1", _columns("Mel 1")),
            ),
            (),
            {"test_lbn": "lbn-hash"},
        ),
    )
    monkeypatch.setitem(
        OBJECT_COLLECTORS,
        "arp",
        lambda sources, on_catalogs: CollectorBatch(
            (
                CollectedObject(
                    "test_arp",
                    "reviewed",
                    "arp",
                    "melotte",
                    "1",
                    _columns("Mel 1"),
                    evidence="reviewed list",
                ),
            ),
            (),
            {"test_arp": "arp-hash"},
        ),
    )

    built = build_object_set(sources, None, frozenset({"melotte", "lbn", "arp"}))

    assert [match.evidence for match in built.stated_matches] == [
        "OpenNGC alternate",
        "earlier catalog: melotte",
        "reviewed list",
    ]


def test_groups_are_rebuilt_without_stale_rows(db: sqlite3.Connection, tmp_path: Path):
    source = _source(tmp_path / "objects.csv", "openngc", "openngc")
    source.file_path.write_text("fixture\n", encoding="utf-8")
    objects = (
        NewObject("openngc", "WHOLE", _columns("LBN 191"), (("lbn", "191", True),), 0),
        NewObject("openngc", "PART", _columns("NGC 6960"), (("ngc", "6960", True),), 1),
    )
    grouped = ObjectSet(
        objects,
        {},
        {"openngc": "hash"},
        0,
        {"openngc": source},
        groups=(NewGroup("lbn", "191", 0, (1,)),),
    )

    apply_object_set(db, grouped, ())
    assert db.execute("SELECT COUNT(*) FROM dso_group_member").fetchone()[0] == 1
    apply_object_set(db, replace(grouped, groups=()), ())
    assert db.execute("SELECT COUNT(*) FROM dso_group").fetchone()[0] == 0


def test_parts_group_collision_keeps_collector_group(
    db: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    sources = _openngc_files(
        tmp_path / "openngc",
        [_openngc_row("NGC1"), _openngc_row("NGC2")],
    )
    ldn_path = tmp_path / "ldn.tsv"
    ldn_path.write_text("fixture\n", encoding="utf-8")
    sources["test_ldn"] = _source(ldn_path, "test_ldn", "ldn")
    parts_path = tmp_path / "dso_parts.csv"
    parts_path.write_text(
        "whole_designation,part_designation,notes\nLDN 1,NGC 1,collision\n",
        encoding="utf-8",
    )
    sources["nightcrate_parts"] = _source(parts_path, "nightcrate_parts", "parts")
    monkeypatch.setattr(registry, "OPTIONAL_CATALOGS", (_optional("ldn", "test_ldn", "ldn"),))
    monkeypatch.setitem(
        OBJECT_COLLECTORS,
        "ldn",
        lambda sources, on_catalogs: CollectorBatch(
            (CollectedObject("test_ldn", "1", "ldn", "ldn", "1", _columns("LDN 1")),),
            (
                CollectedGroup(
                    "ldn",
                    "1",
                    ("test_ldn", "1"),
                    member_designations=(("ngc", "2"),),
                ),
            ),
            {"test_ldn": "ldn-hash"},
        ),
    )
    caplog.set_level(logging.WARNING, logger="nightcrate.catalog_loader.reconcile")

    built = build_object_set(sources, None, frozenset({"ldn"}))
    apply_object_set(db, built, ())

    assert len(built.groups) == 1
    group = built.groups[0]
    assert (group.catalog, group.identifier) == ("ldn", "1")
    assert [built.objects[index].source_key for index in group.member_indexes] == ["NGC2"]
    assert db.execute("SELECT COUNT(*) FROM dso_group").fetchone()[0] == 1
    assert "skipping parts row 'LDN 1' -> 'NGC 1'" in caplog.text


def test_parts_with_whole_catalog_off_are_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    sources = _openngc_files(tmp_path / "openngc", [_openngc_row("NGC6960")])
    editorial = Path(registry._nightcrate_dir())
    sources["nightcrate_parts"] = _source(editorial / "dso_parts.csv", "nightcrate_parts", "parts")
    lbn_file = tmp_path / "lbn.tsv"
    lbn_file.write_text("fixture\n", encoding="utf-8")
    sources["test_lbn"] = _source(lbn_file, "test_lbn", "test_lbn")
    monkeypatch.setattr(registry, "OPTIONAL_CATALOGS", (_optional("lbn", "test_lbn", "lbn"),))
    monkeypatch.setitem(
        OBJECT_COLLECTORS,
        "lbn",
        lambda sources, on_catalogs: CollectorBatch(
            (CollectedObject("test_lbn", "191", "lbn", "lbn", "191", _columns("LBN 191")),),
            (),
            {"test_lbn": "lbn-hash"},
        ),
    )

    built = build_object_set(sources, None, frozenset())

    assert built.groups == ()


@pytest.mark.parametrize(
    "source_id",
    [
        "nightcrate_parts",
        "nightcrate_match_overrides",
        "nightcrate_melotte",
        "nightcrate_arp_members",
    ],
)
def test_editorial_file_change_runs_object_step_once(
    db: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_id: str,
):
    catalogs_root = tmp_path / "catalogs"
    openngc = catalogs_root / "openngc"
    openngc.mkdir(parents=True)
    shutil.copy(FIXTURES / "mini_NGC.csv", openngc / "NGC.csv")
    shutil.copy(FIXTURES / "mini_addendum.csv", openngc / "addendum.csv")
    original_sources = get_sources(catalogs_root)
    redirected: list[CatalogSource] = []
    for source in original_sources:
        if source.source_id in {
            "nightcrate_parts",
            "nightcrate_match_overrides",
            "nightcrate_melotte",
            "nightcrate_arp_members",
        }:
            path = tmp_path / source.file_path.name
            shutil.copy(source.file_path, path)
            source = replace(source, file_path=path)
        redirected.append(source)
    monkeypatch.setattr("nightcrate.catalog_loader.loader.get_sources", lambda _root: redirected)
    if source_id == "nightcrate_melotte":
        write_choice(catalogs_root, CatalogChoice(frozenset({"melotte"}), frozenset()))
    elif source_id == "nightcrate_arp_members":
        arp_path = catalogs_root / "vizier" / "arp_VII_192.tsv"
        arp_path.parent.mkdir(parents=True)
        shutil.copy(FIXTURES.parent / "vizier" / "mini_arp.tsv", arp_path)
        (arp_path.parent / "version.json").write_text(
            json.dumps(
                {
                    "files": {
                        arp_path.name: {
                            "sha256": file_sha256(arp_path),
                            "fetch_date": "2026-11-02T00:00:00+00:00",
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        write_choice(catalogs_root, CatalogChoice(frozenset({"arp"}), frozenset()))

    first = load_catalogs(db, catalogs_root)
    changed_source = next(source for source in redirected if source.source_id == source_id)
    changed_source.file_path.write_text(
        changed_source.file_path.read_text(encoding="utf-8") + "# hash change\n",
        encoding="utf-8",
    )
    changed = load_catalogs(db, catalogs_root)
    unchanged = load_catalogs(db, catalogs_root)

    assert next(row for row in first.results if row.source_id == source_id).status == "loaded"
    assert next(row for row in changed.results if row.source_id == source_id).status == "loaded"
    assert (
        next(row for row in unchanged.results if row.source_id == source_id).status == "unchanged"
    )


def test_missing_previously_used_editorial_file_defers_object_step(
    db: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    catalogs_root = tmp_path / "catalogs"
    openngc = catalogs_root / "openngc"
    openngc.mkdir(parents=True)
    shutil.copy(FIXTURES / "mini_NGC.csv", openngc / "NGC.csv")
    shutil.copy(FIXTURES / "mini_addendum.csv", openngc / "addendum.csv")
    redirected = []
    for source in get_sources(catalogs_root):
        if source.source_id == "nightcrate_parts":
            path = tmp_path / "dso_parts.csv"
            shutil.copy(source.file_path, path)
            source = replace(source, file_path=path)
        redirected.append(source)
    monkeypatch.setattr("nightcrate.catalog_loader.loader.get_sources", lambda _root: redirected)
    load_catalogs(db, catalogs_root)
    parts = next(source for source in redirected if source.source_id == "nightcrate_parts")
    parts.file_path.unlink()

    summary = load_catalogs(db, catalogs_root)
    result = next(row for row in summary.results if row.source_id == "nightcrate_parts")

    assert result.status == "skipped"
    assert result.error is not None and "object step deferred" in result.error


def test_dso_group_tables_are_catalog_derived(db: sqlite3.Connection):
    tables = {table for table, _column in dso_reference_tables(db.cursor())}
    assert "dso_group" not in tables
    assert "dso_group_member" not in tables
    assert _build_search_key("lbn", "191") == "lbn191"
