"""Tests for project target facts and plate-solved object loaders."""

from __future__ import annotations

from typing import Any

from nightcrate.api.gallery import load_project_records
from nightcrate.api.object_facts_db import load_other_objects, load_target_facts
from nightcrate.db.session import get_db
from nightcrate.services.object_facts import catalog_numbers
from tests.gallery_library import make_library_dsos
from tests.test_gallery_api import _project, _solve, _target


def test_catalog_numbers_prefers_messier_then_ngc():
    assert catalog_numbers(
        "Pinwheel Galaxy",
        "M 101",
        [("messier", "M 101"), ("ngc", "NGC 5457"), ("ugc", "UGC 8981")],
    ) == ["M 101", "NGC 5457"]


def test_catalog_numbers_drops_the_name():
    assert catalog_numbers(
        "M 65",
        "M 65",
        [("messier", "M 65"), ("ngc", "NGC 3623")],
    ) == ["NGC 3623"]


def test_catalog_numbers_falls_back_to_primary():
    assert catalog_numbers("Heart Nebula", "IC 1805", [("ic", "IC 1805")]) == ["IC 1805"]


async def _one_target_facts(*, distance_pc: float | None, method: str | None):
    async with get_db() as conn:
        dsos = await make_library_dsos(conn)
        project_id = await _project(conn, "Target facts")
        dso_id = dsos.ids["m31"]
        await _target(conn, project_id, dso_id)
        await conn.execute(
            "UPDATE dso SET distance_pc = ?, distance_method = ? WHERE id = ?",
            (distance_pc, method, dso_id),
        )
        await conn.execute(
            """
            INSERT INTO dso_external_ref (
                dso_id, provider, language, identifier, url
            ) VALUES (?, 'wikipedia', 'en', 'Andromeda_Galaxy',
                      'https://en.wikipedia.org/wiki/Andromeda_Galaxy')
            """,
            (dso_id,),
        )
        await conn.commit()
        loaded = await load_target_facts(conn, [project_id])
    return loaded[project_id][0].target


async def test_target_facts_include_distance_and_wikipedia():
    target = await _one_target_facts(distance_pc=6_950_000, method="50mgc")
    assert target.distance_pc == 6_950_000
    assert target.distance_estimated is False
    assert target.wikipedia_url == "https://en.wikipedia.org/wiki/Andromeda_Galaxy"


async def test_redshift_distance_is_estimated():
    target = await _one_target_facts(distance_pc=75_000_000, method="redshift")
    assert target.distance_estimated is True


async def test_target_without_distance_has_none():
    target = await _one_target_facts(distance_pc=None, method=None)
    assert target.distance_pc is None
    assert target.distance_estimated is False


async def test_other_objects_exclude_targets_and_sort():
    async with get_db() as conn:
        dsos = await make_library_dsos(conn)
        project_id = await _project(conn, "Other objects")
        target_id = dsos.ids["m31"]
        near_id = dsos.ids["m32"]
        far_id = dsos.ids["m42"]
        unknown_id = dsos.ids["m13"]
        await _target(conn, project_id, target_id)
        await _solve(conn, project_id, [target_id, far_id, unknown_id, near_id])
        await conn.execute(
            "UPDATE dso SET distance_pc = 10000000, distance_method = 'curated' WHERE id = ?",
            (near_id,),
        )
        await conn.execute(
            "UPDATE dso SET distance_pc = 300000000, distance_method = 'redshift' WHERE id = ?",
            (far_id,),
        )
        await conn.commit()

        objects = (await load_other_objects(conn, [project_id]))[project_id]

    assert [item.designation for item in objects] == ["M 32", "M 42", "M 13"]
    assert all(item.dso_id != target_id for item in objects)
    assert objects[1].distance_estimated is True
    assert objects[2].distance_pc is None


async def test_other_objects_empty_without_solve():
    async with get_db() as conn:
        project_id = await _project(conn, "Unsolved")
        await conn.commit()
        assert await load_other_objects(conn, [project_id]) == {}


class _CountingConnection:
    def __init__(self, conn: Any):
        self._conn = conn
        self.statements: list[str] = []

    async def execute(self, sql: str, parameters: Any = None):
        self.statements.append(sql)
        if parameters is None:
            return await self._conn.execute(sql)
        return await self._conn.execute(sql, parameters)

    def __getattr__(self, name: str):
        return getattr(self._conn, name)


async def test_records_without_object_facts_skip_the_queries():
    async with get_db() as conn:
        dsos = await make_library_dsos(conn)
        project_id = await _project(conn, "Default loader")
        await _target(conn, project_id, dsos.ids["m31"])
        await conn.commit()
        counted = _CountingConnection(conn)

        records = await load_project_records(counted)

    assert len(records) == 1
    assert len(counted.statements) == 9
    assert all("project_dso" not in sql for sql in counted.statements)
    assert all("dso_external_ref" not in sql for sql in counted.statements)
