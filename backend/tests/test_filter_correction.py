"""User filter corrections and fixed-filter defaults for camera raw files."""

from pathlib import Path

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.api import ingest
from nightcrate.db.session import get_db
from nightcrate.main import app
from tests.catalog_helpers import (
    _assign_rigs,
    _frames,
    _ingest_folder,
    _make_project,
    _seed_rig,
    _write_fits,
)
from tests.fixtures.raw_fixtures import write_cfa_dng


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


async def _fits_project(client: AsyncClient, tmp_path: Path, name: str = "Filters"):
    project_id = await _make_project(client, name)
    folder = tmp_path / name
    folder.mkdir()
    for index in range(2):
        _write_fits(folder / f"Light_{index}.fits", filt="Ha")
    await _ingest_folder(client, project_id, folder)
    return project_id, folder


async def test_bulk_filter_correction_survives_rescan(client: AsyncClient, tmp_path: Path):
    project_id, folder = await _fits_project(client, tmp_path, "Bulk filter")
    frames = await _frames(client, project_id)
    response = await client.post(
        f"/api/projects/{project_id}/catalog/frames/bulk-classification",
        json={"frame_ids": [row["id"] for row in frames], "filter": "  Custom Duo  "},
    )
    assert response.status_code == 200, response.text

    await _ingest_folder(client, project_id, folder, add_folder=False)
    rows = await _frames(client, project_id)
    assert {row["filter_name"] for row in rows} == {"Custom Duo"}
    assert {row["filter_name_source"] for row in rows} == {"user"}


async def test_reset_filter_rederives(client: AsyncClient, tmp_path: Path):
    project_id, _folder = await _fits_project(client, tmp_path, "Reset filter")
    frame = (await _frames(client, project_id))[0]
    await client.patch(
        f"/api/projects/{project_id}/catalog/frames/{frame['id']}/classification",
        json={"filter": "Custom"},
    )
    response = await client.patch(
        f"/api/projects/{project_id}/catalog/frames/{frame['id']}/classification",
        json={"reset_to_auto": ["filter"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["filter_name"] == "Ha"
    assert response.json()["filter_name_source"] == "auto"


async def test_user_filter_beats_header(client: AsyncClient, tmp_path: Path):
    project_id, folder = await _fits_project(client, tmp_path, "User filter")
    frame = (await _frames(client, project_id))[0]
    response = await client.patch(
        f"/api/projects/{project_id}/catalog/frames/{frame['id']}/classification",
        json={"filter": "Oiii"},
    )
    assert response.json()["filter_name"] == "Oiii"
    await _ingest_folder(client, project_id, folder, add_folder=False)
    updated = {row["id"]: row for row in await _frames(client, project_id)}[frame["id"]]
    assert updated["filter_name"] == "Oiii"


async def _rig_with_single_filter(name: str) -> tuple[int, str]:
    rig_id = await _seed_rig(name)
    filter_name = "Fixed Duo"
    async with get_db() as conn:
        manufacturer = await (
            await conn.execute("SELECT id FROM manufacturer WHERE name = 'TestMfg'")
        ).fetchone()
        filter_type = await (
            await conn.execute("SELECT id FROM filter_type ORDER BY id LIMIT 1")
        ).fetchone()
        cursor = await conn.execute(
            "INSERT INTO filter (manufacturer_id, filter_type_id, model_name) VALUES (?, ?, ?)",
            (manufacturer["id"], filter_type["id"], filter_name),
        )
        await conn.execute(
            "UPDATE rig SET single_filter_id = ? WHERE id = ?", (cursor.lastrowid, rig_id)
        )
        await conn.commit()
    return rig_id, filter_name


async def test_rig_single_filter_default_for_raw(client: AsyncClient, tmp_path: Path):
    project_id = await _make_project(client, "Raw fixed filter")
    rig_id, filter_name = await _rig_with_single_filter("Fixed raw rig")
    await _assign_rigs(client, project_id, [rig_id])
    folder = tmp_path / "raw-fixed"
    folder.mkdir()
    for index, kind in enumerate(("Light", "Flat", "Dark", "Bias")):
        samples = np.full((32, 34), 512 + index, dtype=np.uint16)
        write_cfa_dng(folder / f"{kind}_{index}.dng", samples)
    response = await client.post(
        f"/api/projects/{project_id}/folders",
        json={"path": str(folder), "rig_id": rig_id},
    )
    assert response.status_code == 201, response.text
    response = await client.post(f"/api/projects/{project_id}/ingest")
    assert response.status_code == 200, response.text

    rows = await _frames(client, project_id)
    by_type = {row["frame_type"]: row for row in rows}
    assert by_type["light"]["filter_name"] == filter_name
    assert by_type["flat"]["filter_name"] == filter_name
    assert by_type["dark"]["filter_name"] is None
    assert by_type["bias"]["filter_name"] is None


async def test_filter_correction_refreshes_sessions_once(
    client: AsyncClient, tmp_path: Path, monkeypatch
):
    project_id, _folder = await _fits_project(client, tmp_path, "Filter refresh")
    frames = await _frames(client, project_id)
    original = ingest.refresh_auto_sessions
    calls = 0

    async def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return await original(*args, **kwargs)

    monkeypatch.setattr(ingest, "refresh_auto_sessions", counted)
    response = await client.post(
        f"/api/projects/{project_id}/catalog/frames/bulk-classification",
        json={"frame_ids": [row["id"] for row in frames], "filter": "Oiii"},
    )
    assert response.status_code == 200
    assert calls == 1


@pytest.mark.parametrize("value", ["", "   ", "x" * 81])
async def test_filter_validation(client: AsyncClient, tmp_path: Path, value: str):
    project_id, _folder = await _fits_project(client, tmp_path, f"Validate {len(value)}")
    frame = (await _frames(client, project_id))[0]
    response = await client.patch(
        f"/api/projects/{project_id}/catalog/frames/{frame['id']}/classification",
        json={"filter": value},
    )
    assert response.status_code == 422
