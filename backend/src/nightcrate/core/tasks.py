from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)


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
