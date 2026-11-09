import { useState, useEffect, useMemo, useRef } from "react";
import type { HTMLAttributes, Key, ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Autocomplete from "@mui/material/Autocomplete";
import StarIcon from "@mui/icons-material/Star";
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
import RigChangePrompt from "@/components/rigs/RigChangePrompt";
import { withMineGroup } from "@/components/rigs/mineGroup";
import { orderSoftwareOptions } from "@/components/shared/softwareOrder";
import {
  keepRetiredSelected,
  retainedGroup,
  retainedLabel,
  type RetainedOption,
} from "@/components/rigs/retainedOptions";
import { ApiError } from "@/api/client";
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
  type RigChangeChoiceDetail,
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
  software_ids: number[];
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
  is_mine: boolean;
  __mine_group?: string;
}

type GroupedRetained<T> = RetainedOption<T> & { __mine_group?: string };

function OptionListItem({
  optionProps,
  children,
}: {
  optionProps: HTMLAttributes<HTMLLIElement> & { key?: Key };
  children: ReactNode;
}) {
  const { key, ...props } = optionProps;
  return <li key={key} {...props}>{children}</li>;
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
    software_ids: [],
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
    software_ids: r.software.map((s) => s.id),
    is_default: r.is_default,
    notes: r.notes ?? "",
    filter_slots: r.filter_slots.map((s) => ({
      slot_number: s.slot_number,
      filter_id: s.filter_id,
    })),
    guiding_mode: guidingMode,
  };
}

function formatSimple(o: RetainedOption<SimpleOption>): string {
  return retainedLabel(o, `${o.manufacturer_name} \u2014 ${o.model_name}`, o.model_name);
}

function equipmentGroup(o: { retired?: true; __mine_group?: string; manufacturer_name: string }) {
  return retainedGroup(o, o.__mine_group ?? o.manufacturer_name);
}

function cameraLabel(o: RetainedOption<CameraOption>): string {
  return retainedLabel(
    o,
    `${o.manufacturer_name} \u2014 ${o.model_name} (${o.sensor_type})`,
    o.model_name,
  );
}

function filterLabel(o: RetainedOption<FilterOption>): string {
  return retainedLabel(o, `${o.manufacturer_name} \u2014 ${o.model_name}`, o.model_name);
}

function wheelLabel(o: RetainedOption<FilterWheelOption>): string {
  return retainedLabel(
    o,
    `${o.manufacturer_name} \u2014 ${o.model_name} (${o.num_positions}-pos)`,
    o.model_name,
  );
}

