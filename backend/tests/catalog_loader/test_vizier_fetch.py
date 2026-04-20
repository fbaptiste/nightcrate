"""Tests for the VizieR TSV fetcher — retry + mirror-fallback behaviour.

Parser-level assertions live in ``test_vizier_tsv.py``. This module focuses
on the HTTP layer: retry exhaustion on a single host rotates to the next
mirror in ``VIZIER_HOSTS``, and full exhaustion raises ``RuntimeError``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nightcrate.catalog_loader import vizier

_MIN_TSV_BODY = (
    "# VizieR metadata header\ncol_RA\tcol_DE\n--\t--\n------\t------\n" + "1.0\t2.0\n" * 200
).encode("utf-8")
assert len(_MIN_TSV_BODY) > 1024, "fixture must clear _MIN_BODY_BYTES"


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
    handlers: dict[str, object] = {}

    async def fake_get(url, *args, **kwargs):
        calls.append(url)
        for prefix, handler in handlers.items():
            if url.startswith(prefix):
                if callable(handler):
                    return handler()
                return handler
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr("nightcrate.catalog_loader.vizier.http_client.get", fake_get)

    async def _noop_sleep(_):
        return None

    monkeypatch.setattr("nightcrate.catalog_loader._common.asyncio.sleep", _noop_sleep)
    return {"handlers": handlers, "calls": calls}


def _spec():
    return vizier.VizierFetchSpec(
        source_id="vizier_test",
        catalog_id="VII/20/catalog",
        output_filename="test.tsv",
        display_name="Test VizieR",
        citation="test",
    )


@pytest.mark.anyio
async def test_falls_back_to_second_mirror_on_first_host_failure(fake_transport, tmp_path: Path):
    """When the primary host exhausts its 3 retries, the fetcher must
    rotate to the next mirror in ``VIZIER_HOSTS``."""

    def _primary_fails():
        raise RuntimeError("primary down")

    fake_transport["handlers"][f"https://{vizier.VIZIER_HOSTS[0]}"] = _primary_fails
    fake_transport["handlers"][f"https://{vizier.VIZIER_HOSTS[1]}"] = FakeResponse(
        body=_MIN_TSV_BODY,
    )

    await vizier.fetch_vizier_catalog(_spec(), tmp_path)

    # 3 failed attempts on the primary + 1 successful on the second mirror
    primary_calls = [c for c in fake_transport["calls"] if vizier.VIZIER_HOSTS[0] in c]
    mirror_calls = [c for c in fake_transport["calls"] if vizier.VIZIER_HOSTS[1] in c]
    assert len(primary_calls) == 3
    assert len(mirror_calls) == 1
    assert (tmp_path / "vizier" / "test.tsv").exists()


@pytest.mark.anyio
async def test_raises_when_every_mirror_fails(fake_transport, tmp_path: Path):
    def _always_down():
        raise RuntimeError("all down")

    for host in vizier.VIZIER_HOSTS:
        fake_transport["handlers"][f"https://{host}"] = _always_down

    with pytest.raises(RuntimeError, match="All VizieR mirrors failed"):
        await vizier.fetch_vizier_catalog(_spec(), tmp_path)

    # 3 retries per mirror × 3 mirrors = 9 total calls
    assert len(fake_transport["calls"]) == 3 * len(vizier.VIZIER_HOSTS)


@pytest.mark.anyio
async def test_short_body_triggers_retry_then_fallback(fake_transport, tmp_path: Path):
    """Truncated responses (<1 kB) should be treated as failures — those
    typically mean an HTML error page slipped through with HTTP 200."""
    fake_transport["handlers"][f"https://{vizier.VIZIER_HOSTS[0]}"] = FakeResponse(body=b"nope")
    fake_transport["handlers"][f"https://{vizier.VIZIER_HOSTS[1]}"] = FakeResponse(
        body=_MIN_TSV_BODY,
    )

    await vizier.fetch_vizier_catalog(_spec(), tmp_path)

    primary_calls = [c for c in fake_transport["calls"] if vizier.VIZIER_HOSTS[0] in c]
    assert len(primary_calls) == 3
