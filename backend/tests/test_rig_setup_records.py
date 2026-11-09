"""Record-level setup history regressions for frames, batches, and solves."""

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.api.project_solve import _load_focal_length_estimates
from nightcrate.db.session import get_db
from nightcrate.main import app
from nightcrate.services.rig_setups import save_earlier_setup
from tests.catalog_helpers import _frames, _write_fits
from tests.rig_setup_fixtures import make_equipment, make_frame, make_project, make_rig


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


async def _base(*, tagged: bool = True, frame_count: int = 0):
    async with get_db() as conn:
        equipment = await make_equipment(conn)
        rig_id = await make_rig(conn, equipment, "Record Rig")
        project_id = await make_project(conn, "Record Project")
        await conn.execute(
            "INSERT INTO project_rig (project_id, rig_id) VALUES (?, ?)",
            (project_id, rig_id),
        )
        frame_ids = []
        for index in range(frame_count):
            frame_ids.append(
                await make_frame(
                    conn,
                    project_id,
                    f"record-{index}",
                    rig_id=rig_id if tagged else None,
                    date_obs_utc=f"2026-11-{index + 1:02d}T03:00:00+00:00",
                )
            )
        await conn.commit()
    return equipment, rig_id, project_id, frame_ids


async def _split(rig_id: int, camera_id: int) -> int:
    async with get_db() as conn:
        setup_id = await save_earlier_setup(conn, rig_id, until_at="2026-11-07 12:00:00")
        await conn.execute("UPDATE rig SET camera_id = ? WHERE id = ?", (camera_id, rig_id))
        await conn.commit()
        return setup_id


async def _derive(client: AsyncClient, project_id: int):
    response = await client.post(f"/api/projects/{project_id}/sessions/derive")
    assert response.status_code == 200, response.text
    sessions = await client.get(f"/api/projects/{project_id}/sessions")
    assert sessions.status_code == 200
    return sessions.json()


async def test_derive_splits_batches_by_setup(client):
    equipment, rig_id, project_id, frame_ids = await _base(frame_count=1)
    setup_id = await _split(rig_id, equipment.camera_b)
    async with get_db() as conn:
        current_id = await make_frame(
            conn,
            project_id,
            "same-night-current",
            rig_id=rig_id,
            date_obs_utc="2026-11-01T04:00:00+00:00",
        )
        await conn.commit()

    sessions = await _derive(client, project_id)
    assert len(sessions) == 2
    assert {(row["rig_setup_id"], row["num_subs"]) for row in sessions} == {
        (setup_id, 1),
        (None, 1),
    }
    assert set(frame_ids + [current_id])


async def test_untagged_single_rig_project_keeps_setups(client):
    equipment, rig_id, project_id, frame_ids = await _base(tagged=False, frame_count=2)
    await _derive(client, project_id)
    setup_id = await _split(rig_id, equipment.camera_b)
    sessions = await _derive(client, project_id)
    assert {row["rig_setup_id"] for row in sessions} == {setup_id}
    assert all(row["pixel_scale_arcsec"] is None for row in await _frames(client, project_id))

    moved = await client.put(
        f"/api/projects/{project_id}/sessions/{sessions[0]['id']}/setup",
        json={"rig_setup_id": None},
    )
    assert moved.status_code == 200, moved.text
    sessions = await _derive(client, project_id)
    assert {row["rig_setup_id"] for row in sessions} == {setup_id, None}
    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT sub_frame_id, rig_setup_id FROM sub_frame_rig_setup "
            "WHERE rig_id = ? ORDER BY sub_frame_id",
            (rig_id,),
        )
        stamps = {row["sub_frame_id"]: row["rig_setup_id"] for row in await cursor.fetchall()}
    assert len(stamps) == 1
    assert set(stamps).issubset(frame_ids)


async def test_second_project_rig_then_tag_restores_setup(client):
    equipment, rig_id, project_id, frame_ids = await _base(tagged=False, frame_count=1)
    setup_id = await _split(rig_id, equipment.camera_b)
    async with get_db() as conn:
        rig_2 = await make_rig(conn, equipment, "Second Rig", camera_id=equipment.camera_c)
        await conn.execute(
            "INSERT INTO project_rig (project_id, rig_id) VALUES (?, ?)",
            (project_id, rig_2),
        )
        await conn.commit()
    sessions = await _derive(client, project_id)
    assert [(row["rig_id"], row["rig_setup_id"]) for row in sessions] == [(None, None)]

    async with get_db() as conn:
        await conn.execute("UPDATE sub_frame SET rig_id = ? WHERE id = ?", (rig_id, frame_ids[0]))
        await conn.commit()
    sessions = await _derive(client, project_id)
    assert [(row["rig_id"], row["rig_setup_id"]) for row in sessions] == [(rig_id, setup_id)]


