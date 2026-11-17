"""App-data scoped OS lock tests."""

import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from nightcrate.core import app_config, runtime
from nightcrate.core.instance_lock import InstanceLockHeld, acquire_instance_lock
from nightcrate.main import lifespan
from nightcrate.serve import EXIT_LOCK_HELD
from nightcrate.serve import main as serve_main

_HOLDER = """
import os, sys, time
from pathlib import Path
from nightcrate.core.app_config import set_app_dir
from nightcrate.core.instance_lock import acquire_instance_lock
set_app_dir(Path(sys.argv[1]))
lock = acquire_instance_lock('installed', '9.9.9', 9876)
print(f'LOCKED {os.getpid()}', flush=True)
time.sleep(300)
"""


def _holder(path):
    proc = subprocess.Popen(
        [sys.executable, "-c", _HOLDER, str(path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert proc.stdout is not None
    line = proc.stdout.readline().strip()
    prefix, pid = line.split()
    assert prefix == "LOCKED"
    return proc, int(pid)


def _wait_for_pid_exit(pid: int, timeout: float) -> None:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if not handle:
            return
        try:
            if kernel32.WaitForSingleObject(handle, int(timeout * 1000)) != 0:
                pytest.fail(f"lock holder process {pid} did not exit within {timeout:g} seconds")
        finally:
            kernel32.CloseHandle(handle)
        return

    deadline = time.monotonic() + timeout
    while True:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        if time.monotonic() >= deadline:
            pytest.fail(f"lock holder process {pid} did not exit within {timeout:g} seconds")
        time.sleep(0.05)


def _kill_holder(proc: subprocess.Popen, holder_pid: int) -> None:
    if holder_pid != proc.pid:
        try:
            os.kill(holder_pid, signal.SIGTERM)
        except OSError:
            pass
    proc.kill()
    proc.wait(timeout=10)

    if holder_pid != proc.pid:
        _wait_for_pid_exit(holder_pid, 10)


def test_second_acquire_reports_holder(tmp_path):
    app_dir = tmp_path / "app"
    proc, holder_pid = _holder(app_dir)
    app_config.set_app_dir(app_dir)
    try:
        with pytest.raises(InstanceLockHeld) as caught:
            acquire_instance_lock("source", "1.0", None)
        assert caught.value.info is not None
        assert caught.value.info.kind == "installed"
        assert caught.value.info.pid == holder_pid
    finally:
        _kill_holder(proc, holder_pid)


def test_windows_lock_contention_does_not_read_locked_byte(tmp_path, monkeypatch):
    app_dir = tmp_path / "windows-lock"
    app_dir.mkdir()
    lock_path = app_dir / "instance.lock"
    lock_path.write_bytes(b"\0")
    (app_dir / "instance.json").write_text(
        json.dumps({"pid": 123, "kind": "installed", "version": "9.9.9", "port": 9876}),
        encoding="utf-8",
    )
    app_config.set_app_dir(app_dir)
    real_open = type(lock_path).open

    class LockedByteStream:
        def __init__(self, stream):
            self._stream = stream

        def read(self, *_args, **_kwargs):
            raise AssertionError("the locked byte must not be read")

        def __getattr__(self, name):
            return getattr(self._stream, name)

    def open_stream(path, *args, **kwargs):
        stream = real_open(path, *args, **kwargs)
        return LockedByteStream(stream) if path == lock_path else stream

    def deny_lock(*_args):
        raise PermissionError("locked")

    monkeypatch.setattr(type(lock_path), "open", open_stream)
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setitem(
        sys.modules,
        "msvcrt",
        SimpleNamespace(LK_NBLCK=1, locking=deny_lock),
    )

    with pytest.raises(InstanceLockHeld) as caught:
        acquire_instance_lock("source", "1.0", None)

    assert caught.value.info is not None
    assert caught.value.info.pid == 123


def test_lock_released_when_holder_killed(tmp_path):
    app_dir = tmp_path / "app"
    proc, holder_pid = _holder(app_dir)
    _kill_holder(proc, holder_pid)
    app_config.set_app_dir(app_dir)
    deadline = time.monotonic() + 10
    while True:
        try:
            lock = acquire_instance_lock("source", "1.0", None)
            break
        except InstanceLockHeld:
            if time.monotonic() >= deadline:
                pytest.fail("instance lock was not released within 10 seconds after holder exited")
            time.sleep(0.05)
    lock.release()


def test_lock_in_non_ascii_folder(tmp_path):
    app_config.set_app_dir(tmp_path / "Bibliothèque de Fred ✨")
    lock = acquire_instance_lock("source", "1.0", None)
    lock.release()


@pytest.mark.anyio
async def test_lifespan_releases_lock():
    for _ in range(2):
        async with lifespan(FastAPI()):
            pass


def test_serve_exits_when_locked(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(runtime, "production", False)
    monkeypatch.setattr(runtime, "log_dir", None)
    app_dir = tmp_path / "locked-app"
    frontend = tmp_path / "frontend"
    (frontend / "assets").mkdir(parents=True)
    (frontend / "index.html").write_text("NC")
    app_config.set_app_dir(app_dir)
    holder = acquire_instance_lock("installed", "9.9.9", 9999)
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    try:
        code = serve_main(
            [
                "--port",
                str(port),
                "--app-dir",
                str(app_dir),
                "--frontend-dir",
                str(frontend),
            ]
        )
        assert code == EXIT_LOCK_HELD
        payload = json.loads(capsys.readouterr().out.split(" ", 1)[1])
        assert payload["kind"] == "installed"
        assert payload["pid"] == os.getpid()
    finally:
        holder.release()


@pytest.mark.skipif(os.name != "posix", reason="uvicorn reload handoff is POSIX-only")
def test_reload_hands_the_lock_over(tmp_path):
    app_dir = tmp_path / "reload-app-data"
    reload_dir = tmp_path / "reload-package"
    reload_dir.mkdir()
    (reload_dir / "sitecustomize.py").write_text(
        "import os\n"
        "from pathlib import Path\n"
        "from nightcrate.core.app_config import set_app_dir\n"
        "set_app_dir(Path(os.environ['NIGHTCRATE_RELOAD_APP_DIR']))\n",
        encoding="utf-8",
    )
    trigger = reload_dir / "trigger.py"
    trigger.write_text("VALUE = 1\n", encoding="utf-8")
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    log_path = tmp_path / "reload.log"
    env = os.environ.copy()
    env["NIGHTCRATE_RELOAD_APP_DIR"] = str(app_dir)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONPATH"] = os.pathsep.join(
        [str(reload_dir), *(part for part in [env.get("PYTHONPATH")] if part)]
    )

    with log_path.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "nightcrate.main:app",
                "--reload",
                "--reload-dir",
                str(reload_dir),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            stdout=output,
            stderr=subprocess.STDOUT,
            env=env,
        )
        try:
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                try:
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/api/health", timeout=0.25
                    ) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(0.05)
            else:
                raise AssertionError(f"initial server did not start: {log_path.read_text()}")

            trigger.write_text("VALUE = 2\n", encoding="utf-8")
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                log = log_path.read_text(encoding="utf-8")
                if log.count("Started server process") >= 2:
                    try:
                        with urllib.request.urlopen(
                            f"http://127.0.0.1:{port}/api/health", timeout=0.25
                        ) as response:
                            if response.status == 200:
                                break
                    except OSError:
                        pass
                time.sleep(0.05)
            else:
                raise AssertionError(f"reloaded server did not answer: {log_path.read_text()}")

            assert "already running" not in log_path.read_text(encoding="utf-8").lower()
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
