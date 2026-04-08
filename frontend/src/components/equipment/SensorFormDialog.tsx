import { useState, useEffect } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControlLabel from "@mui/material/FormControlLabel";
import FormControl from "@mui/material/FormControl";
import FormHelperText from "@mui/material/FormHelperText";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Snackbar from "@mui/material/Snackbar";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import ManufacturerPicker from "@/components/equipment/shared/ManufacturerPicker";
import { parseOptionalFloat, parseOptionalInt } from "@/lib/formUtils";
import {
  createSensor,
  updateSensor,
  type Sensor,
  type SensorCreate,
} from "@/api/equipment";

interface SensorFormDialogProps {
  open: boolean;
  item: Sensor | null;
  onClose: () => void;
  onSaved: () => void;
}

interface FormState {
  model_name: string;
  manufacturer_id: number | null;
  sensor_type: "mono" | "color" | "";
  pixel_size_um: string;
  resolution_x: string;
  resolution_y: string;
  sensor_width_mm: string;
  sensor_height_mm: string;
  adc_bit_depth: string;
  full_well_capacity_ke: string;
  read_noise_e: string;
  peak_qe_pct: string;
  bayer_pattern: string;
  dual_gain: boolean;
  hcg_threshold_gain: string;
  notes: string;
}

function emptyForm(): FormState {
  return {
    model_name: "",
    manufacturer_id: null,
    sensor_type: "",
    pixel_size_um: "",
    resolution_x: "",
    resolution_y: "",
    sensor_width_mm: "",
    sensor_height_mm: "",
    adc_bit_depth: "",
    full_well_capacity_ke: "",
    read_noise_e: "",
    peak_qe_pct: "",
    bayer_pattern: "",
    dual_gain: false,
    hcg_threshold_gain: "",
    notes: "",
  };
}

function sensorToForm(sensor: Sensor): FormState {
  return {
    model_name: sensor.model_name,
    manufacturer_id: sensor.manufacturer.id,
    sensor_type: sensor.sensor_type,
    pixel_size_um: String(sensor.pixel_size_um),
    resolution_x: String(sensor.resolution_x),
    resolution_y: String(sensor.resolution_y),
    sensor_width_mm: sensor.sensor_width_mm != null ? String(sensor.sensor_width_mm) : "",
    sensor_height_mm: sensor.sensor_height_mm != null ? String(sensor.sensor_height_mm) : "",
    adc_bit_depth: sensor.adc_bit_depth != null ? String(sensor.adc_bit_depth) : "",
    full_well_capacity_ke: sensor.full_well_capacity_ke != null ? String(sensor.full_well_capacity_ke) : "",
    read_noise_e: sensor.read_noise_e != null ? String(sensor.read_noise_e) : "",
    peak_qe_pct: sensor.peak_qe_pct != null ? String(sensor.peak_qe_pct) : "",
    bayer_pattern: sensor.bayer_pattern ?? "",
    dual_gain: sensor.dual_gain,
    hcg_threshold_gain: sensor.hcg_threshold_gain != null ? String(sensor.hcg_threshold_gain) : "",
    notes: sensor.notes ?? "",
  };
}

