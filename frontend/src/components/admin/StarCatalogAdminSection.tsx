import { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import LinearProgress from "@mui/material/LinearProgress";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";

import { parseApiError } from "@/api/plateSolve";
import {
  useBuildStarCatalogRanges,
  useCancelStarCatalogOperation,
  useDeleteStarCatalog,
  useDeleteStarCatalogRange,
  useDownloadStarCatalog,
  useImportStarCatalog,
  useStarCatalogStatus,
  type RangeStatus,
  type StarOperation,
} from "@/api/starCatalog";
import { FileBrowser } from "@/components/fits/FileBrowser";

const INTRO =
  "NightCrate's built-in plate solver uses stars from ESA's Gaia DR3 survey, prepared by the Siril team. Download them once; every database on this computer uses the same copy.";
const ATTRIBUTION =
  "Stars from ESA's Gaia DR3 (ESA/Gaia/DPAC), prepared by the Siril team. Catalogue CC BY 4.0; Gaia data also under CC BY-NC 3.0 IGO.";

function formatBytes(bytes: number): string {
  if (bytes >= 1_000_000_000) {
    return `${(bytes / 1_000_000_000).toFixed(2)} GB`;
  }
  if (bytes >= 1_000_000) {
    return `${Math.round(bytes / 1_000_000)} MB`;
  }
  if (bytes >= 1_000) {
    return `${Math.round(bytes / 1_000)} KB`;
  }
  return `${bytes} B`;
}

function operationLabel(operation: StarOperation): string {
  const phase = `${operation.phase[0].toUpperCase()}${operation.phase.slice(1)}`;
  const parts = [phase];
  if (operation.bytes_total > 0) {
    parts.push(`${formatBytes(operation.bytes_done)} of ${formatBytes(operation.bytes_total)}`);
  }
  if (
    operation.speed_bytes_per_s != null &&
    operation.speed_bytes_per_s > 0 &&
    operation.bytes_total > operation.bytes_done
  ) {
    const minutes = Math.ceil(
      (operation.bytes_total - operation.bytes_done) / operation.speed_bytes_per_s / 60,
    );
    parts.push(`about ${minutes} min left`);
  }
  if (operation.phase === "downloading") {
    parts.push("resumes if interrupted");
  }
  return parts.join(" · ");
}

function RangeState({ range }: { range: RangeStatus }) {
  if (range.state === "building") {
    const progress = Math.round((range.progress ?? 0) * 100);
    return (
      <Box sx={{ width: "100%", maxWidth: 110 }}>
        <LinearProgress
          variant="determinate"
          value={progress}
          sx={{ height: 6, borderRadius: 3, bgcolor: "action.hover" }}
        />
        <Typography variant="caption" color="text.secondary">
          Building · {progress}%
        </Typography>
      </Box>
    );
  }
  if (range.state === "waiting") {
    return (
      <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: "nowrap" }}>
        Waiting
      </Typography>
    );
  }
  if (range.state === "built") {
    return (
      <Typography variant="body2" color="secondary.main" sx={{ whiteSpace: "nowrap" }}>
        ✓ Built
      </Typography>
    );
  }
  return (
    <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: "nowrap" }}>
      {range.state === "needs_rebuild" ? "Needs rebuilding" : "Not built"}
    </Typography>
  );
}

