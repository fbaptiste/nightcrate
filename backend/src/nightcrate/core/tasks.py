from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


async def drain_task_map(
    in_flight: dict,
    *,
    cancel_pending: bool = True,
    running: set[asyncio.Task] | None = None,
) -> None:
    """Drain the current task-map snapshot and remove only matching entries."""
    snapshot = tuple(in_flight.items())
    tasks = tuple(task for _, task in snapshot)
    if cancel_pending:
        protected = running or set()
        for task in tasks:
            if not task.done() and task not in protected:
                task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    for key, task in snapshot:
        if in_flight.get(key) is task:
            in_flight.pop(key, None)


@asynccontextmanager
async def cancellation_safe_connection(conn_factory):
    """Open and close an async connection without cancelling either operation."""
    manager = conn_factory()
    open_task = asyncio.create_task(manager.__aenter__())
    opened = False
    try:
        try:
            connection = await settle(open_task)
            opened = True
        except BaseException:
            opened = (
                open_task.done() and not open_task.cancelled() and open_task.exception() is None
            )
            raise
        yield connection
    finally:
        if opened:
            close_task = asyncio.create_task(manager.__aexit__(None, None, None))
            await settle(close_task)


async def settle[T](task: asyncio.Future[T], *, on_cancel: Callable[[], object] | None = None) -> T:
    """Wait through repeated cancellation until ``task`` settles.

    The first cancellation calls ``on_cancel`` once, retrieves the task's
    outcome, and then wins over that outcome; otherwise the task's result wins.
    """
    waiter = asyncio.gather(task, return_exceptions=True)
    cancelled = False
    while not waiter.done():
        try:
            await asyncio.shield(waiter)
        except asyncio.CancelledError:
            if not cancelled:
                cancelled = True
                if on_cancel is not None:
                    on_cancel()

    waiter.result()
    if cancelled:
        if not task.cancelled() and (error := task.exception()) is not None:
            logger.debug(
                "[tasks] worker raised after cancellation",
                exc_info=(type(error), error, error.__traceback__),
            )
        raise asyncio.CancelledError
    return task.result()
