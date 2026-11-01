from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from .geometry import (
    QuadSet,
    angular_separation_deg,
    build_neighbour_quads,
    build_quads,
    fit_similarity,
    gnomonic_inverse,
    gnomonic_project,
    pixel_to_world,
    radec_to_unit,
    world_to_pixel,
)
from .models import (
    DetectedStars,
    FloatArray,
    SolverConfig,
    SolveResult,
    StarCatalog,
    TanWCS,
)


@dataclass(frozen=True)
class _Verification:
    accepted: bool
    reason: str
    log_odds: float
    catalog_indices: np.ndarray
    detection_indices: np.ndarray
    distances: FloatArray


def _select_catalog(
    catalog: StarCatalog,
    hint_ra: float,
    hint_dec: float,
    radius_deg: float,
    limit: int,
) -> tuple[StarCatalog, np.ndarray]:
    center = radec_to_unit(np.array([hint_ra]), np.array([hint_dec]))[0]
    dots = radec_to_unit(catalog.ra, catalog.dec) @ center
    mask = dots >= math.cos(math.radians(min(radius_deg, 89.0)))
    indices = np.flatnonzero(mask)
    indices = indices[np.argsort(catalog.g[indices], kind="stable")[:limit]]
    return catalog.take(indices), indices


def _catalog_cell_indices(
    catalog_xy: FloatArray,
    magnitudes: np.ndarray,
    depth: int,
    cell_width: float,
    cell_height: float,
    overlap: bool,
) -> list[np.ndarray]:
    """Return brightest-N field-sized catalog cells, including shifted tiles."""
    shifts = ((0.0, 0.0),)
    if overlap:
        # Two diagonal half-cell tilings cover boundaries without quadrupling
        # every quad build in the hint cone.
        shifts = ((0.0, 0.0), (0.5, 0.5))
    brightness = np.argsort(magnitudes, kind="stable")
    cells: list[np.ndarray] = []
    seen: set[tuple[int, ...]] = set()
    for shift_x, shift_y in shifts:
        cell_x = np.floor(catalog_xy[:, 0] / cell_width - shift_x).astype(np.int64)
        cell_y = np.floor(catalog_xy[:, 1] / cell_height - shift_y).astype(np.int64)
        grouped: dict[tuple[int, int], list[int]] = {}
        for index in brightness:
            key = (int(cell_x[index]), int(cell_y[index]))
            group = grouped.setdefault(key, [])
            if len(group) < depth:
                group.append(int(index))
        for key in sorted(grouped):
            values = tuple(grouped[key])
            if len(values) < 4 or values in seen:
                continue
            seen.add(values)
            cells.append(np.asarray(values, dtype=int))
    return cells


def _search_radii(maximum: float, initial: float, growth: float) -> list[float]:
    if maximum <= 0:
        return [0.0]
    radius = min(maximum, max(min(initial, maximum), 1e-6))
    radii = [radius]
    while radii[-1] < maximum:
        next_radius = min(maximum, radii[-1] * max(growth, 1.1))
        if next_radius <= radii[-1] + 1e-12:
            break
        radii.append(next_radius)
    return radii


def _combine_quads(parts: list[QuadSet]) -> QuadSet:
    populated = [part for part in parts if len(part)]
    if not populated:
        return QuadSet(np.empty((0, 4)), np.empty((0, 4), dtype=np.int32), np.empty(0))
    return QuadSet(
        np.concatenate([part.codes for part in populated]),
        np.concatenate([part.indices for part in populated]),
        np.concatenate([part.diameters for part in populated]),
        any(part.capped for part in populated),
    )


def _match_predicted(
    predicted: FloatArray,
    detections: DetectedStars,
    radius: float,
    candidate_indices: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, FloatArray]:
    inside = (
        (predicted[:, 0] >= 0)
        & (predicted[:, 0] <= detections.width - 1)
        & (predicted[:, 1] >= 0)
        & (predicted[:, 1] <= detections.height - 1)
        & np.all(np.isfinite(predicted), axis=1)
    )
    if candidate_indices is None:
        cat_candidates = np.flatnonzero(inside)
    else:
        candidates = np.asarray(candidate_indices, dtype=int)
        cat_candidates = candidates[inside[candidates]]
    if not len(cat_candidates) or not len(detections):
        return np.empty(0, dtype=int), np.empty(0, dtype=int), np.empty(0)
    distances, det_indices = cKDTree(detections.xy).query(predicted[cat_candidates])
    order = np.argsort(distances, kind="stable")
    used: set[int] = set()
    cat_matches: list[int] = []
    det_matches: list[int] = []
    match_distances: list[float] = []
    for position in order:
        distance = float(distances[position])
        det_index = int(det_indices[position])
        if distance > radius or det_index in used:
            continue
        used.add(det_index)
        cat_matches.append(int(cat_candidates[position]))
        det_matches.append(det_index)
        match_distances.append(distance)
    return np.asarray(cat_matches), np.asarray(det_matches), np.asarray(match_distances)


