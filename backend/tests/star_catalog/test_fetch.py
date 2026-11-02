import asyncio
import bz2
import hashlib
import os
import threading
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from nightcrate.core import app_config
from nightcrate.services.star_catalog import fetch, store


def _source(monkeypatch, raw=b"synthetic catalog"):
    compressed = bz2.compress(raw)
    fake = replace(
        store.SIRIL_SOURCE,
        compressed_size=len(compressed),
        compressed_sha256=hashlib.sha256(compressed).hexdigest(),
        uncompressed_size=len(raw),
        uncompressed_sha256=hashlib.sha256(raw).hexdigest(),
    )
    monkeypatch.setattr(store, "SIRIL_SOURCE", fake)
    monkeypatch.setattr(fetch, "SIRIL_SOURCE", fake)
    return fake, raw, compressed


def _mock_http(monkeypatch, handler):
    original = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        fetch.http_client.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=transport, **kwargs),
    )
    monkeypatch.setattr(fetch.http_client.random, "uniform", lambda *_: 0)


def _stream_from(body: bytes):
    async def stream(url, destination, **kwargs):
        offset = kwargs.get("offset", 0)
        expected_size = kwargs["expected_size"]
        have = destination.stat().st_size if destination.exists() else 0
        with destination.open("ab") as output:
            output.write(body[offset + have : offset + expected_size])
        kwargs["on_bytes"](expected_size)

    return stream


def _write_complete_pieces(body: bytes) -> None:
    for index, (start, end) in enumerate(fetch.piece_bounds(len(body), fetch.PIECES)):
        fetch.piece_path(index).parent.mkdir(parents=True, exist_ok=True)
        fetch.piece_path(index).write_bytes(body[start:end])


@pytest.fixture(autouse=True)
async def reset_operation():
    await fetch.shutdown()
    fetch._operation = None
    fetch._task = None
    yield
    await fetch.shutdown()


@pytest.mark.asyncio
async def test_import_dat_installs_without_modifying_source(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    source = tmp_path / "catalog.dat"
    source.write_bytes(b"synthetic catalog")
    fake = replace(
        store.SIRIL_SOURCE,
        uncompressed_size=source.stat().st_size,
        uncompressed_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        compressed_size=10,
    )
    monkeypatch.setattr(store, "SIRIL_SOURCE", fake)
    monkeypatch.setattr(fetch, "SIRIL_SOURCE", fake)
    before = (source.stat().st_size, source.stat().st_mtime_ns)
    operation = fetch.start_import(source)
    await fetch._task
    assert operation.state == "done"
    assert store.catalog_path().read_bytes() == source.read_bytes()
    assert (source.stat().st_size, source.stat().st_mtime_ns) == before
    assert store.installed() is not None


@pytest.mark.parametrize("source_kind", ["staged", "symlink", "hardlink"])
def test_import_rejects_staging_source_without_modifying_it(tmp_path, monkeypatch, source_kind):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    fake, _, compressed = _source(monkeypatch)
    staged = store.staging_dir() / fake.compressed_name
    staged.parent.mkdir(parents=True)
    staged.write_bytes(compressed)
    source = staged
    if source_kind == "symlink":
        source = tmp_path / "symlink.bz2"
        source.symlink_to(staged)
    elif source_kind == "hardlink":
        source = tmp_path / "hardlink.bz2"
        os.link(staged, source)
    before = staged.read_bytes()

    with pytest.raises(
        ValueError,
        match="Choose a copy outside NightCrate's star-data folder\\.",
    ):
        fetch.start_import(source)

    assert staged.stat().st_size == len(before)
    assert staged.read_bytes() == before


def test_import_rejects_alternate_case_path_into_staging(tmp_path, monkeypatch):
    probe = tmp_path / "CaseProbe"
    probe.mkdir()
    if not (tmp_path / "caseprobe").exists():
        pytest.skip("filesystem is case-sensitive")

    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "NightCrateData")
    fake, _, compressed = _source(monkeypatch)
    staged = store.staging_dir() / fake.compressed_name
    staged.parent.mkdir(parents=True)
    staged.write_bytes(compressed)
    alternate = tmp_path / "nightcratedata" / "STAR_CATALOGS" / ".STAGING" / fake.compressed_name
    before = staged.read_bytes()

    with pytest.raises(
        ValueError,
        match="Choose a copy outside NightCrate's star-data folder\\.",
    ):
        fetch.start_import(alternate)

    assert staged.read_bytes() == before


@pytest.mark.asyncio
async def test_busy(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)
    fetch._operation = fetch.StarOperation(kind="download", phase="downloading")
    with pytest.raises(fetch.StarOperationBusy):
        fetch._claim(
            fetch.StarOperation(kind="import", phase="copying"),
            lambda: None,
        )


def test_cancel_without_operation_returns_false():
    fetch._operation = None
    assert fetch.cancel_operation() is False


