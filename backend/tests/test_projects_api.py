"""Tests for project CRUD + save-as-you-go image management endpoints."""

from __future__ import annotations

import io
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from nightcrate.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _png(path: Path) -> str:
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
    return str(path)


def _valid_png(path: Path, color: tuple[int, int, int]) -> str:
    Image.new("RGB", (32, 24), color).save(path)
    return str(path)


def _crop_frame(**updates) -> dict:
    frame = {"crop_x": 0.0, "crop_y": 0.0, "crop_w": 1.0, "crop_h": 1.0}
    frame.update(updates)
    return frame


async def _project_list_item(client: AsyncClient, project_id: int) -> dict:
    response = await client.get("/api/projects", params={"include_retired": True})
    return next(item for item in response.json() if item["id"] == project_id)


async def _crop_rows(project_id: int) -> list[dict]:
    from nightcrate.db.session import get_db

    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT id, size, source_image_id, crop_x, crop_y, crop_w, crop_h"
            " FROM project_thumbnail WHERE project_id = ? ORDER BY size",
            (project_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]


def _crop_artifacts(project_dir: Path) -> dict[str, bytes]:
    paths = [*project_dir.glob("thumb_crop_*"), *project_dir.glob(".thumb_crop_*.tmp")]
    return {path.name: path.read_bytes() for path in paths if path.is_file()}


# ── Project CRUD ────────────────────────────────────────────────────────────


