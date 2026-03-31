"""Compute backend abstraction.

All array operations in the codebase should call get_array_module() rather
than importing numpy or mlx directly. This allows GPU acceleration to be
toggled at runtime without touching business logic.

Current backends:
  - mlx  (Apple Metal — Apple Silicon only)
  - numpy (CPU fallback, always available)
"""

from typing import Any

import numpy as np

from nightcrate.core.config import get_settings

_mlx_available: bool | None = None


def _check_mlx() -> bool:
    global _mlx_available
    if _mlx_available is None:
        try:
            import mlx.core  # noqa: F401

            _mlx_available = True
        except ImportError:
            _mlx_available = False
    return _mlx_available


def get_array_module() -> Any:
    """Return the active array module (mlx.core or numpy).

    Uses mlx when gpu_acceleration is enabled and mlx is available;
    falls back to numpy otherwise.
    """
    settings = get_settings()
    if settings.gpu_acceleration and _check_mlx():
        import mlx.core as mx

        return mx
    return np


def effective_worker_count() -> int:
    """Return the number of worker processes to use for CPU-bound tasks."""
    import os

    settings = get_settings()
    if settings.max_worker_cores is not None:
        return max(1, settings.max_worker_cores)
    return max(1, (os.cpu_count() or 2) - 1)
