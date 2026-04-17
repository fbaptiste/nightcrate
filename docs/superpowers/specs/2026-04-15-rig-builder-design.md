# NightCrate Rig Builder — Implementation Spec

<!-- Saved from user-provided spec, 2026-04-15 -->
<!-- See corrections at the bottom of this file -->

This spec defines the rig system: a user-composed template that assembles equipment into a named imaging configuration. Rigs serve three purposes: (1) giving users a single place to see and manage their equipment setups, (2) powering optical calculators that would otherwise require external tools, and (3) providing the FITS resolver and ingest pipeline with the context they need to disambiguate equipment from FITS headers.

Target: SQLite. Stack: Python/FastAPI backend + React/TypeScript frontend. Current migration: 0008.

**Dependencies (must already exist):**
- The equipment schema and all equipment tables (shipped in v0.11.0)
- `telescope_configuration` with `is_native` support
- `filter_wheel.num_positions`
- All equipment CRUD APIs
- The `location` table (shipped in v0.11.0, migration 0007)

**Out of scope for this change:**
- The ingest pipeline, sessions, sub_frames, projects — those come later and consume rigs; this spec produces them.
- The FITS resolver's rig-aware filter resolution — the `filter_wheel_filter` junction table is renamed here to `rig_filter_slot` and defined with the schema the resolver expects, but the resolver code changes are not part of this spec.
- Per-session equipment overrides — that's the session/sub_frame layer's job.
- Any AI analyzer integration.

---

## Corrections identified during code review (2026-04-15)

These corrections are based on reviewing the spec against the actual codebase:

1. **Migration approach:** Seeing columns on `location` go in `0007.locations.sql` (edit in place, pre-release policy), NOT via ALTER TABLE in 0009. Migration 0009 only contains rig-specific tables.

2. **Missing focuser_name:** `rig_summary` view needs `LEFT JOIN focuser` and `RigOut` needs `focuser_name: str | None` for consistency with other optional slots.

3. **Missing guide calculator fields in RigCalculators:** Add `guide_image_scale_arcsec_per_pixel: float | None` and `guide_field_of_view_arcmin: tuple[float, float] | None`.

4. **PUT not PATCH:** Use `PUT` for rig updates to match established equipment API pattern (PUT with `exclude_unset=True`).

5. **Live calculator preview:** Compute basic calculators (image scale, FOV, resolution limits) client-side from equipment options data. No preview endpoint needed. Sampling assessment (needs location seeing) deferred to after save or fetched separately.

6. **Nullable guide_scope.focal_length_mm:** Guard against NULL in guide calculator — skip guide calculations if focal_length_mm is missing.

7. **OpenAPI tag + router registration:** Add "Rigs" tag to `main.py` openapi_tags and register the router.

8. **Filter slot joins:** `RigFilterSlotOut` needs filter → filter_type and filter → filter_passband joins in the API layer.

9. **Telescope config grouping:** Equipment options endpoint returns configs nested under parent telescopes via `TelescopeWithConfigs` wrapper.

10. **Guide scope focal length in RigOut:** Include `guide_scope_focal_length_mm: float | None` so the frontend can compute guide system metrics or include in calculator display.

11. **D3 for sampling chart:** Confirmed by Fred — use D3 for the sampling visualization, not basic SVG or MUI X Charts.

12. **Imaging camera binning selector in calculator UI:** The spec computes binned values but the UI needs an explicit binning toggle/selector (1×1, 2×2, 3×3, 4×4) on the calculator panel. Changing binning should update all primary metrics (image scale, FOV, sampling assessment), not just the sampling chart bars.

13. **Seeing slider instead of manual input fields:** Replace the "optional manual seeing input fields" with a continuous slider (0.5″–6.0″) with labeled quality zones:
    - 0.5–1.0″ = Excellent
    - 1.0–2.0″ = Good  
    - 2.0–4.0″ = OK
    - 4.0–5.0″ = Poor
    - 5.0–6.0″ = Very Poor
    
    Default position: midpoint of the user's location seeing range (e.g., 3.0″ for a 2.0–4.0″ location). If no location seeing set, default to middle of "OK" range (3.0″). The slider value feeds directly into the sampling assessment — dragging it updates the ideal sampling zone and assessment in real time. This is a transient override (not persisted), replacing the spec's `seeing_low`/`seeing_high` query params with a single seeing FWHM value from the slider.

---

<!-- Original spec continues below -->

---

## Table of contents

1. Design decisions
2. Schema
3. Rig validation rules
4. API
5. Optical calculators
6. UI
7. Integration with downstream specs
8. Deliverables

---

## 1. Design decisions

### 1.1 Rig is a template, not a historical record

A rig represents the user's *current* equipment configuration. When the user swaps a camera or adds a filter, they edit the rig. Historical accuracy is the responsibility of `sub_frame` — each sub_frame records the actual equipment used at capture time. The rig is just a convenient starting point for populating those fields.

This means: no rig versioning, no rig history table, no temporal tracking. Edits are destructive updates. This keeps the model simple.

### 1.2 Fixed slot model

Rigs have a fixed set of equipment slots rather than a flexible component list. Real imaging rigs are highly stereotyped — an OTA, a camera, a filter system, a mount, guiding gear, and peripherals. A slot model maps directly to how astrophotographers think and talk about their setups, and it makes the calculator and resolver integrations straightforward because the code knows exactly which fields exist.

The slots are:

| Slot | FK target | Required | Notes |
|------|-----------|----------|-------|
| OTA configuration | `telescope_configuration` | **Yes** | Commits to a specific focal length / F-ratio. Not the bare telescope — the configuration. |
| Imaging camera | `camera` | **Yes** | The main acquisition camera. |
| Filter wheel | `filter_wheel` | No | OSC rigs and unfiltered setups skip this. |
| Filters (ordered) | `rig_filter_slot` | No | Only meaningful if filter wheel is assigned. See §2. |
| Single filter | `filter` | No | For fixed-filter or no-wheel setups. Mutually exclusive with filter wheel in validation, not in schema. |
| Mount | `mount` | No | |
| Focuser | `focuser` | No | |
| OAG | `oag` | No | |
| Guide scope | `guide_scope` | No | |
| Guide camera | `camera` | No | Points at the same `camera` table — a camera is a camera. |
| Computer | `computer` | No | The acquisition PC/controller. |
| Capture software | `software` | No | |

