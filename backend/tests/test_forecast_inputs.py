"""Complete UTC evaluator-input construction."""

from datetime import UTC, datetime, timedelta

from nightcrate.services.forecast_inputs import build_hours
from nightcrate.services.weather import CloudModelData, HourlyWeather, ModelSeries


def _hour(hour: int, **changes) -> HourlyWeather:
    values = {
        "time_utc": datetime(2026, 10, 18, hour, tzinfo=UTC),
        "temperature_c": 10.0,
        "dew_point_c": 4.0,
        "humidity_pct": 50.0,
        "cloud_cover_pct": 10.0,
        "cloud_cover_low_pct": 2.0,
        "cloud_cover_mid_pct": 3.0,
        "cloud_cover_high_pct": 5.0,
        "wind_speed_kmh": 5.0,
        "wind_direction_deg": 180.0,
        "wind_gusts_kmh": 10.0,
        "visibility_m": 20000.0,
        "precipitation_mm": 0.0,
        "precipitation_probability_pct": 0.0,
    }
    values.update(changes)
    return HourlyWeather(**values)


def _model_series(
    values: dict[datetime, tuple[float | None, float | None, float | None, float | None]],
) -> ModelSeries:
    return ModelSeries(
        cloud_total_pct={stamp: figures[0] for stamp, figures in values.items()},
        cloud_low_pct={stamp: figures[1] for stamp, figures in values.items()},
        cloud_mid_pct={stamp: figures[2] for stamp, figures in values.items()},
        cloud_high_pct={stamp: figures[3] for stamp, figures in values.items()},
        precipitation_mm={},
        fields_present=frozenset(
            {"cloud_cover", "cloud_cover_low", "cloud_cover_mid", "cloud_cover_high"}
        ),
    )


def _expected(until: datetime) -> dict[str, datetime]:
    return {
        "best_match": until,
        "ecmwf_ifs025": until,
        "gfs_seamless": until,
        "icon_seamless": until,
    }


def test_model_hours_carry_expected_flags():
    start = datetime(2026, 10, 18, 18, tzinfo=UTC)
    expected = _expected(start + timedelta(days=1))
    expected["icon_seamless"] = start + timedelta(minutes=30)
    result = build_hours(
        [_hour(18), _hour(19)],
        None,
        {},
        start,
        start + timedelta(hours=1),
        expected=expected,
    )
    icon = result[0].models["icon_seamless"]
    assert icon.cloud_expected is True
    assert icon.amount_expected is False
    assert icon.cloud_total_pct is None
    assert icon.precip_mm is None


def test_missing_total_not_rebuilt():
    start = datetime(2026, 10, 18, 18, tzinfo=UTC)
    series = _model_series({start: (None, 10.0, 20.0, 30.0)})
    cloud_models = CloudModelData(models={"ecmwf_ifs025": series}, raw_json="{}")
    result = build_hours(
        [_hour(18), _hour(19)],
        cloud_models,
        {},
        start,
        start + timedelta(hours=1),
        expected=_expected(start + timedelta(days=1)),
    )
    model = result[0].models["ecmwf_ifs025"]
    assert model.cloud_total_pct is None
    assert model.cloud_layers_pct == (10.0, 20.0, 30.0)


def test_build_hours_shifts_all_preceding_hour_fields():
    start = datetime(2026, 10, 18, 18, tzinfo=UTC)
    next_hour = start + timedelta(hours=1)
    series = _model_series({start: (7.0, 1.0, 2.0, 4.0)})
    series.precipitation_mm[next_hour] = 0.7
    cloud_models = CloudModelData(models={"ecmwf_ifs025": series}, raw_json="{}")
    result = build_hours(
        [
            _hour(18, wind_speed_kmh=8.0),
            _hour(
                19,
                precipitation_mm=0.4,
                precipitation_probability_pct=60.0,
                wind_gusts_kmh=55.0,
            ),
        ],
        cloud_models,
        {},
        start,
        next_hour,
        expected=_expected(start + timedelta(days=1)),
    )[0]
    assert result.precip_mm == 0.4
    assert result.precip_probability_pct == 60.0
    assert result.gust_kmh == 55.0
    assert result.wind_kmh == 8.0
    assert result.models["best_match"].precip_mm == 0.4
    assert result.models["ecmwf_ifs025"].precip_mm == 0.7
