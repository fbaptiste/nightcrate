"""Tests for the Target Planner thumbnail cache service.

Uses the conftest-provided autouse ``_test_db`` fixture, which routes
``nightcrate.db.session`` at a tmp SQLite DB and applies every migration
≥ 0005 — that already includes the thumbnail_cache table (0017), so
these tests reuse ``get_db()`` instead of hand-rolling schema.
"""

from __future__ import annotations

import pytest

from nightcrate.db.session import get_db
from nightcrate.services import thumbnails

# Minimum JPEG body (SOI magic + filler) — clears ``_MIN_BODY`` logic in
# ``fetch_hips_image`` without needing real image bytes.
_FAKE_JPEG = b"\xff\xd8" + b"padding-content" * 200


class FakeResponse:
    def __init__(self, *, status_code: int = 200, body: bytes = b""):
        self.status_code = status_code
        self.content = body


@pytest.fixture
def fake_hips(monkeypatch):
    """Drop-in replacement for the underlying HTTPS fetch."""
    mapping: dict[str, object] = {}

    async def fake_get(url, *args, **kwargs):
        for prefix, handler in mapping.items():
            if prefix in url:
                return handler() if callable(handler) else handler
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr("nightcrate.services.hips_client.http_client.get", fake_get)
    return {"mapping": mapping}


@pytest.fixture(autouse=True)
def _redirect_thumb_dir(tmp_path, monkeypatch):
    """Steer ``APP_DIR/thumbnails`` into the test's tmp_path."""
    monkeypatch.setattr("nightcrate.services.thumbnails.APP_DIR", tmp_path)


@pytest.fixture(autouse=True)
async def _drain_in_flight():
    """Background fetches carry over across tests if we don't drain them."""
    yield
    for key, task in list(thumbnails._in_flight.items()):
        task.cancel()
        try:
            await task
        except BaseException:  # noqa: BLE001 — cleanup
            pass
        thumbnails._in_flight.pop(key, None)


@pytest.fixture(autouse=True)
async def _seed_dso_rows():
    """thumbnail_cache has a FK to dso(id). Seed enough dummy DSO rows
    (and a source to satisfy ``source_catalog_id``) so the tests can
    reference any dso_id in the range 1..999 freely."""
    async with get_db() as conn:
        await conn.execute(
            """
            INSERT INTO dso_catalog_source
                (source_id, category, display_name, file_path, file_hash)
            VALUES ('test', 'openngc', 'Test', '/dev/null', 'abc')
            """
        )
        cursor = await conn.execute("SELECT id FROM dso_catalog_source WHERE source_id = 'test'")
        row = await cursor.fetchone()
        source_id = int(row["id"])
        # A small bank of dummy DSOs — test IDs only need to fall in this
        # range. INSERTs use explicit primary-key values so the tests can
        # refer to them by literal id (42, 99, 55, …).
        for test_dso_id in (1, 2, 3, 42, 55, 66, 77, 99):
            await conn.execute(
                """
                INSERT INTO dso (id, primary_designation, obj_type,
                    source_catalog_id, source_row_hash)
                VALUES (?, ?, 'G', ?, 'h')
                """,
                (test_dso_id, f"TEST-{test_dso_id}", source_id),
            )
        await conn.commit()
    yield


async def test_miss_returns_placeholder_and_enqueues_fetch(fake_hips):
    # URL-encoded HiPS name — hips2fits encodes the slashes as %2F.
    fake_hips["mapping"]["DSS2%2Fcolor"] = FakeResponse(body=_FAKE_JPEG)

    async with get_db() as conn:
        result = await thumbnails.get_thumbnail(
            conn,
            dso_id=42,
            variant="list",
            ra_deg=10.0,
            dec_deg=20.0,
            maj_axis_arcmin=5.0,
            max_cache_bytes=10 * 1024 * 1024,
            conn_factory=get_db,
        )

    assert result.status == "placeholder"
    assert result.content_type == "image/png"
    assert result.body.startswith(b"\x89PNG")

    # Let the background fetch run.
    for t in list(thumbnails._in_flight.values()):
        await t

    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT source, bytes, fetch_error FROM thumbnail_cache WHERE dso_id = 42"
        )
        row = await cursor.fetchone()
    assert row is not None
    assert row["source"] == "dss2_color"
    assert row["bytes"] == len(_FAKE_JPEG)
    assert row["fetch_error"] is None


