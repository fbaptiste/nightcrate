from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.db.session import get_db
from nightcrate.main import app
from nightcrate.services import thumbnails
from nightcrate.services.thumbnails import ChecklistRender, ThumbnailResult


def test_checklist_extent():
    assert thumbnails.compute_angular_extent_deg(
        "checklist", dso_maj_axis_arcmin=190
    ) == pytest.approx(4.75)
    assert thumbnails.compute_angular_extent_deg(
        "checklist", dso_maj_axis_arcmin=2.5
    ) == pytest.approx(0.15)
    assert thumbnails.compute_angular_extent_deg(
        "checklist", dso_maj_axis_arcmin=None
    ) == pytest.approx(0.15)
    assert thumbnails.compute_angular_extent_deg(
        "checklist", dso_maj_axis_arcmin=10
    ) == pytest.approx(0.25)
    assert thumbnails.dimensions_for("checklist") == thumbnails.ThumbnailDimensions(800, 600)


def test_checklist_descriptor():
    descriptor = ChecklistRender.for_object(10.68471, 41.26875, 190.0)
    assert descriptor.ra_e4 == 106847
    assert descriptor.dec_e4 == 412688
    assert descriptor.field_mdeg == 4750
    assert descriptor.render_key == "r1_ra106847_dec412688_f4750_800x600"
    assert ChecklistRender.from_file_name(descriptor.file_name) == descriptor
    assert ChecklistRender.for_object(10.0001, 0, 10) != ChecklistRender.for_object(10.0004, 0, 10)
    assert ChecklistRender(1, 2, round(0.2494 * 1000)).field_mdeg == 249
    assert ChecklistRender(1, 2, round(0.2496 * 1000)).field_mdeg == 250


def test_checklist_descriptor_for_explicit_field_has_its_own_key():
    descriptor = ChecklistRender.for_field(10.68471, 41.26875, 3.043478)
    assert descriptor.field_mdeg == 3043
    assert descriptor.render_key == "r1_ra106847_dec412688_f3043_800x600"
    assert descriptor != ChecklistRender.for_object(10.68471, 41.26875, 190.0)

    key = thumbnails.make_key(
        1,
        "checklist",
        ra_deg=10.68471,
        dec_deg=41.26875,
        maj_axis_arcmin=190,
        field_deg=3.043478,
    )
    assert key.checklist == descriptor
    assert key.render_key == descriptor.render_key


def test_checklist_render_uses_quantised_values():
    descriptor = ChecklistRender.for_object(10.68471, 41.26875, 190.0)
    assert descriptor.wcs().wcs.crval.tolist() == [
        descriptor.ra_e4 / 10_000,
        descriptor.dec_e4 / 10_000,
    ]
    key = thumbnails.make_key(
        1, "checklist", ra_deg=10.68471, dec_deg=41.26875, maj_axis_arcmin=190
    )
    assert key.checklist == descriptor
    assert key.render_key == descriptor.render_key


def test_list_and_detail_keys_unchanged():
    for variant in ("list", "detail"):
        key = thumbnails.make_key(
            1,
            variant,
            ra_deg=10,
            dec_deg=20,
            fov_major_deg=4,
            fov_minor_deg=3,
            center_ra_deg=11,
            center_dec_deg=21,
        )
        assert key.fov_major_deg_x1000 is None
        assert key.fov_minor_deg_x1000 is None
        assert key.center_ra_deg_x1000 is None
        assert key.center_dec_deg_x1000 is None
        assert key.render_key is None
        assert key.checklist is None


async def _dso(conn, *, maj_axis_arcmin: float = 190) -> int:
    source = await conn.execute(
        """
        INSERT INTO dso_catalog_source
            (source_id, category, display_name, file_path, file_hash)
        VALUES ('checklist-test', 'nightcrate', 'Checklist', '/synthetic', 'hash')
        """
    )
    row = await conn.execute(
        """
        INSERT INTO dso (
            primary_designation, obj_type, ra_deg, dec_deg, maj_axis_arcmin,
            source_catalog_id, source_row_hash, source_key
        ) VALUES ('M 31', 'G', 10.6847, 41.2688, ?, ?, 'row', 'm31')
        """,
        (maj_axis_arcmin, source.lastrowid),
    )
    await conn.execute(
        """
        INSERT INTO dso_designation
            (dso_id, catalog, identifier, display_form, search_key, is_primary)
        VALUES (?, 'messier', '31', 'M 31', 'm31', 1)
        """,
        (row.lastrowid,),
    )
    await conn.commit()
    return int(row.lastrowid)


