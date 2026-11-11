from datetime import date

import pytest

from nightcrate.services.messier import (
    Candidate,
    never_rises,
    order_candidates,
    rig_view_field_deg,
    slot_state,
)


def _candidate(
    project_id: int,
    *,
    image: bool,
    dates: list[date],
    created_at: str,
) -> Candidate:
    return Candidate(
        project_id=project_id,
        name=str(project_id),
        status="active",
        created_at=created_at,
        main_image_id=project_id if image else None,
        dates=dates,
    )


def test_never_rises_southern_examples():
    assert never_rises(-35.0, 58.0844) is True
    assert never_rises(-35.0, 55.7632) is False
    assert never_rises(-35.0, 54.3489) is False
    assert never_rises(33.45, -34.8) is False
    assert never_rises(90.0, -1.5) is True
    assert never_rises(90.0, -0.5) is False
    assert never_rises(-35.0, None) is False


def test_rig_view_field_fits_landscape_and_tall_rigs():
    assert rig_view_field_deg(2.80, 1.86) == pytest.approx(3.0435, abs=0.0001)
    assert rig_view_field_deg(41.2 / 60, 27.4 / 60) == pytest.approx(0.7464, abs=0.0001)
    assert rig_view_field_deg(1.0, 1.0) == pytest.approx(1.4493, abs=0.0001)


def test_rig_view_field_supported_range_is_inclusive():
    assert rig_view_field_deg(0.0276, 0.01) is None
    assert rig_view_field_deg(0.046, 0.01) == pytest.approx(0.05)
    assert rig_view_field_deg(27.6, 1.0) == pytest.approx(30.0)
    assert rig_view_field_deg(36.8, 1.0) is None


def test_order_candidates_image_first_then_dates_then_created_then_id():
    items = [
        _candidate(1, image=True, dates=[date(2025, 3, 1)], created_at="2025-01-01"),
        _candidate(2, image=False, dates=[date(2026, 1, 1)], created_at="2025-01-01"),
        _candidate(3, image=True, dates=[], created_at="2026-02-01"),
        _candidate(4, image=True, dates=[], created_at="2026-02-01"),
    ]
    assert [item.project_id for item in order_candidates(items, image_first=True)] == [1, 4, 3, 2]
    assert [item.project_id for item in order_candidates(items, image_first=False)] == [2, 1, 4, 3]


def test_order_candidates_created_at_seconds_and_invalid_last():
    items = [
        _candidate(1, image=False, dates=[], created_at="2026-01-01 12:00:02"),
        _candidate(2, image=False, dates=[], created_at="2026-01-01 12:00:01"),
        _candidate(3, image=False, dates=[], created_at="not-a-date"),
    ]
    assert [item.project_id for item in order_candidates(items, image_first=False)] == [1, 2, 3]


def test_slot_state_all_four():
    no_image = [_candidate(1, image=False, dates=[], created_at="2026-01-01")]
    image = [_candidate(1, image=True, dates=[], created_at="2026-01-01")]
    assert slot_state(False, []) == "missing"
    assert slot_state(True, []) == "none"
    assert slot_state(True, no_image) == "project"
    assert slot_state(True, image) == "imaged"
