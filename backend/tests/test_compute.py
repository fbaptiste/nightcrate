"""Tests for the compute backend abstraction module."""

import builtins
import logging
import os
from unittest.mock import patch

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

import nightcrate.core.compute as compute_mod
from nightcrate.core.compute import (
    effective_worker_count,
    get_array_module,
    gpu_backend_name,
    set_gpu_enabled,
)
from nightcrate.main import app

# ---------------------------------------------------------------------------
# GPU toggle
# ---------------------------------------------------------------------------


class TestGpuToggle:
    def test_set_gpu_enabled_toggle(self):
        """set_gpu_enabled should update the internal _gpu_enabled flag."""
        original = compute_mod._gpu_enabled
        try:
            set_gpu_enabled(False)
            assert compute_mod._gpu_enabled is False
            set_gpu_enabled(True)
            assert compute_mod._gpu_enabled is True
        finally:
            set_gpu_enabled(original)

    def test_disable_gpu_forces_numpy(self):
        """When GPU is disabled, get_array_module should return numpy."""
        original = compute_mod._gpu_enabled
        try:
            set_gpu_enabled(False)
            mod = get_array_module()
            assert mod is np
        finally:
            set_gpu_enabled(original)

    def test_enable_gpu_returns_module(self):
        """When GPU is enabled, get_array_module returns some array module (numpy on CI)."""
        original = compute_mod._gpu_enabled
        try:
            set_gpu_enabled(True)
            mod = get_array_module()
            # Should be numpy, mlx.core, or cupy — all have 'array' attribute
            assert hasattr(mod, "array") or hasattr(mod, "zeros")
        finally:
            set_gpu_enabled(original)


# ---------------------------------------------------------------------------
# gpu_backend_name
# ---------------------------------------------------------------------------


class TestGpuBackendName:
    def test_returns_string_or_none(self):
        """gpu_backend_name should return 'mlx', 'cupy', or None."""
        result = gpu_backend_name()
        assert result in ("mlx", "cupy", None)

    def test_no_gpu_available(self):
        """When neither mlx nor cupy is available, should return None."""
        saved_mlx = compute_mod._mlx_available
        saved_cupy = compute_mod._cupy_available
        try:
            compute_mod._mlx_available = False
            compute_mod._cupy_available = False
            assert gpu_backend_name() is None
        finally:
            compute_mod._mlx_available = saved_mlx
            compute_mod._cupy_available = saved_cupy

    def test_mlx_backend(self):
        """When mlx is available, backend name should be 'mlx'."""
        saved_mlx = compute_mod._mlx_available
        try:
            compute_mod._mlx_available = True
            assert gpu_backend_name() == "mlx"
        finally:
            compute_mod._mlx_available = saved_mlx

    def test_cupy_backend_when_no_mlx(self):
        """When only cupy is available, backend name should be 'cupy'."""
        saved_mlx = compute_mod._mlx_available
        saved_cupy = compute_mod._cupy_available
        try:
            compute_mod._mlx_available = False
            compute_mod._cupy_available = True
            assert gpu_backend_name() == "cupy"
        finally:
            compute_mod._mlx_available = saved_mlx
            compute_mod._cupy_available = saved_cupy


# ---------------------------------------------------------------------------
# get_array_module — CPU fallback
# ---------------------------------------------------------------------------


class TestGetArrayModule:
    def test_cpu_fallback_no_gpu(self):
        """With no GPU backend, get_array_module returns numpy."""
        saved_mlx = compute_mod._mlx_available
        saved_cupy = compute_mod._cupy_available
        original_gpu = compute_mod._gpu_enabled
        try:
            compute_mod._mlx_available = False
            compute_mod._cupy_available = False
            set_gpu_enabled(True)
            assert get_array_module() is np
        finally:
            compute_mod._mlx_available = saved_mlx
            compute_mod._cupy_available = saved_cupy
            set_gpu_enabled(original_gpu)

    def test_gpu_disabled_always_numpy(self):
        """With GPU disabled, always returns numpy regardless of availability."""
        saved_mlx = compute_mod._mlx_available
        original_gpu = compute_mod._gpu_enabled
        try:
            compute_mod._mlx_available = True
            set_gpu_enabled(False)
            assert get_array_module() is np
        finally:
            compute_mod._mlx_available = saved_mlx
            set_gpu_enabled(original_gpu)


# ---------------------------------------------------------------------------
# effective_worker_count
# ---------------------------------------------------------------------------


