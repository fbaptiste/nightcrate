"""Unit tests for the pure gallery service."""

from datetime import date

from nightcrate.services.gallery import (
    GalleryCrop,
    GalleryMark,
    GalleryQuery,
    GallerySolveMarks,
    GalleryTarget,
    ProjectRecord,
    TargetFacts,
    build_gallery,
    imaging_runs,
    valid_session_date,
)


def _target(
    dso_id: int,
    *,
    catalogs: tuple[str, ...] = ("ngc",),
    type_group: str = "Galaxy",
    constellation: str = "And",
) -> TargetFacts:
    return TargetFacts(
        target=GalleryTarget(dso_id=dso_id, name=f"Target {dso_id}"),
        catalogs=frozenset(catalogs),
        type_group=type_group,
        constellation=constellation,
    )


def _record(record_id: int, name: str, **values) -> ProjectRecord:
    return ProjectRecord(id=record_id, name=name, status="active", **values)


def _build(records: list[ProjectRecord], query: GalleryQuery | None = None, **hits):
    return build_gallery(
        records,
        query or GalleryQuery(),
        target_search_hits=hits.get("target_search_hits"),
        image_search_hits=hits.get("image_search_hits"),
    )


def test_dates_ignore_invalid_text():
    values = [
        "2025-10-12",
        "2025-10-12T23:10:00",
        "2025-11-03",
        "spring 2024",
        "2025-02-30",
        "2025-W41-1",
        "20251012",
        "",
        None,
    ]
    dates = sorted({parsed for value in values if (parsed := valid_session_date(value))})
    result = _build([_record(1, "Dates", dates=dates)])
    assert [valid_session_date(value) for value in values] == [
        date(2025, 10, 12),
        date(2025, 10, 12),
        date(2025, 11, 3),
        None,
        None,
        None,
        None,
        None,
        None,
    ]
    assert result.items[0].first_date == "2025-10-12"
    assert result.items[0].last_date == "2025-11-03"
    assert result.items[0].nights == 2


def test_imaging_runs():
    dates = (
        [date(2025, 1, day) for day in (6, 8, 12)]
        + [date(2025, 2, day) for day in (3, 4, 10, 22)]
        + [date(2026, 1, day) for day in (14, 15, 18)]
    )
    assert [(run.start, run.end) for run in imaging_runs(dates)] == [
        ("2025-01", "2025-02"),
        ("2026-01", "2026-01"),
    ]
    assert [
        (run.start, run.end) for run in imaging_runs([date(2023, 12, 20), date(2024, 1, 3)])
    ] == [("2023-12", "2024-01")]
    assert imaging_runs([]) == []


def test_sort_latest_desc_and_asc_undated_last():
    records = [
        _record(1, "Beta", dates=[date(2025, 11, 3)]),
        _record(2, "Alpha", dates=[date(2025, 11, 3)]),
        _record(3, "Gamma", dates=[date(2025, 6, 1)]),
        _record(4, "Delta"),
    ]
    assert [item.name for item in _build(records).items] == ["Alpha", "Beta", "Gamma", "Delta"]
    result = _build(records, GalleryQuery(desc=False))
    assert [item.name for item in result.items] == ["Gamma", "Alpha", "Beta", "Delta"]


def test_sort_name_ties_by_id():
    records = [_record(3, "alpha"), _record(2, "Alpha"), _record(1, "Beta")]
    result = _build(records, GalleryQuery(sort="name", desc=False))
    assert [item.project_id for item in result.items] == [2, 3, 1]


def test_imaged_between_inclusive():
    records = [
        _record(1, "Start", dates=[date(2025, 10, 12)]),
        _record(2, "Late", dates=[date(2025, 11, 1)]),
        _record(3, "Undated"),
    ]
    query = GalleryQuery(date_from=date(2025, 10, 12), date_to=date(2025, 10, 31))
    assert [item.project_id for item in _build(records, query).items] == [1]
    query.include_undated = True
    assert {item.project_id for item in _build(records, query).items} == {1, 3}


