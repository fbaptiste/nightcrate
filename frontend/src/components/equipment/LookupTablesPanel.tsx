import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import FormHelperText from "@mui/material/FormHelperText";
import AddIcon from "@mui/icons-material/Add";
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/Delete";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { DataGrid, type GridColDef } from "@mui/x-data-grid";
import ConfirmDeleteDialog from "@/components/equipment/shared/ConfirmDeleteDialog";
import {
  fetchOpticalDesigns,
  createOpticalDesign,
  updateOpticalDesign,
  deleteOpticalDesign,
  fetchMountTypes,
  createMountType,
  updateMountType,
  deleteMountType,
  fetchConnectionInterfaces,
  createConnectionInterface,
  updateConnectionInterface,
  deleteConnectionInterface,
  fetchConnectorSizes,
  createConnectorSize,
  updateConnectorSize,
  deleteConnectorSize,
  fetchFilterSizes,
  createFilterSize,
  updateFilterSize,
  deleteFilterSize,
  fetchComputerTypes,
  createComputerType,
  updateComputerType,
  deleteComputerType,
  type OpticalDesign,
  type MountType,
  type ConnectionInterface,
  type ConnectorSize,
  type FilterSize,
  type ComputerType,
} from "@/api/equipment";

// ---------------------------------------------------------------------------
// Field config
// ---------------------------------------------------------------------------

interface FieldConfig {
  key: string;
  label: string;
  required?: boolean;
  type?: "text" | "number" | "select";
  options?: { value: string; label: string }[];
}

// ---------------------------------------------------------------------------
// Generic form dialog
// ---------------------------------------------------------------------------

interface LookupFormDialogProps {
  open: boolean;
  title: string;
  fields: FieldConfig[];
  initialValues: Record<string, unknown>;
  onClose: () => void;
  onSubmit: (values: Record<string, unknown>) => Promise<void>;
}

function LookupFormDialog({
  open,
  title,
  fields,
  initialValues,
  onClose,
  onSubmit,
}: LookupFormDialogProps) {
  const [values, setValues] = useState<Record<string, unknown>>(initialValues);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  // Reset form when dialog opens with new initialValues
  const handleEnter = () => {
    setValues(initialValues);
    setErrors({});
  };

  const handleChange = (key: string, value: unknown) => {
    setValues((prev) => ({ ...prev, [key]: value }));
    if (errors[key]) {
      setErrors((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
    }
  };

  const validate = () => {
    const next: Record<string, string> = {};
    for (const field of fields) {
      if (field.required) {
        const val = values[field.key];
        if (val === undefined || val === null || String(val).trim() === "") {
          next[field.key] = `${field.label} is required`;
        }
      }
    }
    return next;
  };

  const handleSubmit = async () => {
    const errs = validate();
    if (Object.keys(errs).length > 0) {
      setErrors(errs);
      return;
    }
    setSaving(true);
    try {
      await onSubmit(values);
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} onTransitionEnter={handleEnter} maxWidth="xs" fullWidth>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, pt: "16px !important" }}>
        {fields.map((field) => {
          if (field.type === "select" && field.options) {
            return (
              <FormControl key={field.key} size="small" error={Boolean(errors[field.key])} required={field.required}>
                <InputLabel>{field.label}</InputLabel>
                <Select
                  label={field.label}
                  value={String(values[field.key] ?? "")}
                  onChange={(e) => handleChange(field.key, e.target.value)}
                >
                  {field.options.map((opt) => (
                    <MenuItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </MenuItem>
                  ))}
                </Select>
                {errors[field.key] && <FormHelperText>{errors[field.key]}</FormHelperText>}
              </FormControl>
            );
          }
          return (
            <TextField
              key={field.key}
              label={field.label}
              required={field.required}
              type={field.type === "number" ? "number" : "text"}
              size="small"
              value={values[field.key] ?? ""}
              onChange={(e) =>
                handleChange(
                  field.key,
                  field.type === "number" && e.target.value !== ""
                    ? Number(e.target.value)
                    : e.target.value === ""
                      ? null
                      : e.target.value,
                )
              }
              error={Boolean(errors[field.key])}
              helperText={errors[field.key]}
            />
          );
        })}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={saving}>
          Cancel
        </Button>
        <Button onClick={handleSubmit} variant="contained" disabled={saving}>
          Save
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Generic lookup section
// ---------------------------------------------------------------------------

interface LookupSectionProps<T extends { id: number; name: string }> {
  title: string;
  queryKey: string;
  fetchFn: (includeRetired?: boolean) => Promise<T[]>;
  createFn: (data: Record<string, unknown>) => Promise<T>;
  updateFn: (id: number, data: Record<string, unknown>) => Promise<T>;
  deleteFn: (id: number) => Promise<unknown>;
  columns: GridColDef<T>[];
  fields: FieldConfig[];
  defaultValues: Record<string, unknown>;
}

function LookupSection<T extends { id: number; name: string }>({
  title,
  queryKey,
  fetchFn,
  createFn,
  updateFn,
  deleteFn,
  columns,
  fields,
  defaultValues,
}: LookupSectionProps<T>) {
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

  const handleSubmit = async (values: Record<string, unknown>) => {
    if (editItem) {
      await updateFn(editItem.id, values);
    } else {
      await createFn(values);
    }
    void queryClient.invalidateQueries({ queryKey: [queryKey] });
  };

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    await deleteFn(deleteTarget.id);
    void queryClient.invalidateQueries({ queryKey: [queryKey] });
    setDeleteTarget(null);
  };

  const actionsColumn: GridColDef<T> = {
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
          aria-label={`Edit ${params.row.name}`}
        >
          <EditIcon fontSize="small" />
        </IconButton>
        <IconButton
          size="small"
          onClick={() => setDeleteTarget(params.row)}
          aria-label={`Retire ${params.row.name}`}
        >
          <DeleteIcon fontSize="small" />
        </IconButton>
      </Box>
    ),
  };

  const allColumns = [...columns, actionsColumn];

  // Build initial values for form: edit uses existing values, add uses defaults
  const initialValues: Record<string, unknown> = editItem
    ? fields.reduce(
        (acc, f) => {
          acc[f.key] = (editItem as Record<string, unknown>)[f.key] ?? defaultValues[f.key] ?? null;
          return acc;
        },
        {} as Record<string, unknown>,
      )
    : { ...defaultValues };

  const dialogTitle = editItem ? `Edit ${title.replace(/s$/, "")}` : `Add ${title.replace(/s$/, "")}`;

  return (
    <>
      <Box sx={{ display: "flex", justifyContent: "flex-end", mb: 1 }}>
        <Button variant="outlined" size="small" startIcon={<AddIcon />} onClick={handleAdd}>
          Add
        </Button>
      </Box>

      <DataGrid
        rows={items}
        columns={allColumns}
        loading={isLoading}
        autoHeight
        disableRowSelectionOnClick
        pageSizeOptions={[10, 25, 50]}
        initialState={{ pagination: { paginationModel: { pageSize: 10 } } }}
        sx={{ fontSize: "0.85rem" }}
      />

      <LookupFormDialog
        open={formOpen}
        title={dialogTitle}
        fields={fields}
        initialValues={initialValues}
        onClose={handleFormClose}
        onSubmit={handleSubmit}
      />

      <ConfirmDeleteDialog
        open={deleteTarget !== null}
        itemName={deleteTarget?.name ?? ""}
        onConfirm={handleDeleteConfirm}
        onCancel={() => setDeleteTarget(null)}
      />
    </>
  );
}

