"""Persisted invalidation and missing-file orchestration regressions."""

from __future__ import annotations

import csv
import shutil
import sqlite3
from pathlib import Path

import pytest

from nightcrate.catalog_loader import load_catalogs, registry
from nightcrate.catalog_loader.loader import (
    LEGACY_OTHER_NAMES,
    SourceResult,
    _fused_pgc_repair_due,
)

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


def _append_openngc_names(path: Path, names: tuple[str, ...]) -> None:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        fieldnames = reader.fieldnames
        assert fieldnames is not None
        rows = list(reader)
    for index, name in enumerate(names):
        row = dict.fromkeys(fieldnames, "")
        row.update(
            {
                "Name": name,
                "Type": "OCl",
                "RA": f"00:{index:02d}:00",
                "Dec": "+10:00:00",
                "Const": "Psc",
            }
        )
        rows.append(row)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def _append_openngc_rows(path: Path, rows: tuple[dict[str, str], ...]) -> None:
    with path.open(encoding="utf-8", newline="") as stream:
        fieldnames = csv.DictReader(stream, delimiter=";").fieldnames
    assert fieldnames is not None
    with path.open("a", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter=";")
        for values in rows:
            row = dict.fromkeys(fieldnames, "")
            row.update(
                {
                    "Type": "G",
                    "RA": "01:00:00",
                    "Dec": "+01:00:00",
                    "Const": "Psc",
                    **values,
                }
            )
            writer.writerow(row)


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


def test_legacy_other_name_repair_runs_on_unchanged_hash_and_preserves_identity(
    db, catalogs_root, monkeypatch
):
    addendum = catalogs_root / "openngc" / "addendum.csv"
    _append_openngc_names(addendum, LEGACY_OTHER_NAMES)
    load_catalogs(db, catalogs_root)

    placeholders = ",".join("?" for _ in LEGACY_OTHER_NAMES)
    before = {
        row["source_key"]: row["id"]
        for row in db.execute(
            f"SELECT id, source_key FROM dso WHERE source_key IN ({placeholders})",  # nosec B608
            LEGACY_OTHER_NAMES,
        )
    }
    assert set(before) == set(LEGACY_OTHER_NAMES)
    linked_id = before["H05"]
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (linked_id,))
    db.execute(
        f"""
        UPDATE dso SET primary_designation = 'OTHER ' || source_key
        WHERE source_key IN ({placeholders})
        """,  # nosec B608
        LEGACY_OTHER_NAMES,
    )
    db.execute(
        "DELETE FROM dso_designation WHERE dso_id IN (?, ?) AND catalog = 'hickson'",
        (before["HCG092"], before["HCG079"]),
    )
    db.commit()

    summary = load_catalogs(db, catalogs_root)

    expected = {
        "HCG092": "HCG 92",
        "HCG079": "HCG 79",
        "H05": "H 5",
        "H13": "H 13",
        "H20": "H 20",
        "H21": "H 21",
        "MWSC3156": "MWSC 3156",
        "MWSC3171": "MWSC 3171",
        "MWSC3561": "MWSC 3561",
    }
    repaired = {
        row["source_key"]: (row["id"], row["primary_designation"])
        for row in db.execute(
            f"""
            SELECT id, source_key, primary_designation
            FROM dso WHERE source_key IN ({placeholders})
            """,  # nosec B608
            LEGACY_OTHER_NAMES,
        )
    }
    assert repaired == {key: (before[key], value) for key, value in expected.items()}
    assert db.execute("SELECT dso_id FROM favorite_target").fetchone()[0] == linked_id
    hickson_rows = db.execute(
        """
        SELECT d.source_key, dd.identifier, dd.display_form
        FROM dso d JOIN dso_designation dd ON dd.dso_id = d.id
        WHERE d.source_key IN ('HCG092', 'HCG079') AND dd.catalog = 'hickson'
        ORDER BY d.source_key
        """
    ).fetchall()
    assert [tuple(row) for row in hickson_rows] == [
        ("HCG079", "79", "HCG 79"),
        ("HCG092", "92", "HCG 92"),
    ]
    assert next(row for row in summary.results if row.source_id == "openngc_addendum").status == (
        "loaded"
    )

    def unexpected(*_args, **_kwargs):
        raise AssertionError("idempotent repair repeated")

    monkeypatch.setattr("nightcrate.catalog_loader.reconcile.apply_object_set", unexpected)
    repeat = load_catalogs(db, catalogs_root)
    assert next(row for row in repeat.results if row.source_id == "openngc_addendum").status == (
        "unchanged"
    )


