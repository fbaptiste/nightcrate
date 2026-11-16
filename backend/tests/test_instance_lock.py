"""App-data scoped OS lock tests."""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest
from fastapi import FastAPI

from nightcrate.core import app_config, runtime
from nightcrate.core.instance_lock import InstanceLockHeld, acquire_instance_lock
from nightcrate.main import lifespan
from nightcrate.serve import EXIT_LOCK_HELD
from nightcrate.serve import main as serve_main

_HOLDER = """
import sys, time
from pathlib import Path
from nightcrate.core.app_config import set_app_dir
from nightcrate.core.instance_lock import acquire_instance_lock
set_app_dir(Path(sys.argv[1]))
lock = acquire_instance_lock('installed', '9.9.9', 9876)
print('LOCKED', flush=True)
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
    assert proc.stdout.readline().strip() == "LOCKED"
    return proc


def test_second_acquire_reports_holder(tmp_path):
    app_dir = tmp_path / "app"
    proc = _holder(app_dir)
    app_config.set_app_dir(app_dir)
    try:
        with pytest.raises(InstanceLockHeld) as caught:
            acquire_instance_lock("source", "1.0", None)
        assert caught.value.info is not None
        assert caught.value.info.kind == "installed"
        assert caught.value.info.pid == proc.pid
    finally:
        proc.kill()
        proc.wait()


def test_lock_released_when_holder_killed(tmp_path):
    app_dir = tmp_path / "app"
    proc = _holder(app_dir)
    proc.kill()
    proc.wait()
    app_config.set_app_dir(app_dir)
    lock = acquire_instance_lock("source", "1.0", None)
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