// ---------------------------------------------------------------------------
// Column definitions
// ---------------------------------------------------------------------------

const nameCol = <T extends { id: number; name: string }>(): GridColDef<T> => ({
  field: "name",
  headerName: "Name",
  flex: 1.5,
  minWidth: 140,
});

const descriptionCol = <T extends { id: number; description: string | null }>(): GridColDef<T> => ({
  field: "description",
  headerName: "Description",
  flex: 2,
  minWidth: 180,
  valueGetter: (_v, row) => row.description ?? "—",
});

const notesCol = <T extends { id: number; notes: string | null }>(): GridColDef<T> => ({
  field: "notes",
  headerName: "Notes",
  flex: 2,
  minWidth: 180,
  valueGetter: (_v, row) => row.notes ?? "—",
});

const opticalDesignColumns: GridColDef<OpticalDesign>[] = [nameCol(), descriptionCol()];

const mountTypeColumns: GridColDef<MountType>[] = [nameCol(), descriptionCol()];

const connectionInterfaceColumns: GridColDef<ConnectionInterface>[] = [
  nameCol(),
  {
    field: "category",
    headerName: "Category",
    width: 110,
  },
  notesCol(),
];

const connectorSizeColumns: GridColDef<ConnectorSize>[] = [
  nameCol(),
  {
    field: "diameter_mm",
    headerName: "Diameter (mm)",
    width: 130,
    valueGetter: (_v, row) => (row.diameter_mm != null ? row.diameter_mm : "—"),
  },
  notesCol(),
];

const filterSizeColumns: GridColDef<FilterSize>[] = [nameCol(), descriptionCol()];

const computerTypeColumns: GridColDef<ComputerType>[] = [nameCol(), descriptionCol()];

// ---------------------------------------------------------------------------
// Field configs
// ---------------------------------------------------------------------------

const CONNECTION_INTERFACE_CATEGORIES = [
  { value: "data", label: "Data" },
  { value: "control", label: "Control" },
  { value: "power", label: "Power" },
  { value: "wireless", label: "Wireless" },
];

const opticalDesignFields: FieldConfig[] = [
  { key: "name", label: "Name", required: true },
  { key: "description", label: "Description" },
];

const mountTypeFields: FieldConfig[] = [
  { key: "name", label: "Name", required: true },
  { key: "description", label: "Description" },
];

const connectionInterfaceFields: FieldConfig[] = [
  { key: "name", label: "Name", required: true },
  {
    key: "category",
    label: "Category",
    required: true,
    type: "select",
    options: CONNECTION_INTERFACE_CATEGORIES,
  },
  { key: "notes", label: "Notes" },
];

