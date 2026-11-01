from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from nightcrate.services.star_catalog.index import IndexLayer
from nightcrate.services.star_catalog.models import STAR_EPOCH, StarCatalog
from nightcrate.services.star_catalog.ranges import FIELD_RANGES
from nightcrate.services.star_catalog.siril import SirilCatalog

from .geometry import (
    angular_separation_deg,
    build_ranked_quads,
    fit_similarity,
    gnomonic_inverse,
    gnomonic_project,
    radec_to_unit,
    unit_to_radec,
    world_to_pixel,
)
from .models import (
    BlindSolverConfig,
    DetectedStars,
    SolverConfig,
    SolveReporter,
    SolveResult,
    TanWCS,
)
from .verify import (
    _fit_tan,
    _refine,
    _solution_grid_median_px,
    _verify_predictions,
)


def _quad_plane(stars: np.ndarray) -> tuple[np.ndarray, float, float]:
    vectors = radec_to_unit(stars["ra"].astype(np.float64), stars["dec"].astype(np.float64))
    center = vectors.mean(axis=0)
    center /= np.linalg.norm(center)
    center_ra, center_dec = unit_to_radec(center)
    xy, valid = gnomonic_project(
        stars["ra"].astype(np.float64),
        stars["dec"].astype(np.float64),
        float(center_ra),
        float(center_dec),
    )
    if not np.all(valid):
        raise ValueError("baseline crosses its tangent-plane horizon")
    return xy, float(center_ra), float(center_dec)


def _pair_transform(
    sky_ab: np.ndarray, image_ab: np.ndarray, mirrored: bool
) -> tuple[np.ndarray, np.ndarray]:
    """Return image = sky @ matrix.T + offset with prescribed parity."""
    sky_delta = sky_ab[1] - sky_ab[0]
    image_delta = image_ab[1] - image_ab[0]
    zs = complex(*sky_delta)
    zi = complex(*image_delta)
    if abs(zs) < 1e-15 or abs(zi) < 1e-9:
        raise ValueError("degenerate baseline")
    value = zi / (zs.conjugate() if mirrored else zs)
    if mirrored:
        matrix = np.array([[value.real, value.imag], [value.imag, -value.real]])
    else:
        matrix = np.array([[value.real, -value.imag], [value.imag, value.real]])
    offset = image_ab[0] - sky_ab[0] @ matrix.T
    return matrix, offset


def _seed_from_quad(
    sky_stars: np.ndarray,
    image_points: np.ndarray,
    width: int,
    height: int,
) -> TanWCS:
    """Fit a four-star seed in the tangent plane of its implied field centre."""
    ra = sky_stars["ra"].astype(np.float64)
    dec = sky_stars["dec"].astype(np.float64)
    _, center_ra, center_dec = _quad_plane(sky_stars)
    center_pixel = np.array([(width - 1.0) / 2.0, (height - 1.0) / 2.0])
    for _ in range(12):
        sky_xy, valid = gnomonic_project(ra, dec, center_ra, center_dec)
        if not np.all(valid):
            raise ValueError("quad crosses its field tangent-plane horizon")
        matrix, offset, _ = fit_similarity(sky_xy, image_points)
        if abs(float(np.linalg.det(matrix))) <= 1e-15:
            raise ValueError("singular quad transform")
        tangent_center = (center_pixel - offset) @ np.linalg.inv(matrix).T
        next_ra, next_dec = gnomonic_inverse(tangent_center, center_ra, center_dec)
        movement = angular_separation_deg(center_ra, center_dec, float(next_ra), float(next_dec))
        center_ra, center_dec = float(next_ra), float(next_dec)
        if movement < 1e-10:
            break
    sky_xy, valid = gnomonic_project(ra, dec, center_ra, center_dec)
    if not np.all(valid):
        raise ValueError("quad crosses its field tangent-plane horizon")
    matrix, _, _ = fit_similarity(sky_xy, image_points)
    return TanWCS(center_ra, center_dec, np.linalg.inv(matrix), width, height)


