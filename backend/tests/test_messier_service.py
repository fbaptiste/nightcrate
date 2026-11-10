from datetime import date

import pytest

from nightcrate.services.messier import (
    Candidate,
    PictureField,
    SolveFacts,
    crop_field,
    main_image_field,
    never_rises,
    order_candidates,
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


def _solve(**values) -> SolveFacts:
    return SolveFacts(
        image_path=values.get("image_path", "/solve.fits"),
        image_width=values.get("image_width", 5845),
        image_height=values.get("image_height", 3646),
        fov_width_arcmin=values.get("fov_width_arcmin", 36.7),
        fov_height_arcmin=values.get("fov_height_arcmin", 22.9),
    )


def test_main_image_field_same_file():
    field = main_image_field(_solve(), "/solve.fits", None)
    assert field == PictureField(width_deg=36.7 / 60, height_deg=22.9 / 60)


def test_main_image_field_matching_proportions():
    assert main_image_field(_solve(), "/main.jpg", (800, 499)) is not None

    square = _solve(image_width=1000, image_height=1000)
    assert main_image_field(square, "/main.jpg", (1004, 1000)) is not None
    assert main_image_field(square, "/main.jpg", (1006, 1000)) is None


def test_main_image_field_other_proportions_is_none():
    assert main_image_field(_solve(), "/main.jpg", (800, 600)) is None


def test_main_image_field_without_solve_or_fov_is_none():
    assert main_image_field(None, "/main.jpg", (800, 499)) is None
    assert main_image_field(_solve(fov_width_arcmin=None), "/solve.fits", None) is None


def test_crop_field():
    result = crop_field(PictureField(width_deg=36.7 / 60, height_deg=22.9 / 60), 0.5, 0.6)
    assert result.width_deg == pytest.approx(0.3058333333, abs=1e-6)
    assert result.height_deg == pytest.approx(0.229, abs=1e-6)
    mat = crop_field(PictureField(width_deg=0.4, height_deg=0.4), 4 / 3, 1)
    assert mat.width_deg == pytest.approx(0.533333, abs=1e-6)
    assert mat.height_deg == pytest.approx(0.4, abs=1e-6)


def test_slot_state_all_four():
    no_image = [_candidate(1, image=False, dates=[], created_at="2026-01-01")]
    image = [_candidate(1, image=True, dates=[], created_at="2026-01-01")]
    assert slot_state(False, []) == "missing"
    assert slot_state(True, []) == "none"
    assert slot_state(True, no_image) == "project"
    assert slot_state(True, image) == "imaged"
