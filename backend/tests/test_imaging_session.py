"""Unit tests for the revised imaging-session kernel."""

from datetime import UTC, datetime, timedelta
from itertools import permutations, product

import pytest

from nightcrate.services.imaging_rules import PRESETS, ImagingRules
from nightcrate.services.imaging_session import (
    Segment,
    decide_cloud,
    joint_states,
    model_status,
    session_pass,
)

START = datetime(2026, 10, 18, 0, tzinfo=UTC)


def _rules(**overrides: object) -> ImagingRules:
    values = PRESETS["left_out_all_night"][1].model_dump()
    values.update(overrides)
    return ImagingRules(**values)


def _segments(count: int) -> list[Segment]:
    return [
        Segment(START + timedelta(hours=index), START + timedelta(hours=index + 1), index)
        for index in range(count)
    ]


def test_share_at_least():
    result = session_pass(
        ["clear", "clear", "clear", "not_clear"],
        _segments(4),
        _rules(min_clear_fraction_pct=75, min_clear_hours=0),
        240,
        optimistic=False,
    )
    assert result.passed is True
    assert result.clear_minutes == 180


def test_runs_do_not_bridge_non_dark():
    segments = [
        Segment(START, START + timedelta(hours=1), 0),
        Segment(START + timedelta(hours=2), START + timedelta(hours=3), 1),
    ]
    result = session_pass(
        ["clear", "clear"],
        segments,
        _rules(session_style="short_session", short_session_hours=2),
        120,
        optimistic=False,
    )
    assert result.passed is False
    assert result.longest_clear == (START, START + timedelta(hours=1))


def test_model_status_table():
    rules = _rules(session_style="short_session", short_session_hours=2)
    segments = _segments(2)
    cases = (
        (["clear", "clear"], False, "go", True, True),
        (["not_clear", "not_clear"], False, "no", False, False),
        (["clear", "unknown"], True, "unresolved", False, True),
        (["clear", "unknown"], False, "not_expected", False, True),
    )
    for states, expected_missing, expected, pessimistic_passed, optimistic_passed in cases:
        status, pessimistic, optimistic = model_status(
            states,
            segments,
            rules,
            120,
            expected_missing=expected_missing,
        )
        assert (status, pessimistic.passed, optimistic.passed) == (
            expected,
            pessimistic_passed,
            optimistic_passed,
        )


def _reference_decide(checks: dict[str, str], order: tuple[str, ...]) -> str:
    def one(unknown: str) -> str:
        votes = {model: unknown if state == "unknown" else state for model, state in checks.items()}
        passed = sum(state == "pass" for state in votes.values())
        failed = sum(state == "fail" for state in votes.values())
        if passed != failed:
            return "pass" if passed > failed else "fail"
        return next(votes[model] for model in order if model in votes)

    pessimistic = one("fail")
    optimistic = one("pass")
    return pessimistic if pessimistic == optimistic else "unknown"


def test_decide_cloud_exhaustive():
    names = ("E", "G", "I")
    states = ("pass", "fail", "unknown")
    for count in range(1, 4):
        voters = names[:count]
        for values in product(states, repeat=count):
            checks = dict(zip(voters, values, strict=True))
            for order in permutations(voters):
                assert decide_cloud(checks, order) == _reference_decide(checks, order)


def test_decide_cloud_hand_checked_cases():
    order = ("E", "G", "I")
    cases = (
        (("pass", "pass", "fail"), order, "pass"),
        (("pass", "fail"), order, "pass"),
        (("fail", "pass"), ("G", "E", "I"), "pass"),
        (("unknown", "pass", "fail"), order, "unknown"),
        (("fail", "fail", "unknown"), order, "fail"),
        (("pass", "pass", "unknown"), order, "pass"),
        (("unknown",), order, "unknown"),
    )
    for values, tie_order, expected in cases:
        checks = dict(zip(order, values, strict=False))
        assert decide_cloud(checks, tie_order) == expected


def test_decide_cloud_requires_a_vote():
    with pytest.raises(ValueError, match="at least one cloud forecast must vote"):
        decide_cloud({}, ())


def test_joint_states_requires_equal_sequence_lengths():
    with pytest.raises(ValueError, match="sequences must have equal lengths"):
        joint_states({"E": ["clear"]}, {"E": [True, False]})


def test_decide_cloud_unknown_replacement_never_creates_pass():
    names = ("E", "G", "I")
    for count in range(1, 4):
        voters = names[:count]
        for values in product(("pass", "fail", "unknown"), repeat=count):
            checks = dict(zip(voters, values, strict=True))
            for order in permutations(voters):
                original = decide_cloud(checks, order)
                if original == "pass":
                    continue
                for model, value in checks.items():
                    if value == "unknown":
                        continue
                    erased = {**checks, model: "unknown"}
                    assert decide_cloud(erased, order) != "pass"
