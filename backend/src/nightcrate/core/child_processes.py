"""Track and terminate child processes owned by the NightCrate server."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess  # nosec B404 -- child tracking requires Popen handles
import threading
import time
import weakref
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from multiprocessing.process import BaseProcess
from typing import Any

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_shutting_down = False
_pools: weakref.WeakSet[ProcessPoolExecutor] = weakref.WeakSet()
_processes: weakref.WeakSet[BaseProcess] = weakref.WeakSet()
_popen_processes: weakref.WeakSet[subprocess.Popen[Any]] = weakref.WeakSet()


class ShuttingDown(RuntimeError):
    """Raised when code tries to start child work during shutdown."""


class _PosixAsyncioProcess:
    """Minimal process handle for uvloop transports that do not expose Popen."""

    def __init__(self, process: asyncio.subprocess.Process) -> None:
        self.process = process
        self.pid = process.pid

    def is_alive(self) -> bool:
        if self.process.returncode is not None:
            return False
        try:
            os.kill(self.pid, 0)
        except OSError:
            return False
        return True

    def terminate(self) -> None:
        if self.process.returncode is None:
            try:
                # A tiny POSIX-only pid-reuse window remains between the loop
                # reaping the child and publishing ``returncode``.
                os.kill(self.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    def kill(self) -> None:
        if self.process.returncode is None:
            try:
                os.kill(self.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


_posix_asyncio_processes: set[_PosixAsyncioProcess] = set()


def begin_shutdown() -> None:
    """Prevent future child work and make late registrations self-terminate."""
    global _shutting_down
    with _lock:
        _shutting_down = True
        pools = list(_pools)
    for pool in pools:
        _stop_pool(pool)


def ensure_running() -> None:
    """Raise if server shutdown has begun."""
    with _lock:
        if _shutting_down:
            raise ShuttingDown("NightCrate is shutting down")


def _reset_for_tests() -> None:
    """Reset process-global shutdown state between isolated unit tests."""
    global _shutting_down
    with _lock:
        _shutting_down = False


def _log_failure(action: str, process: object, exc: Exception) -> None:
    logger.error(
        "[child_processes] failed to %s child %r: %s",
        action,
        process,
        exc,
        exc_info=True,
    )


def _pool_processes(pool: ProcessPoolExecutor) -> list[BaseProcess]:
    try:
        return list((pool._processes or {}).values())  # pyright: ignore[reportPrivateUsage]
    except Exception as exc:
        _log_failure("inspect pool", pool, exc)
        return []


def _stop_pool(pool: ProcessPoolExecutor) -> None:
    for process in _pool_processes(pool):
        _terminate_mp(process)
    try:
        pool.shutdown(wait=False, cancel_futures=True)
    except Exception as exc:
        _log_failure("shut down pool", pool, exc)


def _mp_is_alive(process: BaseProcess) -> bool:
    try:
        return process.is_alive()
    except Exception as exc:
        _log_failure("check", process, exc)
        return True


def _popen_is_alive(process: subprocess.Popen[Any]) -> bool:
    try:
        return process.poll() is None
    except Exception as exc:
        _log_failure("check", process, exc)
        return True


def _posix_is_alive(process: _PosixAsyncioProcess) -> bool:
    try:
        return process.is_alive()
    except Exception as exc:
        _log_failure("check", process, exc)
        return True


def _terminate_mp(process: BaseProcess) -> None:
    try:
        if _mp_is_alive(process):
            process.terminate()
    except Exception as exc:
        _log_failure("terminate", process, exc)


def _kill_mp(process: BaseProcess) -> None:
    try:
        if _mp_is_alive(process):
            process.kill()
    except Exception as exc:
        _log_failure("kill", process, exc)


def _terminate_popen(process: subprocess.Popen[Any]) -> None:
    try:
        if _popen_is_alive(process):
            process.terminate()
    except Exception as exc:
        _log_failure("terminate", process, exc)


def _kill_popen(process: subprocess.Popen[Any]) -> None:
    try:
        if _popen_is_alive(process):
            process.kill()
    except Exception as exc:
        _log_failure("kill", process, exc)


def _terminate_posix(process: _PosixAsyncioProcess) -> None:
    try:
        if _posix_is_alive(process):
            process.terminate()
    except Exception as exc:
        _log_failure("terminate", process, exc)


def _kill_posix(process: _PosixAsyncioProcess) -> None:
    try:
        if _posix_is_alive(process):
            process.kill()
    except Exception as exc:
        _log_failure("kill", process, exc)


def _snapshot() -> tuple[
    list[BaseProcess],
    list[subprocess.Popen[Any]],
    list[_PosixAsyncioProcess],
]:
    with _lock:
        pools = list(_pools)
        processes = list(_processes)
        popen_processes = list(_popen_processes)
        posix_processes = list(_posix_asyncio_processes)

    for pool in pools:
        processes.extend(_pool_processes(pool))
    processes = list({id(process): process for process in processes}.values())
    return processes, popen_processes, posix_processes


def _live_snapshot() -> tuple[
    list[BaseProcess],
    list[subprocess.Popen[Any]],
    list[_PosixAsyncioProcess],
]:
    processes, popen_processes, posix_processes = _snapshot()
    return (
        [process for process in processes if _mp_is_alive(process)],
        [process for process in popen_processes if _popen_is_alive(process)],
        [process for process in posix_processes if _posix_is_alive(process)],
    )


@contextmanager
def registered_pool(pool: ProcessPoolExecutor) -> Iterator[ProcessPoolExecutor]:
    """Register a process pool for cleanup, including late worker creation."""
    with _lock:
        _pools.add(pool)
        shutting_down = _shutting_down
    if shutting_down:
        _stop_pool(pool)
    try:
        yield pool
    finally:
        with _lock:
            _pools.discard(pool)


@contextmanager
def registered_process(process: BaseProcess) -> Iterator[BaseProcess]:
    """Register a multiprocessing process for cleanup."""
    with _lock:
        _processes.add(process)
        shutting_down = _shutting_down
    if shutting_down:
        _terminate_mp(process)
    try:
        yield process
    finally:
        with _lock:
            _processes.discard(process)


@contextmanager
def registered_subprocess(
    process: asyncio.subprocess.Process,
) -> Iterator[asyncio.subprocess.Process]:
    """Register an asyncio subprocess for cleanup."""
    transport = getattr(process, "_transport", None)
    popen = None
    if transport is not None:
        try:
            popen = transport.get_extra_info("subprocess")
        except Exception as exc:
            _log_failure("inspect asyncio transport", process, exc)
        if popen is None:
            popen = getattr(transport, "_proc", None)

    pid = getattr(process, "pid", None)
    adapter: _PosixAsyncioProcess | None = None
    # A small residual gap remains between create_subprocess_exec returning and
    # this registration. The Windows job object and the POSIX shell process
    # group cover that child while the shell process itself is alive.
    with _lock:
        if isinstance(popen, subprocess.Popen):
            _popen_processes.add(popen)
        elif os.name == "posix" and pid is not None:
            adapter = _PosixAsyncioProcess(process)
            _posix_asyncio_processes.add(adapter)
        else:
            logger.error(
                "[child_processes] could not register asyncio child pid=%r",
                pid,
            )
        shutting_down = _shutting_down

    if shutting_down:
        if isinstance(popen, subprocess.Popen):
            _terminate_popen(popen)
        elif adapter is not None:
            _terminate_posix(adapter)
    try:
        yield process
    finally:
        with _lock:
            if isinstance(popen, subprocess.Popen):
                _popen_processes.discard(popen)
            if adapter is not None:
                _posix_asyncio_processes.discard(adapter)


def registered_pids() -> set[int]:
    """Return the PIDs of currently live registered child processes."""
    processes, popen_processes, posix_processes = _live_snapshot()
    return {
        *(process.pid for process in processes if process.pid is not None),
        *(process.pid for process in popen_processes),
        *(process.pid for process in posix_processes),
    }


def terminate_all() -> None:
    """Terminate all registered children, including children registered late."""
    deadline = time.monotonic() + 1.5
    while True:
        processes, popen_processes, posix_processes = _live_snapshot()
        if not processes and not popen_processes and not posix_processes:
            return
        for process in processes:
            _terminate_mp(process)
        for process in popen_processes:
            _terminate_popen(process)
        for process in posix_processes:
            _terminate_posix(process)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(0.025, remaining))

    processes, popen_processes, posix_processes = _live_snapshot()
    for process in processes:
        _kill_mp(process)
    for process in popen_processes:
        _kill_popen(process)
    for process in posix_processes:
        _kill_posix(process)

    # One final rescan catches children that registered while the kill pass ran.
    processes, popen_processes, posix_processes = _live_snapshot()
    for process in processes:
        _kill_mp(process)
    for process in popen_processes:
        _kill_popen(process)
    for process in posix_processes:
        _kill_posix(process)
