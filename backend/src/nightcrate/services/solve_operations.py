"""Identity-scoped lifetime, cancellation, and progress for plate solves."""

from __future__ import annotations

import asyncio
import threading
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from nightcrate.services.plate_solve_models import (
    AttemptOutcome,
    SolveAttempt,
    SolveStep,
)

_PENDING_LIMIT = 64
_PENDING_SECONDS = 600.0
_FINISHED_LIMIT = 16
_FINISHED_SECONDS = 60.0
_USED_LIMIT = 1024


class SolveBusy(RuntimeError):
    """The process-wide solve/publication slot is occupied."""


class SolveCancelled(RuntimeError):
    """The requested operation was cancelled before or during its lifetime."""


class CancelResult(BaseModel):
    cancelled: bool
    pending: bool


class ProgressSnapshot(BaseModel):
    operation_id: UUID
    solver: Literal["native", "astap"]
    attempts: list[SolveAttempt]
    active_step: SolveAttempt | None
    planned: list[SolveStep]
    elapsed_seconds: float
    state: Literal["running", "finished"]


class SolveOperation:
    """One endpoint-owned solve operation and its thread-safe reporter state."""

    def __init__(self, operation_id: UUID, solver: Literal["native", "astap"]) -> None:
        self.operation_id = operation_id
        self.solver = solver
        self.stop = threading.Event()
        self.started_at = time.monotonic()
        self._lock = threading.Lock()
        self._attempts: list[SolveAttempt] = []
        self._active_step: SolveAttempt | None = None
        self._active_started = 0.0
        self._planned: list[SolveStep] = []
        self._cancellable = True
        self.task: asyncio.Task | None = None
        self.process: asyncio.subprocess.Process | None = None

    def plan(self, steps: list[SolveStep]) -> None:
        with self._lock:
            self._planned = list(steps)

    def start(self, attempt: SolveAttempt) -> None:
        with self._lock:
            self._active_step = attempt.model_copy(deep=True)
            self._active_started = time.monotonic()
            if attempt.step in self._planned:
                self._planned.remove(attempt.step)

    def searched(self, layers: list[str], ranges: list[str]) -> None:
        with self._lock:
            if self._active_step is None:
                return
            for layer in layers:
                if layer not in self._active_step.layers:
                    self._active_step.layers.append(layer)
            for range_id in ranges:
                if range_id not in self._active_step.ranges:
                    self._active_step.ranges.append(range_id)

    def set_sources(
        self,
        position_source: Literal["request", "header", "none"],
        scale_source: Literal["request", "header", "none"],
    ) -> None:
        with self._lock:
            if self._active_step is not None:
                self._active_step.position_source = position_source
                self._active_step.scale_source = scale_source

    def finish(self, outcome: AttemptOutcome, *, detail: str | None = None) -> None:
        with self._lock:
            if self._active_step is None:
                return
            attempt = self._active_step
            attempt.outcome = outcome
            attempt.seconds = time.monotonic() - self._active_started
            attempt.detail = detail
            self._attempts.append(attempt)
            self._active_step = None

    def cancel(self) -> bool:
        with self._lock:
            if not self._cancellable:
                return False
            self.stop.set()
        process = self.process
        if process is not None and process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        return True

    def begin_commit(self) -> None:
        """Atomically reject a pending cancel or close the cancellation window."""
        with self._lock:
            if self.stop.is_set():
                raise SolveCancelled("Plate solve cancelled.")
            self._cancellable = False

    def checkpoint(self) -> None:
        if self.stop.is_set():
            raise SolveCancelled("Plate solve cancelled.")

    def attempts(
        self,
        *,
        open_outcome: AttemptOutcome | None = None,
        detail: str | None = None,
    ) -> list[SolveAttempt]:
        with self._lock:
            attempts = [attempt.model_copy(deep=True) for attempt in self._attempts]
            if self._active_step is not None:
                active = self._active_step.model_copy(deep=True)
                if open_outcome is not None:
                    active.outcome = open_outcome
                    active.seconds = max(0.0, time.monotonic() - self._active_started)
                    active.detail = detail
                attempts.append(active)
            return attempts

    def snapshot(self, *, state: Literal["running", "finished"] = "running") -> ProgressSnapshot:
        with self._lock:
            return ProgressSnapshot(
                operation_id=self.operation_id,
                solver=self.solver,
                attempts=[attempt.model_copy(deep=True) for attempt in self._attempts],
                active_step=(
                    self._active_step.model_copy(deep=True)
                    if self._active_step is not None
                    else None
                ),
                planned=list(self._planned),
                elapsed_seconds=max(0.0, time.monotonic() - self.started_at),
                state=state,
            )


