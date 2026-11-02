"""HTTP and atomic-install tests for the Wikidata fetcher."""

from __future__ import annotations

import json

import httpx
import pytest

from nightcrate.catalog_loader import wikidata

_BODY = b"?item\t?itemLabel\n" + b"wd:Q1\tExample\n" * 100
assert len(_BODY) > 1024


class _FixtureStream(httpx.AsyncByteStream):
    def __init__(self, content: bytes) -> None:
        self.content = content

    async def __aiter__(self):
        yield self.content


@pytest.fixture
def mock_http(monkeypatch):
    handlers: list[object] = []
    calls = 0
    original = httpx.AsyncClient

    def transport_handler(request):
        nonlocal calls
        calls += 1
        handler = handlers[min(calls - 1, len(handlers) - 1)]
        if isinstance(handler, BaseException):
            raise handler
        headers = handler[2] if len(handler) > 2 else {}
        if "Content-Length" not in headers:
            return httpx.Response(
                handler[0], headers=headers, stream=_FixtureStream(handler[1]), request=request
            )
        return httpx.Response(handler[0], headers=headers, content=handler[1], request=request)

    monkeypatch.setattr(
        wikidata.http_client.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(transport_handler), **kwargs),
    )
    monkeypatch.setattr(wikidata.http_client.random, "uniform", lambda *_: 0)
    monkeypatch.setattr("nightcrate.catalog_loader._common.random.uniform", lambda *_: 0)
    return handlers, lambda: calls


@pytest.mark.asyncio
async def test_fetch_reports_unknown_total_and_installs(mock_http, tmp_path):
    handlers, calls = mock_http
    handlers.append((200, _BODY, {}))
    updates = []

    result = await wikidata.fetch_wikidata_external_refs(
        tmp_path,
        app_version="test",
        on_progress=updates.append,
    )

    assert calls() == 1
    assert result.size_bytes == len(_BODY)
    assert result.output_path.read_bytes() == _BODY
    assert [update.phase for update in updates] == [
        "waiting",
        "downloading",
        "downloading",
        "checking",
        "saving",
    ]
    transfer = [update for update in updates if update.phase == "downloading"][-1]
    assert transfer.bytes_received == len(_BODY)
    assert transfer.bytes_total is None


@pytest.mark.asyncio
async def test_fetch_nested_retry_reports_retry(mock_http, tmp_path):
    handlers, calls = mock_http
    handlers.extend(
        [
            httpx.ConnectError("offline"),
            (200, _BODY, {"Content-Length": str(len(_BODY))}),
        ]
    )
    updates = []

    await wikidata.fetch_wikidata_external_refs(
        tmp_path,
        app_version="test",
        on_progress=updates.append,
    )

    assert calls() == 2
    assert any(update.phase == "retrying" for update in updates)
    assert [update for update in updates if update.phase == "downloading"][-1].bytes_total == len(
        _BODY
    )


@pytest.mark.asyncio
async def test_invalid_download_keeps_installed_files(mock_http, tmp_path):
    handlers, _calls = mock_http
    handlers.append((200, b"x" * 2048, {}))
    dest = tmp_path / "wikidata"
    dest.mkdir()
    installed = dest / "dso_external_refs.tsv"
    installed.write_bytes(b"previous")
    version = dest / "version.json"
    version.write_text(json.dumps({"fetched_at": "old"}), encoding="utf-8")

    with pytest.raises(ValueError, match="expected SPARQL TSV header"):
        await wikidata.fetch_wikidata_external_refs(tmp_path, app_version="test")

    assert installed.read_bytes() == b"previous"
    assert json.loads(version.read_text())["fetched_at"] == "old"
    assert not (dest / ".download").exists()
