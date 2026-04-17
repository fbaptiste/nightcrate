# Rig Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the rig builder system — a user-composed equipment template that assembles imaging configurations, powers optical calculators (image scale, FOV, sampling assessment), and prepares the schema for future FITS resolver and ingest pipeline integration.

**Architecture:** Rigs are fixed-slot templates (OTA config + camera required, everything else optional) stored in SQLite with a `rig_filter_slot` junction table for filter wheel assignments. Optical calculators are pure server-side functions returning computed metrics with every rig response. Seeing conditions for sampling assessment live on the `location` table and flow through a resolution chain (override → location → default). Frontend is a card-based list with a modal editor dialog and a calculator panel featuring a D3 sampling chart.

**Tech Stack:** Python (FastAPI, math), React + TypeScript (MUI, D3.js for sampling chart), SQLite, Pydantic

**Spec:** `docs/superpowers/specs/2026-04-15-rig-builder-design.md`

---

## File Structure

### Backend — new files

| File | Responsibility |
|------|---------------|
| `db/migrations/0009.rig.sql` | Rig table, rig_filter_slot junction table, rig_summary view, indexes, triggers. |
| `api/rig_models.py` | Pydantic models: RigCreate, RigUpdate, RigOut, RigFilterSlotIn/Out, RigCalculators, SamplingAssessment, RigWarning, EquipmentOptionsOut and per-type option models. |
| `services/rig_calculators.py` | Pure calculator functions: image scale, FOV, resolution limits, sensor coverage, sampling assessment, guide system metrics, seeing resolution. |
| `api/rigs.py` | FastAPI router with all rig CRUD endpoints, equipment options, calculator endpoint. |
| `tests/test_rig_calculators.py` | Unit tests for calculator formulas using Fred's actual equipment values as pinned regression tests. |
| `tests/test_rig_api.py` | Integration tests for all rig API endpoints: CRUD, filter slots, clone, restore, default flag, validation, warnings, equipment options. |
| `tests/test_location_seeing.py` | Tests for seeing fields on location: create/update, validation, seeing resolution chain. |

### Frontend — new files

| File | Responsibility |
|------|---------------|
| `api/rigs.ts` | TypeScript interfaces and fetch functions for all rig endpoints. |
| `pages/RigsPage.tsx` | Main rig page: card-based list, new rig button, retired section. |
| `components/rigs/RigCard.tsx` | Single rig card: name, equipment summary, key stats, sampling badge, action buttons. |
| `components/rigs/RigFormDialog.tsx` | Modal dialog for create/edit with sectioned form (identity, optical train, filtration, guiding, peripherals, options). |
| `components/rigs/CalculatorPanel.tsx` | Computed optical properties display with location selector, seeing slider, binning selector, and D3 sampling chart. |
| `components/rigs/SamplingChart.tsx` | D3 horizontal bar chart showing binning levels against ideal sampling zone. |
| `components/rigs/FilterSlotGrid.tsx` | Grid of filter dropdowns driven by filter wheel's num_positions. |

### Existing files to modify

| File | Change |
|------|--------|
| `db/migrations/0007.locations.sql` | Add `typical_seeing_low_arcsec` and `typical_seeing_high_arcsec` columns (edit in place, pre-release policy). |
| `api/locations.py` | Add seeing fields to LocationCreate, LocationUpdate, LocationResponse models. Add seeing validation (low ≤ high). |
| `main.py` | Add "Rigs" openapi_tags entry, register rigs router. |
| `frontend/src/api/locations.ts` | Add seeing fields to Location and LocationCreate interfaces. |
| `frontend/src/pages/LocationsPage.tsx` | Add seeing input fields with collapsible reference guide to location form. |
| `frontend/src/App.tsx` | Add `/rigs` route. |
| `frontend/src/components/AppShell.tsx` | Add Rigs nav item. |

---

## Task 1: Location seeing columns (migration edit + backend models)

**Files:**
- Modify: `backend/src/nightcrate/db/migrations/0007.locations.sql`
- Modify: `backend/src/nightcrate/api/locations.py:63-169`
- Test: `backend/tests/test_location_seeing.py`

- [ ] **Step 1: Write failing tests for location seeing fields**

Create `backend/tests/test_location_seeing.py`:

```python
"""Tests for seeing fields on locations."""

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


BASE = {
    "name": "Backyard Observatory",
    "latitude": 33.45,
    "longitude": -112.07,
    "timezone": "America/Phoenix",
}


@pytest.mark.anyio
async def test_create_location_with_seeing(client):
    payload = {**BASE, "typical_seeing_low_arcsec": 2.0, "typical_seeing_high_arcsec": 4.0}
    resp = await client.post("/api/locations", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["typical_seeing_low_arcsec"] == 2.0
    assert data["typical_seeing_high_arcsec"] == 4.0


@pytest.mark.anyio
async def test_create_location_without_seeing(client):
    resp = await client.post("/api/locations", json=BASE)
    assert resp.status_code == 201
    data = resp.json()
    assert data["typical_seeing_low_arcsec"] is None
    assert data["typical_seeing_high_arcsec"] is None


@pytest.mark.anyio
async def test_update_location_seeing(client):
    resp = await client.post("/api/locations", json=BASE)
    loc_id = resp.json()["id"]

    resp = await client.put(
        f"/api/locations/{loc_id}",
        json={"typical_seeing_low_arcsec": 1.5, "typical_seeing_high_arcsec": 3.0},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["typical_seeing_low_arcsec"] == 1.5
    assert data["typical_seeing_high_arcsec"] == 3.0


@pytest.mark.anyio
async def test_seeing_low_must_be_lte_high(client):
    payload = {**BASE, "typical_seeing_low_arcsec": 5.0, "typical_seeing_high_arcsec": 2.0}
    resp = await client.post("/api/locations", json=payload)
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_seeing_single_value_ok(client):
    payload = {**BASE, "typical_seeing_low_arcsec": 2.5}
    resp = await client.post("/api/locations", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["typical_seeing_low_arcsec"] == 2.5
    assert data["typical_seeing_high_arcsec"] is None


@pytest.mark.anyio
async def test_seeing_must_be_positive(client):
    payload = {**BASE, "typical_seeing_low_arcsec": -1.0}
    resp = await client.post("/api/locations", json=payload)
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_seeing_zero_rejected(client):
    payload = {**BASE, "typical_seeing_low_arcsec": 0.0}
    resp = await client.post("/api/locations", json=payload)
    assert resp.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_location_seeing.py -v`
Expected: FAIL — `typical_seeing_low_arcsec` not recognized by Pydantic models or DB.

- [ ] **Step 3: Add seeing columns to 0007.locations.sql**

Edit `backend/src/nightcrate/db/migrations/0007.locations.sql` — add two columns before `is_default`:

```sql
    typical_seeing_low_arcsec REAL CHECK (typical_seeing_low_arcsec IS NULL OR typical_seeing_low_arcsec > 0),
    typical_seeing_high_arcsec REAL CHECK (typical_seeing_high_arcsec IS NULL OR typical_seeing_high_arcsec > 0),
```

- [ ] **Step 4: Add seeing fields to LocationCreate model**

In `backend/src/nightcrate/api/locations.py`, add to `LocationCreate`:

```python
    typical_seeing_low_arcsec: float | None = None
    typical_seeing_high_arcsec: float | None = None

    @model_validator(mode="after")
    def check_seeing_range(self) -> "LocationCreate":
        low = self.typical_seeing_low_arcsec
        high = self.typical_seeing_high_arcsec
        if low is not None and low <= 0:
            raise ValueError("typical_seeing_low_arcsec must be positive")
        if high is not None and high <= 0:
            raise ValueError("typical_seeing_high_arcsec must be positive")
        if low is not None and high is not None and low > high:
            raise ValueError(
                "typical_seeing_low_arcsec must be ≤ typical_seeing_high_arcsec"
            )
        return self
```

Add the same fields and validator to `LocationUpdate`. Add both fields to `LocationResponse`.

Import `model_validator` from pydantic at the top of the file.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_location_seeing.py -v`
Expected: All 7 tests PASS.

- [ ] **Step 6: Run full test suite to check for regressions**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest -x -q`
Expected: All existing tests still pass. The conftest `_test_db` fixture re-applies 0007 migration with the new columns.

- [ ] **Step 7: Commit**

```bash
git add backend/src/nightcrate/db/migrations/0007.locations.sql backend/src/nightcrate/api/locations.py backend/tests/test_location_seeing.py
git commit -m "feat: add typical seeing fields to location schema and API"
```

---

## Task 2: Rig calculator service

**Files:**
- Create: `backend/src/nightcrate/services/rig_calculators.py`
- Test: `backend/tests/test_rig_calculators.py`

This is pure math with no DB or API dependencies — perfect for TDD in isolation.

- [ ] **Step 1: Write failing tests for calculator formulas**

Create `backend/tests/test_rig_calculators.py`:

