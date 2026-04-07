# Equipment Management API + Core UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Full backend CRUD API for all equipment types + frontend Equipment page with Cameras, Telescopes, and Filters tabs.

**Architecture:** Backend: single `equipment.py` router + `equipment_models.py` for Pydantic models, all under `/api/equipment/`. Frontend: `EquipmentPage` with collapsible tree sidebar, per-category list components + form dialogs. Small schema migration (0006) for guide_sensor_id on camera.

**Tech Stack:** Python/FastAPI, aiosqlite, Pydantic, React/TypeScript, MUI (DataGrid, TreeView, Dialog, Accordion), TanStack Query

---

## File Structure

### Backend (create)
- `backend/src/nightcrate/db/migrations/0006.camera_guide_sensor.sql` — schema tweak
- `backend/src/nightcrate/api/equipment_models.py` — all Pydantic models (Create/Update/Response per type)
- `backend/src/nightcrate/api/equipment.py` — all CRUD endpoints
- `backend/tests/test_equipment_api.py` — API tests

### Backend (modify)
- `backend/src/nightcrate/main.py` — register equipment router
- `backend/src/nightcrate/db/migrations/0005.equipment_schema.sql` — (only if 0006 needs depends)

### Frontend (create)
- `frontend/src/api/equipment.ts` — types + fetch functions
- `frontend/src/pages/EquipmentPage.tsx` — page layout with sidebar
- `frontend/src/components/equipment/EquipmentSidebar.tsx` — tree navigation
- `frontend/src/components/equipment/EquipmentPlaceholder.tsx` — "Coming soon"
- `frontend/src/components/equipment/CameraList.tsx` — camera DataGrid
- `frontend/src/components/equipment/CameraFormDialog.tsx` — camera add/edit
- `frontend/src/components/equipment/TelescopeList.tsx` — telescope DataGrid
- `frontend/src/components/equipment/TelescopeFormDialog.tsx` — telescope add/edit
- `frontend/src/components/equipment/FilterList.tsx` — filter DataGrid
- `frontend/src/components/equipment/FilterFormDialog.tsx` — filter add/edit
- `frontend/src/components/equipment/shared/ManufacturerPicker.tsx`
- `frontend/src/components/equipment/shared/SensorPicker.tsx`
- `frontend/src/components/equipment/shared/LookupPicker.tsx` — generic dropdown for connector_size, filter_size, optical_design, etc.
- `frontend/src/components/equipment/shared/InterfaceMultiSelect.tsx`
- `frontend/src/components/equipment/shared/ConfirmDeleteDialog.tsx`

### Frontend (modify)
- `frontend/src/App.tsx` — add /equipment route
- `frontend/src/components/AppShell.tsx` — add Equipment nav item

### Docs (modify)
- `DB_SCHEMA_DDL.sql` — add guide_sensor_id
- `DB_SCHEMA.md` — update camera diagram

---

### Task 1: Schema Migration — guide_sensor_id on Camera

**Files:**
- Create: `backend/src/nightcrate/db/migrations/0006.camera_guide_sensor.sql`
- Modify: `DB_SCHEMA_DDL.sql`, `DB_SCHEMA.md`

- [ ] **Step 1: Create migration**

```sql
-- depends: 0005.equipment_schema

ALTER TABLE camera ADD COLUMN guide_sensor_id INTEGER REFERENCES sensor(id);
```

- [ ] **Step 2: Update DB_SCHEMA_DDL.sql**

Add `guide_sensor_id INTEGER REFERENCES sensor(id),` to the camera table definition, after the `sensor_id` line.

- [ ] **Step 3: Update DB_SCHEMA.md**

In the Camera diagram (section 4), add `INTEGER guide_sensor_id FK "optional guide sensor"` to the camera entity and add a relationship line `sensor ||--o{ camera : "guide sensor"`.

- [ ] **Step 4: Verify migration applies**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run python -c "
import sqlite3, importlib.resources
conn = sqlite3.connect(':memory:')
conn.execute('PRAGMA foreign_keys = ON')
mdir = importlib.resources.files('nightcrate') / 'db' / 'migrations'
for f in sorted(f.name for f in mdir.iterdir() if f.name.endswith('.sql')):
    sql = (mdir / f).read_text()
    body = '\n'.join(l for l in sql.split('\n') if not l.strip().startswith('-- depends:'))
    conn.executescript(body)
cols = [r[1] for r in conn.execute('PRAGMA table_info(camera)').fetchall()]
assert 'guide_sensor_id' in cols, f'Missing guide_sensor_id, got: {cols}'
print('OK — guide_sensor_id present')
"`

- [ ] **Step 5: Commit**

```bash
git add backend/src/nightcrate/db/migrations/0006.camera_guide_sensor.sql DB_SCHEMA_DDL.sql DB_SCHEMA.md
git commit -m "feat: add guide_sensor_id to camera table (migration 0006)"
```

---

### Task 2: Pydantic Models

**Files:**
- Create: `backend/src/nightcrate/api/equipment_models.py`

