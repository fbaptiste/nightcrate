"""Tests for the GitHub-backed 50 MGC fetcher.

Mocks ``services.http_client.get`` to verify atomic rename, version.json
commit marker, retry exhaustion, and short-body rejection.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from nightcrate.catalog_loader import mgc50_fetch

_SIZEABLE_BODY = b"# catalog.fits\n" + b"x" * 2048


class FakeResponse:
    def __init__(self, *, status_code: int = 200, body: bytes = b""):
        self.status_code = status_code
        self.content = body


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def fake_transport(monkeypatch):
    calls: list[str] = []
    mapping: dict[str, object] = {}

    async def fake_get(url, *args, **kwargs):
        calls.append(url)
        handler = mapping.get(url)
        if handler is None:
            raise AssertionError(f"unexpected URL: {url}")
        if callable(handler):
            return handler()
        return handler

    monkeypatch.setattr("nightcrate.catalog_loader.mgc50_fetch.http_client.get", fake_get)

    async def _noop_sleep(_):
        return None

    monkeypatch.setattr("nightcrate.catalog_loader._common.asyncio.sleep", _noop_sleep)
    return {"mapping": mapping, "calls": calls}


@pytest.mark.anyio
async def test_fetch_writes_file_and_version_json(fake_transport, tmp_path: Path):
    fake_transport["mapping"][mgc50_fetch.MGC50_RAW_URL] = FakeResponse(body=_SIZEABLE_BODY)

    result = await mgc50_fetch.fetch_50mgc_from_github(tmp_path)

    dest = tmp_path / "github" / "50mgc"
    assert (dest / "catalog.fits").read_bytes() == _SIZEABLE_BODY
    # .download/ tmp dir cleaned up after success
    assert not (dest / ".download").exists()

    info = json.loads((dest / "version.json").read_text())
    assert info["source_id"] == "github_50mgc"
    assert info["source_url"] == mgc50_fetch.MGC50_RAW_URL
    assert info["repository_url"] == mgc50_fetch.MGC50_REPO_URL
    assert info["sha256"] == hashlib.sha256(_SIZEABLE_BODY).hexdigest()
    assert info["size_bytes"] == len(_SIZEABLE_BODY)
    assert info["citation"].startswith("Ohlson")

    assert result.size_bytes == len(_SIZEABLE_BODY)
    assert result.sha256 == hashlib.sha256(_SIZEABLE_BODY).hexdigest()


@pytest.mark.anyio
async def test_fetch_retries_on_transient_failure(fake_transport, tmp_path: Path):
    attempts = {"n": 0}

    def _flaky():
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise RuntimeError("transient")
        return FakeResponse(body=_SIZEABLE_BODY)

    fake_transport["mapping"][mgc50_fetch.MGC50_RAW_URL] = _flaky
    await mgc50_fetch.fetch_50mgc_from_github(tmp_path)
    assert attempts["n"] == 2
    assert (tmp_path / "github" / "50mgc" / "catalog.fits").exists()


@pytest.mark.anyio
async def test_fetch_exhausts_retries(fake_transport, tmp_path: Path):
    def _always_fail():
        raise RuntimeError("upstream down")

    fake_transport["mapping"][mgc50_fetch.MGC50_RAW_URL] = _always_fail
    with pytest.raises(RuntimeError, match="upstream down"):
        await mgc50_fetch.fetch_50mgc_from_github(tmp_path)
    # Default max_attempts=3 → 3 upstream calls
    assert len(fake_transport["calls"]) == 3
    # Partial download dir cleaned up
    assert not (tmp_path / "github" / "50mgc" / "catalog.fits").exists()
    assert not (tmp_path / "github" / "50mgc" / ".download").exists()


@pytest.mark.anyio
async def test_fetch_rejects_short_body(fake_transport, tmp_path: Path):
    """A body smaller than ``_MIN_BODY_BYTES`` looks like an HTML error
    page or truncated response — treat as failure."""
    fake_transport["mapping"][mgc50_fetch.MGC50_RAW_URL] = FakeResponse(body=b"oops")
    with pytest.raises(RuntimeError, match="too small"):
        await mgc50_fetch.fetch_50mgc_from_github(tmp_path)


@pytest.mark.anyio
async def test_fetch_rejects_4xx_status(fake_transport, tmp_path: Path):
    fake_transport["mapping"][mgc50_fetch.MGC50_RAW_URL] = FakeResponse(status_code=404)
    with pytest.raises(RuntimeError, match="404"):
        await mgc50_fetch.fetch_50mgc_from_github(tmp_path)


@pytest.mark.anyio
async def test_fetch_leaves_prior_install_untouched_on_failure(fake_transport, tmp_path: Path):
    """A failed re-fetch must not clobber the previously-committed file."""
    dest = tmp_path / "github" / "50mgc"
    dest.mkdir(parents=True)
    (dest / "catalog.fits").write_bytes(b"OLD_TABLEA1")
    (dest / "version.json").write_text(
        json.dumps({"source_id": "github_50mgc", "fetched_at": "2025-01-01T00:00:00+00:00"})
    )

    def _fail():
        raise RuntimeError("network glitch")

    fake_transport["mapping"][mgc50_fetch.MGC50_RAW_URL] = _fail
    with pytest.raises(RuntimeError, match="network glitch"):
        await mgc50_fetch.fetch_50mgc_from_github(tmp_path)

    # Prior install preserved — we never reached the invalidate-and-rename step.
    assert (dest / "catalog.fits").read_bytes() == b"OLD_TABLEA1"
    info = json.loads((dest / "version.json").read_text())
    assert info["fetched_at"] == "2025-01-01T00:00:00+00:00"


def test_read_installed_fetch_returns_empty_when_missing(tmp_path: Path):
    assert mgc50_fetch.read_installed_fetch(tmp_path) == {}


def test_read_installed_fetch_tolerates_corrupt_json(tmp_path: Path):
    dest = tmp_path / "github" / "50mgc"
    dest.mkdir(parents=True)
    (dest / "version.json").write_text("{ not json")
    assert mgc50_fetch.read_installed_fetch(tmp_path) == {}


def test_read_installed_fetch_returns_parsed_payload(tmp_path: Path):
    dest = tmp_path / "github" / "50mgc"
    dest.mkdir(parents=True)
    (dest / "version.json").write_text(
        json.dumps({"source_id": "github_50mgc", "fetched_at": "2026-04-19T12:00:00+00:00"})
    )
    assert mgc50_fetch.read_installed_fetch(tmp_path)["fetched_at"] == "2026-04-19T12:00:00+00:00"