def _geometry_reason(cd: FloatArray, config: SolverConfig) -> str | None:
    axes = np.linalg.norm(cd, axis=0)
    if np.min(axes) <= 0 or np.max(axes) / np.min(axes) > config.max_axis_scale_ratio:
        return "implausible axis scale ratio"
    cosine = abs(float(cd[:, 0] @ cd[:, 1] / np.prod(axes)))
    nonorthogonality = abs(90.0 - math.degrees(math.acos(np.clip(cosine, -1.0, 1.0))))
    if nonorthogonality > config.max_axis_nonorthogonality_deg:
        return "pixel axes are not perpendicular"
    return None


def _verify_predictions(
    predicted: FloatArray,
    detections: DetectedStars,
    config: SolverConfig,
    *,
    cd: FloatArray | None = None,
    catalog_g: np.ndarray | None = None,
    match_radius_px: float | None = None,
) -> _Verification:
    inside = (
        (predicted[:, 0] >= 0)
        & (predicted[:, 0] <= detections.width - 1)
        & (predicted[:, 1] >= 0)
        & (predicted[:, 1] <= detections.height - 1)
        & np.all(np.isfinite(predicted), axis=1)
    )
    predicted_indices = np.flatnonzero(inside)
    if catalog_g is not None:
        maximum = max(
            config.min_matches,
            int(math.ceil(config.verification_catalog_ratio * len(detections))),
        )
        order = np.argsort(catalog_g[predicted_indices], kind="stable")
        predicted_indices = predicted_indices[order[:maximum]]
    cat_idx, det_idx, distances = _match_predicted(
        predicted,
        detections,
        config.initial_match_radius_px if match_radius_px is None else match_radius_px,
        candidate_indices=predicted_indices,
    )
    # Lang et al. (2010), section 3: every image detection is evidence.  The
    # old catalogue-centric score counted only cherry-picked close pairs and
    # penalised unmatched catalogue stars, so a candidate manufactured from a
    # matching quad could score +33 on random dots.  Here unmatched image
    # detections contribute log(epsilon), while close detections receive the
    # likelihood ratio against a spatially uniform background.
    area = max(float(detections.width * detections.height), 1.0)
    star_sigma = float(np.median(detections.fwhm) / 2.35482) if len(detections) else 0.0
    sigma = max(1.2, 1.6 * config.position_sigma_px, 1.6 * star_sigma)
    epsilon = 1.0 - config.true_match_probability
    if len(predicted_indices):
        image_distances, _ = cKDTree(predicted[predicted_indices]).query(detections.xy)
        gain = (
            config.true_match_probability
            * area
            / (len(predicted_indices) * 2.0 * math.pi * sigma**2)
        )
        terms = np.log(gain * np.exp(-0.5 * (image_distances / sigma) ** 2) + epsilon)
        log_odds = float(terms.sum())
    else:
        log_odds = float("-inf")

    if cd is not None and (reason := _geometry_reason(cd, config)):
        return _Verification(False, reason, log_odds, cat_idx, det_idx, distances)
    if len(cat_idx) < config.min_matches:
        return _Verification(
            False,
            f"only {len(cat_idx)} matches (need {config.min_matches})",
            log_odds,
            cat_idx,
            det_idx,
            distances,
        )
    center = np.array([(detections.width - 1) / 2, (detections.height - 1) / 2])
    matched_xy = detections.xy[det_idx]
    quadrants = (matched_xy[:, 0] >= center[0]).astype(int) + 2 * (
        matched_xy[:, 1] >= center[1]
    ).astype(int)
    if len(np.unique(quadrants)) < config.min_quadrants:
        return _Verification(
            False,
            "matches cover fewer than 3 quadrants",
            log_odds,
            cat_idx,
            det_idx,
            distances,
        )
    if log_odds < config.log_odds_threshold:
        return _Verification(
            False,
            f"log-odds {log_odds:.2f} below {config.log_odds_threshold:.2f}",
            log_odds,
            cat_idx,
            det_idx,
            distances,
        )
    return _Verification(True, "verified", log_odds, cat_idx, det_idx, distances)


