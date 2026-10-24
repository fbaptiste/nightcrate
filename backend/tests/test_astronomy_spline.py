"""Tests for spline interpolation on dense astronomy altitude grids."""

from dataclasses import fields, is_dataclass
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pytest
from astropy.time import Time
from astropy.utils import iers

from nightcrate.services import astronomy


@pytest.fixture(autouse=True, scope="module")
def _app_iers_settings():
    """Match NightCrate's deterministic, offline astropy configuration."""
    with (
        iers.conf.set_temp("auto_download", False),
        iers.conf.set_temp("auto_max_age", None),
    ):
        yield


@pytest.fixture
def location():
    return astronomy._make_location(33.4484, -112.0740, 331.0)


@pytest.fixture
def synthetic_altitude_fn():
    calls: list[Time] = []

    def altitude_fn(times: Time, _location) -> np.ndarray:
        calls.append(times)
        return 60 * np.sin(2 * np.pi * (times.jd - times.jd[0]))

    altitude_fn.calls = calls
    return altitude_fn


def _grid(hours: int, n_samples: int) -> Time:
    start = datetime(2026, 10, 23, tzinfo=UTC)
    return astronomy._make_time_grid(start, start + timedelta(hours=hours), n_samples)


def _node_indices(n_samples: int, node_every: int = 10) -> np.ndarray:
    return np.unique(np.append(np.arange(0, n_samples, node_every), n_samples - 1))


@pytest.mark.parametrize(
    ("times", "expected_node_count"),
    [
        pytest.param(_grid(24, 1440), 145, id="sun-grid"),
        pytest.param(_grid(48, 2881), 289, id="moon-grid"),
        pytest.param(_grid(24, 1445), 146, id="non-multiple"),
    ],
)
def test_spline_nodes_include_last_sample(
    times: Time,
    expected_node_count: int,
    location,
    synthetic_altitude_fn,
):
    astronomy._spline_altitudes(synthetic_altitude_fn, times, location)

    assert len(synthetic_altitude_fn.calls) == 1
    requested = synthetic_altitude_fn.calls[0]
    assert len(requested) == expected_node_count
    assert requested[0].jd == pytest.approx(times[0].jd)
    assert requested[-1].jd == pytest.approx(times[-1].jd)
    assert np.all(np.diff(requested.jd) > 0)


def test_spline_matches_exact_at_nodes(location, synthetic_altitude_fn):
    times = _grid(24, 1440)
    interpolated = astronomy._spline_altitudes(synthetic_altitude_fn, times, location)
    nodes = _node_indices(len(times))
    exact = 60 * np.sin(2 * np.pi * (times.jd - times.jd[0]))

    np.testing.assert_allclose(interpolated[nodes], exact[nodes], atol=1e-12, rtol=0)


def test_spline_error_bound_smooth_curve(location, synthetic_altitude_fn):
    times = _grid(24, 1440)
    interpolated = astronomy._spline_altitudes(synthetic_altitude_fn, times, location)
    exact = 60 * np.sin(2 * np.pi * (times.jd - times.jd[0]))

    assert np.max(np.abs(interpolated - exact)) < 1e-5


@pytest.mark.parametrize("n_samples", [21, 2, 1])
def test_spline_short_grid_falls_back_to_exact(
    n_samples: int,
    location,
    synthetic_altitude_fn,
):
    times = _grid(1, n_samples)
    interpolated = astronomy._spline_altitudes(synthetic_altitude_fn, times, location)
    exact = 60 * np.sin(2 * np.pi * (times.jd - times.jd[0]))

    assert len(synthetic_altitude_fn.calls) == 1
    assert len(synthetic_altitude_fn.calls[0]) == n_samples
    np.testing.assert_array_equal(interpolated, exact)


def test_spline_non_minute_spacing(location, synthetic_altitude_fn):
    times = _grid(25, 1440)
    interpolated = astronomy._spline_altitudes(synthetic_altitude_fn, times, location)
    exact = 60 * np.sin(2 * np.pi * (times.jd - times.jd[0]))
    requested = synthetic_altitude_fn.calls[0]

    assert np.max(np.abs(interpolated - exact)) < 1e-5
    assert requested[-1].jd == pytest.approx(times[-1].jd)


def _compute_exact(monkeypatch, *args):
    with monkeypatch.context() as exact_patch:
        exact_patch.setattr(
            astronomy,
            "_spline_altitudes",
            lambda fn, times, location, node_every=10: fn(times, location),
        )
        return astronomy.compute_night_summary(*args)


def _assert_equivalent(exact, fast, path: str = "summary") -> None:
    if isinstance(exact, datetime):
        assert isinstance(fast, datetime), path
        assert abs(exact - fast) <= timedelta(seconds=1), path
        return
    if is_dataclass(exact):
        assert type(fast) is type(exact), path
        for field in fields(exact):
            _assert_equivalent(
                getattr(exact, field.name),
                getattr(fast, field.name),
                f"{path}.{field.name}",
            )
        return
    if isinstance(exact, dict):
        assert fast.keys() == exact.keys(), path
        for key in exact:
            _assert_equivalent(exact[key], fast[key], f"{path}[{key!r}]")
        return
    if isinstance(exact, (list, tuple)):
        assert type(fast) is type(exact), path
        assert len(fast) == len(exact), path
        for index, (exact_item, fast_item) in enumerate(zip(exact, fast, strict=True)):
            _assert_equivalent(exact_item, fast_item, f"{path}[{index}]")
        return
    assert fast == exact, path


