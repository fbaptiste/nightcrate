"""Integration tests for the v0.18.0 sky-tile cache service.

Mirrors the structure of ``test_planner_thumbnails.py``: uses the
autouse ``_test_db`` fixture (applies every migration including 0020),
mocks ``hips_tiles.render``, and exercises the public
``get_cell`` surface end-to-end.

Key paths covered:
- cache miss → placeholder returned, background fetch scheduled
- cache hit → JPEG bytes + last_access_at refreshed
- long-poll path → holds the request until the fetch lands
- no red-survey fallback when a render fails
- permanent failure → ``fetch_error`` sentinel with 10-minute backoff
- LRU eviction when ``max_cache_bytes`` is exceeded
- orphan-file sweep at startup
- ``clear_cache`` wipes both DB rows and disk
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from nightcrate.db.session import get_db
from nightcrate.services import hips_tiles, sky_tile_cache
from nightcrate.services.sky_tile_cache import (
    _PLACEHOLDER_PNG,
    CellKey,
    clear_cache,
    get_cell,
    make_cell_key,
    rehydrate_from_disk,
    sync_orphan_files,
)
from nightcrate.services.sky_tiles import TIERS

# Synthetic rendered bytes; cache tests patch ``hips_tiles.render`` and do not
# decode this payload.
_FAKE_JPEG = b"\xff\xd8" + b"padding-content" * 200


@pytest.fixture
def fake_hips(monkeypatch):
    state: dict[str, object] = {"calls": 0, "error": None, "delay": 0.0}

    async def fake_render(*args, **kwargs):
        state["calls"] = int(state["calls"]) + 1
        await asyncio.sleep(float(state["delay"]))
        if state["error"] is not None:
            raise state["error"]  # type: ignore[misc]
        return hips_tiles.RenderedImage(_FAKE_JPEG, frozenset({"cds"}))

    monkeypatch.setattr(hips_tiles, "render", fake_render)
    return state


@pytest.fixture(autouse=True)
def _redirect_cell_dir(tmp_path, monkeypatch):
    """Send APP_DIR at the test's tmp_path so cell writes are isolated."""
    monkeypatch.setattr("nightcrate.core.app_config.APP_DIR", tmp_path)


@pytest.fixture(autouse=True)
async def _drain_in_flight():
    sky_tile_cache._failure_backoff.clear()
    yield
    for key, task in list(sky_tile_cache._in_flight.items()):
        task.cancel()
        try:
            await task
        except BaseException:  # noqa: BLE001 — cleanup
            pass
        sky_tile_cache._in_flight.pop(key, None)
    sky_tile_cache._failure_backoff.clear()


def _default_key(cell_i: int = 0, cell_j: int = 0) -> CellKey:
    return make_cell_key(
        hips_survey="CDS/P/DSS2/color",
        healpix_nside=8,
        healpix_ipix=200,
        tier=TIERS["narrow"],
        cell_i=cell_i,
        cell_j=cell_j,
    )


# ── Lookup / hit ─────────────────────────────────────────────────────────────


async def test_miss_returns_placeholder_and_schedules_fetch(fake_hips):
    async with get_db() as conn:
        result = await get_cell(
            conn,
            key=_default_key(),
            region_ra_deg=150.0,
            region_dec_deg=40.0,
            max_cache_bytes=10_000_000,
            conn_factory=get_db,
        )
    assert result.status == "placeholder"
    assert result.content_type == "image/png"
    assert result.body == _PLACEHOLDER_PNG
    # Fetch should have been scheduled.
    assert len(sky_tile_cache._in_flight) == 1


async def test_long_poll_returns_real_image(fake_hips):
    async with get_db() as conn:
        result = await get_cell(
            conn,
            key=_default_key(),
            region_ra_deg=150.0,
            region_dec_deg=40.0,
            max_cache_bytes=10_000_000,
            conn_factory=get_db,
            wait_timeout_s=5.0,
        )
    assert result.status == "hit"
    assert result.content_type == "image/jpeg"
    assert result.body == _FAKE_JPEG


async def test_second_call_is_a_cache_hit(fake_hips):
    async with get_db() as conn:
        await get_cell(
            conn,
            key=_default_key(),
            region_ra_deg=150.0,
            region_dec_deg=40.0,
            max_cache_bytes=10_000_000,
            conn_factory=get_db,
            wait_timeout_s=5.0,
        )
        # Second call uses the cached row — no new fetch required.
        sky_tile_cache._in_flight.clear()
        result = await get_cell(
            conn,
            key=_default_key(),
            region_ra_deg=150.0,
            region_dec_deg=40.0,
            max_cache_bytes=10_000_000,
            conn_factory=get_db,
        )
    assert result.status == "hit"
    assert result.body == _FAKE_JPEG
    assert not sky_tile_cache._in_flight


