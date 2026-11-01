import numpy as np

from nightcrate.services.native_solver.extract import (
    ExtractionConfig,
    _mono_float32,
    _working_bin_factor,
    extract_array,
    extract_for_index,
)
from nightcrate.services.native_solver.geometry import world_to_pixel
from tests.native_solver.synthetic import make_case


def test_extract_rejects_hot_pixels_and_recovers_windowed_centroids():
    case = make_case(30, star_count=45)
    detections = extract_array(case.image)
    assert 40 <= len(detections) <= 48
    # Every true star should have a nearby extraction and hot pixels should not
    # create the twelve extra sources rendered by make_case.
    from scipy.spatial import cKDTree

    true_pixels, valid = world_to_pixel(case.truth, case.catalog.ra, case.catalog.dec)
    assert valid.all()
    distances, _ = cKDTree(detections.xy).query(true_pixels)
    assert np.percentile(distances, 95) < 0.2


def test_bayer_superpixels_map_centroids_back_to_full_resolution():
    case = make_case(31, bayer_mosaic=True, star_count=45)
    detections = extract_array(case.image, bayer_mosaic=True)
    assert detections.width == case.image.shape[1]
    assert detections.height == case.image.shape[0]
    from scipy.spatial import cKDTree

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

    from scipy.spatial import cKDTree

    included_distances, _ = cKDTree(included.xy).query(clipped)
    excluded_distances, _ = cKDTree(excluded.xy).query(clipped)
    assert np.max(included_distances) < 1.5
    assert np.count_nonzero(excluded_distances < 1.5) < len(clipped)


def test_index_extraction_reuses_the_inclusive_population():
    case = make_case(33, star_count=45)
    detections, quads = extract_for_index(case.image, bayer_mosaic=False)
    assert detections is quads