@pytest.mark.asyncio
async def test_task_cancellation_waits_for_thread(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    fake, raw, _ = _source(monkeypatch)
    source = tmp_path / fake.uncompressed_name
    source.write_bytes(raw)
    entered = threading.Event()
    release = threading.Event()

    def blocked_copy(source, destination, cancel):
        entered.set()
        release.wait()
        destination.write_bytes(source.read_bytes())

    monkeypatch.setattr(fetch, "_copy_file", blocked_copy)
    operation = fetch.start_import(source)
    while not entered.is_set():
        await asyncio.sleep(0)
    fetch._task.cancel()
    await asyncio.sleep(0.02)
    assert not fetch._task.done()
    assert operation.state == "running"
    release.set()
    await fetch._task
    assert operation.state == "cancelled"


@pytest.mark.asyncio
async def test_repeated_task_cancellation_keeps_assembly_owned(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    fake, _, compressed = _source(monkeypatch, b"blocked assembly rows" * 20)
    for index, (start, end) in enumerate(fetch.piece_bounds(fake.compressed_size, fetch.PIECES)):
        fetch.piece_path(index).parent.mkdir(parents=True, exist_ok=True)
        fetch.piece_path(index).write_bytes(compressed[start:end])
    entered = threading.Event()
    release = threading.Event()

    def blocked_assembly(destination, cancel):
        entered.set()
        assert release.wait(timeout=5)
        if cancel.is_set():
            raise InterruptedError("operation cancelled")

    monkeypatch.setattr(fetch, "_assemble_pieces", blocked_assembly)
    operation = fetch.start_download()
    task = fetch._task
    assert task is not None
    try:
        await asyncio.wait_for(asyncio.to_thread(entered.wait, 1), timeout=2)
        assert entered.is_set()
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)

        assert not task.done()
        assert operation.state == "running"
        with pytest.raises(fetch.StarOperationBusy):
            fetch.start_download()
    finally:
        release.set()
        task.cancel()
        await asyncio.wait_for(task, timeout=1)

    assert operation.state == "cancelled"
    assert all(fetch.piece_path(index).exists() for index in range(fetch.PIECES))


@pytest.mark.asyncio
async def test_repeated_task_cancellation_awaits_every_piece(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    _source(monkeypatch, b"blocked piece rows" * 20)
    started = 0
    cancelled = 0
    stopped = 0
    all_started = asyncio.Event()
    all_cancelled = asyncio.Event()
    release = asyncio.Event()

    async def stream(url, destination, **kwargs):
        nonlocal started, cancelled, stopped
        destination.write_bytes(b"p")
        started += 1
        if started == fetch.PIECES:
            all_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled += 1
            if cancelled == fetch.PIECES:
                all_cancelled.set()
            while not release.is_set():
                try:
                    await asyncio.shield(release.wait())
                except asyncio.CancelledError:
                    continue
            stopped += 1

    monkeypatch.setattr(fetch.http_client, "stream_to_file", stream)
    operation = fetch.start_download()
    task = fetch._task
    assert task is not None
    try:
        await asyncio.wait_for(all_started.wait(), timeout=1)
        task.cancel()
        await asyncio.wait_for(all_cancelled.wait(), timeout=1)
        task.cancel()
        await asyncio.sleep(0)

        assert not task.done()
        assert operation.state == "running"
    finally:
        release.set()
        task.cancel()
        await asyncio.wait_for(task, timeout=1)

    assert operation.state == "cancelled"
    assert stopped == fetch.PIECES
    assert all(fetch.piece_path(index).exists() for index in range(fetch.PIECES))


@pytest.mark.asyncio
async def test_cancel_and_await_survives_repeated_cancellation():
    piece_cancelled = 0
    all_cancelled = asyncio.Event()
    release = asyncio.Event()

    async def stubborn_piece():
        nonlocal piece_cancelled
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            piece_cancelled += 1
            if piece_cancelled == fetch.PIECES:
                all_cancelled.set()
            while not release.is_set():
                try:
                    await asyncio.shield(release.wait())
                except asyncio.CancelledError:
                    continue

    pieces = {asyncio.create_task(stubborn_piece()) for _ in range(fetch.PIECES)}
    waiter = asyncio.create_task(fetch._cancel_and_await(pieces))
    waiter_cancelled = False
    try:
        await asyncio.wait_for(all_cancelled.wait(), timeout=1)
        waiter.cancel()
        await asyncio.sleep(0)
        waiter.cancel()
        await asyncio.sleep(0)

        assert not waiter.done()
        assert not any(piece.done() for piece in pieces)
    finally:
        release.set()
        waiter.cancel()
        try:
            await asyncio.wait_for(waiter, timeout=1)
        except asyncio.CancelledError:
            waiter_cancelled = True

    assert waiter_cancelled
    assert all(piece.done() for piece in pieces)


def test_import_insufficient_space_bz2(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    fake, _, compressed = _source(monkeypatch)
    source = tmp_path / fake.compressed_name
    source.write_bytes(compressed)
    needed = store.required_free_bytes(0)
    monkeypatch.setattr(store.shutil, "disk_usage", lambda _: SimpleNamespace(free=needed - 1))
    with pytest.raises(store.InsufficientSpace) as error:
        fetch.start_import(source)
    assert error.value.needed == fake.compressed_size + fake.uncompressed_size + 100 * 1024**2


@pytest.mark.asyncio
async def test_import_cancel_cleans_staging(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    fake, raw, _ = _source(monkeypatch)
    source = tmp_path / fake.uncompressed_name
    source.write_bytes(raw)
    entered = threading.Event()

    def cancellable_copy(source, destination, cancel):
        destination.write_bytes(b"partial")
        entered.set()
        cancel.wait()
        raise InterruptedError("operation cancelled")

    monkeypatch.setattr(fetch, "_copy_file", cancellable_copy)
    operation = fetch.start_import(source)
    while not entered.is_set():
        await asyncio.sleep(0)
    fetch.cancel_operation()
    await fetch._task
    assert operation.state == "cancelled"
    assert not store.staging_dir().exists()


@pytest.mark.asyncio
async def test_download_installs_atomically(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    fake, raw, compressed = _source(monkeypatch)
    events = []

    async def stream(url, destination, **kwargs):
        start = kwargs.get("offset", 0)
        size = kwargs["expected_size"]
        destination.write_bytes(compressed[start : start + size])

    real_replace = fetch.os.replace

    def replace_spy(source, destination):
        if destination == store.catalog_path():
            events.append("catalog")
        elif destination.name == "version.json":
            events.append("version")
        real_replace(source, destination)

    monkeypatch.setattr(fetch.http_client, "stream_to_file", stream)
    monkeypatch.setattr(fetch.handles, "close_all", lambda: events.append("close"))
    monkeypatch.setattr(fetch.os, "replace", replace_spy)
    operation = fetch.start_download()
    await fetch._task
    assert operation.state == "done"
    assert store.catalog_path().read_bytes() == raw
    assert events == ["close", "catalog", "version"]


@pytest.mark.asyncio
async def test_download_requests_four_overlapping_exact_ranges(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    fake, raw, compressed = _source(monkeypatch, b"catalog rows" * 20)
    requested: list[str] = []
    all_arrived = asyncio.Event()

    async def handler(request):
        requested.append(request.headers["Range"])
        if len(requested) == fetch.PIECES:
            all_arrived.set()
        await asyncio.wait_for(all_arrived.wait(), timeout=1)
        start, end = map(int, request.headers["Range"].removeprefix("bytes=").split("-"))
        return httpx.Response(
            206,
            headers={"Content-Range": f"bytes {start}-{end}/{len(compressed)}"},
            content=compressed[start : end + 1],
        )

    _mock_http(monkeypatch, handler)
    operation = fetch.start_download()
    await fetch._task

    assert operation.state == "done"
    assert store.catalog_path().read_bytes() == raw
    assert set(requested) == {
        f"bytes={start}-{end - 1}"
        for start, end in fetch.piece_bounds(fake.compressed_size, fetch.PIECES)
    }
    assert not any(fetch.piece_path(index).exists() for index in range(fetch.PIECES))


@pytest.mark.asyncio
async def test_download_resumes_uneven_complete_missing_and_oversized_pieces(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    fake, raw, compressed = _source(monkeypatch, b"resume rows" * 20)
    bounds = fetch.piece_bounds(fake.compressed_size, fetch.PIECES)
    stage = store.staging_dir()
    stage.mkdir(parents=True)
    first_size = 2
    fetch.piece_path(0).write_bytes(compressed[bounds[0][0] : bounds[0][0] + first_size])
    fetch.piece_path(1).write_bytes(compressed[bounds[1][0] : bounds[1][1]])
    fetch.piece_path(3).write_bytes(b"x" * (bounds[3][1] - bounds[3][0] + 1))
    requested: list[str] = []

    def handler(request):
        header = request.headers["Range"]
        requested.append(header)
        start, end = map(int, header.removeprefix("bytes=").split("-"))
        return httpx.Response(
            206,
            headers={"Content-Range": f"bytes {start}-{end}/{len(compressed)}"},
            content=compressed[start : end + 1],
        )

    _mock_http(monkeypatch, handler)
    operation = fetch.start_download()
    await fetch._task

    assert operation.state == "done"
    assert store.catalog_path().read_bytes() == raw
    assert set(requested) == {
        f"bytes={bounds[0][0] + first_size}-{bounds[0][1] - 1}",
        f"bytes={bounds[2][0]}-{bounds[2][1] - 1}",
        f"bytes={bounds[3][0]}-{bounds[3][1] - 1}",
    }


@pytest.mark.asyncio
async def test_download_falls_back_to_single_stream_with_piece_one_prefix(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    fake, raw, compressed = _source(monkeypatch, b"fallback rows" * 20)
    bounds = fetch.piece_bounds(fake.compressed_size, fetch.PIECES)
    prefix_size = 3
    fetch.piece_path(0).parent.mkdir(parents=True)
    fetch.piece_path(0).write_bytes(compressed[:prefix_size])
    first_piece_header = f"bytes={prefix_size}-{bounds[0][1] - 1}"
    first_piece_attempt = True
    requested: list[str] = []

    def handler(request):
        nonlocal first_piece_attempt
        header = request.headers["Range"]
        requested.append(header)
        if header == first_piece_header and first_piece_attempt:
            first_piece_attempt = False
            return httpx.Response(200, content=b"wrong bytes must not be written")
        start, end = map(int, header.removeprefix("bytes=").split("-"))
        return httpx.Response(
            206,
            headers={"Content-Range": f"bytes {start}-{end}/{len(compressed)}"},
            content=compressed[start : end + 1],
        )

    _mock_http(monkeypatch, handler)
    operation = fetch.start_download()
    await fetch._task

    assert operation.state == "done"
    assert store.catalog_path().read_bytes() == raw
    assert first_piece_header in requested
    assert f"bytes={prefix_size}-{fake.compressed_size - 1}" in requested
    assert not (store.staging_dir() / f"{fake.compressed_name}.part").exists()


@pytest.mark.asyncio
async def test_cancel_wins_over_piece_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    _source(monkeypatch, b"cancel fallback rows" * 20)
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def stream(url, destination, **kwargs):
        nonlocal calls
        calls += 1
        if calls == fetch.PIECES:
            entered.set()
        await release.wait()
        if kwargs.get("offset") == 0:
            raise fetch.http_client.RangeNotHonoured("range ignored")
        await asyncio.Event().wait()

    monkeypatch.setattr(fetch.http_client, "stream_to_file", stream)
    operation = fetch.start_download()
    await entered.wait()
    release.set()
    fetch.cancel_operation()
    await asyncio.wait_for(fetch._task, timeout=1)

    assert operation.state == "cancelled"
    assert calls == fetch.PIECES
    assert not list(store.staging_dir().glob("*.part"))


@pytest.mark.asyncio
async def test_cancel_stops_stalled_legacy_single_stream(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    fake, _, _ = _source(monkeypatch)
    partial = store.staging_dir() / f"{fake.compressed_name}.part"
    partial.parent.mkdir(parents=True)
    partial.write_bytes(b"legacy")
    entered = asyncio.Event()

    async def stream(url, destination, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(fetch.http_client, "stream_to_file", stream)
    operation = fetch.start_download()
    await entered.wait()
    fetch.cancel_operation()
    await asyncio.wait_for(fetch._task, timeout=1)

    assert operation.state == "cancelled"
    assert partial.read_bytes() == b"legacy"


@pytest.mark.asyncio
@pytest.mark.parametrize("stall", ["headers", "body"])
@pytest.mark.parametrize("stop", ["cancel", "shutdown"])
async def test_stop_stalled_piece_requests_keeps_partials(tmp_path, monkeypatch, stall, stop):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    fake, _, compressed = _source(monkeypatch, b"stalled request rows" * 20)
    bounds = fetch.piece_bounds(fake.compressed_size, fetch.PIECES)
    for index, (start, _) in enumerate(bounds):
        fetch.piece_path(index).parent.mkdir(parents=True, exist_ok=True)
        fetch.piece_path(index).write_bytes(compressed[start : start + 1])
    stalled = 0
    all_stalled = asyncio.Event()

    class StalledBody(httpx.AsyncByteStream):
        def __init__(self, first_byte):
            self.first_byte = first_byte

        async def __aiter__(self):
            nonlocal stalled
            yield self.first_byte
            stalled += 1
            if stalled == fetch.PIECES:
                all_stalled.set()
            await asyncio.Event().wait()

        async def aclose(self):
            pass

    async def handler(request):
        nonlocal stalled
        start, end = map(int, request.headers["Range"].removeprefix("bytes=").split("-"))
        if stall == "headers":
            stalled += 1
            if stalled == fetch.PIECES:
                all_stalled.set()
            await asyncio.Event().wait()
        return httpx.Response(
            206,
            headers={"Content-Range": f"bytes {start}-{end}/{len(compressed)}"},
            stream=StalledBody(compressed[start : start + 1]),
        )

    _mock_http(monkeypatch, handler)
    operation = fetch.start_download()
    await asyncio.wait_for(all_stalled.wait(), timeout=1)
    if stop == "cancel":
        fetch.cancel_operation()
        await asyncio.wait_for(fetch._task, timeout=1)
    else:
        await asyncio.wait_for(fetch.shutdown(), timeout=1)

    assert fetch._task.done()
    assert operation.state == "cancelled"
    expected_size = 1 if stall == "headers" else 2
    assert [fetch.piece_path(index).stat().st_size for index in range(fetch.PIECES)] == [
        expected_size
    ] * fetch.PIECES


@pytest.mark.asyncio
@pytest.mark.parametrize("stop", ["cancel", "shutdown"])
async def test_stop_stalled_fallback_stream_keeps_prefix(tmp_path, monkeypatch, stop):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    fake, _, compressed = _source(monkeypatch, b"stalled fallback rows" * 20)
    prefix = compressed[:3]
    fetch.piece_path(0).parent.mkdir(parents=True)
    fetch.piece_path(0).write_bytes(prefix)
    entered = asyncio.Event()

    async def stream(url, destination, **kwargs):
        if kwargs.get("allow_whole_file") is False:
            if kwargs.get("offset") == 0:
                raise fetch.http_client.RangeNotHonoured("range ignored")
            await asyncio.Event().wait()
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(fetch.http_client, "stream_to_file", stream)
    operation = fetch.start_download()
    await asyncio.wait_for(entered.wait(), timeout=1)
    if stop == "cancel":
        fetch.cancel_operation()
        await asyncio.wait_for(fetch._task, timeout=1)
    else:
        await asyncio.wait_for(fetch.shutdown(), timeout=1)

    partial = store.staging_dir() / f"{fake.compressed_name}.part"
    assert fetch._task.done()
    assert operation.state == "cancelled"
    assert partial.read_bytes() == prefix


@pytest.mark.asyncio
@pytest.mark.parametrize("stop", ["cancel", "shutdown"])
async def test_stop_assembly_keeps_every_piece(tmp_path, monkeypatch, stop):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    _, _, compressed = _source(monkeypatch, b"stalled assembly rows" * 20)
    _write_complete_pieces(compressed)
    entered = threading.Event()

    def assembly(destination, cancel):
        entered.set()
        cancel.wait()
        raise InterruptedError("operation cancelled")

    monkeypatch.setattr(fetch, "_assemble_pieces", assembly)
    operation = fetch.start_download()
    while not entered.is_set():
        await asyncio.sleep(0)
    if stop == "cancel":
        fetch.cancel_operation()
        await asyncio.wait_for(fetch._task, timeout=1)
    else:
        await asyncio.wait_for(fetch.shutdown(), timeout=1)

    assert fetch._task.done()
    assert operation.state == "cancelled"
    assert all(fetch.piece_path(index).exists() for index in range(fetch.PIECES))


@pytest.mark.asyncio
async def test_piece_failure_after_retry_awaits_siblings_and_keeps_files(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    fake, _, compressed = _source(monkeypatch, b"failed piece rows" * 20)
    bounds = fetch.piece_bounds(fake.compressed_size, fetch.PIECES)
    for index, (start, _) in enumerate(bounds):
        fetch.piece_path(index).parent.mkdir(parents=True, exist_ok=True)
        fetch.piece_path(index).write_bytes(compressed[start : start + 1])
    failed_attempts = 0
    siblings_cancelled = 0

    async def handler(request):
        nonlocal failed_attempts, siblings_cancelled
        start, _ = map(int, request.headers["Range"].removeprefix("bytes=").split("-"))
        if start < bounds[0][1]:
            failed_attempts += 1
            return httpx.Response(503, content=b"unavailable")
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            siblings_cancelled += 1
            raise

    _mock_http(monkeypatch, handler)
    operation = fetch.start_download()
    await asyncio.wait_for(fetch._task, timeout=1)

    assert operation.state == "failed"
    assert "503 Service Unavailable" in operation.message
    assert failed_attempts == 2
    assert siblings_cancelled == fetch.PIECES - 1
    assert all(fetch.piece_path(index).exists() for index in range(fetch.PIECES))


@pytest.mark.asyncio
async def test_fallback_without_piece_one_starts_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    fake, raw, compressed = _source(monkeypatch, b"empty fallback rows" * 20)
    fallback_sizes = []

    async def stream(url, destination, **kwargs):
        if kwargs.get("allow_whole_file") is False:
            if kwargs.get("offset") == 0:
                raise fetch.http_client.RangeNotHonoured("range ignored")
            await asyncio.Event().wait()
        fallback_sizes.append(destination.stat().st_size)
        destination.write_bytes(compressed)
        kwargs["on_bytes"](fake.compressed_size)

    monkeypatch.setattr(fetch.http_client, "stream_to_file", stream)
    operation = fetch.start_download()
    await fetch._task

    assert operation.state == "done"
    assert fallback_sizes == [0]
    assert store.catalog_path().read_bytes() == raw


@pytest.mark.asyncio
@pytest.mark.parametrize("crash_after", [1, 2, 3, 4])
async def test_fallback_crash_points_resume_without_mixed_forms(tmp_path, monkeypatch, crash_after):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    fake, raw, compressed = _source(monkeypatch, b"fallback crash rows" * 20)
    bounds = fetch.piece_bounds(fake.compressed_size, fetch.PIECES)
    prefix = compressed[:3]
    fetch.piece_path(0).parent.mkdir(parents=True)
    fetch.piece_path(0).write_bytes(prefix)
    for index in range(1, fetch.PIECES):
        start, end = bounds[index]
        fetch.piece_path(index).write_bytes(compressed[start:end])
    legacy = store.staging_dir() / f"{fake.compressed_name}.part"
    piece_tail_paths = {fetch.piece_path(index) for index in range(1, fetch.PIECES)}
    real_unlink = Path.unlink
    real_replace = os.replace
    mutations = 0
    crashed = False

    def maybe_crash():
        nonlocal mutations, crashed
        mutations += 1
        if not crashed and mutations == crash_after:
            crashed = True
            raise RuntimeError("simulated crash")

    def unlink(path, *args, **kwargs):
        result = real_unlink(path, *args, **kwargs)
        if path in piece_tail_paths and not crashed:
            maybe_crash()
        return result

    def replace_path(source, destination):
        result = real_replace(source, destination)
        if destination == legacy and not crashed:
            maybe_crash()
        return result

    monkeypatch.setattr(Path, "unlink", unlink)
    monkeypatch.setattr(fetch.os, "replace", replace_path)

    with pytest.raises(RuntimeError, match="simulated crash"):
        fetch._fall_back_to_single()

    pieces_exist = any(fetch.piece_path(index).exists() for index in range(fetch.PIECES))
    assert not (legacy.exists() and pieces_exist)
    retained = legacy if legacy.exists() else fetch.piece_path(0)
    assert retained.read_bytes() == prefix

    monkeypatch.setattr(fetch.http_client, "stream_to_file", _stream_from(compressed))
    operation = fetch.start_download()
    await fetch._task

    assert operation.state == "done"
    assert store.catalog_path().read_bytes() == raw


@pytest.mark.asyncio
@pytest.mark.parametrize("crash_after", [0, 1, 2, 3, 4])
async def test_assembly_publish_crash_points_resume_at_minimum_space(
    tmp_path, monkeypatch, crash_after
):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    fake, raw, compressed = _source(monkeypatch, b"assembly crash rows" * 20)
    bounds = fetch.piece_bounds(fake.compressed_size, fetch.PIECES)
    _write_complete_pieces(compressed)
    archive = store.staging_dir() / fake.compressed_name
    assembling = store.staging_dir() / f".{fake.compressed_name}.assembling.tmp"
    piece_paths = {fetch.piece_path(index) for index in range(fetch.PIECES)}
    real_unlink = Path.unlink
    real_replace = os.replace
    deletions = 0
    crashed = False

    def unlink(path, *args, **kwargs):
        nonlocal deletions, crashed
        result = real_unlink(path, *args, **kwargs)
        if path in piece_paths and not crashed:
            deletions += 1
            if deletions == crash_after:
                crashed = True
                raise InterruptedError("simulated crash")
        return result

    def replace_path(source, destination):
        nonlocal crashed
        result = real_replace(source, destination)
        if source == assembling and destination == archive and crash_after == 0 and not crashed:
            crashed = True
            raise InterruptedError("simulated crash")
        return result

    monkeypatch.setattr(Path, "unlink", unlink)
    monkeypatch.setattr(fetch.os, "replace", replace_path)
    first = fetch.start_download()
    await fetch._task

    assert first.state == "cancelled"
    assert archive.exists()
    assert sum(fetch.piece_path(index).exists() for index in range(fetch.PIECES)) == (
        fetch.PIECES - crash_after
    )

    retained = (
        fake.compressed_size
        if crash_after in {0, fetch.PIECES}
        else sum(end - start for start, end in bounds[crash_after:])
    )
    space_checks = []
    stream_calls = []

    def space(already):
        space_checks.append(already)
        assert store.required_free_bytes(already) == (
            fake.compressed_size - already + fake.uncompressed_size + 100 * 1024**2
        )

    real_stream = _stream_from(compressed)

    async def stream(*args, **kwargs):
        destination = args[1]
        have = destination.stat().st_size if destination.exists() else 0
        if have < kwargs["expected_size"]:
            stream_calls.append(kwargs.get("offset", 0))
        await real_stream(*args, **kwargs)

    monkeypatch.setattr(fetch, "ensure_free_space", space)
    monkeypatch.setattr(fetch.http_client, "stream_to_file", stream)
    second = fetch.start_download()
    await fetch._task

    assert space_checks == [retained]
    assert len(stream_calls) == (crash_after if crash_after < fetch.PIECES else 0)
    assert second.state == "done"
    assert store.catalog_path().read_bytes() == raw


@pytest.mark.asyncio
async def test_assembly_disk_full_keeps_every_piece(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    fake, _, compressed = _source(monkeypatch, b"assembly rows" * 20)

    async def stream(url, destination, **kwargs):
        start = kwargs["offset"]
        size = kwargs["expected_size"]
        destination.write_bytes(compressed[start : start + size])

    def disk_full(destination, cancel):
        assert fetch.current_operation().phase == "verifying"
        destination.write_bytes(b"partial assembly")
        raise OSError(28, "disk full")

    monkeypatch.setattr(fetch.http_client, "stream_to_file", stream)
    monkeypatch.setattr(fetch, "_assemble_pieces", disk_full)
    operation = fetch.start_download()
    await fetch._task

    assert operation.state == "failed"
    assert all(fetch.piece_path(index).exists() for index in range(fetch.PIECES))
    temporary = store.staging_dir() / f".{fake.compressed_name}.assembling.tmp"
    assert temporary.exists()


def test_complete_pieces_fit_existing_free_space_formula(monkeypatch):
    fake, _, _ = _source(monkeypatch)
    remaining = store.required_free_bytes(fake.compressed_size)
    assert remaining >= fake.compressed_size
    assert remaining == fake.uncompressed_size + 100 * 1024**2


@pytest.mark.asyncio
async def test_download_checksum_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    fake, _, compressed = _source(monkeypatch)
    bad = b"x" * len(compressed)
    minimum = store.required_free_bytes(0)
    monkeypatch.setattr(store.shutil, "disk_usage", lambda _: SimpleNamespace(free=minimum))

    async def stream(url, destination, **kwargs):
        start = kwargs.get("offset", 0)
        size = kwargs["expected_size"]
        destination.write_bytes(bad[start : start + size])

    monkeypatch.setattr(fetch.http_client, "stream_to_file", stream)
    operation = fetch.start_download()
    await fetch._task
    assert operation.state == "failed"
    assert operation.message == (
        "The downloaded file didn't match its published checksum. Download it again."
    )
    assert not (store.staging_dir() / fake.compressed_name).exists()
    assert not (store.staging_dir() / f".{fake.compressed_name}.assembling.tmp").exists()
    assert not any(fetch.piece_path(index).exists() for index in range(fetch.PIECES))


@pytest.mark.asyncio
async def test_unpack_failure_keeps_verified_compressed(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    fake, _, compressed = _source(monkeypatch)
    staged = store.staging_dir() / fake.compressed_name
    staged.parent.mkdir(parents=True)
    staged.write_bytes(compressed)
    monkeypatch.setattr(
        fetch,
        "decompress_and_verify",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("unpack failed")),
    )
    operation = fetch.start_download()
    await fetch._task
    assert operation.state == "failed"
    assert staged.read_bytes() == compressed


@pytest.mark.asyncio
async def test_restart_after_verified_compressed_skips_download(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    fake, raw, compressed = _source(monkeypatch)
    staged = store.staging_dir() / fake.compressed_name
    staged.parent.mkdir(parents=True)
    staged.write_bytes(compressed)
    monkeypatch.setattr(
        fetch.http_client,
        "stream_to_file",
        lambda *args, **kwargs: pytest.fail("download attempted"),
    )
    operation = fetch.start_download()
    await fetch._task
    assert operation.state == "done"
    assert store.catalog_path().read_bytes() == raw


def test_download_insufficient_space(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    _source(monkeypatch)
    monkeypatch.setattr(store.shutil, "disk_usage", lambda _: SimpleNamespace(free=0))
    with pytest.raises(store.InsufficientSpace):
        fetch.start_download()


@pytest.mark.asyncio
async def test_download_cancel_keeps_part_for_resume(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    fake, _, _ = _source(monkeypatch)
    entered = asyncio.Event()

    async def stream(url, destination, *, cancel, **kwargs):
        destination.write_bytes(b"part")
        entered.set()
        await cancel.wait()
        raise fetch.http_client.OperationCancelled("operation cancelled")

    monkeypatch.setattr(fetch.http_client, "stream_to_file", stream)
    operation = fetch.start_download()
    await entered.wait()
    fetch.cancel_operation()
    await fetch._task
    assert operation.state == "cancelled"
    assert fetch.piece_path(0).read_bytes() == b"part"


def test_download_refused_when_installed(monkeypatch):
    monkeypatch.setattr(fetch, "installed", lambda: object())
    with pytest.raises(store.AlreadyInstalled):
        fetch.start_download()


@pytest.mark.asyncio
@pytest.mark.parametrize("compressed_import", [False, True], ids=["dat", "bz2"])
async def test_import_bz2_and_dat(tmp_path, monkeypatch, compressed_import):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    fake, raw, compressed = _source(monkeypatch)
    source = tmp_path / (fake.compressed_name if compressed_import else fake.uncompressed_name)
    source.write_bytes(compressed if compressed_import else raw)
    operation = fetch.start_import(source)
    await fetch._task
    assert operation.state == "done"
    assert store.catalog_path().read_bytes() == raw


@pytest.mark.asyncio
async def test_import_wrong_file(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    fake, raw, _ = _source(monkeypatch)
    source = tmp_path / fake.uncompressed_name
    source.write_bytes(b"x" * len(raw))
    operation = fetch.start_import(source)
    await fetch._task
    assert operation.state == "failed"
    assert operation.message == (
        "This file isn't the Siril Gaia DR3 astrometry catalogue, version 1.0.0."
    )
    assert not store.staging_dir().exists()


@pytest.mark.asyncio
async def test_shutdown_waits_for_operation(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    fake, raw, _ = _source(monkeypatch)
    source = tmp_path / fake.uncompressed_name
    source.write_bytes(raw)
    entered = threading.Event()
    release = threading.Event()

    def blocked_copy(source, destination, cancel):
        entered.set()
        release.wait()
        raise InterruptedError("operation cancelled")

    monkeypatch.setattr(fetch, "_copy_file", blocked_copy)
    fetch.start_import(source)
    while not entered.is_set():
        await asyncio.sleep(0)
    stopping = asyncio.create_task(fetch.shutdown())
    await asyncio.sleep(0.02)
    assert not stopping.done()
    release.set()
    await stopping
    assert fetch.current_operation().state == "cancelled"


@pytest.mark.asyncio
async def test_claim_removes_stale_staging_and_unverified_archive(tmp_path, monkeypatch):
    """A crash leaves a hidden unpack temp file and a build folder behind; the
    next operation removes them, but keeps the partial and verified downloads."""
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)
    stage = store.staging_dir()
    stage.mkdir(parents=True)
    stale_unpack = stage / ".siril_cat_healpix8_astro.dat.12345.tmp"
    stale_unpack.write_bytes(b"half unpacked")
    stale_build = stage / "build-q004-0123456789abcdef"
    (stale_build / ".q004.ncidx.build-x").mkdir(parents=True)
    (stale_build / ".q004.ncidx.build-x" / "part-001.bin").write_bytes(b"quads")
    partial = stage / f"{store.SIRIL_SOURCE.compressed_name}.part"
    partial.write_bytes(b"resumable")
    piece = fetch.piece_path(1)
    piece.write_bytes(b"piece")
    compressed = stage / store.SIRIL_SOURCE.compressed_name
    compressed.write_bytes(b"unverified")

    fetch._claim(fetch.StarOperation(kind="build", phase="building"), lambda: None)
    await fetch._task

    assert not stale_unpack.exists()
    assert not stale_build.exists()
    assert partial.read_bytes() == b"resumable"
    assert piece.read_bytes() == b"piece"
    assert not compressed.exists()


def test_partial_selection_validates_sizes_and_keeps_larger_form(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    fake, _, _ = _source(monkeypatch, b"partial selection rows" * 10)
    bounds = fetch.piece_bounds(fake.compressed_size, fetch.PIECES)
    stage = store.staging_dir()
    stage.mkdir(parents=True)
    legacy = stage / f"{fake.compressed_name}.part"
    legacy.write_bytes(b"legacy")
    fetch.piece_path(0).write_bytes(b"p" * (len(b"legacy") + 1))
    fetch.piece_path(1).write_bytes(b"x" * (bounds[1][1] - bounds[1][0] + 1))

    mode, already, sizes = fetch._select_partial()

    assert mode == "pieces"
    assert already == len(b"legacy") + 1
    assert sizes[1] == 0
    assert not legacy.exists()
    assert not fetch.piece_path(1).exists()


@pytest.mark.parametrize("start", ["download", "import"])
def test_stale_assembly_is_removed_before_space_preflight(tmp_path, monkeypatch, start):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    fake, raw, _ = _source(monkeypatch)
    stage = store.staging_dir()
    stage.mkdir(parents=True)
    stale = stage / f".{fake.compressed_name}.assembling.tmp"
    stale.write_bytes(b"stale")
    checked = []

    def space(_already):
        checked.append(not stale.exists())
        raise store.InsufficientSpace(1, 0)

    monkeypatch.setattr(fetch, "ensure_free_space", space)
    if start == "download":
        with pytest.raises(store.InsufficientSpace):
            fetch.start_download()
    else:
        source = tmp_path / fake.uncompressed_name
        source.write_bytes(raw)
        with pytest.raises(store.InsufficientSpace):
            fetch.start_import(source)

    assert checked == [True]


@pytest.mark.asyncio
async def test_restart_removes_stale_assembly_before_minimum_space_check(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    fake, raw, compressed = _source(monkeypatch, b"stale assembly restart rows" * 20)
    bounds = fetch.piece_bounds(fake.compressed_size, fetch.PIECES)
    stage = store.staging_dir()
    stage.mkdir(parents=True)
    stale = stage / f".{fake.compressed_name}.assembling.tmp"
    stale.write_bytes(b"stale allocation")
    prefix = 3
    fetch.piece_path(0).write_bytes(compressed[:prefix])
    already = prefix
    checks = []

    def space(downloaded):
        checks.append(downloaded)
        assert not stale.exists()
        assert downloaded == already
        assert store.required_free_bytes(downloaded) == (
            fake.compressed_size - downloaded + fake.uncompressed_size + 100 * 1024**2
        )

    monkeypatch.setattr(fetch, "ensure_free_space", space)
    monkeypatch.setattr(fetch.http_client, "stream_to_file", _stream_from(compressed))
    operation = fetch.start_download()
    await fetch._task

    assert checks == [already]
    assert operation.state == "done"
    assert store.catalog_path().read_bytes() == raw
    assert bounds[0][1] > prefix


@pytest.mark.asyncio
async def test_interrupted_import_archive_beside_pieces_is_discarded_on_resume(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    fake, raw, compressed = _source(monkeypatch, b"interrupted import rows" * 20)
    piece_started = 0
    all_pieces_started = asyncio.Event()

    async def partial_stream(url, destination, **kwargs):
        nonlocal piece_started
        start = kwargs["offset"]
        destination.write_bytes(compressed[start : start + 1])
        piece_started += 1
        if piece_started == fetch.PIECES:
            all_pieces_started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(fetch.http_client, "stream_to_file", partial_stream)
    download = fetch.start_download()
    await all_pieces_started.wait()
    fetch.cancel_operation()
    await fetch._task
    assert download.state == "cancelled"
    partial_sizes = [fetch.piece_path(index).stat().st_size for index in range(fetch.PIECES)]

    corrupt = tmp_path / fake.compressed_name
    corrupt.write_bytes(b"x" * fake.compressed_size)
    verification_started = asyncio.Event()
    original_import = fetch._import

    async def interrupted_import(path):
        target = store.staging_dir() / fake.compressed_name
        target.write_bytes(path.read_bytes())
        fetch.current_operation().phase = "verifying"
        verification_started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(fetch, "_import", interrupted_import)
    imported = fetch.start_import(corrupt)
    await verification_started.wait()
    fetch._task.cancel()
    await fetch._task
    assert imported.state == "cancelled"
    archive = store.staging_dir() / fake.compressed_name
    assert archive.exists()
    assert [fetch.piece_path(index).stat().st_size for index in range(fetch.PIECES)] == (
        partial_sizes
    )

    monkeypatch.setattr(fetch, "_import", original_import)
    archive_absent_at_stream = []
    real_stream = _stream_from(compressed)

    async def resumed_stream(*args, **kwargs):
        archive_absent_at_stream.append(not archive.exists())
        await real_stream(*args, **kwargs)

    monkeypatch.setattr(fetch.http_client, "stream_to_file", resumed_stream)
    resumed = fetch.start_download()
    await fetch._task

    assert all(archive_absent_at_stream)
    assert resumed.state == "done"
    assert store.catalog_path().read_bytes() == raw


@pytest.mark.asyncio
async def test_piece_progress_is_monotonic_with_one_fallback_drop(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    fake, raw, compressed = _source(monkeypatch, b"progress rows" * 20)
    bounds = fetch.piece_bounds(fake.compressed_size, fetch.PIECES)
    prefix = 3
    fetch.piece_path(0).parent.mkdir(parents=True)
    fetch.piece_path(0).write_bytes(compressed[:prefix])
    other_pieces_done = 0
    all_other_pieces_done = asyncio.Event()
    progress_values = []
    drops = []
    real_progress = fetch._progress
    real_reset = fetch._reset_download_speed

    def progress(done):
        if fetch.current_operation().phase == "downloading":
            progress_values.append(done)
        real_progress(done)

    def reset(done):
        drops.append((fetch.current_operation().bytes_done, done, len(progress_values)))
        real_reset(done)

    async def stream(url, destination, **kwargs):
        nonlocal other_pieces_done
        if kwargs.get("allow_whole_file") is False:
            index = next(
                index for index, (start, _) in enumerate(bounds) if start == kwargs["offset"]
            )
            if index == 0:
                await all_other_pieces_done.wait()
                raise fetch.http_client.RangeNotHonoured("range ignored")
            start, end = bounds[index]
            destination.write_bytes(compressed[start:end])
            kwargs["on_bytes"](end - start)
            other_pieces_done += 1
            if other_pieces_done == fetch.PIECES - 1:
                all_other_pieces_done.set()
            return
        await _stream_from(compressed)(url, destination, **kwargs)

    monkeypatch.setattr(fetch, "_progress", progress)
    monkeypatch.setattr(fetch, "_reset_download_speed", reset)
    monkeypatch.setattr(fetch.http_client, "stream_to_file", stream)
    operation = fetch.start_download()
    await fetch._task

    before_drop, after_drop, drop_index = drops[0]
    assert progress_values[:drop_index] == sorted(progress_values[:drop_index])
    assert before_drop > after_drop == prefix
    assert progress_values[drop_index:] == sorted(progress_values[drop_index:])
    assert len(drops) == 1
    assert operation.state == "done"
    assert store.catalog_path().read_bytes() == raw