def _fit_tan(
    catalog: StarCatalog,
    detections: DetectedStars,
    cat_indices: np.ndarray,
    det_indices: np.ndarray,
    initial_ra: float,
    initial_dec: float,
) -> TanWCS:
    center_pixel = np.array([(detections.width - 1.0) / 2.0, (detections.height - 1.0) / 2.0])
    pixels = detections.xy[det_indices]
    delta = pixels - center_pixel
    crval_ra, crval_dec = initial_ra, initial_dec
    cd = np.eye(2)
    for _ in range(8):
        tangent, valid = gnomonic_project(
            catalog.ra[cat_indices], catalog.dec[cat_indices], crval_ra, crval_dec
        )
        if np.count_nonzero(valid) < 4:
            raise ValueError("too few fit stars project in front of tangent plane")
        design = np.column_stack((delta[valid], np.ones(np.count_nonzero(valid))))
        coefficients, *_ = np.linalg.lstsq(design, tangent[valid], rcond=None)
        cd = coefficients[:2].T
        offset = coefficients[2]
        new_ra, new_dec = gnomonic_inverse(offset, crval_ra, crval_dec)
        movement = angular_separation_deg(crval_ra, crval_dec, float(new_ra), float(new_dec))
        crval_ra, crval_dec = float(new_ra), float(new_dec)
        if movement < 1e-10:
            break
    # The final center move changes the tangent coordinates slightly; refit without intercept.
    tangent, valid = gnomonic_project(
        catalog.ra[cat_indices], catalog.dec[cat_indices], crval_ra, crval_dec
    )
    coefficients, *_ = np.linalg.lstsq(delta[valid], tangent[valid], rcond=None)
    cd = coefficients.T
    return TanWCS(crval_ra, crval_dec, cd, detections.width, detections.height)


def _refine(
    initial: TanWCS,
    catalog: StarCatalog,
    detections: DetectedStars,
    config: SolverConfig,
) -> tuple[TanWCS, _Verification, float]:
    wcs = initial
    cat_idx = np.empty(0, dtype=int)
    det_idx = np.empty(0, dtype=int)
    distances = np.empty(0)
    for radius in (4.0, 2.5, config.final_match_radius_px):
        predicted, valid = world_to_pixel(wcs, catalog.ra, catalog.dec)
        predicted[~valid] = np.nan
        cat_idx, det_idx, distances = _match_predicted(predicted, detections, radius)
        if len(cat_idx) < 4:
            break
        if len(distances) >= 8:
            median = np.median(distances)
            robust_sigma = 1.4826 * np.median(np.abs(distances - median))
            clip = max(1.0, median + 3.0 * robust_sigma)
            keep = distances <= min(radius, clip)
            cat_idx, det_idx = cat_idx[keep], det_idx[keep]
        wcs = _fit_tan(catalog, detections, cat_idx, det_idx, wcs.crval_ra, wcs.crval_dec)
    predicted, valid = world_to_pixel(wcs, catalog.ra, catalog.dec)
    predicted[~valid] = np.nan
    verification = _verify_predictions(
        predicted,
        detections,
        config,
        cd=wcs.cd,
        catalog_g=catalog.g,
    )
    if len(verification.distances):
        rms = float(np.sqrt(np.mean(verification.distances**2)))
    else:
        rms = float("inf")
    return wcs, verification, rms


def _candidate_from_quads(
    catalog_xy: FloatArray,
    image_xy: FloatArray,
    catalog_quads: QuadSet,
    image_quads: QuadSet,
    catalog_quad_index: int,
    image_quad_index: int,
) -> tuple[FloatArray, FloatArray, float]:
    cat_points = catalog_xy[catalog_quads.indices[catalog_quad_index]]
    img_points = image_xy[image_quads.indices[image_quad_index]]
    return fit_similarity(cat_points, img_points)


