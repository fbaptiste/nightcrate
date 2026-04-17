# NightCrate "My Equipment" — Implementation Spec

Adds a user-owned flag (`is_mine`) to equipment, a dedicated sidebar section that surfaces only equipment the user has marked as theirs, and prioritization of owned equipment in rig-builder dropdowns.

Target: SQLite. Stack: Python/FastAPI backend + React/TypeScript frontend. Pre-release — migration edits in place are allowed; Fred recreates the DB from scratch.

**Dependencies (must already exist):**
- Equipment schema + all equipment tables (v0.11.0, migration `0005.equipment_schema.sql` / `0006.camera_guide_sensor.sql`).
- Equipment Management API (v0.11.0) and generic `EquipmentList` frontend component.
- Rig builder (v0.12.0 in progress, migration `0009.rigs.sql`). Rig dropdowns are where "My Equipment" prioritization applies.

**Out of scope:**
- Ownership quantities, purchase dates, serial numbers, price, notes.
- Multi-user or sharing concepts — NightCrate is single-user local-first.
- Any change to seed CSVs — `is_mine` is never seed-authored.
- Impact on rig validity — rigs reference equipment by FK regardless of `is_mine`. Building a rig from non-owned equipment (for planning) stays legal.
- A standalone "Show mine only" toggle on the regular equipment lists — the sidebar's "My Equipment" section already provides that path.

---

## Motivation

Users have hundreds of rows in the equipment DB (seed data covers market-available gear broadly). When configuring a rig, they need a fast path to the 10–20 pieces they actually own. A per-row ownership flag plus a dedicated sidebar view plus prioritized dropdowns solves this without modeling "ownership" as a richer first-class concept.

---

## Schema

Add one column to each of 10 existing equipment tables via **inline edits** to their original migration files (pre-release policy, per `CLAUDE.md`):

```sql
is_mine INTEGER NOT NULL DEFAULT 0 CHECK(is_mine IN (0, 1))
```

**Tables modified** (in `0005.equipment_schema.sql` / `0006.camera_guide_sensor.sql` as applicable):

- `camera`
- `telescope`
- `filter`
- `mount`
- `focuser`
- `filter_wheel`
- `oag`
- `guide_scope`
- `computer`
- `software`

**Tables NOT modified:**
- `sensor` — sensors are parts inside cameras, not owned standalone.
- `telescope_configuration` — a config belongs to its parent telescope; ownership is on the telescope.
- All junction tables (`camera_interface`, `telescope_connector`, etc.).
- All child tables (`filter_passband`, `filter_size_option`).
- All lookup/reference tables (`manufacturer`, `optical_design`, etc.).
- `location` (not equipment).

**Partial index per table:**

```sql
CREATE INDEX idx_<table>_mine ON <table>(is_mine) WHERE is_mine = 1;
```

Cheap, and the "My Equipment" sidebar queries always filter to `is_mine = 1`.

**Seed loader interaction.** `is_mine` is a user-managed column — the seed loader's `SeedableTable` registry in `seed_loader/registry.py` does not include it in the set of seed-authoritative columns, so the hash contract (v1) is unaffected. Marking a seed-loaded item as mine does not change its seed hash and does not cause re-seed to overwrite it on the next run. This matches how `created_at`/`updated_at` already behave. The spec adds a regression test pinning this.

---

## Backend API

### Response model changes

Every equipment `Response` Pydantic model in `api/equipment_models.py` for the 10 modified types gains `is_mine: bool`. No other response shape changes.

### List endpoint changes (`GET /api/equipment/<type>`)

Two behaviors added:

1. **Default ordering:** `ORDER BY is_mine DESC, <existing order>`. Mine items always float to the top. This propagates automatically to the rig-builder dropdowns, which consume the same list endpoints.

2. **Optional filter:** `?mine=true` returns only rows with `is_mine = 1`. Used by the "My Equipment" sidebar sub-pages. `?mine=false` or omission returns everything.

`?include_retired=true` continues to behave as today and composes with `?mine=true`.

### Create/Update endpoint changes

`<Type>Create` Pydantic models for each of the 10 types (e.g. `CameraCreate`, `TelescopeCreate`) gain `is_mine: bool = False`. `<Type>Update` models gain `is_mine: Optional[bool] = None`. No validation beyond type — pure user preference.

### New endpoint: toggle mine

```
POST /api/equipment/<type>/<id>/mine
Body: {"is_mine": true | false}
Response: the updated row (full Response model)
```

One-shot, idempotent. Used by:
- The clickable star-icon column in `EquipmentList`.
- Future callers that need to toggle without re-sending a full update payload.

Rationale over reusing `PUT`: star-click in a list should not require the frontend to know the full object shape, and `PUT` is already the full-replace pattern (carries payload-risk if something else is modified in the meantime).

