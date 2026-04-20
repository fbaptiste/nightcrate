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


def test_compute_angular_extent_uses_minimum_when_size_missing():
    assert thumbnails.compute_angular_extent_deg("list", dso_maj_axis_arcmin=None) == pytest.approx(
        0.125, abs=1e-3
    )
    # 5' fallback × 1.5 / 60 = 0.125, clamped by the 0.1° floor → 0.125 wins
    assert thumbnails.compute_angular_extent_deg("detail", dso_maj_axis_arcmin=None) == 1.0


def test_compute_angular_extent_list_scales_with_major_axis():
    # 30' major axis → 0.5 deg. × 1.5 multiplier = 0.75 deg for list variant.
    assert thumbnails.compute_angular_extent_deg("list", dso_maj_axis_arcmin=30.0) == pytest.approx(
        0.75, abs=1e-3
    )


def test_compute_angular_extent_detail_wider_min():
    # Pass B widened the detail min to 1.0° and the multiplier to 3.5×.
    # A tiny 2' object → 2/60 × 3.5 = 0.117, clamped up to 1.0° minimum.
    assert thumbnails.compute_angular_extent_deg("detail", dso_maj_axis_arcmin=2.0) == 1.0
    # A large 60' object → 60/60 × 3.5 = 3.5° (above the minimum).
    assert thumbnails.compute_angular_extent_deg(
        "detail", dso_maj_axis_arcmin=60.0
    ) == pytest.approx(3.5, abs=1e-3)


def test_compute_angular_extent_rig_framed_matches_rig_major():
    assert thumbnails.compute_angular_extent_deg(
        "rig_framed",
        dso_maj_axis_arcmin=5.0,
        fov_major_deg=0.37,
        fov_minor_deg=0.28,
    ) == pytest.approx(0.37, abs=1e-6)


def test_compute_angular_extent_rig_framed_requires_fov():
    with pytest.raises(ValueError, match="rig_framed"):
        thumbnails.compute_angular_extent_deg("rig_framed", dso_maj_axis_arcmin=5.0)


def test_compute_angular_extent_fov_simulator_rig_major_over_050():
    # Tile extent = fov_major / 0.5 so the sensor rectangle fills 50%
    # of the tile's max dimension. C11-like 0.37×0.28 rig: 0.37/0.5 =
    # 0.74°. Object size is intentionally NOT a factor — the zoom
    # stays tied to the rig only.
    extent = thumbnails.compute_angular_extent_deg(
        "fov_simulator",
        dso_maj_axis_arcmin=5.0,
        fov_major_deg=0.37,
        fov_minor_deg=0.28,
    )
    assert extent == pytest.approx(0.74, abs=1e-3)


def test_compute_angular_extent_fov_simulator_ignores_object_size():
    # M42 at 65' with a tiny 0.1×0.08° rig. Object dominates
    # visually but tile extent is locked to the rig: 0.1/0.5 = 0.2°.
    extent = thumbnails.compute_angular_extent_deg(
        "fov_simulator",
        dso_maj_axis_arcmin=65.0,
        fov_major_deg=0.1,
        fov_minor_deg=0.08,
    )
    assert extent == pytest.approx(0.2, abs=1e-3)


def test_compute_angular_extent_fov_simulator_uses_larger_axis():
    # Portrait rigs (minor > major, rare but possible) should still
    # pick the larger dimension. 0.45 / 0.5 = 0.9.
    extent = thumbnails.compute_angular_extent_deg(
        "fov_simulator",
        dso_maj_axis_arcmin=5.0,
        fov_major_deg=0.3,
        fov_minor_deg=0.45,
    )
    assert extent == pytest.approx(0.9, abs=1e-3)


def test_compute_angular_extent_fov_simulator_requires_both_fov_dims():
    with pytest.raises(ValueError, match="fov_simulator"):
        thumbnails.compute_angular_extent_deg(
            "fov_simulator", dso_maj_axis_arcmin=5.0, fov_major_deg=0.37
        )


def test_make_key_rounds_fov_to_milli_degree():
    k1 = thumbnails.make_key(42, "rig_framed", fov_major_deg=0.3701, fov_minor_deg=0.2801)
    k2 = thumbnails.make_key(42, "rig_framed", fov_major_deg=0.3702, fov_minor_deg=0.2804)
    # 0.3701 × 1000 = 370.1 → rounds to 370; 0.3702 → 370. Match.
    assert k1.fov_major_deg_x1000 == k2.fov_major_deg_x1000 == 370
    assert k1.fov_minor_deg_x1000 == k2.fov_minor_deg_x1000 == 280


def test_make_key_distinguishes_rigs_at_0_01_degree_spacing():
    k1 = thumbnails.make_key(42, "rig_framed", fov_major_deg=0.370, fov_minor_deg=0.280)
    k2 = thumbnails.make_key(42, "rig_framed", fov_major_deg=0.380, fov_minor_deg=0.290)
    assert k1.fov_major_deg_x1000 != k2.fov_major_deg_x1000


def test_make_key_rig_independent_variants_ignore_fov_args():
    # Even if a caller accidentally passes FOV values, list / detail keys
    # must stay rig-independent so the cache doesn't fork.
    k = thumbnails.make_key(42, "list", fov_major_deg=0.37, fov_minor_deg=0.28)
    assert k.fov_major_deg_x1000 is None
    assert k.fov_minor_deg_x1000 is None


