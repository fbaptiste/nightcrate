"""Unit tests for the 50 MGC FITS binary-table parser.

Each test builds a tiny FITS binary table at tmp_path via astropy and
feeds it through the parser. Exercises the filters the parser enforces:
PGC <= 0 sentinel, NaN / missing bestdist, optional error + method
columns, and the column-missing hard error path.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from nightcrate.catalog_loader.mgc50_parser import parse_50mgc_fits


def _write_fits(
    tmp_path: Path,
    *,
    pgc: list[int],
    bestdist: list[float],
    bestdist_error: list[float] | None = None,
    bestdist_method: list[str] | None = None,
) -> Path:
    """Write a minimal 50 MGC-shaped FITS file at tmp_path/catalog.fits."""
    cols = [
        fits.Column(name="pgc", format="J", array=np.asarray(pgc, dtype=np.int32)),
        fits.Column(name="bestdist", format="E", array=np.asarray(bestdist, dtype=np.float32)),
    ]
    if bestdist_error is not None:
        cols.append(
            fits.Column(
                name="bestdist_error",
                format="E",
                array=np.asarray(bestdist_error, dtype=np.float32),
            )
        )
    if bestdist_method is not None:
        cols.append(
            fits.Column(
                name="bestdist_method",
                format="16A",
                array=np.asarray(bestdist_method),
            )
        )
    hdu = fits.BinTableHDU.from_columns(cols)
    path = tmp_path / "catalog.fits"
    fits.HDUList([fits.PrimaryHDU(), hdu]).writeto(path, overwrite=True)
    return path


def test_parses_valid_row_with_all_four_fields(tmp_path: Path) -> None:
    path = _write_fits(
        tmp_path,
        pgc=[2557],
        bestdist=[0.77],
        bestdist_error=[0.05],
        bestdist_method=["HyperLeda"],
    )
    rows = list(parse_50mgc_fits(path))
    assert len(rows) == 1
    assert rows[0].pgc == 2557
    assert rows[0].best_dist_mpc == pytest.approx(0.77, abs=1e-5)
    assert rows[0].e_best_dist_mpc == pytest.approx(0.05, abs=1e-5)
    assert rows[0].f_best_dist == "HyperLeda"


def test_skips_non_positive_pgc(tmp_path: Path) -> None:
    """HyperLEDA encodes "no cross-reference" as PGC -1 (or 0)."""
    path = _write_fits(
        tmp_path,
        pgc=[-1, 0, 2557],
        bestdist=[5.0, 5.0, 0.77],
    )
    rows = list(parse_50mgc_fits(path))
    assert [r.pgc for r in rows] == [2557]


def test_skips_nan_bestdist(tmp_path: Path) -> None:
    path = _write_fits(
        tmp_path,
        pgc=[10266, 2557],
        bestdist=[float("nan"), 0.77],
    )
    rows = list(parse_50mgc_fits(path))
    assert [r.pgc for r in rows] == [2557]


def test_skips_non_positive_bestdist(tmp_path: Path) -> None:
    """Negative or zero bestdist is meaningless — drop silently."""
    path = _write_fits(
        tmp_path,
        pgc=[10266, 99999, 2557],
        bestdist=[-1.0, 0.0, 0.77],
    )
    rows = list(parse_50mgc_fits(path))
    assert [r.pgc for r in rows] == [2557]


def test_parses_multiple_valid_rows(tmp_path: Path) -> None:
    path = _write_fits(
        tmp_path,
        pgc=[2557, 26257, 10266],
        bestdist=[0.77, 0.50, 32.0],
        bestdist_method=["HyperLeda", "HyperLeda", "Karachentsev"],
    )
    rows = list(parse_50mgc_fits(path))
    assert [r.pgc for r in rows] == [2557, 26257, 10266]
    assert [round(r.best_dist_mpc, 3) for r in rows] == [0.77, 0.50, 32.0]
    assert [r.f_best_dist for r in rows] == ["HyperLeda", "HyperLeda", "Karachentsev"]


def test_optional_columns_missing_yield_none(tmp_path: Path) -> None:
    """Stripped FITS variants may omit bestdist_error / bestdist_method."""
    path = _write_fits(
        tmp_path,
        pgc=[2557],
        bestdist=[0.77],
        # No error or method columns
    )
    rows = list(parse_50mgc_fits(path))
    assert rows[0].e_best_dist_mpc is None
    assert rows[0].f_best_dist is None


def test_strips_trailing_whitespace_from_method_string(tmp_path: Path) -> None:
    """FITS ``nA`` columns pad strings to the declared width; we must strip."""
    path = _write_fits(
        tmp_path,
        pgc=[2557],
        bestdist=[0.77],
        bestdist_method=["CF3-Z"],  # Stored as 16A → padded to 16 chars
    )
    rows = list(parse_50mgc_fits(path))
    assert rows[0].f_best_dist == "CF3-Z"


def test_raises_on_missing_required_column(tmp_path: Path) -> None:
    """If bestdist is absent, the file is unusable — fail fast."""
    cols = [
        fits.Column(name="pgc", format="J", array=np.asarray([2557], dtype=np.int32)),
        fits.Column(name="objname", format="16A", array=np.asarray(["M31"])),
    ]
    hdu = fits.BinTableHDU.from_columns(cols)
    path = tmp_path / "catalog.fits"
    fits.HDUList([fits.PrimaryHDU(), hdu]).writeto(path, overwrite=True)

    with pytest.raises(ValueError, match="missing required column"):
        list(parse_50mgc_fits(path))


def test_empty_table_yields_no_rows(tmp_path: Path) -> None:
    path = _write_fits(tmp_path, pgc=[], bestdist=[])
    assert list(parse_50mgc_fits(path)) == []