Applies to all 10 equipment types. Returns 404 if the id is unknown within that type.

### New endpoint: mine counts

```
GET /api/equipment/mine-counts
Response: {
  "cameras": 3,
  "telescopes": 1,
  "filters": 2,
  "mounts": 1,
  "focusers": 0,
  "filter_wheels": 1,
  "oags": 0,
  "guide_scopes": 0,
  "computers": 2,
  "software": 4
}
```

Consumed by the sidebar to decide which "My Equipment" sub-items to render. One round trip instead of 10 per-type list calls. Invalidated (via TanStack Query `invalidateQueries`) on any mine-toggle or equipment delete.

Sum of all counts is used to decide whether to show the empty-state message when zero items are owned across the board.

---

## Frontend — Sidebar

`components/equipment/EquipmentSidebar.tsx` adds a new group, rendered **first** (above "Imaging"):

```
MY EQUIPMENT
├─ Cameras           (only rendered if mine-count > 0)
├─ OTAs              (only rendered if mine-count > 0)
├─ Filters           (only rendered if mine-count > 0)
├─ Mounts            (only rendered if mine-count > 0)
├─ Focusers          (only rendered if mine-count > 0)
├─ Filter Wheels     (only rendered if mine-count > 0)
├─ OAGs              (only rendered if mine-count > 0)
├─ Guide Scopes      (only rendered if mine-count > 0)
├─ Computers         (only rendered if mine-count > 0)
└─ Software          (only rendered if mine-count > 0)

IMAGING
├─ Cameras
├─ Sensors
...(existing groups unchanged)
```

- **Labels:** sub-items are plain type names ("Cameras", "OTAs", etc.) — the group header provides the "My" context.
- **Slugs:** internal category slugs are distinct from the regular sidebar slugs so `selectedCategory` can route to the right variant: `my-cameras`, `my-telescopes`, `my-filters`, `my-mounts`, `my-focusers`, `my-filter-wheels`, `my-oags`, `my-guide-scopes`, `my-computers`, `my-software`.
- **Visibility:** each sub-item renders only when its count is > 0, driven by the `mine-counts` response. The sub-item list reactively grows/shrinks as you star and unstar.
- **Zero items owned across all types:** group header still shows, followed by one muted italic line: *"Click the star on any equipment row to add it here."* No sub-items.

**Edge case.** If you're currently viewing "My Cameras" and unstar the last camera, the sub-item disappears from the sidebar on next `mine-counts` refetch, but the page itself stays valid and shows the standard empty-state message for the filtered DataGrid until you navigate away.

**`EquipmentPage.tsx`** maps the two slug variants (`cameras` and `my-cameras`, etc.) to the same per-type list component but with a `mineOnly={true}` prop passed in the "my-" case.

---

## Frontend — Equipment lists

`components/equipment/EquipmentList.tsx` changes:

### New "Mine" column (leftmost)

- Clickable star icon: `StarIcon` (filled) when `is_mine = 1`, `StarOutlineIcon` when `is_mine = 0`.
- Color: MUI primary blue (`theme.palette.primary.main`) — matches the established colorblind-safe palette (blue as the positive-signal color). No yellow.
- Width: ~50px. No sortable header. Header shows the star icon with a tooltip "Mine".
- Click handler:
  1. Optimistically flip the row's `is_mine` in the query cache.
  2. `POST /api/equipment/<type>/<id>/mine` with the new value.
  3. On success: invalidate the list query and the `mine-counts` query.
  4. On error: roll back the optimistic update and show a Snackbar.
- Present in **both** standard and `mineOnly` views. In the `mineOnly` view, clicking the filled star optimistically removes the row from the filtered list (its `is_mine` becomes 0).

### `mineOnly` prop

- Passed by `EquipmentPage.tsx` when the selected category slug starts with `my-`.
- Appends `?mine=true` to the list query key and URL.
- Empty-state text (when the grid has no rows): *"No equipment marked as yours yet. Open any item and check 'Mark as mine', or click the star in a list."*

### Form dialogs

Each of the 10 per-type form dialogs (`CameraFormDialog`, `TelescopeFormDialog`, `FilterFormDialog`, `MountFormDialog`, `FocuserFormDialog`, `FilterWheelFormDialog`, `OagFormDialog`, `GuideScopeFormDialog`, `ComputerFormDialog`, `SoftwareFormDialog`) adds a "Mark as mine" checkbox.

- Placement: a shared row near the top of the form (above the manufacturer picker) so it's visible regardless of how long the form is.
- Implementation: a small shared `MineCheckbox` component in `components/equipment/shared/` that takes `{ value, onChange }` and renders `<FormControlLabel control={<Checkbox />} label="Mark as mine" />` with a star icon before the label for visual consistency with the list column.
- Bound to form state; saves via the existing PUT/POST update/create flow (the dedicated mine-toggle endpoint is only used by the list star-click).

