"""API and database-loading tests for the gallery endpoint."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.api._common import load_designations
from nightcrate.core.app_config import get_projects_root
from nightcrate.db.session import get_db
from nightcrate.main import app
from nightcrate.services.project_images import crop_path
from tests.gallery_library import make_library_dsos, populate_gallery_projects


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


async def _project(conn, name: str, *, status: str = "active", active: int = 1) -> int:
    cursor = await conn.execute(
        "INSERT INTO project (name, status, active) VALUES (?, ?, ?)",
        (name, status, active),
    )
    return int(cursor.lastrowid)


async def _target(conn, project_id: int, dso_id: int) -> None:
    await conn.execute(
        "INSERT INTO project_target (project_id, dso_id) VALUES (?, ?)",
        (project_id, dso_id),
    )


async def _image(conn, project_id: int, name: str, *, main: bool = False) -> int:
    cursor = await conn.execute(
        """
        INSERT INTO project_image (project_id, file_path, is_main)
        VALUES (?, ?, ?)
        """,
        (project_id, f"/synthetic/{name}.fits", main),
    )
    return int(cursor.lastrowid)


async def _crop(
    conn,
    project_id: int,
    size: str,
    source_image_id: int | None,
    *,
    create_file: bool = True,
) -> int:
    cursor = await conn.execute(
        """
        INSERT INTO project_thumbnail (project_id, size, source_image_id)
        VALUES (?, ?, ?)
        """,
        (project_id, size, source_image_id),
    )
    crop_id = int(cursor.lastrowid)
    if create_file:
        root = get_projects_root()
        assert root is not None
        project_folder = root / str(project_id)
        project_folder.mkdir(parents=True, exist_ok=True)
        crop_path(project_folder, size, crop_id).write_bytes(b"crop")
    return crop_id


async def _solve(conn, project_id: int, dso_ids: list[int]) -> None:
    cursor = await conn.execute(
        """
        INSERT INTO project_solve (
            project_id, image_path, image_width, image_height,
            center_ra_deg, center_dec_deg, cd1_1, cd1_2, cd2_1, cd2_2,
            crpix1, crpix2
        ) VALUES (?, '/synthetic/solve.fits', 100, 100, 0, 0, 1, 0, 0, 1, 50, 50)
        """,
        (project_id,),
    )
    for dso_id in dso_ids:
        await conn.execute(
            "INSERT INTO project_dso (solve_id, dso_id) VALUES (?, ?)",
            (cursor.lastrowid, dso_id),
        )


async def test_inactive_target_still_matches(client: AsyncClient):
    async with get_db() as conn:
        dsos = await make_library_dsos(conn)
        project_id = await _project(conn, "Inactive target")
        await _target(conn, project_id, dsos.inactive_id)
        await conn.commit()
    for params in (
        {"q": "Sh2-240"},
        {"catalog": "sharpless2"},
        {"type_group": "Supernova Remnant"},
        {"constellation": "Tau"},
    ):
        response = await client.get("/api/gallery", params=params)
        assert response.status_code == 200, response.text
        assert [item["project_id"] for item in response.json()["items"]] == [project_id]


async def test_crops_include_effective_source_and_follow_main_lifecycle(client: AsyncClient):
    async with get_db() as conn:
        project_a = await _project(conn, "A")
        project_b = await _project(conn, "B")
        main_id = await _image(conn, project_a, "main", main=True)
        other_id = await _image(conn, project_a, "other")
        small_id = await _crop(conn, project_a, "small", None)
        large_id = await _crop(conn, project_a, "large", other_id)
        await _crop(conn, project_b, "small", None)
        await conn.commit()

    items = {
        item["project_id"]: item for item in (await client.get("/api/gallery")).json()["items"]
    }
    assert items[project_a]["crops"] == {
        "small": {"id": small_id, "image_id": main_id},
        "large": {"id": large_id, "image_id": other_id},
    }
    assert items[project_b]["crops"] == {}

    changed = await client.post(f"/api/projects/{project_a}/images/{other_id}/main")
    assert changed.status_code == 200, changed.text
    item = next(
        item
        for item in (await client.get("/api/gallery")).json()["items"]
        if item["project_id"] == project_a
    )
    assert item["main_image_id"] == other_id
    assert item["crops"] == {"large": {"id": large_id, "image_id": other_id}}


async def test_missing_crop_file_is_omitted_after_main_change(client: AsyncClient):
    async with get_db() as conn:
        project_id = await _project(conn, "Missing crop")
        old_main_id = await _image(conn, project_id, "old-main", main=True)
        new_main_id = await _image(conn, project_id, "new-main")
        crop_id = await _crop(conn, project_id, "medium", old_main_id)
        root = get_projects_root()
        assert root is not None
        crop_path(root / str(project_id), "medium", crop_id).unlink()
        await conn.commit()

    changed = await client.post(f"/api/projects/{project_id}/images/{new_main_id}/main")
    assert changed.status_code == 200, changed.text
    item = next(
        item
        for item in (await client.get("/api/gallery")).json()["items"]
        if item["project_id"] == project_id
    )
    assert item["main_image_id"] == new_main_id
    assert item["crops"] == {}


async def test_rigs_union_declared_and_session(client: AsyncClient):
    async with get_db() as conn:
        project_id = await _project(conn, "Two rigs")
        rig_ids = []
        for index, active in enumerate((1, 0)):
            cursor = await conn.execute(
                """
                INSERT INTO rig (
                    name, telescope_configuration_id, camera_id, active, sort_order
                ) VALUES (?, 1, 1, ?, ?)
                """,
                (f"R{index + 1}", active, index),
            )
            rig_ids.append(int(cursor.lastrowid))
        await conn.execute(
            "INSERT INTO project_rig (project_id, rig_id) VALUES (?, ?)",
            (project_id, rig_ids[0]),
        )
        await conn.execute(
            """
            INSERT INTO project_session (
                project_id, rig_id, line_name, exposure_seconds, num_subs
            ) VALUES (?, ?, 'Ha', 300, 1)
            """,
            (project_id, rig_ids[1]),
        )
        await conn.commit()
    body = (await client.get("/api/gallery", params={"rig": str(rig_ids[1])})).json()
    assert body["items"][0]["rigs"] == [
        {"id": rig_ids[0], "name": "R1"},
        {"id": rig_ids[1], "name": "R2"},
    ]


async def test_integration_matches_project_page(client: AsyncClient):
    async with get_db() as conn:
        project_id = await _project(conn, "Integration")
        empty_id = await _project(conn, "Empty")
        for exposure, subs, source in (
            (300, 2, "manual"),
            (120, 10, "manual"),
            (60, 5, "auto"),
            (600, 4, "manual"),
        ):
            await conn.execute(
                """
                INSERT INTO project_session (
                    project_id, line_name, exposure_seconds, num_subs, source
                ) VALUES (?, 'Ha', ?, ?, ?)
                """,
                (project_id, exposure, subs, source),
            )
        await conn.commit()
    gallery = (await client.get("/api/gallery", params={"sort": "name", "desc": False})).json()
    by_id = {item["project_id"]: item for item in gallery["items"]}
    integration = (await client.get(f"/api/projects/{project_id}/integration")).json()
    assert by_id[project_id]["integration_minutes"] == 75.0
    assert by_id[project_id]["integration_minutes"] == integration["total_actual_minutes"]
    assert by_id[empty_id]["integration_minutes"] == 0.0


async def test_search_examples(client: AsyncClient):
    async with get_db() as conn:
        dsos = await make_library_dsos(conn)
        projects = {}
        for key in ("m1", "m13", "m31", "ngc6992"):
            projects[key] = await _project(conn, key)
            await _target(conn, projects[key], dsos.ids[key])
        rosette = await _project(conn, "Rosette, two seasons")
        await conn.execute(
            "UPDATE project SET description = 'description-only-word' WHERE id = ?", (rosette,)
        )
        await conn.commit()
    expectations = {
        "M1": {projects["m1"], projects["m13"]},
        "m 31": {projects["m31"]},
        "NGC224": {projects["m31"]},
        "andromeda": {projects["m31"]},
        "veil": {projects["ngc6992"]},
        "rosette": {rosette},
        "description-only-word": set(),
    }
    for query, expected in expectations.items():
        body = (await client.get("/api/gallery", params={"q": query})).json()
        assert {item["project_id"] for item in body["items"]} == expected


async def test_search_images(client: AsyncClient):
    async with get_db() as conn:
        dsos = await make_library_dsos(conn)
        project_a = await _project(conn, "A")
        project_b = await _project(conn, "B")
        project_c = await _project(conn, "C")
        await _target(conn, project_a, dsos.ids["m31"])
        await _target(conn, project_b, dsos.ids["m31"])
        await _target(conn, project_b, dsos.ids["m32"])
        await _solve(conn, project_a, [dsos.ids["m31"], dsos.ids["m32"], dsos.ids["ic1795"]])
        await conn.commit()

    plain = (await client.get("/api/gallery", params={"q": "M 32"})).json()["items"]
    assert [item["project_id"] for item in plain] == [project_b]
    searched = (
        await client.get("/api/gallery", params={"q": "M 32", "search_images": True})
    ).json()["items"]
    assert {item["project_id"]: item["found_in_image"] for item in searched} == {
        project_a: ["M 32"],
        project_b: [],
    }
    fish = (
        await client.get("/api/gallery", params={"q": "fish head", "search_images": True})
    ).json()["items"]
    assert [(item["project_id"], item["found_in_image"]) for item in fish] == [
        (project_a, ["Fish Head Nebula"])
    ]
    main = (await client.get("/api/gallery", params={"q": "M 31", "search_images": True})).json()[
        "items"
    ]
    assert {item["project_id"]: item["found_in_image"] for item in main} == {
        project_a: [],
        project_b: [],
    }
    assert project_c not in {item["project_id"] for item in searched}


async def test_also_known_as_lists_designations_then_names(client: AsyncClient):
    async with get_db() as conn:
        dsos = await make_library_dsos(conn)
        project_id = await _project(conn, "Orion")
        await _target(conn, project_id, dsos.ids["m42"])
        await conn.execute(
            """
            INSERT INTO dso_designation
                (dso_id, catalog, identifier, display_form, search_key, is_primary)
            VALUES (?, 'ngc', '1976', 'NGC 1976', 'ngc1976', 0)
            """,
            (dsos.ids["m42"],),
        )
        await conn.commit()
    target = (await client.get("/api/gallery")).json()["items"][0]["targets"][0]
    assert target["also_known_as"] == ["M 42", "NGC 1976", "Great Orion Nebula"]


async def test_bad_date_is_422(client: AsyncClient):
    response = await client.get("/api/gallery", params={"imaged_from": "2025-02-30"})
    assert response.status_code == 422


async def test_bad_rig_is_422(client: AsyncClient):
    response = await client.get("/api/gallery", params={"rig": "not-a-number"})
    assert response.status_code == 422


async def test_from_after_to_is_422(client: AsyncClient):
    response = await client.get(
        "/api/gallery", params={"imaged_from": "2025-11-01", "imaged_to": "2025-10-01"}
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "From is after To"


async def test_library_counts(client: AsyncClient):
    async with get_db() as conn:
        dsos = await make_library_dsos(conn)
        summary = await populate_gallery_projects(conn, dsos.all_ids, n_projects=500)
        counts = await conn.execute(
            """
            SELECT MIN(n) AS minimum, MAX(n) AS maximum
            FROM (
                SELECT COUNT(*) AS n FROM project_session GROUP BY project_id
            )
            """
        )
        session_counts = await counts.fetchone()
    body = (await client.get("/api/gallery")).json()
    assert len(body["items"]) == summary.expected_visible
    assert {
        facet["code"]: facet["count"] for facet in body["facets"]["statuses"]
    } == summary.visible_by_status
    assert (session_counts["minimum"], session_counts["maximum"]) == (3, 10)


async def test_library_search_images(client: AsyncClient):
    async with get_db() as conn:
        dsos = await make_library_dsos(conn)
        summary = await populate_gallery_projects(conn, dsos.all_ids, n_projects=60)

    candidates = list(
        dict.fromkeys(
            dso_id
            for project_id in summary.solved_project_ids
            for dso_id in summary.solve_non_target_dsos[project_id]
        )
    )
    assert candidates

    chosen = None
    for dso_id in candidates:
        async with get_db() as conn:
            row = await (
                await conn.execute(
                    "SELECT primary_designation, common_name FROM dso WHERE id = ?",
                    (dso_id,),
                )
            ).fetchone()
        expected_projects = {
            project_id
            for project_id, non_targets in summary.solve_non_target_dsos.items()
            if dso_id in non_targets
        }
        params = {"q": row["primary_designation"], "include_retired": True}
        plain = (await client.get("/api/gallery", params=params)).json()["items"]
        if expected_projects.isdisjoint(item["project_id"] for item in plain):
            chosen = (row, expected_projects, params)
            break

    assert chosen is not None
    row, expected_projects, params = chosen
    preferred_name = row["common_name"] or row["primary_designation"]
    searched = (await client.get("/api/gallery", params={**params, "search_images": True})).json()[
        "items"
    ]
    by_project = {item["project_id"]: item for item in searched}
    assert expected_projects <= by_project.keys()
    for project_id in expected_projects:
        assert preferred_name in by_project[project_id]["found_in_image"]


async def test_load_designations_batches():
    async with get_db() as conn:
        dsos = await make_library_dsos(conn)
        source_id = (
            await (await conn.execute("SELECT id FROM dso_catalog_source LIMIT 1")).fetchone()
        )["id"]
        ids = []
        for index in range(600):
            cursor = await conn.execute(
                """
                INSERT INTO dso (
                    primary_designation, obj_type, source_catalog_id, source_row_hash, source_key
                ) VALUES (?, 'G', ?, ?, ?)
                """,
                (f"M {1000 + index}", source_id, f"batch-{index}", f"batch-{index}"),
            )
            dso_id = int(cursor.lastrowid)
            ids.append(dso_id)
            for catalog, offset in (("messier", 1000), ("ngc", 9000)):
                identifier = str(offset + index)
                await conn.execute(
                    """
                    INSERT INTO dso_designation (
                        dso_id, catalog, identifier, display_form, search_key, is_primary
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        dso_id,
                        catalog,
                        identifier,
                        f"{catalog} {identifier}",
                        f"{catalog}{identifier}",
                        catalog == "messier",
                    ),
                )
        loaded = await load_designations(conn, [*ids, ids[0]])
        assert len(loaded) == 600
        assert all(
            [item.catalog for item in loaded[dso_id]] == ["messier", "ngc"] for dso_id in ids
        )
        assert dsos.ids["m1"] not in loaded


async def test_library_total_ignores_filters(client: AsyncClient):
    async with get_db() as conn:
        await _project(conn, "Current")
        await _project(conn, "Retired", active=0)
        await conn.commit()
    body = (await client.get("/api/gallery", params={"catalog": "messier"})).json()
    assert body["items"] == []
    assert body["library_total"] == 2


async def test_only_retired_library(client: AsyncClient):
    async with get_db() as conn:
        await _project(conn, "Old 1", active=0)
        await _project(conn, "Old 2", active=0)
        await conn.commit()
    body = (await client.get("/api/gallery")).json()
    assert body["items"] == []
    assert body["library_total"] == 2
