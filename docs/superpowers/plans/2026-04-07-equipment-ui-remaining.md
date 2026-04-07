# Equipment Management UI — Remaining Tabs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the frontend Equipment page with all remaining equipment tabs, reusing patterns from v0.9.0.

**Architecture:** Extract generic `EquipmentList<T>` to eliminate copy-paste scaffolding. Refactor existing 3 lists to use it. Build 9 new list+form components for remaining types. Lookup tables get a shared accordion UI.

**Tech Stack:** React/TypeScript, MUI (DataGrid, Dialog, Accordion), TanStack Query, existing `@/api/equipment` client

---

## File Structure

### Create
- `frontend/src/components/equipment/EquipmentList.tsx` — generic list component
- `frontend/src/components/equipment/SensorFormDialog.tsx`
- `frontend/src/components/equipment/MountFormDialog.tsx`
- `frontend/src/components/equipment/FocuserFormDialog.tsx`
- `frontend/src/components/equipment/FilterWheelFormDialog.tsx`
- `frontend/src/components/equipment/OagFormDialog.tsx`
- `frontend/src/components/equipment/GuideScopeFormDialog.tsx`
- `frontend/src/components/equipment/ComputerFormDialog.tsx`
- `frontend/src/components/equipment/SoftwareFormDialog.tsx`
- `frontend/src/components/equipment/ManufacturerFormDialog.tsx`
- `frontend/src/components/equipment/LookupTablesPanel.tsx` — accordion UI for all lookup tables

### Modify
- `frontend/src/components/equipment/CameraList.tsx` — refactor to use EquipmentList
- `frontend/src/components/equipment/TelescopeList.tsx` — refactor to use EquipmentList
- `frontend/src/components/equipment/FilterList.tsx` — refactor to use EquipmentList
- `frontend/src/pages/EquipmentPage.tsx` — wire up all new tabs

---

### Task 1: Extract Generic EquipmentList Component

**Files:**
- Create: `frontend/src/components/equipment/EquipmentList.tsx`

- [ ] **Step 1: Create the generic component**

```tsx
import { useState } from "react";
import { DataGrid, type GridColDef } from "@mui/x-data-grid";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import ConfirmDeleteDialog from "@/components/equipment/shared/ConfirmDeleteDialog";

interface EquipmentListProps<T extends { id: number }> {
  title: string;
  queryKey: string;
  fetchFn: (includeRetired?: boolean) => Promise<T[]>;
  deleteFn: (id: number) => Promise<unknown>;
  columns: GridColDef<T>[];
  getItemName: (item: T) => string;
  FormDialog: React.ComponentType<{
    open: boolean;
    item: T | null;
    onClose: () => void;
    onSaved: () => void;
  }>;
}

export default function EquipmentList<T extends { id: number }>({
  title,
  queryKey,
  fetchFn,
  deleteFn,
  columns,
  getItemName,
  FormDialog,
}: EquipmentListProps<T>) {
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [editItem, setEditItem] = useState<T | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<T | null>(null);

  const { data: items = [], isLoading } = useQuery({
    queryKey: [queryKey],
    queryFn: () => fetchFn(),
  });

  const handleAdd = () => {
    setEditItem(null);
    setFormOpen(true);
  };

  const handleEdit = (item: T) => {
    setEditItem(item);
    setFormOpen(true);
  };

  const handleFormClose = () => {
    setFormOpen(false);
    setEditItem(null);
  };

  const handleSaved = () => {
    void queryClient.invalidateQueries({ queryKey: [queryKey] });
  };

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    await deleteFn(deleteTarget.id);
    void queryClient.invalidateQueries({ queryKey: [queryKey] });
    setDeleteTarget(null);
  };

  // Inject edit/delete handlers into the actions column
  const allColumns: GridColDef<T>[] = [
    ...columns,
    {
      field: "actions",
      headerName: "Actions",
      width: 100,
      sortable: false,
      filterable: false,
      renderCell: (params) => (
        <Box>
          <IconButton
            size="small"
            onClick={() => handleEdit(params.row)}
            aria-label={`Edit ${getItemName(params.row)}`}
          >
            <EditIcon fontSize="small" />
          </IconButton>
          <IconButton
            size="small"
            onClick={() => setDeleteTarget(params.row)}
            aria-label={`Retire ${getItemName(params.row)}`}
          >
            <DeleteIcon fontSize="small" />
          </IconButton>
        </Box>
      ),
    },
  ];

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <Box sx={{ display: "flex", alignItems: "center", mb: 2 }}>
        <Typography variant="h6" sx={{ flex: 1 }}>
          {title}
        </Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={handleAdd}>
          Add {title.replace(/s$/, "")}
        </Button>
      </Box>

      <DataGrid
        rows={items}
        columns={allColumns}
        loading={isLoading}
        autoHeight
        disableRowSelectionOnClick
        pageSizeOptions={[25, 50, 100]}
        initialState={{ pagination: { paginationModel: { pageSize: 25 } } }}
      />

      <FormDialog
        open={formOpen}
        item={editItem}
        onClose={handleFormClose}
        onSaved={handleSaved}
      />

      <ConfirmDeleteDialog
        open={deleteTarget !== null}
        itemName={deleteTarget ? getItemName(deleteTarget) : ""}
        onConfirm={handleDeleteConfirm}
        onCancel={() => setDeleteTarget(null)}
      />
    </Box>
  );
}
```

