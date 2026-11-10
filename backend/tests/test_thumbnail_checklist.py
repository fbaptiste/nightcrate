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
    await conn.commit()
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


async def test_thumbnail_route_accepts_checklist(monkeypatch):
    async with get_db() as conn:
        dso_id = await _dso(conn)
    mocked = AsyncMock(
        side_effect=[
            ThumbnailResult(body=b"png", content_type="image/png", status="placeholder"),
            ThumbnailResult(body=b"jpeg", content_type="image/jpeg", status="hit"),
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
    assert first.status_code == 202
    assert first.headers["cache-control"].startswith("no-store")
    assert second.status_code == 200
    assert second.headers["cache-control"] == "public, max-age=86400"
