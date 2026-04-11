import { useState, useEffect } from "react";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControl from "@mui/material/FormControl";
import IconButton from "@mui/material/IconButton";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Snackbar from "@mui/material/Snackbar";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { useQuery } from "@tanstack/react-query";
import { parseOptionalFloat } from "@/lib/formUtils";
import ManufacturerPicker from "@/components/equipment/shared/ManufacturerPicker";

import {
  createFilter,
  updateFilter,
  createFilterPassband,
  updateFilterPassband,
  deleteFilterPassband,
  fetchFilterTypes,
  type Filter,
  type FilterPassband,
  type FilterCreate,
  type FilterPassbandCreate,
} from "@/api/equipment";

const LINE_NAME_OPTIONS = [
  "Ha",
  "Hb",
  "Oiii",
  "Sii",
  "Nii",
  "OI",
  "Lum",
  "R",
  "G",
  "B",
  "UVIR",
  "LP",
  "ND",
  "other",
] as const;

interface FilterFormDialogProps {
  open: boolean;
  filter: Filter | null;
  onClose: () => void;
  onSaved: () => void;
}

interface PassbandEntry {
  // undefined = new (not yet saved)
  id?: number;
  line_name: string;
  central_wavelength_nm: string;
  bandwidth_nm: string;
  peak_transmission_pct: string;
  dirty: boolean;
  deleted: boolean;
}

interface FormState {
  model_name: string;
  manufacturer_id: number | null;
  filter_type_id: number | null;
  peak_transmission_pct: string;
  notes: string;
}

function emptyForm(): FormState {
  return {
    model_name: "",
    manufacturer_id: null,
    filter_type_id: null,
    peak_transmission_pct: "",
    notes: "",
  };
}

function filterToForm(filter: Filter): FormState {
  return {
    model_name: filter.model_name,
    manufacturer_id: filter.manufacturer.id,
    filter_type_id: filter.filter_type.id,
    peak_transmission_pct:
      filter.peak_transmission_pct != null ? String(filter.peak_transmission_pct) : "",
    notes: filter.notes ?? "",
  };
}

function emptyPassband(): PassbandEntry {
  return {
    id: undefined,
    line_name: "",
    central_wavelength_nm: "",
    bandwidth_nm: "",
    peak_transmission_pct: "",
    dirty: false,
    deleted: false,
  };
}

function passbandToEntry(pb: FilterPassband): PassbandEntry {
  return {
    id: pb.id,
    line_name: pb.line_name ?? "",
    central_wavelength_nm: String(pb.central_wavelength_nm),
    bandwidth_nm: pb.bandwidth_nm != null ? String(pb.bandwidth_nm) : "",
    peak_transmission_pct:
      pb.peak_transmission_pct != null ? String(pb.peak_transmission_pct) : "",
    dirty: false,
    deleted: false,
  };
}


function passbandHeaderLabel(pb: PassbandEntry): string {
  const name = pb.line_name || "New Passband";
  const wl = pb.central_wavelength_nm ? `${pb.central_wavelength_nm}nm` : null;
  const bw = pb.bandwidth_nm ? `${pb.bandwidth_nm}nm` : null;
  const detail = wl && bw ? `${wl} / ${bw}` : wl ?? "";
  return detail ? `${name} — ${detail}` : name;
}

