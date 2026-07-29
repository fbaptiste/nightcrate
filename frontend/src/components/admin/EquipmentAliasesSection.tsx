import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import {
  confirmObservation,
  dismissObservation,
  fetchUnresolvedObservations,
  type UnresolvedObservation,
} from "@/api/equipmentAliases";
import {
  fetchCameras,
  fetchFilters,
  fetchTelescopes,
} from "@/api/equipment";

interface EquipmentOption {
  id: number;
  label: string;
}

const KIND_LABEL: Record<UnresolvedObservation["equipment_kind"], string> = {
  camera: "Camera",
  telescope: "Telescope / OTA",
  filter: "Filter",
};

/** Admin section: map FITS header strings the resolver couldn't identify to
 * equipment records. Confirming inserts a permanent alias — every future
 * ingest (and any "Re-run equipment resolution") resolves it automatically.
 * The resolver never confirms on its own; this screen is the only path. */
export default function EquipmentAliasesSection() {
  const queryClient = useQueryClient();
  const [snack, setSnack] = useState<string | null>(null);
  // observation id → currently picked equipment option (before Confirm).
  const [picks, setPicks] = useState<Record<number, EquipmentOption | null>>({});

  const { data, isLoading } = useQuery({
    queryKey: ["equipment-unresolved"],
    queryFn: () => fetchUnresolvedObservations(),
  });

  const { data: cameras = [] } = useQuery({
    queryKey: ["equipment-cameras-all"],
    queryFn: () => fetchCameras(true),
    enabled: (data?.pending_by_kind["camera"] ?? 0) > 0,
  });
  const { data: telescopes = [] } = useQuery({
    queryKey: ["equipment-telescopes-all"],
    queryFn: () => fetchTelescopes(true),
    enabled: (data?.pending_by_kind["telescope"] ?? 0) > 0,
  });
  const { data: filters = [] } = useQuery({
    queryKey: ["equipment-filters-all"],
    queryFn: () => fetchFilters(true),
    enabled: (data?.pending_by_kind["filter"] ?? 0) > 0,
  });

  const optionsByKind = useMemo<Record<string, EquipmentOption[]>>(
    () => ({
      camera: cameras.map((c) => ({
        id: c.id,
        label: `${c.manufacturer.name} ${c.model_name}`,
      })),
      telescope: telescopes.map((t) => ({
        id: t.id,
        label: `${t.manufacturer.name} ${t.model_name}`,
      })),
      filter: filters.map((f) => ({
        id: f.id,
        label: `${f.manufacturer.name} ${f.model_name}`,
      })),
    }),
    [cameras, telescopes, filters],
  );

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["equipment-unresolved"] });

  const confirmMut = useMutation({
    mutationFn: ({ obsId, equipmentId }: { obsId: number; equipmentId: number }) =>
      confirmObservation(obsId, equipmentId),
    onSuccess: (result) => {
      invalidate();
      setSnack(
        `Mapped "${result.observation.original_observation}" — ` +
          `re-scan or re-run resolution on affected projects to apply it`,
      );
    },
    onError: (e: Error) => setSnack(e.message),
  });
  const dismissMut = useMutation({
    mutationFn: (obsId: number) => dismissObservation(obsId),
    onSuccess: () => {
      invalidate();
      setSnack("Observation dismissed (it reappears if seen by a later scan)");
    },
    onError: (e: Error) => setSnack(e.message),
  });

  const pending = data?.items ?? [];

  return (
    <>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
        <Typography variant="h6">Equipment Aliases</Typography>
        {data && data.pending_total > 0 && (
          <Chip size="small" color="primary" label={`${data.pending_total} pending`} />
        )}
      </Stack>
      <Paper sx={{ p: 2, mb: 3 }}>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Header values from cataloged files that didn't match any known
          equipment. Map each to the equipment it means — the mapping becomes a
          permanent alias, applied by every future scan (or a catalog's "Re-run
          resolution").
        </Typography>

        {isLoading && <CircularProgress size={20} />}
        {!isLoading && pending.length === 0 && (
          <Typography variant="body2" color="text.secondary">
            Nothing pending — every header value seen so far is mapped.
          </Typography>
        )}

        <Stack spacing={1.5}>
          {pending.map((obs) => (
            <Stack
              key={obs.id}
              direction={{ xs: "column", sm: "row" }}
              spacing={1.5}
              alignItems={{ xs: "stretch", sm: "center" }}
              sx={{ borderBottom: 1, borderColor: "divider", pb: 1.5 }}
            >
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Stack direction="row" spacing={1} alignItems="center">
                  <Chip
                    size="small"
                    variant="outlined"
                    label={KIND_LABEL[obs.equipment_kind]}
                  />
                  <Typography sx={{ fontFamily: "monospace", fontWeight: 600 }}>
                    {obs.original_observation}
                  </Typography>
                </Stack>
                <Typography variant="caption" color="text.secondary">
                  Seen {obs.seen_count} time{obs.seen_count === 1 ? "" : "s"} ·
                  last {obs.last_seen_at}
                </Typography>
              </Box>
              <Autocomplete
                size="small"
                sx={{ width: { xs: "100%", sm: 320 } }}
                options={optionsByKind[obs.equipment_kind] ?? []}
                value={picks[obs.id] ?? null}
                onChange={(_, v) => setPicks((p) => ({ ...p, [obs.id]: v }))}
                isOptionEqualToValue={(a, b) => a.id === b.id}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label={`Map to ${KIND_LABEL[obs.equipment_kind].toLowerCase()}`}
                  />
                )}
              />
              <Button
                size="small"
                variant="contained"
                disabled={!picks[obs.id] || confirmMut.isPending}
                onClick={() =>
                  confirmMut.mutate({
                    obsId: obs.id,
                    equipmentId: picks[obs.id]!.id,
                  })
                }
              >
                Confirm
              </Button>
              <Tooltip title="Dismiss (not my equipment / decide later)">
                <IconButton
                  size="small"
                  onClick={() => dismissMut.mutate(obs.id)}
                  disabled={dismissMut.isPending}
                >
                  <CloseIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </Stack>
          ))}
        </Stack>
      </Paper>
      <Snackbar
        open={snack !== null}
        autoHideDuration={6000}
        onClose={() => setSnack(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert severity="info" onClose={() => setSnack(null)} sx={{ width: "100%" }}>
          {snack}
        </Alert>
      </Snackbar>
    </>
  );
}
