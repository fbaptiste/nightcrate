from __future__ import annotations

from pathlib import Path

import pytest

from nightcrate.db.session import get_db
from nightcrate.services import image_cache


async def _seed_thumbnail(conn, filename: str, size: int, accessed: str) -> None:
    await conn.execute(
        """
        INSERT OR IGNORE INTO dso_catalog_source
            (source_id, category, display_name, file_path, file_hash)
        VALUES ('image-cache-test', 'openngc', 'Test', '/dev/null', 'hash')
        """
    )
    cursor = await conn.execute(
        "SELECT id FROM dso_catalog_source WHERE source_id = 'image-cache-test'"
    )
    source = await cursor.fetchone()
    await conn.execute(
        """
        INSERT OR IGNORE INTO dso
            (id, primary_designation, obj_type, ra_deg, dec_deg,
             source_catalog_id, source_row_hash)
        VALUES (900001, 'CACHE-TEST', 'G', 1.0, 2.0, ?, 'hash')
        """,
        (source["id"],),
    )
    await conn.execute(
        """
        INSERT INTO thumbnail_cache
            (dso_id, variant, width, height, file_path, source, bytes, last_access_at)
        VALUES (900001, 'list', 180, 180, ?, 'dss2_color', ?, ?)
        """,
        (filename, size, accessed),
    )


async def _seed_sky_tile(conn, filename: str, size: int, accessed: str) -> None:
    await conn.execute(
        """
        INSERT INTO sky_tile_cache
            (hips_survey, healpix_nside, healpix_ipix, tier,
             cell_size_deg_x100, cell_width_px, cell_height_px,
             cell_i, cell_j, file_path, source, bytes, last_access_at)
        VALUES ('CDS/P/DSS2/color', 8, 1, 'narrow', 25, 512, 512,
                0, 0, ?, 'dss2_color', ?, ?)
        """,
        (filename, size, accessed),
    )


def test_resolve_path_uses_current_app_dir_for_portable_and_legacy_rows(tmp_path):
    directory = image_cache.cache_dir("thumbnail", create=True)
    expected = directory / "cached.jpg"

    assert image_cache.resolve_path("cached.jpg", "thumbnail") == expected
    assert image_cache.resolve_path("/old/account/thumbnails/cached.jpg", "thumbnail") == expected
    assert (
        image_cache.resolve_path(r"C:\Users\Old\AppData\thumbnails\cached.jpg", "thumbnail")
        == expected
    )
    assert image_cache.resolve_path("../cached.jpg", "thumbnail") is None
    assert image_cache.resolve_path("nested/cached.jpg", "thumbnail") is None


def test_resolve_path_rejects_escaping_symlink(tmp_path):
    directory = image_cache.cache_dir("sky_tile", create=True)
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"outside")
    link = directory / "linked.jpg"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are unavailable")

    assert image_cache.resolve_path(link.name, "sky_tile") is None
    assert outside.read_bytes() == b"outside"


async def test_combined_stats_and_lru_share_one_budget(tmp_path):
    thumbs = image_cache.cache_dir("thumbnail", create=True)
    tiles = image_cache.cache_dir("sky_tile", create=True)
    (thumbs / "thumb.jpg").write_bytes(b"t" * 120)
    (tiles / "tile.jpg").write_bytes(b"s" * 100)

    async with get_db() as conn:
        await _seed_thumbnail(conn, "thumb.jpg", 120, "2026-01-01 00:00:00")
        await _seed_sky_tile(conn, "tile.jpg", 100, "2026-01-01 00:00:00")
        await conn.commit()
        stats = await image_cache.combined_stats(conn, max_bytes=120)
        async with image_cache.lock:
            evicted = await image_cache.evict_lru_locked(conn, 120)

        assert stats == {"total_bytes": 220, "row_count": 2, "max_bytes": 120}
        assert evicted == 1
        # Ties are deterministic: sky_tile sorts before thumbnail.
        assert (thumbs / "thumb.jpg").is_file()
        assert not (tiles / "tile.jpg").exists()
        rows = await conn.execute_fetchall("SELECT file_path FROM thumbnail_cache")
        assert [row["file_path"] for row in rows] == ["thumb.jpg"]
        assert not await conn.execute_fetchall("SELECT id FROM sky_tile_cache")


