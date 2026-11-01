from __future__ import annotations

import dataclasses
import json
import threading

import numpy as np
import pytest
from astropy.io import fits
from scipy.ndimage import gaussian_filter
from scipy.spatial import cKDTree

from nightcrate.core import app_config
from nightcrate.services.native_solver import solve_image as solve_module
from nightcrate.services.native_solver.extract import extract_for_index
from nightcrate.services.native_solver.geometry import angular_separation_deg, world_to_pixel
from nightcrate.services.native_solver.models import NullSolveReporter, TanWCS
from nightcrate.services.star_catalog import handles, ranges, store
from nightcrate.services.star_catalog import index as catalog_index
from nightcrate.services.star_catalog.index import BandSpec, write_band
from tests.native_solver.synthetic import SyntheticCase, _render, make_case
from tests.star_catalog.conftest import SyntheticStar, write_siril_catalog


def _write_empty_layer(path, name: str, source_hash: str) -> None:
    metadata = {
        "format": catalog_index.INDEX_FORMAT,
        "version": catalog_index.INDEX_FORMAT_VERSION,
        "epoch": 2026.0,
        "source": {"uncompressed_sha256": source_hash},
        "band": ranges.LAYERS[name].__dict__,
        "counts": {"tiles": 0, "stars": 0, "quads": 0},
        "layout": {
            "tile_offset": catalog_index.HEADER_SIZE,
            "star_offset": catalog_index.HEADER_SIZE,
            "quad_offset": catalog_index.HEADER_SIZE,
        },
    }
    encoded = json.dumps(metadata).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        catalog_index.MAGIC
        + len(encoded).to_bytes(4, "little")
        + encoded
        + b"\0" * (catalog_index.HEADER_SIZE - 12 - len(encoded))
    )


def _install_real_assets(tmp_path, monkeypatch, case: SyntheticCase) -> None:
    handles.close_all()
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    path = write_siril_catalog(
        store.catalog_path(),
        [
            SyntheticStar(float(ra), float(dec), g=float(g))
            for ra, dec, g in zip(case.catalog.ra, case.catalog.dec, case.catalog.g, strict=True)
        ],
    )
    source = dataclasses.replace(
        store.SIRIL_SOURCE,
        uncompressed_size=path.stat().st_size,
        uncompressed_sha256="rendered-trial-catalog",
    )
    monkeypatch.setattr(store, "SIRIL_SOURCE", source)
    monkeypatch.setattr(catalog_index, "SIRIL_SOURCE", source)
    monkeypatch.setattr(solve_module, "SIRIL_SOURCE", source)
    (path.parent / "version.json").write_text(
        json.dumps(
            {
                "version": source.version,
                "source": "import",
                "installed_at": "2026-10-30T00:00:00+00:00",
                "uncompressed_sha256": source.uncompressed_sha256,
            }
        ),
        encoding="utf-8",
    )

    import astropy.units as u
    from astropy_healpix import HEALPix

    hp = HEALPix(nside=2**8, order="nested", frame="icrs")
    tile = int(hp.lonlat_to_healpix(case.truth.crval_ra * u.deg, case.truth.crval_dec * u.deg))
    write_band(
        ranges.layer_path("q008"),
        BandSpec("q008", 0.01, 1.0, 8, 100, 12),
        [(tile, case.catalog)],
        source_identity={"uncompressed_sha256": source.uncompressed_sha256},
    )
    for name in ("q016", "q032", "q064", "q128", "q256"):
        _write_empty_layer(ranges.layer_path(name), name, source.uncompressed_sha256)
    ranges.write_manifest({"0.4-10"})


def _stretched_clipped(case: SyntheticCase) -> tuple[np.ndarray, np.ndarray]:
    stretched = np.asarray(case.image, dtype=np.float64) ** 0.25
    stretched -= stretched.min()
    stretched /= stretched.max()
    brightest = np.argsort(-case.ideal_detections.flux, kind="stable")[:30]
    positions = case.ideal_detections.xy[brightest]
    third_brightest: list[float] = []
    for x, y in positions:
        xx, yy = int(round(x)), int(round(y))
        patch = stretched[yy - 2 : yy + 3, xx - 2 : xx + 3]
        third_brightest.append(float(np.partition(patch.ravel(), -3)[-3]))
    level = min(third_brightest)
    return np.minimum(stretched / level, 1.0).astype(np.float32), positions


