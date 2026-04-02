"""Tests for the histogram and pixel endpoints, and new stats fields."""

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.main import app
from nightcrate.services.imaging import (
    _channel_stats,
    _compute_lab_a_median,
    compute_image_stats,
)

# ── Unit tests for new stats fields ──────────────────────────────────────────


class TestChannelStatsSNR:
    def test_snr_positive(self):
        rng = np.random.default_rng(42)
        plane = rng.uniform(0.01, 0.05, size=(100, 100))
        stats = _channel_stats(plane)
        assert stats.snr > 0

    def test_snr_zero_when_no_noise(self):
        plane = np.full((50, 50), 0.5)
        stats = _channel_stats(plane)
        # MAD is 0 for uniform data → sigma is 0 → SNR is 0
        assert stats.snr == 0.0

    def test_avg_dev_computed(self):
        rng = np.random.default_rng(7)
        plane = rng.uniform(0.0, 1.0, size=(100, 100))
        stats = _channel_stats(plane)
        assert stats.avg_dev > 0
        # avgDev should be close to but not equal to MAD
        assert stats.avg_dev != stats.mad


class TestBackgroundDelta:
    def test_color_has_delta(self):
        rng = np.random.default_rng(42)
        data = rng.uniform(0.01, 0.05, size=(3, 50, 50))
        data[0] += 0.01  # make R brighter
        stats = compute_image_stats(data)
        assert stats.background_delta is not None
        assert len(stats.background_delta) == 3
        # R should have positive delta (brighter than mean)
        assert stats.background_delta[0] > 0

    def test_mono_has_no_delta(self):
        data = np.random.default_rng(42).uniform(0.0, 1.0, size=(50, 50))
        stats = compute_image_stats(data)
        assert stats.background_delta is None

    def test_equal_channels_zero_delta(self):
        data = np.full((3, 50, 50), 0.5)
        stats = compute_image_stats(data)
        for d in stats.background_delta:
            assert abs(d) < 1e-10


class TestLabAMedian:
    def test_neutral_gray(self):
        # Equal R=G=B should give a* near 0
        data = np.full((3, 50, 50), 0.5)
        a_star = _compute_lab_a_median(data)
        assert abs(a_star) < 0.01

    def test_red_gives_positive(self):
        data = np.zeros((3, 50, 50))
        data[0] = 0.5  # R only
        a_star = _compute_lab_a_median(data)
        assert a_star > 0

    def test_green_gives_negative(self):
        data = np.zeros((3, 50, 50))
        data[1] = 0.5  # G only
        a_star = _compute_lab_a_median(data)
        assert a_star < 0

    def test_color_stats_include_lab_a(self):
        rng = np.random.default_rng(42)
        data = rng.uniform(0.01, 0.05, size=(3, 50, 50))
        stats = compute_image_stats(data)
        assert stats.lab_a_median is not None

    def test_mono_has_no_lab_a(self):
        data = np.random.default_rng(42).uniform(0.0, 1.0, size=(50, 50))
        stats = compute_image_stats(data)
        assert stats.lab_a_median is None


# ── Histogram endpoint tests ─────────────────────────────────────────────────


@pytest.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


class TestHistogramEndpoint:
    async def test_mono_histogram(self, async_client, tmp_fits_mono):
        resp = await async_client.get(
            "/api/images/histogram", params={"path": str(tmp_fits_mono), "hdu": 0}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["color"] is False
        assert len(data["channels"]) == 1
        assert data["channels"][0]["name"] == "L"
        assert len(data["channels"][0]["bins"]) == 256
        assert data["luminosity"] is None
        assert len(data["bin_edges"]) == 257

    async def test_color_histogram(self, async_client, tmp_fits_color):
        resp = await async_client.get(
            "/api/images/histogram", params={"path": str(tmp_fits_color), "hdu": 0}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["color"] is True
        assert len(data["channels"]) == 3
        assert [ch["name"] for ch in data["channels"]] == ["R", "G", "B"]
        assert data["luminosity"] is not None
        assert len(data["luminosity"]) == 256

    async def test_bins_sum_to_pixel_count(self, async_client, tmp_fits_mono):
        resp = await async_client.get(
            "/api/images/histogram", params={"path": str(tmp_fits_mono), "hdu": 0}
        )
        data = resp.json()
        total = sum(data["channels"][0]["bins"])
        # mono_test.fits is 100x120 = 12000 pixels
        assert total == 12000

    async def test_custom_bins(self, async_client, tmp_fits_mono):
        resp = await async_client.get(
            "/api/images/histogram", params={"path": str(tmp_fits_mono), "hdu": 0, "bins": 64}
        )
        data = resp.json()
        assert len(data["channels"][0]["bins"]) == 64
        assert len(data["bin_edges"]) == 65

    async def test_bin_edges_monotonic(self, async_client, tmp_fits_mono):
        resp = await async_client.get(
            "/api/images/histogram", params={"path": str(tmp_fits_mono), "hdu": 0}
        )
        edges = resp.json()["bin_edges"]
        for i in range(1, len(edges)):
            assert edges[i] > edges[i - 1]


class TestPixelEndpoint:
    async def test_mono_pixel(self, async_client, tmp_fits_mono):
        resp = await async_client.get(
            "/api/images/pixel", params={"path": str(tmp_fits_mono), "hdu": 0, "x": 0, "y": 0}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["color"] is False
        assert "K" in data
        assert data["x"] == 0
        assert data["y"] == 0

    async def test_color_pixel(self, async_client, tmp_fits_color):
        resp = await async_client.get(
            "/api/images/pixel", params={"path": str(tmp_fits_color), "hdu": 0, "x": 50, "y": 40}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["color"] is True
        assert all(k in data for k in ["R", "G", "B", "K"])

    async def test_out_of_bounds(self, async_client, tmp_fits_mono):
        resp = await async_client.get(
            "/api/images/pixel", params={"path": str(tmp_fits_mono), "hdu": 0, "x": 9999, "y": 0}
        )
        assert resp.status_code == 400


class TestStatsEndpointNewFields:
    async def test_stats_include_snr_and_avgdev(self, async_client, tmp_fits_mono):
        resp = await async_client.get(
            "/api/images/stats", params={"path": str(tmp_fits_mono), "hdu": 0}
        )
        assert resp.status_code == 200
        data = resp.json()
        ch = data["channels"][0]
        assert "snr" in ch
        assert "avg_dev" in ch
        assert ch["snr"] >= 0
        assert ch["avg_dev"] > 0

    async def test_color_stats_include_delta_and_lab(self, async_client, tmp_fits_color):
        resp = await async_client.get(
            "/api/images/stats", params={"path": str(tmp_fits_color), "hdu": 0}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["background_delta"] is not None
        assert len(data["background_delta"]) == 3
        assert data["lab_a_median"] is not None
