import asyncio
import errno
import gzip
import json
from pathlib import Path

import httpx
import pytest

from nightcrate.services import http_client


class _ChunkStream(httpx.AsyncByteStream):
    def __init__(self, chunks, *, gate: asyncio.Event | None = None, error=None):
        self.chunks = chunks
        self.gate = gate
        self.error = error

    async def __aiter__(self):
        for index, chunk in enumerate(self.chunks):
            yield chunk
            if index == 0 and self.gate is not None:
                await asyncio.wait_for(self.gate.wait(), timeout=1)
        if self.error is not None:
            raise self.error


def _capture_client_timeouts(monkeypatch) -> list:
    seen: list = []
    original = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"ok"))

    def client(**kwargs):
        seen.append(kwargs["timeout"])
        return original(transport=transport, **kwargs)

    monkeypatch.setattr(http_client.httpx, "AsyncClient", client)
    return seen


@pytest.mark.asyncio
async def test_get_connect_timeout_caps_only_connection_setup(monkeypatch):
    seen = _capture_client_timeouts(monkeypatch)

    response = await http_client.get(
        "https://example.test/file", timeout=180.0, connect_timeout=10.0
    )

    assert response.status_code == 200
    assert len(seen) == 1
    assert isinstance(seen[0], httpx.Timeout)
    assert seen[0].connect == 10.0
    assert (seen[0].read, seen[0].write, seen[0].pool) == (180.0, 180.0, 180.0)


@pytest.mark.asyncio
async def test_get_without_connect_timeout_keeps_single_timeout(monkeypatch):
    seen = _capture_client_timeouts(monkeypatch)

    await http_client.get("https://example.test/file", timeout=42.0)

    assert seen == [42.0]


@pytest.mark.asyncio
async def test_get_retries_connect_timeout_once(monkeypatch):
    attempts: list[str] = []
    original = httpx.AsyncClient

    def handler(request):
        attempts.append(str(request.url))
        if len(attempts) == 1:
            raise httpx.ConnectTimeout("handshake timed out", request=request)
        return httpx.Response(200, content=b"ok")

    monkeypatch.setattr(
        http_client.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    monkeypatch.setattr(http_client.random, "uniform", lambda *_: 0)

    response = await http_client.get("https://example.test/file", connect_timeout=10.0)

    assert response.content == b"ok"
    assert len(attempts) == 2


@pytest.mark.asyncio
async def test_get_attempts_one_disables_retry(monkeypatch):
    calls = 0
    original = httpx.AsyncClient

    def handler(request):
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("offline", request=request)

    monkeypatch.setattr(
        http_client.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )

    with pytest.raises(httpx.ConnectError):
        await http_client.get("https://example.test/file", attempts=1)

    assert calls == 1


@pytest.mark.asyncio
async def test_get_progress_streams_chunks_and_preserves_response_interface(monkeypatch):
    gate = asyncio.Event()
    body = json.dumps({"answer": 42}).encode()
    original = httpx.AsyncClient

    def handler(request):
        return httpx.Response(
            200,
            headers={"Content-Length": str(len(body)), "Content-Type": "application/json"},
            stream=_ChunkStream([body[:5], body[5:]], gate=gate),
            request=request,
        )

    monkeypatch.setattr(
        http_client.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    events: list[http_client.GetEvent] = []
    task = asyncio.create_task(http_client.get("https://example.test/data", on_event=events.append))
    for _ in range(20):
        if any(event.kind == "bytes" for event in events):
            break
        await asyncio.sleep(0)
    assert [event.kind for event in events] == ["attempt", "response", "bytes"]
    assert events[-1].bytes_received == 5
    assert not task.done()
    gate.set()
    response = await asyncio.wait_for(task, timeout=1)

    assert response.status_code == 200
    assert response.content == body
    assert response.text == body.decode()
    assert response.json() == {"answer": 42}
    assert [event.bytes_received for event in events if event.kind == "bytes"] == [5, len(body)]
    assert next(event for event in events if event.kind == "response").content_length == len(body)


@pytest.mark.asyncio
@pytest.mark.parametrize("include_length", [True, False], ids=["compressed", "unknown-total"])
async def test_get_progress_counts_wire_bytes(monkeypatch, include_length):
    body = b"repeated catalog row\n" * 100
    wire = gzip.compress(body)
    headers = {"Content-Encoding": "gzip"}
    if include_length:
        headers["Content-Length"] = str(len(wire))
    original = httpx.AsyncClient
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers=headers,
            stream=_ChunkStream([wire[:11], wire[11:]]),
            request=request,
        )
    )
    monkeypatch.setattr(
        http_client.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=transport, **kwargs),
    )
    events: list[http_client.GetEvent] = []

    response = await http_client.get("https://example.test/gzip", on_event=events.append)

    assert response.content == body
    assert [event for event in events if event.kind == "bytes"][-1].bytes_received == len(wire)
    expected_total = len(wire) if include_length else None
    assert (
        next(event for event in events if event.kind == "response").content_length == expected_total
    )


