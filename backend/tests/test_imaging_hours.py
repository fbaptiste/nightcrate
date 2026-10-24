"""Unit tests for revised per-hour imaging checks."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from nightcrate.services.imaging_hours import (
    conditions,
    precipitation_checks,
)
from nightcrate.services.imaging_rules import PRESETS, ImagingRules
from nightcrate.services.imaging_types import HourInput, ModelHour

START = datetime(2026, 10, 18, 2, tzinfo=UTC)


def _rules(**overrides: object) -> ImagingRules:
    values = PRESETS["left_out_all_night"][1].model_dump()
    values.update(overrides)
    return ImagingRules(**values)


def _model(
    total: float | None = 10.0,
    layers: tuple[float | None, float | None, float | None] = (0.0, 0.0, 10.0),
    *,
    amount: float | None = 0.0,
    amount_expected: bool = True,
) -> ModelHour:
    return ModelHour(
        cloud_total_pct=total,
        cloud_layers_pct=layers,
        precip_mm=amount,
        cloud_expected=True,
        amount_expected=amount_expected,
    )


def _hour(**overrides: object) -> HourInput:
    values = {
        "start_utc": START,
        "models": {
            "best_match": _model(),
            "ecmwf_ifs025": _model(),
            "gfs_seamless": _model(),
            "icon_seamless": _model(),
        },
        "precip_probability_pct": 0.0,
        "precip_mm": 0.0,
        "wind_kmh": 10.0,
        "gust_kmh": 15.0,
        "temperature_c": 10.0,
        "dew_point_c": 2.0,
        "moon_altitude_deg": -10.0,
    }
    values.update(overrides)
    return HourInput(**values)


def _with_primary(hour: HourInput, model: ModelHour) -> HourInput:
    models = dict(hour.models)
    models["ecmwf_ifs025"] = model
    return replace(hour, models=models)


def test_total_4_layers_21_clear():
    hour = _with_primary(_hour(), _model(4.0, (0.0, 0.0, 21.0)))
    assert conditions(hour, _rules(cloud_max_pct=20), "ecmwf_ifs025")["cloud"] == "pass"


def test_total_0_layers_missing_clear():
    hour = _with_primary(_hour(), _model(0.0, (None, None, None)))
    assert conditions(hour, _rules(cloud_max_pct=20), "ecmwf_ifs025")["cloud"] == "pass"


def test_total_at_limit_clear():
    hour = _with_primary(_hour(), _model(20.0, (80.0, 80.0, 80.0)))
    assert conditions(hour, _rules(cloud_max_pct=20), "ecmwf_ifs025")["cloud"] == "pass"


def test_total_missing_layers_present_unknown():
    hour = _with_primary(_hour(), _model(None, (1.0, 2.0, 3.0)))
    assert conditions(hour, _rules(cloud_max_pct=20), "ecmwf_ifs025")["cloud"] == "unknown"


@pytest.mark.parametrize(
    ("temperature_c", "dew_point_c", "expected"),
    [(10.0, 6.0, "pass"), (10.0, 7.0, "pass"), (10.0, 8.0, "fail")],
)
def test_dew_spread_threshold(temperature_c, dew_point_c, expected):
    hour = _hour(temperature_c=temperature_c, dew_point_c=dew_point_c)
    result = conditions(hour, _rules(dew_counted=True, dew_min_spread_c=3.0), "ecmwf_ifs025")
    assert result["dew"] == expected


@pytest.mark.parametrize("missing", ["temperature_c", "dew_point_c"])
def test_counted_dew_with_missing_input_is_unknown(missing):
    result = conditions(
        _hour(**{missing: None}),
        _rules(dew_counted=True, dew_min_spread_c=3.0),
        "ecmwf_ifs025",
    )
    assert result["dew"] == "unknown"


def test_uncounted_dew_with_missing_inputs_is_not_counted():
    result = conditions(
        _hour(temperature_c=None, dew_point_c=None),
        _rules(dew_counted=False, dew_min_spread_c=3.0),
        "ecmwf_ifs025",
    )
    assert result["dew"] == "not_counted"


def test_single_chance_limit_applies_to_every_hour():
    rules = _rules(rain_max_probability_pct=10)
    for hour in (0, 48, 240):
        start = START.replace(hour=0) + timedelta(hours=hour)
        assert (
            precipitation_checks(
                _hour(start_utc=start, precip_probability_pct=11),
                rules,
            )["chance"]
            == "fail"
        )
        assert (
            precipitation_checks(
                _hour(start_utc=start, precip_probability_pct=10),
                rules,
            )["chance"]
            == "pass"
        )


def test_amount_005_threshold_0_fails():
    checks = precipitation_checks(_hour(precip_mm=0.05), _rules(rain_amount_threshold_mm=0))
    assert checks["amount"] == "fail"


def test_amount_equal_threshold_passes():
    checks = precipitation_checks(_hour(precip_mm=0.1), _rules(rain_amount_threshold_mm=0.1))
    assert checks["amount"] == "pass"


def test_chance_only_from_main():
    rules = _rules(
        rain_forecasts="any_model",
        rain_max_probability_pct=10,
        rain_amount_threshold_mm=0.1,
    )
    hour = _hour(precip_probability_pct=5.0)
    checks = precipitation_checks(hour, rules)
    assert checks == {
        "chance": "pass",
        "amount": "pass",
        "amount:ecmwf_ifs025": "pass",
        "amount:gfs_seamless": "pass",
        "amount:icon_seamless": "pass",
    }


def test_extra_amount_omitted_outside_coverage():
    hour = _hour()
    models = dict(hour.models)
    models["icon_seamless"] = _model(amount=1.0, amount_expected=False)
    checks = precipitation_checks(
        replace(hour, models=models),
        _rules(rain_forecasts="any_model"),
    )
    assert "amount:icon_seamless" not in checks
