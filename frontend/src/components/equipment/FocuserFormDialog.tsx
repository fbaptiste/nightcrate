import { useState, useEffect } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControlLabel from "@mui/material/FormControlLabel";
import Snackbar from "@mui/material/Snackbar";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import ManufacturerPicker from "@/components/equipment/shared/ManufacturerPicker";
import InterfaceMultiSelect from "@/components/equipment/shared/InterfaceMultiSelect";
import { parseOptionalFloat, parseOptionalInt } from "@/lib/formUtils";
import {
  createFocuser,
  updateFocuser,
  type Focuser,
  type FocuserCreate,
} from "@/api/equipment";

interface FocuserFormDialogProps {
  open: boolean;
  item: Focuser | null;
  onClose: () => void;
  onSaved: () => void;
}

interface FormState {
  model_name: string;
  manufacturer_id: number | null;
  motorized: boolean;
  travel_range_mm: string;
  step_size_um: string;
  total_steps: string;
  temperature_compensation: boolean;
  backlash_steps: string;
  notes: string;
  interface_ids: number[];
}

function emptyForm(): FormState {
  return {
    model_name: "",
    manufacturer_id: null,
    motorized: true,
    travel_range_mm: "",
    step_size_um: "",
    total_steps: "",
    temperature_compensation: false,
    backlash_steps: "",
    notes: "",
    interface_ids: [],
  };
}

function focuserToForm(item: Focuser): FormState {
  return {
    model_name: item.model_name,
    manufacturer_id: item.manufacturer.id,
    motorized: item.motorized,
    travel_range_mm: item.travel_range_mm != null ? String(item.travel_range_mm) : "",
    step_size_um: item.step_size_um != null ? String(item.step_size_um) : "",
    total_steps: item.total_steps != null ? String(item.total_steps) : "",
    temperature_compensation: item.temperature_compensation,
    backlash_steps: item.backlash_steps != null ? String(item.backlash_steps) : "",
    notes: item.notes ?? "",
    interface_ids: item.interfaces.map((i) => i.id),
  };
}

export default function FocuserFormDialog({
  open,
  item,
  onClose,
  onSaved,
}: FocuserFormDialogProps) {
  const [form, setForm] = useState<FormState>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>({});
  const [snackOpen, setSnackOpen] = useState(false);
  const [snackMessage, setSnackMessage] = useState("");
  const [snackSeverity, setSnackSeverity] = useState<"info" | "error">("info");

  useEffect(() => {
    if (open) {
      setForm(item ? focuserToForm(item) : emptyForm());
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
      const payload: FocuserCreate = {
        model_name: form.model_name.trim(),
        manufacturer_id: form.manufacturer_id!,
        motorized: form.motorized,
        travel_range_mm: parseOptionalFloat(form.travel_range_mm),
        step_size_um: parseOptionalFloat(form.step_size_um),
        total_steps: parseOptionalInt(form.total_steps),
        temperature_compensation: form.temperature_compensation,
        backlash_steps: parseOptionalInt(form.backlash_steps),
        notes: form.notes.trim() || null,
        interface_ids: form.interface_ids,
      };

      if (item) {
        await updateFocuser(item.id, payload);
      } else {
        await createFocuser(payload);
      }

      setSnackMessage(isEdit ? "Focuser updated." : "Focuser added.");
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
        <DialogTitle>{isEdit ? "Edit Focuser" : "Add Focuser"}</DialogTitle>

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

            {/* Row 2: Travel range + Step size + Total steps + Backlash */}
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 2 }}>
              <TextField
                label="Travel Range (mm)"
                type="number"
                value={form.travel_range_mm}
                onChange={(e) => set("travel_range_mm", e.target.value)}
                slotProps={{ htmlInput: { step: "any" } }}
              />
              <TextField
                label="Step Size (µm)"
                type="number"
                value={form.step_size_um}
                onChange={(e) => set("step_size_um", e.target.value)}
                slotProps={{ htmlInput: { step: "any" } }}
              />
              <TextField
                label="Total Steps"
                type="number"
                value={form.total_steps}
                onChange={(e) => set("total_steps", e.target.value)}
                slotProps={{ htmlInput: { step: "1" } }}
              />
              <TextField
                label="Backlash Steps"
                type="number"
                value={form.backlash_steps}
                onChange={(e) => set("backlash_steps", e.target.value)}
                slotProps={{ htmlInput: { step: "1" } }}
              />
            </Box>

            {/* Row 3: Switches */}
            <Box sx={{ display: "flex", alignItems: "center", gap: 3, flexWrap: "wrap" }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={form.motorized}
                    onChange={(e) => set("motorized", e.target.checked)}
                  />
                }
                label="Motorized"
              />
              <FormControlLabel
                control={
                  <Switch
                    checked={form.temperature_compensation}
                    onChange={(e) => set("temperature_compensation", e.target.checked)}
                  />
                }
                label="Temperature Compensation"
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