Note: Add `IconButton`, `EditIcon`, `DeleteIcon` imports. The "Add {title}" button strips trailing 's' for singular form (e.g., "Add Camera" from "Cameras"). If a title doesn't follow this pattern (e.g., "Software"), handle it — could add an optional `addLabel` prop.

- [ ] **Step 2: Verify build**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npm run build`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/equipment/EquipmentList.tsx
git commit -m "feat: generic EquipmentList component for equipment tabs"
```

---

### Task 2: Refactor Existing Lists to Use EquipmentList

**Files:**
- Modify: `frontend/src/components/equipment/CameraList.tsx`
- Modify: `frontend/src/components/equipment/TelescopeList.tsx`
- Modify: `frontend/src/components/equipment/FilterList.tsx`

- [ ] **Step 1: Refactor CameraList**

Replace the entire CameraList with a thin wrapper that passes columns + config to EquipmentList:

```tsx
import { type GridColDef } from "@mui/x-data-grid";
import EquipmentList from "./EquipmentList";
import CameraFormDialog from "./CameraFormDialog";
import { fetchCameras, deleteCamera, type Camera } from "@/api/equipment";

// Adapt CameraFormDialog props to the generic interface
function CameraForm({ open, item, onClose, onSaved }: {
  open: boolean; item: Camera | null; onClose: () => void; onSaved: () => void;
}) {
  return <CameraFormDialog open={open} camera={item} onClose={onClose} onSaved={onSaved} />;
}

const columns: GridColDef<Camera>[] = [
  { field: "model_name", headerName: "Model", flex: 1.5, minWidth: 160 },
  { field: "manufacturer", headerName: "Manufacturer", flex: 1, minWidth: 130,
    valueGetter: (_v, row) => row.manufacturer.name },
  { field: "sensor", headerName: "Sensor", flex: 2, minWidth: 200,
    valueGetter: (_v, row) => `${row.sensor.model_name} (${row.sensor.sensor_type})` },
  { field: "cooled", headerName: "Cooled", width: 90,
    valueGetter: (_v, row) => row.cooled ? "Yes" : "No" },
  { field: "connector_size", headerName: "Connector", width: 120,
    valueGetter: (_v, row) => row.connector_size?.name ?? "—" },
];

export default function CameraList() {
  return (
    <EquipmentList<Camera>
      title="Cameras"
      queryKey="cameras"
      fetchFn={fetchCameras}
      deleteFn={deleteCamera}
      columns={columns}
      getItemName={(c) => c.model_name}
      FormDialog={CameraForm}
    />
  );
}
```

