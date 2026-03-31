"""Compute backend abstraction.

All array operations in the codebase should call get_array_module() rather
than importing numpy or mlx directly. This allows GPU acceleration to be
toggled at runtime without touching business logic.

Current backends:
  - mlx   (Apple Metal — Apple Silicon only)
  - cupy  (NVIDIA CUDA — Windows/Linux)
  - numpy (CPU fallback, always available)
"""

import os
from typing import Any

import numpy as np

_mlx_available: bool | None = None
_cupy_available: bool | None = None

# GPU preference is read once at startup to avoid async in hot paths.
# Updated via set_gpu_enabled() when settings change.
_gpu_enabled: bool = True


def _check_mlx() -> bool:
    global _mlx_available
    if _mlx_available is None:
        try:
            import mlx.core  # noqa: F401

            _mlx_available = True
        except ImportError:
            _mlx_available = False
    return _mlx_available


def _check_cupy() -> bool:
    global _cupy_available
    if _cupy_available is None:
        try:
            import cupy  # noqa: F401

            _cupy_available = True
        except ImportError:
            _cupy_available = False
    return _cupy_available


def gpu_backend_name() -> str | None:
    """Return the name of the available GPU backend, or None if CPU-only."""
    if _check_mlx():
        return "mlx"
    if _check_cupy():
        return "cupy"
    return None


def set_gpu_enabled(enabled: bool) -> None:
    """Update the GPU acceleration preference (called when settings change)."""
    global _gpu_enabled
    _gpu_enabled = enabled


def get_array_module() -> Any:
    """Return the active array module (mlx.core, cupy, or numpy).

    Uses GPU backend when gpu_acceleration is enabled and a backend is available;
    falls back to numpy otherwise.
    """
    if _gpu_enabled:
        if _check_mlx():
            import mlx.core as mx

            return mx
        if _check_cupy():
            import cupy

            return cupy
    return np


def effective_worker_count(max_worker_cores: int | None = None) -> int:
    """Return the number of worker processes to use for CPU-bound tasks."""
    if max_worker_cores is not None:
        return max(1, max_worker_cores)
    return max(1, (os.cpu_count() or 2) - 1)
