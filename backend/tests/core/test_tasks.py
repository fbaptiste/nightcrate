from __future__ import annotations

import asyncio
import threading

import pytest

from nightcrate.core.tasks import settle


@pytest.mark.asyncio
async def test_settle_returns_worker_value():
    worker = asyncio.create_task(asyncio.sleep(0, result=42))

    assert await settle(worker) == 42


@pytest.mark.asyncio
async def test_settle_propagates_worker_exception_without_cancellation():
    async def fail() -> None:
        raise OSError("worker failed")

    worker = asyncio.create_task(fail())

    with pytest.raises(OSError, match="worker failed"):
        await settle(worker)


@pytest.mark.asyncio
@pytest.mark.parametrize("cancellations", [1, 2])
async def test_settle_waits_for_blocked_thread_and_calls_on_cancel_once(cancellations: int):
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = threading.Event()
    cancel_calls = 0

    def blocked() -> int:
        loop.call_soon_threadsafe(started.set)
        assert release.wait(timeout=5)
        return 42

    def on_cancel() -> None:
        nonlocal cancel_calls
        cancel_calls += 1

    worker = asyncio.create_task(asyncio.to_thread(blocked))
    owner = asyncio.create_task(settle(worker, on_cancel=on_cancel))
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        for _ in range(cancellations):
            owner.cancel()
            await asyncio.sleep(0)

        assert cancel_calls == 1
        assert not owner.done()
    finally:
        release.set()
        if owner.cancelling() == 0:
            owner.cancel()
        result = await asyncio.wait_for(asyncio.gather(owner, return_exceptions=True), timeout=1)

    assert isinstance(result[0], asyncio.CancelledError)
    assert worker.done()


@pytest.mark.asyncio
async def test_settle_cancellation_wins_worker_exception_without_loop_report():
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = threading.Event()
    loop_reports: list[dict[str, object]] = []
    previous_handler = loop.get_exception_handler()

    def blocked_failure() -> None:
        loop.call_soon_threadsafe(started.set)
        assert release.wait(timeout=5)
        raise OSError("late worker failure")

    loop.set_exception_handler(lambda _loop, context: loop_reports.append(context))
    worker = asyncio.create_task(asyncio.to_thread(blocked_failure))
    owner = asyncio.create_task(settle(worker))
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        owner.cancel()
        await asyncio.sleep(0)
        assert not owner.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(owner, timeout=1)
        await asyncio.sleep(0)
        assert loop_reports == []
    finally:
        release.set()
        owner.cancel()
        await asyncio.wait_for(asyncio.gather(owner, return_exceptions=True), timeout=1)
        loop.set_exception_handler(previous_handler)


@pytest.mark.asyncio
async def test_settle_normal_cancellation_has_no_loop_report():
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = threading.Event()
    loop_reports: list[dict[str, object]] = []
    previous_handler = loop.get_exception_handler()

    def blocked() -> None:
        loop.call_soon_threadsafe(started.set)
        assert release.wait(timeout=5)

    loop.set_exception_handler(lambda _loop, context: loop_reports.append(context))
    worker = asyncio.create_task(asyncio.to_thread(blocked))
    owner = asyncio.create_task(settle(worker))
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        owner.cancel()
        await asyncio.sleep(0)
        assert not owner.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(owner, timeout=1)
        await asyncio.sleep(0)
        assert loop_reports == []
    finally:
        release.set()
        owner.cancel()
        await asyncio.wait_for(asyncio.gather(owner, return_exceptions=True), timeout=1)
        loop.set_exception_handler(previous_handler)
