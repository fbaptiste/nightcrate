"""Wolf-Rayet catalog collection and lifecycle tests."""

from __future__ import annotations

import json
import logging
import shutil
import sqlite3
from pathlib import Path

import pytest

from nightcrate.catalog_loader import load_catalogs, registry
from nightcrate.catalog_loader._common import clean_tex_name
from nightcrate.catalog_loader.catalog_choice import (
    read_choice,
    with_added,
    with_removed,
    write_choice,
)
from nightcrate.catalog_loader.designations import normalize_designation
from nightcrate.catalog_loader.hash import file_sha256
from nightcrate.catalog_loader.reconcile import build_object_set
from nightcrate.catalog_loader.wr_loader import collect_wr

FIXTURES = Path(__file__).parent.parent / "fixtures" / "catalogs"


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
    paths = (
        ("wr_III_215_table13.tsv", "mini_wr.tsv"),
        ("wr_III_215_table15.tsv", "mini_wr_phot.tsv"),
    )
    for destination, fixture in paths:
        shutil.copy(FIXTURES / "vizier" / fixture, vizier / destination)
    if installed:
        version = {
            "files": {
                filename: {
                    "sha256": file_sha256(vizier / filename),
                    "fetch_date": "2026-11-02T00:00:00+00:00",
                }
                for filename, _fixture in paths
            }
        }
        (vizier / "version.json").write_text(json.dumps(version), encoding="utf-8")
    return root


def _sources(root: Path):
    return {source.source_id: source for source in registry.get_sources(root)}


def _wr_batch(root: Path):
    sources = _sources(root)
    return collect_wr(
        {source_id: sources[source_id] for source_id in ("vizier_wr", "vizier_wr_phot")},
        frozenset({"wr"}),
    )


def _append_modified_row(
    path: Path, identifier_column: int, identifier: str, updates: dict[int, str]
) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    fields = next(
        line.split("\t")
        for line in lines
        if len(line.split("\t")) > identifier_column
        and line.split("\t")[identifier_column].strip() == identifier
    )
    for column, value in updates.items():
        fields[column] = value
    path.write_text("\n".join((*lines, "\t".join(fields), "")), encoding="utf-8")


