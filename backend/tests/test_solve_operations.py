"""Operation identity, cancellation, progress, and shared-slot tests."""

import asyncio
from uuid import uuid4

import pytest

from nightcrate.services import solve_operations
from nightcrate.services.plate_solve_models import SolveAttempt


@pytest.fixture(autouse=True)
def reset_operations():
    solve_operations._reset_for_tests()
    yield
    solve_operations._reset_for_tests()


def test_progress_snapshot_lists_attempts():
    operation_id = uuid4()
    operation = solve_operations.claim(operation_id, "native")
    operation.plan(["near_index", "blind_known_scale"])
    operation.start(
        SolveAttempt(
            solver="native",
            step="near_index",
            position_source="request",
            scale_source="header",
        )
    )
    operation.searched(["q016"], ["0.4-10"])
    active = solve_operations.snapshot(operation_id)
    assert active is not None
    assert active.active_step is not None
    assert active.active_step.ranges == ["0.4-10"]
    assert active.planned == ["blind_known_scale"]

    operation.finish("no_match")
    solve_operations.release(operation)
    finished = solve_operations.snapshot(operation_id)
    assert finished is not None
    assert finished.state == "finished"
    assert finished.active_step is None
    assert finished.attempts[0].outcome == "no_match"


def test_cancel_before_claim_stops_solve():
    operation_id = uuid4()
    result = solve_operations.cancel(operation_id)
    assert result.cancelled is False
    assert result.pending is True
    with pytest.raises(solve_operations.SolveCancelled):
        solve_operations.claim(operation_id, "astap")


def test_pending_cancels_are_bounded_and_expire(monkeypatch):
    now = 1000.0
    monkeypatch.setattr(solve_operations.time, "monotonic", lambda: now)
    ids = [uuid4() for _ in range(65)]
    for operation_id in ids:
        solve_operations.cancel(operation_id)
    assert len(solve_operations._pending) == 64
    assert ids[0] not in solve_operations._pending

    now += 601.0
    operation = solve_operations.claim(ids[1], "native")
    solve_operations.release(operation)


def test_reused_operation_id_returns_busy():
    operation_id = uuid4()
    operation = solve_operations.claim(operation_id, "native")
    solve_operations.release(operation)
    with pytest.raises(solve_operations.SolveBusy, match="already been used"):
        solve_operations.claim(operation_id, "native")


def test_used_operation_ids_are_bounded():
    operation_ids = [uuid4() for _ in range(1025)]
    for operation_id in operation_ids:
        operation = solve_operations.claim(operation_id, "native")
        solve_operations.release(operation)

    assert len(solve_operations._used) == 1024
    assert operation_ids[0] not in solve_operations._used


def test_late_cancel_of_finished_operation_leaves_next_running():
    first_id = uuid4()
    first = solve_operations.claim(first_id, "native")
    solve_operations.release(first)
    second = solve_operations.claim(uuid4(), "astap")

    result = solve_operations.cancel(first_id)

    assert result.cancelled is False
    assert not second.stop.is_set()
    solve_operations.release(second)


def test_begin_commit_is_atomic_with_cancel():
    cancelled = solve_operations.claim(uuid4(), "native")
    assert cancelled.cancel()
    with pytest.raises(solve_operations.SolveCancelled):
        cancelled.begin_commit()
    solve_operations.release(cancelled)

    committing = solve_operations.claim(uuid4(), "native")
    committing.begin_commit()
    result = solve_operations.cancel(committing.operation_id)
    assert result.cancelled is False
    assert not committing.stop.is_set()
    solve_operations.release(committing)


@pytest.mark.asyncio
async def test_waiting_publication_stays_excluded_by_active_solve():
    operation = solve_operations.claim(uuid4(), "native")
    entered = asyncio.Event()

    async def publish():
        async with solve_operations.waiting_slot():
            entered.set()

    task = asyncio.create_task(publish())
    await asyncio.sleep(0)
    assert not entered.is_set()
    solve_operations.release(operation)
    await task
    assert entered.is_set()
