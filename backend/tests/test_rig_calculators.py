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


# -- Guide Suitability ---------------------------------------------------------


def _compute_gs(**overrides):
    """Build a compute_guide_suitability call with Askar V guide-scope defaults."""
    from nightcrate.services.rig_calculators import compute_guide_suitability

    kwargs = dict(
        guide_scope_id=1,
        oag_id=None,
        guide_scope_focal_length_mm=208.0,
        telescope_effective_focal_length_mm=360.0,
        guide_pixel_size_um=2.4,
        guide_resolution_x=3096,
        guide_resolution_y=2080,
        main_pixel_size_um=3.76,
        main_focal_length_mm=360.0,
        guide_binning=1,
        centroid_accuracy_pixels=0.2,
    )
    kwargs.update(overrides)
    return compute_guide_suitability(**kwargs)


def test_guide_suitability_askar_v_default():
    """Spec §6.2 — Askar V guide-scope, default centroid, binning=1."""
    gs = _compute_gs()
    assert gs is not None
    assert gs.mode == "guide_scope"
    assert gs.guide_focal_length_mm == 208.0
    assert gs.guide_scale_arcsec_per_pixel == pytest.approx(2.380, abs=0.005)
    assert gs.unbinned_guide_scale_arcsec_per_pixel == pytest.approx(2.380, abs=0.005)
    assert gs.guide_fov_width_arcmin == pytest.approx(122.8, abs=1.0)
    assert gs.guide_fov_height_arcmin == pytest.approx(82.5, abs=1.0)
    assert gs.effective_guide_precision_arcsec == pytest.approx(0.476, abs=0.005)
    assert gs.g_ratio == pytest.approx(1.104, abs=0.005)
    assert gs.effective_error_main_pixels == pytest.approx(0.221, abs=0.005)
    assert gs.rating == "excellent"
    assert gs.rating_reason == "ratio"
    assert "differential flexure" in gs.caveat


def test_guide_suitability_c11_oag():
    """Spec §6.1 — C11 OAG mode, guide FL from main scope."""
    gs = _compute_gs(
        guide_scope_id=None,
        oag_id=1,
        guide_scope_focal_length_mm=None,
        telescope_effective_focal_length_mm=1960.0,
        main_pixel_size_um=3.76,
        main_focal_length_mm=1960.0,
    )
    assert gs is not None
    assert gs.mode == "oag"
    assert gs.guide_focal_length_mm == 1960.0
    assert gs.guide_scale_arcsec_per_pixel == pytest.approx(0.253, abs=0.002)
    assert gs.effective_error_main_pixels == pytest.approx(0.128, abs=0.005)
    assert gs.rating == "excellent"
    assert "off-axis" in gs.caveat


def test_guide_suitability_tiny_30mm_counter_example():
    """Spec §6.3 — 30mm f/4 mini scope + ASI 120MM on C11: both cap AND ratio fail."""
    gs = _compute_gs(
        guide_scope_focal_length_mm=120.0,
        telescope_effective_focal_length_mm=1960.0,
        guide_pixel_size_um=3.75,
        guide_resolution_x=1280,
        guide_resolution_y=960,
        main_pixel_size_um=3.76,
        main_focal_length_mm=1960.0,
    )
    assert gs is not None
    assert gs.guide_scale_arcsec_per_pixel == pytest.approx(6.446, abs=0.01)
    assert gs.effective_error_main_pixels == pytest.approx(3.255, abs=0.01)
    assert gs.rating == "poor"
    # Both fail — cap wins reason.
    assert gs.rating_reason == "scale_cap"


def test_guide_suitability_50mm_borderline():
    """Spec §6.4 — 50mm f/3.2 guide scope: fails ratio but passes cap."""
    gs = _compute_gs(
        guide_scope_focal_length_mm=160.0,
        telescope_effective_focal_length_mm=1960.0,
        guide_pixel_size_um=3.75,
        guide_resolution_x=1280,
        guide_resolution_y=960,
        main_pixel_size_um=3.76,
        main_focal_length_mm=1960.0,
    )
    assert gs is not None
    assert gs.guide_scale_arcsec_per_pixel == pytest.approx(4.834, abs=0.01)
    assert gs.effective_error_main_pixels == pytest.approx(2.442, abs=0.01)
    assert gs.rating == "poor"
    assert gs.rating_reason == "ratio"


def test_guide_suitability_binning_2x_askar_v():
    """Spec §6.5 — Askar V @ 2x2 binning: still excellent but reduced headroom."""
    gs = _compute_gs(guide_binning=2)
    assert gs is not None
    assert gs.guide_binning == 2
    assert gs.effective_guide_pixel_size_um == pytest.approx(4.8, abs=0.001)
    # Binned scale is 2x unbinned.
    assert gs.guide_scale_arcsec_per_pixel == pytest.approx(4.760, abs=0.01)
    assert gs.unbinned_guide_scale_arcsec_per_pixel == pytest.approx(2.380, abs=0.005)
    assert gs.g_ratio == pytest.approx(2.209, abs=0.01)
    assert gs.effective_error_main_pixels == pytest.approx(0.442, abs=0.01)
    assert gs.rating == "excellent"
    assert gs.rating_reason == "ratio"


