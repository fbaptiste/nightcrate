"""ACO galaxy-cluster collection, reconciliation, fetch, and lifecycle tests."""

from __future__ import annotations

import csv
import json
import shutil
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.catalog_loader import load_catalogs, registry, vizier
from nightcrate.catalog_loader.aco_loader import collect_aco
from nightcrate.catalog_loader.catalog_choice import (
    read_choice,
    with_added,
    with_removed,
    write_choice,
)
from nightcrate.catalog_loader.hash import file_sha256
from nightcrate.catalog_loader.loader import _build_search_key
from nightcrate.catalog_loader.reconcile import build_object_set
from nightcrate.catalog_loader.registry import CatalogSource
from nightcrate.db.session import get_db_path
from nightcrate.main import app
from nightcrate.services import catalog_progress

FIXTURES = Path(__file__).parent.parent / "fixtures" / "catalogs"
SAMPLE_ROOT = Path(__file__).parents[3] / ".superpowers" / "codex" / "v0.44.0" / "samples"
FULL_SAMPLES = {
    "vizier_aco_north": SAMPLE_ROOT / "full_VII_110A_table3.tsv",
    "vizier_aco_south": SAMPLE_ROOT / "full_VII_110A_table4.tsv",
    "vizier_aco_s": SAMPLE_ROOT / "full_VII_110A_table5.tsv",
}
ACO_FILES = {
    "vizier_aco_north": "aco_VII_110A_table3.tsv",
    "vizier_aco_south": "aco_VII_110A_table4.tsv",
    "vizier_aco_s": "aco_VII_110A_table5.tsv",
}
MINI_FILES = {
    "vizier_aco_north": "mini_aco_north.tsv",
    "vizier_aco_south": "mini_aco_south.tsv",
    "vizier_aco_s": "mini_aco_s.tsv",
}


@pytest.fixture
def anyio_backend():
    return "asyncio"


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
    vizier_dir = root / "vizier"
    openngc.mkdir(parents=True)
    vizier_dir.mkdir()
    shutil.copy(FIXTURES / "openngc" / "mini_NGC.csv", openngc / "NGC.csv")
    shutil.copy(FIXTURES / "openngc" / "mini_addendum.csv", openngc / "addendum.csv")
    shutil.copy(FIXTURES / "openngc" / "version.json", openngc / "version.json")
    for source_id, filename in ACO_FILES.items():
        shutil.copy(FIXTURES / "vizier" / MINI_FILES[source_id], vizier_dir / filename)
    if installed:
        version = {
            "files": {
                filename: {
                    "sha256": file_sha256(vizier_dir / filename),
                    "fetch_date": "2026-11-02T00:00:00+00:00",
                }
                for filename in ACO_FILES.values()
            }
        }
        (vizier_dir / "version.json").write_text(json.dumps(version), encoding="utf-8")
    return root


def _sources(root: Path) -> dict[str, CatalogSource]:
    return {source.source_id: source for source in registry.get_sources(root)}


def _batch(root: Path):
    sources = _sources(root)
    selected = {source_id: sources[source_id] for source_id in ACO_FILES}
    return collect_aco(selected, frozenset({"aco"}))


def _append_abell_21(root: Path) -> None:
    path = root / "openngc" / "addendum.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        fieldnames = csv.DictReader(handle, delimiter=";").fieldnames
    assert fieldnames is not None
    row = dict.fromkeys(fieldnames, "")
    row.update(
        {
            "Name": "Abell0021",
            "Type": "PN",
            "RA": "07:29:02",
            "Dec": "+13:14:48",
            "Const": "Gem",
            "MajAx": "9",
            "Common names": "Medusa Nebula",
        }
    )
    with path.open("a", encoding="utf-8", newline="") as handle:
        csv.DictWriter(handle, fieldnames=fieldnames, delimiter=";").writerow(row)


