import asyncio
import bz2
import hashlib
import os
import threading
from dataclasses import replace
from types import SimpleNamespace

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
        destination.write_bytes(compressed)

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
async def test_download_checksum_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    fake, _, compressed = _source(monkeypatch)

    async def stream(url, destination, **kwargs):
        destination.write_bytes(b"x" * len(compressed))

    monkeypatch.setattr(fetch.http_client, "stream_to_file", stream)
    operation = fetch.start_download()
    await fetch._task
    assert operation.state == "failed"
    assert operation.message == (
        "The downloaded file didn't match its published checksum. Download it again."
    )
    assert not (store.staging_dir() / fake.compressed_name).exists()


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
        destination.write_bytes(b"partial")
        entered.set()
        await cancel.wait()
        raise fetch.http_client.OperationCancelled("operation cancelled")

    monkeypatch.setattr(fetch.http_client, "stream_to_file", stream)
    operation = fetch.start_download()
    await entered.wait()
    fetch.cancel_operation()
    await fetch._task
    assert operation.state == "cancelled"
    assert (store.staging_dir() / f"{fake.compressed_name}.part").read_bytes() == b"partial"


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
async def test_claim_removes_stale_staging_but_keeps_resumable_files(tmp_path, monkeypatch):
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
    compressed = stage / store.SIRIL_SOURCE.compressed_name
    compressed.write_bytes(b"verified")

    fetch._claim(fetch.StarOperation(kind="build", phase="building"), lambda: None)
    await fetch._task

    assert not stale_unpack.exists()
    assert not stale_build.exists()
    assert partial.read_bytes() == b"resumable"
    assert compressed.read_bytes() == b"verified"