```python
"""Tests for rig optical calculator formulas.

Pinned regression tests using Fred's actual equipment values from Appendix A of the spec.
"""

import math

import pytest


# ── Image Scale ──────────────────────────────────────────────────────────────


def test_image_scale_c11():
    from nightcrate.services.rig_calculators import compute_image_scale

    # C11 + 0.7x reducer: 3.76μm / 1960mm × 206.265 = 0.396″/px
    result = compute_image_scale(pixel_size_um=3.76, focal_length_mm=1960.0)
    assert result == pytest.approx(0.396, abs=0.001)


def test_image_scale_askar_v():
    from nightcrate.services.rig_calculators import compute_image_scale

    # Askar V native: 3.76μm / 360mm × 206.265 = 2.155″/px
    result = compute_image_scale(pixel_size_um=3.76, focal_length_mm=360.0)
    assert result == pytest.approx(2.155, abs=0.001)


def test_image_scale_binned():
    from nightcrate.services.rig_calculators import compute_image_scale_binned

    base_scale = 0.396
    binned = compute_image_scale_binned(base_scale)
    assert binned[1] == pytest.approx(0.396, abs=0.001)
    assert binned[2] == pytest.approx(0.792, abs=0.001)
    assert binned[3] == pytest.approx(1.188, abs=0.001)
    assert binned[4] == pytest.approx(1.584, abs=0.001)


# ── Field of View ────────────────────────────────────────────────────────────


def test_fov_arctan_c11():
    from nightcrate.services.rig_calculators import compute_fov

    # C11 with physical sensor: 23.5mm × 15.7mm, FL 1960mm
    width_deg, height_deg = compute_fov(
        focal_length_mm=1960.0,
        sensor_width_mm=23.5,
        sensor_height_mm=15.7,
        resolution_x=6248,
        resolution_y=4176,
        pixel_size_um=3.76,
    )
    assert width_deg == pytest.approx(0.688, abs=0.002)
    assert height_deg == pytest.approx(0.459, abs=0.002)


def test_fov_arctan_askar_v():
    from nightcrate.services.rig_calculators import compute_fov

    width_deg, height_deg = compute_fov(
        focal_length_mm=360.0,
        sensor_width_mm=23.5,
        sensor_height_mm=15.7,
        resolution_x=6248,
        resolution_y=4176,
        pixel_size_um=3.76,
    )
    assert width_deg == pytest.approx(3.738, abs=0.005)
    assert height_deg == pytest.approx(2.498, abs=0.005)


def test_fov_pixel_fallback():
    """When physical sensor dims are missing, use pixel count × pixel size."""
    from nightcrate.services.rig_calculators import compute_fov

    width_deg, height_deg = compute_fov(
        focal_length_mm=1960.0,
        sensor_width_mm=None,
        sensor_height_mm=None,
        resolution_x=6248,
        resolution_y=4176,
        pixel_size_um=3.76,
    )
    # Pixel-based: (6248 × 3.76 / 1000) ≈ 23.49mm — very close to physical
    assert width_deg == pytest.approx(0.688, abs=0.005)


# ── Resolution Limits ────────────────────────────────────────────────────────


def test_dawes_limit_c11():
    from nightcrate.services.rig_calculators import compute_resolution_limits

    dawes, rayleigh, max_mag = compute_resolution_limits(aperture_mm=280.0)
    assert dawes == pytest.approx(0.414, abs=0.001)
    assert rayleigh == pytest.approx(0.493, abs=0.001)
    assert max_mag == pytest.approx(560.0)


def test_dawes_limit_askar_v():
    from nightcrate.services.rig_calculators import compute_resolution_limits

    dawes, rayleigh, max_mag = compute_resolution_limits(aperture_mm=60.0)
    assert dawes == pytest.approx(1.933, abs=0.001)
    assert rayleigh == pytest.approx(2.300, abs=0.001)
    assert max_mag == pytest.approx(120.0)


# ── Sensor Coverage ──────────────────────────────────────────────────────────


def test_sensor_diagonal():
    from nightcrate.services.rig_calculators import compute_sensor_diagonal

    diag = compute_sensor_diagonal(sensor_width_mm=23.5, sensor_height_mm=15.7)
    assert diag == pytest.approx(28.26, abs=0.01)


def test_sensor_diagonal_from_pixels():
    from nightcrate.services.rig_calculators import compute_sensor_diagonal

    # Fallback from pixel dimensions
    diag = compute_sensor_diagonal(
        sensor_width_mm=None,
        sensor_height_mm=None,
        resolution_x=6248,
        resolution_y=4176,
        pixel_size_um=3.76,
    )
    assert diag == pytest.approx(28.26, abs=0.05)


def test_sensor_coverage():
    from nightcrate.services.rig_calculators import compute_sensor_coverage

    pct = compute_sensor_coverage(sensor_diagonal_mm=28.26, image_circle_mm=32.0)
    assert pct == pytest.approx(88.3, abs=0.5)


def test_sensor_coverage_vignetting():
    from nightcrate.services.rig_calculators import compute_sensor_coverage

    pct = compute_sensor_coverage(sensor_diagonal_mm=28.26, image_circle_mm=20.0)
    assert pct > 100  # vignetting warning expected


# ── Sampling Assessment ──────────────────────────────────────────────────────


def test_sampling_c11_oversampled():
    from nightcrate.services.rig_calculators import assess_sampling

    result = assess_sampling(
        image_scale=0.396,
        seeing_fwhm_low=2.0,
        seeing_fwhm_high=4.0,
    )
    assert result.assessment == "oversampled"
    assert result.ideal_range_low == pytest.approx(0.667, abs=0.01)
    assert result.ideal_range_high == pytest.approx(2.0, abs=0.01)
    assert result.binning_recommendations[1] == "oversampled"
    assert result.binning_recommendations[2] == "well_sampled"
    assert result.binning_recommendations[3] == "well_sampled"


def test_sampling_askar_v_undersampled():
    from nightcrate.services.rig_calculators import assess_sampling

    result = assess_sampling(
        image_scale=2.155,
        seeing_fwhm_low=2.0,
        seeing_fwhm_high=4.0,
    )
    assert result.assessment == "undersampled"
    assert result.binning_recommendations[2] == "undersampled"


def test_sampling_well_sampled():
    from nightcrate.services.rig_calculators import assess_sampling

    # 1.0″/px with 2-4″ seeing → ideal range 0.67-2.0 → well sampled
    result = assess_sampling(
        image_scale=1.0,
        seeing_fwhm_low=2.0,
        seeing_fwhm_high=4.0,
    )
    assert result.assessment == "well_sampled"


# ── Seeing Resolution ───────────────────────────────────────────────────────


def test_resolve_seeing_override():
    from nightcrate.services.rig_calculators import resolve_seeing

    low, high, source, name = resolve_seeing(
        location_seeing_low=2.0,
        location_seeing_high=4.0,
        location_name="Backyard",
        override_low=1.0,
        override_high=2.0,
    )
    assert low == 1.0
    assert high == 2.0
    assert source == "override"
    assert name is None


def test_resolve_seeing_location():
    from nightcrate.services.rig_calculators import resolve_seeing

    low, high, source, name = resolve_seeing(
        location_seeing_low=2.0,
        location_seeing_high=4.0,
        location_name="Backyard Observatory",
    )
    assert low == 2.0
    assert high == 4.0
    assert source == "location"
    assert name == "Backyard Observatory"


def test_resolve_seeing_location_single_value():
    from nightcrate.services.rig_calculators import resolve_seeing

    low, high, source, name = resolve_seeing(
        location_seeing_low=2.5,
        location_seeing_high=None,
        location_name="Backyard",
    )
    assert low == 2.5
    assert high == 2.5
    assert source == "location"


def test_resolve_seeing_default():
    from nightcrate.services.rig_calculators import resolve_seeing

    low, high, source, name = resolve_seeing(
        location_seeing_low=None,
        location_seeing_high=None,
        location_name=None,
    )
    assert low == 2.0
    assert high == 4.0
    assert source == "default"
    assert name is None


# ── Guide System ─────────────────────────────────────────────────────────────


def test_guide_calculations_askar_v():
    from nightcrate.services.rig_calculators import compute_guide_metrics

    scale, fov = compute_guide_metrics(
        guide_pixel_size_um=2.4,
        guide_focal_length_mm=208.0,
        guide_resolution_x=3096,
        guide_resolution_y=2080,
    )
    assert scale == pytest.approx(2.380, abs=0.005)
    # FOV ≈ 107′ × 71′
    assert fov[0] == pytest.approx(122.8, abs=1.0)
    assert fov[1] == pytest.approx(82.5, abs=1.0)


def test_guide_calculations_null_focal_length():
    from nightcrate.services.rig_calculators import compute_guide_metrics

    result = compute_guide_metrics(
        guide_pixel_size_um=2.4,
        guide_focal_length_mm=None,
        guide_resolution_x=3096,
        guide_resolution_y=2080,
    )
    assert result is None


# ── Full Calculator ──────────────────────────────────────────────────────────


def test_full_calculators_c11():
    from nightcrate.services.rig_calculators import compute_rig_calculators

    result = compute_rig_calculators(
        pixel_size_um=3.76,
        focal_length_mm=1960.0,
        focal_ratio=7.0,
        aperture_mm=280.0,
        resolution_x=6248,
        resolution_y=4176,
        sensor_width_mm=23.5,
        sensor_height_mm=15.7,
        image_circle_mm=None,
        seeing_fwhm_low=2.0,
        seeing_fwhm_high=4.0,
        seeing_source="location",
        seeing_location_name="Backyard Observatory",
    )
    assert result["image_scale_arcsec_per_pixel"] == pytest.approx(0.396, abs=0.001)
    assert result["field_of_view_deg"][0] == pytest.approx(0.688, abs=0.002)
    assert result["dawes_limit_arcsec"] == pytest.approx(0.414, abs=0.001)
    assert result["sampling_assessment"]["assessment"] == "oversampled"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_rig_calculators.py -v`
Expected: FAIL — `nightcrate.services.rig_calculators` does not exist.

- [ ] **Step 3: Implement the calculator service**

Create `backend/src/nightcrate/services/rig_calculators.py`:

