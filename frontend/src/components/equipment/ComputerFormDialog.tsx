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
import MineCheckbox from "@/components/equipment/shared/MineCheckbox";
import LookupPicker from "@/components/equipment/shared/LookupPicker";
import { fetchFormFactors } from "@/api/equipment";
import {
  createComputer,
  updateComputer,
  type Computer,
  type ComputerCreate,
} from "@/api/equipment";

interface ComputerFormDialogProps {
  open: boolean;
  item: Computer | null;
  onClose: () => void;
  onSaved: () => void;
}

interface FormState {
  model_name: string;
  manufacturer_id: number | null;
  form_factor_id: number | null;
  notes: string;
}

function emptyForm(): FormState {
  return {
    model_name: "",
    manufacturer_id: null,
    form_factor_id: null,
    notes: "",
  };
}

function computerToForm(item: Computer): FormState {
  return {
    model_name: item.model_name,
    manufacturer_id: item.manufacturer.id,
    form_factor_id: item.form_factor?.id ?? null,
    notes: item.notes ?? "",
  };
}

export default function ComputerFormDialog({
  open,
  item,
  onClose,
  onSaved,
}: ComputerFormDialogProps) {
  const [form, setForm] = useState<FormState>(emptyForm);
  const [isMine, setIsMine] = useState<boolean>(false);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>({});
  const [snackOpen, setSnackOpen] = useState(false);
  const [snackMessage, setSnackMessage] = useState("");
  const [snackSeverity, setSnackSeverity] = useState<"info" | "error">("info");

  useEffect(() => {
    if (open) {
      setForm(item ? computerToForm(item) : emptyForm());
      setIsMine(item?.is_mine ?? false);
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
      const payload: ComputerCreate = {
        is_mine: isMine,
        model_name: form.model_name.trim(),
        manufacturer_id: form.manufacturer_id!,
        form_factor_id: form.form_factor_id,
        notes: form.notes.trim() || null,
      };

      if (item) {
        await updateComputer(item.id, payload);
      } else {
        await createComputer(payload);
      }

      setSnackMessage(isEdit ? "Computer updated." : "Computer added.");
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
        <DialogTitle>{isEdit ? "Edit Computer" : "Add Computer"}</DialogTitle>

        <DialogContent>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 1 }}>
            <MineCheckbox value={isMine} onChange={setIsMine} />

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

            {/* Row 2: Form Factor */}
            <LookupPicker
              fetchFn={fetchFormFactors}
              queryKey="form-factors"
              label="Form Factor"
              value={form.form_factor_id}
              onChange={(id) => set("form_factor_id", id)}
            />

            {/* Row 3: Notes */}
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
