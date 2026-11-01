import asyncio
import json
import os
import sys
import threading
from types import SimpleNamespace

import numpy as np
import pytest

from nightcrate.core import app_config
from nightcrate.services.star_catalog import fetch, handles, index, index_build, ranges, store

from .conftest import SyntheticStar, write_siril_catalog


def _write_empty_layer(path, name="q256"):
    metadata = {
        "format": index.INDEX_FORMAT,
        "version": index.INDEX_FORMAT_VERSION,
        "epoch": 2026.0,
        "source": {"uncompressed_sha256": index.SIRIL_SOURCE.uncompressed_sha256},
        "band": ranges.LAYERS[name].__dict__,
        "counts": {"tiles": 0, "stars": 0, "quads": 0},
        "layout": {
            "tile_offset": index.HEADER_SIZE,
            "star_offset": index.HEADER_SIZE,
            "quad_offset": index.HEADER_SIZE,
        },
    }
    encoded = json.dumps(metadata).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        index.MAGIC
        + len(encoded).to_bytes(4, "little")
        + encoded
        + b"\0" * (index.HEADER_SIZE - 12 - len(encoded))
    )
    return path


def _write_q256_catalog(path):
    count = 20_000
    indices = np.arange(count, dtype=np.float64)
    dec = np.degrees(np.arcsin(1.0 - 2.0 * (indices + 0.5) / count))
    ra = indices * 137.50776405003785 % 360.0
    return write_siril_catalog(
        path,
        [
            SyntheticStar(float(star_ra), float(star_dec), g=5.0 + i % 3000 / 1000)
            for i, (star_ra, star_dec) in enumerate(zip(ra, dec, strict=True))
        ],
    )


async def _settings():
    return SimpleNamespace(max_worker_cores=1)


def _fast_build(name, *, on_progress, **_kwargs):
    on_progress(1.0)
    output = store.staging_dir() / f"build-{name}" / f"{name}.ncidx"
    return _write_empty_layer(output, name)


def test_build_layer_rejects_unknown_name(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)
    with pytest.raises(ValueError, match="Unknown index layer"):
        index_build.build_layer(
            "unknown", threads=1, cancel=threading.Event(), on_progress=lambda _: None
        )


def test_build_layer_matches_prototype_format(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)
    from nightcrate.services.star_catalog.index import IndexLayer
    from nightcrate.services.star_catalog.store import SIRIL_SOURCE, catalog_path

    _write_q256_catalog(catalog_path())
    progress = []
    output = index_build.build_layer(
        "q256", threads=1, cancel=threading.Event(), on_progress=progress.append
    )
    with IndexLayer(output) as layer:
        assert len(layer.quads) > 0
        assert layer.metadata["format"] == "nightcrate-star-index"
        assert layer.metadata["version"] == 1
        assert layer.metadata["epoch"] == 2026.0
        assert layer.metadata["source"]["uncompressed_sha256"] == SIRIL_SOURCE.uncompressed_sha256
    assert progress[-1] == 1.0


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX open-file limit")
def test_build_layer_needs_few_open_files(tmp_path, monkeypatch):
    # macOS starts terminal processes with a 256-file limit; the builder once
    # held one file per partition (256) open at a time.
    import resource

    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)
    _write_q256_catalog(store.catalog_path())
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    limit = min(soft, len(os.listdir("/dev/fd")) + 64)
    resource.setrlimit(resource.RLIMIT_NOFILE, (limit, hard))
    try:
        output = index_build.build_layer(
            "q256", threads=1, cancel=threading.Event(), on_progress=lambda _: None
        )
    finally:
        resource.setrlimit(resource.RLIMIT_NOFILE, (soft, hard))

    with index.IndexLayer(output) as layer:
        assert len(layer.quads) > 0


def test_build_reports_intermediate_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)
    from nightcrate.services.star_catalog.store import catalog_path

    _write_q256_catalog(catalog_path())
    progress = []
    index_build.build_layer(
        "q256", threads=1, cancel=threading.Event(), on_progress=progress.append
    )
    assert progress == sorted(progress)
    assert len({value for value in progress if 0 < value < 1}) >= 3