def test_legacy_other_name_repair_keeps_missing_source_deferral(db, catalogs_root):
    addendum = catalogs_root / "openngc" / "addendum.csv"
    _append_openngc_names(addendum, ("H05",))
    load_catalogs(db, catalogs_root)
    db.execute("UPDATE dso SET primary_designation = 'OTHER H05' WHERE source_key = 'H05'")
    db.commit()
    addendum.unlink()

    summary = load_catalogs(db, catalogs_root)

    assert (
        db.execute("SELECT primary_designation FROM dso WHERE source_key = 'H05'").fetchone()[0]
        == "OTHER H05"
    )
    result = next(row for row in summary.results if row.source_id == "openngc_addendum")
    assert result.status == "skipped"
    assert "addendum.csv" in (result.error or "")


def test_fused_pgc_repair_preserves_identity_and_is_idempotent(db, catalogs_root, monkeypatch):
    ngc = catalogs_root / "openngc" / "NGC.csv"
    cases = {
        "IC1166 NED01": ("56771", "056771", "SDSS J160208.91+261945.5"),
        "IC1191 NED01": ("57152", "057152", "SDSS J160628.98+181603.9"),
    }
    _append_openngc_rows(
        ngc,
        tuple(
            {
                "Name": source_key,
                "Identifiers": f"PGC {raw_pgc}{sdss}",
            }
            for source_key, (_pgc, raw_pgc, sdss) in cases.items()
        ),
    )
    load_catalogs(db, catalogs_root)
    before = {
        row["source_key"]: row["id"]
        for row in db.execute(
            "SELECT id, source_key FROM dso WHERE source_key IN ('IC1166 NED01', 'IC1191 NED01')"
        )
    }
    assert set(before) == set(cases)

    for source_key, (_pgc, raw_pgc, sdss) in cases.items():
        dso_id = before[source_key]
        db.execute(
            "DELETE FROM dso_designation WHERE dso_id = ? AND catalog = 'pgc'",
            (dso_id,),
        )
        malformed = f"{raw_pgc}{sdss}"
        db.execute(
            """
            INSERT INTO dso_designation
                (dso_id, catalog, identifier, display_form, search_key, is_primary)
            VALUES (?, 'pgc', ?, ?, ?, 0)
            """,
            (dso_id, malformed, f"PGC {malformed}", f"pgc{malformed}"),
        )
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (before["IC1166 NED01"],))
    db.execute("INSERT INTO project (name) VALUES ('Fused PGC repair')")
    project_id = int(db.execute("SELECT last_insert_rowid()").fetchone()[0])
    db.execute(
        "INSERT INTO project_target (project_id, dso_id) VALUES (?, ?)",
        (project_id, before["IC1191 NED01"]),
    )
    db.commit()

    statements: list[str] = []
    db.set_trace_callback(statements.append)
    try:
        assert _fused_pgc_repair_due(db.cursor()) is True
    finally:
        db.set_trace_callback(None)
    designation_queries = [
        statement.casefold()
        for statement in statements
        if "dso_designation" in statement.casefold()
    ]
    assert designation_queries
    assert all(" where " in query for query in designation_queries)
    assert not any("join dso_designation" in query for query in designation_queries)

    summary = load_catalogs(db, catalogs_root)

    after = {
        row["source_key"]: row["id"]
        for row in db.execute(
            "SELECT id, source_key FROM dso WHERE source_key IN ('IC1166 NED01', 'IC1191 NED01')"
        )
    }
    assert after == before
    repaired = [
        tuple(row)
        for row in db.execute(
            """
            SELECT d.source_key, dd.identifier, dd.display_form
            FROM dso d JOIN dso_designation dd ON dd.dso_id = d.id
            WHERE d.source_key IN ('IC1166 NED01', 'IC1191 NED01')
              AND dd.catalog = 'pgc'
            ORDER BY d.source_key
            """
        )
    ]
    assert repaired == [
        ("IC1166 NED01", "56771", "PGC 56771"),
        ("IC1191 NED01", "57152", "PGC 57152"),
    ]
    assert (
        db.execute("SELECT raw_other_id FROM dso WHERE source_key = 'IC1166 NED01'").fetchone()[0]
        == "PGC 056771SDSS J160208.91+261945.5"
    )
    assert db.execute("SELECT dso_id FROM favorite_target").fetchone()[0] == before["IC1166 NED01"]
    assert db.execute("SELECT dso_id FROM project_target").fetchone()[0] == before["IC1191 NED01"]
    assert next(row for row in summary.results if row.source_id == "openngc").status == "loaded"

    def unexpected(*_args, **_kwargs):
        raise AssertionError("idempotent fused-PGC repair repeated")

    monkeypatch.setattr("nightcrate.catalog_loader.reconcile.apply_object_set", unexpected)
    repeat = load_catalogs(db, catalogs_root)
    assert next(row for row in repeat.results if row.source_id == "openngc").status == "unchanged"