def test_guide_suitability_binning_4x_triggers_scale_cap():
    """Spec §6.5 — Askar V @ 4x4 binning: unbinned passes but binned exceeds cap."""
    gs = _compute_gs(guide_binning=4)
    assert gs is not None
    assert gs.guide_scale_arcsec_per_pixel == pytest.approx(9.520, abs=0.02)
    # Even though ratio would compute, the cap forces "poor".
    assert gs.rating == "poor"
    assert gs.rating_reason == "scale_cap"


def test_guide_suitability_binning_fov_unchanged():
    """Binning must not affect FOV (physical sensor dims are the same)."""
    baseline = _compute_gs()
    assert baseline is not None
    for binning in (1, 2, 3, 4):
        gs = _compute_gs(guide_binning=binning)
        assert gs is not None
        assert gs.guide_fov_width_arcmin == pytest.approx(
            baseline.guide_fov_width_arcmin, abs=0.001
        )
        assert gs.guide_fov_height_arcmin == pytest.approx(
            baseline.guide_fov_height_arcmin, abs=0.001
        )


def test_guide_suitability_centroid_accuracy_scales_linearly():
    """Spec §6.6 — halving centroid halves effective precision and error."""
    gs_default = _compute_gs(centroid_accuracy_pixels=0.2)
    gs_tight = _compute_gs(centroid_accuracy_pixels=0.1)
    gs_loose = _compute_gs(centroid_accuracy_pixels=0.4)
    assert gs_default is not None and gs_tight is not None and gs_loose is not None
    # Effective precision scales with centroid accuracy.
    assert gs_tight.effective_guide_precision_arcsec == pytest.approx(
        gs_default.effective_guide_precision_arcsec / 2.0, abs=0.005
    )
    assert gs_loose.effective_guide_precision_arcsec == pytest.approx(
        gs_default.effective_guide_precision_arcsec * 2.0, abs=0.01
    )
    # g_ratio is centroid-invariant; only effective_error_main_pixels scales.
    assert gs_tight.g_ratio == pytest.approx(gs_default.g_ratio, abs=0.001)
    assert gs_loose.effective_error_main_pixels == pytest.approx(
        gs_default.effective_error_main_pixels * 2.0, abs=0.01
    )


def test_guide_suitability_combined_binning_and_centroid():
    """Spec §6.7 — binning=2 + centroid=0.3 drops Askar V from excellent to good."""
    gs = _compute_gs(guide_binning=2, centroid_accuracy_pixels=0.3)
    assert gs is not None
    assert gs.guide_scale_arcsec_per_pixel == pytest.approx(4.760, abs=0.01)
    assert gs.effective_guide_precision_arcsec == pytest.approx(1.428, abs=0.01)
    assert gs.effective_error_main_pixels == pytest.approx(0.663, abs=0.005)
    assert gs.rating == "good"


@pytest.mark.parametrize(
    "effective_error,expected_rating",
    [
        (0.5, "excellent"),
        (0.8, "good"),
        (1.1, "marginal"),
        (1.5, "poor"),
    ],
)
def test_guide_suitability_rating_bands(effective_error, expected_rating):
    """Directly exercise each rating band via computed effective error values."""
    # Synthesize inputs that produce the target effective_error_main_pixels.
    # centroid = 0.2 → g_ratio = effective_error / 0.2
    # Fix main_scale = 1.0 → guide_scale = g_ratio.
    target_g_ratio = effective_error / 0.2
    main_pixel_size = 3.76
    main_fl = (main_pixel_size / 1.0) * 206.265  # main_scale = 1.0"/px
    guide_scale_target = target_g_ratio  # since main_scale = 1.0
    guide_pixel_size = 2.4
    guide_fl = (guide_pixel_size / guide_scale_target) * 206.265

    gs = _compute_gs(
        guide_scope_focal_length_mm=guide_fl,
        guide_pixel_size_um=guide_pixel_size,
        main_pixel_size_um=main_pixel_size,
        main_focal_length_mm=main_fl,
    )
    assert gs is not None
    assert gs.effective_error_main_pixels == pytest.approx(effective_error, abs=0.001)
    assert gs.rating == expected_rating


def test_guide_suitability_no_guide_camera_returns_none():
    gs = _compute_gs(guide_pixel_size_um=None, guide_resolution_x=None, guide_resolution_y=None)
    assert gs is None


