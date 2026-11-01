from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import shutil
import threading
import time
from collections import deque
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager, suppress
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from nightcrate.services import http_client

from . import handles
from .siril import ChecksumMismatch, decompress_and_verify
from .store import (
    SIRIL_SOURCE,
    AlreadyInstalled,
    catalog_dir,
    catalog_path,
    ensure_free_space,
    installed,
    staging_dir,
    star_root,
    version_payload,
)

logger = logging.getLogger(__name__)


class StarOperationBusy(RuntimeError):
    pass


class StarOperation(BaseModel):
    kind: Literal["download", "import", "build", "remove"]
    state: Literal["running", "done", "failed", "cancelled"] = "running"
    phase: Literal[
        "downloading", "verifying", "unpacking", "copying", "building", "publishing", "removing"
    ]
    bytes_done: int = 0
    bytes_total: int = 0
    speed_bytes_per_s: float | None = None
    ranges: list[str] = Field(default_factory=list)
    current_range: str | None = None
    range_progress: dict[str, float] = Field(default_factory=dict)
    progress: float | None = None
    message: str | None = None


@asynccontextmanager
async def _unlocked_publish() -> AsyncIterator[None]:
    yield


publish_lock: Callable[[], AbstractAsyncContextManager[None]] = _unlocked_publish
_operation: StarOperation | None = None
_task: asyncio.Task[None] | None = None
_async_cancel: asyncio.Event | None = None
_thread_cancel: threading.Event | None = None
_speed_samples: deque[tuple[float, int]] = deque()


def current_operation() -> StarOperation | None:
    return _operation


def _ensure_not_busy() -> None:
    if _operation is not None and _operation.state == "running":
        raise StarOperationBusy("Another star-data task is running.")


def _clean_stale_staging() -> None:
    """Delete what a crashed operation left in staging.

    Only one operation runs at a time, so at claim time a hidden temporary file
    (an interrupted unpack) or a ``build-*`` folder (an interrupted index build)
    belongs to no live operation. The resumable ``.part`` download and a
    verified compressed file are kept.
    """
    stage = staging_dir()
    if not stage.is_dir():
        return
    for item in stage.iterdir():
        try:
            if item.is_dir() and item.name.startswith("build-"):
                shutil.rmtree(item)
            elif item.is_file() and item.name.startswith(".") and item.name.endswith(".tmp"):
                item.unlink()
        except OSError:
            logger.warning("[star_catalog] could not remove stale staging item %s", item)


def _claim(operation: StarOperation, worker: Callable[[], object]) -> StarOperation:
    global _operation, _task, _async_cancel, _thread_cancel
    _ensure_not_busy()
    _clean_stale_staging()
    _operation = operation
    _async_cancel = asyncio.Event()
    _thread_cancel = threading.Event()
    _speed_samples.clear()
    _task = asyncio.create_task(_run(worker), name=f"star-catalog-{operation.kind}")
    return operation


async def _run(worker: Callable[[], object]) -> None:
    if _operation is None:
        raise RuntimeError("star operation was not claimed")
    try:
        result = worker()
        if asyncio.iscoroutine(result):
            await result
        if _operation.state == "running":
            _operation.state = "done"
            _operation.progress = 1.0
    except asyncio.CancelledError, InterruptedError, http_client.OperationCancelled:
        _operation.state = "cancelled"
        _operation.message = "Cancelled."
    except ChecksumMismatch:
        _operation.state = "failed"
        _operation.message = (
            "The downloaded file didn't match its published checksum. Download it again."
        )
    except Exception as exc:
        logger.exception("[star_catalog] %s operation failed", _operation.kind)
        _operation.state = "failed"
        _operation.message = str(exc)


def _progress(done: int) -> None:
    if _operation is None:
        return
    now = time.monotonic()
    _operation.bytes_done = done
    _operation.progress = done / _operation.bytes_total if _operation.bytes_total else None
    _speed_samples.append((now, done))
    while len(_speed_samples) > 1 and _speed_samples[0][0] < now - 10:
        _speed_samples.popleft()
    if len(_speed_samples) > 1:
        elapsed = now - _speed_samples[0][0]
        _operation.speed_bytes_per_s = (done - _speed_samples[0][1]) / elapsed if elapsed else None


