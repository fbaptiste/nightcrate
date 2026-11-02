from __future__ import annotations

import dataclasses
import threading
import time

import astropy.units as u
import numpy as np
from astropy_healpix import HEALPix

from nightcrate.services.native_solver import index_search, verify
from nightcrate.services.native_solver.extract import ExtractionConfig
from nightcrate.services.native_solver.geometry import gnomonic_inverse, gnomonic_project
from nightcrate.services.native_solver.index_search import search_index
from nightcrate.services.native_solver.models import (
    BlindSolverConfig,
    DetectedStars,
    SolverConfig,
    StarCatalog,
)
from nightcrate.services.native_solver.verify import solve_hinted
from nightcrate.services.star_catalog.index import BandSpec, IndexLayer, write_band
from nightcrate.services.star_catalog.siril import SirilCatalog
from tests.native_solver.synthetic import make_case
from tests.native_solver.test_index_search import _assets
from tests.star_catalog.conftest import SyntheticStar, write_siril_catalog


def test_random_dots_never_solve(tmp_path):
    case, layer_path, catalog_path = _assets(tmp_path)
    rng = np.random.default_rng(2200)
    with IndexLayer(layer_path) as layer, SirilCatalog(catalog_path) as catalog:
        for _ in range(50):
            count = 50
            dots = DetectedStars(
                rng.uniform(0, case.truth.width - 1, count),
                rng.uniform(0, case.truth.height - 1, count),
                rng.uniform(1, 10, count),
                np.full(count, 3.0),
                case.truth.width,
                case.truth.height,
            )
            near = solve_hinted(
                dots,
                case.catalog,
                hint_ra=case.truth.crval_ra,
                hint_dec=case.truth.crval_dec,
                pixel_scale_arcsec=case.truth.scale_arcsec,
                config=SolverConfig(max_solve_seconds=0.05),
                cancel=threading.Event(),
            )
            blind = search_index(
                dots,
                dots,
                [layer],
                catalog,
                pixel_scale_arcsec=case.truth.scale_arcsec,
                near=None,
                deadline=time.perf_counter() + 0.05,
                cancel=threading.Event(),
            )
            assert not near.solved
            assert not blind.solved
            assert near.log_odds < SolverConfig().log_odds_threshold
            assert blind.log_odds < BlindSolverConfig().log_odds_threshold


def test_ambiguous_pattern_refused(tmp_path, monkeypatch):
    case = make_case(602, ra=100.0, dec=20.0, scale_arcsec=2.0, render_image=False)
    tangent, valid = gnomonic_project(
        case.catalog.ra,
        case.catalog.dec,
        case.truth.crval_ra,
        case.truth.crval_dec,
    )
    assert np.all(valid)
    duplicate_ra, duplicate_dec = gnomonic_inverse(tangent, 130.0, 20.0)
    duplicate = StarCatalog(duplicate_ra, duplicate_dec, case.catalog.g.copy())
    hp = HEALPix(nside=2**8, order="nested", frame="icrs")
    first_tile = int(hp.lonlat_to_healpix(100.0 * u.deg, 20.0 * u.deg))
    second_tile = int(hp.lonlat_to_healpix(130.0 * u.deg, 20.0 * u.deg))
    layer_path = tmp_path / "ambiguous.ncidx"
    write_band(
        layer_path,
        BandSpec("ambiguous", 0.01, 1.0, 8, 100, 12),
        [(first_tile, case.catalog), (second_tile, duplicate)],
        source_identity={"kind": "test"},
    )
    combined = StarCatalog(
        np.concatenate((case.catalog.ra, duplicate.ra)),
        np.concatenate((case.catalog.dec, duplicate.dec)),
        np.concatenate((case.catalog.g, duplicate.g)),
    )
    catalog_path = write_siril_catalog(
        tmp_path / "ambiguous.dat",
        [
            SyntheticStar(float(ra), float(dec), g=float(g))
            for ra, dec, g in zip(combined.ra, combined.dec, combined.g, strict=True)
        ],
    )
    deadline = time.perf_counter() + 10
    expired = False
    real_clock = time.perf_counter
    original_distance = index_search._solution_grid_median_px

    def clock():
        return deadline + 1 if expired else real_clock()

    def distance(*args, **kwargs):
        nonlocal expired
        result = original_distance(*args, **kwargs)
        expired = True
        return result

    monkeypatch.setattr(index_search.time, "perf_counter", clock)
    monkeypatch.setattr(index_search, "_solution_grid_median_px", distance)
    with IndexLayer(layer_path) as layer, SirilCatalog(catalog_path) as catalog:
        result = search_index(
            case.ideal_detections,
            case.ideal_detections,
            [layer],
            catalog,
            pixel_scale_arcsec=None,
            near=None,
            deadline=deadline,
            cancel=threading.Event(),
        )
    assert result.status == "ambiguous"
    assert result.wcs is None


