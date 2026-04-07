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
import {
  createManufacturer,
  updateManufacturer,
  type Manufacturer,
  type ManufacturerCreate,
} from "@/api/equipment";

interface ManufacturerFormDialogProps {
  open: boolean;
  item: Manufacturer | null;
  onClose: () => void;
  onSaved: () => void;
}

interface FormState {
  name: string;
  website: string;
  notes: string;
}

function emptyForm(): FormState {
  return {
    name: "",
    website: "",
    notes: "",
  };
}

function manufacturerToForm(item: Manufacturer): FormState {
  return {
    name: item.name,
    website: item.website ?? "",
    notes: item.notes ?? "",
  };
}

export default function ManufacturerFormDialog({
  open,
  item,
  onClose,
  onSaved,
}: ManufacturerFormDialogProps) {
  const [form, setForm] = useState<FormState>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>({});
  const [snackOpen, setSnackOpen] = useState(false);

  useEffect(() => {
    if (open) {
      setForm(item ? manufacturerToForm(item) : emptyForm());
      setErrors({});
    }
  }, [open, item]);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const validate = (): boolean => {
    const newErrors: Partial<Record<keyof FormState, string>> = {};
    if (!form.name.trim()) newErrors.name = "Name is required";
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSave = async () => {
    if (!validate()) return;

    setSaving(true);
    try {
      const payload: ManufacturerCreate = {
        name: form.name.trim(),
        website: form.website.trim() || undefined,
        notes: form.notes.trim() || undefined,
      };

      if (item) {
        await updateManufacturer(item.id, payload);
      } else {
        await createManufacturer(payload);
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
      <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
        <DialogTitle>{isEdit ? "Edit Manufacturer" : "Add Manufacturer"}</DialogTitle>

        <DialogContent>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 1 }}>
            <TextField
              label="Name"
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
              required
              error={Boolean(errors.name)}
              helperText={errors.name}
            />

            <TextField
              label="Website"
              value={form.website}
              onChange={(e) => set("website", e.target.value)}
            />

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
          {isEdit ? "Manufacturer updated." : "Manufacturer added."}
        </Alert>
      </Snackbar>
    </>
  );
}