def _reset_progress(total: int) -> None:
    if _operation is None:
        return
    _operation.bytes_done = 0
    _operation.bytes_total = total
    _operation.progress = 0.0
    _operation.speed_bytes_per_s = None
    _speed_samples.clear()


def _sha256(path: Path, cancel: threading.Event | None = None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            if cancel is not None and cancel.is_set():
                raise InterruptedError("operation cancelled")
            digest.update(block)
    return digest.hexdigest()


async def _in_thread(function: Callable[..., Any], *args: object, **kwargs: object) -> Any:
    """Run blocking work without releasing ownership before its thread exits."""
    global _thread_cancel
    worker = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        if _thread_cancel is not None:
            _thread_cancel.set()
        with suppress(BaseException):
            await worker
        raise


async def _publish_data(staged: Path, source: Literal["download", "import"]) -> None:
    if _operation is None:
        raise RuntimeError("star operation was not claimed")
    _operation.phase = "publishing"
    lock = publish_lock()
    async with lock:
        handles.close_all()
        destination = catalog_dir()
        destination.mkdir(parents=True, exist_ok=True)
        os.replace(staged, catalog_path())
        payload = version_payload(source)
        version_file = destination / "version.json"
        temporary = destination / ".version.json.tmp"
        try:
            temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            os.replace(temporary, version_file)
        finally:
            temporary.unlink(missing_ok=True)


async def _download() -> None:
    if _operation is None or _async_cancel is None or _thread_cancel is None:
        raise RuntimeError("star operation was not claimed")
    stage = staging_dir()
    stage.mkdir(parents=True, exist_ok=True)
    compressed = stage / SIRIL_SOURCE.compressed_name
    partial = stage / f"{SIRIL_SOURCE.compressed_name}.part"
    already = (
        compressed.stat().st_size
        if compressed.exists()
        else (partial.stat().st_size if partial.exists() else 0)
    )
    ensure_free_space(already)
    if not compressed.exists():
        _operation.phase = "downloading"
        await http_client.stream_to_file(
            SIRIL_SOURCE.url,
            partial,
            expected_size=SIRIL_SOURCE.compressed_size,
            on_bytes=_progress,
            cancel=_async_cancel,
            label="[star_catalog] Siril Gaia DR3",
        )
        os.replace(partial, compressed)
    _operation.phase = "verifying"
    digest = await _in_thread(_sha256, compressed, _thread_cancel)
    if digest != SIRIL_SOURCE.compressed_sha256:
        compressed.unlink(missing_ok=True)
        raise ChecksumMismatch("compressed SHA-256 mismatch")
    _operation.phase = "unpacking"
    _reset_progress(SIRIL_SOURCE.uncompressed_size)
    staged_data = stage / SIRIL_SOURCE.uncompressed_name
    await _in_thread(
        decompress_and_verify,
        compressed,
        staged_data,
        compressed_sha256=SIRIL_SOURCE.compressed_sha256,
        uncompressed_sha256=SIRIL_SOURCE.uncompressed_sha256,
        cancel=_thread_cancel,
        on_bytes=_progress,
    )
    await _publish_data(staged_data, "download")
    compressed.unlink(missing_ok=True)
    _remove_empty_staging()


def start_download() -> StarOperation:
    _ensure_not_busy()
    if installed() is not None:
        raise AlreadyInstalled
    partial = staging_dir() / f"{SIRIL_SOURCE.compressed_name}.part"
    compressed = staging_dir() / SIRIL_SOURCE.compressed_name
    already = (
        compressed.stat().st_size
        if compressed.exists()
        else (partial.stat().st_size if partial.exists() else 0)
    )
    ensure_free_space(already)
    return _claim(
        StarOperation(
            kind="download",
            phase="downloading",
            bytes_done=already,
            bytes_total=SIRIL_SOURCE.compressed_size,
        ),
        _download,
    )


async def _import(path: Path) -> None:
    if _operation is None or _thread_cancel is None:
        raise RuntimeError("star operation was not claimed")
    stage = staging_dir()
    stage.mkdir(parents=True, exist_ok=True)
    target = stage / SIRIL_SOURCE.compressed_name
    staged_data = stage / SIRIL_SOURCE.uncompressed_name
    try:
        if path.name.endswith(".bz2"):
            await _in_thread(_copy_file, path, target, _thread_cancel)
            _operation.phase = "verifying"
            if await _in_thread(_sha256, target, _thread_cancel) != SIRIL_SOURCE.compressed_sha256:
                raise ValueError(
                    "This file isn't the Siril Gaia DR3 astrometry catalogue, version 1.0.0."
                )
            _operation.phase = "unpacking"
            _reset_progress(SIRIL_SOURCE.uncompressed_size)
            await _in_thread(
                decompress_and_verify,
                target,
                staged_data,
                compressed_sha256=SIRIL_SOURCE.compressed_sha256,
                uncompressed_sha256=SIRIL_SOURCE.uncompressed_sha256,
                cancel=_thread_cancel,
                on_bytes=_progress,
            )
            target.unlink(missing_ok=True)
        else:
            await _in_thread(_copy_file, path, staged_data, _thread_cancel)
            _operation.phase = "verifying"
            if (
                staged_data.stat().st_size != SIRIL_SOURCE.uncompressed_size
                or await _in_thread(_sha256, staged_data, _thread_cancel)
                != SIRIL_SOURCE.uncompressed_sha256
            ):
                raise ValueError(
                    "This file isn't the Siril Gaia DR3 astrometry catalogue, version 1.0.0."
                )
        await _publish_data(staged_data, "import")
        _remove_empty_staging()
    except BaseException:
        target.unlink(missing_ok=True)
        staged_data.unlink(missing_ok=True)
        _remove_empty_staging()
        raise


def _copy_file(source: Path, destination: Path, cancel: threading.Event) -> None:
    with source.open("rb") as src, destination.open("wb") as dst:
        done = 0
        while block := src.read(1024 * 1024):
            if cancel.is_set():
                raise InterruptedError("operation cancelled")
            dst.write(block)
            done += len(block)
            _progress(done)


def start_import(path: Path) -> StarOperation:
    _ensure_not_busy()
    if installed() is not None:
        raise AlreadyInstalled
    message = "Choose a copy outside NightCrate's star-data folder."
    root = star_root()
    resolved = path.resolve(strict=True)
    if root.exists():
        for ancestor in resolved.parents:
            if os.path.samefile(ancestor, root):
                raise ValueError(message)
    destinations = (
        staging_dir() / SIRIL_SOURCE.compressed_name,
        staging_dir() / SIRIL_SOURCE.uncompressed_name,
    )
    if any(
        destination.exists() and os.path.samefile(path, destination) for destination in destinations
    ):
        raise ValueError(message)
    ensure_free_space(0 if path.name.endswith(".bz2") else SIRIL_SOURCE.compressed_size)
    return _claim(
        StarOperation(kind="import", phase="copying", bytes_total=path.stat().st_size),
        lambda: _import(path),
    )


def cancel_operation() -> bool:
    if _operation is None or _operation.state != "running":
        return False
    if _async_cancel is None or _thread_cancel is None:
        return False
    _async_cancel.set()
    _thread_cancel.set()
    return True


async def shutdown() -> None:
    if _task is None or _task.done():
        return
    cancel_operation()
    done, _ = await asyncio.wait({_task}, timeout=10)
    if not done:
        logger.warning("[star_catalog] operation still stopping at shutdown")


def _remove_empty_staging() -> None:
    stage = staging_dir()
    try:
        stage.rmdir()
    except OSError:
        pass


# Task 3 extends these entry points below.
def start_build(range_ids: list[str]) -> StarOperation:
    from .index_build import run_build, validate_build_request

    _ensure_not_busy()
    validate_build_request(range_ids)
    return _claim(
        StarOperation(kind="build", phase="building", ranges=range_ids),
        lambda: run_build(range_ids),
    )


def start_remove(range_ids: list[str] | Literal["all"]) -> StarOperation:
    from .index_build import run_remove
    from .ranges import FIELD_RANGES

    global _operation
    _ensure_not_busy()
    listed = [item.id for item in FIELD_RANGES] if range_ids == "all" else range_ids
    operation = StarOperation(kind="remove", phase="removing", ranges=listed)
    _operation = operation
    try:
        run_remove(range_ids)
        operation.state = "done"
        operation.progress = 1.0
    except Exception as exc:
        operation.state = "failed"
        operation.message = str(exc)
        raise
    return operation
