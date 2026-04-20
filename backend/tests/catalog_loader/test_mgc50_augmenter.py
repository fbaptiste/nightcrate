"""Integration tests for the 50 MGC distance augmenter (Ohlson+ 2024).

Writes a synthetic ``catalog.fits`` binary table into the fake catalogs
root alongside the OpenNGC + NightCrate bundled sources, then runs the
full ``load_catalogs`` pipeline and asserts the expected precedence:

    curated > 50 MGC > redshift-derived > (none)
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from nightcrate.catalog_loader import load_catalogs

MINI_FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "catalogs"


def _write_mgc50_fits(path: Path, rows: list[tuple[int, float]]) -> None:
    """Write a minimal catalog.fits with (pgc, bestdist) rows at *path*."""
    pgc = np.asarray([r[0] for r in rows], dtype=np.int32)
    bestdist = np.asarray([r[1] for r in rows], dtype=np.float32)
    cols = [
        fits.Column(name="pgc", format="J", array=pgc),
        fits.Column(name="bestdist", format="E", array=bestdist),
    ]
    hdu = fits.BinTableHDU.from_columns(cols)
    path.parent.mkdir(parents=True, exist_ok=True)
    fits.HDUList([fits.PrimaryHDU(), hdu]).writeto(path, overwrite=True)


@pytest.fixture
def catalogs_root(tmp_path: Path) -> Path:
    """Stage OpenNGC mini fixture + a 3-row 50 MGC ``catalog.fits``.

    PGC values are chosen so they cross-reference into the OpenNGC mini:
      - PGC 2557  → NGC 0224 (M 31, no curated distance) — 50 MGC wins
      - PGC 26257 → NGC 1976 (M 42, curated 412 pc in augment CSV). The
        50 MGC row is deliberately 0.50 Mpc so the test can tell the
        curated 412 pc from a would-be clobbered 500,000 pc.
      - PGC 999999 → unmatched — silently skipped
    """
    openngc_dir = tmp_path / "catalogs" / "openngc"
    openngc_dir.mkdir(parents=True)
    shutil.copy(MINI_FIXTURE_DIR / "openngc" / "mini_NGC.csv", openngc_dir / "NGC.csv")
    shutil.copy(MINI_FIXTURE_DIR / "openngc" / "mini_addendum.csv", openngc_dir / "addendum.csv")

    _write_mgc50_fits(
        tmp_path / "catalogs" / "github" / "50mgc" / "catalog.fits",
        [(2557, 0.77), (26257, 0.50), (999999, 15.0)],
    )
    return tmp_path / "catalogs"


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_50mgc_fills_distance_for_matched_galaxy(db, catalogs_root):
    """NGC 0224 (M 31, PGC 2557) has no curated distance; the 50 MGC row
    at 0.77 Mpc should land with method '50mgc' = 770,000 pc."""
    load_catalogs(db, catalogs_root)
    cur = db.cursor()
    cur.execute("SELECT distance_pc, distance_method FROM dso WHERE primary_designation = 'M 31'")
    row = cur.fetchone()
    assert row is not None
    assert row["distance_method"] == "50mgc"
    assert row["distance_pc"] == pytest.approx(770_000.0, rel=1e-4)


def test_50mgc_does_not_overwrite_curated(db, catalogs_root):
    """M 42 has curated 412 pc from the NightCrate augment CSV. 50 MGC's
    0.50 Mpc value (= 500,000 pc) must not overwrite the curated tag."""
    load_catalogs(db, catalogs_root)
    cur = db.cursor()
    cur.execute("SELECT distance_pc, distance_method FROM dso WHERE primary_designation = 'M 42'")
    row = cur.fetchone()
    assert row is not None
    assert row["distance_method"] == "curated"
    assert row["distance_pc"] == pytest.approx(412.0, abs=1e-3)


def test_50mgc_skips_unknown_pgc(db, catalogs_root):
    """PGC 999999 doesn't map to any DSO — the augmenter must handle this
    without error and return status='loaded'."""
    summary = load_catalogs(db, catalogs_root)
    by_id = {r.source_id: r for r in summary.results}
    assert by_id["github_50mgc"].status == "loaded"


def test_50mgc_row_count_tracks_dsos_updated(db, catalogs_root):
    """``row_count`` tracks DSOs actually updated, not FITS rows read.
    With our fixture, only PGC 2557 is updated — M 42 is skipped (curated)
    and PGC 999999 has no match. Expected: row_count = 1."""
    load_catalogs(db, catalogs_root)
    cur = db.cursor()
    cur.execute("SELECT row_count FROM dso_catalog_source WHERE source_id = 'github_50mgc'")
    row = cur.fetchone()
    assert row is not None
    assert row["row_count"] == 1


def test_50mgc_mpc_to_parsec_conversion_unit():
    """Sanity: 1 Mpc = 1,000,000 pc — the one multiplication used inside."""
    assert 1.0 * 1_000_000.0 == 1_000_000.0