- [ ] **Step 1: Create the models file**

Create `backend/src/nightcrate/api/equipment_models.py` with Create, Update, and Response models for every equipment type. Follow this structure:

**Lookup table models** (manufacturer as the template — repeat for optical_design, mount_type, connection_interface, connector_size, filter_size, computer_type):

```python
"""Pydantic models for equipment API request/response shapes."""

from pydantic import BaseModel


# ── Lookup tables ────────────────────────────────────────────────────────────

class ManufacturerCreate(BaseModel):
    name: str
    website: str | None = None
    notes: str | None = None

class ManufacturerUpdate(BaseModel):
    name: str | None = None
    website: str | None = None
    notes: str | None = None

class ManufacturerResponse(BaseModel):
    id: int
    name: str
    website: str | None
    notes: str | None
    active: bool
    created_at: str
    updated_at: str
```

**Equipment models** — each has Create (required fields + optional fields + junction IDs), Update (all optional), Response (includes joined objects). Key models:

```python
# ── Sensor ───────────────────────────────────────────────────────────────────

class SensorCreate(BaseModel):
    manufacturer_id: int
    model_name: str
    sensor_type: str  # 'mono' or 'color'
    pixel_size_um: float
    resolution_x: int
    resolution_y: int
    sensor_width_mm: float | None = None
    sensor_height_mm: float | None = None
    adc_bit_depth: int | None = None
    full_well_capacity_ke: float | None = None
    read_noise_e: float | None = None
    peak_qe_pct: float | None = None
    bayer_pattern: str | None = None
    dual_gain: bool = False
    hcg_threshold_gain: int | None = None
    notes: str | None = None

class SensorUpdate(BaseModel):
    manufacturer_id: int | None = None
    model_name: str | None = None
    sensor_type: str | None = None
    pixel_size_um: float | None = None
    resolution_x: int | None = None
    resolution_y: int | None = None
    sensor_width_mm: float | None = None
    sensor_height_mm: float | None = None
    adc_bit_depth: int | None = None
    full_well_capacity_ke: float | None = None
    read_noise_e: float | None = None
    peak_qe_pct: float | None = None
    bayer_pattern: str | None = None
    dual_gain: bool | None = None
    hcg_threshold_gain: int | None = None
    notes: str | None = None

class SensorResponse(BaseModel):
    id: int
    manufacturer: ManufacturerResponse
    model_name: str
    sensor_type: str
    pixel_size_um: float
    resolution_x: int
    resolution_y: int
    sensor_width_mm: float | None
    sensor_height_mm: float | None
    adc_bit_depth: int | None
    full_well_capacity_ke: float | None
    read_noise_e: float | None
    peak_qe_pct: float | None
    bayer_pattern: str | None
    dual_gain: bool
    hcg_threshold_gain: int | None
    notes: str | None
    active: bool
    created_at: str
    updated_at: str


# ── Camera ───────────────────────────────────────────────────────────────────

class CameraCreate(BaseModel):
    manufacturer_id: int
    sensor_id: int
    guide_sensor_id: int | None = None
    connector_size_id: int | None = None
    model_name: str
    cooled: bool = False
    cooling_delta_c: float | None = None
    back_focus_mm: float | None = None
    weight_g: float | None = None
    tilt_adapter: bool = False
    has_usb_hub: bool = False
    usb_hub_interface_id: int | None = None
    unity_gain: int | None = None
    notes: str | None = None
    interface_ids: list[int] = []

class CameraUpdate(BaseModel):
    manufacturer_id: int | None = None
    sensor_id: int | None = None
    guide_sensor_id: int | None = None
    connector_size_id: int | None = None
    model_name: str | None = None
    cooled: bool | None = None
    cooling_delta_c: float | None = None
    back_focus_mm: float | None = None
    weight_g: float | None = None
    tilt_adapter: bool | None = None
    has_usb_hub: bool | None = None
    usb_hub_interface_id: int | None = None
    unity_gain: int | None = None
    notes: str | None = None
    interface_ids: list[int] | None = None

class CameraResponse(BaseModel):
    id: int
    manufacturer: ManufacturerResponse
    sensor: SensorResponse
    guide_sensor: SensorResponse | None
    connector_size: ConnectorSizeResponse | None
    model_name: str
    cooled: bool
    cooling_delta_c: float | None
    back_focus_mm: float | None
    weight_g: float | None
    tilt_adapter: bool
    has_usb_hub: bool
    usb_hub_interface: ConnectionInterfaceResponse | None
    unity_gain: int | None
    notes: str | None
    interfaces: list[ConnectionInterfaceResponse]
    active: bool
    created_at: str
    updated_at: str
```