function retainedSimpleOptions(
  active: SimpleOption[],
  selectedId: number | null,
  rigId: number | null,
  name: string | null,
): RetainedOption<SimpleOption>[] {
  return keepRetiredSelected(active, [selectedId], (id) => (
    id === rigId && name
      ? { id, model_name: name, manufacturer_name: "", is_mine: false }
      : null
  ));
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
  const [pendingChange, setPendingChange] = useState<{
    detail: RigChangeChoiceDetail;
    payload: RigCreate;
  } | null>(null);
  const saveButtonRef = useRef<HTMLButtonElement>(null);
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
      setPendingChange(null);
    }
  }, [open, rig]);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  // ── Derived option lists ───────────────────────────────────────────────

  const telescopeConfigOptions = useMemo<RetainedOption<FlatConfigOption>[]>(
    () => {
      const active = options?.telescopes.flatMap((t) =>
        t.configs.map((c) => ({
          ...c,
          telescope_name: t.telescope_name,
          manufacturer_name: t.manufacturer_name,
          aperture_mm: t.aperture_mm,
          telescope_id: t.telescope_id,
          is_mine: t.is_mine,
        })),
      ) ?? [];
      return keepRetiredSelected(active, [form.telescope_configuration_id], (id) => {
        if (!rig || rig.telescope_configuration_id !== id) return null;
        return {
          id,
          config_name: rig.telescope_config_name,
          effective_focal_length_mm: rig.effective_focal_length_mm,
          effective_focal_ratio: rig.effective_focal_ratio,
          effective_image_circle_mm: null,
          telescope_name: rig.telescope_name,
          manufacturer_name: "",
          aperture_mm: rig.aperture_mm,
          telescope_id: rig.telescope_id,
          is_mine: false,
        };
      });
    },
    [options?.telescopes, rig, form.telescope_configuration_id],
  );

  const cameraOptions = useMemo(
    () => keepRetiredSelected(
      options?.cameras ?? [],
      [form.camera_id, form.guide_camera_id],
      (id) => {
        if (!rig || (rig.camera_id !== id && rig.guide_camera_id !== id)) return null;
        const isImagingCamera = rig.camera_id === id;
        const name = isImagingCamera ? rig.camera_name : rig.guide_camera_name;
        if (!name) return null;
        return {
          id,
          model_name: name,
          manufacturer_name: "",
          pixel_size_um: isImagingCamera ? rig.pixel_size_um : 0,
          resolution_x: isImagingCamera ? rig.sensor_resolution_x : 0,
          resolution_y: isImagingCamera ? rig.sensor_resolution_y : 0,
          sensor_width_mm: isImagingCamera ? rig.sensor_width_mm : null,
          sensor_height_mm: isImagingCamera ? rig.sensor_height_mm : null,
          sensor_type: isImagingCamera ? rig.sensor_type : "",
          is_mine: false,
        };
      },
    ),
    [options?.cameras, rig, form.camera_id, form.guide_camera_id],
  );

  const filterWheelOptions = useMemo(
    () => keepRetiredSelected(options?.filter_wheels ?? [], [form.filter_wheel_id], (id) => {
      if (!rig || rig.filter_wheel_id !== id || !rig.filter_wheel_name) return null;
      return {
        id,
        model_name: rig.filter_wheel_name,
        manufacturer_name: "",
        num_positions: rig.filter_wheel_positions
          ?? Math.max(1, ...rig.filter_slots.map((slot) => slot.slot_number)),
        is_mine: false,
      };
    }),
    [options?.filter_wheels, rig, form.filter_wheel_id],
  );

  const selectedFilterIds = useMemo(
    () => [form.single_filter_id, ...form.filter_slots.map((slot) => slot.filter_id)],
    [form.single_filter_id, form.filter_slots],
  );
  const filterOptions = useMemo(
    () => keepRetiredSelected(options?.filters ?? [], selectedFilterIds, (id) => {
      if (!rig) return null;
      const name = rig.single_filter_id === id
        ? rig.single_filter_name
        : rig.filter_slots.find((slot) => slot.filter_id === id)?.filter_name;
      if (!name) return null;
      return {
        id,
        model_name: name,
        manufacturer_name: "",
        filter_type_name: "",
        is_mine: false,
      };
    }),
    [options?.filters, rig, selectedFilterIds],
  );

  const mountOptions = useMemo(
    () => retainedSimpleOptions(options?.mounts ?? [], form.mount_id, rig?.mount_id ?? null, rig?.mount_name ?? null),
    [options?.mounts, form.mount_id, rig],
  );
  const focuserOptions = useMemo(
    () => retainedSimpleOptions(options?.focusers ?? [], form.focuser_id, rig?.focuser_id ?? null, rig?.focuser_name ?? null),
    [options?.focusers, form.focuser_id, rig],
  );
  const oagOptions = useMemo(
    () => retainedSimpleOptions(options?.oags ?? [], form.oag_id, rig?.oag_id ?? null, rig?.oag_name ?? null),
    [options?.oags, form.oag_id, rig],
  );
  const computerOptions = useMemo(
    () => retainedSimpleOptions(options?.computers ?? [], form.computer_id, rig?.computer_id ?? null, rig?.computer_name ?? null),
    [options?.computers, form.computer_id, rig],
  );
  const guideScopeOptions = useMemo(
    () => keepRetiredSelected(options?.guide_scopes ?? [], [form.guide_scope_id], (id) => {
      if (!rig || rig.guide_scope_id !== id || !rig.guide_scope_name) return null;
      return {
        id,
        model_name: rig.guide_scope_name,
        manufacturer_name: "",
        focal_length_mm: rig.guide_scope_focal_length_mm,
        is_mine: false,
      };
    }),
    [options?.guide_scopes, form.guide_scope_id, rig],
  );

  const orderedSoftware = useMemo(
    () => orderSoftwareOptions(
      keepRetiredSelected(options?.software ?? [], form.software_ids, (id) => {
        const item = rig?.software.find((software) => software.id === id);
        return item ? { ...item, is_mine: false } : null;
      }),
      "rig",
    ),
    [options?.software, form.software_ids, rig],
  );

  // ── Selected items for preview ─────────────────────────────────────────

  const selectedConfig = telescopeConfigOptions.find(
    (c) => c.id === form.telescope_configuration_id,
  );
  const selectedCamera = cameraOptions.find(
    (c) => c.id === form.camera_id,
  );
  const selectedFilterWheel = filterWheelOptions.find(
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

    const payload: RigCreate = {
      name: form.name.trim(),
      description: form.description.trim() || null,
      telescope_configuration_id: form.telescope_configuration_id!,
      camera_id: form.camera_id!,
      filter_wheel_id: form.filter_wheel_id,
      single_filter_id: form.filter_wheel_id ? null : form.single_filter_id,
      mount_id: form.mount_id,
      focuser_id: form.focuser_id,
      oag_id: form.guiding_mode === "oag" ? form.oag_id : null,
      guide_scope_id:
        form.guiding_mode === "guide_scope" ? form.guide_scope_id : null,
      guide_camera_id:
        form.guiding_mode !== "none" ? form.guide_camera_id : null,
      computer_id: form.computer_id,
      software_ids: form.software_ids,
      is_default: form.is_default,
      notes: form.notes.trim() || null,
      filter_slots: form.filter_wheel_id ? form.filter_slots : [],
    };

    setSaving(true);
    try {
      if (rig) await updateRig(rig.id, payload);
      else await createRig(payload);
      onSaved();
      onClose();
    } catch (err) {
      if (
        rig &&
        err instanceof ApiError &&
        err.status === 409 &&
        typeof err.detail === "object" &&
        err.detail !== null &&
        (err.detail as { code?: string }).code === "rig_change_needs_choice"
      ) {
        setPendingChange({
          detail: err.detail as RigChangeChoiceDetail,
          payload,
        });
        return;
      }
      setSnack({
        open: true,
        message: err instanceof Error ? err.message : String(err),
        severity: "error",
      });
    } finally {
      setSaving(false);
    }
  };

  const handleChoice = async (mode: "existing" | "from_now_on") => {
    if (!rig || !pendingChange) return;
    setSaving(true);
    try {
      await updateRig(rig.id, pendingChange.payload, mode);
      setPendingChange(null);
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

  const cancelChoice = () => {
    setPendingChange(null);
    requestAnimationFrame(() => saveButtonRef.current?.focus());
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
              options={withMineGroup(telescopeConfigOptions)}
              groupBy={(o) =>
                retainedGroup(o, o.__mine_group ?? `${o.manufacturer_name} ${o.telescope_name}`)
              }
              getOptionLabel={(o) => retainedLabel(
                o,
                `${o.manufacturer_name} ${o.telescope_name} \u2014 ${o.config_name} (${o.effective_focal_length_mm}mm f/${o.effective_focal_ratio})`,
                `${o.telescope_name} \u2014 ${o.config_name}`,
              )}
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
              renderOption={(props, option) => (
                <OptionListItem optionProps={props}>
                  {option.is_mine && (
                    <StarIcon fontSize="small" color="primary" sx={{ mr: 0.75 }} />
                  )}
                  {retainedLabel(
                    option,
                    `${option.manufacturer_name} ${option.telescope_name} \u2014 ${option.config_name} (${option.effective_focal_length_mm}mm f/${option.effective_focal_ratio})`,
                    `${option.telescope_name} \u2014 ${option.config_name}`,
                  )}
                </OptionListItem>
              )}
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
            <Autocomplete<GroupedRetained<CameraOption>>
              options={withMineGroup(cameraOptions)}
              groupBy={equipmentGroup}
              getOptionLabel={cameraLabel}
              value={
                cameraOptions.find(
                  (c) => c.id === form.camera_id,
                ) ?? null
              }
              onChange={(_e, value) =>
                set("camera_id", value ? value.id : null)
              }
              isOptionEqualToValue={(opt, val) => opt.id === val.id}
              renderOption={(props, option) => (
                <OptionListItem optionProps={props}>
                  {option.is_mine && (
                    <StarIcon fontSize="small" color="primary" sx={{ mr: 0.75 }} />
                  )}
                  {cameraLabel(option)}
                </OptionListItem>
              )}
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
            <Autocomplete<GroupedRetained<FilterWheelOption>>
              options={withMineGroup(filterWheelOptions)}
              groupBy={equipmentGroup}
              getOptionLabel={wheelLabel}
              value={
                filterWheelOptions.find(
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
              renderOption={(props, option) => (
                <OptionListItem optionProps={props}>
                  {option.is_mine && (
                    <StarIcon fontSize="small" color="primary" sx={{ mr: 0.75 }} />
                  )}
                  {wheelLabel(option)}
                </OptionListItem>
              )}
              renderInput={(params) => (
                <TextField {...params} label="Filter Wheel" />
              )}
            />

            {selectedFilterWheel && (
              <FilterSlotGrid
                numPositions={selectedFilterWheel.num_positions}
                filters={filterOptions}
                slots={form.filter_slots}
                onChange={(slots) => set("filter_slots", slots)}
              />
            )}

            {!form.filter_wheel_id && (
              <Autocomplete<GroupedRetained<FilterOption>>
                options={withMineGroup(filterOptions)}
                groupBy={equipmentGroup}
                getOptionLabel={filterLabel}
                value={
                  filterOptions.find(
                    (f) => f.id === form.single_filter_id,
                  ) ?? null
                }
                onChange={(_e, value) =>
                  set("single_filter_id", value ? value.id : null)
                }
                isOptionEqualToValue={(opt, val) => opt.id === val.id}
                renderOption={(props, option) => (
                  <OptionListItem optionProps={props}>
                    {option.is_mine && (
                      <StarIcon fontSize="small" color="primary" sx={{ mr: 0.75 }} />
                    )}
                    {filterLabel(option)}
                  </OptionListItem>
                )}
                renderInput={(params) => (
                  <TextField {...params} label="Single Filter" />
                )}
              />
            )}

            {/* ── Mount & Guiding ───────────────────────────────────── */}
            <Typography variant="subtitle2" color="text.secondary" sx={{ mt: 1 }}>
              Mount & Guiding
            </Typography>
            <Autocomplete<GroupedRetained<SimpleOption>>
              options={withMineGroup(mountOptions)}
              groupBy={equipmentGroup}
              getOptionLabel={formatSimple}
              value={
                mountOptions.find(
                  (m) => m.id === form.mount_id,
                ) ?? null
              }
              onChange={(_e, value) =>
                set("mount_id", value ? value.id : null)
              }
              isOptionEqualToValue={(opt, val) => opt.id === val.id}
              renderOption={(props, option) => (
                <OptionListItem optionProps={props}>
                  {option.is_mine && (
                    <StarIcon fontSize="small" color="primary" sx={{ mr: 0.75 }} />
                  )}
                  {formatSimple(option)}
                </OptionListItem>
              )}
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
              <Autocomplete<GroupedRetained<SimpleOption>>
                options={withMineGroup(oagOptions)}
                groupBy={equipmentGroup}
                getOptionLabel={formatSimple}
                value={
                  oagOptions.find(
                    (o) => o.id === form.oag_id,
                  ) ?? null
                }
                onChange={(_e, value) =>
                  set("oag_id", value ? value.id : null)
                }
                isOptionEqualToValue={(opt, val) => opt.id === val.id}
                renderOption={(props, option) => (
                  <OptionListItem optionProps={props}>
                    {option.is_mine && (
                      <StarIcon fontSize="small" color="primary" sx={{ mr: 0.75 }} />
                    )}
                    {formatSimple(option)}
                  </OptionListItem>
                )}
                renderInput={(params) => (
                  <TextField {...params} label="OAG" />
                )}
              />
            )}

            {form.guiding_mode === "guide_scope" && (
              <Autocomplete<GroupedRetained<GuideScopeOption>>
                options={withMineGroup(guideScopeOptions)}
                groupBy={equipmentGroup}
                getOptionLabel={formatSimple}
                value={
                  guideScopeOptions.find(
                    (g) => g.id === form.guide_scope_id,
                  ) ?? null
                }
                onChange={(_e, value) =>
                  set("guide_scope_id", value ? value.id : null)
                }
                isOptionEqualToValue={(opt, val) => opt.id === val.id}
                renderOption={(props, option) => (
                  <OptionListItem optionProps={props}>
                    {option.is_mine && (
                      <StarIcon fontSize="small" color="primary" sx={{ mr: 0.75 }} />
                    )}
                    {formatSimple(option)}
                  </OptionListItem>
                )}
                renderInput={(params) => (
                  <TextField {...params} label="Guide Scope" />
                )}
              />
            )}

            {form.guiding_mode !== "none" && (
              <Autocomplete<GroupedRetained<CameraOption>>
                options={withMineGroup(cameraOptions)}
                groupBy={equipmentGroup}
                getOptionLabel={cameraLabel}
                value={
                  cameraOptions.find(
                    (c) => c.id === form.guide_camera_id,
                  ) ?? null
                }
                onChange={(_e, value) =>
                  set("guide_camera_id", value ? value.id : null)
                }
                isOptionEqualToValue={(opt, val) => opt.id === val.id}
                renderOption={(props, option) => (
                  <OptionListItem optionProps={props}>
                    {option.is_mine && (
                      <StarIcon fontSize="small" color="primary" sx={{ mr: 0.75 }} />
                    )}
                    {cameraLabel(option)}
                  </OptionListItem>
                )}
                renderInput={(params) => (
                  <TextField {...params} label="Guide Camera" />
                )}
              />
            )}

            {/* ── Peripherals ───────────────────────────────────────── */}
            <Typography variant="subtitle2" color="text.secondary" sx={{ mt: 1 }}>
              Peripherals
            </Typography>
            <Autocomplete<GroupedRetained<SimpleOption>>
              options={withMineGroup(focuserOptions)}
              groupBy={equipmentGroup}
              getOptionLabel={formatSimple}
              value={
                focuserOptions.find(
                  (f) => f.id === form.focuser_id,
                ) ?? null
              }
              onChange={(_e, value) =>
                set("focuser_id", value ? value.id : null)
              }
              isOptionEqualToValue={(opt, val) => opt.id === val.id}
              renderOption={(props, option) => (
                <OptionListItem optionProps={props}>
                  {option.is_mine && (
                    <StarIcon fontSize="small" color="primary" sx={{ mr: 0.75 }} />
                  )}
                  {formatSimple(option)}
                </OptionListItem>
              )}
              renderInput={(params) => (
                <TextField {...params} label="Focuser" />
              )}
            />
            <Autocomplete<GroupedRetained<SimpleOption>>
              options={withMineGroup(computerOptions)}
              groupBy={equipmentGroup}
              getOptionLabel={formatSimple}
              value={
                computerOptions.find(
                  (c) => c.id === form.computer_id,
                ) ?? null
              }
              onChange={(_e, value) =>
                set("computer_id", value ? value.id : null)
              }
              isOptionEqualToValue={(opt, val) => opt.id === val.id}
              renderOption={(props, option) => (
                <OptionListItem optionProps={props}>
                  {option.is_mine && (
                    <StarIcon fontSize="small" color="primary" sx={{ mr: 0.75 }} />
                  )}
                  {formatSimple(option)}
                </OptionListItem>
              )}
              renderInput={(params) => (
                <TextField {...params} label="Computer" />
              )}
            />
            <Autocomplete<RetainedOption<SoftwareOption>, true>
              multiple
              options={orderedSoftware}
              groupBy={(o) =>
                o.category.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase())
              }
              getOptionLabel={(o) => retainedLabel(o, o.name, o.name)}
              value={
                orderedSoftware.filter((s) =>
                  form.software_ids.includes(s.id),
                ) ?? []
              }
              onChange={(_e, values) =>
                set(
                  "software_ids",
                  values.map((v) => v.id),
                )
              }
              isOptionEqualToValue={(opt, val) => opt.id === val.id}
              renderOption={(props, option) => (
                <OptionListItem optionProps={props}>
                  {option.is_mine && (
                    <StarIcon fontSize="small" color="primary" sx={{ mr: 0.75 }} />
                  )}
                  {retainedLabel(option, option.name, option.name)}
                </OptionListItem>
              )}
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
          <Button
            ref={saveButtonRef}
            onClick={handleSave}
            variant="contained"
            disabled={saving}
          >
            {saving ? "Saving\u2026" : "Save"}
          </Button>
        </DialogActions>
      </Dialog>

      {pendingChange && (
        <RigChangePrompt
          open
          detail={pendingChange.detail}
          saving={saving}
          onChoose={handleChoice}
          onCancel={cancelChoice}
        />
      )}

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
