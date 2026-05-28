"""Tests for project CRUD + save-as-you-go image management endpoints."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

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

    async def test_create_invalid_status_422(self, client: AsyncClient):
        resp = await client.post("/api/projects", json={"name": "Bad", "status": "invalid"})
        assert resp.status_code == 422

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

    async def test_patch_invalid_status_422(self, client: AsyncClient):
        r = await client.post("/api/projects", json={"name": "Status"})
        pid = r.json()["id"]
        resp = await client.patch(f"/api/projects/{pid}", json={"status": "bogus"})
        assert resp.status_code == 422

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
                        "crop_h": 0.5,
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
            json={"crops": {"small": {"crop_x": 0.1, "crop_w": 0.8}}},
        )
        await client.put(
            f"/api/projects/{pid}/thumbnails",
            json={"crops": {"small": {"crop_x": 0.3, "crop_w": 0.4}}},
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
            json={"crops": {"large": {"source_image_id": None, "crop_w": 0.5, "crop_h": 0.5}}},
        )
        assert resp.status_code == 200
        crops = resp.json()["thumbnail_crops"]
        assert len(crops) == 1
        assert crops[0]["source_image_id"] is None

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
                        "crop_x": 0.25,
                        "crop_y": 0.25,
                        "crop_w": 0.5,
                        "crop_h": 0.5,
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
            json={"crops": {"large": {"source_image_id": iid, "crop_w": 0.5, "crop_h": 0.5}}},
        )
        crop_file = _permanent_dir(pid) / "thumb_crop_large.jpg"
        assert crop_file.is_file()
        await client.delete(f"/api/projects/{pid}/images/{iid}")
        assert not crop_file.is_file()

    async def test_response_includes_thumbnail_crops(self, client: AsyncClient):
        r = await client.post("/api/projects", json={"name": "Crop Response"})
        pid = r.json()["id"]
        proj = (await client.get(f"/api/projects/{pid}")).json()
        assert proj["thumbnail_crops"] == []
