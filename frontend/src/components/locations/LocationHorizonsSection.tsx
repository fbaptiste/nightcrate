/**
 * Horizons section for the Location editor dialog.
 *
 * Restores the v0.13.0 staged-save flow that v0.19.0 accidentally
 * dropped: every Create / Update / Delete / Promote-default writes to
 * the parent's staged state, NOT the server. The outer Location
 * editor's Save button commits everything together; its Cancel button
 * discards every local change. This keeps the dialog's dirty-state
 * behaviour consistent across the location's own fields AND its
 * horizons.
 *
 * One location → at most one ``type='custom'`` polyline + any number
 * of ``type='artificial'`` flat-altitude rows. Exactly one visible
 * row is ``is_default`` (UI-enforced; server re-validates on save).
 */
import { useRef, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Radio from "@mui/material/Radio";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import DeleteIcon from "@mui/icons-material/Delete";
import AddIcon from "@mui/icons-material/Add";
import EditIcon from "@mui/icons-material/Edit";
import {
  downloadHorizonExport,
  parseHorizonFile,
  type HorizonExportFormat,
  type HorizonPoint,
} from "@/api/horizons";
import HorizonEditor from "./HorizonEditor";
import {
  customHorizon,
  markDeleted,
  newArtificial,
  newCustom,
  promoteDefault,
  retagState,
  visibleHorizons,
  type StagedHorizon,
} from "./horizonStaging";

interface Props {
  /** Server id for an existing location; ``null`` when creating a new
   *  location (no server record exists yet). Needed by the export
   *  helper for existing custom horizons. */
  locationId: number | null;
  locationName: string;
  /** Full staged state — owned by the parent so it can serialise on
   *  Save and track dirtiness alongside the location's own fields. */
  staged: StagedHorizon[];
  onChange: (next: StagedHorizon[]) => void;
}

export default function LocationHorizonsSection({
  locationId,
  locationName,
  staged,
  onChange,
}: Props) {
  const [snack, setSnack] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [editorTarget, setEditorTarget] = useState<StagedHorizon | null>(null);
  const [creatingCustom, setCreatingCustom] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<StagedHorizon | null>(null);

  const visible = visibleHorizons(staged);
  const currentCustom = customHorizon(staged);

  const handlePromoteDefault = (h: StagedHorizon) => {
    if (h.is_default) return;
    onChange(promoteDefault(staged, h.id));
  };

  const handleDelete = () => {
    if (!deleteTarget) return;
    // Guard: can't delete the last remaining visible horizon — matches
    // the server's "location must have ≥1 horizon" invariant. Surface
    // the rule up front instead of waiting for a 422 at Save.
    if (visible.length === 1) {
      setSnack("Every location needs at least one horizon.");
      setDeleteTarget(null);
      return;
    }
    let next = markDeleted(staged, deleteTarget.id);
    // If we deleted the default, promote the first remaining visible
    // one so the "exactly one default" invariant stays satisfied. The
    // server would auto-promote on DELETE anyway but doing it here
    // keeps the UI state coherent for the user's remaining edits.
    if (deleteTarget.is_default) {
      const next_visible = visibleHorizons(next);
      if (next_visible.length > 0) {
        next = promoteDefault(next, next_visible[0].id);
      }
    }
    onChange(next);
    setDeleteTarget(null);
  };

  const handleAddArtificial = ({ name, altitude }: { name: string; altitude: number }) => {
    const entry = newArtificial({ staged, name, flat_altitude_deg: altitude });
    onChange([...staged, entry]);
    setAddOpen(false);
  };

  const handleCustomSaved = async (points: HorizonPoint[]) => {
    if (editorTarget) {
      // Editing an existing custom horizon — update in place and
      // re-tag state so unchanged-vs-modified is correct.
      onChange(
        staged.map((h) =>
          h.id === editorTarget.id ? retagState({ ...h, points }) : h,
        ),
      );
    } else {
      // Creating a new custom. New locations or locations without a
      // custom yet can have one. Default is inherited from visibility
      // state: if there are no other horizons, the new custom is
      // default; otherwise it's a non-default addition.
      const shouldBeDefault = visible.length === 0;
      const entry = newCustom({
        staged,
        name: "Custom horizon",
        points,
        is_default: shouldBeDefault,
      });
      onChange([...staged, entry]);
    }
    setEditorTarget(null);
    setCreatingCustom(false);
  };

  const handleImport = async (file: File) => {
    // Stateless parse so the editor can show the points before the
    // user commits with Keep changes.
    const result = await parseHorizonFile(file);
    return { points: result.points, warnings: result.warnings };
  };

  const handleExport = (format: HorizonExportFormat) => {
    if (!editorTarget || editorTarget.state === "new" || locationId === null) {
      // Export requires a server-backed horizon. Not available while
      // the user is editing a staged-but-not-yet-saved horizon.
      setSnack("Save the location first to export this horizon.");
      return;
    }
    downloadHorizonExport(locationId, editorTarget.id, format);
  };

  return (
    <Box sx={{ mt: 1 }}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
        <Typography variant="subtitle2" sx={{ flex: 1 }}>
          Horizons
        </Typography>
        <Button
          size="small"
          startIcon={<AddIcon />}
          onClick={() => setAddOpen(true)}
        >
          Artificial
        </Button>
        {!currentCustom && (
          <Button
            size="small"
            startIcon={<AddIcon />}
            onClick={() => {
              setEditorTarget(null);
              setCreatingCustom(true);
            }}
          >
            Custom
          </Button>
        )}
      </Stack>

      <Paper variant="outlined" sx={{ p: 1.5 }}>
        {visible.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No horizons — add one to use this location in the planner.
          </Typography>
        ) : (
          <Stack spacing={0.5}>
            {visible.map((h) => (
              <Stack
                key={h.id}
                direction="row"
                alignItems="center"
                spacing={1}
                sx={{
                  py: 0.5,
                  px: 0.5,
                  borderBottom: 1,
                  borderColor: "divider",
                  "&:last-child": { borderBottom: 0 },
                }}
              >
                <Radio
                  size="small"
                  checked={h.is_default}
                  onChange={() => handlePromoteDefault(h)}
                  title="Set as default for this location"
                  sx={{ p: 0.5 }}
                />
                <Chip
                  size="small"
                  label={h.type}
                  sx={{ textTransform: "capitalize", width: 78 }}
                  variant={h.type === "custom" ? "filled" : "outlined"}
                />
                <Typography variant="body2" sx={{ flex: 1, minWidth: 120 }}>
                  {h.name}
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ minWidth: 80 }}>
                  {h.type === "artificial"
                    ? `${h.flat_altitude_deg?.toFixed(0) ?? "?"}°`
                    : `${h.points.length} pts`}
                </Typography>
                {/* Per-row state tag so the user can see which rows are
                    going to commit as INSERT / PATCH / DELETE at the
                    outer Save. ``unchanged`` → no tag. */}
                {h.state !== "unchanged" && (
                  <Chip
                    size="small"
                    label={h.state}
                    variant="outlined"
                    color="warning"
                    sx={{ height: 18, fontSize: "0.65rem", textTransform: "capitalize" }}
                  />
                )}
                {h.type === "custom" && (
                  <IconButton
                    size="small"
                    onClick={() => {
                      setCreatingCustom(false);
                      setEditorTarget(h);
                    }}
                    aria-label="Edit custom horizon"
                  >
                    <EditIcon fontSize="small" />
                  </IconButton>
                )}
                <IconButton
                  size="small"
                  onClick={() => setDeleteTarget(h)}
                  aria-label="Delete horizon"
                >
                  <DeleteIcon fontSize="small" />
                </IconButton>
              </Stack>
            ))}
          </Stack>
        )}
      </Paper>

      <ArtificialHorizonDialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onCreate={handleAddArtificial}
      />

      <HorizonEditor
        open={editorTarget !== null || creatingCustom}
        locationName={locationName}
        initialPoints={editorTarget?.points ?? null}
        onClose={() => {
          setEditorTarget(null);
          setCreatingCustom(false);
        }}
        onSave={handleCustomSaved}
        onImport={handleImport}
        onExport={handleExport}
        exportsDisabled={
          editorTarget === null ||
          editorTarget.state === "new" ||
          locationId === null
        }
      />

      <Dialog open={deleteTarget !== null} onClose={() => setDeleteTarget(null)}>
        <DialogTitle>Delete horizon?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            Delete <strong>{deleteTarget?.name}</strong>? The change is
            staged until you click Save on the Location editor. If this
            is the current default, another visible horizon will be
            promoted in its place.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTarget(null)}>Cancel</Button>
          <Button color="warning" variant="contained" onClick={handleDelete}>
            Delete
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={snack !== null}
        autoHideDuration={3500}
        onClose={() => setSnack(null)}
        message={snack}
      />
    </Box>
  );
}

