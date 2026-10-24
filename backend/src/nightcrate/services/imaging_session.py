"""Session rules and two-pass model status for the revised evaluator."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from nightcrate.services.imaging_rules import ImagingRules
from nightcrate.services.imaging_types import (
    CheckState,
    HourState,
    ModelStatus,
    Reason,
    WindowStatus,
)


@dataclass(frozen=True)
class Segment:
    start: datetime
    end: datetime
    hour_index: int


@dataclass(frozen=True)
class SessionPass:
    passed: bool
    reason: Reason
    clear_minutes: float
    longest_gap: tuple[datetime, datetime] | None
    longest_clear: tuple[datetime, datetime] | None


def decide_cloud(checks: Mapping[str, CheckState], order: Sequence[str]) -> CheckState:
    """Decide one hour conservatively from the cloud forecasts that vote."""
    if not checks:
        raise ValueError("at least one cloud forecast must vote")

    def decide(unknown: CheckState) -> CheckState:
        votes = {
            model: (unknown if state == "unknown" else state) for model, state in checks.items()
        }
        passed = sum(state == "pass" for state in votes.values())
        failed = sum(state == "fail" for state in votes.values())
        if passed != failed:
            return "pass" if passed > failed else "fail"
        return next(votes[model] for model in order if model in votes)

    pessimistic = decide("fail")
    optimistic = decide("pass")
    return pessimistic if pessimistic == optimistic else "unknown"


def _runs(
    segments: Sequence[Segment],
    states: Sequence[HourState],
    accepted: set[HourState],
) -> list[tuple[datetime, datetime]]:
    runs: list[tuple[datetime, datetime]] = []
    current: tuple[datetime, datetime] | None = None
    for segment in segments:
        if states[segment.hour_index] not in accepted:
            current = None
            continue
        if current is not None and current[1] == segment.start:
            current = (current[0], segment.end)
            runs[-1] = current
        else:
            current = (segment.start, segment.end)
            runs.append(current)
    return runs


def _longest(runs: Sequence[tuple[datetime, datetime]]) -> tuple[datetime, datetime] | None:
    if not runs:
        return None
    return max(runs, key=lambda run: ((run[1] - run[0]).total_seconds(), -run[0].timestamp()))


def _minutes(run: tuple[datetime, datetime] | None) -> float:
    return 0.0 if run is None else (run[1] - run[0]).total_seconds() / 60.0


def session_pass(
    states: Sequence[HourState],
    segments: Sequence[Segment],
    rules: ImagingRules,
    dark_minutes: float,
    *,
    optimistic: bool,
) -> SessionPass:
    """Apply today's session rule with unknown hours resolved for one pass."""
    clear_states: set[HourState] = {"clear", "unknown"} if optimistic else {"clear"}
    clear_runs = _runs(segments, states, clear_states)
    gap_states: set[HourState] = {"not_clear"} if optimistic else {"not_clear", "unknown"}
    gap_runs = _runs(segments, states, gap_states)
    longest_clear = _longest(clear_runs)
    longest_gap = _longest(gap_runs)
    clear_minutes = sum(_minutes(run) for run in clear_runs)

    if rules.session_style == "short_session":
        passed = _minutes(longest_clear) >= rules.short_session_hours * 60.0
        reason = (
            Reason(code="short_window", start_utc=longest_clear[0], end_utc=longest_clear[1])
            if passed and longest_clear is not None
            else Reason(
                code="no_window",
                value=_minutes(longest_clear) / 60.0,
                limit=rules.short_session_hours,
            )
        )
        return SessionPass(passed, reason, clear_minutes, longest_gap, longest_clear)

    fraction = clear_minutes / dark_minutes * 100.0 if dark_minutes > 0 else 0.0
    if fraction < rules.min_clear_fraction_pct:
        return SessionPass(
            False,
            Reason(code="clear_fraction", value=fraction, limit=rules.min_clear_fraction_pct),
            clear_minutes,
            longest_gap,
            longest_clear,
        )
    if clear_minutes < rules.min_clear_hours * 60.0:
        return SessionPass(
            False,
            Reason(
                code="min_hours",
                value=clear_minutes / 60.0,
                limit=rules.min_clear_hours,
            ),
            clear_minutes,
            longest_gap,
            longest_clear,
        )
    if (
        rules.max_cloudy_gap_hours is not None
        and _minutes(longest_gap) > rules.max_cloudy_gap_hours * 60.0
    ):
        return SessionPass(
            False,
            Reason(
                code="gap",
                start_utc=longest_gap[0] if longest_gap else None,
                end_utc=longest_gap[1] if longest_gap else None,
                value=_minutes(longest_gap) / 60.0,
                limit=rules.max_cloudy_gap_hours,
            ),
            clear_minutes,
            longest_gap,
            longest_clear,
        )

    reason = (
        Reason(code="clear_all_night")
        if longest_gap is None
        else Reason(code="clear_with_gaps", start_utc=longest_gap[0], end_utc=longest_gap[1])
    )
    return SessionPass(True, reason, clear_minutes, longest_gap, longest_clear)


def model_status(
    states: Sequence[HourState],
    segments: Sequence[Segment],
    rules: ImagingRules,
    dark_minutes: float,
    *,
    expected_missing: bool,
) -> tuple[ModelStatus, SessionPass, SessionPass]:
    """Classify a model from pessimistic and optimistic session passes."""
    pessimistic = session_pass(states, segments, rules, dark_minutes, optimistic=False)
    optimistic = session_pass(states, segments, rules, dark_minutes, optimistic=True)
    if pessimistic.passed:
        status: ModelStatus = "go"
    elif not optimistic.passed:
        status = "no"
    elif expected_missing:
        status = "unresolved"
    else:
        status = "not_expected"
    return status, pessimistic, optimistic


def joint_states(
    states: Mapping[str, Sequence[HourState]],
    expected: Mapping[str, Sequence[bool]],
) -> list[HourState]:
    """Combine the models declared expected at each hour."""
    lengths = {len(values) for values in states.values()} | {
        len(values) for values in expected.values()
    }
    if len(lengths) > 1:
        raise ValueError("state and expected sequences must have equal lengths")
    count = next(iter(lengths), 0)
    result: list[HourState] = []
    for index in range(count):
        included = [
            values[index]
            for model, values in states.items()
            if model in expected and expected[model][index]
        ]
        if "not_clear" in included:
            result.append("not_clear")
        elif "unknown" in included:
            result.append("unknown")
        elif included and all(state == "outside" for state in included):
            result.append("outside")
        else:
            result.append("clear")
    return result


def _first_window(
    states: Sequence[HourState],
    segments: Sequence[Segment],
    accepted: set[HourState],
    required_minutes: float,
) -> tuple[datetime, datetime] | None:
    for start, end in _runs(segments, states, accepted):
        if (end - start).total_seconds() / 60.0 >= required_minutes:
            return start, start + timedelta(minutes=required_minutes)
    return None


def shared_window(
    joint: Sequence[HourState],
    segments: Sequence[Segment],
    required_minutes: float,
) -> tuple[WindowStatus, tuple[datetime, datetime] | None]:
    """Classify the earliest shared run with pessimistic and optimistic passes."""
    pessimistic = _first_window(joint, segments, {"clear"}, required_minutes)
    if pessimistic is not None:
        return "established", pessimistic
    optimistic = _first_window(joint, segments, {"clear", "unknown"}, required_minutes)
    if optimistic is None:
        return "impossible", None
    return "unresolved", None
