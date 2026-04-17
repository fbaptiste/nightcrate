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
import MineCheckbox from "@/components/equipment/shared/MineCheckbox";
import SensorPicker from "@/components/equipment/shared/SensorPicker";
import LookupPicker from "@/components/equipment/shared/LookupPicker";
import InterfaceMultiSelect from "@/components/equipment/shared/InterfaceMultiSelect";
import { parseOptionalFloat, parseOptionalInt } from "@/lib/formUtils";
import {
  createCamera,
  updateCamera,
  fetchConnectorSizes,
  fetchConnectionInterfaces,
  type Camera,
  type CameraCreate,
} from "@/api/equipment";

interface CameraFormDialogProps {
  open: boolean;
  camera: Camera | null;
  onClose: () => void;
  onSaved: () => void;
}

interface FormState {
  model_name: string;
  manufacturer_id: number | null;
  sensor_id: number | null;
  guide_sensor_id: number | null;
  connector_size_id: number | null;
  cooled: boolean;
  cooling_delta_c: string;
  back_focus_mm: string;
  weight_g: string;
  tilt_adapter: boolean;
  has_usb_hub: boolean;
  usb_hub_interface_id: number | null;
  unity_gain: string;
  notes: string;
  interface_ids: number[];
}

function emptyForm(): FormState {
  return {
    model_name: "",
    manufacturer_id: null,
    sensor_id: null,
    guide_sensor_id: null,
    connector_size_id: null,
    cooled: false,
    cooling_delta_c: "",
    back_focus_mm: "",
    weight_g: "",
    tilt_adapter: false,
    has_usb_hub: false,
    usb_hub_interface_id: null,
    unity_gain: "",
    notes: "",
    interface_ids: [],
  };
}

function cameraToForm(camera: Camera): FormState {
  return {
    model_name: camera.model_name,
    manufacturer_id: camera.manufacturer.id,
    sensor_id: camera.sensor.id,
    guide_sensor_id: camera.guide_sensor?.id ?? null,
    connector_size_id: camera.connector_size?.id ?? null,
    cooled: camera.cooled,
    cooling_delta_c: camera.cooling_delta_c != null ? String(camera.cooling_delta_c) : "",
    back_focus_mm: camera.back_focus_mm != null ? String(camera.back_focus_mm) : "",
    weight_g: camera.weight_g != null ? String(camera.weight_g) : "",
    tilt_adapter: camera.tilt_adapter,
    has_usb_hub: camera.has_usb_hub,
    usb_hub_interface_id: camera.usb_hub_interface?.id ?? null,
    unity_gain: camera.unity_gain != null ? String(camera.unity_gain) : "",
    notes: camera.notes ?? "",
    interface_ids: camera.interfaces.map((i) => i.id),
  };
}


