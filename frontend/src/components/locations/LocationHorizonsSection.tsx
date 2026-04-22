/**
 * Horizons section for the Location editor dialog.
 *
 * Replaces the v0.13.0 staged-save flow with immediate persistence:
 * every Create / Update / Delete / Promote-default hits the server
 * right away, decoupled from the outer location editor's Save. The
 * mental model is "horizons are their own thing, attached to a
 * location". Matches how rigs behave.
 *
 * One location → at most one ``type='custom'`` polyline + any number
 * of ``type='artificial'`` flat-altitude rows. Exactly one row per
 * location is ``is_default`` (enforced server-side).
 */
import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
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
  createHorizon,
  deleteHorizon,
  downloadHorizonExport,
  fetchHorizons,
  parseHorizonFile,
  updateHorizon,
  type Horizon,
  type HorizonExportFormat,
  type HorizonPoint,
} from "@/api/horizons";
import HorizonEditor from "./HorizonEditor";

interface Props {
  locationId: number;
  locationName: string;
}

export default function LocationHorizonsSection({ locationId, locationName }: Props) {
  const queryClient = useQueryClient();
  const [snack, setSnack] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [editorCustom, setEditorCustom] = useState<Horizon | null>(null);
  const [creatingCustom, setCreatingCustom] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Horizon | null>(null);

  const { data: horizons = [], isLoading } = useQuery({
    queryKey: ["horizons", locationId],
    queryFn: () => fetchHorizons(locationId),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["horizons", locationId] });

  const customHorizon = horizons.find((h) => h.type === "custom") ?? null;

  const handlePromoteDefault = async (h: Horizon) => {
    if (h.is_default) return;
    try {
      await updateHorizon(locationId, h.id, { is_default: true });
      invalidate();
    } catch (err) {
      setSnack(err instanceof Error ? err.message : "Failed to promote default");
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteHorizon(locationId, deleteTarget.id);
      setDeleteTarget(null);
      invalidate();
    } catch (err) {
      setSnack(err instanceof Error ? err.message : "Delete failed");
    }
  };

  const handleCustomSaved = async (points: HorizonPoint[]) => {
    try {
      if (editorCustom) {
        await updateHorizon(locationId, editorCustom.id, { points });
      } else {
        await createHorizon(locationId, {
          name: "Custom horizon",
          type: "custom",
          points,
          source: "drawn",
        });
      }
      setEditorCustom(null);
      setCreatingCustom(false);
      invalidate();
    } catch (err) {
      setSnack(err instanceof Error ? err.message : "Save failed");
    }
  };

  const handleImport = async (file: File) => {
    // Stateless parse so the editor can show the points before the
    // user commits with Keep changes.
    const result = await parseHorizonFile(file);
    return { points: result.points, warnings: result.warnings };
  };

  const handleExport = (format: HorizonExportFormat) => {
    if (!customHorizon) return;
    downloadHorizonExport(locationId, customHorizon.id, format);
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
        {!customHorizon && (
          <Button
            size="small"
            startIcon={<AddIcon />}
            onClick={() => {
              setEditorCustom(null);
              setCreatingCustom(true);
            }}
          >
            Custom
          </Button>
        )}
      </Stack>

      <Paper variant="outlined" sx={{ p: 1.5 }}>
        {isLoading ? (
          <Typography variant="body2" color="text.secondary">
            Loading horizons…
          </Typography>
        ) : horizons.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No horizons — add one to use this location in the planner.
          </Typography>
        ) : (
          <Stack spacing={0.5}>
            {horizons.map((h) => (
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
                {h.type === "custom" && (
                  <IconButton
                    size="small"
                    onClick={() => {
                      setCreatingCustom(false);
                      setEditorCustom(h);
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
        onCreate={async ({ name, altitude }) => {
          try {
            await createHorizon(locationId, {
              name,
              type: "artificial",
              flat_altitude_deg: altitude,
            });
            setAddOpen(false);
            invalidate();
          } catch (err) {
            setSnack(err instanceof Error ? err.message : "Create failed");
          }
        }}
      />

      <HorizonEditor
        open={editorCustom !== null || creatingCustom}
        locationName={locationName}
        initialPoints={editorCustom?.points ?? null}
        onClose={() => {
          setEditorCustom(null);
          setCreatingCustom(false);
        }}
        onSave={handleCustomSaved}
        onImport={handleImport}
        onExport={handleExport}
        exportsDisabled={editorCustom === null}
      />

      <Dialog open={deleteTarget !== null} onClose={() => setDeleteTarget(null)}>
        <DialogTitle>Delete horizon?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            Delete <strong>{deleteTarget?.name}</strong>? If this is the
            location's default horizon, another one will be promoted
            automatically. The last horizon on a location can't be
            deleted.
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
  onCreate: (body: { name: string; altitude: number }) => Promise<void>;
}

function ArtificialHorizonDialog({ open, onClose, onCreate }: ArtificialHorizonDialogProps) {
  const [altitude, setAltitude] = useState("30");
  const [name, setName] = useState("");
  const nameEditedRef = useRef(false);
  const [saving, setSaving] = useState(false);
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

  const handleSubmit = async () => {
    const alt = parseFloat(altitude);
    if (isNaN(alt) || alt < -5 || alt > 90) {
      setError("Altitude must be between -5 and 90 degrees.");
      return;
    }
    if (!effectiveName.trim()) {
      setError("Name is required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onCreate({ name: effectiveName.trim(), altitude: alt });
      // Reset for next open.
      setAltitude("30");
      setName("");
      nameEditedRef.current = false;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setSaving(false);
    }
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
        <Button variant="contained" onClick={handleSubmit} disabled={saving}>
          {saving ? "Adding…" : "Add"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