const connectorSizeFields: FieldConfig[] = [
  { key: "name", label: "Name", required: true },
  { key: "diameter_mm", label: "Diameter (mm)", type: "number" },
  { key: "notes", label: "Notes" },
];

const filterSizeFields: FieldConfig[] = [
  { key: "name", label: "Name", required: true },
  { key: "description", label: "Description" },
];

const computerTypeFields: FieldConfig[] = [
  { key: "name", label: "Name", required: true },
  { key: "description", label: "Description" },
];

// ---------------------------------------------------------------------------
// LookupTablesPanel
// ---------------------------------------------------------------------------

// Helper type for the generic create/update wrappers
type GenericItem = { id: number; name: string };
type CreateFn = (data: Record<string, unknown>) => Promise<GenericItem>;
type UpdateFn = (id: number, data: Record<string, unknown>) => Promise<GenericItem>;

const SECTIONS = [
  {
    id: "optical-designs",
    title: "Optical Designs",
    queryKey: "optical-designs",
    fetchFn: fetchOpticalDesigns as (includeRetired?: boolean) => Promise<GenericItem[]>,
    createFn: (createOpticalDesign as unknown) as CreateFn,
    updateFn: (updateOpticalDesign as unknown) as UpdateFn,
    deleteFn: deleteOpticalDesign,
    columns: opticalDesignColumns as GridColDef<GenericItem>[],
    fields: opticalDesignFields,
    defaultValues: { name: "", description: null },
  },
  {
    id: "mount-types",
    title: "Mount Types",
    queryKey: "mount-types",
    fetchFn: fetchMountTypes as (includeRetired?: boolean) => Promise<GenericItem[]>,
    createFn: (createMountType as unknown) as CreateFn,
    updateFn: (updateMountType as unknown) as UpdateFn,
    deleteFn: deleteMountType,
    columns: mountTypeColumns as GridColDef<GenericItem>[],
    fields: mountTypeFields,
    defaultValues: { name: "", description: null },
  },
  {
    id: "connection-interfaces",
    title: "Connection Interfaces",
    queryKey: "connection-interfaces",
    fetchFn: fetchConnectionInterfaces as (includeRetired?: boolean) => Promise<GenericItem[]>,
    createFn: (createConnectionInterface as unknown) as CreateFn,
    updateFn: (updateConnectionInterface as unknown) as UpdateFn,
    deleteFn: deleteConnectionInterface,
    columns: connectionInterfaceColumns as GridColDef<GenericItem>[],
    fields: connectionInterfaceFields,
    defaultValues: { name: "", category: "data", notes: null },
  },
  {
    id: "connector-sizes",
    title: "Connector Sizes",
    queryKey: "connector-sizes",
    fetchFn: fetchConnectorSizes as (includeRetired?: boolean) => Promise<GenericItem[]>,
    createFn: (createConnectorSize as unknown) as CreateFn,
    updateFn: (updateConnectorSize as unknown) as UpdateFn,
    deleteFn: deleteConnectorSize,
    columns: connectorSizeColumns as GridColDef<GenericItem>[],
    fields: connectorSizeFields,
    defaultValues: { name: "", diameter_mm: null, notes: null },
  },
  {
    id: "filter-sizes",
    title: "Filter Sizes",
    queryKey: "filter-sizes",
    fetchFn: fetchFilterSizes as (includeRetired?: boolean) => Promise<GenericItem[]>,
    createFn: (createFilterSize as unknown) as CreateFn,
    updateFn: (updateFilterSize as unknown) as UpdateFn,
    deleteFn: deleteFilterSize,
    columns: filterSizeColumns as GridColDef<GenericItem>[],
    fields: filterSizeFields,
    defaultValues: { name: "", description: null },
  },
  {
    id: "computer-types",
    title: "Computer Types",
    queryKey: "computer-types",
    fetchFn: fetchComputerTypes as (includeRetired?: boolean) => Promise<GenericItem[]>,
    createFn: (createComputerType as unknown) as CreateFn,
    updateFn: (updateComputerType as unknown) as UpdateFn,
    deleteFn: deleteComputerType,
    columns: computerTypeColumns as GridColDef<GenericItem>[],
    fields: computerTypeFields,
    defaultValues: { name: "", description: null },
  },
];

export default function LookupTablesPanel() {
  return (
    <Box>
      <Typography variant="h6" sx={{ mb: 2 }}>
        Lookup Tables
      </Typography>

      {SECTIONS.map((section) => (
        <Accordion key={section.id} disableGutters>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Typography variant="subtitle1" fontWeight={600}>
              {section.title}
            </Typography>
          </AccordionSummary>
          <AccordionDetails>
            <LookupSection
              title={section.title}
              queryKey={section.queryKey}
              fetchFn={section.fetchFn}
              createFn={section.createFn}
              updateFn={section.updateFn}
              deleteFn={section.deleteFn}
              columns={section.columns}
              fields={section.fields as FieldConfig[]}
              defaultValues={{ ...section.defaultValues }}
            />
          </AccordionDetails>
        </Accordion>
      ))}
    </Box>
  );
}