export default function CameraFormDialog({
  open,
  camera,
  onClose,
  onSaved,
}: CameraFormDialogProps) {
  const [form, setForm] = useState<FormState>(emptyForm);
  const [isMine, setIsMine] = useState<boolean>(false);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>({});
  const [snackOpen, setSnackOpen] = useState(false);
  const [snackMessage, setSnackMessage] = useState("");
  const [snackSeverity, setSnackSeverity] = useState<"info" | "error">("info");

  useEffect(() => {
    if (open) {
      setForm(camera ? cameraToForm(camera) : emptyForm());
      setIsMine(camera?.is_mine ?? false);
      setErrors({});
    }
  }, [open, camera]);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const validate = (): boolean => {
    const newErrors: Partial<Record<keyof FormState, string>> = {};
    if (!form.model_name.trim()) newErrors.model_name = "Model name is required";
    if (form.manufacturer_id == null) newErrors.manufacturer_id = "Manufacturer is required";
    if (form.sensor_id == null) newErrors.sensor_id = "Sensor is required";
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSave = async () => {
    if (!validate()) return;

    setSaving(true);
    try {
      const payload: CameraCreate = {
        is_mine: isMine,
        model_name: form.model_name.trim(),
        manufacturer_id: form.manufacturer_id!,
        sensor_id: form.sensor_id!,
        guide_sensor_id: form.guide_sensor_id,
        connector_size_id: form.connector_size_id,
        cooled: form.cooled,
        cooling_delta_c: form.cooled ? parseOptionalFloat(form.cooling_delta_c) : null,
        back_focus_mm: parseOptionalFloat(form.back_focus_mm),
        weight_g: parseOptionalInt(form.weight_g),
        tilt_adapter: form.tilt_adapter,
        has_usb_hub: form.has_usb_hub,
        usb_hub_interface_id: form.has_usb_hub ? form.usb_hub_interface_id : null,
        unity_gain: parseOptionalInt(form.unity_gain),
        notes: form.notes.trim() || null,
        interface_ids: form.interface_ids,
      };

      if (camera) {
        await updateCamera(camera.id, payload);
      } else {
        await createCamera(payload);
      }

      setSnackMessage(isEdit ? "Camera updated." : "Camera added.");
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

  const isEdit = camera !== null;

  return (
    <>
      <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
        <DialogTitle>{isEdit ? "Edit Camera" : "Add Camera"}</DialogTitle>

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

            {/* Row 2: Sensor + Guide Sensor */}
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2 }}>
              <SensorPicker
                label="Sensor"
                value={form.sensor_id}
                onChange={(id) => set("sensor_id", id)}
                required
                error={Boolean(errors.sensor_id)}
                helperText={errors.sensor_id}
              />
              <SensorPicker
                label="Guide Sensor (optional)"
                value={form.guide_sensor_id}
                onChange={(id) => set("guide_sensor_id", id)}
              />
            </Box>

            {/* Row 3: Connector size + Back focus + Weight */}
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 2 }}>
              <LookupPicker
                fetchFn={fetchConnectorSizes}
                queryKey="connector-sizes"
                label="Connector Size"
                value={form.connector_size_id}
                onChange={(id) => set("connector_size_id", id)}
              />
              <TextField
                label="Back Focus (mm)"
                type="number"
                value={form.back_focus_mm}
                onChange={(e) => set("back_focus_mm", e.target.value)}
                slotProps={{ htmlInput: { step: "any" } }}
              />
              <TextField
                label="Weight (g)"
                type="number"
                value={form.weight_g}
                onChange={(e) => set("weight_g", e.target.value)}
                slotProps={{ htmlInput: { step: "1" } }}
              />
            </Box>

            {/* Row 4: Unity gain */}
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 2 }}>
              <TextField
                label="Unity Gain"
                type="number"
                value={form.unity_gain}
                onChange={(e) => set("unity_gain", e.target.value)}
                slotProps={{ htmlInput: { step: "1" } }}
              />
            </Box>

            {/* Row 5: Cooled toggle + delta */}
            <Box sx={{ display: "flex", alignItems: "center", gap: 3 }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={form.cooled}
                    onChange={(e) => set("cooled", e.target.checked)}
                  />
                }
                label="Cooled"
              />
              {form.cooled && (
                <TextField
                  label="Cooling Delta (°C)"
                  type="number"
                  value={form.cooling_delta_c}
                  onChange={(e) => set("cooling_delta_c", e.target.value)}
                  size="small"
                  sx={{ width: 180 }}
                  slotProps={{ htmlInput: { step: "any" } }}
                />
              )}
            </Box>

            {/* Row 6: Tilt adapter + USB Hub */}
            <Box sx={{ display: "flex", alignItems: "center", gap: 3, flexWrap: "wrap" }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={form.tilt_adapter}
                    onChange={(e) => set("tilt_adapter", e.target.checked)}
                  />
                }
                label="Tilt Adapter"
              />
              <FormControlLabel
                control={
                  <Switch
                    checked={form.has_usb_hub}
                    onChange={(e) => set("has_usb_hub", e.target.checked)}
                  />
                }
                label="USB Hub"
              />
              {form.has_usb_hub && (
                <Box sx={{ minWidth: 220 }}>
                  <LookupPicker
                    fetchFn={fetchConnectionInterfaces}
                    queryKey="connection-interfaces"
                    label="USB Hub Interface"
                    value={form.usb_hub_interface_id}
                    onChange={(id) => set("usb_hub_interface_id", id)}
                  />
                </Box>
              )}
            </Box>

            {/* Row 7: Connection interfaces */}
            <InterfaceMultiSelect
              value={form.interface_ids}
              onChange={(ids) => set("interface_ids", ids)}
            />

            {/* Row 8: Notes */}
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