def test_build_cancel_terminates_child_and_cleans_staging(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)
    _write_q256_catalog(store.catalog_path())
    cancel = threading.Event()
    progressed = threading.Event()
    errors = []

    def build():
        try:
            index_build.build_layer(
                "q256",
                threads=1,
                cancel=cancel,
                on_progress=lambda _: progressed.set(),
            )
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=build)
    thread.start()
    assert progressed.wait(timeout=5)
    cancel.set()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert len(errors) == 1
    assert isinstance(errors[0], InterruptedError)
    assert not list(store.staging_dir().glob("build-*"))


def test_build_child_error_cleans_up(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)
    with pytest.raises(RuntimeError):
        index_build.build_layer(
            "q256", threads=1, cancel=threading.Event(), on_progress=lambda _: None
        )
    assert not list(store.staging_dir().glob("build-*"))


def test_build_disk_check(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)
    monkeypatch.setattr(index_build, "layer_state", lambda _: "missing")
    needed = 3 * max(ranges.LAYERS[name].estimated_bytes for name in ranges.FIELD_RANGES[0].layers)
    monkeypatch.setattr(
        index_build.shutil, "disk_usage", lambda _: SimpleNamespace(free=needed - 1)
    )
    with pytest.raises(index_build.InsufficientSpace) as error:
        index_build.validate_build_request(["0.4-10"])
    assert error.value.needed == needed


@pytest.mark.asyncio
async def test_publish_closes_handles_and_reopens(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)
    _write_empty_layer(ranges.layer_path("q256"))
    old = handles.get_layers(["q256"])[0]

    def fake_build(name, **kwargs):
        output = store.staging_dir() / f"build-{name}" / f"{name}.ncidx"
        return _write_empty_layer(output, name)

    async def settings():
        return SimpleNamespace(max_worker_cores=1)

    monkeypatch.setattr(index_build, "layer_state", lambda _: "missing")
    monkeypatch.setattr(index_build, "build_layer", fake_build)
    monkeypatch.setattr(index_build, "get_settings", settings)
    fetch._operation = fetch.StarOperation(kind="build", phase="building", ranges=["0.4-10"])
    fetch._thread_cancel = threading.Event()
    await index_build.run_build(["0.4-10"])
    assert old.closed
    reopened = handles.get_layers(["q256"])[0]
    assert reopened is not old
    assert not reopened.closed
    handles.close_all()
    fetch._operation = None
    fetch._thread_cancel = None


@pytest.mark.asyncio
async def test_builds_and_publishes_ranges_in_field_order(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)
    calls = []

    def build(name, **kwargs):
        if name == "q004":
            assert ranges.read_manifest() == {"0.4-10"}
        calls.append(name)
        return _fast_build(name, **kwargs)

    monkeypatch.setattr(index_build, "build_layer", build)
    monkeypatch.setattr(index_build, "get_settings", _settings)
    fetch._operation = fetch.StarOperation(
        kind="build", phase="building", ranges=["0.2-0.4", "0.4-10"]
    )
    fetch._thread_cancel = threading.Event()

    await index_build.run_build(["0.2-0.4", "0.4-10"])

    assert calls == ["q256", "q128", "q064", "q032", "q016", "q008", "q004"]
    assert ranges.read_manifest() == {"0.4-10", "0.2-0.4"}
    fetch._operation = None
    fetch._thread_cancel = None


@pytest.mark.asyncio
async def test_build_progress_is_weighted_by_estimated_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)
    q128_entered = threading.Event()
    release_q128 = threading.Event()

    def build(name, **kwargs):
        if name == "q128":
            q128_entered.set()
            release_q128.wait(timeout=5)
        return _fast_build(name, **kwargs)

    monkeypatch.setattr(index_build, "build_layer", build)
    monkeypatch.setattr(index_build, "get_settings", _settings)
    operation = fetch.StarOperation(kind="build", phase="building", ranges=["0.4-10"])
    fetch._operation = operation
    fetch._thread_cancel = threading.Event()
    task = asyncio.create_task(index_build.run_build(["0.4-10"]))
    while not q128_entered.is_set():
        await asyncio.sleep(0)

    standard = ranges.FIELD_RANGES[0]
    expected = ranges.LAYERS["q256"].estimated_bytes / sum(
        ranges.LAYERS[name].estimated_bytes for name in standard.layers
    )
    assert operation.range_progress[standard.id] == pytest.approx(expected)
    assert operation.progress == pytest.approx(expected)

    release_q128.set()
    await task
    fetch._operation = None
    fetch._thread_cancel = None