async def test_hit_serves_cached_bytes(fake_hips, tmp_path):
    path = tmp_path / "thumbnails" / "99_list_180x180.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_FAKE_JPEG)

    async with get_db() as conn:
        await conn.execute(
            """
            INSERT INTO thumbnail_cache
                (dso_id, variant, width, height, file_path, source, bytes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (99, "list", 180, 180, str(path), "dss2_color", len(_FAKE_JPEG)),
        )
        await conn.commit()

        result = await thumbnails.get_thumbnail(
            conn,
            dso_id=99,
            variant="list",
            ra_deg=0.0,
            dec_deg=0.0,
            maj_axis_arcmin=1.0,
            max_cache_bytes=10 * 1024 * 1024,
            conn_factory=get_db,
        )

    assert result.status == "hit"
    assert result.body == _FAKE_JPEG


async def test_color_failure_falls_back_to_red(fake_hips):
    def _fail_color():
        raise RuntimeError("color offline")

    fake_hips["mapping"]["DSS2%2Fcolor"] = _fail_color
    fake_hips["mapping"]["DSS2%2Fred"] = FakeResponse(body=_FAKE_JPEG)

    async with get_db() as conn:
        await thumbnails.get_thumbnail(
            conn,
            dso_id=55,
            variant="list",
            ra_deg=10.0,
            dec_deg=20.0,
            maj_axis_arcmin=5.0,
            max_cache_bytes=10 * 1024 * 1024,
            conn_factory=get_db,
        )

    for t in list(thumbnails._in_flight.values()):
        await t

    async with get_db() as conn:
        cursor = await conn.execute("SELECT source FROM thumbnail_cache WHERE dso_id = 55")
        row = await cursor.fetchone()
    assert row["source"] == "dss2_red"


async def test_double_failure_records_fetch_error_row(fake_hips):
    def _fail():
        raise RuntimeError("upstream dead")

    fake_hips["mapping"]["DSS2%2Fcolor"] = _fail
    fake_hips["mapping"]["DSS2%2Fred"] = _fail

    async with get_db() as conn:
        await thumbnails.get_thumbnail(
            conn,
            dso_id=66,
            variant="list",
            ra_deg=10.0,
            dec_deg=20.0,
            maj_axis_arcmin=5.0,
            max_cache_bytes=10 * 1024 * 1024,
            conn_factory=get_db,
        )

    for t in list(thumbnails._in_flight.values()):
        await t

    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT source, bytes, fetch_error FROM thumbnail_cache WHERE dso_id = 66"
        )
        row = await cursor.fetchone()
    assert row["source"] == "placeholder"
    assert row["bytes"] == 0
    assert row["fetch_error"] is not None


async def test_error_row_returns_error_during_backoff(fake_hips):
    """After a fetch_error row exists, subsequent polls short-circuit to
    the 204 error path without kicking off a new fetch."""
    async with get_db() as conn:
        await conn.execute(
            """
            INSERT INTO thumbnail_cache
                (dso_id, variant, width, height, file_path, source, bytes, fetch_error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (77, "list", 180, 180, "/dev/null", "placeholder", 0, "color: boom; red: boom"),
        )
        await conn.commit()

        result = await thumbnails.get_thumbnail(
            conn,
            dso_id=77,
            variant="list",
            ra_deg=0.0,
            dec_deg=0.0,
            maj_axis_arcmin=1.0,
            max_cache_bytes=10 * 1024 * 1024,
            conn_factory=get_db,
        )
    assert result.status == "error"


async def test_lru_eviction_drops_oldest(tmp_path):
    """Set an impossibly small budget and verify the oldest row is dropped."""
    thumb_dir = tmp_path / "thumbnails"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    old_path = thumb_dir / "1_list_180x180.jpg"
    new_path = thumb_dir / "2_list_180x180.jpg"
    old_path.write_bytes(b"x" * 1000)
    new_path.write_bytes(b"x" * 1000)

    async with get_db() as conn:
        await conn.execute(
            "INSERT INTO thumbnail_cache (dso_id, variant, width, height, "
            "file_path, source, bytes, last_access_at) VALUES "
            "(?, ?, ?, ?, ?, ?, ?, '2024-01-01 00:00:00')",
            (1, "list", 180, 180, str(old_path), "dss2_color", 1000),
        )
        await conn.execute(
            "INSERT INTO thumbnail_cache (dso_id, variant, width, height, "
            "file_path, source, bytes) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (2, "list", 180, 180, str(new_path), "dss2_color", 1000),
        )
        await conn.commit()

        evicted = await thumbnails._evict_lru(conn, max_bytes=1500)
        assert evicted == 1
        cursor = await conn.execute("SELECT dso_id FROM thumbnail_cache")
        remaining = {int(r[0]) for r in await cursor.fetchall()}

    assert not old_path.exists()
    assert new_path.exists()
    assert remaining == {2}


async def test_clear_cache_deletes_all(tmp_path):
    thumb_dir = tmp_path / "thumbnails"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    f = thumb_dir / "3_list_180x180.jpg"
    f.write_bytes(_FAKE_JPEG)

    async with get_db() as conn:
        await conn.execute(
            "INSERT INTO thumbnail_cache (dso_id, variant, width, height, "
            "file_path, source, bytes) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (3, "list", 180, 180, str(f), "dss2_color", len(_FAKE_JPEG)),
        )
        await conn.commit()

        deleted = await thumbnails.clear_cache(conn)
        cursor = await conn.execute("SELECT COUNT(*) AS n FROM thumbnail_cache")
        row = await cursor.fetchone()

    assert deleted == 1
    assert not f.exists()
    assert row["n"] == 0


def test_compute_fov_deg_uses_minimum_when_size_missing():
    assert thumbnails.compute_fov_deg("list", None) == 0.1
    assert thumbnails.compute_fov_deg("detail", None) == 0.5


def test_compute_fov_deg_scales_with_major_axis():
    # 30' major axis → 0.5 deg. × 1.5 multiplier = 0.75 deg for list variant.
    assert thumbnails.compute_fov_deg("list", 30.0) == pytest.approx(0.75, abs=1e-3)
    assert thumbnails.compute_fov_deg("detail", 30.0) == pytest.approx(1.25, abs=1e-3)
