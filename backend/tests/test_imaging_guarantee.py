"""Exhaustive monotonicity checks for the revised evaluator kernels."""

import copy
import json
import random
from datetime import UTC, datetime, timedelta
from itertools import product

import pytest

from nightcrate.services.forecast_inputs import build_hours
from nightcrate.services.imaging_hours import hour_state
from nightcrate.services.imaging_rules import PRESETS, ImagingRules
from nightcrate.services.imaging_session import Segment, model_status
from nightcrate.services.imaging_types import (
    HourInput,
    ModelHour,
    NightControls,
    NightInput,
)
from nightcrate.services.imaging_verdict import combine_all_night, evaluate_night
from nightcrate.services.weather import CloudModelData, parse_cloud_models, parse_hourly

START = datetime(2026, 10, 18, 0, tzinfo=UTC)
HOUR_STATES = ("clear", "not_clear", "unknown")
MODEL_STATUSES = ("go", "no", "unresolved", "not_expected")
MODELS = ("best_match", "ecmwf_ifs025", "gfs_seamless", "icon_seamless")


def _rules(**overrides: object) -> ImagingRules:
    values = PRESETS["left_out_all_night"][1].model_dump()
    values.update(overrides)
    return ImagingRules(**values)


def _segments(count: int) -> list[Segment]:
    return [
        Segment(START + timedelta(hours=index), START + timedelta(hours=index + 1), index)
        for index in range(count)
    ]


def _status(states: tuple[str, ...], rules: ImagingRules, segments: list[Segment]) -> str:
    return model_status(
        states,
        segments,
        rules,
        len(states) * 60,
        expected_missing="unknown" in states,
    )[0]


def _assert_status_erasure(before: str, after: str) -> None:
    assert not (before in {"no", "unresolved", "not_expected"} and after == "go")
    if before == "go":
        assert after in {"go", "unresolved"}
    elif before == "no":
        assert after in {"no", "unresolved"}


def _assert_verdict_erasure(before: str, after: str) -> None:
    assert not (before != "go" and after == "go")


def _expected_combination(primary: str, comparisons: tuple[str, str]) -> str:
    expected = tuple(status for status in comparisons if status != "not_expected")
    if primary == "unresolved":
        return "not_enough_data"
    if primary == "go":
        if "no" in expected:
            return "uncertain"
        return "not_enough_data" if "unresolved" in expected else "go"
    return "uncertain" if "go" in expected else "no"


def test_hour_checks_monotone():
    check_names = ("cloud", "rain", "wind", "dew", "moon")
    values = ("pass", "fail", "unknown")
    table = {
        assignment: hour_state(dict(zip(check_names, assignment, strict=True)), dark_minutes=60)
        for assignment in product(values, repeat=len(check_names))
    }
    for assignment, before in table.items():
        for index, value in enumerate(assignment):
            if value == "unknown":
                continue
            erased = (*assignment[:index], "unknown", *assignment[index + 1 :])
            after = table[erased]
            assert not (value == "fail" and after == "clear")
            assert not (before in {"not_clear", "unknown"} and after == "clear")


def test_session_kernel_8h_monotone():
    segments = _segments(8)
    assignments = tuple(product(HOUR_STATES, repeat=8))
    for gap_limit in (None, 1.0):
        rules = _rules(
            min_clear_fraction_pct=75,
            min_clear_hours=2,
            max_cloudy_gap_hours=gap_limit,
        )
        table = {assignment: _status(assignment, rules, segments) for assignment in assignments}
        assert len(table) == 6_561
        assert set(table.values()) == {"go", "no", "unresolved"}
        for assignment, before in table.items():
            for index, value in enumerate(assignment):
                if value == "unknown":
                    continue
                erased = (*assignment[:index], "unknown", *assignment[index + 1 :])
                _assert_status_erasure(before, table[erased])


def test_all_night_counts_reduction():
    rules = _rules(
        min_clear_fraction_pct=75,
        min_clear_hours=2,
        max_cloudy_gap_hours=None,
    )
    segments = _segments(8)
    classes = tuple(
        (clear, failed, 8 - clear - failed) for clear in range(9) for failed in range(9 - clear)
    )
    statuses = {
        counts: _status(
            ("clear",) * counts[0] + ("not_clear",) * counts[1] + ("unknown",) * counts[2],
            rules,
            segments,
        )
        for counts in classes
    }
    table = {
        assignment: combine_all_night(
            statuses[assignment[0]],
            {"gfs_seamless": statuses[assignment[1]], "icon_seamless": statuses[assignment[2]]},
        )
        for assignment in product(classes, repeat=3)
    }
    assert len(table) == 91_125
    assert set(statuses.values()) == {"go", "no", "unresolved"}
    assert set(table.values()) == {"go", "no", "uncertain", "not_enough_data"}

    for assignment, before in table.items():
        for model_index, counts in enumerate(assignment):
            for known_index in (0, 1):
                if counts[known_index] == 0:
                    continue
                erased_counts = list(counts)
                erased_counts[known_index] -= 1
                erased_counts[2] += 1
                erased_assignment = list(assignment)
                erased_assignment[model_index] = tuple(erased_counts)
                _assert_verdict_erasure(before, table[tuple(erased_assignment)])


