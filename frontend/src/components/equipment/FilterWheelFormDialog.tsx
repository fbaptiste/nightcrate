import { useState, useEffect } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Snackbar from "@mui/material/Snackbar";
import TextField from "@mui/material/TextField";
import ManufacturerPicker from "@/components/equipment/shared/ManufacturerPicker";
import LookupPicker from "@/components/equipment/shared/LookupPicker";
import InterfaceMultiSelect from "@/components/equipment/shared/InterfaceMultiSelect";
import { parseOptionalFloat, parseOptionalInt } from "@/lib/formUtils";
import {
  createFilterWheel,
  updateFilterWheel,
  fetchFilterSizes,
  fetchConnectorSizes,
  type FilterWheel,
  type FilterWheelCreate,
} from "@/api/equipment";

interface FilterWheelFormDialogProps {
  open: boolean;
  item: FilterWheel | null;
  onClose: () => void;
  onSaved: () => void;
}

interface FormState {
  model_name: string;
  manufacturer_id: number | null;
  filter_size_id: number | null;
  camera_side_connector_id: number | null;
  telescope_side_connector_id: number | null;
  num_positions: string;
  back_focus_contribution_mm: string;
  notes: string;
  interface_ids: number[];
}

function emptyForm(): FormState {
  return {
    model_name: "",
    manufacturer_id: null,
    filter_size_id: null,
    camera_side_connector_id: null,
    telescope_side_connector_id: null,
    num_positions: "",
    back_focus_contribution_mm: "",
    notes: "",
    interface_ids: [],
  };
}

function filterWheelToForm(item: FilterWheel): FormState {
  return {
    model_name: item.model_name,
    manufacturer_id: item.manufacturer.id,
    filter_size_id: item.filter_size?.id ?? null,
    camera_side_connector_id: item.camera_side_connector?.id ?? null,
    telescope_side_connector_id: item.telescope_side_connector?.id ?? null,
    num_positions: String(item.num_positions),
    back_focus_contribution_mm:
      item.back_focus_contribution_mm != null ? String(item.back_focus_contribution_mm) : "",
    notes: item.notes ?? "",
    interface_ids: item.interfaces.map((i) => i.id),
  };
}

export default function FilterWheelFormDialog({
  open,
  item,
  onClose,
  onSaved,
}: FilterWheelFormDialogProps) {
  const [form, setForm] = useState<FormState>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>({});
  const [snackOpen, setSnackOpen] = useState(false);
  const [snackMessage, setSnackMessage] = useState("");
  const [snackSeverity, setSnackSeverity] = useState<"info" | "error">("info");

  useEffect(() => {
    if (open) {
      setForm(item ? filterWheelToForm(item) : emptyForm());
      setErrors({});
    }
  }, [open, item]);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const validate = (): boolean => {
    const newErrors: Partial<Record<keyof FormState, string>> = {};
    if (!form.model_name.trim()) newErrors.model_name = "Model name is required";
    if (form.manufacturer_id == null) newErrors.manufacturer_id = "Manufacturer is required";
    if (!form.num_positions.trim()) newErrors.num_positions = "Number of positions is required";
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSave = async () => {
    if (!validate()) return;

    setSaving(true);
    try {
      const payload: FilterWheelCreate = {
        model_name: form.model_name.trim(),
        manufacturer_id: form.manufacturer_id!,
        filter_size_id: form.filter_size_id,
        camera_side_connector_id: form.camera_side_connector_id,
        telescope_side_connector_id: form.telescope_side_connector_id,
        num_positions: parseOptionalInt(form.num_positions)!,
        back_focus_contribution_mm: parseOptionalFloat(form.back_focus_contribution_mm),
        notes: form.notes.trim() || null,
        interface_ids: form.interface_ids,
      };

      if (item) {
        await updateFilterWheel(item.id, payload);
      } else {
        await createFilterWheel(payload);
      }

      setSnackMessage(isEdit ? "Filter wheel updated." : "Filter wheel added.");
      setSnackSeverity("info");
      setSnackOpen(true);
      onSaved();
      onClose();
    } catch (err) {
      setSnackMessage(err instanceof Error ? err.message : "Save failed");
      setSnackSeverity("error");
      setSnackOpen(true);
    } finally {
      setSaving(false);
    }
  };

  const isEdit = item !== null;

  return (
    <>
      <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
        <DialogTitle>{isEdit ? "Edit Filter Wheel" : "Add Filter Wheel"}</DialogTitle>

        <DialogContent>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 1 }}>
            {/* Row 1: Model name + Manufacturer */}
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2 }}>
              <TextField
                label="Model Name"
                value={form.model_name}
                onChange={(e) => set("model_name", e.target.value)}
                required
                error={Boolean(errors.model_name)}
                helperText={errors.model_name}
              />
              <ManufacturerPicker
                value={form.manufacturer_id}
                onChange={(id) => set("manufacturer_id", id)}
                required
                error={Boolean(errors.manufacturer_id)}
                helperText={errors.manufacturer_id}
              />
            </Box>

            {/* Row 2: Filter size + Num positions */}
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2 }}>
              <LookupPicker
                fetchFn={fetchFilterSizes}
                queryKey="filter-sizes"
                value={form.filter_size_id}
                onChange={(id) => set("filter_size_id", id)}
                label="Filter Size"
              />
              <TextField
                label="Num Positions"
                type="number"
                value={form.num_positions}
                onChange={(e) => set("num_positions", e.target.value)}
                required
                error={Boolean(errors.num_positions)}
                helperText={errors.num_positions}
                slotProps={{ htmlInput: { step: "1", min: "1" } }}
              />
            </Box>

            {/* Row 3: Camera side connector + Telescope side connector + Back focus */}
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 2 }}>
              <LookupPicker
                fetchFn={fetchConnectorSizes}
                queryKey="connector-sizes"
                value={form.camera_side_connector_id}
                onChange={(id) => set("camera_side_connector_id", id)}
                label="Camera Side Connector"
              />
              <LookupPicker
                fetchFn={fetchConnectorSizes}
                queryKey="connector-sizes"
                value={form.telescope_side_connector_id}
                onChange={(id) => set("telescope_side_connector_id", id)}
                label="Telescope Side Connector"
              />
              <TextField
                label="Back Focus Contribution (mm)"
                type="number"
                value={form.back_focus_contribution_mm}
                onChange={(e) => set("back_focus_contribution_mm", e.target.value)}
                slotProps={{ htmlInput: { step: "any" } }}
              />
            </Box>

            {/* Row 4: Connection interfaces */}
            <InterfaceMultiSelect
              value={form.interface_ids}
              onChange={(ids) => set("interface_ids", ids)}
            />

            {/* Row 5: Notes */}
            <TextField
              label="Notes"
              value={form.notes}
              onChange={(e) => set("notes", e.target.value)}
              multiline
              rows={3}
            />
          </Box>
        </DialogContent>

        <DialogActions>
          <Button onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={handleSave} variant="contained" disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={snackOpen}
        autoHideDuration={3000}
        onClose={() => setSnackOpen(false)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert severity={snackSeverity} onClose={() => setSnackOpen(false)} sx={{ width: "100%" }}>
          {snackMessage}
        </Alert>
      </Snackbar>
    </>
  );
}
