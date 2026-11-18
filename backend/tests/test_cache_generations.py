"""Backward-compatible lookup and refresh for versioned image caches."""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import date
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from nightcrate.api import ingest as ingest_api
from nightcrate.api import project_solve as project_solve_api
from nightcrate.core.app_config import get_projects_root
from nightcrate.db.session import get_db
from nightcrate.main import app
from nightcrate.services.catalog_thumbnail import DEFAULT_MAX_PX
from nightcrate.services.project_images import (
    crop_candidates,
    crop_path,
    drain_background_refreshes,
    refresh_in_background,
    rendition_candidates,
    rendition_path,
)

OLD_RENDITION = b"old rendition bytes"
OLD_CROP = b"old crop bytes"
OLD_CATALOG = b"old catalog bytes"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


def _png(path: Path, color: tuple[int, int, int] = (20, 100, 180)) -> Path:
    Image.new("RGB", (40, 30), color).save(path)
    return path


async def _project_image(source: Path, *, name: str) -> tuple[int, int, Path]:
    async with get_db() as conn:
        project = await conn.execute("INSERT INTO project (name) VALUES (?)", (name,))
        project_id = int(project.lastrowid)
        image = await conn.execute(
            "INSERT INTO project_image (project_id, file_path, is_main) VALUES (?, ?, 1)",
            (project_id, str(source)),
        )
        image_id = int(image.lastrowid)
        await conn.commit()
    root = get_projects_root()
    assert root is not None
    image_dir = root / str(project_id) / f"img_{image_id}"
    image_dir.mkdir(parents=True, exist_ok=True)
    return project_id, image_id, image_dir


async def _crop_row(project_id: int, image_id: int, size: str = "medium") -> int:
    async with get_db() as conn:
        cursor = await conn.execute(
            "INSERT INTO project_thumbnail (project_id, size, source_image_id) VALUES (?, ?, ?)",
            (project_id, size, image_id),
        )
        await conn.commit()
        return int(cursor.lastrowid)


async def _catalog_frame(source: Path, digest: str) -> tuple[int, int]:
    async with get_db() as conn:
        project = await conn.execute("INSERT INTO project (name) VALUES ('Cache catalog')")
        project_id = int(project.lastrowid)
        frame = await conn.execute(
            "INSERT INTO sub_frame (project_id, content_hash, date_obs_utc) VALUES (?, ?, ?)",
            (project_id, digest, "2026-11-17T00:00:00+00:00"),
        )
        frame_id = int(frame.lastrowid)
        await conn.execute(
            "INSERT INTO file_location (project_id, path, category, sub_frame_id) "
            "VALUES (?, ?, 'sub_frame', ?)",
            (project_id, str(source), frame_id),
        )
        await conn.commit()
    return project_id, frame_id


def _catalog_candidates(digest: str) -> list[Path]:
    return ingest_api._thumbnail_candidates(ingest_api._thumb_cache_dir(), digest, DEFAULT_MAX_PX)


