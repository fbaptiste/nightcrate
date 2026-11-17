import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
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
  onSaved: (updated: CatalogFrame | null) => void;
}

export default function FrameCorrectionsDialog({
  open,
  onClose,
  projectId,
  frame,
  frameIds = [],
  onSaved,
}: Props) {
  const bulk = frame === null;
  const count = bulk ? frameIds.length : 1;

  const [frameType, setFrameType] = useState<FrameTypeName | "">("");
  const [typeDirty, setTypeDirty] = useState(false);
  const [resets, setResets] = useState<Set<CorrectableField>>(new Set());
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setFrameType((frame?.frame_type as FrameTypeName) ?? "");
    setTypeDirty(false);
    setResets(new Set());
    setError(null);
  }, [open, frame]);

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

  const anyChange = typeDirty || resets.size > 0;

  const save = () => {
    const body: FrameCorrection = {};
    if (typeDirty && frameType !== "" && !resets.has("frame_type")) {
      body.frame_type = frameType;
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
