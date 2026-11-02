import numpy as np
from scipy.spatial import cKDTree

from nightcrate.services.native_solver.extract import (
    ExtractionConfig,
    _mono_float32,
    _working_bin_factor,
    extract_array,
    extract_for_index,
)
from nightcrate.services.native_solver.geometry import world_to_pixel
from tests.native_solver.synthetic import SyntheticCase, make_case


def _wide_blob_field(
    case: SyntheticCase,
    *,
    count: int = 24,
    sigma: float = 10.0,
) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(991)
    centers: list[np.ndarray] = []
    stars = case.ideal_detections.xy
    for _ in range(20_000):
        center = np.array(
            [
                rng.uniform(50, case.image.shape[1] - 50),
                rng.uniform(50, case.image.shape[0] - 50),
            ]
        )
        if np.min(np.linalg.norm(stars - center, axis=1)) < 45:
            continue
        if centers and np.min(np.linalg.norm(np.asarray(centers) - center, axis=1)) < 60:
            continue
        centers.append(center)
        if len(centers) == count:
            break
    assert len(centers) == count

    image = case.image.copy()
    radius = int(np.ceil(4 * sigma))
    for index, (x, y) in enumerate(centers):
        x0, y0 = int(np.floor(x)), int(np.floor(y))
        xs = np.arange(max(0, x0 - radius), min(image.shape[1], x0 + radius + 1))
        ys = np.arange(max(0, y0 - radius), min(image.shape[0], y0 + radius + 1))
        xx, yy = np.meshgrid(xs, ys)
        amplitude = 0.7 + 0.25 * index / max(count - 1, 1)
        image[np.ix_(ys, xs)] += amplitude * np.exp(
            -((xx - x) ** 2 + (yy - y) ** 2) / (2 * sigma**2)
        )
    return np.clip(image, 0.0, 1.0), np.asarray(centers)


def test_extract_rejects_hot_pixels_and_recovers_windowed_centroids():
    case = make_case(30, star_count=45)
    detections = extract_array(case.image)
    assert 40 <= len(detections) <= 48
    # Every true star should have a nearby extraction and hot pixels should not
    # create the twelve extra sources rendered by make_case.
    true_pixels, valid = world_to_pixel(case.truth, case.catalog.ra, case.catalog.dec)
    assert valid.all()
    distances, _ = cKDTree(detections.xy).query(true_pixels)
    assert np.percentile(distances, 95) < 0.2


def test_bayer_superpixels_map_centroids_back_to_full_resolution():
    case = make_case(31, bayer_mosaic=True, star_count=45)
    detections = extract_array(case.image, bayer_mosaic=True)
    assert detections.width == case.image.shape[1]
    assert detections.height == case.image.shape[0]
    distances, _ = cKDTree(detections.xy).query(case.ideal_detections.xy)
    assert np.percentile(distances, 90) < 0.8
    assert len(detections) >= 38


def test_scale_aware_working_resolution_stops_at_about_four_arcseconds():
    config = ExtractionConfig()
    assert (
        _working_bin_factor(
            4176,
            6248,
            bayer_mosaic=False,
            pixel_scale_arcsec=2.0,
            config=config,
        )
        == 2
    )
    assert (
        _working_bin_factor(
            4176,
            6248,
            bayer_mosaic=False,
            pixel_scale_arcsec=0.37,
            config=config,
        )
        == 4
    )
    assert (
        _working_bin_factor(
            4176,
            6248,
            bayer_mosaic=False,
            pixel_scale_arcsec=None,
            config=config,
        )
        == 2
    )


def test_color_extraction_averages_channels_without_float64_intermediate():
    rgb = np.zeros((4, 5, 3), dtype=np.float64)
    rgb[..., 0] = 1
    rgb[..., 1] = 2
    rgb[..., 2] = 3
    mono = _mono_float32(rgb)
    assert mono.dtype == np.float32
    np.testing.assert_array_equal(mono, 2)


def test_saturation_policy_defaults_to_include():
    assert ExtractionConfig().saturation == "include"


def test_saturation_policy_keeps_flat_topped_stars_when_included():
    case = make_case(32, star_count=45)
    image = case.image.copy()
    clipped = case.ideal_detections.xy[:10]
    for x, y in clipped:
        xx, yy = int(round(x)), int(round(y))
        image[yy - 1 : yy + 2, xx - 1 : xx + 2] = 1.0

    included = extract_array(image, config=ExtractionConfig(saturation="include"))
    excluded = extract_array(image, config=ExtractionConfig(saturation="exclude"))

    included_distances, _ = cKDTree(included.xy).query(clipped)
    excluded_distances, _ = cKDTree(excluded.xy).query(clipped)
    assert np.max(included_distances) < 1.5
    assert np.count_nonzero(excluded_distances < 1.5) < len(clipped)


def test_index_extraction_reuses_the_inclusive_population():
    case = make_case(33, star_count=45)
    detections, quads = extract_for_index(case.image, bayer_mosaic=False)
    assert detections is quads


def test_width_cut_rejects_wide_blobs_and_keeps_stars():
    case = make_case(34, width=800, height=600, scale_arcsec=3.0, star_count=75)
    image, blob_centers = _wide_blob_field(case)

    detections = extract_array(image)
    star_distances, _ = cKDTree(detections.xy).query(case.ideal_detections.xy)
    blob_distances, _ = cKDTree(detections.xy).query(blob_centers)

    assert len(detections) == len(case.ideal_detections)
    assert np.max(star_distances) < 1.5
    assert np.min(blob_distances) > 5.0


def test_width_cut_can_be_disabled():
    case = make_case(35, width=800, height=600, scale_arcsec=3.0, star_count=75)
    image, blob_centers = _wide_blob_field(case)

    detections = extract_array(image, config=ExtractionConfig(max_width_ratio=None))
    blob_distances, _ = cKDTree(detections.xy).query(blob_centers)

    assert len(detections) == len(case.ideal_detections) + len(blob_centers)
    assert np.max(blob_distances) < 2.0


def test_width_cut_preserves_star_only_count():
    case = make_case(36, width=800, height=600, scale_arcsec=3.0, star_count=75)

    filtered = extract_array(case.image)
    unfiltered = extract_array(case.image, config=ExtractionConfig(max_width_ratio=None))

    assert len(filtered) == len(unfiltered)


def test_width_cut_runs_before_brightest_selection():
    case = make_case(37, width=800, height=600, scale_arcsec=3.0, star_count=75)
    image, blob_centers = _wide_blob_field(case)
    star_tree = cKDTree(case.ideal_detections.xy)
    blob_tree = cKDTree(blob_centers)

    filtered = extract_array(image, config=ExtractionConfig(max_sources=75))
    unfiltered = extract_array(
        image,
        config=ExtractionConfig(max_sources=75, max_width_ratio=None),
    )
    filtered_star_distances, _ = star_tree.query(filtered.xy)
    filtered_blob_distances, _ = blob_tree.query(filtered.xy)
    unfiltered_star_distances, _ = star_tree.query(unfiltered.xy)
    unfiltered_blob_distances, _ = blob_tree.query(unfiltered.xy)

    # Selection pressure pins the width cut before _spatial_brightest.
    assert len(filtered) == 75
    assert np.max(filtered_star_distances) < 1.5
    assert np.min(filtered_blob_distances) > 5.0
    assert np.count_nonzero(unfiltered_blob_distances < 2.0) >= 1
    assert np.count_nonzero(unfiltered_star_distances < 1.5) < 75
