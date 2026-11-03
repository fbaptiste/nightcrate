"""Optional-catalog removal, deferral, and identity regressions."""

from __future__ import annotations

import shutil
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
from yoyo import get_backend, read_migrations

from nightcrate.catalog_loader import load_catalogs, registry
from nightcrate.catalog_loader.catalog_choice import (
    CatalogChoice,
    read_choice,
    with_added,
    with_removed,
    write_choice,
)
from nightcrate.catalog_loader.loader import (
    _build_display_form,
    _build_search_key,
    prepare_object_step,
)
from nightcrate.catalog_loader.reconcile import (
    NewObject,
    ObjectSet,
    SourceEntry,
    apply_object_set,
    build_object_set,
)
from nightcrate.db.migrations import MIGRATIONS_DIR, apply_migrations

FIXTURES = Path(__file__).parent.parent / "fixtures" / "catalogs"


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "test.db")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


@pytest.fixture
def catalogs_root(tmp_path: Path) -> Path:
    root = tmp_path / "catalogs"
    openngc = root / "openngc"
    vizier = root / "vizier"
    openngc.mkdir(parents=True)
    vizier.mkdir()
    shutil.copy(FIXTURES / "openngc" / "mini_NGC.csv", openngc / "NGC.csv")
    shutil.copy(FIXTURES / "openngc" / "mini_addendum.csv", openngc / "addendum.csv")
    shutil.copy(
        FIXTURES / "vizier" / "mini_sharpless.tsv",
        vizier / "sharpless_VII_20.tsv",
    )
    shutil.copy(
        FIXTURES / "vizier" / "mini_barnard.tsv",
        vizier / "barnard_VII_220.tsv",
    )
    return root


def _catalog_object_ids(db: sqlite3.Connection, source_id: str) -> list[int]:
    return [
        int(row[0])
        for row in db.execute(
            """
            SELECT d.id
            FROM dso d JOIN dso_catalog_source s ON s.id=d.source_catalog_id
            WHERE s.source_id=? ORDER BY d.id
            """,
            (source_id,),
        )
    ]


def _choice(root: Path, *, removed: str | None = None, added: str | None = None) -> None:
    choice = read_choice(root) or CatalogChoice(frozenset(), frozenset())
    if removed is not None:
        choice = with_removed(choice, removed)
    if added is not None:
        choice = with_added(choice, added)
    write_choice(root, choice)


def _apply_through_0065(db_path: Path) -> None:
    with get_backend(f"sqlite:///{db_path}") as backend:
        migrations = read_migrations(str(MIGRATIONS_DIR))
        backend.apply_migrations(
            backend.to_apply(migrations).filter(
                lambda migration: migration.id != "0066.more_catalogs"
            )
        )


