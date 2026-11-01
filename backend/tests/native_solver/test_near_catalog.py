from __future__ import annotations

import threading
import time

from nightcrate.services.native_solver.near_catalog import search_near_catalog
from nightcrate.services.star_catalog.siril import SirilCatalog
from tests.native_solver.synthetic import make_case
from tests.star_catalog.conftest import SyntheticStar, write_siril_catalog


def test_near_catalog_recovers_2x_scale(tmp_path):
    case = make_case(601, scale_arcsec=2.0, render_image=False)
    path = write_siril_catalog(
        tmp_path / "stars.dat",
        [
            SyntheticStar(float(ra), float(dec), g=float(g))
            for ra, dec, g in zip(case.catalog.ra, case.catalog.dec, case.catalog.g, strict=True)
        ],
    )
    with SirilCatalog(path) as catalog:
        result = search_near_catalog(
            case.ideal_detections,
            catalog,
            ra=case.truth.crval_ra,
            dec=case.truth.crval_dec,
            pixel_scale_arcsec=4.0,
            deadline=time.perf_counter() + 20,
            cancel=threading.Event(),
        )
    assert result.solved, result.reason
    assert result.scale_stage == "half"
