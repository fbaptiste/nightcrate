"""Catalogue-only solving near a supplied sky position."""

from __future__ import annotations

import math
import threading
import time

from nightcrate.services.star_catalog.models import STAR_EPOCH
from nightcrate.services.star_catalog.siril import SirilCatalog

from .models import DetectedStars, SolveOutcome, SolverConfig
from .verify import solve_hinted


def search_near_catalog(
    detections: DetectedStars,
    catalog: SirilCatalog,
    *,
    ra: float,
    dec: float,
    pixel_scale_arcsec: float | None,
    deadline: float,
    cancel: threading.Event,
) -> SolveOutcome:
    """Run the prototype's measured hinted scale stages against Siril stars."""
    config = SolverConfig(max_solve_seconds=max(0.0, deadline - time.perf_counter()))
    maximum_scale = (
        max(pixel_scale_arcsec * 2.0 * 1.15, math.sqrt(0.2 * 30.0))
        if pixel_scale_arcsec is not None
        else math.sqrt(0.2 * 30.0)
    )
    diagonal_deg = maximum_scale * math.hypot(detections.width, detections.height) / 3600.0
    stars = catalog.query_cone(ra, dec, 2.0 + diagonal_deg / 2.0, epoch=STAR_EPOCH)
    return solve_hinted(
        detections,
        stars,
        hint_ra=ra,
        hint_dec=dec,
        hint_radius_deg=2.0,
        pixel_scale_arcsec=pixel_scale_arcsec,
        config=config,
        deadline=deadline,
        cancel=cancel,
    )