async def _rig(conn, name: str) -> int:
    equipment = await (
        await conn.execute(
            """
            SELECT tc.id AS configuration_id, c.id AS camera_id
            FROM telescope_configuration tc
            CROSS JOIN camera c
            JOIN sensor s ON s.id = c.sensor_id
            WHERE tc.effective_focal_length_mm IS NOT NULL
            ORDER BY tc.id, c.id
            LIMIT 1
            """
        )
    ).fetchone()
    row = await conn.execute(
        """
        INSERT INTO rig (name, telescope_configuration_id, camera_id)
        VALUES (?, ?, ?)
        """,
        (name, equipment["configuration_id"], equipment["camera_id"]),
    )
    return int(row.lastrowid)


async def test_checklist_filename_round_trips_through_rehydrate(tmp_path):
    descriptor = ChecklistRender.for_object(10.6847, 41.2688, 190)
    cache_dir = tmp_path / "thumbnails"
    cache_dir.mkdir()
    (cache_dir / descriptor.file_name).write_bytes(b"j" * 256)
    async with get_db() as conn:
        dso_id = await _dso(conn)
        assert await thumbnails.rehydrate_from_disk(conn) == 1
        row = await (
            await conn.execute("SELECT render_key FROM thumbnail_cache WHERE dso_id = ?", (dso_id,))
        ).fetchone()
        assert row["render_key"] == descriptor.render_key

        result = await thumbnails.get_thumbnail(
            conn,
            dso_id=dso_id,
            variant="checklist",
            ra_deg=10.6847,
            dec_deg=41.2688,
            maj_axis_arcmin=190,
            max_cache_bytes=1024 * 1024,
            conn_factory=get_db,
        )
    assert result.status == "hit"
    assert result.body == b"j" * 256


def test_checklist_changed_size_and_revision_change_keys(monkeypatch):
    first = thumbnails.make_key(1, "checklist", ra_deg=10, dec_deg=20, maj_axis_arcmin=10)
    changed = thumbnails.make_key(1, "checklist", ra_deg=10, dec_deg=20, maj_axis_arcmin=12)
    assert first.render_key != changed.render_key
    monkeypatch.setattr(thumbnails, "CHECKLIST_FRAMING_REVISION", 2)
    revised = thumbnails.make_key(1, "checklist", ra_deg=10, dec_deg=20, maj_axis_arcmin=10)
    assert revised.render_key == "r2_ra100000_dec200000_f250_800x600"
    assert revised.render_key != first.render_key