def _solution_grid_median_px(first: TanWCS, second: TanWCS) -> float:
    xs = np.linspace(0.05 * (first.width - 1), 0.95 * (first.width - 1), 5)
    ys = np.linspace(0.05 * (first.height - 1), 0.95 * (first.height - 1), 5)
    xx, yy = np.meshgrid(xs, ys)
    grid = np.column_stack((xx.ravel(), yy.ravel()))
    ra, dec = pixel_to_world(first, grid)
    projected, valid = world_to_pixel(second, ra, dec)
    if not np.all(valid):
        return float("inf")
    return float(np.median(np.linalg.norm(projected - grid, axis=1)))


def _solve_hinted_stage(
    detections: DetectedStars,
    catalog: StarCatalog,
    *,
    hint_ra: float,
    hint_dec: float,
    hint_radius_deg: float = 2.0,
    pixel_scale_arcsec: float | None = None,
    scale_tolerance: float | None = None,
    config: SolverConfig | None = None,
    _deadline: float | None = None,
    cancel: threading.Event | None = None,
) -> SolveResult:
    """Solve in progressive hint-radius and matched brightness-depth passes."""
    started = time.perf_counter()
    config = config or SolverConfig()
    if len(detections) < max(4, config.min_matches):
        return SolveResult(
            "not_solved", "not enough detected stars", detected_count=len(detections)
        )
    if len(catalog) < 4:
        return SolveResult("not_solved", "not enough catalog stars", detected_count=len(detections))

    scale_low = config.scale_min_arcsec
    scale_high = config.scale_max_arcsec
    tolerance = config.scale_tolerance if scale_tolerance is None else scale_tolerance
    if pixel_scale_arcsec is not None:
        scale_low = pixel_scale_arcsec * (1.0 - tolerance)
        scale_high = pixel_scale_arcsec * (1.0 + tolerance)
    expected_scale = (
        pixel_scale_arcsec
        if pixel_scale_arcsec is not None
        else math.sqrt(config.scale_min_arcsec * config.scale_max_arcsec)
    )
    image_span = math.hypot(detections.width, detections.height)
    expected_diagonal = expected_scale * image_span / 3600.0
    radii = _search_radii(
        hint_radius_deg,
        max(config.initial_search_radius_deg, expected_diagonal),
        config.radius_growth,
    )
    depths = sorted(
        {min(int(depth), len(detections)) for depth in config.depth_passes if depth >= 4}
    )
    if config.include_all_depth_pass and (not depths or depths[-1] != len(detections)):
        depths.append(len(detections))
    quad_builder = build_quads if config.quad_method == "diameter" else build_neighbour_quads
    min_cat_diameter = config.image_quad_min_fraction * image_span * scale_low / 3600.0
    max_cat_diameter = config.image_quad_max_fraction * image_span * scale_high / 3600.0
    cell_width = max(expected_scale * detections.width / 3600.0, 1e-6)
    cell_height = max(expected_scale * detections.height / 3600.0, 1e-6)
    image_order_all = np.argsort(-detections.flux, kind="stable")
    image_cache: dict[int, tuple[np.ndarray, list[QuadSet]]] = {}
    timing_totals = {
        "catalog_select": 0.0,
        "quad_build": 0.0,
        "match": 0.0,
        "verify": 0.0,
    }
    caps: list[str] = []
    tested_total = 0
    max_false_log_odds = float("-inf")
    rejection = "candidate verification failed"
    timed_out = False
    cancelled = False
    last_radius: float | None = None
    last_depth: int | None = None
    for radius in radii:
        if cancel is not None and cancel.is_set():
            rejection = "solve cancelled"
            cancelled = True
            break
        if _deadline is not None and time.perf_counter() >= _deadline:
            rejection = "solve time budget exhausted"
            timed_out = True
            break
        select_started = time.perf_counter()
        local_catalog, _ = _select_catalog(
            catalog,
            hint_ra,
            hint_dec,
            radius + expected_diagonal / 2.0,
            len(catalog),
        )
        catalog_xy, valid = gnomonic_project(local_catalog.ra, local_catalog.dec, hint_ra, hint_dec)
        local_catalog = local_catalog.take(np.flatnonzero(valid))
        catalog_xy = catalog_xy[valid]
        timing_totals["catalog_select"] += time.perf_counter() - select_started
        if len(local_catalog) < config.min_matches:
            rejection = "not enough catalog stars near hint"
            continue

        for depth in depths:
            if cancel is not None and cancel.is_set():
                rejection = "solve cancelled"
                cancelled = True
                break
            if _deadline is not None and time.perf_counter() >= _deadline:
                rejection = "solve time budget exhausted"
                timed_out = True
                break
            last_radius, last_depth = radius, depth
            build_started = time.perf_counter()
            if depth not in image_cache:
                image_order = image_order_all[:depth]
                image_xy = detections.xy[image_order]
                build_options = {
                    "min_diameter": config.image_quad_min_fraction * image_span,
                    "max_diameter": config.image_quad_max_fraction * image_span,
                    "max_quads": config.max_image_quads,
                    "max_interior_stars": config.quad_interior_stars,
                    "quads_per_diameter": config.quads_per_diameter,
                }
                image_quads_sets = [
                    quad_builder(image_xy, **build_options),
                    quad_builder(image_xy * np.array([1.0, -1.0]), **build_options),
                ]
                image_cache[depth] = (image_order, image_quads_sets)
                if any(part.capped for part in image_quads_sets):
                    caps.append(f"image depth={depth} max={config.max_image_quads}")
            image_order, image_quads_sets = image_cache[depth]
            cell_indices = _catalog_cell_indices(
                catalog_xy,
                local_catalog.g,
                max(4, int(math.ceil(depth * config.catalog_depth_multiple))),
                cell_width,
                cell_height,
                config.catalog_cell_overlap,
            )
            catalog_parts: list[QuadSet] = []
            catalog_quad_cap = config.max_catalog_quads_per_cell
            for cell_number, indices in enumerate(cell_indices):
                if cancel is not None and cancel.is_set():
                    rejection = "solve cancelled"
                    cancelled = True
                    break
                if _deadline is not None and time.perf_counter() >= _deadline:
                    rejection = "solve time budget exhausted"
                    timed_out = True
                    break
                part = quad_builder(
                    catalog_xy[indices],
                    min_diameter=min_cat_diameter,
                    max_diameter=max_cat_diameter,
                    max_quads=catalog_quad_cap,
                    max_interior_stars=config.quad_interior_stars,
                    quads_per_diameter=config.quads_per_diameter,
                )
                if len(part):
                    part = QuadSet(part.codes, indices[part.indices], part.diameters, part.capped)
                    catalog_parts.append(part)
                if part.capped:
                    caps.append(
                        f"catalog radius={radius:g} depth={depth} cell={cell_number} "
                        f"max={catalog_quad_cap}"
                    )
            if timed_out or cancelled:
                break
            catalog_quads = _combine_quads(catalog_parts)
            timing_totals["quad_build"] += time.perf_counter() - build_started
            if not len(catalog_quads) or not any(len(part) for part in image_quads_sets):
                rejection = "no usable quads"
                continue

            match_started = time.perf_counter()
            code_tree = cKDTree(catalog_quads.codes)
            code_matches: list[tuple[float, int, int, int]] = []
            for parity_index, image_quads in enumerate(image_quads_sets):
                matches = code_tree.query_ball_point(image_quads.codes, r=config.code_tolerance)
                for image_index, catalog_indices in enumerate(matches):
                    if not catalog_indices:
                        continue
                    deltas = catalog_quads.codes[catalog_indices] - image_quads.codes[image_index]
                    distances = np.linalg.norm(deltas, axis=1)
                    code_matches.extend(
                        (float(distance), parity_index, image_index, int(catalog_index))
                        for distance, catalog_index in zip(distances, catalog_indices, strict=True)
                    )
            code_matches.sort(key=lambda item: item[0])
            code_matches = code_matches[: config.max_code_matches]
            timing_totals["match"] += time.perf_counter() - match_started
            if not code_matches:
                rejection = "no quad-code matches"
                continue

            verify_started = time.perf_counter()
            accepted: list[tuple[TanWCS, _Verification, float]] = []
            first_accepted_at: float | None = None
            tested = 0
            seen: set[tuple[tuple[int, ...], tuple[int, ...]]] = set()
            for _, parity_index, image_quad_index, catalog_quad_index in code_matches:
                if cancel is not None and cancel.is_set():
                    rejection = "solve cancelled"
                    cancelled = True
                    break
                if _deadline is not None and time.perf_counter() >= _deadline:
                    rejection = "solve time budget exhausted"
                    timed_out = True
                    break
                if tested >= config.max_candidates:
                    break
                image_quads = image_quads_sets[parity_index]
                cat_ids = catalog_quads.indices[catalog_quad_index]
                img_local_ids = image_quads.indices[image_quad_index]
                image_ids = image_order[img_local_ids]
                key = (
                    tuple(sorted(int(v) for v in cat_ids)),
                    tuple(sorted(int(v) for v in image_ids)),
                )
                if key in seen:
                    continue
                seen.add(key)
                matrix, offset, quad_rms = fit_similarity(
                    catalog_xy[cat_ids], detections.xy[image_ids]
                )
                if quad_rms > max(3.0, 0.015 * image_span):
                    continue
                determinant = abs(np.linalg.det(matrix))
                if determinant <= 0:
                    continue
                candidate_scale = 3600.0 / math.sqrt(determinant)
                if not scale_low <= candidate_scale <= scale_high:
                    continue
                tested += 1
                predicted = catalog_xy @ matrix.T + offset
                initial_cd = np.linalg.inv(matrix)
                verification = _verify_predictions(
                    predicted,
                    detections,
                    config,
                    cd=initial_cd,
                    catalog_g=local_catalog.g,
                )
                rejection = verification.reason
                if not verification.accepted:
                    max_false_log_odds = max(max_false_log_odds, verification.log_odds)
                    continue
                tangent_center = (
                    np.array([(detections.width - 1) / 2, (detections.height - 1) / 2]) - offset
                ) @ np.linalg.inv(matrix).T
                initial_ra, initial_dec = gnomonic_inverse(tangent_center, hint_ra, hint_dec)
                approximate = TanWCS(
                    float(initial_ra),
                    float(initial_dec),
                    initial_cd,
                    detections.width,
                    detections.height,
                )
                if accepted and (
                    approximate.parity == accepted[0][0].parity
                    and _solution_grid_median_px(accepted[0][0], approximate) <= 0.01 * image_span
                ):
                    # It is another quad supporting the already-verified sky
                    # position. The initial all-star verification is enough
                    # to classify it as the same ambiguity cluster.
                    continue
                try:
                    initial_wcs = _fit_tan(
                        local_catalog,
                        detections,
                        verification.catalog_indices,
                        verification.detection_indices,
                        float(initial_ra),
                        float(initial_dec),
                    )
                    fitted, final_verification, rms = _refine(
                        initial_wcs, local_catalog, detections, config
                    )
                except ValueError, np.linalg.LinAlgError:
                    rejection = "TAN fit failed"
                    continue
                rejection = final_verification.reason
                if not final_verification.accepted:
                    max_false_log_odds = max(max_false_log_odds, final_verification.log_odds)
                    continue
                if first_accepted_at is None:
                    first_accepted_at = time.perf_counter()
                if not accepted or (
                    fitted.parity != accepted[0][0].parity
                    or _solution_grid_median_px(accepted[0][0], fitted) > 0.01 * image_span
                ):
                    accepted.append((fitted, final_verification, rms))
            tested_total += tested
            timing_totals["verify"] += time.perf_counter() - verify_started
            if timed_out or cancelled:
                # A partial ambiguity scan cannot safely be called solved.
                accepted.clear()
                break
            if accepted:
                accepted.sort(key=lambda value: (value[1].log_odds, -value[2]), reverse=True)
                wcs, verification, rms = accepted[0]
                timing_totals["ambiguity_extra"] = (
                    time.perf_counter() - first_accepted_at
                    if first_accepted_at is not None
                    else 0.0
                )
                timing_totals["total"] = time.perf_counter() - started
                if len(accepted) > 1:
                    return SolveResult(
                        "ambiguous",
                        "multiple distinct verified solutions",
                        wcs=None,
                        log_odds=verification.log_odds,
                        matched_count=len(verification.catalog_indices),
                        detected_count=len(detections),
                        rms_px=rms,
                        rms_arcsec=rms * wcs.scale_arcsec,
                        candidates_tested=tested_total,
                        search_radius_deg=radius,
                        depth=depth,
                        quad_caps=list(dict.fromkeys(caps)),
                        timings=timing_totals,
                        ambiguous_wcs=[item[0] for item in accepted],
                        max_false_log_odds=max_false_log_odds,
                        fitted_detection_indices=[
                            int(value) for value in verification.detection_indices
                        ],
                    )
                return SolveResult(
                    "solved",
                    "verified",
                    wcs=wcs,
                    log_odds=verification.log_odds,
                    matched_count=len(verification.catalog_indices),
                    detected_count=len(detections),
                    rms_px=rms,
                    rms_arcsec=rms * wcs.scale_arcsec,
                    candidates_tested=tested_total,
                    search_radius_deg=radius,
                    depth=depth,
                    quad_caps=list(dict.fromkeys(caps)),
                    timings=timing_totals,
                    max_false_log_odds=max_false_log_odds,
                    fitted_detection_indices=[
                        int(value) for value in verification.detection_indices
                    ],
                )
        if timed_out or cancelled:
            break

    timing_totals["total"] = time.perf_counter() - started
    return SolveResult(
        "cancelled" if cancelled else "time_limit" if timed_out else "not_solved",
        rejection,
        detected_count=len(detections),
        candidates_tested=tested_total,
        search_radius_deg=last_radius,
        depth=last_depth,
        quad_caps=list(dict.fromkeys(caps)),
        timings=timing_totals,
        max_false_log_odds=max_false_log_odds,
        time_budget_hit=timed_out,
    )


