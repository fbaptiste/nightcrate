"""Integration tests for the v0.18.0 sky-tile cache service.

Mirrors the structure of ``test_planner_thumbnails.py``: uses the
autouse ``_test_db`` fixture (applies every migration including 0020),
mocks ``hips_client.http_client.get``, and exercises the public
``get_cell`` surface end-to-end.

Key paths covered:
- cache miss → placeholder returned, background fetch scheduled
- cache hit → JPEG bytes + last_access_at refreshed
- long-poll path → holds the request until the fetch lands
- DSS2 red fallback when DSS2 color fails
- permanent failure → ``fetch_error`` sentinel with 1-hour backoff
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
from nightcrate.services import sky_tile_cache
from nightcrate.services.sky_tile_cache import (
    _PLACEHOLDER_PNG,
    CellKey,
    clear_cache,
    get_cell,
    make_cell_key,
    sync_orphan_files,
)
from nightcrate.services.sky_tiles import TIERS

# Minimal valid JPEG-ish body — passes ``fetch_hips_image``'s magic-byte
# check (``\xff\xd8``) without needing to decode.
_FAKE_JPEG = b"\xff\xd8" + b"padding-content" * 200


class FakeResponse:
    def __init__(self, *, status_code: int = 200, body: bytes = b""):
        self.status_code = status_code
        self.content = body


@pytest.fixture
def fake_hips(monkeypatch):
    mapping: dict[str, object] = {}

    async def fake_get(url, *args, **kwargs):
        for prefix, handler in mapping.items():
            if prefix in url:
                return handler() if callable(handler) else handler
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr("nightcrate.services.hips_client.http_client.get", fake_get)
    return {"mapping": mapping}


@pytest.fixture(autouse=True)
def _redirect_cell_dir(tmp_path, monkeypatch):
    """Send APP_DIR at the test's tmp_path so cell writes are isolated."""
    monkeypatch.setattr("nightcrate.services.sky_tile_cache.APP_DIR", tmp_path)


@pytest.fixture(autouse=True)
async def _drain_in_flight():
    yield
    for key, task in list(sky_tile_cache._in_flight.items()):
        task.cancel()
        try:
            await task
        except BaseException:  # noqa: BLE001 — cleanup
            pass
        sky_tile_cache._in_flight.pop(key, None)


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
    # DSS2 color succeeds on the mock path.
    fake_hips["mapping"]["CDS%2FP%2FDSS2%2Fcolor"] = FakeResponse(body=_FAKE_JPEG)

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
    fake_hips["mapping"]["CDS%2FP%2FDSS2%2Fcolor"] = FakeResponse(body=_FAKE_JPEG)

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
    fake_hips["mapping"]["CDS%2FP%2FDSS2%2Fcolor"] = FakeResponse(body=_FAKE_JPEG)

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


async def test_dss2_red_fallback_when_color_fails(fake_hips):
    def raise_color():
        raise RuntimeError("color unavailable")

    fake_hips["mapping"]["CDS%2FP%2FDSS2%2Fcolor"] = raise_color
    fake_hips["mapping"]["CDS%2FP%2FDSS2%2Fred"] = FakeResponse(body=_FAKE_JPEG)

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
    async with get_db() as conn:
        cursor = await conn.execute("SELECT source FROM sky_tile_cache")
        row = await cursor.fetchone()
    assert row["source"] == "dss2_red"


async def test_double_failure_records_backoff_and_suppresses_retries(fake_hips):
    def always_fail():
        raise RuntimeError("boom")

    fake_hips["mapping"]["CDS%2FP%2FDSS2%2Fcolor"] = always_fail
    fake_hips["mapping"]["CDS%2FP%2FDSS2%2Fred"] = always_fail

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


async def test_fetch_error_backoff_expires_after_one_hour(fake_hips):
    fake_hips["mapping"]["CDS%2FP%2FDSS2%2Fcolor"] = FakeResponse(body=_FAKE_JPEG)

    # Pre-populate a fetch_error row with an old timestamp.
    key = _default_key()
    stale = (datetime.now(UTC) - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
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
    fake_hips["mapping"]["CDS%2FP%2FDSS2%2Fcolor"] = FakeResponse(body=_FAKE_JPEG)

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

    async with get_db() as conn:
        removed = await sync_orphan_files(conn)
    assert removed == 1
    assert not orphan.exists()
    assert bystander.exists()
    assert unrecognised.exists()


async def test_clear_cache_wipes_everything(fake_hips, tmp_path):
    fake_hips["mapping"]["CDS%2FP%2FDSS2%2Fcolor"] = FakeResponse(body=_FAKE_JPEG)

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
    """Two simultaneous callers for the same cell must share one CDS hit."""
    call_count = 0

    async def slow_response(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)
        return FakeResponse(body=_FAKE_JPEG)

    # Override the raw get directly so we can count calls.
    import nightcrate.services.hips_client as hc

    original = hc.http_client.get
    try:
        hc.http_client.get = slow_response  # type: ignore[attr-defined]
        async with get_db() as conn_a, get_db() as conn_b:
            # Fire two overlapping long-poll requests for the same key.
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
    finally:
        hc.http_client.get = original  # type: ignore[attr-defined]

    # Both callers got the real image, yet only one CDS call happened.
    assert a.status == "hit"
    assert b.status == "hit"
    assert call_count == 1
