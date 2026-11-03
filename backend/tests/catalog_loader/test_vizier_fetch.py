"""Tests for the VizieR TSV fetcher — one pass over the mirrors.

Parser-level assertions live in ``test_vizier_tsv.py``. This module focuses
on the HTTP layer: each mirror in ``VIZIER_HOSTS`` is tried once (the shared
HTTP client retries transient failures itself), a failing or malformed
response moves on to the next mirror, ``version.json`` records the mirror that
served the data, and full exhaustion raises ``RuntimeError`` without touching
the installed copy.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sqlite3
import stat
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from nightcrate.catalog_loader import load_catalogs, registry, vizier
from nightcrate.catalog_loader.catalog_choice import read_choice, with_added, write_choice
from nightcrate.catalog_loader.hash import file_sha256
from nightcrate.db.migrations import apply_migrations
from nightcrate.services import catalog_progress

_MIN_TSV_BODY = (
    "# VizieR metadata header\ncol_RA\tcol_DE\n--\t--\n------\t------\n" + "1.0\t2.0\n" * 200
).encode("utf-8")
assert len(_MIN_TSV_BODY) > 1024, "fixture must clear _MIN_BODY_BYTES"

# Over the 1 kB minimum, but with no tab-separated header.
_HTML_ERROR_PAGE = b"<html><body>" + b"Service temporarily unavailable. " * 64 + b"</body></html>"
assert len(_HTML_ERROR_PAGE) > 1024

# IDIA's real response when a catalog is unavailable there.
_TABLE_NOT_FOUND = (
    b"#\n"
    b"#   VizieR Astronomical Server vizier.idia.ac.za\n"
    b"#    Date: 2026-11-03T13:08:56 [V7.6.1]\n"
    b"#   In case of problem, please report to:\tcds-question@unistra.fr\n"
    b"#\n"
    b"#\n"
    b"#Coosys\tJ2000:\teq_FK5 J2000\n"
    b"#INFO\tservice_protocol=ASU\t  IVOID of the protocol through which the data was retrieved\n"
    b"#INFO\trequest_date=2026-11-03T13:08:56\t  Query execution date\n"
    b"#INFO\trequest=https://vizier.idia.ac.za/viz-bin/asu-tsv?"
    b"-source=V/163/pnmain&-out.max=3\t  Full request URL\n"
    b"#INFO\tcontact=cds-question@unistra.fr\t  Email or URL to contact publisher\n"
    b"#INFO\tserver_software=VizieR/7.6.1\t  Software version\n"
    b"#INFO\tpublisher=CDS\t  Data centre that produced the VOTable\n"
    b"#INFO\tError=Table or Catalog not found: V/163/pnmain\n"
    b"\n"
)
assert len(_TABLE_NOT_FOUND) == 688
_PADDED_TABLE_NOT_FOUND = _TABLE_NOT_FOUND + (
    b"#INFO	padding=not-found-response	  Extra comment line\n" * 8
)
assert len(_PADDED_TABLE_NOT_FOUND) > 1024

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


PRIMARY, SECOND, THIRD, FOURTH, FIFTH, SIXTH = vizier.VIZIER_HOSTS


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
                if f"://{host}/" in url:
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


def _host_from_url(url: str) -> str:
    return url.split("/")[2]


def _is_probe_url(url: str) -> bool:
    return "-source=VII/20/catalog&-out=Sh2,Diam&-out.max=1" in url


def _spec():
    return vizier.VizierFetchSpec(
        source_id="vizier_test",
        catalog_id="VII/20/catalog",
        output_filename="test.tsv",
        display_name="Test VizieR",
        citation="test",
    )


def _two_specs() -> tuple[vizier.VizierFetchSpec, ...]:
    return (
        vizier.VizierFetchSpec("vizier_multi_1", "X/1", "multi-1.tsv", "MCG table 1", "test"),
        vizier.VizierFetchSpec("vizier_multi_2", "X/2", "multi-2.tsv", "MCG table 2", "test"),
    )


def _register_multi(monkeypatch, specs) -> None:
    catalog = registry.OptionalCatalog(
        "mcg",
        "MCG",
        tuple(spec.source_id for spec in specs),
        "vizier",
        specs,
        frozenset({"mcg"}),
        False,
        "test",
    )
    monkeypatch.setattr(registry, "OPTIONAL_CATALOGS", (*registry.OPTIONAL_CATALOGS, catalog))


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
async def test_probe_starts_all_six_requests_before_any_completes(tmp_path: Path, monkeypatch):
    vizier.reset_mirror_health()
    arrived: list[str] = []
    release = asyncio.Event()
    probe_body = _vizier_body(["Sh2", "Diam"])

    async def get(url: str, **_kwargs):
        if _is_probe_url(url):
            arrived.append(_host_from_url(url))
            if len(arrived) == len(vizier.VIZIER_HOSTS):
                release.set()
            await release.wait()
            return SimpleNamespace(status_code=200, content=probe_body)
        return SimpleNamespace(status_code=200, content=_MIN_TSV_BODY)

    monkeypatch.setattr(vizier.http_client, "get", get)

    await vizier.fetch_vizier_catalog(_spec(), tmp_path)

    assert arrived == list(vizier.VIZIER_HOSTS)


@pytest.mark.anyio
async def test_probe_skips_down_hosts_and_downloads_from_first_up_host(tmp_path: Path, monkeypatch):
    vizier.reset_mirror_health()
    calls: list[str] = []
    probe_body = _vizier_body(["Sh2", "Diam"])
    down = {PRIMARY, SECOND, SIXTH}
    updates = []

    async def get(url: str, **kwargs):
        calls.append(url)
        if _is_probe_url(url):
            assert kwargs["attempts"] == 1
            assert kwargs["timeout"] == kwargs["connect_timeout"] == 10.0
            if _host_from_url(url) in down:
                return SimpleNamespace(status_code=503, content=b"")
            return SimpleNamespace(status_code=200, content=probe_body)
        return SimpleNamespace(status_code=200, content=_MIN_TSV_BODY)

    monkeypatch.setattr(vizier.http_client, "get", get)

    result = await vizier.fetch_vizier_catalog(_spec(), tmp_path, updates.append)

    download_hosts = [_host_from_url(url) for url in calls if not _is_probe_url(url)]
    assert download_hosts == [THIRD]
    assert result.source_url.startswith(f"https://{THIRD}/")
    assert updates[0].message == "Checking which VizieR mirrors are up…"
    assert "Strasbourg, Harvard and India are down. Trying the South Africa mirror…" in [
        update.message for update in updates
    ]


@pytest.mark.anyio
async def test_multitable_fetch_skips_host_marked_down_by_first_table(
    fake_transport, tmp_path: Path
):
    fake_transport["handlers"][PRIMARY] = _raise(httpx.ConnectError("offline"))
    fake_transport["handlers"][SECOND] = FakeResponse(body=_MIN_TSV_BODY)

    await vizier.fetch_vizier_tables(_two_specs(), tmp_path)

    assert _hosts_called(fake_transport) == [PRIMARY, PRIMARY, SECOND, SECOND]


@pytest.mark.anyio
async def test_probe_repeats_at_exact_boundary_not_before(tmp_path: Path, monkeypatch):
    now = 100.0
    monkeypatch.setattr(vizier, "_clock", lambda: now)
    vizier.reset_mirror_health()
    calls: list[str] = []
    probe_body = _vizier_body(["Sh2", "Diam"])

    async def get(url: str, **_kwargs):
        calls.append(url)
        body = probe_body if _is_probe_url(url) else _MIN_TSV_BODY
        return SimpleNamespace(status_code=200, content=body)

    monkeypatch.setattr(vizier.http_client, "get", get)
    await vizier.fetch_vizier_catalog(_spec(), tmp_path)
    assert sum(_is_probe_url(url) for url in calls) == len(vizier.VIZIER_HOSTS)

    now += 3599.9
    calls.clear()
    await vizier.fetch_vizier_catalog(_spec(), tmp_path)
    assert not any(_is_probe_url(url) for url in calls)

    now = 100.0 + vizier.MIRROR_DOWN_S
    calls.clear()
    await vizier.fetch_vizier_catalog(_spec(), tmp_path)
    assert sum(_is_probe_url(url) for url in calls) == len(vizier.VIZIER_HOSTS)


@pytest.mark.anyio
async def test_probe_repeats_mid_hour_when_every_host_is_marked_down(tmp_path: Path, monkeypatch):
    now = 100.0
    monkeypatch.setattr(vizier, "_clock", lambda: now)
    vizier.reset_mirror_health()
    calls: list[str] = []
    probe_body = _vizier_body(["Sh2", "Diam"])

    async def get(url: str, **_kwargs):
        calls.append(url)
        body = probe_body if _is_probe_url(url) else _MIN_TSV_BODY
        return SimpleNamespace(status_code=200, content=body)

    monkeypatch.setattr(vizier.http_client, "get", get)
    await vizier.fetch_vizier_catalog(_spec(), tmp_path)
    vizier._mirror_down_until.update(
        {host: now + vizier.MIRROR_DOWN_S for host in vizier.VIZIER_HOSTS}
    )
    calls.clear()

    await vizier.fetch_vizier_catalog(_spec(), tmp_path)

    assert sum(_is_probe_url(url) for url in calls) == len(vizier.VIZIER_HOSTS)
    assert vizier._mirror_down_until == {}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "primary_failure",
    [
        FakeResponse(body=_TABLE_NOT_FOUND),
        FakeResponse(body=_PADDED_TABLE_NOT_FOUND),
        FakeResponse(status_code=404),
        FakeResponse(body=_HTML_ERROR_PAGE),
        FakeResponse(body=b""),
        _raise(RuntimeError("boom")),
    ],
    ids=[
        "short-table-not-found",
        "invalid-table-not-found",
        "http-404",
        "html-error-page",
        "empty-body",
        "unexpected-exception",
    ],
)
async def test_non_host_failures_do_not_demote_mirror(
    fake_transport, tmp_path: Path, primary_failure
):
    fake_transport["handlers"][PRIMARY] = primary_failure
    fake_transport["handlers"][SECOND] = FakeResponse(body=_MIN_TSV_BODY)
    await vizier.fetch_vizier_catalog(_spec(), tmp_path)

    assert vizier._mirror_down_until == {}

    fake_transport["handlers"][PRIMARY] = FakeResponse(body=_MIN_TSV_BODY)
    fake_transport["calls"].clear()
    await vizier.fetch_vizier_catalog(_spec(), tmp_path)

    assert _hosts_called(fake_transport) == [PRIMARY]


@pytest.mark.anyio
async def test_probe_with_no_host_up_records_nothing_and_next_fetch_probes_again(
    tmp_path: Path, monkeypatch
):
    vizier.reset_mirror_health()
    calls: list[str] = []

    async def get(url: str, **_kwargs):
        calls.append(url)
        return SimpleNamespace(status_code=503, content=b"")

    monkeypatch.setattr(vizier.http_client, "get", get)

    for _ in range(2):
        with pytest.raises(vizier.NoVizierSource) as excinfo:
            await vizier.fetch_vizier_catalog(_spec(), tmp_path)
        assert excinfo.value.summary == (
            "no VizieR mirror answered; check your internet connection"
        )
        assert vizier._mirror_down_until == {}
        assert vizier._last_probe_at is None

    assert len(calls) == 2 * len(vizier.VIZIER_HOSTS)


@pytest.mark.anyio
async def test_progress_names_first_three_hosts(fake_transport, tmp_path: Path):
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
async def test_table_not_found_moves_on_without_duration_or_demotion(
    fake_transport, tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(vizier, "VIZIER_HOSTS", (THIRD, PRIMARY, SECOND))
    fake_transport["handlers"][THIRD] = FakeResponse(body=_TABLE_NOT_FOUND)
    fake_transport["handlers"][PRIMARY] = FakeResponse(body=_MIN_TSV_BODY)
    updates = []

    await vizier.fetch_vizier_catalog(_spec(), tmp_path, updates.append)

    messages = [update.message for update in updates]
    assert "South Africa doesn't have this table. Trying CDS Strasbourg…" in messages
    assert not any("doesn't have this table after" in message for message in messages)
    assert vizier._mirror_down_until == {}


@pytest.mark.anyio
async def test_exhausted_mirrors_have_plain_summary(fake_transport, tmp_path: Path):
    fake_transport["handlers"][PRIMARY] = _raise(httpx.ConnectTimeout(""))
    fake_transport["handlers"][SECOND] = FakeResponse(status_code=502)
    fake_transport["handlers"][THIRD] = FakeResponse(body=_TABLE_NOT_FOUND)
    fake_transport["handlers"][FOURTH] = FakeResponse(body=_TABLE_NOT_FOUND)
    fake_transport["handlers"][FIFTH] = FakeResponse(body=_TABLE_NOT_FOUND)
    fake_transport["handlers"][SIXTH] = _raise(httpx.ConnectTimeout(""))

    with pytest.raises(vizier.NoVizierSource) as excinfo:
        await vizier.fetch_vizier_catalog(_spec(), tmp_path)

    assert excinfo.value.summary == (
        "Strasbourg and India timed out, Harvard returned an error (HTTP 502) "
        "and South Africa, Tokyo and Beijing don't have this table"
    )


@pytest.mark.anyio
async def test_exhausted_mirrors_group_one_shared_reason(fake_transport, tmp_path: Path):
    for host in vizier.VIZIER_HOSTS:
        fake_transport["handlers"][host] = FakeResponse(body=_TABLE_NOT_FOUND)

    with pytest.raises(vizier.NoVizierSource) as excinfo:
        await vizier.fetch_vizier_catalog(_spec(), tmp_path)

    assert excinfo.value.summary == (
        "Strasbourg, Harvard, South Africa, Tokyo, Beijing and India don't have this table"
    )


@pytest.mark.anyio
async def test_exhausted_mirrors_include_hosts_skipped_as_down(fake_transport, tmp_path: Path):
    down = (PRIMARY, SECOND, SIXTH)
    vizier._mirror_down_until.update(
        {host: vizier._clock() + vizier.MIRROR_DOWN_S for host in down}
    )
    for host in (THIRD, FOURTH, FIFTH):
        fake_transport["handlers"][host] = FakeResponse(body=_TABLE_NOT_FOUND)

    with pytest.raises(vizier.NoVizierSource) as excinfo:
        await vizier.fetch_vizier_catalog(_spec(), tmp_path)

    assert excinfo.value.summary == (
        "Strasbourg, Harvard and India are down and South Africa, Tokyo and Beijing "
        "don't have this table"
    )


@pytest.mark.anyio
async def test_mid_download_5xx_marks_host_down_and_moves_on(fake_transport, tmp_path: Path):
    fake_transport["handlers"][PRIMARY] = FakeResponse(status_code=502)
    fake_transport["handlers"][SECOND] = FakeResponse(body=_MIN_TSV_BODY)

    result = await vizier.fetch_vizier_catalog(_spec(), tmp_path)

    assert _hosts_called(fake_transport) == [PRIMARY, PRIMARY, SECOND]
    assert PRIMARY in vizier._mirror_down_until
    assert result.source_url.startswith(f"https://{SECOND}/")


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
    fake_transport["handlers"][FOURTH] = FakeResponse(body=_HTML_ERROR_PAGE)
    fake_transport["handlers"][FIFTH] = FakeResponse(body=_HTML_ERROR_PAGE)
    fake_transport["handlers"][SIXTH] = FakeResponse(body=_HTML_ERROR_PAGE)

    with pytest.raises(RuntimeError, match="All VizieR mirrors failed") as excinfo:
        await vizier.fetch_vizier_catalog(_spec(), tmp_path)

    message = str(excinfo.value)
    assert f"{PRIMARY} (ConnectTimeout)" in message
    assert f"{SECOND} (RuntimeError: HTTP 503)" in message
    assert f"{THIRD} (ValueError:" in message
    assert _hosts_called(fake_transport) == [
        PRIMARY,
        PRIMARY,
        SECOND,
        SECOND,
        THIRD,
        FOURTH,
        FIFTH,
        SIXTH,
    ]
    assert installed.read_bytes() == b"previous install"
    assert version_json.read_text(encoding="utf-8") == version_before
    assert not (vizier_dir / ".download").exists()


def test_mirror_order_and_schemes_are_exact():
    assert [
        (host, vizier._build_url(_spec(), host).split(":", 1)[0]) for host in vizier.VIZIER_HOSTS
    ] == [
        ("vizier.cds.unistra.fr", "https"),
        ("vizier.cfa.harvard.edu", "https"),
        ("vizier.idia.ac.za", "https"),
        ("vizier.nao.ac.jp", "http"),
        ("vizier.china-vo.org", "http"),
        ("vizier.iucaa.in", "http"),
    ]
    assert vizier._probe_url(PRIMARY) == (
        "https://vizier.cds.unistra.fr/viz-bin/asu-tsv?"
        "-source=VII/20/catalog&-out=Sh2,Diam&-out.max=1"
    )


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


def test_verify_rejects_a_one_column_tsv_shape(tmp_path: Path):
    path = tmp_path / "one-column.tsv"
    path.write_text("Sh2\n \n----\n1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="no tab-separated header row"):
        vizier._verify_tsv_shape(path, ("Sh2",))


def test_atomic_json_write_preserves_existing_mode_and_uses_readable_default(tmp_path: Path):
    path = tmp_path / "version.json"

    vizier._atomic_write_json(path, {"category": "vizier", "files": {}})
    assert stat.S_IMODE(path.stat().st_mode) == 0o644

    path.chmod(0o640)
    vizier._atomic_write_json(path, {"category": "vizier", "files": {"test": {}}})
    assert stat.S_IMODE(path.stat().st_mode) == 0o640


@pytest.mark.anyio
async def test_two_table_download_failure_preserves_installed_set(
    fake_transport, tmp_path: Path, monkeypatch
):
    specs = _two_specs()
    _register_multi(monkeypatch, specs)
    vizier_dir = tmp_path / "vizier"
    vizier_dir.mkdir()
    old_files = {spec.output_filename: f"old-{spec.source_id}".encode() for spec in specs}
    for filename, content in old_files.items():
        (vizier_dir / filename).write_bytes(content)
    version_path = vizier_dir / "version.json"
    version_path.write_text('{"category":"vizier","files":{"old":{}}}\n')
    version_before = version_path.read_bytes()
    calls = 0

    def primary_response():
        nonlocal calls
        calls += 1
        return FakeResponse(body=_MIN_TSV_BODY if calls == 1 else _HTML_ERROR_PAGE)

    fake_transport["handlers"].update(
        {
            PRIMARY: primary_response,
            SECOND: FakeResponse(body=_HTML_ERROR_PAGE),
            THIRD: FakeResponse(body=_HTML_ERROR_PAGE),
            FOURTH: FakeResponse(body=_HTML_ERROR_PAGE),
            FIFTH: FakeResponse(body=_HTML_ERROR_PAGE),
            SIXTH: FakeResponse(body=_HTML_ERROR_PAGE),
        }
    )

    with pytest.raises(vizier.NoVizierSource):
        await vizier.fetch_vizier_tables(specs, tmp_path, catalog_id="mcg")

    assert {name: (vizier_dir / name).read_bytes() for name in old_files} == old_files
    assert version_path.read_bytes() == version_before
    assert not (vizier_dir / ".download").exists()
    assert not (vizier_dir / "publishing" / "mcg.json").exists()


@pytest.mark.anyio
async def test_two_table_download_failure_restart_is_unchanged(
    fake_transport, tmp_path: Path, monkeypatch
):
    root = tmp_path / "catalogs"
    fixtures = Path(__file__).parent.parent / "fixtures" / "catalogs"
    (root / "openngc").mkdir(parents=True)
    (root / "vizier").mkdir()
    shutil.copy(fixtures / "openngc" / "mini_NGC.csv", root / "openngc" / "NGC.csv")
    shutil.copy(fixtures / "openngc" / "mini_addendum.csv", root / "openngc" / "addendum.csv")
    specs = (
        vizier.VizierFetchSpec("vizier_sharpless", "X/1", "sharpless_VII_20.tsv", "MCG", "test"),
        vizier.VizierFetchSpec("vizier_barnard", "X/2", "barnard_VII_220.tsv", "MCG", "test"),
    )
    for spec, fixture in zip(specs, ("mini_sharpless.tsv", "mini_barnard.tsv"), strict=True):
        shutil.copy(fixtures / "vizier" / fixture, root / "vizier" / spec.output_filename)
    _register_multi(monkeypatch, specs)
    version = {
        "category": "vizier",
        "files": {
            spec.output_filename: {
                "sha256": file_sha256(root / "vizier" / spec.output_filename),
                "fetch_date": "2026-11-01T00:00:00+00:00",
            }
            for spec in specs
        },
    }
    (root / "vizier" / "version.json").write_text(json.dumps(version))
    db_path = tmp_path / "restart.db"
    apply_migrations(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        load_catalogs(conn, root)
        write_choice(root, with_added(read_choice(root), "mcg"))
        load_catalogs(conn, root)

    calls = 0

    def primary_response():
        nonlocal calls
        calls += 1
        return FakeResponse(body=_MIN_TSV_BODY if calls == 1 else _HTML_ERROR_PAGE)

    fake_transport["handlers"].update(
        {
            PRIMARY: primary_response,
            SECOND: FakeResponse(body=_HTML_ERROR_PAGE),
            THIRD: FakeResponse(body=_HTML_ERROR_PAGE),
            FOURTH: FakeResponse(body=_HTML_ERROR_PAGE),
            FIFTH: FakeResponse(body=_HTML_ERROR_PAGE),
            SIXTH: FakeResponse(body=_HTML_ERROR_PAGE),
        }
    )
    with pytest.raises(vizier.NoVizierSource):
        await vizier.fetch_vizier_tables(specs, root, catalog_id="mcg")

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        summary = load_catalogs(conn, root)
    statuses = {
        result.source_id: result.status
        for result in summary.results
        if result.source_id in {"vizier_sharpless", "vizier_barnard"}
    }
    assert statuses == {"vizier_sharpless": "unchanged", "vizier_barnard": "unchanged"}


@pytest.mark.anyio
@pytest.mark.parametrize("version_exists", [True, False], ids=["with-version", "no-version"])
async def test_publication_failure_leaves_catalog_marker(
    fake_transport, tmp_path: Path, monkeypatch, version_exists: bool
):
    specs = _two_specs()
    _register_multi(monkeypatch, specs)
    fake_transport["handlers"][PRIMARY] = FakeResponse(body=_MIN_TSV_BODY)
    vizier_dir = tmp_path / "vizier"
    vizier_dir.mkdir()
    for spec in specs:
        (vizier_dir / spec.output_filename).write_bytes(b"old")
    version_path = vizier_dir / "version.json"
    if version_exists:
        version_path.write_text('{"category":"vizier","files":{}}\n')
    real_replace = vizier.os.replace

    def fail_second_publish(source, destination):
        if Path(destination).name == specs[1].output_filename:
            raise OSError("injected publication failure")
        return real_replace(source, destination)

    monkeypatch.setattr(vizier.os, "replace", fail_second_publish)
    with pytest.raises(OSError, match="injected"):
        await vizier.fetch_vizier_tables(specs, tmp_path, catalog_id="mcg")

    marker = json.loads((vizier_dir / "publishing" / "mcg.json").read_text())
    assert marker["files"] == [spec.output_filename for spec in specs]
    assert registry.optional_catalog_install(registry.optional_catalog("mcg"), tmp_path) == (
        False,
        None,
    )
    assert version_path.exists() is version_exists

    monkeypatch.setattr(vizier.os, "replace", real_replace)
    await vizier.fetch_vizier_tables(specs, tmp_path, catalog_id="mcg")
    assert not (vizier_dir / "publishing" / "mcg.json").exists()
    assert registry.optional_catalog_install(registry.optional_catalog("mcg"), tmp_path)[0] is True


@pytest.mark.anyio
async def test_success_for_one_catalog_keeps_another_catalog_marker(fake_transport, tmp_path: Path):
    marker = tmp_path / "vizier" / "publishing" / "sharpless.json"
    marker.parent.mkdir(parents=True)
    marker.write_text('{"version":1,"catalog_id":"sharpless","files":["sharpless_VII_20.tsv"]}')
    fake_transport["handlers"][PRIMARY] = FakeResponse(
        body=_vizier_body(["_RAJ2000", "_DEJ2000", "Barnard"])
    )
    barnard = registry.optional_catalog("barnard")

    await vizier.fetch_vizier_tables(barnard.fetch_specs, tmp_path, catalog_id="barnard")

    assert marker.exists()
    assert not (marker.parent / "barnard.json").exists()


@pytest.mark.anyio
async def test_multitable_progress_names_the_part(fake_transport, tmp_path, monkeypatch):
    specs = _two_specs()
    _register_multi(monkeypatch, specs)
    fake_transport["handlers"][PRIMARY] = FakeResponse(body=_MIN_TSV_BODY)
    updates = []

    await vizier.fetch_vizier_tables(
        specs,
        tmp_path,
        updates.append,
        catalog_id="mcg",
    )

    messages = [update.message for update in updates]
    assert "Downloading MCG (part 2 of 2) from CDS Strasbourg…" in messages


@pytest.mark.anyio
async def test_shared_fetch_set_uses_requested_catalog_for_marker(
    fake_transport, tmp_path: Path, monkeypatch
):
    specs = _two_specs()
    shared_a = registry.OptionalCatalog(
        "shared_a",
        "Shared catalog A",
        tuple(spec.source_id for spec in specs),
        "vizier",
        specs,
        frozenset({"png"}),
        False,
        "test",
    )
    shared_b = registry.OptionalCatalog(
        "shared_b",
        "Shared catalog B",
        tuple(spec.source_id for spec in specs),
        "vizier",
        specs,
        frozenset({"abell_pn"}),
        False,
        "test",
    )
    monkeypatch.setattr(
        registry,
        "OPTIONAL_CATALOGS",
        (*registry.OPTIONAL_CATALOGS, shared_a, shared_b),
    )
    fake_transport["handlers"][PRIMARY] = FakeResponse(body=_MIN_TSV_BODY)
    (tmp_path / "vizier").mkdir()
    real_replace = vizier.os.replace

    def fail_second_publish(source, destination):
        if Path(destination).name == specs[1].output_filename:
            raise OSError("injected publication failure")
        return real_replace(source, destination)

    monkeypatch.setattr(vizier.os, "replace", fail_second_publish)
    with pytest.raises(OSError, match="injected"):
        await vizier.fetch_vizier_tables(specs, tmp_path, catalog_id="shared_b")

    publishing = tmp_path / "vizier" / "publishing"
    assert (publishing / "shared_b.json").exists()
    assert not (publishing / "shared_a.json").exists()


def test_explicit_required_columns_accept_wr_table15_shape(tmp_path: Path):
    path = tmp_path / "wr-table15.tsv"
    path.write_text(
        "#RESOURCE=yCat_3215\n"
        "recno\tWR\tName\tSpType\tvmag\n"
        " \t \t \t \tmag\n"
        "--------\t-----\t-----------------\t----------------\t-----\n"
        "1\t1\tHD 4004\tWN4b\t10.51\n",
        encoding="utf-8",
    )
    spec = vizier.VizierFetchSpec(
        "vizier_wr_photometry",
        "III/215/table15",
        "wr-table15.tsv",
        "Wolf-Rayet",
        "test",
        required_columns=("WR", "vmag", "SpType"),
    )

    vizier._verify_tsv_shape(path, vizier._required_columns(spec))
