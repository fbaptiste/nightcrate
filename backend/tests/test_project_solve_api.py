"""Tests for project plate-solve + identified-DSO endpoints.

ASTAP and real image rendering are mocked; the WCS projection (astropy) and
DB layer run for real, so the best-match / store-all / cascade logic is
exercised end to end.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import numpy as np
import pytest
from aiosqlite import Connection
from astropy.io import fits
from httpx import ASGITransport, AsyncClient

from nightcrate.api import project_solve as project_solve_api
from nightcrate.db.session import get_db
from nightcrate.main import app
from nightcrate.services import solve_operations
from nightcrate.services.plate_solve_models import (
    AstapLaunchError,
    ImageReadError,
    PlateSolveResult,
    SolveAttempt,
)

_SCALE = 3.0 / 3600.0  # 3 arcsec/px in degrees

# A self-consistent solve: centre 210/+54, 3"/px, 4000×4000, no rotation.
_SOLVE = dict(
    solved=True,
    ra_deg=210.0,
    dec_deg=54.0,
    ra_hms="14 00 00.0",
    dec_dms="+54 00 00",
    pixel_scale_arcsec=3.0,
    rotation_deg=0.0,
    fov_width_arcmin=200.0,
    fov_height_arcmin=200.0,
    image_width=4000,
    image_height=4000,
    cd1_1=-_SCALE,
    cd1_2=0.0,
    cd2_1=0.0,
    cd2_2=_SCALE,
    crpix1=2000.0,
    crpix2=2000.0,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
def reset_solve_operations():
    solve_operations._reset_for_tests()
    yield
    solve_operations._reset_for_tests()


def _dso_dict(dso_id: int, designation: str, ra: float, dec: float, maj: float) -> dict:
    return {
        "id": dso_id,
        "primary_designation": designation,
        "obj_type": "G",
        "type_group": "Galaxy",
        "ra_deg": ra,
        "dec_deg": dec,
        "maj_axis_arcmin": maj,
        "min_axis_arcmin": maj * 0.9,
        "position_angle_deg": 0.0,
        "common_name": None,
        "constellation": "UMa",
        "distance_pc": None,
        "distance_method": None,
        "mag_b": 9.0,
    }


async def _seed_two_dsos() -> tuple[int, int]:
    """Insert a big central DSO + a smaller offset one; return their ids."""
    async with get_db() as conn:
        await conn.execute(
            "INSERT INTO dso_catalog_source"
            " (source_id, category, display_name, file_path, file_hash, row_count)"
            " VALUES ('test', 'openngc', 'Test', '/dev/null', 'abc', 0)"
        )
        cur = await conn.execute("SELECT id FROM dso_catalog_source WHERE source_id = 'test'")
        sid = int((await cur.fetchone())["id"])

        cur = await conn.execute(
            "INSERT INTO dso (primary_designation, obj_type, ra_deg, dec_deg, constellation,"
            " maj_axis_arcmin, min_axis_arcmin, position_angle_deg, mag_b,"
            " source_catalog_id, source_row_hash)"
            " VALUES ('M 101', 'G', 210.0, 54.0, 'UMa', 28.0, 27.0, 0.0, 8.0, ?, 'h1')",
            (sid,),
        )
        big = cur.lastrowid
        cur = await conn.execute(
            "INSERT INTO dso (primary_designation, obj_type, ra_deg, dec_deg, constellation,"
            " maj_axis_arcmin, min_axis_arcmin, position_angle_deg, mag_b,"
            " source_catalog_id, source_row_hash)"
            " VALUES ('NGC 5474', 'G', 210.1, 54.05, 'UMa', 4.8, 4.3, 0.0, 11.0, ?, 'h2')",
            (sid,),
        )
        small = cur.lastrowid
        await conn.commit()
    return big, small


def _renderer(payload: bytes):
    def render(_image_path, output_dir):
        output_dir.mkdir(parents=True, exist_ok=True)
        for variant in ("full", "thumb_lg", "thumb_md", "thumb_sm"):
            (output_dir / f"{variant}.jpg").write_bytes(payload)

    return render


@contextlib.contextmanager
def _mock_solve(
    dso_dicts: list[dict],
    result_kwargs: dict | None = None,
    *,
    renderer=None,
):
    """Patch ASTAP + cone query + render so the solve runs without external deps."""
    result = PlateSolveResult(**(result_kwargs or _SOLVE))
    with (
        patch(
            "nightcrate.api.project_solve.get_settings",
            new=AsyncMock(
                return_value=SimpleNamespace(
                    astap_executable_path="/fake/astap", default_solver="astap"
                )
            ),
        ),
        patch(
            "nightcrate.api.project_solve.validate_astap_path",
            new=MagicMock(return_value={"valid": True, "error": None}),
        ),
        patch(
            "nightcrate.api.project_solve.run_solve",
            new=AsyncMock(return_value=result),
        ),
        patch(
            "nightcrate.api.project_solve.query_dsos_in_cone",
            new=AsyncMock(return_value=dso_dicts),
        ),
        patch(
            "nightcrate.api.project_solve.generate_rendered_images",
            new=MagicMock(side_effect=renderer),
        ),
    ):
        yield


async def _make_project(client: AsyncClient, name: str) -> int:
    r = await client.post("/api/projects", json={"name": name})
    return r.json()["id"]


def _solve_payload(image_path: str, **values) -> dict:
    return {"image_path": image_path, "operation_id": str(uuid4()), **values}


@contextlib.contextmanager
def _capture_loop_reports():
    loop = asyncio.get_running_loop()
    reports: list[dict[str, object]] = []
    previous_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: reports.append(context))
    try:
        yield reports
    finally:
        loop.set_exception_handler(previous_handler)


async def test_render_repeated_cancellation_wins_late_worker_failure(tmp_path, monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def fail_late(*_args):
        started.set()
        assert release.wait(timeout=5)
        raise OSError("late render failure")

    monkeypatch.setattr(project_solve_api, "generate_rendered_images", fail_late)
    with _capture_loop_reports() as loop_reports:
        task = asyncio.create_task(
            project_solve_api._render_to_staging("image.fits", tmp_path / "staging")
        )
        assert await asyncio.wait_for(asyncio.to_thread(started.wait, 1), timeout=2)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()

        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=1)
        await asyncio.sleep(0)
        assert loop_reports == []


class TestCreateSolve:
    async def test_solve_requires_operation_id_and_rejects_mode(self, client: AsyncClient):
        pid = await _make_project(client, "Solve Contract")

        missing_id = await client.post(
            f"/api/projects/{pid}/solve",
            json={"image_path": "/fake/image.fits"},
        )
        legacy_mode = await client.post(
            f"/api/projects/{pid}/solve",
            json=_solve_payload("/fake/image.fits", mode="blind"),
        )

        assert missing_id.status_code == 422
        assert legacy_mode.status_code == 422
        missing_item = missing_id.json()["detail"][0]
        assert missing_item["type"] == "missing"
        assert missing_item["loc"] == ["body", "operation_id"]
        mode_item = legacy_mode.json()["detail"][0]
        assert mode_item["type"] == "extra_forbidden"
        assert mode_item["loc"] == ["body", "mode"]

    async def test_stores_all_objects_and_flags_main(self, client: AsyncClient):
        big, small = await _seed_two_dsos()
        async with get_db() as conn:
            await conn.executemany(
                "INSERT INTO dso_other_name (dso_id, name, position) VALUES (?, ?, ?)",
                ((big, "Pinwheel Galaxy", 1), (big, "Messier 101", 2)),
            )
            await conn.commit()
        pid = await _make_project(client, "Solve Create")
        dsos = [
            _dso_dict(big, "M 101", 210.0, 54.0, 28.0),
            _dso_dict(small, "NGC 5474", 210.1, 54.05, 4.8),
        ]
        with _mock_solve(dsos):
            resp = await client.post(
                f"/api/projects/{pid}/solve", json=_solve_payload("/fake/light.fits")
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["center_ra_deg"] == 210.0
        assert data["image_width"] == 4000
        # All identified objects stored (not just the main).
        assert {o["dso_id"] for o in data["objects"]} == {big, small}
        mains = [o for o in data["objects"] if o["is_main"]]
        assert len(mains) == 1
        assert mains[0]["dso_id"] == big  # central + largest
        # Overlay data present.
        assert data["wcs"]["naxis1"] == 4000
        assert all("pixel_x" in o for o in data["objects"])
        by_id = {o["dso_id"]: o for o in data["objects"]}
        assert by_id[big]["other_names"] == ["Pinwheel Galaxy", "Messier 101"]
        assert by_id[small]["other_names"] == []

    async def test_conflict_when_solve_exists(self, client: AsyncClient):
        big, small = await _seed_two_dsos()
        pid = await _make_project(client, "Solve Conflict")
        dsos = [_dso_dict(big, "M 101", 210.0, 54.0, 28.0)]
        with _mock_solve(dsos):
            await client.post(f"/api/projects/{pid}/solve", json=_solve_payload("/fake/a.fits"))
            second = await client.post(
                f"/api/projects/{pid}/solve", json=_solve_payload("/fake/b.fits")
            )
        assert second.status_code == 409
        assert second.json()["detail"] == {
            "message": "A plate solve already exists for this project. Delete it first.",
            "failure_reason": "solve_exists",
            "attempts": [],
        }

    async def test_failed_solve_422(self, client: AsyncClient):
        pid = await _make_project(client, "Solve Fail")
        with _mock_solve([], result_kwargs={"solved": False, "error_message": "No stars"}):
            resp = await client.post(
                f"/api/projects/{pid}/solve", json=_solve_payload("/fake/blank.fits")
            )
        assert resp.status_code == 422
        assert resp.json()["detail"] == {
            "message": "No stars",
            "failure_reason": None,
            "attempts": [],
        }

    async def test_no_astap_path_422(self, client: AsyncClient):
        pid = await _make_project(client, "No ASTAP")
        with patch(
            "nightcrate.api.project_solve.get_settings",
            new=AsyncMock(
                return_value=SimpleNamespace(astap_executable_path="", default_solver="astap")
            ),
        ):
            resp = await client.post(
                f"/api/projects/{pid}/solve", json=_solve_payload("/fake/x.fits")
            )
        assert resp.status_code == 422
        assert resp.json()["detail"] == {
            "message": "ASTAP executable path is not configured. Set it in Settings.",
            "failure_reason": "invalid_configuration",
            "attempts": [],
        }

    async def test_solve_empty_field_stores_no_objects(self, client: AsyncClient):
        pid = await _make_project(client, "Empty Field")
        with _mock_solve([]):
            resp = await client.post(
                f"/api/projects/{pid}/solve", json=_solve_payload("/fake/sparse.fits")
            )
        assert resp.status_code == 200
        assert resp.json()["objects"] == []

    async def test_post_returns_attempts_but_get_does_not_persist_them(self, client: AsyncClient):
        pid = await _make_project(client, "Solve Attempts")
        attempt = SolveAttempt(
            solver="astap",
            step="astap_blind",
            position_source="none",
            scale_source="none",
            outcome="solved",
        )
        with _mock_solve([], result_kwargs={**_SOLVE, "attempts": [attempt]}):
            created = await client.post(
                f"/api/projects/{pid}/solve", json=_solve_payload("/fake/a.fits")
            )
        assert created.json()["attempts"][0]["step"] == "astap_blind"
        assert (await client.get(f"/api/projects/{pid}/solve")).json()["attempts"] == []

    async def test_referenced_file_missing_422(self, client: AsyncClient):
        """A missing referenced source file (e.g. a pxiproject master on a
        disconnected drive) surfaces as a clear 422, not a generic 500."""
        pid = await _make_project(client, "Missing Ref")
        with (
            patch(
                "nightcrate.api.project_solve.get_settings",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        astap_executable_path="/fake/astap", default_solver="astap"
                    )
                ),
            ),
            patch(
                "nightcrate.api.project_solve.validate_astap_path",
                new=MagicMock(return_value={"valid": True, "error": None}),
            ),
            patch(
                "nightcrate.api.project_solve.run_solve",
                new=AsyncMock(
                    side_effect=FileNotFoundError("Referenced file not found: /Volumes/X/m.xisf")
                ),
            ),
        ):
            resp = await client.post(
                f"/api/projects/{pid}/solve",
                json=_solve_payload("/fake/p.pxiproject::3"),
            )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail == {
            "message": (
                "Referenced file not found: /Volumes/X/m.xisf — "
                "is the source file's drive connected?"
            ),
            "failure_reason": "read_error",
            "attempts": [],
        }

    async def test_internal_value_error_is_structured_500(self, client: AsyncClient):
        pid = await _make_project(client, "Read Error")
        with (
            patch(
                "nightcrate.api.project_solve.get_settings",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        astap_executable_path=None, default_solver="native"
                    )
                ),
            ),
            patch(
                "nightcrate.api.project_solve.run_solve",
                new=AsyncMock(side_effect=ValueError("Unsupported image data")),
            ),
        ):
            response = await client.post(
                f"/api/projects/{pid}/solve",
                json=_solve_payload("/fake/bad.fits", solver="native"),
            )

        assert response.status_code == 500
        assert response.json()["detail"] == {
            "message": "Internal plate solve error",
            "failure_reason": "error",
            "attempts": [],
        }

    @pytest.mark.parametrize(
        ("error", "status", "reason", "message"),
        [
            (ImageReadError("unsupported image"), 422, "read_error", "unsupported image"),
            (
                AstapLaunchError("ASTAP couldn't be started"),
                422,
                "invalid_configuration",
                "ASTAP couldn't be started",
            ),
            (TimeoutError("too slow"), 408, "time_limit", "too slow"),
        ],
    )
    async def test_application_errors_have_structured_details(
        self, client: AsyncClient, error, status, reason, message
    ):
        pid = await _make_project(client, f"Structured {reason}")
        with patch("nightcrate.api.project_solve.run_solve", new=AsyncMock(side_effect=error)):
            response = await client.post(
                f"/api/projects/{pid}/solve",
                json=_solve_payload("/fake/image.fits", solver="native"),
            )

        assert response.status_code == status
        assert response.json()["detail"] == {
            "message": message,
            "failure_reason": reason,
            "attempts": [],
        }

    async def test_open_attempt_uses_overall_timeout_outcome(self, client: AsyncClient):
        pid = await _make_project(client, "Timeout Attempt")

        async def timeout_with_open_attempt(**values):
            operation = values["operation"]
            operation.start(
                SolveAttempt(
                    solver="native",
                    step="load",
                    position_source="none",
                    scale_source="none",
                )
            )
            raise TimeoutError("too slow")

        with patch("nightcrate.api.project_solve.run_solve", new=timeout_with_open_attempt):
            response = await client.post(
                f"/api/projects/{pid}/solve",
                json=_solve_payload("/fake/image.fits", solver="native"),
            )

        assert response.status_code == 408
        detail = response.json()["detail"]
        assert detail["failure_reason"] == "time_limit"
        assert detail["attempts"][0]["outcome"] == "overall_timeout"

    @pytest.mark.parametrize("solver", ["native", "astap"])
    @pytest.mark.parametrize(
        ("error_type", "text", "expected"),
        [
            (
                FileNotFoundError,
                "missing image.fits",
                "missing image.fits — is the source file's drive connected?",
            ),
            (ImageReadError, "unsupported image type", "unsupported image type"),
            (ImageReadError, "corrupt FITS", "corrupt FITS"),
            (
                ImageReadError,
                "unresolvable pxiproject reference",
                "unresolvable pxiproject reference",
            ),
        ],
    )
    async def test_read_error_cases_for_both_solvers(
        self, client: AsyncClient, solver, error_type, text, expected
    ):
        pid = await _make_project(client, f"{solver} {text}")
        with (
            patch(
                "nightcrate.api.project_solve.get_settings",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        astap_executable_path="/fake/astap", default_solver=solver
                    )
                ),
            ),
            patch(
                "nightcrate.api.project_solve.validate_astap_path",
                new=MagicMock(return_value={"valid": True, "error": None}),
            ),
            patch(
                "nightcrate.api.project_solve.run_solve",
                new=AsyncMock(side_effect=error_type(text)),
            ),
        ):
            response = await client.post(
                f"/api/projects/{pid}/solve",
                json=_solve_payload("/fake/image.fits", solver=solver),
            )

        assert response.status_code == 422
        assert response.json()["detail"] == {
            "message": expected,
            "failure_reason": "read_error",
            "attempts": [],
        }

    async def test_cancel_before_claim_stops_project_solver(self, client: AsyncClient):
        pid = await _make_project(client, "Pending Cancel")
        operation_id = uuid4()
        cancelled = await client.post(
            "/api/plate-solve/cancel", json={"operation_id": str(operation_id)}
        )
        runner = AsyncMock(side_effect=AssertionError("solver ran"))
        with patch("nightcrate.api.project_solve.run_solve", new=runner):
            response = await client.post(
                f"/api/projects/{pid}/solve",
                json={
                    "image_path": "/fake/image.fits",
                    "operation_id": str(operation_id),
                    "solver": "native",
                },
            )
        assert cancelled.json() == {"cancelled": False, "pending": True}
        assert response.status_code == 422
        assert response.json()["detail"]["failure_reason"] == "cancelled"
        runner.assert_not_awaited()

    async def test_cancel_during_project_render_saves_nothing(self, client: AsyncClient):
        pid = await _make_project(client, "Render Cancel")
        operation_id = uuid4()
        render_started = threading.Event()
        release_render = threading.Event()

        def blocked_render(*_args):
            render_started.set()
            release_render.wait(2)

        with (
            patch(
                "nightcrate.api.project_solve.get_settings",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        astap_executable_path=None, default_solver="native"
                    )
                ),
            ),
            patch(
                "nightcrate.api.project_solve.run_solve",
                new=AsyncMock(return_value=PlateSolveResult(**_SOLVE, solver="native")),
            ),
            patch(
                "nightcrate.api.project_solve.query_dsos_in_cone",
                new=AsyncMock(return_value=[]),
            ),
            patch("nightcrate.api.project_solve.generate_rendered_images", new=blocked_render),
        ):
            solve_task = asyncio.create_task(
                client.post(
                    f"/api/projects/{pid}/solve",
                    json={
                        "image_path": "/fake/image.fits",
                        "operation_id": str(operation_id),
                    },
                )
            )
            assert await asyncio.to_thread(render_started.wait, 1)
            cancelled = await client.post(
                "/api/plate-solve/cancel", json={"operation_id": str(operation_id)}
            )
            release_render.set()
            response = await solve_task

        assert cancelled.json() == {"cancelled": True, "pending": False}
        assert response.status_code == 422
        assert response.json()["detail"]["failure_reason"] == "cancelled"
        async with get_db() as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM project_solve WHERE project_id = ?", (pid,)
            )
            assert (await cursor.fetchone())[0] == 0

    async def test_replace_swaps_row_images_and_keeps_main_targets(self, client: AsyncClient):
        big, small = await _seed_two_dsos()
        pid = await _make_project(client, "Replace Success")
        dsos = [
            _dso_dict(big, "M 101", 210.0, 54.0, 28.0),
            _dso_dict(small, "NGC 5474", 210.1, 54.05, 4.8),
        ]
        with _mock_solve(dsos, renderer=_renderer(b"old")):
            first = await client.post(
                f"/api/projects/{pid}/solve", json=_solve_payload("/fake/old.fits")
            )
        old_id = first.json()["id"]
        await client.put(f"/api/projects/{pid}/solve/objects/{small}", json={"is_main": True})
        solve_dir = project_solve_api._solve_dir(pid)
        (solve_dir / "orphan.jpg").write_bytes(b"legacy")
        (solve_dir / "999999").mkdir()
        (solve_dir / "999999" / "full.jpg").write_bytes(b"orphan")
        (solve_dir / ".staging-stray").mkdir()

        with _mock_solve(dsos, renderer=_renderer(b"new")):
            replaced = await client.post(
                f"/api/projects/{pid}/solve",
                json=_solve_payload("/fake/new.fits", replace=True),
            )

        assert replaced.status_code == 200, replaced.text
        data = replaced.json()
        assert data["id"] != old_id
        assert {item["dso_id"] for item in data["objects"] if item["is_main"]} == {
            big,
            small,
        }
        assert {path.name for path in solve_dir.iterdir()} == {str(data["id"])}
        assert (solve_dir / str(data["id"]) / "full.jpg").read_bytes() == b"new"
        image = await client.get(f"/api/projects/{pid}/solve/image/full")
        assert image.content == b"new"

    async def test_failed_solve_and_render_keep_old_generation(self, client: AsyncClient):
        pid = await _make_project(client, "Replace Failures")
        with _mock_solve([], renderer=_renderer(b"old")):
            first = await client.post(
                f"/api/projects/{pid}/solve", json=_solve_payload("/fake/old.fits")
            )
        old_id = first.json()["id"]

        with _mock_solve(
            [],
            result_kwargs={"solved": False, "error_message": "No stars"},
            renderer=_renderer(b"unused"),
        ):
            failed_solve = await client.post(
                f"/api/projects/{pid}/solve",
                json=_solve_payload("/fake/fail.fits", replace=True),
            )
        assert failed_solve.status_code == 422

        def fail_render(*_args):
            raise OSError("render failed")

        with _mock_solve([], renderer=fail_render):
            failed_render = await client.post(
                f"/api/projects/{pid}/solve",
                json=_solve_payload("/fake/render.fits", replace=True),
            )
        assert failed_render.status_code == 422
        assert failed_render.json()["detail"] == {
            "message": (
                "The image solved, but NightCrate couldn't render it for display. "
                "Nothing was saved."
            ),
            "failure_reason": "render_failed",
            "attempts": [],
        }
        current = await client.get(f"/api/projects/{pid}/solve")
        assert current.json()["id"] == old_id
        assert (await client.get(f"/api/projects/{pid}/solve/image/full")).content == b"old"
        assert not list(project_solve_api._solve_dir(pid).glob(".staging-*"))

    async def test_delete_during_replace_render_leaves_staging_for_publication(
        self, client: AsyncClient
    ):
        pid = await _make_project(client, "Delete During Replace")
        with _mock_solve([], renderer=_renderer(b"old")):
            await client.post(f"/api/projects/{pid}/solve", json=_solve_payload("/fake/old.fits"))
        render_started = threading.Event()
        release_render = threading.Event()

        def blocked_render(_image_path, output_dir):
            render_started.set()
            release_render.wait(2)
            _renderer(b"new")(_image_path, output_dir)

        with _mock_solve([], renderer=blocked_render):
            replace_task = asyncio.create_task(
                client.post(
                    f"/api/projects/{pid}/solve",
                    json=_solve_payload("/fake/new.fits", replace=True),
                )
            )
            assert await asyncio.to_thread(render_started.wait, 1)
            assert (await client.delete(f"/api/projects/{pid}/solve")).status_code == 204
            assert list(project_solve_api._solve_dir(pid).glob(".staging-*"))
            release_render.set()
            replaced = await replace_task

        assert replaced.status_code == 200, replaced.text
        assert (await client.get(f"/api/projects/{pid}/solve/image/full")).content == b"new"

    @pytest.mark.parametrize("failure", ["rename", "after_rename", "commit"])
    async def test_publication_failure_rolls_back_and_keeps_old(
        self, client: AsyncClient, failure: str
    ):
        pid = await _make_project(client, f"Replace {failure}")
        with _mock_solve([], renderer=_renderer(b"old")):
            first = await client.post(
                f"/api/projects/{pid}/solve", json=_solve_payload("/fake/old.fits")
            )
        old_id = first.json()["id"]
        original_rename = Path.rename

        def fail_rename(_self, _target):
            raise OSError("rename failed")

        def rename_then_fail(path, target):
            original_rename(path, target)
            raise RuntimeError("interrupted after rename")

        if failure == "rename":
            failure_patch = patch.object(Path, "rename", fail_rename)
        elif failure == "after_rename":
            failure_patch = patch.object(Path, "rename", rename_then_fail)
        else:
            failure_patch = patch(
                "aiosqlite.core.Connection.commit",
                new=AsyncMock(side_effect=OSError("commit failed")),
            )

        with _mock_solve([], renderer=_renderer(b"new")), failure_patch:
            if failure == "rename":
                response = await client.post(
                    f"/api/projects/{pid}/solve",
                    json=_solve_payload("/fake/new.fits", replace=True),
                )
                assert response.status_code == 422
                assert response.json()["detail"]["failure_reason"] == "render_failed"
            else:
                response = await client.post(
                    f"/api/projects/{pid}/solve",
                    json=_solve_payload("/fake/new.fits", replace=True),
                )
                assert response.status_code == 500
                assert response.json()["detail"]["failure_reason"] == "error"

        current = await client.get(f"/api/projects/{pid}/solve")
        assert current.json()["id"] == old_id
        assert (await client.get(f"/api/projects/{pid}/solve/image/full")).content == b"old"
        solve_dir = project_solve_api._solve_dir(pid)
        assert {path.name for path in solve_dir.iterdir()} == {str(old_id)}

    async def test_reused_row_id_residue_is_replaced(self, client: AsyncClient):
        pid = await _make_project(client, "Replace Residue")
        with _mock_solve([], renderer=_renderer(b"old")):
            first = await client.post(
                f"/api/projects/{pid}/solve", json=_solve_payload("/fake/old.fits")
            )
        next_id = first.json()["id"] + 1
        residue = project_solve_api._solve_dir(pid) / str(next_id)
        residue.mkdir(parents=True)
        (residue / "full.jpg").write_bytes(b"residue")

        with _mock_solve([], renderer=_renderer(b"new")):
            replaced = await client.post(
                f"/api/projects/{pid}/solve",
                json=_solve_payload("/fake/new.fits", replace=True),
            )

        assert replaced.json()["id"] == next_id
        assert (residue / "full.jpg").read_bytes() == b"new"

    async def test_reused_generation_removal_failure_rolls_back(self, client: AsyncClient):
        pid = await _make_project(client, "Replace Residue Failure")
        with _mock_solve([], renderer=_renderer(b"old")):
            first = await client.post(
                f"/api/projects/{pid}/solve", json=_solve_payload("/fake/old.fits")
            )
        old_id = first.json()["id"]
        residue = project_solve_api._solve_dir(pid) / str(old_id + 1)
        residue.mkdir(parents=True)
        (residue / "full.jpg").write_bytes(b"residue")
        original_rmtree = project_solve_api.shutil.rmtree
        failed = False

        def fail_residue_once(path, *args, **kwargs):
            nonlocal failed
            if Path(path) == residue and not failed:
                failed = True
                raise OSError("residue removal failed")
            return original_rmtree(path, *args, **kwargs)

        with (
            _mock_solve([], renderer=_renderer(b"new")),
            patch.object(project_solve_api.shutil, "rmtree", new=fail_residue_once),
        ):
            response = await client.post(
                f"/api/projects/{pid}/solve",
                json=_solve_payload("/fake/new.fits", replace=True),
            )

        assert response.status_code == 500
        current = await client.get(f"/api/projects/{pid}/solve")
        assert current.json()["id"] == old_id
        assert (await client.get(f"/api/projects/{pid}/solve/image/full")).content == b"old"
        assert {path.name for path in project_solve_api._solve_dir(pid).iterdir()} == {str(old_id)}

    async def test_cancellation_during_rename_rolls_back_publication(self, client: AsyncClient):
        pid = await _make_project(client, "Rename Cancel")
        operation_id = uuid4()
        rename_started = threading.Event()
        release_rename = threading.Event()
        original_rename = Path.rename

        def blocked_rename(path, target):
            rename_started.set()
            assert release_rename.wait(timeout=5)
            return original_rename(path, target)

        with (
            _mock_solve([], renderer=_renderer(b"new")),
            patch.object(Path, "rename", blocked_rename),
        ):
            solve_task = asyncio.create_task(
                client.post(
                    f"/api/projects/{pid}/solve",
                    json={
                        "image_path": "/fake/new.fits",
                        "operation_id": str(operation_id),
                    },
                )
            )
            assert await asyncio.wait_for(asyncio.to_thread(rename_started.wait, 1), timeout=2)
            solve_task.cancel()
            await asyncio.sleep(0)
            solve_task.cancel()
            await asyncio.sleep(0)

            assert solve_operations.active_operation() is not None
            assert not solve_task.done()
            release_rename.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(solve_task, timeout=1)

        async with get_db() as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM project_solve WHERE project_id = ?", (pid,)
            )
            assert (await cursor.fetchone())[0] == 0
        assert not any(project_solve_api._solve_dir(pid).iterdir())

    @pytest.mark.parametrize("commit_succeeds", [True, False])
    async def test_cancellation_during_commit_preserves_only_committed_generation(
        self, client: AsyncClient, commit_succeeds: bool
    ):
        pid = await _make_project(client, f"Commit Cancel {commit_succeeds}")
        operation_id = uuid4()
        commit_started = asyncio.Event()
        release_commit = asyncio.Event()
        original_commit = Connection.commit

        async def blocked_commit(conn):
            commit_started.set()
            await release_commit.wait()
            if not commit_succeeds:
                raise OSError("commit failed")
            await original_commit(conn)

        with _capture_loop_reports() as loop_reports:
            with (
                _mock_solve([], renderer=_renderer(b"new")),
                patch("aiosqlite.core.Connection.commit", new=blocked_commit),
            ):
                solve_task = asyncio.create_task(
                    client.post(
                        f"/api/projects/{pid}/solve",
                        json={
                            "image_path": "/fake/new.fits",
                            "operation_id": str(operation_id),
                        },
                    )
                )
                await asyncio.wait_for(commit_started.wait(), timeout=1)
                solve_task.cancel()
                await asyncio.sleep(0)
                solve_task.cancel()
                await asyncio.sleep(0)

                assert solve_operations.active_operation() is not None
                assert not solve_task.done()
                release_commit.set()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(solve_task, timeout=1)
                await asyncio.sleep(0)
                assert loop_reports == []

        async with get_db() as conn:
            cursor = await conn.execute("SELECT id FROM project_solve WHERE project_id = ?", (pid,))
            row = await cursor.fetchone()
        generations = list(project_solve_api._solve_dir(pid).glob("[0-9]*"))
        if commit_succeeds:
            assert row is not None
            assert [path.name for path in generations] == [str(row["id"])]
            assert (generations[0] / "full.jpg").read_bytes() == b"new"
        else:
            assert row is None
            assert generations == []

    async def test_post_commit_cleanup_failure_keeps_new_generation(self, client: AsyncClient):
        pid = await _make_project(client, "Cleanup Failure")

        def fail_cleanup(*_args):
            raise OSError("cleanup failed")

        with (
            _mock_solve([], renderer=_renderer(b"new")),
            patch.object(project_solve_api, "_cleanup_generations", new=fail_cleanup),
        ):
            response = await client.post(
                f"/api/projects/{pid}/solve", json=_solve_payload("/fake/new.fits")
            )

        assert response.status_code == 500
        current = await client.get(f"/api/projects/{pid}/solve")
        assert current.status_code == 200
        generation = project_solve_api._solve_dir(pid) / str(current.json()["id"])
        assert (generation / "full.jpg").read_bytes() == b"new"

    async def test_hdu_contract_primary_image_and_attempts(self, client: AsyncClient, tmp_path):
        pid = await _make_project(client, "Project HDU")
        invalid_hdu = await client.post(
            f"/api/projects/{pid}/solve", json=_solve_payload("/fake/a.fits", hdu=1)
        )
        assert invalid_hdu.status_code == 422

        no_primary = tmp_path / "extension.fits"
        fits.HDUList(
            [fits.PrimaryHDU(), fits.ImageHDU(np.ones((10, 10), dtype=np.float32))]
        ).writeto(no_primary)
        runner = AsyncMock(side_effect=AssertionError("solver ran"))
        with (
            patch(
                "nightcrate.api.project_solve.get_settings",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        astap_executable_path=None, default_solver="native"
                    )
                ),
            ),
            patch("nightcrate.api.project_solve.run_solve", new=runner),
        ):
            no_image = await client.post(
                f"/api/projects/{pid}/solve",
                json=_solve_payload(str(no_primary), solver="native"),
            )
        assert no_image.status_code == 422
        assert no_image.json()["detail"]["message"] == (
            "This file's image isn't in its primary extension. "
            "Open it in the Image Analyzer to solve it."
        )
        runner.assert_not_awaited()

        attempt = SolveAttempt(
            solver="astap",
            step="astap_blind",
            position_source="none",
            scale_source="none",
            outcome="no_match",
        )
        with _mock_solve(
            [],
            result_kwargs={
                "solved": False,
                "error_message": "No solution",
                "failure_reason": "no_match",
                "attempts": [attempt],
            },
        ):
            failed = await client.post(
                f"/api/projects/{pid}/solve", json=_solve_payload("/fake/a.fits")
            )
        assert failed.json()["detail"]["attempts"][0]["step"] == "astap_blind"

    async def test_unreadable_primary_fits_is_structured_422(self, client, tmp_path):
        pid = await _make_project(client, "Unreadable FITS")
        corrupt = tmp_path / "corrupt.fits"
        corrupt.write_bytes(b"not a FITS file")
        runner = AsyncMock(side_effect=AssertionError("solver ran"))
        with (
            patch(
                "nightcrate.api.project_solve.get_settings",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        astap_executable_path=None, default_solver="native"
                    )
                ),
            ),
            patch("nightcrate.api.project_solve.run_solve", new=runner),
        ):
            response = await client.post(
                f"/api/projects/{pid}/solve",
                json=_solve_payload(str(corrupt), solver="native"),
            )

        assert response.status_code == 422
        assert response.json()["detail"]["failure_reason"] == "read_error"
        assert response.json()["detail"]["message"].startswith(
            "NightCrate couldn't read this file:"
        )
        runner.assert_not_awaited()

    async def test_cancel_during_commit_is_too_late(self, client: AsyncClient):
        pid = await _make_project(client, "Commit Cancel")
        operation_id = uuid4()
        original_commit = Connection.commit
        cancel_result = None

        async def commit_after_cancel(conn):
            nonlocal cancel_result
            cancel_result = solve_operations.cancel(operation_id)
            await original_commit(conn)

        with (
            _mock_solve([], renderer=_renderer(b"new")),
            patch("aiosqlite.core.Connection.commit", new=commit_after_cancel),
        ):
            response = await client.post(
                f"/api/projects/{pid}/solve",
                json={
                    "image_path": "/fake/new.fits",
                    "operation_id": str(operation_id),
                },
            )

        assert cancel_result is not None
        assert cancel_result.model_dump() == {"cancelled": False, "pending": False}
        assert response.status_code == 200, response.text
        assert response.json()["image_path"] == "/fake/new.fits"

    async def test_cancel_during_cleanup_holds_lock_and_slot(self, client: AsyncClient):
        pid = await _make_project(client, "Cleanup Cancel")
        operation_id = uuid4()
        cleanup_started = threading.Event()
        release_cleanup = threading.Event()
        original_cleanup = project_solve_api._cleanup_generations

        def blocked_cleanup(solve_dir, current_id):
            cleanup_started.set()
            assert release_cleanup.wait(timeout=5)
            original_cleanup(solve_dir, current_id)

        with (
            _mock_solve([], renderer=_renderer(b"new")),
            patch.object(project_solve_api, "_cleanup_generations", new=blocked_cleanup),
        ):
            solve_task = asyncio.create_task(
                client.post(
                    f"/api/projects/{pid}/solve",
                    json={
                        "image_path": "/fake/new.fits",
                        "operation_id": str(operation_id),
                    },
                )
            )
            assert await asyncio.wait_for(asyncio.to_thread(cleanup_started.wait, 1), timeout=2)
            next_staging = project_solve_api._solve_dir(pid) / ".staging-next-operation"
            next_staging.mkdir()
            solve_task.cancel()
            await asyncio.sleep(0)
            solve_task.cancel()
            await asyncio.sleep(0)

            lock = project_solve_api._project_solve_locks[pid]
            assert lock.locked()
            assert solve_operations.active_operation() is not None
            assert solve_operations.active_operation().operation_id == operation_id
            assert not solve_task.done()

            release_cleanup.set()
            with pytest.raises(asyncio.CancelledError):
                await solve_task

        assert not lock.locked()
        assert solve_operations.active_operation() is None
        assert not next_staging.exists()
        current = await client.get(f"/api/projects/{pid}/solve")
        assert current.status_code == 200
        assert (await client.get(f"/api/projects/{pid}/solve/image/full")).content == b"new"


class TestGetSolve:
    async def test_get_after_create(self, client: AsyncClient):
        big, _ = await _seed_two_dsos()
        pid = await _make_project(client, "Solve Get")
        with _mock_solve([_dso_dict(big, "M 101", 210.0, 54.0, 28.0)]):
            await client.post(f"/api/projects/{pid}/solve", json=_solve_payload("/fake/a.fits"))
        resp = await client.get(f"/api/projects/{pid}/solve")
        assert resp.status_code == 200
        assert resp.json()["objects"][0]["dso_id"] == big

    async def test_get_204_when_no_solve(self, client: AsyncClient):
        pid = await _make_project(client, "No Solve")
        resp = await client.get(f"/api/projects/{pid}/solve")
        assert resp.status_code == 204

    async def test_get_marks_inactive_object(self, client: AsyncClient):
        big, _ = await _seed_two_dsos()
        pid = await _make_project(client, "Inactive Solve Object")
        with _mock_solve([_dso_dict(big, "M 101", 210.0, 54.0, 28.0)]):
            await client.post(f"/api/projects/{pid}/solve", json=_solve_payload("/fake/a.fits"))
        async with get_db() as conn:
            await conn.execute("UPDATE dso SET active = 0 WHERE id = ?", (big,))
            await conn.commit()

        resp = await client.get(f"/api/projects/{pid}/solve")
        assert resp.status_code == 200
        assert resp.json()["objects"][0]["active"] is False


class TestSetMain:
    async def test_toggle_main_on(self, client: AsyncClient):
        big, small = await _seed_two_dsos()
        pid = await _make_project(client, "Set Main On")
        dsos = [
            _dso_dict(big, "M 101", 210.0, 54.0, 28.0),
            _dso_dict(small, "NGC 5474", 210.1, 54.05, 4.8),
        ]
        with _mock_solve(dsos):
            await client.post(f"/api/projects/{pid}/solve", json=_solve_payload("/fake/a.fits"))
        # Add the small one as a second main (multi-main allowed).
        resp = await client.put(
            f"/api/projects/{pid}/solve/objects/{small}", json={"is_main": True}
        )
        assert resp.status_code == 200
        mains = {o["dso_id"] for o in resp.json()["objects"] if o["is_main"]}
        assert mains == {big, small}

    async def test_toggle_main_off(self, client: AsyncClient):
        big, _ = await _seed_two_dsos()
        pid = await _make_project(client, "Set Main Off")
        with _mock_solve([_dso_dict(big, "M 101", 210.0, 54.0, 28.0)]):
            await client.post(f"/api/projects/{pid}/solve", json=_solve_payload("/fake/a.fits"))
        resp = await client.put(f"/api/projects/{pid}/solve/objects/{big}", json={"is_main": False})
        assert resp.status_code == 200
        assert all(not o["is_main"] for o in resp.json()["objects"])

    async def test_inactive_object_cannot_become_main_but_existing_main_can_be_unset(
        self, client: AsyncClient
    ):
        big, small = await _seed_two_dsos()
        pid = await _make_project(client, "Inactive Main")
        dsos = [
            _dso_dict(big, "M 101", 210.0, 54.0, 28.0),
            _dso_dict(small, "NGC 5474", 210.1, 54.05, 4.8),
        ]
        with _mock_solve(dsos):
            await client.post(f"/api/projects/{pid}/solve", json=_solve_payload("/fake/a.fits"))
        async with get_db() as conn:
            await conn.execute("UPDATE dso SET active = 0 WHERE id IN (?, ?)", (big, small))
            await conn.commit()

        refused = await client.put(
            f"/api/projects/{pid}/solve/objects/{small}", json={"is_main": True}
        )
        assert refused.status_code == 409
        assert refused.json()["detail"] == "This object is no longer listed in its catalog."

        no_op = await client.put(f"/api/projects/{pid}/solve/objects/{big}", json={"is_main": True})
        assert no_op.status_code == 200
        removed = await client.put(
            f"/api/projects/{pid}/solve/objects/{big}", json={"is_main": False}
        )
        assert removed.status_code == 200
        assert all(not o["is_main"] for o in removed.json()["objects"])

    async def test_unknown_dso_404(self, client: AsyncClient):
        big, _ = await _seed_two_dsos()
        pid = await _make_project(client, "Set Main 404")
        with _mock_solve([_dso_dict(big, "M 101", 210.0, 54.0, 28.0)]):
            await client.post(f"/api/projects/{pid}/solve", json=_solve_payload("/fake/a.fits"))
        resp = await client.put(f"/api/projects/{pid}/solve/objects/999999", json={"is_main": True})
        assert resp.status_code == 404

    async def test_set_main_no_solve_404(self, client: AsyncClient):
        pid = await _make_project(client, "Set Main No Solve")
        resp = await client.put(f"/api/projects/{pid}/solve/objects/1", json={"is_main": True})
        assert resp.status_code == 404


class TestDeleteSolve:
    async def test_delete_cascades_objects(self, client: AsyncClient):
        big, small = await _seed_two_dsos()
        pid = await _make_project(client, "Solve Delete")
        dsos = [
            _dso_dict(big, "M 101", 210.0, 54.0, 28.0),
            _dso_dict(small, "NGC 5474", 210.1, 54.05, 4.8),
        ]
        with _mock_solve(dsos):
            await client.post(f"/api/projects/{pid}/solve", json=_solve_payload("/fake/a.fits"))

        assert (await client.delete(f"/api/projects/{pid}/solve")).status_code == 204
        assert (await client.get(f"/api/projects/{pid}/solve")).status_code == 204

        async with get_db() as conn:
            cur = await conn.execute(
                "SELECT COUNT(*) FROM project_dso pd"
                " JOIN project_solve ps ON ps.id = pd.solve_id WHERE ps.project_id = ?",
                (pid,),
            )
            assert (await cur.fetchone())[0] == 0

    async def test_delete_no_solve_is_noop(self, client: AsyncClient):
        pid = await _make_project(client, "Delete No Solve")
        assert (await client.delete(f"/api/projects/{pid}/solve")).status_code == 204

    async def test_delete_keeps_in_flight_staging(self, client: AsyncClient):
        pid = await _make_project(client, "Delete Staging")
        with _mock_solve([], renderer=_renderer(b"published")):
            created = await client.post(
                f"/api/projects/{pid}/solve", json=_solve_payload("/fake/a.fits")
            )
        solve_dir = project_solve_api._solve_dir(pid)
        staging = solve_dir / ".staging-in-flight"
        staging.mkdir()
        (staging / "full.jpg").write_bytes(b"staging")

        assert (await client.delete(f"/api/projects/{pid}/solve")).status_code == 204
        assert staging.is_dir()
        assert not (solve_dir / str(created.json()["id"])).exists()


class TestSolveImage:
    async def test_invalid_variant_422(self, client: AsyncClient):
        pid = await _make_project(client, "Solve Img Variant")
        resp = await client.get(f"/api/projects/{pid}/solve/image/bogus")
        assert resp.status_code == 422

    async def test_missing_image_204(self, client: AsyncClient):
        pid = await _make_project(client, "Solve Img Missing")
        resp = await client.get(f"/api/projects/{pid}/solve/image/full")
        assert resp.status_code == 204

    async def test_legacy_layout_is_served_and_removed_on_replace(self, client: AsyncClient):
        pid = await _make_project(client, "Legacy Solve Images")
        with _mock_solve([], renderer=_renderer(b"legacy")):
            created = await client.post(
                f"/api/projects/{pid}/solve", json=_solve_payload("/fake/old.fits")
            )
        solve_dir = project_solve_api._solve_dir(pid)
        generation = solve_dir / str(created.json()["id"])
        for image in generation.glob("*.jpg"):
            image.rename(solve_dir / image.name)
        generation.rmdir()
        assert (await client.get(f"/api/projects/{pid}/solve/image/full")).content == b"legacy"

        with _mock_solve([], renderer=_renderer(b"new")):
            replaced = await client.post(
                f"/api/projects/{pid}/solve",
                json=_solve_payload("/fake/new.fits", replace=True),
            )
        assert replaced.status_code == 200
        assert not (solve_dir / "full.jpg").exists()
        assert (await client.get(f"/api/projects/{pid}/solve/image/full")).content == b"new"


class TestNativeSolverPersistence:
    async def test_project_route_calls_the_real_dispatcher(self, client: AsyncClient):
        """The route's call must match run_solve's real signature: only the
        native worker underneath is faked. (Every other route test replaces
        run_solve with a mock that accepts any arguments, which hid a missing
        ``timeout`` argument until a rendered check.)"""
        pid = await _make_project(client, "Real Dispatcher")
        solved = PlateSolveResult(**_SOLVE, solver="native", solve_path="blind")
        with (
            patch(
                "nightcrate.api.project_solve.get_settings",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        astap_executable_path=None, default_solver="native"
                    )
                ),
            ),
            patch(
                "nightcrate.services.native_solver.solve_image.solve_image",
                new=MagicMock(return_value=solved),
            ),
            patch(
                "nightcrate.api.project_solve.query_dsos_in_cone",
                new=AsyncMock(return_value=[]),
            ),
            patch("nightcrate.api.project_solve.generate_rendered_images", new=MagicMock()),
        ):
            created = await client.post(
                f"/api/projects/{pid}/solve", json=_solve_payload("/fake/native.fits")
            )

        assert created.status_code == 200, created.text
        assert created.json()["solver"] == "native"
        assert created.json()["solve_path"] == "blind"

    async def test_project_solve_saves_native_fields(self, client: AsyncClient):
        pid = await _make_project(client, "Native Fields")
        result = PlateSolveResult(
            **_SOLVE,
            solver="native",
            star_catalog="siril-gaia",
            stars_detected=87,
            stars_matched=31,
            rms_px=0.42,
            log_odds=27.5,
            solve_path="near_index",
            scale_stage="exact",
        )
        with (
            patch(
                "nightcrate.api.project_solve.get_settings",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        astap_executable_path=None, default_solver="native"
                    )
                ),
            ),
            patch(
                "nightcrate.api.project_solve.run_solve",
                new=AsyncMock(return_value=result),
            ),
            patch(
                "nightcrate.api.project_solve.query_dsos_in_cone",
                new=AsyncMock(return_value=[]),
            ),
            patch("nightcrate.api.project_solve.generate_rendered_images", new=MagicMock()),
        ):
            created = await client.post(
                f"/api/projects/{pid}/solve", json=_solve_payload("/fake/native.fits")
            )

        assert created.status_code == 200
        data = created.json()
        assert data["solver"] == "native"
        assert data["star_catalog"] == "siril-gaia"
        assert data["stars_detected"] == 87
        assert data["stars_matched"] == 31
        assert data["rms_px"] == 0.42
        assert data["rms_arcsec"] == pytest.approx(1.26)
        assert data["log_odds"] == 27.5
        assert data["solve_path"] == "near_index"
        assert data["scale_stage"] == "exact"

        read_back = await client.get(f"/api/projects/{pid}/solve")
        assert read_back.status_code == 200
        assert read_back.json() == data

    async def test_project_solve_unsolved_detail_object(self, client: AsyncClient):
        pid = await _make_project(client, "Native Failure")
        result = PlateSolveResult(
            solved=False,
            solver="native",
            error_message="No matching star pattern was found.",
            failure_reason="no_match",
        )
        with (
            patch(
                "nightcrate.api.project_solve.get_settings",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        astap_executable_path=None, default_solver="native"
                    )
                ),
            ),
            patch(
                "nightcrate.api.project_solve.run_solve",
                new=AsyncMock(return_value=result),
            ),
        ):
            response = await client.post(
                f"/api/projects/{pid}/solve", json=_solve_payload("/fake/native.fits")
            )

        assert response.status_code == 422
        assert response.json()["detail"] == {
            "message": "No matching star pattern was found.",
            "failure_reason": "no_match",
            "attempts": [],
        }

    async def test_project_solve_forwards_solver_astap(self, client: AsyncClient):
        pid = await _make_project(client, "Explicit ASTAP")
        runner = AsyncMock(return_value=PlateSolveResult(**_SOLVE))
        with (
            patch(
                "nightcrate.api.project_solve.get_settings",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        astap_executable_path="/fake/astap", default_solver="native"
                    )
                ),
            ),
            patch(
                "nightcrate.api.project_solve.validate_astap_path",
                new=MagicMock(return_value={"valid": True, "error": None}),
            ),
            patch("nightcrate.api.project_solve.run_solve", new=runner),
            patch(
                "nightcrate.api.project_solve.query_dsos_in_cone",
                new=AsyncMock(return_value=[]),
            ),
            patch("nightcrate.api.project_solve.generate_rendered_images", new=MagicMock()),
        ):
            response = await client.post(
                f"/api/projects/{pid}/solve",
                json=_solve_payload("/fake/astap.fits", solver="astap"),
            )

        assert response.status_code == 200
        assert runner.await_args.kwargs["solver"] == "astap"
        assert runner.await_args.kwargs["astap_path"] == "/fake/astap"

    async def test_project_solve_cancelled_saves_nothing(self, client: AsyncClient):
        pid = await _make_project(client, "Cancelled Native")
        result = PlateSolveResult(
            solved=False,
            solver="native",
            error_message="Plate solve cancelled.",
            failure_reason="cancelled",
        )
        with (
            patch(
                "nightcrate.api.project_solve.get_settings",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        astap_executable_path=None, default_solver="native"
                    )
                ),
            ),
            patch(
                "nightcrate.api.project_solve.run_solve",
                new=AsyncMock(return_value=result),
            ),
        ):
            response = await client.post(
                f"/api/projects/{pid}/solve", json=_solve_payload("/fake/native.fits")
            )

        assert response.status_code == 422
        async with get_db() as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM project_solve WHERE project_id = ?", (pid,)
            )
            assert (await cursor.fetchone())[0] == 0
            cursor = await conn.execute("SELECT COUNT(*) FROM project_dso")
            assert (await cursor.fetchone())[0] == 0

    async def test_existing_astap_project_solve_reads_back_as_astap(self, client: AsyncClient):
        pid = await _make_project(client, "Legacy ASTAP")
        with _mock_solve([]):
            response = await client.post(
                f"/api/projects/{pid}/solve", json=_solve_payload("/fake/astap.fits")
            )

        assert response.status_code == 200
        read_back = (await client.get(f"/api/projects/{pid}/solve")).json()
        assert read_back["solver"] == "astap"
        for field in (
            "star_catalog",
            "stars_detected",
            "stars_matched",
            "rms_px",
            "rms_arcsec",
            "log_odds",
            "solve_path",
            "scale_stage",
        ):
            assert read_back[field] is None
