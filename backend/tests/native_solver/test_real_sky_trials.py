"""Slow, opt-in trials against the installed Siril catalog and real indexes."""

from __future__ import annotations

import json
import math
import os
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from astropy.wcs import WCS

from nightcrate.services.native_solver.geometry import world_to_pixel
from nightcrate.services.native_solver.index_search import search_index
from nightcrate.services.native_solver.models import DetectedStars, TanWCS
from nightcrate.services.star_catalog.index import IndexLayer
from nightcrate.services.star_catalog.ranges import LAYERS
from nightcrate.services.star_catalog.siril import SirilCatalog
from nightcrate.services.star_catalog.store import SIRIL_SOURCE
from tests.native_solver.synthetic import make_wcs

SEED = 20261029
WIDTH = 1600
HEIGHT = 1200
NEGATIVE_COUNT = 1_000
REPORTING_BANDS = (
    ("0.2-0.4", 0.2, 0.4),
    ("0.4-0.8", 0.4, 0.8),
    ("0.8-1.6", 0.8, 1.6),
    ("1.6-3.2", 1.6, 3.2),
    ("3.2-6.4", 3.2, 6.4),
    ("6.4-10", 6.4, 10.0),
)


def _configured_star_data() -> Path | None:
    value = os.environ.get("NIGHTCRATE_STAR_DATA")
    if not value:
        return None
    root = Path(value)
    catalog = root / f"siril-astro-gaia-dr3-{SIRIL_SOURCE.version}" / SIRIL_SOURCE.uncompressed_name
    if not catalog.is_file() or not (root / "indexes" / "ranges.json").is_file():
        return None
    if any(not (root / "indexes" / f"{name}.ncidx").is_file() for name in LAYERS):
        return None
    return root


STAR_DATA = _configured_star_data()
pytestmark = pytest.mark.skipif(
    STAR_DATA is None,
    reason="NIGHTCRATE_STAR_DATA does not point at an installed catalog with all layers",
)


def _declination_band(dec: float) -> str:
    if dec < -30.0:
        return "-90..-30"
    if dec < 30.0:
        return "-30..30"
    return "30..90"


def _field_width(rng: np.random.Generator, trial: int) -> tuple[str, float]:
    range_id, min_deg, max_deg = REPORTING_BANDS[trial % len(REPORTING_BANDS)]
    low = math.log(min_deg)
    high = math.log(max_deg)
    return range_id, float(math.exp(rng.uniform(low, high)))


def _real_sky_case(source: SirilCatalog, rng: np.random.Generator, trial: int) -> dict[str, Any]:
    range_id, field_width = _field_width(rng, trial)
    ra = float(rng.uniform(0.0, 360.0))
    dec = float(np.degrees(np.arcsin(rng.uniform(-1.0, 1.0))))
    truth = make_wcs(
        ra,
        dec,
        WIDTH,
        HEIGHT,
        field_width * 3600.0 / max(WIDTH, HEIGHT),
        float(rng.uniform(0.0, 360.0)),
        int(rng.choice((-1, 1))),
    )
    radius = 0.6 * math.hypot(WIDTH, HEIGHT) * truth.scale_arcsec / 3600.0
    catalog = source.query_cone(ra, dec, radius, epoch=2026.0)
    predicted, valid = world_to_pixel(truth, catalog.ra, catalog.dec)
    inside = (
        valid
        & (predicted[:, 0] >= 10)
        & (predicted[:, 0] < WIDTH - 10)
        & (predicted[:, 1] >= 10)
        & (predicted[:, 1] < HEIGHT - 10)
    )
    indices = np.flatnonzero(inside)
    if len(indices) > 180:
        indices = indices[np.argsort(catalog.g[indices], kind="stable")[:180]]

    # The calibrated generator drops 15–35% of catalog stars and applies a
    # measured 0.25-mag brightness scatter.  Spurious detections draw from the
    # surviving real-star flux range rather than an unrelated distribution.
    if len(indices):
        keep = rng.random(len(indices)) >= rng.uniform(0.15, 0.35)
        indices = indices[keep]
    xy = predicted[indices].copy()
    if len(xy):
        xy += rng.normal(0.0, 0.12, xy.shape)
    flux = 10 ** (-0.4 * catalog.g[indices].astype(np.float64))
    flux *= 10 ** (-0.4 * rng.normal(0.0, 0.25, len(flux)))
    spurious_count = max(2, int(math.ceil(0.12 * max(len(indices), 10))))
    spurious_xy = np.column_stack(
        (
            rng.uniform(10, WIDTH - 10, spurious_count),
            rng.uniform(10, HEIGHT - 10, spurious_count),
        )
    )
    if len(flux):
        spurious_flux = rng.uniform(float(flux.min()), float(flux.max()), spurious_count)
    else:
        spurious_flux = np.ones(spurious_count)
    xy = np.vstack((xy, spurious_xy))
    flux = np.concatenate((flux, spurious_flux))
    order = np.argsort(-flux, kind="stable")
    detections = DetectedStars(
        xy[order, 0].astype(np.float64),
        xy[order, 1].astype(np.float64),
        flux[order].astype(np.float64),
        np.full(len(order), 3.0),
        WIDTH,
        HEIGHT,
    )
    return {
        "kind": "positive",
        "trial": trial,
        "range_id": range_id,
        "declination_band": _declination_band(dec),
        "field_width_deg": field_width,
        "detections": detections,
        "quad_detections": detections,
        "input_scale_arcsec": None,
        "truth": truth,
    }