Continue the same pattern for **all** remaining types. The implementer should create complete models for:
- `OpticalDesign` (Create/Update/Response) — name, description
- `MountType` — name, description
- `ConnectionInterface` — name, category, notes
- `ConnectorSize` — name, diameter_mm, notes
- `FilterSize` — name, description
- `ComputerType` — name, description
- `FilterType` — Response only (read-only, name + description)
- `Telescope` — manufacturer_id, optical_design_id, model_name, aperture_mm, image_circle_mm, weight_kg, obstruction_pct, notes, connector_size_ids. Response includes configurations list and connectors list.
- `TelescopeConfiguration` — telescope_id, config_name, accessory_name, reduction_factor, effective_focal_length_mm, effective_focal_ratio, effective_image_circle_mm, effective_back_focus_mm, is_native, notes
- `Filter` — manufacturer_id, filter_type_id, filter_size_id, model_name, peak_transmission_pct, mounted_thickness_mm, notes. Response includes passbands list.
- `FilterPassband` — filter_id, line_name, central_wavelength_nm, bandwidth_nm, peak_transmission_pct
- `Mount` — manufacturer_id, mount_type_id, model_name, payload_capacity_kg, mount_weight_kg, counterweight_required, goto_capable, periodic_error_arcsec, drive_type, notes, interface_ids
- `Focuser` — manufacturer_id, model_name, motorized, travel_range_mm, step_size_um, total_steps, temperature_compensation, backlash_steps, notes, interface_ids
- `FilterWheel` — manufacturer_id, filter_size_id, camera_side_connector_id, telescope_side_connector_id, model_name, num_positions, back_focus_contribution_mm, notes, interface_ids
- `Oag` — manufacturer_id, imaging_side_connector_id, guide_camera_connector_id, model_name, prism_size_mm, back_focus_contribution_mm, weight_g, notes
- `GuideScope` — manufacturer_id, guide_camera_connector_id, model_name, aperture_mm, focal_length_mm, weight_g, notes
- `Computer` — manufacturer_id, computer_type_id, model_name, notes
- `Software` — manufacturer_id, name, category, website, notes

- [ ] **Step 2: Verify models parse**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run python -c "from nightcrate.api.equipment_models import *; print('OK')"`

- [ ] **Step 3: Lint and format**

Run: `uv run ruff check src/nightcrate/api/equipment_models.py && uv run ruff format src/nightcrate/api/equipment_models.py`

- [ ] **Step 4: Commit**

```bash
git add backend/src/nightcrate/api/equipment_models.py
git commit -m "feat: Pydantic models for all equipment types"
```

---

### Task 3: Backend CRUD — Lookup Tables + Sensor

**Files:**
- Create: `backend/src/nightcrate/api/equipment.py`
- Modify: `backend/src/nightcrate/main.py`

This task establishes the CRUD pattern. The implementer should build endpoints for all 7 lookup tables + sensor, following the pattern below.

- [ ] **Step 1: Create equipment router with manufacturer CRUD**

Create `backend/src/nightcrate/api/equipment.py`:

```python
"""Equipment management API endpoints — CRUD for all equipment types."""

from fastapi import APIRouter, HTTPException, Query

from nightcrate.api.equipment_models import (
    ManufacturerCreate,
    ManufacturerResponse,
    ManufacturerUpdate,
)
from nightcrate.db.session import get_db

router = APIRouter(prefix="/api/equipment", tags=["equipment"])


# ── Helpers ──────────────────────────────────────────────────────────────────


def _row_to_dict(row) -> dict:
    """Convert an aiosqlite.Row to a plain dict."""
    return dict(row)


def _bool_fields(d: dict, *keys) -> dict:
    """Convert integer 0/1 fields to Python bools for Pydantic."""
    for k in keys:
        if k in d and d[k] is not None:
            d[k] = bool(d[k])
    return d


async def _get_or_404(conn, table: str, row_id: int, label: str = "Item") -> dict:
    """Fetch a single row by ID or raise 404."""
    row = await conn.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,))
    result = await row.fetchone()
    if result is None:
        raise HTTPException(status_code=404, detail=f"{label} not found: {row_id}")
    return _row_to_dict(result)


# ── Manufacturer CRUD ────────────────────────────────────────────────────────


@router.get("/manufacturer", response_model=list[ManufacturerResponse])
async def list_manufacturers(
    include_retired: bool = Query(False, description="Include retired items"),
):
    async with get_db() as conn:
        where = "" if include_retired else "WHERE active = 1"
        rows = await conn.execute(
            f"SELECT * FROM manufacturer {where} ORDER BY name"
        )
        return [
            _bool_fields(_row_to_dict(r), "active")
            for r in await rows.fetchall()
        ]


@router.get("/manufacturer/{manufacturer_id}", response_model=ManufacturerResponse)
async def get_manufacturer(manufacturer_id: int):
    async with get_db() as conn:
        d = await _get_or_404(conn, "manufacturer", manufacturer_id, "Manufacturer")
        return _bool_fields(d, "active")