**Minimum viable rig:** OTA configuration + imaging camera. That's the floor for any calculator to work. Everything else is optional and additive.

### 1.3 OTA slot points at telescope_configuration, not telescope

Every meaningful optical calculation needs a concrete focal length and aperture. Those live on `telescope_configuration`, not on the bare `telescope`. If the rig pointed at a bare OTA, calculators would require a second selection every time.

For users who regularly swap configurations (Askar V at 360mm vs 500mm), the right answer is two rigs. These are genuinely different optical setups with different image scales, FOVs, and target lists. A rig named "Askar V (V60 Native)" and another named "Askar V (V80 + Reducer)" reflects how users think about their gear.

### 1.4 Filter assignments live on the rig, not the filter wheel

The same physical filter wheel could be loaded with different filters in different rigs, or even re-loaded on the same rig between seasons. The rig is the right place to record "slot 3 = Ha 7nm" because:

- It enables the FITS resolver's two-phase filter handling: given a rig context, the resolver can map a wheel position or line name to a specific physical filter.
- It solves the "which filter is in which slot" documentation problem — the rig page is where a user records and checks their current filter loadout.
- Per-session overrides (future) can start from the rig's filter assignments as defaults and let the user swap individual slots.

### 1.5 Default rig flag

Like the default location, a single rig can be marked as the default. This is used as the pre-selection when the user creates a new session or project (future features). Enforced as a partial unique index — at most one rig with `is_default = 1`.

### 1.6 Clone rig as a convenience

Creating a second rig that differs by one component (different OTA config, same everything else) is a common operation. A "Clone Rig" action copies all slots and filter assignments into a new rig with a "(Copy)" suffix, ready for editing.

### 1.7 No rig-to-location binding

Rigs and locations are orthogonal concepts. A user might take a rig to a dark site or use it from their backyard. Don't couple them.

### 1.8 Seeing conditions live on the location, feed into rig calculators

The sampling assessment calculator needs a seeing range (FWHM in arcseconds) to determine whether a rig is over/under/well-sampled. Rather than hardcoding defaults or asking the user to enter seeing every time, the seeing range is stored on the `location` record.

This is the right home for seeing data because seeing is a property of the *site*, not the rig. The same rig at a mountain dark site (1.0–2.0″) and a suburban backyard (2.0–4.0″) has very different sampling characteristics. When the user selects a location in the calculator, the seeing values flow through automatically.

**Sourcing the data:** No reliable global "median seeing by coordinates" database or API exists for amateur sites. Professional observatory seeing measurements (DIMM monitors) cover a handful of mountaintop locations. Forecast services like Meteoblue provide nightly estimates but tend to be optimistic at non-mountain sites and aren't suitable for long-term site characterization.

The approach is:

1. **Manual entry with guidance (now).** Two fields on the location record: `typical_seeing_low_arcsec` and `typical_seeing_high_arcsec`. The UI provides a reference table to help users estimate: mountain observatory 0.5–1.5″, rural dark site 1.5–3.0″, suburban backyard 2.0–4.0″, urban 3.0–5.0″. Most experienced astrophotographers already know their typical seeing from measured FWHM in processed subs.

2. **Derive from imaging history (future, post-ingest).** Once the ingest pipeline is running and sub_frames have FWHM data, NightCrate can compute the actual median seeing from the user's own imaging history at each location. This is the gold standard — real measurements from real nights at their actual site. A simple query: median FWHM from sub_frames captured at this location, corrected for pixel scale. Not part of this spec, but the schema is designed to accommodate it.

**Fallback:** If a location has no seeing values set, the calculators use 2.0–4.0″ as a sensible default for non-mountain amateur sites.

---

## 2. Schema

Migration: `0009.rig.sql`

### Location table additions

Add seeing columns to the existing `location` table:

```sql
ALTER TABLE location ADD COLUMN typical_seeing_low_arcsec REAL
    CHECK (typical_seeing_low_arcsec IS NULL OR typical_seeing_low_arcsec > 0);

ALTER TABLE location ADD COLUMN typical_seeing_high_arcsec REAL
    CHECK (typical_seeing_high_arcsec IS NULL OR typical_seeing_high_arcsec > 0);
```

**Application-layer validation:** if both are provided, `typical_seeing_low_arcsec` must be ≤ `typical_seeing_high_arcsec`. If only one is provided, that's fine — the calculator will use the single value as both bounds (point estimate rather than range).

These columns are nullable. NULL means "not set — use defaults." The location CRUD API and UI are updated to expose these fields (see §4 and §6).

### Rig table

```sql
CREATE TABLE rig (
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

-- At most one default rig
CREATE UNIQUE INDEX idx_rig_one_default
    ON rig(is_default)
    WHERE is_default = 1;

CREATE INDEX idx_rig_telescope_configuration ON rig(telescope_configuration_id);
CREATE INDEX idx_rig_camera ON rig(camera_id);

-- updated_at trigger
CREATE TRIGGER trg_rig_updated_at
AFTER UPDATE ON rig
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE rig SET updated_at = datetime('now') WHERE id = NEW.id;
END;
```

**No seed tracking columns** on `rig`. Rigs are always user-created, never seeded. No `source`, `seed_key`, `seed_hash`.

### Filter slot junction table

This is the table the FITS resolver spec references as `filter_wheel_filter`. It is scoped to the rig (not the filter wheel alone) because the same wheel can carry different filters in different rigs.

```sql
CREATE TABLE rig_filter_slot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rig_id INTEGER NOT NULL REFERENCES rig(id) ON DELETE CASCADE,
    slot_number INTEGER NOT NULL CHECK (slot_number >= 1),
    filter_id INTEGER NOT NULL REFERENCES filter(id),
    UNIQUE (rig_id, slot_number),
    UNIQUE (rig_id, filter_id)
);

CREATE INDEX idx_rig_filter_slot_rig ON rig_filter_slot(rig_id);
```