_state_lock = threading.Lock()
_active: SolveOperation | None = None
_external_owner = False
_waiters: set[asyncio.Event] = set()
_pending: OrderedDict[UUID, float] = OrderedDict()
_finished: OrderedDict[UUID, tuple[float, ProgressSnapshot]] = OrderedDict()
_used: OrderedDict[UUID, None] = OrderedDict()


def _prune(now: float) -> None:
    while _pending and now - next(iter(_pending.values())) >= _PENDING_SECONDS:
        _pending.popitem(last=False)
    while _finished:
        _, (finished_at, _) = next(iter(_finished.items()))
        if now - finished_at < _FINISHED_SECONDS:
            break
        _finished.popitem(last=False)


def _wake_waiters() -> None:
    for waiter in tuple(_waiters):
        waiter.set()


def _remember_used(operation_id: UUID) -> None:
    _used[operation_id] = None
    _used.move_to_end(operation_id)
    while len(_used) > _USED_LIMIT:
        _used.popitem(last=False)


def claim(operation_id: UUID, solver: Literal["native", "astap"]) -> SolveOperation:
    """Claim the shared slot immediately for an endpoint-owned operation."""
    global _active
    now = time.monotonic()
    with _state_lock:
        _prune(now)
        if operation_id in _used or operation_id in _finished:
            raise SolveBusy("This plate solve operation ID has already been used.")
        cancelled_at = _pending.pop(operation_id, None)
        if cancelled_at is not None and now - cancelled_at < _PENDING_SECONDS:
            _remember_used(operation_id)
            raise SolveCancelled("Plate solve cancelled.")
        if _active is not None or _external_owner:
            raise SolveBusy("A plate solve is already in progress.")
        op = SolveOperation(operation_id, solver)
        _active = op
        _remember_used(operation_id)
        return op


def release(op: SolveOperation) -> None:
    """Finish *op*, retain its snapshot briefly, and free the shared slot."""
    global _active
    with _state_lock:
        if _active is not op:
            return
        op.task = None
        op.process = None
        snapshot = op.snapshot(state="finished")
        _finished[op.operation_id] = (time.monotonic(), snapshot)
        while len(_finished) > _FINISHED_LIMIT:
            _finished.popitem(last=False)
        _active = None
        _wake_waiters()


def cancel(operation_id: UUID) -> CancelResult:
    """Cancel one identified operation."""
    now = time.monotonic()
    with _state_lock:
        _prune(now)
        if _active is not None and _active.operation_id == operation_id:
            return CancelResult(cancelled=_active.cancel(), pending=False)
        if operation_id in _finished or operation_id in _used:
            return CancelResult(cancelled=False, pending=False)
        _pending[operation_id] = now
        _pending.move_to_end(operation_id)
        while len(_pending) > _PENDING_LIMIT:
            _pending.popitem(last=False)
        return CancelResult(cancelled=False, pending=True)


def snapshot(operation_id: UUID) -> ProgressSnapshot | None:
    now = time.monotonic()
    with _state_lock:
        _prune(now)
        if _active is not None and _active.operation_id == operation_id:
            return _active.snapshot()
        item = _finished.get(operation_id)
        return item[1].model_copy(deep=True) if item is not None else None


def active_operation() -> SolveOperation | None:
    with _state_lock:
        return _active


@asynccontextmanager
async def immediate_slot():
    """Claim the shared slot for a short non-solve operation or fail."""
    global _external_owner
    with _state_lock:
        if _active is not None or _external_owner:
            raise SolveBusy("A plate solve is running. Try again when it finishes.")
        _external_owner = True
    try:
        yield
    finally:
        with _state_lock:
            _external_owner = False
            _wake_waiters()


@asynccontextmanager
async def waiting_slot():
    """Wait for the shared slot for star-data publication."""
    global _external_owner
    while True:
        waiter = asyncio.Event()
        with _state_lock:
            if _active is None and not _external_owner:
                _external_owner = True
                break
            _waiters.add(waiter)
        try:
            await waiter.wait()
        finally:
            with _state_lock:
                _waiters.discard(waiter)
    try:
        yield
    finally:
        with _state_lock:
            _external_owner = False
            _wake_waiters()


def _reset_for_tests() -> None:
    """Reset process state; intentionally private and used only by unit tests."""
    global _active, _external_owner
    with _state_lock:
        _active = None
        _external_owner = False
        _waiters.clear()
        _pending.clear()
        _finished.clear()
        _used.clear()
