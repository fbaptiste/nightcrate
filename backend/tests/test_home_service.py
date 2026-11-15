"""Pure Home aggregation boundary and ranking tests."""

from datetime import date

import pytest

from nightcrate.services.home import (
    LocationRank,
    RigRank,
    month_keys,
    rank_forecast_locations,
    rank_locations,
    rank_rigs,
    stage_of,
    summarise_year,
    window_start,
)


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        (date(2026, 11, 14), date(2025, 12, 1)),
        (date(2026, 1, 10), date(2025, 2, 1)),
        (date(2026, 12, 31), date(2026, 1, 1)),
        (date(2024, 2, 29), date(2023, 3, 1)),
    ],
)
def test_window_start(today: date, expected: date):
    assert window_start(today) == expected
    assert len(month_keys(today)) == 12


def test_summarise_year_boundaries_best_night_and_images():
    today = date(2026, 11, 14)
    summary = summarise_year(
        [
            (1, "Alpha", date(2025, 11, 30), 999),
            (1, "Alpha", date(2025, 12, 1), 60),
            (1, "Alpha", date(2026, 9, 30), 120),
            (2, "Beta", date(2026, 9, 30), 180),
            (2, "Beta", today, 30),
            (3, "Tomorrow", date(2026, 11, 15), 999),
        ],
        [(date(2025, 12, 1),), (today,), (date(2026, 11, 15),)],
        today,
    )
    assert summary.since == date(2025, 12, 1)
    assert summary.minutes == 390
    assert summary.nights == 3
    assert summary.new_pictures == 2
    assert summary.best_night is not None
    assert summary.best_night.date == date(2026, 9, 30)
    assert summary.best_night.minutes == 300
    assert summary.best_night.project_name == "Beta"
    assert summary.best_night.other_projects == 1
    assert [month.month for month in summary.months] == month_keys(today)
    assert next(month.minutes for month in summary.months if month.month == "2026-09") == 300


def test_summarise_year_empty_and_best_night_ties_choose_later_date_then_name():
    today = date(2026, 11, 14)
    empty = summarise_year([], [], today)
    assert empty.minutes == empty.nights == empty.new_pictures == 0
    assert empty.best_night is None
    assert all(month.minutes == 0 for month in empty.months)

    tied = summarise_year(
        [
            (2, "Zulu", date(2026, 1, 1), 60),
            (3, "Beta", date(2026, 2, 1), 30),
            (1, "Alpha", date(2026, 2, 1), 30),
        ],
        [],
        today,
    )
    assert tied.best_night is not None
    assert tied.best_night.date == date(2026, 2, 1)
    assert tied.best_night.project_name == "Alpha"


def test_forecast_location_ranking_rules_and_caps():
    locations = [(1, "Default", True), *[(i, f"Used {i}", False) for i in range(2, 7)]]
    ranked = rank_forecast_locations(locations, {2: 1, 3: 5, 4: 3, 5: 2, 6: 4})
    assert [item.location_id for item in ranked] == [1, 3, 6, 4]
    assert ranked[0].note == "default"
    assert ranked[1].note == "used"
    assert rank_forecast_locations([(2, "B", False), (1, "A", False)], {})[0].name == "A"
    assert rank_forecast_locations([], {}) == []


def test_spare_forecast_rows_go_to_other_locations_by_name():
    """A location no active project uses still gets a spare row (Fred, 2026-11-14)."""
    locations = [
        (1, "Backyard", True),
        (2, "Remote site", False),
        (3, "Beta", False),
        (4, "alpha", False),
        (5, "Used", False),
    ]
    ranked = rank_forecast_locations(locations, {5: 2})
    assert [item.location_id for item in ranked] == [1, 5, 4, 3]
    assert [item.note for item in ranked] == ["default", "used", None, None]
    assert [item.active_projects for item in ranked] == [0, 2, 0, 0]

    default_and_unused = rank_forecast_locations(locations[:2], {1: 3})
    assert [(item.name, item.note) for item in default_and_unused] == [
        ("Backyard", "default"),
        ("Remote site", None),
    ]

    no_default = rank_forecast_locations([(1, "Zed", False), (2, "Alpha", False)], {1: 2})
    assert [(item.name, item.note) for item in no_default] == [("Zed", "used"), ("Alpha", None)]


def test_stage_and_panel_ranking():
    assert stage_of("active", 0) == "not_started"
    assert stage_of("active", 0.1 / 60) == "capturing"
    assert stage_of("ready_to_process", 0) == "ready_to_process"
    rigs = [
        RigRank(1, "B", 2, 60, 1, None, 0),
        RigRank(2, "A", 1, 60, 1, None, 0),
    ]
    assert [rig.rig_id for rig in rank_rigs(rigs)] == [2, 1]
    locations = [
        LocationRank(1, "B", False, 120, 1, None, 0),
        LocationRank(2, "Default", True, 0, 0, None, 0),
    ]
    assert [location.location_id for location in rank_locations(locations)] == [2, 1]