def test_night_summary_exact_evaluation_counts(monkeypatch):
    sun_call_sizes: list[int] = []
    moon_call_sizes: list[int] = []
    original_sun_altitudes = astronomy._sun_altitudes
    original_moon_altitudes = astronomy._moon_altitudes

    def recording_sun_altitudes(times, location):
        sun_call_sizes.append(len(times))
        return original_sun_altitudes(times, location)

    def recording_moon_altitudes(times, location):
        moon_call_sizes.append(len(times))
        return original_moon_altitudes(times, location)

    monkeypatch.setattr(astronomy, "_sun_altitudes", recording_sun_altitudes)
    monkeypatch.setattr(astronomy, "_moon_altitudes", recording_moon_altitudes)

    astronomy.compute_night_summary(
        33.4484,
        -112.0740,
        331.0,
        date(2026, 10, 23),
        "America/Phoenix",
    )

    assert sun_call_sizes == [145]
    assert 289 in moon_call_sizes
    assert max(moon_call_sizes) <= 289


@pytest.mark.parametrize(
    ("latitude", "longitude", "elevation_m", "night", "timezone"),
    [
        pytest.param(
            33.4484,
            -112.0740,
            331.0,
            date(2026, 10, 23),
            "America/Phoenix",
            id="phoenix",
        ),
        pytest.param(
            51.5074,
            -0.1278,
            None,
            date(2026, 10, 24),
            "Europe/London",
            id="london-dst",
        ),
        pytest.param(
            -0.1807,
            -78.4678,
            None,
            date(2026, 10, 23),
            "America/Guayaquil",
            id="quito",
        ),
        pytest.param(
            -33.8688,
            151.2093,
            None,
            date(2026, 12, 14),
            "Australia/Sydney",
            id="sydney",
        ),
        pytest.param(
            69.65,
            18.96,
            None,
            date(2026, 6, 14),
            "Europe/Oslo",
            id="tromso-summer",
        ),
        pytest.param(
            69.65,
            18.96,
            None,
            date(2026, 12, 14),
            "Europe/Oslo",
            id="tromso-winter",
        ),
        pytest.param(
            84.5,
            -15,
            0,
            date(2026, 12, 21),
            "UTC",
            id="split-astro",
        ),
        pytest.param(
            48.5640,
            7.75,
            None,
            date(2026, 6, 20),
            "Europe/Paris",
            id="graze-below",
        ),
        pytest.param(
            48.5655,
            7.75,
            None,
            date(2026, 6, 20),
            "Europe/Paris",
            id="graze-above",
        ),
    ],
)
def test_night_summary_equivalent_to_exact(
    monkeypatch,
    latitude,
    longitude,
    elevation_m,
    night,
    timezone,
):
    args = (latitude, longitude, elevation_m, night, timezone)
    exact = _compute_exact(monkeypatch, *args)

    sun_call_sizes: list[int] = []
    original_sun_altitudes = astronomy._sun_altitudes

    def recording_sun_altitudes(times, location):
        sun_call_sizes.append(len(times))
        return original_sun_altitudes(times, location)

    monkeypatch.setattr(astronomy, "_sun_altitudes", recording_sun_altitudes)
    fast = astronomy.compute_night_summary(*args)

    assert sun_call_sizes == [145]
    _assert_equivalent(exact, fast)


def test_grazing_cases_are_grazing(monkeypatch):
    below = _compute_exact(
        monkeypatch,
        48.5640,
        7.75,
        None,
        date(2026, 6, 20),
        "Europe/Paris",
    )
    above = _compute_exact(
        monkeypatch,
        48.5655,
        7.75,
        None,
        date(2026, 6, 20),
        "Europe/Paris",
    )

    assert len(below.dark_intervals["astronomical"]) == 1
    start, end = below.dark_intervals["astronomical"][0]
    assert end - start < timedelta(minutes=10)
    assert above.dark_intervals["astronomical"] == []


def test_moon_branch_cases(monkeypatch):
    winter = _compute_exact(
        monkeypatch,
        69.65,
        18.96,
        None,
        date(2026, 12, 14),
        "Europe/Oslo",
    )
    summer = _compute_exact(
        monkeypatch,
        69.65,
        18.96,
        None,
        date(2026, 6, 14),
        "Europe/Oslo",
    )
    split_astro = _compute_exact(
        monkeypatch,
        84.5,
        -15,
        0,
        date(2026, 12, 21),
        "UTC",
    )

    assert winter.moon.moonrise_utc is not None
    assert winter.moon.moonset_utc is not None
    assert summer.moon.moonrise_utc is None
    assert summer.moon.moonset_utc is None
    assert split_astro.moon.moonrise_utc is None
    assert split_astro.moon.moonset_utc is None
