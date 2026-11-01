from __future__ import annotations

import multiprocessing
import os
import queue
import shutil
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from nightcrate.core.compute import effective_worker_count
from nightcrate.core.config import get_settings

from . import handles
from .index import build_siril_band, layer_state
from .ranges import FIELD_RANGES, LAYERS, indexes_dir, layer_path, read_manifest, write_manifest
from .store import InsufficientSpace, catalog_dir, catalog_path, staging_dir


def validate_build_request(range_ids: list[str]) -> None:
    ranges_by_id = {item.id: item for item in FIELD_RANGES}
    unknown = sorted(set(range_ids) - set(ranges_by_id))
    if unknown:
        raise ValueError(f"Unknown field range: {', '.join(unknown)}")
    needed_layers = {
        layer
        for range_id in range_ids
        for layer in ranges_by_id[range_id].layers
        if layer_state(layer) != "ready"
    }
    if not needed_layers:
        return
    root = staging_dir()
    root.mkdir(parents=True, exist_ok=True)
    needed = max(3 * LAYERS[name].estimated_bytes for name in needed_layers)
    free = shutil.disk_usage(root).free
    if free < needed:
        raise InsufficientSpace(needed, free)


def _child_main(name: str, catalog: Path, output: Path, threads: int, messages: object) -> None:
    try:
        last_sent_at = 0.0
        last_value = -1.0

        def report(value: float) -> None:
            nonlocal last_sent_at, last_value
            value = max(last_value, min(1.0, value))
            now = time.monotonic()
            if value >= 1.0 or now - last_sent_at >= 0.25 or value - last_value >= 0.2:
                messages.put(("progress", value))  # type: ignore[attr-defined]
                last_sent_at = now
                last_value = value

        build_siril_band(catalog, output, LAYERS[name], workers=threads, on_progress=report)
        report(1.0)
        messages.put(("done", None))  # type: ignore[attr-defined]
    except BaseException as exc:
        messages.put(("error", f"{type(exc).__name__}: {exc}"))  # type: ignore[attr-defined]
        raise


def build_layer(
    name: str, *, threads: int, cancel: threading.Event, on_progress: Callable[[float], None]
) -> Path:
    if name not in LAYERS:
        raise ValueError(f"Unknown index layer: {name}")
    parent = staging_dir() / f"build-{name}-{uuid.uuid4().hex}"
    parent.mkdir(parents=True, exist_ok=False)
    output = parent / f"{name}.ncidx"
    context = multiprocessing.get_context("spawn")
    messages = context.Queue()
    process = context.Process(
        target=_child_main,
        args=(name, catalog_path(), output, max(1, threads), messages),
    )
    process.start()
    error: str | None = None
    succeeded = False
    try:
        while process.is_alive():
            if cancel.is_set():
                process.terminate()
                break
            try:
                kind, value = messages.get(timeout=0.05)
            except queue.Empty:
                continue
            if kind == "progress":
                on_progress(float(value))
            elif kind == "error":
                error = str(value)
        process.join()
        while True:
            try:
                kind, value = messages.get_nowait()
            except queue.Empty:
                break
            if kind == "progress":
                on_progress(float(value))
            elif kind == "error":
                error = str(value)
        if cancel.is_set():
            raise InterruptedError("operation cancelled")
        if process.exitcode != 0 or error:
            raise RuntimeError(error or f"index builder exited with status {process.exitcode}")
        if not output.is_file():
            raise RuntimeError("index builder produced no output")
        succeeded = True
        for item in parent.iterdir():
            if item != output:
                shutil.rmtree(item) if item.is_dir() else item.unlink()
        return output
    finally:
        if process.is_alive():
            process.terminate()
        process.join()
        messages.close()
        if not succeeded:
            shutil.rmtree(parent, ignore_errors=True)