async def test_manual_batch_rig_change_clears_foreign_stamp(client):
    equipment, rig_id, project_id, _frame_ids = await _base()
    setup_id = await _split(rig_id, equipment.camera_b)
    async with get_db() as conn:
        rig_2 = await make_rig(conn, equipment, "Other Rig", camera_id=equipment.camera_c)
        await conn.commit()
    created = await client.post(
        f"/api/projects/{project_id}/sessions",
        json={
            "rig_id": rig_id,
            "rig_setup_id": setup_id,
            "line_name": "Ha",
            "exposure_seconds": 60,
            "num_subs": 2,
        },
    )
    changed = await client.patch(
        f"/api/projects/{project_id}/sessions/{created.json()['id']}", json={"rig_id": rig_2}
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["rig_setup_id"] is None


async def test_setup_move_rejects_other_projects_batch(client):
    equipment, rig_id, project_id, _frame_ids = await _base()
    setup_id = await _split(rig_id, equipment.camera_b)
    other = await client.post("/api/projects", json={"name": "Other Project"})
    batch = await client.post(
        f"/api/projects/{project_id}/sessions",
        json={"rig_id": rig_id, "line_name": "Ha", "exposure_seconds": 60, "num_subs": 1},
    )
    response = await client.put(
        f"/api/projects/{other.json()['id']}/sessions/{batch.json()['id']}/setup",
        json={"rig_setup_id": setup_id},
    )
    assert response.status_code == 404


async def test_move_derived_night_restamps_frames_and_rederive_keeps_it(client):
    equipment, rig_id, project_id, frame_ids = await _base(frame_count=2)
    setup_id = await _split(rig_id, equipment.camera_b)
    async with get_db() as conn:
        await conn.execute("DELETE FROM sub_frame_rig_setup")
        await conn.commit()
    sessions = await _derive(client, project_id)
    selected = sessions[0]
    response = await client.put(
        f"/api/projects/{project_id}/sessions/{selected['id']}/setup",
        json={"rig_setup_id": setup_id},
    )
    assert response.status_code == 200, response.text
    sessions = await _derive(client, project_id)
    moved_night = selected["session_date"]
    moved = next(row for row in sessions if row["session_date"] == moved_night)
    assert moved["rig_setup_id"] == setup_id
    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT sub_frame_id FROM sub_frame_rig_setup WHERE rig_id = ?", (rig_id,)
        )
        stamped = {row["sub_frame_id"] for row in await cursor.fetchall()}
    assert stamped and stamped.issubset(frame_ids)


async def test_move_night_moves_its_calibration_frames(client):
    equipment, rig_id, project_id, _frame_ids = await _base()
    async with get_db() as conn:
        frame_ids = {
            frame_type: await make_frame(
                conn,
                project_id,
                f"night-with-{frame_type}",
                rig_id=rig_id,
                frame_type=frame_type,
            )
            for frame_type in ("light", "dark", "flat", "bias")
        }
        await conn.commit()
    setup_id = await _split(rig_id, equipment.camera_b)
    session = (await _derive(client, project_id))[0]

    async def assert_stamps_and_matches(expected_setup_id):
        async with get_db() as conn:
            cursor = await conn.execute(
                "SELECT sub_frame_id, rig_setup_id FROM sub_frame_rig_setup WHERE rig_id = ?",
                (rig_id,),
            )
            stamps = {row["sub_frame_id"]: row["rig_setup_id"] for row in await cursor.fetchall()}
            if expected_setup_id is None:
                assert not set(frame_ids.values()) & set(stamps)
            else:
                assert {stamps[frame_id] for frame_id in frame_ids.values()} == {expected_setup_id}
            for view, column, frame_type in (
                ("matching_darks", "dark_id", "dark"),
                ("matching_flats", "flat_id", "flat"),
                ("matching_bias", "bias_id", "bias"),
            ):
                cursor = await conn.execute(
                    f"SELECT {column} FROM {view} WHERE light_id = ?",  # nosec B608 - test allow-list
                    (frame_ids["light"],),
                )
                assert [row[column] for row in await cursor.fetchall()] == [frame_ids[frame_type]]

    moved_current = await client.put(
        f"/api/projects/{project_id}/sessions/{session['id']}/setup",
        json={"rig_setup_id": None},
    )
    assert moved_current.status_code == 200, moved_current.text
    await assert_stamps_and_matches(None)

    moved_earlier = await client.put(
        f"/api/projects/{project_id}/sessions/{session['id']}/setup",
        json={"rig_setup_id": setup_id},
    )
    assert moved_earlier.status_code == 200, moved_earlier.text
    await assert_stamps_and_matches(setup_id)