def test_own_name_ownership_repairs_on_unchanged_hash_and_is_idempotent(
    db, catalogs_root, monkeypatch
):
    ngc = catalogs_root / "openngc" / "NGC.csv"
    _append_openngc_rows(
        ngc,
        (
            {"Name": "NGC0755", "NGC": "0764"},
            {"Name": "NGC0764"},
            {"Name": "NGC6838", "NGC": "6839", "M": "071"},
            {"Name": "NGC6839"},
        ),
    )
    load_catalogs(db, catalogs_root)
    ids = {
        row["source_key"]: row["id"]
        for row in db.execute(
            "SELECT id, source_key FROM dso WHERE source_key IN "
            "('NGC0755', 'NGC0764', 'NGC6838', 'NGC6839')"
        )
    }
    db.execute("DELETE FROM dso_designation WHERE catalog='ngc' AND identifier IN ('764','6839')")
    db.executemany(
        """
        INSERT INTO dso_designation
            (dso_id, catalog, identifier, display_form, search_key, is_primary)
        VALUES (?, 'ngc', ?, ?, ?, 0)
        """,
        (
            (ids["NGC0755"], "764", "NGC 764", "ngc764"),
            (ids["NGC6838"], "6839", "NGC 6839", "ngc6839"),
        ),
    )
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (ids["NGC0755"],))
    db.execute("INSERT INTO project (name) VALUES ('Own names')")
    project_id = int(db.execute("SELECT last_insert_rowid()").fetchone()[0])
    db.execute(
        "INSERT INTO project_target (project_id, dso_id) VALUES (?, ?)",
        (project_id, ids["NGC0764"]),
    )
    db.commit()

    summary = load_catalogs(db, catalogs_root)

    owners = {
        row["identifier"]: row["dso_id"]
        for row in db.execute(
            "SELECT identifier, dso_id FROM dso_designation "
            "WHERE catalog='ngc' AND identifier IN ('764','6839')"
        )
    }
    assert owners == {"764": ids["NGC0764"], "6839": ids["NGC6839"]}
    assert db.execute("SELECT dso_id FROM favorite_target").fetchone()[0] == ids["NGC0755"]
    assert db.execute("SELECT dso_id FROM project_target").fetchone()[0] == ids["NGC0764"]
    assert next(row for row in summary.results if row.source_id == "openngc").status == "loaded"

    def unexpected(*_args, **_kwargs):
        raise AssertionError("idempotent ownership repair repeated")

    monkeypatch.setattr("nightcrate.catalog_loader.reconcile.apply_object_set", unexpected)
    repeat = load_catalogs(db, catalogs_root)
    assert next(row for row in repeat.results if row.source_id == "openngc").status == "unchanged"


