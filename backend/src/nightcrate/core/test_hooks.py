"""Environment-controlled process hooks used by production-entrypoint tests."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from contextlib import AsyncExitStack, asynccontextmanager
from multiprocessing import get_context

from nightcrate.core import child_processes


def _sleep_child() -> None:
    time.sleep(300)


@asynccontextmanager
async def busy_children():
    """Start the opt-in test children and keep them registered until reaped."""
    workers = int(os.getenv("NIGHTCRATE_TEST_BUSY_POOL", "0"))
    async with AsyncExitStack() as stack:
        if not workers:
            yield
            return

        context = get_context("spawn")
        child_processes.ensure_running()
        pool = ProcessPoolExecutor(max_workers=workers, mp_context=context)
        stack.enter_context(child_processes.registered_pool(pool))
        futures = [pool.submit(_sleep_child) for _ in range(workers)]

        process = context.Process(target=_sleep_child)
        stack.enter_context(child_processes.registered_process(process))
        child_processes.ensure_running()
        process.start()

        child_processes.ensure_running()
        async_process = await asyncio.create_subprocess_exec(
            sys.executable, "-c", "import time; time.sleep(300)"
        )
        stack.enter_context(child_processes.registered_subprocess(async_process))

        while len(pool._processes) < workers:  # noqa: SLF001
            await asyncio.sleep(0.01)
        pids = sorted(
            [proc.pid for proc in pool._processes.values()]  # noqa: SLF001
            + [process.pid, async_process.pid]
        )
        print(f"NIGHTCRATE_TEST_POOL_PIDS {json.dumps(pids)}", flush=True)
        try:
            yield
        finally:
            child_processes.terminate_all()
            if async_process.returncode is None:
                await async_process.wait()
            process.join(timeout=0.1)
            pool.shutdown(wait=True, cancel_futures=True)
            del futures
