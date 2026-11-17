"""Process-local progress for the single active ingest scan."""

from __future__ import annotations

import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from nightcrate.services.ingest_sessions import folder_prefix

if TYPE_CHECKING:
    from nightcrate.services.ingest_models import IngestStatus

IngestStage = Literal["listing", "reading", "saving", "grouping"]

RETAIN_FINISHED_S = 300.0


@dataclass(slots=True)
class _Scan:
    scan_id: str
    workspace: str
    project_id: int
    run_id: int
    folder: str | None = None
    stage: IngestStage = "listing"
    done: int = 0
    total: int = 0
    recent: deque[dict] = field(default_factory=lambda: deque(maxlen=10))
    result: IngestStatus | None = None
    finished_at: float | None = None


_active: _Scan | None = None
_finished: dict[tuple[str, int], _Scan] = {}
_clock: Callable[[], float] = time.monotonic


def start(workspace: str, project_id: int, run_id: int) -> str:
    """Start a scan record and discard this project's older retained result."""
    global _active

    key = (workspace, project_id)
    _finished.pop(key, None)
    scan_id = uuid.uuid4().hex
    _active = _Scan(
        scan_id=scan_id,
        workspace=workspace,
        project_id=project_id,
        run_id=run_id,
    )
    return scan_id


def folder(value: str) -> None:
    """Move to a folder and reset its per-folder counts and recent paths."""
    if _active is None:
        return
    _active.folder = value
    _active.done = 0
    _active.total = 0
    _active.recent.clear()


def stage(value: IngestStage) -> None:
    if _active is not None:
        _active.stage = value


def total(value: int) -> None:
    if _active is not None:
        _active.total = max(0, value)


def file_read(path: str, ok: bool) -> None:
    """Record a completed header read, relative to the current folder when possible."""
    if _active is None:
        return
    prefix = folder_prefix(_active.folder) if _active.folder is not None else ""
    shown = path[len(prefix) :] if prefix and path.startswith(prefix) else path
    _active.done += 1
    _active.recent.append({"path": shown, "ok": ok})


def finish(result: IngestStatus) -> None:
    """Retain the active scan as this project's latest finished result."""
    global _active

    if _active is None:
        return
    _active.result = result
    _active.finished_at = _clock()
    _finished[(_active.workspace, _active.project_id)] = _active
    _active = None


def _prune(now: float) -> None:
    expired = [
        key
        for key, scan in _finished.items()
        if scan.finished_at is not None and now - scan.finished_at >= RETAIN_FINISHED_S
    ]
    for key in expired:
        del _finished[key]


def snapshot(workspace: str, project_id: int) -> dict | None:
    """Return this project's active scan or its retained finished scan."""
    now = _clock()
    _prune(now)
    key = (workspace, project_id)
    scan = (
        _active
        if _active is not None and (_active.workspace, _active.project_id) == key
        else _finished.get(key)
    )
    if scan is None:
        return None
    return {
        "scan_id": scan.scan_id,
        "run_id": scan.run_id,
        "running": scan.finished_at is None,
        "folder": scan.folder,
        "stage": scan.stage,
        "done": scan.done,
        "total": scan.total,
        "recent": list(scan.recent),
        "result": scan.result,
    }


def reset() -> None:
    """Clear process-local state. Intended for test isolation."""
    global _active
    _active = None
    _finished.clear()
