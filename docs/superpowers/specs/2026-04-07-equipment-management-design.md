# Equipment Management API + Core UI — Design Spec

**Version:** 0.9.0
**Date:** 2026-04-07

## Summary

Full backend CRUD API for all equipment types plus frontend Equipment page with the three most complex tabs (Cameras, Telescopes, Filters). Remaining equipment tabs follow in v0.9.1.

## Scope

**In scope (v0.9.0):**
- Backend CRUD API for all equipment types (14 entity types + 7 lookup tables)
- Small schema migration (0006) adding `guide_sensor_id` to camera
- Frontend Equipment page with collapsible tree sidebar navigation
- Three complete frontend tabs: Cameras, Telescopes, Filters
- Shared frontend components (ManufacturerPicker, SensorPicker, etc.)
- Remaining tabs present with "Coming soon" placeholder

**Out of scope:**
- Remaining equipment UI tabs (v0.9.1)
- Seed loader, FITS resolver
- Rig management

## Schema Change

Add `guide_sensor_id` to the `camera` table for dual-sensor cameras (e.g., QHY 268M with built-in guide sensor).

```sql
-- Migration 0006
ALTER TABLE camera ADD COLUMN guide_sensor_id INTEGER REFERENCES sensor(id);
```

Update `DB_SCHEMA_DDL.sql` and `DB_SCHEMA.md` to match.

## Backend API

### Router Structure

Single router file: `backend/src/nightcrate/api/equipment.py`
- Prefix: `/api/equipment`
- Tag: `equipment`
- Mounted in `main.py` alongside existing routers

### Pydantic Models

File: `backend/src/nightcrate/api/equipment_models.py`

Separate file for models to keep the router file focused on endpoints. Models follow this pattern:

```python
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

Each equipment type gets Create, Update, and Response models. Complex types include nested children in their response:

```python
class TelescopeResponse(BaseModel):
    id: int
    manufacturer: ManufacturerResponse
    optical_design: OpticalDesignResponse | None
    model_name: str
    aperture_mm: float
    # ... other fields
    configurations: list[TelescopeConfigurationResponse]
    connectors: list[ConnectorSizeResponse]

class FilterResponse(BaseModel):
    id: int
    manufacturer: ManufacturerResponse
    filter_type: FilterTypeResponse
    filter_size: FilterSizeResponse | None
    model_name: str
    # ... other fields
    passbands: list[FilterPassbandResponse]

class CameraResponse(BaseModel):
    id: int
    manufacturer: ManufacturerResponse
    sensor: SensorResponse
    guide_sensor: SensorResponse | None
    connector_size: ConnectorSizeResponse | None
    # ... other fields
    interfaces: list[ConnectionInterfaceResponse]
```

### Endpoint Pattern

Every equipment type follows this CRUD pattern:

```
GET    /api/equipment/{type}            — list (active only by default, ?include_retired=true for all)
GET    /api/equipment/{type}/{id}       — get single with joins
POST   /api/equipment/{type}            — create
PUT    /api/equipment/{type}/{id}       — update
DELETE /api/equipment/{type}/{id}       — soft delete (sets active=0)
```

### Endpoint Inventory

**Lookup tables** (simple CRUD, no joins):

| Endpoint prefix | Notes |
|-----------------|-------|
| `/api/equipment/manufacturer` | Full CRUD |
| `/api/equipment/optical-design` | Full CRUD |
| `/api/equipment/mount-type` | Full CRUD |
| `/api/equipment/connection-interface` | Full CRUD |
| `/api/equipment/connector-size` | Full CRUD |
| `/api/equipment/filter-size` | Full CRUD |
| `/api/equipment/computer-type` | Full CRUD |
| `/api/equipment/filter-type` | Read-only (GET list, GET by id). Closed vocabulary — no create/update/delete. |

**Equipment** (CRUD with joins):

| Endpoint prefix | Joins | Child management |
|-----------------|-------|------------------|
| `/api/equipment/sensor` | manufacturer | — |
| `/api/equipment/camera` | manufacturer, sensor, guide_sensor, connector_size, interfaces | Interfaces via request body array |
| `/api/equipment/telescope` | manufacturer, optical_design, connectors, configurations | Configs + connectors via nested endpoints |
| `/api/equipment/filter` | manufacturer, filter_type, filter_size, passbands | Passbands via nested endpoints |
| `/api/equipment/mount` | manufacturer, mount_type, interfaces | Interfaces via request body array |
| `/api/equipment/focuser` | manufacturer, interfaces | Interfaces via request body array |
| `/api/equipment/filter-wheel` | manufacturer, filter_size, connectors, interfaces | Interfaces via request body array |
| `/api/equipment/oag` | manufacturer, connectors | — |
| `/api/equipment/guide-scope` | manufacturer, connector | — |
| `/api/equipment/computer` | manufacturer, computer_type | — |
| `/api/equipment/software` | manufacturer | — |

**Child table endpoints** (scoped to parent):

```
POST   /api/equipment/telescope/{id}/configuration       — add config
PUT    /api/equipment/telescope/{id}/configuration/{cid}  — update config
DELETE /api/equipment/telescope/{id}/configuration/{cid}  — delete config (hard delete)

