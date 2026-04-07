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
import { parseOptionalFloat } from "@/lib/formUtils";
import {
  createOag,
  updateOag,
  fetchConnectorSizes,
  type Oag,
  type OagCreate,
} from "@/api/equipment";

interface OagFormDialogProps {
  open: boolean;
  item: Oag | null;
  onClose: () => void;
  onSaved: () => void;
}

interface FormState {
  model_name: string;
  manufacturer_id: number | null;
  imaging_side_connector_id: number | null;
  guide_camera_connector_id: number | null;
  prism_size_mm: string;
  back_focus_contribution_mm: string;
  weight_g: string;
  notes: string;
}

function emptyForm(): FormState {
  return {
    model_name: "",
    manufacturer_id: null,
    imaging_side_connector_id: null,
    guide_camera_connector_id: null,
    prism_size_mm: "",
    back_focus_contribution_mm: "",
    weight_g: "",
    notes: "",
  };
}

function oagToForm(item: Oag): FormState {
  return {
    model_name: item.model_name,
    manufacturer_id: item.manufacturer.id,
    imaging_side_connector_id: item.imaging_side_connector?.id ?? null,
    guide_camera_connector_id: item.guide_camera_connector?.id ?? null,
    prism_size_mm: item.prism_size_mm != null ? String(item.prism_size_mm) : "",
    back_focus_contribution_mm:
      item.back_focus_contribution_mm != null ? String(item.back_focus_contribution_mm) : "",
    weight_g: item.weight_g != null ? String(item.weight_g) : "",
    notes: item.notes ?? "",
  };
}

export default function OagFormDialog({
  open,
  item,
  onClose,
  onSaved,
}: OagFormDialogProps) {
  const [form, setForm] = useState<FormState>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>({});
  const [snackOpen, setSnackOpen] = useState(false);

  useEffect(() => {
    if (open) {
      setForm(item ? oagToForm(item) : emptyForm());
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
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSave = async () => {
    if (!validate()) return;

    setSaving(true);
    try {
      const payload: OagCreate = {
        model_name: form.model_name.trim(),
        manufacturer_id: form.manufacturer_id!,
        imaging_side_connector_id: form.imaging_side_connector_id,
        guide_camera_connector_id: form.guide_camera_connector_id,
        prism_size_mm: parseOptionalFloat(form.prism_size_mm),
        back_focus_contribution_mm: parseOptionalFloat(form.back_focus_contribution_mm),
        weight_g: parseOptionalFloat(form.weight_g),
        notes: form.notes.trim() || null,
      };

      if (item) {
        await updateOag(item.id, payload);
      } else {
        await createOag(payload);
      }

      setSnackOpen(true);
      onSaved();
      onClose();
    } finally {
      setSaving(false);
    }
  };

  const isEdit = item !== null;

  return (
    <>
      <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
        <DialogTitle>{isEdit ? "Edit OAG" : "Add OAG"}</DialogTitle>

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

            {/* Row 2: Connectors */}
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2 }}>
              <LookupPicker
                fetchFn={fetchConnectorSizes}
                queryKey="connector-sizes"
                label="Imaging Side Connector"
                value={form.imaging_side_connector_id}
                onChange={(id) => set("imaging_side_connector_id", id)}
              />
              <LookupPicker
                fetchFn={fetchConnectorSizes}
                queryKey="connector-sizes"
                label="Guide Camera Connector"
                value={form.guide_camera_connector_id}
                onChange={(id) => set("guide_camera_connector_id", id)}
              />
            </Box>

            {/* Row 3: Numeric fields */}
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 2 }}>
              <TextField
                label="Prism Size (mm)"
                type="number"
                value={form.prism_size_mm}
                onChange={(e) => set("prism_size_mm", e.target.value)}
                slotProps={{ htmlInput: { step: "any" } }}
              />
              <TextField
                label="Back Focus Contribution (mm)"
                type="number"
                value={form.back_focus_contribution_mm}
                onChange={(e) => set("back_focus_contribution_mm", e.target.value)}
                slotProps={{ htmlInput: { step: "any" } }}
              />
              <TextField
                label="Weight (g)"
                type="number"
                value={form.weight_g}
                onChange={(e) => set("weight_g", e.target.value)}
                slotProps={{ htmlInput: { step: "any" } }}
              />
            </Box>

            {/* Row 4: Notes */}
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
        <Alert severity="info" onClose={() => setSnackOpen(false)} sx={{ width: "100%" }}>
          {isEdit ? "OAG updated." : "OAG added."}
        </Alert>
      </Snackbar>
    </>
  );
}
