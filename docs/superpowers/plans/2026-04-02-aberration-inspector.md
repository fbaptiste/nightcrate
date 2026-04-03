# Aberration Inspector v0.5.0 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect and measure star shapes across an astronomical image, display results in a zoned crop grid that replaces N.I.N.A.'s basic aberration inspector.

**Architecture:** A `services/aberration.py` backend module uses `sep` for star detection and computes per-star metrics (FWHM, HFR, eccentricity, elongation angle). Zone aggregation groups stars into a configurable grid. Results are cached in SQLite tables with TTL. A new `api/aberration.py` router exposes analyze, zones, crop, and cache endpoints. The frontend adds an "Aberration" tab to the image viewer with a crop grid view and a context-dependent right sidebar showing global stats and zone details.

**Tech Stack:** Python (`sep`, `numpy`, `aiosqlite`), React/TypeScript (MUI, TanStack Query)

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `backend/src/nightcrate/services/aberration.py` | Star detection, metrics, zone aggregation |
| Create | `backend/src/nightcrate/api/aberration.py` | REST endpoints for analyze, zones, crop, cache |
| Create | `backend/src/nightcrate/db/migrations/0004.aberration_cache.sql` | DB tables for cached analysis results |
| Modify | `backend/src/nightcrate/main.py` | Register aberration router, startup cache cleanup |
| Modify | `backend/src/nightcrate/core/config.py` | Add `aberration_cache_ttl_days` setting |
| Create | `backend/tests/test_aberration.py` | Tests for star detection, zone aggregation |
| Create | `backend/tests/test_aberration_api.py` | Tests for API endpoints |
| Create | `frontend/src/api/aberration.ts` | API types and fetch functions |
| Create | `frontend/src/components/aberration/CropGrid.tsx` | Crop grid visualization |
| Create | `frontend/src/components/aberration/AberrationSidebar.tsx` | Right sidebar for aberration tab |
| Create | `frontend/src/components/aberration/AberrationToolbar.tsx` | Grid density + metric selector |
| Modify | `frontend/src/pages/ImageViewerPage.tsx` | Add Aberration tab, context-dependent sidebar |
| Modify | `frontend/src/pages/SettingsPage.tsx` | Cache size display + clear button |

---

### Task 1: Database migration for aberration cache

**Files:**
- Create: `backend/src/nightcrate/db/migrations/0004.aberration_cache.sql`

- [ ] **Step 1: Create the migration file**

Create `backend/src/nightcrate/db/migrations/0004.aberration_cache.sql`:

```sql
-- depends: 0003.recent_files

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
);

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
);

CREATE INDEX IF NOT EXISTS idx_aberration_stars_analysis
    ON aberration_stars(analysis_id);

CREATE INDEX IF NOT EXISTS idx_aberration_analysis_path
    ON aberration_analysis(file_path, hdu);
```

- [ ] **Step 2: Verify migration applies**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run python -c "from nightcrate.db.migrations import apply_migrations; apply_migrations(); print('OK')"`

Expected: OK (no errors)

---

### Task 2: Settings — cache TTL

**Files:**
- Modify: `backend/src/nightcrate/core/config.py`
- Modify: `frontend/src/api/settings.ts`

- [ ] **Step 1: Add `aberration_cache_ttl_days` to Settings model**

In `backend/src/nightcrate/core/config.py`, add to the `Settings` class:

```python
aberration_cache_ttl_days: int = 30
```

- [ ] **Step 2: Add field to frontend Settings type**

In `frontend/src/api/settings.ts`, add to the `Settings` interface:

```typescript
aberration_cache_ttl_days: number;
```

- [ ] **Step 3: Run existing tests to verify nothing breaks**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_config.py -v`

Expected: all PASS

---

### Task 3: Backend — Star detection service

**Files:**
- Create: `backend/src/nightcrate/services/aberration.py`
- Create: `backend/tests/test_aberration.py`

This is the core module. It provides:
- `DetectionSettings` — Pydantic model for configurable detection parameters
- `StarMeasurement` — Pydantic model for per-star results
- `AnalysisResult` — Pydantic model for full analysis output
- `detect_stars()` — Runs sep extraction on image data, returns measurements
- `aggregate_zones()` — Groups stars into grid zones with aggregated stats
- `ZoneStats` / `ZoneResult` — Pydantic models for zone data

- [ ] **Step 1: Write tests for star detection on synthetic image**

Create `backend/tests/test_aberration.py`:

```python
"""Tests for aberration analysis — star detection and zone aggregation."""

import numpy as np
import pytest

from nightcrate.services.aberration import (
    AnalysisResult,
    DetectionSettings,
    ZoneResult,
    aggregate_zones,
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
        """Stars near the edge should be excluded."""
        data = _make_star_field(
            stars=[(5, 5, 0.8, 3.0), (200, 200, 0.8, 3.0)]
        )
        result = detect_stars(data, DetectionSettings(edge_margin_px=20))
        assert len(result.stars) == 1
        assert abs(result.stars[0].x - 200) < 5

    def test_snr_filter(self):
        """Low SNR stars should be filtered out."""
        data = _make_star_field(
            stars=[
                (200, 200, 0.8, 3.0),   # bright
                (100, 100, 0.01, 3.0),   # very faint
            ],
            noise_std=0.005,
        )
        result = detect_stars(data, DetectionSettings(min_star_snr=10.0))
        # The faint star should be filtered
        assert len(result.stars) >= 1
        assert all(s.snr >= 10.0 for s in result.stars)

    def test_empty_image_returns_no_stars(self):
        data = np.full((100, 100), 0.02, dtype=np.float64)
        result = detect_stars(data)
        assert len(result.stars) == 0
        assert result.star_count == 0


class TestAggregateZones:
    def test_3x3_grid(self):
        data = _make_star_field()
        analysis = detect_stars(data)
        zones = aggregate_zones(analysis, grid=(3, 3))
        assert isinstance(zones, ZoneResult)
        assert len(zones.zones) == 9
        assert zones.grid == (3, 3)

    def test_5x5_grid(self):
        data = _make_star_field()
        analysis = detect_stars(data)
        zones = aggregate_zones(analysis, grid=(5, 5))
        assert len(zones.zones) == 25

    def test_zone_positions(self):
        """Each zone should have correct row/col indices."""
        data = _make_star_field()
        analysis = detect_stars(data)
        zones = aggregate_zones(analysis, grid=(3, 3))
        coords = [(z.row, z.col) for z in zones.zones]
        for r in range(3):
            for c in range(3):
                assert (r, c) in coords

    def test_zones_contain_star_counts(self):
        data = _make_star_field()
        analysis = detect_stars(data)
        zones = aggregate_zones(analysis, grid=(3, 3))
        total = sum(z.star_count for z in zones.zones)
        assert total == analysis.star_count

    def test_zone_metrics(self):
        """Zones with stars should have non-None metrics."""
        data = _make_star_field()
        analysis = detect_stars(data)
        zones = aggregate_zones(analysis, grid=(3, 3))
        zones_with_stars = [z for z in zones.zones if z.star_count > 0]
        assert len(zones_with_stars) > 0
        for z in zones_with_stars:
            assert z.median_fwhm is not None
            assert z.median_eccentricity is not None
            assert z.median_hfr is not None
            assert z.representative_star_idx is not None

    def test_empty_zones_have_none_metrics(self):
        """Zones without stars should have None metrics."""
        data = _make_star_field()
        analysis = detect_stars(data)
        zones = aggregate_zones(analysis, grid=(9, 9))  # many zones, few stars
        empty_zones = [z for z in zones.zones if z.star_count == 0]
        assert len(empty_zones) > 0
        for z in empty_zones:
            assert z.median_fwhm is None
            assert z.median_eccentricity is None

    def test_regrid_without_reanalysis(self):
        """Zone aggregation should work on existing analysis results."""
        data = _make_star_field()
        analysis = detect_stars(data)
        z3 = aggregate_zones(analysis, grid=(3, 3))
        z5 = aggregate_zones(analysis, grid=(5, 5))
        assert len(z3.zones) == 9
        assert len(z5.zones) == 25
        # Same total stars
        assert sum(z.star_count for z in z3.zones) == sum(z.star_count for z in z5.zones)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_aberration.py -v 2>&1 | head -5`

