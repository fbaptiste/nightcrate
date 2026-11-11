"""Regression tests for live object membership in stored plate solves."""

from __future__ import annotations

import math

import numpy as np
import pytest

from nightcrate.api.dso import dso_search_clause
from nightcrate.api.object_search_db import load_solves
from nightcrate.db.session import get_db
from nightcrate.services.image_annotation_models import WcsParams
from nightcrate.services.image_annotations import build_wcs, project_dsos
from nightcrate.services.object_search import (
    SolveGeometry,
    marks_in_solve,
    objects_near,
    solve_reach,
)
from tests.gallery_library import make_library_dsos


def _solve(**updates) -> SolveGeometry:
    scale = 4.5 / 3600.0
    values = {
        "crval1": 0.2,
        "crval2": 10.0,
        "cd1_1": -scale,
        "cd1_2": 0.0,
        "cd2_1": 0.0,
        "cd2_2": -scale,
        "crpix1": 601.0,
        "crpix2": 451.0,
        "naxis1": 1200,
        "naxis2": 900,
    }
    values.update(updates)
    wcs = WcsParams(**values)
    return SolveGeometry(
        project_id=1,
        solve_id=2,
        wcs=wcs,
        image_width=wcs.naxis1,
        image_height=wcs.naxis2,
    )


def _dso(dso_id: int, ra: float, dec: float, size: float | None = None) -> dict:
    return {
        "id": dso_id,
        "primary_designation": f"Test {dso_id}",
        "obj_type": "G",
        "type_group": "Galaxy",
        "ra_deg": ra,
        "dec_deg": dec,
        "maj_axis_arcmin": size,
        "min_axis_arcmin": size,
        "position_angle_deg": 0.0,
        "common_name": None,
        "constellation": None,
    }


def test_centre_edges_and_extended_overlap():
    solve = _solve()
    wcs = build_wcs(solve.wcs)
    coords = [wcs.pixel_to_world(x, 450.0) for x in (600.0, 1198.0, 1202.0, 1266.0)]
    dsos = [
        _dso(1, coords[0].ra.deg, coords[0].dec.deg),
        _dso(2, coords[1].ra.deg, coords[1].dec.deg),
        _dso(3, coords[2].ra.deg, coords[2].dec.deg),
        _dso(4, coords[3].ra.deg, coords[3].dec.deg, 20.0),
    ]
    assert {item.id for item in marks_in_solve(solve, dsos)} == {1, 2, 4}


def test_ra_wrap_and_polar_fields_are_not_dropped():
    wrap = _solve(crval1=0.2)
    wrap_dsos = [_dso(1, 359.9, 10.0), _dso(2, 0.5, 10.0)]
    assert {item["id"] for item in objects_near(wrap, wrap_dsos)} == {1, 2}

    pole = _solve(crval1=10.0, crval2=89.5)
    pole_dsos = [_dso(3, 10.0, 89.6), _dso(4, 190.0, 89.6)]
    assert {item["id"] for item in objects_near(pole, pole_dsos)} == {3, 4}


def test_empty_object_list_has_no_nearby_objects():
    assert objects_near(_solve(), []) == []


def test_zero_second_cd_row_keeps_only_centre_object_without_size_margin():
    solve = _solve(cd2_1=0.0, cd2_2=0.0)
    centre = _dso(1, 0.2, 10.0)
    large_outside_point_bounds = _dso(2, 1.2, 10.0, 120.0)

    assert objects_near(solve, [centre, large_outside_point_bounds]) == [centre]


def test_mirror_keeps_membership_and_more_than_500_objects():
    normal = _solve()
    mirrored = _solve(cd1_1=4.5 / 3600.0)
    coords = build_wcs(normal.wcs).pixel_to_world(
        np.linspace(100, 1100, 600),
        np.linspace(100, 800, 600),
    )
    dsos = [_dso(index, coord.ra.deg, coord.dec.deg) for index, coord in enumerate(coords)]
    normal_ids = {item.id for item in marks_in_solve(normal, dsos)}
    mirrored_ids = {item.id for item in marks_in_solve(mirrored, dsos)}
    assert len(normal_ids) == 600
    assert mirrored_ids == normal_ids