```python
"""Optical calculator functions for rig configurations.

All computations are pure functions with no DB or API dependencies.
Formulas use well-established optical constants.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# arcseconds per radian, scaled for microns/mm: (3600 × 180 / π) / 1000
ARCSEC_PER_UM_PER_MM = 206.265


def compute_image_scale(pixel_size_um: float, focal_length_mm: float) -> float:
    """Image scale in arcsec/pixel."""
    return (pixel_size_um / focal_length_mm) * ARCSEC_PER_UM_PER_MM


def compute_image_scale_binned(base_scale: float) -> dict[int, float]:
    """Image scale at binning factors 1-4."""
    return {n: base_scale * n for n in range(1, 5)}


def compute_fov(
    focal_length_mm: float,
    sensor_width_mm: float | None,
    sensor_height_mm: float | None,
    resolution_x: int,
    resolution_y: int,
    pixel_size_um: float,
) -> tuple[float, float]:
    """Field of view in degrees (width, height).

    Uses arctan formula with physical sensor dims when available,
    falls back to pixel-count formula otherwise.
    """
    if sensor_width_mm and sensor_height_mm:
        w = 2 * math.atan(sensor_width_mm / (2 * focal_length_mm)) * (180 / math.pi)
        h = 2 * math.atan(sensor_height_mm / (2 * focal_length_mm)) * (180 / math.pi)
    else:
        w_mm = resolution_x * pixel_size_um / 1000
        h_mm = resolution_y * pixel_size_um / 1000
        w = 2 * math.atan(w_mm / (2 * focal_length_mm)) * (180 / math.pi)
        h = 2 * math.atan(h_mm / (2 * focal_length_mm)) * (180 / math.pi)
    return (w, h)


def compute_resolution_limits(
    aperture_mm: float,
) -> tuple[float, float, float]:
    """Returns (dawes_limit_arcsec, rayleigh_limit_arcsec, max_useful_magnification)."""
    return (
        116.0 / aperture_mm,
        138.0 / aperture_mm,
        2.0 * aperture_mm,
    )


def compute_sensor_diagonal(
    sensor_width_mm: float | None = None,
    sensor_height_mm: float | None = None,
    resolution_x: int | None = None,
    resolution_y: int | None = None,
    pixel_size_um: float | None = None,
) -> float | None:
    """Sensor diagonal in mm. Falls back to pixel-derived dimensions."""
    w = sensor_width_mm
    h = sensor_height_mm
    if w is None or h is None:
        if resolution_x is None or resolution_y is None or pixel_size_um is None:
            return None
        w = resolution_x * pixel_size_um / 1000
        h = resolution_y * pixel_size_um / 1000
    return math.sqrt(w * w + h * h)


def compute_sensor_coverage(
    sensor_diagonal_mm: float, image_circle_mm: float
) -> float:
    """Sensor coverage as percentage of image circle."""
    return (sensor_diagonal_mm / image_circle_mm) * 100


@dataclass
class SamplingResult:
    image_scale: float
    ideal_range_low: float
    ideal_range_high: float
    seeing_fwhm_low: float
    seeing_fwhm_high: float
    seeing_source: str
    seeing_location_name: str | None
    assessment: str
    recommendation: str
    binning_recommendations: dict[int, str]


def _assess(image_scale: float, ideal_low: float, ideal_high: float) -> str:
    if image_scale < ideal_low:
        return "oversampled"
    elif image_scale > ideal_high:
        return "undersampled"
    return "well_sampled"


def _recommendation_text(
    scale: float,
    assessment: str,
    seeing_low: float,
    seeing_high: float,
    seeing_source: str,
    seeing_location_name: str | None,
    binned_2x: float,
) -> str:
    seeing_range = f"{seeing_low}\u2033\u2013{seeing_high}\u2033"
    if assessment == "oversampled":
        msg = (
            f"At {scale:.2f}\u2033/pixel unbinned, this setup is oversampled for "
            f"{seeing_range} seeing. Consider 2\u00d7 binning ({binned_2x:.2f}\u2033/pixel) "
            f"for better SNR."
        )
    elif assessment == "undersampled":
        msg = (
            f"At {scale:.2f}\u2033/pixel, this setup is undersampled for "
            f"{seeing_range} seeing. Stars will appear blocky. Consider a longer "
            f"focal length or smaller pixels."
        )
    else:
        msg = (
            f"At {scale:.2f}\u2033/pixel, this setup is well-matched to "
            f"{seeing_range} seeing conditions."
        )

    if seeing_source == "location" and seeing_location_name:
        msg += f" (seeing from {seeing_location_name})"
    elif seeing_source == "default":
        msg += (
            " (using default 2\u20134\u2033 seeing \u2014 set your location\u2019s "
            "typical seeing for a more accurate assessment)"
        )
    return msg


def assess_sampling(
    image_scale: float,
    seeing_fwhm_low: float,
    seeing_fwhm_high: float,
    seeing_source: str = "default",
    seeing_location_name: str | None = None,
) -> SamplingResult:
    """Assess sampling quality for given image scale and seeing conditions."""
    ideal_low = seeing_fwhm_low / 3.0
    ideal_high = seeing_fwhm_high / 2.0
    assessment = _assess(image_scale, ideal_low, ideal_high)

    binning_recs = {}
    for n in range(1, 5):
        binning_recs[n] = _assess(image_scale * n, ideal_low, ideal_high)

    recommendation = _recommendation_text(
        image_scale,
        assessment,
        seeing_fwhm_low,
        seeing_fwhm_high,
        seeing_source,
        seeing_location_name,
        image_scale * 2,
    )

    return SamplingResult(
        image_scale=image_scale,
        ideal_range_low=ideal_low,
        ideal_range_high=ideal_high,
        seeing_fwhm_low=seeing_fwhm_low,
        seeing_fwhm_high=seeing_fwhm_high,
        seeing_source=seeing_source,
        seeing_location_name=seeing_location_name,
        assessment=assessment,
        recommendation=recommendation,
        binning_recommendations=binning_recs,
    )


def resolve_seeing(
    location_seeing_low: float | None = None,
    location_seeing_high: float | None = None,
    location_name: str | None = None,
    override_low: float | None = None,
    override_high: float | None = None,
) -> tuple[float, float, str, str | None]:
    """Resolve seeing values through the fallback chain.

    Returns (low, high, source, location_name).
    Priority: override → location → default (2.0–4.0″).
    """
    if override_low is not None or override_high is not None:
        low = override_low if override_low is not None else override_high
        high = override_high if override_high is not None else override_low
        return (low, high, "override", None)

    if location_seeing_low is not None or location_seeing_high is not None:
        low = location_seeing_low if location_seeing_low is not None else location_seeing_high
        high = location_seeing_high if location_seeing_high is not None else location_seeing_low
        return (low, high, "location", location_name)

    return (2.0, 4.0, "default", None)


def compute_guide_metrics(
    guide_pixel_size_um: float,
    guide_focal_length_mm: float | None,
    guide_resolution_x: int,
    guide_resolution_y: int,
) -> tuple[float, tuple[float, float]] | None:
    """Compute guide camera image scale and FOV.

    Returns (scale_arcsec_per_pixel, (fov_width_arcmin, fov_height_arcmin))
    or None if focal_length_mm is missing.
    """
    if guide_focal_length_mm is None:
        return None

    scale = compute_image_scale(guide_pixel_size_um, guide_focal_length_mm)
    fov_w = (guide_resolution_x * guide_pixel_size_um * ARCSEC_PER_UM_PER_MM) / (
        guide_focal_length_mm * 60
    )
    fov_h = (guide_resolution_y * guide_pixel_size_um * ARCSEC_PER_UM_PER_MM) / (
        guide_focal_length_mm * 60
    )
    return (scale, (fov_w, fov_h))


def compute_rig_calculators(
    pixel_size_um: float,
    focal_length_mm: float,
    focal_ratio: float,
    aperture_mm: float,
    resolution_x: int,
    resolution_y: int,
    sensor_width_mm: float | None,
    sensor_height_mm: float | None,
    image_circle_mm: float | None,
    seeing_fwhm_low: float,
    seeing_fwhm_high: float,
    seeing_source: str,
    seeing_location_name: str | None,
    guide_pixel_size_um: float | None = None,
    guide_focal_length_mm: float | None = None,
    guide_resolution_x: int | None = None,
    guide_resolution_y: int | None = None,
) -> dict:
    """Compute all rig calculator results as a dict matching RigCalculators schema."""
    scale = compute_image_scale(pixel_size_um, focal_length_mm)
    binned = compute_image_scale_binned(scale)
    fov_deg = compute_fov(
        focal_length_mm, sensor_width_mm, sensor_height_mm,
        resolution_x, resolution_y, pixel_size_um,
    )
    fov_arcmin = (fov_deg[0] * 60, fov_deg[1] * 60)
    dawes, rayleigh, max_mag = compute_resolution_limits(aperture_mm)

    diag = compute_sensor_diagonal(
        sensor_width_mm, sensor_height_mm, resolution_x, resolution_y, pixel_size_um,
    )
    coverage = None
    if diag is not None and image_circle_mm is not None:
        coverage = compute_sensor_coverage(diag, image_circle_mm)

    sampling = assess_sampling(
        scale, seeing_fwhm_low, seeing_fwhm_high,
        seeing_source, seeing_location_name,
    )

    # Guide system
    guide_scale = None
    guide_fov = None
    if (
        guide_pixel_size_um is not None
        and guide_resolution_x is not None
        and guide_resolution_y is not None
    ):
        guide_result = compute_guide_metrics(
            guide_pixel_size_um, guide_focal_length_mm,
            guide_resolution_x, guide_resolution_y,
        )
        if guide_result is not None:
            guide_scale, guide_fov = guide_result

    return {
        "image_scale_arcsec_per_pixel": scale,
        "image_scale_arcsec_per_pixel_binned": binned,
        "field_of_view_arcmin": fov_arcmin,
        "field_of_view_deg": fov_deg,
        "focal_ratio": focal_ratio,
        "dawes_limit_arcsec": dawes,
        "rayleigh_limit_arcsec": rayleigh,
        "max_useful_magnification": max_mag,
        "sensor_diagonal_mm": diag,
        "image_circle_mm": image_circle_mm,
        "sensor_coverage_pct": coverage,
        "sampling_assessment": {
            "image_scale": sampling.image_scale,
            "ideal_range_low": sampling.ideal_range_low,
            "ideal_range_high": sampling.ideal_range_high,
            "seeing_fwhm_low": sampling.seeing_fwhm_low,
            "seeing_fwhm_high": sampling.seeing_fwhm_high,
            "seeing_source": sampling.seeing_source,
            "seeing_location_name": sampling.seeing_location_name,
            "assessment": sampling.assessment,
            "recommendation": sampling.recommendation,
            "binning_recommendations": sampling.binning_recommendations,
        },
        "guide_image_scale_arcsec_per_pixel": guide_scale,
        "guide_field_of_view_arcmin": guide_fov,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_rig_calculators.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/nightcrate/services/rig_calculators.py backend/tests/test_rig_calculators.py
git commit -m "feat: add rig optical calculator service with pinned regression tests"
```

---

## Task 3: Rig migration and Pydantic models

**Files:**
- Create: `backend/src/nightcrate/db/migrations/0009.rig.sql`
- Create: `backend/src/nightcrate/api/rig_models.py`

- [ ] **Step 1: Create the rig migration**

Create `backend/src/nightcrate/db/migrations/0009.rig.sql`:

