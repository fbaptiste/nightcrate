"""Tests for the GitHub-backed OpenNGC fetcher."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from nightcrate.catalog_loader import remote


class FakeResponse:
    def __init__(self, *, status_code: int = 200, body: bytes | None = None, json_data: Any = None):
        self.status_code = status_code
        self._json = json_data
        self.content = body or b""

    def json(self) -> Any:
        return self._json


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def fake_transport(monkeypatch):
    """Run the real shared client over a programmable mock transport."""
    calls: list[str] = []
    mapping: dict[str, Any] = {}
    original = httpx.AsyncClient

    def transport_handler(request):
        url = str(request.url)
        calls.append(url)
        handler = mapping.get(url)
        if handler is None:
            raise AssertionError(f"unexpected URL: {url}")
        if callable(handler):
            handler = handler()
        content = handler.content
        if handler._json is not None:
            return httpx.Response(handler.status_code, json=handler._json, request=request)
        return httpx.Response(handler.status_code, content=content, request=request)

    monkeypatch.setattr(
        remote.http_client.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(transport_handler), **kwargs),
    )
    monkeypatch.setattr(remote.http_client.random, "uniform", lambda *_: 0)

    # Collapse retry backoff to zero so tests run fast.
    async def _noop_sleep(_):
        return None

    # Retry backoff lives in the shared helper now.
    monkeypatch.setattr("nightcrate.catalog_loader._common.asyncio.sleep", _noop_sleep)

    return {"mapping": mapping, "calls": calls}


@pytest.mark.anyio
async def test_fetch_latest_release_parses_github_response(fake_transport):
    fake_transport["mapping"][remote.GITHUB_RELEASES_URL] = FakeResponse(
        json_data={
            "tag_name": "v20260307",
            "published_at": "2026-03-07T17:18:41Z",
            "html_url": "https://github.com/mattiaverga/OpenNGC/releases/tag/v20260307",
        },
    )
    info = await remote.fetch_latest_release()
    assert info.tag_name == "v20260307"
    assert info.published_at == "2026-03-07T17:18:41Z"
    assert "releases/tag/v20260307" in info.release_url


@pytest.mark.anyio
async def test_fetch_latest_release_retries_on_failure(fake_transport):
    attempts = {"n": 0}

    def _flaky():
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise RuntimeError("boom")
        return FakeResponse(
            json_data={"tag_name": "v20260307", "published_at": None, "html_url": ""},
        )

    fake_transport["mapping"][remote.GITHUB_RELEASES_URL] = _flaky
    info = await remote.fetch_latest_release()
    assert info.tag_name == "v20260307"
    assert attempts["n"] == 2


@pytest.mark.anyio
async def test_fetch_latest_release_exhausts_retries(fake_transport):
    def _always_boom():
        raise RuntimeError("upstream down")

    fake_transport["mapping"][remote.GITHUB_RELEASES_URL] = _always_boom
    with pytest.raises(RuntimeError, match="upstream down"):
        await remote.fetch_latest_release()
    # RuntimeError is not a shared-client transient; the outer layer tries three times.
    assert len(fake_transport["calls"]) == 3


@pytest.mark.anyio
async def test_fetch_latest_release_raises_on_4xx(fake_transport):
    fake_transport["mapping"][remote.GITHUB_RELEASES_URL] = FakeResponse(status_code=404)
    with pytest.raises(RuntimeError, match="404"):
        await remote.fetch_latest_release()


@pytest.mark.anyio
async def test_download_openngc_writes_files_and_version_json(fake_transport, tmp_path: Path):
    release = remote.RemoteReleaseInfo(
        tag_name="v20260307",
        published_at="2026-03-07T17:18:41Z",
        release_url="https://github.com/mattiaverga/OpenNGC/releases/tag/v20260307",
    )
    ngc_body = b"Name;Type;RA;Dec\nNGC0001;G;00:00:00;+00:00:00\n"
    addendum_body = b"Name;Type;RA;Dec\nB033;DrkN;05:40:59;-02:27:30\n"
    fake_transport["mapping"][f"{remote.RAW_BASE}/v20260307/database_files/NGC.csv"] = FakeResponse(
        body=ngc_body
    )
    fake_transport["mapping"][f"{remote.RAW_BASE}/v20260307/database_files/addendum.csv"] = (
        FakeResponse(body=addendum_body)
    )

    updates = []
    report = await remote.download_openngc(release, tmp_path, updates.append)

    openngc_dir = tmp_path / "openngc"
    assert (openngc_dir / "NGC.csv").read_bytes() == ngc_body
    assert (openngc_dir / "addendum.csv").read_bytes() == addendum_body

    # .download/ tmp dir must be cleaned up after success
    assert not (openngc_dir / ".download").exists()

    # version.json shape + hash round-trip
    version_info = json.loads((openngc_dir / "version.json").read_text())
    assert version_info["version"] == "v20260307"
    assert version_info["source_id"] == "openngc"
    assert version_info["license"] == "CC-BY-SA-4.0"
    assert version_info["files"]["NGC.csv"]["sha256"] == hashlib.sha256(ngc_body).hexdigest()
    assert (
        version_info["files"]["addendum.csv"]["sha256"] == hashlib.sha256(addendum_body).hexdigest()
    )

    assert report.tag == "v20260307"
    assert {f.name for f in report.files} == {"NGC.csv", "addendum.csv"}
    transfer = [update for update in updates if update.phase == "downloading"][-1]
    assert transfer.bytes_received == len(ngc_body) + len(addendum_body)
    assert transfer.bytes_total == len(ngc_body) + len(addendum_body)


@pytest.mark.anyio
async def test_download_openngc_rejects_empty_body(fake_transport, tmp_path: Path):
    release = remote.RemoteReleaseInfo(tag_name="v20260307", published_at=None, release_url="")
    fake_transport["mapping"][f"{remote.RAW_BASE}/v20260307/database_files/NGC.csv"] = FakeResponse(
        body=b""
    )
    fake_transport["mapping"][f"{remote.RAW_BASE}/v20260307/database_files/addendum.csv"] = (
        FakeResponse(body=b"valid sibling")
    )
    with pytest.raises(RuntimeError, match="empty body"):
        await remote.download_openngc(release, tmp_path)

    # Partial download dir cleaned up; real files never landed.
    openngc_dir = tmp_path / "openngc"
    assert not (openngc_dir / "NGC.csv").exists()
    assert not (openngc_dir / "version.json").exists()


@pytest.mark.anyio
async def test_download_openngc_leaves_prior_install_untouched_on_failure(
    fake_transport, tmp_path: Path
):
    # Pre-populate an "existing install" so we can confirm a failed download
    # doesn't clobber it.
    openngc_dir = tmp_path / "openngc"
    openngc_dir.mkdir()
    (openngc_dir / "NGC.csv").write_bytes(b"OLD_NGC")
    (openngc_dir / "addendum.csv").write_bytes(b"OLD_ADDENDUM")
    (openngc_dir / "version.json").write_text(json.dumps({"version": "v20200101"}))

    release = remote.RemoteReleaseInfo(tag_name="v20260307", published_at=None, release_url="")
    # Second file (addendum) fails after first succeeds — atomic rename of
    # NGC.csv should therefore NOT happen either.
    fake_transport["mapping"][f"{remote.RAW_BASE}/v20260307/database_files/NGC.csv"] = FakeResponse(
        body=b"NEW_NGC"
    )

    def _fail():
        raise RuntimeError("network glitch")

    fake_transport["mapping"][f"{remote.RAW_BASE}/v20260307/database_files/addendum.csv"] = _fail

    with pytest.raises(RuntimeError, match="network glitch"):
        await remote.download_openngc(release, tmp_path)

    # Old files preserved.
    assert (openngc_dir / "NGC.csv").read_bytes() == b"OLD_NGC"
    assert (openngc_dir / "addendum.csv").read_bytes() == b"OLD_ADDENDUM"
    assert json.loads((openngc_dir / "version.json").read_text())["version"] == "v20200101"


@pytest.mark.anyio
async def test_download_openngc_retries_individual_file(fake_transport, tmp_path: Path):
    release = remote.RemoteReleaseInfo(tag_name="v20260307", published_at=None, release_url="")
    attempts = {"ngc": 0}

    def _flaky_ngc():
        attempts["ngc"] += 1
        if attempts["ngc"] < 2:
            raise RuntimeError("transient")
        return FakeResponse(body=b"NEW_NGC")

    fake_transport["mapping"][f"{remote.RAW_BASE}/v20260307/database_files/NGC.csv"] = _flaky_ngc
    fake_transport["mapping"][f"{remote.RAW_BASE}/v20260307/database_files/addendum.csv"] = (
        FakeResponse(body=b"NEW_ADDENDUM")
    )

    await remote.download_openngc(release, tmp_path)
    assert attempts["ngc"] == 2
    assert (tmp_path / "openngc" / "NGC.csv").read_bytes() == b"NEW_NGC"


@pytest.mark.anyio
async def test_download_failure_cancels_and_drains_sibling_before_cleanup(monkeypatch, tmp_path):
    sibling_started = asyncio.Event()
    sibling_cancelled = asyncio.Event()
    release_sibling = asyncio.Event()
    original = httpx.AsyncClient

    class GatedStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            sibling_started.set()
            yield b"partial addendum"
            try:
                await release_sibling.wait()
                yield b"late write"
            finally:
                sibling_cancelled.set()

    def handler(request):
        if str(request.url).endswith("NGC.csv"):
            return httpx.Response(200, content=b"", request=request)
        return httpx.Response(200, stream=GatedStream(), request=request)

    monkeypatch.setattr(
        remote.http_client.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    monkeypatch.setattr(remote.http_client.random, "uniform", lambda *_: 0)
    monkeypatch.setattr("nightcrate.catalog_loader._common.random.uniform", lambda *_: 0)
    updates = []
    release = remote.RemoteReleaseInfo("v-test", None, "")

    task = asyncio.create_task(remote.download_openngc(release, tmp_path, updates.append))
    await asyncio.wait_for(sibling_started.wait(), timeout=1)
    with pytest.raises(RuntimeError, match="empty body"):
        await asyncio.wait_for(task, timeout=1)
    assert sibling_cancelled.is_set()
    assert not (tmp_path / "openngc" / ".download").exists()
    update_count = len(updates)
    release_sibling.set()
    await asyncio.sleep(0)
    assert len(updates) == update_count