@router.post("/manufacturer", response_model=ManufacturerResponse, status_code=201)
async def create_manufacturer(body: ManufacturerCreate):
    async with get_db() as conn:
        try:
            cursor = await conn.execute(
                "INSERT INTO manufacturer (name, website, notes) VALUES (?, ?, ?)",
                (body.name, body.website, body.notes),
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(status_code=409, detail=f"Manufacturer already exists: {body.name}")
            raise
        row_id = cursor.lastrowid
        return _bool_fields(
            await _get_or_404(conn, "manufacturer", row_id, "Manufacturer"),
            "active",
        )


@router.put("/manufacturer/{manufacturer_id}", response_model=ManufacturerResponse)
async def update_manufacturer(manufacturer_id: int, body: ManufacturerUpdate):
    async with get_db() as conn:
        existing = await _get_or_404(conn, "manufacturer", manufacturer_id, "Manufacturer")
        updates = body.model_dump(exclude_unset=True)
        if not updates:
            return _bool_fields(existing, "active")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [manufacturer_id]
        try:
            await conn.execute(
                f"UPDATE manufacturer SET {set_clause} WHERE id = ?",
                values,
            )
            await conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(status_code=409, detail="Manufacturer name already exists")
            raise
        return _bool_fields(
            await _get_or_404(conn, "manufacturer", manufacturer_id, "Manufacturer"),
            "active",
        )


@router.delete("/manufacturer/{manufacturer_id}")
async def delete_manufacturer(manufacturer_id: int):
    async with get_db() as conn:
        await _get_or_404(conn, "manufacturer", manufacturer_id, "Manufacturer")
        await conn.execute(
            "UPDATE manufacturer SET active = 0 WHERE id = ?",
            (manufacturer_id,),
        )
        await conn.commit()
    return {"ok": True}
```

- [ ] **Step 2: Add remaining lookup table CRUD**

Follow the exact same pattern for: `optical_design`, `mount_type`, `connection_interface`, `connector_size`, `filter_size`, `computer_type`. Each gets list/get/create/update/delete endpoints.

`filter_type` is read-only — only list and get endpoints (no create/update/delete since it's a closed vocabulary).

For `connection_interface`, the Create model includes `category` (required, CHECK constraint enforced by DB).
For `connector_size`, the Create model includes `diameter_mm` (optional).

- [ ] **Step 3: Add sensor CRUD**

Sensor is the first equipment type with a manufacturer join. The list endpoint returns `SensorResponse` with nested `ManufacturerResponse`:

```python
@router.get("/sensor", response_model=list[SensorResponse])
async def list_sensors(include_retired: bool = Query(False)):
    async with get_db() as conn:
        where = "" if include_retired else "WHERE s.active = 1"
        rows = await conn.execute(f"""
            SELECT s.*, m.id AS m_id, m.name AS m_name, m.website AS m_website,
                   m.notes AS m_notes, m.active AS m_active,
                   m.created_at AS m_created_at, m.updated_at AS m_updated_at
            FROM sensor s
            JOIN manufacturer m ON m.id = s.manufacturer_id
            {where}
            ORDER BY m.name, s.model_name
        """)
        results = []
        for r in await rows.fetchall():
            d = _row_to_dict(r)
            _bool_fields(d, "active", "dual_gain")
            d["manufacturer"] = {
                "id": d.pop("m_id"), "name": d.pop("m_name"),
                "website": d.pop("m_website"), "notes": d.pop("m_notes"),
                "active": bool(d.pop("m_active")),
                "created_at": d.pop("m_created_at"),
                "updated_at": d.pop("m_updated_at"),
            }
            results.append(d)
        return results
```

Create and update follow the manufacturer pattern but insert into the `sensor` table with all sensor-specific columns. The create endpoint should convert `dual_gain` bool to int (0/1) for SQLite.

- [ ] **Step 4: Register router in main.py**

Add to `backend/src/nightcrate/main.py`:

```python
from nightcrate.api import aberration, diagnostics, equipment, files, images, settings
# ...
app.include_router(equipment.router)
```

- [ ] **Step 5: Verify endpoints start**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run uvicorn nightcrate.main:app --port 8000 &` then `curl http://localhost:8000/api/equipment/manufacturer | python3 -m json.tool` — should return `[]`. Kill the server.

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check src/ && uv run ruff format src/
git add backend/src/nightcrate/api/equipment.py backend/src/nightcrate/main.py
git commit -m "feat: equipment CRUD API — lookup tables + sensor"
```

---

### Task 4: Backend CRUD — Camera, Telescope, Filter (complex types)

**Files:**
- Modify: `backend/src/nightcrate/api/equipment.py`

These are the three complex types with joins and child/junction tables.

- [ ] **Step 1: Add camera CRUD**

Camera endpoints need to:
- JOIN manufacturer, sensor, guide_sensor (LEFT), connector_size (LEFT), usb_hub_interface (LEFT)
- Fetch interfaces from `camera_interface` junction table as a second query
- On create/update, replace junction rows with provided `interface_ids`
- Convert booleans (cooled, tilt_adapter, has_usb_hub, active) to Python bools

The list endpoint joins all FKs and assembles nested response objects. The create endpoint inserts the camera row, then inserts junction rows. The update endpoint updates the camera row and replaces junction rows.

- [ ] **Step 2: Add telescope CRUD with configuration and connector endpoints**

Telescope endpoints:
- JOIN manufacturer, optical_design (LEFT)
- Fetch configurations from `telescope_configuration` as a second query
- Fetch connectors from `telescope_connector` + `connector_size` as a third query
- On create, accept `connector_size_ids` and insert junction rows
- On update, replace connector junction rows

Child endpoints for configurations:
```
POST   /telescope/{id}/configuration
PUT    /telescope/{id}/configuration/{cid}
DELETE /telescope/{id}/configuration/{cid}
```

Configuration create/update should validate that there's exactly one `is_native=1` per telescope (the partial unique index will catch duplicates, but the API should give a clear error message).

- [ ] **Step 3: Add filter CRUD with passband endpoints**

Filter endpoints:
- JOIN manufacturer, filter_type, filter_size (LEFT)
- Fetch passbands from `filter_passband` as a second query

Child endpoints for passbands:
```
POST   /filter/{id}/passband
PUT    /filter/{id}/passband/{pid}
DELETE /filter/{id}/passband/{pid}
```

- [ ] **Step 4: Lint and commit**

```bash
uv run ruff check src/ && uv run ruff format src/
git add backend/src/nightcrate/api/equipment.py
git commit -m "feat: equipment CRUD API — camera, telescope, filter with child tables"
```

---

### Task 5: Backend CRUD — Remaining Equipment Types

**Files:**
- Modify: `backend/src/nightcrate/api/equipment.py`

Add CRUD for: mount, focuser, filter_wheel, oag, guide_scope, computer, software.

- [ ] **Step 1: Add mount CRUD**

Mount follows the camera pattern: manufacturer + mount_type joins, interface junction table. Same list/get/create/update/delete + junction management.

- [ ] **Step 2: Add focuser CRUD**

Same pattern as mount: manufacturer join, interface junction.

- [ ] **Step 3: Add filter_wheel CRUD**

More complex: manufacturer join, filter_size join, two connector_size joins (camera_side, telescope_side), interface junction.

- [ ] **Step 4: Add oag CRUD**

Manufacturer join, two connector_size joins. No junction table.

- [ ] **Step 5: Add guide_scope CRUD**

Manufacturer join, one connector_size join. No junction table.

- [ ] **Step 6: Add computer CRUD**

Manufacturer + computer_type joins. No junction table.

- [ ] **Step 7: Add software CRUD**

Manufacturer join + category field. No junction table.

- [ ] **Step 8: Lint and commit**

```bash
uv run ruff check src/ && uv run ruff format src/
git add backend/src/nightcrate/api/equipment.py
git commit -m "feat: equipment CRUD API — mount, focuser, filter_wheel, oag, guide_scope, computer, software"
```

---

### Task 6: Backend Tests

**Files:**
- Create: `backend/tests/test_equipment_api.py`

- [ ] **Step 1: Write test fixtures and lookup table tests**

```python
"""Tests for equipment CRUD API endpoints."""

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


class TestManufacturerCRUD:
    async def test_create_and_list(self, client: AsyncClient):
        resp = await client.post(
            "/api/equipment/manufacturer",
            json={"name": "ZWO", "website": "https://www.zwoastro.com"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "ZWO"
        assert data["active"] is True

        resp = await client.get("/api/equipment/manufacturer")
        assert resp.status_code == 200
        names = [m["name"] for m in resp.json()]
        assert "ZWO" in names

    async def test_get_by_id(self, client: AsyncClient):
        resp = await client.post(
            "/api/equipment/manufacturer", json={"name": "Celestron"}
        )
        mid = resp.json()["id"]
        resp = await client.get(f"/api/equipment/manufacturer/{mid}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Celestron"

    async def test_update(self, client: AsyncClient):
        resp = await client.post(
            "/api/equipment/manufacturer", json={"name": "Askar"}
        )
        mid = resp.json()["id"]
        resp = await client.put(
            f"/api/equipment/manufacturer/{mid}",
            json={"website": "https://www.askar.com"},
        )
        assert resp.status_code == 200
        assert resp.json()["website"] == "https://www.askar.com"
        assert resp.json()["name"] == "Askar"

    async def test_soft_delete(self, client: AsyncClient):
        resp = await client.post(
            "/api/equipment/manufacturer", json={"name": "ToRetire"}
        )
        mid = resp.json()["id"]
        resp = await client.delete(f"/api/equipment/manufacturer/{mid}")
        assert resp.status_code == 200

        # Not in default list
        resp = await client.get("/api/equipment/manufacturer")
        names = [m["name"] for m in resp.json()]
        assert "ToRetire" not in names

        # In list with include_retired
        resp = await client.get(
            "/api/equipment/manufacturer", params={"include_retired": "true"}
        )
        names = [m["name"] for m in resp.json()]
        assert "ToRetire" in names

    async def test_duplicate_name_409(self, client: AsyncClient):
        await client.post(
            "/api/equipment/manufacturer", json={"name": "Unique"}
        )
        resp = await client.post(
            "/api/equipment/manufacturer", json={"name": "Unique"}
        )
        assert resp.status_code == 409

    async def test_not_found_404(self, client: AsyncClient):
        resp = await client.get("/api/equipment/manufacturer/99999")
        assert resp.status_code == 404
```

- [ ] **Step 2: Write sensor tests**

Test sensor CRUD with manufacturer FK resolution, verify the response includes nested manufacturer object.

- [ ] **Step 3: Write camera tests**

Test camera CRUD including:
- Create with sensor_id, manufacturer_id, interface_ids
- Verify response includes nested sensor, manufacturer, interfaces
- Update with new interface_ids replaces junction rows
- Soft delete

- [ ] **Step 4: Write telescope tests**

Test telescope CRUD including:
- Create telescope, then add configurations via child endpoint
- Verify native config uniqueness (only one is_native=1)
- Verify configurations returned in telescope response
- Delete configuration via child endpoint
- Connector junction management

- [ ] **Step 5: Write filter tests**

Test filter CRUD including:
- Create filter, then add passbands via child endpoint
- Verify passbands returned in filter response
- line_name CHECK constraint (invalid line rejected)

- [ ] **Step 6: Write tests for remaining types**

One test class per type (mount, focuser, filter_wheel, oag, guide_scope, computer, software) covering at minimum: create + list + soft-delete. Follow the manufacturer test pattern.

- [ ] **Step 7: Run all tests**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_equipment_api.py -v`

Expected: All tests pass.

- [ ] **Step 8: Lint and commit**

```bash
uv run ruff check tests/ && uv run ruff format tests/
git add backend/tests/test_equipment_api.py
git commit -m "test: comprehensive equipment API tests"
```

---

### Task 7: Frontend — API Client + Types

**Files:**
- Create: `frontend/src/api/equipment.ts`

- [ ] **Step 1: Create types and fetch functions**

```typescript
import { apiFetch } from "./client";

// ── Lookup types ────────────────────────────────────────────────────────────

export interface Manufacturer {
  id: number;
  name: string;
  website: string | null;
  notes: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ConnectorSize {
  id: number;
  name: string;
  diameter_mm: number | null;
  notes: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

// ... similar interfaces for OpticalDesign, MountType, ConnectionInterface,
//     FilterSize, ComputerType, FilterType

// ── Equipment types ─────────────────────────────────────────────────────────

export interface Sensor {
  id: number;
  manufacturer: Manufacturer;
  model_name: string;
  sensor_type: "mono" | "color";
  pixel_size_um: number;
  resolution_x: number;
  resolution_y: number;
  // ... all fields from SensorResponse
  active: boolean;
}

export interface Camera {
  id: number;
  manufacturer: Manufacturer;
  sensor: Sensor;
  guide_sensor: Sensor | null;
  connector_size: ConnectorSize | null;
  model_name: string;
  cooled: boolean;
  // ... all fields from CameraResponse
  interfaces: ConnectionInterface[];
  active: boolean;
}

// ... TelescopeConfiguration, Telescope, FilterPassband, Filter, etc.

// ── Fetch functions ─────────────────────────────────────────────────────────

// Lookup tables
export const fetchManufacturers = (includeRetired = false) =>
  apiFetch<Manufacturer[]>(
    `/equipment/manufacturer${includeRetired ? "?include_retired=true" : ""}`,
  );

export const createManufacturer = (data: { name: string; website?: string; notes?: string }) =>
  apiFetch<Manufacturer>("/equipment/manufacturer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

// ... similar for all lookup tables

// Equipment
export const fetchCameras = (includeRetired = false) =>
  apiFetch<Camera[]>(
    `/equipment/camera${includeRetired ? "?include_retired=true" : ""}`,
  );

export const fetchCamera = (id: number) =>
  apiFetch<Camera>(`/equipment/camera/${id}`);

export const createCamera = (data: CameraCreate) =>
  apiFetch<Camera>("/equipment/camera", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

export const updateCamera = (id: number, data: Partial<CameraCreate>) =>
  apiFetch<Camera>(`/equipment/camera/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

export const deleteCamera = (id: number) =>
  apiFetch<void>(`/equipment/camera/${id}`, { method: "DELETE" });

// ... same pattern for telescope, filter, and all types
// Child endpoints:
export const createTelescopeConfig = (telescopeId: number, data: TelescopeConfigCreate) =>
  apiFetch<TelescopeConfiguration>(`/equipment/telescope/${telescopeId}/configuration`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
// ... etc
```

Complete ALL types and fetch functions for every equipment type. The implementer should create Create types (matching the Pydantic Create models) for use in form submissions.

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npx tsc --noEmit`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/equipment.ts
git commit -m "feat: frontend API client for equipment CRUD"
```

---

### Task 8: Frontend — Equipment Page Scaffolding

**Files:**
- Create: `frontend/src/pages/EquipmentPage.tsx`
- Create: `frontend/src/components/equipment/EquipmentSidebar.tsx`
- Create: `frontend/src/components/equipment/EquipmentPlaceholder.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/AppShell.tsx`

- [ ] **Step 1: Create EquipmentSidebar**

MUI TreeView (SimpleTreeView from `@mui/x-tree-view`) with grouped categories. Accepts `selectedCategory` and `onSelectCategory` props.

```typescript
// Groups:
// Imaging: cameras, sensors
// Optics: telescopes, filters
// Tracking: mounts
// Accessories: focusers, filter-wheels, oags, guide-scopes
// Computing: computers, software
// Reference: manufacturers
```

Each tree item uses the URL slug as its `itemId`. Clicking a leaf item calls `onSelectCategory(slug)`.

- [ ] **Step 2: Create EquipmentPlaceholder**

Simple component showing "Coming soon" centered text for unbuilt tabs.

- [ ] **Step 3: Create EquipmentPage**

Two-panel layout: sidebar (fixed width ~220px) + content area. Uses `useParams` to get `:category` from URL. Renders the appropriate list component or placeholder based on category.

```typescript
export function EquipmentPage() {
  const { category = "cameras" } = useParams();
  const navigate = useNavigate();

  const content = (() => {
    switch (category) {
      case "cameras": return <CameraList />;
      case "telescopes": return <TelescopeList />;
      case "filters": return <FilterList />;
      default: return <EquipmentPlaceholder category={category} />;
    }
  })();

  return (
    <Box sx={{ display: "flex", height: "100%" }}>
      <EquipmentSidebar
        selectedCategory={category}
        onSelectCategory={(cat) => navigate(`/equipment/${cat}`)}
      />
      <Box sx={{ flex: 1, overflow: "auto", p: 2 }}>
        {content}
      </Box>
    </Box>
  );
}
```

- [ ] **Step 4: Add route to App.tsx**

```typescript
{ path: "equipment", element: <EquipmentPage /> },
{ path: "equipment/:category", element: <EquipmentPage /> },
```

- [ ] **Step 5: Add nav item to AppShell**

Add to the `navItems` array:

```typescript
{ to: "/equipment", label: "Equipment", icon: <BuildIcon /> },
```

Import `BuildIcon` from `@mui/icons-material/Build`.

- [ ] **Step 6: Verify build**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npm run build`

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/EquipmentPage.tsx frontend/src/components/equipment/ frontend/src/App.tsx frontend/src/components/AppShell.tsx
git commit -m "feat: Equipment page scaffolding with sidebar navigation"
```

---

### Task 9: Frontend — Shared Components

**Files:**
- Create: `frontend/src/components/equipment/shared/ManufacturerPicker.tsx`
- Create: `frontend/src/components/equipment/shared/SensorPicker.tsx`
- Create: `frontend/src/components/equipment/shared/LookupPicker.tsx`
- Create: `frontend/src/components/equipment/shared/InterfaceMultiSelect.tsx`
- Create: `frontend/src/components/equipment/shared/ConfirmDeleteDialog.tsx`

- [ ] **Step 1: Create ManufacturerPicker**

MUI Autocomplete that fetches manufacturers via `useQuery` and presents them as a searchable dropdown. Props: `value` (manufacturer ID or null), `onChange` (called with selected manufacturer ID).

- [ ] **Step 2: Create SensorPicker**

MUI Autocomplete that fetches sensors and shows `model_name (sensor_type, pixel_size_um µm, resolution_x × resolution_y)` as the option label. Props: `value`, `onChange`, `label` (for "Sensor" vs "Guide Sensor").

- [ ] **Step 3: Create LookupPicker**

Generic dropdown for any simple lookup table (connector_size, filter_size, optical_design, mount_type, computer_type). Props: `fetchFn` (the API fetch function), `queryKey`, `value`, `onChange`, `label`. Uses `useQuery` internally.

- [ ] **Step 4: Create InterfaceMultiSelect**

Chip array showing selected interfaces with × to remove, plus an "Add" button that opens a small popover/menu to pick from available `connection_interface` rows. Props: `value` (array of interface IDs), `onChange`.

- [ ] **Step 5: Create ConfirmDeleteDialog**

Simple MUI Dialog: "Are you sure you want to retire {name}?" with Cancel and Retire buttons. Props: `open`, `itemName`, `onConfirm`, `onCancel`.

- [ ] **Step 6: Verify build**

Run: `npm run build`

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/equipment/shared/
git commit -m "feat: shared equipment form components (pickers, multi-select, confirm dialog)"
```

---

### Task 10: Frontend — Camera List + Form Dialog

**Files:**
- Create: `frontend/src/components/equipment/CameraList.tsx`
- Create: `frontend/src/components/equipment/CameraFormDialog.tsx`

- [ ] **Step 1: Create CameraList**

MUI DataGrid showing cameras. Columns: Model, Manufacturer, Sensor (model_name + type), Cooled (boolean chip), Connector, Actions (Edit/Delete icon buttons). "Add Camera" button in the header. Uses `useQuery` with `fetchCameras`. Click Edit opens `CameraFormDialog` in edit mode. Click Add opens it in create mode. Delete opens `ConfirmDeleteDialog`.

- [ ] **Step 2: Create CameraFormDialog**

MUI Dialog (`maxWidth="md"`, `fullWidth`). Contains:
- Model name (TextField)
- ManufacturerPicker
- SensorPicker (main sensor, required)
- SensorPicker (guide sensor, optional, with "None" option)
- LookupPicker for connector_size
- Cooled (Switch), Cooling delta, Back focus, Weight, Tilt adapter, Unity gain
- USB Hub (Switch) + LookupPicker for hub interface (shown only when hub=true)
- InterfaceMultiSelect for connection interfaces
- Notes (multiline TextField)
- Save / Cancel buttons

On save: calls `createCamera` or `updateCamera`, invalidates `["cameras"]` query, shows snackbar, closes dialog.

In edit mode: pre-populates all fields from the selected camera.

- [ ] **Step 3: Verify build**

Run: `npm run build`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/equipment/CameraList.tsx frontend/src/components/equipment/CameraFormDialog.tsx
git commit -m "feat: Camera list + add/edit dialog"
```

---

### Task 11: Frontend — Telescope List + Form Dialog

**Files:**
- Create: `frontend/src/components/equipment/TelescopeList.tsx`
- Create: `frontend/src/components/equipment/TelescopeFormDialog.tsx`

- [ ] **Step 1: Create TelescopeList**

DataGrid columns: Model, Manufacturer, Design, Aperture (mm), Configs (count), Actions. Same pattern as CameraList.

- [ ] **Step 2: Create TelescopeFormDialog**

Dialog with:
- Model name, ManufacturerPicker, LookupPicker for optical_design
- Aperture (mm), Image circle (mm), Weight (kg), Obstruction (%)
- Connector multi-select (LookupPicker for connector_sizes, rendered as chips)
- **Configurations section**: MUI Accordion stack. Each configuration is a collapsible panel:
  - Header: config_name + key specs summary (e.g., "1960mm f/7") + star icon if native + delete icon
  - Body: config_name, accessory_name, reduction_factor, effective_focal_length, effective_focal_ratio, effective_image_circle, effective_back_focus, is_native (switch), notes
- "Add Configuration" button below the accordions
- At least one config must have `is_native=true`

On save: saves the telescope first, then creates/updates/deletes configurations via the child endpoints. New configs use POST, existing modified configs use PUT, removed configs use DELETE.

- [ ] **Step 3: Verify build**

Run: `npm run build`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/equipment/TelescopeList.tsx frontend/src/components/equipment/TelescopeFormDialog.tsx
git commit -m "feat: Telescope list + add/edit dialog with configuration accordions"
```

---

### Task 12: Frontend — Filter List + Form Dialog

**Files:**
- Create: `frontend/src/components/equipment/FilterList.tsx`
- Create: `frontend/src/components/equipment/FilterFormDialog.tsx`

- [ ] **Step 1: Create FilterList**

DataGrid columns: Model, Manufacturer, Type (formatted filter_type name), Passbands (e.g., "Ha", "Ha+Oiii"), Size, Actions.

- [ ] **Step 2: Create FilterFormDialog**

Dialog with:
- Model name, ManufacturerPicker, FilterTypePicker (dropdown of the 9 types, formatted nicely)
- LookupPicker for filter_size
- Peak transmission (%), Mounted thickness (mm)
- **Passbands section**: Accordion stack. Each passband is a collapsible panel:
  - Header: line_name + wavelength summary (e.g., "Ha — 656.3nm / 7nm") + delete icon
  - Body: line_name (dropdown from the CHECK constraint values: Ha, Hb, Oiii, Sii, etc.), central_wavelength_nm, bandwidth_nm, peak_transmission_pct
- "Add Passband" button
- Notes

On save: saves the filter, then manages passbands via child endpoints (same pattern as telescope configs).

- [ ] **Step 3: Verify build**

Run: `npm run build`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/equipment/FilterList.tsx frontend/src/components/equipment/FilterFormDialog.tsx
git commit -m "feat: Filter list + add/edit dialog with passband accordions"
```

---

### Task 13: Full Test Suite + Final Checks

**Files:** None (verification only)

- [ ] **Step 1: Run full backend test suite**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest -v`

Expected: All tests pass (373 existing + new equipment API tests)

- [ ] **Step 2: Lint and format**

Run: `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/`

- [ ] **Step 3: Security scan**

Run: `uv run bandit -r src/`

- [ ] **Step 4: Frontend build**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npm run build`

- [ ] **Step 5: Verify equipment page loads**

Start dev server with `make dev`, navigate to `/equipment`, verify:
- Sidebar tree renders with all groups
- Clicking "Cameras" shows the camera DataGrid (empty initially)
- Clicking "Telescopes" and "Filters" shows their respective DataGrids
- Other categories show "Coming soon"
- Add Camera dialog opens and closes
