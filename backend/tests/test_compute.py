"""Tests for the compute backend abstraction module."""

import os
from unittest.mock import patch

import numpy as np

import nightcrate.core.compute as compute_mod
from nightcrate.core.compute import (
    effective_worker_count,
    get_array_module,
    gpu_backend_name,
    set_gpu_enabled,
)

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