def solve_hinted(
    detections: DetectedStars,
    catalog: StarCatalog,
    *,
    hint_ra: float,
    hint_dec: float,
    hint_radius_deg: float = 2.0,
    pixel_scale_arcsec: float | None = None,
    scale_tolerance: float | None = None,
    config: SolverConfig | None = None,
    deadline: float | None = None,
    cancel: threading.Event | None = None,
) -> SolveResult:
    """Solve progressively, including recovery from incorrect scale metadata."""
    started = time.perf_counter()
    config = config or SolverConfig()
    deadline = min(
        started + config.max_solve_seconds,
        deadline if deadline is not None else float("inf"),
    )
    stages: list[tuple[str, float | None]] = [("unknown", None)]
    if pixel_scale_arcsec is not None:
        stages = [
            ("hinted", pixel_scale_arcsec),
            ("half", pixel_scale_arcsec * 0.5),
            ("double", pixel_scale_arcsec * 2.0),
            ("unknown", None),
        ]
    tried: list[str] = []
    aggregate_timings: dict[str, float] = {}
    candidates = 0
    caps: list[str] = []
    last: SolveResult | None = None
    max_false_log_odds = float("-inf")
    for stage_name, stage_scale in stages:
        if cancel is not None and cancel.is_set():
            return SolveResult("cancelled", "solve cancelled", detected_count=len(detections))
        tried.append(stage_name)
        result = _solve_hinted_stage(
            detections,
            catalog,
            hint_ra=hint_ra,
            hint_dec=hint_dec,
            hint_radius_deg=hint_radius_deg,
            pixel_scale_arcsec=stage_scale,
            scale_tolerance=scale_tolerance,
            config=config,
            _deadline=deadline,
            cancel=cancel,
        )
        last = result
        max_false_log_odds = max(max_false_log_odds, result.max_false_log_odds)
        candidates += result.candidates_tested
        caps.extend(result.quad_caps)
        for key, value in result.timings.items():
            if key != "total":
                aggregate_timings[key] = aggregate_timings.get(key, 0.0) + value
        if result.status in ("time_limit", "cancelled"):
            break
        if result.status in ("solved", "ambiguous"):
            result.scale_stage = stage_name
            result.scale_stages_tried = tried.copy()
            result.candidates_tested = candidates
            result.quad_caps = list(dict.fromkeys(caps))
            aggregate_timings["total"] = time.perf_counter() - started
            result.timings = aggregate_timings
            result.max_false_log_odds = max_false_log_odds
            return result
    if last is None:
        raise RuntimeError("hinted solve did not run a scale stage")
    last.scale_stage = None
    last.scale_stages_tried = tried
    last.candidates_tested = candidates
    last.quad_caps = list(dict.fromkeys(caps))
    aggregate_timings["total"] = time.perf_counter() - started
    last.timings = aggregate_timings
    last.max_false_log_odds = max_false_log_odds
    return last
