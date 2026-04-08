import { useState, useEffect } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Snackbar from "@mui/material/Snackbar";
import TextField from "@mui/material/TextField";
import ManufacturerPicker from "@/components/equipment/shared/ManufacturerPicker";
import { formatFilterType } from "@/lib/formUtils";
import {
  createSoftware,
  updateSoftware,
  type Software,
  type SoftwareCreate,
} from "@/api/equipment";

interface SoftwareFormDialogProps {
  open: boolean;
  item: Software | null;
  onClose: () => void;
  onSaved: () => void;
}

const SOFTWARE_CATEGORIES = [
  "capture",
  "guiding",
  "processing",
  "planetarium",
  "plate_solving",
  "utility",
  "other",
] as const;

interface FormState {
  name: string;
  manufacturer_id: number | null;
  category: string;
  website: string;
  notes: string;
}

function emptyForm(): FormState {
  return {
    name: "",
    manufacturer_id: null,
    category: "capture",
    website: "",
    notes: "",
  };
}

function softwareToForm(item: Software): FormState {
  return {
    name: item.name,
    manufacturer_id: item.manufacturer?.id ?? null,
    category: item.category,
    website: item.website ?? "",
    notes: item.notes ?? "",
  };
}

export default function SoftwareFormDialog({
  open,
  item,
  onClose,
  onSaved,
}: SoftwareFormDialogProps) {
  const [form, setForm] = useState<FormState>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>({});
  const [snackOpen, setSnackOpen] = useState(false);
  const [snackMessage, setSnackMessage] = useState("");
  const [snackSeverity, setSnackSeverity] = useState<"info" | "error">("info");

  useEffect(() => {
    if (open) {
      setForm(item ? softwareToForm(item) : emptyForm());
      setErrors({});
    }
  }, [open, item]);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const validate = (): boolean => {
    const newErrors: Partial<Record<keyof FormState, string>> = {};
    if (!form.name.trim()) newErrors.name = "Name is required";
    if (form.manufacturer_id == null) newErrors.manufacturer_id = "Manufacturer is required";
    if (!form.category) newErrors.category = "Category is required";
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSave = async () => {
    if (!validate()) return;

    setSaving(true);
    try {
      const payload: SoftwareCreate = {
        name: form.name.trim(),
        manufacturer_id: form.manufacturer_id,
        category: form.category,
        website: form.website.trim() || null,
        notes: form.notes.trim() || null,
      };

      if (item) {
        await updateSoftware(item.id, payload);
      } else {
        await createSoftware(payload);
      }

      setSnackMessage(isEdit ? "Software updated." : "Software added.");
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
        <DialogTitle>{isEdit ? "Edit Software" : "Add Software"}</DialogTitle>

        <DialogContent>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 1 }}>
            {/* Row 1: Name + Manufacturer */}
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2 }}>
              <TextField
                label="Name"
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
                required
                error={Boolean(errors.name)}
                helperText={errors.name}
              />
              <ManufacturerPicker
                value={form.manufacturer_id}
                onChange={(id) => set("manufacturer_id", id)}
                required
                error={Boolean(errors.manufacturer_id)}
                helperText={errors.manufacturer_id}
              />
            </Box>

            {/* Row 2: Category */}
            <FormControl required error={Boolean(errors.category)}>
              <InputLabel id="software-category-label">Category</InputLabel>
              <Select
                labelId="software-category-label"
                value={form.category}
                label="Category"
                onChange={(e) => set("category", e.target.value)}
              >
                {SOFTWARE_CATEGORIES.map((cat) => (
                  <MenuItem key={cat} value={cat}>
                    {formatFilterType(cat)}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            {/* Row 3: Website */}
            <TextField
              label="Website"
              value={form.website}
              onChange={(e) => set("website", e.target.value)}
            />

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
        <Alert severity={snackSeverity} onClose={() => setSnackOpen(false)} sx={{ width: "100%" }}>
          {snackMessage}
        </Alert>
      </Snackbar>
    </>
  );
}
