"""Production entrypoint unit and ASGI tests."""

import json
import os
import queue
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from nightcrate.core import runtime
from nightcrate.serve import (
    EXIT_DEADLINE,
    EXIT_NO_FRONTEND,
    choose_port,
    configure_production,
    main,
)


def _frontend(tmp_path):
    root = tmp_path / "frontend"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("NC-INDEX", encoding="utf-8")
    (root / "assets" / "app.js").write_text("NC-ASSET", encoding="utf-8")
    return root


def _free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _occupied_with_free_next():
    for _ in range(100):
        occupied = socket.socket()
        occupied.bind(("127.0.0.1", 0))
        base = occupied.getsockname()[1]
        probe = socket.socket()
        try:
            probe.bind(("127.0.0.1", base + 1))
        except OSError:
            occupied.close()
            probe.close()
            continue
        probe.close()
        return occupied, base
    raise AssertionError("could not find consecutive free ports")


def test_deadline_exits_even_if_terminate_raises():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from nightcrate import serve; "
                "serve.child_processes.terminate_all = "
                "lambda: (_ for _ in ()).throw(RuntimeError('boom')); "
                "serve._deadline_exit()"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == EXIT_DEADLINE


class _Output:
    def __init__(self, process):
        self.process = process
        self.lines = []
        self.queue = queue.Queue()
        assert process.stdout is not None

        def read():
            for line in process.stdout:
                line = line.rstrip()
                self.lines.append(line)
                self.queue.put(line)

        threading.Thread(target=read, daemon=True).start()

    def wait_for(self, prefix, timeout=25):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None and self.queue.empty():
                break
            try:
                line = self.queue.get(timeout=min(0.2, deadline - time.monotonic()))
            except queue.Empty:
                continue
            if line.startswith(prefix):
                return line
        raise AssertionError(f"never saw {prefix!r}; output: {self.lines!r}")


