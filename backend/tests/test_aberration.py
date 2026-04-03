"""Tests for aberration analysis — star detection and sample grid aggregation."""

import numpy as np

from nightcrate.services.aberration import (
    AnalysisResult,
    DetectionSettings,
    SampleGridResult,
    compute_sample_grid,
    detect_stars,
)


def _make_star_field(
    width: int = 400,
    height: int = 400,
    stars: list[tuple[float, float, float, float]] | None = None,
    background: float = 0.02,
    noise_std: float = 0.002,
) -> np.ndarray:
    """Create a synthetic star field for testing.

    stars: list of (cx, cy, flux_peak, sigma) tuples.
    Returns float64 array in [0, 1] range, shape (height, width).
    """
    rng = np.random.default_rng(42)
    data = rng.normal(background, noise_std, (height, width)).clip(0, 1)
    if stars is None:
        stars = [
            (100, 100, 0.8, 3.0),
            (300, 100, 0.6, 4.0),
            (100, 300, 0.7, 3.5),
            (300, 300, 0.5, 5.0),
            (200, 200, 0.9, 3.0),
        ]
    for cx, cy, peak, sigma in stars:
        y, x = np.ogrid[0:height, 0:width]
        r2 = (x - cx) ** 2 + (y - cy) ** 2
        data += peak * np.exp(-r2 / (2 * sigma**2))
    return data.clip(0, 1).astype(np.float64)


class TestDetectStars:
    def test_finds_stars_in_synthetic_image(self):
        data = _make_star_field()
        result = detect_stars(data)
        assert isinstance(result, AnalysisResult)
        assert len(result.stars) == 5

    def test_star_positions_match_input(self):
        data = _make_star_field()
        result = detect_stars(data)
        positions = sorted([(s.x, s.y) for s in result.stars])
        expected = sorted([(100, 100), (200, 200), (300, 100), (100, 300), (300, 300)])
        for (ex, ey), (ax, ay) in zip(expected, positions):
            assert abs(ax - ex) < 5, f"Expected x≈{ex}, got {ax}"
            assert abs(ay - ey) < 5, f"Expected y≈{ey}, got {ay}"

    def test_star_metrics_reasonable(self):
        data = _make_star_field()
        result = detect_stars(data)
        for star in result.stars:
            assert star.fwhm > 0
            assert star.hfr > 0
            assert 0 <= star.eccentricity < 1
            assert 0 <= star.elongation_angle_deg < 180
            assert star.peak_adu > 0
            assert star.flux > 0
            assert star.snr > 0
            assert star.semi_major >= star.semi_minor > 0

    def test_global_stats_populated(self):
        data = _make_star_field()
        result = detect_stars(data)
        assert result.star_count == 5
        assert result.median_fwhm > 0
        assert result.median_hfr > 0
        assert 0 <= result.median_eccentricity < 1
        assert result.image_width == 400
        assert result.image_height == 400

    def test_edge_exclusion(self):
        data = _make_star_field(stars=[(5, 5, 0.8, 3.0), (200, 200, 0.8, 3.0)])
        result = detect_stars(data, DetectionSettings(edge_margin_px=20))
        assert len(result.stars) == 1
        assert abs(result.stars[0].x - 200) < 5

    def test_snr_filter(self):
        data = _make_star_field(
            stars=[
                (200, 200, 0.8, 3.0),
                (100, 100, 0.01, 3.0),
            ],
            noise_std=0.005,
        )
        result = detect_stars(data, DetectionSettings(min_star_snr=10.0))
        assert len(result.stars) >= 1
        assert all(s.snr >= 10.0 for s in result.stars)

    def test_extended_objects_filtered(self):
        """Objects with large semi-major axis should be rejected."""
        data = _make_star_field(
            stars=[
                (200, 200, 0.8, 3.0),
                (100, 100, 0.5, 20.0),
            ],
        )
        result = detect_stars(data, DetectionSettings(max_semi_major_px=10.0))
        assert all(s.semi_major <= 10.0 for s in result.stars)

    def test_empty_image_returns_no_stars(self):
        data = np.full((100, 100), 0.02, dtype=np.float64)
        result = detect_stars(data)
        assert len(result.stars) == 0
        assert result.star_count == 0


class TestComputeSampleGrid:
    def test_basic_grid(self):
        data = _make_star_field()
        analysis = detect_stars(data)
        grid = compute_sample_grid(analysis, samples_across=3)
        assert isinstance(grid, SampleGridResult)
        assert grid.samples_across == 3
        assert grid.cols == 3
        assert grid.rows >= 2
        assert len(grid.squares) == grid.rows * grid.cols

    def test_squares_have_image_coordinates(self):
        data = _make_star_field()
        analysis = detect_stars(data)
        grid = compute_sample_grid(analysis, samples_across=3)
        for sq in grid.squares:
            assert sq.x0 >= 0
            assert sq.y0 >= 0
            assert sq.x1 <= analysis.image_width
            assert sq.y1 <= analysis.image_height
            assert sq.x1 > sq.x0
            assert sq.y1 > sq.y0

    def test_squares_contain_star_counts(self):
        data = _make_star_field()
        analysis = detect_stars(data)
        grid = compute_sample_grid(analysis, samples_across=3)
        total = sum(sq.star_count for sq in grid.squares)
        assert total <= analysis.star_count

    def test_squares_with_stars_have_metrics(self):
        data = _make_star_field()
        analysis = detect_stars(data)
        grid = compute_sample_grid(analysis, samples_across=3)
        with_stars = [sq for sq in grid.squares if sq.star_count > 0]
        assert len(with_stars) > 0
        for sq in with_stars:
            assert sq.median_fwhm is not None
            assert sq.median_eccentricity is not None
            assert sq.median_hfr is not None
            assert len(sq.star_indices) == sq.star_count

    def test_empty_squares_have_none_metrics(self):
        data = _make_star_field()
        analysis = detect_stars(data)
        grid = compute_sample_grid(analysis, samples_across=7)
        empty = [sq for sq in grid.squares if sq.star_count == 0]
        assert len(empty) > 0
        for sq in empty:
            assert sq.median_fwhm is None
            assert sq.median_eccentricity is None
            assert len(sq.star_indices) == 0

    def test_different_sample_counts(self):
        data = _make_star_field()
        analysis = detect_stars(data)
        g3 = compute_sample_grid(analysis, samples_across=3)
        g5 = compute_sample_grid(analysis, samples_across=5)
        assert g3.cols == 3
        assert g5.cols == 5
        assert len(g5.squares) > len(g3.squares)

    def test_square_size_scales_with_image(self):
        small = _make_star_field(width=200, height=200, stars=[(100, 100, 0.8, 3.0)])
        large = _make_star_field(width=800, height=800, stars=[(400, 400, 0.8, 3.0)])
        g_small = compute_sample_grid(detect_stars(small), samples_across=3)
        g_large = compute_sample_grid(detect_stars(large), samples_across=3)
        assert g_large.square_size > g_small.square_size
