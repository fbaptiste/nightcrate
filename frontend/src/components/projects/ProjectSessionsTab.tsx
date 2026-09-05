import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Snackbar from "@mui/material/Snackbar";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import AutorenewIcon from "@mui/icons-material/Autorenew";
import DeleteIcon from "@mui/icons-material/Delete";
import EditIcon from "@mui/icons-material/Edit";
import NotesIcon from "@mui/icons-material/Notes";
import PersonOutlineIcon from "@mui/icons-material/PersonOutline";
import { fetchRigs } from "@/api/rigs";
import { fetchFilters } from "@/api/equipment";
import { fetchProject } from "@/api/projects";
import {
  type ProjectSession,
  type SessionCreate,
  createSession,
  deleteSession,
  deriveSessions,
  getIntegration,
  listSessions,
  updateSession,
} from "@/api/projectSessions";
import IntegrationBars, { formatHoursMinutes } from "./IntegrationBars";
import SessionFormDialog from "./SessionFormDialog";

interface Props {
  projectId: number;
}

export default function ProjectSessionsTab({ projectId }: Props) {
  const queryClient = useQueryClient();
  const [snack, setSnack] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<ProjectSession | null>(null);
  const [confirmDerive, setConfirmDerive] = useState(false);

  const { data: sessions = [], isLoading } = useQuery({
    queryKey: ["project-sessions", projectId],
    queryFn: () => listSessions(projectId),
  });
  const { data: integration } = useQuery({
    queryKey: ["project-integration", projectId],
    queryFn: () => getIntegration(projectId),
  });
  const { data: rigs = [] } = useQuery({ queryKey: ["rigs", "mine"], queryFn: () => fetchRigs(true, true) });
  const { data: filters = [] } = useQuery({
    queryKey: ["filters"],
    queryFn: () => fetchFilters(false, false),
  });
  // The project's rigs (full Rig objects) — used to surface their loaded
  // filters at the top of the filter pickers.
  const { data: project } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => fetchProject(projectId),
  });

  const projectRigs = useMemo(() => {
    const ids = new Set(project?.rigs.map((r) => r.id) ?? []);
    return rigs.filter((r) => ids.has(r.id));
  }, [project, rigs]);

  const rigFilterIds = useMemo(() => {
    const ids = new Set<number>();
    for (const rig of projectRigs) {
      for (const slot of rig.filter_slots) ids.add(slot.filter_id);
      if (rig.single_filter_id != null) ids.add(rig.single_filter_id);
    }
    return ids;
  }, [projectRigs]);

  // Derived rows go stale the moment the catalog changes and nothing re-derives on
  // its own, so surface how many there are and when they were last built. One pass.
  const { derivedCount, manualCount, lastDerived } = useMemo(() => {
    let derived = 0;
    let latest: string | null = null;
    for (const s of sessions) {
      if (s.source !== "auto") continue;
      derived += 1;
      if (latest === null || s.created_at > latest) latest = s.created_at;
    }
    return {
      derivedCount: derived,
      manualCount: sessions.length - derived,
      lastDerived: latest,
    };
  }, [sessions]);
  const countsCaption = [
    derivedCount > 0 ? `${derivedCount} derived` : null,
    manualCount > 0 ? `${manualCount} manual` : null,
    // created_at is SQLite's "YYYY-MM-DD HH:MM:SS" — take the date part rather
    // than feeding a non-ISO string to Date(), which Safari rejects outright.
    lastDerived ? `last derived ${lastDerived.slice(0, 10)}` : null,
  ]
    .filter(Boolean)
    .join(" \u00b7 ");

  // Shared with ProjectDetailPage's Overview — same query key, so TanStack
  // dedupes them and invalidating here refreshes the Overview's bars too.
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["project-sessions", projectId] });
    queryClient.invalidateQueries({ queryKey: ["project-integration", projectId] });
  };

  const deleteMut = useMutation({
    mutationFn: (id: number) => deleteSession(projectId, id),
    onSuccess: () => {
      refresh();
      setSnack("Session removed");
    },
    onError: (e) => setSnack(String(e)),
  });

  const deriveMut = useMutation({
    mutationFn: () => deriveSessions(projectId),
    onSuccess: (r) => {
      refresh();
      const skipped = r.lights_skipped
        ? `, ${r.lights_skipped} skipped (no exposure time)`
        : "";
      setSnack(
        r.sessions_created === 0
          ? `No sessions derived — this project has no cataloged light frames${skipped}`
          : `Derived ${r.sessions_created} session${r.sessions_created === 1 ? "" : "s"} ` +
            `from ${r.lights_considered} light frames${skipped}`,
      );
    },
    onError: (e) => setSnack(String(e)),
  });

  const handleSubmit = async (body: SessionCreate) => {
    if (editing) {
      await updateSession(projectId, editing.id, body);
    } else {
      await createSession(projectId, body);
    }
    refresh();
    setSnack(editing ? "Session updated" : "Session added");
  };

  if (isLoading) {
    return (
      <Box sx={{ p: 2 }}>
        <CircularProgress size={24} />
      </Box>
    );
  }

  return (
    <Box sx={{ maxWidth: 900 }}>
      <Box sx={{ display: "flex", alignItems: "center", mb: 0.5 }}>
        <Typography variant="h6">Imaging Sessions</Typography>
        <Box sx={{ display: "flex", gap: 1, ml: "50px" }}>
          <Button
            variant="contained"
            size="small"
            startIcon={<AddIcon />}
            onClick={() => {
              setEditing(null);
              setFormOpen(true);
            }}
          >
            Add session
          </Button>
          <Tooltip title="Rebuild the derived sessions from this project's cataloged light frames — one row per night, filter, exposure and gain. Sessions you added by hand are never touched.">
            <span>
              <Button
                variant="outlined"
                size="small"
                startIcon={
                  deriveMut.isPending ? <CircularProgress size={14} /> : <AutorenewIcon />
                }
                onClick={() => (derivedCount > 0 ? setConfirmDerive(true) : deriveMut.mutate())}
                disabled={deriveMut.isPending}
              >
                {deriveMut.isPending ? "Deriving\u2026" : "Derive from subs"}
              </Button>
            </span>
          </Tooltip>
        </Box>
      </Box>

      {sessions.length > 0 && (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1.5 }}>
          {countsCaption}
        </Typography>
      )}

      {sessions.length === 0 ? (
        <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
          No sessions yet. Add one by hand, or derive them from the light frames you have
          already cataloged.
        </Typography>
      ) : (
        <TableContainer sx={{ maxHeight: "60dvh" }}>
        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell>Date</TableCell>
              <TableCell>Filter</TableCell>
              <TableCell align="right">Exp (s)</TableCell>
              <TableCell align="right">Gain</TableCell>
              <TableCell align="right">Subs</TableCell>
              <TableCell align="right">Bin</TableCell>
              <TableCell align="right">Time</TableCell>
              <TableCell>Rig</TableCell>
              <TableCell>Source</TableCell>
              <TableCell align="right" />
            </TableRow>
          </TableHead>
          <TableBody>
            {sessions.map((s) => {
              const derived = s.source === "auto";
              return (
              <TableRow key={s.id} hover>
                <TableCell
                  sx={{
                    borderLeft: 3,
                    borderLeftColor: derived ? "secondary.main" : "primary.main",
                    pl: 1.5,
                  }}
                >
                  {s.session_date?.slice(0, 10) ?? "—"}
                </TableCell>
                <TableCell sx={{ maxWidth: 200 }}>
                  {/* filter_label first: a derived row also carries a canonical
                      line_name purely to satisfy the table CHECK, so the label is
                      the only place the real header name survives. */}
                  <Tooltip title={s.filter_label ?? s.filter_name ?? s.line_name ?? ""}>
                    <Box
                      component="span"
                      sx={{
                        display: "inline-block",
                        maxWidth: "100%",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        verticalAlign: "bottom",
                      }}
                    >
                      {s.filter_label ?? s.filter_name ?? s.line_name ?? "—"}
                    </Box>
                  </Tooltip>
                  {s.notes && (
                    <Tooltip title={s.notes}>
                      <NotesIcon fontSize="inherit" sx={{ ml: 0.5, verticalAlign: "middle" }} />
                    </Tooltip>
                  )}
                </TableCell>
                <TableCell align="right">{s.exposure_seconds}</TableCell>
                <TableCell align="right">{s.gain ?? "—"}</TableCell>
                <TableCell align="right">{s.num_subs}</TableCell>
                <TableCell align="right">
                  {s.binning != null ? `${s.binning}x${s.binning}` : "—"}
                </TableCell>
                <TableCell align="right">{formatHoursMinutes(s.integration_minutes)}</TableCell>
                <TableCell>{s.rig_name ?? "—"}</TableCell>
                <TableCell>
                  <Tooltip
                    title={
                      derived
                        ? "Rebuilt from the catalog. Correct the frames on the Catalog tab, then derive again."
                        : "Entered by hand. Never touched by a derive."
                    }
                  >
                    <Chip
                      size="small"
                      variant="outlined"
                      color={derived ? "secondary" : "primary"}
                      icon={
                        derived ? (
                          <AutorenewIcon fontSize="small" />
                        ) : (
                          <PersonOutlineIcon fontSize="small" />
                        )
                      }
                      label={derived ? "derived" : "manual"}
                    />
                  </Tooltip>
                </TableCell>
                {/* Derived rows carry no actions: editing one is a lie (the next
                    derive replaces it) and so is deleting one (it comes back). */}
                <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
                  {!derived && (
                    <>
                      <IconButton
                        size="small"
                        aria-label="Edit session"
                        onClick={() => {
                          setEditing(s);
                          setFormOpen(true);
                        }}
                      >
                        <EditIcon fontSize="small" />
                      </IconButton>
                      <IconButton
                        size="small"
                        aria-label="Delete session"
                        onClick={() => deleteMut.mutate(s.id)}
                      >
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </>
                  )}
                </TableCell>
              </TableRow>
              );
            })}
          </TableBody>
        </Table>
        </TableContainer>
      )}

      <Divider sx={{ my: 5 }} />

      {integration && <IntegrationBars summary={integration} />}

      {formOpen && (
        <SessionFormDialog
          key={editing?.id ?? "new"}
          open
          onClose={() => setFormOpen(false)}
          session={editing}
          rigs={rigs}
          filters={filters}
          rigFilterIds={rigFilterIds}
          projectRigs={projectRigs}
          onSubmit={handleSubmit}
        />
      )}

      <Dialog open={confirmDerive} onClose={() => setConfirmDerive(false)}>
        <DialogTitle>Replace derived sessions?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            This deletes the {derivedCount} derived session
            {derivedCount === 1 ? "" : "s"} and rebuilds them from this project&apos;s
            cataloged light frames.
            {manualCount > 0 &&
              ` Your ${manualCount} hand-entered session${manualCount === 1 ? "" : "s"} ${
                manualCount === 1 ? "is" : "are"
              } left untouched.`}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmDerive(false)}>Cancel</Button>
          <Button
            color="error"
            variant="contained"
            onClick={() => {
              setConfirmDerive(false);
              deriveMut.mutate();
            }}
          >
            Replace
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={!!snack}
        autoHideDuration={3000}
        onClose={() => setSnack(null)}
        message={snack}
      />
    </Box>
  );
}