Note: The existing CameraFormDialog takes `camera` as the prop name for the item, but EquipmentList passes `item`. The thin `CameraForm` wrapper adapts this. Same pattern for TelescopeList (prop name `telescope`) and FilterList (prop name `filter`).

- [ ] **Step 2: Refactor TelescopeList**

Same pattern. Columns: Model, Manufacturer, Design, Aperture, Configs count. Wrapper maps `item` → `telescope`.

- [ ] **Step 3: Refactor FilterList**

Same pattern. Columns: Model, Manufacturer, Type (formatted), Passbands (summarized), Size. Keep the `formatFilterType` and `summarizePassbands` helpers. Wrapper maps `item` → `filter`.

- [ ] **Step 4: Verify build**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npm run build`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/equipment/CameraList.tsx frontend/src/components/equipment/TelescopeList.tsx frontend/src/components/equipment/FilterList.tsx
git commit -m "refactor: CameraList, TelescopeList, FilterList use generic EquipmentList"
```

---

### Task 3: Sensor Tab

**Files:**
- Create: `frontend/src/components/equipment/SensorFormDialog.tsx`
- Modify: `frontend/src/pages/EquipmentPage.tsx`

- [ ] **Step 1: Create SensorFormDialog**

MUI Dialog (`maxWidth="md"`, `fullWidth`). Props: `open`, `item: Sensor | null` (generic interface), `onClose`, `onSaved`.

Fields:
- Model name (TextField, required)
- ManufacturerPicker (required)
- Sensor type: Select with options "mono" and "color" (required)
- Pixel size µm (TextField, number, required)
- Resolution X (TextField, number, required)
- Resolution Y (TextField, number, required)
- Sensor width mm (TextField, number)
- Sensor height mm (TextField, number)
- ADC bit depth (TextField, number)
- Full well capacity ke (TextField, number)
- Read noise e (TextField, number)
- Peak QE % (TextField, number)
- Bayer pattern: Select with options "RGGB", "BGGR", "GRBG", "GBRG" (shown only when sensor_type="color")
- Dual gain (Switch)
- HCG threshold gain (TextField, number, shown only when dual_gain=true)
- Notes (TextField, multiline)

On save: calls `createSensor` or `updateSensor`. Use `parseOptionalFloat`/`parseOptionalInt` from `@/lib/formUtils`.

- [ ] **Step 2: Add sensor tab to EquipmentPage**

Add a `SensorList` using `EquipmentList<Sensor>` inline or as a small component, plus the SensorFormDialog. Wire into the switch:

```tsx
case "sensors":
  return (
    <EquipmentList<Sensor>
      title="Sensors"
      queryKey="sensors"
      fetchFn={fetchSensors}
      deleteFn={deleteSensor}
      columns={sensorColumns}
      getItemName={(s) => s.model_name}
      FormDialog={SensorForm}
    />
  );
```

Columns: Model, Manufacturer, Type (mono/color), Pixel Size, Resolution (X×Y).

Note: Since each tab is now just columns + form dialog, the list component can be defined inline in EquipmentPage or as a thin file. Prefer inline in EquipmentPage for simplicity when the columns are straightforward, or a separate file if the columns need helper functions.

Actually — for consistency and to keep EquipmentPage small, create each list as a thin file like the refactored CameraList. Create `frontend/src/components/equipment/SensorList.tsx`.

- [ ] **Step 3: Verify build**

