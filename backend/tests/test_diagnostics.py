"""Tests for the activity console — request tracking middleware and endpoints."""

import time

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.api.diagnostics import _records
from nightcrate.main import app


@pytest.fixture(autouse=True)
def _clear_records():
    """Clear tracked records before each test."""
    _records.clear()
    yield
    _records.clear()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestRequestTracking:
    async def test_requests_are_recorded(self, client: AsyncClient):
        await client.get("/api/images/recent")
        assert len(_records) >= 1
        rec = _records[-1]
        assert rec.path == "/api/images/recent"
        assert rec.method == "GET"
        assert rec.status_code == 200

    async def test_timestamp_is_start_time(self, client: AsyncClient):
        """Timestamp should be captured before request processing, not after."""
        start = time.time()
        await client.get("/api/images/recent")
        rec = _records[-1]
        # Parse the ISO timestamp
        from datetime import datetime

        ts = datetime.fromisoformat(rec.timestamp)
        ts_epoch = ts.timestamp()
        # Start time should be very close to when we made the request
        assert abs(ts_epoch - start) < 1.0

    async def test_duration_is_positive(self, client: AsyncClient):
        await client.get("/api/images/recent")
        rec = _records[-1]
        assert rec.duration_ms > 0

    async def test_diagnostics_requests_are_skipped(self, client: AsyncClient):
        count_before = len(_records)
        await client.get("/api/diagnostics/activity")
        assert len(_records) == count_before  # no new record

    async def test_activity_from_header(self, client: AsyncClient):
        await client.get("/api/images/recent", headers={"X-Activity": "Test Activity"})
        rec = _records[-1]
        assert rec.activity == "Test Activity"

    async def test_activity_from_query_string(self, client: AsyncClient):
        await client.get("/api/images/recent?_activity=From+QS")
        rec = _records[-1]
        assert rec.activity == "From QS"


class TestActivityEndpoint:
    async def test_empty_activity(self, client: AsyncClient):
        resp = await client.get("/api/diagnostics/activity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["groups"] == []

    async def test_groups_by_activity(self, client: AsyncClient):
        await client.get("/api/images/recent", headers={"X-Activity": "Group A"})
        await client.get("/api/images/recent", headers={"X-Activity": "Group A"})
        await client.get("/api/images/recent", headers={"X-Activity": "Group B"})
        resp = await client.get("/api/diagnostics/activity")
        data = resp.json()
        assert len(data["groups"]) == 2
        assert data["groups"][0]["activity"] == "Group A"
        assert len(data["groups"][0]["requests"]) == 2
        assert data["groups"][1]["activity"] == "Group B"
        assert len(data["groups"][1]["requests"]) == 1

    async def test_clear_activity(self, client: AsyncClient):
        await client.get("/api/images/recent")
        assert len(_records) > 0
        resp = await client.delete("/api/diagnostics/activity")
        assert resp.status_code == 200
        assert len(_records) == 0
