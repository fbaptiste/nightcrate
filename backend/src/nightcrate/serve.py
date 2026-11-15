"""Production backend entrypoint and built-frontend server."""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send

from nightcrate.core import child_processes, runtime
from nightcrate.core.app_config import set_app_dir
from nightcrate.core.instance_lock import InstanceLockHeld, acquire_instance_lock

EXIT_LOCK_HELD = 3
EXIT_NO_PORT = 4
EXIT_NO_FRONTEND = 5
EXIT_DEADLINE = 6


def _deadline_exit() -> None:
    child_processes.begin_shutdown()
    try:
        child_processes.terminate_all()
    finally:
        os._exit(EXIT_DEADLINE)


def choose_port(preferred: int, extra: int) -> socket.socket:
    """Bind and return the first available loopback socket in a port range."""
    last_error: OSError | None = None
    for port in range(preferred, preferred + extra + 1):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", port))
            return sock
        except OSError as exc:
            last_error = exc
            sock.close()
    raise OSError("No available port in requested range") from last_error


class _ExactHostMiddleware:
    def __init__(self, app: ASGIApp, port: int):
        self.app = app
        self.allowed = {f"127.0.0.1:{port}".encode(), f"localhost:{port}".encode()}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            host = next((value for key, value in scope["headers"] if key == b"host"), b"")
            if host not in self.allowed:
                response = PlainTextResponse("Invalid host header", status_code=400)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def configure_production(app: FastAPI, frontend_dir: Path, port: int) -> None:
    """Add exact-host validation and built SPA serving to an API app."""
    root = frontend_dir.resolve()
    app.add_middleware(_ExactHostMiddleware, port=port)
    app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa_fallback(path: str):
        if path.startswith(("api/", "docs", "redoc", "openapi.json")):
            raise HTTPException(status_code=404)
        candidate = (root / path).resolve()
        if candidate.is_relative_to(root) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(root / "index.html")


def _default_frontend_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "frontend"
    return Path(__file__).resolve().parents[3] / "frontend" / "dist"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nightcrate")
    parser.add_argument("--port", type=int)
    parser.add_argument("--shell", action="store_true")
    parser.add_argument("--app-dir", type=Path)
    parser.add_argument("--frontend-dir", type=Path)
    parser.add_argument("--open-browser", action="store_true")
    parser.add_argument("--version", action="store_true")
    parser.add_argument("--test-manifest-url")
    parser.add_argument("--test-releases-url")
    return parser


def main(argv: list[str] | None = None) -> int:
    multiprocessing.freeze_support()
    runtime.production = True
    args = _parser().parse_args(argv)
    if args.shell:
        runtime.install_kind = "installed"
    if args.app_dir is not None:
        set_app_dir(args.app_dir)
        runtime.log_dir = args.app_dir / "logs"
    if args.version:
        print(runtime.app_version())
        return 0
    if args.test_manifest_url or args.test_releases_url:
        from nightcrate.services.update_check import set_test_urls

        try:
            set_test_urls(args.test_manifest_url, args.test_releases_url)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    frontend_dir = args.frontend_dir or _default_frontend_dir()
    if not (frontend_dir / "index.html").is_file() or not (frontend_dir / "assets").is_dir():
        print(
            f"Frontend build not found at {frontend_dir}. "
            "Build the frontend first: cd frontend && npm run build",
            file=sys.stderr,
        )
        return EXIT_NO_FRONTEND

    preferred = args.port
    if preferred is None:
        preferred = int(os.getenv("NIGHTCRATE_TEST_BASE_PORT", "8765"))
        extra = 10
    else:
        extra = 0
    try:
        sock = choose_port(preferred, extra)
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_NO_PORT
    port = sock.getsockname()[1]

    try:
        instance_lock = acquire_instance_lock(runtime.install_kind, runtime.app_version(), port)
    except InstanceLockHeld as exc:
        sock.close()
        info = exc.info
        print(
            "NIGHTCRATE_LOCKED "
            + json.dumps(
                {
                    "kind": info.kind if info else None,
                    "pid": info.pid if info else None,
                    "version": info.version if info else None,
                },
                separators=(",", ":"),
            ),
            flush=True,
        )
        return EXIT_LOCK_HELD

    # Import only after runtime.production is set, so main omits development CORS.
    from nightcrate.main import app

    configure_production(app, frontend_dir, port)
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        timeout_graceful_shutdown=10,
    )
    server = uvicorn.Server(config)
    deadline: threading.Timer | None = None
    ready = threading.Event()

    runtime.report_step("starting")
    stop_heartbeat = runtime.start_heartbeat()

    def report_ready() -> None:
        while not server.started and not server.should_exit:
            time.sleep(0.01)
        if not server.started:
            return
        stop_heartbeat()
        ready.set()
        print(f"NIGHTCRATE_READY {json.dumps({'port': port}, separators=(',', ':'))}", flush=True)
        if args.open_browser:
            webbrowser.open(f"http://127.0.0.1:{port}")

    threading.Thread(target=report_ready, name="nightcrate-ready", daemon=True).start()

    def watch_stdin() -> None:
        nonlocal deadline
        sys.stdin.buffer.read()
        server.should_exit = True
        deadline = threading.Timer(10, _deadline_exit)
        deadline.daemon = True
        deadline.start()

    if args.shell:
        threading.Thread(target=watch_stdin, name="nightcrate-shell-watch", daemon=True).start()

    try:
        server.run(sockets=[sock])
        return 0
    finally:
        stop_heartbeat()
        if deadline is not None:
            deadline.cancel()
        child_processes.begin_shutdown()
        child_processes.terminate_all()
        instance_lock.release()
        sock.close()
        ready.set()


if __name__ == "__main__":
    raise SystemExit(main())
