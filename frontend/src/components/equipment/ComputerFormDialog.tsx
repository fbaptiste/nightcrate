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
import { fetchComputerTypes } from "@/api/equipment";
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
  computer_type_id: number | null;
  notes: string;
}

function emptyForm(): FormState {
  return {
    model_name: "",
    manufacturer_id: null,
    computer_type_id: null,
    notes: "",
  };
}

function computerToForm(item: Computer): FormState {
  return {
    model_name: item.model_name,
    manufacturer_id: item.manufacturer.id,
    computer_type_id: item.computer_type?.id ?? null,
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
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>({});
  const [snackOpen, setSnackOpen] = useState(false);

  useEffect(() => {
    if (open) {
      setForm(item ? computerToForm(item) : emptyForm());
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
        model_name: form.model_name.trim(),
        manufacturer_id: form.manufacturer_id!,
        computer_type_id: form.computer_type_id,
        notes: form.notes.trim() || null,
      };

      if (item) {
        await updateComputer(item.id, payload);
      } else {
        await createComputer(payload);
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
        <DialogTitle>{isEdit ? "Edit Computer" : "Add Computer"}</DialogTitle>

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

            {/* Row 2: Computer Type */}
            <LookupPicker
              fetchFn={fetchComputerTypes}
              queryKey="computer-types"
              label="Computer Type"
              value={form.computer_type_id}
              onChange={(id) => set("computer_type_id", id)}
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
        <Alert severity="info" onClose={() => setSnackOpen(false)} sx={{ width: "100%" }}>
          {isEdit ? "Computer updated." : "Computer added."}
        </Alert>
      </Snackbar>
    </>
  );
}