# ── Fallback + failure ───────────────────────────────────────────────────────


async def test_render_failure_has_no_red_fallback(fake_hips):
    fake_hips["error"] = RuntimeError("all tile sources unavailable")

    async with get_db() as conn:
        result = await get_cell(
            conn,
            key=_default_key(),
            region_ra_deg=150.0,
            region_dec_deg=40.0,
            max_cache_bytes=10_000_000,
            conn_factory=get_db,
            wait_timeout_s=5.0,
        )
    assert result.status == "error"
    async with get_db() as conn:
        cursor = await conn.execute("SELECT source FROM sky_tile_cache")
        row = await cursor.fetchone()
    assert row["source"] == "placeholder"
    assert fake_hips["calls"] == 1


async def test_render_failure_records_backoff_and_suppresses_retries(fake_hips):
    fake_hips["error"] = RuntimeError("boom")

    async with get_db() as conn:
        result = await get_cell(
            conn,
            key=_default_key(),
            region_ra_deg=150.0,
            region_dec_deg=40.0,
            max_cache_bytes=10_000_000,
            conn_factory=get_db,
            wait_timeout_s=5.0,
        )
    # After the long-poll resolves we re-check the cache; the row is a
    # fetch_error sentinel, so status is ``error``.
    assert result.status == "error"
    async with get_db() as conn:
        cursor = await conn.execute("SELECT fetch_error, source FROM sky_tile_cache")
        row = await cursor.fetchone()
    assert row["source"] == "placeholder"
    assert row["fetch_error"] is not None
    async with get_db() as conn:
        repeated = await get_cell(
            conn,
            key=_default_key(),
            region_ra_deg=150.0,
            region_dec_deg=40.0,
            max_cache_bytes=10_000_000,
            conn_factory=get_db,
            wait_timeout_s=5.0,
        )
    assert repeated.status == "error"
    assert fake_hips["calls"] == 1


async def test_write_failure_records_backoff_and_suppresses_retries(fake_hips, monkeypatch):
    key = _default_key()
    final_path = sky_tile_cache._cell_path(key)
    original = type(final_path).write_bytes

    def fail_after_partial_write(path, data):
        if path.name.startswith("."):
            original(path, data[:20])
            raise OSError("simulated interrupted write")
        return original(path, data)

    monkeypatch.setattr(type(final_path), "write_bytes", fail_after_partial_write)
    async with get_db() as conn:
        first = await get_cell(
            conn,
            key=key,
            region_ra_deg=150.0,
            region_dec_deg=40.0,
            max_cache_bytes=10_000_000,
            conn_factory=get_db,
            wait_timeout_s=5.0,
        )
    assert first.status == "error"
    async with get_db() as conn:
        cursor = await conn.execute("SELECT source, fetch_error FROM sky_tile_cache")
        row = await cursor.fetchone()
        second = await get_cell(
            conn,
            key=key,
            region_ra_deg=150.0,
            region_dec_deg=40.0,
            max_cache_bytes=10_000_000,
            conn_factory=get_db,
            wait_timeout_s=5.0,
        )
    assert row["source"] == "placeholder"
    assert "interrupted" in row["fetch_error"]
    assert second.status == "error"
    assert fake_hips["calls"] == 1
    assert not final_path.exists()
    assert not final_path.with_name(f".{final_path.name}.tmp").exists()


async def test_insert_failures_use_in_memory_backoff(fake_hips, monkeypatch):
    insert_sources = []

    async def fail_insert(*args, **kwargs):
        insert_sources.append(kwargs["source"])
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(sky_tile_cache, "_insert_cache_row", fail_insert)
    key = _default_key()
    async with get_db() as conn:
        first = await get_cell(
            conn,
            key=key,
            region_ra_deg=150.0,
            region_dec_deg=40.0,
            max_cache_bytes=10_000_000,
            conn_factory=get_db,
            wait_timeout_s=5.0,
        )
        second = await get_cell(
            conn,
            key=key,
            region_ra_deg=150.0,
            region_dec_deg=40.0,
            max_cache_bytes=10_000_000,
            conn_factory=get_db,
            wait_timeout_s=5.0,
        )
    assert first.status == second.status == "error"
    assert insert_sources == ["dss2_color", "placeholder"]
    assert fake_hips["calls"] == 1