Run: `npm run build`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/equipment/SensorFormDialog.tsx frontend/src/components/equipment/SensorList.tsx frontend/src/pages/EquipmentPage.tsx
git commit -m "feat: Sensor list + form dialog"
```

---

### Task 4: Mount Tab

**Files:**
- Create: `frontend/src/components/equipment/MountFormDialog.tsx`
- Create: `frontend/src/components/equipment/MountList.tsx`
- Modify: `frontend/src/pages/EquipmentPage.tsx`

- [ ] **Step 1: Create MountFormDialog**

Fields:
- Model name (TextField, required)
- ManufacturerPicker (required)
- LookupPicker for mount_type (fetchMountTypes, queryKey="mount-types", label="Mount Type")
- Payload capacity kg (TextField, number)
- Mount weight kg (TextField, number)
- Counterweight required (Switch, default true)
- GoTo capable (Switch, default true)
- Periodic error arcsec (TextField, number)
- Drive type (TextField)
- InterfaceMultiSelect for connection interfaces
- Notes (TextField, multiline)

On save: calls `createMount` or `updateMount`.

- [ ] **Step 2: Create MountList + wire up in EquipmentPage**

Columns: Model, Manufacturer, Type, Payload (kg), GoTo (Yes/No).

Add `case "mounts"` to EquipmentPage switch.

- [ ] **Step 3: Verify build + commit**

```bash
git add frontend/src/components/equipment/MountFormDialog.tsx frontend/src/components/equipment/MountList.tsx frontend/src/pages/EquipmentPage.tsx
git commit -m "feat: Mount list + form dialog"
```

---

### Task 5: Focuser Tab

**Files:**
- Create: `frontend/src/components/equipment/FocuserFormDialog.tsx`
- Create: `frontend/src/components/equipment/FocuserList.tsx`
- Modify: `frontend/src/pages/EquipmentPage.tsx`

- [ ] **Step 1: Create FocuserFormDialog**

Fields:
- Model name (TextField, required)
- ManufacturerPicker (required)
- Motorized (Switch, default true)
- Travel range mm (TextField, number)
- Step size µm (TextField, number)
- Total steps (TextField, number)
- Temperature compensation (Switch, default false)
- Backlash steps (TextField, number)
- InterfaceMultiSelect
- Notes (TextField, multiline)

- [ ] **Step 2: Create FocuserList + wire up**

Columns: Model, Manufacturer, Motorized (Yes/No), Travel (mm), Steps.

- [ ] **Step 3: Verify build + commit**

```bash
git commit -m "feat: Focuser list + form dialog"
```

---

### Task 6: Filter Wheel Tab

**Files:**
- Create: `frontend/src/components/equipment/FilterWheelFormDialog.tsx`
- Create: `frontend/src/components/equipment/FilterWheelList.tsx`
- Modify: `frontend/src/pages/EquipmentPage.tsx`

- [ ] **Step 1: Create FilterWheelFormDialog**

Fields:
- Model name (TextField, required)
- ManufacturerPicker (required)
- LookupPicker for filter_size (fetchFilterSizes, label="Filter Size")
- LookupPicker for camera_side_connector (fetchConnectorSizes, label="Camera Side Connector")
- LookupPicker for telescope_side_connector (fetchConnectorSizes, label="Telescope Side Connector")
- Num positions (TextField, number, required)
- Back focus contribution mm (TextField, number)
- InterfaceMultiSelect
- Notes (TextField, multiline)

Note: Two separate LookupPicker instances for connector sizes — one for camera side, one for telescope side. Both use the same `fetchConnectorSizes` and `queryKey="connector-sizes"` but different `value`/`onChange` bindings.

- [ ] **Step 2: Create FilterWheelList + wire up**

Columns: Model, Manufacturer, Filter Size, Positions, Camera Connector, Telescope Connector.

Category slug is `"filter-wheels"` (matches the sidebar).

- [ ] **Step 3: Verify build + commit**

```bash
git commit -m "feat: Filter wheel list + form dialog"
```

---

### Task 7: OAG + Guide Scope Tabs

**Files:**
- Create: `frontend/src/components/equipment/OagFormDialog.tsx`
- Create: `frontend/src/components/equipment/OagList.tsx`
- Create: `frontend/src/components/equipment/GuideScopeFormDialog.tsx`
- Create: `frontend/src/components/equipment/GuideScopeList.tsx`
- Modify: `frontend/src/pages/EquipmentPage.tsx`

- [ ] **Step 1: Create OagFormDialog**

Fields:
- Model name (TextField, required)
- ManufacturerPicker (required)
- LookupPicker for imaging_side_connector (fetchConnectorSizes, label="Imaging Side Connector")
- LookupPicker for guide_camera_connector (fetchConnectorSizes, label="Guide Camera Connector")
- Prism size mm (TextField, number)
- Back focus contribution mm (TextField, number)
- Weight g (TextField, number)
- Notes (TextField, multiline)

No InterfaceMultiSelect (OAG has no junction table).

- [ ] **Step 2: Create OagList**

Columns: Model, Manufacturer, Imaging Connector, Guide Connector, Prism (mm).

- [ ] **Step 3: Create GuideScopeFormDialog**

Fields:
- Model name (TextField, required)
- ManufacturerPicker (required)
- LookupPicker for guide_camera_connector (fetchConnectorSizes, label="Guide Camera Connector")
- Aperture mm (TextField, number)
- Focal length mm (TextField, number)
- Weight g (TextField, number)
- Notes (TextField, multiline)

- [ ] **Step 4: Create GuideScopeList**

Columns: Model, Manufacturer, Aperture (mm), Focal Length (mm), Connector.

- [ ] **Step 5: Wire up both in EquipmentPage**

```tsx
case "oags": return <OagList />;
case "guide-scopes": return <GuideScopeList />;
```

- [ ] **Step 6: Verify build + commit**

```bash
git commit -m "feat: OAG + Guide Scope lists + form dialogs"
```

---

### Task 8: Computer + Software Tabs

**Files:**
- Create: `frontend/src/components/equipment/ComputerFormDialog.tsx`
- Create: `frontend/src/components/equipment/ComputerList.tsx`
- Create: `frontend/src/components/equipment/SoftwareFormDialog.tsx`
- Create: `frontend/src/components/equipment/SoftwareList.tsx`
- Modify: `frontend/src/pages/EquipmentPage.tsx`

- [ ] **Step 1: Create ComputerFormDialog**

Fields:
- Model name (TextField, required)
- ManufacturerPicker (required)
- LookupPicker for computer_type (fetchComputerTypes, queryKey="computer-types", label="Computer Type")
- Notes (TextField, multiline)

- [ ] **Step 2: Create ComputerList**

Columns: Model, Manufacturer, Type.

- [ ] **Step 3: Create SoftwareFormDialog**

Fields:
- Name (TextField, required) — note: Software uses `name` not `model_name`
- ManufacturerPicker (required — DB requires NOT NULL despite Pydantic model allowing null)
- Category: Select with options: 'capture', 'guiding', 'processing', 'planetarium', 'plate_solving', 'utility', 'other'. Format for display using `formatFilterType` from `@/lib/formUtils` (same snake_case → Title Case logic works).
- Website (TextField)
- Notes (TextField, multiline)

Note: Software's `getItemName` should use `s.name` not `s.model_name`.

- [ ] **Step 4: Create SoftwareList**

Columns: Name, Manufacturer, Category (formatted), Website.

- [ ] **Step 5: Wire up in EquipmentPage**

```tsx
case "computers": return <ComputerList />;
case "software": return <SoftwareList />;
```

- [ ] **Step 6: Verify build + commit**

```bash
git commit -m "feat: Computer + Software lists + form dialogs"
```

---

### Task 9: Manufacturer Tab

**Files:**
- Create: `frontend/src/components/equipment/ManufacturerFormDialog.tsx`
- Create: `frontend/src/components/equipment/ManufacturerList.tsx`
- Modify: `frontend/src/pages/EquipmentPage.tsx`

- [ ] **Step 1: Create ManufacturerFormDialog**

Simplest form — only 3 fields:
- Name (TextField, required)
- Website (TextField)
- Notes (TextField, multiline)

On save: calls `createManufacturer` or `updateManufacturer`. Note: Manufacturer uses `name` not `model_name`.

- [ ] **Step 2: Create ManufacturerList**

Columns: Name, Website, Notes (truncated).

`getItemName` uses `m.name`.

- [ ] **Step 3: Wire up in EquipmentPage**

```tsx
case "manufacturers": return <ManufacturerList />;
```

- [ ] **Step 4: Verify build + commit**

```bash
git commit -m "feat: Manufacturer list + form dialog"
```

---

### Task 10: Lookup Tables Panel

**Files:**
- Create: `frontend/src/components/equipment/LookupTablesPanel.tsx`
- Modify: `frontend/src/pages/EquipmentPage.tsx`

- [ ] **Step 1: Create LookupTablesPanel**

MUI Accordion stack with one section per lookup table: Optical Designs, Mount Types, Connection Interfaces, Connector Sizes, Filter Sizes, Computer Types. Each section is an expandable accordion showing a simple DataGrid.

Each section uses a mini DataGrid with the table's columns and Add/Edit/Delete inline. Since these are simple name+description tables, use a lightweight inline editing pattern or a small form dialog.

Recommended approach: each accordion section renders a mini `EquipmentList` (but without the title/header since the accordion header already labels it). Or simpler: create a `LookupSection` sub-component that takes the fetch/create/update/delete functions and columns, and renders a compact list with Add button and inline edit.

Actually, the simplest approach: a single `LookupSection<T>` component that renders a compact DataGrid with Add/Edit/Delete. Each lookup type gets an accordion wrapping a `LookupSection`.

```tsx
interface LookupSectionProps<T extends { id: number; name: string }> {
  queryKey: string;
  fetchFn: (includeRetired?: boolean) => Promise<T[]>;
  createFn: (data: Record<string, unknown>) => Promise<T>;
  updateFn: (id: number, data: Record<string, unknown>) => Promise<T>;
  deleteFn: (id: number) => Promise<unknown>;
  columns: GridColDef<T>[];  // Extra columns beyond "name" (e.g., "description", "diameter_mm", "category")
}
```

For each lookup table:
- **Optical Design**: columns [Name, Description]
- **Mount Type**: columns [Name, Description]
- **Connection Interface**: columns [Name, Category, Notes]
- **Connector Size**: columns [Name, Diameter (mm), Notes]
- **Filter Size**: columns [Name, Description]
- **Computer Type**: columns [Name, Description]

Use a small MUI Dialog for add/edit (not inline DataGrid editing — that's MUI X Pro). The dialog can be generic since all lookup tables have name + 1-2 optional fields.

- [ ] **Step 2: Wire up in EquipmentPage**

The sidebar category for this is not a single slug — it could be a group. Check the EquipmentSidebar to see what slugs are used for lookup tables. If the sidebar has individual leaf items for each lookup type, handle each separately. If it has a single "Lookup Tables" item, render the accordion panel.

Looking at the sidebar groups from Task 8: the "Reference" group has "manufacturers" as a leaf. The lookup tables (optical_design, mount_type, etc.) don't have individual sidebar entries — they should be under a "Lookup Tables" leaf item or similar.

Add a "lookup-tables" leaf item to the Reference group in EquipmentSidebar, and wire it up:

```tsx
case "lookup-tables": return <LookupTablesPanel />;
```

Also update EquipmentSidebar to add a "Lookup Tables" item in the Reference group.

- [ ] **Step 3: Verify build + commit**

```bash
git commit -m "feat: Lookup tables accordion panel with inline CRUD"
```

---

### Task 11: Final Checks + Cleanup

**Files:** None (verification only)

- [ ] **Step 1: Remove EquipmentPlaceholder usage**

Check if any category still falls through to the placeholder. If all categories are now handled, the `default` case in the switch can remain as a fallback but should never trigger for known categories.

- [ ] **Step 2: Run full backend test suite**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest -v`

Expected: All tests pass (existing tests should not be affected — this is frontend-only work)

- [ ] **Step 3: Lint and format**

Run: `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/`

- [ ] **Step 4: Security scan**

Run: `uv run bandit -r src/`

- [ ] **Step 5: Frontend build**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npm run build`

- [ ] **Step 6: Verify all equipment categories load**

Start dev server with `make dev`, navigate to `/equipment`, verify:
- All sidebar categories render their respective lists (no more "Coming soon" for any)
- Lookup Tables accordion expands and shows all 6 lookup types