@pytest.mark.asyncio
async def test_get_progress_partial_read_retries_with_fresh_counter(monkeypatch):
    calls = 0
    original = httpx.AsyncClient

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                200,
                stream=_ChunkStream(
                    [b"partial"],
                    error=httpx.ReadError("reset", request=request),
                ),
                request=request,
            )
        return httpx.Response(200, content=b"complete", request=request)

    monkeypatch.setattr(
        http_client.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    monkeypatch.setattr(http_client.random, "uniform", lambda *_: 0)
    events: list[http_client.GetEvent] = []

    response = await http_client.get("https://example.test/retry", on_event=events.append)

    assert response.content == b"complete"
    assert calls == 2
    assert [event.attempt for event in events if event.kind == "attempt"] == [1, 2]
    assert [event.kind for event in events].count("retry_delay") == 1
    assert [event.bytes_received for event in events if event.kind == "bytes"] == [7, 8]


@pytest.mark.asyncio
async def test_get_progress_follows_redirect_and_reports_final_response(monkeypatch):
    original = httpx.AsyncClient

    def handler(request):
        if request.url.path == "/start":
            return httpx.Response(302, headers={"Location": "/final"}, request=request)
        return httpx.Response(200, content=b"catalog", request=request)

    monkeypatch.setattr(
        http_client.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    events: list[http_client.GetEvent] = []

    response = await http_client.get(
        "https://example.test/start",
        follow_redirects=True,
        on_event=events.append,
    )

    assert response.url.path == "/final"
    assert response.content == b"catalog"
    assert [event.status_code for event in events if event.kind == "response"] == [200]


@pytest.mark.asyncio
@pytest.mark.parametrize(("first_status", "attempts"), [(404, 1), (503, 2)])
async def test_get_progress_preserves_status_retry_policy(monkeypatch, first_status, attempts):
    calls = 0
    original = httpx.AsyncClient

    def handler(request):
        nonlocal calls
        calls += 1
        status = first_status if calls == 1 else 404
        return httpx.Response(status, content=b"error", request=request)

    monkeypatch.setattr(
        http_client.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    monkeypatch.setattr(http_client.random, "uniform", lambda *_: 0)
    events: list[http_client.GetEvent] = []

    response = await http_client.get("https://example.test/status", on_event=events.append)

    assert response.status_code == 404
    assert calls == attempts
    assert [event.kind for event in events].count("retry_delay") == attempts - 1


@pytest.mark.asyncio
async def test_stream_resumes_with_range(tmp_path, monkeypatch):
    body = b"0123456789"
    destination = tmp_path / "file.part"
    destination.write_bytes(body[:4])
    seen = []

    def handler(request):
        seen.append(request.headers["Range"])
        return httpx.Response(
            206,
            headers={"Content-Range": "bytes 4-9/10"},
            content=body[4:],
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        http_client.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    await http_client.stream_to_file(
        "https://example.test/file",
        destination,
        expected_size=len(body),
        on_bytes=lambda _: None,
        cancel=asyncio.Event(),
        label="test",
    )
    assert seen == ["bytes=4-9"]
    assert destination.read_bytes() == body


@pytest.mark.asyncio
async def test_stream_restarts_when_range_ignored(tmp_path, monkeypatch):
    destination = tmp_path / "file.part"
    destination.write_bytes(b"old")
    original = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"new body"))
    monkeypatch.setattr(
        http_client.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=transport, **kwargs),
    )
    await http_client.stream_to_file(
        "https://example.test/file",
        destination,
        expected_size=8,
        on_bytes=lambda _: None,
        cancel=asyncio.Event(),
        label="test",
    )
    assert destination.read_bytes() == b"new body"


@pytest.mark.asyncio
async def test_stream_complete_part_makes_no_request(tmp_path, monkeypatch):
    destination = tmp_path / "file.part"
    destination.write_bytes(b"done")
    monkeypatch.setattr(
        http_client.httpx, "AsyncClient", lambda **kwargs: pytest.fail("request made")
    )
    await http_client.stream_to_file(
        "https://example.test/file",
        destination,
        expected_size=4,
        on_bytes=lambda _: None,
        cancel=asyncio.Event(),
        label="test",
    )


@pytest.mark.asyncio
async def test_stream_wrong_content_range_rejected(tmp_path, monkeypatch):
    destination = tmp_path / "file.part"
    destination.write_bytes(b"old")
    original = httpx.AsyncClient
    transport = httpx.MockTransport(
        lambda request: httpx.Response(206, headers={"Content-Range": "bytes 0-9/10"}, content=b"x")
    )
    monkeypatch.setattr(
        http_client.httpx, "AsyncClient", lambda **kwargs: original(transport=transport, **kwargs)
    )
    with pytest.raises(http_client.MalformedRange):
        await http_client.stream_to_file(
            "https://example.test/file",
            destination,
            expected_size=10,
            on_bytes=lambda _: None,
            cancel=asyncio.Event(),
            label="test",
        )
    assert destination.read_bytes() == b"old"


@pytest.mark.asyncio
async def test_stream_oversized_part_deleted(tmp_path):
    destination = tmp_path / "file.part"
    destination.write_bytes(b"oversized")
    with pytest.raises(ValueError):
        await http_client.stream_to_file(
            "https://example.test/file",
            destination,
            expected_size=2,
            on_bytes=lambda _: None,
            cancel=asyncio.Event(),
            label="test",
        )
    assert not destination.exists()


@pytest.mark.asyncio
async def test_stream_short_body_then_retry_resumes(tmp_path, monkeypatch):
    destination = tmp_path / "file.part"
    seen = []

    def handler(request):
        seen.append(request.headers["Range"])
        if len(seen) == 1:
            return httpx.Response(
                206,
                headers={"Content-Range": "bytes 0-9/10"},
                content=b"0123",
            )
        return httpx.Response(
            206,
            headers={"Content-Range": "bytes 4-9/10"},
            content=b"456789",
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        http_client.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    monkeypatch.setattr(http_client.random, "uniform", lambda *_: 0)
    await http_client.stream_to_file(
        "https://example.test/file",
        destination,
        expected_size=10,
        on_bytes=lambda _: None,
        cancel=asyncio.Event(),
        label="test",
    )
    assert seen == ["bytes=0-9", "bytes=4-9"]
    assert destination.read_bytes() == b"0123456789"


@pytest.mark.asyncio
async def test_stream_never_exceeds_expected_size(tmp_path, monkeypatch):
    destination = tmp_path / "file.part"
    original = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"0123456789"))
    monkeypatch.setattr(
        http_client.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=transport, **kwargs),
    )
    await http_client.stream_to_file(
        "https://example.test/file",
        destination,
        expected_size=4,
        on_bytes=lambda _: None,
        cancel=asyncio.Event(),
        label="test",
    )
    assert destination.read_bytes() == b"0123"