def _negative_case(
    rng: np.random.Generator, trial: int, count: int, flux_min: float, flux_max: float
) -> dict[str, Any]:
    count = max(count, 12)
    flux = np.sort(rng.uniform(flux_min, flux_max, count))[::-1]
    detections = DetectedStars(
        rng.uniform(10, WIDTH - 10, count),
        rng.uniform(10, HEIGHT - 10, count),
        flux,
        np.full(count, 3.0),
        WIDTH,
        HEIGHT,
    )
    return {
        "kind": "negative",
        "trial": trial,
        "range_id": None,
        "declination_band": None,
        "field_width_deg": None,
        "detections": detections,
        "quad_detections": detections,
        "input_scale_arcsec": None,
        "truth": None,
    }


def _pack_detections(cases: list[dict[str, Any]], key: str) -> tuple[np.ndarray, np.ndarray]:
    offsets = [0]
    values: list[np.ndarray] = []
    for case in cases:
        detections = case[key]
        values.append(
            np.column_stack((detections.x, detections.y, detections.flux, detections.fwhm)).astype(
                np.float64
            )
        )
        offsets.append(offsets[-1] + len(detections))
    packed = np.concatenate(values) if values else np.empty((0, 4), dtype=np.float64)
    return packed, np.asarray(offsets, dtype=np.int64)


def _write_fixture(path: Path, cases: list[dict[str, Any]]) -> None:
    detections, detection_offsets = _pack_detections(cases, "detections")
    quads, quad_offsets = _pack_detections(cases, "quad_detections")
    truths = np.full((len(cases), 12), np.nan, dtype=np.float64)
    for index, case in enumerate(cases):
        truth = case["truth"]
        if truth is None:
            continue
        truths[index] = (
            truth.crval_ra,
            truth.crval_dec,
            truth.cd[0, 0],
            truth.cd[0, 1],
            truth.cd[1, 0],
            truth.cd[1, 1],
            truth.crpix[0],
            truth.crpix[1],
            truth.width,
            truth.height,
            truth.scale_arcsec,
            truth.parity,
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        np.savez_compressed(
            stream,
            fixture_version=np.asarray([1], dtype=np.int64),
            kind=np.asarray([case["kind"] for case in cases]),
            trial=np.asarray([case["trial"] for case in cases], dtype=np.int64),
            range_id=np.asarray([case["range_id"] or "" for case in cases]),
            declination_band=np.asarray([case["declination_band"] or "" for case in cases]),
            field_width_deg=np.asarray(
                [case["field_width_deg"] or np.nan for case in cases], dtype=np.float64
            ),
            width=np.asarray([WIDTH] * len(cases), dtype=np.int64),
            height=np.asarray([HEIGHT] * len(cases), dtype=np.int64),
            input_scale_arcsec=np.asarray(
                [
                    case["input_scale_arcsec"] if case["input_scale_arcsec"] is not None else np.nan
                    for case in cases
                ],
                dtype=np.float64,
            ),
            truth_wcs=truths,
            detections=detections,
            detection_offsets=detection_offsets,
            quad_detections=quads,
            quad_detection_offsets=quad_offsets,
        )


def _as_astropy(wcs: TanWCS) -> WCS:
    result = WCS(naxis=2)
    result.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    result.wcs.cunit = ["deg", "deg"]
    result.wcs.crval = [wcs.crval_ra, wcs.crval_dec]
    result.wcs.crpix = wcs.crpix
    result.wcs.cd = wcs.cd
    result.array_shape = (wcs.height, wcs.width)
    return result


def _wrong(truth: TanWCS, candidate: TanWCS) -> bool:
    if truth.parity != candidate.parity:
        return True
    xs = np.linspace(0.05 * (truth.width - 1), 0.95 * (truth.width - 1), 7)
    ys = np.linspace(0.05 * (truth.height - 1), 0.95 * (truth.height - 1), 7)
    xx, yy = np.meshgrid(xs, ys)
    sky = _as_astropy(truth).pixel_to_world(xx.ravel(), yy.ravel())
    candidate_x, candidate_y = _as_astropy(candidate).world_to_pixel(sky)
    distances = np.hypot(candidate_x - xx.ravel(), candidate_y - yy.ravel())
    if not np.all(np.isfinite(distances)):
        return True
    median = float(np.median(distances))
    return median > 0.01 * math.hypot(truth.width, truth.height)


def _counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "trials": len(rows),
        "solved": sum(bool(row["solved"]) for row in rows),
        "wrong": sum(bool(row["wrong"]) for row in rows),
    }


