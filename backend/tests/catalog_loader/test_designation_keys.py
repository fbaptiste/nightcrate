"""Structured designation normalization and repair regressions."""

from __future__ import annotations

import csv
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

from nightcrate.catalog_loader import load_catalogs
from nightcrate.catalog_loader.designations import (
    canonical_identifier,
    designation_search_prefixes,
    normalize_designation,
)
from nightcrate.catalog_loader.loader import _designation_canon_due

FIXTURES = Path(__file__).parent.parent / "fixtures" / "catalogs"


def test_loader_modules_import_in_fresh_process():
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-c",
            "import nightcrate.catalog_loader.crossref_parser, nightcrate.catalog_loader.loader",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_structured_designation_keys_preserve_signs():
    assert {
        normalize_designation("PN G000.0+02.0"),
        normalize_designation("PN G0.0+2.0"),
        normalize_designation("PNG 000.0+02.0"),
    } == {"png000.0+02.0"}
    assert normalize_designation("PN G000.0+02.0") != normalize_designation("PN G000.0-02.0")
    assert {
        normalize_designation("MCG-02-05-50"),
        normalize_designation("MCG-02-05-050"),
        normalize_designation("MCG -02-05-050"),
    } == {"mcg-02-05-050"}
    assert normalize_designation("MCG+02-05-050") != normalize_designation("MCG-02-05-050")
    assert normalize_designation("MCG 07-28-004") == normalize_designation("MCG +07-28-004")
    assert normalize_designation("MCG 07-28-004") != normalize_designation("MCG -07-28-004")
    assert normalize_designation("MCG 0-1-4") == normalize_designation("MCG +00-01-004")


def test_existing_designation_keys_are_unchanged():
    assert normalize_designation("M 42") == "m42"
    assert normalize_designation("messier 42") == "m42"
    assert normalize_designation("NGC 1976") == "ngc1976"
    assert normalize_designation("Sh2-281") == "sh2281"
    assert normalize_designation("B 33") == "b33"
    assert normalize_designation("ruprecht 147") == "ru147"
    assert normalize_designation("dolidze 25") == "do25"


def test_partial_structured_designations_include_padded_search_prefixes():
    assert designation_search_prefixes("MCG-1-2") == [
        "mcg-1-2",
        "mcg-01-2",
        "mcg-01-02",
    ]
    assert designation_search_prefixes("MCG-1") == ["mcg-1", "mcg-01"]
    assert designation_search_prefixes("PN G 10.8") == ["png10.8", "png010.8"]
    assert designation_search_prefixes("PN G 10") == ["png10", "png010"]
    assert designation_search_prefixes("NGC 70") == ["ngc70"]


def test_canonical_identifiers():
    assert canonical_identifier("mcg", "-2-5-50A") == "-02-05-050a"
    assert canonical_identifier("mcg", "2-5-50A") == "+02-05-050a"
    assert canonical_identifier("png", "0.0+2.0") == "000.0+02.0"
    assert canonical_identifier("wr", "0101A") == "101a"
    assert canonical_identifier("ngc", "001") == "001"


def test_long_catalog_names():
    assert normalize_designation("Melotte 25") == "mel25"
    assert normalize_designation("Collinder 399") == "cr399"
    assert normalize_designation("Herbig-Haro 46") == "hh46"
    assert normalize_designation("Wolf-Rayet 134") == "wr134"
    assert normalize_designation("Wolf-Rayet 101A") == normalize_designation("WR 101a")


def test_openngc_structured_names_load_and_repair(tmp_path: Path):
    catalogs_root = tmp_path / "catalogs"
    openngc = catalogs_root / "openngc"
    openngc.mkdir(parents=True)
    shutil.copy(FIXTURES / "openngc" / "mini_NGC.csv", openngc / "NGC.csv")
    shutil.copy(FIXTURES / "openngc" / "mini_addendum.csv", openngc / "addendum.csv")
    with (openngc / "addendum.csv").open(encoding="utf-8", newline="") as stream:
        fieldnames = csv.DictReader(stream, delimiter=";").fieldnames
    assert fieldnames is not None
    with (openngc / "addendum.csv").open("a", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter=";")
        row = dict.fromkeys(fieldnames, "")
        row.update(
            {
                "Name": "IC9998",
                "Type": "PN",
                "RA": "01:00:00",
                "Dec": "+01:00:00",
                "Const": "Psc",
                "Identifiers": "PN G010.1+00.7, MCG-07-28-004",
            }
        )
        writer.writerow(row)

    db = sqlite3.connect(tmp_path / "test.db")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        load_catalogs(db, catalogs_root)
        dso_id = int(db.execute("SELECT id FROM dso WHERE source_key='IC9998'").fetchone()[0])
        designations = {
            (str(row["catalog"]), str(row["identifier"]), str(row["search_key"]))
            for row in db.execute(
                "SELECT catalog,identifier,search_key FROM dso_designation WHERE dso_id=?",
                (dso_id,),
            )
        }
        assert ("png", "010.1+00.7", "png010.1+00.7") in designations
        assert ("mcg", "-07-28-004", "mcg-07-28-004") in designations

        db.execute(
            """
            UPDATE dso_designation
            SET identifier='07-28-004', display_form='MCG 07-28-004',
                search_key='mcg0728004'
            WHERE dso_id=? AND catalog='mcg'
            """,
            (dso_id,),
        )
        db.commit()
        assert _designation_canon_due(db.cursor())

        load_catalogs(db, catalogs_root)
        repaired = db.execute(
            """
            SELECT identifier,display_form,search_key
            FROM dso_designation WHERE dso_id=? AND catalog='mcg'
            """,
            (dso_id,),
        ).fetchone()
        assert tuple(repaired) == ("-07-28-004", "MCG -07-28-004", "mcg-07-28-004")
        assert not _designation_canon_due(db.cursor())
    finally:
        db.close()
