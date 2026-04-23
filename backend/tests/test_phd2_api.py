"""Tests for PHD2 guide-log API endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.api.phd2 import _cache, _key_locks
from nightcrate.main import app

FIXTURES = Path(__file__).parent / "fixtures" / "phd2"
SAMPLE = FIXTURES / "sample_asiair.txt"
DEBUG_LOG = FIXTURES / "debug_log_rejected.txt"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    # Drop cache entries between tests — tests mutate the same process cache.
    _cache.clear()
    _key_locks.clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


class TestParseEndpoint:
    async def test_parse_real_sample_returns_sections_and_metrics(self, client: AsyncClient):
        resp = await client.post("/api/phd2/parse", json={"path": str(SAMPLE)})
        assert resp.status_code == 200
        data = resp.json()
        assert "log" in data
        assert "sections" in data
        # Trimmed sample has one calibration + one guiding section.
        assert len(data["sections"]) == 2
        guiding_section = data["sections"][1]
        assert guiding_section["section"]["kind"] == "guiding"
        assert guiding_section["metrics"]["rms_total_px"] is not None
        assert guiding_section["metrics"]["arcsec_scale"] == 3.96

    async def test_parse_reports_log_version_and_blank_app_version(self, client: AsyncClient):
        resp = await client.post("/api/phd2/parse", json={"path": str(SAMPLE)})
        data = resp.json()
        assert data["log"]["log_version"] == "2.5"
        # ASIAIR-bundled — app version blank.
        assert data["log"]["phd2_version"] is None

    async def test_parse_404_on_missing_file(self, client: AsyncClient):
        resp = await client.post("/api/phd2/parse", json={"path": "/nonexistent/path.txt"})
        assert resp.status_code == 404
        assert "File not found" in resp.json()["detail"]

    async def test_parse_400_on_directory(self, client: AsyncClient, tmp_path: Path):
        resp = await client.post("/api/phd2/parse", json={"path": str(tmp_path)})
        assert resp.status_code == 400
        assert "Not a file" in resp.json()["detail"]

    async def test_parse_422_on_debug_log(self, client: AsyncClient):
        resp = await client.post("/api/phd2/parse", json={"path": str(DEBUG_LOG)})
        assert resp.status_code == 422
        assert "Debug logs are not supported" in resp.json()["detail"]

    async def test_parse_422_on_non_phd2_file(self, client: AsyncClient, tmp_path: Path):
        bogus = tmp_path / "bogus.txt"
        bogus.write_text("not a phd2 log at all\n")
        resp = await client.post("/api/phd2/parse", json={"path": str(bogus)})
        assert resp.status_code == 422


class TestCache:
    async def test_cache_hit_on_second_call(self, client: AsyncClient):
        """The second request for the same path must be served from cache."""
        r1 = await client.post("/api/phd2/parse", json={"path": str(SAMPLE)})
        assert r1.status_code == 200

        stats1 = await client.get("/api/phd2/cache/stats")
        assert stats1.json()["entries"] == 1

        r2 = await client.post("/api/phd2/parse", json={"path": str(SAMPLE)})
        assert r2.status_code == 200
        # Still 1 entry — the same cache slot was reused, not duplicated.
        stats2 = await client.get("/api/phd2/cache/stats")
        assert stats2.json()["entries"] == 1

    async def test_cache_clear_empties_cache(self, client: AsyncClient):
        await client.post("/api/phd2/parse", json={"path": str(SAMPLE)})
        clear = await client.post("/api/phd2/cache/clear")
        assert clear.status_code == 200
        assert clear.json()["cleared"] == 1

        stats = await client.get("/api/phd2/cache/stats")
        assert stats.json()["entries"] == 0

    async def test_cache_stats_shape(self, client: AsyncClient):
        resp = await client.get("/api/phd2/cache/stats")
        data = resp.json()
        assert "entries" in data
        assert "max_entries" in data
        assert "ttl_seconds" in data
        assert data["max_entries"] >= 1


class TestValidation:
    async def test_parse_requires_path(self, client: AsyncClient):
        resp = await client.post("/api/phd2/parse", json={})
        assert resp.status_code == 422  # Pydantic validation error

    async def test_parse_rejects_extra_fields(self, client: AsyncClient):
        resp = await client.post(
            "/api/phd2/parse",
            json={"path": str(SAMPLE), "bogus_extra_field": "ignored"},
        )
        # Pydantic `extra="forbid"` rejects unknown keys.
        assert resp.status_code == 422
