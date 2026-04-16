"""Tests for rig optical calculator formulas.

Pinned regression tests using Fred's actual equipment values.
"""

import pytest

# -- Image Scale ---------------------------------------------------------------


def test_image_scale_c11():
    from nightcrate.services.rig_calculators import compute_image_scale

    # C11 + 0.7x reducer: 3.76um / 1960mm x 206.265 = 0.396"/px
    result = compute_image_scale(pixel_size_um=3.76, focal_length_mm=1960.0)
    assert result == pytest.approx(0.396, abs=0.001)


def test_image_scale_askar_v():
    from nightcrate.services.rig_calculators import compute_image_scale

    # Askar V native: 3.76um / 360mm x 206.265 = 2.155"/px
    result = compute_image_scale(pixel_size_um=3.76, focal_length_mm=360.0)
    assert result == pytest.approx(2.155, abs=0.001)


def test_image_scale_binned():
    from nightcrate.services.rig_calculators import compute_image_scale_binned

    base_scale = 0.396
    binned = compute_image_scale_binned(base_scale)
    assert binned[1] == pytest.approx(0.396, abs=0.001)
    assert binned[2] == pytest.approx(0.792, abs=0.001)
    assert binned[3] == pytest.approx(1.188, abs=0.001)
    assert binned[4] == pytest.approx(1.584, abs=0.001)


# -- Field of View -------------------------------------------------------------


def test_fov_arctan_c11():
    from nightcrate.services.rig_calculators import compute_fov

    # C11 with physical sensor: 23.5mm x 15.7mm, FL 1960mm
    width_deg, height_deg = compute_fov(
        focal_length_mm=1960.0,
        sensor_width_mm=23.5,
        sensor_height_mm=15.7,
        resolution_x=6248,
        resolution_y=4176,
        pixel_size_um=3.76,
    )
    assert width_deg == pytest.approx(0.688, abs=0.002)
    assert height_deg == pytest.approx(0.459, abs=0.002)


def test_fov_arctan_askar_v():
    from nightcrate.services.rig_calculators import compute_fov

    width_deg, height_deg = compute_fov(
        focal_length_mm=360.0,
        sensor_width_mm=23.5,
        sensor_height_mm=15.7,
        resolution_x=6248,
        resolution_y=4176,
        pixel_size_um=3.76,
    )
    assert width_deg == pytest.approx(3.738, abs=0.005)
    assert height_deg == pytest.approx(2.498, abs=0.005)


def test_fov_pixel_fallback():
    """When physical sensor dims are missing, use pixel count x pixel size."""
    from nightcrate.services.rig_calculators import compute_fov

    width_deg, height_deg = compute_fov(
        focal_length_mm=1960.0,
        sensor_width_mm=None,
        sensor_height_mm=None,
        resolution_x=6248,
        resolution_y=4176,
        pixel_size_um=3.76,
    )
    assert width_deg == pytest.approx(0.688, abs=0.005)


# -- Resolution Limits ---------------------------------------------------------


def test_dawes_limit_c11():
    from nightcrate.services.rig_calculators import compute_resolution_limits

    dawes, rayleigh, max_mag = compute_resolution_limits(aperture_mm=280.0)
    assert dawes == pytest.approx(0.414, abs=0.001)
    assert rayleigh == pytest.approx(0.493, abs=0.001)
    assert max_mag == pytest.approx(560.0)


def test_dawes_limit_askar_v():
    from nightcrate.services.rig_calculators import compute_resolution_limits

    dawes, rayleigh, max_mag = compute_resolution_limits(aperture_mm=60.0)
    assert dawes == pytest.approx(1.933, abs=0.001)
    assert rayleigh == pytest.approx(2.300, abs=0.001)
    assert max_mag == pytest.approx(120.0)


# -- Sensor Coverage -----------------------------------------------------------


def test_sensor_diagonal():
    from nightcrate.services.rig_calculators import compute_sensor_diagonal

    diag = compute_sensor_diagonal(sensor_width_mm=23.5, sensor_height_mm=15.7)
    assert diag == pytest.approx(28.26, abs=0.01)


def test_sensor_diagonal_from_pixels():
    from nightcrate.services.rig_calculators import compute_sensor_diagonal

    diag = compute_sensor_diagonal(
        sensor_width_mm=None,
        sensor_height_mm=None,
        resolution_x=6248,
        resolution_y=4176,
        pixel_size_um=3.76,
    )
    assert diag == pytest.approx(28.26, abs=0.05)


def test_sensor_coverage():
    from nightcrate.services.rig_calculators import compute_sensor_coverage

    pct = compute_sensor_coverage(sensor_diagonal_mm=28.26, image_circle_mm=32.0)
    assert pct == pytest.approx(88.3, abs=0.5)


