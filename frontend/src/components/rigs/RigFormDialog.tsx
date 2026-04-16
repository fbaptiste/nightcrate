import { useState, useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControlLabel from "@mui/material/FormControlLabel";
import Paper from "@mui/material/Paper";
import Snackbar from "@mui/material/Snackbar";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import FilterSlotGrid from "@/components/rigs/FilterSlotGrid";
import {
  fetchEquipmentOptions,
  createRig,
  updateRig,
  type Rig,
  type RigCreate,
  type CameraOption,
  type FilterWheelOption,
  type FilterOption,
  type SimpleOption,
  type GuideScopeOption,
  type SoftwareOption,
  type TelescopeConfigOption,
} from "@/api/rigs";

// ── Types ──────────────────────────────────────────────────────────────────

interface RigFormDialogProps {
  open: boolean;
  rig: Rig | null;
  onClose: () => void;
  onSaved: () => void;
}

type GuidingMode = "none" | "oag" | "guide_scope";

interface FormState {
  name: string;
  description: string;
  telescope_configuration_id: number | null;
  camera_id: number | null;
  filter_wheel_id: number | null;
  single_filter_id: number | null;
  mount_id: number | null;
  focuser_id: number | null;
  oag_id: number | null;
  guide_scope_id: number | null;
  guide_camera_id: number | null;
  computer_id: number | null;
  software_id: number | null;
  is_default: boolean;
  notes: string;
  filter_slots: { slot_number: number; filter_id: number }[];
  guiding_mode: GuidingMode;
}

// Flattened config option with parent telescope info
interface FlatConfigOption extends TelescopeConfigOption {
  telescope_name: string;
  manufacturer_name: string;
  aperture_mm: number;
  telescope_id: number;
}

// ── Helpers ────────────────────────────────────────────────────────────────

const ARCSEC_PER_UM_PER_MM = 206.265;

function emptyForm(): FormState {
  return {
    name: "",
    description: "",
    telescope_configuration_id: null,
    camera_id: null,
    filter_wheel_id: null,
    single_filter_id: null,
    mount_id: null,
    focuser_id: null,
    oag_id: null,
    guide_scope_id: null,
    guide_camera_id: null,
    computer_id: null,
    software_id: null,
    is_default: false,
    notes: "",
    filter_slots: [],
    guiding_mode: "none",
  };
}

function rigToForm(r: Rig): FormState {
  let guidingMode: GuidingMode = "none";
  if (r.oag_id) guidingMode = "oag";
  else if (r.guide_scope_id) guidingMode = "guide_scope";

  return {
    name: r.name,
    description: r.description ?? "",
    telescope_configuration_id: r.telescope_configuration_id,
    camera_id: r.camera_id,
    filter_wheel_id: r.filter_wheel_id,
    single_filter_id: r.single_filter_id,
    mount_id: r.mount_id,
    focuser_id: r.focuser_id,
    oag_id: r.oag_id,
    guide_scope_id: r.guide_scope_id,
    guide_camera_id: r.guide_camera_id,
    computer_id: r.computer_id,
    software_id: r.software_id,
    is_default: r.is_default,
    notes: r.notes ?? "",
    filter_slots: r.filter_slots.map((s) => ({
      slot_number: s.slot_number,
      filter_id: s.filter_id,
    })),
    guiding_mode: guidingMode,
  };
}

function formatSimple(o: SimpleOption): string {
  return `${o.manufacturer_name} \u2014 ${o.model_name}`;
}

// ── Component ──────────────────────────────────────────────────────────────

export default function RigFormDialog({
  open,
  rig,
  onClose,
  onSaved,
}: RigFormDialogProps) {
  const [form, setForm] = useState<FormState>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Partial<Record<string, string>>>({});
  const [snack, setSnack] = useState<{
    open: boolean;
    message: string;
    severity: "success" | "error";
  }>({ open: false, message: "", severity: "error" });

  const { data: options } = useQuery({
    queryKey: ["equipment-options"],
    queryFn: fetchEquipmentOptions,
    enabled: open,
  });

  // Reset form when dialog opens
  useEffect(() => {
    if (open) {
      setForm(rig ? rigToForm(rig) : emptyForm());
      setErrors({});
    }
  }, [open, rig]);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  // ── Derived option lists ───────────────────────────────────────────────

  const telescopeConfigOptions: FlatConfigOption[] = useMemo(
    () =>
      options?.telescopes.flatMap((t) =>
        t.configs.map((c) => ({
          ...c,
          telescope_name: t.telescope_name,
          manufacturer_name: t.manufacturer_name,
          aperture_mm: t.aperture_mm,
          telescope_id: t.telescope_id,
        })),
      ) ?? [],
    [options?.telescopes],
  );

  // ── Selected items for preview ─────────────────────────────────────────

  const selectedConfig = telescopeConfigOptions.find(
    (c) => c.id === form.telescope_configuration_id,
  );
  const selectedCamera = options?.cameras.find(
    (c) => c.id === form.camera_id,
  );
  const selectedFilterWheel = options?.filter_wheels.find(
    (w) => w.id === form.filter_wheel_id,
  );

  // ── Calculator preview ─────────────────────────────────────────────────

  const preview = useMemo(() => {
    if (!selectedConfig || !selectedCamera) return null;

    const imageScale =
      (selectedCamera.pixel_size_um /
        selectedConfig.effective_focal_length_mm) *
      ARCSEC_PER_UM_PER_MM;

    let fovW: number | null = null;
    let fovH: number | null = null;
    if (selectedCamera.sensor_width_mm && selectedCamera.sensor_height_mm) {
      fovW =
        ((selectedCamera.sensor_width_mm /
          selectedConfig.effective_focal_length_mm) *
          180 *
          60) /
        Math.PI;
      fovH =
        ((selectedCamera.sensor_height_mm /
          selectedConfig.effective_focal_length_mm) *
          180 *
          60) /
        Math.PI;
    }

    return {
      imageScale,
      fovW,
      fovH,
      focalRatio: selectedConfig.effective_focal_ratio,
    };
  }, [selectedConfig, selectedCamera]);

  // ── Save ───────────────────────────────────────────────────────────────

  const handleSave = async () => {
    const newErrors: Partial<Record<string, string>> = {};
    if (!form.name.trim()) newErrors.name = "Required";
    if (!form.telescope_configuration_id)
      newErrors.telescope_configuration_id = "Required";
    if (!form.camera_id) newErrors.camera_id = "Required";
    setErrors(newErrors);
    if (Object.keys(newErrors).length > 0) return;

    setSaving(true);
    try {
      const payload: RigCreate = {
        name: form.name.trim(),
        description: form.description.trim() || null,
        telescope_configuration_id: form.telescope_configuration_id!,
        camera_id: form.camera_id!,
        filter_wheel_id: form.filter_wheel_id,
        single_filter_id: form.filter_wheel_id
          ? null
          : form.single_filter_id,
        mount_id: form.mount_id,
        focuser_id: form.focuser_id,
        oag_id: form.guiding_mode === "oag" ? form.oag_id : null,
        guide_scope_id:
          form.guiding_mode === "guide_scope" ? form.guide_scope_id : null,
        guide_camera_id:
          form.guiding_mode !== "none" ? form.guide_camera_id : null,
        computer_id: form.computer_id,
        software_id: form.software_id,
        is_default: form.is_default,
        notes: form.notes.trim() || null,
        filter_slots: form.filter_wheel_id ? form.filter_slots : [],
      };

      if (rig) {
        await updateRig(rig.id, payload);
      } else {
        await createRig(payload);
      }
      onSaved();
      onClose();
    } catch (err) {
      setSnack({
        open: true,
        message: err instanceof Error ? err.message : String(err),
        severity: "error",
      });
    } finally {
      setSaving(false);
    }
  };

  const isEdit = rig !== null;

  return (
    <>
      <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
        <DialogTitle>{isEdit ? "Edit Rig" : "New Rig"}</DialogTitle>

        <DialogContent>
          <Box
            sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 1 }}
          >
            {/* ── Identity ──────────────────────────────────────────── */}
            <Typography variant="subtitle2" color="text.secondary">
              Identity
            </Typography>
            <TextField
              label="Name"
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
              required
              error={Boolean(errors.name)}
              helperText={errors.name}
            />
            <TextField
              label="Description"
              value={form.description}
              onChange={(e) => set("description", e.target.value)}
            />

            {/* ── Optical Train ──────────────────────────────────────── */}
            <Typography variant="subtitle2" color="text.secondary" sx={{ mt: 1 }}>
              Optical Train
            </Typography>
            <Autocomplete
              options={telescopeConfigOptions}
              groupBy={(o) =>
                `${o.manufacturer_name} ${o.telescope_name}`
              }
              getOptionLabel={(o: FlatConfigOption) =>
                `${o.manufacturer_name} ${o.telescope_name} \u2014 ${o.config_name} (${o.effective_focal_length_mm}mm f/${o.effective_focal_ratio})`
              }
              value={
                telescopeConfigOptions.find(
                  (c) => c.id === form.telescope_configuration_id,
                ) ?? null
              }
              onChange={(_e, value) =>
                set(
                  "telescope_configuration_id",
                  value ? value.id : null,
                )
              }
              isOptionEqualToValue={(opt, val) => opt.id === val.id}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label="OTA Configuration"
                  required
                  error={Boolean(errors.telescope_configuration_id)}
                  helperText={errors.telescope_configuration_id}
                />
              )}
            />
            <Autocomplete<CameraOption>
              options={options?.cameras ?? []}
              getOptionLabel={(o) =>
                `${o.manufacturer_name} \u2014 ${o.model_name} (${o.sensor_type})`
              }
              value={
                options?.cameras.find(
                  (c) => c.id === form.camera_id,
                ) ?? null
              }
              onChange={(_e, value) =>
                set("camera_id", value ? value.id : null)
              }
              isOptionEqualToValue={(opt, val) => opt.id === val.id}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label="Imaging Camera"
                  required
                  error={Boolean(errors.camera_id)}
                  helperText={errors.camera_id}
                />
              )}
            />

            {/* ── Calculator Preview ────────────────────────────────── */}
            {preview && (
              <Paper
                variant="outlined"
                sx={{
                  p: 1.5,
                  display: "flex",
                  gap: 3,
                  flexWrap: "wrap",
                  bgcolor: "action.hover",
                }}
              >
                <Typography variant="body2">
                  Image Scale:{" "}
                  <strong>{preview.imageScale.toFixed(2)}{"\u2033"}/pixel</strong>
                </Typography>
                {preview.fovW != null && preview.fovH != null && (
                  <Typography variant="body2">
                    FOV:{" "}
                    <strong>
                      {preview.fovW.toFixed(1)}{"\u2032"} {"\u00d7"}{" "}
                      {preview.fovH.toFixed(1)}{"\u2032"}
                    </strong>
                  </Typography>
                )}
                <Typography variant="body2">
                  Focal Ratio: <strong>f/{preview.focalRatio}</strong>
                </Typography>
              </Paper>
            )}

            {/* ── Filtration ────────────────────────────────────────── */}
            <Typography variant="subtitle2" color="text.secondary" sx={{ mt: 1 }}>
              Filtration
            </Typography>
            <Autocomplete<FilterWheelOption>
              options={options?.filter_wheels ?? []}
              getOptionLabel={(o) =>
                `${o.manufacturer_name} \u2014 ${o.model_name} (${o.num_positions}-pos)`
              }
              value={
                options?.filter_wheels.find(
                  (w) => w.id === form.filter_wheel_id,
                ) ?? null
              }
              onChange={(_e, value) => {
                set("filter_wheel_id", value ? value.id : null);
                if (!value) {
                  set("filter_slots", []);
                }
              }}
              isOptionEqualToValue={(opt, val) => opt.id === val.id}
              renderInput={(params) => (
                <TextField {...params} label="Filter Wheel" />
              )}
            />

            {selectedFilterWheel && (
              <FilterSlotGrid
                numPositions={selectedFilterWheel.num_positions}
                filters={options?.filters ?? []}
                slots={form.filter_slots}
                onChange={(slots) => set("filter_slots", slots)}
              />
            )}

            {!form.filter_wheel_id && (
              <Autocomplete<FilterOption>
                options={options?.filters ?? []}
                getOptionLabel={(o) =>
                  `${o.manufacturer_name} \u2014 ${o.model_name}`
                }
                value={
                  options?.filters.find(
                    (f) => f.id === form.single_filter_id,
                  ) ?? null
                }
                onChange={(_e, value) =>
                  set("single_filter_id", value ? value.id : null)
                }
                isOptionEqualToValue={(opt, val) => opt.id === val.id}
                renderInput={(params) => (
                  <TextField {...params} label="Single Filter" />
                )}
              />
            )}

            {/* ── Mount & Guiding ───────────────────────────────────── */}
            <Typography variant="subtitle2" color="text.secondary" sx={{ mt: 1 }}>
              Mount & Guiding
            </Typography>
            <Autocomplete<SimpleOption>
              options={options?.mounts ?? []}
              getOptionLabel={formatSimple}
              value={
                options?.mounts.find(
                  (m) => m.id === form.mount_id,
                ) ?? null
              }
              onChange={(_e, value) =>
                set("mount_id", value ? value.id : null)
              }
              isOptionEqualToValue={(opt, val) => opt.id === val.id}
              renderInput={(params) => (
                <TextField {...params} label="Mount" />
              )}
            />

            <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
              <Typography variant="body2" sx={{ flexShrink: 0 }}>
                Guiding Mode:
              </Typography>
              <ToggleButtonGroup
                value={form.guiding_mode}
                exclusive
                onChange={(_e, val) => {
                  if (val !== null) set("guiding_mode", val as GuidingMode);
                }}
                size="small"
              >
                <ToggleButton value="none">None</ToggleButton>
                <ToggleButton value="oag">OAG</ToggleButton>
                <ToggleButton value="guide_scope">Guide Scope</ToggleButton>
              </ToggleButtonGroup>
            </Box>

            {form.guiding_mode === "oag" && (
              <Autocomplete<SimpleOption>
                options={options?.oags ?? []}
                getOptionLabel={formatSimple}
                value={
                  options?.oags.find(
                    (o) => o.id === form.oag_id,
                  ) ?? null
                }
                onChange={(_e, value) =>
                  set("oag_id", value ? value.id : null)
                }
                isOptionEqualToValue={(opt, val) => opt.id === val.id}
                renderInput={(params) => (
                  <TextField {...params} label="OAG" />
                )}
              />
            )}

            {form.guiding_mode === "guide_scope" && (
              <Autocomplete<GuideScopeOption>
                options={options?.guide_scopes ?? []}
                getOptionLabel={formatSimple}
                value={
                  options?.guide_scopes.find(
                    (g) => g.id === form.guide_scope_id,
                  ) ?? null
                }
                onChange={(_e, value) =>
                  set("guide_scope_id", value ? value.id : null)
                }
                isOptionEqualToValue={(opt, val) => opt.id === val.id}
                renderInput={(params) => (
                  <TextField {...params} label="Guide Scope" />
                )}
              />
            )}

            {form.guiding_mode !== "none" && (
              <Autocomplete<CameraOption>
                options={options?.cameras ?? []}
                getOptionLabel={(o) =>
                  `${o.manufacturer_name} \u2014 ${o.model_name} (${o.sensor_type})`
                }
                value={
                  options?.cameras.find(
                    (c) => c.id === form.guide_camera_id,
                  ) ?? null
                }
                onChange={(_e, value) =>
                  set("guide_camera_id", value ? value.id : null)
                }
                isOptionEqualToValue={(opt, val) => opt.id === val.id}
                renderInput={(params) => (
                  <TextField {...params} label="Guide Camera" />
                )}
              />
            )}

            {/* ── Peripherals ───────────────────────────────────────── */}
            <Typography variant="subtitle2" color="text.secondary" sx={{ mt: 1 }}>
              Peripherals
            </Typography>
            <Autocomplete<SimpleOption>
              options={options?.focusers ?? []}
              getOptionLabel={formatSimple}
              value={
                options?.focusers.find(
                  (f) => f.id === form.focuser_id,
                ) ?? null
              }
              onChange={(_e, value) =>
                set("focuser_id", value ? value.id : null)
              }
              isOptionEqualToValue={(opt, val) => opt.id === val.id}
              renderInput={(params) => (
                <TextField {...params} label="Focuser" />
              )}
            />
            <Autocomplete<SimpleOption>
              options={options?.computers ?? []}
              getOptionLabel={formatSimple}
              value={
                options?.computers.find(
                  (c) => c.id === form.computer_id,
                ) ?? null
              }
              onChange={(_e, value) =>
                set("computer_id", value ? value.id : null)
              }
              isOptionEqualToValue={(opt, val) => opt.id === val.id}
              renderInput={(params) => (
                <TextField {...params} label="Computer" />
              )}
            />
            <Autocomplete<SoftwareOption>
              options={options?.software ?? []}
              getOptionLabel={(o) => `${o.name} (${o.category})`}
              value={
                options?.software.find(
                  (s) => s.id === form.software_id,
                ) ?? null
              }
              onChange={(_e, value) =>
                set("software_id", value ? value.id : null)
              }
              isOptionEqualToValue={(opt, val) => opt.id === val.id}
              renderInput={(params) => (
                <TextField {...params} label="Software" />
              )}
            />

            {/* ── Options ───────────────────────────────────────────── */}
            <Typography variant="subtitle2" color="text.secondary" sx={{ mt: 1 }}>
              Options
            </Typography>
            <FormControlLabel
              control={
                <Switch
                  checked={form.is_default}
                  onChange={(e) => set("is_default", e.target.checked)}
                />
              }
              label="Default Rig"
            />
            <TextField
              label="Notes"
              value={form.notes}
              onChange={(e) => set("notes", e.target.value)}
              multiline
              rows={2}
            />
          </Box>
        </DialogContent>

        <DialogActions>
          <Button onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={handleSave} variant="contained" disabled={saving}>
            {saving ? "Saving\u2026" : "Save"}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={snack.open}
        autoHideDuration={4000}
        onClose={() => setSnack((s) => ({ ...s, open: false }))}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert
          severity={snack.severity}
          onClose={() => setSnack((s) => ({ ...s, open: false }))}
        >
          {snack.message}
        </Alert>
      </Snackbar>
    </>
  );
}