def test_prefilter_is_a_superset_for_displaced_rotated_and_mirrored_solves():
    rng = np.random.default_rng(49)
    for index in range(200):
        scale = 4.5 / 3600.0
        angle = rng.uniform(0, 2 * math.pi)
        reflection = -1.0 if index % 2 else 1.0
        cosine = math.cos(angle)
        sine = math.sin(angle)
        solve = _solve(
            crval1=float(
                rng.choice([rng.uniform(0, 360), rng.uniform(0, 0.5), rng.uniform(359.5, 360)])
            ),
            crval2=float(rng.uniform(-89, 89)),
            cd1_1=-scale * cosine,
            cd1_2=reflection * scale * sine,
            cd2_1=-scale * sine,
            cd2_2=-reflection * scale * cosine,
            crpix1=float(rng.uniform(300, 900)),
            crpix2=float(rng.uniform(200, 700)),
        )
        wcs = build_wcs(solve.wcs)
        pixels = rng.uniform([-200, -200], [1400, 1100], size=(40, 2))
        coords = wcs.pixel_to_world(pixels[:, 0], pixels[:, 1])
        dsos = [
            _dso(i, coord.ra.deg, coord.dec.deg, float(rng.uniform(0, 60)))
            for i, coord in enumerate(coords)
        ]
        direct = {item.id for item in project_dsos(solve.wcs, dsos)}
        narrowed = {item.id for item in marks_in_solve(solve, dsos)}
        assert narrowed == direct


def test_large_object_overlapping_a_corner_survives_prefilter():
    solve = _solve()
    coordinate = build_wcs(solve.wcs).pixel_to_world(1310.0, 1010.0)
    dso = _dso(1, coordinate.ra.deg, coordinate.dec.deg, 18.0)
    assert [item.id for item in marks_in_solve(solve, [dso])] == [1]


def test_solve_reach_uses_displayed_centre_not_crval():
    solve = _solve(crpix1=300.0, crpix2=200.0)
    centre_ra, centre_dec, radius = solve_reach(solve)
    expected = build_wcs(solve.wcs).pixel_to_world(600.0, 450.0)
    assert centre_ra == pytest.approx(expected.ra.deg, abs=1e-8)
    assert centre_dec == pytest.approx(expected.dec.deg, abs=1e-8)
    assert radius > 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("M1", {"M 1"}),
        ("M 1", {"M 1"}),
        ("m1", {"M 1"}),
        ("NGC 36", set()),
        ("PGC 1430330", {"IC 2729"}),
        ("Hamburger", {"NGC 3628"}),
        ("Arp 244", {"NGC 8000", "IC 8001"}),
    ],
)
async def test_exact_designations_keep_name_and_group_matching(query, expected):
    async with get_db() as conn:
        await make_library_dsos(conn)
        clause, params = dso_search_clause(query, exact_designations=True)
        cursor = await conn.execute(
            f"SELECT primary_designation FROM dso d WHERE {clause}",  # noqa: S608
            params,
        )
        assert {row["primary_designation"] for row in await cursor.fetchall()} == expected


@pytest.mark.asyncio
async def test_load_solves_without_project_filter_returns_every_solve_in_project_order():
    async with get_db() as conn:
        project_ids = []
        for name in ("First", "Second"):
            cursor = await conn.execute("INSERT INTO project (name) VALUES (?)", (name,))
            project_ids.append(int(cursor.lastrowid))

        solve_ids = {}
        for project_id in reversed(project_ids):
            cursor = await conn.execute(
                """
                INSERT INTO project_solve (
                    project_id, image_path, image_width, image_height,
                    center_ra_deg, center_dec_deg,
                    cd1_1, cd1_2, cd2_1, cd2_2, crpix1, crpix2
                ) VALUES (?, '/synthetic/solve.fits', 100, 80, 10, 20,
                          -0.001, 0, 0, 0.001, 51, 41)
                """,
                (project_id,),
            )
            solve_ids[project_id] = int(cursor.lastrowid)

        solves = await load_solves(conn)

    assert [(solve.project_id, solve.solve_id) for solve in solves] == [
        (project_id, solve_ids[project_id]) for project_id in project_ids
    ]