Expected: ImportError (module doesn't exist yet)

- [ ] **Step 3: Implement the aberration service**

Create `backend/src/nightcrate/services/aberration.py`:

```python
"""Aberration analysis — star detection, measurement, and zone aggregation."""

from __future__ import annotations

import numpy as np
import sep
from pydantic import BaseModel


class DetectionSettings(BaseModel):
    """Configurable parameters for star detection."""

    detection_threshold: float = 5.0
    min_star_snr: float = 5.0
    max_star_peak_adu: float | None = None
    min_star_fwhm_px: float = 1.0
    max_star_fwhm_px: float = 50.0
    edge_margin_px: int = 10
    aperture_radius_factor: float = 3.0
    hfr_max_radius: float = 20.0


class StarMeasurement(BaseModel):
    """Per-star metrics from detection."""

    x: float
    y: float
    fwhm: float
    hfr: float
    eccentricity: float
    elongation_angle_deg: float
    peak_adu: float
    flux: float
    snr: float
    semi_major: float
    semi_minor: float


class AnalysisResult(BaseModel):
    """Full analysis output — star list plus global stats."""

    stars: list[StarMeasurement]
    star_count: int
    image_width: int
    image_height: int
    median_fwhm: float | None = None
    median_hfr: float | None = None
    median_eccentricity: float | None = None
    settings: DetectionSettings


class ZoneStats(BaseModel):
    """Aggregated stats for one grid zone."""

    row: int
    col: int
    star_count: int
    median_fwhm: float | None = None
    mean_fwhm: float | None = None
    std_fwhm: float | None = None
    median_eccentricity: float | None = None
    median_hfr: float | None = None
    median_elongation_angle: float | None = None
    representative_star_idx: int | None = None


class ZoneResult(BaseModel):
    """Zone aggregation output."""

    grid: tuple[int, int]
    zones: list[ZoneStats]


def detect_stars(
    data: np.ndarray,
    settings: DetectionSettings | None = None,
) -> AnalysisResult:
    """Detect stars and measure per-star metrics.

    Args:
        data: 2D float64 array normalized to [0, 1]. For color images,
              pass a single channel or luminance.
        settings: Detection parameters. Uses defaults if None.

    Returns:
        AnalysisResult with star measurements and global stats.
    """
    if settings is None:
        settings = DetectionSettings()

    height, width = data.shape

    # sep requires C-contiguous float64 or float32
    img = np.ascontiguousarray(data, dtype=np.float64)

    # Background subtraction
    bkg = sep.Background(img)
    img_sub = img - bkg

    # Detect sources
    objects = sep.extract(img_sub, thresh=settings.detection_threshold, err=bkg.globalrms)

    if len(objects) == 0:
        return AnalysisResult(
            stars=[],
            star_count=0,
            image_width=width,
            image_height=height,
            settings=settings,
        )

    # Compute per-star metrics
    stars: list[StarMeasurement] = []
    xs = objects["x"]
    ys = objects["y"]
    as_ = objects["a"]
    bs = objects["b"]
    thetas = objects["theta"]
    peaks = objects["peak"]

    # HFR via flux_radius (half-light radius)
    rmax = np.full(len(objects), settings.hfr_max_radius)
    hfrs, _ = sep.flux_radius(img_sub, xs, ys, rmax, 0.5)

    # Aperture photometry for flux + SNR
    radii = settings.aperture_radius_factor * as_
    radii = np.clip(radii, 3.0, 50.0)
    flux_arr, fluxerr_arr, _ = sep.sum_circle(
        img_sub, xs, ys, radii, err=bkg.globalrms,
    )

    for i in range(len(objects)):
        x, y = float(xs[i]), float(ys[i])
        a, b = float(as_[i]), float(bs[i])

        # Edge exclusion
        margin = settings.edge_margin_px
        if x < margin or x > width - margin or y < margin or y > height - margin:
            continue

        # Ensure a >= b (semi-major >= semi-minor)
        if b > a:
            a, b = b, a

        # Eccentricity
        ecc = float(np.sqrt(1 - (b / a) ** 2)) if a > 0 else 0.0

        # FWHM from Gaussian approximation
        fwhm = 2.0 * np.sqrt(np.log(2)) * np.sqrt(a**2 + b**2)

        # Elongation angle (convert from sep's radians to degrees, 0-180)
        angle_deg = float(np.degrees(thetas[i])) % 180

        hfr = float(hfrs[i])
        peak = float(peaks[i])
        flux = float(flux_arr[i])
        fluxerr = float(fluxerr_arr[i])
        snr = flux / fluxerr if fluxerr > 0 else 0.0

        # Apply filters
        if snr < settings.min_star_snr:
            continue
        if fwhm < settings.min_star_fwhm_px or fwhm > settings.max_star_fwhm_px:
            continue
        if settings.max_star_peak_adu is not None and peak > settings.max_star_peak_adu:
            continue

        stars.append(
            StarMeasurement(
                x=round(x, 2),
                y=round(y, 2),
                fwhm=round(fwhm, 3),
                hfr=round(hfr, 3),
                eccentricity=round(ecc, 4),
                elongation_angle_deg=round(angle_deg, 1),
                peak_adu=round(peak, 4),
                flux=round(flux, 2),
                snr=round(snr, 1),
                semi_major=round(a, 3),
                semi_minor=round(b, 3),
            )
        )

    # Global stats
    median_fwhm = None
    median_hfr = None
    median_ecc = None
    if stars:
        fwhms = [s.fwhm for s in stars]
        median_fwhm = round(float(np.median(fwhms)), 3)
        median_hfr = round(float(np.median([s.hfr for s in stars])), 3)
        median_ecc = round(float(np.median([s.eccentricity for s in stars])), 4)

    return AnalysisResult(
        stars=stars,
        star_count=len(stars),
        image_width=width,
        image_height=height,
        median_fwhm=median_fwhm,
        median_hfr=median_hfr,
        median_eccentricity=median_ecc,
        settings=settings,
    )


def aggregate_zones(
    analysis: AnalysisResult,
    grid: tuple[int, int] = (5, 5),
) -> ZoneResult:
    """Group stars into a rectangular grid and compute per-zone stats.

    Args:
        analysis: Result from detect_stars().
        grid: (rows, cols) grid dimensions.

    Returns:
        ZoneResult with per-zone aggregated metrics.
    """
    rows, cols = grid
    w, h = analysis.image_width, analysis.image_height
    zone_w = w / cols
    zone_h = h / rows

    # Assign each star to a zone
    buckets: dict[tuple[int, int], list[int]] = {}
    for r in range(rows):
        for c in range(cols):
            buckets[(r, c)] = []

    for idx, star in enumerate(analysis.stars):
        c = min(int(star.x / zone_w), cols - 1)
        r = min(int(star.y / zone_h), rows - 1)
        buckets[(r, c)].append(idx)

    zones: list[ZoneStats] = []
    for r in range(rows):
        for c in range(cols):
            indices = buckets[(r, c)]
            if not indices:
                zones.append(ZoneStats(row=r, col=c, star_count=0))
                continue

            zone_stars = [analysis.stars[i] for i in indices]
            fwhms = np.array([s.fwhm for s in zone_stars])
            eccs = np.array([s.eccentricity for s in zone_stars])
            hfrs = np.array([s.hfr for s in zone_stars])
            angles = np.array([s.elongation_angle_deg for s in zone_stars])

            # Representative star: closest to zone center with highest SNR
            zone_cx = (c + 0.5) * zone_w
            zone_cy = (r + 0.5) * zone_h
            best_idx = max(
                indices,
                key=lambda i: analysis.stars[i].snr
                / (1 + np.sqrt((analysis.stars[i].x - zone_cx) ** 2 + (analysis.stars[i].y - zone_cy) ** 2) / 100),
            )

            zones.append(
                ZoneStats(
                    row=r,
                    col=c,
                    star_count=len(indices),
                    median_fwhm=round(float(np.median(fwhms)), 3),
                    mean_fwhm=round(float(np.mean(fwhms)), 3),
                    std_fwhm=round(float(np.std(fwhms)), 3),
                    median_eccentricity=round(float(np.median(eccs)), 4),
                    median_hfr=round(float(np.median(hfrs)), 3),
                    median_elongation_angle=round(float(np.median(angles)), 1),
                    representative_star_idx=best_idx,
                )
            )

    return ZoneResult(grid=grid, zones=zones)
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_aberration.py -v`

Expected: all PASS

- [ ] **Step 5: Lint and format**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run ruff check src/nightcrate/services/aberration.py tests/test_aberration.py && uv run ruff format src/nightcrate/services/aberration.py tests/test_aberration.py`

---

### Task 4: Backend — API endpoints

**Files:**
- Create: `backend/src/nightcrate/api/aberration.py`
- Modify: `backend/src/nightcrate/main.py`
- Create: `backend/tests/test_aberration_api.py`

- [ ] **Step 1: Write API endpoint tests**

Create `backend/tests/test_aberration_api.py`:

```python
"""Tests for aberration API endpoints."""

from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from httpx import ASGITransport, AsyncClient

from nightcrate.main import app


@pytest.fixture
def tmp_fits_with_stars(tmp_path: Path) -> Path:
    """Create a FITS file with synthetic stars for aberration testing."""
    rng = np.random.default_rng(42)
    data = rng.normal(1500, 30, (400, 400)).astype(np.uint16)
    # Add stars at known positions
    for cx, cy, peak in [(100, 100, 50000), (300, 100, 40000), (100, 300, 45000), (300, 300, 35000), (200, 200, 55000)]:
        y, x = np.ogrid[0:400, 0:400]
        r2 = (x - cx) ** 2 + (y - cy) ** 2
        data = data.astype(np.float64) + peak * np.exp(-r2 / (2 * 3.5**2))
    data = np.clip(data, 0, 65535).astype(np.uint16)
    hdu = fits.PrimaryHDU(data)
    hdu.header["OBJECT"] = "TestStars"
    path = tmp_path / "stars.fits"
    hdu.writeto(path, overwrite=True)
    return path


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestAberrationEndpoints:
    @pytest.mark.anyio
    async def test_analyze(self, client, tmp_fits_with_stars):
        resp = await client.post(
            "/api/aberration/analyze",
            params={"path": str(tmp_fits_with_stars)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["star_count"] >= 3
        assert len(data["stars"]) == data["star_count"]
        assert data["median_fwhm"] is not None
        assert data["image_width"] == 400
        assert data["image_height"] == 400

    @pytest.mark.anyio
    async def test_zones(self, client, tmp_fits_with_stars):
        # First analyze
        await client.post("/api/aberration/analyze", params={"path": str(tmp_fits_with_stars)})
        # Then get zones
        resp = await client.post(
            "/api/aberration/zones",
            params={"path": str(tmp_fits_with_stars), "rows": 3, "cols": 3},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["grid"] == [3, 3]
        assert len(data["zones"]) == 9

    @pytest.mark.anyio
    async def test_crop(self, client, tmp_fits_with_stars):
        # First analyze
        resp = await client.post("/api/aberration/analyze", params={"path": str(tmp_fits_with_stars)})
        stars = resp.json()["stars"]
        star = stars[0]
        # Get crop
        resp = await client.get(
            "/api/aberration/crop",
            params={"path": str(tmp_fits_with_stars), "x": star["x"], "y": star["y"], "size": 64},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert len(resp.content) > 0

    @pytest.mark.anyio
    async def test_cache_size(self, client, tmp_fits_with_stars):
        resp = await client.get("/api/aberration/cache/size")
        assert resp.status_code == 200
        data = resp.json()
        assert "bytes" in data

    @pytest.mark.anyio
    async def test_cache_clear(self, client, tmp_fits_with_stars):
        # Analyze to populate cache
        await client.post("/api/aberration/analyze", params={"path": str(tmp_fits_with_stars)})
        # Clear
        resp = await client.delete("/api/aberration/cache")
        assert resp.status_code == 200
        # Re-analyze should work (cache miss)
        resp = await client.post("/api/aberration/analyze", params={"path": str(tmp_fits_with_stars)})
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_analyze_nonexistent_file(self, client):
        resp = await client.post("/api/aberration/analyze", params={"path": "/nonexistent/file.fits"})
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_zones_without_analyze_first(self, client, tmp_fits_with_stars):
        """Zones should auto-trigger analysis if not cached."""
        resp = await client.post(
            "/api/aberration/zones",
            params={"path": str(tmp_fits_with_stars), "rows": 3, "cols": 3},
        )
        assert resp.status_code == 200
        assert len(resp.json()["zones"]) == 9
```

- [ ] **Step 2: Implement the API router**

Create `backend/src/nightcrate/api/aberration.py`:

```python
"""Aberration inspector API endpoints."""

from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from PIL import Image

from nightcrate.db.session import get_db
from nightcrate.services.aberration import (
    AnalysisResult,
    DetectionSettings,
    ZoneResult,
    aggregate_zones,
    detect_stars,
)
from nightcrate.services.imaging import StretchParams, render_image_png, compute_image_stats

router = APIRouter(prefix="/api/aberration", tags=["aberration"])


def _load_mono_data(file_path: str, hdu: int = 0) -> np.ndarray:
    """Load image data as 2D float64 [0, 1]. Converts color to luminance."""
    from nightcrate.services.fits_io import load_image_data as fits_load
    from nightcrate.services.xisf_io import load_image_data as xisf_load
    from nightcrate.services.standard_io import load_image_data as standard_load
    from nightcrate.services.pxiproject_io import load_image_data as pxi_load

    p = Path(file_path)
    suffix = p.suffix.lower()
    pxi_suffixes = {".pxiproject"}
    fits_suffixes = {".fits", ".fit", ".fts"}
    xisf_suffixes = {".xisf"}

    if suffix in pxi_suffixes or (p.is_dir() and (p / "project.xosm").exists()):
        data = pxi_load(p, hdu)
    elif suffix in fits_suffixes:
        data = fits_load(p, hdu)
    elif suffix in xisf_suffixes:
        data = xisf_load(p, hdu)
    else:
        data = standard_load(p)

    # Convert color to luminance
    if data.ndim == 3 and data.shape[0] == 3:
        data = 0.2126 * data[0] + 0.7152 * data[1] + 0.0722 * data[2]

    return data


def _settings_key(settings: DetectionSettings) -> str:
    """Stable JSON key for cache lookup."""
    return json.dumps(settings.model_dump(), sort_keys=True)


async def _get_cached_analysis(
    file_path: str, hdu: int, settings: DetectionSettings,
) -> AnalysisResult | None:
    """Look up a cached analysis result from the database."""
    key = _settings_key(settings)
    async with get_db() as conn:
        row = await conn.execute_fetchall(
            "SELECT id, image_width, image_height, star_count, median_fwhm, median_hfr, median_eccentricity "
            "FROM aberration_analysis WHERE file_path = ? AND hdu = ? AND settings_json = ?",
            (file_path, hdu, key),
        )
        if not row:
            return None
        r = row[0]
        analysis_id = r[0]

        star_rows = await conn.execute_fetchall(
            "SELECT x, y, fwhm, hfr, eccentricity, elongation_angle_deg, peak_adu, flux, snr, semi_major, semi_minor "
            "FROM aberration_stars WHERE analysis_id = ? ORDER BY id",
            (analysis_id,),
        )
        from nightcrate.services.aberration import StarMeasurement
        stars = [
            StarMeasurement(
                x=s[0], y=s[1], fwhm=s[2], hfr=s[3], eccentricity=s[4],
                elongation_angle_deg=s[5], peak_adu=s[6], flux=s[7], snr=s[8],
                semi_major=s[9], semi_minor=s[10],
            )
            for s in star_rows
        ]
        return AnalysisResult(
            stars=stars,
            star_count=r[3],
            image_width=r[1],
            image_height=r[2],
            median_fwhm=r[4],
            median_hfr=r[5],
            median_eccentricity=r[6],
            settings=settings,
        )


async def _cache_analysis(
    file_path: str, hdu: int, result: AnalysisResult,
) -> None:
    """Store analysis result in the database cache."""
    key = _settings_key(result.settings)
    async with get_db() as conn:
        cursor = await conn.execute(
            "INSERT OR REPLACE INTO aberration_analysis "
            "(file_path, hdu, image_width, image_height, settings_json, star_count, "
            "median_fwhm, median_hfr, median_eccentricity) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                file_path, hdu, result.image_width, result.image_height,
                key, result.star_count, result.median_fwhm,
                result.median_hfr, result.median_eccentricity,
            ),
        )
        analysis_id = cursor.lastrowid
        # Delete old stars if this was a replace
        await conn.execute("DELETE FROM aberration_stars WHERE analysis_id = ?", (analysis_id,))
        # Insert stars
        for star in result.stars:
            await conn.execute(
                "INSERT INTO aberration_stars "
                "(analysis_id, x, y, fwhm, hfr, eccentricity, elongation_angle_deg, "
                "peak_adu, flux, snr, semi_major, semi_minor) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    analysis_id, star.x, star.y, star.fwhm, star.hfr,
                    star.eccentricity, star.elongation_angle_deg,
                    star.peak_adu, star.flux, star.snr,
                    star.semi_major, star.semi_minor,
                ),
            )
        await conn.commit()


async def _analyze_or_cache(
    file_path: str, hdu: int, settings: DetectionSettings,
) -> AnalysisResult:
    """Return cached analysis or run fresh detection."""
    cached = await _get_cached_analysis(file_path, hdu, settings)
    if cached is not None:
        return cached

    p = Path(file_path)
    if not p.exists():
        raise HTTPException(status_code=422, detail=f"File not found: {file_path}")

    data = _load_mono_data(file_path, hdu)
    result = detect_stars(data, settings)
    await _cache_analysis(file_path, hdu, result)
    return result


@router.post("/analyze")
async def analyze(
    path: str = Query(..., description="Absolute path to image file"),
    hdu: int = Query(0, description="Extension index"),
) -> dict:
    """Run star detection on an image frame. Returns cached result if available."""
    settings = DetectionSettings()
    result = await _analyze_or_cache(path, hdu, settings)
    return result.model_dump()


@router.post("/zones")
async def zones(
    path: str = Query(..., description="Absolute path to image file"),
    hdu: int = Query(0, description="Extension index"),
    rows: int = Query(5, ge=2, le=9, description="Grid rows"),
    cols: int = Query(5, ge=2, le=9, description="Grid columns"),
) -> dict:
    """Compute zone-aggregated stats. Triggers analysis if not cached."""
    settings = DetectionSettings()
    analysis = await _analyze_or_cache(path, hdu, settings)
    result = aggregate_zones(analysis, grid=(rows, cols))
    return result.model_dump()


@router.get("/crop")
async def crop(
    path: str = Query(..., description="Absolute path to image file"),
    hdu: int = Query(0, description="Extension index"),
    x: float = Query(..., description="Star center X"),
    y: float = Query(..., description="Star center Y"),
    size: int = Query(64, ge=16, le=256, description="Crop size in pixels"),
) -> Response:
    """Return an auto-stretched PNG crop around a star position."""
    p = Path(path)
    if not p.exists():
        raise HTTPException(status_code=422, detail=f"File not found: {path}")

    data = _load_mono_data(path, hdu)
    h, w = data.shape

    # Extract crop region (clamp to image bounds)
    half = size // 2
    ix, iy = int(round(x)), int(round(y))
    y0 = max(0, iy - half)
    y1 = min(h, iy + half)
    x0 = max(0, ix - half)
    x1 = min(w, ix + half)
    crop_data = data[y0:y1, x0:x1]

    if crop_data.size == 0:
        raise HTTPException(status_code=422, detail="Crop region is empty")

    # Auto-stretch the crop
    stats = compute_image_stats(crop_data)
    stf = stats.channels[0].stf
    linked = StretchParams(
        stretch="stf", shadow=stf.shadow, midtone=stf.midtone, highlight=stf.highlight,
    )
    png_bytes = render_image_png(crop_data, linked=linked)
    return Response(content=png_bytes, media_type="image/png")


@router.get("/cache/size")
async def cache_size() -> dict:
    """Return the total size of cached aberration data in bytes."""
    async with get_db() as conn:
        row = await conn.execute_fetchall(
            "SELECT COALESCE(SUM(pgsize), 0) FROM dbstat WHERE name IN ('aberration_analysis', 'aberration_stars')"
        )
        # dbstat may not be available — fall back to row count estimate
        if row and row[0][0] is not None:
            return {"bytes": row[0][0]}

        # Fallback: count rows and estimate
        row = await conn.execute_fetchall("SELECT COUNT(*) FROM aberration_stars")
        star_count = row[0][0] if row else 0
        # ~100 bytes per star row estimate
        return {"bytes": star_count * 100}


@router.delete("/cache")
async def clear_cache() -> dict:
    """Delete all cached aberration analysis data."""
    async with get_db() as conn:
        await conn.execute("DELETE FROM aberration_stars")
        await conn.execute("DELETE FROM aberration_analysis")
        await conn.commit()
    return {"status": "cleared"}
```

- [ ] **Step 3: Register the router and add startup cache cleanup**

In `backend/src/nightcrate/main.py`, add:

1. Import: `from nightcrate.api import aberration`
2. Register: `app.include_router(aberration.router)`
3. In the `lifespan` function, after `apply_migrations()`, add cache cleanup:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    apply_migrations()
    await _cleanup_expired_cache()
    yield


async def _cleanup_expired_cache() -> None:
    """Purge aberration cache entries older than the configured TTL."""
    from nightcrate.core.config import get_settings
    from nightcrate.db.session import get_db

    settings = await get_settings()
    ttl_days = settings.aberration_cache_ttl_days
    async with get_db() as conn:
        await conn.execute(
            "DELETE FROM aberration_analysis WHERE created_at < datetime('now', ?)",
            (f"-{ttl_days} days",),
        )
        await conn.commit()
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_aberration_api.py -v`

Expected: all PASS

- [ ] **Step 5: Run full backend checks**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run ruff check src/ tests/ && uv run ruff format src/ tests/ && uv run pytest -v`

---

### Task 5: Frontend — API types and fetch functions

**Files:**
- Create: `frontend/src/api/aberration.ts`

- [ ] **Step 1: Create the API module**

Create `frontend/src/api/aberration.ts`:

```typescript
import { apiFetch } from "./client";

export interface StarMeasurement {
  x: number;
  y: number;
  fwhm: number;
  hfr: number;
  eccentricity: number;
  elongation_angle_deg: number;
  peak_adu: number;
  flux: number;
  snr: number;
  semi_major: number;
  semi_minor: number;
}

export interface AnalysisResult {
  stars: StarMeasurement[];
  star_count: number;
  image_width: number;
  image_height: number;
  median_fwhm: number | null;
  median_hfr: number | null;
  median_eccentricity: number | null;
}

export interface ZoneStats {
  row: number;
  col: number;
  star_count: number;
  median_fwhm: number | null;
  mean_fwhm: number | null;
  std_fwhm: number | null;
  median_eccentricity: number | null;
  median_hfr: number | null;
  median_elongation_angle: number | null;
  representative_star_idx: number | null;
}

export interface ZoneResult {
  grid: [number, number];
  zones: ZoneStats[];
}

export type AberrationMetric = "eccentricity" | "fwhm" | "hfr" | "peak_adu" | "elongation_angle";

export function analyzeFrame(path: string, hdu: number): Promise<AnalysisResult> {
  return apiFetch<AnalysisResult>(
    `/aberration/analyze?path=${encodeURIComponent(path)}&hdu=${hdu}`,
    { method: "POST" },
  );
}

export function fetchZones(
  path: string,
  hdu: number,
  rows: number,
  cols: number,
): Promise<ZoneResult> {
  return apiFetch<ZoneResult>(
    `/aberration/zones?path=${encodeURIComponent(path)}&hdu=${hdu}&rows=${rows}&cols=${cols}`,
    { method: "POST" },
  );
}

export function cropUrl(path: string, hdu: number, x: number, y: number, size: number): string {
  const q = new URLSearchParams({ path, hdu: String(hdu), x: String(x), y: String(y), size: String(size) });
  return `/api/aberration/crop?${q.toString()}`;
}

export interface CacheSize {
  bytes: number;
}

export function fetchCacheSize(): Promise<CacheSize> {
  return apiFetch<CacheSize>("/aberration/cache/size");
}

export function clearCache(): Promise<{ status: string }> {
  return apiFetch("/aberration/cache", { method: "DELETE" });
}
```

- [ ] **Step 2: Build frontend to verify types**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npm run build`

Expected: Build succeeds

---

### Task 6: Frontend — Aberration toolbar component

**Files:**
- Create: `frontend/src/components/aberration/AberrationToolbar.tsx`

- [ ] **Step 1: Create the toolbar**

Create `frontend/src/components/aberration/AberrationToolbar.tsx`:

```typescript
import Box from "@mui/material/Box";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import type { AberrationMetric } from "@/api/aberration";

const GRID_OPTIONS = [
  { label: "3×3", rows: 3, cols: 3 },
  { label: "4×4", rows: 4, cols: 4 },
  { label: "5×5", rows: 5, cols: 5 },
  { label: "7×7", rows: 7, cols: 7 },
  { label: "9×9", rows: 9, cols: 9 },
];

const METRIC_OPTIONS: { value: AberrationMetric; label: string }[] = [
  { value: "eccentricity", label: "Eccentricity" },
  { value: "fwhm", label: "FWHM" },
  { value: "hfr", label: "HFR" },
  { value: "peak_adu", label: "Peak ADU" },
  { value: "elongation_angle", label: "Elong. Angle" },
];

interface Props {
  gridSize: string;
  onGridChange: (size: string) => void;
  metric: AberrationMetric;
  onMetricChange: (m: AberrationMetric) => void;
  analyzing: boolean;
}

export function AberrationToolbar({ gridSize, onGridChange, metric, onMetricChange, analyzing }: Props) {
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 2, px: 2, py: 1, borderBottom: 1, borderColor: "divider" }}>
      <ToggleButtonGroup
        exclusive
        size="small"
        value={gridSize}
        onChange={(_, v) => { if (v) onGridChange(v); }}
      >
        {GRID_OPTIONS.map((opt) => (
          <ToggleButton key={opt.label} value={opt.label} sx={{ fontSize: "0.65rem", py: 0.25 }}>
            {opt.label}
          </ToggleButton>
        ))}
      </ToggleButtonGroup>

      <FormControl size="small" sx={{ minWidth: 130 }}>
        <InputLabel sx={{ fontSize: "0.75rem" }}>Metric</InputLabel>
        <Select
          label="Metric"
          value={metric}
          onChange={(e) => onMetricChange(e.target.value as AberrationMetric)}
          sx={{ fontSize: "0.75rem" }}
        >
          {METRIC_OPTIONS.map((opt) => (
            <MenuItem key={opt.value} value={opt.value} sx={{ fontSize: "0.75rem" }}>
              {opt.label}
            </MenuItem>
          ))}
        </Select>
      </FormControl>

      {analyzing && (
        <Box sx={{ fontSize: "0.65rem", color: "text.secondary" }}>Analyzing…</Box>
      )}
    </Box>
  );
}

export function parseGrid(size: string): { rows: number; cols: number } {
  const opt = GRID_OPTIONS.find((o) => o.label === size);
  return opt ?? { rows: 5, cols: 5 };
}
```

- [ ] **Step 2: Build to verify**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npm run build`

---

### Task 7: Frontend — Crop grid component

**Files:**
- Create: `frontend/src/components/aberration/CropGrid.tsx`

- [ ] **Step 1: Create the crop grid**

Create `frontend/src/components/aberration/CropGrid.tsx`:

```typescript
import { useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import type { ZoneResult, ZoneStats, AberrationMetric } from "@/api/aberration";
import { cropUrl } from "@/api/aberration";
import { monoFontFamily } from "@/theme/theme";

/** Viridis-inspired colorblind-safe scale (5 stops). */
const VIRIDIS = ["#440154", "#3b528b", "#21918c", "#5ec962", "#fde725"];

function viridisColor(t: number): string {
  const clamped = Math.max(0, Math.min(1, t));
  const idx = clamped * (VIRIDIS.length - 1);
  const lo = Math.floor(idx);
  const hi = Math.min(lo + 1, VIRIDIS.length - 1);
  const frac = idx - lo;
  // Simple linear interpolation in hex
  const lerp = (a: number, b: number) => Math.round(a + (b - a) * frac);
  const parse = (hex: string) => [parseInt(hex.slice(1, 3), 16), parseInt(hex.slice(3, 5), 16), parseInt(hex.slice(5, 7), 16)];
  const [r1, g1, b1] = parse(VIRIDIS[lo]);
  const [r2, g2, b2] = parse(VIRIDIS[hi]);
  const r = lerp(r1, r2);
  const g = lerp(g1, g2);
  const b = lerp(b1, b2);
  return `rgb(${r}, ${g}, ${b})`;
}

function getMetricValue(zone: ZoneStats, metric: AberrationMetric): number | null {
  switch (metric) {
    case "eccentricity": return zone.median_eccentricity;
    case "fwhm": return zone.median_fwhm;
    case "hfr": return zone.median_hfr;
    case "peak_adu": return null; // not aggregated per zone
    case "elongation_angle": return zone.median_elongation_angle;
  }
}

function formatMetric(value: number | null, metric: AberrationMetric): string {
  if (value == null) return "—";
  switch (metric) {
    case "eccentricity": return value.toFixed(3);
    case "fwhm": return value.toFixed(2);
    case "hfr": return value.toFixed(2);
    case "peak_adu": return value.toFixed(0);
    case "elongation_angle": return `${value.toFixed(0)}°`;
  }
}

interface Props {
  zones: ZoneResult;
  analysis: { stars: { x: number; y: number }[]; image_width: number; image_height: number };
  path: string;
  hdu: number;
  metric: AberrationMetric;
  onZoneClick: (zone: ZoneStats) => void;
}

export function CropGrid({ zones, analysis, path, hdu, metric, onZoneClick }: Props) {
  const [rows, cols] = zones.grid;
  const [hoveredZone, setHoveredZone] = useState<string | null>(null);

  // Compute metric range for color scale
  const values = zones.zones
    .map((z) => getMetricValue(z, metric))
    .filter((v): v is number => v != null);
  const minVal = values.length > 0 ? Math.min(...values) : 0;
  const maxVal = values.length > 0 ? Math.max(...values) : 1;
  const range = maxVal - minVal || 1;

  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: `repeat(${cols}, 1fr)`,
        gridTemplateRows: `repeat(${rows}, 1fr)`,
        gap: "2px",
        width: "100%",
        height: "100%",
        p: 1,
      }}
    >
      {zones.zones.map((zone) => {
        const key = `${zone.row}-${zone.col}`;
        const metricVal = getMetricValue(zone, metric);
        const t = metricVal != null ? (metricVal - minVal) / range : 0;
        const bgColor = zone.star_count > 0 ? viridisColor(t) : "transparent";
        const isHovered = hoveredZone === key;

        // Get representative star for crop
        const repIdx = zone.representative_star_idx;
        const repStar = repIdx != null ? analysis.stars[repIdx] : null;

        return (
          <Box
            key={key}
            onClick={() => onZoneClick(zone)}
            onMouseEnter={() => setHoveredZone(key)}
            onMouseLeave={() => setHoveredZone(null)}
            sx={{
              position: "relative",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              bgcolor: bgColor,
              opacity: zone.star_count > 0 ? 1 : 0.3,
              border: 1,
              borderColor: isHovered ? "primary.main" : "divider",
              borderRadius: 0.5,
              cursor: "pointer",
              overflow: "hidden",
              transition: "border-color 0.15s",
            }}
          >
            {/* Star crop image */}
            {repStar && (
              <Box
                component="img"
                src={cropUrl(path, hdu, repStar.x, repStar.y, 64)}
                sx={{
                  position: "absolute",
                  inset: 0,
                  width: "100%",
                  height: "100%",
                  objectFit: "cover",
                  imageRendering: "pixelated",
                  opacity: 0.7,
                }}
              />
            )}
            {/* Metric overlay */}
            <Box sx={{ position: "relative", zIndex: 1, textAlign: "center" }}>
              <Typography
                sx={{
                  fontSize: "0.7rem",
                  fontFamily: monoFontFamily,
                  fontWeight: 600,
                  color: "#ffffff",
                  textShadow: "0 0 4px rgba(0,0,0,0.8), 0 0 2px rgba(0,0,0,0.9)",
                }}
              >
                {formatMetric(metricVal, metric)}
              </Typography>
              <Typography
                sx={{
                  fontSize: "0.55rem",
                  color: "rgba(255,255,255,0.7)",
                  textShadow: "0 0 3px rgba(0,0,0,0.8)",
                }}
              >
                {zone.star_count} star{zone.star_count !== 1 ? "s" : ""}
              </Typography>
            </Box>
          </Box>
        );
      })}
    </Box>
  );
}
```

- [ ] **Step 2: Build to verify**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npm run build`

---

### Task 8: Frontend — Aberration sidebar component

**Files:**
- Create: `frontend/src/components/aberration/AberrationSidebar.tsx`

- [ ] **Step 1: Create the sidebar**

Create `frontend/src/components/aberration/AberrationSidebar.tsx`:

```typescript
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import type { AnalysisResult, ZoneStats } from "@/api/aberration";
import { cropUrl } from "@/api/aberration";
import { monoFontFamily } from "@/theme/theme";

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <>
      <Typography sx={{ fontSize: "inherit", fontFamily: "inherit", color: "text.secondary" }}>{label}</Typography>
      <Typography sx={{ fontSize: "inherit", fontFamily: "inherit" }}>{value}</Typography>
    </>
  );
}

interface Props {
  analysis: AnalysisResult | null;
  selectedZone: ZoneStats | null;
  path: string;
  hdu: number;
}

export function AberrationSidebar({ analysis, selectedZone, path, hdu }: Props) {
  if (!analysis) {
    return (
      <Box sx={{ p: 1.5 }}>
        <Typography variant="caption" color="text.secondary" sx={{ fontSize: "0.65rem" }}>
          Open an image and switch to the Aberration tab to analyze star shapes.
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
      {/* Global stats */}
      <Box sx={{ px: 1.5, pt: 1.5, pb: 0.5 }}>
        <Typography variant="caption" color="secondary.main" sx={{ fontSize: "0.65rem", letterSpacing: "0.05em", textTransform: "uppercase" }}>
          Global Stats
        </Typography>
      </Box>
      <Box sx={{ px: 1.5, display: "grid", gridTemplateColumns: "auto 1fr", columnGap: 1, rowGap: 0.125, fontSize: "0.65rem", fontFamily: monoFontFamily }}>
        <StatRow label="Stars" value={String(analysis.star_count)} />
        <StatRow label="Med FWHM" value={analysis.median_fwhm?.toFixed(2) ?? "—"} />
        <StatRow label="Med Ecc" value={analysis.median_eccentricity?.toFixed(3) ?? "—"} />
        <StatRow label="Med HFR" value={analysis.median_hfr?.toFixed(2) ?? "—"} />
      </Box>

      {/* Zone detail (when a zone is clicked) */}
      {selectedZone && selectedZone.star_count > 0 && (
        <>
          <Box sx={{ px: 1.5, pt: 1 }}>
            <Typography variant="caption" color="secondary.main" sx={{ fontSize: "0.65rem", letterSpacing: "0.05em", textTransform: "uppercase" }}>
              Zone [{selectedZone.row}, {selectedZone.col}]
            </Typography>
          </Box>

          {/* Representative star crop */}
          {selectedZone.representative_star_idx != null && (
            <Box sx={{ px: 1.5, display: "flex", justifyContent: "center" }}>
              <Box
                component="img"
                src={cropUrl(path, hdu, analysis.stars[selectedZone.representative_star_idx].x, analysis.stars[selectedZone.representative_star_idx].y, 128)}
                sx={{
                  width: 128,
                  height: 128,
                  imageRendering: "pixelated",
                  borderRadius: 1,
                  border: 1,
                  borderColor: "divider",
                }}
              />
            </Box>
          )}

          <Box sx={{ px: 1.5, display: "grid", gridTemplateColumns: "auto 1fr", columnGap: 1, rowGap: 0.125, fontSize: "0.65rem", fontFamily: monoFontFamily }}>
            <StatRow label="Stars" value={String(selectedZone.star_count)} />
            <StatRow label="Med FWHM" value={selectedZone.median_fwhm?.toFixed(2) ?? "—"} />
            <StatRow label="Med Ecc" value={selectedZone.median_eccentricity?.toFixed(3) ?? "—"} />
            <StatRow label="Med HFR" value={selectedZone.median_hfr?.toFixed(2) ?? "—"} />
            <StatRow label="Mean FWHM" value={selectedZone.mean_fwhm?.toFixed(2) ?? "—"} />
            <StatRow label="Std FWHM" value={selectedZone.std_fwhm?.toFixed(3) ?? "—"} />
            <StatRow label="Med Angle" value={selectedZone.median_elongation_angle != null ? `${selectedZone.median_elongation_angle.toFixed(0)}°` : "—"} />
          </Box>
        </>
      )}

      {selectedZone && selectedZone.star_count === 0 && (
        <Box sx={{ px: 1.5 }}>
          <Typography variant="caption" color="text.secondary" sx={{ fontSize: "0.65rem" }}>
            No stars detected in this zone.
          </Typography>
        </Box>
      )}
    </Box>
  );
}
```

- [ ] **Step 2: Build to verify**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npm run build`

---

### Task 9: Frontend — Aberration tab in ImageViewerPage

**Files:**
- Modify: `frontend/src/pages/ImageViewerPage.tsx`

This is the integration task. Adds the "Aberration" tab, wires up the analysis query, and switches the right sidebar content based on active tab.

- [ ] **Step 1: Add imports**

Add to the imports in `ImageViewerPage.tsx`:

```typescript
import { useQuery, useMutation } from "@tanstack/react-query";
import { analyzeFrame, fetchZones, type AnalysisResult, type ZoneResult, type ZoneStats, type AberrationMetric } from "@/api/aberration";
import { AberrationToolbar, parseGrid } from "@/components/aberration/AberrationToolbar";
import { CropGrid } from "@/components/aberration/CropGrid";
import { AberrationSidebar } from "@/components/aberration/AberrationSidebar";
```

Note: `useMutation` may already be imported — check. If `useQuery` is already imported from TanStack Query, just add `useMutation` to the existing import.

- [ ] **Step 2: Add aberration state**

Add after the existing state declarations (near the stretch state):

```typescript
// Aberration inspector state
const [gridSize, setGridSize] = useState("5×5");
const [aberrationMetric, setAberrationMetric] = useState<AberrationMetric>("eccentricity");
const [selectedZone, setSelectedZone] = useState<ZoneStats | null>(null);
```

- [ ] **Step 3: Add aberration queries**

Add after the existing queries:

```typescript
// Aberration analysis — triggered when switching to aberration tab
const aberrationQuery = useQuery({
  queryKey: ["aberration", activePath, selectedHdu],
  queryFn: () => analyzeFrame(activePath, selectedHdu),
  enabled: activePath !== "" && tab === 2,
});

const { rows: gridRows, cols: gridCols } = parseGrid(gridSize);
const zonesQuery = useQuery({
  queryKey: ["zones", activePath, selectedHdu, gridRows, gridCols],
  queryFn: () => fetchZones(activePath, selectedHdu, gridRows, gridCols),
  enabled: aberrationQuery.data != null,
});
```

- [ ] **Step 4: Add the Aberration tab**

Find the existing tabs (the `<Tab label="Image" />` and `<Tab label="Header" />` elements) and add a third tab:

```typescript
<Tab label="Aberration" disabled={!hasFile || !selectedExtInfo?.has_image} />
```

- [ ] **Step 5: Add the aberration content area**

After the Header tab's content `Box`, add:

```typescript
{/* Aberration tab content */}
<Box sx={{ flexGrow: 1, overflow: "hidden", display: tab === 2 ? "flex" : "none", flexDirection: "column" }}>
  <AberrationToolbar
    gridSize={gridSize}
    onGridChange={(s) => { setGridSize(s); setSelectedZone(null); }}
    metric={aberrationMetric}
    onMetricChange={setAberrationMetric}
    analyzing={aberrationQuery.isFetching}
  />
  <Box sx={{ flexGrow: 1, overflow: "auto" }}>
    {zonesQuery.data && aberrationQuery.data && (
      <CropGrid
        zones={zonesQuery.data}
        analysis={aberrationQuery.data}
        path={activePath}
        hdu={selectedHdu}
        metric={aberrationMetric}
        onZoneClick={setSelectedZone}
      />
    )}
    {aberrationQuery.isLoading && (
      <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100%" }}>
        <CircularProgress size={32} />
      </Box>
    )}
    {aberrationQuery.isError && (
      <Alert severity="error" sx={{ m: 2 }}>{String(aberrationQuery.error)}</Alert>
    )}
  </Box>
</Box>
```

- [ ] **Step 6: Make the right sidebar context-dependent**

The right sidebar currently renders only when `tab === 0`. Change it to render for both tab 0 and tab 2, but with different content.

Find the sidebar container condition: `{hasFile && selectedExtInfo?.has_image && tab === 0 && (`

Change to: `{hasFile && selectedExtInfo?.has_image && (tab === 0 || tab === 2) && (`

Then inside the sidebar Box, wrap the existing content in a `tab === 0` check, and add the aberration sidebar for `tab === 2`:

```typescript
{tab === 0 && (
  <>
    {/* ...existing Image Info, Image Size, Stretch, Pixel Inspector, Statistics, Help sections... */}
  </>
)}
{tab === 2 && (
  <AberrationSidebar
    analysis={aberrationQuery.data ?? null}
    selectedZone={selectedZone}
    path={activePath}
    hdu={selectedHdu}
  />
)}
```

- [ ] **Step 7: Reset aberration state on file change**

In the `openFile` function, add:

```typescript
setSelectedZone(null);
```

- [ ] **Step 8: Build frontend**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npm run build`

Expected: Build succeeds

---

### Task 10: Frontend — Cache management in Settings

**Files:**
- Modify: `frontend/src/pages/SettingsPage.tsx`

- [ ] **Step 1: Add cache size display and clear button**

Read the current `SettingsPage.tsx`, then add a new Card section after the Performance card:

```typescript
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Button from "@mui/material/Button";
import { fetchCacheSize, clearCache } from "@/api/aberration";

// Inside the component:
const queryClient = useQueryClient();
const cacheQuery = useQuery({
  queryKey: ["aberration-cache-size"],
  queryFn: fetchCacheSize,
});

const cacheMB = cacheQuery.data ? (cacheQuery.data.bytes / (1024 * 1024)).toFixed(2) : "…";

// Add this Card after the Performance card:
<Card variant="outlined">
  <CardContent>
    <Typography variant="body2" color="text.secondary" fontWeight={500} sx={{ mb: 2, textTransform: "uppercase", letterSpacing: "0.05em", fontSize: "0.7rem" }}>
      Aberration Cache
    </Typography>
    <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
      <Box>
        <Typography variant="body1">Cache Size</Typography>
        <Typography variant="body2" color="text.secondary">
          {cacheMB} MB used by cached star detection results
        </Typography>
      </Box>
      <Button
        variant="outlined"
        size="small"
        onClick={async () => {
          await clearCache();
          queryClient.invalidateQueries({ queryKey: ["aberration-cache-size"] });
        }}
      >
        Clear All
      </Button>
    </Box>
  </CardContent>
</Card>
```

- [ ] **Step 2: Build frontend**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npm run build`

---

### Task 11: Full test suite and final checks

- [ ] **Step 1: Run backend lint + format + security**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run bandit -r src/`

- [ ] **Step 2: Run all backend tests**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest -v`

Expected: all PASS (210 existing + ~20 new)

- [ ] **Step 3: Build frontend**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npm run build`

Expected: Build succeeds

- [ ] **Step 4: Update README attribution**

Add `sep` to the Open Source Acknowledgments table in README.md (LGPL-3.0 requires attribution).