@pytest.mark.asyncio
async def test_cancel_later_range_keeps_published_range(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)
    q004_entered = threading.Event()

    def build(name, *, cancel, **kwargs):
        if name == "q004":
            q004_entered.set()
            cancel.wait(timeout=5)
        return _fast_build(name, cancel=cancel, **kwargs)

    monkeypatch.setattr(index_build, "build_layer", build)
    monkeypatch.setattr(index_build, "get_settings", _settings)
    operation = fetch.start_build(["0.2-0.4", "0.4-10"])
    while not q004_entered.is_set():
        await asyncio.sleep(0)

    assert fetch.cancel_operation()
    await fetch._task

    assert operation.state == "cancelled"
    assert ranges.read_manifest() == {"0.4-10"}
    assert all(ranges.layer_path(name).is_file() for name in ranges.FIELD_RANGES[0].layers)
    assert not ranges.layer_path("q004").exists()
    assert not list(store.staging_dir().glob("build-*"))
    fetch._operation = None
    fetch._task = None


@pytest.mark.asyncio
async def test_failure_later_range_keeps_published_range(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)
    monkeypatch.setattr(index_build, "build_layer", _fast_build)
    monkeypatch.setattr(index_build, "get_settings", _settings)
    real_replace = index_build.os.replace

    def replace(source, destination):
        if destination == ranges.layer_path("q004"):
            raise OSError("q004 publication failed")
        real_replace(source, destination)

    monkeypatch.setattr(index_build.os, "replace", replace)
    operation = fetch.start_build(["0.2-0.4", "0.4-10"])
    await fetch._task

    assert operation.state == "failed"
    assert operation.message == "q004 publication failed"
    assert ranges.read_manifest() == {"0.4-10"}
    assert all(ranges.layer_path(name).is_file() for name in ranges.FIELD_RANGES[0].layers)
    assert not ranges.layer_path("q004").exists()
    assert not list(store.staging_dir().glob("build-*"))
    fetch._operation = None
    fetch._task = None


def test_remove_all_deletes_catalog_and_indexes(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)
    ranges.layer_path("q256").parent.mkdir(parents=True)
    ranges.layer_path("q256").write_bytes(b"index")
    store.catalog_path().parent.mkdir(parents=True)
    store.catalog_path().write_bytes(b"catalog")
    store.staging_dir().mkdir(parents=True)
    (store.staging_dir() / "partial").write_bytes(b"partial")
    index_build.run_remove("all")
    assert not store.catalog_dir().exists()
    assert not ranges.indexes_dir().exists()
    assert not store.staging_dir().exists()


def test_remove_drops_orphan_layers(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)
    from nightcrate.services.star_catalog import ranges

    ranges.write_manifest({"0.4-10"})
    for name in ("q128", "q256", "orphan"):
        ranges.layer_path(name).write_bytes(b"index")
    index_build.run_remove([])
    assert ranges.layer_path("q128").exists()
    assert ranges.layer_path("q256").exists()
    assert not ranges.layer_path("orphan").exists()


def test_remove_with_shared_layers(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)
    custom = (
        ranges.FieldRange("stale-a", "Stale A", False, 1, 2, ("q008",), 1, 0),
        ranges.FieldRange("stale-b", "Stale B", False, 2, 3, ("q008",), 1, 0),
        ranges.FieldRange("small", "Small", False, 3, 4, ("q128",), 1, 0),
        ranges.FieldRange("large", "Large", False, 3, 4, ("q128", "q256"), 2, 0),
    )
    monkeypatch.setattr(ranges, "FIELD_RANGES", custom)
    monkeypatch.setattr(index_build, "FIELD_RANGES", custom)

    ranges.write_manifest({"stale-a", "stale-b"})
    ranges.layer_path("q008").write_bytes(b"stale-but-shared")
    index_build.run_remove(["stale-a"])
    assert ranges.layer_path("q008").exists()
    assert ranges.read_manifest() == {"stale-b"}
    index_build.run_remove(["stale-b"])
    assert not ranges.layer_path("q008").exists()

    ranges.write_manifest({"small", "large"})
    ranges.layer_path("q128").write_bytes(b"stale-but-owned")
    ranges.layer_path("q256").write_bytes(b"large-only")
    index_build.run_remove(["small"])
    assert ranges.layer_path("q128").exists()
    assert ranges.layer_path("q256").exists()
    assert ranges.read_manifest() == {"large"}
    index_build.run_remove(["large"])
    assert not ranges.layer_path("q128").exists()
    assert not ranges.layer_path("q256").exists()