async def test_thumbnail_route_owns_rig_field_and_reuses_equal_fields(monkeypatch):
    async with get_db() as conn:
        dso_id = await _dso(conn)
        first_rig = await _rig(conn, "First")
        second_rig = await _rig(conn, "Second")
        await conn.commit()
    mocked = AsyncMock(
        side_effect=[
            ThumbnailResult(body=b"png", content_type="image/png", status="placeholder"),
            ThumbnailResult(body=b"jpeg", content_type="image/jpeg", status="hit"),
            ThumbnailResult(body=b"first", content_type="image/jpeg", status="hit"),
            ThumbnailResult(body=b"second", content_type="image/jpeg", status="hit"),
            ThumbnailResult(body=b"ignored", content_type="image/jpeg", status="hit"),
        ]
    )
    monkeypatch.setattr(thumbnails, "get_thumbnail", mocked)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.get(
            f"/api/planner/thumbnails/{dso_id}", params={"variant": "checklist"}
        )
        second = await client.get(
            f"/api/planner/thumbnails/{dso_id}", params={"variant": "checklist"}
        )
        first_field = await client.get(
            f"/api/planner/thumbnails/{dso_id}",
            params={"variant": "checklist", "rig_id": first_rig},
        )
        second_field = await client.get(
            f"/api/planner/thumbnails/{dso_id}",
            params={"variant": "checklist", "rig_id": second_rig},
        )
        ignored_field = await client.get(
            f"/api/planner/thumbnails/{dso_id}",
            params={"variant": "checklist", "field_deg": 1},
        )
        unknown = await client.get(
            f"/api/planner/thumbnails/{dso_id}",
            params={"variant": "checklist", "rig_id": 999999},
        )
        wrong_variant = await client.get(
            f"/api/planner/thumbnails/{dso_id}",
            params={"variant": "list", "rig_id": first_rig},
        )
        async with get_db() as conn:
            await conn.execute("UPDATE rig SET active = 0 WHERE id = ?", (second_rig,))
            await conn.commit()
        retired = await client.get(
            f"/api/planner/thumbnails/{dso_id}",
            params={"variant": "checklist", "rig_id": second_rig},
        )
    assert first.status_code == 202
    assert first.headers["cache-control"].startswith("no-store")
    assert second.status_code == 200
    assert second.headers["cache-control"] == "public, max-age=86400"
    assert first_field.content == b"first"
    assert second_field.content == b"second"
    first_deg = mocked.await_args_list[2].kwargs["field_deg"]
    second_deg = mocked.await_args_list[3].kwargs["field_deg"]
    assert first_deg == second_deg
    assert thumbnails.make_key(
        dso_id,
        "checklist",
        ra_deg=10.6847,
        dec_deg=41.2688,
        maj_axis_arcmin=190,
        field_deg=first_deg,
    ) == thumbnails.make_key(
        dso_id,
        "checklist",
        ra_deg=10.6847,
        dec_deg=41.2688,
        maj_axis_arcmin=190,
        field_deg=second_deg,
    )
    assert ignored_field.content == b"ignored"
    assert mocked.await_args_list[4].kwargs["field_deg"] is None
    assert unknown.status_code == 404
    assert retired.status_code == 404
    assert wrong_variant.status_code == 422


async def test_thumbnail_route_rejects_stale_render_key_after_rig_edit(monkeypatch):
    async with get_db() as conn:
        dso_id = await _dso(conn)
        rig_id = await _rig(conn, "Edited")
        await conn.commit()

    mocked = AsyncMock(
        return_value=ThumbnailResult(body=b"new", content_type="image/jpeg", status="hit")
    )
    monkeypatch.setattr(thumbnails, "get_thumbnail", mocked)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        before = await client.get("/api/messier", params={"location": "none", "rig_id": rig_id})
        old_key = before.json()["slots"][30]["survey"]["render_key"]

        async with get_db() as conn:
            await conn.execute(
                """
                UPDATE telescope_configuration
                SET effective_focal_length_mm = effective_focal_length_mm * 2
                WHERE id = (
                    SELECT telescope_configuration_id FROM rig WHERE id = ?
                )
                """,
                (rig_id,),
            )
            await conn.commit()

        after = await client.get("/api/messier", params={"location": "none", "rig_id": rig_id})
        new_key = after.json()["slots"][30]["survey"]["render_key"]
        stale = await client.get(
            f"/api/planner/thumbnails/{dso_id}",
            params={"variant": "checklist", "rig_id": rig_id, "render_key": old_key},
        )
        fresh = await client.get(
            f"/api/planner/thumbnails/{dso_id}",
            params={"variant": "checklist", "rig_id": rig_id, "render_key": new_key},
        )

    assert new_key != old_key
    assert stale.status_code == 204
    assert stale.headers["cache-control"] == "no-store"
    assert fresh.status_code == 200
    assert fresh.content == b"new"
    mocked.assert_awaited_once()


async def test_thumbnail_route_rejects_fieldless_and_unsupported_rigs(monkeypatch):
    async with get_db() as conn:
        dso_id = await _dso(conn)
        rig_id = await _rig(conn, "Unsupported")
        await conn.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for field in (None, (0.0276, 0.01), (36.8, 1.0)):
            monkeypatch.setattr(
                "nightcrate.api.planner.rig_fov_from_summary",
                lambda _row, field=field: field,
            )
            response = await client.get(
                f"/api/planner/thumbnails/{dso_id}",
                params={"variant": "checklist", "rig_id": rig_id},
            )
            assert response.status_code == 404
