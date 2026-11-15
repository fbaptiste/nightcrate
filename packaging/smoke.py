#!/usr/bin/env python3
"""End-to-end smoke test for a frozen NightCrate backend."""

from __future__ import annotations

import json
import os
import queue
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import closing
from pathlib import Path

from make_test_data import make_data

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def process_exists(pid: int) -> bool:
    if sys.platform == "win32":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            check=False,
            capture_output=True,
            text=True,
        )
        return f'"{pid}"' in result.stdout
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


class Backend:
    def __init__(self, executable: Path, app_dir: Path, port: int):
        env = os.environ.copy()
        env["NIGHTCRATE_TEST_BUSY_POOL"] = "2"
        self.process = subprocess.Popen(
            [
                str(executable),
                "--shell",
                "--app-dir",
                str(app_dir),
                "--port",
                str(port),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
        self.lines: queue.Queue[str] = queue.Queue()
        self.all_lines: list[str] = []
        self.worker_pids: list[int] = []
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            line = line.rstrip()
            print(line)
            self.all_lines.append(line)
            if line.startswith("NIGHTCRATE_TEST_POOL_PIDS "):
                self.worker_pids = json.loads(line.split(" ", 1)[1])
            self.lines.put(line)

    def wait_ready(self) -> None:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            try:
                line = self.lines.get(timeout=1)
            except queue.Empty:
                if self.process.poll() is not None:
                    break
                continue
            if line.startswith("NIGHTCRATE_READY "):
                return
        raise RuntimeError(
            "backend did not become ready:\n" + "\n".join(self.all_lines[-20:])
        )

    def stop(self) -> None:
        if self.process.stdin is not None:
            self.process.stdin.close()
        try:
            exit_code = self.process.wait(timeout=15)
        except subprocess.TimeoutExpired as exc:
            self.process.kill()
            raise RuntimeError("backend did not exit within 15 seconds") from exc
        if exit_code != 0:
            raise RuntimeError(f"backend exited with {exit_code}")
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and any(
            process_exists(pid) for pid in self.worker_pids
        ):
            time.sleep(0.1)
        survivors = [pid for pid in self.worker_pids if process_exists(pid)]
        if survivors:
            raise RuntimeError(f"backend children survived shutdown: {survivors}")


class Client:
    def __init__(self, port: int):
        self.origin = f"http://127.0.0.1:{port}"

    def request(self, method: str, path: str, body: object | None = None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            self.origin + path,
            data=data,
            method=method,
            headers={"content-type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=300) as response:
            content = response.read()
            if "json" in response.headers.get("content-type", ""):
                return json.loads(content)
            return response.headers.get("content-type", ""), content


def check_database(workspace: Path) -> None:
    database = workspace / "nightcrate.db"
    # closing(): sqlite3's own context manager only commits; an open handle
    # keeps Windows from deleting the temporary workspace afterwards.
    with closing(sqlite3.connect(database)) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        applied = {
            row[0]
            for row in connection.execute("SELECT migration_id FROM _yoyo_migration")
        }
    expected = {
        path.stem
        for path in (ROOT / "backend/src/nightcrate/db/migrations").iterdir()
        if path.suffix in {".sql", ".py"}
        and path.name != "__init__.py"
        and ".rollback." not in path.name
    }
    if integrity != "ok" or foreign_keys or applied != expected:
        raise RuntimeError(
            f"database check failed: integrity={integrity!r}, foreign_keys={foreign_keys!r}, "
            f"missing={sorted(expected - applied)!r}, extra={sorted(applied - expected)!r}"
        )


def check_shell_gone(executable: Path, app_dir: Path) -> None:
    """A force-quit shell closes stdin and stdout together; nothing may survive.

    The frozen interpreter leaves SIGPIPE at its default; before v0.54.0's fix
    the backend died logging its shutdown and left its workers running.
    """
    env = os.environ.copy()
    env["NIGHTCRATE_TEST_BUSY_POOL"] = "2"
    group = {} if sys.platform == "win32" else {"process_group": 0}
    process = subprocess.Popen(
        [
            str(executable),
            "--shell",
            "--app-dir",
            str(app_dir),
            "--port",
            str(free_port()),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
        **group,
    )
    pids: list[int] = []
    try:
        assert process.stdout is not None and process.stdin is not None
        ready = False
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline and not (pids and ready):
            line = process.stdout.readline()
            if not line:
                break
            print(line.rstrip())
            if line.startswith("NIGHTCRATE_TEST_POOL_PIDS "):
                pids = json.loads(line.split(" ", 1)[1])
            ready = ready or line.startswith("NIGHTCRATE_READY ")
        if not (pids and ready):
            raise RuntimeError("backend did not become ready with its test workers")
        process.stdout.close()
        process.stdin.close()
        exit_code = process.wait(timeout=15)
        if exit_code != 0:
            raise RuntimeError(
                f"backend exited with {exit_code} after its shell went away"
            )
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and _survivors(process.pid, pids):
            time.sleep(0.1)
        survivors = _survivors(process.pid, pids)
        if survivors:
            raise RuntimeError(f"processes survived the shell going away: {survivors}")
    finally:
        if process.poll() is None:
            process.kill()
        if sys.platform != "win32":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def _survivors(group_id: int, pids: list[int]) -> list[object]:
    survivors: list[object] = [pid for pid in pids if process_exists(pid)]
    if sys.platform != "win32":
        try:
            os.killpg(group_id, 0)
        except ProcessLookupError:
            pass
        else:
            survivors.append(f"process group {group_id}")
    return survivors


def run(build_dir: Path) -> None:
    executable = build_dir / (
        "nightcrate-backend.exe" if sys.platform == "win32" else "nightcrate-backend"
    )
    with tempfile.TemporaryDirectory(prefix="nightcrate-smoke-") as scratch_value:
        scratch = Path(scratch_value)
        app_dir = scratch / "App Data with accents é"
        workspace = scratch / "My NightCrate é"
        data_dir = scratch / "twenty lights"
        app_dir.mkdir()
        make_data(data_dir)
        port = free_port()
        backend = Backend(executable, app_dir, port)
        client = Client(port)
        try:
            backend.wait_ready()
            health = client.request("GET", "/api/health")
            version = subprocess.run(
                [str(executable), "--version"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            if health["version"] != version or health["install_kind"] != "installed":
                raise RuntimeError(f"unexpected health response: {health!r}")

            client.request(
                "POST",
                "/api/admin/database/setup",
                {"path": str(workspace), "name": "Smoke"},
            )
            check_database(workspace)
            client.request("PATCH", "/api/settings", {"max_worker_cores": 1})
            project = client.request(
                "POST", "/api/projects", {"name": "Smoke NGC 7000"}
            )
            client.request(
                "POST",
                f"/api/projects/{project['id']}/folders",
                {"path": str(data_dir)},
            )
            ingest = client.request("POST", f"/api/projects/{project['id']}/ingest")
            if ingest["status"] != "completed" or ingest["subs_inserted"] != 20:
                raise RuntimeError(f"unexpected ingest result: {ingest!r}")
            summary = client.request(
                "GET", f"/api/projects/{project['id']}/catalog/summary"
            )
            if summary["lights"] != 20 or summary["sessions"] != 2:
                raise RuntimeError(f"unexpected catalog summary: {summary!r}")

            for name in ("Light_NGC7000_Ha_000.fits", "Light_NGC7000_OIII_000.xisf"):
                path = urllib.parse.quote(str(data_dir / name))
                content_type, png = client.request(
                    "GET", f"/api/images/image?path={path}"
                )
                if not content_type.startswith("image/png") or len(png) < 1000:
                    raise RuntimeError(
                        f"failed to render {name}: {content_type}, {len(png)} bytes"
                    )

            compute = client.request("GET", "/api/settings/compute")
            if sys.platform == "darwin" and compute["gpu_backend"] != "mlx":
                raise RuntimeError(f"macOS smoke test did not load mlx: {compute!r}")
            _, deep_link = client.request("GET", "/projects")
            if b'id="root"' not in deep_link:
                raise RuntimeError("deep link did not return the frontend index")

            bad_host = urllib.request.Request(
                client.origin + "/api/health", headers={"Host": "evil.example"}
            )
            try:
                urllib.request.urlopen(bad_host, timeout=10)
            except urllib.error.HTTPError as exc:
                if exc.code != 400:
                    raise
            else:
                raise RuntimeError("bad Host header was accepted")
        finally:
            backend.stop()
        check_shell_gone(executable, app_dir)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: smoke.py <frozen-backend-dir>", file=sys.stderr)
        return 2
    run(Path(sys.argv[1]).resolve())
    print("Frozen backend smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
