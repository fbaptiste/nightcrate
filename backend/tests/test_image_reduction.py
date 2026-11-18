from __future__ import annotations

import math

import numpy as np

from nightcrate.services.catalog_thumbnail import _area_reduce, _decimate_step
from nightcrate.services.project_images import _downsample


def _legacy_reduce(data: np.ndarray, step: int) -> np.ndarray:
    if step <= 1:
        return data
    height, width = data.shape[-2:]
    y_starts = np.arange(0, height, step)
    x_starts = np.arange(0, width, step)
    y_counts = np.minimum(step, height - y_starts)
    x_counts = np.minimum(step, width - x_starts)
    reduced = np.add.reduceat(data.astype(np.float32), y_starts, axis=-2)
    reduced = np.add.reduceat(reduced, x_starts, axis=-1)
    return reduced / (y_counts[:, None] * x_counts[None, :])


def test_shared_area_reduction_preserves_both_callers_bytes():
    data = np.arange(3 * 17 * 23, dtype=np.uint16).reshape(3, 17, 23)

    catalog_step = _decimate_step(23, 3)
    assert (
        _area_reduce(data, 3).tobytes()
        == np.ascontiguousarray(_legacy_reduce(data, catalog_step)).tobytes()
    )

    project_step = max(1, math.ceil(23 / 7))
    assert _downsample(data, 7).tobytes() == _legacy_reduce(data, project_step).tobytes()