def test_sensor_coverage_vignetting():
    from nightcrate.services.rig_calculators import compute_sensor_coverage

    pct = compute_sensor_coverage(sensor_diagonal_mm=28.26, image_circle_mm=20.0)
    assert pct > 100


# -- Sampling Assessment -------------------------------------------------------


def test_sampling_c11_oversampled():
    from nightcrate.services.rig_calculators import assess_sampling

    result = assess_sampling(image_scale=0.396, seeing_fwhm_low=2.0, seeing_fwhm_high=4.0)
    assert result.assessment == "oversampled"
    assert result.ideal_range_low == pytest.approx(0.667, abs=0.01)
    assert result.ideal_range_high == pytest.approx(2.0, abs=0.01)
    assert result.binning_recommendations[1] == "oversampled"
    assert result.binning_recommendations[2] == "well_sampled"
    assert result.binning_recommendations[3] == "well_sampled"


def test_sampling_askar_v_undersampled():
    from nightcrate.services.rig_calculators import assess_sampling

    result = assess_sampling(image_scale=2.155, seeing_fwhm_low=2.0, seeing_fwhm_high=4.0)
    assert result.assessment == "undersampled"
    assert result.binning_recommendations[2] == "undersampled"


def test_sampling_well_sampled():
    from nightcrate.services.rig_calculators import assess_sampling

    result = assess_sampling(image_scale=1.0, seeing_fwhm_low=2.0, seeing_fwhm_high=4.0)
    assert result.assessment == "well_sampled"


# -- Seeing Resolution ---------------------------------------------------------


def test_resolve_seeing_override():
    from nightcrate.services.rig_calculators import resolve_seeing

    low, high, source, name = resolve_seeing(
        location_seeing_low=2.0,
        location_seeing_high=4.0,
        location_name="Backyard",
        override_low=1.0,
        override_high=2.0,
    )
    assert low == 1.0
    assert high == 2.0
    assert source == "override"
    assert name is None


def test_resolve_seeing_location():
    from nightcrate.services.rig_calculators import resolve_seeing

    low, high, source, name = resolve_seeing(
        location_seeing_low=2.0,
        location_seeing_high=4.0,
        location_name="Backyard Observatory",
    )
    assert low == 2.0
    assert high == 4.0
    assert source == "location"
    assert name == "Backyard Observatory"


def test_resolve_seeing_location_single_value():
    from nightcrate.services.rig_calculators import resolve_seeing

    low, high, source, name = resolve_seeing(
        location_seeing_low=2.5,
        location_seeing_high=None,
        location_name="Backyard",
    )
    assert low == 2.5
    assert high == 2.5
    assert source == "location"


def test_resolve_seeing_default():
    from nightcrate.services.rig_calculators import resolve_seeing

    low, high, source, name = resolve_seeing(
        location_seeing_low=None,
        location_seeing_high=None,
        location_name=None,
    )
    assert low == 2.0
    assert high == 4.0
    assert source == "default"
    assert name is None


# -- Guide System --------------------------------------------------------------


def test_guide_calculations_askar_v():
    from nightcrate.services.rig_calculators import compute_guide_metrics

    scale, fov = compute_guide_metrics(
        guide_pixel_size_um=2.4,
        guide_focal_length_mm=208.0,
        guide_resolution_x=3096,
        guide_resolution_y=2080,
    )
    assert scale == pytest.approx(2.380, abs=0.005)
    assert fov[0] == pytest.approx(122.8, abs=1.0)
    assert fov[1] == pytest.approx(82.5, abs=1.0)


def test_guide_calculations_null_focal_length():
    from nightcrate.services.rig_calculators import compute_guide_metrics

    result = compute_guide_metrics(
        guide_pixel_size_um=2.4,
        guide_focal_length_mm=None,
        guide_resolution_x=3096,
        guide_resolution_y=2080,
    )
    assert result is None


# -- Full Calculator -----------------------------------------------------------


def test_full_calculators_c11():
    from nightcrate.services.rig_calculators import compute_rig_calculators

    result = compute_rig_calculators(
        pixel_size_um=3.76,
        focal_length_mm=1960.0,
        focal_ratio=7.0,
        aperture_mm=280.0,
        resolution_x=6248,
        resolution_y=4176,
        sensor_width_mm=23.5,
        sensor_height_mm=15.7,
        image_circle_mm=None,
        seeing_fwhm_low=2.0,
        seeing_fwhm_high=4.0,
        seeing_source="location",
        seeing_location_name="Backyard Observatory",
    )
    assert result["image_scale_arcsec_per_pixel"] == pytest.approx(0.396, abs=0.001)
    assert result["field_of_view_deg"][0] == pytest.approx(0.688, abs=0.002)
    assert result["dawes_limit_arcsec"] == pytest.approx(0.414, abs=0.001)
    assert result["sampling_assessment"]["assessment"] == "oversampled"