def _legacy_seed(db_path: Path, root: Path) -> tuple[dict[tuple[str, str], int], tuple[int, int]]:
    sources = {source.source_id: source for source in registry.get_sources(root)}
    object_set = build_object_set(
        sources,
        sources["nightcrate_sharpless_crossref"].file_path,
    )
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        source_ids: dict[str, int] = {}
        for source_id in {obj.source_id for obj in object_set.objects}:
            source = sources[source_id]
            source_ids[source_id] = int(
                conn.execute(
                    """
                    INSERT INTO dso_catalog_source (
                        source_id, category, display_name, version, source_url,
                        file_path, file_hash, license, attribution, row_count,
                        keys_assigned
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                    """,
                    (
                        source.source_id,
                        source.category,
                        source.display_name,
                        source.version,
                        source.source_url,
                        str(source.file_path),
                        object_set.hashes[source_id],
                        source.license,
                        source.attribution,
                        sum(obj.source_id == source_id for obj in object_set.objects),
                    ),
                ).lastrowid
            )
        ids: dict[tuple[str, str], int] = {}
        for obj in object_set.objects:
            columns = [*obj.columns, "source_catalog_id", "source_key", "active"]
            values = [*obj.columns.values(), source_ids[obj.source_id], obj.source_key, 1]
            dso_id = int(
                conn.execute(
                    f"INSERT INTO dso ({', '.join(columns)}) "  # noqa: S608  # nosec B608
                    f"VALUES ({', '.join('?' for _ in columns)})",
                    values,
                ).lastrowid
            )
            ids[(obj.source_id, obj.source_key)] = dso_id
            conn.executemany(
                """
                INSERT INTO dso_designation
                    (dso_id, catalog, identifier, display_form, search_key, is_primary)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        dso_id,
                        catalog,
                        identifier,
                        _build_display_form(catalog, identifier),
                        _build_search_key(catalog, identifier),
                        int(primary),
                    )
                    for catalog, identifier, primary in obj.designations
                ),
            )
        linked = list(ids.values())[:2]
        conn.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (linked[0],))
        conn.execute("INSERT INTO project (name) VALUES ('0065 upgrade')")
        project_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.execute(
            "INSERT INTO project_target (project_id, dso_id) VALUES (?, ?)",
            (project_id, linked[1]),
        )
        target_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.execute(
            """
            INSERT INTO sub_frame (project_id, content_hash, project_target_id, date_obs_utc)
            VALUES (?, '0065-child', ?, '2026-01-01')
            """,
            (project_id, target_id),
        )
        conn.commit()
    return ids, (linked[0], linked[1])


def _new_object(source_id: str, source_key: str, catalog_id: str, index: int) -> NewObject:
    return NewObject(
        source_id,
        source_key,
        {
            "primary_designation": f"TEST {source_key}",
            "obj_type": "Other",
            "source_row_hash": f"hash-{source_key}",
        },
        (("ngc", source_key, True),),
        index,
        catalog_id,
    )


@pytest.mark.parametrize(
    "case",
    ("all-present", "barnard-missing", "version-missing", "version-corrupt", "shared-root"),
)
def test_upgrade_without_choice_file_removes_nothing(tmp_path: Path, catalogs_root, case: str):
    version_path = catalogs_root / "vizier" / "version.json"
    version_path.write_text('{"files": {}}\n', encoding="utf-8")
    database_count = 2 if case == "shared-root" else 1
    db_paths = [tmp_path / f"upgrade-{index}.db" for index in range(database_count)]
    expected: list[tuple[dict[tuple[str, str], int], tuple[int, int]]] = []
    for db_path in db_paths:
        _apply_through_0065(db_path)
        expected.append(_legacy_seed(db_path, catalogs_root))
        with sqlite3.connect(db_path) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
            assert "dso_source_entry" not in tables
            assert "dso_catalog_applied" not in tables

    if case == "barnard-missing":
        (catalogs_root / "vizier" / "barnard_VII_220.tsv").unlink()
    elif case == "version-missing":
        version_path.unlink()
    elif case == "version-corrupt":
        version_path.write_text("{not-json", encoding="utf-8")

    assert read_choice(catalogs_root) is None
    for db_path, (before_ids, linked) in zip(db_paths, expected, strict=True):
        apply_migrations(db_path)
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            first = load_catalogs(conn, catalogs_root)
            second = load_catalogs(conn, catalogs_root)
            after_ids = {
                (str(row["source_id"]), str(row["source_key"])): int(row["id"])
                for row in conn.execute(
                    """
                    SELECT d.id, d.source_key, s.source_id
                    FROM dso d JOIN dso_catalog_source s ON s.id = d.source_catalog_id
                    WHERE d.source_key IS NOT NULL
                    """
                )
            }
            assert after_ids == before_ids
            assert conn.execute("SELECT COUNT(*) FROM dso WHERE active = 0").fetchone()[0] == 0
            assert conn.execute("SELECT dso_id FROM favorite_target").fetchone()[0] == linked[0]
            assert conn.execute("SELECT dso_id FROM project_target").fetchone()[0] == linked[1]
            assert conn.execute("SELECT COUNT(*) FROM sub_frame").fetchone()[0] == 1
            assert not any(result.status == "failed" for result in first.results + second.results)
            if case == "barnard-missing":
                errors = [
                    result.error
                    for summary in (first, second)
                    for result in summary.results
                    if result.source_id == "vizier_barnard"
                ]
                assert all(error is not None and "deferred" in error for error in errors)
            else:
                assert (
                    next(
                        result for result in second.results if result.source_id == "openngc"
                    ).status
                    == "unchanged"
                )


def test_absent_legacy_files_are_never_applied(db, catalogs_root):
    (catalogs_root / "vizier" / "sharpless_VII_20.tsv").unlink()
    (catalogs_root / "vizier" / "barnard_VII_220.tsv").unlink()

    first = load_catalogs(db, catalogs_root)
    second = load_catalogs(db, catalogs_root)

    assert db.execute("SELECT COUNT(*) FROM dso_catalog_applied").fetchone()[0] == 0
    assert not any("deferred" in (result.error or "") for result in first.results + second.results)


def test_removed_catalog_deletes_unlinked_objects(db, catalogs_root):
    load_catalogs(db, catalogs_root)
    barnard_ids = _catalog_object_ids(db, "vizier_barnard")
    assert barnard_ids
    _choice(catalogs_root, removed="barnard")

    load_catalogs(db, catalogs_root)

    assert not set(barnard_ids) & {int(row[0]) for row in db.execute("SELECT id FROM dso")}
    assert (
        db.execute("SELECT state FROM dso_catalog_applied WHERE catalog_id='barnard'").fetchone()[0]
        == "removed"
    )


def test_removed_catalog_keeps_linked_objects_inactive_with_names(db, catalogs_root):
    load_catalogs(db, catalogs_root)
    dso_id = _catalog_object_ids(db, "vizier_barnard")[0]
    original_names = [
        tuple(row)
        for row in db.execute(
            "SELECT catalog,identifier,display_form FROM dso_designation WHERE dso_id=?",
            (dso_id,),
        )
    ]
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (dso_id,))
    db.commit()
    _choice(catalogs_root, removed="barnard")

    load_catalogs(db, catalogs_root)

    assert db.execute("SELECT active FROM dso WHERE id=?", (dso_id,)).fetchone()[0] == 0
    assert [
        tuple(row)
        for row in db.execute(
            "SELECT catalog,identifier,display_form FROM dso_designation WHERE dso_id=?",
            (dso_id,),
        )
    ] == original_names


def test_retained_inactive_designations_repair_once(db, catalogs_root):
    load_catalogs(db, catalogs_root)
    dso_id = _catalog_object_ids(db, "vizier_barnard")[0]
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (dso_id,))
    db.commit()
    _choice(catalogs_root, removed="barnard")
    load_catalogs(db, catalogs_root)
    db.execute(
        """
        INSERT INTO dso_designation
            (dso_id, catalog, identifier, display_form, search_key, is_primary)
        VALUES (?, 'mcg', '07-28-004', 'old MCG', 'old-key', 0)
        """,
        (dso_id,),
    )
    db.commit()

    repaired = load_catalogs(db, catalogs_root)
    repeat = load_catalogs(db, catalogs_root)

    row = db.execute(
        "SELECT identifier,display_form,search_key FROM dso_designation "
        "WHERE dso_id=? AND catalog='mcg'",
        (dso_id,),
    ).fetchone()
    assert tuple(row) == ("-07-28-004", "MCG -07-28-004", "mcg-07-28-004")
    assert next(result for result in repaired.results if result.source_id == "openngc").status == (
        "loaded"
    )
    assert next(result for result in repeat.results if result.source_id == "openngc").status == (
        "unchanged"
    )


def test_readding_reactivates_same_ids(db, catalogs_root):
    load_catalogs(db, catalogs_root)
    dso_id = _catalog_object_ids(db, "vizier_barnard")[0]
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (dso_id,))
    db.commit()
    _choice(catalogs_root, removed="barnard")
    load_catalogs(db, catalogs_root)
    _choice(catalogs_root, added="barnard")

    load_catalogs(db, catalogs_root)

    assert tuple(db.execute("SELECT id,active FROM dso WHERE id=?", (dso_id,)).fetchone()) == (
        dso_id,
        1,
    )
    keyed_count = db.execute("SELECT COUNT(*) FROM dso WHERE source_key IS NOT NULL").fetchone()[0]
    distinct_count = db.execute(
        "SELECT COUNT(DISTINCT source_key) FROM dso WHERE source_key IS NOT NULL"
    ).fetchone()[0]
    assert keyed_count == distinct_count


def test_add_overrides_recorded_removal(db, catalogs_root):
    load_catalogs(db, catalogs_root)
    dso_id = _catalog_object_ids(db, "vizier_barnard")[0]
    source_key = db.execute("SELECT source_key FROM dso WHERE id=?", (dso_id,)).fetchone()[0]
    _choice(catalogs_root, removed="barnard")
    load_catalogs(db, catalogs_root)

    _choice(catalogs_root, added="barnard")
    load_catalogs(db, catalogs_root)

    assert (
        db.execute(
            """
        SELECT d.active
        FROM dso d JOIN dso_catalog_source s ON s.id=d.source_catalog_id
        WHERE s.source_id='vizier_barnard' AND d.source_key=?
        """,
            (source_key,),
        ).fetchone()[0]
        == 1
    )
    assert (
        db.execute("SELECT state FROM dso_catalog_applied WHERE catalog_id='barnard'").fetchone()[0]
        == "on"
    )


def test_unrelated_removal_spares_legacy_rows(tmp_path: Path, catalogs_root):
    db_path = tmp_path / "legacy-bystander.db"
    _apply_through_0065(db_path)
    _legacy_seed(db_path, catalogs_root)
    with sqlite3.connect(db_path) as legacy:
        source_id = int(
            legacy.execute(
                "SELECT id FROM dso_catalog_source WHERE source_id='openngc'"
            ).fetchone()[0]
        )
        legacy_id = int(
            legacy.execute(
                """
                INSERT INTO dso (
                    primary_designation, obj_type, source_catalog_id,
                    source_row_hash, source_key, active
                ) VALUES ('Legacy bystander', 'Other', ?, 'legacy-bystander',
                          'legacy-bystander', 0)
                """,
                (source_id,),
            ).lastrowid
        )
        legacy.commit()
    apply_migrations(db_path)
    _choice(catalogs_root, removed="barnard")

    with sqlite3.connect(db_path) as upgraded:
        upgraded.row_factory = sqlite3.Row
        upgraded.execute("PRAGMA foreign_keys = ON")
        load_catalogs(upgraded, catalogs_root)

        assert tuple(
            upgraded.execute("SELECT id,active FROM dso WHERE id=?", (legacy_id,)).fetchone()
        ) == (legacy_id, 0)
        assert (
            upgraded.execute(
                "SELECT COUNT(*) FROM dso_source_entry WHERE dso_id=?", (legacy_id,)
            ).fetchone()[0]
            == 0
        )


def test_keyless_retained_rows_get_no_entry(db, catalogs_root):
    load_catalogs(db, catalogs_root)
    dso_id = _catalog_object_ids(db, "vizier_barnard")[0]
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (dso_id,))
    db.execute("DELETE FROM dso_source_entry WHERE dso_id=?", (dso_id,))
    db.execute("UPDATE dso SET source_key=NULL WHERE id=?", (dso_id,))
    db.commit()
    _choice(catalogs_root, removed="barnard")

    load_catalogs(db, catalogs_root)
    load_catalogs(db, catalogs_root, force=True)

    row = db.execute("SELECT active,source_key FROM dso WHERE id=?", (dso_id,)).fetchone()
    assert tuple(row) == (
        0,
        None,
    )
    assert (
        db.execute("SELECT COUNT(*) FROM dso_source_entry WHERE dso_id=?", (dso_id,)).fetchone()[0]
        == 0
    )


def test_removed_catalog_never_defers(db, catalogs_root):
    load_catalogs(db, catalogs_root)
    _choice(catalogs_root, removed="barnard")
    (catalogs_root / "vizier" / "barnard_VII_220.tsv").unlink()

    summary = load_catalogs(db, catalogs_root)

    assert not any("deferred" in (result.error or "") for result in summary.results)


def test_in_frame_rows_go_with_removed_objects(db, catalogs_root):
    load_catalogs(db, catalogs_root)
    dso_id = _catalog_object_ids(db, "vizier_barnard")[0]
    db.execute("INSERT INTO project (name) VALUES ('Frame-only reference')")
    project_id = int(db.execute("SELECT last_insert_rowid()").fetchone()[0])
    db.execute(
        """
        INSERT INTO project_solve (
            project_id,image_path,image_width,image_height,center_ra_deg,
            center_dec_deg,cd1_1,cd1_2,cd2_1,cd2_2,crpix1,crpix2
        ) VALUES (?, 'frame.fits', 10, 10, 0, 0, 1, 0, 0, 1, 5, 5)
        """,
        (project_id,),
    )
    solve_id = int(db.execute("SELECT last_insert_rowid()").fetchone()[0])
    db.execute("INSERT INTO project_dso (solve_id,dso_id) VALUES (?,?)", (solve_id, dso_id))
    db.commit()
    _choice(catalogs_root, removed="barnard")

    load_catalogs(db, catalogs_root)

    assert db.execute("SELECT 1 FROM dso WHERE id=?", (dso_id,)).fetchone() is None
    assert db.execute("SELECT COUNT(*) FROM project_dso").fetchone()[0] == 0


def test_removal_applies_to_every_database(tmp_path: Path, catalogs_root):
    paths = (tmp_path / "first.db", tmp_path / "second.db")
    before: list[set[int]] = []
    for path in paths:
        apply_migrations(path)
        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            load_catalogs(conn, catalogs_root)
            before.append(set(_catalog_object_ids(conn, "vizier_barnard")))
    _choice(catalogs_root, removed="barnard")

    for path, barnard_ids in zip(paths, before, strict=True):
        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            load_catalogs(conn, catalogs_root)
            remaining = {int(row[0]) for row in conn.execute("SELECT id FROM dso")}
            assert not barnard_ids & remaining
            assert (
                conn.execute(
                    "SELECT state FROM dso_catalog_applied WHERE catalog_id='barnard'"
                ).fetchone()[0]
                == "removed"
            )


def test_legacy_catalog_with_missing_file_still_defers(db, catalogs_root):
    load_catalogs(db, catalogs_root)
    (catalogs_root / "vizier" / "barnard_VII_220.tsv").unlink()

    summary = load_catalogs(db, catalogs_root)

    barnard = next(result for result in summary.results if result.source_id == "vizier_barnard")
    assert barnard.status == "skipped"
    assert "deferred" in (barnard.error or "")


def test_removing_a_catalog_that_only_contributed_names(db, catalogs_root):
    load_catalogs(db, catalogs_root)
    merged = db.execute(
        """
        SELECT e.dso_id, e.source_key AS identifier
        FROM dso_source_entry e
        JOIN dso_catalog_source es ON es.id=e.source_catalog_id
        JOIN dso d ON d.id=e.dso_id
        JOIN dso_catalog_source owner ON owner.id=d.source_catalog_id
        WHERE e.catalog_id='sharpless'
          AND es.source_id='vizier_sharpless'
          AND owner.source_id!='vizier_sharpless'
          AND COALESCE(d.raw_other_id, '') NOT LIKE '%Sh2-' || e.source_key || '%'
        LIMIT 1
        """
    ).fetchone()
    assert merged is not None
    _choice(catalogs_root, removed="sharpless")

    load_catalogs(db, catalogs_root)

    assert (
        db.execute(
            "SELECT 1 FROM dso_designation WHERE dso_id=? AND catalog='sharpless2'",
            (merged["dso_id"],),
        ).fetchone()
        is None
    )


def test_preview_matches_real_apply(db, catalogs_root):
    load_catalogs(db, catalogs_root)
    _choice(catalogs_root, removed="barnard")
    plan = prepare_object_step(db, catalogs_root, force=False)
    assert plan.run and plan.object_set is not None
    before = [tuple(row) for row in db.execute("SELECT id,active FROM dso ORDER BY id")]

    preview = apply_object_set(
        db,
        plan.object_set,
        (),
        removed_catalogs=frozenset({"barnard"}),
        dry_run=True,
    )
    assert [tuple(row) for row in db.execute("SELECT id,active FROM dso ORDER BY id")] == before
    real = apply_object_set(
        db,
        plan.object_set,
        (),
        removed_catalogs=frozenset({"barnard"}),
    )
    assert (preview.deleted, preview.removed, preview.transferred) == (
        real.deleted,
        real.removed,
        real.transferred,
    )


def test_preview_reports_blocked_when_deferred(db, catalogs_root):
    load_catalogs(db, catalogs_root)
    barnard_ids = set(_catalog_object_ids(db, "vizier_barnard"))
    _choice(catalogs_root, removed="barnard")
    (catalogs_root / "openngc" / "addendum.csv").unlink()

    preview = prepare_object_step(db, catalogs_root, force=False)
    summary = load_catalogs(db, catalogs_root)

    assert not preview.run
    assert preview.deferred_reason is not None and "addendum.csv" in preview.deferred_reason
    remaining = {int(row[0]) for row in db.execute("SELECT id FROM dso")}
    assert barnard_ids <= remaining
    result = next(row for row in summary.results if row.source_id == "openngc_addendum")
    assert result.status == "skipped"
    assert result.error == preview.deferred_reason


def test_lost_choice_file_never_removes(db, catalogs_root, tmp_path: Path):
    write_choice(catalogs_root, with_added(read_choice(catalogs_root), "melotte"))
    load_catalogs(db, catalogs_root)
    melotte_ids = {
        str(row[0]): int(row[1])
        for row in db.execute(
            """
            SELECT dd.identifier, d.id
            FROM dso d
            JOIN dso_designation dd ON dd.dso_id=d.id
            WHERE dd.catalog='mel' AND dd.identifier IN ('20', '66')
            """
        )
    }
    assert set(melotte_ids) == {"20", "66"}
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (melotte_ids["20"],))
    db.commit()

    choice_path = catalogs_root / "choice.json"
    choice_path.unlink()
    missing = load_catalogs(db, catalogs_root)

    assert missing.objects_removed == 0
    assert {
        str(row[0]): (int(row[1]), int(row[2]))
        for row in db.execute(
            """
            SELECT dd.identifier, d.id, d.active
            FROM dso d
            JOIN dso_designation dd ON dd.dso_id=d.id
            WHERE dd.catalog='mel' AND dd.identifier IN ('20', '66')
            """
        )
    } == {identifier: (dso_id, 1) for identifier, dso_id in melotte_ids.items()}
    assert db.execute(
        "SELECT 1 FROM favorite_target WHERE dso_id=?", (melotte_ids["20"],)
    ).fetchone()

    choice_path.write_text("{invalid", encoding="utf-8")
    corrupt = load_catalogs(db, catalogs_root)

    assert corrupt.objects_removed == 0
    assert {
        str(row[0]): (int(row[1]), int(row[2]))
        for row in db.execute(
            """
            SELECT dd.identifier, d.id, d.active
            FROM dso d
            JOIN dso_designation dd ON dd.dso_id=d.id
            WHERE dd.catalog='mel' AND dd.identifier IN ('20', '66')
            """
        )
    } == {identifier: (dso_id, 1) for identifier, dso_id in melotte_ids.items()}

    choice_path.unlink()
    fresh_path = tmp_path / "fresh-after-missing-choice.db"
    apply_migrations(fresh_path)
    with sqlite3.connect(fresh_path) as fresh:
        fresh.row_factory = sqlite3.Row
        fresh.execute("PRAGMA foreign_keys = ON")
        load_catalogs(fresh, catalogs_root)
        assert _catalog_object_ids(fresh, "nightcrate_melotte") == []


def test_lost_choice_file_after_removal(db, catalogs_root, tmp_path: Path):
    choice = with_added(read_choice(catalogs_root), "barnard")
    choice = with_added(choice, "melotte")
    write_choice(catalogs_root, choice)
    load_catalogs(db, catalogs_root)

    choice = with_removed(read_choice(catalogs_root), "barnard")
    choice = with_removed(choice, "melotte")
    write_choice(catalogs_root, choice)
    load_catalogs(db, catalogs_root)

    for invalid in (None, "{invalid"):
        choice_path = catalogs_root / "choice.json"
        if invalid is None:
            choice_path.unlink(missing_ok=True)
        else:
            choice_path.write_text(invalid, encoding="utf-8")
        plan = prepare_object_step(db, catalogs_root, force=False)
        assert plan.effective["barnard"] == plan.effective["melotte"] == "removed"
        assert plan.deferred_reason is None
        summary = load_catalogs(db, catalogs_root)
        relevant = [
            result
            for result in summary.results
            if result.source_id in {"vizier_barnard", "nightcrate_melotte"}
        ]
        assert all(result.error is None for result in relevant)
        active_counts = {
            str(row[0]): int(row[1])
            for row in db.execute(
                """
                SELECT s.source_id, COUNT(d.id)
                FROM dso_catalog_source s
                LEFT JOIN dso d ON d.source_catalog_id=s.id AND d.active=1
                WHERE s.source_id IN ('vizier_barnard', 'nightcrate_melotte')
                GROUP BY s.source_id
                """
            )
        }
        assert active_counts == {"nightcrate_melotte": 0, "vizier_barnard": 0}
        applied = {
            str(row[0]): str(row[1])
            for row in db.execute(
                """
                SELECT catalog_id, state FROM dso_catalog_applied
                WHERE catalog_id IN ('barnard', 'melotte')
                """
            )
        }
        assert applied == {"barnard": "removed", "melotte": "removed"}

    fresh_path = tmp_path / "fresh-after-lost-choice.db"
    apply_migrations(fresh_path)
    with sqlite3.connect(fresh_path) as fresh:
        fresh.row_factory = sqlite3.Row
        fresh.execute("PRAGMA foreign_keys = ON")
        load_catalogs(fresh, catalogs_root)
        assert (catalogs_root / "vizier" / "barnard_VII_220.tsv").is_file()
        assert _catalog_object_ids(fresh, "vizier_barnard")
        assert (
            fresh.execute(
                "SELECT state FROM dso_catalog_applied WHERE catalog_id='barnard'"
            ).fetchone()[0]
            == "on"
        )
        assert _catalog_object_ids(fresh, "nightcrate_melotte") == []


def test_entry_in_two_catalogs(db, tmp_path: Path, monkeypatch):
    source_path = tmp_path / "shared.tsv"
    source_path.write_text("fixture", encoding="utf-8")
    source = registry.CatalogSource(
        "shared",
        "nightcrate",
        "Shared",
        source_path,
        None,
        None,
        "MIT",
        "test",
        "openngc",
    )
    png = registry.OptionalCatalog(
        "png", "PN", ("shared",), "nightcrate", (), frozenset({"png"}), False, "test"
    )
    abell = registry.OptionalCatalog(
        "abell_pn",
        "Abell PN",
        ("shared",),
        "nightcrate",
        (),
        frozenset({"abell"}),
        False,
        "test",
    )
    monkeypatch.setattr(registry, "OPTIONAL_CATALOGS", (png, abell))
    obj = NewObject(
        "shared",
        "entry-1",
        {"primary_designation": "PN G001.0+01.0", "obj_type": "PN", "source_row_hash": "h"},
        (("png", "001.0+01.0", True),),
        0,
        "png",
    )
    both = ObjectSet(
        (obj,),
        {},
        {"shared": "hash"},
        0,
        {"shared": source},
        (
            SourceEntry("shared", "entry-1", "png", 0),
            SourceEntry("shared", "entry-1", "abell_pn", 0),
        ),
    )
    apply_object_set(db, both, ())
    dso_id = int(db.execute("SELECT id FROM dso WHERE source_key='entry-1'").fetchone()[0])

    abell_only = replace(
        both,
        entries=(SourceEntry("shared", "entry-1", "abell_pn", 0),),
    )
    apply_object_set(db, abell_only, (), removed_catalogs=frozenset({"png"}))
    assert db.execute("SELECT id FROM dso WHERE id=?", (dso_id,)).fetchone() is not None

    empty = ObjectSet((), {}, {}, 0, {"shared": source})
    report = apply_object_set(
        db,
        empty,
        (),
        removed_catalogs=frozenset({"png", "abell_pn"}),
    )
    assert report.deleted == 1
    assert db.execute("SELECT id FROM dso WHERE id=?", (dso_id,)).fetchone() is None


def test_identity_survives_remove_and_readd_of_owner(db, tmp_path: Path):
    source_path = tmp_path / "identity.tsv"
    source_path.write_text("fixture", encoding="utf-8")

    def source(source_id: str) -> registry.CatalogSource:
        return registry.CatalogSource(
            source_id, "nightcrate", source_id, source_path, None, None, "MIT", "test", "openngc"
        )

    sources = {source_id: source(source_id) for source_id in ("s1", "s2")}
    owner = _new_object("s1", "owner", "cat1", 0)
    combined = ObjectSet(
        (owner,),
        {("s2", "member"): 0},
        {"s1": "hash-s1", "s2": "hash-s2"},
        0,
        sources,
        (
            SourceEntry("s1", "owner", "cat1", 0),
            SourceEntry("s2", "member", "cat2", 0),
        ),
    )
    apply_object_set(db, combined, ())
    dso_id = int(db.execute("SELECT id FROM dso").fetchone()[0])
    db.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (dso_id,))
    db.commit()

    member = _new_object("s2", "member", "cat2", 0)
    member_only = ObjectSet(
        (member,),
        {},
        {"s2": "hash-s2"},
        0,
        sources,
        (SourceEntry("s2", "member", "cat2", 0),),
    )
    apply_object_set(db, member_only, (), removed_catalogs=frozenset({"cat1"}))
    assert [tuple(row) for row in db.execute("SELECT id,active FROM dso")] == [(dso_id, 1)]
    assert db.execute("SELECT dso_id FROM favorite_target").fetchone()[0] == dso_id
    apply_object_set(db, combined, ())

    assert [tuple(row) for row in db.execute("SELECT id,active FROM dso")] == [(dso_id, 1)]
    assert db.execute("SELECT dso_id FROM favorite_target").fetchone()[0] == dso_id


def test_large_removal_discovers_foreign_keys_once(db, tmp_path: Path, monkeypatch):
    source_path = tmp_path / "bulk.tsv"
    source_path.write_text("fixture", encoding="utf-8")
    source = registry.CatalogSource(
        "bulk", "nightcrate", "Bulk", source_path, None, None, "MIT", "test", "openngc"
    )
    objects = tuple(_new_object("bulk", f"{index:05d}", "bulkcat", index) for index in range(5000))
    full = ObjectSet(objects, {}, {"bulk": "hash"}, 0, {"bulk": source})
    apply_object_set(db, full, ())
    linked_ids = [int(row[0]) for row in db.execute("SELECT id FROM dso ORDER BY id LIMIT 3")]
    db.executemany(
        "INSERT INTO favorite_target (dso_id) VALUES (?)",
        ((value,) for value in linked_ids),
    )
    db.commit()

    from nightcrate.catalog_loader import user_links

    real_discovery = user_links._foreign_keys_to
    calls = 0

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real_discovery(*args, **kwargs)

    monkeypatch.setattr(user_links, "_foreign_keys_to", counted)
    report = apply_object_set(
        db,
        ObjectSet((), {}, {}, 0, {"bulk": source}),
        (),
        removed_catalogs=frozenset({"bulkcat"}),
    )

    assert calls == 1
    assert report.deleted == 4997
    assert report.removed == 3
    assert [tuple(row) for row in db.execute("SELECT id,active FROM dso ORDER BY id")] == [
        (dso_id, 0) for dso_id in linked_ids
    ]