def test_real_sky_trials() -> None:
    assert STAR_DATA is not None
    fixture_value = os.environ.get("NIGHTCRATE_TRIALS_FIXTURE")
    output_value = os.environ.get("NIGHTCRATE_TRIALS_OUTPUT")
    assert fixture_value, "NIGHTCRATE_TRIALS_FIXTURE is required for real-sky trials"
    assert output_value, "NIGHTCRATE_TRIALS_OUTPUT is required for real-sky trials"
    fixture_path = Path(fixture_value)
    output_path = Path(output_value)
    positive_count = int(os.environ.get("NIGHTCRATE_TRIALS_N", "2000"))
    assert positive_count > 0

    rng = np.random.default_rng(SEED)
    catalog_path = (
        STAR_DATA / f"siril-astro-gaia-dr3-{SIRIL_SOURCE.version}" / SIRIL_SOURCE.uncompressed_name
    )
    with SirilCatalog(catalog_path) as source:
        positives = [_real_sky_case(source, rng, trial) for trial in range(positive_count)]
    negatives: list[dict[str, Any]] = []
    for trial in range(NEGATIVE_COUNT):
        example = positives[trial % len(positives)]["detections"]
        flux_min = float(example.flux.min(initial=1.0))
        flux_max = float(example.flux.max(initial=max(2.0, flux_min)))
        negatives.append(_negative_case(rng, trial, len(example), flux_min, flux_max))
    cases = positives + negatives

    # This write intentionally precedes every solver call so the prototype can
    # consume the exact inputs even if a later product solve fails or crashes.
    _write_fixture(fixture_path, cases)

    layer_paths = [STAR_DATA / "indexes" / f"{name}.ncidx" for name in LAYERS]
    layers = [IndexLayer(path) for path in layer_paths]
    rows: list[dict[str, Any]] = []
    try:
        with SirilCatalog(catalog_path) as source:
            for case in cases:
                started = time.perf_counter()
                result = search_index(
                    case["detections"],
                    case["quad_detections"],
                    layers,
                    source,
                    pixel_scale_arcsec=case["input_scale_arcsec"],
                    near=None,
                    deadline=time.perf_counter() + 30.0,
                    cancel=threading.Event(),
                )
                wrong = bool(
                    result.solved
                    and (
                        case["truth"] is None
                        or result.wcs is None
                        or _wrong(case["truth"], result.wcs)
                    )
                )
                rows.append(
                    {
                        "kind": case["kind"],
                        "trial": case["trial"],
                        "range_id": case["range_id"],
                        "declination_band": case["declination_band"],
                        "solved": result.solved,
                        "wrong": wrong,
                        "status": result.status,
                        "seconds": time.perf_counter() - started,
                    }
                )
    finally:
        for layer in layers:
            layer.close()

    positive_rows = [row for row in rows if row["kind"] == "positive"]
    negative_rows = [row for row in rows if row["kind"] == "negative"]
    by_range: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_declination: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in positive_rows:
        by_range[str(row["range_id"])].append(row)
        by_declination[str(row["declination_band"])].append(row)
    report = {
        "seed": SEED,
        "positive": _counts(positive_rows),
        "negative": _counts(negative_rows),
        "recovery_by_field_range": {key: _counts(value) for key, value in sorted(by_range.items())},
        "recovery_by_declination_band": {
            key: _counts(value) for key, value in sorted(by_declination.items())
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    assert report["positive"]["wrong"] == 0
    # Regression floor, not a target: the trials include deliberately hard
    # fields, and the accepted baseline is 1540 of 2000 (77%), measured on
    # 2026-10-29 and again on 2026-10-30.
    assert report["positive"]["solved"] >= math.ceil(0.75 * report["positive"]["trials"])
    assert report["negative"]["solved"] == 0
