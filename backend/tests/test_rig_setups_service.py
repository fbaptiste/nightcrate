"""Unit tests for setup snapshots, stamping, usage, and corrections."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import aiosqlite
import pytest
from yoyo import get_backend, read_migrations

from nightcrate.db.migrations import MIGRATIONS_DIR
from nightcrate.services.rig_setups import (
    PART_GROUPS,
    RigParts,
    RigUsage,
    apply_correction_to_earlier_setups,
    changed_groups,
    read_rig_parts,
    read_setup_parts,
    rig_usage,
    save_earlier_setup,
)
from tests.rig_setup_fixtures import make_equipment, make_frame, make_project, make_rig


@pytest.fixture
def rig_db(tmp_path: Path) -> Path:
    path = tmp_path / "rig-setups.db"
    with get_backend(f"sqlite:///{path}") as backend:
        migrations = read_migrations(str(MIGRATIONS_DIR))
        backend.apply_migrations(backend.to_apply(migrations))
    return path


def test_changed_groups_reports_only_equipment():
    base = RigParts(telescope_configuration_id=1, camera_id=2)
    assert PART_GROUPS == (
        "telescope",
        "camera",
        "filters",
        "mount",
        "focuser",
        "guider",
        "guide_camera",
        "computer",
        "software",
    )
    assert changed_groups(base, replace(base, camera_id=3)) == ["camera"]
    slotted = replace(base, filter_wheel_id=4, filter_slots=frozenset(((1, 8), (2, 9))))
    reordered = replace(slotted, filter_slots=frozenset(((2, 9), (1, 8))))
    assert changed_groups(slotted, reordered) == []
    single = replace(slotted, filter_wheel_id=None, single_filter_id=8, filter_slots=frozenset())
    assert changed_groups(slotted, single) == ["filters"]
    oag = replace(base, oag_id=5)
    guide_scope = replace(base, guide_scope_id=6)
    assert changed_groups(oag, guide_scope) == ["guider"]
    assert changed_groups(base, replace(base, guide_camera_id=7)) == ["guide_camera"]


@pytest.mark.asyncio
async def test_rig_usage_counts(rig_db: Path):
    async with aiosqlite.connect(rig_db) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        equipment = await make_equipment(conn)
        rig_id = await make_rig(conn, equipment, "Main rig")
        planned_rig = await make_rig(conn, equipment, "Travel rig")
        project_a = await make_project(conn)
        project_b = await make_project(conn, "Project B")
        await conn.execute("INSERT INTO project_rig VALUES (?, ?)", (project_a, rig_id))
        await make_frame(conn, project_a, "night-1", rig_id=rig_id)
        await make_frame(
            conn,
            project_a,
            "night-2",
            rig_id=rig_id,
            date_obs_utc="2026-11-02T03:00:00+00:00",
        )
        await conn.executemany(
            "INSERT INTO session (project_id, rig_id, start_utc) VALUES (?, ?, ?)",
            (
                (project_a, rig_id, "2026-11-01T03:00:00+00:00"),
                (project_a, rig_id, "2026-11-02T03:00:00+00:00"),
            ),
        )
        await conn.execute(
            """
            INSERT INTO project_session
                (project_id, rig_id, line_name, exposure_seconds, num_subs,
                 session_date, source)
            VALUES (?, ?, 'Lum', 60, 1, '2026-11-03', 'manual')
            """,
            (project_a, rig_id),
        )
        await conn.execute(
            "INSERT INTO project_source_folder (project_id, path, rig_id) VALUES (?, ?, ?)",
            (project_b, "/synthetic/project-b", rig_id),
        )

        source = (
            await conn.execute(
                """
            INSERT INTO dso_catalog_source
                (source_id, category, display_name, file_path, file_hash)
            VALUES ('test', 'nightcrate', 'Test', '/synthetic/catalog.csv', 'hash')
            """
            )
        ).lastrowid
        dso = (
            await conn.execute(
                """
            INSERT INTO dso
                (primary_designation, obj_type, source_catalog_id, source_row_hash)
            VALUES ('Object A', 'Other', ?, 'row-hash')
            """,
                (source,),
            )
        ).lastrowid
        await conn.execute("INSERT INTO favorite_target (dso_id) VALUES (?)", (dso,))
        location = (
            await conn.execute(
                """
            INSERT INTO location (name, latitude, longitude, timezone)
            VALUES ('Test location', 33.4484, -112.0740, 'America/Phoenix')
            """
            )
        ).lastrowid
        horizon = (
            await conn.execute(
                """
            INSERT INTO location_horizon
                (location_id, name, type, flat_altitude_deg, is_default)
            VALUES (?, 'Flat', 'artificial', 0, 1)
            """,
                (location,),
            )
        ).lastrowid
        await conn.execute(
            "INSERT INTO target_plan (dso_id, location_id, horizon_id, rig_id) VALUES (?, ?, ?, ?)",
            (dso, location, horizon, planned_rig),
        )

        assert await rig_usage(conn, rig_id) == RigUsage(2, 3)
        assert await rig_usage(conn, planned_rig) == RigUsage(0, 0)


@pytest.mark.asyncio
async def test_rig_usage_counts_session_nights(rig_db: Path):
    async with aiosqlite.connect(rig_db) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        equipment = await make_equipment(conn)
        rig_id = await make_rig(conn, equipment, "Session rig")
        project_id = await make_project(conn)
        await conn.execute(
            "INSERT INTO session (project_id, rig_id, start_utc) VALUES (?, ?, ?)",
            (project_id, rig_id, "2026-11-04T03:00:00+00:00"),
        )

        assert await rig_usage(conn, rig_id) == RigUsage(1, 1)


@pytest.mark.asyncio
async def test_rig_usage_counts_untagged_one_rig_nights(rig_db: Path):
    async with aiosqlite.connect(rig_db) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        equipment = await make_equipment(conn)
        rig_1 = await make_rig(conn, equipment, "Main rig")
        rig_2 = await make_rig(conn, equipment, "Travel rig")
        project_id = await make_project(conn)
        await conn.execute("INSERT INTO project_rig VALUES (?, ?)", (project_id, rig_1))
        await make_frame(conn, project_id, "night-1", rig_id=None)
        await make_frame(
            conn,
            project_id,
            "night-2",
            rig_id=None,
            date_obs_utc="2026-11-02T03:00:00+00:00",
        )

        assert await rig_usage(conn, rig_1) == RigUsage(1, 2)

        await conn.execute("INSERT INTO project_rig VALUES (?, ?)", (project_id, rig_2))
        assert await rig_usage(conn, rig_1) == RigUsage(1, 0)


@pytest.mark.asyncio
async def test_rig_usage_counts_derived_batches_without_frames(rig_db: Path):
    async with aiosqlite.connect(rig_db) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        equipment = await make_equipment(conn)
        rig_id = await make_rig(conn, equipment, "Main rig")
        project_id = await make_project(conn)
        await conn.executemany(
            """
            INSERT INTO project_session
                (project_id, rig_id, line_name, exposure_seconds, num_subs,
                 session_date, source)
            VALUES (?, ?, 'Lum', 60, 1, ?, 'auto')
            """,
            [
                (project_id, rig_id, "2026-11-01"),
                (project_id, rig_id, "2026-11-02"),
                (project_id, rig_id, "2026-11-03"),
            ],
        )

        assert await rig_usage(conn, rig_id) == RigUsage(1, 3)


@pytest.mark.asyncio
async def test_save_earlier_setup_stamps_existing_rows(rig_db: Path):
    async with aiosqlite.connect(rig_db) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        equipment = await make_equipment(conn)
        rig_id = await make_rig(conn, equipment, "Main rig")
        other_rig = await make_rig(conn, equipment, "Travel rig", camera_id=equipment.camera_b)
        project_id = await make_project(conn)
        f1 = await make_frame(conn, project_id, "f1", rig_id=rig_id)
        f2 = await make_frame(conn, project_id, "f2", rig_id=rig_id)
        f3 = await make_frame(conn, project_id, "f3", rig_id=other_rig)
        await conn.execute(
            "INSERT INTO rig_filter_slot (rig_id, slot_number, filter_id) VALUES (?, 1, ?)",
            (rig_id, equipment.filter_l),
        )
        await conn.execute(
            "INSERT INTO rig_software (rig_id, software_id) VALUES (?, ?)",
            (rig_id, equipment.software),
        )
        batch = (
            await conn.execute(
                """
            INSERT INTO project_session
                (project_id, rig_id, line_name, exposure_seconds, num_subs)
            VALUES (?, ?, 'Lum', 60, 2)
            """,
                (project_id, rig_id),
            )
        ).lastrowid
        setup_id = await save_earlier_setup(conn, rig_id, until_at="2026-11-07T12:00:00+00:00")
        stamps = await conn.execute_fetchall(
            "SELECT sub_frame_id, rig_setup_id FROM sub_frame_rig_setup ORDER BY sub_frame_id"
        )
        assert [tuple(row) for row in stamps] == [(f1, setup_id), (f2, setup_id)]
        assert f3 not in {row[0] for row in stamps}
        row = await (
            await conn.execute("SELECT rig_setup_id FROM project_session WHERE id = ?", (batch,))
        ).fetchone()
        assert row["rig_setup_id"] == setup_id
        parts = await read_setup_parts(conn, setup_id)
        assert parts.filter_slots == frozenset(((1, equipment.filter_l),))
        assert parts.software_ids == frozenset((equipment.software,))


@pytest.mark.asyncio
async def test_untagged_frames_stamped_in_one_rig_project(rig_db: Path):
    async with aiosqlite.connect(rig_db) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        equipment = await make_equipment(conn)
        rig_1 = await make_rig(conn, equipment, "Main rig")
        rig_2 = await make_rig(conn, equipment, "Travel rig")
        one_rig_project = await make_project(conn)
        two_rig_project = await make_project(conn, "Project B")
        await conn.execute("INSERT INTO project_rig VALUES (?, ?)", (one_rig_project, rig_1))
        await conn.executemany(
            "INSERT INTO project_rig VALUES (?, ?)",
            ((two_rig_project, rig_1), (two_rig_project, rig_2)),
        )
        one_frame = await make_frame(conn, one_rig_project, "one", rig_id=None)
        two_frame = await make_frame(conn, two_rig_project, "two", rig_id=None)
        setup_id = await save_earlier_setup(conn, rig_1, until_at="2026-11-07T12:00:00+00:00")
        rows = await conn.execute_fetchall(
            "SELECT sub_frame_id, rig_setup_id FROM sub_frame_rig_setup"
        )
        assert [tuple(row) for row in rows] == [(one_frame, setup_id)]
        assert two_frame not in {row[0] for row in rows}


@pytest.mark.asyncio
async def test_stamp_per_rig_survives_other_rig_split(rig_db: Path):
    async with aiosqlite.connect(rig_db) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        equipment = await make_equipment(conn)
        rig_1 = await make_rig(conn, equipment, "Main rig", camera_id=equipment.camera_a)
        rig_2 = await make_rig(conn, equipment, "Travel rig", camera_id=equipment.camera_c)
        project_id = await make_project(conn)
        frame_id = await make_frame(conn, project_id, "f1", rig_id=rig_1)
        setup_1 = await save_earlier_setup(conn, rig_1, until_at="2026-11-07T12:00:00+00:00")
        await conn.execute("UPDATE rig SET camera_id = ? WHERE id = ?", (equipment.camera_b, rig_1))
        await conn.execute("UPDATE sub_frame SET rig_id = ? WHERE id = ?", (rig_2, frame_id))
        setup_2 = await save_earlier_setup(conn, rig_2, until_at="2026-11-08T12:00:00+00:00")
        await conn.execute("UPDATE rig SET camera_id = ? WHERE id = ?", (equipment.camera_d, rig_2))
        await conn.execute("UPDATE sub_frame SET rig_id = ? WHERE id = ?", (rig_1, frame_id))
        stamps = await conn.execute_fetchall(
            "SELECT rig_id, rig_setup_id FROM sub_frame_rig_setup WHERE sub_frame_id = ?",
            (frame_id,),
        )
        assert {tuple(row) for row in stamps} == {(rig_1, setup_1), (rig_2, setup_2)}
        row = await (
            await conn.execute(
                "SELECT camera_id FROM sub_frame_equipment WHERE sub_frame_id = ?", (frame_id,)
            )
        ).fetchone()
        assert row["camera_id"] == equipment.camera_a


@pytest.mark.asyncio
async def test_guide_camera_correction_ignores_guider(rig_db: Path):
    async with aiosqlite.connect(rig_db) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        equipment = await make_equipment(conn)
        rig_id = await make_rig(conn, equipment, "Main rig")
        setup_id = await save_earlier_setup(conn, rig_id, until_at="2026-11-07T12:00:00+00:00")
        await conn.execute(
            "UPDATE rig SET oag_id = NULL, guide_scope_id = ? WHERE id = ?",
            (equipment.guide_scope, rig_id),
        )
        old = await read_rig_parts(conn, rig_id)
        new = replace(old, guide_camera_id=equipment.camera_b)
        assert await apply_correction_to_earlier_setups(conn, rig_id, old, new) == 1
        corrected = await read_setup_parts(conn, setup_id)
        assert corrected.oag_id == equipment.oag
        assert corrected.guide_scope_id is None
        assert corrected.guide_camera_id == equipment.camera_b


@pytest.mark.asyncio
async def test_two_splits_then_correction(rig_db: Path):
    async with aiosqlite.connect(rig_db) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        equipment = await make_equipment(conn)
        rig_id = await make_rig(conn, equipment, "Main rig", camera_id=equipment.camera_a)
        await conn.execute(
            "INSERT INTO rig_filter_slot (rig_id, slot_number, filter_id) VALUES (?, 1, ?)",
            (rig_id, equipment.filter_l),
        )
        project_id = await make_project(conn)
        f1 = await make_frame(conn, project_id, "f1", rig_id=rig_id)
        f2 = await make_frame(conn, project_id, "f2", rig_id=rig_id)
        setup_1 = await save_earlier_setup(conn, rig_id, until_at="2026-11-07T12:00:00+00:00")
        await conn.execute(
            "UPDATE rig SET camera_id = ? WHERE id = ?", (equipment.camera_b, rig_id)
        )
        f3 = await make_frame(conn, project_id, "f3", rig_id=rig_id)
        setup_2 = await save_earlier_setup(conn, rig_id, until_at="2026-11-08T12:00:00+00:00")
        await conn.execute(
            "UPDATE rig SET camera_id = ? WHERE id = ?", (equipment.camera_c, rig_id)
        )
        assert [
            tuple(row)
            for row in await conn.execute_fetchall(
                "SELECT sub_frame_id, rig_setup_id FROM sub_frame_rig_setup ORDER BY sub_frame_id"
            )
        ] == [(f1, setup_1), (f2, setup_1), (f3, setup_2)]

        old = await read_rig_parts(conn, rig_id)
        new_filters = replace(old, filter_slots=frozenset(((1, equipment.filter_ha),)))
        assert await apply_correction_to_earlier_setups(conn, rig_id, old, new_filters) == 2
        assert (await read_setup_parts(conn, setup_1)).filter_slots == frozenset(
            ((1, equipment.filter_ha),)
        )
        assert (await read_setup_parts(conn, setup_2)).filter_slots == frozenset(
            ((1, equipment.filter_ha),)
        )
        new_camera = replace(old, camera_id=equipment.camera_d)
        assert await apply_correction_to_earlier_setups(conn, rig_id, old, new_camera) == 0


@pytest.mark.asyncio
async def test_correction_skips_setup_with_other_value(rig_db: Path):
    async with aiosqlite.connect(rig_db) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        equipment = await make_equipment(conn)
        rig_id = await make_rig(conn, equipment, "Main rig")
        await conn.execute(
            "INSERT INTO rig_filter_slot (rig_id, slot_number, filter_id) VALUES (?, 1, ?)",
            (rig_id, equipment.filter_r),
        )
        setup_id = await save_earlier_setup(conn, rig_id, until_at="2026-11-07T12:00:00+00:00")
        current = await read_rig_parts(conn, rig_id)
        old = replace(current, filter_slots=frozenset(((1, equipment.filter_l),)))
        new = replace(current, filter_slots=frozenset(((1, equipment.filter_ha),)))
        assert await apply_correction_to_earlier_setups(conn, rig_id, old, new) == 0
        assert (await read_setup_parts(conn, setup_id)).filter_slots == frozenset(
            ((1, equipment.filter_r),)
        )