def test_aco_registry_has_three_atomic_tables_and_readme_credit(tmp_path: Path):
    catalog = registry.optional_catalog("aco")

    assert catalog is not None
    assert catalog.display_name == "ACO (Abell galaxy clusters)"
    assert catalog.kind == "vizier"
    assert catalog.source_ids == tuple(ACO_FILES)
    assert catalog.legacy_default is False
    assert catalog.designation_catalogs == frozenset({"aco"})
    assert [spec.catalog_id for spec in catalog.fetch_specs] == [
        "VII/110A/table3",
        "VII/110A/table4",
        "VII/110A/table5",
    ]
    assert [spec.output_filename for spec in catalog.fetch_specs] == list(ACO_FILES.values())
    assert all(
        spec.additional_params == {"-out.add": "_RAJ2000,_DEJ2000"} for spec in catalog.fetch_specs
    )
    assert catalog.fetch_specs[0].required_columns == (
        "_RAJ2000",
        "_DEJ2000",
        "ACO",
        "BMtype",
        "z",
        "Rich",
        "Dclass",
        "m10",
    )
    assert catalog.fetch_specs[2].required_columns[2] == "ACOS"
    assert catalog.credit == "Abell, Corwin & Olowin 1989. Retrieved via VizieR VII/110A."
    sources = _sources(_catalogs_root(tmp_path))
    assert {sources[source_id].attribution for source_id in ACO_FILES} == {registry.ACO_CITATION}
    for wording in (
        "Abell, G.O., Corwin, H.G. Jr. & Olowin, R.P. 1989",
        "A Catalogue of Rich Clusters of Galaxies",
        "Astrophysical Journal Supplement Series 70, 1",
        "(VizieR VII/110A)",
        registry.CDS_CITATION,
    ):
        assert wording in sources["vizier_aco_north"].attribution


def test_collect_aco_uses_all_three_tables_and_keeps_member_magnitude_in_notes(
    tmp_path: Path,
):
    batch = _batch(_catalogs_root(tmp_path))
    rows = {row.source_key: row for row in batch.objects}

    assert len(batch.objects) == 9
    assert set(batch.source_hashes) == set(ACO_FILES)
    assert rows["2151"].columns["primary_designation"] == "ACO 2151"
    assert rows["2151"].columns["obj_type"] == "ClG"
    assert rows["2151"].columns["ra_deg"] == 241.3125
    assert rows["2151"].columns["dec_deg"] == 17.7485
    assert rows["2151"].columns["mag_v"] is None
    assert rows["2151"].columns["maj_axis_arcmin"] is None
    assert rows["2151"].columns["openngc_notes"] == (
        "m10 13.8 (tenth-brightest member) · richness 2 · distance class 1 · BM III · z 0.0371"
    )
    assert rows["S1063"].columns["primary_designation"] == "ACO S1063"
    assert rows["S1063"].columns["openngc_notes"] == (
        "m10 19.7 (tenth-brightest member) · richness 1 · distance class 6 · BM I-II"
    )


def test_aco_2151_and_s1063_are_distinct_from_abell_21(tmp_path: Path):
    root = _catalogs_root(tmp_path)
    _append_abell_21(root)

    built = build_object_set(_sources(root), None, frozenset({"aco"}))
    abell = next(obj for obj in built.objects if obj.source_key == "Abell0021")
    aco_2151 = next(obj for obj in built.objects if obj.source_key == "2151")
    aco_s1063 = next(obj for obj in built.objects if obj.source_key == "S1063")

    assert abell.designations == (("abell", "21", True),)
    assert aco_2151.designations == (("aco", "2151", True),)
    assert aco_s1063.designations == (("aco", "S1063", True),)
    assert _build_search_key("aco", "2151") == "aco2151"
    assert _build_search_key("aco", "S1063") == "acos1063"
    assert _build_search_key("abell", "21") == "abell21"
    assert len({_build_search_key("aco", "2151"), _build_search_key("abell", "21")}) == 2


