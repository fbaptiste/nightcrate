"""Common-name validation, ordering, persistence, and lifecycle tests."""

from __future__ import annotations

import csv
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from nightcrate.catalog_loader import load_catalogs, registry
from nightcrate.catalog_loader.catalog_choice import CatalogChoice, write_choice
from nightcrate.catalog_loader.common_names import (
    merge_names,
    read_common_names,
    split_common_names,
)
from nightcrate.catalog_loader.hash import file_sha256
from nightcrate.catalog_loader.registry import CatalogSource, get_sources

FIXTURES = Path(__file__).parent.parent / "fixtures" / "catalogs"
FIELDS = ("designation", "target", "name", "action", "rank", "sources", "verified", "notes")


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(tmp_path / "test.db")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    yield connection
    connection.close()


@pytest.fixture
def catalogs_root(tmp_path: Path) -> Path:
    root = tmp_path / "catalogs"
    openngc = root / "openngc"
    openngc.mkdir(parents=True)
    shutil.copy(FIXTURES / "openngc" / "mini_NGC.csv", openngc / "NGC.csv")
    shutil.copy(FIXTURES / "openngc" / "mini_addendum.csv", openngc / "addendum.csv")
    shutil.copy(FIXTURES / "openngc" / "version.json", openngc / "version.json")
    return root


@pytest.fixture
def nightcrate_dir(tmp_path: Path, monkeypatch) -> Path:
    source = Path(registry.__file__).parent.parent / "data" / "catalogs" / "nightcrate"
    target = tmp_path / "nightcrate"
    shutil.copytree(source, target)
    monkeypatch.setattr(registry, "_nightcrate_dir", lambda: target)
    return target


def _source(path: Path) -> CatalogSource:
    return CatalogSource(
        "test_common_names",
        "nightcrate",
        "Test common names",
        path,
        None,
        None,
        registry.NIGHTCRATE_LICENSE,
        "test",
        "common_names",
    )