def _spawn(tmp_path, frontend, *, port=None, extra_env=None):
    args = [
        sys.executable,
        "-m",
        "nightcrate.serve",
        "--shell",
        "--app-dir",
        str(tmp_path / "app-data"),
        "--frontend-dir",
        str(frontend),
    ]
    if port is not None:
        args.extend(("--port", str(port)))
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env.update(extra_env or {})
    process = subprocess.Popen(
        args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    return process, _Output(process)


def _close_stdin(process):
    assert process.stdin is not None
    process.stdin.close()


def _cleanup(process):
    if process.poll() is None:
        process.kill()
    process.wait(timeout=5)


@pytest.mark.anyio
async def test_spa_fallback_and_host_check(tmp_path):
    app = FastAPI()

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    frontend = _frontend(tmp_path)
    configure_production(app, frontend, 9123)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:9123") as client:
        assert (await client.get("/projects/12")).text == "NC-INDEX"
        assert (await client.get("/assets/app.js")).text == "NC-ASSET"
        assert (await client.get("/api/nope")).status_code == 404
        assert (await client.get("/openapi.json")).status_code == 200
        assert (await client.get("/../../pyproject.toml")).text == "NC-INDEX"
        assert (await client.get("/", headers={"host": "localhost:9123"})).status_code == 200
        assert (await client.get("/", headers={"host": "evil.example"})).status_code == 400
        assert (await client.get("/", headers={"host": "127.0.0.1:9124"})).status_code == 400


def test_choose_port_falls_back():
    occupied, base = _occupied_with_free_next()
    chosen = choose_port(base, 1)
    try:
        assert chosen.getsockname()[1] == base + 1
    finally:
        chosen.close()
        occupied.close()


def test_choose_port_all_taken():
    first = socket.socket()
    first.bind(("127.0.0.1", 0))
    port = first.getsockname()[1]
    with pytest.raises(OSError):
        choose_port(port, 0)
    first.close()


def test_serve_version_flag(monkeypatch, capsys):
    monkeypatch.setattr(runtime, "production", False)
    monkeypatch.setattr(runtime, "install_kind", "source")
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == runtime.app_version()


def test_missing_frontend_has_build_instruction(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(runtime, "production", False)
    assert main(["--frontend-dir", str(tmp_path / "missing")]) == EXIT_NO_FRONTEND
    assert "Build the frontend first: cd frontend && npm run build" in capsys.readouterr().err


def test_ready_only_when_accepting_and_shell_eof_exits(tmp_path):
    frontend = _frontend(tmp_path)
    port = _free_port()
    process, output = _spawn(tmp_path, frontend, port=port)
    try:
        ready = json.loads(output.wait_for("NIGHTCRATE_READY ").split(" ", 1)[1])
        assert ready == {"port": port}
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as response:
            assert response.status == 200
        _close_stdin(process)
        assert process.wait(timeout=15) == 0
    finally:
        _cleanup(process)


def test_shell_eof_during_startup_hits_deadline(tmp_path):
    frontend = _frontend(tmp_path)
    process, output = _spawn(
        tmp_path,
        frontend,
        port=_free_port(),
        extra_env={"NIGHTCRATE_TEST_STARTUP_DELAY": "60"},
    )
    try:
        output.wait_for("NIGHTCRATE_ALIVE", timeout=8)
        _close_stdin(process)
        assert process.wait(timeout=20) == 6
    finally:
        _cleanup(process)


def test_heartbeat_until_ready(tmp_path):
    frontend = _frontend(tmp_path)
    process, output = _spawn(
        tmp_path,
        frontend,
        port=_free_port(),
        extra_env={"NIGHTCRATE_TEST_STARTUP_DELAY": "12"},
    )
    try:
        output.wait_for("NIGHTCRATE_READY", timeout=20)
        ready_index = next(
            i for i, line in enumerate(output.lines) if line.startswith("NIGHTCRATE_READY")
        )
        assert sum(line == "NIGHTCRATE_ALIVE" for line in output.lines[:ready_index]) >= 2
        time.sleep(5.5)
        assert "NIGHTCRATE_ALIVE" not in output.lines[ready_index + 1 :]
        _close_stdin(process)
        assert process.wait(timeout=15) == 0
    finally:
        _cleanup(process)


def test_port_fallback_without_flag(tmp_path):
    frontend = _frontend(tmp_path)
    occupied, base = _occupied_with_free_next()
    process, output = _spawn(
        tmp_path,
        frontend,
        extra_env={"NIGHTCRATE_TEST_BASE_PORT": str(base)},
    )
    try:
        ready = json.loads(output.wait_for("NIGHTCRATE_READY ").split(" ", 1)[1])
        assert ready == {"port": base + 1}
        _close_stdin(process)
        assert process.wait(timeout=15) == 0
    finally:
        occupied.close()
        _cleanup(process)


def _pid_exists(pid):
    if os.name == "nt":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True,
            text=True,
            check=False,
        )
        return str(pid) in result.stdout
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def test_shell_eof_kills_busy_workers(tmp_path):
    frontend = _frontend(tmp_path)
    pids = []
    process, output = _spawn(
        tmp_path,
        frontend,
        port=_free_port(),
        extra_env={
            "NIGHTCRATE_TEST_BUSY_POOL": "2",
            "NIGHTCRATE_TEST_STARTUP_DELAY": "60",
        },
    )
    try:
        line = output.wait_for("NIGHTCRATE_TEST_POOL_PIDS", timeout=15)
        pids = json.loads(line.split(" ", 1)[1])
        assert len(pids) == 4
        output.wait_for("NIGHTCRATE_ALIVE", timeout=8)
        _close_stdin(process)
        assert process.wait(timeout=20) == 6
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and any(_pid_exists(pid) for pid in pids):
            time.sleep(0.05)
        assert all(not _pid_exists(pid) for pid in pids)
    finally:
        _cleanup(process)
        if os.name != "nt":
            for pid in pids:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
