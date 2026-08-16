import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { fetchCameras, fetchFilters } from "@/api/equipment";
import { fetchRigs } from "@/api/rigs";
import {
  overrideFrameEquipment,
  type CatalogFrame,
  type EquipmentOverride,
  type OverridableField,
} from "@/api/projectCatalog";

interface Option {
  id: number;
  label: string;
}

interface FieldState {
  pick: Option | null;
  dirty: boolean; // user changed the value → include in the PATCH
  resetAuto: boolean; // hand the field back to automated control
}

const FIELDS: {
  key: OverridableField;
  label: string;
  sourceKey: "rig_source" | "camera_source" | "filter_source";
}[] = [
  { key: "rig_id", label: "Rig", sourceKey: "rig_source" },
  { key: "camera_id", label: "Camera", sourceKey: "camera_source" },
  { key: "filter_id", label: "Filter", sourceKey: "filter_source" },
];

/** Manual attribution override for one cataloged frame.

    A changed field is stored verbatim and marked user-sourced, so re-scans and
    "Re-run resolution" never clobber it. "Return to automatic" hands the field
    back — the next re-run refills it. */
export default function EquipmentOverrideDialog({
  open,
  onClose,
  projectId,
  frame,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  projectId: number;
  frame: CatalogFrame | null;
  onSaved: (updated: CatalogFrame) => void;
}) {
  const [fields, setFields] = useState<Record<OverridableField, FieldState>>({
    rig_id: { pick: null, dirty: false, resetAuto: false },
    camera_id: { pick: null, dirty: false, resetAuto: false },
    filter_id: { pick: null, dirty: false, resetAuto: false },
  });
  const [error, setError] = useState<string | null>(null);

  const { data: rigs = [] } = useQuery({
    queryKey: ["rigs-active"],
    queryFn: () => fetchRigs(),
    enabled: open,
  });
  const { data: cameras = [] } = useQuery({
    queryKey: ["equipment-cameras-all"],
    queryFn: () => fetchCameras(true),
    enabled: open,
  });
  const { data: filters = [] } = useQuery({
    queryKey: ["equipment-filters-all"],
    queryFn: () => fetchFilters(true),
    enabled: open,
  });

  const options = useMemo<Record<OverridableField, Option[]>>(
    () => ({
      rig_id: rigs.map((r) => ({ id: r.id, label: r.name })),
      camera_id: cameras.map((c) => ({
        id: c.id,
        label: `${c.manufacturer.name} ${c.model_name}`,
      })),
      filter_id: filters.map((f) => ({
        id: f.id,
        label: `${f.manufacturer.name} ${f.model_name}`,
      })),
    }),
    [rigs, cameras, filters],
  );

  // (Re)initialize from the frame each time the dialog opens. Labels come from
  // the frame's own resolved display names (NOT the picker option lists, which
  // load async — depending on them would wipe in-progress edits when a query
  // resolves mid-dialog); Autocomplete matches picks to options by id.
  useEffect(() => {
    if (!open || !frame) return;
    const init = (id: number | null, label: string | null): Option | null =>
      id == null ? null : { id, label: label ?? `#${id}` };
    setFields({
      rig_id: { pick: init(frame.rig_id, frame.rig_name), dirty: false, resetAuto: false },
      camera_id: {
        pick: init(frame.camera_id, frame.camera_model),
        dirty: false,
        resetAuto: false,
      },
      filter_id: {
        pick: init(frame.filter_id, frame.filter_model),
        dirty: false,
        resetAuto: false,
      },
    });
    setError(null);
  }, [open, frame]);

  const mutation = useMutation({
    mutationFn: (body: EquipmentOverride) =>
      overrideFrameEquipment(projectId, frame!.id, body),
    onSuccess: (updated) => {
      onSaved(updated);
      onClose();
    },
    onError: (e: Error) => setError(e.message),
  });

  if (!frame) return null;
  const filterAllowed = frame.frame_type === "light" || frame.frame_type === "flat";
  const anyChange = FIELDS.some(
    (f) => fields[f.key].dirty || fields[f.key].resetAuto,
  );

  const save = () => {
    const body: EquipmentOverride = {};
    const resets: OverridableField[] = [];
    for (const f of FIELDS) {
      const st = fields[f.key];
      if (st.resetAuto) resets.push(f.key);
      else if (st.dirty) body[f.key] = st.pick?.id ?? null;
    }
    if (resets.length > 0) body.reset_to_auto = resets;
    mutation.mutate(body);
  };

  const fileName = frame.path?.split("/").pop() ?? `frame ${frame.id}`;

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Equipment attribution</DialogTitle>
      <DialogContent>
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ mb: 2, fontFamily: "monospace" }}
        >
          {fileName}
        </Typography>
        <Stack spacing={2}>
          {FIELDS.map((f) => {
            const st = fields[f.key];
            const isUser = frame[f.sourceKey] === "user";
            const disabled =
              (f.key === "filter_id" && !filterAllowed) || st.resetAuto;
            return (
              <Stack key={f.key} direction="row" spacing={1} alignItems="center">
                <Autocomplete
                  size="small"
                  sx={{ flex: 1 }}
                  options={options[f.key]}
                  value={st.pick}
                  disabled={disabled}
                  onChange={(_, v) =>
                    setFields((prev) => ({
                      ...prev,
                      [f.key]: { pick: v, dirty: true, resetAuto: false },
                    }))
                  }
                  isOptionEqualToValue={(a, b) => a.id === b.id}
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      label={f.label}
                      helperText={
                        f.key === "filter_id" && !filterAllowed
                          ? "Only lights and flats carry a filter"
                          : undefined
                      }
                    />
                  )}
                />
                {isUser && !st.resetAuto && (
                  <Tooltip title="This field is a manual override — automated passes never change it. Click to hand it back to automatic resolution (the next re-run refills it).">
                    <Chip
                      size="small"
                      label="manual"
                      color="primary"
                      variant="outlined"
                      onClick={() =>
                        setFields((prev) => ({
                          ...prev,
                          [f.key]: { ...prev[f.key], resetAuto: true, dirty: false },
                        }))
                      }
                    />
                  </Tooltip>
                )}
                {st.resetAuto && (
                  <Tooltip title="Will return to automatic resolution on save">
                    <Chip
                      size="small"
                      label="→ auto"
                      variant="filled"
                      onDelete={() =>
                        setFields((prev) => ({
                          ...prev,
                          [f.key]: { ...prev[f.key], resetAuto: false },
                        }))
                      }
                    />
                  </Tooltip>
                )}
              </Stack>
            );
          })}
        </Stack>
        {error && (
          <Typography variant="body2" color="warning.main" sx={{ mt: 2 }}>
            {error}
          </Typography>
        )}
        <Box sx={{ mt: 2 }}>
          <Typography variant="caption" color="text.secondary">
            Changes here are yours — re-scans and "Re-run resolution" will never
            overwrite them.
          </Typography>
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          onClick={save}
          disabled={!anyChange || mutation.isPending}
        >
          Save
        </Button>
      </DialogActions>
    </Dialog>
  );
}
