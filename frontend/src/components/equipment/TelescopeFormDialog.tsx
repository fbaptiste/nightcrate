import { useState, useEffect } from "react";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Alert from "@mui/material/Alert";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import Snackbar from "@mui/material/Snackbar";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import StarIcon from "@mui/icons-material/Star";
import { useQuery } from "@tanstack/react-query";
import { parseOptionalFloat } from "@/lib/formUtils";
import ManufacturerPicker from "@/components/equipment/shared/ManufacturerPicker";
import LookupPicker from "@/components/equipment/shared/LookupPicker";
import {
  createTelescope,
  updateTelescope,
  createTelescopeConfig,
  updateTelescopeConfig,
  deleteTelescopeConfig,
  fetchOpticalDesigns,
  fetchConnectorSizes,
  type Telescope,
  type TelescopeConfiguration,
  type TelescopeCreate,
  type TelescopeConfigurationCreate,
  type ConnectorSize,
} from "@/api/equipment";

interface TelescopeFormDialogProps {
  open: boolean;
  telescope: Telescope | null;
  onClose: () => void;
  onSaved: () => void;
}

// A config entry in the form — may be new (no id) or existing
interface ConfigEntry {
  // undefined = new (not yet saved)
  id?: number;
  config_name: string;
  accessory_name: string;
  reduction_factor: string;
  effective_focal_length_mm: string;
  effective_focal_ratio: string;
  effective_image_circle_mm: string;
  effective_back_focus_mm: string;
  is_native: boolean;
  notes: string;
  // track whether this existing config has been modified
  dirty: boolean;
  // track whether this existing config should be deleted
  deleted: boolean;
}

interface FormState {
  model_name: string;
  manufacturer_id: number | null;
  optical_design_id: number | null;
  aperture_mm: string;
  image_circle_mm: string;
  weight_kg: string;
  obstruction_pct: string;
  notes: string;
  connector_size_ids: number[];
}

function emptyForm(): FormState {
  return {
    model_name: "",
    manufacturer_id: null,
    optical_design_id: null,
    aperture_mm: "",
    image_circle_mm: "",
    weight_kg: "",
    obstruction_pct: "",
    notes: "",
    connector_size_ids: [],
  };
}

function telescopeToForm(telescope: Telescope): FormState {
  return {
    model_name: telescope.model_name,
    manufacturer_id: telescope.manufacturer.id,
    optical_design_id: telescope.optical_design?.id ?? null,
    aperture_mm: String(telescope.aperture_mm),
    image_circle_mm: telescope.image_circle_mm != null ? String(telescope.image_circle_mm) : "",
    weight_kg: telescope.weight_kg != null ? String(telescope.weight_kg) : "",
    obstruction_pct: telescope.obstruction_pct != null ? String(telescope.obstruction_pct) : "",
    notes: telescope.notes ?? "",
    connector_size_ids: telescope.connectors.map((c) => c.id),
  };
}

function emptyConfig(): ConfigEntry {
  return {
    id: undefined,
    config_name: "",
    accessory_name: "",
    reduction_factor: "",
    effective_focal_length_mm: "",
    effective_focal_ratio: "",
    effective_image_circle_mm: "",
    effective_back_focus_mm: "",
    is_native: false,
    notes: "",
    dirty: false,
    deleted: false,
  };
}

function configToEntry(c: TelescopeConfiguration): ConfigEntry {
  return {
    id: c.id,
    config_name: c.config_name,
    accessory_name: c.accessory_name ?? "",
    reduction_factor: c.reduction_factor != null ? String(c.reduction_factor) : "",
    effective_focal_length_mm: String(c.effective_focal_length_mm),
    effective_focal_ratio: String(c.effective_focal_ratio),
    effective_image_circle_mm:
      c.effective_image_circle_mm != null ? String(c.effective_image_circle_mm) : "",
    effective_back_focus_mm:
      c.effective_back_focus_mm != null ? String(c.effective_back_focus_mm) : "",
    is_native: c.is_native,
    notes: c.notes ?? "",
    dirty: false,
    deleted: false,
  };
}