---

## Frontend — Rig-builder dropdowns

The rig builder uses MUI Autocomplete with `groupBy="manufacturer_name"` today. Changes to achieve "my equipment first, flat, starred; then manufacturer-grouped 'all' with stars":

1. **Pre-process options** in the dropdown component: for each option with `is_mine = true`, emit it **twice** — once with a virtual group tag `"My Equipment"` and once with its real `manufacturer_name`. Both copies carry `is_mine = true` for star rendering.
2. **Custom `groupBy`** returns the option's virtual group tag when present, otherwise its manufacturer name.
3. **Sort** the options array so all `"My Equipment"`-tagged entries precede manufacturer entries (natural, since the API already returns `is_mine DESC` first).
4. **`renderOption`** shows a filled blue star (same `StarIcon`, `theme.palette.primary.main`) before the label when `is_mine = true`. Also renders in the "My Equipment" virtual group header.
5. **Selection value** is the original option's id — the duplication is purely a display concern; the Autocomplete's `isOptionEqualToValue` compares on id, and a duplicated "mine" option selects the same underlying row.

This applies to every equipment dropdown in the rig form: Camera, OTA, Mount, Focuser, Filter Wheel, OAG, Guide Scope, Software (multi-select). Filter slot pickers too. No change to telescope-configuration pickers (configurations are not top-level ownable entities).

---

## Data flow

```
star click in list
  ├─ optimistic cache update (TanStack Query)
  ├─ POST /api/equipment/<type>/<id>/mine
  ├─ invalidate: list query for that type
  ├─ invalidate: mine-counts
  └─ (rig dropdowns re-render on next mount; no cross-invalidation needed)

equipment create/update with is_mine changed
  ├─ existing PUT/POST flow
  └─ invalidate: mine-counts

sidebar render
  └─ GET /api/equipment/mine-counts → decide sub-items to render

"My <Type>" page render
  └─ GET /api/equipment/<type>?mine=true → filtered list with stars all filled

Rig form dropdown render
  └─ GET /api/equipment/<type>?include_retired=false (existing call)
       → frontend duplicates is_mine=true rows into a "My Equipment" virtual group
       → renders flat mine block + manufacturer groups with stars
```

---

## Testing

### Backend

- **Toggle endpoint** (`tests/api/test_equipment_mine.py`):
  - Toggle a camera from 0→1, assert row updated and response includes `is_mine=true`.
  - Toggle idempotently (0→1 twice), assert no error, assert final state stable.
  - Toggle an unknown id, assert 404.
  - Parameterize across all 10 equipment types (at minimum: one happy-path test per type).
- **List ordering:** for at least 3 types (camera, telescope, filter), insert a mix of `is_mine=0` and `is_mine=1` rows, assert that the default list response orders `is_mine=1` first.
- **`?mine=true` filter:** assert only `is_mine=1` rows are returned; assert it composes with `?include_retired=true`.
- **mine-counts endpoint:** with a known seeded state (N cameras with 2 marked, etc.), assert the returned counts match. Assert zero counts for types with no ownership.
- **Response-model test:** assert `is_mine` is present on every equipment response shape (parameterized over the 10 types).
- **Seed-loader regression test:** seed from CSV, toggle an item to `is_mine=1`, re-run the seed loader, assert the item's `is_mine` is still 1 and the row is not re-written. This pins the interaction with the hash contract.

### Frontend

- `npm run build` passes (existing bar).
- No new component-level tests required — project convention.

Manual smoke test on Fred's local after implementation:

1. Star an item in the Cameras list → sidebar "My Equipment > Cameras" appears.
2. Click "My Equipment > Cameras" → only the starred camera shows.
3. Unstar it in the `mineOnly` view → row disappears, sidebar sub-item disappears after refetch.
4. Star two cameras and two OTAs; open the Rig form → Camera dropdown shows a "My Equipment" section with the 2 items at the top, followed by manufacturer groups; both starred cameras also appear with stars inside their manufacturer groups.
5. Open a filter's edit dialog, toggle "Mark as mine", save → list refreshes, star reflects new state.
6. Recreate DB, run seed loader, star an item, re-run seed loader → star persists.

---

## Non-goals recap

- No ownership quantities, purchase metadata, or serial numbers.
- No multi-user / sharing.
- No change to rig validity or FK semantics.
- No change to seed CSVs.
- No "Show mine only" toggle on standard lists — sidebar provides that.
- No impact on sensors, telescope_configurations, junction tables, child tables, or lookup tables.
