from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

STAR_EPOCH = 2026.0


@dataclass(frozen=True)
class StarCatalog:
    ra: NDArray[np.float64]
    dec: NDArray[np.float64]
    g: NDArray[np.float32]

    def __post_init__(self) -> None:
        n = len(self.ra)
        if self.ra.shape != (n,) or self.dec.shape != (n,) or self.g.shape != (n,):
            raise ValueError("catalog columns must be one-dimensional and equally sized")

    def __len__(self) -> int:
        return len(self.ra)

    def take(self, indices: NDArray[np.integer[Any]]) -> StarCatalog:
        return StarCatalog(self.ra[indices], self.dec[indices], self.g[indices])