export default function SensorFormDialog({
  open,
  item,
  onClose,
  onSaved,
}: SensorFormDialogProps) {
  const [form, setForm] = useState<FormState>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>({});
  const [snackOpen, setSnackOpen] = useState(false);
  const [snackMessage, setSnackMessage] = useState("");
  const [snackSeverity, setSnackSeverity] = useState<"info" | "error">("info");

  useEffect(() => {
    if (open) {
      setForm(item ? sensorToForm(item) : emptyForm());
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
    if (!form.sensor_type) newErrors.sensor_type = "Sensor type is required";
    if (!form.pixel_size_um.trim()) newErrors.pixel_size_um = "Pixel size is required";
    if (!form.resolution_x.trim()) newErrors.resolution_x = "Resolution X is required";
    if (!form.resolution_y.trim()) newErrors.resolution_y = "Resolution Y is required";
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSave = async () => {
    if (!validate()) return;

    setSaving(true);
    try {
      const payload: SensorCreate = {
        model_name: form.model_name.trim(),
        manufacturer_id: form.manufacturer_id!,
        sensor_type: form.sensor_type as "mono" | "color",
        pixel_size_um: parseFloat(form.pixel_size_um),
        resolution_x: parseInt(form.resolution_x, 10),
        resolution_y: parseInt(form.resolution_y, 10),
        sensor_width_mm: parseOptionalFloat(form.sensor_width_mm),
        sensor_height_mm: parseOptionalFloat(form.sensor_height_mm),
        adc_bit_depth: parseOptionalInt(form.adc_bit_depth),
        full_well_capacity_ke: parseOptionalFloat(form.full_well_capacity_ke),
        read_noise_e: parseOptionalFloat(form.read_noise_e),
        peak_qe_pct: parseOptionalFloat(form.peak_qe_pct),
        bayer_pattern: form.sensor_type === "color" && form.bayer_pattern ? form.bayer_pattern : null,
        dual_gain: form.dual_gain,
        hcg_threshold_gain: form.dual_gain ? parseOptionalFloat(form.hcg_threshold_gain) : null,
        notes: form.notes.trim() || null,
      };

      if (item) {
        await updateSensor(item.id, payload);
      } else {
        await createSensor(payload);
      }

      setSnackMessage(isEdit ? "Sensor updated." : "Sensor added.");
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
        <DialogTitle>{isEdit ? "Edit Sensor" : "Add Sensor"}</DialogTitle>

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

            {/* Row 2: Sensor type + Bayer pattern (conditional) */}
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2 }}>
              <FormControl required error={Boolean(errors.sensor_type)}>
                <InputLabel>Sensor Type</InputLabel>
                <Select
                  label="Sensor Type"
                  value={form.sensor_type}
                  onChange={(e) => {
                    set("sensor_type", e.target.value as "mono" | "color" | "");
                    if (e.target.value !== "color") {
                      set("bayer_pattern", "");
                    }
                  }}
                >
                  <MenuItem value="mono">Mono</MenuItem>
                  <MenuItem value="color">Color</MenuItem>
                </Select>
                {errors.sensor_type && (
                  <FormHelperText>{errors.sensor_type}</FormHelperText>
                )}
              </FormControl>

              {form.sensor_type === "color" && (
                <FormControl>
                  <InputLabel>Bayer Pattern</InputLabel>
                  <Select
                    label="Bayer Pattern"
                    value={form.bayer_pattern}
                    onChange={(e) => set("bayer_pattern", e.target.value)}
                  >
                    <MenuItem value="">— None —</MenuItem>
                    <MenuItem value="RGGB">RGGB</MenuItem>
                    <MenuItem value="BGGR">BGGR</MenuItem>
                    <MenuItem value="GRBG">GRBG</MenuItem>
                    <MenuItem value="GBRG">GBRG</MenuItem>
                  </Select>
                </FormControl>
              )}
            </Box>

            {/* Row 3: Pixel size + Resolution X + Resolution Y */}
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 2 }}>
              <TextField
                label="Pixel Size (µm)"
                type="number"
                value={form.pixel_size_um}
                onChange={(e) => set("pixel_size_um", e.target.value)}
                required
                error={Boolean(errors.pixel_size_um)}
                helperText={errors.pixel_size_um}
                slotProps={{ htmlInput: { step: "any" } }}
              />
              <TextField
                label="Resolution X"
                type="number"
                value={form.resolution_x}
                onChange={(e) => set("resolution_x", e.target.value)}
                required
                error={Boolean(errors.resolution_x)}
                helperText={errors.resolution_x}
                slotProps={{ htmlInput: { step: "1" } }}
              />
              <TextField
                label="Resolution Y"
                type="number"
                value={form.resolution_y}
                onChange={(e) => set("resolution_y", e.target.value)}
                required
                error={Boolean(errors.resolution_y)}
                helperText={errors.resolution_y}
                slotProps={{ htmlInput: { step: "1" } }}
              />
            </Box>

            {/* Row 4: Sensor width + height */}
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2 }}>
              <TextField
                label="Sensor Width (mm)"
                type="number"
                value={form.sensor_width_mm}
                onChange={(e) => set("sensor_width_mm", e.target.value)}
                slotProps={{ htmlInput: { step: "any" } }}
              />
              <TextField
                label="Sensor Height (mm)"
                type="number"
                value={form.sensor_height_mm}
                onChange={(e) => set("sensor_height_mm", e.target.value)}
                slotProps={{ htmlInput: { step: "any" } }}
              />
            </Box>

            {/* Row 5: ADC bit depth + Full well + Read noise + Peak QE */}
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 2 }}>
              <TextField
                label="ADC Bit Depth"
                type="number"
                value={form.adc_bit_depth}
                onChange={(e) => set("adc_bit_depth", e.target.value)}
                slotProps={{ htmlInput: { step: "1" } }}
              />
              <TextField
                label="Full Well (ke⁻)"
                type="number"
                value={form.full_well_capacity_ke}
                onChange={(e) => set("full_well_capacity_ke", e.target.value)}
                slotProps={{ htmlInput: { step: "any" } }}
              />
              <TextField
                label="Read Noise (e⁻)"
                type="number"
                value={form.read_noise_e}
                onChange={(e) => set("read_noise_e", e.target.value)}
                slotProps={{ htmlInput: { step: "any" } }}
              />
              <TextField
                label="Peak QE (%)"
                type="number"
                value={form.peak_qe_pct}
                onChange={(e) => set("peak_qe_pct", e.target.value)}
                slotProps={{ htmlInput: { step: "any" } }}
              />
            </Box>

            {/* Row 6: Dual gain toggle + HCG threshold (conditional) */}
            <Box sx={{ display: "flex", alignItems: "center", gap: 3 }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={form.dual_gain}
                    onChange={(e) => set("dual_gain", e.target.checked)}
                  />
                }
                label="Dual Gain"
              />
              {form.dual_gain && (
                <TextField
                  label="HCG Threshold Gain"
                  type="number"
                  value={form.hcg_threshold_gain}
                  onChange={(e) => set("hcg_threshold_gain", e.target.value)}
                  size="small"
                  sx={{ width: 200 }}
                  slotProps={{ htmlInput: { step: "1" } }}
                />
              )}
            </Box>

            {/* Row 7: Notes */}
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
