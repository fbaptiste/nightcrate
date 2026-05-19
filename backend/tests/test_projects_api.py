"""Tests for project CRUD + staged image management API endpoints."""

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

    async def test_list_excludes_retired_by_default(self, client: AsyncClient):
        r = await client.post("/api/projects", json={"name": "To Retire"})
        pid = r.json()["id"]
        await client.delete(f"/api/projects/{pid}")
        resp = await client.get("/api/projects")
        names = {p["name"] for p in resp.json()}
        assert "To Retire" not in names

    async def test_get_project(self, client: AsyncClient):
        r = await client.post("/api/projects", json={"name": "Get Me"})
        pid = r.json()["id"]
        resp = await client.get(f"/api/projects/{pid}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Get Me"

    async def test_get_project_404(self, client: AsyncClient):
        resp = await client.get("/api/projects/99999")
        assert resp.status_code == 404

    async def test_soft_delete_and_restore(self, client: AsyncClient):
        r = await client.post("/api/projects", json={"name": "Delete Me"})
        pid = r.json()["id"]
        assert (await client.delete(f"/api/projects/{pid}")).status_code == 204
        assert (await client.get(f"/api/projects/{pid}")).json()["active"] is False
        assert (await client.post(f"/api/projects/{pid}/restore")).json()["active"] is True

    async def test_permanent_delete(self, client: AsyncClient, tmp_fits_mono: Path):
        r = await client.post("/api/projects", json={"name": "Perm Delete"})
        pid = r.json()["id"]

        await client.post(
            f"/api/projects/{pid}/images/stage",
            json={"file_paths": [str(tmp_fits_mono)]},
        )
        await client.post(f"/api/projects/{pid}/save", json={})

        resp = await client.delete(f"/api/projects/{pid}/permanent")
        assert resp.status_code == 204

        resp = await client.get(f"/api/projects/{pid}")
        assert resp.status_code == 404

    async def test_permanent_delete_cascade_images(self, client: AsyncClient):
        from nightcrate.db.session import get_db

        r = await client.post("/api/projects", json={"name": "Cascade Perm"})
        pid = r.json()["id"]

        resp = await client.delete(f"/api/projects/{pid}/permanent")
        assert resp.status_code == 204

        async with get_db() as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM project_image WHERE project_id = ?", (pid,)
            )
            assert (await cursor.fetchone())[0] == 0


# ── Stage images ───────────────────────────────────────────────────────────


class TestStageImages:
    async def test_stage_single_image(self, client: AsyncClient, tmp_fits_mono: Path):
        r = await client.post("/api/projects", json={"name": "Stage Test"})
        pid = r.json()["id"]

        resp = await client.post(
            f"/api/projects/{pid}/images/stage",
            json={"file_paths": [str(tmp_fits_mono)]},
        )
        assert resp.status_code == 201
        images = resp.json()
        assert len(images) == 1
        assert images[0]["file_path"] == str(tmp_fits_mono)
        assert images[0]["staged"] is True
        assert images[0]["is_main"] is True

    async def test_staged_images_excluded_from_list_count(
        self, client: AsyncClient, tmp_fits_mono: Path
    ):
        r = await client.post("/api/projects", json={"name": "Count Test"})
        pid = r.json()["id"]

        await client.post(
            f"/api/projects/{pid}/images/stage",
            json={"file_paths": [str(tmp_fits_mono)]},
        )
        resp = await client.get("/api/projects")
        proj = next(p for p in resp.json() if p["id"] == pid)
        assert proj["image_count"] == 0

    async def test_unstage_image(self, client: AsyncClient, tmp_fits_mono: Path):
        r = await client.post("/api/projects", json={"name": "Unstage"})
        pid = r.json()["id"]

        r2 = await client.post(
            f"/api/projects/{pid}/images/stage",
            json={"file_paths": [str(tmp_fits_mono)]},
        )
        iid = r2.json()[0]["id"]

        resp = await client.delete(f"/api/projects/{pid}/images/{iid}/stage")
        assert resp.status_code == 204

        proj = (await client.get(f"/api/projects/{pid}")).json()
        assert len(proj["images"]) == 0

    async def test_unstage_committed_image_409(self, client: AsyncClient, tmp_fits_mono: Path):
        r = await client.post("/api/projects", json={"name": "Committed"})
        pid = r.json()["id"]

        r2 = await client.post(
            f"/api/projects/{pid}/images/stage",
            json={"file_paths": [str(tmp_fits_mono)]},
        )
        iid = r2.json()[0]["id"]

        await client.post(f"/api/projects/{pid}/save", json={})

        resp = await client.delete(f"/api/projects/{pid}/images/{iid}/stage")
        assert resp.status_code == 409

    async def test_stage_archive_enumerates(self, client: AsyncClient, tmp_path: Path):
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
            patch(
                "nightcrate.api.projects.archive_io.list_contents",
                return_value=mock_contents,
            ),
            patch(
                "nightcrate.api.projects.archive_io.is_archive",
                return_value=True,
            ),
            patch(
                "nightcrate.api.projects.generate_rendered_images",
            ),
        ):
            resp = await client.post(
                f"/api/projects/{pid}/images/stage",
                json={"file_paths": [str(archive)]},
            )

        assert resp.status_code == 201
        images = resp.json()
        assert len(images) == 2
        paths = {i["file_path"] for i in images}
        assert f"{archive}::img1.fits" in paths
        assert f"{archive}::img2.xisf" in paths


# ── Save ───────────────────────────────────────────────────────────────────