async def test_old_rendition_survives_failed_background_refresh(
    client: AsyncClient, tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    project_id, image_id, image_dir = await _project_image(
        tmp_path / "offline.png", name="Offline rendition"
    )
    old = image_dir / "thumb_md.jpg"
    old.write_bytes(OLD_RENDITION)
    caplog.set_level(logging.INFO, logger="nightcrate.services.project_images")

    response = await client.get(f"/api/projects/{project_id}/images/{image_id}/rendered/thumb_md")
    assert response.status_code == 200
    assert response.content == OLD_RENDITION
    await drain_background_refreshes()

    assert not rendition_path(image_dir, "thumb_md").exists()
    assert old.read_bytes() == OLD_RENDITION
    messages = [
        record.message for record in caplog.records if "background refresh failed" in record.message
    ]
    assert len(messages) == 1


async def test_old_rendition_is_served_then_replaced(client: AsyncClient, tmp_path: Path):
    source = _png(tmp_path / "source.png")
    project_id, image_id, image_dir = await _project_image(source, name="Rendition refresh")
    old = image_dir / "thumb_md.jpg"
    old.write_bytes(OLD_RENDITION)

    first = await client.get(f"/api/projects/{project_id}/images/{image_id}/rendered/thumb_md")
    assert first.content == OLD_RENDITION
    await drain_background_refreshes()

    candidates = rendition_candidates(image_dir, "thumb_md")
    assert candidates[0].is_file()
    assert all(not path.exists() for path in candidates[1:])
    second = await client.get(f"/api/projects/{project_id}/images/{image_id}/rendered/thumb_md")
    assert second.content == candidates[0].read_bytes()
    assert second.content != OLD_RENDITION


async def test_two_old_rendition_requests_start_one_refresh(
    client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source = _png(tmp_path / "source.png")
    project_id, image_id, image_dir = await _project_image(source, name="Single refresh")
    (image_dir / "thumb_md.jpg").write_bytes(OLD_RENDITION)
    started = threading.Event()
    release = threading.Event()
    calls = 0

    def blocked_render(_source: str, output_dir: Path) -> None:
        nonlocal calls
        calls += 1
        started.set()
        release.wait(timeout=5)
        rendition_path(output_dir, "thumb_md").write_bytes(b"new")

    monkeypatch.setattr("nightcrate.api.projects.generate_rendered_images", blocked_render)
    try:
        first = await client.get(f"/api/projects/{project_id}/images/{image_id}/rendered/thumb_md")
        assert first.content == OLD_RENDITION
        assert await asyncio.to_thread(started.wait, 1)
        second = await client.get(f"/api/projects/{project_id}/images/{image_id}/rendered/thumb_md")
        assert second.content == OLD_RENDITION
        assert calls == 1
    finally:
        release.set()
        await drain_background_refreshes()


async def test_project_refreshes_take_one_thread_at_a_time(tmp_path: Path):
    lock = threading.Lock()
    started = threading.Event()
    release = threading.Event()
    calls = 0
    concurrent = 0
    peak = 0

    def blocked_operation() -> None:
        nonlocal calls, concurrent, peak
        with lock:
            calls += 1
            concurrent += 1
            peak = max(peak, concurrent)
        started.set()
        release.wait(timeout=5)
        with lock:
            concurrent -= 1

    for index in range(6):
        refresh_in_background(tmp_path / f"target-{index}", blocked_operation)
    try:
        assert await asyncio.to_thread(started.wait, 1)
        assert calls == 1
        assert peak == 1
    finally:
        release.set()
        await drain_background_refreshes()

    assert calls == 6
    assert peak == 1


async def test_project_shutdown_cancels_queued_refreshes(tmp_path: Path):
    started = threading.Event()
    release = threading.Event()
    calls: list[Path] = []
    old_files = [tmp_path / f"old-{index}.jpg" for index in range(3)]
    current_files = [tmp_path / f"current-{index}.jpg" for index in range(3)]
    for old in old_files:
        old.write_bytes(b"old")

    def blocked_operation(current: Path, old: Path) -> None:
        calls.append(current)
        started.set()
        release.wait(timeout=5)
        current.write_bytes(b"new")
        old.unlink()

    refresh_in_background(current_files[0], blocked_operation, current_files[0], old_files[0])
    assert await asyncio.to_thread(started.wait, 1)
    for current, old in zip(current_files[1:], old_files[1:], strict=True):
        refresh_in_background(current, blocked_operation, current, old)

    shutdown = asyncio.create_task(drain_background_refreshes(cancel_pending=True))
    await asyncio.sleep(0)
    assert not shutdown.done()
    release.set()
    await shutdown

    assert calls == [current_files[0]]
    assert current_files[0].read_bytes() == b"new"
    assert not old_files[0].exists()
    assert all(not path.exists() for path in current_files[1:])
    assert [path.read_bytes() for path in old_files[1:]] == [b"old", b"old"]


async def test_rendition_replaced_between_lookup_and_read(
    client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    project_id, image_id, image_dir = await _project_image(
        tmp_path / "offline.png", name="Racing rendition"
    )
    candidates = rendition_candidates(image_dir, "thumb_md")
    current, old = candidates[0], candidates[-1]
    old.write_bytes(OLD_RENDITION)
    original_read_bytes = Path.read_bytes
    raced = False

    def racing_read_bytes(path: Path) -> bytes:
        nonlocal raced
        if path == old and not raced:
            raced = True
            old.unlink()
            current.write_bytes(b"new rendition")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", racing_read_bytes)
    response = await client.get(f"/api/projects/{project_id}/images/{image_id}/rendered/thumb_md")

    assert response.status_code == 200
    assert response.content == b"new rendition"
    assert raced


@pytest.mark.parametrize("source_exists", [False, True])
async def test_old_crop_is_served_while_current_refreshes(
    client: AsyncClient, tmp_path: Path, source_exists: bool
):
    source = tmp_path / "crop-source.png"
    if source_exists:
        _png(source, (80, 30, 140))
    project_id, image_id, _ = await _project_image(source, name=f"Crop {source_exists}")
    crop_id = await _crop_row(project_id, image_id)
    root = get_projects_root()
    assert root is not None
    project_dir = root / str(project_id)
    old = project_dir / f"thumb_crop_medium_{crop_id}.jpg"
    old.write_bytes(OLD_CROP)

    first = await client.get(f"/api/projects/{project_id}/thumbnail?size=medium")
    assert first.status_code == 200
    assert first.content == OLD_CROP
    await drain_background_refreshes()

    current = crop_path(project_dir, "medium", crop_id)
    if not source_exists:
        assert not current.exists()
        assert old.read_bytes() == OLD_CROP
        return
    assert current.is_file()
    assert all(not path.exists() for path in crop_candidates(project_dir, "medium", crop_id)[1:])
    second = await client.get(f"/api/projects/{project_id}/thumbnail?size=medium")
    assert second.content == current.read_bytes()
    assert second.content != OLD_CROP


async def test_gallery_and_home_include_old_crop_generation(client: AsyncClient, tmp_path: Path):
    source = _png(tmp_path / "gallery.png")
    project_id, image_id, _ = await _project_image(source, name="Old framing")
    crop_id = await _crop_row(project_id, image_id)
    async with get_db() as conn:
        await conn.execute(
            "INSERT INTO project_session "
            "(project_id, line_name, exposure_seconds, num_subs, session_date) "
            "VALUES (?, 'Lum', 60, 1, ?)",
            (project_id, date.today().isoformat()),
        )
        await conn.commit()
    root = get_projects_root()
    assert root is not None
    project_dir = root / str(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / f"thumb_crop_medium_{crop_id}.jpg").write_bytes(OLD_CROP)
    expected = {"id": crop_id, "image_id": image_id}

    gallery = (await client.get("/api/gallery")).json()["items"]
    gallery_item = next(item for item in gallery if item["project_id"] == project_id)
    assert gallery_item["crops"]["medium"] == expected

    home = (await client.get("/api/home")).json()
    recent = next(item for item in home["recent"] if item["project_id"] == project_id)
    assert recent["crops"]["medium"] == expected


async def test_old_catalog_thumbnail_survives_failed_refresh(
    client: AsyncClient, tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    digest = "a" * 64
    project_id, frame_id = await _catalog_frame(tmp_path / "offline.png", digest)
    candidates = _catalog_candidates(digest)
    candidates[-1].parent.mkdir(parents=True, exist_ok=True)
    candidates[-1].write_bytes(OLD_CATALOG)
    caplog.set_level(logging.INFO, logger="nightcrate")

    response = await client.get(f"/api/projects/{project_id}/catalog/frames/{frame_id}/thumbnail")
    assert response.status_code == 200
    assert response.content == OLD_CATALOG
    await ingest_api.drain_background_thumbnail_refreshes()

    assert not candidates[0].exists()
    assert candidates[-1].read_bytes() == OLD_CATALOG
    messages = [
        record.message
        for record in caplog.records
        if "background thumbnail refresh failed" in record.message
    ]
    assert len(messages) == 1


async def test_old_catalog_thumbnail_is_served_then_replaced(client: AsyncClient, tmp_path: Path):
    source = _png(tmp_path / "catalog.png", (150, 60, 20))
    digest = "b" * 64
    project_id, frame_id = await _catalog_frame(source, digest)
    candidates = _catalog_candidates(digest)
    candidates[-1].parent.mkdir(parents=True, exist_ok=True)
    candidates[-1].write_bytes(OLD_CATALOG)

    first = await client.get(f"/api/projects/{project_id}/catalog/frames/{frame_id}/thumbnail")
    assert first.content == OLD_CATALOG
    await ingest_api.drain_background_thumbnail_refreshes()

    assert candidates[0].is_file()
    assert all(not path.exists() for path in candidates[1:])
    second = await client.get(f"/api/projects/{project_id}/catalog/frames/{frame_id}/thumbnail")
    assert second.content == candidates[0].read_bytes()
    assert second.content != OLD_CATALOG


async def test_catalog_thumbnail_replaced_between_lookup_and_read(
    client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    digest = "d" * 64
    project_id, frame_id = await _catalog_frame(tmp_path / "offline.png", digest)
    candidates = _catalog_candidates(digest)
    current, old = candidates[0], candidates[-1]
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_bytes(OLD_CATALOG)
    original_read_bytes = Path.read_bytes
    raced = False

    def racing_read_bytes(path: Path) -> bytes:
        nonlocal raced
        if path == old and not raced:
            raced = True
            old.unlink()
            current.write_bytes(b"new catalog")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", racing_read_bytes)
    response = await client.get(f"/api/projects/{project_id}/catalog/frames/{frame_id}/thumbnail")

    assert response.status_code == 200
    assert response.content == b"new catalog"
    assert raced


async def test_catalog_shutdown_cancels_queued_refreshes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(ingest_api, "_THUMB_SEM", asyncio.Semaphore(1))
    started = threading.Event()
    release = threading.Event()
    calls: list[str] = []
    digests = [character * 64 for character in "efg"]
    candidates = [
        ingest_api._thumbnail_candidates(tmp_path, digest, DEFAULT_MAX_PX) for digest in digests
    ]
    for paths in candidates:
        paths[-1].write_bytes(b"old")

    def blocked_render(source_path: str, _max_px: int) -> bytes:
        calls.append(source_path)
        started.set()
        release.wait(timeout=5)
        return b"new"

    monkeypatch.setattr(ingest_api, "render_thumbnail_bytes", blocked_render)
    ingest_api._refresh_thumbnail_in_background(
        candidates[0][0], digests[0], "source-0", DEFAULT_MAX_PX
    )
    assert await asyncio.to_thread(started.wait, 1)
    for index in (1, 2):
        ingest_api._refresh_thumbnail_in_background(
            candidates[index][0], digests[index], f"source-{index}", DEFAULT_MAX_PX
        )

    shutdown = asyncio.create_task(
        ingest_api.drain_background_thumbnail_refreshes(cancel_pending=True)
    )
    await asyncio.sleep(0)
    assert not shutdown.done()
    release.set()
    await shutdown

    assert calls == ["source-0"]
    assert candidates[0][0].read_bytes() == b"new"
    assert not candidates[0][-1].exists()
    assert all(not paths[0].exists() for paths in candidates[1:])
    assert [paths[-1].read_bytes() for paths in candidates[1:]] == [b"old", b"old"]


async def test_missing_all_generations_keeps_existing_statuses(client: AsyncClient, tmp_path: Path):
    project_id, image_id, _ = await _project_image(
        tmp_path / "missing-project.png", name="No rendition"
    )
    rendition = await client.get(f"/api/projects/{project_id}/images/{image_id}/rendered/thumb_md")
    assert rendition.status_code == 204

    catalog_project, frame_id = await _catalog_frame(tmp_path / "missing-catalog.png", "c" * 64)
    catalog = await client.get(
        f"/api/projects/{catalog_project}/catalog/frames/{frame_id}/thumbnail"
    )
    assert catalog.status_code == 404


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        ({"full_v2.jpg": b"current"}, b"current"),
        ({"full.jpg": b"old"}, b"old"),
        ({"full_v2.jpg": b"current", "full.jpg": b"old"}, b"current"),
    ],
)
async def test_solve_image_generation_lookup(
    client: AsyncClient, files: dict[str, bytes], expected: bytes
):
    async with get_db() as conn:
        project = await conn.execute("INSERT INTO project (name) VALUES ('Solve cache')")
        project_id = int(project.lastrowid)
        solve = await conn.execute(
            "INSERT INTO project_solve ("
            "project_id, image_path, image_width, image_height, center_ra_deg, center_dec_deg, "
            "cd1_1, cd1_2, cd2_1, cd2_2, crpix1, crpix2"
            ") VALUES (?, '/offline.fits', 100, 100, 0, 0, 1, 0, 0, 1, 50, 50)",
            (project_id,),
        )
        solve_id = int(solve.lastrowid)
        await conn.commit()
    folder = project_solve_api._solve_dir(project_id) / str(solve_id)
    folder.mkdir(parents=True)
    for name, body in files.items():
        (folder / name).write_bytes(body)

    response = await client.get(f"/api/projects/{project_id}/solve/image/full")
    assert response.status_code == 200
    assert response.content == expected
