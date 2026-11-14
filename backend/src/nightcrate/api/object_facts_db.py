"""Batched database loaders for project target and plate-solve facts."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from typing import Any

from nightcrate.api._common import load_designations, load_other_names
from nightcrate.services.dso_type_groups import group_for_raw_type
from nightcrate.services.gallery import GalleryTarget, TargetFacts
from nightcrate.services.object_facts import OtherObject, OtherObjectDistance, catalog_numbers

_ID_QUERY_BATCH_SIZE = 500


def _id_batches(project_ids: list[int] | None) -> Iterator[list[int] | None]:
    if project_ids is None:
        yield None
        return
    unique_ids = list(dict.fromkeys(project_ids))
    for start in range(0, len(unique_ids), _ID_QUERY_BATCH_SIZE):
        yield unique_ids[start : start + _ID_QUERY_BATCH_SIZE]


def _where_ids(column: str, batch: list[int] | None) -> tuple[str, list[int]]:
    if batch is None:
        return "", []
    placeholders = ",".join("?" * len(batch))
    return f"WHERE {column} IN ({placeholders})", batch


def _other_object_where(
    batch: list[int] | None,
    *,
    require_distance: bool,
) -> tuple[str, list[int]]:
    conditions: list[str] = []
    params: list[int] = []
    if batch is not None:
        placeholders = ",".join("?" * len(batch))
        conditions.append(f"ps.project_id IN ({placeholders})")
        params.extend(batch)
    if require_distance:
        conditions.append("d.distance_pc IS NOT NULL")
    conditions.append(
        """NOT EXISTS (
            SELECT 1
            FROM project_target pt
            WHERE pt.project_id = ps.project_id AND pt.dso_id = d.id
        )"""
    )
    return f"WHERE {' AND '.join(conditions)}", params


def _alternate_names(name: str, designations: list[Any], other_names: list[str]) -> list[str]:
    result: list[str] = []
    seen = {name.casefold()}
    for value in [*(designation.display_form for designation in designations), *other_names]:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


async def load_target_facts(
    conn: Any,
    project_ids: list[int] | None = None,
    *,
    with_facts: bool = True,
) -> dict[int, list[TargetFacts]]:
    """Load ordered project targets with their catalog and reference facts."""
    if project_ids == []:
        return {}

    target_rows = []
    for batch in _id_batches(project_ids):
        where, params = _where_ids("pt.project_id", batch)
        if with_facts:
            cursor = await conn.execute(
                f"""
                SELECT pt.project_id, pt.dso_id, d.primary_designation, d.common_name,
                       d.obj_type, d.constellation, d.distance_pc, d.distance_method,
                       (
                           SELECT ref.url
                           FROM dso_external_ref ref
                           WHERE ref.dso_id = d.id
                             AND ref.provider = 'wikipedia'
                             AND ref.language = 'en'
                           ORDER BY ref.id
                           LIMIT 1
                       ) AS wikipedia_url
                FROM project_target pt
                JOIN dso d ON d.id = pt.dso_id
                {where}
                ORDER BY pt.project_id, pt.created_at, pt.id
                """,  # noqa: S608  # nosec B608 - placeholders built only from ?
                params,
            )
        else:
            cursor = await conn.execute(
                f"""
                SELECT pt.project_id, pt.dso_id, d.primary_designation, d.common_name,
                       d.obj_type, d.constellation
                FROM project_target pt
                JOIN dso d ON d.id = pt.dso_id
                {where}
                ORDER BY pt.project_id, pt.created_at, pt.id
                """,  # noqa: S608  # nosec B608 - placeholders built only from ?
                params,
            )
        target_rows.extend(await cursor.fetchall())

    dso_ids = list(dict.fromkeys(int(row["dso_id"]) for row in target_rows))
    designations = await load_designations(conn, dso_ids)
    other_names = await load_other_names(conn, dso_ids)

    group_catalogs: dict[int, set[str]] = defaultdict(set)
    for batch in _id_batches(project_ids):
        where, params = _where_ids("pt.project_id", batch)
        group_cursor = await conn.execute(
            f"""
            SELECT DISTINCT pt.dso_id, g.catalog
            FROM project_target pt
            JOIN dso_group_member gm ON gm.dso_id = pt.dso_id
            JOIN dso_group g ON g.id = gm.group_id
            {where}
            """,  # noqa: S608  # nosec B608 - placeholders built only from ?
            params,
        )
        for row in await group_cursor.fetchall():
            group_catalogs[int(row["dso_id"])].add(str(row["catalog"]))

    targets_by_project: dict[int, list[TargetFacts]] = defaultdict(list)
    for row in target_rows:
        dso_id = int(row["dso_id"])
        dso_designations = designations.get(dso_id, [])
        preferred_name = row["common_name"] or row["primary_designation"]
        catalogs = {designation.catalog for designation in dso_designations}
        catalogs.update(group_catalogs.get(dso_id, set()))
        if with_facts:
            designation_pairs = [
                (designation.catalog, designation.display_form) for designation in dso_designations
            ]
            target = GalleryTarget(
                dso_id=dso_id,
                name=preferred_name,
                also_known_as=_alternate_names(
                    preferred_name,
                    dso_designations,
                    other_names.get(dso_id, []),
                ),
                designation=row["primary_designation"],
                catalog_numbers=catalog_numbers(
                    preferred_name,
                    row["primary_designation"],
                    designation_pairs,
                ),
                obj_type=row["obj_type"],
                constellation=row["constellation"],
                distance_pc=row["distance_pc"],
                distance_estimated=row["distance_method"] == "redshift",
                wikipedia_url=row["wikipedia_url"],
            )
        else:
            target = GalleryTarget(
                dso_id=dso_id,
                name=preferred_name,
                also_known_as=_alternate_names(
                    preferred_name,
                    dso_designations,
                    other_names.get(dso_id, []),
                ),
            )
        targets_by_project[int(row["project_id"])].append(
            TargetFacts(
                target=target,
                catalogs=frozenset(catalogs),
                type_group=group_for_raw_type(row["obj_type"]),
                constellation=row["constellation"],
            )
        )
    return dict(targets_by_project)


async def load_other_objects(
    conn: Any,
    project_ids: list[int],
) -> dict[int, list[OtherObject]]:
    """Load non-target objects in project solves, nearest first."""
    result: dict[int, list[OtherObject]] = defaultdict(list)
    for batch in _id_batches(project_ids):
        if batch is None:
            continue
        where, params = _other_object_where(batch, require_distance=False)
        cursor = await conn.execute(
            f"""
            SELECT ps.project_id, d.id AS dso_id, d.primary_designation,
                   d.common_name, d.obj_type, d.constellation,
                   d.distance_pc, d.distance_method,
                   (
                       SELECT ref.url
                       FROM dso_external_ref ref
                       WHERE ref.dso_id = d.id
                         AND ref.provider = 'wikipedia'
                         AND ref.language = 'en'
                       ORDER BY ref.id
                       LIMIT 1
                   ) AS wikipedia_url
            FROM project_solve ps
            JOIN project_dso pd ON pd.solve_id = ps.id
            JOIN dso d ON d.id = pd.dso_id
            {where}
            ORDER BY ps.project_id, d.distance_pc IS NULL, d.distance_pc,
                     d.primary_designation COLLATE NOCASE, d.id
            """,  # noqa: S608  # nosec B608 - placeholders built only from ?
            params,
        )
        for row in await cursor.fetchall():
            result[int(row["project_id"])].append(
                OtherObject(
                    dso_id=int(row["dso_id"]),
                    name=row["common_name"] or row["primary_designation"],
                    designation=row["primary_designation"],
                    obj_type=row["obj_type"],
                    constellation=row["constellation"],
                    distance_pc=row["distance_pc"],
                    distance_estimated=row["distance_method"] == "redshift",
                    wikipedia_url=row["wikipedia_url"],
                )
            )
    return dict(result)


async def load_other_distances(
    conn: Any,
    project_ids: list[int] | None = None,
) -> dict[int, list[OtherObjectDistance]]:
    """Load only the distances needed to draw Gallery solve-object markers."""
    if project_ids == []:
        return {}
    result: dict[int, list[OtherObjectDistance]] = defaultdict(list)
    for batch in _id_batches(project_ids):
        where, params = _other_object_where(batch, require_distance=True)
        cursor = await conn.execute(
            f"""
            SELECT ps.project_id, d.id AS dso_id, d.distance_pc, d.distance_method
            FROM project_solve ps
            JOIN project_dso pd ON pd.solve_id = ps.id
            JOIN dso d ON d.id = pd.dso_id
            {where}
            ORDER BY ps.project_id, d.distance_pc, d.primary_designation COLLATE NOCASE, d.id
            """,  # noqa: S608  # nosec B608 - placeholders built only from ?
            params,
        )
        for row in await cursor.fetchall():
            result[int(row["project_id"])].append(
                OtherObjectDistance(
                    dso_id=int(row["dso_id"]),
                    distance_pc=float(row["distance_pc"]),
                    distance_estimated=row["distance_method"] == "redshift",
                )
            )
    return dict(result)