def test_make_key_rig_dependent_variants_require_fov():
    with pytest.raises(ValueError, match="rig_framed"):
        thumbnails.make_key(42, "rig_framed")
    with pytest.raises(ValueError, match="fov_simulator"):
        thumbnails.make_key(42, "fov_simulator", fov_major_deg=0.37)


def test_make_key_sky_center_only_recorded_for_fov_simulator():
    # Stray center coords on a non-simulator variant must be discarded
    # so the list/detail caches don't fork on a bug elsewhere.
    k = thumbnails.make_key(42, "list", center_ra_deg=100.0, center_dec_deg=20.0)
    assert k.center_ra_deg_x1000 is None
    assert k.center_dec_deg_x1000 is None


def test_make_key_sky_center_rounds_to_milli_degree():
    k = thumbnails.make_key(
        42,
        "fov_simulator",
        fov_major_deg=0.37,
        fov_minor_deg=0.28,
        center_ra_deg=202.4731,
        center_dec_deg=47.1954,
    )
    assert k.center_ra_deg_x1000 == 202473
    assert k.center_dec_deg_x1000 == 47195


def test_make_key_sky_center_distinguishes_panned_from_native():
    native = thumbnails.make_key(42, "fov_simulator", fov_major_deg=0.37, fov_minor_deg=0.28)
    panned = thumbnails.make_key(
        42,
        "fov_simulator",
        fov_major_deg=0.37,
        fov_minor_deg=0.28,
        center_ra_deg=10.0,
        center_dec_deg=-5.0,
    )
    assert native.center_ra_deg_x1000 is None
    assert panned.center_ra_deg_x1000 == 10000
    assert native != panned


async def test_rig_framed_cache_miss_enqueues_fetch(fake_hips):
    fake_hips["mapping"]["DSS2%2Fcolor"] = FakeResponse(body=_FAKE_JPEG)

    async with get_db() as conn:
        result = await thumbnails.get_thumbnail(
            conn,
            dso_id=42,
            variant="rig_framed",
            ra_deg=10.0,
            dec_deg=20.0,
            maj_axis_arcmin=5.0,
            max_cache_bytes=10 * 1024 * 1024,
            conn_factory=get_db,
            fov_major_deg=0.37,
            fov_minor_deg=0.28,
        )
    assert result.status == "placeholder"

    for t in list(thumbnails._in_flight.values()):
        await t

    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT source, fov_major_deg_x1000, fov_minor_deg_x1000 "
            "FROM thumbnail_cache WHERE dso_id = 42 AND variant = 'rig_framed'"
        )
        row = await cursor.fetchone()
    assert row["source"] == "dss2_color"
    assert row["fov_major_deg_x1000"] == 370
    assert row["fov_minor_deg_x1000"] == 280


async def test_rig_framed_two_distinct_rigs_get_separate_rows(fake_hips):
    fake_hips["mapping"]["DSS2%2Fcolor"] = FakeResponse(body=_FAKE_JPEG)

    for fov_major, fov_minor in ((0.37, 0.28), (0.80, 0.60)):
        async with get_db() as conn:
            await thumbnails.get_thumbnail(
                conn,
                dso_id=55,
                variant="rig_framed",
                ra_deg=10.0,
                dec_deg=20.0,
                maj_axis_arcmin=5.0,
                max_cache_bytes=10 * 1024 * 1024,
                conn_factory=get_db,
                fov_major_deg=fov_major,
                fov_minor_deg=fov_minor,
            )
        for t in list(thumbnails._in_flight.values()):
            await t

    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT COUNT(*) AS n FROM thumbnail_cache WHERE dso_id = 55 AND variant='rig_framed'"
        )
        assert (await cursor.fetchone())["n"] == 2


async def test_sync_orphan_files_deletes_untracked(tmp_path):
    thumb_dir = tmp_path / "thumbnails"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    # One tracked, one orphan, one non-matching filename (should be left alone).
    tracked = thumb_dir / "1_list_180x180.jpg"
    orphan = thumb_dir / "2_detail_800x800.jpg"
    other = thumb_dir / "README.txt"
    tracked.write_bytes(b"x")
    orphan.write_bytes(b"x")
    other.write_bytes(b"x")

    async with get_db() as conn:
        await conn.execute(
            "INSERT INTO thumbnail_cache (dso_id, variant, width, height, "
            "file_path, source, bytes) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (1, "list", 180, 180, str(tracked), "dss2_color", 1),
        )
        await conn.commit()

        removed = await thumbnails.sync_orphan_files(conn)

    assert removed == 1
    assert tracked.exists()
    assert not orphan.exists()
    assert other.exists()  # non-thumbnail files untouched


def test_filename_regex_matches_panned_fov_simulator():
    # The panned fov_simulator filename has both the FOV pair and the
    # sky-centre pair; the regex must accept either/both suffixes.
    match = thumbnails._THUMB_FILENAME_RE.match(
        "42_fov_simulator_800x800_370_280_c202473_47195.jpg"
    )
    assert match is not None
    assert match.group("variant") == "fov_simulator"
    assert match.group("fmaj") == "370"
    assert match.group("cra") == "202473"
    assert match.group("cdec") == "47195"


def test_filename_regex_accepts_negative_dec():
    # Southern declinations carry a leading minus sign.
    match = thumbnails._THUMB_FILENAME_RE.match("7_fov_simulator_800x800_100_80_c50000_-15500.jpg")
    assert match is not None
    assert match.group("cdec") == "-15500"