def test_guide_suitability_no_optical_path_returns_none():
    """Guide camera with no guide scope or OAG."""
    gs = _compute_gs(
        guide_scope_id=None,
        oag_id=None,
        guide_scope_focal_length_mm=None,
    )
    assert gs is None


def test_guide_suitability_missing_guide_scope_focal_length_returns_none():
    """Guide scope assigned but focal_length_mm is NULL."""
    gs = _compute_gs(guide_scope_focal_length_mm=None)
    assert gs is None


# -- Guiding Tolerance ---------------------------------------------------------


def test_guiding_tolerance_thresholds_at_binning_1():
    from nightcrate.services.rig_calculators import compute_guiding_tolerance

    gt = compute_guiding_tolerance(
        unbinned_main_scale_arcsec_per_pixel=1.0,
        image_binning=1,
        guide_suitability=None,
    )
    assert gt.main_scale_arcsec_per_pixel == pytest.approx(1.0)
    assert gt.tight_rms_arcsec == pytest.approx(0.5)
    assert gt.acceptable_rms_arcsec == pytest.approx(1.0)
    assert gt.noticeable_rms_arcsec == pytest.approx(1.5)
    assert gt.current_guide_precision_arcsec is None
    assert gt.guide_system_within_tight is None
    assert "Compare your measured" in gt.interpretation


def test_guiding_tolerance_doubles_at_binning_2():
    from nightcrate.services.rig_calculators import compute_guiding_tolerance

    gt = compute_guiding_tolerance(
        unbinned_main_scale_arcsec_per_pixel=1.0,
        image_binning=2,
        guide_suitability=None,
    )
    assert gt.tight_rms_arcsec == pytest.approx(1.0)
    assert gt.acceptable_rms_arcsec == pytest.approx(2.0)
    assert gt.image_binning == 2


def test_guiding_tolerance_within_tight_when_guide_is_precise():
    gs = _compute_gs()  # Askar V @ binning=1, precision ≈ 0.48"
    from nightcrate.services.rig_calculators import compute_guiding_tolerance

    # Use Askar V main scale ≈ 2.16"/px; tight = 1.08"; 0.48 is well within.
    gt = compute_guiding_tolerance(
        unbinned_main_scale_arcsec_per_pixel=2.155,
        image_binning=1,
        guide_suitability=gs,
    )
    assert gt.guide_system_within_tight is True
    assert gt.guide_system_within_acceptable is True
    assert gt.headroom_arcsec == pytest.approx(1.08 - 0.48, abs=0.05)
    assert "comfortably within" in gt.interpretation


def test_guiding_tolerance_exceeds_acceptable():
    """Contrived guide system precision well above the acceptable threshold."""
    from dataclasses import replace

    gs = _compute_gs()  # baseline Askar V, precision 0.48"
    # Swap in a much coarser precision to simulate a bad setup.
    bad = replace(gs, effective_guide_precision_arcsec=5.0)
    from nightcrate.services.rig_calculators import compute_guiding_tolerance

    gt = compute_guiding_tolerance(
        unbinned_main_scale_arcsec_per_pixel=2.155,  # acceptable = 2.16"
        image_binning=1,
        guide_suitability=bad,
    )
    assert gt.guide_system_within_tight is False
    assert gt.guide_system_within_acceptable is False
    assert "exceeds" in gt.interpretation


def test_guiding_tolerance_in_full_calc_dict():
    """compute_rig_calculators dict carries guiding_tolerance at the top level."""
    from nightcrate.services.rig_calculators import compute_rig_calculators

    result = compute_rig_calculators(
        pixel_size_um=3.76,
        focal_length_mm=360.0,
        focal_ratio=4.5,
        aperture_mm=80.0,
        resolution_x=6248,
        resolution_y=4176,
        sensor_width_mm=23.5,
        sensor_height_mm=15.7,
        image_circle_mm=None,
        seeing_fwhm_low=2.0,
        seeing_fwhm_high=4.0,
        seeing_source="default",
        image_binning=2,
    )
    gt = result["guiding_tolerance"]
    assert gt is not None
    assert gt["image_binning"] == 2
    # Unbinned main scale ≈ 2.155"/px, binned 2x = 4.31; tight = 2.155.
    assert gt["tight_rms_arcsec"] == pytest.approx(2.155, abs=0.01)


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
    # No guide camera → guide_suitability is None.
    assert result["guide_suitability"] is None


def test_full_calculators_c11_with_oag():
    """Guide suitability surfaces through the full calculator when guide data provided."""
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
        guide_scope_id=None,
        oag_id=1,
        guide_pixel_size_um=2.4,
        guide_focal_length_mm=None,  # OAG uses main FL
        guide_resolution_x=3096,
        guide_resolution_y=2080,
    )
    gs = result["guide_suitability"]
    assert gs is not None
    assert gs["mode"] == "oag"
    assert gs["rating"] == "excellent"
    assert gs["guide_focal_length_mm"] == 1960.0