def test_false_primary_repairs_on_unchanged_hash_and_preserves_user_links(
    db, catalogs_root, monkeypatch
):
    ngc = catalogs_root / "openngc" / "NGC.csv"
    _append_openngc_rows(
        ngc,
        (
            {"Name": "IC0001", "NGC": "0764"},
            {"Name": "NGC0764"},
        ),
    )
    load_catalogs(db, catalogs_root)
    ids = {
        row["source_key"]: row["id"]
        for row in db.execute(
            "SELECT id, source_key FROM dso WHERE source_key IN ('IC0001', 'NGC0764')"
        )
    }
    db.execute(
        "UPDATE dso SET primary_designation='NGC 764' WHERE id=?",
        (ids["IC0001"],),
    )
    db.execute(
        "UPDATE dso_designation SET is_primary=0 WHERE dso_id=?",
        (ids["IC0001"],),
    )
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (ids["IC0001"],))
    db.execute("INSERT INTO project (name) VALUES ('Primary repair')")
    project_id = int(db.execute("SELECT last_insert_rowid()").fetchone()[0])
    db.execute(
        "INSERT INTO project_target (project_id, dso_id) VALUES (?, ?)",
        (project_id, ids["NGC0764"]),
    )
    db.commit()

    summary = load_catalogs(db, catalogs_root)

    repaired = db.execute(
        "SELECT id, primary_designation FROM dso WHERE source_key='IC0001'"
    ).fetchone()
    assert tuple(repaired) == (ids["IC0001"], "IC 1")
    assert [
        tuple(row)
        for row in db.execute(
            "SELECT catalog, identifier FROM dso_designation WHERE dso_id=? AND is_primary=1",
            (ids["IC0001"],),
        )
    ] == [("ic", "1")]
    assert db.execute("SELECT dso_id FROM favorite_target").fetchone()[0] == ids["IC0001"]
    assert db.execute("SELECT dso_id FROM project_target").fetchone()[0] == ids["NGC0764"]
    assert next(row for row in summary.results if row.source_id == "openngc").status == "loaded"

    def unexpected(*_args, **_kwargs):
        raise AssertionError("idempotent primary repair repeated")

    monkeypatch.setattr("nightcrate.catalog_loader.reconcile.apply_object_set", unexpected)
    repeat = load_catalogs(db, catalogs_root)
    assert next(row for row in repeat.results if row.source_id == "openngc").status == "unchanged"


def test_barnard_merge_repairs_on_unchanged_hash_without_sharpless(db, catalogs_root, monkeypatch):
    vizier = catalogs_root / "vizier"
    vizier.mkdir()
    shutil.copy(FIXTURES / "vizier" / "mini_barnard.tsv", vizier / "barnard_VII_220.tsv")
    load_catalogs(db, catalogs_root)
    survivor_id = int(db.execute("SELECT id FROM dso WHERE source_key='B033'").fetchone()[0])
    source_id = int(
        db.execute("SELECT id FROM dso_catalog_source WHERE source_id='vizier_barnard'").fetchone()[
            0
        ]
    )
    db.execute(
        """
        INSERT INTO dso
            (primary_designation, obj_type, source_catalog_id, source_row_hash, source_key)
        VALUES ('B 33', 'DrkN', ?, 'legacy-barnard-33', '33')
        """,
        (source_id,),
    )
    old_id = int(db.execute("SELECT last_insert_rowid()").fetchone()[0])
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (old_id,))
    db.commit()

    summary = load_catalogs(db, catalogs_root)

    assert db.execute("SELECT COUNT(*) FROM dso WHERE id=?", (old_id,)).fetchone()[0] == 0
    assert db.execute("SELECT dso_id FROM favorite_target").fetchone()[0] == survivor_id
    assert next(row for row in summary.results if row.source_id == "vizier_barnard").status == (
        "loaded"
    )

    def unexpected(*_args, **_kwargs):
        raise AssertionError("idempotent Barnard repair repeated")

    monkeypatch.setattr("nightcrate.catalog_loader.reconcile.apply_object_set", unexpected)
    repeat = load_catalogs(db, catalogs_root)
    assert next(row for row in repeat.results if row.source_id == "vizier_barnard").status == (
        "unchanged"
    )


