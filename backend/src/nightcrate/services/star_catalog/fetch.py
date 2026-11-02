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
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from nightcrate.core.tasks import settle
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
PIECES = 4
_COPY_CHUNK_BYTES = 8 * 1024 * 1024


class StarOperationBusy(RuntimeError):
    pass


class AlreadyBuilt(ValueError):
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


def piece_bounds(size: int, pieces: int) -> list[tuple[int, int]]:
    if size < 0:
        raise ValueError("size must be non-negative")
    if pieces < 1:
        raise ValueError("pieces must be at least 1")
    return [(index * size // pieces, (index + 1) * size // pieces) for index in range(pieces)]


def piece_path(index: int) -> Path:
    if not 0 <= index < PIECES:
        raise ValueError(f"piece index must be between 0 and {PIECES - 1}")
    return staging_dir() / f"{SIRIL_SOURCE.compressed_name}.part{index + 1}of{PIECES}"


def _clean_stale_staging() -> None:
    """Delete what a crashed operation left in staging.

    Only one operation runs at a time, so at claim time a hidden temporary file
    (an interrupted unpack) or a ``build-*`` folder (an interrupted index build)
    belongs to no live operation. The resumable ``.part`` download and a
    compressed file are kept unless partial downloads exist beside it.
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
    compressed = stage / SIRIL_SOURCE.compressed_name
    partial = stage / f"{SIRIL_SOURCE.compressed_name}.part"
    pieces = [piece_path(index) for index in range(PIECES)]
    if compressed.is_file() and (partial.exists() or any(path.exists() for path in pieces)):
        try:
            compressed.unlink()
        except OSError:
            logger.warning("[star_catalog] could not remove unverified archive %s", compressed)


def _select_partial() -> tuple[Literal["compressed", "pieces", "legacy"], int, list[int]]:
    """Validate staging files and choose the one resumable representation."""
    stage = staging_dir()
    compressed = stage / SIRIL_SOURCE.compressed_name
    partial = stage / f"{SIRIL_SOURCE.compressed_name}.part"
    bounds = piece_bounds(SIRIL_SOURCE.compressed_size, PIECES)
    paths = [piece_path(index) for index in range(PIECES)]

    if compressed.exists() and compressed.stat().st_size != SIRIL_SOURCE.compressed_size:
        compressed.unlink()
    if partial.exists() and partial.stat().st_size > SIRIL_SOURCE.compressed_size:
        partial.unlink()
    piece_sizes: list[int] = []
    pieces_exist = False
    for path, (start, end) in zip(paths, bounds, strict=True):
        size = path.stat().st_size if path.exists() else 0
        if size > end - start:
            path.unlink()
            size = 0
        elif path.exists():
            pieces_exist = True
        piece_sizes.append(size)

    partial_exists = partial.exists()
    if compressed.exists() and (pieces_exist or partial_exists):
        compressed.unlink()
    if compressed.exists():
        return "compressed", SIRIL_SOURCE.compressed_size, piece_sizes

    piece_total = sum(piece_sizes)
    partial_size = partial.stat().st_size if partial_exists else 0
    if pieces_exist and partial_exists:
        if piece_total >= partial_size:
            partial.unlink()
            return "pieces", piece_total, piece_sizes
        for path in paths:
            path.unlink(missing_ok=True)
        return "legacy", partial_size, [0] * PIECES
    if pieces_exist:
        return "pieces", piece_total, piece_sizes
    if partial_exists:
        return "legacy", partial_size, [0] * PIECES
    return "pieces", 0, [0] * PIECES


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
        while block := stream.read(_COPY_CHUNK_BYTES):
            if cancel is not None and cancel.is_set():
                raise InterruptedError("operation cancelled")
            digest.update(block)
    return digest.hexdigest()


def _assemble_pieces(destination: Path, cancel: threading.Event) -> None:
    with destination.open("wb") as output:
        for index in range(PIECES):
            with piece_path(index).open("rb") as source:
                while block := source.read(_COPY_CHUNK_BYTES):
                    if cancel.is_set():
                        raise InterruptedError("operation cancelled")
                    output.write(block)


async def _cancel_and_await(tasks: set[asyncio.Task[None]]) -> None:
    for task in tasks:
        if not task.done():
            task.cancel()
    if not tasks:
        return
    await settle(asyncio.gather(*tasks, return_exceptions=True))


async def _cancel_watcher(tasks: set[asyncio.Task[None]]) -> None:
    if _async_cancel is None:
        raise RuntimeError("star operation was not claimed")
    await _async_cancel.wait()
    await _cancel_and_await(tasks)


async def _run_single_stream(destination: Path, tasks: set[asyncio.Task[None]]) -> None:
    if _async_cancel is None:
        raise RuntimeError("star operation was not claimed")
    task = asyncio.create_task(
        http_client.stream_to_file(
            SIRIL_SOURCE.url,
            destination,
            expected_size=SIRIL_SOURCE.compressed_size,
            on_bytes=_progress,
            cancel=_async_cancel,
            label="[star_catalog] Siril Gaia DR3",
        )
    )
    tasks.add(task)
    if _async_cancel.is_set():
        await _cancel_and_await({task})
        raise http_client.OperationCancelled("operation cancelled")
    try:
        await task
    except asyncio.CancelledError:
        if _async_cancel.is_set():
            raise http_client.OperationCancelled("operation cancelled") from None
        raise


async def _run_piece_streams(sizes: list[int], tasks: set[asyncio.Task[None]]) -> None:
    if _async_cancel is None:
        raise RuntimeError("star operation was not claimed")
    counters = sizes.copy()
    bounds = piece_bounds(SIRIL_SOURCE.compressed_size, PIECES)

    def progress(index: int, done: int) -> None:
        counters[index] = done
        _progress(sum(counters))

    piece_tasks: set[asyncio.Task[None]] = set()
    for index, (start, end) in enumerate(bounds):
        task = asyncio.create_task(
            http_client.stream_to_file(
                SIRIL_SOURCE.url,
                piece_path(index),
                expected_size=end - start,
                offset=start,
                total_size=SIRIL_SOURCE.compressed_size,
                allow_whole_file=False,
                on_bytes=lambda done, index=index: progress(index, done),
                cancel=_async_cancel,
                label=f"[star_catalog] Siril Gaia DR3 piece {index + 1}/{PIECES}",
            )
        )
        piece_tasks.add(task)
        tasks.add(task)
    if _async_cancel.is_set():
        await _cancel_and_await(piece_tasks)
        raise http_client.OperationCancelled("operation cancelled")
    try:
        await asyncio.gather(*piece_tasks)
    except BaseException:
        await _cancel_and_await(piece_tasks)
        if _async_cancel.is_set():
            raise http_client.OperationCancelled("operation cancelled") from None
        raise


def _fall_back_to_single() -> Path:
    partial = staging_dir() / f"{SIRIL_SOURCE.compressed_name}.part"
    for index in range(1, PIECES):
        piece_path(index).unlink(missing_ok=True)
    first = piece_path(0)
    if first.exists():
        os.replace(first, partial)
    else:
        partial.parent.mkdir(parents=True, exist_ok=True)
        partial.write_bytes(b"")
    return partial


def _reset_download_speed(done: int) -> None:
    if _operation is None:
        return
    _operation.bytes_done = done
    _operation.progress = done / _operation.bytes_total if _operation.bytes_total else None
    _operation.speed_bytes_per_s = None
    _speed_samples.clear()


async def _in_thread(function: Callable[..., Any], *args: object, **kwargs: object) -> Any:
    """Run blocking work without releasing ownership before its thread exits."""
    global _thread_cancel
    worker = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    cancel = _thread_cancel
    return await settle(worker, on_cancel=cancel.set if cancel is not None else None)


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
    mode, _, piece_sizes = _select_partial()
    compressed_verified = False
    tasks: set[asyncio.Task[None]] = set()
    watcher = asyncio.create_task(_cancel_watcher(tasks))
    try:
        if mode == "legacy":
            _operation.phase = "downloading"
            await _run_single_stream(partial, tasks)
            if _async_cancel.is_set():
                raise http_client.OperationCancelled("operation cancelled")
            os.replace(partial, compressed)
        elif mode == "pieces":
            _operation.phase = "downloading"
            try:
                await _run_piece_streams(piece_sizes, tasks)
            except http_client.RangeNotHonoured:
                if _async_cancel.is_set():
                    raise http_client.OperationCancelled("operation cancelled") from None
                partial = _fall_back_to_single()
                _reset_download_speed(partial.stat().st_size)
                await _run_single_stream(partial, tasks)
                if _async_cancel.is_set():
                    raise http_client.OperationCancelled("operation cancelled")
                os.replace(partial, compressed)
            else:
                if _async_cancel.is_set():
                    raise http_client.OperationCancelled("operation cancelled")
                _operation.phase = "verifying"
                assembling = stage / f".{SIRIL_SOURCE.compressed_name}.assembling.tmp"
                await _in_thread(_assemble_pieces, assembling, _thread_cancel)
                digest = await _in_thread(_sha256, assembling, _thread_cancel)
                if digest != SIRIL_SOURCE.compressed_sha256:
                    assembling.unlink(missing_ok=True)
                    for index in range(PIECES):
                        piece_path(index).unlink(missing_ok=True)
                    raise ChecksumMismatch("compressed SHA-256 mismatch")
                if _async_cancel.is_set():
                    raise http_client.OperationCancelled("operation cancelled")
                os.replace(assembling, compressed)
                compressed_verified = True
                for index in range(PIECES):
                    piece_path(index).unlink(missing_ok=True)
    finally:
        cancelled_while_stopping = False
        try:
            await _cancel_and_await(tasks)
        except asyncio.CancelledError:
            cancelled_while_stopping = True
        try:
            await _cancel_and_await({watcher})
        except asyncio.CancelledError:
            cancelled_while_stopping = True
        if cancelled_while_stopping:
            raise asyncio.CancelledError
    _operation.phase = "verifying"
    if not compressed_verified:
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
    _clean_stale_staging()
    if installed() is not None:
        raise AlreadyInstalled
    _, already, _ = _select_partial()
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
    _clean_stale_staging()
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
    from .ranges import built_ranges

    _ensure_not_busy()
    validate_build_request(range_ids)
    built = built_ranges()
    remaining = [range_id for range_id in range_ids if range_id not in built]
    if not remaining:
        raise AlreadyBuilt
    return _claim(
        StarOperation(kind="build", phase="building", ranges=remaining),
        lambda: run_build(remaining),
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
