"""Regression tests for the midnight-meridian calendar date."""

import pytest

from nightcrate.services.astronomy import midnight_meridian_date


@pytest.mark.parametrize(
    ("ra_deg", "expected"),
    [
        (210.80, (4, 23)),
        (83.82, (12, 16)),
        (10.68, (10, 5)),
        (160.9, (2, 28)),
        (0.0, (9, 23)),
        (180.0, (3, 20)),
        (359.9, (9, 23)),
        (0.1, (9, 23)),
        (179.9, (3, 20)),
        (180.1, (3, 21)),
        (570.80, (4, 23)),
    ],
)
def test_midnight_meridian_date_2026(ra_deg: float, expected: tuple[int, int]):
    assert midnight_meridian_date(ra_deg, 2026) == expected


def test_midnight_meridian_date_rejects_non_finite_ra():
    with pytest.raises(ValueError):
        midnight_meridian_date(float("nan"), 2026)