def test_all_night_combiner_monotone():
    table = {
        (primary, gfs, icon): combine_all_night(
            primary,
            {"gfs_seamless": gfs, "icon_seamless": icon},
        )
        for primary in MODEL_STATUSES[:-1]
        for gfs in MODEL_STATUSES
        for icon in MODEL_STATUSES
    }
    for statuses, verdict in table.items():
        assert verdict == _expected_combination(statuses[0], statuses[1:])
    for statuses, before in table.items():
        for index, status in enumerate(statuses):
            if status not in {"go", "no"}:
                continue
            degraded = list(statuses)
            degraded[index] = "unresolved"
            _assert_verdict_erasure(before, table[tuple(degraded)])

    with pytest.raises(ValueError):
        combine_all_night("not_expected", {})


def _short_night(assignment: tuple[str, ...]) -> NightInput:
    models = ("ecmwf_ifs025", "gfs_seamless", "icon_seamless")
    hours = []
    for hour_index in range(3):
        model_hours = {}
        for model_index, model in enumerate(models):
            state = assignment[model_index * 3 + hour_index]
            total = 0.0 if state == "clear" else 100.0 if state == "not_clear" else None
            model_hours[model] = ModelHour(total, (0.0, 0.0, 0.0), 0.0, True, True)
        model_hours["best_match"] = ModelHour(0.0, (0.0, 0.0, 0.0), 0.0, True, True)
        hours.append(
            HourInput(
                start_utc=START + timedelta(hours=hour_index),
                models=model_hours,
                precip_probability_pct=0.0,
                precip_mm=0.0,
                wind_kmh=0.0,
                gust_kmh=0.0,
                temperature_c=10.0,
                dew_point_c=0.0,
                moon_altitude_deg=-10.0,
            )
        )
    return NightInput(
        sunset_utc=START,
        sunrise_utc=START + timedelta(hours=3),
        noon_start_utc=START - timedelta(hours=12),
        noon_end_utc=START + timedelta(hours=12),
        dark_intervals=[(START, START + timedelta(hours=3))],
        hours=hours,
        now_utc=START - timedelta(hours=1),
        controls=NightControls(),
        cloud_models=("ecmwf_ifs025", "gfs_seamless", "icon_seamless"),
        preferred_model="ecmwf_ifs025",
        combination="uncertain",
        fallback_model="best_match",
        stale_minutes={"forecast": None, "cloud_models": None},
    )


def test_short_session_guarantee_exhaustive():
    rules = _rules(
        session_style="short_session",
        short_session_hours=2,
        rain_policy="hours_lost",
        wind_counted=False,
    )
    assignments = tuple(product(HOUR_STATES, repeat=9))
    table = {
        assignment: evaluate_night(_short_night(assignment), rules).verdict
        for assignment in assignments
    }
    assert len(table) == 19_683
    assert set(table.values()) == {"go", "no", "uncertain", "not_enough_data"}

    edges = 0
    for assignment, before in table.items():
        for index, value in enumerate(assignment):
            if value == "unknown":
                continue
            erased = (*assignment[:index], "unknown", *assignment[index + 1 :])
            _assert_verdict_erasure(before, table[erased])
            edges += 1
    assert edges == 118_098


def _raw_case(case_index: int) -> dict:
    times = [int((START + timedelta(hours=index)).timestamp()) for index in range(4)]
    outcome = case_index % 4
    clear = [0.0, 0.0, 0.0, 0.0]
    failed = [100.0, 100.0, 100.0, 100.0]
    primary = failed if outcome == 1 else clear
    gfs = failed if outcome in {1, 2} else [None] * 4 if outcome == 3 else clear
    icon = failed if outcome in {1, 2} else clear
    chance = [0.0, 20.0 if case_index % 9 == 0 else 0.0, 0.0, 0.0]
    main = {
        "time": times,
        "cloud_cover": list(primary),
        "cloud_cover_low": [0.0] * 4,
        "cloud_cover_mid": [0.0] * 4,
        "cloud_cover_high": [0.0] * 4,
        "precipitation": [0.0] * 4,
        "precipitation_probability": chance,
        "wind_speed_10m": [5.0] * 4,
        "wind_gusts_10m": [8.0] * 4,
        "temperature_2m": [10.0] * 4,
        "dew_point_2m": [2.0] * 4,
    }
    cloud = {"time": times}
    for model, totals in (
        ("ecmwf_ifs025", primary),
        ("gfs_seamless", gfs),
        ("icon_seamless", icon),
    ):
        cloud[f"cloud_cover_{model}"] = list(totals)
        cloud[f"precipitation_{model}"] = [0.0] * 4
    return {"main": main, "cloud": cloud}


