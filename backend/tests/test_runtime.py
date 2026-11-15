"""Runtime reporting tests."""

import asyncio
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context

import pytest

from nightcrate.core import child_processes, runtime


def _sleep_child():
    time.sleep(300)


@pytest.fixture(autouse=True)
def _reset_shutdown_state():
    child_processes._reset_for_tests()
    yield
    child_processes._reset_for_tests()


def test_report_step_silent_outside_production(monkeypatch, capsys):
    monkeypatch.setattr(runtime, "production", False)
    runtime.report_step("starting", "My Workspace")
    assert capsys.readouterr().out == ""


def test_report_step_machine_readable_in_production(monkeypatch, capsys):
    monkeypatch.setattr(runtime, "production", True)
    runtime.report_step("backing_up", "Bibliothèque ✨")
    prefix, payload = capsys.readouterr().out.split(" ", 1)
    assert prefix == "NIGHTCRATE_STEP"
    assert json.loads(payload) == {"step": "backing_up", "workspace": "Bibliothèque ✨"}


def test_app_version_is_package_metadata():
    assert runtime.app_version() != "unknown"


async def _terminate_registered_subprocess():
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "import time; time.sleep(300)"
    )
    try:
        with child_processes.registered_subprocess(process):
            assert process.pid in child_processes.registered_pids()
            await asyncio.to_thread(child_processes.terminate_all)
            await asyncio.wait_for(process.wait(), timeout=2)
        assert process.returncode is not None
        assert process.pid not in child_processes.registered_pids()
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


def test_terminate_all_under_standard_asyncio():
    asyncio.run(_terminate_registered_subprocess())


@pytest.mark.skipif(os.name == "nt", reason="uvloop is POSIX-only")
def test_terminate_all_under_uvloop():
    uvloop = pytest.importorskip("uvloop")
    uvloop.run(_terminate_registered_subprocess())


def test_terminate_all_catches_late_pool_workers():
    context = get_context("spawn")
    pool = ProcessPoolExecutor(max_workers=1, mp_context=context)
    try:
        with child_processes.registered_pool(pool):
            child_processes.begin_shutdown()
            try:
                pool.submit(_sleep_child)
            except RuntimeError:
                submitted = False
            else:
                submitted = True
            if submitted:
                deadline = time.monotonic() + 3
                while not pool._processes and time.monotonic() < deadline:  # noqa: SLF001
                    time.sleep(0.01)
            workers = list((pool._processes or {}).values())  # noqa: SLF001
            child_processes.terminate_all()
            assert all(not process.is_alive() for process in workers)
    finally:
        child_processes.terminate_all()
        pool.shutdown(wait=True, cancel_futures=True)


def test_registration_during_shutdown_terminates_child():
    process = get_context("spawn").Process(target=_sleep_child)
    process.start()
    try:
        child_processes.begin_shutdown()
        with child_processes.registered_process(process):
            process.join(timeout=2)
            assert not process.is_alive()
    finally:
        if process.is_alive():
            process.kill()
        process.join(timeout=2)