class TestProjectCRUD:
    async def test_create_project(self, client: AsyncClient):
        resp = await client.post(
            "/api/projects",
            json={"name": "M101 Deep", "description": "Pinwheel Galaxy project"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "M101 Deep"
        assert data["description"] == "Pinwheel Galaxy project"
        assert data["status"] == "active"
        assert data["active"] is True
        assert data["images"] == []

    async def test_image_response_has_no_staged_field(self, client: AsyncClient, tmp_path: Path):
        r = await client.post("/api/projects", json={"name": "No Staged"})
        pid = r.json()["id"]
        img = await client.post(
            f"/api/projects/{pid}/images", json={"file_paths": [_png(tmp_path / "a.png")]}
        )
        assert "staged" not in img.json()[0]

    async def test_duplicate_names_allowed(self, client: AsyncClient):
        r1 = await client.post("/api/projects", json={"name": "Same Name"})
        r2 = await client.post("/api/projects", json={"name": "Same Name"})
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.json()["id"] != r2.json()["id"]

    async def test_create_status_invalid_is_422(self, client: AsyncClient):
        resp = await client.post("/api/projects", json={"name": "Bad", "status": "done"})
        assert resp.status_code == 422

    async def test_solved_at(self, client: AsyncClient):
        from nightcrate.db.session import get_db

        created = await client.post("/api/projects", json={"name": "Solve lifecycle"})
        project_id = created.json()["id"]
        assert created.json()["solved_at"] is None

        async with get_db() as conn:
            await conn.execute(
                """
                INSERT INTO project_solve (
                    project_id, image_path, image_width, image_height,
                    center_ra_deg, center_dec_deg, cd1_1, cd1_2, cd2_1, cd2_2,
                    crpix1, crpix2, solved_at
                ) VALUES (?, '/synthetic/solve.fits', 100, 100, 0, 0, 1, 0, 0, 1,
                          50, 50, '2026-03-27 04:05:06')
                """,
                (project_id,),
            )
            await conn.commit()

        solved = await client.get(f"/api/projects/{project_id}")
        assert solved.json()["solved_at"] == "2026-03-27 04:05:06"

        async with get_db() as conn:
            await conn.execute("DELETE FROM project_solve WHERE project_id = ?", (project_id,))
            await conn.commit()

        deleted = await client.get(f"/api/projects/{project_id}")
        assert deleted.json()["solved_at"] is None

    async def test_list_projects(self, client: AsyncClient):
        await client.post("/api/projects", json={"name": "Alpha"})
        await client.post("/api/projects", json={"name": "Beta"})
        resp = await client.get("/api/projects")
        assert resp.status_code == 200
        names = {p["name"] for p in resp.json()}
        assert "Alpha" in names
        assert "Beta" in names

    async def test_list_search(self, client: AsyncClient):
        await client.post(
            "/api/projects",
            json={"name": "Horsehead", "description": "B33 in Orion"},
        )
        await client.post("/api/projects", json={"name": "Rosette"})
        resp = await client.get("/api/projects", params={"q": "orion"})
        items = resp.json()
        assert len(items) == 1
        assert items[0]["name"] == "Horsehead"

    async def test_list_image_count(self, client: AsyncClient, tmp_path: Path):
        r = await client.post("/api/projects", json={"name": "Count Test"})
        pid = r.json()["id"]
        await client.post(
            f"/api/projects/{pid}/images",
            json={"file_paths": [_png(tmp_path / "a.png"), _png(tmp_path / "b.png")]},
        )
        resp = await client.get("/api/projects")
        proj = next(p for p in resp.json() if p["id"] == pid)
        assert proj["image_count"] == 2

    async def test_list_excludes_retired_by_default(self, client: AsyncClient):
        r = await client.post("/api/projects", json={"name": "To Retire"})
        pid = r.json()["id"]
        await client.delete(f"/api/projects/{pid}")
        resp = await client.get("/api/projects")
        names = {p["name"] for p in resp.json()}
        assert "To Retire" not in names

    async def test_get_project_404(self, client: AsyncClient):
        resp = await client.get("/api/projects/99999")
        assert resp.status_code == 404

    async def test_soft_delete_and_restore(self, client: AsyncClient):
        r = await client.post("/api/projects", json={"name": "Delete Me"})
        pid = r.json()["id"]
        assert (await client.delete(f"/api/projects/{pid}")).status_code == 204
        assert (await client.get(f"/api/projects/{pid}")).json()["active"] is False
        assert (await client.post(f"/api/projects/{pid}/restore")).json()["active"] is True

    async def test_permanent_delete(self, client: AsyncClient, tmp_path: Path):
        r = await client.post("/api/projects", json={"name": "Perm Delete"})
        pid = r.json()["id"]
        await client.post(
            f"/api/projects/{pid}/images", json={"file_paths": [_png(tmp_path / "a.png")]}
        )
        assert (await client.delete(f"/api/projects/{pid}/permanent")).status_code == 204
        assert (await client.get(f"/api/projects/{pid}")).status_code == 404

    async def test_permanent_delete_cascade_images(self, client: AsyncClient):
        from nightcrate.db.session import get_db

        r = await client.post("/api/projects", json={"name": "Cascade Perm"})
        pid = r.json()["id"]
        assert (await client.delete(f"/api/projects/{pid}/permanent")).status_code == 204
        async with get_db() as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM project_image WHERE project_id = ?", (pid,)
            )
            assert (await cursor.fetchone())[0] == 0


# ── Update metadata (PATCH) ──────────────────────────────────────────────────


class TestUpdateMetadata:
    async def test_patch_updates_fields(self, client: AsyncClient):
        r = await client.post("/api/projects", json={"name": "Meta", "description": "original"})
        pid = r.json()["id"]
        resp = await client.patch(
            f"/api/projects/{pid}",
            json={"name": "Renamed", "description": "updated", "status": "complete"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed"
        assert resp.json()["description"] == "updated"
        assert resp.json()["status"] == "complete"

    async def test_patch_preserves_unset_fields(self, client: AsyncClient):
        r = await client.post("/api/projects", json={"name": "Keep", "description": "keep me"})
        pid = r.json()["id"]
        resp = await client.patch(f"/api/projects/{pid}", json={"name": "Kept"})
        assert resp.json()["name"] == "Kept"
        assert resp.json()["description"] == "keep me"

    async def test_patch_empty_description_clears(self, client: AsyncClient):
        r = await client.post("/api/projects", json={"name": "Clear", "description": "remove me"})
        pid = r.json()["id"]
        resp = await client.patch(f"/api/projects/{pid}", json={"description": ""})
        assert resp.json()["description"] is None

    async def test_patch_empty_name_422(self, client: AsyncClient):
        r = await client.post("/api/projects", json={"name": "Has Name"})
        pid = r.json()["id"]
        resp = await client.patch(f"/api/projects/{pid}", json={"name": "   "})
        assert resp.status_code == 422

    @pytest.mark.parametrize("status", ["active", "paused", "complete", "abandoned"])
    async def test_update_status_each_value(self, client: AsyncClient, status: str):
        created = await client.post("/api/projects", json={"name": f"Status {status}"})
        project_id = created.json()["id"]

        response = await client.patch(f"/api/projects/{project_id}", json={"status": status})
        assert response.status_code == 200
        assert response.json()["status"] == status
        assert (await client.get(f"/api/projects/{project_id}")).json()["status"] == status

    async def test_update_status_invalid_is_422(self, client: AsyncClient):
        r = await client.post("/api/projects", json={"name": "Status"})
        pid = r.json()["id"]
        await client.patch(f"/api/projects/{pid}", json={"status": "paused"})

        resp = await client.patch(f"/api/projects/{pid}", json={"status": "done"})
        assert resp.status_code == 422
        assert (await client.get(f"/api/projects/{pid}")).json()["status"] == "paused"

    async def test_patch_404(self, client: AsyncClient):
        resp = await client.patch("/api/projects/99999", json={"name": "Nope"})
        assert resp.status_code == 404


# ── Add / remove images ──────────────────────────────────────────────────────


class TestImages:
    async def test_add_single_image_is_main(self, client: AsyncClient, tmp_fits_mono: Path):
        r = await client.post("/api/projects", json={"name": "Add One"})
        pid = r.json()["id"]
        resp = await client.post(
            f"/api/projects/{pid}/images", json={"file_paths": [str(tmp_fits_mono)]}
        )
        assert resp.status_code == 201
        images = resp.json()
        assert len(images) == 1
        assert images[0]["file_path"] == str(tmp_fits_mono)
        assert images[0]["is_main"] is True

    async def test_second_image_not_main(self, client: AsyncClient, tmp_path: Path):
        r = await client.post("/api/projects", json={"name": "Two"})
        pid = r.json()["id"]
        await client.post(
            f"/api/projects/{pid}/images", json={"file_paths": [_png(tmp_path / "a.png")]}
        )
        r2 = await client.post(
            f"/api/projects/{pid}/images", json={"file_paths": [_png(tmp_path / "b.png")]}
        )
        assert r2.json()[0]["is_main"] is False

    async def test_add_archive_enumerates(self, client: AsyncClient, tmp_path: Path):
        r = await client.post("/api/projects", json={"name": "Archive"})
        pid = r.json()["id"]
        archive = tmp_path / "test.zip"
        archive.write_bytes(b"PK")
        mock_contents = [
            {"name": "img1.fits", "type": "file", "size": 100},
            {"name": "img2.xisf", "type": "file", "size": 200},
            {"name": "readme.txt", "type": "file", "size": 50},
        ]
        with (
            patch("nightcrate.api.projects.archive_io.list_contents", return_value=mock_contents),
            patch("nightcrate.api.projects.archive_io.is_archive", return_value=True),
            patch("nightcrate.api.projects.generate_rendered_images"),
        ):
            resp = await client.post(
                f"/api/projects/{pid}/images", json={"file_paths": [str(archive)]}
            )
        assert resp.status_code == 201
        paths = {i["file_path"] for i in resp.json()}
        assert f"{archive}::img1.fits" in paths
        assert f"{archive}::img2.xisf" in paths
        assert len(paths) == 2

    async def test_remove_image(self, client: AsyncClient, tmp_path: Path):
        r = await client.post("/api/projects", json={"name": "Remove"})
        pid = r.json()["id"]
        added = await client.post(
            f"/api/projects/{pid}/images",
            json={"file_paths": [_png(tmp_path / "a.png"), _png(tmp_path / "b.png")]},
        )
        iid = added.json()[0]["id"]
        assert (await client.delete(f"/api/projects/{pid}/images/{iid}")).status_code == 204
        proj = (await client.get(f"/api/projects/{pid}")).json()
        assert [i["id"] for i in proj["images"]] == [added.json()[1]["id"]]

    async def test_remove_main_auto_promotes(self, client: AsyncClient, tmp_path: Path):
        r = await client.post("/api/projects", json={"name": "Promote"})
        pid = r.json()["id"]
        added = await client.post(
            f"/api/projects/{pid}/images",
            json={"file_paths": [_png(tmp_path / "a.png"), _png(tmp_path / "b.png")]},
        )
        main_id, other_id = added.json()[0]["id"], added.json()[1]["id"]
        await client.delete(f"/api/projects/{pid}/images/{main_id}")
        proj = (await client.get(f"/api/projects/{pid}")).json()
        assert proj["images"][0]["id"] == other_id
        assert proj["images"][0]["is_main"] is True

    async def test_remove_image_wrong_project_404(self, client: AsyncClient, tmp_path: Path):
        r = await client.post("/api/projects", json={"name": "Owner"})
        pid = r.json()["id"]
        added = await client.post(
            f"/api/projects/{pid}/images", json={"file_paths": [_png(tmp_path / "a.png")]}
        )
        iid = added.json()[0]["id"]
        other = await client.post("/api/projects", json={"name": "Other"})
        opid = other.json()["id"]
        assert (await client.delete(f"/api/projects/{opid}/images/{iid}")).status_code == 404

    async def test_reorder_images(self, client: AsyncClient, tmp_path: Path):
        r = await client.post("/api/projects", json={"name": "Reorder"})
        pid = r.json()["id"]
        added = await client.post(
            f"/api/projects/{pid}/images",
            json={
                "file_paths": [
                    _png(tmp_path / "a.png"),
                    _png(tmp_path / "b.png"),
                    _png(tmp_path / "c.png"),
                ]
            },
        )
        ids = [i["id"] for i in added.json()]
        reversed_ids = list(reversed(ids))
        resp = await client.put(
            f"/api/projects/{pid}/images/order", json={"image_ids": reversed_ids}
        )
        assert [i["id"] for i in resp.json()["images"]] == reversed_ids

    async def test_set_main_image(self, client: AsyncClient, tmp_path: Path):
        r = await client.post("/api/projects", json={"name": "Main"})
        pid = r.json()["id"]
        added = await client.post(
            f"/api/projects/{pid}/images",
            json={"file_paths": [_png(tmp_path / "a.png"), _png(tmp_path / "b.png")]},
        )
        second_id = added.json()[1]["id"]
        resp = await client.post(f"/api/projects/{pid}/images/{second_id}/main")
        mains = [i for i in resp.json()["images"] if i["is_main"]]
        assert len(mains) == 1
        assert mains[0]["id"] == second_id

    async def test_update_image_notes(self, client: AsyncClient, tmp_path: Path):
        r = await client.post("/api/projects", json={"name": "Notes"})
        pid = r.json()["id"]
        added = await client.post(
            f"/api/projects/{pid}/images", json={"file_paths": [_png(tmp_path / "a.png")]}
        )
        iid = added.json()[0]["id"]
        resp = await client.patch(
            f"/api/projects/{pid}/images/{iid}", json={"notes": "first light"}
        )
        assert resp.status_code == 200
        assert resp.json()["notes"] == "first light"


# ── Rendered images ────────────────────────────────────────────────────────


class TestRenderedImages:
    async def test_rendered_image_after_add(self, client: AsyncClient, tmp_fits_mono: Path):
        r = await client.post("/api/projects", json={"name": "Rendered"})
        pid = r.json()["id"]
        added = await client.post(
            f"/api/projects/{pid}/images", json={"file_paths": [str(tmp_fits_mono)]}
        )
        iid = added.json()[0]["id"]
        resp = await client.get(f"/api/projects/{pid}/images/{iid}/rendered/thumb_sm")
        assert resp.status_code in (200, 204)

    async def test_rendered_invalid_variant_422(self, client: AsyncClient):
        r = await client.post("/api/projects", json={"name": "BadVariant"})
        pid = r.json()["id"]
        resp = await client.get(f"/api/projects/{pid}/images/1/rendered/invalid")
        assert resp.status_code == 422

    async def test_project_thumbnail_204_when_empty(self, client: AsyncClient):
        r = await client.post("/api/projects", json={"name": "Empty Thumb"})
        pid = r.json()["id"]
        resp = await client.get(f"/api/projects/{pid}/thumbnail")
        assert resp.status_code == 204

    async def test_project_thumbnail_accepts_size(self, client: AsyncClient, tmp_fits_mono: Path):
        r = await client.post("/api/projects", json={"name": "Size Thumb"})
        pid = r.json()["id"]
        await client.post(f"/api/projects/{pid}/images", json={"file_paths": [str(tmp_fits_mono)]})
        for size in ("small", "medium", "large"):
            resp = await client.get(f"/api/projects/{pid}/thumbnail", params={"size": size})
            assert resp.status_code in (200, 204), f"size={size} got {resp.status_code}"


# ── Thumbnail crops ────────────────────────────────────────────────────────


class TestThumbnailCrops:
    async def test_put_crop_stores_definition(self, client: AsyncClient, tmp_fits_mono: Path):
        r = await client.post("/api/projects", json={"name": "Crop Save"})
        pid = r.json()["id"]
        added = await client.post(
            f"/api/projects/{pid}/images", json={"file_paths": [str(tmp_fits_mono)]}
        )
        iid = added.json()[0]["id"]
        resp = await client.put(
            f"/api/projects/{pid}/thumbnails",
            json={
                "crops": {
                    "large": {
                        "source_image_id": iid,
                        "crop_x": 0.1,
                        "crop_y": 0.2,
                        "crop_w": 0.5,
                        "crop_h": 0.45,
                    }
                }
            },
        )
        assert resp.status_code == 200
        crops = resp.json()["thumbnail_crops"]
        assert len(crops) == 1
        assert crops[0]["size"] == "large"
        assert crops[0]["source_image_id"] == iid
        assert crops[0]["crop_x"] == 0.1
        assert crops[0]["crop_w"] == 0.5

    async def test_crop_updates_on_second_put(self, client: AsyncClient, tmp_fits_mono: Path):
        r = await client.post("/api/projects", json={"name": "Crop Update"})
        pid = r.json()["id"]
        await client.post(f"/api/projects/{pid}/images", json={"file_paths": [str(tmp_fits_mono)]})
        await client.put(
            f"/api/projects/{pid}/thumbnails",
            json={
                "crops": {"small": {"crop_x": 0.1, "crop_y": 0.2, "crop_w": 0.5, "crop_h": 0.45}}
            },
        )
        await client.put(
            f"/api/projects/{pid}/thumbnails",
            json={
                "crops": {"small": {"crop_x": 0.3, "crop_y": 0.1, "crop_w": 0.4, "crop_h": 0.36}}
            },
        )
        proj = (await client.get(f"/api/projects/{pid}")).json()
        small = next(c for c in proj["thumbnail_crops"] if c["size"] == "small")
        assert small["crop_x"] == 0.3
        assert small["crop_w"] == 0.4

    async def test_crop_null_source_uses_main(self, client: AsyncClient, tmp_fits_mono: Path):
        r = await client.post("/api/projects", json={"name": "Crop Default"})
        pid = r.json()["id"]
        await client.post(f"/api/projects/{pid}/images", json={"file_paths": [str(tmp_fits_mono)]})
        resp = await client.put(
            f"/api/projects/{pid}/thumbnails",
            json={
                "crops": {
                    "large": {
                        "source_image_id": None,
                        "crop_x": 0.1,
                        "crop_y": 0.2,
                        "crop_w": 0.5,
                        "crop_h": 0.45,
                    }
                }
            },
        )
        assert resp.status_code == 200
        crops = resp.json()["thumbnail_crops"]
        assert len(crops) == 1
        assert crops[0]["source_image_id"] is None

    async def test_crop_source_zero_is_422(self, client: AsyncClient, tmp_path: Path):
        from nightcrate.api.projects import _permanent_dir

        project = await client.post("/api/projects", json={"name": "Zero crop source"})
        project_id = project.json()["id"]
        source = _valid_png(tmp_path / "source.png", (40, 80, 120))
        added = await client.post(
            f"/api/projects/{project_id}/images", json={"file_paths": [source]}
        )
        assert added.status_code == 201

        project_dir = _permanent_dir(project_id)
        files_before = {
            path.relative_to(project_dir): path.read_bytes()
            for path in project_dir.rglob("*")
            if path.is_file()
        }
        response = await client.put(
            f"/api/projects/{project_id}/thumbnails",
            json={"crops": {"large": _crop_frame(source_image_id=0)}},
        )

        assert response.status_code == 422
        assert await _crop_rows(project_id) == []
        assert {
            path.relative_to(project_dir): path.read_bytes()
            for path in project_dir.rglob("*")
            if path.is_file()
        } == files_before
        assert list(project_dir.glob(".thumb_crop_*.tmp")) == []

    async def test_cropped_thumbnail_served_over_fallback(
        self, client: AsyncClient, tmp_fits_mono: Path
    ):
        r = await client.post("/api/projects", json={"name": "Crop Serve"})
        pid = r.json()["id"]
        added = await client.post(
            f"/api/projects/{pid}/images", json={"file_paths": [str(tmp_fits_mono)]}
        )
        iid = added.json()[0]["id"]
        resp_before = await client.get(f"/api/projects/{pid}/thumbnail", params={"size": "large"})
        await client.put(
            f"/api/projects/{pid}/thumbnails",
            json={
                "crops": {
                    "large": {
                        "source_image_id": iid,
                        "crop_x": 0.1,
                        "crop_y": 0.2,
                        "crop_w": 0.5,
                        "crop_h": 0.45,
                    }
                }
            },
        )
        resp_after = await client.get(f"/api/projects/{pid}/thumbnail", params={"size": "large"})
        assert resp_after.status_code == 200
        assert resp_after.headers["content-type"] == "image/jpeg"
        if resp_before.status_code == 200:
            assert resp_after.content != resp_before.content

    async def test_removing_source_image_clears_crop_file(
        self, client: AsyncClient, tmp_fits_mono: Path
    ):
        from nightcrate.api.projects import _permanent_dir

        r = await client.post("/api/projects", json={"name": "Crop Cleanup"})
        pid = r.json()["id"]
        added = await client.post(
            f"/api/projects/{pid}/images", json={"file_paths": [str(tmp_fits_mono)]}
        )
        iid = added.json()[0]["id"]
        await client.put(
            f"/api/projects/{pid}/thumbnails",
            json={
                "crops": {
                    "large": {
                        "source_image_id": iid,
                        "crop_x": 0.1,
                        "crop_y": 0.2,
                        "crop_w": 0.5,
                        "crop_h": 0.45,
                    }
                }
            },
        )
        crop_row = (await _crop_rows(pid))[0]
        crop_file = _permanent_dir(pid) / f"thumb_crop_large_{crop_row['id']}.jpg"
        assert crop_file.is_file()
        await client.delete(f"/api/projects/{pid}/images/{iid}")
        assert not crop_file.is_file()

    async def test_portrait_fit_box_crop_is_served_with_black_mat(
        self, client: AsyncClient, tmp_path: Path
    ):
        project = await client.post("/api/projects", json={"name": "Portrait mat"})
        project_id = project.json()["id"]
        source = tmp_path / "portrait.png"
        Image.new("RGB", (16, 32), (80, 140, 220)).save(source)
        image = await client.post(
            f"/api/projects/{project_id}/images", json={"file_paths": [str(source)]}
        )

        saved = await client.put(
            f"/api/projects/{project_id}/thumbnails",
            json={
                "crops": {
                    "small": {
                        "source_image_id": image.json()[0]["id"],
                        "crop_x": -5 / 6,
                        "crop_y": 0,
                        "crop_w": 8 / 3,
                        "crop_h": 1,
                    }
                }
            },
        )
        response = await client.get(f"/api/projects/{project_id}/thumbnail?size=small")

        assert saved.status_code == 200
        assert response.status_code == 200
        with Image.open(io.BytesIO(response.content)) as thumbnail:
            assert thumbnail.format == "JPEG"
            assert thumbnail.size == (480, 360)
            assert max(thumbnail.getpixel((30, 180))) <= 5
            assert max(thumbnail.getpixel((240, 180))) > 100

    @pytest.mark.parametrize(
        ("crop", "message"),
        [
            (
                {"crop_x": 0, "crop_y": 0, "crop_w": 0.5, "crop_h": 0.4},
                "The frame must be 4:3.",
            ),
            (
                {"crop_x": 0.1, "crop_y": 0, "crop_w": 1, "crop_h": 1},
                "The frame must stay within the picture and its mat.",
            ),
            (
                {"crop_x": 1, "crop_y": 0, "crop_w": 1, "crop_h": 1},
                "The frame must include part of the picture.",
            ),
            (
                {"crop_x": float("nan"), "crop_y": 0, "crop_w": 1, "crop_h": 1},
                "Input should be a valid number",
            ),
            (
                {"crop_x": 0, "crop_y": 0, "crop_w": 1},
                "Field required",
            ),
        ],
    )
    async def test_invalid_crop_leaves_no_artifacts(
        self, client: AsyncClient, tmp_path: Path, crop: dict, message: str
    ):
        from nightcrate.api.projects import _permanent_dir

        project = await client.post("/api/projects", json={"name": "Invalid crop"})
        project_id = project.json()["id"]
        source = _valid_png(tmp_path / "invalid-source.png", (40, 80, 120))
        await client.post(f"/api/projects/{project_id}/images", json={"file_paths": [source]})

        url = f"/api/projects/{project_id}/thumbnails"
        if crop.get("crop_x") != crop.get("crop_x"):
            response = await client.put(
                url,
                content=(b'{"crops":{"small":{"crop_x":NaN,"crop_y":0,"crop_w":1,"crop_h":1}}}'),
                headers={"Content-Type": "application/json"},
            )
        else:
            response = await client.put(url, json={"crops": {"small": crop}})

        assert response.status_code == 422
        assert message in str(response.json()["detail"])
        assert await _crop_rows(project_id) == []
        assert _crop_artifacts(_permanent_dir(project_id)) == {}

    async def test_response_includes_thumbnail_crops(self, client: AsyncClient):
        r = await client.post("/api/projects", json={"name": "Crop Response"})
        pid = r.json()["id"]
        proj = (await client.get(f"/api/projects/{pid}")).json()
        assert proj["thumbnail_crops"] == []


class TestImageIdentity:
    async def _project_with_images(
        self,
        client: AsyncClient,
        tmp_path: Path,
        colors: list[tuple[int, int, int]],
    ) -> tuple[int, list[dict], list[Path]]:
        project = await client.post("/api/projects", json={"name": "Image identity"})
        project_id = project.json()["id"]
        paths = [tmp_path / f"source_{index}.png" for index in range(len(colors))]
        for path, color in zip(paths, colors, strict=True):
            _valid_png(path, color)
        added = await client.post(
            f"/api/projects/{project_id}/images",
            json={"file_paths": [str(path) for path in paths]},
        )
        assert added.status_code == 201
        return project_id, added.json(), paths

    async def test_version_stable_without_change(self, client: AsyncClient, tmp_path: Path):
        project_id, _, _ = await self._project_with_images(client, tmp_path, [(20, 40, 60)])
        first = await _project_list_item(client, project_id)
        second = await _project_list_item(client, project_id)
        detail = (await client.get(f"/api/projects/{project_id}")).json()
        assert first["thumbnail_version"] == second["thumbnail_version"]
        assert first["workspace_key"] == second["workspace_key"]
        assert detail["workspace_key"] == first["workspace_key"]

    async def test_version_changes_on_set_main(self, client: AsyncClient, tmp_path: Path):
        project_id, images, _ = await self._project_with_images(
            client, tmp_path, [(220, 10, 10), (10, 20, 220)]
        )
        before = await _project_list_item(client, project_id)
        before_bytes = (
            await client.get(f"/api/projects/{project_id}/thumbnail", params={"size": "large"})
        ).content

        response = await client.post(f"/api/projects/{project_id}/images/{images[1]['id']}/main")
        assert response.status_code == 200
        after = await _project_list_item(client, project_id)
        after_bytes = (
            await client.get(f"/api/projects/{project_id}/thumbnail", params={"size": "large"})
        ).content
        expected = (
            await client.get(
                f"/api/projects/{project_id}/images/{images[1]['id']}/rendered/thumb_lg"
            )
        ).content
        assert before["thumbnail_version"] != after["thumbnail_version"]
        assert after_bytes == expected
        assert after_bytes != before_bytes

    async def test_version_changes_on_first_image(self, client: AsyncClient, tmp_path: Path):
        project = await client.post("/api/projects", json={"name": "First image"})
        project_id = project.json()["id"]
        before = await _project_list_item(client, project_id)
        source = _valid_png(tmp_path / "first.png", (15, 80, 160))
        added = await client.post(
            f"/api/projects/{project_id}/images", json={"file_paths": [source]}
        )
        after = await _project_list_item(client, project_id)
        thumbnail = await client.get(f"/api/projects/{project_id}/thumbnail")
        rendered = await client.get(
            f"/api/projects/{project_id}/images/{added.json()[0]['id']}/rendered/thumb_sm"
        )
        assert before["thumbnail_version"] != after["thumbnail_version"]
        assert thumbnail.content == rendered.content

    async def test_crop_save_new_generation(self, client: AsyncClient, tmp_path: Path):
        from nightcrate.api.projects import _permanent_dir

        project_id, images, _ = await self._project_with_images(client, tmp_path, [(80, 120, 40)])
        payload = {
            "crops": {
                "large": {
                    "source_image_id": images[0]["id"],
                    "crop_x": 0.0,
                    "crop_y": 0.0,
                    "crop_w": 0.75,
                    "crop_h": 0.75,
                }
            }
        }
        assert (
            await client.put(f"/api/projects/{project_id}/thumbnails", json=payload)
        ).status_code == 200
        first_row = (await _crop_rows(project_id))[0]
        first_version = (await _project_list_item(client, project_id))["thumbnail_version"]
        first_file = _permanent_dir(project_id) / f"thumb_crop_large_{first_row['id']}.jpg"
        first_bytes = (await client.get(f"/api/projects/{project_id}/thumbnail?size=large")).content
        assert first_file.read_bytes() == first_bytes

        assert (
            await client.put(f"/api/projects/{project_id}/thumbnails", json=payload)
        ).status_code == 200
        second_row = (await _crop_rows(project_id))[0]
        second_version = (await _project_list_item(client, project_id))["thumbnail_version"]
        second_file = _permanent_dir(project_id) / f"thumb_crop_large_{second_row['id']}.jpg"
        assert second_row["id"] > first_row["id"]
        assert second_version != first_version
        assert second_file.is_file()
        assert not first_file.exists()
        assert (
            await client.get(f"/api/projects/{project_id}/thumbnail?size=large")
        ).content == second_file.read_bytes()

    async def test_failed_crop_generation_changes_nothing(
        self, client: AsyncClient, tmp_path: Path
    ):
        from nightcrate.api.projects import _permanent_dir

        project_id, images, paths = await self._project_with_images(
            client, tmp_path, [(110, 70, 30)]
        )
        url = f"/api/projects/{project_id}/thumbnails"
        initial_payload = {"crops": {"small": _crop_frame(source_image_id=images[0]["id"])}}
        assert (await client.put(url, json=initial_payload)).status_code == 200
        rows_before = await _crop_rows(project_id)
        version_before = (await _project_list_item(client, project_id))["thumbnail_version"]
        files_before = _crop_artifacts(_permanent_dir(project_id))

        source_bytes = paths[0].read_bytes()
        paths[0].unlink()
        retry_payload = {
            "crops": {
                "small": {
                    "source_image_id": images[0]["id"],
                    "crop_x": 0.1,
                    "crop_y": 0.1,
                    "crop_w": 0.8,
                    "crop_h": 0.8,
                }
            }
        }
        failed = await client.put(url, json=retry_payload)
        assert failed.status_code == 422
        assert paths[0].name in failed.json()["detail"]
        assert await _crop_rows(project_id) == rows_before
        assert (await _project_list_item(client, project_id))["thumbnail_version"] == version_before
        assert _crop_artifacts(_permanent_dir(project_id)) == files_before

        paths[0].write_bytes(source_bytes)
        succeeded = await client.put(url, json=retry_payload)
        assert succeeded.status_code == 200
        assert (await _project_list_item(client, project_id))["thumbnail_version"] != version_before

    async def test_rename_failure_rolls_back(self, client: AsyncClient, tmp_path: Path):
        from nightcrate.api.projects import _permanent_dir

        project_id, _, _ = await self._project_with_images(client, tmp_path, [(90, 30, 160)])
        url = f"/api/projects/{project_id}/thumbnails"
        payload = {"crops": {"small": _crop_frame(), "medium": _crop_frame()}}
        assert (await client.put(url, json=payload)).status_code == 200
        rows_before = await _crop_rows(project_id)
        files_before = _crop_artifacts(_permanent_dir(project_id))
        original_rename = Path.rename
        calls = 0

        def fail_second_rename(path: Path, target: Path):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("rename blocked")
            return original_rename(path, target)

        with patch("pathlib.Path.rename", new=fail_second_rename):
            response = await client.put(url, json=payload)
        assert response.status_code == 500
        assert response.json()["detail"] == "Couldn't save the thumbnails: rename blocked"
        assert await _crop_rows(project_id) == rows_before
        assert _crop_artifacts(_permanent_dir(project_id)) == files_before

    async def test_second_temporary_allocation_failure_cleans_staging(
        self, client: AsyncClient, tmp_path: Path
    ):
        from nightcrate.api import projects
        from nightcrate.api.projects import _permanent_dir

        project_id, _, _ = await self._project_with_images(client, tmp_path, [(70, 120, 170)])
        url = f"/api/projects/{project_id}/thumbnails"
        assert (await client.put(url, json={"crops": {"large": _crop_frame()}})).status_code == 200
        rows_before = await _crop_rows(project_id)
        files_before = _crop_artifacts(_permanent_dir(project_id))
        original_named_temporary_file = projects.tempfile.NamedTemporaryFile
        calls = 0

        def fail_second_allocation(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("allocation blocked")
            return original_named_temporary_file(*args, **kwargs)

        with patch(
            "nightcrate.api.projects.tempfile.NamedTemporaryFile", new=fail_second_allocation
        ):
            response = await client.put(
                url,
                json={"crops": {"small": _crop_frame(), "medium": _crop_frame()}},
            )

        assert response.status_code == 500
        assert response.json()["detail"] == "Couldn't save the thumbnails: allocation blocked"
        assert await _crop_rows(project_id) == rows_before
        assert _crop_artifacts(_permanent_dir(project_id)) == files_before

    async def test_main_changed_during_save_is_409(self, client: AsyncClient, tmp_path: Path):
        from nightcrate.api import projects
        from nightcrate.api.projects import _permanent_dir

        project_id, images, _ = await self._project_with_images(
            client, tmp_path, [(100, 30, 20), (20, 30, 100)]
        )
        original_generate = projects._generate_crop_file
        switched = False

        async def switch_main(source_path, size_name, crop_def, out_path):
            nonlocal switched
            await original_generate(source_path, size_name, crop_def, out_path)
            if not switched:
                switched = True
                response = await client.post(
                    f"/api/projects/{project_id}/images/{images[1]['id']}/main"
                )
                assert response.status_code == 200

        with patch("nightcrate.api.projects._generate_crop_file", new=switch_main):
            response = await client.put(
                f"/api/projects/{project_id}/thumbnails",
                json={"crops": {"large": _crop_frame(source_image_id=None)}},
            )
        assert response.status_code == 409
        assert response.json()["detail"] == "The main image changed while saving. Try again."
        assert await _crop_rows(project_id) == []
        assert _crop_artifacts(_permanent_dir(project_id)) == {}

    async def test_commit_failure_removes_new_files(self, client: AsyncClient, tmp_path: Path):
        from aiosqlite.core import Connection

        from nightcrate.api.projects import _permanent_dir

        project_id, _, _ = await self._project_with_images(client, tmp_path, [(25, 125, 225)])
        url = f"/api/projects/{project_id}/thumbnails"
        assert (await client.put(url, json={"crops": {"large": _crop_frame()}})).status_code == 200
        rows_before = await _crop_rows(project_id)
        files_before = _crop_artifacts(_permanent_dir(project_id))

        async def fail_commit(_conn):
            raise OSError("commit blocked")

        with patch.object(Connection, "commit", new=fail_commit):
            response = await client.put(
                url,
                json={"crops": {"large": _crop_frame()}},
            )
        assert response.status_code == 500
        assert response.json()["detail"] == "Couldn't save the thumbnails: commit blocked"
        assert await _crop_rows(project_id) == rows_before
        assert _crop_artifacts(_permanent_dir(project_id)) == files_before

    async def test_crop_without_main_is_422(self, client: AsyncClient):
        project = await client.post("/api/projects", json={"name": "No image"})
        response = await client.put(
            f"/api/projects/{project.json()['id']}/thumbnails",
            json={"crops": {"small": _crop_frame()}},
        )
        assert response.status_code == 422
        assert response.json()["detail"] == "This project has no main image to crop."

    async def test_crop_source_from_another_project_is_422(
        self, client: AsyncClient, tmp_path: Path
    ):
        project_id, _, _ = await self._project_with_images(client, tmp_path, [(80, 30, 10)])
        other = await client.post("/api/projects", json={"name": "Other project"})
        other_id = other.json()["id"]
        other_source = _valid_png(tmp_path / "other.png", (10, 30, 80))
        other_image = await client.post(
            f"/api/projects/{other_id}/images", json={"file_paths": [other_source]}
        )
        image_id = other_image.json()[0]["id"]
        response = await client.put(
            f"/api/projects/{project_id}/thumbnails",
            json={"crops": {"small": _crop_frame(source_image_id=image_id)}},
        )
        assert response.status_code == 422
        assert response.json()["detail"] == f"Image {image_id} isn't in this project."
        assert await _crop_rows(project_id) == []

    async def test_set_main_deletes_follow_main_crops(self, client: AsyncClient, tmp_path: Path):
        from nightcrate.api.projects import _permanent_dir

        project_id, images, _ = await self._project_with_images(
            client, tmp_path, [(230, 50, 20), (20, 50, 230)]
        )
        await client.put(
            f"/api/projects/{project_id}/thumbnails",
            json={
                "crops": {
                    "large": _crop_frame(source_image_id=None),
                    "small": _crop_frame(source_image_id=images[0]["id"]),
                }
            },
        )
        before = {row["size"]: row for row in await _crop_rows(project_id)}
        large_file = _permanent_dir(project_id) / f"thumb_crop_large_{before['large']['id']}.jpg"
        small_file = _permanent_dir(project_id) / f"thumb_crop_small_{before['small']['id']}.jpg"

        await client.post(f"/api/projects/{project_id}/images/{images[1]['id']}/main")
        after = {row["size"]: row for row in await _crop_rows(project_id)}
        served = await client.get(f"/api/projects/{project_id}/thumbnail?size=large")
        fallback = await client.get(
            f"/api/projects/{project_id}/images/{images[1]['id']}/rendered/thumb_lg"
        )
        assert set(after) == {"small"}
        assert not large_file.exists()
        assert small_file.is_file()
        assert served.content == fallback.content

    async def test_remove_main_deletes_follow_main_crops(self, client: AsyncClient, tmp_path: Path):
        from nightcrate.api.projects import _permanent_dir

        project_id, images, _ = await self._project_with_images(
            client, tmp_path, [(180, 80, 20), (20, 80, 180)]
        )
        await client.put(
            f"/api/projects/{project_id}/thumbnails",
            json={"crops": {"large": _crop_frame(source_image_id=None)}},
        )
        crop = (await _crop_rows(project_id))[0]
        crop_file = _permanent_dir(project_id) / f"thumb_crop_large_{crop['id']}.jpg"
        await client.delete(f"/api/projects/{project_id}/images/{images[0]['id']}")
        assert await _crop_rows(project_id) == []
        assert not crop_file.exists()

    async def test_remove_named_image_deletes_its_crops(self, client: AsyncClient, tmp_path: Path):
        from nightcrate.api.projects import _permanent_dir

        project_id, images, _ = await self._project_with_images(
            client, tmp_path, [(50, 180, 20), (180, 50, 20)]
        )
        await client.put(
            f"/api/projects/{project_id}/thumbnails",
            json={"crops": {"small": _crop_frame(source_image_id=images[1]["id"])}},
        )
        crop = (await _crop_rows(project_id))[0]
        crop_file = _permanent_dir(project_id) / f"thumb_crop_small_{crop['id']}.jpg"
        await client.delete(f"/api/projects/{project_id}/images/{images[1]['id']}")
        assert await _crop_rows(project_id) == []
        assert not crop_file.exists()

    async def test_remove_image_write_lock_blocks_interleaved_crop_save(
        self, client: AsyncClient, tmp_path: Path
    ):
        from aiosqlite.core import Connection

        from nightcrate.db.session import get_db_path

        project_id, images, _ = await self._project_with_images(
            client, tmp_path, [(40, 80, 120), (120, 80, 40)]
        )
        removed_id = images[1]["id"]
        original_execute = Connection.execute
        attempted = False

        async def attempt_crop_after_lock(conn, sql, parameters=None):
            nonlocal attempted
            if not attempted and sql.startswith("SELECT id, is_main FROM project_image"):
                attempted = True
                with sqlite3.connect(get_db_path(), timeout=0) as other:
                    with pytest.raises(sqlite3.OperationalError, match="locked"):
                        other.execute(
                            "INSERT INTO project_thumbnail"
                            " (project_id, size, source_image_id, crop_x, crop_y, crop_w, crop_h)"
                            " VALUES (?, 'small', ?, 0, 0, 1, 1)",
                            (project_id, removed_id),
                        )
            return await original_execute(conn, sql, parameters)

        with patch.object(Connection, "execute", new=attempt_crop_after_lock):
            response = await client.delete(f"/api/projects/{project_id}/images/{removed_id}")

        assert response.status_code == 204
        assert attempted
        assert await _crop_rows(project_id) == []

    async def test_set_main_write_lock_blocks_interleaved_follow_main_crop(
        self, client: AsyncClient, tmp_path: Path
    ):
        from aiosqlite.core import Connection

        from nightcrate.db.session import get_db_path

        project_id, images, _ = await self._project_with_images(
            client, tmp_path, [(30, 60, 90), (90, 60, 30)]
        )
        new_main_id = images[1]["id"]
        original_execute = Connection.execute
        attempted = False

        async def attempt_crop_after_lock(conn, sql, parameters=None):
            nonlocal attempted
            if (
                not attempted
                and sql.startswith("SELECT id FROM project_image WHERE id = ?")
                and parameters == (new_main_id, project_id)
            ):
                attempted = True
                with sqlite3.connect(get_db_path(), timeout=0) as other:
                    with pytest.raises(sqlite3.OperationalError, match="locked"):
                        other.execute(
                            "INSERT INTO project_thumbnail"
                            " (project_id, size, source_image_id, crop_x, crop_y, crop_w, crop_h)"
                            " VALUES (?, 'small', NULL, 0, 0, 1, 1)",
                            (project_id,),
                        )
            return await original_execute(conn, sql, parameters)

        with patch.object(Connection, "execute", new=attempt_crop_after_lock):
            response = await client.post(f"/api/projects/{project_id}/images/{new_main_id}/main")

        assert response.status_code == 200
        assert attempted
        assert await _crop_rows(project_id) == []

    async def test_remove_last_image(self, client: AsyncClient, tmp_path: Path):
        project_id, images, _ = await self._project_with_images(client, tmp_path, [(70, 90, 110)])
        await client.delete(f"/api/projects/{project_id}/images/{images[0]['id']}")
        response = await client.get(f"/api/projects/{project_id}/thumbnail")
        assert await _crop_rows(project_id) == []
        assert response.status_code == 204
        assert response.headers["cache-control"] == "no-store"

    async def test_set_main_same_image_keeps_crops(self, client: AsyncClient, tmp_path: Path):
        from nightcrate.api.projects import _permanent_dir

        project_id, images, _ = await self._project_with_images(client, tmp_path, [(75, 125, 175)])
        await client.put(
            f"/api/projects/{project_id}/thumbnails",
            json={"crops": {"medium": _crop_frame(source_image_id=None)}},
        )
        rows_before = await _crop_rows(project_id)
        crop_file = _permanent_dir(project_id) / f"thumb_crop_medium_{rows_before[0]['id']}.jpg"
        bytes_before = crop_file.read_bytes()
        await client.post(f"/api/projects/{project_id}/images/{images[0]['id']}/main")
        assert await _crop_rows(project_id) == rows_before
        assert crop_file.read_bytes() == bytes_before

    async def test_legacy_crop_file_is_ignored(self, client: AsyncClient, tmp_path: Path):
        from nightcrate.api.projects import _permanent_dir
        from nightcrate.db.session import get_db

        project_id, images, _ = await self._project_with_images(client, tmp_path, [(30, 60, 90)])
        async with get_db() as conn:
            await conn.execute(
                "INSERT INTO project_thumbnail (project_id, size) VALUES (?, 'large')",
                (project_id,),
            )
            await conn.commit()
        legacy = _permanent_dir(project_id) / "thumb_crop_large.jpg"
        legacy.write_bytes(b"legacy crop")
        response = await client.get(f"/api/projects/{project_id}/thumbnail?size=large")
        expected = await client.get(
            f"/api/projects/{project_id}/images/{images[0]['id']}/rendered/thumb_lg"
        )
        assert response.status_code == 200
        assert response.content == expected.content
        assert response.content != legacy.read_bytes()

    async def test_save_sweeps_orphan_crops_but_keeps_live_and_temporary_files(
        self, client: AsyncClient, tmp_path: Path
    ):
        from nightcrate.api.projects import _permanent_dir

        project_id, _, _ = await self._project_with_images(client, tmp_path, [(45, 90, 135)])
        url = f"/api/projects/{project_id}/thumbnails"
        assert (await client.put(url, json={"crops": {"large": _crop_frame()}})).status_code == 200
        project_dir = _permanent_dir(project_id)
        large_row = (await _crop_rows(project_id))[0]
        live_large = project_dir / f"thumb_crop_large_{large_row['id']}.jpg"
        live_bytes = live_large.read_bytes()
        legacy_small = project_dir / "thumb_crop_small.jpg"
        orphan_medium = project_dir / "thumb_crop_medium_999.jpg"
        temporary = project_dir / ".thumb_crop_x.tmp"
        legacy_small.write_bytes(b"legacy small")
        orphan_medium.write_bytes(b"orphan medium")
        temporary.write_bytes(b"in-progress elsewhere")

        response = await client.put(
            url,
            json={"crops": {"small": _crop_frame()}},
        )

        rows = {row["size"]: row for row in await _crop_rows(project_id)}
        new_small = project_dir / f"thumb_crop_small_{rows['small']['id']}.jpg"
        assert response.status_code == 200
        assert set(rows) == {"large", "small"}
        assert new_small.is_file()
        assert live_large.read_bytes() == live_bytes
        assert not legacy_small.exists()
        assert not orphan_medium.exists()
        assert temporary.read_bytes() == b"in-progress elsewhere"

    async def test_project_images_are_no_store(self, client: AsyncClient, tmp_path: Path):
        project_id, images, _ = await self._project_with_images(client, tmp_path, [(10, 110, 210)])
        successful_thumbnail = await client.get(f"/api/projects/{project_id}/thumbnail")
        successful_render = await client.get(
            f"/api/projects/{project_id}/images/{images[0]['id']}/rendered/thumb_sm"
        )
        missing_thumbnail = await client.get(f"/api/projects/{project_id}/thumbnail?size=invalid")
        missing_render = await client.get(
            f"/api/projects/{project_id}/images/999999/rendered/thumb_sm"
        )
        assert successful_thumbnail.status_code == 200
        assert successful_render.status_code == 200
        assert successful_thumbnail.headers["cache-control"] == "no-store"
        assert successful_render.headers["cache-control"] == "no-store"
        assert missing_thumbnail.headers["cache-control"] == "no-store"
        assert missing_render.status_code == 204
        assert missing_render.headers["cache-control"] == "no-store"

    async def test_workspace_key_changes_on_every_activation(self):
        from nightcrate.db.session import get_db_path, set_db_path, workspace_key

        path = get_db_path()
        initial = workspace_key()
        assert workspace_key() == initial
        set_db_path(path)
        first_activation = workspace_key()
        assert workspace_key() == first_activation
        set_db_path(path)
        second_activation = workspace_key()
        assert initial != first_activation
        assert first_activation != second_activation