def _evaluate_raw(raw: dict, case_index: int) -> tuple[str, list[HourInput], str]:
    hourly = parse_hourly(raw["main"], "forecast")
    models = parse_cloud_models(
        raw["cloud"],
        ("ecmwf_ifs025", "gfs_seamless", "icon_seamless"),
    )
    cloud = CloudModelData(models=models, raw_json=json.dumps(raw["cloud"]))
    expected = {model: START + timedelta(hours=3) for model in MODELS}
    if case_index % 10 == 0:
        expected["icon_seamless"] = START + timedelta(hours=1)
    if case_index % 20 == 0:
        expected["ecmwf_ifs025"] = START - timedelta(hours=1)
    hours = build_hours(
        hourly,
        cloud,
        {},
        START,
        START + timedelta(hours=3),
        expected=expected,
    )
    selections = (
        ("ecmwf_ifs025",),
        ("gfs_seamless",),
        ("icon_seamless",),
        ("ecmwf_ifs025", "gfs_seamless"),
        ("ecmwf_ifs025", "icon_seamless"),
        ("gfs_seamless", "icon_seamless"),
        ("ecmwf_ifs025", "gfs_seamless", "icon_seamless"),
    )
    selected = selections[case_index % len(selections)]
    preferred = selected[(case_index // len(selections)) % len(selected)]
    combination = "majority" if case_index % 2 else "uncertain"
    rules = _rules(
        session_style="short_session",
        short_session_hours=2,
        rain_policy="night_off" if case_index % 2 else "hours_lost",
        rain_forecasts="any_model" if case_index % 3 == 0 else "main",
        rain_max_probability_pct=10,
        wind_counted=False,
        cloud_use_ecmwf="ecmwf_ifs025" in selected,
        cloud_use_gfs="gfs_seamless" in selected,
        cloud_use_icon="icon_seamless" in selected,
        cloud_preferred_model=preferred,
        cloud_combination=combination,
    )
    dark_intervals = [(START, START + timedelta(hours=3))]
    if case_index % 11 == 0:
        dark_intervals = [
            (START, START + timedelta(hours=1)),
            (START + timedelta(hours=1, minutes=30), START + timedelta(hours=3)),
        ]
    noon_hours = 23 if case_index % 13 == 0 else 25 if case_index % 17 == 0 else 24
    result = evaluate_night(
        NightInput(
            sunset_utc=START,
            sunrise_utc=START + timedelta(hours=3),
            noon_start_utc=START - timedelta(hours=12),
            noon_end_utc=START - timedelta(hours=12) + timedelta(hours=noon_hours),
            dark_intervals=dark_intervals,
            hours=hours,
            now_utc=START - timedelta(hours=1),
            controls=NightControls(),
            cloud_models=selected,
            preferred_model=preferred,
            combination=combination,
            fallback_model="best_match",
            stale_minutes={
                "forecast": 480 if case_index % 47 == 0 else None,
                "cloud_models": 480 if case_index % 53 == 0 else None,
            },
        ),
        rules,
    )
    return result.verdict, hours, combination


def _erase_raw(raw: dict, rng: random.Random) -> str:
    choices = ["chance", "amount", "wind", "ecmwf", "gfs", "icon"]
    target = rng.choice(choices)
    index = rng.randrange(3)
    if target == "chance":
        raw["main"]["precipitation_probability"][index + 1] = None
    elif target == "amount":
        raw["main"]["precipitation"][index + 1] = None
    elif target == "wind":
        raw["main"]["wind_speed_10m"][index] = None
    elif target in {"ecmwf", "gfs"}:
        model = "ecmwf_ifs025" if target == "ecmwf" else "gfs_seamless"
        raw["cloud"][f"cloud_cover_{model}"][index] = None
    elif target == "icon":
        for key in tuple(raw["cloud"]):
            if key.endswith("_icon_seamless"):
                del raw["cloud"][key]
    return target


def test_end_to_end_seeded():
    for seed in range(1, 5):
        rng = random.Random(seed)
        counts = {"go": 0, "no": 0, "uncertain": 0, "not_enough_data": 0}
        majority_counts = {"go": 0, "no": 0}
        counted_erasures = 0
        for case_index in range(2_500):
            raw = _raw_case(case_index)
            before, before_hours, combination = _evaluate_raw(raw, case_index)
            counts[before] += 1
            if combination == "majority" and before in majority_counts:
                majority_counts[before] += 1
            erased = copy.deepcopy(raw)
            target = _erase_raw(erased, rng)
            after, after_hours, _ = _evaluate_raw(erased, case_index)
            if target != "wind" and before_hours != after_hours:
                counted_erasures += 1
            assert not (before != "go" and after == "go"), (
                seed,
                case_index,
                target,
                before,
                after,
            )
        assert counts["go"] >= 375, (seed, counts)
        assert counts["no"] >= 375, (seed, counts)
        assert counts["uncertain"] >= 125, (seed, counts)
        assert majority_counts["go"] >= 1, (seed, majority_counts)
        assert majority_counts["no"] >= 1, (seed, majority_counts)
        assert counted_erasures >= 1_250, (seed, counted_erasures)