def _write_fits(path, image: np.ndarray, truth: TanWCS) -> None:
    hdu = fits.PrimaryHDU(np.asarray(image, dtype=np.float32))
    hdu.header["RA"] = truth.crval_ra
    hdu.header["DEC"] = truth.crval_dec
    hdu.header["YPIXSZ"] = 3.76
    hdu.header["FOCALLEN"] = 206.265 * 3.76 / truth.scale_arcsec
    hdu.writeto(path)


def _solve(path):
    return solve_module.solve_image(
        str(path),
        0,
        ra_hint=None,
        dec_hint=None,
        fov_hint=None,
        cancel=threading.Event(),
        reporter=NullSolveReporter(),
    )


def _center_error_arcsec(result, truth: TanWCS) -> float:
    assert result.ra_deg is not None and result.dec_deg is not None
    return 3600.0 * angular_separation_deg(
        result.ra_deg, result.dec_deg, truth.crval_ra, truth.crval_dec
    )


def test_clipped_bright_stars_are_kept_for_verification():
    case = make_case(900, width=800, height=600, scale_arcsec=3.0, star_count=75)
    image, clipped_positions = _stretched_clipped(case)

    detections, quads = extract_for_index(image, bayer_mosaic=False, pixel_scale_arcsec=3.0)
    distances, _ = cKDTree(detections.xy).query(clipped_positions)

    assert detections is quads
    assert np.max(distances) < 1.5


def test_stretched_clipped_field_solves(tmp_path, monkeypatch):
    case = make_case(901, width=800, height=600, scale_arcsec=3.0, star_count=75)
    image, _ = _stretched_clipped(case)
    _install_real_assets(tmp_path, monkeypatch, case)
    path = tmp_path / "stretched-clipped.fits"
    _write_fits(path, image, case.truth)
    try:
        result = _solve(path)
        assert result.solved, result.error_message
        assert _center_error_arcsec(result, case.truth) < 2.0
    finally:
        handles.close_all()


def test_true_mirrored_and_clipped_controls_solve(tmp_path, monkeypatch):
    case = make_case(902, width=800, height=600, scale_arcsec=3.0, star_count=75)
    clipped, _ = _stretched_clipped(case)
    mirrored_truth = dataclasses.replace(
        case.truth,
        cd=case.truth.cd @ np.diag([-1.0, 1.0]),
    )
    controls = (
        ("true", case.image, case.truth),
        ("mirrored", np.fliplr(case.image), mirrored_truth),
        ("clipped", clipped, case.truth),
    )
    _install_real_assets(tmp_path, monkeypatch, case)
    try:
        for name, image, truth in controls:
            path = tmp_path / f"{name}.fits"
            _write_fits(path, image, truth)
            result = _solve(path)
            assert result.solved, f"{name}: {result.error_message}"
            assert _center_error_arcsec(result, truth) < 2.0
    finally:
        handles.close_all()


def _negative_anchor_pixels(case: SyntheticCase) -> np.ndarray:
    layer = handles.get_layers(["q008"])[0]
    quad = layer.quad_radec([0])[0]
    quad_pixels, valid = world_to_pixel(case.truth, quad["ra"], quad["dec"])
    assert valid.all()
    true_pixels, valid = world_to_pixel(case.truth, case.catalog.ra, case.catalog.dec)
    assert valid.all()
    anchors = list(quad_pixels)
    for pixel in true_pixels:
        if all(np.linalg.norm(pixel - existing) > 1.0 for existing in anchors):
            anchors.append(pixel)
        if len(anchors) == 11:
            break
    return np.asarray(anchors)


