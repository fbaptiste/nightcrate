"""Shared test fixtures."""

from pathlib import Path

import aiosqlite
import numpy as np
import pytest
from astropy.io import fits


@pytest.fixture(autouse=True)
async def _test_db(tmp_path: Path, monkeypatch):
    """Point the database at a temp file and create the settings table for all tests."""
    test_db = tmp_path / "test.db"
    monkeypatch.setattr("nightcrate.db.session.DB_PATH", test_db)
    monkeypatch.setattr("nightcrate.db.session.APP_DIR", tmp_path)

    async with aiosqlite.connect(test_db) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                data TEXT NOT NULL DEFAULT '{}'
            )
        """)
        await conn.execute("INSERT OR IGNORE INTO settings (id, data) VALUES (1, '{}')")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS recent_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL UNIQUE,
                opened_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS aberration_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                hdu INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                image_width INTEGER NOT NULL,
                image_height INTEGER NOT NULL,
                settings_json TEXT NOT NULL,
                star_count INTEGER NOT NULL,
                median_fwhm REAL,
                median_hfr REAL,
                median_eccentricity REAL,
                UNIQUE(file_path, hdu, settings_json)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS aberration_stars (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_id INTEGER NOT NULL REFERENCES aberration_analysis(id) ON DELETE CASCADE,
                x REAL NOT NULL,
                y REAL NOT NULL,
                fwhm REAL NOT NULL,
                hfr REAL NOT NULL,
                eccentricity REAL NOT NULL,
                elongation_angle_deg REAL NOT NULL,
                peak_adu REAL NOT NULL,
                flux REAL NOT NULL,
                snr REAL NOT NULL,
                semi_major REAL NOT NULL,
                semi_minor REAL NOT NULL
            )
        """)
        await conn.commit()


@pytest.fixture
def tmp_fits_mono(tmp_path: Path) -> Path:
    """Create a minimal mono (uint16) FITS file and return its path."""
    # Simulate a typical astro sub: background ~1500, a few bright stars
    rng = np.random.default_rng(42)
    data = rng.integers(1400, 1600, size=(100, 120), dtype=np.uint16)
    # Add a "star" at (50, 60)
    data[48:53, 58:63] = 40000

    hdu = fits.PrimaryHDU(data)
    hdu.header["OBJECT"] = "TestTarget"
    hdu.header["EXPTIME"] = 300.0
    hdu.header["FILTER"] = "Ha"
    hdu.header["DATE-OBS"] = "2026-03-15T02:30:45"
    hdu.header["GAIN"] = 100
    hdu.header["CCD-TEMP"] = -10.0
    hdu.header["INSTRUME"] = "ZWO ASI2600MM Pro"

    path = tmp_path / "mono_test.fits"
    hdu.writeto(path, overwrite=True)
    return path


@pytest.fixture
def tmp_fits_color(tmp_path: Path) -> Path:
    """Create a minimal 3-channel (RGB, uint16) FITS file and return its path."""
    rng = np.random.default_rng(99)
    # Shape (3, H, W) — planar RGB
    data = rng.integers(1000, 2000, size=(3, 80, 100), dtype=np.uint16)
    # Make red channel brighter (higher median)
    data[0] += 500

    hdu = fits.PrimaryHDU(data)
    hdu.header["OBJECT"] = "ColorTarget"
    hdu.header["EXPTIME"] = 120.0
    hdu.header["FILTER"] = "RGB"

    path = tmp_path / "color_test.fits"
    hdu.writeto(path, overwrite=True)
    return path


@pytest.fixture
def tmp_fits_float32(tmp_path: Path) -> Path:
    """Create a float32 FITS file (already normalized 0–1)."""
    rng = np.random.default_rng(7)
    data = rng.uniform(0.01, 0.05, size=(60, 80)).astype(np.float32)
    data[25:35, 35:45] = 0.8  # bright region

    hdu = fits.PrimaryHDU(data)
    hdu.header["OBJECT"] = "FloatTarget"

    path = tmp_path / "float_test.fits"
    hdu.writeto(path, overwrite=True)
    return path


@pytest.fixture
def tmp_fits_no_image(tmp_path: Path) -> Path:
    """Create a FITS file with an empty primary HDU (no image data)."""
    hdu = fits.PrimaryHDU()
    path = tmp_path / "empty_test.fits"
    hdu.writeto(path, overwrite=True)
    return path


@pytest.fixture
def tmp_dir_with_fits(tmp_path: Path, tmp_fits_mono: Path) -> Path:
    """Create a directory tree with FITS files and subdirectories for browse tests."""
    import shutil

    sub = tmp_path / "subdir"
    sub.mkdir()
    hidden = tmp_path / ".hidden"
    hidden.mkdir()

    # Copy the mono fits into the dir
    shutil.copy(tmp_fits_mono, tmp_path / "image1.fits")
    shutil.copy(tmp_fits_mono, tmp_path / "image2.fit")
    # Non-FITS file should be excluded
    (tmp_path / "readme.txt").write_text("hello")
    # Hidden file should be excluded
    (tmp_path / ".secret.fits").write_text("nope")

    return tmp_path