**Constraints:**

- `UNIQUE (rig_id, slot_number)` — one filter per slot per rig.
- `UNIQUE (rig_id, filter_id)` — a filter can't appear in two slots on the same rig. (A user doesn't put the same physical filter in two wheel positions.)
- `slot_number` starts at 1, matching how filter wheels are labeled in acquisition software.

**Application-layer validation** (not enforceable in SQLite without triggers; enforce in the API):
- `slot_number` must be ≤ the rig's filter wheel's `num_positions`.
- `rig_filter_slot` rows should only exist when the rig has a `filter_wheel_id`. If the user removes the filter wheel from a rig, CASCADE on the rig's filter slots (handle in API — delete `rig_filter_slot` rows when `filter_wheel_id` is set to NULL).

### FITS resolver compatibility

The FITS resolver spec references `filter_wheel_filter` with this query pattern:

```sql
SELECT DISTINCT f.id, f.active
FROM filter f
JOIN filter_passband fp ON fp.filter_id = f.id
JOIN filter_wheel_filter fwf ON fwf.filter_id = f.id
WHERE fp.line_name = ?
  AND fwf.filter_wheel_id = ?
```

Under the rig-scoped design, the resolver query becomes:

```sql
SELECT DISTINCT f.id, f.active
FROM filter f
JOIN filter_passband fp ON fp.filter_id = f.id
JOIN rig_filter_slot rfs ON rfs.filter_id = f.id
WHERE fp.line_name = ?
  AND rfs.rig_id = ?
```

The `RigContext` dataclass in the resolver spec already carries `rig_id`. The resolver's filter resolution method should use `rig_id` instead of `filter_wheel_id` for scoping. This is a minor signature change in the resolver — document it but don't implement it in this spec.

### View: rig_summary

A convenience view for listing rigs with their key equipment names resolved. Avoids N+1 queries in the rig list UI.

```sql
CREATE VIEW rig_summary AS
SELECT
    r.id,
    r.name,
    r.description,
    r.is_default,
    r.active,
    r.created_at,
    r.updated_at,
    -- OTA
    t.model_name AS telescope_name,
    tc.config_name AS telescope_config_name,
    tc.effective_focal_length_mm,
    tc.effective_focal_ratio,
    t.aperture_mm,
    -- Camera
    c.model_name AS camera_name,
    s.pixel_size_um,
    s.resolution_x AS sensor_resolution_x,
    s.resolution_y AS sensor_resolution_y,
    s.sensor_width_mm,
    s.sensor_height_mm,
    s.sensor_type,
    -- Mount
    m.model_name AS mount_name,
    -- Filter wheel
    fw.model_name AS filter_wheel_name,
    fw.num_positions AS filter_wheel_positions,
    -- Guide
    gc.model_name AS guide_camera_name,
    gs.model_name AS guide_scope_name,
    gs.focal_length_mm AS guide_scope_focal_length_mm,
    oag.model_name AS oag_name,
    -- Peripherals
    comp.model_name AS computer_name,
    sw.name AS software_name,
    -- Single filter (for no-wheel setups)
    sf.model_name AS single_filter_name
FROM rig r
JOIN telescope_configuration tc ON tc.id = r.telescope_configuration_id
JOIN telescope t ON t.id = tc.telescope_id
JOIN camera c ON c.id = r.camera_id
JOIN sensor s ON s.id = c.sensor_id
LEFT JOIN mount m ON m.id = r.mount_id
LEFT JOIN filter_wheel fw ON fw.id = r.filter_wheel_id
LEFT JOIN camera gc ON gc.id = r.guide_camera_id
LEFT JOIN guide_scope gs ON gs.id = r.guide_scope_id
LEFT JOIN oag ON oag.id = r.oag_id
LEFT JOIN computer comp ON comp.id = r.computer_id
LEFT JOIN software sw ON sw.id = r.software_id
LEFT JOIN filter sf ON sf.id = r.single_filter_id;
```

---

## 3. Rig validation rules

All enforced at the API layer. Return 422 with descriptive error messages.

1. **Name uniqueness.** Rig names must be unique (enforced by schema, but return a friendly error, not a raw UNIQUE constraint violation).

2. **OTA config and camera are required.** These are NOT NULL in the schema, so the API just validates they're present in the request body.

3. **Filter wheel / single filter mutual exclusivity (soft).** If both `filter_wheel_id` and `single_filter_id` are provided, return a warning (not an error). The UI should discourage this but the schema allows it — some edge cases exist (e.g., an IR-cut filter in front of a filter wheel). If the user wants both, let them.

4. **Filter slot count must not exceed wheel capacity.** If the rig has a filter wheel with `num_positions = 7`, reject `rig_filter_slot` rows with `slot_number > 7`.

5. **Filter slots require a filter wheel.** If `filter_wheel_id` is NULL, reject any `rig_filter_slot` rows in the same request.

6. **Retired equipment warning.** If any referenced equipment has `active = 0`, return the rig successfully but include a warning in the response indicating which slots reference retired equipment. Don't block creation — the user might be documenting a historical rig.

7. **Guide camera ≠ imaging camera.** Warn (not error) if `guide_camera_id = camera_id`. It's technically possible (some people swap cameras) but usually a mistake.

---

## 4. API

Base path: `/api/rigs`

### Pydantic models

