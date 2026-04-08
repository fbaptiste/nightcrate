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
import LookupPicker from "@/components/equipment/shared/LookupPicker";
import InterfaceMultiSelect from "@/components/equipment/shared/InterfaceMultiSelect";
import { parseOptionalFloat } from "@/lib/formUtils";
import {
  createMount,
  updateMount,
  fetchMountTypes,
  type Mount,
  type MountCreate,
} from "@/api/equipment";

interface MountFormDialogProps {
  open: boolean;
  item: Mount | null;
  onClose: () => void;
  onSaved: () => void;
}

interface FormState {
  model_name: string;
  manufacturer_id: number | null;
  mount_type_id: number | null;
  payload_capacity_kg: string;
  mount_weight_kg: string;
  counterweight_required: boolean;
  goto_capable: boolean;
  periodic_error_arcsec: string;
  drive_type: string;
  notes: string;
  interface_ids: number[];
}

function emptyForm(): FormState {
  return {
    model_name: "",
    manufacturer_id: null,
    mount_type_id: null,
    payload_capacity_kg: "",
    mount_weight_kg: "",
    counterweight_required: true,
    goto_capable: true,
    periodic_error_arcsec: "",
    drive_type: "",
    notes: "",
    interface_ids: [],
  };
}

function mountToForm(item: Mount): FormState {
  return {
    model_name: item.model_name,
    manufacturer_id: item.manufacturer.id,
    mount_type_id: item.mount_type?.id ?? null,
    payload_capacity_kg: item.payload_capacity_kg != null ? String(item.payload_capacity_kg) : "",
    mount_weight_kg: item.mount_weight_kg != null ? String(item.mount_weight_kg) : "",
    counterweight_required: item.counterweight_required,
    goto_capable: item.goto_capable,
    periodic_error_arcsec: item.periodic_error_arcsec != null ? String(item.periodic_error_arcsec) : "",
    drive_type: item.drive_type ?? "",
    notes: item.notes ?? "",
    interface_ids: item.interfaces.map((i) => i.id),
  };
}

export default function MountFormDialog({
  open,
  item,
  onClose,
  onSaved,
}: MountFormDialogProps) {
  const [form, setForm] = useState<FormState>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>({});
  const [snackOpen, setSnackOpen] = useState(false);
  const [snackMessage, setSnackMessage] = useState("");
  const [snackSeverity, setSnackSeverity] = useState<"info" | "error">("info");

  useEffect(() => {
    if (open) {
      setForm(item ? mountToForm(item) : emptyForm());
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
      const payload: MountCreate = {
        model_name: form.model_name.trim(),
        manufacturer_id: form.manufacturer_id!,
        mount_type_id: form.mount_type_id,
        payload_capacity_kg: parseOptionalFloat(form.payload_capacity_kg),
        mount_weight_kg: parseOptionalFloat(form.mount_weight_kg),
        counterweight_required: form.counterweight_required,
        goto_capable: form.goto_capable,
        periodic_error_arcsec: parseOptionalFloat(form.periodic_error_arcsec),
        drive_type: form.drive_type.trim() || null,
        notes: form.notes.trim() || null,
        interface_ids: form.interface_ids,
      };

      if (item) {
        await updateMount(item.id, payload);
      } else {
        await createMount(payload);
      }

      setSnackMessage(isEdit ? "Mount updated." : "Mount added.");
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
        <DialogTitle>{isEdit ? "Edit Mount" : "Add Mount"}</DialogTitle>

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

            {/* Row 2: Mount type + Drive type */}
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2 }}>
              <LookupPicker
                fetchFn={fetchMountTypes}
                queryKey="mount-types"
                label="Mount Type"
                value={form.mount_type_id}
                onChange={(id) => set("mount_type_id", id)}
              />
              <TextField
                label="Drive Type"
                value={form.drive_type}
                onChange={(e) => set("drive_type", e.target.value)}
              />
            </Box>

            {/* Row 3: Payload + Mount weight + Periodic error */}
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 2 }}>
              <TextField
                label="Payload Capacity (kg)"
                type="number"
                value={form.payload_capacity_kg}
                onChange={(e) => set("payload_capacity_kg", e.target.value)}
                slotProps={{ htmlInput: { step: "any" } }}
              />
              <TextField
                label="Mount Weight (kg)"
                type="number"
                value={form.mount_weight_kg}
                onChange={(e) => set("mount_weight_kg", e.target.value)}
                slotProps={{ htmlInput: { step: "any" } }}
              />
              <TextField
                label="Periodic Error (arcsec)"
                type="number"
                value={form.periodic_error_arcsec}
                onChange={(e) => set("periodic_error_arcsec", e.target.value)}
                slotProps={{ htmlInput: { step: "any" } }}
              />
            </Box>

            {/* Row 4: Switches */}
            <Box sx={{ display: "flex", alignItems: "center", gap: 3, flexWrap: "wrap" }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={form.counterweight_required}
                    onChange={(e) => set("counterweight_required", e.target.checked)}
                  />
                }
                label="Counterweight Required"
              />
              <FormControlLabel
                control={
                  <Switch
                    checked={form.goto_capable}
                    onChange={(e) => set("goto_capable", e.target.checked)}
                  />
                }
                label="GoTo Capable"
              />
            </Box>

            {/* Row 5: Connection interfaces */}
            <InterfaceMultiSelect
              value={form.interface_ids}
              onChange={(ids) => set("interface_ids", ids)}
            />

            {/* Row 6: Notes */}
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