def _local_catalog(
    source: SirilCatalog | StarCatalog,
    ra: float,
    dec: float,
    radius: float,
    epoch: float,
) -> StarCatalog:
    if isinstance(source, SirilCatalog):
        return source.query_cone(ra, dec, radius, epoch=epoch)
    center_xy, valid = gnomonic_project(source.ra, source.dec, ra, dec)
    keep = valid & (np.linalg.norm(center_xy, axis=1) <= radius)
    return source.take(np.flatnonzero(keep))


def _cheap_index_check(
    band: IndexLayer,
    approximate: TanWCS,
    detections: DetectedStars,
    radius: float,
    match_radius_px: float,
) -> tuple[bool, int, int]:
    stars = band.query_stars(approximate.crval_ra, approximate.crval_dec, radius)
    if not len(stars):
        return True, 0, 0
    predicted, valid = world_to_pixel(
        approximate,
        stars["ra"].astype(np.float64),
        stars["dec"].astype(np.float64),
    )
    inside = (
        valid
        & (predicted[:, 0] >= 0)
        & (predicted[:, 0] < detections.width)
        & (predicted[:, 1] >= 0)
        & (predicted[:, 1] < detections.height)
    )
    predicted = predicted[inside]
    if len(predicted) < 6:
        return True, len(predicted), 0
    distances, detection_ids = cKDTree(detections.xy).query(
        predicted, distance_upper_bound=match_radius_px
    )
    matched = np.isfinite(distances)
    distinct = len(np.unique(detection_ids[matched]))
    return distinct >= 5, len(predicted), distinct


def _adaptive_seed_refine(
    band: IndexLayer,
    approximate: TanWCS,
    detections: DetectedStars,
    radius: float,
    quad_center_px: np.ndarray,
    baseline_px: float,
    config: SolverConfig,
) -> TanWCS:
    """Use nearby index stars to absorb short-baseline seed scale error."""
    stars = band.query_stars(approximate.crval_ra, approximate.crval_dec, radius)
    if len(stars) < 5:
        return approximate
    predicted, valid = world_to_pixel(
        approximate,
        stars["ra"].astype(np.float64),
        stars["dec"].astype(np.float64),
    )
    inside = (
        valid
        & (predicted[:, 0] >= 0)
        & (predicted[:, 0] < detections.width)
        & (predicted[:, 1] >= 0)
        & (predicted[:, 1] < detections.height)
    )
    star_ids = np.flatnonzero(inside)
    if len(star_ids) < 5:
        return approximate
    points = predicted[star_ids]
    distances, detection_ids = cKDTree(detections.xy).query(points)
    relative_error = float(
        np.clip(2.0 * config.position_sigma_px / max(baseline_px, 1.0), 0.0015, 0.006)
    )
    allowed = np.minimum(
        getattr(config, "seed_match_radius_px", 12.0),
        max(config.initial_match_radius_px, 4.0)
        + relative_error * np.linalg.norm(points - quad_center_px, axis=1),
    )
    eligible = np.flatnonzero(distances <= allowed)
    if len(eligible) < 5:
        return approximate
    order = eligible[np.argsort(distances[eligible] / allowed[eligible], kind="stable")]
    used: set[int] = set()
    chosen: list[int] = []
    for position in order:
        detection_id = int(detection_ids[position])
        if detection_id not in used:
            used.add(detection_id)
            chosen.append(int(position))
    if len(chosen) < 5:
        return approximate
    selected = np.asarray(chosen, dtype=int)
    catalog = StarCatalog(
        stars["ra"].astype(np.float64),
        stars["dec"].astype(np.float64),
        np.zeros(len(stars), dtype=np.float32),
    )
    try:
        return _fit_tan(
            catalog,
            detections,
            star_ids[selected],
            detection_ids[selected],
            approximate.crval_ra,
            approximate.crval_dec,
        )
    except ValueError, np.linalg.LinAlgError:
        return approximate


@dataclass
class _Candidate:
    wcs: TanWCS
    baseline_px: float
    code_distance: float
    quad_center_px: np.ndarray
    agreement: int = 1
    rank: int = 0