```sql
-- depends: 0008.weather_cache

-- Rig: user-composed equipment template for imaging configurations.

CREATE TABLE IF NOT EXISTS rig (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,

    -- Required slots
    telescope_configuration_id INTEGER NOT NULL
        REFERENCES telescope_configuration(id),
    camera_id INTEGER NOT NULL
        REFERENCES camera(id),

    -- Optional slots
    filter_wheel_id INTEGER REFERENCES filter_wheel(id),
    single_filter_id INTEGER REFERENCES filter(id),
    mount_id INTEGER REFERENCES mount(id),
    focuser_id INTEGER REFERENCES focuser(id),
    oag_id INTEGER REFERENCES oag(id),
    guide_scope_id INTEGER REFERENCES guide_scope(id),
    guide_camera_id INTEGER REFERENCES camera(id),
    computer_id INTEGER REFERENCES computer(id),
    software_id INTEGER REFERENCES software(id),

    -- Metadata
    is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_rig_one_default
    ON rig(is_default)
    WHERE is_default = 1;

CREATE INDEX IF NOT EXISTS idx_rig_telescope_configuration ON rig(telescope_configuration_id);
CREATE INDEX IF NOT EXISTS idx_rig_camera ON rig(camera_id);

CREATE TRIGGER IF NOT EXISTS trg_rig_updated_at
AFTER UPDATE ON rig
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE rig SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- Filter slot junction table (rig-scoped, not filter-wheel-scoped).
CREATE TABLE IF NOT EXISTS rig_filter_slot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rig_id INTEGER NOT NULL REFERENCES rig(id) ON DELETE CASCADE,
    slot_number INTEGER NOT NULL CHECK (slot_number >= 1),
    filter_id INTEGER NOT NULL REFERENCES filter(id),
    UNIQUE (rig_id, slot_number),
    UNIQUE (rig_id, filter_id)
);

CREATE INDEX IF NOT EXISTS idx_rig_filter_slot_rig ON rig_filter_slot(rig_id);

-- Convenience view resolving all equipment names for rig listing.
CREATE VIEW IF NOT EXISTS rig_summary AS
SELECT
    r.id,
    r.name,
    r.description,
    r.is_default,
    r.active,
    r.notes,
    r.created_at,
    r.updated_at,
    -- OTA
    r.telescope_configuration_id,
    t.model_name AS telescope_name,
    tc.config_name AS telescope_config_name,
    tc.effective_focal_length_mm,
    tc.effective_focal_ratio,
    tc.effective_image_circle_mm,
    t.aperture_mm,
    -- Camera
    r.camera_id,
    c.model_name AS camera_name,
    s.pixel_size_um,
    s.resolution_x AS sensor_resolution_x,
    s.resolution_y AS sensor_resolution_y,
    s.sensor_width_mm,
    s.sensor_height_mm,
    s.sensor_type,
    -- Mount
    r.mount_id,
    m.model_name AS mount_name,
    -- Filter wheel
    r.filter_wheel_id,
    fw.model_name AS filter_wheel_name,
    fw.num_positions AS filter_wheel_positions,
    -- Focuser
    r.focuser_id,
    foc.model_name AS focuser_name,
    -- Guide
    r.guide_camera_id,
    gc.model_name AS guide_camera_name,
    r.guide_scope_id,
    gs.model_name AS guide_scope_name,
    gs.focal_length_mm AS guide_scope_focal_length_mm,
    r.oag_id,
    oag.model_name AS oag_name,
    -- Guide camera sensor (for guide calculator)
    gs2.pixel_size_um AS guide_pixel_size_um,
    gs2.resolution_x AS guide_resolution_x,
    gs2.resolution_y AS guide_resolution_y,
    -- Peripherals
    r.computer_id,
    comp.model_name AS computer_name,
    r.software_id,
    sw.name AS software_name,
    -- Single filter
    r.single_filter_id,
    sf.model_name AS single_filter_name
FROM rig r
JOIN telescope_configuration tc ON tc.id = r.telescope_configuration_id
JOIN telescope t ON t.id = tc.telescope_id
JOIN camera c ON c.id = r.camera_id
JOIN sensor s ON s.id = c.sensor_id
LEFT JOIN mount m ON m.id = r.mount_id
LEFT JOIN filter_wheel fw ON fw.id = r.filter_wheel_id
LEFT JOIN focuser foc ON foc.id = r.focuser_id
LEFT JOIN camera gc ON gc.id = r.guide_camera_id
LEFT JOIN sensor gs2 ON gs2.id = gc.sensor_id
LEFT JOIN guide_scope gs ON gs.id = r.guide_scope_id
LEFT JOIN oag ON oag.id = r.oag_id
LEFT JOIN computer comp ON comp.id = r.computer_id
LEFT JOIN software sw ON sw.id = r.software_id
LEFT JOIN filter sf ON sf.id = r.single_filter_id;
```

- [ ] **Step 2: Create the Pydantic models**

Create `backend/src/nightcrate/api/rig_models.py`:

```python
"""Pydantic models for the rig API."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Request Models ───────────────────────────────────────────────────────────


class RigFilterSlotIn(BaseModel):
    slot_number: int = Field(ge=1)
    filter_id: int


class RigCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    telescope_configuration_id: int
    camera_id: int
    filter_wheel_id: int | None = None
    single_filter_id: int | None = None
    mount_id: int | None = None
    focuser_id: int | None = None
    oag_id: int | None = None
    guide_scope_id: int | None = None
    guide_camera_id: int | None = None
    computer_id: int | None = None
    software_id: int | None = None
    is_default: bool = False
    notes: str | None = None
    filter_slots: list[RigFilterSlotIn] = []


class RigUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    telescope_configuration_id: int | None = None
    camera_id: int | None = None
    filter_wheel_id: int | None = None
    single_filter_id: int | None = None
    mount_id: int | None = None
    focuser_id: int | None = None
    oag_id: int | None = None
    guide_scope_id: int | None = None
    guide_camera_id: int | None = None
    computer_id: int | None = None
    software_id: int | None = None
    is_default: bool | None = None
    notes: str | None = None
    filter_slots: list[RigFilterSlotIn] | None = None


# ── Response Models ──────────────────────────────────────────────────────────


class RigFilterSlotOut(BaseModel):
    slot_number: int
    filter_id: int
    filter_name: str
    filter_type_name: str
    passbands: list[str]


class RigWarning(BaseModel):
    field: str
    message: str


class SamplingAssessment(BaseModel):
    image_scale: float
    ideal_range_low: float
    ideal_range_high: float
    seeing_fwhm_low: float
    seeing_fwhm_high: float
    seeing_source: str
    seeing_location_name: str | None
    assessment: str
    recommendation: str
    binning_recommendations: dict[int, str]


class RigCalculators(BaseModel):
    image_scale_arcsec_per_pixel: float
    image_scale_arcsec_per_pixel_binned: dict[int, float]
    field_of_view_arcmin: tuple[float, float]
    field_of_view_deg: tuple[float, float]
    focal_ratio: float
    dawes_limit_arcsec: float
    rayleigh_limit_arcsec: float
    max_useful_magnification: float
    sensor_diagonal_mm: float | None
    image_circle_mm: float | None
    sensor_coverage_pct: float | None
    sampling_assessment: SamplingAssessment
    guide_image_scale_arcsec_per_pixel: float | None = None
    guide_field_of_view_arcmin: tuple[float, float] | None = None


class RigOut(BaseModel):
    id: int
    name: str
    description: str | None
    telescope_configuration_id: int
    telescope_name: str
    telescope_config_name: str
    effective_focal_length_mm: float
    effective_focal_ratio: float
    aperture_mm: float
    camera_id: int
    camera_name: str
    pixel_size_um: float
    sensor_resolution_x: int
    sensor_resolution_y: int
    sensor_width_mm: float | None
    sensor_height_mm: float | None
    sensor_type: str
    filter_wheel_id: int | None
    filter_wheel_name: str | None
    filter_wheel_positions: int | None
    single_filter_id: int | None
    single_filter_name: str | None
    mount_id: int | None
    mount_name: str | None
    focuser_id: int | None
    focuser_name: str | None
    oag_id: int | None
    oag_name: str | None
    guide_scope_id: int | None
    guide_scope_name: str | None
    guide_scope_focal_length_mm: float | None
    guide_camera_id: int | None
    guide_camera_name: str | None
    computer_id: int | None
    computer_name: str | None
    software_id: int | None
    software_name: str | None
    filter_slots: list[RigFilterSlotOut]
    is_default: bool
    active: bool
    notes: str | None
    created_at: str
    updated_at: str
    calculators: RigCalculators
    warnings: list[RigWarning]


# ── Equipment Options ────────────────────────────────────────────────────────


class TelescopeConfigOption(BaseModel):
    id: int
    config_name: str
    effective_focal_length_mm: float
    effective_focal_ratio: float
    effective_image_circle_mm: float | None


class TelescopeWithConfigs(BaseModel):
    telescope_id: int
    telescope_name: str
    manufacturer_name: str
    aperture_mm: float
    configs: list[TelescopeConfigOption]


class CameraOption(BaseModel):
    id: int
    model_name: str
    manufacturer_name: str
    pixel_size_um: float
    resolution_x: int
    resolution_y: int
    sensor_width_mm: float | None
    sensor_height_mm: float | None
    sensor_type: str


class FilterWheelOption(BaseModel):
    id: int
    model_name: str
    manufacturer_name: str
    num_positions: int


class FilterOption(BaseModel):
    id: int
    model_name: str
    manufacturer_name: str
    filter_type_name: str


class MountOption(BaseModel):
    id: int
    model_name: str
    manufacturer_name: str


class FocuserOption(BaseModel):
    id: int
    model_name: str
    manufacturer_name: str


class OagOption(BaseModel):
    id: int
    model_name: str
    manufacturer_name: str


class GuideScopeOption(BaseModel):
    id: int
    model_name: str
    manufacturer_name: str
    focal_length_mm: float | None


class ComputerOption(BaseModel):
    id: int
    model_name: str
    manufacturer_name: str


class SoftwareOption(BaseModel):
    id: int
    name: str
    category: str


class EquipmentOptionsOut(BaseModel):
    telescopes: list[TelescopeWithConfigs]
    cameras: list[CameraOption]
    filter_wheels: list[FilterWheelOption]
    filters: list[FilterOption]
    mounts: list[MountOption]
    focusers: list[FocuserOption]
    oags: list[OagOption]
    guide_scopes: list[GuideScopeOption]
    computers: list[ComputerOption]
    software: list[SoftwareOption]
```

