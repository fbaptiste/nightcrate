#!/usr/bin/env python3
"""Drive the installed A -> bad-signature C -> signed B update rehearsal."""

from __future__ import annotations

import argparse
import json
import platform
import queue
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

UPDATE_PORT = 48123
PROBE_PORT = 48124
BACKEND_PORT = 48125


def request(method: str, path: str, body: object | None = None, timeout: float = 30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"http://127.0.0.1:{BACKEND_PORT}{path}",
        data=data,
        method=method,
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        content = response.read()
        return json.loads(content) if content else None


def wait_for(predicate, description: str, timeout: float = 600):
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            value = predicate()
            if value:
                return value
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last_error = exc
        time.sleep(0.25)
    suffix = f": {last_error}" if last_error else ""
    raise RuntimeError(f"timed out waiting for {description}{suffix}")


class Backend:
    def __init__(self, executable: Path, app_dir: Path):
        self.process = subprocess.Popen(
            [
                str(executable),
                "--shell",
                "--app-dir",
                str(app_dir),
                "--port",
                str(BACKEND_PORT),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.lines: queue.Queue[str] = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            print(line, end="")
            self.lines.put(line.rstrip())

    def wait_ready(self) -> None:
        def ready():
            try:
                return self.lines.get(timeout=0.25).startswith("NIGHTCRATE_READY ")
            except queue.Empty:
                if self.process.poll() is not None:
                    raise RuntimeError(
                        f"provisioning backend exited with {self.process.returncode}"
                    )
                return False

        wait_for(ready, "the provisioning backend", 120)

    def stop(self) -> None:
        assert self.process.stdin is not None
        self.process.stdin.close()
        if self.process.wait(timeout=30) != 0:
            raise RuntimeError("provisioning backend did not stop cleanly")


class State:
    def __init__(self, archive: Path, good_signature: str, bad_signature: str, target: str):
        self.archive = archive
        self.good_signature = good_signature
        self.bad_signature = bad_signature
        self.target = target
        self.good = False
        self.probe_report: dict[str, object] | None = None

    def manifest(self) -> bytes:
        signature = self.good_signature if self.good else self.bad_signature
        value = {
            "version": "0.0.2",
            "notes": "Update rehearsal B",
            "pub_date": "2026-11-15T00:00:00Z",
            "platforms": {
                self.target: {
                    "url": f"http://127.0.0.1:{UPDATE_PORT}/update{self.archive.suffix}",
                    "signature": signature,
                }
            },
        }
        return (json.dumps(value) + "\n").encode()


def handlers(state: State, probe_html: bytes):
    class UpdateHandler(BaseHTTPRequestHandler):
        def do_OPTIONS(self):  # noqa: N802
            self.send_response(204)
            self.send_header("access-control-allow-origin", "*")
            self.send_header("access-control-allow-headers", "content-type")
            self.send_header("access-control-allow-methods", "POST, OPTIONS")
            self.end_headers()

        def do_GET(self):  # noqa: N802
            if self.path == "/latest.json":
                self._send(state.manifest(), "application/json")
            elif self.path == "/release.json":
                value = {
                    "tag_name": "v0.0.2",
                    "published_at": "2026-11-15T00:00:00Z",
                    "html_url": "https://github.com/fbaptiste/nightcrate/releases/tag/v0.0.2",
                    "body": "Update rehearsal B",
                }
                self._send(json.dumps(value).encode(), "application/json")
            elif self.path.startswith("/update"):
                self._send(state.archive.read_bytes(), "application/octet-stream")
            else:
                self.send_error(404)

        def do_POST(self):  # noqa: N802
            if self.path != "/probe-report":
                self.send_error(404)
                return
            length = int(self.headers.get("content-length", "0"))
            state.probe_report = json.loads(self.rfile.read(length))
            self._send(b"{}", "application/json", cors=True)

        def _send(self, data: bytes, content_type: str, *, cors: bool = False):
            self.send_response(200)
            self.send_header("content-type", content_type)
            self.send_header("content-length", str(len(data)))
            if cors:
                self.send_header("access-control-allow-origin", "*")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, fmt: str, *args) -> None:
            print(f"[update-server] {fmt % args}")

    class ProbeHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if urllib.parse.urlsplit(self.path).path != "/probe.html":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("content-length", str(len(probe_html)))
            self.end_headers()
            self.wfile.write(probe_html)

        def log_message(self, fmt: str, *args) -> None:
            print(f"[probe-server] {fmt % args}")

    return UpdateHandler, ProbeHandler


def platform_target() -> str:
    system = platform.system()
    machine = platform.machine().lower()
    if system == "Darwin" and machine in {"arm64", "aarch64"}:
        return "darwin-aarch64"
    if system == "Linux" and machine in {"x86_64", "amd64"}:
        return "linux-x86_64"
    if system == "Windows" and machine in {"x86_64", "amd64"}:
        return "windows-x86_64"
    raise RuntimeError(f"unsupported rehearsal platform: {system} {machine}")


def database_facts(database: Path) -> dict[str, object]:
    with closing(sqlite3.connect(database)) as connection:
        return {
            "projects": connection.execute("SELECT COUNT(*) FROM project").fetchone()[0],
            "locations": connection.execute("SELECT COUNT(*) FROM location").fetchone()[0],
            "subs": connection.execute("SELECT COUNT(*) FROM sub_frame").fetchone()[0],
            "images": connection.execute("SELECT COUNT(*) FROM project_image").fetchone()[0],
            "project_location": connection.execute(
                "SELECT p.name, l.name FROM project p JOIN location l ON l.id = p.location_id"
            ).fetchall(),
            "foreign_keys": connection.execute("PRAGMA foreign_key_check").fetchall(),
            "integrity": connection.execute("PRAGMA integrity_check").fetchone()[0],
        }


def provision(
    backend_path: Path, app_dir: Path, workspace: Path, data_dir: Path
) -> dict[str, object]:
    backend = Backend(backend_path, app_dir)
    try:
        backend.wait_ready()
        request(
            "POST",
            "/api/admin/database/setup",
            {"path": str(workspace), "name": "Rehearsal"},
        )
        request("PATCH", "/api/settings", {"max_worker_cores": 1})
        location = request(
            "POST",
            "/api/locations",
            {
                "name": "Rehearsal Site",
                "latitude": 33.4484,
                "longitude": -112.0740,
                "timezone": "America/Phoenix",
            },
        )
        project = request("POST", "/api/projects", {"name": "Rehearsal NGC 7000"})
        request("PATCH", f"/api/projects/{project['id']}", {"location_id": location["id"]})
        request("POST", f"/api/projects/{project['id']}/folders", {"path": str(data_dir)})
        ingest = request("POST", f"/api/projects/{project['id']}/ingest", timeout=300)
        if ingest["status"] != "completed" or ingest["subs_inserted"] != 20:
            raise RuntimeError(f"unexpected ingest result: {ingest!r}")
        image = data_dir / "Light_NGC7000_Ha_000.fits"
        request(
            "POST",
            f"/api/projects/{project['id']}/images",
            {"file_paths": [str(image)]},
            300,
        )
        return database_facts(workspace / "nightcrate.db")
    finally:
        backend.stop()


def verify_preservation(workspace: Path, data_dir: Path, before: dict[str, object]) -> None:
    database = workspace / "nightcrate.db"
    after = database_facts(database)
    if after != before or after["integrity"] != "ok" or after["foreign_keys"]:
        raise RuntimeError(f"workspace changed: before={before!r}, after={after!r}")
    if not (data_dir / "Light_NGC7000_Ha_000.fits").is_file():
        raise RuntimeError("project image file was lost")
    backups = list((workspace / "backups").glob("nightcrate-before-0.0.2-*.db"))
    if len(backups) != 1:
        listing = sorted(
            str(path.relative_to(workspace))
            for path in workspace.rglob("*")
            if "project_data" not in path.parts
        )
        raise RuntimeError(
            f"expected one 0.0.2 backup, found {backups!r}; workspace holds {listing!r}"
        )
    backup_facts = database_facts(backups[0])
    if backup_facts != before or backup_facts["integrity"] != "ok":
        raise RuntimeError(f"backup did not preserve records: {backup_facts!r}")
    if (workspace / "backups" / "upgrade-in-progress.json").exists():
        raise RuntimeError("upgrade marker remained after successful launch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", type=Path, required=True)
    parser.add_argument("--app-dir", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--good-signature", type=Path, required=True)
    parser.add_argument("--bad-signature", type=Path, required=True)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("app_command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.app_command[:1] == ["--"]:
        args.app_command = args.app_command[1:]
    if not args.app_command:
        parser.error("an installed-app launch command is required")

    args.app_dir.mkdir(parents=True, exist_ok=True)
    before = provision(args.backend, args.app_dir, args.workspace, args.data_dir)
    state = State(
        args.archive,
        args.good_signature.read_text(encoding="utf-8"),
        args.bad_signature.read_text(encoding="utf-8"),
        platform_target(),
    )
    update_handler, probe_handler = handlers(state, args.probe.read_bytes())
    update_server = ThreadingHTTPServer(("127.0.0.1", UPDATE_PORT), update_handler)
    probe_server = ThreadingHTTPServer(("127.0.0.1", PROBE_PORT), probe_handler)
    threading.Thread(target=update_server.serve_forever, daemon=True).start()
    threading.Thread(target=probe_server.serve_forever, daemon=True).start()

    process = subprocess.Popen(args.app_command)
    log_path = args.app_dir / "logs" / "shell.log"
    try:
        wait_for(
            lambda: (
                log_path.is_file()
                and f"main loaded http://127.0.0.1:{BACKEND_PORT}/"
                in log_path.read_text(errors="replace")
            ),
            "the main-window backend load",
            120,
        )
        wait_for(
            lambda: (
                log_path.is_file()
                and f"main loaded http://127.0.0.1:{PROBE_PORT}/probe.html"
                in log_path.read_text(errors="replace")
            ),
            "the probe-window load",
            60,
        )
        report = wait_for(lambda: state.probe_report, "the probe report", 60)
        rejected_for_acl = report.get("outcome") == "invoke-rejected" and any(
            word in str(report.get("error", "")).lower()
            for word in ("not allowed", "permission", "denied", "acl")
        )
        if report.get("outcome") != "no-bridge" and not rejected_for_acl:
            raise RuntimeError(f"probe crossed the origin boundary: {report!r}")

        wait_for(lambda: request("GET", "/api/health")["version"] == "0.0.1", "A health", 120)
        request("PATCH", "/api/updates/preferences", {"check_automatically": True})
        request("POST", "/api/updates/check")
        wait_for(
            lambda: "install_update failed" in log_path.read_text(errors="replace"),
            "the bad-signature failure",
            180,
        )
        if request("GET", "/api/health")["version"] != "0.0.1":
            raise RuntimeError("bad signature stopped or replaced A")
        reservation = request("POST", "/api/app/install-reservation")
        if "token" not in reservation:
            raise RuntimeError(f"reservation was not released: {reservation!r}")
        request(
            "DELETE",
            "/api/app/install-reservation?token=" + urllib.parse.quote(reservation["token"]),
        )

        state.good = True
        request("POST", "/api/updates/check")
        wait_for(lambda: request("GET", "/api/health")["version"] == "0.0.2", "B health", 600)
        verify_preservation(args.workspace, args.data_dir, before)
        print("Update rehearsal passed")
        return 0
    finally:
        update_server.shutdown()
        probe_server.shutdown()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