def _rank_candidates(candidates: list[_Candidate]) -> list[_Candidate]:
    if not candidates:
        return []
    vectors = radec_to_unit(
        np.asarray([item.wcs.crval_ra for item in candidates]),
        np.asarray([item.wcs.crval_dec for item in candidates]),
    )
    scales = np.asarray([item.wcs.scale_arcsec for item in candidates])
    angular_limit = 2.0 * math.sin(math.radians(0.25) / 2.0)
    tree = cKDTree(vectors)
    for index, item in enumerate(candidates):
        neighbours = np.asarray(tree.query_ball_point(vectors[index], angular_limit))
        item.agreement = int(
            np.count_nonzero(np.abs(scales[neighbours] / scales[index] - 1.0) < 0.03)
        )
    candidates.sort(key=lambda item: (-item.agreement, -item.baseline_px, item.code_distance))
    for rank, item in enumerate(candidates, 1):
        item.rank = rank
    return candidates


def _candidate_key(candidate: _Candidate) -> tuple[int, int, int, int]:
    wcs = candidate.wcs
    return (
        round(wcs.crval_ra * 40),
        round(wcs.crval_dec * 40),
        round(math.log(wcs.scale_arcsec) * 40),
        wcs.parity,
    )


def solve_blind(
    detections: DetectedStars,
    index_paths: list[IndexLayer],
    source: SirilCatalog | StarCatalog,
    *,
    pixel_scale_arcsec: float | None = None,
    config: SolverConfig | None = None,
    max_seconds: float = 30.0,
    hint_ra: float | None = None,
    hint_dec: float | None = None,
    hint_radius_deg: float = 2.0,
    cheap_check: bool = True,
    quad_detections: DetectedStars | None = None,
    deadline: float | None = None,
    cancel: threading.Event | None = None,
    reporter: SolveReporter | None = None,
) -> SolveResult:
    """Blind or scale-known solve from independently memory-mapped layers."""
    started = time.perf_counter()
    deadline = min(
        started + max_seconds,
        deadline if deadline is not None else float("inf"),
    )
    config = config or BlindSolverConfig()
    quad_detections = detections if quad_detections is None else quad_detections
    if len(detections) < max(4, config.min_matches):
        return SolveResult(
            "not_solved", "not enough detected stars", detected_count=len(detections)
        )
    image_span = math.hypot(quad_detections.width, quad_detections.height)
    brightness_order = np.argsort(-quad_detections.flux, kind="stable")
    depth_values = sorted(
        {
            min(value, len(quad_detections), config.blind_max_stars)
            for value in (*config.depth_passes, config.blind_max_stars)
            if min(value, len(quad_detections), config.blind_max_stars) >= 4
        }
    )
    bands = list(index_paths)
    timings = {
        "image_quads": 0.0,
        "index_lookup": 0.0,
        "candidate_rank": 0.0,
        "cheap_verify": 0.0,
        "catalog_read": 0.0,
        "verify": 0.0,
        "ambiguity_extra": 0.0,
    }
    counts = {
        "quad_code_matches": 0,
        "ranked_candidates": 0,
        "duplicate": 0,
        "geometry": 0,
        "cheap_index": 0,
        "cheap_survivors": 0,
        "catalog_too_small": 0,
        "siril_queries": 0,
        "full_verified": 0,
        "full_rejected": 0,
        "full_accepted": 0,
        "correct_rank": 0,
        "image_quads": 0,
        "correct_below_cap": 0,
        "correct_seed_rejected": 0,
        "correct_verification_rejected": 0,
        "max_agreement": 0,
    }
    best_false = float("-inf")
    tested = 0
    first_accepted_at: float | None = None
    timed_out = False
    cancelled = False
    try:
        if pixel_scale_arcsec is not None:
            field_deg = image_span * pixel_scale_arcsec / 3600.0
            bands = [
                band for band in bands if 1.5 <= field_deg / band.spec.nominal_diameter_deg <= 12.0
            ]
            bands.sort(
                key=lambda band: abs(math.log(field_deg / band.spec.nominal_diameter_deg / 4.5))
            )
        else:
            bands.sort(key=lambda band: band.spec.nominal_diameter_deg, reverse=True)
        if not bands:
            return SolveResult(
                "not_solved",
                "no index layer fits the scale",
                detected_count=len(detections),
            )

        seen_verified: set[tuple[int, int, int, int]] = set()
        for depth in depth_values:
            image_ids = brightness_order[:depth]
            image_xy = quad_detections.xy[image_ids]
            for band in bands:
                if cancel is not None and cancel.is_set():
                    cancelled = True
                    break
                if time.perf_counter() >= deadline:
                    timed_out = True
                    break
                if pixel_scale_arcsec is None:
                    low_px, high_px = 0.04 * image_span, 0.60 * image_span
                else:
                    low_px = band.spec.min_diameter_deg * 3600.0 / pixel_scale_arcsec / 1.30
                    high_px = band.spec.max_diameter_deg * 3600.0 / pixel_scale_arcsec * 1.30
                    low_px = max(low_px, 0.03 * image_span)
                    high_px = min(high_px, 0.70 * image_span)
                    if high_px <= low_px:
                        continue
                if reporter is not None:
                    reporter.searched(
                        [band.spec.name],
                        [item.id for item in FIELD_RANGES if band.spec.name in item.layers],
                    )
                build_started = time.perf_counter()
                image_sets = [
                    build_ranked_quads(
                        image_xy,
                        min_diameter=low_px,
                        max_diameter=high_px,
                        max_b_per_a=config.image_max_b_per_a,
                        max_quads=config.max_image_quads,
                    ),
                    build_ranked_quads(
                        image_xy * np.array([1.0, -1.0]),
                        min_diameter=low_px,
                        max_diameter=high_px,
                        max_b_per_a=config.image_max_b_per_a,
                        max_quads=config.max_image_quads,
                    ),
                ]
                timings["image_quads"] += time.perf_counter() - build_started
                counts["image_quads"] += sum(len(quads) for quads in image_sets)
                raw_matches: list[tuple[float, int, int, int]] = []
                lookup_started = time.perf_counter()
                for parity, quads in enumerate(image_sets):
                    tolerance = np.clip(
                        3.0 * config.position_sigma_px / np.maximum(quads.diameters, 1.0),
                        config.code_tolerance_min,
                        config.code_tolerance_max,
                    )
                    raw_matches.extend(
                        (distance, parity, image_row, disk_row)
                        for distance, image_row, disk_row in band.query_codes(
                            quads.codes,
                            tolerance,
                            config.max_code_matches,
                            None,
                        )
                    )
                timings["index_lookup"] += time.perf_counter() - lookup_started
                raw_matches.sort(key=lambda item: item[0])
                raw_matches = raw_matches[: config.max_code_matches]
                counts["quad_code_matches"] += len(raw_matches)

                candidates: list[_Candidate] = []
                for distance, parity, image_row, disk_row in raw_matches:
                    try:
                        sky_quad = band.quad_radec([disk_row])[0]
                        local_ids = image_sets[parity].indices[image_row]
                        detection_ids = image_ids[local_ids]
                        wcs = _seed_from_quad(
                            sky_quad,
                            quad_detections.xy[detection_ids],
                            detections.width,
                            detections.height,
                        )
                        scale = wcs.scale_arcsec
                        if not config.scale_min_arcsec <= scale <= config.scale_max_arcsec:
                            continue
                        if pixel_scale_arcsec is not None and not (
                            pixel_scale_arcsec * (1.0 - config.scale_tolerance)
                            <= scale
                            <= pixel_scale_arcsec * (1.0 + config.scale_tolerance)
                        ):
                            continue
                        if hint_ra is not None and hint_dec is not None:
                            if (
                                angular_separation_deg(
                                    wcs.crval_ra,
                                    wcs.crval_dec,
                                    hint_ra,
                                    hint_dec,
                                )
                                > hint_radius_deg
                            ):
                                continue
                        candidates.append(
                            _Candidate(
                                wcs,
                                float(image_sets[parity].diameters[image_row]),
                                distance,
                                quad_detections.xy[detection_ids].mean(axis=0),
                            )
                        )
                    except ValueError, np.linalg.LinAlgError:
                        counts["geometry"] += 1
                rank_started = time.perf_counter()
                candidates = _rank_candidates(candidates)
                timings["candidate_rank"] += time.perf_counter() - rank_started
                counts["ranked_candidates"] += len(candidates)
                if candidates:
                    counts["max_agreement"] = max(counts["max_agreement"], candidates[0].agreement)
                accepted: list[SolveResult] = []
                for candidate in candidates[: config.max_verify_per_layer]:
                    if cancel is not None and cancel.is_set():
                        cancelled = True
                        break
                    if time.perf_counter() >= deadline:
                        timed_out = True
                        break
                    key = _candidate_key(candidate)
                    if key in seen_verified:
                        counts["duplicate"] += 1
                        continue
                    tested += 1
                    approximate = candidate.wcs
                    radius = max(
                        0.1,
                        0.7 * approximate.scale_arcsec * image_span / 3600.0,
                    )
                    if cheap_check:
                        cheap_started = time.perf_counter()
                        survives, _, _ = _cheap_index_check(
                            band,
                            approximate,
                            quad_detections,
                            radius,
                            max(config.initial_match_radius_px, 4.0),
                        )
                        if not survives and candidate.agreement >= 2:
                            approximate = _adaptive_seed_refine(
                                band,
                                approximate,
                                quad_detections,
                                radius,
                                candidate.quad_center_px,
                                candidate.baseline_px,
                                config,
                            )
                            survives, _, _ = _cheap_index_check(
                                band,
                                approximate,
                                quad_detections,
                                radius,
                                max(config.initial_match_radius_px, 4.0),
                            )
                        timings["cheap_verify"] += time.perf_counter() - cheap_started
                        if not survives:
                            counts["cheap_index"] += 1
                            continue
                        counts["cheap_survivors"] += 1
                    catalog_started = time.perf_counter()
                    catalog = _local_catalog(
                        source,
                        approximate.crval_ra,
                        approximate.crval_dec,
                        radius,
                        STAR_EPOCH,
                    )
                    timings["catalog_read"] += time.perf_counter() - catalog_started
                    counts["siril_queries"] += 1
                    if len(catalog) < config.min_matches:
                        counts["catalog_too_small"] += 1
                        continue
                    verify_started = time.perf_counter()
                    seen_verified.add(key)
                    counts["full_verified"] += 1
                    predicted, valid = world_to_pixel(approximate, catalog.ra, catalog.dec)
                    predicted[~valid] = np.nan
                    verification = _verify_predictions(
                        predicted,
                        detections,
                        config,
                        cd=approximate.cd,
                        catalog_g=catalog.g,
                        match_radius_px=getattr(config, "seed_match_radius_px", 12.0),
                    )
                    fitted = None
                    rms = float("inf")
                    final_verification = verification
                    if verification.accepted:
                        try:
                            initial = _fit_tan(
                                catalog,
                                detections,
                                verification.catalog_indices,
                                verification.detection_indices,
                                approximate.crval_ra,
                                approximate.crval_dec,
                            )
                            fitted, final_verification, rms = _refine(
                                initial, catalog, detections, config
                            )
                        except ValueError, np.linalg.LinAlgError:
                            fitted = None
                    timings["verify"] += time.perf_counter() - verify_started
                    if fitted is None or not final_verification.accepted:
                        counts["full_rejected"] += 1
                        best_false = max(best_false, final_verification.log_odds)
                        continue
                    counts["full_accepted"] += 1
                    result = SolveResult(
                        "solved",
                        "verified",
                        wcs=fitted,
                        log_odds=final_verification.log_odds,
                        matched_count=len(final_verification.catalog_indices),
                        detected_count=len(detections),
                        rms_px=rms,
                        rms_arcsec=rms * fitted.scale_arcsec,
                        depth=depth,
                        search_radius_deg=radius,
                        fitted_detection_indices=[
                            int(value) for value in final_verification.detection_indices
                        ],
                        candidate_rank=candidate.rank,
                        candidate_agreement=candidate.agreement,
                    )
                    accepted.append(result)
                    if first_accepted_at is None:
                        first_accepted_at = time.perf_counter()
                    if len(accepted) > 1 and (
                        accepted[-1].wcs.parity != accepted[0].wcs.parity
                        or _solution_grid_median_px(accepted[-1].wcs, accepted[0].wcs)
                        > 0.01 * image_span
                    ):
                        if cancel is not None and cancel.is_set():
                            return SolveResult(
                                "cancelled",
                                "solve cancelled",
                                detected_count=len(detections),
                                candidates_tested=tested,
                            )
                        result = accepted[0]
                        result.status = "ambiguous"
                        result.reason = "multiple distinct verified blind solutions"
                        result.ambiguous_wcs = [item.wcs for item in accepted if item.wcs]
                        result.wcs = None
                        timings["total"] = time.perf_counter() - started
                        timings["ambiguity_extra"] = timings["total"] - (
                            first_accepted_at - started
                        )
                        result.timings = timings
                        result.candidates_tested = tested
                        result.max_false_log_odds = best_false
                        result.rejection_counts = counts
                        return result
                if accepted:
                    if cancelled:
                        return SolveResult(
                            "cancelled",
                            "solve cancelled",
                            detected_count=len(detections),
                            candidates_tested=tested,
                            timings=timings,
                        )
                    if timed_out:
                        return SolveResult(
                            "time_limit",
                            "blind solve time budget exhausted",
                            detected_count=len(detections),
                            candidates_tested=tested,
                            timings=timings,
                            time_budget_hit=True,
                        )
                    result = max(accepted, key=lambda item: item.log_odds)
                    timings["total"] = time.perf_counter() - started
                    if first_accepted_at is not None:
                        timings["ambiguity_extra"] = time.perf_counter() - first_accepted_at
                    result.timings = timings
                    result.candidates_tested = tested
                    result.max_false_log_odds = best_false
                    result.time_budget_hit = False
                    result.rejection_counts = counts
                    return result
            if cancelled or timed_out:
                break
        timings["total"] = time.perf_counter() - started
        if cancelled:
            return SolveResult(
                "cancelled",
                "solve cancelled",
                detected_count=len(detections),
                candidates_tested=tested,
                timings=timings,
                max_false_log_odds=best_false,
                rejection_counts=counts,
            )
        return SolveResult(
            "time_limit" if timed_out else "not_solved",
            "blind solve time budget exhausted" if timed_out else "no verified blind candidate",
            detected_count=len(detections),
            candidates_tested=tested,
            timings=timings,
            max_false_log_odds=best_false,
            time_budget_hit=timed_out,
            rejection_counts=counts,
        )
    finally:
        pass


def search_index(
    detections: DetectedStars,
    quad_detections: DetectedStars,
    layers: list[IndexLayer],
    catalog: SirilCatalog,
    *,
    pixel_scale_arcsec: float | None,
    near: tuple[float, float] | None,
    deadline: float,
    cancel: threading.Event,
    reporter: SolveReporter | None = None,
) -> SolveResult:
    """Search product index layers with the measured blind-solver settings."""
    result = solve_blind(
        detections,
        layers,
        catalog,
        pixel_scale_arcsec=pixel_scale_arcsec,
        config=BlindSolverConfig(),
        max_seconds=max(0.0, deadline - time.perf_counter()),
        hint_ra=near[0] if near is not None else None,
        hint_dec=near[1] if near is not None else None,
        hint_radius_deg=2.0,
        quad_detections=quad_detections,
        deadline=deadline,
        cancel=cancel,
        reporter=reporter,
    )
    if result.solved:
        result.scale_stage = "known" if pixel_scale_arcsec is not None else "unknown"
    return result