- [ ] **Step 3: Verify migration applies cleanly**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_rig_calculators.py -v`
Expected: Still passes (migration is applied by conftest automatically).

- [ ] **Step 4: Commit**

```bash
git add backend/src/nightcrate/db/migrations/0009.rig.sql backend/src/nightcrate/api/rig_models.py
git commit -m "feat: add rig migration schema and Pydantic models"
```

---

## Task 4: Rig API — CRUD endpoints

**Files:**
- Create: `backend/src/nightcrate/api/rigs.py`
- Modify: `backend/src/nightcrate/main.py`
- Test: `backend/tests/test_rig_api.py`

This is the largest task. It implements all rig CRUD operations with validation, filter slot handling, calculator integration, and equipment options.

- [ ] **Step 1: Write failing tests for rig CRUD**

Create `backend/tests/test_rig_api.py`. This file needs helper functions to insert seed equipment (telescope, camera, sensor, manufacturer, etc.) before testing rig operations. The tests use the same `AsyncClient` + `ASGITransport` pattern as `test_locations_api.py`.

```python
"""Tests for rig API endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.db.session import get_db
from nightcrate.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


async def _seed_equipment():
    """Insert minimal equipment for rig tests. Returns dict of created IDs."""
    async with get_db() as conn:
        # Manufacturer
        await conn.execute(
            "INSERT INTO manufacturer (name, country, active, source) "
            "VALUES ('ZWO', 'CN', 1, 'user')"
        )
        mfr = (await (await conn.execute("SELECT last_insert_rowid()")).fetchone())[0]

        # Sensor
        await conn.execute(
            "INSERT INTO sensor (manufacturer_id, model_name, sensor_type, "
            "pixel_size_um, resolution_x, resolution_y, sensor_width_mm, "
            "sensor_height_mm, active, source) "
            "VALUES (?, 'IMX571', 'mono', 3.76, 6248, 4176, 23.5, 15.7, 1, 'user')",
            (mfr,),
        )
        sensor = (await (await conn.execute("SELECT last_insert_rowid()")).fetchone())[0]

        # Guide sensor
        await conn.execute(
            "INSERT INTO sensor (manufacturer_id, model_name, sensor_type, "
            "pixel_size_um, resolution_x, resolution_y, active, source) "
            "VALUES (?, 'IMX178', 'mono', 2.4, 3096, 2080, 1, 'user')",
            (mfr,),
        )
        guide_sensor = (await (await conn.execute("SELECT last_insert_rowid()")).fetchone())[0]

        # Camera
        await conn.execute(
            "INSERT INTO camera (manufacturer_id, sensor_id, model_name, cooled, "
            "tilt_adapter, has_usb_hub, active, source) "
            "VALUES (?, ?, 'ASI 2600MM Pro', 1, 0, 0, 1, 'user')",
            (mfr, sensor),
        )
        camera = (await (await conn.execute("SELECT last_insert_rowid()")).fetchone())[0]

        # Guide camera
        await conn.execute(
            "INSERT INTO camera (manufacturer_id, sensor_id, model_name, cooled, "
            "tilt_adapter, has_usb_hub, active, source) "
            "VALUES (?, ?, 'ASI 178MM', 0, 0, 0, 1, 'user')",
            (mfr, guide_sensor),
        )
        guide_camera = (await (await conn.execute("SELECT last_insert_rowid()")).fetchone())[0]

        # Telescope
        await conn.execute(
            "INSERT INTO manufacturer (name, country, active, source) "
            "VALUES ('Celestron', 'US', 1, 'user')"
        )
        cel_mfr = (await (await conn.execute("SELECT last_insert_rowid()")).fetchone())[0]

        # Need optical_design for telescope
        await conn.execute(
            "INSERT INTO optical_design (name, active, source) VALUES ('SCT', 1, 'user')"
        )
        od = (await (await conn.execute("SELECT last_insert_rowid()")).fetchone())[0]

        await conn.execute(
            "INSERT INTO telescope (manufacturer_id, optical_design_id, model_name, "
            "aperture_mm, active, source) "
            "VALUES (?, ?, 'C11', 280.0, 1, 'user')",
            (cel_mfr, od),
        )
        telescope = (await (await conn.execute("SELECT last_insert_rowid()")).fetchone())[0]

        # Telescope configuration
        await conn.execute(
            "INSERT INTO telescope_configuration (telescope_id, config_name, "
            "reduction_factor, effective_focal_length_mm, effective_focal_ratio, "
            "is_native, active, source) "
            "VALUES (?, '0.7x Reducer', 0.7, 1960.0, 7.0, 0, 1, 'user')",
            (telescope,),
        )
        tc = (await (await conn.execute("SELECT last_insert_rowid()")).fetchone())[0]

        # Filter wheel
        await conn.execute(
            "INSERT INTO filter_wheel (manufacturer_id, model_name, num_positions, "
            "active, source) "
            "VALUES (?, '7-pos Wheel', 7, 1, 'user')",
            (mfr,),
        )
        fw = (await (await conn.execute("SELECT last_insert_rowid()")).fetchone())[0]

        # Filters — need a filter_type first
        ft_row = await conn.execute(
            "SELECT id FROM filter_type WHERE name = 'luminance' LIMIT 1"
        )
        ft = (await ft_row.fetchone())[0]

        filter_ids = []
        for fname in ["Luminance", "Red", "Green", "Blue", "Ha 7nm", "Oiii 7nm", "Sii 7nm"]:
            await conn.execute(
                "INSERT INTO filter (manufacturer_id, filter_type_id, model_name, "
                "active, source) VALUES (?, ?, ?, 1, 'user')",
                (mfr, ft, fname),
            )
            fid = (await (await conn.execute("SELECT last_insert_rowid()")).fetchone())[0]
            filter_ids.append(fid)

        # Mount
        await conn.execute(
            "INSERT INTO manufacturer (name, country, active, source) "
            "VALUES ('WarpAstron', 'CN', 1, 'user')"
        )
        wa_mfr = (await (await conn.execute("SELECT last_insert_rowid()")).fetchone())[0]

        # Need mount_type
        await conn.execute(
            "INSERT INTO mount_type (name, active, source) VALUES ('EQ', 1, 'user')"
        )
        mt = (await (await conn.execute("SELECT last_insert_rowid()")).fetchone())[0]

        await conn.execute(
            "INSERT INTO mount (manufacturer_id, mount_type_id, model_name, "
            "active, source) "
            "VALUES (?, ?, 'WD-20', 1, 'user')",
            (wa_mfr, mt),
        )
        mount = (await (await conn.execute("SELECT last_insert_rowid()")).fetchone())[0]

        # Guide scope
        await conn.execute(
            "INSERT INTO manufacturer (name, country, active, source) "
            "VALUES ('Askar', 'CN', 1, 'user')"
        )
        askar_mfr = (await (await conn.execute("SELECT last_insert_rowid()")).fetchone())[0]

        await conn.execute(
            "INSERT INTO guide_scope (manufacturer_id, model_name, aperture_mm, "
            "focal_length_mm, active, source) "
            "VALUES (?, '52mm f/4', 52.0, 208.0, 1, 'user')",
            (askar_mfr,),
        )
        guide_scope = (await (await conn.execute("SELECT last_insert_rowid()")).fetchone())[0]

        await conn.commit()

        return {
            "camera_id": camera,
            "guide_camera_id": guide_camera,
            "telescope_configuration_id": tc,
            "filter_wheel_id": fw,
            "filter_ids": filter_ids,
            "mount_id": mount,
            "guide_scope_id": guide_scope,
        }


@pytest.fixture
async def equipment():
    return await _seed_equipment()


def _rig_payload(eq, **overrides):
    """Build a minimal rig creation payload."""
    base = {
        "name": "C11 Deep Sky",
        "telescope_configuration_id": eq["telescope_configuration_id"],
        "camera_id": eq["camera_id"],
    }
    base.update(overrides)
    return base


# ── CRUD Tests ───────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_create_rig(client, equipment):
    payload = _rig_payload(equipment)
    resp = await client.post("/api/rigs", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "C11 Deep Sky"
    assert data["camera_name"] == "ASI 2600MM Pro"
    assert data["telescope_config_name"] == "0.7x Reducer"
    assert data["calculators"]["image_scale_arcsec_per_pixel"] == pytest.approx(0.396, abs=0.001)


@pytest.mark.anyio
async def test_list_rigs(client, equipment):
    await client.post("/api/rigs", json=_rig_payload(equipment))
    resp = await client.get("/api/rigs")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "C11 Deep Sky"


@pytest.mark.anyio
async def test_get_rig(client, equipment):
    create_resp = await client.post("/api/rigs", json=_rig_payload(equipment))
    rig_id = create_resp.json()["id"]
    resp = await client.get(f"/api/rigs/{rig_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == rig_id


@pytest.mark.anyio
async def test_update_rig(client, equipment):
    create_resp = await client.post("/api/rigs", json=_rig_payload(equipment))
    rig_id = create_resp.json()["id"]
    resp = await client.put(f"/api/rigs/{rig_id}", json={"name": "C11 Narrowband"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "C11 Narrowband"


@pytest.mark.anyio
async def test_soft_delete_rig(client, equipment):
    create_resp = await client.post("/api/rigs", json=_rig_payload(equipment))
    rig_id = create_resp.json()["id"]
    resp = await client.delete(f"/api/rigs/{rig_id}")
    assert resp.status_code == 204

    # Should not appear in active list
    list_resp = await client.get("/api/rigs")
    assert len(list_resp.json()) == 0

    # Should appear with active_only=false
    list_resp = await client.get("/api/rigs?active_only=false")
    assert len(list_resp.json()) == 1


@pytest.mark.anyio
async def test_restore_rig(client, equipment):
    create_resp = await client.post("/api/rigs", json=_rig_payload(equipment))
    rig_id = create_resp.json()["id"]
    await client.delete(f"/api/rigs/{rig_id}")
    resp = await client.post(f"/api/rigs/{rig_id}/restore")
    assert resp.status_code == 200
    assert resp.json()["active"] is True


# ── Filter Slots ─────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_create_rig_with_filter_slots(client, equipment):
    payload = _rig_payload(
        equipment,
        filter_wheel_id=equipment["filter_wheel_id"],
        filter_slots=[
            {"slot_number": 1, "filter_id": equipment["filter_ids"][0]},
            {"slot_number": 2, "filter_id": equipment["filter_ids"][1]},
        ],
    )
    resp = await client.post("/api/rigs", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert len(data["filter_slots"]) == 2
    assert data["filter_slots"][0]["slot_number"] == 1
    assert data["filter_slots"][1]["slot_number"] == 2


@pytest.mark.anyio
async def test_update_replaces_filter_slots(client, equipment):
    payload = _rig_payload(
        equipment,
        filter_wheel_id=equipment["filter_wheel_id"],
        filter_slots=[{"slot_number": 1, "filter_id": equipment["filter_ids"][0]}],
    )
    create_resp = await client.post("/api/rigs", json=payload)
    rig_id = create_resp.json()["id"]

    # Replace with different slots
    resp = await client.put(
        f"/api/rigs/{rig_id}",
        json={"filter_slots": [{"slot_number": 3, "filter_id": equipment["filter_ids"][2]}]},
    )
    assert resp.status_code == 200
    slots = resp.json()["filter_slots"]
    assert len(slots) == 1
    assert slots[0]["slot_number"] == 3


@pytest.mark.anyio
async def test_remove_filter_wheel_clears_slots(client, equipment):
    payload = _rig_payload(
        equipment,
        filter_wheel_id=equipment["filter_wheel_id"],
        filter_slots=[{"slot_number": 1, "filter_id": equipment["filter_ids"][0]}],
    )
    create_resp = await client.post("/api/rigs", json=payload)
    rig_id = create_resp.json()["id"]

    resp = await client.put(f"/api/rigs/{rig_id}", json={"filter_wheel_id": None})
    assert resp.status_code == 200
    assert resp.json()["filter_wheel_id"] is None
    assert resp.json()["filter_slots"] == []


# ── Validation ───────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_slot_number_exceeds_wheel_capacity(client, equipment):
    payload = _rig_payload(
        equipment,
        filter_wheel_id=equipment["filter_wheel_id"],
        filter_slots=[{"slot_number": 8, "filter_id": equipment["filter_ids"][0]}],
    )
    resp = await client.post("/api/rigs", json=payload)
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_filter_slots_without_wheel_rejected(client, equipment):
    payload = _rig_payload(
        equipment,
        filter_slots=[{"slot_number": 1, "filter_id": equipment["filter_ids"][0]}],
    )
    resp = await client.post("/api/rigs", json=payload)
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_duplicate_name_rejected(client, equipment):
    await client.post("/api/rigs", json=_rig_payload(equipment))
    resp = await client.post("/api/rigs", json=_rig_payload(equipment))
    assert resp.status_code == 409


# ── Default Flag ─────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_set_default_clears_others(client, equipment):
    r1 = await client.post("/api/rigs", json=_rig_payload(equipment, is_default=True))
    r2 = await client.post(
        "/api/rigs",
        json=_rig_payload(equipment, name="Rig 2", is_default=True),
    )
    assert r2.status_code == 201

    # First rig should no longer be default
    r1_data = await client.get(f"/api/rigs/{r1.json()['id']}")
    assert r1_data.json()["is_default"] is False
    assert r2.json()["is_default"] is True


# ── Clone ────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_clone_rig(client, equipment):
    payload = _rig_payload(
        equipment,
        filter_wheel_id=equipment["filter_wheel_id"],
        filter_slots=[{"slot_number": 1, "filter_id": equipment["filter_ids"][0]}],
    )
    create_resp = await client.post("/api/rigs", json=payload)
    rig_id = create_resp.json()["id"]

    resp = await client.post(f"/api/rigs/{rig_id}/clone")
    assert resp.status_code == 201
    clone = resp.json()
    assert clone["name"] == "C11 Deep Sky (Copy)"
    assert clone["is_default"] is False
    assert len(clone["filter_slots"]) == 1


@pytest.mark.anyio
async def test_clone_name_collision(client, equipment):
    payload = _rig_payload(equipment)
    create_resp = await client.post("/api/rigs", json=payload)
    rig_id = create_resp.json()["id"]

    # First clone
    await client.post(f"/api/rigs/{rig_id}/clone")
    # Second clone — name collision with "(Copy)", should get "(Copy 2)"
    resp = await client.post(f"/api/rigs/{rig_id}/clone")
    assert resp.status_code == 201
    assert resp.json()["name"] == "C11 Deep Sky (Copy 2)"


# ── Warnings ─────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_guide_camera_same_as_imaging_warning(client, equipment):
    payload = _rig_payload(
        equipment,
        guide_camera_id=equipment["camera_id"],  # same as imaging camera
    )
    resp = await client.post("/api/rigs", json=payload)
    assert resp.status_code == 201
    warnings = resp.json()["warnings"]
    assert any(w["field"] == "guide_camera_id" for w in warnings)


# ── Equipment Options ────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_equipment_options(client, equipment):
    resp = await client.get("/api/rigs/equipment-options")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["telescopes"]) >= 1
    assert len(data["cameras"]) >= 1
    assert len(data["telescopes"][0]["configs"]) >= 1


# ── Calculators ──────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_calculator_endpoint(client, equipment):
    create_resp = await client.post("/api/rigs", json=_rig_payload(equipment))
    rig_id = create_resp.json()["id"]

    resp = await client.get(f"/api/rigs/{rig_id}/calculators")
    assert resp.status_code == 200
    data = resp.json()
    assert data["image_scale_arcsec_per_pixel"] == pytest.approx(0.396, abs=0.001)
    assert data["sampling_assessment"]["seeing_source"] == "default"


@pytest.mark.anyio
async def test_calculator_with_seeing_override(client, equipment):
    create_resp = await client.post("/api/rigs", json=_rig_payload(equipment))
    rig_id = create_resp.json()["id"]

    resp = await client.get(
        f"/api/rigs/{rig_id}/calculators?seeing_low=1.0&seeing_high=2.0"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sampling_assessment"]["seeing_source"] == "override"
    assert data["sampling_assessment"]["seeing_fwhm_low"] == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_rig_api.py -v`
Expected: FAIL — no `/api/rigs` router exists.

- [ ] **Step 3: Implement the rig API router**

Create `backend/src/nightcrate/api/rigs.py`. This is a large file — implement all endpoints following the patterns from `equipment.py` and `locations.py`:

Key implementation details:
- `router = APIRouter(prefix="/api/rigs", tags=["Rigs"])`
- Helper functions: `_row_to_dict`, `_bool_fields`, `_get_rig_or_404` (fetches from `rig_summary` view)
- `_build_filter_slots(conn, rig_id)` — joins rig_filter_slot → filter → filter_type, fetches passbands
- `_build_rig_response(conn, rig_row, location, override_seeing_low, override_seeing_high)` — assembles full RigOut with calculators and warnings
- `_resolve_location(conn, location_id)` — gets specified location or default location
- `_check_warnings(conn, rig_data)` — checks retired equipment, guide=imaging camera
- `_validate_filter_slots(conn, slots, filter_wheel_id)` — enforces slot_number ≤ num_positions, requires filter wheel
- Default flag management via `_ensure_single_default(conn, rig_id)`
- Clone logic: copy all fields, generate unique name with `(Copy)` / `(Copy N)` suffix
- Equipment options: one query per type with manufacturer JOIN, telescope configs grouped under parent telescopes

All SQL queries use parameterized `?` placeholders. All writes use `await conn.commit()` inside `async with get_db() as conn:` blocks.

The full implementation follows the exact patterns established in `equipment.py` — use `model_dump(exclude_unset=True)` for PUT, dynamic SET clause construction, UNIQUE constraint → 409, re-fetch after commit.

- [ ] **Step 4: Register the router in main.py**

Add to `main.py`:
1. Import: `from nightcrate.api import rigs`
2. Add OpenAPI tag (after "Locations" tag):
```python
    {
        "name": "Rigs",
        "description": (
            "Imaging rig templates: user-composed equipment configurations with "
            "optical calculators (image scale, FOV, sampling assessment). Each rig "
            "combines an OTA configuration, camera, and optional filter wheel, mount, "
            "guiding, and peripheral equipment."
        ),
    },
```
3. Register router: `app.include_router(rigs.router)` (after `locations.router`)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_rig_api.py -v`
Expected: All tests PASS.

- [ ] **Step 6: Run full backend checks**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run pytest -x -q`
Expected: All lint, format, and test checks pass.

- [ ] **Step 7: Commit**

```bash
git add backend/src/nightcrate/api/rigs.py backend/src/nightcrate/main.py backend/tests/test_rig_api.py
git commit -m "feat: add rig CRUD API with validation, filter slots, clone, and equipment options"
```

---

## Task 5: Frontend — API client and types

**Files:**
- Create: `frontend/src/api/rigs.ts`
- Modify: `frontend/src/api/locations.ts`

- [ ] **Step 1: Add seeing fields to location types**

Edit `frontend/src/api/locations.ts`:

Add to the `Location` interface:
```typescript
  typical_seeing_low_arcsec: number | null;
  typical_seeing_high_arcsec: number | null;
```

Add to the `LocationCreate` interface:
```typescript
  typical_seeing_low_arcsec?: number | null;
  typical_seeing_high_arcsec?: number | null;
```

- [ ] **Step 2: Create the rigs API client**

Create `frontend/src/api/rigs.ts`:

```typescript
import { apiFetch } from "./client";

// ── Types ─────────────────────────────────────────────────────────────────

export interface RigFilterSlotIn {
  slot_number: number;
  filter_id: number;
}

export interface RigFilterSlotOut {
  slot_number: number;
  filter_id: number;
  filter_name: string;
  filter_type_name: string;
  passbands: string[];
}

export interface RigWarning {
  field: string;
  message: string;
}

export interface SamplingAssessment {
  image_scale: number;
  ideal_range_low: number;
  ideal_range_high: number;
  seeing_fwhm_low: number;
  seeing_fwhm_high: number;
  seeing_source: string;
  seeing_location_name: string | null;
  assessment: string;
  recommendation: string;
  binning_recommendations: Record<number, string>;
}

export interface RigCalculators {
  image_scale_arcsec_per_pixel: number;
  image_scale_arcsec_per_pixel_binned: Record<number, number>;
  field_of_view_arcmin: [number, number];
  field_of_view_deg: [number, number];
  focal_ratio: number;
  dawes_limit_arcsec: number;
  rayleigh_limit_arcsec: number;
  max_useful_magnification: number;
  sensor_diagonal_mm: number | null;
  image_circle_mm: number | null;
  sensor_coverage_pct: number | null;
  sampling_assessment: SamplingAssessment;
  guide_image_scale_arcsec_per_pixel: number | null;
  guide_field_of_view_arcmin: [number, number] | null;
}

export interface Rig {
  id: number;
  name: string;
  description: string | null;
  telescope_configuration_id: number;
  telescope_name: string;
  telescope_config_name: string;
  effective_focal_length_mm: number;
  effective_focal_ratio: number;
  aperture_mm: number;
  camera_id: number;
  camera_name: string;
  pixel_size_um: number;
  sensor_resolution_x: number;
  sensor_resolution_y: number;
  sensor_width_mm: number | null;
  sensor_height_mm: number | null;
  sensor_type: string;
  filter_wheel_id: number | null;
  filter_wheel_name: string | null;
  filter_wheel_positions: number | null;
  single_filter_id: number | null;
  single_filter_name: string | null;
  mount_id: number | null;
  mount_name: string | null;
  focuser_id: number | null;
  focuser_name: string | null;
  oag_id: number | null;
  oag_name: string | null;
  guide_scope_id: number | null;
  guide_scope_name: string | null;
  guide_scope_focal_length_mm: number | null;
  guide_camera_id: number | null;
  guide_camera_name: string | null;
  computer_id: number | null;
  computer_name: string | null;
  software_id: number | null;
  software_name: string | null;
  filter_slots: RigFilterSlotOut[];
  is_default: boolean;
  active: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
  calculators: RigCalculators;
  warnings: RigWarning[];
}

export interface RigCreate {
  name: string;
  description?: string | null;
  telescope_configuration_id: number;
  camera_id: number;
  filter_wheel_id?: number | null;
  single_filter_id?: number | null;
  mount_id?: number | null;
  focuser_id?: number | null;
  oag_id?: number | null;
  guide_scope_id?: number | null;
  guide_camera_id?: number | null;
  computer_id?: number | null;
  software_id?: number | null;
  is_default?: boolean;
  notes?: string | null;
  filter_slots?: RigFilterSlotIn[];
}

export interface TelescopeConfigOption {
  id: number;
  config_name: string;
  effective_focal_length_mm: number;
  effective_focal_ratio: number;
  effective_image_circle_mm: number | null;
}

export interface TelescopeWithConfigs {
  telescope_id: number;
  telescope_name: string;
  manufacturer_name: string;
  aperture_mm: number;
  configs: TelescopeConfigOption[];
}

export interface CameraOption {
  id: number;
  model_name: string;
  manufacturer_name: string;
  pixel_size_um: number;
  resolution_x: number;
  resolution_y: number;
  sensor_width_mm: number | null;
  sensor_height_mm: number | null;
  sensor_type: string;
}

export interface FilterWheelOption {
  id: number;
  model_name: string;
  manufacturer_name: string;
  num_positions: number;
}

export interface FilterOption {
  id: number;
  model_name: string;
  manufacturer_name: string;
  filter_type_name: string;
}

export interface SimpleOption {
  id: number;
  model_name: string;
  manufacturer_name: string;
}

export interface GuideScopeOption extends SimpleOption {
  focal_length_mm: number | null;
}

export interface SoftwareOption {
  id: number;
  name: string;
  category: string;
}

export interface EquipmentOptions {
  telescopes: TelescopeWithConfigs[];
  cameras: CameraOption[];
  filter_wheels: FilterWheelOption[];
  filters: FilterOption[];
  mounts: SimpleOption[];
  focusers: SimpleOption[];
  oags: SimpleOption[];
  guide_scopes: GuideScopeOption[];
  computers: SimpleOption[];
  software: SoftwareOption[];
}

// ── Fetch Functions ──────────────────────────────────────────────────────

export const fetchRigs = (activeOnly = true) =>
  apiFetch<Rig[]>(`/rigs${activeOnly ? "" : "?active_only=false"}`);

export const fetchRig = (id: number, locationId?: number) =>
  apiFetch<Rig>(`/rigs/${id}${locationId ? `?location_id=${locationId}` : ""}`);

export const createRig = (data: RigCreate) =>
  apiFetch<Rig>("/rigs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

export const updateRig = (id: number, data: Partial<RigCreate>) =>
  apiFetch<Rig>(`/rigs/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

export const deleteRig = (id: number) =>
  apiFetch<void>(`/rigs/${id}`, { method: "DELETE" });

export const restoreRig = (id: number) =>
  apiFetch<Rig>(`/rigs/${id}/restore`, { method: "POST" });

export const cloneRig = (id: number) =>
  apiFetch<Rig>(`/rigs/${id}/clone`, { method: "POST" });

export const fetchRigCalculators = (
  id: number,
  params?: { location_id?: number; seeing_low?: number; seeing_high?: number }
) => {
  const query = new URLSearchParams();
  if (params?.location_id) query.set("location_id", String(params.location_id));
  if (params?.seeing_low) query.set("seeing_low", String(params.seeing_low));
  if (params?.seeing_high) query.set("seeing_high", String(params.seeing_high));
  const qs = query.toString();
  return apiFetch<RigCalculators>(`/rigs/${id}/calculators${qs ? `?${qs}` : ""}`);
};

export const fetchEquipmentOptions = () =>
  apiFetch<EquipmentOptions>("/rigs/equipment-options");
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npx tsc --noEmit`
Expected: No type errors (new files are valid TypeScript, location types extended correctly).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/rigs.ts frontend/src/api/locations.ts
git commit -m "feat: add rig API client types and fetch functions"
```

---

## Task 6: Frontend — Location seeing fields in form

**Files:**
- Modify: `frontend/src/pages/LocationsPage.tsx`

- [ ] **Step 1: Add seeing fields to the location form**

Edit `frontend/src/pages/LocationsPage.tsx`:

1. Add to `FormState` interface:
```typescript
  typical_seeing_low_arcsec: string;
  typical_seeing_high_arcsec: string;
```

2. Add to `emptyForm()`:
```typescript
    typical_seeing_low_arcsec: "",
    typical_seeing_high_arcsec: "",
```

3. Add to `locationToForm()`:
```typescript
    typical_seeing_low_arcsec: loc.typical_seeing_low_arcsec != null ? String(loc.typical_seeing_low_arcsec) : "",
    typical_seeing_high_arcsec: loc.typical_seeing_high_arcsec != null ? String(loc.typical_seeing_high_arcsec) : "",
```

4. Add to validation in `handleSave` (after the SQM validation block):
```typescript
    if (form.typical_seeing_low_arcsec.trim()) {
      const v = parseFloat(form.typical_seeing_low_arcsec);
      if (isNaN(v) || v <= 0) e.typical_seeing_low_arcsec = "Must be positive";
    }
    if (form.typical_seeing_high_arcsec.trim()) {
      const v = parseFloat(form.typical_seeing_high_arcsec);
      if (isNaN(v) || v <= 0) e.typical_seeing_high_arcsec = "Must be positive";
    }
    if (form.typical_seeing_low_arcsec.trim() && form.typical_seeing_high_arcsec.trim()) {
      const low = parseFloat(form.typical_seeing_low_arcsec);
      const high = parseFloat(form.typical_seeing_high_arcsec);
      if (!isNaN(low) && !isNaN(high) && low > high) {
        e.typical_seeing_high_arcsec = "Must be ≥ best seeing";
      }
    }
```

5. Add seeing fields to the `payload` construction in `handleSave`:
```typescript
        typical_seeing_low_arcsec: parseOptionalFloat(form.typical_seeing_low_arcsec),
        typical_seeing_high_arcsec: parseOptionalFloat(form.typical_seeing_high_arcsec),
```

6. Add UI fields in the form dialog, after the Bortle/SQM section and before the Notes field. Add a new "Seeing Conditions" section with a collapsible reference guide:

```tsx
            {/* Seeing Conditions */}
            <Typography variant="subtitle2" sx={{ mt: 1, mb: -0.5 }}>
              Seeing Conditions
            </Typography>
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2 }}>
              <TextField
                label="Best Typical Seeing"
                type="number"
                value={form.typical_seeing_low_arcsec}
                onChange={(e) => set("typical_seeing_low_arcsec", e.target.value)}
                error={Boolean(errors.typical_seeing_low_arcsec)}
                helperText={errors.typical_seeing_low_arcsec || 'FWHM in arcseconds (e.g. 2.0)'}
                slotProps={{ htmlInput: { step: "any", min: 0.1 } }}
              />
              <TextField
                label="Worst Typical Seeing"
                type="number"
                value={form.typical_seeing_high_arcsec}
                onChange={(e) => set("typical_seeing_high_arcsec", e.target.value)}
                error={Boolean(errors.typical_seeing_high_arcsec)}
                helperText={errors.typical_seeing_high_arcsec || 'FWHM in arcseconds (e.g. 4.0)'}
                slotProps={{ htmlInput: { step: "any", min: 0.1 } }}
              />
            </Box>
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ mt: -1, cursor: "pointer" }}
              onClick={() => setSeeingGuideOpen((v) => !v)}
            >
              {seeingGuideOpen ? "▾" : "▸"} How to estimate your seeing
            </Typography>
            {seeingGuideOpen && (
              <Box sx={{ ml: 1, mt: 0.5, fontSize: "0.75rem", color: "text.secondary" }}>
                <Typography variant="caption" component="p" sx={{ mb: 0.5 }}>
                  Estimate from the FWHM of stars in your processed subs, or use these guidelines:
                </Typography>
                <Box component="table" sx={{ "& td, & th": { px: 1, py: 0.25, fontSize: "0.75rem" } }}>
                  <thead>
                    <tr><th align="left">Site Type</th><th align="left">Typical Range</th></tr>
                  </thead>
                  <tbody>
                    <tr><td>Mountain observatory (&gt;2000m)</td><td>0.5–1.5″</td></tr>
                    <tr><td>Rural dark site</td><td>1.5–3.0″</td></tr>
                    <tr><td>Suburban backyard</td><td>2.0–4.0″</td></tr>
                    <tr><td>Urban / rooftop</td><td>3.0–5.0″</td></tr>
                  </tbody>
                </Box>
                <Typography variant="caption" component="p" sx={{ mt: 0.5 }}>
                  Used by Rig calculators to assess whether your equipment matches your site conditions.
                </Typography>
              </Box>
            )}
```

7. Add `seeingGuideOpen` state near the other state declarations:
```typescript
  const [seeingGuideOpen, setSeeingGuideOpen] = useState(false);
```

- [ ] **Step 2: Verify frontend builds**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npm run build`
Expected: Build succeeds with no type errors.

- [ ] **Step 3: Test manually**

Run: `cd /Users/fbaptiste/dev/nightcrate && make dev`
Navigate to `/locations`, edit a location, verify the seeing fields appear and save correctly.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/LocationsPage.tsx
git commit -m "feat: add seeing condition fields to location form with reference guide"
```

---

## Task 7: Frontend — Rigs page with card list

**Files:**
- Create: `frontend/src/pages/RigsPage.tsx`
- Create: `frontend/src/components/rigs/RigCard.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/AppShell.tsx`

- [ ] **Step 1: Create the RigCard component**

Create `frontend/src/components/rigs/RigCard.tsx`:

A card showing rig name, equipment summary, key stats, sampling badge, and action buttons (Edit, Clone, Delete, Set Default, Restore). Uses MUI `Card` component. Sampling badge uses blue (well_sampled) and orange (oversampled/undersampled) — never red/green.

Key stats line: `"{focal_length}mm f/{focal_ratio} {image_scale}″/px {fov_width}×{fov_height}′"`

Filter summary: `"7-pos: L R G B Ha Oiii Sii"` or `"No filter wheel"`.

- [ ] **Step 2: Create the RigsPage**

Create `frontend/src/pages/RigsPage.tsx`:

Uses `useQuery` to fetch rigs. Renders a grid of `RigCard` components. Active rigs shown first, retired rigs in a collapsible "Retired" section. "New Rig" button at the top opens the `RigFormDialog`.

- [ ] **Step 3: Add route and nav item**

Edit `frontend/src/App.tsx`:
- Import: `import RigsPage from "./pages/RigsPage";`
- Add route: `{ path: "rigs", element: <RigsPage /> }` (after "locations" route)

Edit `frontend/src/components/AppShell.tsx`:
- Import: `import PrecisionManufacturingIcon from "@mui/icons-material/PrecisionManufacturing";`
- Add nav item after Locations: `{ to: "/rigs", label: "Rigs", icon: <PrecisionManufacturingIcon /> }`

- [ ] **Step 4: Verify frontend builds**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 5: Test manually**

Run: `cd /Users/fbaptiste/dev/nightcrate && make dev`
Navigate to `/rigs`. Verify the page loads (empty state with "New Rig" button). Verify nav item appears.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/RigsPage.tsx frontend/src/components/rigs/RigCard.tsx frontend/src/App.tsx frontend/src/components/AppShell.tsx
git commit -m "feat: add rigs page with card list and navigation"
```

---

## Task 8: Frontend — Rig form dialog

**Files:**
- Create: `frontend/src/components/rigs/RigFormDialog.tsx`
- Create: `frontend/src/components/rigs/FilterSlotGrid.tsx`

- [ ] **Step 1: Create FilterSlotGrid component**

Create `frontend/src/components/rigs/FilterSlotGrid.tsx`:

Shows N rows (driven by `numPositions` prop), each with a slot number label and a filter Autocomplete dropdown. Accepts `filters: FilterOption[]`, `slots: RigFilterSlotIn[]`, and `onChange: (slots: RigFilterSlotIn[]) => void`.

- [ ] **Step 2: Create RigFormDialog component**

Create `frontend/src/components/rigs/RigFormDialog.tsx`:

Modal dialog for create and edit. Uses `{ open, rig, onClose, onSaved }` prop interface matching the established pattern. Sections:

1. **Identity** — Name (required), Description
2. **Optical Train** — Telescope config (grouped Autocomplete: configs nested under telescope names), Imaging Camera (Autocomplete)
3. **Filtration** — Filter Wheel (Autocomplete, optional). When selected, renders `FilterSlotGrid`. Single Filter (Autocomplete, optional — shown when no filter wheel).
4. **Mount & Guiding** — Mount, Guiding mode radio (OAG / Guide Scope / None), conditional OAG/Guide Scope/Guide Camera dropdowns
5. **Peripherals** — Focuser, Computer, Capture Software
6. **Options** — Default rig switch, Notes textarea

All dropdowns use Autocomplete with `getOptionLabel` showing `"{manufacturer} — {model}"`. Fetches equipment options via `useQuery(["equipment-options"], fetchEquipmentOptions)`.

Live calculator preview: When both telescope config and camera are selected, compute and show basic metrics client-side (image scale, FOV) in a side panel or below the form. Uses the formulas from the spec directly in JS:
```typescript
const imageScale = (pixelSize / focalLength) * 206.265;
```

Save: calls `createRig()` or `updateRig()`. Error → Snackbar. Success → `onSaved()` + close.

- [ ] **Step 3: Wire dialog into RigsPage**

Update `RigsPage.tsx` to render `RigFormDialog` and open it on "New Rig" click and card Edit action.

- [ ] **Step 4: Verify frontend builds**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 5: Test manually**

Run: `cd /Users/fbaptiste/dev/nightcrate && make dev`
Navigate to `/rigs`. Click "New Rig". Verify:
- All dropdowns populate from equipment options
- Telescope configs grouped under telescope names
- Filter slot grid appears when filter wheel selected
- Live calculator preview shows when OTA + camera selected
- Save creates a rig and card appears in the list

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/rigs/RigFormDialog.tsx frontend/src/components/rigs/FilterSlotGrid.tsx frontend/src/pages/RigsPage.tsx
git commit -m "feat: add rig form dialog with equipment dropdowns and filter slot grid"
```

---

## Task 9: Frontend — Calculator panel with D3 sampling chart

**Files:**
- Create: `frontend/src/components/rigs/CalculatorPanel.tsx`
- Create: `frontend/src/components/rigs/SamplingChart.tsx`

- [ ] **Step 1: Create SamplingChart component**

Create `frontend/src/components/rigs/SamplingChart.tsx`:

D3 horizontal bar chart showing image scale at binning levels 1-4 plotted against the ideal sampling zone. Uses `useRef` + `useEffect` pattern for D3 rendering (same as `HourlyTimeline.tsx`).

- X-axis: arcsec/pixel
- Y-axis: binning levels (1×1, 2×2, 3×3, 4×4)
- Shaded region: ideal sampling zone (seeing_fwhm_low/3 to seeing_fwhm_high/2)
- Bar colors: blue (`#1976d2`) for bars in ideal zone, orange (`#ed6c02`) for bars outside

Props: `imageScale: number`, `idealRangeLow: number`, `idealRangeHigh: number`, `binningRecommendations: Record<number, string>`.

SVG-based (not canvas) — small fixed number of elements, SVG is simpler here.

- [ ] **Step 2: Create CalculatorPanel component**

Create `frontend/src/components/rigs/CalculatorPanel.tsx`:

Shows all computed optical properties. Accepts a `Rig` prop (or `RigCalculators` directly).

Sections:
- **Location selector** — Autocomplete dropdown from `fetchLocations()`. Defaults to default location. Changing location calls `fetchRigCalculators()` with the new location_id.
- **Seeing slider** — MUI Slider, range 0.5–6.0″, with quality zone labels. Default position: midpoint of location seeing range (or 3.0″ if no seeing set). Dragging updates sampling assessment in real time (client-side recalculation).
- **Binning selector** — ToggleButtonGroup (1×1, 2×2, 3×3, 4×4). Changes displayed image scale and FOV.
- **Metrics table** — Image Scale, FOV (arcmin + degrees), Focal Ratio, Dawes Limit, Rayleigh Limit, Sensor Coverage (with vignetting warning if >100%)
- **Sampling assessment** — Assessment text, recommendation, seeing source indicator
- **Sampling chart** — `SamplingChart` component
- **Guide system** — Guide image scale and FOV (shown only when guide camera + guide scope assigned)

- [ ] **Step 3: Wire CalculatorPanel into RigCard and RigFormDialog**

Update `RigCard.tsx` to show a collapsible calculator panel on click/expand. Update `RigFormDialog.tsx` to show a live preview calculator panel when OTA + camera are selected.

- [ ] **Step 4: Verify frontend builds**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 5: Test manually**

Run: `cd /Users/fbaptiste/dev/nightcrate && make dev`

Test the calculator panel:
- Verify all metrics match spec values for C11 rig (0.396″/px, 41.3′×27.6′ FOV)
- Change location → sampling assessment updates
- Drag seeing slider → assessment updates in real time
- Change binning → image scale and FOV update
- Sampling chart shows correct bars and ideal zone
- Guide metrics appear when guide camera + guide scope assigned

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/rigs/CalculatorPanel.tsx frontend/src/components/rigs/SamplingChart.tsx frontend/src/components/rigs/RigCard.tsx frontend/src/components/rigs/RigFormDialog.tsx
git commit -m "feat: add calculator panel with D3 sampling chart, seeing slider, and binning selector"
```

---

## Task 10: Final integration and verification

**Files:**
- Modify: various (fixes from integration testing)

- [ ] **Step 1: Run all backend checks**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run bandit -r src/ && uv run pytest -x -q`
Expected: All pass.

- [ ] **Step 2: Run frontend build**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 3: End-to-end manual testing**

Run: `cd /Users/fbaptiste/dev/nightcrate && make dev`

Test the complete flow:
1. Navigate to Locations → edit a location → set seeing values (2.0 / 4.0) → save
2. Navigate to Rigs → click "New Rig"
3. Fill in: name, select telescope config, select camera → verify live calculator preview
4. Add filter wheel → verify filter slot grid appears → assign filters
5. Add mount, OAG, guide camera → verify guide metrics appear in calculator
6. Save → verify card appears in list with correct stats and sampling badge
7. Clone rig → verify copy created with "(Copy)" suffix
8. Edit clone → change name → save
9. Delete rig → verify it moves to retired section
10. Restore rig → verify it returns to active list
11. Set as default → verify badge appears, other default cleared
12. Change location in calculator → verify sampling assessment updates
13. Drag seeing slider → verify real-time update
14. Change binning → verify metrics update

- [ ] **Step 4: Fix any issues found during testing**

Address any bugs or UI issues found during manual testing.

- [ ] **Step 5: Final commit (if any fixes were needed)**

```bash
git add -A
git commit -m "fix: address integration issues from rig builder testing"
```

---

## Summary

| Task | Description | Dependencies |
|------|-------------|-------------|
| 1 | Location seeing columns + backend models | None |
| 2 | Rig calculator service (pure math, TDD) | None |
| 3 | Rig migration + Pydantic models | Task 1 (migration ordering) |
| 4 | Rig API — CRUD endpoints | Tasks 2, 3 |
| 5 | Frontend API client + types | Task 4 |
| 6 | Frontend location seeing fields | Task 1, 5 |
| 7 | Frontend rigs page + cards | Task 5 |
| 8 | Frontend rig form dialog | Tasks 5, 7 |
| 9 | Frontend calculator panel + D3 chart | Tasks 5, 7, 8 |
| 10 | Final integration testing | All |

**Parallelizable:** Tasks 1 and 2 are fully independent. Tasks 5 and 6 can run in parallel after Task 4 completes.