def test_completed_index_scan_after_expiry_is_solved(tmp_path, monkeypatch):
    case, layer_path, catalog_path = _assets(tmp_path, seed=603)
    deadline = time.perf_counter() + 10
    expired = False
    real_clock = time.perf_counter
    original_rank = index_search._rank_candidates
    original_refine = index_search._refine

    def clock():
        return deadline + 1 if expired else real_clock()

    def rank(candidates):
        return original_rank(candidates)[:1]

    def refine(*args, **kwargs):
        nonlocal expired
        result = original_refine(*args, **kwargs)
        expired = True
        return result

    monkeypatch.setattr(index_search.time, "perf_counter", clock)
    monkeypatch.setattr(index_search, "_rank_candidates", rank)
    monkeypatch.setattr(index_search, "_refine", refine)
    with IndexLayer(layer_path) as layer, SirilCatalog(catalog_path) as catalog:
        result = search_index(
            case.ideal_detections,
            case.ideal_detections,
            [layer],
            catalog,
            pixel_scale_arcsec=None,
            near=None,
            deadline=deadline,
            cancel=threading.Event(),
        )

    assert result.status == "solved"
    assert result.wcs is not None


def test_completed_near_scan_after_expiry_is_solved(monkeypatch):
    case = make_case(604, scale_arcsec=2.0, render_image=False)
    deadline = time.perf_counter() + 10
    expired = False
    real_clock = time.perf_counter
    original_refine = verify._refine

    def clock():
        return deadline + 1 if expired else real_clock()

    def refine(*args, **kwargs):
        nonlocal expired
        result = original_refine(*args, **kwargs)
        expired = True
        return result

    monkeypatch.setattr(verify.time, "perf_counter", clock)
    monkeypatch.setattr(verify, "_refine", refine)
    result = solve_hinted(
        case.ideal_detections,
        case.catalog,
        hint_ra=case.truth.crval_ra,
        hint_dec=case.truth.crval_dec,
        pixel_scale_arcsec=2.0,
        config=dataclasses.replace(SolverConfig(), max_code_matches=1),
        deadline=deadline,
        cancel=threading.Event(),
    )

    assert result.status == "solved"
    assert result.wcs is not None


def test_deadline_after_first_acceptance_not_solved(tmp_path, monkeypatch):
    case = make_case(701, scale_arcsec=2.0, render_image=False)
    deadline = time.perf_counter() + 10
    expired = False
    real_clock = time.perf_counter
    original_refine = verify._refine

    def clock():
        return deadline + 1 if expired else real_clock()

    def refine(*args, **kwargs):
        nonlocal expired
        result = original_refine(*args, **kwargs)
        expired = True
        return result

    monkeypatch.setattr(verify.time, "perf_counter", clock)
    monkeypatch.setattr(verify, "_refine", refine)
    near = solve_hinted(
        case.ideal_detections,
        case.catalog,
        hint_ra=case.truth.crval_ra,
        hint_dec=case.truth.crval_dec,
        pixel_scale_arcsec=2.0,
        deadline=deadline,
        cancel=threading.Event(),
    )
    assert near.status == "time_limit"
    assert near.wcs is None

    monkeypatch.undo()
    case, layer_path, catalog_path = _assets(tmp_path, seed=702)
    deadline = time.perf_counter() + 10
    expired = False
    original_refine = index_search._refine

    def index_clock():
        return deadline + 1 if expired else real_clock()

    def index_refine(*args, **kwargs):
        nonlocal expired
        result = original_refine(*args, **kwargs)
        expired = True
        return result

    monkeypatch.setattr(index_search.time, "perf_counter", index_clock)
    monkeypatch.setattr(index_search, "_refine", index_refine)
    with IndexLayer(layer_path) as layer, SirilCatalog(catalog_path) as catalog:
        blind = search_index(
            case.ideal_detections,
            case.ideal_detections,
            [layer],
            catalog,
            pixel_scale_arcsec=None,
            near=None,
            deadline=deadline,
            cancel=threading.Event(),
        )
    assert blind.status == "time_limit"
    assert blind.wcs is None