def test_collect_aco_full_sample_counts_when_available():
    missing = [path for path in FULL_SAMPLES.values() if not path.exists()]
    if missing:
        pytest.skip("local full ACO samples are not present")
    sources = {
        source_id: CatalogSource(
            source_id,
            "vizier",
            "ACO sample",
            path,
            None,
            None,
            "CDS public",
            registry.ACO_CITATION,
            "aco",
        )
        for source_id, path in FULL_SAMPLES.items()
    }

    objects = collect_aco(sources, frozenset({"aco"})).objects
    counts = {
        source_id: sum(row.source_id == source_id for row in objects) for source_id in sources
    }

    assert counts == {
        "vizier_aco_north": 2712,
        "vizier_aco_south": 1364,
        "vizier_aco_s": 1174,
    }


def test_aco_load_remove_and_add_reactivates_same_object(db: sqlite3.Connection, tmp_path: Path):
    root = _catalogs_root(tmp_path, installed=True)
    write_choice(root, with_added(None, "aco"))
    load_catalogs(db, root)
    row = db.execute(
        "SELECT d.id, d.obj_type, d.mag_v, d.maj_axis_arcmin FROM dso d "
        "JOIN dso_designation dd ON dd.dso_id=d.id "
        "WHERE dd.catalog='aco' AND dd.identifier='2151'"
    ).fetchone()
    assert row is not None
    dso_id = int(row[0])
    assert tuple(row[1:]) == ("ClG", None, None)
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (dso_id,))
    db.commit()

    write_choice(root, with_removed(read_choice(root), "aco"))
    load_catalogs(db, root)
    assert db.execute("SELECT active FROM dso WHERE id=?", (dso_id,)).fetchone()[0] == 0

    write_choice(root, with_added(read_choice(root), "aco"))
    load_catalogs(db, root)
    assert tuple(db.execute("SELECT id, active FROM dso WHERE id=?", (dso_id,)).fetchone()) == (
        dso_id,
        1,
    )
    assert db.execute("SELECT 1 FROM favorite_target WHERE dso_id=?", (dso_id,)).fetchone()


@pytest.mark.anyio
async def test_aco_part_three_download_failure_leaves_choice_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    catalog = registry.optional_catalog("aco")
    assert catalog is not None
    root = _catalogs_root(tmp_path, installed=True)
    write_choice(root, with_added(None, "aco"))
    with sqlite3.connect(get_db_path()) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        load_catalogs(conn, root)

    vizier_dir = root / "vizier"
    tracked_paths = {
        **{filename: vizier_dir / filename for filename in ACO_FILES.values()},
        "version.json": vizier_dir / "version.json",
        "choice.json": root / "choice.json",
    }
    before = {name: path.read_bytes() for name, path in tracked_paths.items()}
    successful_bodies = {
        spec.catalog_id: _valid_vizier_body(spec.required_columns)
        for spec in catalog.fetch_specs[:2]
    }
    calls: list[str] = []

    async def get(url: str, **_kwargs):
        calls.append(url)
        for catalog_id, body in successful_bodies.items():
            if f"-source={catalog_id}" in url:
                return SimpleNamespace(status_code=200, content=body)
        raise OSError("injected table5 failure")

    monkeypatch.setattr(vizier.http_client, "get", get)
    monkeypatch.setattr(
        "nightcrate.api.admin.load_config", lambda: SimpleNamespace(db_configured=True)
    )
    catalog_progress.reset()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/admin/catalogs/optional/aco/add")

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "Couldn't download ACO (Abell galaxy clusters): part 3 of 3, "
        "ACO supplementary southern clusters (VII/110A table5). "
        "Strasbourg, Harvard, South Africa, Tokyo, Beijing and India failed."
    )
    assert sum("-source=VII/110A/table5" in url for url in calls) == len(vizier.VIZIER_HOSTS)
    assert {name: path.read_bytes() for name, path in tracked_paths.items()} == before
    assert not (vizier_dir / ".download").exists()
    assert not (vizier_dir / "publishing" / "aco.json").exists()


def _valid_vizier_body(columns: tuple[str, ...]) -> bytes:
    header = "\t".join(columns)
    units = "\t".join("unit" for _ in columns)
    separator = "\t".join("--------" for _ in columns)
    row = "\t".join("1" for _ in columns)
    return (f"# VizieR fixture\n{header}\n{units}\n{separator}\n" + f"{row}\n" * 100).encode()
