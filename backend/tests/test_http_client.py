import asyncio
import errno
from pathlib import Path

import httpx
import pytest

from nightcrate.services import http_client


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
    assert seen == ["bytes=4-"]
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
    assert seen == ["bytes=0-", "bytes=4-"]
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