async def run_build(range_ids: list[str]) -> None:
    from . import fetch

    validate_build_request(range_ids)
    requested_ranges = [item for item in FIELD_RANGES if item.id in set(range_ids)]
    job_layers = list(
        dict.fromkeys(
            layer
            for field_range in requested_ranges
            for layer in field_range.layers
            if layer_state(layer) != "ready"
        )
    )
    job_total = sum(LAYERS[name].estimated_bytes for name in job_layers)
    job_done = 0
    settings = await get_settings()
    threads = effective_worker_count(settings.max_worker_cores)
    if fetch._operation is not None:
        fetch._operation.range_progress = {item.id: 0.0 for item in requested_ranges}
        fetch._operation.progress = 0.0 if job_total else 1.0
    try:
        for field_range in requested_ranges:
            staged: list[tuple[str, Path]] = []
            range_layers = [
                name for name in reversed(field_range.layers) if layer_state(name) != "ready"
            ]
            range_total = sum(LAYERS[name].estimated_bytes for name in range_layers)
            range_done = 0
            if fetch._operation is not None:
                fetch._operation.phase = "building"
                fetch._operation.current_range = field_range.id
                fetch._operation.range_progress[field_range.id] = 0.0 if range_total else 1.0
            try:
                for name in range_layers:
                    root = staging_dir()
                    root.mkdir(parents=True, exist_ok=True)
                    needed = 3 * LAYERS[name].estimated_bytes
                    free = shutil.disk_usage(root).free
                    if free < needed:
                        raise InsufficientSpace(needed, free)
                    if fetch._thread_cancel is None:
                        raise RuntimeError("star operation was not claimed")
                    if fetch._thread_cancel.is_set():
                        raise InterruptedError("operation cancelled")

                    layer_bytes = LAYERS[name].estimated_bytes

                    def progress(value: float) -> None:
                        if fetch._operation is not None:
                            fraction = max(0.0, min(1.0, value))
                            fetch._operation.range_progress[field_range.id] = (
                                range_done + fraction * layer_bytes
                            ) / range_total
                            fetch._operation.progress = (
                                job_done + fraction * layer_bytes
                            ) / job_total

                    output = await fetch._in_thread(
                        build_layer,
                        name,
                        threads=threads,
                        cancel=fetch._thread_cancel,
                        on_progress=progress,
                    )
                    staged.append((name, output))
                    if fetch._thread_cancel.is_set():
                        raise InterruptedError("operation cancelled")
                    range_done += layer_bytes
                    job_done += layer_bytes
                    if fetch._operation is not None:
                        fetch._operation.range_progress[field_range.id] = range_done / range_total
                        fetch._operation.progress = job_done / job_total
                if fetch._operation is not None:
                    fetch._operation.phase = "publishing"
                lock = fetch.publish_lock()
                async with lock:
                    if fetch._thread_cancel is not None and fetch._thread_cancel.is_set():
                        raise InterruptedError("operation cancelled")
                    handles.close_all()
                    indexes_dir().mkdir(parents=True, exist_ok=True)
                    for name, output in staged:
                        os.replace(output, layer_path(name))
                    write_manifest(read_manifest() | {field_range.id})
                if fetch._operation is not None:
                    fetch._operation.range_progress[field_range.id] = 1.0
                    fetch._operation.phase = "building"
            finally:
                for _, output in staged:
                    shutil.rmtree(output.parent, ignore_errors=True)
    finally:
        if fetch._operation is not None:
            fetch._operation.current_range = None


def run_remove(range_ids: list[str] | Literal["all"]) -> None:
    ranges_by_id = {item.id: item for item in FIELD_RANGES}
    old_manifest = read_manifest()
    removing = old_manifest if range_ids == "all" else set(range_ids)
    remaining = old_manifest - removing
    write_manifest(remaining)
    handles.close_all()
    retained = {
        layer
        for range_id in remaining
        if range_id in ranges_by_id
        for layer in ranges_by_id[range_id].layers
    }
    directory = indexes_dir()
    if directory.exists():
        for path in directory.glob("*.ncidx"):
            if path.stem not in retained:
                path.unlink(missing_ok=True)
    if range_ids == "all":
        shutil.rmtree(catalog_dir(), ignore_errors=True)
        shutil.rmtree(directory, ignore_errors=True)
        shutil.rmtree(staging_dir(), ignore_errors=True)