class TestEffectiveWorkerCount:
    def test_default_uses_cpu_count(self):
        """Default should be cpu_count - 1, minimum 1."""
        count = effective_worker_count()
        cpu = os.cpu_count() or 2
        assert count == max(1, cpu - 1)

    def test_explicit_override(self):
        """Explicit max_worker_cores should be honored."""
        assert effective_worker_count(4) == 4
        assert effective_worker_count(1) == 1

    def test_zero_clamped_to_one(self):
        """Zero workers should be clamped to 1."""
        assert effective_worker_count(0) == 1

    def test_negative_clamped_to_one(self):
        """Negative value should be clamped to 1."""
        assert effective_worker_count(-5) == 1

    def test_cpu_count_none_fallback(self):
        """When os.cpu_count() returns None, should fall back to 1."""
        with patch("os.cpu_count", return_value=None):
            count = effective_worker_count()
            assert count == 1


# ---------------------------------------------------------------------------
# Probe failure handling
# ---------------------------------------------------------------------------


def _raising_import(prefix: str, exc: Exception):
    """Return an __import__ replacement that raises for one module prefix."""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == prefix or name.startswith(prefix + "."):
            raise exc
        return real_import(name, *args, **kwargs)

    return fake_import


class TestProbeFailureHandling:
    """An installed-but-unusable GPU library must degrade to numpy, not crash.

    mlx raising something other than ImportError is the realistic case: the
    wheel imports fine but Metal initialisation fails. Before this was handled
    the exception escaped through an image render.
    """

    def test_mlx_runtime_failure_falls_back_to_numpy(self, caplog):
        saved_mlx = compute_mod._mlx_available
        saved_cupy = compute_mod._cupy_available
        original_gpu = compute_mod._gpu_enabled
        try:
            compute_mod._mlx_available = None  # force a fresh probe
            compute_mod._cupy_available = False
            set_gpu_enabled(True)
            boom = RuntimeError("Metal device not found")
            with caplog.at_level(logging.WARNING, logger="nightcrate.core.compute"):
                with patch("builtins.__import__", _raising_import("mlx", boom)):
                    assert get_array_module() is np
            assert compute_mod._mlx_available is False
            assert "[compute]" in caplog.text
            assert "mlx" in caplog.text
        finally:
            compute_mod._mlx_available = saved_mlx
            compute_mod._cupy_available = saved_cupy
            set_gpu_enabled(original_gpu)

    def test_cupy_runtime_failure_falls_back_to_numpy(self, caplog):
        saved_mlx = compute_mod._mlx_available
        saved_cupy = compute_mod._cupy_available
        original_gpu = compute_mod._gpu_enabled
        try:
            compute_mod._mlx_available = False
            compute_mod._cupy_available = None  # force a fresh probe
            set_gpu_enabled(True)
            boom = RuntimeError("CUDA driver version is insufficient")
            with caplog.at_level(logging.WARNING, logger="nightcrate.core.compute"):
                with patch("builtins.__import__", _raising_import("cupy", boom)):
                    assert get_array_module() is np
            assert compute_mod._cupy_available is False
            assert "[compute]" in caplog.text
        finally:
            compute_mod._mlx_available = saved_mlx
            compute_mod._cupy_available = saved_cupy
            set_gpu_enabled(original_gpu)

    def test_missing_library_is_not_logged_as_a_warning(self, caplog):
        """A plain ImportError is the normal Intel/Linux case, not a problem."""
        saved_mlx = compute_mod._mlx_available
        try:
            compute_mod._mlx_available = None
            with caplog.at_level(logging.WARNING, logger="nightcrate.core.compute"):
                with patch("builtins.__import__", _raising_import("mlx", ImportError("no mlx"))):
                    assert compute_mod._check_mlx() is False
            assert caplog.text == ""
        finally:
            compute_mod._mlx_available = saved_mlx


# ---------------------------------------------------------------------------
# GET /api/settings/compute
# ---------------------------------------------------------------------------


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


class TestComputeInfoEndpoint:
    async def test_reports_current_backend(self, client):
        resp = await client.get("/api/settings/compute")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body) == {"gpu_backend"}
        assert body["gpu_backend"] == gpu_backend_name()

    async def test_reports_none_when_cpu_only(self, client):
        saved_mlx = compute_mod._mlx_available
        saved_cupy = compute_mod._cupy_available
        try:
            compute_mod._mlx_available = False
            compute_mod._cupy_available = False
            resp = await client.get("/api/settings/compute")
            assert resp.status_code == 200
            assert resp.json()["gpu_backend"] is None
        finally:
            compute_mod._mlx_available = saved_mlx
            compute_mod._cupy_available = saved_cupy

    async def test_ignores_the_user_toggle(self, client):
        """The endpoint reports availability, not the preference."""
        saved_mlx = compute_mod._mlx_available
        original_gpu = compute_mod._gpu_enabled
        try:
            compute_mod._mlx_available = True
            set_gpu_enabled(False)
            resp = await client.get("/api/settings/compute")
            assert resp.json()["gpu_backend"] == "mlx"
        finally:
            compute_mod._mlx_available = saved_mlx
            set_gpu_enabled(original_gpu)