def _remove_row(path: Path, identifier_column: int, identifier: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    kept = []
    for line in lines:
        fields = line.split("\t")
        is_target = (
            len(fields) > identifier_column and fields[identifier_column].strip() == identifier
        )
        if not is_target:
            kept.append(line)
    path.write_text("\n".join((*kept, "")), encoding="utf-8")


def test_wr_registry_projects_used_columns_and_omits_table15_coordinates():
    catalog = registry.optional_catalog("wr")

    assert catalog is not None
    assert catalog.display_name == "Wolf-Rayet stars"
    assert catalog.legacy_default is False
    positions, photometry = catalog.fetch_specs
    assert positions.required_columns == ("_RAJ2000", "_DEJ2000", "WR", "Name")
    assert positions.additional_params == {"-out.add": "_RAJ2000,_DEJ2000"}
    assert photometry.required_columns == ("WR", "vmag", "SpType")
    assert photometry.additional_params == {}


def test_wr_and_hh_credits_match_the_supplied_readmes(tmp_path: Path):
    sources = _sources(_catalogs_root(tmp_path))
    wr = registry.optional_catalog("wr")
    hh = registry.optional_catalog("hh")

    assert wr is not None and hh is not None
    assert wr.credit == "van der Hucht 2001. Retrieved via VizieR III/215."
    assert {spec.citation for spec in wr.fetch_specs} == {registry.WR_CITATION}
    assert sources["vizier_wr"].attribution == registry.WR_CITATION
    assert sources["vizier_wr_phot"].attribution == registry.WR_CITATION
    for required in (
        "van der Hucht, K.A. 2001",
        "The Seventh Catalogue of Galactic Wolf-Rayet stars",
        "New Astronomy Reviews 45, 135",
        "(VizieR III/215)",
        registry.CDS_CITATION,
    ):
        assert required in sources["vizier_wr"].attribution

    assert hh.credit == "Reipurth 1999. Retrieved via VizieR V/104."
    assert hh.fetch_specs[0].citation == registry.HH_CITATION
    assert sources["vizier_hh"].attribution == registry.HH_CITATION
    for required in (
        "Reipurth, B.: 1999",
        "A general catalogue of Herbig-Haro objects, 2. edition",
        "http://casa.colorado.edu/hhcat",
        "(VizieR V/104)",
        registry.CDS_CITATION,
    ):
        assert required in sources["vizier_hh"].attribution


def test_collect_wr_joins_photometry_into_notes_and_keeps_vmag_missing(tmp_path: Path):
    rows = {row.source_key: row for row in _wr_batch(_catalogs_root(tmp_path)).objects}

    assert set(rows) == {"11", "101a", "134", "136"}
    assert rows["11"].columns["openngc_notes"] == (
        "Narrow-band v 1.74 · WC8+O7.5III-V · Also γ² Vel"
    )
    assert rows["134"].columns["openngc_notes"] == "Narrow-band v 8.23 · WN6"
    assert rows["136"].columns["openngc_notes"] == "Narrow-band v 7.65 · WN6(h)"
    assert rows["101a"].columns["openngc_notes"] == "WC9 · Also BSD 1"
    assert all(row.columns["mag_v"] is None for row in rows.values())
    assert all(row.columns["obj_type"] == "WR*" for row in rows.values())


def test_collect_wr_counts_and_skips_unpaired_photometry(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    caplog.set_level(logging.INFO, logger="nightcrate.catalog_loader.wr")

    batch = _wr_batch(_catalogs_root(tmp_path))

    assert len(batch.objects) == 4
    assert "skipped 1 table15 rows without a table13 partner" in caplog.text
    assert "kept 0 table13 rows without table15 photometry" in caplog.text


def test_collect_wr_duplicates_in_both_tables_keep_first_rows(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    root = _catalogs_root(tmp_path)
    _append_modified_row(root / "vizier" / "wr_III_215_table13.tsv", 4, "134", {5: "Later Name"})
    _append_modified_row(
        root / "vizier" / "wr_III_215_table15.tsv",
        1,
        "134",
        {3: "LATE", 6: "99.99"},
    )
    caplog.set_level(logging.WARNING, logger="nightcrate.catalog_loader.wr")

    rows = {row.source_key: row for row in _wr_batch(root).objects}

    assert len(rows) == 4
    assert rows["134"].columns["openngc_notes"] == "Narrow-band v 8.23 · WN6"
    assert "duplicate WR id 134 in table13; keeping first row" in caplog.text
    assert "duplicate WR id 134 in table15; keeping first row" in caplog.text


def test_collect_wr_keeps_table13_only_row_without_photometry(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    root = _catalogs_root(tmp_path)
    _remove_row(root / "vizier" / "wr_III_215_table15.tsv", 1, "101a")
    caplog.set_level(logging.INFO, logger="nightcrate.catalog_loader.wr")

    rows = {row.source_key: row for row in _wr_batch(root).objects}

    assert rows["101a"].columns["openngc_notes"] == "Also BSD 1"
    assert "skipped 1 table15 rows without a table13 partner" in caplog.text
    assert "kept 1 table13 rows without table15 photometry" in caplog.text


@pytest.mark.parametrize(
    ("name", "symbol"),
    (
        ("alpha", "α"),
        ("beta", "β"),
        ("gamma", "γ"),
        ("delta", "δ"),
        ("epsilon", "ε"),
        ("zeta", "ζ"),
        ("eta", "η"),
        ("theta", "θ"),
        ("iota", "ι"),
        ("kappa", "κ"),
        ("lambda", "λ"),
        ("mu", "μ"),
        ("nu", "ν"),
        ("xi", "ξ"),
        ("pi", "π"),
        ("rho", "ρ"),
        ("sigma", "σ"),
        ("tau", "τ"),
        ("upsilon", "υ"),
        ("phi", "φ"),
        ("chi", "χ"),
        ("psi", "ψ"),
        ("omega", "ω"),
    ),
)
def test_clean_tex_name_maps_catalog_greek_placeholders(name: str, symbol: str):
    assert clean_tex_name(f"A{{{name}}} B") == f"A{symbol} B"


def test_clean_tex_name_maps_bare_lowercase_greek_and_superscripts_without_changing_tau():
    assert clean_tex_name("gamma^20 Vel") == "γ²⁰ Vel"
    assert clean_tex_name("theta Mus") == "θ Mus"
    assert clean_tex_name("HL Tau H{alpha} jet") == "HL Tau Hα jet"
    assert clean_tex_name("A{unknown}  B") == "Aunknown  B"


def test_wr_101a_and_uppercase_query_share_a_search_key(tmp_path: Path):
    row = next(
        row for row in _wr_batch(_catalogs_root(tmp_path)).objects if row.source_key == "101a"
    )

    assert row.identifier == "101a"
    assert normalize_designation("WR 101a") == normalize_designation("WR 101A")


def test_wr_reconcile_keeps_fixture_rows_standalone_without_groups(tmp_path: Path):
    root = _catalogs_root(tmp_path)
    built = build_object_set(_sources(root), None, frozenset({"wr"}))
    wr_objects = [obj for obj in built.objects if obj.source_id == "vizier_wr"]

    assert len(wr_objects) == 4
    assert not any(source_id == "vizier_wr" for source_id, _source_key in built.merges)
    assert {obj.designations for obj in wr_objects} == {
        (("wr", "101a", True),),
        (("wr", "11", True),),
        (("wr", "134", True),),
        (("wr", "136", True),),
    }
    assert built.groups == ()
    assert built.stated_matches == ()


def test_wr_load_remove_and_add_reactivates_linked_object(db: sqlite3.Connection, tmp_path: Path):
    root = _catalogs_root(tmp_path, installed=True)
    write_choice(root, with_added(None, "wr"))
    load_catalogs(db, root)
    row = db.execute(
        "SELECT d.id FROM dso d JOIN dso_designation dd ON dd.dso_id=d.id "
        "WHERE dd.catalog='wr' AND dd.identifier='134'"
    ).fetchone()
    assert row is not None
    dso_id = int(row[0])
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (dso_id,))
    db.commit()

    write_choice(root, with_removed(read_choice(root), "wr"))
    load_catalogs(db, root)
    assert db.execute("SELECT active FROM dso WHERE id=?", (dso_id,)).fetchone()[0] == 0
    assert (
        db.execute(
            "SELECT display_form FROM dso_designation WHERE dso_id=? AND catalog='wr'", (dso_id,)
        ).fetchone()[0]
        == "WR 134"
    )

    write_choice(root, with_added(read_choice(root), "wr"))
    load_catalogs(db, root)
    assert tuple(db.execute("SELECT id, active FROM dso WHERE id=?", (dso_id,)).fetchone()) == (
        dso_id,
        1,
    )
