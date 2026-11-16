"""Cross-platform single-instance lock scoped to the app-data folder."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import BinaryIO

from nightcrate.core import app_config
from nightcrate.core.runtime import InstallKind
from nightcrate.db.durable_fs import durable_remove, durable_write


@dataclass(frozen=True)
class InstanceInfo:
    pid: int
    kind: InstallKind
    version: str
    port: int | None


class InstanceLockHeld(RuntimeError):
    def __init__(self, info: InstanceInfo | None):
        super().__init__("NightCrate is already running")
        self.info = info


class InstanceLock:
    def __init__(self, stream: BinaryIO, info_path: Path):
        self._stream = stream
        self._info_path = info_path
        self._released = False

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        try:
            durable_remove(self._info_path)
        finally:
            if os.name == "nt":
                import msvcrt

                self._stream.seek(0)
                msvcrt.locking(self._stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._stream.fileno(), fcntl.LOCK_UN)
            self._stream.close()


def read_instance_info() -> InstanceInfo | None:
    path = app_config.APP_DIR / "instance.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("kind") not in ("installed", "source"):
            return None
        return InstanceInfo(
            pid=int(data["pid"]),
            kind=data["kind"],
            version=str(data["version"]),
            port=int(data["port"]) if data.get("port") is not None else None,
        )
    except OSError, KeyError, TypeError, ValueError, json.JSONDecodeError:
        return None


def acquire_instance_lock(kind: InstallKind, version: str, port: int | None) -> InstanceLock:
    app_config.APP_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = app_config.APP_DIR / "instance.lock"
    stream = lock_path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt

            stream.seek(0)
            if stream.read(1) == b"":
                stream.write(b"\0")
                stream.flush()
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise InstanceLockHeld(read_instance_info()) from exc
        else:
            import fcntl

            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise InstanceLockHeld(read_instance_info()) from exc
        info = InstanceInfo(pid=os.getpid(), kind=kind, version=version, port=port)
        durable_write(
            app_config.APP_DIR / "instance.json",
            json.dumps(asdict(info), separators=(",", ":")).encode(),
        )
        return InstanceLock(stream, app_config.APP_DIR / "instance.json")
    except Exception:
        if not stream.closed:
            stream.close()
        raise