async def test_move_rejects_other_rigs_setup(client):
    equipment, rig_id, project_id, _frame_ids = await _base()
    async with get_db() as conn:
        other_rig = await make_rig(conn, equipment, "Other Rig", camera_id=equipment.camera_c)
        await conn.commit()
    other_setup = await _split(other_rig, equipment.camera_d)
    batch = await client.post(
        f"/api/projects/{project_id}/sessions",
        json={"rig_id": rig_id, "line_name": "Ha", "exposure_seconds": 60, "num_subs": 1},
    )
    response = await client.put(
        f"/api/projects/{project_id}/sessions/{batch.json()['id']}/setup",
        json={"rig_setup_id": other_setup},
    )
    assert response.status_code == 422


async def test_manual_batch_setup_roundtrip(client):
    equipment, rig_id, project_id, _frame_ids = await _base()
    setup_id = await _split(rig_id, equipment.camera_b)
    created = await client.post(
        f"/api/projects/{project_id}/sessions",
        json={
            "rig_id": rig_id,
            "rig_setup_id": setup_id,
            "line_name": "Ha",
            "exposure_seconds": 60,
            "num_subs": 1,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["rig_setup_id"] == setup_id
    assert created.json()["setup_until_at"] == "2026-11-07 12:00:00"


async def test_focal_estimates_per_setup():
    equipment, rig_id, project_id, _frame_ids = await _base()
    setup_id = await _split(rig_id, equipment.camera_b)
    async with get_db() as conn:
        await conn.executemany(
            "INSERT INTO project_session "
            "(project_id, rig_id, rig_setup_id, line_name, exposure_seconds, "
            "num_subs, session_date) "
            "VALUES (?, ?, ?, 'Ha', 60, 1, ?)",
            (
                (project_id, rig_id, setup_id, "2026-11-01"),
                (project_id, rig_id, None, "2026-11-02"),
            ),
        )
        estimates = await _load_focal_length_estimates(conn, project_id, 0.9)
    values = [(item.rig_setup_id, round(item.estimated_focal_length_mm, 1)) for item in estimates]
    assert values == [
        (None, 861.7),
        (setup_id, 550.0),
    ]


async def test_rescan_through_scan_endpoint_keeps_stamps(client, tmp_path):
    equipment, rig_id, project_id, _frame_ids = await _base()
    folder = tmp_path / "lights"
    folder.mkdir()
    _write_fits(folder / "old.fits", date_obs="2026-11-01T03:00:00")
    bound = await client.post(
        f"/api/projects/{project_id}/folders", json={"path": str(folder), "rig_id": rig_id}
    )
    assert bound.status_code == 201, bound.text
    scan = await client.post(f"/api/projects/{project_id}/ingest")
    assert scan.status_code == 200, scan.text

    split = await client.put(
        f"/api/rigs/{rig_id}",
        json={"camera_id": equipment.camera_b, "apply_mode": "from_now_on"},
    )
    assert split.status_code == 200, split.text
    async with get_db() as conn:
        other_rig = await make_rig(conn, equipment, "Retag Rig", camera_id=equipment.camera_c)
        await conn.commit()
    retagged = await client.patch(
        f"/api/projects/{project_id}/folders/{bound.json()['id']}", json={"rig_id": other_rig}
    )
    assert retagged.status_code == 200
    assert round((await _frames(client, project_id))[0]["pixel_scale_arcsec"], 2) == 1.09
    restored = await client.patch(
        f"/api/projects/{project_id}/folders/{bound.json()['id']}", json={"rig_id": rig_id}
    )
    assert restored.status_code == 200
    assert round((await _frames(client, project_id))[0]["pixel_scale_arcsec"], 2) == 0.90

    _write_fits(folder / "new.fits", date_obs="2026-11-02T03:00:00")
    scan = await client.post(f"/api/projects/{project_id}/ingest")
    assert scan.status_code == 200, scan.text

    rows = await _frames(client, project_id)
    by_name = {row["path"].rsplit("/", 1)[-1]: row for row in rows}
    assert round(by_name["old.fits"]["pixel_scale_arcsec"], 2) == 0.90
    assert round(by_name["new.fits"]["pixel_scale_arcsec"], 2) == 1.41
    assert by_name["old.fits"]["full_scale_adu"] == 4095
    assert by_name["new.fits"]["full_scale_adu"] == 65535

    async with get_db() as conn:
        await conn.execute(
            "UPDATE sub_frame SET hfr = CASE WHEN id = ? THEN 2.0 ELSE 1.0 END",
            (by_name["old.fits"]["id"],),
        )
        await conn.commit()
    ordered = await _frames(client, project_id, sort="hfr_arcsec_desc")
    assert ordered[0]["id"] == by_name["old.fits"]["id"]
