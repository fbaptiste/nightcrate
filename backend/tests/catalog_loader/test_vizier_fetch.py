"""Tests for the VizieR TSV fetcher — one pass over the mirrors.

Parser-level assertions live in ``test_vizier_tsv.py``. This module focuses
on the HTTP layer: each mirror in ``VIZIER_HOSTS`` is tried once (the shared
HTTP client retries transient failures itself), a failing or malformed
response moves on to the next mirror, ``version.json`` records the mirror that
served the data, and full exhaustion raises ``RuntimeError`` without touching
the installed copy.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from nightcrate.catalog_loader import vizier
from nightcrate.services import catalog_progress

_MIN_TSV_BODY = (
    "# VizieR metadata header\ncol_RA\tcol_DE\n--\t--\n------\t------\n" + "1.0\t2.0\n" * 200
).encode("utf-8")
assert len(_MIN_TSV_BODY) > 1024, "fixture must clear _MIN_BODY_BYTES"

# Over the 1 kB minimum, but with no tab-separated header.
_HTML_ERROR_PAGE = b"<html><body>" + b"Service temporarily unavailable. " * 64 + b"</body></html>"
assert len(_HTML_ERROR_PAGE) > 1024

# Tab-indented HTML: the first non-blank line contains a tab.
_TABBED_HTML = b"\t<html>\n" + b"\t\t<p>Service temporarily unavailable.</p>\n" * 40 + b"</html>\n"
assert len(_TABBED_HTML) > 1024

# A TSV-shaped proxy error: tab-separated rows but no VizieR units/hyphen rows.
_TSV_PROXY_ERROR = b"status\tmessage\n" + b"503\tupstream unavailable, retry later\n" * 40
assert len(_TSV_PROXY_ERROR) > 1024


def _vizier_body(columns: list[str]) -> bytes:
    header = "\t".join(columns)
    units = "\t".join("deg" for _ in columns)
    separator = "\t".join("-" * 8 for _ in columns)
    rows = "\t".join("1.0" for _ in columns) + "\n"
    lines = ["# VizieR metadata", header, units, separator]
    return ("\n".join(lines) + "\n" + rows * 120).encode()


PRIMARY, SECOND, THIRD = vizier.VIZIER_HOSTS


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        body: bytes = b"",
        stream: httpx.AsyncByteStream | None = None,
    ):
        self.status_code = status_code
        self.content = body
        self.stream = stream


class DroppedConnectionStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield b"partial catalog"
        raise httpx.RemoteProtocolError("peer closed connection")


class AdvancingDroppedConnectionStream(httpx.AsyncByteStream):
    def __init__(self, advance):
        self._advance = advance

    async def __aiter__(self):
        yield b"partial catalog"
        self._advance()
        raise httpx.ReadError("peer closed connection")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def fake_transport(monkeypatch):
    calls: list[tuple[str, dict]] = []
    handlers: dict[str, object] = {}
    original = httpx.AsyncClient

    def client(**kwargs):
        def transport_handler(request):
            url = str(request.url)
            calls.append((url, kwargs))
            for host, handler in handlers.items():
                if url.startswith(f"https://{host}/"):
                    if callable(handler):
                        handler = handler()
                    return httpx.Response(
                        handler.status_code,
                        content=handler.content if handler.stream is None else None,
                        stream=handler.stream,
                        request=request,
                    )
            raise AssertionError(f"unexpected URL: {url}")

        return original(transport=httpx.MockTransport(transport_handler), **kwargs)

    monkeypatch.setattr(vizier.http_client.httpx, "AsyncClient", client)
    monkeypatch.setattr(vizier.http_client.random, "uniform", lambda *_: 0)
    return {"handlers": handlers, "calls": calls}


def _hosts_called(fake_transport) -> list[str]:
    return [url.split("/")[2] for url, _ in fake_transport["calls"]]


def _spec():
    return vizier.VizierFetchSpec(
        source_id="vizier_test",
        catalog_id="VII/20/catalog",
        output_filename="test.tsv",
        display_name="Test VizieR",
        citation="test",
    )


def _raise(exc: BaseException):
    def _handler():
        raise exc

    return _handler


@pytest.mark.anyio
async def test_primary_success_calls_only_primary(fake_transport, tmp_path: Path):
    fake_transport["handlers"][PRIMARY] = FakeResponse(body=_MIN_TSV_BODY)

    result = await vizier.fetch_vizier_catalog(_spec(), tmp_path)

    assert _hosts_called(fake_transport) == [PRIMARY]
    assert (tmp_path / "vizier" / "test.tsv").read_bytes() == _MIN_TSV_BODY
    assert result.source_url == vizier._build_url(_spec(), PRIMARY)
    assert result.size_bytes == len(_MIN_TSV_BODY)
    version = json.loads((tmp_path / "vizier" / "version.json").read_text())
    assert version["files"]["test.tsv"]["source_url"].startswith(f"https://{PRIMARY}/")


@pytest.mark.anyio
async def test_unreachable_primary_falls_to_next_mirror(fake_transport, tmp_path: Path):
    """One attempt per host here: ``http_client.get`` owns the transient retry."""
    fake_transport["handlers"][PRIMARY] = _raise(httpx.ConnectTimeout(""))
    fake_transport["handlers"][SECOND] = FakeResponse(body=_MIN_TSV_BODY)

    result = await vizier.fetch_vizier_catalog(_spec(), tmp_path)

    assert _hosts_called(fake_transport) == [PRIMARY, PRIMARY, SECOND]
    assert result.source_url == vizier._build_url(_spec(), SECOND)
    version = json.loads((tmp_path / "vizier" / "version.json").read_text())
    assert version["files"]["test.tsv"]["source_url"].startswith(f"https://{SECOND}/")
    assert (tmp_path / "vizier" / "test.tsv").read_bytes() == _MIN_TSV_BODY


@pytest.mark.anyio
async def test_every_call_caps_connection_setup(fake_transport, tmp_path: Path):
    fake_transport["handlers"][PRIMARY] = _raise(httpx.ConnectError("refused"))
    fake_transport["handlers"][SECOND] = FakeResponse(body=_MIN_TSV_BODY)

    await vizier.fetch_vizier_catalog(_spec(), tmp_path)

    assert len(fake_transport["calls"]) == 3
    for _, kwargs in fake_transport["calls"]:
        timeout = kwargs["timeout"]
        assert isinstance(timeout, httpx.Timeout)
        assert timeout.connect == 10.0
        assert timeout.read == 180.0


@pytest.mark.anyio
@pytest.mark.parametrize(
    "bad_primary",
    [
        FakeResponse(body=b"nope"),  # truncated
        FakeResponse(body=_HTML_ERROR_PAGE),  # error page served as HTTP 200
        FakeResponse(status_code=503, body=_MIN_TSV_BODY),  # server error
        FakeResponse(body=_TABBED_HTML),  # indented HTML has tabs but no envelope
        FakeResponse(body=_TSV_PROXY_ERROR),  # tabular error page without hyphen row
    ],
    ids=["short-body", "html-page", "http-503", "tabbed-html", "tsv-proxy-error"],
)
async def test_bad_primary_response_falls_through(fake_transport, tmp_path: Path, bad_primary):
    fake_transport["handlers"][PRIMARY] = bad_primary
    fake_transport["handlers"][SECOND] = FakeResponse(body=_MIN_TSV_BODY)

    result = await vizier.fetch_vizier_catalog(_spec(), tmp_path)

    expected_primary_calls = 2 if bad_primary.status_code >= 500 else 1
    assert _hosts_called(fake_transport) == [PRIMARY] * expected_primary_calls + [SECOND]
    assert result.source_url.startswith(f"https://{SECOND}/")
    assert (tmp_path / "vizier" / "test.tsv").read_bytes() == _MIN_TSV_BODY


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        (_raise(httpx.ReadTimeout("slow")), "Strasbourg timed out"),
        (_raise(httpx.ConnectError("offline")), "Strasbourg couldn't connect"),
        (FakeResponse(status_code=503), "Strasbourg returned an error (HTTP 503)"),
        (FakeResponse(body=b""), "Strasbourg returned no data"),
        (
            FakeResponse(body=_HTML_ERROR_PAGE),
            "Strasbourg returned something that isn't the catalog",
        ),
        (_raise(RuntimeError("boom")), "Strasbourg failed"),
    ],
    ids=["timeout", "connect", "http", "empty", "invalid", "unexpected"],
)
async def test_progress_explains_why_each_mirror_is_skipped(
    fake_transport, tmp_path, failure, reason
):
    fake_transport["handlers"][PRIMARY] = failure
    fake_transport["handlers"][SECOND] = FakeResponse(body=_MIN_TSV_BODY)
    updates = []

    await vizier.fetch_vizier_catalog(_spec(), tmp_path, updates.append)

    assert any(
        update.message.startswith(f"{reason} after ")
        and update.message.endswith(" s. Trying the Harvard mirror…")
        for update in updates
    )
    assert any(
        update.message == "Downloading Test VizieR from the Harvard mirror…" for update in updates
    )


@pytest.mark.anyio
async def test_third_mirror_used_when_first_two_fail(fake_transport, tmp_path: Path):
    fake_transport["handlers"][PRIMARY] = _raise(httpx.ConnectTimeout(""))
    fake_transport["handlers"][SECOND] = FakeResponse(status_code=502)
    fake_transport["handlers"][THIRD] = FakeResponse(body=_MIN_TSV_BODY)

    result = await vizier.fetch_vizier_catalog(_spec(), tmp_path)

    assert _hosts_called(fake_transport) == [PRIMARY, PRIMARY, SECOND, SECOND, THIRD]
    assert result.source_url.startswith(f"https://{THIRD}/")


@pytest.mark.anyio
async def test_progress_names_all_three_hosts(fake_transport, tmp_path: Path):
    fake_transport["handlers"][PRIMARY] = _raise(httpx.ConnectTimeout(""))
    fake_transport["handlers"][SECOND] = FakeResponse(status_code=502)
    fake_transport["handlers"][THIRD] = FakeResponse(body=_MIN_TSV_BODY)
    updates = []

    await vizier.fetch_vizier_catalog(_spec(), tmp_path, updates.append)

    messages = [update.message for update in updates]
    assert "Trying CDS Strasbourg…" in messages
    assert any(
        message.startswith("Strasbourg timed out after ")
        and message.endswith(" s. Trying the Harvard mirror…")
        for message in messages
    )
    assert any(
        message.startswith("Harvard returned an error (HTTP 502) after ")
        and message.endswith(" s. Trying the South Africa mirror…")
        for message in messages
    )
    assert "Downloading Test VizieR from the South Africa mirror…" in messages


@pytest.mark.anyio
async def test_progress_reports_a_midstream_disconnect(fake_transport, tmp_path: Path):
    fake_transport["handlers"][PRIMARY] = _raise(httpx.ConnectError("offline"))
    fake_transport["handlers"][SECOND] = FakeResponse(stream=DroppedConnectionStream())
    fake_transport["handlers"][THIRD] = FakeResponse(body=_MIN_TSV_BODY)
    updates = []

    await vizier.fetch_vizier_catalog(_spec(), tmp_path, updates.append)

    messages = [update.message for update in updates]
    assert any(
        message.startswith("Harvard dropped the connection after ")
        and message.endswith(" s. Trying the South Africa mirror…")
        for message in messages
    )


@pytest.mark.anyio
async def test_host_duration_covers_retries_backoff_and_next_counter_advances(
    fake_transport, tmp_path: Path, monkeypatch
):
    now = 100.0

    def advance(delta: float) -> None:
        nonlocal now
        now += delta

    async def advance_sleep(delay: float) -> None:
        advance(delay)

    def primary_failure():
        return FakeResponse(stream=AdvancingDroppedConnectionStream(lambda: advance(10.25)))

    harvard_elapsed: list[float] = []

    def harvard_failure():
        advance(4.25)
        snapshot = catalog_progress.snapshot()
        assert snapshot is not None
        harvard_elapsed.append(snapshot["phase_elapsed_s"])
        return FakeResponse(status_code=502)

    fake_transport["handlers"][PRIMARY] = primary_failure
    fake_transport["handlers"][SECOND] = harvard_failure
    fake_transport["handlers"][THIRD] = FakeResponse(body=_MIN_TSV_BODY)
    monkeypatch.setattr(vizier, "_clock", lambda: now)
    monkeypatch.setattr(catalog_progress, "_clock", lambda: now)
    monkeypatch.setattr(vizier.http_client.asyncio, "sleep", advance_sleep)
    monkeypatch.setattr(vizier.http_client.random, "uniform", lambda *_: 0.5)
    catalog_progress.reset()
    operation_id = catalog_progress.start("fetch", source="vizier_test")
    updates = []
    callback = catalog_progress.callback(operation_id)

    def record(update):
        updates.append(update)
        callback(update)

    try:
        await vizier.fetch_vizier_catalog(_spec(), tmp_path, record)
    finally:
        catalog_progress.reset()

    assert _hosts_called(fake_transport) == [PRIMARY, PRIMARY, SECOND, SECOND, THIRD]
    assert harvard_elapsed == [4.25, 9.0]
    messages = [update.message for update in updates]
    assert "Strasbourg dropped the connection after 21 s. Trying the Harvard mirror…" in messages
    assert (
        "Harvard returned an error (HTTP 502) after 9 s. Trying the South Africa mirror…"
    ) in messages


@pytest.mark.anyio
async def test_raises_when_every_mirror_fails_and_keeps_installed_copy(
    fake_transport, tmp_path: Path
):
    vizier_dir = tmp_path / "vizier"
    vizier_dir.mkdir()
    installed = vizier_dir / "test.tsv"
    installed.write_bytes(b"previous install")
    version_json = vizier_dir / "version.json"
    version_json.write_text(
        json.dumps({"category": "vizier", "files": {"test.tsv": {"fetch_date": "2026-01-01"}}}),
        encoding="utf-8",
    )
    version_before = version_json.read_text(encoding="utf-8")

    fake_transport["handlers"][PRIMARY] = _raise(httpx.ConnectTimeout(""))
    fake_transport["handlers"][SECOND] = FakeResponse(status_code=503)
    fake_transport["handlers"][THIRD] = FakeResponse(body=_HTML_ERROR_PAGE)

    with pytest.raises(RuntimeError, match="All VizieR mirrors failed") as excinfo:
        await vizier.fetch_vizier_catalog(_spec(), tmp_path)

    message = str(excinfo.value)
    assert f"{PRIMARY} (ConnectTimeout)" in message
    assert f"{SECOND} (RuntimeError: HTTP 503)" in message
    assert f"{THIRD} (ValueError:" in message
    assert _hosts_called(fake_transport) == [PRIMARY, PRIMARY, SECOND, SECOND, THIRD]
    assert installed.read_bytes() == b"previous install"
    assert version_json.read_text(encoding="utf-8") == version_before
    assert not (vizier_dir / ".download").exists()


def test_mirrors_are_https_urls():
    urls = [vizier._build_url(_spec(), host) for host in vizier.VIZIER_HOSTS]
    assert urls[0].startswith("https://vizier.cds.unistra.fr/viz-bin/asu-tsv?")
    assert all(url.startswith("https://") for url in urls)
    assert len(set(vizier.VIZIER_HOSTS)) == len(vizier.VIZIER_HOSTS) == 3


@pytest.mark.anyio
async def test_requested_columns_must_be_present(fake_transport, tmp_path: Path):
    """A VizieR-shaped table without the ``-out.add`` columns is not this catalog."""
    spec = vizier.VizierFetchSpec(
        source_id="vizier_test",
        catalog_id="VII/20/catalog",
        output_filename="test.tsv",
        display_name="Test VizieR",
        citation="test",
        additional_params={"-out.add": "_RAJ2000,_DEJ2000"},
    )
    good = _vizier_body(["_RAJ2000", "_DEJ2000", "Sh2"])
    fake_transport["handlers"][PRIMARY] = FakeResponse(body=_vizier_body(["recno", "Sh2"]))
    fake_transport["handlers"][SECOND] = FakeResponse(body=good)

    result = await vizier.fetch_vizier_catalog(spec, tmp_path)

    assert _hosts_called(fake_transport) == [PRIMARY, SECOND]
    assert result.source_url.startswith(f"https://{SECOND}/")
    assert (tmp_path / "vizier" / "test.tsv").read_bytes() == good


def test_verify_accepts_a_real_vizier_layout(tmp_path: Path):
    """The header, units, hyphen and data rows of a real ``asu-tsv`` export pass."""
    path = tmp_path / "real.tsv"
    path.write_text(
        "#RESOURCE=yCat_7020\n#Title: Catalogue of HII Regions (Sharpless 1959)\n"
        "_RAJ2000\t_DEJ2000\trecno\tSh2\n"
        "deg\tdeg\t \t \n"
        "----------\t----------\t--------\t----\n"
        "239.713380\t-26.120461\t       1\t   1\n",
        encoding="utf-8",
    )
    vizier._verify_tsv_shape(path, ("_RAJ2000", "_DEJ2000"))
    with pytest.raises(ValueError, match="requested columns"):
        vizier._verify_tsv_shape(path, ("_RAJ2000", "Diam"))