```python
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
    """All fields optional — PATCH semantics."""
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
    # When filter_slots is provided, it replaces all existing slots (full replacement, not merge).
    # When filter_slots is None (omitted), existing slots are left untouched.

class RigFilterSlotOut(BaseModel):
    slot_number: int
    filter_id: int
    filter_name: str
    filter_type_name: str
    # Include passband summary for display
    passbands: list[str]  # e.g. ["Ha", "Oiii"] for duoband

class RigWarning(BaseModel):
    field: str
    message: str

class RigOut(BaseModel):
    id: int
    name: str
    description: str | None
    # Equipment IDs + display names (from rig_summary view)
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
    oag_id: int | None
    oag_name: str | None
    guide_scope_id: int | None
    guide_scope_name: str | None
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
    # Computed optical properties (from §5)
    calculators: RigCalculators
    warnings: list[RigWarning]

class RigCalculators(BaseModel):
    """Computed optical properties derived from the rig's OTA config + camera."""
    image_scale_arcsec_per_pixel: float
    image_scale_arcsec_per_pixel_binned: dict[int, float]  # {1: 0.40, 2: 0.79, 3: 1.19}
    field_of_view_arcmin: tuple[float, float]  # (width, height)
    field_of_view_deg: tuple[float, float]
    focal_ratio: float
    dawes_limit_arcsec: float
    rayleigh_limit_arcsec: float
    max_useful_magnification: float
    sensor_diagonal_mm: float | None
    image_circle_mm: float | None  # from telescope_configuration
    sensor_coverage_pct: float | None  # sensor_diagonal / image_circle × 100
    sampling_assessment: SamplingAssessment

class SamplingAssessment(BaseModel):
    """Sampling assessment relative to seeing conditions."""
    image_scale: float  # unbinned arcsec/pixel
    ideal_range_low: float  # arcsec/pixel
    ideal_range_high: float  # arcsec/pixel
    seeing_fwhm_low: float  # seeing range low (arcsec)
    seeing_fwhm_high: float  # seeing range high (arcsec)
    seeing_source: str  # 'location' | 'override' | 'default'
    seeing_location_name: str | None  # name of the location, if seeing_source = 'location'
    assessment: str  # 'undersampled' | 'well_sampled' | 'oversampled'
    recommendation: str  # human-readable
    binning_recommendations: dict[int, str]  # {1: 'oversampled', 2: 'well_sampled', 3: 'undersampled'}
```

### Endpoints

**`GET /api/rigs`** — List all rigs.

Returns `list[RigOut]`. Includes computed calculators for each rig. Query params:
- `active_only: bool = True` — filter to active rigs only.
- `location_id: int | None = None` — location to pull seeing values from for sampling assessment. If omitted, uses the default location. If no default location exists or the location has no seeing values, falls back to 2.0–4.0″.

Implementation: query `rig_summary` view, join `rig_filter_slot` per rig, resolve seeing from location, compute calculators.

**`GET /api/rigs/{rig_id}`** — Get a single rig.

Returns `RigOut`. 404 if not found. Same `location_id` query param as the list endpoint.

**`POST /api/rigs`** — Create a rig.

Request body: `RigCreate`. Returns `RigOut` with 201 status. Validation per §3.

