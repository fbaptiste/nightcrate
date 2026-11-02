"""In-memory progress for the single explicit catalog operation.

The registry deliberately has no database or FastAPI dependency.  Catalog
actions are admitted synchronously on the event loop, so checking and claiming
the one slot is atomic before an endpoint reaches its first ``await``.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Literal

CatalogOutcome = Literal["success", "warning", "failed"]

RETAIN_FINISHED_S = 300.0


@dataclass(frozen=True, slots=True)
class ProgressUpdate:
    phase: str
    message: str
    bytes_received: int = 0
    bytes_total: int | None = None


ProgressCallback = Callable[[ProgressUpdate], None]


@dataclass(frozen=True, slots=True)
class _Operation:
    operation_id: str
    action: str
    source: str | None
    phase: str
    message: str
    bytes_received: int
    bytes_total: int | None
    phase_started: float
    outcome: CatalogOutcome | None = None
    detail: str | None = None
    finished_at: float | None = None


class CatalogOperationConflict(RuntimeError):
    """Raised when an explicit catalog action already owns the slot."""


_current: _Operation | None = None
_clock: Callable[[], float] = time.monotonic


def start(action: str, *, source: str | None = None) -> str:
    """Atomically claim the catalog-action slot and return its opaque ID."""
    global _current

    now = _clock()
    if _current is not None and _current.outcome is None:
        raise CatalogOperationConflict("Another catalog update is running.")
    operation_id = uuid.uuid4().hex
    _current = _Operation(
        operation_id=operation_id,
        action=action,
        source=source,
        phase="starting",
        message="Starting catalog update…",
        bytes_received=0,
        bytes_total=None,
        phase_started=now,
    )
    return operation_id


def update(operation_id: str, progress: ProgressUpdate) -> bool:
    """Apply an update only when *operation_id* still owns the slot."""
    global _current

    current = _current
    if current is None or current.operation_id != operation_id or current.outcome is not None:
        return False
    phase_started = current.phase_started
    if progress.phase != current.phase or progress.message != current.message:
        phase_started = _clock()
    _current = replace(
        current,
        phase=progress.phase,
        message=progress.message,
        bytes_received=max(0, progress.bytes_received),
        bytes_total=progress.bytes_total
        if progress.bytes_total is None
        else max(0, progress.bytes_total),
        phase_started=phase_started,
    )
    return True


def finish(
    operation_id: str,
    *,
    outcome: CatalogOutcome,
    message: str,
    detail: str | None = None,
) -> bool:
    """Finish the matching operation; stale finalizers are ignored."""
    global _current

    current = _current
    if current is None or current.operation_id != operation_id or current.outcome is not None:
        return False
    now = _clock()
    _current = replace(
        current,
        phase="finished",
        message=message,
        bytes_received=current.bytes_received,
        bytes_total=current.bytes_total,
        phase_started=now,
        outcome=outcome,
        detail=detail,
        finished_at=now,
    )
    return True


def snapshot() -> dict | None:
    """Return the active or retained operation, expiring old results."""
    global _current

    current = _current
    now = _clock()
    if (
        current is not None
        and current.finished_at is not None
        and now - current.finished_at >= RETAIN_FINISHED_S
    ):
        _current = None
        return None
    if current is None:
        return None
    return {
        "operation_id": current.operation_id,
        "action": current.action,
        "source": current.source,
        "phase": current.phase,
        "message": current.message,
        "bytes_received": current.bytes_received,
        "bytes_total": current.bytes_total,
        "phase_elapsed_s": max(0.0, now - current.phase_started),
        "outcome": current.outcome,
        "detail": current.detail,
    }


def callback(operation_id: str) -> ProgressCallback:
    """Build the ID-carrying callback passed through the fetch layers."""

    def _report(progress: ProgressUpdate) -> None:
        update(operation_id, progress)

    return _report


def reset() -> None:
    """Clear process-local state. Intended for test isolation."""
    global _current
    _current = None