async def test_in_memory_backoff_expires_after_ten_minutes(fake_hips, monkeypatch):
    now = 100.0
    monkeypatch.setattr(sky_tile_cache, "_clock", lambda: now)

    async def fail_insert(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(sky_tile_cache, "_insert_cache_row", fail_insert)
    key = _default_key()
    async with get_db() as conn:
        first = await get_cell(
            conn,
            key=key,
            region_ra_deg=150.0,
            region_dec_deg=40.0,
            max_cache_bytes=10_000_000,
            conn_factory=get_db,
            wait_timeout_s=5.0,
        )
        now += sky_tile_cache._FETCH_ERROR_BACKOFF.total_seconds() + 1
        retried = await get_cell(
            conn,
            key=key,
            region_ra_deg=150.0,
            region_dec_deg=40.0,
            max_cache_bytes=10_000_000,
            conn_factory=get_db,
            wait_timeout_s=5.0,
        )
    assert first.status == retried.status == "error"
    assert fake_hips["calls"] == 2


async def test_fetch_error_backoff_expires_after_ten_minutes(fake_hips):
    # Pre-populate a fetch_error row with an old timestamp.
    key = _default_key()
    stale = (datetime.now(UTC) - timedelta(minutes=11)).strftime("%Y-%m-%d %H:%M:%S")
    async with get_db() as conn:
        await conn.execute(
            """
            INSERT INTO sky_tile_cache (
                hips_survey, healpix_nside, healpix_ipix, tier,
                cell_size_deg_x100, cell_width_px, cell_height_px,
                cell_i, cell_j, file_path, source, bytes, fetched_at,
                fetch_error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'placeholder', 0, ?, 'old error')
            """,
            (
                key.hips_survey,
                key.healpix_nside,
                key.healpix_ipix,
                key.tier,
                key.cell_size_deg_x100,
                key.cell_width_px,
                key.cell_height_px,
                key.cell_i,
                key.cell_j,
                str(sky_tile_cache._cell_path(key)),
                stale,
            ),
        )
        await conn.commit()

        # The next call should drop the expired sentinel and schedule a
        # fresh fetch.
        result = await get_cell(
            conn,
            key=key,
            region_ra_deg=150.0,
            region_dec_deg=40.0,
            max_cache_bytes=10_000_000,
            conn_factory=get_db,
            wait_timeout_s=5.0,
        )
    assert result.status == "hit"


# ── LRU eviction + orphan sweep ──────────────────────────────────────────────


async def test_lru_eviction_enforces_max_bytes(fake_hips, tmp_path):
    async with get_db() as conn:
        # First cell populates the cache.
        await get_cell(
            conn,
            key=_default_key(cell_i=0, cell_j=0),
            region_ra_deg=150.0,
            region_dec_deg=40.0,
            max_cache_bytes=10_000_000,
            conn_factory=get_db,
            wait_timeout_s=5.0,
        )
        # Second cell with a tiny max_bytes forces the first to evict.
        await get_cell(
            conn,
            key=_default_key(cell_i=1, cell_j=0),
            region_ra_deg=150.0,
            region_dec_deg=40.0,
            max_cache_bytes=len(_FAKE_JPEG) + 10,  # room for only one cell
            conn_factory=get_db,
            wait_timeout_s=5.0,
        )
        cursor = await conn.execute("SELECT COUNT(*) AS n FROM sky_tile_cache")
        row = await cursor.fetchone()
    assert row["n"] == 1


async def test_rehydrate_from_disk_rebuilds_cache_index(tmp_path):
    """Tiles on disk survive a database wipe — ``rehydrate_from_disk``
    re-parses filenames back into ``sky_tile_cache`` rows so the cache
    is usable even when the SQLite index was just dropped and
    recreated. Matches the real-world scenario where a user switches
    databases or bootstraps a fresh one.
    """
    cell_dir = tmp_path / "sky_tiles"
    cell_dir.mkdir()
    jpeg = cell_dir / "CDS_P_DSS2_color_n8_p300_narrow_50_800x800_1_-2.jpg"
    jpeg.write_bytes(b"\xff\xd8" + b"x" * 2048)  # plausible JPEG body
    # Unrecognised slug → skipped (not all surveys are rehydratable).
    unknown = cell_dir / "unknown_survey_n8_p300_narrow_50_800x800_0_0.jpg"
    unknown.write_bytes(b"\xff\xd8" + b"x" * 2048)
    # Too small → skipped (treated as truncated).
    tiny = cell_dir / "CDS_P_DSS2_color_n8_p300_narrow_50_800x800_2_0.jpg"
    tiny.write_bytes(b"\x00\x01\x02")

    async with get_db() as conn:
        inserted = await rehydrate_from_disk(conn)
        cursor = await conn.execute(
            "SELECT hips_survey, healpix_ipix, cell_i, cell_j, bytes FROM sky_tile_cache"
        )
        rows = [dict(r) for r in await cursor.fetchall()]

    assert inserted == 1
    assert len(rows) == 1
    assert rows[0]["hips_survey"] == "CDS/P/DSS2/color"
    assert rows[0]["healpix_ipix"] == 300
    assert rows[0]["cell_i"] == 1
    assert rows[0]["cell_j"] == -2
    assert rows[0]["bytes"] == len(jpeg.read_bytes())
    # Unknown / tiny files are untouched — rehydrate doesn't delete.
    assert unknown.exists()
    assert tiny.exists()


async def test_rehydrate_repairs_moved_path_and_preserves_timestamp(tmp_path):
    old_dir = tmp_path / "old-app-data" / "sky_tiles"
    old_dir.mkdir(parents=True)
    cell_dir = tmp_path / "sky_tiles"
    cell_dir.mkdir()
    filename = "CDS_P_DSS2_color_n8_p300_narrow_50_800x800_1_-2.jpg"
    original = old_dir / filename
    original.write_bytes(b"original")
    jpeg = cell_dir / filename
    jpeg.write_bytes(b"\xff\xd8" + b"x" * 2048)
    accessed = "2025-02-03 04:05:06"

    async with get_db() as conn:
        await conn.execute(
            """
            INSERT INTO sky_tile_cache
                (hips_survey, healpix_nside, healpix_ipix, tier,
                 cell_size_deg_x100, cell_width_px, cell_height_px,
                 cell_i, cell_j, file_path, source, bytes, last_access_at)
            VALUES ('CDS/P/DSS2/color', 8, 300, 'narrow', 50, 800, 800,
                    1, -2, ?, 'dss2_color', 1, ?)
            """,
            (str(original), accessed),
        )
        await conn.commit()
        assert await rehydrate_from_disk(conn) == 0
        assert await rehydrate_from_disk(conn) == 0
        row = (
            await conn.execute_fetchall(
                "SELECT file_path, bytes, last_access_at FROM sky_tile_cache"
            )
        )[0]

    assert row["file_path"] == filename
    assert row["bytes"] == jpeg.stat().st_size
    assert row["last_access_at"] == accessed
    assert original.read_bytes() == b"original"


async def test_sync_orphan_files_removes_unreferenced_jpegs(tmp_path):
    cell_dir = tmp_path / "sky_tiles"
    cell_dir.mkdir()
    # An orphan that matches the filename pattern must be swept.
    orphan = cell_dir / ("CDS_P_DSS2_color_n8_p200_narrow_50_800x800_0_0.jpg")
    orphan.write_bytes(b"orphan")
    # A file that doesn't match the pattern stays (defensive — don't
    # delete arbitrary user files that land in the directory).
    bystander = cell_dir / "notes.txt"
    bystander.write_bytes(b"leave me alone")
    # A jpg with a weird name also stays (pattern must match).
    unrecognised = cell_dir / "random.jpg"
    unrecognised.write_bytes(b"no pattern")
    temporary = cell_dir / ".CDS_P_DSS2_color_n8_p200_narrow_50_800x800_1_0.jpg.tmp"
    temporary.write_bytes(b"partial")

    async with get_db() as conn:
        removed = await sync_orphan_files(conn)
    assert removed == 2
    assert not orphan.exists()
    assert not temporary.exists()
    assert bystander.exists()
    assert unrecognised.exists()


async def test_clear_cache_wipes_everything(fake_hips, tmp_path):
    async with get_db() as conn:
        await get_cell(
            conn,
            key=_default_key(),
            region_ra_deg=150.0,
            region_dec_deg=40.0,
            max_cache_bytes=10_000_000,
            conn_factory=get_db,
            wait_timeout_s=5.0,
        )
        # Confirm a file was written.
        files_before = list((tmp_path / "sky_tiles").glob("*.jpg"))
        assert len(files_before) == 1

        deleted = await clear_cache(conn)

        cursor = await conn.execute("SELECT COUNT(*) AS n FROM sky_tile_cache")
        row = await cursor.fetchone()

    assert deleted == 1
    assert row["n"] == 0
    assert not any(Path(f).exists() for f in files_before)


# ── In-flight dedup ──────────────────────────────────────────────────────────


async def test_concurrent_misses_share_one_fetch_task(fake_hips):
    """Two simultaneous callers for the same cell must share one render."""
    fake_hips["delay"] = 0.05
    async with get_db() as conn_a, get_db() as conn_b:
        key = _default_key()
        a, b = await asyncio.gather(
            get_cell(
                conn_a,
                key=key,
                region_ra_deg=150.0,
                region_dec_deg=40.0,
                max_cache_bytes=10_000_000,
                conn_factory=get_db,
                wait_timeout_s=5.0,
            ),
            get_cell(
                conn_b,
                key=key,
                region_ra_deg=150.0,
                region_dec_deg=40.0,
                max_cache_bytes=10_000_000,
                conn_factory=get_db,
                wait_timeout_s=5.0,
            ),
        )

    # Both callers got the real image, yet only one CDS call happened.
    assert a.status == "hit"
    assert b.status == "hit"
    assert fake_hips["calls"] == 1