@pytest.mark.asyncio
async def test_stream_disk_full_keeps_partial(tmp_path, monkeypatch):
    destination = tmp_path / "file.part"
    original_open = Path.open

    class DiskFullFile:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def write(self, data):
            self.stream.write(data[:3])
            self.stream.flush()
            raise OSError(errno.ENOSPC, "disk full")

    def patched_open(path, mode="r", *args, **kwargs):
        stream = original_open(path, mode, *args, **kwargs)
        if path == destination and mode == "wb":
            return DiskFullFile(stream)
        return stream

    original = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"0123456789"))
    monkeypatch.setattr(Path, "open", patched_open)
    monkeypatch.setattr(
        http_client.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=transport, **kwargs),
    )
    with pytest.raises(OSError) as error:
        await http_client.stream_to_file(
            "https://example.test/file",
            destination,
            expected_size=10,
            on_bytes=lambda _: None,
            cancel=asyncio.Event(),
            label="test",
        )
    assert error.value.errno == errno.ENOSPC
    assert destination.read_bytes() == b"012"


@pytest.mark.asyncio
async def test_stream_piece_resumes_at_absolute_offset(tmp_path, monkeypatch):
    destination = tmp_path / "piece"
    destination.write_bytes(b"34")
    seen = []

    def handler(request):
        seen.append(request.headers["Range"])
        return httpx.Response(
            206,
            headers={"Content-Range": "bytes 5-6/10"},
            content=b"56",
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        http_client.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )

    await http_client.stream_to_file(
        "https://example.test/file",
        destination,
        expected_size=4,
        offset=3,
        total_size=10,
        allow_whole_file=False,
        on_bytes=lambda _: None,
        cancel=asyncio.Event(),
        label="piece",
    )

    assert seen == ["bytes=5-6"]
    assert destination.read_bytes() == b"3456"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "content_range"),
    [(200, None), (206, "bytes 0-3/10")],
    ids=["whole-file", "wrong-range"],
)
async def test_stream_piece_rejects_unhonoured_range_before_writing(
    tmp_path, monkeypatch, status, content_range
):
    destination = tmp_path / "piece"
    destination.write_bytes(b"old")
    headers = {"Content-Range": content_range} if content_range is not None else None
    original = httpx.AsyncClient
    monkeypatch.setattr(
        http_client.httpx,
        "AsyncClient",
        lambda **kwargs: original(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(status, headers=headers, content=b"wrong")
            ),
            **kwargs,
        ),
    )

    with pytest.raises(http_client.RangeNotHonoured):
        await http_client.stream_to_file(
            "https://example.test/file",
            destination,
            expected_size=5,
            offset=5,
            total_size=10,
            allow_whole_file=False,
            on_bytes=lambda _: None,
            cancel=asyncio.Event(),
            label="piece",
        )

    assert destination.read_bytes() == b"old"