def test_cancel_during_ambiguity_scan_not_solved(tmp_path, monkeypatch):
    event = threading.Event()
    case = make_case(703, scale_arcsec=2.0, render_image=False)
    original_refine = verify._refine

    def refine(*args, **kwargs):
        result = original_refine(*args, **kwargs)
        event.set()
        return result

    monkeypatch.setattr(verify, "_refine", refine)
    result = solve_hinted(
        case.ideal_detections,
        case.catalog,
        hint_ra=case.truth.crval_ra,
        hint_dec=case.truth.crval_dec,
        pixel_scale_arcsec=2.0,
        cancel=event,
    )
    assert result.status == "cancelled"
    assert result.wcs is None


def test_cancel_stops_quickly():
    event = threading.Event()
    event.set()
    case = make_case(704, render_image=False)
    started = time.perf_counter()
    result = solve_hinted(
        case.ideal_detections,
        case.catalog,
        hint_ra=case.truth.crval_ra,
        hint_dec=case.truth.crval_dec,
        cancel=event,
    )
    assert result.status == "cancelled"
    assert time.perf_counter() - started < 0.5


def test_configs_match_prototype():
    assert ExtractionConfig().max_width_ratio == 6.0
    assert dataclasses.asdict(SolverConfig()) == {
        "code_tolerance": 0.025,
        "code_tolerance_min": 0.0025,
        "code_tolerance_max": 0.010,
        "depth_passes": (30, 60, 120, 240),
        "blind_max_stars": 80,
        "image_max_b_per_a": 4,
        "include_all_depth_pass": True,
        "quad_method": "diameter",
        "catalog_depth_multiple": 1.0,
        "initial_search_radius_deg": 0.5,
        "radius_growth": 2.0,
        "catalog_cell_overlap": True,
        "verification_catalog_ratio": 1.5,
        "image_quad_min_fraction": 0.08,
        "image_quad_max_fraction": 0.75,
        "max_image_quads": 4000,
        "max_catalog_quads_per_cell": 2000,
        "quad_interior_stars": 12,
        "quads_per_diameter": 8,
        "max_code_matches": 2000,
        "max_candidates": 300,
        "max_verify_per_layer": 48,
        "initial_match_radius_px": 4.0,
        "final_match_radius_px": 2.0,
        "position_sigma_px": 1.0,
        "true_match_probability": 0.75,
        "min_matches": 10,
        "min_quadrants": 3,
        "log_odds_threshold": float(np.log(1e18)),
        "max_axis_scale_ratio": 1.05,
        "max_axis_nonorthogonality_deg": 3.0,
        "scale_min_arcsec": 0.2,
        "scale_max_arcsec": 30.0,
        "scale_tolerance": 0.15,
        "max_solve_seconds": 20.0,
    }
    blind = dataclasses.asdict(BlindSolverConfig())
    expected = dataclasses.asdict(SolverConfig())
    expected.update(
        code_tolerance=0.010,
        depth_passes=(30, 60, 80),
        true_match_probability=0.65,
        min_matches=12,
        max_axis_nonorthogonality_deg=0.2,
        seed_match_radius_px=12.0,
    )
    assert blind == expected