def _write_rows(path: Path, *rows: dict[str, str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(
            "# Test common names. GPL-3.0-or-later (see LICENSE at the repository root).\n"
        )
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _row(
    designation: str = "M 42",
    name: str = "Orion Nebula",
    *,
    target: str = "object",
    action: str = "name",
    rank: str = "1",
    sources: str = "SIMBAD:one;NED:two",
) -> dict[str, str]:
    return {
        "designation": designation,
        "target": target,
        "name": name,
        "action": action,
        "rank": rank,
        "sources": sources,
        "verified": "2026-11-03",
        "notes": "",
    }


def _append_openngc(path: Path, **values: str) -> None:
    with path.open(encoding="utf-8", newline="") as handle:
        fieldnames = csv.DictReader(handle, delimiter=";").fieldnames
    assert fieldnames is not None
    row = dict.fromkeys(fieldnames, "")
    row.update({"Type": "G", "RA": "01:00:00", "Dec": "+01:00:00", **values})
    with path.open("a", encoding="utf-8", newline="") as handle:
        csv.DictWriter(handle, fieldnames=fieldnames, delimiter=";").writerow(row)


def _names(db: sqlite3.Connection, designation: str) -> tuple[str | None, int, tuple[str, ...]]:
    row = db.execute(
        """
        SELECT d.id, d.common_name, d.common_name_augmented
        FROM dso d
        JOIN dso_designation dd ON dd.dso_id=d.id
        WHERE dd.display_form=? AND d.active=1
        """,
        (designation,),
    ).fetchone()
    assert row is not None
    others = db.execute(
        "SELECT name FROM dso_other_name WHERE dso_id=? ORDER BY position", (row["id"],)
    ).fetchall()
    return row["common_name"], row["common_name_augmented"], tuple(item[0] for item in others)


def test_split_common_names():
    assert split_common_names(None) == ()
    assert split_common_names("") == ()
    assert split_common_names(" A , a , B, ,b ") == ("A", "B")


def test_merge_names():
    assert merge_names((), ("A", "B"), (" a ", "C", "b")) == ("A", "B", "C")


@pytest.mark.parametrize(
    "rows,match",
    [
        ((_row(rank="2"),), "rank sequence"),
        ((_row(action="remove", rank="1", sources=""),), "cannot have a rank"),
        ((_row(name="Bad, Name"),), "contains a comma"),
        ((_row(sources="SIMBAD:one"),), "needs two sources"),
        ((_row(action="rename"),), "unknown common-name action"),
        ((_row(target="system"),), "unknown common-name target"),
        ((_row(designation="not a designation"),), "unrecognized designation"),
        (
            (_row(), _row("M 31", "Orion Nebula")),
            "assigned more than once",
        ),
        (
            (_row(), _row(name="orion nebula", rank="2")),
            "assigned more than once",
        ),
        (
            (
                _row("Arp 244", "Antennae", target="group"),
                _row("Arp 244", "Antennae Galaxies", target="group", rank="2"),
            ),
            "exactly one name",
        ),
        (
            (_row("Arp 244", "Antennae", target="group", action="remove", rank=""),),
            "cannot remove",
        ),
    ],
)
def test_read_common_names_validates(tmp_path: Path, rows, match: str):
    path = tmp_path / "common_names.csv"
    _write_rows(path, *rows)

    with pytest.raises(ValueError, match=match):
        read_common_names(_source(path))


@pytest.mark.parametrize(
    "sources",
    [
        "SIMBAD:one; SIMBAD:two",
        "Wikidata:Q1; Wikipedia:Example",
        "Wikipedia:Example; https://en.wikipedia.org/wiki/Example",
        "https://science.nasa.gov/example; https://apod.nasa.gov/example",
        "https://esa.int/example; https://esahubble.org/example; https://esawebb.org/example",
        "https://one.noirlab.edu/example; https://two.noirlab.edu/example",
        "https://one.saao.ac.za/example; https://two.saao.ac.za/example",
    ],
)
def test_read_common_names_requires_distinct_source_families(tmp_path: Path, sources: str):
    path = tmp_path / "common_names.csv"
    _write_rows(path, _row(sources=sources))

    with pytest.raises(ValueError, match="needs two sources"):
        read_common_names(_source(path))


def test_read_common_names_accepts_distinct_source_families(tmp_path: Path):
    path = tmp_path / "common_names.csv"
    _write_rows(
        path,
        _row(sources="https://science.nasa.gov/example; https://esahubble.org/example"),
    )

    assert read_common_names(_source(path))[0].names == ("Orion Nebula",)


def test_read_common_names_reports_physical_file_line(tmp_path: Path):
    path = tmp_path / "common_names.csv"
    _write_rows(path, _row(designation="not a designation"))

    with pytest.raises(ValueError, match="common-names row 3"):
        read_common_names(_source(path))


def test_read_common_names_allows_moving_a_name(tmp_path: Path):
    path = tmp_path / "common_names.csv"
    _write_rows(
        path,
        _row(action="remove", rank="", sources=""),
        _row("M 31", "Orion Nebula"),
    )

    listed = read_common_names(_source(path))

    assert listed[0].removals == frozenset({"orion nebula"})
    assert listed[1].names == ("Orion Nebula",)


def test_catalog_names_split_on_load(db, catalogs_root, nightcrate_dir):
    _write_rows(nightcrate_dir / "common_names.csv")

    load_catalogs(db, catalogs_root)

    assert _names(db, "M 42") == ("Orion Nebula", 0, ("Great Orion Nebula",))


def test_list_orders_adds_and_removes(db, catalogs_root, nightcrate_dir):
    _append_openngc(
        catalogs_root / "openngc" / "NGC.csv",
        Name="NGC0650",
        Type="PN",
        M="076",
        **{"Common names": "Fixture Wrong,Barbell Nebula,Cork Nebula"},
    )
    _write_rows(
        nightcrate_dir / "common_names.csv",
        _row("M 76", "Little Dumbbell Nebula"),
        _row("M 76", "Barbell Nebula", rank="2"),
        _row("M 76", "Cork Nebula", rank="3"),
        _row("M 76", "Fixture Wrong", action="remove", rank="", sources=""),
    )

    load_catalogs(db, catalogs_root)

    assert _names(db, "M 76") == (
        "Little Dumbbell Nebula",
        1,
        ("Barbell Nebula", "Cork Nebula"),
    )


def test_unlisting_writes_flag_zero(db, catalogs_root, nightcrate_dir):
    path = nightcrate_dir / "common_names.csv"
    _write_rows(path, _row())
    load_catalogs(db, catalogs_root)
    assert _names(db, "M 42") == ("Orion Nebula", 1, ("Great Orion Nebula",))

    _write_rows(path)
    load_catalogs(db, catalogs_root)

    assert _names(db, "M 42") == ("Orion Nebula", 0, ("Great Orion Nebula",))


def test_list_conflicting_designations_for_one_object(db, catalogs_root, nightcrate_dir, caplog):
    _append_openngc(
        catalogs_root / "openngc" / "NGC.csv",
        Name="NGC1952",
        Type="SNR",
        M="001",
        **{"Common names": "Catalog Wrong,Catalog Kept"},
    )
    _write_rows(
        nightcrate_dir / "common_names.csv",
        _row("M 1", "First Listed Name"),
        _row("NGC 1952", "Second Listed Name"),
        _row("NGC 1952", "Catalog Wrong", action="remove", rank="", sources=""),
    )

    with caplog.at_level("WARNING", logger="nightcrate.catalog_loader.reconcile"):
        load_catalogs(db, catalogs_root)

    assert _names(db, "M 1") == (
        "First Listed Name",
        1,
        ("Second Listed Name", "Catalog Kept"),
    )
    assert any("resolve to one object" in record.getMessage() for record in caplog.records)


def test_merged_entry_names_follow_catalog(db, catalogs_root, nightcrate_dir):
    _write_rows(nightcrate_dir / "common_names.csv")
    main = catalogs_root / "openngc" / "NGC.csv"
    addendum = catalogs_root / "openngc" / "addendum.csv"
    _append_openngc(main, Name="M901", Type="Dup", M="900", **{"Common names": "Chain"})
    _append_openngc(main, Name="M900", Type="Dup", M="042", **{"Common names": "Direct"})
    _append_openngc(
        addendum,
        Name="M902",
        Type="Dup",
        M="042",
        **{"Common names": "Addendum"},
    )
    with (nightcrate_dir / "melotte.csv").open("a", encoding="utf-8") as handle:
        handle.write("999,NGC 1976,,,,,Rule R Name,,test\n")
    vizier = catalogs_root / "vizier"
    vizier.mkdir()
    shutil.copy(FIXTURES / "vizier" / "mini_barnard.tsv", vizier / "barnard_VII_220.tsv")
    write_choice(catalogs_root, CatalogChoice(frozenset({"melotte"}), frozenset()))

    load_catalogs(db, catalogs_root)

    assert _names(db, "M 42") == (
        "Orion Nebula",
        0,
        ("Great Orion Nebula", "Chain", "Direct", "Addendum", "Rule R Name"),
    )
    assert _names(db, "B 33") == ("Horsehead Nebula", 0, ("Barnard Horsehead",))


def test_group_name_from_list(db, catalogs_root, nightcrate_dir):
    _write_rows(
        nightcrate_dir / "common_names.csv",
        _row("Arp 244", "Antennae Galaxies", target="group"),
    )
    _append_openngc(
        catalogs_root / "openngc" / "NGC.csv",
        Name="NGC4038",
        RA="12:01:52.8",
        Dec="-18:51:54",
        Identifiers="Arp 244",
    )
    _append_openngc(
        catalogs_root / "openngc" / "NGC.csv",
        Name="NGC4039",
        RA="12:01:53.8",
        Dec="-18:53:06",
    )
    vizier = catalogs_root / "vizier"
    vizier.mkdir()
    arp_path = vizier / "arp_VII_192.tsv"
    shutil.copy(FIXTURES / "vizier" / "mini_arp.tsv", arp_path)
    (vizier / "version.json").write_text(
        json.dumps({"files": {arp_path.name: {"sha256": file_sha256(arp_path)}}}),
        encoding="utf-8",
    )

    load_catalogs(db, catalogs_root)
    assert (
        db.execute("SELECT COUNT(*) FROM dso_group WHERE common_name IS NOT NULL").fetchone()[0]
        == 0
    )
    assert (
        db.execute("SELECT COUNT(*) FROM dso WHERE common_name='Antennae Galaxies'").fetchone()[0]
        == 0
    )

    write_choice(catalogs_root, CatalogChoice(frozenset({"arp"}), frozenset()))
    load_catalogs(db, catalogs_root)
    assert (
        db.execute(
            "SELECT common_name FROM dso_group WHERE catalog='arp' AND identifier='244'"
        ).fetchone()[0]
        == "Antennae Galaxies"
    )
    assert (
        db.execute("SELECT COUNT(*) FROM dso WHERE common_name='Antennae Galaxies'").fetchone()[0]
        == 0
    )

    write_choice(catalogs_root, CatalogChoice(frozenset(), frozenset({"arp"})))
    load_catalogs(db, catalogs_root)
    assert (
        db.execute(
            "SELECT COUNT(*) FROM dso_group WHERE catalog='arp' AND identifier='244'"
        ).fetchone()[0]
        == 0
    )
    assert (
        db.execute("SELECT COUNT(*) FROM dso WHERE common_name='Antennae Galaxies'").fetchone()[0]
        == 0
    )

    write_choice(catalogs_root, CatalogChoice(frozenset({"arp"}), frozenset()))
    load_catalogs(db, catalogs_root)
    assert (
        db.execute(
            "SELECT common_name FROM dso_group WHERE catalog='arp' AND identifier='244'"
        ).fetchone()[0]
        == "Antennae Galaxies"
    )


def test_list_names_follow_optional_catalog(db, catalogs_root, nightcrate_dir):
    _write_rows(nightcrate_dir / "common_names.csv", _row("LBN 437", "Gecko Nebula"))
    vizier = catalogs_root / "vizier"
    vizier.mkdir()
    lbn_path = vizier / "lbn_VII_9.tsv"
    shutil.copy(FIXTURES / "vizier" / "mini_lbn.tsv", lbn_path)
    (vizier / "version.json").write_text(
        json.dumps({"files": {lbn_path.name: {"sha256": file_sha256(lbn_path)}}}),
        encoding="utf-8",
    )

    load_catalogs(db, catalogs_root)
    assert (
        db.execute(
            "SELECT COUNT(*) FROM dso_designation WHERE catalog='lbn' AND identifier='437'"
        ).fetchone()[0]
        == 0
    )

    write_choice(catalogs_root, CatalogChoice(frozenset({"lbn"}), frozenset()))
    load_catalogs(db, catalogs_root)
    row = db.execute(
        """
        SELECT d.id, d.common_name, d.common_name_augmented
        FROM dso d JOIN dso_designation dd ON dd.dso_id=d.id
        WHERE dd.catalog='lbn' AND dd.identifier='437'
        """
    ).fetchone()
    assert tuple(row) == (row["id"], "Gecko Nebula", 1)
    dso_id = int(row["id"])
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (dso_id,))
    db.commit()

    write_choice(catalogs_root, CatalogChoice(frozenset(), frozenset({"lbn"})))
    load_catalogs(db, catalogs_root)
    assert tuple(
        db.execute(
            "SELECT active, common_name, common_name_augmented FROM dso WHERE id=?", (dso_id,)
        ).fetchone()
    ) == (0, "Gecko Nebula", 1)

    write_choice(catalogs_root, CatalogChoice(frozenset({"lbn"}), frozenset()))
    load_catalogs(db, catalogs_root)
    assert tuple(
        db.execute(
            "SELECT active, common_name, common_name_augmented FROM dso WHERE id=?", (dso_id,)
        ).fetchone()
    ) == (1, "Gecko Nebula", 1)


def test_shipped_common_names_valid(catalogs_root):
    source = next(
        source
        for source in get_sources(catalogs_root)
        if source.source_id == "nightcrate_common_names"
    )

    assert read_common_names(source)


def test_second_load_runs_no_object_step(db, catalogs_root, nightcrate_dir, monkeypatch):
    from nightcrate.catalog_loader import reconcile

    _write_rows(nightcrate_dir / "common_names.csv", _row())
    real_apply = reconcile.apply_object_set
    calls = 0

    def recording_apply(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real_apply(*args, **kwargs)

    monkeypatch.setattr(reconcile, "apply_object_set", recording_apply)
    first = load_catalogs(db, catalogs_root)
    first_calls = calls
    second = load_catalogs(db, catalogs_root)

    assert first_calls == 1
    assert calls == 1
    assert all(result.status != "failed" for result in first.results)
    assert all(result.status != "failed" for result in second.results)