// ── Artificial-horizon create dialog ────────────────────────────────────────

interface ArtificialHorizonDialogProps {
  open: boolean;
  onClose: () => void;
  onCreate: (body: { name: string; altitude: number }) => void;
}

function ArtificialHorizonDialog({ open, onClose, onCreate }: ArtificialHorizonDialogProps) {
  const [altitude, setAltitude] = useState("30");
  const [name, setName] = useState("");
  const nameEditedRef = useRef(false);
  const [error, setError] = useState<string | null>(null);

  // Name auto-fills from the altitude (e.g. "30° flat") until the user
  // types a custom value, mirroring the calculator-page patterns.
  const effectiveName = nameEditedRef.current ? name : `${altitude || "?"}° flat`;

  const handleAltitudeChange = (value: string) => {
    setAltitude(value);
    if (!nameEditedRef.current) {
      setName(`${value || "?"}° flat`);
    }
  };

  const handleSubmit = () => {
    const alt = parseFloat(altitude);
    if (isNaN(alt) || alt < -5 || alt > 90) {
      setError("Altitude must be between -5 and 90 degrees.");
      return;
    }
    if (!effectiveName.trim()) {
      setError("Name is required.");
      return;
    }
    setError(null);
    onCreate({ name: effectiveName.trim(), altitude: alt });
    // Reset for next open.
    setAltitude("30");
    setName("");
    nameEditedRef.current = false;
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>Add artificial horizon</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField
            label="Altitude (°)"
            value={altitude}
            onChange={(e) => handleAltitudeChange(e.target.value)}
            type="number"
            inputProps={{ min: -5, max: 90, step: 1 }}
            size="small"
            helperText="A flat floor at this altitude in all directions."
            autoFocus
          />
          <TextField
            label="Name"
            value={effectiveName}
            onChange={(e) => {
              nameEditedRef.current = true;
              setName(e.target.value);
            }}
            size="small"
            helperText="Shown in the planner's horizon dropdown."
          />
          {error && (
            <Typography variant="body2" color="error">
              {error}
            </Typography>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={handleSubmit}>
          Add
        </Button>
      </DialogActions>
    </Dialog>
  );
}
