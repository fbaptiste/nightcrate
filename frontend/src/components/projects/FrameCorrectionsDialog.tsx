import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import Autocomplete from "@mui/material/Autocomplete";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControlLabel from "@mui/material/FormControlLabel";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import {
  bulkCorrectFrames,
  correctFrameClassification,
  FRAME_TYPES,
  type CatalogFrame,
  type CorrectableField,
  type FrameCorrection,
  type FrameTypeName,
} from "@/api/projectCatalog";
import { LINE_NAMES } from "@/lib/lineNames";
import { filterSuggestions, type FilterSuggestion } from "./catalogMarkers";

/** Human labels for the frame_type vocabulary. "unknown" is offered so a user
 *  can un-classify a frame the header mislabeled into a real type. */
const TYPE_LABELS: Record<FrameTypeName, string> = {
  light: "Light",
  dark: "Dark",
  flat: "Flat",
  bias: "Bias",
  dark_flat: "Dark Flat",
  unknown: "Unknown",
};

interface Props {
  open: boolean;
  onClose: () => void;
  projectId: number;
  /** Single-frame mode. Null in bulk mode. */
  frame: CatalogFrame | null;
  /** Bulk mode: the selected frame ids. Empty in single-frame mode. */
  frameIds?: number[];
  rigFilters?: string[];
  onSaved: (updated: CatalogFrame | null) => void;
}

export default function FrameCorrectionsDialog({
  open,
  onClose,
  projectId,
  frame,
  frameIds = [],
  rigFilters = [],
  onSaved,
}: Props) {
  const bulk = frame === null;
  const count = bulk ? frameIds.length : 1;

  const [frameType, setFrameType] = useState<FrameTypeName | "">(
    (frame?.frame_type as FrameTypeName) ?? "",
  );
  const [typeDirty, setTypeDirty] = useState(false);
  const [filter, setFilter] = useState(frame?.filter_name ?? "");
  const [filterDirty, setFilterDirty] = useState(false);
  const [resets, setResets] = useState<Set<CorrectableField>>(new Set());
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (body: FrameCorrection) =>
      bulk
        ? bulkCorrectFrames(projectId, frameIds, body).then(() => null)
        : correctFrameClassification(projectId, frame!.id, body),
    onSuccess: (updated) => {
      onSaved(updated);
      onClose();
    },
    onError: (e: Error) => setError(e.message),
  });

  const anyChange = typeDirty || filterDirty || resets.size > 0;
  const suggestions = filterSuggestions(rigFilters, LINE_NAMES);

  const save = () => {
    const body: FrameCorrection = {};
    if (typeDirty && frameType !== "" && !resets.has("frame_type")) {
      body.frame_type = frameType;
    }
    if (filterDirty && !resets.has("filter")) {
      body.filter = filter.trim() || null;
    }
    if (resets.size > 0) body.reset_to_auto = [...resets];
    mutation.mutate(body);
  };

  const toggleReset = (field: CorrectableField) =>
    setResets((prev) => {
      const next = new Set(prev);
      if (next.has(field)) next.delete(field);
      else next.add(field);
      return next;
    });

  const title = bulk ? `Correct ${count} frames` : "Frame classification";
  const subtitle = bulk
    ? "Applies to every selected frame. All or nothing — if one frame fails, none change."
    : (frame?.path?.split("/").pop() ?? `frame ${frame?.id}`);

  const typeIsUser = frame?.frame_type_source === "user";

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ mb: 2, fontFamily: bulk ? undefined : "monospace" }}
        >
          {subtitle}
        </Typography>
        <Stack spacing={2}>
          <Stack direction="row" spacing={1} alignItems="center">
            <TextField
              select
              size="small"
              label="Frame type"
              sx={{ flex: 1 }}
              value={frameType}
              disabled={resets.has("frame_type")}
              onChange={(e) => {
                setFrameType(e.target.value as FrameTypeName);
                setTypeDirty(true);
              }}
              helperText={
                bulk ? "Leave unchanged to keep each frame's current type" : undefined
              }
            >
              {FRAME_TYPES.map((t) => (
                <MenuItem key={t} value={t}>
                  {TYPE_LABELS[t]}
                </MenuItem>
              ))}
            </TextField>
            {!bulk && typeIsUser && (
              <ResetChip
                active={resets.has("frame_type")}
                onToggle={() => toggleReset("frame_type")}
              />
            )}
          </Stack>

          <Autocomplete<FilterSuggestion, false, false, true>
            freeSolo
            size="small"
            options={suggestions}
            groupBy={(option) => option.group}
            getOptionLabel={(option) => typeof option === "string" ? option : option.value}
            value={filter}
            disabled={resets.has("filter")}
            onInputChange={(_, value, reason) => {
              if (reason === "reset" && value === filter) return;
              setFilter(value);
              setFilterDirty(true);
            }}
            onChange={(_, value) => {
              setFilter(typeof value === "string" ? value : value?.value ?? "");
              setFilterDirty(true);
            }}
            renderInput={(params) => (
              <TextField
                {...params}
                label="Filter"
                helperText="Applies to every selected frame and survives rescans."
                FormHelperTextProps={{ sx: { color: "text.secondary", fontSize: "12px" } }}
              />
            )}
          />
          <FormControlLabel
            control={
              <Checkbox
                checked={resets.has("filter")}
                onChange={() => toggleReset("filter")}
                inputProps={{ "aria-label": "Use each file's own filter" }}
              />
            }
            label="Use each file's own filter"
          />

          <Typography variant="caption" color="text.secondary">
            A correction is marked as yours, so re-scans and re-runs leave it alone.
          </Typography>

          {error && (
            <Typography variant="body2" color="warning.main">
              {error}
            </Typography>
          )}
        </Stack>
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

function ResetChip({
  active,
  onToggle,
}: {
  active: boolean;
  onToggle: () => void;
}) {
  if (active) {
    return (
      <Chip size="small" label="→ auto" color="primary" onDelete={onToggle} />
    );
  }
  return (
    <Tooltip title="This field is a manual correction — automated passes never change it. Click to hand it back to automatic classification (the next scan re-derives it).">
      <Chip
        size="small"
        label="manual"
        color="primary"
        variant="outlined"
        onClick={onToggle}
      />
    </Tooltip>
  );
}
