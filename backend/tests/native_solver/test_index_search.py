from __future__ import annotations

import threading
import time
from pathlib import Path

import astropy.units as u
import numpy as np
import pytest
from astropy_healpix import HEALPix

from nightcrate.services.native_solver.geometry import (
    angular_separation_deg,
    pixel_to_world,
    world_to_pixel,
)
from nightcrate.services.native_solver.index_search import search_index
from nightcrate.services.star_catalog.index import BandSpec, IndexLayer, write_band
from nightcrate.services.star_catalog.siril import SirilCatalog
from tests.native_solver.synthetic import make_case
from tests.star_catalog.conftest import SyntheticStar, write_siril_catalog


def _assets(tmp_path: Path, *, parity: int = 1, seed: int = 900):
    case = make_case(
        seed,
        ra=83.82,
        dec=-5.39,
        width=2400,
        height=1600,
        scale_arcsec=1.5,
        rotation_deg=30.0,
        parity=parity,
        star_count=75,
        render_image=False,
    )
    hp = HEALPix(nside=2**8, order="nested", frame="icrs")
    tile = int(hp.lonlat_to_healpix(case.truth.crval_ra * u.deg, case.truth.crval_dec * u.deg))
    layer_path = tmp_path / f"case-{parity}.ncidx"
    write_band(
        layer_path,
        BandSpec("test", 0.03, 1.2, 8, 100, 12),
        [(tile, case.catalog)],
        source_identity={"kind": "test", "checksum": "synthetic"},
    )
    catalog_path = write_siril_catalog(
        tmp_path / f"case-{parity}.dat",
        [
            SyntheticStar(float(ra), float(dec), g=float(g))
            for ra, dec, g in zip(case.catalog.ra, case.catalog.dec, case.catalog.g, strict=True)
        ],
    )
    return case, layer_path, catalog_path


@pytest.mark.parametrize("parity", [-1, 1])
def test_index_search_blind_solves(tmp_path, parity):
    case, layer_path, catalog_path = _assets(tmp_path, parity=parity, seed=900 + parity)
    with IndexLayer(layer_path) as layer, SirilCatalog(catalog_path) as catalog:
        result = search_index(
            case.ideal_detections,
            case.ideal_detections,
            [layer],
            catalog,
            pixel_scale_arcsec=None,
            near=None,
            deadline=time.perf_counter() + 10,
            cancel=threading.Event(),
        )
    assert result.solved, result.reason
    assert result.wcs is not None
    ra, dec = pixel_to_world(case.truth, np.array([[200.0, 300.0]]))
    recovered, valid = world_to_pixel(result.wcs, ra, dec)
    assert valid.all()
    assert np.linalg.norm(recovered[0] - [200.0, 300.0]) < 0.3
    assert (
        3600.0
        * angular_separation_deg(
            result.wcs.crval_ra,
            result.wcs.crval_dec,
            case.truth.crval_ra,
            case.truth.crval_dec,
        )
        < 1.0
    )
    assert abs(result.wcs.scale_arcsec / 1.5 - 1.0) < 0.001
    assert result.wcs.parity == parity


def test_index_search_wrong_scale_fails_then_unknown_solves(tmp_path):
    case, layer_path, catalog_path = _assets(tmp_path)
    with IndexLayer(layer_path) as layer, SirilCatalog(catalog_path) as catalog:
        wrong = search_index(
            case.ideal_detections,
            case.ideal_detections,
            [layer],
            catalog,
            pixel_scale_arcsec=3.0,
            near=None,
            deadline=time.perf_counter() + 10,
            cancel=threading.Event(),
        )
        unknown = search_index(
            case.ideal_detections,
            case.ideal_detections,
            [layer],
            catalog,
            pixel_scale_arcsec=None,
            near=None,
            deadline=time.perf_counter() + 10,
            cancel=threading.Event(),
        )
    assert not wrong.solved
    assert unknown.solved
    assert unknown.scale_stage == "unknown"


def test_index_search_near_restricts_to_radius(tmp_path):
    case, layer_path, catalog_path = _assets(tmp_path)
    with IndexLayer(layer_path) as layer, SirilCatalog(catalog_path) as catalog:
        close = search_index(
            case.ideal_detections,
            case.ideal_detections,
            [layer],
            catalog,
            pixel_scale_arcsec=1.5,
            near=(case.truth.crval_ra + 1.5, case.truth.crval_dec),
            deadline=time.perf_counter() + 10,
            cancel=threading.Event(),
        )
        far = search_index(
            case.ideal_detections,
            case.ideal_detections,
            [layer],
            catalog,
            pixel_scale_arcsec=1.5,
            near=(case.truth.crval_ra + 3.0, case.truth.crval_dec),
            deadline=time.perf_counter() + 10,
            cancel=threading.Event(),
        )
    assert close.solved
    assert not far.solved