def _negative_images(case: SyntheticCase, anchors: np.ndarray) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(903)
    true_pixels, valid = world_to_pixel(case.truth, case.catalog.ra, case.catalog.dec)
    assert valid.all()
    random_points = np.column_stack(
        (
            rng.uniform(14, case.truth.width - 14, 70),
            rng.uniform(14, case.truth.height - 14, 70),
        )
    )
    points = np.vstack((anchors, random_points))
    flux = np.concatenate((np.linspace(0.9, 0.7, len(anchors)), rng.uniform(0.12, 0.65, 70)))
    random_dots = _render(
        rng, case.truth.width, case.truth.height, points, flux, hot_pixels=0
    ).astype(np.float32)

    impulses = np.zeros((case.truth.height, case.truth.width), dtype=np.float32)
    for (x, y), amplitude in zip(points, flux, strict=True):
        impulses[int(round(y)), int(round(x))] += amplitude
    nebula = gaussian_filter(impulses, sigma=2.5)
    nebula /= nebula.max()
    nebula += rng.normal(0.02, 0.002, nebula.shape).astype(np.float32)
    nebula = np.clip(nebula, 0.0, 1.0)

    displaced = true_pixels[:75].copy()
    angles = rng.uniform(0.0, 2.0 * np.pi, len(displaced))
    radii = rng.uniform(20.0, 60.0, len(displaced))
    displaced += np.column_stack((np.cos(angles), np.sin(angles))) * radii[:, None]
    displaced[:, 0] = np.clip(displaced[:, 0], 14, case.truth.width - 14)
    displaced[:, 1] = np.clip(displaced[:, 1], 14, case.truth.height - 14)
    displaced = np.vstack((anchors, displaced))
    displaced_flux = np.concatenate(
        (np.linspace(0.9, 0.7, len(anchors)), np.linspace(0.65, 0.12, 75))
    )
    rng.shuffle(displaced_flux[len(anchors) :])
    displaced_catalog = _render(
        rng,
        case.truth.width,
        case.truth.height,
        displaced,
        displaced_flux,
        hot_pixels=0,
    ).astype(np.float32)

    clipped_decoy = random_dots.copy()
    for x, y in anchors:
        xx, yy = int(round(x)), int(round(y))
        clipped_decoy[yy - 1 : yy + 2, xx - 1 : xx + 2] = 1.0
    return {
        "random-dots": random_dots,
        "nebula-only": nebula,
        "displaced-catalog": displaced_catalog,
        "clipped-decoy": clipped_decoy,
    }


@pytest.mark.parametrize(
    "name", ("random-dots", "nebula-only", "displaced-catalog", "clipped-decoy")
)
def test_rendered_negative_reaches_full_verification(name, tmp_path, monkeypatch):
    case = make_case(903, width=800, height=600, scale_arcsec=3.0, star_count=75)
    _install_real_assets(tmp_path, monkeypatch, case)
    image = _negative_images(case, _negative_anchor_pixels(case))[name]
    outcomes = []
    search_index = solve_module.search_index

    def capture_outcome(*args, **kwargs):
        outcome = search_index(*args, **kwargs)
        outcomes.append(outcome)
        return outcome

    monkeypatch.setattr(solve_module, "search_index", capture_outcome)
    path = tmp_path / f"{name}.fits"
    _write_fits(path, image, case.truth)
    try:
        result = _solve(path)
        assert not result.solved, f"negative trial {name} produced a solution"
        assert sum(outcome.rejection_counts["full_verified"] for outcome in outcomes) > 0
    finally:
        handles.close_all()


def test_pure_noise_reports_too_few_stars(tmp_path, monkeypatch):
    case = make_case(904, width=800, height=600, scale_arcsec=3.0, star_count=75)
    rng = np.random.default_rng(904)
    noise = rng.normal(0.025, 0.003, (case.truth.height, case.truth.width)).astype(np.float32)
    _install_real_assets(tmp_path, monkeypatch, case)
    path = tmp_path / "noise.fits"
    _write_fits(path, noise, case.truth)
    try:
        result = _solve(path)
        assert not result.solved
        assert result.failure_reason == "too_few_stars"
        assert any(attempt.outcome == "too_few_stars" for attempt in result.attempts)
    finally:
        handles.close_all()


def test_seeded_true_field_recovery_floor(tmp_path, monkeypatch):
    solved = 0
    for offset, seed in enumerate(range(910, 920)):
        case = make_case(seed, width=800, height=600, scale_arcsec=3.0, star_count=75)
        directory = tmp_path / str(offset)
        directory.mkdir()
        _install_real_assets(directory, monkeypatch, case)
        path = directory / "field.fits"
        _write_fits(path, case.image, case.truth)
        try:
            result = _solve(path)
            if result.solved:
                assert _center_error_arcsec(result, case.truth) < 2.0
                solved += 1
        finally:
            handles.close_all()
    assert solved >= 9