async def test_clear_all_remaps_legacy_paths_and_never_touches_original(tmp_path):
    old_root = tmp_path / "old-copy"
    old_root.mkdir()
    old_thumb = old_root / "thumb.jpg"
    old_tile = old_root / "tile.jpg"
    old_thumb.write_bytes(b"original thumbnail")
    old_tile.write_bytes(b"original tile")

    thumbs = image_cache.cache_dir("thumbnail", create=True)
    tiles = image_cache.cache_dir("sky_tile", create=True)
    (thumbs / old_thumb.name).write_bytes(b"current thumbnail")
    (tiles / old_tile.name).write_bytes(b"current tile")

    before = image_cache.generation()
    async with get_db() as conn:
        await _seed_thumbnail(conn, str(old_thumb), 17, "2026-01-01 00:00:00")
        await _seed_sky_tile(conn, str(old_tile), 13, "2026-01-02 00:00:00")
        await conn.commit()
        deleted = await image_cache.clear_all(conn)
        assert not await conn.execute_fetchall("SELECT id FROM thumbnail_cache")
        assert not await conn.execute_fetchall("SELECT id FROM sky_tile_cache")

    assert deleted == 2
    assert image_cache.generation() == before + 1
    assert old_thumb.read_bytes() == b"original thumbnail"
    assert old_tile.read_bytes() == b"original tile"
    assert not (thumbs / old_thumb.name).exists()
    assert not (tiles / old_tile.name).exists()


async def test_clear_all_removes_unindexed_owned_files_and_preserves_bystanders(tmp_path):
    thumbs = image_cache.cache_dir("thumbnail", create=True)
    tiles = image_cache.cache_dir("sky_tile", create=True)
    thumb_name = "ra123_dec-456_list_180x180.jpg"
    tile_name = "CDS_P_DSS2_color_n8_p1_narrow_25_512x512_0_0.jpg"
    owned = [
        thumbs / thumb_name,
        thumbs / f".{thumb_name}.tmp",
        tiles / tile_name,
        tiles / f".{tile_name}.tmp",
    ]
    for path in owned:
        path.write_bytes(b"cache")

    bystanders = [
        thumbs / "notes.txt",
        thumbs / "unknown.jpg",
        tiles / ".unknown.jpg.tmp",
    ]
    for path in bystanders:
        path.write_bytes(b"keep")
    outside = tmp_path / tile_name
    outside.write_bytes(b"outside")

    async with get_db() as conn:
        assert await image_cache.clear_all(conn) == len(owned)

    assert all(not path.exists() for path in owned)
    assert all(path.read_bytes() == b"keep" for path in bystanders)
    assert outside.read_bytes() == b"outside"


async def test_lru_keeps_row_when_unlink_fails(tmp_path, monkeypatch):
    thumbs = image_cache.cache_dir("thumbnail", create=True)
    path = thumbs / "locked.jpg"
    path.write_bytes(b"x" * 200)
    original_unlink = Path.unlink

    def fail_locked(candidate: Path, *args, **kwargs):
        if candidate == path:
            raise PermissionError("locked")
        return original_unlink(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_locked)
    async with get_db() as conn:
        await _seed_thumbnail(conn, path.name, 200, "2026-01-01 00:00:00")
        await conn.commit()
        async with image_cache.lock:
            assert await image_cache.evict_lru_locked(conn, 0) == 0
        assert await conn.execute_fetchall("SELECT id FROM thumbnail_cache")
    assert path.is_file()
