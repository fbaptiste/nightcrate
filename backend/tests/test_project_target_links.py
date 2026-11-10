from __future__ import annotations

import time

from httpx import ASGITransport, AsyncClient

from nightcrate.db.session import get_db
from nightcrate.main import app
from tests.gallery_library import make_library_dsos, populate_gallery_projects


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_retired_excluded_order_undated_last_and_two_targets():
    async with get_db() as conn:
        dsos = await make_library_dsos(conn)
        dso_a = dsos.ids["m1"]
        dso_b = dsos.ids["m31"]
        recent = await conn.execute(
            """
            INSERT INTO project (name, status, active, created_at)
            VALUES ('Recent', 'active', 1, '2026-01-01')
            """
        )
        older = await conn.execute(
            """
            INSERT INTO project (name, status, active, created_at)
            VALUES ('Older', 'paused', 1, '2025-01-01')
            """
        )
        undated = await conn.execute(
            """
            INSERT INTO project (name, status, active, created_at)
            VALUES ('Undated', 'complete', 1, '2026-02-01')
            """
        )
        retired = await conn.execute("INSERT INTO project (name, active) VALUES ('Retired', 0)")
        for project_id, dso_id in (
            (recent.lastrowid, dso_a),
            (recent.lastrowid, dso_b),
            (older.lastrowid, dso_a),
            (undated.lastrowid, dso_a),
            (retired.lastrowid, dso_a),
        ):
            await conn.execute(
                "INSERT INTO project_target (project_id, dso_id) VALUES (?, ?)",
                (project_id, dso_id),
            )
        for project_id, session_date in (
            (older.lastrowid, "2025-02-02"),
            (recent.lastrowid, "2026-01-02"),
            (recent.lastrowid, "2026-01-03T03:00:00"),
            (recent.lastrowid, "not a date"),
        ):
            await conn.execute(
                """
                INSERT INTO project_session
                    (project_id, line_name, exposure_seconds, num_subs, session_date)
                VALUES (?, 'Ha', 300, 1, ?)
                """,
                (project_id, session_date),
            )
        await conn.commit()

    async with await _client() as client:
        response = await client.get("/api/project-target-links")
    assert response.status_code == 200, response.text
    rows = response.json()
    for_dso_a = [row for row in rows if row["dso_id"] == dso_a]
    assert [row["name"] for row in for_dso_a] == ["Recent", "Older", "Undated"]
    assert for_dso_a[0]["first_date"] == "2026-01-02"
    assert for_dso_a[0]["last_date"] == "2026-01-03"
    assert for_dso_a[0]["nights"] == 2
    assert for_dso_a[0]["imaging_runs"] == [{"start": "2026-01", "end": "2026-01"}]
    assert [row["name"] for row in rows if row["dso_id"] == dso_b] == ["Recent"]
    assert all(row["name"] != "Retired" for row in rows)
    assert [row["dso_id"] for row in rows] == sorted(row["dso_id"] for row in rows)


async def test_500_projects_is_batched():
    async with get_db() as conn:
        dsos = await make_library_dsos(conn)
        await populate_gallery_projects(conn, dsos.all_ids, n_projects=500)
    started = time.perf_counter()
    async with await _client() as client:
        response = await client.get("/api/project-target-links")
    elapsed = time.perf_counter() - started
    assert response.status_code == 200, response.text
    assert response.json()
    assert elapsed < 1.0
