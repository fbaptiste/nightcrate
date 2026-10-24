"""Night-level imaging verdicts from declared forecast evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Literal

from nightcrate.services.imaging_hours import (
    conditions,
    hour_state,
    precipitation_checks,
)
from nightcrate.services.imaging_rules import CLOUD_MODEL_ORDER, ImagingRules
from nightcrate.services.imaging_session import (
    Segment,
    SessionPass,
    decide_cloud,
    joint_states,
    model_status,
    shared_window,
)
from nightcrate.services.imaging_types import (
    CheckState,
    CoverageNote,
    HourInput,
    HourResult,
    HourState,
    ModelStatus,
    NightInput,
    NightResult,
    Reason,
    Verdict,
    WindowStatus,
)

_HOUR = timedelta(hours=1)
_CHECK_ORDER = ("cloud", "rain", "wind", "dew", "moon")


@dataclass(frozen=True)
class _ModelEvaluation:
    status: ModelStatus
    pessimistic: SessionPass
    optimistic: SessionPass
    expected_missing_minutes: float


@dataclass
class _HourWork:
    source: HourInput
    dark_minutes: float
    exposure_minutes: float
    elapsed: bool
    excluded: bool
    display_conditions: dict[str, dict[str, CheckState]]
    display_checks: dict[str, dict[str, CheckState]]
    session_checks: dict[str, dict[str, CheckState]]
    display_states: dict[str, HourState]
    session_states: dict[str, HourState]


def combine_all_night(primary: ModelStatus, comparisons: Mapping[str, ModelStatus]) -> Verdict:
    """Combine established all-night model statuses using §5.6."""
    if primary == "not_expected":
        raise ValueError("the primary model must be resolved or replaced by the fallback")
    if primary == "unresolved":
        return "not_enough_data"

    expected = tuple(status for status in comparisons.values() if status != "not_expected")
    if primary == "go":
        if "no" in expected:
            return "uncertain"
        if "unresolved" in expected:
            return "not_enough_data"
        return "go"
    return "uncertain" if "go" in expected else "no"


def combine_short_session(
    primary: ModelStatus,
    window: WindowStatus,
    comparisons: Mapping[str, ModelStatus],
) -> Verdict:
    """Combine short-session evidence using the two §5.5 tables."""
    if primary == "not_expected":
        raise ValueError("the primary model must be resolved or replaced by the fallback")
    if primary == "unresolved":
        return "not_enough_data"
    expected = tuple(status for status in comparisons.values() if status != "not_expected")
    if primary == "no":
        return "uncertain" if "go" in expected else "no"
    if window == "established":
        return "go"
    if window == "impossible":
        return "uncertain"
    return "not_enough_data"


def apply_precedence(
    cloud: Verdict,
    *,
    precipitation_veto: bool,
    precipitation_unknown: bool,
    stale: bool,
) -> Verdict:
    """Apply night-level precipitation and freshness precedence."""
    if precipitation_veto:
        result: Verdict = "no"
    elif precipitation_unknown and cloud in {"go", "uncertain"}:
        result = "not_enough_data"
    else:
        result = cloud
    if stale and result in {"go", "uncertain", "not_enough_data"}:
        return "not_enough_data"
    return result


def _overlap(
    start: datetime,
    end: datetime,
    other_start: datetime,
    other_end: datetime,
) -> float:
    return max(0.0, (min(end, other_end) - max(start, other_start)).total_seconds() / 60.0)


def _segments_for_hour(
    start: datetime,
    end: datetime,
    dark_intervals: Sequence[tuple[datetime, datetime]],
    imaging_start: datetime,
    imaging_end: datetime,
    hour_index: int,
) -> list[Segment]:
    result: list[Segment] = []
    for dark_start, dark_end in dark_intervals:
        segment_start = max(start, dark_start, imaging_start)
        segment_end = min(end, dark_end, imaging_end)
        if segment_start < segment_end:
            result.append(Segment(segment_start, segment_end, hour_index))
    return result


def _aggregate(states: Sequence[CheckState]) -> CheckState:
    if "fail" in states:
        return "fail"
    if "unknown" in states:
        return "unknown"
    if states:
        return "pass"
    return "not_counted"


def _condition_checks_for_model(
    hour: HourInput,
    rules: ImagingRules,
    model: str,
) -> dict[str, CheckState]:
    return conditions(hour, rules, model)


def _counted_checks(
    condition_checks: Mapping[str, CheckState],
    *,
    rain: CheckState,
    dark_minutes: float,
    rain_minutes: float,
) -> dict[str, CheckState]:
    checks = dict(condition_checks)
    if dark_minutes <= 0:
        checks.update(
            cloud="not_counted",
            wind="not_counted",
            dew="not_counted",
            moon="not_counted",
        )
    checks["rain"] = rain if rain_minutes > 0 else "not_counted"
    return checks


def _reason_for_gap(
    run: tuple[datetime, datetime],
    works: Sequence[_HourWork],
    model: str,
) -> str:
    counts = {name: 0 for name in _CHECK_ORDER}
    for work in works:
        if work.source.start_utc + _HOUR <= run[0] or work.source.start_utc >= run[1]:
            continue
        for name in _CHECK_ORDER:
            if work.session_checks[model][name] == "fail":
                counts[name] += 1
    most = max(counts.values())
    if most == 0:
        return "unknown"
    return next(name for name in _CHECK_ORDER if counts[name] == most)


def _with_gap_requirement(
    session: SessionPass,
    works: Sequence[_HourWork],
    model: str,
) -> Reason:
    reason = session.reason
    if reason.code == "clear_with_gaps" and session.longest_gap is not None:
        return replace(reason, requirement=_reason_for_gap(session.longest_gap, works, model))
    return reason


def _bounded(reason: Reason, unknown_minutes: float) -> Reason:
    if unknown_minutes <= 0:
        return reason
    if reason.code in {"clear_fraction", "min_hours", "no_window"}:
        return replace(reason, bound="at_most")
    if reason.code == "gap":
        return replace(reason, bound="at_least")
    return reason


def _model_evaluation(
    model: str,
    states: Sequence[HourState],
    expected: Sequence[bool],
    works: Sequence[_HourWork],
    segments: Sequence[Segment],
    rules: ImagingRules,
    dark_minutes: float,
) -> _ModelEvaluation:
    expected_missing_minutes = sum(
        (segment.end - segment.start).total_seconds() / 60.0
        for segment in segments
        if states[segment.hour_index] == "unknown"
        and (
            (
                expected[segment.hour_index]
                and works[segment.hour_index].session_checks[model]["cloud"] == "unknown"
            )
            or any(
                works[segment.hour_index].session_checks[model][name] == "unknown"
                for name in ("rain", "wind", "dew", "moon")
            )
        )
    )
    status, pessimistic, optimistic = model_status(
        states,
        segments,
        rules,
        dark_minutes,
        expected_missing=expected_missing_minutes > 0,
    )
    return _ModelEvaluation(status, pessimistic, optimistic, expected_missing_minutes)


def _model_incomplete_reason(model: str, evaluation: _ModelEvaluation) -> Reason:
    return Reason(
        code="model_incomplete",
        model=model,
        missing_hours=evaluation.expected_missing_minutes / 60.0,
    )


def _coverage_end(hours: Sequence[HourInput], model: str) -> datetime | None:
    return max(
        (
            hour.start_utc
            for hour in hours
            if model in hour.models and hour.models[model].cloud_expected
        ),
        default=None,
    )


def _precipitation_reasons(
    works: Sequence[_HourWork],
    rules: ImagingRules,
    *,
    use_exposure: bool,
) -> tuple[list[Reason], list[Reason]]:
    failures: list[Reason] = []
    missing: list[Reason] = []
    check_names = ["chance", "amount"]
    if rules.rain_forecasts == "any_model":
        check_names.extend(
            f"amount:{model}"
            for model in sorted(
                {model for work in works for model in work.source.models if model != "best_match"}
            )
        )

    for check_name in check_names:
        applicable = []
        for work in works:
            minutes = work.exposure_minutes if use_exposure else work.dark_minutes
            checks = precipitation_checks(work.source, rules)
            if minutes > 0 and check_name in checks:
                applicable.append((work, checks[check_name]))
        failed = [(work, state) for work, state in applicable if state == "fail"]
        unknown = [(work, state) for work, state in applicable if state == "unknown"]
        model = check_name.removeprefix("amount:") if check_name.startswith("amount:") else None

        if failed:
            grouped = [failed[0][0]]
            for work, _ in failed[1:]:
                if work.source.start_utc == grouped[-1].source.start_utc + _HOUR:
                    grouped.append(work)
                else:
                    break
            start = grouped[0].source.start_utc
            end = grouped[-1].source.start_utc + _HOUR
            if check_name == "chance":
                values = [
                    work.source.precip_probability_pct
                    for work in grouped
                    if work.source.precip_probability_pct is not None
                ]
                failures.append(
                    Reason(
                        code="rain",
                        start_utc=start,
                        end_utc=end,
                        value=max(values),
                        limit=rules.rain_max_probability_pct,
                    )
                )
            else:
                values = [
                    (
                        work.source.precip_mm
                        if model is None
                        else work.source.models[model].precip_mm
                    )
                    for work in grouped
                ]
                failures.append(
                    Reason(
                        code="rain_amount" if model is None else "rain_model_amount",
                        start_utc=start,
                        end_utc=end,
                        value=max(value for value in values if value is not None),
                        limit=rules.rain_amount_threshold_mm,
                        model=model,
                    )
                )

        if unknown:
            minutes = sum(
                work.exposure_minutes if use_exposure else work.dark_minutes for work, _ in unknown
            )
            missing.append(
                Reason(
                    code="rain_missing",
                    start_utc=unknown[0][0].source.start_utc,
                    end_utc=unknown[-1][0].source.start_utc + _HOUR,
                    model=model,
                    missing_hours=minutes / 60.0,
                )
            )
    return failures, missing


def _layer_advisory(
    works: Sequence[_HourWork],
    segments: Sequence[Segment],
    rules: ImagingRules,
    primary_model: str,
    *,
    fallback: bool,
    night_over: bool,
) -> Reason | None:
    if fallback or night_over or primary_model != "ecmwf_ifs025":
        return None
    names = ("low", "mid", "high")
    candidates: list[tuple[int, int, float]] = []
    for hour_index, work in enumerate(works):
        model = work.source.models.get(primary_model)
        if work.dark_minutes <= 0 or model is None or not model.cloud_expected:
            continue
        if model.cloud_total_pct is None or model.cloud_total_pct > rules.cloud_max_pct:
            continue
        for index, layer in enumerate(model.cloud_layers_pct):
            if layer is not None and layer > rules.cloud_max_pct:
                candidates.append((hour_index, index, layer))
    if not candidates:
        return None
    _, peak_index, peak = max(candidates, key=lambda item: item[2])
    hour_indexes = {hour_index for hour_index, index, _ in candidates if index == peak_index}
    layer_segments = [segment for segment in segments if segment.hour_index in hour_indexes]
    return Reason(
        code="layer_advisory",
        start_utc=layer_segments[0].start,
        end_utc=layer_segments[-1].end,
        value=peak,
        limit=rules.cloud_max_pct,
        requirement=names[peak_index],
    )


def _empty_session() -> SessionPass:
    return SessionPass(False, Reason(code="no_dark_time"), 0.0, None, None)


def evaluate_night(night: NightInput, rules: ImagingRules) -> NightResult:
    """Evaluate one noon-to-noon night following Task 5's ordered algorithm."""
    natural_start = (night.sunset_utc or night.noon_start_utc) - timedelta(
        minutes=rules.gear_out_before_sunset_min if night.sunset_utc is not None else 0
    )
    natural_end = (night.sunrise_utc or night.noon_end_utc) + timedelta(
        minutes=rules.gear_out_after_sunrise_min if night.sunrise_utc is not None else 0
    )
    controls = night.controls
    raw_exposure = (
        (
            controls.gear_out_utc or natural_start,
            controls.gear_in_utc or natural_end,
        )
        if rules.rain_policy == "night_off"
        else None
    )
    raw_imaging_start = controls.imaging_from_utc or (
        raw_exposure[0] if raw_exposure is not None else night.noon_start_utc
    )
    raw_imaging_end = controls.imaging_until_utc or (
        raw_exposure[1] if raw_exposure is not None else night.noon_end_utc
    )
    imaging_start = max(raw_imaging_start, night.now_utc)
    imaging_end = raw_imaging_end
    remaining_dark = [
        (max(start, imaging_start), min(end, imaging_end))
        for start, end in night.dark_intervals
        if max(start, imaging_start) < min(end, imaging_end)
    ]
    geometric_dark_minutes = sum(
        (end - start).total_seconds() / 60.0 for start, end in remaining_dark
    )
    exposure = (
        (max(raw_exposure[0], night.now_utc), raw_exposure[1]) if raw_exposure is not None else None
    )
    night_over = imaging_start >= imaging_end or (
        bool(night.dark_intervals) and night.now_utc >= night.dark_intervals[-1][1]
    )
    evaluated_from = night.now_utc if night.now_utc > raw_imaging_start else None

    selected_models = night.cloud_models
    tie_order = tuple(
        dict.fromkeys(
            (
                night.preferred_model,
                *(model for model in CLOUD_MODEL_ORDER if model in selected_models),
            )
        )
    )
    models = tuple(dict.fromkeys((*selected_models, night.fallback_model)))
    segments: list[Segment] = []
    works: list[_HourWork] = []
    state_lists: dict[str, list[HourState]] = {model: [] for model in models}
    expected_lists: dict[str, list[bool]] = {model: [] for model in models}

    for index, source in enumerate(night.hours):
        hour_end = source.start_utc + _HOUR
        hour_segments = _segments_for_hour(
            source.start_utc,
            hour_end,
            night.dark_intervals,
            imaging_start,
            imaging_end,
            index,
        )
        segments.extend(hour_segments)
        dark_minutes = sum(
            (segment.end - segment.start).total_seconds() / 60.0 for segment in hour_segments
        )
        exposure_minutes = (
            _overlap(source.start_utc, hour_end, *exposure) if exposure is not None else 0.0
        )
        rain_minutes = exposure_minutes if rules.rain_policy == "night_off" else dark_minutes
        rain_state = _aggregate(tuple(precipitation_checks(source, rules).values()))
        display_conditions: dict[str, dict[str, CheckState]] = {}
        display_checks: dict[str, dict[str, CheckState]] = {}
        session_checks: dict[str, dict[str, CheckState]] = {}
        display_states: dict[str, HourState] = {}
        session_states: dict[str, HourState] = {}
        for model_name in models:
            model = source.models[model_name]
            condition = _condition_checks_for_model(source, rules, model_name)
            display = _counted_checks(
                condition,
                rain=rain_state,
                dark_minutes=dark_minutes,
                rain_minutes=rain_minutes,
            )
            session = dict(display)
            if rules.rain_policy == "night_off":
                session["rain"] = "not_counted"
            if dark_minutes > 0 and not model.cloud_expected:
                session["cloud"] = "unknown"
                display["cloud"] = "unknown"
            display_conditions[model_name] = condition
            display_checks[model_name] = display
            session_checks[model_name] = session
            display_states[model_name] = hour_state(display, dark_minutes=dark_minutes)
            state = hour_state(session, dark_minutes=dark_minutes)
            session_states[model_name] = state
            state_lists[model_name].append(state)
            expected_lists[model_name].append(model.cloud_expected)
        works.append(
            _HourWork(
                source,
                dark_minutes,
                exposure_minutes,
                hour_end <= night.now_utc,
                hour_end <= raw_imaging_start or source.start_utc >= raw_imaging_end,
                display_conditions,
                display_checks,
                session_checks,
                display_states,
                session_states,
            )
        )

    segments.sort(key=lambda item: item.start)
    dark_minutes = sum((item.end - item.start).total_seconds() / 60.0 for item in segments)
    evaluations: dict[str, _ModelEvaluation] = {}
    if dark_minutes > 0:
        evaluations = {
            model: _model_evaluation(
                model,
                state_lists[model],
                expected_lists[model],
                works,
                segments,
                rules,
                dark_minutes,
            )
            for model in selected_models
        }

    cloud_combination = "single" if len(selected_models) == 1 else night.combination
    use_decided_sequence = cloud_combination in {"majority", "single"}
    cloud_models_used = tuple(
        model
        for model in selected_models
        if any(
            work.dark_minutes > 0 and not work.excluded and work.source.models[model].cloud_expected
            for work in works
        )
    )
    default_cloud_used = False
    fallback = False
    actual_primary = tie_order[0]
    evaluation_key = actual_primary
    comparisons: tuple[str, ...] = ()
    comparison_evaluations: dict[str, _ModelEvaluation] = {}
    expected_comparisons: dict[str, ModelStatus] = {}
    fallback_evaluation: _ModelEvaluation | None = None

    differing_hours = 0
    compared_hours = 0
    compared_unknown = False
    if use_decided_sequence:
        reached_models = {
            model
            for work in works
            if work.dark_minutes > 0
            for model in selected_models
            if work.source.models[model].cloud_expected
        }
        actual_primary = next(
            (model for model in tie_order if model in reached_models),
            night.fallback_model if dark_minutes > 0 else tie_order[0],
        )
        fallback = actual_primary == night.fallback_model
        evaluation_key = "__decided__"
        state_lists[evaluation_key] = []
        expected_lists[evaluation_key] = []
        for work in works:
            voters = {
                model: work.display_conditions[model]["cloud"]
                for model in selected_models
                if work.source.models[model].cloud_expected
            }
            known = {state for state in voters.values() if state in {"pass", "fail"}}
            if work.dark_minutes > 0 and not work.excluded and len(voters) >= 2:
                compared_hours += 1
                compared_unknown = compared_unknown or "unknown" in voters.values()
                if len(known) == 2:
                    differing_hours += 1
            fallback_expected = work.source.models[night.fallback_model].cloud_expected
            if voters:
                cloud = decide_cloud(voters, tie_order)
                expected = True
            elif fallback_expected:
                cloud = work.display_conditions[night.fallback_model]["cloud"]
                expected = True
                if work.dark_minutes > 0 and not work.excluded:
                    default_cloud_used = True
                    fallback = True
            else:
                cloud = "unknown"
                expected = False

            base_model = (
                actual_primary
                if actual_primary in work.display_conditions
                else night.fallback_model
            )
            display_condition = dict(work.display_conditions[base_model])
            display_condition["cloud"] = cloud
            display = dict(work.display_checks[base_model])
            session = dict(work.session_checks[base_model])
            display["cloud"] = cloud if work.dark_minutes > 0 else "not_counted"
            session["cloud"] = cloud if work.dark_minutes > 0 else "not_counted"
            work.display_conditions[evaluation_key] = display_condition
            work.display_checks[evaluation_key] = display
            work.session_checks[evaluation_key] = session
            work.display_states[evaluation_key] = hour_state(
                display, dark_minutes=work.dark_minutes
            )
            session_state = hour_state(session, dark_minutes=work.dark_minutes)
            work.session_states[evaluation_key] = session_state
            state_lists[evaluation_key].append(session_state)
            expected_lists[evaluation_key].append(expected)

        if dark_minutes > 0:
            primary_evaluation = _model_evaluation(
                evaluation_key,
                state_lists[evaluation_key],
                expected_lists[evaluation_key],
                works,
                segments,
                rules,
                dark_minutes,
            )
        else:
            primary_evaluation = _ModelEvaluation(
                "unresolved", _empty_session(), _empty_session(), 0.0
            )
    else:
        actual_primary = next(
            (
                model
                for model in tie_order
                if model in evaluations and evaluations[model].status != "not_expected"
            ),
            night.fallback_model if dark_minutes > 0 else tie_order[0],
        )
        evaluation_key = actual_primary
        fallback = actual_primary == night.fallback_model
        if fallback:
            if dark_minutes > 0:
                fallback_evaluation = _model_evaluation(
                    night.fallback_model,
                    state_lists[night.fallback_model],
                    expected_lists[night.fallback_model],
                    works,
                    segments,
                    rules,
                    dark_minutes,
                )
            comparisons = ()
        else:
            comparisons = tuple(model for model in selected_models if model != actual_primary)
            comparison_evaluations = {model: evaluations[model] for model in comparisons}
            expected_comparisons = {
                model: evaluation.status
                for model, evaluation in comparison_evaluations.items()
                if evaluation.status != "not_expected"
            }
        primary_evaluation = (
            fallback_evaluation
            if fallback_evaluation is not None
            else evaluations.get(
                actual_primary,
                _ModelEvaluation("unresolved", _empty_session(), _empty_session(), 0.0),
            )
        )
        default_cloud_used = fallback

    if fallback and fallback_evaluation is None and dark_minutes > 0:
        fallback_evaluation = _model_evaluation(
            night.fallback_model,
            state_lists[night.fallback_model],
            expected_lists[night.fallback_model],
            works,
            segments,
            rules,
            dark_minutes,
        )
    statuses = {model: evaluation.status for model, evaluation in evaluations.items()}
    if fallback and fallback_evaluation is not None:
        statuses[night.fallback_model] = fallback_evaluation.status
    reason_statuses = {actual_primary: primary_evaluation.status, **expected_comparisons}

    early_reason: Reason | None = None
    early_verdict: Verdict | None = None
    if night_over:
        early_verdict, early_reason = "night_over", Reason(code="night_over")
    elif not night.dark_intervals:
        early_verdict, early_reason = "no", Reason(code="never_dark")
    elif geometric_dark_minutes <= 0:
        early_verdict, early_reason = (
            "no",
            Reason(code="no_dark_time", start_utc=raw_imaging_end),
        )

    missing_dark_inputs = early_verdict is None and geometric_dark_minutes > 0 and dark_minutes <= 0

    window: tuple[datetime, datetime] | None = None
    window_status: WindowStatus = "impossible"
    if early_verdict is not None:
        cloud_verdict = early_verdict
        cloud_reason = early_reason
    elif missing_dark_inputs:
        cloud_verdict = "not_enough_data"
        cloud_reason = Reason(
            code="missing_data",
            start_utc=remaining_dark[0][0],
            requirement="cloud",
        )
    elif primary_evaluation.status in {"unresolved", "not_expected"}:
        cloud_verdict = "not_enough_data"
        cloud_reason = _model_incomplete_reason(actual_primary, primary_evaluation)
    elif rules.session_style == "short_session":
        if use_decided_sequence:
            joint = state_lists[evaluation_key]
        else:
            expected_models = (evaluation_key, *comparisons)
            joint = joint_states(
                {model: state_lists[model] for model in expected_models},
                {model: expected_lists[model] for model in expected_models},
            )
        window_status, window = shared_window(
            joint,
            segments,
            rules.short_session_hours * 60.0,
        )
        cloud_verdict = combine_short_session(
            primary_evaluation.status,
            window_status,
            {model: value.status for model, value in comparison_evaluations.items()},
        )
        if primary_evaluation.status == "no":
            cloud_reason = _bounded(
                primary_evaluation.optimistic.reason,
                primary_evaluation.expected_missing_minutes,
            )
        elif window_status == "established" and window is not None:
            cloud_reason = Reason(code="short_window", start_utc=window[0], end_utc=window[1])
        elif window_status == "impossible":
            cloud_reason = (
                primary_evaluation.optimistic.reason
                if use_decided_sequence
                else Reason(code="no_shared_window", limit=rules.short_session_hours)
            )
        else:
            incomplete = next(
                (
                    (model, evaluation)
                    for model, evaluation in comparison_evaluations.items()
                    if evaluation.status == "unresolved"
                ),
                (actual_primary, primary_evaluation),
            )
            cloud_reason = _model_incomplete_reason(*incomplete)
    else:
        cloud_verdict = combine_all_night(
            primary_evaluation.status,
            {model: value.status for model, value in comparison_evaluations.items()},
        )
        if cloud_verdict == "uncertain":
            cloud_reason = Reason(code="models_disagree", models=reason_statuses)
        elif cloud_verdict == "not_enough_data" and primary_evaluation.status != "unresolved":
            incomplete = next(
                (item for item in comparison_evaluations.items() if item[1].status == "unresolved"),
                (actual_primary, primary_evaluation),
            )
            cloud_reason = _model_incomplete_reason(*incomplete)
        elif primary_evaluation.status == "go":
            cloud_reason = _with_gap_requirement(
                primary_evaluation.pessimistic, works, evaluation_key
            )
        elif primary_evaluation.status == "no":
            cloud_reason = _bounded(
                primary_evaluation.optimistic.reason,
                primary_evaluation.expected_missing_minutes,
            )
        else:
            cloud_reason = _model_incomplete_reason(actual_primary, primary_evaluation)

    disagreement = not use_decided_sequence and (
        cloud_verdict == "uncertain"
        or (
            primary_evaluation.status in {"go", "no"}
            and any(
                status in {"go", "no"} and status != primary_evaluation.status
                for status in expected_comparisons.values()
            )
        )
    )
    disagreement_reason = (
        Reason(code="models_disagree", models=reason_statuses) if disagreement else None
    )

    precip_failures: list[Reason] = []
    precip_missing: list[Reason] = []
    if early_verdict is None:
        precip_failures, precip_missing = _precipitation_reasons(
            works,
            rules,
            use_exposure=rules.rain_policy == "night_off",
        )
    precipitation_veto = rules.rain_policy == "night_off" and bool(precip_failures)
    precipitation_unknown = rules.rain_policy == "night_off" and bool(precip_missing)

    comparison_expected = not fallback and any(
        work.dark_minutes > 0
        and any(work.source.models[model].cloud_expected for model in comparisons)
        for work in works
    )
    selected_cloud_used = any(
        work.dark_minutes > 0
        and any(work.source.models[model].cloud_expected for model in selected_models)
        for work in works
    )
    amount_expected = rules.rain_forecasts == "any_model" and any(
        (work.exposure_minutes if rules.rain_policy == "night_off" else work.dark_minutes) > 0
        and any(
            model != "best_match" and value.amount_expected
            for model, value in work.source.models.items()
        )
        for work in works
    )
    cloud_freshness_counts = selected_cloud_used or comparison_expected or amount_expected
    stale_values = [night.stale_minutes.get("forecast")]
    if cloud_freshness_counts:
        stale_values.append(night.stale_minutes.get("cloud_models"))
    stale_age = max((value for value in stale_values if value is not None), default=None)
    stale = early_verdict is None and stale_age is not None
    verdict = (
        early_verdict
        if early_verdict is not None
        else apply_precedence(
            cloud_verdict,
            precipitation_veto=precipitation_veto,
            precipitation_unknown=precipitation_unknown,
            stale=stale,
        )
    )

    reasons: list[Reason]
    if early_reason is not None:
        reasons = [early_reason]
    elif precipitation_veto:
        reasons = [precip_failures[0]]
        if disagreement_reason is not None:
            reasons.append(disagreement_reason)
        reasons.extend(precip_failures[1:])
        if cloud_verdict in {"no", "not_enough_data"}:
            reasons.append(cloud_reason)
        reasons.extend(precip_missing)
    elif precipitation_unknown and cloud_verdict in {"go", "uncertain"}:
        reasons = [precip_missing[0]]
        if disagreement_reason is not None:
            reasons.append(disagreement_reason)
        reasons.extend(precip_missing[1:])
    else:
        reasons = [cloud_reason]
        if disagreement_reason is not None and cloud_reason.code not in {
            "no_shared_window",
            "models_disagree",
        }:
            reasons.append(disagreement_reason)
        reasons.extend(precip_missing)
        if rules.rain_policy == "hours_lost":
            reasons.extend(precip_failures)

    if fallback:
        reasons.append(Reason(code="fallback", model=night.fallback_model))
    coverage: list[CoverageNote] = []
    for model, evaluation in evaluations.items():
        end = _coverage_end(night.hours, model)
        coverage.append(CoverageNote(model, end, evaluation.status))
        if model != actual_primary and evaluation.status == "not_expected" and end is not None:
            reasons.append(Reason(code="model_not_used", model=model, end_utc=end))
        elif evaluation.status == "unresolved" and cloud_verdict == "no":
            reasons.append(_model_incomplete_reason(model, evaluation))
    if stale and stale_age is not None:
        reasons.insert(0, Reason(code="stale", value=float(stale_age)))
    if cloud_combination == "majority" and differing_hours > 0:
        reasons.insert(
            1,
            Reason(
                code="forecasts_differ",
                value=float(differing_hours),
                limit=float(compared_hours),
            ),
        )

    primary_states = state_lists.get(evaluation_key, [])
    unknown_minutes = sum(
        (segment.end - segment.start).total_seconds() / 60.0
        for segment in segments
        if primary_states and primary_states[segment.hour_index] == "unknown"
    )
    clear_minutes = primary_evaluation.pessimistic.clear_minutes if dark_minutes > 0 else 0.0
    longest_gap = primary_evaluation.pessimistic.longest_gap if dark_minutes > 0 else None
    longest_clear = primary_evaluation.pessimistic.longest_clear if dark_minutes > 0 else None

    hour_results: list[HourResult] = []
    for index, work in enumerate(works):
        model_states = {
            model: work.session_states[model]
            for model in models
            if work.source.models[model].cloud_expected
        }
        primary_state = work.session_states[evaluation_key]
        disagrees = (
            not use_decided_sequence
            and verdict == "uncertain"
            and any(
                model != actual_primary
                and work.source.models[model].cloud_expected
                and work.session_states[model] in {"clear", "not_clear"}
                and primary_state in {"clear", "not_clear"}
                and work.session_states[model] != primary_state
                for model in selected_models
            )
        )
        hour_results.append(
            HourResult(
                start_utc=work.source.start_utc,
                elapsed=work.elapsed,
                excluded=work.excluded,
                dark_minutes=work.dark_minutes,
                exposure_minutes=work.exposure_minutes,
                checks=work.display_checks[evaluation_key],
                conditions=work.display_conditions[evaluation_key],
                state=work.display_states[evaluation_key],
                session_state=primary_state,
                model_states=model_states,
                disagrees=disagrees,
                cloud_pct={
                    model: value.cloud_total_pct for model, value in work.source.models.items()
                },
                expected={
                    model: (value.cloud_expected, value.amount_expected)
                    for model, value in work.source.models.items()
                },
                dew_spread_c=(
                    work.source.temperature_c - work.source.dew_point_c
                    if work.source.temperature_c is not None and work.source.dew_point_c is not None
                    else None
                ),
            )
        )

    dark_results = [item for item in hour_results if item.dark_minutes > 0]
    rain_results = [
        item
        for item in hour_results
        if (item.exposure_minutes if rules.rain_policy == "night_off" else item.dark_minutes) > 0
    ]
    if cloud_combination == "majority":
        models_requirement: CheckState | Literal["info"] = (
            "not_counted"
            if fallback or len(selected_models) == 1 or compared_hours == 0
            else "unknown"
            if differing_hours == 0 and compared_unknown
            else "pass"
            if differing_hours == 0
            else "info"
        )
    elif cloud_combination == "single":
        models_requirement = "not_counted"
    else:
        models_requirement = (
            "not_counted"
            if fallback or not expected_comparisons
            else "fail"
            if cloud_verdict == "uncertain"
            else "unknown"
            if any(status == "unresolved" for status in expected_comparisons.values())
            else "pass"
        )
    requirements: dict[str, CheckState | Literal["info"]] = {
        "clear_time": (
            "pass"
            if primary_evaluation.status == "go"
            else "fail"
            if primary_evaluation.status == "no"
            else "unknown"
        ),
        "rain": _aggregate([item.checks["rain"] for item in rain_results]),
        "wind": (
            _aggregate([item.checks["wind"] for item in dark_results])
            if rules.wind_counted
            else "not_counted"
        ),
        "dew": (
            _aggregate([item.checks["dew"] for item in dark_results])
            if rules.dew_counted
            else "not_counted"
        ),
        "moon": (
            _aggregate([item.checks["moon"] for item in dark_results])
            if rules.moon_must_be_down
            else "not_counted"
        ),
        "models": models_requirement,
    }
    advisory = _layer_advisory(
        works,
        segments,
        rules,
        actual_primary,
        fallback=fallback,
        night_over=night_over,
    )
    imaging = (segments[0].start, segments[-1].end) if segments else None
    return NightResult(
        verdict=verdict,
        reasons=reasons or [Reason(code="missing_data")],
        advisory=advisory,
        clear_minutes=clear_minutes,
        dark_minutes=dark_minutes,
        unknown_minutes=unknown_minutes,
        longest_gap=longest_gap,
        longest_clear_run=longest_clear,
        window=window,
        exposure=exposure,
        imaging=imaging,
        evaluated_from_utc=evaluated_from,
        primary_model=actual_primary,
        fallback=fallback,
        cloud_combination=cloud_combination,
        differing_hours=differing_hours,
        compared_hours=compared_hours,
        cloud_models=selected_models,
        cloud_models_used=cloud_models_used,
        default_cloud_used=default_cloud_used,
        model_statuses=statuses,
        coverage=coverage,
        requirements=requirements,
        hours=hour_results,
    )
