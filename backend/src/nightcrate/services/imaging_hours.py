"""Pure per-hour checks for the revised imaging evaluator."""

from collections.abc import Mapping

from nightcrate.services.imaging_rules import ImagingRules
from nightcrate.services.imaging_types import (
    CheckState,
    HourInput,
    HourState,
)


def _threshold(value: float | None, limit: float) -> CheckState:
    if value is None:
        return "unknown"
    return "fail" if value > limit else "pass"


def precipitation_checks(hour: HourInput, rules: ImagingRules) -> dict[str, CheckState]:
    """Judge main-forecast chance and amounts from each enabled source."""
    checks = {
        "chance": _threshold(
            hour.precip_probability_pct,
            rules.rain_max_probability_pct,
        ),
        "amount": _threshold(hour.precip_mm, rules.rain_amount_threshold_mm),
    }
    if rules.rain_forecasts == "any_model":
        for model_name, model in hour.models.items():
            if model_name == "best_match" or not model.amount_expected:
                continue
            checks[f"amount:{model_name}"] = _threshold(
                model.precip_mm,
                rules.rain_amount_threshold_mm,
            )
    return checks


def _aggregate(checks: Mapping[str, CheckState]) -> CheckState:
    if "fail" in checks.values():
        return "fail"
    if "unknown" in checks.values():
        return "unknown"
    return "pass"


def conditions(
    hour: HourInput,
    rules: ImagingRules,
    cloud_model: str,
) -> dict[str, CheckState]:
    """Judge every enabled display condition, without applying intervals."""
    model = hour.models.get(cloud_model)
    cloud_total = model.cloud_total_pct if model is not None else None
    cloud = _threshold(cloud_total, rules.cloud_max_pct)

    if rules.wind_counted:
        wind_checks = {
            "wind": _threshold(hour.wind_kmh, rules.wind_max_kmh),
            "gust": _threshold(hour.gust_kmh, rules.gust_max_kmh),
        }
        wind = _aggregate(wind_checks)
    else:
        wind = "not_counted"

    if rules.dew_counted:
        dew_spread = (
            hour.temperature_c - hour.dew_point_c
            if hour.temperature_c is not None and hour.dew_point_c is not None
            else None
        )
        dew: CheckState = (
            "unknown"
            if dew_spread is None
            else "fail"
            if dew_spread < rules.dew_min_spread_c
            else "pass"
        )
    else:
        dew = "not_counted"

    if rules.moon_must_be_down:
        moon: CheckState = (
            "unknown"
            if hour.moon_altitude_deg is None
            else "fail"
            if hour.moon_altitude_deg >= 0
            else "pass"
        )
    else:
        moon = "not_counted"

    return {
        "cloud": cloud,
        "rain": _aggregate(precipitation_checks(hour, rules)),
        "wind": wind,
        "dew": dew,
        "moon": moon,
    }


def hour_state(checks: Mapping[str, CheckState], *, dark_minutes: float) -> HourState:
    """Reduce counted checks to the state used by the session kernel."""
    if dark_minutes <= 0:
        return "outside"
    counted = tuple(state for state in checks.values() if state != "not_counted")
    if "fail" in counted:
        return "not_clear"
    if "unknown" in counted:
        return "unknown"
    return "clear"
