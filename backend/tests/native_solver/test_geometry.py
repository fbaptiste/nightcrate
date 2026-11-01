import numpy as np
import pytest

from nightcrate.services.native_solver.geometry import (
    build_quads,
    fit_similarity,
    gnomonic_inverse,
    gnomonic_project,
)


@pytest.mark.parametrize("ra,dec", [(359.99, 0.0), (0.01, 89.9), (180.0, -89.9)])
def test_gnomonic_round_trip_at_wrap_and_poles(ra, dec):
    xy = np.array([[0.03, -0.02], [-0.01, 0.04]])
    sky_ra, sky_dec = gnomonic_inverse(xy, ra, dec)
    recovered, valid = gnomonic_project(sky_ra, sky_dec, ra, dec)
    assert valid.all()
    np.testing.assert_allclose(recovered, xy, atol=1e-10)


def test_quad_codes_survive_similarity_and_mirror_search():
    points = np.array([[0.0, 0.0], [10.0, 8.0], [3.0, 5.0], [6.0, 3.0]])
    matrix = np.array([[1.2, -0.7], [0.7, 1.2]])
    transformed = points @ matrix.T + [40.0, -12.0]
    source = build_quads(points, neighbour_count=3)
    target = build_quads(transformed, neighbour_count=3)
    mirrored_for_lookup = build_quads(transformed * [1.0, -1.0], neighbour_count=3)
    assert len(source) == len(target) == 1
    np.testing.assert_allclose(source.codes, target.codes, atol=1e-12)
    reflected = transformed * [-1.0, 1.0]
    reflected_lookup = build_quads(reflected * [1.0, -1.0], neighbour_count=3)
    assert any(
        np.allclose(source.codes[0], code, atol=1e-12)
        for code in np.vstack((mirrored_for_lookup.codes, reflected_lookup.codes))
    )


def test_similarity_fit_permits_negative_parity():
    source = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [2.0, 3.0]])
    matrix = np.array([[2.0, 0.0], [0.0, -2.0]])
    target = source @ matrix.T + [8.0, 4.0]
    fitted, offset, rms = fit_similarity(source, target)
    np.testing.assert_allclose(fitted, matrix, atol=1e-12)
    np.testing.assert_allclose(offset, [8.0, 4.0], atol=1e-12)
    assert rms < 1e-12