export default function TelescopeFormDialog({
  open,
  telescope,
  onClose,
  onSaved,
}: TelescopeFormDialogProps) {
  const [form, setForm] = useState<FormState>(emptyForm);
  const [configs, setConfigs] = useState<ConfigEntry[]>([emptyConfig()]);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Partial<Record<keyof FormState | "configs" | "native", string>>>({});
  const [snackOpen, setSnackOpen] = useState(false);
  const [snackMessage, setSnackMessage] = useState("");
  const [snackSeverity, setSnackSeverity] = useState<"info" | "error">("info");
  const [expandedIndex, setExpandedIndex] = useState<number | false>(0);

  const { data: connectorSizes = [] } = useQuery({
    queryKey: ["connector-sizes"],
    queryFn: () => fetchConnectorSizes(),
  });

  useEffect(() => {
    if (open) {
      if (telescope) {
        setForm(telescopeToForm(telescope));
        const entries = telescope.configurations.map(configToEntry);
        setConfigs(entries.length > 0 ? entries : [emptyConfig()]);
        setExpandedIndex(0);
      } else {
        setForm(emptyForm());
        setConfigs([emptyConfig()]);
        setExpandedIndex(0);
      }
      setErrors({});
    }
  }, [open, telescope]);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const setConfig = (index: number, patch: Partial<ConfigEntry>) => {
    setConfigs((prev) =>
      prev.map((c, i) => (i === index ? { ...c, ...patch, dirty: true } : c))
    );
  };

  const addConfig = () => {
    setConfigs((prev) => [...prev, emptyConfig()]);
    setExpandedIndex(configs.length);
  };

  const removeConfig = (index: number) => {
    setConfigs((prev) =>
      prev.map((c, i) => (i === index ? { ...c, deleted: true } : c))
    );
    if (expandedIndex === index) setExpandedIndex(false);
  };

  const validate = (): boolean => {
    const newErrors: typeof errors = {};
    if (!form.model_name.trim()) newErrors.model_name = "Model name is required";
    if (form.manufacturer_id == null) newErrors.manufacturer_id = "Manufacturer is required";
    if (!form.aperture_mm.trim() || isNaN(parseFloat(form.aperture_mm))) {
      newErrors.aperture_mm = "Aperture is required";
    }

    const activeConfigs = configs.filter((c) => !c.deleted);
    if (activeConfigs.length === 0) {
      newErrors.configs = "At least one configuration is required";
    } else {
      for (const c of activeConfigs) {
        if (!c.config_name.trim()) {
          newErrors.configs = "All configurations must have a name";
          break;
        }
        if (!c.effective_focal_length_mm.trim() || isNaN(parseFloat(c.effective_focal_length_mm))) {
          newErrors.configs = "All configurations must have effective focal length";
          break;
        }
        if (!c.effective_focal_ratio.trim() || isNaN(parseFloat(c.effective_focal_ratio))) {
          newErrors.configs = "All configurations must have effective focal ratio";
          break;
        }
      }
    }

    const hasNative = activeConfigs.some((c) => c.is_native);
    if (!hasNative && activeConfigs.length > 0 && !newErrors.configs) {
      newErrors.native = "Exactly one configuration must be marked as native";
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSave = async () => {
    if (!validate()) return;

    setSaving(true);
    try {
      const payload: TelescopeCreate = {
        model_name: form.model_name.trim(),
        manufacturer_id: form.manufacturer_id!,
        optical_design_id: form.optical_design_id,
        aperture_mm: parseFloat(form.aperture_mm),
        image_circle_mm: parseOptionalFloat(form.image_circle_mm),
        weight_kg: parseOptionalFloat(form.weight_kg),
        obstruction_pct: parseOptionalFloat(form.obstruction_pct),
        notes: form.notes.trim() || null,
        connector_size_ids: form.connector_size_ids,
      };

      let telescopeId: number;
      if (telescope) {
        await updateTelescope(telescope.id, payload);
        telescopeId = telescope.id;
      } else {
        const created = await createTelescope(payload);
        telescopeId = created.id;
      }

      // Process configurations
      for (const config of configs) {
        if (config.deleted) {
          if (config.id != null) {
            await deleteTelescopeConfig(telescopeId, config.id);
          }
          continue;
        }

        const configPayload: TelescopeConfigurationCreate = {
          telescope_id: telescopeId,
          config_name: config.config_name.trim(),
          accessory_name: config.accessory_name.trim() || null,
          reduction_factor: parseOptionalFloat(config.reduction_factor) ?? 1.0,
          effective_focal_length_mm: parseFloat(config.effective_focal_length_mm),
          effective_focal_ratio: parseFloat(config.effective_focal_ratio),
          effective_image_circle_mm: parseOptionalFloat(config.effective_image_circle_mm),
          effective_back_focus_mm: parseOptionalFloat(config.effective_back_focus_mm),
          is_native: config.is_native,
          notes: config.notes.trim() || null,
        };

        if (config.id == null) {
          // New config
          await createTelescopeConfig(telescopeId, configPayload);
        } else if (config.dirty) {
          // Modified existing config
          await updateTelescopeConfig(telescopeId, config.id, configPayload);
        }
      }

      setSnackMessage(isEdit ? "OTA updated." : "OTA added.");
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

  const isEdit = telescope !== null;

  // Visible (non-deleted) configs with their original indices
  const visibleConfigs = configs
    .map((c, i) => ({ config: c, index: i }))
    .filter(({ config }) => !config.deleted);

  const selectedConnectorSizeObjects = connectorSizes.filter((cs) =>
    form.connector_size_ids.includes(cs.id)
  );

  return (
    <>
      <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
        <DialogTitle>{isEdit ? "Edit OTA" : "Add OTA"}</DialogTitle>

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

            {/* Row 2: Optical design + Aperture */}
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2 }}>
              <LookupPicker
                fetchFn={fetchOpticalDesigns}
                queryKey="optical-designs"
                label="Optical Design"
                value={form.optical_design_id}
                onChange={(id) => set("optical_design_id", id)}
              />
              <TextField
                label="Aperture (mm)"
                type="number"
                value={form.aperture_mm}
                onChange={(e) => set("aperture_mm", e.target.value)}
                required
                error={Boolean(errors.aperture_mm)}
                helperText={errors.aperture_mm}
                slotProps={{ htmlInput: { step: "any", min: 0 } }}
              />
            </Box>

            {/* Row 3: Image circle + Weight + Obstruction */}
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 2 }}>
              <TextField
                label="Image Circle (mm)"
                type="number"
                value={form.image_circle_mm}
                onChange={(e) => set("image_circle_mm", e.target.value)}
                slotProps={{ htmlInput: { step: "any", min: 0 } }}
              />
              <TextField
                label="Weight (kg)"
                type="number"
                value={form.weight_kg}
                onChange={(e) => set("weight_kg", e.target.value)}
                slotProps={{ htmlInput: { step: "any", min: 0 } }}
              />
              <TextField
                label="Obstruction (%)"
                type="number"
                value={form.obstruction_pct}
                onChange={(e) => set("obstruction_pct", e.target.value)}
                slotProps={{ htmlInput: { step: "any", min: 0, max: 100 } }}
              />
            </Box>

            {/* Row 4: Connectors multi-select */}
            <Autocomplete
              multiple
              options={connectorSizes}
              value={selectedConnectorSizeObjects}
              onChange={(_event, values: ConnectorSize[]) =>
                set("connector_size_ids", values.map((v) => v.id))
              }
              getOptionLabel={(o) => o.name}
              isOptionEqualToValue={(option, value) => option.id === value.id}
              renderInput={(params) => <TextField {...params} label="Connectors" />}
            />

            {/* Row 5: Notes */}
            <TextField
              label="Notes"
              value={form.notes}
              onChange={(e) => set("notes", e.target.value)}
              multiline
              rows={2}
            />

            {/* Configurations section */}
            <Box>
              <Typography variant="subtitle1" sx={{ mb: 1, fontWeight: 600 }}>
                Configurations
              </Typography>

              {(errors.configs || errors.native) && (
                <Alert severity="warning" sx={{ mb: 1 }}>
                  {errors.configs ?? errors.native}
                </Alert>
              )}

              {visibleConfigs.length === 0 && (
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  No configurations yet. Add at least one.
                </Typography>
              )}

              {visibleConfigs.map(({ config, index }) => {
                const focalSummary =
                  config.effective_focal_length_mm && config.effective_focal_ratio
                    ? `${config.effective_focal_length_mm}mm f/${config.effective_focal_ratio}`
                    : "";
                const headerLabel = config.config_name || "New Configuration";

                return (
                  <Accordion
                    key={config.id ?? `new-${index}`}
                    expanded={expandedIndex === index}
                    onChange={(_e, isExpanded) =>
                      setExpandedIndex(isExpanded ? index : false)
                    }
                    sx={{ mb: 1 }}
                  >
                    <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                      <Box
                        sx={{
                          display: "flex",
                          alignItems: "center",
                          width: "100%",
                          gap: 1,
                        }}
                      >
                        {config.is_native && (
                          <StarIcon fontSize="small" color="primary" titleAccess="Native config" />
                        )}
                        <Typography sx={{ flex: 1 }}>
                          {headerLabel}
                          {focalSummary && (
                            <Typography
                              component="span"
                              variant="body2"
                              color="text.secondary"
                              sx={{ ml: 1 }}
                            >
                              {focalSummary}
                            </Typography>
                          )}
                        </Typography>
                        <IconButton
                          size="small"
                          onClick={(e) => {
                            e.stopPropagation();
                            removeConfig(index);
                          }}
                          aria-label={`Remove configuration ${headerLabel}`}
                          sx={{ mr: 1 }}
                        >
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </Box>
                    </AccordionSummary>

                    <AccordionDetails>
                      <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
                        {/* Config name + Accessory */}
                        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2 }}>
                          <TextField
                            label="Config Name"
                            value={config.config_name}
                            onChange={(e) =>
                              setConfig(index, { config_name: e.target.value })
                            }
                            required
                          />
                          <TextField
                            label="Accessory Name"
                            value={config.accessory_name}
                            onChange={(e) =>
                              setConfig(index, { accessory_name: e.target.value })
                            }
                          />
                        </Box>

                        {/* Focal length + Focal ratio + Reduction factor */}
                        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 2 }}>
                          <TextField
                            label="Focal Length (mm)"
                            type="number"
                            value={config.effective_focal_length_mm}
                            onChange={(e) =>
                              setConfig(index, { effective_focal_length_mm: e.target.value })
                            }
                            required
                            slotProps={{ htmlInput: { step: "any", min: 0 } }}
                          />
                          <TextField
                            label="Focal Ratio (f/)"
                            type="number"
                            value={config.effective_focal_ratio}
                            onChange={(e) =>
                              setConfig(index, { effective_focal_ratio: e.target.value })
                            }
                            required
                            slotProps={{ htmlInput: { step: "any", min: 0 } }}
                          />
                          <TextField
                            label="Reduction Factor"
                            type="number"
                            value={config.reduction_factor}
                            onChange={(e) =>
                              setConfig(index, { reduction_factor: e.target.value })
                            }
                            slotProps={{ htmlInput: { step: "any", min: 0 } }}
                          />
                        </Box>

                        {/* Image circle + Back focus */}
                        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2 }}>
                          <TextField
                            label="Effective Image Circle (mm)"
                            type="number"
                            value={config.effective_image_circle_mm}
                            onChange={(e) =>
                              setConfig(index, { effective_image_circle_mm: e.target.value })
                            }
                            slotProps={{ htmlInput: { step: "any", min: 0 } }}
                          />
                          <TextField
                            label="Back Focus (mm)"
                            type="number"
                            value={config.effective_back_focus_mm}
                            onChange={(e) =>
                              setConfig(index, { effective_back_focus_mm: e.target.value })
                            }
                            slotProps={{ htmlInput: { step: "any", min: 0 } }}
                          />
                        </Box>

                        {/* Is native toggle */}
                        <FormControlLabel
                          control={
                            <Switch
                              checked={config.is_native}
                              onChange={(e) =>
                                setConfig(index, { is_native: e.target.checked })
                              }
                            />
                          }
                          label="Native configuration (no accessories)"
                        />

                        {/* Config notes */}
                        <TextField
                          label="Notes"
                          value={config.notes}
                          onChange={(e) => setConfig(index, { notes: e.target.value })}
                          multiline
                          rows={2}
                        />
                      </Box>
                    </AccordionDetails>
                  </Accordion>
                );
              })}

              <Button
                startIcon={<AddIcon />}
                onClick={addConfig}
                variant="outlined"
                size="small"
                sx={{ mt: 1 }}
              >
                Add Configuration
              </Button>
            </Box>
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