class TestSave:
    async def test_save_commits_staged_images(self, client: AsyncClient, tmp_fits_mono: Path):
        r = await client.post("/api/projects", json={"name": "Save Test"})
        pid = r.json()["id"]

        await client.post(
            f"/api/projects/{pid}/images/stage",
            json={"file_paths": [str(tmp_fits_mono)]},
        )

        resp = await client.post(f"/api/projects/{pid}/save", json={})
        assert resp.status_code == 200
        images = resp.json()["images"]
        assert len(images) == 1
        assert images[0]["staged"] is False

    async def test_save_updates_metadata(self, client: AsyncClient):
        r = await client.post(
            "/api/projects",
            json={"name": "Meta", "description": "original"},
        )
        pid = r.json()["id"]

        resp = await client.post(
            f"/api/projects/{pid}/save",
            json={"name": "Renamed", "description": "updated", "status": "complete"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed"
        assert resp.json()["description"] == "updated"
        assert resp.json()["status"] == "complete"

    async def test_save_preserves_unset_fields(self, client: AsyncClient):
        r = await client.post(
            "/api/projects",
            json={"name": "Keep", "description": "keep me"},
        )
        pid = r.json()["id"]
        resp = await client.post(f"/api/projects/{pid}/save", json={"name": "Kept"})
        assert resp.json()["description"] == "keep me"

    async def test_save_removes_images(self, client: AsyncClient, tmp_path: Path):
        img1 = tmp_path / "a.png"
        img2 = tmp_path / "b.png"
        img1.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
        img2.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

        r = await client.post("/api/projects", json={"name": "Remove Test"})
        pid = r.json()["id"]

        r1 = await client.post(
            f"/api/projects/{pid}/images/stage",
            json={"file_paths": [str(img1), str(img2)]},
        )
        await client.post(f"/api/projects/{pid}/save", json={})

        iid = r1.json()[0]["id"]
        resp = await client.post(
            f"/api/projects/{pid}/save",
            json={"remove_image_ids": [iid]},
        )
        assert len(resp.json()["images"]) == 1

    async def test_save_reorders_images(self, client: AsyncClient, tmp_path: Path):
        imgs = []
        for name in ["c.png", "a.png", "b.png"]:
            p = tmp_path / name
            p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
            imgs.append(str(p))

        r = await client.post("/api/projects", json={"name": "Reorder"})
        pid = r.json()["id"]

        await client.post(f"/api/projects/{pid}/images/stage", json={"file_paths": imgs})
        await client.post(f"/api/projects/{pid}/save", json={})

        proj = (await client.get(f"/api/projects/{pid}")).json()
        ids = [i["id"] for i in proj["images"]]
        reversed_ids = list(reversed(ids))

        resp = await client.post(
            f"/api/projects/{pid}/save",
            json={"image_order": reversed_ids},
        )
        result_ids = [i["id"] for i in resp.json()["images"]]
        assert result_ids == reversed_ids

    async def test_save_sets_main_image(self, client: AsyncClient, tmp_path: Path):
        img1 = tmp_path / "x.png"
        img2 = tmp_path / "y.png"
        img1.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
        img2.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

        r = await client.post("/api/projects", json={"name": "Main"})
        pid = r.json()["id"]

        r2 = await client.post(
            f"/api/projects/{pid}/images/stage",
            json={"file_paths": [str(img1), str(img2)]},
        )
        await client.post(f"/api/projects/{pid}/save", json={})

        second_id = r2.json()[1]["id"]
        resp = await client.post(
            f"/api/projects/{pid}/save",
            json={"main_image_id": second_id},
        )
        mains = [i for i in resp.json()["images"] if i["is_main"]]
        assert len(mains) == 1
        assert mains[0]["id"] == second_id


# ── Discard ────────────────────────────────────────────────────────────────


class TestDiscard:
    async def test_discard_removes_staged_images(self, client: AsyncClient, tmp_fits_mono: Path):
        r = await client.post("/api/projects", json={"name": "Discard"})
        pid = r.json()["id"]

        await client.post(
            f"/api/projects/{pid}/images/stage",
            json={"file_paths": [str(tmp_fits_mono)]},
        )

        resp = await client.post(f"/api/projects/{pid}/discard")
        assert resp.status_code == 200
        assert len(resp.json()["images"]) == 0

    async def test_discard_preserves_committed_images(
        self, client: AsyncClient, tmp_fits_mono: Path
    ):
        r = await client.post("/api/projects", json={"name": "Keep Committed"})
        pid = r.json()["id"]

        await client.post(
            f"/api/projects/{pid}/images/stage",
            json={"file_paths": [str(tmp_fits_mono)]},
        )
        await client.post(f"/api/projects/{pid}/save", json={})

        img2 = tmp_fits_mono.parent / "second.fits"
        import shutil

        shutil.copy(tmp_fits_mono, img2)
        await client.post(
            f"/api/projects/{pid}/images/stage",
            json={"file_paths": [str(img2)]},
        )

        resp = await client.post(f"/api/projects/{pid}/discard")
        images = resp.json()["images"]
        assert len(images) == 1
        assert images[0]["staged"] is False


# ── Rendered images ────────────────────────────────────────────────────────


class TestRenderedImages:
    async def test_rendered_image_after_save(self, client: AsyncClient, tmp_fits_mono: Path):
        r = await client.post("/api/projects", json={"name": "Rendered"})
        pid = r.json()["id"]

        r2 = await client.post(
            f"/api/projects/{pid}/images/stage",
            json={"file_paths": [str(tmp_fits_mono)]},
        )
        iid = r2.json()[0]["id"]

        resp = await client.get(f"/api/projects/{pid}/images/{iid}/rendered/thumb_sm")
        assert resp.status_code == 200 or resp.status_code == 204

        await client.post(f"/api/projects/{pid}/save", json={})

        resp = await client.get(f"/api/projects/{pid}/images/{iid}/rendered/thumb_sm")
        assert resp.status_code == 200 or resp.status_code == 204

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