Transactional: INSERT rig row, INSERT all `rig_filter_slot` rows, handle `is_default` flag (clear other rigs' default if setting this one).

**`PUT /api/rigs/{rig_id}`** — Update a rig.

Request body: `RigUpdate`. Returns `RigOut`. Uses `exclude_unset=True` — only provided fields are updated.

Special handling for `filter_slots`: when the field is present in the request body (even as an empty list), it triggers a **full replacement** — DELETE all existing `rig_filter_slot` rows for this rig, INSERT the new ones. When the field is absent (not in the JSON), existing slots are untouched.

Special handling for `filter_wheel_id`: if set to `null`, also delete all `rig_filter_slot` rows (filters without a wheel are meaningless).

Special handling for `is_default`: if set to `true`, clear `is_default` on all other rigs in the same transaction.

**`DELETE /api/rigs/{rig_id}`** — Soft-delete a rig.

Sets `active = 0`. Does NOT delete `rig_filter_slot` rows (they CASCADE on hard delete only). Returns 204.

Future consideration: once sessions reference `rig_id`, prevent hard deletion of rigs that have associated sessions. For now, soft-delete is the only option exposed via API.

**`POST /api/rigs/{rig_id}/clone`** — Clone a rig.

Creates a new rig with all the same equipment slots and filter assignments. Name is set to `"{original_name} (Copy)"` — if that name already exists, append a number: `"(Copy 2)"`, etc. The clone is NOT marked as default. Returns the new `RigOut` with 201 status.

**`POST /api/rigs/{rig_id}/restore`** — Restore a soft-deleted rig.

Sets `active = 1`. Returns `RigOut`.

**`GET /api/rigs/{rig_id}/calculators`** — Get calculator results only.

Returns `RigCalculators`. Useful for the UI to refresh calculations without fetching the full rig. Accepts optional query params:
- `location_id: int | None = None` — location to pull seeing values from. If omitted, uses the default location.
- `seeing_low: float | None = None` — explicit seeing FWHM low bound override (arcsec). If provided, takes precedence over location values.
- `seeing_high: float | None = None` — explicit seeing FWHM high bound override (arcsec). If provided, takes precedence over location values.
- `binning: int = 1` — binning factor for primary calculation

**Seeing resolution order:** (1) explicit `seeing_low`/`seeing_high` query params if provided → `seeing_source = 'override'`; (2) the specified or default location's `typical_seeing_low/high_arcsec` if set → `seeing_source = 'location'`; (3) hardcoded 2.0–4.0″ fallback → `seeing_source = 'default'`.

**`GET /api/rigs/equipment-options`** — Get available equipment for rig building.

Returns all active equipment grouped by type, suitable for populating dropdowns. Each entry includes the minimum fields needed for display and selection:

```python
class EquipmentOptionsOut(BaseModel):
    telescope_configurations: list[TelescopeConfigOption]
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

Each option type includes `id`, display name (with manufacturer), and any fields needed for the UI (e.g., `num_positions` for filter wheels, `pixel_size_um` for cameras, `effective_focal_length_mm` for telescope configs). Group telescope configurations under their parent telescope for hierarchical display.

---

## 5. Optical calculators

All computations are performed server-side and returned as part of `RigOut`. They're also available standalone via `GET /api/rigs/{rig_id}/calculators`. All formulas use well-established optical constants — no external API calls, no libraries beyond basic math.

### 5.1 Image scale (arcsec/pixel)

```
image_scale = (pixel_size_um / effective_focal_length_mm) × 206.265
```

The constant 206.265 converts radians to arcseconds (arcseconds per radian = 3600 × 180 / π ≈ 206264.8, but the per-micron-per-mm version is 206.265).

Compute for binning factors 1, 2, 3, and 4:

```
image_scale_binned(n) = image_scale × n
```

### 5.2 Field of view

```
fov_width_arcmin  = (sensor_resolution_x × pixel_size_um × 206.265) / (effective_focal_length_mm × 60)
fov_height_arcmin = (sensor_resolution_y × pixel_size_um × 206.265) / (effective_focal_length_mm × 60)
```

Or equivalently:

```
fov_width_deg  = (sensor_resolution_x × image_scale) / 3600
fov_height_deg = (sensor_resolution_y × image_scale) / 3600
```

If `sensor_width_mm` and `sensor_height_mm` are available, use the physical sensor dimensions for a more accurate calculation:

```
fov_width_deg  = 2 × arctan(sensor_width_mm / (2 × effective_focal_length_mm)) × (180 / π)
fov_height_deg = 2 × arctan(sensor_height_mm / (2 × effective_focal_length_mm)) × (180 / π)
```

Prefer the arctan version when physical dimensions are available; fall back to the pixel-count version when they're not.

### 5.3 Resolution limits

```
dawes_limit_arcsec     = 116.0 / aperture_mm
rayleigh_limit_arcsec  = 138.0 / aperture_mm
max_useful_magnification = 2.0 × aperture_mm
```

### 5.4 Sensor coverage

```
sensor_diagonal_mm = √(sensor_width_mm² + sensor_height_mm²)
```

If `effective_image_circle_mm` is available from the telescope configuration:

```
sensor_coverage_pct = (sensor_diagonal_mm / effective_image_circle_mm) × 100
```

If `sensor_coverage_pct > 100`, include a warning: the sensor extends beyond the OTA's illuminated image circle, expect vignetting in the corners.

If physical sensor dimensions are unavailable, compute from pixel count and pixel size:

```
sensor_width_mm  = resolution_x × pixel_size_um / 1000
sensor_height_mm = resolution_y × pixel_size_um / 1000
```

### 5.5 Sampling assessment

The ideal sampling range for a given seeing FWHM is:

```
ideal_scale_low  = seeing_fwhm_low / 3.0    (Nyquist-ish lower bound)
ideal_scale_high = seeing_fwhm_high / 2.0   (practical upper bound)
```

**Seeing resolution order:**

1. **Explicit override** — if the caller passes `seeing_low`/`seeing_high` query params, use those. Set `seeing_source = 'override'`.
2. **Location-based** — if a `location_id` is provided (or the default location is used), read `typical_seeing_low_arcsec` and `typical_seeing_high_arcsec` from the location record. If both are set, use them. If only one is set, use it for both bounds (point estimate). Set `seeing_source = 'location'`, `seeing_location_name = location.name`.
3. **Fallback** — if no location is available or the location's seeing fields are NULL, use 2.0–4.0 arcsec FWHM (covers "OK" to "poor" — typical for non-mountain amateur sites). Set `seeing_source = 'default'`.

```python
def resolve_seeing(
    location: Location | None,
    override_low: float | None,
    override_high: float | None,
) -> tuple[float, float, str, str | None]:
    """Returns (low, high, source, location_name)."""
    if override_low is not None or override_high is not None:
        low = override_low or override_high
        high = override_high or override_low
        return (low, high, 'override', None)
    if location is not None:
        low = location.typical_seeing_low_arcsec
        high = location.typical_seeing_high_arcsec
        if low is not None or high is not None:
            low = low or high
            high = high or low
            return (low, high, 'location', location.name)
    return (2.0, 4.0, 'default', None)
```

Assessment logic:

```python
def assess_sampling(image_scale: float, ideal_low: float, ideal_high: float) -> str:
    if image_scale < ideal_low:
        return 'oversampled'
    elif image_scale > ideal_high:
        return 'undersampled'
    else:
        return 'well_sampled'
```

Generate recommendations per binning level:

```python
binning_recommendations = {}
for bin_factor in [1, 2, 3, 4]:
    binned_scale = image_scale * bin_factor
    binning_recommendations[bin_factor] = assess_sampling(binned_scale, ideal_low, ideal_high)
```

Human-readable recommendation string:

- If unbinned is `oversampled`: "At {scale}″/pixel unbinned, this setup is oversampled for {seeing_low}–{seeing_high}″ seeing. Consider 2× binning ({binned_scale}″/pixel) for better SNR. Will require a good mount and careful guiding."
- If unbinned is `well_sampled`: "At {scale}″/pixel, this setup is well-matched to {seeing_low}–{seeing_high}″ seeing conditions."
- If unbinned is `undersampled`: "At {scale}″/pixel, this setup is undersampled for {seeing_low}–{seeing_high}″ seeing. Stars will appear blocky. Consider a longer focal length or smaller pixels."

When `seeing_source = 'location'`, append to the recommendation: " (seeing from {location_name})". When `seeing_source = 'default'`, append: " (using default 2–4″ seeing — set your location's typical seeing for a more accurate assessment)".

### 5.6 Guide camera calculations (when guide camera + guide scope are both assigned)

> **Superseded by** [`2026-04-16-guide-suitability-design.md`](2026-04-16-guide-suitability-design.md).
> Guide camera math was replaced in v0.12.0 with a full guide-suitability assessment
> (rating bands, 6″/pixel hard cap, binning + centroid parameters, OAG support, and a
> nested `guide_suitability` field replacing the old top-level `guide_image_scale_*` /
> `guide_field_of_view_*` fields on `RigCalculators`).

If both `guide_camera_id` and `guide_scope_id` are present (guidescope guiding, not OAG):

```
guide_image_scale = (guide_pixel_size_um / guide_focal_length_mm) × 206.265
guide_fov_width_arcmin = (guide_resolution_x × guide_pixel_size_um × 206.265) / (guide_focal_length_mm × 60)
guide_fov_height_arcmin = (guide_resolution_y × guide_pixel_size_um × 206.265) / (guide_focal_length_mm × 60)
```

Include in `RigCalculators` as optional `guide_image_scale_arcsec_per_pixel` and `guide_field_of_view_arcmin` fields.

---

## 6. UI

### 6.1 Route and navigation

- **Route:** `/rigs`
- **Nav position:** top-level, between Equipment and Locations (or after Locations — wherever it fits in the existing nav order). The rig page bridges Equipment (which it composes) and the future catalog/session pages (which will consume it).

### 6.2 Rig list view

The landing view at `/rigs`. Shows all rigs as cards (not a data grid — rigs are few and information-dense).

Each card shows:
- **Rig name** (bold, prominent)
- **Default badge** (if `is_default`)
- **OTA:** "{telescope_name} — {config_name}" (e.g., "Celestron C11 — 0.7x Reducer")
- **Camera:** "{camera_name}" (e.g., "ZWO ASI 2600MM Pro")
- **Key stats line:** "{focal_length}mm  f/{focal_ratio}  {image_scale}″/px  {fov_width}×{fov_height}′"
- **Mount:** if assigned
- **Filter summary:** compact line showing assigned filters, e.g., "7-pos: L R G B Ha Oiii Sii" or "No filter wheel"
- **Sampling badge:** colored chip showing "Well Sampled" / "Oversampled" / "Undersampled" (use blue/orange palette, never red/green)

Card actions: Edit, Clone, Delete (soft), Set as Default, Restore (for soft-deleted, shown in a separate "Retired" section).

**"+ New Rig" button** at the top — opens the rig editor dialog.

### 6.3 Rig editor dialog

A modal dialog for create and edit. Not a separate page — rigs don't have enough complexity to warrant a page, and inline editing avoids route transitions.

**Layout:** a structured form with grouped sections:

**Section: Identity**
- Name (text field, required)
- Description (text field, optional)

**Section: Optical Train**
- Telescope + Configuration (hierarchical dropdown: first select telescope, then configuration — or a single grouped dropdown with configs nested under their telescope). Required.
- Imaging Camera (dropdown). Required.

**Section: Filtration**
- Filter Wheel (dropdown, optional). When selected, show a filter slot grid.
- **Filter Slot Grid:** Rendered when a filter wheel is selected. Shows N rows (one per wheel position, driven by the wheel's `num_positions`). Each row: slot number label + filter dropdown. Dropdowns are optional — empty slots are fine.
- OR: Single Filter (dropdown, optional). Shown when no filter wheel is selected, or as an additional slot.

**Section: Mount & Guiding**
- Mount (dropdown, optional)
- Guiding mode: toggle or radio — "OAG" | "Guide Scope" | "None"
  - If OAG: OAG dropdown + Guide Camera dropdown
  - If Guide Scope: Guide Scope dropdown + Guide Camera dropdown
  - If None: hide both

**Section: Peripherals**
- Focuser (dropdown, optional)
- Computer (dropdown, optional)
- Capture Software (dropdown, optional)

**Section: Options**
- Default rig toggle
- Notes (multiline text area)

**Live calculator preview:** As the user selects equipment, the right side (or bottom, on mobile) shows a live-updating calculator panel with image scale, FOV, sampling assessment, and resolution limits. This updates on every equipment change. The preview only appears once both OTA config and camera are selected.

**Save / Cancel buttons.** Save triggers validation per §3. On success, close dialog and refresh the rig list.

### 6.4 Calculator panel (also shown on rig detail)

A dedicated panel showing all computed optical properties. This is the "you don't need to go to astronomy.tools anymore" feature.

**Location selector:** At the top of the calculator panel, a dropdown to select the imaging location. Defaults to the user's default location. Changing the location re-fetches calculator results with that location's seeing values. If the selected location has no seeing values set, show a subtle prompt: "Set typical seeing for this location in Location settings for a more accurate assessment."

**Metrics displayed:**

| Metric | Value | Notes |
|--------|-------|-------|
| Image Scale | 0.40″/pixel | With binning variants: 2×2 = 0.79, 3×3 = 1.19 |
| Field of View | 42.1′ × 28.1′ (0.70° × 0.47°) | Both arcmin and degrees |
| Focal Ratio | f/7.0 | From telescope configuration |
| Dawes Limit | 0.41″ | |
| Rayleigh Limit | 0.49″ | |
| Sensor Coverage | 87% of image circle | With warning if > 100% |
| Sampling | Oversampled for 2–4″ seeing | With recommendation text and seeing source |

**Seeing source indicator:** Below the sampling assessment, show where the seeing values came from: "Seeing: 2.0–4.0″ from Backyard Observatory" (location name) or "Seeing: 2.0–4.0″ (default — set in Location settings)" — helps the user understand what's driving the assessment and how to change it.

**Sampling visualization:** A horizontal bar chart (like the astronomy.tools CCD suitability calculator in the screenshot) showing the image scale at each binning level plotted against the ideal sampling zone for the selected seeing range. The ideal zone is highlighted. Bars that fall within the zone are colored favorably (blue); bars outside are colored differently (orange).

- X-axis: arcsec/pixel
- Y-axis: binning levels (1×1, 2×2, 3×3, 4×4)
- Shaded region: ideal sampling zone
- Seeing override: optional manual seeing input fields below the location selector, for quick "what if" exploration without changing the location record. Overrides are transient (not persisted).

**Guide system summary** (when guide camera + guide scope assigned):
- Guide image scale
- Guide FOV

### 6.5 Equipment dropdowns

All equipment dropdowns filter to `active = 1` by default. Include a "Show retired" toggle to also show `active = 0` items (grayed out, with a "(retired)" suffix).

Dropdown display format: "{manufacturer} — {model_name}" for most equipment. For telescope configurations: "{manufacturer} {telescope_model} — {config_name} ({focal_length}mm f/{focal_ratio})".

Dropdowns should be searchable/filterable for users with large equipment collections.

### 6.6 Location form update (seeing fields)

The existing Location edit form (on the `/locations` page) gets two new fields in a new "Seeing Conditions" section:

- **Typical Seeing (Best)** — numeric input, arcseconds, optional. Label: "Best typical seeing (FWHM, arcseconds)". Placeholder: "e.g. 2.0"
- **Typical Seeing (Worst)** — numeric input, arcseconds, optional. Label: "Worst typical seeing (FWHM, arcseconds)". Placeholder: "e.g. 4.0"

Below these fields, include a collapsible reference guide:

> **How to estimate your seeing:**
> Most astrophotographers can estimate seeing from the FWHM of stars in their processed subs. If you're not sure, use these rough guidelines based on site type:
>
> | Site Type | Typical Seeing Range |
> |-----------|---------------------|
> | Mountain observatory (>2000m) | 0.5–1.5″ |
> | Rural dark site | 1.5–3.0″ |
> | Suburban backyard | 2.0–4.0″ |
> | Urban / rooftop | 3.0–5.0″ |
>
> These values are used by the Rig calculators to assess whether your equipment is well-matched to your site conditions. Once NightCrate has ingested enough of your imaging data, it will be able to compute your actual seeing from measured star FWHM.

Validation: if both are provided, low must be ≤ high. If only one is provided, that's fine.

### 6.7 Colorblind safety

All color use in the rig UI must be colorblind-safe:
- Sampling assessment badges: use **blue** (well sampled) and **orange** (over/undersampled). Never red/green.
- Sampling bar chart: blue for bars in the ideal zone, orange for bars outside it.
- Warning/error states: use orange with icon, not red.

---

## 7. Integration with downstream specs

This section documents how the rig schema connects to the specs that consume it. No code changes in those specs are part of this deliverable — this is documentation to keep the specs consistent.

### 7.1 FITS resolver (nightcrate-fits-resolver-spec.md)

The resolver spec references `filter_wheel_filter` — this is now `rig_filter_slot`. The resolver's `RigContext` should carry `rig_id` (which it already does). The resolver query for line-name filter resolution should join `rig_filter_slot` on `rig_id` instead of joining a hypothetical `filter_wheel_filter` on `filter_wheel_id`.

**Action for resolver spec update:** Replace all references to `filter_wheel_filter` with `rig_filter_slot`. Replace `fwf.filter_wheel_id = ?` with `rfs.rig_id = ?`. The `RigContext` dataclass already has `rig_id` — no change needed there, but `filter_wheel_id` on `RigContext` can be dropped (it's now derivable from the rig row).

### 7.2 Ingest pipeline (nightcrate-ingest-pipeline-spec.md)

The pipeline's rig inference step (stage 4) queries the `rig` table to match resolved equipment against known rigs. The rig table defined here provides exactly the columns that query needs: `camera_id`, `telescope_configuration_id` (from which `telescope_id` is derivable via join), `mount_id`.

The pipeline spec's rig-matching query:

```sql
SELECT id FROM rig
WHERE (camera_id = ? OR camera_id IS NULL)
  AND (telescope_id = ? OR telescope_id IS NULL)
  AND (mount_id = ? OR mount_id IS NULL)
```

This needs a minor adjustment: the rig table stores `telescope_configuration_id`, not `telescope_id`. The query should join through `telescope_configuration` to get `telescope_id`, or match on `telescope_configuration_id` directly if the pipeline has resolved to a specific configuration (via FOCALLEN).

### 7.3 Session equipment overrides (future)

When the session/project schema lands, sessions will reference a `rig_id` as their starting template. The session's actual equipment will be stored either on the session itself or on individual sub_frames (per the existing spec decision: sub_frame is source of truth). The rig provides defaults; the session can override any slot.

Filter slot overrides at the session level: a future `session_filter_slot` table (or equivalent) would allow per-session changes to the filter loadout, starting from the rig's `rig_filter_slot` entries as defaults. Not part of this spec.

---

## 8. Deliverables

### 1. Schema migration (`0009.rig.sql`)

- `ALTER TABLE location` adding `typical_seeing_low_arcsec` and `typical_seeing_high_arcsec` columns per §2.
- `CREATE TABLE rig` with all columns, indexes, trigger, and partial unique index per §2.
- `CREATE TABLE rig_filter_slot` with columns, indexes, and unique constraints per §2.
- `CREATE VIEW rig_summary` per §2.

### 2. Backend: API router (`api/rigs.py`)

- All endpoints from §4.
- Request validation per §3.
- Rig CRUD with transactional filter slot handling.
- Equipment options endpoint.
- Seeing resolution logic (location lookup → fallback chain) integrated into all calculator-producing endpoints.

### 2b. Backend: Location API update (`api/locations.py`)

- Add `typical_seeing_low_arcsec` and `typical_seeing_high_arcsec` to the existing location create/update models and CRUD endpoints.
- Validation: if both provided, low ≤ high.

### 3. Backend: Pydantic models (`api/rig_models.py`)

- All models from §4: `RigCreate`, `RigUpdate`, `RigOut`, `RigFilterSlotIn`, `RigFilterSlotOut`, `RigCalculators`, `SamplingAssessment`, `RigWarning`, `EquipmentOptionsOut`, and per-type option models.

### 4. Backend: Calculator service (`services/rig_calculators.py`)

- Pure functions implementing all formulas from §5.
- `resolve_seeing()` function implementing the location → override → default fallback chain.
- No external dependencies beyond `math`.
- Called by the API layer to populate `RigCalculators` on every rig response.

### 5. Frontend: Rig page (`pages/Rigs.tsx`)

- Rig list with cards per §6.2.
- Rig editor dialog per §6.3.
- Calculator panel with location selector per §6.4.

### 5b. Frontend: Location form update

- Add seeing fields to location create/edit form per §6.6.
- Collapsible reference guide.

### 6. Frontend: API client (`api/rigs.ts`)

- Typed fetch functions for all rig endpoints.
- Location API client updated for new seeing fields (if not already covered by existing location client).

### 7. Tests

pytest-based, using in-memory SQLite with the equipment schema + rig migration applied.

- `test_rig_crud.py` — create, read, update, delete, restore. Verify filter slots are persisted and returned correctly. Verify soft-delete. Verify clone (including filter slot duplication and name collision handling).
- `test_rig_validation.py` — missing required fields, slot_number > num_positions, filter slots without filter wheel, duplicate slot numbers, duplicate filter IDs in same rig.
- `test_rig_default.py` — setting default clears other defaults. Only one default at a time.
- `test_rig_filter_slot_lifecycle.py` — add slots, replace slots (full replacement semantics), remove filter wheel clears slots.
- `test_rig_calculators.py` — verify image scale, FOV, Dawes limit, Rayleigh limit, sampling assessment for known inputs. Test with and without physical sensor dimensions. Test sensor coverage warning when diagonal > image circle. Test binning recommendations.
- `test_seeing_resolution.py` — verify the seeing fallback chain: explicit override wins over location, location wins over default. Test with location that has both seeing values set, only one set, neither set. Test that `seeing_source` and `seeing_location_name` are correctly populated in each case. Test default location auto-selection when no `location_id` is provided.
- `test_rig_warnings.py` — retired equipment warning, guide camera = imaging camera warning.
- `test_rig_summary_view.py` — verify the view returns correct joined data, including NULL optional slots.
- `test_equipment_options.py` — verify the options endpoint returns grouped, active-only equipment.
- `test_location_seeing_fields.py` — verify location CRUD accepts and returns seeing fields. Validate low ≤ high constraint. Verify NULL handling.

### 8. What NOT to build in this change

- The FITS resolver's rig-aware code changes (it already has a forward-compatible stub).
- Session or sub_frame tables or any ingest pipeline code.
- Per-session filter slot overrides.
- Rig history/versioning.
- Rig-to-location binding.
- Any seed data for rigs (rigs are always user-created).
- Back-focus calculator (would need to sum back-focus contributions across the entire optical train — interesting but not MVP).
- Plate scale / airy disk calculator (useful but deferred — can add to calculators later).
- Auto-derived seeing from imaging history (requires ingest pipeline + sub_frame FWHM data — documented as the planned long-term replacement for manual seeing entry in §1.8).

---

## Appendix A: Worked examples

These examples use Fred's actual equipment to validate the schema and calculators. Both rigs use Fred's default location: "Backyard Observatory" with `typical_seeing_low_arcsec = 2.0`, `typical_seeing_high_arcsec = 4.0`.

### Fred's C11 Rig

```
Rig name: "C11 Deep Sky"
Telescope configuration: Celestron C11 — 0.7x Reducer (1960mm f/7, aperture 280mm)
Camera: ZWO ASI 2600MM Pro (3.76μm, 6248×4176, mono, 23.5×15.7mm)
Mount: WarpAstron WD-20
Filter wheel: ZWO 7-position
Filter slots:
  1: ZWO Luminance
  2: ZWO Red
  3: ZWO Green
  4: ZWO Blue
  5: Optolong Ha 7nm
  6: Optolong Oiii 7nm
  7: Optolong Sii 7nm
OAG: (Fred's OAG)
Guide camera: ZWO ASI 178MM
Focuser: PrimaLuceLab ESATTO 2"
Computer: Geekom AX8 Max
Software: N.I.N.A.

Calculator results:
  Image scale: (3.76 / 1960) × 206.265 = 0.396″/pixel
  FOV (arctan): 2 × arctan(23.5 / (2 × 1960)) × (180/π) = 0.688° width
                2 × arctan(15.7 / (2 × 1960)) × (180/π) = 0.459° height
                = 41.3′ × 27.6′
  Dawes limit: 116 / 280 = 0.414″
  Rayleigh limit: 138 / 280 = 0.493″
  Sampling (seeing from Backyard Observatory: 2.0–4.0″):
    seeing_source: 'location'
    seeing_location_name: 'Backyard Observatory'
    Ideal range: 0.67–2.0″/pixel
    At 0.40″/pixel unbinned: oversampled
    At 0.79″/pixel 2×2: well sampled
    At 1.19″/pixel 3×3: well sampled
```

### Fred's Askar V Rig (V60 Native)

```
Rig name: "Askar V (V60 Native)"
Telescope configuration: Askar V — V60 Native (360mm f/6, aperture 60mm)
Camera: ZWO ASI 2600MM Pro (second unit)
Mount: ZWO AM5
Guide scope: Askar 52mm f/4 (208mm FL)
Guide camera: ZWO ASI 178MM (second unit)
Filter wheel: ZWO 7-position (second unit)
Filter slots:
  1: Optolong Luminance
  2: Optolong Red
  3: Optolong Green
  4: Optolong Blue
  5: Antlia Ha 3nm
  6: Antlia Oiii 3nm
  7: Antlia Sii 3nm
Software: ASIAIR

Calculator results:
  Image scale: (3.76 / 360) × 206.265 = 2.155″/pixel
  FOV (arctan): 2 × arctan(23.5 / (2 × 360)) × (180/π) = 3.738° width
                2 × arctan(15.7 / (2 × 360)) × (180/π) = 2.498° height
                = 224.3′ × 149.9′
  Dawes limit: 116 / 60 = 1.933″
  Rayleigh limit: 138 / 60 = 2.300″
  Sampling (seeing from Backyard Observatory: 2.0–4.0″):
    seeing_source: 'location'
    seeing_location_name: 'Backyard Observatory'
    Ideal range: 0.67–2.0″/pixel
    At 2.15″/pixel unbinned: slightly undersampled (borderline)
    At 4.31″/pixel 2×2: undersampled

  Guide system:
    Guide image scale: (2.4 / 208) × 206.265 = 2.380″/pixel
    Guide FOV: ~107′ × 71′

  Example with dark site override (seeing_low=1.0, seeing_high=2.0):
    seeing_source: 'override'
    Ideal range: 0.33–1.0″/pixel
    At 2.15″/pixel unbinned: undersampled
    — demonstrates how the same rig assessment changes for a mountain trip
```
