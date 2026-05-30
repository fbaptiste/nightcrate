"""Tests for v0.38.0 project metadata: rig association, location, manual
imaging sessions, per-filter integration summary, and filter goals."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.db.session import get_db
from nightcrate.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ── helpers ──────────────────────────────────────────────────────────────


async def _make_project(client: AsyncClient, name: str = "Sessions Project") -> int:
    r = await client.post("/api/projects", json={"name": name})
    assert r.status_code == 201
    return r.json()["id"]


async def _make_location(client: AsyncClient, name: str = "Backyard") -> int:
    r = await client.post(
        "/api/locations",
        json={"name": name, "latitude": 40.0, "longitude": -74.0, "timezone": "America/New_York"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _make_rig(name: str = "Test Rig") -> int:
    # Rigs are user-created; seed provides camera id=1 and telescope_configuration id=1.
    async with get_db() as conn:
        cur = await conn.execute(
            "INSERT INTO rig (name, telescope_configuration_id, camera_id) VALUES (?, 1, 1)",
            (name,),
        )
        await conn.commit()
        return cur.lastrowid


async def _filter_with_passbands(min_n: int, max_n: int) -> tuple[int, list[str]]:
    async with get_db() as conn:
        cur = await conn.execute(
            "SELECT filter_id, COUNT(*) c FROM filter_passband WHERE active = 1"
            " GROUP BY filter_id HAVING c BETWEEN ? AND ? ORDER BY filter_id LIMIT 1",
            (min_n, max_n),
        )
        row = await cur.fetchone()
        assert row is not None, f"no seeded filter with {min_n}-{max_n} passbands"
        fid = row["filter_id"]
        cur = await conn.execute(
            "SELECT line_name FROM filter_passband WHERE filter_id = ? AND active = 1", (fid,)
        )
        return fid, sorted(r["line_name"] for r in await cur.fetchall())


# ── Rig association ─────────────────────────────────────────────────────────


class TestProjectRigs:
    async def test_set_and_read_rigs(self, client: AsyncClient):
        pid = await _make_project(client)
        r1 = await _make_rig("Rig A")
        r2 = await _make_rig("Rig B")

        resp = await client.put(f"/api/projects/{pid}/rigs", json={"rig_ids": [r1, r2]})
        assert resp.status_code == 200
        rigs = resp.json()["rigs"]
        assert {x["id"] for x in rigs} == {r1, r2}
        assert {x["name"] for x in rigs} == {"Rig A", "Rig B"}

        # Persisted on the project fetch.
        got = await client.get(f"/api/projects/{pid}")
        assert {x["id"] for x in got.json()["rigs"]} == {r1, r2}

    async def test_replace_set_and_dedupe(self, client: AsyncClient):
        pid = await _make_project(client)
        r1 = await _make_rig("Rig A")
        r2 = await _make_rig("Rig B")
        await client.put(f"/api/projects/{pid}/rigs", json={"rig_ids": [r1, r2]})

        # Replace with a single rig, sent twice (dedupe to one).
        resp = await client.put(f"/api/projects/{pid}/rigs", json={"rig_ids": [r2, r2]})
        assert [x["id"] for x in resp.json()["rigs"]] == [r2]

    async def test_clear_rigs(self, client: AsyncClient):
        pid = await _make_project(client)
        r1 = await _make_rig("Rig A")
        await client.put(f"/api/projects/{pid}/rigs", json={"rig_ids": [r1]})
        resp = await client.put(f"/api/projects/{pid}/rigs", json={"rig_ids": []})
        assert resp.json()["rigs"] == []

    async def test_invalid_rig_404(self, client: AsyncClient):
        pid = await _make_project(client)
        resp = await client.put(f"/api/projects/{pid}/rigs", json={"rig_ids": [99999]})
        assert resp.status_code == 404

    async def test_invalid_rig_does_not_clear_existing(self, client: AsyncClient):
        pid = await _make_project(client)
        r1 = await _make_rig("Rig A")
        await client.put(f"/api/projects/{pid}/rigs", json={"rig_ids": [r1]})
        # A bad rig in the set must reject BEFORE the delete-and-reinsert runs.
        await client.put(f"/api/projects/{pid}/rigs", json={"rig_ids": [r1, 99999]})
        got = await client.get(f"/api/projects/{pid}")
        assert [x["id"] for x in got.json()["rigs"]] == [r1]


# ── Location ────────────────────────────────────────────────────────────────


class TestProjectLocation:
    async def test_set_and_clear_location(self, client: AsyncClient):
        pid = await _make_project(client)
        loc = await _make_location(client)

        resp = await client.patch(f"/api/projects/{pid}", json={"location_id": loc})
        assert resp.status_code == 200
        assert resp.json()["location_id"] == loc
        assert resp.json()["location_name"] == "Backyard"

        cleared = await client.patch(f"/api/projects/{pid}", json={"location_id": None})
        assert cleared.json()["location_id"] is None
        assert cleared.json()["location_name"] is None

    async def test_invalid_location_404(self, client: AsyncClient):
        pid = await _make_project(client)
        resp = await client.patch(f"/api/projects/{pid}", json={"location_id": 99999})
        assert resp.status_code == 404

    async def test_location_untouched_when_absent(self, client: AsyncClient):
        pid = await _make_project(client)
        loc = await _make_location(client)
        await client.patch(f"/api/projects/{pid}", json={"location_id": loc})
        # A metadata patch that omits location_id must leave it intact.
        resp = await client.patch(f"/api/projects/{pid}", json={"notes": "hi"})
        assert resp.json()["location_id"] == loc


# ── Sessions CRUD ────────────────────────────────────────────────────────────


class TestSessionsCRUD:
    async def test_create_generic_line(self, client: AsyncClient):
        pid = await _make_project(client)
        resp = await client.post(
            f"/api/projects/{pid}/sessions",
            json={"line_name": "Ha", "exposure_seconds": 300, "num_subs": 20, "gain": 100},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["line_name"] == "Ha"
        assert data["filter_id"] is None
        assert data["integration_minutes"] == 100.0  # 300 * 20 / 60
        assert data["source"] == "manual"

    async def test_create_with_specific_filter(self, client: AsyncClient):
        pid = await _make_project(client)
        fid, _ = await _filter_with_passbands(1, 99)
        resp = await client.post(
            f"/api/projects/{pid}/sessions",
            json={"filter_id": fid, "exposure_seconds": 180, "num_subs": 10},
        )
        assert resp.status_code == 201
        assert resp.json()["filter_id"] == fid
        assert resp.json()["filter_name"] is not None

    async def test_create_requires_filter_or_line(self, client: AsyncClient):
        pid = await _make_project(client)
        resp = await client.post(
            f"/api/projects/{pid}/sessions",
            json={"exposure_seconds": 300, "num_subs": 20},
        )
        assert resp.status_code == 422

    async def test_create_invalid_line_422(self, client: AsyncClient):
        pid = await _make_project(client)
        resp = await client.post(
            f"/api/projects/{pid}/sessions",
            json={"line_name": "Zz", "exposure_seconds": 300, "num_subs": 20},
        )
        assert resp.status_code == 422

    async def test_create_invalid_filter_404(self, client: AsyncClient):
        pid = await _make_project(client)
        resp = await client.post(
            f"/api/projects/{pid}/sessions",
            json={"filter_id": 99999, "exposure_seconds": 300, "num_subs": 20},
        )
        assert resp.status_code == 404

    async def test_create_invalid_rig_404(self, client: AsyncClient):
        pid = await _make_project(client)
        resp = await client.post(
            f"/api/projects/{pid}/sessions",
            json={"line_name": "Ha", "rig_id": 99999, "exposure_seconds": 300, "num_subs": 20},
        )
        assert resp.status_code == 404

    async def test_nonpositive_exposure_422(self, client: AsyncClient):
        pid = await _make_project(client)
        resp = await client.post(
            f"/api/projects/{pid}/sessions",
            json={"line_name": "Ha", "exposure_seconds": 0, "num_subs": 20},
        )
        assert resp.status_code == 422

    async def test_list_orders_dated_first_desc(self, client: AsyncClient):
        pid = await _make_project(client)
        await client.post(
            f"/api/projects/{pid}/sessions",
            json={"line_name": "Ha", "exposure_seconds": 300, "num_subs": 5},
        )  # undated
        await client.post(
            f"/api/projects/{pid}/sessions",
            json={
                "line_name": "Oiii",
                "exposure_seconds": 300,
                "num_subs": 5,
                "session_date": "2026-01-10",
            },
        )
        await client.post(
            f"/api/projects/{pid}/sessions",
            json={
                "line_name": "Sii",
                "exposure_seconds": 300,
                "num_subs": 5,
                "session_date": "2026-02-20",
            },
        )
        rows = (await client.get(f"/api/projects/{pid}/sessions")).json()
        # Dated newest-first, then undated last.
        assert [r["line_name"] for r in rows] == ["Sii", "Oiii", "Ha"]

    async def test_patch_session(self, client: AsyncClient):
        pid = await _make_project(client)
        sid = (
            await client.post(
                f"/api/projects/{pid}/sessions",
                json={"line_name": "Ha", "exposure_seconds": 300, "num_subs": 10},
            )
        ).json()["id"]
        resp = await client.patch(
            f"/api/projects/{pid}/sessions/{sid}", json={"num_subs": 30, "exposure_seconds": 120}
        )
        assert resp.status_code == 200
        assert resp.json()["num_subs"] == 30
        assert resp.json()["integration_minutes"] == 60.0  # 120 * 30 / 60

    async def test_patch_clear_filter_without_line_422(self, client: AsyncClient):
        pid = await _make_project(client)
        fid, _ = await _filter_with_passbands(1, 99)
        sid = (
            await client.post(
                f"/api/projects/{pid}/sessions",
                json={"filter_id": fid, "exposure_seconds": 300, "num_subs": 10},
            )
        ).json()["id"]
        # Clearing the only filter identifier must be rejected.
        resp = await client.patch(f"/api/projects/{pid}/sessions/{sid}", json={"filter_id": None})
        assert resp.status_code == 422

    async def test_patch_null_exposure_422(self, client: AsyncClient):
        pid = await _make_project(client)
        sid = (
            await client.post(
                f"/api/projects/{pid}/sessions",
                json={"line_name": "Ha", "exposure_seconds": 300, "num_subs": 10},
            )
        ).json()["id"]
        resp = await client.patch(
            f"/api/projects/{pid}/sessions/{sid}", json={"exposure_seconds": None}
        )
        assert resp.status_code == 422

    async def test_delete_session(self, client: AsyncClient):
        pid = await _make_project(client)
        sid = (
            await client.post(
                f"/api/projects/{pid}/sessions",
                json={"line_name": "Ha", "exposure_seconds": 300, "num_subs": 10},
            )
        ).json()["id"]
        assert (await client.delete(f"/api/projects/{pid}/sessions/{sid}")).status_code == 204
        assert (await client.get(f"/api/projects/{pid}/sessions")).json() == []

    async def test_session_cross_project_404(self, client: AsyncClient):
        pid1 = await _make_project(client, "P1")
        pid2 = await _make_project(client, "P2")
        sid = (
            await client.post(
                f"/api/projects/{pid1}/sessions",
                json={"line_name": "Ha", "exposure_seconds": 300, "num_subs": 10},
            )
        ).json()["id"]
        # The session belongs to pid1, not pid2.
        assert (await client.get(f"/api/projects/{pid2}/sessions")).json() == []
        resp = await client.patch(f"/api/projects/{pid2}/sessions/{sid}", json={"num_subs": 5})
        assert resp.status_code == 404

    async def test_sessions_cascade_on_project_delete(self, client: AsyncClient):
        pid = await _make_project(client)
        await client.post(
            f"/api/projects/{pid}/sessions",
            json={"line_name": "Ha", "exposure_seconds": 300, "num_subs": 10},
        )
        await client.delete(f"/api/projects/{pid}/permanent")
        async with get_db() as conn:
            cur = await conn.execute(
                "SELECT COUNT(*) c FROM project_session WHERE project_id = ?", (pid,)
            )
            assert (await cur.fetchone())["c"] == 0


# ── Integration summary ─────────────────────────────────────────────────────


class TestIntegration:
    async def test_generic_lines_sum(self, client: AsyncClient):
        pid = await _make_project(client)
        # 300 * 20 = 6000s = 100 min of Ha across two batches.
        await client.post(
            f"/api/projects/{pid}/sessions",
            json={"line_name": "Ha", "exposure_seconds": 300, "num_subs": 10},
        )
        await client.post(
            f"/api/projects/{pid}/sessions",
            json={"line_name": "Ha", "exposure_seconds": 300, "num_subs": 10},
        )
        await client.post(
            f"/api/projects/{pid}/sessions",
            json={"line_name": "Oiii", "exposure_seconds": 600, "num_subs": 5},
        )
        summary = (await client.get(f"/api/projects/{pid}/integration")).json()
        by_line = {ln["line_name"]: ln for ln in summary["lines"]}
        assert by_line["Ha"]["actual_minutes"] == 100.0
        assert by_line["Ha"]["sub_count"] == 20
        assert by_line["Ha"]["session_count"] == 2
        assert by_line["Oiii"]["actual_minutes"] == 50.0
        assert summary["total_actual_minutes"] == 150.0

    async def test_duoband_filter_double_counts(self, client: AsyncClient):
        pid = await _make_project(client)
        fid, lines = await _filter_with_passbands(2, 2)  # e.g. Ha + Oiii
        # 300 * 10 = 3000s = 50 min, contributing to BOTH passband lines.
        await client.post(
            f"/api/projects/{pid}/sessions",
            json={"filter_id": fid, "exposure_seconds": 300, "num_subs": 10},
        )
        summary = (await client.get(f"/api/projects/{pid}/integration")).json()
        by_line = {ln["line_name"]: ln for ln in summary["lines"]}
        for line in lines:
            assert by_line[line]["actual_minutes"] == 50.0
        # Wall-clock total counts the batch once, NOT once per line.
        assert summary["total_actual_minutes"] == 50.0

    async def test_date_range_derived(self, client: AsyncClient):
        pid = await _make_project(client)
        await client.post(
            f"/api/projects/{pid}/sessions",
            json={
                "line_name": "Ha",
                "exposure_seconds": 300,
                "num_subs": 5,
                "session_date": "2026-02-20T22:15:00",
            },
        )
        await client.post(
            f"/api/projects/{pid}/sessions",
            json={
                "line_name": "Ha",
                "exposure_seconds": 300,
                "num_subs": 5,
                "session_date": "2026-01-05",
            },
        )
        await client.post(
            f"/api/projects/{pid}/sessions",
            json={"line_name": "Ha", "exposure_seconds": 300, "num_subs": 5},
        )  # undated — ignored in range
        summary = (await client.get(f"/api/projects/{pid}/integration")).json()
        assert summary["first_session_date"] == "2026-01-05"
        assert summary["last_session_date"] == "2026-02-20"

    async def test_empty_integration(self, client: AsyncClient):
        pid = await _make_project(client)
        summary = (await client.get(f"/api/projects/{pid}/integration")).json()
        assert summary["lines"] == []
        assert summary["total_actual_minutes"] == 0.0
        assert summary["first_session_date"] is None

    async def test_line_ordering(self, client: AsyncClient):
        pid = await _make_project(client)
        for line in ("B", "Ha", "Lum"):  # inserted out of canonical order
            await client.post(
                f"/api/projects/{pid}/sessions",
                json={"line_name": line, "exposure_seconds": 60, "num_subs": 1},
            )
        summary = (await client.get(f"/api/projects/{pid}/integration")).json()
        # Canonical LINE_NAMES order: Ha ... Lum ... B
        assert [ln["line_name"] for ln in summary["lines"]] == ["Ha", "Lum", "B"]


# ── Filter goals ────────────────────────────────────────────────────────────


class TestFilterGoals:
    async def test_set_goals_appear_in_summary(self, client: AsyncClient):
        pid = await _make_project(client)
        resp = await client.put(
            f"/api/projects/{pid}/integration/goals",
            json={"goals": [{"line_name": "Ha", "goal_minutes": 240}]},
        )
        assert resp.status_code == 200
        by_line = {ln["line_name"]: ln for ln in resp.json()["lines"]}
        assert by_line["Ha"]["goal_minutes"] == 240.0
        assert by_line["Ha"]["actual_minutes"] == 0.0  # goal with no sessions yet

    async def test_goals_replace_set(self, client: AsyncClient):
        pid = await _make_project(client)
        await client.put(
            f"/api/projects/{pid}/integration/goals",
            json={"goals": [{"line_name": "Ha", "goal_minutes": 240}]},
        )
        resp = await client.put(
            f"/api/projects/{pid}/integration/goals",
            json={"goals": [{"line_name": "Oiii", "goal_minutes": 120}]},
        )
        by_line = {ln["line_name"]: ln for ln in resp.json()["lines"]}
        assert "Ha" not in by_line  # replaced
        assert by_line["Oiii"]["goal_minutes"] == 120.0

    async def test_goal_invalid_line_422(self, client: AsyncClient):
        pid = await _make_project(client)
        resp = await client.put(
            f"/api/projects/{pid}/integration/goals",
            json={"goals": [{"line_name": "Zz", "goal_minutes": 60}]},
        )
        assert resp.status_code == 422

    async def test_goal_nonpositive_422(self, client: AsyncClient):
        pid = await _make_project(client)
        resp = await client.put(
            f"/api/projects/{pid}/integration/goals",
            json={"goals": [{"line_name": "Ha", "goal_minutes": 0}]},
        )
        assert resp.status_code == 422

    async def test_goal_duplicate_line_last_wins(self, client: AsyncClient):
        pid = await _make_project(client)
        resp = await client.put(
            f"/api/projects/{pid}/integration/goals",
            json={
                "goals": [
                    {"line_name": "Ha", "goal_minutes": 100},
                    {"line_name": "Ha", "goal_minutes": 300},
                ]
            },
        )
        assert resp.status_code == 200
        by_line = {ln["line_name"]: ln for ln in resp.json()["lines"]}
        assert by_line["Ha"]["goal_minutes"] == 300.0