POST   /api/equipment/filter/{id}/passband                — add passband
PUT    /api/equipment/filter/{id}/passband/{pid}          — update passband
DELETE /api/equipment/filter/{id}/passband/{pid}          — delete passband (hard delete)
```

### Junction Table Management

For equipment with many-to-many relationships (camera interfaces, mount interfaces, etc.), the junction table is managed via the parent's create/update request body:

```python
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
    interface_ids: list[int] = []  # connection_interface IDs
```

On create/update, the endpoint replaces all junction rows for the parent with the provided list. This is a simple delete-and-reinsert pattern.

### Soft Delete

- `DELETE /api/equipment/{type}/{id}` sets `active=0`, never hard deletes
- `GET /api/equipment/{type}` returns only `active=1` rows by default
- `GET /api/equipment/{type}?include_retired=true` returns all rows
- Response includes `active` field so the UI can show retired status
- Child table entries (configs, passbands) are hard-deleted because they have no independent identity — they're part of the parent

### Query Patterns

List endpoints return denormalized responses with joined data to avoid N+1 queries. Example for cameras:

```sql
SELECT c.*, m.name AS manufacturer_name, s.model_name AS sensor_name,
       gs.model_name AS guide_sensor_name, cs.name AS connector_name
FROM camera c
JOIN manufacturer m ON m.id = c.manufacturer_id
JOIN sensor s ON s.id = c.sensor_id
LEFT JOIN sensor gs ON gs.id = c.guide_sensor_id
LEFT JOIN connector_size cs ON cs.id = c.connector_size_id
WHERE c.active = 1
ORDER BY m.name, c.model_name
```

Junction table data (interfaces, connectors) is fetched in a second query per parent and assembled in Python.

## Frontend

### Routing

```
/equipment              → EquipmentPage (default to Cameras)
/equipment/:category    → EquipmentPage with category selected in sidebar
```

Category URL slugs: `cameras`, `sensors`, `telescopes`, `filters`, `mounts`, `focusers`, `filter-wheels`, `oags`, `guide-scopes`, `computers`, `software`, `manufacturers`

### Page Layout

`EquipmentPage.tsx` — two-panel layout:
- Left: collapsible tree sidebar (MUI TreeView, free tier) with grouped categories
- Right: content area showing the selected category's list + CRUD

Sidebar groups:
- **Imaging**: Cameras, Sensors
- **Optics**: Telescopes, Filters
- **Tracking**: Mounts
- **Accessories**: Focusers, Filter Wheels, OAGs, Guide Scopes
- **Computing**: Computers, Software
- **Reference**: Manufacturers

### Component Architecture

```
pages/
  EquipmentPage.tsx              — layout with sidebar + content router

components/equipment/
  EquipmentSidebar.tsx           — collapsible tree navigation
  EquipmentPlaceholder.tsx       — "Coming soon" for unbuilt tabs

  CameraList.tsx                 — DataGrid + Add button
  CameraFormDialog.tsx           — Add/Edit dialog with all camera fields
  TelescopeList.tsx              — DataGrid + Add button
  TelescopeFormDialog.tsx        — Add/Edit dialog with config accordions
  FilterList.tsx                 — DataGrid + Add button
  FilterFormDialog.tsx           — Add/Edit dialog with passband accordions

  shared/
    ManufacturerPicker.tsx       — autocomplete dropdown, reused across all forms
    SensorPicker.tsx             — autocomplete with specs preview (sensor_type, pixel_size, resolution)
    ConnectorSizePicker.tsx      — simple dropdown
    FilterTypePicker.tsx         — simple dropdown (read-only values)
    FilterSizePicker.tsx         — simple dropdown
    InterfaceMultiSelect.tsx     — multi-select for connection interfaces
    ConfirmDeleteDialog.tsx      — shared soft-delete confirmation