export default function StarCatalogAdminSection() {
  const statusQuery = useStarCatalogStatus();
  const download = useDownloadStarCatalog();
  const importCatalog = useImportStarCatalog();
  const cancel = useCancelStarCatalogOperation();
  const build = useBuildStarCatalogRanges();
  const deleteRange = useDeleteStarCatalogRange();
  const deleteAll = useDeleteStarCatalog();

  const [selection, setSelection] = useState<{
    installKey: string | null;
    ids: Set<string>;
  }>({ installKey: null, ids: new Set() });
  const [importOpen, setImportOpen] = useState(false);
  const [removeOpen, setRemoveOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const status = statusQuery.data;
  const operation = status?.operation ?? null;
  const operationRunning = operation?.state === "running";
  const installKey = status?.installed?.installed_at ?? null;
  const selected =
    selection.installKey === installKey
      ? selection.ids
      : new Set(
          (status?.ranges ?? [])
            .filter(
              (range) =>
                range.state !== "built" && (range.recommended || range.rigs.length > 0),
            )
            .map((range) => range.id),
        );

  const run = async (action: () => Promise<unknown>) => {
    setError(null);
    try {
      await action();
    } catch (err: unknown) {
      setError(parseApiError(err).message);
    }
  };

  const buildableIds = (status?.ranges ?? [])
    .filter(
      (range) =>
        selected.has(range.id) &&
        range.state !== "built" &&
        range.state !== "building" &&
        range.state !== "waiting",
    )
    .map((range) => range.id);

  const mutationBusy =
    download.isPending ||
    importCatalog.isPending ||
    cancel.isPending ||
    build.isPending ||
    deleteRange.isPending ||
    deleteAll.isPending;

  const displayedError =
    error ??
    (operation && operation.state === "failed" ? operation.message : null) ??
    (statusQuery.isError ? parseApiError(statusQuery.error).message : null);

  return (
    <Box id="plate-solving-stars" sx={{ scrollMarginTop: 16 }}>
      <Typography variant="h6" sx={{ mb: 1, mt: 3 }}>
        Plate-solving stars
      </Typography>
      <Paper sx={{ p: 2 }}>
        {statusQuery.isLoading && <CircularProgress size={20} />}
        {displayedError && (
          <Alert severity="warning" onClose={() => setError(null)} sx={{ mb: 2 }}>
            {displayedError}
          </Alert>
        )}

        {status && !status.installed && !operationRunning && (
          <>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.25 }}>
              {INTRO}
            </Typography>
            <Box
              sx={{
                display: "flex",
                flexDirection: { xs: "column", sm: "row" },
                alignItems: { sm: "center" },
                gap: 1.5,
                py: 1.5,
                borderBottom: 1,
                borderColor: "divider",
              }}
            >
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography variant="body2" fontWeight={600}>
                  Siril Astrometry Catalogue (Gaia DR3)
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  Not installed · 1.14 GB download, 1.52 GB on disk · CC BY 4.0 · zenodo.org
                </Typography>
              </Box>
              <Stack direction="row" spacing={1}>
                <Button
                  size="small"
                  variant="outlined"
                  disabled={mutationBusy}
                  onClick={() => setImportOpen(true)}
                >
                  Import file…
                </Button>
                <Button
                  size="small"
                  variant="contained"
                  disabled={mutationBusy}
                  onClick={() => run(() => download.mutateAsync())}
                >
                  Download
                </Button>
              </Stack>
            </Box>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.75 }}>
              Field ranges can be chosen once the stars are installed.
            </Typography>
          </>
        )}

        {status && !status.installed && operationRunning && operation && (
          <Box
            sx={{
              display: "flex",
              alignItems: "center",
              gap: 1.5,
              py: 1.5,
              borderBottom: 1,
              borderColor: "divider",
            }}
          >
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="body2" fontWeight={600}>
                Siril Astrometry Catalogue (Gaia DR3)
              </Typography>
              <LinearProgress
                variant="determinate"
                value={(operation.progress ?? 0) * 100}
                sx={{ height: 6, borderRadius: 3, bgcolor: "action.hover", my: 0.75 }}
              />
              <Typography variant="caption" color="text.secondary">
                {operationLabel(operation)}
              </Typography>
            </Box>
            <Button
              size="small"
              variant="outlined"
              disabled={cancel.isPending}
              onClick={() => run(() => cancel.mutateAsync())}
            >
              Cancel
            </Button>
          </Box>
        )}

        {status?.installed && (
          <>
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                gap: 1.5,
                py: 1.5,
                borderBottom: 1,
                borderColor: "divider",
              }}
            >
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography variant="body2" fontWeight={600}>
                  Siril Astrometry Catalogue (Gaia DR3)
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  Version 1.0.0 · 1.52 GB · checksum verified · CC BY 4.0 · zenodo.org
                </Typography>
              </Box>
              <Button
                size="small"
                disabled={operationRunning || mutationBusy}
                onClick={() => setRemoveOpen(true)}
              >
                Remove
              </Button>
            </Box>

            <Box sx={{ mt: 1.75, minWidth: 0, maxWidth: "100%" }}>
              <Typography variant="body2" fontWeight={600} sx={{ mb: 0.25 }}>
                Field ranges
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Standard covers fields from 0.4° to 10°, which suits most rigs. Add Narrow fields for fields under 0.4°, usually at long focal lengths. An image whose field isn't covered can't be blind solved.
              </Typography>

              <Box sx={{ width: "100%", maxWidth: "100%", minWidth: 0, overflowX: "auto" }}>
                <Table size="small" sx={{ width: "100%", tableLayout: "fixed" }}>
                  <TableHead
                    sx={{
                      "& .MuiTableCell-root": {
                        color: "text.secondary",
                        fontSize: "0.75rem",
                      },
                    }}
                  >
                    <TableRow>
                      <TableCell padding="checkbox" sx={{ width: 42 }} />
                      <TableCell sx={{ width: { xs: 120, lg: 210 } }}>Field width</TableCell>
                      <TableCell>Your rigs</TableCell>
                      <TableCell align="right" sx={{ width: 105, px: 1 }}>Size</TableCell>
                      <TableCell sx={{ width: 120, px: 1 }}>Status</TableCell>
                      <TableCell sx={{ pl: 0, pr: 1, width: 72 }} />
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {status.ranges.map((range) => {
                      const isBuilt = range.state === "built";
                      const isQueued = range.state === "building" || range.state === "waiting";
                      const checked = isBuilt || isQueued || selected.has(range.id);
                      return (
                        <TableRow key={range.id}>
                          <TableCell padding="checkbox">
                            <Checkbox
                              size="small"
                              checked={checked}
                              disabled={isBuilt || range.state === "building" || operationRunning}
                              inputProps={{ "aria-label": `Build ${range.name}` }}
                              onChange={(event) => {
                                setSelection(() => {
                                  const next = new Set(selected);
                                  if (event.target.checked) next.add(range.id);
                                  else next.delete(range.id);
                                  return { installKey, ids: next };
                                });
                              }}
                            />
                          </TableCell>
                          <TableCell>
                            <Typography variant="body2" fontWeight={600} sx={{ whiteSpace: "nowrap" }}>
                              {range.name}
                            </Typography>
                            <Typography
                              variant="caption"
                              color="text.secondary"
                              sx={{ display: "block", whiteSpace: "nowrap" }}
                            >
                              {range.min_deg}° – {range.max_deg}°
                            </Typography>
                            {range.build_memory_bytes > 2_000_000_000 && (
                              <Typography
                                variant="caption"
                                color="text.secondary"
                                sx={{
                                  display: "block",
                                  whiteSpace: "normal",
                                }}
                              >
                                Building needs about {(range.build_memory_bytes / 1_000_000_000).toFixed(1)} GB of memory.
                              </Typography>
                            )}
                          </TableCell>
                          <TableCell sx={{ minWidth: 0 }}>
                            {range.rigs.length ? (
                              <Stack
                                direction="row"
                                spacing={0.5}
                                useFlexGap
                                flexWrap="wrap"
                                sx={{ minWidth: 0 }}
                              >
                                {range.rigs.map((rig) => (
                                  <Chip
                                    key={rig.id}
                                    label={`${rig.name} · ${rig.field_deg.toFixed(2)}°`}
                                    size="small"
                                    color="secondary"
                                    variant="outlined"
                                    sx={{
                                      maxWidth: "100%",
                                      height: "auto",
                                      "& .MuiChip-label": {
                                        py: 0.5,
                                        whiteSpace: "normal",
                                      },
                                    }}
                                  />
                                ))}
                              </Stack>
                            ) : (
                              <Typography variant="caption" color="text.secondary">—</Typography>
                            )}
                          </TableCell>
                          <TableCell
                            align="right"
                            sx={{
                              px: 1,
                              fontVariantNumeric: "tabular-nums",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {range.size_is_estimate && "about "}
                            {formatBytes(range.size_bytes)}
                          </TableCell>
                          <TableCell sx={{ px: 1, whiteSpace: "nowrap" }}>
                            <RangeState range={range} />
                          </TableCell>
                          <TableCell align="right" sx={{ pl: 0, pr: 1 }}>
                            {range.state === "built" && (
                              <Button
                                size="small"
                                disabled={operationRunning || mutationBusy}
                                onClick={() => run(() => deleteRange.mutateAsync(range.id))}
                              >
                                Remove
                              </Button>
                            )}
                            {range.state === "needs_rebuild" && (
                              <Button
                                size="small"
                                disabled={operationRunning || mutationBusy}
                                onClick={() => run(() => build.mutateAsync([range.id]))}
                              >
                                Build
                              </Button>
                            )}
                            {range.state === "building" && (
                              <Button
                                size="small"
                                disabled={cancel.isPending}
                                onClick={() => run(() => cancel.mutateAsync())}
                              >
                                Cancel
                              </Button>
                            )}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </Box>

              <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mt: 1.5 }}>
                <Typography variant="caption" color="text.secondary" sx={{ flex: 1 }}>
                  Stars and indexes use {formatBytes(status.total_bytes_used)} in NightCrate's data folder.
                </Typography>
                <Button
                  size="small"
                  variant="outlined"
                  disabled={buildableIds.length === 0 || operationRunning || mutationBusy}
                  onClick={() => {
                    const ids = [...buildableIds];
                    setSelection({ installKey, ids: new Set() });
                    run(() => build.mutateAsync(ids));
                  }}
                >
                  Build selected
                </Button>
              </Stack>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1.5 }}>
                {ATTRIBUTION}
              </Typography>
            </Box>
          </>
        )}
      </Paper>

      <FileBrowser
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onSelect={(path) => {
          setImportOpen(false);
          run(() => importCatalog.mutateAsync(path));
        }}
        accept={[".bz2", ".dat"]}
        title="Import plate-solving stars"
        emptyMessage="No Siril astrometry catalogue files here"
      />

      <Dialog open={removeOpen} onClose={() => setRemoveOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Remove plate-solving stars?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            This removes the stars and every built field range, freeing {formatBytes(status?.total_bytes_used ?? 0)} from NightCrate's data folder.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRemoveOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={() => {
              setRemoveOpen(false);
              run(() => deleteAll.mutateAsync());
            }}
          >
            Remove
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