export default function FilterFormDialog({
  open,
  filter,
  onClose,
  onSaved,
}: FilterFormDialogProps) {
  const [form, setForm] = useState<FormState>(emptyForm);
  const [passbands, setPassbands] = useState<PassbandEntry[]>([]);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<
    Partial<Record<keyof FormState | "passbands", string>>
  >({});
  const [snackOpen, setSnackOpen] = useState(false);
  const [snackMessage, setSnackMessage] = useState("");
  const [snackSeverity, setSnackSeverity] = useState<"info" | "error">("info");
  const [expandedIndex, setExpandedIndex] = useState<number | false>(false);

  const { data: filterTypes = [] } = useQuery({
    queryKey: ["filter-types"],
    queryFn: () => fetchFilterTypes(),
  });

  useEffect(() => {
    if (open) {
      if (filter) {
        setForm(filterToForm(filter));
        setPassbands(filter.passbands.map(passbandToEntry));
        setExpandedIndex(false);
      } else {
        setForm(emptyForm());
        setPassbands([]);
        setExpandedIndex(false);
      }
      setErrors({});
    }
  }, [open, filter]);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const setPassband = (index: number, patch: Partial<PassbandEntry>) => {
    setPassbands((prev) =>
      prev.map((pb, i) => (i === index ? { ...pb, ...patch, dirty: true } : pb)),
    );
  };

  const addPassband = () => {
    const newIndex = passbands.length;
    setPassbands((prev) => [...prev, emptyPassband()]);
    setExpandedIndex(newIndex);
  };

  const removePassband = (index: number) => {
    setPassbands((prev) =>
      prev.map((pb, i) => (i === index ? { ...pb, deleted: true } : pb)),
    );
    if (expandedIndex === index) setExpandedIndex(false);
  };

  const validate = (): boolean => {
    const newErrors: typeof errors = {};
    if (!form.model_name.trim()) newErrors.model_name = "Model name is required";
    if (form.manufacturer_id == null) newErrors.manufacturer_id = "Manufacturer is required";
    if (form.filter_type_id == null) newErrors.filter_type_id = "Filter type is required";

    const activePassbands = passbands.filter((pb) => !pb.deleted);
    for (const pb of activePassbands) {
      if (!pb.central_wavelength_nm.trim() || isNaN(parseFloat(pb.central_wavelength_nm))) {
        newErrors.passbands = "All passbands must have a central wavelength";
        break;
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSave = async () => {
    if (!validate()) return;

    setSaving(true);
    try {
      const payload: FilterCreate = {
        model_name: form.model_name.trim(),
        manufacturer_id: form.manufacturer_id!,
        filter_type_id: form.filter_type_id!,
        peak_transmission_pct: parseOptionalFloat(form.peak_transmission_pct),
        notes: form.notes.trim() || null,
      };

      let filterId: number;
      if (filter) {
        await updateFilter(filter.id, payload);
        filterId = filter.id;
      } else {
        const created = await createFilter(payload);
        filterId = created.id;
      }

      // Process passbands
      for (const pb of passbands) {
        if (pb.deleted) {
          if (pb.id != null) {
            await deleteFilterPassband(filterId, pb.id);
          }
          continue;
        }

        const pbPayload: FilterPassbandCreate = {
          filter_id: filterId,
          line_name: pb.line_name.trim() || null,
          central_wavelength_nm: parseFloat(pb.central_wavelength_nm),
          bandwidth_nm: parseOptionalFloat(pb.bandwidth_nm),
          peak_transmission_pct: parseOptionalFloat(pb.peak_transmission_pct),
        };

        if (pb.id == null) {
          await createFilterPassband(filterId, pbPayload);
        } else if (pb.dirty) {
          await updateFilterPassband(filterId, pb.id, pbPayload);
        }
      }

      setSnackMessage(isEdit ? "Filter updated." : "Filter added.");
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

  const isEdit = filter !== null;

  const visiblePassbands = passbands
    .map((pb, i) => ({ pb, index: i }))
    .filter(({ pb }) => !pb.deleted);

  return (
    <>
      <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
        <DialogTitle>{isEdit ? "Edit Filter" : "Add Filter"}</DialogTitle>

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

            {/* Row 2: Filter type + Peak transmission */}
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2 }}>
              <FormControl required error={Boolean(errors.filter_type_id)}>
                <InputLabel id="filter-type-label">Filter Type</InputLabel>
                <Select<string>
                  labelId="filter-type-label"
                  label="Filter Type"
                  value={form.filter_type_id != null ? String(form.filter_type_id) : ""}
                  onChange={(e) => {
                    const val = e.target.value;
                    set("filter_type_id", val === "" ? null : Number(val));
                  }}
                >
                  {filterTypes.map((ft) => (
                    <MenuItem key={ft.id} value={String(ft.id)}>
                      {ft.display_name}
                    </MenuItem>
                  ))}
                </Select>
                {errors.filter_type_id && (
                  <Typography variant="caption" color="error" sx={{ mt: 0.5, mx: 1.75 }}>
                    {errors.filter_type_id}
                  </Typography>
                )}
              </FormControl>

              <TextField
                label="Peak Transmission (%)"
                type="number"
                value={form.peak_transmission_pct}
                onChange={(e) => set("peak_transmission_pct", e.target.value)}
                slotProps={{ htmlInput: { step: "any", min: 0, max: 100 } }}
              />
            </Box>

            {/* Row 4: Notes */}
            <TextField
              label="Notes"
              value={form.notes}
              onChange={(e) => set("notes", e.target.value)}
              multiline
              rows={2}
            />

            {/* Passbands section */}
            <Box>
              <Typography variant="subtitle1" sx={{ mb: 1, fontWeight: 600 }}>
                Passbands
              </Typography>

              {errors.passbands && (
                <Alert severity="warning" sx={{ mb: 1 }}>
                  {errors.passbands}
                </Alert>
              )}

              {visiblePassbands.length === 0 && (
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  No passbands defined. Add one for narrowband or specific wavelength filters.
                </Typography>
              )}

              {visiblePassbands.map(({ pb, index }) => (
                <Accordion
                  key={pb.id ?? `new-${index}`}
                  expanded={expandedIndex === index}
                  onChange={(_e, isExpanded) => setExpandedIndex(isExpanded ? index : false)}
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
                      <Typography sx={{ flex: 1 }}>{passbandHeaderLabel(pb)}</Typography>
                      <IconButton
                        size="small"
                        onClick={(e) => {
                          e.stopPropagation();
                          removePassband(index);
                        }}
                        aria-label={`Remove passband ${passbandHeaderLabel(pb)}`}
                        sx={{ mr: 1 }}
                      >
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </Box>
                  </AccordionSummary>

                  <AccordionDetails>
                    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
                      {/* Line name */}
                      <FormControl>
                        <InputLabel id={`line-name-label-${index}`}>Line Name</InputLabel>
                        <Select
                          labelId={`line-name-label-${index}`}
                          label="Line Name"
                          value={pb.line_name}
                          onChange={(e) => setPassband(index, { line_name: e.target.value })}
                        >
                          <MenuItem value="">
                            <em>None</em>
                          </MenuItem>
                          {LINE_NAME_OPTIONS.map((name) => (
                            <MenuItem key={name} value={name}>
                              {name}
                            </MenuItem>
                          ))}
                        </Select>
                      </FormControl>

                      {/* Central wavelength + Bandwidth */}
                      <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2 }}>
                        <TextField
                          label="Central Wavelength (nm)"
                          type="number"
                          value={pb.central_wavelength_nm}
                          onChange={(e) =>
                            setPassband(index, { central_wavelength_nm: e.target.value })
                          }
                          required
                          slotProps={{ htmlInput: { step: "any", min: 0 } }}
                        />
                        <TextField
                          label="Bandwidth (nm)"
                          type="number"
                          value={pb.bandwidth_nm}
                          onChange={(e) =>
                            setPassband(index, { bandwidth_nm: e.target.value })
                          }
                          slotProps={{ htmlInput: { step: "any", min: 0 } }}
                        />
                      </Box>

                      {/* Peak transmission */}
                      <TextField
                        label="Peak Transmission (%)"
                        type="number"
                        value={pb.peak_transmission_pct}
                        onChange={(e) =>
                          setPassband(index, { peak_transmission_pct: e.target.value })
                        }
                        slotProps={{ htmlInput: { step: "any", min: 0, max: 100 } }}
                        sx={{ width: "50%" }}
                      />
                    </Box>
                  </AccordionDetails>
                </Accordion>
              ))}

              <Button
                startIcon={<AddIcon />}
                onClick={addPassband}
                variant="outlined"
                size="small"
                sx={{ mt: 1 }}
              >
                Add Passband
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
