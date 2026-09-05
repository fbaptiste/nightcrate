"""Shared setup helpers for the catalog/ingest test modules.

Direct SQL for rig seeding — going through the API would drag in the whole
equipment-form surface these tests don't exercise.
"""

from __future__ import annotations

import itertools
from pathlib import Path

import numpy as np
from astropy.io import fits
from httpx import AsyncClient

from nightcrate.db.session import get_db


async def _seed_rig(name: str = "Test Rig") -> int:
    """Insert one rig with the minimum its NOT NULL columns require.

    The ingest reads no equipment at all now — a rig matters only where the user
    declares one (a project's rigs, or a source folder's tag).
    """
    async with get_db() as conn:
        await conn.execute("PRAGMA foreign_keys = ON")

        async def insert(sql: str, params: tuple) -> int:
            cursor = await conn.execute(sql, params)
            return cursor.lastrowid

        await conn.execute("INSERT OR IGNORE INTO manufacturer (name) VALUES ('TestMfg')")
        cursor = await conn.execute("SELECT id FROM manufacturer WHERE name = 'TestMfg'")
        mfr = (await cursor.fetchone())["id"]
        sensor = await insert(
            "INSERT INTO sensor (manufacturer_id, model_name, sensor_type, pixel_size_um, "
            "resolution_x, resolution_y) VALUES (?, ?, 'mono', 3.76, 6248, 4176)",
            (mfr, f"Sensor for {name}"),
        )
        camera = await insert(
            "INSERT INTO camera (manufacturer_id, sensor_id, model_name) VALUES (?, ?, ?)",
            (mfr, sensor, f"Camera for {name}"),
        )
        scope = await insert(
            "INSERT INTO telescope (manufacturer_id, model_name, aperture_mm) VALUES (?, ?, 80)",
            (mfr, f"Scope for {name}"),
        )
        config = await insert(
            "INSERT INTO telescope_configuration (telescope_id, config_name, "
            "effective_focal_length_mm, effective_focal_ratio, is_native) "
            "VALUES (?, 'Native', 600, 7.5, 1)",
            (scope,),
        )
        rig_id = await insert(
            "INSERT INTO rig (name, telescope_configuration_id, camera_id) VALUES (?, ?, ?)",
            (name, config, camera),
        )
        await conn.commit()
    return rig_id


async def _assign_rigs(client: AsyncClient, project_id: int, rig_ids: list[int]) -> None:
    resp = await client.put(f"/api/projects/{project_id}/rigs", json={"rig_ids": rig_ids})
    assert resp.status_code == 200, resp.text


async def _make_project(client: AsyncClient, name: str) -> int:
    resp = await client.post("/api/projects", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


_PIXEL_SEED = itertools.count(1000)


def _write_fits(
    path: Path,
    *,
    imagetyp: str = "LIGHT",
    filt: str | None = "Ha",
    exptime: float = 300.0,
    gain: int = 100,
    date_obs: str = "2026-03-15T23:30:00",
) -> None:
    """A synthetic frame with unique pixel data — byte-identical files in one
    project correctly dedupe to a single row, which would break count assertions."""
    data = np.full((8, 8), next(_PIXEL_SEED) % 65535, dtype=np.uint16)
    hdu = fits.PrimaryHDU(data)
    hdu.header["IMAGETYP"] = imagetyp
    hdu.header["EXPTIME"] = exptime
    hdu.header["GAIN"] = gain
    # Recorded into fits_header_json, but nothing reads them for equipment any
    # more — a project's rigs and its folders' rig tags are the equipment context.
    hdu.header["INSTRUME"] = "ZWO ASI2600MM Pro"
    hdu.header["FOCALLEN"] = 2800.0
    hdu.header["DATE-OBS"] = date_obs
    if filt is not None:
        hdu.header["FILTER"] = filt
    hdu.writeto(path, overwrite=True)


async def _ingest_folder(
    client: AsyncClient, project_id: int, folder: Path, *, add_folder: bool = True
) -> dict:
    """Bind *folder* to the project and scan it.

    Pass ``add_folder=False`` to re-scan an already-bound folder — that's the
    path that exercises whether a manual correction survives.
    """
    if add_folder:
        resp = await client.post(f"/api/projects/{project_id}/folders", json={"path": str(folder)})
        assert resp.status_code == 201, resp.text
    resp = await client.post(f"/api/projects/{project_id}/ingest")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _frames(client: AsyncClient, project_id: int, **params) -> list[dict]:
    resp = await client.get(f"/api/projects/{project_id}/catalog/frames", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()["rows"]