def test_imaged_between_gap():
    record = _record(1, "Gap", dates=[date(2025, 10, 1), date(2025, 11, 15)])
    query = GalleryQuery(date_from=date(2025, 10, 12), date_to=date(2025, 10, 31))
    assert _build([record], query).items == []


def test_facet_counts_project_once():
    record = _record(1, "Two", targets=[_target(1), _target(2)])
    assert _build([record]).facets.catalogs[0].model_dump() == {"code": "ngc", "count": 1}


def test_catalog_type_constellation_filters_any_target():
    record = _record(
        1,
        "Mixed",
        targets=[
            _target(1),
            _target(2, catalogs=("messier",), type_group="Emission Nebula", constellation="Ori"),
        ],
    )
    query = GalleryQuery(catalogs=["messier"], type_groups=["Galaxy"], constellations=["Ori"])
    assert [item.project_id for item in _build([record], query).items] == [1]


def test_facets_exclude_own_dimension():
    records = [
        _record(1, "Active", targets=[_target(1)]),
        ProjectRecord(
            id=2, name="Complete", status="complete", targets=[_target(2, catalogs=("messier",))]
        ),
    ]
    facets = _build(records, GalleryQuery(statuses=["complete"])).facets
    assert {facet.code: facet.count for facet in facets.statuses} == {"active": 1, "complete": 1}
    assert [(facet.code, facet.count) for facet in facets.catalogs] == [("messier", 1)]


def test_facets_keep_selected_zero():
    result = _build([_record(1, "One", targets=[_target(1)])], GalleryQuery(catalogs=["messier"]))
    assert {facet.code: facet.count for facet in result.facets.catalogs} == {
        "messier": 0,
        "ngc": 1,
    }


def test_projects_without_main_image_listed():
    records = [_record(1, "One", targets=[_target(1)]), _record(2, "Two", targets=[_target(2)])]
    result = _build(records)
    assert [item.main_image_id for item in result.items] == [None, None]
    assert result.facets.catalogs[0].count == 2


def test_crops_pass_through_to_gallery_items():
    crops = {
        "small": GalleryCrop(id=11, image_id=21),
        "large": GalleryCrop(id=12, image_id=22),
    }
    result = _build([_record(1, "Framed", crops=crops)])
    assert result.items[0].crops == crops


def test_retired_hidden_unless_included():
    records = [_record(1, "Current"), _record(2, "Old", retired=True)]
    assert [item.project_id for item in _build(records).items] == [1]
    result = _build(records, GalleryQuery(include_retired=True))
    assert {item.project_id for item in result.items} == {1, 2}
    assert result.library_total == 2


def test_name_or_target_search():
    records = [_record(1, "Rosette seasons"), _record(2, "Other"), _record(3, "Nope")]
    query = GalleryQuery(q="rosette", search_images=True)
    result = _build(
        records,
        query,
        target_search_hits={2},
        image_search_hits={
            3: GallerySolveMarks(
                solve_id=7,
                width=100,
                height=100,
                pixel_scale_arcsec=1.0,
                marks=[
                    GalleryMark(
                        dso_id=9,
                        designation="Object",
                        pixel_x=50,
                        pixel_y=50,
                        inset_radius_px=150,
                        main_target=False,
                    )
                ],
            )
        },
    )
    assert {item.project_id for item in result.items} == {1, 2, 3}
    by_id = {item.project_id: item for item in result.items}
    assert by_id[1].match_main_target is False
    assert by_id[1].match_in_image is False
    assert by_id[2].match_main_target is True
    assert by_id[2].match_in_image is False
    assert by_id[3].match_main_target is False
    assert by_id[3].match_in_image is True
    assert by_id[3].solve is not None
    assert by_id[3].solve.marks[0].designation == "Object"