api/
  equipment.ts                   — all equipment API functions + TanStack Query hooks
```

### DataGrid Columns (v0.9.0 tabs)

**Cameras:**
| Column | Source |
|--------|--------|
| Model | `model_name` |
| Manufacturer | `manufacturer.name` |
| Sensor | `sensor.model_name` + `sensor.sensor_type` |
| Cooled | `cooled` (boolean chip) |
| Connector | `connector_size.name` |
| Actions | Edit, Delete buttons |

**Telescopes:**
| Column | Source |
|--------|--------|
| Model | `model_name` |
| Manufacturer | `manufacturer.name` |
| Design | `optical_design.name` |
| Aperture | `aperture_mm` mm |
| Configs | count of configurations |
| Actions | Edit, Delete buttons |

**Filters:**
| Column | Source |
|--------|--------|
| Model | `model_name` |
| Manufacturer | `manufacturer.name` |
| Type | `filter_type.name` (formatted) |
| Passbands | `passband_lines` summary (e.g., "Ha", "Ha+Oiii") |
| Size | `filter_size.name` |
| Actions | Edit, Delete buttons |

### Dialog UX

**Simple fields:** MUI TextField, Switch (for booleans), Autocomplete (for FK pickers).

**Child tables (telescope configs, filter passbands):** MUI Accordion within the dialog. Each child item is a collapsible panel:
- Collapsed: shows summary (config name + key specs, or line name + wavelength)
- Expanded: shows all editable fields
- Delete button (icon) on each panel header
- "Add Configuration" / "Add Passband" button below the accordion stack
- Native config marked with a star icon; at least one config must be native

**Junction tables (interfaces, connectors):** Chip array with an "Add" button. Each chip has an × to remove. Add opens a small dropdown/popover to pick from available options.

**Save behavior:** Clicking Save on the dialog sends the full state to the API. For parent + children, the API receives the parent update plus the full list of children (create replaces all). For junction tables, the API receives the full list of IDs.

### API Client

`frontend/src/api/equipment.ts`:

```typescript
// Types for all equipment entities
export interface Manufacturer { id: number; name: string; ... }
export interface Camera { id: number; manufacturer: Manufacturer; sensor: Sensor; ... }
// ... etc

// Fetch functions
export function fetchCameras(includeRetired?: boolean): Promise<Camera[]>
export function fetchCamera(id: number): Promise<Camera>
export function createCamera(data: CameraCreate): Promise<Camera>
export function updateCamera(id: number, data: CameraUpdate): Promise<Camera>
export function deleteCamera(id: number): Promise<void>
// ... same pattern for all types

// TanStack Query hooks used directly in components via useQuery/useMutation
```

### Query Invalidation

On successful mutation (create/update/delete):
- Invalidate the list query for the affected type
- For child table mutations (config, passband), also invalidate the parent's detail query
- Snackbar feedback on success/error (same pattern as header editing)

## Testing

### Backend Tests

File: `backend/tests/test_equipment_api.py`

- CRUD for each equipment type: create, list, get, update, soft-delete
- Validation: missing required fields return 422, invalid FK returns 400
- Soft delete: deleted item excluded from default list, included with `?include_retired=true`
- Junction tables: create camera with interface_ids, verify junction rows created
- Child tables: create telescope, add/update/delete configurations, verify cascade
- Filter passbands: create filter, add passbands, verify filter_summary view
- Telescope native config: exactly one is_native=1 enforced

### Frontend Tests

- Frontend build passes (`npm run build`)
- No dedicated component tests in v0.9.0 (manual testing for UI)

## What's NOT in v0.9.0

- Remaining equipment tabs (Sensors, Mounts, Focusers, Filter Wheels, OAGs, Guide Scopes, Computers, Software, Manufacturers, Lookup Tables) — v0.9.1
- Seed loader
- FITS resolver
- Rig management
- Optimistic updates (keep it simple — refetch on mutation)
