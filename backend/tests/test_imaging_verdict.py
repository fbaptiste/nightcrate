"""Hand-computed regression tests for the revised imaging verdict evaluator."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from random import Random

import pytest

from nightcrate.api.weather import _is_single_model
from nightcrate.services.imaging_rules import PRESETS, ImagingRules
from nightcrate.services.imaging_types import (
    HourInput,
    ModelHour,
    NightControls,
    NightInput,
    Reason,
)
from nightcrate.services.imaging_verdict import (
    _bounded,
    apply_precedence,
    combine_short_session,
    evaluate_night,
)

DAY = datetime(2026, 10, 17, 12, tzinfo=UTC)
MODELS = ("best_match", "ecmwf_ifs025", "gfs_seamless", "icon_seamless")


def _at(hour: int, minute: int = 0) -> datetime:
    day = DAY if hour >= 12 else DAY + timedelta(days=1)
    return day.replace(hour=hour, minute=minute)


def _model(
    total: float | None = 10.0,
    *,
    layers: tuple[float | None, float | None, float | None] = (0.0, 0.0, 10.0),
    amount: float | None = 0.0,
    cloud_expected: bool = True,
    amount_expected: bool = True,
) -> ModelHour:
    return ModelHour(total, layers, amount, cloud_expected, amount_expected)


def _hour(start: datetime) -> HourInput:
    return HourInput(
        start_utc=start,
        models={name: _model() for name in MODELS},
        precip_probability_pct=0.0,
        precip_mm=0.0,
        wind_kmh=10.0,
        gust_kmh=15.0,
        temperature_c=10.0,
        dew_point_c=2.0,
        moon_altitude_deg=-10.0,
    )


def _night(**overrides: object) -> NightInput:
    primary_model = overrides.pop("primary_model", "ecmwf_ifs025")
    comparison_models = overrides.pop("comparison_models", ())
    values: dict[str, object] = {
        "sunset_utc": _at(18, 30),
        "sunrise_utc": _at(5, 30),
        "noon_start_utc": DAY,
        "noon_end_utc": DAY + timedelta(days=1),
        "dark_intervals": [(_at(20), _at(4))],
        "hours": [_hour(_at(hour)) for hour in (*range(18, 24), *range(0, 6))],
        "now_utc": DAY,
        "controls": NightControls(),
        "cloud_models": (primary_model, *comparison_models),
        "preferred_model": primary_model,
        "combination": "uncertain",
        "fallback_model": "best_match",
        "stale_minutes": {"forecast": None, "cloud_models": None},
    }
    values.update(overrides)
    return NightInput(**values)


def _rules(**overrides: object) -> ImagingRules:
    values = PRESETS["left_out_all_night"][1].model_dump()
    values.update(overrides)
    return ImagingRules(**values)


def _set_hour(night: NightInput, hours: tuple[int, ...], **changes: object) -> NightInput:
    return replace(
        night,
        hours=[
            replace(item, **changes) if item.start_utc.hour in hours else item
            for item in night.hours
        ],
    )


def _set_model(
    night: NightInput, model: str, hours: tuple[int, ...], **changes: object
) -> NightInput:
    revised = []
    for item in night.hours:
        if item.start_utc.hour in hours:
            models = dict(item.models)
            models[model] = replace(models[model], **changes)
            item = replace(item, models=models)
        revised.append(item)
    return replace(night, hours=revised)


def _result_hour(result, hour: int):
    return next(item for item in result.hours if item.start_utc.hour == hour)


def test_combiners_and_precedence_tables():
    assert combine_short_session("go", "established", {"gfs": "go"}) == "go"
    assert combine_short_session("go", "impossible", {"gfs": "no"}) == "uncertain"
    assert combine_short_session("go", "unresolved", {"gfs": "unresolved"}) == ("not_enough_data")
    assert combine_short_session("no", "impossible", {"gfs": "go"}) == "uncertain"
    assert combine_short_session("no", "impossible", {"gfs": "unresolved"}) == "no"
    assert (
        apply_precedence(
            "uncertain", precipitation_veto=True, precipitation_unknown=True, stale=True
        )
        == "no"
    )
    assert (
        apply_precedence(
            "uncertain", precipitation_veto=False, precipitation_unknown=True, stale=False
        )
        == "not_enough_data"
    )
    assert (
        apply_precedence("no", precipitation_veto=False, precipitation_unknown=True, stale=True)
        == "no"
    )


def test_short_session_combiner_rejects_not_expected_and_preserves_unresolved():
    with pytest.raises(ValueError, match="primary model must be resolved"):
        combine_short_session("not_expected", "impossible", {})
    # An impossible window would otherwise give "uncertain".
    assert combine_short_session("unresolved", "impossible", {"gfs": "no"}) == "not_enough_data"


def test_bounded_gap_reason_and_no_unknown_minutes():
    reason = Reason(code="gap", value=2.0, limit=1.0)
    assert _bounded(reason, 30.0) == replace(reason, bound="at_least")
    assert _bounded(reason, 0.0) is reason
    assert _bounded(reason, -1.0) is reason


def test_clear_with_gaps_names_requirement():
    night = _set_model(_night(), "ecmwf_ifs025", (20, 21, 22), cloud_total_pct=80.0)
    result = evaluate_night(night, _rules())
    assert result.verdict == "go"
    assert (result.reasons[0].code, result.reasons[0].requirement) == (
        "clear_with_gaps",
        "cloud",
    )


def test_total_only_cloud_rule_ignores_layers():
    night = _set_model(
        _night(),
        "ecmwf_ifs025",
        tuple(range(24)),
        cloud_total_pct=4.0,
        cloud_layers_pct=(0.0, 0.0, 21.0),
    )
    assert evaluate_night(night, _rules(cloud_max_pct=20)).verdict == "go"


def test_chance_reason_uses_first_consecutive_failure_run():
    night = _set_hour(
        _night(),
        (18, 19, 21, 22),
        precip_probability_pct=11.0,
    )
    night = _set_hour(night, (19,), precip_probability_pct=20.0)
    result = evaluate_night(
        night,
        _rules(
            gear_out_before_sunset_min=36,
            rain_max_probability_pct=10,
        ),
    )
    reason = result.reasons[0]
    assert (result.verdict, reason.code) == ("no", "rain")
    assert (reason.start_utc, reason.end_utc) == (_at(18), _at(20))
    assert (reason.value, reason.limit) == (20.0, 10.0)

    passing = evaluate_night(
        night,
        _rules(
            gear_out_before_sunset_min=36,
            rain_max_probability_pct=20,
        ),
    )
    assert passing.verdict == "go"


def test_amount_thresholds_and_any_model():
    main = _set_hour(_night(), (22,), precip_mm=0.05)
    result = evaluate_night(main, _rules(rain_amount_threshold_mm=0))
    assert (result.verdict, result.reasons[0].code) == ("no", "rain_amount")
    equal = _set_hour(_night(), (22,), precip_mm=0.1)
    assert evaluate_night(equal, _rules(rain_amount_threshold_mm=0.1)).verdict == "go"
    icon = _set_model(_night(), "icon_seamless", (22,), precip_mm=0.7)
    result = evaluate_night(icon, _rules(rain_forecasts="any_model"))
    assert (result.verdict, result.reasons[0].code, result.reasons[0].model) == (
        "no",
        "rain_model_amount",
        "icon_seamless",
    )


def test_any_model_amount_outside_exposure_is_ignored():
    night = _set_model(_night(), "icon_seamless", (5,), precip_mm=0.7)
    result = evaluate_night(
        replace(night, controls=NightControls(gear_in_utc=_at(5))),
        _rules(rain_forecasts="any_model"),
    )
    assert result.verdict == "go"


def test_main_chance_only_and_missing_model_amount():
    night = _set_model(_night(), "icon_seamless", (22,), precip_mm=None)
    night = _set_hour(night, (22,), precip_probability_pct=5.0)
    result = evaluate_night(night, _rules(rain_forecasts="any_model"))
    assert result.verdict == "not_enough_data"
    assert (result.reasons[0].code, result.reasons[0].model) == (
        "rain_missing",
        "icon_seamless",
    )


def test_missing_model_amount_hours_lost_can_still_go():
    night = _set_model(_night(), "icon_seamless", (22,), precip_mm=None)
    result = evaluate_night(
        night,
        _rules(
            session_style="short_session",
            short_session_hours=2,
            rain_forecasts="any_model",
            rain_policy="hours_lost",
        ),
    )
    assert result.verdict == "go"


def test_rain_before_now_ignored():
    night = _set_hour(_night(now_utc=_at(23)), (20,), precip_probability_pct=90.0)
    assert evaluate_night(night, _rules()).verdict == "go"


def test_missing_main_precipitation_in_twilight_is_not_enough_data():
    night = _set_hour(_night(), (18,), precip_probability_pct=None)
    result = evaluate_night(night, _rules())
    assert (result.verdict, result.reasons[0].code, result.reasons[0].start_utc) == (
        "not_enough_data",
        "rain_missing",
        _at(18),
    )


def test_icon_beyond_coverage_ignored_without_reason_noise():
    night = _set_model(
        _night(comparison_models=("gfs_seamless", "icon_seamless")),
        "icon_seamless",
        tuple(range(24)),
        cloud_total_pct=90.0,
        cloud_expected=False,
    )
    result = evaluate_night(night, _rules())
    assert result.verdict == "go"
    assert result.model_statuses["icon_seamless"] == "not_expected"
    assert not any(reason.code == "model_not_used" for reason in result.reasons)


def test_model_not_used_only_when_partly_covered():
    no_coverage = _set_model(
        _night(comparison_models=("icon_seamless",)),
        "icon_seamless",
        tuple(range(24)),
        cloud_expected=False,
    )
    no_coverage_result = evaluate_night(no_coverage, _rules())
    assert not any(reason.code == "model_not_used" for reason in no_coverage_result.reasons)

    partial = _set_model(
        _night(comparison_models=("icon_seamless",)),
        "icon_seamless",
        (22, 23, 0, 1, 2, 3, 4, 5),
        cloud_expected=False,
    )
    partial_result = evaluate_night(partial, _rules())
    qualifier = next(reason for reason in partial_result.reasons if reason.code == "model_not_used")
    assert (qualifier.model, qualifier.end_utc) == ("icon_seamless", _at(21))


def test_disagreement_models_exclude_not_expected():
    night = _set_model(
        _night(comparison_models=("gfs_seamless", "icon_seamless")),
        "gfs_seamless",
        tuple(range(24)),
        cloud_total_pct=90.0,
    )
    night = _set_model(
        night,
        "icon_seamless",
        tuple(range(24)),
        cloud_expected=False,
    )
    result = evaluate_night(night, _rules())
    assert result.reasons[0].code == "models_disagree"
    assert result.reasons[0].models == {"ecmwf_ifs025": "go", "gfs_seamless": "no"}


def test_whole_cloud_response_missing_inside_coverage():
    night = _set_model(
        _night(comparison_models=("gfs_seamless", "icon_seamless")),
        "icon_seamless",
        tuple(range(24)),
        cloud_total_pct=None,
    )
    result = evaluate_night(night, _rules())
    assert (result.verdict, result.fallback) == ("not_enough_data", False)
    assert result.model_statuses["icon_seamless"] == "unresolved"


def test_comparison_partial_coverage_status_rows():
    base = _night(comparison_models=("gfs_seamless", "icon_seamless"))
    two_cloudy = _set_model(base, "icon_seamless", (20, 21), cloud_total_pct=90.0)
    two_cloudy = _set_model(
        two_cloudy,
        "icon_seamless",
        (22, 23, 0, 1, 2, 3),
        cloud_expected=False,
    )
    disclosed = evaluate_night(two_cloudy, _rules(min_clear_fraction_pct=75))
    assert (disclosed.verdict, disclosed.model_statuses["icon_seamless"]) == (
        "go",
        "not_expected",
    )

    seven_cloudy = _set_model(
        base,
        "icon_seamless",
        (20, 21, 22, 23, 0, 1, 2),
        cloud_total_pct=90.0,
    )
    seven_cloudy = _set_model(seven_cloudy, "icon_seamless", (3,), cloud_expected=False)
    established = evaluate_night(seven_cloudy, _rules(min_clear_fraction_pct=75))
    assert (established.verdict, established.model_statuses["icon_seamless"]) == (
        "uncertain",
        "no",
    )


def test_primary_no_comparison_rows():
    primary_no = _set_model(
        _night(comparison_models=("gfs_seamless", "icon_seamless")),
        "ecmwf_ifs025",
        tuple(range(24)),
        cloud_total_pct=90.0,
    )
    dissent = evaluate_night(primary_no, _rules())
    assert dissent.verdict == "uncertain"

    agreed = _set_model(primary_no, "gfs_seamless", tuple(range(24)), cloud_total_pct=90.0)
    agreed = _set_model(agreed, "icon_seamless", tuple(range(24)), cloud_total_pct=10.0)
    agreed = _set_model(agreed, "icon_seamless", (3,), cloud_total_pct=None)
    result = evaluate_night(agreed, _rules(min_clear_fraction_pct=100))
    assert (result.verdict, result.model_statuses["icon_seamless"]) == (
        "no",
        "unresolved",
    )
    assert any(reason.code == "model_incomplete" for reason in result.reasons)


def test_ecmwf_missing_decisive_hour_not_enough_data():
    night = _set_model(_night(), "ecmwf_ifs025", (23,), cloud_total_pct=None)
    result = evaluate_night(night, _rules(min_clear_fraction_pct=100, min_clear_hours=8))
    assert (result.verdict, result.fallback, result.reasons[0].model) == (
        "not_enough_data",
        False,
        "ecmwf_ifs025",
    )


def test_primary_partial_coverage_failure_does_not_fallback():
    night = _set_model(
        _night(comparison_models=("gfs_seamless",)),
        "ecmwf_ifs025",
        (20, 21, 22, 23, 0, 1),
        cloud_total_pct=90.0,
    )
    night = _set_model(night, "ecmwf_ifs025", (2, 3), cloud_expected=False)
    result = evaluate_night(night, _rules(min_clear_fraction_pct=90))
    assert (result.fallback, result.model_statuses["ecmwf_ifs025"]) == (False, "no")


def test_preferred_partial_coverage_uses_next_ticked_model():
    night = _set_model(
        _night(comparison_models=("gfs_seamless", "icon_seamless")),
        "ecmwf_ifs025",
        (2, 3),
        cloud_expected=False,
    )
    result = evaluate_night(night, _rules(min_clear_fraction_pct=90))
    assert (result.verdict, result.fallback, result.primary_model) == (
        "go",
        False,
        "gfs_seamless",
    )
    assert set(result.model_statuses) == {
        "ecmwf_ifs025",
        "gfs_seamless",
        "icon_seamless",
    }


def test_fallback_not_expected_is_not_enough_data():
    night = _set_model(_night(), "ecmwf_ifs025", tuple(range(24)), cloud_expected=False)
    night = _set_model(night, "best_match", tuple(range(24)), cloud_expected=False)
    result = evaluate_night(night, _rules())
    assert (result.verdict, result.fallback) == ("not_enough_data", True)


def test_short_session_shared_window_cases():
    rules = _rules(session_style="short_session", short_session_hours=2)
    night = _night(comparison_models=("gfs_seamless", "icon_seamless"))
    night = _set_model(night, "gfs_seamless", (20, 21), cloud_total_pct=90.0)
    night = _set_model(night, "icon_seamless", (22, 23), cloud_total_pct=90.0)
    result = evaluate_night(night, rules)
    assert result.verdict == "go"
    assert result.window == (_at(0), _at(2))

    disjoint = _night(comparison_models=("gfs_seamless", "icon_seamless"))
    disjoint = _set_model(disjoint, "ecmwf_ifs025", (22, 23, 0, 1, 2, 3), cloud_total_pct=90)
    disjoint = _set_model(disjoint, "gfs_seamless", (20, 21, 0, 1, 2, 3), cloud_total_pct=90)
    disjoint = _set_model(disjoint, "icon_seamless", (20, 21, 22, 23, 2, 3), cloud_total_pct=90)
    result = evaluate_night(disjoint, rules)
    assert (result.verdict, result.reasons[0].code) == ("uncertain", "no_shared_window")


def test_short_session_missing_only_window_not_enough_data():
    rules = _rules(session_style="short_session", short_session_hours=2)
    night = _night(comparison_models=("gfs_seamless", "icon_seamless"))
    night = _set_model(night, "icon_seamless", (20, 21), cloud_total_pct=None)
    for hour in (22, 23, 0, 1, 2, 3):
        night = _set_model(night, "ecmwf_ifs025", (hour,), cloud_total_pct=90.0)
        night = _set_model(night, "gfs_seamless", (hour,), cloud_total_pct=90.0)
    assert evaluate_night(night, rules).verdict == "not_enough_data"


def test_night_off_unknown_rain_keeps_cloud_no():
    no_night = _set_model(_night(), "ecmwf_ifs025", (20, 21, 22, 23, 0), cloud_total_pct=90.0)
    no_night = _set_hour(no_night, (2,), precip_probability_pct=None)
    result = evaluate_night(no_night, _rules())
    assert result.verdict == "no"
    assert any(reason.code == "rain_missing" for reason in result.reasons)
    uncertain = replace(
        no_night,
        cloud_models=("ecmwf_ifs025", "gfs_seamless"),
        combination="uncertain",
    )
    assert evaluate_night(uncertain, _rules()).verdict == "not_enough_data"


def test_precip_veto_with_disagreement_context():
    night = _set_model(
        _night(comparison_models=("gfs_seamless",)),
        "gfs_seamless",
        tuple(range(24)),
        cloud_total_pct=90.0,
    )
    night = _set_hour(night, (22,), precip_probability_pct=20.0)
    result = evaluate_night(night, _rules())
    assert result.verdict == "no"
    assert [reason.code for reason in result.reasons[:2]] == ["rain", "models_disagree"]


def test_unresolved_primary_with_precip_veto_is_no():
    night = _set_model(_night(), "ecmwf_ifs025", (23,), cloud_total_pct=None)
    night = _set_hour(night, (22,), precip_probability_pct=20.0)
    result = evaluate_night(night, _rules(min_clear_fraction_pct=100))
    assert (result.verdict, result.reasons[0].code) == ("no", "rain")


def test_stale_no_keeps_no_with_age_and_stale_uncertain_is_not_enough_data():
    no_night = _set_model(
        _night(stale_minutes={"forecast": 540, "cloud_models": None}),
        "ecmwf_ifs025",
        (20, 21, 22, 23, 0),
        cloud_total_pct=90.0,
    )
    no = evaluate_night(no_night, _rules())
    assert (no.verdict, no.reasons[0].code, no.reasons[0].value) == ("no", "stale", 540)
    uncertain = replace(
        no_night,
        cloud_models=("ecmwf_ifs025", "gfs_seamless"),
        combination="uncertain",
    )
    uncertain = _set_model(uncertain, "gfs_seamless", tuple(range(24)), cloud_total_pct=10.0)
    result = evaluate_night(uncertain, _rules())
    assert (result.verdict, result.reasons[0].code) == ("not_enough_data", "stale")


def test_disagrees_only_on_uncertain():
    go_night = _set_model(
        _night(comparison_models=("gfs_seamless",)), "gfs_seamless", (20,), cloud_total_pct=90.0
    )
    go = evaluate_night(go_night, _rules())
    assert go.verdict == "go"
    assert not any(hour.disagrees for hour in go.hours)
    uncertain = evaluate_night(
        _set_model(go_night, "gfs_seamless", (21, 22, 23, 0), cloud_total_pct=90.0),
        _rules(),
    )
    assert uncertain.verdict == "uncertain"
    assert any(hour.disagrees for hour in uncertain.hours)


def test_advisory_shown_and_suppressed():
    layers = (0.0, 0.0, 44.0)
    night = _set_model(_night(), "ecmwf_ifs025", (22, 23), cloud_layers_pct=layers)
    shown = evaluate_night(night, _rules())
    assert (shown.advisory.code, shown.advisory.requirement, shown.advisory.value) == (
        "layer_advisory",
        "high",
        44.0,
    )
    failing = _set_model(night, "ecmwf_ifs025", (22, 23), cloud_total_pct=90.0)
    assert evaluate_night(failing, _rules()).advisory is None
    fallback = _set_model(night, "ecmwf_ifs025", tuple(range(24)), cloud_expected=False)
    assert evaluate_night(fallback, _rules()).advisory is None
    twilight = _set_model(_night(), "ecmwf_ifs025", (19,), cloud_layers_pct=layers)
    assert evaluate_night(twilight, _rules()).advisory is None
    assert evaluate_night(replace(night, now_utc=_at(5)), _rules()).advisory is None


def test_imaging_inside_exposure():
    controls = NightControls(
        gear_out_utc=_at(17), gear_in_utc=_at(7), imaging_from_utc=_at(20), imaging_until_utc=_at(1)
    )
    night = _set_model(_night(controls=controls), "ecmwf_ifs025", (2, 3), cloud_total_pct=90)
    night = _set_hour(night, (3,), precip_probability_pct=20.0)
    result = evaluate_night(night, _rules())
    assert result.dark_minutes == 300
    assert (result.verdict, result.reasons[0].code) == ("no", "rain")


def test_gear_controls_and_hours_lost_stop():
    shower = _set_hour(_night(), (2,), precip_probability_pct=20.0)
    gear_in = evaluate_night(replace(shower, controls=NightControls(gear_in_utc=_at(0))), _rules())
    assert gear_in.verdict == "go"
    start = _set_hour(_night(), (22,), precip_probability_pct=11.0)
    start = evaluate_night(
        replace(start, controls=NightControls(gear_out_utc=_at(23))),
        _rules(rain_max_probability_pct=10),
    )
    assert (start.verdict, start.exposure[0]) == ("go", _at(23))
    stopped = evaluate_night(
        replace(shower, controls=NightControls(imaging_until_utc=_at(0))),
        _rules(rain_policy="hours_lost"),
    )
    assert stopped.exposure is None
    assert stopped.imaging[1] == _at(0)


def test_polar_intervals_and_early_exit_order():
    hours = [_hour(DAY + timedelta(hours=index)) for index in range(24)]
    continuous = _night(
        sunset_utc=None,
        sunrise_utc=None,
        dark_intervals=[(DAY, DAY + timedelta(days=1))],
        hours=hours,
    )
    result = evaluate_night(continuous, _rules())
    assert (result.dark_minutes, result.exposure) == (1440, (DAY, DAY + timedelta(days=1)))
    assert evaluate_night(replace(continuous, dark_intervals=[]), _rules()).reasons[0].code == (
        "never_dark"
    )
    split = replace(continuous, dark_intervals=[(DAY, _at(14)), (_at(16), DAY + timedelta(days=1))])
    assert evaluate_night(split, _rules()).dark_minutes == 1320
    expired = replace(
        continuous, now_utc=_at(18), controls=NightControls(imaging_until_utc=_at(17))
    )
    assert evaluate_night(expired, _rules()).verdict == "night_over"


def test_no_dark_time_after_never_dark_check():
    result = evaluate_night(
        replace(_night(), controls=NightControls(imaging_until_utc=_at(19, 30))), _rules()
    )
    assert (result.verdict, result.reasons[0].code) == ("no", "no_dark_time")


def test_min_hours_short_night():
    result = evaluate_night(_night(dark_intervals=[(_at(23, 30), _at(1))]), _rules())
    reason = result.reasons[0]
    assert result.verdict == "no"
    assert (reason.code, reason.value, reason.limit) == ("min_hours", 1.5, 2.0)


def test_gap_limit():
    night = _set_model(_night(), "ecmwf_ifs025", (22, 23), cloud_total_pct=80.0)
    result = evaluate_night(night, _rules(max_cloudy_gap_hours=1.0))
    reason = result.reasons[0]
    assert result.verdict == "no"
    assert (reason.code, reason.start_utc, reason.value, reason.limit) == (
        "gap",
        _at(22),
        2.0,
        1.0,
    )


def test_reason_tie_earliest_stretch():
    night = _set_model(_night(), "ecmwf_ifs025", (21, 1), cloud_total_pct=80.0)
    result = evaluate_night(night, _rules())
    assert result.verdict == "go"
    assert (result.reasons[0].code, result.reasons[0].start_utc) == (
        "clear_with_gaps",
        _at(21),
    )


def test_short_session_window():
    night = _set_model(_night(), "ecmwf_ifs025", (22, 23, 0, 1, 2, 3), cloud_total_pct=80.0)
    result = evaluate_night(night, _rules(session_style="short_session"))
    assert (result.verdict, result.window, result.reasons[0].code) == (
        "go",
        (_at(20), _at(22)),
        "short_window",
    )


def test_short_session_fragmented():
    night = _set_model(_night(), "ecmwf_ifs025", (21, 23, 1, 2, 3), cloud_total_pct=80.0)
    result = evaluate_night(night, _rules(session_style="short_session"))
    reason = result.reasons[0]
    assert result.verdict == "no"
    assert (reason.code, reason.value, reason.limit) == ("no_window", 1.0, 2.0)


def test_imaging_until_caps_short_session():
    result = evaluate_night(
        replace(_night(), controls=NightControls(imaging_until_utc=_at(21, 30))),
        _rules(session_style="short_session"),
    )
    reason = result.reasons[0]
    assert result.verdict == "no"
    assert (reason.code, reason.value) == ("no_window", 1.5)
    assert result.imaging == (_at(20), _at(21, 30))


def test_imaging_until_before_dark():
    result = evaluate_night(
        replace(_night(), controls=NightControls(imaging_until_utc=_at(19, 30))), _rules()
    )
    assert (result.verdict, result.reasons[0].code, result.reasons[0].start_utc) == (
        "no",
        "no_dark_time",
        _at(19, 30),
    )


def test_night_off_rain_in_cloudy_hour():
    night = _set_model(_night(), "ecmwf_ifs025", (22,), cloud_total_pct=90.0)
    night = _set_hour(night, (22,), precip_probability_pct=11.0)
    result = evaluate_night(night, _rules())
    assert (result.verdict, result.reasons[0].code, result.reasons[0].start_utc) == (
        "no",
        "rain",
        _at(22),
    )


def test_rain_amount_fails_even_at_zero_probability():
    result = evaluate_night(_set_hour(_night(), (22,), precip_mm=0.2), _rules())
    reason = result.reasons[0]
    assert result.verdict == "no"
    assert (reason.code, reason.value, reason.limit) == ("rain_amount", 0.2, 0.0)


def test_hours_lost_rain():
    night = _set_hour(_night(), (22, 23), precip_probability_pct=50.0)
    result = evaluate_night(night, _rules(rain_policy="hours_lost"))
    assert result.verdict == "go"
    assert _result_hour(result, 22).state == "not_clear"
    assert result.requirements["rain"] == "fail"
    assert result.requirements["clear_time"] == "pass"


def test_wind_not_counted_ignores_extreme_wind():
    windy = _set_hour(_night(), tuple(range(24)), wind_kmh=100.0, gust_kmh=150.0)
    result = evaluate_night(windy, _rules(wind_counted=False))
    assert result.verdict == "go"
    assert _result_hour(result, 22).checks["wind"] == "not_counted"
    assert result.requirements["wind"] == "not_counted"

    counted = evaluate_night(_set_hour(_night(), (22,), gust_kmh=50.0), _rules(wind_counted=True))
    assert _result_hour(counted, 22).checks["wind"] == "fail"
    assert _result_hour(counted, 22).state == "not_clear"


def test_dew_rule_changes_night_verdict():
    night = _set_hour(
        _night(),
        tuple(range(24)),
        temperature_c=5.0,
        dew_point_c=3.0,
    )

    # The dark interval is 20:00–04:00: 8 hours. A 2 C spread fails the
    # 3 C minimum in every dark hour, leaving 0/480 usable minutes; with dew
    # disabled, all 480 minutes are usable.
    counted = evaluate_night(night, _rules(dew_counted=True, dew_min_spread_c=3.0))
    assert (counted.verdict, counted.dark_minutes, counted.clear_minutes) == ("no", 480, 0)
    assert counted.requirements["dew"] == "fail"
    assert (counted.reasons[0].code, counted.reasons[0].value, counted.reasons[0].limit) == (
        "clear_fraction",
        0.0,
        50.0,
    )

    uncounted = evaluate_night(night, _rules(dew_counted=False, dew_min_spread_c=3.0))
    assert (uncounted.verdict, uncounted.dark_minutes, uncounted.clear_minutes) == (
        "go",
        480,
        480,
    )
    assert uncounted.requirements["dew"] == "not_counted"


def test_moon_boundary():
    failed = evaluate_night(
        _set_hour(_night(), (22,), moon_altitude_deg=0.0),
        _rules(moon_must_be_down=True),
    )
    passed = evaluate_night(
        _set_hour(_night(), (22,), moon_altitude_deg=-0.1),
        _rules(moon_must_be_down=True),
    )
    assert _result_hour(failed, 22).checks["moon"] == "fail"
    assert _result_hour(passed, 22).checks["moon"] == "pass"


def test_zero_limits_pass_on_zero_values():
    night = _set_model(_night(), "ecmwf_ifs025", tuple(range(24)), cloud_total_pct=0.0)
    assert evaluate_night(night, _rules(cloud_max_pct=0)).verdict == "go"


def test_missing_rain_but_provably_no():
    night = _set_model(_night(), "ecmwf_ifs025", (20, 21, 22, 23, 0), cloud_total_pct=80.0)
    night = _set_hour(night, (2,), precip_probability_pct=None)
    result = evaluate_night(night, _rules())
    reason = result.reasons[0]
    assert result.verdict == "no"
    assert (reason.code, reason.value, reason.bound) == (
        "clear_fraction",
        37.5,
        None,
    )
    assert result.clear_minutes == 180


def test_missing_cloud_hour_unknown():
    night = _set_model(_night(), "ecmwf_ifs025", (23,), cloud_total_pct=None)
    result = evaluate_night(night, _rules())
    reason = result.reasons[0]
    assert result.verdict == "go"
    assert (reason.code, reason.start_utc, reason.requirement) == (
        "clear_with_gaps",
        _at(23),
        "unknown",
    )
    assert _result_hour(result, 23).state == "unknown"
    assert result.unknown_minutes == 60


def test_continuous_darkness():
    hours = [_hour(DAY + timedelta(hours=index)) for index in range(24)]
    night = _night(
        sunset_utc=None,
        sunrise_utc=None,
        dark_intervals=[(DAY, DAY + timedelta(days=1))],
        hours=hours,
    )
    result = evaluate_night(night, _rules())
    assert result.verdict == "go"
    assert result.dark_minutes == 1440
    assert result.exposure == (DAY, DAY + timedelta(days=1))


def test_night_under_way():
    night = _set_hour(_night(now_utc=_at(23)), (19,), precip_probability_pct=20.0)
    result = evaluate_night(night, _rules())
    assert result.verdict == "go"
    assert result.evaluated_from_utc == _at(23)
    assert result.dark_minutes == 300
    elapsed = _result_hour(result, 19)
    assert elapsed.elapsed is True
    assert elapsed.excluded is False


def test_no_remaining_darkness_is_night_over():
    result = evaluate_night(_night(now_utc=_at(4, 30)), _rules())
    assert result.verdict == "night_over"
    assert result.reasons[0].code == "night_over"
    assert _result_hour(result, 3).elapsed is True
    assert _result_hour(result, 3).excluded is False
    assert _result_hour(result, 4).elapsed is False


def test_hours_not_covering_darkness_is_not_enough_data():
    result = evaluate_night(_night(hours=[_hour(_at(18))]), _rules())
    reason = result.reasons[0]
    assert result.verdict == "not_enough_data"
    assert (reason.code, reason.requirement, reason.start_utc) == (
        "missing_data",
        "cloud",
        _at(20),
    )


def test_gap_lower_bound_with_unknown():
    night = _set_model(_night(), "ecmwf_ifs025", (21,), cloud_total_pct=None)
    night = _set_model(night, "ecmwf_ifs025", (22, 23), cloud_total_pct=80.0)
    result = evaluate_night(night, _rules(max_cloudy_gap_hours=1.0))
    reason = result.reasons[0]
    assert result.verdict == "no"
    assert (reason.code, reason.value, reason.bound, reason.start_utc) == (
        "gap",
        2.0,
        "at_least",
        _at(22),
    )


def test_two_dark_intervals():
    hours = [_hour(DAY + timedelta(hours=index)) for index in range(24)]
    night = _night(
        sunset_utc=None,
        sunrise_utc=None,
        dark_intervals=[
            (DAY, DAY.replace(hour=12, minute=23)),
            (DAY.replace(hour=13, minute=33), DAY + timedelta(days=1)),
        ],
        hours=hours,
    )
    short = evaluate_night(night, _rules(session_style="short_session", short_session_hours=22.5))
    assert short.verdict == "no"
    assert short.reasons[0].code == "no_window"
    assert short.reasons[0].value == pytest.approx(22.45)
    all_night = evaluate_night(night, _rules())
    assert (all_night.verdict, all_night.dark_minutes) == ("go", 1370)


def test_imaging_until_marks_excluded():
    result = evaluate_night(
        replace(_night(), controls=NightControls(imaging_until_utc=_at(1))), _rules()
    )
    for hour in (1, 2, 3, 4, 5):
        item = _result_hour(result, hour)
        assert item.excluded is True
        assert item.elapsed is False


def test_conditions_cover_twilight_and_excluded_hours():
    night = replace(_night(), controls=NightControls(imaging_until_utc=_at(1)))
    night = _set_model(night, "ecmwf_ifs025", (19, 2), cloud_total_pct=90.0)
    night = _set_hour(night, (19,), precip_probability_pct=11.0)
    result = evaluate_night(night, _rules(wind_counted=True, wind_max_kmh=5.0))

    twilight = _result_hour(result, 19)
    assert twilight.dark_minutes == 0
    assert twilight.checks == {
        "cloud": "not_counted",
        "rain": "fail",
        "wind": "not_counted",
        "dew": "not_counted",
        "moon": "not_counted",
    }
    assert twilight.conditions == {
        "cloud": "fail",
        "rain": "fail",
        "wind": "fail",
        "dew": "not_counted",
        "moon": "not_counted",
    }

    after_stop = _result_hour(result, 2)
    assert after_stop.excluded is True
    assert after_stop.checks["cloud"] == "not_counted"
    assert after_stop.checks["rain"] == "pass"
    assert after_stop.conditions["cloud"] == "fail"
    assert after_stop.conditions["rain"] == "pass"

    dark = _result_hour(result, 21)
    assert dark.conditions == dark.checks


def test_single_model():
    result = evaluate_night(_night(), _rules())
    assert result.verdict != "uncertain"
    assert result.model_statuses == {"ecmwf_ifs025": "go"}
    assert result.requirements["models"] == "not_counted"


def test_comparisons_all_beyond_coverage_are_single_model():
    night = _night(comparison_models=("gfs_seamless", "icon_seamless"))
    for model in night.cloud_models[1:]:
        night = _set_model(
            night,
            model,
            tuple(range(24)),
            cloud_expected=False,
        )

    result = evaluate_night(night, _rules())

    assert result.model_statuses == {
        "ecmwf_ifs025": "go",
        "gfs_seamless": "not_expected",
        "icon_seamless": "not_expected",
    }
    assert result.requirements["models"] == "not_counted"


def test_short_session_models_agree_inside_window():
    night = _night(comparison_models=("gfs_seamless", "icon_seamless"))
    night = _set_model(night, "gfs_seamless", (20, 21, 0, 1, 2, 3), cloud_total_pct=90.0)
    night = _set_model(night, "icon_seamless", (20, 21, 0, 1, 2, 3), cloud_total_pct=90.0)
    night = _set_model(night, "ecmwf_ifs025", (2, 3), cloud_total_pct=90.0)
    result = evaluate_night(night, _rules(session_style="short_session"))
    assert (result.verdict, result.window) == ("go", (_at(22), _at(0)))


def test_reasons_primary_plus_blockers():
    night = _set_hour(
        _night(dark_intervals=[(_at(18), _at(4, 18))]),
        (18, 19, 20, 21, 22),
        precip_probability_pct=11.0,
    )
    night = _set_model(night, "ecmwf_ifs025", (18, 19, 20, 21, 22, 23, 0, 1), cloud_total_pct=90.0)
    result = evaluate_night(
        night,
        _rules(
            min_clear_fraction_pct=50,
            rain_max_probability_pct=10,
        ),
    )
    assert result.verdict == "no"
    assert [reason.code for reason in result.reasons[:2]] == ["rain", "clear_fraction"]


@pytest.mark.parametrize("model", ["ecmwf_ifs025", "gfs_seamless", "icon_seamless"])
def test_model_states_contain_expected_models_only(model: str):
    night = _set_model(
        _night(comparison_models=("gfs_seamless", "icon_seamless")),
        model,
        (22,),
        cloud_expected=False,
    )
    result = evaluate_night(night, _rules())
    assert model not in _result_hour(result, 22).model_states


def _majority_night(*, dark_end: int = 24, preferred: str = "ecmwf_ifs025") -> NightInput:
    end = _at(0) if dark_end == 24 else _at(dark_end)
    return _night(
        dark_intervals=[(_at(20), end)],
        cloud_models=("ecmwf_ifs025", "gfs_seamless", "icon_seamless"),
        preferred_model=preferred,
        combination="majority",
    )


def test_majority_needs_hourly_support_for_a_window():
    night = _majority_night()
    for model in ("ecmwf_ifs025", "gfs_seamless", "icon_seamless"):
        night = _set_model(night, model, (20, 21, 22, 23), cloud_total_pct=90.0)
    night = _set_model(night, "ecmwf_ifs025", (20, 21), cloud_total_pct=0.0)
    night = _set_model(night, "gfs_seamless", (22, 23), cloud_total_pct=0.0)
    result = evaluate_night(
        night,
        _rules(session_style="short_session", short_session_hours=2),
    )
    assert result.verdict == "no"


def test_majority_hourly_pattern_can_pass():
    night = _majority_night(dark_end=23)
    patterns = {
        "ecmwf_ifs025": ("pass", "pass", "fail"),
        "gfs_seamless": ("fail", "pass", "pass"),
        "icon_seamless": ("pass", "fail", "pass"),
    }
    for model, values in patterns.items():
        for hour, value in zip((20, 21, 22), values, strict=True):
            night = _set_model(
                night,
                model,
                (hour,),
                cloud_total_pct=0.0 if value == "pass" else 90.0,
            )
    result = evaluate_night(
        night,
        _rules(session_style="short_session", short_session_hours=3),
    )
    assert (result.verdict, result.clear_minutes) == ("go", 180)


def test_majority_window_never_starts_on_unreached_hours():
    night = _majority_night()
    for model in MODELS:
        night = _set_model(night, model, (20, 21), cloud_expected=False)

    result = evaluate_night(
        night,
        _rules(session_style="short_session", short_session_hours=2),
    )

    assert result.verdict == "go"
    assert result.window == (_at(22), _at(0))


def test_partial_reach_models_count_as_used():
    night = replace(
        _majority_night(dark_end=22),
        cloud_models=("ecmwf_ifs025", "gfs_seamless"),
    )
    night = _set_model(night, "ecmwf_ifs025", (21,), cloud_expected=False)
    night = _set_model(night, "gfs_seamless", (20,), cloud_expected=False)

    result = evaluate_night(night, _rules())

    assert result.cloud_models_used == ("ecmwf_ifs025", "gfs_seamless")
    assert result.default_cloud_used is False
    assert _is_single_model(result.cloud_combination, result.cloud_models_used) is False


def test_default_cloud_used_flag():
    night = _majority_night(dark_end=22)
    for model in night.cloud_models:
        night = _set_model(night, model, (20,), cloud_expected=False)

    result = evaluate_night(night, _rules())

    assert result.default_cloud_used is True


def test_majority_never_returns_uncertain():
    random = Random(20261018)
    for _ in range(200):
        night = _majority_night(dark_end=23)
        for model in ("ecmwf_ifs025", "gfs_seamless", "icon_seamless"):
            for hour in (20, 21, 22):
                value = random.choice((0.0, 90.0, None))
                night = _set_model(night, model, (hour,), cloud_total_pct=value)
        result = evaluate_night(
            night,
            _rules(session_style="short_session", short_session_hours=2),
        )
        assert result.verdict != "uncertain"
        assert not any(hour.disagrees for hour in result.hours)


def test_uncertain_mode_matches_previous_results():
    all_night = _night(comparison_models=("gfs_seamless", "icon_seamless"))
    all_night = _set_model(
        all_night,
        "gfs_seamless",
        (20, 21, 22, 23, 0, 1, 2, 3),
        cloud_total_pct=90.0,
    )
    assert evaluate_night(all_night, _rules()).verdict == "uncertain"

    short = _night(comparison_models=("gfs_seamless", "icon_seamless"))
    short = _set_model(short, "ecmwf_ifs025", (22, 23, 0, 1, 2, 3), cloud_total_pct=90)
    short = _set_model(short, "gfs_seamless", (20, 21, 0, 1, 2, 3), cloud_total_pct=90)
    short = _set_model(short, "icon_seamless", (20, 21, 22, 23, 2, 3), cloud_total_pct=90)
    result = evaluate_night(
        short,
        _rules(session_style="short_session", short_session_hours=2),
    )
    assert (result.verdict, result.reasons[0].code) == ("uncertain", "no_shared_window")


def test_preferred_beyond_reach_uses_next_ticked():
    night = _majority_night(dark_end=22, preferred="icon_seamless")
    night = _set_model(night, "icon_seamless", (20, 21), cloud_expected=False)
    night = _set_model(night, "gfs_seamless", (20, 21), cloud_total_pct=90.0)
    result = evaluate_night(
        night,
        _rules(session_style="short_session", short_session_hours=2),
    )
    assert (result.verdict, result.primary_model) == ("go", "ecmwf_ifs025")


def test_no_ticked_model_reaches_uses_fallback():
    night = _majority_night(dark_end=22)
    for model in ("ecmwf_ifs025", "gfs_seamless", "icon_seamless"):
        night = _set_model(night, model, (20, 21), cloud_expected=False)
    result = evaluate_night(
        night,
        _rules(session_style="short_session", short_session_hours=2),
    )
    assert (result.verdict, result.fallback, result.primary_model) == (
        "go",
        True,
        "best_match",
    )


def test_single_model_gfs_freshness_counts():
    night = replace(
        _majority_night(dark_end=22),
        cloud_models=("gfs_seamless",),
        preferred_model="gfs_seamless",
        stale_minutes={"forecast": None, "cloud_models": 61},
    )
    result = evaluate_night(
        night,
        _rules(session_style="short_session", short_session_hours=2),
    )
    assert (result.verdict, result.reasons[0].code) == ("not_enough_data", "stale")


def test_forecasts_differ_reason_counts():
    night = _majority_night(dark_end=23)
    night = _set_model(night, "gfs_seamless", (20, 21), cloud_total_pct=90.0)
    result = evaluate_night(
        night,
        _rules(session_style="short_session", short_session_hours=3),
    )
    reason = next(reason for reason in result.reasons if reason.code == "forecasts_differ")
    assert (result.differing_hours, result.compared_hours) == (2, 3)
    assert (reason.value, reason.limit) == (2.0, 3.0)
    assert result.requirements["models"] == "info"


def test_majority_models_not_counted_when_no_hour_compares_forecasts():
    night = _majority_night(dark_end=22)
    for model in ("gfs_seamless", "icon_seamless"):
        night = _set_model(night, model, (20, 21), cloud_expected=False)

    result = evaluate_night(night, _rules())

    assert result.compared_hours == 0
    assert result.requirements["models"] == "not_counted"


def test_majority_models_unknown_when_compared_vote_is_unknown():
    night = _majority_night(dark_end=22)
    night = _set_model(night, "icon_seamless", (20,), cloud_total_pct=None)

    result = evaluate_night(night, _rules())

    assert (result.differing_hours, result.compared_hours) == (0, 2)
    assert result.requirements["models"] == "unknown"


def test_majority_models_pass_when_known_votes_agree():
    result = evaluate_night(_majority_night(dark_end=22), _rules())

    assert (result.differing_hours, result.compared_hours) == (0, 2)
    assert result.requirements["models"] == "pass"