def test_barnard_merge_repair_keeps_missing_source_deferral(db, catalogs_root):
    vizier = catalogs_root / "vizier"
    vizier.mkdir()
    barnard = vizier / "barnard_VII_220.tsv"
    shutil.copy(FIXTURES / "vizier" / "mini_barnard.tsv", barnard)
    load_catalogs(db, catalogs_root)
    source_id = int(
        db.execute("SELECT id FROM dso_catalog_source WHERE source_id='vizier_barnard'").fetchone()[
            0
        ]
    )
    db.execute(
        """
        INSERT INTO dso
            (primary_designation, obj_type, source_catalog_id, source_row_hash, source_key)
        VALUES ('B 33', 'DrkN', ?, 'legacy-barnard-33', '33')
        """,
        (source_id,),
    )
    old_id = int(db.execute("SELECT last_insert_rowid()").fetchone()[0])
    db.commit()
    barnard.unlink()

    summary = load_catalogs(db, catalogs_root)

    assert db.execute("SELECT active FROM dso WHERE id=?", (old_id,)).fetchone()[0] == 1
    result = next(row for row in summary.results if row.source_id == "vizier_barnard")
    assert result.status == "skipped"
    assert "barnard_VII_220.tsv" in (result.error or "")


def test_changed_sharpless_crossref_merges_existing_standalone(
    db, catalogs_root, monkeypatch, tmp_path
):
    isolated = tmp_path / "nightcrate"
    package_data = Path(registry.__file__).parent.parent / "data" / "catalogs" / "nightcrate"
    shutil.copytree(package_data, isolated)
    crossref = isolated / "sharpless_crossref.csv"
    crossref.write_text(
        "\n".join(
            line
            for line in crossref.read_text(encoding="utf-8").splitlines()
            if not line.startswith("155,")
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(registry, "_nightcrate_dir", lambda: isolated)
    _append_openngc_rows(
        catalogs_root / "openngc" / "addendum.csv",
        ({"Name": "C009", "Type": "DrkN", "Common names": "Cave Nebula"},),
    )
    vizier = catalogs_root / "vizier"
    vizier.mkdir()
    shutil.copy(FIXTURES / "vizier" / "mini_sharpless.tsv", vizier / "sharpless_VII_20.tsv")
    load_catalogs(db, catalogs_root)
    standalone_id = int(
        db.execute("SELECT id FROM dso WHERE primary_designation='Sh2-155'").fetchone()[0]
    )
    survivor_id = int(db.execute("SELECT id FROM dso WHERE source_key='C009'").fetchone()[0])
    with crossref.open("a", encoding="utf-8") as stream:
        stream.write("155,C 9,Cave Nebula / Caldwell 9\n")

    summary = load_catalogs(db, catalogs_root)

    assert db.execute("SELECT COUNT(*) FROM dso WHERE id=?", (standalone_id,)).fetchone()[0] == 0
    assert (
        db.execute(
            "SELECT dso_id FROM dso_designation WHERE catalog='sharpless2' AND identifier='155'"
        ).fetchone()[0]
        == survivor_id
    )
    assert next(row for row in summary.results if row.source_id == "vizier_sharpless").status == (
        "loaded"
    )
    repeat = load_catalogs(db, catalogs_root)
    assert next(row for row in repeat.results if row.source_id == "vizier_sharpless").status == (
        "unchanged"
    )


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
