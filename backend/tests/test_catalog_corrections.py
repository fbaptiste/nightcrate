"""Tests for catalog classification corrections (v0.41.1).

The point of these tests is the *durability* of a manual correction: both
`frame_type` and `project_target_id` are re-derived by the ingest pipeline on
every scan, so each correction has to survive a re-scan via its `*_source`
column (migration 0043).
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.db.session import get_db
from nightcrate.main import app
from nightcrate.services.ingest_classify import FRAME_TYPES
from nightcrate.services.ingest_models import FrameTypeName
from tests.catalog_helpers import (
    _frames,
    _ingest_folder,
    _make_project,
    _write_fits,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _add_target(client: AsyncClient, project_id: int, dso_id: int) -> int:
    """Attach a DSO to the project and return the project_target id."""
    resp = await client.post(f"/api/projects/{project_id}/targets", json={"dso_id": dso_id})
    assert resp.status_code in (200, 201), resp.text
    listing = await client.get(f"/api/projects/{project_id}/targets")
    row = next(t for t in listing.json() if t["dso_id"] == dso_id)
    return row["id"]


async def _seed_dsos(n: int = 2) -> list[int]:
    """Minimal DSO rows so targets can be attached (dso requires a source catalog)."""
    ids = []
    async with get_db() as conn:
        cursor = await conn.execute(
            "INSERT INTO dso_catalog_source (source_id, category, display_name, file_path, "
            "file_hash) VALUES ('test-src', 'nightcrate', 'Test Source', '/x', 'h')"
        )
        source_id = cursor.lastrowid
        for i in range(n):
            cursor = await conn.execute(
                "INSERT INTO dso (primary_designation, obj_type, ra_deg, dec_deg, "
                "source_catalog_id, source_row_hash) VALUES (?, 'Neb', 300.0, 38.0, ?, ?)",
                (f"TestDSO {i + 1}", source_id, f"rowhash{i}"),
            )
            ids.append(cursor.lastrowid)
        await conn.commit()
    return ids


async def _setup(client, tmp_path, *, name: str):
    """A project with one light and one dark cataloged.

    No equipment is seeded: nothing in the ingest or correction path reads any,
    since v0.41.1 removed equipment identification.
    """
    pid = await _make_project(client, name)
    folder = tmp_path / "capture"
    folder.mkdir()
    _write_fits(folder / "light_001.fits")
    _write_fits(folder / "dark_001.fits", imagetyp="DARK", filt=None)
    await _ingest_folder(client, pid, folder)
    return pid, folder


class TestFrameTypeCorrection:
    async def test_manual_frame_type_survives_rescan(self, client, tmp_path):
        """The dark-flat reclassification pass runs on every scan — it must not
        revert a hand-set type."""
        pid, folder = await _setup(client, tmp_path, name="TypeDurable")
        dark = (await _frames(client, pid, frame_type="dark"))[0]

        resp = await client.patch(
            f"/api/projects/{pid}/catalog/frames/{dark['id']}/classification",
            json={"frame_type": "dark_flat"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["frame_type"] == "dark_flat"
        assert resp.json()["frame_type_source"] == "user"

        await _ingest_folder(client, pid, folder, add_folder=False)

        rows = await _frames(client, pid, frame_type="dark_flat")
        assert [r["id"] for r in rows] == [dark["id"]]
        assert rows[0]["frame_type_source"] == "user"

    async def test_reset_to_auto_lets_ingest_rederive(self, client, tmp_path):
        pid, folder = await _setup(client, tmp_path, name="TypeReset")
        dark = (await _frames(client, pid, frame_type="dark"))[0]

        await client.patch(
            f"/api/projects/{pid}/catalog/frames/{dark['id']}/classification",
            json={"frame_type": "dark_flat"},
        )
        resp = await client.patch(
            f"/api/projects/{pid}/catalog/frames/{dark['id']}/classification",
            json={"reset_to_auto": ["frame_type"]},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["frame_type_source"] == "auto"

        # Re-scan re-derives from the header, which still says DARK.
        await _ingest_folder(client, pid, folder, add_folder=False)
        rows = await _frames(client, pid, frame_type="dark")
        assert [r["id"] for r in rows] == [dark["id"]]

    async def test_correcting_to_calibration_drops_the_filter(self, client, tmp_path):
        """Only lights and flats carry a filter. Correcting a light to a dark must
        clear the filter name the header supplied, or the filterless-calibration
        invariant breaks in a way no later pass repairs — re-scan is guarded on
        frame_type_source, so it will not undo the correction either."""
        pid, folder = await _setup(client, tmp_path, name="TypeDropsFilter")
        light = (await _frames(client, pid, frame_type="light"))[0]
        assert light["filter_name"] == "Ha"

        resp = await client.patch(
            f"/api/projects/{pid}/catalog/frames/{light['id']}/classification",
            json={"frame_type": "dark"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["frame_type"] == "dark"
        assert body["filter_name"] is None

        # And a re-scan must not hand the header's filter back.
        await _ingest_folder(client, pid, folder, add_folder=False)
        dark = [r for r in await _frames(client, pid, frame_type="dark") if r["id"] == light["id"]]
        assert dark and dark[0]["filter_name"] is None

    async def test_correcting_back_to_light_restores_the_filter(self, client, tmp_path):
        """The hint follows the corrected type in BOTH directions. A one-way null
        would strand the frame with no filter forever — and matching_flats joins on
        this column, so that frame would silently never match a flat."""
        pid, folder = await _setup(client, tmp_path, name="TypeRestoresFilter")
        light = (await _frames(client, pid, frame_type="light"))[0]

        resp = await client.patch(
            f"/api/projects/{pid}/catalog/frames/{light['id']}/classification",
            json={"frame_type": "dark"},
        )
        assert resp.json()["filter_name"] is None

        resp = await client.patch(
            f"/api/projects/{pid}/catalog/frames/{light['id']}/classification",
            json={"frame_type": "light"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["filter_name"] == "Ha", "the header's FILTER must come back"

        # And a re-scan agrees rather than re-nulling it.
        await _ingest_folder(client, pid, folder, add_folder=False)
        rows = [r for r in await _frames(client, pid, frame_type="light") if r["id"] == light["id"]]
        assert rows and rows[0]["filter_name"] == "Ha"

    async def test_target_on_a_calibration_frame_422(self, client, tmp_path):
        """Only lights carry a target. The automatic path enforces this, so the
        manual path must too — the removed equipment override had the same guard
        for filter_id and losing it would let the two disagree."""
        pid, _ = await _setup(client, tmp_path, name="TargetOnDark")
        dark = (await _frames(client, pid, frame_type="dark"))[0]
        dso_id = (await _seed_dsos(1))[0]
        target_id = await _add_target(client, pid, dso_id)

        resp = await client.patch(
            f"/api/projects/{pid}/catalog/frames/{dark['id']}/classification",
            json={"project_target_id": target_id},
        )
        assert resp.status_code == 422
        assert "Only lights carry a target" in resp.json()["detail"]

        # Clearing it on a calibration frame is still fine (explicit null = none).
        resp = await client.patch(
            f"/api/projects/{pid}/catalog/frames/{dark['id']}/classification",
            json={"project_target_id": None},
        )
        assert resp.status_code == 200, resp.text

        # And correcting the type to light in the SAME request is allowed.
        resp = await client.patch(
            f"/api/projects/{pid}/catalog/frames/{dark['id']}/classification",
            json={"frame_type": "light", "project_target_id": target_id},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["project_target_id"] == target_id

    async def test_null_frame_type_422(self, client, tmp_path):
        pid, _ = await _setup(client, tmp_path, name="TypeNull")
        light = (await _frames(client, pid, frame_type="light"))[0]
        resp = await client.patch(
            f"/api/projects/{pid}/catalog/frames/{light['id']}/classification",
            json={"frame_type": None},
        )
        assert resp.status_code == 422

    async def test_unknown_frame_type_422(self, client, tmp_path):
        pid, _ = await _setup(client, tmp_path, name="TypeBogus")
        light = (await _frames(client, pid, frame_type="light"))[0]
        resp = await client.patch(
            f"/api/projects/{pid}/catalog/frames/{light['id']}/classification",
            json={"frame_type": "flatfield"},
        )
        assert resp.status_code == 422

    async def test_empty_body_422_and_unknown_frame_404(self, client, tmp_path):
        pid, _ = await _setup(client, tmp_path, name="TypeEdges")
        light = (await _frames(client, pid, frame_type="light"))[0]
        resp = await client.patch(
            f"/api/projects/{pid}/catalog/frames/{light['id']}/classification", json={}
        )
        assert resp.status_code == 422
        resp = await client.patch(
            f"/api/projects/{pid}/catalog/frames/999999/classification",
            json={"frame_type": "dark"},
        )
        assert resp.status_code == 404


class TestTargetCorrection:
    async def test_manual_target_survives_rescan_in_multi_target_project(self, client, tmp_path):
        """The case that motivated the source column: ingest assigns a target only
        when the project has exactly one, and writes NULL otherwise — so without
        the guard a re-scan wipes every hand-set target on a multi-target project.
        """
        pid, folder = await _setup(client, tmp_path, name="TargetDurable")
        dso_a, dso_b = await _seed_dsos(2)
        target_a = await _add_target(client, pid, dso_a)
        await _add_target(client, pid, dso_b)  # second target → ingest assigns NULL

        light = (await _frames(client, pid, frame_type="light"))[0]
        resp = await client.patch(
            f"/api/projects/{pid}/catalog/frames/{light['id']}/classification",
            json={"project_target_id": target_a},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["project_target_id"] == target_a
        assert resp.json()["target_name"] == "TestDSO 1"

        await _ingest_folder(client, pid, folder, add_folder=False)

        row = (await _frames(client, pid, frame_type="light"))[0]
        assert row["project_target_id"] == target_a
        assert row["project_target_source"] == "user"

    async def test_target_from_another_project_404(self, client, tmp_path):
        pid, _ = await _setup(client, tmp_path, name="TargetScope")
        other = await _make_project(client, "OtherProject")
        (dso,) = await _seed_dsos(1)
        foreign = await _add_target(client, other, dso)

        light = (await _frames(client, pid, frame_type="light"))[0]
        resp = await client.patch(
            f"/api/projects/{pid}/catalog/frames/{light['id']}/classification",
            json={"project_target_id": foreign},
        )
        assert resp.status_code == 404

    async def test_explicit_null_clears_the_target(self, client, tmp_path):
        pid, _ = await _setup(client, tmp_path, name="TargetClear")
        (dso,) = await _seed_dsos(1)
        target = await _add_target(client, pid, dso)
        light = (await _frames(client, pid, frame_type="light"))[0]

        await client.patch(
            f"/api/projects/{pid}/catalog/frames/{light['id']}/classification",
            json={"project_target_id": target},
        )
        resp = await client.patch(
            f"/api/projects/{pid}/catalog/frames/{light['id']}/classification",
            json={"project_target_id": None},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["project_target_id"] is None
        assert resp.json()["project_target_source"] == "user", "explicit none is still a choice"


class TestBulkCorrection:
    async def test_bulk_applies_to_every_frame(self, client, tmp_path):
        pid = await _make_project(client, "BulkApply")
        folder = tmp_path / "capture"
        folder.mkdir()
        for i in range(4):
            _write_fits(folder / f"dark_{i}.fits", imagetyp="DARK", filt=None)
        await _ingest_folder(client, pid, folder)

        darks = await _frames(client, pid, frame_type="dark")
        assert len(darks) == 4

        resp = await client.post(
            f"/api/projects/{pid}/catalog/frames/bulk-classification",
            json={"frame_ids": [d["id"] for d in darks], "frame_type": "bias"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["updated"] == 4

        assert await _frames(client, pid, frame_type="dark") == []
        biases = await _frames(client, pid, frame_type="bias")
        assert len(biases) == 4
        assert all(b["frame_type_source"] == "user" for b in biases)

    async def test_bulk_is_all_or_nothing(self, client, tmp_path):
        """An unknown id 404s and must leave the earlier frames untouched."""
        pid, _ = await _setup(client, tmp_path, name="BulkAtomic")
        light = (await _frames(client, pid, frame_type="light"))[0]

        resp = await client.post(
            f"/api/projects/{pid}/catalog/frames/bulk-classification",
            json={"frame_ids": [light["id"], 999999], "frame_type": "bias"},
        )
        assert resp.status_code == 404

        rows = await _frames(client, pid, frame_type="light")
        assert [r["id"] for r in rows] == [light["id"]], "the valid frame must not have changed"
        assert rows[0]["frame_type_source"] == "auto"

    async def test_bulk_rejects_empty_id_list_and_empty_body(self, client, tmp_path):
        pid, _ = await _setup(client, tmp_path, name="BulkEdges")
        light = (await _frames(client, pid, frame_type="light"))[0]
        resp = await client.post(
            f"/api/projects/{pid}/catalog/frames/bulk-classification",
            json={"frame_ids": [], "frame_type": "bias"},
        )
        assert resp.status_code == 422
        resp = await client.post(
            f"/api/projects/{pid}/catalog/frames/bulk-classification",
            json={"frame_ids": [light["id"]]},
        )
        assert resp.status_code == 422


class TestVocabularySync:
    def test_frame_type_literal_matches_classifier(self):
        """FrameTypeName restates FRAME_TYPES for Pydantic validation — catch drift."""
        from typing import get_args

        assert set(get_args(FrameTypeName)) == set(FRAME_TYPES)

    async def test_frame_type_literal_matches_db_check(self):
        """...and the DB CHECK constraint, which is the real enforcement."""
        from typing import get_args

        async with get_db() as conn:
            cursor = await conn.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'sub_frame'"
            )
            ddl = (await cursor.fetchone())["sql"]
        for name in get_args(FrameTypeName):
            assert f"'{name}'" in ddl, f"{name} missing from the sub_frame CHECK"
